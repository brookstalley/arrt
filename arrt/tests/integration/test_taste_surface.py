"""Taste over real HTTP and over the mounted tool surface.

Against a real uvicorn server rather than an in-process transport, per this
suite's standing rule: Starlette does not run a mounted sub-app's lifespan, so an
in-process test would pass against an application whose every MCP request fails.

**The rule this file holds at the boundary** is that `inferred` is refused on the
write path *only*: no caller can write one, and the ones the catalogue already
holds load and render with their rationale.
"""

import asyncio
import json
from datetime import UTC, datetime

import httpx

from arrt.persistence.discovery_records import Affinity, AffinityDerivation, AffinitySentiment
from arrt.persistence.records import VocabularyKind


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """One MCP tool call over the mounted surface, as an agent would make it."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


def set_taste(server_url: str, **body) -> httpx.Response:
    return httpx.post(f"{server_url}/api/affinities", json=body, timeout=20)


def taste(server_url: str, **params) -> dict:
    return httpx.get(f"{server_url}/api/affinities", params=params, timeout=20).json()


# -- the taste routes ---------------------------------------------------------


def test_a_reaction_writes_a_stated_judgment_the_screen_can_read_back(server_url):
    """The write every reaction makes, at the boundary the client sees."""
    written = set_taste(server_url, kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)

    assert written.status_code == 200
    assert written.json()["derivation"] == "stated"
    assert written.json()["rationale"] is None
    listed = taste(server_url)
    assert listed["count"] == 1
    assert listed["affinities"][0]["value"] == "Kandinsky"
    assert listed["affinities"][0]["open_to_more"] is True


def test_the_two_fields_hold_meh_but_open_to_more(server_url):
    """Q13's example, written down. One warmth score cannot express it.

    "Tell me more" is `cool` and still open, which a single scalar renders as a
    low number indistinguishable from "never show me this again" — and the
    curator's honest lukewarm reaction would then blacklist an artist they
    explicitly asked to keep hearing about.
    """
    written = set_taste(server_url, kind="artist", value="Magritte", sentiment="cool", open_to_more=True).json()

    assert (written["sentiment"], written["open_to_more"]) == ("cool", True)


def test_setting_observed_over_http_is_refused_in_the_one_error_shape(server_url):
    response = set_taste(
        server_url,
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="observed",
        rationale="accepted four of their works",
    )

    assert response.status_code == 400
    assert "review" in response.json()["error"]


def test_forgetting_a_judgment_answers_with_what_was_forgotten(server_url):
    written = set_taste(server_url, kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False).json()

    forgotten = httpx.delete(f"{server_url}/api/affinities/{written['affinity_id']}", timeout=20)

    assert forgotten.status_code == 200
    assert forgotten.json()["value"] == "Kandinsky"
    assert taste(server_url)["count"] == 0


def test_the_listing_narrows_by_kind(server_url):
    set_taste(server_url, kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)
    set_taste(server_url, kind="movement", value="Bauhaus", sentiment="declines", open_to_more=False)

    assert [entry["value"] for entry in taste(server_url, kind="artist")["affinities"]] == ["Kandinsky"]


async def test_the_tool_and_the_route_call_the_same_fields_the_same_things(server_url):
    """Parity, over the wire on both sides.

    Two surfaces that name one fact differently is how an agent and a click come
    to disagree about the same taste, and it is invisible to either surface's own
    tests.
    """
    await asyncio.to_thread(set_taste, server_url, kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)

    payload, errored = await call(server_url, "art_taste", action="list")

    assert errored is False
    over_http = (await asyncio.to_thread(taste, server_url))["affinities"][0]
    assert payload["affinities"][0] == over_http


async def test_the_tool_refuses_observed_and_says_which_path_can_write_it(server_url):
    payload, errored = await call(
        server_url,
        "art_taste",
        action="set",
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="observed",
        rationale="accepted four of their works",
    )

    assert errored is True
    assert "review" in payload["error"]
    assert (await asyncio.to_thread(taste, server_url))["count"] == 0


# -- inferred: refused on the write, held on the read --------------------------


def test_setting_inferred_over_http_is_refused_and_writes_nothing(server_url):
    response = set_taste(
        server_url,
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="inferred",
        rationale="they asked for calm grids",
    )

    assert response.status_code == 400
    assert "not stored" in response.json()["error"]
    assert taste(server_url)["count"] == 0


async def test_the_tool_refuses_inferred_and_says_what_it_can_write(server_url):
    payload, errored = await call(
        server_url,
        "art_taste",
        action="set",
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="inferred",
        rationale="they asked for calm grids",
    )

    assert errored is True
    assert "stated" in payload["error"]
    assert (await asyncio.to_thread(taste, server_url))["count"] == 0


def test_an_inferred_judgment_already_held_loads_and_renders(server_url, services):
    """**The rule is on the write path only.**

    Seeded through the store, because no surface can write one. The count is
    asserted before the fields, since an assertion over an empty list is
    vacuously true, and "renders" is the row coming back through the read the
    Taste screen makes with everything it draws present.
    """
    now = datetime.now(UTC)
    services.discovery._store.add_affinity(
        Affinity(
            id="affinity-held",
            kind=VocabularyKind.ARTIST,
            value="Agnes Martin",
            sentiment=AffinitySentiment.LOVES,
            open_to_more=True,
            derivation=AffinityDerivation.INFERRED,
            created_at=now,
            updated_at=now,
            rationale="they asked for stillness, and said the room is pale",
        )
    )

    listed = taste(server_url)
    assert listed["count"] == 1
    (standing,) = listed["affinities"]
    # Not softened to `stated`, which would be the product claiming the curator
    # said something they never said.
    assert standing["derivation"] == "inferred"
    assert standing["rationale"] == "they asked for stillness, and said the room is pale"
    assert (standing["sentiment"], standing["open_to_more"]) == ("loves", True)
    assert "source_turn_id" not in standing
    assert "conversation_id" not in standing


def test_the_old_conversation_routes_are_gone(server_url):
    """Nothing serves the retired conversations: Ask's threads are under `/api/ask`."""
    assert httpx.get(f"{server_url}/api/conversations", timeout=20).status_code == 404
    assert httpx.post(f"{server_url}/api/conversations", timeout=20).status_code in (404, 405)
