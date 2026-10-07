"""The Rijksmuseum findings the image source leans on, as a test rather than as prose.

`linked-art-findings.md` § The Rijksmuseum records what the source was built
against: Wikidata's Rijksmuseum ID naming the record; the road from the object
through its VisualItem and DigitalObject to an image service; the VisualItem's
rights; the three ways a maker is stated; the search matching the museum's own
spelling of a maker, accents included or not; and the image service declaring
17.55 MP while holding originals far larger, in copyright included. The museum
can change any of them.

**Deselected by default** and free. Each image's head is streamed and the
connection closed once its frame is read, so a run costs a few dozen requests,
not the originals. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_rijksmuseum_shapes_are_still_real.py
"""

import httpx
import pytest

from arrt.library.discovery.images import ImageQuery
from arrt.library.registry import ItemId, WorkPage
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import FetchLocator, LocatorKind
from arrt.library.sources.met import jpeg_size
from arrt.library.sources.rijksmuseum import RijksmuseumFinder, RijksmuseumReader
from arrt.persistence.records import AcquisitionMethod, RightsStatus

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

ID = "https://id.rijksmuseum.nl/"
#: *The Milkmaid*: public domain, 4649 x 5177, over the declared area (2026-10-07).
MILKMAID_ITEM = ItemId("Q167605")
MILKMAID = f"{ID}200108369"
#: Van der Elsken's *Man en vrouw bovenin de Tokyo Tower*: in copyright, not downloadable, 3200 x 3327 (2026-10-07).
ELSKEN = f"{ID}200100873"
#: Appel's *Compositie*, signed: in copyright (2026-10-07).
APPEL = f"{ID}200496110"
#: *Samson and Delilah*, attributed to Rembrandt (2026-10-07).
SAMSON = f"{ID}200109435"
#: Israels' *Two Young Women in the Snow* (2026-10-07).
ISRAELS = f"{ID}200109400"
#: A Rembrandt drawing with no image (2026-10-07).
NO_IMAGE = f"{ID}200556187"
#: A well-shaped number the museum does not know: it answered 400 (2026-10-07).
UNKNOWN = f"{ID}299999999"

#: Far beyond the frame, which the image server writes near the start.
_HEAD_BYTES = 256 * 1024


class _Pages:
    """A registry that names one page for every item, for objects Wikidata does not link."""

    def __init__(self, page: str) -> None:
        self._page = page

    def pages_about(self, qid: ItemId) -> list[WorkPage]:
        return [WorkPage(self._page)]


def head_size(url: str) -> tuple[int, int] | None:
    """The size in the JPEG header of `url`, read without fetching the rest."""
    head = bytearray()
    with (
        httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client,
        client.stream("GET", url, headers={"User-Agent": USER_AGENT}) as response,
    ):
        assert response.status_code == httpx.codes.OK, f"{url} answered HTTP {response.status_code}"
        assert response.headers["content-type"] == "image/jpeg"
        for chunk in response.iter_bytes():
            head.extend(chunk)
            size = jpeg_size(bytes(head))
            if size is not None or len(head) >= _HEAD_BYTES:
                return size
    return jpeg_size(bytes(head))


def by_item(page: str) -> list:
    return list(
        RijksmuseumFinder(user_agent=USER_AGENT, registry=_Pages(page)).find_images(ImageQuery(title="x", qid=ItemId("Q1")))
    )


def test_an_in_copyright_original_within_the_area_is_still_one_request_served_whole():
    locator = RijksmuseumReader(user_agent=USER_AGENT).read(ELSKEN)

    assert locator.kind is LocatorKind.DIRECT
    assert locator.url.startswith("https://iiif.micr.io/")
    assert head_size(locator.url) == (3200, 3327)


def test_an_original_over_the_area_is_still_tiles_and_a_tile_is_still_served():
    locator = RijksmuseumReader(user_agent=USER_AGENT).read(MILKMAID)

    assert locator.kind is LocatorKind.TILES
    service = locator.url.removesuffix("/info.json")
    assert locator == FetchLocator.tiles(f"{service}/info.json")
    assert head_size(f"{service}/0,0,1024,1024/1024,/0/default.jpg") == (1024, 1024)


def test_an_object_with_no_image_and_an_unknown_number_still_hold_nothing():
    reader = RijksmuseumReader(user_agent=USER_AGENT)

    assert reader.read(NO_IMAGE).kind is LocatorKind.NONE
    assert reader.read(UNKNOWN).kind is LocatorKind.NONE


def test_wikidata_still_names_the_record_and_the_records_still_say_what_the_finder_reads():
    registry = WikidataRegistry(user_agent=USER_AGENT)
    try:
        assert MILKMAID in registry.pages_about(MILKMAID_ITEM)
        (image,) = RijksmuseumFinder(user_agent=USER_AGENT, registry=registry).find_images(
            ImageQuery(title="x", qid=MILKMAID_ITEM)
        )
    finally:
        registry.close()

    assert image.url == MILKMAID
    assert (image.title, image.artist) == ("The Milkmaid", "Johannes Vermeer")
    assert (image.estimated_width, image.estimated_height) == (4649, 5177)
    assert image.acquisition_method is AcquisitionMethod.DEZOOMIFY
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN


@pytest.mark.parametrize(
    ("page", "artist", "rights"),
    [
        (APPEL, "Karel Appel", RightsStatus.IN_COPYRIGHT),
        (SAMSON, "attributed to Rembrandt van Rijn", RightsStatus.PUBLIC_DOMAIN),
        (ELSKEN, "Ed van der Elsken", RightsStatus.IN_COPYRIGHT),
    ],
    ids=["signed-evidence-dropped", "attribution-kept", "inline"],
)
def test_the_maker_and_the_rights_are_still_stated_as_measured(page, artist, rights):
    (image,) = by_item(page)

    assert (image.artist, image.rights_status) == (artist, rights)


def test_the_search_still_spells_israels_without_accents_and_the_plugin_still_finds_him_by_asking_twice():
    found = RijksmuseumFinder(user_agent=USER_AGENT, registry=None).find_images(
        ImageQuery(title="Two Young Women in the Snow", artist="Isaac Israëls")
    )

    assert [(image.url, image.title, image.artist) for image in found] == [
        (ISRAELS, "Two Young Women in the Snow", "Isaac Israels")
    ]
