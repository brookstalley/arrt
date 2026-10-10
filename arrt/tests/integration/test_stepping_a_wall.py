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

    def test_a_step_leaves_every_other_walls_feed_alone(self, http, settings, ready_work, the_wall):
        """On a one-wall deployment the two behaviours are indistinguishable, which is why this is asserted with two."""
        study = http.post("/api/walls", json={"name": "The study"}).json()
        theme = _hang(http, the_wall, ready_work("Automat"), ready_work("Chop Suey"))
        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": study["wall_id"]})
        untouched = settings.manifest_v2_path(study["wall_id"]).read_bytes()

        http.post(f"/api/walls/{the_wall['wall_id']}/next")

        assert settings.manifest_v2_path(study["wall_id"]).read_bytes() == untouched

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

        The first wall's published file is compared before and after, because the
        failure worth catching is a second activation rewriting it.
        """
        work = ready_work(title="Automat")
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
        study = http.post("/api/walls", json={"name": "The study"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": the_wall["wall_id"]})
        first = json.loads(settings.manifest_v2_path(the_wall["wall_id"]).read_text(encoding="utf-8"))

        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": study["wall_id"]})

        assert json.loads(settings.manifest_v2_path(the_wall["wall_id"]).read_text(encoding="utf-8")) == first
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


def test_a_wall_says_why_it_judged_no_work_for_size_over_http(http, the_wall):
    wall = _wall_named(http, the_wall["name"])

    assert (wall["too_small"], wall["sizes_judged_against"], wall["sizes_unjudged"]) == ([], None, "no_display")
