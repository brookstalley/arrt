"""A minor is additive: everything a released version of this major accepted, this version accepts.

`player-contract.md` § Versioning says a new minor is additive and a released tag
is not moved, and until this file that was held by review alone. A Player pins a
tag; a server built from this checkout serves it. So each release's fixtures and
routes are kept here as they were at the tag (`released/<version>/`, copied once
when it was cut, `sha256.json` recording each file's hash), and held to HEAD:

- **every valid fixture of a release validates at HEAD**, the schema and the
  rules no schema states, so a document an older writer produces is still a
  document;
- **every invalid fixture of a release is still invalid at HEAD**, unless the
  loosening is recorded in `LOOSENED` with its reason. A minor that loosens a
  writer's obligation lets a new writer send what an older reader refuses
  (heartbeat minor 4 did, deliberately, deployed server first), so it is a
  decision, never a side effect;
- **no route and no fixture of a release is gone** within the major, and a
  route keeps its method and its path;
- **each frozen file is the bytes it was**, so a release cannot be edited into
  agreement with HEAD.
"""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import pytest

from arrt_contract import fixtures, released, root, routes, semantic_errors, validator

RELEASES = released()
HEAD_MAJOR = int(version("arrt-contract").split(".")[0])

#: Invalid fixtures of a release that HEAD accepts, each with the decision that
#: loosened its rule. Empty: no minor since the first frozen release has loosened one.
LOOSENED: dict[tuple[str, str], str] = {}


def _index(release: Path) -> list[dict]:
    return json.loads((release / "fixtures" / "index.json").read_text(encoding="utf-8"))["fixtures"]


def _document(release: Path, row: dict) -> dict:
    return json.loads((release / row["path"]).read_text(encoding="utf-8"))


def _errors_at_head(release: Path, row: dict) -> list[str]:
    document = _document(release, row)
    errors = [error.message for error in validator(row["schema"]).iter_errors(document)]
    if not errors and row["schema"] == "schemas/manifest.v2.schema.json":
        errors = semantic_errors(document)
    return errors


def _rows(*, valid: bool) -> list[tuple[str, dict]]:
    return [(name, row) for name, release in RELEASES.items() for row in _index(release) if row["valid"] is valid]


def _id(case: tuple[str, dict]) -> str:
    return f"{case[0]}:{case[1]['path']}"


def test_the_releases_a_player_may_pin_are_here():
    """contract-v1.0.0 is what Arrt Player pins as this is written, and contract-v1.1.0 the latest tag."""
    assert {"1.0.0", "1.1.0"} <= set(RELEASES)


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_a_release_kept_here_is_of_this_major(name):
    """A new major may break what a release of the old one accepted, so its frozen copies are retired by a decision then."""
    assert int(name.split(".")[0]) == HEAD_MAJOR, f"released/{name} is of another major: retire it deliberately"


@pytest.mark.parametrize("case", _rows(valid=True), ids=_id)
def test_every_valid_fixture_of_a_release_is_valid_at_head(case):
    name, row = case

    assert _errors_at_head(RELEASES[name], row) == [], f"contract-v{name} accepted {row['path']}"


@pytest.mark.parametrize("case", _rows(valid=False), ids=_id)
def test_every_invalid_fixture_of_a_release_is_still_refused_at_head_unless_its_loosening_is_recorded(case):
    name, row = case
    refused = _errors_at_head(RELEASES[name], row) != []

    assert refused is ((name, row["path"]) not in LOOSENED), f"contract-v{name} refused {row['path']}"


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_no_route_of_a_release_is_gone_or_moved(name):
    then = json.loads((RELEASES[name] / "routes.json").read_text(encoding="utf-8"))["routes"]
    now = routes()

    assert set(then) - set(now) == set(), f"routes contract-v{name} named and HEAD does not"
    for route, spelling in then.items():
        assert now[route] == spelling, f"{route} moved since contract-v{name}"


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_no_fixture_of_a_release_is_gone_or_changed_its_verdict(name):
    head = {row["path"]: row for row in fixtures()}

    for row in _index(RELEASES[name]):
        assert row["path"] in head, f"{row['path']} was in contract-v{name} and is gone"
        assert head[row["path"]]["schema"] == row["schema"], row["path"]
        assert head[row["path"]]["valid"] is row["valid"], row["path"]


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_each_frozen_file_is_the_bytes_it_was_when_it_was_copied(name):
    release = RELEASES[name]
    recorded = json.loads((release / "sha256.json").read_text(encoding="utf-8"))
    on_disk = {
        str(path.relative_to(release)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(release.rglob("*"))
        if path.is_file() and path.name != "sha256.json"
    }

    assert recorded["version"] == name
    assert recorded["tag"] == f"contract-v{name}"
    assert on_disk == recorded["files"]


def test_a_release_is_read_from_the_packages_own_data():
    """Through `released()`, under `root()`, so a wheel carries the same copies a checkout does."""
    for release in RELEASES.values():
        assert release.parent == root() / "released"
        assert (release / "fixtures" / "index.json").is_file()
        assert (release / "routes.json").is_file()
