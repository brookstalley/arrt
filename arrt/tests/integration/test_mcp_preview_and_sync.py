"""A look at what would reach a wall is not a write, and `sync` cannot hang another theme.

`art_theme(action='get')` used to tell an agent to run `art_display(action='sync')`
to see which works would reach the wall. `sync` published whatever theme it was
handed, without recording a hang, so the check changed the wall and left every
other surface saying something else was hanging there
(`audit-5-ia.md` F1). The browser's `GET /api/manifest` was the read-only twin;
`art_display(action='preview')` is its twin on this surface.

Entered through a real MCP client over real HTTP, for the reason the neighbouring
file gives: a binding deleted or miswired leaves every service test green.
The evidence of "nothing was written" is the feed file's bytes, the wall's
`hanging` and the history, read back through the surface a curator reads them by.
"""

import json
from collections.abc import Iterator

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.mcp.tools import ART_DISPLAY, ART_THEME, TOOLS


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """Call a tool over real HTTP; return its payload and the protocol's error flag."""
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


@pytest.fixture
async def wall(server_url):
    payload, _ = await call(server_url, "art_display", action="walls")
    return payload["walls"][0]["wall_id"]


async def _theme_holding(server_url, name, *works) -> str:
    created, _ = await call(server_url, "art_theme", action="create", name=name)
    theme_id = created["theme"]["theme_id"]
    for work in works:
        await call(server_url, "art_theme", action="add", theme_id=theme_id, artwork_id=work.id)
    return theme_id


@pytest.fixture
async def two_themes(server_url, ready_work, wall):
    """One theme hanging on the wall, and a second that is not hanging anywhere.

    The second holds a work that can be shown and a seeded one that cannot, so a
    report of what it would put on the wall has both halves to get right.
    """
    seeded, _ = await call(server_url, "art_catalogue", action="list")
    unshowable = next(work for work in seeded["artworks"] if work["title"] == "Nighthawks")
    hanging = await _theme_holding(server_url, "Hanging", ready_work("Automat"), ready_work("Chop Suey"))
    foreign = await _theme_holding(server_url, "Foreign", ready_work("Hopper study"))
    await call(server_url, "art_theme", action="add", theme_id=foreign, artwork_id=unshowable["artwork_id"])
    await call(server_url, "art_display", action="activate", theme_id=hanging, wall_id=wall)
    return {"hanging": hanging, "foreign": foreign}


async def _what_a_curator_can_read(server_url, wall_settings, wall) -> dict:
    """The feed's bytes, which theme each wall reports hanging, and the history."""
    walls, _ = await call(server_url, "art_display", action="walls")
    history, _ = await call(server_url, "art_catalogue", action="history")
    return {
        "feed": wall_settings.manifest_v2_path(wall).read_bytes(),
        "hanging": {
            entry["wall_id"]: None if entry["hanging"] is None else entry["hanging"]["theme_id"] for entry in walls["walls"]
        },
        "history": history["events"],
    }


# -- preview --------------------------------------------------------------------


async def test_a_preview_of_a_theme_not_hanging_reports_what_it_would_put_on_the_wall_and_writes_nothing(
    server_url, wall_settings, two_themes, wall
):
    before = await _what_a_curator_can_read(server_url, wall_settings, wall)
    assert before["hanging"][wall] == two_themes["hanging"]

    payload, errored = await call(server_url, "art_display", action="preview", wall_id=wall, theme_id=two_themes["foreign"])

    assert errored is False, payload
    assert payload["wall"]["wall_id"] == wall
    assert payload["theme"]["theme_id"] == two_themes["foreign"]
    assert [entry["title"] for entry in payload["on_the_wall"]] == ["Hopper study"]
    assert [(entry["title"], entry["reason"]) for entry in payload["not_on_the_wall"]] == [("Nighthawks", "no_original")]
    assert payload["considered"] == 2
    # A preview is a conditional, and the sentence says so: "would be", never "is".
    assert "would be on the wall" in payload["notice"]
    assert " is on the wall" not in payload["notice"]
    assert " are on the wall" not in payload["notice"]
    assert "not_on_the_wall" in payload["notice"]

    after = await _what_a_curator_can_read(server_url, wall_settings, wall)
    assert after["feed"] == before["feed"]
    assert after["hanging"] == before["hanging"]
    assert after["history"] == before["history"]
    # The wall still plays the theme that hangs there.
    assert json.loads(after["feed"])["playlist"]["id"] == two_themes["hanging"]


async def test_a_preview_without_a_theme_reports_what_is_hanging_on_the_wall(server_url, wall_settings, two_themes, wall):
    before = await _what_a_curator_can_read(server_url, wall_settings, wall)

    payload, errored = await call(server_url, "art_display", action="preview", wall_id=wall)

    assert errored is False, payload
    assert payload["theme"]["theme_id"] == two_themes["hanging"]
    assert sorted(entry["title"] for entry in payload["on_the_wall"]) == ["Automat", "Chop Suey"]
    assert payload["not_on_the_wall"] == []
    assert "would be on the wall" in payload["notice"]
    assert await _what_a_curator_can_read(server_url, wall_settings, wall) == before


async def test_a_preview_of_a_clean_theme_is_conditional_too(server_url, ready_work, wall):
    """The branch with nothing left out is its own sentence, and it must not say "are"."""
    theme_id = await _theme_holding(server_url, "Clean", ready_work("Automat"), ready_work("Chop Suey"))

    payload, errored = await call(server_url, "art_display", action="preview", wall_id=wall, theme_id=theme_id)

    assert errored is False, payload
    assert payload["not_on_the_wall"] == []
    assert "would be on the wall" in payload["notice"]
    assert " are on the wall" not in payload["notice"]
    assert "not_on_the_wall" not in payload["notice"]


async def test_a_preview_of_an_empty_theme_says_so_rather_than_failing(server_url, wall):
    theme_id = await _theme_holding(server_url, "Empty")

    payload, errored = await call(server_url, "art_display", action="preview", wall_id=wall, theme_id=theme_id)

    assert errored is False, payload
    assert payload["considered"] == 0
    assert "holds no works yet" in payload["notice"]
    assert " is on the wall" not in payload["notice"]


async def test_a_preview_names_the_wall_it_needs_and_a_theme_that_is_not_there(server_url, two_themes, wall):
    no_wall, errored = await call(server_url, "art_display", action="preview", theme_id=two_themes["foreign"])
    assert errored is True
    assert "wall_id" in no_wall["error"]

    unknown, errored = await call(server_url, "art_display", action="preview", wall_id=wall, theme_id="not-a-theme")
    assert errored is True
    assert "not-a-theme" in unknown["error"]


async def test_a_preview_on_a_wall_with_nothing_hung_and_no_theme_is_refused_by_name(server_url, wall):
    payload, errored = await call(server_url, "art_display", action="preview", wall_id=wall)

    assert errored is True
    assert "Nothing is hanging" in payload["error"]


# -- sync -----------------------------------------------------------------------


async def test_sync_refuses_a_theme_id_by_name_and_writes_nothing(server_url, wall_settings, two_themes, wall):
    before = await _what_a_curator_can_read(server_url, wall_settings, wall)

    payload, errored = await call(server_url, "art_display", action="sync", wall_id=wall, theme_id=two_themes["foreign"])

    assert errored is True
    assert "does not take" in payload["error"]
    assert "theme_id" in payload["error"]
    after = await _what_a_curator_can_read(server_url, wall_settings, wall)
    assert after["feed"] == before["feed"]
    assert json.loads(after["feed"])["playlist"]["id"] == two_themes["hanging"]
    assert after["hanging"] == before["hanging"]
    assert after["history"] == before["history"]


async def test_sync_republishes_what_is_hanging_and_reports_it(server_url, wall_settings, two_themes, wall):
    payload, errored = await call(server_url, "art_display", action="sync", wall_id=wall)

    assert errored is False, payload
    assert payload["theme"]["theme_id"] == two_themes["hanging"]
    assert sorted(entry["title"] for entry in payload["on_the_wall"]) == ["Automat", "Chop Suey"]
    assert payload["notice"] == "All 2 works in this theme are on the wall."
    assert json.loads(wall_settings.manifest_v2_path(wall).read_text())["playlist"]["id"] == two_themes["hanging"]


async def test_sync_on_a_wall_with_nothing_hung_is_refused(server_url, wall):
    payload, errored = await call(server_url, "art_display", action="sync", wall_id=wall)

    assert errored is True
    assert "Nothing is hanging" in payload["error"]


# -- the descriptions an agent reads ---------------------------------------------


def _action(record, name):
    return next(action for action in record.actions if action.name == name)


def _every_sentence(record) -> Iterator[tuple[str, str]]:
    """(where, text) for each sentence a client can read off one tool record, from the record itself."""
    yield f"{record.name}.summary", record.summary
    for action in record.actions:
        yield f"{record.name}.{action.name}.description", action.description
        for position, tip in enumerate(action.tips):
            yield f"{record.name}.{action.name}.tips[{position}]", tip
        for param in action.params:
            yield f"{record.name}.{action.name}.{param.name}", param.description


#: What `audit-5-ia.md` F10 found stale, as the words that said it. Each was true
#: of an earlier plane or an earlier name and false of the bindings now: a Frame
#: Player uploads what it has not got, a wall's television is recorded, the Player
#: (not "a display") writes the heartbeat, and the Walls card calls it Remove.
RETIRED_PHRASES = (
    "no television writes",
    "stays on the tv",
    "nothing about a television is recorded",
    "writes its own heartbeat",
    "if no display has ever run",
    "this one again",
)


@pytest.mark.parametrize("record", TOOLS, ids=lambda record: record.name)
def test_no_tool_description_teaches_a_retired_phrase(record):
    stale = [(where, phrase) for where, text in _every_sentence(record) for phrase in RETIRED_PHRASES if phrase in text.lower()]

    assert not stale, f"{record.name} still says what is no longer true: {stale}"


def test_the_theme_get_tip_points_at_preview_and_at_no_write():
    tips = " ".join(_action(ART_THEME, "get").tips)

    assert "art_display(action='preview')" in tips
    assert "sync" not in tips


def test_preview_is_a_wall_and_an_optional_theme_and_sync_is_a_wall_alone():
    preview = _action(ART_DISPLAY, "preview")
    sync = _action(ART_DISPLAY, "sync")

    assert [(param.name, param.required) for param in preview.params] == [("wall_id", True), ("theme_id", False)]
    assert [param.name for param in sync.params] == ["wall_id"]
    assert "theme_id" not in sync.example
    assert "wall_id=" in preview.example


def test_sync_says_it_republishes_what_is_hanging_and_preview_says_it_writes_nothing():
    sync_prose = " ".join([_action(ART_DISPLAY, "sync").description, *_action(ART_DISPLAY, "sync").tips]).lower()
    preview_prose = " ".join([_action(ART_DISPLAY, "preview").description, *_action(ART_DISPLAY, "preview").tips]).lower()

    assert "republish" in sync_prose
    assert "preview" in sync_prose
    assert "writes nothing" in preview_prose or "changes nothing" in preview_prose


def test_hang_selection_is_on_the_wall_tool_the_theme_tool_points_there_and_show_now_says_it_lasts_one_slot():
    """Every act on a wall is `art_display`'s, `hang_selection` among them, and the theme tool's summary points there."""
    assert "hang_selection" in ART_DISPLAY.action_names
    assert "hang_selection" not in ART_THEME.action_names
    assert "art_display" in ART_THEME.summary
    tips = " ".join(_action(ART_DISPLAY, "show_now").tips)
    assert "one slot" in tips
    assert "hang_selection" in tips
