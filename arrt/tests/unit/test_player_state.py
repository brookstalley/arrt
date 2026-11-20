"""Each Player's state and each of its outputs', as the server derives it (`programming/player_state.py`).

Read from real report files through `client_heartbeat.read`, because that is
what the clients and health routes read, and through `ClientService` where the
token and the recorded outputs come in. The setup flags the server quotes are
held to the contract package, which the server cannot read at run time.
"""

import importlib.metadata
import json
from datetime import UTC, datetime, timedelta

import pytest
from arrt_contract import vocabulary

from arrt.programming import client_heartbeat, display_state, player_state
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS
from arrt.programming.player_state import OutputKind, PlayerState, player_reading, player_state_of

NOW = datetime(2026, 11, 19, 20, 0, tzinfo=UTC)

#: Two label panels and no screen: the shape the owner's ruling 8 keeps open.
PANELS = {
    "outputs": [],
    "label_outputs": [
        {"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]},
        {"name": "epd-1", "kind": "epaper", "connected": False, "size": None},
    ],
}


def report_of(tmp_path, document, *, age=timedelta(seconds=5)):
    path = tmp_path / "client-heartbeat-p1.json"
    path.write_text(json.dumps({**document, "reported_at": (NOW - age).isoformat()}))
    return client_heartbeat.read(path, now=NOW)


def absent(tmp_path):
    return client_heartbeat.read(tmp_path / "client-heartbeat-none.json", now=NOW)


# -- the Player's state -----------------------------------------------------------------


def test_a_player_with_no_token_is_no_token_whatever_its_report_says(tmp_path):
    current = report_of(tmp_path, {"outputs": []})

    assert player_state_of(token_issued=False, reading=current) is PlayerState.NO_TOKEN
    assert player_state_of(token_issued=False, reading=absent(tmp_path)) is PlayerState.NO_TOKEN


def test_a_token_and_no_report_is_awaiting_its_first_report(tmp_path):
    assert player_state_of(token_issued=True, reading=absent(tmp_path)) is PlayerState.AWAITING_REPORT


def test_a_current_report_is_reporting_and_one_past_the_threshold_is_not_heard_from(tmp_path):
    edge = timedelta(seconds=STALE_AFTER_SECONDS)
    at_the_edge = report_of(tmp_path, {"outputs": []}, age=edge)
    past_it = report_of(tmp_path, {"outputs": []}, age=edge + timedelta(seconds=1))

    assert player_state_of(token_issued=True, reading=at_the_edge) is PlayerState.REPORTING
    assert player_state_of(token_issued=True, reading=past_it) is PlayerState.NOT_HEARD_FROM
    assert player_reading(token_issued=True, reading=past_it).since == NOW - edge - timedelta(seconds=1)


def test_a_report_that_cannot_be_read_is_report_unreadable(tmp_path):
    path = tmp_path / "client-heartbeat-p1.json"
    path.write_text("{ not json")

    reading = player_reading(token_issued=True, reading=client_heartbeat.read(path, now=NOW))

    assert reading.state is PlayerState.REPORT_UNREADABLE
    assert reading.since is None


# -- each output's state (ruling 8) -------------------------------------------------------


def test_each_label_panel_of_a_player_with_no_screen_has_a_state_of_its_own(tmp_path):
    """Two reported panels and one the curator named first: three outputs, read apart."""
    reading = player_reading(token_issued=True, reading=report_of(tmp_path, PANELS), recorded_labels=["epd-0", "epd-2"])

    assert reading.state is PlayerState.REPORTING
    assert [(o.kind, o.name, o.state, o.connected) for o in reading.outputs] == [
        (OutputKind.LABEL, "epd-0", PlayerState.REPORTING, True),
        (OutputKind.LABEL, "epd-1", PlayerState.REPORTING, False),
        (OutputKind.LABEL, "epd-2", PlayerState.AWAITING_REPORT, None),
    ]


def test_a_player_not_reporting_lists_its_recorded_outputs_in_its_own_state_and_says_nothing_of_connection(tmp_path):
    stale = report_of(tmp_path, {"outputs": [], **PANELS}, age=timedelta(hours=2))

    reading = player_reading(token_issued=True, reading=stale, recorded_displays=["hdmi-a-1"], recorded_labels=["epd-0"])

    assert [(o.kind, o.name, o.state, o.connected) for o in reading.outputs] == [
        (OutputKind.DISPLAY, "hdmi-a-1", PlayerState.NOT_HEARD_FROM, None),
        (OutputKind.LABEL, "epd-0", PlayerState.NOT_HEARD_FROM, None),
    ]


def test_an_output_both_reported_and_recorded_is_listed_once(tmp_path):
    document = {"outputs": [{"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]}]}

    reading = player_reading(token_issued=True, reading=report_of(tmp_path, document), recorded_displays=["hdmi-a-1"])

    assert [(o.name, o.state) for o in reading.outputs] == [("hdmi-a-1", PlayerState.REPORTING)]


def test_the_client_service_gives_each_label_panel_its_own_state(services):
    """Through the service the routes call: the token and the recorded label outputs come from the store."""
    clients = services.clients
    door = clients.add_client(name="The Pi by the door")
    services.access.issue(door.id)
    clients.record_heartbeat(door.id, {**PANELS, "reported_at": datetime.now(UTC).isoformat()})
    wall = services.display.add_wall(name="Landing")
    clients.add_label(wall.id, client_id=door.id, output="epd-2")

    view = clients.get_client_view(door.id)

    assert view.player.state is PlayerState.REPORTING
    assert {o.name: (o.state, o.connected) for o in view.player.outputs} == {
        "epd-0": (PlayerState.REPORTING, True),
        "epd-1": (PlayerState.REPORTING, False),
        "epd-2": (PlayerState.AWAITING_REPORT, None),
    }


# -- the setup flags the server quotes, held to the package -----------------------------

#: Absent until contract 1.3.0, which words the Player's states.
PLAYER_STATES = vocabulary().get("player_states")


@pytest.mark.parametrize("state", sorted(PlayerState))
def test_each_player_states_setup_flag_is_the_one_the_package_states(state):
    """Over the server's states, so it has cases before the package words them; the test below says when it must."""
    if PLAYER_STATES is None:
        # Before contract 1.3.0: the plan's DECISION is the only statement of
        # the flags, and the guard below fails once the package must carry them.
        assert (state in player_state.SETUP) is (state in {"no_token", "awaiting_report"})
        return
    assert (state in player_state.SETUP) is PLAYER_STATES[str(state)]["setup"]


def test_the_package_words_the_player_states_from_1_3_0_and_the_server_names_the_same_ones():
    """Holds the parametrised test above to something: it has no case until the package states the Player's words.

    Before 1.3.0 the package says nothing of a Player's states, so the server's
    keys are the plan's (`build-plan-audit-wave-2b.md` § Goals); from 1.3.0 the
    package must state them, and the same five.
    """
    released = tuple(int(part) for part in importlib.metadata.version("arrt-contract").split(".")[:3])
    if PLAYER_STATES is None:
        assert released < (1, 3, 0), "contract 1.3.0 and later must word the Player's states"
        return
    assert set(PLAYER_STATES) == {str(state) for state in PlayerState}


def test_no_setup_state_is_ever_a_trouble():
    assert not display_state.SETUP & display_state.TROUBLES
    assert not player_state.SETUP & player_state.TROUBLES
