"""Opening a catalogue that still records television canvases forgets them.

Each Player draws its own mat on the presentation master, so a `tv_display`
row names a picture nothing serves, and a `wall_preview` drawn from one would go
on passing the hash test while showing the old matted picture. The migration
deletes both kinds of row and the `mat_hex` column only a canvas filled, and
leaves every other rendition, and every file, where it is.
"""

import logging
import sqlite3

import pytest

from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import RenditionKind
from arrt.persistence.sqlite import SqliteCatalogue

#: Two kinds the migration forgets and two it keeps, each with a row in the file.
_FORGOTTEN = ("tv_display", "wall_preview")
_KEPT = (str(RenditionKind.PRESENTATION_MASTER), str(RenditionKind.THUMBNAIL))


@pytest.fixture
def with_canvases(tmp_path, service, settings):
    """A catalogue file put back to the shape it had while the server composed canvases."""

    def _make():
        work = service.add_artwork(title="Nighthawks")
        source = service.add_source(
            artwork_id=work.id,
            url="https://museum.example/n",
            provider="artic",
            source_class="institutional",
            acquisition_method="dezoomify",
            rights_status="public_domain",
            is_primary=True,
        )
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path="raw/n.jpg",
            width=6000,
            height=4000,
            byte_size=1,
            content_hash="hash-1",
            fetch_status="ok",
        )
        connection = sqlite3.connect(settings.catalogue_path)
        try:
            connection.execute("ALTER TABLE renditions ADD COLUMN mat_hex TEXT")
            for kind in (*_FORGOTTEN, *_KEPT):
                connection.execute(
                    "INSERT INTO renditions (id, artwork_id, kind, target_width, target_height, relative_path,"
                    " source_content_hash, generated_at, mat_hex) VALUES (?, ?, ?, 1, 1, ?, 'hash-1', ?, ?)",
                    (f"r-{kind}", work.id, kind, f"{kind}/n.jpg", "2026-10-01T00:00:00+00:00", "#27285b"),
                )
            connection.commit()
        finally:
            connection.close()
        return work.id

    return _make


def _kinds(path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[0] for row in connection.execute("SELECT kind FROM renditions")}
    finally:
        connection.close()


def _columns(path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute("PRAGMA table_info(renditions)")}
    finally:
        connection.close()


def test_the_canvases_and_their_previews_are_forgotten_and_the_rest_kept(with_canvases, settings, store, caplog):
    with_canvases()
    store.close()
    assert _kinds(settings.catalogue_path) >= set(_FORGOTTEN), "the fixture holds no canvas, so this checks nothing"

    with caplog.at_level(logging.INFO, logger="arrt.persistence.migrations"):
        SqliteCatalogue(open_catalogue_file(settings.catalogue_path)).close()

    assert _kinds(settings.catalogue_path) == set(_KEPT)
    assert "mat_hex" not in _columns(settings.catalogue_path)
    assert any("Forgot 2 television canvases" in record.getMessage() for record in caplog.records)


def test_forgetting_them_is_safe_to_run_again(with_canvases, settings, store, caplog):
    """It runs on every open, so a file it already tidied opens unchanged and says nothing."""
    with_canvases()
    store.close()
    SqliteCatalogue(open_catalogue_file(settings.catalogue_path)).close()

    with caplog.at_level(logging.INFO, logger="arrt.persistence.migrations"):
        SqliteCatalogue(open_catalogue_file(settings.catalogue_path)).close()

    assert _kinds(settings.catalogue_path) == set(_KEPT)
    assert not [record for record in caplog.records if "television canvases" in record.getMessage()]
