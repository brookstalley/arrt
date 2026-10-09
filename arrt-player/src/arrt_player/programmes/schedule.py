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
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

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

    def __init__(self, *, wall_id: str, render_root: Path, memory: Memory, clock: Clock) -> None:
        self._wall_id = wall_id
        self._render_root = render_root
        self._memory = memory
        self._clock = clock
        self._feed: Feed | None = None
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
        """Every work the feed names, staged ones included, so a display can prepare them ahead."""
        if self._feed is None:
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
        # A new feed is news: a work refused under the old one gets its chance.
        self._refused = None

    async def step(self, display: Display) -> None:
        feed = self._feed
        if feed is None:
            return
        target = what_to_show(feed, self._clock.now())
        if target.scene_id is None:
            # No scene is active, whatever is still on the wall: a scene names a
            # live override, and once it has ended there is none — into a gap, or
            # into a slot whose work cannot be shown yet. A scene that is active
            # is reported only once its work is up.
            self._scene_id = None
        if target.work_id is None:
            # A gap. The wall keeps what it has until power control can act on it.
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
            self._shown_path = picture.path
            self._scene_id = target.scene_id
            self._refused = None
        elif outcome is Shown.SKIP:
            self._refused = (target.work_id, self._clock.monotonic())

    def _ready(self, picture: Picture) -> bool:
        """Whether this work can be offered to the display: its media is cached, and it was not just refused."""
        if not picture.path.is_file():
            if picture.work_id not in self._missing:
                self._missing.add(picture.work_id)
                log.warning(
                    "cannot show %s yet: its media is not at %s",
                    picture.work_id,
                    picture.path,
                    extra={"event": "schedule.media_missing", "wall_id": self._wall_id, "render_path": str(picture.path)},
                )
            return False
        refused = self._refused
        return refused is None or refused[0] != picture.work_id or self._clock.monotonic() - refused[1] >= RETRY_SECONDS

    def _picture(self, work_id: str) -> Picture:
        assert self._feed is not None  # noqa: S101 -- called only with a feed adopted
        work = self._feed.works[work_id]
        return Picture(
            work_id=work_id,
            path=self._render_root / work.media_path,
            title=work.label.get("title") or work_id,
            theme_id=self._feed.playlist_id,
        )
