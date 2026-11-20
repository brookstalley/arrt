"""The run's header says, by name, when the real-Player test is deselected, and how to run it.

`player_e2e_header.header` is what `conftest.py`'s `pytest_report_header` prints.
It is asked here with the marker expression the suite runs by default (read from
`pyproject.toml`'s `addopts`, so a change there is tested too) and with the one
that runs the test.
"""

import pathlib
import shlex
import tomllib

from player_e2e_header import RUN_IT, header, marks

PYPROJECT = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"


def _default_markexpr() -> str:
    addopts = shlex.split(tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]["addopts"])
    return addopts[addopts.index("-m") + 1]


def test_the_default_run_says_the_real_player_test_is_deselected_and_how_to_run_it():
    expression = _default_markexpr()

    line = header(expression)

    assert "player_e2e" in expression
    assert line == f"player_e2e: the real-Player test is deselected by -m {expression!r}; run it with {RUN_IT}"


def test_a_run_that_selects_it_does_not_say_it_is_deselected():
    line = header("player_e2e")

    assert "deselected" not in line
    assert line == "player_e2e: this run's marker expression does not exclude the real-Player test"


def test_a_run_with_no_marker_expression_does_not_say_it_is_deselected():
    assert "deselected" not in header("")


def test_an_expression_that_excludes_another_mark_of_the_test_is_read_as_deselecting_it():
    """The decision is the expression against all of the test's marks, not a search for the word."""
    assert "deselected" in header("not uncacheable")
    assert "deselected" not in header("not browser")


def test_the_marks_are_the_real_player_tests_own():
    assert {"player_e2e", "uncacheable"} <= marks()
