"""Which release last opened the catalogue, when, and whether it finished migrating it.

The record is one row in `catalogue_opened`, written by every open through
`open_catalogue_file`, the call the server, the seed and the identify commands
make (`open_configured_catalogue`). It answers the operator before a rollback,
the server at start (a file recorded by code expecting a higher catalogue shape
generation is refused by name; release numbers are not compared), and support
after a failed upgrade (an open that died mid-migration says so).

**What the guard replaced by the shape generation guaranteed, and still does**
(2026-11-19): a refused file is left byte for byte, with nothing new beside it;
the refusal is asked before the copy and the store, at every entry point; a hot
journal is rolled back before the record is read; a file with no record opens;
the refusal names both releases and raises `NewerRelease` with ERROR
`catalogue.newer_release_refused`; an unfinished last open is warned of. What
it changed: a newer release of the same shape opens, a recorded release this
code cannot read no longer stops a start, and this code's own release is
checked before anything is written, not only when the file has a record.

Adding the table is itself a change to the opening path, so the cases below also
hold what that path guaranteed before it: an addition takes no pre-migration
copy, an interrupted open is finished by the next, one copy per migration, and a
hot journal left by a killed writer is rolled back before anything is read.
"""

import importlib.metadata
import re
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


def _generation(path):
    ((generation,),) = _query(path, "SELECT schema_generation FROM catalogue_opened")
    return generation


def _take_a_generation(path, directory, at):
    """One backup generation of the catalogue, as the server's backup job takes it."""
    receipt = directory.parent / "backup-status.json"
    backup.CatalogueBackup(catalogue_path=path, directory=directory, receipt_path=receipt, keep=14).run(now=at)


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


def test_every_open_records_the_shape_generation_this_code_expects(tmp_path):
    path = _older_shape(tmp_path / "catalogue.sqlite", START - timedelta(days=30))

    _open(path, START, release="0.12.0")

    assert _generation(path) == file.SCHEMA_GENERATION


def _record_written_by(path, *, release, generation):
    """The record a release of `generation` would leave, on a file of either shape: the table made if the file has none."""
    if not _query(path, "SELECT 1 FROM sqlite_master WHERE name = 'catalogue_opened'"):
        connection = sqlite3.connect(path)
        connection.executescript(file.OPENED_SCHEMA)
        connection.execute(
            "INSERT INTO catalogue_opened (id, release, opened_at, migrations_completed) VALUES (1, 'x', ?, 1)",
            (START.isoformat(),),
        )
        connection.commit()
        connection.close()
    _write(path, "UPDATE catalogue_opened SET release = ?, schema_generation = ?", release, generation)


def _listing(directory):
    return sorted(str(entry.relative_to(directory)) for entry in directory.rglob("*"))


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("newer", ["0.12.1", "1.0.0", "0.11.10", "0.11.0"])
def test_a_file_a_newer_release_of_the_same_shape_opened_opens_and_is_recorded_as_this_one(tmp_path, shape, newer):
    """The commonest rollback, a bad patch release to the one before it, crosses no change to the shape: it opens.

    "0.11.0" is `develop`'s case: two builds sharing one version string, which
    a release number cannot order.
    """
    path = SHAPES[shape](tmp_path / "catalogue.sqlite", START)
    _record_written_by(path, release=newer, generation=file.SCHEMA_GENERATION)

    _open(path, START + timedelta(days=1), release="0.11.0")

    assert _record(path) == [("0.11.0", (START + timedelta(days=1)).isoformat(), 1)]
    assert _generation(path) == file.SCHEMA_GENERATION


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize(("newer", "generation"), [("0.12.0", 1), ("0.11.0", 1), ("1.0.0", 40), ("0.10.0", "two")])
def test_a_file_a_newer_release_opened_is_refused_by_name_and_left_untouched(tmp_path, shape, newer, generation):
    """Refused before the copy and before the store, so the file is byte for byte what the newer release left.

    "Newer" is the shape generation, and only that: a release numbered the same
    as this one, or lower, recording a higher generation is refused, and so is
    a generation this code cannot read. `generation` is added to this code's.
    """
    recorded = file.SCHEMA_GENERATION + generation if isinstance(generation, int) else generation
    path = SHAPES[shape](tmp_path / "catalogue.sqlite", START)
    _record_written_by(path, release=newer, generation=recorded)
    before, listed = path.read_bytes(), _listing(tmp_path)

    with pytest.raises(NewerRelease) as refused:
        _open(path, START, release="0.11.0")

    assert f"Arrt {newer} " in str(refused.value)
    assert "This is Arrt 0.11.0" in str(refused.value)
    assert str(recorded) in str(refused.value)
    assert path.read_bytes() == before
    assert _listing(tmp_path) == listed


@pytest.mark.parametrize("unreadable", ["next", "0.12", "2026.11"])
def test_a_recorded_release_this_code_cannot_read_no_longer_stops_a_start(tmp_path, unreadable):
    """The release is a fact for the operator and the journal, not what the guard compares, so one it cannot read opens."""
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _recorded_as(path, unreadable)

    _open(path, START + timedelta(days=1), release="0.11.0")

    assert _record(path) == [("0.11.0", (START + timedelta(days=1)).isoformat(), 1)]


# -- a file a build from before shape generations left -------------------------------
#
# `tests/fixtures/catalogue_opened/before-generations.sql` is the catalogue the
# code at 6e4faae5 (the last build
# whose record named a release and no shape) made over `tools/old_catalogue.py`'s
# seed: `uv run python tools/old_catalogue.py --ref 6e4faae5 --to <that path>`.
# Its record says 0.11.0, the version string `develop` carried through it.

_BEFORE_GENERATIONS = Path(__file__).resolve().parents[1] / "fixtures" / "catalogue_opened" / "before-generations.sql"


def _before_generations(path, *, release=None):
    connection = sqlite3.connect(path)
    connection.executescript(_BEFORE_GENERATIONS.read_text(encoding="utf-8"))
    connection.close()
    if release is not None:
        _recorded_as(path, release)
    return path


def test_the_fixture_is_a_record_with_a_release_and_no_shape_generation(tmp_path):
    path = _before_generations(tmp_path / "catalogue.sqlite")

    assert _record(path) == [("0.11.0", "2026-09-01T12:00:00+00:00", 1)]
    assert "schema_generation" not in {row[1] for row in _query(path, "PRAGMA table_info(catalogue_opened)")}


@pytest.mark.parametrize("ours", ["0.11.0", "0.12.0"])
def test_a_file_a_build_from_before_generations_left_opens_takes_no_copy_and_gains_a_generation(tmp_path, ours):
    """Its shape is one this code knows, whatever the two releases say; the same string included, which is `develop`'s."""
    path = _before_generations(tmp_path / "catalogue.sqlite")

    _open(path, START, release=ours)

    assert _record(path) == [(ours, START.isoformat(), 1)]
    assert _generation(path) == file.SCHEMA_GENERATION
    assert _snapshots(tmp_path) == []
    assert _query(path, "SELECT COUNT(*) FROM artworks") == [(4,)]


def test_a_file_a_build_from_before_generations_left_naming_a_later_release_is_still_refused(tmp_path):
    """The one refusal the old guard made that this code cannot place: kept, and the file untouched."""
    path = _before_generations(tmp_path / "catalogue.sqlite", release="0.12.0")
    before, listed = path.read_bytes(), _listing(tmp_path)

    with pytest.raises(NewerRelease, match=r"Arrt 0\.12\.0 .*from before catalogue shape generations"):
        _open(path, START, release="0.11.0")

    assert path.read_bytes() == before
    assert _listing(tmp_path) == listed


def test_a_file_a_build_from_before_generations_left_naming_an_unreadable_release_opens_and_says_so(tmp_path, caplog):
    path = _before_generations(tmp_path / "catalogue.sqlite", release="0.12")

    _open(path, START, release="0.11.0")

    assert _record(path) == [("0.11.0", START.isoformat(), 1)]
    assert [record.recorded_release for record in caplog.records if record.event == "catalogue.unreadable_release_recorded"] == [
        "0.12"
    ]


# -- this code's own release -----------------------------------------------------------


@pytest.mark.parametrize("ours", ["0.12", "2026.11", "next"])
@pytest.mark.parametrize("existing", [False, True], ids=["a new file", "a file with a record"])
def test_this_code_s_release_it_cannot_read_stops_the_open_before_anything_is_written(tmp_path, ours, existing):
    """Checked before the file is judged or created: a build from before generations refuses a file holding such a release."""
    path = tmp_path / "catalogue.sqlite"
    if existing:
        _current_shape(path, START)
    before = path.read_bytes() if existing else None
    listed = _listing(tmp_path)

    with pytest.raises(file.UnreadableRelease, match=re.escape(repr(ours))):
        _open(path, START + timedelta(days=1), release=ours)

    assert _listing(tmp_path) == listed
    if existing:
        assert path.read_bytes() == before


def test_the_installed_package_s_release_is_the_one_checked(tmp_path, monkeypatch):
    """Through the default, as the server opens: the package's version is what the open would record."""
    monkeypatch.setattr(file.importlib.metadata, "version", lambda _name: "0.12")

    with pytest.raises(file.UnreadableRelease, match=re.escape("'0.12'")):
        open_catalogue_file(tmp_path / "catalogue.sqlite").close()

    assert _listing(tmp_path) == []


# -- the ways back a refusal names ---------------------------------------------------------


def test_the_copy_names_a_refusal_looks_for_are_backup_s_own():
    assert (file._PRE_MIGRATION_COPIES, file._GENERATIONS) == (backup._SNAPSHOT_GLOB, backup._GENERATION_GLOB)


def test_a_refusal_with_no_copy_beside_the_file_names_none_and_says_which_could_have_been(tmp_path):
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _record_written_by(path, release="0.12.0", generation=file.SCHEMA_GENERATION + 1)

    with pytest.raises(NewerRelease) as refused:
        _open(path, START, release="0.11.0")

    message = str(refused.value)
    assert f"No copy this release opens is in {tmp_path}" in message
    assert "pre-migration-2" not in message
    assert "catalogue-2" not in message
    assert "start Arrt 0.12.0 or a newer release" in message
    assert "operational-spec.md § Backup and Restore" in message
    assert "catalogue.sqlite-journal" in message


@pytest.mark.parametrize("starts", [1, 3])
def test_a_release_that_raises_the_generation_copies_first_and_the_one_left_behind_is_named_that_copy(
    tmp_path, monkeypatch, starts
):
    """The remedy exists: the open that raises a generation copies the file first, and the release it leaves names that copy.

    A later release is this code with its generation raised by one. Its first
    `starts - 1` starts die in the step after the record is begun, each at its
    own instant, so the copy must be the one from before them all. Beside it,
    a backup generation the later release wrote, which the older release would
    refuse too: counted, never named.
    """
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    as_left = sorted(_query(path, "SELECT name FROM themes"))
    backups = tmp_path / "backups"
    later = file.SCHEMA_GENERATION + 1
    with monkeypatch.context() as patch:
        patch.setattr(file, "SCHEMA_GENERATION", later)
        for start in range(starts - 1):
            with monkeypatch.context() as dying:

                def dies(*_args, **_kwargs):
                    raise RuntimeError("killed in the wall step")

                dying.setattr(file, "establish_the_wall", dies)
                with pytest.raises(RuntimeError, match="killed in the wall step"):
                    _open(path, START + timedelta(minutes=start + 1), release="0.12.0", snapshot_directory=backups)
        _open(path, START + timedelta(hours=1), release="0.12.0", snapshot_directory=backups)
        _take_a_generation(path, backups, START + timedelta(hours=2))
    (copy,) = _snapshots(backups)
    (generation,) = sorted(backups.glob("catalogue-*Z.sqlite"))
    assert _generation(path) == later

    with pytest.raises(NewerRelease) as refused:
        _open(path, START + timedelta(hours=3), release="0.11.0", snapshot_directory=backups)

    message = str(refused.value)
    assert f"{copy} (last opened by Arrt 0.11.0 on {START.isoformat()})" in message
    assert str(generation) not in message
    # And it does open, holding the household as this release left it.
    restored = tmp_path / "restored" / "catalogue.sqlite"
    restored.parent.mkdir()
    restored.write_bytes(copy.read_bytes())
    _open(restored, START + timedelta(hours=4), release="0.11.0")
    assert sorted(_query(restored, "SELECT name FROM themes")) == as_left


def test_a_refusal_counts_the_copies_this_release_would_refuse_too(tmp_path):
    """Only copies the newer release wrote: none named, each counted, so the operator knows they were looked at."""
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _record_written_by(path, release="0.12.0", generation=file.SCHEMA_GENERATION + 1)
    backups = tmp_path / "backups"
    _take_a_generation(path, backups, START)
    (backups / "catalogue-20261119T100000Z.sqlite").write_bytes(b"not a catalogue")

    with pytest.raises(NewerRelease) as refused:
        _open(path, START, release="0.11.0", snapshot_directory=backups)

    message = str(refused.value)
    assert "(2 copies are there that this release refuses too)" in message
    assert "catalogue-2" not in message


@pytest.mark.parametrize("older", ["0.11.0", "0.9.1", "0.11.0rc1"])
def test_a_file_an_older_or_the_same_release_opened_opens_and_is_recorded_as_this_one(tmp_path, older):
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _recorded_as(path, older)

    _open(path, START + timedelta(days=1), release="0.11.0")

    assert _record(path) == [("0.11.0", (START + timedelta(days=1)).isoformat(), 1)]


def test_the_server_s_entry_point_refuses_it_too(tmp_path):
    """`open_configured_catalogue` is what the server, seed and identify open through."""
    path = _current_shape(tmp_path / "catalogue.sqlite", START)
    _record_written_by(path, release="99.0.0", generation=file.SCHEMA_GENERATION + 1)
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
connection.execute("UPDATE catalogue_opened SET release = '99.0.0', schema_generation = 99")
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
