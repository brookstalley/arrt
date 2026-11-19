"""Fail when an opt-in suite reported success without actually testing anything.

**Two kinds of suite depend on this, not one.** The live probes are the obvious
half; the pool run in `tests.yml`, which includes the browser suite, is the other,
and it needs exactly the same protection for a different missing dependency — the browser suite skips itself when the `browser`
group or the downloaded Chromium is absent, which in CI is a provisioning failure
that would otherwise report a green client-coverage job having executed no line of
the client. Written out because an earlier version of this docstring described
only the live suites, so the guard read as narrower than the workflows that
actually call it.

**The whole opt-in-probe design depends on this.** Every test in those suites skips
itself cleanly when its dependency is absent — `skipif(not OPENROUTER_API_KEY)`,
`pytest.skip("dezoomify-rs is not installed")` — which is right for a developer's
machine and is a trap in CI. An expired secret, a rename, a failed binary install:
each gives a completely green pytest run that made no request and verified
nothing, and a scheduled job whose job is to notice change would go on reporting
success for as long as it stayed broken.

So a skip here is read as a provisioning failure rather than a legitimate
absence. In CI every dependency is meant to be present; if one is not, that is
the finding.

**An `xfail` is not one of those skips, and the distinction is load-bearing.**
pytest reports an expected failure in JUnit as a `<skipped>` element and counts
it in the suite's `skipped` attribute — indistinguishable from a missing
dependency if you read the attribute, which is what this file used to do. An
`xfail` is the opposite of an unprovisioned test: it ran, it failed exactly as
recorded, and the recording is a deliberate artefact of a decision someone wrote
down. Failing the job on one would mean a suite could never carry a documented
expected failure and a CI leg at the same time.

Found the day the default suites first got a CI leg: the curation suite carries
one `xfail`, and the job went red naming a "dependency not provisioned" that was
a documented order-sensitivity in artist identity. Nothing was broken; the guard
was reading the wrong number.

**A run on the pool, or a fallback without the browser suite.** `tests.yml` passes
`--decision`, the record `pool_or_fallback.py` wrote of where the suites ran. On the
pool, the report the run wrote must hold every suite the manifest declares, as
before. In a fallback, the record must earn it (its attempts end where only the
pool's own trouble could, `fallback_is_earned`), and then each suite the fallback
runs must have run something in its own report, and only the suites the manifest
says need a labelled runner may be missing. A pool record that excuses any suite,
or a fallback record whose excused suites are not exactly those, fails: "browser not
run" is a property of an earned fallback, never a flag a normal run can carry.

Usage: assert_tests_ran.py <junit-xml-path> [--suites-from <testament manifest> [--decision <decision.json>]]
"""

import importlib.util
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

#: How testament's merged JUnit opens an expected failure: `[<phase>] xfail`, then a
#: colon and the reason, or nothing when there is no reason. Matched against the
#: element's text, whose first line is that opening, and against `message`, which
#: keeps only the last line of a multi-line reason.
_TESTAMENT_XFAIL = re.compile(r"\[\w+\]\s*xfail(:|$)")


def _is_testament_xfail(skip: ET.Element) -> bool:
    first_line = (skip.text or "").strip().split("\n", 1)[0]
    return bool(_TESTAMENT_XFAIL.match(first_line) or _TESTAMENT_XFAIL.match(skip.get("message", "")))


def suites_in(manifest: Path) -> list[str]:
    """The suite names a testament manifest declares, in its order."""
    return list(tomllib.loads(manifest.read_text(encoding="utf-8")).get("suites", {}))


def main(path: Path, required_suites: list[str] | None = None) -> int:
    if not path.is_file():
        # pytest writes the file even when every test fails, so its absence means
        # pytest never got far enough to run — a collection error, a bad marker
        # expression, or an install that did not complete.
        print(f"::error::{path} does not exist — pytest never produced a report.")
        return 1

    root = ET.parse(path).getroot()
    # `testsuite` is nested under `testsuites` in pytest's output, but has been
    # the root element in older versions. Handle both rather than assume.
    suites = root.findall(".//testsuite") or ([root] if root.tag == "testsuite" else [])
    if not suites:
        print(f"::error::{path} contains no testsuite element.")
        return 1

    tests = sum(int(s.get("tests", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    ran = tests - skipped

    # The suite attribute counts expected failures alongside real skips, so the
    # cases are walked to tell them apart. pytest's own report gives an `xfail`
    # type "pytest.xfail". testament's merged report, which CI reads, gives no
    # type and starts the message `[<phase>] xfail:`; only that exact opening
    # counts, so a skip whose reason merely mentions xfail stays a skip. Anything
    # else is read as a real skip, because the safe direction for an unknown is
    # to fail the job rather than pass it.
    blocking = []
    expected_failures = 0
    for suite in suites:
        for case in suite.iter("testcase"):
            skip = case.find("skipped")
            if skip is None:
                continue
            if skip.get("type") == "pytest.xfail" or _is_testament_xfail(skip):
                expected_failures += 1
                continue
            name = f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":")
            blocking.append((name, skip.get("message", "no reason given")))

    # A report whose suite attribute claims skips but carries no `<skipped>` case
    # elements is one this walk cannot classify. Trust the attribute there: a
    # tool that omits the detail must not thereby win a pass.
    if skipped and not blocking and not expected_failures:
        blocking = [("<unnamed>", f"{skipped} skip(s) reported at suite level with no testcase detail")]

    summary = f"collected {tests}, ran {ran}, skipped {len(blocking)}, failed {failures}, errored {errors}"
    if expected_failures:
        summary += f", xfailed {expected_failures}"
    print(summary)

    if tests == 0:
        print("::error::No tests were collected. The marker expression selected nothing.")
        return 1

    if blocking:
        # Named individually — "3 skipped" does not tell you which dependency is
        # missing, and that is the only thing worth knowing here.
        for name, message in blocking:
            print(f"::error::skipped in CI: {name} — {message}")
        print(
            f"::error::{len(blocking)} test(s) skipped. In CI a skip means a dependency was not provisioned "
            "— an absent or expired secret, or a failed install — not a legitimate absence. "
            "This job verified less than it appears to have."
        )
        return 1

    if ran == 0:
        print("::error::Nothing ran.")
        return 1

    # A report merged across suites can carry hundreds of tests from one while another
    # collected nothing, so each suite the run was meant to cover is checked by name.
    empty = []
    for name in required_suites or []:
        found = [s for s in suites if s.get("name") == name]
        ran_here = sum(int(s.get("tests", 0)) - int(s.get("skipped", 0)) for s in found)
        if ran_here <= 0:
            empty.append(name if found else f"{name} (not in the report)")
    if empty:
        print(f"::error::these suites ran no test: {', '.join(empty)}. Each suite .testament.toml declares must run something.")
        return 1

    return 0


def _decider():
    """`pool_or_fallback.py`, beside this file, which owns what a fallback is."""
    spec = importlib.util.spec_from_file_location("pool_or_fallback", Path(__file__).with_name("pool_or_fallback.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("pool_or_fallback", module)
    spec.loader.exec_module(module)
    return module


def main_with_decision(path: Path, manifest: Path, decision_path: Path) -> int:
    """Check the run `decision_path` records: on the pool, `path` with every suite; in a fallback, each suite's own report."""
    decider = _decider()
    try:
        decision = decider.Decision.from_json(json.loads(decision_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"::error::{decider.NO_RECORD} ({decision_path}: {e})")
        return 1
    suites = suites_in(manifest)
    if decision.mode == "none":
        print(f"::error::{decider.HEADLINES['none']} {decision.why}")
        return 1
    if decision.mode == "pool":
        if decision.not_run or decision.reports:
            print(
                f"::error::the record says the pool ran, yet excuses {sorted(decision.not_run)} and names fallback reports "
                f"{sorted(decision.reports)}: a run on the pool must hold every suite"
            )
            return 1
        print(HEADLINES_POOL)
        return main(path, suites)
    if decision.mode != "fallback":
        print(f"::error::the record's mode is {decision.mode!r}, which is none of pool, fallback and none")
        return 1
    if not decider.fallback_is_earned(decision.attempts):
        print(
            "::error::the record claims a fallback that its attempts do not earn; a fallback follows only a pool that "
            "could not answer, never a verdict: " + "; ".join(decider._attempt_line(a) for a in decision.attempts)
        )
        return 1
    reports, not_run = decider.fallback_plan(tomllib.loads(manifest.read_text(encoding="utf-8")))
    if decision.reports != reports or sorted(decision.not_run) != sorted(not_run):
        print(
            f"::error::the fallback ran {sorted(decision.reports)} and excused {sorted(decision.not_run)}, but the manifest "
            f"asks it to run {sorted(reports)} and excuses only {sorted(not_run)}"
        )
        return 1
    print(decider.HEADLINES["fallback"])
    worst = 0
    for suite, report in reports.items():
        print(f"{suite}, on GitHub's runner:")
        worst = max(worst, main(decision_path.parent / report, [suite]))
    for suite, why in not_run.items():
        print(f"::warning::the {suite} suite did not run: {why}")
    return worst


HEADLINES_POOL = "Ran on the pool: every suite the manifest declares must be in the report."


if __name__ == "__main__":
    # `assert_tests_ran.py <report> [--suites-from <testament manifest> [--decision <decision.json>]]`
    if len(sys.argv) == 2:
        raise SystemExit(main(Path(sys.argv[1])))
    if len(sys.argv) == 4 and sys.argv[2] == "--suites-from":
        raise SystemExit(main(Path(sys.argv[1]), suites_in(Path(sys.argv[3]))))
    if len(sys.argv) == 6 and sys.argv[2] == "--suites-from" and sys.argv[4] == "--decision":
        raise SystemExit(main_with_decision(Path(sys.argv[1]), Path(sys.argv[3]), Path(sys.argv[5])))
    print(__doc__)
    raise SystemExit(2)
