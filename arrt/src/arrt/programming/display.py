"""What the wall shows: `DisplayService`, the facade every surface calls as `services.display`.

The catalogue answers "what do we hold"; this answers "what is on the wall, in
what order, and what should it do next". They are separated because they change
for different reasons: a work's metadata changes when a curator corrects it, and
a theme changes when a curator changes their mind about an evening.

**`DisplayService` is a composition facade**: it builds one of each
collaborator over one store, and each public method is a one-line delegation to
the collaborator that holds the rule:

- `Lookups` (`lookups.py`): a wall, a theme, what hangs on a wall and the
  draft, found or refused in one set of words, for every collaborator below
  and for the facade's own `get_wall` and `get_theme`.
- `FeedPublisher` (`feeds.py`): each wall's feed, built, staged, published, and
  kept true to the Library. Every collaborator below publishes through this one
  publisher, in its transaction, so one act has one transaction and one set of
  feeds staged.
- `Themes` (`themes.py`): themes and their membership, what hangs on each wall,
  a newly accepted work's offer, and *Not this one again*.
- `Walls` (`walls.py`): walls, their settings, and moving a wall on by hand.
- `Scenes` (`scenes.py`): scenes, from draft to applied, released or run out.
- `Reports` (`reports.py`): what each wall's Player reports about itself, and
  what is answered from it (showings, size judgements).

Each collaborator calls only those above it in that list. The facade itself
keeps one rule, `on_work_changed`, because it composes the publisher's
`reconcile` with the themes' `offer_destinations`. The types and constants the
collaborators define are re-exported here (`__all__`), so no caller changed
when they moved; `DisplaySettings` is one of them (`settings.py`).

**This service depends on the Library and never the reverse**, and only through
`arrt.library.facade`. A theme is a grouping of works, so building one
requires asking about them; nothing about a work requires knowing which themes
hold it. Works are held here as ids, and the facade says whether each can go on a
wall. **The Library tells this service when a work changes**, and this service
decides what that means for a wall: `on_work_changed` takes a work the Library
now refuses off every published feed.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

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
from arrt.programming.clients import WallsReading
from arrt.programming.display_state import ReportedState
from arrt.programming.feeds import FeedPublisher, Reconciliation
from arrt.programming.lookups import Lookups
from arrt.programming.manifest.builder import ManifestBuild
from arrt.programming.reports import (
    SCREEN_MEMORY,
    SCREEN_REFRESH,
    Reports,
    SizeJudgement,
    Unjudged,
    WallHeartbeat,
    describe_wall_status,
    wall_statuses,
)
from arrt.programming.scenes import MAX_PREVIEW_MINUTES, PREVIEW_MINUTES, Scenes, SceneView, SceneWall
from arrt.programming.settings import DisplaySettings
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
    WallsSeen,
    WallView,
    feed_notice,
)

#: Every name callers imported from here before the collaborators had modules
#: of their own, re-exported so that none of them changes.
__all__ = [
    "DEFAULT_SHUFFLE",
    "IN_ORDER",
    "MAX_PREVIEW_MINUTES",
    "PLAYERS_OWN_MAT",
    "PREVIEW_MINUTES",
    "SCREEN_MEMORY",
    "SCREEN_REFRESH",
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
    "SizeJudgement",
    "ThemeCount",
    "ThemePlacement",
    "Unjudged",
    "Unset",
    "WallHeartbeat",
    "WallView",
    "WallsSeen",
    "WorkPlacements",
    "describe_wall_status",
    "feed_notice",
    "wall_statuses",
]


class DisplayService:
    """Read and write the themes, memberships, walls, scenes and feeds the walls run on, through its collaborators."""

    def __init__(self, store: ProgrammingStore, library: LibraryFacade, settings: DisplaySettings) -> None:
        # The store, the Library and the settings are the collaborators'; the
        # facade keeps none of them, since none of its own rules reads one.
        #: Every collaborator's wall, theme, hang and draft lookup, over the one store (`lookups.py`).
        self._lookups = Lookups(store)
        #: Everything that builds, stages and publishes a wall's feed (`feeds.py`).
        self._feeds = FeedPublisher(store, library, settings, self._lookups)
        #: Themes, their membership, what hangs where, and the works kept off every wall (`themes.py`).
        self._themes = Themes(store, library, self._lookups, self._feeds)
        #: Walls, their settings, and what each shows now (`walls.py`).
        self._walls = Walls(store, settings, self._lookups, self._feeds, self._themes)
        #: Scenes (`scenes.py`).
        self._scenes = Scenes(store, library, settings, self._lookups, self._feeds, self._themes, self._walls)
        #: What each wall's Player reports, and what is answered from it (`reports.py`).
        self._reports = Reports(store, settings, self._lookups, self._feeds, self._themes, self._walls, self._scenes)

    # -- reads: themes --------------------------------------------------------

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme."""
        return self._themes.list_themes()

    def get_theme(self, theme_id: str) -> Theme:
        """Return one theme (`Lookups.get_theme`)."""
        return self._lookups.get_theme(theme_id)

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
        """Return one wall (`Lookups.get_wall`)."""
        return self._lookups.get_wall(wall_id)

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

    def read_walls(self, wall_id: str | None = None) -> WallsSeen:
        """Every wall, or the one named, with the one reading of reports and placements its views were built from."""
        return self._walls.read_walls(wall_id)

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

    # -- writes: a wall's settings ---------------------------------------------

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

    # -- writes: themes and membership ----------------------------------------

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
        """Every wall with whatever the display serving it last said."""
        return self._reports.survey_wall_status()

    def read_wall_reports(self) -> WallsReading:
        """Every wall's report, who shows it and every Player's, each file read once (`Walls.read_wall_reports`)."""
        return self._walls.read_wall_reports()

    # -- writes: what the wall shows now ---------------------------------------

    def step_display(self, wall_id: str) -> str:
        """Move one wall on to the work after the one on it now, and return that work's id."""
        return self._walls.step_display(wall_id)

    def show_work_now(self, wall_id: str, artwork_id: str) -> str:
        """Put this work on the wall now and carry on from there; return its id."""
        return self._walls.show_work_now(wall_id, artwork_id)

    # -- scenes (`scenes.py`) ------------------------------------------------

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
        """Keep what a Player said about itself, where the health panel already looks; note its screen; roll its horizon."""
        self._reports.record_heartbeat(wall_id, document)

    def keep_showing(self, wall_id: str, reported: ReportedState, *, at: datetime) -> None:
        """Keep what one report made `at` says the wall's screen is doing (`showings.py`), against the feed it carries now."""
        self._reports.keep_showing(wall_id, reported, at=at)

    # -- what each wall has shown ---------------------------------------------

    def last_showing(self, wall_id: str) -> Showing | None:
        """The work this wall showed last and for how long, whatever its screen does now; None if it has shown nothing."""
        return self._reports.last_showing(wall_id)

    def last_shown_by_work(self) -> Mapping[str, datetime]:
        """Each work any wall has shown, with the latest report naming it; walls since removed count."""
        return self._reports.last_shown_by_work()

    # -- too small for this wall ----------------------------------------------

    def largest_screen(self, wall_id: str) -> tuple[int, int] | None:
        """The largest screen the wall's display reported within `SCREEN_MEMORY`, or None if it reported none."""
        return self._reports.largest_screen(wall_id)

    def judge_sizes(self, wall_id: str) -> SizeJudgement:
        """Which works on the wall's feed are too small for its largest recent screen (`adequacy.py`)."""
        return self._reports.judge_sizes(wall_id)

    def judge_sizes_of(self, wall: Wall) -> SizeJudgement:
        """`judge_sizes` for a wall already read, by the display its row names (`Reports.judge_sizes_of`)."""
        return self._reports.judge_sizes_of(wall)

    def too_small_on(self, wall_id: str) -> frozenset[str]:
        """The works too small for the wall; empty both when all are fine and when none was judged (`judge_sizes`)."""
        return self._reports.too_small_on(wall_id)

    def size_judgements(self, theme_id: str) -> Mapping[str, SizeJudgement]:
        """Each wall hanging the theme, by name, with its judgement."""
        return self._reports.size_judgements(theme_id)

    def too_small_for_walls(self, theme_id: str) -> Mapping[str, Sequence[str]]:
        """For each of the theme's works too small for a wall hanging it, those walls' names, in name order."""
        return self._reports.too_small_for_walls(theme_id)

    def published_manifest_v2(self, wall_id: str) -> bytes | None:
        """The bytes of this wall's feed as last published, or None if nothing has been."""
        return self._reports.published_manifest_v2(wall_id)

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
