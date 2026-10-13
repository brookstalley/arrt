"""Moving how long a work stays up and whether it is shuffled from each theme to the walls hanging it.

The file this reads is the one every deployment had before 2026-10-13: `themes`
carrying `rotation_interval_seconds` and `shuffle`, and `walls` carrying
neither. It is made by opening a fresh catalogue and putting that shape back
with raw SQL, because the store no longer writes it — which is the point.
"""

import sqlite3
from datetime import UTC, datetime

from arrt.persistence.file import open_catalogue_file
from arrt.persistence.migrations import carry_rotation_to_walls
from arrt.persistence.sqlite import SqliteCatalogue

_MOMENT = datetime(2026, 10, 12, 12, 0, tzinfo=UTC).isoformat()

#: (theme id, name, interval, shuffle as stored). Each value one no default
#: could produce, so a value dropped or crossed between walls shows.
_THEMES = [
    ("t-shuffled", "Shuffled", None, 1),
    ("t-in-order", "In order", None, 0),
    ("t-slow", "Slow", 931, None),
    ("t-both", "Both", 47, 0),
    ("t-plain", "Plain", None, None),
    ("t-unhung", "Unhung", 600, 1),
]

#: (wall id, name, theme it hangs or None). Two walls share one theme.
_WALLS = [
    ("w-a", "A", "t-shuffled"),
    ("w-b", "B", "t-in-order"),
    ("w-c", "C", "t-slow"),
    ("w-d", "D", "t-both"),
    ("w-e", "E", "t-both"),
    ("w-f", "F", "t-plain"),
    ("w-g", "G", None),
]

#: What each wall plays at after: the theme's value, or None for the default.
_EXPECTED = {
    "w-a": (None, True),
    "w-b": (None, False),
    "w-c": (931, None),
    "w-d": (47, False),
    "w-e": (47, False),
    "w-f": (None, None),
    "w-g": (None, None),
}


def _pre_move_catalogue(path):
    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            "ALTER TABLE walls DROP COLUMN rotation_interval_seconds;"
            "ALTER TABLE walls DROP COLUMN shuffle;"
            "ALTER TABLE themes ADD COLUMN rotation_interval_seconds INTEGER;"
            "ALTER TABLE themes ADD COLUMN shuffle INTEGER;"
            "DELETE FROM walls;"
        )
        for theme_id, name, interval, shuffle in _THEMES:
            connection.execute(
                "INSERT INTO themes (id, name, created_at, rotation_interval_seconds, shuffle) VALUES (?, ?, ?, ?, ?)",
                (theme_id, name, _MOMENT, interval, shuffle),
            )
        for wall_id, name, theme_id in _WALLS:
            connection.execute("INSERT INTO walls (id, name, created_at) VALUES (?, ?, ?)", (wall_id, name, _MOMENT))
            if theme_id is not None:
                connection.execute("INSERT INTO theme_assignments VALUES (?, ?, ?)", (wall_id, theme_id, _MOMENT))
        connection.commit()
    finally:
        connection.close()
    return path


def _columns(path, table):
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
    finally:
        connection.close()


def _rotations(catalogue):
    return {wall.id: (wall.rotation_interval_seconds, wall.shuffle) for wall in catalogue.list_walls()}


def test_every_wall_plays_as_its_theme_did(tmp_path):
    path = _pre_move_catalogue(tmp_path / "catalogue.sqlite")

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert _rotations(catalogue) == _EXPECTED
    finally:
        catalogue.close()


def test_the_theme_columns_are_gone(tmp_path):
    path = _pre_move_catalogue(tmp_path / "catalogue.sqlite")
    open_catalogue_file(path).close()

    assert not {"rotation_interval_seconds", "shuffle"} & _columns(path, "themes")
    assert {"rotation_interval_seconds", "shuffle"} <= _columns(path, "walls")


def test_a_theme_hanging_nowhere_loses_its_setting_by_name(tmp_path, caplog):
    path = _pre_move_catalogue(tmp_path / "catalogue.sqlite")

    with caplog.at_level("INFO", logger="arrt.persistence.migrations"):
        open_catalogue_file(path).close()

    # The summary counts only the themes that gave a wall something.
    assert "Carried the rotation settings of 4 hung theme(s) onto 5 wall(s)." in caplog.messages
    lost = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert len(lost) == 1
    assert "'Unhung'" in lost[0]
    assert "600" in lost[0]
    assert "True" in lost[0]


def test_opening_again_changes_nothing(tmp_path, caplog):
    path = _pre_move_catalogue(tmp_path / "catalogue.sqlite")
    open_catalogue_file(path).close()
    caplog.clear()

    with caplog.at_level("INFO", logger="arrt.persistence.migrations"):
        catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert _rotations(catalogue) == _EXPECTED
        assert not [record for record in caplog.records if "rotation" in record.getMessage()]
    finally:
        catalogue.close()


def test_a_wall_chosen_after_an_interrupted_carry_keeps_its_choice(tmp_path):
    """Carried and committed, the columns not dropped, then a wall changed: the next open keeps the wall's own value."""
    path = _pre_move_catalogue(tmp_path / "catalogue.sqlite")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            "ALTER TABLE walls ADD COLUMN rotation_interval_seconds INTEGER;" "ALTER TABLE walls ADD COLUMN shuffle INTEGER;"
        )
        connection.execute("UPDATE walls SET rotation_interval_seconds = 5, shuffle = 1 WHERE id = 'w-d'")
        connection.commit()
    finally:
        connection.close()

    catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert _rotations(catalogue) == {**_EXPECTED, "w-d": (5, True)}
    finally:
        catalogue.close()


def test_an_open_interrupted_between_the_two_drops_takes_away_the_last(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("ALTER TABLE themes ADD COLUMN shuffle INTEGER")
        connection.commit()
        carry_rotation_to_walls(connection)
    finally:
        connection.close()

    assert "shuffle" not in _columns(path, "themes")
