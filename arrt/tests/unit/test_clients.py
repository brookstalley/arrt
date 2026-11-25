"""The client service and the access service: every operation, through the real store.

`clients.md` is the requirement. What is held here is what both surfaces rely on:
HTTP and MCP both bind these, so a rule tested only through
one surface would be a rule the other could miss.
"""

import hashlib
import json
import logging
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from arrt.persistence.catalogue import StorageError
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.programming.access import REFUSAL_LOG_INTERVAL_SECONDS, Admission, PlayerAccess
from arrt.programming.client_heartbeat import MAX_OUTPUTS, client_heartbeat_path_in
from arrt.programming.clients import Placements, refused_reports_of
from arrt.programming.display_state import ScreenState
from arrt.programming.player_state import PlayerState
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


def test_removing_a_client_unassigns_its_walls_and_keeps_their_themes(services, store, clients, pi, wall_id):
    theme = services.display.add_theme(name="Late night")
    services.display.activate_theme(theme.id, wall_id=wall_id)
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    other = clients.add_client(name="The Pi in the study")
    study = services.display.add_wall(name="Study")
    clients.assign_wall(study.id, client_id=other.id, output="frame")

    released = clients.remove_client(pi.id)

    assert [wall.id for wall in released] == [wall_id]
    wall = services.display.get_wall(wall_id)
    assert wall.display_id is None
    assert services.display.hanging_on(wall_id).id == theme.id
    assert clients.placement_of(study.id).client.id == other.id, "another client's wall is untouched"
    assert [display.client_id for display in store.list_displays()] == [other.id], "its displays go with it"
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
    access = PlayerAccess(store, clients.placements, clock=lambda: now[0])
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


def test_a_refusal_and_a_token_issued_each_carry_an_event_and_never_the_token(store, clients, pi, wall_id, caplog):
    """Every line a dashboard reads carries an event field (`observability-strategy.md`); the token is in no field."""
    access = PlayerAccess(store, clients.placements, clock=lambda: 0.0)
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    other = clients.add_client(name="The Pi in the study")

    with caplog.at_level(logging.INFO, logger="arrt.programming.access"):
        token = access.issue(other.id).token
        access.admit(wall_id, "stale")
        access.admit(wall_id, token)

    lines = [record for record in caplog.records if record.name == "arrt.programming.access"]
    assert [getattr(record, "event", None) for record in lines] == [
        "client.token_issued",
        "client.request_refused",
        "client.request_refused",
    ]
    assert lines[0].client_id == other.id
    assert [record.subject for record in lines[1:]] == ["an unknown client", "client 'The Pi in the study'"]
    for record in lines:
        assert token not in repr(record.__dict__), "the token reached a log record"


# -- assignment -------------------------------------------------------------------------


def test_assigning_places_the_wall_on_the_display_on_that_output(services, clients, pi, wall_id):
    assignment = clients.assign_wall(wall_id, client_id=pi.id, output="  hdmi-a-1 ")

    wall = services.display.get_wall(wall_id)
    placement = clients.placement_of(wall_id)
    assert (placement.client.id, placement.output) == (pi.id, "hdmi-a-1")
    assert placement.display.identity == f"{pi.id}/hdmi-a-1", "an output nothing has named is keyed by its place"
    assert assignment.wall == wall
    assert assignment.display == placement.display
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
def test_an_output_is_checked_against_the_last_report_and_assigned_either_way(clients, access, pi, wall_id, report, notice):
    if report is not None:
        # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
        access.issue(pi.id)
        clients.record_heartbeat(pi.id, report)

    assignment = clients.assign_wall(wall_id, client_id=pi.id, output="hdmi-a-1")

    assert assignment.display.output == "hdmi-a-1"
    if notice is None:
        assert assignment.notice is None
    else:
        assert notice in assignment.notice


def test_an_unreadable_report_is_treated_as_no_report(clients, pi, wall_id, wall_settings):
    client_heartbeat_path_in(wall_settings.art_root, pi.id).write_text("{not json", encoding="utf-8")

    assert "has not reported its outputs yet" in clients.assign_wall(wall_id, client_id=pi.id, output="frame").notice


@pytest.mark.parametrize(
    ("report", "said"),
    [
        (None, "The Pi in the hall has not reported its screens yet, so there is no screen to show The wall on. Start"),
        ({**_REPORT, "outputs": []}, "The Pi in the hall reports no screens, so there is none to show The wall on."),
        (_REPORT, "Choose which of The Pi in the hall's screens shows The wall: it reported 'frame', 'hdmi-a-1'."),
    ],
)
def test_a_blank_output_is_refused_saying_what_the_player_has_reported(clients, access, pi, wall_id, report, said):
    """The UX walk's finding 2: "output cannot be empty" named a validator, not that the Player had not reported.

    Rewritten from a match on that sentence, which the plan replaced: each case
    is still refused and assigns nothing, and now says which of the three it is.
    """
    if report is not None:
        # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
        access.issue(pi.id)
        clients.record_heartbeat(pi.id, report)
    with pytest.raises(ServiceError) as refused:
        clients.assign_wall(wall_id, client_id=pi.id, output="  ")

    assert str(refused.value).startswith(said)
    assert clients.placement_of(wall_id).display is None


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
    assert clients.placement_of(study.id).client.id == other.id


def test_the_store_refuses_a_second_wall_on_one_display_even_past_the_service(services, store, clients, pi, wall_id):
    """The partial unique index is the weaker statement of the same rule, for a path that forgets it."""
    study = services.display.add_wall(name="Study")
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")

    with pytest.raises(StorageError, match="already stored"):
        store.update_wall(replace(store.get_wall(study.id), display_id=store.get_wall(wall_id).display_id))


def test_assigning_to_another_client_moves_the_wall(services, clients, pi, wall_id):
    other = clients.add_client(name="The Pi in the study")
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")

    clients.assign_wall(wall_id, client_id=other.id, output="hdmi-a-1")

    assert clients.walls_of(pi.id) == []
    assert [wall.id for wall in clients.walls_of(other.id)] == [wall_id]
    assert clients.placement_of(wall_id).output == "hdmi-a-1"


def test_unassigning_clears_both_fields_and_is_idempotent(services, clients, pi, wall_id):
    clients.assign_wall(wall_id, client_id=pi.id, output="frame")

    clients.unassign_wall(wall_id)
    again = clients.unassign_wall(wall_id)

    assert again.display_id is None
    assert services.display.get_wall(wall_id).display_id is None
    assert clients.placement_of(wall_id).client is None
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
        "walls": [
            {
                "wall_id": wall_id,
                "name": services.display.get_wall(wall_id).name,
                "output": "frame",
                "display": services.display.get_wall(wall_id).display_id,
            }
        ],
        "labels": [],
    }


def test_the_client_document_is_the_same_bytes_until_something_changes(clients, pi, wall_id):
    first = clients.client_document(pi.id)
    assert clients.client_document(pi.id) == first

    clients.assign_wall(wall_id, client_id=pi.id, output="frame")
    assert clients.client_document(pi.id) != first


def test_a_report_is_kept_and_read_back_as_outputs(clients, access, pi):
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    access.issue(pi.id)
    clients.record_heartbeat(pi.id, _REPORT)

    reading = clients.read_heartbeat(pi.id)
    assert reading.problem is None
    assert [(output.name, output.kind, output.connected, output.screen) for output in reading.outputs] == [
        ("hdmi-a-1", "framebuffer", True, (1920, 1080)),
        ("frame", "frame", False, None),
    ]
    assert reading.output_names() == {"hdmi-a-1", "frame"}


def test_a_report_this_server_cannot_read_is_refused_and_not_written(clients, access, pi, wall_settings):
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    access.issue(pi.id)
    with pytest.raises(ServiceError, match="'kind' is one of frame, framebuffer"):
        clients.record_heartbeat(pi.id, {**_REPORT, "outputs": [{**_REPORT["outputs"][0], "kind": "hdmi"}]})

    assert not client_heartbeat_path_in(wall_settings.art_root, pi.id).exists()


def _screens(count):
    return [{"name": f"hdmi-a-{n}", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]} for n in range(count)]


def _panels(count):
    return [{"name": f"panel-{n}", "kind": "epaper", "connected": True, "size": [800, 480]} for n in range(count)]


@pytest.mark.parametrize(
    ("key", "many", "word"),
    [("outputs", _screens, "outputs"), ("label_outputs", _panels, "label outputs")],
    ids=["outputs", "labels"],
)
def test_a_report_of_more_outputs_than_the_cap_is_refused_by_name_and_keeps_nothing(
    clients, pi, wall_settings, services, key, many, word
):
    """Every output a report names can become a row the server keeps; one report may name at most the cap."""
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    services.access.issue(pi.id)
    displays_before = len(services.clients.placements.survey().displays)

    with pytest.raises(ServiceError, match=rf"at most {MAX_OUTPUTS} {word}, and this report carries {MAX_OUTPUTS + 1}\."):
        clients.record_heartbeat(pi.id, {**_REPORT, key: many(MAX_OUTPUTS + 1)})

    assert not client_heartbeat_path_in(wall_settings.art_root, pi.id).exists()
    assert len(services.clients.placements.survey().displays) == displays_before
    # The cap itself is a report a Player may send.
    clients.record_heartbeat(pi.id, {**_REPORT, key: many(MAX_OUTPUTS)})
    assert client_heartbeat_path_in(wall_settings.art_root, pi.id).exists()


def test_a_report_from_an_unknown_client_is_refused(clients):
    with pytest.raises(ServiceError, match="No client with id 'nobody'"):
        clients.record_heartbeat("nobody", _REPORT)


# -- what the health reading makes of Players (the one health model) ---------------------


def test_a_display_two_players_report_is_a_trouble_though_its_wall_reads_unassigned(services, clients, wall_id):
    """`unassigned` is a setup step, but the fault behind this one is not: the health reading names it."""
    now = datetime.now(UTC).isoformat()
    frame = {"name": "frame", "kind": "frame", "connected": True, "screen": [3840, 2160], "identity": "uuid:the-one-frame"}
    hall = clients.add_client(name="The Pi in the hall")
    study = clients.add_client(name="The Pi in the study")
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    services.access.issue(hall.id)
    services.access.issue(study.id)
    clients.record_heartbeat(hall.id, {"reported_at": now, "outputs": [frame]})
    clients.assign_wall(wall_id, client_id=hall.id, output="frame")
    clients.record_heartbeat(study.id, {"reported_at": now, "outputs": [frame]})

    reading = services.health.observe()

    assert [seen.state.state for seen in reading.walls if seen.wall.id == wall_id] == [ScreenState.UNASSIGNED]
    assert [(t.about, t.subject, t.words) for t in reading.troubles() if t.about in {"wall", "display_fault"}] == [
        ("display_fault", "uuid:the-one-frame", "The Pi in the hall and The Pi in the study both report one display")
    ]
    # Nor is the wall a setup step: "has no Player yet" would be false of it.
    assert wall_id not in {step.subject for step in reading.setup_steps()}


def test_players_being_set_up_are_on_the_health_reading_and_not_among_its_troubles(services, clients, pi, access):
    """No token, then a token and no report: both setup states, so neither is counted."""
    spare = clients.add_client(name="A spare Pi")
    access.issue(pi.id)

    reading = services.health.observe()

    assert {view.client.id: view.player.state for view in reading.players} == {
        pi.id: PlayerState.AWAITING_REPORT,
        spare.id: PlayerState.NO_TOKEN,
    }
    assert not [t for t in reading.troubles() if t.about == "player"]


def test_a_player_whose_report_cannot_be_read_is_a_trouble(services, clients, pi, access, wall_settings):
    access.issue(pi.id)
    client_heartbeat_path_in(wall_settings.art_root, pi.id).write_text("{ not json", encoding="utf-8")

    troubles = [t for t in services.health.observe().troubles() if t.about == "player"]

    assert [(t.subject, t.state, t.words) for t in troubles] == [
        (pi.id, "report_unreadable", "The Pi in the hall's report cannot be read")
    ]


# -- a Player whose reports are refused ----------------------------------------------------

#: A report the server refuses, and the words it refuses it in (`client_heartbeat.problem_with`).
_REFUSED = {**_REPORT, "outputs": [{**_REPORT["outputs"][0], "kind": "hdmi"}]}
_REFUSED_PROBLEM = "output 0: 'kind' is one of frame, framebuffer."


def _refuse(clients, client_id, document=_REFUSED):
    with pytest.raises(ServiceError):
        clients.record_heartbeat(client_id, document)


def _now_report():
    return {**_REPORT, "reported_at": datetime.now(UTC).isoformat()}


def test_a_player_whose_first_report_is_refused_reads_unreadable_with_the_servers_words(services, clients, pi, access):
    """Not `awaiting_report`, a setup step: it is talking, and what it says cannot be read, so it is a trouble."""
    access.issue(pi.id)
    _refuse(clients, pi.id)

    view = clients.get_client_view(pi.id)
    assert view.player.state is PlayerState.REPORT_UNREADABLE
    assert view.heartbeat.problem == _REFUSED_PROBLEM
    assert view.heartbeat.describe() == f"Its last report could not be read: {_REFUSED_PROBLEM}"
    reading = services.health.observe()
    assert {each.client.id: each.player.state for each in reading.players} == {pi.id: PlayerState.REPORT_UNREADABLE}
    assert [(t.subject, t.state) for t in reading.troubles() if t.about == "player"] == [(pi.id, "report_unreadable")]
    assert pi.id not in {step.subject for step in reading.setup_steps()}


def test_a_refusal_after_an_accepted_report_reads_unreadable_and_keeps_the_settings_page(clients, pi, access):
    """The file still holds the last report accepted; the Player's reading is the refusal, but its settings page stays."""
    access.issue(pi.id)
    clients.record_heartbeat(pi.id, {**_now_report(), "settings_url": "http://player.example:8080/"})
    assert clients.get_client_view(pi.id).player.state is PlayerState.REPORTING

    _refuse(clients, pi.id)

    view = clients.get_client_view(pi.id)
    assert view.player.state is PlayerState.REPORT_UNREADABLE
    assert view.heartbeat.problem == _REFUSED_PROBLEM
    assert view.heartbeat.outputs == ()
    assert view.heartbeat.settings_url == "http://player.example:8080/"
    # The outputs recorded for it read as its state, never as reported now.
    assert {(output.name, output.state, output.connected) for output in view.player.outputs} == {
        ("hdmi-a-1", PlayerState.REPORT_UNREADABLE, None),
        ("frame", PlayerState.REPORT_UNREADABLE, None),
    }


def test_an_accepted_report_clears_a_refusal(services, clients, pi, access):
    access.issue(pi.id)
    _refuse(clients, pi.id)
    clients.record_heartbeat(pi.id, _now_report())

    view = clients.get_client_view(pi.id)
    assert view.player.state is PlayerState.REPORTING
    assert view.heartbeat.problem is None
    assert not [t for t in services.health.observe().troubles() if t.about == "player"]


def test_ten_identical_refusals_write_one_journal_line_and_another_problem_writes_one_more(clients, pi, access, caplog):
    """A Player resending a refused report every cycle writes one line, not one a cycle; the line carries its event."""
    access.issue(pi.id)
    with caplog.at_level(logging.WARNING, logger="arrt.programming.clients"):
        for second in range(10):
            # Each one a new report: only its instant differs, as a Player's resend does.
            _refuse(clients, pi.id, {**_REFUSED, "reported_at": f"2026-10-02T14:00:{second:02d}+00:00"})
        _refuse(clients, pi.id, {**_REPORT, "reported_at": "yesterday"})

    lines = [record for record in caplog.records if getattr(record, "event", None) == "client.report_refused"]
    assert [(record.client_id, record.problem) for record in lines] == [
        (pi.id, _REFUSED_PROBLEM),
        (pi.id, "it carries 'reported_at' as an RFC 3339 timestamp with an offset."),
    ]


def test_a_refusal_after_an_accepted_report_starts_a_new_run_in_the_journal(clients, pi, access, caplog):
    access.issue(pi.id)
    with caplog.at_level(logging.WARNING, logger="arrt.programming.clients"):
        _refuse(clients, pi.id)
        clients.record_heartbeat(pi.id, _now_report())
        _refuse(clients, pi.id)

    assert sum(getattr(record, "event", None) == "client.report_refused" for record in caplog.records) == 2


def test_every_placements_over_the_store_reads_a_refusal_and_it_is_forgotten_with_its_player(
    store, clients, pi, access, wall_settings
):
    """Walls holds a `Placements` of its own, which the health reading reads Players through; both read one memory."""
    access.issue(pi.id)
    _refuse(clients, pi.id)

    elsewhere = Placements(store, wall_settings.art_root)
    assert [view.player.state for view in elsewhere.read_walls().players()] == [PlayerState.REPORT_UNREADABLE]

    clients.remove_client(pi.id)
    assert refused_reports_of(store).now() == {}


def test_a_refusal_is_not_written_so_a_store_opened_afresh_knows_nothing_of_it(
    clients, pi, access, wall_settings, quiet_catalogue_file
):
    """In memory only: a refused report is one the server records nothing of, so a restart forgets it."""
    access.issue(pi.id)
    _refuse(clients, pi.id)

    restarted = Placements(SqliteCatalogue(quiet_catalogue_file), wall_settings.art_root)
    [view] = restarted.read_walls().players()
    assert view.player.state is PlayerState.AWAITING_REPORT
    assert not client_heartbeat_path_in(wall_settings.art_root, pi.id).exists()
