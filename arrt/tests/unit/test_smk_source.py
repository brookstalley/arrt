"""SMK as an image source, driven through the real client against recorded answers.

Every file under `tests/fixtures/smk/` is an answer SMK's API gave on 2026-10-06,
asked in English as the plugin asks (`smk-api-findings.md`).
"""

import json
from pathlib import Path

import httpx
import pytest
from fakes import FakeRegistry

from arrt.config import DEFAULT_QUALITY_MINIMUM_PX
from arrt.library.discovery.images import ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.phase_two import CONFIDENT, PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry import ItemId, WorkPage
from arrt.library.services.quality import QualityProfile
from arrt.library.sources import FetchLocator, LocatorKind, SourceContext, SourceParts, smk
from arrt.library.sources.smk import PLUGIN, SmkFinder, SmkReader, claims, object_number
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import AcquisitionMethod, RightsStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "smk"

#: Object number → the recorded answer for it.
OBJECTS = {
    "KMS1": "object_KMS1_fall_of_the_titans.json",
    "KMS8010": "object_KMS8010_tree_trunks.json",
    "KKS2020-3/16": "object_KKS2020-3_16_salon_in_copyright.json",
    "KMSst28Ø": "object_KMSst28_no_image.json",
}

#: (keys, fields) → the recorded search answer. Any other search found nothing.
SEARCHES = {
    ("Interior", ("titles",)): "search_title_interior.json",
    ("Interior Vilhelm Hammershøi", ("titles", "creator")): "search_interior_vilhelm_hammershoi.json",
}

#: SMK's front-end page for *Tree Trunks*, exactly as Wikidata's Q20268298 records it (P973).
TREE_TRUNKS_ITEM = ItemId("Q20268298")
FRAGMENT_PAGE = "https://collection.smk.dk/#/en/detail/KMS8010"

DANISH_COPYRIGHT_PAGE = "https://www.smk.dk/section/brug-af-museets-materiale/"
ENGLISH_COPYRIGHT_PAGE = "https://www.smk.dk/en/section/use-of-smk-material/"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def record(number: str) -> dict:
    (item,) = fixture(OBJECTS[number])["items"]
    return item


def recorded(request: httpx.Request, *, objects=None, searches=None, thumbnail=None) -> httpx.Response:
    """SMK as it answered: objects by number, searches by keys and fields, thumbnails by host."""
    url = request.url
    if url.host == "iip-thumb.smk.dk":
        return thumbnail(request) if thumbnail else httpx.Response(200, content=b"thumbnail")
    assert url.host == "api.smk.dk", f"asked a host the plugin is not about: {url}"
    if url.path == "/api/v1/art/search/":
        key = (url.params["keys"], tuple(url.params.get_list("qfields")))
        answer = (searches or {}).get(key)
        if answer is not None:
            return answer
        return httpx.Response(200, json=fixture(SEARCHES.get(key, "search_nothing.json")))
    assert url.path == "/api/v1/art/", url
    number = url.params["object_number"]
    answer = (objects or {}).get(number)
    if answer is not None:
        return answer
    for known, name in OBJECTS.items():
        if known.casefold() == number.casefold():
            return httpx.Response(200, json=fixture(name))
    return httpx.Response(200, json=fixture("object_not_found.json"))


def a_transport(asked: list | None = None, **kwargs) -> httpx.MockTransport:
    """The recorded SMK, under the plugin's own client policy: a test passes a transport, never a client."""

    def handler(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(request)
        return recorded(request, **kwargs)

    return httpx.MockTransport(handler)


def a_finder(registry=None, asked=None, **kwargs) -> SmkFinder:
    return SmkFinder(user_agent="arrt-tests/0", registry=registry, transport=a_transport(asked, **kwargs))


def a_reader(**kwargs) -> SmkReader:
    return SmkReader(user_agent="arrt-tests/0", transport=a_transport(**kwargs))


def answer_with(number: str, **changes) -> httpx.Response:
    """The recorded object, with some of its fields changed."""
    return httpx.Response(200, json={"items": [{**record(number), **changes}]})


def searches_made(asked: list[httpx.Request]) -> list[tuple[str, tuple[str, ...]]]:
    return [(r.url.params["keys"], tuple(r.url.params.get_list("qfields"))) for r in asked if r.url.path.endswith("/search/")]


def objects_read(asked: list[httpx.Request]) -> list[str]:
    return [r.url.params["object_number"] for r in asked if r.url.path == "/api/v1/art/"]


# -- claims ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "number"),
    [
        (FRAGMENT_PAGE, "KMS8010"),
        ("https://collection.smk.dk/#/detail/KMS412", "KMS412"),
        ("https://collection.smk.dk/#/detail/KKS12485%2F6", "KKS12485/6"),
        ("http://collection.smk.dk/#/en/detail/KMSst28Ø", "KMSst28Ø"),
        ("https://open.smk.dk/artwork/image/KKS2020-3/16", "KKS2020-3/16"),
        ("https://open.smk.dk/en/artwork/image/KMS421/", "KMS421"),
        ("https://open.smk.dk/artwork/image/KMS4585?q=KMS4585&page=0", "KMS4585"),
        ("https://api.smk.dk/api/v1/art?object_number=KMS1", "KMS1"),
        ("https://api.smk.dk/api/v1/art/?object_number=KKS2020-3/16", "KKS2020-3/16"),
    ],
)
def test_the_plugin_claims_each_shape_an_item_or_the_api_spells_and_reads_its_object_number(url, number):
    """Every spelling here was found on a Wikidata item or in an API answer (2026-10-06)."""
    assert claims(url)
    assert object_number(url) == number


@pytest.mark.parametrize(
    "url",
    [
        "https://smk.dk.example.com/#/en/detail/KMS8010",
        "https://collection.smk.dk.example.com/#/en/detail/KMS8010",
        "https://example.com/artwork/image/KMS1",
        "https://www.smk.dk/udforsk-kunsten/soeg-i-smk/#/detail/KMS3648",
        "https://collection.smk.dk/detail/KMS8010",
        "https://collection.smk.dk/#/en/search/KMS8010",
        "https://collection.smk.dk/#/en/detail/",
        "https://collection.smk.dk/#/en/detail/KMS8010?x=1",
        "https://collection.smk.dk/?q=1#/en/detail/KMS8010",
        "https://open.smk.dk/artwork/KMS1",
        "https://open.smk.dk/artwork/image/KMS1#top",
        "https://open.smk.dk/artwork/image/KMS%2520x",
        "https://open.smk.dk:8443/artwork/image/KMS1",
        "https://user@open.smk.dk/artwork/image/KMS1",
        "ftp://open.smk.dk/artwork/image/KMS1",
        "http://api.smk.dk/api/v1/art?object_number=KMS1",
        "https://api.smk.dk/api/v1/art?object_number=KMS1&lang=en",
        "https://api.smk.dk/api/v1/art/search/?keys=KMS1",
        "https://api.smk.dk/api/v1/download/W3sia/KMS1.jpg",
        "https://iip.smk.dk/iiif/jp2/9g54xm869_KMS1-cropped.tif.jp2/info.json",
        "https://open.smk.dk/artwork/image/" + "K" * 65,
        "not a url at all",
    ],
)
def test_the_plugin_refuses_another_host_a_look_alike_and_another_shape(url):
    assert not claims(url)


# -- finding by Wikidata item ------------------------------------------------------------


def test_a_work_whose_item_records_an_smk_page_is_read_from_that_object_under_the_page_and_not_searched():
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [WorkPage("https://www.moma.org/collection/works/1"), FRAGMENT_PAGE]})

    (image,) = a_finder(registry, asked).find_images(ImageQuery(title="Tree Trunks", qid=TREE_TRUNKS_ITEM))

    assert image.url == FRAGMENT_PAGE
    assert (image.provider, image.title, image.artist) == (
        "smk",
        "Tree Trunks. Arresødal near Frederiksværk, North Zealand",
        "Vilhelm Hammershøi",
    )
    assert (image.estimated_width, image.estimated_height) == (7217, 4873)
    assert image.preview_url == "https://iip-thumb.smk.dk/iiif/jp2/5712m747g_KMS8010.tif.jp2/full/!1024,/0/default.jpg"
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert image.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    assert searches_made(asked) == []
    (read,) = [r for r in asked if r.url.path == "/api/v1/art/"]
    assert (read.url.params["object_number"], read.url.params["lang"]) == ("KMS8010", "en")


def test_the_fragment_page_identifies_the_work_through_the_identity_check():
    """The case the plan names: SMK's title is longer than the work's, and the item's link settles it.

    Driven through phase 2, the caller that reads the link, so a finder that
    reported a page of its own spelling would be refused here on its title.
    """
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [FRAGMENT_PAGE]})
    profile = QualityProfile(minimum_long_edge_px=DEFAULT_QUALITY_MINIMUM_PX)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=profile, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Tree Trunks", artist="Vilhelm Hammershøi", qid=TREE_TRUNKS_ITEM))

    (entry,) = resolution.instances
    assert entry.found.url == FRAGMENT_PAGE
    assert entry.confidence == CONFIDENT
    assert "Wikidata item records" in entry.rationale
    assert resolution.refusals == frozenset()


def test_two_pages_for_one_object_read_it_once_under_the_first():
    asked: list[httpx.Request] = []
    pages = [FRAGMENT_PAGE, WorkPage("https://open.smk.dk/artwork/image/KMS8010")]

    found = a_finder(FakeRegistry(pages={TREE_TRUNKS_ITEM: pages}), asked).find_images(
        ImageQuery(title="x", qid=TREE_TRUNKS_ITEM)
    )

    assert [image.url for image in found] == [FRAGMENT_PAGE]
    assert objects_read(asked) == ["KMS8010"]


def test_an_item_naming_no_smk_page_falls_back_to_search():
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [WorkPage("https://www.moma.org/collection/works/1")]})

    found = a_finder(registry, asked).find_images(ImageQuery(title="Interior", artist="Vilhelm Hammershøi", qid=TREE_TRUNKS_ITEM))

    assert searches_made(asked) == [("Interior Vilhelm Hammershøi", ("titles", "creator"))]
    assert {image.artist for image in found} == {"Vilhelm Hammershøi"}


def test_an_object_number_smk_does_not_know_skips_that_page_and_the_rest_stands():
    asked: list[httpx.Request] = []
    pages = [WorkPage("https://collection.smk.dk/#/en/detail/KMS99999999"), FRAGMENT_PAGE]

    found = a_finder(FakeRegistry(pages={TREE_TRUNKS_ITEM: pages}), asked).find_images(
        ImageQuery(title="x", qid=TREE_TRUNKS_ITEM)
    )

    assert [image.url for image in found] == [FRAGMENT_PAGE]
    assert searches_made(asked) == []


def test_an_item_whose_smk_pages_name_no_object_smk_knows_is_searched_for():
    """A number SMK has dropped says nothing about whether it holds the work under another."""
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [WorkPage("https://collection.smk.dk/#/en/detail/KMS99999999")]})

    found = a_finder(registry, asked).find_images(ImageQuery(title="Interior", qid=TREE_TRUNKS_ITEM))

    assert searches_made(asked) == [("Interior", ("titles",))]
    assert found


def test_an_item_whose_object_has_no_image_is_not_searched_for():
    """SMK knows the object and offers no image of it: that is an answer about this work."""
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [WorkPage("http://collection.smk.dk/#/en/detail/KMSst28Ø")]})

    found = a_finder(registry, asked).find_images(ImageQuery(title="Anna", qid=TREE_TRUNKS_ITEM))

    assert found == []
    assert objects_read(asked) == ["KMSst28Ø"]
    assert searches_made(asked) == []


def test_a_registry_that_cannot_be_asked_is_a_search_that_could_not_be_asked():
    with pytest.raises(ImageSearchFailure, match="Wikidata could not be asked"):
        a_finder(FakeRegistry(failing=True)).find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM))


def test_no_registry_searches_even_with_an_item():
    asked: list[httpx.Request] = []

    a_finder(None, asked).find_images(ImageQuery(title="Interior", qid=TREE_TRUNKS_ITEM))

    assert searches_made(asked) == [("Interior", ("titles",))]


# -- finding by search -------------------------------------------------------------------


def test_a_search_asks_for_the_title_and_artist_words_among_objects_with_images_ten_at_most():
    asked: list[httpx.Request] = []

    found = a_finder(asked=asked).find_images(ImageQuery(title="Interior", artist="Vilhelm Hammershøi"))

    (search,) = [r for r in asked if r.url.path.endswith("/search/")]
    assert search.url.params["filters"] == "[has_image:true]"
    assert (search.url.params["rows"], search.url.params["lang"]) == ("10", "en")
    assert [image.url for image in found] == [
        "https://open.smk.dk/artwork/image/KMS8677",
        "https://open.smk.dk/artwork/image/KMS7444",
        "https://open.smk.dk/artwork/image/KMS7246",
        "https://open.smk.dk/artwork/image/KKS9475",
        "https://open.smk.dk/artwork/image/KMS3696",
    ]
    assert objects_read(asked) == []


def test_a_title_and_artist_search_that_finds_nothing_leaves_the_titles_own_results():
    """Otherwise an artist SMK spells another way would read as SMK holding nothing."""
    asked: list[httpx.Request] = []

    found = a_finder(asked=asked).find_images(ImageQuery(title="Interior", artist="V. Hammershoi"))

    assert searches_made(asked) == [("Interior V Hammershoi", ("titles", "creator")), ("Interior", ("titles",))]
    assert len(found) == 10


def test_another_artists_object_among_the_hits_is_reported_as_theirs_and_refused_by_the_identity_check():
    """Three of the hits for "Interior" are titled exactly so, by three artists; one is the work asked for."""
    asked: list[httpx.Request] = []
    finder = a_finder(asked=asked)
    query = ImageQuery(title="Interior", artist="Willy Ørskov")

    by_artist = {image.url.rsplit("/", 1)[1]: image.artist for image in finder.find_images(query)}
    assert by_artist["KMS7121"] == "Willy Ørskov"
    assert by_artist["KMS2094"] == "Arne Kavli"

    profile = QualityProfile(minimum_long_edge_px=DEFAULT_QUALITY_MINIMUM_PX)
    resolution = PhaseTwoEngine(ImageSourcePool([finder]), profile=profile).resolve(query)
    assert [entry.found.url for entry in resolution.instances] == ["https://open.smk.dk/artwork/image/KMS7121"]
    assert UnresolvedReason.IDENTITY_REFUSED in resolution.refusals


def test_the_search_reads_the_words_of_a_title_and_never_its_punctuation():
    asked: list[httpx.Request] = []

    a_finder(asked=asked).find_images(ImageQuery(title='Interior. "An Old Stove" [study]'))

    assert searches_made(asked) == [("Interior An Old Stove study", ("titles",))]


def test_a_title_with_no_words_cannot_be_asked_of_smk():
    with pytest.raises(ImageQueryUnanswerable):
        a_finder().find_images(ImageQuery(title="…"))


def test_a_search_that_matches_nothing_finds_nothing():
    assert a_finder().find_images(ImageQuery(title="zzqxv")) == []


def test_an_answer_of_more_than_ten_objects_is_read_ten_deep():
    many = fixture("search_title_interior.json")
    many["items"] = many["items"] + many["items"][:5]
    searches = {("Interior", ("titles",)): httpx.Response(200, json=many)}

    assert len(a_finder(searches=searches).find_images(ImageQuery(title="Interior"))) == 10


def test_a_hit_whose_page_is_not_a_page_of_its_object_is_skipped():
    """Reported under a page the reader would read to another object, or to none."""
    hits = fixture("search_interior_vilhelm_hammershoi.json")
    hits["items"][0] = {**hits["items"][0], "frontend_url": "https://open.smk.dk/artwork/image/KMS1"}
    hits["items"][1] = {**hits["items"][1], "frontend_url": "https://example.com/artwork/image/KMS7444"}
    searches = {("Interior Vilhelm Hammershøi", ("titles", "creator")): httpx.Response(200, json=hits)}

    found = a_finder(searches=searches).find_images(ImageQuery(title="Interior", artist="Vilhelm Hammershøi"))

    assert [image.url.rsplit("/", 1)[1] for image in found] == ["KMS7246", "KKS9475", "KMS3696"]


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(200, json={"found": "3", "items": []}),
        httpx.Response(200, json={"found": 3, "items": "KMS1"}),
        httpx.Response(200, text="<html>maintenance</html>"),
        httpx.Response(403),
        httpx.Response(429),
        httpx.Response(503),
        httpx.Response(301, headers={"Location": "http://10.0.0.1/"}),
    ],
    ids=["found-not-a-number", "items-not-a-list", "not-json", "forbidden", "too-many", "unavailable", "redirect"],
)
def test_a_search_answer_that_is_not_a_search_could_not_be_asked(answer):
    searches = {("Interior", ("titles",)): answer}

    with pytest.raises(ImageSearchFailure):
        a_finder(searches=searches).find_images(ImageQuery(title="Interior"))


def test_a_network_failure_could_not_be_asked():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ImageSearchFailure, match="Could not search"):
        SmkFinder(user_agent="t", transport=httpx.MockTransport(handler)).find_images(ImageQuery(title="Interior"))


# -- what an object yields ---------------------------------------------------------------


@pytest.mark.parametrize("page", [ENGLISH_COPYRIGHT_PAGE, DANISH_COPYRIGHT_PAGE])
def test_an_in_copyright_object_is_found_and_recorded_as_in_copyright(page):
    """SMK's own page on the use of its material, in whichever language it was asked."""
    salon = WorkPage("https://open.smk.dk/artwork/image/KKS2020-3/16")
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [salon]})

    (image,) = a_finder(registry, objects={"KKS2020-3/16": answer_with("KKS2020-3/16", rights=page)}).find_images(
        ImageQuery(title="Salon", qid=TREE_TRUNKS_ITEM)
    )

    assert image.url == salon
    assert (image.title, image.artist) == ("Salon", "Al Masson")
    assert (image.estimated_width, image.estimated_height) == (6296, 4370)
    assert image.rights_status is RightsStatus.IN_COPYRIGHT


@pytest.mark.parametrize(
    "changes",
    [
        {"rights": "https://creativecommons.org/licenses/by/4.0/"},
        {"rights": None},
        {"public_domain": None, "rights": ENGLISH_COPYRIGHT_PAGE},
    ],
    ids=["another-licence", "no-rights", "public-domain-unsaid"],
)
def test_a_rights_statement_never_seen_is_recorded_unknown_and_still_found(changes):
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [WorkPage("https://open.smk.dk/artwork/image/KKS2020-3/16")]})

    (image,) = a_finder(registry, objects={"KKS2020-3/16": answer_with("KKS2020-3/16", **changes)}).find_images(
        ImageQuery(title="Salon", qid=TREE_TRUNKS_ITEM)
    )

    assert image.rights_status is RightsStatus.UNKNOWN


def test_a_public_domain_object_is_public_domain_whatever_its_rights_page_says():
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [FRAGMENT_PAGE]})
    answer = answer_with("KMS8010", rights=ENGLISH_COPYRIGHT_PAGE)

    (image,) = a_finder(registry, objects={"KMS8010": answer}).find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM))

    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN


@pytest.mark.parametrize(
    "changes",
    [
        {"image_native": "https://example.com/KMS8010.jpg"},
        {"image_native": "https://iip.smk.dk/iiif/jp2/x/full/full/0/native.jpg"},
        {"image_native": "https://api.smk.dk/api/v1/art/?object_number=KMS8010"},
    ],
    ids=["another-host", "smk-but-not-the-api", "the-api-but-not-an-image"],
)
def test_an_image_named_off_the_apis_image_paths_is_not_offered_or_read(changes):
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [FRAGMENT_PAGE]})

    found = a_finder(registry, asked, objects={"KMS8010": answer_with("KMS8010", **changes)}).find_images(
        ImageQuery(title="x", qid=TREE_TRUNKS_ITEM)
    )

    assert found == []
    assert {r.url.host for r in asked} == {"api.smk.dk"}


def test_an_object_smk_says_has_no_image_is_not_one_whatever_url_it_names():
    """`has_image` is SMK's own word, read before the URL beside it."""
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [FRAGMENT_PAGE]})
    answer = answer_with("KMS8010", has_image=False)

    assert a_finder(registry, objects={"KMS8010": answer}).find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM)) == []
    assert a_reader(objects={"KMS8010": answer}).read(FRAGMENT_PAGE).kind is LocatorKind.NONE


def test_an_item_recording_more_than_ten_smk_pages_reads_ten_objects():
    asked: list[httpx.Request] = []
    pages = [WorkPage(f"https://open.smk.dk/artwork/image/KMS{n}") for n in range(1, 13)]

    a_finder(FakeRegistry(pages={TREE_TRUNKS_ITEM: pages}), asked).find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM))

    read = objects_read(asked)
    assert len(read) == len(set(read)) == 10


def test_an_object_with_no_image_url_is_not_an_image():
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [FRAGMENT_PAGE]})
    answer = answer_with("KMS8010", image_native=None)

    assert a_finder(registry, objects={"KMS8010": answer}).find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM)) == []


def test_a_preview_named_off_the_thumbnail_host_is_not_offered():
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [FRAGMENT_PAGE]})
    answer = answer_with("KMS8010", image_thumbnail="https://example.com/thumb.jpg")

    (image,) = a_finder(registry, objects={"KMS8010": answer}).find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM))

    assert image.preview_url is None


@pytest.mark.parametrize(
    "answer",
    [
        answer_with("KMS1"),
        httpx.Response(200, json={"items": [record("KMS8010"), record("KMS1")]}),
        httpx.Response(200, json={"message": "maintenance"}),
        httpx.Response(200, text="<html>challenge</html>"),
        httpx.Response(404, json={"message": "Not found"}),
        httpx.Response(500),
    ],
    ids=["another-objects-record", "two-records", "no-items", "not-json", "404", "500"],
)
def test_an_object_answer_that_is_not_the_record_asked_for_could_not_be_asked(answer):
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [FRAGMENT_PAGE]})

    with pytest.raises(ImageSearchFailure):
        a_finder(registry, objects={"KMS8010": answer}).find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM))


def test_an_object_number_is_matched_as_smk_matches_it_without_regard_to_case():
    """Measured: `object_number=kms1` answers KMS1."""
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [WorkPage("https://open.smk.dk/artwork/image/kms1")]})

    (image,) = a_finder(registry).find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM))

    assert image.url == "https://open.smk.dk/artwork/image/kms1"


def search_hit(number: str) -> dict:
    """A recorded search hit, which carries the whole record."""
    return next(item for item in fixture("search_title_interior.json")["items"] if item["object_number"] == number)


def test_an_object_with_no_iiif_image_offers_its_one_file_at_the_size_it_states():
    """Measured: KMS7121's only file is 1229 x 1600, served from the API's thumbnail path, as the record says."""
    (image,) = [
        image
        for image in a_finder().find_images(ImageQuery(title="Interior", artist="Willy Ørskov"))
        if image.url.endswith("/KMS7121")
    ]

    assert (image.estimated_width, image.estimated_height) == (1229, 1600)
    assert image.preview_url == "https://api.smk.dk/api/v1/thumbnail/25f86678-d676-45cc-87e2-56b53f78e7a7.jpg"
    assert image.rights_status is RightsStatus.IN_COPYRIGHT


# -- previews ----------------------------------------------------------------------------


def test_a_preview_is_read_from_the_thumbnail_host_only_and_under_the_ceiling():
    thumb = "https://iip-thumb.smk.dk/iiif/jp2/5712m747g_KMS8010.tif.jp2/full/!1024,/0/default.jpg"
    big = a_transport(thumbnail=lambda r: httpx.Response(200, content=b"x" * 100))

    assert SmkFinder(user_agent="t", transport=big, preview_max_bytes=50).fetch_preview(thumb) is None
    roomy = SmkFinder(user_agent="t", transport=big)
    assert roomy.fetch_preview(thumb) == b"x" * 100
    assert roomy.fetch_preview("https://example.com/p.jpg") is None
    assert roomy.fetch_preview("https://iip.smk.dk/iiif/jp2/x/full/!1024,/0/default.jpg") is None


def test_a_preview_on_the_apis_thumbnail_path_is_read():
    """An object with no IIIF image names its preview there."""
    asked: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return httpx.Response(200, content=b"small")

    thumb = search_hit("KMS7121")["image_thumbnail"]
    assert SmkFinder(user_agent="t", transport=httpx.MockTransport(handler)).fetch_preview(thumb) == b"small"
    assert [str(r.url) for r in asked] == [thumb]


def test_a_thumbnail_redirect_is_not_followed_off_the_host():
    asked: list[httpx.Request] = []
    elsewhere = a_transport(asked, thumbnail=lambda r: httpx.Response(302, headers={"Location": "https://example.com/t.jpg"}))
    thumb = "https://iip-thumb.smk.dk/iiif/jp2/x/full/!1024,/0/default.jpg"

    assert SmkFinder(user_agent="t", transport=elsewhere).fetch_preview(thumb) is None
    assert {r.url.host for r in asked} == {"iip-thumb.smk.dk"}


# -- reading -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "number"),
    [
        ("https://open.smk.dk/artwork/image/KMS1", "KMS1"),
        ("https://collection.smk.dk/#/en/detail/KMS8010", "KMS8010"),
        ("https://open.smk.dk/artwork/image/KKS2020-3/16", "KKS2020-3/16"),
        ("https://api.smk.dk/api/v1/art?object_number=KMS1", "KMS1"),
    ],
)
def test_the_reader_reads_a_page_to_its_objects_original_in_copyright_or_not(url, number):
    locator = a_reader().read(url)

    assert locator.kind is LocatorKind.DIRECT
    assert locator.url == record(number)["image_native"]
    assert locator.url.startswith("https://api.smk.dk/api/v1/download/")


def test_the_reader_reads_an_object_with_no_iiif_image_to_its_one_file():
    hit = httpx.Response(200, json={"items": [search_hit("KMS7121")]})

    locator = a_reader(objects={"KMS7121": hit}).read("https://open.smk.dk/artwork/image/KMS7121")

    assert locator == FetchLocator.direct("https://api.smk.dk/api/v1/thumbnail/25f86678-d676-45cc-87e2-56b53f78e7a7.jpg")


def test_the_reader_says_none_for_an_object_with_no_image_and_one_smk_does_not_have():
    assert a_reader().read("http://collection.smk.dk/#/en/detail/KMSst28Ø").kind is LocatorKind.NONE
    assert a_reader().read("https://open.smk.dk/artwork/image/KMS99999999").kind is LocatorKind.NONE


def test_the_reader_refuses_a_url_it_does_not_claim_and_an_image_off_the_apis_image_paths():
    with pytest.raises(ImageSearchFailure):
        a_reader().read("https://www.smk.dk/udforsk-kunsten/soeg-i-smk/#/detail/KMS1")
    elsewhere = answer_with("KMS1", image_native="https://example.com/KMS1.jpg")
    with pytest.raises(ImageSearchFailure, match="off the API's image paths"):
        a_reader(objects={"KMS1": elsewhere}).read("https://open.smk.dk/artwork/image/KMS1")


# -- the plugin --------------------------------------------------------------------------


def test_the_factory_wires_the_deployments_registry_agent_and_preview_ceiling(monkeypatch):
    """Through the plugin's own factory, with values no default carries."""
    asked: list[httpx.Request] = []
    real = smk._client
    monkeypatch.setattr(
        smk,
        "_client",
        lambda transport: real(transport or a_transport(asked, thumbnail=lambda r: httpx.Response(200, content=b"x" * 100))),
    )
    registry = FakeRegistry(pages={TREE_TRUNKS_ITEM: [FRAGMENT_PAGE]})
    thumb = "https://iip-thumb.smk.dk/iiif/jp2/5712m747g_KMS8010.tif.jp2/full/!1024,/0/default.jpg"

    parts = PLUGIN.create(SourceContext(environ={}, user_agent="deployment/7", preview_max_bytes=50, registry=registry))
    (image,) = parts.finder.find_images(ImageQuery(title="x", qid=TREE_TRUNKS_ITEM))

    assert image.url == FRAGMENT_PAGE
    assert registry.pages_asked == [TREE_TRUNKS_ITEM]
    assert {r.headers["User-Agent"] for r in asked} == {"deployment/7"}
    assert parts.finder.fetch_preview(thumb) is None
    roomy = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1000, registry=None))
    assert roomy.finder.fetch_preview(thumb) == b"x" * 100


def test_the_plugin_never_declines_and_finds_by_item_only_with_a_registry():
    without = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=None))
    with_registry = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=FakeRegistry()))

    for parts in (without, with_registry):
        assert isinstance(parts, SourceParts)
        assert parts.finder is not None
        assert parts.finder.provider == "smk"
        assert parts.reader is not None
    assert PLUGIN.claims is claims
