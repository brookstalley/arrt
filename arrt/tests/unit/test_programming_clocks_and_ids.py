"""Programming's collaborators stamp what they write by the clock and ids they were given, and one owner says what is kept off.

Each collaborator takes a clock and an id source, each defaulting to the machine's, so
every construction site is unchanged and a test can say what time it is. Each case below
builds one collaborator over its own clock (an hour of its own) and its own id source
(a prefix of its own), calls one act through it, and reads every record the act wrote back
from the store. A record must carry an instant that clock gave and an id that source
minted: an instant from another collaborator's clock, or the machine's, is the defect this
refuses. **An act reads its clock once**, so the same cases count the readings.

Built from the collaborators directly rather than through `DisplayService`, because the
facade is what hands them one clock: one case at the end builds it and follows one clock
and one source through every collaborator it composes.

The second half is two guards over `arrt/src`: the store's exclusions are read by the
owner (`Lookups`) and nowhere else, and the machine's clock and `uuid4` are read by the
two defaults and nowhere else in Programming.
"""

import ast
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import arrt
from arrt.persistence.records import SceneLifetime
from arrt.programming.access import PlayerAccess
from arrt.programming.clients import ClientService, refused_reports_of
from arrt.programming.display import DisplayService
from arrt.programming.feeds import FeedPublisher
from arrt.programming.lookups import Lookups, machine_now, new_id
from arrt.programming.reports import Reports
from arrt.programming.scenes import Scenes
from arrt.programming.themes import Themes
from arrt.programming.walls import Walls

_DAY = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class Ticks:
    """A clock that answers a later second of its own hour on every reading, and remembers each.

    Given a `probe`, it also remembers what the probe said at each reading: whether the
    store's lock was held when the act read its instant.
    """

    hour: int
    read: list[datetime] = field(default_factory=list)
    probe: Callable[[], bool] | None = None
    held: list[bool] = field(default_factory=list)

    def __call__(self) -> datetime:
        instant = _DAY + timedelta(hours=self.hour, seconds=len(self.read) + 1)
        self.read.append(instant)
        if self.probe is not None:
            self.held.append(self.probe())
        return instant


@dataclass
class Names:
    """An id source whose ids say whose they are."""

    prefix: str
    minted: list[str] = field(default_factory=list)

    def __call__(self) -> str:
        minted = f"{self.prefix}-{len(self.minted) + 1:04d}"
        self.minted.append(minted)
        return minted


@dataclass
class Stack:
    """Every collaborator `DisplayService` composes, each over a clock and an id source of its own."""

    feeds: FeedPublisher
    themes: Themes
    walls: Walls
    scenes: Scenes
    reports: Reports
    clients: ClientService
    access: PlayerAccess
    clocks: dict[str, Ticks]
    ids: dict[str, Names]


@pytest.fixture
def stack(store, services, wall_settings) -> Stack:
    clocks = {
        name: Ticks(hour) for hour, name in enumerate(("feeds", "themes", "walls", "scenes", "reports", "clients", "access"), 1)
    }
    ids = {name: Names(name) for name in ("themes", "walls", "scenes", "clients")}
    lookups = Lookups(store)
    library = services.library
    feeds = FeedPublisher(store, library, wall_settings, lookups, now=clocks["feeds"])
    themes = Themes(store, library, lookups, feeds, now=clocks["themes"], mint_id=ids["themes"])
    walls = Walls(store, wall_settings, lookups, feeds, themes, now=clocks["walls"], mint_id=ids["walls"])
    scenes = Scenes(store, library, wall_settings, lookups, feeds, themes, walls, now=clocks["scenes"], mint_id=ids["scenes"])
    reports = Reports(store, wall_settings, lookups, feeds, themes, walls, scenes, now=clocks["reports"])
    clients = ClientService(store, wall_settings, library, now=clocks["clients"], mint_id=ids["clients"])
    access = PlayerAccess(store, clients.placements, now=clocks["access"])
    return Stack(feeds, themes, walls, scenes, reports, clients, access, clocks, ids)


def _generated_at(settings, wall_id: str) -> str:
    return json.loads(settings.manifest_v2_path(wall_id).read_text(encoding="utf-8"))["generated_at"]


def _once(clock: Ticks) -> datetime:
    """The one instant the clock gave, failing when an act read it more than once or not at all."""
    assert len(clock.read) == 1, f"the act read the clock {len(clock.read)} times: {clock.read}"
    return clock.read[0]


def _fresh(clock: Ticks) -> None:
    clock.read.clear()


# -- the defaults are the machine's -------------------------------------------------------


def test_a_collaborator_handed_neither_reads_the_machine(store, services, wall_settings):
    before = datetime.now(UTC)
    lookups = Lookups(store)
    feeds = FeedPublisher(store, services.library, wall_settings, lookups)
    themes = Themes(store, services.library, lookups, feeds)
    walls = Walls(store, wall_settings, lookups, feeds, themes)

    wall = walls.add_wall(name="Machine's")

    assert before <= wall.created_at <= datetime.now(UTC)
    assert before <= machine_now() <= datetime.now(UTC)
    assert str(uuid.UUID(wall.id)) == wall.id
    assert len({new_id() for _ in range(5)}) == 5


# -- themes -------------------------------------------------------------------------------


def test_a_theme_carries_the_clock_and_the_id_it_was_given(stack, store):
    theme = stack.themes.add_theme(name="Quiet")

    stored = store.get_theme(theme.id)
    assert (stored.id, stored.created_at) == (stack.ids["themes"].minted[0], _once(stack.clocks["themes"]))
    assert stack.ids["themes"].minted == [theme.id]


def test_a_selection_is_one_instant_and_one_id_on_everything_it_writes(stack, store, ready_work, wall_id):
    work = ready_work("Nighthawks")

    stack.themes.hang_selection([work.id], wall_id=wall_id)

    instant = _once(stack.clocks["themes"])
    assignment = store.get_assignment(wall_id)
    theme = store.get_theme(assignment.theme_id)
    (membership,) = store.list_memberships(theme.id)
    assert stack.ids["themes"].minted == [theme.id]
    assert (theme.created_at, membership.added_at, assignment.assigned_at) == (instant, instant, instant)


def test_a_hang_carries_the_themes_clock(stack, store, wall_id):
    theme = stack.themes.add_theme(name="Quiet")
    _fresh(stack.clocks["themes"])

    stack.themes.activate_theme(theme.id, wall_id=wall_id)

    assert store.get_assignment(wall_id).assigned_at == _once(stack.clocks["themes"])


def test_a_work_joins_a_theme_at_the_clock_and_many_join_at_one_instant(stack, store, ready_work):
    theme = stack.themes.add_theme(name="Quiet")
    first, second, third = ready_work("One"), ready_work("Two"), ready_work("Three")
    _fresh(stack.clocks["themes"])

    stack.themes.add_to_theme(theme_id=theme.id, artwork_id=first.id)
    assert [m.added_at for m in store.list_memberships(theme.id)] == [_once(stack.clocks["themes"])]

    _fresh(stack.clocks["themes"])
    stack.themes.add_works_to_theme(theme_id=theme.id, artwork_ids=[second.id, third.id])
    instant = _once(stack.clocks["themes"])
    assert {m.artwork_id: m.added_at for m in store.list_memberships(theme.id)}[second.id] == instant
    assert {m.artwork_id: m.added_at for m in store.list_memberships(theme.id)}[third.id] == instant


def test_a_work_kept_off_is_stamped_by_the_clock(stack, store, ready_work):
    work = ready_work("Nighthawks")
    _fresh(stack.clocks["themes"])

    stack.themes.exclude_work(work.id)

    assert [kept.excluded_at for kept in store.list_exclusions()] == [_once(stack.clocks["themes"])]


def test_every_work_offered_in_one_act_is_offered_at_one_instant(stack, store, ready_work, monkeypatch):
    works = [ready_work(title) for title in ("One", "Two", "Three")]
    stack.themes.make_default(stack.themes.add_theme(name="Default").id)
    offered: dict[str, datetime] = {}
    # The services' own display offered each work when it was accepted; say none was, so this one does.
    monkeypatch.setattr(store, "offered_work_ids", set)
    monkeypatch.setattr(store, "record_offer", offered.__setitem__)
    _fresh(stack.clocks["themes"])

    stack.themes.offer_destinations([work.id for work in works])

    assert set(offered) == {work.id for work in works}
    assert set(offered.values()) == {_once(stack.clocks["themes"])}


# -- walls --------------------------------------------------------------------------------


def test_a_wall_carries_the_clock_and_the_id_it_was_given(stack, store):
    wall = stack.walls.add_wall(name="Study")

    stored = next(found for found in store.list_walls() if found.id == wall.id)
    assert (stored.id, stored.created_at) == (stack.ids["walls"].minted[0], _once(stack.clocks["walls"]))
    assert stack.ids["walls"].minted == [wall.id]


def test_a_wall_survey_counts_the_upcoming_slots_from_one_instant(stack, wall_id, ready_work):
    stack.themes.hang_selection([ready_work("Nighthawks").id], wall_id=wall_id)
    stack.walls.add_wall(name="Study")
    _fresh(stack.clocks["walls"])

    stack.walls.survey_walls()

    assert len(stack.clocks["walls"].read) == 1


# -- scenes -------------------------------------------------------------------------------


@pytest.fixture
def hung(stack, ready_work, wall_id):
    """A wall with a work hanging and a feed published, which a scene can be pinned over."""
    work = ready_work("Nighthawks")
    stack.themes.hang_selection([work.id], wall_id=wall_id)
    return work


def test_a_draft_carries_the_clock_and_the_id_it_was_given(stack, store):
    draft = stack.scenes.draft_scene().scene

    stored = store.get_scene(draft.id)
    assert (stored.id, stored.created_at) == (stack.ids["scenes"].minted[0], _once(stack.clocks["scenes"]))


def test_applying_and_releasing_are_each_one_instant(stack, store, hung, wall_id):
    draft = stack.scenes.draft_scene().scene
    stack.scenes.pin_scene(draft.id, wall_id, hung.id)
    _fresh(stack.clocks["scenes"])

    stack.scenes.apply_scene(draft.id, lifetime=SceneLifetime.PREVIEW, minutes=5)

    # The act's one instant, then the answer's own reading of the scene it returns.
    applied = store.get_scene(draft.id)
    started, _answer = stack.clocks["scenes"].read
    assert (applied.starts_at, applied.until) == (started, started + timedelta(minutes=5))

    _fresh(stack.clocks["scenes"])
    stack.scenes.release_scene(draft.id)
    released, _answer = stack.clocks["scenes"].read
    assert store.get_scene(draft.id).ended_at == released


def test_a_scene_is_judged_live_by_the_scenes_clock(stack, hung, wall_id):
    draft = stack.scenes.draft_scene().scene
    stack.scenes.pin_scene(draft.id, wall_id, hung.id)
    stack.scenes.apply_scene(draft.id, lifetime=SceneLifetime.PREVIEW, minutes=5)
    _fresh(stack.clocks["scenes"])

    live = stack.scenes.live_scene()

    assert live is not None
    assert len(stack.clocks["scenes"].read) == 1
    # A clock that has run past the preview's end finds the same scene ended.
    stack.clocks["scenes"].hour += 1
    assert stack.scenes.live_scene() is None


# -- feeds --------------------------------------------------------------------------------


def test_a_feed_says_it_was_generated_at_the_one_instant_its_act_read(stack, wall_settings, ready_work, wall_id):
    work = ready_work("Nighthawks")
    _fresh(stack.clocks["feeds"])

    stack.themes.hang_selection([work.id], wall_id=wall_id)

    instant = _once(stack.clocks["feeds"])
    assert _generated_at(wall_settings, wall_id) == instant.isoformat()


# -- reports ------------------------------------------------------------------------------


def _beat(width: int, height: int) -> dict:
    return {
        "schema": {"major": 1, "minor": 2},
        "reported_at": "2026-01-01T00:00:00+00:00",
        "current_work_id": None,
        "capabilities": {
            "screen": {"width_px": width, "height_px": height},
            "backend": "framebuffer",
            "label_modes": ["none"],
            "manifest_majors": [2, 1],
        },
    }


def test_a_heartbeat_is_one_instant_for_the_screen_it_keeps_and_the_scenes_it_settles(stack, store, hung, wall_id):
    client = stack.clients.add_client(name="Pi")
    stack.access.issue(client.id)
    placed = stack.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    _fresh(stack.clocks["reports"])

    stack.reports.record_heartbeat(wall_id, _beat(3840, 2160))

    instant = _once(stack.clocks["reports"])
    assert store.reported_screens(placed.display.id) == [(3840, 2160, instant)]


# -- clients ------------------------------------------------------------------------------


def test_a_client_carries_the_clock_and_the_id_it_was_given(stack, store):
    client = stack.clients.add_client(name="Pi")

    stored = store.get_client(client.id)
    assert (stored.id, stored.created_at) == (stack.ids["clients"].minted[0], _once(stack.clocks["clients"]))


def test_a_display_recorded_by_assigning_a_wall_carries_both(stack, store, wall_id):
    client = stack.clients.add_client(name="Pi")
    _fresh(stack.clocks["clients"])
    minted = len(stack.ids["clients"].minted)

    placed = stack.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")

    (display,) = store.list_displays()
    assert display.id == placed.display.id == stack.ids["clients"].minted[minted]
    assert display.first_seen == _once(stack.clocks["clients"])


def test_a_label_output_carries_the_id_it_was_given(stack, store, wall_id):
    client = stack.clients.add_client(name="Pi")
    minted = len(stack.ids["clients"].minted)

    stack.clients.add_label(wall_id, client_id=client.id, output="caption-1")

    (label,) = store.list_label_outputs()
    assert label.id == stack.ids["clients"].minted[minted]


def test_a_first_report_records_displays_and_labels_at_one_instant_with_ids_from_the_source(stack, store):
    client = stack.clients.add_client(name="Pi")
    _fresh(stack.clocks["clients"])
    minted = len(stack.ids["clients"].minted)
    report = {
        "reported_at": "2026-01-01T00:00:05+00:00",
        "outputs": [
            {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080], "identity": "panel-a"},
            {"name": "hdmi-a-2", "kind": "framebuffer", "connected": True, "screen": [1920, 1080], "identity": "panel-b"},
        ],
        "label_outputs": [{"name": "caption-1", "kind": "epaper", "connected": True, "size": [800, 480]}],
    }

    stack.clients.record_heartbeat(client.id, report)

    instant = _once(stack.clocks["clients"])
    displays = store.list_displays()
    assert {display.first_seen for display in displays} == {instant}
    assert {display.id for display in displays} | {label.id for label in store.list_label_outputs()} == set(
        stack.ids["clients"].minted[minted:]
    )
    assert len(stack.ids["clients"].minted) - minted == 3


def test_a_refused_report_is_remembered_at_the_clients_clock(stack):
    client = stack.clients.add_client(name="Pi")
    _fresh(stack.clocks["clients"])

    stack.clients.refused(client.id, "not a report")

    remembered = refused_reports_of(stack.clients._store).now()[client.id]
    assert remembered.at == remembered.since == _once(stack.clocks["clients"])


def test_a_token_is_issued_at_the_access_clock(stack, store):
    client = stack.clients.add_client(name="Pi")

    issued = stack.access.issue(client.id)

    assert issued.issued_at == store.get_client(client.id).token_issued_at == _once(stack.clocks["access"])


# -- an act reads its instant under the store's lock --------------------------------------
#
# Read before the lock, an act that waited on another writer is stamped earlier than the
# one it waited for, so records ordered by time disagree with the order they were written
# in. Each act below reads its clock once, and the store's lock is held when it does.


def _token(stack, store, ready_work, wall_id):
    client = stack.clients.add_client(name="Pi")
    return "access", lambda: stack.access.issue(client.id)


def _wall(stack, store, ready_work, wall_id):
    return "walls", lambda: stack.walls.add_wall(name="Study")


def _theme(stack, store, ready_work, wall_id):
    return "themes", lambda: stack.themes.add_theme(name="Quiet")


def _selection(stack, store, ready_work, wall_id):
    work = ready_work("Nighthawks")
    return "themes", lambda: stack.themes.hang_selection([work.id], wall_id=wall_id)


def _many_join(stack, store, ready_work, wall_id):
    theme = stack.themes.add_theme(name="Quiet")
    works = [ready_work(title).id for title in ("One", "Two")]
    return "themes", lambda: stack.themes.add_works_to_theme(theme_id=theme.id, artwork_ids=works)


@pytest.mark.parametrize("act", [_token, _wall, _theme, _selection, _many_join], ids=lambda act: act.__name__.strip("_"))
def test_an_act_reads_its_instant_with_the_stores_lock_held(stack, store, ready_work, wall_id, act):
    name, do = act(stack, store, ready_work, wall_id)
    clock = stack.clocks[name]
    _fresh(clock)
    clock.probe = store.in_transaction

    do()

    _once(clock)
    assert clock.held == [True], f"the {name} clock was read with the store's lock not held"


# -- the facade hands every collaborator the same two -------------------------------------


def test_the_facade_hands_one_clock_and_one_source_to_every_collaborator(store, services, wall_settings, wall_id):
    clock, ids = Ticks(9), Names("one")
    display = DisplayService(store, services.library, wall_settings, now=clock, mint_id=ids)

    theme = display.add_theme(name="Quiet")
    wall = display.add_wall(name="Study")
    draft = display.draft_scene().scene

    assert [theme.id, wall.id, draft.id] == ids.minted
    assert {theme.created_at, wall.created_at, draft.created_at} <= set(clock.read)
    assert not {theme.created_at, wall.created_at, draft.created_at} & {_DAY}
    display.activate_theme(theme.id, wall_id=wall_id)
    assert store.get_assignment(wall_id).assigned_at in clock.read
    assert _generated_at(wall_settings, wall_id) in {instant.isoformat() for instant in clock.read}


# -- the guards ---------------------------------------------------------------------------

_SRC = Path(arrt.__file__).parent
_OWNER = _SRC / "programming" / "lookups.py"


def _calls(source: str, matches) -> list[int]:
    """The line of every call in `source` that `matches` says is the one looked for."""
    return [node.lineno for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call) and matches(node.func)]


def _reads_exclusions(callee: ast.expr) -> bool:
    return isinstance(callee, ast.Attribute) and callee.attr == "list_exclusions"


#: What a call reads from the machine, by the qualified name its callee resolves to.
_MACHINE_READS = frozenset(
    {
        "datetime.datetime.now",
        "datetime.datetime.utcnow",
        "datetime.datetime.today",
        "datetime.date.today",
        "time.time",
        "time.time_ns",
        "uuid.uuid1",
        "uuid.uuid4",
    }
)


def _imported(tree: ast.Module) -> dict[str, str]:
    """Each name the module binds by an import, anywhere in it, to the dotted name it stands for."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                names[alias.asname or top] = alias.name if alias.asname else top
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            for alias in node.names:
                names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return names


def _qualified(callee: ast.expr, imported: dict[str, str]) -> str | None:
    """The dotted name a callee stands for, resolved through the module's imports; None when it names no import."""
    attributes: list[str] = []
    while isinstance(callee, ast.Attribute):
        attributes.append(callee.attr)
        callee = callee.value
    if not isinstance(callee, ast.Name) or callee.id not in imported:
        return None
    return ".".join([imported[callee.id], *reversed(attributes)])


def _machine_reads(source: str) -> list[int]:
    """The line of every call reading the machine's clock or a random id, however the module imported or named it."""
    tree = ast.parse(source)
    imported = _imported(tree)
    return [
        node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call) and _qualified(node.func, imported) in _MACHINE_READS
    ]


def _found(root: Path, lines) -> list[str]:
    """`path:line` of every line `lines` finds in a module under `root`, the owner's own file excluded."""
    return sorted(
        f"{path.relative_to(root)}:{line}"
        for path in root.rglob("*.py")
        if path != _OWNER
        for line in lines(path.read_text(encoding="utf-8"))
    )


def test_only_the_owner_reads_the_exclusions():
    assert _found(_SRC, lambda source: _calls(source, _reads_exclusions)) == []
    assert _calls(
        _OWNER.read_text(encoding="utf-8"), _reads_exclusions
    ), "the owner no longer reads them: the guard guards nothing"


@pytest.mark.parametrize(
    "second_reader",
    [
        "def kept(store):\n    return {e.artwork_id for e in store.list_exclusions()}\n",
        "def kept(self):\n    return any(e for e in self._store.list_exclusions())\n",
        "def kept(self):\n    return next(iter(self.store.list_exclusions()), None)\n",
    ],
    ids=["a store argument", "the store attribute", "a nested call"],
)
def test_a_second_reader_of_the_exclusions_is_seen(second_reader):
    assert _calls(second_reader, _reads_exclusions) == [2]


def test_programming_reads_the_machines_clock_and_uuid_only_in_its_two_defaults():
    programming = _SRC / "programming"
    assert _found(programming, _machine_reads) == []
    owner = _OWNER.read_text(encoding="utf-8")
    assert len(_machine_reads(owner)) == 2, "the defaults moved: the guard's one exemption is wrong"


@pytest.mark.parametrize(
    "direct",
    [
        "import uuid\ndef make():\n    return uuid.uuid4()\n",
        "from uuid import uuid4\ndef make():\n    return uuid4()\n",
        "from datetime import UTC, datetime\ndef make():\n    return datetime.now(UTC)\n",
        "import datetime as _dt\ndef make():\n    return _dt.datetime.now(_dt.UTC)\n",
        "import datetime\ndef make():\n    return datetime.datetime.now(datetime.UTC)\n",
        "from datetime import datetime as moment\ndef make():\n    return moment.now()\n",
        "import uuid as _u\ndef make():\n    return _u.uuid4()\n",
        "from uuid import uuid4 as fresh\ndef make():\n    return fresh()\n",
    ],
    ids=[
        "uuid module",
        "uuid4 imported",
        "datetime now",
        "datetime module aliased",
        "datetime module by its name",
        "datetime class aliased",
        "uuid module aliased",
        "uuid4 aliased",
    ],
)
def test_a_direct_read_of_the_machine_is_seen(direct):
    assert _machine_reads(direct) == [3]


@pytest.mark.parametrize(
    "innocent",
    [
        "from datetime import datetime\ndef make(text):\n    return datetime.fromisoformat(text)\n",
        "import time\ndef make():\n    return time.monotonic()\n",
        "def make(self):\n    return self._now(), self.now(), self._mint_id()\n",
        "def make(datetime):\n    return datetime.today\n",
    ],
    ids=["an instant parsed", "a duration's clock", "an injected clock and id source", "an attribute never called"],
)
def test_what_reads_no_machine_is_not_seen(innocent):
    assert _machine_reads(innocent) == []
