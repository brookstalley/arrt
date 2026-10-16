"""One wall: a programme says what should be on it, a display puts it there.

**One loop for every kind of display.** A wall used to have a loop per kind —
the Frame's and an HDMI screen's — each adopting the manifest, deciding what
to show, showing it and beating, and each drifting from the other in
small ways. What is shared now lives here and in the programme; what is a
display's own lives in its driver (`arrt_player.displays`):

* **The programme** (`arrt_player.programmes`) holds what the wall should show:
  for a major 2 feed the schedule and its scene. The wall holds one per major it
  reads and uses the one whose major it adopted last, so a major served beside
  2 later is one more programme. A programme asks the display whether it may
  change the wall, and then to show a picture.
* **The display** owns everything about its screen: for the Frame, the set's
  art mode, its uploads and bindings, reconciliation, brightness and what the
  set announces; for a screen this host draws on, drawing and redrawing. It
  keeps the display-state record every label of the wall follows, and the last
  error.
* **The loop** runs one pass at a time and writes the wall's heartbeat.

**Nothing here is a command handler.** Curation writes desired state and the
wall converges on it. If curation dies, the wall keeps following the last
schedule for ever, which is the availability norm working, not degradation.

**The display going away is an expected operating condition.** A display names
the exceptions that mean it cannot be reached (`Display.unavailable`); such a
pass still beats, and then waits as long as the display says, because a wall
that only reported on good passes would fall silent exactly when it had
something to say.
"""

import asyncio
import enum
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from arrt_player import heartbeat as heartbeat_module
from arrt_player.config import WallSettings
from arrt_player.episodes import ReportOnce
from arrt_player.heartbeat import DisplayReport, ScreenState
from arrt_player.manifest import REQUESTED_MAJORS, Feed, Watcher

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Clock:
    """Wall time and elapsed time, injected so the loop is testable at any hour.

    Two readings rather than one, because they answer different questions and one
    of them lies. `now()` is for the sun, which genuinely cares what time it is.
    `monotonic()` is for every interval, so an NTP correction — routine on a Pi
    with no RTC, which comes up believing it is 1970 — cannot stall a wait
    for the length of the jump or fire every timer at once.
    """

    now: Callable[[], datetime]
    monotonic: Callable[[], float]

    @staticmethod
    def system() -> "Clock":
        return Clock(now=lambda: datetime.now(UTC).astimezone(), monotonic=time.monotonic)


class Shown(enum.Enum):
    """What came of trying to put one work on the wall.

    **Three outcomes rather than a boolean, because two failures want opposite
    responses.** A work that cannot be shown — no render, no binding — means try
    the next one, which is what makes a theme with a pruned image tree degrade to
    the works that survive. A wall that is not accepting selections at all means
    try *nothing* else: every remaining work would fail identically, and a pass
    that walked forty of them would cost eighty round trips against a television
    that displayed none of it.
    """

    YES = "yes"
    #: This work could not be shown; another might.
    SKIP = "skip"
    #: The display took the request and displayed nothing. No work will fare
    #: better until that changes, so the pass ends here.
    WALL_UNCHANGED = "wall_unchanged"


@dataclass(frozen=True)
class Picture:
    """One work as a display is handed it: its composition for this display."""

    work_id: str
    path: Path
    #: What the journal calls it.
    title: str
    #: The theme it was shown from, for the journal.
    theme_id: str | None = None


@dataclass(frozen=True)
class Capabilities:
    """What a display can do, as `player-contract.md` § The heartbeat, minor 2 names it."""

    #: `(width, height)` in pixels, or None while the display cannot say.
    screen: tuple[int, int] | None
    #: `frame` or `framebuffer`.
    backend: str
    #: The modes of text on the display itself it can draw now.
    label_modes: tuple[str, ...]


class DisplayRecord:
    """What the wall's screen is doing (`labels-and-surfaces.md` § Display state), and whether that is owed to the heartbeat.

    **A change is written on the pass that saw it**, not at the heartbeat's
    interval, because every label of the wall follows this record
    (`player-contract.md` § The heartbeat, minor 3).
    """

    def __init__(self, clock: Clock, *, wall_id: str, initial: DisplayReport | None = None) -> None:
        self._clock = clock
        self._wall_id = wall_id
        self.report = initial
        #: A change not yet written.
        self.owed = False

    def moved_to(self, state: ScreenState, work_id: str | None = None) -> None:
        """Record what the screen is doing now, and say so when it changed."""
        now = self._clock.now()
        moved = (
            DisplayReport(state=state, work_id=work_id, since=now)
            if self.report is None
            else self.report.moved_to(state, work_id, at=now)
        )
        if moved is self.report:
            return
        self.report = moved
        self.owed = True
        log.info(
            "the screen is %s%s",
            state.value,
            f" ({work_id})" if work_id is not None else "",
            extra={"event": "display.state", "wall_id": self._wall_id, "display_state": state.value, "work_id": work_id},
        )


class Display(Protocol):
    """One kind of screen a wall can be on. See this module's docstring for what is the display's own."""

    #: The exceptions that mean the display cannot be reached this pass.
    unavailable: tuple[type[Exception], ...]
    #: The word this display's start, stop and crash lines are filed under in
    #: the journal (`<journal_name>.started`), kept from when each kind had its
    #: own loop so a journal search an operator already uses still finds them.
    journal_name: str
    #: What the journal calls this display when it starts and stops.
    description: str
    record: DisplayRecord

    @property
    def last_error(self) -> str | None:
        """The last thing that went wrong, for the heartbeat. Not cleared by a good pass."""

    def start_lines(self) -> dict[str, object]:
        """The structured fields of the start line."""

    def adopted(self, pictures: Sequence[Picture]) -> None:
        """A new manifest was adopted, and these are the pictures it names."""

    async def prepare(self, pictures: Sequence[Picture]) -> None:
        """Get ready to change the wall this pass. May raise one of `unavailable`."""

    def may_attempt(self) -> bool:
        """Whether the wall may be asked to change yet, without asking the display anything."""

    async def is_ours(self) -> bool:
        """Whether the wall may be changed now: asked only when something is about to happen."""

    async def show(self, picture: Picture) -> Shown:
        """Put one picture on the screen, or say why it could not be."""

    async def after(self, pictures: Sequence[Picture]) -> None:
        """The rest of a pass with a manifest, once the wall has had its chance to change."""

    async def idle(self) -> None:
        """A pass with no manifest yet."""

    def went_away(self, exc: Exception) -> float:
        """The display could not be reached; record it, and say how long to wait."""

    def answering(self) -> None:
        """A pass reached the display."""

    def heartbeat_fields(self, *, reachable: bool | None) -> dict[str, Any]:
        """This display's own keys of the wall's heartbeat."""

    def capabilities(self) -> Capabilities:
        """What the display can do now. Read on every pass, so it must be cheap."""

    async def close(self) -> None:
        """Let go of the display, on every way out of the loop."""


class Programme(Protocol):
    """What should be on the wall, given a manifest of the major it reads."""

    @property
    def pictures(self) -> Sequence[Picture]:
        """Every picture the adopted manifest names, whether or not it is in the cache yet."""

    @property
    def current_work_id(self) -> str | None:
        """The work the wall is showing, as this wall last confirmed it."""

    @property
    def scene_id(self) -> str | None:
        """The scene the wall is showing, or None."""

    def adopt(self, manifest: Any) -> None:  # noqa: ANN401 -- each programme takes its own major's document
        """Take a new manifest of this programme's major."""

    def entered(self) -> None:
        """The wall switched to this programme from another major, whose picture is up now."""

    async def step(self, display: Display) -> None:
        """Change the wall if the programme says to."""


class Wall:
    """One wall, one display, one loop."""

    def __init__(
        self,
        *,
        wall: WallSettings,
        display: Display,
        programmes: Mapping[int, Programme],
        watcher: Watcher,
        clock: Clock,
    ) -> None:
        self._wall = wall
        self._display = display
        #: One programme per manifest major, and the one whose major was adopted
        #: last. **Each keeps its own state across a switch**, and they share the
        #: display's memory of which work is on the wall. **Not the picture**: each
        #: major draws a work its own way, so a programme switched to is told it
        #: was (`entered`) and puts its own picture up. The lowest major answers
        #: before any manifest.
        self._programmes = programmes
        self._programme = programmes[min(programmes)]
        self._watcher = watcher
        self._clock = clock
        self._heartbeat_at: float | None = None
        self._heartbeat_failed = ReportOnce()
        #: The capabilities last written, so a change — a screen plugged in, or
        #: one of another size — is reported at once rather than at the interval.
        self._capabilities_written: dict[str, Any] | None = None

    async def run(self, stop: asyncio.Event) -> None:
        """Run until asked to stop."""
        name = self._display.journal_name
        log.info(
            "%s starting for wall %s",
            self._display.description,
            self._wall.wall_id,
            extra={"event": f"{name}.started", **self._display.start_lines()},
        )
        crashed = False
        try:
            while not stop.is_set():
                interval = await self.tick()
                await self._wait(stop, interval)
        except Exception:  # prawduct:allow prawduct/broad-except -- top-level supervisor; records and re-raises unchanged
            # **`Exception`, not `BaseException`, and the difference is a wrong
            # log line.** `CancelledError` and `KeyboardInterrupt` are shutdowns,
            # not crashes; reporting one as crashed at ERROR would be the inverse
            # of what this is for. They still reach the `finally`, so the display
            # is let go of either way.
            #
            # **Nothing is swallowed and nothing is handled** — the exception goes
            # straight back out to the supervisor, which restarts the wall. What
            # this buys is the only record that will exist: without an ERROR here
            # a crash left the stopped line at INFO, which is the identical line a
            # clean shutdown writes.
            crashed = True
            log.exception(
                "%s is stopping on an error",
                self._display.description,
                extra={"event": f"{name}.crashed", "wall_id": self._wall.wall_id},
            )
            raise
        finally:
            # **Let go of on every way out, including the unexpected one.** The
            # Frame has been observed refusing new art-channel connections for
            # minutes after a client went away without closing.
            await self._display.close()
            if not crashed:
                log.info(
                    "%s stopped for wall %s",
                    self._display.description,
                    self._wall.wall_id,
                    extra={"event": f"{name}.stopped", "wall_id": self._wall.wall_id},
                )

    async def tick(self) -> float:
        """One pass. Returns how long to wait before the next one.

        Public because it is the unit the tests drive: a loop that could only be
        exercised by starting it and stopping it would be tested through a timer,
        and timing tests are the ones that go flaky on a loaded machine.
        """
        # The manifest is read first and unconditionally, because it is local file
        # I/O that cannot fail on account of the display. A set that is asleep
        # must not stop the wall from *knowing* what it will show when it wakes.
        adopted = self._watcher.poll()
        if adopted is not None:
            programme = self._programmes[adopted.schema_major]
            if programme is not self._programme:
                # Before the adoption, which a programme may read it in.
                programme.entered()
                self._programme = programme
            self._programme.adopt(adopted)
            self._display.adopted(self._programme.pictures)

        manifest = self._watcher.current
        if manifest is None:
            # **Still beats.** A wall with no manifest is the state a fresh
            # install sits in, and it is exactly when somebody wants to know this
            # process is alive.
            await self._display.idle()
            self._beat(manifest=None, reachable=None)
            return self._wall.poll_interval_seconds

        pictures = self._programme.pictures
        try:
            await self._display.prepare(pictures)
            await self._programme.step(self._display)
            await self._display.after(pictures)
        except self._display.unavailable as exc:
            wait = self._display.went_away(exc)
            self._beat(manifest=manifest, reachable=False)
            return wait

        self._display.answering()
        self._beat(manifest=manifest, reachable=True)
        return self._wall.poll_interval_seconds

    def _beat(self, *, manifest: Feed | None, reachable: bool | None) -> None:
        """Write the heartbeat once per interval, and at once when the display state changed.

        **Rate-limited here rather than by the caller**, so every path through
        `tick` can call it unconditionally — including the two that return early.
        A heartbeat gated behind the good path is one that goes quiet precisely
        when it matters. Its own failure is an episode like any other: worth one
        line, not one a minute.
        """
        record = self._display.record
        capabilities = self._capabilities()
        elapsed = self._clock.monotonic()
        due = self._heartbeat_at is None or elapsed - self._heartbeat_at >= heartbeat_module.INTERVAL_SECONDS
        if not due and not record.owed and capabilities == self._capabilities_written:
            return
        self._capabilities_written = capabilities
        self._heartbeat_at = elapsed
        # Cleared on the attempt: a disk that refuses this write gets the next
        # one at the interval, not on every poll.
        record.owed = False
        health = heartbeat_module.Health(
            manifest_schema=f"{manifest.schema_major}.{manifest.schema_minor}" if manifest is not None else None,
            theme_id=manifest.theme_id if manifest is not None else None,
            current_work_id=self._programme.current_work_id,
            last_error=self._display.last_error,
            display_state=record.report,
            capabilities=capabilities,
            scene_id=self._programme.scene_id,
            **self._display.heartbeat_fields(reachable=reachable),
        )
        try:
            heartbeat_module.write(self._wall.heartbeat_root, health, wall_id=self._wall.wall_id, reported_at=self._clock.now())
        except OSError as exc:
            if self._heartbeat_failed.begin():
                log.warning(
                    "could not write the heartbeat to %s (%s); the wall is unaffected",
                    heartbeat_module.path_in(self._wall.heartbeat_root, self._wall.wall_id),
                    exc,
                    extra={"event": "heartbeat.failed", "wall_id": self._wall.wall_id},
                )
            return
        if self._heartbeat_failed.end():
            log.info(
                "the heartbeat is being written again", extra={"event": "heartbeat.recovered", "wall_id": self._wall.wall_id}
            )

    def _capabilities(self) -> dict[str, Any]:
        """The heartbeat's `capabilities`, with `screen` only while the display knows its size.

        The rest goes regardless (heartbeat minor 4): the server reads a
        heartbeat with no capabilities as a Player that cannot read its feed.
        """
        found = self._display.capabilities()
        screen = {} if found.screen is None else {"screen": {"width_px": found.screen[0], "height_px": found.screen[1]}}
        return {
            **screen,
            "backend": found.backend,
            "label_modes": list(found.label_modes),
            "manifest_majors": list(REQUESTED_MAJORS),
        }

    async def _wait(self, stop: asyncio.Event, seconds: float) -> None:
        """Sleep, but wake immediately when asked to stop.

        systemd's stop timeout is finite, and a wall that slept through a SIGTERM
        for the length of a backoff would be killed rather than closed — leaving
        the Frame's websocket to time out on the set's side.
        """
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            return
