"""Commons as an image source, driven through the real client against recorded answers.

Every file under `tests/fixtures/commons/` is an answer Commons gave on
2026-10-02 (`wikidata-findings.md` § Commons), so a parser written from its own
assumptions cannot pass here.
"""

import json
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fakes import FakeFinder, FakeRegistry, an_image

from arrt.library.discovery.images import ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry import CommonsFile, ItemId, RegistryCreator, RegistryText, RegistryWork
from arrt.library.services.display_fit import ArtworkBox
from arrt.library.sources.commons import DOWNLOAD_WIDTH, PREVIEW_WIDTH, CommonsFinder
from arrt.persistence.records import AcquisitionMethod, RightsStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "commons"

STARRY = "Van Gogh - Starry Night - Google Art Project.jpg"
DELAUNAY = (
    "Robert Delaunay, 1912, Les Fenêtres simultanée sur la ville (Simultaneous Windows on the City), "
    "40 x 46 cm, Kunsthalle Hamburg.jpg"
)
LICENSED = "020B-020A Macau Light Rapid Transit Taipa Line compartment 06-06-2024.jpg"
SVG = "Commons-logo.svg"

#: Which recorded answer stands for which file and rendering width.
ANSWERS = {
    (STARRY, DOWNLOAD_WIDTH): "starry_night_3840.json",
    (STARRY, PREVIEW_WIDTH): "starry_night_960.json",
    (DELAUNAY, DOWNLOAD_WIDTH): "delaunay_3840.json",
    (LICENSED, DOWNLOAD_WIDTH): "cc_by_sa_3840.json",
    (SVG, DOWNLOAD_WIDTH): "svg_3840.json",
}


def recorded(request: httpx.Request) -> httpx.Response:
    name = request.url.params["titles"].removeprefix("File:")
    width = int(request.url.params["iiurlwidth"])
    fixture = ANSWERS.get((name, width), "missing.json")
    return httpx.Response(200, json=json.loads((FIXTURES / fixture).read_text()))


def a_work(qid: str, file: str | None, *, title: str = "The Starry Night", creator: str = "Vincent van Gogh"):
    return RegistryWork(
        qid=ItemId(qid),
        title=RegistryText(title),
        sitelinks=100,
        image=None if file is None else CommonsFile(f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(file)}"),
        creators=(RegistryCreator(qid=ItemId("Q5582"), name=RegistryText(creator)),),
    )


def a_source(registry: FakeRegistry, handler=recorded, *, asked: list | None = None) -> CommonsFinder:
    def recording(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(request)
        return handler(request)

    return CommonsFinder(
        registry=registry,
        user_agent="arrt-tests/0",
        client=httpx.Client(transport=httpx.MockTransport(recording), follow_redirects=False),
    )


def find(registry: FakeRegistry, qid: str = "Q45585", **kwargs):
    return a_source(registry, **kwargs).find_images(ImageQuery(title="The Starry Night", qid=ItemId(qid)))


def test_a_file_too_large_to_fetch_whole_is_offered_as_its_widest_rendering():
    (image,) = find(FakeRegistry(works={"Q45585": a_work("Q45585", STARRY)}))

    assert image.provider == "commons"
    assert image.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    assert image.url == (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ea/"
        "Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg/3840px-Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg"
    )
    assert (image.estimated_width, image.estimated_height) == (3840, 3041)
    assert image.preview_url.endswith("/960px-Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg")
    assert (image.title, image.artist) == ("The Starry Night", "Vincent van Gogh")
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN


def test_a_file_no_wider_than_a_rendering_is_offered_whole_at_its_own_size():
    """Commons reports a 3840 rendering of a 1,229 px file, and serves the original for it."""
    (image,) = find(FakeRegistry(works={"Q19861807": a_work("Q19861807", DELAUNAY)}), qid="Q19861807")

    assert image.url.startswith("https://upload.wikimedia.org/wikipedia/commons/")
    assert "?" not in image.url, "Commons' tracking parameters are not part of the file's address"
    assert (image.estimated_width, image.estimated_height) == (1229, 1335)


def test_a_licensed_file_is_recorded_as_in_copyright():
    (image,) = find(FakeRegistry(works={"Q1": a_work("Q1", LICENSED)}), qid="Q1")

    assert image.rights_status is RightsStatus.IN_COPYRIGHT


def test_a_file_whose_size_commons_does_not_give_carries_no_size():
    def sizeless(request: httpx.Request) -> httpx.Response:
        answer = recorded(request).json()
        info = answer["query"]["pages"][0]["imageinfo"][0]
        del info["width"], info["height"]
        return httpx.Response(200, json=answer)

    (image,) = find(FakeRegistry(works={"Q45585": a_work("Q45585", STARRY)}), handler=sizeless)

    assert (image.estimated_width, image.estimated_height) == (None, None)


@pytest.mark.parametrize(
    "works",
    [
        pytest.param({}, id="an item the registry does not have"),
        pytest.param({"Q45585": a_work("Q45585", None)}, id="an item with no image"),
        pytest.param({"Q45585": a_work("Q45585", "No such file anywhere 7f3a.jpg")}, id="a file Commons does not have"),
        pytest.param({"Q45585": a_work("Q45585", SVG)}, id="a file that is not a raster image"),
    ],
)
def test_nothing_to_offer_is_an_empty_answer(works):
    assert find(FakeRegistry(works=works)) == ()


def test_a_query_without_an_item_is_one_commons_cannot_answer_and_asks_nobody():
    """Not "holds nothing": nothing was looked up, so the source says it cannot answer."""
    registry = FakeRegistry(works={"Q45585": a_work("Q45585", STARRY)})
    asked: list = []

    with pytest.raises(ImageQueryUnanswerable):
        a_source(registry, asked=asked).find_images(ImageQuery(title="The Starry Night"))
    assert (registry.works_asked, asked) == ([], [])


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(lambda request: httpx.Response(503, text="unwell"), id="a server error"),
        pytest.param(
            lambda request: httpx.Response(301, headers={"Location": "http://127.0.0.1/"}), id="a redirect, not followed"
        ),
        pytest.param(lambda request: httpx.Response(200, text="<html>"), id="an answer that is not JSON"),
        pytest.param(
            lambda request: httpx.Response(302, json=recorded(request).json(), headers={"Location": "https://elsewhere/"}),
            id="a redirect carrying an answer that parses",
        ),
    ],
)
def test_a_commons_that_cannot_be_asked_raises_rather_than_answering_empty(answer):
    with pytest.raises(ImageSearchFailure):
        find(FakeRegistry(works={"Q45585": a_work("Q45585", STARRY)}), handler=answer)


def test_a_registry_that_cannot_be_asked_raises_rather_than_answering_empty():
    with pytest.raises(ImageSearchFailure):
        find(FakeRegistry(failing=True))


def test_a_preview_is_read_against_its_ceiling():
    source = CommonsFinder(
        registry=FakeRegistry(),
        user_agent="arrt-tests/0",
        preview_max_bytes=10,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 11))),
    )

    assert source.fetch_preview("https://thumb.wikimedia.org/p.jpg") is None


def test_a_preview_at_the_ceiling_arrives_whole_from_several_chunks():
    body = [b"a" * 4, b"b" * 4, b"c" * 2]

    def chunked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_Chunks(body))

    source = CommonsFinder(
        registry=FakeRegistry(),
        user_agent="arrt-tests/0",
        preview_max_bytes=10,
        client=httpx.Client(transport=httpx.MockTransport(chunked)),
    )

    assert source.fetch_preview("https://thumb.wikimedia.org/p.jpg") == b"aaaabbbbcc"


def test_a_preview_whose_transport_fails_is_absent_rather_than_raised():
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset", request=request)

    assert a_source(FakeRegistry(), handler=broken).fetch_preview("https://thumb.wikimedia.org/p.jpg") is None


def test_a_preview_rendering_commons_cannot_describe_leaves_the_image_found():
    """Only the 960 px question fails; the image is still offered, without a preview."""

    def preview_fails(request: httpx.Request) -> httpx.Response:
        if request.url.params["iiurlwidth"] == str(PREVIEW_WIDTH):
            return httpx.Response(503, text="unwell")
        return recorded(request)

    (image,) = find(FakeRegistry(works={"Q45585": a_work("Q45585", STARRY)}), handler=preview_fails)

    assert (image.estimated_width, image.preview_url) == (DOWNLOAD_WIDTH, None)


def test_a_file_too_large_to_fetch_with_no_rendering_offered_raises():
    def no_rendering(request: httpx.Request) -> httpx.Response:
        answer = recorded(request).json()
        del answer["query"]["pages"][0]["imageinfo"][0]["thumburl"]
        return httpx.Response(200, json=answer)

    with pytest.raises(ImageSearchFailure, match="rendering"):
        find(FakeRegistry(works={"Q45585": a_work("Q45585", STARRY)}), handler=no_rendering)


class _Chunks(httpx.SyncByteStream):
    """A body served in the pieces given, so a reader that keeps only the last piece shows."""

    def __init__(self, pieces: list[bytes]) -> None:
        self._pieces = pieces

    def __iter__(self):
        yield from self._pieces


def test_a_preview_that_is_not_served_is_absent():
    source = a_source(FakeRegistry(), handler=lambda request: httpx.Response(404))

    assert source.fetch_preview("https://thumb.wikimedia.org/p.jpg") is None


# -- beside another source --------------------------------------------------------


#: The engine tests' 42" geometry.
BOX = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.9, floor_inches=12.0)


@pytest.mark.parametrize(
    ("museum_size", "winner"),
    [
        pytest.param((2000, 1584), "commons", id="a smaller museum scan loses to the Commons rendering"),
        pytest.param((8000, 6335), "artic", id="a larger museum scan beats the Commons rendering"),
    ],
)
def test_phase_two_picks_the_better_image_whichever_source_found_it(museum_size, winner):
    """Asked for one item, both sources answer, and resolution decides; neither source is preferred outright."""
    commons = a_source(FakeRegistry(works={"Q45585": a_work("Q45585", STARRY)}))
    museum = FakeFinder(
        holdings={
            "The Starry Night": (
                an_image("The Starry Night", artist="Vincent van Gogh", width=museum_size[0], height=museum_size[1]),
            )
        }
    )
    engine = PhaseTwoEngine(ImageSourcePool([commons, museum]), box=BOX)

    resolution = engine.resolve(ImageQuery(title="The Starry Night", artist="Vincent van Gogh", qid=ItemId("Q45585")))

    assert [entry.found.provider for entry in resolution.instances][0] == winner
    assert {entry.found.provider for entry in resolution.instances} == {"commons", "artic"}
