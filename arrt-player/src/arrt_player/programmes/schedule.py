"""Major 2's programme: show what the feed's schedule says, now.

A schedule is state, not a command (`player-contract.md` § What happens to
`show_now` and `next`): nothing here counts directives or keeps a place in a
list. Each pass asks what the feed says to show at this instant, and changes the
wall only when that differs from what this wall last put there. So a restart, a
republished feed and an hour off the network all come to the same thing: the
wall shows what the schedule says, as soon as the display lets it.

**What to show** (`what_to_show`) is `player-contract.md` § Time and § Scenes,
held to `contract/vectors/schedule.json` by this plane's suite:

* an active scene wins, at its own absolute times, and is never moved;
* otherwise the instant is moved into the horizon by whole horizons — forward
  past its end, back before its start — and the slot covering it is shown, so a
  wall cut off from the server keeps its household's hours;
* a time no slot covers is dark. **Until power control exists the wall keeps
  the last work it showed** (§ Time): the gap still means dark, and this Player
  cannot yet act on it.

**The art-mode gate is asked here, in the same order the rotation asks it**:
the display's own wait first, which costs nothing, and only then whether the
wall is ours, which on a Frame is a request to the set. A display that is not
ours is left alone and asked again when its wait allows.

**What goes up is a composed picture, never the master** (`compose.py`). Each
work the feed names is composed for the display's geometry and the feed's mat
mode, in a thread, one at a time, and before its slot where the cache allows:
a compose takes seconds on a Pi, and the loop must keep polling, beating and
watching the set meanwhile (`nonfunctional-requirements.md` § Performance). A
work whose picture is not composed yet is passed over for this pass, as a work
whose media is not cached is. Its file is named by its composition key, so a
display can learn what to prepare before the file exists.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from arrt_player.compose import Geometry, Uncomposable, compose, composed_path, mat_mode
from arrt_player.episodes import ReportOnce
from arrt_player.logs import work_context
from arrt_player.manifest import Feed
from arrt_player.programmes.memory import Memory
from arrt_player.wall import Clock, Display, Picture, Shown

log = logging.getLogger(__name__)

#: How long a work the display could not show is left before it is tried again.
#: The Frame refuses a picture whose upload failed, and without a wait that is a
#: question to the set every pass for as long as the slot lasts; a minute keeps
#: the wall within a minute of recovering at a cost of one request.
RETRY_SECONDS: Final[float] = 60.0

#: How long a work whose picture could not be written (a full disk, a directory
#: with the wrong owner) is left before it is composed again. A master that
#: cannot be decoded is not retried until the feed changes, because the bytes
#: are verified against their hash and the same bytes decode the same way.
COMPOSE_RETRY_SECONDS: Final[float] = 300.0

#: What `compose.compose` is to this programme; a test passes one it controls.
Composer = Callable[..., Path]


@dataclass(frozen=True)
class _Planned:
    """One work as this wall will draw it: its master and the file it composes to."""

    work_id: str
    master: Path
    sha256: str
    mat_color: object
    composed: Path


@dataclass(frozen=True)
class Showing:
    """What a feed says to show at one instant: a work, or dark, and the scene it is part of."""

    work_id: str | None
    scene_id: str | None


def what_to_show(feed: Feed, now: datetime) -> Showing:
    """The work `feed` says to show at `now`, or dark. Every span is half-open."""
    scene = feed.scene
    if scene is not None and scene.start <= now and (scene.until is None or now < scene.until):
        return Showing(work_id=scene.work_id, scene_id=scene.scene_id)
    span = feed.horizon_until - feed.horizon_start
    moved = feed.horizon_start + (now - feed.horizon_start) % span
    for slot in feed.slots:
        if slot.start <= moved < slot.until:
            return Showing(work_id=slot.work_id, scene_id=None)
    return Showing(work_id=None, scene_id=None)


class Schedule:
    """Major 2's programme for one wall."""

    def __init__(
        self,
        *,
        wall_id: str,
        render_root: Path,
        composed_root: Path,
        geometry: Callable[[], Geometry | None],
        memory: Memory,
        clock: Clock,
        composer: Composer = compose,
    ) -> None:
        self._wall_id = wall_id
        self._render_root = render_root
        self._composed_root = composed_root
        #: Asked on every pass, because a screen's mode can change under a
        #: running wall; None while the display has no screen to compose for.
        self._geometry = geometry
        self._memory = memory
        self._clock = clock
        self._composer = composer
        self._feed: Feed | None = None
        #: The composition running in its thread, and the file it is writing.
        self._composing: tuple[asyncio.Task[Path], _Planned] | None = None
        #: Composed files that failed: when, and whether a retry can help.
        self._failed: dict[Path, tuple[float, bool]] = {}
        #: Whether the composed directory owes a tidy, and the geometry it was last
        #: tidied for: a new feed or a new geometry owes one, done between
        #: compositions.
        self._tidy_owed = True
        self._tidied_for: Geometry | None = None
        #: A composed directory that cannot be read or emptied is said once.
        self._tidy_failed = ReportOnce()
        #: The scene the wall is showing, for the heartbeat.
        self._scene_id: str | None = None
        #: Works whose media is not in the cache, said once per feed.
        self._missing: set[str] = set()
        #: The work the display last could not show, and when.
        self._refused: tuple[str, float] | None = None
        #: The file this programme last put on the wall. **The work's id alone is
        #: not enough**: a wall moved here from major 1 holds that work's
        #: composed render, not its master, and a feed may give a work new
        #: media under the same id. None until this programme has shown anything,
        #: so the first pass after a restart or a switch shows the slot's work even
        #: when the wall's memory already names it — on the Frame an idempotent
        #: re-selection of a picture it holds, on a screen the draw a restart owes.
        self._shown_path: Path | None = None

    @property
    def pictures(self) -> Sequence[Picture]:
        """Every work the feed names, staged ones included, as the files they compose to, so a display can prepare them ahead.

        None while the display has no geometry: there is nothing it could be
        prepared to show.
        """
        if self._feed is None or self._geometry() is None:
            return ()
        return tuple(self._picture(work_id) for work_id in self._feed.named())

    @property
    def current_work_id(self) -> str | None:
        return self._memory.last_selected_work_id

    @property
    def scene_id(self) -> str | None:
        """The scene the wall is showing, or None."""
        return self._scene_id

    def adopt(self, feed: Feed) -> None:
        self._feed = feed
        self._missing.clear()
        # A new feed is news: a work refused under the old one gets its chance,
        # and so does a master that would not decode, whose bytes may be new.
        self._refused = None
        self._failed.clear()
        self._tidy_owed = True

    def entered(self) -> None:
        """The wall has just switched to this programme from another major.

        **What this programme last put up is no longer what is on the wall**:
        the other major's programme has shown its own picture since, perhaps of
        the same work. So the next pass shows the slot's work even when the
        wall's memory already names it.
        """
        self._shown_path = None

    async def step(self, display: Display) -> None:
        feed = self._feed
        if feed is None:
            return
        target = what_to_show(feed, self._clock.now())
        self._compose_next(first=target.work_id)
        if target.scene_id is None:
            # No scene is active, whatever is still on the wall: a scene names a
            # live override, and once it has ended there is none — into a gap, or
            # into a slot whose work cannot be shown yet. A scene that is active
            # is reported only once its work is up.
            self._scene_id = None
        if target.work_id is None or self._geometry() is None:
            # A gap, or no screen to compose for. The wall keeps what it has
            # until power control can act on a gap.
            return
        picture = self._picture(target.work_id)
        if target.work_id == self._memory.last_selected_work_id and picture.path == self._shown_path:
            self._scene_id = target.scene_id
            return

        with work_context(target.work_id):
            if not self._ready(picture) or not display.may_attempt() or not await display.is_ours():
                return
            outcome = await display.show(picture)

        if outcome is Shown.YES:
            self._memory.set_last_selected_work_id(target.work_id)
            replaced, self._shown_path = self._shown_path, picture.path
            if replaced is not None and replaced != picture.path:
                # Kept by the tidy while it was up; now nothing is showing it.
                self._remove_unwanted([replaced])
            self._scene_id = target.scene_id
            self._refused = None
        elif outcome is Shown.SKIP:
            self._refused = (target.work_id, self._clock.monotonic())

    async def settle(self) -> None:
        """Compose every work that can be composed now, waiting for each.

        The loop never calls this: it composes one work in the background and
        moves on. It is for a caller that must see the compositions finished,
        which is what a test of the wall's behaviour around them needs.

        **Each file is composed at most once per call**, so a fault that leaves
        a work owed after its composition finished ends the wait rather than
        repeating it for ever.
        """
        attempted: set[Path] = set()
        while True:
            self._compose_next(first=None, skip=attempted)
            if self._composing is None:
                return
            attempted.add(self._composing[1].composed)
            await asyncio.wait({self._composing[0]})

    def _ready(self, picture: Picture) -> bool:
        """Whether this work can be offered to the display: media cached, picture composed, and not just refused."""
        planned = self._plan(picture.work_id)
        if planned is None:
            return False
        if not planned.master.is_file():
            if picture.work_id not in self._missing:
                self._missing.add(picture.work_id)
                log.warning(
                    "cannot show %s yet: its media is not at %s",
                    picture.work_id,
                    planned.master,
                    extra={"event": "schedule.media_missing", "wall_id": self._wall_id, "render_path": str(planned.master)},
                )
            return False
        if not picture.path.is_file():
            # Composing, or queued to be, or failed and said so once already.
            return False
        refused = self._refused
        return refused is None or refused[0] != picture.work_id or self._clock.monotonic() - refused[1] >= RETRY_SECONDS

    def _picture(self, work_id: str) -> Picture:
        assert self._feed is not None  # noqa: S101 -- called only with a feed adopted
        planned = self._plan(work_id)
        assert planned is not None  # noqa: S101 -- called only with a geometry to compose for
        return Picture(
            work_id=work_id,
            path=planned.composed,
            title=self._feed.works[work_id].label.get("title") or work_id,
            theme_id=self._feed.playlist_id,
        )

    def _plan(self, work_id: str) -> _Planned | None:
        """Where a work's master is, and the file it composes to on this display now; None with no screen."""
        assert self._feed is not None  # noqa: S101 -- called only with a feed adopted
        geometry = self._geometry()
        if geometry is None:
            return None
        work = self._feed.works[work_id]
        return _Planned(
            work_id=work_id,
            master=self._render_root / work.media_path,
            sha256=work.sha256,
            mat_color=work.mat_color,
            composed=composed_path(
                self._composed_root,
                master_sha256=work.sha256,
                mat_color=work.mat_color,
                mode=self._mode(),
                geometry=geometry,
            ),
        )

    def _mode(self) -> str:
        """The feed's mat mode, or the Player's default for one it does not set or this Player does not know."""
        assert self._feed is not None  # noqa: S101 -- called only with a feed adopted
        mat = self._feed.settings.get("mat")
        return mat_mode(mat.get("mode") if isinstance(mat, dict) else None)

    # -- composing -------------------------------------------------------------

    def _compose_next(self, *, first: str | None, skip: set[Path] | frozenset[Path] = frozenset()) -> None:
        """Collect a finished composition, and start the next one owed, `first` ahead of the rest.

        Never waits: a composition runs in a thread, and the loop finds it
        finished on a later pass.
        """
        if self._composing is not None:
            task, planned = self._composing
            if not task.done():
                return
            self._composing = None
            self._collect(task, planned)
        feed, geometry = self._feed, self._geometry()
        if feed is None or geometry is None:
            return
        if self._tidy_owed or self._tidied_for != geometry:
            self._tidy()
            self._tidy_owed, self._tidied_for = False, geometry
        order = ([first] if first is not None else []) + [work_id for work_id in feed.named() if work_id != first]
        for work_id in order:
            planned = self._plan(work_id)
            if planned is None or planned.composed in skip or not self._owed(planned):
                continue
            task = asyncio.create_task(
                asyncio.to_thread(
                    self._composer,
                    planned.master,
                    master_sha256=planned.sha256,
                    mat_color=planned.mat_color,
                    mode=self._mode(),
                    geometry=geometry,
                    directory=self._composed_root,
                ),
                name=f"compose:{self._wall_id}:{work_id}",
            )
            self._composing = (task, planned)
            return

    def _owed(self, planned: _Planned) -> bool:
        """Whether this work still needs composing: its master is here, its picture is not, and it has not just failed."""
        if planned.composed.is_file() or not planned.master.is_file():
            return False
        failed = self._failed.get(planned.composed)
        if failed is None:
            return True
        at, retryable = failed
        return retryable and self._clock.monotonic() - at >= COMPOSE_RETRY_SECONDS

    def _collect(self, task: asyncio.Task[Path], planned: _Planned) -> None:
        """Read a finished composition. A failure costs its work, never the wall, and is said once."""
        exc = task.exception()
        if exc is None:
            return
        retryable = isinstance(exc, OSError)
        first_time = planned.composed not in self._failed
        self._failed[planned.composed] = (self._clock.monotonic(), retryable)
        if not first_time:
            return
        if isinstance(exc, Uncomposable):
            reason, event = str(exc), "schedule.uncomposable"
        elif retryable:
            reason, event = f"its picture could not be written ({exc})", "schedule.compose_write_failed"
        else:
            reason, event = f"composing it failed ({exc!r})", "schedule.compose_failed"
        log.warning(
            "cannot show %s: %s",
            planned.work_id,
            reason,
            extra={"event": event, "wall_id": self._wall_id, "render_path": str(planned.master)},
        )

    def _tidy(self) -> None:
        """Remove composed files no work of this feed composes to on this display, and any half-written one.

        Run only between compositions, so a file being written is never taken.
        **The picture on the wall is kept until another replaces it**: a screen
        redraws it when its mode changes, and in a gap nothing replaces it at
        all, so taking it would blank the wall the rule says keeps its work.
        """
        try:
            present = [path for path in self._composed_root.iterdir() if path.is_file()] if self._composed_root.is_dir() else []
        except OSError as exc:
            self._say_tidy_failed(exc)
            return
        self._remove_unwanted(present)

    def _remove_unwanted(self, paths: Sequence[Path]) -> None:
        """Remove each of `paths` that no work of the feed composes to now and that is not on the wall.

        A file that will not go is said once and costs nothing else: a
        composed directory is regenerable, and a wall must not stop over one.
        """
        if self._feed is None:
            return
        wanted = {planned.composed for work_id in self._feed.named() if (planned := self._plan(work_id)) is not None}
        if self._shown_path is not None:
            wanted.add(self._shown_path)
        removed = 0
        for path in paths:
            if path in wanted:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                self._say_tidy_failed(exc)
                return
            removed += 1
        if removed:
            log.info(
                "removed %d composed picture(s) no work of the feed needs",
                removed,
                extra={"event": "schedule.composed_removed", "wall_id": self._wall_id},
            )
        if self._tidy_failed.end():
            log.info(
                "the composed pictures can be tidied again", extra={"event": "schedule.tidy_recovered", "wall_id": self._wall_id}
            )

    def _say_tidy_failed(self, exc: OSError) -> None:
        if self._tidy_failed.begin():
            log.warning(
                "could not tidy the composed pictures in %s (%s); the wall goes on",
                self._composed_root,
                exc,
                extra={"event": "schedule.tidy_failed", "wall_id": self._wall_id},
            )
