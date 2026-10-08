"""The Frame's display state, driven through the real loop.

What the wall's screen is doing (`labels-and-surfaces.md` § Display state) is
reported in the heartbeat as minor 3's `display_state`, written on the pass that
saw it change. Every label of the wall follows it through the server; the panel
that followed it here, while the Frame loop drew it, is the label renderer's now,
and its tests moved with it to `test_label_renderer.py` (`TestThePanelFollowsTheScreen`).

Every document written here is validated against the contract's schema, because
a state the server refuses is a wall that reads as silent.

Clock steps are deliberately not multiples of the heartbeat interval or the
caption hold, so a timer consumed early cannot pass for one correctly withheld.
"""

import json
import logging
from pathlib import Path

from conftest import WALL_ID
from jsonschema import Draft202012Validator

from postarr.heartbeat import INTERVAL_SECONDS, path_in

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
SCHEMA = json.loads((CONTRACT / "schemas" / "heartbeat.v1.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)


def heartbeat(wall_dir: Path) -> dict:
    """The heartbeat on disk, refused here if the server would refuse it."""
    document = json.loads(path_in(wall_dir, WALL_ID).read_text(encoding="utf-8"))
    errors = [error.message for error in VALIDATOR.iter_errors(document)]
    assert errors == [], errors
    return document


def display(wall_dir: Path) -> tuple[str, str | None]:
    reported = heartbeat(wall_dir)["display_state"]
    return reported["state"], reported["work_id"]


class TestTheStateIsReported:
    async def test_art_on_the_wall_names_the_work_and_the_schema_minor_is_3(self, daemon, publish, wall_dir):
        publish(["w1", "w2"])

        await daemon.tick()

        document = heartbeat(wall_dir)
        assert document["schema"] == {"major": 1, "minor": 3}
        assert display(wall_dir) == ("showing_art", "w1")
        # Kept, with their old meanings, for readers built before minor 3.
        assert document["current_work_id"] == "w1"
        assert document["television_showing_art"] is True

    async def test_art_then_television_then_art(self, daemon, tv, publish, wall_dir, clock):
        publish(["w1", "w2"], interval_seconds=900)
        await daemon.tick()
        assert display(wall_dir) == ("showing_art", "w1")

        tv.art_mode = "off"
        tv.art_mode_announced = True
        clock.advance(4.3)
        await daemon.tick()
        assert display(wall_dir) == ("in_use", None)
        assert heartbeat(wall_dir)["television_showing_art"] is False

        tv.art_mode = "on"
        tv.art_mode_announced = True
        clock.advance(7.9)
        await daemon.tick()
        assert display(wall_dir) == ("showing_art", "w1"), "the picture the set went back to is the one it left"

    async def test_art_then_standby_is_dark(self, daemon, tv, publish, wall_dir, clock):
        publish(["w1"])
        await daemon.tick()

        tv.art_mode = "off"
        tv.power = "standby"
        tv.art_mode_announced = True
        clock.advance(3.1)
        await daemon.tick()

        assert display(wall_dir) == ("dark", None)

    async def test_power_state_is_read_only_after_art_mode_says_no(self, daemon, tv, publish, clock):
        """It rides a read the loop was already taking; it adds no cadence of its own."""
        publish(["w1"])
        for _ in range(5):
            await daemon.tick()
            clock.advance(1.3)
        assert tv.power_reads == 0, "PowerState was read while the set was plainly in art mode"

    async def test_an_unreadable_power_state_reports_in_use_and_is_said_once(self, daemon, tv, publish, wall_dir, clock, caplog):
        publish(["w1"], interval_seconds=900)
        await daemon.tick()

        tv.art_mode = "off"
        tv.power_unreadable = True
        with caplog.at_level(logging.INFO):
            for _ in range(4):
                tv.art_mode_announced = True
                clock.advance(2.7)
                await daemon.tick()

        assert display(wall_dir) == ("in_use", None)
        assert tv.power_reads == 4
        events = [getattr(record, "event", None) for record in caplog.records]
        assert events.count("display.power_unreadable") == 1, "a failing PowerState read was reported per pass"
        assert tv.connects == 1, "a failed REST read dropped the art channel as if it were an outage"

    async def test_a_remote_change_names_the_work_the_set_announced(self, daemon, tv, publish, state, wall_dir, clock):
        publish(["w1", "w2"], interval_seconds=900)
        await daemon.tick()
        await daemon.tick()  # the second work is uploaded behind the first
        binding = state.binding_for("w2")
        assert binding is not None
        assert binding.tv_content_id

        tv.announce(binding.tv_content_id, is_shown=True)
        clock.advance(2.2)
        await daemon.tick()

        assert display(wall_dir) == ("showing_art", "w2")
        # The older field keeps its meaning: this plane's own confirmed selection.
        assert heartbeat(wall_dir)["current_work_id"] == "w1"

    async def test_a_picture_this_wall_did_not_put_there_is_art_with_no_work(self, daemon, tv, publish, wall_dir, clock):
        publish(["w1"])
        await daemon.tick()

        tv.announce("SAM-F0222", is_shown=True)
        clock.advance(2.2)
        await daemon.tick()

        assert display(wall_dir) == ("showing_art", None)

    async def test_an_announcement_the_set_says_it_is_not_showing_changes_nothing(self, daemon, tv, publish, wall_dir, clock):
        publish(["w1"])
        await daemon.tick()

        tv.announce("SAM-F0222", is_shown=False)
        clock.advance(2.2)
        await daemon.tick()

        assert display(wall_dir) == ("showing_art", "w1")

    async def test_a_set_that_cannot_be_reached_is_unreachable(self, daemon, tv, publish, wall_dir, clock):
        publish(["w1", "w2"], interval_seconds=60)
        await daemon.tick()

        tv.unavailable = True
        # Learned at the next call the loop makes anyway — here the rotation —
        # since nothing polls the set to find out.
        clock.advance(61.3)
        await daemon.tick()

        assert display(wall_dir) == ("unreachable", None)

    async def test_since_is_when_the_state_began_not_when_it_was_last_seen(self, daemon, tv, publish, wall_dir, clock):
        publish(["w1"], interval_seconds=900)
        await daemon.tick()
        tv.art_mode = "off"
        tv.art_mode_announced = True
        clock.advance(5.5)
        await daemon.tick()
        began = heartbeat(wall_dir)["display_state"]["since"]

        clock.advance(INTERVAL_SECONDS * 1.5)
        tv.art_mode_announced = True
        await daemon.tick()

        document = heartbeat(wall_dir)
        assert document["display_state"]["since"] == began
        assert document["reported_at"] != began


class TestAChangeIsWrittenAtOnce:
    async def test_a_change_does_not_wait_for_the_interval(self, daemon, tv, publish, wall_dir, clock):
        publish(["w1"], interval_seconds=900)
        await daemon.tick()
        first = heartbeat(wall_dir)["reported_at"]

        tv.art_mode = "off"
        tv.art_mode_announced = True
        clock.advance(INTERVAL_SECONDS / 7)
        await daemon.tick()

        assert heartbeat(wall_dir)["reported_at"] != first

    async def test_an_unchanged_state_keeps_the_interval(self, daemon, tv, publish, wall_dir, clock):
        publish(["w1"], interval_seconds=900)
        await daemon.tick()
        tv.art_mode = "off"
        tv.art_mode_announced = True
        clock.advance(2.3)
        await daemon.tick()
        written = path_in(wall_dir, WALL_ID).read_text()

        # The same reading again: news from the set, answered in the same state.
        tv.art_mode_announced = True
        clock.advance(INTERVAL_SECONDS / 7)
        await daemon.tick()

        assert path_in(wall_dir, WALL_ID).read_text() == written


async def test_a_device_with_no_panel_still_reports_its_state(daemon, tv, publish, wall_dir, clock):
    """The display state is the wall's, not the panel's: Walls and every other label read it."""
    publish(["w1"])
    await daemon.tick()
    tv.art_mode = "off"
    tv.power = "standby"
    tv.art_mode_announced = True
    clock.advance(2.5)
    await daemon.tick()

    assert display(wall_dir) == ("dark", None)
    assert heartbeat(wall_dir)["has_label_surface"] is False


def test_the_player_reports_exactly_the_states_the_schema_names():
    """Copied by hand from the schema, so a state added there and not here is caught by name."""
    import json
    from pathlib import Path

    from postarr.heartbeat import ScreenState

    schema = json.loads((Path(__file__).parents[2] / "contract" / "schemas" / "heartbeat.v1.schema.json").read_text())

    assert {state.value for state in ScreenState} == set(schema["properties"]["display_state"]["properties"]["state"]["enum"])
