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
the schema or one of these. Since 1.3.0 the client heartbeat has two such rules
as well (no two outputs, and no two label outputs, share a name), which the
server enforces as its reader.
"""

import json
from pathlib import Path
from urllib.parse import urldefrag, urljoin

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
    return semantic_errors(_document(row), row["schema"])


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


#: Superseded in contract 1.2.0 and kept required until heartbeat major 2: a
#: required key made optional is a writer change an older reader refuses.
SUPERSEDED = ("television_reachable", "television_showing_art", "has_label_surface", "label_surface_working")


@pytest.mark.parametrize("name", SUPERSEDED)
def test_a_superseded_wall_heartbeat_field_is_said_to_be_and_is_still_required(name):
    heartbeat = schema("schemas/heartbeat.v1.schema.json")

    assert name in heartbeat["required"]
    assert heartbeat["properties"][name]["description"].startswith("Superseded")


def test_invalid_client_heartbeats_say_whether_the_server_must_refuse_them():
    """Arrt's suite reads this flag to choose its 400 test or its tolerance test; a row without it is one neither runs."""
    rows = [row for row in INDEX if row["path"].startswith("fixtures/client-heartbeat.v1/invalid/")]

    assert rows
    for row in rows:
        assert isinstance(row.get("server_must_refuse"), bool), row["path"]
    assert {row["server_must_refuse"] for row in rows} == {True, False}


def test_invalid_manifests_say_whether_a_player_must_refuse_them():
    """Arrt Player's suite reads this flag while collecting, so a row without it stops that suite at collection."""
    for row in INDEX:
        if row["path"].startswith("fixtures/manifest.v2/invalid/"):
            assert isinstance(row.get("player_must_refuse"), bool), row["path"]


# -- every constraint a schema states has a fixture that breaks it alone (1.3.0) ------
#
# A Player's readers are written by hand, so a schema's constraint that no invalid
# fixture breaks is one no Player is ever tested to enforce. Until 1.3.0 most had
# none (audit-3: about 20 of 26 in client.v1, 17 of 22 and 81 of 86 elsewhere).
#
# A constraint is one assertion keyword at one place in a schema, named by its
# schema file and the JSON pointer to the keyword, such as
# `schemas/client.v1.schema.json#/properties/walls/items/required`. `required` is one
# constraint however many keys it lists, as the validator reports it once. A
# definition under `$defs` is one place, however many references reach it. What
# `if` and `not` hold is a condition, not a constraint; `oneOf` and `contains` are
# one constraint each, since the validator reports each as one error whatever
# inside it failed. `format` is not counted: the validator does not check the
# formats these schemas name (held below), so no fixture can break one alone, and
# each instant carries a pattern for that reason.
#
# Each invalid fixture's row names the constraint it breaks (`constraint`) and says
# why it is refused (`refused_because`). The constraint is checked against where the
# validator says the fixture failed, so a row cannot name one its fixture does not
# break; for a fixture that breaks a rule no schema states, it is that rule's words
# as `semantic_errors` reports them.

#: Keywords that assert something of an instance, and are counted.
ASSERTIONS = frozenset(
    {
        "type",
        "enum",
        "const",
        "required",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
        "dependentRequired",
        "oneOf",
        "anyOf",
        "contains",
    }
)
#: Keywords holding named subschemas, each walked.
NAMED_SUBSCHEMAS = frozenset({"properties", "$defs", "patternProperties", "dependentSchemas"})
#: Keywords holding one subschema, walked.
ONE_SUBSCHEMA = frozenset({"items", "additionalProperties", "propertyNames", "then", "else"})
#: Keywords whose subschemas are not walked: a condition (`if`, `not`) or one error whatever inside failed.
NOT_WALKED = frozenset({"if", "not", "oneOf", "anyOf", "allOf", "contains"})
#: Keywords that are annotations here, not constraints (see above).
ANNOTATIONS = frozenset({"format", "description", "title", "$schema", "$id", "$ref", "$comment", "default", "examples"})

SCHEMAS = {
    str(path.relative_to(CONTRACT)): schema(str(path.relative_to(CONTRACT)))
    for path in sorted((CONTRACT / "schemas").glob("*.json"))
}
_BY_ID = {document["$id"]: relative for relative, document in SCHEMAS.items()}


def _escaped(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def constraints_of(relative: str, node: dict, pointer: str = "") -> list[str]:
    """Every constraint `node` states, at `pointer` in the schema file `relative`; a keyword it does not know is refused."""
    found = []
    for keyword, value in node.items():
        if keyword in ASSERTIONS or (keyword == "additionalProperties" and value is False):
            found.append(f"{relative}#{pointer}/{keyword}")
        if keyword in NAMED_SUBSCHEMAS:
            for name, subschema in value.items():
                found += constraints_of(relative, subschema, f"{pointer}/{keyword}/{_escaped(name)}")
        elif keyword in ONE_SUBSCHEMA and isinstance(value, dict):
            found += constraints_of(relative, value, f"{pointer}/{keyword}")
        elif keyword not in ASSERTIONS | NOT_WALKED | ANNOTATIONS | NAMED_SUBSCHEMAS | ONE_SUBSCHEMA:
            raise ValueError(f"{relative}#{pointer} uses {keyword}, which this count does not know how to read")
    return found


def every_constraint() -> list[str]:
    return [found for relative, document in SCHEMAS.items() for found in constraints_of(relative, document)]


def where_it_failed(relative: str, schema_path: list) -> str:
    """The constraint a validator error's `absolute_schema_path` names, following each `$ref` to the place it points.

    The validator's path reads as if every reference were inlined, so a step the
    current subschema does not hold is taken inside the subschema its `$ref` names.
    """
    node, pointer, base = SCHEMAS[relative], "", SCHEMAS[relative]["$id"]
    for step in schema_path:
        while isinstance(node, dict) and "$ref" in node and step not in node:
            target, fragment = urldefrag(urljoin(base, node["$ref"]))
            relative, base, node, pointer = _BY_ID[target], target, SCHEMAS[_BY_ID[target]], ""
            for part in (part for part in fragment.split("/") if part):
                node, pointer = node[part], f"{pointer}/{part}"
        node, pointer = node[step], f"{pointer}/{_escaped(str(step))}"
    return f"{relative}#{pointer}"


def _failed_at(row: dict) -> list[str]:
    return [
        where_it_failed(row["schema"], list(error.absolute_schema_path))
        for error in validator(row["schema"]).iter_errors(_document(row))
    ]


INVALID = [row for row in INDEX if not row["valid"]]


@pytest.mark.parametrize("row", INVALID, ids=lambda row: row["path"])
def test_an_invalid_fixture_breaks_the_constraint_its_row_names_and_says_why(row):
    if row["breaks"] == "schema":
        assert _failed_at(row) == [row["constraint"]]
    else:
        assert _semantics(row) == [row["constraint"]]
    assert isinstance(row["refused_because"], str), row["path"]
    assert row["refused_because"].strip() == row["refused_because"], row["path"]
    assert row["refused_because"], row["path"]


def test_every_constraint_a_schema_states_has_a_fixture_that_breaks_it_alone():
    named = {row.get("constraint") for row in INVALID if row["breaks"] == "schema"}
    unbroken = [found for found in every_constraint() if found not in named]
    counts = {relative: sum(found.startswith(f"{relative}#") for found in unbroken) for relative in SCHEMAS}

    assert unbroken == [], f"constraints no fixture breaks, by schema: {counts}"


def test_every_constraint_a_row_names_is_one_a_schema_states():
    stated = set(every_constraint())

    assert [row["path"] for row in INVALID if row["breaks"] == "schema" and row.get("constraint") not in stated] == []


def test_the_validator_does_not_check_the_formats_the_schemas_name():
    """Why `format` is not counted: were it checked, a fixture breaking a pattern would break the format too."""
    named = {value for document in SCHEMAS.values() for value in _values_of(document, "format")}

    assert named == {"date-time", "uri", "uri-reference"}
    for name in named:
        assert Draft202012Validator({"format": name}, format_checker=Draft202012Validator.FORMAT_CHECKER).is_valid(
            "not a ' value"
        )


def _values_of(node: object, keyword: str) -> list:
    if isinstance(node, dict):
        return [value for key, value in node.items() if key == keyword] + [
            found for value in node.values() for found in _values_of(value, keyword)
        ]
    if isinstance(node, list):
        return [found for value in node for found in _values_of(value, keyword)]
    return []


# The walk and the lookup, on a schema written for them: one of each shape they read.
_SAMPLE = {
    "$id": "https://example.invalid/sample.json",
    "type": "object",
    "required": ["a", "b"],
    "additionalProperties": False,
    "properties": {
        "a": {"type": "string", "format": "date-time", "pattern": "^x$"},
        "b": {"$ref": "#/$defs/thing"},
        "c": {"oneOf": [{"type": "null"}, {"type": "integer", "minimum": 1}]},
        "d": {"type": "array", "items": {"enum": [1]}, "contains": {"const": 1}},
    },
    "if": {"properties": {"a": {"not": {"const": "x"}}}},
    "then": {"properties": {"b": {"const": None}}},
    "$defs": {"thing": {"type": "object", "properties": {"e": {"minLength": 1}}}},
}


def test_the_walk_counts_each_assertion_once_and_nothing_inside_a_condition_or_a_one_of():
    assert constraints_of("sample", _SAMPLE) == [
        "sample#/type",
        "sample#/required",
        "sample#/additionalProperties",
        "sample#/properties/a/type",
        "sample#/properties/a/pattern",
        "sample#/properties/c/oneOf",
        "sample#/properties/d/type",
        "sample#/properties/d/items/enum",
        "sample#/properties/d/contains",
        "sample#/then/properties/b/const",
        "sample#/$defs/thing/type",
        "sample#/$defs/thing/properties/e/minLength",
    ]


def test_the_walk_refuses_a_keyword_it_does_not_know():
    with pytest.raises(ValueError, match="unevaluatedProperties"):
        constraints_of("sample", {"unevaluatedProperties": False})


def test_the_lookup_follows_a_reference_to_the_definition_it_names(monkeypatch):
    monkeypatch.setitem(SCHEMAS, "sample", _SAMPLE)
    monkeypatch.setitem(_BY_ID, _SAMPLE["$id"], "sample")

    assert (
        where_it_failed("sample", ["properties", "b", "properties", "e", "minLength"])
        == "sample#/$defs/thing/properties/e/minLength"
    )
    assert where_it_failed("sample", ["properties", "a", "pattern"]) == "sample#/properties/a/pattern"


def test_a_schema_with_no_rules_beyond_itself_has_none_and_a_path_that_is_no_schema_is_refused():
    document = _document(next(row for row in INDEX if row["schema"] == "schemas/client.v1.schema.json" and row["valid"]))

    assert semantic_errors(document, "schemas/client.v1.schema.json") == []
    for stray in ("schemas/client.v2.schema.json", "routes.json", "../pyproject.toml"):
        with pytest.raises(ValueError, match="is not a schema"):
            semantic_errors(document, stray)


def test_the_manifest_is_the_schema_semantic_errors_reads_when_none_is_named():
    """A caller from before 1.3.0 passes the document alone, and is asked the manifest's rules as it was."""
    manifests = [row for row in INVALID if row["breaks"] == "semantics" and row["schema"] == "schemas/manifest.v2.schema.json"]

    assert manifests
    for row in manifests:
        assert semantic_errors(_document(row)) == semantic_errors(_document(row), row["schema"]) == [row["constraint"]]


def test_the_lookup_follows_a_reference_into_another_schema():
    """label.v1's label is manifest.v2's, by a reference across files."""
    relative = "schemas/label.v1.schema.json"
    path = ["properties", "label", "oneOf", 1, "properties", "title", "type"]

    assert where_it_failed(relative, path) == "schemas/manifest.v2.schema.json#/$defs/label/properties/title/type"
