"""The Library's two writing services stamp what they write by the clock and ids they were given.

`CatalogueService` and `DiscoveryService` take a clock and an id source, each
defaulting to the machine's, so every construction site is unchanged and a test
can say what time it is. Each case below is one writing method, called through
the service with a clock that answers a different instant on every reading and
an id source that names its ids. Every record the act adds or changes is read
back from the store, and must carry:

- for each new record, an id the source minted during the act, and every id the
  source minted during the act on some record;
- for each time written, the one instant the act read. **An act reads the clock
  once**: a row and the history line beside it, or the runs one repair ends, are
  one moment, so a second reading inside one act is the defect this refuses.

Built from `store` and `discovery_store` directly rather than through the
container, because the container is what must not change (build-plan-audit-wave-2b,
Chunk 43).
"""

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fakes import stored_awaiting_approval

from arrt.library.services.catalogue import CatalogueService, FacetClaim
from arrt.library.services.discovery import ChosenWork, DiscoveryService
from arrt.persistence.catalogue import WorkQuery
from arrt.persistence.discovery_records import InitiatedBy, RunKind, SpendCategory, Verdict
from arrt.persistence.records import (
    AcquisitionMethod,
    EventKind,
    FacetDerivation,
    FetchStatus,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
    VocabularyKind,
)

#: Far from today, so a time the machine's clock wrote cannot pass for one of these.
_START = datetime(2001, 2, 3, 4, 5, 6, tzinfo=UTC)


@dataclass
class TickingClock:
    """A clock that answers a later instant on every reading, and remembers each."""

    read: list[datetime] = field(default_factory=list)

    def __call__(self) -> datetime:
        instant = _START + timedelta(seconds=len(self.read) + 1)
        self.read.append(instant)
        return instant


@dataclass
class NamedIds:
    """An id source whose ids say they are its own."""

    minted: list[str] = field(default_factory=list)

    def __call__(self) -> str:
        minted = f"minted-{len(self.minted) + 1:04d}"
        self.minted.append(minted)
        return minted


@dataclass
class Library:
    catalogue: CatalogueService
    discovery: DiscoveryService
    clock: TickingClock
    ids: NamedIds


@pytest.fixture
def library(store, discovery_store) -> Library:
    clock, ids = TickingClock(), NamedIds()
    catalogue = CatalogueService(store, now=clock, mint_id=ids)
    return Library(
        catalogue=catalogue,
        discovery=DiscoveryService(discovery_store, catalogue, now=clock, mint_id=ids),
        clock=clock,
        ids=ids,
    )


def _everything(lib: Library) -> dict[tuple[str, str], Any]:
    """Every record the two services write, keyed by its kind and id, read back from the stores."""
    catalogue, discovery = lib.catalogue._store, lib.discovery._store
    held: dict[tuple[str, str], Any] = {}

    def keep(records: Any) -> None:
        for record in records:
            held[(type(record).__name__, record.id)] = record

    keep(catalogue.list_artists())
    artworks = catalogue.list_artworks(WorkQuery(), limit=1000, offset=0).artworks
    keep(artworks)
    for artwork in artworks:
        keep(catalogue.list_facets(artwork.id))
        keep(catalogue.list_sources(artwork.id))
        keep(catalogue.list_renditions(artwork.id))
        keep(catalogue.list_mat_colors(artwork.id))
        original = catalogue.get_original(artwork.id)
        keep([] if original is None else [original])
    keep(catalogue.list_events(limit=1000, offset=0).events)
    runs = discovery.list_runs()
    keep(runs)
    for run in runs:
        works = discovery.list_candidate_works(run.id)
        keep(works)
        for work in works:
            keep(discovery.list_candidate_images(work.id))
    keep(discovery.list_spend_records())
    return held


def _times(record: Any) -> dict[str, datetime]:
    return {f.name: getattr(record, f.name) for f in dataclasses.fields(record) if isinstance(getattr(record, f.name), datetime)}


@dataclass
class Written:
    """What one act added or changed, as the stores now hold it."""

    new_ids: set[str]
    times: dict[str, datetime]
    kinds: set[str]


def _act(lib: Library, act: Callable[[], object]) -> tuple[Written, list[datetime], list[str]]:
    before = _everything(lib)
    read_from, minted_from = len(lib.clock.read), len(lib.ids.minted)
    act()
    after = _everything(lib)
    new_ids: set[str] = set()
    times: dict[str, datetime] = {}
    kinds: set[str] = set()
    for key, record in after.items():
        earlier = before.get(key)
        if earlier == record:
            continue
        kinds.add(key[0])
        if earlier is None:
            new_ids.add(record.id)
        old_times = {} if earlier is None else _times(earlier)
        for name, value in _times(record).items():
            if old_times.get(name) != value:
                times[f"{key[0]}.{name}"] = value
    return Written(new_ids, times, kinds), lib.clock.read[read_from:], lib.ids.minted[minted_from:]


# -- the writing methods, each with what it needs first ------------------------


def _work(lib: Library) -> str:
    return lib.catalogue.add_artwork(title="Nighthawks").id


def _work_with_source(lib: Library) -> tuple[str, str]:
    work = _work(lib)
    source = lib.catalogue.add_source(
        artwork_id=work,
        url="https://museum.example/nighthawks",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    return work, source.id


def _work_with_original(lib: Library) -> str:
    work, source = _work_with_source(lib)
    lib.catalogue.record_original(
        artwork_id=work,
        source_id=source,
        path=f"raw/{work}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-1",
        fetch_status=FetchStatus.OK,
    )
    return work


def _get_run(lib: Library, *, artist: str | None = None) -> str:
    return lib.discovery.start_get_run(
        works=[ChosenWork(qid="Q1", title="Nighthawks", artist=artist)], initiated_by=InitiatedBy.WEB_UI
    ).id


def _found_work(lib: Library, *, artist: str | None = None, images: int = 1) -> str:
    """A Get's work holding `images` scans, the first on offer."""
    run = _get_run(lib, artist=artist)
    work = lib.discovery.list_candidate_works(run)[0].id
    for n in range(images):
        lib.discovery.record_image(
            candidate_work_id=work,
            url=f"https://museum.example/scan-{n}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            confidence=0.9,
            estimated_width=6000,
            estimated_height=4000,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
        )
    return work


def _discovery_run(lib: Library) -> str:
    return lib.discovery.start_discovery_run(intent_text="night scenes", initiated_by=InitiatedBy.WEB_UI).id


Act = Callable[[], object]


def _add_artist(lib: Library) -> Act:
    return lambda: lib.catalogue.add_artist(name="Edward Hopper")


def _add_artwork(lib: Library) -> Act:
    return lambda: lib.catalogue.add_artwork(title="Nighthawks")


def _archive_artwork(lib: Library) -> Act:
    work = _work(lib)
    return lambda: lib.catalogue.archive_artwork(work)


def _restore_artwork(lib: Library) -> Act:
    work = _work(lib)
    lib.catalogue.archive_artwork(work)
    return lambda: lib.catalogue.restore_artwork(work)


def _record_event(lib: Library) -> Act:
    return lambda: lib.catalogue.record_event(EventKind.ARCHIVED, detail={"title": "Nighthawks"})


def _record_facet(lib: Library) -> Act:
    work = _work(lib)
    return lambda: lib.catalogue.record_facet(
        artwork_id=work, kind=VocabularyKind.MOVEMENT, value="Realism", derivation=FacetDerivation.SOURCED
    )


def _replace_sourced_facets(lib: Library) -> Act:
    work = _work(lib)
    claims = [
        FacetClaim(kind=VocabularyKind.MOVEMENT, value="Realism"),
        FacetClaim(kind=VocabularyKind.MOVEMENT, value="Urban realism"),
    ]
    return lambda: lib.catalogue.replace_sourced_facets(work, source_note="artic", claims=claims)


def _add_source(lib: Library) -> Act:
    work = _work(lib)
    return lambda: lib.catalogue.add_source(
        artwork_id=work,
        url="https://museum.example/automat",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
    )


def _record_fetch(lib: Library) -> Act:
    _, source = _work_with_source(lib)
    return lambda: lib.catalogue.record_fetch(source, status=FetchStatus.OK)


def _record_original(lib: Library) -> Act:
    work, source = _work_with_source(lib)
    return lambda: lib.catalogue.record_original(
        artwork_id=work,
        source_id=source,
        path="raw/a.tif",
        width=6000,
        height=4000,
        byte_size=1,
        content_hash="hash-1",
        fetch_status=FetchStatus.OK,
    )


def _record_rendition(lib: Library) -> Act:
    work = _work_with_original(lib)
    return lambda: lib.catalogue.record_rendition(
        artwork_id=work,
        kind=RenditionKind.PRESENTATION_MASTER,
        target_width=7680,
        target_height=7680,
        path=f"masters/{work}.jpg",
    )


def _record_mat_color(lib: Library) -> Act:
    work = _work(lib)
    return lambda: lib.catalogue.record_mat_color(artwork_id=work, hex_rgb="#c8c0b0", method=MatMethod.MANUAL)


def _start_discovery_run(lib: Library) -> Act:
    return lambda: _discovery_run(lib)


def _start_get_run(lib: Library) -> Act:
    return lambda: _get_run(lib)


def _start_resolve_run(lib: Library) -> Act:
    work = _found_work(lib)
    return lambda: lib.discovery.start_resolve_run(candidate_work_ids=[work], initiated_by=InitiatedBy.WEB_UI)


def _propose_work(lib: Library) -> Act:
    run = _discovery_run(lib)
    return lambda: lib.discovery.propose_work(
        run_id=run, proposed_title="Automat", rationale="A night scene.", work_dedup_key="hopper::automat"
    )


def _offer_work(lib: Library) -> Act:
    run = _discovery_run(lib)
    lib.discovery.finish_work_list(run)
    return lambda: lib.discovery.offer_work(
        run_id=run,
        title="Automat",
        artist="Edward Hopper",
        rationale="By an artist you asked for.",
        work_dedup_key="hopper::automat",
        offered_for_artist="Edward Hopper",
        offered_artist_matched=1,
        offered_by="artic",
    )


def _record_image(lib: Library) -> Act:
    work = lib.discovery.list_candidate_works(_get_run(lib))[0].id
    return lambda: lib.discovery.record_image(
        candidate_work_id=work,
        url="https://museum.example/scan",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        confidence=0.9,
    )


def _accept(lib: Library) -> Act:
    # Attributed, so the acceptance mints an artist as well as the work and its source.
    work = _found_work(lib, artist="Edward Hopper")
    return lambda: lib.discovery.set_verdict(work, Verdict.ACCEPTED)


def _reject(lib: Library) -> Act:
    work = _found_work(lib)
    return lambda: lib.discovery.set_verdict(work, Verdict.REJECTED)


def _reject_alternate(lib: Library) -> Act:
    work = _found_work(lib, images=2)
    alternate = next(image for image in lib.discovery.list_candidate_images(work) if not image.is_selected)
    return lambda: lib.discovery.reject_image(alternate.id)


def _want_turning_down(lib: Library) -> Act:
    work = _found_work(lib)
    offered = lib.discovery.list_candidate_images(work)[0].id
    return lambda: lib.discovery.want(work, turning_down=offered)


def _record_spend(lib: Library) -> Act:
    return lambda: lib.discovery.record_spend(category=SpendCategory.MAT_COLOR_VISION, cost_usd=Decimal("0.01"))


def _complete_run(lib: Library) -> Act:
    run = _get_run(lib)
    return lambda: lib.discovery.complete_run(run)


def _fail_run(lib: Library) -> Act:
    run = _get_run(lib)
    return lambda: lib.discovery.fail_run(run, reason="the source broke")


def _halt_run_for_budget(lib: Library) -> Act:
    run = _get_run(lib)
    return lambda: lib.discovery.halt_run_for_budget(run, reason="the provider refused")


def _cancel_run(lib: Library) -> Act:
    run = _get_run(lib)
    return lambda: lib.discovery.cancel_run(run)


def _decline_run(lib: Library) -> Act:
    run = stored_awaiting_approval(lib.discovery._store, _discovery_run(lib))
    return lambda: lib.discovery.decline_run(run)


def _reconcile(lib: Library) -> Act:
    # Two runs a dead process left, so one repair ends two and both must carry its one instant.
    _get_run(lib)
    lib.discovery.start_get_run(works=[ChosenWork(qid="Q2", title="Automat")], initiated_by=InitiatedBy.WEB_UI)
    return lib.discovery.reconcile


#: Each writing method: given the services, do what it needs first and return the act.
#: `stamps` and `mints` say whether the act writes a time and an id, so a case that
#: wrote neither cannot pass by writing nothing.
CASES: dict[str, tuple[Callable[[Library], Act], bool, bool]] = {
    "catalogue.add_artist": (_add_artist, False, True),
    "catalogue.add_artwork": (_add_artwork, True, True),
    "catalogue.archive_artwork": (_archive_artwork, True, True),
    "catalogue.restore_artwork": (_restore_artwork, True, True),
    "catalogue.record_event": (_record_event, True, True),
    "catalogue.record_facet": (_record_facet, True, True),
    "catalogue.replace_sourced_facets": (_replace_sourced_facets, True, True),
    "catalogue.add_source": (_add_source, False, True),
    "catalogue.record_fetch": (_record_fetch, True, False),
    "catalogue.record_original": (_record_original, False, True),
    "catalogue.record_rendition": (_record_rendition, True, True),
    "catalogue.record_mat_color": (_record_mat_color, True, True),
    "discovery.start_discovery_run": (_start_discovery_run, True, True),
    "discovery.start_get_run": (_start_get_run, True, True),
    "discovery.start_resolve_run": (_start_resolve_run, True, True),
    "discovery.propose_work": (_propose_work, False, True),
    "discovery.offer_work": (_offer_work, False, True),
    "discovery.record_image": (_record_image, False, True),
    "discovery.set_verdict accepted": (_accept, True, True),
    "discovery.set_verdict rejected": (_reject, True, True),
    "discovery.reject_image": (_reject_alternate, True, False),
    "discovery.want turning down": (_want_turning_down, True, False),
    "discovery.record_spend": (_record_spend, True, True),
    "discovery.complete_run": (_complete_run, True, True),
    "discovery.fail_run": (_fail_run, True, True),
    "discovery.halt_run_for_budget": (_halt_run_for_budget, True, True),
    "discovery.cancel_run": (_cancel_run, True, True),
    "discovery.decline_run": (_decline_run, True, True),
    "discovery.reconcile": (_reconcile, True, True),
}


@pytest.mark.parametrize("case", list(CASES))
def test_every_record_an_act_writes_carries_the_clock_and_ids_the_service_was_given(library: Library, case: str):
    prepare, stamps, mints = CASES[case]
    act = prepare(library)

    written, read, minted = _act(library, act)

    assert len(read) <= 1, f"{case} read the clock {len(read)} times in one act: {read}"
    if stamps:
        assert written.times, f"{case} wrote no time, so this case tests nothing about the clock"
        assert set(written.times.values()) == set(
            read
        ), f"{case} wrote times the act's one reading ({read}) did not give: {written.times}"
    else:
        assert not written.times, f"{case} wrote times it was not expected to: {written.times}"
    if mints:
        assert written.new_ids, f"{case} wrote no record, so this case tests nothing about ids"
    assert written.new_ids == set(
        minted
    ), f"{case} wrote ids {sorted(written.new_ids)} where the id source minted {minted} during the act"


#: What a method's source calls when it stamps or mints, itself or through a helper.
_WRITES = ("self._now", "self._mint_id", "self._ended(", "self._end_active(", "self._turn_down(", "self._record_facet(")


def test_the_cases_cover_every_public_writer_that_mints_or_stamps():
    """A writer added to either service that reads the clock or mints an id needs a case here.

    Read from the source of each service: a public method whose body (or a private
    helper only it reaches) calls `self._now` or `self._mint_id` is named in `CASES`.
    """
    import inspect

    named = {case.split(" ")[0] for case in CASES}
    missing: list[str] = []
    for prefix, cls in (("catalogue", CatalogueService), ("discovery", DiscoveryService)):
        for name, member in inspect.getmembers(cls, inspect.isfunction):
            if name.startswith("_"):
                continue
            body = inspect.getsource(member)
            if any(marker in body for marker in _WRITES) and f"{prefix}.{name}" not in named:
                missing.append(f"{prefix}.{name}")
    assert not missing, f"writers with no case: {missing}"


def test_a_service_built_without_a_clock_or_id_source_still_reads_the_machines(store, discovery_store):
    """The defaults are the machine's, so the container and the seed construct both as before."""
    catalogue = CatalogueService(store)
    discovery = DiscoveryService(discovery_store, catalogue)
    before = datetime.now(UTC)

    work = catalogue.add_artwork(title="Nighthawks")
    run = discovery.start_get_run(works=[ChosenWork(qid="Q1", title="Nighthawks")], initiated_by=InitiatedBy.WEB_UI)

    assert work.created_at >= before
    assert run.started_at >= before
    assert run.kind is RunKind.GET
    assert work.id != run.id
    assert len(work.id) == 36
    assert len(run.id) == 36
