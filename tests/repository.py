"""What the guards that scan this repository share: its projects, and how CI runs pytest.

A project is a directory holding a tracked `pyproject.toml`, the root's own
aside. Derived rather than listed, so a project that leaves the repository
leaves every scan with it, and a new one joins them without an edit.
"""

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def projects() -> list[str]:
    """Each project's directory, relative to the repository root. Never empty: a scan over none checks nothing."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "*pyproject.toml"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    found = sorted(str(pathlib.PurePosixPath(name).parent) for name in listed if name and name != "pyproject.toml")
    assert found, "no project's pyproject.toml is tracked; a scan over the projects would cover nothing"
    return found


#: `uv run`, anything uv itself takes, then `pytest`. **Whatever sits between is
#: the point.** Matching the literal `uv run pytest` skips every `uv run --group
#: <name> pytest …` in silence, and a suite that needs a group is the kind that
#: skips itself when the group is absent. A pattern spelling out which options may
#: appear skips the next option it does not know in the same silence, so nothing
#: between the two words is constrained.
#:
#: Each word stands alone, bounded by anything that is not a name or path
#: character. A word boundary alone stops inside `pytest-cov` or `./pytest`,
#: which an option's value may carry, and the line then splits at the wrong
#: word. A boundary of whitespace alone never sees a quoted `run:` value, which
#: YAML needs whenever it holds `: `. Shared by both scans of the workflows: the
#: scope guard and the CI-scope guard.
INVOCATION = re.compile(r"(?<![\w./-])uv run(?![\w./-]).*?(?<![\w./-])pytest(?![\w./-])")
