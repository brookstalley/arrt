"""What each wall's Player says about itself: heartbeats, what each wall has shown, and size judgements.

`Reports` keeps a Player's heartbeat and what rides on it (the work shown, the
screen reported, a preview noticed as run out, the horizon's roll), and answers
from those reports: each wall's status, its last showing, and which works are
too small for its screen. `DisplayService` (`display.py`) composes it and
delegates to it; every surface still calls `services.display`.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from arrt import observations
from arrt.persistence.records import (
    Showing,
    Wall,
)
from arrt.programming import adequacy, showings
from arrt.programming.display_state import ReportedState, reported_state
from arrt.programming.feeds import FeedPublisher
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.builder import write_atomically
from arrt.programming.manifest.heartbeat import HeartbeatReading
from arrt.programming.scenes import Scenes
from arrt.programming.store import ProgrammingStore
from arrt.programming.themes import Themes
from arrt.services.errors import ServiceError
from arrt.services.store import store_write

if TYPE_CHECKING:
    # Only for the annotation: `display.py` builds this class, so a runtime
    # import back would be a cycle.
    from arrt.programming.display import DisplaySettings

#: Named for the module these lines were said from before it had a module of its
#: own, and kept, for the reason `feeds.py` gives: a logger's name is what a
#: reader of the journal filters on.
log = logging.getLogger("arrt.programming.display")


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


class Reports:
    """Keep what each wall's Player reports, and answer from it."""

    def __init__(
        self, store: ProgrammingStore, settings: DisplaySettings, feeds: FeedPublisher, themes: Themes, scenes: Scenes
    ) -> None:
        self._store = store
        self._settings = settings
        self._feeds = feeds
        self._themes = themes
        self._scenes = scenes

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
        self._feeds.get_wall(wall_id)
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
        self._feeds.get_wall(wall_id)
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
        wall = self._feeds.get_wall(wall_id)
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
        if self._feeds.get_wall(wall_id).display_id is None:
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
        return {wall.name: self.judge_sizes(wall.id) for wall in self._themes.walls_hanging(theme_id)}

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
        wall = self._feeds.get_wall(wall_id)
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
        self._feeds.get_wall(wall_id)
        try:
            return self._settings.manifest_v2_path(wall_id).read_bytes()
        except FileNotFoundError:
            return None
