"""What `DisplayService` guaranteed before it became a facade over five collaborators, held after.

On 2026-11-19 (audit wave 2, chunks 20 and 21, #382) everything `DisplayService`
did moved, verbatim, into `FeedPublisher` (`feeds.py`), `Themes` (`themes.py`),
`Walls` (`walls.py`), `Scenes` (`scenes.py`) and `Reports` (`reports.py`), and
`DisplayService` (`display.py`) became the composition facade every surface
calls. A move like that keeps every test green while silently changing what
nobody wrote down, so what it must not change is held here:

- every public name the class had, with its signature (`BEFORE`, taken from the
  class on chunk 21's base and written in once, so a name dropped or a
  parameter renamed fails here rather than at a surface that calls it);
- each delegation hands every argument, by name, to the collaborator that holds
  the method, and returns what it returns;
- one store and one publisher under all of them, so one act has one
  transaction and one set of staged feeds (`FeedPublisher.publishing`);
- every name callers imported from `display.py` still imports from there, and
  is the collaborator's own object rather than a copy;
- every module says its lines under `arrt.programming.display`, the logger the
  journal's readers filter on.

On 2026-11-20 (audit wave 2b, Chunk 48) the existence-checking lookups left
`FeedPublisher` for a home of their own (`Lookups`, `lookups.py`), every
collaborator and the facade calling the one instance the facade builds, and
`DisplaySettings` left `display.py` for `settings.py`. What the lookups guaranteed
as the publisher's methods is held at the end of this file.
"""

import ast
import contextlib
import inspect
import logging
from annotationlib import Format
from datetime import UTC, datetime
from pathlib import Path

import pytest

from arrt.persistence.records import Wall
from arrt.programming import display as display_module
from arrt.programming import feeds as feeds_module
from arrt.programming import lookups as lookups_module
from arrt.programming import reports as reports_module
from arrt.programming import scenes as scenes_module
from arrt.programming import settings as settings_module
from arrt.programming import themes as themes_module
from arrt.programming import walls as walls_module
from arrt.programming.display import UNSET, DisplayService
from arrt.programming.lookups import Lookups
from arrt.services.errors import NotFound, ServiceError

#: `DisplayService`'s public methods on chunk 21's base (c1915a9e), with their
#: signatures as `inspect.signature` spells them, annotations as written and the
#: `UNSET` default as `UNSET`. Written once from the class itself.
BEFORE = {
    "activate_theme": "(self, theme_id: 'str', *, wall_id: 'str') -> 'ManifestBuild'",
    "add_theme": "(self, *, name: 'str', description: 'str | None' = None) -> 'Theme'",
    "add_to_theme": "(self, *, theme_id: 'str', artwork_id: 'str', position: 'int | None' = None) -> 'ThemeMembership'",
    "add_wall": "(self, *, name: 'str') -> 'Wall'",
    "add_works_to_theme": "(self, *, theme_id: 'str', artwork_ids: 'Sequence[str]') -> 'tuple[int, int]'",
    "allow_work": "(self, artwork_id: 'str') -> 'None'",
    "apply_scene": "(self, scene_id: 'str', *, lifetime: 'SceneLifetime | str', minutes: 'int | None' = None) -> 'SceneView'",
    "build_manifest": "(self, wall_id: 'str', theme_id: 'str | None' = None) -> 'ManifestBuild'",
    "catch_up_offers": "(self) -> 'Sequence[str]'",
    "clear_wall": "(self, wall_id: 'str') -> 'None'",
    "default_theme": "(self) -> 'Theme | None'",
    "delete_theme": "(self, theme_id: 'str') -> 'None'",
    "delete_wall": "(self, wall_id: 'str') -> 'Wall'",
    "discard_scene": "(self, scene_id: 'str') -> 'None'",
    "draft_scene": "(self) -> 'SceneView'",
    "exclude_work": "(self, artwork_id: 'str', *, wall_id: 'str | None' = None) -> 'WorkExclusion'",
    "excluded_works": "(self) -> 'Sequence[WorkExclusion]'",
    "get_listed_theme": "(self, theme_id: 'str') -> 'Theme'",
    "get_scene": "(self, scene_id: 'str') -> 'SceneView'",
    "get_theme": "(self, theme_id: 'str') -> 'Theme'",
    "get_wall": "(self, wall_id: 'str') -> 'Wall'",
    "get_wall_view": "(self, wall_id: 'str') -> 'WallView'",
    "hang_selection": "(self, artwork_ids: 'Sequence[str]', *, wall_id: 'str') -> 'ManifestBuild'",
    "hanging_on": "(self, wall_id: 'str') -> 'Theme | None'",
    "judge_sizes": "(self, wall_id: 'str') -> 'SizeJudgement'",
    "keep_showing": "(self, wall_id: 'str', reported: 'ReportedState', *, at: 'datetime') -> 'None'",
    "largest_screen": "(self, wall_id: 'str') -> 'tuple[int, int] | None'",
    "last_showing": "(self, wall_id: 'str') -> 'Showing | None'",
    "last_shown_by_work": "(self) -> 'Mapping[str, datetime]'",
    "leave_theme": "(self, artwork_id: 'str', *, wall_id: 'str') -> 'Theme'",
    "list_themes": "(self) -> 'Sequence[Theme]'",
    "live_scene": "(self) -> 'SceneView | None'",
    "make_default": "(self, theme_id: 'str') -> 'Theme'",
    "move_in_theme": "(self, *, theme_id: 'str', artwork_id: 'str', position: 'int | None') -> 'ThemeMembership'",
    "not_this_one_again": "(self, artwork_id: 'str', *, wall_id: 'str', scope: 'NotAgainScope | str') -> 'NotAgain'",
    "offer_destinations": "(self, work_ids: 'Iterable[str]') -> 'Sequence[str]'",
    "on_work_changed": "(self, event: 'WorkChanged') -> 'None'",
    "pace": "(self, wall: 'Wall') -> 'tuple[int, bool]'",
    "pin_scene": "(self, scene_id: 'str', wall_id: 'str', artwork_id: 'str') -> 'SceneView'",
    "placements_of": "(self, artwork_id: 'str') -> 'WorkPlacements'",
    "published_manifest_v2": "(self, wall_id: 'str') -> 'bytes | None'",
    "reconcile": "(self, work_ids: 'Iterable[str] | None' = None, *, cause: 'str' = 'startup') -> 'Reconciliation'",
    "record_heartbeat": "(self, wall_id: 'str', document: 'dict[str, Any]') -> 'None'",
    "release_scene": "(self, scene_id: 'str') -> 'SceneView'",
    "remove_from_theme": "(self, *, theme_id: 'str', artwork_id: 'str') -> 'None'",
    "remove_works_from_theme": "(self, *, theme_id: 'str', artwork_ids: 'Sequence[str]') -> 'Sequence[str]'",
    "rename_wall": "(self, wall_id: 'str', *, name: 'str') -> 'Wall'",
    "scene_draft": "(self) -> 'SceneView | None'",
    "scene_walls": "(self, view: 'SceneView') -> 'list[SceneWall]'",
    "set_mat_mode": "(self, wall_id: 'str', mode: 'MatMode | str | None') -> 'Wall'",
    "set_playback": (
        "(self, wall_id: 'str', *, rotation_interval_seconds: 'int | Unset | None' = UNSET, "
        "shuffle: 'bool | Unset | None' = UNSET, tallest: 'str | Unset | None' = UNSET, "
        "widest: 'str | Unset | None' = UNSET) -> 'Wall'"
    ),
    "show_work_now": "(self, wall_id: 'str', artwork_id: 'str') -> 'str'",
    "size_judgements": "(self, theme_id: 'str') -> 'Mapping[str, SizeJudgement]'",
    "step_display": "(self, wall_id: 'str') -> 'str'",
    "survey_themes": "(self) -> 'Sequence[ThemePlacement]'",
    "survey_wall_status": "(self) -> 'Sequence[WallHeartbeat]'",
    "survey_walls": "(self) -> 'Sequence[WallView]'",
    "sync": "(self, wall_id: 'str') -> 'ManifestBuild'",
    "theme_counts": "(self, work_ids: 'Iterable[str]', *, selected: 'str | None' = None) -> 'Sequence[ThemeCount]'",
    "theme_work_ids": "(self, theme_id: 'str') -> 'Sequence[str]'",
    "too_small_for_walls": "(self, theme_id: 'str') -> 'Mapping[str, Sequence[str]]'",
    "too_small_on": "(self, wall_id: 'str') -> 'frozenset[str]'",
    "unpin_scene": "(self, scene_id: 'str', wall_id: 'str') -> 'SceneView'",
    "update_theme": (
        "(self, theme_id: 'str', *, name: 'str | None' = None, description: 'str | Unset | None' = UNSET) -> 'Theme'"
    ),
    "walls_hanging": "(self, theme_id: 'str') -> 'Sequence[Wall]'",
    "work_ids_on_walls": "(self) -> 'frozenset[str]'",
}

#: Every public module-level name `display.py` had on chunk 21's base, by the
#: module it lives in now. `DisplayService` stayed; `DisplaySettings` moved to
#: `settings.py` in 2b's Chunk 48.
IMPORTED_FROM_DISPLAY = {
    display_module: ["DisplayService"],
    settings_module: ["DisplaySettings"],
    themes_module: ["Unset", "UNSET", "ThemeCount", "ThemePlacement", "WorkPlacements", "NotAgainScope", "NotAgain"],
    walls_module: [
        "MatMode",
        "PLAYERS_OWN_MAT",
        "SHUFFLED",
        "IN_ORDER",
        "DEFAULT_SHUFFLE",
        "SHUFFLE_CHOICES",
        "WallView",
        "feed_notice",
        "UPCOMING",
    ],
    scenes_module: ["SceneView", "SceneWall", "PREVIEW_MINUTES", "MAX_PREVIEW_MINUTES"],
    reports_module: ["Unjudged", "SizeJudgement", "WallHeartbeat", "describe_wall_status", "SCREEN_MEMORY", "SCREEN_REFRESH"],
}

#: The collaborators the facade composes, by the attribute it holds each in.
COLLABORATORS = ("_lookups", "_feeds", "_themes", "_walls", "_scenes", "_reports")


class _Spelled:
    def __repr__(self) -> str:
        return "UNSET"


def _spelled(function) -> str:
    signature = inspect.signature(function, annotation_format=Format.STRING)
    return str(
        signature.replace(
            parameters=[
                parameter.replace(default=_Spelled()) if parameter.default is UNSET else parameter
                for parameter in signature.parameters.values()
            ]
        )
    )


def _public(cls) -> dict[str, str]:
    return {name: _spelled(member) for name, member in vars(cls).items() if not name.startswith("_") and callable(member)}


def test_every_public_name_the_service_had_is_still_there_with_its_signature():
    assert _public(DisplayService) == BEFORE


@pytest.mark.parametrize("module", IMPORTED_FROM_DISPLAY, ids=lambda module: module.__name__.rsplit(".", 1)[-1])
def test_every_name_callers_import_from_display_is_the_collaborators_own(module):
    for name in IMPORTED_FROM_DISPLAY[module]:
        assert getattr(display_module, name) is getattr(module, name), f"display.{name} is not {module.__name__}.{name}"
        assert name in display_module.__all__, f"display.py does not export {name}"


def test_display_py_holds_only_the_facade_and_defines_none_of_what_it_re_exports():
    """A copy of a constant or type left in `display.py` would be a second owner; `is` cannot see one for a small int."""
    tree = ast.parse(Path(display_module.__file__).read_text(encoding="utf-8"))
    defined = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, (ast.AnnAssign, ast.TypeAlias)):
            defined.add(node.target.id if isinstance(node, ast.AnnAssign) else node.name.id)
    assert defined == {"DisplayService", "__all__"}


def test_one_store_and_one_publisher_under_every_collaborator(display, store):
    """One act is one transaction and one set of staged feeds only while every collaborator shares them.

    The store is found through the collaborators: the facade keeps none of its
    own since 2b's Chunk 48, so it is the one the services were bound with.
    """
    for attribute in COLLABORATORS:
        collaborator = getattr(display, attribute)
        assert collaborator._store is store, f"{attribute} has a store of its own"
        if attribute not in ("_lookups", "_feeds"):
            assert collaborator._feeds is display._feeds, f"{attribute} publishes through a publisher of its own"
        if attribute != "_lookups":
            assert collaborator._lookups is display._lookups, f"{attribute} looks walls up through lookups of its own"
        for other in COLLABORATORS:
            if hasattr(collaborator, other):
                assert getattr(collaborator, other) is getattr(display, other), f"{attribute}.{other} is not the facade's"


def test_the_facade_keeps_no_store_library_or_settings_of_its_own(display):
    """C19: it set `_store`, `_library` and `_settings` and read none; what it holds now is its collaborators."""
    assert set(vars(display)) == set(COLLABORATORS)


class _Recorder:
    """A collaborator that answers every method with a token, and records what it was handed."""

    def __init__(self, real, calls: list) -> None:
        self._real = real
        self._calls = calls

    def __getattr__(self, name: str):
        held = getattr(self._real, name)

        def answer(*args, **keywords):
            bound = inspect.signature(held).bind(*args, **keywords)
            self._calls.append((self, name, dict(bound.arguments)))
            return ("answered", name)

        return answer


@pytest.mark.parametrize("name", sorted(set(BEFORE) - {"on_work_changed"}))
def test_each_delegation_hands_every_argument_to_the_collaborator_holding_it_and_returns_its_answer(display, name):
    """`on_work_changed` is the facade's own rule, not a delegation; `test_feed_publisher` holds it."""
    holders = [attribute for attribute in COLLABORATORS if hasattr(type(getattr(display, attribute)), name)]
    assert len(holders) == 1, f"{name} is held by {holders}, so which one the facade should call is not one answer"
    calls: list = []
    recorders = {attribute: _Recorder(getattr(display, attribute), calls) for attribute in COLLABORATORS}
    for attribute, recorder in recorders.items():
        setattr(display, attribute, recorder)
    parameters = list(inspect.signature(getattr(DisplayService, name)).parameters.values())[1:]
    given = {parameter.name: object() for parameter in parameters}
    positional = [given[p.name] for p in parameters if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD]
    keywords = {p.name: given[p.name] for p in parameters if p.kind is inspect.Parameter.KEYWORD_ONLY}

    answer = getattr(display, name)(*positional, **keywords)

    assert calls == [(recorders[holders[0]], name, given)]
    returns_none = inspect.signature(getattr(DisplayService, name), annotation_format=Format.STRING).return_annotation
    assert answer == (None if returns_none == "None" else ("answered", name))


@pytest.mark.parametrize(
    "module",
    [
        display_module,
        feeds_module,
        themes_module,
        walls_module,
        scenes_module,
        reports_module,
        lookups_module,
        settings_module,
    ],
    ids=lambda module: module.__name__.rsplit(".", 1)[-1],
)
def test_every_module_s_lines_are_said_under_the_display_logger(module):
    """By name, so the journal's filters keep reading every line a wall's programming says."""
    log = getattr(module, "log", None)
    assert log is None or log.name == "arrt.programming.display", f"{module.__name__} logs under {log.name}"


def test_a_line_from_each_collaborator_reaches_the_journal_under_the_display_logger(display, ready_work, wall_id, caplog):
    """One line said by each of themes, walls, scenes and reports, read back by its record's logger name."""
    shown, stranger = ready_work("Dalí"), ready_work("Ernst")
    theme = display.add_theme(name="Surrealism")
    display.add_to_theme(theme_id=theme.id, artwork_id=shown.id)
    display.activate_theme(theme.id, wall_id=wall_id)

    with caplog.at_level(logging.INFO):
        display.rename_wall(wall_id, name="The hall")  # walls
        draft = display.draft_scene()
        display.pin_scene(draft.scene.id, wall_id, shown.id)  # scenes
        now = datetime.now(UTC).isoformat()
        display.record_heartbeat(  # reports: a work the feed does not carry
            wall_id,
            {
                "schema": {"major": 1, "minor": 3},
                "reported_at": now,
                "display_state": {"state": "showing_art", "work_id": stranger.id, "since": now},
            },
        )
        display.clear_wall(wall_id)  # themes

    said = {
        "walls": [r for r in caplog.records if "is now called" in r.getMessage()],
        "scenes": [r for r in caplog.records if getattr(r, "event", None) == "scene.staged"],
        "reports": [r for r in caplog.records if getattr(r, "event", None) == "showings.not_in_feed"],
        "themes": [r for r in caplog.records if r.getMessage().startswith("Took theme")],
    }
    assert all(said.values()), {where: len(lines) for where, lines in said.items()}
    assert {where: {r.name for r in lines} for where, lines in said.items()} == {
        where: {"arrt.programming.display"} for where in said
    }


# -- the lookups' one home (Chunk 48, C9) ---------------------------------------------------

#: The existence-checking lookups, which `Lookups` alone defines.
LOOKUPS = ("get_wall", "get_theme", "require_hanging", "current_draft")
#: The modules of the facade and its collaborators.
COMPOSED = (display_module, feeds_module, themes_module, walls_module, scenes_module, reports_module)


def _lookups_defined_outside(sources):
    """Each `module.Class.name` defining a lookup outside `Lookups`, but for the facade's own one-line delegations to it."""
    found = []
    for module, source in sources.items():
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.ClassDef):
                continue
            for method in node.body:
                if not isinstance(method, ast.FunctionDef) or method.name not in LOOKUPS:
                    continue
                if node.name == "DisplayService" and _delegates_to_lookups(method):
                    continue
                found.append(f"{module}.{node.name}.{method.name}")
    return found


def _delegates_to_lookups(method):
    """Whether the body, past its docstring, is `return self._lookups.<the same name>(…)` and nothing else."""
    body = [statement for statement in method.body if not isinstance(statement, ast.Expr)]
    if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
        return False
    called = body[0].value.func
    return (
        isinstance(called, ast.Attribute)
        and called.attr == method.name
        and isinstance(called.value, ast.Attribute)
        and called.value.attr == "_lookups"
    )


def _sources():
    return {module.__name__.rsplit(".", 1)[-1]: Path(module.__file__).read_text(encoding="utf-8") for module in COMPOSED}


def test_no_collaborator_but_the_lookups_defines_a_wall_or_theme_lookup():
    """Acceptance 3 of Chunk 48: one home, so a change to what a lookup raises (Chunk 37) is made once."""
    assert _lookups_defined_outside(_sources()) == []
    assert {name for name in LOOKUPS if callable(getattr(Lookups, name, None))} == set(LOOKUPS)


def test_a_lookup_planted_in_a_collaborator_is_found():
    """The check above, shown able to fail: one lookup planted back on the publisher, and one facade method that does more."""
    sources = _sources()
    sources["feeds"] = sources["feeds"].replace(
        "class FeedPublisher:\n",
        "class FeedPublisher:\n    def get_wall(self, wall_id):\n        return self._store.get_wall(wall_id)\n",
        1,
    )
    sources["display"] = sources["display"].replace(
        "return self._lookups.get_theme(theme_id)", "return self._feeds.get_theme(theme_id)", 1
    )

    assert _lookups_defined_outside(sources) == ["display.DisplayService.get_theme", "feeds.FeedPublisher.get_wall"]


def test_the_refusals_are_the_lookups_sentences_word_for_word(services, display, wall_id):
    """Implicit guarantee: the sentences a person and an agent read, and the error class each is raised as.

    A wall or theme that is not there is `NotFound` (Chunk 37: 404 on `/api`, a
    `ServiceError` to everything else); a wall with nothing hanging is a plain
    `ServiceError`, because the wall is there.
    """
    with pytest.raises(ServiceError) as wall:
        display.get_wall("nowhere")
    with pytest.raises(ServiceError) as theme:
        display.get_theme("nothing")
    with pytest.raises(ServiceError) as hanging:
        display.leave_theme("any-work", wall_id=wall_id)

    assert type(wall.value) is NotFound
    assert type(theme.value) is NotFound
    assert type(hanging.value) is ServiceError
    assert str(wall.value) == "No wall with id 'nowhere' is recorded."
    assert str(theme.value) == "No theme with id 'nothing' is recorded."
    name = display.get_wall(wall_id).name
    assert str(hanging.value) == (f"Nothing is hanging on {name!r}, so there is nothing to put on it. Hang a theme there first.")


def test_the_clients_wall_refusal_is_the_lookups_own(services, display):
    """One owner for the sentence: `ClientService` refuses a wall it does not hold exactly as the lookups do."""
    client = services.clients.add_client(name="Hall Pi")
    with pytest.raises(ServiceError) as from_clients:
        services.clients.assign_wall("nowhere", client_id=client.id, output="hdmi-a-1")
    with pytest.raises(ServiceError) as from_lookups:
        display.get_wall("nowhere")

    assert type(from_clients.value) is type(from_lookups.value)
    assert str(from_clients.value) == str(from_lookups.value) == lookups_module.no_wall("nowhere")


def test_a_lookup_answers_from_inside_the_callers_transaction(display, store):
    """Implicit guarantee: a lookup reads the one store on the caller's thread, so it sees what the caller's act wrote."""
    wall = Wall(id="written-just-now", name="The landing", created_at=datetime.now(UTC))
    seen = []

    def act() -> None:
        with store.transaction():
            store.add_wall(wall)
            seen.append(display._lookups.get_wall(wall.id))
            raise RuntimeError("roll the act back")

    with pytest.raises(RuntimeError):
        act()

    assert seen == [wall]
    with pytest.raises(ServiceError, match="No wall with id 'written-just-now'"):
        display._lookups.get_wall(wall.id)


def test_a_lookup_replaced_on_the_facade_reaches_every_collaborator(display, ready_work, wall_id, monkeypatch):
    """Implicit guarantee: one object answers them all, as the publisher did, so one patch reaches every call."""
    theme = display.add_theme(name="Hung")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work("On the wall").id)
    display.activate_theme(theme.id, wall_id=wall_id)
    draft = display.draft_scene()
    real = display._lookups.get_wall
    asked: list[str] = []

    def counted(wall):
        asked.append(wall)
        return real(wall)

    monkeypatch.setattr(display._lookups, "get_wall", counted)
    acts = {
        "facade": lambda: display.get_wall(wall_id),
        "feeds": lambda: display.build_manifest(wall_id),
        "themes": lambda: display.leave_theme("not-in-it", wall_id=wall_id),
        "walls": lambda: display.rename_wall(wall_id, name="The hall"),
        "scenes": lambda: display.unpin_scene(draft.scene.id, wall_id),
        "reports": lambda: display.last_showing(wall_id),
    }
    reached = {}
    for where, act in acts.items():
        asked.clear()
        with contextlib.suppress(ServiceError):
            act()
        reached[where] = wall_id in asked

    assert reached == dict.fromkeys(acts, True)


def test_display_settings_is_one_class_imported_from_either_module():
    """Acceptance 4 of Chunk 48: moved, and re-exported as the same object, so `__main__` and the container still build it."""
    assert display_module.DisplaySettings is settings_module.DisplaySettings
    assert settings_module.DisplaySettings.__module__ == "arrt.programming.settings"
