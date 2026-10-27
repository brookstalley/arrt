"""The projects this repository holds, for the guards that scan every one of them.

A project is a directory holding a tracked `pyproject.toml`, the root's own
aside. Derived rather than listed, so a project that leaves the repository
leaves every scan with it, and a new one joins them without an edit.
"""

import pathlib
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
