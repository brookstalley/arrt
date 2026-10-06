"""A look at a work the library does not hold, over real HTTP and a real MCP client.

What only a booted server shows: the page's poll answers at once and fills in
over later polls as each source answers on the look's own threads, a picture is
served by a key the look minted and by nothing else, and the MCP twin carries the
route's answer in the route's names, holding until the sources have answered.
"""

import asyncio
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from async_http import request
from fakes import FakeRegistry, a_decodable_jpeg, a_roster, an_image
from mcp import types

from arrt.http.api import LOOK_AGAIN
from arrt.library.discovery.images import FoundImage, ImageQuery, ImageSearchFailure
from arrt.library.registry import ItemId, RegistryCreator, RegistryText, RegistryWork
from arrt.library.services.look import ANSWER_KEPT_FOR
from arrt.services.container import Services

TANTRA = ItemId("Q20267229")
NOWHERE = ItemId("Q1005")
ELSEWHERE = ItemId("Q1006")
BILLE = RegistryCreator(qid=ItemId("Q5001"), name=RegistryText("Ejler Bille"))


def a_work(qid: str, title: str) -> RegistryWork:
    return RegistryWork(qid=ItemId(qid), title=RegistryText(title), sitelinks=3, creators=(BILLE,))


class Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.at


class Source:
    """An image source answering by title, after `delay` seconds, or failing."""

    def __init__(
        self, provider: str, holdings: dict[str, Sequence[FoundImage]], *, fails: bool = False, delay: float = 0.0
    ) -> None:
        self._provider = provider
        self.holdings = holdings
        self.fails = fails
        self.delay = delay
        self.asked: list[str] = []

    @property
    def provider(self) -> str:
        return self._provider

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        self.asked.append(query.title)
        time.sleep(self.delay)
        if self.fails:
            raise ImageSearchFailure(f"{self._provider} is down")
        return tuple(self.holdings.get(query.title, ()))

    def fetch_preview(self, url: str) -> bytes | None:
        return a_decodable_jpeg()


def found(title: str, provider: str, *, artist: str = "Ejler Bille", width: int = 2201) -> FoundImage:
    return an_image(
        title,
        artist=artist,
        width=width,
        height=2221,
        provider=provider,
        url=f"https://{provider}.example/{title.replace(' ', '-')}/{width}/{artist.replace(' ', '-')}",
    )


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry(
        works={
            TANTRA: a_work(TANTRA, "Tantra-Vision"),
            NOWHERE: a_work(NOWHERE, "A Painting Nobody Has"),
            ELSEWHERE: a_work(ELSEWHERE, "Swans"),
        }
    )


@pytest.fixture
def smk() -> Source:
    """Slow, so a first poll sees it asking: what SMK does on a bad day."""
    return Source(
        "smk",
        {"Tantra-Vision": [found("Tantra-Vision", "smk")], "Swans": [found("Swans", "smk")]},
        delay=1.0,
    )


@pytest.fixture
def met() -> Source:
    """Holds the title by another painter, which a Get's judge refuses."""
    return Source("met", {"Tantra-Vision": [found("Tantra-Vision", "met", artist="Somebody Else")]})


@pytest.fixture
def artic() -> Source:
    return Source("artic", {}, fails=True)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def services(
    run_threads,
    store,
    discovery_store,
    wall_settings,
    thumbnail_settings,
    settings,
    engine,
    registry,
    kept,
    smk,
    met,
    artic,
    clock,
):
    """The plane with three image sources wired, a registry, and the look's clock in the test's hand."""
    return Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        sources=a_roster(smk, met, artic),
        registry=registry,
        kept=kept,
        spawn=run_threads,
        look_now=clock,
    )


async def look(server_url: str, qid: str) -> httpx.Response:
    return await request("GET", f"{server_url}/api/registry/works/{qid}/look", timeout=10)


async def settled(server_url: str, qid: str) -> dict:
    """Poll as the page does until no source is still being asked."""
    deadline = time.monotonic() + 15
    while True:
        body = (await look(server_url, qid)).json()
        if body["state"] != "asking":
            return body
        assert time.monotonic() < deadline, f"the look never settled: {body}"
        await asyncio.sleep(0.2)


def by_provider(body: dict) -> dict[str, dict]:
    return {source["provider"]: source for source in body["sources"]}


# -- over HTTP -----------------------------------------------------------------------


async def test_the_first_poll_answers_at_once_and_later_polls_fill_in(server_url, smk):
    first = await look(server_url, TANTRA)

    assert first.status_code == 200, first.text
    assert first.json()["state"] == "asking"
    assert by_provider(first.json())["smk"]["state"] == "asking", "the slow source is still being asked"

    body = await settled(server_url, TANTRA)
    sources = by_provider(body)
    assert sources["smk"]["state"] == "found"
    assert sources["smk"]["found"] == 1
    assert smk.asked == ["Tantra-Vision"], "every poll joined the one ask"


async def test_a_source_holding_the_title_by_another_artist_is_refused_and_shows_nothing(server_url):
    body = await settled(server_url, TANTRA)

    met = by_provider(body)["met"]
    assert met["state"] == "refused"
    assert met["refusals"] == ["identity_refused"]
    assert [picture["provider"] for picture in body["pictures"]] == ["smk"]


async def test_one_source_failing_leaves_the_others_answering(server_url, clock):
    body = await settled(server_url, TANTRA)

    artic = by_provider(body)["artic"]
    assert artic["state"] == "unreachable"
    assert artic["retry_at"] == (clock() + timedelta(minutes=10)).isoformat()
    assert by_provider(body)["smk"]["state"] == "found"
    assert body["note"] is None, "a picture was found, so nothing is said about none"


async def test_a_work_no_source_holds_says_so_once_every_source_has_answered(server_url):
    body = await settled(server_url, NOWHERE)

    assert body["state"] == "answered"
    assert body["pictures"] == []
    assert {source["state"] for source in body["sources"]} == {"holds_none", "unreachable"}
    assert body["note"] == "No image source that answered holds a picture of this work now."


async def test_a_held_work_asks_nothing_and_names_the_library_s_work(server_url, services, ready_work, smk):
    work = ready_work()
    services.identity.set_work_identity(work.id, TANTRA)

    body = (await look(server_url, TANTRA)).json()

    assert body["state"] == "held"
    assert body["held_artwork_ids"] == [work.id]
    assert smk.asked == []


async def test_a_malformed_qid_is_refused(server_url):
    response = await look(server_url, "tantra")

    assert response.status_code == 400
    assert "not a Wikidata item id" in response.json()["error"]


async def test_a_picture_is_served_only_for_a_key_this_work_s_look_names(server_url, clock):
    tantra = (await settled(server_url, TANTRA))["pictures"][0]["key"]
    swans = (await settled(server_url, ELSEWHERE))["pictures"][0]["key"]
    pictures = f"{server_url}/api/registry/works/{TANTRA}/look/pictures"

    served = await request("GET", f"{pictures}/{tantra}", timeout=10)
    assert served.status_code == 200, served.text
    assert served.headers["content-type"] == "image/jpeg"
    assert served.content.startswith(b"\xff\xd8\xff")
    large = await request("GET", f"{pictures}/{tantra}", params={"size": "large"}, timeout=10)
    assert large.status_code == 200

    other = await request("GET", f"{pictures}/{swans}", timeout=10)
    assert other.status_code == 404, "another work's key"
    assert other.json() == {"error": LOOK_AGAIN}

    clock.at += ANSWER_KEPT_FOR + timedelta(seconds=1)
    expired = await request("GET", f"{pictures}/{tantra}", timeout=10)
    assert expired.status_code == 404, "a key from a look no longer kept"


# -- over MCP ------------------------------------------------------------------------


async def call(server_url: str, **arguments) -> types.CallToolResult:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        return await session.call_tool("art_discovery", arguments)


async def test_the_mcp_look_holds_until_the_sources_have_answered(server_url, smk):
    started = time.monotonic()
    result = await call(server_url, action="look", qid=TANTRA)
    payload = json.loads(result.content[0].text)

    assert not result.isError, payload
    assert payload["state"] == "answered", "one call carries every answer, the slow source's included"
    assert by_provider(payload)["smk"]["state"] == "found"
    assert time.monotonic() - started >= smk.delay * 0.9, "it waited for the slow source"
    images = [block for block in result.content if isinstance(block, types.ImageContent)]
    assert len(images) == 1
    assert payload["pictures"][0]["image_block_index"] == 0


async def test_the_mcp_look_carries_the_route_s_answer_in_the_route_s_names(server_url):
    route = await settled(server_url, TANTRA)
    result = await call(server_url, action="look", qid=TANTRA)
    tool = json.loads(result.content[0].text)

    assert {key for key in tool if key not in {"success", "notice"}} == set(route)
    for key in ("qid", "state", "note", "held_artwork_ids", "sources"):
        assert tool[key] == route[key], key
    assert [{k: v for k, v in p.items() if k != "image_block_index"} for p in tool["pictures"]] == route["pictures"]


async def test_the_mcp_look_at_a_held_work_says_so_as_the_route_does(server_url, services, ready_work):
    work = ready_work()
    services.identity.set_work_identity(work.id, TANTRA)

    result = await call(server_url, action="look", qid=TANTRA)
    payload = json.loads(result.content[0].text)

    assert payload["state"] == "held"
    assert payload["held_artwork_ids"] == [work.id]
    assert [block for block in result.content if isinstance(block, types.ImageContent)] == []
