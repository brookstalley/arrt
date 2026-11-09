"""The suite's own requests are bounded by Playwright's 30 s default, well above the measured worst (`serving.py`)."""

import ast
from pathlib import Path

import httpx
import pytest
from serving import _ONE_SHOT, SUITE_REQUEST_SECONDS

import arrt

_PRODUCT = Path(arrt.__file__).parent


@pytest.mark.parametrize("name", _ONE_SHOT)
def test_every_one_shot_call_a_test_makes_waits_the_suites_bound(name):
    """Read off the function a test calls, so a hook that stopped running fails here, not on a loaded machine."""
    assert getattr(httpx, name).__kwdefaults__["timeout"] == httpx.Timeout(SUITE_REQUEST_SECONDS)


def test_the_product_calls_none_of_httpxs_one_shot_functions():
    """The bound is set on httpx itself, so it would reach a product call too and change what is under test.

    The product builds its own clients, each with the timeout it means, so this
    holds today. It fails by name on the day a module calls `httpx.get` and the
    suite starts testing that call with thirty seconds where production has five.
    """
    found = []
    for path in sorted(_PRODUCT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            called = (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "httpx"
                and node.attr in _ONE_SHOT
            )
            imported = (
                isinstance(node, ast.ImportFrom)
                and node.module == "httpx"
                and any(alias.name in _ONE_SHOT for alias in node.names)
            )
            if called or imported:
                found.append(f"{path.relative_to(_PRODUCT)}:{node.lineno}")
    assert found == []
