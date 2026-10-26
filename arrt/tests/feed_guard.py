"""Every major 2 feed this suite publishes keeps the Player contract, checked where it is built.

A Player refuses a document that breaks the schema or one of the rules a schema
cannot state, and keeps its last good one, so a server that published one would
leave a wall stale with nothing on the server saying why. Checking one feed in
one test would leave every other publish path (a theme edit, show now, a
withdrawal, a horizon rolled forward) unchecked, so `conftest.py` wraps the
builder for every test.

**The rules are the contract package's reference statement**, imported, not
copied: a copy here would be a second statement free to drift from the one the
fixtures are held to.
"""

from collections.abc import Callable
from functools import cache, wraps
from typing import Any

from arrt_contract import semantic_errors, validator
from jsonschema import Draft202012Validator


@cache
def _validator() -> Draft202012Validator:
    return validator("schemas/manifest.v2.schema.json")


def problems(document: dict) -> list[str]:
    """Everything a Player would refuse this feed for, schema first."""
    return [error.message for error in _validator().iter_errors(document)] + semantic_errors(document)


def checked(build: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(build)
    def _build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        document = build(*args, **kwargs)
        found = problems(document)
        assert found == [], f"A published major 2 feed breaks the Player contract: {found}"
        return document

    return _build
