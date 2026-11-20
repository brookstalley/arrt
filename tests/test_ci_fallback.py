"""CI's fallback: what runs when testament's pool cannot answer, and that nothing else reaches it.

Ruling 4 of 2026-11-19 makes CI required to merge once the pool has a fallback, and
the 2026-11-18 ruling keeps the suites off GitHub's runners. The two meet in
`.github/scripts/pool_or_fallback.py`, which `tests.yml` calls: it retries a pool that
cannot answer for ten minutes, then sends the job to the fallback steps, which run
every suite needing no labelled runner here, without the browser suite, and without
the real-Player suite, the pool's alone by the owner's ruling of 2026-11-20.

What the old `--no-fallback`-only job guaranteed without saying so, and what holds it now:

- **Green meant the pool ran every suite, browser included.** Now green means that only
  when the summary opens "Ran on the pool". The summary opens with one of three lines on
  every path (`test_the_summary_opens_with_*`), and a fallback names the browser suite
  as not run. `assert_tests_ran.py --decision` refuses a pool record that excuses any
  suite (`tests/test_assert_tests_ran.py`).
- **GitHub's minutes were never spent on suites.** Now they are only during an outage:
  the decision reaches the fallback only from the pool's two "cannot answer" endings,
  never from a `failed` verdict (`test_only_an_unavailable_ending_reaches_the_fallback`),
  and the workflow's fallback steps run only on that decision
  (`test_the_workflow_falls_back_only_on_the_decision`).

The decision is tested against envelopes recorded from testament 0.58.0 on 2026-11-19
(passed, failed, and unavailable from a coordinator that refused the connection),
trimmed to the keys the script reads, runner names replaced; the population-mismatch
and older-client shapes are built from AGENTS.md § Running tests, which states them.
"""

import dataclasses
import importlib.util
import itertools
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tomllib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".github" / "scripts" / "pool_or_fallback.py"
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"
MANIFEST = tomllib.loads((REPO / ".testament.toml").read_text(encoding="utf-8"))


def _load():
    spec = importlib.util.spec_from_file_location("pool_or_fallback", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["pool_or_fallback"] = module
    spec.loader.exec_module(module)
    return module


pof = _load()

# -- recorded envelopes ------------------------------------------------------------------

#: `testament run --json=summary --suite governance -- tests/test_one_python.py`, request 35bd2ccc.
PASSED = {
    "status": "passed",
    "exit_code": 0,
    "verdict": "passed",
    "verdict_reason": "passed",
    "report": {"counts": {"passed": 6}},
}
#: A one-line red test on the pool, request 1577d6e4. No `error` key.
FAILED = {
    "status": "failed",
    "exit_code": 1,
    "verdict": "failed",
    "verdict_reason": "tests_failed",
    "report": {
        "counts": {"failed": 1},
        "items": [
            {
                "id": "tests/test_red.py::test_red",
                "outcome": "failed",
                "runner": "runner-a",
                "message": (
                    '[call] def test_red():\n>       assert 1 == 2, "a recorded red"\n' "E       AssertionError: a recorded red"
                ),
            }
        ],
    },
}
#: `--no-fallback` against a coordinator that refused the connection, request 4e59578f.
UNAVAILABLE = {
    "status": "coordinator_unreachable",
    "exit_code": 75,
    "verdict": "unavailable",
    "verdict_reason": "coordinator_unreachable",
    "error": {"code": "coordinator_unreachable", "message": "governance: connect call failed", "retryable": True, "ran": 0},
}
#: AGENTS.md: "A non-empty list is never a pass: `population_mismatch`, exit 2, verdict `failed`".
POPULATION_MISMATCH = {
    "exit_code": 2,
    "verdict": "failed",
    "verdict_reason": "population_mismatch",
    "error": {"code": "population_mismatch", "retryable": False},
    "report": {"missing": ["arrt/tests/unit/test_a.py::test_b"]},
}
#: `testament guide client`: "a client from before that rule said true for a `batches_lost` that cut a red short".
OLD_CLIENT_RED_BATCHES_LOST = {
    "exit_code": 2,
    "verdict": "failed",
    "verdict_reason": "batches_lost",
    "error": {"code": "batches_lost", "retryable": True},
}
#: The pool's trouble, but one it says a retry will not mend.
UNAVAILABLE_FOR_GOOD = {
    "exit_code": 75,
    "verdict": "unavailable",
    "verdict_reason": "no_runner",
    "error": {"code": "no_runner", "retryable": False},
}


def run_attempt(envelope: dict | None, exit_code: int | None = None, tmp: pathlib.Path | None = None):
    """An attempt read the way the real pool reads one: from an envelope file and the exit code."""
    path = (tmp or pathlib.Path("/nonexistent")) / "envelope.json"
    if envelope is not None:
        path.write_text(json.dumps(envelope), encoding="utf-8")
    return pof.attempt_from_envelope(path, envelope["exit_code"] if exit_code is None and envelope else exit_code)


def install(curl_exit: int = 0, http_status: int | None = 200, detail: str = ""):
    return pof.Attempt("install", curl_exit=curl_exit, http_status=http_status, detail=detail)


#: The console's 503, as the 2026-11-19 outage gave it: `curl: (22) The requested URL returned error: 503`.
CONSOLE_503 = install(22, 503, "curl: (22) The requested URL returned error: 503")


class ScriptedPool:
    """A pool that answers from a script: install attempts, then run attempts; the last of each repeats."""

    def __init__(self, installs, runs):
        self.installs, self.runs = list(installs), list(runs)
        self.install_calls = self.run_calls = 0

    def install(self):
        self.install_calls += 1
        return self.installs[min(self.install_calls, len(self.installs)) - 1]

    def run(self, limit_s=None):
        self.run_calls += 1
        return self.runs[min(self.run_calls, len(self.runs)) - 1]


class Clock:
    """The step's clock: only sleeping and an attempt that takes time move it."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def drive(pool, clock=None, checkpoint=None):
    clock = clock or Clock()
    slept = []

    def sleep(s):
        slept.append(s)
        clock.now += s

    said = []
    extra = {"checkpoint": checkpoint} if checkpoint else {}
    decision = pof.drive(pool, MANIFEST, clock=clock, sleep=sleep, say=said.append, **extra)
    return decision, slept, said


# -- the decision, case by case -------------------------------------------------------------


def test_a_pool_that_passes_is_the_pool(tmp_path):
    pool = ScriptedPool([install()], [run_attempt(PASSED, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert (decision.mode, decision.verdict, decision.exit_code) == ("pool", "passed", 0)
    assert (pool.run_calls, slept) == (1, [])


def test_a_failed_verdict_is_a_result_never_retried_never_a_fallback(tmp_path):
    pool = ScriptedPool([install()], [run_attempt(FAILED, tmp=tmp_path), run_attempt(PASSED, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert (decision.mode, decision.verdict, decision.exit_code) == ("pool", "failed", 1)
    assert (pool.run_calls, slept, decision.reports, decision.not_run) == (1, [], {}, {})


def test_an_unavailable_pool_that_recovers_is_the_pool(tmp_path):
    pool = ScriptedPool([install()], [run_attempt(UNAVAILABLE, tmp=tmp_path), run_attempt(PASSED, tmp=tmp_path)])
    decision, slept, said = drive(pool)

    assert (decision.mode, decision.verdict, decision.exit_code) == ("pool", "passed", 0)
    assert (pool.run_calls, slept) == (2, [15])
    assert "coordinator_unreachable" in said[0]


def test_a_pool_unavailable_for_ten_minutes_falls_back_without_the_browser_suite(tmp_path):
    pool = ScriptedPool([install()], [run_attempt(UNAVAILABLE, tmp=tmp_path)])
    decision, slept, said = drive(pool)

    assert (decision.mode, decision.exit_code) == ("fallback", 0)
    assert sum(slept) == pof.BUDGET_S and slept[:4] == [15, 30, 60, 120]
    assert decision.reports == {s: f"fallback/{s}.xml" for s in ("governance", "curation", "contract")}
    assert sorted(decision.not_run) == ["browser", "player"]
    assert pof.fallback_is_earned(decision.attempts)
    assert "without the browser and real-Player suites" in said[-1]
    assert said[-1].endswith("not run: browser, player.")


def test_a_console_that_answers_503_for_ten_minutes_falls_back_and_never_runs(tmp_path):
    pool = ScriptedPool([CONSOLE_503], [run_attempt(PASSED, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert decision.mode == "fallback"
    assert pool.run_calls == 0 and sum(slept) == pof.BUDGET_S
    assert "503" in decision.why


def test_a_console_503_that_recovers_runs_on_the_pool(tmp_path):
    pool = ScriptedPool([CONSOLE_503, install()], [run_attempt(PASSED, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert (decision.mode, decision.verdict, slept) == ("pool", "passed", [15])


def test_the_install_and_the_run_share_one_ten_minute_budget(tmp_path):
    pool = ScriptedPool([CONSOLE_503] * 5 + [install()], [run_attempt(UNAVAILABLE, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert decision.mode == "fallback" and sum(slept) == pof.BUDGET_S


def test_a_population_mismatch_is_a_failed_result(tmp_path):
    pool = ScriptedPool([install()], [run_attempt(POPULATION_MISMATCH, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert (decision.mode, decision.verdict, decision.exit_code, pool.run_calls, slept) == ("pool", "failed", 1, 1, [])


def test_an_older_clients_retryable_red_is_still_a_red(tmp_path):
    pool = ScriptedPool([install()], [run_attempt(OLD_CLIENT_RED_BATCHES_LOST, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert (decision.mode, decision.verdict, pool.run_calls) == ("pool", "failed", 1)


def test_an_unavailable_ending_the_pool_says_will_not_mend_falls_back_at_once(tmp_path):
    pool = ScriptedPool([install()], [run_attempt(UNAVAILABLE_FOR_GOOD, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert (decision.mode, pool.run_calls, slept) == ("fallback", 1, [])


@pytest.mark.parametrize(
    "attempt",
    [
        install(-1, None, "the TESTAMENT_KEY secret or the TESTAMENT_CONSOLE variable is not set"),
        install(22, 401, "curl: (22) 401"),
        install(22, 403, "curl: (22) 403"),
        install(22, 404, "curl: (22) 404"),
        install(3, None, "curl: (3) URL malformed"),
        install(60, None, "curl: (60) certificate"),
        install(0, 200, "the wheel does not match the digest the console sent"),
        install(0, 200, "the console's answer named no wheel or no digest: HTTP/2 200"),
        install(0, 200, "uv tool install failed"),
    ],
    ids=["no-key", "401", "403", "404", "bad-url", "bad-cert", "digest", "no-wheel-name", "uv-install"],
)
def test_an_install_the_console_refused_or_spoiled_is_nothing_ran_not_a_fallback(attempt, tmp_path):
    pool = ScriptedPool([attempt], [run_attempt(PASSED, tmp=tmp_path)])
    decision, slept, said = drive(pool)

    assert (decision.mode, decision.exit_code, pool.run_calls, slept) == ("none", 1, 0, [])
    assert said[-1].startswith("::error::Nothing ran.")


@pytest.mark.parametrize("missing", ["TESTAMENT_KEY", "TESTAMENT_CONSOLE"])
def test_the_real_pool_with_no_key_or_console_runs_nothing_and_says_why(missing, tmp_path):
    """A pull request from a fork gets no secrets: the real install says so and asks nothing of the network."""
    env = {"TESTAMENT_KEY": "k", "TESTAMENT_CONSOLE": "https://console.invalid", missing: ""}
    pool = pof.RealPool(tmp_path, ["testament", "run"], env)
    decision, slept, _ = drive(pool)

    assert (decision.mode, decision.exit_code, pool.runs, slept) == ("none", 1, 0, [])
    assert "a pull request from a fork gets neither" in decision.why


@pytest.mark.parametrize(
    "curl_exit,status", [(6, None), (7, None), (28, None), (35, None), (56, None), (22, 500), (22, 502), (22, 429)]
)
def test_a_console_that_could_not_be_reached_is_retried(curl_exit, status):
    assert pof.classify(install(curl_exit, status, "curl failed")) == "retry"


@pytest.mark.parametrize(
    "envelope,exit_code",
    [
        (None, 1),  # no envelope at all
        ({**UNAVAILABLE, "exit_code": 2}, 2),  # unavailable, but an exit code the contract does not pair with it
        ({**PASSED, "exit_code": 1}, 1),  # passed, but the run did not exit 0
        ({**UNAVAILABLE, "fallback": {"reason": "coordinator_unreachable"}}, 0),  # testament ran it here itself
        ({"verdict": "maybe", "exit_code": 3}, 3),  # a verdict and a code the contract never names
        ({**UNAVAILABLE, "exit_code": 130}, 130),  # an interrupt
    ],
    ids=["no-envelope", "unavailable-exit-2", "passed-exit-1", "local-fallback", "unknown-verdict", "interrupt"],
)
def test_an_ending_the_contract_does_not_name_is_nothing_ran(envelope, exit_code, tmp_path):
    pool = ScriptedPool([install()], [run_attempt(envelope, exit_code, tmp=tmp_path)])
    decision, slept, _ = drive(pool)

    assert (decision.mode, decision.exit_code, pool.run_calls, slept) == ("none", 1, 1, [])


def test_only_an_unavailable_ending_reaches_the_fallback(tmp_path):
    """Every verdict against every exit code testament can give, retryable or not: the fallback follows only
    `unavailable` with 75, the one ending AGENTS.md calls "the pool could not give a verdict"."""
    reached = []
    for verdict, code, retryable in itertools.product(
        ["passed", "failed", "unavailable", None, "other"], [0, 1, 2, 5, 75, 130, 3], [True, False]
    ):
        envelope = {"verdict": verdict, "exit_code": code, "error": {"retryable": retryable}}
        decision, _, _ = drive(ScriptedPool([install()], [run_attempt(envelope, code, tmp=tmp_path)]))
        if decision.mode == "fallback":
            reached.append((verdict, code))
        if verdict == "failed":
            assert (decision.mode, decision.verdict) == ("pool", "failed"), (verdict, code, retryable)

    assert sorted(set(reached)) == [("unavailable", 75)]


def test_a_record_holding_a_verdict_never_earns_the_fallback(tmp_path):
    unavailable = run_attempt(UNAVAILABLE, tmp=tmp_path)
    # The records the driver writes when the pool cannot answer for ten minutes earn it.
    assert pof.fallback_is_earned(drive(ScriptedPool([install()], [unavailable]))[0].attempts)
    assert pof.fallback_is_earned(drive(ScriptedPool([CONSOLE_503], []))[0].attempts)
    assert not pof.fallback_is_earned([install(), run_attempt(FAILED, tmp=tmp_path), unavailable])
    assert not pof.fallback_is_earned([install(), run_attempt(FAILED, tmp=tmp_path)])
    assert not pof.fallback_is_earned([install(), run_attempt(PASSED, tmp=tmp_path)])
    assert not pof.fallback_is_earned([install(22, 401, "refused"), unavailable])
    assert not pof.fallback_is_earned([])


def test_the_fallback_plan_is_the_manifest_less_the_suites_that_need_a_labelled_runner_or_are_the_pools_alone():
    reports, not_run = pof.fallback_plan(MANIFEST)
    labelled = {name for name, suite in MANIFEST["suites"].items() if suite.get("requires")}

    assert set(reports) | set(not_run) == set(MANIFEST["suites"])
    assert labelled == {"browser"}
    assert set(not_run) == labelled | set(pof.POOL_ONLY) == {"browser", "player"}
    assert not_run["player"] == pof.POOL_ONLY["player"] and "2026-11-20" in not_run["player"]


def test_the_suites_the_pool_keeps_to_itself_are_suites_it_would_otherwise_run_here():
    """A name in `POOL_ONLY` the manifest no longer declares, or that a `requires` already keeps off this runner, is stale."""
    for name in pof.POOL_ONLY:
        assert name in MANIFEST["suites"], f"POOL_ONLY names {name!r}, which .testament.toml does not declare"
        assert not MANIFEST["suites"][name].get("requires"), f"{name!r} needs a labelled runner; POOL_ONLY adds nothing"


def test_the_words_for_the_suites_left_out_are_the_suites_the_fallback_leaves_out():
    """`LEFT_OUT` quotes the manifest and `POOL_ONLY`: every headline and the second job's message name exactly those."""
    _, not_run = pof.fallback_plan(MANIFEST)

    assert sorted(pof.LEFT_OUT) == sorted(not_run)
    for name, words in pof.LEFT_OUT.items():
        for text in (pof.HEADLINES["pool"], pof.HEADLINES["fallback"], pof.BROWSER_NO_VERDICT):
            assert words in text, f"{text!r} does not name the {name} suite"
        assert f"--suite {name}" in pof.BROWSER_NO_VERDICT


# -- the summary --------------------------------------------------------------------------


def _summary(tmp_path, decision=None, envelope=None, reports=()):
    if decision is not None:
        (tmp_path / "decision.json").write_text(json.dumps(decision.to_json()), encoding="utf-8")
    if envelope is not None:
        (tmp_path / "envelope.json").write_text(json.dumps(envelope), encoding="utf-8")
    for suite in reports:
        (tmp_path / "fallback").mkdir(exist_ok=True)
        (tmp_path / "fallback" / f"{suite}.xml").write_text(
            f'<testsuites><testsuite name="{suite}" tests="3" skipped="0" failures="0" errors="0"/></testsuites>',
            encoding="utf-8",
        )
    return pof.summary_lines(tmp_path)


def test_the_summary_opens_with_the_pool_when_the_pool_ran(tmp_path):
    decision, _, _ = drive(ScriptedPool([install()], [run_attempt(FAILED, tmp=tmp_path)]))
    lines, notes = _summary(tmp_path, decision, FAILED)

    assert lines[0] == "### Ran on the pool: every suite, the browser and real-Player suites included."
    assert any("tests/test_red.py::test_red" in line for line in lines)
    assert notes and notes[0].startswith("::error title=tests/test_red.py%3A%3Atest_red::")


def test_the_summary_opens_with_the_fallback_and_names_the_browser_and_real_player_suites_as_not_run(tmp_path):
    decision, _, _ = drive(ScriptedPool([CONSOLE_503], []))
    lines, _ = _summary(tmp_path, decision, reports=("governance", "curation", "contract"))

    assert lines[0] == "### The pool was unavailable; ran here, on GitHub's runner, without the browser and real-Player suites."
    assert any(line.startswith("| **not run** | the browser suite") for line in lines)
    assert f"| **not run** | the player suite: {pof.POOL_ONLY['player']}. |" in lines
    assert not any(line.startswith("| GitHub's runner | the player suite") for line in lines)
    for suite in ("governance", "curation", "contract"):
        assert f"| GitHub's runner | the {suite} suite: 3 collected, 0 failed, 0 errored, 0 skipped |" in lines
    assert any("HTTP 503" in line for line in lines)


def test_the_summary_opens_with_nothing_ran_when_nothing_did(tmp_path):
    decision, _, _ = drive(ScriptedPool([install(22, 401, "curl: (22) 401")], []))
    lines, notes = _summary(tmp_path, decision)

    assert lines[0] == "### Nothing ran."
    assert notes == ["::error::Nothing ran. curl: (22) 401"]


def test_the_summary_says_nothing_ran_when_no_decision_was_recorded(tmp_path):
    lines, notes = _summary(tmp_path)

    assert lines[0] == f"### {pof.NO_RECORD}"
    assert notes == [f"::error::{pof.NO_RECORD}"]


def test_each_mode_has_its_own_headline():
    assert len(set(pof.HEADLINES.values()) | {pof.NO_RECORD}) == 4


# -- the workflow --------------------------------------------------------------------------

FALLBACK_IF = "${{ !cancelled() && steps.pool.outputs.mode == 'fallback' }}"


def _steps(workflow: dict) -> list[dict]:
    return workflow["jobs"]["pool"]["steps"]


def _pytest_selection(run: str) -> tuple[str, list[str], dict[str, str]]:
    """A fallback step's suite name, the paths it selects from the repo root, and its report."""
    cwd = ""
    for line in run.splitlines():
        words = shlex.split(line.strip())
        if words[:1] == ["cd"]:
            cwd = words[1].rstrip("/") + "/"
        if "pytest" in words:
            after = words[words.index("pytest") + 1 :]
            paths = list(itertools.takewhile(lambda w: not w.startswith("-"), after))
            options = {after[i]: after[i + 1] for i in range(len(after) - 1) if after[i] in ("-o", "--junitxml")}
            name = options.get("-o", "").removeprefix("junit_suite_name=")
            return name, [f"{cwd}{p}" for p in paths], options
    raise AssertionError(f"a fallback step runs no pytest: {run!r}")


def check_the_fallback(workflow: dict, manifest: dict) -> None:
    """Raise unless the fallback runs exactly the planned suites, only on the decision, and the summary is there."""
    steps = _steps(workflow)
    pool = [s for s in steps if s.get("id") == "pool"]
    assert (
        len(pool) == 1 and "pool_or_fallback.py pool --out" in pool[0]["run"]
    ), "no pool step hands the run to pool_or_fallback.py"
    assert "if" not in pool[0], "the pool step carries a condition, so the decision may never be made"

    runs_tests = [s for s in steps if "pytest" in str(s.get("run", "")) or "testament run" in str(s.get("run", ""))]
    fallback = [s for s in runs_tests if s is not pool[0]]
    for step in fallback:
        assert step.get("if") == FALLBACK_IF, (
            f"`{step.get('name')}` runs tests on GitHub's runner under `if: {step.get('if')}`; "
            f"only `{FALLBACK_IF}` keeps it off a failed verdict and off a pool that answered"
        )
        text = str(step["run"])
        for word in ("browser", "playwright", "chrom"):
            assert word not in text.lower(), f"`{step.get('name')}` reaches the browser suite ({word}) on GitHub's runner"

    reports, _ = pof.fallback_plan(manifest)
    ran = {}
    for step in fallback:
        name, paths, options = _pytest_selection(step["run"])
        assert name in reports, f"`{step.get('name')}` writes a report for {name!r}, which is no suite the fallback runs"
        assert options.get("--junitxml") == f"$OUT/{reports[name]}", f"the {name} suite's report is not where the guard reads it"
        ran[name] = paths
    assert sorted(ran) == sorted(reports), f"the fallback runs {sorted(ran)}, and the manifest asks for {sorted(reports)}"
    for name, paths in ran.items():
        assert (
            paths == manifest["suites"][name]["default_selection"]
        ), f"the fallback's {name} suite selects {paths}, the pool's {manifest['suites'][name]['default_selection']}"

    summary = [s for s in steps if "pool_or_fallback.py summary --out" in str(s.get("run", ""))]
    assert summary, "no step writes the summary, so a fallback run would not say the browser suite did not run"
    assert summary[0].get("if") == "always()", "the summary step does not run on every path"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_workflow_falls_back_only_on_the_decision():
    check_the_fallback(_workflow(), MANIFEST)


def _fallback_steps(workflow):
    return [s for s in _steps(workflow) if s.get("if") == FALLBACK_IF]


@pytest.mark.parametrize(
    "condition",
    [
        "${{ failure() }}",
        "${{ always() }}",
        "${{ !cancelled() && steps.pool.outcome == 'failure' }}",
        "${{ !cancelled() && steps.pool.outputs.mode != 'pool' }}",
        "${{ !cancelled() && (steps.pool.outputs.mode == 'fallback' || failure()) }}",
    ],
)
def test_a_fallback_reachable_from_a_failed_verdict_is_refused(condition):
    workflow = _workflow()
    _fallback_steps(workflow)[0]["if"] = condition
    with pytest.raises(AssertionError, match="only `"):
        check_the_fallback(workflow, MANIFEST)


def test_a_fallback_that_runs_the_browser_suite_is_refused():
    workflow = _workflow()
    step = _fallback_steps(workflow)[1]
    step["run"] = step["run"].replace("tests/unit", "tests/browser tests/unit")
    with pytest.raises(AssertionError, match="browser"):
        check_the_fallback(workflow, MANIFEST)


def test_a_fallback_with_the_browser_marker_is_refused():
    workflow = _workflow()
    step = _fallback_steps(workflow)[1]
    step["run"] = step["run"].replace(" -q ", " -q -m browser ")
    with pytest.raises(AssertionError, match="browser"):
        check_the_fallback(workflow, MANIFEST)


def test_a_fallback_missing_a_suite_is_refused():
    workflow = _workflow()
    _steps(workflow).remove(_fallback_steps(workflow)[2])
    with pytest.raises(AssertionError, match="the manifest asks for"):
        check_the_fallback(workflow, MANIFEST)


def test_a_fallback_selecting_less_than_the_pool_is_refused():
    workflow = _workflow()
    step = _fallback_steps(workflow)[1]
    step["run"] = step["run"].replace(" tests/eval", "")
    with pytest.raises(AssertionError, match="selects"):
        check_the_fallback(workflow, MANIFEST)


def test_a_workflow_without_the_summary_step_is_refused():
    workflow = _workflow()
    workflow["jobs"]["pool"]["steps"] = [s for s in _steps(workflow) if "summary --out" not in str(s.get("run", ""))]
    with pytest.raises(AssertionError, match="no step writes the summary"):
        check_the_fallback(workflow, MANIFEST)


def test_a_conditional_pool_step_is_refused():
    workflow = _workflow()
    next(s for s in _steps(workflow) if s.get("id") == "pool")["if"] = "github.event_name == 'never'"
    with pytest.raises(AssertionError, match="carries a condition"):
        check_the_fallback(workflow, MANIFEST)


def test_a_manifest_suite_the_fallback_forgets_is_refused():
    manifest = {**MANIFEST, "suites": {**MANIFEST["suites"], "system": {"default_selection": ["arrt/tests/system"]}}}
    with pytest.raises(AssertionError, match="the manifest asks for"):
        check_the_fallback(_workflow(), manifest)


#: The fallback step the real-Player suite would need, by the project's command: what the
#: owner's ruling of 2026-11-20 keeps off GitHub's runner.
_A_PLAYER_STEP = {
    "name": "Fallback: the real-Player suite, here",
    "if": FALLBACK_IF,
    "timeout-minutes": 10,
    "run": 'OUT="$RUNNER_TEMP/$OUT_DIR"\ncd arrt\nuv run --frozen pytest tests/system/test_a_real_player.py -m player_e2e '
    '-n 0 -q -o junit_suite_name=player --junitxml "$OUT/fallback/player.xml"\n',
}


def test_a_fallback_that_runs_the_real_player_suite_on_githubs_runner_is_refused():
    workflow = _workflow()
    steps = _steps(workflow)
    steps.insert(steps.index(_fallback_steps(workflow)[-1]) + 1, _A_PLAYER_STEP)
    with pytest.raises(AssertionError, match="writes a report for 'player', which is no suite the fallback runs"):
        check_the_fallback(workflow, MANIFEST)


def test_without_the_ruling_the_manifests_real_player_suite_would_be_owed_a_fallback_step(monkeypatch):
    """The other side of the refusal above: what `POOL_ONLY` holds back is a suite the workflow would otherwise owe."""
    monkeypatch.setattr(pof, "POOL_ONLY", {})
    with pytest.raises(AssertionError, match=r"the manifest asks for \['contract', 'curation', 'governance', 'player'\]"):
        check_the_fallback(_workflow(), MANIFEST)


# -- time: no attempt outlives the step (finding 1 of the wave-2 boundary review) ------------


class HungPool:
    """A pool that accepts the run and holds it for forty minutes, as long as nothing stops it.

    Handed a limit (the driver's deadline), it is stopped there, as `RealPool` stops the
    client; handed none, it holds the full forty minutes, which spends a 45-minute job.
    """

    HOLD_S = 40 * 60

    def __init__(self, clock, installs=None):
        self.clock, self.installs, self.limits = clock, list(installs or [install()]), []

    def install(self):
        return self.installs.pop(0) if len(self.installs) > 1 else self.installs[0]

    def run(self, *limit):
        self.limits.append(limit[0] if limit else None)
        held = min(self.HOLD_S, limit[0]) if limit else self.HOLD_S
        self.clock.now += held
        if limit and held < self.HOLD_S:
            return pof.Attempt("run", exit_code=-15, killed="deadline", accepted=True, detail="stopped at the deadline")
        return pof.Attempt("run", exit_code=0, has_envelope=True, verdict="passed", verdict_reason="passed")


def test_a_run_the_pool_accepts_and_holds_is_stopped_at_the_deadline_and_falls_back():
    clock = Clock()
    decision, _, _ = drive(HungPool(clock), clock)

    assert clock.now <= pof.DEADLINE_S, f"the attempt ran {clock.now:.0f} s, past the step's {pof.DEADLINE_S} s"
    assert decision.mode == "fallback", decision.why
    assert decision.attempts[-1].ended_s == pof.DEADLINE_S
    assert "no verdict within the step's 20 minutes" in decision.why
    assert pof.fallback_is_earned(decision.attempts)


def test_a_run_after_retries_gets_only_what_is_left_of_the_deadline():
    clock = Clock()
    pool = HungPool(clock, installs=[CONSOLE_503] * 3 + [install()])
    decision, slept, _ = drive(pool, clock)

    assert slept == [15, 30, 60]
    assert pool.limits == [pof.DEADLINE_S - 105]
    assert (decision.mode, clock.now) == ("fallback", pof.DEADLINE_S)


def test_the_deadline_leaves_the_job_time_for_the_fallback_and_the_summary():
    """The sums that keep the `!cancelled()` and `always()` steps alive: every step has a ceiling, and they fit the job's."""
    job = _workflow()["jobs"]["pool"]
    ceilings = {s.get("name") or s.get("uses"): s.get("timeout-minutes") for s in job["steps"]}
    unbounded = [name for name, minutes in ceilings.items() if not isinstance(minutes, int)]
    assert not unbounded, f"steps with no timeout-minutes, so one can spend the job: {unbounded}"
    assert sum(ceilings.values()) <= job["timeout-minutes"], (
        f"the steps' ceilings add to {sum(ceilings.values())} minutes, past the job's {job['timeout-minutes']}: "
        "a pool step that runs to its ceiling would leave the fallback and the summary no time"
    )
    pool_step = next(s for s in job["steps"] if s.get("id") == "pool")
    assert pool_step["timeout-minutes"] * 60 >= pof.DEADLINE_S + 120, (
        f"the pool step's ceiling ({pool_step['timeout-minutes']} min) does not leave the driver's deadline "
        f"({pof.DEADLINE_S} s) two minutes to stop the client and write its record"
    )


FAKE_CLIENT = """
import json, sys, time
mode = sys.argv[1]
if mode != "never-accepts":
    print("request 0123abcd accepted for arrt at tree 7ea4377c29d8", file=sys.stderr, flush=True)
    print("collected 7 items", file=sys.stderr, flush=True)
if mode == "fails-then-hangs":
    print("FAILED   tests/test_red.py::test_red  [runner-a]", file=sys.stderr, flush=True)
if mode == "passes":
    print(json.dumps({"exit_code": 0, "verdict": "passed", "verdict_reason": "passed"}))
    sys.exit(0)
time.sleep(60)
"""


def _real_run(tmp_path, mode, limit_s=3.0, accept_s=1.0):
    """`RealPool.run` against a stand-in client that prints testament's progress lines (as 0.58.0 prints them)."""
    client = tmp_path / "client.py"
    client.write_text(FAKE_CLIENT, encoding="utf-8")
    echoed = []
    argv = [sys.executable, str(client), mode]
    pool = pof.RealPool(tmp_path, argv, {"PATH": ""}, accept_s=accept_s, poll_s=0.05, echo=echoed.append)
    return pool.run(limit_s), echoed


#: `testament run`'s progress exactly as it reached GitHub's log and this machine's, copied from
#: observed runs of 0.58.0: a run of one suite prints each line bare, and a run of several
#: prefixes each with the suite's name in brackets. The first version of the driver matched
#: only the bare form, so on a pull request (every suite) it saw no acceptance, stopped a
#: healthy run after `ACCEPT_S`, and fell back every time.
OBSERVED_PROGRESS = {
    "one suite": (
        "request d7eb96f74cb846cd83f04001c03237ea accepted for arrt at tree 8c4fab253715",
        "collected 199 items",
        "FAILED   tests/test_red.py::test_red  [runner-a]",
    ),
    "every suite": (
        "[browser] request cac2b18e7eea40ef99680aef84181f7f accepted for arrt at tree 8c4fab253715",
        "[curation] collected 6580 items",
        "[browser] FAILED   arrt/tests/browser/test_navigation.py::test_red[chromium]  [runner-a]",
    ),
}


@pytest.mark.parametrize("shape", sorted(OBSERVED_PROGRESS))
def test_progress_is_read_in_both_shapes_the_client_prints(shape):
    accepted, collected, failed = OBSERVED_PROGRESS[shape]
    progress = pof.Progress(echo=lambda line: None)

    progress.read(iter(line + "\n" for line in (accepted, collected, failed)))

    assert progress.accepted.is_set(), f"an accepted run reads as never accepted: {accepted!r}"
    assert progress.requests == [accepted.split("request ")[1].split()[0]]
    assert progress.collected == int(collected.split("collected ")[1].split()[0])
    assert progress.failures == [failed.split("FAILED")[1].split()[0]]


#: The first lines `testament run --json=summary --junit-xml … --no-fallback` printed with the
#: five suites of Chunk 29's manifest, copied from the observed run of 2026-11-19 (testament
#: 0.58.0, requests 96f5041e…, e861507f…, b08c7d62…, 4deff0eb…, 1a644963…), two of its nine
#: FAILED lines kept, the runner's name replaced. Before the real-Player suite, a pull
#: request's run printed four `accepted` lines; it prints five.
OBSERVED_FIVE_SUITES = """\
[browser] request b08c7d620c414c659e3bde6d33b6dc18 accepted for arrt at tree 1cf5b8ec5e36
[player] request 4deff0ebac4348fcb9ebe17fe460e9c5 accepted for arrt at tree 1cf5b8ec5e36
[governance] request 96f5041e28f4441b880ae59922e241d9 accepted for arrt at tree 1cf5b8ec5e36
[curation] request e861507f10c3443b84eb8122fb40fb4f accepted for arrt at tree 1cf5b8ec5e36
[contract] request 1a64496325204139a6cf35e1eaecf9b3 accepted for arrt at tree 1cf5b8ec5e36
[governance] collected 841 items
[contract] collected 474 items
[player] collected 1 items
[governance] FAILED   tests/test_ci_fallback.py::test_the_workflow_falls_back_only_on_the_decision  [runner-a]
[governance] FAILED   tests/test_assert_tests_ran.py::test_a_pool_run_with_every_suite_passes  [runner-a]
[curation] collected 6580 items
[curation] … 1000 results
[curation] … 2000 results
[browser] collected 1582 items
[curation] … 3000 results
[browser] … 1000 results
"""
#: `testament run --json=summary --suite player` alone, observed 2026-11-19 (request 841de9fe…): bare lines.
OBSERVED_PLAYER_ALONE = """\
request 841de9fe17424ab0b29c10c4477f0fb5 accepted for arrt at tree 1cf5b8ec5e36
collected 1 items
"""


def test_a_run_of_the_five_suites_is_read_as_accepted_with_every_request_and_count():
    progress = pof.Progress(echo=lambda line: None)

    progress.read(iter(OBSERVED_FIVE_SUITES.splitlines(keepends=True)))

    assert progress.accepted.is_set()
    assert progress.requests == [
        "b08c7d620c414c659e3bde6d33b6dc18",
        "4deff0ebac4348fcb9ebe17fe460e9c5",
        "96f5041e28f4441b880ae59922e241d9",
        "e861507f10c3443b84eb8122fb40fb4f",
        "1a64496325204139a6cf35e1eaecf9b3",
    ]
    assert progress.collected == 841 + 474 + 1 + 6580 + 1582
    assert progress.failures == [
        "tests/test_ci_fallback.py::test_the_workflow_falls_back_only_on_the_decision",
        "tests/test_assert_tests_ran.py::test_a_pool_run_with_every_suite_passes",
    ]


def test_the_real_player_suite_run_alone_is_read_as_accepted():
    progress = pof.Progress(echo=lambda line: None)

    progress.read(iter(OBSERVED_PLAYER_ALONE.splitlines(keepends=True)))

    assert (progress.accepted.is_set(), progress.requests, progress.collected) == (
        True,
        ["841de9fe17424ab0b29c10c4477f0fb5"],
        1,
    )


#: The merged report the same five-suite run wrote (`--junit-xml`), its `<testsuite>` elements
#: as observed with their test cases, timestamps and host left out.
OBSERVED_ALL_XML = (
    '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests" time="429.990">'
    '<testsuite name="governance" errors="0" failures="9" skipped="0" tests="841" time="14.612" />'
    '<testsuite name="curation" errors="0" failures="0" skipped="2" tests="6580" time="278.691" />'
    '<testsuite name="browser" errors="0" failures="0" skipped="0" tests="1582" time="428.796" />'
    '<testsuite name="player" errors="0" failures="0" skipped="0" tests="1" time="70.697" />'
    '<testsuite name="contract" errors="0" failures="0" skipped="0" tests="474" time="9.770" />'
    "</testsuites>"
)


def test_the_pool_summary_names_each_suite_the_merged_report_holds(tmp_path):
    decision, _, _ = drive(ScriptedPool([install()], [run_attempt(PASSED, tmp=tmp_path)]))
    (tmp_path / "all.xml").write_text(OBSERVED_ALL_XML, encoding="utf-8")
    lines, _ = _summary(tmp_path, decision, PASSED)

    assert "- the player suite, on the pool: 1 collected, 0 failed, 0 errored, 0 skipped" in lines
    assert "- the governance suite, on the pool: 841 collected, 9 failed, 0 errored, 0 skipped" in lines
    assert [
        line.split(" suite,")[0].removeprefix("- the ") for line in lines if line.endswith("skipped") and "on the pool" in line
    ] == [
        "governance",
        "curation",
        "browser",
        "player",
        "contract",
    ]


def test_the_pool_summary_says_so_when_there_is_no_merged_report(tmp_path):
    decision, _, _ = drive(ScriptedPool([install()], [run_attempt(PASSED, tmp=tmp_path)]))
    lines, _ = _summary(tmp_path, decision, PASSED)

    assert any(line.startswith("**No merged report**") for line in lines)


def test_the_real_pool_stops_a_run_the_pool_never_accepts_and_calls_it_could_not_answer(tmp_path):
    attempt, _ = _real_run(tmp_path, "never-accepts")

    assert (attempt.killed, attempt.accepted, pof.classify(attempt)) == ("not_accepted", False, "retry")
    assert "did not accept the run within 1 s" in attempt.detail


def test_the_real_pool_stops_an_accepted_run_at_its_limit(tmp_path):
    attempt, echoed = _real_run(tmp_path, "hangs")

    assert (attempt.killed, attempt.accepted, pof.classify(attempt)) == ("deadline", True, "timeout")
    assert "request 0123abcd" in attempt.detail and "collected 7 tests" in attempt.detail
    assert any("accepted" in line for line in echoed), "the client's progress no longer reaches the step's log"


def test_a_run_that_reported_a_red_before_it_was_stopped_never_falls_back(tmp_path):
    attempt, _ = _real_run(tmp_path, "fails-then-hangs")
    decision, _, _ = drive(ScriptedPool([install()], [attempt]))

    assert attempt.failures_seen == ["tests/test_red.py::test_red"]
    assert (decision.mode, decision.exit_code) == ("none", 1)
    assert "tests/test_red.py::test_red" in decision.why and "nothing falls back" in decision.why


def test_the_real_pool_lets_a_run_that_finishes_be_read_from_its_envelope(tmp_path):
    attempt, _ = _real_run(tmp_path, "passes")

    assert (attempt.killed, attempt.accepted, pof.classify(attempt)) == (None, True, "passed")


class StepKilledMidway(BaseException):
    """What GitHub's step timeout is to the driver: it stops, and no line after the kill runs."""


def test_a_pool_step_killed_midway_leaves_a_record_that_names_the_pool_not_lint(tmp_path, monkeypatch):
    class KilledPool:
        def __init__(self, out, argv):
            pass

        def install(self):
            return install()

        def run(self, limit_s):
            raise StepKilledMidway

    monkeypatch.chdir(REPO)
    monkeypatch.setattr(pof, "RealPool", KilledPool)
    with pytest.raises(StepKilledMidway):
        pof.main(["pool", "--out", str(tmp_path), "--", "testament", "run"])
    lines, notes = pof.summary_lines(tmp_path)

    assert lines[0] == "### Nothing ran.", lines[0]
    assert lines[2] == pof.STOPPED
    assert any(line.startswith("- install: curl exit 0") for line in lines), "the attempt before the kill is not named"
    assert notes == [f"::error::Nothing ran. {pof.STOPPED}"]


def test_the_record_is_checkpointed_after_every_attempt_and_every_wait(tmp_path):
    seen = []
    pool = ScriptedPool([CONSOLE_503, install()], [run_attempt(PASSED, tmp=tmp_path)])
    drive(pool, checkpoint=lambda attempts: seen.append([(a.step, a.waited_s) for a in attempts]))

    assert seen == [
        [("install", 0.0)],
        [("install", 15)],
        [("install", 15), ("install", 0.0)],
        [("install", 15), ("install", 0.0), ("run", 0.0)],
    ]


# -- envelopes of a shape the driver does not expect (finding 2) -----------------------------


@pytest.mark.parametrize(
    "envelope",
    [
        {"exit_code": 2, "verdict": "failed", "error": "upgrade_required"},
        {"exit_code": 75, "verdict": "unavailable", "error": ["coordinator_unreachable"]},
        {"exit_code": 75, "verdict": "unavailable", "error": {"retryable": "false"}},
        {"exit_code": 0, "verdict": "passed", "report": ["a", "b"]},
        {"exit_code": 0, "verdict": "passed", "report": {"counts": [1]}},
        {"exit_code": 1, "verdict": "failed", "report": {"items": "none"}},
        {"exit_code": 1, "verdict": "failed", "report": {"items": [{"id": 3}]}},
        {"exit_code": 0, "verdict": "passed", "report": {"missing": "tests/a.py::b"}},
        {"exit_code": 0, "verdict": "passed", "setup": "machine_not_set_up"},
        {"exit_code": 0, "verdict": "passed", "fallback": "coordinator_unreachable"},
        {"exit_code": 0, "verdict": 1},
        ["not", "an", "object"],
    ],
    ids=[
        "error-str",
        "error-list",
        "retryable-str",
        "report-list",
        "counts-list",
        "items-str",
        "item-id-int",
        "missing-str",
        "setup-str",
        "fallback-str",
        "verdict-int",
        "envelope-list",
    ],
)
def test_an_envelope_of_a_shape_it_cannot_read_is_named_as_such_never_a_crash(envelope, tmp_path):
    path = tmp_path / "envelope.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    code = envelope["exit_code"] if isinstance(envelope, dict) else 2
    decision, _, _ = drive(ScriptedPool([install()], [pof.attempt_from_envelope(path, code)]))

    assert (decision.mode, decision.exit_code) == ("none", 1)
    assert decision.why.startswith("the pool could not give a verdict I can read"), decision.why


@pytest.mark.parametrize("envelope", [{"exit_code": 1, "verdict": "failed", "error": "upgrade_required"}, {"report": []}])
def test_the_summary_names_an_envelope_it_cannot_read(envelope, tmp_path):
    decision = pof.Decision("pool", "w", [install()], verdict="failed")
    lines, _ = _summary(tmp_path, decision, envelope)

    assert any(line.startswith("the pool could not give a verdict I can read") for line in lines), lines


# -- a fallback record must have waited out the budget (finding 3) ---------------------------


def test_one_retryable_blip_does_not_earn_the_fallback(tmp_path):
    installed = dataclasses.replace(install(), started_s=0, ended_s=1)
    blip = dataclasses.replace(run_attempt(UNAVAILABLE, tmp=tmp_path), started_s=1, ended_s=4)

    assert not pof.fallback_is_earned([installed, blip])
    assert not pof.fallback_is_earned([install(), run_attempt(UNAVAILABLE, tmp=tmp_path)]), "a record with no times"


def test_a_record_whose_times_do_not_account_for_the_budget_does_not_earn_the_fallback(tmp_path):
    decision, _, _ = drive(ScriptedPool([install()], [run_attempt(UNAVAILABLE, tmp=tmp_path)]))
    attempts = decision.attempts
    assert pof.fallback_is_earned(attempts)

    skipped_waits = [dataclasses.replace(a, waited_s=0.0) for a in attempts]
    untimed = [dataclasses.replace(a, started_s=None, ended_s=None) for a in attempts]
    timeout_early = [attempts[0], dataclasses.replace(attempts[1], killed="deadline", ended_s=30, waited_s=0.0)]
    for name, forged in {"skipped-waits": skipped_waits, "untimed": untimed, "timeout-early": timeout_early}.items():
        assert not pof.fallback_is_earned(forged), name
    # One attempt that itself lasted the budget, then the fallback, is consistent, and earned.
    assert pof.fallback_is_earned(attempts[:1] + [dataclasses.replace(attempts[1], ended_s=pof.BUDGET_S, waited_s=0.0)])


# -- the second job: a mark that is not prose (finding 4) -------------------------------------


def _browser_job(workflow):
    jobs = [job for job in workflow["jobs"].values() if job.get("name") == pof.BROWSER_JOB]
    assert len(jobs) == 1, f"no single job named {pof.BROWSER_JOB!r} in tests.yml"
    return jobs[0]


def _run_browser_job(job, mode):
    """The job's own step, run as GitHub would run it, with the first job's mode in its environment."""
    step = next(s for s in job["steps"] if "browser-verdict" in str(s.get("run", "")))
    assert step.get("env", {}).get("POOL_MODE") == "${{ needs.pool.outputs.mode }}", "the job does not read the mode"
    env = {**os.environ, "POOL_MODE": mode}
    return subprocess.run(["bash", "-eo", "pipefail", "-c", step["run"]], cwd=REPO, env=env, capture_output=True, text=True)


def test_the_browser_job_is_green_when_the_pool_gave_the_verdict_and_red_after_a_fallback():
    workflow = _workflow()
    job = _browser_job(workflow)
    assert workflow["jobs"]["pool"]["outputs"]["mode"] == "${{ steps.pool.outputs.mode }}"

    passed = _run_browser_job(job, "pool")
    fell_back = _run_browser_job(job, "fallback")
    no_mode = _run_browser_job(job, "")

    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert fell_back.returncode == 1 and "no verdict for this tree" in fell_back.stdout, fell_back.stdout
    assert "testament run --json=summary --suite browser --suite player" in fell_back.stdout
    assert "The browser and real-Player suites have no verdict" in fell_back.stdout
    assert "The browser and real-Player suites ran on the pool" in passed.stdout
    assert no_mode.returncode == 1 and "no mode" in no_mode.stdout


def check_the_browser_job_condition(workflow: dict) -> None:
    """Raise unless the browser job is skipped when the first job failed or was cancelled.

    With no `if`, or `success()`, a job whose `needs` failed or was cancelled is skipped;
    the job's own step is green only on `mode=pool`, which a failed first job can carry
    (a `failed` verdict), so the condition is what keeps that case from a green mark.
    """
    job = _browser_job(workflow)
    assert job.get("needs") in ("pool", ["pool"]), f"the browser job needs {job.get('needs')!r}, not the first job"
    assert job.get("if") in (None, "success()", "${{ success() }}"), (
        f"the browser job runs under `if: {job.get('if')}`, so it can go green after the first job failed or " "was cancelled"
    )


def test_the_browser_job_is_skipped_never_green_when_the_first_job_failed_or_was_cancelled():
    check_the_browser_job_condition(_workflow())


@pytest.mark.parametrize("condition", ["always()", "${{ !cancelled() }}", "failure() || success()"])
def test_a_browser_job_that_runs_after_a_failed_first_job_is_refused(condition):
    workflow = _workflow()
    _browser_job(workflow)["if"] = condition
    with pytest.raises(AssertionError, match="runs under"):
        check_the_browser_job_condition(workflow)


def test_the_browser_job_is_not_the_required_check_and_reaches_nothing():
    workflow = _workflow()
    job = _browser_job(workflow)

    assert workflow["jobs"]["pool"]["name"] != pof.BROWSER_JOB
    assert job.get("permissions") == {"contents": "read"}
    assert "secrets." not in json.dumps(job), "the browser job reads a secret it has no use for"
    assert isinstance(job.get("timeout-minutes"), int) and job["timeout-minutes"] <= 5


# -- the type gate's environments on the fallback (finding 5) --------------------------------


def check_the_fallback_provisions_the_type_gate(workflow: dict) -> None:
    """Raise unless the fallback's governance step syncs every project the type gate runs mypy in, before pytest."""
    step = next(s for s in _fallback_steps(workflow) if "junit_suite_name=governance" in s["run"])
    lines = [line.strip() for line in step["run"].splitlines() if line.strip()]
    first_pytest = next(i for i, line in enumerate(lines) if "pytest" in line)
    for project in ("arrt", "contract"):
        synced = [i for i, line in enumerate(lines) if line.startswith("uv sync --frozen") and f"--project {project}" in line]
        assert synced and synced[0] < first_pytest, (
            f"the fallback's governance step runs pytest without {project}'s environment, so the type gate's mypy "
            "cannot be spawned there"
        )


def test_the_fallback_provisions_the_environments_the_type_gate_runs_mypy_in():
    check_the_fallback_provisions_the_type_gate(_workflow())


@pytest.mark.parametrize("project", ["arrt", "contract"])
def test_a_fallback_that_does_not_provision_a_type_checked_project_is_refused(project):
    workflow = _workflow()
    step = next(s for s in _fallback_steps(workflow) if "junit_suite_name=governance" in s["run"])
    step["run"] = "\n".join(line for line in step["run"].splitlines() if f"--project {project}" not in line)
    with pytest.raises(AssertionError, match=f"without {project}'s environment"):
        check_the_fallback_provisions_the_type_gate(workflow)
