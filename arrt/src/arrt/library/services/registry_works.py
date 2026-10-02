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
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from arrt.library.registry import Registry, RegistryUnavailable, RegistryWork
from arrt.library.services.artists import REGISTRY_KEPT_FOR, artist_ids_by_qid
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
    #: The library's artist for each creator it holds, by the creator's QID.
    artists: Mapping[str, str] = field(default_factory=dict)


class RegistryWorkService:
    """Ask the registry about one work, and say what the library holds of it."""

    def __init__(self, store: CatalogueStore, registry: Registry | None, *, kept: KeptAnswers) -> None:
        self._store = store
        self._registry = registry
        self._kept: Kept[str, RegistryWork] = kept.namespace(
            "registry.work", codec=JsonCodec(RegistryWork), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )

    def view(self, qid: str) -> RegistryWorkView:
        checked_qid(qid)
        held = tuple(self._store.circulating_ids_by_qid().get(qid, ()))
        if self._registry is None:
            return RegistryWorkView(
                state=RegistryWorkState.NOT_CONFIGURED,
                note=NOT_CONFIGURED_NOTE,
                held=held,
            )
        try:
            known = self._known(qid, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata about work %s: %s", qid, exc)
            return RegistryWorkView(
                state=RegistryWorkState.UNAVAILABLE,
                note="Wikidata could not be asked just now. Try again later.",
                held=held,
            )
        if known is None:
            return RegistryWorkView(
                state=RegistryWorkState.NOT_FOUND,
                note=f"Wikidata has no item {qid}. It may have been merged into another, or the address is mistyped.",
                held=held,
            )
        ours = artist_ids_by_qid(self._store)
        return RegistryWorkView(
            state=RegistryWorkState.KNOWN,
            known=known,
            held=held,
            artists={creator.qid: ours[creator.qid] for creator in known.creators if creator.qid in ours},
        )

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
