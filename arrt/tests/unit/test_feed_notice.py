"""Whether a wall's Player can read this server's feed, read from its heartbeat.

The server publishes manifest major 2 alone, so a Player that reads only major 1
asks for a feed that answers 404 and shows nothing new. `player-contract.md`
§ The cutover promises that such a Player is visible because its heartbeat lacks
2, and counts a heartbeat with no `capabilities` as `[1]`. These tests hold that
reading, and the one sentence both surfaces show for it, in every case it can
take: absent where it must not appear as well as present where it must.
"""

import json

import httpx
import pytest

from arrt.programming.display import feed_notice

_REPORTED = "2026-10-10T12:00:00+00:00"


def _beat(wall_settings, wall_id, **document) -> None:
    wall_settings.heartbeat_path(wall_id).write_text(json.dumps({"reported_at": _REPORTED, **document}), encoding="utf-8")


def _capabilities(majors, *, screen=True) -> dict:
    return {
        **({"screen": {"width_px": 3840, "height_px": 2160}} if screen else {}),
        "backend": "frame",
        "label_modes": ["none"],
        "manifest_majors": majors,
    }


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"capabilities": _capabilities([2, 1])}, True),
        ({"capabilities": _capabilities([2])}, True),
        ({"capabilities": _capabilities([1])}, False),
        # Minor 4: a Player whose screen is unplugged still says what it reads.
        ({"capabilities": _capabilities([2], screen=False)}, True),
        ({"capabilities": _capabilities([1], screen=False)}, False),
        # Silence about majors is a Player from before minor 2, which reads major 1 alone.
        ({}, False),
    ],
    ids=["reads-2-and-1", "reads-2", "reads-1", "reads-2-no-screen", "reads-1-no-screen", "no-capabilities"],
)
def test_a_heartbeat_says_whether_its_player_reads_the_feed(display, wall_settings, wall_id, document, expected):
    _beat(wall_settings, wall_id, **document)

    view = display.get_wall_view(wall_id)

    assert view.reads_feed is expected
    assert [wall.reads_feed for wall in display.survey_walls()] == [expected]


def test_a_wall_with_no_heartbeat_says_nothing_about_its_player(display, wall_id):
    """Walls already says the wall is silent; a notice about majors would be a guess."""
    assert display.get_wall_view(wall_id).reads_feed is None
    assert feed_notice(reads_feed=None) is None


def test_the_notice_is_said_only_for_a_player_that_cannot_read_the_feed():
    assert feed_notice(reads_feed=True) is None
    notice = feed_notice(reads_feed=False)
    assert notice is not None
    assert "can't read this server's feed" in notice
    assert "Update Arrt Player" in notice


def test_walls_over_http_carries_the_reading_and_the_notice(server_url, wall_settings, wall_id):
    _beat(wall_settings, wall_id, capabilities=_capabilities([1]))

    wall = httpx.get(server_url + "/api/walls").json()["walls"][0]

    assert wall["reads_feed"] is False
    assert wall["feed_notice"] == feed_notice(reads_feed=False)


def test_walls_over_http_carries_no_notice_for_a_player_that_reads_the_feed(server_url, wall_settings, wall_id):
    _beat(wall_settings, wall_id, capabilities=_capabilities([2, 1]))

    wall = httpx.get(server_url + "/api/walls").json()["walls"][0]

    assert (wall["reads_feed"], wall["feed_notice"]) == (True, None)
