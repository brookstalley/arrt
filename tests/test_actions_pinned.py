"""Every action a workflow runs is pinned to a commit, and no job that holds a secret can write issues.

Two properties of `.github/workflows/`, both on a public repository whose CI runs
code with a key in reach.

**Pinned by commit.** A tag is a pointer its owner can move, and `tests.yml` hands
`TESTAMENT_KEY` to steps that run after `actions/checkout` and `astral-sh/setup-uv`
in the same job: a moved tag there could poison `PATH` or `uv` and read the key
from a later step (`audit-8` F6). A 40-hex commit is the only reference that
cannot move. The tag the commit was resolved from stays in a trailing comment, so
a person reading the file knows what is pinned and can re-resolve it
(`gh api repos/<owner>/<repo>/git/ref/tags/<tag>`, following an annotated tag to
its commit). No Dependabot is added, by the plan's ruling: it would open pull
requests on a public repository and spend the minutes the 2026-11-18 ruling saves.
A local action (`./path`) is this repository's own tree and is not a pointer to
anything; a `docker://` reference must carry a digest.

**What the pin check cannot see.** That the commit is the one the tag named, or
that it still is: a pin proves the reference is fixed, not that it was good when
fixed. And a download the workflow makes by hand (`api-drift.yml` fetches the
latest dezoomify-rs on purpose, and its comment says why) is a `run:` step, which
no `uses:` check reads.

**Least privilege.** `issues: write` is what lets a failing drift job open an
issue. It is granted to the job that reports, and never to a job that holds a
secret of the repository's (`audit-8` F22, written when a drift job held the
OpenRouter key; since wave 2b's Chunk 66 no workflow holds a model key,
`tests/test_ci_makes_no_paid_call.py`, and the secret it guards is the pool's). Permissions are
read as GitHub resolves them: a job that names its own `permissions` replaces the
workflow's, and one that names none inherits them.
"""

import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
GITHUB = REPO / ".github"

_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>[^\s#]+)\s*(?:#\s*(?P<comment>.*\S))?\s*$")
_COMMIT = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
_DIGEST = re.compile(r"^docker://\S+@sha256:[0-9a-f]{64}$")


def _yaml_files() -> list[pathlib.Path]:
    return sorted([*GITHUB.rglob("*.yml"), *GITHUB.rglob("*.yaml")])


def unpinned_uses(text: str, where: str = "<text>") -> list[str]:
    """One line per `uses:` that is not a commit with its tag beside it, naming the file, the line and the reference."""
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        found = _USES.match(line)
        if not found:
            if re.match(r"^\s*(?:-\s+)?uses:", line):
                problems.append(f"{where}:{number}: a `uses:` this check cannot read: {line.strip()}")
            continue
        reference, comment = found["ref"], found["comment"]
        if reference.startswith("./"):
            continue
        if reference.startswith("docker://"):
            if not _DIGEST.match(reference):
                problems.append(f"{where}:{number}: {reference} is a docker reference with no sha256 digest")
            continue
        if not _COMMIT.match(reference):
            problems.append(f"{where}:{number}: {reference} is not pinned to a 40-hex commit")
        elif not comment:
            problems.append(f"{where}:{number}: {reference} names no tag in a trailing comment")
    return problems


def test_there_are_workflows_with_uses_to_check():
    """The vacuity check: a scan of nothing passes."""
    files = _yaml_files()

    assert files, f"no workflow files under {GITHUB}"
    assert sum(len(re.findall(r"^\s*(?:-\s+)?uses:", f.read_text(), re.M)) for f in files) >= 5


def test_every_action_is_pinned_to_a_commit_with_its_tag_in_a_comment():
    problems = [
        problem
        for path in _yaml_files()
        for problem in unpinned_uses(path.read_text(encoding="utf-8"), str(path.relative_to(REPO)))
    ]

    assert problems == [], "\n".join(problems)


class TestThePinCheckCanFail:
    """Planted references, one per way a pin goes wrong."""

    def test_a_major_tag_fails(self):
        problems = unpinned_uses("      - uses: actions/checkout@v4\n", "w.yml")

        assert problems == ["w.yml:1: actions/checkout@v4 is not pinned to a 40-hex commit"]

    def test_a_branch_fails(self):
        assert unpinned_uses("    uses: actions/checkout@main\n")

    def test_a_short_sha_fails(self):
        assert unpinned_uses("      - uses: actions/checkout@11d5960 # v4\n")

    def test_a_forty_character_ref_that_is_not_hex_fails(self):
        assert unpinned_uses(f"      - uses: actions/checkout@{'g' * 40} # v4\n")

    def test_a_commit_with_no_tag_comment_fails(self):
        problems = unpinned_uses(f"      - uses: actions/checkout@{'a' * 40}\n")

        assert len(problems) == 1
        assert "names no tag" in problems[0]

    def test_a_docker_reference_by_tag_fails(self):
        assert unpinned_uses("      - uses: docker://alpine:3.20\n")

    def test_a_pinned_commit_with_its_tag_passes(self):
        assert unpinned_uses(f"      - uses: actions/checkout@{'a' * 40} # v4\n") == []

    def test_a_step_that_names_the_action_on_its_own_line_is_read(self):
        text = "      - name: x\n        uses: docker/build-push-action@v6\n        with:\n          a: b\n"

        assert len(unpinned_uses(text)) == 1

    def test_a_local_action_passes(self):
        assert unpinned_uses("      - uses: ./.github/actions/thing\n") == []

    def test_a_path_inside_an_action_repository_is_checked_like_the_rest(self):
        assert unpinned_uses("      - uses: github/codeql-action/analyze@v3\n")
        assert unpinned_uses(f"      - uses: github/codeql-action/analyze@{'b' * 40} # v3\n") == []


# -- least privilege ------------------------------------------------------


def jobs_that_can_write_issues_while_holding_a_secret(workflow: dict) -> list[str]:
    """The jobs whose effective permissions include `issues: write` and whose steps read a repository secret.

    `secrets.GITHUB_TOKEN` is not one: it is the token the permissions govern, so
    a job using it holds nothing the grant does not already carry.
    """
    inherited = workflow.get("permissions")
    found = []
    for name, job in (workflow.get("jobs") or {}).items():
        permissions = job["permissions"] if "permissions" in job else inherited
        if not isinstance(permissions, dict) or permissions.get("issues") != "write":
            continue
        secrets_read = {
            secret for secret in re.findall(r"secrets\.([A-Za-z0-9_]+)", yaml.safe_dump(job)) if secret != "GITHUB_TOKEN"
        }
        if secrets_read:
            found.append(f"{name} (reads {', '.join(sorted(secrets_read))})")
    return found


def test_no_job_that_holds_a_secret_can_write_issues():
    offenders = []
    for path in sorted((GITHUB / "workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        offenders += [f"{path.name}: {job}" for job in jobs_that_can_write_issues_while_holding_a_secret(workflow)]

    assert offenders == [], "\n".join(offenders)


def test_the_drift_workflow_still_has_a_job_that_can_write_issues():
    """Without one, the failure route this guard protects would be gone and the guard above would pass over nothing."""
    workflow = yaml.safe_load((GITHUB / "workflows" / "api-drift.yml").read_text(encoding="utf-8"))

    writers = [name for name, job in workflow["jobs"].items() if job.get("permissions", {}).get("issues") == "write"]

    assert writers, "no api-drift job has issues: write, so a failing probe cannot open its issue"


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        # the shape this audit found: write granted to the whole workflow, one job holds a key
        (
            {
                "permissions": {"issues": "write"},
                "jobs": {"paid": {"steps": [{"env": {"K": "${{ secrets.OPENROUTER_API_KEY }}"}}]}},
            },
            ["paid (reads OPENROUTER_API_KEY)"],
        ),
        # granted to the job itself
        (
            {
                "jobs": {
                    "paid": {"permissions": {"issues": "write"}, "steps": [{"env": {"K": "${{ secrets.OPENROUTER_API_KEY }}"}}]}
                }
            },
            ["paid (reads OPENROUTER_API_KEY)"],
        ),
        # a job that names its own permissions replaces the workflow's
        (
            {
                "permissions": {"issues": "write"},
                "jobs": {
                    "paid": {"permissions": {"contents": "read"}, "steps": [{"env": {"K": "${{ secrets.OPENROUTER_API_KEY }}"}}]}
                },
            },
            [],
        ),
        # a writer that holds no secret of its own is the reporting job
        ({"jobs": {"report": {"permissions": {"issues": "write"}, "steps": [{"env": {"GH_TOKEN": "${{ github.token }}"}}]}}}, []),
        # the token the grant governs is not a secret the grant adds to
        ({"jobs": {"r": {"permissions": {"issues": "write"}, "steps": [{"env": {"T": "${{ secrets.GITHUB_TOKEN }}"}}]}}}, []),
    ],
)
def test_the_privilege_check_knows_a_holder_from_a_reporter(workflow, expected):
    assert jobs_that_can_write_issues_while_holding_a_secret(workflow) == expected
