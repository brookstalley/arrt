"""A wall on a screen this client draws itself: the worker, and the output it draws on.

The Frame's loop (`daemon.Daemon`) is a television's: it uploads into the set's
own store, selects by the set's content id, asks the set whether it is in art
mode before touching it, and keeps its place in a store that outlives the
process, because the set holds the picture between restarts. A screen this host
draws on holds nothing of the sort — the picture is whatever this process last
put there — so none of that machinery applies, and what is left is small enough
to write plainly here rather than to carve out of the Frame's loop:

* **the rotation**: the manifest's entries in order, or shuffled afresh on each
  pass when the manifest says shuffle, one every `interval_seconds`;
* **the directive**: `next` steps on and `show_now` jumps to the pinned work,
  each acted on once when `directive.sequence` advances. The first sequence a
  worker sees is its baseline and is not acted on, and one that goes backwards
  is a restored catalogue and re-baselines — both as on the Frame. Unlike the
  Frame, the baseline is held in memory, so a worker restarted after a `show_now`
  it never saw does not replay it;
* **a sync keeps the place**: a rewritten manifest resumes after the work on the
  screen rather than at the first one;
* **a missing render is skipped, never fatal.** The wall going black is always
  worse than the wall being incomplete.

**The output is an interface** (`ScreenOutput`); an HDMI connector's is
`kms.KmsOutput`. The loop asks it on every poll to draw again if its screen came
back, which is what turns a monitor plugged in after the wall started — or a
television switched back to this input — into the wall's picture rather than a
black screen until the next rotation.
"""

import asyncio
import contextlib
import logging
import random
from pathlib import Path
from typing import Protocol

from postarr import heartbeat as heartbeat_module
from postarr.config import WallSettings
from postarr.daemon import Clock
from postarr.episodes import ReportOnce
from postarr.heartbeat import DisplayReport, ScreenState
from postarr.logs import work_context
from postarr.manifest import Entry, Manifest, Watcher

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


class ScreenWall:
    """One wall, one screen, one loop."""

    def __init__(
        self,
        *,
        wall: WallSettings,
        output: ScreenOutput,
        watcher: Watcher,
        clock: Clock,
        rng: random.Random | None = None,
    ) -> None:
        self._wall = wall
        self._output = output
        self._watcher = watcher
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()  # noqa: S311 -- it orders artworks, it guards nothing
        #: Positions into the current manifest's entries, in the order they will
        #: be shown, and where the next one is taken from.
        self._order: list[int] = []
        self._cursor = 0
        #: The work on the screen, as this worker last put it there.
        self._showing: str | None = None
        #: When the last rotation was attempted, stamped before the attempt so a
        #: theme with no usable render is walked once per interval, not per poll.
        self._attempted_at: float | None = None
        #: The directive sequence this worker has acted on, or None before the
        #: first manifest gives it a baseline.
        self._acted_sequence: int | None = None
        self._last_error: str | None = None
        self._heartbeat_at: float | None = None
        self._heartbeat_failed = ReportOnce()
        self._refresh_failed = ReportOnce()
        self._draw_failed = ReportOnce()
        self._missing: set[str] = set()
        #: What the screen is doing, as `labels-and-surfaces.md` § Display state
        #: names it. None until the first pass has looked.
        self._display: DisplayReport | None = None
        #: A change not yet written; see `_beat`.
        self._display_owed = False

    @property
    def showing(self) -> str | None:
        return self._showing

    async def run(self, stop: asyncio.Event) -> None:
        """Rotate until asked to stop."""
        log.info(
            "screen wall %s starting",
            self._wall.wall_id,
            extra={"event": "screen.started", **self._wall.wall_lines()},
        )
        while not stop.is_set():
            interval = await self.tick()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)
        log.info("screen wall %s stopped", self._wall.wall_id, extra={"event": "screen.stopped", "wall_id": self._wall.wall_id})

    async def tick(self) -> float:
        """One pass. Returns how long to wait before the next one."""
        adopted = self._watcher.poll()
        if adopted is not None:
            self._adopt(adopted)
        manifest = self._watcher.current
        if manifest is not None and not await self._act_on_directive(manifest):
            await self._rotate_if_due(manifest)
        await self._refresh()
        self._observe_the_screen()
        self._beat(manifest)
        return self._wall.poll_interval_seconds

    def _observe_the_screen(self) -> None:
        """Read the display state off the output, every pass, and note a change.

        **This controller can always tell**, because it is the one drawing: the
        connector's own `status` says whether a screen is there, the same reading
        the client heartbeat reports, so it never reports `unreachable` or
        `in_use`. An output the kernel no longer lists is `no_screen`; a listed
        connector with no screen detected is `dark`; a screen showing what this
        worker last drew is `showing_art`.

        **A screen with nothing of this wall's on it yet is `dark`** — before the
        first draw, or with no manifest, it shows the console's black, not art,
        and `dark` is the state whose label is blank. The cost is one pass of
        "The screen is off" on Walls at startup.
        """
        if not self._output.listed:
            state, work_id = ScreenState.NO_SCREEN, None
        elif not self._output.connected or self._showing is None:
            state, work_id = ScreenState.DARK, None
        else:
            state, work_id = ScreenState.SHOWING_ART, self._showing
        now = self._clock.now()
        moved = (
            DisplayReport(state=state, work_id=work_id, since=now)
            if self._display is None
            else self._display.moved_to(state, work_id, at=now)
        )
        if moved is self._display:
            return
        self._display = moved
        self._display_owed = True
        log.info(
            "the screen is %s%s",
            state.value,
            f" ({work_id})" if work_id is not None else "",
            extra={"event": "display.state", "wall_id": self._wall.wall_id, "display_state": state.value, "work_id": work_id},
        )

    def _adopt(self, manifest: Manifest) -> None:
        """Take a new manifest's entries as the rotation, resuming after the work on the screen."""
        self._order = list(range(len(manifest.entries)))
        if manifest.shuffle:
            self._rng.shuffle(self._order)
        self._cursor = 0
        self._missing.clear()
        position = manifest.index_of(self._showing) if self._showing is not None else None
        if position is not None:
            self._cursor = (self._order.index(position) + 1) % len(self._order)

    async def _act_on_directive(self, manifest: Manifest) -> bool:
        """Act on `next` or `show_now` once, when the sequence advances. True when the screen changed."""
        observed = manifest.directive_sequence
        if self._acted_sequence is None or observed < self._acted_sequence:
            if self._acted_sequence is not None:
                log.warning(
                    "the manifest's directive sequence went backwards (%d after %d); re-baselining without acting",
                    observed,
                    self._acted_sequence,
                    extra={"event": "directive.regressed", "wall_id": self._wall.wall_id, "sequence": observed},
                )
            self._acted_sequence = observed
            return False
        if observed == self._acted_sequence:
            return False
        self._acted_sequence = observed

        if manifest.pinned_work_id is None:
            log.info("directive %d: stepping to the next work", observed, extra={"event": "directive.acted", "directive": "next"})
            self._attempted_at = self._clock.monotonic()
            return await self._advance(manifest)

        position = manifest.index_of(manifest.pinned_work_id)
        if position is None:
            log.warning(
                "directive %d pins work %s, which the active theme does not carry; continuing to rotate",
                observed,
                manifest.pinned_work_id,
                extra={"event": "directive.pin_unresolvable", "pinned_work_id": manifest.pinned_work_id},
            )
            return False
        log.info(
            "directive %d: jumping to work %s",
            observed,
            manifest.pinned_work_id,
            extra={"event": "directive.acted", "directive": "show_now"},
        )
        # Rotation continues from the pin rather than from where it was.
        self._cursor = (self._order.index(position) + 1) % len(self._order)
        self._attempted_at = self._clock.monotonic()
        return await self._show(manifest.entries[position])

    async def _rotate_if_due(self, manifest: Manifest) -> None:
        if self._attempted_at is not None and self._clock.monotonic() - self._attempted_at < manifest.rotation_interval_seconds:
            return
        self._attempted_at = self._clock.monotonic()
        await self._advance(manifest)

    async def _advance(self, manifest: Manifest) -> bool:
        """Show the next work that can be shown, trying each at most once."""
        for _ in range(len(self._order)):
            position = self._order[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._order)
            if self._cursor == 0 and manifest.shuffle:
                # A new order for each pass through the theme, as on the Frame.
                self._rng.shuffle(self._order)
            if await self._show(manifest.entries[position]):
                return True
        return False

    async def _show(self, entry: Entry) -> bool:
        with work_context(entry.work_id):
            render = self._wall.render_root / entry.render_path
            if not render.is_file():
                if entry.work_id not in self._missing:
                    self._missing.add(entry.work_id)
                    log.warning(
                        "skipping %s: its render is not at %s",
                        entry.work_id,
                        render,
                        extra={"event": "rotation.render_missing", "render_path": str(render)},
                    )
                return False
            try:
                await asyncio.to_thread(self._output.show, render)
            except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- costs this picture, never the wall
                self._last_error = f"the screen refused {entry.work_id} ({exc})"
                # Once per episode: a screen that refuses one work refuses the
                # next, and the rotation tries every work in the theme each time.
                if self._draw_failed.begin():
                    log.warning(
                        "could not draw %s on the screen (%s); the wall keeps rotating",
                        entry.work_id,
                        exc,
                        extra={"event": "screen.draw_failed"},
                    )
                return False
            if self._draw_failed.end():
                log.info("the screen draws again", extra={"event": "screen.draw_recovered"})
            self._showing = entry.work_id
            log.info(
                "showing %s",
                entry.label.get("title") or entry.work_id,
                extra={"event": "rotation.selected", "render_path": str(render)},
            )
            return True

    async def _refresh(self) -> None:
        """Let the output draw again for a screen that came back. Its failure is said once, and costs the poll nothing."""
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

    def _beat(self, manifest: Manifest | None) -> None:
        """Write the wall's heartbeat once per interval, and at once when the display state changed.

        Never stops the wall. A display-state change is written on the pass that
        saw it because every label of the wall follows that record, and the pull
        forwards a changed file within about a second; the interval stays the
        ceiling on everything else, for the SD card's sake.
        """
        elapsed = self._clock.monotonic()
        due = self._heartbeat_at is None or elapsed - self._heartbeat_at >= heartbeat_module.INTERVAL_SECONDS
        if not due and not self._display_owed:
            return
        self._heartbeat_at = elapsed
        # Cleared on the attempt, so a refusing disk is retried at the interval.
        self._display_owed = False
        health = heartbeat_module.Health(
            manifest_schema=f"{manifest.schema_major}.{manifest.schema_minor}" if manifest is not None else None,
            theme_id=manifest.theme_id if manifest is not None else None,
            current_work_id=self._showing,
            last_error=self._last_error,
            display_state=self._display,
        )
        try:
            heartbeat_module.write(self._wall.heartbeat_root, health, wall_id=self._wall.wall_id, reported_at=self._clock.now())
        except OSError as exc:
            if self._heartbeat_failed.begin():
                log.warning(
                    "could not write the heartbeat for wall %s (%s); the wall is unaffected",
                    self._wall.wall_id,
                    exc,
                    extra={"event": "heartbeat.failed"},
                )
            return
        if self._heartbeat_failed.end():
            log.info("the heartbeat is being written again", extra={"event": "heartbeat.recovered"})
