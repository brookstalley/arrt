"""What the composition root refuses to start for, and what it starts anyway.

**One refusal.** A missing deployment value, read by a person who has just run
the command at a terminal, so it owes three things: a non-zero exit so systemd and
a shell agree something failed, a sentence on stderr rather than only a JSON log
line, and no traceback, because a stack through `load()` points at this codebase,
which is the one place the problem is not. It is driven through `main`, since what
is under test is the handling rather than the work.

**A store written by a newer plane is not a refusal any more.** The store is a
wall's, opened by that wall's worker, so it parks that wall and says so once; the
process and every other wall keep running.

**And one thing that is emphatically not a refusal**: a label panel that will not
open. It costs the label, says so in the journal, and is reported as a label
output that is not connected — driven through `label_panel`, because the claim is
about the wiring between a raise and what the client reports, and a test of
either end alone leaves the line between them undefended.

**And how a wall's worker holds its pull**: beside the Frame's loop, stopped with
it, and ending the worker when it dies, so the supervisor starts both again.
"""

import asyncio
from typing import ClassVar

import pytest

from postarr import __main__ as entry
from postarr.config import ConfigError
from postarr.panel import SurfaceUnavailable
from postarr.state import StateSchemaTooNew


@pytest.fixture(autouse=True)
def _quiet_logging(monkeypatch):
    """`main` configures logging as its first act; leave the suite's alone."""
    monkeypatch.setattr(entry.logs, "configure", lambda: None)


def _raising(exc: Exception):
    async def _run() -> int:
        raise exc

    return _run


def test_a_missing_deployment_value_refuses_to_start_and_says_so_at_the_terminal(monkeypatch, capsys):
    what = "CLIENT_TOKEN"
    monkeypatch.setattr(entry, "_run", _raising(ConfigError(f"{what} is not set. Copy .env.example to .env and fill it in.")))

    code = entry.main()

    assert code == 2, "a refusal to start exited zero, so systemd would treat it as a clean stop"
    printed = capsys.readouterr().err
    assert "display plane cannot start" in printed
    assert what in printed, "the operator is told it cannot start but not which value is wrong"


def test_an_unexpected_failure_is_not_swallowed_into_a_tidy_exit(monkeypatch):
    """Only the deployment fault is handled. Anything else must keep its
    traceback: that one is 'the fix is in `.env`', and a bug wearing the same
    two-line exit would send whoever reads it to the wrong file."""
    monkeypatch.setattr(entry, "_run", _raising(RuntimeError("something nobody anticipated")))

    with pytest.raises(RuntimeError):
        entry.main()


class TestWhetherThisDeviceHasALabelSurface:
    """Two roads to no label, and only one of them is a fault.

    `architecture.md` § Direction: a device with no label surface is a supported
    configuration, not a broken deployment. A device whose configured panel will
    not open is broken — and still rotates the wall, because the label is an
    annotation of the product and never a precondition for it.
    """

    def test_a_device_with_no_panel_configured_gets_no_surface_and_no_complaint(self, panel_settings, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            assert entry.label_surface(panel_settings) is None

        assert caplog.records == [], "a supported deployment was reported as a fault"

    def test_a_configured_panel_that_will_not_open_is_a_raise_and_not_a_second_none(self, panel_settings):
        """The panel is absent on every machine this suite runs on, which is what
        makes this the real path rather than a simulated one.

        A raise rather than `None` because the caller has to tell the two apart:
        `None` is a deployment with no panel, and this is a deployment whose panel
        is broken. Collapsing them is how a broken panel became invisible on the
        health surface.
        """
        import dataclasses

        configured = dataclasses.replace(panel_settings, epd_device="no_such_vendor.no_such_panel")

        with pytest.raises(SurfaceUnavailable) as raised:
            entry.label_surface(configured)

        # **Two roads and one type, which is the point.** A laptop has no text
        # stack and stops at the import; a Pi has one and stops at the device. The
        # caller must not have to tell them apart — but the operator must, so
        # whichever road was taken has to name what is missing.
        assert any(
            named in str(raised.value) for named in ("no_such_vendor.no_such_panel", "--group raster")
        ), f"the failure names neither the device nor the missing install: {raised.value}"

    @pytest.mark.parametrize(
        ("unstated", "named"),
        [
            ("epd_panel_diagonal_inches", "EPD_PANEL_DIAGONAL_INCHES"),
            ("epd_viewing_distance_inches", "EPD_VIEWING_DISTANCE_INCHES"),
        ],
    )
    def test_a_panel_whose_viewing_conditions_are_unstated_loses_the_label_and_not_the_wall(
        self, panel_settings, unstated: str, named: str
    ):
        """**The third road to no label, and it is a fault of the same shape.**

        A device with a panel and no stated viewing distance cannot be told how
        large its type has to be, and the one thing that must not happen is
        guessing: a wrong distance gives silently illegible type, which looks like
        success from every direction except standing in front of the panel.

        But it is `SurfaceUnavailable` rather than `ConfigError` — the label
        surface goes, the daemon does not. Refusing to start would break two rules
        this plane holds: nothing about the label may stop the television, and a
        device with no usable label surface is a configuration rather than a
        fault. That distinction is the whole reason this raises the type the
        caller already catches.
        """
        import dataclasses

        configured = dataclasses.replace(panel_settings, epd_device="omni_epd.mock", **{unstated: None})

        with pytest.raises(SurfaceUnavailable) as raised:
            entry.label_surface(configured)

        assert named in str(raised.value), f"the operator is not told which key to set: {raised.value}"

    def test_the_unstated_distance_is_reported_before_the_driver_is_even_looked_for(self, panel_settings):
        """Both are reasons this device draws no label; only one is a value
        somebody typed. A deployment that has not stated its viewing distance must
        be told *that* — not told its text stack is missing, which on a machine
        with no panel it also is, and which names a fix that would not help.
        """
        import dataclasses

        configured = dataclasses.replace(
            panel_settings, epd_device="no_such_vendor.no_such_panel", epd_viewing_distance_inches=None
        )

        with pytest.raises(SurfaceUnavailable) as raised:
            entry.label_surface(configured)

        assert "EPD_VIEWING_DISTANCE_INCHES" in str(raised.value)
        assert "--group raster" not in str(raised.value), "the reader was sent to fix the wrong thing"

    @pytest.mark.parametrize(
        ("margin", "named"),
        [(None, "derived"), (17, "EPD_MARGIN_PX")],
    )
    def test_the_derived_numbers_reach_the_journal_even_with_no_text_stack(self, panel_settings, caplog, margin, named):
        """**What the wall actually computed, not just what it was told.**

        The startup line carries the two inputs; without this an operator asking
        "why is this label dropping three lines" has a formula in an artifact and
        no way to see the numbers. Whether the border was derived or overridden is
        named for the same reason — nothing else in the journal distinguishes them.

        Driven on the path where the surface cannot be opened, which is the reason
        the line sits above the driver import: a device that cannot draw still
        reports what it would have set, and that is precisely when somebody is
        already reading the journal.

        **Which road reaches that path depends on the machine, and the assertion
        holds on both.** Without the `raster` group the text stack import fails
        first; with it — on the Pi, and in the `typesetting` CI job — the import
        succeeds and `open_panel("no_such_vendor…")` raises the same type a step
        later. Saying "the text stack is missing" named one machine's state as
        though it were the test's subject, which is a claim that goes stale by
        being run somewhere else.
        """
        import dataclasses
        import logging

        configured = dataclasses.replace(panel_settings, epd_device="no_such_vendor.no_such_panel", epd_margin_px=margin)

        with caplog.at_level(logging.INFO), pytest.raises(SurfaceUnavailable):
            entry.label_surface(configured)

        derived = [r for r in caplog.records if getattr(r, "event", None) == "panel.type_scale"]
        assert len(derived) == 1, "the derived type never reached the journal"
        assert named in derived[0].getMessage()

    def test_the_border_derives_from_the_type_when_the_deployment_states_none(self, panel_settings):
        """**The shipped path**, and the one the old 40 px default occupied.

        A border trades directly against how many lines survive the drop rule, so
        it cannot be picked independently of the floor that decides how many lines
        there are — which is now derived per device from the viewing distance.
        Asserted against `margin_for` rather than against a number, because a
        literal here would be this test re-stating the ratio instead of checking
        that the ratio is what got used.
        """
        from postarr.panel.legibility import margin_for, type_scale_for

        scale = type_scale_for(
            width_px=panel_settings.epd_panel_width_px,
            height_px=panel_settings.epd_panel_height_px,
            diagonal_inches=panel_settings.epd_panel_diagonal_inches,
            viewing_distance_inches=panel_settings.epd_viewing_distance_inches,
        )

        geometry = entry.label_geometry(panel_settings, scale)

        assert geometry.margin_px == margin_for(scale)
        assert geometry.margin_px > 0, "the label was given no border at all"

    def test_a_deployment_that_states_a_border_keeps_it(self, panel_settings):
        """The override, for the surface whose border is a physical fact: a device
        drawing its label into the mat around an artwork does not choose where the
        picture ends."""
        import dataclasses

        from postarr.panel.legibility import margin_for, type_scale_for

        scale = type_scale_for(width_px=1448, height_px=1072, diagonal_inches=6.0, viewing_distance_inches=84.0)
        stated = dataclasses.replace(panel_settings, epd_margin_px=17)

        assert entry.label_geometry(stated, scale).margin_px == 17
        assert margin_for(scale) != 17, "the override happens to equal the derived value, so this proves nothing"

    def test_a_client_with_no_panel_configured_has_no_label_output(self, panel_settings, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            assert entry.label_panel(panel_settings) is None

        assert caplog.records == [], "a supported deployment was reported as a fault"

    def test_a_broken_panel_is_a_label_output_that_is_not_connected(self, monkeypatch, panel_settings, caplog):
        """**Driven through `label_panel` rather than around it**, because the claim
        is about the wiring and not about either end of it.

        Moved from the Frame worker, which opened the panel while it drew the
        label: `label_surface` raising and the result reporting the panel broken
        were both tested while the `except` joining them was covered by nothing,
        and a mutation sweep changed it to catch `ZeroDivisionError` with every
        test still passing. That mutation is a client that refuses to start
        because a panel is unplugged. The reason, which the Frame loop's heartbeat
        used to carry, is in the journal and on the panel object.
        """
        import dataclasses
        import logging

        def _no_panel(_settings):
            # Stubbed rather than provoked, so the message is the same on a laptop
            # with no text stack and on a Pi with one.
            raise SurfaceUnavailable("could not open the e-paper device 'waveshare_epd.it8951' (no SPI device)")

        monkeypatch.setattr(entry, "label_surface", _no_panel)

        with caplog.at_level(logging.WARNING):
            panel = entry.label_panel(dataclasses.replace(panel_settings, epd_device="waveshare_epd.it8951"))

        assert panel is not None, "a broken panel reported as a client that has none"
        assert panel.surface is None
        assert panel.report().connected is False
        assert panel.report().name == "epd-0"
        assert "no SPI device" in str(panel.error), "the reason was dropped on the way in"
        assert any(record.__dict__.get("event") == "panel.unavailable" for record in caplog.records)
        assert "waveshare_epd.it8951" in caplog.text, "the journal does not name which device could not be opened"

    def test_a_panel_that_opens_is_a_connected_label_output_of_its_size(self, monkeypatch, panel_settings):
        import dataclasses

        from fakes import FakeSurface

        surface = FakeSurface()
        monkeypatch.setattr(entry, "label_surface", lambda _settings: surface)

        panel = entry.label_panel(
            dataclasses.replace(
                panel_settings, epd_device="waveshare_epd.it8951", epd_panel_width_px=800, epd_panel_height_px=600
            )
        )

        assert panel is not None
        assert panel.surface is surface
        assert panel.report().document() == {"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 600]}


async def test_a_crash_still_closes_the_art_channel_on_the_way_out(settings, tv, state, clock):
    """`Restart=always` makes the exit path load-bearing.

    The set has been observed refusing new art-channel connections for minutes
    after a client vanished without closing, apparently holding the slot until it
    times out. So a daemon that skipped its close on the unexpected exit would
    come back up unable to reach the television it just crashed away from.
    """
    from postarr.daemon import Daemon
    from postarr.manifest import Watcher

    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    daemon = Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    async def explode() -> float:
        raise RuntimeError("something nobody predicted")

    daemon.tick = explode  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await daemon.run(asyncio.Event())

    assert tv.closed, "the art channel was left open at the set"


async def test_a_crash_is_distinguishable_from_a_clean_stop_in_the_log(settings, tv, state, clock, caplog):
    """The journal is this plane's only failure channel.

    A crash used to write `daemon.stopped` at INFO — the identical line a clean
    shutdown writes — so an operator reading the log could not tell a wall
    somebody switched off from one falling over in a `Restart=always` loop.
    """
    import logging

    from postarr.daemon import Daemon
    from postarr.manifest import Watcher

    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    daemon = Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())

    async def explode() -> float:
        raise RuntimeError("something nobody predicted")

    daemon.tick = explode  # type: ignore[method-assign]

    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        await daemon.run(asyncio.Event())

    events = [r.__dict__.get("event") for r in caplog.records]
    assert "daemon.crashed" in events, "a crash left no ERROR behind"
    assert "daemon.stopped" not in events, "a crash reported itself as a clean shutdown"
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


class _PullRecorder:
    """Stands in for the pull: records that it ran, and stops when asked, or fails when told to."""

    started: ClassVar[list[object]] = []
    failure: Exception | None = None

    def __init__(self, settings) -> None:
        type(self).started.append(settings)

    async def run(self, stop) -> None:
        if type(self).failure is not None:
            raise type(self).failure
        await stop.wait()


def _wire(monkeypatch, tv, *, daemon_run, pull_fails: Exception | None = None):
    from postarr import daemon as daemon_module

    class QuickDaemon(daemon_module.Daemon):
        async def run(self, stop) -> None:
            await daemon_run(stop)

    _PullRecorder.started = []
    # Set here on every wiring, so a test cannot inherit another's failure.
    monkeypatch.setattr(_PullRecorder, "failure", pull_fails)
    monkeypatch.setattr(entry, "SamsungTv", lambda **kwargs: tv)
    monkeypatch.setattr(entry, "Daemon", QuickDaemon)
    monkeypatch.setattr(entry, "Pull", _PullRecorder)


async def test_the_frames_worker_runs_its_walls_pull_beside_the_loop_and_stops_them_together(monkeypatch, settings, tv):
    async def runs_briefly(stop) -> None:
        await asyncio.sleep(0.01)
        stop.set()

    _wire(monkeypatch, tv, daemon_run=runs_briefly)

    await asyncio.wait_for(entry.run_frame_wall(settings, asyncio.Event()), timeout=5)
    assert _PullRecorder.started == [settings]


async def test_the_supervisors_stop_reaches_the_loop_and_the_pull(monkeypatch, settings, tv):
    """The wall taken away, or SIGTERM: both halves end, and the worker returns rather than raising."""

    async def runs_until_stopped(stop) -> None:
        await stop.wait()

    _wire(monkeypatch, tv, daemon_run=runs_until_stopped)
    stop = asyncio.Event()
    worker = asyncio.create_task(entry.run_frame_wall(settings, stop))
    await asyncio.sleep(0.05)
    assert not worker.done(), "the worker ended before it was asked to"

    stop.set()
    await asyncio.wait_for(worker, timeout=5)


async def test_a_pull_that_dies_ends_its_walls_worker_at_once_and_says_why(monkeypatch, settings, tv, caplog):
    """A dead pull is a wall that takes no updates; it becomes a restart instead of a silence.

    The worker ends with the pull's error, so the supervisor logs it and starts the
    wall again. **The supervisor's own stop event is left alone**: setting it would
    read as the wall having been taken away, which is the one case not restarted.
    """
    import logging

    async def runs_until_stopped(stop) -> None:
        await stop.wait()

    _wire(monkeypatch, tv, daemon_run=runs_until_stopped, pull_fails=OSError("No space left on device"))
    supervisors_stop = asyncio.Event()
    with caplog.at_level(logging.ERROR), pytest.raises(OSError, match="No space"):
        await asyncio.wait_for(entry.run_frame_wall(settings, supervisors_stop), timeout=5)

    assert [record.__dict__.get("event") for record in caplog.records if record.levelno >= logging.ERROR] == ["pull.crashed"]
    assert not supervisors_stop.is_set(), "the pull's death was told to the supervisor as the wall being taken away"


async def test_a_store_from_a_newer_plane_parks_its_wall_and_says_so_once(monkeypatch, settings, tv, caplog):
    """The wall waits to be stopped rather than ending: an ending is a crash to the
    supervisor, restarted every few seconds with a traceback each time, and the
    answer cannot change until a rollout. No loop and no pull start for it."""
    import logging

    async def must_not_run(stop) -> None:
        raise AssertionError("the Frame's loop ran against a store it cannot read")

    _wire(monkeypatch, tv, daemon_run=must_not_run)

    def too_new(path, *, now=None):
        raise StateSchemaTooNew("display-state.sqlite was written by a display plane at schema 9; this one understands 8.")

    monkeypatch.setattr(entry, "DisplayState", too_new)
    stop = asyncio.Event()
    with caplog.at_level(logging.ERROR):
        worker = asyncio.create_task(entry.run_frame_wall(settings, stop))
        await asyncio.sleep(0.05)
        assert not worker.done(), "the wall ended, which the supervisor reads as a crash and restarts"
        stop.set()
        await asyncio.wait_for(worker, timeout=5)

    said = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert [record.__dict__.get("event") for record in said] == ["daemon.state_too_new"]
    assert "schema 9" in said[0].getMessage()
    assert said[0].exc_info is None, "a rollout fault was logged with a traceback into this codebase"
    assert _PullRecorder.started == []
