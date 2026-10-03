"""Sightings: the pages found for a work that no installed plugin reads, kept once and counted by host.

A sighting is keyed by the work's item, and question 1 counts hosts over the
works still open (`source-plugins.md` § Sightings). The services here are built
over the suite's roster, in which the Art Institute's plugin claims its own
object pages, so a claimed page and an unclaimed one sit side by side.
"""

import logging
import sqlite3

import pytest
from fakes import FakeFinder, FakeRegistry
from plugin_fakes import StubFinder, claims_example

from arrt.library.discovery.images import FoundImage, FoundPage, ImageQuery, ImageQueryUnanswerable, offers_images
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool, NoSourceCanAnswer
from arrt.library.registry import ItemId
from arrt.library.services.discovery import ChosenWork
from arrt.library.services.previews import PreviewCache, PreviewSettings
from arrt.library.services.runner import DiscoveryRunner
from arrt.library.services.sightings import HostCount, SightingService
from arrt.library.sources import SourceContext
from arrt.library.sources.loading import FAULT_EVENT, FAULT_LOGGER, SourceRoster, load_sources
from arrt.library.sources.wikidata import WikidataFinder
from arrt.persistence.discovery_records import (
    CandidateWork,
    InitiatedBy,
    ResolutionStatus,
    Sighting,
    Verdict,
)
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.sqlite_discovery import SqliteDiscovery

DROWNING_GIRL = "Q5308687"
MOMA = "https://www.moma.org/collection/works/80249"
#: An Art Institute object page: the suite's roster has its plugin claim it.
ARTIC_PAGE = "https://www.artic.edu/artworks/27992/a-sunday-on-la-grande-jatte-1884"


def _page(url: str) -> FoundPage:
    return FoundPage(url=url)


# -- recording ----------------------------------------------------------------


def test_a_page_no_plugin_claims_becomes_exactly_one_sighting(services, discovery_store, run):
    _open_work(discovery_store, run.id, DROWNING_GIRL, verdict=Verdict.WANTED)

    new = services.sightings.record(DROWNING_GIRL, [_page(MOMA)], work_title="Drowning Girl")

    assert new == 1
    assert discovery_store.list_open_sightings() == [Sighting(wikidata_qid=DROWNING_GIRL, url=MOMA)]


def test_the_same_page_found_again_stays_one_sighting(services, discovery_store, run):
    """Found by a second search with another page beside it: the first stays one, the second is added."""
    _open_work(discovery_store, run.id, DROWNING_GIRL, verdict=Verdict.WANTED)
    services.sightings.record(DROWNING_GIRL, [_page(MOMA)], work_title="Drowning Girl")

    again = services.sightings.record(
        DROWNING_GIRL, [_page(MOMA), _page("https://www.lichtensteincatalogue.org/x")], work_title="Drowning Girl"
    )

    assert again == 1
    assert sorted(sighting.url for sighting in discovery_store.list_open_sightings()) == [
        "https://www.lichtensteincatalogue.org/x",
        MOMA,
    ]


def test_a_page_a_loaded_plugin_claims_is_left_to_it(services, discovery_store, run, caplog):
    _open_work(discovery_store, run.id, DROWNING_GIRL, verdict=Verdict.WANTED)

    with caplog.at_level(logging.INFO, logger="arrt.library.services.sightings"):
        new = services.sightings.record(DROWNING_GIRL, [_page(ARTIC_PAGE)], work_title="Drowning Girl")

    assert new == 0
    assert discovery_store.list_open_sightings() == []
    claimed = [record for record in caplog.records if getattr(record, "event", None) == "sightings.claimed"]
    assert [(record.plugin, record.host) for record in claimed] == [("artic", "www.artic.edu")]


def test_a_page_a_declined_plugin_claims_is_not_a_sighting(discovery_store, store, run):
    """Installed and not configured here is still installed: configuring it reads the page, so no reader is owed."""
    roster = SourceRoster.of(unavailable={"example": (claims_example, "EXAMPLE_KEY is unset")})
    service = SightingService(discovery_store, store, route=roster.route)
    _open_work(discovery_store, run.id, DROWNING_GIRL, verdict=Verdict.WANTED)

    assert service.record(DROWNING_GIRL, [_page("https://example.org/works/1")], work_title="Drowning Girl") == 0
    assert discovery_store.list_open_sightings() == []


def test_pages_for_a_work_with_no_item_are_journalled_and_not_kept(services, discovery_store, caplog):
    with caplog.at_level(logging.INFO, logger="arrt.library.services.sightings"):
        new = services.sightings.record(None, [_page(MOMA)], work_title="Drowning Girl")

    assert new == 0
    assert [getattr(record, "event", None) for record in caplog.records] == ["sightings.no_item"]


# -- question 1: hosts by count, over works still open ----------------------------


def test_hosts_count_only_works_still_open(services, discovery_store, run):
    """Wanted, and unresolved with no verdict, count. Held, rejected and resolved works do not."""
    counted = {
        "Q1": {"verdict": Verdict.WANTED},
        "Q2": {"resolution_status": ResolutionStatus.UNRESOLVED},
    }
    not_counted = {
        # Wanted in one run and since held: the catalogue's answer wins.
        "Q3": {"verdict": Verdict.WANTED},
        "Q4": {"resolution_status": ResolutionStatus.UNRESOLVED, "verdict": Verdict.REJECTED},
        "Q5": {"resolution_status": ResolutionStatus.RESOLVED},
    }
    for qid, state in {**counted, **not_counted}.items():
        _open_work(discovery_store, run.id, qid, **state)
        services.sightings.record(qid, [_page(f"https://www.moma.org/collection/works/{qid}")], work_title=qid)
    services.catalogue.add_artwork(title="Held", wikidata_qid="Q3")

    assert services.sightings.hosts() == [HostCount(host="www.moma.org", works=2)]


def test_hosts_count_works_not_pages_and_the_most_first(services, discovery_store, run):
    """MoMA's two pages for one work count it once; the order is by works, and a tie goes by name."""
    for qid in ("Q1", "Q2"):
        _open_work(discovery_store, run.id, qid, verdict=Verdict.WANTED)
    services.sightings.record(
        "Q1",
        [_page("https://www.moma.org/a"), _page("https://www.moma.org/b"), _page("https://www.tate.org.uk/1")],
        work_title="one",
    )
    services.sightings.record("Q2", [_page("https://www.moma.org/c"), _page("https://www.centrepompidou.fr/2")], work_title="two")

    assert services.sightings.hosts() == [
        HostCount(host="www.moma.org", works=2),
        HostCount(host="www.centrepompidou.fr", works=1),
        HostCount(host="www.tate.org.uk", works=1),
    ]


def test_a_page_a_plugin_installed_since_claims_drops_out_of_the_count(discovery_store, store, run):
    """Question 2's reading: the rows stay, and the count asks the plugins installed now."""
    _open_work(discovery_store, run.id, "Q1", verdict=Verdict.WANTED)
    SightingService(discovery_store, store, route=SourceRoster.empty().route).record(
        "Q1", [_page("https://example.org/works/1"), _page(MOMA)], work_title="one"
    )

    since = SightingService(discovery_store, store, route=SourceRoster.of(readers={"example": (claims_example, None)}).route)

    assert since.hosts() == [HostCount(host="www.moma.org", works=1)]
    assert len(discovery_store.list_open_sightings()) == 2


# -- through the pool and phase 2 -----------------------------------------------


def test_the_pool_keeps_pages_apart_from_images_and_each_once():
    moma = _page(MOMA)
    roster = SourceRoster.of(
        finders=[
            StubFinder("artic"),
            _Pages("wikidata", moma, _page(ARTIC_PAGE)),
            _Pages("another", moma),
        ]
    )

    answer = ImageSourcePool(roster.finders).find_images(ImageQuery(title="Drowning Girl", qid=ItemId(DROWNING_GIRL)))

    assert [image.provider for image in answer.images] == ["artic"]
    assert answer.pages == (moma, _page(ARTIC_PAGE))


@pytest.mark.plugin_fault_expected
def test_a_finder_answering_a_page_that_is_not_a_url_is_a_contained_fault(caplog):
    """`FoundPage` refuses it in the plugin's own call, which the containment turns into could-not-be-asked."""
    roster = SourceRoster.of(finders=[StubFinder("artic"), _Raw("bad", lambda: FoundPage(url="moma.org/80249"))])

    with caplog.at_level(logging.ERROR, logger=FAULT_LOGGER):
        answer = ImageSourcePool(roster.finders).find_images(ImageQuery(title="Drowning Girl"))

    assert answer.unreachable == ("bad",)
    assert [record.plugin for record in caplog.records if getattr(record, "event", None) == FAULT_EVENT] == ["bad"]


@pytest.mark.plugin_fault_expected
def test_a_finder_answering_something_that_is_neither_image_nor_page_is_a_contained_fault(caplog):
    roster = SourceRoster.of(finders=[StubFinder("artic"), _Raw("bad", lambda: MOMA)])

    with caplog.at_level(logging.ERROR, logger=FAULT_LOGGER):
        answer = ImageSourcePool(roster.finders).find_images(ImageQuery(title="Drowning Girl"))

    assert answer.unreachable == ("bad",)
    assert answer.pages == ()


@pytest.mark.parametrize("pages", [(FoundPage(url=MOMA),), ()], ids=["with pages", "with none"])
def test_a_finder_of_pages_alone_is_not_a_source_that_answered(pages):
    """Its answer says nothing about images, so the work waits rather than being held by nobody."""
    roster = SourceRoster.of(finders=[_Pages("wikidata", *pages, offers_images=False)])

    with pytest.raises(NoSourceCanAnswer, match="wikidata finds pages only"):
        ImageSourcePool(roster.finders).find_images(ImageQuery(title="Drowning Girl", qid=ItemId(DROWNING_GIRL)))


def test_a_finder_of_pages_beside_one_that_declined_still_leaves_the_work_waiting():
    roster = SourceRoster.of(finders=[_Raw("commons", _declines), _Pages("wikidata", FoundPage(url=MOMA), offers_images=False)])

    with pytest.raises(NoSourceCanAnswer, match="commons cannot; wikidata finds pages only"):
        ImageSourcePool(roster.finders).find_images(ImageQuery(title="Drowning Girl"))


def test_an_image_source_answering_nothing_beside_a_finder_of_pages_is_held_by_nobody():
    """The other direction: an image source did answer, so the empty answer is a fact about the work."""
    roster = SourceRoster.of(finders=[_Raw("artic", list), _Pages("wikidata", FoundPage(url=MOMA), offers_images=False)])

    answer = ImageSourcePool(roster.finders).find_images(ImageQuery(title="Drowning Girl"))

    assert (answer.images, answer.unreachable, answer.pages) == ((), (), (FoundPage(url=MOMA),))


def test_the_loaded_wikidata_plugin_is_a_finder_of_pages_through_the_containment():
    """Read from the real entry point and the real loader: the declaration has to survive the wrapping."""
    roster = load_sources(
        SourceContext(
            environ={"WIKIDATA_USER_AGENT": "arrt-tests/0"},
            user_agent="arrt-tests/0",
            preview_max_bytes=1,
            registry=FakeRegistry(),
        ),
        order=(),
    )

    finders = {finder.provider: finder for finder in roster.finders}
    assert offers_images(finders["wikidata"]) is False
    assert offers_images(finders["commons"]) is True


def test_phase_two_passes_the_pages_on_untouched(settings):
    engine = PhaseTwoEngine(
        ImageSourcePool(SourceRoster.of(finders=[_Pages("wikidata", _page(MOMA))]).finders),
        box=settings.tv_artwork_box,
    )

    resolution = engine.resolve(ImageQuery(title="Drowning Girl", qid=ItemId(DROWNING_GIRL)))

    assert resolution.instances == []
    assert resolution.pages == (_page(MOMA),)


# -- through the runner ---------------------------------------------------------


def test_a_get_records_the_pages_its_search_found(services, engine, settings):
    """The whole path: the Wikidata finder's pages, the pool, phase 2, the runner, the routing and the store."""
    registry = FakeRegistry(pages={DROWNING_GIRL: [MOMA, ARTIC_PAGE]})
    museum = FakeFinder()
    pool = ImageSourcePool([museum, WikidataFinder(registry=registry)])
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(pool, box=settings.tv_artwork_box),
        previews=PreviewCache(PreviewSettings(art_root=settings.art_root, directory=settings.previews_path), pool.fetch_preview),
        sightings=services.sightings,
        spawn=lambda work: work(),
    )

    runner.get(
        works=[ChosenWork(qid=DROWNING_GIRL, title="Drowning Girl", artist="Roy Lichtenstein")],
        initiated_by=InitiatedBy.MCP_CLIENT,
    )

    # The museum holds only a near-match, so the work is unresolved and open,
    # and the Art Institute's page is its plugin's, not a sighting.
    assert registry.pages_asked == [DROWNING_GIRL]
    assert services.sightings.hosts() == [HostCount(host="www.moma.org", works=1)]


# -- the table ------------------------------------------------------------------


def test_a_file_written_before_sightings_gains_the_table_and_keeps_its_rows(tmp_path):
    """Varied between opens: a file with no table, then rows written, then reopened and written to again."""
    path = tmp_path / "catalogue.sqlite"
    first = open_catalogue_file(path)
    first.close()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE sightings")
    connection.commit()
    connection.close()

    second = open_catalogue_file(path)
    SqliteDiscovery(second).add_sighting(Sighting(wikidata_qid="Q1", url=MOMA))
    second.close()

    third = open_catalogue_file(path)
    store = SqliteDiscovery(third)
    assert store.add_sighting(Sighting(wikidata_qid="Q1", url=MOMA)) is False
    assert store.add_sighting(Sighting(wikidata_qid="Q2", url=MOMA)) is True
    rows = third.select_rows('SELECT "wikidata_qid", "url" FROM sightings ORDER BY "wikidata_qid"')
    third.close()

    assert rows == [{"wikidata_qid": "Q1", "url": MOMA}, {"wikidata_qid": "Q2", "url": MOMA}]


# -- helpers --------------------------------------------------------------------


def _open_work(store, run_id: str, qid: str, **state) -> CandidateWork:
    work = CandidateWork(
        id=f"work-{qid}",
        discovery_run_id=run_id,
        proposed_title=f"A work {qid}",
        rationale="Asked for.",
        work_dedup_key=f"key-{qid}",
        wikidata_qid=qid,
        **state,
    )
    store.add_candidate_work(work)
    return work


class _Pages:
    """A finder that answers the same pages for every work, and no image.

    It says it offers images unless told otherwise: a finder of images that found
    only pages this time, which is a real answer of "no image here".
    """

    def __init__(self, provider: str, *pages: FoundPage, offers_images: bool = True) -> None:
        self._provider = provider
        self._pages = pages
        self.offers_images = offers_images

    @property
    def provider(self) -> str:
        return self._provider

    def find_images(self, query: ImageQuery) -> tuple[FoundPage, ...]:
        return self._pages

    def fetch_preview(self, url: str) -> bytes | None:
        return None


class _Raw:
    """A finder whose answer is built inside its own call, so what the answer raises is the plugin's."""

    def __init__(self, provider: str, build) -> None:
        self._provider = provider
        self._build = build

    @property
    def provider(self) -> str:
        return self._provider

    def find_images(self, query: ImageQuery) -> list[FoundImage | FoundPage]:
        answer = self._build()
        return answer if isinstance(answer, list) else [answer]

    def fetch_preview(self, url: str) -> bytes | None:
        return None


def _declines():
    raise ImageQueryUnanswerable("this finder looks a work up by item")
