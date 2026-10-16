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
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import pytest
from aiohttp.test_utils import TestServer
from fakes import FakeTv, RecordingOutput, drm_tree
from server_double import CLIENT_ID, ServerDouble

from arrt_player import __main__ as entry
from arrt_player.client import (
    Assignment,
    ClientDocument,
    FrameIdentity,
    LabelAssignment,
    LabelOutputReport,
    OutputReport,
    Supervisor,
    client_outputs,
    hdmi_outputs,
)
from arrt_player.compose import Geometry, composed_path, mat_mode
from arrt_player.config import COMPOSED_DIRNAME, ClientSettings
from arrt_player.pull import ClientPull
from arrt_player.wall import Clock

#: The connectors of a Pi with one screen plugged in and one socket empty — and,
#: beside them, connectors that are not HDMI and must not become outputs.
CONNECTORS = {
    "card1-HDMI-A-1": ("connected", "1920x1080\n1280x720\n"),
    "card1-HDMI-A-2": ("disconnected", ""),
    "card1-Writeback-1": ("unknown", ""),
    "card0-DSI-1": ("connected", "800x480\n"),
}


async def eventually(
    predicate,
    *,
    timeout: float = 5.0,  # noqa: ASYNC109 -- a test helper's own deadline, not a cancellation scope
    what: str = "the condition",
) -> None:
    """Wait for something the running process will make true, or fail saying what."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.01)


@pytest.fixture
async def server():
    double = ServerDouble(wall_id="living-room", output="frame")
    # These tests run the process on the system clock, so its schedules start now.
    double.schedule_starts = datetime.now(UTC).replace(microsecond=0)
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


def supervisor_for(client, drm: Path, *, worker=None, link=None, outputs=None, **overrides) -> Supervisor:
    clock = Clock.system()
    return Supervisor(
        settings=client,
        link=link if link is not None else ClientPull(client),
        worker=worker if worker is not None else partial(entry.run_wall, client),
        outputs=outputs if outputs is not None else partial(client_outputs, client, drm_root=drm),
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


def _pictures(server: ServerDouble, wall_dir: Path, geometry: Geometry) -> dict[Path, str]:
    """Each work of a wall's feed by the file it composes to for `geometry`."""
    feed = server.manifests[wall_dir.name]
    mode = mat_mode((feed.get("settings") or {}).get("mat", {}).get("mode"))
    return {
        composed_path(
            wall_dir / COMPOSED_DIRNAME,
            master_sha256=work["media"]["sha256"],
            mat_color=work["mat_color"],
            mode=mode,
            geometry=geometry,
        ): work_id
        for work_id, work in feed["works"].items()
    }


def _shown_ids(output: RecordingOutput, server: ServerDouble, client: ClientSettings, wall_id: str) -> list[str]:
    """The work ids a recording output drew, read back through the files their masters compose to."""
    by_picture = _pictures(server, client.cache_dir / wall_id, client.wall(wall_id).geometry_for(output.screen))
    return [by_picture.get(path, path.name) for path in output.shown]


# -- walls come and go -------------------------------------------------------------------


async def test_a_wall_assigned_to_this_client_starts_a_worker_that_shows_it(client, server, drm, television):
    server.publish("w1", "w2", wall_id="living-room")

    async with Running(supervisor_for(client, drm)) as supervisor:
        await eventually(lambda: television.on_the_wall is not None, what="the Frame to show the wall")

        assert supervisor.running == {"living-room": "frame"}
        assert television.on_the_wall.parent == client.cache_dir / "living-room" / COMPOSED_DIRNAME


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


async def test_two_walls_on_two_outputs_each_follow_their_own_schedule(client, server, drm, television, screens):
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
    on_the_frame = {television.holding[content] for content in television.selected}
    living_room = _pictures(server, client.cache_dir / "living-room", client.frame_wall("living-room").geometry)
    assert on_the_frame <= set(living_room), "the Frame showed another wall's work"
    assert set(_shown_ids(screens["hall"], server, client, "hall")) == {"hall-1", "hall-2"}
    assert all(path.parent == client.cache_dir / "hall" / COMPOSED_DIRNAME for path in screens["hall"].shown)


async def test_a_wall_on_an_output_this_client_lacks_is_reported_once_and_not_started(client, server, drm, screens, caplog):
    server.unassign("living-room")
    server.assign("study", "hdmi-a-3")
    server.assign("hall", "hdmi-a-1")
    server.publish("h1", wall_id="hall")

    with caplog.at_level(logging.ERROR, logger="arrt_player.client"):
        async with Running(supervisor_for(client, drm)) as supervisor:
            await eventually(lambda: "hall" in screens and screens["hall"].shown, what="the placeable wall to start")
            # A change elsewhere in the document, so it is read again and the
            # same impossible assignment met a second time.
            server.assign("porch", "hdmi-a-2")
            await eventually(lambda: "porch" in supervisor.running, what="the second document to be read")

            assert supervisor.running == {"hall": "hdmi-a-1", "porch": "hdmi-a-2"}

    reports = [record for record in caplog.records if record.__dict__.get("event") == "client.wall_unplaceable"]
    assert len(reports) == 1, f"an unplaceable wall was reported {len(reports)} times"
    assert reports[0].wall_id == "study"
    assert reports[0].output == "hdmi-a-3"


async def test_a_client_with_no_frame_does_not_start_a_wall_assigned_to_one(client, server, drm, caplog):
    without_frame = replace(client, frame=None)
    server.publish("w1", wall_id="living-room")

    with caplog.at_level(logging.ERROR, logger="arrt_player.client"):
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
    assert set(_shown_ids(screens["hall"], server, client, "hall")) == {"h1", "h2"}


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

    with caplog.at_level(logging.WARNING, logger="arrt_player.pull"):
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


def _etag_not_utf8(path: Path) -> None:
    path.write_bytes(b'\xff\xfe"stale"')


def _etag_unreadable(path: Path) -> None:
    path.unlink()
    path.mkdir()


@pytest.mark.parametrize("spoil", [_etag_not_utf8, _etag_unreadable], ids=["not-utf8", "unreadable"])
async def test_a_spoiled_etag_is_not_sent_and_the_whole_document_comes_back(client, server, spoil):
    from arrt_player import pull as pull_module

    link = ClientPull(client)
    try:
        first = await link.fetch()
        spoil(client.cache_dir / pull_module.CLIENT_ETAG_FILENAME)
        sent_before = len(server.requests)
        second = await link.fetch()
    finally:
        await link.close()

    assert second == first, "a spoiled ETag cost the client its document"
    assert len(server.requests) == sent_before + 1


async def test_a_client_document_that_cannot_be_cached_still_starts_its_walls_and_is_said_once(
    monkeypatch, client, server, drm, television, caplog
):
    """A full disk costs the cache, not the walls: the supervisor gets the
    document all the same, and the failure is said once over several polls."""
    from arrt_player import pull as pull_module

    cache_files = {client.client_document_path, client.cache_dir / pull_module.CLIENT_ETAG_FILENAME}
    write = pull_module._write_atomically

    def disk_full_for_the_client_cache(path: Path, data: bytes) -> None:
        if path in cache_files:
            raise OSError(28, "No space left on device")
        write(path, data)

    monkeypatch.setattr(pull_module, "_write_atomically", disk_full_for_the_client_cache)
    server.publish("w1", wall_id="living-room")

    with caplog.at_level(logging.INFO, logger="arrt_player.pull"):
        async with Running(supervisor_for(client, drm)) as supervisor:
            await eventually(lambda: television.on_the_wall is not None, what="the Frame to show the wall")
            await asyncio.sleep(0.3)  # several polls
            assert supervisor.running == {"living-room": "frame"}

    events = [record.__dict__.get("event") for record in caplog.records]
    assert events.count("client.cache_unwritable") == 1, events
    assert "client.cache_writable" not in events, "the cache was said to recover while every write failed"
    assert not client.client_document_path.exists()


# -- a worker that fails ---------------------------------------------------------------------


async def test_a_crashed_worker_is_logged_and_started_again(client, server, drm, caplog):
    calls: list[str] = []

    async def fails_once(wall, output, stop):
        calls.append(wall.wall_id)
        if len(calls) == 1:
            raise RuntimeError("something nobody predicted")
        await stop.wait()

    supervisor = supervisor_for(client, drm, worker=fails_once, restart_min_seconds=0.01, restart_max_seconds=0.05)
    with caplog.at_level(logging.ERROR, logger="arrt_player.client"):
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
    with caplog.at_level(logging.ERROR, logger="arrt_player.client"):
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


# -- the Frame's identity ----------------------------------------------------------------------


def identified(client, tv: FakeTv) -> FrameIdentity:
    return FrameIdentity(tv.read_identity, budget_seconds=1.0)


def supervisor_with_identity(client, drm: Path, identity: FrameIdentity, **overrides) -> Supervisor:
    return supervisor_for(
        client,
        drm,
        outputs=lambda: client_outputs(client, drm_root=drm, frame_identity=identity.value),
        frame_identity=identity,
        **overrides,
    )


async def test_a_frame_with_no_wall_on_it_still_reports_its_identity(client, server, drm, tv):
    """**The case the identity exists for.** A Frame moved to a new client has no
    wall there yet; it must say who it is for its walls to follow it. Read through
    the television double, with no worker running and no art channel opened."""
    server.unassign("living-room")
    identity = identified(client, tv)

    async with Running(supervisor_with_identity(client, drm, identity)) as supervisor:
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")
        assert supervisor.running == {}, "a worker ran, so this is not the no-wall case"

    frame = server.client_heartbeats[0]["outputs"][0]
    assert frame == {"name": "frame", "kind": "frame", "connected": True, "screen": None, "identity": tv.device_id}
    assert tv.connects == 0, "the identity read opened the art channel"


async def test_hdmi_outputs_report_no_identity(client, server, drm, tv):
    identity = identified(client, tv)

    async with Running(supervisor_with_identity(client, drm, identity, worker=_idle)):
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")

    hdmi = [output for output in server.client_heartbeats[0]["outputs"] if output["kind"] == "framebuffer"]
    assert hdmi, "no HDMI output was reported, so this proves nothing"
    assert all("identity" not in output for output in hdmi)


async def test_a_frame_whose_id_cannot_be_read_is_reported_without_one_and_said_once(client, server, drm, tv, caplog):
    tv.unavailable = True
    identity = identified(client, tv)
    supervisor = supervisor_with_identity(client, drm, identity, worker=_idle)

    with caplog.at_level(logging.WARNING, logger="arrt_player.client"):
        for _ in range(3):
            await supervisor.cycle()
    await supervisor.stop_all()

    assert tv.identity_reads == 3, "the read was not tried again on each report"
    assert "identity" not in server.client_heartbeats[0]["outputs"][0]
    unreadable = [record for record in caplog.records if record.__dict__.get("event") == "client.identity_unreadable"]
    assert len(unreadable) == 1, "an unreadable identity was said on every report"


async def test_an_identity_read_late_is_reported_at_once_and_then_never_read_again(client, server, drm, tv):
    """A set asleep at boot is identified once it answers; once read, the
    identity is kept, so a later failed read cannot make it flap away."""
    tv.unavailable = True
    identity = identified(client, tv)
    supervisor = supervisor_with_identity(client, drm, identity, worker=_idle)

    await supervisor.cycle()
    tv.unavailable = False
    await supervisor.cycle()
    tv.unavailable = True
    await supervisor.cycle()
    await supervisor.stop_all()

    assert [beat["outputs"][0].get("identity") for beat in server.client_heartbeats] == [None, tv.device_id]
    assert tv.identity_reads == 2


async def test_an_identity_read_that_hangs_costs_the_report_its_identity_and_nothing_else(client, server, drm):
    async def hangs() -> str:
        await asyncio.Event().wait()
        return "never"

    identity = FrameIdentity(hangs, budget_seconds=0.05)
    supervisor = supervisor_with_identity(client, drm, identity, worker=_idle)

    await asyncio.wait_for(supervisor.cycle(), timeout=5)
    await supervisor.stop_all()

    assert server.client_heartbeats, "a hung read held the report back"
    assert "identity" not in server.client_heartbeats[0]["outputs"][0]


async def test_the_entry_point_reads_the_identity_from_the_frames_rest_description(monkeypatch, client, server, drm, tv):
    """The composition root's wiring: a `FrameIdentity` over the Frame's own client."""
    monkeypatch.setattr(entry, "SamsungTv", lambda **kwargs: tv)
    monkeypatch.setattr(entry, "load", lambda: client)
    monkeypatch.setattr(entry, "client_outputs", partial(_outputs_beside, drm))
    server.unassign("living-room")

    running = asyncio.create_task(entry._run())
    try:
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")
    finally:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(running, timeout=5)

    assert server.client_heartbeats[0]["outputs"][0]["identity"] == tv.device_id


def _outputs_beside(drm: Path, settings, *, frame_identity=None):
    return client_outputs(settings, drm_root=drm, frame_identity=frame_identity)


async def _idle(wall, output, stop):
    await stop.wait()


# -- label outputs -----------------------------------------------------------------------------

LABEL_DOCUMENT = {
    "schema": {"major": 1, "minor": 0},
    "wall_id": "living-room",
    "wall_name": "Living room",
    "display_state": {"state": "showing_art", "work_id": "w1", "since": "2026-10-08T16:00:00Z"},
    "label": {"title": "Cat Litter"},
}


class RecordingLabels:
    """A label worker that records what it was started for, and how it was stopped."""

    def __init__(self) -> None:
        self.started: list[LabelAssignment] = []
        self.stopped: list[tuple[LabelAssignment, bool]] = []

    async def __call__(self, assignment, stop, retired) -> None:
        self.started.append(assignment)
        await stop.wait()
        self.stopped.append((assignment, retired.is_set()))


def with_a_panel(client, drm, labels, **overrides) -> Supervisor:
    report = LabelOutputReport(name="epd-0", kind="epaper", connected=True, size=(1448, 1072))
    return supervisor_for(client, drm, worker=_idle, label_worker=labels, label_outputs=lambda: [report], **overrides)


async def test_a_mapped_label_output_starts_a_renderer_and_an_unmapped_one_retires_it(client, server, drm):
    labels = RecordingLabels()
    server.map_label("label-1", "epd-0", "a-wall-on-another-client", LABEL_DOCUMENT)

    async with Running(with_a_panel(client, drm, labels)) as supervisor:
        await eventually(lambda: labels.started, what="the renderer to start")
        assert supervisor.labels == {"epd-0": LabelAssignment("label-1", "epd-0", "a-wall-on-another-client")}

        server.unmap_label("label-1")
        await eventually(lambda: labels.stopped, what="the renderer to stop")
        assert supervisor.labels == {}

    assert labels.stopped == [(labels.started[0], True)], "a label that captions no wall was not retired"


async def test_a_label_moved_to_another_wall_is_restarted_not_retired(client, server, drm):
    labels = RecordingLabels()
    server.map_label("label-1", "epd-0", "living-room", LABEL_DOCUMENT)

    async with Running(with_a_panel(client, drm, labels)):
        await eventually(lambda: labels.started, what="the renderer to start")
        server.map_label("label-2", "epd-0", "study", {**LABEL_DOCUMENT, "wall_id": "study"})
        await eventually(lambda: len(labels.started) == 2, what="the renderer to start again")

    assert labels.stopped[0] == (LabelAssignment("label-1", "epd-0", "living-room"), False)
    assert labels.started[1] == LabelAssignment("label-2", "epd-0", "study")


async def test_a_client_going_down_stops_its_renderers_without_retiring_them(client, server, drm):
    """The panel keeps what it last showed through a restart; blanking it would flash every restart."""
    labels = RecordingLabels()
    server.map_label("label-1", "epd-0", "living-room", LABEL_DOCUMENT)

    async with Running(with_a_panel(client, drm, labels)):
        await eventually(lambda: labels.started, what="the renderer to start")

    assert labels.stopped == [(labels.started[0], False)]


async def test_a_label_on_an_output_this_client_lacks_is_reported_once_and_not_started(client, server, drm, caplog):
    labels = RecordingLabels()
    server.map_label("label-1", "epd-7", "living-room", LABEL_DOCUMENT)

    with caplog.at_level(logging.ERROR, logger="arrt_player.client"):
        async with Running(with_a_panel(client, drm, labels)):
            await eventually(lambda: len(server.client_heartbeats) >= 1, what="a poll")
            await asyncio.sleep(0.2)

    assert labels.started == []
    unplaceable = [record for record in caplog.records if record.__dict__.get("event") == "client.label_unplaceable"]
    assert len(unplaceable) == 1


async def test_two_labels_on_one_output_start_one_renderer(client, server, drm, caplog):
    labels = RecordingLabels()
    server.map_label("label-1", "epd-0", "living-room", LABEL_DOCUMENT)
    server.clients[CLIENT_ID]["labels"].append({"label_id": "label-2", "output": "epd-0", "wall_id": "study"})

    with caplog.at_level(logging.ERROR, logger="arrt_player.client"):
        async with Running(with_a_panel(client, drm, labels)):
            await eventually(lambda: labels.started, what="the renderer to start")
            await asyncio.sleep(0.2)

    assert [assignment.label_id for assignment in labels.started] == ["label-1"]
    assert [record.__dict__.get("event") for record in caplog.records].count("client.label_unplaceable") == 1


async def test_a_crashed_renderer_is_logged_and_started_again(client, server, drm, caplog):
    calls: list[str] = []

    async def fails_once(assignment, stop, retired):
        calls.append(assignment.label_id)
        if len(calls) == 1:
            raise RuntimeError("something nobody predicted")
        await stop.wait()

    server.map_label("label-1", "epd-0", "living-room", LABEL_DOCUMENT)
    supervisor = with_a_panel(client, drm, fails_once, restart_min_seconds=0.01, restart_max_seconds=0.05)
    with caplog.at_level(logging.ERROR, logger="arrt_player.client"):
        async with Running(supervisor):
            await eventually(lambda: len(calls) >= 2, what="the renderer to be started again")

    crashes = [record for record in caplog.records if record.__dict__.get("event") == "client.label_crashed"]
    assert len(crashes) == 1
    assert crashes[0].__dict__.get("label_id") == "label-1"


async def test_the_client_heartbeat_reports_the_panel_and_a_client_without_one_reports_no_label_outputs(client, server, drm):
    async with Running(with_a_panel(client, drm, RecordingLabels())):
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")
    with_panel = server.client_heartbeats[-1]

    server.client_heartbeats.clear()
    async with Running(supervisor_for(client, drm, worker=_idle)):
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")
    without = server.client_heartbeats[-1]

    assert with_panel["label_outputs"] == [{"name": "epd-0", "kind": "epaper", "connected": True, "size": [1448, 1072]}]
    assert "label_outputs" not in without


async def test_a_panel_whose_health_changes_is_reported_at_once(client, server, drm):
    connected = {"now": True}

    def label_outputs():
        return [LabelOutputReport(name="epd-0", kind="epaper", connected=connected["now"], size=(1448, 1072))]

    supervisor = supervisor_for(client, drm, worker=_idle, label_worker=RecordingLabels(), label_outputs=label_outputs)
    async with Running(supervisor):
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")
        connected["now"] = False
        await eventually(lambda: len(server.client_heartbeats) == 2, what="the panel's failure to be reported")

    assert server.client_heartbeats[1]["label_outputs"][0]["connected"] is False


async def test_the_entry_point_draws_a_mapped_label_on_its_panel(monkeypatch, client, server, drm, tv):
    """**Through the composition root**: the panel opened once, a renderer per
    mapping polling the label route, and the panel closed on the way out."""
    from fakes import FakeSurface

    surface = FakeSurface()
    monkeypatch.setattr(entry, "SamsungTv", lambda **kwargs: tv)
    monkeypatch.setattr(entry, "label_surface", lambda _settings: surface)
    monkeypatch.setattr(entry, "client_outputs", partial(_outputs_beside, drm))
    with_panel = replace(client, frame=None, panel=replace(client.panel, epd_device="omni_epd.mock"), label_poll_seconds=0.02)
    monkeypatch.setattr(entry, "load", lambda: with_panel)
    server.unassign("living-room")
    server.map_label("label-1", "epd-0", "a-wall-on-another-client", LABEL_DOCUMENT)

    running = asyncio.create_task(entry._run())
    try:
        await eventually(lambda: surface.shown, what="the label to be drawn")
        await eventually(lambda: server.client_heartbeats, what="the client heartbeat")
    finally:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(running, timeout=5)
        surface.release.set()

    assert surface.last_text == ["Cat Litter"]
    assert all(output["kind"] != "frame" for output in server.client_heartbeats[0]["outputs"]), "a panel needs no Frame"
    assert server.client_heartbeats[0]["label_outputs"][0]["name"] == "epd-0"
    assert surface.closed == 1, "the panel was not powered down on the way out"
