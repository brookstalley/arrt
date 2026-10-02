"""Get: acquire works the curator chose from the registry, by their Wikidata items.

The action ruling 3 of `ia-proposal.md` makes of Add New: a selection of works,
each named by its item, becomes one run that looks for their images. This
service decides which of the chosen items a Get asks for, and the runner does
the asking.

**An item is skipped, never refused, when it cannot be asked for**: one the
library already holds, one a Get under way is already looking for, and one the
registry has no work for. A selection usually mixes these, and a Get that
refused the whole selection over one held work would make the curator untick it
by hand to get the rest. Every skip is reported with its reason.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from arrt.library.registry import Registry, RegistryUnavailable
from arrt.library.services.discovery import ChosenWork, DiscoveryService
from arrt.library.services.remembered import checked_qid
from arrt.library.services.runner import DiscoveryRunner
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.discovery_records import DiscoveryRun, InitiatedBy
from arrt.services.errors import ServiceError

log = logging.getLogger(__name__)

#: The most items one Get asks for. Each new item is one Wikidata lookup made
#: while the request waits, so the bound is on the request's length; a page of
#: the Artist hub or the results page shows fewer works than this.
MAX_ITEMS_PER_GET = 50


class SkipReason(StrEnum):
    """Why a chosen item was left out of a Get."""

    HELD = "held"
    BEING_GOT = "being_got"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class Skipped:
    qid: str
    reason: SkipReason


@dataclass(frozen=True, slots=True)
class GetOutcome:
    """The run a Get started, if any work was left to ask for, and what it skipped."""

    run: DiscoveryRun | None
    skipped: tuple[Skipped, ...]


class GetService:
    """Turn a selection of Wikidata items into one Get."""

    def __init__(
        self,
        *,
        store: CatalogueStore,
        discovery: DiscoveryService,
        runner: DiscoveryRunner,
        registry: Registry | None,
    ) -> None:
        self._store = store
        self._discovery = discovery
        self._runner = runner
        self._registry = registry

    def start(self, qids: Sequence[str], *, initiated_by: InitiatedBy) -> GetOutcome:
        """Start a Get over the chosen items that can be asked for, and report the rest.

        Refused outright with no registry, because a Get names its works by
        item and nothing else can say what an item is. A registry that cannot be
        asked is refused too: nothing has been started, and trying again later
        is the curator's whole remedy.
        """
        if not qids:
            raise ServiceError("A Get needs at least one work.")
        if len(set(qids)) > MAX_ITEMS_PER_GET:
            raise ServiceError(
                f"A Get asks for at most {MAX_ITEMS_PER_GET} works, and this asked for {len(set(qids))}. "
                "Nothing was started; split the selection."
            )
        wanted = list(dict.fromkeys(checked_qid(qid) for qid in qids))
        if self._registry is None:
            raise ServiceError(
                "A Get names its works by their Wikidata items, and this deployment has no registry "
                "(WIKIDATA_USER_AGENT is unset). Nothing was started."
            )
        held = self._store.circulating_ids_by_qid()
        being_got = self._discovery.items_being_got()
        skipped: list[Skipped] = []
        chosen: list[ChosenWork] = []
        for qid in wanted:
            if qid in held:
                skipped.append(Skipped(qid, SkipReason.HELD))
                continue
            if qid in being_got:
                skipped.append(Skipped(qid, SkipReason.BEING_GOT))
                continue
            try:
                work = self._registry.work(qid)
            except RegistryUnavailable as exc:
                raise ServiceError(f"Wikidata could not be asked about {qid}, so nothing was started. Try again.") from exc
            if work is None:
                skipped.append(Skipped(qid, SkipReason.NOT_FOUND))
                continue
            chosen.append(ChosenWork(qid=qid, title=work.title, artist=work.creators[0].name if work.creators else None))
        run = self._runner.get(works=chosen, initiated_by=initiated_by) if chosen else None
        log.info(
            "a get was asked for",
            extra={
                "event": "get.asked",
                "started_run_id": None if run is None else run.id,
                "works_chosen": len(chosen),
                "skipped": {str(reason): sum(1 for s in skipped if s.reason is reason) for reason in SkipReason},
            },
        )
        return GetOutcome(run=run, skipped=tuple(skipped))
