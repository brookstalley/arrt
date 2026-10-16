"""The Getty findings the image source leans on, as a test rather than as prose.

`linked-art-findings.md` records what the source was built against: the SPARQL
endpoint mapping a page's slug to its Linked Art record, and a maker's name and a
title's words to objects; the record's titles, maker and manifest; the manifest's
first canvas and per-object `rights`; the image service serving the original whole,
in-copyright works included; and Wikidata's Getty ID naming the page. The Getty can
change any of them.

**Deselected by default** and free. Each image's head is streamed and the
connection closed once its frame is read, so a run costs a handful of requests,
not the originals. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_getty_shapes_are_still_real.py
"""

import httpx
import pytest

from arrt.library.discovery.images import ImageQuery
from arrt.library.registry import ItemId
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import LocatorKind
from arrt.library.sources.getty import GettyFinder, GettyReader
from arrt.library.sources.met import jpeg_size
from arrt.persistence.records import RightsStatus

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: *Irises*: public domain, 9021 x 7122, three canvases (2026-10-07).
IRISES_ITEM = ItemId("Q2282256")
IRISES_PAGE = "https://www.getty.edu/art/collection/object/103JNH"
#: Brockhurst's *Portrait of J. Paul Getty*: in copyright, served whole at 3347 x 4020 (2026-10-07).
BROCKHURST_PAGE = "https://www.getty.edu/art/collection/object/103R9G"
#: Arbus's *Nudist couple on a bench*: in copyright, kept at 573 x 600 (2026-10-07).
ARBUS_PAGE = "https://www.getty.edu/art/collection/object/10P1MS"
#: An armlet: a record with no manifest (2026-10-07).
NO_IMAGE_PAGE = "https://www.getty.edu/art/collection/object/107SAK"

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
    [(IRISES_PAGE, (9021, 7122)), (BROCKHURST_PAGE, (3347, 4020)), (ARBUS_PAGE, (573, 600))],
    ids=["public-domain", "in-copyright-whole", "in-copyright-600"],
)
def test_the_reader_still_reads_a_page_to_one_request_serving_the_original_at_the_canvas_size(page, size):
    locator = GettyReader(user_agent=USER_AGENT).read(page)

    assert locator.kind is LocatorKind.DIRECT
    assert locator.url.startswith("https://media.getty.edu/iiif/image/")
    assert head_size(locator.url) == size


def test_an_object_with_no_image_still_has_no_manifest():
    assert GettyReader(user_agent=USER_AGENT).read(NO_IMAGE_PAGE).kind is LocatorKind.NONE


def test_wikidata_still_names_the_getty_page_and_the_record_still_says_what_the_finder_reads():
    registry = WikidataRegistry(user_agent=USER_AGENT)
    try:
        assert IRISES_PAGE in registry.pages_about(IRISES_ITEM)
        (image,) = GettyFinder(user_agent=USER_AGENT, registry=registry).find_images(ImageQuery(title="Irises", qid=IRISES_ITEM))
    finally:
        registry.close()

    assert image.url == IRISES_PAGE
    assert (image.title, image.artist) == ("Irises", "Vincent van Gogh")
    assert (image.estimated_width, image.estimated_height) == (9021, 7122)
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN


def test_the_endpoint_still_finds_a_work_by_its_makers_name_and_its_titles_words():
    found = GettyFinder(user_agent=USER_AGENT, registry=None).find_images(ImageQuery(title="The City", artist="Fédèle Azari"))

    assert [(image.url, image.title, image.artist) for image in found] == [
        ("https://www.getty.edu/art/collection/object/104430", "The City", "Fédèle Azari")
    ]
    assert found[0].rights_status is RightsStatus.PUBLIC_DOMAIN


def test_the_endpoint_still_finds_a_work_whose_maker_is_one_of_several_parts():
    """*Rocky Bear, Sioux* records Muhr and Rinehart each in a part of its production."""
    found = GettyFinder(user_agent=USER_AGENT, registry=None).find_images(ImageQuery(title="Rocky Bear", artist="Adolph F. Muhr"))

    assert ("https://www.getty.edu/art/collection/object/10435K", "Adolph F. Muhr") in [(i.url, i.artist) for i in found]
