"""The Library as Programming sees it: the one module Programming may import.

**Written as if the Library were already on another host** (`architecture.md`
§ Direction, the Library/Programming seam, rule 2). A call takes ids and returns
plain frozen data: never a store record, never a handle that reads more later.
It is coarse, answering a whole theme in one call rather than one work per
call, and asking twice returns the same answer while nothing has changed. If
Programming ever runs as its own process, this class becomes a client for an
HTTP endpoint with the same shape, and nothing that calls it changes.

`tests/preferences/test_seam_imports.py` holds the import half of the rule:
Programming reaches nothing in the Library but this module, and the Library
reaches nothing in Programming.
"""

from collections.abc import Iterable

from curatarr.library.readiness import (
    PlayableWork,
    Unplayable,
    UnplayableReason,
    WorkInputs,
    assess,
    not_in_catalogue,
    playable_from,
    tv_rendition_of,
)
from curatarr.library.services.catalogue import CatalogueService

#: One work's answer: it can go on a wall, or it cannot and here is why.
type Playability = PlayableWork | Unplayable

__all__ = ["LibraryFacade", "Playability", "PlayableWork", "Unplayable", "UnplayableReason"]


class LibraryFacade:
    """What Programming may ask the Library."""

    def __init__(self, catalogue: CatalogueService) -> None:
        self._catalogue = catalogue

    def playable(self, work_ids: Iterable[str]) -> dict[str, Playability]:
        """Whether each work can go on a wall, keyed by id, in the order asked.

        **Every id asked about is answered**, including one the catalogue does
        not hold, which comes back as `NOT_IN_CATALOGUE` rather than raising.
        Programming holds work ids as references that may fail to resolve, and a
        call that raised on the first one would make a theme holding one
        dangling reference unbuildable. An id asked twice is answered once.
        """
        return {work_id: self._answer(work_id) for work_id in dict.fromkeys(work_ids)}

    def _answer(self, work_id: str) -> Playability:
        inputs = self._gather(work_id)
        if inputs is None:
            return not_in_catalogue(work_id)
        refused = assess(inputs)
        return refused if refused is not None else playable_from(inputs)

    def _gather(self, work_id: str) -> WorkInputs | None:
        """Collect everything the readiness rule judges one work on, or None if it is not held.

        Everything comes through the catalogue service, because it owns what
        each of these means. Renditions reached straight past it into the store
        until 2026-08-05, and the hazard was the one the mat colour was already
        routed around: a second path to the same fact decides manifest
        membership while the first decides everything else, and only one of them
        is updated when the rule changes.
        """
        detail = self._catalogue.find_artwork(work_id)
        if detail is None:
            return None
        return WorkInputs(
            artwork=detail.artwork,
            artist=detail.artist,
            original=self._catalogue.get_original(work_id),
            tv_rendition=tv_rendition_of([view.rendition for view in self._catalogue.list_renditions(work_id)]),
            mat_color=self._catalogue.current_mat_color(work_id),
        )
