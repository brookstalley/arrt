"""The pages a work's Wikidata item records, and the finder that offers them.

`tests/fixtures/wikidata_pages/answers.json` holds the bindings the query service
returned on 2026-10-03 to the client's own query, for four procurement-corpus
items (`build-plan-source-plugins.md` Chunk 03): *Drowning Girl* (`Q5308687`),
*The Persistence of Memory* (`Q25729`), *Prismes électriques* (`Q60144838`) and
*Margarethe* (`Q50321310`). Uncut, because what an item carries besides holders'
pages is part of what these tests are about.
"""

import json
import pathlib
from urllib.parse import parse_qs

import httpx
import pytest
from fakes import FakeRegistry
from plugin_fakes import StubFinder

from arrt.library.discovery.images import FoundPage, ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry import ItemId
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import SourceContext, SourceParts
from arrt.library.sources.loading import SourceRoster
from arrt.library.sources.wikidata import PLUGIN, WikidataFinder

ANSWERS = json.loads((pathlib.Path(__file__).parents[1] / "fixtures" / "wikidata_pages" / "answers.json").read_text())

UA = "arrt test (+https://example.org)"

MOMA_DROWNING_GIRL = "https://www.moma.org/collection/works/80249"


def _registry(*bindings, asked=None) -> WikidataRegistry:
    queue = list(bindings)

    def handler(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(parse_qs(request.content.decode())["query"][0])
        return httpx.Response(200, json={"results": {"bindings": queue.pop(0) if queue else []}})

    return WikidataRegistry(user_agent=UA, client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))


def _external(prop: str, value: str, formatter: str) -> dict:
    return {
        "prop": {"type": "uri", "value": f"http://www.wikidata.org/entity/{prop}"},
        "value": {"type": "literal", "value": value},
        "formatter": {"type": "literal", "value": formatter},
    }


def _described(url: str) -> dict:
    return {"described": {"type": "uri", "value": url}}


# -- the registry client ------------------------------------------------------


def test_drowning_girl_gives_moma_s_page_through_p2014_s_formatter_url():
    asked: list[str] = []

    pages = _registry(ANSWERS["pages Q5308687"], asked=asked).pages_about("Q5308687")

    assert MOMA_DROWNING_GIRL in pages
    assert "wd:Q5308687" in asked[0]


def test_every_page_the_item_records_is_offered_not_only_the_holder_s():
    """The Lichtenstein catalogue raisonné and a Google search link are on the item too.

    Which of them shows the work is a reader's to say, so the client keeps them all.
    """
    pages = _registry(ANSWERS["pages Q5308687"]).pages_about("Q5308687")

    assert pages == [
        "https://www.google.com/search?kgmid=/m/03qqzvj",
        "https://www.lichtensteincatalogue.org/catalogue/entry.php?id=452",
        MOMA_DROWNING_GIRL,
    ]


def test_reproduction_sites_are_offered_with_the_holder():
    """*The Persistence of Memory* carries MoMA beside the Athenaeum (through the archive) and HA!."""
    pages = _registry(ANSWERS["pages Q25729"]).pages_about("Q25729")

    assert "https://www.moma.org/collection/works/79018" in pages
    assert "https://historia-arte.com/obras/la-persistencia-de-la-memoria" in pages
    assert "https://web.archive.org/web/*/https://www.the-athenaeum.org/art/detail.php?ID=234901" in pages


def test_an_identifier_is_percent_encoded_into_its_formatter_url():
    """As Wikibase encodes it: the path's own separators kept, everything else escaped."""
    pages = _registry(ANSWERS["pages Q25729"]).pages_about("Q25729")

    assert "https://central.vikidia.org/wiki/fr:La_Persistance_de_la_m%C3%A9moire" in pages
    assert "https://www.britannica.com/topic/The-Persistence-of-Memory" in pages
    assert not [page for page in pages if "é" in page or " " in page]


def test_a_described_at_url_is_a_page_as_it_stands():
    """*Margarethe* carries no identifier with a formatter; SFMOMA is on it as P973 alone."""
    assert _registry(ANSWERS["pages Q50321310"]).pages_about("Q50321310") == ["https://www.sfmoma.org/artwork/FC.595"]


def test_both_of_the_pompidou_s_identifiers_give_a_page():
    pages = _registry(ANSWERS["pages Q60144838"]).pages_about("Q60144838")

    assert "https://www.centrepompidou.fr/fr/id/zS28bfR" in pages
    assert "https://collection.centrepompidou.fr/#/artwork/150000000029902" in pages


def test_an_item_with_neither_kind_of_statement_has_no_pages():
    assert _registry([]).pages_about("Q1") == []


@pytest.mark.parametrize(
    ("row", "why"),
    [
        (_external("P1", "42", "https://example.org/works/"), "a formatter with nowhere to put the identifier"),
        (_described("javascript:alert(1)"), "a scheme no reader fetches"),
        (_described("ftp://example.org/work/42"), "a scheme no reader fetches"),
        (_described("https:///no-host"), "no host"),
        (_described("https://example.org/a work"), "a space, which an encoded URL never carries"),
        (_described("https://example.org/work\n42"), "a line break, which would split a journal line"),
        (_described("https://example.org/" + "a" * 2048), "longer than any address someone typed"),
    ],
)
def test_a_statement_that_is_not_a_page_is_dropped(row, why):
    kept = _described("https://example.org/kept")

    assert _registry([row, kept]).pages_about("Q1") == ["https://example.org/kept"], why


def test_one_page_named_twice_is_offered_once():
    twice = [_external("P2014", "80249", "https://www.moma.org/collection/works/$1"), _described(MOMA_DROWNING_GIRL)]

    assert _registry(twice).pages_about("Q5308687") == [MOMA_DROWNING_GIRL]


def test_an_id_that_is_not_an_item_is_refused_before_anything_is_asked():
    asked: list[str] = []

    with pytest.raises(ValueError):
        _registry([], asked=asked).pages_about("Q1 } ?x ?y ?z . {")

    assert asked == []


# -- the finder -----------------------------------------------------------------


def _finder(**pages) -> WikidataFinder:
    return WikidataFinder(registry=FakeRegistry(pages=pages))


def test_the_finder_offers_each_page_and_no_image():
    found = _finder(Q5308687=[MOMA_DROWNING_GIRL, "https://www.google.com/search?kgmid=/m/03qqzvj"]).find_images(
        ImageQuery(title="Drowning Girl", artist="Roy Lichtenstein", qid=ItemId("Q5308687"))
    )

    assert found == (FoundPage(url="https://www.google.com/search?kgmid=/m/03qqzvj"), FoundPage(url=MOMA_DROWNING_GIRL))


def test_a_work_with_no_item_is_not_a_question_the_finder_can_answer():
    with pytest.raises(ImageQueryUnanswerable):
        _finder().find_images(ImageQuery(title="Drowning Girl"))


def test_wikidata_down_is_could_not_be_asked_not_holds_nothing():
    finder = WikidataFinder(registry=FakeRegistry(failing=True))

    with pytest.raises(ImageSearchFailure):
        finder.find_images(ImageQuery(title="Drowning Girl", qid=ItemId("Q5308687")))


def test_the_finder_reports_no_preview():
    assert _finder().fetch_preview("https://upload.wikimedia.org/anything.jpg") is None


def test_the_plugin_is_built_over_the_deployment_s_registry():
    registry = FakeRegistry(pages={"Q5308687": [MOMA_DROWNING_GIRL]})

    parts = PLUGIN.create(SourceContext(environ={}, user_agent="arrt-tests/0", preview_max_bytes=1, registry=registry))

    assert isinstance(parts, SourceParts) and parts.finder is not None
    parts.finder.find_images(ImageQuery(title="Drowning Girl", qid=ItemId("Q5308687")))
    assert registry.pages_asked == ["Q5308687"]


# -- with the image a work's item names -----------------------------------------


def test_an_item_with_no_pages_gives_only_its_commons_image():
    """The item's own image (P18) is the Commons plugin's to find, as an image; this finder adds nothing."""
    commons = StubFinder("commons")
    roster = SourceRoster.of(finders=[commons, _finder()])

    answer = ImageSourcePool(roster.finders).find_images(ImageQuery(title="Drowning Girl", qid=ItemId("Q5308687")))

    assert [image.provider for image in answer.images] == ["commons"]
    assert answer.pages == ()
