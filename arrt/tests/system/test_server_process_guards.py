"""The guards a server run as a process is held to, each shown to catch what it is for.

The in-process feed guard cannot see into a child process (`conftest.py`, § the
server as a process), so these are its counterparts across the boundary: the
feeds such a server leaves are held to the contract when the test ends; the
paths it would write are resolved before it starts and refused outside the
test's scratch root; and the port it is handed is checked to be its own before
the test talks to it.
"""

import json
import shutil
import tempfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from fakes import open_catalogue
from server_process import ArrtProcess, free_port, serving

from arrt.config import CATALOGUE_FILENAME
from arrt.programming.manifest.v2 import manifest_v2_path_in

pytestmark = pytest.mark.uncacheable("starts the server as a process")


@pytest.fixture
def hung(services, ready_work, wall_id) -> str:
    """One work hung on the wall before any start, so a server publishes the wall's feed; returns the wall's id."""
    theme = services.display.add_theme(name="Late night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)
    services.display.activate_theme(theme.id, wall_id=wall_id)
    return wall_id


def test_a_feed_corrupted_on_disk_before_a_server_test_ends_fails_it_naming_the_wall(settings, hung, tmp_path_factory):
    """Red while nothing read a server process's feeds (until 2026-11-20): the block below ended green."""
    feed = manifest_v2_path_in(settings.art_root, hung)

    def serve_and_corrupt() -> None:
        with serving(settings.art_root, tmp_path_factory.getbasetemp()) as server:
            server.start()
            document = json.loads(feed.read_text(encoding="utf-8"))
            assert document["works"], "the wall's feed carries no work, so dropping them would say nothing"
            del document["works"]
            feed.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(pytest.fail.Exception) as refused:
        serve_and_corrupt()

    assert f"wall {hung} " in str(refused.value)
    assert "'works' is a required property" in str(refused.value)
    assert "--- the server's log ---" in str(refused.value)


def test_a_server_test_whose_feeds_keep_the_contract_ends_green(settings, hung, tmp_path_factory):
    """The other half, anchored: the feed is there and read, and the end of the test finds nothing."""
    with serving(settings.art_root, tmp_path_factory.getbasetemp()) as server:
        base_url = server.start()
        assert httpx.get(f"{base_url}/api/walls").status_code == 200
    assert manifest_v2_path_in(settings.art_root, hung).is_file()


@pytest.fixture
def outside(tmp_path_factory) -> Iterator[Path]:
    """A directory in the system's temporary directory and outside this run's base temporary directory."""
    made = Path(tempfile.mkdtemp(prefix="arrt-escaped-"))
    assert not made.resolve().is_relative_to(tmp_path_factory.getbasetemp().resolve())
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


@pytest.mark.parametrize("setting", ["ART_ROOT", "BACKUP_DIR"])
def test_a_server_whose_paths_escape_its_scratch_root_is_refused_before_it_starts(
    settings, wall_id, tmp_path_factory, outside, setting
):
    """Refused naming the setting, before a process exists and before the escaped directory does.

    The escaped art root is given a catalogue of its own, so a server let through
    would start there and write its feeds, heartbeats and backups outside the run.
    """
    escaped = outside / "root"
    if setting == "ART_ROOT":
        escaped.mkdir()
        open_catalogue(escaped / CATALOGUE_FILENAME).close()
    process = ArrtProcess(art_root=settings.art_root, scratch_root=tmp_path_factory.getbasetemp())
    process.environment = {setting: str(escaped)}
    try:
        with pytest.raises(pytest.fail.Exception, match="would write outside its scratch root"):
            process.start()
    finally:
        process.stop()

    assert process._process is None, "a server was started"
    assert sorted(path.name for path in outside.rglob("*")) == (
        sorted(["root", CATALOGUE_FILENAME]) if setting == "ART_ROOT" else []
    )


def test_a_relative_art_root_is_resolved_where_the_server_runs_and_refused(settings, tmp_path_factory):
    """A relative `ART_ROOT` is relative to the server's working directory, this project's directory in the checkout."""
    process = ArrtProcess(art_root=settings.art_root, scratch_root=tmp_path_factory.getbasetemp())
    process.environment = {"ART_ROOT": "escaped-art-root"}
    with pytest.raises(pytest.fail.Exception, match=r"art_root resolves to .*/arrt/escaped-art-root"):
        process.start()
    assert process._process is None


class _Impostor(BaseHTTPRequestHandler):
    """Answers every request as a server would, so an answer alone cannot say whose it is."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"walls": []}')

    def log_message(self, *_args: object) -> None:
        return


class _HoldsItsPort(ThreadingHTTPServer):
    """No `SO_REUSEADDR`, so the port is held as any other process would hold it."""

    allow_reuse_address = False


def test_a_port_another_server_holds_is_never_taken_for_this_one(settings, wall_id, tmp_path_factory):
    """The race a free port leaves, lost on purpose: another server takes the port first and answers on it.

    Red while a start called the server up when the port answered (until
    2026-11-20): the test was handed the other server's URL. Now the start waits
    for its own server to say it holds the port, sees it lose the port instead,
    and starts it again on another.
    """
    impostor = _HoldsItsPort(("127.0.0.1", 0), _Impostor)
    threading.Thread(target=impostor.serve_forever, daemon=True).start()
    taken = impostor.server_address[1]
    assert httpx.get(f"http://127.0.0.1:{taken}/api/walls").status_code == 200, "the impostor does not answer"
    offered = [taken]
    process = ArrtProcess(art_root=settings.art_root, scratch_root=tmp_path_factory.getbasetemp())
    process.ports = lambda: offered.pop(0) if offered else free_port()
    try:
        base_url = process.start()
        assert base_url != f"http://127.0.0.1:{taken}"
        assert httpx.get(f"{base_url}/api/walls").json()["walls"], "the URL handed back is not this server's"
        assert any("error while attempting to bind on address" in event.get("message", "") for event in process.events())
    finally:
        process.stop()
        impostor.shutdown()
        impostor.server_close()
