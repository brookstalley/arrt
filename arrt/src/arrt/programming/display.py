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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from arrt import observations
from arrt.library.facade import (
    LibraryFacade,
    WorkChange,
    WorkChanged,
)
from arrt.persistence.records import (
    SceneLifetime,
    Showing,
    Theme,
    ThemeMembership,
    Wall,
    WorkExclusion,
)
from arrt.programming import adequacy, showings
from arrt.programming.display_state import ReportedState, reported_state
from arrt.programming.feeds import FeedPublisher, Reconciliation
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.builder import ManifestBuild, write_atomically
from arrt.programming.manifest.heartbeat import HeartbeatReading, heartbeat_path_in
from arrt.programming.manifest.v2 import manifest_v2_path_in
from arrt.programming.scenes import MAX_PREVIEW_MINUTES, PREVIEW_MINUTES, Scenes, SceneView, SceneWall
from arrt.programming.store import ProgrammingStore
from arrt.programming.themes import UNSET, NotAgain, NotAgainScope, ThemeCount, ThemePlacement, Themes, Unset, WorkPlacements
from arrt.programming.walls import (
    DEFAULT_SHUFFLE,
    IN_ORDER,
    PLAYERS_OWN_MAT,
    SHUFFLE_CHOICES,
    SHUFFLED,
    UPCOMING,
    MatMode,
    Walls,
    WallView,
    feed_notice,
)
from arrt.services.errors import ServiceError
from arrt.services.store import store_write

#: Every name callers imported from here before the collaborators had modules
#: of their own, re-exported so that none of them changes.
__all__ = [
    "DEFAULT_SHUFFLE",
    "IN_ORDER",
    "MAX_PREVIEW_MINUTES",
    "PLAYERS_OWN_MAT",
    "PREVIEW_MINUTES",
    "SHUFFLED",
    "SHUFFLE_CHOICES",
    "UNSET",
    "UPCOMING",
    "DisplayService",
    "DisplaySettings",
    "MatMode",
    "NotAgain",
    "NotAgainScope",
    "SceneView",
    "SceneWall",
    "ThemeCount",
    "ThemePlacement",
    "Unset",
    "WallView",
    "WorkPlacements",
    "feed_notice",
]

log = logging.getLogger(__name__)


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


class DisplayService:
    """Read and write the themes, memberships, and feeds the walls run on."""

    def __init__(self, store: ProgrammingStore, library: LibraryFacade, settings: DisplaySettings) -> None:
        self._store = store
        self._library = library
        self._settings = settings
        #: Everything that builds, stages and publishes a wall's feed (`feeds.py`).
        self._feeds = FeedPublisher(store, library, settings)
        #: Themes, their membership, what hangs where, and the works kept off every wall (`themes.py`).
        self._themes = Themes(store, library, self._feeds)
        #: Walls, their settings, and what each shows now (`walls.py`).
        self._walls = Walls(store, settings, self._feeds, self._themes)
        #: Scenes (`scenes.py`).
        self._scenes = Scenes(store, library, settings, self._feeds, self._themes, self._walls)

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
        """The theme hanging on this wall, or None while nothing is."""
        return self._walls.hanging_on(wall_id)

    def walls_hanging(self, theme_id: str) -> Sequence[Wall]:
        """Every wall showing this theme, in the order walls are listed."""
        return self._themes.walls_hanging(theme_id)

    def survey_walls(self) -> Sequence[WallView]:
        """Every wall with what hangs on it and what its screen is doing."""
        return self._walls.survey_walls()

    def get_wall_view(self, wall_id: str) -> WallView:
        """One wall with what hangs on it and what its screen is doing."""
        return self._walls.get_wall_view(wall_id)

    def survey_themes(self) -> Sequence[ThemePlacement]:
        """Every theme with every wall showing it."""
        return self._themes.survey_themes()

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
        """Record a wall."""
        return self._walls.add_wall(name=name)

    def rename_wall(self, wall_id: str, *, name: str) -> Wall:
        """Give a wall a new name; a name another wall has is refused, as at `add_wall`."""
        return self._walls.rename_wall(wall_id, name=name)

    def delete_wall(self, wall_id: str) -> Wall:
        """Forget a wall for good, freeing its screen and its label panels; its history stays."""
        return self._walls.delete_wall(wall_id)

    # -- writes: themes and membership ----------------------------------------

    def set_mat_mode(self, wall_id: str, mode: MatMode | str | None) -> Wall:
        """Choose how this wall's Player draws the mat, or with None leave it to the Player."""
        return self._walls.set_mat_mode(wall_id, mode)

    def set_playback(
        self,
        wall_id: str,
        *,
        rotation_interval_seconds: int | Unset | None = UNSET,
        shuffle: bool | Unset | None = UNSET,
        tallest: str | Unset | None = UNSET,
        widest: str | Unset | None = UNSET,
    ) -> Wall:
        """Choose how this wall plays its theme: how long each work stays up, in what order, and which shapes."""
        return self._walls.set_playback(
            wall_id, rotation_interval_seconds=rotation_interval_seconds, shuffle=shuffle, tallest=tallest, widest=widest
        )

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
        """Move one wall on to the work after the one on it now, and return that work's id."""
        return self._walls.step_display(wall_id)

    def show_work_now(self, wall_id: str, artwork_id: str) -> str:
        """Put this work on the wall now and carry on from there; return its id."""
        return self._walls.show_work_now(wall_id, artwork_id)

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
        """The scene being assembled: the one already started, else a new empty one."""
        return self._scenes.draft_scene()

    def pin_scene(self, scene_id: str, wall_id: str, artwork_id: str) -> SceneView:
        """Put this work on this wall in the draft, replacing the wall's earlier pick, and stage it there."""
        return self._scenes.pin_scene(scene_id, wall_id, artwork_id)

    def unpin_scene(self, scene_id: str, wall_id: str) -> SceneView:
        """Take this wall out of the draft and stop staging its work there."""
        return self._scenes.unpin_scene(scene_id, wall_id)

    def discard_scene(self, scene_id: str) -> None:
        """Forget a draft, and stop staging its works."""
        self._scenes.discard_scene(scene_id)

    def apply_scene(self, scene_id: str, *, lifetime: SceneLifetime | str, minutes: int | None = None) -> SceneView:
        """Show the draft on every wall it pins, now: for `minutes` as a preview, or until released as a hold."""
        return self._scenes.apply_scene(scene_id, lifetime=lifetime, minutes=minutes)

    def release_scene(self, scene_id: str) -> SceneView:
        """End a live scene now; each of its walls returns to its schedule where the schedule is now."""
        return self._scenes.release_scene(scene_id)

    def live_scene(self) -> SceneView | None:
        """The scene on the walls now, or None. A preview whose end has passed is not live, written or not."""
        return self._scenes.live_scene()

    def scene_draft(self) -> SceneView | None:
        """The scene being assembled, or None."""
        return self._scenes.scene_draft()

    def get_scene(self, scene_id: str) -> SceneView:
        """A scene and its pins, with its status as of now."""
        return self._scenes.get_scene(scene_id)

    def scene_walls(self, view: SceneView) -> list[SceneWall]:
        """Each wall a scene pins, with its work and whether its last heartbeat reports the scene."""
        return self._scenes.scene_walls(view)

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
                ended = self._scenes.settle_scenes()
            self._scenes.record_ended(ended)
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
