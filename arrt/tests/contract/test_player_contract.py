"""Arrt's side of the Player contract: what it writes, and what it reads.

The schemas under `contract/` describe the feed this plane writes and the
heartbeat it reads. They were derived from this code, which is exactly why they
need testing against it: a schema read off a builder is one mis-read away from
describing a document the builder never writes, and nothing else would notice
until a Player in another repository refused a real manifest.

So the feed is built here by the real service from real records and written by
the real `sync`, and the document on disk is what is validated, against the
schema and the contract's semantic rules (`feed_guard.problems`). The heartbeat
runs the other way: each fixture the contract calls valid must be one this
plane's reader accepts, and the one the contract names for a misspelled instant
must be one it refuses.
"""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from feed_guard import problems

from arrt.library.facade import UnplayableReason
from arrt.persistence.records import RenditionKind
from arrt.programming.manifest import heartbeat

CONTRACT = Path(__file__).resolve().parents[3] / "contract"


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
        return json.loads(wall_settings.manifest_v2_path(wall_id).read_text(encoding="utf-8"))

    return _publish


def _read(wall_settings, wall_id) -> dict:
    return json.loads(wall_settings.manifest_v2_path(wall_id).read_text(encoding="utf-8"))


def test_a_published_feed_with_an_attributed_and_an_unattributed_work_conforms(service, ready_work, theme_of, published):
    """Both label shapes: an artist with recorded name parts, and none at all."""
    dali = service.add_artist(
        name="Salvador Dalí", nationality="Spanish", born=1904, died=1989, family_name="Dalí", given_name="Salvador"
    )
    attributed = ready_work("The Persistence of Memory", artist_id=dali.id, content_hash="hash-a")
    unattributed = ready_work("Stirrup-spout vessel", content_hash="hash-b")

    document = published(theme_of(attributed, unattributed))

    assert set(document["works"]) == {attributed.id, unattributed.id}
    assert document["works"][attributed.id]["label"]["artist_family_name"] == "Dalí"
    assert document["works"][unattributed.id]["label"]["artist"] is None
    assert problems(document) == []


def test_a_published_feed_whose_every_work_is_excluded_conforms(service, ready_work, theme_of, published):
    """An empty feed is a real document: the theme hangs and nothing in it is ready."""
    work = ready_work()
    theme = theme_of(work)
    service.archive_artwork(work.id)

    document = published(theme)

    assert document["works"] == {}
    assert document["schedule"]["slots"] == []
    assert problems(document) == []


def test_a_published_feed_carrying_a_work_shown_now_conforms(display, ready_work, theme_of, published, wall_id, wall_settings):
    """A guest: a work from outside the theme, carried for the one slot it is shown in."""
    published(theme_of(ready_work("Automat")))
    guest = ready_work()

    display.show_work_now(wall_id, guest.id)

    document = _read(wall_settings, wall_id)
    assert document["schedule"]["slots"][0]["work_id"] == guest.id
    assert problems(document) == []


def test_a_published_feed_carrying_media_conforms(service, ready_work, theme_of, published, wall_settings):
    """Media is the hash of the master's real bytes, with its size, as the contract spells it."""
    work = ready_work()
    master = next(
        view.rendition for view in service.list_renditions(work.id) if view.rendition.kind is RenditionKind.PRESENTATION_MASTER
    )
    data = (wall_settings.art_root / master.relative_path).read_bytes()

    document = published(theme_of(work))

    assert document["schema"] == {"major": 2, "minor": 0}
    assert document["works"][work.id]["media"] == {
        "url": f"/media/sha256-{hashlib.sha256(data).hexdigest()}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "content_type": "image/jpeg",
        "width": 400,
        "height": 300,
    }
    assert problems(document) == []


def test_a_master_with_no_file_is_left_off_the_feed_and_named(service, display, ready_work, theme_of, wall_settings, wall_id):
    """A Player could not fetch it, so it is not sent; named in the build's
    exclusions, because a wall one work short with nothing on the server naming
    it is the silence this product refuses."""
    work = ready_work()
    kept = ready_work("Automat")
    master = next(
        view.rendition for view in service.list_renditions(work.id) if view.rendition.kind is RenditionKind.PRESENTATION_MASTER
    )
    (wall_settings.art_root / master.relative_path).unlink()

    build = display.sync(wall_id, theme_of(work, kept).id)
    document = _read(wall_settings, wall_id)

    assert set(document["works"]) == {kept.id}
    assert problems(document) == []
    assert [(exclusion.work_id, exclusion.reason) for exclusion in build.exclusions] == [
        (work.id, UnplayableReason.NO_RENDITION)
    ], "nothing named the work"


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
