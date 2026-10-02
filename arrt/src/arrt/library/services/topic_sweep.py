"""Keeping the library's works' topics as facets, from what Wikidata says of them.

A work's topics come from the registry only (`build-plan-topics-and-destinations.md`
§ Requirements Confidence): its own QID gives its century, what it depicts or its
genre, and the kind of work it is; its artist's QID gives the artist's movements. They are written as `work_facets` rows,
`sourced`, with `source_note` "Wikidata" and the topic's QID beside the label, so
the Artworks rail and Library › Topics read them without asking anything.

**What a pass asks about is decided from memory of this process's own passes.**
A work is asked about when this process has not yet asked, when its QID or its
artist's has changed since it last did, or when its answer is older than the
interval. So a start asks about every work once (one query per 200 QIDs:
`topics_of` over the owner's catalogue copy took about a second,
`wikidata-findings.md` § Topics), and an acceptance or a corrected QID costs a
question about that work alone. Nothing persists the memory: a sweep that
crashed costs one more question at the next start, and the facet rows are the
only state anyone reads. A QID matched by the hand-run `python -m arrt.identify`
is another process's write, which nothing announces here: the next daily pass,
or the next start, sees it as a changed QID.

**A pass replaces; it never adds.** A work's Wikidata rows are withdrawn and the
new answer written in one transaction (`CatalogueService.replace_sourced_facets`),
so a topic the registry no longer gives leaves the rail, and an `inferred` row is
never touched. A work whose QIDs were cleared loses its Wikidata rows without a
question being asked. A registry that cannot be asked replaces nothing and is
asked again next pass.

**Off, and saying so once, without `WIKIDATA_USER_AGENT`.** No thread is started,
and the one line says why Library › Topics will stay as it is.
"""

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from arrt.library.registry import ItemId, Registry, RegistryTopicRef, RegistryTopicsOf, RegistryUnavailable
from arrt.library.services.catalogue import CatalogueService, FacetClaim
from arrt.library.services.topics import FACET_KINDS
from arrt.persistence.catalogue import CatalogueStore, WorkQuery
from arrt.persistence.records import Artwork

log = logging.getLogger(__name__)

#: What every row this sweep writes says it came from, and so which rows its
#: next answer replaces.
SOURCE_NOTE: Final[str] = "Wikidata"

#: How old a work's topics may get before a pass asks again, and how long the
#: sweep sleeps between passes when nothing wakes it. A day: a registry's facts
#: about a painting change rarely, and what changes in the library (an
#: acceptance, a QID set by hand) wakes the sweep at once.
INTERVAL_SECONDS: Final[float] = 86_400.0

#: What the sweep's thread is called, in `journalctl` and in a stack dump, and
#: what a test looks for to say it was or was not started.
TOPIC_SWEEP_THREAD_NAME: Final[str] = "topic-sweep"

#: How long a shutdown waits for a pass in flight. A pass waiting on Wikidata
#: holds no lock while it waits, so a bound is enough.
_SHUTDOWN_JOIN_SECONDS: Final[float] = 5.0

#: Works read per page while walking the catalogue.
_PAGE: Final[int] = 500


@dataclass(frozen=True, slots=True)
class TopicSweepResult:
    """What one pass asked about and changed."""

    #: Works whose topics were due: new to this process, re-identified, or stale.
    due: int = 0
    #: Of those, the works with a QID or an artist's QID, which the registry was asked about.
    asked: int = 0
    #: Rows withdrawn and rows the works now carry, across every due work.
    withdrawn: int = 0
    written: int = 0
    #: True when the registry could not be asked, so nothing was replaced.
    unavailable: bool = False


@dataclass(frozen=True, slots=True)
class _Asked:
    """What this process last asked about a work, and when."""

    work_qid: str | None
    artist_qid: str | None
    at: float


class TopicSweep:
    """Write each work's registry topics as its facets, replacing what was there."""

    def __init__(
        self,
        store: CatalogueStore,
        catalogue: CatalogueService,
        registry: Registry | None,
        *,
        interval_seconds: float = INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._catalogue = catalogue
        self._registry = registry
        self._interval = interval_seconds
        self._clock = clock
        self._asked: dict[str, _Asked] = {}
        #: Set by `nudge`, so a waiting loop runs a pass now rather than at the interval.
        self._wake = threading.Event()
        #: One pass at a time: a nudge arriving mid-pass runs the next one.
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        """Whether there is a registry to ask. Without one the sweep does nothing."""
        return self._registry is not None

    def nudge(self) -> None:
        """Ask for a pass soon: a work was accepted or a QID changed. Never blocks, never asks anything itself."""
        self._wake.set()

    def wait_for_work(self) -> None:
        """Wait until nudged, or for the interval, whichever is sooner.

        The nudge is cleared on the way out, before the next pass reads
        anything: a nudge landing after that wakes the pass after, and one
        landing before it is covered by the pass about to run.
        """
        self._wake.wait(self._interval)
        self._wake.clear()

    def run(self) -> TopicSweepResult:
        """Bring every due work's topics up to date. Safe to call at any time, any number of times."""
        registry = self._registry
        if registry is None:
            return TopicSweepResult()
        with self._lock:
            log.debug("sweeping topics", extra={"event": "topics.sweep_started"})
            artist_qids = {artist.id: artist.wikidata_qid for artist in self._store.list_artists()}
            now = self._clock()
            paired = [(work, artist_qids.get(work.artist_id or "")) for work in self._all_works()]
            due = [(work, artist_qid) for work, artist_qid in paired if self._due(work, artist_qid, now)]
            identified = [(work, artist_qid) for work, artist_qid in due if work.wikidata_qid or artist_qid]
            try:
                answer = (
                    registry.topics_of(
                        sorted({work.wikidata_qid for work, _ in identified if work.wikidata_qid}),
                        sorted({artist_qid for _, artist_qid in identified if artist_qid}),
                    )
                    if identified
                    else RegistryTopicsOf()
                )
            except RegistryUnavailable as exc:
                log.warning(
                    "Wikidata could not be asked for the library's topics; the next pass asks again",
                    extra={"event": "topics.sweep_unavailable", "due": len(due), "reason": str(exc)},
                )
                return TopicSweepResult(due=len(due), asked=len(identified), unavailable=True)
            withdrawn = written = 0
            for work, artist_qid in due:
                replaced = self._catalogue.replace_sourced_facets(
                    work.id, source_note=SOURCE_NOTE, claims=claims_for(answer, work.wikidata_qid, artist_qid)
                )
                withdrawn += replaced.withdrawn
                written += replaced.written
                self._asked[work.id] = _Asked(work_qid=work.wikidata_qid, artist_qid=artist_qid, at=now)
            result = TopicSweepResult(due=len(due), asked=len(identified), withdrawn=withdrawn, written=written)
        # At INFO on every pass, including one with nothing due, for the preview
        # sweep's reason: a periodic job that logs only when it acts cannot be
        # told from one that died.
        log.info(
            "swept the library's topics",
            extra={
                "event": "topics.swept",
                "due": result.due,
                "asked": result.asked,
                "withdrawn": result.withdrawn,
                "written": result.written,
            },
        )
        return result

    def _due(self, work: Artwork, artist_qid: str | None, now: float) -> bool:
        asked = self._asked.get(work.id)
        if asked is None:
            return True
        if (asked.work_qid, asked.artist_qid) != (work.wikidata_qid, artist_qid):
            return True
        return now - asked.at >= self._interval

    def _all_works(self) -> list[Artwork]:
        """Every work in the catalogue, archived included: a facet says what a work is, and the rail filters by status."""
        works: list[Artwork] = []
        offset = 0
        while True:
            page = self._store.list_artworks(WorkQuery(), limit=_PAGE, offset=offset)
            works.extend(page.artworks)
            offset += len(page.artworks)
            if not page.artworks or offset >= page.total:
                return works


def claims_for(answer: RegistryTopicsOf, work_qid: str | None, artist_qid: str | None) -> Sequence[FacetClaim]:
    """A work's topics as facet claims: its own, then its artist's movements, in the registry's order.

    Two items of one kind with one name (two "landscape"s) are one facet value,
    which a work carries once; `record_facet` keeps the first it is given, so
    the QID beside the value is the same on every pass.
    """
    refs: list[RegistryTopicRef] = []
    if work_qid is not None:
        refs.extend(answer.works.get(ItemId(work_qid), ()))
    if artist_qid is not None:
        refs.extend(answer.artists.get(ItemId(artist_qid), ()))
    return tuple(FacetClaim(kind=FACET_KINDS[ref.kind], value=ref.label, value_qid=ref.qid) for ref in refs)


def run_topic_sweeps(sweep: TopicSweep, *, stop: threading.Event, after_pass: Callable[[], None] = lambda: None) -> None:
    """Sweep once, then whenever nudged or every interval, until `stop` is set.

    `after_pass` is called once per completed pass: the seam a test counts passes by.
    """
    while not stop.is_set():
        try:
            sweep.run()
        except Exception:  # prawduct:allow prawduct/broad-except -- a background loop that dies stops keeping topics, silently
            log.exception("a topic sweep failed; the next one will try again", extra={"event": "topics.sweep_error"})
        after_pass()
        sweep.wait_for_work()


def start_topic_sweep(sweep: TopicSweep) -> Callable[[], None]:
    """Run the sweep on a daemon thread, returning the call that stops it; or say once that topics are off.

    With no registry nothing is started, and the line saying so is the only one
    the sweep ever writes about it.
    """
    if not sweep.configured:
        log.info(
            "topics are off: WIKIDATA_USER_AGENT is unset, so the library's works are not given topics",
            extra={"event": "topics.off"},
        )
        return lambda: None
    stop = threading.Event()
    thread = threading.Thread(
        target=run_topic_sweeps, args=(sweep,), kwargs={"stop": stop}, name=TOPIC_SWEEP_THREAD_NAME, daemon=True
    )
    thread.start()

    def halt() -> None:
        stop.set()
        sweep.nudge()
        thread.join(timeout=_SHUTDOWN_JOIN_SECONDS)
        if thread.is_alive():
            log.warning(
                "a topic sweep did not stop when asked and is still running",
                extra={"event": "topics.sweep_wedged", "waited_seconds": _SHUTDOWN_JOIN_SECONDS},
            )

    return halt
