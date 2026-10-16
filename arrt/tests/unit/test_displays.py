"""Displays and label outputs: the records a heartbeat keeps, and the rules for placing walls and labels on them.

`feeds-and-players.md` § Displays are configured, never discovered, and
`labels-and-surfaces.md` § The model are the requirements. Every case goes
through `ClientService`, which HTTP and MCP both bind, and reads back through
`Placements`, which `GET /client`, admission and every display state read.
"""

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from arrt.persistence.catalogue import StorageError
from arrt.persistence.records import Display, LabelOutput
from arrt.programming.access import Admission
from arrt.programming.client_heartbeat import client_heartbeat_path_in
from arrt.programming.display_state import ScreenState
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS
from arrt.services.errors import ServiceError

#: A Frame's identity as its client reads it from the set (`device.duid`).
FRAME = "uuid:8e7b6c2a-1f3d-4e5a-9b0c-2d4e6f8a0b1c"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def report(*outputs: dict, labels: list[dict] | None = None, at: str | None = None) -> dict:
    document: dict = {"reported_at": at or _now(), "outputs": list(outputs)}
    if labels is not None:
        document["label_outputs"] = labels
    return document


def frame(identity: str | None = FRAME, name: str = "frame") -> dict:
    output = {"name": name, "kind": "frame", "connected": True, "screen": None}
    if identity is not None:
        output["identity"] = identity
    return output


def hdmi(name: str = "hdmi-a-1") -> dict:
    return {"name": name, "kind": "framebuffer", "connected": True, "screen": [1920, 1080]}


def panel(name: str = "epd-0") -> dict:
    return {"name": name, "kind": "epaper", "connected": True, "size": [800, 480]}


@pytest.fixture
def clients(services):
    return services.clients


@pytest.fixture
def pi(clients):
    return clients.add_client(name="The Pi in the hall")


@pytest.fixture
def mac(clients):
    return clients.add_client(name="The Mac in the study")


def displays_of(store, client_id):
    return [display for display in store.list_displays() if display.client_id == client_id]


def write_stale(wall_settings, client_id, document):
    """Leave a client's report as one written long enough ago to say nothing about now."""
    old = (datetime.now(UTC) - timedelta(seconds=STALE_AFTER_SECONDS + 60)).isoformat(timespec="seconds")
    client_heartbeat_path_in(wall_settings.art_root, client_id).write_text(json.dumps({**document, "reported_at": old}))


# -- what a heartbeat records ---------------------------------------------------------------


def test_a_heartbeat_records_each_display_keyed_by_identity_or_by_place(clients, store, pi):
    clients.record_heartbeat(pi.id, report(frame(), hdmi("hdmi-a-1"), hdmi("hdmi-a-2")))

    recorded = {display.output: display for display in displays_of(store, pi.id)}
    assert set(recorded) == {"frame", "hdmi-a-1", "hdmi-a-2"}
    assert recorded["frame"].identity == FRAME
    assert recorded["hdmi-a-1"].identity == f"{pi.id}/hdmi-a-1"
    assert (recorded["frame"].kind, recorded["hdmi-a-1"].kind) == ("frame", "framebuffer")


def test_a_repeated_heartbeat_refreshes_and_records_nothing_twice(clients, store, pi):
    clients.record_heartbeat(pi.id, report(frame(), hdmi(), labels=[panel()]))
    first = {display.id: display for display in store.list_displays()}

    clients.record_heartbeat(pi.id, report(frame(), {**hdmi(), "connected": False}, labels=[panel()]))

    assert {display.id: display for display in store.list_displays()} == first
    assert len(store.list_label_outputs()) == 1


def test_a_heartbeat_records_each_label_output(clients, store, pi):
    clients.record_heartbeat(pi.id, report(labels=[panel("epd-0"), panel("epd-1")]))

    assert sorted((label.client_id, label.output, label.wall_id) for label in store.list_label_outputs()) == [
        (pi.id, "epd-0", None),
        (pi.id, "epd-1", None),
    ]
    assert displays_of(store, pi.id) == [], "a client with labels and no display is an ordinary client"


def test_a_frame_first_reported_without_identity_is_renamed_when_it_can_say_and_keeps_its_wall(clients, store, pi, wall_id):
    """The set asleep at first contact, then awake: one display throughout, never a second."""
    clients.record_heartbeat(pi.id, report(frame(identity=None)))
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    [before] = displays_of(store, pi.id)
    assert before.identity == f"{pi.id}/frame"

    clients.record_heartbeat(pi.id, report(frame()))

    [after] = displays_of(store, pi.id)
    assert (after.id, after.identity) == (before.id, FRAME)
    assert [wall.id for wall in clients.walls_of(pi.id)] == [wall_id]


def test_a_frame_that_cannot_be_asked_this_time_stays_the_display_it_was(clients, store, pi, wall_id):
    clients.record_heartbeat(pi.id, report(frame()))
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")

    clients.record_heartbeat(pi.id, report(frame(identity=None)))

    [display] = displays_of(store, pi.id)
    assert display.identity == FRAME
    assert [wall.id for wall in clients.walls_of(pi.id)] == [wall_id]


def test_a_frame_moved_to_another_client_keeps_its_walls(clients, store, services, pi, mac, wall_id, wall_settings):
    clients.record_heartbeat(pi.id, report(frame(), hdmi()))
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    hdmi_wall = services.display.add_wall(name="Office")
    clients.assign_wall(hdmi_wall.id, client_id=pi.id, output="hdmi-a-1")
    # The Pi's configuration no longer names the Frame: it reports only its HDMI.
    clients.record_heartbeat(pi.id, report(hdmi()))

    clients.record_heartbeat(mac.id, report(frame(name="frame-1")))

    moved = next(display for display in store.list_displays() if display.identity == FRAME)
    assert (moved.client_id, moved.output) == (mac.id, "frame-1")
    assert [wall.id for wall in clients.walls_of(mac.id)] == [wall_id]
    assert [wall.id for wall in clients.walls_of(pi.id)] == [hdmi_wall.id], "the HDMI wall stays where it is"
    document = json.loads(clients.client_document(mac.id))
    assert [(entry["wall_id"], entry["output"], entry["display"]) for entry in document["walls"]] == [
        (wall_id, "frame-1", moved.id)
    ]


def test_a_frame_moved_from_a_client_that_went_quiet_moves_too(clients, store, pi, mac, wall_id, wall_settings):
    """A host switched off still has its last report on disk; a stale one claims nothing."""
    clients.record_heartbeat(pi.id, report(frame()))
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    write_stale(wall_settings, pi.id, report(frame()))

    clients.record_heartbeat(mac.id, report(frame()))

    assert [wall.id for wall in clients.walls_of(mac.id)] == [wall_id]
    assert clients.walls_of(pi.id) == []


def test_a_moved_frame_absorbs_the_place_display_the_curator_set_up_and_its_wall(
    clients, store, services, pi, mac, wall_settings
):
    """The Mac was given a wall on 'frame' before it ran; the Frame then arrives there with no wall of its own."""
    clients.record_heartbeat(pi.id, report(frame()))
    write_stale(wall_settings, pi.id, report(frame()))
    study = services.display.add_wall(name="Study")
    clients.assign_wall(study.id, client_id=mac.id, output="frame")

    clients.record_heartbeat(mac.id, report(frame()))

    [display] = displays_of(store, mac.id)
    assert display.identity == FRAME
    assert [wall.id for wall in clients.walls_of(mac.id)] == [study.id]
    assert not [display for display in store.list_displays() if display.identity == f"{mac.id}/frame"]


def test_when_both_have_a_wall_the_moved_frame_keeps_its_own(clients, store, services, pi, mac, wall_id, wall_settings):
    """One screen shows one wall: the identified display's wall wins, the place's wall is unassigned and said."""
    clients.record_heartbeat(pi.id, report(frame()))
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    write_stale(wall_settings, pi.id, report(frame()))
    study = services.display.add_wall(name="Study")
    clients.assign_wall(study.id, client_id=mac.id, output="frame")

    clients.record_heartbeat(mac.id, report(frame()))

    assert [wall.id for wall in clients.walls_of(mac.id)] == [wall_id]
    assert services.display.get_wall(study.id).display_id is None
    assert [display.identity for display in displays_of(store, mac.id)] == [FRAME]


def test_another_device_on_an_output_leaves_the_old_display_with_no_client(clients, store, pi, wall_id):
    clients.record_heartbeat(pi.id, report(frame()))
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")

    clients.record_heartbeat(pi.id, report(frame("uuid:another-set")))

    old = next(display for display in store.list_displays() if display.identity == FRAME)
    assert old.client_id is None
    assert clients.walls_of(pi.id) == []
    assert clients.placement_of(wall_id).display.id == old.id, "the wall stays on its screen, which nobody shows"
    assert clients.placement_of(wall_id).output is None


def test_an_hdmi_output_is_keyed_by_place_and_never_moves(clients, store, pi, mac):
    clients.record_heartbeat(pi.id, report(hdmi()))
    clients.record_heartbeat(mac.id, report(hdmi()))

    assert sorted(display.identity for display in store.list_displays()) == sorted([f"{pi.id}/hdmi-a-1", f"{mac.id}/hdmi-a-1"])


# -- the store's own rules ------------------------------------------------------------------


def _display(display_id: str, identity: str, client_id: str | None, output: str) -> Display:
    return Display(
        id=display_id, identity=identity, client_id=client_id, output=output, kind="frame", first_seen=datetime.now(UTC)
    )


def test_the_store_refuses_a_second_display_with_one_identity(store, pi, mac):
    store.add_display(_display("d1", FRAME, pi.id, "frame"))

    with pytest.raises(StorageError, match="already stored"):
        store.add_display(_display("d2", FRAME, mac.id, "frame"))


def test_the_store_refuses_two_displays_on_one_output_of_a_client_but_not_two_with_no_client(store, pi):
    store.add_display(_display("d1", FRAME, pi.id, "frame"))

    with pytest.raises(StorageError, match="already stored"):
        store.add_display(_display("d2", "uuid:other", pi.id, "frame"))
    store.add_display(_display("d3", "uuid:third", None, "frame"))
    store.add_display(_display("d4", "uuid:fourth", None, "frame"))


def test_the_store_refuses_a_second_label_output_by_one_name_on_a_client(store, pi, mac):
    store.add_label_output(LabelOutput(id="l1", client_id=pi.id, output="epd-0"))

    with pytest.raises(StorageError, match="already stored"):
        store.add_label_output(LabelOutput(id="l2", client_id=pi.id, output="epd-0"))
    store.add_label_output(LabelOutput(id="l3", client_id=mac.id, output="epd-0"))


def test_the_store_lets_a_wall_have_many_label_outputs(store, services, pi, wall_id):
    for index in range(3):
        store.add_label_output(LabelOutput(id=f"l{index}", client_id=pi.id, output=f"epd-{index}", wall_id=wall_id))

    assert len([label for label in store.list_label_outputs() if label.wall_id == wall_id]) == 3


# -- placing walls and labels -----------------------------------------------------------------


def test_a_wall_is_mapped_to_a_display_by_its_id(clients, store, pi, wall_id):
    clients.record_heartbeat(pi.id, report(frame()))
    [display] = displays_of(store, pi.id)

    assignment = clients.assign_display(wall_id, display_id=display.id)

    assert assignment.notice is None
    assert assignment.client.id == pi.id
    assert [wall.id for wall in clients.walls_of(pi.id)] == [wall_id]


def test_a_display_that_shows_a_wall_refuses_another(clients, store, services, pi, wall_id):
    clients.record_heartbeat(pi.id, report(frame()))
    [display] = displays_of(store, pi.id)
    clients.assign_display(wall_id, display_id=display.id)
    study = services.display.add_wall(name="Study")

    with pytest.raises(ServiceError, match="output 'frame' already shows"):
        clients.assign_display(study.id, display_id=display.id)


def test_a_display_no_client_reports_is_assigned_with_a_notice_and_shown_by_nobody(clients, store, pi, wall_id):
    store.add_display(_display("d-orphan", FRAME, None, "frame"))

    assignment = clients.assign_display(wall_id, display_id="d-orphan")

    assert "No client reports the display" in assignment.notice
    assert clients.placement_of(wall_id).shown_by is None


def test_an_unknown_display_is_refused_by_id(clients, wall_id):
    with pytest.raises(ServiceError, match="No display with id 'nothing'"):
        clients.assign_display(wall_id, display_id="nothing")


def test_a_wall_takes_labels_on_any_clients_and_each_client_is_told_its_own(clients, services, pi, mac, wall_id):
    clients.record_heartbeat(mac.id, report(labels=[panel()]))
    on_pi = clients.add_label(wall_id, client_id=pi.id, output="epd-0")
    on_mac = clients.add_label(wall_id, client_id=mac.id, output="epd-0")

    assert "has not reported its outputs yet" in on_pi.notice
    assert on_mac.notice is None
    assert sorted(label.client_id for label in clients.placement_of(wall_id).labels) == sorted([pi.id, mac.id])
    assert json.loads(clients.client_document(mac.id))["labels"] == [
        {"label_id": on_mac.label.id, "output": "epd-0", "wall_id": wall_id}
    ]
    assert json.loads(clients.client_document(pi.id))["labels"] == [
        {"label_id": on_pi.label.id, "output": "epd-0", "wall_id": wall_id}
    ]


def test_a_label_output_not_reported_by_that_name_is_mapped_with_a_notice(clients, pi, wall_id):
    clients.record_heartbeat(pi.id, report(labels=[panel("epd-0")]))

    assignment = clients.add_label(wall_id, client_id=pi.id, output="epd-9")

    assert "'epd-9' is not among them" in assignment.notice


def test_a_label_output_captions_at_most_one_wall(clients, services, pi, wall_id):
    clients.add_label(wall_id, client_id=pi.id, output="epd-0")
    study = services.display.add_wall(name="Study")

    with pytest.raises(ServiceError, match="already captions"):
        clients.add_label(study.id, client_id=pi.id, output="epd-0")
    again = clients.add_label(wall_id, client_id=pi.id, output="epd-0")
    assert again.label.wall_id == wall_id, "mapping it to the wall it captions is not an error"


def test_removing_a_label_leaves_it_recorded_captioning_nothing(clients, services, store, pi, wall_id):
    label = clients.add_label(wall_id, client_id=pi.id, output="epd-0").label
    study = services.display.add_wall(name="Study")

    with pytest.raises(ServiceError, match="does not caption Study"):
        clients.remove_label(study.id, label_id=label.id)
    clients.remove_label(wall_id, label_id=label.id)
    clients.remove_label(wall_id, label_id=label.id)

    assert store.get_label_output(label.id).wall_id is None
    assert json.loads(clients.client_document(pi.id))["labels"] == []
    with pytest.raises(ServiceError, match="No label output with id 'nothing'"):
        clients.remove_label(wall_id, label_id="nothing")


def test_removing_a_client_takes_its_label_outputs_with_it(clients, store, pi, wall_id):
    clients.add_label(wall_id, client_id=pi.id, output="epd-0")

    clients.remove_client(pi.id)

    assert store.list_label_outputs() == []


# -- two clients reporting one display --------------------------------------------------------


@pytest.fixture
def fault(clients, pi, mac, wall_id):
    """The Frame configured on both hosts at once, its wall placed while only the Pi reported it."""
    clients.record_heartbeat(pi.id, report(frame()))
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    clients.record_heartbeat(mac.id, report(frame()))


def test_two_clients_reporting_one_display_show_its_wall_to_neither(clients, services, pi, mac, wall_id, fault):
    assert clients.walls_of(pi.id) == []
    assert clients.walls_of(mac.id) == []
    assert json.loads(clients.client_document(pi.id))["walls"] == []
    placement = clients.placement_of(wall_id)
    assert placement.shown_by is None
    assert [client.name for client in placement.fault.clients] == ["The Mac in the study", "The Pi in the hall"]
    assert services.display.get_wall_view(wall_id).display_state.state is ScreenState.UNASSIGNED


def test_the_fault_is_named_on_both_clients_with_both_names(clients, pi, mac, wall_id, fault):
    for client_id in (pi.id, mac.id):
        [named] = clients.get_client_view(client_id).faults
        assert named.identity == FRAME
        assert named.wall.id == wall_id
        sentence = named.describe()
        assert "The Mac in the study and The Pi in the hall" in sentence
        assert "neither shows" in sentence


def test_a_fault_admits_neither_client_to_the_wall(services, pi, mac, wall_id, fault):
    pi_token = services.access.issue(pi.id).token
    mac_token = services.access.issue(mac.id).token

    assert services.access.admit(wall_id, pi_token) is Admission.NOT_ITS_WALL
    assert services.access.admit(wall_id, mac_token) is Admission.NOT_ITS_WALL


def test_the_display_stays_with_its_client_while_in_fault(clients, store, pi, wall_id, fault):
    [display] = [display for display in store.list_displays() if display.identity == FRAME]
    assert display.client_id == pi.id, "no client arbitrates: the record does not flap between them"


def test_the_fault_ends_when_one_client_stops_reporting(clients, pi, mac, wall_id, wall_settings, fault):
    clients.record_heartbeat(mac.id, report(hdmi()))

    assert [wall.id for wall in clients.walls_of(pi.id)] == [wall_id]
    assert clients.get_client_view(pi.id).faults == []


def test_the_fault_ends_when_one_client_goes_quiet_and_the_other_takes_the_display(
    clients, pi, mac, wall_id, wall_settings, fault
):
    write_stale(wall_settings, pi.id, report(frame()))
    clients.record_heartbeat(mac.id, report(frame()))

    assert [wall.id for wall in clients.walls_of(mac.id)] == [wall_id]
    assert clients.walls_of(pi.id) == []


def test_a_fault_is_said_once_per_episode(clients, pi, mac, caplog):
    clients.record_heartbeat(pi.id, report(frame()))
    with caplog.at_level(logging.WARNING, logger="arrt.programming.clients"):
        for _ in range(3):
            clients.record_heartbeat(mac.id, report(frame()))

    said = [record for record in caplog.records if "reports the display" in record.getMessage()]
    assert len(said) == 1
    assert "'The Mac in the study'" in said[0].getMessage()
    assert "'The Pi in the hall'" in said[0].getMessage()


def test_assigning_onto_a_display_in_fault_says_so(clients, store, services, pi, mac, wall_id, fault):
    [display] = [display for display in store.list_displays() if display.identity == FRAME]
    study = services.display.add_wall(name="Study")
    clients.unassign_wall(wall_id)

    assignment = clients.assign_display(study.id, display_id=display.id)

    assert "both report the display" in assignment.notice


# -- one answer for every reader ---------------------------------------------------------------


@pytest.mark.parametrize("shown", [True, False])
def test_walls_and_admission_and_the_client_document_agree_on_who_shows_a_wall(services, clients, pi, wall_id, shown):
    clients.record_heartbeat(pi.id, report(frame()))
    if shown:
        clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    token = services.access.issue(pi.id).token

    listed = [entry["wall_id"] for entry in json.loads(clients.client_document(pi.id))["walls"]]
    admitted = services.access.admit(wall_id, token) is Admission.ADMITTED
    unassigned = services.display.get_wall_view(wall_id).display_state.state is ScreenState.UNASSIGNED

    assert (wall_id in listed, admitted, not unassigned) == (shown, shown, shown)


def test_a_wall_whose_display_lost_its_client_is_unassigned_on_walls(clients, store, services, pi, wall_id):
    clients.record_heartbeat(pi.id, report(frame()))
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    [display] = displays_of(store, pi.id)
    store.update_display(replace(display, client_id=None))

    assert services.display.get_wall_view(wall_id).display_state.state is ScreenState.UNASSIGNED


# -- reported screens go with their display -------------------------------------------


def test_removing_a_client_whose_display_reported_a_screen_takes_the_sizes_with_it(clients, store, pi, wall_id):
    clients.assign_wall(wall_id, client_id=pi.id, output="hdmi-a-1")
    display_id = store.get_wall(wall_id).display_id
    store.record_screen(display_id, 3840, 2160, datetime.now(UTC))

    clients.remove_client(pi.id)

    assert store.get_display(display_id) is None
    assert store.reported_screens(display_id) == []


def test_a_place_display_with_a_reported_screen_folds_into_the_frame(clients, store, services, pi, mac, wall_settings):
    clients.record_heartbeat(pi.id, report(frame()))
    write_stale(wall_settings, pi.id, report(frame()))
    study = services.display.add_wall(name="Study")
    clients.assign_wall(study.id, client_id=mac.id, output="frame")
    place = store.get_wall(study.id).display_id
    store.record_screen(place, 3840, 2160, datetime.now(UTC))

    clients.record_heartbeat(mac.id, report(frame()))

    assert store.get_display(place) is None
    assert store.reported_screens(place) == []
