"""The history: each act writes exactly one event, read back through `GET /api/history`.

Driven through the HTTP surface against a real server, because the claim is
about the act a curator performs, not about the store: a write site that a route
bypassed, or a route that wrote twice (once in the service, once somewhere
above it), would pass every unit test of `record_event` and fail here.

Each act is performed with values a default would not produce (a second wall,
a reason, a named theme, a non-default title) so that an event carrying the
wrong wall or the wrong work cannot pass by coincidence. "Exactly one" is
asserted over the whole history of that kind, not only the rows naming the
work, so a duplicate written with a missing reference is caught too.
"""

import time

import httpx
import pytest
from fakes import a_work_list

from arrt.persistence.discovery_records import RunStatus


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def history(http: httpx.Client, **params) -> list[dict]:
    response = http.get("/api/history", params={"limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()["events"]


def of_kind(http: httpx.Client, kind: str) -> list[dict]:
    return history(http, kind=kind)


def settled(http: httpx.Client, run_id: str, status: str) -> dict:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        view = http.get(f"/api/runs/{run_id}").json()
        if view["run"]["status"] == status:
            return view
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never reached {status}: {view}")


class TestEachActWritesOneEvent:
    def test_an_ask_writes_one_start_and_its_decline_one_finish(self, http, engine, settings):
        engine.result = a_work_list(settings.discovery_settings.approval_threshold + 1)
        run_id = http.post("/api/runs", json={"intent": "Everything Dalí ever painted"}).json()["run_id"]
        settled(http, run_id, RunStatus.AWAITING_APPROVAL)

        assert http.post(f"/api/runs/{run_id}/decline").status_code == 200

        started = of_kind(http, "get.started")
        assert [(event["run_id"], event["detail"]) for event in started] == [
            (run_id, {"run_kind": "discovery", "intent": "Everything Dalí ever painted"})
        ]
        finished = of_kind(http, "get.finished")
        assert [(event["run_id"], event["detail"]["status"]) for event in finished] == [(run_id, "declined")]

    def test_a_cancelled_get_carries_how_it_ended_once(self, http, engine, settings):
        engine.result = a_work_list(settings.discovery_settings.approval_threshold + 1)
        run_id = http.post("/api/runs", json={"intent": "Surrealists"}).json()["run_id"]
        settled(http, run_id, RunStatus.AWAITING_APPROVAL)

        http.post(f"/api/runs/{run_id}/cancel")
        # A second cancel is refused, and a refused act writes nothing.
        assert http.post(f"/api/runs/{run_id}/cancel").status_code == 400

        assert [event["detail"]["status"] for event in of_kind(http, "get.finished")] == ["cancelled"]

    def test_accepting_writes_one_event_naming_the_work_it_became(self, http, resolved_work):
        candidate = resolved_work("The Elephants")

        accepted = http.post(f"/api/candidates/{candidate.id}/verdict", json={"verdict": "accepted"}).json()

        events = of_kind(http, "work.accepted")
        assert len(events) == 1
        assert events[0]["artwork_id"] == accepted["work"]["artwork_id"]
        assert events[0]["run_id"] == candidate.discovery_run_id
        assert events[0]["detail"] == {"title": "The Elephants", "candidate_work_id": candidate.id}
        assert of_kind(http, "work.rejected") == []

    def test_rejecting_writes_one_event_naming_the_candidate(self, http, resolved_work):
        candidate = resolved_work("Swans Reflecting Elephants")

        response = http.post(
            f"/api/candidates/{candidate.id}/verdict", json={"verdict": "rejected", "reason": "Too busy for the hall"}
        )
        assert response.status_code == 200
        # A verdict is final, so a second is refused and writes nothing.
        assert http.post(f"/api/candidates/{candidate.id}/verdict", json={"verdict": "accepted"}).status_code == 400

        events = of_kind(http, "work.rejected")
        assert [(event["artwork_id"], event["detail"]) for event in events] == [
            (None, {"title": "Swans Reflecting Elephants", "candidate_work_id": candidate.id})
        ]
        assert of_kind(http, "work.accepted") == []

    def test_archiving_and_restoring_write_one_event_each(self, http, ready_work):
        work = ready_work("Automat")

        http.post(f"/api/works/{work.id}/archive")
        # Archiving an archived work is refused, and leaves the history alone.
        assert http.post(f"/api/works/{work.id}/archive").status_code == 400
        http.post(f"/api/works/{work.id}/restore")

        assert [(event["artwork_id"], event["detail"]) for event in of_kind(http, "work.archived")] == [
            (work.id, {"title": "Automat"})
        ]
        assert [event["artwork_id"] for event in of_kind(http, "work.restored")] == [work.id]

    def test_hanging_a_theme_writes_one_event_with_the_wall_and_what_it_was_drawn_from(self, http, ready_work):
        work = ready_work("Automat")
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
        study = http.post("/api/walls", json={"name": "The study"}).json()

        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": study["wall_id"]})

        events = of_kind(http, "wall.hung")
        assert len(events) == 1
        assert events[0]["wall_id"] == study["wall_id"]
        assert events[0]["theme_id"] == theme["theme_id"]
        assert events[0]["detail"] == {"theme_name": "Late night", "selection": False, "works": 1, "wall_name": "The study"}

    def test_a_hang_that_is_refused_writes_nothing(self, http):
        study = http.post("/api/walls", json={"name": "The study"}).json()

        response = http.post("/api/themes/no-such-theme/activate", json={"wall_id": study["wall_id"]})

        assert response.status_code == 400
        assert of_kind(http, "wall.hung") == []


class TestReadingTheHistory:
    @pytest.fixture
    def three_acts(self, http, ready_work):
        """An archive, a restore and a hang on a second wall, in that order."""
        work = ready_work("Automat")
        http.post(f"/api/works/{work.id}/archive")
        http.post(f"/api/works/{work.id}/restore")
        theme = http.post("/api/themes", json={"name": "Late night"}).json()
        study = http.post("/api/walls", json={"name": "The study"}).json()
        http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": study["wall_id"]})
        return study

    def test_newest_first(self, http, three_acts):
        assert [event["kind"] for event in history(http)] == ["wall.hung", "work.restored", "work.archived"]

    def test_kinds_repeat_and_any_of_them_matches(self, http, three_acts):
        kinds = [event["kind"] for event in history(http, kind=["work.archived", "wall.hung"])]

        assert kinds == ["wall.hung", "work.archived"]

    def test_a_wall_has_its_own_history(self, http, three_acts):
        the_wall = next(wall for wall in http.get("/api/walls").json()["walls"] if wall["name"] != "The study")

        assert [event["kind"] for event in history(http, wall_id=three_acts["wall_id"])] == ["wall.hung"]
        assert history(http, wall_id=the_wall["wall_id"]) == []

    def test_a_page_says_where_it_sits(self, http, three_acts):
        page = http.get("/api/history", params={"limit": 1, "offset": 1}).json()

        assert [event["kind"] for event in page["events"]] == ["work.restored"]
        assert (page["total"], page["limit"], page["offset"]) == (3, 1, 1)

    def test_an_unknown_kind_is_refused_in_words(self, http):
        response = http.get("/api/history", params={"kind": "work.hung"})

        assert response.status_code == 400
        assert "work.hung" in response.json()["error"]
