"""Every run says, by name, what it did with the real-Player test, and where that test runs.

`player_e2e_header.py` holds the words and `conftest.py`'s hooks say them. Asked here
of real pytest runs over the real test module, as a person running the suite sees
them: with the marker expression the suite runs by default (the `addopts`, so a change
there, or to the module's own marks, is tested too), under xdist and without it, with
the expression that selects the test, and with a selection that never reaches it.
Then that neither file reads pytest's private modules, which is what this replaced
(C17 of build-plan-audit-wave-2b: the header compiled the marker expression with
`_pytest.mark.expression`).
"""

import ast
import os
import pathlib
import subprocess
import sys

import pytest
from player_e2e_header import BY_HAND, ON_THE_POOL, WHERE, after_collection

ARRT = pathlib.Path(__file__).resolve().parents[2]
REAL_PLAYER = "tests/system/test_a_real_player.py"


def _pytest(*args: str) -> str:
    """A pytest run of this project with its own configuration, as `cd arrt && uv run pytest …` is, its output."""
    environment = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    done = subprocess.run(  # noqa: S603 -- this interpreter running pytest, with arguments this file composes
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=ARRT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert done.returncode in (0, 5), f"pytest {args} ended {done.returncode}:\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
    return done.stdout


DESELECTED = (
    "player_e2e: this run deselected the real-Player test; it runs as testament's `player` suite "
    "(testament run --json=summary --suite player); by hand: cd arrt && uv run pytest -m player_e2e -n0 "
    "tests/system/test_a_real_player.py"
)


def test_the_default_run_says_it_deselected_the_real_player_test_and_how_to_run_it():
    out = _pytest("-n0", "--collect-only", REAL_PLAYER)

    assert DESELECTED in out.splitlines(), out
    assert WHERE in out.splitlines(), "the header no longer says where the test runs"


def test_the_default_run_says_so_under_xdist_too():
    """The controller collects nothing under `-n`: the line comes from the workers' collections."""
    out = _pytest("-n", "2", REAL_PLAYER)

    assert DESELECTED in out.splitlines(), out


def test_a_run_that_selects_it_says_so():
    out = _pytest("-n0", "--collect-only", "-m", "player_e2e", REAL_PLAYER)

    assert "player_e2e: this run selects the real-Player test, which needs the network to GitHub, git and uv" in out
    assert "deselected the real-Player" not in out


def test_a_run_that_never_reaches_it_says_it_did_not_collect_it():
    out = _pytest("-n0", "--collect-only", "tests/test_scaffold.py")

    assert any(line.startswith("player_e2e: this run did not collect the real-Player test;") for line in out.splitlines())
    assert "deselected the real-Player" not in out


def test_a_process_no_collection_reached_says_it_cannot_tell():
    line = after_collection(None)

    assert line.startswith("player_e2e: no collection reached this process, so it cannot say")
    assert ON_THE_POOL in line
    assert BY_HAND in line


def _imports(path: pathlib.Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("module", ["player_e2e_header.py", "conftest.py"])
def test_the_header_reads_no_private_pytest_module(module):
    private = sorted(name for name in _imports(ARRT / "tests" / module) if name.split(".")[0] == "_pytest")

    assert not private, f"tests/{module} imports {private}, pytest's private modules"
