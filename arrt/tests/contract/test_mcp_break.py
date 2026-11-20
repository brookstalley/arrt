"""The MCP surface's one break, and nothing else breaking with it.

`SNAPSHOT` is the surface as it stood before the break the owner allowed once
(ruling 3 of 2026-11-19), recorded by `record()` from the registry and the
bindings themselves at the reset point 15704496: every tool's annotations,
every action's arguments, and every key each action's answer can carry. The
break is four tables below; the surface is held to the recording with them
applied, so a second break fails by tool, action and name. A caller of an old
name is refused naming the new one (`registry.resolve_action`, `validate`).

The result keys are read from `bindings.py`'s source: `ok(...)`'s keywords and
every literal dict key, through the helpers each binding reaches. That is a
flattened set per action, not the nested shape, so it holds that a name is
still answered, not where.
"""

import ast
import inspect
import json
from pathlib import Path
from typing import Any, cast

import pytest

from arrt.mcp import bindings, registry
from arrt.mcp.registry import HELP_ACTION
from arrt.mcp.server import dispatch
from arrt.mcp.tools import TOOLS, TOOLS_BY_NAME
from arrt.services.container import Services

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


# -- the break, written down once ------------------------------------------------------
#
# Ruling 3 of 2026-11-19 allows the surface to break once: `work_id` becomes
# `artwork_id` in wall answers and the acts on a wall are gathered in one tool.
# These four tables are the whole of it. Anything
# the recording holds and these do not name must still be there, unchanged: a
# second break, made by accident, fails below by tool, action and name. Adding
# is not breaking (`api-contract.md` § Versioning), so an action, an optional
# argument or a result key the recording lacks passes.

_WALL_ACTS = (
    "activate",
    "hang_selection",
    "not_again",
    "kept_off",
    "allow_again",
    "unhang",
    "scenes",
    "draft_scene",
    "pin_scene",
    "unpin_scene",
    "discard_scene",
    "apply_scene",
    "release_scene",
)
_PLAYER_ACTS = (
    "clients",
    "add_client",
    "rename_client",
    "remove_client",
    "issue_client_token",
    "assign_wall",
    "assign_display",
    "add_label",
    "remove_label",
    "unassign_wall",
)

#: Every action that moved, from (tool, action) to the tool that takes it now, unrenamed.
MOVED: dict[tuple[str, str], str] = {
    **{("art_theme", name): "art_display" for name in _WALL_ACTS},
    **{("art_display", name): "art_players" for name in _PLAYER_ACTS},
}

#: Result keys renamed on every action of the wall tool, old name to new.
RENAMED_ON_THE_WALL_TOOL: dict[str, str] = {"work_id": "artwork_id", "display_plane_has_reported": "has_reported"}

#: Arguments an action no longer takes. `not_again`'s theme scope was `art_theme(action='remove')`.
RETIRED_ARGUMENTS: dict[tuple[str, str], frozenset[str]] = {("art_display", "not_again"): frozenset({"scope"})}

#: Tools the recording does not have. Annotations are part of the frozen surface.
NEW_TOOLS: dict[str, dict[str, bool]] = {"art_players": {"read_only": False, "destructive": True, "open_world": False}}


def _recorded() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _expected_after_the_break(recorded: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Where each recorded action should be now, and what it should take and answer at least."""
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for tool, record in recorded.items():
        for action, entry in record["actions"].items():
            where = (MOVED.get((tool, action), tool), action)
            arguments = {
                name: shape for name, shape in entry["arguments"].items() if name not in RETIRED_ARGUMENTS.get(where, ())
            }
            keys = set(entry["result_keys"])
            if where[0] == "art_display":
                keys = {RENAMED_ON_THE_WALL_TOOL.get(key, key) for key in keys}
            expected[where] = {"arguments": arguments, "result_keys": keys}
    return expected


def _tool_differences(recorded: dict[str, Any], current: dict[str, Any]) -> list[str]:
    found = [f"tool {tool} is gone" for tool in recorded if tool not in current]
    found += [
        f"{tool}'s {flag} was {record[flag]} and is {current[tool][flag]}"
        for tool, record in recorded.items()
        if tool in current
        for flag in ("read_only", "destructive", "open_world")
        if current[tool][flag] != record[flag]
    ]
    found += [
        f"{tool}'s annotations are not the ones the break gave it: {flags}"
        for tool, flags in NEW_TOOLS.items()
        if tool in current and {flag: current[tool][flag] for flag in flags} != flags
    ]
    return found


def _action_differences(tool: str, action: str, entry: dict[str, Any], now: dict[str, Any]) -> list[str]:
    called = f"{tool}(action={action!r})"
    found = [f"{called} no longer takes {name!r}" for name in entry["arguments"] if name not in now["arguments"]]
    found += [
        f"{called}'s {name!r} was {shape} and is {now['arguments'][name]}"
        for name, shape in entry["arguments"].items()
        if name in now["arguments"] and now["arguments"][name] != shape
    ]
    found += [
        f"{called} requires {name!r}, which it did not"
        for name, shape in now["arguments"].items()
        if name not in entry["arguments"] and shape["required"]
    ]
    if missing := sorted(entry["result_keys"] - set(now["result_keys"])):
        found.append(f"{called} no longer answers {missing}")
    return found


def differences(recorded: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Every way `current` departs from the recording beyond the break, by name. Empty when none."""
    found = _tool_differences(recorded, current)
    for (tool, action), entry in _expected_after_the_break(recorded).items():
        now = current.get(tool, {}).get("actions", {}).get(action)
        if now is None:
            found.append(f"{tool}(action={action!r}) is gone")
        else:
            found += _action_differences(tool, action, entry, now)
    found += [
        f"{tool}(action={action!r}) moved to {destination} and is still on {tool}"
        for (tool, action), destination in MOVED.items()
        if action in current.get(tool, {}).get("actions", {})
    ]
    return found


def test_the_surface_is_the_recorded_one_but_for_the_break():
    assert differences(_recorded(), surface_shape()) == []


def test_every_entry_of_the_break_names_something_the_recording_had():
    """A table naming what never existed would read as a considered change to nothing."""
    recorded = _recorded()
    for tool, action in MOVED:
        assert action in recorded[tool]["actions"], (tool, action)
    for (tool, action), names in RETIRED_ARGUMENTS.items():
        origin = next(old for (old, moved), new in MOVED.items() if moved == action and new == tool)
        assert names <= set(recorded[origin]["actions"][action]["arguments"]), (tool, action)
    answered_on_the_wall_tool = {
        key
        for tool, record in recorded.items()
        for action, entry in record["actions"].items()
        if MOVED.get((tool, action), tool) == "art_display"
        for key in entry["result_keys"]
    }
    for old in RENAMED_ON_THE_WALL_TOOL:
        assert old in answered_on_the_wall_tool, old
    assert not set(NEW_TOOLS) & set(recorded)


def test_a_second_break_fails_by_name():
    """The check above, against a surface broken once more on purpose, three ways."""
    recorded = _recorded()
    current = surface_shape()
    current["art_catalogue"]["actions"]["get"]["result_keys"].remove("artwork_id")
    del current["art_theme"]["actions"]["reorder"]["arguments"]["position"]
    current["art_display"]["actions"]["walls"]["arguments"]["wall_id"] = {
        "type": "string",
        "required": True,
        "choices": None,
        "minimum": None,
        "maximum": None,
        "items": None,
    }

    assert sorted(differences(recorded, current)) == [
        "art_catalogue(action='get') no longer answers ['artwork_id']",
        "art_display(action='walls') requires 'wall_id', which it did not",
        "art_theme(action='reorder') no longer takes 'position'",
    ]


def test_no_answer_on_the_wall_tools_says_work_id():
    """No wall answer says `work_id`, over every key every action of both tools can answer.

    `art_display(action='status')`'s `reported` is the one exception, and it is
    not a key here: it is the Player's heartbeat document, passed on in the
    contract's names (`player-contract.md`), so its `display_state.work_id` is
    the Player's word, not this surface's.
    """
    shape = surface_shape()
    saying = sorted(
        f"{tool}(action={action!r})"
        for tool in ("art_display", "art_players")
        for action, entry in shape[tool]["actions"].items()
        if "work_id" in entry["result_keys"] or "display_plane_has_reported" in entry["result_keys"]
    )
    assert saying == []


# -- a caller of an old name is refused, naming the new one ----------------------------


def _dispatch(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Through the server's dispatcher. Every refusal here is made before a service is reached."""
    return dispatch(cast("Services", None), tool, arguments)


@pytest.mark.parametrize(("origin", "destination"), sorted(MOVED.items()), ids=str)
def test_a_moved_action_is_refused_where_it_was_naming_where_it_went(origin, destination):
    tool, action = origin

    refused = _dispatch(tool, {"action": action})

    assert refused["success"] is False
    assert f"call {destination}(action={action!r}) instead" in refused["error"]
    assert refused["moved_to"] == {action: destination}
    assert refused["example"] == f"{destination}(action='help')"
    assert action not in refused["valid_actions"]


@pytest.mark.parametrize(("origin", "destination"), sorted(MOVED.items()), ids=str)
def test_each_tool_says_in_help_where_its_moved_actions_went(origin, destination):
    tool, action = origin

    assert registry.help_payload(TOOLS_BY_NAME[tool])["moved"][action] == destination


@pytest.mark.parametrize("scope", ["theme", "every_wall"])
def test_not_again_with_a_scope_is_refused_naming_the_themes_remove(scope):
    refused = _dispatch("art_display", {"action": "not_again", "wall_id": "w", "artwork_id": "a", "scope": scope})

    assert refused["success"] is False
    assert refused["error"].startswith("art_display(action='not_again') no longer takes 'scope':")
    assert "art_theme(action='remove'" in refused["error"]


#: Every action that takes a Library work as `artwork_id` and names `work_id` when sent it.
#: Written out, not derived, so an action that stops refusing it fails here.
_TAKES_ARTWORK_ID = {
    ("art_display", "show_now"),
    ("art_display", "not_again"),
    ("art_display", "allow_again"),
    ("art_display", "pin_scene"),
    ("art_theme", "add"),
    ("art_theme", "remove"),
    ("art_theme", "reorder"),
}


def test_the_actions_that_name_artwork_id_for_work_id_are_these():
    declared = {(tool.name, action.name) for tool in TOOLS for action in tool.actions if "work_id" in action.retired}
    assert declared == _TAKES_ARTWORK_ID


@pytest.mark.parametrize(("tool", "action"), sorted(_TAKES_ARTWORK_ID))
def test_work_id_sent_for_a_library_work_is_refused_naming_artwork_id(tool, action):
    refused = _dispatch(tool, {"action": action, "work_id": "wrk_1"})

    assert refused["success"] is False
    assert refused["error"].startswith(f"{tool}(action={action!r}) no longer takes 'work_id':")
    assert "Send it as artwork_id." in refused["error"]


def test_a_move_to_a_tool_that_does_not_take_it_stops_the_import(monkeypatch):
    from arrt.mcp import tools

    stray = registry.ToolRecord(
        name="art_stray",
        title="Stray",
        summary="s",
        read_only=True,
        destructive=False,
        open_world=False,
        moved={"sculpt": "art_theme"},
    )
    monkeypatch.setattr(tools, "TOOLS", (*tools.TOOLS, stray))

    with pytest.raises(registry.RegistryError, match="'sculpt' moved to art_theme, which does not take it"):
        tools._check_every_move_lands()


def test_a_tool_cannot_both_take_an_action_and_record_it_as_moved():
    with pytest.raises(registry.RegistryError, match="records them as moved away"):
        registry.ToolRecord(
            name="art_x",
            title="X",
            summary="s",
            read_only=True,
            destructive=False,
            open_world=False,
            actions=(registry.Action(name="walls", description="d", example="art_x(action='walls')"),),
            moved={"walls": "art_display"},
        )


def test_an_action_cannot_both_take_an_argument_and_retire_it():
    with pytest.raises(registry.RegistryError, match="both takes and retires"):
        registry.Action(
            name="a",
            description="d",
            example="e",
            params=(registry.Param(name="scope", type="string", description="d"),),
            retired={"scope": "gone"},
        )
