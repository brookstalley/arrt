"""What the wall shows — themes, what hangs where, and each wall's feed.

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
now refuses off every published feed. Every rule about what a republish keeps —
the slot on the wall now, or a fresh start — lives here.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import logging
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from arrt import observations
from arrt.library.facade import (
    EventKind,
    LibraryFacade,
    PlayableWork,
    ProgrammingAct,
    Unplayable,
    UnplayableReason,
    WorkChange,
    WorkChanged,
)
from arrt.persistence.records import Theme, ThemeAssignment, ThemeMembership, Wall, WorkExclusion
from arrt.programming import adequacy
from arrt.programming.clients import Placements
from arrt.programming.display_state import DisplayState
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.builder import Exclusion, ManifestBuild, write_atomically
from arrt.programming.manifest.heartbeat import HeartbeatReading, heartbeat_path_in
from arrt.programming.manifest.v2 import SCHEMA_MAJOR as MANIFEST_MAJOR
from arrt.programming.manifest.v2 import Feed, Published, manifest_v2_path_in, work_document
from arrt.programming.manifest.v2 import as_document as as_v2_document
from arrt.programming.manifest.v2 import read_published as read_published_v2
from arrt.programming.schedule import Keep, Schedule, Start, StartFresh
from arrt.programming.schedule import build as build_schedule
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member, require_text
from arrt.services.store import store_write

log = logging.getLogger(__name__)


class MatMode(StrEnum):
    """How a Player draws the mat around a work (`feeds-and-players.md` § Mat modes).

    The feed names a mode; the width is always the Player's (ruling 7).
    """

    #: The work fitted on black.
    NONE = "none"
    #: A mat of the work's own shape, black beyond.
    PROPORTIONAL = "proportional"
    #: Mat colour to every edge of the screen.
    FULL = "full"


#: What a caller with only text to send (an MCP argument) says for "no choice, the
#: Player's own mat". A spelling apart from every mode, so it can never be taken
#: for one.
PLAYERS_OWN_MAT: Final[str] = "players_own"


class Unjudged(StrEnum):
    """Why no work on a wall was judged for size: each quiet state said apart from "every work is big enough"."""

    #: The wall is on no display, so no Player reports a screen for it.
    NO_DISPLAY = "no_display"
    #: Its display's Player has reported no screen size in `SCREEN_MEMORY`
    #: (before minor 2, a Frame before its Player knew its panel, or silent).
    NO_SCREEN = "no_screen_reported"
    #: It has no feed, which is where each master's size is read.
    NO_FEED = "no_feed"


@dataclass(frozen=True, slots=True)
class SizeJudgement:
    """Which works on a wall are too small for it, and what that was judged against.

    `screen` is None exactly when `unjudged` names why, so an empty `too_small`
    means "every work is big enough" only when a screen is given.
    """

    screen: tuple[int, int] | None
    too_small: frozenset[str]
    unjudged: Unjudged | None


class Unset:
    """ "The caller said nothing about this field", as distinct from "set it to null".

    A sentinel type rather than a `None` default, because `None` is a meaningful
    value for every field that takes this: no description, and "inherit the
    global default" for both rotation settings.
    """


UNSET: Final[Unset] = Unset()


@dataclass(frozen=True, slots=True)
class ThemeCount:
    """A theme as a filter option: how many of a given set of works it holds."""

    theme: Theme
    count: int
    #: The theme the listing is filtered by.
    selected: bool

    @property
    def disabled(self) -> bool:
        """True for a theme that would select nothing, unless it is the one chosen.

        The facet rule, applied to themes: a chosen option is never disabled,
        because the option itself is the control that turns it off.
        """
        return self.count == 0 and not self.selected


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

    #: The directory both planes share. The feed and the heartbeat are named
    #: from it **per wall**, so this holds the root and not a file: the catalogue
    #: names as many walls as the curator has rooms, and each one has its own
    #: pair of files.
    art_root: Path
    #: What a theme that has expressed no pace of its own inherits.
    rotation_interval_seconds: int
    shuffle: bool

    def manifest_v2_path(self, wall_id: str) -> Path:
        """Where this plane publishes one wall's feed."""
        return manifest_v2_path_in(self.art_root, wall_id)

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
    #: What the wall's screen is doing, from its last heartbeat and its assignment.
    display_state: DisplayState
    #: Whether the wall's Player said it reads this server's feed (manifest major
    #: 2), from its last readable heartbeat. None when there is no such
    #: heartbeat to read. `heartbeat.reads_major` says how silence is read.
    reads_feed: bool | None = None


def feed_notice(*, reads_feed: bool | None) -> str | None:
    """What a curator is told about a wall whose Player cannot read this server's feed, or None.

    One sentence for every surface, so Walls and the tool surface cannot tell a
    curator two different things about the same wall. Nothing is said when no
    heartbeat has been read: Walls already says the wall's display is silent.
    """
    if reads_feed is not False:
        return None
    return (
        "This wall's Player can't read this server's feed, so it will show nothing new. "
        "Update Arrt Player on the device that shows this wall."
    )


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
class WorkPlacements:
    """Where one work is: the themes holding it, and whether it is kept off every wall."""

    themes: Sequence[ThemePlacement]
    exclusion: WorkExclusion | None


class NotAgainScope(StrEnum):
    """The one question *Not this one again* asks: how far the curator meant it."""

    #: Out of the theme hanging on this wall, and so off every wall hanging it.
    THEME = "theme"
    #: Off every wall, whatever hangs there, until allowed again. The work stays held.
    EVERY_WALL = "every_wall"


@dataclass(frozen=True, slots=True)
class NotAgain:
    """What *Not this one again* did: the theme the work left, or the exclusion now standing."""

    scope: NotAgainScope
    artwork_id: str
    wall_id: str
    #: The theme the work left, for `THEME`; None otherwise.
    left_theme: Theme | None = None
    #: The exclusion now standing, for `EVERY_WALL`; None otherwise.
    exclusion: WorkExclusion | None = None


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """What one reconciliation found and did, so a caller and a test can read it rather than the journal."""

    #: How many works it asked the Library about.
    asked: int
    #: The ids the Library refused, whether or not any wall was carrying them.
    refused: Sequence[str]
    #: Walls whose published feed was rewritten.
    republished: Sequence[str]

    @property
    def changed(self) -> bool:
        return bool(self.republished)


class DisplayService:
    """Read and write the themes, memberships, and feeds the walls run on."""

    def __init__(self, store: ProgrammingStore, library: LibraryFacade, settings: DisplaySettings) -> None:
        self._store = store
        self._library = library
        self._settings = settings
        self._placements = Placements(store, settings.art_root)

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

    def get_listed_theme(self, theme_id: str) -> Theme:
        """A theme a curator can name: any theme but a hung selection.

        A selection lives only as long as it hangs (`_retire_selection`), so a
        Get that sent its works there, a default that pointed at it, a work
        added to it or a name given it would all be lost the day the wall
        changes. Each names a theme from a picker that never offers a
        selection; this refuses the id arriving another way. Taking a work out
        of one stays allowed: *Not this one again* does it on the wall's behalf.
        """
        theme = self.get_theme(theme_id)
        if theme.hidden:
            raise ServiceError(
                f"{theme.name!r} is the selection hanging on a wall, not a theme, so it cannot be renamed, "
                "made the default, or have works sent or added to it. Choose a theme from Themes."
            )
        return theme

    def shuffles(self, theme: Theme) -> bool:
        """Whether a wall hanging this theme shows its works in shuffled order.

        The theme's own setting when it has expressed one, else the deployment's:
        null on `Theme.shuffle` means "inherit", not "off". One place, so the
        manifest a wall is given and the theme page's account of its order
        cannot disagree about which of the two decides what the wall shows first.
        """
        return theme.shuffle if theme.shuffle is not None else self._settings.shuffle

    def default_theme(self) -> Theme | None:
        """The theme new works join, or None while the curator has marked none."""
        return self._store.get_default_theme()

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
        """Every wall with what hangs on it and what its screen is doing."""
        themes = {theme.id: theme for theme in self._store.list_themes()}
        hanging = {assignment.wall_id: assignment.theme_id for assignment in self._store.list_assignments()}
        return [self._view(wall, themes, hanging) for wall in self._store.list_walls()]

    def get_wall_view(self, wall_id: str) -> WallView:
        """One wall with what hangs on it and what its screen is doing.

        **Composed from the single-fact reads rather than repeating them**, so
        "what hangs here" has one answer in this class. `survey_walls` is the
        bulk path, and reads the whole catalogue once for N walls.
        """
        wall = self.get_wall(wall_id)
        return WallView(
            wall=wall,
            hanging=self.hanging_on(wall_id),
            display_state=self._display_state(wall),
            reads_feed=self._reads_feed(wall.id),
        )

    def _display_state(self, wall: Wall) -> DisplayState:
        """What the wall's screen is doing, read from its heartbeat file now, as every label reads it too."""
        return self._placements.wall_state(wall).state

    def _reads_feed(self, wall_id: str) -> bool | None:
        """Whether the wall's last readable heartbeat lists major 2, or None if there is no such heartbeat."""
        reading = heartbeat.read(self._settings.heartbeat_path(wall_id))
        return None if reading.contents is None else heartbeat.reads_major(reading.contents, MANIFEST_MAJOR)

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
            # A selection is not a theme the curator made, so the Themes index
            # leaves it out; the wall it hangs on is where it is seen.
            for theme in self._store.list_themes()
            if not theme.hidden
        ]

    def _view(self, wall: Wall, themes: Mapping[str, Theme], hanging: Mapping[str, str]) -> WallView:
        theme_id = hanging.get(wall.id)
        return WallView(
            wall=wall,
            hanging=None if theme_id is None else themes[theme_id],
            display_state=self._display_state(wall),
            reads_feed=self._reads_feed(wall.id),
        )

    def theme_counts(self, work_ids: Iterable[str], *, selected: str | None = None) -> Sequence[ThemeCount]:
        """Every theme, by name, with how many of `work_ids` it holds.

        The ids are the Library's answer to "which works does this filter
        select", taken as opaque references: Artworks' *Filter* rail prints each
        theme's count beside it and disables a theme that would select nothing,
        as it does a facet value. One read scope, so the counts agree with one
        another; they cannot share a scope with the Library's read that produced
        the ids, which is the price of the seam.
        """
        among = set(work_ids)
        with self._store.reading():
            return [
                ThemeCount(
                    theme=theme,
                    count=sum(1 for membership in self._store.list_memberships(theme.id) if membership.artwork_id in among),
                    selected=theme.id == selected,
                )
                for theme in self._store.list_themes()
                # A selection is no filter a curator would look for, unless it
                # is the one they followed a link to.
                if not theme.hidden or theme.id == selected
            ]

    def work_ids_on_walls(self) -> frozenset[str]:
        """The ids of every work some wall plays now, through the theme or selection hanging there.

        What Artworks' *Not on any wall* facet leaves out (the owner's ruling of
        2026-10-08 on #288): a work is on a wall when a theme or selection
        hanging on one holds it and it is not kept off every wall. **Not what a
        wall has shown**: which works a wall actually displayed is not
        recorded, so "never hung" cannot be answered, and this does not pretend
        to. Nor is it readiness: a held work a wall would skip for want of a
        render still counts as on it, since the curator's act — hanging the
        theme — is what this answers for.

        Ids, opaque to this plane, for the bindings to hand the Library, as
        `theme_work_ids` are. One read scope.
        """
        with self._store.reading():
            hung = {assignment.theme_id for assignment in self._store.list_assignments()}
            kept_off = {exclusion.artwork_id for exclusion in self._store.list_exclusions()}
            playing = {membership.artwork_id for theme_id in hung for membership in self._store.list_memberships(theme_id)}
        return frozenset(playing - kept_off)

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

    # -- writes: walls --------------------------------------------------------

    def add_wall(self, *, name: str) -> Wall:
        """Record a wall.

        A wall arrives with nothing hanging on it. Nothing is promoted onto it —
        with more than one wall there is no defensible answer to which theme
        belongs on a wall the curator has not hung anything on, and the empty
        state is a designed one.

        **A wall recorded here shows nothing until a client is assigned to show
        it** (`clients.ClientService.assign_wall`), and that is a curatorial step
        rather than a gap. Each wall gets its own feed, named by the wall's
        id, from the moment a theme is hung on it, and a client is admitted only
        to the walls assigned to it. Nothing is overwritten and no client can
        open a wall it does not show; until 2026-08-12 both were false, and a
        second wall was a thing an operator could record and be told would not
        light up.
        """
        wall = Wall(id=str(uuid.uuid4()), name=require_text(name, field="name"), created_at=datetime.now(UTC))
        with self._store.transaction():
            store_write(self._store.add_wall, wall)
        return wall

    # -- writes: themes and membership ----------------------------------------

    def set_mat_mode(self, wall_id: str, mode: MatMode | str | None) -> Wall:
        """Choose how this wall's Player draws the mat, or with None leave it to the Player.

        Republishes the wall's feed with the setting and changes nothing else in
        it: the schedule and every work stay as published.
        """
        wall = self.get_wall(wall_id)
        chosen = None if mode is None else require_member(mode, enum=MatMode, field="mat mode").value
        with self._store.transaction():
            store_write(self._store.update_wall, replace(wall, mat_mode=chosen))
            feed = read_published_v2(self._settings.manifest_v2_path(wall_id))
            if feed is not None:
                self._patch_v2_works(wall_id, feed, {})
        log.info("Wall %r: the mat is now %s.", wall.name, chosen or "the Player's own choice")
        return self.get_wall(wall_id)

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

    def make_default(self, theme_id: str) -> Theme:
        """Make this the theme new works join, taking the mark off whichever had it.

        **Only works accepted from now on join it.** Every work already in the
        catalogue has been offered to the default once, whatever was the default
        then, and marking a theme is not a request to fill it with everything
        accepted before; a curator who wants that adds them from Library › Works.
        """
        self.get_listed_theme(theme_id)
        store_write(self._store.mark_default_theme, theme_id)
        return self.get_theme(theme_id)

    def offer_destinations(self, work_ids: Iterable[str]) -> Sequence[str]:
        """Offer each work the theme it was accepted into, once, and return the ones that joined.

        **Where a work goes is the Library's to say and this service's to
        apply.** The facade answers, for each work, the theme its Get named, or
        None. None means the default theme, the owner's ruling 8: what is
        accepted lands there, at the end of its order. A named theme takes the
        default's place, so a work the curator sent somewhere else never enters
        the everyday rotation (ruling 5a, as the owner recast it on 2026-10-02).

        **A named theme that has since been deleted is joined by nothing.** The
        curator chose "not the rotation" when they started the Get, and deleting
        the theme does not reverse that. The work is recorded as offered all the
        same, so the next start does not sweep it into the default either, and
        the log says which work and which theme.

        **Once per work, ever**, and that is what the offer record is for: the
        Library announces a restored work as accepted, exactly as it announces a
        new one, and startup offers every accepted work with no offer recorded.
        Without the record either would put back a work the curator took out of
        its theme by hand. A work offered while no theme was the default is
        recorded too, so marking one later does not sweep in everything accepted
        before it.

        A work already in its theme, placed there by hand before its
        announcement arrived, is recorded and left where the curator put it.
        Offer and membership commit together, so a work is never recorded as
        offered without having joined, or joined without the record that stops a
        second join.

        **Nothing is published here.** A work is offered when it is accepted,
        before it is prepared, so it has nothing a feed could send yet: the
        announcement of its master puts it on any wall hanging its theme, and
        failing that the next roll does (`_roll_v2`).
        """
        already = self._store.offered_work_ids()
        unoffered = [work_id for work_id in dict.fromkeys(work_ids) if work_id not in already]
        if not unoffered:
            return []
        # Asked before the transaction, and once for every work: the facade is
        # written as if remote, so it is one coarse question, never one per work
        # and never with this plane's lock held.
        destinations = self._library.destinations(unoffered)
        joined: list[str] = []
        joined_by_theme: Counter[str] = Counter()
        vanished: list[tuple[str, str]] = []
        with self._store.transaction():
            default = self._store.get_default_theme()
            offered = self._store.offered_work_ids()
            for work_id in unoffered:
                if work_id in offered:
                    continue
                named = destinations[work_id]
                target = default if named is None else self._store.get_theme(named)
                if named is not None and target is None:
                    vanished.append((work_id, named))
                if target is not None and self._store.get_membership(target.id, work_id) is None:
                    self._insert(theme_id=target.id, artwork_id=work_id, position=None)
                    joined.append(work_id)
                    joined_by_theme[target.name] += 1
                store_write(self._store.record_offer, work_id, datetime.now(UTC))
        for name, count in joined_by_theme.items():
            log.info("Added %d newly accepted work(s) to theme %r.", count, name)
        for work_id, theme_id in vanished:
            # Said out loud, because the work is now in no theme at all, which is
            # exactly what the curator would come looking for.
            log.warning(
                "Work %s was accepted from a Get that named theme %s, which has since been deleted. "
                "It joins no theme, and not the default either; add it to one from Library › Works.",
                work_id,
                theme_id,
            )
        return joined

    def catch_up_offers(self) -> Sequence[str]:
        """Offer every accepted work that was never offered the theme it was accepted into. Run at start.

        For an announcement lost between the Library's commit and this plane's
        handler. It goes through `offer_destinations`, so a work whose
        announcement was lost lands where a delivered one would. Every work the
        catalogue held before the default existed was recorded as offered when
        the file was migrated, so this finds only what a crash dropped.
        """
        return self.offer_destinations(self._library.accepted_work_ids())

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
        replaced = self._store.get_assignment(wall_id)
        # One transaction around the hang and the publish, so a manifest that
        # could not be written takes the hang back with it. Recording the hang
        # and then failing to publish left the catalogue naming a theme the wall
        # was not showing, with nothing to say the two disagreed.
        with self._store.transaction():
            store_write(
                self._store.set_assignment,
                ThemeAssignment(wall_id=wall_id, theme_id=theme_id, assigned_at=datetime.now(UTC)),
            )
            build = self.sync(wall_id, theme_id)
            self._retire_selection(replaced)
        self._record_hang(build)
        return build

    def hang_selection(self, artwork_ids: Sequence[str], *, wall_id: str) -> ManifestBuild:
        """Hang these works on this wall, until something else is hung there.

        **A selection is stored as a theme with the hidden flag**, made here and
        holding these works in the order given, so the feed and readiness work
        on it exactly as on any theme. It is left off the
        Themes index and the theme pickers, because the curator chose works, not
        a theme, and would not recognise it in a list of theirs.

        Every id has to name a work the Library holds, and the whole hang is
        refused otherwise, in the catalogue's words. A work the Library holds
        but will not show is hung all the same and named in the build's
        exclusions, as hanging a theme does, so the curator learns why the wall
        is short rather than finding the act refused.
        """
        chosen = list(dict.fromkeys(artwork_ids))
        if not chosen:
            raise ServiceError("A selection needs at least one work to hang.")
        wall = self.get_wall(wall_id)
        # One question for every work, as the manifest build asks it: the facade
        # is written as if remote.
        for answer in self._library.playable(chosen).values():
            if not isinstance(answer, PlayableWork) and answer.reason is UnplayableReason.NOT_IN_CATALOGUE:
                raise ServiceError(answer.detail)
        now = datetime.now(UTC)
        replaced = self._store.get_assignment(wall_id)
        theme_id = str(uuid.uuid4())
        theme = Theme(
            id=theme_id,
            # Names are unique across themes, hidden or not, so the id's head
            # keeps two selections for one wall apart.
            name=f"Selection for {wall.name} ({theme_id[:8]})",
            created_at=now,
            hidden=True,
        )
        with self._store.transaction():
            store_write(self._store.add_theme, theme)
            for position, artwork_id in enumerate(chosen):
                store_write(
                    self._store.add_membership,
                    ThemeMembership(theme_id=theme_id, artwork_id=artwork_id, added_at=now, position=position),
                )
            store_write(self._store.set_assignment, ThemeAssignment(wall_id=wall_id, theme_id=theme_id, assigned_at=now))
            build = self.sync(wall_id, theme_id)
            self._retire_selection(replaced)
        self._record_hang(build)
        return build

    # -- writes: not this one again -------------------------------------------

    def not_this_one_again(self, artwork_id: str, *, wall_id: str, scope: NotAgainScope | str) -> NotAgain:
        """The Walls card's *Not this one again*, answered *from this theme* or *from every wall*.

        One method for both answers, so a click and an agent asking the same
        question reach the same act; each answer is its own method below.
        """
        resolved = require_member(scope, enum=NotAgainScope, field="scope")
        if resolved is NotAgainScope.THEME:
            left = self.leave_theme(artwork_id, wall_id=wall_id)
            return NotAgain(scope=resolved, artwork_id=artwork_id, wall_id=wall_id, left_theme=left)
        exclusion = self.exclude_work(artwork_id, wall_id=wall_id)
        return NotAgain(scope=resolved, artwork_id=artwork_id, wall_id=wall_id, exclusion=exclusion)

    def leave_theme(self, artwork_id: str, *, wall_id: str) -> Theme:
        """*Not this one again*, from this theme: take the work out of what hangs on this wall.

        The work leaves the theme, so it leaves every wall hanging that theme,
        and the published feeds of those walls lose it now rather than at the
        next sync: a curator who said "not this one" and saw it again a minute
        later would conclude the act did nothing. A wall showing it now starts
        fresh. Nothing else changes, on any wall: no work arrives with the
        patch, and the work stays held and in every other theme.

        Returns the theme it left, so the answer can say which.
        """
        wall = self.get_wall(wall_id)
        theme = self._require_hanging(wall)
        if self._store.get_membership(theme.id, artwork_id) is None:
            raise ServiceError(
                f"Artwork {artwork_id!r} is not in {theme.name!r}, which is what hangs on {wall.name!r}, "
                "so there is nothing to take it out of."
            )
        with self._store.transaction():
            store_write(self._store.remove_membership, theme.id, artwork_id)
            self._withdraw(artwork_id, [hung.id for hung in self.walls_hanging(theme.id)], cause="leaving its theme")
        self._library.record(
            ProgrammingAct(
                kind=EventKind.LEFT_THEME,
                wall_id=wall_id,
                theme_id=theme.id,
                work_id=artwork_id,
                detail={"theme_name": theme.name, "selection": theme.hidden},
            )
        )
        return theme

    def exclude_work(self, artwork_id: str, *, wall_id: str | None = None) -> WorkExclusion:
        """*Not this one again*, from every wall: keep the work off every wall until it is allowed again.

        **Not Archive.** The work stays in the Library and in every theme that
        holds it; what changes is that no feed carries it. Every published feed
        loses it now, for the reason `leave_theme` gives.

        `wall_id` is the wall the curator was looking at, recorded in the
        history so that wall's history shows the act. It changes nothing else.
        """
        self._require_held(artwork_id)
        if wall_id is not None:
            self.get_wall(wall_id)
        if any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
            raise ServiceError(f"Artwork {artwork_id!r} is already kept off every wall.")
        exclusion = WorkExclusion(artwork_id=artwork_id, excluded_at=datetime.now(UTC))
        with self._store.transaction():
            store_write(self._store.add_exclusion, exclusion)
            self._withdraw(artwork_id, [wall.id for wall in self._store.list_walls()], cause="being kept off every wall")
        self._library.record(ProgrammingAct(kind=EventKind.EXCLUDED, wall_id=wall_id, work_id=artwork_id))
        return exclusion

    def allow_work(self, artwork_id: str) -> None:
        """Undo *Not this one again* from every wall: the work may go on walls again.

        Every wall whose hung theme holds it gets it back now, if the Library
        will show it (`reconcile`, the owner's ruling of 2026-10-10).
        """
        if not any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
            raise ServiceError(f"Artwork {artwork_id!r} is not kept off the walls, so there is nothing to allow.")
        with self._store.transaction():
            store_write(self._store.remove_exclusion, artwork_id)
            self.reconcile([artwork_id], cause="being allowed back")
        self._library.record(ProgrammingAct(kind=EventKind.ALLOWED, work_id=artwork_id))

    def excluded_works(self) -> Sequence[WorkExclusion]:
        """Every work kept off every wall, oldest first."""
        return self._store.list_exclusions()

    def placements_of(self, artwork_id: str) -> WorkPlacements:
        """Every theme holding this work, with the walls hanging each, and whether it is kept off every wall.

        **Selections included.** A hidden theme is how one work hangs on a wall
        by itself, so leaving them out would hide the very hang the Work page
        exists to show; the caller decides which of them a curator would
        recognise. Read in one scope, so the themes, the walls and the exclusion
        describe one instant.
        """
        with self._store.reading():
            walls = list(self._store.list_walls())
            hung: dict[str, set[str]] = {}
            for assignment in self._store.list_assignments():
                hung.setdefault(assignment.theme_id, set()).add(assignment.wall_id)
            themes = [
                ThemePlacement(theme=theme, walls=[wall for wall in walls if wall.id in hung.get(theme.id, ())])
                for theme in self._store.list_themes()
                if any(membership.artwork_id == artwork_id for membership in self._store.list_memberships(theme.id))
            ]
            exclusion = next((kept for kept in self._store.list_exclusions() if kept.artwork_id == artwork_id), None)
        return WorkPlacements(themes=themes, exclusion=exclusion)

    def clear_wall(self, wall_id: str) -> None:
        """Take down whatever is hanging, leaving the wall holding nothing.

        The inverse of `activate_theme`, and the operation that keeps a theme
        deletable: the delete refusal below is absolute about a theme that hangs
        somewhere, so without a way to take one down a curator could never empty
        the catalogue.

        **It deliberately does not rewrite the feed.** The wall keeps showing
        what it was showing, which is the same posture as curation being stopped
        entirely and the same one deleting the last theme already had. Publishing
        an empty feed would blank the wall as a side effect of tidying up.
        """
        wall = self.get_wall(wall_id)
        assignment = self._store.get_assignment(wall_id)
        if assignment is None:
            raise ServiceError(f"Nothing is hanging on wall {wall_id!r}, so there is nothing to take down.")
        taken_down = self.get_theme(assignment.theme_id)
        with self._store.transaction():
            store_write(self._store.remove_assignment, wall_id)
            self._retire_selection(assignment)
        # The only operation in this plane that deliberately leaves the catalogue
        # and the wall disagreeing for an unbounded time, so it is the one an
        # operator asking "why is the set showing a theme that hangs nowhere"
        # comes to the journal for. `sync`'s two lines are the precedent: what a
        # wall shows changing is worth a line, and this is the change that
        # writes no manifest to record it anywhere else.
        log.info(
            "Took theme %r down from wall %r. The wall goes on showing it until a theme is hung.",
            taken_down.name,
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

        **A wall hanging the theme gets the work at once**, if the Library will
        show it (`reconcile`, the owner's ruling of 2026-10-10).
        """
        self.get_listed_theme(theme_id)
        self._require_held(artwork_id)
        target = self._require_position(position)
        with self._store.transaction():
            membership = self._insert(theme_id=theme_id, artwork_id=artwork_id, position=target)
            self.reconcile([artwork_id], cause="joining its theme")
        return membership

    def _insert(self, *, theme_id: str, artwork_id: str, position: int | None) -> ThemeMembership:
        """Write the membership at `position` (the end for None), renumbering what it displaces. Publishes nothing."""
        membership = ThemeMembership(theme_id=theme_id, artwork_id=artwork_id, added_at=datetime.now(UTC), position=None)
        with self._store.transaction():
            others = list(self._store.list_memberships(theme_id))
            index = len(others) if position is None else min(position, len(others))
            self._renumber([*others[:index], membership, *others[index:]], new=membership)
        return replace(membership, position=index)

    def add_works_to_theme(self, *, theme_id: str, artwork_ids: Sequence[str]) -> tuple[int, int]:
        """Put many works at the end of a theme's order, in the order given, in one transaction.

        Answers how many joined and how many the theme already held. A work
        already in the theme is passed over rather than refused, unlike
        `add_to_theme`: a selection made by a filter routinely holds some, and
        refusing the act for them would make *Add to theme* on a whole filter
        fail exactly when it is most useful.

        **One renumber, not one per work.** `add_to_theme` renumbers the whole
        theme on every insert, which over a few thousand works is millions of
        row writes. Here the existing order is made dense once and the newcomers
        are written after it, which is the same order a loop of single adds
        would leave, reached in one pass.

        Every id has to name a work the Library holds, asked of the facade in
        one question, and the whole act is refused otherwise, in the catalogue's
        words — so nothing is half-added. Walls hanging the theme get what
        joined, once, as `add_to_theme` says.
        """
        self.get_listed_theme(theme_id)
        chosen = list(dict.fromkeys(artwork_ids))
        for answer in self._library.playable(chosen).values():
            if not isinstance(answer, PlayableWork) and answer.reason is UnplayableReason.NOT_IN_CATALOGUE:
                raise ServiceError(answer.detail)
        now = datetime.now(UTC)
        with self._store.transaction():
            others = list(self._store.list_memberships(theme_id))
            held = {membership.artwork_id for membership in others}
            joining = [artwork_id for artwork_id in chosen if artwork_id not in held]
            self._renumber(others)
            for place, artwork_id in enumerate(joining, start=len(others)):
                store_write(
                    self._store.add_membership,
                    ThemeMembership(theme_id=theme_id, artwork_id=artwork_id, added_at=now, position=place),
                )
            if joining:
                self.reconcile(joining, cause="joining its theme")
        return len(joining), len(chosen) - len(joining)

    def remove_works_from_theme(self, *, theme_id: str, artwork_ids: Sequence[str]) -> Sequence[str]:
        """Take many works out of a theme in one transaction, and answer which left.

        A work the theme does not hold is passed over: the selection was made
        by a filter, and the theme is what it is now. The order left behind is
        not renumbered, as a single removal does not renumber it. Walls hanging
        the theme lose what left, as `remove_from_theme` says.
        """
        self.get_theme(theme_id)
        removed: list[str] = []
        with self._store.transaction():
            for artwork_id in dict.fromkeys(artwork_ids):
                if self._store.get_membership(theme_id, artwork_id) is None:
                    continue
                store_write(self._store.remove_membership, theme_id, artwork_id)
                removed.append(artwork_id)
            walls = [wall.id for wall in self.walls_hanging(theme_id)]
            for wall_id in walls:
                self._withdraw_v2(wall_id, set(removed), cause="leaving its theme")
        return removed

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
                self._renumber([*others[:index], membership, *others[index:]])
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
        """Take a work out of a theme. The work itself is untouched.

        Walls hanging the theme lose it now, as *Not this one again* from the
        theme takes it off (`leave_theme`): the feed follows the hung theme both
        ways, or a restart, which publishes what the theme lacks, would be the
        only thing that moved the wall.
        """
        if self._store.get_membership(theme_id, artwork_id) is None:
            raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
        with self._store.transaction():
            store_write(self._store.remove_membership, theme_id, artwork_id)
            self._withdraw(artwork_id, [wall.id for wall in self.walls_hanging(theme_id)], cause="leaving its theme")

    def update_theme(
        self,
        theme_id: str,
        *,
        name: str | None = None,
        description: str | Unset | None = UNSET,
        rotation_interval_seconds: int | Unset | None = UNSET,
        shuffle: bool | Unset | None = UNSET,
    ) -> Theme:
        """Change a theme's name, description, or pace.

        The nullable fields take a sentinel rather than defaulting to `None`,
        because `None` is a meaningful value for all three — "no description",
        and "inherit the global default" for the two rotation settings. Without
        it, a caller changing only the name would silently clear the theme's pace.
        """
        theme = self.get_listed_theme(theme_id)
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
        if theme.is_default:
            raise ServiceError(
                f"Theme {theme.name!r} is the default, which new works join, so it cannot be deleted. "
                "Make another theme the default first, and then delete this one."
            )
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

    # -- writes: what the wall shows now ---------------------------------------

    def step_display(self, wall_id: str) -> str:
        """Move one wall on to the work after the one on it now, and return that work's id.

        A republish of the wall's feed starting now (`player-contract.md` § What
        happens to `show_now` and `next`). One wall's step leaves every other
        wall's schedule alone, so a `next` aimed at the living room never moves
        the study.
        """
        self.get_wall(wall_id)
        with self._store.transaction():
            return self._restart(wall_id, pinned=None)

    def show_work_now(self, wall_id: str, artwork_id: str) -> str:
        """Put this work on the wall now and carry on from there; return its id.

        **Refused if the work is not displayable**, with the same reason the
        feed's build would have given, and refused if the curator kept it off
        every wall: a feed naming it would be a work no wall carries.

        **It checks readiness, not theme membership.** A displayable work that
        is not in the theme hanging there is shown for one slot, as a guest,
        and the schedule then carries on through the theme.
        """
        self.get_wall(wall_id)
        answer = self._require_held(artwork_id)
        if not isinstance(answer, PlayableWork):
            raise ServiceError(f"Artwork {artwork_id!r} cannot be shown on the wall: {answer.detail}")
        if any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
            raise ServiceError(f"Artwork {answer.title!r} is kept off every wall. Allow it again from its page first.")
        with self._store.transaction():
            return self._restart(wall_id, pinned=answer)

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

        entries: list[PlayableWork] = []
        exclusions: list[Exclusion] = []
        kept_off = {exclusion.artwork_id for exclusion in self._store.list_exclusions()}
        # One question for the whole theme rather than one per work: the facade
        # is written as if it were remote, and so is this call.
        answers = self._library.playable(membership.artwork_id for membership in self._store.list_memberships(theme.id))
        for answer in answers.values():
            # The curator's word comes first: a work kept off every wall is
            # reported as that, whatever the Library would say of it, because
            # allowing it again is the act that would change anything.
            if answer.work_id in kept_off:
                exclusions.append(Exclusion.kept_off(answer))
            elif isinstance(answer, PlayableWork):
                entries.append(answer)
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
            shuffle=self.shuffles(theme),
        )

    def sync(self, wall_id: str, theme_id: str | None = None) -> ManifestBuild:
        """Rebuild the wall's feed and publish it.

        Returns what it wrote **and what it left out**. A caller that only
        reports the entry count is describing a theme that may be silently
        half on the wall.

        This writes desired state; it does not command the television. The wall
        converges within the display plane's poll interval, and saying anything
        stronger would assert something this plane cannot observe.

        **It takes a wall and writes that wall's feed, and no other's**, so
        hanging a theme in the study leaves the living room's file untouched. The
        household rule reads every other wall's published schedule, and moves
        none of them (`_write_v2`).
        """
        # Built and written inside one transaction, which is also what serialises
        # every rewrite of a published feed: a step or a reconciliation
        # rewriting it between the build and the write would otherwise be
        # overwritten by a document built before it.
        with self._store.transaction():
            build = self.build_manifest(wall_id, theme_id)
            self._sync_v2(build)
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
            "Published the feed for wall %r showing theme %r, with %d works.",
            build.wall.name,
            build.theme.name,
            len(build.entries),
        )
        return build

    # -- what a Player reads and writes --------------------------------------------

    def record_heartbeat(self, wall_id: str, document: dict[str, Any]) -> None:
        """Keep what a Player said about itself, where the health panel already looks; note its screen; roll its horizon.

        Two things ride on the heartbeat because a live wall sends one a minute
        and nothing else does: the screen size a minor 2 Player reports, which
        too-small is judged against, and extending the wall's horizon when
        less than two days of it are left.

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
        self._record_screen(wall_id, document)
        self._roll_v2(wall_id)

    # -- too small for this wall ----------------------------------------------

    def largest_screen(self, wall_id: str) -> tuple[int, int] | None:
        """The largest screen the wall's display reported within `SCREEN_MEMORY`, or None if it reported none.

        Largest by area, and recent rather than latest (`player-contract.md`
        § The heartbeat, minor 2): a window made smaller for a minute must not
        make every work on the wall look fine.
        """
        wall = self.get_wall(wall_id)
        if wall.display_id is None:
            return None
        since = datetime.now(UTC) - SCREEN_MEMORY
        recent = [(w, h) for w, h, at in self._store.reported_screens(wall.display_id) if at >= since]
        return max(recent, key=lambda size: size[0] * size[1], default=None)

    def judge_sizes(self, wall_id: str) -> SizeJudgement:
        """Which works on the wall's feed are too small for its largest recent screen (`adequacy.py`).

        Read from the feed, which carries each master's size, so this asks the
        Library nothing. When there is nothing to judge against, it says which
        of the reasons it is, rather than an empty answer that would read as
        "every work is fine".
        """
        if self.get_wall(wall_id).display_id is None:
            return SizeJudgement(None, frozenset(), Unjudged.NO_DISPLAY)
        screen = self.largest_screen(wall_id)
        if screen is None:
            return SizeJudgement(None, frozenset(), Unjudged.NO_SCREEN)
        feed = read_published_v2(self._settings.manifest_v2_path(wall_id))
        if feed is None:
            return SizeJudgement(None, frozenset(), Unjudged.NO_FEED)
        small = frozenset(
            work_id
            for work_id, entry in feed.works.items()
            if adequacy.too_small(screen, (entry["media"]["width"], entry["media"]["height"]))
        )
        return SizeJudgement(screen, small, None)

    def too_small_on(self, wall_id: str) -> frozenset[str]:
        """The works too small for the wall; empty both when all are fine and when none was judged (`judge_sizes`)."""
        return self.judge_sizes(wall_id).too_small

    def size_judgements(self, theme_id: str) -> Mapping[str, SizeJudgement]:
        """Each wall hanging the theme, by name, with its judgement."""
        return {wall.name: self.judge_sizes(wall.id) for wall in self.walls_hanging(theme_id)}

    def too_small_for_walls(self, theme_id: str) -> Mapping[str, Sequence[str]]:
        """For each of the theme's works too small for a wall hanging it, those walls' names, in name order."""
        found: dict[str, list[str]] = {}
        for name, judgement in self.size_judgements(theme_id).items():
            for work_id in judgement.too_small:
                found.setdefault(work_id, []).append(name)
        return {work_id: sorted(names) for work_id, names in found.items()}

    def _record_screen(self, wall_id: str, document: Mapping[str, Any]) -> None:
        """Keep the screen size a minor 2 heartbeat reports, and forget sizes too old to count.

        A heartbeat with no capabilities (before minor 2), or with capabilities
        and no screen (minor 4, a screen unplugged), says nothing about the
        screen, and nothing is kept.
        """
        wall = self.get_wall(wall_id)
        capabilities = document.get("capabilities")
        screen = capabilities.get("screen") if isinstance(capabilities, Mapping) else None
        if wall.display_id is None or not isinstance(screen, Mapping):
            return
        width, height = screen.get("width_px"), screen.get("height_px")
        if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
            return
        now = datetime.now(UTC)
        known = self._store.reported_screens(wall.display_id)
        if any((w, h) == (width, height) and now - at < SCREEN_REFRESH for w, h, at in known):
            # Seen within the hour: the judgement needs day-scale freshness, and
            # a write per heartbeat per wall would buy nothing it uses.
            return
        with self._store.transaction():
            store_write(self._store.record_screen, wall.display_id, width, height, now)
            for old_width, old_height, at in known:
                if at < now - SCREEN_MEMORY:
                    store_write(self._store.forget_screen, wall.display_id, old_width, old_height)

    def published_manifest_v2(self, wall_id: str) -> bytes | None:
        """The bytes of this wall's feed as last published, or None if nothing has been.

        The bytes, not a parse of them, so the ETag a Player compares is a hash
        of exactly what it was sent.
        """
        self.get_wall(wall_id)
        try:
            return self._settings.manifest_v2_path(wall_id).read_bytes()
        except FileNotFoundError:
            return None

    # -- keeping published manifests true to the Library ---------------------

    def on_work_changed(self, event: WorkChanged) -> None:
        """The Library changed a work: take it off walls it can no longer go on, or put it on walls whose theme holds it.

        A newly accepted work is offered its theme too. It joins no feed then,
        since acceptance is what queues its preparation; its master's
        announcement puts it on the wall.

        Subscribed to the Library's announcements. The rules are the ones startup
        applies, narrowed to the one work, so the running server and a restarted
        one cannot disagree. The offer is made once per work, so an acceptance
        announced for a restore offers nothing (`offer_destinations`).
        """
        self.reconcile([event.work_id], cause=event.change.value)
        if event.change is WorkChange.ACCEPTED:
            self.offer_destinations([event.work_id])

    def reconcile(self, work_ids: Iterable[str] | None = None, *, cause: str = "startup") -> Reconciliation:
        """Make every published feed agree with what the Library will show.

        Asks the facade about the works in question: the ones named, or, with
        none named, every work any published feed carries. A work the Library
        now refuses leaves every feed carrying it; a work whose master, colour
        or label changed has its entry replaced where it stands.

        **A named work of a wall's hung theme that the Library will now show
        joins that wall's feed**, and with none named, a wall with a theme hung
        and no feed for it has the theme's feed published (the owner,
        2026-10-10: it is fine, even desirable, for the server to add works to a
        theme while it is hung). This superseded the ruling of 2026-09-30 that
        additions wait for sync.

        **Run at every start**, because an announcement lost to a crash between
        the Library's commit and this handler would otherwise leave a wall
        showing a work the curator withdrew until someone happened to hang the
        theme again. A lost announcement that would have added a work is not
        searched for here: a feed names only what its horizon schedules, so a
        member it does not name may simply not be due, and the next roll, which
        builds the hung theme, carries it (`_roll_v2`).
        """
        named = None if work_ids is None else set(work_ids)
        with self._store.transaction():
            walls = self._store.list_walls()
            feeds = {wall.id: read_published_v2(self._settings.manifest_v2_path(wall.id)) for wall in walls}
            hung = {assignment.wall_id: assignment.theme_id for assignment in self._store.list_assignments()}
            mentioned = {work_id for feed in feeds.values() if feed for work_id in feed.works}
            asked = mentioned if named is None else mentioned & named
            joining = {
                wall_id: self._held(theme_id, named) - set(feeds[wall_id].works if feeds[wall_id] else ())
                for wall_id, theme_id in hung.items()
            }
            asked |= {work_id for candidates in joining.values() for work_id in candidates}
            answers = self._library.playable(sorted(asked))
            refused = {work_id for work_id, answer in answers.items() if not isinstance(answer, PlayableWork)}
            republished = [wall.id for wall in walls if self._reconcile_v2(wall.id, feeds[wall.id], answers, cause=cause)]
            for wall_id, theme_id in hung.items():
                shown = {work_id for work_id in joining[wall_id] if isinstance(answers.get(work_id), PlayableWork)}
                if (shown or self._unpublished(wall_id)) and self._publish_additions(wall_id, theme_id, shown, cause=cause):
                    republished.append(wall_id)

        result = Reconciliation(asked=len(asked), refused=tuple(sorted(refused)), republished=tuple(dict.fromkeys(republished)))
        if work_ids is None and not result.changed:
            log.info("Reconciled %d walls against the Library at startup: nothing to change.", len(walls))
        return result

    def _held(self, theme_id: str, work_ids: set[str] | None) -> set[str]:
        """Which of these works the theme holds; none when none are named, since startup adds by publishing whole."""
        if not work_ids:
            return set()
        return {work_id for work_id in work_ids if self._store.get_membership(theme_id, work_id) is not None}

    def _unpublished(self, wall_id: str) -> bool:
        """Whether the wall has no feed on disk.

        A feed on disk that cannot be read is not unpublished: start-up leaves
        it for the next publish to replace, as reconciliation always has, so a
        bad file cannot stop the plane starting. A work joining the wall's theme
        is such a publish, as a hang is.
        """
        return not self._settings.manifest_v2_path(wall_id).exists()

    def _publish_additions(self, wall_id: str, theme_id: str, work_ids: Iterable[str], *, cause: str) -> bool:
        """Republish the hung theme's feed if one of these works joins it, or if it has none. True if it did.

        Built as a hang builds it, and published as re-hanging the same theme
        publishes it: the slot on the wall now is kept. A work joins when the
        build sends it and the feed does not carry it. Only then, because a
        republish reshuffles the slots to come, and only for the works the act
        or the announcement concerns: a feed names only what its horizon
        schedules, so a member it lacks may simply not be due.
        """
        feed = read_published_v2(self._settings.manifest_v2_path(wall_id))
        build = self.build_manifest(wall_id, theme_id)
        sent = {work.work_id for work in build.entries}
        joining = sorted(set(work_ids) & sent - set(feed.works if feed is not None else ()))
        if feed is not None and not joining:
            return False
        self._sync_v2(build)
        log.info(
            "Wall %r: published theme %r%s (after %s).",
            build.wall.name,
            build.theme.name,
            f" with {', '.join(joining)} joining" if joining else ", which had no feed on this wall",
            cause,
        )
        return True

    # -- the feed: the wall's schedule ------------------------------------------
    #
    # Published from every path that changes what a wall shows: a sync
    # (re-hanging the same theme keeps the slot on the wall now; another theme
    # starts fresh), a work joining the hung theme and a wall with a theme hung
    # and no feed (a sync, `_publish_additions`), show now and next (start
    # fresh), a withdrawal or a refusal (keep, unless the work on the wall is
    # the one leaving), a new master or colour (patch, no slot moves), and a
    # heartbeat with under two days of horizon left (a sync of the hung theme,
    # or keep what is carried when nothing is hung). Each reads the wall's published feed back rather than
    # a copy of its own, for the reason `manifest/v2.py` gives.

    def _sync_v2(self, build: ManifestBuild) -> None:
        """Publish the wall's feed from a build.

        The same theme as the feed already carries keeps the slot on the wall now
        (re-hanging it is how a curator republishes); another theme starts fresh.
        """
        previous = read_published_v2(self._settings.manifest_v2_path(build.wall.id))
        works: dict[str, Mapping[str, Any]] = {work.work_id: work_document(work) for work in build.entries}
        start: Start = StartFresh()
        guests: dict[str, Mapping[str, Any]] = {}
        if previous is not None and previous.playlist_id == build.theme.id:
            start = Keep()
            # A work on the wall now that the theme does not hold (shown from
            # outside it, or just taken out of it) finishes its slot. A member is
            # never a guest: one the Library now refuses, or one that lost its
            # master, would otherwise finish its slot on a superseded entry.
            members = {work.work_id for work in build.entries} | {exclusion.work_id for exclusion in build.exclusions}
            guests = {work_id: entry for work_id, entry in previous.works.items() if work_id not in members}
        self._write_v2(
            build.wall.id,
            playlist=(build.theme.id, build.theme.name),
            order=list(works),
            works={**guests, **works},
            slot_seconds=build.rotation_interval_seconds,
            shuffle=build.shuffle,
            start=start,
        )

    def _restart(self, wall_id: str, *, pinned: PlayableWork | None) -> str:
        """Republish the wall's feed starting now, and return the work it starts with.

        With the pinned work, or with the one after the work on the wall now.
        Refused by name when there is nothing to restart, or the work has nothing
        the feed could send: answering "done" while the wall goes on as it was is
        the silence this product exists to avoid.
        """
        wall = self.get_wall(wall_id)
        previous = read_published_v2(self._settings.manifest_v2_path(wall_id))
        if previous is None:
            raise ServiceError(
                f"Nothing has been hung on {wall.name!r} yet, so there is nothing to move on. Hang a theme there first."
            )
        if pinned is None and not previous.works:
            raise ServiceError(
                f"Nothing hanging on {wall.name!r} can be shown yet, so there is nothing to move on to. "
                "Walls lists each of its works that is not on the wall, with why."
            )
        works = dict(previous.works)
        if pinned is not None:
            works[pinned.work_id] = work_document(pinned)
        first = pinned.work_id if pinned is not None else previous.after(datetime.now(UTC))
        schedule = self._rebuild_v2(wall_id, previous, works=works, start=StartFresh(first))
        return schedule.slots[0].work_id

    def _withdraw_v2(self, wall_id: str, refused: set[str], *, cause: str) -> bool:
        """Take these works off the wall's feed, adding none. True if the feed carried any of them.

        The slot on the wall now is kept unless it shows one of them, and then the
        wall starts fresh: `Keep` keeps only a work the rebuild still carries.
        """
        previous = read_published_v2(self._settings.manifest_v2_path(wall_id))
        if previous is None or not refused & set(previous.works):
            return False
        works = {work_id: entry for work_id, entry in previous.works.items() if work_id not in refused}
        self._rebuild_v2(wall_id, previous, works=works, start=Keep())
        log.info(
            "Wall %r: took %s off the feed (after %s).",
            self.get_wall(wall_id).name,
            ", ".join(sorted(refused & set(previous.works))),
            cause,
        )
        return True

    def _roll_v2(self, wall_id: str) -> None:
        """Extend the wall's horizon when less than `ROLL_WHEN_LEFT` of it is left.

        Run on the wall's heartbeat, which a live wall sends every few seconds, so
        no scheduler is needed; a wall nobody is running needs no fresh horizon,
        and its Player replays the one it has when it comes back.

        **A wall with a theme hung rolls by building the theme**, as re-hanging
        it does. A feed names only the works its horizon schedules, so rolling
        from those alone narrowed a theme with more works than one horizon
        shows to the ones it happened to show first. So a reorder or a new pace
        reaches the wall at the next roll, within a day, without a re-hang. A wall with nothing hung
        goes on with what its feed carries.
        """
        with self._store.transaction():
            previous = read_published_v2(self._settings.manifest_v2_path(wall_id))
            if previous is None or previous.horizon_until - datetime.now(UTC) >= ROLL_WHEN_LEFT:
                return
            assignment = self._store.get_assignment(wall_id)
            if assignment is not None:
                build = self.build_manifest(wall_id, assignment.theme_id)
                self._sync_v2(build)
                # Said, because this is also how a work whose announcement was
                # lost reaches the wall, and how a reorder or a new pace does.
                log.info(
                    "Wall %r: rolled its horizon forward from theme %r, %d of %d works.",
                    build.wall.name,
                    build.theme.name,
                    len(build.entries),
                    build.considered,
                )
                return
            self._rebuild_v2(wall_id, previous, works=dict(previous.works), start=Keep())

    def _rebuild_v2(self, wall_id: str, previous: Published, *, works: Mapping[str, Mapping[str, Any]], start: Start) -> Schedule:
        """Rebuild a wall's feed from what it carries now: no work arrives that is not already in it.

        A horizon rolled forward or a work withdrawn cycles through the works
        already published, in the theme's order and at its pace. A work joining
        the hung theme arrives by `_publish_additions`, which builds the theme.
        """
        order, slot_seconds, shuffle = self._v2_pace(previous.playlist_id, works)
        return self._write_v2(
            wall_id,
            playlist=(previous.playlist_id, previous.playlist_name),
            order=order,
            works=works,
            slot_seconds=slot_seconds,
            shuffle=shuffle,
            start=start,
        )

    def _v2_pace(self, playlist_id: str, works: Mapping[str, Any]) -> tuple[list[str], int, bool]:
        """The cycle (the theme's members the feed carries, in its order), the slot length and the shuffle.

        A theme deleted since (possible once it hangs nowhere, after `clear_wall`)
        leaves the works the feed carries in id order at the default pace.
        """
        theme = self._store.get_theme(playlist_id)
        if theme is None:
            return sorted(works), self._settings.rotation_interval_seconds, self._settings.shuffle
        members = [membership.artwork_id for membership in self._store.list_memberships(theme.id)]
        interval = (
            theme.rotation_interval_seconds
            if theme.rotation_interval_seconds is not None
            else self._settings.rotation_interval_seconds
        )
        return [work_id for work_id in members if work_id in works], interval, self.shuffles(theme)

    def _write_v2(
        self,
        wall_id: str,
        *,
        playlist: tuple[str, str],
        order: Sequence[str],
        works: Mapping[str, Mapping[str, Any]],
        slot_seconds: int,
        shuffle: bool,
        start: Start,
    ) -> Schedule:
        """Schedule the wall against every other wall's published feed, and publish it.

        `order` is the cycle; any other work in `works` may only finish the slot
        it is in now, or be the one a `StartFresh` names.
        """
        now = datetime.now(UTC)
        published = {
            wall.id: feed.slots
            for wall in self._store.list_walls()
            if (feed := read_published_v2(self._settings.manifest_v2_path(wall.id))) is not None
        }
        cycle = [work_id for work_id in order if work_id in works]
        schedule = build_schedule(
            wall_id=wall_id,
            work_ids=cycle,
            slot_seconds=slot_seconds,
            shuffle=shuffle,
            now=now,
            start=start,
            published=published,
            seed=f"{wall_id}:{now.isoformat()}",
            also_showable=set(works) - set(cycle),
        )
        feed = Feed(
            playlist_id=playlist[0],
            playlist_name=playlist[1],
            schedule=schedule,
            works=works,
            settings=self._feed_settings(wall_id),
        )
        write_atomically(self._settings.manifest_v2_path(wall_id), as_v2_document(feed))
        if schedule.clashes:
            # Named, because a clash is the household rule giving way, and a rule
            # that gives way silently is one nobody can tell is still in force.
            shared = sorted({(clash.work_id, clash.other_wall_id) for clash in schedule.clashes})
            log.info(
                "Wall %r shows works another wall shows at the same time, having nothing else to show then: %s.",
                self.get_wall(wall_id).name,
                ", ".join(f"{work_id} (with {other})" for work_id, other in shared),
            )
        return schedule

    def _reconcile_v2(
        self,
        wall_id: str,
        feed: Published | None,
        answers: Mapping[str, PlayableWork | Unplayable],
        *,
        cause: str,
    ) -> bool:
        """Bring one wall's feed in line with the Library's answers. True if it was rewritten.

        A work the Library refuses, its master included, leaves; a work
        whose master, colour or label changed has its entry replaced where it
        stands. Works the Library was not asked about are left as they are.
        """
        if feed is None:
            return False
        gone: set[str] = set()
        fresh: dict[str, Mapping[str, Any]] = {}
        for work_id, entry in feed.works.items():
            answer = answers.get(work_id)
            if answer is None:
                continue
            if not isinstance(answer, PlayableWork):
                gone.add(work_id)
            elif (current := work_document(answer)) != entry:
                fresh[work_id] = current
        if gone:
            works = {work_id: fresh.get(work_id, entry) for work_id, entry in feed.works.items() if work_id not in gone}
            self._rebuild_v2(wall_id, feed, works=works, start=Keep())
            log.info(
                "Wall %r: took works the Library no longer offers off the feed (%s, after %s).",
                self.get_wall(wall_id).name,
                ", ".join(sorted(gone)),
                cause,
            )
            return True
        if fresh:
            self._patch_v2_works(wall_id, feed, fresh)
            log.info(
                "Wall %r: pointed the feed at the current master or colour of %s (after %s).",
                self.get_wall(wall_id).name,
                ", ".join(sorted(fresh)),
                cause,
            )
            return True
        return False

    def _feed_settings(self, wall_id: str) -> dict[str, Any]:
        """The wall's presentation settings as its feed carries them: only what the curator chose.

        A key nobody set is absent, so the Player falls to its own default, as a
        channel reader would (`player-contract.md` § Presentation settings).
        """
        wall = self.get_wall(wall_id)
        return {} if wall.mat_mode is None else {"mat": {"mode": wall.mat_mode}}

    def _patch_v2_works(self, wall_id: str, feed: Published, entries: Mapping[str, Mapping[str, Any]]) -> None:
        """Replace these works' entries and the wall's settings in its published feed, and nothing else.

        A re-render, a new mat colour or a new mat mode changes what the Player
        composes, not when: the schedule is republished exactly as it stands,
        through the same builder every other feed goes through.
        """
        schedule = Schedule(feed.horizon_from, feed.horizon_until, feed.slots, ())
        works = {**feed.works, **entries}
        settings = self._feed_settings(wall_id)
        document = as_v2_document(Feed(feed.playlist_id, feed.playlist_name, schedule, works, settings))
        write_atomically(self._settings.manifest_v2_path(wall_id), document)

    # -- internals ------------------------------------------------------------

    def _retire_selection(self, replaced: ThemeAssignment | None) -> None:
        """Delete the selection a wall stopped hanging, if no other wall still hangs it.

        A selection is made for one hang and has no name a curator chose, so
        once nothing hangs it nobody can find it to hang again, and keeping it
        would leave one hidden theme behind per hang for good. History does not
        need the row: a hang event carries the selection's name and id itself.
        Called inside the caller's transaction, after the new assignment is
        written, so `walls_hanging` already sees the wall as moved on.
        """
        if replaced is None:
            return
        theme = self._store.get_theme(replaced.theme_id)
        if theme is None or not theme.hidden or self.walls_hanging(theme.id):
            return
        for membership in self._store.list_memberships(theme.id):
            store_write(self._store.remove_membership, theme.id, membership.artwork_id)
        store_write(self._store.remove_theme, theme.id)

    def _record_hang(self, build: ManifestBuild) -> None:
        """Tell the Library's history what was hung where, once the hang has committed."""
        self._library.record(
            ProgrammingAct(
                kind=EventKind.HUNG,
                wall_id=build.wall.id,
                theme_id=build.theme.id,
                detail={
                    "theme_name": build.theme.name,
                    "selection": build.theme.hidden,
                    "works": build.considered,
                    "wall_name": build.wall.name,
                },
            )
        )

    def _withdraw(self, artwork_id: str, wall_ids: Iterable[str], *, cause: str) -> None:
        """Take one work off these walls' published feeds, adding nothing.

        The patch reconciliation applies, narrowed to one work and to the walls
        named.
        """
        for wall_id in wall_ids:
            self._withdraw_v2(wall_id, {artwork_id}, cause=cause)

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


#: When a wall's published horizon has less than this left, its next heartbeat
#: republishes it. Two of the horizon's three days: a server that comes back after
#: a day away still finds a day in hand on every wall, and a live wall, which
#: reports every few seconds, is extended about once a day.
ROLL_WHEN_LEFT: Final[timedelta] = timedelta(days=2)

#: How far back a reported screen size counts toward a wall's largest
#: (`player-contract.md` § The heartbeat, minor 2: "the largest size reported
#: recently"). A week: long enough that a screen switched off for a weekend is
#: still remembered, short enough that a screen replaced by a smaller one stops
#: counting within days.
SCREEN_MEMORY: Final[timedelta] = timedelta(days=7)

#: How long a reported size stands before the same report writes it again. An
#: hour against a week's memory: a screen still reporting is never near falling
#: out of the window, and a live wall costs one write an hour, not one a minute.
SCREEN_REFRESH: Final[timedelta] = timedelta(hours=1)
