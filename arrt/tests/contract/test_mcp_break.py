"""The MCP surface's shape, held to a recording of it.

`SNAPSHOT` is the surface as it stood before wave 2b's one allowed break
(the owner's ruling 3 of 2026-11-19), recorded by `record()` from the registry
and the bindings themselves: every tool's annotations, every action's
arguments, and every key each action's answer can carry.
"""

import ast
import inspect
import json
from pathlib import Path
from typing import Any

from arrt.mcp import bindings
from arrt.mcp.registry import HELP_ACTION
from arrt.mcp.tools import TOOLS

SNAPSHOT = Path(__file__).resolve().parents[1] / "fixtures" / "mcp-surface-before-the-break.json"


def _module_functions() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(inspect.getsource(bindings))
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _result_keys(name: str, functions: dict[str, ast.FunctionDef], seen: set[str] | None = None) -> set[str]:
    """Every key a binding can answer: `ok(...)`'s keywords and every literal dict key, through the helpers it reaches."""
    seen = set() if seen is None else seen
    if name in seen:
        return set()
    seen.add(name)
    keys: set[str] = set()
    for node in ast.walk(functions[name]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ok":
            keys.update(keyword.arg for keyword in node.keywords if keyword.arg is not None)
        elif isinstance(node, ast.Dict):
            keys.update(key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str))
        elif isinstance(node, ast.Name) and node.id in functions and node.id != name:
            keys |= _result_keys(node.id, functions, seen)
    return keys


def _param_shape(param: Any) -> dict[str, Any]:
    return {
        "type": param.type,
        "required": param.required,
        "choices": None if param.choices is None else list(param.choices),
        "minimum": param.minimum,
        "maximum": param.maximum,
        "items": param.items,
    }


def surface_shape() -> dict[str, Any]:
    """The surface as names: each tool's annotations, each action's arguments and the keys its answer can carry."""
    functions = _module_functions()
    shape: dict[str, Any] = {}
    for tool in TOOLS:
        actions: dict[str, Any] = {}
        for action in tool.actions:
            if action.name == HELP_ACTION:
                continue
            binding = bindings.BINDINGS[(tool.name, action.name)]
            actions[action.name] = {
                "arguments": {param.name: _param_shape(param) for param in action.params},
                "result_keys": sorted(_result_keys(binding.__name__, functions)),
            }
        shape[tool.name] = {
            "read_only": tool.read_only,
            "destructive": tool.destructive,
            "open_world": tool.open_world,
            "actions": actions,
        }
    return shape


def record() -> None:
    """Write the snapshot. Run once, at the commit the snapshot names; never to make a test pass."""
    SNAPSHOT.write_text(json.dumps(surface_shape(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_the_surface_is_the_recorded_one():
    assert surface_shape() == json.loads(SNAPSHOT.read_text(encoding="utf-8"))
