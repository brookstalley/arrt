"""The shared fixtures' one clock and one id source, and the guard that a report is kept only for a wall a Player shows.

`tests/conftest.py` builds every service over `shared_clock` (`fakes.Ticking`) and
`shared_ids` (`fakes.counted_ids`), passed through `Services.bind`, so a test that
reads no other clock reads the same instants on every run and the test runner can
reuse its result. These tests hold the three things that must stay true for that:
no service the fixture builds reads the machine's clock or draws a random id; the
fakes keep what the machine's clock and `uuid4` guaranteed (instants strictly
increasing across threads, ids unique across every service and every file named
by one); and a deployment, which passes neither, still gets the machine's.
"""

import builtins
import datetime as _dt
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import CodeType, FunctionType

import pytest
from conftest import NO_PLAYER_REPORTS_MARKER, ReportsForNoPlayer
from fakes import CLOCK_STARTS_AT, CLOCK_STEP, OPENED_AT, Ticking, counted_ids

import arrt
from arrt.library.services import spend_history
from arrt.persistence.discovery_records import InitiatedBy
from arrt.programming.clients import ClientService
from arrt.services.container import Services

_SRC = Path(arrt.__file__).parent

#: What reads the machine: its clock, and a random id.
_MACHINE_CALLABLES: dict[object, str] = {
    time.time: "time.time",
    time.time_ns: "time.time_ns",
    uuid.uuid1: "uuid.uuid1",
    uuid.uuid4: "uuid.uuid4",
}
_MACHINE_CLOCK_METHODS = frozenset({"now", "utcnow", "today"})


def _machine(callee: object) -> str | None:
    """The machine read a call makes, by name, or None.

    A bound `datetime.now` is a new object at each access, so it is matched by its owner.
    """
    try:
        named = _MACHINE_CALLABLES.get(callee)
    except TypeError:  # a callable that cannot be hashed is none of them
        named = None
    if named is not None:
        return named
    owner = getattr(callee, "__self__", None)
    if isinstance(owner, type) and issubclass(owner, date) and getattr(callee, "__name__", None) in _MACHINE_CLOCK_METHODS:
        return f"{owner.__name__}.{callee.__name__}"  # type: ignore[attr-defined]
    return None


@contextmanager
def machine_reads() -> Iterator[list[str]]:
    """Every call the server's own code makes, on any thread, to the machine's clock or a random id, while open.

    Watched with `sys.monitoring`, so a read is seen however its module imported
    or named it, and inside whatever default or helper made it; only calls made by
    code under `arrt/` count, so the test's own and its libraries' do not.
    """
    monitoring = sys.monitoring
    tool = next((each for each in range(6) if monitoring.get_tool(each) is None), None)
    assert tool is not None, "every sys.monitoring tool id is taken, so nothing can watch for a machine read"
    found: list[str] = []
    lock = threading.Lock()
    prefix = f"{_SRC}/"

    def on_call(code, _offset, callee, _arg0):
        if code.co_filename.startswith(prefix):
            read = _machine(callee)
            if read is not None:
                with lock:
                    found.append(f"{Path(code.co_filename).relative_to(_SRC)}:{code.co_qualname} called {read}")

    monitoring.use_tool_id(tool, "arrt machine reads")
    try:
        monitoring.register_callback(tool, monitoring.events.CALL, on_call)
        monitoring.set_events(tool, monitoring.events.CALL)
        yield found
    finally:
        monitoring.set_events(tool, monitoring.events.NO_EVENTS)
        monitoring.register_callback(tool, monitoring.events.CALL, None)
        monitoring.free_tool_id(tool)


def _client_report(at: datetime) -> dict:
    return {
        "reported_at": at.isoformat(),
        "outputs": [{"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]}],
    }


def _wall_report(at: datetime) -> dict:
    return {
        "schema": {"major": 1, "minor": 2},
        "reported_at": at.isoformat(),
        "current_work_id": None,
        "capabilities": {
            "screen": {"width_px": 1920, "height_px": 1080},
            "backend": "framebuffer",
            "label_modes": ["none"],
            "manifest_majors": [2, 1],
        },
    }


# -- no service the fixture builds reads the machine ------------------------------------------


def _the_household_at_work(services: Services, wall_id: str, ready_work, shared_clock) -> None:
    """One act or reading on every service `Services.bind` hands a clock or an id source to."""
    catalogue = services.catalogue
    artist = catalogue.add_artist(name="Edward Hopper")
    work = ready_work("Nighthawks", artist_id=artist.id)
    run = services.discovery.start_discovery_run(intent_text="American realism", initiated_by=InitiatedBy.MCP_CLIENT)
    services.discovery.propose_work(
        run_id=run.id, proposed_title="Automat", rationale="Hopper's diner, as the intent asked.", work_dedup_key="automat"
    )
    theme = services.display.add_theme(name="Night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=wall_id)
    player = services.clients.add_client(name="Hall Pi")
    services.access.issue(player.id)
    services.clients.assign_wall(wall_id, client_id=player.id, output="hdmi-a-1")
    services.clients.record_heartbeat(player.id, _client_report(shared_clock()))
    services.display.record_heartbeat(wall_id, _wall_report(shared_clock()))
    services.display.read_walls()
    services.clients.list_clients()
    services.health.observe()
    services.health.observe_walls()
    services.acquisition_queue.failed_states()
    services.unattended.standing()
    services.watches.reading()
    services.taste.brief()
    services.runner.spend_report()
    spend_history.read(services.discovery)


def test_no_service_the_shared_fixture_builds_reads_the_machines_clock_or_a_random_id(
    services, wall_id, ready_work, shared_clock
):
    with machine_reads() as found:
        _the_household_at_work(services, wall_id, ready_work, shared_clock)

    assert found == []


def _as_the_servers(source: str, namespace: dict[str, object]) -> Callable[[], object]:
    """The one function `source` defines, compiled as if it were a module under `arrt/`, which is all the watch counts."""
    module = compile(source, str(_SRC / "planted.py"), "exec")
    (body,) = [constant for constant in module.co_consts if isinstance(constant, CodeType)]
    return FunctionType(body, {"__builtins__": builtins, **namespace})


def _the_tests_own_reads() -> object:
    return datetime.now(UTC), _dt.datetime.now(_dt.UTC), uuid.uuid4(), time.time()


def test_the_watch_sees_a_machine_read_however_it_is_named():
    """The probe above can fail: each way of reading the machine, from code under `arrt/`, is seen."""
    # The reads are the test's own, so none counts, though the call into them is the server's.
    on_behalf = _as_the_servers("def planted():\n    return read()\n", {"read": _the_tests_own_reads})
    with machine_reads() as found:
        on_behalf()
    assert found == [], "a read made by the test's own code was counted"

    planted = _as_the_servers(
        "def planted():\n    return datetime.now(UTC), _dt.datetime.now(), date.today(), uuid.uuid4(), time.time()\n",
        {"datetime": datetime, "UTC": UTC, "_dt": _dt, "date": date, "uuid": uuid, "time": time},
    )
    with machine_reads() as found:
        planted()
    assert [line.split(" called ")[1] for line in found] == [
        "datetime.now",
        "datetime.now",
        "date.today",
        "uuid.uuid4",
        "time.time",
    ]


# -- what the fakes keep of the machine's ------------------------------------------------------


def test_the_clock_starts_after_the_file_was_opened_and_moves_forward_on_every_reading():
    clock = Ticking()

    first, second = clock(), clock()

    assert OPENED_AT < CLOCK_STARTS_AT == first < second


def test_every_reading_from_many_threads_at_once_is_a_later_instant_than_the_one_before_it():
    clock = Ticking()
    threads, each = 8, 500
    start = threading.Barrier(threads)
    read: list[list[datetime]] = [[] for _ in range(threads)]

    def reader(mine: list[datetime]) -> None:
        start.wait()
        mine.extend(clock() for _ in range(each))

    workers = [threading.Thread(target=reader, args=(read[n],)) for n in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    every = [instant for mine in read for instant in mine]
    assert len(set(every)) == threads * each, "two readings gave the same instant"
    assert all(mine == sorted(mine) for mine in read), "a thread read an instant earlier than its previous one"
    assert sorted(every) == [CLOCK_STARTS_AT + n * CLOCK_STEP for n in range(threads * each)]


def test_time_passes_only_forward():
    clock = Ticking()
    before = clock()

    clock.advance(timedelta(minutes=10))

    assert clock() - before > timedelta(minutes=10)
    with pytest.raises(ValueError, match="does not go back"):
        clock.advance(timedelta(seconds=-1))


def test_ids_differ_in_their_head_as_well_as_their_tail():
    """A selection is named by its theme id's first eight characters, and names are unique."""
    mint = counted_ids()

    ids = [mint() for _ in range(300)]

    assert len({each[:8] for each in ids}) == len(ids)
    assert all(str(uuid.UUID(each)) == each for each in ids)


def test_one_id_source_is_shared_by_the_file_and_every_service_so_no_two_records_or_files_share_one(
    services, store, wall_id, ready_work, settings, shared_clock
):
    work = ready_work()
    services.display.add_theme(name="Night")
    second = services.display.add_wall(name="Study")
    player = services.clients.add_client(name="Hall Pi")
    services.access.issue(player.id)
    services.clients.assign_wall(wall_id, client_id=player.id, output="hdmi-a-1")
    services.clients.assign_wall(second.id, client_id=player.id, output="hdmi-a-2")
    services.display.hang_selection([work.id], wall_id=wall_id)
    services.display.hang_selection([work.id], wall_id=second.id)
    services.clients.record_heartbeat(player.id, _client_report(shared_clock()))
    services.display.record_heartbeat(wall_id, _wall_report(shared_clock()))
    services.display.record_heartbeat(second.id, _wall_report(shared_clock()))

    minted = [
        work.id,
        *(wall.id for wall in store.list_walls()),
        *(theme.id for theme in store.list_themes()),
        *(client.id for client in store.list_clients()),
        *(display.id for display in store.list_displays()),
    ]
    assert len(set(minted)) == len(minted), f"two records were given one id: {sorted(minted)}"
    named = [path for path in Path(settings.art_root).rglob("*") if any(each in path.name for each in minted)]
    assert named, "no file is named for an id, so nothing here is checked"
    assert all(sum(each in path.name for each in minted) == 1 for path in named)


def test_a_deployment_that_passes_neither_gets_the_machines(
    store, discovery_store, wall_settings, thumbnail_settings, settings, engine
):
    services = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        quality_profile=settings.quality_profile,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        resolve=lambda _host: ["93.184.216.34"],
    )
    before = datetime.now(UTC)

    theme = services.display.add_theme(name="Night")
    player = services.clients.add_client(name="Hall Pi")
    work = services.catalogue.add_artwork(title="Nighthawks")

    after = datetime.now(UTC)
    assert all(before <= stamped <= after for stamped in (theme.created_at, player.created_at, work.created_at))
    assert all(uuid.UUID(each).version == 4 for each in (theme.id, player.id, work.id))


# -- a report's first display is stamped once the act holds the store ------------------------


def test_a_report_reads_its_clock_only_once_it_holds_the_store(store, wall_settings, services, quiet_catalogue_file):
    held: list[bool] = []

    def clock() -> datetime:
        held.append(quiet_catalogue_file.in_transaction())
        return CLOCK_STARTS_AT + timedelta(seconds=len(held))

    clients = ClientService(store, wall_settings, services.library, now=clock, mint_id=counted_ids())
    player = clients.add_client(name="Hall Pi")
    held.clear()

    clients.record_heartbeat(player.id, _client_report(CLOCK_STARTS_AT))

    (display,) = store.list_displays()
    assert held == [True], f"the report read its clock outside the store's lock: {held}"
    assert display.first_seen == CLOCK_STARTS_AT + timedelta(seconds=1)


def test_a_player_is_stamped_once_the_act_holds_the_store(store, wall_settings, services, quiet_catalogue_file):
    held: list[bool] = []

    def clock() -> datetime:
        held.append(quiet_catalogue_file.in_transaction())
        return CLOCK_STARTS_AT

    ClientService(store, wall_settings, services.library, now=clock, mint_id=counted_ids()).add_client(name="Hall Pi")

    assert held == [True]


# -- a report only for a wall a Player shows ---------------------------------------------------


@pytest.mark.reports_for_a_wall_no_player_shows("the guard's own test: it must see this report")
def test_the_guard_sees_a_report_kept_for_a_wall_no_player_shows(
    services, wall_id, shared_clock, reports_only_where_a_player_shows: ReportsForNoPlayer
):
    services.display.record_heartbeat(wall_id, _wall_report(shared_clock()))

    assert {writer for writer, wall in reports_only_where_a_player_shows.kept if wall == wall_id} == {
        "record_heartbeat",
        "keep_showing",
    }
    complaint = reports_only_where_a_player_shows.complaint()
    assert complaint is not None
    assert wall_id in complaint
    assert NO_PLAYER_REPORTS_MARKER in complaint


@pytest.mark.reports_for_a_wall_no_player_shows("the guard's own test: a Player with no token reports nothing")
def test_the_guard_counts_a_player_with_no_token_as_none(
    services, wall_id, shared_clock, reports_only_where_a_player_shows: ReportsForNoPlayer
):
    player = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(wall_id, client_id=player.id, output="hdmi-a-1")

    services.display.record_heartbeat(wall_id, _wall_report(shared_clock()))

    assert reports_only_where_a_player_shows.kept


def test_the_guard_passes_a_report_for_a_wall_a_player_shows(
    services, wall_id, shared_clock, a_player_shows_the_wall, reports_only_where_a_player_shows: ReportsForNoPlayer
):
    services.display.record_heartbeat(wall_id, _wall_report(shared_clock()))

    assert reports_only_where_a_player_shows.kept == []


def test_the_guard_does_not_count_a_report_refused(services, wall_id, reports_only_where_a_player_shows: ReportsForNoPlayer):
    with pytest.raises(Exception, match="not a heartbeat"):
        services.display.record_heartbeat(wall_id, {"reported_at": "never"})

    assert reports_only_where_a_player_shows.kept == []
