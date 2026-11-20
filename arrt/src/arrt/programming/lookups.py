"""Programming's existence-checking lookups: a wall, a theme, what hangs on a wall, the draft.

**One home**, so a lookup that refuses has one sentence and one error, and a
change to either (`build-plan-audit-wave-2b.md`, Chunk 37: not found is 404) is
made once. Until 2026-11-20 they were methods of `FeedPublisher`, and every
other collaborator, including the ones that never publish, looked walls and
themes up through the publisher (the 2a boundary review, R-3).

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

from arrt.persistence.records import Scene, SceneStatus, Theme, Wall
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import NotFound, ServiceError


def no_wall(wall_id: str) -> str:
    """What a person or an agent reads when no wall has this id."""
    return f"No wall with id {wall_id!r} is in the catalogue."


def no_theme(theme_id: str) -> str:
    """What a person or an agent reads when no theme has this id."""
    return f"No theme with id {theme_id!r} is in the catalogue."


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

    def current_draft(self) -> Scene | None:
        """The draft the builder shows and the walls stage: the newest, should the store hold more than one. Never raises."""
        drafts = self._store.list_scenes(SceneStatus.DRAFT)
        return drafts[-1] if drafts else None
