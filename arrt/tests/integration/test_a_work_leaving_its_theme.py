"""A wall's history says a work left its theme, whichever way it left.

Only *Not this one again*, answered *from this theme*, could once write
`work.left_theme`, and only for the wall it was asked on. The MCP break removed
that answer's `scope`, so an agent takes a work out of a theme
with the theme's Remove, and were that to write nothing a wall's history would say a work
was hung and never that it left. Every way of taking a work out of a theme now
writes one line per work for every wall the theme hangs on, from one place
(`Themes._record_left`). Activity words each as "Took <work> out of <theme> on
<wall>" (`static/screens/activity.js`).

Through the browser's routes, with the server booted, and through the service.
"""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.library.facade import EventKind


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def two_walls_one_theme(services, ready_work, wall_id):
    """One theme of three works hung on the hall and the study, and a third wall hanging another theme."""
    display = services.display
    works = [ready_work(title) for title in ("Automat", "Chop Suey", "Nighthawks")]
    theme = display.add_theme(name="Late night")
    for work in works:
        display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    study = display.add_wall(name="Study").id
    attic = display.add_wall(name="Attic").id
    other = display.add_theme(name="Elsewhere")
    display.add_to_theme(theme_id=other.id, artwork_id=works[0].id)
    for wall in (wall_id, study):
        display.activate_theme(theme.id, wall_id=wall)
    display.activate_theme(other.id, wall_id=attic)
    return theme, works, (wall_id, study), attic


def _left(http, **params) -> list[tuple[str, str, str]]:
    events = http.get("/api/history", params={"kind": "work.left_theme", **params}).json()["events"]
    return sorted((event["artwork_id"], event["wall_id"], event["detail"]["theme_name"]) for event in events)


def _kept_off(http, **params) -> list[tuple[str, str]]:
    events = http.get("/api/history", params={"kind": "work.excluded", **params}).json()["events"]
    return [(event["artwork_id"], event["wall_id"]) for event in events]


def test_a_theme_s_remove_writes_the_line_on_every_wall_the_theme_hangs_on(http, two_walls_one_theme):
    theme, works, walls, attic = two_walls_one_theme
    gone = works[0]

    response = http.delete(f"/api/themes/{theme.id}/works/{gone.id}")

    assert response.status_code == 200, response.text
    assert _left(http) == sorted((gone.id, wall, "Late night") for wall in walls)
    # The attic's theme still holds the work: nothing left there.
    assert _left(http, wall_id=attic) == []


def test_a_selection_removed_from_a_theme_writes_one_line_a_work_a_wall(http, two_walls_one_theme):
    theme, works, walls, _ = two_walls_one_theme
    chosen = [works[0].id, works[1].id]

    response = http.post(f"/api/themes/{theme.id}/works/remove", json={"artwork_ids": chosen})

    assert response.status_code == 200, response.text
    assert sorted(response.json()["removed"]) == sorted(chosen)
    assert _left(http) == sorted((work_id, wall, "Late night") for work_id in chosen for wall in walls)


def test_not_this_one_again_from_the_theme_writes_the_line_on_every_wall_the_theme_hangs_on(http, two_walls_one_theme):
    """Asked on the hall, the work leaves the theme, so it leaves the study too, and the study's history says so."""
    _, works, (hall, study), _ = two_walls_one_theme
    gone = works[1]

    response = http.post(f"/api/walls/{hall}/not-again", json={"artwork_id": gone.id, "scope": "theme"})

    assert response.status_code == 200, response.text
    assert _left(http, wall_id=study) == [(gone.id, study, "Late night")]
    assert _left(http, wall_id=hall) == [(gone.id, hall, "Late night")]


def test_a_theme_hanging_nowhere_writes_no_line(http, services, ready_work):
    work = ready_work("Automat")
    theme = services.display.add_theme(name="On the shelf")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)

    assert http.delete(f"/api/themes/{theme.id}/works/{work.id}").status_code == 200
    assert _left(http) == []


def test_a_removal_refused_writes_no_line(http, two_walls_one_theme, ready_work):
    theme, _, _, _ = two_walls_one_theme
    stranger = ready_work("Gas")

    assert http.delete(f"/api/themes/{theme.id}/works/{stranger.id}").status_code == 400
    assert _left(http) == []


async def _over_mcp(server_url: str, tool: str, **arguments) -> dict:
    """Call `tool` over the MCP surface, as an agent does, and return its payload; a refusal fails the test."""
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    payload = json.loads(result.content[0].text)
    assert result.isError is False, payload
    return payload


async def test_art_theme_remove_over_mcp_writes_the_line_on_every_wall_the_theme_hangs_on(server_url, two_walls_one_theme):
    """An agent takes a work out of a theme with `art_theme(action='remove')`, and each wall's history says so."""
    theme, works, walls, attic = two_walls_one_theme
    gone = works[2]

    await _over_mcp(server_url, "art_theme", action="remove", theme_id=theme.id, artwork_id=gone.id)

    with httpx.Client(base_url=server_url, timeout=30.0) as http:
        assert _left(http) == sorted((gone.id, wall, "Late night") for wall in walls)
        assert _left(http, wall_id=attic) == []


async def test_not_again_over_mcp_keeps_the_work_off_every_wall_and_writes_that_not_that_it_left_its_theme(
    server_url, services, two_walls_one_theme
):
    """`art_display(action='not_again')` keeps the work off every wall and leaves it in its theme (the MCP break).

    So the wall it was asked on says it was kept off (`work.excluded`), and no
    wall says it left its theme: that line is `art_theme(action='remove')`'s.
    """
    theme, works, (hall, _study), _ = two_walls_one_theme
    gone = works[1]

    answer = await _over_mcp(server_url, "art_display", action="not_again", wall_id=hall, artwork_id=gone.id)

    assert (answer["scope"], answer["left_theme"]) == ("every_wall", None)
    with httpx.Client(base_url=server_url, timeout=30.0) as http:
        assert _kept_off(http, wall_id=hall) == [(gone.id, hall)]
        assert _left(http) == []
    assert gone.id in services.display.theme_work_ids(theme.id)


def test_the_service_s_remove_writes_each_wall_s_line_with_the_wall_s_name(services, two_walls_one_theme):
    """Through the service, as an MCP caller's `art_theme(action='remove')` reaches it; the name is kept, as a hang's is."""
    theme, works, walls, _ = two_walls_one_theme

    services.display.remove_from_theme(theme_id=theme.id, artwork_id=works[2].id)

    for wall in walls:
        [event] = [event for event in services.catalogue.list_events(wall_id=wall).events if event.kind is EventKind.LEFT_THEME]
        assert (event.work_id, event.theme_id) == (works[2].id, theme.id)
        assert event.detail == {
            "theme_name": "Late night",
            "selection": False,
            "wall_name": services.display.get_wall(wall).name,
        }
