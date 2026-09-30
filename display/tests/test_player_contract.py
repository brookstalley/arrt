"""Displayarr's side of the Player contract: what it reads, and what it writes.

The manifest fixtures under `contract/` are the documents Curatarr may publish.
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

These tests read JSON files and never import curation, which is the
plane-isolation norm; after the repo split they read a pinned copy of the same
files.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from display import manifest
from display.heartbeat import Health

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
INDEX = json.loads((CONTRACT / "fixtures" / "index.json").read_text(encoding="utf-8"))["fixtures"]
MANIFESTS = [row for row in INDEX if row["schema"] == "schemas/manifest.v1.schema.json"]


def _parse(row: dict) -> manifest.Manifest:
    text = (CONTRACT / row["path"]).read_text(encoding="utf-8")
    return manifest.parse(text, rotation_interval_fallback=180, shuffle_fallback=False)


@pytest.mark.parametrize("row", [row for row in MANIFESTS if row["valid"]], ids=lambda row: row["path"])
def test_every_valid_manifest_in_the_contract_is_adopted(row):
    document = json.loads((CONTRACT / row["path"]).read_text(encoding="utf-8"))

    adopted = _parse(row)

    assert [entry.work_id for entry in adopted.entries] == [entry["work_id"] for entry in document["entries"]]
    assert adopted.directive_sequence == document["directive"]["sequence"]


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

    Wave 4 publishes major 2 to every wall at once. A Player not yet upgraded must
    keep its wall rather than misread a document with no entries list, and it
    must say why in terms of the version, so the fix is "upgrade this Player"
    rather than "debug the server".
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


def test_a_heartbeat_from_a_player_that_has_only_just_started_conforms():
    assert _heartbeat_errors(Health().document(reported_at=datetime(2026, 9, 30, 14, 0, 5, tzinfo=UTC))) == []
