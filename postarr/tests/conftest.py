"""Fixtures for the display plane: an art root, a store, a clock that does not tick.

The daemon is driven one `tick()` at a time rather than started and stopped,
because a loop exercised through its own timer is a test that fails on a busy
machine and tells you nothing when it does. Time is a parameter here, so a
three-minute rotation interval is asserted in microseconds.
"""

import json
import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fakes import FakeTv
from hypothesis import settings as hypothesis_settings

from postarr.config import CACHED_MANIFEST_FILENAME, ClientSettings, FrameSettings, Settings
from postarr.daemon import Clock, Daemon
from postarr.manifest import Watcher
from postarr.state import DisplayState

#: **The property suite is derandomized, and that is a decision rather than a
#: default.** Hypothesis normally draws fresh examples per run, so a property
#: suite can go red on a commit that touched nothing near it — and a suite that
#: does that is one people learn to re-run until it passes, which is worse than
#: not having it at all. Pinned, a failure means the code changed, and the
#: examples it explores still number in the hundreds per property.
#:
#: **What is given up is real and is bought back deliberately**: a fixed corpus
#: stops finding new counterexamples once it has been seen green. The label
#: engine's inputs are enumerable in the dimension that matters — which fields a
#: work has — so the properties below draw from the *whole* space rather than
#: sampling a tail of it, and the fixed seed is choosing which surfaces to cross
#: it with rather than which content to try.
#:
#: **No health check is suppressed, and that is worth stating because one was.**
#: `function_scoped_fixture` was disarmed here on the reasoning that this file's
#: fixtures would trip it — they cannot: that check fires only for a `@given` test
#: that *requests* a function-scoped fixture, no property here takes one, and
#: nothing in this file is autouse. Registered globally it would have bought
#: nothing today and cost the next property test that takes `tmp_path` its
#: warning, which is the exact failure the check exists for: one fixture instance
#: silently shared across all 200 examples.
hypothesis_settings.register_profile(
    "postarr",
    derandomize=True,
    max_examples=200,
)
hypothesis_settings.load_profile("postarr")


class FakeClock:
    """Wall time and elapsed time that only move when a test moves them."""

    def __init__(self, at: datetime | None = None) -> None:
        self._now = at or datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
        self._elapsed = 1000.0

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._elapsed += seconds

    def move_to(self, at: datetime) -> None:
        """Jump wall time without moving elapsed time.

        The two are independent on purpose — that is the whole reason the daemon
        reads them separately — so a test can put the sun where it wants it
        without also firing every interval that was pending.
        """
        self._now = at

    def as_clock(self) -> Clock:
        return Clock(now=lambda: self._now, monotonic=lambda: self._elapsed)


#: The wall every fixture in this suite serves. A readable literal rather than a
#: UUID because what the plane requires is *a* wall id, and the assertions that
#: name a file are legible with this one. Module-level so a test that has a wall
#: directory but no `Settings` can still say which wall's file it means.
WALL_ID = "living-room"

#: The client's token in every fixture. Distinctive, so a test can search a
#: journal for it.
CLIENT_TOKEN = "the-clients-token"


@pytest.fixture(autouse=True)
def _root_logger_as_found() -> Iterator[None]:
    """Undo whatever a test's `main()` does to the root logger.

    `logs.configure()` sets the root level and attaches a handler on the test's
    own stderr, which pytest closes when that test ends. Left in place, every
    later test in the run captures lines it never asked for, and writes each to a
    closed stream. The curation suite failed on exactly this.
    """
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """`CACHE_DIR`: every wall this client serves has a directory under it."""
    return tmp_path / "cache"


@pytest.fixture
def wall_dir(cache_dir: Path) -> Path:
    """The fixture wall's directory, as `ClientSettings.wall` derives it."""
    root = cache_dir / WALL_ID
    (root / "ready").mkdir(parents=True)
    return root


@pytest.fixture
def frame_settings(cache_dir: Path) -> FrameSettings:
    """A Frame whose every interval is a round number a test can reason about."""
    return FrameSettings(
        tv_address="10.0.0.1",
        tv_port=8002,
        tv_token_file=cache_dir / "token_file",
        tv_client_name="tvpi-test",
        epd_panel_width_px=1448,
        epd_panel_height_px=1072,
        # The reference wall: a 6-inch panel read from 7 feet. Stated even though
        # the fixture below configures no panel, because a `Settings` that omitted
        # them would let a test reach a code path no real deployment with a label
        # can be in — the two are what a label surface is derived from.
        epd_panel_diagonal_inches=6.0,
        epd_viewing_distance_inches=84.0,
        # None, which is the shipped shape: the border derives from the type
        # rather than being chosen beside it. Tests wanting a specific one build
        # their own `Geometry`.
        epd_margin_px=None,
        epd_rotate_degrees=180,
        # Empty, so the daemon fixtures below get the deployment most devices are:
        # a television and no panel. The tests that want one attach a double.
        epd_device="",
        latitude=45.68,
        longitude=-111.04,
        location_name="Bozeman",
        location_region="USA",
        tv_min_brightness=-4,
        tv_max_brightness=10,
        brightness_interval_seconds=300.0,
        upload_timeout_seconds=60.0,
        upload_retry_seconds=300.0,
        # Zero, so a confirmation is one read and no test waits on a real sleep.
        # The window's *duration* is exercised where it is the subject, by a test
        # that moves the clock itself.
        select_confirm_seconds=0.0,
        tv_connect_timeout_seconds=30.0,
        tv_retry_min_seconds=5.0,
        tv_retry_max_seconds=300.0,
    )


@pytest.fixture
def client_settings(cache_dir: Path, frame_settings: FrameSettings) -> ClientSettings:
    """A client with a Frame. Its server is an address nothing listens on; tests that talk to one replace it."""
    return ClientSettings(
        server_url="http://127.0.0.1:9",
        client_token=CLIENT_TOKEN,
        cache_dir=cache_dir,
        poll_interval_seconds=1.0,
        rotation_interval_fallback_seconds=180,
        rotation_shuffle_fallback=False,
        frame=frame_settings,
    )


@pytest.fixture
def settings(client_settings: ClientSettings, wall_dir: Path) -> Settings:
    """The fixture wall on the Frame, derived exactly as the supervisor derives it."""
    derived = client_settings.frame_wall(WALL_ID)
    assert derived.wall_dir == wall_dir
    return derived


@pytest.fixture
def state(settings: Settings, clock: "FakeClock") -> Iterator[DisplayState]:
    # The store shares the daemon's clock, because the daemon measures a retry
    # wait against a timestamp the store wrote. Two clocks there is not a test
    # detail — it is a wait computed from the difference between today and a
    # fixture's chosen afternoon.
    with DisplayState(settings.state_path, now=lambda: clock.as_clock().now()) as store:
        yield store


@pytest.fixture
def tv() -> FakeTv:
    return FakeTv()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def daemon(settings: Settings, tv: FakeTv, state: DisplayState, clock: FakeClock) -> Daemon:
    watcher = Watcher(
        settings.manifest_path,
        rotation_interval_fallback=settings.rotation_interval_fallback_seconds,
        shuffle_fallback=settings.rotation_shuffle_fallback,
    )
    return Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())


@pytest.fixture
def publish(wall_dir: Path) -> Callable[..., dict]:
    """Cache a manifest the way the pull does, and the renders it names.

    Renders are created by default because their *absence* is a distinct
    behaviour with its own tests — a fixture that silently omitted them would
    make every other test exercise the skip path by accident.
    """

    def _publish(
        work_ids: list[str],
        *,
        wall_id: str = WALL_ID,
        sequence: int = 0,
        pinned_work_id: str | None = None,
        major: int = 1,
        interval_seconds: int = 180,
        shuffle: bool = False,
        renders: bool = True,
        theme_id: str = "theme-1",
        labels: dict[str, dict] | None = None,
    ) -> dict:
        document = {
            "schema": {"major": major, "minor": 0},
            "generated_at": datetime.now(UTC).isoformat(),
            "theme": {"id": theme_id, "name": "A theme"},
            "rotation": {"interval_seconds": interval_seconds, "shuffle": shuffle},
            "directive": {"sequence": sequence, "pinned_work_id": pinned_work_id},
            "entries": [
                {
                    "work_id": work_id,
                    "render_path": f"ready/{work_id}.jpg",
                    # A plausible default so callers that do not care get real
                    # label text rather than an empty block — an empty label is a
                    # distinct behaviour with its own tests, and a fixture that
                    # produced one by default would make every other test
                    # exercise that path by accident.
                    "label": (labels or {}).get(work_id, {"title": f"Work {work_id}"}),
                }
                for work_id in work_ids
            ],
        }
        if renders:
            for work_id in work_ids:
                # **Written once, not on every publish.** Curation rewrites the
                # manifest on every catalogue edit and does not touch the renders,
                # so a fixture that rewrote them would move every file's mtime and
                # make each `sync` look like forty re-renders — which the daemon
                # now correctly treats as forty re-uploads.
                render = wall_dir / "ready" / f"{work_id}.jpg"
                if not render.exists():
                    render.write_bytes(b"not really a jpeg")
        write_manifest(wall_dir, document, wall_id=wall_id)
        return document

    return _publish


def write_manifest(wall_dir: Path, document: object, *, wall_id: str = WALL_ID) -> None:
    """Cache a manifest as the pull does: atomically, into the wall's own directory.

    Temp file in the same directory then `os.replace`, so a reader never sees a
    partial document — and so the mtime the watcher keys on moves on every write.

    **The wall defaults to the one the fixtures serve, and is an argument at
    all** so a test can cache a manifest for another wall on the same client —
    which lands in that wall's directory, beside this one's, and is the property
    one directory per wall was built for.
    """
    target = wall_dir.parent / wall_id / CACHED_MANIFEST_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document), encoding="utf-8")
    temporary.replace(target)
