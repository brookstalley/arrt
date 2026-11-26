"""The themes listing over MCP and a label's document each say what they say from one reading.

Each answer reads several rows and files. A write committed by another thread
between two of those reads let one answer say two instants: a themes listing
naming a wall on display D beside display D holding no wall, and a label's
document judging a wall's state by a wall row read before the wall was taken off
its display, so a label kept captioning a showing wall after the write had
committed and Walls said unassigned. Each answer now takes its rows and files
inside the store's one read scope, which keeps this process's writers out until
the answer has read them.

The writer is a real second thread, started from inside the answer between
two of its reads. The store's lock is watched, so the test knows without
sleeping whether the writer committed then or was made to wait: an answer read
while a write committed must say the instant after it, and one the write waited
for must say the instant before.
"""

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from arrt import observations
from arrt.mcp import bindings

#: Never waited out in a passing run: the wait ends the moment the writer commits or is made to wait.
_FAILSAFE_SECONDS = 30.0


class _WatchedLock:
    """The store's re-entrant lock, saying when the writer had to wait for it and letting it in at the first gap.

    A writer kept waiting commits the moment the answer's thread holds the lock
    no more, as it would if the scheduler chose it then: so an answer that
    takes its reads in two scopes is caught every time at the gap between
    them, never only when the scheduler happens to pick the writer.
    """

    def __init__(self, real, settled: threading.Event, committed: threading.Event) -> None:
        self._real = real
        self._settled = settled
        self._committed = committed
        self._depth = threading.local()
        self.writer: threading.Thread | None = None
        self.waited = threading.Event()

    def __enter__(self):
        if not self._real.acquire(blocking=False):
            if threading.current_thread() is self.writer:
                self.waited.set()
                self._settled.set()
            self._real.acquire()
        self._depth.value = getattr(self._depth, "value", 0) + 1
        return self

    def __exit__(self, *_exc) -> None:
        self._depth.value -= 1
        self._real.release()
        if self._depth.value == 0 and threading.current_thread() is not self.writer and self.waited.is_set():
            assert self._committed.wait(_FAILSAFE_SECONDS), "the writer was let in and never committed"


class _WriterBetweenReads:
    """At the first call of `owner.name`, run `write` on another thread and note whether it committed then.

    The answer's own thread waits until the writer has committed or the store's
    lock has made it wait, then makes the call it was about to make.
    """

    def __init__(self, monkeypatch, durable, owner, name: str, write: Callable[[], object]) -> None:
        self._settled = threading.Event()
        self.committed = threading.Event()
        self._lock = _WatchedLock(durable._lock, self._settled, self.committed)
        monkeypatch.setattr(durable, "_lock", self._lock)
        self._real = getattr(owner, name)
        self._write = write
        self.committed_while_reading: bool | None = None
        self._thread: threading.Thread | None = None
        monkeypatch.setattr(owner, name, self._between)

    def _run(self) -> None:
        self._write()
        self.committed.set()
        self._settled.set()

    def _between(self, *args, **kwargs):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="a writer between two reads")
            self._lock.writer = self._thread
            self._thread.start()
            assert self._settled.wait(_FAILSAFE_SECONDS), "the writer neither committed nor waited"
            self.committed_while_reading = self.committed.is_set()
        return self._real(*args, **kwargs)

    def finish(self) -> None:
        assert self._thread is not None, "the answer never made the read the writer starts at, so nothing was tested"
        self._thread.join(_FAILSAFE_SECONDS)
        assert self.committed.is_set(), "the writer never committed"


def _a_player_reporting(services, name: str):
    client = services.clients.add_client(name=name)
    services.access.issue(client.id)
    services.clients.record_heartbeat(
        client.id,
        {
            "reported_at": datetime.now(UTC).isoformat(),
            "outputs": [{"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]}],
        },
    )
    return client


# -- the themes listing ----------------------------------------------------------------


def _wall_entry(listing: dict, wall_id: str) -> dict:
    [entry] = [wall for theme in listing["themes"] for wall in theme["hanging_on"] if wall["wall_id"] == wall_id]
    return entry


def _says_one_instant_of_the_wall(entry: dict) -> list[str]:
    """What in one wall's entry contradicts the rest of it; empty when it says one instant."""
    display = entry["display"]
    if entry["display_id"] is None:
        return [] if display is None else [f"names no display beside display {display['display_id']}"]
    if display is None or display["display_id"] != entry["display_id"]:
        return [f"names display {entry['display_id']} beside {display}"]
    if display["wall_id"] != entry["wall_id"]:
        return [f"names display {entry['display_id']}, which holds wall {display['wall_id']!r}, not this one"]
    return []


@pytest.fixture
def hung(services, wall_id):
    """The catalogue's wall hanging a theme on Hall Pi's screen, and Landing Pi's screen free."""
    theme = services.display.add_theme(name="Nocturnes")
    services.display.activate_theme(theme.id, wall_id=wall_id)
    hall = _a_player_reporting(services, "Hall Pi")
    services.clients.assign_wall(wall_id, client_id=hall.id, output="hdmi-a-1")
    return _a_player_reporting(services, "Landing Pi")


_MOVES = {
    "the wall is taken off its screen": lambda services, wall_id, _landing: services.clients.unassign_wall(wall_id),
    "the wall moves to another Player's screen": lambda services, wall_id, landing: services.clients.assign_wall(
        wall_id, client_id=landing.id, output="hdmi-a-1"
    ),
}


@pytest.mark.parametrize("move", _MOVES)
def test_the_themes_listing_says_one_instant_of_each_wall_whatever_commits_while_it_is_read(
    services, quiet_catalogue_file, monkeypatch, wall_id, hung, move
):
    """`art_theme(action='list')`: a wall's display and that display's wall, from one reading.

    The writer starts at the listing's read of the themes, after its read of
    the walls. Before, the walls and hangs were read, then the themes, then who
    shows what in a reading of its own, so a wall moved between them was named
    on its old display beside that display holding no wall.
    """
    writer = _WriterBetweenReads(
        monkeypatch,
        quiet_catalogue_file,
        services.clients.placements._store,
        "list_themes",
        lambda: _MOVES[move](services, wall_id, hung),
    )

    listing = bindings._list_themes(services, {})
    writer.finish()

    entry = _wall_entry(listing, wall_id)
    assert _says_one_instant_of_the_wall(entry) == []
    after = services.display.get_wall(wall_id).display_id
    if writer.committed_while_reading:
        assert entry["display_id"] == after, "the move committed while the listing was read; it must say the instant after"
    else:
        assert entry["display_id"] != after, "the move waited for the listing, which must say the instant before it"


# -- a label's document ------------------------------------------------------------------


@pytest.fixture
def captioned(services, wall_id):
    """The catalogue's wall on Hall Pi's screen, having reported, captioned by Door Pi's panel."""
    hall = _a_player_reporting(services, "Hall Pi")
    services.clients.assign_wall(wall_id, client_id=hall.id, output="hdmi-a-1")
    panel = services.clients.add_client(name="Door Pi")
    label = services.clients.add_label(wall_id, client_id=panel.id, output="epd-0").label
    now = datetime.now(UTC).isoformat(timespec="seconds")
    services.display.record_heartbeat(
        wall_id,
        {
            "schema": {"major": 1, "minor": 3},
            "display_state": {"state": "silent", "work_id": None, "since": now},
            "reported_at": now,
        },
    )
    return label


def _walls_state(services, wall_id: str) -> str:
    [view] = services.health.observe_walls(wall_id).views
    return str(view.display_state.state)


def test_a_labels_document_says_the_walls_state_of_one_instant_whatever_commits_while_it_is_read(
    services, quiet_catalogue_file, monkeypatch, wall_id, captioned
):
    """`GET /labels/{label_id}`: the label, the wall's row and who shows it, from one reading.

    The writer takes the wall off its screen, started at the document's read
    of the wall's report, after its read of the wall's row. Before, the row was
    read first and who shows what apart from it, so the document said the
    wall's state as the old row placed it after the write had committed and
    Walls said unassigned.
    """
    before = _walls_state(services, wall_id)
    assert before != "unassigned", "the wall must be shown before the write, or there is nothing to tell apart"
    writer = _WriterBetweenReads(
        monkeypatch, quiet_catalogue_file, observations, "observe", lambda: services.clients.unassign_wall(wall_id)
    )

    document = json.loads(services.clients.label_document(captioned.id))
    writer.finish()

    said = document["display_state"]["state"]
    assert _walls_state(services, wall_id) == "unassigned"
    if writer.committed_while_reading:
        assert said == "unassigned", f"the wall was unassigned while the document was read, and it says {said!r}"
    else:
        assert said == before, f"the write waited for the document, which must say the instant before it: {said!r}"
