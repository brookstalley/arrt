"""Taking the stored conversations out of a catalogue, with every judgment and every cent left standing.

Before 2026-10-09 a catalogue held `conversations` and `conversation_turns`, and
two columns cited a turn: `affinities.source_turn_id` and
`spend_records.conversation_turn_id`. Ask's threads are not stored (the owner,
2026-10-08: old ones "are just gone"), so the migration drops all four. Deleting
a conversation always nulled both citations and kept the rows, so the migration
does to every row what a delete did to some.

The old shape is laid onto a file the current store has opened, with raw SQL,
because the store no longer makes it.
"""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from arrt.persistence.durable import SqliteDurableStore
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.migrations import retire_conversations
from arrt.persistence.sqlite_discovery import SqliteDiscovery

_MOMENT = datetime(2026, 10, 8, 12, 0, tzinfo=UTC).isoformat()

#: The two tables and two citing columns, as the last revision to have them declared them.
_CONVERSATION_DDL = """
CREATE TABLE conversations (
    id             TEXT PRIMARY KEY,
    started_at     TEXT NOT NULL,
    last_turn_at   TEXT NOT NULL,
    summary        TEXT
);
CREATE INDEX conversations_by_last_turn ON conversations(last_turn_at);
CREATE TABLE conversation_turns (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id),
    ordinal          INTEGER NOT NULL,
    role             TEXT NOT NULL,
    text             TEXT NOT NULL,
    suggested        TEXT,
    committed_run_id TEXT REFERENCES discovery_runs(id),
    created_at       TEXT NOT NULL
);
CREATE INDEX conversation_turns_by_conversation ON conversation_turns(conversation_id);
CREATE UNIQUE INDEX conversation_turns_one_per_ordinal ON conversation_turns(conversation_id, ordinal);
ALTER TABLE affinities ADD COLUMN source_turn_id TEXT REFERENCES conversation_turns(id);
CREATE INDEX affinities_by_turn ON affinities(source_turn_id);
ALTER TABLE spend_records ADD COLUMN conversation_turn_id TEXT REFERENCES conversation_turns(id);
CREATE INDEX spend_records_by_turn ON spend_records(conversation_turn_id);
"""

_RETIRED_TABLES = {"conversations", "conversation_turns"}
_RETIRED_INDEXES = {
    "conversations_by_last_turn",
    "conversation_turns_by_conversation",
    "conversation_turns_one_per_ordinal",
    "affinities_by_turn",
    "spend_records_by_turn",
}


def _conversation_era_catalogue(path):
    """A catalogue with one thread of two turns, a judgment citing each and none, and spend citing a turn and none."""
    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_CONVERSATION_DDL)
        connection.execute("INSERT INTO conversations VALUES ('c-1', ?, ?, NULL)", (_MOMENT, _MOMENT))
        for turn_id, ordinal, role in (("t-1", 0, "curator"), ("t-2", 1, "system")):
            connection.execute(
                "INSERT INTO conversation_turns (id, conversation_id, ordinal, role, text, created_at) "
                "VALUES (?, 'c-1', ?, ?, 'words', ?)",
                (turn_id, ordinal, role, _MOMENT),
            )
        for affinity_id, value, derivation, rationale, turn_id in (
            ("a-inferred", "Magritte", "inferred", "Lingered on the bowler hats.", "t-2"),
            ("a-stated", "Hopper", "stated", None, None),
        ):
            connection.execute(
                "INSERT INTO affinities (id, kind, value, sentiment, open_to_more, derivation, rationale, "
                "source_turn_id, created_at, updated_at) VALUES (?, 'artist', ?, 'loves', 1, ?, ?, ?, ?, ?)",
                (affinity_id, value, derivation, rationale, turn_id, _MOMENT, _MOMENT),
            )
        for spend_id, category, cost, turn_id in (
            ("s-talk", "conversation_tokens", "0.0021", "t-2"),
            ("s-mat", "mat_color_vision", "0.0100", None),
        ):
            connection.execute(
                "INSERT INTO spend_records (id, category, cost_usd, occurred_at, conversation_turn_id) VALUES (?, ?, ?, ?, ?)",
                (spend_id, category, cost, _MOMENT, turn_id),
            )
        connection.commit()
    finally:
        connection.close()
    return path


def _tables(path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _indexes(path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}


def _columns(path, table) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


@pytest.fixture
def old_file(tmp_path):
    return _conversation_era_catalogue(tmp_path / "catalogue.sqlite")


@pytest.fixture
def upgraded(old_file) -> Iterator[SqliteDurableStore]:
    opened = open_catalogue_file(old_file)
    yield opened
    opened.close()


def test_the_conversation_tables_columns_and_indexes_are_gone(upgraded, old_file):
    assert not _RETIRED_TABLES & _tables(old_file)
    assert not _RETIRED_INDEXES & _indexes(old_file)
    assert "source_turn_id" not in _columns(old_file, "affinities")
    assert "conversation_turn_id" not in _columns(old_file, "spend_records")


def test_every_judgment_keeps_its_derivation_and_rationale(upgraded):
    affinities = {affinity.id: affinity for affinity in SqliteDiscovery(upgraded).list_affinities()}

    assert set(affinities) == {"a-inferred", "a-stated"}
    assert affinities["a-inferred"].derivation == "inferred"
    assert affinities["a-inferred"].rationale == "Lingered on the bowler hats."
    assert affinities["a-stated"].derivation == "stated"


def test_every_spend_record_is_kept_and_still_counted(upgraded):
    records = {record.id: record for record in SqliteDiscovery(upgraded).list_spend_records()}

    assert set(records) == {"s-talk", "s-mat"}
    assert records["s-talk"].category == "conversation_tokens"
    assert sum(record.cost_usd for record in records.values()) == Decimal("0.0121")


def test_opening_again_changes_nothing(upgraded, old_file):
    upgraded.close()
    before = (_tables(old_file), _indexes(old_file))

    open_catalogue_file(old_file).close()

    assert (_tables(old_file), _indexes(old_file)) == before


def test_an_open_interrupted_after_the_columns_went_is_finished_by_the_next(old_file):
    connection = sqlite3.connect(old_file)
    connection.row_factory = sqlite3.Row
    try:
        # What an open stopped after the citing columns went, before the tables did.
        for statement in (
            "DROP INDEX affinities_by_turn",
            "ALTER TABLE affinities DROP COLUMN source_turn_id",
            "DROP INDEX spend_records_by_turn",
            "ALTER TABLE spend_records DROP COLUMN conversation_turn_id",
        ):
            connection.execute(statement)
        connection.commit()
        assert _tables(old_file) >= _RETIRED_TABLES

        retire_conversations(connection)
    finally:
        connection.close()

    assert not _RETIRED_TABLES & _tables(old_file)


def test_a_fresh_catalogue_never_has_them(tmp_path):
    path = tmp_path / "fresh.sqlite"

    open_catalogue_file(path).close()

    assert not _RETIRED_TABLES & _tables(path)
    assert "source_turn_id" not in _columns(path, "affinities")
    assert "conversation_turn_id" not in _columns(path, "spend_records")
