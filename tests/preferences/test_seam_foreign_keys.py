"""The catalogue file has exactly one foreign key across the Library/Programming seam, and the count only shrinks.

`architecture.md` § Direction, the seam's rule 3: separate stores, no cross-seam
foreign keys. Until the store split lands the two halves share one SQLite file,
and the interim rule is that Programming's tables hold the Library's ids as
opaque text (`work_exclusions`, `showings`, `scene_pins`, `default_theme_offers`
are all built that way) and that the one foreign key still crossing,
`theme_memberships.artwork_id`, is the only one. A key added across the seam
would make the split a data migration of two tables' integrity and not one
file's move, and **it looks exactly like success**: a `REFERENCES artworks(id)`
makes the delete protection work, in development and in every test. Nothing but
a reader of the schema notices, and the rule was held until now by reviewers
alone.

**What it reads.** The two schema strings the file is created from
(`CATALOGUE_SCHEMA` in `persistence/sqlite.py`, `DISCOVERY_SCHEMA` in
`persistence/sqlite_discovery.py`, joined as `persistence/file.py` joins them),
read out of those modules' syntax trees so that this guard never imports `arrt`.
They are run into an in-memory SQLite, and `PRAGMA foreign_key_list` is asked of
every table. The result is what the file would carry, including a column added by
`ALTER TABLE ADD COLUMN`, because the store derives that from the same string.

**Every table is classified**, in `OWNER`, and a table the dict does not name
fails by name: a new table is a decision about which side owns it, and a guard
that guessed would call a new Programming table Library and see nothing wrong.

**What it cannot see.** A reference with no `REFERENCES` clause: a Programming
table that stores a Library id as text and joins on it in SQL crosses the seam
without a foreign key (`migrations.py`'s `mark_the_default_theme` is the one such
statement). A table created outside those two strings, or in a second file
(`persistence/kept.py`'s). And the ownership of a table is this file's own
judgment, written here by hand, not read from anywhere.
"""

import ast
import pathlib
import sqlite3

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PERSISTENCE = REPOSITORY_ROOT / "arrt" / "src" / "arrt" / "persistence"

#: The two strings the catalogue file is created from, in the order `file.py` joins them.
SCHEMAS = (("sqlite.py", "CATALOGUE_SCHEMA"), ("sqlite_discovery.py", "DISCOVERY_SCHEMA"))

LIBRARY = "library"
PROGRAMMING = "programming"

#: Which side owns each table of the file: thirteen are Programming's, and the
#: rest are the Library's. A new table is named here by whoever adds it.
OWNER: dict[str, str] = {
    # Library: the catalogue
    "artists": LIBRARY,
    "artworks": LIBRARY,
    "work_facets": LIBRARY,
    "sources": LIBRARY,
    "originals": LIBRARY,
    "renditions": LIBRARY,
    "mat_colors": LIBRARY,
    "acquisition_queue": LIBRARY,
    "history_events": LIBRARY,
    # Library: discovery
    "discovery_runs": LIBRARY,
    "candidate_works": LIBRARY,
    "candidate_images": LIBRARY,
    "affinities": LIBRARY,
    "spend_records": LIBRARY,
    "settings": LIBRARY,
    "watches": LIBRARY,
    "resolve_run_works": LIBRARY,
    "sightings": LIBRARY,
    "run_citations": LIBRARY,
    # Programming
    "themes": PROGRAMMING,
    "theme_memberships": PROGRAMMING,
    "theme_assignments": PROGRAMMING,
    "default_theme_offers": PROGRAMMING,
    "clients": PROGRAMMING,
    "displays": PROGRAMMING,
    "label_outputs": PROGRAMMING,
    "walls": PROGRAMMING,
    "reported_screens": PROGRAMMING,
    "work_exclusions": PROGRAMMING,
    "showings": PROGRAMMING,
    "scenes": PROGRAMMING,
    "scene_pins": PROGRAMMING,
}

#: The foreign keys allowed across the seam, as `(table, column, parent table)`.
#: **This set only shrinks.** When rule 3 removes `theme_memberships.artwork_id`,
#: the test below fails to say so, and the entry goes with it.
ALLOWED_CROSSINGS: frozenset[tuple[str, str, str]] = frozenset({("theme_memberships", "artwork_id", "artworks")})


def test_the_schema_has_tables_to_check():
    """The vacuity check: a read that found nothing would hold every key to nothing."""
    tables = _tables(_connection(_real_schema()))

    assert len(tables) > 20, f"only {sorted(tables)} found; has the schema moved out of {PERSISTENCE}?"
    assert any(_foreign_keys(_connection(_real_schema()), table) for table in tables), "no foreign key at all"


def test_every_table_has_an_owner():
    unclassified = _unclassified(_connection(_real_schema()))

    assert unclassified == [], f"tables with no owner in OWNER (Library or Programming?): {unclassified}"


def test_the_owner_table_names_no_table_the_file_lacks():
    """A renamed or retired table must leave `OWNER` too, or the dict stops describing the file."""
    stale = sorted(set(OWNER) - set(_tables(_connection(_real_schema()))))

    assert stale == [], f"OWNER names tables the schema no longer creates: {stale}"


def test_exactly_the_allowed_foreign_keys_cross_the_seam():
    crossing = _crossing(_connection(_real_schema()))

    assert crossing == ALLOWED_CROSSINGS, _explain(crossing)


class TestTheGuardCanFail:
    """Planted keys and tables, one per way the rule is actually broken."""

    def test_a_second_foreign_key_from_programming_to_a_library_table_fails(self):
        connection = _connection(_real_schema() + "CREATE TABLE showings_v2 (work_id TEXT REFERENCES artworks(id));")
        owner = {**OWNER, "showings_v2": PROGRAMMING}

        crossing = _crossing(connection, owner)

        assert crossing - ALLOWED_CROSSINGS == {("showings_v2", "work_id", "artworks")}

    def test_a_foreign_key_from_a_library_table_to_a_programming_table_fails(self):
        connection = _connection(_real_schema() + "CREATE TABLE seen (wall_id TEXT REFERENCES walls(id));")
        owner = {**OWNER, "seen": LIBRARY}

        crossing = _crossing(connection, owner)

        assert crossing - ALLOWED_CROSSINGS == {("seen", "wall_id", "walls")}

    def test_a_second_key_on_the_allowed_table_fails_by_its_own_column(self):
        """The allowance is one column of one table, not the table: `theme_memberships` may not grow another."""
        connection = _connection(_real_schema() + "CREATE TABLE theme_memberships_extra (a TEXT REFERENCES sources(id));")
        owner = {**OWNER, "theme_memberships_extra": PROGRAMMING}

        crossing = _crossing(connection, owner)

        assert crossing - ALLOWED_CROSSINGS == {("theme_memberships_extra", "a", "sources")}

    def test_a_foreign_key_within_a_side_is_not_a_crossing(self):
        connection = _connection(_real_schema() + "CREATE TABLE pins (scene_id TEXT REFERENCES scenes(id));")
        owner = {**OWNER, "pins": PROGRAMMING}

        assert _crossing(connection, owner) == ALLOWED_CROSSINGS

    def test_a_table_nobody_classified_fails_by_name(self):
        connection = _connection(_real_schema() + "CREATE TABLE brand_new_things (id TEXT PRIMARY KEY);")

        assert _unclassified(connection) == ["brand_new_things"]

    def test_a_key_into_an_unclassified_table_is_reported_not_skipped(self):
        """A crossing that cannot be judged is not a pass."""
        connection = _connection(
            _real_schema() + "CREATE TABLE mystery (id TEXT PRIMARY KEY);\n" "CREATE TABLE pin (m TEXT REFERENCES mystery(id));"
        )

        with pytest.raises(KeyError, match="mystery|pin"):
            _crossing(connection)

    def test_removing_the_allowed_key_is_reported_so_the_allowance_shrinks_with_it(self):
        sql = _real_schema().replace(
            "artwork_id  TEXT NOT NULL REFERENCES artworks(id),\n    position", "artwork_id  TEXT NOT NULL,\n    position"
        )
        assert sql != _real_schema(), "the planted edit matched nothing"

        crossing = _crossing(_connection(sql))

        assert crossing == frozenset()
        assert crossing != ALLOWED_CROSSINGS


# -- the audit ------------------------------------------------------------


def _crossing(connection: sqlite3.Connection, owner: dict[str, str] = OWNER) -> frozenset[tuple[str, str, str]]:
    """Every foreign key whose child and parent tables belong to different sides.

    A table with no owner raises rather than being skipped: a guard that passed
    over what it could not classify would pass for the wrong reason.
    """
    found = set()
    for table in _tables(connection):
        for column, parent in _foreign_keys(connection, table):
            if owner[table] != owner[parent]:
                found.add((table, column, parent))
    return frozenset(found)


def _unclassified(connection: sqlite3.Connection, owner: dict[str, str] = OWNER) -> list[str]:
    return sorted(table for table in _tables(connection) if table not in owner)


def _explain(crossing: frozenset[tuple[str, str, str]]) -> str:
    added = sorted(crossing - ALLOWED_CROSSINGS)
    gone = sorted(ALLOWED_CROSSINGS - crossing)
    lines = [f"cross-seam foreign key {t}.{c} -> {p}: a new one is not allowed (seam rule 3)" for t, c, p in added]
    lines += [f"{t}.{c} -> {p} no longer crosses: remove it from ALLOWED_CROSSINGS, the count only shrinks" for t, c, p in gone]
    return "\n".join(lines)


def _tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [name for (name,) in rows]


def _foreign_keys(connection: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    """`(column, parent table)` for each foreign key a table declares."""
    return [(row[3], row[2]) for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')]


def _connection(schema: str) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(schema)
    return connection


def _real_schema() -> str:
    return "".join(_schema_string(PERSISTENCE / name, constant) for name, constant in SCHEMAS)


def _schema_string(path: pathlib.Path, constant: str) -> str:
    """A module-level string constant, read from the syntax tree without importing the module."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            continue
        if constant in names and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise AssertionError(f"{path} has no module-level string {constant}; has the schema moved?")
