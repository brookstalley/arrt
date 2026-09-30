"""The Player contract's schemas and fixtures agree with each other.

The contract under `contract/` is what Curatarr and Displayarr are each tested
against, and after the repo split it is what Displayarr pins. So the fixtures are
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
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
INDEX = json.loads((CONTRACT / "fixtures" / "index.json").read_text(encoding="utf-8"))["fixtures"]


def _validator(schema_path: str) -> Draft202012Validator:
    schema = json.loads((CONTRACT / schema_path).read_text(encoding="utf-8"))
    # The format checker is passed so that a validator which does check formats
    # checks them; the schemas do not rely on it, because without an optional
    # package `date-time` is not checked at all, and each instant carries a
    # pattern for that reason.
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _errors(row: dict) -> list[str]:
    document = json.loads((CONTRACT / row["path"]).read_text(encoding="utf-8"))
    return [error.message for error in _validator(row["schema"]).iter_errors(document)]


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


@pytest.mark.parametrize("row", [row for row in INDEX if not row["valid"]], ids=lambda row: row["path"])
def test_an_invalid_fixture_breaks_exactly_one_rule(row):
    assert len(_errors(row)) == 1, _errors(row)


def test_invalid_manifests_say_whether_a_player_must_refuse_them():
    """The display suite reads this flag; a row without it would be skipped there, not failed."""
    for row in INDEX:
        if row["path"].startswith("fixtures/manifest.v1/invalid/"):
            assert isinstance(row.get("player_must_refuse"), bool), row["path"]
