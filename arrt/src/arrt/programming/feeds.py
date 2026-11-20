"""Each wall's feed: built, staged, published, and kept true to the Library.

`FeedPublisher` is everything that decides a wall's feed and writes it: the
transaction a feed is decided in and written at the end of (`publishing`), the
manifest a theme makes on a wall (`build_manifest`, `sync`), keeping published
feeds true to what the Library will show (`reconcile`), and the schedule each
feed carries, rebuilt beside every wall it shares a work with (`_write_v2`).
Every act decides its feeds for one instant (`_now`), and no feed is published
over the bound a Player reads (`FEED_MAX_BYTES`, `_publish_feed`).
`DisplayService` (`display.py`) composes it and delegates to it; every surface
still calls `services.display`.

It reads the walls, themes and scenes a feed is built from through the
Programming store, and asks the Library about works only through
`arrt.library.facade`.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import json
import logging
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from arrt import atomic
from arrt.library.facade import LibraryFacade, PlayableWork, Unplayable
from arrt.persistence.records import Scene, ScenePin, SceneStatus, Wall
from arrt.programming import shape
from arrt.programming.lookups import Lookups
from arrt.programming.manifest.builder import Exclusion, KeptOff, ManifestBuild, write_atomically
from arrt.programming.manifest.v2 import Feed, Published, SceneEntry, published_from, work_document
from arrt.programming.manifest.v2 import as_document as as_v2_document
from arrt.programming.manifest.v2 import read_published as read_published_v2
from arrt.programming.schedule import (
    Keep,
    PassView,
    Schedule,
    Start,
    StartFresh,
    movable_walls,
    run_household_pass,
)
from arrt.programming.schedule import build as build_schedule
from arrt.programming.settings import DisplaySettings
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import ServiceError
from arrt.services.store import ActState

#: Named for the module the feed's lines were said from before it had a module
#: of its own, and kept: a logger's name is what a reader of the journal filters
#: on, and the feed's events (`scene.work_dropped`, a wall's published, withdrawn
#: and rolled lines) are read beside the rest of what a wall did.
log = logging.getLogger("arrt.programming.display")


@dataclass(frozen=True, slots=True)
class _Held:
    """A neighbour's feed as a household pass rebuilt it, held until the wall republished is written."""

    wall_id: str
    playlist: tuple[str, str]
    schedule: Schedule
    works: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class _Beside:
    """A wall rebuilt in a household pass beside the wall republished (`schedule.run_household_pass`).

    `view` is what it is built against. It is built from the act's one instant
    (`FeedPublisher._now`), as every wall of the pass is, so every wall of one
    pass is scheduled for one moment however long the pass takes. Its feed is
    not written there: what would be written goes into `held`, and the pass
    writes it once the wall republished has been, so no wall is left scheduled
    round a first slot that was never published.
    """

    view: PassView
    held: list[_Held] = field(default_factory=list)


@dataclass(slots=True)
class _Act:
    """What one publishing act holds while it is open (`FeedPublisher.publishing`)."""

    #: The feeds it has decided, by wall, written as its last step.
    staged: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: The act's one instant, read from the clock the first time the act asks,
    #: which is inside the store's lock: every schedule, step and scene layer
    #: of the act is decided for this moment (`FeedPublisher._now`).
    now: datetime | None = None


@dataclass(slots=True)
class _Household:
    """One household pass beside the wall republished, across its runs (`FeedPublisher._write_v2`).

    A run that a refusal caught out is run again: from the feeds as the act
    had them before the first run (`before`, put back into the act's staged
    feeds), without each neighbour refused after the wall republished was
    built counting it by its slot now alone (`outside`), and with each
    refused neighbour counted by its published slots (`refused`).
    """

    act: _Act
    rebuild_beside: Callable[[str, _Beside], None]
    walls: Mapping[str, Wall]
    #: Every wall's feed as the act had it when the pass began.
    feeds: Mapping[str, Published]
    #: Every wall whose feed shares a work with the wall republished.
    neighbours: Sequence[str]
    #: The works each wall's feed names, the wall republished's to come for it.
    held: Mapping[str, Collection[str]]
    #: The act's staged feeds before the pass, put back before a run again.
    before: Mapping[str, dict[str, Any]]
    #: Each neighbour rebuilt in the current run.
    rebuilt: dict[str, _Held] = field(default_factory=dict)
    #: The neighbours staged in the current run, in the order staged.
    staged: list[str] = field(default_factory=list)
    #: Each neighbour that could not be rebuilt or staged, with why.
    refused: dict[str, ServiceError] = field(default_factory=dict)
    #: Neighbours refused after the wall republished was built counting them by
    #: their slot now alone, left out of the next run so they count as walls
    #: outside the pass, by their whole published schedule.
    outside: set[str] = field(default_factory=set)

    def outside_starts(self, pace: Callable[[str], int]) -> tuple[datetime, ...]:
        """The slot starts of the slowest neighbour left out of the pass, if any, which the wall republished lines up with."""
        if not self.outside:
            return ()
        slowest = max(sorted(self.outside), key=pace)
        return tuple(slot.start for slot in self.feeds[slowest].slots)

    def among(self) -> list[str]:
        """The neighbours this run rebuilds."""
        return [other for other in self.neighbours if other not in self.outside]

    def build_neighbour(self, neighbour: str, view: PassView) -> Schedule | None:
        """`run_household_pass`'s builder of a neighbour: None for one that cannot be rebuilt, or was refused before."""
        if neighbour in self.refused:
            return None
        beside = _Beside(view)
        try:
            self.rebuild_beside(neighbour, beside)
        except ServiceError as error:
            self.refused[neighbour] = error
            return None
        if not beside.held:
            return None
        self.rebuilt[neighbour] = beside.held[-1]
        return self.rebuilt[neighbour].schedule

    def rebuilt_in(self, built: Mapping[str, Schedule]) -> list[str]:
        """The neighbours a run rebuilt, in the order to stage them, with the run's staged list begun afresh."""
        self.staged.clear()
        return [neighbour for neighbour in built if neighbour in self.rebuilt]

    def run_again(self, discounted: Collection[str], *, refused_at_staging: bool) -> bool:
        """Whether a refusal caught this run out; if so, set the next run up.

        Caught out: a neighbour refused that the wall republished counted by its
        slot now alone (`discounted`), or one refused at staging, whose rebuilt
        slots the run was built against.
        """
        caught_out = (set(self.refused) & set(discounted)) - self.outside
        if not caught_out and not refused_at_staging:
            return False
        self.act.staged.clear()
        self.act.staged.update(self.before)
        self.outside |= caught_out
        self.rebuilt.clear()
        return True


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """What one reconciliation found and did, so a caller and a test can read it rather than the journal."""

    #: How many works it asked the Library about.
    asked: int
    #: The ids the Library refused, whether or not any wall was carrying them.
    refused: Sequence[str]
    #: Walls whose published feed was rewritten for the works in question. A wall
    #: sharing a work with one of them has its slots to come rebuilt too
    #: (`_write_v2`), and is not listed for that.
    republished: Sequence[str]
    #: How many walls it looked at: every wall the store holds.
    walls: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.republished)


@dataclass(frozen=True, slots=True)
class _Control:
    """One wall's control layer, as its next feed carries it (`FeedPublisher._control_layer`)."""

    scene: SceneEntry | None
    staging: tuple[str, ...]
    #: The entry of each work the scene or staging names.
    works: Mapping[str, Mapping[str, Any]]


class FeedPublisher:
    """Build, stage and publish each wall's feed, and keep every published feed true to the Library."""

    def __init__(self, store: ProgrammingStore, library: LibraryFacade, settings: DisplaySettings, lookups: Lookups) -> None:
        self._store = store
        self._library = library
        self._settings = settings
        #: The facade's one set of lookups, over the same store (`lookups.py`).
        self._lookups = lookups
        #: The open publishing transaction's feeds, decided by wall and written
        #: as its last step, and its one instant (`publishing`, `_Act`). Seen
        #: only by the act that opened it: any other reads the published file,
        #: which is what Players have.
        self._act: ActState[_Act] = ActState(store)
        #: The size of the feed last refused for each wall for being over the
        #: bound (`_publish_feed`), so a refusal repeated at every heartbeat's
        #: roll or every scheduled reconcile is said once, not each time. A wall
        #: leaves it when a feed of its is next staged. Touched only under the
        #: store's lock, inside an act.
        self._over_bound: dict[str, int] = {}

    # -- the feeds' transaction -----------------------------------------------

    @contextmanager
    def publishing(self) -> Iterator[None]:
        """One store transaction whose feeds are written as its last step, so a feed changes only with what decided it.

        **Every act that publishes a feed runs in one.** A feed is a file beside
        the catalogue, so no transaction holds it; what this gives instead:

        - **A feed is decided in the body and written at its end**, after every
          other statement of the act has run. A later step that raises (a
          selection that cannot be retired, after a hang published the wall)
          rolls the act back with no feed written. Until 2026-11-19 each feed
          was written as it was built, and that step left the walls showing a
          hang the catalogue did not record.
        - **A feed that cannot be written rolls the act back**, as before: the
          write is still inside the transaction, and the catalogue never names
          a theme the wall is not showing (backlog #35).
        - **The feeds of one act change together or not at all**, as far as a
          filesystem allows (`_write_staged`).
        - **Each wall's feed is written once per act**, however many steps
          rebuilt it: a bulk archive that rebuilds a wall for each of fifty
          works writes it once, so its Player re-fetches once.

        What remains is the commit itself failing after the files are renamed
        into place, and startup `reconcile` republishes a feed whose theme is
        not the one hung. The store's lock is held throughout, which is what
        serialises every build of a feed with its write, so no lock of this
        service's own is needed. Nesting joins the outer act; opening one
        inside another kind of transaction is refused by name, since its feeds
        would be written before that transaction decided anything.
        """
        if self._act.current() is not None:
            with self._store.transaction():
                yield
            return
        if self._store.in_transaction():
            raise RuntimeError("A feed is published from a transaction of its own (`publishing`), never inside another.")
        with self._act.opened(_Act()) as act:
            yield
            self._write_staged(act.staged)

    def _now(self) -> datetime:
        """The open act's one instant, or the clock's when no act is open.

        **One reading of the clock per act**, made the first time the act asks,
        under the store's lock. Read twice, two steps of one act can be decided
        for different moments: a step chose the work after the one on the wall
        at one reading and scheduled from a later one, which a slot boundary
        between the two turned into showing the work already up (no move on);
        and each wall's scene layer read its own, so a scene ending between two
        readings was on one wall's feed and off its neighbour's.
        """
        act = self._act.current()
        if act is None:
            return datetime.now(UTC)
        if act.now is None:
            act.now = datetime.now(UTC)
        return act.now

    def published(self, wall_id: str) -> Published | None:
        """The wall's feed as this act has decided it, else as published: what every build reads back."""
        act = self._act.current()
        if act is not None and wall_id in act.staged:
            # Through JSON, so it reads exactly as the file it will be.
            return published_from(json.loads(json.dumps(act.staged[wall_id])), where=f"the feed staged for wall {wall_id}")
        return read_published_v2(self._settings.manifest_v2_path(wall_id))

    def _write_staged(self, staged: Mapping[str, dict[str, Any]]) -> None:
        """Write the feeds an act decided: each beside its feed first, then each into place.

        The first pass is the one that can fail (a full disk, a directory gone
        read-only), and a failure there removes what it wrote and raises, so no
        wall's feed has changed. The second is one rename per wall, within one
        directory, each made durable by `atomic.promote`. The staging name is fixed per wall: every write is made under
        the store's lock, so no two can meet on it.
        """
        ready: list[tuple[Path, Path]] = []
        try:
            for wall_id, document in staged.items():
                path = self._settings.manifest_v2_path(wall_id)
                beside = path.with_name(f".{path.name}.staged")
                write_atomically(beside, document)
                ready.append((beside, path))
        except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; no half-written act is left
            for beside, _ in ready:
                beside.unlink(missing_ok=True)
            raise
        for beside, path in ready:
            # Each staged feed is whole and synced (`write_atomically`); the
            # shared writer's last step renames it and syncs the directory.
            atomic.promote(beside, path)

    # -- what a feed is built from -------------------------------------------

    def pace(self, wall: Wall) -> tuple[int, bool]:
        """How long each work stays up on this wall, and whether it plays shuffled.

        The wall's own setting where it has chosen one, else the deployment's:
        null on either means "the default", never "off". One place, so a build,
        a rebuild and a rolled horizon cannot disagree about how a wall plays.
        """
        return (
            (
                wall.rotation_interval_seconds
                if wall.rotation_interval_seconds is not None
                else self._settings.rotation_interval_seconds
            ),
            wall.shuffle if wall.shuffle is not None else self._settings.shuffle,
        )

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
        wall = self._lookups.get_wall(wall_id)
        theme = self._lookups.get_theme(theme_id) if theme_id is not None else self._lookups.require_hanging(wall)

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
                # Only a playable work is judged by shape. A work the Library
                # refuses is reported for that, because widening the wall's
                # range would not put it on the wall.
                if shape.fits(
                    (answer.master.width, answer.master.height),
                    tallest=wall.min_aspect_ratio,
                    widest=wall.max_aspect_ratio,
                ):
                    entries.append(answer)
                else:
                    exclusions.append(Exclusion.outside_shape(answer, wall))
            else:
                exclusions.append(Exclusion.of(answer))

        interval, shuffle = self.pace(wall)
        return ManifestBuild(
            wall=wall,
            theme=theme,
            entries=entries,
            exclusions=exclusions,
            rotation_interval_seconds=interval,
            shuffle=shuffle,
        )

    def sync(self, wall_id: str) -> ManifestBuild:
        """Rebuild the wall's feed from what is hung on it, and publish it.

        **What is hung, and nothing else.** It takes no theme: a feed of a theme
        the catalogue does not record as hung would put on the wall what the
        catalogue says is not there, with nothing to show the two disagree.
        Hanging is `activate_theme` or `hang_selection`, each of which records
        the hang and then publishes through here in the same transaction, so
        what this reads is the hang it has just written. What a theme would put
        on a wall, without writing, is `build_manifest`.

        Returns what it wrote **and what it left out**. A caller that only
        reports the entry count is describing a theme that may be silently
        half on the wall.

        This writes desired state; it does not command the television. The wall
        converges within its Player's poll interval, and saying anything
        stronger would assert something this server cannot observe.

        **It writes this wall's feed, and another wall's only when the two share
        a work**, so hanging a theme in the study leaves the living room's file
        untouched unless a work could be on both at once. A wall that shares one
        has its slots to come rebuilt beside this one, keeping the work on it
        now (`_write_v2`).
        """
        # Built and written inside one transaction, which is also what serialises
        # every rewrite of a published feed: a step or a reconciliation
        # rewriting it between the build and the write would otherwise be
        # overwritten by a document built before it.
        with self.publishing():
            build = self.build_manifest(wall_id)
            self._sync_v2(build)
        log_published(build)
        return build

    # -- keeping published feeds true to the Library -------------------------

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

        **Run at every start, and on every scheduler pass** (`FeedsJob`,
        `services/container.py`, cause `SCHEDULED`), because an announcement lost
        to a crash between the Library's commit and this handler would otherwise
        leave a wall showing a work the curator withdrew until someone happened
        to hang the theme again, and a feed changed on disk behind the server's
        back (removed, an entry no longer the Library's, another theme's) would
        stay so until the next start. A lost announcement that would have added a work is not
        searched for here: a feed names only what its horizon schedules, so a
        member it does not name may simply not be due, and the next roll, which
        builds the hung theme, carries it (`roll_v2`).
        """
        named = None if work_ids is None else set(work_ids)
        # Whether this is its own act or a step of a person's: what a feed
        # over the bound does to it (`_passed_over_if_too_large`).
        own = self._act.current() is None
        with self.publishing():
            walls = self._store.list_walls()
            feeds = {wall.id: self.published(wall.id) for wall in walls}
            hung = {assignment.wall_id: assignment.theme_id for assignment in self._store.list_assignments()}
            mentioned = {work_id for feed in feeds.values() if feed for work_id in feed.carried}
            asked = mentioned if named is None else mentioned & named
            joining = {
                wall_id: self._held(theme_id, named) - set(had.works if (had := feeds[wall_id]) else ())
                for wall_id, theme_id in hung.items()
            }
            asked |= {work_id for candidates in joining.values() for work_id in candidates}
            # A work a scene pins that the wall's feed lost (archived, or kept off
            # every wall) comes back when the Library or the curator allows it.
            returning = {
                wall.id: {
                    work_id
                    for work_id in self._pinned_work_ids(wall.id)
                    if (named is None or work_id in named) and work_id not in (had.carried if (had := feeds[wall.id]) else {})
                }
                for wall in walls
            }
            asked |= {work_id for candidates in returning.values() for work_id in candidates}
            answers = self._library.playable(sorted(asked))
            refused = {work_id for work_id, answer in answers.items() if not isinstance(answer, PlayableWork)}
            # Each feed read again as its turn comes: an earlier wall's republish
            # may have rebuilt it beside that wall, and the copy read above would
            # write the old schedule back over the new.
            republished: list[str] = []
            for wall in walls:
                with self._passed_over_if_too_large(own=own):
                    if self._reconcile_v2(wall.id, self.published(wall.id), answers, cause=cause):
                        republished.append(wall.id)
            for wall_id, theme_id in hung.items():
                shown = {work_id for work_id in joining[wall_id] if isinstance(answers.get(work_id), PlayableWork)}
                # At a start, a feed of another theme than the one hung too: what
                # a hang leaves when its files were renamed into place and its
                # commit then failed (`publishing`), which no roll would mend
                # until the horizon ran low.
                disowned = named is None and self._of_another_theme(wall_id, theme_id)
                if not (shown or disowned or self._unpublished(wall_id)):
                    continue
                with self._passed_over_if_too_large(own=own):
                    if self._publish_additions(wall_id, theme_id, shown, cause=cause, whole=disowned):
                        republished.append(wall_id)
            kept_off = {exclusion.artwork_id for exclusion in self._store.list_exclusions()}
            for wall_id, candidates in returning.items():
                back = sorted(w for w in candidates if isinstance(answers.get(w), PlayableWork) and w not in kept_off)
                if back and feeds[wall_id] is not None:
                    with self._passed_over_if_too_large(own=own):
                        self.patch_walls([wall_id])
                        republished.append(wall_id)
                        log.info(
                            "Wall %r: %s back in its scene (after %s).",
                            self._lookups.get_wall(wall_id).name,
                            ", ".join(back),
                            cause,
                        )

        result = Reconciliation(
            asked=len(asked),
            refused=tuple(sorted(refused)),
            republished=tuple(dict.fromkeys(republished)),
            walls=len(walls),
        )
        if work_ids is None:
            _say_reconciled(result, {wall.id: wall.name for wall in walls}, cause=cause)
        return result

    @contextmanager
    def _passed_over_if_too_large(self, *, own: bool) -> Iterator[None]:
        """One wall's step of a reconciliation: as its own act, a feed over the bound passes the wall over.

        Inside a person's act (a work joining its theme) the refusal is that
        act's, so the person is told. As its own act (a start, a scheduled
        pass, a Library announcement) it has nobody to tell, so the wall keeps
        the feed it has, said once (`_publish_feed`), and the other walls go on.
        Nothing of the wall's step was staged: a feed is refused before it is.
        """
        if not own:
            yield
            return
        try:
            yield
        except FeedTooLarge:
            return

    def _held(self, theme_id: str, work_ids: set[str] | None) -> set[str]:
        """Which of these works the theme holds; none when none are named, since startup adds by publishing whole."""
        if not work_ids:
            return set()
        return {work_id for work_id in work_ids if self._store.get_membership(theme_id, work_id) is not None}

    def _unpublished(self, wall_id: str) -> bool:
        """Whether the wall has no feed on disk.

        A feed on disk that cannot be read is not unpublished: start-up leaves
        it for the next publish to replace, as reconciliation always has, so a
        bad file cannot stop the server starting. A work joining the wall's theme
        is such a publish, as a hang is.
        """
        act = self._act.current()
        if act is not None and wall_id in act.staged:
            return False
        return not self._settings.manifest_v2_path(wall_id).exists()

    def _of_another_theme(self, wall_id: str, theme_id: str) -> bool:
        """Whether the wall's feed, read as published, carries a theme other than this one."""
        feed = self.published(wall_id)
        return feed is not None and feed.playlist_id != theme_id

    def _publish_additions(
        self, wall_id: str, theme_id: str, work_ids: Iterable[str], *, cause: str, whole: bool = False
    ) -> bool:
        """Republish the hung theme's feed if one of these works joins it, if it has none, or if `whole`. True if it did.

        Built as a hang builds it, and published as re-hanging the same theme
        publishes it: the slot on the wall now is kept. A work joins when the
        build sends it and the feed does not carry it. Only then, because a
        republish reshuffles the slots to come, and only for the works the act
        or the announcement concerns: a feed names only what its horizon
        schedules, so a member it lacks may simply not be due.
        """
        feed = self.published(wall_id)
        build = self.build_manifest(wall_id, theme_id)
        sent = {work.work_id for work in build.entries}
        joining = sorted(set(work_ids) & sent - set(feed.works if feed is not None else ()))
        if feed is not None and not joining and not whole:
            return False
        self._sync_v2(build)
        if joining:
            said = f" with {', '.join(joining)} joining"
        elif feed is None:
            said = ", which had no feed on this wall"
        else:
            said = f" in place of {feed.playlist_name!r}, which its feed carried"
        log.info("Wall %r: published theme %r%s (after %s).", build.wall.name, build.theme.name, said, cause)
        return True

    # -- the feed: the wall's schedule ------------------------------------------
    #
    # Published from every path that changes what a wall shows: a sync
    # (re-hanging the same theme keeps the slot on the wall now; another theme
    # starts fresh), a work joining the hung theme and a wall with a theme
    # hung and no feed (a sync, `_publish_additions`), show now and next (start
    # fresh), a withdrawal or a refusal (keep, unless the work on the wall is
    # the one leaving), a new master or colour (patch, no slot moves), and a
    # heartbeat with under two days of horizon left (a sync of the hung theme,
    # or keep what is carried when nothing is hung). Each reads the wall's published feed back rather than
    # a copy of its own, for the reason `manifest/v2.py` gives.

    def _sync_v2(self, build: ManifestBuild, *, beside: _Beside | None = None) -> None:
        """Publish the wall's feed from a build.

        The same theme as the feed already carries keeps the slot on the wall now
        (re-hanging it is how a curator republishes); another theme starts fresh.
        """
        previous = self.published(build.wall.id)
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
            beside=beside,
        )

    def restart(self, wall_id: str, *, pinned: PlayableWork | None) -> str:
        """Republish the wall's feed starting now, and return the work it starts with.

        With the pinned work, or with the one after the work on the wall now.
        Refused by name when there is nothing to restart, or the work has nothing
        the feed could send: answering "done" while the wall goes on as it was is
        the silence this product exists to avoid.
        """
        wall = self._lookups.get_wall(wall_id)
        previous = self.published(wall_id)
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
        # The work after the one on the wall at the act's instant, which is the
        # instant the schedule below starts from (`_now`).
        first = pinned.work_id if pinned is not None else previous.after(self._now())
        schedule = self._rebuild_v2(wall_id, previous, works=works, start=StartFresh(first))
        return schedule.slots[0].work_id

    def withdraw_v2(self, wall_id: str, refused: set[str], *, cause: str) -> bool:
        """Take these works off the wall's feed, adding none. True if the feed carried any of them.

        The slot on the wall now is kept unless it shows one of them, and then the
        wall starts fresh: `Keep` keeps only a work the rebuild still carries.
        """
        previous = self.published(wall_id)
        if previous is None or not refused & set(previous.carried):
            return False
        if refused & set(previous.works):
            works = {work_id: entry for work_id, entry in previous.works.items() if work_id not in refused}
            self._rebuild_v2(wall_id, previous, works=works, start=Keep())
        else:
            # Only the scene or staging names it: the schedule stands, and the
            # control layer, derived afresh at the write, leaves it out if the
            # walls may no longer show it.
            self.patch_v2_works(wall_id, previous, {})
        # Said for what actually left: a work leaving its theme stays on the
        # wall when a scene pins it, because the control layer puts it back.
        after = self.published(wall_id)
        left = sorted(refused & set(previous.carried) - set(after.carried if after is not None else ()))
        if left:
            log.info("Wall %r: took %s off the feed (after %s).", self._lookups.get_wall(wall_id).name, ", ".join(left), cause)
        return True

    def roll_v2(self, wall_id: str) -> None:
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
        try:
            with self.publishing():
                previous = self.published(wall_id)
                if previous is None or previous.horizon_until - self._now() >= ROLL_WHEN_LEFT:
                    return
                build = self.republish(wall_id, previous)
        except FeedTooLarge:
            # A Player's heartbeat is no place to refuse: the wall keeps the
            # feed it has, which is what a Player does with one over the bound,
            # and the refusal was said once (`_publish_feed`).
            return
        if build is not None:
            # Said, because this is also how a work whose announcement was
            # lost reaches the wall, and how a reorder or a new pace does.
            log.info(
                "Wall %r: rolled its horizon forward from theme %r, %d of %d works.",
                build.wall.name,
                build.theme.name,
                len(build.entries),
                build.considered,
            )

    def _rebuild_v2(
        self,
        wall_id: str,
        previous: Published,
        *,
        works: Mapping[str, Mapping[str, Any]],
        start: Start,
        beside: _Beside | None = None,
    ) -> Schedule:
        """Rebuild a wall's feed from what it carries now: no work arrives that is not already in it.

        A horizon rolled forward or a work withdrawn cycles through the works
        already published, in the theme's order and at the wall's pace. A work joining
        the hung theme arrives by `_publish_additions`, which builds the theme.
        """
        order = self._v2_order(previous.playlist_id, works)
        slot_seconds, shuffle = self.pace(self._lookups.get_wall(wall_id))
        return self._write_v2(
            wall_id,
            playlist=(previous.playlist_id, previous.playlist_name),
            order=order,
            works=works,
            slot_seconds=slot_seconds,
            shuffle=shuffle,
            start=start,
            beside=beside,
        )

    def _v2_order(self, playlist_id: str, works: Mapping[str, Any]) -> list[str]:
        """The cycle: the theme's members the feed carries, in its order.

        A theme deleted since (possible once it hangs nowhere, after `clear_wall`)
        leaves the works the feed carries in id order. The pace is the wall's
        either way (`pace`).
        """
        theme = self._store.get_theme(playlist_id)
        if theme is None:
            return sorted(works)
        members = [membership.artwork_id for membership in self._store.list_memberships(theme.id)]
        return [work_id for work_id in members if work_id in works]

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
        beside: _Beside | None = None,
    ) -> Schedule:
        """Schedule the wall against every other wall's published feed, and publish it.

        `order` is the cycle; any other work in `works` may only finish the slot
        it is in now, or be the one a `StartFresh` names.

        **Every wall whose feed shares a work with this one is rebuilt beside
        it** (the owner, 2026-10-13), as one pass in the order
        `schedule.household_pass` gives: rebuilt one at a time against the
        others' whole schedules, two walls sharing two works lock, each showing
        one of them for a whole horizon (`schedule` module docstring). The pass's
        builds are `schedule.run_household_pass`'s; this says how one wall is
        built. **This wall is written first**, then each neighbour the pass
        rebuilt, each once: a neighbour built before this wall is held until
        this wall's feed is written, so if this wall's build or write fails no
        neighbour has been rewritten round it. A wall rebuilt `beside` another
        is one step of that pass: it is built against the pass's view, handed
        back unwritten, and rebuilds no neighbours of its own.

        **A neighbour that cannot be rebuilt keeps its published feed, and this
        wall is built against that.** One refused while the pass builds it, if
        it was built before this wall (a slower one), is counted by its
        published slots and this wall lines up with them (`run_household_pass`).
        One built after this wall, at its pace or quicker, was counted by its
        slot now alone, as a wall that would step aside; refused, it does not,
        so the pass is run again without it, this wall built against its whole
        published schedule, as a wall outside the pass is. One whose feed cannot
        be staged (`_publish_feed`: over the bound, or its scene's works cannot
        be asked about) is refused in the same way, after this wall was staged,
        so the pass is run again and this wall staged again. Each run reads the
        act's one instant, and nothing reaches a file until the act ends, so a
        second run costs builds, never a second write. Each refusal is said
        once, after the last run.
        """
        now = self._now()
        cycle = [work_id for work_id in order if work_id in works]
        #: The walls that were still to come, and so counted by their slot now
        #: alone, when this wall was last built: the ones a refusal can catch out.
        discounted: set[str] = set()
        #: In a run without a neighbour refused after this wall was built, that
        #: neighbour's published slot starts, which this wall lines up with.
        outside: list[datetime] = []

        def build(view: PassView, start: Start, also: Collection[str]) -> Schedule:
            return build_schedule(
                wall_id=wall_id,
                work_ids=cycle,
                slot_seconds=slot_seconds,
                shuffle=shuffle,
                now=now,
                start=start,
                published=view.published,
                seed=f"{wall_id}:{now.isoformat()}",
                also_showable={*works, *also} - set(cycle),
                movable=view.movable,
                align_to=view.align_to,
            )

        def scheduled(view: PassView, start: Start, also: Collection[str]) -> Schedule:
            if beside is not None:
                return build(view, start, also)
            discounted.clear()
            discounted.update(view.movable)
            schedule = build(view, start, also)
            if not outside or view.align_to:
                return schedule
            # Lined up with the neighbour left out of the pass, as with one
            # refused before this wall (`run_household_pass`): built again
            # keeping its first slot, which runs on to that wall's next boundary,
            # so a slot here does not span two of its slots and meet both of
            # two works the walls share.
            first = schedule.slots[0]
            again = PassView({**view.published, wall_id: (first,)}, view.movable, tuple(outside))
            return build(again, Keep(), {*also, first.work_id})

        if beside is not None:
            schedule = scheduled(beside.view, start, ())
            beside.held.append(_Held(wall_id, playlist, schedule, works))
            return schedule
        household = self._household(wall_id, works, cycle)
        while True:
            outside[:] = household.outside_starts(lambda other: self.pace(household.walls[other])[0])
            built = run_household_pass(
                wall_id,
                household.among(),
                start=start,
                movable=movable_walls(wall_id, household.among(), household.held),
                slot_seconds={
                    wall_id: slot_seconds,
                    **{other: self.pace(household.walls[other])[0] for other in household.among()},
                },
                works=household.held,
                published={other: feed.slots for other, feed in household.feeds.items()},
                build_republished=scheduled,
                build_neighbour=household.build_neighbour,
            )
            schedule = built[wall_id]
            self._publish_feed(wall_id, playlist=playlist, schedule=schedule, works=works)
            refused_at_staging = False
            for neighbour in household.rebuilt_in(built):
                feed = household.rebuilt[neighbour]
                try:
                    self._publish_feed(neighbour, playlist=feed.playlist, schedule=feed.schedule, works=feed.works)
                except ServiceError as error:
                    household.refused[neighbour] = error
                    refused_at_staging = True
                    continue
                household.staged.append(neighbour)
            if not household.run_again(discounted, refused_at_staging=refused_at_staging):
                break
        self._say_pass(household, wall_id, schedule)
        return schedule

    def _household(self, wall_id: str, works: Mapping[str, Any], cycle: Sequence[str]) -> _Household:
        """The household pass that republishes this wall: its neighbours, as the act has their feeds now."""
        act = self._act.current()
        if act is None:
            raise RuntimeError(f"Wall {wall_id}'s feed was built outside `publishing`, where nothing would write it.")
        walls = {wall.id: wall for wall in self._store.list_walls()}
        feeds = {other: current for other in walls if (current := self.published(other)) is not None}
        held: dict[str, Collection[str]] = {other: feed.works.keys() for other, feed in feeds.items()}
        held[wall_id] = cycle
        return _Household(
            act=act,
            rebuild_beside=self._rebuild_beside,
            walls=walls,
            feeds=feeds,
            neighbours=sorted(
                other for other, feed in feeds.items() if other != wall_id and not feed.works.keys().isdisjoint(works)
            ),
            held=held,
            before=dict(act.staged),
        )

    def _say_pass(self, household: _Household, wall_id: str, schedule: Schedule) -> None:
        """Say what a household pass did: each neighbour it could not rebuild, each clash, each neighbour rebuilt."""
        walls = household.walls
        for neighbour, refusal in household.refused.items():
            self._say_not_rebuilt(walls[neighbour], walls[wall_id], refusal)
        self._say_clashes(walls[wall_id], schedule)
        for neighbour in household.staged:
            self._say_clashes(walls[neighbour], household.rebuilt[neighbour].schedule)
            # Said, because a wall's feed changing when nobody touched that wall
            # is otherwise a mystery in the journal.
            log.info(
                "Wall %r: its slots to come were rebuilt beside wall %r, which shares works with it.",
                walls[neighbour].name,
                walls[wall_id].name,
            )

    def _say_clashes(self, wall: Wall, schedule: Schedule) -> None:
        """Name the clashes a schedule kept, if any.

        Named, because a clash is the household rule giving way, and a rule
        that gives way silently is one nobody can tell is still in force.
        """
        if not schedule.clashes:
            return
        shared = sorted({(clash.work_id, clash.other_wall_id) for clash in schedule.clashes})
        log.info(
            "Wall %r shows works another wall shows at the same time, having nothing else to show then: %s.",
            wall.name,
            ", ".join(f"{work_id} (with {other})" for work_id, other in shared),
        )

    @staticmethod
    def _say_not_rebuilt(wall: Wall, republished: Wall, error: ServiceError) -> None:
        """Say that a neighbour keeps the schedule it had.

        The act asked for on the wall republished goes ahead; the neighbour goes
        on with its published feed, as before a pass existed, and the walls
        built after it in the pass are built against that.
        """
        log.warning(
            "Wall %r: its slots to come could not be rebuilt beside wall %r: %s",
            wall.name,
            republished.name,
            error,
        )

    def _rebuild_beside(self, wall_id: str, beside: _Beside) -> None:
        """Rebuild a wall's slots to come in a household pass, keeping the work on it now, into `beside.held`.

        As its roll would: from its hung theme when its feed carries that theme,
        so a theme with more works than one horizon names is not narrowed to the
        ones it named; else from what its feed carries. Never a fresh start, which
        would change the picture on a wall nobody touched. The work on it now
        changes only when that work has left the wall, as at any rebuild.
        """
        feed = self.published(wall_id)
        if feed is None:
            return
        self.republish(wall_id, feed, beside=beside)

    def republish(self, wall_id: str, feed: Published | None, *, beside: _Beside | None = None) -> ManifestBuild | None:
        """Republish a wall keeping the work on it now: from its hung theme, else from what its feed carries.

        Returns the build when it built the theme. From the theme so one with
        more works than a horizon names is not narrowed to those its feed named.
        **A feed not of the hung theme** (its files renamed into place, then the
        hang's commit failed, `publishing`) is put right at the next start or
        scheduled pass (`reconcile`) or by the wall's own roll or setting change, which publish
        the hung theme and so start it fresh; a pass `beside` another wall
        leaves it as it is, since that would change the picture on a wall
        nobody touched.
        """
        assignment = self._store.get_assignment(wall_id)
        carries_it = feed is not None and assignment is not None and feed.playlist_id == assignment.theme_id
        if assignment is not None and (beside is None or carries_it):
            build = self.build_manifest(wall_id, assignment.theme_id)
            self._sync_v2(build, beside=beside)
            return build
        if feed is not None:
            self._rebuild_v2(wall_id, feed, works=dict(feed.works), start=Keep(), beside=beside)
        return None

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
        # Every entry the feed carries, the scene's and staging's included: a
        # pinned work re-rendered or refused changes the wall's feed as a
        # scheduled one does. The control layer is derived afresh at the write
        # (`_control_layer`), so only the schedule's works are passed on.
        for work_id, entry in feed.carried.items():
            answer = answers.get(work_id)
            if answer is None:
                continue
            if not isinstance(answer, PlayableWork):
                gone.add(work_id)
            elif (current := work_document(answer)) != entry:
                fresh[work_id] = current
        if gone & set(feed.works):
            works = {work_id: fresh.get(work_id, entry) for work_id, entry in feed.works.items() if work_id not in gone}
            self._rebuild_v2(wall_id, feed, works=works, start=Keep())
            log.info(
                "Wall %r: took works the Library no longer offers off the feed (%s, after %s).",
                self._lookups.get_wall(wall_id).name,
                ", ".join(sorted(gone)),
                cause,
            )
            return True
        if fresh or gone:
            self.patch_v2_works(wall_id, feed, {work_id: entry for work_id, entry in fresh.items() if work_id in feed.works})
            if fresh:
                log.info(
                    "Wall %r: pointed the feed at the current master or colour of %s (after %s).",
                    self._lookups.get_wall(wall_id).name,
                    ", ".join(sorted(fresh)),
                    cause,
                )
            if gone:
                log.info(
                    "Wall %r: took works the Library no longer offers out of its scene (%s, after %s).",
                    self._lookups.get_wall(wall_id).name,
                    ", ".join(sorted(gone)),
                    cause,
                )
            return True
        return False

    def _feed_settings(self, wall_id: str) -> dict[str, Any]:
        """The wall's presentation settings as its feed carries them: only what the curator chose.

        A key nobody set is absent, so the Player falls to its own default, as a
        channel reader would (`player-contract.md` § Presentation settings).
        """
        wall = self._lookups.get_wall(wall_id)
        return {} if wall.mat_mode is None else {"mat": {"mode": wall.mat_mode}}

    def patch_v2_works(self, wall_id: str, feed: Published, entries: Mapping[str, Mapping[str, Any]]) -> None:
        """Replace these works' entries and the wall's settings in its published feed, and nothing else.

        A re-render, a new mat colour or a new mat mode changes what the Player
        composes, not when: the schedule is republished exactly as it stands,
        through the same builder every other feed goes through.
        """
        schedule = Schedule(feed.horizon_from, feed.horizon_until, feed.slots, ())
        self._publish_feed(
            wall_id,
            playlist=(feed.playlist_id, feed.playlist_name),
            schedule=schedule,
            works={**feed.works, **entries},
        )

    def _publish_feed(
        self,
        wall_id: str,
        *,
        playlist: tuple[str, str],
        schedule: Schedule,
        works: Mapping[str, Mapping[str, Any]],
    ) -> None:
        """Spell the wall's feed and stage it for the act's end (`publishing`): the one place a wall's feed is decided.

        **Everything the store decides about the wall is added here**, not by
        each caller: its settings, and its control layer, the scene it shows and
        the works it stages. A scene missing from any one publish path (a roll,
        a withdrawal, a mat patch, a neighbour's rebuild) would take a live scene
        off a wall mid-preview, so no path is trusted to carry one. The schedule
        is the caller's, read back from the published document because its
        stability rule needs the one before; the control layer needs no such
        thing, and is never read back.

        **A feed over `FEED_MAX_BYTES` is not staged** (`FeedTooLarge`): a
        Player may stop reading past the bound and keep what it has, so a feed
        over it is one no Player would take. The wall keeps the feed it has;
        the act asked for on it is refused whole, and a neighbour rebuilt
        beside it keeps its feed as one that cannot be rebuilt does
        (`_write_v2`). Said once per wall, with the event `feed.over_bound`,
        until a feed of that wall is staged again.
        """
        control = self._control_layer(wall_id)
        feed = Feed(
            playlist_id=playlist[0],
            playlist_name=playlist[1],
            schedule=schedule,
            works={**control.works, **works},
            settings=self._feed_settings(wall_id),
            scene=control.scene,
            staging=control.staging,
        )
        act = self._act.current()
        if act is None:
            raise RuntimeError(f"Wall {wall_id}'s feed was published outside `publishing`, where nothing would write it.")
        document = as_v2_document(feed)
        size = served_size(document)
        if size > FEED_MAX_BYTES:
            raise self._over_the_bound(wall_id, size)
        self._over_bound.pop(wall_id, None)
        act.staged[wall_id] = document

    def _over_the_bound(self, wall_id: str, size: int) -> FeedTooLarge:
        """The refusal of a feed over the bound, said once for the wall (`_publish_feed`)."""
        wall = self._lookups.get_wall(wall_id)
        if wall_id not in self._over_bound:
            log.warning(
                "Wall %r: its feed would be %d bytes, over the %d a Player reads, so it was not published; "
                "the wall keeps the feed it has.",
                wall.name,
                size,
                FEED_MAX_BYTES,
                extra={"event": "feed.over_bound", "wall_id": wall_id, "bytes": size, "max_bytes": FEED_MAX_BYTES},
            )
        self._over_bound[wall_id] = size
        return FeedTooLarge(wall.name, size)

    def _control_layer(self, wall_id: str) -> _Control:
        """The scene this wall shows now and the works a draft stages on it, with their entries.

        **A pinned work the Library refuses now, or one kept off every wall, is
        left out and said**: the pin was checked when it was made, but a work can
        be archived or kept off while a scene is live, and a feed naming a work
        it cannot carry is one the Player refuses whole. The wall then shows its
        schedule, which is what it would show with no scene.
        """
        now = self._now()
        pinned, staged = self._control_pins(wall_id, now)
        if pinned is None and not staged:
            return _Control(scene=None, staging=(), works={})
        wanted = sorted(set(staged) | ({pinned[1].work_id} if pinned else set()))
        answers = self._library.playable(wanted)
        kept_off = {exclusion.artwork_id for exclusion in self._store.list_exclusions()}
        works = {
            work_id: work_document(answer)
            for work_id, answer in answers.items()
            if isinstance(answer, PlayableWork) and work_id not in kept_off
        }
        dropped = sorted(set(wanted) - set(works))
        if dropped:
            log.warning(
                "Wall %r: its scene names works it can no longer show (%s); the wall shows its schedule in their place.",
                self._lookups.get_wall(wall_id).name,
                ", ".join(dropped),
                extra={"event": "scene.work_dropped", "wall_id": wall_id, "work_ids": dropped},
            )
        scene = None
        if pinned is not None and pinned[1].work_id in works:
            applied, pin = pinned
            scene = SceneEntry(id=applied.id, work_id=pin.work_id, starts_at=applied.starts_at or now, until=applied.until)
        staging = tuple(dict.fromkeys(work_id for work_id in staged if work_id in works))
        return _Control(scene=scene, staging=staging, works=works)

    def _control_pins(self, wall_id: str, now: datetime) -> tuple[tuple[Scene, ScenePin] | None, list[str]]:
        """The live scene's pin on this wall, if any, and the works the current draft stages on it."""
        live: list[tuple[Scene, ScenePin]] = []
        for scene in self._store.list_scenes(SceneStatus.LIVE):
            if scene.status_at(now) is SceneStatus.LIVE:
                live.extend((scene, pin) for pin in self._store.list_pins(scene.id) if pin.wall_id == wall_id)
        draft = self._lookups.current_draft()
        staged = [] if draft is None else [pin.work_id for pin in self._store.list_pins(draft.id) if pin.wall_id == wall_id]
        if len(live) > 1:
            # Apply ends every other live scene, so this is a store written by
            # something else; the latest applied wins, as it would on the wall.
            log.warning(
                "Wall %r is pinned by %d live scenes; its feed carries the one applied last.",
                self._lookups.get_wall(wall_id).name,
                len(live),
            )
        return (max(live, key=lambda found: applied_at(found[0])) if live else None), staged

    def _pinned_work_ids(self, wall_id: str) -> set[str]:
        """Every work a scene pins or stages on this wall now, whether or not the wall can show it."""
        pinned, staged = self._control_pins(wall_id, self._now())
        return set(staged) | ({pinned[1].work_id} if pinned is not None else set())

    # -- republishing a feed as it stands, and taking a work off ---------------

    def patch_walls(self, wall_ids: Iterable[str]) -> None:
        """Republish each wall's feed as it stands, so it carries the control layer as the store now says.

        A wall the store no longer holds is passed over: it was deleted, and its
        feed with it.
        """
        held = {wall.id for wall in self._store.list_walls()}
        for wall_id in dict.fromkeys(wall_id for wall_id in wall_ids if wall_id in held):
            feed = self.published(wall_id)
            if feed is None:
                # A wall with no feed has nothing to show a scene over, and a pin
                # to one is refused; this is a feed removed since.
                log.warning("Wall %s has no feed, so its part in a scene is not published.", wall_id)
                continue
            self.patch_v2_works(wall_id, feed, {})

    def withdraw(self, artwork_id: str, wall_ids: Iterable[str], *, cause: str) -> None:
        """Take one work off these walls' published feeds, adding nothing.

        The patch reconciliation applies, narrowed to one work and to the walls
        named.
        """
        for wall_id in wall_ids:
            self.withdraw_v2(wall_id, {artwork_id}, cause=cause)


#: The largest feed this server publishes, in bytes of the file a Player is
#: sent: `contract/transport.json`'s `max_bytes` for the `manifest_major` route,
#: quoted because the server cannot read the contract package at run time (it
#: is a dev dependency, and the image's app stage installs none), and held to
#: the package by `tests/unit/test_feed_publisher.py`.
FEED_MAX_BYTES: Final[int] = 16_777_216


def served_size(document: Mapping[str, Any]) -> int:
    """How many bytes this feed is as its file, which is what a Player is sent.

    Spelled as `manifest.builder.write_atomically` writes it (two-space
    indents, UTF-8, a closing newline); a test holds the two to one length.
    """
    return len(json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")) + 1


class FeedTooLarge(ServiceError):
    """A wall's feed would be over `FEED_MAX_BYTES`, so it was not published and the wall keeps the one it has."""

    def __init__(self, wall_name: str, size: int) -> None:
        super().__init__(
            f"The feed for {wall_name!r} would be {size:,} bytes, past the {FEED_MAX_BYTES:,} a Player reads, "
            "so nothing was changed and the wall keeps the feed it has. A longer rotation interval on the wall "
            "makes its feed smaller."
        )
        self.size = size


#: When a wall's published horizon has less than this left, its next heartbeat
#: republishes it. Two of the horizon's three days: a server that comes back after
#: a day away still finds a day in hand on every wall, and a live wall, which
#: reports every few seconds, is extended about once a day.
ROLL_WHEN_LEFT: Final[timedelta] = timedelta(days=2)


#: The cause a scheduled reconciliation names in its lines, as a start names
#: "startup" and an announcement the change it announced.
SCHEDULED: Final[str] = "the scheduled check"


def _say_reconciled(result: Reconciliation, names: Mapping[str, str], *, cause: str) -> None:
    """Say what a reconciliation of every wall did: what it corrected, with the event `feeds.reconciled`.

    A start says so when there was nothing to change, as it always has; a
    scheduled pass that changed nothing says nothing here, since the
    scheduler's own `scheduler.pass` line is its line on every pass.
    """
    if result.changed:
        log.info(
            "Reconciled %d walls against the Library (after %s): republished %s.",
            result.walls,
            cause,
            ", ".join(repr(names.get(wall_id, wall_id)) for wall_id in result.republished),
            extra={
                "event": "feeds.reconciled",
                "cause": cause,
                "walls": result.walls,
                "republished": list(result.republished),
                "refused": list(result.refused),
            },
        )
    elif cause == "startup":
        log.info("Reconciled %d walls against the Library at startup: nothing to change.", result.walls)


def applied_at(scene: Scene) -> datetime:
    """What decides which of several live scenes a wall shows: the one applied last."""
    return scene.starts_at or scene.created_at


def log_published(build: ManifestBuild) -> None:
    """Say what a published build put on its wall, and what it left off and why.

    WARNING when a work is left off for a reason the curator did not choose, or
    when nothing reached the wall: a theme quietly showing fewer works than it
    holds is this product's characteristic failure, and a dark wall is the
    loudest form of it. A work the curator kept off, by hand or by the wall's
    shapes, is the curator's choice and logged at INFO, so a wall narrowed on
    purpose does not warn on every sync.
    """
    unchosen = [exclusion for exclusion in build.exclusions if not isinstance(exclusion.reason, KeptOff)]
    level = logging.WARNING if unchosen or (build.considered and not build.entries) else logging.INFO
    log.log(level, "Published the feed for wall %r showing theme %r: %s", build.wall.name, build.theme.name, build.summarise())
