"""A theme is one more filter on the works listing, composing with the rest.

Artworks' *Filter* rail offers a theme beside the facets (the owner's ruling on
#169, following Radarr's filters), so the listing has to answer "this theme's
works, narrowed by these facets and these words" — with facet counts about that
slice. Until this, a theme's works came only from `GET /api/themes/{id}`, which
cannot narrow, and the client made a theme and a facet exclusive.

A theme is Programming's and the listing is the Library's, so the Library is
handed the theme's members as opaque ids and learns nothing about themes; the
bindings compose the two calls, as `_theme_detail` already does.

Every fixture here holds a non-member that the asserted filter would select if
the theme narrowing were dropped, so an ignored theme fails rather than passes.
"""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.persistence.records import FacetDerivation, VocabularyKind


def _by_title(service, title):
    return next(entry.artwork for entry in service.list_artworks().entries if entry.artwork.title == title)


@pytest.fixture
def themed(services, seeded_service):
    """Four works, two in *Twentieth*; every work is Realism or Surrealism.

    Each member has a non-member twin that the asserted filter would also select
    if the theme were dropped: *Nighthawks* is Realism like *I Saw the Figure 5
    in Gold*, and *Swans Reflecting Elephants* is a Surrealist Dalí like *The
    Persistence of Memory*.
    """
    dali = _by_title(seeded_service, "The Persistence of Memory").artist_id
    seeded_service.add_artwork(title="Swans Reflecting Elephants", artist_id=dali, date_created="1937")
    facets = {
        "Nighthawks": "Realism",
        "Swans Reflecting Elephants": "Surrealism",
        "I Saw the Figure 5 in Gold": "Realism",
        "The Persistence of Memory": "Surrealism",
    }
    for title, movement in facets.items():
        seeded_service.record_facet(
            artwork_id=_by_title(seeded_service, title).id,
            kind=VocabularyKind.MOVEMENT,
            value=movement,
            derivation=FacetDerivation.INFERRED,
        )
    theme = services.display.add_theme(name="Twentieth")
    for title in ("I Saw the Figure 5 in Gold", "The Persistence of Memory"):
        services.display.add_to_theme(theme_id=theme.id, artwork_id=_by_title(seeded_service, title).id)
    empty = services.display.add_theme(name="Nothing yet")
    realists = services.display.add_theme(name="Realists")
    services.display.add_to_theme(theme_id=realists.id, artwork_id=_by_title(seeded_service, "Nighthawks").id)
    return theme.id, empty.id


def _movement_counts(facets, *, options="options"):
    """The movement group's counts from a payload; MCP names the list `values` where HTTP names it `options`."""
    group = next(group for group in facets if group["kind"] == "movement")
    return {option["value"]: option["count"] for option in group[options]}


class TestTheLibraryNarrowsToTheIdsItIsHanded:
    """The Library's half: an opaque id restriction that every other narrowing composes with."""

    def test_the_restriction_alone_selects_exactly_those_works(self, seeded_service):
        held = [_by_title(seeded_service, "Nighthawks").id]

        listing = seeded_service.list_artworks(within=held)

        assert [entry.artwork.title for entry in listing.entries] == ["Nighthawks"]
        assert listing.total == 1

    def test_an_empty_restriction_selects_nothing_rather_than_everything(self, seeded_service):
        """An empty theme is an empty grid; "no restriction" is `None`, never `[]`."""
        listing = seeded_service.list_artworks(within=[])

        assert (listing.total, list(listing.entries)) == (0, [])

    def test_an_id_the_library_does_not_hold_is_passed_over(self, seeded_service):
        """Programming holds work ids as references that may fail to resolve (seam rule 3)."""
        listing = seeded_service.list_artworks(within=["no-such-work", _by_title(seeded_service, "Nighthawks").id])

        assert [entry.artwork.title for entry in listing.entries] == ["Nighthawks"]


class TestTheHttpSurface:
    @pytest.fixture
    def http(self, server_url, themed):
        with httpx.Client(base_url=server_url, timeout=30.0) as client:
            yield client

    def test_a_theme_alone_lists_its_members(self, http, themed):
        theme_id, _ = themed

        payload = http.get("/api/works", params={"theme": theme_id}).raise_for_status().json()

        assert sorted(work["title"] for work in payload["works"]) == ["I Saw the Figure 5 in Gold", "The Persistence of Memory"]
        assert payload["total"] == 2

    def test_a_theme_and_a_facet_mean_both(self, http, themed):
        theme_id, _ = themed

        payload = http.get("/api/works", params={"theme": theme_id, "movement": "Realism"}).raise_for_status().json()

        assert [work["title"] for work in payload["works"]] == ["I Saw the Figure 5 in Gold"]

    def test_a_theme_and_text_mean_both(self, http, themed):
        theme_id, _ = themed

        payload = http.get("/api/works", params={"theme": theme_id, "q": "dali"}).raise_for_status().json()

        assert [work["title"] for work in payload["works"]] == ["The Persistence of Memory"]

    def test_the_facet_counts_are_about_the_themes_slice(self, http, themed):
        """Each movement is 2 across the catalogue and 1 within the theme; the counts beside the grid must say 1."""
        theme_id, _ = themed

        whole = http.get("/api/works").raise_for_status().json()
        sliced = http.get("/api/works", params={"theme": theme_id}).raise_for_status().json()

        assert _movement_counts(whole["facets"]) == {"Realism": 2, "Surrealism": 2}
        assert _movement_counts(sliced["facets"]) == {"Realism": 1, "Surrealism": 1}

    def test_an_empty_theme_is_an_empty_page(self, http, themed):
        _, empty_id = themed

        payload = http.get("/api/works", params={"theme": empty_id}).raise_for_status().json()

        assert (payload["total"], payload["works"]) == (0, [])

    def test_an_unknown_theme_is_refused_by_name_rather_than_ignored(self, http, themed):
        """Ignoring it would answer with the whole catalogue, labelled as a theme's."""
        response = http.get("/api/works", params={"theme": "no-such-theme"})

        assert response.status_code == 400
        assert "no-such-theme" in response.json()["error"]


def _themes(payload):
    return {option["name"]: (option["count"], option["selected"], option["disabled"]) for option in payload["themes"]}


class TestEachThemeIsAFilterOptionWithItsCount:
    """The *Filter* rail's Theme group follows the facet rule: a count per option, and no dead end.

    A theme's count is how many works it would select **given every other
    filter but the theme**, so a theme that would empty the grid is disabled
    rather than offered, and the chosen theme stays pressable so it can be
    turned off.
    """

    @pytest.fixture
    def http(self, server_url, themed):
        with httpx.Client(base_url=server_url, timeout=30.0) as client:
            yield client

    def test_unfiltered_each_theme_counts_its_members(self, http, themed):
        payload = http.get("/api/works").raise_for_status().json()

        assert _themes(payload) == {
            "Nothing yet": (0, False, True),
            "Realists": (1, False, False),
            "Twentieth": (2, False, False),
        }
        assert [option["name"] for option in payload["themes"]] == ["Nothing yet", "Realists", "Twentieth"]

    def test_a_facet_narrows_each_themes_count_and_disables_the_one_it_empties(self, http, themed):
        """Surrealism leaves *Twentieth* one of its two members and *Realists* none."""
        payload = http.get("/api/works", params={"movement": "Surrealism"}).raise_for_status().json()

        assert _themes(payload) == {
            "Nothing yet": (0, False, True),
            "Realists": (0, False, True),
            "Twentieth": (1, False, False),
        }

    def test_text_narrows_the_counts_too(self, http, themed):
        payload = http.get("/api/works", params={"q": "nighthawks"}).raise_for_status().json()

        assert _themes(payload)["Realists"] == (1, False, False)
        assert _themes(payload)["Twentieth"] == (0, False, True)

    def test_the_chosen_theme_is_counted_without_itself_and_never_disabled(self, http, themed):
        """Chosen, and empty under the facet: the option is the only way to turn it off."""
        realists = next(option for option in http.get("/api/works").json()["themes"] if option["name"] == "Realists")

        chosen = {"theme": realists["theme_id"], "movement": "Surrealism"}
        payload = http.get("/api/works", params=chosen).raise_for_status().json()

        assert payload["total"] == 0
        assert _themes(payload)["Realists"] == (0, True, False)
        # The other themes are counted against the facet, not against the chosen
        # theme: choosing *Twentieth* next would select one work, not none.
        assert _themes(payload)["Twentieth"] == (1, False, False)

    def test_a_theme_keeps_the_sort_it_is_given(self, http, themed):
        """Sort orders the theme's slice and selects nothing; title and newest disagree here."""
        theme_id, _ = themed

        by_title = http.get("/api/works", params={"theme": theme_id}).raise_for_status().json()
        newest = http.get("/api/works", params={"theme": theme_id, "sort": "newest"}).raise_for_status().json()

        assert [work["title"] for work in by_title["works"]] == ["I Saw the Figure 5 in Gold", "The Persistence of Memory"]
        assert [work["title"] for work in newest["works"]] == ["The Persistence of Memory", "I Saw the Figure 5 in Gold"]


class TestTheToolSurface:
    """`art_catalogue(action='list')` takes the same theme and answers with the same slice."""

    @staticmethod
    async def call(server_url: str, **arguments) -> tuple[dict, bool]:
        async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("art_catalogue", arguments)
        return json.loads(result.content[0].text), bool(result.isError)

    async def test_a_theme_and_a_facet_mean_both(self, server_url, themed):
        theme_id, _ = themed

        payload, failed = await self.call(server_url, action="list", theme=theme_id, movement=["Realism"])

        assert not failed
        assert [work["title"] for work in payload["artworks"]] == ["I Saw the Figure 5 in Gold"]
        assert _movement_counts(payload["facets"], options="values") == {"Realism": 1, "Surrealism": 1}
        # The theme options travel with it, counted the way the browser's are.
        assert _themes(payload)["Twentieth"] == (1, True, False)
        assert _themes(payload)["Realists"] == (1, False, False)

    async def test_an_unknown_theme_is_refused_by_name(self, server_url, themed):
        payload, failed = await self.call(server_url, action="list", theme="no-such-theme")

        assert failed
        assert "no-such-theme" in payload["error"]
