"""Start the Player: `uv run python -m arrt_player`.

The composition root, and the only module that knows a real television exists —
everything above the seam is written against `TvClient`, so this is where the
`samsungtvws` fork is named and where it stays. It is also the only module that
imports the pull, which holds this plane's one HTTP client.

**One process per client, one worker per wall** (`clients.md` § The Player). The
supervisor (`client.Supervisor`) asks the server which walls this client drives
and runs a worker for each on its output: one wall loop (`wall.Wall`) and the
wall's pull, with the Frame's driver for the Frame (`run_frame_wall`) and the
screen's for a screen this host draws on (`run_screen_wall`).

**And one label renderer per mapped label output** (`labels-and-surfaces.md`):
`run_label` for the e-paper panel, which this module opens once per process
(`label_panel`) because it is the client's, not any wall's. The Frame's identity
is read here too, at the client, so a Frame with no wall on it still says who it
is (`FrameIdentity`).

**A dead pull ends its own wall's worker, and the supervisor starts it again.**
A pull that stops leaves its wall rotating its cache, taking no updates and
sending no heartbeat, which is invisible from the wall. So the worker stops with
the pull's error, which the supervisor logs at ERROR and answers with a restart.
That used to be the whole process stopping so systemd restarted it; with several
walls in one process, that would blank every other wall over one wall's fault.

**Shutdown is deliberate rather than abrupt.** systemd sends SIGTERM and then
waits a bounded time before SIGKILL; a process that ignored the first would be
killed with the Frame's websocket open, and the set holds a half-closed art
channel until it times out on its own. The stop event reaches every worker, and
the supervisor waits for each to close what it holds.
"""

import asyncio
import logging
import signal
import sys
from collections.abc import Awaitable, Callable
from functools import partial

from arrt_player import logs
from arrt_player.client import FRAME_KIND, FrameIdentity, LabelAssignment, OutputReport, Supervisor, client_outputs
from arrt_player.config import (
    PANEL_OUTPUT,
    ClientSettings,
    ConfigError,
    FrameSettings,
    PanelSettings,
    Settings,
    WallSettings,
    load,
)
from arrt_player.displays.frame import frame_wall
from arrt_player.displays.screen import ScreenOutput, screen_wall
from arrt_player.kms import KmsOutput
from arrt_player.label_renderer import LabelPanel, LabelRenderer
from arrt_player.manifest import Watcher
from arrt_player.panel import Geometry, LabelSurface, SurfaceUnavailable
from arrt_player.panel.legibility import TypeScale, ViewingConditionsUnknown, margin_for, type_scale_for
from arrt_player.pull import ClientPull, LabelPull, Pull
from arrt_player.state import DisplayState, StateSchemaTooNew
from arrt_player.tv.samsung import SamsungTv
from arrt_player.wall import Clock

log = logging.getLogger(__name__)


def label_surface(settings: PanelSettings) -> LabelSurface | None:
    """This device's label surface, None when it has none, raising when it has a broken one.

    **The three outcomes are three different things and are reported
    differently.** No `EPD_DEVICE` means this device draws no label, which
    `architecture.md` § Direction makes a supported deployment rather than a
    fault — `None`, and nothing said. A configured panel that will not open is a
    device that is *meant* to have a label and does not, which is worth saying
    out loud — hence a raise rather than a second `None`, because two roads to
    the same return value is how a broken panel came to look identical to a
    deployment that never had one.

    **The rasterizer is imported here rather than at the top of this module.** It
    pulls in Pango through PyGObject, which is installed only where a label is
    actually drawn, and importing it unconditionally would make a text stack a
    requirement for every device including the ones with no panel at all.

    **The type scale is derived here** because this is where `.env` is read and
    where a device is decided to have a panel; everything below the seam takes its
    physical facts as arguments, which is what lets the next device be a
    configuration rather than a rewrite.
    """
    if not settings.epd_device:
        return None

    # **Before the driver import, deliberately.** Both are reasons this device
    # gets no label, but only one of them is a value somebody typed: a deployment
    # that has not stated its viewing distance should be told that, not told its
    # text stack is missing — which on a dev machine it also is.
    try:
        scale = type_scale_for(
            width_px=settings.epd_panel_width_px,
            height_px=settings.epd_panel_height_px,
            diagonal_inches=settings.epd_panel_diagonal_inches,
            viewing_distance_inches=settings.epd_viewing_distance_inches,
        )
    except ViewingConditionsUnknown as exc:
        # Converted rather than propagated, the same move the text stack's
        # ImportError gets below: this function's promise to its caller is that a
        # device without a usable label surface raises one type, and the caller
        # answers all of them by saying so once and rotating the wall anyway.
        raise SurfaceUnavailable(str(exc)) from exc

    geometry = label_geometry(settings, scale)
    # **The derived numbers, said out loud once, and before the imports below.**
    # The startup line carries the two inputs; without these an operator asking
    # "why is this label dropping three lines" has a formula in an artifact and no
    # way to see what the wall actually computed. Whether the border was derived
    # or overridden is named for the same reason — nothing else distinguishes the
    # two. It sits above the driver import so that a device with a missing text
    # stack still reports what it would have set, which is the case where somebody
    # is already reading the journal.
    log.info(
        "label type derives to %d px over a %d px floor, with a %d px border (%s)",
        scale.primary_px,
        scale.floor_px,
        geometry.margin_px,
        "EPD_MARGIN_PX" if settings.epd_margin_px is not None else "derived",
        extra={"event": "panel.type_scale"},
    )

    try:
        from arrt_player.panel.epaper import EpaperSurface, open_panel
        from arrt_player.panel.pango import PangoRasterizer
    except ImportError as exc:
        # The text stack being absent lands in the same place as the panel being
        # absent, and it is a provisioning mistake somebody can fix while the wall
        # keeps working — so it is converted rather than allowed to crash a daemon
        # whose television is perfectly healthy.
        raise SurfaceUnavailable(f"the label's text stack is not installed ({exc}); try `uv sync --group raster`") from exc

    return EpaperSurface(
        epd=open_panel(settings.epd_device),
        rasterizer=PangoRasterizer(),
        geometry=geometry,
        type_scale=scale,
        rotate_degrees=settings.epd_rotate_degrees,
    )


def label_geometry(settings: PanelSettings, scale: TypeScale) -> Geometry:
    """This panel's usable area, with a border derived from the type on it.

    **Separate from `label_surface` because it is the only part of that function
    reachable without hardware.** Everything else there needs a driver and a text
    stack; this is a decision, and a decision covered by no test is one a
    refactor can invert silently — which for this one means a label that quietly
    goes back to a border chosen against type sizes nobody had measured.

    The margin derives unless the deployment states one. It cannot be picked
    independently: a border trades directly against how many lines survive the
    drop rule, so choosing it apart from the floor that decides how many lines
    there are leaves two numbers in tension that nobody compared. The override is
    for the surface whose border is a physical fact rather than a typographic
    choice — a device drawing its label into the mat area around an artwork does
    not get to choose where the picture ends.
    """
    return Geometry(
        width_px=settings.epd_panel_width_px,
        height_px=settings.epd_panel_height_px,
        margin_px=settings.epd_margin_px if settings.epd_margin_px is not None else margin_for(scale),
    )


def label_panel(settings: PanelSettings) -> LabelPanel | None:
    """This client's label output, or None for a client with no panel configured.

    **A panel that will not open is reported, not fatal**, and not dropped
    either: it is a `LabelPanel` with no surface, which the client heartbeat
    reports as a label output that is not connected. Without it a
    configured-but-broken panel would read on the server exactly like a client
    that never had one.
    """
    if not settings.epd_device:
        return None
    size = (settings.epd_panel_width_px, settings.epd_panel_height_px)
    try:
        surface = label_surface(settings)
    except SurfaceUnavailable as exc:
        log.warning(
            "this device has a panel configured (%s) and no label will be drawn (%s); the walls are unaffected",
            settings.epd_device,
            exc,
            extra={"event": "panel.unavailable", "output": PANEL_OUTPUT},
        )
        return LabelPanel(name=PANEL_OUTPUT, surface=None, error=str(exc), size=size)
    return LabelPanel(name=PANEL_OUTPUT, surface=surface, error=None, size=size)


def frame_tv(settings: FrameSettings) -> SamsungTv:
    """The Frame's television client, as every reader of it is built."""
    return SamsungTv(
        host=settings.tv_address,
        port=settings.tv_port,
        token_file=settings.tv_token_file,
        client_name=settings.tv_client_name,
        connect_timeout_seconds=settings.tv_connect_timeout_seconds,
        upload_timeout_seconds=settings.upload_timeout_seconds,
        select_confirm_seconds=settings.select_confirm_seconds,
    )


async def run_label(
    settings: ClientSettings,
    panel: LabelPanel,
    assignment: LabelAssignment,
    stop: asyncio.Event,
    retired: asyncio.Event,
    *,
    clock: Clock | None = None,
) -> None:
    """The supervisor's label worker: one renderer on this client's panel, until stopped."""
    renderer = LabelRenderer(
        assignment=assignment,
        link=LabelPull(settings, assignment.label_id),
        panel=panel,
        now=(clock if clock is not None else Clock.system()).now,
        poll_seconds=settings.label_poll_seconds,
    )
    await renderer.run(stop, retired)


async def run_frame_wall(settings: Settings, stop: asyncio.Event, *, clock: Clock | None = None) -> None:
    """One wall on the Frame: the wall's loop on the Frame and the wall's pull, until stopped.

    The Frame draws no label: the panel is a label output of the client,
    mapped to a wall by the server and drawn by `run_label`.
    """
    settings.wall_dir.mkdir(parents=True, exist_ok=True)
    watcher = Watcher(
        settings.manifest_path,
        rotation_interval_fallback=settings.rotation_interval_fallback_seconds,
        shuffle_fallback=settings.rotation_shuffle_fallback,
    )
    tv = frame_tv(settings)

    # One clock for both, because the Frame measures an upload's retry wait
    # against a timestamp the store wrote. Two sources here would be two answers
    # to the same question, and the store's is the one that has to survive a
    # restart.
    clock = clock if clock is not None else Clock.system()
    # **A store from a newer plane parks this wall, and only this wall.** Opening
    # it would guess at a shape this code does not know, and restarting cannot
    # change the answer — the fix is a rollout — so the worker says so once and
    # waits to be stopped, rather than crash-looping a traceback per backoff step
    # or ending the process and blanking every other wall this client drives.
    try:
        state = DisplayState(settings.state_path, now=clock.now)
    except StateSchemaTooNew as exc:
        log.error(  # noqa: TRY400 -- the fix is a rollout, not a frame
            "wall %s is not shown: %s",
            settings.wall_id,
            exc,
            extra={"event": "daemon.state_too_new", "wall_id": settings.wall_id},
        )
        await stop.wait()
        return
    with state:
        frame = frame_wall(
            settings=settings,
            tv=tv,
            state=state,
            watcher=watcher,
            clock=clock,
        )
        await _beside_its_pull(settings, stop, frame.run)


async def run_screen_wall(wall: WallSettings, output: str, stop: asyncio.Event, *, clock: Clock | None = None) -> None:
    """One wall on a screen this host draws on: the wall's loop on the screen and the wall's pull, until stopped."""
    wall.wall_dir.mkdir(parents=True, exist_ok=True)
    watcher = Watcher(
        wall.manifest_path,
        rotation_interval_fallback=wall.rotation_interval_fallback_seconds,
        shuffle_fallback=wall.rotation_shuffle_fallback,
    )
    screen = screen_wall(
        wall=wall,
        output=screen_output(wall, output),
        watcher=watcher,
        clock=clock if clock is not None else Clock.system(),
    )
    await _beside_its_pull(wall, stop, screen.run)


def screen_output(
    wall: WallSettings,  # noqa: ARG001 -- every output builder takes the wall; a screen needs only its connector
    output: str,
) -> ScreenOutput:
    """What a wall on an HDMI connector draws on: the connector, through kernel mode setting."""
    return KmsOutput(output)


async def run_wall(settings: ClientSettings, wall: WallSettings, output: OutputReport, stop: asyncio.Event) -> None:
    """The supervisor's worker: the wall on the Frame for the Frame, on a screen this host draws for anything else."""
    if output.kind == FRAME_KIND:
        await run_frame_wall(settings.frame_wall(wall.wall_id), stop)
    else:
        await run_screen_wall(wall, output.name, stop)


async def _beside_its_pull(wall: WallSettings, stop: asyncio.Event, loop: Callable[[asyncio.Event], Awaitable[None]]) -> None:
    """Run a wall's loop with its pull beside it, stopped together.

    **Their own stop event, not the supervisor's.** A dead pull must end this
    worker, and setting the supervisor's event to do that would read to it as
    "this wall was taken away" — the one case it does not restart.
    """
    ending = asyncio.Event()
    relay = asyncio.create_task(_relay(stop, ending), name=f"stop:{wall.wall_id}")
    pulling = asyncio.create_task(Pull(wall).run(ending), name=f"pull:{wall.wall_id}")
    pulling.add_done_callback(lambda task: _pull_ended(task, ending, wall.wall_id))
    try:
        await loop(ending)
    finally:
        ending.set()
        relay.cancel()
        # Re-raises a pull that crashed, so the worker ends failed and the
        # supervisor starts the wall and its pull again together.
        await pulling


async def _relay(stop: asyncio.Event, ending: asyncio.Event) -> None:
    await stop.wait()
    ending.set()


def _pull_ended(task: asyncio.Task[None], ending: asyncio.Event, wall_id: str) -> None:
    """Say at once that the pull died, and end the wall's worker so it starts again.

    A dead pull leaves the wall rotating its cache and taking no updates and
    sending no heartbeat, which is invisible from the wall and would stay
    invisible until somebody stopped the process.
    """
    if task.cancelled() or task.exception() is None:
        return
    log.error(
        "the pull for wall %s stopped on an error; stopping the wall's worker so it starts again",
        wall_id,
        exc_info=task.exception(),
        extra={"event": "pull.crashed", "wall_id": wall_id},
    )
    ending.set()


async def _run() -> int:
    settings = load()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for received in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(received, stop.set)

    clock = Clock.system()
    identity = FrameIdentity(frame_tv(settings.frame).read_identity) if settings.frame is not None else None
    panel = label_panel(settings.panel)
    supervisor = Supervisor(
        settings=settings,
        link=ClientPull(settings),
        worker=partial(run_wall, settings),
        outputs=lambda: client_outputs(settings, frame_identity=identity.value if identity is not None else None),
        now=clock.now,
        monotonic=clock.monotonic,
        label_worker=partial(run_label, settings, panel) if panel is not None else None,
        label_outputs=lambda: [panel.report()] if panel is not None else [],
        frame_identity=identity,
    )
    try:
        await supervisor.run(stop)
    finally:
        # After every renderer has stopped, so no draw is in flight. On e-paper
        # this is the panel's power-down.
        if panel is not None:
            panel.close()
    return 0


def main() -> int:
    logs.configure()
    try:
        return asyncio.run(_run())
    except ConfigError as exc:
        # Named on stderr as well as logged, because the most likely reader of
        # this failure is a person who has just run the command by hand and a
        # JSON line is the harder of the two to read at a terminal.
        #
        # No traceback: it says a *deployment value* is wrong, and the fix is in
        # `.env`. A stack through `load()` points at this codebase, which is the
        # one place the problem is not.
        log.error("%s", exc, extra={"event": "daemon.misconfigured"})  # noqa: TRY400 -- the fix is in .env, not in a frame
        print(f"display plane cannot start: {exc}", file=sys.stderr)  # noqa: T201 -- the operator is at a terminal
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
