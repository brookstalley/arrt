"""Bringing a catalogue written before the default theme onto it, once.

The owner's catalogue holds *All works*, with every work in it, and one other
theme. The first open after this code ships has to mark *All works* the default
and record every held work as already offered, archived ones included, or the
next restore would put a work into the default that the curator never put there.

The file is built as today's schema and then has this change's additions taken
away, so it is the shape a deployment has on disk rather than one a fixture
imagines.
"""

import sqlite3
import uuid
from datetime import UTC, datetime

from arrt.persistence.file import open_catalogue_file

_MOMENT = datetime(2026, 9, 30, 9, 0, tzinfo=UTC).isoformat()


def _catalogue_before_the_default(path, *, themes, works, archived=()):
    """A file as the code before this change left it. `themes` is name -> member work ids."""
    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP INDEX themes_one_default")
        connection.execute("ALTER TABLE themes DROP COLUMN is_default")
        connection.execute("DROP TABLE default_theme_offers")
        for work_id in works:
            status = "archived" if work_id in archived else "accepted"
            connection.execute(
                "INSERT INTO artworks (id, title, status, created_at) VALUES (?, ?, ?, ?)",
                (work_id, f"Work {work_id[:4]}", status, _MOMENT),
            )
        for name, member_ids in themes.items():
            theme_id = str(uuid.uuid4())
            connection.execute("INSERT INTO themes (id, name, created_at) VALUES (?, ?, ?)", (theme_id, name, _MOMENT))
            for position, work_id in enumerate(member_ids):
                connection.execute(
                    "INSERT INTO theme_memberships (theme_id, artwork_id, position, added_at) VALUES (?, ?, ?, ?)",
                    (theme_id, work_id, position, _MOMENT),
                )
        connection.commit()
    finally:
        connection.close()


def _defaults(path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT name FROM themes WHERE is_default = 1")]
    finally:
        connection.close()


def _offered(path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[0] for row in connection.execute("SELECT artwork_id FROM default_theme_offers")}
    finally:
        connection.close()


def _rename(path, old: str, new: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE themes SET name = ? WHERE name = ?", (new, old))
        connection.commit()
    finally:
        connection.close()


def test_the_owners_all_works_becomes_the_default_and_every_work_is_offered(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    works = [str(uuid.uuid4()) for _ in range(5)]
    _catalogue_before_the_default(
        path,
        themes={"End-to-end validation 2026-08-04": works[:1], "All works": works},
        works=works,
        archived=works[4:],
    )

    open_catalogue_file(path).close()

    assert _defaults(path) == ["All works"]
    # The archived one too: a restore announces an acceptance, and an
    # unrecorded work would join the default on it.
    assert _offered(path) == set(works)


def test_the_name_is_matched_ignoring_case(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    work = str(uuid.uuid4())
    _catalogue_before_the_default(path, themes={"all works": [work]}, works=[work])

    open_catalogue_file(path).close()

    assert _defaults(path) == ["all works"]


def test_it_happens_once_whatever_themes_exist_at_the_next_open(tmp_path):
    """Two runs with different theme sets: no *All works* the first time, one the second.

    The second open must not mark it: by then the curator has been running with
    no default, and a theme they name *All works* later is not a request for one.
    """
    path = tmp_path / "catalogue.sqlite"
    works = [str(uuid.uuid4()) for _ in range(3)]
    _catalogue_before_the_default(path, themes={"Winter": works[:2]}, works=works)

    open_catalogue_file(path).close()
    assert (_defaults(path), _offered(path)) == ([], set(works))

    _rename(path, "Winter", "All works")
    open_catalogue_file(path).close()

    assert _defaults(path) == []
    assert _offered(path) == set(works)


def test_reopening_the_owners_file_changes_nothing(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    works = [str(uuid.uuid4()) for _ in range(3)]
    _catalogue_before_the_default(path, themes={"All works": works, "Winter": []}, works=works)
    open_catalogue_file(path).close()
    first = (_defaults(path), _offered(path))

    _rename(path, "Winter", "ALL WORKS ")
    open_catalogue_file(path).close()

    assert (_defaults(path), _offered(path)) == first


def test_an_empty_catalogue_is_left_alone(tmp_path):
    """Nothing on it predates the default, so nothing is recorded and nothing is marked."""
    path = tmp_path / "catalogue.sqlite"
    _catalogue_before_the_default(path, themes={"All works": []}, works=[])

    open_catalogue_file(path).close()

    assert (_defaults(path), _offered(path)) == ([], set())
