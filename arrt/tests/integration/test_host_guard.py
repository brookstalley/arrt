"""The Host and Origin guard, over a real server (`arrt.http.hosts`).

**Each case names the request a DNS-rebinding page would make, or the one a
household's own client makes**, and asserts what the server answers. A name is
sent in `Host` while the connection goes to loopback, which is exactly what a
rebound name looks like from the server's side.
"""

from collections.abc import Iterator

import httpx
import pytest
from serving import serve

from arrt.app import create_app
from arrt.http.hosts import ALLOWED_HOSTS_SETTING, HOST_REFUSED, ORIGIN_REFUSED, hostname

LISTED = "arrt.example"
FOREIGN = "rebound.example"

#: A surface a person or an agent uses, one of each kind the guard wraps: the
#: JSON API, the MCP mount, a page, and the static files.
GUARDED = ("/api/health", "/mcp/", "/", "/static/app.js")

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


def get(url: str, path: str, **headers: str) -> httpx.Response:
    # `/mcp` redirects to `/mcp/`, and following it would leave for the name in Host.
    if path == "/mcp/":
        return httpx.post(
            f"{url}{path}",
            json=_MCP_INITIALIZE,
            headers={"accept": "application/json, text/event-stream", **headers},
            timeout=20,
        )
    return httpx.get(f"{url}{path}", headers=headers, timeout=20)


@pytest.mark.parametrize("path", GUARDED)
def test_a_name_nobody_listed_is_refused_and_told_which_setting(guarded_url, path):
    response = get(guarded_url, path, host=f"{FOREIGN}:8770")

    assert response.status_code == HOST_REFUSED
    assert ALLOWED_HOSTS_SETTING in response.text
    assert FOREIGN in response.text


@pytest.mark.parametrize("path", GUARDED)
def test_a_listed_name_is_answered(guarded_url, path):
    response = get(guarded_url, path, host=f"{LISTED}:8770")

    assert response.status_code == 200


@pytest.mark.parametrize("host", ["127.0.0.1:8770", "localhost", "[::1]:8770", "10.1.2.3", "ARRT.Example.:8770"])
def test_an_address_localhost_and_a_listed_name_in_any_case_are_answered(guarded_url, host):
    assert get(guarded_url, "/api/health", host=host).status_code == 200


def test_with_nothing_listed_an_address_is_still_answered(server_url):
    """A fresh install, reached by its address, works before anyone sets anything."""
    assert httpx.get(f"{server_url}/api/health", timeout=20).status_code == 200
    assert get(server_url, "/api/health", host=LISTED).status_code == HOST_REFUSED


@pytest.mark.parametrize("path", GUARDED)
def test_a_foreign_page_is_refused_even_by_a_listed_name(guarded_url, path):
    """A page elsewhere calling the server by its real name: Host passes, Origin gives it away."""
    response = get(guarded_url, path, host=LISTED, origin=f"https://{FOREIGN}")

    assert response.status_code == ORIGIN_REFUSED
    assert FOREIGN in response.text


@pytest.mark.parametrize("origin", [f"http://{LISTED}", f"https://{LISTED}:8443", "http://127.0.0.1:8770"])
def test_arrts_own_page_may_call_it(guarded_url, origin):
    assert get(guarded_url, "/mcp/", host=LISTED, origin=origin).status_code == 200


@pytest.mark.parametrize("origin", ["null", LISTED, f"http://{FOREIGN}@{LISTED}", f"http://{LISTED}/path", "://"])
def test_an_opaque_or_malformed_origin_is_refused(guarded_url, origin):
    """`Origin: null` is what a sandboxed frame or a file page sends, and it is no household page.

    A malformed one is refused rather than skipped, so a shape the parser does
    not expect cannot carry a foreign page past it.
    """
    assert get(guarded_url, "/api/health", host=LISTED, origin=origin).status_code == ORIGIN_REFUSED


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/client"), ("POST", "/client/heartbeat"), ("GET", "/walls/w/manifest/v2"), ("GET", "/labels/l")],
)
def test_the_players_routes_answer_under_any_name(guarded_url, method, path):
    """They take the wall's token instead, so an unlisted name gets the token's answer, not the guard's."""
    response = httpx.request(method, f"{guarded_url}{path}", headers={"host": FOREIGN}, timeout=20)

    assert response.status_code == 401


def test_a_path_like_a_players_but_not_one_is_guarded(guarded_url):
    """The exemption is the Player's routes, not everything that begins like one."""
    assert get(guarded_url, "/client-settings", host=FOREIGN).status_code == HOST_REFUSED
    assert get(guarded_url, "/walls", host=FOREIGN).status_code == HOST_REFUSED


@pytest.mark.parametrize(
    ("header", "name"),
    [
        ("arrt.example:8770", "arrt.example"),
        ("ARRT.example.", "arrt.example"),
        ("[::1]:8770", "::1"),
        ("[fe80::1]", "fe80::1"),
        ("10.0.0.1", "10.0.0.1"),
        ("", ""),
    ],
)
def test_the_name_is_read_without_its_port(header, name):
    assert hostname(header) == name
