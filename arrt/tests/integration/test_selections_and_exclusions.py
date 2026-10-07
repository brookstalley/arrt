"""Hanging a selection of works, and *Not this one again*, over both surfaces against a real server.

The evidence is the published manifest on disk wherever the claim is about a
wall, because the file is what a Player reads: a route that answered with the
right build while publishing something else would pass every assertion made over
JSON. Two walls appear wherever "every wall" is the claim, since with one wall
"this wall" and "every wall" look the same.
"""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def the_wall(http):
    walls = http.get("/api/walls").json()["walls"]
    assert len(walls) == 1
    return walls[0]


def published(settings, wall_id: str) -> list[str]:
    """The work ids a wall's published manifest carries, read off the file a Player reads."""
    document = json.loads(settings.manifest_path(wall_id).read_text())
    return [entry["work_id"] for entry in document["entries"]]


def a_theme_holding(http, name: str, *works) -> dict:
    theme = http.post("/api/themes", json={"name": name}).json()
    for work in works:
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
    return theme


def hang(http, theme: dict, wall: dict) -> dict:
    response = http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})
    assert response.status_code == 200, response.text
    return response.json()


def events(http, kind: str) -> list[dict]:
    return http.get("/api/history", params={"kind": kind}).json()["events"]


class TestHangingASelection:
    def test_a_one_work_selection_is_what_the_walls_manifest_carries(self, http, settings, ready_work, the_wall):
        hung = ready_work("Automat")
        ready_work("Nighthawks at the Diner")

        response = http.post(f"/api/walls/{the_wall['wall_id']}/selection", json={"artwork_ids": [hung.id]})

        assert response.status_code == 200, response.text
        assert [entry["artwork_id"] for entry in response.json()["entries"]] == [hung.id]
        assert published(settings, the_wall["wall_id"]) == [hung.id]

    def test_the_selection_hangs_until_changed_and_reads_as_hidden_on_the_wall(self, http, ready_work, the_wall):
        work = ready_work("Automat")

        http.post(f"/api/walls/{the_wall['wall_id']}/selection", json={"artwork_ids": [work.id]})

        hanging = next(wall for wall in http.get("/api/walls").json()["walls"] if wall["wall_id"] == the_wall["wall_id"])
        assert hanging["theme"]["hidden"] is True

    def test_the_themes_index_and_the_theme_pickers_leave_a_selection_out(self, http, ready_work, the_wall):
        work = ready_work("Automat")
        a_theme_holding(http, "Late night", work)

        http.post(f"/api/walls/{the_wall['wall_id']}/selection", json={"artwork_ids": [work.id]})

        listed = [placement["theme"] for placement in http.get("/api/themes").json()["themes"]]
        assert [(theme["name"], theme["hidden"]) for theme in listed] == [("Late night", False)]
        # The works grid's theme filter is a picker too.
        options = http.get("/api/works").json()["themes"]
        assert [option["name"] for option in options] == ["Late night"]

    def test_several_works_hang_in_the_order_chosen(self, http, settings, ready_work, the_wall):
        first, second = ready_work("Automat"), ready_work("Chop Suey")

        http.post(f"/api/walls/{the_wall['wall_id']}/selection", json={"artwork_ids": [second.id, first.id]})

        assert published(settings, the_wall["wall_id"]) == [second.id, first.id]

    def test_hanging_a_selection_writes_one_hang_event_saying_so(self, http, ready_work, the_wall):
        work = ready_work("Automat")

        http.post(f"/api/walls/{the_wall['wall_id']}/selection", json={"artwork_ids": [work.id]})

        hung = events(http, "wall.hung")
        assert len(hung) == 1
        assert hung[0]["wall_id"] == the_wall["wall_id"]
        assert hung[0]["detail"]["selection"] is True
        assert hung[0]["detail"]["works"] == 1

    def test_an_empty_selection_and_an_unknown_work_are_refused_and_nothing_hangs(self, http, the_wall):
        empty = http.post(f"/api/walls/{the_wall['wall_id']}/selection", json={"artwork_ids": []})
        unknown = http.post(f"/api/walls/{the_wall['wall_id']}/selection", json={"artwork_ids": ["no-such-work"]})

        assert (empty.status_code, unknown.status_code) == (400, 400)
        assert http.get("/api/walls").json()["walls"][0]["theme"] is None
        assert events(http, "wall.hung") == []


class TestNotThisOneAgain:
    @pytest.fixture
    def two_walls_hanging(self, http, ready_work, the_wall):
        """One work on two walls through two themes, beside a work that stays."""
        gone, stays = ready_work("Automat"), ready_work("Chop Suey")
        study = http.post("/api/walls", json={"name": "The study"}).json()
        hang(http, a_theme_holding(http, "Late night", gone, stays), the_wall)
        hang(http, a_theme_holding(http, "Hopper", gone, stays), study)
        return gone, stays, study

    def test_from_this_theme_takes_it_out_of_that_theme_and_off_that_wall_now(self, http, settings, the_wall, two_walls_hanging):
        gone, stays, study = two_walls_hanging

        response = http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "theme"})

        assert response.status_code == 200, response.text
        assert response.json()["left_theme"]["name"] == "Late night"
        assert published(settings, the_wall["wall_id"]) == [stays.id]
        # The other wall hangs another theme, which still holds it.
        assert published(settings, study["wall_id"]) == [gone.id, stays.id]
        assert http.get(f"/api/works/{gone.id}").json()["work"]["status"] == "accepted"

    def test_from_every_wall_keeps_it_off_every_wall_and_in_the_library(self, http, settings, the_wall, two_walls_hanging):
        gone, stays, study = two_walls_hanging

        response = http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "every_wall"})

        assert response.status_code == 200, response.text
        assert published(settings, the_wall["wall_id"]) == [stays.id]
        assert published(settings, study["wall_id"]) == [stays.id]
        # Still held, still in both themes: only the walls changed.
        assert http.get(f"/api/works/{gone.id}").json()["work"]["status"] == "accepted"
        for theme in http.get("/api/themes").json()["themes"]:
            detail = http.get(f"/api/themes/{theme['theme']['theme_id']}").json()
            assert gone.id in [work["artwork_id"] for work in detail["works"]]
        assert [row["artwork_id"] for row in http.get("/api/exclusions").json()["exclusions"]] == [gone.id]

    def test_a_rebuild_leaves_an_excluded_work_off_and_says_why(self, http, settings, the_wall, two_walls_hanging):
        gone, stays, study = two_walls_hanging
        http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "every_wall"})

        rebuilt = hang(http, http.get("/api/themes").json()["themes"][0]["theme"], study)

        assert published(settings, study["wall_id"]) == [stays.id]
        assert [(row["artwork_id"], row["reason"]) for row in rebuilt["exclusions"]] == [(gone.id, "kept_off_every_wall")]

    def test_undo_lets_it_back_on_at_the_next_hang(self, http, settings, the_wall, two_walls_hanging):
        gone, stays, study = two_walls_hanging
        http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "every_wall"})

        response = http.delete(f"/api/exclusions/{gone.id}")

        assert response.status_code == 200
        assert response.json()["exclusions"] == []
        # Nothing is republished by the undo itself; the next hang carries it.
        assert published(settings, study["wall_id"]) == [stays.id]
        hopper = next(p["theme"] for p in http.get("/api/themes").json()["themes"] if p["theme"]["name"] == "Hopper")
        hang(http, hopper, study)
        assert published(settings, study["wall_id"]) == [gone.id, stays.id]

    def test_an_excluded_work_cannot_be_pinned(self, http, services, the_wall, two_walls_hanging):
        gone, _, _ = two_walls_hanging
        http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "every_wall"})

        with pytest.raises(Exception, match="kept off every wall"):
            services.display.show_work_now(the_wall["wall_id"], gone.id)

    def test_a_pin_on_the_work_is_withdrawn_without_advancing(self, http, services, settings, the_wall, two_walls_hanging):
        gone, _, _ = two_walls_hanging
        pinned = services.display.show_work_now(the_wall["wall_id"], gone.id)

        http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "theme"})

        directive = json.loads(settings.manifest_path(the_wall["wall_id"]).read_text())["directive"]
        assert directive == {"sequence": pinned.sequence, "pinned_work_id": None}
        # And the standing directive itself, which the next build publishes.
        wall = next(wall for wall in http.get("/api/walls").json()["walls"] if wall["wall_id"] == the_wall["wall_id"])
        assert (wall["directive_sequence"], wall["pinned_work_id"]) == (pinned.sequence, None)

    def test_each_answer_and_its_undo_write_one_event(self, http, the_wall, two_walls_hanging):
        gone, stays, study = two_walls_hanging
        http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": stays.id, "scope": "theme"})
        http.post(f"/api/walls/{study['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "every_wall"})
        http.delete(f"/api/exclusions/{gone.id}")

        left = events(http, "work.left_theme")
        assert [(event["artwork_id"], event["wall_id"], event["detail"]["theme_name"]) for event in left] == [
            (stays.id, the_wall["wall_id"], "Late night")
        ]
        assert [(event["artwork_id"], event["wall_id"]) for event in events(http, "work.excluded")] == [
            (gone.id, study["wall_id"])
        ]
        assert [event["artwork_id"] for event in events(http, "work.allowed")] == [gone.id]
        # The study's history shows what was hung there and what was kept off from there.
        study_history = http.get("/api/history", params={"wall_id": study["wall_id"]}).json()["events"]
        assert [event["kind"] for event in study_history] == ["work.excluded", "wall.hung"]

    def test_refusals_write_nothing(self, http, the_wall, two_walls_hanging):
        gone, _, _ = two_walls_hanging
        http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "theme"})

        again = http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "theme"})
        badly = http.post(f"/api/walls/{the_wall['wall_id']}/not-again", json={"artwork_id": gone.id, "scope": "wall"})
        not_kept = http.delete(f"/api/exclusions/{gone.id}")

        assert (again.status_code, badly.status_code, not_kept.status_code) == (400, 400, 400)
        assert len(events(http, "work.left_theme")) == 1
        assert events(http, "work.excluded") == events(http, "work.allowed") == []


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


class TestTheToolSurface:
    async def test_hang_a_selection_then_keep_it_off_then_allow_it(self, server_url, settings, ready_work):
        work = ready_work("Automat")
        walls, _ = await call(server_url, "art_display", action="walls")
        wall_id = walls["walls"][0]["wall_id"]

        hung, error = await call(server_url, "art_theme", action="hang_selection", wall_id=wall_id, artwork_ids=[work.id])
        assert not error, hung
        assert hung["theme"]["hidden"] is True
        assert published(settings, wall_id) == [work.id]
        listed, _ = await call(server_url, "art_theme", action="list")
        assert listed["themes"] == []

        kept, error = await call(
            server_url, "art_theme", action="not_again", wall_id=wall_id, artwork_id=work.id, scope="every_wall"
        )
        assert not error, kept
        assert kept["excluded_at"] is not None
        assert published(settings, wall_id) == []
        off, _ = await call(server_url, "art_theme", action="kept_off")
        assert [row["artwork_id"] for row in off["exclusions"]] == [work.id]

        allowed, error = await call(server_url, "art_theme", action="allow_again", artwork_id=work.id)
        assert not error, allowed
        off, _ = await call(server_url, "art_theme", action="kept_off")
        assert off["exclusions"] == []

        told, error = await call(server_url, "art_catalogue", action="history", wall_id=wall_id)
        assert not error, told
        assert [event["kind"] for event in told["events"]] == ["work.excluded", "wall.hung"]
        everything, _ = await call(server_url, "art_catalogue", action="history", kinds=["work.allowed"])
        assert [event["artwork_id"] for event in everything["events"]] == [work.id]

    async def test_from_this_theme_over_the_tool_names_the_theme_it_left(self, server_url, ready_work):
        work, other = ready_work("Automat"), ready_work("Chop Suey")
        walls, _ = await call(server_url, "art_display", action="walls")
        wall_id = walls["walls"][0]["wall_id"]
        await call(server_url, "art_theme", action="hang_selection", wall_id=wall_id, artwork_ids=[work.id, other.id])

        left, error = await call(server_url, "art_theme", action="not_again", wall_id=wall_id, artwork_id=work.id, scope="theme")

        assert not error, left
        assert left["left_theme"]["hidden"] is True
        assert left["excluded_at"] is None
