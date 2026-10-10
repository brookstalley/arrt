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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Final

from arrt.library.dimensions import Units
from arrt.library.events import WorkChange, WorkChanged, WorkChangedHandler
from arrt.library.readiness import (
    Media,
    PlayableWork,
    Unplayable,
    UnplayableReason,
    WorkInputs,
    assess,
    label_of,
    master_rendition_of,
    not_in_catalogue,
    playable_from,
    tv_rendition_of,
)
from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.discovery import DiscoveryService
from arrt.persistence.records import EventKind
from arrt.services.errors import ServiceError

log = logging.getLogger(__name__)

#: One work's answer: it can go on a wall, or it cannot and here is why.
type Playability = PlayableWork | Unplayable

#: The acts Programming performs that the Library's history records. Programming
#: may record these and no others: a Get or a verdict is the Library's own act,
#: written where it happens.
PROGRAMMING_ACTS: Final[frozenset[EventKind]] = frozenset(
    {EventKind.HUNG, EventKind.LEFT_THEME, EventKind.EXCLUDED, EventKind.ALLOWED}
)


@dataclass(frozen=True, slots=True)
class ProgrammingAct:
    """One act on the walls, for the history: plain ids and plain words, as a request body would carry.

    The wall and the theme are Programming's, and the Library keeps their ids
    without knowing what they name, which is why `detail` carries the words the
    history is read by (a theme's name, whether it was a selection).
    """

    kind: EventKind
    wall_id: str | None = None
    theme_id: str | None = None
    work_id: str | None = None
    detail: Mapping[str, object] = field(default_factory=dict)


__all__ = [
    "PROGRAMMING_ACTS",
    "EventKind",
    "LibraryFacade",
    "Media",
    "Playability",
    "PlayableWork",
    "ProgrammingAct",
    "Unplayable",
    "UnplayableReason",
    "WorkChange",
    "WorkChanged",
    "WorkChangedHandler",
]


class LibraryFacade:
    """What Programming may ask the Library."""

    def __init__(self, catalogue: CatalogueService, discovery: DiscoveryService, *, label_units: Units) -> None:
        self._catalogue = catalogue
        self._discovery = discovery
        #: The system every label this facade sets states dimensions in.
        self._label_units = label_units

    def playable(self, work_ids: Iterable[str]) -> dict[str, Playability]:
        """Whether each work can go on a wall, keyed by id, in the order asked.

        **Every id asked about is answered**, including one the catalogue does
        not hold, which comes back as `NOT_IN_CATALOGUE` rather than raising.
        Programming holds work ids as references that may fail to resolve, and a
        call that raised on the first one would make a theme holding one
        dangling reference unbuildable. An id asked twice is answered once.
        """
        return {work_id: self._answer(work_id) for work_id in dict.fromkeys(work_ids)}

    def labels(self, work_ids: Iterable[str]) -> dict[str, Mapping[str, str | None] | None]:
        """Each work's label text, keyed by id, or None for an id the catalogue does not hold.

        The same ten keys `playable` carries, from the same function, for a
        reader that needs the words and not whether the work can go on a wall:
        a label captioning a picture already on a screen. Asked about once a
        second per label, so it reads only the work and its artist, and says
        nothing in the journal.
        """
        answers: dict[str, Mapping[str, str | None] | None] = {}
        for work_id in dict.fromkeys(work_ids):
            detail = self._catalogue.find_artwork(work_id)
            answers[work_id] = None if detail is None else label_of(detail.artwork, detail.artist, units=self._label_units)
        return answers

    def accepted_work_ids(self) -> Sequence[str]:
        """Every work in circulation, oldest first.

        For a startup catch-up of an announcement a crash lost: Programming asks
        which works exist, here, rather than reading the Library's tables.
        """
        return self._catalogue.accepted_work_ids()

    def destinations(self, work_ids: Iterable[str]) -> dict[str, str | None]:
        """Where each accepted work was sent: a theme id, or None for the default theme.

        A Get may name the theme its accepted works join instead of the default,
        and this is how Programming learns it, for a work announced as accepted
        and for one a startup catch-up finds, so the two land a work in the same
        theme. **Every id asked about is answered**, None included for a work
        whose run named no theme, one no run minted, and one the catalogue does
        not hold. The id is Programming's own, carried opaquely: the Library does
        not know whether that theme still exists, and Programming decides what a
        deleted one means.
        """
        return dict(self._discovery.destinations(work_ids))

    def record(self, act: ProgrammingAct) -> None:
        """Write an act on the walls into the Library's history.

        **After Programming's own change has committed, never inside it**,
        because once the two sides have separate stores no transaction spans
        them, and recording an act that then rolled back would put a hang in the
        history that never happened. A crash between the two loses the line,
        which is the cheaper failure for a history. After a split this is a POST.

        **The one call here that writes, and it is not idempotent**: asked twice,
        it records two lines. Every other call answers the same while nothing
        has changed.
        """
        if act.kind not in PROGRAMMING_ACTS:
            allowed = ", ".join(sorted(str(kind) for kind in PROGRAMMING_ACTS))
            raise ServiceError(f"Programming records only acts on the walls ({allowed}), not {act.kind}.")
        self._catalogue.record_event(act.kind, wall_id=act.wall_id, theme_id=act.theme_id, work_id=act.work_id, detail=act.detail)

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
        master = self._catalogue.with_content(inputs.master) if inputs.master else None
        size = self._catalogue.pixel_size(master) if master is not None else None
        playable = playable_from(
            replace(inputs, tv_rendition=rendition, master=master, master_size=size), units=self._label_units
        )
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
        original = self._catalogue.get_original(work_id)
        renditions = [view.rendition for view in self._catalogue.list_renditions(work_id)]
        return WorkInputs(
            artwork=detail.artwork,
            artist=detail.artist,
            original=original,
            tv_rendition=tv_rendition_of(renditions),
            mat_color=self._catalogue.current_mat_color(work_id),
            master=master_rendition_of(renditions, original),
        )
