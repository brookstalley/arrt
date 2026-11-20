"""`vocabulary.json` has a word for every display state a document can carry, and for no other.

The words are what a person reads, on Walls and on a Player's settings page, so
the two products say one thing for one state. The states are the schemas':
a wall's controller reports five (`heartbeat.v1`'s `display_state`), and the
server adds two of its own (`label.v1`'s). A state added to a schema with no word
here would be said by each side in words of its own, which is the drift this file
exists to stop.
"""

from arrt_contract import schema, vocabulary

WORDS = vocabulary()
STATES = WORDS["display_states"]


def _enum(relative: str) -> set[str]:
    return set(schema(relative)["properties"]["display_state"]["properties"]["state"]["enum"])


def test_every_state_the_server_sends_has_a_word_and_nothing_else_does():
    assert set(STATES) == _enum("schemas/label.v1.schema.json")


def test_the_states_a_player_reports_are_the_wall_heartbeats():
    reported = {state for state, entry in STATES.items() if entry["reported_by"] == "player"}

    assert reported == _enum("schemas/heartbeat.v1.schema.json")
    assert {entry["reported_by"] for entry in STATES.values()} == {"player", "server"}


def test_each_state_has_one_word_of_its_own():
    words = [entry["word"] for entry in STATES.values()]

    assert all(word.strip() == word and word for word in words), words
    assert len(words) == len(set(words)), "two states share a word, so a person cannot tell them apart"


def test_unassigned_is_the_one_setup_step():
    """A wall no Player shows yet is a step of setting it up, not a fault, and is worded as one."""
    assert {state for state, entry in STATES.items() if entry["setup"]} == {"unassigned"}
    assert STATES["unassigned"]["word"].endswith("yet")


def test_the_pairing_fields_are_named():
    assert WORDS["pairing"] == {"server_address": "Server address", "token": "Token"}
