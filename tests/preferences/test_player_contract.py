"""The Player contract's schemas and fixtures agree with each other.

The contract under `contract/` is what Curatarr and Arrt are each tested
against, and after the repo split it is what Arrt pins. So the fixtures are
a claim about the schemas, and this file is what makes the claim true: every
valid fixture validates, and every invalid one fails for exactly one reason.

**Exactly one, not at least one.** An invalid fixture's filename names the rule it
breaks. A fixture that also breaks a second rule by accident, a typo in an
unrelated field, would still fail, and would go on failing after the rule it
names had been deleted from the schema. Counting the errors is what makes each
fixture defend the rule it is named for.

**The index is checked in both directions.** A fixture on disk that the index does
not list is one no test reads, and an index row with no file is a test that
passes by reading nothing.

It lives in the root suite because the contract belongs to neither plane: each
plane's own suite checks its side against these same files.

**Major 2 has rules no schema can state**: every work the schedule, a scene or
staging names is in `works`, slots run forward in order without overlapping and
stay inside the horizon, and the horizon is whole days. `semantic_errors` below is
the reference statement of those rules. A Player enforces the same ones when
wave 4 builds its reader, and an invalid fixture is marked as breaking either the
schema or one of these.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
INDEX = json.loads((CONTRACT / "fixtures" / "index.json").read_text(encoding="utf-8"))["fixtures"]


def _schema(schema_path: str) -> dict:
    return json.loads((CONTRACT / schema_path).read_text(encoding="utf-8"))


# Every schema, registered under its $id, so a reference from one major to another
# (major 2 reuses major 1's label) resolves to the file on disk rather than to a
# URL nobody serves.
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema))
    for schema in (_schema(str(path.relative_to(CONTRACT))) for path in (CONTRACT / "schemas").glob("*.json"))
)


def _validator(schema_path: str) -> Draft202012Validator:
    # The format checker is passed so that a validator which does check formats
    # checks them; the schemas do not rely on it, because without an optional
    # package `date-time` is not checked at all, and each instant carries a
    # pattern for that reason.
    return Draft202012Validator(_schema(schema_path), registry=REGISTRY, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _document(row: dict) -> dict:
    return json.loads((CONTRACT / row["path"]).read_text(encoding="utf-8"))


def _errors(row: dict) -> list[str]:
    return [error.message for error in _validator(row["schema"]).iter_errors(_document(row))]


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text)


def semantic_errors(document: dict) -> list[str]:
    """The major 2 rules a schema cannot state, each broken rule reported once."""
    errors = []
    works = document["works"]
    slots = document["schedule"]["slots"]
    scene = document["scene"]
    named = [slot["work_id"] for slot in slots] + document["staging"] + ([scene["work_id"]] if scene else [])
    if any(work_id not in works for work_id in named):
        errors.append("a work is named that is not in works")
    if any(_instant(slot["from"]) >= _instant(slot["until"]) for slot in slots):
        errors.append("a slot ends before it starts")
    elif any(_instant(first["until"]) > _instant(second["from"]) for first, second in zip(slots, slots[1:], strict=False)):
        errors.append("slots overlap or are out of order")
    horizon_from = _instant(document["schedule"]["horizon"]["from"])
    horizon_until = _instant(document["schedule"]["horizon"]["until"])
    span = horizon_until - horizon_from
    if span <= timedelta(0) or span % timedelta(days=1):
        errors.append("the horizon is not a whole number of days")
    if any(_instant(slot["from"]) < horizon_from or _instant(slot["until"]) > horizon_until for slot in slots):
        errors.append("a slot falls outside the horizon")
    if scene and scene["until"] is not None and _instant(scene["until"]) <= _instant(scene["from"]):
        errors.append("the scene ends before it starts")
    return errors


def _semantics(row: dict) -> list[str]:
    return semantic_errors(_document(row)) if row["schema"] == "schemas/manifest.v2.schema.json" else []


@pytest.mark.parametrize("schema_path", sorted({row["schema"] for row in INDEX}))
def test_every_schema_is_valid_draft_2020_12(schema_path):
    Draft202012Validator.check_schema(json.loads((CONTRACT / schema_path).read_text(encoding="utf-8")))


def test_every_fixture_on_disk_is_indexed_and_every_indexed_fixture_exists():
    on_disk = {str(path.relative_to(CONTRACT)) for path in (CONTRACT / "fixtures").rglob("*.json") if path.name != "index.json"}
    indexed = {row["path"] for row in INDEX}

    assert on_disk - indexed == set(), "fixtures no test reads"
    assert indexed - on_disk == set(), "index rows with no file"


def test_every_schema_on_disk_is_judged_by_some_fixture():
    on_disk = {str(path.relative_to(CONTRACT)) for path in (CONTRACT / "schemas").glob("*.json")}

    assert on_disk - {row["schema"] for row in INDEX} == set()


def test_every_schema_has_valid_and_invalid_fixtures():
    """A schema with no invalid fixture could accept anything and still pass."""
    for schema_path in {row["schema"] for row in INDEX}:
        kinds = {row["valid"] for row in INDEX if row["schema"] == schema_path}
        assert kinds == {True, False}, schema_path


@pytest.mark.parametrize("row", [row for row in INDEX if row["valid"]], ids=lambda row: row["path"])
def test_a_valid_fixture_validates(row):
    assert _errors(row) == []
    assert _semantics(row) == []


@pytest.mark.parametrize(
    "row", [row for row in INDEX if not row["valid"] and row["breaks"] == "schema"], ids=lambda row: row["path"]
)
def test_a_fixture_invalid_by_schema_breaks_exactly_one_rule(row):
    assert len(_errors(row)) == 1, _errors(row)


@pytest.mark.parametrize(
    "row", [row for row in INDEX if not row["valid"] and row["breaks"] == "semantics"], ids=lambda row: row["path"]
)
def test_a_fixture_invalid_by_semantics_passes_the_schema_and_breaks_exactly_one_rule(row):
    assert _errors(row) == []
    assert len(_semantics(row)) == 1, _semantics(row)


def test_each_fixtures_directory_agrees_with_its_flag():
    """`valid/` holds only valid fixtures and `invalid/` only invalid ones.

    A reader choosing fixtures by directory, as Arrt's suite and the curation
    plane's both do, would otherwise be told the opposite of what the index says.
    """
    for row in INDEX:
        directory = Path(row["path"]).parent.name
        assert directory in {"valid", "invalid"}, row["path"]
        assert (directory == "valid") == row["valid"], row["path"]


def test_every_invalid_fixture_says_what_it_breaks():
    for row in INDEX:
        if not row["valid"]:
            assert row.get("breaks") in {"schema", "semantics"}, row["path"]


def test_invalid_manifests_say_whether_a_player_must_refuse_them():
    """Arrt's suite reads this flag while collecting, so a row without it stops that suite at collection."""
    for row in INDEX:
        if row["path"].startswith("fixtures/manifest.v1/invalid/"):
            assert isinstance(row.get("player_must_refuse"), bool), row["path"]
