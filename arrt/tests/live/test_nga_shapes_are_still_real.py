"""The NGA findings the image source leans on, as a test rather than as prose.

`nga-api-findings.md` records what the source was built against: the open data's
two files on GitHub's raw host, gzipped with an ETag that a conditional request
answers with 304; their columns and rows; the IIIF service stating the original's
size and serving its tiles at full resolution; the capped service stating the
size the plugin computes; and Wikidata's items recording NGA's page through
P4683. NGA can change any of them.

**Deselected by default.** Free, but the first test downloads both files (about
43 MB on the wire) into a temporary directory. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_nga_shapes_are_still_real.py
"""

import httpx
import pytest

from arrt.library.discovery.images import ImageQuery
from arrt.library.registry import ItemId
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import FetchLocator
from arrt.library.sources.nga import REFRESH_SECONDS, NgaCatalogue, NgaFinder, NgaReader
from arrt.persistence.records import RightsStatus

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: Murillo's *Two Women at a Window*: open access, 17385 x 20855 (2026-10-06).
MURILLO_ITEM = ItemId("Q3757652")
MURILLO_PAGE = "https://www.nga.gov/collection/art-object-page.1185.html"
#: Escher's *Castrovalva* (corpus row 15): capped at 900, and US public domain since 2026.
CASTROVALVA = 54101


class Recording(httpx.BaseTransport):
    """The real network, with each answer's status noted."""

    def __init__(self) -> None:
        self._inner = httpx.HTTPTransport()
        self.statuses: list[int] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._inner.handle_request(request)
        self.statuses.append(response.status_code)
        return response


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(scope="module")
def copy(tmp_path_factory):
    """One download of the open data, shared by the module's tests."""
    directory = tmp_path_factory.mktemp("nga")
    network = Recording()
    clock = Clock()
    catalogue = NgaCatalogue(
        directory=directory, user_agent=USER_AGENT, transport=network, clock=clock, schedule=lambda delay, call: None
    )
    catalogue.entry(1185)
    return directory, network, clock, catalogue


def info(service: str) -> dict:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{service}/info.json", headers={"User-Agent": USER_AGENT})
    assert response.status_code == httpx.codes.OK, f"{service} answered HTTP {response.status_code}"
    return response.json()


def test_the_open_data_still_arrives_gzipped_and_answers_a_conditional_request_with_304(copy):
    directory, network, clock, _ = copy
    assert network.statuses == [200, 200]
    assert (directory / "published_images.csv.gz").stat().st_size > 10_000_000

    clock.now += REFRESH_SECONDS
    restarted = NgaCatalogue(
        directory=directory, user_agent=USER_AGENT, transport=network, clock=clock, schedule=lambda delay, call: None
    )
    restarted.entry(1185)

    again = network.statuses[2:]
    if again == [200, 200]:
        pytest.skip("NGA published both files between the two requests, as it does once a day")
    assert 304 in again
    assert set(again) <= {200, 304}


def test_an_open_image_is_still_stated_and_served_at_the_originals_size(copy):
    _, _, _, catalogue = copy
    entry = catalogue.entry(1185)

    assert (entry.title, entry.attribution, entry.open_access, entry.maxpixels) == (
        "Two Women at a Window",
        "Bartolomé Esteban Murillo",
        True,
        None,
    )
    stated = info(entry.service)
    assert (stated["width"], stated["height"]) == (entry.width, entry.height)
    with httpx.Client(timeout=30.0) as client:
        corner = client.get(
            f"{entry.service}/{entry.width - 256},{entry.height - 256},256,256/256,/0/default.jpg",
            headers={"User-Agent": USER_AGENT},
        )
    assert corner.status_code == httpx.codes.OK, "the original's tiles are served to its far corner"


def test_a_capped_image_still_states_the_size_the_plugin_computes(copy):
    _, _, _, catalogue = copy
    entry = catalogue.entry(CASTROVALVA)

    assert (entry.maxpixels, entry.open_access) == (900, False)
    stated = info(entry.service)
    assert (stated["width"], stated["height"]) == entry.served_size


def test_wikidata_still_records_ngas_page_and_the_image_is_reported_under_it(copy):
    _, _, _, catalogue = copy
    registry = WikidataRegistry(user_agent=USER_AGENT)
    try:
        finder = NgaFinder(catalogue=catalogue, registry=registry, user_agent=USER_AGENT)
        (image,) = finder.find_images(ImageQuery(title="Two Women at a Window", qid=MURILLO_ITEM))
    finally:
        registry.close()

    assert image.url == MURILLO_PAGE
    assert image.artist == "Bartolomé Esteban Murillo"
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert NgaReader(catalogue=catalogue).read(MURILLO_PAGE) == FetchLocator.tiles(
        "https://api.nga.gov/iiif/099e8599-3242-46f4-bf5d-1a2e6032eb13/info.json"
    )
