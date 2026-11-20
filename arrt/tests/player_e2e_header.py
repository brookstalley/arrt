"""What a run's header says about the real-Player test, so its deselection is never silent.

`player_e2e` is off by default (`pyproject.toml`'s `addopts`, for the network it
installs over), and under `-n auto` pytest prints no deselected count, so a run
that leaves it out would otherwise say nothing. `conftest.py`'s
`pytest_report_header` prints `header(config.option.markexpr)` on every run.

The decision is pytest's own: the run's marker expression, evaluated against the
real-Player test's marks, as collection evaluates it. The marks are read from the
test module itself (`tests/system/test_a_real_player.py`'s `pytestmark`), so a
mark added there cannot leave this saying the wrong thing.
"""

import ast
import pathlib

from _pytest.mark.expression import Expression

TEST_MODULE = pathlib.Path(__file__).resolve().parent / "system" / "test_a_real_player.py"
RUN_IT = "-m player_e2e arrt/tests/system/test_a_real_player.py"


def marks() -> frozenset[str]:
    """The marks on the real-Player test's module, by name: `pytest.mark.<name>` in its `pytestmark` list."""
    for node in ast.parse(TEST_MODULE.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "pytestmark" for t in node.targets):
            found = {
                (call.func if isinstance(call, ast.Call) else call).attr
                for call in getattr(node.value, "elts", [])
                if isinstance(call.func if isinstance(call, ast.Call) else call, ast.Attribute)
            }
            if found:
                return frozenset(found)
    raise AssertionError(f"{TEST_MODULE} has no pytestmark list; has the real-Player test moved?")


def header(markexpr: str, test_marks: frozenset[str] | None = None) -> str:
    """The header line for a run whose `-m` is `markexpr` (empty when the run gave none)."""
    held = marks() if test_marks is None else test_marks
    if markexpr and not Expression.compile(markexpr).evaluate(lambda name, /, **_: name in held):
        return f"player_e2e: the real-Player test is deselected by -m {markexpr!r}; run it with {RUN_IT}"
    return "player_e2e: this run's marker expression does not exclude the real-Player test"
