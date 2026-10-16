"""Yale (YUAG and YCBA) as an image source, driven through the real client against recorded answers.

Every file under `tests/fixtures/yale/` is an answer Yale's manifest or image host
gave on 2026-10-07 (`linked-art-findings.md`). The object pages are never asked:
they are behind a challenge, and the transport below fails any request to them.
"""

import json
import logging
from pathlib import Path

import httpx
import pytest
from fakes import FakeRegistry

from arrt.config import DEFAULT_QUALITY_MINIMUM_PX
from arrt.library.discovery.images import ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.phase_two import CONFIDENT, PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry import ItemId, RegistryUnavailable, WorkPage
from arrt.library.services.quality import QualityProfile
from arrt.library.sources import FetchLocator, LocatorKind, SourceContext, SourceParts, yale
from arrt.library.sources.yale import PLUGIN, ObjectRef, YaleFinder, YaleReader, claims, object_ref
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import AcquisitionMethod, RightsStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yale"

#: (museum, number) → the recorded manifest. Any other object answers 404, as an object with no image does.
MANIFESTS = {
    ("yuag", "12507"): "manifest_yuag_12507_night_cafe.json",
    ("yuag", "28401"): "manifest_yuag_28401_rothko_in_copyright.json",
    ("yuag", "52642"): "manifest_yuag_52642_hopper_not_evaluated.json",
    ("yuag", "2746"): "manifest_yuag_2746_copy_after_romanelli.json",
    ("yuag", "8124"): "manifest_yuag_8124_artist_unknown.json",
    ("yuag", "77864"): "manifest_yuag_77864_not_assigned.json",
    ("ycba", "34"): "manifest_ycba_34_dort_five_canvases.json",
}

IMAGES = "https://images.collections.yale.edu/iiif/2/"

#: Image id → the recorded `info.json`.
INFOS = {
    "yuag:3b072179-2fc7-42bc-87cc-9ee4d782b270": "info_yuag_night_cafe.json",
    "yuag:d043425e-8e1c-4766-bcb4-ec455cae5171": "info_yuag_rothko.json",
    "yuag:b9079cbe-8492-421a-8ac4-a72e66ecad5b": "info_yuag_hopper_sunlight.json",
    "ycba:4f227f08-7842-46cc-b05a-e3c6a4614cc1": "info_ycba_dort_recto.json",
    "ycba:0eb669dc-788b-45f4-b2ec-b3cc74cc56f8": "info_ycba_dort_46800_radiograph.json",
}

NIGHT_CAFE_SERVICE = f"{IMAGES}yuag:3b072179-2fc7-42bc-87cc-9ee4d782b270"
DORT_RECTO_SERVICE = f"{IMAGES}ycba:4f227f08-7842-46cc-b05a-e3c6a4614cc1"
RADIOGRAPH_SERVICE = f"{IMAGES}ycba:0eb669dc-788b-45f4-b2ec-b3cc74cc56f8"

#: *The Night Café*, and its page as P8583's formatter builds it.
NIGHT_CAFE_ITEM = ItemId("Q674846")
NIGHT_CAFE_PAGE = WorkPage("https://artgallery.yale.edu/collections/objects/12507")
#: Rothko's *Untitled* (1958), in copyright.
ROTHKO_ITEM = ItemId("Q49251823")
ROTHKO_PAGE = WorkPage("https://artgallery.yale.edu/collections/objects/28401")
#: Hopper's *Sunlight in a Cafeteria*, "Copyright Not Evaluated".
SUNLIGHT_ITEM = ItemId("Q49198630")
SUNLIGHT_PAGE = WorkPage("https://artgallery.yale.edu/collections/objects/52642")
#: Turner's *Dort*, at YCBA, as P9789's formatter builds its page. A stand-in item.
DORT_ITEM = ItemId("Q90000034")
DORT_PAGE = WorkPage("https://collections.britishart.yale.edu/catalog/tms:34")


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def recorded(request: httpx.Request, *, manifests=None, infos=None, preview=None) -> httpx.Response:
    """Yale as it answered: manifests by museum and number, `info.json`s and previews by image id."""
    url = request.url
    if url.host == "manifests.collections.yale.edu":
        museum, _, number = url.path.strip("/").partition("/obj/")
        answer = (manifests or {}).get((museum, number))
        if answer is not None:
            return answer
        name = MANIFESTS.get((museum, number))
        return httpx.Response(200, json=fixture(name)) if name else httpx.Response(404, text="Not Found")
    assert url.host == "images.collections.yale.edu", f"asked a host the plugin must not: {url}"
    path = url.path.removeprefix("/iiif/2/")
    image, _, rest = path.partition("/")
    if rest == "info.json":
        answer = (infos or {}).get(image)
        if answer is not None:
            return answer
        return httpx.Response(200, json=fixture(INFOS[image]))
    return preview(request) if preview else httpx.Response(200, content=b"preview")


def a_transport(asked: list | None = None, **kwargs) -> httpx.MockTransport:
    """The recorded Yale, under the plugin's own client policy: a test passes a transport, never a client."""

    def handler(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(request)
        return recorded(request, **kwargs)

    return httpx.MockTransport(handler)


def a_finder(registry, asked=None, **kwargs) -> YaleFinder:
    return YaleFinder(user_agent="arrt-tests/0", registry=registry, transport=a_transport(asked, **kwargs))


def a_reader(asked=None, **kwargs) -> YaleReader:
    return YaleReader(user_agent="arrt-tests/0", transport=a_transport(asked, **kwargs))


def pages(*urls: str, qid: ItemId = NIGHT_CAFE_ITEM) -> FakeRegistry:
    return FakeRegistry(pages={qid: [WorkPage(u) for u in urls]})


def find(*urls: str, qid: ItemId = NIGHT_CAFE_ITEM, asked=None, **kwargs):
    return a_finder(pages(*urls, qid=qid), asked, **kwargs).find_images(ImageQuery(title="x", qid=qid))


def manifest_with(name: str, change) -> httpx.Response:
    """A recorded manifest, changed in place by `change`."""
    manifest = fixture(name)
    change(manifest)
    return httpx.Response(200, json=manifest)


def manifests_read(asked: list[httpx.Request]) -> list[str]:
    return [r.url.path for r in asked if r.url.host == "manifests.collections.yale.edu"]


PROFILE = QualityProfile(minimum_long_edge_px=DEFAULT_QUALITY_MINIMUM_PX)


# -- claims ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "ref"),
    [
        (NIGHT_CAFE_PAGE, ObjectRef("yuag", "12507")),
        ("http://artgallery.yale.edu/collections/objects/12507", ObjectRef("yuag", "12507")),
        ("https://artgallery.yale.edu/collections/objects/12507/", ObjectRef("yuag", "12507")),
        (DORT_PAGE, ObjectRef("ycba", "34")),
        ("http://collections.britishart.yale.edu/catalog/tms:38743", ObjectRef("ycba", "38743")),
    ],
)
def test_the_plugin_claims_each_museums_page_and_reads_its_object(url, ref):
    assert claims(url)
    assert object_ref(url) == ref
    assert ref.manifest_url == f"https://manifests.collections.yale.edu/{ref.museum}/obj/{ref.number}"


@pytest.mark.parametrize(
    "url",
    [
        "https://artgallery.yale.edu.example.com/collections/objects/12507",
        "https://example.com/collections/objects/12507",
        "https://artgallery.yale.edu/collections/objects/12507/images",
        "https://artgallery.yale.edu/collections/objects/abc",
        "https://artgallery.yale.edu/collections/objects/012507",
        "https://artgallery.yale.edu/collections/objects/12507?tab=images",
        "https://artgallery.yale.edu/collections/objects/12507#top",
        "https://artgallery.yale.edu:8443/collections/objects/12507",
        "ftp://artgallery.yale.edu/collections/objects/12507",
        "https://collections.britishart.yale.edu/vufind/Record/1671503",
        "https://collections.britishart.yale.edu/catalog/tms:34/",
        "https://lux.collections.yale.edu/view/object/3b0e2c2d-2c8e-4a5f-8f43-2b9c35f1c1a1",
        "https://manifests.collections.yale.edu/yuag/obj/12507",
        "not a url at all",
        "https://[::1",
    ],
)
def test_the_plugin_refuses_another_host_a_look_alike_and_another_shape(url):
    assert not claims(url)


# -- finding -----------------------------------------------------------------------------


def test_a_work_whose_item_names_a_yuag_page_is_found_from_the_manifest_under_that_page():
    asked: list[httpx.Request] = []

    (image,) = find("https://www.moma.org/collection/works/1", NIGHT_CAFE_PAGE, asked=asked)

    assert image.url == NIGHT_CAFE_PAGE
    assert (image.provider, image.title, image.artist) == ("yale", "Le café de nuit (The Night Café)", "Vincent van Gogh")
    assert (image.estimated_width, image.estimated_height) == (7408, 5848)
    assert image.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert image.preview_url == f"{NIGHT_CAFE_SERVICE}/full/!400,400/0/default.jpg"
    assert [str(r.url) for r in asked] == ["https://manifests.collections.yale.edu/yuag/obj/12507"]
    assert {r.headers["User-Agent"] for r in asked} == {"arrt-tests/0"}


def test_the_page_as_the_item_spells_it_identifies_the_work_through_the_identity_check():
    """Yale's title is longer than the work's; the item's link settles it, and the artist is still checked.

    Driven through phase 2, the caller that reads the link, so a finder that
    reported a page of its own spelling would be refused here on its title.
    """
    spelled = "http://artgallery.yale.edu/collections/objects/12507/"
    registry = pages(spelled)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=PROFILE, registry=registry)

    resolution = engine.resolve(ImageQuery(title="The Night Café", artist="Vincent van Gogh", qid=NIGHT_CAFE_ITEM))

    (entry,) = resolution.instances
    assert entry.found.url == spelled
    assert entry.confidence == CONFIDENT
    assert "Wikidata item records" in entry.rationale
    assert resolution.refusals == frozenset()


def test_another_artists_object_linked_by_mistake_is_refused_by_the_identity_check():
    """An item naming Rothko's page for a Hopper: the link stands, the artist does not."""
    registry = pages(ROTHKO_PAGE, qid=SUNLIGHT_ITEM)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=PROFILE, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Sunlight in a Cafeteria", artist="Edward Hopper", qid=SUNLIGHT_ITEM))

    assert list(resolution.instances) == []
    assert UnresolvedReason.IDENTITY_REFUSED in resolution.refusals


def test_an_in_copyright_work_is_found_at_the_480_pixels_served_and_recorded_as_in_copyright():
    (image,) = find(ROTHKO_PAGE, qid=ROTHKO_ITEM)

    assert (image.title, image.artist) == ("Untitled", "Mark Rothko")
    assert (image.estimated_width, image.estimated_height) == (376, 480)
    assert image.rights_status is RightsStatus.IN_COPYRIGHT


def test_the_manifests_own_cc0_is_never_read_as_the_images():
    """Every Yale manifest says CC0, Rothko's too: it licenses the record."""
    assert fixture(MANIFESTS["yuag", "28401"])["rights"] == "https://creativecommons.org/publicdomain/zero/1.0/"

    (image,) = find(ROTHKO_PAGE, qid=ROTHKO_ITEM)

    assert image.rights_status is RightsStatus.IN_COPYRIGHT


@pytest.mark.parametrize(
    ("page", "rights"),
    [
        (SUNLIGHT_PAGE, RightsStatus.UNKNOWN),
        ("https://artgallery.yale.edu/collections/objects/77864", RightsStatus.UNKNOWN),
        (DORT_PAGE, RightsStatus.PUBLIC_DOMAIN),
    ],
    ids=["copyright-not-evaluated", "not-assigned", "cc0-text"],
)
def test_each_rights_statement_is_read_for_what_it_says(page, rights):
    (image,) = find(page)

    assert image.rights_status is rights


@pytest.mark.parametrize("stated", [["No Copyright – United States"], [], ["In copyright"]], ids=["en-dash", "none", "lowercase"])
def test_a_rights_statement_never_seen_is_unknown_and_still_found(stated):
    def change(manifest):
        manifest["items"][0]["metadata"] = [{"label": {"en": ["Image Use Rights"]}, "value": {"en": stated}}] if stated else []

    (image,) = find(NIGHT_CAFE_PAGE, manifests={("yuag", "12507"): manifest_with(MANIFESTS["yuag", "12507"], change)})

    assert image.rights_status is RightsStatus.UNKNOWN


def test_a_ycba_object_is_its_first_canvas_and_its_maker_is_read_from_ycbas_creator_line():
    """The Dort's first canvas is "recto, cropped to image"; its fifth is a 46,800-pixel X-ray."""
    (image,) = find(DORT_PAGE, qid=DORT_ITEM)

    assert image.title == "Dort, or Dordrecht: The Dort Packet-Boat from Rotterdam Becalmed"
    assert image.artist == "Joseph Mallord William Turner"
    assert (image.estimated_width, image.estimated_height) == (14484, 9741)
    assert image.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    assert image.preview_url == f"{DORT_RECTO_SERVICE}/full/!400,400/0/default.jpg"


def test_a_first_canvas_longer_than_one_request_serves_is_found_as_tiles():
    def x_ray_first(manifest):
        manifest["items"] = manifest["items"][4:]

    (image,) = find(DORT_PAGE, qid=DORT_ITEM, manifests={("ycba", "34"): manifest_with(MANIFESTS["ycba", "34"], x_ray_first)})

    assert (image.estimated_width, image.estimated_height) == (46800, 34053)
    assert image.acquisition_method is AcquisitionMethod.DEZOOMIFY


@pytest.mark.parametrize(
    ("page", "artist"),
    [
        ("https://artgallery.yale.edu/collections/objects/2746", "Artist, copy after: Giovanni Francesco Romanelli"),
        ("https://artgallery.yale.edu/collections/objects/8124", None),
        (SUNLIGHT_PAGE, "Edward Hopper"),
    ],
    ids=["a-copy-keeps-its-role", "an-unknown-hand-is-none", "plain-artist"],
)
def test_the_maker_is_yales_own_words_without_the_biography(page, artist):
    (image,) = find(page)

    assert image.artist == artist


@pytest.mark.parametrize(
    ("creators", "artist"),
    [
        (["Printer: Atelier Mourlot (French)", "Artist: Pablo Picasso (Spanish, 1881–1973)"], "Pablo Picasso"),
        (["Publisher: Ambroise Vollard (French, 1866–1939)"], "Publisher: Ambroise Vollard"),
        (["Artist: Unknown , English, 18th century"], None),
        ([], None),
    ],
    ids=["the-artist-among-other-roles", "no-artist-role-keeps-the-first", "unknown-with-a-place", "no-creator"],
)
def test_among_several_makers_the_artist_is_read(creators, artist):
    def change(manifest):
        manifest["metadata"] = [m for m in manifest["metadata"] if m["label"]["en"] != ["Creator(s)"]]
        if creators:
            manifest["metadata"].append({"label": {"en": ["Creator(s)"]}, "value": {"en": creators}})

    (image,) = find(NIGHT_CAFE_PAGE, manifests={("yuag", "12507"): manifest_with(MANIFESTS["yuag", "12507"], change)})

    assert image.artist == artist


def test_an_object_yale_has_no_manifest_for_is_skipped_and_the_rest_stands(caplog):
    caplog.set_level(logging.INFO, logger=yale.__name__)
    asked: list[httpx.Request] = []
    no_image = "https://artgallery.yale.edu/collections/objects/90363"

    found = find(no_image, NIGHT_CAFE_PAGE, asked=asked)

    assert [image.url for image in found] == [NIGHT_CAFE_PAGE]
    assert sorted(manifests_read(asked)) == ["/yuag/obj/12507", "/yuag/obj/90363"]
    assert any(getattr(r, "event", None) == "yale.no_manifest" for r in caplog.records)


def test_a_manifest_with_no_canvases_is_no_image():
    no_canvas = manifest_with(MANIFESTS["yuag", "12507"], lambda m: m.update(items=[]))

    assert find(NIGHT_CAFE_PAGE, manifests={("yuag", "12507"): no_canvas}) == []


def test_two_spellings_of_one_object_read_it_once_under_the_first():
    asked: list[httpx.Request] = []

    found = find("http://artgallery.yale.edu/collections/objects/12507", NIGHT_CAFE_PAGE, asked=asked)

    assert [image.url for image in found] == ["http://artgallery.yale.edu/collections/objects/12507"]
    assert manifests_read(asked) == ["/yuag/obj/12507"]


def test_an_item_naming_more_than_ten_yale_pages_reads_ten_manifests():
    asked: list[httpx.Request] = []

    find(*(f"https://artgallery.yale.edu/collections/objects/{n}" for n in range(100, 112)), asked=asked)

    assert len(manifests_read(asked)) == 10


def test_an_item_naming_no_yale_page_finds_nothing_and_asks_nothing():
    asked: list[httpx.Request] = []

    assert find("https://www.moma.org/collection/works/1", asked=asked) == []
    assert asked == []


def test_a_work_with_no_item_cannot_be_asked_of_yale():
    with pytest.raises(ImageQueryUnanswerable):
        a_finder(FakeRegistry()).find_images(ImageQuery(title="The Night Café", artist="Vincent van Gogh"))


def test_a_registry_that_cannot_be_asked_is_a_search_that_could_not_be_asked():
    class Down(FakeRegistry):
        def pages_about(self, qid):
            raise RegistryUnavailable("timed out")

    with pytest.raises(ImageSearchFailure, match="Wikidata could not be asked"):
        a_finder(Down()).find_images(ImageQuery(title="x", qid=NIGHT_CAFE_ITEM))


def _network_down(_):
    raise httpx.ConnectError("unreachable")


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(403, text="<title>Just a moment...</title>"),
        httpx.Response(429, text="slow down"),
        httpx.Response(500, text="oops"),
        httpx.Response(301, headers={"Location": "https://elsewhere.example.com/manifest"}),
        httpx.Response(200, text="<html>This site is unavailable</html>"),
        httpx.Response(200, json=["not", "a", "manifest"]),
        httpx.Response(200, json={"@context": "http://iiif.io/api/presentation/3/context.json", "type": "Collection"}),
    ],
    ids=["challenge", "rate-limited", "server-error", "redirect", "html", "json-list", "a-collection"],
)
def test_a_manifest_answer_that_is_not_a_manifest_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure):
        find(NIGHT_CAFE_PAGE, manifests={("yuag", "12507"): answer})


def test_a_network_failure_could_not_be_asked():
    registry = pages(NIGHT_CAFE_PAGE)
    finder = YaleFinder(user_agent="t", registry=registry, transport=httpx.MockTransport(_network_down))

    with pytest.raises(ImageSearchFailure, match="Could not read the manifest of YUAG object 12507"):
        finder.find_images(ImageQuery(title="x", qid=NIGHT_CAFE_ITEM))


@pytest.mark.parametrize(
    "service",
    [
        "https://images.collections.yale.edu.example.com/iiif/2/yuag:x",
        "http://images.collections.yale.edu/iiif/2/yuag:x",
        "https://iiif.micr.io/PJEZO",
        "https://images.collections.yale.edu/other/yuag:x",
        "https://images.collections.yale.edu:8443/iiif/2/yuag:x",
        "https://user@images.collections.yale.edu/iiif/2/yuag:x",
    ],
    ids=["look-alike-host", "plain-http", "another-museum", "another-path", "a-port", "credentials"],
)
def test_an_image_service_off_yales_image_host_is_not_offered_or_read(service):
    def elsewhere(manifest):
        manifest["items"][0]["items"][0]["items"][0]["body"]["service"][0]["@id"] = service

    answer = manifest_with(MANIFESTS["yuag", "12507"], elsewhere)

    with pytest.raises(ImageSearchFailure):
        find(NIGHT_CAFE_PAGE, manifests={("yuag", "12507"): answer})
    with pytest.raises(ImageSearchFailure, match=r"off images\.collections\.yale\.edu"):
        a_reader(manifests={("yuag", "12507"): answer}).read(NIGHT_CAFE_PAGE)


def test_a_canvas_whose_image_is_not_iiif_could_not_be_asked():
    def plain_file(manifest):
        del manifest["items"][0]["items"][0]["items"][0]["body"]["service"]

    answer = manifest_with(MANIFESTS["yuag", "12507"], plain_file)

    with pytest.raises(ImageSearchFailure):
        find(NIGHT_CAFE_PAGE, manifests={("yuag", "12507"): answer})
    with pytest.raises(ImageSearchFailure, match="not a IIIF image service"):
        a_reader(manifests={("yuag", "12507"): answer}).read(NIGHT_CAFE_PAGE)


def test_a_manifest_giving_no_title_could_not_be_asked():
    def untitled(manifest):
        manifest["metadata"] = [m for m in manifest["metadata"] if m["label"]["en"] != ["Title"]]

    with pytest.raises(ImageSearchFailure, match="no title"):
        find(NIGHT_CAFE_PAGE, manifests={("yuag", "12507"): manifest_with(MANIFESTS["yuag", "12507"], untitled)})


# -- previews ----------------------------------------------------------------------------


def test_a_preview_is_read_from_yales_image_host_only_and_under_the_ceiling():
    preview = f"{NIGHT_CAFE_SERVICE}/full/!400,400/0/default.jpg"

    def big(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 100)

    roomy = YaleFinder(user_agent="t", registry=FakeRegistry(), transport=a_transport(preview=big), preview_max_bytes=100)
    tight = YaleFinder(user_agent="t", registry=FakeRegistry(), transport=a_transport(preview=big), preview_max_bytes=99)

    assert roomy.fetch_preview(preview) == b"x" * 100
    assert tight.fetch_preview(preview) is None
    assert roomy.fetch_preview("https://iiif.micr.io/PJEZO/full/!400,400/0/default.jpg") is None


@pytest.mark.parametrize(
    "answer",
    [
        lambda _: httpx.Response(404),
        lambda _: httpx.Response(302, headers={"Location": "http://10.0.0.1/secret"}),
        _network_down,
    ],
    ids=["not-found", "redirect-not-followed", "network"],
)
def test_a_preview_that_cannot_be_read_is_none(answer):
    finder = YaleFinder(user_agent="t", registry=FakeRegistry(), transport=a_transport(preview=answer))

    assert finder.fetch_preview(f"{NIGHT_CAFE_SERVICE}/full/!400,400/0/default.jpg") is None


# -- reading -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("page", "service"),
    [
        (NIGHT_CAFE_PAGE, NIGHT_CAFE_SERVICE),
        (ROTHKO_PAGE, f"{IMAGES}yuag:d043425e-8e1c-4766-bcb4-ec455cae5171"),
        (DORT_PAGE, DORT_RECTO_SERVICE),
    ],
    ids=["public-domain", "in-copyright-480", "ycba-14484"],
)
def test_the_reader_reads_a_page_through_its_manifest_to_one_request_for_the_original(page, service):
    asked: list[httpx.Request] = []

    locator = a_reader(asked).read(page)

    assert locator == FetchLocator.direct(f"{service}/full/full/0/default.jpg")
    assert [r.url.host for r in asked] == ["manifests.collections.yale.edu", "images.collections.yale.edu"]
    assert str(asked[1].url) == f"{service}/info.json"


def test_the_reader_reads_an_original_longer_than_one_request_serves_as_tiles():
    def x_ray_first(manifest):
        manifest["items"] = manifest["items"][4:]

    locator = a_reader(manifests={("ycba", "34"): manifest_with(MANIFESTS["ycba", "34"], x_ray_first)}).read(DORT_PAGE)

    assert locator == FetchLocator.tiles(f"{RADIOGRAPH_SERVICE}/info.json")


def test_the_reader_reads_a_declared_limit_below_the_original_as_tiles():
    info = {**fixture(INFOS["yuag:3b072179-2fc7-42bc-87cc-9ee4d782b270"])}
    info["profile"] = [info["profile"][0], {**info["profile"][1], "maxWidth": 2000}]

    locator = a_reader(infos={"yuag:3b072179-2fc7-42bc-87cc-9ee4d782b270": httpx.Response(200, json=info)}).read(NIGHT_CAFE_PAGE)

    assert locator == FetchLocator.tiles(f"{NIGHT_CAFE_SERVICE}/info.json")


def test_the_reader_says_none_for_an_object_with_no_manifest_and_one_with_no_canvas():
    no_canvas = manifest_with(MANIFESTS["yuag", "12507"], lambda m: m.update(items=[]))

    assert a_reader().read("https://artgallery.yale.edu/collections/objects/90363").kind is LocatorKind.NONE
    assert a_reader(manifests={("yuag", "12507"): no_canvas}).read(NIGHT_CAFE_PAGE).kind is LocatorKind.NONE


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500, text="Invalid scanline stride"),
        httpx.Response(200, text="<html></html>"),
        httpx.Response(200, json={"@context": "http://iiif.io/api/image/2/context.json", "@id": NIGHT_CAFE_SERVICE}),
        httpx.Response(
            200,
            json={"@context": "http://iiif.io/api/image/2/context.json", "@id": RADIOGRAPH_SERVICE, "width": 1, "height": 1},
        ),
    ],
    ids=["server-error", "html", "no-size", "another-image"],
)
def test_an_image_service_answer_that_is_not_this_images_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure):
        a_reader(infos={"yuag:3b072179-2fc7-42bc-87cc-9ee4d782b270": answer}).read(NIGHT_CAFE_PAGE)


def test_the_reader_refuses_a_url_it_does_not_claim_and_never_asks_for_it():
    asked: list[httpx.Request] = []

    with pytest.raises(ImageSearchFailure):
        a_reader(asked).read("https://collections.britishart.yale.edu/vufind/Record/1671503")
    assert asked == []


# -- the plugin --------------------------------------------------------------------------


def test_the_factory_wires_the_deployments_registry_agent_and_preview_ceiling(monkeypatch):
    """Through the plugin's own factory, with values no default carries."""
    asked: list[httpx.Request] = []
    real = yale._client
    monkeypatch.setattr(
        yale,
        "_client",
        lambda transport: real(transport or a_transport(asked, preview=lambda r: httpx.Response(200, content=b"x" * 100))),
    )
    registry = pages(NIGHT_CAFE_PAGE)
    preview = f"{NIGHT_CAFE_SERVICE}/full/!400,400/0/default.jpg"

    parts = PLUGIN.create(SourceContext(environ={}, user_agent="deployment/7", preview_max_bytes=50, registry=registry))
    (image,) = parts.finder.find_images(ImageQuery(title="x", qid=NIGHT_CAFE_ITEM))
    locator = parts.reader.read(NIGHT_CAFE_PAGE)

    assert image.url == NIGHT_CAFE_PAGE
    assert locator.kind is LocatorKind.DIRECT
    assert registry.pages_asked == [NIGHT_CAFE_ITEM]
    assert {r.headers["User-Agent"] for r in asked} == {"deployment/7"}
    assert parts.finder.fetch_preview(preview) is None
    roomy = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1000, registry=registry))
    assert roomy.finder.fetch_preview(preview) == b"x" * 100


def test_the_plugin_never_declines_and_finds_only_with_a_registry():
    without = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=None))
    with_registry = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=FakeRegistry()))

    assert isinstance(without, SourceParts)
    assert (without.finder, without.reader is not None) == (None, True)
    assert isinstance(with_registry, SourceParts)
    assert with_registry.finder.provider == "yale"
    assert with_registry.reader is not None
    assert PLUGIN.claims is claims
