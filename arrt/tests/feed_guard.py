"""Every major 2 feed this suite publishes keeps the Player contract, checked where it is built.

A Player refuses a document that breaks the schema or one of the rules a schema
cannot state, and keeps its last good one, so a server that published one would
leave a wall stale with nothing on the server saying why. Checking one feed in
one test would leave every other publish path (a theme edit, show now, a
withdrawal, a horizon rolled forward) unchecked, so `conftest.py` wraps the
builder for every test.

**The rules are the root suite's reference statement**, loaded from its file,
not copied: the contract belongs to neither plane, and a copy here would be a
second statement free to drift from the one the fixtures are held to.
"""

import importlib.util
import json
from collections.abc import Callable
from functools import cache, wraps
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contract"


@cache
def _validator() -> Draft202012Validator:
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in (CONTRACT / "schemas").glob("*.json")]
    registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas)
    feed = next(schema for schema in schemas if schema["$id"].endswith("manifest.v2.schema.json"))
    return Draft202012Validator(feed, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER)


@cache
def _semantic_errors() -> Callable[[dict], list[str]]:
    spec = importlib.util.spec_from_file_location(
        "contract_reference", ROOT / "tests" / "preferences" / "test_player_contract.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.semantic_errors


def problems(document: dict) -> list[str]:
    """Everything a Player would refuse this feed for, schema first."""
    return [error.message for error in _validator().iter_errors(document)] + _semantic_errors()(document)


def checked(build: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(build)
    def _build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        document = build(*args, **kwargs)
        found = problems(document)
        assert found == [], f"A published major 2 feed breaks the Player contract: {found}"
        return document

    return _build
