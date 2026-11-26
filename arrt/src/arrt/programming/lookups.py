"""Programming's existence-checking lookups: a wall, a theme, what hangs on a wall, the draft, what is kept off.

**One home**, so a lookup that refuses has one sentence and one error, and a
change to either (not found is 404 on `/api`) is made once, and a collaborator
that never publishes does not look walls and themes up through the publisher.

**What is kept off every wall is answered here and nowhere else**
(`exclusions`, `kept_off`, `exclusion_of`): the one reader of the store's
exclusions, so what "kept off" means is stated once. An act asks for the set
once and tests every work against it, never one read a work.

**The machine's clock and identity source live here too** (`machine_now`,
`new_id`): the defaults each Programming collaborator takes when it is handed
neither, so a test that hands it its own is what every record it writes carries.

`Lookups` holds the store and nothing else. The facade (`display.py`) builds one
over its one store and hands that one to every collaborator, `FeedPublisher`
among them, so what this guaranteed as the publisher's methods still holds:

- each lookup reads the one store every collaborator writes through, on the
  calling thread, so one made inside a caller's `transaction()` or `reading()`
  block answers from inside it;
- one object answers every collaborator, so a test that replaces a lookup on the
  facade's instance (`display._lookups`) reaches every call a collaborator makes;
- the refusals are the sentences below, word for word; `ClientService`
  (`clients.py`) quotes `no_wall` rather than writing it out again;
- a wall or a theme the caller named that is not there is `NotFound` (404 on
  `/api`, the same failure on MCP); a wall with nothing hanging on it is a plain
  `ServiceError` (400), because the wall is there and only its state refuses.
  A hang naming a theme that is gone is the same: the caller named the wall.

Nothing here logs, publishes or asks the Library anything.
"""

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from arrt.persistence.records import Scene, SceneStatus, Theme, Wall, WorkExclusion
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import NotFound, ServiceError

#: A clock a collaborator reads: an instant in UTC.
type Clock = Callable[[], datetime]

#: A source of fresh identities, each a text no other record holds.
type IdSource = Callable[[], str]


def machine_now() -> datetime:
    """This machine's clock, in UTC: what a collaborator reads when it was handed no clock."""
    return datetime.now(UTC)


def new_id() -> str:
    """A fresh random identity: what a collaborator mints when it was handed no id source."""
    return str(uuid.uuid4())


def no_wall(wall_id: str) -> str:
    """What a person or an agent reads when no wall has this id."""
    return f"No wall with id {wall_id!r} is recorded."


def no_theme(theme_id: str) -> str:
    """What a person or an agent reads when no theme has this id."""
    return f"No theme with id {theme_id!r} is recorded."


class Lookups:
    """Find a wall, a theme, what hangs on a wall, or the draft, refusing in one set of words."""

    def __init__(self, store: ProgrammingStore) -> None:
        self._store = store

    def get_wall(self, wall_id: str) -> Wall:
        """The wall with this id; `NotFound` (`no_wall`) when none is recorded."""
        wall = self._store.get_wall(wall_id)
        if wall is None:
            raise NotFound(no_wall(wall_id))
        return wall

    def get_theme(self, theme_id: str) -> Theme:
        """The theme with this id, a hung selection included; `NotFound` (`no_theme`) when there is none."""
        theme = self._store.get_theme(theme_id)
        if theme is None:
            raise NotFound(no_theme(theme_id))
        return theme

    def require_hanging(self, wall: Wall) -> Theme:
        """The theme hanging on this wall; `ServiceError` when nothing is, or `no_theme` for a hang naming none.

        Both are plain `ServiceError`, never `NotFound`: the caller named a wall
        that is there, and what refuses is that wall's state.
        """
        assignment = self._store.get_assignment(wall.id)
        if assignment is None:
            raise ServiceError(
                f"Nothing is hanging on {wall.name!r}, so there is nothing to put on it. Hang a theme there first."
            )
        try:
            return self.get_theme(assignment.theme_id)
        except NotFound as gone:
            raise ServiceError(str(gone)) from gone

    def exclusions(self) -> Sequence[WorkExclusion]:
        """Every work kept off every wall, oldest first: the store's one reading of them."""
        return self._store.list_exclusions()

    def kept_off(self) -> frozenset[str]:
        """The ids of the works kept off every wall, from one reading: ask once, test every work against it."""
        return frozenset(exclusion.artwork_id for exclusion in self.exclusions())

    def exclusion_of(self, artwork_id: str) -> WorkExclusion | None:
        """The record keeping this work off every wall, or None while it is allowed."""
        return next((kept for kept in self.exclusions() if kept.artwork_id == artwork_id), None)

    def current_draft(self) -> Scene | None:
        """The draft the builder shows and the walls stage: the newest, should the store hold more than one. Never raises."""
        drafts = self._store.list_scenes(SceneStatus.DRAFT)
        return drafts[-1] if drafts else None
