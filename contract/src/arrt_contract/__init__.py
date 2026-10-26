"""The contract between Arrt and every Arrt Player, as one installable version.

`player-contract.md` is the specification. This package is what both sides are
tested against: the JSON Schemas, the fixtures that pin each schema's rules, the
conformance vectors every Player runs, the routes a Player may request, and
`semantic_errors`, the reference statement of the manifest rules a schema cannot
state. They travel together because the schemas alone do not carry those rules,
and a Player pinned to schemas without them would pass documents Arrt refuses.

Arrt owns the source. A Player depends on a released version and reads the
files through `root()`, never by a path of its own, so the version it pins is
the contract it is tested against.
"""

import itertools
import json
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

__all__ = [
    "ContractNotFoundError",
    "fixtures",
    "instant_key",
    "registry",
    "root",
    "routes",
    "schema",
    "semantic_errors",
    "specification",
    "timing",
    "validator",
]

_HERE = Path(__file__).resolve().parent


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


def schema(relative: str) -> dict:
    """One schema, by its path under `root()`, such as `schemas/manifest.v2.schema.json`."""
    return _load(relative)


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
    return keys[0]


def fixtures() -> list[dict]:
    """The fixture index's rows: each fixture's path, its schema, whether it is valid, and what an invalid one breaks."""
    return _load("fixtures/index.json")["fixtures"]


def routes() -> dict[str, dict]:
    """The routes a Player may request, and nothing else, by name: each a `method` and a `path`."""
    return _load("routes.json")["routes"]


def timing() -> dict[str, int]:
    """The heartbeat interval and the staleness threshold in intervals, which no document carries."""
    return {key: value for key, value in _load("timing.json").items() if not key.startswith("_")}


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text)


def semantic_errors(document: dict) -> list[str]:
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
