"""Walls and their settings: recorded, renamed, deleted, and how each plays what hangs on it.

`Walls` is each wall as a surface shows it (`WallView`, read at one instant),
the wall's own settings (its mat, its pace, order and shapes), and moving a
wall on by hand (`step_display`, `show_work_now`). `DisplayService`
(`display.py`) composes it and delegates to it; every surface still calls
`services.display`.

What hangs on a wall is the themes' (`themes.py`); a wall's feed is written by
the one `FeedPublisher` the facade built (`feeds.py`).

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Final

from arrt.persistence.records import (
    SceneStatus,
    Showing,
    Theme,
    Wall,
)
from arrt.programming import shape
from arrt.programming.clients import Placements, WallsReading
from arrt.programming.display_state import DisplayState
from arrt.programming.feeds import FeedPublisher, log_published
from arrt.programming.lookups import Clock, IdSource, Lookups, machine_now, new_id
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.v2 import SCHEMA_MAJOR as MANIFEST_MAJOR
from arrt.programming.schedule import Slot
from arrt.programming.settings import DisplaySettings
from arrt.programming.store import ProgrammingStore
from arrt.programming.themes import UNSET, Themes, Unset
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member, require_text
from arrt.services.store import store_write

#: Named for the module these lines were said from before it had a module of its
#: own, and kept, for the reason `feeds.py` gives: a logger's name is what a
#: reader of the journal filters on.
log = logging.getLogger("arrt.programming.display")


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


@dataclass(frozen=True, slots=True)
class WallsSeen:
    """Walls as a surface shows them, and the one reading of reports and placements each view was built from.

    `views[i].display_state` and `views[i].reads_feed` are `reading`'s, so an
    answer that says who shows a wall, its display and its labels from
    `reading.survey` says them of the instant its state was read
    (`WallsReading`).
    """

    views: Sequence[WallView]
    reading: WallsReading


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


#: How many of the wall's next works Walls shows: "the next three" (`ia-proposal.md`
#: § Walls, ruled 2026-10-07).
UPCOMING: Final[int] = 3


class Walls:
    """Read and write the walls, their settings, and what each shows now."""

    def __init__(
        self,
        store: ProgrammingStore,
        settings: DisplaySettings,
        lookups: Lookups,
        feeds: FeedPublisher,
        themes: Themes,
        *,
        now: Clock = machine_now,
        mint_id: IdSource = new_id,
    ) -> None:
        self._store = store
        self._settings = settings
        #: The clock a wall is stamped by and its upcoming slots are counted from (read once an answer), and its ids' source.
        self._now = now
        self._mint_id = mint_id
        self._placements = Placements(store, settings.art_root, now=now)
        #: The facade's one set of lookups (`lookups.py`).
        self._lookups = lookups
        self._feeds = feeds
        self._themes = themes

    # -- reads: walls and what hangs on them -----------------------------------

    def hanging_on(self, wall_id: str) -> Theme | None:
        """The theme hanging on this wall, or None while nothing is.

        None is an ordinary answer, not a fault: an empty catalogue and a curator
        who took everything down both produce it, and `information-architecture.md`
        designs it as one of the Walls screen's named empty states.
        """
        # One scope, so a hang changed between the two reads cannot name a
        # theme deleted meanwhile and refuse a wall that is fine.
        with self._store.reading():
            self._lookups.get_wall(wall_id)
            assignment = self._store.get_assignment(wall_id)
            return None if assignment is None else self._lookups.get_theme(assignment.theme_id)

    def survey_walls(self) -> Sequence[WallView]:
        """Every wall with what hangs on it and what its screen is doing (`read_walls`)."""
        return self.read_walls().views

    def get_wall_view(self, wall_id: str) -> WallView:
        """One wall with what hangs on it and what its screen is doing (`read_walls`)."""
        [view] = self.read_walls(wall_id).views
        return view

    def read_walls(self, wall_id: str | None = None) -> WallsSeen:
        """Every wall, or the one named, each view built from one reading of the reports and placements.

        **One store scope for the rows and one read of each report file.** A
        theme made and hung between the themes' read and the hangs' was a hang
        naming a theme the survey did not hold, and a fault; a wall's state read
        apart from its feed's major, or from who shows it, let one answer say
        two instants (`WallsReading`). The store's scope excludes this process's
        writers for the whole read, so the views, the placements and the walls
        listed are one instant's; each report file is read once, inside it.
        A named wall the catalogue does not hold is refused, as `get_wall` does.
        """
        with self._store.reading():
            if wall_id is not None:
                self._lookups.get_wall(wall_id)
            # One instant for the reports' ages and the slots still to come.
            now = self._now()
            reading = self.read_wall_reports(None if wall_id is None else frozenset({wall_id}), at=now)
            themes = {theme.id: theme for theme in self._store.list_themes()}
            hanging = {assignment.wall_id: assignment.theme_id for assignment in self._store.list_assignments()}
            return WallsSeen(views=[self._view(wall, themes, hanging, reading, now) for wall in reading.walls], reading=reading)

    def read_wall_reports(self, wall_ids: frozenset[str] | None = None, at: datetime | None = None) -> WallsReading:
        """Every wall's report, or those named, and who shows each: one survey and one read of each file, in one store scope.

        **The one way into the walls reading** (`Placements.read_walls`): the
        walls answers, the health answer and a scene's walls all take theirs
        here, so how the reading is taken is decided once. The scope excludes
        this process's writers while the rows and the report files are read,
        and joins a scope its caller already holds. The reports are aged at
        `at`, the instant the caller read, or now by this clock.
        """
        with self._store.reading():
            return self._placements.read_walls(wall_ids, at)

    def _upcoming(self, wall_id: str, now: datetime) -> Sequence[Slot]:
        """The published schedule's next slots, starting after now: the one on the wall now is not among them."""
        published = self._feeds.published(wall_id)
        if published is None:
            return ()
        return tuple(slot for slot in published.slots if slot.start > now)[:UPCOMING]

    def _view(
        self, wall: Wall, themes: Mapping[str, Theme], hanging: Mapping[str, str], reading: WallsReading, now: datetime
    ) -> WallView:
        theme_id = hanging.get(wall.id)
        report = reading.reports[wall.id]
        return WallView(
            wall=wall,
            hanging=None if theme_id is None else themes[theme_id],
            display_state=reading.state_of(wall),
            # Whether the wall's last readable report lists major 2, from the
            # read its state is: None while there is no such report.
            reads_feed=None if report.contents is None else heartbeat.reads_major(report.contents, MANIFEST_MAJOR),
            last_shown=self._store.latest_showing(wall.id),
            upcoming=self._upcoming(wall.id, now),
        )

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
        open a wall it does not show.
        """
        chosen = require_text(name, field="name")
        # The instant is read under the store's lock, so walls added at once are
        # stamped in the order they were written.
        with self._store.transaction():
            wall = Wall(id=self._mint_id(), name=chosen, created_at=self._now())
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
            wall = self._lookups.get_wall(wall_id)
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
            wall = self._lookups.get_wall(wall_id)
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
            # Read here, not in the line below: a theme deleted after the commit
            # failed a delete that had already happened.
            taken_down = None if assignment is None else self._store.get_theme(assignment.theme_id)
        # After the commit, for the reason `ClientService.remove_client` gives:
        # files nothing will read again would otherwise sit under the art root.
        self._settings.manifest_v2_path(wall_id).unlink(missing_ok=True)
        self._settings.heartbeat_path(wall_id).unlink(missing_ok=True)
        log.info(
            "Deleted wall %r (%s)%s.",
            wall.name,
            wall_id,
            f"; took down {taken_down.name!r}" if taken_down else "",
        )
        return wall

    # -- writes: a wall's settings ---------------------------------------------

    def set_mat_mode(self, wall_id: str, mode: MatMode | str | None) -> Wall:
        """Choose how this wall's Player draws the mat, or with None leave it to the Player.

        Republishes the wall's feed with the setting and changes nothing else in
        it: the schedule and every work stay as published.
        """
        chosen = None if mode is None else require_member(mode, enum=MatMode, field="mat mode").value
        # Read where it is written, for the reason `rename_wall` gives.
        with self._feeds.publishing():
            wall = self._lookups.get_wall(wall_id)
            store_write(self._store.update_wall, replace(wall, mat_mode=chosen))
            feed = self._feeds.published(wall_id)
            if feed is not None:
                self._feeds.patch_v2_works(wall_id, feed, {})
            # Inside, so a wall deleted after the commit is not a refusal of a
            # setting that was written.
            written = self._lookups.get_wall(wall_id)
        log.info("Wall %r: the mat is now %s.", wall.name, chosen or "the Player's own choice")
        return written

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
            wall = self._lookups.get_wall(wall_id)
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
            # Inside, as `set_mat_mode` says.
            written = self._lookups.get_wall(wall_id)
        interval, shuffled = self._feeds.pace(chosen)
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
        return written

    # -- writes: what the wall shows now ---------------------------------------

    def step_display(self, wall_id: str) -> str:
        """Move one wall on to the work after the one on it now, and return that work's id.

        A republish of the wall's feed starting now (`player-contract.md` § What
        happens to `show_now` and `next`). One wall's step leaves every other
        wall's picture alone, so a `next` aimed at the living room never moves
        the study; a wall sharing works with it has its slots to come rebuilt
        beside it (`FeedPublisher._write_v2`).
        """
        with self._feeds.publishing():
            self._lookups.get_wall(wall_id)
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
        # Checked inside the act, so a work kept off every wall meanwhile is
        # refused rather than put up.
        with self._feeds.publishing():
            self._lookups.get_wall(wall_id)
            answer = self._themes.require_showable(artwork_id)
            return self._feeds.restart(wall_id, pinned=answer)

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
