"""The Rijksmuseum as an image source, driven through the real client against recorded answers.

Every file under `tests/fixtures/rijksmuseum/` is an answer the museum's ID, search
or image host gave on 2026-10-07 (`linked-art-findings.md` § The Rijksmuseum). The
object records are trimmed to the keys the plugin reads (`@context`, `id`, `type`,
`identified_by`'s names and identifiers, `produced_by` and `shows`), and the
VisualItems to their rights and `digitally_shown_by`; the full Night Watch record
runs to 97 KB of provenance and literature. DigitalObjects, `info.json`s and search
pages are as served.
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
from arrt.library.registry import ItemId, WorkPage
from arrt.library.services.quality import QualityProfile
from arrt.library.sources import FetchLocator, LocatorKind, SourceContext, SourceParts, rijksmuseum
from arrt.library.sources.rijksmuseum import PLUGIN, RijksmuseumFinder, RijksmuseumReader, claims, number_of
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import AcquisitionMethod, RightsStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "rijksmuseum"

ID = "https://id.rijksmuseum.nl/"
SEARCH = "/search/collection"
IMAGES = "https://iiif.micr.io/"

MILKMAID = WorkPage(f"{ID}200108369")
ELSKEN = WorkPage(f"{ID}200100873")
APPEL = WorkPage(f"{ID}200496110")
SAMSON = WorkPage(f"{ID}200109435")
ADORATION = WorkPage(f"{ID}200106080")
SLUIJTERS = WorkPage(f"{ID}200656394")
NO_IMAGE = WorkPage(f"{ID}200556187")
ISRAELS = WorkPage(f"{ID}200109400")
NIGHT_WATCH = WorkPage(f"{ID}200107928")
UNKNOWN = WorkPage(f"{ID}299999999")

MILKMAID_ITEM = ItemId("Q167605")
OTHER_ITEM = ItemId("Q90000001")


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _stems(prefix: str) -> dict[str, str]:
    """The recorded answers of one kind, by the URL each answer names itself by."""
    return {fixture(p.name)["id"]: p.name.removeprefix(prefix).removesuffix(".json") for p in FIXTURES.glob(f"{prefix}*.json")}


#: Record URL → fixture file, for objects, VisualItems and DigitalObjects, each from its own `id`.
LINKED = {
    url: f"{prefix}{stem}.json" for prefix in ("record_", "visualitem_", "digital_") for url, stem in _stems(prefix).items()
}
#: Image service → fixture stem, from each `info.json`'s own `id`.
INFOS = _stems("info_")

#: (title, creator) → the recorded search page.
SEARCHES = {
    ("The Milkmaid", "Johannes Vermeer"): "search_milkmaid.json",
    ("Two Young Women in the Snow", "Isaac Israëls"): "search_israels_accented.json",
    ("Two Young Women in the Snow", "Isaac Israels"): "search_israels_plain.json",
}


def service_of(stem: str) -> str:
    return fixture(f"info_{stem}.json")["id"]


def recorded(request: httpx.Request, *, linked=None, infos=None, searches=None, preview=None) -> httpx.Response:
    """The museum as it answered: records on its ID host, the search on its data host, images on its IIIF host."""
    url = request.url
    if url.host == "id.rijksmuseum.nl":
        return on_id_host(request, linked=linked)
    if url.host == "data.rijksmuseum.nl":
        return on_data_host(request, searches=searches)
    assert url.host == "iiif.micr.io", f"asked a host the plugin must not: {url}"
    if str(url).endswith("/info.json"):
        service = str(url).removesuffix("/info.json")
        if infos and service in infos:
            return infos[service]
        return httpx.Response(200, json=fixture(f"info_{INFOS[service]}.json"))
    return preview(request) if preview else httpx.Response(200, content=b"preview")


def on_id_host(request: httpx.Request, *, linked=None) -> httpx.Response:
    """Records by URL; a number the museum was not asked about answers 400, as an unknown one does."""
    assert request.headers["Accept"] == "application/ld+json"
    key = str(request.url)
    if linked and key in linked:
        return linked[key]
    if key in LINKED:
        return httpx.Response(200, json=fixture(LINKED[key]))
    return httpx.Response(400, json={"detail": "Bad Request"})


def on_data_host(request: httpx.Request, *, searches=None) -> httpx.Response:
    """The search, by (title, creator); a question not recorded finds nothing."""
    url = request.url
    assert url.path == SEARCH, f"asked a data path the plugin must not: {url}"
    assert url.params["imageAvailable"] == "true"
    asked = (url.params["title"], url.params["creator"])
    if searches and asked in searches:
        return searches[asked]
    if asked in SEARCHES:
        return httpx.Response(200, json=fixture(SEARCHES[asked]))
    return httpx.Response(200, json={**fixture("search_israels_accented.json"), "id": str(url)})


def a_transport(asked: list | None = None, **kwargs) -> httpx.MockTransport:
    """The recorded Rijksmuseum, under the plugin's own client policy: a test passes a transport, never a client."""

    def handler(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(request)
        return recorded(request, **kwargs)

    return httpx.MockTransport(handler)


def a_finder(registry=None, asked=None, **kwargs) -> RijksmuseumFinder:
    return RijksmuseumFinder(user_agent="arrt-tests/0", registry=registry, transport=a_transport(asked, **kwargs))


def a_reader(asked=None, **kwargs) -> RijksmuseumReader:
    return RijksmuseumReader(user_agent="arrt-tests/0", transport=a_transport(asked, **kwargs))


def pages(*urls: str, qid: ItemId = MILKMAID_ITEM) -> FakeRegistry:
    return FakeRegistry(pages={qid: [WorkPage(u) for u in urls]})


def find(*urls: str, qid: ItemId = MILKMAID_ITEM, asked=None, **kwargs):
    return a_finder(pages(*urls, qid=qid), asked, **kwargs).find_images(ImageQuery(title="x", qid=qid))


def search(title: str, artist: str | None, asked=None, **kwargs):
    return a_finder(None, asked, **kwargs).find_images(ImageQuery(title=title, artist=artist))


def changed(name: str, change) -> httpx.Response:
    """A recorded answer, changed in place by `change`."""
    answer = fixture(name)
    change(answer)
    return httpx.Response(200, json=answer)


def visual_item(stem: str) -> str:
    return fixture(f"record_{stem}.json")["shows"][0]["id"]


def digital(stem: str) -> str:
    return fixture(f"visualitem_{stem}.json")["digitally_shown_by"][0]["id"]


PROFILE = QualityProfile(minimum_long_edge_px=DEFAULT_QUALITY_MINIMUM_PX)


# -- claims ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "number"),
    [
        ("https://id.rijksmuseum.nl/200107928", "200107928"),
        ("http://id.rijksmuseum.nl/200107928", "200107928"),
        ("https://id.rijksmuseum.nl/20022176", "20022176"),
        ("https://id.rijksmuseum.nl/2002217", "2002217"),
    ],
)
def test_the_plugin_claims_an_object_record_and_reads_its_number(url, number):
    assert claims(url)
    assert number_of(url) == number


@pytest.mark.parametrize(
    "url",
    [
        "https://data.rijksmuseum.nl/200107928",
        "https://www.rijksmuseum.nl/nl/collectie/object/SK-C-5--3137deb45cd7765f9a76084a16c99544",
        "https://www.rijksmuseum.nl/en/collection/SK-C-5",
        "https://id.rijksmuseum.nl.example.com/200107928",
        "https://rijksmuseum.nl/200107928",
        "https://id.rijksmuseum.nl:8443/200107928",
        "https://someone@id.rijksmuseum.nl/200107928",
        "https://id.rijksmuseum.nl/200107928/",
        "https://id.rijksmuseum.nl/200107928?_profile=la",
        "https://id.rijksmuseum.nl/200107928#top",
        "https://id.rijksmuseum.nl/202107928x",
        "https://id.rijksmuseum.nl/123456",
        "https://id.rijksmuseum.nl/1234567890",
        "https://id.rijksmuseum.nl/500711199912110510799100",
        "ftp://id.rijksmuseum.nl/200107928",
        "https://[::1/",
    ],
)
def test_the_plugin_refuses_another_host_a_look_alike_and_another_shape(url):
    assert not claims(url)


# -- the finder, by Wikidata item --------------------------------------------------------


def test_a_work_whose_item_names_a_record_is_found_through_its_three_records_and_image_service():
    asked: list[httpx.Request] = []

    (image,) = find("https://www.moma.org/collection/works/1", MILKMAID, asked=asked)

    assert image.url == MILKMAID
    assert (image.provider, image.title, image.artist) == ("rijksmuseum", "The Milkmaid", "Johannes Vermeer")
    assert (image.estimated_width, image.estimated_height) == (4649, 5177)
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert image.preview_url == f"{service_of('milkmaid')}/full/!400,400/0/default.jpg"
    assert [str(r.url) for r in asked] == [
        MILKMAID,
        visual_item("milkmaid"),
        digital("milkmaid"),
        f"{service_of('milkmaid')}/info.json",
    ]
    assert {r.headers["User-Agent"] for r in asked} == {"arrt-tests/0"}


def test_an_original_larger_than_the_declared_area_is_found_as_tiles_and_a_smaller_one_as_one_request():
    """The Milkmaid is 24 MP and van der Elsken's photograph 10.6 MP, against a declared 17.55 MP."""
    (milkmaid,) = find(MILKMAID)
    (elsken,) = find(ELSKEN)

    assert milkmaid.acquisition_method is AcquisitionMethod.DEZOOMIFY
    assert elsken.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    assert (elsken.estimated_width, elsken.estimated_height) == (3200, 3327)


def test_the_record_as_the_item_spells_it_identifies_the_work_through_the_identity_check():
    """Driven through phase 2, the caller that reads the link: a URL of the plugin's own spelling would not count."""
    spelled = "http://id.rijksmuseum.nl/200108369"
    registry = pages(spelled)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=PROFILE, registry=registry)

    resolution = engine.resolve(ImageQuery(title="The Milkmaid", artist="Johannes Vermeer", qid=MILKMAID_ITEM))

    (entry,) = resolution.instances
    assert entry.found.url == spelled
    assert entry.confidence == CONFIDENT
    assert resolution.refusals == frozenset()


def test_another_artists_object_linked_by_mistake_is_refused_by_the_identity_check():
    """An item naming van der Elsken's photograph for a Hopper: the link stands, the artist does not."""
    registry = pages(ELSKEN, qid=OTHER_ITEM)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=PROFILE, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Nighthawks", artist="Edward Hopper", qid=OTHER_ITEM))

    assert list(resolution.instances) == []
    assert UnresolvedReason.IDENTITY_REFUSED in resolution.refusals


def test_an_in_copyright_work_the_museum_will_not_let_be_downloaded_is_still_found_and_recorded_in_copyright():
    (image,) = find(ELSKEN)

    assert (image.title, image.artist) == ("Man en vrouw bovenin de Tokyo Tower", "Ed van der Elsken")
    assert image.rights_status is RightsStatus.IN_COPYRIGHT
    assert "niet downloadbaar" in [s["content"] for s in fixture("digital_elsken_in_copyright.json")["referred_to_by"]]


@pytest.mark.parametrize(
    ("rights", "status"),
    [
        ("https://creativecommons.org/publicdomain/mark/1.0/", RightsStatus.PUBLIC_DOMAIN),
        ("http://creativecommons.org/publicdomain/zero/1.0/", RightsStatus.PUBLIC_DOMAIN),
        ("https://rightsstatements.org/vocab/InC/1.0/", RightsStatus.IN_COPYRIGHT),
        ("http://rightsstatements.org/vocab/InC-EDU/1.0/", RightsStatus.IN_COPYRIGHT),
        ("https://rightsstatements.org/vocab/NoC-US/1.0/", RightsStatus.UNKNOWN),
        ("https://rightsstatements.org/vocab/InC/1.0/extra", RightsStatus.UNKNOWN),
        ("https://creativecommons.org/licenses/by/4.0/", RightsStatus.UNKNOWN),
        (7, RightsStatus.UNKNOWN),
    ],
)
def test_the_visual_items_rights_are_read_for_what_they_say_and_never_gate(rights, status):
    def restate(item):
        item["subject_to"][0]["classified_as"][0]["id"] = rights

    restated = changed("visualitem_milkmaid.json", restate)
    (image,) = find(MILKMAID, linked={visual_item("milkmaid"): restated})

    assert image.rights_status is status


def test_a_visual_item_stating_no_rights_is_unknown_and_still_found():
    def unstate(item):
        del item["subject_to"]

    (image,) = find(MILKMAID, linked={visual_item("milkmaid"): changed("visualitem_milkmaid.json", unstate)})

    assert image.rights_status is RightsStatus.UNKNOWN


# -- the maker ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("page", "artist"),
    [
        (MILKMAID, "Johannes Vermeer"),
        (APPEL, "Karel Appel"),
        (ISRAELS, "Isaac Israels"),
        (SAMSON, "attributed to Rembrandt van Rijn"),
        (ADORATION, None),
        (SLUIJTERS, "Jan Sluijters"),
    ],
)
def test_the_maker_is_the_museums_with_its_attribution_and_without_its_evidence(page, artist):
    """Inline (Vermeer); assigned on evidence (Appel signed it, Israels' name is on it); assigned
    under an attribution (Samson); an unknown hand; and a poster whose second part is its publisher."""
    (image,) = find(page)

    assert image.artist == artist


def test_evidence_is_dropped_once_so_a_name_with_its_own_parenthesis_keeps_it():
    def bruegel(record):
        statement = next(
            s for s in record["produced_by"]["part"][0]["referred_to_by"] if s["content"] == "Karel Appel (signed by artist)"
        )
        statement["content"] = "Pieter Bruegel (I) (mentioned on object)"

    (image,) = find(APPEL, linked={APPEL: changed("record_appel_signed.json", bruegel)})

    assert image.artist == "Pieter Bruegel (I)"


def test_a_part_naming_only_the_design_a_print_is_after_names_no_maker_and_the_next_part_is_read():
    """A print after another's design records that design in a part of its own (measured third on 200124675)."""

    def design_first(record):
        after = {
            "type": "Production",
            "assigned_by": [
                {
                    "type": "AttributeAssignment",
                    "assigned": [{"id": f"{ID}2103429", "type": "Person"}],
                    "assigned_property": "influenced_by",
                    "classified_as": [{"id": "http://vocab.getty.edu/aat/300404286", "type": "Type"}],
                }
            ],
            "referred_to_by": [
                {
                    "type": "LinguisticObject",
                    "content": "after design by Rembrandt van Rijn",
                    "classified_as": [{"id": "http://vocab.getty.edu/aat/300435417", "type": "Type"}],
                }
            ],
        }
        record["produced_by"]["part"].insert(0, after)

    (image,) = find(APPEL, linked={APPEL: changed("record_appel_signed.json", design_first)})

    assert image.artist == "Karel Appel"


def test_a_maker_part_with_no_name_statement_is_no_artist_rather_than_a_later_parts():
    """Sluijters' publisher part states its name only as a role line, never as a name."""

    def designer_unstated(record):
        record["produced_by"]["part"][0]["referred_to_by"] = []

    (image,) = find(SLUIJTERS, linked={SLUIJTERS: changed("record_sluijters_poster_dutch_title.json", designer_unstated)})

    assert image.artist is None


def test_a_maker_statement_only_in_dutch_is_read_and_a_part_with_none_is_no_artist():
    def dutch_only(record):
        part = record["produced_by"]["part"][0]
        part["referred_to_by"] = [s for s in part["referred_to_by"] if "toegeschreven" in s["content"]]

    def silent(record):
        record["produced_by"]["part"][0]["referred_to_by"] = []

    (dutch,) = find(SAMSON, linked={SAMSON: changed("record_samson_attributed.json", dutch_only)})
    (none,) = find(SAMSON, linked={SAMSON: changed("record_samson_attributed.json", silent)})

    assert dutch.artist == "toegeschreven aan Rembrandt van Rijn"
    assert none.artist is None


def test_an_inline_maker_is_named_in_english_where_the_record_has_english():
    def dutch_first(record):
        person = record["produced_by"]["part"][0]["carried_out_by"][0]
        person["notation"] = [{"@language": "nl", "@value": "Jan Vermeer"}, {"@language": "en", "@value": "Johannes Vermeer"}]

    def dutch_only(record):
        person = record["produced_by"]["part"][0]["carried_out_by"][0]
        person["notation"] = [{"@language": "nl", "@value": "Jan Vermeer"}]

    (english,) = find(MILKMAID, linked={MILKMAID: changed("record_milkmaid.json", dutch_first)})
    (dutch,) = find(MILKMAID, linked={MILKMAID: changed("record_milkmaid.json", dutch_only)})

    assert (english.artist, dutch.artist) == ("Johannes Vermeer", "Jan Vermeer")


def test_an_attribution_written_in_parentheses_is_kept_where_evidence_would_be_dropped():
    """The museum classifies "possibly" (aat:300435722) as an attribution, and writes it after the name."""

    def possibly(record):
        part = record["produced_by"]["part"][0]
        part["assigned_by"][0]["classified_as"] = [{"id": "http://vocab.getty.edu/aat/300435722", "type": "Type"}]
        for statement in part["referred_to_by"]:
            statement["content"] = statement["content"].replace("(signed by artist)", "(possibly)")

    (image,) = find(APPEL, linked={APPEL: changed("record_appel_signed.json", possibly)})

    assert image.artist == "Karel Appel (possibly)"


def test_an_attributed_work_is_refused_by_the_identity_check_as_not_certainly_the_masters():
    """Even on the page the item records: an attribution is another name than the master's."""
    registry = pages(SAMSON, qid=OTHER_ITEM)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=PROFILE, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Samson and Delilah", artist="Rembrandt van Rijn", qid=OTHER_ITEM))

    assert list(resolution.instances) == []
    assert UnresolvedReason.IDENTITY_REFUSED in resolution.refusals


# -- the title ---------------------------------------------------------------------------


def test_by_item_the_preferred_english_title_is_reported_and_a_dutch_only_one_when_that_is_all():
    (milkmaid,) = find(MILKMAID)
    (poster,) = find(SLUIJTERS)

    assert milkmaid.title == "The Milkmaid"
    assert poster.title == "Affiche voor Zegepraal door Israël Querido"


def test_a_search_reports_the_records_title_equal_to_the_one_asked_else_the_preferred_english_one():
    (english,) = search("The Milkmaid", "Johannes Vermeer")
    (dutch,) = search(
        "het  melkmeisje",
        "Johannes Vermeer",
        searches={("het melkmeisje", "Johannes Vermeer"): httpx.Response(200, json=fixture("search_milkmaid.json"))},
    )

    assert english.title == "The Milkmaid"
    assert dutch.title == "Het melkmeisje"


def test_a_record_with_no_preferred_title_reports_its_first_title():
    def unpreferred(record):
        for name in record["identified_by"]:
            name["classified_as"] = [k for k in name.get("classified_as", []) if not k["id"].endswith("300404670")]

    (image,) = find(MILKMAID, linked={MILKMAID: changed("record_milkmaid.json", unpreferred)})

    first = next(n["content"] for n in fixture("record_milkmaid.json")["identified_by"] if n["type"] == "Name")
    assert image.title == first
    assert first != "The Milkmaid"


def test_a_record_giving_no_title_could_not_be_asked():
    def untitled(record):
        record["identified_by"] = [n for n in record["identified_by"] if n["type"] != "Name"]

    with pytest.raises(ImageSearchFailure, match="no title"):
        find(MILKMAID, linked={MILKMAID: changed("record_milkmaid.json", untitled)})


# -- holding nothing ---------------------------------------------------------------------


def test_an_object_with_no_image_holds_nothing_and_the_rest_stands(caplog):
    with caplog.at_level(logging.INFO):
        found = find(NO_IMAGE, ELSKEN)

    assert [image.url for image in found] == [ELSKEN]
    assert any(getattr(r, "event", None) == "rijksmuseum.no_image" for r in caplog.records)


def test_an_object_with_no_visual_item_holds_nothing():
    def unshown(record):
        del record["shows"]

    assert find(MILKMAID, ELSKEN, linked={MILKMAID: changed("record_milkmaid.json", unshown)})[0].url == ELSKEN


@pytest.mark.parametrize("status", [400, 404])
def test_an_item_whose_numbers_the_museum_does_not_know_is_searched_for(status, caplog):
    asked: list[httpx.Request] = []
    finder = a_finder(pages(UNKNOWN), asked, linked={UNKNOWN: httpx.Response(status, text="no")})

    with caplog.at_level(logging.WARNING):
        (image,) = finder.find_images(ImageQuery(title="The Milkmaid", artist="Johannes Vermeer", qid=MILKMAID_ITEM))

    assert image.url == MILKMAID
    assert [r.url.host for r in asked][:2] == ["id.rijksmuseum.nl", "data.rijksmuseum.nl"]
    assert any(getattr(r, "event", None) == "rijksmuseum.object_not_found" for r in caplog.records)


def test_an_item_naming_no_record_is_searched_for():
    asked: list[httpx.Request] = []
    finder = a_finder(pages("https://www.getty.edu/art/collection/object/103JNH"), asked)

    (image,) = finder.find_images(ImageQuery(title="The Milkmaid", artist="Johannes Vermeer", qid=MILKMAID_ITEM))

    assert image.url == MILKMAID
    assert asked[0].url.host == "data.rijksmuseum.nl"


def test_two_spellings_of_one_object_read_it_once_under_the_first_the_registry_gives():
    asked: list[httpx.Request] = []
    spelled = "http://id.rijksmuseum.nl/200108369"

    (image,) = find(spelled, MILKMAID, asked=asked)

    assert image.url == spelled
    assert [str(r.url) for r in asked].count(MILKMAID) == 1


def test_an_item_naming_more_than_ten_records_reads_ten():
    asked: list[httpx.Request] = []
    many = [f"{ID}2000000{n:02d}" for n in range(12)]

    with pytest.raises(ImageQueryUnanswerable):
        find(*many, asked=asked)

    assert len([r for r in asked if r.url.host == "id.rijksmuseum.nl"]) == 10


def test_a_registry_that_cannot_be_asked_is_a_search_that_could_not_be_asked():
    registry = FakeRegistry(failing=True)

    with pytest.raises(ImageSearchFailure, match="Wikidata could not be asked"):
        a_finder(registry).find_images(ImageQuery(title="x", qid=MILKMAID_ITEM))


# -- the search --------------------------------------------------------------------------


def test_a_work_is_searched_for_by_its_title_and_maker_among_objects_with_an_image():
    asked: list[httpx.Request] = []

    (image,) = search("The  Milkmaid", " Johannes Vermeer", asked=asked)

    assert image.url == MILKMAID
    (question,) = [r for r in asked if r.url.host == "data.rijksmuseum.nl"]
    assert dict(question.url.params) == {"title": "The Milkmaid", "creator": "Johannes Vermeer", "imageAvailable": "true"}


def test_a_maker_with_accents_that_finds_nothing_is_asked_once_more_without_them_and_identity_accepts_it():
    """Driven through phase 2: the museum spells him "Isaac Israels", Wikidata "Isaac Israëls"."""
    asked: list[httpx.Request] = []
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(None, asked)]), profile=PROFILE, registry=FakeRegistry())

    resolution = engine.resolve(ImageQuery(title="Two Young Women in the Snow", artist="Isaac Israëls"))

    (entry,) = resolution.instances
    assert (entry.found.url, entry.found.artist) == (ISRAELS, "Isaac Israels")
    assert [r.url.params["creator"] for r in asked if r.url.host == "data.rijksmuseum.nl"] == ["Isaac Israëls", "Isaac Israels"]


def test_a_plain_maker_that_finds_nothing_is_asked_once():
    asked: list[httpx.Request] = []

    assert search("Two Young Women in the Snow", "Isaac Israels Junior", asked=asked) == []
    assert len(asked) == 1


def test_an_accented_maker_that_finds_something_is_not_asked_again():
    asked: list[httpx.Request] = []
    plain = httpx.Response(200, json=fixture("search_israels_plain.json"))

    search(
        "Two Young Women in the Snow",
        "Isaac Israëls",
        asked=asked,
        searches={("Two Young Women in the Snow", "Isaac Israëls"): plain},
    )

    assert [r.url.params["creator"] for r in asked if r.url.host == "data.rijksmuseum.nl"] == ["Isaac Israëls"]


@pytest.mark.parametrize("artist", [None, "", "   "])
def test_a_work_with_no_maker_and_no_record_cannot_be_asked_of_the_museum(artist):
    asked: list[httpx.Request] = []

    with pytest.raises(ImageQueryUnanswerable, match="maker"):
        search("The Milkmaid", artist, asked=asked)
    assert asked == []


def test_a_blank_title_cannot_be_asked():
    with pytest.raises(ImageQueryUnanswerable, match="title"):
        search("  ", "Johannes Vermeer")


def test_a_search_reads_at_most_ten_hits():
    asked: list[httpx.Request] = []
    page = fixture("search_milkmaid.json")
    page["orderedItems"] = [{"id": MILKMAID, "type": "HumanMadeObject"}] * 12

    search(
        "The Milkmaid",
        "Johannes Vermeer",
        asked=asked,
        searches={("The Milkmaid", "Johannes Vermeer"): httpx.Response(200, json=page)},
    )

    assert [str(r.url) for r in asked].count(MILKMAID) == 10


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500, text="error"),
        httpx.Response(302, headers={"Location": "https://elsewhere.example/"}),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json={"type": "OrderedCollection", "orderedItems": []}),
        httpx.Response(200, json={"type": "OrderedCollectionPage", "orderedItems": "none"}),
        httpx.Response(
            200, json={"type": "OrderedCollectionPage", "orderedItems": [{"id": "https://elsewhere.example/200108369"}]}
        ),
        httpx.Response(200, json={"type": "OrderedCollectionPage", "orderedItems": [{"id": f"{ID}202107928x"}]}),
        httpx.Response(200, json={"type": "OrderedCollectionPage", "orderedItems": ["https://id.rijksmuseum.nl/200108369"]}),
    ],
)
def test_a_search_answer_that_is_not_a_page_of_the_museums_records_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure):
        search("The Milkmaid", "Johannes Vermeer", searches={("The Milkmaid", "Johannes Vermeer"): answer})


def test_a_network_failure_could_not_be_asked():
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    finder = RijksmuseumFinder(user_agent="t", registry=None, transport=httpx.MockTransport(down))

    with pytest.raises(ImageSearchFailure, match="Could not search"):
        finder.find_images(ImageQuery(title="The Milkmaid", artist="Johannes Vermeer"))


# -- the road and its hosts --------------------------------------------------------------


@pytest.mark.parametrize(
    ("which", "url"),
    [
        ("visual item", "https://elsewhere.example/202108369"),
        ("visual item", "https://id.rijksmuseum.nl.example.com/202108369"),
        ("visual item", "http://id.rijksmuseum.nl/202108369"),
        ("visual item", None),
        ("digital object", "https://data.rijksmuseum.nl/500711199912110510799100"),
    ],
)
def test_a_record_linking_off_the_museums_id_host_could_not_be_asked(which, url):
    if which == "visual item":

        def relink(record):
            record["shows"][0]["id"] = url

        linked = {MILKMAID: changed("record_milkmaid.json", relink)}
    else:

        def relink(item):
            item["digitally_shown_by"][0]["id"] = url

        linked = {visual_item("milkmaid"): changed("visualitem_milkmaid.json", relink)}

    asked: list[httpx.Request] = []
    with pytest.raises(ImageSearchFailure, match="off its ID host"):
        find(MILKMAID, asked=asked, linked=linked)
    assert all(r.url.host == "id.rijksmuseum.nl" for r in asked)


@pytest.mark.parametrize(
    "point",
    [
        "https://elsewhere.example/QkOGy/full/max/0/default.jpg",
        "https://iiif.micr.io.example.com/QkOGy/full/max/0/default.jpg",
        "http://iiif.micr.io/QkOGy/full/max/0/default.jpg",
        "https://iiif.micr.io/QkOGy/full/!400,400/0/default.jpg",
        "https://iiif.micr.io/QkOGy/../x/full/max/0/default.jpg",
        None,
    ],
)
def test_an_access_point_off_the_museums_image_host_or_of_another_shape_is_not_offered_or_read(point):
    def repoint(obj):
        obj["access_point"][0]["id"] = point

    asked: list[httpx.Request] = []
    linked = {digital("milkmaid"): changed("digital_milkmaid.json", repoint)}

    with pytest.raises(ImageSearchFailure, match="does not read"):
        find(MILKMAID, asked=asked, linked=linked)
    with pytest.raises(ImageSearchFailure, match="does not read"):
        a_reader(linked=linked).read(MILKMAID)
    assert not any(r.url.host == "iiif.micr.io" for r in asked)


def test_a_digital_object_with_no_access_point_could_not_be_asked():
    def pointless(obj):
        obj["access_point"] = []

    with pytest.raises(ImageSearchFailure):
        find(MILKMAID, linked={digital("milkmaid"): changed("digital_milkmaid.json", pointless)})


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        (MILKMAID, "Person"),
        (lambda: visual_item("milkmaid"), "HumanMadeObject"),
        (lambda: digital("milkmaid"), "VisualItem"),
    ],
)
def test_a_record_of_another_type_than_the_road_expects_could_not_be_asked(url, kind):
    url = url() if callable(url) else url
    stem = LINKED[url]

    def retype(record):
        record["type"] = kind

    with pytest.raises(ImageSearchFailure):
        find(MILKMAID, linked={url: changed(stem, retype)})


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500, text="error"),
        httpx.Response(303, headers={"Location": "https://www.rijksmuseum.nl/nl/collectie/object/x"}),
        httpx.Response(200, text="<html>"),
    ],
)
def test_a_record_answer_that_is_not_a_record_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure):
        find(MILKMAID, linked={MILKMAID: answer})
    with pytest.raises(ImageSearchFailure):
        find(MILKMAID, linked={visual_item("milkmaid"): answer})


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(
            200,
            json={
                "@context": "http://iiif.io/api/image/3/context.json",
                "id": "https://iiif.micr.io/other",
                "width": 1,
                "height": 1,
            },
        ),
        httpx.Response(500, text="error"),
        httpx.Response(200, json={"not": "an info.json"}),
    ],
)
def test_an_image_service_answer_that_is_not_this_images_could_not_be_asked(answer):
    with pytest.raises(ImageSearchFailure):
        find(MILKMAID, infos={service_of("milkmaid"): answer})
    with pytest.raises(ImageSearchFailure):
        a_reader(infos={service_of("milkmaid"): answer}).read(MILKMAID)


# -- previews ----------------------------------------------------------------------------


def test_a_preview_is_read_from_the_museums_image_host_only_and_under_the_ceiling():
    asked: list[httpx.Request] = []
    finder = RijksmuseumFinder(
        user_agent="t",
        registry=None,
        preview_max_bytes=10,
        transport=a_transport(asked, preview=lambda r: httpx.Response(200, content=b"x" * 10)),
    )
    preview = f"{service_of('milkmaid')}/full/!400,400/0/default.jpg"

    assert finder.fetch_preview(preview) == b"x" * 10
    assert finder.fetch_preview("https://elsewhere.example/QkOGy/full/!400,400/0/default.jpg") is None
    assert finder.fetch_preview("https://iiif.micr.io.example.com/QkOGy/full/!400,400/0/default.jpg") is None
    assert [str(r.url) for r in asked] == [preview]
    assert asked[0].headers["Accept"] == "image/*"


@pytest.mark.parametrize("answer", [httpx.Response(404, text="gone"), httpx.Response(200, content=b"x" * 11)])
def test_a_preview_that_cannot_be_read_is_none(answer):
    finder = RijksmuseumFinder(
        user_agent="t", registry=None, preview_max_bytes=10, transport=a_transport(preview=lambda r: answer)
    )

    assert finder.fetch_preview(f"{service_of('milkmaid')}/full/!400,400/0/default.jpg") is None


def test_a_preview_whose_connection_fails_is_none():
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    finder = RijksmuseumFinder(user_agent="t", registry=None, transport=httpx.MockTransport(down))

    assert finder.fetch_preview(f"{service_of('milkmaid')}/full/!400,400/0/default.jpg") is None


# -- the reader --------------------------------------------------------------------------


def test_the_reader_reads_a_record_through_its_three_records_to_one_request_for_an_original_within_the_area():
    asked: list[httpx.Request] = []

    locator = a_reader(asked).read(ELSKEN)

    assert locator == FetchLocator.direct(f"{service_of('elsken_in_copyright')}/full/max/0/default.jpg")
    assert [r.url.host for r in asked] == ["id.rijksmuseum.nl"] * 3 + ["iiif.micr.io"]
    assert not any(r.url.host == "www.rijksmuseum.nl" for r in asked)


@pytest.mark.parametrize(("page", "stem"), [(NIGHT_WATCH, "night_watch"), (MILKMAID, "milkmaid")])
def test_the_reader_reads_an_original_larger_than_the_declared_area_as_tiles(page, stem):
    """The Night Watch is 178 MP; the service declares 17.55 MP, and `TILE_MAX_PIXELS` bounds what tiling assembles."""
    assert a_reader().read(page) == FetchLocator.tiles(f"{service_of(stem)}/info.json")


def test_the_reader_says_none_for_an_unknown_number_and_an_object_with_no_image():
    assert a_reader().read(UNKNOWN).kind is LocatorKind.NONE
    assert a_reader(linked={UNKNOWN: httpx.Response(404, text="no")}).read(UNKNOWN).kind is LocatorKind.NONE
    assert a_reader().read(NO_IMAGE).kind is LocatorKind.NONE


def test_the_reader_refuses_a_url_it_does_not_claim_and_never_asks_for_it():
    asked: list[httpx.Request] = []

    with pytest.raises(ImageSearchFailure, match="not a Rijksmuseum object record"):
        a_reader(asked).read("https://www.rijksmuseum.nl/en/collection/SK-C-5")
    assert asked == []


# -- the plugin --------------------------------------------------------------------------


def test_the_factory_wires_the_deployments_registry_agent_and_preview_ceiling(monkeypatch):
    """Through the plugin's own factory, with values no default carries."""
    asked: list[httpx.Request] = []
    real = rijksmuseum._client
    monkeypatch.setattr(
        rijksmuseum,
        "_client",
        lambda transport: real(transport or a_transport(asked, preview=lambda r: httpx.Response(200, content=b"x" * 100))),
    )
    registry = pages(MILKMAID)
    preview = f"{service_of('milkmaid')}/full/!400,400/0/default.jpg"

    parts = PLUGIN.create(SourceContext(environ={}, user_agent="deployment/7", preview_max_bytes=50, registry=registry))
    (image,) = parts.finder.find_images(ImageQuery(title="x", qid=MILKMAID_ITEM))
    locator = parts.reader.read(ELSKEN)

    assert image.url == MILKMAID
    assert locator.kind is LocatorKind.DIRECT
    assert registry.pages_asked == [MILKMAID_ITEM]
    assert {r.headers["User-Agent"] for r in asked} == {"deployment/7"}
    assert parts.finder.fetch_preview(preview) is None
    roomy = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1000, registry=registry))
    assert roomy.finder.fetch_preview(preview) == b"x" * 100


def test_the_plugin_never_declines_and_searches_without_a_registry(monkeypatch):
    monkeypatch.setattr(rijksmuseum, "_client", lambda transport: httpx.Client(transport=a_transport()))
    without = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=None))

    assert isinstance(without, SourceParts)
    assert without.finder.provider == "rijksmuseum"
    assert without.reader is not None
    found = without.finder.find_images(ImageQuery(title="The Milkmaid", artist="Johannes Vermeer", qid=MILKMAID_ITEM))
    assert [i.url for i in found] == [MILKMAID]
    assert PLUGIN.claims is claims
