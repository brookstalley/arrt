"""The label rule, run over the contract's conformance vectors, and the reading of a document offline.

`contract/vectors/label-rule.json` is what every label renderer is tested
against, wherever it runs (`player-contract.md` § Transport). Each vector goes
through this reader's own parser before the rule, so a document the parser
mangles fails a vector rather than passing on a dict the Player never sees.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from arrt_player.label_rule import (
    HOLD,
    STATES,
    Drawing,
    LabelDocumentUnreadable,
    Outcome,
    drawing_for,
    offline,
    outcome,
    parse_label_document,
)

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
VECTORS_FILE = json.loads((CONTRACT / "vectors" / "label-rule.json").read_text(encoding="utf-8"))
VECTORS = VECTORS_FILE["vectors"]
LABEL_SCHEMA = json.loads((CONTRACT / "schemas" / "label.v1.schema.json").read_text(encoding="utf-8"))

LABEL = VECTORS[0]["document"]["label"]
SINCE = datetime(2026, 10, 8, 16, 0, tzinfo=UTC)


def a_document(state: str = "showing_art", *, label: dict | None = LABEL, since: datetime | None = SINCE, **extra) -> dict:
    return {
        "schema": {"major": 1, "minor": 0},
        "wall_id": "w-living",
        "wall_name": "Living room",
        "display_state": {
            "state": state,
            "work_id": "work-great-wave" if state == "showing_art" and label is not None else None,
            "since": since.isoformat() if since is not None else None,
        },
        "label": label,
        **extra,
    }


def parsed(document: dict):
    return parse_label_document(json.dumps(document))


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["name"])
def test_each_vector_gives_the_outcome_the_contract_gives(vector):
    document = parsed(vector["document"])

    assert outcome(document, datetime.fromisoformat(vector["now"])) == Outcome(vector["outcome"])


def test_the_hold_is_the_vectors_hold():
    assert timedelta(seconds=VECTORS_FILE["hold_seconds"]) == HOLD


def test_the_rule_knows_exactly_the_states_the_schema_names():
    """So a state added to the schema and not here fails by name, rather than being read as unreachable."""
    assert set(STATES) == set(LABEL_SCHEMA["properties"]["display_state"]["properties"]["state"]["enum"])


class TestReadingADocument:
    def test_an_unknown_state_is_kept_as_sent(self):
        assert parsed(a_document("dimmed")).state == "dimmed"

    def test_since_in_another_offset_is_the_same_instant(self):
        document = a_document()
        document["display_state"]["since"] = "2026-10-08T09:00:00-07:00"

        assert parsed(document).since == SINCE

    def test_unknown_keys_are_allowed(self):
        assert parsed(a_document(later_key={"anything": 1})).wall_name == "Living room"

    @pytest.mark.parametrize(
        ("change", "why"),
        [
            (lambda document: document.update(schema={"major": 2, "minor": 0}), "another major"),
            (lambda document: document.pop("schema"), "no schema"),
            (lambda document: document.pop("wall_name"), "no wall name"),
            (lambda document: document.update(wall_id=""), "an empty wall id"),
            (lambda document: document.pop("display_state"), "no display state"),
            (lambda document: document["display_state"].pop("state"), "no state"),
            (lambda document: document["display_state"].update(since="yesterday"), "a since that is no instant"),
            (lambda document: document["display_state"].update(since="2026-10-08T16:00:00"), "a since with no offset"),
            (lambda document: document["display_state"].update(since=12), "a since that is a number"),
            (lambda document: document["display_state"].update(work_id=""), "an empty work id"),
            (lambda document: document.update(label="The Great Wave"), "a label that is not an object"),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_a_document_this_reader_cannot_act_on_is_refused_whole(self, change, why):
        document = a_document()
        change(document)

        with pytest.raises(LabelDocumentUnreadable):
            parsed(document)

    @pytest.mark.parametrize("text", ["not json", "[1, 2]"])
    def test_text_that_is_not_a_document_is_refused(self, text):
        with pytest.raises(LabelDocumentUnreadable):
            parse_label_document(text)


class TestTheServerGoneAway:
    """`offline`: what the renderer reads when the server cannot be reached.

    The server going away is the wall going silent as far as a label can tell,
    so a caption is held for 30 minutes from the last answer and then blanked
    (Chunk 06 item 3), and nothing else is ever turned into a caption.
    """

    LAST_ANSWER = SINCE + timedelta(hours=3)

    @pytest.mark.parametrize(
        ("minutes", "expected"),
        [(29, Outcome.CAPTION), (30, Outcome.BLANK), (95, Outcome.BLANK)],
    )
    def test_a_caption_is_held_for_thirty_minutes_from_the_last_answer(self, minutes, expected):
        held = offline(parsed(a_document()), self.LAST_ANSWER)

        assert outcome(held, self.LAST_ANSWER + timedelta(minutes=minutes, seconds=59 if minutes == 29 else 0)) is expected

    def test_the_hold_runs_from_the_last_answer_not_from_when_the_art_went_up(self):
        """The art went up three hours before the server went away; it is still captioned."""
        held = offline(parsed(a_document()), self.LAST_ANSWER)

        assert outcome(held, self.LAST_ANSWER + timedelta(minutes=1)) is Outcome.CAPTION

    def test_a_held_state_keeps_its_own_earlier_since(self):
        silent = parsed(a_document("silent"))

        held = offline(silent, self.LAST_ANSWER)

        assert held == silent
        assert outcome(held, self.LAST_ANSWER) is Outcome.BLANK

    @pytest.mark.parametrize("state", ["in_use", "dark", "no_screen"])
    def test_a_blank_with_a_label_beside_it_is_never_turned_into_a_caption(self, state):
        """The vectors give in_use a label; read as unreachable with it, it would caption somebody's programme."""
        held = offline(parsed(a_document(state)), self.LAST_ANSWER)

        assert held.label is None
        assert outcome(held, self.LAST_ANSWER) is Outcome.BLANK

    @pytest.mark.parametrize("document", [a_document("unassigned", label=None), a_document("showing_art", label=None)])
    def test_a_card_has_no_caption_to_hold_and_blanks(self, document):
        assert outcome(offline(parsed(document), self.LAST_ANSWER), self.LAST_ANSWER) is Outcome.BLANK

    def test_an_unknown_state_is_held_by_its_own_since(self):
        unknown = parsed(a_document("dimmed"))

        assert offline(unknown, self.LAST_ANSWER) == unknown

    def test_with_no_document_and_no_answer_there_is_nothing_to_hold(self):
        assert offline(None, None) is None
        assert drawing_for(offline(None, None), SINCE) == Drawing(Outcome.BLANK)

    def test_a_server_that_never_answered_cannot_time_a_hold(self):
        assert outcome(offline(parsed(a_document()), None), SINCE) is Outcome.BLANK


class TestTheDrawing:
    """`drawing_for` decides a redraw: equal drawings put the same ink down."""

    def test_the_same_caption_for_another_state_is_the_same_drawing(self):
        """Held after a server goes, a caption must not flash the panel by being redrawn."""
        showing = drawing_for(parsed(a_document()), SINCE)
        held = drawing_for(offline(parsed(a_document()), SINCE), SINCE)

        assert showing == held
        assert (showing.state, held.state) == ("showing_art", "unreachable")

    def test_another_work_with_the_same_text_is_the_same_drawing(self):
        first = drawing_for(parsed(a_document()), SINCE)
        second = replace(first, work_id="work-another-print")

        assert first == second

    def test_different_text_is_a_different_drawing(self):
        first = drawing_for(parsed(a_document()), SINCE)
        second = drawing_for(parsed(a_document(label={**LABEL, "title": "Fine Wind, Clear Morning"})), SINCE)

        assert first != second

    def test_a_card_carries_the_walls_name_and_a_renamed_wall_is_a_new_card(self):
        card = drawing_for(parsed(a_document("unassigned", label=None)), SINCE)
        renamed = parsed(a_document("unassigned", label=None, wall_name="Hall"))

        assert card == Drawing(Outcome.CARD, wall_name="Living room")
        assert drawing_for(renamed, SINCE) != card

    def test_a_card_and_a_blank_carry_no_label(self):
        assert drawing_for(parsed(a_document("unassigned")), SINCE).label is None
        assert drawing_for(parsed(a_document("in_use")), SINCE) == Drawing(Outcome.BLANK)

    def test_a_caption_names_its_work_for_the_journal(self):
        assert drawing_for(parsed(a_document()), SINCE).work_id == "work-great-wave"
