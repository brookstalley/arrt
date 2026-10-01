"""What the wall shows — themes, the standing directive, and the manifest.

The catalogue answers "what do we hold"; this answers "what is on the wall, in
what order, and what should it do next". They are separated because they change
for different reasons: a work's metadata changes when a curator corrects it, and
a theme changes when a curator changes their mind about an evening.

**This service depends on the Library and never the reverse**, and only through
`arrt.library.facade`. A theme is a grouping of works, so building one
requires asking about them; nothing about a work requires knowing which themes
hold it. Works are held here as ids, and the facade says whether each can go on a
wall. **The Library tells this service when a work changes**, and this service
decides what that means for a wall: `on_work_changed` takes a work the Library
now refuses off every published manifest and withdraws any pin naming it. Every
rule about what an advance *means* — that the counter is monotonic, that
rebuilds carry it forward, that a step supersedes a pin, that a withdrawal is
not a step — lives here.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from arrt import observations
from arrt.library.facade import LibraryFacade, PlayableWork, Unplayable, UnplayableReason, WorkChanged
from arrt.persistence.records import Directive, Theme, ThemeAssignment, ThemeMembership, Wall
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.builder import (
    Exclusion,
    ManifestBuild,
    ManifestEntry,
    as_document,
    manifest_path_in,
    media_document,
    read_published,
    write_atomically,
)
from arrt.programming.manifest.heartbeat import HeartbeatReading, heartbeat_path_in
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import ServiceError
from arrt.services.fields import require_text
from arrt.services.store import store_write

log = logging.getLogger(__name__)


class Unset:
    """ "The caller said nothing about this field", as distinct from "set it to null".

    A sentinel type rather than a `None` default, because `None` is a meaningful
    value for every field that takes this: no description, and "inherit the
    global default" for both rotation settings.
    """


UNSET: Final[Unset] = Unset()


@dataclass(frozen=True, slots=True)
class DisplaySettings:
    """The deployment facts the walls' operations need.

    **Named for the plane rather than for a wall**, because a wall is now a
    first-class entity with a name and an id: a type called `WallSettings` beside
    `Services.bind(wall=…)` read as though the container were being handed a
    wall, when what it is handed is where this installation publishes and the
    pace a theme inherits when it has expressed none of its own.

    Passed in rather than read from the environment here, because a service that
    resolved its own configuration could not be tested against two deployments
    and would make every caller share one.
    """

    #: The directory both planes share. The manifest and the heartbeat are named
    #: from it **per wall**, so this holds the root and not a file: the catalogue
    #: names as many walls as the curator has rooms, and each one has its own
    #: pair of files.
    art_root: Path
    #: What a theme that has expressed no pace of its own inherits.
    rotation_interval_seconds: int
    shuffle: bool

    def manifest_path(self, wall_id: str) -> Path:
        """Where this plane publishes one wall's desired state."""
        return manifest_path_in(self.art_root, wall_id)

    def heartbeat_path(self, wall_id: str) -> Path:
        """Where the display serving one wall reports. Never written by this plane."""
        return heartbeat_path_in(self.art_root, wall_id)


@dataclass(frozen=True, slots=True)
class WallView:
    """One wall with everything a surface showing it needs, read at one instant.

    Composed here rather than by each surface, for the reason the service layer
    exists at all: both surfaces need the identical composition, and two callers
    assembling it from three reads apiece would be two places for "what is a wall
    made of" to be decided — and two chances to report a wall and a theme that
    were never simultaneously true.
    """

    wall: Wall
    #: Null when nothing is hanging, which is an ordinary state.
    hanging: Theme | None
    directive: Directive


@dataclass(frozen=True, slots=True)
class WallHeartbeat:
    """One wall and what the display serving it last said about itself.

    The pairing exists because the reading alone cannot say *whose* silence it
    is, and naming which wall has stopped reporting is the whole reason the
    heartbeat became one file per wall.
    """

    wall: Wall
    heartbeat: HeartbeatReading


def describe_wall_status(readings: Sequence[WallHeartbeat]) -> str:
    """One sentence across every wall — an observation, never a verdict.

    **It names the wall that has not reported, and that is what the heartbeat
    became one file per wall for.** A line saying "the study has not reported" is
    what a reader of a two-room installation needs, and one shared heartbeat could
    not have said it: the second display would have overwritten the first's
    report, so a wall that had gone quiet would have looked exactly like a wall
    that was fine.

    **No threshold is applied and no word like "healthy" appears.** What is
    stated are facts a reader cannot get wrong — a wall has written a heartbeat
    or it has not, and if it has, how long ago in the unit a person reads it in.
    Whether four minutes is late is the reader's to decide, because this plane
    does not know whether that television was switched off on purpose.

    A function rather than a method, because the browser panel and the tool
    surface both state this and neither owns it: two hand-written sentences from
    the same readings drift, and a caller told "the study has not reported" by
    one surface and "every wall has reported" by the other cannot tell which is
    lying.
    """
    if not readings:
        # Unreachable through a catalogue this plane opened, which seeds a wall on
        # first open — so it means a file something else wrote, and saying that
        # plainly beats a sentence composed over an empty list that reads as an
        # all-clear.
        return "No wall is in the catalogue, so there is nothing for a display plane to report about."
    silent = [seen for seen in readings if seen.heartbeat.absent or seen.heartbeat.problem is not None]
    if silent:
        names = ", ".join(repr(seen.wall.name) for seen in silent)
        counted = (
            f"{names} has not reported"
            if len(silent) == 1
            else f"{len(silent)} of {len(readings)} walls have not reported: {names}"
        )
        return f"{counted}. Each wall's own reading says whether nothing was ever written or what could not be read."
    # The least recent, because a summary quoting the freshest would read as an
    # all-clear bought from whichever wall happened to report last.
    oldest = max(readings, key=lambda seen: seen.heartbeat.age_seconds or 0.0)
    aged = observations.ago(oldest.heartbeat.age_seconds)
    if len(readings) == 1:
        return f"{oldest.wall.name!r} last reported {aged}."
    return f"Every wall has reported; the least recent is {oldest.wall.name!r}, {aged}."


@dataclass(frozen=True, slots=True)
class ThemePlacement:
    """One theme and every wall showing it.

    Several walls, deliberately: hanging the same theme in two rooms requires no
    duplication, and a shape with room for one wall would have re-made the
    single-wall assumption one layer up from the boolean that was removed.
    """

    theme: Theme
    walls: Sequence[Wall]


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """What one reconciliation found and did, so a caller and a test can read it rather than the journal."""

    #: How many works it asked the Library about.
    asked: int
    #: The ids the Library refused, whether or not any wall was carrying them.
    refused: Sequence[str]
    #: Walls whose published manifest was rewritten.
    republished: Sequence[str]
    #: Walls whose standing pin was withdrawn.
    pins_withdrawn: Sequence[str]

    @property
    def changed(self) -> bool:
        return bool(self.republished or self.pins_withdrawn)


class DisplayService:
    """Read and write the themes, memberships, and directives the walls run on."""

    def __init__(self, store: ProgrammingStore, library: LibraryFacade, settings: DisplaySettings) -> None:
        self._store = store
        self._library = library
        self._settings = settings

    # -- reads: themes --------------------------------------------------------

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme."""
        return self._store.list_themes()

    def get_theme(self, theme_id: str) -> Theme:
        """Return one theme."""
        theme = self._store.get_theme(theme_id)
        if theme is None:
            raise ServiceError(f"No theme with id {theme_id!r} is in the catalogue.")
        return theme

    # -- reads: walls and what hangs on them -----------------------------------

    def get_wall(self, wall_id: str) -> Wall:
        """Return one wall."""
        wall = self._store.get_wall(wall_id)
        if wall is None:
            raise ServiceError(f"No wall with id {wall_id!r} is in the catalogue.")
        return wall

    def hanging_on(self, wall_id: str) -> Theme | None:
        """The theme hanging on this wall, or None while nothing is.

        None is an ordinary answer, not a fault: an empty catalogue and a curator
        who took everything down both produce it, and `information-architecture.md`
        designs it as one of the Walls screen's named empty states.
        """
        self.get_wall(wall_id)
        assignment = self._store.get_assignment(wall_id)
        return None if assignment is None else self.get_theme(assignment.theme_id)

    def walls_hanging(self, theme_id: str) -> Sequence[Wall]:
        """Every wall showing this theme, in the order walls are listed.

        Several, deliberately: two walls may hang the same theme and that
        requires no duplication, which is the property the old boolean could not
        have. This is what the delete refusal counts and what it names.
        """
        hung = {assignment.wall_id for assignment in self._store.list_assignments() if assignment.theme_id == theme_id}
        # Keyed off the wall listing rather than off the assignment order, so the
        # walls come back in the order every other surface shows them in.
        return [wall for wall in self._store.list_walls() if wall.id in hung]

    def survey_walls(self) -> Sequence[WallView]:
        """Every wall with what hangs on it and what it was last told to do."""
        themes = {theme.id: theme for theme in self._store.list_themes()}
        hanging = {assignment.wall_id: assignment.theme_id for assignment in self._store.list_assignments()}
        # Keyed by wall rather than indexed positionally: `list_directives`
        # promises an order but nothing promises it matches the wall listing's,
        # and a read that lined the two up by position would be wrong the first
        # time a wall was renamed.
        directives = {directive.wall_id: directive for directive in self._store.list_directives()}
        return [self._view(wall, themes, hanging, directives) for wall in self._store.list_walls()]

    def get_wall_view(self, wall_id: str) -> WallView:
        """One wall with what hangs on it and what it was last told to do.

        **Composed from the two single-fact reads rather than repeating them.**
        Written out, this method held a second implementation of "what hangs
        here" and a second of "what was this wall told to do" — two answers to
        each question, from the same class, which is the shape that diverges the
        first time either rule gains a condition. `survey_walls` is the third
        answer and the justified one: it is the bulk path, and it reads the whole
        catalogue once for N walls rather than three times for each.

        It costs two extra `get_wall` lookups against the same open file, which
        is the price of the single definition and is not worth inlining back.
        """
        return WallView(
            wall=self.get_wall(wall_id),
            hanging=self.hanging_on(wall_id),
            directive=self.read_directive(wall_id),
        )

    def survey_themes(self) -> Sequence[ThemePlacement]:
        """Every theme with every wall showing it.

        One pass over the assignments rather than one lookup per theme: the
        question "where is each of these hanging" is asked about the whole list
        every time it is asked at all.
        """
        walls = {wall.id: wall for wall in self._store.list_walls()}
        hung: dict[str, list[str]] = {}
        for assignment in self._store.list_assignments():
            hung.setdefault(assignment.theme_id, []).append(assignment.wall_id)
        return [
            ThemePlacement(
                theme=theme,
                # Ordered by the wall listing so every surface names walls the
                # same way round, whatever order the assignments came back in.
                walls=[wall for wall in walls.values() if wall.id in set(hung.get(theme.id, ()))],
            )
            for theme in self._store.list_themes()
        ]

    @staticmethod
    def _view(
        wall: Wall,
        themes: Mapping[str, Theme],
        hanging: Mapping[str, str],
        directives: Mapping[str, Directive],
    ) -> WallView:
        directive = directives.get(wall.id)
        if directive is None:
            # Unreachable through this service — a wall is created with its
            # directive in one transaction — so it means the file was written by
            # something else, and saying so beats a KeyError from a dict lookup.
            raise ServiceError(f"Wall {wall.name!r} has no display directive, which this plane never writes.")
        theme_id = hanging.get(wall.id)
        return WallView(wall=wall, hanging=None if theme_id is None else themes[theme_id], directive=directive)

    def theme_work_ids(self, theme_id: str) -> Sequence[str]:
        """The ids of the theme's works, in curated order.

        Ordered because the entries carry a curator's placement; the ones nobody
        placed follow the ones somebody did. **Ids and not works**, because what a
        work *is* is the Library's to say: a surface listing a theme resolves
        these through the Library, which is the composition the bindings are
        allowed to do and this service is not.
        """
        self.get_theme(theme_id)
        return [membership.artwork_id for membership in self._store.list_memberships(theme_id)]

    # -- reads: the display directive -----------------------------------------

    def read_directive(self, wall_id: str) -> Directive:
        """One wall's standing instruction to the display plane."""
        self.get_wall(wall_id)
        return self._store.get_directive(wall_id)

    # -- writes: walls --------------------------------------------------------

    def add_wall(self, *, name: str) -> Wall:
        """Record a wall, with the directive every wall has from creation.

        The pair is written together so that no caller ever has to make a
        directive, and so that no wall can be observed without one: every advance
        reads the counter it is about, and a wall lacking the row would refuse a
        `next` for a reason that is this product's mistake rather than the
        curator's.

        A wall arrives with nothing hanging on it. Nothing is promoted onto it —
        with more than one wall there is no defensible answer to which theme
        belongs on a wall the curator has not hung anything on, and the empty
        state is a designed one.

        **A wall recorded here shows nothing until a display plane is configured
        to serve it**, and that is a deployment step rather than a gap. Each wall
        gets its own manifest, named by the wall's id, and a display reads the one
        wall its `WALL_ID` names — so a second wall's manifest exists from the
        moment a theme is hung on it and is read by whichever device is pointed at
        it. Nothing is overwritten and no display can open a wall it does not
        serve; until 2026-08-12 both were false, and a second wall was a thing an
        operator could record and be told would not light up.
        """
        with self._store.transaction():
            wall = Wall(id=str(uuid.uuid4()), name=require_text(name, field="name"), created_at=datetime.now(UTC))
            store_write(self._store.add_wall, wall)
            store_write(self._store.add_directive, Directive(wall_id=wall.id, sequence=0, pinned_work_id=None))
        return wall

    # -- writes: themes and membership ----------------------------------------

    def add_theme(self, *, name: str, description: str | None = None) -> Theme:
        """Record a theme and return it.

        **It hangs nowhere.** A theme is created globally and hanging it is a
        separate act — `activate_theme` — because with more than one wall there
        is no wall a new theme could be put on without the curator having chosen
        one. This method arrived active-if-none-else-is, which was the same
        automatic promotion `reconcile` did and is dropped for the same reason.
        """
        theme = Theme(
            id=str(uuid.uuid4()),
            name=require_text(name, field="name"),
            created_at=datetime.now(UTC),
            description=description,
        )
        store_write(self._store.add_theme, theme)
        return theme

    def activate_theme(self, theme_id: str, *, wall_id: str) -> ManifestBuild:
        """Hang this theme on this wall, and publish what follows.

        **The wall is named even while there is one and the answer is obvious.**
        A confirmation that reads correctly today only because there is one
        possible target is a sentence that silently becomes wrong the day a
        second display arrives, and this is the call every such sentence is built
        from.

        **Hanging rewrites the manifest**, so switching themes changes the wall
        rather than arming a later `sync`. A curator who chose a theme and found
        the wall unchanged would reasonably conclude the product was broken, and
        the two-step alternative exists only as an artefact of how the operations
        decompose.

        The switch costs **zero television writes**: the whole library stays on
        the TV and rotation is driven from here, so this is a file rewrite rather
        than minutes of upload churn.

        It returns the build, not the theme, because the theme alone cannot say
        how much of itself reached the wall — and a switch that silently put up
        four of a theme's twelve works is the failure this report exists for.
        """
        self.get_theme(theme_id)
        self.get_wall(wall_id)
        # One transaction around the hang and the publish, so a manifest that
        # could not be written takes the hang back with it. Recording the hang
        # and then failing to publish left the catalogue naming a theme the wall
        # was not showing, with nothing to say the two disagreed.
        with self._store.transaction():
            store_write(
                self._store.set_assignment,
                ThemeAssignment(wall_id=wall_id, theme_id=theme_id, assigned_at=datetime.now(UTC)),
            )
            return self.sync(wall_id, theme_id)

    def clear_wall(self, wall_id: str) -> None:
        """Take down whatever is hanging, leaving the wall holding nothing.

        The inverse of `activate_theme`, and the operation that keeps a theme
        deletable: the delete refusal below is absolute about a theme that hangs
        somewhere, so without a way to take one down a curator could never empty
        the catalogue.

        **It does not advance the directive sequence and does not clear the pin.**
        Taking a theme down is not an instruction to the display plane, and an
        advance here would fire a directive nobody issued — the same reasoning
        that keeps archiving a pinned work from advancing it.

        **It deliberately does not rewrite the manifest.** The wall keeps showing
        what it was showing, which is the same posture as curation being stopped
        entirely and the same one deleting the last theme already had. Publishing
        an empty manifest would blank the wall as a side effect of tidying up.
        """
        wall = self.get_wall(wall_id)
        assignment = self._store.get_assignment(wall_id)
        if assignment is None:
            raise ServiceError(f"Nothing is hanging on wall {wall_id!r}, so there is nothing to take down.")
        store_write(self._store.remove_assignment, wall_id)
        # The only operation in this plane that deliberately leaves the catalogue
        # and the wall disagreeing for an unbounded time, so it is the one an
        # operator asking "why is the set showing a theme that hangs nowhere"
        # comes to the journal for. `sync`'s two lines are the precedent: what a
        # wall shows changing is worth a line, and this is the change that
        # writes no manifest to record it anywhere else.
        log.info(
            "Took theme %r down from wall %r. The wall goes on showing it until a theme is hung.",
            self.get_theme(assignment.theme_id).name,
            wall.name,
        )

    def add_to_theme(self, *, theme_id: str, artwork_id: str, position: int | None = None) -> ThemeMembership:
        """Put a work in a theme, at a place in the order or at the end of it.

        **`position` is an index here for the same reason it is one on a move**,
        and saying nothing means the end rather than nowhere. Ruled by the
        operator on 2026-08-12, when the two had drifted apart: an add wrote the
        number it was handed into the column as a sort key while a move had
        become an index, so one MCP parameter description was covering two
        meanings — and, worse, every work added through a screen or a tool came
        out *unplaced*, because nothing a curator touches sends a number. The
        list a surface renders is placed-then-unplaced; the list a move renumbers
        was the placed ones alone. Two different lists, indexed against each
        other, which is a reorder that does nothing or moves the work the way it
        was not asked to go.

        Making an add place the work is what collapses them into one list, for
        every caller rather than for the one screen that noticed. `position=None`
        on a *move* still means unplaced — that is a curator saying they have no
        opinion, which is a thing to be able to say; an add has no opinion to
        express yet, and the end of the order is where a work with nothing said
        about it goes.

        The insert renumbers what it displaces, in one transaction: writing the
        number and stopping is what left two rows tied on a position with
        `added_at` picking the winner, and an add can produce that tie exactly as
        a move could.
        """
        self.get_theme(theme_id)
        self._require_held(artwork_id)
        target = self._require_position(position)
        membership = ThemeMembership(
            theme_id=theme_id,
            artwork_id=artwork_id,
            added_at=datetime.now(UTC),
            position=None,
        )
        with self._store.transaction():
            others = list(self._store.list_memberships(theme_id))
            index = len(others) if target is None else min(target, len(others))
            self._renumber(others[:index] + [membership] + others[index:], new=membership)
        return replace(membership, position=index)

    def move_in_theme(self, *, theme_id: str, artwork_id: str, position: int | None) -> ThemeMembership:
        """Move a work to a place in the curated order, or return it to unplaced.

        **`position` is an index into the order, not a value written to a
        column** — the work ends up *at* that place and the works around it are
        renumbered to make room. Writing the number and stopping there is what
        this replaced, and it made the ordinary move silently do nothing:
        `list_memberships` breaks a tie on `added_at`, so a work sent from
        position 0 to position 1 landed level with the work already there and
        sorted ahead of it again, being the older row. Moving a work *up* worked
        and moving it *down* did not, which is the shape a defect takes when
        nothing renumbers — and the Theme screen's ↓ button had never once
        reordered anything.

        The renumber leaves the order dense from zero, so the index a surface
        reads off the list it was given is the index it can send back. An index
        past the end lands at the end rather than being refused: the list a
        curator is looking at is the one they are moving within, and there is no
        wrong answer to "put this last" worth a refusal.

        **The whole list is renumbered, not the placed part of it.** `theme_work_ids`
        hands a surface the placed works and then the unplaced ones as one list,
        and a surface can only index against what it was handed — so renumbering
        the placed subset alone made the index mean something the sender never
        meant. Anything sitting unplaced therefore acquires the place it was
        already being shown at, which changes no order anybody can see.

        **Unplaced is still a real destination**, and it is not the same as last.
        `None` means the curator has said nothing about where this work goes;
        `theme_work_ids` puts those after the placed ones, and returning a work to
        it renumbers what is left rather than leaving a hole in the sequence.

        One transaction, and the read of the order is inside it: a partial
        renumber is an order no curator asked for and no error message would
        describe, and an order read before the lock is one another move may
        already have replaced.
        """
        target = self._require_position(position)
        with self._store.transaction():
            membership = self._store.get_membership(theme_id, artwork_id)
            if membership is None:
                raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
            # Everything else, in the order a surface would have been handed it.
            others = [entry for entry in self._store.list_memberships(theme_id) if entry.artwork_id != artwork_id]
            if target is None:
                moved = replace(membership, position=None)
                self._renumber(others)
                # The moved row is not in that list, so nothing above writes it.
                store_write(self._store.update_membership, moved)
            else:
                index = min(target, len(others))
                self._renumber(others[:index] + [membership] + others[index:])
                moved = replace(membership, position=index)
        return moved

    def _renumber(self, order: Sequence[ThemeMembership], *, new: ThemeMembership | None = None) -> None:
        """Write a theme's entries out as dense positions from zero.

        Dense is what makes an index a round trip: a gap or a repeat still reads
        as a sensible order for a while and then loses a tie to `added_at`, which
        looks like a move that did nothing rather than like a corrupted sequence.

        `new` is the one entry that has never been stored, told apart by identity
        rather than by id because a duplicate add puts *two* entries here with the
        same `artwork_id` — the row already in the theme and the row being added.
        Either match refuses that add, since one of the two inserts always
        collides; identity is used because it describes which row is meant rather
        than relying on the refusal to make the ambiguity moot. Callers hold this
        inside a transaction, which is what turns that refusal into a rollback
        rather than a half-renumbered order.
        """
        for place, entry in enumerate(order):
            if entry is new:
                store_write(self._store.add_membership, replace(entry, position=place))
            elif entry.position != place:
                store_write(self._store.update_membership, replace(entry, position=place))

    def remove_from_theme(self, *, theme_id: str, artwork_id: str) -> None:
        """Take a work out of a theme. The work itself is untouched."""
        if self._store.get_membership(theme_id, artwork_id) is None:
            raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
        store_write(self._store.remove_membership, theme_id, artwork_id)

    def update_theme(
        self,
        theme_id: str,
        *,
        name: str | None = None,
        description: str | None | Unset = UNSET,
        rotation_interval_seconds: int | None | Unset = UNSET,
        shuffle: bool | None | Unset = UNSET,
    ) -> Theme:
        """Change a theme's name, description, or pace.

        The nullable fields take a sentinel rather than defaulting to `None`,
        because `None` is a meaningful value for all three — "no description",
        and "inherit the global default" for the two rotation settings. Without
        it, a caller changing only the name would silently clear the theme's pace.
        """
        theme = self.get_theme(theme_id)
        updated = replace(
            theme,
            name=theme.name if name is None else require_text(name, field="name"),
            description=theme.description if isinstance(description, Unset) else description,
            rotation_interval_seconds=(
                theme.rotation_interval_seconds
                if isinstance(rotation_interval_seconds, Unset)
                else self._require_interval(rotation_interval_seconds)
            ),
            shuffle=theme.shuffle if isinstance(shuffle, Unset) else shuffle,
        )
        store_write(self._store.update_theme, updated)
        return updated

    def delete_theme(self, theme_id: str) -> None:
        """Remove a theme and its membership rows. The works themselves are untouched.

        **A theme hanging on any wall is refused**, and the count that matters is
        walls rather than themes: a theme hung in three rooms is three rooms that
        lose their picture, so "it is the only theme" is not a reason to permit
        it. The curator hangs something else, or takes it down, and then deletes
        — either way what happens to those walls is a choice.

        This generalises a narrower rule. Until 2026-08-12 the refusal was "the
        active theme, while another theme exists", and the last theme was
        deletable *even while active* because there was no way to take one down
        and a curator has to be able to empty the catalogue. `clear_wall` is that
        way, which is what lets this be absolute.

        **A deletion that is permitted does not rewrite any manifest.** A theme
        that hangs nowhere is on no wall to take a picture off, and a wall whose
        theme was taken down keeps showing what it was showing — the same posture
        as curation being stopped entirely: the display plane runs off the last
        manifest indefinitely, and that is normal operation rather than
        degradation. Publishing an empty manifest instead would blank the wall as
        a side effect of tidying up the catalogue.
        """
        theme = self.get_theme(theme_id)
        hanging = self.walls_hanging(theme_id)
        if hanging:
            where = ", ".join(repr(wall.name) for wall in hanging)
            raise ServiceError(
                f"Theme {theme.name!r} is hanging on {where}. Hang another theme there first, or take this one "
                "down, so that what those walls show next is a choice rather than whatever was on them before."
            )
        with self._store.transaction():
            for membership in self._store.list_memberships(theme_id):
                store_write(self._store.remove_membership, theme_id, membership.artwork_id)
            store_write(self._store.remove_theme, theme_id)

    # -- reads: what the display plane says about itself -----------------------

    def survey_wall_status(self) -> Sequence[WallHeartbeat]:
        """Every wall with whatever the display serving it last said.

        **Composed here rather than by the health surface**, for the reason
        `survey_walls` is: the panel and the tool surface both need the identical
        pairing, and two callers assembling it from a wall listing and a read
        apiece would be two places for "which walls are we listening to" to be
        decided — which is exactly the question a wall that has gone silent is
        answered by.
        """
        return [
            WallHeartbeat(wall=wall, heartbeat=heartbeat.read(self._settings.heartbeat_path(wall.id)))
            for wall in self._store.list_walls()
        ]

    # -- writes: the display directive ----------------------------------------

    def step_display(self, wall_id: str) -> Directive:
        """Tell the display serving this wall to move to the next work.

        **One wall's advance leaves every other wall's counter alone**, which is
        what the directive stopped being a singleton for: a `next` aimed at the
        living room stepping the study is one counter being asked a question it
        cannot answer.

        The step clears any standing pin. A sequence that advanced while a pin
        was still set would read as "jump to that work again" rather than as
        "move on", so the two directives cannot both be in force.
        """
        return self._advance(wall_id, pinned_work_id=None)

    def show_work_now(self, wall_id: str, artwork_id: str) -> Directive:
        """Tell the display serving this wall to jump to this work and carry on from there.

        **Refused if the work is not displayable**, with the same reason the
        manifest build would have given. `data-model.md` specifies the refusal
        for an archived work; this applies the whole readiness rule, because the
        neighbouring cases fail identically from the curator's side. Pinning a
        work with no render writes a directive naming something the manifest does
        not carry, answers "the directive is written", and the wall never moves —
        which is the silence the exclusion report exists to break, arriving
        through the one path that did not consult readiness.

        **It checks readiness, not theme membership**, so it does not remove the
        display plane's own obligation. A perfectly displayable work that is
        simply not in the active theme can still be pinned, and the manifest will
        not carry it — that is available on every call rather than a timing
        window. The membership check belongs to the plane that has to resolve the
        pin rather than the one writing it: display logs one WARNING and carries
        on rotating, by the same posture as a missing render file. What this
        closes is the case a curator can be told about now.
        """
        answer = self._require_held(artwork_id)
        if not isinstance(answer, PlayableWork):
            raise ServiceError(f"Artwork {artwork_id!r} cannot be shown on the wall: {answer.detail}")
        return self._advance(wall_id, pinned_work_id=artwork_id)

    # -- the manifest ---------------------------------------------------------

    def build_manifest(self, wall_id: str, theme_id: str | None = None) -> ManifestBuild:
        """Evaluate what a theme would put on one wall, without writing anything.

        Separate from `sync` so a curator can ask "what would go on the wall, and
        what would not" before changing what is on it — and so the readiness rule
        is testable without a filesystem.

        **The wall is named, and the theme defaults to what is hanging there.**
        Exclusions belong to a wall rather than to the installation once two
        walls can hang different themes, and this route's whole job is to state a
        consequence before it happens — which it cannot do without knowing whose
        consequence it is.
        """
        wall = self.get_wall(wall_id)
        theme = self.get_theme(theme_id) if theme_id is not None else self._require_hanging(wall)
        directive = self._store.get_directive(wall_id)

        entries = []
        exclusions = []
        # One question for the whole theme rather than one per work: the facade
        # is written as if it were remote, and so is this call.
        answers = self._library.playable(membership.artwork_id for membership in self._store.list_memberships(theme.id))
        for answer in answers.values():
            if isinstance(answer, PlayableWork):
                entries.append(ManifestEntry.of(answer))
            else:
                exclusions.append(Exclusion.of(answer))

        return ManifestBuild(
            wall=wall,
            theme=theme,
            entries=entries,
            exclusions=exclusions,
            # Null on either field means "inherit the global default", so the
            # theme's own value is used only when it has expressed one.
            rotation_interval_seconds=(
                theme.rotation_interval_seconds
                if theme.rotation_interval_seconds is not None
                else self._settings.rotation_interval_seconds
            ),
            shuffle=theme.shuffle if theme.shuffle is not None else self._settings.shuffle,
            # Carried forward unchanged. A rebuild is not a directive, and a
            # counter that reset here would read to the display plane as an
            # advance — firing a jump nobody asked for on every sync.
            directive_sequence=directive.sequence,
            pinned_work_id=directive.pinned_work_id,
        )

    def sync(self, wall_id: str, theme_id: str | None = None) -> ManifestBuild:
        """Rebuild the manifest and publish it to the display plane.

        Returns what it wrote **and what it left out**. A caller that only
        reports the entry count is describing a theme that may be silently
        half on the wall.

        This writes desired state; it does not command the television. The wall
        converges within the display plane's poll interval, and saying anything
        stronger would assert something this plane cannot observe.

        **It takes a wall and writes that wall's file, and no other's.** The
        manifest is one document per wall, named by the wall's id, so hanging a
        theme in the study leaves the living room's file untouched — its mtime
        included, which is what the other display polls. Two rooms therefore run
        independent themes and independent directive sequences without either
        plane coordinating anything.
        """
        # Built and written inside one transaction, which is also what serialises
        # every rewrite of a published manifest: a step or a reconciliation
        # patching this file between the build and the write would otherwise be
        # overwritten by a document built before it.
        with self._store.transaction():
            build = self.build_manifest(wall_id, theme_id)
            write_atomically(self._settings.manifest_path(wall_id), as_document(build))
        if build.exclusions:
            # Named at WARNING with the count, because a theme quietly showing
            # fewer works than it holds is precisely this product's
            # characteristic failure.
            log.warning(
                "Wall %r, theme %r: %d of %d works are not currently displayable (%s).",
                build.wall.name,
                build.theme.name,
                len(build.exclusions),
                build.considered,
                ", ".join(sorted({exclusion.reason.value for exclusion in build.exclusions})),
            )
        log.info(
            "Wrote the manifest for wall %r showing theme %r, with %d entries.",
            build.wall.name,
            build.theme.name,
            len(build.entries),
        )
        return build

    # -- what a Player reads and writes --------------------------------------------

    def published_manifest(self, wall_id: str) -> bytes | None:
        """The bytes of this wall's manifest as last published, or None if nothing has been.

        The bytes, not a parse of them, so the ETag a Player compares is a hash
        of exactly what it was sent.
        """
        self.get_wall(wall_id)
        try:
            return self._settings.manifest_path(wall_id).read_bytes()
        except FileNotFoundError:
            return None

    def record_heartbeat(self, wall_id: str, document: dict[str, Any]) -> None:
        """Keep what a Player said about itself, where the health panel already looks.

        Written to the same file the file channel writes, so every existing
        reader sees a heartbeat that arrived over HTTP exactly as it sees one
        that did not. Refused, and nothing written, if the health panel could
        not read it.
        """
        self.get_wall(wall_id)
        problem = heartbeat.problem_with(document)
        if problem is not None:
            raise ServiceError(f"That is not a heartbeat this plane can read: {problem}")
        write_atomically(self._settings.heartbeat_path(wall_id), document)

    # -- keeping published manifests true to the Library ---------------------

    def on_work_changed(self, event: WorkChanged) -> None:
        """The Library changed a work: take it off any wall it can no longer go on.

        Subscribed to the Library's announcements. The rule is the one startup
        reconciliation applies, narrowed to the one work, so the running server
        and a restarted one cannot disagree.
        """
        self.reconcile([event.work_id], cause=event.change.value)

    def reconcile(self, work_ids: Iterable[str] | None = None, *, cause: str = "startup") -> Reconciliation:
        """Make every published manifest and pin agree with what the Library will still show.

        Asks the facade about the works in question: the ones named, or, with
        none named, every work any published manifest or standing pin mentions.
        For each wall whose published manifest carries a work the Library now
        refuses, those entries are removed, and no other entry leaves or
        arrives. A pin naming a refused work is withdrawn without advancing the
        sequence, because withdrawing is not an instruction to move on.

        **No work is ever added.** A work that became showable is not published.
        Deciding when new work reaches the wall is what sync is for (the
        operator's ruling, 2026-09-30), and a reconciliation that also added
        would publish a theme's unsynced changes as a side effect of archiving
        something. The one change to a kept entry is its `media`, replaced when
        the Library's hash for it moved (a re-render), because the old hash is
        one `/media` no longer serves and a Player on HTTP would otherwise lose
        the work until the next sync.

        **Run at every start**, because an announcement lost to a crash between
        the Library's commit and this handler would otherwise leave a wall
        showing a work the curator withdrew until someone happened to sync.
        """
        with self._store.transaction():
            walls = self._store.list_walls()
            published = {wall.id: read_published(self._settings.manifest_path(wall.id)) for wall in walls}
            directives = {directive.wall_id: directive for directive in self._store.list_directives()}
            mentioned = {entry["work_id"] for document in published.values() if document for entry in document["entries"]}
            mentioned |= {directive.pinned_work_id for directive in directives.values() if directive.pinned_work_id}
            asked = mentioned if work_ids is None else mentioned & set(work_ids)
            answers = self._library.playable(sorted(asked))
            refused = {work_id for work_id, answer in answers.items() if not isinstance(answer, PlayableWork)}

            withdrawn: list[str] = []
            for wall_id, directive in directives.items():
                if directive.pinned_work_id in refused:
                    store_write(self._store.set_directive, replace(directive, pinned_work_id=None))
                    withdrawn.append(wall_id)

            republished: dict[str, tuple[list[str], list[str]]] = {}
            for wall in walls:
                document = published[wall.id]
                if document is None:
                    continue
                kept = [entry for entry in document["entries"] if entry["work_id"] not in refused]
                removed = [entry["work_id"] for entry in document["entries"] if entry["work_id"] in refused]
                # A kept work whose render was redone since the sync: its old
                # hash is one `/media` no longer serves, so a Player on HTTP
                # would skip it until the next sync while the file channel went
                # on showing it. The entry keeps its place and changes only its
                # `media`; this adds no work to the wall.
                refreshed = [entry for entry in kept if _media_moved(entry, answers.get(entry["work_id"]))]
                for entry in refreshed:
                    fresh = answers[entry["work_id"]].media  # type: ignore[union-attr]
                    if fresh is None:
                        entry.pop("media", None)
                    else:
                        entry["media"] = media_document(fresh)
                pin = (document.get("directive") or {}).get("pinned_work_id")
                if len(kept) == len(document["entries"]) and pin not in refused and not refreshed:
                    continue
                document["entries"] = kept
                if pin in refused:
                    document["directive"] = {**document["directive"], "pinned_work_id": None}
                document["generated_at"] = datetime.now(UTC).isoformat()
                write_atomically(self._settings.manifest_path(wall.id), document)
                republished[wall.id] = (removed, [entry["work_id"] for entry in refreshed])

        result = Reconciliation(
            asked=len(asked),
            refused=tuple(sorted(refused)),
            republished=tuple(republished),
            pins_withdrawn=tuple(withdrawn),
        )
        names = {wall.id: wall.name for wall in walls}
        for wall_id, (removed, refreshed_ids) in republished.items():
            # Only the works this wall carried: naming every refused work on
            # every wall's line would send an operator looking for works that
            # were never there.
            if removed:
                log.info(
                    "Wall %r: took works the Library no longer offers off the published manifest (%s, after %s).",
                    names[wall_id],
                    ", ".join(removed),
                    cause,
                )
            if refreshed_ids:
                log.info(
                    "Wall %r: pointed the published manifest at the current render of %s (after %s).",
                    names[wall_id],
                    ", ".join(refreshed_ids),
                    cause,
                )
        for wall_id in withdrawn:
            # Said out loud: a standing instruction disappearing is the kind of
            # silent change that becomes "the wall stopped doing what I told it"
            # with nothing to read back.
            log.info(
                "Wall %r: withdrew the standing pin, whose work the Library no longer offers (after %s).", names[wall_id], cause
            )
        if work_ids is None and not result.changed:
            log.info("Reconciled %d walls against the Library at startup: nothing to change.", len(walls))
        return result

    # -- internals ------------------------------------------------------------

    def _advance(self, wall_id: str, *, pinned_work_id: str | None) -> Directive:
        """Move one wall's directive on by one.

        The counter only ever increases, for the life of the wall. The display
        plane acts each time it sees the number go up, so a counter that reset —
        on a manifest rebuild, on a theme switch — would fire a directive nobody
        issued.
        """
        self.get_wall(wall_id)
        with self._store.transaction():
            current = self._store.get_directive(wall_id)
            advanced = replace(current, sequence=current.sequence + 1, pinned_work_id=pinned_work_id)
            store_write(self._store.set_directive, advanced)
            # Inside the transaction, so a directive that could not reach the
            # wall is not recorded as issued.
            self._publish_directive(wall_id, advanced)
        return advanced

    def _publish_directive(self, wall_id: str, directive: Directive) -> None:
        """Put this directive in the wall's published manifest, and change nothing else in it.

        The Player reads its directive only from the manifest, so a directive
        that stays in the catalogue never reaches the wall. **A patch, not a
        sync**: rebuilding from the theme would also publish every work added
        since the last sync, and deciding when new work reaches the wall is what
        sync is for. A wall with nothing published yet has nothing to patch, and
        its first sync carries the directive out, since a build reads the current
        one.
        """
        path = self._settings.manifest_path(wall_id)
        document = read_published(path)
        if document is None:
            return
        document["directive"] = {"sequence": directive.sequence, "pinned_work_id": directive.pinned_work_id}
        document["generated_at"] = datetime.now(UTC).isoformat()
        write_atomically(path, document)

    def _require_hanging(self, wall: Wall) -> Theme:
        assignment = self._store.get_assignment(wall.id)
        if assignment is None:
            raise ServiceError(
                f"Nothing is hanging on {wall.name!r}, so there is nothing to put on it. Hang a theme there first."
            )
        return self.get_theme(assignment.theme_id)

    def _require_held(self, artwork_id: str) -> PlayableWork | Unplayable:
        """The Library's answer about one work, refusing an id it does not hold.

        Refused in the catalogue's own words, so a curator adding an unknown id to
        a theme hears what they would have heard before the facade existed.
        """
        answer = self._library.playable([artwork_id])[artwork_id]
        if not isinstance(answer, PlayableWork) and answer.reason is UnplayableReason.NOT_IN_CATALOGUE:
            raise ServiceError(answer.detail)
        return answer

    @staticmethod
    def _require_position(position: int | None) -> int | None:
        if position is not None and position < 0:
            raise ServiceError(f"A position cannot be negative, got {position}.")
        return position

    @staticmethod
    def _require_interval(seconds: int | None) -> int | None:
        """Null inherits the default; a number has to be a length of time.

        Zero is refused rather than treated as "as fast as possible": the display
        plane would spin selecting images, and nothing about that reads as a
        setting somebody chose.
        """
        if seconds is not None and seconds <= 0:
            raise ServiceError(f"A rotation interval must be greater than zero seconds, got {seconds}.")
        return seconds


def _media_moved(entry: dict[str, Any], answer: object) -> bool:
    """Whether a published entry names different media from what the Library now offers for it."""
    if not isinstance(answer, PlayableWork):
        return False
    published = (entry.get("media") or {}).get("sha256")
    offered = None if answer.media is None else answer.media.sha256
    return published != offered
