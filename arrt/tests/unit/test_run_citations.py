"""The pages a run's search read, kept with the run and handed to every finder.

Phase 1's web search cites a gallery's artist page when it is asked about the
artist (measured 2026-10-05, `procurement-corpus.md`), and a plugin that
recognises such a page looks for the work on it. These tests hold the half Arrt
owns: the pages are stored once, in the search's order, survive into a re-search,
and reach a finder only after the fetch policy has passed them.

Driven through the runner, because the store already answering is not the claim:
the claim is that the query a finder receives carries them.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from fakes import FakeFinder, a_work, an_image

from arrt.library.acquisition.urls import UrlRefused
from arrt.library.discovery.engine import WorkList
from arrt.library.discovery.images import FoundImage, ImageQuery
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.services.discovery import ChosenWork
from arrt.library.services.previews import PreviewCache, PreviewSettings
from arrt.library.services.runner import DiscoveryRunner
from arrt.library.sources.loading import SourceRoster
from arrt.persistence.discovery_records import DiscoveryRun, InitiatedBy, RunKind, RunStatus
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.sqlite_discovery import SqliteDiscovery
from arrt.services.container import Services

MARKEL = "https://www.markelfinearts.com/artists/422-peter-stephens/works"
ARTSY = "https://www.artsy.net/artist/peter-stephens"
#: A citation an injected page could have put in the search's results: a name
#: that resolves inside the house.
ROUTER = "http://router.example/admin"


@dataclass
class QueryRecordingFinder(FakeFinder):
    """The fake museum, keeping each whole query rather than only its title."""

    queries: list[ImageQuery] = field(default_factory=list)

    def find_images(self, query: ImageQuery) -> list[FoundImage]:
        self.queries.append(query)
        return list(super().find_images(query))


@dataclass
class PagePolicy:
    """The fetch policy with its DNS answers stated: `refused` hosts resolve to the LAN."""

    refused: set[str] = field(default_factory=set)
    checked: list[str] = field(default_factory=list)

    def __call__(self, url: str) -> str:
        self.checked.append(url)
        if any(host in url for host in self.refused):
            raise UrlRefused(f"{url!r} resolves to 192.168.1.1, which is not a public address.")
        return url


@pytest.fixture
def museum() -> QueryRecordingFinder:
    return QueryRecordingFinder()


@pytest.fixture
def policy() -> PagePolicy:
    return PagePolicy(refused={"router.example"})


@pytest.fixture
def runner(services, engine, settings, museum, policy) -> DiscoveryRunner:
    previews = PreviewCache(
        PreviewSettings(art_root=settings.art_root, directory=settings.previews_path), ImageSourcePool([museum]).fetch_preview
    )
    return DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(ImageSourcePool([museum]), box=settings.tv_artwork_box),
        previews=previews,
        spawn=lambda work: work(),
        check_page=policy,
    )


def ask(runner, engine, museum, *titles, citations=(MARKEL, ARTSY)):
    engine.result = WorkList(works=tuple(a_work(title, artist="Peter Stephens") for title in titles), citations=citations)
    museum.holdings = {title: (an_image(title, artist="Peter Stephens"),) for title in titles}
    return runner.start(intent_text="Peter Stephens's geometric paintings", initiated_by=InitiatedBy.MCP_CLIENT)


def pages_by_title(museum) -> dict[str, tuple[str, ...]]:
    return {query.title: query.pages for query in museum.queries}


# -- handed to the finders --------------------------------------------------------


def test_every_work_a_run_proposed_is_searched_with_the_run_s_pages_in_the_search_s_order(runner, engine, museum, services):
    run = ask(runner, engine, museum, "Mambo Jumbo", "Quadrivium 77")

    assert services.discovery.get_run(run.id).status is RunStatus.COMPLETED
    assert pages_by_title(museum) == {"Mambo Jumbo": (MARKEL, ARTSY), "Quadrivium 77": (MARKEL, ARTSY)}


def test_a_page_the_fetch_policy_refuses_never_reaches_a_finder_and_the_others_still_do(runner, engine, museum, caplog):
    with caplog.at_level(logging.INFO, logger="arrt.library.services.runner"):
        ask(runner, engine, museum, "Mambo Jumbo", citations=(ROUTER, MARKEL, ARTSY))

    assert pages_by_title(museum) == {"Mambo Jumbo": (MARKEL, ARTSY)}
    assert [record.event for record in caplog.records if getattr(record, "event", "") == "phase_two.page_refused"] == [
        "phase_two.page_refused"
    ]


def test_a_run_s_pages_are_checked_once_however_many_works_it_proposed(runner, engine, museum, policy):
    ask(runner, engine, museum, "Mambo Jumbo", "Quadrivium 77", "Big Top")

    assert sorted(policy.checked) == sorted([MARKEL, ARTSY])


def test_a_run_whose_search_cited_nothing_searches_as_before(runner, engine, museum):
    ask(runner, engine, museum, "Mambo Jumbo", citations=())

    assert pages_by_title(museum) == {"Mambo Jumbo": ()}


def test_a_re_search_hands_the_proposing_run_s_pages_again(runner, engine, museum, services):
    """A re-search is its own run with no search of its own: the pages are the
    ones the run that proposed the work stored, read back, not held in memory."""
    run = ask(runner, engine, museum, "Mambo Jumbo", "Quadrivium 77")
    work = next(w for w in services.discovery.list_candidate_works(run.id) if w.proposed_title == "Quadrivium 77")
    museum.queries.clear()
    engine.result = WorkList(works=(), citations=("https://elsewhere.example/a",))

    runner.resolve_images(candidate_work_ids=[work.id], initiated_by=InitiatedBy.MCP_CLIENT)

    assert pages_by_title(museum) == {"Quadrivium 77": (MARKEL, ARTSY)}


def test_a_get_s_works_are_searched_with_no_pages(runner, engine, museum):
    """A Get searches nothing on the web, so it has no citations to hand on."""
    museum.holdings = {"Mambo Jumbo": (an_image("Mambo Jumbo", artist="Peter Stephens"),)}

    runner.get(works=[ChosenWork(qid="Q1", title="Mambo Jumbo", artist="Peter Stephens")], initiated_by=InitiatedBy.MCP_CLIENT)

    assert [query.pages for query in museum.queries] == [()]


# -- the table ------------------------------------------------------------------


def test_a_run_s_citations_keep_the_search_s_order_and_a_repeat_keeps_its_first_place(services, engine, runner, museum):
    """Out of alphabetical order on purpose, so an ordering by address would fail it."""
    run = ask(runner, engine, museum, "Mambo Jumbo", citations=(MARKEL, ARTSY, MARKEL))

    assert list(services.discovery.run_citations(run.id)) == [MARKEL, ARTSY]


def test_a_run_s_citations_survive_a_restart_and_another_run_s_are_not_mixed_in(tmp_path):
    """Varied between opens: a file from before the table, then two runs written, then reopened."""
    path = tmp_path / "catalogue.sqlite"
    first = open_catalogue_file(path)
    first.close()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE run_citations")
    connection.commit()
    connection.close()

    second = open_catalogue_file(path)
    store = SqliteDiscovery(second)
    for run_id in ("run-a", "run-b", "run-c"):
        store.add_run(
            DiscoveryRun(
                id=run_id,
                kind=RunKind.DISCOVERY,
                initiated_by=InitiatedBy.MCP_CLIENT,
                status=RunStatus.RESOLVING_WORKS,
                approval_required=False,
                started_at=datetime(2026, 10, 5, tzinfo=UTC),
            )
        )
    store.add_run_citations("run-a", [MARKEL, ARTSY, MARKEL])
    store.add_run_citations("run-b", [ROUTER])
    second.close()

    third = SqliteDiscovery(open_catalogue_file(path))
    assert list(third.list_run_citations("run-a")) == [MARKEL, ARTSY]
    assert list(third.list_run_citations("run-b")) == [ROUTER]
    assert list(third.list_run_citations("run-c")) == []


# -- as the deployment wires it ---------------------------------------------------


def test_a_runner_given_no_check_uses_the_fetch_policy(services, engine, settings, museum):
    """The default, which is what a deployment gets: `__main__` binds no resolver.
    Literals and a `.local` name only, so the policy decides without DNS."""
    previews = PreviewCache(
        PreviewSettings(art_root=settings.art_root, directory=settings.previews_path), ImageSourcePool([museum]).fetch_preview
    )
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(ImageSourcePool([museum]), box=settings.tv_artwork_box),
        previews=previews,
        spawn=lambda work: work(),
    )
    public = "http://93.184.216.34/artists/1-someone/works"

    ask(
        runner,
        engine,
        museum,
        "Mambo Jumbo",
        citations=("http://nas.local/admin", "http://[fd00::1]/", "http://10.0.0.5/", public),
    )

    assert pages_by_title(museum) == {"Mambo Jumbo": (public,)}


def test_a_citation_that_is_not_a_url_is_refused_and_the_run_s_works_are_still_searched(services, engine, settings, museum):
    """A stored citation is read again on every re-search, so one that raised
    instead of being refused would fail that run's phase 2 for good."""
    previews = PreviewCache(
        PreviewSettings(art_root=settings.art_root, directory=settings.previews_path), ImageSourcePool([museum]).fetch_preview
    )
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(ImageSourcePool([museum]), box=settings.tv_artwork_box),
        previews=previews,
        spawn=lambda work: work(),
    )
    public = "http://93.184.216.34/artists/1-someone/works"

    run = ask(runner, engine, museum, "Mambo Jumbo", citations=("http://[x/", "http://a..b/", public))

    assert services.discovery.get_run(run.id).status is RunStatus.COMPLETED
    assert pages_by_title(museum) == {"Mambo Jumbo": (public,)}


def test_the_container_s_runner_hands_on_only_what_the_real_fetch_policy_passes(
    store, discovery_store, wall_settings, thumbnail_settings, settings, engine, museum
):
    """The shipped check, not a stand-in, through the runner the container builds.

    `.local` and a private literal are refused by the policy itself. `.invalid`
    resolves nowhere for real, so it reaching the finder is the proof that the
    container handed the runner the suite's stated resolver, and that nothing
    here asked real DNS.
    """
    bound = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        previews=PreviewSettings(art_root=settings.art_root, directory=settings.previews_path),
        resolve=lambda _host: ["93.184.216.34"],
        sources=SourceRoster.of(finders=[museum]),
    )
    gallery = "https://gallery.invalid/artists/1-someone/works"
    engine.result = WorkList(
        works=(a_work("Mambo Jumbo", artist="Peter Stephens"),),
        citations=("http://nas.local/admin", "http://192.168.1.1/", MARKEL, gallery),
    )
    museum.holdings = {"Mambo Jumbo": (an_image("Mambo Jumbo", artist="Peter Stephens"),)}

    run = bound.runner.start(intent_text="Peter Stephens's paintings", initiated_by=InitiatedBy.MCP_CLIENT)
    for _ in range(20):
        if bound.runner.run_status(run.id).run.status.is_terminal:
            break

    assert pages_by_title(museum) == {"Mambo Jumbo": (MARKEL, gallery)}
