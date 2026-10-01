"""What the Library announces when a work changes, and the in-process publisher that carries it.

`architecture.md` § Direction, the Library/Programming seam, rule 4: Library
changes reach Programming as events, and Programming never reads Library tables
to find out what changed. In one process the publisher calls each subscriber in
turn. After a split, the same announcements become webhooks, and the subscriber
is an HTTP endpoint instead of a method.

**Events make Programming prompt, not correct.** Once the two sides have
separate stores, no transaction spans the Library's commit and Programming's
handler, so a crash between them loses the event. Programming therefore
reconciles against the facade at every start. A lost event delays a correction
until the next start and never leaves it undone.

**An event is published only after the change it describes has committed**
(`CatalogueStore.after_commit`). Acceptance adds a work inside discovery's own
transaction, and an announcement made inside it would describe a work that a
rollback could still take back.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

log = logging.getLogger(__name__)


class WorkChange(StrEnum):
    """What happened to a work. The values are the names a webhook would carry."""

    #: The work entered circulation: added to the catalogue, or restored from
    #: the archive.
    ACCEPTED = "work.accepted"
    #: The work left circulation.
    ARCHIVED = "work.archived"
    #: A new master image or a new render was recorded. A new master can leave the
    #: existing render stale; a new render can make the work showable again.
    IMAGE_CHANGED = "work.image_changed"
    #: A mat colour was recorded, so the composed presentation changes.
    MAT_CHANGED = "work.mat_changed"


@dataclass(frozen=True, slots=True)
class WorkChanged:
    """One announcement: which work, and what happened to it.

    It carries no record and no verdict. A subscriber that needs to know whether
    the work can still go on a wall asks the facade, so the announcement and the
    answer cannot disagree.
    """

    change: WorkChange
    work_id: str


type WorkChangedHandler = Callable[[WorkChanged], None]


class LibraryEvents:
    """The Library's in-process publisher. Subscribers are called in the order they subscribed."""

    def __init__(self) -> None:
        self._handlers: list[WorkChangedHandler] = []

    def subscribe(self, handler: WorkChangedHandler) -> None:
        self._handlers.append(handler)

    def publish(self, event: WorkChanged) -> None:
        """Tell every subscriber, and never fail the change that caused it.

        By the time this runs, the Library's change has committed. A subscriber
        that raises has failed to act on it, and that is logged by name at
        ERROR. It is not raised to whoever made the change, whose operation
        succeeded, and it does not stop the subscribers after it. Startup
        reconciliation repairs what the failed handler left undone.
        """
        for handler in list(self._handlers):
            # The change committed, so a subscriber's failure must neither undo
            # nor misreport it: logged by name, and repaired by reconciliation.
            try:
                handler(event)
            except Exception:  # prawduct:allow prawduct/broad-except -- event boundary after commit; logged, then reconciled
                log.exception(
                    "A subscriber failed to act on %s for work %s; the change stands, and the next start reconciles it.",
                    event.change.value,
                    event.work_id,
                )
