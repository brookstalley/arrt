"""The persistence contract over Programming's tables.

Themes, what each holds, walls, what hangs on each, and each wall's directive.
Programming reaches its storage only through this protocol and never through
`persistence.catalogue.CatalogueStore`, which is the Library's. Today one SQLite
file serves both and one object implements both protocols. The split is
`architecture.md` § Direction's rule 3: when Programming's tables move to a file
of their own, a second implementation of this protocol replaces the first and no
caller changes.

Implementations own persistence and nothing else, for the reason the Library's
contract gives: every rule about what a valid arrangement looks like belongs to
the service, which is the only caller.
"""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from arrt.persistence.records import Directive, Theme, ThemeAssignment, ThemeMembership, Wall


class ProgrammingStore(Protocol):
    """Everything Programming can ask of its storage."""

    # -- atomicity ------------------------------------------------------------

    def transaction(self) -> AbstractContextManager[None]:
        """Group several writes so they commit together or not at all.

        A renumber of a theme's order is several writes, and a partial one is an
        order no curator asked for. Nesting joins the outer group.
        """
        ...

    def reading(self) -> AbstractContextManager[None]:
        """Group several reads so they answer about one instant."""
        ...

    # -- themes ---------------------------------------------------------------

    def add_theme(self, theme: Theme) -> None:
        """Persist a theme. Raises if the id or the name is already present."""
        ...

    def get_theme(self, theme_id: str) -> Theme | None:
        """Return the theme, or None if no such id is stored."""
        ...

    def update_theme(self, theme: Theme) -> None:
        """Overwrite a stored theme with this one. Raises if the id is absent."""
        ...

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme in a stable order."""
        ...

    def remove_theme(self, theme_id: str) -> None:
        """Delete a theme. Its membership rows must already be gone."""
        ...

    # -- theme membership -----------------------------------------------------

    def add_membership(self, membership: ThemeMembership) -> None:
        """Place a work in a theme. Raises if it is already in that theme."""
        ...

    def get_membership(self, theme_id: str, artwork_id: str) -> ThemeMembership | None:
        """Return the entry, or None if the work is not in the theme."""
        ...

    def update_membership(self, membership: ThemeMembership) -> None:
        """Overwrite a stored entry with this one. Raises if it is absent."""
        ...

    def remove_membership(self, theme_id: str, artwork_id: str) -> None:
        """Take a work out of a theme. Removing an absent entry is not an error."""
        ...

    def list_memberships(self, theme_id: str) -> Sequence[ThemeMembership]:
        """Return a theme's entries in curated order, unordered entries last."""
        ...

    # -- the default theme ----------------------------------------------------

    def get_default_theme(self) -> Theme | None:
        """Return the theme new works join, or None while no theme is marked."""
        ...

    def mark_default_theme(self, theme_id: str) -> None:
        """Make this theme the default, taking the mark off any other. Raises if it is absent."""
        ...

    def record_offer(self, artwork_id: str, offered_at: datetime) -> None:
        """Record that this work has been offered to the default theme. Raises if it already has."""
        ...

    def offered_work_ids(self) -> set[str]:
        """Every work the default theme has been offered, whether or not it joined."""
        ...

    # -- walls ----------------------------------------------------------------

    def add_wall(self, wall: Wall) -> None:
        """Persist a wall. Raises if the id or the name is already present."""
        ...

    def get_wall(self, wall_id: str) -> Wall | None:
        """Return the wall, or None if no such id is stored."""
        ...

    def update_wall(self, wall: Wall) -> None:
        """Overwrite a stored wall with this one. Raises if the id is absent."""
        ...

    def list_walls(self) -> Sequence[Wall]:
        """Return every wall in a stable order.

        Unpaged: a household has as many walls as it has displays.
        """
        ...

    # -- what is hanging ------------------------------------------------------

    def get_assignment(self, wall_id: str) -> ThemeAssignment | None:
        """What is hanging on this wall, or None while nothing is."""
        ...

    def set_assignment(self, assignment: ThemeAssignment) -> None:
        """Hang a theme on a wall, replacing whatever was hanging there.

        There is no second row to displace: `wall_id` is the whole primary key,
        so a wall holding a theme already is an update rather than a conflict to
        resolve.
        """
        ...

    def remove_assignment(self, wall_id: str) -> None:
        """Take down whatever is hanging. Clearing an empty wall is not an error."""
        ...

    def list_assignments(self) -> Sequence[ThemeAssignment]:
        """Every wall that has something hanging on it, in a stable order.

        Walls with nothing hanging have no row and do not appear.
        """
        ...

    # -- the display directives -----------------------------------------------

    def add_directive(self, directive: Directive) -> None:
        """Persist a wall's directive. Raises if that wall already has one."""
        ...

    def get_directive(self, wall_id: str) -> Directive:
        """Return this wall's standing directive. A wall has one from creation."""
        ...

    def set_directive(self, directive: Directive) -> None:
        """Replace a wall's standing directive. Raises if that wall has none."""
        ...

    def list_directives(self) -> Sequence[Directive]:
        """Every wall's standing directive, in a stable order."""
        ...
