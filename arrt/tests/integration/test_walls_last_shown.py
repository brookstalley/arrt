"""Walls' read of what a wall showed last and what comes next, over both surfaces.

`GET /api/walls` and `art_display(action='walls')` describe the same wall, so each
case reads both through a booted server and asks that they agree, value for
value, as well as that the value is right. The showings are kept the way a
Player's heartbeat keeps them (`DisplayService.record_heartbeat`), and the
schedule is the one hanging a theme publishes.
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.programming.manifest.v2 import read_published

#: Not a multiple of the schedule's slot, so no step lands on a boundary.
MINUTE = timedelta(seconds=61)
#: Each work's slot on the wall, long enough that no test crosses one while it runs.
SLOT = 600


async def _mcp_walls(server_url):
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_display", {"action": "walls"})
    assert not result.isError
    return {wall["wall_id"]: wall for wall in json.loads(result.content[0].text)["walls"]}


def _http_walls(server_url):
    walls = httpx.get(server_url + "/api/walls", timeout=30.0).json()["walls"]
    return {wall["wall_id"]: wall for wall in walls}


async def _both(server_url, wall_id, field):
    """The field as each surface states it, after asking that they state it alike."""
    over_http = _http_walls(server_url)[wall_id][field]
    over_mcp = (await _mcp_walls(server_url))[wall_id][field]
    assert over_http == over_mcp, f"{field}: GET /api/walls says {over_http!r}, art_display says {over_mcp!r}"
    return over_http


@pytest.fixture
def hung(services, ready_work, wall_id):
    """Three works hung on the wall in order, `SLOT` seconds each."""
    works = [ready_work(title) for title in ("Dalí", "Magritte", "Ernst")]
    theme = services.display.add_theme(name="Surrealism")
    for position, work in enumerate(works):
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
    services.display.set_playback(wall_id, rotation_interval_seconds=SLOT, shuffle=False)
    services.display.activate_theme(theme.id, wall_id=wall_id)
    return works


def _report(at, state, work_id=None, since=None):
    return {
        "schema": {"major": 1, "minor": 3},
        "reported_at": at.isoformat(),
        "display_state": {"state": state, "work_id": work_id, "since": (since or at).isoformat()},
    }


async def test_a_dark_wall_says_what_it_showed_last_and_until_when(server_url, services, hung, wall_id):
    first, second, _ = hung
    now = datetime.now(UTC)
    services.display.record_heartbeat(wall_id, _report(now - 3 * MINUTE, "showing_art", first.id))
    services.display.record_heartbeat(wall_id, _report(now - 2 * MINUTE, "showing_art", second.id))
    services.display.record_heartbeat(wall_id, _report(now - MINUTE, "showing_art", second.id, since=now - 2 * MINUTE))
    services.display.record_heartbeat(wall_id, _report(now, "dark"))

    assert await _both(server_url, wall_id, "last_shown") == {
        "work_id": second.id,
        "started_at": (now - 2 * MINUTE).isoformat(),
        "until": now.isoformat(),
        "ended": True,
    }


async def test_a_wall_showing_a_work_now_says_it_until_its_last_report(server_url, services, hung, wall_id):
    first, _, _ = hung
    now = datetime.now(UTC)
    services.display.record_heartbeat(wall_id, _report(now - MINUTE, "showing_art", first.id))
    services.display.record_heartbeat(wall_id, _report(now, "showing_art", first.id, since=now - MINUTE))

    shown = await _both(server_url, wall_id, "last_shown")

    assert (shown["work_id"], shown["until"], shown["ended"]) == (first.id, now.isoformat(), False)


async def test_a_wall_that_has_shown_nothing_says_so(server_url, hung, wall_id):
    assert await _both(server_url, wall_id, "last_shown") is None


async def test_the_next_three_are_the_schedules_slots_after_the_one_on_the_wall(server_url, hung, wall_settings, wall_id):
    published = read_published(wall_settings.manifest_v2_path(wall_id))
    now = datetime.now(UTC)
    after = [slot for slot in published.slots if slot.start > now][:3]

    upcoming = await _both(server_url, wall_id, "upcoming")

    assert [entry["work_id"] for entry in upcoming] == [slot.work_id for slot in after]
    assert [datetime.fromisoformat(entry["starts_at"]) for entry in upcoming] == [slot.start for slot in after]
    assert len(upcoming) == 3
    # The one on the wall now is not "next".
    assert all(datetime.fromisoformat(entry["starts_at"]) > now for entry in upcoming)


async def test_a_schedule_with_fewer_than_three_slots_left_says_only_those(server_url, services, hung, wall_settings, wall_id):
    path = wall_settings.manifest_v2_path(wall_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(UTC)
    kept = [
        slot for slot in document["schedule"]["slots"] if datetime.fromisoformat(slot["from"]) <= now + timedelta(seconds=SLOT)
    ]
    document["schedule"]["slots"] = kept
    path.write_text(json.dumps(document), encoding="utf-8")

    upcoming = await _both(server_url, wall_id, "upcoming")

    assert len(upcoming) == len([slot for slot in kept if datetime.fromisoformat(slot["from"]) > now]) == 1


async def test_a_wall_with_no_feed_published_has_nothing_coming(server_url, wall_id):
    assert await _both(server_url, wall_id, "upcoming") == []


def test_a_change_to_the_wall_reads_back_the_same_last_shown_and_next_three(server_url, services, hung, wall_id):
    """A write answers with the wall read alone (`get_wall_view`), which the listing does not go through."""
    first, _, _ = hung
    now = datetime.now(UTC)
    services.display.record_heartbeat(wall_id, _report(now, "showing_art", first.id))

    answered = httpx.put(f"{server_url}/api/walls/{wall_id}/playback", json={"shuffle": False}, timeout=30.0).json()
    listed = _http_walls(server_url)[wall_id]

    assert answered["last_shown"]["work_id"] == first.id
    assert answered["last_shown"] == listed["last_shown"]
    assert len(answered["upcoming"]) == 3
    assert answered["upcoming"] == listed["upcoming"]
