"""Decide whether a drift-probe job failed, knowing which of its red probes are excused.

**Why the job's verdict is made here and not by pytest's exit code.** Seven weeks of
scheduled runs went red on probes whose cause nobody had established (#109, #110,
#150), and an alarm that is always red cannot tell a museum moving its API from the
day before. The owner ruled on 2026-11-19 that those probes are marked known-blocked
in `.github/known-blocked.json` (the shape is `known_blocked.py`'s) instead of each
being investigated by hand first. pytest cannot make that distinction: it exits 1 for
a red test whoever listed it. So the probe step records pytest's exit and its JUnit
report, and this reads both.

The four verdicts, each by name, each tested:

- a probe that is **red and listed** is excused. The job's summary says which, and
  until when, so the excuse is visible on every run it is used.
- a probe that is **red and not listed** fails the job. That is a new red, which is
  the thing the alarm exists to show.
- a probe that is **listed and green** fails the job, telling whoever reads it to
  delete the row. A stale excuse is how the alarm went quiet the first time.
- a **row that is itself wrong** (no issue, an expiry past or more than 60 days out,
  a probe that does not exist) fails the job, naming the row.

**"Blocked" is not "never ran".** A probe that skipped, a report that is missing or
holds no test, a run in which nothing ran, a pytest that exited with anything but "all
passed" or "some failed": each fails the job even when every red test in it is listed.
A row excuses a probe that ran and is red; it never excuses a probe that did not run,
because that is `assert_tests_ran.py`'s finding and the one a missing secret produces.

Usage: judge_drift_probes.py <junit-xml> --pytest-exit <code> --contract <name>
           [--verdict <json to write>] [--now <ISO date>]
Appends a summary to $GITHUB_STEP_SUMMARY when that is set.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import known_blocked  # noqa: E402  (a sibling script, not a package)


def test_id(classname: str, name: str) -> str:
    """The row-style id (`<file>::<Class>::<function>`) of a JUnit testcase.

    Parametrization is dropped, so a row naming the function covers every case of it.
    A collection error has no module and comes back as whatever pytest called it,
    which no row names, so it fails as red-and-unlisted, by that name.
    """
    function = name.split("[", 1)[0]
    parts = [p for p in classname.split(".") if p]
    split = next((i for i, p in enumerate(parts) if p[:1].isupper()), len(parts))
    module, classes = parts[:split], parts[split:]
    if not module:
        return function
    return "::".join(["/".join(module) + ".py", *classes, function])


def outcomes(report: Path) -> tuple[dict[str, str], int, int] | str:
    """Per test id: "red", "skipped" or "green"; and how many cases collected and ran.

    Or a string saying why the report cannot be read, which is a failure of its own.
    A test with several cases is red if any case is, so a row excuses the red cases
    and the green ones beside them do not make it stale.
    """
    if not report.is_file():
        return f"{report} does not exist, so pytest never produced a report: the probes did not run"
    try:
        root = ET.parse(report).getroot()
    except ET.ParseError as error:
        return f"{report} is not a readable JUnit report ({error}): the probes did not run"
    cases: dict[str, set[str]] = defaultdict(set)
    collected = ran = 0
    for case in root.iter("testcase"):
        collected += 1
        name = test_id(case.get("classname", ""), case.get("name", ""))
        if case.find("failure") is not None or case.find("error") is not None:
            cases[name].add("red")
        elif (skip := case.find("skipped")) is not None:
            if skip.get("type") == "pytest.xfail":
                cases[name].add("xfail")  # an expected failure ran and is neither red nor green
                ran += 1
            else:
                cases[name].add("skipped")
            continue
        else:
            cases[name].add("green")
        ran += 1
    verdicts = {}
    for name, seen in cases.items():
        verdicts[name] = "red" if "red" in seen else "skipped" if "skipped" in seen else "xfail" if "xfail" in seen else "green"
    return verdicts, collected, ran


def judge(
    report: Path,
    blocked_file: Path,
    pytest_exit: str,
    today: date,
    tests_root: Path = known_blocked.TESTS_ROOT,
) -> tuple[list[str], list[known_blocked.Row], int]:
    """(failures, the rows that excused something, how many probes passed)."""
    rows, failures = known_blocked.check(blocked_file, today, tests_root)
    listed = {row.test: row for row in rows}

    # `known_blocked.check` drops a refused row, so a probe it was meant to excuse
    # falls through to "red and not listed" below as well: both findings print.
    if pytest_exit not in {"0", "1"}:
        failures.append(
            f"pytest exited {pytest_exit or 'with no recorded exit code'}; only 0 (all passed) and 1 "
            "(some failed) mean the probes ran, so this run verified nothing"
        )

    read = outcomes(report)
    if isinstance(read, str):
        return failures + [read], [], 0
    verdicts, collected, ran = read
    if collected == 0:
        failures.append("the report holds no test: the marker selected nothing, so nothing ran")
    elif ran == 0:
        failures.append(
            "nothing ran: every probe was skipped, so a probe was not provisioned; that is not a probe that is blocked"
        )

    excused: list[known_blocked.Row] = []
    passed = 0
    for name, verdict in sorted(verdicts.items()):
        row = listed.get(name)
        if verdict == "red" and row:
            excused.append(row)
        elif verdict == "red":
            failures.append(
                f"{name} is red and is not in .github/known-blocked.json. This is a probe that has "
                "moved, or broken, since the listed ones were measured"
            )
        elif verdict == "skipped":
            failures.append(
                f"{name} skipped, so it did not run"
                + (f" (its known-blocked row, #{row.issue}, excuses a red probe, not one that never ran)" if row else "")
                + ". In CI a skip means a dependency was not provisioned"
            )
        elif verdict == "green":
            passed += 1
            if row:
                failures.append(
                    f"{name} is listed in .github/known-blocked.json (#{row.issue}) but its probe has turned "
                    "green. Delete the row from .github/known-blocked.json: a stale excuse is how this alarm "
                    "went quiet the first time"
                )

    if pytest_exit == "1" and not any(v == "red" for v in verdicts.values()):
        failures.append("pytest exited 1 but the report holds no failing probe: something failed that the report does not show")
    return failures, excused, passed


def summary(contract: str, failures: list[str], excused: list[known_blocked.Row], passed: int) -> str:
    lines = [f"### Drift probes: {contract}", ""]
    if excused:
        lines.append("Excused as known-blocked (red, listed in `.github/known-blocked.json`):")
        lines += [f"- `{row.test}`: #{row.issue}, until {row.expires.isoformat()}. {row.reason}" for row in excused]
        lines.append("")
    if failures:
        lines.append("Failing this job:")
        lines += [f"- {each}" for each in failures]
    else:
        lines.append(f"{passed} probe(s) passed; nothing is failing that is not excused above.")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    args = list(argv)

    def option(flag: str) -> str | None:
        if flag in args:
            at = args.index(flag)
            value = args[at + 1] if at + 1 < len(args) else ""
            del args[at : at + 2]
            return value
        return None

    pytest_exit = option("--pytest-exit")
    contract = option("--contract")
    verdict_out = option("--verdict")
    now = option("--now")
    if len(args) != 1 or pytest_exit is None or not contract:
        print(__doc__)
        return 2
    today = date.fromisoformat(now) if now else datetime.now(UTC).date()

    failures, excused, passed = judge(Path(args[0]), known_blocked.BLOCKED_FILE, pytest_exit, today)

    text = summary(contract, failures, excused, passed)
    print(text)
    for each in failures:
        print(f"::error::{contract}: {each}")
    if target := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text)
    if verdict_out:
        Path(verdict_out).write_text(
            json.dumps(
                {
                    "contract": contract,
                    "failures": failures,
                    "excused": [{"test": r.test, "issue": r.issue, "expires": r.expires.isoformat()} for r in excused],
                }
            ),
            encoding="utf-8",
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
