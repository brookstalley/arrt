"""No scheduled run of any workflow reaches a job that holds a paid model key.

The owner's ruling of 2026-11-20 (`.prawduct/owner-rulings.md`, "CI is kept small,
tests run on the pool first, and CI makes no paid call"): a probe that costs money
is run when a person asks for it, never by a clock. `api-drift.yml` ran the
OpenRouter probe on a monthly cron after that ruling (wave 2b, Chunk 66); it now
runs only on a dispatch that ticks `include_paid`.

**Read from the workflow files themselves**, every one under `.github/workflows/`,
so a cron added to any of them, or a job's `if` loosened, fails here by the job's
name and the schedule that reaches it. A job is reached by a schedule when its
`if` can be true for that cron's event and the jobs it needs can run too. The `if`
is evaluated, not matched as text: each status function (`failure()`,
`always()`, …) and each needed job's result is tried both ways, so an `if` that
could pass on some outcome counts as passing. A name in an `if` this file does not
know fails by name rather than being guessed.

What it cannot see: a key reached some way other than a `secrets.` expression in
the job (a key fetched by a script from elsewhere), and a schedule GitHub applies
that the file does not state. Neither exists here today.
"""

import itertools
import json
import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"

#: A secret that buys model calls: a key to a model provider. `TESTAMENT_KEY`
#: (the pool's) and `github.token` are not.
PAID_KEY = re.compile(r"\$\{\{\s*secrets\.(\w*(?:OPENROUTER|ANTHROPIC|OPENAI)\w*)\s*\}\}")

#: The functions a job's `if` may call whose value depends on how other jobs ended.
STATUS_FUNCTIONS = ("success", "failure", "always", "cancelled")
#: The results a needed job may end with.
RESULTS = ("success", "failure", "skipped", "cancelled")

TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>==|!=|&&|\|\||!|\(|\))|(?P<call>[A-Za-z_][\w-]*)\(\)|(?P<name>[A-Za-z_][\w.\-]*))"
)


class UnknownName(Exception):
    """A name in an `if` this check cannot give a value."""


def _on(workflow: dict) -> dict:
    """The workflow's triggers; PyYAML reads the bare key `on` as the boolean True."""
    triggers = workflow.get("on", workflow.get(True)) or {}
    return {trigger: None for trigger in triggers} if isinstance(triggers, list | str) else triggers


def crons(workflow: dict) -> list[str]:
    return [entry["cron"] for entry in (_on(workflow).get("schedule") or [])]


def paid_keys(job: dict) -> set[str]:
    return set(PAID_KEY.findall(json.dumps(job)))


def _python(expression: str) -> tuple[str, set[str]]:
    """The `if` as a Python expression over `_v` (a name) and `_f` (a status function), and the names it reads."""
    text = expression.strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2]
    out, names, at = [], set(), 0
    while at < len(text.rstrip()):
        match = TOKEN.match(text, at)
        if match is None or match.end() == at:
            raise UnknownName(f"cannot read {text[at:]!r}")
        at = match.end()
        if match["str"] is not None:
            out.append(repr(match["str"][1:-1].replace("''", "'")))
        elif match["op"] is not None:
            out.append({"&&": " and ", "||": " or ", "!": " not "}.get(match["op"], f" {match['op']} "))
        elif match["call"] is not None:
            if match["call"] not in STATUS_FUNCTIONS:
                raise UnknownName(f"the function {match['call']}()")
            out.append(f"_f[{match['call']!r}]")
        else:
            name = match["name"]
            literal = {"true": "True", "false": "False", "null": "None"}.get(name)
            if literal is None:
                names.add(name)
            out.append(literal or f"_v[{name!r}]")
    return "".join(out), names


def can_pass(expression: str | None, event: dict[str, object]) -> bool:
    """Whether a job's `if` can be true for `event`, trying each status function and each needed result both ways."""
    if expression is None:
        return True
    code, names = _python(str(expression))
    open_names = sorted(name for name in names if name.startswith("needs.") and name.endswith(".result"))
    for name in names - set(open_names):
        if name not in event and not name.startswith("inputs."):
            raise UnknownName(name)
    for statuses in itertools.product((True, False), repeat=len(STATUS_FUNCTIONS)):
        for results in itertools.product(RESULTS, repeat=len(open_names)):
            values = {name: event.get(name) for name in names} | dict(zip(open_names, results, strict=True))
            if eval(code, {"__builtins__": {}}, {"_v": values, "_f": dict(zip(STATUS_FUNCTIONS, statuses, strict=True))}):
                return True
    return False


def reached(workflow: dict, job_id: str, event: dict[str, object]) -> bool:
    """Whether `job_id` can run for `event`: its `if` can pass, and the jobs it needs can run, or its `if` runs anyway."""
    job = workflow["jobs"][job_id]
    needs = job.get("needs") or []
    needs = [needs] if isinstance(needs, str) else needs
    anyway = "always()" in str(job.get("if", ""))
    if needs and not anyway and not all(reached(workflow, need, event) for need in needs):
        return False
    return can_pass(job.get("if"), event)


def scheduled_event(cron: str) -> dict[str, object]:
    return {"github.event_name": "schedule", "github.event.schedule": cron}


def dispatched(**inputs: object) -> dict[str, object]:
    return {"github.event_name": "workflow_dispatch", "github.event.schedule": None} | {
        f"inputs.{name}": value for name, value in inputs.items()
    }


def schedules_reaching_a_paid_key(workflow: dict) -> list[str]:
    """Each job holding a paid model key that a schedule of this workflow can start, with the cron that starts it."""
    found = []
    for cron in crons(workflow):
        for job_id, job in workflow.get("jobs", {}).items():
            keys = paid_keys(job)
            if keys and reached(workflow, job_id, scheduled_event(cron)):
                found.append(f"{job_id} (holds {', '.join(sorted(keys))}) runs on the schedule {cron!r}")
    return found


def _workflows() -> list[pathlib.Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


@pytest.mark.parametrize("path", _workflows(), ids=lambda path: path.name)
def test_no_schedule_reaches_a_job_that_holds_a_paid_model_key(path):
    found = schedules_reaching_a_paid_key(yaml.safe_load(path.read_text(encoding="utf-8")))

    assert found == [], (
        f"{path.name}: a scheduled run reaches a job that holds a paid model key, against the owner's ruling of "
        f"2026-11-20 that CI makes no paid call; run it only when a person dispatches it: {found}"
    )


def test_the_workflows_are_read_and_the_drift_workflow_is_among_them():
    """Anchors, so a glob that found nothing, or a drift workflow that lost its schedule, cannot pass vacuously."""
    names = {path.name for path in _workflows()}
    assert {"api-drift.yml", "tests.yml"} <= names
    drift = yaml.safe_load((WORKFLOWS / "api-drift.yml").read_text(encoding="utf-8"))
    assert crons(drift), "the drift workflow has no schedule, so this check reads nothing there"


def test_the_paid_probe_runs_only_on_a_dispatch_that_asks_for_it():
    """The other half: the paid job is still there, a person can still run it, and only by ticking `include_paid`."""
    drift = yaml.safe_load((WORKFLOWS / "api-drift.yml").read_text(encoding="utf-8"))
    paid = [job_id for job_id, job in drift["jobs"].items() if paid_keys(job)]

    assert paid == ["openrouter"], "the paid probe's job is gone or renamed, so the check above passes over nothing"
    assert reached(drift, "openrouter", dispatched(include_paid=True))
    assert not reached(drift, "openrouter", dispatched(include_paid=False))
    assert reached(drift, "museum", dispatched(include_paid=False)), "the free probes run on any dispatch"


# -- the check itself can fail ---------------------------------------------------------------------

KEYED_STEPS = [{"run": "uv run pytest -m live_api", "env": {"OPENROUTER_API_KEY": "${{ secrets.OPENROUTER_API_KEY }}"}}]


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        # The shape `api-drift.yml` had before Chunk 66: a monthly cron that exists to start the paid job.
        (
            {
                "on": {"schedule": [{"cron": "17 6 * * 1"}, {"cron": "43 6 1 * *"}], "workflow_dispatch": None},
                "jobs": {
                    "openrouter": {
                        "if": (
                            "github.event.schedule == '43 6 1 * *' ||\n"
                            "(github.event_name == 'workflow_dispatch' && inputs.include_paid)\n"
                        ),
                        "steps": KEYED_STEPS,
                    }
                },
            },
            ["openrouter (holds OPENROUTER_API_KEY) runs on the schedule '43 6 1 * *'"],
        ),
        # A keyed job with no `if` at all runs on every trigger, the weekly one included.
        (
            {"on": {"schedule": [{"cron": "17 6 * * 1"}]}, "jobs": {"paid": {"steps": KEYED_STEPS}}},
            ["paid (holds OPENROUTER_API_KEY) runs on the schedule '17 6 * * 1'"],
        ),
        # A key at the job's level, not a step's, and an `if` that admits any schedule.
        (
            {
                True: {"schedule": [{"cron": "0 0 * * *"}]},
                "jobs": {
                    "j": {"if": "${{ github.event_name != 'pull_request' }}", "env": {"K": "${{ secrets.ANTHROPIC_API_KEY }}"}}
                },
            },
            ["j (holds ANTHROPIC_API_KEY) runs on the schedule '0 0 * * *'"],
        ),
        # A keyed job reached through `needs` from a scheduled one, on a failure.
        (
            {
                "on": {"schedule": [{"cron": "0 0 * * *"}]},
                "jobs": {
                    "free": {"if": "github.event_name == 'schedule'"},
                    "after": {"needs": "free", "if": "failure() && needs.free.result == 'failure'", "steps": KEYED_STEPS},
                },
            },
            ["after (holds OPENROUTER_API_KEY) runs on the schedule '0 0 * * *'"],
        ),
    ],
)
def test_a_schedule_that_reaches_a_paid_key_is_found_by_name(workflow, expected):
    assert schedules_reaching_a_paid_key(workflow) == expected


@pytest.mark.parametrize(
    "workflow",
    [
        # Today's shape: the paid job only on a dispatch that asks for it.
        {
            "on": {"schedule": [{"cron": "17 6 * * 1"}], "workflow_dispatch": None},
            "jobs": {
                "openrouter": {"if": "github.event_name == 'workflow_dispatch' && inputs.include_paid", "steps": KEYED_STEPS}
            },
        },
        # A scheduled job that holds only the pool's key.
        {"on": {"schedule": [{"cron": "0 0 * * *"}]}, "jobs": {"t": {"env": {"K": "${{ secrets.TESTAMENT_KEY }}"}}}},
        # A keyed job that needs a job no schedule starts.
        {
            "on": {"schedule": [{"cron": "0 0 * * *"}]},
            "jobs": {
                "free": {"if": "github.event_name == 'workflow_dispatch'"},
                "after": {"needs": ["free"], "if": "success()", "steps": KEYED_STEPS},
            },
        },
    ],
)
def test_a_workflow_whose_schedules_reach_no_paid_key_passes(workflow):
    assert schedules_reaching_a_paid_key(workflow) == []


def test_a_name_the_check_cannot_value_fails_by_name():
    workflow = {"on": {"schedule": [{"cron": "0 0 * * *"}]}, "jobs": {"j": {"if": "github.ref == 'main'", "steps": KEYED_STEPS}}}

    with pytest.raises(UnknownName, match="github.ref"):
        schedules_reaching_a_paid_key(workflow)
