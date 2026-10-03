"""The catalogue's backup: a generation taken safely, kept for a while, and recorded only when it worked.

`operational-spec.md` § Backup and Restore is the design these hold: the
catalogue alone, `VACUUM INTO` rather than a file copy, several generations,
and a receipt the health panel reads that is written **only on success**, so
its age means what the panel says. A real SQLite file stands in for the
catalogue; nothing here is mocked except the one fault each failure test needs.
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import pytest

from arrt.persistence import backup
from arrt.persistence.backup import BACKUP_RECEIPT_FILENAME, BackupFailed, CatalogueBackup, start_backups

NOON = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "art" / "catalogue.sqlite"
    path.parent.mkdir()
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE artworks (id TEXT PRIMARY KEY, title TEXT)")
    db.executemany("INSERT INTO artworks VALUES (?, ?)", [("w1", "Nighthawks"), ("w2", "The Persistence of Memory")])
    db.commit()
    db.close()
    return path


@pytest.fixture
def job(tmp_path, catalogue):
    return CatalogueBackup(
        catalogue_path=catalogue,
        directory=tmp_path / "backups",
        receipt_path=catalogue.parent / BACKUP_RECEIPT_FILENAME,
        keep=2,
    )


def titles(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return sorted(row[0] for row in db.execute("SELECT title FROM artworks"))
    finally:
        db.close()


def test_a_generation_holds_the_catalogue_and_the_receipt_says_when(job, catalogue):
    result = job.run(now=NOON)

    assert result.path.name == "catalogue-20261002T120000Z.sqlite"
    assert titles(result.path) == ["Nighthawks", "The Persistence of Memory"]
    receipt = json.loads((catalogue.parent / BACKUP_RECEIPT_FILENAME).read_text())
    assert receipt["path"] == str(result.path)
    assert receipt["bytes"] == result.path.stat().st_size
    # The panel reads the receipt it writes: both ends of this file are ours.
    reading = backup.read(catalogue.parent / BACKUP_RECEIPT_FILENAME)
    assert reading.problem is None
    assert reading.completed_at is not None
    assert reading.describe().startswith("The catalogue was last backed up")


def test_a_failed_pass_leaves_the_last_receipt_and_no_half_copy(job, catalogue, monkeypatch):
    """The failure the receipt exists to expose: a backup that stopped working must not look fresh."""
    job.run(now=NOON)
    receipt = catalogue.parent / BACKUP_RECEIPT_FILENAME
    before = receipt.read_text()

    def refuse(_copy):
        raise BackupFailed("the copy failed its integrity check: simulated")

    monkeypatch.setattr(backup, "_require_intact", refuse)

    with pytest.raises(BackupFailed):
        job.run(now=NOON + timedelta(days=1))

    assert receipt.read_text() == before
    names = sorted(path.name for path in (catalogue.parent.parent / "backups").iterdir())
    assert names == ["catalogue-20261002T120000Z.sqlite"], "a failed copy was kept, or kept under a generation's name"


def test_a_catalogue_that_cannot_be_read_fails_the_pass_without_a_receipt(tmp_path):
    """A first backup that fails leaves no receipt at all, so the panel still says none was recorded."""
    receipt = tmp_path / BACKUP_RECEIPT_FILENAME
    job = CatalogueBackup(
        catalogue_path=tmp_path / "missing.sqlite", directory=tmp_path / "backups", receipt_path=receipt, keep=2
    )

    with pytest.raises(sqlite3.Error):
        job.run(now=NOON)

    assert not receipt.exists()
    assert backup.read(receipt).absent
    # Nothing half-made is left for retention or a restorer to trip over.
    assert list((tmp_path / "backups").iterdir()) == []


def test_retention_keeps_the_newest_and_touches_nothing_it_did_not_write(job, tmp_path):
    (tmp_path / "backups").mkdir()
    stranger = tmp_path / "backups" / "notes.txt"
    stranger.write_text("the operator's own file", encoding="utf-8")

    for day in range(3):
        result = job.run(now=NOON + timedelta(days=day))

    kept = sorted(path.name for path in (tmp_path / "backups").glob("catalogue-*"))
    assert kept == ["catalogue-20261003T120000Z.sqlite", "catalogue-20261004T120000Z.sqlite"]
    assert result.removed == ("catalogue-20261002T120000Z.sqlite",)
    assert result.kept == 2
    assert stranger.read_text(encoding="utf-8") == "the operator's own file"


def test_a_backup_reads_a_live_catalogue_without_taking_its_write_lock(job, catalogue):
    """A writer holding the catalogue open does not stop the backup, and the copy is a consistent snapshot."""
    writer = sqlite3.connect(catalogue)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO artworks VALUES ('w3', 'Uncommitted')")
    try:
        result = job.run(now=NOON)
    finally:
        writer.rollback()
        writer.close()

    assert titles(result.path) == ["Nighthawks", "The Persistence of Memory"]


def test_the_schedule_backs_up_at_once_and_keeps_going_after_a_failure(tmp_path, catalogue, monkeypatch):
    """Now rather than after the first interval, and a failed pass does not end the loop."""
    job = CatalogueBackup(
        catalogue_path=catalogue,
        directory=tmp_path / "backups",
        receipt_path=catalogue.parent / BACKUP_RECEIPT_FILENAME,
        keep=5,
    )
    calls = {"n": 0}
    real = job.run

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackupFailed("simulated first-pass failure")
        return real(**kwargs)

    monkeypatch.setattr(job, "run", flaky)
    passes = threading.Semaphore(0)
    halt = start_backups(job, interval_seconds=0.01, after_pass=passes.release)
    try:
        for _ in range(2):
            assert passes.acquire(timeout=10), "the schedule stopped after a failed pass"
    finally:
        halt()

    assert calls["n"] >= 2
    assert any((tmp_path / "backups").glob("catalogue-*.sqlite"))


def test_keep_must_be_at_least_one(tmp_path, catalogue):
    with pytest.raises(ValueError, match="keep must be at least 1"):
        CatalogueBackup(catalogue_path=catalogue, directory=tmp_path, receipt_path=tmp_path / "r.json", keep=0)
