"""The SMK findings the image source leans on, as a test rather than as prose.

`smk-api-findings.md` records what the source was built against: the object
record and its fields, the empty answer for an unknown number, the search by
title and artist, SMK's own rights statement for a work in copyright, the
original served at the size the record states for a public-domain and an
in-copyright work alike, and Wikidata's item recording SMK's page with a
fragment. SMK can change any of them.

**Deselected by default** and free. Each original's head is streamed and the
connection closed once its frame is read, so a run costs a handful of requests,
not the originals (28 MB and 10 MB). Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_smk_shapes_are_still_real.py
"""

import httpx
import pytest

from arrt.library.discovery.images import ImageQuery
from arrt.library.registry import ItemId
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import LocatorKind
from arrt.library.sources.met import jpeg_size
from arrt.library.sources.smk import SmkFinder, SmkReader
from arrt.persistence.records import RightsStatus

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: Cornelis van Haarlem's *The Fall of the Titans*: public domain, 7174 x 5536 (2026-10-06).
FALL_OF_THE_TITANS = ("https://open.smk.dk/artwork/image/KMS1", (7174, 5536))
#: Al Masson's *Salon*: in copyright, 6296 x 4370 (2026-10-06). Its number holds a slash.
SALON = ("https://open.smk.dk/artwork/image/KKS2020-3/16", (6296, 4370))
#: Hammershøi's *Tree Trunks*, whose item records SMK's page with a fragment (P973).
TREE_TRUNKS_ITEM = ItemId("Q20268298")
TREE_TRUNKS_PAGE = "https://collection.smk.dk/#/en/detail/KMS8010"

#: Far beyond the frame of either original, which IIPImage writes near the start.
_HEAD_BYTES = 256 * 1024


def head_size(url: str) -> tuple[int, int] | None:
    """The size in the JPEG header of `url`, read without fetching the rest."""
    head = bytearray()
    with (
        httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client,
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


@pytest.mark.parametrize(("page", "size"), [FALL_OF_THE_TITANS, SALON], ids=["public-domain", "in-copyright"])
def test_the_reader_still_reads_a_page_to_the_original_at_the_size_the_record_states(page, size):
    locator = SmkReader(user_agent=USER_AGENT).read(page)

    assert locator.kind is LocatorKind.DIRECT
    assert locator.url.startswith("https://api.smk.dk/api/v1/download/")
    assert head_size(locator.url) == size


def test_a_search_still_finds_an_in_copyright_work_by_title_and_artist_and_says_so():
    found = SmkFinder(user_agent=USER_AGENT).find_images(ImageQuery(title="Salon", artist="Al Masson"))

    (image,) = [image for image in found if image.url == SALON[0]]
    assert (image.title, image.artist) == ("Salon", "Al Masson")
    assert (image.estimated_width, image.estimated_height) == SALON[1]
    assert image.rights_status is RightsStatus.IN_COPYRIGHT


def test_wikidata_still_records_the_fragment_page_and_the_image_is_reported_under_it():
    registry = WikidataRegistry(user_agent=USER_AGENT)
    try:
        found = SmkFinder(user_agent=USER_AGENT, registry=registry).find_images(
            ImageQuery(title="Tree Trunks", qid=TREE_TRUNKS_ITEM)
        )
    finally:
        registry.close()

    (image,) = found
    assert image.url == TREE_TRUNKS_PAGE
    assert image.artist == "Vilhelm Hammershøi"
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN


def test_an_object_number_smk_does_not_have_is_still_an_empty_answer():
    assert SmkReader(user_agent=USER_AGENT).read("https://open.smk.dk/artwork/image/KMS99999999").kind is LocatorKind.NONE
