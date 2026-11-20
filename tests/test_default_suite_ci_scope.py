"""What CI runs, and that nothing falls out of it unseen.

Every suite runs on testament's pool: `.github/workflows/tests.yml` hands its
driver one `testament run` with no `--suite`, and the driver asks for every suite
`.testament.toml` declares but the image suite, which CI's key cannot run
(`NOT_CI`, held by `tests/test_ci_fallback.py`). So the manifest decides what CI
covers, and two things can quietly shrink it while the run still reports green:

- a test directory that no suite selects, which the tests at the end of this
  file derive from the tree;
- a workflow edit that narrows the run (a `--suite`, a path) or lets testament
  fall back to GitHub's runner by itself, or a skip guard that reads some other
  file than the report the run wrote, or not the record of where it ran. The
  tests just below read the workflow for each. The fallback the workflow does
  run, when the pool cannot answer, is `tests/test_ci_fallback.py`'s.
"""

import fnmatch
import importlib.util
import pathlib
import re
import shlex
import subprocess
import tomllib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"
CURATION_TESTS = REPO / "arrt" / "tests"


def _run_lines(workflow: dict) -> list[str]:
    """Every shell line of every step, comments and blank lines dropped."""
    lines = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            for line in str(step.get("run", "")).splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    lines.append(stripped)
    return lines


def _testament_runs(lines: list[str]) -> list[list[str]]:
    """The argument lists of every `testament run`, wherever on its line it starts.

    The workflow hands the run to `pool_or_fallback.py` after a `--`, so the command
    is read from where `testament run` begins, not only from a line that opens with it.
    """
    runs = []
    for line in lines:
        at = re.search(r"(?<![\w./-])testament run(?![\w./-])", line)
        if at:
            runs.append(shlex.split(line[at.start() :].split(" > ", 1)[0].split(" || ", 1)[0]))
    return runs


#: The only flags the pool run may carry. An allowlist, because testament accepts
#: `--name=value` for every valued flag and adds flags over time: `--suite=curation`,
#: `--area=x`, `--changed-since=REF` and a path each run less than every suite, and a
#: denylist names only the spellings someone thought of.
_ALLOWED_FLAGS = {"--json", "--json=summary", "--no-fallback"}
_VALUED_FLAGS = {"--junit-xml"}


def check_the_pool_run(lines: list[str]) -> None:
    """Raise unless the lines run every suite on the pool and guard the report they write."""
    runs = _testament_runs(lines)
    assert len(runs) == 1, f"expected one `testament run`, found {len(runs)}: {runs}"
    args = runs[0][2:]
    assert "--no-fallback" in args, "without --no-fallback an unreachable pool runs every suite on GitHub's runner"
    report = None
    refused = []
    i = 0
    while i < len(args):
        if args[i] in _VALUED_FLAGS and i + 1 < len(args):
            report = args[i + 1]
            i += 2
            continue
        if args[i] not in _ALLOWED_FLAGS:
            refused.append(args[i])
        i += 1
    assert not refused, f"the run carries {refused}, which can narrow it to less than every suite"
    assert report, "the run writes no JUnit report, so the skip guard has nothing to read"
    guards = [shlex.split(line) for line in lines if "assert_tests_ran.py" in line]
    assert guards, "nothing checks that the pool's tests actually ran"
    for guard in guards:
        after = guard[guard.index(next(w for w in guard if w.endswith("assert_tests_ran.py"))) + 1 :]
        assert after[:1] == [report], f"the skip guard reads {after[:1]}, not the report the run writes ({report})"
        assert after[1:3] == [
            "--suites-from",
            ".testament.toml",
        ], f"the skip guard is given {after[1:]}, so a suite that collected nothing would hide behind the others' counts"
        assert after[3:4] == ["--decision"] and len(after) == 5 and after[4].endswith("/decision.json"), (
            f"the skip guard is given {after[1:]}, not the record of where the suites ran, "
            "so it cannot tell a pool run from a fallback"
        )


def test_ci_runs_every_suite_on_the_pool_and_guards_its_report():
    check_the_pool_run(_run_lines(yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))))


_GOOD = [
    'python3 .github/scripts/pool_or_fallback.py pool --out "$OUT" -- '
    'testament run --json=summary --junit-xml "$OUT/all.xml" --no-fallback',
    'python3 .github/scripts/assert_tests_ran.py "$OUT/all.xml" --suites-from .testament.toml --decision "$OUT/decision.json"',
]


def test_the_good_shape_passes():
    check_the_pool_run(_GOOD)


def test_a_run_that_can_fall_back_is_refused():
    lines = [_GOOD[0].replace(" --no-fallback", ""), _GOOD[1]]
    try:
        check_the_pool_run(lines)
    except AssertionError as e:
        assert "--no-fallback" in str(e)
    else:
        raise AssertionError("a run without --no-fallback passed")


@pytest.mark.parametrize(
    "narrowing", ["--suite curation", "--suite=curation", "--area=programming", "--changed-since=HEAD~1", "arrt/tests/unit"]
)
def test_a_run_narrowed_in_any_spelling_is_refused(narrowing):
    lines = [_GOOD[0].replace("--no-fallback", f"--no-fallback {narrowing}"), _GOOD[1]]
    with pytest.raises(AssertionError, match="can narrow it"):
        check_the_pool_run(lines)


def test_a_guard_without_the_per_suite_check_is_refused():
    lines = [_GOOD[0], 'python3 .github/scripts/assert_tests_ran.py "$OUT/all.xml"']
    with pytest.raises(AssertionError, match="hide behind the others"):
        check_the_pool_run(lines)


def test_a_guard_without_the_record_of_where_the_suites_ran_is_refused():
    lines = [_GOOD[0], 'python3 .github/scripts/assert_tests_ran.py "$OUT/all.xml" --suites-from .testament.toml']
    with pytest.raises(AssertionError, match="not the record of where the suites ran"):
        check_the_pool_run(lines)


def test_a_run_that_opens_its_line_is_still_read():
    """The older shape, a line that opens with `testament run`, is read the same way."""
    lines = ['testament run --json=summary --junit-xml "$OUT/all.xml" --suite curation --no-fallback', _GOOD[1]]
    with pytest.raises(AssertionError, match="can narrow it"):
        check_the_pool_run(lines)


def test_a_guard_reading_another_report_is_refused():
    lines = [_GOOD[0], 'python3 .github/scripts/assert_tests_ran.py "$OUT/other.xml" --suites-from .testament.toml']
    try:
        check_the_pool_run(lines)
    except AssertionError as e:
        assert "not the report the run writes" in str(e)
    else:
        raise AssertionError("a guard on another file passed")


#: Directories under `arrt/tests` the pool's curation suite leaves to another:
#: the browser suite has its own, and the live suites run only on this machine.
_NOT_IN_THE_POOLS_CURATION_SUITE = {"browser", "live"}


def _holds_tests(entry: pathlib.Path) -> bool:
    if entry.is_file():
        return entry.name.startswith("test_") and entry.suffix == ".py"
    return entry.is_dir() and any(entry.rglob("test_*.py"))


def test_the_pools_curation_suite_selects_every_test_directory_but_the_ones_left_to_others():
    """`.testament.toml` names the curation suite's paths by hand, so a new test directory
    under `arrt/tests` would be left out of a bare `testament run`, which still reports green.
    The list is derived here from the tree."""
    manifest = tomllib.loads((REPO / ".testament.toml").read_text(encoding="utf-8"))
    selected = set(manifest["suites"]["curation"]["default_selection"])
    wanted = {
        f"arrt/tests/{entry.name}"
        for entry in CURATION_TESTS.iterdir()
        if entry.name not in _NOT_IN_THE_POOLS_CURATION_SUITE and _holds_tests(entry)
    }

    assert selected == wanted, (
        f"the pool's curation suite selects {sorted(selected)}, and the tree's test paths are {sorted(wanted)}: "
        f"missing {sorted(wanted - selected)}, extra {sorted(selected - wanted)}"
    )
    assert manifest["suites"]["browser"]["default_selection"] == ["arrt/tests/browser"]


def _uncovered_test_roots(manifest: dict, test_roots: list[str]) -> list[str]:
    """The test roots no suite in `manifest` selects anything under."""
    selections = [path.rstrip("/") for suite in manifest["suites"].values() for path in suite.get("default_selection", [])]
    return [root for root in test_roots if not any(path == root or path.startswith(f"{root}/") for path in selections)]


def test_the_evidence_run_is_every_suite_and_every_test_root_is_in_one():
    """Test evidence is recorded by one `testament run` with no `--suite`, which runs every
    suite `.testament.toml` declares. So the manifest is what decides which projects' tests
    the evidence covers, and a suite dropped from it drops out of the evidence while the run
    still reports green. `tests_dirs` names every project's test root, and each must be
    selected by some suite."""
    state = yaml.safe_load((REPO / ".prawduct" / "project-state.yaml").read_text(encoding="utf-8"))
    manifest = tomllib.loads((REPO / ".testament.toml").read_text(encoding="utf-8"))

    assert state["test_commands"] == ["testament run --junit-xml {junit_xml}"]
    test_roots = state["tests_dirs"].split()
    assert test_roots, "tests_dirs names no test root"
    assert _uncovered_test_roots(manifest, test_roots) == []


def test_a_test_root_no_suite_selects_is_named():
    manifest = {"suites": {"governance": {"default_selection": ["tests"]}, "x": {"default_selection": ["arrt/tests/unit"]}}}

    assert _uncovered_test_roots(manifest, ["tests", "arrt/tests", "contract/tests"]) == ["contract/tests"]
    assert _uncovered_test_roots({"suites": {"y": {"default_selection": ["contract/testsuite"]}}}, ["contract/tests"]) == [
        "contract/tests"
    ]


IMAGE_WORKFLOW = REPO / ".github" / "workflows" / "image.yml"
WORKFLOWS = REPO / ".github" / "workflows"

# -- the image is built on GitHub's runner only for a release --------------------------------------
#
# The owner, 2026-11-20 (`.prawduct/owner-rulings.md`): CI is kept small, GitHub's minutes are
# nearly spent. The image's test stage, about seven minutes of build per pull request, runs on a
# pull request into `main` and by hand only; the one class it caught that nothing else did is
# held on every pull request by `tests/test_the_image_carries_what_tests_read.py`.

#: The base of an ordinary pull request: everything merges into `develop` first.
ORDINARY_BASE = "develop"

#: A step that builds a container image: an action that builds, or a shell line that does.
_BUILDING_ACTIONS = ("docker/build-push-action", "docker/setup-buildx-action", "docker/bake-action")
_BUILDING_LINE = re.compile(
    r"\b(docker\s+(buildx\s+)?(image\s+)?build|docker\s+buildx\s+bake|docker\s+compose\s+build|podman\s+build|buildah)\b"
)


def _triggers(workflow: dict) -> dict:
    """The `on:` block, which YAML 1.1 reads as the key `True`; a bare string or list is normalised."""
    on = workflow.get(True, workflow.get("on"))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {name: None for name in on}
    return dict(on or {})


def _runs_on_an_ordinary_pull_request(workflow: dict) -> bool:
    """Whether a pull request into `develop` starts this workflow, by its triggers' branch filters.

    A filter is read as GitHub reads one only for plain names; any pattern with a wildcard is
    taken to match, so a glob cannot hide a trigger from the check.
    """
    triggers = _triggers(workflow)
    for event in ("pull_request", "pull_request_target", "merge_group"):
        if event not in triggers:
            continue
        config = triggers[event] or {}
        branches = config.get("branches")
        if branches is not None:
            if any(b == ORDINARY_BASE or not re.fullmatch(r"[\w./-]+", b) for b in branches):
                return True
            continue
        if ORDINARY_BASE in (config.get("branches-ignore") or []):
            continue
        return True
    return False


def _image_building_steps(workflow: dict) -> list[str]:
    """`job: step` for every step that builds an image."""
    found = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            uses = str(step.get("uses", ""))
            if uses.startswith(_BUILDING_ACTIONS) or _BUILDING_LINE.search(str(step.get("run", ""))):
                found.append(f"{job_name}: {step.get('name') or uses}")
    return found


def check_no_ordinary_pull_request_builds_an_image(workflows: dict[str, dict]) -> None:
    """Raise, naming each, unless no workflow a pull request into `develop` starts builds an image."""
    building = [
        f"{name} ({step})"
        for name, workflow in sorted(workflows.items())
        if _runs_on_an_ordinary_pull_request(workflow)
        for step in _image_building_steps(workflow)
    ]
    assert not building, (
        f"a pull request into {ORDINARY_BASE} builds an image on GitHub's runner: {building}. "
        "The owner's ruling of 2026-11-20 keeps that to a pull request into main and a run by hand"
    )


def _all_workflows() -> dict[str, dict]:
    return {path.name: yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(WORKFLOWS.glob("*.y*ml"))}


def test_no_workflow_an_ordinary_pull_request_starts_builds_an_image():
    workflows = _all_workflows()
    assert {"image.yml", "tests.yml"} <= set(workflows), f"the workflows read are {sorted(workflows)}"
    assert _image_building_steps(workflows["image.yml"]), "image.yml builds nothing, so this check reads nothing"
    assert _runs_on_an_ordinary_pull_request(workflows["tests.yml"]), "tests.yml is not read as running on every pull request"
    check_no_ordinary_pull_request_builds_an_image(workflows)


@pytest.mark.parametrize(
    "on",
    [
        {"pull_request": None, "workflow_dispatch": None},
        {"pull_request": {"branches": ["main", "develop"]}},
        {"pull_request": {"branches": ["release/**"]}},
        {"pull_request": {"paths": ["arrt/Dockerfile"]}},
        {"pull_request": {"branches-ignore": ["main"]}},
        {"pull_request_target": None},
        "pull_request",
        ["pull_request", "workflow_dispatch"],
    ],
    ids=["unfiltered", "develop-named", "a-glob", "a-paths-filter", "ignoring-main", "target", "a-string", "a-list"],
)
def test_an_image_build_an_ordinary_pull_request_reaches_is_refused(on):
    workflow = yaml.safe_load(IMAGE_WORKFLOW.read_text(encoding="utf-8"))
    workflow[True] = on
    with pytest.raises(AssertionError, match=r"image\.yml \(image: Build the test stage\)"):
        check_no_ordinary_pull_request_builds_an_image({"image.yml": workflow})


@pytest.mark.parametrize(
    "step",
    [
        {"name": "build", "run": "docker build -t x arrt"},
        {"name": "build", "run": "set -e\ndocker buildx build --target test arrt"},
        {"name": "build", "run": "docker compose build"},
        {"name": "build", "uses": "docker/build-push-action@0000000000000000000000000000000000000000"},
    ],
    ids=["docker-build", "buildx", "compose", "the-action"],
)
def test_an_image_built_by_the_suites_workflow_is_refused(step):
    """`tests.yml` runs on every pull request, so an image built there is what the ruling forbids."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    workflow["jobs"]["pool"]["steps"].append(step)
    with pytest.raises(AssertionError, match=r"tests\.yml \(pool: build\)"):
        check_no_ordinary_pull_request_builds_an_image({"tests.yml": workflow})


def check_the_image_triggers(workflow: dict) -> None:
    """Raise unless image.yml runs on a pull request into `main`, unfiltered by path, and by hand, and on nothing else.

    Unfiltered by path because a release builds whatever it changes (two of the
    image's first three reds were tests, which no path filter on the image's inputs watched).
    """
    triggers = _triggers(workflow)
    assert set(triggers) == {
        "pull_request",
        "workflow_dispatch",
    }, f"image.yml runs on {sorted(triggers)}; it runs on a pull request into main and by hand, nothing else"
    config = triggers["pull_request"] or {}
    assert config.get("branches") == [
        "main"
    ], f"image.yml's pull_request trigger has branches {config.get('branches')!r}: a release, `main`, and no other base"
    filtered = sorted(set(config) - {"branches"})
    assert not filtered, f"the pull_request trigger carries {filtered}, so a release could merge with no image built"


def test_the_image_builds_for_a_release_and_by_hand():
    check_the_image_triggers(yaml.safe_load(IMAGE_WORKFLOW.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "on,refusal",
    [
        ({"pull_request": None, "workflow_dispatch": None}, "branches None"),
        ({"pull_request": {"branches": ["main"]}}, "nothing else"),
        ({"pull_request": {"branches": ["main"], "paths": ["arrt/**"]}, "workflow_dispatch": None}, r"carries \['paths'\]"),
        ({"pull_request": {"branches": ["main", "develop"]}, "workflow_dispatch": None}, "no other base"),
        ({"pull_request": {"branches": ["main"]}, "workflow_dispatch": None, "push": None}, "nothing else"),
    ],
    ids=["every-pull-request", "not-by-hand", "path-filtered", "develop-too", "on-push"],
)
def test_an_image_trigger_other_than_a_release_and_by_hand_is_refused(on, refusal):
    workflow = yaml.safe_load(IMAGE_WORKFLOW.read_text(encoding="utf-8"))
    workflow[True] = on
    with pytest.raises(AssertionError, match=refusal):
        check_the_image_triggers(workflow)


def test_the_image_job_builds_on_every_run_it_starts():
    """With the trigger narrowed, no step may decide not to build: a release builds whatever it changes."""
    job = yaml.safe_load(IMAGE_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["image"]
    conditional = [step.get("name") or step.get("uses") for step in job["steps"] if step.get("if", "always()") != "always()"]
    assert "if" not in job and not conditional, f"the image job's build is conditional: {conditional}"


def test_the_required_check_and_the_browsers_mark_keep_their_names():
    """Branch protection requires the first by name; the second is the browser suite's mark (`tests.yml`)."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    assert (jobs["pool"]["name"], jobs["browser"]["name"]) == ("Lint, then every suite", "The browser suite ran on the pool")


# -- the real-Player test: its own suite, and nowhere else ----------------------------------------
#
# What the old arrangement (deselected by the addopts, run unasked only by `image.yml`)
# guaranteed without saying so, and what holds each now:
#
# (a) the curation suite never needs GitHub: its command, over the test's file,
#     collects nothing (`test_the_player_suite_selects_the_one_test_and_the_curation_suite_none`);
# (b) a pool outage never blocks a merge: the fallback leaves the suite out by name
#     (`tests/test_ci_fallback.py`, `POOL_ONLY`), so it never waits on GitHub there;
# (c) the image's test stage never runs it, having no git: that stage runs the addopts
#     with no `-m` of its own (`test_the_image_test_stage_keeps_the_addopts_marker_expression`);
# (d) a bare `cd arrt && uv run pytest` reaches no network: the addopts exclude
#     `player_e2e`, which (a)'s collection runs and the test below reads.

ARRT = REPO / "arrt"
PLAYER_TEST = "arrt/tests/system/test_a_real_player.py"


def _suites() -> dict:
    return tomllib.loads((REPO / ".testament.toml").read_text(encoding="utf-8"))["suites"]


def test_the_player_suite_is_the_curation_suites_command_with_its_marker():
    suites = _suites()
    player, curation = suites["player"], suites["curation"]

    assert player["command"] == [
        *curation["command"],
        "-m",
        "player_e2e",
    ], f"the player suite runs {player['command']}, not the curation suite's command with -m player_e2e"
    assert player["default_selection"] == [PLAYER_TEST]
    assert any(PLAYER_TEST.startswith(f"{path.rstrip('/')}/") for path in curation["default_selection"]), (
        "the curation suite's selection does not hold the real-Player test's file, so the check that its command "
        "deselects the test would pass on a file it never looks at"
    )


def _collected(command: list[str], selection: list[str]) -> tuple[list[str], subprocess.CompletedProcess]:
    """The test ids a suite's pytest command collects over `selection`, run from the root as testament runs it.

    The manifest's `uv run --frozen` is run as `uv run --no-sync`: the environment is the
    one `[setup]` (or the fallback's governance step) made, with groups a plain sync would
    remove (`tests/preferences/test_type_gate.py` does the same).
    """
    assert command[:2] == ["uv", "run"] and "pytest" in command, f"not a uv-run pytest command: {command}"
    pytest_args = command[command.index("pytest") + 1 :]
    project = command[command.index("--project") + 1]
    argv = ["uv", "run", "--no-sync", "--project", project, "pytest", *pytest_args, "-p", "no:cacheprovider"]
    done = subprocess.run(
        [*argv, "--collect-only", *selection], cwd=REPO, capture_output=True, text=True, check=False, timeout=300
    )
    assert done.returncode in (0, 5), (
        f"collecting with {argv} ended {done.returncode} (no tests collected is 5); if uv could not start, make "
        f"the environment first (`cd arrt && uv sync --group dev --group browser`):\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}"
    )
    return [line for line in done.stdout.splitlines() if "::" in line and not line.startswith(" ")], done


def test_the_player_suite_selects_the_one_test_and_the_curation_suite_none():
    suites = _suites()

    player, _ = _collected(suites["player"]["command"], suites["player"]["default_selection"])
    curation, done = _collected(suites["curation"]["command"], [PLAYER_TEST])

    assert len(player) == 1 and player[0].startswith(f"{PLAYER_TEST}::"), f"the player suite collects {player}"
    assert curation == [], f"the curation suite's command collects the real-Player test: {curation}"
    assert "1 deselected" in done.stdout, f"the curation command did not deselect the test, it never saw it:\n{done.stdout}"


def test_the_addopts_exclude_the_real_player_test():
    addopts = shlex.split(
        tomllib.loads((ARRT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]["addopts"]
    )
    expression = addopts[addopts.index("-m") + 1]

    assert "not player_e2e" in expression.split(" and "), f"the addopts' -m {expression!r} does not exclude player_e2e"


def _image_test_stage_pytest(dockerfile: str) -> list[str]:
    runs = [line for line in dockerfile.splitlines() if line.startswith("RUN ") and " pytest" in line]
    assert len(runs) == 1, f"expected the test stage's one pytest RUN in arrt/Dockerfile, found {runs}"
    return shlex.split(runs[0])


def check_the_image_test_stage(words: list[str]) -> None:
    """Raise unless the image's pytest leaves the addopts' marker expression alone: a `-m` of its own replaces it."""
    overriding = [w for w in words if w == "-m" or w.startswith("-m") and len(w) > 2 or w.startswith("--markexpr")]
    assert not overriding, f"the image's test stage passes {overriding}, which replaces the addopts' exclusion of player_e2e"


def test_the_image_test_stage_keeps_the_addopts_marker_expression():
    check_the_image_test_stage(_image_test_stage_pytest((ARRT / "Dockerfile").read_text(encoding="utf-8")))


@pytest.mark.parametrize("extra", ["-m player_e2e", "-m 'not browser'", "--markexpr=player_e2e", "-mplayer_e2e"])
def test_an_image_test_stage_with_a_marker_expression_of_its_own_is_refused(extra):
    words = _image_test_stage_pytest((ARRT / "Dockerfile").read_text(encoding="utf-8")) + shlex.split(extra)
    with pytest.raises(AssertionError, match="replaces the addopts"):
        check_the_image_test_stage(words)


def _header_module():
    spec = importlib.util.spec_from_file_location("player_e2e_header", ARRT / "tests" / "player_e2e_header.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_curation_runs_header_quotes_the_manifests_player_suite():
    """`player_e2e_header.py` tells every curation run where the test runs; the manifest owns that."""
    header = _header_module()
    suites = _suites()

    assert header.SUITE in suites, f"the header names the suite {header.SUITE!r}, which .testament.toml does not declare"
    assert suites[header.SUITE]["default_selection"] == [str(header.TEST_MODULE.relative_to(REPO))]
    assert header.ON_THE_POOL == f"testament run --json=summary --suite {header.SUITE}"
    assert "-m player_e2e" in header.BY_HAND and str(header.TEST_MODULE.relative_to(ARRT)) in header.BY_HAND


# -- the image's test stage, as a suite on the pool -----------------------------------------------
#
# `tests/the_image_test_stage.py` builds the stage on a runner's host. What holds it here, on
# every pull request: it is the build `image.yml` makes; it is routed where that build can run;
# the governance suite, which has no Docker daemon, never collects it; and CI never asks for
# it (`tests/test_ci_fallback.py`, `NOT_CI`).

IMAGE_SUITE_FILE = "tests/the_image_test_stage.py"


def _image_stage_module():
    spec = importlib.util.spec_from_file_location("the_image_test_stage", REPO / IMAGE_SUITE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_image_suite_is_a_host_suite_on_amd64_runners_with_docker_one_batch_at_a_time():
    """Host, because it drives the host's Docker; `docker-heavy`, the label a runner's operator declares for
    work that drives Docker hard; amd64, because the image is (dezoomify-rs ships x86_64 alone, `image.yml`),
    and an arm64 host would build it under emulation; one batch a runner, because its builder is one per host."""
    image = _suites()["image"]

    assert image["executor"] == "host" and image["env"] == {}
    assert sorted(image["requires"]) == ["arch:x86_64", "docker", "docker-heavy"]
    assert image["max_batches_per_runner"] == 1
    assert image["default_selection"] == [IMAGE_SUITE_FILE]
    assert image["setup"]["steps"] == [["uv", "sync", "--frozen"]]


def _build_flags(command: list[str]) -> dict[str, str]:
    """A `docker buildx build` line's valued flags, and its context as `context`."""
    assert command[:3] == ["docker", "buildx", "build"], command
    flags, words = {}, iter(command[3:])
    for word in words:
        if word.startswith("--"):
            flags[word] = next(words)
        else:
            flags["context"] = word
    return flags


def check_the_suite_builds_what_image_yml_builds(command: list[str], workflow: dict) -> None:
    """Raise unless the suite's build is `image.yml`'s: the same context, second context, target and platform."""
    step = next(s for s in workflow["jobs"]["image"]["steps"] if s.get("name") == "Build the test stage")["with"]
    flags = _build_flags(command)
    contexts = dict(c.split("=", 1) for c in step["build-contexts"].split())
    ours = dict([flags["--build-context"].split("=", 1)])
    seen = {
        "context": pathlib.Path(flags["context"]).relative_to(REPO).as_posix(),
        "target": flags["--target"],
        "platforms": flags["--platform"],
        "repo": pathlib.Path(ours["repo"]).relative_to(REPO).as_posix(),
        "dockerfile": pathlib.Path(flags["--file"]).relative_to(REPO).as_posix(),
    }
    wanted = {
        "context": step["context"],
        "target": step["target"],
        "platforms": step["platforms"],
        "repo": contexts["repo"],
        "dockerfile": f"{step['context']}/Dockerfile",
    }
    assert seen == wanted, f"the image suite builds {seen}, and image.yml builds {wanted}"


def test_the_image_suite_builds_what_image_yml_builds():
    check_the_suite_builds_what_image_yml_builds(
        _image_stage_module().build_command(pathlib.Path("/out")), yaml.safe_load(IMAGE_WORKFLOW.read_text(encoding="utf-8"))
    )


@pytest.mark.parametrize(
    "old,new",
    [("test-report", "app"), ("linux/amd64", "linux/arm64"), (f"repo={REPO}", f"repo={REPO / 'arrt'}")],
    # Named, never derived: the third case's values hold the checkout's path, which differs
    # between the pool's workspace slots, so a derived id is not the same test on each.
    ids=["another-target", "another-platform", "another-repo-context"],
)
def test_an_image_suite_building_something_else_is_refused(old, new):
    command = [word.replace(old, new) for word in _image_stage_module().build_command(pathlib.Path("/out"))]
    with pytest.raises(AssertionError, match="and image.yml builds"):
        check_the_suite_builds_what_image_yml_builds(command, yaml.safe_load(IMAGE_WORKFLOW.read_text(encoding="utf-8")))


def check_governance_never_collects_the_image_suite(manifest: dict, pytest_config: dict) -> None:
    """Raise unless each file the image suite selects sits under the governance suite's selection as a name pytest
    collects only when it is named: the governance suite runs where there is no Docker daemon."""
    patterns = pytest_config.get("python_files", ["test_*.py", "*_test.py"])
    patterns = patterns.split() if isinstance(patterns, str) else patterns
    governance = manifest["suites"]["governance"]["default_selection"]
    for path in manifest["suites"]["image"]["default_selection"]:
        assert any(path.startswith(f"{root}/") for root in governance), f"{path} is not under {governance}"
        assert path.endswith(".py"), f"the image suite selects {path}, a directory or not a module"
        name = pathlib.PurePosixPath(path).name
        matched = [p for p in patterns if fnmatch.fnmatch(name, p)]
        assert not matched, f"the governance suite collects {path} (python_files {matched}), and has no Docker"


def _root_pytest_config() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]


def test_the_governance_suite_never_collects_the_image_suite():
    check_governance_never_collects_the_image_suite(
        tomllib.loads((REPO / ".testament.toml").read_text(encoding="utf-8")), _root_pytest_config()
    )


@pytest.mark.parametrize(
    "selection,config",
    [
        (["tests/test_image_stage.py"], {}),
        ([IMAGE_SUITE_FILE], {"python_files": ["*.py"]}),
        ([IMAGE_SUITE_FILE], {"python_files": "*_stage.py"}),
    ],
)
def test_an_image_suite_file_the_governance_suite_would_collect_is_refused(selection, config):
    manifest = tomllib.loads((REPO / ".testament.toml").read_text(encoding="utf-8"))
    manifest["suites"]["image"]["default_selection"] = selection
    with pytest.raises(AssertionError, match="the governance suite collects"):
        check_governance_never_collects_the_image_suite(manifest, config)


#: Lines copied from the suite's first build on the pool (2026-11-20, a runner with Docker,
#: request 93a4a6c667164af997fd0978fffd96a6): two of pytest's progress lines inside the build,
#: and the lines that said what failed.
_OBSERVED_BUILD_TAIL = "\n".join(
    [
        "#38 87.77 ........................................................................ [ 72%]",
        "#38 106.9 ......................................                                   [100%]",
        "#38 120.2 =========================== short test summary info ============================",
        "#38 120.2 FAILED tests/system/test_server_process_guards.py::"
        "test_a_relative_art_root_is_resolved_where_the_server_runs_and_refused",
        "#38 120.2 1 failed, 7307 passed, 2 xfailed, 14 warnings in 117.88s (0:01:57)",
        " 123 | >>> RUN uv run --no-sync pytest -q -p no:cacheprovider --ignore=tests/browser --junitxml=/tmp/results.xml",
        'ERROR: failed to build: failed to solve: process "/bin/sh -c uv run --no-sync pytest -q -p no:cacheprovider '
        '--ignore=tests/browser --junitxml=/tmp/results.xml" did not complete successfully: exit code: 1',
    ]
)


def test_the_failure_text_keeps_what_failed_and_drops_pytests_progress():
    kept = _image_stage_module().tail(_OBSERVED_BUILD_TAIL).splitlines()

    assert kept == _OBSERVED_BUILD_TAIL.splitlines()[2:]
    assert _image_stage_module().tail(_OBSERVED_BUILD_TAIL, lines=2).splitlines() == _OBSERVED_BUILD_TAIL.splitlines()[-2:]
