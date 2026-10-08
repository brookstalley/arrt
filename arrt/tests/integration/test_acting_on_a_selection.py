"""Acting on a selection: by its ids, or on every work a filter matches.

*Select all* on a list means every work its filter matches, including the ones
the screen has not loaded (`build-plan-lists-settings-and-scale.md` Chunk 05,
#285). So the routes that act on a selection take the filter itself, and the
server resolves it exactly as `GET /api/works` would: a test here that a filter
reaches past one page uses more works than the listing's default page holds.

Every fixture holds a work the asserted filter would also select if a narrowing
were dropped, so a route that ignored the filter would fail rather than pass.
"""

import httpx
import pytest

from arrt.library.services.catalogue import DEFAULT_LIST_LIMIT
from arrt.persistence.records import ArtworkStatus, FacetDerivation, VocabularyKind

#: More than one page, and not a multiple of it, so a route that acted only on
#: the first page — or dropped the boundary row — leaves a remainder to see.
PAST_ONE_PAGE = DEFAULT_LIST_LIMIT * 2 + 3


@pytest.fixture
def studies(services, seeded_service):
    """`PAST_ONE_PAGE` works titled "Study …", beside the three seeded works the search must leave out."""
    return [seeded_service.add_artwork(title=f"Study number {number:03d}").id for number in range(PAST_ONE_PAGE)]


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=60.0) as client:
        yield client


def test_select_all_adds_every_work_the_filter_matches_not_one_page(http, services, studies):
    theme = services.display.add_theme(name="Studies")

    answer = http.post(f"/api/themes/{theme.id}/works/bulk", json={"filter": {"q": "study"}})

    assert answer.status_code == 200, answer.text
    assert answer.json() == {"added": PAST_ONE_PAGE, "already": 0}
    assert set(services.display.theme_work_ids(theme.id)) == set(studies)


def test_works_join_in_the_order_the_listing_shows_them(http, services, studies):
    """The theme's order is the one the curator saw, title order by default."""
    theme = services.display.add_theme(name="Studies")

    http.post(f"/api/themes/{theme.id}/works/bulk", json={"filter": {"q": "study"}}).raise_for_status()

    assert services.display.theme_work_ids(theme.id) == studies


def test_the_works_unticked_after_select_all_are_left_out(http, services, studies):
    theme = services.display.add_theme(name="Studies")
    unticked = [studies[0], studies[-1]]

    answer = http.post(f"/api/themes/{theme.id}/works/bulk", json={"filter": {"q": "study"}, "except_ids": unticked})

    assert answer.json()["added"] == PAST_ONE_PAGE - 2
    assert not set(unticked) & set(services.display.theme_work_ids(theme.id))


def test_works_the_theme_holds_are_counted_and_passed_over(http, services, studies):
    theme = services.display.add_theme(name="Studies")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=studies[5])

    answer = http.post(f"/api/themes/{theme.id}/works/bulk", json={"filter": {"q": "study"}})

    assert answer.json() == {"added": PAST_ONE_PAGE - 1, "already": 1}
    # The work already there keeps its place at the front rather than moving.
    assert services.display.theme_work_ids(theme.id)[0] == studies[5]
    assert len(services.display.theme_work_ids(theme.id)) == PAST_ONE_PAGE


def test_a_filter_naming_a_theme_and_a_facet_means_both(http, services, seeded_service, studies):
    """Composed as the listing composes them: the theme's ids, narrowed by the facet."""
    source = services.display.add_theme(name="Source")
    for artwork_id in studies[:4]:
        services.display.add_to_theme(theme_id=source.id, artwork_id=artwork_id)
    # Realism on two members and on one non-member, which only a dropped theme would select.
    for artwork_id in (studies[0], studies[1], studies[10]):
        seeded_service.record_facet(
            artwork_id=artwork_id, kind=VocabularyKind.MOVEMENT, value="Realism", derivation=FacetDerivation.INFERRED
        )
    target = services.display.add_theme(name="Target")

    http.post(
        f"/api/themes/{target.id}/works/bulk", json={"filter": {"theme": source.id, "movement": ["Realism"]}}
    ).raise_for_status()

    assert set(services.display.theme_work_ids(target.id)) == {studies[0], studies[1]}


def test_ids_are_accepted_as_well_as_a_filter(http, services, studies):
    theme = services.display.add_theme(name="Two")

    answer = http.post(f"/api/themes/{theme.id}/works/bulk", json={"artwork_ids": studies[:2]})

    assert answer.json() == {"added": 2, "already": 0}


@pytest.mark.parametrize(
    "body",
    [{}, {"artwork_ids": ["x"], "filter": {"q": "study"}}],
    ids=["neither", "both"],
)
def test_a_selection_names_its_works_one_way(http, services, studies, body):
    theme = services.display.add_theme(name="Studies")

    answer = http.post(f"/api/themes/{theme.id}/works/bulk", json=body)

    assert answer.status_code == 400
    assert "either by their ids or by a filter" in answer.json()["error"]
    assert services.display.theme_work_ids(theme.id) == []


def test_an_unknown_id_refuses_the_whole_addition(http, services, studies):
    theme = services.display.add_theme(name="Studies")

    answer = http.post(f"/api/themes/{theme.id}/works/bulk", json={"artwork_ids": [studies[0], "no-such-work"]})

    assert answer.status_code == 400
    assert services.display.theme_work_ids(theme.id) == []


def test_removing_by_filter_takes_out_every_match_and_names_them(http, services, studies):
    theme = services.display.add_theme(name="Studies")
    for artwork_id in studies:
        services.display.add_to_theme(theme_id=theme.id, artwork_id=artwork_id)
    keep = studies[3]

    answer = http.post(f"/api/themes/{theme.id}/works/remove", json={"filter": {"theme": theme.id}, "except_ids": [keep]})

    assert answer.status_code == 200, answer.text
    assert set(answer.json()["removed"]) == set(studies) - {keep}
    assert services.display.theme_work_ids(theme.id) == [keep]


def test_archiving_by_filter_archives_every_match_and_passes_over_the_archived(http, seeded_service, studies):
    seeded_service.archive_artwork(studies[7])

    answer = http.post("/api/works/archive", json={"filter": {"q": "study"}})

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["already"] == 1
    assert set(body["archived"]) == set(studies) - {studies[7]}
    statuses = {seeded_service.get_artwork(artwork_id).artwork.status for artwork_id in studies}
    assert statuses == {ArtworkStatus.ARCHIVED}
    # The three seeded works the search does not match are untouched.
    others = [entry.artwork for entry in seeded_service.list_artworks(q="nighthawks").entries]
    assert [work.status for work in others] == [ArtworkStatus.ACCEPTED]


def test_an_unknown_id_refuses_the_whole_archive(http, seeded_service, studies):
    answer = http.post("/api/works/archive", json={"artwork_ids": [studies[0], "no-such-work"]})

    assert answer.status_code == 400
    assert seeded_service.get_artwork(studies[0]).artwork.status is ArtworkStatus.ACCEPTED
