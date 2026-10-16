"""The two acts the Walls screen performs, over HTTP, against a real server.

`POST /api/walls/{wall_id}/next` is Skip. Everything it asserts is about *which
wall*: a `next` in the living room must not move the study, and a route that
answered correctly for one wall while quietly republishing both would look
identical from a single-wall deployment.

Activation is here for the same reason and not because it is new: the wall it
publishes to is the half no unit test of `activate_theme` can see, because the
evidence is a file on disk named for a wall.
"""

import json
from datetime import datetime, timedelta

import httpx
import pytest


@pytest.fixture
def http(server_url):
    """A client pointed at the booted server, with the timeout a Pi deserves."""
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def the_wall(http):
    """The wall a fresh deployment has, read off the surface rather than the store."""
    walls = http.get("/api/walls").json()["walls"]
    assert len(walls) == 1, f"a fresh deployment should serve exactly one wall, got {walls}"
    return walls[0]


def _wall_named(http, name):
    return next(wall for wall in http.get("/api/walls").json()["walls"] if wall["name"] == name)


def _hang(http, wall, *works, name="Late night"):
    theme = http.post("/api/themes", json={"name": name}).json()
    for work in works:
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
    http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})
    return theme


def _feed(settings, wall):
    return json.loads(settings.manifest_v2_path(wall["wall_id"]).read_text(encoding="utf-8"))


class TestSteppingAWall:
    def test_a_step_republishes_the_named_wall_and_answers_with_the_work_it_starts(self, http, settings, ready_work, the_wall):
        """The answer names the wall and the work its feed now starts with, which is what was published."""
        _hang(http, the_wall, ready_work("Automat"), ready_work("Chop Suey"))

        response = http.post(f"/api/walls/{the_wall['wall_id']}/next")

        assert response.status_code == 200
        assert response.json() == {
            "wall_id": the_wall["wall_id"],
            "work_id": _feed(settings, the_wall)["schedule"]["slots"][0]["work_id"],
        }

    def test_a_step_leaves_every_other_walls_picture_alone(self, http, settings, ready_work, the_wall):
        """On a one-wall deployment the two behaviours are indistinguishable, which is why this is asserted with two.

        The study hangs the same theme, so its slots to come are rebuilt beside
        this wall's (the owner, 2026-10-13); the work on it now, and since when, stay.
        """
        study = http.post("/api/walls", json={"name": "The study"}).json()
        theme = _hang(http, the_wall, ready_work("Automat"), ready_work("Chop Suey"))
        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": study["wall_id"]})
        on_the_study = _slot_now(settings, study["wall_id"])

        http.post(f"/api/walls/{the_wall['wall_id']}/next")

        assert _slot_now(settings, study["wall_id"]) == on_the_study

    def test_a_step_moves_on_from_a_work_shown_now(self, http, services, ready_work, the_wall):
        """A work shown from outside the theme has its one slot, and Skip moves past it."""
        _hang(http, the_wall, ready_work("Automat"), ready_work("Chop Suey"))
        shown = ready_work()
        services.display.show_work_now(the_wall["wall_id"], shown.id)

        assert http.post(f"/api/walls/{the_wall['wall_id']}/next").json()["work_id"] != shown.id

    def test_a_step_at_a_wall_with_nothing_hung_is_refused_in_words(self, http, the_wall):
        response = http.post(f"/api/walls/{the_wall['wall_id']}/next")

        assert response.status_code == 400
        assert "Hang a theme there first" in response.json()["error"]

    def test_a_step_at_a_wall_whose_feed_holds_nothing_is_refused_in_words(self, http, services, settings, ready_work, the_wall):
        """A theme none of whose works can be sent hangs with an empty feed; "skipped" would claim a move that cannot happen."""
        only = ready_work("Automat")
        _hang(http, the_wall, only)
        services.catalogue.archive_artwork(only.id)
        before = settings.manifest_v2_path(the_wall["wall_id"]).read_bytes()
        assert _feed(settings, the_wall)["works"] == {}, "the feed still holds a work, so this checks nothing"

        response = http.post(f"/api/walls/{the_wall['wall_id']}/next")

        assert response.status_code == 400
        assert "nothing to move on to" in response.json()["error"]
        assert settings.manifest_v2_path(the_wall["wall_id"]).read_bytes() == before

    def test_a_step_at_a_wall_that_does_not_exist_is_refused_in_words(self, http):
        """The service's own message reaches whoever asked, as every refusal does."""
        response = http.post("/api/walls/no-such-wall/next")

        assert response.status_code == 400
        assert "no-such-wall" in response.json()["error"]


class TestActivationPublishesToTheNamedWallOnly:
    def test_hanging_writes_the_named_walls_feed_and_no_others(self, http, settings, ready_work, the_wall):
        """One feed per wall, and hanging touches exactly one of them.

        The evidence is on disk rather than in the response, because the file is
        what a Player actually reads: a route that answered with the right wall's
        build while writing another wall's feed would pass every assertion made
        over JSON.
        """
        work = ready_work(title="Automat")
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
        study = http.post("/api/walls", json={"name": "The study"}).json()

        published = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": the_wall["wall_id"]}).json()

        assert published["wall_id"] == the_wall["wall_id"]
        assert settings.manifest_v2_path(the_wall["wall_id"]).is_file()
        assert not settings.manifest_v2_path(study["wall_id"]).exists()
        # And the wall that was not named goes on hanging nothing, which is the
        # half a curator would notice second and an agent first.
        assert _wall_named(http, "The study")["theme"] is None

    def test_a_second_wall_hangs_the_same_theme_without_disturbing_the_first(self, http, settings, ready_work, the_wall):
        """Two walls may hang one theme, and that must not require duplicating it.

        The first wall's picture and works are compared before and after, because
        the failure worth catching is a second activation changing what it shows.
        Its slots to come may be rebuilt beside the second's (the owner, 2026-10-13).
        """
        work = ready_work(title="Automat")
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
        study = http.post("/api/walls", json={"name": "The study"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": the_wall["wall_id"]})
        first = json.loads(settings.manifest_v2_path(the_wall["wall_id"]).read_text(encoding="utf-8"))

        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": study["wall_id"]})

        after = json.loads(settings.manifest_v2_path(the_wall["wall_id"]).read_text(encoding="utf-8"))
        assert after["works"] == first["works"]
        assert after["playlist"] == first["playlist"]
        assert _slot_now(settings, the_wall["wall_id"]) == (
            first["schedule"]["slots"][0]["work_id"],
            first["schedule"]["slots"][0]["from"],
        )
        assert settings.manifest_v2_path(study["wall_id"]).is_file()
        themes = http.get("/api/themes").json()["themes"]
        hanging = next(entry for entry in themes if entry["theme"]["theme_id"] == theme["theme_id"])
        assert sorted(where["name"] for where in hanging["hanging_on"]) == ["The study", the_wall["name"]]


def test_a_walls_mat_is_chosen_and_handed_back_over_http(http, the_wall):
    path = f"/api/walls/{the_wall['wall_id']}/mat"

    chosen = http.put(path, json={"mode": "none"})
    listed = _wall_named(http, the_wall["name"])
    cleared = http.put(path, json={"mode": None})
    refused = http.put(path, json={"mode": "thick"})

    assert chosen.status_code == 200
    assert chosen.json()["mat_mode"] == "none"
    assert listed["mat_mode"] == "none"
    assert cleared.json()["mat_mode"] is None
    assert refused.status_code == 400
    assert "mat mode" in refused.json()["error"]
    assert _wall_named(http, the_wall["name"])["mat_mode"] is None


def test_a_walls_rotation_is_chosen_and_handed_back_over_http(http, settings, ready_work, the_wall):
    """Values no default could produce; the feed is what the wall plays, so it is read too."""
    _hang(http, the_wall, ready_work(title="Automat"), ready_work(title="Nighthawks"))
    path = f"/api/walls/{the_wall['wall_id']}/playback"

    chosen = http.put(path, json={"rotation_interval_seconds": 931, "shuffle": False, "tallest": None, "widest": None})
    listed = _wall_named(http, the_wall["name"])
    manifest = http.get("/api/manifest", params={"wall_id": the_wall["wall_id"]}).json()
    slots = _feed(settings, the_wall)["schedule"]["slots"]

    assert chosen.status_code == 200
    assert (chosen.json()["rotation_interval_seconds"], chosen.json()["shuffle"]) == (931, False)
    assert (listed["rotation_interval_seconds"], listed["shuffle"]) == (931, False)
    assert (manifest["rotation_interval_seconds"], manifest["shuffle"]) == (931, False)
    # The first slot was kept and the last may be cut by the horizon; those between are the new length.
    lengths = {datetime.fromisoformat(slot["until"]) - datetime.fromisoformat(slot["from"]) for slot in slots[1:-1]}
    assert lengths == {timedelta(seconds=931)}


def test_a_walls_rotation_returns_to_the_default_with_null_and_refuses_what_is_not_a_length(http, the_wall):
    path = f"/api/walls/{the_wall['wall_id']}/playback"
    http.put(path, json={"rotation_interval_seconds": 931, "shuffle": True, "tallest": None, "widest": None})

    cleared = http.put(path, json={"rotation_interval_seconds": None, "shuffle": None, "tallest": None, "widest": None})
    refused = http.put(path, json={"rotation_interval_seconds": 0, "shuffle": None, "tallest": None, "widest": None})
    assert (cleared.json()["rotation_interval_seconds"], cleared.json()["shuffle"]) == (None, None)
    assert refused.status_code == 400
    assert "greater than zero" in refused.json()["error"]
    wall = _wall_named(http, the_wall["name"])
    assert (wall["rotation_interval_seconds"], wall["shuffle"]) == (None, None)


def test_a_field_left_out_of_the_playback_body_is_left_as_it_is_never_read_as_the_default(http, the_wall):
    """So a page setting the shapes cannot put back a pace another surface set after that page was drawn."""
    path = f"/api/walls/{the_wall['wall_id']}/playback"
    http.put(path, json={"rotation_interval_seconds": 931, "shuffle": True, "widest": "16:9"})

    shapes_only = http.put(path, json={"tallest": "1:1"})
    pace_only = http.put(path, json={"rotation_interval_seconds": 47})

    assert shapes_only.status_code == 200
    assert (shapes_only.json()["rotation_interval_seconds"], shapes_only.json()["shuffle"]) == (931, True)
    assert (pace_only.json()["tallest"], pace_only.json()["widest"], pace_only.json()["shuffle"]) == ("1:1", "16:9", True)


def test_a_walls_shapes_are_chosen_over_http_and_leave_its_wider_works_off(http, ready_work, the_wall):
    """Every fixture master is 4:3, so a wall showing nothing wider than 1:1 shows none of them."""
    _hang(http, the_wall, ready_work(title="Automat"), ready_work(title="Nighthawks"))
    path = f"/api/walls/{the_wall['wall_id']}/playback"

    chosen = http.put(path, json={"rotation_interval_seconds": None, "shuffle": None, "tallest": "9:16", "widest": "1:1"})
    manifest = http.get("/api/manifest", params={"wall_id": the_wall["wall_id"]}).json()

    assert chosen.status_code == 200
    assert (chosen.json()["tallest"], chosen.json()["widest"]) == ("9:16", "1:1")
    assert chosen.json()["shapes"] == "works from 9:16 to 1:1"
    assert {exclusion["reason"] for exclusion in manifest["exclusions"]} == {"outside_wall_shape"}
    assert manifest["summary"].endswith("2 are outside this wall's shapes, so the wall is dark.")

    reopened = http.put(path, json={"rotation_interval_seconds": None, "shuffle": None, "tallest": None, "widest": "any"})

    assert (reopened.json()["tallest"], reopened.json()["widest"], reopened.json()["shapes"]) == (None, None, None)
    assert http.get("/api/manifest", params={"wall_id": the_wall["wall_id"]}).json()["exclusions"] == []


def test_a_shape_that_is_not_one_or_a_range_that_holds_nothing_is_refused_over_http(http, the_wall):
    path = f"/api/walls/{the_wall['wall_id']}/playback"
    body = {"rotation_interval_seconds": None, "shuffle": None}

    unreadable = http.put(path, json={**body, "tallest": None, "widest": "wide"})
    inverted = http.put(path, json={**body, "tallest": "16:9", "widest": "1:1"})

    assert unreadable.status_code == 400
    assert "width:height" in unreadable.json()["error"]
    assert inverted.status_code == 400
    assert "wider than the widest" in inverted.json()["error"]
    assert _wall_named(http, the_wall["name"])["widest"] is None


def test_a_wall_says_why_it_judged_no_work_for_size_over_http(http, the_wall):
    wall = _wall_named(http, the_wall["name"])

    assert (wall["too_small"], wall["sizes_judged_against"], wall["sizes_unjudged"]) == ([], None, "no_display")


def _slot_now(settings, wall_id):
    """The work a wall's feed shows now and since when: its first slot, which a republish keeps."""
    first = json.loads(settings.manifest_v2_path(wall_id).read_text(encoding="utf-8"))["schedule"]["slots"][0]
    return first["work_id"], first["from"]
