"""Artworks' clean-up facets: *Size on the wall* and *Not on any wall* (#288).

`build-plan-lists-settings-and-scale.md` Chunk 06. Both are counted by the
server like the existing facets — each option's count is what choosing it
would select given every other filter, its own selection dropped — and both
compose with the search, the theme and the other facets.

**The two cross the seam in opposite directions and neither plane reaches the
other.** The fit band is the Library's (`SurveyService.fit_bands`, the verdict a
card shows); which works a wall plays now is Programming's
(`DisplayService.work_ids_on_walls`). The bindings meet them as id sets and hand
the Library the result as the `within` restriction it already lists theme
slices by.

*Not on any wall* is the owner's ruling of 2026-10-08: works no wall plays now,
through any hung theme or selection. Which works a wall has *shown* is not
recorded, so "never hung" is not what it answers.
"""

import httpx
import pytest

from arrt.library.services.display_fit import assess_display_fit
from arrt.library.services.survey import FIT_BANDS
from arrt.persistence.records import (
    AcquisitionMethod,
    FacetDerivation,
    FetchStatus,
    RightsStatus,
    SourceClass,
    VocabularyKind,
)

#: Three masters, each meant to land in its own band on the test deployment's
#: box. The fixture asserts that they do, so a box that changed under the test
#: fails there rather than making the counts below mean something else.
SIZES = {
    "A large scan": (12000, 8000),
    "A middling scan": (1600, 1000),
    "A tiny scan": (120, 80),
}
EXPECTED = {"A large scan": "native", "A middling scan": "matted_small", "A tiny scan": "below_floor"}


def _with_master(service, title, width, height):
    artwork = service.add_artwork(title=title)
    source = service.add_source(
        artwork_id=artwork.id,
        url=f"https://museum.example/{artwork.id}",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    service.record_original(
        artwork_id=artwork.id,
        source_id=source.id,
        path=f"raw/{artwork.id}.jpg",
        width=width,
        height=height,
        byte_size=1000,
        content_hash=f"hash-{artwork.id}",
        fetch_status=FetchStatus.OK,
    )
    return artwork


@pytest.fixture
def sized(seeded_service, settings):
    """The three seeded works, which hold no master, and three that do, one per band."""
    works = {title: _with_master(seeded_service, title, *size) for title, size in SIZES.items()}
    for title, (width, height) in SIZES.items():
        band = str(assess_display_fit(width=width, height=height, box=settings.tv_artwork_box).fit)
        assert band == EXPECTED[title], f"{title} is {band} on this box, so the fixture no longer spans the bands"
    return works


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def _fits(page):
    return {option["value"]: (option["count"], option["selected"], option["disabled"]) for option in page["fits"]}


def _titles(page):
    return sorted(work["title"] for work in page["works"])


class TestSizeOnTheWall:
    def test_every_band_is_offered_in_order_and_counted(self, http, sized):
        page = http.get("/api/works").json()

        assert [option["value"] for option in page["fits"]] == list(FIT_BANDS)
        assert _fits(page) == {
            "native": (1, False, False),
            "matted_small": (1, False, False),
            "below_floor": (1, False, False),
            # The seeded three hold no master, and are a band of their own
            # rather than left out, so the bands add up to the works.
            "unknown": (3, False, False),
        }

    def test_a_band_narrows_the_works_and_its_own_counts_ignore_it(self, http, sized):
        page = http.get("/api/works", params={"fit": "below_floor"}).json()

        assert _titles(page) == ["A tiny scan"]
        assert page["total"] == 1
        # The other bands keep their counts, so the curator can change their mind.
        assert _fits(page)["native"] == (1, False, False)
        assert _fits(page)["below_floor"] == (1, True, False)

    def test_two_bands_mean_either(self, http, sized):
        page = http.get("/api/works", params=[("fit", "native"), ("fit", "matted_small")]).json()

        assert _titles(page) == ["A large scan", "A middling scan"]

    def test_a_band_composes_with_the_search(self, http, sized):
        page = http.get("/api/works", params={"q": "scan", "fit": "unknown"}).json()

        # "scan" selects only works with a master, so no work is both.
        assert page["total"] == 0
        assert _fits(page)["unknown"] == (0, True, False)
        assert _fits(page)["native"] == (1, False, False)

    def test_a_band_narrows_the_other_facets_counts(self, http, sized, seeded_service):
        for title in ("A large scan", "A tiny scan"):
            seeded_service.record_facet(
                artwork_id=sized[title].id, kind=VocabularyKind.MOVEMENT, value="Realism", derivation=FacetDerivation.INFERRED
            )

        page = http.get("/api/works", params={"fit": "native"}).json()

        movement = next(group for group in page["facets"] if group["kind"] == "movement")
        assert {option["value"]: option["count"] for option in movement["options"]} == {"Realism": 1}

    def test_an_unknown_band_is_refused_by_name(self, http, sized):
        answer = http.get("/api/works", params={"fit": "huge"})

        assert answer.status_code == 400
        assert "'huge'" in answer.json()["error"]


@pytest.fixture
def hung(services, sized):
    """*A large scan* in a theme hanging on a wall; *A middling scan* in a theme that hangs nowhere."""
    wall = services.display.add_wall(name="The hall")
    on_show = services.display.add_theme(name="On show")
    services.display.add_to_theme(theme_id=on_show.id, artwork_id=sized["A large scan"].id)
    services.display.activate_theme(on_show.id, wall_id=wall.id)
    resting = services.display.add_theme(name="Resting")
    services.display.add_to_theme(theme_id=resting.id, artwork_id=sized["A middling scan"].id)
    return wall, on_show, resting


class TestNotOnAnyWall:
    def test_it_counts_every_work_no_hung_theme_holds(self, http, hung):
        page = http.get("/api/works").json()

        assert page["not_on_wall"] == {"value": "not_on_wall", "count": 5, "selected": False, "disabled": False}

    def test_it_leaves_out_what_a_hung_theme_holds_and_keeps_an_unhung_themes(self, http, hung):
        page = http.get("/api/works", params={"not_on_wall": "true"}).json()

        assert "A large scan" not in _titles(page)
        # In a theme, but one no wall hangs: not on any wall.
        assert "A middling scan" in _titles(page)
        assert page["total"] == 5
        assert page["not_on_wall"]["selected"] is True

    def test_a_hung_selection_counts_as_on_a_wall(self, http, services, hung, sized):
        wall, _, _ = hung
        services.display.hang_selection([sized["A tiny scan"].id], wall_id=wall.id)

        page = http.get("/api/works", params={"not_on_wall": "true"}).json()

        assert "A tiny scan" not in _titles(page)
        # The selection replaced the theme on the hall, so the large scan is off it now.
        assert "A large scan" in _titles(page)

    def test_a_work_kept_off_every_wall_is_not_on_one(self, http, services, hung, sized):
        services.display.exclude_work(sized["A large scan"].id)

        page = http.get("/api/works", params={"not_on_wall": "true"}).json()

        assert "A large scan" in _titles(page)

    def test_it_composes_with_a_band_both_ways(self, http, hung):
        page = http.get("/api/works", params={"not_on_wall": "true", "fit": "native"}).json()

        # The only native work is on the wall.
        assert page["total"] == 0
        assert _fits(page)["native"] == (0, True, False)
        assert _fits(page)["below_floor"] == (1, False, False)
        # And counted under the band, *Not on any wall* says it would select none.
        assert page["not_on_wall"]["count"] == 0

    def test_a_theme_option_is_counted_under_it(self, http, hung):
        page = http.get("/api/works", params={"not_on_wall": "true"}).json()

        counts = {option["name"]: (option["count"], option["disabled"]) for option in page["themes"]}
        assert counts["On show"] == (0, True)
        assert counts["Resting"] == (1, False)


def test_select_all_by_a_clean_up_filter_acts_on_exactly_its_works(http, services, hung, sized):
    target = services.display.add_theme(name="To look at")

    answer = http.post(
        f"/api/themes/{target.id}/works/bulk", json={"filter": {"not_on_wall": True, "fit": ["native", "matted_small"]}}
    )

    assert answer.json() == {"added": 1, "already": 0}
    assert services.display.theme_work_ids(target.id) == [sized["A middling scan"].id]
