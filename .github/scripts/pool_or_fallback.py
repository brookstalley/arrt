"""Run every suite on testament's pool, and decide what CI does when the pool cannot answer.

`tests.yml` calls this twice. `pool` installs the client from the pool's console and
runs the suites there, retrying with backoff for up to ten minutes while the pool
cannot give a verdict; it records what happened in `decision.json` and tells the
workflow one of three modes. `summary` writes the job summary from that record.

The three modes, each with its own headline, because a quiet "cannot tell" is read as
a pass:

- **pool**: the pool gave a verdict, `passed` or `failed`. A `failed` verdict is a
  result: it is never retried and never sent to the fallback, because a second run
  that passed, or a run elsewhere that passed, would hide the failure (AGENTS.md
  § Running tests; `testament guide client`, "CI with a fallback").
- **fallback**: the pool could not answer for ten minutes: the console would not
  serve the client (a connection failure, a 5xx, a 429), or `testament run` ended
  `verdict: unavailable` with exit 75. The workflow then runs lint and every suite
  `.testament.toml` declares that needs no labelled runner on GitHub's runner,
  directly with uv; the suites that `require` a label (the browser suite needs
  Chrome) are not run, and the summary says so.
- **none**: nothing ran, and the job fails: no key (a pull request from a fork), the
  console refused the key or the address, the wheel did not match its digest, the
  client could not be installed, or `testament run` ended in a way the contract does
  not call "the pool could not decide" (a refusal, an unknown exit code, no envelope).

`assert_tests_ran.py --decision` reads the same record and re-checks it with
`fallback_is_earned`, so a record claiming a fallback the evidence does not support
fails the job.

Usage:
  pool_or_fallback.py pool --out DIR -- testament run ...
  pool_or_fallback.py summary --out DIR
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

#: How long the pool may stay unable to answer before the fallback runs, and the waits
#: between attempts (the last repeats). The owner's ruling 4 of 2026-11-19 and the
#: plan's DECISION: ten minutes.
BUDGET_S = 600
BACKOFF_S = (15, 30, 60, 120)

#: curl's exit codes that mean the console could not be reached or did not finish
#: answering: resolve a proxy or host, connect, a partial body, a timeout, the TLS
#: handshake, an empty reply, send and receive failures, an HTTP/2 stream error.
#: Any other curl failure (a malformed address, a certificate refused) is a
#: configuration fault, not an outage.
_CURL_UNREACHABLE = {5, 6, 7, 18, 28, 35, 52, 55, 56, 92}
#: HTTP statuses that mean the console is up but cannot serve now. 401, 403 and 404
#: are a refused key or a wrong address, which the fallback must not paper over.
_HTTP_UNAVAILABLE = {408, 429}

#: The words the summary opens with, one per mode, and the one for no record at all.
HEADLINES = {
    "pool": "Ran on the pool: every suite, the browser suite included.",
    "fallback": "The pool was unavailable; ran here, on GitHub's runner, without the browser suite.",
    "none": "Nothing ran.",
}
NO_RECORD = "Nothing ran: the pool step recorded no decision (lint failed before it, or the job was cancelled)."


@dataclasses.dataclass
class Attempt:
    """One try at the pool: installing the client, or running the suites. Only what the decision reads."""

    step: str  # "install" or "run"
    curl_exit: int | None = None
    http_status: int | None = None
    exit_code: int | None = None
    verdict: str | None = None
    verdict_reason: str | None = None
    retryable: bool | None = None
    has_envelope: bool = False
    local_fallback: bool = False
    detail: str = ""


def classify(a: Attempt) -> str:
    """What one attempt means: `ok` (installed), `passed`, `failed`, `retry`, `unavailable` or `broken`.

    `retry` and `unavailable` are the only two that may lead to the fallback; `retry`
    waits and tries again while the budget lasts, `unavailable` goes at once (the
    pool said a retry would not help).
    """
    if a.step == "install":
        if a.curl_exit == 0 and not a.detail:
            return "ok"
        if a.curl_exit in _CURL_UNREACHABLE:
            return "retry"
        if a.curl_exit == 22 and a.http_status is not None and (a.http_status >= 500 or a.http_status in _HTTP_UNAVAILABLE):
            return "retry"
        return "broken"
    if a.step != "run" or not a.has_envelope or a.local_fallback:
        return "broken"
    if a.verdict == "failed":
        # Whatever the exit code and whatever `retryable` says: an older client said
        # retryable for a `batches_lost` that cut a red short.
        return "failed"
    if a.verdict == "passed" and a.exit_code == 0:
        return "passed"
    if a.verdict == "unavailable" and a.exit_code == 75:
        return "retry" if a.retryable else "unavailable"
    # A verdict and an exit code the contract does not pair, or a verdict it does not
    # name: "any other code is a failure (never fall back on it)".
    return "broken"


def fallback_is_earned(attempts: list[Attempt]) -> bool:
    """Whether a run of attempts ends where only the fallback can follow.

    Every install before the last succeeded or could not reach the console, every run
    could not decide, and the last attempt is one that could not answer. A passed,
    failed or broken attempt anywhere ends the loop, so a record holding one never
    earns the fallback.
    """
    if not attempts:
        return False
    kinds = [classify(a) for a in attempts]
    if kinds[-1] not in ("retry", "unavailable"):
        return False
    return all(k in ("ok", "retry") for k in kinds[:-1])


@dataclasses.dataclass
class Decision:
    mode: str  # "pool", "fallback" or "none"
    why: str
    attempts: list[Attempt]
    verdict: str | None = None
    #: In fallback mode: the suites run here, each with the report it writes, and the ones not run, with why.
    reports: dict[str, str] = dataclasses.field(default_factory=dict)
    not_run: dict[str, str] = dataclasses.field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        """The pool step's own exit: 0 when the job goes on (a pass, or the fallback), 1 otherwise."""
        return 0 if self.mode == "fallback" or (self.mode == "pool" and self.verdict == "passed") else 1

    def to_json(self) -> dict:
        return {
            "mode": self.mode,
            "why": self.why,
            "verdict": self.verdict,
            "attempts": [dataclasses.asdict(a) for a in self.attempts],
            "reports": self.reports,
            "not_run": self.not_run,
        }

    @classmethod
    def from_json(cls, data: dict) -> Decision:
        return cls(
            mode=data["mode"],
            why=data.get("why", ""),
            verdict=data.get("verdict"),
            attempts=[Attempt(**a) for a in data.get("attempts", [])],
            reports=dict(data.get("reports") or {}),
            not_run=dict(data.get("not_run") or {}),
        )


def fallback_plan(manifest: dict) -> tuple[dict[str, str], dict[str, str]]:
    """The suites the fallback runs, each with its report's path under the output directory, and those it does not.

    Derived from `.testament.toml`: a suite that `requires` a runner label (the browser
    suite needs `chrome`) runs only where the pool's labelled runners are, and every
    other suite runs here. A suite added to the manifest is therefore expected of the
    fallback the day it is added, and `assert_tests_ran.py` fails the job until the
    workflow runs it.
    """
    reports, not_run = {}, {}
    for name, suite in manifest.get("suites", {}).items():
        needs = suite.get("requires") or []
        if needs:
            not_run[name] = f"needs a runner labelled {', '.join(needs)}, which only the pool has"
        else:
            reports[name] = f"fallback/{name}.xml"
    return reports, not_run


class Pool(Protocol):
    def install(self) -> Attempt: ...
    def run(self) -> Attempt: ...


def drive(
    pool: Pool,
    manifest: dict,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    budget: float = BUDGET_S,
    backoff: tuple[float, ...] = BACKOFF_S,
    say: Callable[[str], None] = print,
) -> Decision:
    """Install, run, retry while the pool cannot answer and the budget lasts; decide."""
    start = clock()
    attempts: list[Attempt] = []
    waits = 0

    def wait() -> bool:
        nonlocal waits
        remaining = start + budget - clock()
        if remaining <= 0:
            return False
        delay = min(backoff[min(waits, len(backoff) - 1)], remaining)
        waits += 1
        reason = attempts[-1].detail or attempts[-1].verdict_reason
        say(f"::warning::the pool could not answer ({reason}); trying again in {delay:.0f} s")
        sleep(delay)
        return True

    def fallback(why: str) -> Decision:
        reports, not_run = fallback_plan(manifest)
        say(
            f"::warning::{HEADLINES['fallback']} {why}. Running {', '.join(reports)} here directly with uv; "
            f"not run: {', '.join(not_run) or 'none'}."
        )
        return Decision("fallback", why, attempts, reports=reports, not_run=not_run)

    for step in ("install", "run"):
        while True:
            attempt = pool.install() if step == "install" else pool.run()
            attempts.append(attempt)
            kind = classify(attempt)
            if kind == "ok":
                break
            if kind in ("passed", "failed"):
                return Decision(
                    "pool", f"the pool's verdict is {attempt.verdict} ({attempt.verdict_reason})", attempts, verdict=kind
                )
            if kind == "broken":
                why = attempt.detail or f"testament run ended verdict {attempt.verdict!r}, exit {attempt.exit_code}"
                say(f"::error::{HEADLINES['none']} {why}")
                return Decision("none", why, attempts)
            reason = attempt.detail or attempt.verdict_reason or "unavailable"
            if kind == "unavailable":
                return fallback(f"the pool answered unavailable ({reason}) and said a retry would not help")
            if not wait():
                return fallback(f"the pool could not answer for {budget / 60:g} minutes ({reason})")
    raise AssertionError("unreachable: the run step always decides")


# -- the real pool -------------------------------------------------------------


def _header(headers: str, pattern: str) -> str | None:
    found = [m.group(1) for m in re.finditer(pattern, headers.replace("\r", ""), re.M)]
    return found[-1] if found else None


class RealPool:
    """The pool as `tests.yml` reaches it: the console's wheel, then `testament run`."""

    def __init__(self, out: Path, run_argv: list[str], env: dict[str, str] | None = None):
        self.out = out
        self.run_argv = run_argv
        self.env = dict(os.environ if env is None else env)
        self.runs = 0

    def install(self) -> Attempt:
        key, console = self.env.get("TESTAMENT_KEY", ""), self.env.get("TESTAMENT_CONSOLE", "")
        if not key or not console:
            return Attempt(
                "install",
                curl_exit=-1,
                detail=(
                    "the TESTAMENT_KEY secret or the TESTAMENT_CONSOLE variable is not set "
                    "(a pull request from a fork gets neither)"
                ),
            )
        wheel = self.out / "wheel"
        wheel.mkdir(parents=True, exist_ok=True)
        for old in wheel.iterdir():
            old.unlink()
        # The key goes to curl on stdin, never in argv.
        config = f'header = "Authorization: Bearer {key}"\nurl = "{console.rstrip("/")}/api/v1/cli/wheel"\n'
        done = subprocess.run(
            [
                "curl",
                "-fsS",
                "--connect-timeout",
                "20",
                "--max-time",
                "180",
                "-K",
                "-",
                "-D",
                "headers.txt",
                "-o",
                "wheel.bin",
                "-w",
                "%{http_code}",
            ],
            input=config,
            capture_output=True,
            text=True,
            cwd=wheel,
        )
        status = int(done.stdout.strip()) if done.stdout.strip().isdigit() else None
        if done.returncode != 0:
            return Attempt(
                "install",
                curl_exit=done.returncode,
                http_status=status,
                detail=done.stderr.strip() or f"curl exited {done.returncode}",
            )
        headers = (wheel / "headers.txt").read_text(encoding="utf-8", errors="replace")
        name = _header(headers, r'^[Cc]ontent-[Dd]isposition:.*filename="?([^";/]+\.whl)"?')
        want = _header(headers, r"^[Xx]-[Tt]estament-[Ww]heel-[Ss][Hh][Aa]256: *([0-9A-Fa-f]+)")
        if not name or not want:
            first = headers.splitlines()[0] if headers else ""
            return Attempt(
                "install", curl_exit=0, http_status=status, detail=f"the console's answer named no wheel or no digest: {first}"
            )
        body = (wheel / "wheel.bin").read_bytes()
        if hashlib.sha256(body).hexdigest() != want.lower():
            return Attempt(
                "install", curl_exit=0, http_status=status, detail="the wheel does not match the digest the console sent"
            )
        (wheel / "wheel.bin").rename(wheel / name)
        done = subprocess.run(
            ["uv", "tool", "install", "--force", "--python", "3.14", f"./{name}"], cwd=wheel, capture_output=True, text=True
        )
        if done.returncode != 0:
            return Attempt(
                "install", curl_exit=0, http_status=status, detail=f"uv tool install failed: {done.stderr.strip()[-300:]}"
            )
        return Attempt("install", curl_exit=0, http_status=status)

    def run(self) -> Attempt:
        self.runs += 1
        if shutil.which(self.run_argv[0], path=self.env.get("PATH")) is None:
            # `uv tool install` puts the client in uv's tool directory, which this step's
            # PATH may not carry yet.
            bin_dir = subprocess.run(["uv", "tool", "dir", "--bin"], capture_output=True, text=True).stdout.strip()
            self.env["PATH"] = f"{bin_dir}{os.pathsep}{self.env.get('PATH', '')}"
        envelope = self.out / "envelope.json"
        with envelope.open("w", encoding="utf-8") as stdout:
            code = subprocess.run(self.run_argv, stdout=stdout, env=self.env).returncode
        # Each attempt's envelope is kept, so a retried run can be read afterwards.
        (self.out / f"envelope-{self.runs}.json").write_bytes(envelope.read_bytes())
        return attempt_from_envelope(envelope, code)


def attempt_from_envelope(path: Path, exit_code: int) -> Attempt:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return Attempt("run", exit_code=exit_code, detail=f"testament run wrote no envelope that parses: {e}")
    if not isinstance(data, dict):
        return Attempt("run", exit_code=exit_code, detail="testament run's envelope is not an object")
    error = data.get("error") or {}
    return Attempt(
        "run",
        exit_code=exit_code,
        verdict=data.get("verdict"),
        verdict_reason=data.get("verdict_reason"),
        retryable=bool(error.get("retryable")),
        has_envelope=True,
        local_fallback=bool(data.get("fallback")),
        detail="testament ran the tests on GitHub's runner despite --no-fallback" if data.get("fallback") else "",
    )


# -- the summary -----------------------------------------------------------------


def _junit_counts(path: Path) -> str:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return "no report"
    suites = root.findall(".//testsuite") or ([root] if root.tag == "testsuite" else [])
    total = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    return f"{total['tests']} collected, {total['failures']} failed, {total['errors']} errored, {total['skipped']} skipped"


def _attempt_line(a: Attempt) -> str:
    if a.step == "install":
        said = f"curl exit {a.curl_exit}" + (f", HTTP {a.http_status}" if a.http_status else "")
    else:
        said = f"verdict {a.verdict} ({a.verdict_reason}), exit {a.exit_code}, retryable {a.retryable}"
    return f"- {a.step}: {said}: {classify(a)}" + (f". {a.detail}" if a.detail else "")


def summary_lines(out: Path) -> tuple[list[str], list[str]]:
    """The job summary's lines, and the annotations to print, from what the pool step recorded."""
    lines: list[str] = []
    notes: list[str] = []
    try:
        decision = Decision.from_json(json.loads((out / "decision.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f"### {NO_RECORD}", "", f"(`decision.json`: {e})"], [f"::error::{NO_RECORD}"]
    lines += [f"### {HEADLINES.get(decision.mode, HEADLINES['none'])}", "", decision.why, ""]
    if decision.mode == "fallback":
        lines.append("| Where | What |")
        lines.append("|---|---|")
        lines.append("| GitHub's runner | lint and format |")
        for suite, report in decision.reports.items():
            lines.append(f"| GitHub's runner | the {suite} suite: {_junit_counts(out / report)} |")
        for suite, why in decision.not_run.items():
            lines.append(f"| **not run** | the {suite} suite: {why}. Run it on the pool before merging, when the pool is back. |")
        lines.append("")
    if decision.mode == "pool":
        lines.append("Lint and format ran on GitHub's runner; every suite ran on the pool.")
        try:
            env = json.loads((out / "envelope.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            env = {}
        r = env.get("report") or {}
        lines.append(
            f"verdict {env.get('verdict')} ({env.get('verdict_reason')}), exit {env.get('exit_code')}; counts {r.get('counts')}"
        )
        if env.get("error"):
            lines.append(f"**Error** `{env['error'].get('code')}`: {env['error'].get('message')}")
        if r.get("missing"):
            lines.append(f"**Never reported ({len(r['missing'])}):** " + ", ".join(r["missing"][:20]))
        for i in [i for i in r.get("items", []) if i.get("outcome") in ("failed", "error")][:50]:
            text = (i.get("message") or "").strip().splitlines() or [""]
            said = [t[1:].strip() for t in text if t.startswith("E ")]
            last = (said[0] if said else text[-1])[:300]
            lines.append(f"- `{i['id']}` {i['outcome']} on {i.get('runner')}: {last}")
            title = i["id"].replace("%", "%25").replace(":", "%3A").replace(",", "%2C")
            notes.append(f"::error title={title}::{last.replace('%', '%25')}")
        lines.append("")
    lines.append("Attempts at the pool:")
    lines += [_attempt_line(a) for a in decision.attempts] or ["- none"]
    if decision.mode == "none":
        notes.append(f"::error::{HEADLINES['none']} {decision.why}")
    return lines, notes


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] in ("pool", "summary") and argv[1] == "--out":
        out = Path(argv[2])
        out.mkdir(parents=True, exist_ok=True)
        if argv[0] == "summary" and len(argv) == 3:
            lines, notes = summary_lines(out)
            for note in notes:
                print(note)
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            else:
                print("\n".join(lines))
            return 0
        if argv[0] == "pool" and len(argv) > 4 and argv[3] == "--":
            manifest = tomllib.loads(Path(".testament.toml").read_text(encoding="utf-8"))
            decision = drive(RealPool(out, argv[4:]), manifest)
            (out / "decision.json").write_text(json.dumps(decision.to_json(), indent=2), encoding="utf-8")
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with open(output, "a", encoding="utf-8") as f:
                    f.write(f"mode={decision.mode}\n")
            print(f"mode {decision.mode}: {decision.why}")
            return decision.exit_code
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
