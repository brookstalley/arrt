"""The heartbeat, driven by the real Frame loop rather than called directly.

**These exist because everything they exercise was, briefly, unreachable.** The
heartbeat writer had a full suite of its own and no production caller — which is
the shape of a green suite over a feature that does nothing. What is asserted
here is only what the Frame loop itself does with it.

**The label tests that lived here moved with the label** to
`test_label_renderer.py`: the Frame loop no longer draws the panel, it only
reports, and every label follows its report through the server
(`labels-and-surfaces.md`). What stays is the Frame loop's side of that: it
reports no label surface, says nothing about one, and never stops for one.

The governing rule throughout: **nothing about a heartbeat may stop the wall.**
"""

import asyncio
import io
import json
import logging
from pathlib import Path

import pytest
from conftest import WALL_ID

from arrt_player import logs
from arrt_player.heartbeat import INTERVAL_SECONDS, path_in


class TestTheFrameLoopDrawsNoLabel:
    """A Frame wall is a supported deployment with or without a panel on its client:
    the panel is a label output, mapped and drawn elsewhere."""

    @pytest.fixture
    def journal(self):
        """The lines this plane would actually write, parsed (see `test_label_renderer.py`)."""
        root = logging.getLogger()
        handlers, level = list(root.handlers), root.level
        logs.configure()
        installed = [handler for handler in root.handlers if handler not in handlers]
        assert len(installed) == 1, "configure() no longer installs exactly one handler"
        written = io.StringIO()
        installed[0].setStream(written)

        def lines() -> list[dict]:
            return [json.loads(line) for line in written.getvalue().splitlines() if line.startswith("{")]

        yield lines
        root.handlers[:] = handlers
        root.setLevel(level)

    @pytest.mark.asyncio
    async def test_the_wall_rotates_normally(self, daemon, tv, publish):
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await daemon.tick()

        assert tv.displaying is not None

    @pytest.mark.asyncio
    async def test_it_claims_nothing_about_a_label(self, daemon, publish, journal):
        """The Frame loop has nowhere to put one; a label event from it would be a
        report about a panel it does not drive."""
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await daemon.tick()

        assert not [line for line in journal() if str(line.get("event", "")).startswith("label.")]

    @pytest.mark.asyncio
    async def test_the_heartbeat_says_no_surface_and_null_rather_than_false(self, daemon, publish, wall_dir: Path):
        """`false` would read as a broken panel on a loop that has none."""
        publish(["work-a"])

        await daemon.tick()

        document = json.loads(path_in(wall_dir, WALL_ID).read_text())
        assert document["label_surface_working"] is None
        assert document["has_label_surface"] is False

    @pytest.mark.asyncio
    async def test_a_selection_the_set_never_displayed_is_not_reported_as_shown(self, daemon, tv, publish, wall_dir: Path):
        """**What kept the label from naming a picture the set accepted and never
        displayed, now that the label follows this report.** Moved from "nothing is
        captioned when the wall did not change": a wrong label is worse than a stale
        one, and the label is only as right as the display state it reads."""
        tv.displays_nothing_selected = True
        publish(["work-a"], labels={"work-a": {"title": "Cat Litter"}})

        await daemon.tick()

        document = json.loads(path_in(wall_dir, WALL_ID).read_text())
        assert document["display_state"]["work_id"] != "work-a"


class TestShuttingDown:
    @pytest.mark.asyncio
    async def test_it_closes_the_art_channel(self, daemon, tv):
        stop = asyncio.Event()
        stop.set()

        await daemon.run(stop)

        assert tv.closed == 1


class TestTheHeartbeat:
    @pytest.mark.asyncio
    async def test_a_running_plane_writes_one(self, daemon, publish, wall_dir: Path):
        publish(["work-a"])

        await daemon.tick()

        assert path_in(wall_dir, WALL_ID).is_file()

    @pytest.mark.asyncio
    async def test_it_carries_what_the_wall_is_showing(self, daemon, publish, wall_dir: Path):
        publish(["work-a"])

        await daemon.tick()

        document = json.loads(path_in(wall_dir, WALL_ID).read_text())
        assert document["current_work_id"] == "work-a"
        assert document["television_reachable"] is True
        assert document["television_showing_art"] is True

    @pytest.mark.asyncio
    async def test_it_carries_the_sets_own_announcement_not_only_our_belief(self, daemon, tv, publish, wall_dir: Path, clock):
        """Somebody used the remote. The heartbeat should say what is actually up."""
        publish(["work-a"])
        await daemon.tick()

        tv.announce("SAM-F0222", is_shown=True)
        clock.advance(INTERVAL_SECONDS * 1.5)
        await daemon.tick()

        document = json.loads(path_in(wall_dir, WALL_ID).read_text())
        assert document["announced_content_id"] == "SAM-F0222"

    @pytest.mark.asyncio
    async def test_it_is_written_while_the_television_is_unreachable(self, daemon, tv, publish, wall_dir: Path):
        """The condition an operator most wants reported.

        A plane that only beat on good passes would fall silent exactly when it
        had something to say, and curation would report a healthy process as one
        that has never spoken.
        """
        publish(["work-a"])
        tv.unavailable = True

        await daemon.tick()

        document = json.loads(path_in(wall_dir, WALL_ID).read_text())
        assert document["television_reachable"] is False
        assert document["last_error"]

    @pytest.mark.asyncio
    async def test_it_is_written_before_any_manifest_exists(self, daemon, wall_dir: Path):
        """The state a fresh install sits in, and when 'is it alive' is asked most."""
        await daemon.tick()

        document = json.loads(path_in(wall_dir, WALL_ID).read_text())
        assert document["manifest_schema"] is None

    @pytest.mark.asyncio
    async def test_it_is_not_rewritten_on_every_pass(self, daemon, publish, wall_dir: Path, clock):
        """At the one-second poll this would be ~86,400 writes a day, forever."""
        publish(["work-a"])
        await daemon.tick()
        first = path_in(wall_dir, WALL_ID).read_text()

        clock.advance(INTERVAL_SECONDS / 4)
        await daemon.tick()

        assert path_in(wall_dir, WALL_ID).read_text() == first

    @pytest.mark.asyncio
    async def test_it_is_rewritten_once_the_interval_has_run(self, daemon, publish, wall_dir: Path, clock):
        publish(["work-a"])
        await daemon.tick()
        first = json.loads(path_in(wall_dir, WALL_ID).read_text())

        # Deliberately not a whole multiple of the interval: a clock stepped by
        # exactly the wait cannot tell `>=` from `>`.
        clock.advance(INTERVAL_SECONDS * 1.5)
        await daemon.tick()

        second = json.loads(path_in(wall_dir, WALL_ID).read_text())
        assert second["reported_at"] != first["reported_at"]

    @pytest.mark.asyncio
    async def test_an_unwritable_heartbeat_does_not_stop_the_wall(self, daemon, tv, publish, wall_dir: Path):
        """The disk is full or read-only. The television is unaffected."""
        path_in(wall_dir, WALL_ID).mkdir()
        publish(["work-a"])

        await daemon.tick()

        assert tv.displaying is not None
