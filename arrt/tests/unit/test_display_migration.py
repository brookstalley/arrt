"""Moving a catalogue from walls on a client's output onto displays, with every wall left on its screen.

The file this reads is the one every deployment had before 2026-10-08: `walls`
carrying `client_id` and `output`, a partial unique index over the pair, and no
`displays` table. Written with raw SQL rather than through the store, because the
store no longer makes that shape — which is the point, and the reason a fixture
built through it would test a file nobody has on disk.
"""

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from arrt.persistence.durable import SqliteDurableStore
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.migrations import walls_name_displays
from arrt.persistence.sqlite import SqliteCatalogue

#: The tables a clients-era file held about walls, as that revision declared them.
_CLIENTS_ERA_DDL = """
CREATE TABLE clients (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL,
    token_verifier   TEXT,
    token_issued_at  TEXT
);

CREATE TABLE walls (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL,
    client_id        TEXT REFERENCES clients(id),
    output           TEXT
);

CREATE UNIQUE INDEX walls_one_per_output ON walls(client_id, output) WHERE client_id IS NOT NULL;

CREATE TABLE theme_assignments (
    wall_id      TEXT PRIMARY KEY REFERENCES walls(id),
    theme_id     TEXT NOT NULL,
    assigned_at  TEXT NOT NULL
);

CREATE TABLE directives (
    wall_id         TEXT PRIMARY KEY REFERENCES walls(id),
    sequence        INTEGER NOT NULL,
    pinned_work_id  TEXT
);
"""

_MOMENT = datetime(2026, 10, 7, 12, 0, tzinfo=UTC).isoformat()

#: Where each wall hangs in the file: (wall id, name, client id, output). Two
#: clients, a Frame and two HDMI connectors, and a wall nobody shows.
_WALLS = [
    ("w-living", "Living room", "c-pi", "frame"),
    ("w-office", "Office", "c-pi", "hdmi-a-1"),
    ("w-study", "Study", "c-mac", "hdmi-a-1"),
    ("w-spare", "Spare room", None, None),
]


def _clients_era_catalogue(path):
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_CLIENTS_ERA_DDL)
        for client_id, name in (("c-pi", "The Pi"), ("c-mac", "The Mac")):
            connection.execute("INSERT INTO clients (id, name, created_at) VALUES (?, ?, ?)", (client_id, name, _MOMENT))
        for wall_id, name, client_id, output in _WALLS:
            connection.execute("INSERT INTO walls VALUES (?, ?, ?, ?, ?)", (wall_id, name, _MOMENT, client_id, output))
            connection.execute("INSERT INTO directives VALUES (?, 0, NULL)", (wall_id,))
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


@pytest.fixture
def catalogue_file(tmp_path) -> Iterator[SqliteDurableStore]:
    """The clients-era catalogue, opened (and so upgraded) the way the plane opens it; every service reads it."""
    opened = open_catalogue_file(_clients_era_catalogue(tmp_path / "catalogue.sqlite"))
    yield opened
    opened.close()


@pytest.fixture
def upgraded(store):
    return store


def _screen_of(catalogue, wall_id):
    """Where the wall is now: the display's client and output, or None."""
    wall = catalogue.get_wall(wall_id)
    if wall.display_id is None:
        return None
    display = catalogue.get_display(wall.display_id)
    return (display.client_id, display.output)


def test_every_wall_is_on_the_same_screen_after(upgraded):
    for wall_id, _name, client_id, output in _WALLS:
        expected = None if client_id is None else (client_id, output)
        assert _screen_of(upgraded, wall_id) == expected, wall_id


def test_each_carried_display_is_keyed_by_its_place_and_its_kind_is_left_to_the_client(upgraded):
    displays = {(display.client_id, display.output): display for display in upgraded.list_displays()}

    assert set(displays) == {("c-pi", "frame"), ("c-pi", "hdmi-a-1"), ("c-mac", "hdmi-a-1")}
    for (client_id, output), display in displays.items():
        assert display.identity == f"{client_id}/{output}"
        assert display.kind is None


def test_each_client_is_told_the_same_walls_on_the_same_outputs(services):
    told = {
        client_id: [
            (entry["wall_id"], entry["output"]) for entry in json.loads(services.clients.client_document(client_id))["walls"]
        ]
        for client_id in ("c-pi", "c-mac")
    }

    assert told == {
        "c-pi": [("w-living", "frame"), ("w-office", "hdmi-a-1")],
        "c-mac": [("w-study", "hdmi-a-1")],
    }


def test_the_frame_wall_stays_put_when_its_client_first_names_the_set(services):
    """The carried Frame display is keyed by place; the Pi's first report with the set's id re-keys it."""
    services.clients.record_heartbeat(
        "c-pi",
        {
            "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "outputs": [
                {"name": "frame", "kind": "frame", "connected": True, "screen": None, "identity": "uuid:the-set"},
                {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
            ],
        },
    )
    walls = [(entry["wall_id"], entry["output"]) for entry in json.loads(services.clients.client_document("c-pi"))["walls"]]
    identity = services.clients.placement_of("w-living").display.identity

    assert walls == [("w-living", "frame"), ("w-office", "hdmi-a-1")]
    assert identity == "uuid:the-set"


def test_the_old_columns_and_index_are_gone(upgraded, tmp_path):
    path = tmp_path / "catalogue.sqlite"

    assert _columns(path, "walls") == {"id", "name", "created_at", "display_id"}
    indexes = {row[1] for row in _raw(path, "PRAGMA index_list(walls)")}
    assert "walls_one_per_output" not in indexes
    assert "walls_one_per_display" in indexes


def test_opening_again_changes_nothing(tmp_path, caplog):
    path = _clients_era_catalogue(tmp_path / "another.sqlite")
    open_catalogue_file(path).close()
    before = sorted(_raw(path, "SELECT id, identity, client_id, output FROM displays"))

    with caplog.at_level("INFO", logger="arrt.persistence.migrations"):
        catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert sorted(_raw(path, "SELECT id, identity, client_id, output FROM displays")) == before
        assert _screen_of(catalogue, "w-study") == ("c-mac", "hdmi-a-1")
        assert not [record for record in caplog.records if "display records" in record.getMessage()]
    finally:
        catalogue.close()


def test_an_open_interrupted_after_the_carry_is_finished_by_the_next(tmp_path):
    """The rows carried and committed, the columns not yet dropped: the next open drops them and carries nothing twice."""
    path = _clients_era_catalogue(tmp_path / "another.sqlite")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            "ALTER TABLE walls ADD COLUMN display_id TEXT;"
            "CREATE TABLE displays (id TEXT PRIMARY KEY, identity TEXT NOT NULL UNIQUE, client_id TEXT, output TEXT NOT NULL,"
            " kind TEXT, first_seen TEXT NOT NULL);"
        )
        connection.execute("INSERT INTO displays VALUES ('d-office', 'c-pi/hdmi-a-1', 'c-pi', 'hdmi-a-1', NULL, ?)", (_MOMENT,))
        connection.execute("UPDATE walls SET display_id = 'd-office' WHERE id = 'w-office'")
        connection.commit()
    finally:
        connection.close()

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert catalogue.get_wall("w-office").display_id == "d-office"
        assert len([display for display in catalogue.list_displays() if display.identity == "c-pi/hdmi-a-1"]) == 1
        for wall_id, _name, client_id, output in _WALLS:
            assert _screen_of(catalogue, wall_id) == (None if client_id is None else (client_id, output))
    finally:
        catalogue.close()


def test_an_open_interrupted_between_the_two_drops_takes_away_the_last(tmp_path):
    path = _clients_era_catalogue(tmp_path / "another.sqlite")
    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("ALTER TABLE walls ADD COLUMN output TEXT")
        connection.commit()
        walls_name_displays(connection)
    finally:
        connection.close()

    assert _columns(path, "walls") == {"id", "name", "created_at", "display_id"}
