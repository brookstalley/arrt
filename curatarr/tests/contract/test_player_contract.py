"""Curatarr's side of the Player contract: what it writes, and what it reads.

The schemas under `contract/` describe the manifest this plane writes and the
heartbeat it reads. They were derived from this code, which is exactly why they
need testing against it: a schema read off a builder is one mis-read away from
describing a document the builder never writes, and nothing else would notice
until a Player in another repository refused a real manifest.

So the manifest is built here by the real service from real records and written
by the real `sync`, and the document on disk is what is validated. The heartbeat
runs the other way: each fixture the contract calls valid must be one this
plane's reader accepts, and the one the contract names for a misspelled instant
must be one it refuses.
"""

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from curatarr.programming.manifest import heartbeat

CONTRACT = Path(__file__).resolve().parents[3] / "contract"


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((CONTRACT / "schemas" / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _errors(document: dict, schema_name: str = "manifest.v1.schema.json") -> list[str]:
    return [error.message for error in _validator(schema_name).iter_errors(document)]


@pytest.fixture
def theme_of(display):
    """A theme holding the given works, in the order given."""

    def _theme(*works, name="Surrealism"):
        theme = display.add_theme(name=name)
        for position, work in enumerate(works):
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        return theme

    return _theme


@pytest.fixture
def published(display, wall_settings, wall_id):
    """Hang a theme on the wall, sync it, and return the document written to disk."""

    def _publish(theme) -> dict:
        display.sync(wall_id, theme.id)
        return json.loads(wall_settings.manifest_path(wall_id).read_text(encoding="utf-8"))

    return _publish


def test_a_published_manifest_with_an_attributed_and_an_unattributed_work_conforms(service, ready_work, theme_of, published):
    """Both label shapes: an artist with recorded name parts, and none at all."""
    dali = service.add_artist(
        name="Salvador Dalí", nationality="Spanish", born=1904, died=1989, family_name="Dalí", given_name="Salvador"
    )
    attributed = ready_work("The Persistence of Memory", artist_id=dali.id, content_hash="hash-a")
    unattributed = ready_work("Stirrup-spout vessel", content_hash="hash-b")

    document = published(theme_of(attributed, unattributed))

    assert len(document["entries"]) == 2
    assert _errors(document) == []


def test_a_published_manifest_whose_every_work_is_excluded_conforms(service, ready_work, theme_of, published):
    """An empty entries list is a real document: the theme hangs and nothing in it is ready."""
    work = ready_work()
    theme = theme_of(work)
    service.archive_artwork(work.id)

    document = published(theme)

    assert document["entries"] == []
    assert _errors(document) == []


def test_a_published_manifest_carrying_a_pin_conforms(display, ready_work, theme_of, published, wall_id):
    work = ready_work()
    theme = theme_of(work)
    display.show_work_now(wall_id, work.id)

    document = published(theme)

    assert document["directive"]["pinned_work_id"] == work.id
    assert _errors(document) == []


def _heartbeat_fixtures(validity: str) -> list[Path]:
    return sorted((CONTRACT / "fixtures" / "heartbeat.v1" / validity).glob("*.json"))


@pytest.mark.parametrize("fixture", _heartbeat_fixtures("valid"), ids=lambda path: path.name)
def test_every_valid_heartbeat_in_the_contract_is_one_this_plane_can_read(fixture, tmp_path):
    path = tmp_path / "display-heartbeat-wall.json"
    shutil.copyfile(fixture, path)

    reading = heartbeat.read(path)

    assert reading.problem is None
    assert reading.reported_at is not None


def test_a_heartbeat_that_misspells_its_instant_is_one_this_plane_refuses(tmp_path):
    """The contract's reason for fixing the key's spelling, checked from the reading end."""
    path = tmp_path / "display-heartbeat-wall.json"
    shutil.copyfile(CONTRACT / "fixtures" / "heartbeat.v1" / "invalid" / "timestamp-instead-of-reported-at.json", path)

    reading = heartbeat.read(path)

    assert reading.problem is not None
