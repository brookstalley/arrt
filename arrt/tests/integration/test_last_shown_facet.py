"""Artworks' *Last shown* facet, and the clean-up filters on the tool surface (#316).

`build-plan-shown-record.md` Chunk 03. *Last shown* narrows to the works no wall
has shown, never or not in a period, each period counting the never-shown
works too (the owner, 2026-10-15). Which works were shown, and when, is
Programming's log of showings (`last_shown_by_work`); the Library's narrowings
are its own; `services/works_filter.py` meets them, and both surfaces call it.

So each case asks `GET /api/works` and `art_catalogue(action='list')` the same
question through a booted server, and asks that they answer alike as well as
rightly. The showings are written to the store as a Player's reports would
leave them, at instants either side of each period's edge.
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.persistence.records import Showing

#: Each test work's title, and how long ago a wall last showed it (None: never).
#: A day inside each edge, so neither a slow run nor the clock at the edge moves one.
AGES = {
    "Shown last week": timedelta(days=7),
    "Shown two months ago": timedelta(days=60),
    "Shown in the spring": timedelta(days=200),
    "Shown two years ago": timedelta(days=730),
    "Shown never": None,
}
#: Every test work is titled "Shown …", so `q=Shown` leaves out the seeded works.
OURS = "Shown"


@pytest.fixture
def shown(services, seeded_service, store):
    """The five works, the four that were shown each with one showing on a wall since removed."""
    now = datetime.now(UTC)
    works = {}
    for title, age in AGES.items():
        works[title] = seeded_service.add_artwork(title=title)
        if age is not None:
            seen = now - age
            store.save_showing(
                Showing(
                    wall_id="a-wall-taken-down",
                    work_id=works[title].id,
                    started_at=seen - timedelta(minutes=3),
                    last_seen_at=seen,
                )
            )
    return works


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


async def _tool(server_url, **arguments):
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_catalogue", {"action": "list", **arguments})
    return json.loads(result.content[0].text), bool(result.isError)


def _titles(works):
    return sorted(work["title"] for work in works)


async def _both(http, server_url, **query):
    """The page each surface answers, after asking that they select the same works and count the same options."""
    params = {key: ("true" if value is True else value) for key, value in query.items()}
    page = http.get("/api/works", params=params).json()
    listed, errored = await _tool(server_url, **query)
    assert errored is False, listed
    assert _titles(page["works"]) == _titles(listed["artworks"])
    assert page["total"] == listed["total"]
    for field in ("shown", "fits", "not_on_wall"):
        assert page[field] == listed[field], f"{field}: GET /api/works says {page[field]!r}, art_catalogue says {listed[field]!r}"
    return page


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("never", ["Shown never"]),
        ("month", ["Shown in the spring", "Shown never", "Shown two months ago", "Shown two years ago"]),
        ("quarter", ["Shown in the spring", "Shown never", "Shown two years ago"]),
        ("year", ["Shown never", "Shown two years ago"]),
    ],
)
async def test_each_period_selects_the_works_no_wall_has_shown_in_it(http, server_url, shown, period, expected):
    page = await _both(http, server_url, q=OURS, shown=period)

    assert _titles(page["works"]) == expected
    assert [(option["value"], option["selected"]) for option in page["shown"]] == [
        ("never", period == "never"),
        ("month", period == "month"),
        ("quarter", period == "quarter"),
        ("year", period == "year"),
    ]


async def test_each_option_counts_what_choosing_it_would_select(http, server_url, shown):
    page = await _both(http, server_url, q=OURS)

    assert [(option["value"], option["count"]) for option in page["shown"]] == [
        ("never", 1),
        ("month", 4),
        ("quarter", 3),
        ("year", 2),
    ]
    assert page["total"] == len(AGES)


async def test_the_counts_ignore_their_own_choice_and_move_with_every_other_filter(http, server_url, shown):
    """Counted as a facet is: chosen, its own options still count the whole filter; searched narrower, they shrink."""
    chosen = await _both(http, server_url, q=OURS, shown="never")
    narrower = await _both(http, server_url, q="Shown two")

    assert [option["count"] for option in chosen["shown"]] == [1, 4, 3, 2]
    assert [(option["value"], option["count"]) for option in narrower["shown"]] == [
        ("never", 0),
        ("month", 2),
        ("quarter", 1),
        ("year", 1),
    ]
    assert narrower["shown"][0]["disabled"] is True


async def test_last_shown_composes_with_not_on_any_wall(http, server_url, services, shown, wall_id):
    """Hung now and never shown are different questions, and the two meet as a filter."""
    theme = services.display.add_theme(name="Hung, not yet up")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=shown["Shown never"].id)
    services.display.activate_theme(theme.id, wall_id=wall_id)

    page = await _both(http, server_url, q=OURS, shown="year", not_on_wall=True)

    assert _titles(page["works"]) == ["Shown two years ago"]


async def test_an_unknown_period_is_refused_by_name_on_both_surfaces(http, server_url, shown):
    response = http.get("/api/works", params={"shown": "fortnight"})
    listed, errored = await _tool(server_url, shown="fortnight")

    assert response.status_code == 400
    assert "never" in response.json()["error"]
    assert errored is True or listed.get("success") is False
    assert "never" in json.dumps(listed)


async def test_the_tool_surface_takes_the_size_and_wall_filters_too(http, server_url, shown, services, ready_work, wall_id):
    """`art_catalogue(action='list')` had neither of #288's filters; both now select as the browser's listing does.

    A work with a master, which `unknown` leaves out, and a work hung, which *Not on any wall* leaves out, so
    a surface ignoring either filter answers differently.
    """
    mastered = ready_work("Shown with a master")
    theme = services.display.add_theme(name="Up now")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=shown["Shown last week"].id)
    services.display.activate_theme(theme.id, wall_id=wall_id)

    page = await _both(http, server_url, q=OURS, fit=["unknown"], not_on_wall=True)

    assert mastered.title not in _titles(page["works"])
    assert _titles(page["works"]) == sorted(title for title in AGES if title != "Shown last week")


def test_select_all_by_last_shown_acts_on_exactly_its_works(http, shown):
    """*Select all* sends the filter, not the ids, so the filter body must carry `shown` or the act reaches too many works."""
    response = http.post("/api/works/archive", json={"filter": {"q": OURS, "shown": "never"}})

    assert response.status_code == 200
    assert response.json()["archived"] == [shown["Shown never"].id]
