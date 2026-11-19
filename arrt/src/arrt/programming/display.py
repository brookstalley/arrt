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
from arrt.persistence.records import (
    Scene,
    SceneEnding,
    SceneLifetime,
    ScenePin,
    SceneStatus,
    Showing,
    Theme,
    ThemeAssignment,
    ThemeMembership,
    Wall,
    WorkExclusion,
)
from arrt.programming import adequacy, shape, showings
from arrt.programming.clients import Placements
from arrt.programming.display_state import DisplayState, ReportedState, ScreenState, reported_state
from arrt.programming.feeds import FeedPublisher, Reconciliation, applied_at, log_published
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.builder import ManifestBuild, write_atomically
from arrt.programming.manifest.heartbeat import HeartbeatReading, heartbeat_path_in
from arrt.programming.manifest.v2 import SCHEMA_MAJOR as MANIFEST_MAJOR
from arrt.programming.manifest.v2 import manifest_v2_path_in
from arrt.programming.schedule import Slot
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

#: What a caller with only text to send says for each shuffle setting, the
#: deployment default included, which such a caller cannot say as null.
SHUFFLED: Final[str] = "shuffled"
IN_ORDER: Final[str] = "in_order"
DEFAULT_SHUFFLE: Final[str] = "default"
SHUFFLE_CHOICES: Final[Mapping[str, bool | None]] = {SHUFFLED: True, IN_ORDER: False, DEFAULT_SHUFFLE: None}


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

    **Named for the service rather than for a wall**, because a wall is now a
    first-class entity with a name and an id: a type called `WallSettings` beside
    `Services.bind(wall=…)` read as though the container were being handed a
    wall, when what it is handed is where this installation publishes and the
    pace a theme inherits when it has expressed none of its own.

    Passed in rather than read from the environment here, because a service that
    resolved its own configuration could not be tested against two deployments
    and would make every caller share one.
    """

    #: The art root, where this server keeps each wall's feed and heartbeat. They
    #: are named from it **per wall**, so this holds the root and not a file: the catalogue
    #: names as many walls as the curator has rooms, and each one has its own
    #: pair of files.
    art_root: Path
    #: What a wall that has chosen no pace of its own plays at.
    rotation_interval_seconds: int
    shuffle: bool

    def manifest_v2_path(self, wall_id: str) -> Path:
        """Where this server publishes one wall's feed."""
        return manifest_v2_path_in(self.art_root, wall_id)

    def heartbeat_path(self, wall_id: str) -> Path:
        """Where one wall's last heartbeat is kept: written by `record_heartbeat`, from what its Player POSTs."""
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
    #: The work the wall showed last, whatever its screen does now (`showings.py`);
    #: None while it has shown nothing.
    last_shown: Showing | None = None
    #: Up to `UPCOMING` slots of the published schedule starting after now: what
    #: the wall's Player will put up next, in order.
    upcoming: Sequence[Slot] = ()


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
    Whether four minutes is late is the reader's to decide, because this server
    does not know whether that television was switched off on purpose.

    A function rather than a method, because the browser panel and the tool
    surface both state this and neither owns it: two hand-written sentences from
    the same readings drift, and a caller told "the study has not reported" by
    one surface and "every wall has reported" by the other cannot tell which is
    lying.
    """
    if not readings:
        # Unreachable through a catalogue this server opened, which seeds a wall on
        # first open — so it means a file something else wrote, and saying that
        # plainly beats a sentence composed over an empty list that reads as an
        # all-clear.
        return "No wall is in the catalogue, so there is nothing for a Player to report about."
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
class SceneView:
    """A scene and its pins, as one read found them."""

    scene: Scene
    pins: Sequence[ScenePin]

    @property
    def wall_ids(self) -> list[str]:
        return [pin.wall_id for pin in self.pins]


@dataclass(frozen=True, slots=True)
class SceneWall:
    """One wall in a scene, as Walls shows it: its work, and whether it has reached the scene.

    `reached` is the wall's own word: its last heartbeat names this scene
    (`player-contract.md` § The heartbeat, minor 2, `scene_id`). Never stored,
    because whether a wall reached a scene is the wall's runtime state.
    """

    wall_id: str
    wall_name: str
    work_id: str
    #: The work's title as the Library gives it; None for an id it does not hold.
    title: str | None
    reached: bool
    #: Why the wall cannot show its work in the scene now, in the Library's or
    #: the curator's words, or None. A work archived or kept off every wall
    #: after it was pinned leaves the wall's feed, so the wall shows its
    #: schedule; it returns if the work is restored or allowed again.
    cannot_show: str | None
    #: What the wall's screen is doing now, so a wall not there yet can say why:
    #: `in_use` is somebody watching television, and the Player waits for it.
    screen: ScreenState


#: A scene just ended, its pins, how, and the words its journal line says.
type _Ended = tuple[Scene, Sequence[ScenePin], SceneEnding, str]


class DisplayService:
    """Read and write the themes, memberships, and feeds the walls run on."""

    def __init__(self, store: ProgrammingStore, library: LibraryFacade, settings: DisplaySettings) -> None:
        self._store = store
        self._library = library
        self._settings = settings
        self._placements = Placements(store, settings.art_root)
        #: Everything that builds, stages and publishes a wall's feed (`feeds.py`).
        self._feeds = FeedPublisher(store, library, settings)

    # -- reads: themes --------------------------------------------------------

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme."""
        return self._store.list_themes()

    def get_theme(self, theme_id: str) -> Theme:
        """Return one theme."""
        return self._feeds.get_theme(theme_id)

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

    def pace(self, wall: Wall) -> tuple[int, bool]:
        """How long each work stays up on this wall, and whether it plays shuffled (`FeedPublisher.pace`)."""
        return self._feeds.pace(wall)

    def default_theme(self) -> Theme | None:
        """The theme new works join, or None while the curator has marked none."""
        return self._store.get_default_theme()

    # -- reads: walls and what hangs on them -----------------------------------

    def get_wall(self, wall_id: str) -> Wall:
        """Return one wall."""
        return self._feeds.get_wall(wall_id)

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
            last_shown=self._store.latest_showing(wall.id),
            upcoming=self._upcoming(wall.id),
        )

    def _display_state(self, wall: Wall) -> DisplayState:
        """What the wall's screen is doing, read from its heartbeat file now, as every label reads it too."""
        return self._placements.wall_state(wall).state

    def _upcoming(self, wall_id: str) -> Sequence[Slot]:
        """The published schedule's next slots, starting after now: the one on the wall now is not among them."""
        published = self._feeds.published(wall_id)
        if published is None:
            return ()
        now = datetime.now(UTC)
        return tuple(slot for slot in published.slots if slot.start > now)[:UPCOMING]

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
            last_shown=self._store.latest_showing(wall.id),
            upcoming=self._upcoming(wall.id),
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
        wall has shown**, which is `last_shown_by_work`'s, from the Players'
        reports. Nor is it readiness: a held work a wall would skip for want of a
        render still counts as on it, since the curator's act — hanging the
        theme — is what this answers for.

        Ids, opaque to Programming, for the bindings to hand the Library, as
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
            self._refuse_a_taken_name(wall)
            store_write(self._store.add_wall, wall)
        return wall

    def rename_wall(self, wall_id: str, *, name: str) -> Wall:
        """Give a wall a new name; a name another wall has is refused, as at `add_wall`.

        **Nothing is republished.** A feed names works and slots, never the wall
        (`player-contract.md`), so a Player sees no change. What changes is what a
        person reads: Walls, History, and every confirmation that names the wall.
        """
        chosen = require_text(name, field="name")
        # Read inside the transaction it writes in, as every whole-row write of
        # a wall is: a Player's heartbeat can move the wall to another display
        # (`ClientService._merge_place`), and a wall read before it would put
        # the old display back.
        with self._store.transaction():
            wall = self.get_wall(wall_id)
            renamed = replace(wall, name=chosen)
            self._refuse_a_taken_name(renamed)
            store_write(self._store.update_wall, renamed)
        log.info("Wall %r is now called %r.", wall.name, renamed.name)
        return renamed

    def _refuse_a_taken_name(self, wall: Wall) -> None:
        """Refuse a name another wall has, in words a person reads in a dialog.

        The file's UNIQUE constraint still holds the rule; this says it first, because
        the store's own refusal ("already stored") is about rows, not rooms.
        """
        if any(other.name == wall.name and other.id != wall.id for other in self._store.list_walls()):
            raise ServiceError(f"Another wall is already called {wall.name!r}.")

    def delete_wall(self, wall_id: str) -> Wall:
        """Forget a wall for good, freeing its screen and its label panels; its history stays.

        The owner's rulings of 2026-10-30 (`build-plan-delete-a-wall.md` § Goals),
        each row that names the wall decided rather than left to a foreign key:

        - **What it hangs comes down**, and a selection nothing else hangs is
          retired as `clear_wall` retires one. The theme stays: it is not the
          wall's, and a theme hung here is no reason to refuse.
        - **Its label panels stay recorded and caption nothing**, offered to
          other walls as any free panel is. Its screen is freed with the row.
        - **Its pick in a scene being assembled goes**, or the draft could never
          be applied. In the live scene its pin is kept: that is the scene's
          record, and the scene goes on for the walls left (`scene_walls`
          skips a wall no longer recorded).
        - **Its showings and history stay**, as `data-model.md` says they
          outlive a wall; no event is written for the delete, as none is for a
          theme deleted or a Player removed.
        - **Its feed and heartbeat files go**, after the commit, as a removed
          Player's report does. Its Player stops showing it on its next poll:
          `GET /client` no longer lists it, and its routes answer 403 for a wall
          the server does not hold (`player-contract.md`).

        The last wall may go too; the file then opens with none
        (`migrations.establish_the_wall`). Returns the wall as it was, so a
        caller can name it.
        """
        with self._store.transaction():
            wall = self.get_wall(wall_id)
            assignment = self._store.get_assignment(wall_id)
            if assignment is not None:
                store_write(self._store.remove_assignment, wall_id)
                self._retire_selection(assignment)
            for label in self._store.list_label_outputs():
                if label.wall_id == wall_id:
                    store_write(self._store.update_label_output, replace(label, wall_id=None))
            for draft in self._store.list_scenes(SceneStatus.DRAFT):
                if any(pin.wall_id == wall_id for pin in self._store.list_pins(draft.id)):
                    store_write(self._store.remove_pin, draft.id, wall_id)
            store_write(self._store.remove_wall, wall_id)
        # After the commit, for the reason `ClientService.remove_client` gives:
        # files nothing will read again would otherwise sit under the art root.
        self._settings.manifest_v2_path(wall_id).unlink(missing_ok=True)
        self._settings.heartbeat_path(wall_id).unlink(missing_ok=True)
        log.info(
            "Deleted wall %r (%s)%s.",
            wall.name,
            wall_id,
            (
                f"; took down {self.get_theme(assignment.theme_id).name!r}"
                if assignment and self._store.get_theme(assignment.theme_id)
                else ""
            ),
        )
        return wall

    # -- writes: themes and membership ----------------------------------------

    def set_mat_mode(self, wall_id: str, mode: MatMode | str | None) -> Wall:
        """Choose how this wall's Player draws the mat, or with None leave it to the Player.

        Republishes the wall's feed with the setting and changes nothing else in
        it: the schedule and every work stay as published.
        """
        chosen = None if mode is None else require_member(mode, enum=MatMode, field="mat mode").value
        # Read where it is written, for the reason `rename_wall` gives.
        with self._feeds.publishing():
            wall = self.get_wall(wall_id)
            store_write(self._store.update_wall, replace(wall, mat_mode=chosen))
            feed = self._feeds.published(wall_id)
            if feed is not None:
                self._feeds.patch_v2_works(wall_id, feed, {})
        log.info("Wall %r: the mat is now %s.", wall.name, chosen or "the Player's own choice")
        return self.get_wall(wall_id)

    def set_playback(
        self,
        wall_id: str,
        *,
        rotation_interval_seconds: int | Unset | None = UNSET,
        shuffle: bool | Unset | None = UNSET,
        tallest: str | Unset | None = UNSET,
        widest: str | Unset | None = UNSET,
    ) -> Wall:
        """Choose how this wall plays its theme: how long each work stays up, in what order, and which shapes.

        None on the interval or shuffle is the deployment default. `tallest` and
        `widest` are spelled as a curator says them (`shape.parse`: `4:5`, `0.8`,
        or `any`), and None on either is no limit. An omitted setting is left as
        it is.

        The wall's feed is republished at once, keeping the work on the wall
        now: a new order, pace or range changes the slots after it, which is
        what the curator asked for, not something to wait a day's roll for. A
        range that leaves nothing is honoured: the wall goes dark, and the
        build's summary says so.

        **On a wall with nothing hung, the range waits for the next hanging.**
        The feed such a wall carries is re-paced, but not trimmed: with no theme
        to rebuild from, a work the range took off could never come back when
        the range was widened again.
        """
        # Read where it is written, for the reason `rename_wall` gives.
        with self._feeds.publishing():
            wall = self.get_wall(wall_id)
            chosen = replace(
                wall,
                rotation_interval_seconds=(
                    wall.rotation_interval_seconds
                    if isinstance(rotation_interval_seconds, Unset)
                    else self._require_interval(rotation_interval_seconds)
                ),
                shuffle=wall.shuffle if isinstance(shuffle, Unset) else shuffle,
                min_aspect_ratio=(
                    wall.min_aspect_ratio if isinstance(tallest, Unset) else None if tallest is None else shape.parse(tallest)
                ),
                max_aspect_ratio=(
                    wall.max_aspect_ratio if isinstance(widest, Unset) else None if widest is None else shape.parse(widest)
                ),
            )
            shape.require_range(chosen.min_aspect_ratio, chosen.max_aspect_ratio)
            store_write(self._store.update_wall, chosen)
            build = self._feeds.republish(wall_id, self._feeds.published(wall_id))
        interval, shuffled = self.pace(chosen)
        log.info(
            "Wall %r: each work stays up %ds%s, %s%s; it shows %s.",
            wall.name,
            interval,
            "" if chosen.rotation_interval_seconds is not None else " (the default)",
            "shuffled" if shuffled else "in the theme's order",
            "" if chosen.shuffle is not None else " (the default)",
            shape.described(chosen.min_aspect_ratio, chosen.max_aspect_ratio) or "every shape",
        )
        if build is not None:
            log_published(build)
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
        # and never with the store's lock held.
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

        For an announcement lost between the Library's commit and Programming's
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

        **Here, the switch is a file rewrite**: the server writes the wall's feed
        and nothing else. What it costs at the wall is the Player's: it reads the
        feed on its next poll and fetches, or for a Frame uploads to the
        television, any work of the new theme it does not hold, which can take a
        while. Nothing here writes to a television.

        It returns the build, not the theme, because the theme alone cannot say
        how much of itself reached the wall — and a switch that silently put up
        four of a theme's twelve works is the failure this report exists for.
        """
        self.get_theme(theme_id)
        # One act around the hang, the publish and the retirement, and it holds
        # both ways (`_publishing`). A feed that cannot be written takes the hang
        # back: recording the hang and then failing to publish left the
        # catalogue naming a theme the wall was not showing, with nothing to say
        # the two disagreed. And a step after the publish that raises (the
        # selection replaced cannot be retired) writes no feed, so the walls do
        # not show a hang the catalogue rolled back. What it replaces is read
        # inside, so a hang made meanwhile is the one retired.
        with self._feeds.publishing():
            self.get_wall(wall_id)
            replaced = self._store.get_assignment(wall_id)
            store_write(
                self._store.set_assignment,
                ThemeAssignment(wall_id=wall_id, theme_id=theme_id, assigned_at=datetime.now(UTC)),
            )
            build = self.sync(wall_id)
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
        theme_id = str(uuid.uuid4())
        theme = Theme(
            id=theme_id,
            # Names are unique across themes, hidden or not, so the id's head
            # keeps two selections for one wall apart.
            name=f"Selection for {wall.name} ({theme_id[:8]})",
            created_at=now,
            hidden=True,
        )
        # One act, and what it replaces read inside it, as `activate_theme` says.
        with self._feeds.publishing():
            replaced = self._store.get_assignment(wall_id)
            store_write(self._store.add_theme, theme)
            for position, artwork_id in enumerate(chosen):
                store_write(
                    self._store.add_membership,
                    ThemeMembership(theme_id=theme_id, artwork_id=artwork_id, added_at=now, position=position),
                )
            store_write(self._store.set_assignment, ThemeAssignment(wall_id=wall_id, theme_id=theme_id, assigned_at=now))
            build = self.sync(wall_id)
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
        # Read inside, so the theme it leaves is the one hanging when it leaves.
        with self._feeds.publishing():
            wall = self.get_wall(wall_id)
            theme = self._feeds.require_hanging(wall)
            if self._store.get_membership(theme.id, artwork_id) is None:
                raise ServiceError(
                    f"Artwork {artwork_id!r} is not in {theme.name!r}, which is what hangs on {wall.name!r}, "
                    "so there is nothing to take it out of."
                )
            store_write(self._store.remove_membership, theme.id, artwork_id)
            self._feeds.withdraw(artwork_id, [hung.id for hung in self.walls_hanging(theme.id)], cause="leaving its theme")
        self._library.record(
            ProgrammingAct(
                kind=EventKind.LEFT_THEME,
                wall_id=wall_id,
                theme_id=theme.id,
                work_id=artwork_id,
                # The wall's name too, as a hang carries it: a history outlives
                # the wall it names, and once that wall is deleted this is the
                # only place its name is kept.
                detail={"theme_name": theme.name, "selection": theme.hidden, "wall_name": wall.name},
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
        looking_at = self.get_wall(wall_id) if wall_id is not None else None
        if any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
            raise ServiceError(f"Artwork {artwork_id!r} is already kept off every wall.")
        exclusion = WorkExclusion(artwork_id=artwork_id, excluded_at=datetime.now(UTC))
        with self._feeds.publishing():
            store_write(self._store.add_exclusion, exclusion)
            self._feeds.withdraw(artwork_id, [wall.id for wall in self._store.list_walls()], cause="being kept off every wall")
        self._library.record(
            ProgrammingAct(
                kind=EventKind.EXCLUDED,
                wall_id=wall_id,
                work_id=artwork_id,
                # Named for the reason `leave_theme` names it.
                detail={"wall_name": looking_at.name} if looking_at else {},
            )
        )
        return exclusion

    def allow_work(self, artwork_id: str) -> None:
        """Undo *Not this one again* from every wall: the work may go on walls again.

        Every wall whose hung theme holds it gets it back now, if the Library
        will show it (`reconcile`, the owner's ruling of 2026-10-10).
        """
        if not any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
            raise ServiceError(f"Artwork {artwork_id!r} is not kept off the walls, so there is nothing to allow.")
        with self._feeds.publishing():
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
        # Read inside, so a hang made meanwhile is the one taken down and retired.
        with self._store.transaction():
            wall = self.get_wall(wall_id)
            assignment = self._store.get_assignment(wall_id)
            if assignment is None:
                raise ServiceError(f"Nothing is hanging on wall {wall_id!r}, so there is nothing to take down.")
            taken_down = self.get_theme(assignment.theme_id)
            store_write(self._store.remove_assignment, wall_id)
            self._retire_selection(assignment)
        # The only operation in Programming that deliberately leaves the catalogue
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
        with self._feeds.publishing():
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
        with self._feeds.publishing():
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
        with self._feeds.publishing():
            for artwork_id in dict.fromkeys(artwork_ids):
                if self._store.get_membership(theme_id, artwork_id) is None:
                    continue
                store_write(self._store.remove_membership, theme_id, artwork_id)
                removed.append(artwork_id)
            walls = [wall.id for wall in self.walls_hanging(theme_id)]
            for wall_id in walls:
                self._feeds.withdraw_v2(wall_id, set(removed), cause="leaving its theme")
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
        with self._feeds.publishing():
            store_write(self._store.remove_membership, theme_id, artwork_id)
            self._feeds.withdraw(artwork_id, [wall.id for wall in self.walls_hanging(theme_id)], cause="leaving its theme")

    def update_theme(
        self,
        theme_id: str,
        *,
        name: str | None = None,
        description: str | Unset | None = UNSET,
    ) -> Theme:
        """Change a theme's name or description.

        The description takes a sentinel rather than defaulting to `None`,
        because `None` is a meaningful value — "no description" — and a caller
        changing only the name would otherwise silently clear it.
        """
        theme = self.get_listed_theme(theme_id)
        updated = replace(
            theme,
            name=theme.name if name is None else require_text(name, field="name"),
            description=theme.description if isinstance(description, Unset) else description,
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
        as the server being stopped entirely: a Player runs off the last
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

    # -- reads: what each wall's Player says about itself -----------------------

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
        wall's picture alone, so a `next` aimed at the living room never moves
        the study; a wall sharing works with it has its slots to come rebuilt
        beside it (`_write_v2`).
        """
        self.get_wall(wall_id)
        with self._feeds.publishing():
            return self._feeds.restart(wall_id, pinned=None)

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
        answer = self._require_showable(artwork_id)
        with self._feeds.publishing():
            return self._feeds.restart(wall_id, pinned=answer)

    # -- scenes ---------------------------------------------------------------
    #
    # A scene is a work per wall, applied together over each wall's schedule
    # (`player-contract.md` § Scenes). While a draft, each pin stages its work
    # on its wall, so a Frame has its upload done before Apply and the walls
    # switch together. Every act writes the store, then patches each wall it
    # touched: the schedule is republished exactly as it stands, and the one
    # feed writer derives the control layer (`_publish_feed`). Expiry is
    # observed, not scheduled: a Player returns to its schedule at `until` on
    # its own, so the server keeps no timer.

    def draft_scene(self) -> SceneView:
        """The scene being assembled: the one already started, else a new empty one.

        One draft at a time, because the builder on Walls holds one; the store
        would take more, and only the newest stages anything (`_current_draft`).
        """
        with self._store.transaction():
            ended = self._settle_scenes()
            draft = self._feeds.current_draft()
            if draft is None:
                draft = Scene(id=str(uuid.uuid4()), status=SceneStatus.DRAFT, created_at=datetime.now(UTC))
                store_write(self._store.add_scene, draft)
            view = self._scene_view(draft)
        self._record_ended(ended)
        return view

    def pin_scene(self, scene_id: str, wall_id: str, artwork_id: str) -> SceneView:
        """Put this work on this wall in the draft, replacing the wall's earlier pick, and stage it there.

        **Refused as show now refuses**, in its words: a work the Library will
        not show, or one kept off every wall. Refused too for a wall with no
        feed, whose Player has nothing to show a scene over. A refusal changes
        nothing in the draft.
        """
        wall = self.get_wall(wall_id)
        answer = self._require_showable(artwork_id)
        with self._feeds.publishing():
            scene = self._require_scene(scene_id, SceneStatus.DRAFT)
            if self._feeds.published(wall_id) is None:
                raise ServiceError(
                    f"Nothing has been hung on {wall.name!r} yet, so it has no feed to show a scene over. "
                    "Hang a theme there first."
                )
            store_write(self._store.set_pin, ScenePin(scene_id=scene.id, wall_id=wall_id, work_id=answer.work_id))
            self._feeds.patch_walls([wall_id])
        _log_scene("staged", scene_id, [wall_id], f"staging {answer.work_id} on wall {wall.name!r}")
        return self.get_scene(scene_id)

    def unpin_scene(self, scene_id: str, wall_id: str) -> SceneView:
        """Take this wall out of the draft and stop staging its work there."""
        wall = self.get_wall(wall_id)
        with self._feeds.publishing():
            self._require_scene(scene_id, SceneStatus.DRAFT)
            store_write(self._store.remove_pin, scene_id, wall_id)
            self._feeds.patch_walls([wall_id])
        _log_scene("unstaged", scene_id, [wall_id], f"nothing staged on wall {wall.name!r} any more")
        return self.get_scene(scene_id)

    def discard_scene(self, scene_id: str) -> None:
        """Forget a draft, and stop staging its works."""
        with self._feeds.publishing():
            self._require_scene(scene_id, SceneStatus.DRAFT)
            walls = [pin.wall_id for pin in self._store.list_pins(scene_id)]
            for wall_id in walls:
                store_write(self._store.remove_pin, scene_id, wall_id)
            store_write(self._store.remove_scene, scene_id)
            self._feeds.patch_walls(walls)
        _log_scene("discarded", scene_id, walls, "discarded before it was applied")

    def apply_scene(self, scene_id: str, *, lifetime: SceneLifetime | str, minutes: int | None = None) -> SceneView:
        """Show the draft on every wall it pins, now: for `minutes` as a preview, or until released as a hold.

        A preview with no length is `PREVIEW_MINUTES` long. **Any other live
        scene ends**, because a wall shows one scene and the builder offers one.
        Each pin is checked again as it was when made, and a refusal names its
        wall and applies nothing.
        """
        chosen = SceneLifetime(require_member(lifetime, enum=SceneLifetime, field="lifetime"))
        if chosen is SceneLifetime.HOLD and minutes is not None:
            raise ServiceError("A held scene stays until it is released, so it takes no length.")
        length = PREVIEW_MINUTES if minutes is None else minutes
        if chosen is SceneLifetime.PREVIEW and length <= 0:
            raise ServiceError(f"A preview must last at least a minute, got {length}.")
        if chosen is SceneLifetime.PREVIEW and length > MAX_PREVIEW_MINUTES:
            raise ServiceError(
                f"A preview lasts at most {MAX_PREVIEW_MINUTES} minutes, got {length}. Hold the scene to keep it longer."
            )
        with self._feeds.publishing():
            ended = self._settle_scenes()
            scene = self._require_scene(scene_id, SceneStatus.DRAFT)
            pins = self._store.list_pins(scene_id)
            if not pins:
                raise ServiceError("This scene has no walls in it yet. Pick a work for a wall first.")
            for pin in pins:
                wall = self.get_wall(pin.wall_id)
                try:
                    self._require_showable(pin.work_id)
                except ServiceError as refusal:
                    raise ServiceError(f"{wall.name}: {refusal}") from refusal
            now = datetime.now(UTC)
            ended += [
                self._end(other, at=now, how=SceneEnding.REPLACED, words=f"replaced by scene {scene_id}")
                for other in self._store.list_scenes(SceneStatus.LIVE)
                if other.status_at(now) is SceneStatus.LIVE
            ]
            applied = replace(
                scene,
                status=SceneStatus.LIVE,
                lifetime=chosen,
                starts_at=now,
                until=now + timedelta(minutes=length) if chosen is SceneLifetime.PREVIEW else None,
            )
            store_write(self._store.update_scene, applied)
            walls = [pin.wall_id for pin in pins]
            replaced = (pin.wall_id for _, ended_pins, how, _ in ended if how is SceneEnding.REPLACED for pin in ended_pins)
            self._feeds.patch_walls([*walls, *replaced])
        self._record_ended(ended)
        self._record_scene(EventKind.SCENE_APPLIED, applied, pins, lifetime=str(chosen), until=_iso(applied.until))
        _log_scene(
            "applied",
            scene_id,
            walls,
            f"applied on {self._wall_names(walls)}, "
            + (f"until {applied.until.isoformat()}" if applied.until else "held until released"),
        )
        return self.get_scene(scene_id)

    def release_scene(self, scene_id: str) -> SceneView:
        """End a live scene now; each of its walls returns to its schedule where the schedule is now."""
        with self._feeds.publishing():
            ended = self._settle_scenes()
            scene = self._require_scene(scene_id, SceneStatus.LIVE)
            released = self._end(scene, at=datetime.now(UTC), how=SceneEnding.RELEASED, words="released")
            self._feeds.patch_walls(pin.wall_id for pin in released[1])
        self._record_ended([*ended, released])
        return self.get_scene(scene_id)

    def live_scene(self) -> SceneView | None:
        """The scene on the walls now, or None. A preview whose end has passed is not live, written or not."""
        now = datetime.now(UTC)
        with self._store.reading():
            live = [scene for scene in self._store.list_scenes(SceneStatus.LIVE) if scene.status_at(now) is SceneStatus.LIVE]
            return self._scene_view(max(live, key=applied_at)) if live else None

    def scene_draft(self) -> SceneView | None:
        """The scene being assembled, or None."""
        with self._store.reading():
            draft = self._feeds.current_draft()
            return None if draft is None else self._scene_view(draft)

    def get_scene(self, scene_id: str) -> SceneView:
        """A scene and its pins, with its status as of now."""
        with self._store.reading():
            scene = self._store.get_scene(scene_id)
            if scene is None:
                raise ServiceError(f"No scene with id {scene_id!r}.")
            return self._scene_view(scene)

    def scene_walls(self, view: SceneView) -> list[SceneWall]:
        """Each wall a scene pins, with its work and whether its last heartbeat reports the scene."""
        walls: list[SceneWall] = []
        answers = self._library.playable(sorted({pin.work_id for pin in view.pins}))
        kept_off = {exclusion.artwork_id for exclusion in self._store.list_exclusions()}
        for pin in self._pins_on_held_walls(view.pins):
            wall = self._store.get_wall(pin.wall_id)
            contents = heartbeat.read(self._settings.heartbeat_path(wall.id)).contents or {}
            walls.append(
                SceneWall(
                    wall_id=wall.id,
                    wall_name=wall.name,
                    work_id=pin.work_id,
                    title=answers[pin.work_id].title if pin.work_id in answers else None,
                    reached=contents.get("scene_id") == view.scene.id,
                    cannot_show=_cannot_show(answers.get(pin.work_id), kept_off=pin.work_id in kept_off),
                    screen=self._display_state(wall).state,
                )
            )
        return walls

    def _scene_view(self, scene: Scene) -> SceneView:
        now = datetime.now(UTC)
        if scene.status_at(now) is not scene.status:
            scene = replace(scene, status=scene.status_at(now), ended_at=scene.until)
        return SceneView(scene=scene, pins=tuple(self._store.list_pins(scene.id)))

    def _require_scene(self, scene_id: str, status: SceneStatus) -> Scene:
        scene = self._store.get_scene(scene_id)
        if scene is None:
            raise ServiceError(f"No scene with id {scene_id!r}.")
        actual = scene.status_at(datetime.now(UTC))
        if actual is not status:
            raise ServiceError(_SCENE_NOT[status].format(status=actual.value))
        return scene

    def _end(self, scene: Scene, *, at: datetime, how: SceneEnding, words: str) -> _Ended:
        """Write a live scene's end and return it with its pins: the one place a scene ends.

        Released or replaced ends it now; a preview run out ends it at its
        `until`. The caller republishes the walls, or, for a preview run out,
        leaves them: their Players returned to the schedule on their own. The
        caller says it and records it in History once its transaction commits
        (`_record_ended`), so a refusal that rolls the end back leaves no line
        claiming it.
        """
        ended = replace(scene, status=SceneStatus.ENDED, ended_at=at)
        store_write(self._store.update_scene, ended)
        return ended, self._store.list_pins(scene.id), how, words

    def _record_ended(self, ended: Iterable[_Ended]) -> None:
        """Say each scene's end in the journal and History, with when it ended, once the end has committed."""
        for scene, pins, how, words in ended:
            walls = [pin.wall_id for pin in pins]
            _log_scene(how.event.removeprefix("scene."), scene.id, walls, f"{words} on {self._wall_names(walls)}")
            # When it ended, not when this line is written: a preview noticed
            # after a restart ended at its `until`, while the server was down.
            self._record_scene(EventKind.SCENE_ENDED, scene, pins, how=str(how), ended_at=_iso(scene.ended_at))

    def _record_scene(self, kind: EventKind, scene: Scene, pins: Sequence[ScenePin], **detail: object) -> None:
        """One History line per wall a scene pins, naming the wall's work, with the words it is read by."""
        titles = {
            work_id: answer.title
            for work_id, answer in self._library.playable(sorted({pin.work_id for pin in pins})).items()
            if isinstance(answer, PlayableWork)
        }
        for pin in self._pins_on_held_walls(pins):
            wall = self._store.get_wall(pin.wall_id)
            words: dict[str, object] = {"scene_id": scene.id, **detail, "wall_name": wall.name}
            if pin.work_id in titles:
                words["title"] = titles[pin.work_id]
            self._library.record(ProgrammingAct(kind=kind, wall_id=pin.wall_id, work_id=pin.work_id, detail=words))

    def _settle_scenes(self) -> list[_Ended]:
        """Write down that each preview whose `until` has passed has ended, as of that `until`.

        Nothing about the walls changes: each Player returned to its schedule
        at `until` on its own, and the expired scene left in its feed until the
        next write is contract-valid and ignored. This only makes the store and
        the journal say so.
        """
        now = datetime.now(UTC)
        return [
            self._end(scene, at=scene.until, how=SceneEnding.RAN_OUT, words=f"ran out at {scene.until.isoformat()}")
            for scene in self._store.list_scenes(SceneStatus.LIVE)
            if scene.status_at(now) is SceneStatus.ENDED and scene.until is not None
        ]

    def _pins_on_held_walls(self, pins: Iterable[ScenePin]) -> list[ScenePin]:
        """The pins whose wall the store still holds.

        A wall deleted while a scene was live leaves its pin as the scene's record
        (`delete_wall`), and has left the scene: it is shown nothing, named in no
        new history line, and its feed, removed with it, is not republished.
        Every path that acts on a scene's pins takes them through here, so none
        meets the deleted wall in a way of its own.
        """
        held = {wall.id for wall in self._store.list_walls()}
        return [pin for pin in pins if pin.wall_id in held]

    def _wall_names(self, wall_ids: Iterable[str]) -> str:
        held = {wall.id: wall.name for wall in self._store.list_walls()}
        return ", ".join(repr(held[wall_id]) for wall_id in wall_ids if wall_id in held) or "no wall"

    # -- the manifest ---------------------------------------------------------

    def build_manifest(self, wall_id: str, theme_id: str | None = None) -> ManifestBuild:
        """Evaluate what a theme would put on one wall, without writing anything (`FeedPublisher.build_manifest`)."""
        return self._feeds.build_manifest(wall_id, theme_id)

    def sync(self, wall_id: str) -> ManifestBuild:
        """Rebuild the wall's feed from what is hung on it, and publish it (`FeedPublisher.sync`)."""
        return self._feeds.sync(wall_id)

    # -- what a Player reads and writes --------------------------------------------

    def record_heartbeat(self, wall_id: str, document: dict[str, Any]) -> None:
        """Keep what a Player said about itself, where the health panel already looks; note its screen; roll its horizon.

        Two things ride on the heartbeat because a live wall sends one a minute
        and nothing else does: the screen size a minor 2 Player reports, which
        too-small is judged against, and extending the wall's horizon when
        less than two days of it are left.

        Kept as the wall's heartbeat file (`heartbeat_path`), which is what
        every reader of a wall's report opens. Refused, and nothing written, if
        the health panel could not read it.
        """
        self.get_wall(wall_id)
        problem = heartbeat.problem_with(document)
        if problem is not None:
            raise ServiceError(f"That is not a heartbeat this server can read: {problem}")
        write_atomically(self._settings.heartbeat_path(wall_id), document)
        self._record_showing(wall_id, document)
        self._record_screen(wall_id, document)
        # A live wall's heartbeat is the clock a preview's end is noticed by,
        # as it is for the horizon's roll. Behind a bulkhead, as the showings
        # record is: this is the store's account of what the Player already did,
        # and must never cost the wall its roll.
        try:
            with self._store.transaction():
                ended = self._settle_scenes()
            self._record_ended(ended)
        except Exception:  # prawduct:allow prawduct/broad-except -- expiry bookkeeping never stops a heartbeat
            log.exception(
                "a preview that ran out was not written down as ended",
                extra={"event": "scene.not_settled", "wall_id": wall_id},
            )
        self._feeds.roll_v2(wall_id)

    def _record_showing(self, wall_id: str, document: Mapping[str, Any]) -> None:
        """Keep what a heartbeat says the wall is showing.

        Before the roll, so the feed that vouches for the work is the one the
        Player was showing from.
        """
        at = observations.instant(document[heartbeat.REPORTED_AT_KEY])
        if at is not None:
            self.keep_showing(wall_id, reported_state(dict(document)), at=at)

    def keep_showing(self, wall_id: str, reported: ReportedState, *, at: datetime) -> None:
        """Keep what one report made `at` says the wall's screen is doing (`showings.py`), against the feed it carries now.

        Any source of a reported state feeds the record through here: the
        heartbeat today, and display state reported on change when it arrives.
        **A record that cannot be written is logged, never raised**: the report is
        the Player's, and its heartbeat must not be refused for this server's
        bookkeeping.
        """
        published = self._feeds.published(wall_id)
        # The scene's work too: a wall showing its scene shows a work its feed carries.
        playable = frozenset() if published is None else frozenset(published.carried)
        try:
            with self._store.transaction():
                latest = self._store.latest_showing(wall_id)
                for showing in showings.advance(latest, reported, wall_id=wall_id, at=at, playable=playable):
                    self._store.save_showing(showing)
        # A bulkhead, not a filter: the store translates only a refused row into
        # `StorageError` and a full disk or a held lock into `StorageFault`, and
        # anything else arrives as whatever raised it. Whatever fails here, the
        # heartbeat's later steps still run, and one of them rolls the wall's
        # horizon forward.
        except Exception:  # prawduct:allow prawduct/broad-except -- the shown record never stops a heartbeat
            log.exception(
                "a wall's report was not kept as a showing",
                extra={"event": "showings.not_recorded", "wall_id": wall_id, "reported_at": at.isoformat()},
            )
            return
        stranger = showings.unbelieved_work(reported, playable)
        # Only against a feed that exists, and only for a report that is still
        # news: a wall with nothing published, or a report a later one has
        # superseded, says nothing about what the Player is showing from.
        if stranger is not None and published is not None and not showings.superseded(latest, at):
            log.info(
                "a wall reported a work its feed does not carry, and it was not kept as a showing",
                extra={"event": "showings.not_in_feed", "wall_id": wall_id, "work_id": stranger},
            )

    # -- what each wall has shown ---------------------------------------------

    def last_showing(self, wall_id: str) -> Showing | None:
        """The work this wall showed last and for how long, whatever its screen does now; None if it has shown nothing."""
        self.get_wall(wall_id)
        return self._store.latest_showing(wall_id)

    def last_shown_by_work(self) -> Mapping[str, datetime]:
        """Each work any wall has shown, with the latest report naming it; walls since removed count.

        Ids, opaque to Programming, as `work_ids_on_walls` returns them, for the
        composer to meet with the Library's (`services/works_filter.py`). Read
        from the showings' last sight, so a work up now counts as shown now.
        """
        return self._store.last_shown_by_work()

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
        feed = self._feeds.published(wall_id)
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
        """The Library changed works: take them off walls they can no longer go on, or put them on walls whose theme holds them.

        A newly accepted work is offered its theme too. It joins no feed then,
        since acceptance is what queues its preparation; its master's
        announcement puts it on the wall.

        Subscribed to the Library's announcements. The rules are the ones startup
        applies, narrowed to the works named, so the running server and a
        restarted one cannot disagree. **One reconciliation for the whole
        announcement**: a bulk archive names every work it archived
        (`library/events.py`), so each wall is rebuilt and written once for the
        act. The offer is made once per work, so an acceptance announced for a
        restore offers nothing (`offer_destinations`).
        """
        self.reconcile(event.work_ids, cause=event.change.value)
        if event.change is WorkChange.ACCEPTED:
            self.offer_destinations(event.work_ids)

    def reconcile(self, work_ids: Iterable[str] | None = None, *, cause: str = "startup") -> Reconciliation:
        """Make every published feed agree with what the Library will show (`FeedPublisher.reconcile`)."""
        return self._feeds.reconcile(work_ids, cause=cause)

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

    def _require_showable(self, artwork_id: str) -> PlayableWork:
        """The work, if a wall may be told to show it by hand: displayable, and not kept off every wall.

        Show now and a scene's pin ask the same question, so they refuse in the
        same words.
        """
        answer = self._require_held(artwork_id)
        if not isinstance(answer, PlayableWork):
            raise ServiceError(f"Artwork {artwork_id!r} cannot be shown on the wall: {answer.detail}")
        if any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
            raise ServiceError(f"Artwork {answer.title!r} is kept off every wall. Allow it again from its page first.")
        return answer

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

        Zero is refused rather than treated as "as fast as possible": a Player
        would spin selecting images, and nothing about that reads as a
        setting somebody chose.
        """
        if seconds is not None and seconds <= 0:
            raise ServiceError(f"A rotation interval must be greater than zero seconds, got {seconds}.")
        return seconds


#: How long a preview lasts when nobody says (the owner, 2026-10-08, confirmed 2026-10-26).
PREVIEW_MINUTES: Final[int] = 20

#: The longest preview: a day. Longer is what a hold is for, and a bound keeps
#: an agent's length from overflowing the date arithmetic into a fault.
MAX_PREVIEW_MINUTES: Final[int] = 24 * 60

#: What `_require_scene` says when a scene is not in the state an act needs.
_SCENE_NOT: Final[Mapping[SceneStatus, str]] = {
    SceneStatus.DRAFT: "That scene is {status}, not being assembled, so its walls cannot be changed.",
    SceneStatus.LIVE: "That scene is {status}, not on the walls, so there is nothing to release.",
    SceneStatus.ENDED: "That scene is {status}.",
}

#: How many of the wall's next works Walls shows: "the next three" (`ia-proposal.md`
#: § Walls, ruled 2026-10-07).
UPCOMING: Final[int] = 3

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


def _cannot_show(answer: PlayableWork | Unplayable | None, *, kept_off: bool) -> str | None:
    """Why a scene's wall cannot show its work now, in words, or None when it can."""
    if kept_off:
        return "It is kept off every wall."
    if answer is None:
        return "The Library does not hold it."
    return None if isinstance(answer, PlayableWork) else answer.detail


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def _log_scene(act: str, scene_id: str, wall_ids: Sequence[str], words: str) -> None:
    """Say one act on a scene, naming its walls, under the event `scene.<act>`.

    Every act that changes what a wall stages or shows says so, because a Frame
    uploading or evicting a work nobody hung is otherwise a mystery in the journal.
    """
    log.info("Scene %s: %s.", scene_id, words, extra={"event": f"scene.{act}", "scene_id": scene_id, "wall_ids": list(wall_ids)})
