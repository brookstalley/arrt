"""Each wall's display state, as the server derives it (`labels-and-surfaces.md` § Display state).

The controller's five states come from the heartbeat (minor 3), a Player before
minor 3 is read through `current_work_id`, and the server adds `unassigned` and
`silent`. Read from real heartbeat files, through `heartbeat.read`, because that
is what `survey_walls` reads.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from arrt.persistence.records import Wall
from arrt.programming.display_state import ScreenState, display_state_of
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS

CONTRACT = Path(__file__).resolve().parents[3] / "contract" / "fixtures" / "heartbeat.v1"
NOW = datetime(2026, 10, 8, 20, 0, tzinfo=UTC)
ASSIGNED = Wall(id="w1", name="The hall", created_at=NOW, client_id="c1", output="hdmi-a-1")


def reading_of(tmp_path, document, *, age=timedelta(seconds=5)):
    document = {**document, "reported_at": (NOW - age).isoformat()}
    path = tmp_path / "display-heartbeat-w1.json"
    path.write_text(json.dumps(document))
    return heartbeat.read(path, now=NOW)


def minor_3(state, work_id=None, since="2026-10-08T19:00:00+00:00"):
    return {
        "schema": {"major": 1, "minor": 3},
        "current_work_id": "w-old",
        "display_state": {"state": state, "work_id": work_id, "since": since},
    }


@pytest.mark.parametrize("state", ["showing_art", "in_use", "dark", "no_screen", "unreachable"])
def test_a_minor_3_report_is_the_walls_state(tmp_path, state):
    work_id = "w-dali" if state == "showing_art" else None
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, minor_3(state, work_id)))

    assert shown.state is ScreenState(state)
    assert shown.work_id == work_id
    assert shown.since == datetime(2026, 10, 8, 19, 0, tzinfo=UTC)
    assert shown.reported_at == NOW - timedelta(seconds=5)
    assert shown.last is None


def test_display_state_is_read_over_current_work_id(tmp_path):
    """A Frame after a remote-control change: the state says so, the old field does not."""
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, minor_3("showing_art", None)))

    assert shown.state is ScreenState.SHOWING_ART
    assert shown.work_id is None


def test_a_pre_minor_3_report_naming_a_work_is_showing_art(tmp_path):
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, {"current_work_id": "w-dali"}))

    assert shown.state is ScreenState.SHOWING_ART
    assert shown.work_id == "w-dali"
    assert shown.since is None


@pytest.mark.parametrize("current", [None, "", 7])
def test_a_pre_minor_3_report_naming_no_work_cannot_tell(tmp_path, current):
    document = {} if current is None else {"current_work_id": current}
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, document))

    assert shown.state is ScreenState.UNREACHABLE
    assert shown.work_id is None


def test_a_wall_no_client_shows_is_unassigned_whatever_its_file_says(tmp_path):
    unassigned = Wall(id="w1", name="The hall", created_at=NOW)
    shown = display_state_of(unassigned, reading_of(tmp_path, minor_3("showing_art", "w-dali")))

    assert shown.state is ScreenState.UNASSIGNED
    assert shown.work_id is None
    assert shown.last is None


def test_a_report_past_the_threshold_is_silent_and_keeps_what_it_said(tmp_path):
    age = timedelta(seconds=STALE_AFTER_SECONDS + 1)
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, minor_3("showing_art", "w-dali"), age=age))

    assert shown.state is ScreenState.SILENT
    assert shown.work_id is None
    assert shown.since == NOW - age
    assert shown.reported_at == NOW - age
    assert shown.last is not None
    assert (shown.last.state, shown.last.work_id) == (ScreenState.SHOWING_ART, "w-dali")


def test_a_report_at_the_threshold_still_speaks(tmp_path):
    age = timedelta(seconds=STALE_AFTER_SECONDS)
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, minor_3("dark"), age=age))

    assert shown.state is ScreenState.DARK


def test_a_report_stamped_ahead_of_this_clock_is_not_silent(tmp_path):
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, minor_3("in_use"), age=timedelta(minutes=-10)))

    assert shown.state is ScreenState.IN_USE


def test_no_report_is_silent_with_nothing_last(tmp_path):
    shown = display_state_of(ASSIGNED, heartbeat.read(tmp_path / "absent.json", now=NOW))

    assert shown.state is ScreenState.SILENT
    assert (shown.since, shown.reported_at, shown.age_seconds, shown.last) == (None, None, None, None)


# The unknown-state fixture is schema-invalid (the writer's contract) and read,
# not refused, by the server: a later minor may add a state, and Players upgrade
# first, so refusing it would silence an upgraded Player's wall.
MALFORMED = sorted(
    path for path in (CONTRACT / "invalid").glob("display-state-*.json") if path.name != "display-state-unknown.json"
)


@pytest.mark.parametrize("fixture", MALFORMED, ids=lambda path: path.name)
def test_a_file_carrying_a_malformed_display_state_is_silent(tmp_path, fixture):
    """The file channel is not checked on the way in, so the read refuses what POST would."""
    document = json.loads(fixture.read_text())
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, document))

    assert shown.state is ScreenState.SILENT
    assert shown.last is None


@pytest.mark.parametrize("fixture", MALFORMED, ids=lambda path: path.name)
def test_the_server_refuses_each_malformed_display_state(fixture):
    assert heartbeat.problem_with(json.loads(fixture.read_text())) is not None


def test_a_state_a_later_minor_added_is_read_as_unreachable_naming_no_work(tmp_path):
    document = json.loads((CONTRACT / "invalid" / "display-state-unknown.json").read_text())
    document["display_state"]["work_id"] = "w-dali-1"

    assert heartbeat.problem_with(document) is None
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, document))
    assert (shown.state, shown.work_id) == (ScreenState.UNREACHABLE, None)


@pytest.mark.parametrize("fixture", sorted((CONTRACT / "valid").glob("*.json")), ids=lambda path: path.name)
def test_every_valid_heartbeat_reads_as_a_reported_state(tmp_path, fixture):
    document = json.loads(fixture.read_text())
    assert heartbeat.problem_with(document) is None
    shown = display_state_of(ASSIGNED, reading_of(tmp_path, document))
    assert shown.state in {ScreenState.SHOWING_ART, ScreenState.IN_USE, ScreenState.DARK, ScreenState.UNREACHABLE}
    if "display_state" in document:
        assert shown.state is ScreenState(document["display_state"]["state"])
        assert shown.work_id == document["display_state"]["work_id"]


def test_survey_walls_carries_each_walls_state(services, wall_settings):
    """Through the service both surfaces read, with two walls in two states."""
    hall = services.display.survey_walls()[0].wall
    study = services.display.add_wall(name="Study")
    client = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(hall.id, client_id=client.id, output="hdmi-a-1")
    services.display.record_heartbeat(
        hall.id, {**minor_3("in_use"), "reported_at": datetime.now(UTC).isoformat(timespec="seconds")}
    )

    states = {view.wall.id: view.display_state.state for view in services.display.survey_walls()}

    assert states == {hall.id: ScreenState.IN_USE, study.id: ScreenState.UNASSIGNED}
    assert services.display.get_wall_view(hall.id).display_state.state is ScreenState.IN_USE


def test_the_server_knows_exactly_the_states_the_schema_names():
    """Copied by hand from the schema, so a state added there and not here is caught by name.

    The server's own two (unassigned, silent) are the only states it has that a
    controller cannot report.
    """
    schema = json.loads((Path(__file__).parents[3] / "contract" / "schemas" / "heartbeat.v1.schema.json").read_text())
    named = set(schema["properties"]["display_state"]["properties"]["state"]["enum"])

    assert set(heartbeat.REPORTED_DISPLAY_STATES) == named
    assert {state.value for state in ScreenState} - named == {"unassigned", "silent"}
