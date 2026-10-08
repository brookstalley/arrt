"""Moving a catalogue from wall tokens onto clients, without losing a wall.

The file this reads is the one every deployment had before 2026-10-02: `walls`
carrying `token_verifier` and `token_issued_at`, and no `clients` table. Written
with raw SQL rather than through the store, because the store no longer makes
that shape — which is the point, and the reason a fixture built through it would
test a file nobody has on disk.
"""

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from arrt.persistence.catalogue import StorageError
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import Client, Display
from arrt.persistence.sqlite import SqliteCatalogue

#: The three tables a wall-token file held about walls, as that revision declared them.
_WALL_TOKEN_DDL = """
CREATE TABLE IF NOT EXISTS themes (
    id                        TEXT PRIMARY KEY,
    name                      TEXT NOT NULL UNIQUE,
    description               TEXT,
    created_at                TEXT NOT NULL,
    rotation_interval_seconds INTEGER,
    shuffle                   INTEGER,
    is_default                INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS walls (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL,
    token_verifier   TEXT,
    token_issued_at  TEXT
);

CREATE TABLE IF NOT EXISTS theme_assignments (
    wall_id      TEXT PRIMARY KEY REFERENCES walls(id),
    theme_id     TEXT NOT NULL REFERENCES themes(id),
    assigned_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS directives (
    wall_id         TEXT PRIMARY KEY REFERENCES walls(id),
    sequence        INTEGER NOT NULL,
    pinned_work_id  TEXT
);
"""

_MOMENT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC).isoformat()

#: A verifier as the retired code stored it. Its value is what must not survive.
_OLD_VERIFIER = "a" * 64


def _wall_token_catalogue(path):
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_WALL_TOKEN_DDL)
        connection.execute(
            "INSERT INTO themes (id, name, created_at) VALUES ('t1', 'Late night', ?)",
            (_MOMENT,),
        )
        connection.execute(
            "INSERT INTO walls (id, name, created_at, token_verifier, token_issued_at) VALUES (?, ?, ?, ?, ?)",
            ("w-living", "Living room", _MOMENT, _OLD_VERIFIER, _MOMENT),
        )
        connection.execute(
            "INSERT INTO walls (id, name, created_at, token_verifier, token_issued_at) VALUES (?, ?, ?, NULL, NULL)",
            ("w-study", "Study", _MOMENT),
        )
        connection.execute("INSERT INTO theme_assignments VALUES ('w-living', 't1', ?)", (_MOMENT,))
        connection.execute("INSERT INTO directives VALUES ('w-living', 7, NULL)")
        connection.execute("INSERT INTO directives VALUES ('w-study', 0, NULL)")
        connection.commit()
    finally:
        connection.close()
    return path


def _raw(path, sql):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def _columns(path, table):
    return {row[1] for row in _raw(path, f'PRAGMA table_info("{table}")')}


def test_a_wall_token_file_opens_with_its_walls_kept_and_unassigned(tmp_path):
    path = _wall_token_catalogue(tmp_path / "catalogue.sqlite")

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        walls = {wall.id: wall for wall in catalogue.list_walls()}
        assert set(walls) == {"w-living", "w-study"}, "opening must neither lose a wall nor seed another"
        assert walls["w-living"].name == "Living room"
        assert walls["w-living"].display_id is None
        assert catalogue.get_assignment("w-living").theme_id == "t1"
        assert catalogue.get_directive("w-living").sequence == 7
        assert catalogue.list_clients() == []
    finally:
        catalogue.close()


def test_the_wall_token_columns_are_dropped_and_the_old_verifier_is_in_no_table(tmp_path):
    path = _wall_token_catalogue(tmp_path / "catalogue.sqlite")

    open_catalogue_file(path).close()

    assert _columns(path, "walls") == {"id", "name", "created_at", "display_id"}
    for (table,) in _raw(path, "SELECT name FROM sqlite_master WHERE type = 'table'"):
        for column in _columns(path, table):
            found = _raw(
                path,
                f'SELECT COUNT(*) FROM "{table}" WHERE CAST("{column}" AS TEXT) = \'{_OLD_VERIFIER}\'',  # noqa: S608 -- test's own names
            )
            assert found == [(0,)], f"{table}.{column} still holds a retired wall token's verifier"


def _display(display_id: str, client_id: str, output: str) -> Display:
    return Display(
        id=display_id,
        identity=f"{client_id}/{output}",
        client_id=client_id,
        output=output,
        kind="framebuffer",
        first_seen=datetime.now(UTC),
    )


def test_the_widened_display_column_refuses_a_display_that_does_not_exist(tmp_path):
    """The reference `walls.display_id` declares holds on an upgraded file, not only on a fresh one."""
    path = _wall_token_catalogue(tmp_path / "catalogue.sqlite")

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert _raw(path, "PRAGMA foreign_key_list(walls)")[0][2:5] == ("displays", "display_id", "id")
        wall = catalogue.get_wall("w-study")
        with pytest.raises(StorageError, match="refers to a record that is not stored"):
            catalogue.update_wall(replace(wall, display_id="nowhere"))

        catalogue.add_client(Client(id="c1", name="The Pi", created_at=datetime.now(UTC)))
        catalogue.add_display(_display("d1", "c1", "hdmi-a-1"))
        catalogue.update_wall(replace(wall, display_id="d1"))
        assert catalogue.get_wall("w-study").display_id == "d1"
    finally:
        catalogue.close()


def test_opening_again_changes_nothing_and_keeps_an_assignment(tmp_path, caplog):
    """Idempotent with the inputs varied: the second open meets a wall the first did not have assigned."""
    path = _wall_token_catalogue(tmp_path / "catalogue.sqlite")
    first = SqliteCatalogue(open_catalogue_file(path))
    first.add_client(Client(id="c1", name="The Pi", created_at=datetime.now(UTC)))
    first.add_display(_display("d1", "c1", "frame"))
    wall = first.get_wall("w-living")
    first.update_wall(replace(wall, display_id="d1"))
    first.close()

    with caplog.at_level("INFO", logger="arrt.persistence.migrations"):
        second = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert second.get_wall("w-living").display_id == "d1"
        assert (second.get_display("d1").client_id, second.get_display("d1").output) == ("c1", "frame")
        assert not [record for record in caplog.records if "Dropped walls." in record.getMessage()]
    finally:
        second.close()


def test_the_first_open_says_what_it_dropped(tmp_path, caplog):
    path = _wall_token_catalogue(tmp_path / "catalogue.sqlite")

    with caplog.at_level("INFO", logger="arrt.persistence.migrations"):
        open_catalogue_file(path).close()

    assert any("walls.token_verifier and walls.token_issued_at" in record.getMessage() for record in caplog.records)
