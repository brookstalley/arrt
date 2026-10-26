"""Scenes over HTTP, against a real server: each route is one `DisplayService` act.

What the scene does to each wall's feed is `tests/unit/test_scenes.py`'s. Here
the question is the surface: that each route reaches its act with what the
request carried, answers with the scene read back, and refuses in the service's
own words.
"""

import json
from datetime import UTC, datetime

import httpx
import pytest


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def _hang(http, wall, *works, name):
    theme = http.post("/api/themes", json={"name": name}).json()
    for work in works:
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
    http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})


@pytest.fixture
def walls(http, ready_work):
    """The hall and the study, each hanging a theme of its own."""
    hall = http.get("/api/walls").json()["walls"][0]
    study = http.post("/api/walls", json={"name": "The study"}).json()
    _hang(http, hall, ready_work("Automat"), name="Hall's")
    _hang(http, study, ready_work("Chop Suey"), name="Study's")
    return hall, study


def _feed(settings, wall):
    return json.loads(settings.manifest_v2_path(wall["wall_id"]).read_text(encoding="utf-8"))


def test_a_scene_is_assembled_applied_and_released_over_http(http, settings, ready_work, walls):
    hall, study = walls
    dali, magritte = ready_work("Dalí"), ready_work("Magritte")

    draft = http.post("/api/scenes").json()
    assert (draft["status"], draft["walls"]) == ("draft", [])
    http.put(f"/api/scenes/{draft['scene_id']}/pins/{hall['wall_id']}", json={"work_id": dali.id})
    pinned = http.put(f"/api/scenes/{draft['scene_id']}/pins/{study['wall_id']}", json={"work_id": magritte.id}).json()
    assert {(wall["wall_name"], wall["title"], wall["reached"]) for wall in pinned["walls"]} == {
        (hall["name"], "Dalí", False),
        ("The study", "Magritte", False),
    }
    assert _feed(settings, hall)["staging"] == [dali.id]
    assert http.get("/api/scenes/live").json() == {"live": None, "draft": pinned}

    applied = http.post(f"/api/scenes/{draft['scene_id']}/apply", json={"lifetime": "preview", "minutes": 5}).json()
    assert applied["status"] == "live"
    assert applied["lifetime"] == "preview"
    span = datetime.fromisoformat(applied["until"]) - datetime.fromisoformat(applied["starts_at"])
    assert span.total_seconds() == 300
    assert _feed(settings, study)["scene"]["work_id"] == magritte.id
    assert http.get("/api/scenes/live").json()["live"]["scene_id"] == draft["scene_id"]

    released = http.post(f"/api/scenes/{draft['scene_id']}/release").json()
    assert released["status"] == "ended"
    assert "scene" not in _feed(settings, hall)
    assert http.get("/api/scenes/live").json() == {"live": None, "draft": None}


def test_unpinning_and_discarding_over_http(http, settings, ready_work, walls):
    hall, study = walls
    draft = http.post("/api/scenes").json()
    http.put(f"/api/scenes/{draft['scene_id']}/pins/{hall['wall_id']}", json={"work_id": ready_work("Dalí").id})
    http.put(f"/api/scenes/{draft['scene_id']}/pins/{study['wall_id']}", json={"work_id": ready_work("Magritte").id})

    left = http.delete(f"/api/scenes/{draft['scene_id']}/pins/{hall['wall_id']}").json()
    assert [wall["wall_id"] for wall in left["walls"]] == [study["wall_id"]]
    assert "staging" not in _feed(settings, hall)

    assert http.delete(f"/api/scenes/{draft['scene_id']}").json() == {"live": None, "draft": None}
    assert "staging" not in _feed(settings, study)


def test_a_hold_is_applied_with_no_length(http, ready_work, walls):
    hall, _ = walls
    draft = http.post("/api/scenes").json()
    http.put(f"/api/scenes/{draft['scene_id']}/pins/{hall['wall_id']}", json={"work_id": ready_work("Dalí").id})

    applied = http.post(f"/api/scenes/{draft['scene_id']}/apply", json={"lifetime": "hold"}).json()

    assert (applied["lifetime"], applied["until"]) == ("hold", None)


def test_a_refused_pin_answers_in_the_services_words_and_keeps_the_other(http, ready_work, walls):
    hall, study = walls
    draft = http.post("/api/scenes").json()
    http.put(f"/api/scenes/{draft['scene_id']}/pins/{study['wall_id']}", json={"work_id": ready_work("Magritte").id})
    plain = ready_work("Plain", master=False)

    response = http.put(f"/api/scenes/{draft['scene_id']}/pins/{hall['wall_id']}", json={"work_id": plain.id})

    assert response.status_code == 400
    assert "cannot be shown on the wall" in response.json()["error"]
    assert [wall["wall_id"] for wall in http.get("/api/scenes/live").json()["draft"]["walls"]] == [study["wall_id"]]


def test_releasing_a_scene_that_is_not_live_is_refused_in_words(http):
    draft = http.post("/api/scenes").json()

    response = http.post(f"/api/scenes/{draft['scene_id']}/release")

    assert response.status_code == 400
    assert "nothing to release" in response.json()["error"]


def test_a_lifetime_that_is_not_one_is_refused_in_words(http, ready_work, walls):
    hall, _ = walls
    draft = http.post("/api/scenes").json()
    http.put(f"/api/scenes/{draft['scene_id']}/pins/{hall['wall_id']}", json={"work_id": ready_work("Dalí").id})

    response = http.post(f"/api/scenes/{draft['scene_id']}/apply", json={"lifetime": "keep"})

    assert response.status_code == 400
    assert "lifetime" in response.json()["error"]
    assert http.get("/api/scenes/live").json()["live"] is None


def test_a_wall_reports_reaching_the_scene_through_its_heartbeat(http, services, ready_work, walls):
    hall, _ = walls
    dali = ready_work("Dalí")
    draft = http.post("/api/scenes").json()
    http.put(f"/api/scenes/{draft['scene_id']}/pins/{hall['wall_id']}", json={"work_id": dali.id})
    http.post(f"/api/scenes/{draft['scene_id']}/apply", json={"lifetime": "hold"})
    now = datetime.now(UTC).isoformat()

    beat = {
        "schema": {"major": 1, "minor": 3},
        "reported_at": now,
        "current_work_id": dali.id,
        "scene_id": draft["scene_id"],
        "display_state": {"state": "showing_art", "work_id": dali.id, "since": now},
    }
    services.display.record_heartbeat(hall["wall_id"], beat)

    (wall,) = http.get("/api/scenes/live").json()["live"]["walls"]
    assert wall["reached"] is True
