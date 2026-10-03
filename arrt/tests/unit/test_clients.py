"""The client service and the access service: every operation, through the real store.

`clients.md` is the requirement. What is held here is what both surfaces rely on:
HTTP binds these today and MCP binds them next, so a rule tested only through
one surface would be a rule the other could miss.
"""

import hashlib
import json
import logging
from dataclasses import replace

import pytest

from arrt.persistence.catalogue import StorageError
from arrt.programming.access import REFUSAL_LOG_INTERVAL_SECONDS, Admission, PlayerAccess
from arrt.programming.client_heartbeat import client_heartbeat_path_in
from arrt.services.errors import ServiceError

_REPORT = {
    "reported_at": "2026-10-02T14:00:05+00:00",
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "frame", "kind": "frame", "connected": False, "screen": None},
    ],
}


@pytest.fixture
def clients(services):
    return services.clients


@pytest.fixture
def access(services):
    return services.access


@pytest.fixture
def pi(clients):
    return clients.add_client(name="The Pi in the hall")


# -- recording clients ------------------------------------------------------------------


def test_a_client_is_recorded_with_no_token_and_no_walls(clients, pi):
    view = clients.get_client_view(pi.id)

    assert view.client.name == "The Pi in the hall"
    assert (view.client.token_verifier, view.client.token_issued_at) == (None, None)
    assert view.walls == []
    assert view.heartbeat.absent


def test_a_client_name_is_trimmed_and_must_not_be_blank(clients):
    assert clients.add_client(name="  The Pi  ").name == "The Pi"
    with pytest.raises(ServiceError, match="name cannot be empty"):
        clients.add_client(name="   ")


def test_two_clients_cannot_share_a_name(clients, pi):
    with pytest.raises(ServiceError, match="The Pi in the hall"):
        clients.add_client(name="The Pi in the hall")


def test_renaming_keeps_the_token_and_the_walls(clients, access, pi, wall_id):
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    token = access.issue(pi.id).token

    renamed = clients.rename_client(pi.id, name="The hall Pi")

    assert renamed.name == "The hall Pi"
    assert access.identify(token).name == "The hall Pi"
    assert [wall.id for wall in clients.walls_of(pi.id)] == [wall_id]


def test_renaming_onto_another_clients_name_is_refused(clients, pi):
    clients.add_client(name="The Pi in the study")

    with pytest.raises(ServiceError, match="The Pi in the study"):
        clients.rename_client(pi.id, name="The Pi in the study")


def test_listing_names_every_client_in_name_order(clients, pi):
    clients.add_client(name="A spare Pi")

    assert [view.client.name for view in clients.list_clients()] == ["A spare Pi", "The Pi in the hall"]


@pytest.mark.parametrize("operation", ["get_client", "get_client_view", "remove_client", "walls_of"])
def test_an_unknown_client_is_refused_by_id(clients, operation):
    with pytest.raises(ServiceError, match="No client with id 'nobody'"):
        getattr(clients, operation)("nobody")


# -- removing a client ------------------------------------------------------------------


def test_removing_a_client_unassigns_its_walls_and_keeps_their_themes(services, clients, pi, wall_id):
    theme = services.display.add_theme(name="Late night")
    services.display.activate_theme(theme.id, wall_id=wall_id)
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    other = clients.add_client(name="The Pi in the study")
    study = services.display.add_wall(name="Study")
    clients.assign_wall(study.id, client_id=other.id, output="frame")

    released = clients.remove_client(pi.id)

    assert [wall.id for wall in released] == [wall_id]
    wall = services.display.get_wall(wall_id)
    assert (wall.client_id, wall.output) == (None, None)
    assert services.display.hanging_on(wall_id).id == theme.id
    assert services.display.get_wall(study.id).client_id == other.id, "another client's wall is untouched"
    assert [view.client.name for view in clients.list_clients()] == ["The Pi in the study"]


def test_removing_a_client_stops_its_token_and_drops_its_report(clients, access, pi, wall_settings):
    token = access.issue(pi.id).token
    clients.record_heartbeat(pi.id, _REPORT)
    path = client_heartbeat_path_in(wall_settings.art_root, pi.id)
    assert path.exists()

    clients.remove_client(pi.id)

    assert access.identify(token) is None
    assert not path.exists()


# -- tokens -----------------------------------------------------------------------------


def test_a_token_is_stored_only_as_its_sha256(access, store, pi):
    issued = access.issue(pi.id)

    stored = store.get_client(pi.id)
    assert stored.token_verifier == hashlib.sha256(issued.token.encode()).hexdigest()
    assert stored.token_issued_at == issued.issued_at
    assert issued.client_id == pi.id
    assert len(issued.token) >= 43, "32 random bytes, url-safe"


def test_rotating_stops_the_old_token_at_once(access, pi):
    first = access.issue(pi.id).token
    second = access.issue(pi.id).token

    assert first != second
    assert access.identify(first) is None
    assert access.identify(second).id == pi.id


def test_issuing_for_an_unknown_client_is_refused(access):
    with pytest.raises(ServiceError, match="No client with id 'nobody'"):
        access.issue("nobody")


def test_issuing_logs_the_client_and_never_the_token(access, pi, caplog):
    with caplog.at_level(logging.DEBUG):
        token = access.issue(pi.id).token

    journal = "\n".join(record.getMessage() for record in caplog.records)
    assert "The Pi in the hall" in journal
    assert token not in journal


# -- admission --------------------------------------------------------------------------


def test_a_client_is_admitted_to_its_own_walls_only(services, clients, access, pi, wall_id):
    study = services.display.add_wall(name="Study")
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    token = access.issue(pi.id).token

    assert access.admit(wall_id, token) is Admission.ADMITTED
    assert access.admit(study.id, token) is Admission.NOT_ITS_WALL
    assert access.admit("no-such-wall", token) is Admission.NOT_ITS_WALL
    assert access.admit(wall_id, "not-a-token") is Admission.UNKNOWN
    assert access.admit(wall_id, None) is Admission.UNKNOWN
    assert access.admit(wall_id, "") is Admission.UNKNOWN


def test_media_admits_any_client_with_a_token_whatever_it_drives(clients, access, pi):
    assert access.admit_any(access.issue(pi.id).token) is Admission.ADMITTED
    assert access.admit_any("not-a-token") is Admission.UNKNOWN
    assert access.admit_any(None) is Admission.UNKNOWN


def test_a_client_with_no_token_is_identified_by_no_presented_value(clients, access, pi):
    clients.add_client(name="Another with no token")

    for presented in (None, "", "None", hashlib.sha256(b"").hexdigest()):
        assert access.identify(presented) is None


def test_refusals_are_logged_once_per_subject_per_interval(store, clients, pi, wall_id, caplog):
    now = [0.0]
    access = PlayerAccess(store, clock=lambda: now[0])
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    other = clients.add_client(name="The Pi in the study")
    other_token = access.issue(other.id).token

    with caplog.at_level(logging.WARNING, logger="arrt.programming.access"):
        for _ in range(3):
            access.admit(wall_id, "stale")
            access.admit(wall_id, other_token)
        now[0] = REFUSAL_LOG_INTERVAL_SECONDS + 1
        access.admit(wall_id, "stale")

    messages = [record.getMessage() for record in caplog.records]
    assert sum("an unknown client" in message for message in messages) == 2
    assert sum("'The Pi in the study'" in message for message in messages) == 1
    assert not any("stale" in message or other_token in message for message in messages)


# -- assignment -------------------------------------------------------------------------


def test_assigning_records_the_client_and_the_output_on_the_wall(services, clients, pi, wall_id):
    assignment = clients.assign_wall(wall_id, client_id=pi.id, output="  hdmi-a-1 ")

    wall = services.display.get_wall(wall_id)
    assert (wall.client_id, wall.output) == (pi.id, "hdmi-a-1")
    assert assignment.wall == wall
    assert assignment.client.id == pi.id


@pytest.mark.parametrize(
    ("report", "notice"),
    [
        (None, "has not reported its outputs yet"),
        (_REPORT, None),
        ({**_REPORT, "outputs": [_REPORT["outputs"][1]]}, "'hdmi-a-1' is not among them"),
    ],
    ids=["never-reported", "reported-it", "reported-others"],
)
def test_an_output_is_checked_against_the_last_report_and_assigned_either_way(clients, pi, wall_id, report, notice):
    if report is not None:
        clients.record_heartbeat(pi.id, report)

    assignment = clients.assign_wall(wall_id, client_id=pi.id, output="hdmi-a-1")

    assert assignment.wall.output == "hdmi-a-1"
    if notice is None:
        assert assignment.notice is None
    else:
        assert notice in assignment.notice


def test_an_unreadable_report_is_treated_as_no_report(clients, pi, wall_id, wall_settings):
    client_heartbeat_path_in(wall_settings.art_root, pi.id).write_text("{not json", encoding="utf-8")

    assert "has not reported its outputs yet" in clients.assign_wall(wall_id, client_id=pi.id, output="frame").notice


def test_an_output_name_must_not_be_blank(clients, pi, wall_id):
    with pytest.raises(ServiceError, match="output cannot be empty"):
        clients.assign_wall(wall_id, client_id=pi.id, output="  ")


def test_assigning_an_unknown_wall_or_client_is_refused(clients, pi, wall_id):
    with pytest.raises(ServiceError, match="No wall with id 'nowhere'"):
        clients.assign_wall("nowhere", client_id=pi.id, output="frame")
    with pytest.raises(ServiceError, match="No client with id 'nobody'"):
        clients.assign_wall(wall_id, client_id="nobody", output="frame")


def test_one_output_of_one_client_shows_one_wall(services, clients, pi, wall_id):
    study = services.display.add_wall(name="Study")
    clients.assign_wall(wall_id, client_id=pi.id, output="hdmi-a-1")

    with pytest.raises(ServiceError, match="output 'hdmi-a-1' already shows"):
        clients.assign_wall(study.id, client_id=pi.id, output="hdmi-a-1")

    other = clients.add_client(name="The Pi in the study")
    clients.assign_wall(study.id, client_id=other.id, output="hdmi-a-1")
    clients.assign_wall(wall_id, client_id=pi.id, output="hdmi-a-1")
    assert services.display.get_wall(study.id).client_id == other.id


def test_the_store_refuses_a_second_wall_on_one_output_even_past_the_service(services, store, clients, pi, wall_id):
    """The partial unique index is the weaker statement of the same rule, for a path that forgets it."""
    study = services.display.add_wall(name="Study")
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")

    with pytest.raises(StorageError, match="already stored"):
        store.update_wall(replace(store.get_wall(study.id), client_id=pi.id, output="frame"))


def test_assigning_to_another_client_moves_the_wall(services, clients, pi, wall_id):
    other = clients.add_client(name="The Pi in the study")
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")

    clients.assign_wall(wall_id, client_id=other.id, output="hdmi-a-1")

    assert clients.walls_of(pi.id) == []
    assert [(wall.id, wall.output) for wall in clients.walls_of(other.id)] == [(wall_id, "hdmi-a-1")]


def test_unassigning_clears_both_fields_and_is_idempotent(services, clients, pi, wall_id):
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")

    clients.unassign_wall(wall_id)
    again = clients.unassign_wall(wall_id)

    assert (again.client_id, again.output) == (None, None)
    wall = services.display.get_wall(wall_id)
    assert (wall.client_id, wall.output) == (None, None)
    with pytest.raises(ServiceError, match="No wall with id 'nowhere'"):
        clients.unassign_wall("nowhere")


# -- what a client reads and writes -----------------------------------------------------


def test_the_client_document_lists_only_this_clients_walls_with_their_outputs(services, clients, pi, wall_id):
    study = services.display.add_wall(name="Study")
    other = clients.add_client(name="The Pi in the study")
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    clients.assign_wall(study.id, client_id=other.id, output="hdmi-a-1")

    document = json.loads(clients.client_document(pi.id))

    assert document == {
        "client_id": pi.id,
        "name": "The Pi in the hall",
        "walls": [{"wall_id": wall_id, "name": services.display.get_wall(wall_id).name, "output": "frame"}],
    }


def test_the_client_document_is_the_same_bytes_until_something_changes(clients, pi, wall_id):
    first = clients.client_document(pi.id)
    assert clients.client_document(pi.id) == first

    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    assert clients.client_document(pi.id) != first


def test_a_report_is_kept_and_read_back_as_outputs(clients, pi):
    clients.record_heartbeat(pi.id, _REPORT)

    reading = clients.read_heartbeat(pi.id)
    assert reading.problem is None
    assert [(output.name, output.kind, output.connected, output.screen) for output in reading.outputs] == [
        ("hdmi-a-1", "framebuffer", True, (1920, 1080)),
        ("frame", "frame", False, None),
    ]
    assert reading.output_names() == {"hdmi-a-1", "frame"}


def test_a_report_this_server_cannot_read_is_refused_and_not_written(clients, pi, wall_settings):
    with pytest.raises(ServiceError, match="'kind' is one of frame, framebuffer"):
        clients.record_heartbeat(pi.id, {**_REPORT, "outputs": [{**_REPORT["outputs"][0], "kind": "hdmi"}]})

    assert not client_heartbeat_path_in(wall_settings.art_root, pi.id).exists()


def test_a_report_from_an_unknown_client_is_refused(clients):
    with pytest.raises(ServiceError, match="No client with id 'nobody'"):
        clients.record_heartbeat("nobody", _REPORT)
