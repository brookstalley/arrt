"""The navigart findings the image source leans on, as a test rather than as prose.

`navigart-api-findings.md` records what the source was built against: the
artwork record and its fields, navigart's own 404 for an artwork a vault does
not have, the image served at the size the record states and never over 1,000
px, the vault that differs from its IDs' prefix, and Wikidata's items recording
navigart's pages in a fragment and in a path. navigart can change any of them.

**Deselected by default** and free: a handful of requests, each image under
half a megabyte. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_navigart_shapes_are_still_real.py
"""

import httpx
import pytest

from arrt.library.discovery.images import ImageQuery
from arrt.library.registry import ItemId
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import LocatorKind
from arrt.library.sources.met import jpeg_size
from arrt.library.sources.navigart import NavigartFinder, NavigartReader
from arrt.persistence.records import RightsStatus

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: Corpus row 14, Taeuber-Arp's *Échelonnement* at Grenoble: public domain, 777 x 1000 (2026-10-06).
ECHELONNEMENT_ITEM = ItemId("Q136030970")
ECHELONNEMENT_PAGE = "https://www.navigart.fr/grenoble/#/artwork/60000000002521"
#: Corpus row 6, Sonia Delaunay's *Rythme couleur n°1076* at the FNAC: in copyright, 1000 x 979.
RYTHME_ITEM = ItemId("Q116464677")
RYTHME_PAGE = "https://www.navigart.fr/fnac/artwork/140000000027457"
#: Matisse's *Fenêtre à Tahiti* at Le Cateau, whose vault (701) is not its ID's prefix (7).
TAHITI_PAGE = "https://www.navigart.fr/matisse_lecateau/artwork/70000000000186"


def served_size(url: str) -> tuple[int, int] | None:
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
    assert response.status_code == httpx.codes.OK, f"{url} answered HTTP {response.status_code}"
    assert response.headers["content-type"] == "image/jpeg"
    return jpeg_size(response.content)


def test_wikidata_still_records_the_pages_and_each_image_is_reported_under_its_page_at_its_stated_size():
    registry = WikidataRegistry(user_agent=USER_AGENT)
    try:
        finder = NavigartFinder(user_agent=USER_AGENT, registry=registry)
        (echelonnement,) = finder.find_images(ImageQuery(title="Échelonnement", qid=ECHELONNEMENT_ITEM))
        (rythme,) = finder.find_images(ImageQuery(title="Rythme couleur n°1076", qid=RYTHME_ITEM))
    finally:
        registry.close()

    assert (echelonnement.url, echelonnement.artist) == (ECHELONNEMENT_PAGE, "Sophie Taeuber-Arp")
    assert (echelonnement.estimated_width, echelonnement.estimated_height) == (777, 1000)
    assert echelonnement.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert (rythme.url, rythme.artist) == (RYTHME_PAGE, "Sonia Delaunay")
    assert (rythme.estimated_width, rythme.estimated_height) == (1000, 979)
    assert rythme.rights_status is RightsStatus.IN_COPYRIGHT


@pytest.mark.parametrize(
    ("page", "size"), [(ECHELONNEMENT_PAGE, (777, 1000)), (RYTHME_PAGE, (1000, 979)), (TAHITI_PAGE, (775, 1000))]
)
def test_the_reader_still_reads_a_page_to_the_image_at_the_size_the_record_states(page, size):
    locator = NavigartReader(user_agent=USER_AGENT).read(page)

    assert locator.kind is LocatorKind.DIRECT
    assert served_size(locator.url) == size


def test_no_size_over_a_thousand_is_served():
    with httpx.Client(timeout=30.0) as client:
        response = client.get("https://images.navigart.fr/2000/5D/69/5D69677.jpg", headers={"User-Agent": USER_AGENT})

    assert response.status_code != httpx.codes.OK


def test_an_artwork_a_vault_does_not_have_is_still_navigarts_own_404():
    assert NavigartReader(user_agent=USER_AGENT).read("https://www.navigart.fr/grenoble/#/artwork/60000000999999").kind is (
        LocatorKind.NONE
    )
