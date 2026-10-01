"""HTTP mode: pulling a wall into a local cache, and rendering only from it.

Against a local stub server that serves the contract's own documents on the
contract's own routes (`contract/routes.json`), so these tests pin the client to
the contract rather than to Arrt's code, which a Player in another repository
will not have. `player-contract.md` § Transport is the specification.

**The test this chunk exists for is the one that stops the server while the wall
runs**: the cache is the only thing the wall renders from, so a server that goes
away must change nothing about what is on the wall.
"""

import asyncio
import copy
import hashlib
import json
import logging
from dataclasses import replace
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from conftest import WALL_ID

from postarr.daemon import Daemon
from postarr.manifest import Watcher
from postarr.pull import ETAG_FILENAME, HEARTBEAT_ROUTE, MANIFEST_ROUTE, MEDIA_DIRNAME, Pull

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
ROUTES = json.loads((CONTRACT / "routes.json").read_text(encoding="utf-8"))["routes"]
FIXTURE = json.loads((CONTRACT / "fixtures" / "manifest.v1" / "valid" / "minor-2-with-media.json").read_text())
TOKEN = "this-walls-token"


class Stub:
    """Arrt's Player surface, as the contract describes it, and nothing more."""

    def __init__(self) -> None:
        self.manifest: dict | None = None
        self.media: dict[str, bytes] = {}
        self.tokens = {TOKEN: WALL_ID}
        self.heartbeats: list[bytes] = []
        self.media_status: int | None = None
        self.authorizations: list[str | None] = []
        self.echo_heartbeats_to: Path | None = None

    def app(self) -> web.Application:
        application = web.Application()
        application.router.add_route(ROUTES["manifest"]["method"], ROUTES["manifest"]["path"], self.serve_manifest)
        application.router.add_route(ROUTES["media"]["method"], ROUTES["media"]["path"], self.serve_media)
        application.router.add_route(ROUTES["heartbeat"]["method"], ROUTES["heartbeat"]["path"], self.receive_heartbeat)
        return application

    def _admit(self, request: web.Request, wall_id: str | None) -> web.Response | None:
        header = request.headers.get("Authorization")
        self.authorizations.append(header)
        holder = self.tokens.get((header or "").removeprefix("Bearer "))
        if holder is None:
            return web.json_response({"error": "A valid wall token is required."}, status=401)
        if wall_id is not None and holder != wall_id:
            return web.json_response({"error": "That token is for another wall."}, status=403)
        return None

    async def serve_manifest(self, request: web.Request) -> web.Response:
        refused = self._admit(request, request.match_info["wall_id"])
        if refused is not None:
            return refused
        if self.manifest is None:
            return web.json_response({"error": "Nothing has been published for this wall yet."}, status=404)
        body = json.dumps(self.manifest).encode()
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers={"ETag": etag})
        return web.Response(body=body, content_type="application/json", headers={"ETag": etag})

    async def serve_media(self, request: web.Request) -> web.Response:
        refused = self._admit(request, None)
        if refused is not None:
            return refused
        if self.media_status is not None:
            return web.Response(status=self.media_status)
        data = self.media.get(request.match_info["sha256"])
        if data is None:
            return web.json_response({"error": "No render with that hash is held."}, status=404)
        return web.Response(body=data, content_type="image/jpeg")

    async def receive_heartbeat(self, request: web.Request) -> web.Response:
        refused = self._admit(request, request.match_info["wall_id"])
        if refused is not None:
            return refused
        body = await request.read()
        self.heartbeats.append(body)
        if self.echo_heartbeats_to is not None:
            # What Arrt does with a POSTed heartbeat on a host it shares.
            self.echo_heartbeats_to.write_bytes(body)
        return web.Response(status=204)

    def publish(self, *work_ids: str, sequence: int = 4, renders: dict[str, bytes] | None = None) -> dict:
        """The contract's minor 2 fixture, carrying these works with real bytes behind their hashes."""
        document = copy.deepcopy(FIXTURE)
        template = document["entries"][0]
        document["entries"] = []
        document["directive"]["sequence"] = sequence
        for work_id in work_ids:
            data = (renders or {}).get(work_id, f"the render of {work_id}".encode())
            sha = hashlib.sha256(data).hexdigest()
            self.media[sha] = data
            entry = copy.deepcopy(template)
            entry["work_id"] = work_id
            entry["label"] = {**entry["label"], "title": f"Title of {work_id}"}
            entry["media"] = {"url": f"/media/sha256-{sha}", "sha256": sha, "bytes": len(data), "content_type": "image/jpeg"}
            document["entries"].append(entry)
        self.manifest = document
        return document


@pytest.fixture
async def stub():
    stub = Stub()
    server = TestServer(stub.app())
    await server.start_server()
    stub.server = server
    stub.url = str(server.make_url("")).rstrip("/")
    yield stub
    await server.close()


@pytest.fixture
def http_settings(settings, stub, tmp_path):
    return replace(settings, manifest_source="http", server_url=stub.url, wall_token=TOKEN, cache_dir=tmp_path / "cache")


@pytest.fixture
def pull(http_settings):
    (http_settings.cache_dir / MEDIA_DIRNAME).mkdir(parents=True)
    return Pull(http_settings)


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as client:
        yield client


def _watcher(settings) -> Watcher:
    return Watcher(
        settings.manifest_path,
        rotation_interval_fallback=settings.rotation_interval_fallback_seconds,
        shuffle_fallback=settings.rotation_shuffle_fallback,
    )


def _cached(settings) -> dict | None:
    path = settings.manifest_path
    return json.loads(path.read_text()) if path.exists() else None


def _held(settings) -> set[str]:
    return {path.name for path in (settings.cache_dir / MEDIA_DIRNAME).iterdir()}


# -- the contract's routes ------------------------------------------------------------


def test_the_client_requests_the_routes_the_contract_names():
    assert MANIFEST_ROUTE == ROUTES["manifest"]["path"]
    assert HEARTBEAT_ROUTE == ROUTES["heartbeat"]["path"]
    assert ROUTES["manifest"]["method"] == "GET" and ROUTES["heartbeat"]["method"] == "POST"


def test_http_mode_reads_the_cache_and_renders_from_it(http_settings):
    assert http_settings.manifest_path == http_settings.cache_dir / "manifest.json"
    assert http_settings.render_root == http_settings.cache_dir


def test_file_mode_is_unchanged(settings):
    assert settings.manifest_path == settings.art_root / f"theme-manifest-{WALL_ID}.json"
    assert settings.render_root == settings.art_root


# -- adopting ------------------------------------------------------------------------------


async def test_a_new_manifest_is_cached_only_with_its_renders_verified(pull, stub, session, http_settings):
    published = stub.publish("w1", "w2")

    assert await pull.cycle(session) is True

    cached = _cached(http_settings)
    assert [entry["work_id"] for entry in cached["entries"]] == ["w1", "w2"]
    for entry in cached["entries"]:
        path = http_settings.render_root / entry["render_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["media"]["sha256"]
    # Nothing but the render path is rewritten: the directive, rotation and label
    # are the server's, and the daemon reads them as it would the shared file.
    for key in ("schema", "theme", "rotation", "directive"):
        assert cached[key] == published[key]
    assert [entry["label"] for entry in cached["entries"]] == [entry["label"] for entry in published["entries"]]
    adopted = _watcher(http_settings).poll()
    assert [entry.work_id for entry in adopted.entries] == ["w1", "w2"]


async def test_nothing_is_cached_while_a_render_cannot_be_fetched(pull, stub, session, http_settings):
    stub.publish("w1")
    stub.media_status = 503

    await pull.cycle(session)
    assert _cached(http_settings) is None, "a manifest was cached before its render"

    stub.media_status = None
    await pull.cycle(session)
    assert [entry["work_id"] for entry in _cached(http_settings)["entries"]] == ["w1"]


async def test_an_unchanged_manifest_is_not_downloaded_again(pull, stub, session, http_settings):
    stub.publish("w1")
    await pull.cycle(session)
    etag = (http_settings.cache_dir / ETAG_FILENAME).read_text()

    before = http_settings.manifest_path.stat().st_mtime_ns
    await pull.cycle(session)

    assert (http_settings.cache_dir / ETAG_FILENAME).read_text() == etag
    assert http_settings.manifest_path.stat().st_mtime_ns == before


async def test_a_render_that_does_not_match_its_hash_is_discarded_and_reported_once(pull, stub, session, http_settings, caplog):
    stub.publish("w1", "w2")
    bad = stub.manifest["entries"][1]["media"]["sha256"]
    stub.media[bad] = b"bytes that are not the render"

    with caplog.at_level(logging.WARNING, logger="postarr.pull"):
        await pull.cycle(session)
        stub.publish("w1", "w2", sequence=5)
        stub.media[bad] = b"bytes that are not the render"
        await pull.cycle(session)

    assert [entry["work_id"] for entry in _cached(http_settings)["entries"]] == ["w1"]
    assert f"sha256-{bad}" not in _held(http_settings)
    mismatches = [record for record in caplog.records if "did not match its hash" in record.getMessage()]
    assert len(mismatches) == 1


async def test_the_contract_fixtures_placeholder_hash_is_refused_by_the_bytes(pull, stub, session, http_settings):
    """The fixture's own `media` names a hash no real bytes have, so its render never reaches the cache."""
    stub.manifest = copy.deepcopy(FIXTURE)
    for entry in stub.manifest["entries"]:
        stub.media[entry["media"]["sha256"]] = b"anything"

    await pull.cycle(session)

    assert _cached(http_settings)["entries"] == []


async def test_a_manifest_this_reader_refuses_is_never_cached(pull, stub, session, http_settings, caplog):
    stub.publish("w1")
    await pull.cycle(session)
    stub.manifest = json.loads((CONTRACT / "fixtures" / "manifest.v1" / "invalid" / "major-2.json").read_text())

    with caplog.at_level(logging.ERROR, logger="postarr.pull"):
        await pull.cycle(session)
        await pull.cycle(session)

    assert [entry["work_id"] for entry in _cached(http_settings)["entries"]] == ["w1"]
    assert len([record for record in caplog.records if "refusing the manifest" in record.getMessage()]) == 1


async def test_eviction_removes_a_render_once_two_manifests_in_a_row_have_not_named_it(pull, stub, session, http_settings):
    """One generation of grace.

    The daemon adopts a new manifest on its next poll, and may reach for a render
    only the old one names until then.
    """
    stub.publish("w1", "w2")
    await pull.cycle(session)
    names = {entry["work_id"]: Path(entry["render_path"]).name for entry in _cached(http_settings)["entries"]}

    stub.publish("w2", "w3")
    await pull.cycle(session)
    names.update({entry["work_id"]: Path(entry["render_path"]).name for entry in _cached(http_settings)["entries"]})
    assert _held(http_settings) == {names["w1"], names["w2"], names["w3"]}, "the outgoing manifest's render went early"

    stub.publish("w3", "w4")
    await pull.cycle(session)
    names.update({entry["work_id"]: Path(entry["render_path"]).name for entry in _cached(http_settings)["entries"]})
    assert _held(http_settings) == {names["w2"], names["w3"], names["w4"]}
    assert names["w1"] not in _held(http_settings)


async def test_a_stray_file_in_the_media_cache_is_evicted(pull, stub, session, http_settings):
    stray = http_settings.cache_dir / MEDIA_DIRNAME / "sha256-left-over"
    stray.write_bytes(b"from a crash mid-write")
    stub.publish("w1")

    await pull.cycle(session)

    assert not stray.exists()


# -- refusals and outages keep the cache ------------------------------------------------------


@pytest.mark.parametrize(
    ("holders", "status"),
    [({}, 401), ({TOKEN: "another-wall"}, 403)],
    ids=["token-unknown", "token-for-another-wall"],
)
async def test_a_refused_token_is_reported_once_and_the_cache_is_kept(
    pull, stub, session, http_settings, caplog, holders, status
):
    stub.publish("w1")
    await pull.cycle(session)
    stub.tokens = holders
    stub.publish("w2")

    with caplog.at_level(logging.ERROR, logger="postarr.pull"):
        for _ in range(3):
            assert await pull.cycle(session) is True

    assert [entry["work_id"] for entry in _cached(http_settings)["entries"]] == ["w1"]
    refused = [record for record in caplog.records if record.getMessage().startswith("the server refused")]
    assert len(refused) == 1
    assert refused[0].status == status


async def test_the_server_stopped_while_the_wall_runs_and_rotation_continues_from_the_cache(
    pull, stub, session, http_settings, tv, state, clock
):
    """The test this chunk exists for."""
    stub.publish("w1", "w2")
    await pull.cycle(session)
    daemon = Daemon(settings=http_settings, tv=tv, state=state, watcher=_watcher(http_settings), clock=clock.as_clock())
    await daemon.tick()
    first = tv.on_the_wall

    await stub.server.close()
    assert await pull.cycle(session) is False, "a stopped server was reported as reachable"
    clock.advance(181)
    await daemon.tick()

    assert tv.on_the_wall != first, "the rotation stopped with the server"
    assert tv.on_the_wall.parent == http_settings.cache_dir / MEDIA_DIRNAME
    assert _cached(http_settings) is not None


async def test_a_player_restarted_with_the_server_down_starts_from_its_cache(stub, session, http_settings, pull):
    stub.publish("w1", "w2")
    await pull.cycle(session)
    await stub.server.close()

    restarted = Pull(http_settings)
    assert await restarted.cycle(session) is False
    adopted = _watcher(http_settings).poll()

    assert [entry.work_id for entry in adopted.entries] == ["w1", "w2"]
    for entry in adopted.entries:
        assert (http_settings.render_root / entry.render_path).is_file()


async def test_an_unreachable_server_is_reported_once_and_its_return_once(stub, session, http_settings, caplog):
    stub.publish("w1")
    pull = Pull(http_settings)
    (http_settings.cache_dir / MEDIA_DIRNAME).mkdir(parents=True)
    port = stub.server.port
    await stub.server.close()

    with caplog.at_level(logging.INFO, logger="postarr.pull"):
        for _ in range(3):
            assert await pull.cycle(session) is False
        stub.server = TestServer(stub.app(), port=port)
        await stub.server.start_server()
        for _ in range(2):
            assert await pull.cycle(session) is True

    messages = [record.getMessage() for record in caplog.records]
    assert len([message for message in messages if "cannot be reached" in message]) == 1
    assert len([message for message in messages if "answers again" in message]) == 1


async def test_a_manifest_404_is_reported_once_as_nothing_published(pull, stub, session, caplog):
    with caplog.at_level(logging.ERROR, logger="postarr.pull"):
        for _ in range(3):
            assert await pull.cycle(session) is True

    refused = [record for record in caplog.records if record.getMessage().startswith("the server refused")]
    assert len(refused) == 1
    assert refused[0].status == 404
    assert "published nothing" in refused[0].getMessage()


async def test_a_refusal_ends_on_a_304(pull, stub, session, caplog):
    """The server accepting the token again for a manifest already cached is the end of the refusal."""
    stub.publish("w1")
    await pull.cycle(session)
    holders = stub.tokens
    stub.tokens = {}

    with caplog.at_level(logging.INFO, logger="postarr.pull"):
        await pull.cycle(session)
        stub.tokens = holders
        await pull.cycle(session)
        stub.tokens = {}
        await pull.cycle(session)

    messages = [record.getMessage() for record in caplog.records]
    assert len([message for message in messages if message.startswith("the server refused")]) == 2
    assert len([message for message in messages if "serves this wall's manifest again" in message]) == 1


async def test_a_render_the_server_does_not_hold_is_skipped_and_the_rest_cached(pull, stub, session, http_settings):
    stub.publish("w1", "w2")
    del stub.media[stub.manifest["entries"][0]["media"]["sha256"]]

    assert await pull.cycle(session) is True

    assert [entry["work_id"] for entry in _cached(http_settings)["entries"]] == ["w2"]


async def test_a_work_with_no_usable_media_is_skipped_and_said_once(pull, stub, session, http_settings, caplog):
    stub.publish("w1", "w2")
    del stub.manifest["entries"][0]["media"]

    with caplog.at_level(logging.WARNING, logger="postarr.pull"):
        await pull.cycle(session)
        stub.publish("w1", "w2", sequence=9)
        del stub.manifest["entries"][0]["media"]
        await pull.cycle(session)

    assert [entry["work_id"] for entry in _cached(http_settings)["entries"]] == ["w2"]
    assert len([record for record in caplog.records if "no usable media" in record.getMessage()]) == 1


async def test_a_render_that_keeps_failing_is_said_once_and_backed_off(pull, stub, session, http_settings, caplog):
    stub.publish("w1")
    await pull.cycle(session)
    stub.publish("w2")
    stub.media_status = 503
    heartbeat = http_settings.heartbeat_root / f"display-heartbeat-{WALL_ID}.json"
    heartbeat.write_text(json.dumps({"reported_at": "2026-09-30T12:00:00+00:00"}))

    with caplog.at_level(logging.INFO, logger="postarr.pull"):
        for _ in range(3):
            assert await pull.cycle(session) is False, "a failing render was not backed off"
        # Checked while the render is still failing: the manifest route answered,
        # so the Player must still be heard.
        assert [json.loads(body)["reported_at"] for body in stub.heartbeats] == ["2026-09-30T12:00:00+00:00"]
        stub.media_status = None
        assert await pull.cycle(session) is True

    messages = [record.getMessage() for record in caplog.records]
    assert len([message for message in messages if "could not be fetched" in message]) == 1
    assert len([message for message in messages if "arrive again" in message]) == 1
    assert [entry["work_id"] for entry in _cached(http_settings)["entries"]] == ["w2"]


# -- the token -------------------------------------------------------------------------------


async def test_the_token_never_reaches_the_journal(pull, stub, session, http_settings, caplog):
    with caplog.at_level(logging.DEBUG):
        stub.publish("w1", "w2")
        bad = stub.manifest["entries"][1]["media"]["sha256"]
        stub.media[bad] = b"wrong"
        await pull.cycle(session)
        stub.tokens = {}
        stub.publish("w3")
        await pull.cycle(session)
        await stub.server.close()
        await pull.cycle(session)

    postarr_lines = [record.getMessage() for record in caplog.records if record.name.startswith("postarr")]
    assert postarr_lines, "nothing was logged, so this checks nothing"
    assert all(TOKEN not in line for line in postarr_lines)
    assert all(
        TOKEN not in json.dumps(record.__dict__, default=str) for record in caplog.records if record.name.startswith("postarr")
    )
    assert TOKEN not in repr(http_settings)


async def test_the_token_is_not_sent_to_another_host(pull, stub, session, http_settings):
    """A manifest names where to fetch, so it must not be able to send the token there."""
    elsewhere = Stub()
    other = TestServer(elsewhere.app())
    await other.start_server()
    try:
        stub.publish("w1")
        sha = stub.manifest["entries"][0]["media"]["sha256"]
        elsewhere.media[sha] = stub.media[sha]
        elsewhere.tokens = {"": WALL_ID}
        stub.manifest["entries"][0]["media"]["url"] = str(other.make_url(f"/media/sha256-{sha}"))

        await pull.cycle(session)
    finally:
        await other.close()

    assert elsewhere.authorizations == [None]
    assert [entry["work_id"] for entry in _cached(http_settings)["entries"]] == ["w1"]


# -- the heartbeat ---------------------------------------------------------------------------


async def test_the_heartbeat_file_is_posted_when_it_holds_a_new_report_and_not_otherwise(pull, stub, session, http_settings):
    heartbeat = http_settings.heartbeat_root / f"display-heartbeat-{WALL_ID}.json"
    assert heartbeat.parent == http_settings.cache_dir, "in HTTP mode the Player's heartbeat file is its own"
    stub.publish("w1")
    heartbeat.write_text(json.dumps({"reported_at": "2026-09-30T12:00:00+00:00"}))

    await pull.cycle(session)
    await pull.cycle(session)
    assert [json.loads(body) for body in stub.heartbeats] == [{"reported_at": "2026-09-30T12:00:00+00:00"}]

    # Rewritten with the same report: not a new heartbeat.
    heartbeat.write_text(json.dumps({"reported_at": "2026-09-30T12:00:00+00:00"}, indent=2))
    await pull.cycle(session)
    assert len(stub.heartbeats) == 1

    heartbeat.write_text(json.dumps({"reported_at": "2026-09-30T12:01:00+00:00", "schema": {"major": 1, "minor": 1}}))
    await pull.cycle(session)
    assert len(stub.heartbeats) == 2
    assert json.loads(stub.heartbeats[-1])["reported_at"] == "2026-09-30T12:01:00+00:00"


async def test_a_server_that_writes_the_heartbeat_into_the_shared_tree_causes_no_loop(pull, stub, session, http_settings):
    """The Pi runs both: the server keeps each POSTed heartbeat in ART_ROOT, where its health panel reads it."""
    shared = http_settings.art_root / f"display-heartbeat-{WALL_ID}.json"
    stub.echo_heartbeats_to = shared
    stub.publish("w1")
    (http_settings.heartbeat_root / f"display-heartbeat-{WALL_ID}.json").write_text(
        json.dumps({"reported_at": "2026-09-30T12:00:00+00:00"})
    )

    for _ in range(5):
        await pull.cycle(session)

    assert len(stub.heartbeats) == 1, "each echo was posted again"
    assert json.loads(shared.read_text())["reported_at"] == "2026-09-30T12:00:00+00:00"


async def test_the_pull_stops_when_asked(stub, http_settings):
    stub.publish("w1")
    stop = asyncio.Event()
    running = asyncio.create_task(Pull(http_settings, interval_seconds=0.01).run(stop))
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.wait_for(running, timeout=5)

    assert _cached(http_settings) is not None


async def test_in_http_mode_the_daemon_writes_its_heartbeat_into_the_cache_and_not_the_shared_tree(
    pull, stub, session, http_settings, tv, state, clock
):
    """Where the pull looks for it, and nowhere the server writes."""
    assert http_settings.cache_dir != http_settings.art_root, "the two directories coincide, so this checks nothing"
    stub.publish("w1")
    await pull.cycle(session)
    daemon = Daemon(settings=http_settings, tv=tv, state=state, watcher=_watcher(http_settings), clock=clock.as_clock())

    await daemon.tick()

    assert (http_settings.cache_dir / f"display-heartbeat-{WALL_ID}.json").is_file()
    assert not (http_settings.art_root / f"display-heartbeat-{WALL_ID}.json").exists()
