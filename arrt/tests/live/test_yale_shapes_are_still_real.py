"""The Yale findings the image source leans on, as a test rather than as prose.

`linked-art-findings.md` records what the source was built against: a manifest
built from the number in a museum page, its title, maker, canvases and each
canvas's rights; the 404 for an object with no image; the image service serving
the original whole at the size the canvas states, and in-copyright works at 480
pixels; and Wikidata's YUAG ID naming the page. Yale can change any of them.

**Deselected by default** and free. Each image's head is streamed and the
connection closed once its frame is read, so a run costs a handful of requests,
not the originals. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_yale_shapes_are_still_real.py
"""

import httpx
import pytest

from arrt.library.discovery.images import ImageQuery
from arrt.library.registry import ItemId
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import LocatorKind
from arrt.library.sources.met import jpeg_size
from arrt.library.sources.yale import YaleFinder, YaleReader
from arrt.persistence.records import RightsStatus

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: *The Night Café*: public domain, 7408 x 5848 (2026-10-07).
NIGHT_CAFE_ITEM = ItemId("Q674846")
NIGHT_CAFE_PAGE = "https://artgallery.yale.edu/collections/objects/12507"
#: Rothko's *Untitled* (1958): in copyright, 376 x 480 (2026-10-07).
ROTHKO_PAGE = "https://artgallery.yale.edu/collections/objects/28401"
#: Turner's *Dort*, at YCBA: its first canvas 14484 x 9741 (2026-10-07).
DORT_PAGE = "https://collections.britishart.yale.edu/catalog/tms:34"
#: A YUAG object with no image: its manifest answers 404 (2026-10-07).
NO_IMAGE_PAGE = "https://artgallery.yale.edu/collections/objects/90363"

#: Far beyond the frame, which the image server writes near the start.
_HEAD_BYTES = 256 * 1024


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


@pytest.mark.parametrize(
    ("page", "size"),
    [(NIGHT_CAFE_PAGE, (7408, 5848)), (ROTHKO_PAGE, (376, 480)), (DORT_PAGE, (14484, 9741))],
    ids=["public-domain", "in-copyright-480", "ycba-14484"],
)
def test_the_reader_still_reads_a_page_to_one_request_serving_the_original_at_the_canvas_size(page, size):
    locator = YaleReader(user_agent=USER_AGENT).read(page)

    assert locator.kind is LocatorKind.DIRECT
    assert locator.url.startswith("https://images.collections.yale.edu/iiif/2/")
    assert head_size(locator.url) == size


def test_an_object_with_no_image_still_has_no_manifest():
    assert YaleReader(user_agent=USER_AGENT).read(NO_IMAGE_PAGE).kind is LocatorKind.NONE


def test_wikidata_still_names_the_yuag_page_and_the_manifest_still_says_what_the_finder_reads():
    registry = WikidataRegistry(user_agent=USER_AGENT)
    try:
        assert NIGHT_CAFE_PAGE in registry.pages_about(NIGHT_CAFE_ITEM)
        (image,) = YaleFinder(user_agent=USER_AGENT, registry=registry).find_images(
            ImageQuery(title="The Night Café", qid=NIGHT_CAFE_ITEM)
        )
    finally:
        registry.close()

    assert image.url == NIGHT_CAFE_PAGE
    assert (image.title, image.artist) == ("Le café de nuit (The Night Café)", "Vincent van Gogh")
    assert (image.estimated_width, image.estimated_height) == (7408, 5848)
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
