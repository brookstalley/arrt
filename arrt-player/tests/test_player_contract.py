"""Arrt Player's side of the Player contract: what it reads, and what it writes.

The manifest fixtures under `contract/` are the documents Arrt may publish.
Every one the contract calls valid must be one this reader adopts. Every invalid
one that the contract's index marks `player_must_refuse` must be one it refuses.
Those are the rules the reader enforces rather than trusts. The other invalid
fixtures break writer obligations the reader deliberately tolerates, and they
are not asserted here in either direction.

**`major-2` is the one to watch.** It must be refused as an *unsupported
version*, not as a malformed document, because that is the cutover rule schema
major 2 relies on: a Player that has not been upgraded keeps its wall rather than
misreading the new shape.

The heartbeat runs the other way: what `Health.document()` writes must validate
against the contract's heartbeat schema, for a Player mid-flight and for one
that has only just started.

**The client's two documents are the same pair, one level up.** The Player reads
the client document (`client.v1`): every valid fixture must be read whole and
every invalid one refused. It writes the client heartbeat
(`client-heartbeat.v1`): what it reports must validate, and for the fixture's
own machine must be the fixture.

These tests read JSON files and never import curation, which is the
plane-isolation norm; after the repo split they read a pinned copy of the same
files.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fakes import drm_tree
from jsonschema import Draft202012Validator

from arrt_player import manifest
from arrt_player.client import (
    ClientDocumentUnreadable,
    LabelOutputReport,
    client_heartbeat,
    client_outputs,
    parse_client_document,
)
from arrt_player.heartbeat import DisplayReport, Health, ScreenState
from arrt_player.label_rule import STATES, LabelDocumentUnreadable, Outcome, outcome, parse_label_document

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
INDEX = json.loads((CONTRACT / "fixtures" / "index.json").read_text(encoding="utf-8"))["fixtures"]
MANIFESTS = [row for row in INDEX if row["schema"] == "schemas/manifest.v1.schema.json"]


def _parse(row: dict) -> manifest.Manifest:
    text = (CONTRACT / row["path"]).read_text(encoding="utf-8")
    return manifest.parse(text, rotation_interval_fallback=180, shuffle_fallback=False)


#: A rotation interval no fixture carries, so a reader that fell back to it
#: instead of reading the document's value cannot pass.
_UNUSED_INTERVAL = 7919


@pytest.mark.parametrize("row", [row for row in MANIFESTS if row["valid"]], ids=lambda row: row["path"])
def test_every_valid_manifest_in_the_contract_is_adopted_whole(row):
    """Every field the Player acts on, read from the document rather than defaulted.

    The fallbacks are ones no fixture carries, the shuffle one set against each
    fixture's own value, so a reader that ignored a field and used its fallback
    fails here instead of passing on a coincidence.
    """
    document = json.loads((CONTRACT / row["path"]).read_text(encoding="utf-8"))
    assert document["rotation"]["interval_seconds"] != _UNUSED_INTERVAL

    adopted = manifest.parse(
        (CONTRACT / row["path"]).read_text(encoding="utf-8"),
        rotation_interval_fallback=_UNUSED_INTERVAL,
        shuffle_fallback=not document["rotation"]["shuffle"],
    )

    assert (adopted.schema_major, adopted.schema_minor) == (document["schema"]["major"], document["schema"]["minor"])
    assert (adopted.theme_id, adopted.theme_name) == (document["theme"]["id"], document["theme"]["name"])
    assert adopted.rotation_interval_seconds == document["rotation"]["interval_seconds"]
    assert adopted.shuffle == document["rotation"]["shuffle"]
    assert adopted.directive_sequence == document["directive"]["sequence"]
    assert adopted.pinned_work_id == document["directive"]["pinned_work_id"]
    assert [(entry.work_id, entry.render_path, entry.label) for entry in adopted.entries] == [
        (entry["work_id"], entry["render_path"], entry["label"]) for entry in document["entries"]
    ]


@pytest.mark.parametrize(
    "row",
    [row for row in MANIFESTS if not row["valid"] and row["player_must_refuse"]],
    ids=lambda row: row["path"],
)
def test_every_manifest_the_contract_says_to_refuse_is_refused(row):
    with pytest.raises(manifest.ManifestUnreadable):
        _parse(row)


def test_a_future_major_is_refused_as_a_version_not_as_a_malformed_document():
    (row,) = [row for row in MANIFESTS if row["path"].endswith("/major-2.json")]

    with pytest.raises(manifest.ManifestVersionUnsupported) as refused:
        _parse(row)

    assert refused.value.major == 2


@pytest.mark.parametrize(
    "row",
    [row for row in INDEX if row["schema"] == "schemas/manifest.v2.schema.json" and row["valid"]],
    ids=lambda row: row["path"],
)
def test_every_major_2_manifest_is_refused_by_this_major_1_reader(row):
    """The cutover, pinned from the Player's side for every shape major 2 can take.

    The server serves each major at its own URL, but a document of the wrong
    major can still reach this reader (an unversioned route, a cache, a server
    misconfigured). A Player not yet upgraded must keep its wall rather than
    misread a document with no entries list, and it must say why in terms of the
    version, so the fix is "upgrade this Player" rather than "debug the server".
    """
    with pytest.raises(manifest.ManifestVersionUnsupported) as refused:
        _parse(row)

    assert refused.value.major == 2


def _heartbeat_errors(document: dict) -> list[str]:
    schema = json.loads((CONTRACT / "schemas" / "heartbeat.v1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    return [error.message for error in validator.iter_errors(document)]


def test_a_heartbeat_from_a_running_player_conforms():
    health = Health(
        manifest_schema="1.1",
        theme_id="th-surrealism",
        current_work_id="w-dali-1",
        announced_content_id="MY_F0042",
        television_reachable=True,
        television_showing_art=True,
        has_label_surface=True,
        label_surface_working=False,
        last_error="the panel did not answer",
    )

    assert _heartbeat_errors(health.document(reported_at=datetime(2026, 9, 30, 14, 0, 5, 123456, tzinfo=UTC))) == []


@pytest.mark.parametrize("state", list(ScreenState))
def test_a_heartbeat_carrying_each_display_state_conforms(state):
    work_id = "w-dali-1" if state is ScreenState.SHOWING_ART else None
    since = datetime(2026, 10, 8, 14, 0, tzinfo=UTC)
    health = Health(display_state=DisplayReport(state=state, work_id=work_id, since=since))

    document = health.document(reported_at=datetime(2026, 10, 8, 14, 0, 5, tzinfo=UTC))

    assert _heartbeat_errors(document) == []
    assert document["schema"] == {"major": 1, "minor": 3}


def test_a_display_state_naming_a_work_beside_anything_but_art_is_refused_before_it_is_written():
    """The schema refuses it; the writer refuses it first, so it never reaches the server."""
    with pytest.raises(ValueError, match="names no work"):
        DisplayReport(state=ScreenState.IN_USE, work_id="w-dali-1", since=datetime(2026, 10, 8, tzinfo=UTC))


def test_a_heartbeat_from_a_player_that_has_only_just_started_conforms():
    assert _heartbeat_errors(Health().document(reported_at=datetime(2026, 9, 30, 14, 0, 5, tzinfo=UTC))) == []


# -- the client document, which the Player reads -------------------------------------------

CLIENT_DOCUMENTS = [row for row in INDEX if row["schema"] == "schemas/client.v1.schema.json"]
CLIENT_HEARTBEATS = [row for row in INDEX if row["schema"] == "schemas/client-heartbeat.v1.schema.json"]


def test_the_index_holds_client_documents_and_client_heartbeats_of_both_kinds():
    """The vacuity check: the parametrized tests below pass trivially over an empty list."""
    for rows in (CLIENT_DOCUMENTS, CLIENT_HEARTBEATS):
        assert {row["valid"] for row in rows} == {True, False}


@pytest.mark.parametrize("row", [row for row in CLIENT_DOCUMENTS if row["valid"]], ids=lambda row: row["path"])
def test_every_valid_client_document_is_read_whole(row):
    """Every wall, with its id, name, output and display, and every label, read from the document in its order."""
    document = json.loads((CONTRACT / row["path"]).read_text(encoding="utf-8"))

    read = parse_client_document((CONTRACT / row["path"]).read_text(encoding="utf-8"))

    assert (read.client_id, read.name) == (document["client_id"], document["name"])
    assert [(wall.wall_id, wall.name, wall.output, wall.display) for wall in read.walls] == [
        (wall["wall_id"], wall["name"], wall["output"], wall.get("display")) for wall in document["walls"]
    ]
    assert [(label.label_id, label.output, label.wall_id) for label in read.labels] == [
        (label["label_id"], label["output"], label["wall_id"]) for label in document.get("labels", [])
    ]


@pytest.mark.parametrize("row", [row for row in CLIENT_DOCUMENTS if not row["valid"]], ids=lambda row: row["path"])
def test_every_invalid_client_document_is_refused_whole(row):
    """Refused rather than read in part: acting on the readable part would stop
    the walls the unreadable part named."""
    with pytest.raises(ClientDocumentUnreadable):
        parse_client_document((CONTRACT / row["path"]).read_text(encoding="utf-8"))


# -- the client heartbeat, which the Player writes -----------------------------------------


def _client_heartbeat_errors(document: dict) -> list[str]:
    schema = json.loads((CONTRACT / "schemas" / "client-heartbeat.v1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    return [error.message for error in validator.iter_errors(document)]


@pytest.mark.parametrize("row", CLIENT_HEARTBEATS, ids=lambda row: row["path"])
def test_the_client_heartbeat_schema_judges_its_fixtures_as_the_index_says(row):
    """So the validator below is one that can say no."""
    errors = _client_heartbeat_errors(json.loads((CONTRACT / row["path"]).read_text(encoding="utf-8")))

    assert (errors == []) is row["valid"], errors


def test_what_the_player_writes_for_two_connectors_one_unplugged_is_the_fixture(tmp_path, client_settings):
    """The Player's own report of the fixture's machine, compared output for output."""
    fixture = json.loads((CONTRACT / "fixtures/client-heartbeat.v1/valid/two-connectors-one-unplugged.json").read_text())
    drm = drm_tree(
        tmp_path / "drm",
        {"card1-HDMI-A-1": ("connected", "1920x1080\n1280x720\n"), "card1-HDMI-A-2": ("disconnected", "")},
    )

    written = client_heartbeat(
        client_outputs(replace(client_settings, frame=None), drm_root=drm),
        reported_at=datetime(2026, 10, 2, 14, 0, 5, tzinfo=UTC),
    )

    assert _client_heartbeat_errors(written) == []
    assert written["outputs"] == fixture["outputs"]


def test_what_a_player_with_a_frame_writes_conforms(tmp_path, client_settings):
    drm = drm_tree(tmp_path / "drm", {"card1-HDMI-A-1": ("connected", "1280x1024\n")})

    written = client_heartbeat(
        client_outputs(client_settings, drm_root=drm), reported_at=datetime(2026, 10, 2, 14, 0, 5, 250000, tzinfo=UTC)
    )

    assert _client_heartbeat_errors(written) == []
    assert [output["name"] for output in written["outputs"]] == ["frame", "hdmi-a-1"]


def test_what_a_player_with_nothing_to_draw_on_writes_conforms(tmp_path, client_settings):
    written = client_heartbeat(
        client_outputs(replace(client_settings, frame=None), drm_root=tmp_path / "no-drm"),
        reported_at=datetime(2026, 10, 2, 14, 0, 5, tzinfo=UTC),
    )

    assert written["outputs"] == []
    assert _client_heartbeat_errors(written) == []


def _panel(connected: bool = True) -> LabelOutputReport:
    return LabelOutputReport(name="epd-0", kind="epaper", connected=connected, size=(1448, 1072))


def test_what_a_player_with_an_identified_frame_and_a_panel_writes_is_the_fixtures_shape(tmp_path, client_settings):
    """The fixture `frame-with-identity-and-a-panel`, written by the Player's own code."""
    fixture = json.loads((CONTRACT / "fixtures/client-heartbeat.v1/valid/frame-with-identity-and-a-panel.json").read_text())
    frame_fixture = next(output for output in fixture["outputs"] if output["kind"] == "frame")

    written = client_heartbeat(
        client_outputs(client_settings, drm_root=tmp_path / "no-drm", frame_identity=frame_fixture["identity"]),
        label_outputs=[_panel()],
        reported_at=datetime(2026, 10, 8, 14, 0, 5, tzinfo=UTC),
    )

    assert _client_heartbeat_errors(written) == []
    # The Player reports no size for the Frame (its render arrives composed for
    # it), where the fixture's writer knew one.
    assert written["outputs"] == [{**frame_fixture, "screen": None}]
    assert written["label_outputs"] == [{"name": "epd-0", "kind": "epaper", "connected": True, "size": [1448, 1072]}]


def test_what_a_player_with_a_panel_and_no_display_writes_conforms(tmp_path, client_settings):
    written = client_heartbeat(
        client_outputs(replace(client_settings, frame=None), drm_root=tmp_path / "no-drm"),
        label_outputs=[_panel(connected=False)],
        reported_at=datetime(2026, 10, 8, 14, 0, 5, tzinfo=UTC),
    )

    assert _client_heartbeat_errors(written) == []
    assert written["outputs"] == []
    assert written["label_outputs"][0]["connected"] is False


def test_a_frame_whose_id_could_not_be_read_is_written_without_the_key(tmp_path, client_settings):
    """Absent, never empty or null: the schema refuses an empty identity, and the
    server keys an output with none on the client and its name."""
    written = client_heartbeat(
        client_outputs(client_settings, drm_root=tmp_path / "no-drm", frame_identity=None),
        reported_at=datetime(2026, 10, 8, 14, 0, 5, tzinfo=UTC),
    )

    assert _client_heartbeat_errors(written) == []
    assert "identity" not in written["outputs"][0]
    assert "label_outputs" not in written, "a client with no panel wrote a label_outputs key"


# -- the label document, which a label renderer reads -------------------------------------------

LABEL_DOCUMENTS = [row for row in INDEX if row["schema"] == "schemas/label.v1.schema.json"]

#: The invalid label fixtures this reader refuses. The others break writer
#: obligations it tolerates: an unknown state is read as unreachable (the
#: contract's instruction for a later minor), a work named beside a state that
#: names none is ignored by the rule, and a label without a title is drawn as the
#: facts it does carry.
REFUSED_LABEL_DOCUMENTS = {
    "fixtures/label.v1/invalid/schema-major-2.json",
    "fixtures/label.v1/invalid/since-without-offset.json",
    "fixtures/label.v1/invalid/wall-name-missing.json",
}


def test_the_index_holds_label_documents_of_both_kinds():
    assert {row["valid"] for row in LABEL_DOCUMENTS} == {True, False}
    assert {row["path"] for row in LABEL_DOCUMENTS if not row["valid"]} >= REFUSED_LABEL_DOCUMENTS


@pytest.mark.parametrize("row", [row for row in LABEL_DOCUMENTS if row["valid"]], ids=lambda row: row["path"])
def test_every_valid_label_document_is_read_whole(row):
    document = json.loads((CONTRACT / row["path"]).read_text(encoding="utf-8"))

    read = parse_label_document((CONTRACT / row["path"]).read_text(encoding="utf-8"))

    assert (read.wall_id, read.wall_name, read.state, read.work_id, read.label) == (
        document["wall_id"],
        document["wall_name"],
        document["display_state"]["state"],
        document["display_state"]["work_id"],
        document["label"],
    )
    assert (read.since is None) is (document["display_state"]["since"] is None)


@pytest.mark.parametrize("path", sorted(REFUSED_LABEL_DOCUMENTS))
def test_every_label_document_this_reader_enforces_is_refused(path):
    with pytest.raises(LabelDocumentUnreadable):
        parse_label_document((CONTRACT / path).read_text(encoding="utf-8"))


def test_a_label_document_in_a_state_this_reader_does_not_know_is_read_as_unreachable():
    document = parse_label_document((CONTRACT / "fixtures/label.v1/invalid/state-unknown.json").read_text(encoding="utf-8"))

    assert document.state not in STATES
    assert outcome(document, datetime(2100, 1, 1, tzinfo=UTC)) is Outcome.BLANK
