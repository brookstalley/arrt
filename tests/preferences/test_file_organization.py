"""Where code and tests live: no code at the root, and every test sits in its plane's `tests/`.

Two preferences in `project-preferences.md` § Testing and § File organization,
which went two Norm Health sweeps with no mechanism. Both are structural, so both
get a test rather than a reviewer's memory.
"""

import pathlib
import subprocess

_REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: The root holds no modules. Code goes in a plane package or a plane's `tools/`;
#: the root is the governance suite, its CI scripts and tool configuration. The
#: 2024 modules that were here left at the legacy retirement, and the hand-run
#: tools went to `arrt-player/tools` with the Player whose hardware they exercise.
_ROOT_MODULES: frozenset[str] = frozenset()

#: Each plane's test tree, and the contract package's. `testpaths = ["tests"]` in every plane's `pyproject.toml`
#: means a `test_*.py` anywhere else is never collected, so it would look like a
#: test and guard nothing.
_TEST_TREES = ("tests/", "arrt/tests/", "arrt-player/tests/", "contract/tests/")


def _tracked() -> list[str]:
    files = subprocess.run(
        ["git", "ls-files", "-z"], cwd=_REPOSITORY_ROOT, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    tracked = [name for name in files if name]
    assert len(tracked) > 100, "git ls-files returned almost nothing; the check would be vacuous"
    return tracked


def test_nothing_new_is_added_at_the_root():
    present = {name for name in _tracked() if "/" not in name and name.endswith(".py")}

    assert present <= _ROOT_MODULES, (
        f"new modules at the repository root: {sorted(present - _ROOT_MODULES)}. "
        "New code goes in a plane package (arrt/src, arrt-player/src, or a plane's tools/)."
    )


def test_every_test_module_lives_in_its_planes_test_tree():
    misplaced = [
        name
        for name in _tracked()
        if pathlib.PurePosixPath(name).name.startswith("test_") and name.endswith(".py") and not name.startswith(_TEST_TREES)
    ]

    assert not misplaced, f"test modules outside a plane's tests/, which pytest never collects: {misplaced}"
