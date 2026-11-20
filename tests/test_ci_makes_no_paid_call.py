"""No workflow holds a model key: CI makes no paid call, on any event.

The owner's ruling of 2026-11-20 (`.prawduct/owner-rulings.md`, "CI is kept small,
tests run on the pool first, and CI makes no paid call"): "No workflow holds a model
key or reaches a paid service; probes and evaluations that cost money are run by
hand." `api-drift.yml` ran the paid OpenRouter probe on a monthly cron, then (for
one commit of wave 2b's Chunk 66) on a dispatch that asked for it; both were CI
making a paid call with a key GitHub holds. The job is gone, and the probe is run
on a person's machine: `cd arrt && uv run pytest tests/live -m live_api -n0`.

**How a model key is told from a secret CI must keep, with no list of key
names.** The check is the other way round: `SECRETS_CI_MAY_HOLD` names each secret
a workflow may read, with what it buys, and every other secret a workflow reads
is refused by the job's name and the secret's. The pool's client key
(`TESTAMENT_KEY`) is on it because it sends a worktree to the house's test pool,
which runs no live marker (`CLAUDE.md`) and buys nothing. A model key added under
any name fails here until someone writes, beside it, why CI may hold it, which
is the sentence the ruling says cannot be written. A secret read in a way no name
can be given (`secrets[...]`, `toJSON(secrets)`, a reusable workflow's `secrets:
inherit`) is refused too, since nothing can say which secret it is. A name kept
here that no workflow reads any more fails, so the list stays what CI holds.

Read from every workflow under `.github/workflows/`, `.yml` and `.yaml` alike, the whole of each: a workflow's
own `env`, each job's `env`, `with` and `secrets`, each step's `env`, `with` and
`run`, whatever event starts it. So a job reached only by a dispatch is refused
as surely as a scheduled one.

**What it cannot see.** A key that never passes through a `secrets` expression: a
repository variable (`vars.`), a key a script fetches from elsewhere, or a key a
runner holds in its own environment (the pool's runners: whether any holds a
model key is the pool's to say, and the live markers are kept off it). And what
an allowed secret's holder does with it: that the pool runs no paid call is
`CLAUDE.md`'s rule about the live markers, not something read here.
"""

import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"

#: Every secret a workflow may read, and what it buys. Nothing here may be a key
#: to a paid service: the ruling of 2026-11-20 is that CI makes no paid call.
SECRETS_CI_MAY_HOLD: dict[str, str] = {
    "TESTAMENT_KEY": (
        "the pool's client key: `tests.yml` sends the worktree to the house's test pool with it; the pool runs no "
        "live marker and no model call (`CLAUDE.md`), so it buys nothing"
    ),
}

#: A secret named in an expression: `secrets.NAME`.
NAMED = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)")
#: A secret read so that no name can be given: by index, or all of them at once.
UNNAMED = re.compile(r"\bsecrets\s*\[|toJSON\(\s*secrets\s*\)")


def _texts(value: object) -> list[str]:
    """Every string anywhere in a part of a workflow, keys included."""
    if isinstance(value, dict):
        return [text for key, inner in value.items() for text in (*_texts(key), *_texts(inner))]
    if isinstance(value, list):
        return [text for inner in value for text in _texts(inner)]
    return [value] if isinstance(value, str) else []


def _secrets_read(part: object) -> tuple[set[str], bool]:
    """The secrets a part of a workflow names, and whether it reads one it does not name."""
    texts = _texts(part)
    named = {name for text in texts for name in NAMED.findall(text)}
    unnamed = any(UNNAMED.search(text) for text in texts)
    return named, unnamed


def secrets_ci_may_not_hold(workflow: dict) -> list[str]:
    """Each place a workflow reads a secret `SECRETS_CI_MAY_HOLD` does not name, or one no name can be given."""
    found = []
    parts = [("the workflow's env", workflow.get("env"))]
    for job_id, job in (workflow.get("jobs") or {}).items():
        parts.append((job_id, job))
        if isinstance(job, dict) and job.get("secrets") == "inherit":
            found.append(f"{job_id} hands a called workflow every secret (`secrets: inherit`)")
    for where, part in parts:
        named, unnamed = _secrets_read(part)
        for name in sorted(named - set(SECRETS_CI_MAY_HOLD)):
            found.append(f"{where} reads {name}")
        if unnamed:
            found.append(f"{where} reads a secret no name can be given")
    return found


def _workflows(directory: pathlib.Path = WORKFLOWS) -> list[pathlib.Path]:
    """Every workflow GitHub would run from `directory`: each `.yml` and each `.yaml` file in it."""
    return sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _workflows(), ids=lambda path: path.name)
def test_no_workflow_reads_a_secret_ci_may_not_hold(path):
    found = secrets_ci_may_not_hold(_load(path))

    assert found == [], (
        f"{path.name} reads a secret CI may not hold. The owner's ruling of 2026-11-20: CI makes no paid call, "
        "and no workflow holds a model key; run a paid probe by hand. A secret that buys nothing goes in "
        f"SECRETS_CI_MAY_HOLD with what it buys: {found}"
    )


def test_every_secret_ci_may_hold_is_one_a_workflow_reads():
    """A name kept after its last reader went would let the next secret of that name in unread."""
    read = {name for path in _workflows() for name in _secrets_read(_load(path))[0]}

    assert set(SECRETS_CI_MAY_HOLD) <= read, f"no workflow reads {sorted(set(SECRETS_CI_MAY_HOLD) - read)}: delete it"
    assert all(reason.strip() for reason in SECRETS_CI_MAY_HOLD.values())


def test_the_workflows_are_read():
    """Anchors, so a glob that found nothing cannot pass: the drift workflow and the one that holds the pool's key."""
    assert {"api-drift.yml", "tests.yml"} <= {path.name for path in _workflows()}


# -- the check itself can fail ---------------------------------------------------------------------


def test_a_yaml_workflow_holding_a_model_key_is_read_and_refused(tmp_path):
    """GitHub runs `.yaml` workflows as it runs `.yml` ones, so a key in one is found as surely."""
    (tmp_path / "nightly.yaml").write_text(
        yaml.safe_dump({"on": {"schedule": [{"cron": "0 3 * * *"}]}, "jobs": {"eval": {"steps": [KEYED]}}}), encoding="utf-8"
    )
    (tmp_path / "tests.yml").write_text(yaml.safe_dump({"jobs": {"suite": {"steps": [{"run": "true"}]}}}), encoding="utf-8")

    found = {path.name: secrets_ci_may_not_hold(_load(path)) for path in _workflows(tmp_path)}

    assert found == {"nightly.yaml": ["eval reads OPENROUTER_API_KEY"], "tests.yml": []}


KEYED = {"env": {"OPENROUTER_API_KEY": "${{ secrets.OPENROUTER_API_KEY }}"}, "run": "uv run pytest -m live_api"}


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        # The shape `api-drift.yml` had at Chunk 66's fourth commit: the paid job only on a dispatch that asks.
        (
            {
                "on": {"schedule": [{"cron": "17 6 * * 1"}], "workflow_dispatch": {"inputs": {"include_paid": {}}}},
                "jobs": {
                    "museum": {"steps": [{"run": "uv run pytest -m live_museum"}]},
                    "openrouter": {"if": "github.event_name == 'workflow_dispatch' && inputs.include_paid", "steps": [KEYED]},
                },
            },
            ["openrouter reads OPENROUTER_API_KEY"],
        ),
        # A key under any name, at a job's level, with no `if` at all.
        (
            {"jobs": {"nightly": {"env": {"K": "${{ secrets.MY_LLM_TOKEN }}"}, "steps": [{"run": "make eval"}]}}},
            ["nightly reads MY_LLM_TOKEN"],
        ),
        # The workflow's own env, which every job inherits; and a key passed to an action's input.
        (
            {
                "env": {"KEY": "${{ secrets.ANTHROPIC_API_KEY }}"},
                "jobs": {"j": {"steps": [{"uses": "some/action@0", "with": {"token": "${{ secrets.OPENAI_KEY }}"}}]}},
            },
            ["the workflow's env reads ANTHROPIC_API_KEY", "j reads OPENAI_KEY"],
        ),
        # Secrets no name can be given.
        (
            {
                "jobs": {
                    "a": {"steps": [{"env": {"ALL": "${{ toJSON(secrets) }}"}}]},
                    "b": {"steps": [{"env": {"ONE": "${{ secrets[format('{0}_KEY', 'PAID')] }}"}}]},
                    "c": {"uses": "./.github/workflows/other.yml", "secrets": "inherit"},
                }
            },
            [
                "c hands a called workflow every secret (`secrets: inherit`)",
                "a reads a secret no name can be given",
                "b reads a secret no name can be given",
            ],
        ),
    ],
)
def test_a_secret_ci_may_not_hold_is_found_by_name(workflow, expected):
    assert secrets_ci_may_not_hold(workflow) == expected


def test_the_pools_key_and_github_s_own_token_are_not_refused():
    workflow = {
        "jobs": {
            "pool": {"steps": [{"env": {"TESTAMENT_KEY": "${{ secrets.TESTAMENT_KEY }}"}}]},
            "issues": {"steps": [{"env": {"GH_TOKEN": "${{ github.token }}"}}]},
        }
    }

    assert secrets_ci_may_not_hold(workflow) == []
