"""`GET /api/works/{id}/placements`: where a held work is, against a real server.

The Work page's state strip says which walls and themes a work is on from this
one read. Two walls appear wherever a wall is named, since with one wall "the
wall hanging it" and "some wall" look the same, and every fixture carries a
theme that does *not* hold the work, so an answer listing every theme fails.
"""

import httpx
import pytest


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def a_theme_holding(http, name: str, *works) -> dict:
    theme = http.post("/api/themes", json={"name": name}).json()
    for work in works:
        response = http.post(f"/api/themes/{theme['theme_id']}/works", json={"artwork_id": work.id})
        assert response.status_code == 200, response.text
    return theme


def placements(http, work) -> dict:
    response = http.get(f"/api/works/{work.id}/placements")
    assert response.status_code == 200, response.text
    return response.json()


def by_name(answer: dict) -> dict[str, dict]:
    return {placement["theme"]["name"]: placement for placement in answer["themes"]}


def test_a_work_in_a_theme_and_a_selection_names_both_with_the_walls_hanging_each(http, ready_work):
    work = ready_work("Automat")
    other = ready_work("Nighthawks")
    hall = http.get("/api/walls").json()["walls"][0]
    study = http.post("/api/walls", json={"name": "Study"}).json()
    late = a_theme_holding(http, "Late night", work, other)
    a_theme_holding(http, "Without it", other)
    assert http.post(f"/api/themes/{late['theme_id']}/activate", json={"wall_id": hall["wall_id"]}).status_code == 200
    assert http.post(f"/api/walls/{study['wall_id']}/selection", json={"artwork_ids": [work.id]}).status_code == 200

    answer = placements(http, work)

    themes = by_name(answer)
    assert answer["artwork_id"] == work.id
    assert answer["excluded_at"] is None
    assert len(themes) == 2, "a theme without the work, or a missing one, changes the count"
    assert "Without it" not in themes
    assert themes["Late night"]["theme"]["hidden"] is False
    assert [wall["name"] for wall in themes["Late night"]["hanging_on"]] == [hall["name"]]
    (selection,) = [placement for placement in answer["themes"] if placement["theme"]["hidden"]]
    assert [wall["name"] for wall in selection["hanging_on"]] == ["Study"]


def test_a_selection_taken_down_is_still_listed_hanging_nowhere(http, ready_work):
    """The server reports it; leaving an old selection unsaid is the page's choice."""
    work = ready_work("Automat")
    other = ready_work("Nighthawks")
    wall = http.get("/api/walls").json()["walls"][0]
    http.post(f"/api/walls/{wall['wall_id']}/selection", json={"artwork_ids": [work.id]})
    http.post(f"/api/walls/{wall['wall_id']}/selection", json={"artwork_ids": [other.id]})

    (selection,) = placements(http, work)["themes"]

    assert selection["theme"]["hidden"] is True
    assert selection["hanging_on"] == []


def test_a_work_kept_off_every_wall_says_since_when_and_the_undo_clears_it(http, ready_work):
    work = ready_work("Automat")
    other = ready_work("Nighthawks")
    wall = http.get("/api/walls").json()["walls"][0]
    theme = a_theme_holding(http, "Late night", work, other)
    http.post(f"/api/themes/{theme['theme_id']}/activate", json={"wall_id": wall["wall_id"]})
    kept = http.post(f"/api/walls/{wall['wall_id']}/not-again", json={"artwork_id": work.id, "scope": "every_wall"})
    assert kept.status_code == 200, kept.text

    assert placements(http, work)["excluded_at"] == kept.json()["excluded_at"]
    assert placements(http, other)["excluded_at"] is None
    # Kept off every wall, and still in its theme.
    assert list(by_name(placements(http, work))) == ["Late night"]

    assert http.delete(f"/api/exclusions/{work.id}").status_code == 200
    assert placements(http, work)["excluded_at"] is None


def test_a_work_the_catalogue_does_not_hold_is_refused(http):
    response = http.get("/api/works/no-such-work/placements")

    assert response.status_code == 400
    assert "no-such-work" in response.json()["error"]
