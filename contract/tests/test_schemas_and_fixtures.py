"""The Player contract's schemas and fixtures agree with each other.

The `arrt-contract` package is what Arrt and Arrt Player are each tested
against, and a released version of it is what Arrt Player pins. So the fixtures are
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

It lives in the package's own suite because a version of the package is a
claim that these agree: each plane's suite checks its side against the same
files, at whatever version it depends on.

**Major 2 has rules no schema can state**: every work the schedule, a scene or
staging names is in `works`, slots run forward in order without overlapping and
stay inside the horizon, and the horizon is whole days. The package's
`semantic_errors` is the reference statement of those rules. A Player enforces
the same ones in its reader, and an invalid fixture is marked as breaking either
the schema or one of these.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from arrt_contract import fixtures, root, schema, semantic_errors, validator

CONTRACT = root()
INDEX = fixtures()


def _document(row: dict) -> dict:
    return json.loads((CONTRACT / row["path"]).read_text(encoding="utf-8"))


def _errors(row: dict) -> list[str]:
    return [error.message for error in validator(row["schema"]).iter_errors(_document(row))]


def _semantics(row: dict) -> list[str]:
    return semantic_errors(_document(row)) if row["schema"] == "schemas/manifest.v2.schema.json" else []


@pytest.mark.parametrize("schema_path", sorted({row["schema"] for row in INDEX}))
def test_every_schema_is_valid_draft_2020_12(schema_path):
    Draft202012Validator.check_schema(schema(schema_path))


def test_the_facts_a_major_2_overlay_may_show_are_exactly_the_label_keys():
    """`settings.facts` names label keys, defined once in major 2's `$defs` and reused by reference.

    The enum is a copy, because a schema cannot list another definition's keys, so
    this is what keeps the copy from drifting: a key added to the label and not
    here would be a fact no setting could ask for.
    """
    facts = schema("schemas/manifest.v2.schema.json")["properties"]["settings"]["properties"]["facts"]["items"]["enum"]
    label = schema("schemas/manifest.v2.schema.json")["$defs"]["label"]["properties"]

    assert facts == list(label)


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

    A reader choosing fixtures by directory, as Arrt Player's suite and the curation
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
    """Arrt Player's suite reads this flag while collecting, so a row without it stops that suite at collection."""
    for row in INDEX:
        if row["path"].startswith("fixtures/manifest.v2/invalid/"):
            assert isinstance(row.get("player_must_refuse"), bool), row["path"]
