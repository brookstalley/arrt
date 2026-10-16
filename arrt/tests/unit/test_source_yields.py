"""What each source has given the library, counted from the records in one statement.

Status's sources table states, for each installed source, how many images it has
offered, how many held works chose one of them, how many of those no other source
offered anything for, and how large its images usually are. These are the figures
that tell a curator what a source is worth, so each is pinned here against a
library holding the case that would make it wrong: an address offered twice, a
work found again in another run, a source that offered an image for a held work
without being chosen, a scan taller than it is wide.
"""

from datetime import UTC, datetime

import pytest
from fakes import FakeReader

from arrt.library.sources.artic import claims as artic_claims
from arrt.library.sources.loading import SourceRoster
from arrt.persistence.discovery_records import (
    CandidateImage,
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    RunKind,
    RunStatus,
    SourceYield,
)
from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

_STARTED = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


@pytest.fixture
def library(service, discovery_store):
    """Writers for the three kinds of record a yield is counted from."""

    class Library:
        def __init__(self) -> None:
            self.serial = 0

        def _next(self, prefix: str) -> str:
            self.serial += 1
            return f"{prefix}{self.serial}"

        def run(self) -> str:
            run_id = self._next("r")
            discovery_store.add_run(
                DiscoveryRun(
                    id=run_id,
                    kind=RunKind.DISCOVERY,
                    initiated_by=InitiatedBy.MCP_CLIENT,
                    status=RunStatus.COMPLETED,
                    approval_required=False,
                    started_at=_STARTED,
                )
            )
            return run_id

        def proposal(self, key: str, *, artwork_id: str | None = None) -> str:
            work_id = self._next("c")
            discovery_store.add_candidate_work(
                CandidateWork(
                    id=work_id,
                    discovery_run_id=self.run(),
                    proposed_title=key,
                    rationale="Asked for.",
                    work_dedup_key=key,
                    artwork_id=artwork_id,
                )
            )
            return work_id

        def offer(self, work_id: str, provider: str, url: str, *, width=None, height=None, rejected=False) -> None:
            discovery_store.add_candidate_image(
                CandidateImage(
                    id=self._next("i"),
                    candidate_work_id=work_id,
                    url=url,
                    provider=provider,
                    source_class=SourceClass.INSTITUTIONAL,
                    acquisition_method=AcquisitionMethod.DEZOOMIFY,
                    confidence=0.9,
                    estimated_width=width,
                    estimated_height=height,
                    rejected_at=_STARTED if rejected else None,
                )
            )

        def held(self, title: str, primary: str, *, also: tuple[str, ...] = ()) -> str:
            artwork = service.add_artwork(title=title)
            for provider in (primary, *also):
                service.add_source(
                    artwork_id=artwork.id,
                    url=f"https://{provider}.example/{artwork.id}",
                    provider=provider,
                    source_class=SourceClass.INSTITUTIONAL,
                    acquisition_method=AcquisitionMethod.DEZOOMIFY,
                    rights_status=RightsStatus.PUBLIC_DOMAIN,
                    is_primary=provider == primary,
                )
            return artwork.id

    return Library()


def test_an_address_offered_again_is_one_offer_and_a_turned_down_one_still_counts(library, discovery_store):
    first = library.proposal("monet::water-lilies")
    again = library.proposal("monet::water-lilies")
    library.offer(first, "met", "https://met.example/1")
    library.offer(again, "met", "https://met.example/1")
    library.offer(again, "met", "https://met.example/2", rejected=True)

    assert discovery_store.source_yields()["met"].offered == 2


def test_a_held_works_sources_are_offers_even_with_no_search_behind_them(library, discovery_store):
    """A work held from before searches recorded candidates still counts the source that gave it."""
    library.held("Nighthawks", "artic")

    found = discovery_store.source_yields()["artic"]
    assert (found.offered, found.chosen, found.only_here) == (1, 1, 1)


def test_chosen_counts_the_works_whose_primary_source_is_the_provider(library, discovery_store):
    library.held("One", "met")
    library.held("Two", "met", also=("artic",))
    library.held("Three", "artic", also=("met",))

    found = discovery_store.source_yields()
    assert (found["met"].chosen, found["artic"].chosen) == (2, 1)
    # Both offered for every work they were a source of, chosen or not.
    assert (found["met"].offered, found["artic"].offered) == (3, 2)


def test_only_here_excludes_a_work_another_source_offered_anything_for(library, discovery_store):
    alone = library.held("Alone", "met")
    library.held("Shared in the catalogue", "met", also=("artic",))
    found_again = library.held("Found again elsewhere", "met")
    # The proposal acceptance minted the work from, and another run's proposal of
    # the same work, where a second source answered: that source offered it too.
    library.offer(library.proposal("found-again", artwork_id=found_again), "met", "https://met.example/fa")
    library.offer(library.proposal("found-again"), "smk", "https://smk.example/fa")
    # A second offer from the chosen source itself takes nothing away.
    library.offer(library.proposal("alone", artwork_id=alone), "met", "https://met.example/alone-2")

    found = discovery_store.source_yields()
    assert (found["met"].chosen, found["met"].only_here) == (3, 1)
    assert (found["smk"].chosen, found["smk"].only_here) == (0, 0)


def test_the_median_long_edge_is_the_middle_known_size_and_the_mean_of_two_middles(library, discovery_store):
    work = library.proposal("sizes")
    # Odd: 3000, 4000 (a portrait scan, so its height), 9000; one unsized, not counted.
    library.offer(work, "met", "https://met.example/a", width=3000, height=2000)
    library.offer(work, "met", "https://met.example/b", width=2500, height=4000)
    library.offer(work, "met", "https://met.example/c", width=9000, height=6000)
    library.offer(work, "met", "https://met.example/d")
    # Even: 1000 and 3000 either side, so the mean of the two middle ones.
    for index, edge in enumerate((1000, 2000, 2400, 3000)):
        library.offer(work, "smk", f"https://smk.example/{index}", width=edge, height=edge // 2)
    library.offer(work, "artic", "https://artic.example/unsized")

    found = discovery_store.source_yields()
    assert found["met"].median_long_edge == 4000
    assert found["smk"].median_long_edge == 2200
    assert found["artic"].median_long_edge is None


def test_a_provider_with_nothing_recorded_is_absent(discovery_store):
    assert discovery_store.source_yields() == {}


@pytest.fixture
def sources() -> SourceRoster:
    """The Art Institute's reader, as the suite's roster has it, and a declined SMK that has offered nothing."""
    return SourceRoster.of(
        readers={"artic": (artic_claims, FakeReader())},
        unavailable={"smk": (lambda _url: False, "SMK_USER_AGENT is unset")},
    )


def test_the_health_service_gives_every_installed_source_a_row_and_no_other(services, library):
    """In the roster's order; zeros for one with nothing recorded; nothing for a provider no longer installed."""
    library.held("Nighthawks", "artic")
    library.held("A seed work", "an-uninstalled-source")

    rows = services.health.observe_yields()

    assert rows == (
        SourceYield(provider="artic", offered=1, chosen=1, only_here=1, median_long_edge=None),
        SourceYield(provider="smk", offered=0, chosen=0, only_here=0, median_long_edge=None),
    )
