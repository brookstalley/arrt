"""The Met as an image source, driven through the real client against recorded answers.

Every file under `tests/fixtures/met/` is an answer the Met gave on 2026-10-06
(`met-api-findings.md`); `wheat_field_head.bin` is the first 40,820 bytes of
*Wheat Field with Cypresses*' original, which end just past its start-of-frame.
"""

import json
from pathlib import Path

import httpx
import pytest
from fakes import FakeRegistry

from arrt.library.discovery.images import ImageQuery, ImageSearchFailure
from arrt.library.registry import ItemId, WorkPage
from arrt.library.sources import LocatorKind, SourceContext, SourceParts
from arrt.library.sources.met import PLUGIN, MetFinder, MetReader, claims, jpeg_size, object_url
from arrt.persistence.records import AcquisitionMethod, RightsStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "met"
HEAD = (FIXTURES / "wheat_field_head.bin").read_bytes()

API = "https://collectionapi.metmuseum.org/public/collection"
WHEAT_FIELD, CYPRESSES, KOSON, KELLY = 436535, 437980, 53426, 915129

#: Object id → the recorded answer for it.
OBJECTS = {
    WHEAT_FIELD: "object_436535_wheat_field.json",
    CYPRESSES: "object_437980_cypresses.json",
    KOSON: "object_53426_koson_cypresses.json",
    KELLY: "object_915129_kelly_in_copyright.json",
}

#: (field, query) → the recorded search answer.
SEARCHES = {
    ("title", "Cypresses"): "search_title_cypresses.json",
    ("artistOrCulture", "Vincent van Gogh"): "search_artist_van_gogh.json",
}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def recorded(request: httpx.Request, *, objects=None, image=None) -> httpx.Response:
    """The Met as it answered: objects by id, searches by field and words, images by their head."""
    url = request.url
    if url.host == "images.metmuseum.org":
        if "json" in request.headers.get("Accept", ""):
            # Measured: the image host refuses a request that asks for JSON.
            return httpx.Response(406)
        return image(request) if image else httpx.Response(206, content=HEAD)
    if url.path.startswith("/public/collection/v1.1/search"):
        field = next(name for name in ("title", "artistOrCulture") if url.params.get(name) == "true")
        name = SEARCHES.get((field, url.params["q"]), "search_nothing.json")
        return httpx.Response(200, json=fixture(name))
    object_id = int(url.path.rsplit("/", 1)[1])
    answer = (objects or {}).get(object_id)
    if answer is not None:
        return answer
    if object_id in OBJECTS:
        return httpx.Response(200, json=fixture(OBJECTS[object_id]))
    # An object these tests did not record answers as an in-copyright one does.
    return httpx.Response(200, json={**fixture(OBJECTS[KELLY]), "objectID": object_id})


def a_client(asked: list | None = None, **kwargs) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(request)
        return recorded(request, **kwargs)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def a_finder(registry=None, asked=None, **kwargs) -> MetFinder:
    return MetFinder(user_agent="arrt-tests/0", registry=registry, client=a_client(asked, **kwargs))


def a_reader(**kwargs) -> MetReader:
    return MetReader(user_agent="arrt-tests/0", client=a_client(**kwargs))


WHEAT_ITEM = ItemId("Q18689458")
WEB_PAGE = WorkPage(f"https://www.metmuseum.org/art/collection/search/{WHEAT_FIELD}")


# -- finding by Wikidata item ------------------------------------------------------------


def test_a_work_whose_item_names_its_met_page_is_read_from_that_object_and_not_searched():
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={WHEAT_ITEM: [WorkPage("https://www.moma.org/collection/works/1"), WEB_PAGE]})

    (image,) = a_finder(registry, asked).find_images(ImageQuery(title="Wheat Field", qid=WHEAT_ITEM))

    assert image.url == object_url(WHEAT_FIELD)
    assert (image.provider, image.title, image.artist) == ("met", "Wheat Field with Cypresses", "Vincent van Gogh")
    assert (image.estimated_width, image.estimated_height) == (4000, 3184)
    assert image.preview_url == "https://images.metmuseum.org/CRDImages/ep/web-large/DP-42549-001.jpg"
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert image.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    assert not [r for r in asked if "search" in r.url.path]


def test_an_api_formatter_page_names_the_object_too():
    page = WorkPage(object_url(WHEAT_FIELD))

    (image,) = a_finder(FakeRegistry(pages={WHEAT_ITEM: [page]})).find_images(ImageQuery(title="x", qid=WHEAT_ITEM))

    assert image.url == object_url(WHEAT_FIELD)


def test_an_item_naming_no_met_object_falls_back_to_search():
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={WHEAT_ITEM: [WorkPage("https://www.moma.org/collection/works/1")]})

    found = a_finder(registry, asked).find_images(ImageQuery(title="Cypresses", artist="Vincent van Gogh", qid=WHEAT_ITEM))

    assert {image.url for image in found} == {object_url(CYPRESSES), object_url(WHEAT_FIELD)}
    assert [r for r in asked if "search" in r.url.path]


def test_a_registry_that_cannot_be_asked_is_a_search_that_could_not_be_asked():
    with pytest.raises(ImageSearchFailure, match="Wikidata could not be asked"):
        a_finder(FakeRegistry(failing=True)).find_images(ImageQuery(title="x", qid=WHEAT_ITEM))


# -- finding by search -------------------------------------------------------------------


def test_a_title_search_is_narrowed_to_the_artists_objects():
    """Ikeda Koson's public-domain *Cypresses* matches the title and is left out by the artist."""
    found = a_finder().find_images(ImageQuery(title="Cypresses", artist="Vincent van Gogh"))

    assert [image.url for image in found] == [object_url(CYPRESSES), object_url(WHEAT_FIELD)]
    assert {image.artist for image in found} == {"Vincent van Gogh"}


def test_an_artist_the_met_does_not_know_leaves_the_titles_own_results():
    """Otherwise a name spelt another way would read as the Met holding nothing."""
    found = a_finder().find_images(ImageQuery(title="Cypresses", artist="Vincent Willem van Gogh (painter)"))

    assert object_url(KOSON) in {image.url for image in found}
    assert object_url(CYPRESSES) in {image.url for image in found}


def test_no_artist_searches_by_title_alone_and_reads_at_most_ten_objects():
    asked: list[httpx.Request] = []
    titled = {"total": 30, "objectIDs": list(range(1, 31))}

    def search(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=titled)

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return search(request) if "search" in request.url.path else recorded(request)

    finder = MetFinder(user_agent="t", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert finder.find_images(ImageQuery(title="Untitled")) == []
    assert len([r for r in asked if "/objects/" in r.url.path]) == 10


def test_a_search_that_matches_nothing_finds_nothing():
    assert a_finder().find_images(ImageQuery(title="zzqx", artist="Vincent van Gogh")) == []


def test_a_search_answer_in_another_shape_could_not_be_asked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total": 3, "objectIDs": "1,2,3"})

    finder = MetFinder(user_agent="t", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ImageSearchFailure, match="shape"):
        finder.find_images(ImageQuery(title="Cypresses"))


def test_a_redirect_from_the_api_is_not_followed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"Location": "http://10.0.0.1/"})

    finder = MetFinder(user_agent="t", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ImageSearchFailure, match="HTTP 301"):
        finder.find_images(ImageQuery(title="Cypresses"))


# -- what an object yields ---------------------------------------------------------------


def test_an_in_copyright_object_offers_no_image():
    registry = FakeRegistry(pages={WHEAT_ITEM: [WorkPage(f"https://www.metmuseum.org/art/collection/search/{KELLY}")]})

    assert a_finder(registry).find_images(ImageQuery(title="Black White", qid=WHEAT_ITEM)) == []


def test_an_object_the_met_says_it_does_not_have_is_skipped():
    gone = httpx.Response(404, json=fixture("object_not_found.json"))
    registry = FakeRegistry(pages={WHEAT_ITEM: [WEB_PAGE]})

    assert a_finder(registry, objects={WHEAT_FIELD: gone}).find_images(ImageQuery(title="x", qid=WHEAT_ITEM)) == []


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(404, text="<html>Not Found</html>"),
        httpx.Response(200, json={**fixture(OBJECTS[CYPRESSES])}),
        httpx.Response(200, text="<html>challenge</html>"),
        httpx.Response(503),
    ],
    ids=["unrecognised-404", "another-objects-record", "not-json", "unavailable"],
)
def test_an_object_answer_that_is_not_the_record_asked_for_could_not_be_asked(answer):
    registry = FakeRegistry(pages={WHEAT_ITEM: [WEB_PAGE]})

    with pytest.raises(ImageSearchFailure):
        a_finder(registry, objects={WHEAT_FIELD: answer}).find_images(ImageQuery(title="x", qid=WHEAT_ITEM))


def test_an_image_named_off_the_met_image_host_is_not_offered_or_read():
    asked: list[httpx.Request] = []
    elsewhere = {**fixture(OBJECTS[WHEAT_FIELD]), "primaryImage": "https://example.com/wheat.jpg"}
    registry = FakeRegistry(pages={WHEAT_ITEM: [WEB_PAGE]})

    found = a_finder(registry, asked, objects={WHEAT_FIELD: httpx.Response(200, json=elsewhere)}).find_images(
        ImageQuery(title="x", qid=WHEAT_ITEM)
    )

    assert found == []
    assert not [r for r in asked if r.url.host != "collectionapi.metmuseum.org"]


def test_the_size_is_read_from_a_ranged_head_of_the_original():
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={WHEAT_ITEM: [WEB_PAGE]})

    a_finder(registry, asked).find_images(ImageQuery(title="x", qid=WHEAT_ITEM))

    (head,) = [r for r in asked if r.url.host == "images.metmuseum.org"]
    assert str(head.url) == "https://images.metmuseum.org/CRDImages/ep/original/DP-42549-001.jpg"
    assert head.headers["Range"] == "bytes=0-262143"


def test_a_head_with_no_frame_leaves_the_size_unknown():
    registry = FakeRegistry(pages={WHEAT_ITEM: [WEB_PAGE]})
    png = lambda request: httpx.Response(206, content=b"\x89PNG\r\n\x1a\n" + bytes(1000))  # noqa: E731 -- a one-line answer

    (image,) = a_finder(registry, image=png).find_images(ImageQuery(title="x", qid=WHEAT_ITEM))

    assert (image.estimated_width, image.estimated_height) == (None, None)


def test_a_head_that_never_reaches_a_frame_stops_at_the_bound():
    """An endless body costs the bound, not the box."""
    registry = FakeRegistry(pages={WHEAT_ITEM: [WEB_PAGE]})
    served: list[int] = []

    def endless():
        # A host ignoring the range: a segment too long to hold a frame, then more, for ever.
        yield HEAD[:2] + b"\xff\xe1\xff\xff"
        while True:
            served.append(1)
            yield bytes(64 * 1024)

    (image,) = a_finder(registry, image=lambda r: httpx.Response(200, content=endless())).find_images(
        ImageQuery(title="x", qid=WHEAT_ITEM)
    )

    assert image.estimated_width is None
    assert len(served) <= 5


def test_an_image_host_that_refuses_the_head_could_not_be_asked():
    registry = FakeRegistry(pages={WHEAT_ITEM: [WEB_PAGE]})

    with pytest.raises(ImageSearchFailure, match="HTTP 403"):
        a_finder(registry, image=lambda r: httpx.Response(403)).find_images(ImageQuery(title="x", qid=WHEAT_ITEM))


def test_jpeg_size_reads_the_frame_and_none_from_a_head_cut_before_it():
    assert jpeg_size(HEAD) == (4000, 3184)
    assert jpeg_size(HEAD[:40_000]) is None
    assert jpeg_size(b"GIF89a") is None


# -- previews ----------------------------------------------------------------------------


def test_a_preview_is_read_from_the_image_host_only_and_under_the_ceiling():
    small = "https://images.metmuseum.org/CRDImages/ep/web-large/DP-42549-001.jpg"
    finder = MetFinder(
        user_agent="t",
        client=a_client(image=lambda r: httpx.Response(200, content=b"x" * 100)),
        preview_max_bytes=50,
    )
    assert finder.fetch_preview(small) is None
    assert finder.fetch_preview("https://example.com/p.jpg") is None

    roomy = MetFinder(user_agent="t", client=a_client(image=lambda r: httpx.Response(200, content=b"x" * 100)))
    assert roomy.fetch_preview(small) == b"x" * 100


# -- claims and reading ------------------------------------------------------------------


def test_the_plugin_claims_the_api_object_url_it_records_and_nothing_else():
    """A private reader of the Met's web pages claims those.

    One URL claimed by both would route one plugin's rows to the other's reader.
    """
    assert claims(object_url(WHEAT_FIELD))
    for other in (
        f"https://www.metmuseum.org/art/collection/search/{WHEAT_FIELD}",
        f"http://collectionapi.metmuseum.org/public/collection/v1/objects/{WHEAT_FIELD}",
        f"https://collectionapi.metmuseum.org:8443/public/collection/v1/objects/{WHEAT_FIELD}",
        f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{WHEAT_FIELD}?x=1",
        f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{WHEAT_FIELD}/extra",
        "https://collectionapi.metmuseum.org/public/collection/v1/objects/0123",
        f"https://example.com/public/collection/v1/objects/{WHEAT_FIELD}",
        "https://images.metmuseum.org/CRDImages/ep/original/DP-42549-001.jpg",
        "not a url at all",
    ):
        assert not claims(other), other


def test_the_reader_reads_a_public_domain_object_to_its_original():
    locator = a_reader().read(object_url(WHEAT_FIELD))

    assert locator.kind is LocatorKind.DIRECT
    assert locator.url == "https://images.metmuseum.org/CRDImages/ep/original/DP-42549-001.jpg"


def test_the_reader_says_none_for_an_in_copyright_object_and_for_one_the_met_does_not_have():
    gone = httpx.Response(404, json=fixture("object_not_found.json"))

    assert a_reader().read(object_url(KELLY)).kind is LocatorKind.NONE
    assert a_reader(objects={WHEAT_FIELD: gone}).read(object_url(WHEAT_FIELD)).kind is LocatorKind.NONE


def test_the_reader_refuses_a_url_it_does_not_claim_and_an_image_off_the_host():
    with pytest.raises(ImageSearchFailure):
        a_reader().read(f"https://www.metmuseum.org/art/collection/search/{WHEAT_FIELD}")
    elsewhere = {**fixture(OBJECTS[WHEAT_FIELD]), "primaryImage": "https://example.com/wheat.jpg"}
    with pytest.raises(ImageSearchFailure, match="off its image host"):
        a_reader(objects={WHEAT_FIELD: httpx.Response(200, json=elsewhere)}).read(object_url(WHEAT_FIELD))


def test_the_plugin_never_declines_and_finds_by_item_only_with_a_registry():
    without = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=None))
    with_registry = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=FakeRegistry()))

    for parts in (without, with_registry):
        assert isinstance(parts, SourceParts)
        assert parts.finder is not None
        assert parts.finder.provider == "met"
        assert parts.reader is not None
    assert PLUGIN.claims is claims
