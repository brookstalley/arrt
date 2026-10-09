"""Where code and tests live: the root only shrinks, and every test sits in its plane's `tests/`.

Two preferences in `project-preferences.md` § Testing and § File organization,
which went two Norm Health sweeps with no mechanism. Both are structural, so both
get a test rather than a reviewer's memory.
"""

import pathlib
import subprocess

_REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: The root plane's modules on 2026-10-05, when this guard was written. The rule is
#: that nothing new is added at the root: new code goes in a plane package. So the
#: set may lose members (the 2024 modules leave at wave 5, and the hand-run tools
#: move to `arrt-player/tools` before the extraction) and may never gain one. A module
#: that leaves is deleted from this list in the same commit, which is the only edit
#: this list should ever see.
_ROOT_MODULES = frozenset(
    {
        "ai.py",
        "art.py",
        "config.py",
        "display.py",
        "image_utils.py",
        "local.py",
        "metadata.py",
        "panel_check.py",
        "remote_test.py",
        "source_utils.py",
        "spi_test.py",
        "tv_api_check.py",
        "tv_delete.py",
        "tvart.py",
        "urls_to_json.py",
    }
)

#: Each plane's test tree. `testpaths = ["tests"]` in every plane's `pyproject.toml`
#: means a `test_*.py` anywhere else is never collected, so it would look like a
#: test and guard nothing.
_TEST_TREES = ("tests/", "arrt/tests/", "arrt-player/tests/")


def _tracked() -> list[str]:
    files = subprocess.run(
        ["git", "ls-files", "-z"], cwd=_REPOSITORY_ROOT, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    tracked = [name for name in files if name]
    assert len(tracked) > 100, "git ls-files returned almost nothing; the check would be vacuous"
    return tracked


def test_nothing_new_is_added_at_the_root():
    present = {name for name in _tracked() if "/" not in name and name.endswith(".py")}

    assert present, "no root modules found; has the layout moved?"
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
