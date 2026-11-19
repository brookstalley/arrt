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
the slot on the wall now, or a fresh start — lives in `feeds.py`: this service
composes its `FeedPublisher`, and every act here that changes a wall's feed
publishes through it, in the publisher's transaction.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import logging
import uuid
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
from arrt.programming.themes import UNSET, NotAgain, NotAgainScope, ThemeCount, ThemePlacement, Themes, Unset, WorkPlacements
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member, require_text
from arrt.services.store import store_write

#: Every name callers imported from here before the collaborators had modules
#: of their own, re-exported so that none of them changes.
__all__ = [
    "UNSET",
    "DisplayService",
    "DisplaySettings",
    "NotAgain",
    "NotAgainScope",
    "ThemeCount",
    "ThemePlacement",
    "Unset",
    "WorkPlacements",
]

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
        #: Themes, their membership, what hangs where, and the works kept off every wall (`themes.py`).
        self._themes = Themes(store, library, self._feeds)

    # -- reads: themes --------------------------------------------------------

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme."""
        return self._themes.list_themes()

    def get_theme(self, theme_id: str) -> Theme:
        """Return one theme."""
        return self._feeds.get_theme(theme_id)

    def get_listed_theme(self, theme_id: str) -> Theme:
        """A theme a curator can name: any theme but a hung selection."""
        return self._themes.get_listed_theme(theme_id)

    def pace(self, wall: Wall) -> tuple[int, bool]:
        """How long each work stays up on this wall, and whether it plays shuffled (`FeedPublisher.pace`)."""
        return self._feeds.pace(wall)

    def default_theme(self) -> Theme | None:
        """The theme new works join, or None while the curator has marked none."""
        return self._themes.default_theme()

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
        """Every wall showing this theme, in the order walls are listed."""
        return self._themes.walls_hanging(theme_id)

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
        """Every theme with every wall showing it."""
        return self._themes.survey_themes()

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
        """Every theme, by name, with how many of `work_ids` it holds."""
        return self._themes.theme_counts(work_ids, selected=selected)

    def work_ids_on_walls(self) -> frozenset[str]:
        """The ids of every work some wall plays now, through the theme or selection hanging there."""
        return self._themes.work_ids_on_walls()

    def theme_work_ids(self, theme_id: str) -> Sequence[str]:
        """The ids of the theme's works, in curated order."""
        return self._themes.theme_work_ids(theme_id)

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
                self._themes.retire_selection(assignment)
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
        """Record a theme and return it."""
        return self._themes.add_theme(name=name, description=description)

    def make_default(self, theme_id: str) -> Theme:
        """Make this the theme new works join, taking the mark off whichever had it."""
        return self._themes.make_default(theme_id)

    def offer_destinations(self, work_ids: Iterable[str]) -> Sequence[str]:
        """Offer each work the theme it was accepted into, once, and return the ones that joined."""
        return self._themes.offer_destinations(work_ids)

    def catch_up_offers(self) -> Sequence[str]:
        """Offer every accepted work that was never offered the theme it was accepted into. Run at start."""
        return self._themes.catch_up_offers()

    def activate_theme(self, theme_id: str, *, wall_id: str) -> ManifestBuild:
        """Hang this theme on this wall, and publish what follows."""
        return self._themes.activate_theme(theme_id, wall_id=wall_id)

    def hang_selection(self, artwork_ids: Sequence[str], *, wall_id: str) -> ManifestBuild:
        """Hang these works on this wall, until something else is hung there."""
        return self._themes.hang_selection(artwork_ids, wall_id=wall_id)

    # -- writes: not this one again -------------------------------------------

    def not_this_one_again(self, artwork_id: str, *, wall_id: str, scope: NotAgainScope | str) -> NotAgain:
        """The Walls card's *Not this one again*, answered *from this theme* or *from every wall*."""
        return self._themes.not_this_one_again(artwork_id, wall_id=wall_id, scope=scope)

    def leave_theme(self, artwork_id: str, *, wall_id: str) -> Theme:
        """*Not this one again*, from this theme: take the work out of what hangs on this wall."""
        return self._themes.leave_theme(artwork_id, wall_id=wall_id)

    def exclude_work(self, artwork_id: str, *, wall_id: str | None = None) -> WorkExclusion:
        """*Not this one again*, from every wall: keep the work off every wall until it is allowed again."""
        return self._themes.exclude_work(artwork_id, wall_id=wall_id)

    def allow_work(self, artwork_id: str) -> None:
        """Undo *Not this one again* from every wall: the work may go on walls again."""
        self._themes.allow_work(artwork_id)

    def excluded_works(self) -> Sequence[WorkExclusion]:
        """Every work kept off every wall, oldest first."""
        return self._themes.excluded_works()

    def placements_of(self, artwork_id: str) -> WorkPlacements:
        """Every theme holding this work, with the walls hanging each, and whether it is kept off every wall."""
        return self._themes.placements_of(artwork_id)

    def clear_wall(self, wall_id: str) -> None:
        """Take down whatever is hanging, leaving the wall holding nothing."""
        self._themes.clear_wall(wall_id)

    def add_to_theme(self, *, theme_id: str, artwork_id: str, position: int | None = None) -> ThemeMembership:
        """Put a work in a theme, at a place in the order or at the end of it."""
        return self._themes.add_to_theme(theme_id=theme_id, artwork_id=artwork_id, position=position)

    def add_works_to_theme(self, *, theme_id: str, artwork_ids: Sequence[str]) -> tuple[int, int]:
        """Put many works at the end of a theme's order, in the order given, in one transaction."""
        return self._themes.add_works_to_theme(theme_id=theme_id, artwork_ids=artwork_ids)

    def remove_works_from_theme(self, *, theme_id: str, artwork_ids: Sequence[str]) -> Sequence[str]:
        """Take many works out of a theme in one transaction, and answer which left."""
        return self._themes.remove_works_from_theme(theme_id=theme_id, artwork_ids=artwork_ids)

    def move_in_theme(self, *, theme_id: str, artwork_id: str, position: int | None) -> ThemeMembership:
        """Move a work to a place in the curated order, or return it to unplaced."""
        return self._themes.move_in_theme(theme_id=theme_id, artwork_id=artwork_id, position=position)

    def remove_from_theme(self, *, theme_id: str, artwork_id: str) -> None:
        """Take a work out of a theme. The work itself is untouched."""
        self._themes.remove_from_theme(theme_id=theme_id, artwork_id=artwork_id)

    def update_theme(
        self,
        theme_id: str,
        *,
        name: str | None = None,
        description: str | Unset | None = UNSET,
    ) -> Theme:
        """Change a theme's name or description."""
        return self._themes.update_theme(theme_id, name=name, description=description)

    def delete_theme(self, theme_id: str) -> None:
        """Remove a theme and its membership rows. The works themselves are untouched."""
        self._themes.delete_theme(theme_id)

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
        beside it (`FeedPublisher._write_v2`).
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
        answer = self._themes.require_showable(artwork_id)
        with self._feeds.publishing():
            return self._feeds.restart(wall_id, pinned=answer)

    # -- scenes ---------------------------------------------------------------
    #
    # A scene is a work per wall, applied together over each wall's schedule
    # (`player-contract.md` § Scenes). While a draft, each pin stages its work
    # on its wall, so a Frame has its upload done before Apply and the walls
    # switch together. Every act writes the store, then patches each wall it
    # touched: the schedule is republished exactly as it stands, and the one
    # feed writer derives the control layer (`FeedPublisher._publish_feed`). Expiry is
    # observed, not scheduled: a Player returns to its schedule at `until` on
    # its own, so the server keeps no timer.

    def draft_scene(self) -> SceneView:
        """The scene being assembled: the one already started, else a new empty one.

        One draft at a time, because the builder on Walls holds one; the store
        would take more, and only the newest stages anything (`FeedPublisher.current_draft`).
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
        answer = self._themes.require_showable(artwork_id)
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
                    self._themes.require_showable(pin.work_id)
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
