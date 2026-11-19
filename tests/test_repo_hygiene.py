"""No source file is silently excluded from version control.

This exists because of a real near-miss: the stock Python `.gitignore` carries an
unanchored `MANIFEST` rule for the setuptools artifact, and on a case-insensitive
filesystem (macOS) that also matched `arrt/src/arrt/programming/manifest/` — the
feed builder, which publishes what every Player shows. The
package existed on disk, imports succeeded, and tests passed; it was simply never
committed. A fresh clone, or the Pi, would have had a missing module.

The failure mode is invisible by construction, so it gets a mechanical guard
rather than vigilance.
"""

import pathlib
import subprocess

import pytest
from repository import ROOT, projects, projects_present


def _source_trees(names: list[str]) -> tuple[str, ...]:
    """Every tree whose absence from a fresh clone would matter.

    Each project's `src` and `tests`, its `tools` where it has one, and the
    root's own `tests`. A project's tests carry almost all of its coverage, and
    a tree the guard does not walk is exactly the tree this guard was built for:
    the suite stays green locally while the clone quietly loses it. The `tools/`
    trees are here because an operator runs them by hand.
    """
    return (
        "tests",
        *(
            f"{project}/{tree}"
            for project in names
            for tree in ("src", "tests", "tools")
            if tree != "tools" or (ROOT / project / "tools").is_dir()
        ),
    )


#: The trees as collection sees them, from the projects in the tree rather than
#: git's index: a git call at import would count against every test in the process.
#: The scans below ask git which projects are tracked, inside the test.
SOURCE_TREES_PRESENT = _source_trees(projects_present())


def source_trees() -> tuple[str, ...]:
    """The trees of every tracked project, which the scans walk."""
    return _source_trees(projects())


@pytest.fixture(autouse=True)
def _at_the_repository_root(monkeypatch):
    """Every path and git call below is relative to the repository root, wherever pytest was started."""
    monkeypatch.chdir(ROOT)


def _ignored(paths: list[pathlib.Path]) -> list[str]:
    """Return the subset of `paths` that git would exclude."""
    if not paths:
        return []
    # `--no-index` is load-bearing. Without it git skips paths already in the
    # index, because ignore rules genuinely do not apply to tracked files — so
    # the check would pass for anything already committed and could never fail
    # on a bad rule once the damage was undone. We want the stronger invariant:
    # no ignore rule matches a source path, whatever the index currently holds.
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "--no-index"],
        input="\n".join(str(p) for p in paths),
        capture_output=True,
        text=True,
        check=False,
    )
    # Exit 0 = some paths ignored, 1 = none ignored. Anything else is a real error.
    assert result.returncode in (0, 1), f"git check-ignore failed: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line]


@pytest.mark.parametrize("tree", SOURCE_TREES_PRESENT)
def test_every_tree_the_scan_names_exists(tree):
    """Each tree on its own, because the scans below skip a missing one.

    Their own check is that *something* was found, which a single misspelled or
    moved tree cannot fail while the others still hold files.
    """
    assert pathlib.Path(tree).is_dir(), f"{tree} is not a directory, so the scans below pass over nothing there"


def test_the_trees_checked_one_by_one_are_every_tree_the_scans_walk():
    """The cases above come from the tree, the scans from git's index; a tracked project they miss is checked by neither."""
    unchecked = sorted(set(source_trees()) - set(SOURCE_TREES_PRESENT))
    assert not unchecked, f"trees the scans walk that no case above checks exists: {unchecked}"


def test_no_python_source_is_gitignored():
    candidates: list[pathlib.Path] = []
    for tree in source_trees():
        root = pathlib.Path(tree)
        if root.exists():
            candidates.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)

    assert candidates, "expected to find source files; has the layout moved?"
    ignored = _ignored(candidates)
    assert not ignored, "these source files would never be committed:\n" + "\n".join(ignored)


def test_no_package_directory_is_gitignored():
    """Directories matter separately: an ignored dir hides files that look fine alone."""
    candidates: list[pathlib.Path] = []
    for tree in source_trees():
        root = pathlib.Path(tree)
        if root.exists():
            candidates.extend(p for p in root.rglob("*") if p.is_dir() and p.name != "__pycache__")

    assert candidates, "expected to find package directories; has the layout moved?"
    ignored = _ignored(candidates)
    assert not ignored, "these package directories would never be committed:\n" + "\n".join(ignored)


def test_the_tv_token_is_not_tracked():
    """It was committed to a public repo once. Keep it from happening twice."""
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
    offenders = [p for p in tracked if pathlib.Path(p).name in {"token_file", ".env"}]
    assert not offenders, f"credential files must never be tracked: {offenders}"
