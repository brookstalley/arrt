"""The Player as a client: one process, one worker per wall the server assigns it.

Driven against the server double (`server_double.py`), with the real workers the
entry point runs — the Frame's loop over a television double, and the screen
loop over a recording output — so what is under test is the supervisor and the
composition together, as the process runs them. `clients.md` § The Player and
`player-contract.md` § Transport are the specification.
"""

import asyncio
import json
import logging
import os
import signal
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest
from aiohttp.test_utils import TestServer
from fakes import FakeTv, RecordingOutput, drm_tree
from server_double import CLIENT_ID, ServerDouble

from postarr import __main__ as entry
from postarr.client import (
    Assignment,
    ClientDocument,
    OutputReport,
    Supervisor,
    client_outputs,
    hdmi_outputs,
)
from postarr.daemon import Clock
from postarr.pull import ClientPull

#: The connectors of a Pi with one screen plugged in and one socket empty — and,
#: beside them, connectors that are not HDMI and must not become outputs.
CONNECTORS = {
    "card1-HDMI-A-1": ("connected", "1920x1080\n1280x720\n"),
    "card1-HDMI-A-2": ("disconnected", ""),
    "card1-Writeback-1": ("unknown", ""),
    "card0-DSI-1": ("connected", "800x480\n"),
}


async def eventually(predicate, *, timeout: float = 5.0, what: str = "the condition") -> None:
    """Wait for something the running process will make true, or fail saying what."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.01)


@pytest.fixture
async def server():
    double = ServerDouble(wall_id="living-room", output="frame")
    test_server = TestServer(double.app())
    await test_server.start_server()
    double.server = test_server
    double.url = str(test_server.make_url("")).rstrip("/")
    yield double
    await double.server.close()


@pytest.fixture
def drm(tmp_path: Path) -> Path:
    return drm_tree(tmp_path / "drm", CONNECTORS)


@pytest.fixture
def client(client_settings, server):
    """This client, pointed at the double, polling fast enough for a test to watch."""
    return replace(client_settings, server_url=server.url, poll_interval_seconds=0.02, client_poll_seconds=0.05)


@pytest.fixture
def screens(monkeypatch) -> dict[str, RecordingOutput]:
    """Every screen output the entry point builds, by wall, recording what it draws."""
    built: dict[str, RecordingOutput] = {}

    def recording(wall, output):
        built[wall.wall_id] = RecordingOutput()
        return built[wall.wall_id]

    monkeypatch.setattr(entry, "screen_output", recording)
    return built


@pytest.fixture
def television(monkeypatch, tv: FakeTv) -> FakeTv:
    monkeypatch.setattr(entry, "SamsungTv", lambda **kwargs: tv)
    return tv


def supervisor_for(client, drm: Path, *, worker=None, link=None, **overrides) -> Supervisor:
    clock = Clock.system()
    return Supervisor(
        settings=client,
        link=link if link is not None else ClientPull(client),
        worker=worker if worker is not None else partial(entry.run_wall, client),
        outputs=partial(client_outputs, client, drm_root=drm),
        now=clock.now,
        monotonic=clock.monotonic,
        **overrides,
    )


class Running:
    """A supervisor running as a task, stopped and awaited on the way out of a test."""

    def __init__(self, supervisor: Supervisor) -> None:
        self.supervisor = supervisor
        self.stop = asyncio.Event()

    async def __aenter__(self) -> Supervisor:
        self.task = asyncio.create_task(self.supervisor.run(self.stop))
        return self.supervisor

    async def __aexit__(self, *exc) -> None:
        self.stop.set()
        await asyncio.wait_for(self.task, timeout=5)


def _shown_ids(output: RecordingOutput, server: ServerDouble, wall_id: str) -> list[str]:
    """The work ids a recording output drew, read back through the renders' hashes."""
    by_hash = {entry["media"]["sha256"]: entry["work_id"] for entry in server.manifests[wall_id]["entries"] if "media" in entry}
    return [by_hash.get(path.name.removeprefix("sha256-"), path.name) for path in output.shown]


# -- walls come and go -------------------------------------------------------------------


async def test_a_wall_assigned_to_this_client_starts_a_worker_that_shows_it(client, server, drm, television):
    server.publish("w1", "w2", wall_id="living-room")

    async with Running(supervisor_for(client, drm)) as supervisor:
        await eventually(lambda: television.on_the_wall is not None, what="the Frame to show the wall")

        assert supervisor.running == {"living-room": "frame"}
        assert television.on_the_wall.parent == client.cache_dir / "living-room" / "media"


async def test_a_wall_assigned_later_is_started_on_the_next_poll(client, server, drm, screens):
    server.unassign("living-room")
    server.publish("h1", wall_id="hall")

    async with Running(supervisor_for(client, drm)) as supervisor:
        await asyncio.sleep(0.15)
        assert supervisor.running == {}, "a client with no walls started one"

        server.assign("hall", "hdmi-a-1")
        await eventually(lambda: "hall" in screens and screens["hall"].shown, what="the new wall to be drawn")
        assert supervisor.running == {"hall": "hdmi-a-1"}


async def test_a_wall_taken_away_stops_its_worker_and_closes_the_art_channel(client, server, drm, television):
    server.publish("w1", wall_id="living-room")

    async with Running(supervisor_for(client, drm)) as supervisor:
        await eventually(lambda: television.on_the_wall is not None, what="the Frame to show the wall")
        server.unassign("living-room")

        await eventually(lambda: supervisor.running == {}, what="the worker to stop")
        await eventually(lambda: television.closed >= 1, what="the art channel to be closed")


class SlowToCloseTv(FakeTv):
    """A set whose art channel takes a moment to close, as a real websocket's does."""

    async def close(self) -> None:
        await asyncio.sleep(0.2)
        await super().close()


async def test_a_wall_moved_to_another_output_is_restarted_there_once_the_old_worker_has_closed(monkeypatch, client, server, drm):
    """**One worker per wall at a time**, even across a move: the new one starts
    only once the old one has finished closing, so two pulls never share the
    wall's directory and the Frame's art channel is closed before anything else
    shows the wall."""
    television = SlowToCloseTv()
    monkeypatch.setattr(entry, "SamsungTv", lambda **kwargs: television)
    closed_at_first_draw: list[int] = []

    class Watching(RecordingOutput):
        def show(self, render):
            if not self.shown:
                closed_at_first_draw.append(television.closed)
            super().show(render)

    screens: dict[str, RecordingOutput] = {}
    monkeypatch.setattr(entry, "screen_output", lambda wall, output: screens.setdefault(wall.wall_id, Watching()))
    server.publish("w1", wall_id="living-room")

    async with Running(supervisor_for(client, drm)) as supervisor:
        await eventually(lambda: television.on_the_wall is not None, what="the Frame to show the wall")
        server.assign("living-room", "hdmi-a-1")

        await eventually(lambda: supervisor.running == {"living-room": "hdmi-a-1"}, what="the move")
        await eventually(lambda: "living-room" in screens and screens["living-room"].shown, what="the screen to draw")

    assert closed_at_first_draw == [1], "the screen drew the wall while the Frame's worker was still closing"


async def test_two_walls_on_two_outputs_each_rotate_their_own_wall(client, server, drm, television, screens):
    """The Frame and a screen at once, from one process, each with only its own works."""
    server.assign("hall", "hdmi-a-1")
    server.publish("lr-1", "lr-2", wall_id="living-room", interval_seconds=1)
    server.publish("hall-1", "hall-2", wall_id="hall", interval_seconds=1)

    async with Running(supervisor_for(client, drm)) as supervisor:
        await eventually(lambda: len(set(television.selected)) >= 2, timeout=8, what="the Frame to rotate")
        await eventually(
            lambda: "hall" in screens and len(set(screens["hall"].shown)) >= 2, timeout=8, what="the screen to rotate"
        )

        assert supervisor.running == {"living-room": "frame", "hall": "hdmi-a-1"}
    on_the_frame = {television.holding[content].name for content in television.selected}
    living_room = {entry["media"]["sha256"] for entry in server.manifests["living-room"]["entries"]}
    assert {name.removeprefix("sha256-") for name in on_the_frame} <= living_room, "the Frame showed another wall's work"
    assert set(_shown_ids(screens["hall"], server, "hall")) == {"hall-1", "hall-2"}
    assert all(path.parent == client.cache_dir / "hall" / "media" for path in screens["hall"].shown)


async def test_a_wall_on_an_output_this_client_lacks_is_reported_once_and_not_started(client, server, drm, screens, caplog):
    server.unassign("living-room")
    server.assign("study", "hdmi-a-3")
    server.assign("hall", "hdmi-a-1")
    server.publish("h1", wall_id="hall")

    with caplog.at_level(logging.ERROR, logger="postarr.client"):
        async with Running(supervisor_for(client, drm)) as supervisor:
            await eventually(lambda: "hall" in screens and screens["hall"].shown, what="the placeable wall to start")
            # A change elsewhere in the document, so it is read again and the
            # same impossible assignment met a second time.
            server.assign("porch", "hdmi-a-2")
            await eventually(lambda: "porch" in supervisor.running, what="the second document to be read")

            assert supervisor.running == {"hall": "hdmi-a-1", "porch": "hdmi-a-2"}

    reports = [record for record in caplog.records if record.__dict__.get("event") == "client.wall_unplaceable"]
    assert len(reports) == 1, f"an unplaceable wall was reported {len(reports)} times"
    assert reports[0].wall_id == "study" and reports[0].output == "hdmi-a-3"


async def test_a_client_with_no_frame_does_not_start_a_wall_assigned_to_one(client, server, drm, caplog):
    without_frame = replace(client, frame=None)
    server.publish("w1", wall_id="living-room")

    with caplog.at_level(logging.ERROR, logger="postarr.client"):
        async with Running(supervisor_for(without_frame, drm)) as supervisor:
            await asyncio.sleep(0.15)
            assert supervisor.running == {}

    assert [record.output for record in caplog.records if record.__dict__.get("event") == "client.wall_unplaceable"] == ["frame"]


# -- every failure keeps the walls running ------------------------------------------------


async def test_the_server_unreachable_keeps_every_worker_on_its_cache(client, server, drm, screens):
    server.unassign("living-room")
    server.assign("hall", "hdmi-a-1")
    server.publish("h1", "h2", wall_id="hall", interval_seconds=1)

    async with Running(supervisor_for(client, drm)) as supervisor:
        await eventually(lambda: "hall" in screens and screens["hall"].shown, what="the wall to be drawn")
        await server.server.close()
        drawn = len(screens["hall"].shown)

        await eventually(lambda: len(screens["hall"].shown) > drawn, timeout=4, what="the wall to rotate from its cache")
        assert supervisor.running == {"hall": "hdmi-a-1"}, "losing the server stopped a wall"
    assert set(_shown_ids(screens["hall"], server, "hall")) == {"h1", "h2"}


async def test_a_client_restarted_while_the_server_is_down_starts_the_walls_it_last_knew(client, server, drm, screens):
    server.unassign("living-room")
    server.assign("hall", "hdmi-a-1")
    server.publish("h1", wall_id="hall")
    async with Running(supervisor_for(client, drm)):
        await eventually(lambda: "hall" in screens and screens["hall"].shown, what="the wall to be drawn")
    await server.server.close()
    screens.clear()

    async with Running(supervisor_for(client, drm)) as restarted:
        await eventually(lambda: "hall" in screens and screens["hall"].shown, what="the wall to be drawn from the cache")
        assert restarted.running == {"hall": "hdmi-a-1"}


@pytest.mark.parametrize(
    "fault",
    ["token-refused", "document-unreadable", "server-error"],
)
async def test_a_client_document_the_server_will_not_give_keeps_the_walls_and_is_said_once(
    client, server, drm, television, caplog, fault
):
    server.publish("w1", wall_id="living-room")

    with caplog.at_level(logging.WARNING, logger="postarr.pull"):
        async with Running(supervisor_for(client, drm)) as supervisor:
            await eventually(lambda: television.on_the_wall is not None, what="the Frame to show the wall")
            if fault == "token-refused":
                server.tokens = {}
            elif fault == "document-unreadable":
                server.client_body = json.dumps({"client_id": CLIENT_ID, "name": "x", "walls": {"living-room": "frame"}}).encode()
            else:
                server.client_status = 503
            await asyncio.sleep(0.3)  # several polls

            assert supervisor.running == {"living-room": "frame"}, "a failed poll stopped a wall"

    events = [record.__dict__.get("event") for record in caplog.records]
    expected = {
        "token-refused": "client.refused",
        "document-unreadable": "client.document_refused",
        "server-error": "client.unreachable",
    }
    assert events.count(expected[fault]) == 1, events


async def test_an_unchanged_client_document_is_asked_for_with_its_etag(client, server):
    link = ClientPull(client)
    try:
        first = await link.fetch()
        second = await link.fetch()
    finally:
        await link.close()

    assert first == ClientDocument(
        client_id=CLIENT_ID, name="The Pi in the hall", walls=(Assignment("living-room", "living-room", "frame"),)
    )
    assert second is None, "an unchanged document was handed over again"
    assert link.cached() == first


# -- a worker that fails ---------------------------------------------------------------------


async def test_a_crashed_worker_is_logged_and_started_again(client, server, drm, caplog):
    calls: list[str] = []

    async def fails_once(wall, output, stop):
        calls.append(wall.wall_id)
        if len(calls) == 1:
            raise RuntimeError("something nobody predicted")
        await stop.wait()

    supervisor = supervisor_for(client, drm, worker=fails_once, restart_min_seconds=0.01, restart_max_seconds=0.05)
    with caplog.at_level(logging.ERROR, logger="postarr.client"):
        async with Running(supervisor):
            await eventually(lambda: len(calls) >= 2, what="the worker to be started again")
            await asyncio.sleep(0.1)
            assert len(calls) == 2, "a worker running normally was restarted"

    crashes = [record for record in caplog.records if record.__dict__.get("event") == "client.worker_crashed"]
    assert len(crashes) == 1
    assert crashes[0].exc_info is not None, "the crash was logged without its traceback"


async def test_a_worker_that_ends_without_being_asked_is_started_again(client, server, drm, caplog):
    calls: list[str] = []

    async def returns_once(wall, output, stop):
        calls.append(wall.wall_id)
        if len(calls) > 1:
            await stop.wait()

    supervisor = supervisor_for(client, drm, worker=returns_once, restart_min_seconds=0.01)
    with caplog.at_level(logging.ERROR, logger="postarr.client"):
        async with Running(supervisor):
            await eventually(lambda: len(calls) >= 2, what="the worker to be started again")

    assert [record.__dict__.get("event") for record in caplog.records].count("client.worker_ended") == 1


async def test_a_stopped_wall_is_not_restarted(client, server, drm):
    calls: list[str] = []

    async def runs(wall, output, stop):
        calls.append(wall.wall_id)
        await stop.wait()

    async with Running(supervisor_for(client, drm, worker=runs, restart_min_seconds=0.01)) as supervisor:
        await eventually(lambda: calls == ["living-room"], what="the worker to start")
        server.unassign("living-room")
        await eventually(lambda: supervisor.running == {}, what="the worker to stop")
        await asyncio.sleep(0.1)

    assert calls == ["living-room"]


# -- the outputs ---------------------------------------------------------------------------


async def test_the_client_heartbeat_reports_the_frame_and_each_hdmi_connector(client, server, drm):
    async with Running(supervisor_for(client, drm)):
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")

    assert server.client_heartbeats[0]["outputs"] == [
        {"name": "frame", "kind": "frame", "connected": True, "screen": None},
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ]


async def test_a_screen_plugged_in_is_reported_at_once_and_an_unchanged_one_is_not_repeated(client, server, drm):
    async with Running(supervisor_for(client, drm)):
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")
        await asyncio.sleep(0.2)
        assert len(server.client_heartbeats) == 1, "an unchanged report was sent on every poll"

        (drm / "card1-HDMI-A-2" / "status").write_text("connected\n")
        (drm / "card1-HDMI-A-2" / "modes").write_text("3840x2160\n")
        await eventually(lambda: len(server.client_heartbeats) == 2, what="the change to be reported")

    assert server.client_heartbeats[1]["outputs"][2] == {
        "name": "hdmi-a-2",
        "kind": "framebuffer",
        "connected": True,
        "screen": [3840, 2160],
    }


def test_a_machine_with_no_drm_directory_has_no_hdmi_outputs(tmp_path):
    assert hdmi_outputs(tmp_path / "absent") == []


def test_a_connector_whose_status_is_not_connected_is_not_claimed(tmp_path):
    drm = drm_tree(tmp_path / "drm", {"card0-HDMI-A-1": ("unknown", "1920x1080\n")})

    assert hdmi_outputs(drm) == [OutputReport(name="hdmi-a-1", kind="framebuffer", connected=False, screen=None)]


def test_one_connector_on_two_cards_is_one_output(tmp_path):
    """No two outputs in one report may share a name, so the server can place a wall by it."""
    drm = drm_tree(
        tmp_path / "drm",
        {"card0-HDMI-A-1": ("connected", "1920x1080\n"), "card1-HDMI-A-1": ("connected", "1280x720\n")},
    )

    assert hdmi_outputs(drm) == [OutputReport(name="hdmi-a-1", kind="framebuffer", connected=True, screen=(1920, 1080))]


def test_a_connected_screen_with_no_mode_listed_has_no_size(tmp_path):
    drm = drm_tree(tmp_path / "drm", {"card1-HDMI-A-1": ("connected", "")})

    assert hdmi_outputs(drm)[0].screen is None


# -- the process ----------------------------------------------------------------------------


async def test_sigterm_stops_every_worker_and_closes_the_art_channel(monkeypatch, client, server, drm, screens):
    """The whole process as systemd runs it: `_run` until SIGTERM, then a clean exit.

    **The art channel is closed before the process returns, not merely asked
    to.** The set's close takes a moment here, so a supervisor that signalled its
    workers and returned without waiting would exit with the channel still open
    — which is what SIGKILL after a timeout would then find.
    """
    television = SlowToCloseTv()
    monkeypatch.setattr(entry, "SamsungTv", lambda **kwargs: television)
    server.assign("hall", "hdmi-a-1")
    server.publish("w1", wall_id="living-room")
    server.publish("h1", wall_id="hall")
    monkeypatch.setattr(entry, "load", lambda: client)
    monkeypatch.setattr(entry, "client_outputs", partial(client_outputs, drm_root=drm))

    running = asyncio.create_task(entry._run())
    await eventually(lambda: television.on_the_wall is not None, what="the Frame to show its wall")
    await eventually(lambda: "hall" in screens and screens["hall"].shown, what="the screen to draw its wall")

    os.kill(os.getpid(), signal.SIGTERM)

    assert await asyncio.wait_for(running, timeout=5) == 0
    assert television.closed >= 1, "the art channel was left open at the set"
