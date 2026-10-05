"""One work as a registry knows it, for the page of a work the library may not hold.

Ruling 2 puts the library and the registry in one world: a work Wikidata lists
has a page here whether or not the library holds it, instead of a link out. The
page asks this by QID. A QID the library holds is answered with the works that
are it, so the page can send the curator to the library's own; one it does not
is answered with what the registry says, and with the library's artist for any
creator it holds, so the page can link there rather than out.

**Kept per work for a week, across restarts**, as the Artist page's half is: a
work's facts change rarely and a curator going back and forth between a work
and its artist should not wait on the network each time. A failure is not
kept, so the next visit asks again.

**Its picture's pixel size is asked of the registry too, and judged against
the wall** by `assess_display_fit`, the function the review grid's verdict
comes from, so the page and the review cannot disagree about one file. The
size is kept per file, as the work is per QID. Only Commons knows it, and
Commons can be down while the query service answers, so a failure to ask
leaves the work known and its size unknown, and is not kept. The verdict is
on the file as Commons holds it: a Get of a file wider than Commons' widest
rendering fetches that rendering, which on a panel no wider than it judges
the same.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from arrt.library.registry import CommonsFile, Registry, RegistryImageSize, RegistryUnavailable, RegistryWork
from arrt.library.services.artists import REGISTRY_KEPT_FOR, WantedItems, artist_ids_by_qid
from arrt.library.services.display_fit import ArtworkBox, FitAssessment, assess_display_fit
from arrt.library.services.remembered import NOT_CONFIGURED_NOTE, REMEMBERED, checked_qid
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.kept import JsonCodec, Kept, KeptAnswers

log = logging.getLogger(__name__)


class RegistryWorkState(StrEnum):
    """Why a registry work's page says what it says."""

    #: The registry answered with the work.
    KNOWN = "known"
    #: The registry was asked and has no such item.
    NOT_FOUND = "not_found"
    #: No registry is configured (`WIKIDATA_USER_AGENT` unset).
    NOT_CONFIGURED = "not_configured"
    #: The registry was asked and could not answer.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RegistryWorkView:
    """A registry work's page: the work, or why there is none, and what the library holds of it."""

    state: RegistryWorkState
    #: A sentence for the curator when the state is not `KNOWN`.
    note: str | None = None
    known: RegistryWork | None = None
    #: The library's works in circulation that are this one, by QID. Answered
    #: whatever the registry is doing, because it is the library's to say.
    held: Sequence[str] = ()
    #: A wanted work names this item. Answered whatever the registry is doing,
    #: as `held` is, because it is the library's to say.
    wanted: bool = False
    #: The library's artist for each creator it holds, by the creator's QID.
    artists: Mapping[str, str] = field(default_factory=dict)
    #: The pixel size of the work's picture, where it has one and Commons said.
    image_size: RegistryImageSize | None = None
    #: How that picture would meet this deployment's wall, beside its size.
    fit: FitAssessment | None = None


class RegistryWorkService:
    """Ask the registry about one work, and say what the library holds of it."""

    def __init__(
        self, store: CatalogueStore, registry: Registry | None, *, kept: KeptAnswers, wanted: WantedItems, box: ArtworkBox
    ) -> None:
        self._store = store
        self._registry = registry
        self._wanted = wanted
        self._box = box
        self._kept: Kept[str, RegistryWork] = kept.namespace(
            "registry.work", codec=JsonCodec(RegistryWork), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )
        self._sizes: Kept[str, RegistryImageSize] = kept.namespace(
            "registry.image_size", codec=JsonCodec(RegistryImageSize), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )

    def view(self, qid: str) -> RegistryWorkView:
        checked_qid(qid)
        held = tuple(self._store.circulating_ids_by_qid().get(qid, ()))
        wanted = qid in self._wanted.wanted_qids()
        if self._registry is None:
            return RegistryWorkView(
                state=RegistryWorkState.NOT_CONFIGURED,
                note=NOT_CONFIGURED_NOTE,
                held=held,
                wanted=wanted,
            )
        try:
            known = self._known(qid, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata about work %s: %s", qid, exc)
            return RegistryWorkView(
                state=RegistryWorkState.UNAVAILABLE,
                note="Wikidata could not be asked just now. Try again later.",
                held=held,
                wanted=wanted,
            )
        if known is None:
            return RegistryWorkView(
                state=RegistryWorkState.NOT_FOUND,
                note=f"Wikidata has no item {qid}. It may have been merged into another, or the address is mistyped.",
                held=held,
                wanted=wanted,
            )
        ours = artist_ids_by_qid(self._store)
        size = None if known.image is None else self._size(known.image, self._registry)
        return RegistryWorkView(
            state=RegistryWorkState.KNOWN,
            known=known,
            held=held,
            wanted=wanted,
            artists={creator.qid: ours[creator.qid] for creator in known.creators if creator.qid in ours},
            image_size=size,
            fit=None if size is None else assess_display_fit(width=size.width, height=size.height, box=self._box),
        )

    def _size(self, image: CommonsFile, registry: Registry) -> RegistryImageSize | None:
        kept = self._sizes.get(image)
        if kept is not None:
            return kept
        try:
            size = registry.image_size(image)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Commons how big %s is: %s", image, exc)
            return None
        if size is not None:
            # A missing file is not kept, as a missing item is not: it can be uploaded.
            self._sizes.put(image, size)
        return size

    def _known(self, qid: str, registry: Registry) -> RegistryWork | None:
        kept = self._kept.get(qid)
        if kept is not None:
            return kept
        # Asked between `get` and `put`, under no lock, as the Artist page's half
        # is: another page must not wait on this one's query.
        known = registry.work(qid)
        if known is None:
            # Not kept either: an item can be created, and a curator who
            # mistyped will try again with the right one.
            return None
        self._kept.put(qid, known)
        return known
