"""The catalogue's shape generation moves whenever its shape does, beyond an addition.

`file.SCHEMA_GENERATION` is what the guard compares (`test_catalogue_opened.py`):
a release refuses a file recorded at a higher generation, and opens one at its
own or a lower one, whatever release numbers the two carry. So a release that
changes the catalogue in a way an older release of the same generation would
mishandle has to raise it, by hand. This test is what makes forgetting fail.

`tests/fixtures/catalogue-generations.json` holds, for every generation, the
shape the open declared and the steps it ran when that generation was raised.
The shape is what SQLite reports of the declared schema, built in memory (each
table's columns with their type, nullability, default and key place, its
single-column references, and its indexes), so reformatting the DDL moves
nothing. **Within a generation the shape may only grow**: a table, a column or
an index added is something an older release of the same generation ignores.
Anything in the recorded shape taken away or declared differently, or a step
the open runs that the generation did not record, fails here until
`SCHEMA_GENERATION` is raised and the new generation's entry is added (the
failure prints it). A value written into a column an older release reads is
beyond what this can see; `SCHEMA_GENERATION`'s comment says so.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from arrt.persistence import file
from arrt.persistence.sqlite import CATALOGUE_SCHEMA
from arrt.persistence.sqlite_discovery import DISCOVERY_SCHEMA

GENERATIONS = Path(__file__).resolve().parents[1] / "fixtures" / "catalogue-generations.json"


def _shape(schema: str) -> dict[str, dict[str, object]]:
    """Every table the schema declares, as SQLite reports it."""
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(schema)
        tables: dict[str, dict[str, object]] = {}
        for (table,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall():
            columns = {
                name: {"type": kind.strip().upper(), "notnull": bool(notnull), "default": default, "pk": pk}
                for _, name, kind, notnull, default, pk in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            }
            references = sorted(
                f"{row[3]} -> {row[2]}.{row[4]}" for row in connection.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
            )
            indexes = {}
            for _, name, unique, origin, partial in connection.execute(f'PRAGMA index_list("{table}")').fetchall():
                indexed = [row[2] for row in connection.execute(f'PRAGMA index_info("{name}")').fetchall()]
                key = name if origin == "c" else f"({origin}) {','.join(map(str, indexed))}"
                indexes[key] = {"unique": bool(unique), "partial": bool(partial), "columns": indexed}
            tables[table] = {"columns": columns, "references": references, "indexes": indexes}
        return tables
    finally:
        connection.close()


def _steps() -> list[str]:
    """The name of every step the open runs, in order, read from the call that builds them."""
    built = file.catalogue_migrations(
        release="0.0.0", wall_name="w", seed_wall=False, now=lambda: datetime(2026, 1, 1, tzinfo=UTC), new_id=str
    )
    return [getattr(step, "func", step).__name__ for step in built]


def _now() -> dict[str, object]:
    return {"tables": _shape(CATALOGUE_SCHEMA + DISCOVERY_SCHEMA + file.OPENED_SCHEMA), "steps": _steps()}


def _recorded() -> dict[int, dict[str, object]]:
    return {int(generation): entry for generation, entry in json.loads(GENERATIONS.read_text(encoding="utf-8")).items()}


def _shrunk(recorded: dict[str, dict[str, object]], current: dict[str, dict[str, object]]) -> list[str]:
    """Everything in the recorded shape that the current one lacks or declares differently; additions are not listed."""
    lost: list[str] = []
    for table, was in recorded.items():
        now = current.get(table)
        if now is None:
            lost.append(f"table {table}")
            continue
        for kind in ("columns", "indexes"):
            for name, declared in was[kind].items():
                found = now[kind].get(name)
                if found != declared:
                    noun = "column" if kind == "columns" else "index"
                    lost.append(f"{table} {noun} {name}: {declared} is now {found}")
        lost.extend(f"{table} reference {reference}" for reference in was["references"] if reference not in now["references"])
    return lost


def _raise_it(reason: str) -> str:
    entry = json.dumps({str(file.SCHEMA_GENERATION + 1): _now()}, indent=2, sort_keys=True)
    return (
        f"{reason}. An older release of generation {file.SCHEMA_GENERATION} would open a file this code left and "
        f"mishandle it: raise file.SCHEMA_GENERATION to {file.SCHEMA_GENERATION + 1} and add this entry to "
        f"{GENERATIONS.name}:\n{entry}"
    )


def test_every_generation_up_to_this_code_s_is_recorded_and_none_beyond_it():
    assert sorted(_recorded()) == list(range(1, file.SCHEMA_GENERATION + 1))


def test_within_this_generation_the_shape_has_only_grown():
    recorded = _recorded()[file.SCHEMA_GENERATION]["tables"]

    lost = _shrunk(recorded, _now()["tables"])

    assert lost == [], _raise_it("Since this generation was recorded the catalogue lost or changed " + "; ".join(lost))


def _not_in_order(steps: list[str], recorded: list[str]) -> list[str]:
    """The steps that are not the recorded ones, in their recorded order, with some left out; a step only removed is fine."""
    out_of_order: list[str] = []
    position = 0
    for step in steps:
        if step in recorded[position:]:
            position = recorded.index(step, position) + 1
        else:
            out_of_order.append(step)
    return out_of_order


def test_within_this_generation_the_open_runs_no_step_it_did_not_record():
    """A step added, run twice or moved is something older code of this generation did not do; one retired is not."""
    added = _not_in_order(_steps(), _recorded()[file.SCHEMA_GENERATION]["steps"])

    assert added == [], _raise_it(f"The open runs {', '.join(added)} where this generation did not record it")


@pytest.mark.parametrize(
    ("steps", "named"),
    [
        (["a", "b", "c"], []),
        (["a", "c"], []),
        (["a", "b", "x", "c"], ["x"]),
        (["a", "b", "b", "c"], ["b"]),
        (["a", "c", "b"], ["b"]),
    ],
    ids=["as recorded", "one retired", "one added", "one run twice", "two swapped"],
)
def test_a_step_added_repeated_or_moved_is_named(steps, named):
    assert _not_in_order(steps, ["a", "b", "c"]) == named


# -- the check can fail, on the shapes it is about --------------------------------

_A_TABLE = "CREATE TABLE things (id TEXT PRIMARY KEY, name TEXT NOT NULL, note TEXT);"


@pytest.mark.parametrize(
    ("later", "lost"),
    [
        ("CREATE TABLE things (id TEXT PRIMARY KEY, name TEXT NOT NULL, note TEXT, added TEXT);", []),
        ("CREATE TABLE things (id TEXT PRIMARY KEY, name TEXT NOT NULL, note TEXT); CREATE TABLE more (x);", []),
        ("CREATE TABLE things (id TEXT PRIMARY KEY, name TEXT NOT NULL);", ["things column note"]),
        ("CREATE TABLE things (id TEXT PRIMARY KEY, name TEXT, note TEXT);", ["things column name"]),
        ("CREATE TABLE others (id TEXT PRIMARY KEY);", ["table things"]),
    ],
    ids=["a column added", "a table added", "a column taken away", "a column redeclared", "a table taken away"],
)
def test_an_addition_passes_and_anything_else_is_named(later, lost):
    found = _shrunk(_shape(_A_TABLE), _shape(later))

    assert [entry.split(":")[0] for entry in found] == lost


def test_an_index_taken_away_is_named():
    indexed = _A_TABLE + "CREATE UNIQUE INDEX things_by_name ON things(name);"

    assert [entry.split(":")[0] for entry in _shrunk(_shape(indexed), _shape(_A_TABLE))] == ["things index things_by_name"]


def test_the_reformatted_ddl_is_the_same_shape():
    assert _shape(_A_TABLE) == _shape(_A_TABLE.replace(" (", "(\n    ").replace(", ", ",\n    ").lower())
