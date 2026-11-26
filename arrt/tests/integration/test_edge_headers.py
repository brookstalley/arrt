"""What the server's edge says about who may call it, who may frame it, and what it writes down (`arrt.http.hosts`, `arrt.logs`).

**Each case is a hostile request the edge must refuse, or the one that must keep
working beside it**, over a real server. The hostile requests are described by
their headers alone: a page elsewhere sends a plain `GET` with the headers its
browser adds, and that is all these send.

- A `GET` from a page of another site carries no `Origin`, so the guard's `Origin`
  rule never sees it; `Sec-Fetch-Site: cross-site` is what a browser adds, and
  `/api` and `/mcp` refuse it.
- The interface's own requests say `same-origin`; an MCP client, `curl` and a
  Player send no such header. None of those is refused.
- Every HTML response forbids being framed.
- A Player's successful poll writes no access line, and a refused one does.
"""

import json
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

import httpx
import pytest
import uvicorn
from serving import serve

from arrt import logs
from arrt.app import create_app
from arrt.http.hosts import CROSS_SITE_REFUSED_UNDER, ORIGIN_REFUSED

LISTED = "arrt.example"
QID = "Q20267229"
LOOK = f"/api/registry/works/{QID}/look"

_MCP_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}


@pytest.fixture
def guarded_url(services, seeded_service) -> Iterator[str]:
    with serve(create_app(services, allowed_hosts=frozenset({LISTED}))) as url:
        yield url


def _mcp(url: str, **headers: str) -> httpx.Response:
    return httpx.post(
        f"{url}/mcp/",
        json=_MCP_INITIALIZE,
        headers={"accept": "application/json, text/event-stream", **headers},
    )


# -- a cross-site GET -------------------------------------------------------------


@pytest.fixture
def looks_started(services) -> Iterator[mock.MagicMock]:
    """Every call the look service receives, which is what a cross-site GET must not cause."""
    with mock.patch.object(services.look, "look", side_effect=RuntimeError("no registry here")) as spy:
        yield spy


def test_a_cross_site_get_cannot_start_a_look_and_is_refused_before_the_handler(guarded_url, looks_started):
    response = httpx.get(guarded_url + LOOK, headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors"})

    assert response.status_code == ORIGIN_REFUSED
    assert "another site" in response.text
    looks_started.assert_not_called()


def test_the_same_request_from_the_interface_itself_reaches_the_handler(guarded_url, looks_started):
    httpx.get(guarded_url + LOOK, headers={"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors"})

    looks_started.assert_called_once_with(QID)


@pytest.mark.parametrize("site", ["same-origin", "none", "same-site", ""])
def test_every_other_relation_reaches_the_handler_too(guarded_url, looks_started, site):
    """`none` is a typed or bookmarked address; `same-site` is another port on this host, which the Origin rule already judges."""
    httpx.get(guarded_url + LOOK, headers={"Sec-Fetch-Site": site} if site else {})

    looks_started.assert_called_once_with(QID)


def test_a_client_that_sends_no_such_header_reaches_the_handler(guarded_url, looks_started):
    """`curl`, an MCP client or a script: refusing the absent header would refuse every client that is not a browser."""
    httpx.get(guarded_url + LOOK)

    looks_started.assert_called_once_with(QID)


@pytest.mark.parametrize("site", ["cross-site", "Cross-Site"])
@pytest.mark.parametrize("path", ["/api/health", "/api/walls", "/mcp/"])
def test_cross_site_is_refused_on_every_api_and_mcp_route_in_any_spelling(guarded_url, path, site):
    if path == "/mcp/":
        response = _mcp(guarded_url, **{"Sec-Fetch-Site": site})
    else:
        response = httpx.get(guarded_url + path, headers={"Sec-Fetch-Site": site})

    assert response.status_code == ORIGIN_REFUSED


def test_a_cross_site_post_is_refused_too(guarded_url):
    response = httpx.post(guarded_url + "/api/health", headers={"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == ORIGIN_REFUSED


def test_an_mcp_client_with_no_such_header_is_served(guarded_url):
    assert _mcp(guarded_url).status_code == 200


def test_the_mcp_mount_answers_a_same_origin_request(guarded_url):
    assert _mcp(guarded_url, **{"Sec-Fetch-Site": "same-origin"}).status_code == 200


@pytest.mark.parametrize("path", ["/", "/walls", "/static/app.js"])
def test_a_page_and_its_files_load_from_a_link_on_another_site(guarded_url, path):
    """A bookmark or a link in a chat is a cross-site navigation; refusing it would lock the household out of its own pages."""
    response = httpx.get(guarded_url + path, headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"})

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/client", "/walls/some-wall/manifest/v2", "/labels/some-label", "/client/heartbeat"])
def test_the_players_routes_skip_the_guard_and_answer_for_their_token(guarded_url, path):
    """401 is the route's own answer to a request with no token; the guard's would be 403."""
    method = "POST" if path.endswith("heartbeat") else "GET"

    response = httpx.request(
        method, guarded_url + path, headers={"Sec-Fetch-Site": "cross-site"}, json={} if method == "POST" else None
    )

    assert response.status_code == 401


def test_the_refused_prefixes_are_a_path_or_its_parent_and_never_a_lookalike(guarded_url):
    """`/apiary` is not `/api`, so it is the app's 404 and not the guard's 403."""
    assert httpx.get(guarded_url + "/apiary", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 404
    assert set(CROSS_SITE_REFUSED_UNDER) == {"/api", "/mcp"}


# -- framing -----------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/walls", "/queue", "/settings", "/docs", "/redoc"])
def test_every_html_page_forbids_being_framed(guarded_url, path):
    response = httpx.get(guarded_url + path)

    assert response.headers["content-type"].startswith("text/html")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("path", ["/api/health", "/healthz", "/static/app.js", "/openapi.json"])
def test_a_response_that_is_not_a_page_carries_neither(guarded_url, path):
    response = httpx.get(guarded_url + path)

    assert "content-security-policy" not in response.headers
    assert "x-frame-options" not in response.headers


def test_a_refusal_is_not_a_page_and_carries_neither(guarded_url):
    response = httpx.get(guarded_url + "/", headers={"host": "rebound.example"})

    assert response.status_code == 421
    assert "x-frame-options" not in response.headers


def test_a_page_that_already_names_its_own_frame_options_keeps_it_and_gains_no_second():
    from arrt.http.hosts import _unframed

    sent: list[dict] = []

    async def collect(message):
        sent.append(message)

    import asyncio

    asyncio.run(
        _unframed(collect)(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/html"), (b"x-frame-options", b"SAMEORIGIN")],
            }
        )
    )

    names = [name for name, _ in sent[0]["headers"]]
    assert names.count(b"x-frame-options") == 1
    assert dict(sent[0]["headers"])[b"x-frame-options"] == b"SAMEORIGIN"
    assert b"content-security-policy" in names


# -- a Player's polls out of the access log -----------------------------------------


class _AccessLines(logging.Handler):
    """Every line uvicorn's access logger wrote, as the message it formatted."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@contextmanager
def _serving_with_the_access_log(app) -> Iterator[tuple[str, _AccessLines]]:
    """A real uvicorn that writes its access lines, under the logging `configure` installs.

    `serving.serve` runs uvicorn at `warning`, which gates the access logger shut and
    so could not show a line written or dropped. This asks for `info` and leaves
    logging configuration to `logs.configure`, as the entry point does.
    """
    root, access = logging.getLogger(), logging.getLogger("uvicorn.access")
    before = (list(root.handlers), root.level, list(access.filters), access.level)
    seen = _AccessLines()
    logs.configure()
    access.addHandler(seen)
    access.setLevel(logging.INFO)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_config=None, access_log=True)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            pytest.fail("the server did not start within 20 seconds")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", seen
    finally:
        server.should_exit = True
        thread.join(timeout=20)
        access.removeHandler(seen)
        root.handlers, access.filters = before[0], before[2]
        root.setLevel(before[1])
        access.setLevel(before[3])


@pytest.fixture
def logged(services, seeded_service, wall_id) -> Iterator[tuple[str, _AccessLines, str]]:
    client = services.clients.add_client(name="The Pi in the hall")
    services.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    token = services.access.issue(client.id).token
    with _serving_with_the_access_log(create_app(services)) as (url, seen):
        yield url, seen, token


def _lines_for(seen: _AccessLines, fragment: str) -> list[str]:
    return [line for line in seen.lines if fragment in line]


def test_the_control_an_ordinary_request_writes_its_access_line(logged):
    url, seen, _ = logged

    httpx.get(url + "/api/health")

    assert _lines_for(seen, "/api/health"), f"the server wrote no access line, so the cases below prove nothing: {seen.lines}"


def test_a_manifest_poll_answered_304_writes_no_access_line_and_a_refused_one_does(logged, services, wall_id, ready_work):
    url, seen, token = logged
    work = ready_work()
    theme = services.display.add_theme(name="Late night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=wall_id)
    feed = f"/walls/{wall_id}/manifest/v2"
    first = httpx.get(url + feed, headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 200

    unchanged = httpx.get(url + feed, headers={"Authorization": f"Bearer {token}", "If-None-Match": first.headers["etag"]})
    refused = httpx.get(url + feed, headers={"Authorization": "Bearer not-a-token"})
    httpx.get(url + "/api/health")  # written after, so a line still in flight would be seen by now

    assert (first.status_code, unchanged.status_code, refused.status_code) == (200, 304, 401)
    assert _lines_for(seen, feed) == [line for line in seen.lines if feed in line and " 401" in line]
    assert len(_lines_for(seen, feed)) == 1, seen.lines
    assert _lines_for(seen, "/api/health")


def test_a_heartbeat_and_the_client_document_write_no_line_when_they_succeed(logged, wall_id):
    url, seen, token = logged
    bearer = {"Authorization": f"Bearer {token}"}

    client = httpx.get(url + "/client", headers=bearer)
    beat = httpx.post(url + "/client/heartbeat", content=json.dumps({"schema": 1}), headers=bearer)
    missing = httpx.get(url + "/labels/nothing-here", headers=bearer)
    httpx.get(url + "/api/health")

    assert client.status_code == 200
    assert beat.status_code in (204, 400)
    assert not [line for line in _lines_for(seen, "/client") if " 200" in line or " 204" in line]
    assert missing.status_code in (403, 404)
    assert _lines_for(seen, "/labels/nothing-here"), "a failed request keeps its line"
