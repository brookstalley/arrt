"""Walls has words for every display state the server can send, and for no other.

`screens/walls.js` names five states in `STATE_WORDS` and words `showing_art` and
`silent` where the card is built, because those two lead with a work or with when
the wall was last heard from. A state added to the contract and not to Walls would
be said as "Not known", which is the reading of a state Walls cannot name, not of
one it forgot. So the seven are checked against the label schema's states, which
are the server's, in both directions.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WALLS = ROOT / "arrt" / "src" / "arrt" / "http" / "static" / "screens" / "walls.js"
LABEL_SCHEMA = ROOT / "contract" / "schemas" / "label.v1.schema.json"

#: Worded where the card is built rather than in the table.
WORDED_IN_THE_CARD = {"showing_art", "silent"}


def _state_words() -> set[str]:
    source = WALLS.read_text(encoding="utf-8")
    table = re.search(r"const STATE_WORDS = \{(.*?)\};", source, flags=re.DOTALL)
    assert table, "STATE_WORDS is not where this test reads it"
    return set(re.findall(r"^\s*(\w+):", table.group(1), flags=re.MULTILINE))


def _schema_states() -> set[str]:
    schema = json.loads(LABEL_SCHEMA.read_text(encoding="utf-8"))
    return set(schema["properties"]["display_state"]["properties"]["state"]["enum"])


def test_walls_words_every_state_the_server_sends_and_no_other():
    words = _state_words()

    assert words, "the table read as empty, so this checks nothing"
    assert not words & WORDED_IN_THE_CARD, "a state is worded twice"
    assert words | WORDED_IN_THE_CARD == _schema_states()
