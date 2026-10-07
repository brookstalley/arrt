"""The Met findings the image source leans on, as a test rather than as prose.

`met-api-findings.md` records what the source was built against: the paginated
search, the object record's image fields, the empty image of an in-copyright
object, the 404 for an unknown id, the ranged head an original's size is read
from, and Wikidata's item naming the Met's page. The Met can change any of them,
and did once (`/v1/search`, retired 2026-10-01).

**Deselected by default** and free. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_met_shapes_are_still_real.py
"""

import pytest

from arrt.library.discovery.images import ImageQuery
from arrt.library.registry import ItemId
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import LocatorKind
from arrt.library.sources.met import MetFinder, MetReader, object_url

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: *Wheat Field with Cypresses*: public domain, a 4000 x 3184 original (2026-10-06).
WHEAT_FIELD = 436535
WHEAT_FIELD_ITEM = ItemId("Q18689458")
#: Ellsworth Kelly's *Black White*: in copyright, so no image in the API.
KELLY = 915129


@pytest.fixture(scope="module")
def finder():
    return MetFinder(user_agent=USER_AGENT)


def test_a_search_still_finds_by_title_narrowed_to_the_artist(finder):
    found = finder.find_images(ImageQuery(title="Wheat Field with Cypresses", artist="Vincent van Gogh"))

    (image,) = [image for image in found if image.url == object_url(WHEAT_FIELD)]
    assert image.artist == "Vincent van Gogh"
    assert image.estimated_width is not None, "the original's head no longer carries its size within the bound"
    assert image.estimated_width * image.estimated_height > 1_000_000


def test_wikidata_still_names_the_met_object_for_the_item():
    registry = WikidataRegistry(user_agent=USER_AGENT)
    try:
        found = MetFinder(user_agent=USER_AGENT, registry=registry).find_images(
            ImageQuery(title="Wheat Field with Cypresses", qid=WHEAT_FIELD_ITEM)
        )
    finally:
        registry.close()

    assert [image.url for image in found] == [object_url(WHEAT_FIELD)]


def test_the_reader_still_reads_an_object_to_its_original_and_an_in_copyright_one_to_none():
    reader = MetReader(user_agent=USER_AGENT)

    original = reader.read(object_url(WHEAT_FIELD))
    assert original.kind is LocatorKind.DIRECT
    assert original.url.startswith("https://images.metmuseum.org/")
    assert reader.read(object_url(KELLY)).kind is LocatorKind.NONE
    assert reader.read(object_url(999_999_999)).kind is LocatorKind.NONE
