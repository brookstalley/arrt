"""navigart as an image source, driven through the real client against recorded answers.

Every file under `tests/fixtures/navigart/` is an answer navigart's API gave on
2026-10-06 (`navigart-api-findings.md`).
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
from arrt.library.services.quality import Fit, QualityProfile
from arrt.library.sources import FetchLocator, LocatorKind, SourceContext, SourceParts, navigart
from arrt.library.sources.navigart import (
    PLUGIN,
    PUBLICATIONS,
    Artwork,
    NavigartFinder,
    NavigartReader,
    api_url,
    artwork,
    claims,
    reading_order,
)
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import AcquisitionMethod, RightsStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "navigart"

#: (vault, artwork ID) → the recorded answer, HTTP 200. Any other artwork is
#: one the vault does not have, as navigart answers it.
ARTWORKS = {
    (6, "60000000002521"): "artwork_6_60000000002521_echelonnement.json",
    (14, "140000000027457"): "artwork_14_140000000027457_rythme_couleur_in_copyright.json",
    (14, "140000000046190"): "artwork_14_140000000046190_no_image.json",
    (18, "180000000000725"): "artwork_18_180000000000725_small_image.json",
    (25, "250000000002062"): "artwork_25_250000000002062_anonymous_then_dore.json",
    (701, "70000000000186"): "artwork_701_70000000000186_fenetre_a_tahiti.json",
}

#: Taeuber-Arp's *Échelonnement* at Grenoble (corpus row 14), as its item Q136030970 records it (P973).
ECHELONNEMENT_ITEM = ItemId("Q136030970")
ECHELONNEMENT_PAGE = "https://www.navigart.fr/grenoble/#/artwork/60000000002521"

#: Sonia Delaunay's *Rythme couleur n°1076* (corpus row 6), as its item's FNAC ID (P12213) builds it.
RYTHME_ITEM = ItemId("Q116464677")
RYTHME_PAGE = "https://www.navigart.fr/fnac/artwork/140000000027457"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def ua(vault: int, artwork_id: str) -> dict:
    return fixture(ARTWORKS[(vault, artwork_id)])["results"][0]["_source"]["ua"]


def recorded(request: httpx.Request, *, answers=None, image=None) -> httpx.Response:
    """navigart as it answered: artworks by vault and ID, images from its image host."""
    url = request.url
    if url.host == "images.navigart.fr":
        return image(request) if image else httpx.Response(200, content=b"jpeg")
    assert url.host == "api.navigart.fr", f"asked a host the plugin is not about: {url}"
    _, vault, collection, artwork_id = url.path.split("/")
    assert collection == "artworks", url
    key = (int(vault), artwork_id)
    answer = (answers or {}).get(key)
    if answer is not None:
        return answer
    if key in ARTWORKS:
        return httpx.Response(200, json=fixture(ARTWORKS[key]))
    return httpx.Response(404, json=fixture("not_found_404.json"))


def a_transport(asked: list | None = None, **kwargs) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(request)
        return recorded(request, **kwargs)

    return httpx.MockTransport(handler)


def a_finder(registry=None, asked=None, **kwargs) -> NavigartFinder:
    return NavigartFinder(user_agent="arrt-tests/0", registry=registry or FakeRegistry(), transport=a_transport(asked, **kwargs))


def a_reader(**kwargs) -> NavigartReader:
    return NavigartReader(user_agent="arrt-tests/0", transport=a_transport(**kwargs))


def answer_with(vault: int, artwork_id: str, *, artwork_changes=None, **ua_changes) -> httpx.Response:
    """The recorded artwork, with some of its fields changed."""
    body = fixture(ARTWORKS[(vault, artwork_id)])
    section = body["results"][0]["_source"]["ua"]
    section.update(ua_changes)
    section["artwork"].update(artwork_changes or {})
    return httpx.Response(200, json=body)


def artworks_read(asked: list[httpx.Request]) -> list[str]:
    return [r.url.path for r in asked if r.url.host == "api.navigart.fr"]


# -- claims ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "where"),
    [
        (ECHELONNEMENT_PAGE, (6, "60000000002521")),
        (RYTHME_PAGE, (14, "140000000027457")),
        ("https://www.navigart.fr/grenoble-collections#/artwork/60000000002521", (6, "60000000002521")),
        ("http://www.navigart.fr/macs/#/artwork/300000000001234", (30, "300000000001234")),
        ("https://www.navigart.fr/mamparis/#/artwork/180000000000755?note=no", (18, "180000000000755")),
        ("https://www.navigart.fr/lam/artwork/kees-van-dongen-femme-lippue-280000000000728", (28, "280000000000728")),
        ("https://www.navigart.fr/fnac/artwork/cecile-ferrere-la-vierge-140000000080312", (14, "140000000080312")),
        ("https://www.navigart.fr/MAMC-saint-etienne-collections/#/artwork/240000000001234", (24, "240000000001234")),
        ("https://www.navigart.fr/matisse_lecateau/artwork/70000000000186", (701, "70000000000186")),
        ("https://api.navigart.fr/701/artworks/70000000000186", (701, "70000000000186")),
    ],
)
def test_the_plugin_claims_each_shape_an_item_or_the_api_spells_and_reads_its_vault_and_artwork(url, where):
    """Every spelling here was found on a Wikidata item, or is the API's own (2026-10-06)."""
    assert claims(url)
    assert artwork(url) == Artwork(*where)


def test_the_vault_is_the_publications_not_the_ids_prefix():
    """`matisse_lecateau`'s IDs begin with 7, and vault 7 is nginx's 404: its vault is 701."""
    assert artwork("https://www.navigart.fr/matisse_lecateau/artwork/70000000000186").vault == 701
    assert not claims("https://api.navigart.fr/7/artworks/70000000000186")


@pytest.mark.parametrize(
    "url",
    [
        "https://navigart.fr.example.com/grenoble/#/artwork/60000000002521",
        "https://www.navigart.fr.example.com/grenoble/#/artwork/60000000002521",
        "https://example.com/grenoble/#/artwork/60000000002521",
        "https://www.navigart.fr:8443/grenoble/#/artwork/60000000002521",
        "ftp://www.navigart.fr/grenoble/#/artwork/60000000002521",
        # A publication not in the table stays a sighting.
        "https://www.navigart.fr/somewhere-new/#/artwork/60000000002521",
        "https://www.navigart.fr/Grenoble/#/artwork/60000000002521",
        # Pages that are not one artwork's.
        "https://www.navigart.fr/grenoble/",
        "https://www.navigart.fr/lam/artworks/authors/DECK%20Fran%C3%A7ois%E2%86%B9DECK%20Fran%C3%A7ois",
        "https://www.navigart.fr/grenoble/#/artworks?filters=authors:X",
        "https://www.navigart.fr/grenoble/artwork/60000000002521?page=2",
        "https://www.navigart.fr/grenoble/#/artwork/6000000000252",
        "https://www.navigart.fr/grenoble/#/artwork/abc",
        "https://www.navigart.fr/a/b/#/artwork/60000000002521",
        # The API, only for a known vault and only an artwork.
        "https://api.navigart.fr/999/artworks/9990000000001",
        "http://api.navigart.fr/6/artworks/60000000002521",
        "https://api.navigart.fr/6/artworks/60000000002521?x=1",
        "https://api.navigart.fr/6/artworks",
        "https://images.navigart.fr/1000/5E/76/5E76440.JPG",
        "https://www.mam.paris.fr/en/online-collections#/artwork/180000000000755",
        "not a url",
        "http://[::1",
    ],
)
def test_the_plugin_refuses_another_host_a_look_alike_an_unknown_publication_and_another_shape(url):
    assert not claims(url)


def test_the_api_url_is_one_the_plugin_claims_back():
    for slug, vault in PUBLICATIONS.items():
        where = Artwork(vault, "123456789012345")
        assert artwork(api_url(where)) == where, slug


# -- the artist's name -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("notice", "name"),
    [
        ("TAEUBER-ARP Sophie (TAEUBER Sophie-Henriette, dite)", "Sophie Taeuber-Arp"),
        ("DELAUNAY Sonia (STERN TERK Sarah Sophie, dite)", "Sonia Delaunay"),
        ("DORÉ Gustave", "Gustave Doré"),
        ("DE STAËL Nicolas", "Nicolas De Staël"),
        ("MATISSE Henri", "Henri Matisse"),
        ("MATTA (MATTA ECHAURREN Roberto Sebastián Antonio Matta Echaurren, dit)", "Matta"),
        ("D'ARTOIS Jean", "Jean D'Artois"),
        ("SMITH J. R.", "J. R. Smith"),
        ("Collectif sans nom", "Collectif sans nom"),
    ],
)
def test_navigarts_surname_first_name_is_reported_in_reading_order(notice, name):
    assert reading_order(notice) == name


# -- finding by Wikidata item ------------------------------------------------------------


def test_a_work_whose_item_records_a_navigart_page_is_read_from_its_vault_under_the_page():
    asked: list[httpx.Request] = []
    registry = FakeRegistry(
        pages={ECHELONNEMENT_ITEM: [WorkPage("https://www.moma.org/collection/works/1"), WorkPage(ECHELONNEMENT_PAGE)]}
    )

    (image,) = a_finder(registry, asked).find_images(ImageQuery(title="Échelonnement", qid=ECHELONNEMENT_ITEM))

    assert image.url == ECHELONNEMENT_PAGE
    assert (image.provider, image.title, image.artist) == ("navigart", "Echelonnement", "Sophie Taeuber-Arp")
    assert (image.estimated_width, image.estimated_height) == (777, 1000)
    assert image.preview_url == "https://images.navigart.fr/400/5E/76/5E76440.JPG"
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert image.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    (read,) = asked
    assert str(read.url) == "https://api.navigart.fr/6/artworks/60000000002521"
    assert read.headers["User-Agent"] == "arrt-tests/0"


def test_the_items_page_identifies_the_work_through_the_identity_check_with_the_artist_matched():
    """Driven through phase 2, the caller that reads the link and compares the artist.

    navigart's own spelling of the artist (`TAEUBER-ARP Sophie`) would be refused
    here, and a page of the plugin's own spelling would be judged on its title.
    """
    registry = FakeRegistry(pages={RYTHME_ITEM: [WorkPage(RYTHME_PAGE)]})
    profile = QualityProfile(minimum_long_edge_px=DEFAULT_QUALITY_MINIMUM_PX)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=profile, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Rythme couleur no 1076", artist="Sonia Delaunay", qid=RYTHME_ITEM))

    (entry,) = resolution.instances
    assert entry.found.url == RYTHME_PAGE
    assert entry.found.rights_status is RightsStatus.IN_COPYRIGHT
    assert entry.confidence == CONFIDENT
    assert "Wikidata item records" in entry.rationale
    # 777 x 1000, navigart's largest: exactly the owner's minimum, which is met.
    # Against the retired 42" reference floor (about 1,260 px) it fell short.
    assert entry.fit is Fit.MEETS_MINIMUM
    assert resolution.refusals == frozenset()


def test_another_artists_artwork_on_the_items_page_is_refused_by_the_identity_check():
    registry = FakeRegistry(pages={RYTHME_ITEM: [WorkPage(RYTHME_PAGE)]})
    profile = QualityProfile(minimum_long_edge_px=DEFAULT_QUALITY_MINIMUM_PX)
    engine = PhaseTwoEngine(ImageSourcePool([a_finder(registry)]), profile=profile, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Rythme couleur no 1076", artist="Robert Delaunay", qid=RYTHME_ITEM))

    assert list(resolution.instances) == []
    assert UnresolvedReason.IDENTITY_REFUSED in resolution.refusals


def test_two_pages_for_one_artwork_read_it_once_under_the_first_the_registry_gives():
    asked: list[httpx.Request] = []
    other = WorkPage("https://www.navigart.fr/grenoble-collections/#/artwork/60000000002521")
    registry = FakeRegistry(pages={ECHELONNEMENT_ITEM: [WorkPage(ECHELONNEMENT_PAGE), other]})
    first = registry.pages_about(ECHELONNEMENT_ITEM)[0]

    found = a_finder(registry, asked).find_images(ImageQuery(title="x", qid=ECHELONNEMENT_ITEM))

    assert [image.url for image in found] == [first]
    assert artworks_read(asked) == ["/6/artworks/60000000002521"]


def test_an_artwork_its_vault_does_not_have_skips_that_page_and_the_rest_stands():
    asked: list[httpx.Request] = []
    pages = [WorkPage("https://www.navigart.fr/grenoble/#/artwork/60000000999999"), WorkPage(ECHELONNEMENT_PAGE)]

    found = a_finder(FakeRegistry(pages={ECHELONNEMENT_ITEM: pages}), asked).find_images(
        ImageQuery(title="x", qid=ECHELONNEMENT_ITEM)
    )

    assert [image.url for image in found] == [ECHELONNEMENT_PAGE]
    assert sorted(artworks_read(asked)) == ["/6/artworks/60000000002521", "/6/artworks/60000000999999"]


def test_an_item_naming_no_navigart_page_holds_nothing_and_asks_navigart_nothing():
    asked: list[httpx.Request] = []
    registry = FakeRegistry(pages={ECHELONNEMENT_ITEM: [WorkPage("https://www.moma.org/collection/works/1")]})

    assert a_finder(registry, asked).find_images(ImageQuery(title="x", qid=ECHELONNEMENT_ITEM)) == []
    assert asked == []


def test_an_artwork_with_no_image_is_not_an_image():
    page = WorkPage("https://www.navigart.fr/fnac/artwork/140000000046190")

    assert a_finder(FakeRegistry(pages={RYTHME_ITEM: [page]})).find_images(ImageQuery(title="x", qid=RYTHME_ITEM)) == []


def test_an_image_under_a_thousand_pixels_is_reported_at_its_own_size():
    page = WorkPage("https://www.navigart.fr/mamparis/#/artwork/180000000000725")

    (image,) = a_finder(FakeRegistry(pages={RYTHME_ITEM: [page]})).find_images(ImageQuery(title="x", qid=RYTHME_ITEM))

    assert (image.estimated_width, image.estimated_height) == (366, 495)
    assert image.title == "Composition n°27 Jaune assez animé", "the line break in navigart's title is a space"
    assert image.artist == "Jean-Marie Euzet"


@pytest.mark.parametrize(("stated", "reported"), [((2000.0, 1500.0), (1000, 750)), ((900.0, 3000.0), (300, 1000))])
def test_a_record_stating_more_than_the_host_serves_is_reported_at_what_the_host_serves(stated, reported):
    """None measured does, but the read is at 1,000 whatever the record says, and a placeholder must not pass the floor."""
    record = ua(6, "60000000002521")
    medias = [{**record["medias"][0], "max_width": stated[0], "max_height": stated[1]}]
    answers = {(6, "60000000002521"): answer_with(6, "60000000002521", medias=medias)}

    (image,) = a_finder(FakeRegistry(pages={RYTHME_ITEM: [WorkPage(ECHELONNEMENT_PAGE)]}), answers=answers).find_images(
        ImageQuery(title="x", qid=RYTHME_ITEM)
    )

    assert (image.estimated_width, image.estimated_height) == reported


def test_an_anonymous_first_author_is_passed_over_for_the_named_one():
    page = WorkPage("https://www.navigart.fr/mamcs/artwork/250000000002062")

    (image,) = a_finder(FakeRegistry(pages={RYTHME_ITEM: [page]})).find_images(ImageQuery(title="x", qid=RYTHME_ITEM))

    assert image.artist == "Gustave Doré"


def test_an_artwork_of_only_anonymous_authors_has_no_artist():
    page = WorkPage("https://www.navigart.fr/mamcs/artwork/250000000002062")
    anonymous = [{"type": "anonyme", "_id": "1", "name": {"notice": "sans auteur"}}]
    answers = {(25, "250000000002062"): answer_with(25, "250000000002062", authors=anonymous)}

    (image,) = a_finder(FakeRegistry(pages={RYTHME_ITEM: [page]}), answers=answers).find_images(
        ImageQuery(title="x", qid=RYTHME_ITEM)
    )

    assert image.artist is None


def test_the_vault_that_differs_from_its_ids_prefix_is_asked_by_its_publication():
    asked: list[httpx.Request] = []
    page = WorkPage("https://www.navigart.fr/matisse_lecateau/artwork/henri-matisse-fenetre-a-tahiti-ou-tahiti-ii-70000000000186")

    (image,) = a_finder(FakeRegistry(pages={RYTHME_ITEM: [page]}), asked).find_images(ImageQuery(title="x", qid=RYTHME_ITEM))

    assert artworks_read(asked) == ["/701/artworks/70000000000186"]
    assert (image.title, image.artist) == ("Fenêtre à Tahiti ou Tahiti II", "Henri Matisse")


def test_an_item_recording_more_than_ten_navigart_pages_reads_ten_artworks():
    asked: list[httpx.Request] = []
    pages = [WorkPage(f"https://www.navigart.fr/grenoble/#/artwork/{60000000001000 + n}") for n in range(12)]

    a_finder(FakeRegistry(pages={RYTHME_ITEM: pages}), asked).find_images(ImageQuery(title="x", qid=RYTHME_ITEM))

    assert len(artworks_read(asked)) == 10


@pytest.mark.parametrize(
    "query",
    [ImageQuery(title="Échelonnement", artist="Sophie Taeuber-Arp"), ImageQuery(title="x", qid=ECHELONNEMENT_ITEM)],
    ids=["no item", "no registry"],
)
def test_a_work_with_no_item_or_a_deployment_with_no_registry_cannot_be_asked(query):
    finder = a_finder() if query.qid is None else NavigartFinder(user_agent="t", registry=None, transport=a_transport())

    with pytest.raises(ImageQueryUnanswerable):
        finder.find_images(query)


def test_a_registry_that_cannot_be_asked_is_a_search_that_could_not_be_asked():
    with pytest.raises(ImageSearchFailure, match="Wikidata could not be asked"):
        a_finder(FakeRegistry(failing=True)).find_images(ImageQuery(title="x", qid=RYTHME_ITEM))


# -- rights ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "rights"),
    [
        ("Domaine public", RightsStatus.PUBLIC_DOMAIN),
        (" Domaine public ", RightsStatus.PUBLIC_DOMAIN),
        ("© Pracusa S.A.", RightsStatus.IN_COPYRIGHT),
        ("© Adagp, Paris", RightsStatus.IN_COPYRIGHT),
        ("© droits réservés", RightsStatus.IN_COPYRIGHT),
        ("", RightsStatus.UNKNOWN),
        ("Droits réservés", RightsStatus.UNKNOWN),
        (None, RightsStatus.UNKNOWN),
    ],
)
def test_rights_are_the_holders_own_statement_and_never_leave_an_image_out(statement, rights):
    answers = {(6, "60000000002521"): answer_with(6, "60000000002521", artwork_changes={"copyright": statement})}

    (image,) = a_finder(FakeRegistry(pages={RYTHME_ITEM: [WorkPage(ECHELONNEMENT_PAGE)]}), answers=answers).find_images(
        ImageQuery(title="x", qid=RYTHME_ITEM)
    )

    assert image.rights_status is rights


# -- answers that are not the shape measured ---------------------------------------------


@pytest.mark.parametrize(
    "media",
    [
        {"url_template": "https://example.com/{size}/{file_name}"},
        {"url_template": "http://images.navigart.fr/{size}/{file_name}"},
        {"file_name": "../../etc/passwd"},
        {"file_name": "https://example.com/x.jpg"},
        {"file_name": None},
    ],
    ids=["another host", "plain http", "a parent path", "a url", "no file"],
)
def test_an_image_navigart_does_not_serve_is_not_offered_or_read(media):
    record = ua(6, "60000000002521")
    medias = [{**record["medias"][0], **media}]
    answers = {(6, "60000000002521"): answer_with(6, "60000000002521", medias=medias)}

    found = a_finder(FakeRegistry(pages={RYTHME_ITEM: [WorkPage(ECHELONNEMENT_PAGE)]}), answers=answers).find_images(
        ImageQuery(title="x", qid=RYTHME_ITEM)
    )

    assert found == []
    with pytest.raises(ImageSearchFailure, match="does not serve"):
        a_reader(answers=answers).read(ECHELONNEMENT_PAGE)


def test_a_media_that_is_not_an_image_is_passed_over_for_the_image():
    """The API documents media types; only `image` is a picture of the work."""
    record = ua(6, "60000000002521")
    sound = {"_id": "1", "type": "sound", "file_name": "interview.mp3", "url_template": "https://example.com/{file_name}"}
    answers = {(6, "60000000002521"): answer_with(6, "60000000002521", medias=[sound, *record["medias"]])}

    (image,) = a_finder(FakeRegistry(pages={RYTHME_ITEM: [WorkPage(ECHELONNEMENT_PAGE)]}), answers=answers).find_images(
        ImageQuery(title="x", qid=RYTHME_ITEM)
    )

    assert image.preview_url == "https://images.navigart.fr/400/5E/76/5E76440.JPG"
    assert a_reader(answers=answers).read(ECHELONNEMENT_PAGE) == FetchLocator.direct(
        "https://images.navigart.fr/1000/5E/76/5E76440.JPG"
    )


def test_an_artwork_with_no_title_is_not_offered():
    answers = {(6, "60000000002521"): answer_with(6, "60000000002521", artwork_changes={"title_notice": "  "})}

    found = a_finder(FakeRegistry(pages={RYTHME_ITEM: [WorkPage(ECHELONNEMENT_PAGE)]}), answers=answers).find_images(
        ImageQuery(title="x", qid=RYTHME_ITEM)
    )

    assert found == []


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(404, text=(FIXTURES / "unknown_vault_404.html").read_text(), headers={"Content-Type": "text/html"}),
        httpx.Response(401, json=fixture("unauthorized_401.json")),
        httpx.Response(403, text="forbidden"),
        httpx.Response(429, text="slow down"),
        httpx.Response(503, text="down"),
        httpx.Response(302, headers={"Location": "https://example.com/"}),
        httpx.Response(200, text="<html>maintenance</html>"),
        httpx.Response(200, json={"results": []}),
        httpx.Response(200, json={"results": [{"_id": "60000000000001", "_source": {"ua": {}}}]}),
        httpx.Response(200, json={"results": [{"_id": "60000000002521"}]}),
        httpx.Response(200, json=[]),
    ],
    ids=[
        "nginx 404",
        "private vault",
        "403",
        "429",
        "503",
        "redirect",
        "a page",
        "no record",
        "another artwork",
        "no ua",
        "a list",
    ],
)
def test_an_answer_that_is_not_the_artwork_asked_for_could_not_be_asked(answer):
    answers = {(6, "60000000002521"): answer}
    registry = FakeRegistry(pages={RYTHME_ITEM: [WorkPage(ECHELONNEMENT_PAGE)]})

    with pytest.raises(ImageSearchFailure):
        a_finder(registry, answers=answers).find_images(ImageQuery(title="x", qid=RYTHME_ITEM))
    with pytest.raises(ImageSearchFailure):
        a_reader(answers=answers).read(ECHELONNEMENT_PAGE)


def test_a_network_failure_could_not_be_asked():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    finder = NavigartFinder(
        user_agent="t",
        registry=FakeRegistry(pages={RYTHME_ITEM: [WorkPage(RYTHME_PAGE)]}),
        transport=httpx.MockTransport(down),
    )

    with pytest.raises(ImageSearchFailure, match="Could not read artwork"):
        finder.find_images(ImageQuery(title="x", qid=RYTHME_ITEM))


# -- previews ----------------------------------------------------------------------------


def test_a_preview_is_read_from_the_image_host_only_and_under_the_ceiling():
    preview = "https://images.navigart.fr/400/5E/76/5E76440.JPG"
    big = a_transport(image=lambda r: httpx.Response(200, content=b"x" * 100))

    assert NavigartFinder(user_agent="t", registry=None, transport=big, preview_max_bytes=50).fetch_preview(preview) is None
    roomy = NavigartFinder(user_agent="t", registry=None, transport=big)
    assert roomy.fetch_preview(preview) == b"x" * 100
    assert roomy.fetch_preview("https://example.com/400/5E/76/5E76440.JPG") is None
    assert roomy.fetch_preview("http://images.navigart.fr/400/5E/76/5E76440.JPG") is None


def test_an_image_host_redirect_is_not_followed_off_the_host():
    asked: list[httpx.Request] = []
    elsewhere = a_transport(asked, image=lambda r: httpx.Response(302, headers={"Location": "https://example.com/t.jpg"}))

    assert (
        NavigartFinder(user_agent="t", registry=None, transport=elsewhere).fetch_preview(
            "https://images.navigart.fr/400/5E/76/5E76440.JPG"
        )
        is None
    )
    assert {r.url.host for r in asked} == {"images.navigart.fr"}


# -- reading -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "image"),
    [
        (ECHELONNEMENT_PAGE, "https://images.navigart.fr/1000/5E/76/5E76440.JPG"),
        (RYTHME_PAGE, "https://images.navigart.fr/1000/5D/69/5D69677.jpg"),
        ("https://api.navigart.fr/18/artworks/180000000000725", "https://images.navigart.fr/1000/1A/36/1A36857.jpg"),
        ("https://www.navigart.fr/matisse_lecateau/artwork/70000000000186", "https://images.navigart.fr/1000/2G/05/2G05796.JPG"),
    ],
)
def test_the_reader_reads_a_page_to_the_largest_image_navigart_serves(url, image):
    assert a_reader().read(url) == FetchLocator.direct(image)


def test_the_reader_says_none_for_an_artwork_with_no_image_and_one_its_vault_does_not_have():
    assert a_reader().read("https://www.navigart.fr/fnac/artwork/140000000046190").kind is LocatorKind.NONE
    assert a_reader().read("https://www.navigart.fr/grenoble/#/artwork/60000000999999").kind is LocatorKind.NONE


def test_the_reader_refuses_a_url_it_does_not_claim():
    with pytest.raises(ImageSearchFailure):
        a_reader().read("https://www.navigart.fr/somewhere-new/#/artwork/60000000002521")


# -- the plugin --------------------------------------------------------------------------


def test_the_factory_wires_the_deployments_registry_agent_and_preview_ceiling(monkeypatch):
    """Through the plugin's own factory, with values no default carries."""
    asked: list[httpx.Request] = []
    real = navigart._client
    monkeypatch.setattr(
        navigart,
        "_client",
        lambda transport: real(transport or a_transport(asked, image=lambda r: httpx.Response(200, content=b"x" * 100))),
    )
    registry = FakeRegistry(pages={ECHELONNEMENT_ITEM: [WorkPage(ECHELONNEMENT_PAGE)]})
    preview = "https://images.navigart.fr/400/5E/76/5E76440.JPG"

    parts = PLUGIN.create(SourceContext(environ={}, user_agent="deployment/7", preview_max_bytes=50, registry=registry))
    (image,) = parts.finder.find_images(ImageQuery(title="x", qid=ECHELONNEMENT_ITEM))

    assert image.url == ECHELONNEMENT_PAGE
    assert registry.pages_asked == [ECHELONNEMENT_ITEM]
    assert {r.headers["User-Agent"] for r in asked} == {"deployment/7"}
    assert parts.finder.fetch_preview(preview) is None
    roomy = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1000, registry=registry))
    assert roomy.finder.fetch_preview(preview) == b"x" * 100
    assert parts.reader.read(RYTHME_PAGE) == FetchLocator.direct("https://images.navigart.fr/1000/5D/69/5D69677.jpg")


def test_the_plugin_never_declines_and_finds_only_with_a_registry():
    without = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=None))
    with_registry = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=FakeRegistry()))

    assert isinstance(without, SourceParts)
    assert without.finder is None, "with no registry it cannot find a work, so it is not an image source"
    assert without.reader is not None
    assert isinstance(with_registry, SourceParts)
    assert with_registry.finder is not None
    assert with_registry.finder.provider == "navigart"
    assert with_registry.reader is not None
    assert PLUGIN.claims is claims
