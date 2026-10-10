"""Fixtures for the display plane: an art root, a store, a clock that does not tick.

The daemon is driven one `tick()` at a time rather than started and stopped,
because a loop exercised through its own timer is a test that fails on a busy
machine and tells you nothing when it does. Time is a parameter here, so a
three-minute slot is asserted in microseconds.
"""

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pytest
from fakes import FakeTv
from hypothesis import settings as hypothesis_settings
from PIL import Image

from arrt_player.compose import DEFAULT_MAT_MODE, Geometry, composed_path
from arrt_player.config import (
    CACHED_MANIFEST_FILENAME,
    COMPOSED_DIRNAME,
    ClientSettings,
    FrameSettings,
    PanelSettings,
    Settings,
)
from arrt_player.displays.frame import frame_wall
from arrt_player.manifest import MEDIA_DIRNAME, Watcher, media_name
from arrt_player.state import DisplayState
from arrt_player.wall import Clock, Wall

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
    "arrt-player",
    derandomize=True,
    max_examples=200,
)
hypothesis_settings.load_profile("arrt-player")


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
    root.mkdir(parents=True)
    return root


@pytest.fixture
def frame_settings(cache_dir: Path) -> FrameSettings:
    """A Frame whose every interval is a round number a test can reason about."""
    return FrameSettings(
        tv_address="10.0.0.1",
        tv_port=8002,
        tv_token_file=cache_dir / "token_file",
        tv_client_name="tvpi-test",
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
        tv_panel_width_px=3840,
        tv_panel_height_px=2160,
        tv_panel_diagonal_inches=50.0,
    )


@pytest.fixture
def panel_settings() -> PanelSettings:
    """The label panel as a client with none states it: the reference geometry, no device."""
    return PanelSettings(
        epd_panel_width_px=1448,
        epd_panel_height_px=1072,
        # The reference wall: a 6-inch panel read from 7 feet. Stated even though
        # the fixture configures no panel, because settings that omitted them
        # would let a test reach a code path no real deployment with a label can
        # be in — the two are what a label surface is derived from.
        epd_panel_diagonal_inches=6.0,
        epd_viewing_distance_inches=84.0,
        # None, which is the shipped shape: the border derives from the type
        # rather than being chosen beside it. Tests wanting a specific one build
        # their own `Geometry`.
        epd_margin_px=None,
        epd_rotate_degrees=180,
        # Empty, so the fixtures get the deployment most devices are: a
        # television and no panel. The tests that want one attach a double.
        epd_device="",
    )


@pytest.fixture
def client_settings(cache_dir: Path, frame_settings: FrameSettings, panel_settings: PanelSettings) -> ClientSettings:
    """A client with a Frame. Its server is an address nothing listens on; tests that talk to one replace it."""
    return ClientSettings(
        server_url="http://127.0.0.1:9",
        client_token=CLIENT_TOKEN,
        cache_dir=cache_dir,
        poll_interval_seconds=1.0,
        frame=frame_settings,
        panel=panel_settings,
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
def daemon(settings: Settings, tv: FakeTv, state: DisplayState, clock: FakeClock) -> Wall:
    watcher = Watcher(settings.manifest_path)
    return frame_wall(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())


#: Where every fixture feed's schedule starts: the instant `FakeClock` starts at,
#: so the first work of a feed is the one up when a test begins.
FEED_STARTS: Final[datetime] = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)

#: The mat colour of every fixture feed's works.
FEED_MAT: Final[str] = "#222222"

#: How many slots a fixture feed carries at most. A one-second slot repeated
#: over a whole day would be a document of 86,400 slots; this covers more than
#: any test moves its clock, and the rest of the horizon is a gap, in which the
#: wall keeps what it shows.
_MOST_SLOTS: Final[int] = 2000


def work_sha(work_id: str) -> str:
    """A fixture work's media hash: lowercase hex, distinct per work, and stable across publishes."""
    return hashlib.sha256(work_id.encode("utf-8")).hexdigest()


class Publisher:
    """Cache a major 2 feed the way the pull does, with each work's master and composed picture.

    **The schedule stands in for a rotation**: the works in order, each up for
    `interval_seconds`, from the instant the test clock starts and round again,
    over a one-day horizon. So the first work is up at once, and the next once
    the clock moves past the slot.

    **Each work's picture is composed already**, for the geometry this wall's
    display composes for (the Frame's unless a test sets `geometry`), as a wall
    whose cache survived a restart has it. A test of what reaches the display
    then sees it on the first pass, rather than after a composition on a thread;
    composing is `test_schedule.py`'s and `test_majors.py`'s subject, which run
    it for real. The picture's bytes are not a JPEG, as the renders this fixture
    used to write were not: no display double decodes them.

    Masters and pictures are written by default, because their *absence* is a
    distinct behaviour with its own tests — a fixture that silently omitted them
    would make every other test exercise that path by accident.
    """

    def __init__(self, wall_dir: Path, geometry: Geometry) -> None:
        self._wall_dir = wall_dir
        #: What the pictures are composed for; a screen's test sets its own.
        self.geometry = geometry

    def __call__(
        self,
        work_ids: list[str],
        *,
        wall_id: str = WALL_ID,
        interval_seconds: int = 180,
        media: bool = True,
        theme_id: str = "theme-1",
        labels: dict[str, dict] | None = None,
    ) -> dict:
        works = {
            work_id: {
                "media": {"url": f"/media/sha256-{work_sha(work_id)}", "sha256": work_sha(work_id)},
                "mat_color": FEED_MAT,
                # A plausible default so callers that do not care get real label
                # text rather than an empty block — an empty label is a distinct
                # behaviour with its own tests.
                "label": (labels or {}).get(work_id, {"title": f"Work {work_id}"}),
            }
            for work_id in work_ids
        }
        horizon_until = FEED_STARTS + timedelta(days=1)
        slots = []
        start = FEED_STARTS
        for position in range(_MOST_SLOTS):
            if not work_ids or start >= horizon_until:
                break
            until = min(start + timedelta(seconds=interval_seconds), horizon_until)
            slots.append({"work_id": work_ids[position % len(work_ids)], "from": _instant(start), "until": _instant(until)})
            start = until
        document = {
            "schema": {"major": 2, "minor": 0},
            "generated_at": datetime.now(UTC).isoformat(),
            "playlist": {"id": theme_id, "name": "A theme"},
            "works": works,
            "schedule": {"horizon": {"from": _instant(FEED_STARTS), "until": _instant(horizon_until)}, "slots": slots},
        }
        if media:
            for work_id in work_ids:
                # **Written once, not on every publish.** The server republishes on
                # every catalogue edit without touching a work's media, so a
                # fixture that rewrote these would move every file's mtime and
                # make each republish look like forty new pictures — which the
                # Frame correctly treats as forty re-uploads.
                master = self.master(work_id, wall_id=wall_id)
                if not master.exists():
                    master.parent.mkdir(parents=True, exist_ok=True)
                    master.write_bytes(b"not really a master")
                picture = self.picture(work_id, wall_id=wall_id)
                if not picture.exists():
                    picture.parent.mkdir(parents=True, exist_ok=True)
                    picture.write_bytes(b"not really a jpeg")
        write_manifest(self._wall_dir, document, wall_id=wall_id)
        return document

    def master(self, work_id: str, *, wall_id: str = WALL_ID) -> Path:
        """Where the pull caches this work's master."""
        return self._wall_dir.parent / wall_id / MEDIA_DIRNAME / media_name(work_sha(work_id))

    def picture(self, work_id: str, *, wall_id: str = WALL_ID) -> Path:
        """The file this work composes to on this wall's display: the one the display is handed."""
        return composed_path(
            self._wall_dir.parent / wall_id / COMPOSED_DIRNAME,
            master_sha256=work_sha(work_id),
            mat_color=FEED_MAT,
            mode=DEFAULT_MAT_MODE,
            geometry=self.geometry,
        )

    def withdraw(self, work_id: str) -> None:
        """Take a work's master and picture out of the cache, as a pull that could not fetch it leaves it."""
        self.master(work_id).unlink(missing_ok=True)
        self.picture(work_id).unlink(missing_ok=True)

    def work_of(self, path: Path | None) -> str | None:
        """Which fixture work a picture handed to a display is, by its composed name; None for none."""
        if path is None:
            return None
        for candidate in self._named:
            if self.picture(candidate) == path:
                return candidate
        raise AssertionError(f"{path} is not a picture any fixture work composes to")

    @property
    def _named(self) -> list[str]:
        cached = json.loads((self._wall_dir / CACHED_MANIFEST_FILENAME).read_text(encoding="utf-8"))
        return list(cached["works"])


def _instant(at: datetime) -> str:
    return at.isoformat()


@pytest.fixture
def publish(wall_dir: Path, client_settings: ClientSettings) -> Publisher:
    """Cache a major 2 feed the way the pull does; see `Publisher`."""
    return Publisher(wall_dir, client_settings.frame_wall(WALL_ID).geometry)


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


def a_master(path: Path, colour: tuple[int, int, int] = (200, 30, 30), size: tuple[int, int] = (300, 200)) -> Path:
    """A presentation master the compositor can decode: a real JPEG, small enough to compose in milliseconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path, format="JPEG", quality=95)
    return path


async def tick_until(tick: Callable[[], Awaitable[object]], done: Callable[[], bool], *, passes: int = 200) -> None:
    """Run passes until `done`, letting a composition's thread finish between them.

    The wall composes in the background and never waits for it, so a test of
    what reaches the display runs the loop as the wall does: pass after pass,
    with time for the thread in between. Fails rather than passing on a budget.
    """
    for _ in range(passes):
        await tick()
        if done():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"not done after {passes} passes")
