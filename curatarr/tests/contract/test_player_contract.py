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

import hashlib
import json
import logging
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from curatarr.programming.manifest import heartbeat

CONTRACT = Path(__file__).resolve().parents[3] / "contract"


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((CONTRACT / "schemas" / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _errors(document: dict) -> list[str]:
    return [error.message for error in _validator("manifest.v1.schema.json").iter_errors(document)]


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


def test_a_published_manifest_carrying_media_conforms(service, ready_work, theme_of, published, wall_settings):
    """Minor 2, as the builder writes it, beside the contract's own minor 2 fixture and never instead of it.

    The render's file is written here, because media is the hash of real bytes:
    a render with no file has no media, and a document without the key would
    pass this schema without testing the key at all.
    """
    work = ready_work()
    render = next(view.rendition for view in service.list_renditions(work.id))
    data = b"\xff\xd8\xff\xe0 a render's bytes"
    (wall_settings.art_root / render.relative_path).parent.mkdir(parents=True, exist_ok=True)
    (wall_settings.art_root / render.relative_path).write_bytes(data)

    document = published(theme_of(work))

    assert document["schema"] == {"major": 1, "minor": 2}
    media = document["entries"][0]["media"]
    assert media == {
        "url": f"/media/sha256-{hashlib.sha256(data).hexdigest()}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "content_type": "image/jpeg",
    }
    assert _errors(document) == []


def test_a_render_with_no_file_is_published_without_media_and_says_so(ready_work, theme_of, published, caplog):
    """It still plays on the file channel, which reads `render_path`; there is no hash to offer.

    Said in the journal, because a Player on HTTP skips the work, and a wall one
    work short with nothing on the server naming it is the silence this product
    refuses.
    """
    work = ready_work()

    with caplog.at_level(logging.WARNING, logger="curatarr.library.facade"):
        document = published(theme_of(work))

    assert "media" not in document["entries"][0]
    assert _errors(document) == []
    assert [record.getMessage() for record in caplog.records if work.id in record.getMessage()], "nothing named the work"


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
