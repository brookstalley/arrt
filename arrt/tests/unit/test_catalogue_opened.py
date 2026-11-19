"""Which release last opened the catalogue, when, and whether it finished migrating it.

The record is one row in `catalogue_opened`, written by every open through
`open_catalogue_file`, the call the server, the seed and the identify commands
make (`open_configured_catalogue`). It answers the operator before a rollback,
the server at start (a file a newer release opened is refused by name), and
support after a failed upgrade (an open that died mid-migration says so).

Adding the table is itself a change to the opening path, so the cases below also
hold what that path guaranteed before it: an addition takes no pre-migration
copy, an interrupted open is finished by the next, one copy per migration, and a
hot journal left by a killed writer is rolled back before anything is read.
"""

import importlib.metadata
import sqlite3
import subprocess
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from arrt.persistence import backup, file
from arrt.persistence.file import NewerRelease, open_catalogue_file, open_configured_catalogue

START = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)

#: A file from before walls had per-wall rotation: every later migration but the
#: oldest has something to do on it, and two of them drop columns.
_WALL_TOKENS_AND_THEME_ROTATION = (
    ("walls", "token_verifier", "v-9f2"),
    ("walls", "token_issued_at", "2026-10-01T00:00:00+00:00"),
    ("themes", "rotation_interval_seconds", None),
    ("themes", "shuffle", None),
)


def _open(path, at, **given):
    """Open as a start at `at` would: every stamp the open writes, the copy's name included, reads that instant."""
    open_catalogue_file(path, now=lambda: at, **given).close()


def _query(path, sql):
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def _record(path):
    return _query(path, "SELECT release, opened_at, migrations_completed FROM catalogue_opened")


def _write(path, sql, *arguments):
    connection = sqlite3.connect(path)
    connection.execute(sql, arguments)
    connection.commit()
    connection.close()


def _recorded_as(path, release):
    _write(path, "UPDATE catalogue_opened SET release = ?", release)


def _older_shape(path, at):
    """A current file given back the wall tokens and the theme rotation columns, as v0.1.0 left them."""
    _open(path, at, release="0.1.0")
    connection = sqlite3.connect(path)
    for table, column, value in _WALL_TOKENS_AND_THEME_ROTATION:
        connection.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" TEXT')
        connection.execute(f'UPDATE "{table}" SET "{column}" = ?', (value,))  # noqa: S608 -- the test's own names
    # The record v0.1.0 never wrote: a file it left has no such table.
    connection.execute("DROP TABLE catalogue_opened")
    connection.commit()
    connection.close()
    return path


def _current_shape(path, at):
    _open(path, at, release="0.11.0")
    return path


#: Two different catalogues: one every later migration acts on, one on today's shape.
SHAPES = {"older shape": _older_shape, "current shape": _current_shape}


def _snapshots(directory):
    return sorted(directory.glob("pre-migration-*Z.sqlite"))


@pytest.mark.parametrize("shape", SHAPES)
def test_every_open_records_this_release_when_and_that_it_finished(tmp_path, shape):
    path = SHAPES[shape](tmp_path / "catalogue.sqlite", START - timedelta(days=30))

    _open(path, START, release="0.12.0")

    assert _record(path) == [("0.12.0", START.isoformat(), 1)]
    assert _query(path, "PRAGMA user_version") == [(0,)]


def test_a_second_start_records_its_own_instant_and_keeps_one_row(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    _open(path, START, release="0.12.0")
    first = _record(path)
    _open(path, START + timedelta(minutes=1), release="0.12.1")

    assert first == [("0.12.0", START.isoformat(), 1)]
    assert _record(path) == [("0.12.1", (START + timedelta(minutes=1)).isoformat(), 1)]


def test_by_default_the_release_recorded_is_the_installed_package_s_and_pyproject_s():
    """One owner: `pyproject.toml`'s version, which the installed package states and the record quotes."""
    pyproject = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8"))

    assert file.this_release() == importlib.metadata.version("arrt") == pyproject["project"]["version"]


def test_an_open_with_no_release_given_records_this_one(tmp_path):
    path = tmp_path / "catalogue.sqlite"

    _open(path, START)

    assert _record(path)[0][0] == importlib.metadata.version("arrt")


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("newer", ["0.12.0", "1.0.0", "0.11.10"])
def test_a_file_a_newer_release_opened_is_refused_by_name_and_left_untouched(tmp_path, shape, newer):
    """Refused before the copy and before the store, so the file is byte for byte what the newer release left."""
    path = SHAPES[shape](tmp_path / "catalogue.sqlite", START)
    if not _query(path, "SELECT 1 FROM sqlite_master WHERE name = 'catalogue_opened'"):
        connection = sqlite3.connect(path)
        connection.executescript(file.OPENED_SCHEMA)
        connection.execute("INSERT INTO catalogue_opened VALUES (1, 'x', ?, 1)", (START.isoformat(),))
        connection.commit()
        connection.close()
    _recorded_as(path, newer)
    before = path.read_bytes()

    with pytest.raises(NewerRelease) as refused:
        _open(path, START, release="0.11.9")

    assert newer in str(refused.value)
    assert "0.11.9" in str(refused.value)
    assert path.read_bytes() == before
    assert _snapshots(tmp_path) == []


def test_a_recorded_release_this_code_cannot_read_is_refused_by_name(tmp_path):
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _recorded_as(path, "next")

    with pytest.raises(NewerRelease, match="Arrt next"):
        _open(path, START, release="0.11.0")


@pytest.mark.parametrize("older", ["0.11.0", "0.9.1", "0.11.0rc1"])
def test_a_file_an_older_or_the_same_release_opened_opens_and_is_recorded_as_this_one(tmp_path, older):
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _recorded_as(path, older)

    _open(path, START + timedelta(days=1), release="0.11.0")

    assert _record(path) == [("0.11.0", (START + timedelta(days=1)).isoformat(), 1)]


def test_the_server_s_entry_point_refuses_it_too(tmp_path):
    """`open_configured_catalogue` is what the server, seed and identify open through."""
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _recorded_as(path, "99.0.0")
    settings = SimpleNamespace(catalogue_path=path, wall_name="The wall", backup_dir=tmp_path / "backups")

    with pytest.raises(NewerRelease, match=r"99\.0\.0"):
        open_configured_catalogue(settings)


def test_adding_the_record_to_a_file_on_today_s_shape_is_no_drop_and_takes_no_copy(tmp_path):
    """A v0.11.0 file is today's shape less the table: the addition is a widening, never a migration that copies first."""
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _write(path, "DROP TABLE catalogue_opened")

    _open(path, START, release="0.12.0")

    assert _snapshots(tmp_path) == []
    assert _record(path)[0][0] == "0.12.0"


#: Where a start can die after its copy: in each migration that drops, and in the
#: step that clears the mark, every one of them after the record was begun.
_FAILING_STEPS = ("retire_wall_tokens", "carry_rotation_to_walls", "finish_migration")


@pytest.mark.parametrize("step", _FAILING_STEPS)
def test_a_start_killed_mid_migration_says_so_and_the_next_start_finishes(tmp_path, monkeypatch, step):
    path = _older_shape(tmp_path / "catalogue.sqlite", START - timedelta(days=30))
    failing = monkeypatch.context()
    with failing as patch:

        def dies(*_args, **_kwargs):
            raise RuntimeError(f"killed in {step}")

        patch.setattr(file, step, dies)
        with pytest.raises(RuntimeError, match=f"killed in {step}"):
            _open(path, START, release="0.12.0")

    assert _record(path) == [("0.12.0", START.isoformat(), 0)], "the record did not say the open had not finished"
    assert _query(path, "PRAGMA user_version") == [(backup.MIGRATION_BEGUN,)]

    _open(path, START + timedelta(minutes=1), release="0.12.0")

    assert _record(path) == [("0.12.0", (START + timedelta(minutes=1)).isoformat(), 1)]
    assert _query(path, "PRAGMA user_version") == [(0,)]
    assert "token_verifier" not in {row[1] for row in _query(path, "PRAGMA table_info(walls)")}
    (copy,) = _snapshots(tmp_path)
    assert _query(copy, "SELECT DISTINCT token_verifier FROM walls") == [("v-9f2",)]
    assert not _query(copy, "SELECT 1 FROM sqlite_master WHERE name = 'catalogue_opened'"), "the copy is not the untouched file"


def test_a_start_killed_between_its_copy_and_the_mark_wrote_no_record_and_the_next_finishes(tmp_path, monkeypatch):
    """Nothing but the copy was written, so the file is still as the old release left it, and the next start copies it again."""
    path = _older_shape(tmp_path / "catalogue.sqlite", START - timedelta(days=30))
    with monkeypatch.context() as patch:

        def dies(_path):
            raise RuntimeError("killed after the copy")

        patch.setattr(backup, "_mark", dies)
        with pytest.raises(RuntimeError, match="killed after the copy"):
            _open(path, START, release="0.12.0")

    assert not _query(path, "SELECT 1 FROM sqlite_master WHERE name = 'catalogue_opened'")
    assert _query(path, "PRAGMA user_version") == [(0,)]

    _open(path, START + timedelta(minutes=1), release="0.12.0")

    assert _record(path) == [("0.12.0", (START + timedelta(minutes=1)).isoformat(), 1)]
    copies = _snapshots(tmp_path)
    assert len(copies) == 2
    assert all(_query(copy, "SELECT DISTINCT token_verifier FROM walls") == [("v-9f2",)] for copy in copies)


_KILLED_WRITING_A_NEWER_RECORD = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute("PRAGMA cache_size = 1")
connection.execute("BEGIN")
connection.execute("UPDATE catalogue_opened SET release = '99.0.0'")
connection.execute("CREATE TABLE ballast (x)")
connection.executemany("INSERT INTO ballast VALUES (?)", [(str(i) * 50,) for i in range(5000)])
os._exit(0)
"""


@pytest.mark.uncacheable("runs a child process that is killed inside a transaction, which is what leaves the journal")
def test_the_guard_reads_the_last_commit_after_a_writer_killed_mid_transaction(tmp_path):
    """A hot journal is rolled back before the record is read: the newer release the killed writer never committed opens nothing.

    Asked read-only, the read would fail on every start with "attempt to write a
    readonly database"; asked without the rollback, it would refuse a file no
    newer release ever finished writing.
    """
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    child = [sys.executable, "-c", _KILLED_WRITING_A_NEWER_RECORD, str(path)]
    subprocess.run(child, check=True)  # noqa: S603 -- this interpreter, running the fixed script above
    assert path.with_name(path.name + "-journal").exists(), "the child committed or cleaned up, so no journal was left"

    _open(path, START + timedelta(days=1), release="0.11.0")

    assert _record(path) == [("0.11.0", (START + timedelta(days=1)).isoformat(), 1)]
