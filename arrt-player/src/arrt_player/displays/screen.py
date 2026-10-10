"""A screen this client draws on itself, as a wall's display.

Unlike the Frame, a screen holds nothing between restarts — the picture is
whatever this process last put there — so there are no uploads, no bindings and
no art mode to ask about: the wall is always this host's to change, and the
wall's memory of which work is up lasts as long as the process
(`programmes.schedule.InMemory`), so a restarted worker draws the slot's work
again on its first pass.

**The output is an interface** (`ScreenOutput`); an HDMI connector's is
`kms.KmsOutput`. The wall asks it on every pass to draw again if its screen came
back, which is what turns a monitor plugged in after the wall started — or a
television switched back to this input — into the wall's picture rather than a
black screen until the next slot.
"""

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from arrt_player.compose import Geometry
from arrt_player.config import WallSettings
from arrt_player.episodes import ReportOnce
from arrt_player.heartbeat import ScreenState
from arrt_player.manifest import Watcher
from arrt_player.programmes.schedule import InMemory, Schedule
from arrt_player.wall import Capabilities, Clock, DisplayRecord, Picture, Shown, Wall

log = logging.getLogger(__name__)


class ScreenOutput(Protocol):
    """A screen this client draws a wall on.

    **`show` blocks and is run on a worker thread**, because drawing a full
    render — decoding it, fitting it to the screen — is seconds of work on a Pi,
    and every wall this client drives shares one event loop. It is given the
    path of a verified render in the wall's cache and draws it fitted to the
    screen; it must not raise for a screen that is off or unplugged, and should
    draw the last render again when one comes back.
    """

    def show(self, render: Path) -> None: ...

    def refresh(self) -> None:
        """Draw the last render again if the screen went away and came back, or changed size.

        Called on every poll, so it must be cheap when nothing changed, and like
        `show` it blocks and must not raise for a screen that is off or unplugged.
        """

    @property
    def listed(self) -> bool:
        """Whether the output exists on this client at all, screen or no screen."""

    @property
    def connected(self) -> bool:
        """Whether a screen is present on the output now."""

    @property
    def screen(self) -> tuple[int, int] | None:
        """`(width, height)` of the screen in pixels, or None when not known."""


def screen_wall(
    *,
    wall: WallSettings,
    output: ScreenOutput,
    watcher: Watcher,
    clock: Clock,
) -> Wall:
    """A wall on a screen this host draws: the shared loop, this driver, and a programme per major, remembering in memory."""
    memory = InMemory()

    def geometry() -> Geometry | None:
        """The connector's current mode, which can change under a running wall; None with no screen on it."""
        return None if output.screen is None else wall.geometry_for(output.screen)

    return Wall(
        wall=wall,
        display=ScreenDisplay(wall=wall, output=output, clock=clock),
        programmes={
            2: Schedule(
                wall_id=wall.wall_id,
                render_root=wall.render_root,
                composed_root=wall.composed_root,
                geometry=geometry,
                memory=memory,
                clock=clock,
            ),
        },
        watcher=watcher,
        clock=clock,
    )


class ScreenDisplay:
    """One screen, as a wall's display."""

    #: Nothing here means the screen cannot be reached: an unplugged screen is
    #: a state this display reports (`no_screen`, `dark`), never a failed pass.
    unavailable: tuple[type[Exception], ...] = ()
    journal_name = "screen"
    description = "the screen"

    def __init__(self, *, wall: WallSettings, output: ScreenOutput, clock: Clock) -> None:
        self._wall = wall
        self._output = output
        #: What the screen is doing. None until the first pass has looked.
        self.record = DisplayRecord(clock, wall_id=wall.wall_id)
        #: The work on the screen, as this display last put it there.
        self._showing: str | None = None
        self._last_error: str | None = None
        self._refresh_failed = ReportOnce()
        self._draw_failed = ReportOnce()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def start_lines(self) -> dict[str, object]:
        return self._wall.wall_lines()

    def adopted(self, pictures: Sequence[Picture]) -> None:  # noqa: ARG002 -- the wall.Display protocol's signature
        return

    async def prepare(self, pictures: Sequence[Picture]) -> None:  # noqa: ARG002 -- the wall.Display protocol's signature
        return

    def may_attempt(self) -> bool:
        return True

    async def is_ours(self) -> bool:
        """Always: nobody else draws on this screen."""
        return True

    async def show(self, picture: Picture) -> Shown:
        try:
            await asyncio.to_thread(self._output.show, picture.path)
        except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- costs this picture, never the wall
            self._last_error = f"the screen refused {picture.work_id} ({exc})"
            # Once per episode: a screen that refuses one work refuses the
            # next, and the schedule tries again at every slot.
            if self._draw_failed.begin():
                log.warning(
                    "could not draw %s on the screen (%s); the wall goes on",
                    picture.work_id,
                    exc,
                    extra={"event": "screen.draw_failed"},
                )
            return Shown.SKIP
        if self._draw_failed.end():
            log.info("the screen draws again", extra={"event": "screen.draw_recovered"})
        self._showing = picture.work_id
        log.info(
            "showing %s",
            picture.title,
            extra={"event": "rotation.selected", "picture_path": str(picture.path)},
        )
        return Shown.YES

    async def after(self, pictures: Sequence[Picture]) -> None:  # noqa: ARG002 -- the wall.Display protocol's signature
        await self._refresh()
        self._observe_the_screen()

    async def idle(self) -> None:
        await self._refresh()
        self._observe_the_screen()

    def went_away(self, exc: Exception) -> float:
        # Unreachable: `unavailable` is empty, so the wall never calls this.
        raise exc

    def answering(self) -> None:
        return

    def heartbeat_fields(self, *, reachable: bool | None) -> dict[str, Any]:  # noqa: ARG002 -- the Display protocol's
        # A screen has no television to reach, and draws no label.
        return {}

    def capabilities(self) -> Capabilities:
        """The connector's current mode as its screen; no text of its own until a caption is drawn in the mat (wave 6+)."""
        return Capabilities(screen=self._output.screen, backend="framebuffer", label_modes=("none",))

    async def close(self) -> None:
        return

    async def _refresh(self) -> None:
        """Let the output draw again for a screen that came back. Its failure is said once, and costs the pass nothing."""
        try:
            await asyncio.to_thread(self._output.refresh)
        # A screen that cannot be redrawn must not stop the wall.
        except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- see above
            self._last_error = f"the screen could not be drawn again ({exc})"
            if self._refresh_failed.begin():
                log.warning(
                    "could not draw the screen again (%s); trying on every poll",
                    exc,
                    extra={"event": "screen.refresh_failed", "wall_id": self._wall.wall_id},
                )
            return
        if self._refresh_failed.end():
            log.info("the screen can be drawn again", extra={"event": "screen.refresh_recovered", "wall_id": self._wall.wall_id})

    def _observe_the_screen(self) -> None:
        """Read the display state off the output, every pass, and note a change.

        **This display can always tell**, because it is the one drawing: the
        connector's own `status` says whether a screen is there, the same reading
        the client heartbeat reports, so it never reports `unreachable` or
        `in_use`. An output the kernel no longer lists is `no_screen`; a listed
        connector with no screen detected is `dark`; a screen showing what this
        display last drew is `showing_art`.

        **A screen with nothing of this wall's on it yet is `dark`** — before the
        first draw, or with no manifest, it shows the console's black, not art,
        and `dark` is the state whose label is blank. The cost is one pass of
        "The screen is off" on Walls at startup.
        """
        if not self._output.listed:
            self.record.moved_to(ScreenState.NO_SCREEN)
        elif not self._output.connected or self._showing is None:
            self.record.moved_to(ScreenState.DARK)
        else:
            self.record.moved_to(ScreenState.SHOWING_ART, self._showing)
