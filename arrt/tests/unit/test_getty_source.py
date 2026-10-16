"""The J. Paul Getty Museum as an image source, driven through the real client against recorded answers.

Every file under `tests/fixtures/getty/` is an answer the Getty's data or media host
gave on 2026-10-07 (`linked-art-findings.md`). The Linked Art records are trimmed
to the keys the plugin reads (`@context`, `id`, `type`, `_label`, `classified_as`,
`identified_by`, `produced_by`, and the page and manifest entries of `subject_of`);
the full records carry provenance and exhibition history that ran to 550 KB for one
painting. The `sparql_*.json` files are the endpoint's own answers to the plugin's
three questions, and the transport below answers each question from them.
"""

import json
import logging
import re
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
from arrt.library.sources import FetchLocator, LocatorKind, SourceContext, SourceParts, getty
from arrt.library.sources.getty import PLUGIN, GettyFinder, GettyReader, claims, slug_of
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import AcquisitionMethod, RightsStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "getty"

SPARQL = "/museum/collection/sparql"
OBJECTS = "https://data.getty.edu/museum/collection/object/"
PERSONS = "https://data.getty.edu/museum/collection/person/"
IMAGES = "https://media.getty.edu/iiif/image/"
MANIFESTS = "https://media.getty.edu/iiif/manifest/3/"
URN = "urn:getty-local:idm:object:slug/"

PAGE = "https://www.getty.edu/art/collection/object/"
IRISES_PAGE = WorkPage(f"{PAGE}103JNH")
BROCKHURST_PAGE = WorkPage(f"{PAGE}103R9G")
ARBUS_PAGE = WorkPage(f"{PAGE}10P1MS")
CARIANI_PAGE = WorkPage(f"{PAGE}1JAXFV")
ROCKY_BEAR_PAGE = WorkPage(f"{PAGE}10435K")
RUBENS_PAGE = WorkPage(f"{PAGE}103RBN")
LA_VILLE_PAGE = WorkPage(f"{PAGE}104430")
ARMLET_PAGE = WorkPage(f"{PAGE}107SAK")

IRISES_ITEM = ItemId("Q2282256")
OTHER_ITEM = ItemId("Q90000001")

LANGE = f"{PERSONS}d6446240-36e4-49d8-a9e7-bf0126c6cd95"
AZARI = f"{PERSONS}e543ada0-4fdc-4b01-8043-b123576ec4d4"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _stem(name: str, prefix: str) -> str:
    return name.removeprefix(prefix).removesuffix(".json")


def _uuid(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


#: Record uuid → fixture stem, each from the record's own `id`.
RECORDS = {_uuid(fixture(p.name)["id"]): _stem(p.name, "record_") for p in FIXTURES.glob("record_*.json")}
#: Manifest uuid → fixture stem, and image uuid → fixture stem, each from the recorded answer itself.
MANIFEST_FILES = {_uuid(fixture(p.name)["id"]): _stem(p.name, "manifest_") for p in FIXTURES.glob("manifest_*.json")}
INFO_FILES = {_uuid(fixture(p.name)["id"]): _stem(p.name, "info_") for p in FIXTURES.glob("info_*.json")}

#: Slug → record URL, as the endpoint answered for every slug recorded (and not for `ZZZZZZ`, which it does not know).
SLUGS = {
    row["urn"]["value"].removeprefix(URN): row["object"]["value"] for row in fixture("sparql_slugs.json")["results"]["bindings"]
}

#: A name, lowercased → the people the endpoint answered; and (people, words) → the objects.
PEOPLE = {
    "dorothea lange": [row["person"]["value"] for row in fixture("sparql_people_dorothea_lange.json")["results"]["bindings"]],
    "fédèle azari": [AZARI],
}
SEARCHES = {
    ((LANGE,), ("migrant", "mother")): [
        row["object"]["value"] for row in fixture("sparql_objects_lange_migrant_mother.json")["results"]["bindings"]
    ],
    ((AZARI,), ("the", "city")): [f"{OBJECTS}c6a909e7-ce1c-4331-8516-0ac40522fd22"],
}


def bindings(rows: list[dict[str, tuple[str, str]]]) -> httpx.Response:
    """A SPARQL JSON result in the endpoint's shape: each variable to its (type, value)."""
    vars_ = sorted({name for row in rows for name in row})
    return httpx.Response(
        200,
        json={
            "head": {"vars": vars_},
            "results": {"bindings": [{k: {"type": t, "value": v} for k, (t, v) in row.items()} for row in rows]},
        },
    )


def endpoint(query: str) -> httpx.Response:
    """The endpoint as it answered the plugin's three questions."""
    if "VALUES ?urn" in query:
        asked = re.findall(r'"urn:getty-local:idm:object:slug/([^"]*)"', query)
        return bindings([{"urn": ("literal", URN + s), "object": ("uri", SLUGS[s])} for s in asked if s in SLUGS])
    if "E21_Person" in query:
        (name,) = re.findall(r"= LCASE\((\".*\")\)\)", query)
        return bindings([{"person": ("uri", p)} for p in PEOPLE.get(json.loads(name).lower(), [])])
    if "VALUES ?person" in query:
        people = tuple(re.findall(r"<([^>]+)>", query.split("VALUES ?person", 1)[1].split("}", 1)[0]))
        words = tuple(json.loads(w) for w in re.findall(r"CONTAINS\(LCASE\(\?title\), (\"[^\"]*\")\)", query))
        return bindings([{"object": ("uri", o)} for o in SEARCHES.get((people, words), [])])
    raise AssertionError(f"a question the plugin does not ask: {query}")


def recorded(request: httpx.Request, *, records=None, sparql=None, **media) -> httpx.Response:
    """The Getty as it answered: the endpoint and records on its data host, the rest on its media host."""
    url = request.url
    if url.host != "data.getty.edu":
        return on_media_host(request, **media)
    if url.path == SPARQL:
        query = url.params["query"]
        return sparql(query) if sparql else endpoint(query)
    assert url.path.startswith("/museum/collection/object/"), f"asked a record the plugin must not: {url}"
    uuid = _uuid(url.path)
    if records and uuid in records:
        return records[uuid]
    return httpx.Response(200, json=fixture(f"record_{RECORDS[uuid]}.json"))


def on_media_host(request: httpx.Request, *, manifests=None, infos=None, preview=None) -> httpx.Response:
    """Manifests and `info.json`s by uuid, and previews."""
    url = request.url
    assert url.host == "media.getty.edu", f"asked a host the plugin must not: {url}"
    if url.path.startswith("/iiif/manifest/3/"):
        uuid = _uuid(url.path)
        if manifests and uuid in manifests:
            return manifests[uuid]
        return httpx.Response(200, json=fixture(f"manifest_{MANIFEST_FILES[uuid]}.json"))
    image, _, rest = url.path.removeprefix("/iiif/image/").partition("/")
    if rest == "info.json":
        if infos and image in infos:
            return infos[image]
        return httpx.Response(200, json=fixture(f"info_{INFO_FILES[image]}.json"))
    return preview(request) if preview else httpx.Response(200, content=b"preview")


def a_transport(asked: list | None = None, **kwargs) -> httpx.MockTransport:
    """The recorded Getty, under the plugin's own client policy: a test passes a transport, never a client."""

    def handler(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(request)
        return recorded(request, **kwargs)

    return httpx.MockTransport(handler)


def a_finder(registry=None, asked=None, **kwargs) -> GettyFinder:
    return GettyFinder(user_agent="arrt-tests/0", registry=registry, transport=a_transport(asked, **kwargs))


def a_reader(asked=None, **kwargs) -> GettyReader:
    return GettyReader(user_agent="arrt-tests/0", transport=a_transport(asked, **kwargs))


def pages(*urls: str, qid: ItemId = IRISES_ITEM) -> FakeRegistry:
    return FakeRegistry(pages={qid: [WorkPage(u) for u in urls]})


def find(*urls: str, qid: ItemId = IRISES_ITEM, asked=None, **kwargs):
    return a_finder(pages(*urls, qid=qid), asked, **kwargs).find_images(ImageQuery(title="x", qid=qid))


def search(title: str, artist: str | None, asked=None, **kwargs):
    return a_finder(None, asked, **kwargs).find_images(ImageQuery(title=title, artist=artist))


def changed(name: str, change) -> httpx.Response:
    """A recorded answer, changed in place by `change`."""
    answer = fixture(name)
    change(answer)
    return httpx.Response(200, json=answer)


def queries(asked: list[httpx.Request]) -> list[str]:
    return [r.url.params["query"] for r in asked if r.url.path == SPARQL]


def manifest_id(stem: str) -> str:
    return _uuid(fixture(f"manifest_{stem}.json")["id"])


def service_of(stem: str) -> str:
    return fixture(f"info_{stem}.json")["id"]


PROFILE = QualityProfile(minimum_long_edge_px=DEFAULT_QUALITY_MINIMUM_PX)


# -- claims ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://www.getty.edu/art/collection/object/103JNH", "103JNH"),
        ("http://www.getty.edu/art/collection/object/103JNH", "103JNH"),
        ("https://www.getty.edu/art/collection/object/1JAXFV/", "1JAXFV"),
    ],
)
def test_the_plugin_claims_an_object_page_and_reads_its_slug(url, slug):
    assert claims(url)
    assert slug_of(url) == slug


@pytest.mark.parametrize(
    "url",
    [
        "https://getty.edu/art/collection/object/103JNH",
        "https://www.getty.edu.example.com/art/collection/object/103JNH",
        "https://www.getty.edu:8443/art/collection/object/103JNH",
        "https://someone@www.getty.edu/art/collection/object/103JNH",
        "https://www.getty.edu/art/collection/objects/133675/",
        "https://www.getty.edu/art/collection/exhibition/103NPA",
        "https://www.getty.edu/art/collection/person/105PMK",
        "https://www.getty.edu/art/collection/object/103jnh",
        "https://www.getty.edu/art/collection/object/103JN",
        "https://www.getty.edu/art/collection/object/103JNHX",
        "https://www.getty.edu/art/collection/object/103JNH?x=1",
        "https://www.getty.edu/art/collection/object/103JNH#top",
        "ftp://www.getty.edu/art/collection/object/103JNH",
        "https://data.getty.edu/museum/collection/object/c88b3df0-de91-4f5b-a9ef-7b2b9a6d8abb",
        "https://[::1/",
    ],
)
def test_the_plugin_refuses_another_host_a_look_alike_and_another_shape(url):
    assert not claims(url)


# -- the finder, by Wikidata item --------------------------------------------------------


def test_a_work_whose_item_names_a_getty_page_is_found_from_the_record_and_manifest_under_that_page():
    asked: list[httpx.Request] = []

    (image,) = find("https://www.moma.org/collection/works/1", IRISES_PAGE, asked=asked)

    assert image.url == IRISES_PAGE
    assert (image.provider, image.title, image.artist) == ("getty", "Irises", "Vincent van Gogh")
    assert (image.estimated_width, image.estimated_height) == (9021, 7122)
    assert image.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert image.preview_url == f"{service_of('irises')}/full/!400,400/0/default.jpg"
    assert [r.url.host for r in asked] == ["data.getty.edu", "data.getty.edu", "media.getty.edu"]
    assert {r.headers["User-Agent"] for r in asked} == {"arrt-tests/0"}


def test_the_item_road_reads_the_first_canvas_the_front_not_the_back_or_the_frame():
    """*Irises* has three canvases: front, back, and its frame, which is another object."""
    (image,) = find(IRISES_PAGE)

    assert image.preview_url.startswith(service_of("irises"))
    assert service_of("irises").endswith("8c255d80-7382-46db-9fa8-892c0d37247e")


def test_the_page_as_the_item_spells_it_identifies_the_work_through_the_identity_check():
    """Driven through phase 2, the caller that reads the link: a page of the plugin's own spelling would not count."""
    spelled = "http://www.getty.edu/art/collection/object/103JNH/"
    registry = pages(spelled)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=PROFILE, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Irises", artist="Vincent van Gogh", qid=IRISES_ITEM))

    (entry,) = resolution.instances
    assert entry.found.url == spelled
    assert entry.confidence == CONFIDENT
    assert resolution.refusals == frozenset()


def test_another_artists_object_linked_by_mistake_is_refused_by_the_identity_check():
    """An item naming the Brockhurst's page for a Hopper: the link stands, the artist does not."""
    registry = pages(BROCKHURST_PAGE, qid=OTHER_ITEM)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=PROFILE, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Portrait of J. Paul Getty", artist="Edward Hopper", qid=OTHER_ITEM))

    assert list(resolution.instances) == []
    assert UnresolvedReason.IDENTITY_REFUSED in resolution.refusals


def test_an_in_copyright_work_served_in_full_is_found_at_full_size_and_recorded_in_copyright():
    (image,) = find(BROCKHURST_PAGE)

    assert (image.title, image.artist) == ("Portrait of J. Paul Getty", "Gerald L. Brockhurst")
    assert (image.estimated_width, image.estimated_height) == (3347, 4020)
    assert image.rights_status is RightsStatus.IN_COPYRIGHT


def test_an_in_copyright_work_kept_at_600_pixels_is_still_found_at_that_size():
    (image,) = find(ARBUS_PAGE)

    assert (image.estimated_width, image.estimated_height) == (573, 600)
    assert image.rights_status is RightsStatus.IN_COPYRIGHT


@pytest.mark.parametrize(
    ("rights", "status"),
    [
        ("http://creativecommons.org/publicdomain/zero/1.0/", RightsStatus.PUBLIC_DOMAIN),
        ("https://rightsstatements.org/vocab/InC/1.0/", RightsStatus.IN_COPYRIGHT),
        ("https://rightsstatements.org/vocab/InC-RUU/1.0/", RightsStatus.IN_COPYRIGHT),
        ("http://rightsstatements.org/vocab/InC-OW-EU/1.0/", RightsStatus.IN_COPYRIGHT),
        ("https://rightsstatements.org/vocab/NoC-US/1.0/", RightsStatus.UNKNOWN),
        ("https://rightsstatements.org/vocab/CNE/1.0/", RightsStatus.UNKNOWN),
        ("https://rightsstatements.org/vocab/InC/1.0/extra", RightsStatus.UNKNOWN),
        ("https://creativecommons.org/licenses/by/4.0/", RightsStatus.UNKNOWN),
        (7, RightsStatus.UNKNOWN),
    ],
)
def test_the_manifests_rights_are_read_for_what_they_say_and_never_gate(rights, status):
    def restate(manifest):
        manifest["rights"] = rights

    (image,) = find(IRISES_PAGE, manifests={manifest_id("irises"): changed("manifest_irises.json", restate)})

    assert image.rights_status is status


def test_a_manifest_stating_no_rights_is_unknown_and_still_found():
    (image,) = find(CARIANI_PAGE)

    assert "rights" not in fixture("manifest_cariani_no_rights.json")
    assert image.rights_status is RightsStatus.UNKNOWN
    assert image.artist == "Giovanni Busi (Cariani)"


def test_a_work_of_two_makers_reports_the_first_in_the_gettys_order():
    (image,) = find(ROCKY_BEAR_PAGE)

    assert image.artist == "Adolph F. Muhr"


def test_a_workshop_work_is_reported_with_the_gettys_attribution_before_the_name():
    (image,) = find(RUBENS_PAGE)

    assert image.artist == "Workshop of Peter Paul Rubens"
    assert (image.estimated_width, image.estimated_height) == (13445, 5055)


def test_an_attribution_after_the_name_is_kept_and_a_role_after_it_is_not():
    record = fixture("record_and_workshop_suffix.json")
    assert getty._artist(record) == "Master of Guillaume Lambert and workshop"

    (suffix,) = (e for e in record["produced_by"]["referred_to_by"] if e.get("content") == "and workshop")
    suffix["content"] = "maker, American"
    assert getty._artist(record) == "Master of Guillaume Lambert"


def test_an_unknown_hand_is_no_artist():
    record = fixture("record_irises.json")
    for entry in record["produced_by"]["referred_to_by"]:
        if entry.get("content") == "Vincent van Gogh":
            entry["content"] = "Unknown"

    assert getty._artist(record) is None


def test_names_are_read_from_the_record_with_their_accents_not_the_manifest_that_drops_them():
    raw = (FIXTURES / "manifest_la_ville_translated_title.json").read_text()

    (image,) = find(LA_VILLE_PAGE)

    assert "Fdle Azari" in raw
    assert "Fédèle" not in raw
    assert image.artist == "Fédèle Azari"


def test_by_item_the_gettys_preferred_title_is_reported():
    (image,) = find(LA_VILLE_PAGE)

    assert image.title == "La Ville"


def test_a_title_is_reported_only_when_it_equals_the_one_asked_else_the_preferred_one():
    record = fixture("record_la_ville_translated_title.json")
    names = record["identified_by"]
    # The translation first, so a rule that took the first title, or any title but the preferred one, says "The City".
    names.sort(key=lambda name: name.get("content") != "The City")

    assert getty._title(record, asked="The  CITY") == "The City"
    assert getty._title(record, asked="City") == "La Ville"
    assert getty._title(record, asked=None) == "La Ville"


def test_an_object_with_no_manifest_holds_nothing_and_the_rest_stands(caplog):
    asked: list[httpx.Request] = []
    with caplog.at_level(logging.INFO):
        found = find(ARMLET_PAGE, IRISES_PAGE, asked=asked)

    assert [image.url for image in found] == [IRISES_PAGE]
    assert any(getattr(r, "event", None) == "getty.no_manifest" for r in caplog.records)
    assert len(queries(asked)) == 1


def test_every_slug_an_item_names_is_mapped_in_one_question():
    asked: list[httpx.Request] = []

    found = find(IRISES_PAGE, BROCKHURST_PAGE, f"{PAGE}ZZZZZZ", asked=asked)

    (query,) = queries(asked)
    assert {"103JNH", "103R9G", "ZZZZZZ"} <= set(re.findall(r"slug/([0-9A-Z]{6})", query))
    assert [image.url for image in found] == [IRISES_PAGE, BROCKHURST_PAGE]


def test_two_spellings_of_one_object_read_it_once_under_the_first_the_registry_gives():
    asked: list[httpx.Request] = []

    found = find(f"{PAGE}103JNH/", IRISES_PAGE, asked=asked)

    assert [image.url for image in found] == [IRISES_PAGE]
    assert len([r for r in asked if "/object/" in r.url.path]) == 1


def test_an_item_naming_more_than_ten_getty_pages_maps_ten():
    asked: list[httpx.Request] = []
    slugs = [f"A{n:05d}" for n in range(12)]

    with pytest.raises(ImageQueryUnanswerable):
        # The Getty knows none of them, so the work is searched for, and it names no maker.
        find(*(f"{PAGE}{s}" for s in slugs), f"{PAGE}103JNH", asked=asked, sparql=lambda q: bindings([]))

    (query,) = queries(asked)
    assert re.findall(r"slug/([0-9A-Z]{6})", query) == sorted([*slugs, "103JNH"])[:10]


def test_an_item_whose_getty_pages_the_getty_does_not_know_is_searched_for(caplog):
    """A dropped ID says nothing about whether the Getty holds the work under another."""
    asked: list[httpx.Request] = []
    registry = pages(f"{PAGE}ZZZZZZ")
    with caplog.at_level(logging.INFO):
        found = a_finder(registry, asked).find_images(ImageQuery(title="The City", artist="Fédèle Azari", qid=IRISES_ITEM))

    assert [image.url for image in found] == [LA_VILLE_PAGE]
    assert len(queries(asked)) == 3
    assert any(getattr(r, "event", None) == "getty.object_not_found" for r in caplog.records)
    assert any(getattr(r, "by", None) == "maker and title" for r in caplog.records)


def test_an_item_naming_no_getty_page_is_searched_for():
    found = a_finder(pages("https://www.moma.org/collection/works/1")).find_images(
        ImageQuery(title="The City", artist="Fédèle Azari", qid=IRISES_ITEM)
    )

    assert [image.url for image in found] == [LA_VILLE_PAGE]


def test_a_registry_that_cannot_be_asked_is_a_search_that_could_not_be_asked():
    registry = FakeRegistry(failing=True)

    with pytest.raises(ImageSearchFailure, match="Wikidata could not be asked"):
        a_finder(registry).find_images(ImageQuery(title="Irises", artist="Vincent van Gogh", qid=IRISES_ITEM))


# -- the finder, by search ---------------------------------------------------------------


def test_a_work_is_searched_for_by_its_makers_name_then_its_title_words():
    asked: list[httpx.Request] = []

    found = search("Migrant Mother", "Dorothea Lange", asked=asked)

    assert [image.url for image in found] == [f"{PAGE}108E2E", f"{PAGE}104CF5"]
    assert [image.title for image in found] == [
        "Human Erosion in California (Migrant Mother)",
        "[Copy print of Migrant Mother, Nipomo, California]",
    ]
    assert {image.artist for image in found} == {"Dorothea Lange"}
    people, objects = queries(asked)
    assert 'LCASE("Dorothea Lange")' in people
    assert people.endswith("LIMIT 5")
    assert objects.endswith("LIMIT 10")
    assert LANGE in objects
    assert 'CONTAINS(LCASE(?title), "migrant")' in objects
    assert 'CONTAINS(LCASE(?title), "mother")' in objects


def test_a_search_reports_the_gettys_title_equal_to_the_one_asked_and_identity_accepts_it():
    """Getty prefers "La Ville" and records "The City": asked for the second, the second is reported."""
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(None)]), profile=PROFILE, registry=FakeRegistry())

    resolution = engine.resolve(ImageQuery(title="the  city", artist="Fédèle Azari"))

    (entry,) = resolution.instances
    assert entry.found.title == "The City"
    assert entry.found.url == LA_VILLE_PAGE


def test_a_maker_the_getty_does_not_know_finds_nothing_after_one_question():
    asked: list[httpx.Request] = []

    assert search("Irises", "Nobody Atall", asked=asked) == []
    assert len(queries(asked)) == 1


def test_a_work_with_no_maker_and_no_getty_page_cannot_be_asked_of_the_getty():
    with pytest.raises(ImageQueryUnanswerable, match="maker"):
        search("Irises", None)
    with pytest.raises(ImageQueryUnanswerable, match="maker"):
        search("Irises", "   ")


def test_a_title_with_no_words_cannot_be_asked():
    with pytest.raises(ImageQueryUnanswerable, match="no words"):
        search("—", "Dorothea Lange")


@pytest.mark.parametrize(
    "name",
    [
        'Dorothea" } } ; DROP ALL ; { "',
        "Dorothea \\u0022 Lange",
        "Dorothea\nLange",
    ],
)
def test_a_name_never_leaves_its_string_in_the_question(name):
    """The name is outside text, so the question is checked as the endpoint would parse its one literal."""
    asked: list[httpx.Request] = []

    search("Migrant Mother", name, asked=asked)

    query = queries(asked)[0]
    (literal,) = re.findall(r"= LCASE\((\".*\")\)\) \} LIMIT", query)
    assert json.loads(literal) == " ".join(name.split())


def test_a_search_hit_whose_page_is_not_the_shape_read_is_skipped(caplog):
    lange = _uuid(SLUGS["108E2E"])

    def no_page(record):
        record["subject_of"] = [s for s in record["subject_of"] if s.get("format") != "text/html"]

    with caplog.at_level(logging.WARNING):
        found = search("Migrant Mother", "Dorothea Lange", records={lange: changed("record_lange_migrant_mother.json", no_page)})

    assert [image.url for image in found] == [f"{PAGE}104CF5"]
    assert any(getattr(r, "event", None) == "getty.unexpected_page" for r in caplog.records)


@pytest.mark.parametrize(
    "answer",
    [
        bindings([{"person": ("uri", "https://evil.example/museum/collection/person/x")}]),
        bindings([{"person": ("uri", LANGE + "> } ?x ?y ?z . { <x")}]),
    ],
)
def test_an_endpoint_naming_someone_other_than_its_people_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure, match="other than its people"):
        search("Migrant Mother", "Dorothea Lange", sparql=lambda q: answer)


def test_an_endpoint_answering_a_search_with_another_hosts_record_could_not_be_asked():
    def sparql(query):
        if "E21_Person" in query:
            return endpoint(query)
        return bindings([{"object": ("uri", "https://data.getty.edu.example.com/museum/collection/object/x")}])

    with pytest.raises(ImageSearchFailure, match="other than its records"):
        search("Migrant Mother", "Dorothea Lange", sparql=sparql)


def test_an_endpoint_answering_ids_with_something_else_could_not_be_asked():
    answer = bindings([{"urn": ("literal", URN + "103JNH"), "object": ("uri", "https://elsewhere.example/object/1")}])

    with pytest.raises(ImageSearchFailure, match="other than its records"):
        find(IRISES_PAGE, sparql=lambda q: answer)


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(503, text="busy"),
        httpx.Response(429, text="slow down"),
        httpx.Response(302, headers={"Location": "https://elsewhere.example/"}),
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json=["a", "list"]),
        httpx.Response(200, json={"head": {}, "results": {}}),
        httpx.Response(200, json={"head": {}, "results": {"bindings": "rows"}}),
    ],
)
def test_an_endpoint_answer_that_is_not_a_result_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure):
        find(IRISES_PAGE, sparql=lambda q: answer)


def test_a_network_failure_could_not_be_asked():
    def failing(request):
        raise httpx.ConnectError("no route", request=request)

    finder = GettyFinder(user_agent="t", registry=pages(IRISES_PAGE), transport=httpx.MockTransport(failing))

    with pytest.raises(ImageSearchFailure, match="no route"):
        finder.find_images(ImageQuery(title="x", qid=IRISES_ITEM))


# -- what the finder refuses to read -----------------------------------------------------


@pytest.mark.parametrize(
    "manifest",
    [
        "https://media.getty.edu.example.com/iiif/manifest/3/53be857e-41e8-4198-b45d-2e0f52d3051b",
        "https://elsewhere.example/iiif/manifest/3/53be857e-41e8-4198-b45d-2e0f52d3051b",
        "http://media.getty.edu/iiif/manifest/3/53be857e-41e8-4198-b45d-2e0f52d3051b",
    ],
)
def test_a_record_naming_a_manifest_off_the_media_host_could_not_be_asked(manifest):
    irises = _uuid(SLUGS["103JNH"])

    def elsewhere(record):
        for subject in record["subject_of"]:
            for key in ("id", "has_format"):
                if "/iiif/manifest/3/" in str(subject.get(key)):
                    subject[key] = manifest

    with pytest.raises(ImageSearchFailure, match="off its media host"):
        find(IRISES_PAGE, records={irises: changed("record_irises.json", elsewhere)})


@pytest.mark.parametrize(
    "service",
    [
        "https://media.getty.edu.example.com/iiif/image/8c255d80-7382-46db-9fa8-892c0d37247e",
        "https://elsewhere.example/iiif/image/8c255d80-7382-46db-9fa8-892c0d37247e",
    ],
)
def test_an_image_service_off_the_gettys_image_host_is_not_offered_or_read(service):
    def elsewhere(manifest):
        manifest["items"][0]["items"][0]["items"][0]["body"]["service"][0]["id"] = service

    answer = {manifest_id("irises"): changed("manifest_irises.json", elsewhere)}

    with pytest.raises(ImageSearchFailure, match="does not read"):
        find(IRISES_PAGE, manifests=answer)
    with pytest.raises(ImageSearchFailure, match="off its image host"):
        a_reader(manifests=answer).read(IRISES_PAGE)


def test_a_canvas_whose_image_is_not_iiif_could_not_be_asked_by_the_finder_or_the_reader():
    def plain(manifest):
        del manifest["items"][0]["items"][0]["items"][0]["body"]["service"]

    answer = {manifest_id("irises"): changed("manifest_irises.json", plain)}

    with pytest.raises(ImageSearchFailure, match="does not read"):
        find(IRISES_PAGE, manifests=answer)
    with pytest.raises(ImageSearchFailure, match="not a IIIF image service"):
        a_reader(manifests=answer).read(IRISES_PAGE)


def test_a_first_canvas_longer_than_the_declared_limit_is_found_as_tiles():
    def huge(manifest):
        manifest["items"][0]["width"] = 30001

    (image,) = find(IRISES_PAGE, manifests={manifest_id("irises"): changed("manifest_irises.json", huge)})

    assert image.acquisition_method is AcquisitionMethod.DEZOOMIFY
    assert image.estimated_width == 30001


def test_only_the_gettys_own_records_and_people_are_read_or_written_into_a_question():
    """Each check sits where outside text meets a request, whatever its caller already checked."""
    asked: list[httpx.Request] = []
    client = getty._Getty(user_agent="t", transport=a_transport(asked))

    with pytest.raises(ImageSearchFailure, match="own people"):
        client.objects_by([LANGE, "https://elsewhere.example/person/1> } ?x ?y ?z . { <x"], ["mother"])
    with pytest.raises(ImageSearchFailure, match="not a Getty object record"):
        client.record("https://data.getty.edu.example.com/museum/collection/object/c88b3df0-de91-4f5b-a9ef-7b2b9a6d8abb")
    assert asked == []


def test_a_manifest_with_no_canvases_is_no_image():
    def empty(manifest):
        manifest["items"] = []

    assert find(IRISES_PAGE, manifests={manifest_id("irises"): changed("manifest_irises.json", empty)}) == []


def test_a_record_giving_no_title_could_not_be_asked():
    irises = _uuid(SLUGS["103JNH"])

    def untitled(record):
        record["identified_by"] = [n for n in record["identified_by"] if n.get("type") != "Name"]

    with pytest.raises(ImageSearchFailure, match="no title"):
        find(IRISES_PAGE, records={irises: changed("record_irises.json", untitled)})


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(404, text="gone"), httpx.Response(200, json={"not": "a manifest"}), httpx.Response(200, text="<html>")],
)
def test_a_manifest_answer_that_is_not_a_manifest_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure):
        find(IRISES_PAGE, manifests={manifest_id("irises"): answer})


# -- previews ----------------------------------------------------------------------------


def test_a_preview_is_read_from_the_gettys_image_host_only_and_under_the_ceiling():
    asked: list[httpx.Request] = []
    finder = GettyFinder(
        user_agent="t",
        registry=None,
        preview_max_bytes=10,
        transport=a_transport(asked, preview=lambda r: httpx.Response(200, content=b"x" * 10)),
    )
    preview = f"{service_of('irises')}/full/!400,400/0/default.jpg"

    assert finder.fetch_preview(preview) == b"x" * 10
    assert finder.fetch_preview("https://elsewhere.example/iiif/image/x/full/!400,400/0/default.jpg") is None
    assert finder.fetch_preview("https://media.getty.edu.example.com/iiif/image/x/full/max/0/default.jpg") is None
    assert [str(r.url) for r in asked] == [preview]
    assert asked[0].headers["Accept"] == "image/*"


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(404, text="gone"), httpx.Response(200, content=b"x" * 11)],
)
def test_a_preview_that_cannot_be_read_is_none(answer):
    finder = GettyFinder(user_agent="t", registry=None, preview_max_bytes=10, transport=a_transport(preview=lambda r: answer))

    assert finder.fetch_preview(f"{service_of('irises')}/full/!400,400/0/default.jpg") is None


# -- the reader --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("page", "stem"),
    [(IRISES_PAGE, "irises"), (BROCKHURST_PAGE, "brockhurst_in_copyright_zoom"), (RUBENS_PAGE, "rubens_workshop_of")],
)
def test_the_reader_reads_a_page_through_its_record_and_manifest_to_one_request_for_the_original(page, stem):
    asked: list[httpx.Request] = []

    locator = a_reader(asked).read(page)

    assert locator == FetchLocator.direct(f"{service_of(stem)}/full/max/0/default.jpg")
    assert [r.url.host for r in asked] == ["data.getty.edu", "data.getty.edu", "media.getty.edu", "media.getty.edu"]
    assert not any(r.url.host == "www.getty.edu" for r in asked)


def test_the_reader_reads_an_original_longer_than_the_declared_limit_as_tiles():
    def huge(info):
        info["width"] = 30001

    stem = "irises"
    locator = a_reader(infos={_uuid(service_of(stem)): changed(f"info_{stem}.json", huge)}).read(IRISES_PAGE)

    assert locator == FetchLocator.tiles(f"{service_of(stem)}/info.json")


def test_the_reader_says_none_for_an_unknown_slug_an_object_with_no_manifest_and_one_with_no_canvas():
    def empty(manifest):
        manifest["items"] = []

    assert a_reader().read(f"{PAGE}ZZZZZZ").kind is LocatorKind.NONE
    assert a_reader().read(ARMLET_PAGE).kind is LocatorKind.NONE
    assert (
        a_reader(manifests={manifest_id("irises"): changed("manifest_irises.json", empty)}).read(IRISES_PAGE).kind
        is LocatorKind.NONE
    )


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(
            200,
            json={
                "@context": "http://iiif.io/api/image/3/context.json",
                "id": "https://media.getty.edu/iiif/image/other",
                "width": 1,
                "height": 1,
            },
        ),
        httpx.Response(500, text="error"),
    ],
)
def test_an_image_service_answer_that_is_not_this_images_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure):
        a_reader(infos={_uuid(service_of("irises")): answer}).read(IRISES_PAGE)


def test_the_reader_refuses_a_url_it_does_not_claim_and_never_asks_for_it():
    asked: list[httpx.Request] = []

    with pytest.raises(ImageSearchFailure, match="not a Getty object page"):
        a_reader(asked).read("https://www.getty.edu/art/collection/objects/133675/")
    assert asked == []


# -- the plugin --------------------------------------------------------------------------


def test_the_factory_wires_the_deployments_registry_agent_and_preview_ceiling(monkeypatch):
    """Through the plugin's own factory, with values no default carries."""
    asked: list[httpx.Request] = []
    real = getty._client
    monkeypatch.setattr(
        getty,
        "_client",
        lambda transport: real(transport or a_transport(asked, preview=lambda r: httpx.Response(200, content=b"x" * 100))),
    )
    registry = pages(IRISES_PAGE)
    preview = f"{service_of('irises')}/full/!400,400/0/default.jpg"

    parts = PLUGIN.create(SourceContext(environ={}, user_agent="deployment/7", preview_max_bytes=50, registry=registry))
    (image,) = parts.finder.find_images(ImageQuery(title="x", qid=IRISES_ITEM))
    locator = parts.reader.read(IRISES_PAGE)

    assert image.url == IRISES_PAGE
    assert locator.kind is LocatorKind.DIRECT
    assert registry.pages_asked == [IRISES_ITEM]
    assert {r.headers["User-Agent"] for r in asked} == {"deployment/7"}
    assert parts.finder.fetch_preview(preview) is None
    roomy = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1000, registry=registry))
    assert roomy.finder.fetch_preview(preview) == b"x" * 100


def test_the_plugin_never_declines_and_searches_without_a_registry(monkeypatch):
    monkeypatch.setattr(getty, "_client", lambda transport: httpx.Client(transport=a_transport()))
    without = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=None))

    assert isinstance(without, SourceParts)
    assert without.finder.provider == "getty"
    assert without.reader is not None
    assert [i.url for i in without.finder.find_images(ImageQuery(title="The City", artist="Fédèle Azari", qid=IRISES_ITEM))] == [
        LA_VILLE_PAGE
    ]
    assert PLUGIN.claims is claims
