"""The contract between Arrt and every Arrt Player, as one installable version.

`player-contract.md` is the specification. This package is what both sides are
tested against: the JSON Schemas, the fixtures that pin each schema's rules, the
conformance vectors every Player runs, the routes a Player may request, and
`semantic_errors`, the reference statement of the manifest's and the client heartbeat's rules a schema cannot
state, what each route answers (`transport`), the household's words both sides
say (`vocabulary`), and frozen copies of each released minor (`released`). They
travel together because the schemas alone do not carry those rules,
and a Player pinned to schemas without them would pass documents Arrt refuses.

Arrt owns the source. A Player depends on a released version and reads the
files through `root()`, never by a path of its own, so the version it pins is
the contract it is tested against.
"""

import itertools
import json
import re
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

__all__ = [
    "MAX_OUTPUTS_PER_REPORT",
    "ContractNotFoundError",
    "fixtures",
    "instant_key",
    "registry",
    "released",
    "root",
    "routes",
    "schema",
    "semantic_errors",
    "specification",
    "timing",
    "transport",
    "validator",
    "vocabulary",
]

_HERE = Path(__file__).resolve().parent

#: A frozen release's directory name: three whole numbers, none with a leading zero.
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class ContractNotFoundError(RuntimeError):
    """The package is installed without its data, which is a broken build, not an empty contract."""


@cache
def root() -> Path:
    """The directory holding `schemas/`, `fixtures/`, `vectors/`, `routes.json` and `timing.json`.

    An installed wheel carries the data inside the package. A checkout of Arrt
    keeps it in `contract/`, where the specification's paths name it, two levels
    above the package's `src/` layout. Any
    other layout is refused by name: a contract that resolved to nothing would
    give every parametrised test zero cases, and an empty run reads as a pass.
    """
    for candidate in (_HERE, _HERE.parents[1]):
        if (candidate / "schemas").is_dir() and (candidate / "routes.json").is_file():
            return candidate
    raise ContractNotFoundError(f"no contract data at {_HERE} or {_HERE.parents[1]}")


def specification() -> Path:
    """`player-contract.md` as released with this version: in the package when installed, beside it in a checkout."""
    for candidate in (_HERE / "player-contract.md", _HERE.parents[1] / "player-contract.md"):
        if candidate.is_file():
            return candidate
    raise ContractNotFoundError(f"no player-contract.md in {_HERE} or {_HERE.parents[1]}")


def _load(relative: str) -> Any:  # noqa: ANN401 -- a JSON document is any JSON value
    return json.loads((root() / relative).read_text(encoding="utf-8"))


def schema(relative: str) -> dict[str, Any]:
    """One schema, by its path under `root()`, such as `schemas/manifest.v2.schema.json`."""
    document: dict[str, Any] = _load(relative)
    return document


@cache
def registry() -> Registry:
    """Every schema under its `$id`, so a reference between schemas resolves here rather than to a URL nobody serves."""
    schemas = (schema(str(path.relative_to(root()))) for path in sorted((root() / "schemas").glob("*.json")))
    return Registry().with_resources((document["$id"], Resource.from_contents(document)) for document in schemas)


def validator(relative: str) -> Draft202012Validator:
    """A validator for one schema, with every other schema registered.

    The format checker is passed so that a validator which does check formats
    checks them. The schemas do not rely on it: without an optional package
    `date-time` is not checked at all, and each instant carries a pattern for
    that reason.
    """
    return Draft202012Validator(schema(relative), registry=registry(), format_checker=Draft202012Validator.FORMAT_CHECKER)


def instant_key(relative: str) -> str:
    """The key a document's own instant is reported under: its one required `date-time` property.

    A heartbeat's writer and reader each spell it as a constant of their own, and
    a reader that finds the instant under another spelling reads the heartbeat as
    unreadable, which reports a running Player as down. Each side holds its
    constant to this, so the two agree because each agrees with the contract.
    A schema with no such key, or more than one, is refused by name.
    """
    document = schema(relative)
    properties = document.get("properties", {})
    keys = [key for key in document.get("required", []) if properties.get(key, {}).get("format") == "date-time"]
    if len(keys) != 1:
        raise ValueError(f"{relative} has {len(keys)} required date-time properties, not one: {keys}")
    key: str = keys[0]
    return key


def fixtures() -> list[dict[str, Any]]:
    """The fixture index's rows: each fixture's path, its schema, whether it is valid, and what an invalid one breaks."""
    rows: list[dict[str, Any]] = _load("fixtures/index.json")["fixtures"]
    return rows


def routes() -> dict[str, dict[str, str]]:
    """The routes a Player may request, and nothing else, by name: each a `method` and a `path`."""
    named: dict[str, dict[str, str]] = _load("routes.json")["routes"]
    return named


def timing() -> dict[str, int]:
    """The heartbeat interval and the staleness threshold in intervals, which no document carries."""
    return {key: value for key, value in _load("timing.json").items() if not key.startswith("_")}


def transport() -> dict[str, Any]:
    """What each route answers and what each answer means to a Player: `transport.json`.

    `routes` holds, for each route `routes()` names, its `answers` (one row per
    status a Player may meet: `case`, `status`, `body`, `means`, `player`), the
    schema of the document it serves or takes, and for a document its
    `max_bytes`. Beside them: `conditional_get` (the ETag rule and its cases),
    `unanswered` (what any 5xx or no answer means), `error_body` and
    `size_bounds`. `player-contract.md` § Transport is the prose of it.
    """
    table: dict[str, Any] = _load("transport.json")
    return table


def vocabulary() -> dict[str, Any]:
    """The household's words both sides say alike: `vocabulary.json`.

    `display_states` maps each display state to its `word`, who reports it
    (`reported_by`), whether it is a setup step (`setup`) and what it `means`;
    `player_states` (since 1.3.0) maps each state a Player can be in to its
    `word`, `setup` and `means`, a `{date}` in a word being the date of the
    report it names; `pairing` names the settings page's two pairing fields.
    """
    words: dict[str, Any] = _load("vocabulary.json")
    return words


def released() -> dict[str, Path]:
    """Each released version's frozen copy, by version: a directory holding what that release held.

    Every copy holds its `fixtures/` (the index included), `routes.json` and
    `sha256.json`; from 1.2.0 on, which introduced them, it holds the release's
    `transport.json` and `vocabulary.json` too, so 1.0.0's and 1.1.0's copies
    have neither. Copied from the release's tag when it was cut
    (`contract/tools/freeze_release.py`), with `sha256.json` recording each
    file's hash then. A consumer can hold itself to what an older Player or
    server was tested against: every valid fixture of a release this major
    still validates at this version, every answer and word of one from 1.2.0 on
    still holds (`contract/tests/test_released.py`).

    Oldest first by version, compared as three whole numbers, so `1.9.0` comes
    before `1.10.0`; the last entry is the latest. A directory under `released/`
    whose name is not a version is refused by name (`ValueError`), because one
    ordered by its spelling would sit in the order wherever the letters put it.
    """
    frozen = [path for path in (root() / "released").iterdir() if path.is_dir()]
    return {path.name: path for path in sorted(frozen, key=_version_of)}


def _version_of(path: Path) -> tuple[int, int, int]:
    """The `(major, minor, patch)` a frozen release's directory name spells; refuses a name that is not one."""
    found = _VERSION.fullmatch(path.name)
    if found is None:
        raise ValueError(f"{path} is under released/ and is not named for a version (major.minor.patch)")
    major, minor, patch = found.groups()
    return int(major), int(minor), int(patch)


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text)


#: How many outputs, and how many label outputs, one client heartbeat may carry
#: (since 1.3.0): a rule of the client heartbeat's that its schema does not
#: state, so a report over it breaks `semantic_errors`. Far above any Player (a
#: Pi drives two screens and a handful of panels); the server keeps a row for
#: each output a report names, so without it a token holder could have it keep
#: as many as a request body holds. The server quotes this value.
MAX_OUTPUTS_PER_REPORT: Final[int] = 32

#: The schemas with rules no schema can state, by path under `root()`.
_MANIFEST = "schemas/manifest.v2.schema.json"
_CLIENT_HEARTBEAT = "schemas/client-heartbeat.v1.schema.json"


def semantic_errors(document: dict[str, Any], schema: str = _MANIFEST) -> list[str]:
    """The rules a schema cannot state, for the document's schema, each broken rule reported once.

    `schema` is the document's schema by its path under `root()`, as the fixture
    index names it, and is the manifest's when not given. Two have such rules:
    the manifest (major 2, below) and, since 1.3.0, the client heartbeat, where no
    two outputs and no two label outputs share a name, and a report carries at
    most `MAX_OUTPUTS_PER_REPORT` of each (`player-contract.md` § Transport).
    Any other schema has none, which is `[]`; a path that names no schema is
    refused (`ValueError`), because reading it as one with no rules
    would pass every document.
    """
    if schema == _CLIENT_HEARTBEAT:
        return _client_heartbeat_errors(document)
    if schema == _MANIFEST:
        return _manifest_errors(document)
    if not schema.startswith("schemas/") or not (root() / schema).is_file():
        raise ValueError(f"{schema} is not a schema of this contract")
    return []


def _client_heartbeat_errors(document: dict[str, Any]) -> list[str]:
    """No two outputs share a name, nor two label outputs; a report carries at most `MAX_OUTPUTS_PER_REPORT` of each.

    A name is how a wall or a label is placed on one. For a document the schema
    accepts, as for the manifest's rules.
    """
    errors = []
    names = [output["name"] for output in document["outputs"]]
    if len(names) > MAX_OUTPUTS_PER_REPORT:
        errors.append(f"more than {MAX_OUTPUTS_PER_REPORT} outputs")
    if len(names) != len(set(names)):
        errors.append("two outputs share a name")
    label_names = [label_output["name"] for label_output in document.get("label_outputs", [])]
    if len(label_names) > MAX_OUTPUTS_PER_REPORT:
        errors.append(f"more than {MAX_OUTPUTS_PER_REPORT} label outputs")
    if len(label_names) != len(set(label_names)):
        errors.append("two label outputs share a name")
    return errors


def _manifest_errors(document: dict[str, Any]) -> list[str]:
    """The major 2 rules a schema cannot state, each broken rule reported once.

    Every work the schedule, a scene or staging names is in `works`; slots run
    forward in order without overlapping and stay inside the horizon; the
    horizon is whole days; a scene with an end ends after it starts. A Player
    enforces the same rules in its own reader, and Arrt checks every feed it
    publishes against this statement of them.

    **For a document the schema accepts.** These rules are about the values of
    keys the schema requires, so a caller validates first and asks this only of
    a document with no schema errors; a document missing `works` or `schedule`
    raises `KeyError` here rather than being reported twice.
    """
    errors = []
    works = document["works"]
    slots = document["schedule"]["slots"]
    # A channel's feed carries no control layer, so scene and staging may be absent.
    scene = document.get("scene")
    named = [slot["work_id"] for slot in slots] + document.get("staging", []) + ([scene["work_id"]] if scene else [])
    if any(work_id not in works for work_id in named):
        errors.append("a work is named that is not in works")
    if any(_instant(slot["from"]) >= _instant(slot["until"]) for slot in slots):
        errors.append("a slot ends before it starts")
    elif any(_instant(first["until"]) > _instant(second["from"]) for first, second in itertools.pairwise(slots)):
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
