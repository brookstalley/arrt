"""`vocabulary.json` has a word for every display state a document can carry, and for no other.

The words are what a person reads, on Walls and on a Player's settings page, so
the two products say one thing for one state. The states are the schemas':
a wall's controller reports five (`heartbeat.v1`'s `display_state`), and the
server adds two of its own (`label.v1`'s). A state added to a schema with no word
here would be said by each side in words of its own, which is the drift this file
exists to stop.

A Player's own states (`player_states`, since 1.3.0) are the server's judgement
of a Player, which no schema enumerates, so they are held to the decision that
named them instead.
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


# -- a Player's states (contract 1.3.0) ---------------------------------------------
#
# What the server says of a Player, and a Player's settings page of itself. The keys,
# the words and the setup flags are the audit wave 2b plan's decision (the household
# reads one story about its walls and Players); the server's health model quotes
# them with a test against this file, so they are written out here once more as the
# decision stated them, and a change to any is a change to this test too.

PLAYER_STATES = WORDS["player_states"]

#: The decision's keys and words, in its order.
DECIDED = {
    "no_token": "No token yet",
    "awaiting_report": "Waiting for its first report",
    "reporting": "Reporting",
    "not_heard_from": "Not heard from since {date}",
    "report_unreadable": "Report unreadable",
}


def test_a_player_has_the_five_states_the_decision_names_with_its_words_in_its_order():
    assert list(PLAYER_STATES) == list(DECIDED)
    assert {state: entry["word"] for state, entry in PLAYER_STATES.items()} == DECIDED


def test_each_player_state_says_its_word_whether_it_is_a_setup_step_and_what_it_means_and_nothing_else():
    for state, entry in PLAYER_STATES.items():
        assert set(entry) == {"word", "setup", "means"}, state
        assert isinstance(entry["setup"], bool), state
        assert entry["means"], state
        assert entry["means"].strip() == entry["means"], state


def test_the_setup_steps_of_a_player_are_having_no_token_and_waiting_for_its_first_report():
    """A step not yet taken is never a fault on the top bar or the System badge, so the flag is the whole of that rule."""
    assert {state for state, entry in PLAYER_STATES.items() if entry["setup"]} == {"no_token", "awaiting_report"}


def test_each_player_state_has_one_word_of_its_own_and_only_not_heard_from_names_a_date():
    words = [entry["word"] for entry in PLAYER_STATES.values()]

    assert all(word.strip() == word and word for word in words), words
    assert len(words) == len(set(words)), "two Player states share a word"
    assert {state for state, entry in PLAYER_STATES.items() if "{" in entry["word"]} == {"not_heard_from"}
    assert PLAYER_STATES["not_heard_from"]["word"].count("{date}") == 1


def test_no_player_state_is_worded_as_a_wall_state():
    """A person reads both on one screen, so a word that meant a wall's state and a Player's could not be told apart."""
    assert {entry["word"] for entry in PLAYER_STATES.values()} & {entry["word"] for entry in STATES.values()} == set()


def test_the_pairing_fields_are_named():
    assert WORDS["pairing"] == {"server_address": "Server address", "token": "Token"}
