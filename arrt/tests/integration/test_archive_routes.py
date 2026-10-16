"""Archive and restore over real HTTP, and what archiving does to a standing pin.

The service layer's own tests already hold the rules — a work archives once, a
restore refuses a work that is not archived, and archiving the pinned work
withdraws the pin without advancing the sequence. What none of them touches is
the pair of routes the browser client actually calls, and a binding that called
the wrong service method, swallowed the refusal, or answered with a shape the
screen cannot repaint from would pass every one of them.

Against a real uvicorn server rather than an in-process transport, per the
suite's standing rule: Starlette does not run a mounted sub-app's lifespan, and
an in-process test would pass against an application that fails every MCP
request in production.
"""

import json

import httpx
import pytest


@pytest.fixture
def http(server_url):
    """A client pointed at the booted server, with the timeout a Pi deserves."""
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def wall(http):
    """The wall this deployment has, read off the surface rather than the store."""
    walls = http.get("/api/walls").json()["walls"]
    assert len(walls) == 1, f"a fresh deployment should serve exactly one wall, got {walls}"
    return walls[0]


def test_archiving_answers_with_the_whole_dossier_the_screen_repaints_from(http, service):
    """Read-back-after-mutate, and the read-back is `GET /api/works/{id}`'s own shape.

    The screen that archives is the screen that shows the work, so a slimmer body
    would send it straight back for the rest — and a second request is a second
    chance for the page to disagree with the catalogue it just changed.
    """
    work = service.add_artwork(title="Chop Suey")

    answer = http.post(f"/api/works/{work.id}/archive")

    assert answer.status_code == 200
    body = answer.json()
    assert body["work"]["status"] == "archived"
    assert set(body) == set(http.get(f"/api/works/{work.id}").json())


def test_restoring_puts_the_work_back_in_circulation(http, service):
    """The undo, and the reason the control may say Archive rather than Remove."""
    work = service.add_artwork(title="Chop Suey")
    http.post(f"/api/works/{work.id}/archive")

    answer = http.post(f"/api/works/{work.id}/restore")

    assert answer.status_code == 200
    assert answer.json()["work"]["status"] == "accepted"
    assert service.get_artwork(work.id).artwork.status == "accepted"


def test_the_work_is_still_listed_while_it_is_archived(http, service):
    """Archived is out of circulation, not out of the catalogue.

    "Everything we hold" means everything, and a work that vanished from the
    listing the moment it was archived would be a delete wearing another word —
    with no route back to it to press Restore on.
    """
    work = service.add_artwork(title="Chop Suey")
    http.post(f"/api/works/{work.id}/archive")

    listed = http.get("/api/works").json()["works"]

    assert work.id in {entry["artwork_id"] for entry in listed}


@pytest.mark.parametrize(
    ("first", "second", "refusal"),
    [("archive", "archive", "already archived"), ("restore", "restore", "not archived")],
)
def test_a_second_call_is_refused_in_words_a_curator_can_act_on(http, service, first, second, refusal):
    """One shape for every refusal, and the message is the service's own sentence."""
    work = service.add_artwork(title="Chop Suey")
    if first == "restore":
        http.post(f"/api/works/{work.id}/archive")
    http.post(f"/api/works/{work.id}/{first}")

    answer = http.post(f"/api/works/{work.id}/{second}")

    assert answer.status_code == 400
    assert refusal in answer.json()["error"]


@pytest.mark.parametrize("act", ["archive", "restore"])
def test_an_unknown_work_is_refused_rather_than_silently_accepted(http, act):
    answer = http.post(f"/api/works/no-such-work/{act}")

    assert answer.status_code == 400
    assert "no-such-work" in answer.json()["error"]


def _hang_with(display, wall_id, *works):
    theme = display.add_theme(name="Late night")
    for work in works:
        display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    display.activate_theme(theme.id, wall_id=wall_id)


def test_archiving_the_work_shown_now_takes_it_off_the_wall(http, wall, display, ready_work, wall_settings):
    """The rule that reaches the room, exercised through the route that triggers it.

    A feed naming an archived work would put it back on the screen, so archiving
    takes it off the feed, and a wall showing it starts fresh without it.
    """
    kept = ready_work(title="Automat")
    _hang_with(display, wall["wall_id"], kept)
    work = ready_work()
    display.show_work_now(wall["wall_id"], work.id)

    http.post(f"/api/works/{work.id}/archive")

    feed = json.loads(wall_settings.manifest_v2_path(wall["wall_id"]).read_text())
    assert work.id not in feed["works"]
    assert feed["schedule"]["slots"][0]["work_id"] == kept.id


def test_archiving_some_other_work_leaves_the_wall_as_it_was(http, wall, service, display, ready_work, wall_settings):
    """The withdrawal is about the work on the wall, not about archiving in general."""
    _hang_with(display, wall["wall_id"], ready_work(title="Automat"))
    display.show_work_now(wall["wall_id"], ready_work().id)
    other = service.add_artwork(title="Chop Suey")
    before = wall_settings.manifest_v2_path(wall["wall_id"]).read_bytes()

    http.post(f"/api/works/{other.id}/archive")

    assert wall_settings.manifest_v2_path(wall["wall_id"]).read_bytes() == before
