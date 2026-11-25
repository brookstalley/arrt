"""What the health answer and the Players answers make the catalogue's other callers wait for, and what wakes them.

Both answers take one reading of the store's rows and of every report file
inside one read scope (`HealthService.observe` through `Walls.read_wall_reports`,
`ClientService.read_clients`), so the store's one lock is held while the report
files are read. Before, the scope held only the row statements and the files
were read after it. Kept as it is, by the decision recorded with this test:
what the hold costs is bounded, and this file holds the bound and the wake.

- **The bound:** under the hold, the health answer reads each wall's report and
  each Player's report once, W + P small files and nothing else from disk (no
  feed is parsed there); a Players answer reads each Player's report once, P
  files. Nothing else a caller of the store waits for is read under it.
- **The wake:** a writer that asks for the store while a report is being read
  is turned away, and runs once the answer's scope ends, after the last report
  is read; what it wrote is in no part of the answer it waited for.

Nothing sleeps: the writer's wait is seen by the lock it waits on
(`_WatchedLock`), and the reading thread goes on only once it has been seen.
"""

import threading
from datetime import UTC, datetime

import pytest

from arrt import observations
from arrt.programming import feeds as feeds_module
from arrt.programming.client_heartbeat import client_heartbeat_path_in

#: The name of the thread that writes while an answer reads.
_WRITER = "the writer"


class _WatchedLock:
    """The store's lock, which says whether the calling thread holds it and when the writer had to wait for it."""

    def __init__(self, real) -> None:
        self._real = real
        self._depth: dict[int, int] = {}
        self.writer_waiting = threading.Event()

    def __enter__(self):
        if threading.current_thread().name == _WRITER and not self._real.acquire(blocking=False):
            self.writer_waiting.set()
            self._real.acquire()
        elif threading.current_thread().name != _WRITER:
            self._real.acquire()
        me = threading.get_ident()
        self._depth[me] = self._depth.get(me, 0) + 1
        return self

    def __exit__(self, *_):
        self._depth[threading.get_ident()] -= 1
        self._real.release()

    def held_here(self) -> bool:
        return self._depth.get(threading.get_ident(), 0) > 0


@pytest.fixture
def household(services, settings):
    """Three walls on two reporting Players, each wall and each Player with a report: W = 3, P = 2."""
    walls = [services.display.survey_walls()[0].wall.id, *(services.display.add_wall(name=n).id for n in ("Study", "Attic"))]
    players = [services.clients.add_client(name=name).id for name in ("Study Pi", "Attic Pi")]
    for player, outputs in zip(players, (2, 1), strict=True):
        services.access.issue(player)
        services.clients.record_heartbeat(
            player,
            {
                "reported_at": datetime.now(UTC).isoformat(),
                "outputs": [
                    {"name": f"hdmi-a-{n}", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]}
                    for n in range(1, outputs + 1)
                ],
            },
        )
    services.clients.assign_wall(walls[0], client_id=players[0], output="hdmi-a-1")
    services.clients.assign_wall(walls[1], client_id=players[0], output="hdmi-a-2")
    services.clients.assign_wall(walls[2], client_id=players[1], output="hdmi-a-1")
    for wall in walls:
        settings.heartbeat_path(wall).write_text(f'{{"reported_at": "{datetime.now(UTC).isoformat()}"}}', encoding="utf-8")
    return {
        "walls": {str(settings.heartbeat_path(wall)) for wall in walls},
        "players": {str(client_heartbeat_path_in(settings.art_root, player)) for player in players},
    }


class _Reads:
    """Every report read and feed parse an answer makes, each with whether the store was held; a writer started at the first."""

    def __init__(self, monkeypatch, store, write) -> None:
        self.lock = _WatchedLock(store._store._lock)
        monkeypatch.setattr(store._store, "_lock", self.lock)
        self.log: list[tuple[str, str, bool]] = []
        self._write = write
        self.writer: threading.Thread | None = None
        observe, parse = observations.observe, feeds_module.read_published_v2

        def observing(path, **keywords):
            self._started()
            self.log.append(("report", str(path), self.lock.held_here()))
            return observe(path, **keywords)

        def parsing(path):
            self.log.append(("feed", str(path), self.lock.held_here()))
            return parse(path)

        monkeypatch.setattr(observations, "observe", observing)
        monkeypatch.setattr(feeds_module, "read_published_v2", parsing)

    def _started(self) -> None:
        """At the first read under the hold, a writer asks for the store, and is seen turned away before the read goes on."""
        if self.writer is not None or not self.lock.held_here():
            return

        def write() -> None:
            self._write()
            self.log.append(("wrote", "", False))

        self.writer = threading.Thread(target=write, name=_WRITER, daemon=True)
        self.writer.start()
        assert self.lock.writer_waiting.wait(10), "the writer was not turned away, so the store was not held during the read"

    def held(self) -> dict[str, int]:
        """Each file read or parsed under the hold, with how many times."""
        held = [path for kind, path, locked in self.log if kind != "wrote" and locked]
        return {path: held.count(path) for path in held}

    def finish(self) -> None:
        assert self.writer is not None, "no read was made under the store's lock, so no writer was turned away"
        self.writer.join(10)
        assert not self.writer.is_alive(), "the writer never got the store after the answer"
        kinds = [kind for kind, _, _ in self.log]
        last_read = max(index for index, kind in enumerate(kinds) if kind != "wrote")
        assert kinds.index("wrote") > last_read, f"the writer ran before the answer's last read: {self.log}"


def test_the_health_answer_holds_the_store_for_each_report_once_and_wakes_a_writer_after_the_last(
    services, store, household, monkeypatch
):
    """W + P report files under the hold and no feed; a wall added meanwhile waits, and is in no part of the answer."""
    reads = _Reads(monkeypatch, store, lambda: services.display.add_wall(name="Porch"))

    reading = services.health.observe()

    reads.finish()
    assert reads.held() == dict.fromkeys(household["walls"] | household["players"], 1), reads.log
    assert "Porch" not in {seen.wall.name for seen in reading.walls}
    assert "Porch" in {view.wall.name for view in services.display.survey_walls()}


def test_a_players_answer_holds_the_store_for_each_players_report_once_and_wakes_a_writer_after_the_last(
    services, store, household, monkeypatch
):
    """P report files under the hold, no wall's and no feed; a Player added meanwhile waits, and is not listed."""
    reads = _Reads(monkeypatch, store, lambda: services.clients.add_client(name="Porch Pi"))

    views = services.clients.list_clients()

    reads.finish()
    assert reads.held() == dict.fromkeys(household["players"], 1), reads.log
    assert "Porch Pi" not in {view.client.name for view in views}
    assert "Porch Pi" in {view.client.name for view in services.clients.list_clients()}
