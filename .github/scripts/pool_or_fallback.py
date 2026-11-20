"""Run every suite on testament's pool, and decide what CI does when the pool cannot answer.

`tests.yml` calls this three times. `pool` installs the client from the pool's console
and runs the suites there, retrying with backoff for up to ten minutes while the pool
cannot give a verdict; it records what happened in `decision.json` and tells the
workflow one of three modes. `summary` writes the job summary from that record.
`browser-verdict` is the whole of the second, non-required job: green when the pool
gave the verdict, red after a fallback, because then the browser suite has none.

The three modes, each with its own headline, because a quiet "cannot tell" is read as
a pass:

- **pool**: the pool gave a verdict, `passed` or `failed`. A `failed` verdict is a
  result: it is never retried and never sent to the fallback, because a second run
  that passed, or a run elsewhere that passed, would hide the failure (AGENTS.md
  § Running tests; `testament guide client`, "CI with a fallback").
- **fallback**: the pool could not answer for ten minutes: the console would not
  serve the client (a connection failure, a 5xx, a 429), `testament run` ended
  `verdict: unavailable` with exit 75, or the pool did not accept the run; or the
  pool accepted the run and gave no verdict by the step's deadline. The workflow
  then runs lint and every suite `.testament.toml` declares that needs no labelled
  runner on GitHub's runner, directly with uv; the suites that `require` a label (the
  browser suite needs Chrome) are not run, and the summary and the second job say so.
- **none**: nothing ran, and the job fails: no key (a pull request from a fork), the
  console refused the key or the address, the wheel did not match its digest, the
  client could not be installed, `testament run` ended in a way the contract does not
  call "the pool could not decide" (a refusal, an unknown exit code, no envelope), its
  envelope has a shape this cannot read, or the pool reported a failing test and then
  ran out of time (a red is a result, never a fallback).

**Time.** No attempt outlives the step. The whole pool step has `DEADLINE_S`, twenty
minutes, about three times a healthy full run of the four suites on the pool (six to
seven). A run the pool has not accepted within `ACCEPT_S` is stopped and retried as
"could not answer"; a run the pool accepted and still holds at the deadline is
stopped and sent to the fallback. The client prints nothing between "collected" and
the first failure, so a run whose tests are running cannot be told from one gone
quiet: the deadline, never silence, is what stops an accepted run. The record is
written before the first attempt and after each one, so a step killed anyway leaves
a record naming its attempts, never the headline that blames lint.

`assert_tests_ran.py --decision` reads the same record and re-checks it with
`fallback_is_earned`, so a record claiming a fallback the evidence does not support
fails the job: the attempts' kinds, and their recorded times, which must account for
the ten minutes (or the deadline) the fallback claims to have waited out.

Usage:
  pool_or_fallback.py pool --out DIR -- testament run ...
  pool_or_fallback.py summary --out DIR
  POOL_MODE=<mode> pool_or_fallback.py browser-verdict
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
import threading
import time
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import IO, Protocol

#: How long the pool may stay unable to answer before the fallback runs, and the waits
#: between attempts (the last repeats). The owner's ruling 4 of 2026-11-19 and the
#: plan's DECISION: ten minutes.
BUDGET_S = 600
BACKOFF_S = (15, 30, 60, 120)
#: The whole pool step's time, installs and every run included: about three times a
#: healthy full run on the pool (six to seven minutes for the four suites, 2026-11-19).
#: `tests.yml` gives the step two minutes more than this, and the job room for this,
#: every other step and the fallback's (`tests/test_ci_fallback.py` holds the sums).
DEADLINE_S = 1200
#: How long `testament run` may go without the pool accepting it ("request <id>
#: accepted" on its stderr, which comes within seconds when the pool is up).
ACCEPT_S = 120
#: How long `uv tool install` may take over the console's wheel.
INSTALL_S = 300

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
#: The record the pool step holds from before its first attempt until it decides.
STOPPED = (
    "the pool step stopped before it decided: it ran past its time limit or was killed, "
    "after the attempts below (none, if it stopped before the first)"
)
#: How the decision names an envelope it cannot read.
UNREADABLE = "the pool could not give a verdict I can read"

#: The second job's name, and what it says after a fallback. Not a required check: an
#: outage must not block a merge (ruling 4 of 2026-11-19); this is the mark, not
#: prose, that a tree has no browser verdict.
BROWSER_JOB = "The browser suite ran on the pool"
BROWSER_NO_VERDICT = (
    "The browser suite has no verdict for this tree: the pool could not answer, and the fallback ran every "
    "other suite on GitHub's runner without it. To get one, re-run all of this workflow's jobs once the pool "
    "is back, or run `testament run --json=summary --suite browser` on this branch's head and put its "
    "request id on the pull request."
)


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
    #: Seconds from the step's start when the attempt began and ended, and how long the
    #: step waited after it. Written by `drive`; `fallback_is_earned` reads them.
    started_s: float | None = None
    ended_s: float | None = None
    waited_s: float = 0.0
    #: Why the run was stopped, if it was: `not_accepted` or `deadline`.
    killed: str | None = None
    accepted: bool = False
    #: The tests the pool reported failing (its FAILED and ERROR progress lines) before the run was stopped.
    failures_seen: list[str] = dataclasses.field(default_factory=list)


def classify(a: Attempt) -> str:
    """What one attempt means: `ok` (installed), `passed`, `failed`, `retry`, `unavailable`, `timeout` or `broken`.

    `retry`, `unavailable` and `timeout` are the only three that may lead to the
    fallback. `retry` waits and tries again while the budget lasts; `unavailable` goes
    at once (the pool said a retry would not help), and so does `timeout` (the pool
    accepted the run and held it to the deadline, so no time is left for another).
    """
    if a.step == "install":
        if a.curl_exit == 0 and not a.detail:
            return "ok"
        if a.curl_exit in _CURL_UNREACHABLE:
            return "retry"
        if a.curl_exit == 22 and a.http_status is not None and (a.http_status >= 500 or a.http_status in _HTTP_UNAVAILABLE):
            return "retry"
        return "broken"
    if a.step == "run" and a.killed:
        if a.failures_seen:
            # The pool said a test failed before the time ran out: a red, never a fallback.
            return "broken"
        if a.killed == "not_accepted":
            return "retry"
        return "timeout" if a.killed == "deadline" else "broken"
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


#: How far apart, in seconds, one attempt's end plus its wait and the next one's start
#: may be in a record: the driver does nothing between them but print.
_CLOCK_SLACK_S = 2.0


def _is_seconds(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def _times_account(attempts: list[Attempt]) -> bool:
    """Whether the record's times are a driver's: each attempt begins when the one before it ended and waited."""
    previous_end = None
    for a in attempts:
        if not (_is_seconds(a.started_s) and _is_seconds(a.ended_s) and _is_seconds(a.waited_s)):
            return False
        if a.started_s > a.ended_s:
            return False
        if previous_end is not None and abs(a.started_s - previous_end) > _CLOCK_SLACK_S:
            return False
        previous_end = a.ended_s + a.waited_s
    return True


def fallback_is_earned(attempts: list[Attempt], budget: float = BUDGET_S, deadline: float = DEADLINE_S) -> bool:
    """Whether a run of attempts ends where only the fallback can follow, having waited out what it claims.

    Every install before the last succeeded or could not reach the console, every run
    could not decide, and the last attempt is one that could not answer. A passed,
    failed or broken attempt anywhere ends the loop, so a record holding one never
    earns the fallback. Then the time: every attempt starts when the one before it
    ended and waited; a record ending `retry` has spent the budget (its last attempt
    ends at least `budget` seconds in), and one ending `timeout` reached the deadline.
    Only `unavailable`, which the pool said a retry would not mend, goes at once. A
    record with no times (one written before they were kept) earns nothing.
    """
    if not attempts:
        return False
    kinds = [classify(a) for a in attempts]
    if kinds[-1] not in ("retry", "unavailable", "timeout"):
        return False
    if not all(k in ("ok", "retry") for k in kinds[:-1]):
        return False
    if not _times_account(attempts):
        return False
    last = attempts[-1]
    if kinds[-1] == "retry":
        return last.ended_s >= budget
    if kinds[-1] == "timeout":
        return last.ended_s >= deadline
    return True


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
    def run(self, limit_s: float) -> Attempt: ...


def drive(
    pool: Pool,
    manifest: dict,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    budget: float = BUDGET_S,
    backoff: tuple[float, ...] = BACKOFF_S,
    say: Callable[[str], None] = print,
    deadline: float = DEADLINE_S,
    checkpoint: Callable[[list[Attempt]], None] = lambda attempts: None,
) -> Decision:
    """Install, run, retry while the pool cannot answer and the budget lasts; decide by the deadline.

    `checkpoint` is handed the attempts after each one and each wait, so the record a
    killed step leaves names them.
    """
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
        attempts[-1].waited_s = delay
        checkpoint(attempts)
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
            began = clock()
            if step == "run":
                limit = start + deadline - began
                if limit < min(ACCEPT_S, deadline):
                    why = f"no time was left in the step's {deadline / 60:g} minutes to start a run ({limit:.0f} s)"
                    say(f"::error::{HEADLINES['none']} {why}")
                    return Decision("none", why, attempts)
                raw = pool.run(limit)
            else:
                raw = pool.install()
            # A copy: a pool may hand back one object twice, and each attempt keeps its own times.
            attempt = dataclasses.replace(raw, started_s=began - start, ended_s=clock() - start, waited_s=0.0)
            attempts.append(attempt)
            checkpoint(attempts)
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
            if kind == "timeout":
                return fallback(f"the pool gave no verdict within the step's {deadline / 60:g} minutes ({reason})")
            if not wait():
                return fallback(f"the pool could not answer for {budget / 60:g} minutes ({reason})")
    raise AssertionError("unreachable: the run step always decides")


# -- the real pool -------------------------------------------------------------


def _header(headers: str, pattern: str) -> str | None:
    found = [m.group(1) for m in re.finditer(pattern, headers.replace("\r", ""), re.M)]
    return found[-1] if found else None


#: `testament run`'s progress on stderr (AGENTS.md § Running tests): the pool accepting
#: a suite's request, the tests it collected, and each test that failed or errored.
#: A run of one suite prints each line bare; a run of several, which is what a pull
#: request is, prefixes each with the suite's name in brackets (`[browser] request …`).
#: Both are matched: read bare only, every pull request's run looked never accepted,
#: was stopped after `ACCEPT_S`, and fell back (`tests/test_ci_fallback.py` holds the
#: lines as they were observed).
_SUITE = r"^(?:\[[^\]]+\]\s+)?"
_ACCEPTED = re.compile(_SUITE + r"request ([0-9a-f]+) accepted\b")
_COLLECTED = re.compile(_SUITE + r"collected (\d+) items?\b")
_FAILING = re.compile(_SUITE + r"(?:FAILED|ERROR)\s+(\S+)")


class Progress:
    """What `testament run` has said on stderr so far, each line passed on to this step's log."""

    def __init__(self, echo: Callable[[str], object]):
        self.echo = echo
        self.accepted = threading.Event()
        self.requests: list[str] = []
        self.collected = 0
        self.failures: list[str] = []

    def read(self, stream: IO[str]) -> None:
        for line in stream:
            self.echo(line)
            text = line.strip()
            if m := _ACCEPTED.match(text):
                self.requests.append(m.group(1))
                self.accepted.set()
            elif m := _COLLECTED.match(text):
                self.collected += int(m.group(1))
            elif m := _FAILING.match(text):
                self.failures.append(m.group(1))


def _stop(proc: subprocess.Popen) -> None:
    """Ask the client to stop, so it can let the pool go; then make it."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


class RealPool:
    """The pool as `tests.yml` reaches it: the console's wheel, then `testament run`."""

    def __init__(
        self,
        out: Path,
        run_argv: list[str],
        env: dict[str, str] | None = None,
        accept_s: float = ACCEPT_S,
        poll_s: float = 1.0,
        echo: Callable[[str], object] = sys.stderr.write,
    ):
        self.out = out
        self.run_argv = run_argv
        self.env = dict(os.environ if env is None else env)
        self.accept_s = accept_s
        self.poll_s = poll_s
        self.echo = echo
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
        try:
            done = subprocess.run(
                ["uv", "tool", "install", "--force", "--python", "3.14", f"./{name}"],
                cwd=wheel,
                capture_output=True,
                text=True,
                timeout=INSTALL_S,
            )
        except subprocess.TimeoutExpired:
            return Attempt("install", curl_exit=0, http_status=status, detail=f"uv tool install did not finish in {INSTALL_S} s")
        if done.returncode != 0:
            return Attempt(
                "install", curl_exit=0, http_status=status, detail=f"uv tool install failed: {done.stderr.strip()[-300:]}"
            )
        return Attempt("install", curl_exit=0, http_status=status)

    def run(self, limit_s: float) -> Attempt:
        """`testament run`, stopped if the pool has not accepted it in `accept_s`, or at all by `limit_s`."""
        self.runs += 1
        if shutil.which(self.run_argv[0], path=self.env.get("PATH")) is None:
            # `uv tool install` puts the client in uv's tool directory, which this step's
            # PATH may not carry yet.
            bin_dir = subprocess.run(["uv", "tool", "dir", "--bin"], capture_output=True, text=True, timeout=60).stdout.strip()
            self.env["PATH"] = f"{bin_dir}{os.pathsep}{self.env.get('PATH', '')}"
        envelope = self.out / "envelope.json"
        progress = Progress(self.echo)
        begun = time.monotonic()
        killed = None
        with envelope.open("w", encoding="utf-8") as stdout:
            proc = subprocess.Popen(
                self.run_argv, stdout=stdout, stderr=subprocess.PIPE, text=True, errors="replace", env=self.env
            )
            reader = threading.Thread(target=progress.read, args=(proc.stderr,), daemon=True)
            reader.start()
            while proc.poll() is None:
                elapsed = time.monotonic() - begun
                if elapsed >= limit_s:
                    killed = "deadline"
                elif not progress.accepted.is_set() and elapsed >= self.accept_s:
                    killed = "not_accepted"
                if killed:
                    _stop(proc)
                    break
                try:
                    proc.wait(timeout=self.poll_s)
                except subprocess.TimeoutExpired:
                    pass
            reader.join(timeout=10)
        elapsed = time.monotonic() - begun
        # Each attempt's envelope is kept, so a retried run can be read afterwards.
        (self.out / f"envelope-{self.runs}.json").write_bytes(envelope.read_bytes())
        if killed:
            return Attempt(
                "run",
                exit_code=proc.returncode,
                killed=killed,
                accepted=progress.accepted.is_set(),
                failures_seen=progress.failures[:20],
                detail=_stopped_detail(killed, progress, elapsed, self.accept_s),
            )
        return dataclasses.replace(attempt_from_envelope(envelope, proc.returncode), accepted=progress.accepted.is_set())


def _stopped_detail(killed: str, progress: Progress, elapsed: float, accept_s: float) -> str:
    if progress.failures:
        return (
            f"the pool reported {len(progress.failures)} failing test(s) ({', '.join(progress.failures[:5])}) and then "
            f"gave no verdict in {elapsed:.0f} s, so the run was stopped; a red is a result, so nothing falls back"
        )
    if killed == "not_accepted":
        return f"the pool did not accept the run within {accept_s:.0f} s, so it was stopped"
    if progress.accepted.is_set():
        return (
            f"the pool accepted the run (request {', '.join(progress.requests)}), collected {progress.collected} tests "
            f"and gave no verdict in {elapsed:.0f} s, all the step had left, so it was stopped"
        )
    return f"testament run did not finish in {elapsed:.0f} s, all the step had left, so it was stopped"


def _type_name(v: object) -> str:
    return f"a {type(v).__name__} ({json.dumps(v)[:80]})"


def envelope_shape_problem(data: object) -> str | None:
    """What in an envelope is not the shape AGENTS.md § Running tests gives it, among the fields read here; or None.

    Every field this script or its summary reads: `verdict`, `verdict_reason`,
    `status`, `error` (and its `retryable`, `code` and `message`), `fallback`, `setup`,
    `report` (and its `counts`, `missing` and `items`, each item's `id`, `outcome`,
    `message` and `runner`). Absent or null is always readable.
    """
    if not isinstance(data, dict):
        return f"the envelope is {_type_name(data)}, not an object"
    for key in ("verdict", "verdict_reason", "status"):
        if data.get(key) is not None and not isinstance(data[key], str):
            return f"`{key}` is {_type_name(data[key])}, not a string"
    for key in ("error", "setup", "report"):
        if data.get(key) is not None and not isinstance(data[key], dict):
            return f"`{key}` is {_type_name(data[key])}, not an object"
    if data.get("fallback") not in (None, False) and not isinstance(data["fallback"], dict):
        return f"`fallback` is {_type_name(data['fallback'])}, not an object"
    error = data.get("error") or {}
    if error.get("retryable") is not None and not isinstance(error["retryable"], bool):
        return f"`error.retryable` is {_type_name(error['retryable'])}, not true or false"
    for key in ("code", "message"):
        if error.get(key) is not None and not isinstance(error[key], str):
            return f"`error.{key}` is {_type_name(error[key])}, not a string"
    report = data.get("report") or {}
    if report.get("counts") is not None and not isinstance(report["counts"], dict):
        return f"`report.counts` is {_type_name(report['counts'])}, not an object"
    for key in ("missing", "items"):
        if report.get(key) is not None and not isinstance(report[key], list):
            return f"`report.{key}` is {_type_name(report[key])}, not a list"
    if not all(isinstance(m, str) for m in report.get("missing") or []):
        return "`report.missing` holds something that is not a test id"
    for item in report.get("items") or []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            return f"`report.items` holds {_type_name(item)}, not a test with an id"
        for key in ("outcome", "message", "runner"):
            if item.get(key) is not None and not isinstance(item[key], str):
                return f"`report.items[].{key}` is {_type_name(item[key])}, not a string"
    return None


def attempt_from_envelope(path: Path, exit_code: int) -> Attempt:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return Attempt("run", exit_code=exit_code, detail=f"testament run wrote no envelope that parses: {e}")
    problem = envelope_shape_problem(data)
    if problem:
        return Attempt("run", exit_code=exit_code, detail=f"{UNREADABLE}: testament run's envelope has {problem}")
    error = data.get("error") or {}
    return Attempt(
        "run",
        exit_code=exit_code,
        verdict=data.get("verdict"),
        verdict_reason=data.get("verdict_reason"),
        retryable=error.get("retryable") is True,
        has_envelope=True,
        local_fallback=bool(data.get("fallback")),
        detail="testament ran the tests on GitHub's runner despite --no-fallback" if data.get("fallback") else "",
    )


# -- the summary -----------------------------------------------------------------


def _junit_counts(path: Path) -> str:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return "**no report**: the step did not finish (its time limit) or pytest never started; see its log"
    suites = root.findall(".//testsuite") or ([root] if root.tag == "testsuite" else [])
    total = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    return f"{total['tests']} collected, {total['failures']} failed, {total['errors']} errored, {total['skipped']} skipped"


def _attempt_line(a: Attempt) -> str:
    if a.step == "install":
        said = f"curl exit {a.curl_exit}" + (f", HTTP {a.http_status}" if a.http_status else "")
    elif a.killed:
        said = f"stopped ({a.killed}), exit {a.exit_code}"
    else:
        said = f"verdict {a.verdict} ({a.verdict_reason}), exit {a.exit_code}, retryable {a.retryable}"
    if isinstance(a.started_s, (int, float)) and isinstance(a.ended_s, (int, float)):
        said += f", {a.started_s:.0f}-{a.ended_s:.0f} s" + (f", then waited {a.waited_s:.0f} s" if a.waited_s else "")
    return f"- {a.step}: {said}: {classify(a)}" + (f". {a.detail}" if a.detail else "")


def _envelope_lines(out: Path, notes: list[str]) -> list[str]:
    try:
        env = json.loads((out / "envelope.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        env = {}
    problem = envelope_shape_problem(env)
    if problem:
        return [f"{UNREADABLE}: the envelope has {problem}"]
    r = env.get("report") or {}
    lines = [f"verdict {env.get('verdict')} ({env.get('verdict_reason')}), exit {env.get('exit_code')}; counts {r.get('counts')}"]
    if env.get("error"):
        lines.append(f"**Error** `{env['error'].get('code')}`: {env['error'].get('message')}")
    if r.get("missing"):
        lines.append(f"**Never reported ({len(r['missing'])}):** " + ", ".join(r["missing"][:20]))
    for i in [i for i in r.get("items") or [] if i.get("outcome") in ("failed", "error")][:50]:
        text = (i.get("message") or "").strip().splitlines() or [""]
        said = [t[1:].strip() for t in text if t.startswith("E ")]
        last = (said[0] if said else text[-1])[:300]
        lines.append(f"- `{i['id']}` {i['outcome']} on {i.get('runner')}: {last}")
        title = i["id"].replace("%", "%25").replace(":", "%3A").replace(",", "%2C")
        notes.append(f"::error title={title}::{last.replace('%', '%25')}")
    return lines


def summary_lines(out: Path) -> tuple[list[str], list[str]]:
    """The job summary's lines, and the annotations to print, from what the pool step recorded."""
    lines: list[str] = []
    notes: list[str] = []
    try:
        decision = Decision.from_json(json.loads((out / "decision.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        return [f"### {NO_RECORD}", "", f"(`decision.json`: {e})"], [f"::error::{NO_RECORD}"]
    lines += [f"### {HEADLINES.get(decision.mode, HEADLINES['none'])}", "", decision.why, ""]
    if decision.mode == "fallback":
        lines.append("| Where | What |")
        lines.append("|---|---|")
        lines.append("| GitHub's runner | lint and format |")
        for suite, report in decision.reports.items():
            lines.append(f"| GitHub's runner | the {suite} suite: {_junit_counts(out / report)} |")
        for suite, why in decision.not_run.items():
            lines.append(f"| **not run** | the {suite} suite: {why}. |")
        lines += ["", f"The check **{BROWSER_JOB}** is red for this tree. {BROWSER_NO_VERDICT}", ""]
    if decision.mode == "pool":
        lines.append("Lint and format ran on GitHub's runner; every suite ran on the pool.")
        lines += _envelope_lines(out, notes)
        lines.append("")
    lines.append("Attempts at the pool:")
    lines += [_attempt_line(a) for a in decision.attempts] or ["- none"]
    if decision.mode == "none":
        notes.append(f"::error::{HEADLINES['none']} {decision.why}")
    return lines, notes


# -- the second job ----------------------------------------------------------------


def browser_verdict(mode: str) -> tuple[int, str]:
    """The second job's exit and its one line, from the first job's mode."""
    if mode == "pool":
        return 0, "The browser suite ran on the pool, in the run whose verdict the required check carries."
    if mode == "fallback":
        return 1, f"::error title={BROWSER_JOB}::{BROWSER_NO_VERDICT}"
    return 1, (
        f"::error title={BROWSER_JOB}::the first job recorded no mode the browser's verdict can be read from "
        f"({mode!r}), so nothing says the browser suite ran"
    )


def _write_decision(out: Path, decision: Decision) -> None:
    (out / "decision.json").write_text(json.dumps(decision.to_json(), indent=2), encoding="utf-8")


def main(argv: list[str]) -> int:
    if argv == ["browser-verdict"]:
        code, line = browser_verdict(os.environ.get("POOL_MODE", ""))
        print(line)
        return code
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
            # Before anything can hang: a step killed from here on leaves this record, not none.
            _write_decision(out, Decision("none", STOPPED, []))
            manifest = tomllib.loads(Path(".testament.toml").read_text(encoding="utf-8"))
            decision = drive(
                RealPool(out, argv[4:]),
                manifest,
                checkpoint=lambda attempts: _write_decision(out, Decision("none", STOPPED, list(attempts))),
            )
            _write_decision(out, decision)
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
