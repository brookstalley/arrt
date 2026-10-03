"""The Commons findings the image source leans on, as a test rather than as prose.

`wikidata-findings.md` § Commons records what the source was built against: the
widest rendering is 3840, a fixed-width request reports the size it serves, a
file too large to fetch whole has a rendering, and Wikidata's item still names
that file. Commons can change any of these, and the source would then report a
size that is not the size that arrives.

**Deselected by default** and free. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_commons_shapes_are_still_real.py
"""

import httpx
import pytest

from arrt.library.discovery.images import ImageQuery
from arrt.library.registry import ItemId
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources.commons import DOWNLOAD_WIDTH, CommonsImageSearch

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: The Starry Night, read from the 2026-10-02 probe: its original is 44,567 px
#: wide and 696,195,208 bytes, past the acquisition ceiling.
STARRY_NIGHT = ItemId("Q45585")


@pytest.fixture(scope="module")
def source():
    registry = WikidataRegistry(user_agent=USER_AGENT)
    yield CommonsImageSearch(registry=registry, user_agent=USER_AGENT)
    registry.close()


def test_a_file_too_large_to_fetch_is_offered_as_a_rendering_that_is_served(source):
    (image,) = source.find_images(ImageQuery(title="The Starry Night", qid=STARRY_NIGHT))

    assert image.estimated_width == DOWNLOAD_WIDTH
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=False) as http:
        response = http.get(image.url, headers={"Range": "bytes=0-0"})
    assert response.status_code in (200, 206), f"the rendering the source offers is not served: {response.status_code}"


def test_a_rendering_wider_than_the_widest_is_still_refused():
    """If Commons starts serving wider renderings, `DOWNLOAD_WIDTH` can rise."""
    url = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg/"
        "5000px-Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg"
    )
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as http:
        assert http.get(url, headers={"Range": "bytes=0-0"}).status_code == 400
