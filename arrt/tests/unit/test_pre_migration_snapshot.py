"""A copy of the catalogue before a migration takes anything from it.

The rollback across a migration that drops a column is a restore
(`operational-spec.md` § Routine Operations), so the copy to restore has to
exist whether or not the operator took one by hand. These cases open real
files of older shapes through `open_catalogue_file`, the call the server makes,
and read what the copy holds.

The older shapes are written two ways: the single-wall file as raw DDL, as the
store can no longer make one, and a current file given back a retired column
with `ALTER TABLE ... ADD COLUMN`, which is the shape a file the previous
release left has as far as the migration that drops it can tell.
"""

import errno
import fnmatch
import hashlib
import inspect
import os
import sqlite3
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from arrt import atomic
from arrt.persistence import backup, file, migrations
from arrt.persistence.backup import SNAPSHOTS_KEPT, SnapshotFailed, take_pre_migration_snapshot
from arrt.persistence.file import open_catalogue_file

START = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)

_SINGLE_WALL_DDL = """
CREATE TABLE artworks (id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE themes (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT,
    is_active INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX themes_one_active ON themes(is_active) WHERE is_active = 1;
CREATE TABLE directive (id INTEGER PRIMARY KEY CHECK (id = 1), sequence INTEGER NOT NULL, pinned_work_id TEXT);
"""


class Clock:
    """A minute later at every reading, so each open names its copy apart."""

    def __init__(self, at: datetime = START) -> None:
        self.at = at

    def __call__(self) -> datetime:
        moment = self.at
        self.at += timedelta(minutes=1)
        return moment


def _open(path, clock, **given):
    store = open_catalogue_file(path, now=clock, **given)
    store.close()


def _query(path, sql, *arguments):
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return connection.execute(sql, arguments).fetchall()
    finally:
        connection.close()


def _columns(path, table):
    return {row[1] for row in _query(path, f'PRAGMA table_info("{table}")')}


def _snapshots(directory):
    return sorted(directory.glob("pre-migration-*Z.sqlite"))


def _single_wall_file(path, theme_name):
    connection = sqlite3.connect(path)
    connection.executescript(_SINGLE_WALL_DDL)
    connection.execute(
        "INSERT INTO themes VALUES ('t1', ?, NULL, 1, ?)",
        (theme_name, START.isoformat()),
    )
    connection.execute("INSERT INTO directive VALUES (1, 7, NULL)")
    connection.commit()
    connection.close()
    return path


def _with_retired_columns(path, clock, table, columns, value):
    """A current file given back `columns` on `table`, each holding `value` on every row."""
    _open(path, clock)
    connection = sqlite3.connect(path)
    for column in columns:
        connection.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" TEXT')
        connection.execute(f'UPDATE "{table}" SET "{column}" = ?', (value,))  # noqa: S608 -- the test's own names
    connection.commit()
    connection.close()
    return path


#: Two older shapes, each with data of its own: the file, the column that goes,
#: the table it is on, and the value the copy must still hold there.
SHAPES = {
    "single-wall": (lambda path, clock: _single_wall_file(path, "Late night"), "themes", "is_active", 1),
    "wall-tokens": (
        lambda path, clock: _with_retired_columns(path, clock, "walls", ("token_verifier", "token_issued_at"), "v-9f2"),
        "walls",
        "token_verifier",
        "v-9f2",
    ),
}


@pytest.mark.parametrize("shape", SHAPES, ids=list(SHAPES))
def test_opening_an_older_shape_copies_it_first_and_the_copy_holds_what_goes(tmp_path, shape):
    make, table, column, value = SHAPES[shape]
    path = tmp_path / "catalogue.sqlite"
    clock = Clock()
    make(path, clock)

    _open(path, clock)

    (copy,) = _snapshots(tmp_path)
    assert column not in _columns(path, table), "the migration did not run, so nothing was dropped"
    assert column in _columns(copy, table)
    assert _query(copy, f'SELECT "{column}" FROM "{table}"') == [(value,)]  # noqa: S608 -- the test's own names
    assert _query(copy, "PRAGMA integrity_check") == [("ok",)]


def test_the_copy_is_the_file_as_it_was_before_the_store_touched_it(tmp_path):
    """Taken before the schema runs, so it holds no table the new release would have created."""
    path = _single_wall_file(tmp_path / "catalogue.sqlite", "Daylight")

    _open(path, Clock())

    (copy,) = _snapshots(tmp_path)
    tables = {row[0] for row in _query(copy, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"artworks", "themes", "directive"}
    assert _query(copy, "SELECT name, is_active FROM themes") == [("Daylight", 1)]


def test_a_file_on_the_current_shape_and_a_new_one_take_no_copy(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    clock = Clock()

    _open(path, clock)
    _open(path, clock)

    assert _snapshots(tmp_path) == []
    connection = migrations.open_existing(path)
    try:
        assert migrations.pending_drops(connection) == ()
    finally:
        connection.close()


def test_the_copy_goes_to_the_directory_named_for_it(tmp_path):
    """Where `__main__` names `BACKUP_DIR`, beside the generations a restore is taken from."""
    path = _single_wall_file(tmp_path / "catalogue.sqlite", "Late night")
    backups = tmp_path / "backups"

    _open(path, Clock(), snapshot_directory=backups)

    assert len(_snapshots(backups)) == 1
    assert _snapshots(tmp_path) == []


def _read_only(directory):
    directory.mkdir()
    directory.chmod(stat.S_IRUSR | stat.S_IXUSR)
    return directory


def _disk_full_at_sync(monkeypatch):
    def refuse(_path):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(atomic, "sync_file", refuse)


@pytest.mark.skipif(os.geteuid() == 0, reason="a read-only directory does not refuse root")
@pytest.mark.parametrize("fault", ["read-only directory", "disk full"])
def test_a_copy_that_cannot_be_written_stops_the_open_and_changes_nothing(tmp_path, monkeypatch, fault):
    """No column is dropped without its copy, and the message says what to do."""
    path = _single_wall_file(tmp_path / "catalogue.sqlite", "Late night")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    real_sync = atomic.sync_file
    if fault == "read-only directory":
        snapshots = _read_only(tmp_path / "backups")
    else:
        snapshots = tmp_path / "backups"
        _disk_full_at_sync(monkeypatch)

    try:
        with pytest.raises(SnapshotFailed) as refused:
            _open(path, Clock(), snapshot_directory=snapshots)
        left = list(snapshots.iterdir()) if snapshots.exists() else []
    finally:
        if snapshots.exists():
            snapshots.chmod(stat.S_IRWXU)

    message = str(refused.value)
    assert "drops themes.is_active" in message
    assert "Nothing in the catalogue has been changed" in message
    assert "Free space there or make it writable" in message
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert "is_active" in _columns(path, "themes")
    assert left == [], "a half copy was left where a restorer would find it"

    # And once the directory takes it, the next start copies and migrates.
    monkeypatch.setattr(atomic, "sync_file", real_sync)
    _open(path, Clock(START + timedelta(hours=1)), snapshot_directory=snapshots)
    assert len(_snapshots(snapshots)) == 1
    assert "is_active" not in _columns(path, "themes")


def _marked(path, mark):
    """A file whose drops `_drops_by_mark` reads off its one row, so a test chooses what an open would drop."""
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS marker (name TEXT)")
    connection.execute("DELETE FROM marker")
    connection.execute("INSERT INTO marker VALUES (?)", (mark,))
    connection.commit()
    connection.close()


def _drops_by_mark(connection):
    return tuple(row[0] for row in connection.execute("SELECT name FROM marker"))


def test_the_newest_copies_are_kept_and_older_ones_go(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    marks = ["a", "b", "c", "d", "e"]
    for minute, mark in enumerate(marks):
        _marked(path, mark)
        take_pre_migration_snapshot(
            path, directory=tmp_path / "s", would_drop=_drops_by_mark, now=START + timedelta(minutes=minute)
        )

    kept = _snapshots(tmp_path / "s")
    assert len(kept) == SNAPSHOTS_KEPT
    assert [_query(copy, "SELECT name FROM marker") for copy in kept] == [[(mark,)] for mark in marks[-SNAPSHOTS_KEPT:]]


@pytest.mark.parametrize("starts", [2, 6])
def test_a_migration_failing_on_every_start_never_pushes_out_the_copy_from_before_it(tmp_path, monkeypatch, starts):
    """The crash loop the copy exists for: the first start drops what it can, then fails, and so does every start after.

    The first copy is the only one holding the wall tokens, which the first
    start dropped before the next migration failed. Every later start would
    drop the same thing, so its copy replaces the previous later one rather
    than adding a copy; two starts and six (more than the copies kept) both
    leave the first one in place.
    """
    path = tmp_path / "catalogue.sqlite"
    clock = Clock()
    _with_retired_columns(path, clock, "walls", ("token_verifier", "token_issued_at"), "v-71c")
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE themes ADD COLUMN rotation_interval_seconds INTEGER")
    connection.execute("ALTER TABLE themes ADD COLUMN shuffle INTEGER")
    connection.commit()
    connection.close()

    def fails(_connection):
        raise RuntimeError("a migration that fails on this file every time")

    monkeypatch.setattr(file, "carry_rotation_to_walls", fails)

    for _ in range(starts):
        with pytest.raises(RuntimeError, match="fails on this file"):
            open_catalogue_file(path, now=clock)

    copies = _snapshots(tmp_path)
    assert "token_verifier" not in _columns(path, "walls"), "the first start did not drop the tokens"
    assert len(copies) == min(starts, 2)
    assert _query(copies[0], "SELECT DISTINCT token_verifier FROM walls") == [("v-71c",)]


def test_two_opens_in_one_second_keep_the_first_copy(tmp_path):
    """The earlier copy is of a state no later than the second's, so it is not overwritten."""
    path = tmp_path / "catalogue.sqlite"
    _marked(path, "first")
    first = take_pre_migration_snapshot(path, directory=tmp_path / "s", would_drop=_drops_by_mark, now=START)
    _marked(path, "second")

    again = take_pre_migration_snapshot(path, directory=tmp_path / "s", would_drop=_drops_by_mark, now=START)

    assert again == first
    assert _query(first, "SELECT name FROM marker") == [("first",)]


_KILLED_MID_WRITE = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute("PRAGMA cache_size = 1")
connection.execute("BEGIN")
connection.execute("CREATE TABLE ballast (x)")
connection.executemany("INSERT INTO ballast VALUES (?)", [(str(i) * 50,) for i in range(5000)])
os._exit(0)
"""


@pytest.mark.uncacheable("runs a child process that is killed inside a transaction, which is what leaves the journal")
@pytest.mark.parametrize("older", [False, True], ids=["current shape", "single-wall shape"])
def test_a_file_left_with_a_hot_journal_by_a_killed_writer_still_opens(tmp_path, older):
    """A server killed inside a transaction leaves a hot rollback journal, and the next start must open the file.

    Everything asked of the file before the store opens it reads it first, and a
    read-only connection cannot roll a hot journal back: every read fails with
    "attempt to write a readonly database", on this start and every start after.
    """
    path = tmp_path / "catalogue.sqlite"
    clock = Clock()
    if older:
        _single_wall_file(path, "Late night")
    else:
        _open(path, clock)
    child = [sys.executable, "-c", _KILLED_MID_WRITE, str(path)]
    subprocess.run(child, check=True)  # noqa: S603 -- this interpreter, running the fixed script above
    assert path.with_name(path.name + "-journal").exists(), "the child committed or cleaned up, so no journal was left"

    _open(path, clock)

    assert "ballast" not in {row[0] for row in _query(path, "SELECT name FROM sqlite_master")}
    assert len(_snapshots(tmp_path)) == (1 if older else 0)


@pytest.mark.uncacheable("runs a child process that is killed inside a transaction, which is what leaves the journal")
def test_asking_a_file_with_a_hot_journal_whether_it_had_a_table_answers(tmp_path):
    """The open asks this after the copy has rolled the journal back; asked first, it must not refuse either."""
    path = tmp_path / "catalogue.sqlite"
    _single_wall_file(path, "Late night")
    child = [sys.executable, "-c", _KILLED_MID_WRITE, str(path)]
    subprocess.run(child, check=True)  # noqa: S603 -- this interpreter, running the fixed script above
    assert path.with_name(path.name + "-journal").exists(), "the child committed or cleaned up, so no journal was left"

    assert migrations.file_had_table(path, "themes") is True
    assert migrations.file_had_table(path, "ballast") is False


def _runs_a_drop(function) -> bool:
    source = inspect.getsource(function)
    return "DROP TABLE" in source or "DROP COLUMN" in source


def test_every_migration_that_drops_something_says_what_it_would_drop():
    """A drop added without its question would run with no copy taken; this names it.

    Read off the module's own functions, so the one added later is in the set
    without anyone listing it here.
    """
    dropping = {
        function
        for _, function in inspect.getmembers(migrations, inspect.isfunction)
        if function.__module__ == migrations.__name__ and _runs_a_drop(function)
    }

    assert dropping, "no function in migrations.py drops anything, so this checks nothing"
    assert dropping == set(migrations.WOULD_DROP)


def test_the_copy_s_name_is_outside_the_generations_glob(tmp_path):
    """The generations' retention would otherwise count the copy, and a crash loop prune it."""
    path = _single_wall_file(tmp_path / "catalogue.sqlite", "Late night")

    _open(path, Clock())

    (copy,) = _snapshots(tmp_path)
    assert not fnmatch.fnmatch(copy.name, backup._GENERATION_GLOB)
