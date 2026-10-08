"""The label rule's conformance vectors agree with the label schema and with the rule.

`contract/vectors/label-rule.json` is what every label renderer is tested against,
on every platform it is written for, so the vectors are a claim twice over: that
each input is a label document a server may send, and that each outcome is what
`labels-and-surfaces.md` § What a label says gives for it. This file makes both
true. `label_outcome` below is the reference statement of the rule, as
`semantic_errors` is of major 2's rules in `test_player_contract.py`; a renderer
implements it again and runs the same vectors.

**Coverage is checked, not hoped for.** A vector file that lost its boundary cases
would still pass every per-vector test, so the table's rows, both sides of the
30-minute boundary for each held state, and the unknown state are each asserted
to be present.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
VECTORS_FILE = json.loads((CONTRACT / "vectors" / "label-rule.json").read_text(encoding="utf-8"))
VECTORS = VECTORS_FILE["vectors"]
HOLD = timedelta(seconds=VECTORS_FILE["hold_seconds"])
LABEL_SCHEMA = json.loads((CONTRACT / "schemas" / "label.v1.schema.json").read_text(encoding="utf-8"))
STATES = LABEL_SCHEMA["properties"]["display_state"]["properties"]["state"]["enum"]

# The label schema reuses the manifest's label text by reference, so every schema
# is registered under its $id and the reference resolves to the file on disk.
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema))
    for schema in (json.loads(path.read_text(encoding="utf-8")) for path in (CONTRACT / "schemas").glob("*.json"))
)
VALIDATOR = Draft202012Validator(LABEL_SCHEMA, registry=REGISTRY, format_checker=Draft202012Validator.FORMAT_CHECKER)

BLANK_STATES = {"in_use", "dark", "no_screen"}
HELD_STATES = {"silent", "unreachable"}


def label_outcome(document: dict, now: datetime) -> str:
    """caption, card or blank for one label document at one instant."""
    shown = document["display_state"]
    state = shown["state"] if shown["state"] in STATES else "unreachable"
    label = document["label"]
    if state == "showing_art":
        return "caption" if label is not None else "card"
    if state == "unassigned":
        return "card"
    if state in BLANK_STATES:
        return "blank"
    if label is None or shown["since"] is None:
        return "blank"
    held = now - datetime.fromisoformat(shown["since"])
    return "caption" if held < HOLD else "blank"


def _now(vector: dict) -> datetime:
    return datetime.fromisoformat(vector["now"])


def test_the_rule_names_exactly_the_states_the_schema_does():
    """So a state added to the schema and not to the rule fails here by name."""
    assert BLANK_STATES | HELD_STATES | {"showing_art", "unassigned"} == set(STATES)


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["name"])
def test_each_vector_gives_the_outcome_the_rule_gives(vector):
    assert label_outcome(vector["document"], _now(vector)) == vector["outcome"]


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["name"])
def test_each_vector_is_a_label_document_or_says_why_not(vector):
    """A vector marked schema_valid false breaks the schema only by its state:
    any other fault would make it a test of a malformed document, not of the
    rule's reading of a later minor."""
    errors = list(VALIDATOR.iter_errors(vector["document"]))
    if vector.get("schema_valid", True):
        assert errors == [], [error.message for error in errors]
    else:
        assert [list(error.absolute_path) for error in errors] == [["display_state", "state"]]


def test_the_vectors_cover_every_row_of_the_table():
    """Every state with and without a label, as far as the table distinguishes them."""
    covered = {(vector["document"]["display_state"]["state"], vector["outcome"]) for vector in VECTORS}
    expected = {("showing_art", "caption"), ("showing_art", "card"), ("unassigned", "card")}
    expected |= {(state, "blank") for state in BLANK_STATES}
    expected |= {(state, outcome) for state in HELD_STATES for outcome in ("caption", "blank")}
    assert expected <= covered, expected - covered


@pytest.mark.parametrize("state", sorted(HELD_STATES))
def test_the_vectors_hold_each_held_state_on_both_sides_of_the_boundary(state):
    """Just inside the hold captions and exactly at it blanks, so an off-by-one in a
    renderer's comparison fails a vector."""
    offsets = {
        (_now(vector) - datetime.fromisoformat(vector["document"]["display_state"]["since"]), vector["outcome"])
        for vector in VECTORS
        if vector["document"]["display_state"]["state"] == state and vector["document"]["display_state"]["since"]
    }
    assert (HOLD - timedelta(seconds=1), "caption") in offsets
    assert (HOLD, "blank") in offsets


def test_the_vectors_read_an_unknown_state_as_unreachable_on_both_sides_of_the_boundary():
    unknown = [vector for vector in VECTORS if vector["document"]["display_state"]["state"] not in STATES]
    assert {vector["outcome"] for vector in unknown} == {"caption", "blank"}
