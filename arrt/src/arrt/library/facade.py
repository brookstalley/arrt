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

import logging
from collections.abc import Iterable, Sequence
from dataclasses import replace

from arrt.library.events import WorkChange, WorkChanged, WorkChangedHandler
from arrt.library.readiness import (
    Media,
    PlayableWork,
    Unplayable,
    UnplayableReason,
    WorkInputs,
    assess,
    not_in_catalogue,
    playable_from,
    tv_rendition_of,
)
from arrt.library.services.catalogue import CatalogueService

log = logging.getLogger(__name__)

#: One work's answer: it can go on a wall, or it cannot and here is why.
type Playability = PlayableWork | Unplayable

__all__ = [
    "LibraryFacade",
    "Media",
    "Playability",
    "PlayableWork",
    "Unplayable",
    "UnplayableReason",
    "WorkChange",
    "WorkChanged",
    "WorkChangedHandler",
]


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

    def accepted_work_ids(self) -> Sequence[str]:
        """Every work in circulation, oldest first.

        For a startup catch-up of an announcement a crash lost: Programming asks
        which works exist, here, rather than reading the Library's tables.
        """
        return self._catalogue.accepted_work_ids()

    def subscribe(self, handler: WorkChangedHandler) -> None:
        """Be told which work changed, after each change commits.

        The announcement names the work and what happened, and nothing else. A
        subscriber that needs to know whether the work can still go on a wall
        asks `playable`, which is the only verdict there is. After a split this
        is a webhook registration.
        """
        self._catalogue.subscribe(handler)

    def _answer(self, work_id: str) -> Playability:
        inputs = self._gather(work_id)
        if inputs is None:
            return not_in_catalogue(work_id)
        refused = assess(inputs)
        if refused is not None:
            return refused
        # Hashed on first need for a render recorded before hashes were, so the
        # answer can say where its bytes are and how to check them.
        rendition = self._catalogue.with_content(inputs.tv_rendition) if inputs.tv_rendition else None
        playable = playable_from(replace(inputs, tv_rendition=rendition))
        if playable.media is None:
            # Said here, where the gap is decided: the work still reaches a wall
            # on the file channel, which reads `render_path`, and a Player on HTTP
            # skips it. Without this line that Player's wall would be one work
            # short with nothing on the server saying which or why.
            log.warning(
                "Work %s is offered without media: its render at %s could not be read or is not a JPEG or PNG. "
                "A Player on HTTP skips it until the render is readable.",
                work_id,
                playable.render_path,
            )
        return playable

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
