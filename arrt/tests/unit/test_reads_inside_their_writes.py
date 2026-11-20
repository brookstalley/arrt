"""Programming reads what it decides from inside the scope that writes it (audit wave 2b, Chunk 48; C1, C2).

Part 2a's split of `DisplayService` moved each method verbatim, and its builder
listed the ones that checked the catalogue, then opened the transaction that
acts on the answer: a second act landing between the check and the write was
decided against a catalogue that no longer stood. Requests run on a threadpool,
so a second curator's tab, an agent or a Player's heartbeat is that second act.

Two kinds of test hold the fix:

- **A store that records, for every read, whether a transaction or read scope
  was open** (`_Scoped`): each method named here makes every read inside one.
- **Two acts ordered on purpose** (`_another_act_at`): at the act's first call of
  a named read, a second thread asks for the store's lock *without waiting*.
  Free, the read was made outside any scope, and the second act runs there and
  then, before the first goes on — the interleaving the lock let through. Held,
  it runs nothing, and the second act runs once the first has returned, which is
  where a thread waiting on the lock would have landed. Nothing sleeps and
  nothing is timed: the probe never blocks, and the first act waits for it.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from arrt.library.facade import EventKind
from arrt.programming.display import DisplayService
from arrt.programming.lookups import no_theme
from arrt.programming.reports import SCREEN_MEMORY
from arrt.services.errors import ServiceError

#: The store methods that only read. Every other method of the store writes.
_READ_PREFIXES = ("get_", "list_")
_READS = {"offered_work_ids", "reported_screens", "latest_showing", "last_shown_by_work"}


class _Scoped:
    """The test's store, recording each read with whether a `transaction()` or `reading()` block was open around it."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self._depth = 0
        self.recording = False
        self.reads: list[tuple[str, bool]] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._real.transaction():
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1

    @contextmanager
    def reading(self) -> Iterator[None]:
        with self._real.reading():
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1

    def __getattr__(self, name: str) -> Any:
        held = getattr(self._real, name)
        if not callable(held) or not (name.startswith(_READ_PREFIXES) or name in _READS):
            return held

        def read(*arguments: Any, **keywords: Any) -> Any:
            if self.recording:
                self.reads.append((name, self._depth > 0))
            return held(*arguments, **keywords)

        return read


@pytest.fixture
def scoped(services, store, wall_settings):
    """A second facade over the same catalogue, whose store records every read's scope."""
    spy = _Scoped(store)
    return spy, DisplayService(spy, services.library, wall_settings)


def _outside(spy: _Scoped, act: Callable[[], object]) -> list[str]:
    """Run `act` with the spy recording, and return the reads it made with no scope open."""
    spy.reads.clear()
    spy.recording = True
    try:
        act()
    finally:
        spy.recording = False
    assert spy.reads, "the act made no read at all, so there was nothing to check"
    return [name for name, inside in spy.reads if not inside]


@pytest.fixture
def on_a_display(services, wall_id):
    """The wall on a client's HDMI output, so it has a display that screen sizes are kept against."""
    client = services.clients.add_client(name="Hall Pi")
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    services.access.issue(client.id)
    services.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    return services.display.get_wall(wall_id).display_id


def _beat_with_screen(width: int, height: int) -> dict:
    return {
        "schema": {"major": 1, "minor": 2},
        "reported_at": datetime.now(UTC).isoformat(),
        "current_work_id": None,
        "capabilities": {
            "screen": {"width_px": width, "height_px": height},
            "backend": "framebuffer",
            "label_modes": ["none"],
            "manifest_majors": [2, 1],
        },
    }


# -- every read inside the scope that writes ----------------------------------------------


def _seven(display, ready_work, wall_id, on_a_display):
    """Each of the seven methods C1 named, as a callable over a facade, set up through the services' own."""

    def delete_theme(facade):
        theme = display.add_theme(name="Unhung")
        return lambda: facade.delete_theme(theme.id)

    def exclude_work(facade):
        work = ready_work("Kept off")
        return lambda: facade.exclude_work(work.id, wall_id=wall_id)

    def allow_work(facade):
        work = ready_work("Allowed back")
        display.exclude_work(work.id)
        return lambda: facade.allow_work(work.id)

    def remove_from_theme(facade):
        theme = display.add_theme(name="Holding one")
        work = ready_work("Taken out")
        display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
        return lambda: facade.remove_from_theme(theme_id=theme.id, artwork_id=work.id)

    def make_default(facade):
        theme = display.add_theme(name="New default")
        return lambda: facade.make_default(theme.id)

    def update_theme(facade):
        theme = display.add_theme(name="Renamed")
        return lambda: facade.update_theme(theme.id, name="Renamed again")

    def record_screen(facade):
        return lambda: facade._reports._record_screen(wall_id, _beat_with_screen(3840, 2160))

    return {
        "delete_theme": delete_theme,
        "exclude_work": exclude_work,
        "allow_work": allow_work,
        "remove_from_theme": remove_from_theme,
        "make_default": make_default,
        "update_theme": update_theme,
        "_record_screen": record_screen,
    }


@pytest.mark.parametrize(
    "method",
    ["delete_theme", "exclude_work", "allow_work", "remove_from_theme", "make_default", "update_theme", "_record_screen"],
)
def test_each_of_the_seven_reads_inside_the_scope_that_writes(scoped, display, ready_work, wall_id, on_a_display, method):
    """Acceptance 1 of Chunk 48: red on 2b's head for each method, naming the reads it made outside."""
    spy, facade = scoped
    act = _seven(display, ready_work, wall_id, on_a_display)[method](facade)

    assert _outside(spy, act) == [], f"{method} read outside the scope that writes"


def test_a_scenes_walls_are_read_in_one_scope(scoped, display, ready_work, wall_id):
    """C2: `scene_walls` read with no read scope, so a wall deleted meanwhile was asserted present."""
    spy, facade = scoped
    work = ready_work("Pinned")
    theme = display.add_theme(name="Hung")
    display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    display.activate_theme(theme.id, wall_id=wall_id)
    draft = display.draft_scene()
    display.pin_scene(draft.scene.id, wall_id, work.id)
    view = display.apply_scene(draft.scene.id, lifetime="hold")

    assert _outside(spy, lambda: facade.scene_walls(view)) == []


# -- two acts, ordered on purpose ------------------------------------------------------------


class _Second:
    """What the second act did, and where it landed."""

    def __init__(self) -> None:
        self.landed: str | None = None
        self.value: object = None
        self.refused: ServiceError | None = None
        self.failed: BaseException | None = None

    def run(self, act: Callable[[], object]) -> None:
        try:
            self.value = act()
        except ServiceError as refusal:
            self.refused = refusal
        except BaseException as error:  # noqa: BLE001 -- carried back to the test's thread and raised there
            self.failed = error


def _another_act_at(monkeypatch, store, method: str, act: Callable[[], object]) -> Callable[[], _Second]:
    """At the first act's first call of `store.<method>`, land `act` there if the store's lock lets it in.

    Returns `finish`: called once the first act has returned, it runs `act` then
    if it was kept out, raises whatever `act` raised other than a refusal, and
    answers what `act` did and whether it landed `between` the first act's read
    and its write or `after` the first act.
    """
    # The one lock `transaction()` and `reading()` both hold (`persistence/durable.py`).
    lock = store._store._lock
    read = getattr(store, method)
    first = threading.get_ident()
    second = _Second()
    fired: list[bool] = []

    def probe() -> None:
        if lock.acquire(blocking=False):
            lock.release()
            second.landed = "between"
            second.run(act)

    def reading(*arguments, **keywords):
        found = read(*arguments, **keywords)
        if threading.get_ident() == first and not fired:
            fired.append(True)
            other = threading.Thread(target=probe)
            other.start()
            other.join()
        return found

    monkeypatch.setattr(store, method, reading)

    def finish() -> _Second:
        assert fired, f"the first act never called {method}, so nothing was interleaved"
        monkeypatch.setattr(store, method, read)
        if second.landed is None:
            second.landed = "after"
            second.run(act)
        if second.failed is not None:
            raise second.failed
        return second

    return finish


@pytest.fixture
def hung_theme(display, ready_work, wall_id):
    """A theme with one work, hung on the wall."""
    theme = display.add_theme(name="Hung")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work("On the wall").id)
    display.activate_theme(theme.id, wall_id=wall_id)
    return theme


def test_a_theme_hung_while_it_is_deleted_is_hung_after_it_is_gone_and_refused(display, store, ready_work, wall_id, monkeypatch):
    """`delete_theme` checked which walls hang it, then deleted: a hang between them left the delete refused by the file."""
    theme = display.add_theme(name="Unhung")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work("In it").id)
    finish = _another_act_at(monkeypatch, store, "list_assignments", lambda: display.activate_theme(theme.id, wall_id=wall_id))

    display.delete_theme(theme.id)
    second = finish()

    assert second.landed == "after"
    assert str(second.refused) == no_theme(theme.id)
    assert store.get_theme(theme.id) is None
    assert store.get_assignment(wall_id) is None


def test_a_work_kept_off_twice_at_once_is_kept_off_once_and_the_second_is_told_so(
    display, store, ready_work, wall_id, monkeypatch
):
    """`exclude_work` checked the exclusions, then wrote: a second exclusion between them made the file refuse the first."""
    work = ready_work("Kept off")
    finish = _another_act_at(monkeypatch, store, "list_exclusions", lambda: display.exclude_work(work.id))

    display.exclude_work(work.id, wall_id=wall_id)
    second = finish()

    assert second.landed == "after"
    assert str(second.refused) == f"Artwork {work.id!r} is already kept off every wall."
    assert [kept.artwork_id for kept in store.list_exclusions()] == [work.id]


def test_a_work_allowed_back_twice_at_once_is_allowed_once_and_the_second_is_told_so(display, store, ready_work, monkeypatch):
    """`allow_work` checked the exclusions outside its act, so both allowed it and History said so twice."""
    work = ready_work("Allowed back")
    display.exclude_work(work.id)
    finish = _another_act_at(monkeypatch, store, "list_exclusions", lambda: display.allow_work(work.id))

    display.allow_work(work.id)
    second = finish()

    assert second.landed == "after"
    assert str(second.refused) == f"Artwork {work.id!r} is not kept off the walls, so there is nothing to allow."


def test_a_work_taken_out_of_a_theme_twice_at_once_leaves_once_and_the_second_is_told_so(display, store, ready_work, monkeypatch):
    """`remove_from_theme` checked the membership outside its act, so both removed it and neither was refused."""
    theme = display.add_theme(name="Holding one")
    work = ready_work("Taken out")
    display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    finish = _another_act_at(
        monkeypatch,
        store,
        "get_membership",
        lambda: display.remove_from_theme(theme_id=theme.id, artwork_id=work.id),
    )

    display.remove_from_theme(theme_id=theme.id, artwork_id=work.id)
    second = finish()

    assert second.landed == "after"
    assert str(second.refused) == f"Artwork {work.id!r} is not in theme {theme.id!r}."


def test_a_theme_deleted_while_it_is_made_the_default_stays_and_its_delete_is_refused(display, store, monkeypatch):
    """`make_default` checked the theme, then marked it: a delete between them made the mark fail in the store's words."""
    theme = display.add_theme(name="New default")
    finish = _another_act_at(monkeypatch, store, "get_theme", lambda: display.delete_theme(theme.id))

    made = display.make_default(theme.id)
    second = finish()

    assert second.landed == "after"
    assert made.id == theme.id
    assert made.is_default
    assert "is the default" in str(second.refused)
    assert store.get_default_theme().id == theme.id


def test_a_description_written_while_a_theme_is_renamed_is_kept(display, store, monkeypatch):
    """`update_theme` read the whole row, then wrote it back: a description written between them was put back to none."""
    theme = display.add_theme(name="Renamed")
    finish = _another_act_at(
        monkeypatch, store, "get_theme", lambda: display.update_theme(theme.id, description="Written meanwhile")
    )

    display.update_theme(theme.id, name="Renamed again")
    second = finish()

    assert second.landed == "after"
    kept = store.get_theme(theme.id)
    assert (kept.name, kept.description) == ("Renamed again", "Written meanwhile")


def test_a_size_reported_again_while_old_sizes_are_forgotten_is_kept(display, store, wall_id, on_a_display, monkeypatch):
    """`_record_screen` read the known sizes, then forgot the old ones: a size refreshed between them was forgotten."""
    long_ago = datetime.now(UTC) - SCREEN_MEMORY - timedelta(hours=1)
    store.record_screen(on_a_display, 1920, 1080, long_ago)
    finish = _another_act_at(
        monkeypatch, store, "reported_screens", lambda: display.record_heartbeat(wall_id, _beat_with_screen(1920, 1080))
    )

    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))
    second = finish()

    assert second.landed == "after"
    kept = {(width, height): at for width, height, at in store.reported_screens(on_a_display)}
    assert set(kept) == {(1920, 1080), (3840, 2160)}
    assert kept[(1920, 1080)] > long_ago


@pytest.fixture
def two_walls_in_a_scene(display, ready_work, wall_id, hung_theme):
    """The hall and the study, both pinned in a held scene."""
    study = display.add_wall(name="Study").id
    display.activate_theme(hung_theme.id, wall_id=study)
    work = ready_work("Pinned")
    draft = display.draft_scene()
    for wall in (wall_id, study):
        display.pin_scene(draft.scene.id, wall, work.id)
    return display.apply_scene(draft.scene.id, lifetime="hold"), study


def test_a_wall_deleted_while_a_scenes_walls_are_read_does_not_fail_the_read(
    display, store, wall_id, two_walls_in_a_scene, monkeypatch
):
    """Acceptance 2 of Chunk 48 (C2): a wall deleted between `_pins_on_held_walls` and its read ended as a 500."""
    view, study = two_walls_in_a_scene
    finish = _another_act_at(monkeypatch, store, "list_walls", lambda: display.delete_wall(study))

    walls = display.scene_walls(view)
    second = finish()

    assert second.landed == "after"
    assert {wall.wall_id for wall in walls} == {wall_id, study}
    assert store.get_wall(study) is None
    assert {wall.wall_id for wall in display.scene_walls(view)} == {wall_id}


def test_a_wall_deleted_while_a_scenes_history_is_written_does_not_fail_the_act(
    display, store, wall_id, two_walls_in_a_scene, monkeypatch
):
    """`_record_scene` runs after its act commits and had the same read: a wall deleted meanwhile failed a committed act."""
    view, study = two_walls_in_a_scene
    finish = _another_act_at(monkeypatch, store, "list_walls", lambda: display.delete_wall(study))

    display._scenes._record_scene(EventKind.SCENE_ENDED, view.scene, view.pins, how="released")
    second = finish()

    # No scope holds it off: one listing of the walls decides which are held and
    # names them, so the delete lands after that listing and changes nothing it said.
    assert second.landed == "between"
    assert store.get_wall(study) is None
    page = store.list_events(kinds=[EventKind.SCENE_ENDED], limit=50, offset=0)
    assert {event.wall_id: event.detail["wall_name"] for event in page.events} == {
        wall_id: display.get_wall(wall_id).name,
        study: "Study",
    }


def test_a_theme_deleted_while_it_is_hung_is_hung_and_its_delete_refused(display, store, ready_work, wall_id, monkeypatch):
    """A sibling: `activate_theme` checked the theme before its act, so a delete between them had the file refuse the hang."""
    theme = display.add_theme(name="About to hang")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work("In it").id)
    finish = _another_act_at(monkeypatch, store, "get_theme", lambda: display.delete_theme(theme.id))

    display.activate_theme(theme.id, wall_id=wall_id)
    second = finish()

    assert second.landed == "after"
    assert "is hanging on" in str(second.refused)
    assert store.get_assignment(wall_id).theme_id == theme.id


def test_a_theme_deleted_while_a_work_joins_it_takes_the_work_with_it(display, store, ready_work, monkeypatch):
    """A sibling: `add_to_theme` checked the theme before its act, so a delete between them left the add refused by the file."""
    theme = display.add_theme(name="About to go")
    work = ready_work("Joining")
    finish = _another_act_at(monkeypatch, store, "get_theme", lambda: display.delete_theme(theme.id))

    display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    second = finish()

    assert second.landed == "after"
    assert second.refused is None
    assert store.get_theme(theme.id) is None


def test_a_theme_hung_while_the_walls_are_surveyed_is_answered(display, store, ready_work, wall_id, monkeypatch):
    """A sibling: `survey_walls` read the themes, then the hangs, so a theme made and hung between them was a KeyError."""

    def make_and_hang() -> None:
        theme = display.add_theme(name="Made meanwhile")
        display.add_to_theme(theme_id=theme.id, artwork_id=ready_work("New").id)
        display.activate_theme(theme.id, wall_id=wall_id)

    finish = _another_act_at(monkeypatch, store, "list_themes", make_and_hang)

    views = display.survey_walls()
    second = finish()

    assert second.landed == "after"
    assert [view.hanging for view in views] == [None]
    assert display.survey_walls()[0].hanging.name == "Made meanwhile"
