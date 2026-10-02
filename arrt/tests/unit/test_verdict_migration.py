"""Carrying a catalogue's `awaiting_better_image` verdicts onto `wanted`.

The file is written as a deployment has it on disk: today's schema, with rows a
curator left in the old verdict, written with raw SQL because nothing in the code
can write that spelling any more. Reading such a row without the migration fails
outright, since `Verdict` has no member for it, so these tests also stand for the
migration being wired into the open at all.
"""

import sqlite3
import uuid
from datetime import UTC, datetime

from arrt.persistence.discovery_records import Verdict
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.sqlite_discovery import SqliteDiscovery

_MOMENT = datetime(2026, 9, 30, 9, 0, tzinfo=UTC).isoformat()


def _catalogue_holding(path, verdicts: dict[str, str]) -> dict[str, str]:
    """A file whose candidate works hold these verdicts, by title. Returns title -> work id."""
    open_catalogue_file(path).close()
    run_id = str(uuid.uuid4())
    ids = {title: str(uuid.uuid4()) for title in verdicts}
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO discovery_runs (id, kind, initiated_by, status, approval_required, started_at) "
            "VALUES (?, 'discover', 'mcp_client', 'completed', 0, ?)",
            (run_id, _MOMENT),
        )
        for title, verdict in verdicts.items():
            connection.execute(
                "INSERT INTO candidate_works (id, discovery_run_id, proposed_title, rationale, work_dedup_key, "
                "resolution_status, verdict) VALUES (?, ?, ?, 'Asked for.', ?, 'unresolved', ?)",
                (ids[title], run_id, title, title.lower(), verdict),
            )
        connection.commit()
    finally:
        connection.close()
    return ids


def _stored_verdicts(path) -> dict[str, str]:
    connection = sqlite3.connect(path)
    try:
        return dict(connection.execute("SELECT proposed_title, verdict FROM candidate_works"))
    finally:
        connection.close()


def test_every_old_verdict_is_rewritten_and_no_other_is_touched(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    _catalogue_holding(
        path,
        {
            "The Elephants": "awaiting_better_image",
            "Nighthawks": "awaiting_better_image",
            "Sleep": "pending",
            "Automat": "rejected",
        },
    )

    open_catalogue_file(path).close()

    assert _stored_verdicts(path) == {
        "The Elephants": "wanted",
        "Nighthawks": "wanted",
        "Sleep": "pending",
        "Automat": "rejected",
    }


def test_a_second_open_rewrites_only_what_is_still_old_and_the_rows_read_back_as_wanted(tmp_path):
    """Run twice with different rows between, because the guard is the rows and not a flag.

    The row written between the two opens is what an open interrupted before its
    commit leaves behind: the next open has to finish it, and must leave alone the
    one already carried.
    """
    path = tmp_path / "catalogue.sqlite"
    ids = _catalogue_holding(path, {"The Elephants": "awaiting_better_image", "Sleep": "pending"})
    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE candidate_works SET verdict = 'awaiting_better_image' WHERE id = ?", (ids["Sleep"],))
        connection.commit()
    finally:
        connection.close()

    durable = open_catalogue_file(path)
    try:
        store = SqliteDiscovery(durable)
        assert store.get_candidate_work(ids["The Elephants"]).verdict is Verdict.WANTED
        assert {work.id for work in store.list_wanted_works()} == {ids["The Elephants"], ids["Sleep"]}
    finally:
        durable.close()

    assert _stored_verdicts(path) == {"The Elephants": "wanted", "Sleep": "wanted"}
