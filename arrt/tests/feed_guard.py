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

**A server run as a process is out of the wrapper's reach.** It imports its own
copy of every module, so a patch in the test process changes nothing it runs.
`published_problems` reads instead what such a server left on disk, every wall's
feed under an art root, and `tests/system/conftest.py` asks it when each server
test ends: the same rules, checked after the fact rather than as each feed is built.
"""

import json
from collections.abc import Callable
from functools import cache, wraps
from pathlib import Path
from typing import Any

from arrt_contract import semantic_errors, validator
from jsonschema import Draft202012Validator


@cache
def _validator() -> Draft202012Validator:
    return validator("schemas/manifest.v2.schema.json")


def problems(document: dict) -> list[str]:
    """Everything a Player would refuse this feed for: the schema's errors, or, when it has none, the semantic rules'.

    The semantic rules read keys the schema requires, so asking them of a
    document the schema refuses would trade the schema's message for a
    `KeyError` traceback.
    """
    schema_errors = [error.message for error in _validator().iter_errors(document)]
    return schema_errors or semantic_errors(document)


def checked(build: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(build)
    def _build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        document = build(*args, **kwargs)
        found = problems(document)
        assert found == [], f"A published major 2 feed breaks the Player contract: {found}"
        return document

    return _build


def published_problems(art_root: Path) -> dict[str, list[str]]:
    """Every wall's feed published under `art_root`, by wall id, with what a Player would refuse it for; a good feed is left out.

    The files are found by the publisher's own name for them
    (`MANIFEST_V2_FILENAME_TEMPLATE`), so a rename of the template moves this with it.
    A file that is not a JSON object is refused as the Player refuses it, before any rule.
    """
    from arrt.programming.manifest.v2 import MANIFEST_V2_FILENAME_TEMPLATE

    before, after = MANIFEST_V2_FILENAME_TEMPLATE.split("{wall_id}")
    found: dict[str, list[str]] = {}
    for path in sorted(art_root.glob(f"{before}*{after}")):
        wall_id = path.name.removeprefix(before).removesuffix(after)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            found[wall_id] = [f"{path.name} is not a readable JSON document ({error})"]
            continue
        wrong = problems(document) if isinstance(document, dict) else [f"{path.name} holds no JSON object"]
        if wrong:
            found[wall_id] = wrong
    return found
