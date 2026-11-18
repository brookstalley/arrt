"""What CI runs, and that nothing falls out of it unseen.

Every suite runs on testament's pool: `.github/workflows/tests.yml` runs one
`testament run` with no `--suite`, which runs every suite `.testament.toml`
declares. So the manifest decides what CI covers, and two things can quietly
shrink it while the run still reports green:

- a test directory that no suite selects, which the tests at the end of this
  file derive from the tree;
- a workflow edit that narrows the run (a `--suite`, a path) or lets it fall
  back to GitHub's runner, or a skip guard that reads some other file than the
  report the run wrote. The tests just below read the workflow for each.
"""

import pathlib
import shlex
import tomllib

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
    """The argument lists of every `testament run` line."""
    runs = []
    for line in lines:
        if line.startswith("testament run"):
            runs.append(shlex.split(line.split(" > ", 1)[0].split(" || ", 1)[0]))
    return runs


def check_the_pool_run(lines: list[str]) -> None:
    """Raise unless the lines run every suite on the pool and guard the report they write."""
    runs = _testament_runs(lines)
    assert len(runs) == 1, f"expected one `testament run`, found {len(runs)}: {runs}"
    args = runs[0][2:]
    assert "--no-fallback" in args, "without --no-fallback an unreachable pool runs every suite on GitHub's runner"
    assert "--suite" not in args, "a --suite narrows CI to that suite, and the rest stop running with nothing to say so"
    report = args[args.index("--junit-xml") + 1] if "--junit-xml" in args else None
    assert report, "the run writes no JUnit report, so the skip guard has nothing to read"
    selection = [a for i, a in enumerate(args) if not a.startswith("-") and (i == 0 or args[i - 1] != "--junit-xml")]
    assert not selection, f"the run selects {selection}, so CI runs less than every suite"
    guards = [line for line in lines if "assert_tests_ran.py" in line]
    assert guards, "nothing checks that the pool's tests actually ran"
    reads = {shlex.split(line)[-1] for line in guards}
    assert reads == {report}, f"the skip guard reads {sorted(reads)}, not the report the run writes ({report})"


def test_ci_runs_every_suite_on_the_pool_and_guards_its_report():
    check_the_pool_run(_run_lines(yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))))


_GOOD = [
    'testament run --json=summary --junit-xml "$OUT/all.xml" --no-fallback > "$OUT/envelope.json" || code=$?',
    'python3 .github/scripts/assert_tests_ran.py "$OUT/all.xml"',
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


def test_a_run_narrowed_to_one_suite_is_refused():
    lines = [_GOOD[0].replace("--no-fallback", "--no-fallback --suite curation"), _GOOD[1]]
    try:
        check_the_pool_run(lines)
    except AssertionError as e:
        assert "--suite" in str(e)
    else:
        raise AssertionError("a run narrowed to one suite passed")


def test_a_guard_reading_another_report_is_refused():
    lines = [_GOOD[0], 'python3 .github/scripts/assert_tests_ran.py "$OUT/other.xml"']
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
    The list is derived here from the tree, as the CI leg's ignores are above."""
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
DOCKERFILE = REPO / "arrt" / "Dockerfile"

#: What the image copies in that `image.yml` deliberately does not watch, because the
#: pool's suites run it on every pull request: the server's code, tests and tools, the
#: contract package's source and the documents its tests read. The contract's own
#: dependency declarations are watched, since they change what the image installs.
_RUN_BY_THE_POOL = {"arrt/src", "arrt/tests", "arrt/tools", "contract", ".prawduct/artifacts/player-contract.md", "all.json"}


def _copied_sources(dockerfile: str) -> set[str]:
    """Every repository path a `COPY` brings into the image, as a path from the repo root.

    The build context is `arrt/`; `--from=repo` is the repository root (`image.yml`'s
    `build-contexts`); any other `--from` names an earlier stage, which copies nothing
    from the repository.
    """
    stages = {line.split()[-1] for line in dockerfile.splitlines() if line.startswith("FROM ") and " AS " in line}
    found = set()
    for line in dockerfile.splitlines():
        if not line.startswith("COPY "):
            continue
        words = line.split()[1:]
        source = next((w.split("=", 1)[1] for w in words if w.startswith("--from=")), None)
        paths = [w for w in words if not w.startswith("--")][:-1]
        if source in stages:
            continue
        root = "" if source == "repo" else "arrt/"
        found |= {f"{root}{p}".rstrip("/") for p in paths}
    return found


def check_the_image_filter(copied: set[str], watched: list[str]) -> None:
    """Raise unless every copied path is watched by the filter or run by the pool."""
    unwatched = sorted(
        path for path in copied if path not in _RUN_BY_THE_POOL and path not in watched and f"{path}/**" not in watched
    )
    assert not unwatched, (
        f"arrt/Dockerfile copies {unwatched}, which image.yml's paths filter does not watch and the pool "
        "does not run: add each to the filter, or to _RUN_BY_THE_POOL with the reason the pool covers it"
    )


def test_the_image_build_watches_everything_the_image_is_built_from():
    workflow = yaml.safe_load(IMAGE_WORKFLOW.read_text(encoding="utf-8"))
    watched = workflow[True]["pull_request"]["paths"]
    copied = _copied_sources(DOCKERFILE.read_text(encoding="utf-8"))
    assert copied, "no COPY read from arrt/Dockerfile, so this checks nothing"

    check_the_image_filter(copied, watched)


def test_a_copied_file_the_filter_misses_is_named():
    try:
        check_the_image_filter({"arrt/uv.lock", "arrt/requirements.txt"}, ["arrt/uv.lock"])
    except AssertionError as e:
        assert "arrt/requirements.txt" in str(e)
        assert "arrt/uv.lock'" not in str(e)
    else:
        raise AssertionError("a copied file outside the filter passed")


def test_copy_sources_are_read_from_the_right_context():
    dockerfile = "\n".join(
        [
            "FROM uv:1 AS uv",
            "FROM debian AS base",
            "COPY --from=uv /uv /uvx /usr/local/bin/",
            "COPY pyproject.toml uv.lock ./",
            "COPY --from=repo contract /contract",
        ]
    )
    assert _copied_sources(dockerfile) == {"arrt/pyproject.toml", "arrt/uv.lock", "contract"}
