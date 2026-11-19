"""CI's fallback: what runs when testament's pool cannot answer, and that nothing else reaches it.

Ruling 4 of 2026-11-19 makes CI required to merge once the pool has a fallback, and
the 2026-11-18 ruling keeps the suites off GitHub's runners. The two meet in
`.github/scripts/pool_or_fallback.py`, which `tests.yml` calls: it retries a pool that
cannot answer for ten minutes, then sends the job to the fallback steps, which run
every suite needing no labelled runner here, without the browser suite.

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

import importlib.util
import itertools
import json
import pathlib
import shlex
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

    def run(self):
        self.run_calls += 1
        return self.runs[min(self.run_calls, len(self.runs)) - 1]


def drive(pool):
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    said = []
    decision = pof.drive(pool, MANIFEST, clock=lambda: now[0], sleep=sleep, say=said.append)
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
    assert list(decision.not_run) == ["browser"]
    assert pof.fallback_is_earned(decision.attempts)
    assert "without the browser suite" in said[-1]


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
    assert pof.fallback_is_earned([install(), unavailable, unavailable])
    assert pof.fallback_is_earned([CONSOLE_503, CONSOLE_503])
    assert not pof.fallback_is_earned([install(), run_attempt(FAILED, tmp=tmp_path), unavailable])
    assert not pof.fallback_is_earned([install(), run_attempt(FAILED, tmp=tmp_path)])
    assert not pof.fallback_is_earned([install(), run_attempt(PASSED, tmp=tmp_path)])
    assert not pof.fallback_is_earned([install(22, 401, "refused"), unavailable])
    assert not pof.fallback_is_earned([])


def test_the_fallback_plan_is_the_manifest_less_the_suites_that_need_a_labelled_runner():
    reports, not_run = pof.fallback_plan(MANIFEST)

    assert set(reports) | set(not_run) == set(MANIFEST["suites"])
    assert set(not_run) == {name for name, suite in MANIFEST["suites"].items() if suite.get("requires")} == {"browser"}


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

    assert lines[0] == "### Ran on the pool: every suite, the browser suite included."
    assert any("tests/test_red.py::test_red" in line for line in lines)
    assert notes and notes[0].startswith("::error title=tests/test_red.py%3A%3Atest_red::")


def test_the_summary_opens_with_the_fallback_and_names_the_browser_suite_as_not_run(tmp_path):
    decision, _, _ = drive(ScriptedPool([CONSOLE_503], []))
    lines, _ = _summary(tmp_path, decision, reports=("governance", "curation", "contract"))

    assert lines[0] == "### The pool was unavailable; ran here, on GitHub's runner, without the browser suite."
    assert any(line.startswith("| **not run** | the browser suite") for line in lines)
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
