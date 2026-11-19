"""The catalogue's backup: a generation taken safely, kept for a while, and recorded only when it worked.

`operational-spec.md` § Backup and Restore is the design these hold: the
catalogue alone, `VACUUM INTO` rather than a file copy, several generations,
and a receipt the health panel reads that is written **only on success**, so
its age means what the panel says. A real SQLite file stands in for the
catalogue; nothing here is mocked except the one fault each failure test needs.
"""

import json
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from fakes import counted_tokens

from arrt.persistence import backup
from arrt.persistence.backup import BACKUP_RECEIPT_FILENAME, BackupFailed, CatalogueBackup, start_backups

NOON = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


class Clock:
    """The job's clock, passed in so a test reads none of its own.

    A second later at each reading, so a pass completes after it starts and a
    schedule's passes are named apart; a test moves it to another day by setting `at`.
    """

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        moment = self.at
        self.at += timedelta(seconds=1)
        return moment


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
def clock():
    return Clock(NOON)


@pytest.fixture
def job(tmp_path, catalogue, clock):
    return CatalogueBackup(
        catalogue_path=catalogue,
        directory=tmp_path / "backups",
        receipt_path=catalogue.parent / BACKUP_RECEIPT_FILENAME,
        keep=2,
        clock=clock,
    )


def titles(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return sorted(row[0] for row in db.execute("SELECT title FROM artworks"))
    finally:
        db.close()


def test_a_generation_holds_the_catalogue_and_the_receipt_says_when(job, catalogue, clock):
    """A pass told when it started is named by that moment, and completes by the job's clock, later."""
    done = NOON + timedelta(seconds=5)
    clock.at = done

    result = job.run(now=NOON)

    assert result.path.name == "catalogue-20261002T120000Z.sqlite"
    assert titles(result.path) == ["Nighthawks", "The Persistence of Memory"]
    receipt = json.loads((catalogue.parent / BACKUP_RECEIPT_FILENAME).read_text())
    assert receipt["path"] == str(result.path)
    assert receipt["bytes"] == result.path.stat().st_size
    # The panel reads the receipt it writes: both ends of this file are ours.
    assert receipt["started_at"] == NOON.isoformat()
    reading = backup.read(catalogue.parent / BACKUP_RECEIPT_FILENAME, now=done + timedelta(hours=1))
    assert reading.problem is None
    assert reading.completed_at == done
    assert reading.describe().startswith("The catalogue was last backed up")


def test_a_failed_pass_leaves_the_last_receipt_and_no_half_copy(job, catalogue, clock, monkeypatch):
    """The failure the receipt exists to expose: a backup that stopped working must not look fresh."""
    job.run()
    receipt = catalogue.parent / BACKUP_RECEIPT_FILENAME
    before = receipt.read_text()

    def refuse(_copy):
        raise BackupFailed("the copy failed its integrity check: simulated")

    monkeypatch.setattr(backup, "_require_intact", refuse)

    clock.at = NOON + timedelta(days=1)
    with pytest.raises(BackupFailed):
        job.run()

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


def test_retention_keeps_the_newest_and_touches_nothing_it_did_not_write(job, tmp_path, clock):
    (tmp_path / "backups").mkdir()
    stranger = tmp_path / "backups" / "notes.txt"
    stranger.write_text("the operator's own file", encoding="utf-8")

    for day in range(3):
        clock.at = NOON + timedelta(days=day)
        result = job.run()

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
        result = job.run()
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
        clock=Clock(NOON),
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


def test_a_generation_carries_the_catalogue_and_never_the_picture_store(job, catalogue, tmp_path):
    """The store is not in the backup (owner, 2026-10-06): it can be fetched again, and it has no ceiling.

    A kept picture sits beside the catalogue, where a deployment keeps it, and
    the backup directory afterwards holds the one generation and nothing else.
    """
    from arrt.library.services.pictures import PictureStore

    art_root = catalogue.parent
    store = PictureStore(art_root / "pictures", art_root=art_root, now=lambda: NOON, staging_token=counted_tokens())
    store.put("artic", "https://museum.example/kept", _a_jpeg())
    assert store.size().pictures_files > 0, "a store with nothing in it would make this pass vacuously"

    result = job.run()

    backed_up = {path for path in (tmp_path / "backups").rglob("*") if path.is_file()}
    assert backed_up == {result.path}
    with sqlite3.connect(f"file:{result.path}?mode=ro", uri=True) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"artworks"}


def _a_jpeg() -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (900, 600), (90, 70, 140)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_a_pass_not_told_when_starts_and_completes_by_the_job_s_clock(tmp_path, catalogue):
    """What the schedule's passes do: `run()` with no moment, so the job's clock names the generation and stamps the receipt."""
    receipt = catalogue.parent / BACKUP_RECEIPT_FILENAME
    job = CatalogueBackup(
        catalogue_path=catalogue, directory=tmp_path / "backups", receipt_path=receipt, keep=2, clock=Clock(NOON)
    )

    result = job.run()

    assert result.path.name == "catalogue-20261002T120000Z.sqlite"
    stamped = json.loads(receipt.read_text())
    assert (stamped["started_at"], stamped[backup.COMPLETED_AT_KEY]) == (
        NOON.isoformat(),
        (NOON + timedelta(seconds=1)).isoformat(),
    )


@pytest.mark.parametrize("seconds", [0.0, 2.5])
def test_backup_completed_says_how_long_the_copy_took_by_the_injected_monotonic_clock(tmp_path, catalogue, caplog, seconds):
    """The figure the WAL decision's third trigger reads: the copy alone, from before the generation exists to after.

    The injected clock notes, at each reading, whether the generation is on
    disk yet, so a timing that began after the copy or ended before it fails
    here rather than reading as a short copy.
    """
    directory = tmp_path / "backups"
    readings: list[bool] = []

    def monotonic() -> float:
        readings.append(any(directory.glob("catalogue-*Z.sqlite")))
        return 1000.0 + (seconds if len(readings) > 1 else 0.0)

    job = CatalogueBackup(
        catalogue_path=catalogue,
        directory=directory,
        receipt_path=catalogue.parent / BACKUP_RECEIPT_FILENAME,
        keep=2,
        clock=Clock(NOON),
        monotonic=monotonic,
    )

    with caplog.at_level("INFO", logger="arrt.persistence.backup"):
        result = job.run()

    (completed,) = [record for record in caplog.records if getattr(record, "event", None) == "backup.completed"]
    assert readings == [False, True]
    assert completed.copy_seconds == result.copy_seconds == seconds
    assert isinstance(completed.copy_seconds, float)


def test_by_default_the_copy_is_timed_by_the_real_monotonic_clock(job, caplog):
    with caplog.at_level("INFO", logger="arrt.persistence.backup"):
        result = job.run()

    assert isinstance(result.copy_seconds, float)
    assert 0.0 <= result.copy_seconds < 60.0


# -- the start-up pass after an upgrade ----------------------------------------------

DAY = 24 * 60 * 60


def _upgraded_job(tmp_path, catalogue, *, keep=14, generation_age=timedelta(hours=2)):
    """A job holding one generation from before the upgrade, `generation_age` old at the first start."""
    clock = Clock(NOON)
    job = CatalogueBackup(
        catalogue_path=catalogue,
        directory=tmp_path / "backups",
        receipt_path=catalogue.parent / BACKUP_RECEIPT_FILENAME,
        keep=keep,
        clock=clock,
    )
    before = job.run(now=NOON - generation_age).path
    return job, clock, before


def _start(job, clock, at, *, interval=DAY):
    """One start of the server: the backup schedule begins at `at`, and the server stops again.

    `halt` joins the thread, and a pass decided at the start runs before the
    loop first waits, so by the time this returns a start that backs up has.
    """
    clock.at = at
    halt = start_backups(job, interval_seconds=interval)
    halt()


@pytest.mark.parametrize("starts", [3, 14, 20])
def test_a_crash_loop_after_an_upgrade_leaves_the_generation_from_before_it(tmp_path, catalogue, starts):
    """Starts within an hour of a generation younger than the interval write nothing, so none is pruned.

    Twenty is more starts than the fourteen generations kept, the crash loop
    that replaced every pre-upgrade copy; three is fewer, where only the count
    of generations written says whether a start backed up.
    """
    job, clock, before = _upgraded_job(tmp_path, catalogue)

    for start in range(starts):
        _start(job, clock, NOON + timedelta(minutes=3 * start))

    generations = sorted((tmp_path / "backups").glob("catalogue-*Z.sqlite"))
    assert generations == [before]
    assert titles(before) == ["Nighthawks", "The Persistence of Memory"]


def test_a_start_after_the_interval_has_passed_backs_up_at_once(tmp_path, catalogue):
    job, clock, before = _upgraded_job(tmp_path, catalogue, generation_age=timedelta(hours=25))

    _start(job, clock, NOON)

    generations = sorted((tmp_path / "backups").glob("catalogue-*Z.sqlite"))
    assert before in generations
    assert len(generations) == 2


def test_a_generation_named_after_now_does_not_stand_in_for_a_backup(tmp_path, catalogue):
    """A clock set back makes the newest generation look as if it were taken in the future; the pass runs."""
    job, clock, _ = _upgraded_job(tmp_path, catalogue, generation_age=-timedelta(days=3))

    _start(job, clock, NOON)

    assert len(list((tmp_path / "backups").glob("catalogue-*Z.sqlite"))) == 2


def test_a_skipped_start_backs_up_when_the_interval_since_the_generation_ends(tmp_path, catalogue):
    """What is left of the interval, not a whole one more: a server restarting more often than the interval still backs up."""
    hour = 60 * 60
    job, clock, _ = _upgraded_job(tmp_path, catalogue, generation_age=timedelta(seconds=hour - 1))
    clock.at = NOON
    passes = threading.Semaphore(0)

    halt = start_backups(job, interval_seconds=hour, after_pass=passes.release)
    try:
        assert passes.acquire(timeout=10), "the first pass waited a whole interval, not what was left of it"
    finally:
        halt()

    assert len(list((tmp_path / "backups").glob("catalogue-*Z.sqlite"))) == 2


def test_a_snapshot_beside_the_generations_is_never_counted_or_pruned_by_them(tmp_path, catalogue):
    """The pre-migration copy shares BACKUP_DIR and stays out of the generations' retention."""
    directory = tmp_path / "backups"
    directory.mkdir()
    snapshot = directory / "pre-migration-20261001T000000Z.sqlite"
    snapshot.write_bytes(catalogue.read_bytes())
    job = CatalogueBackup(
        catalogue_path=catalogue, directory=directory, receipt_path=tmp_path / "r.json", keep=1, clock=Clock(NOON)
    )

    for day in range(3):
        result = job.run(now=NOON + timedelta(days=day))

    assert result.kept == 1
    assert snapshot.exists()


def _left_by_a_killed_copy(directory, name, *, hours_old):
    """A staged copy as a pass or an open killed mid-`VACUUM INTO` leaves it, `hours_old` by its mtime."""
    from arrt import atomic

    directory.mkdir(parents=True, exist_ok=True)
    staged = atomic.staging_path(directory / name)
    staged.write_bytes(b"half a catalogue")
    stamp = time.time() - hours_old * 3600
    os.utime(staged, (stamp, stamp))
    return staged


@pytest.mark.parametrize("hours_old", [25, 24 * 30], ids=["a day old", "a month old"])
def test_a_pass_sweeps_what_a_killed_copy_left_staged_and_only_that(job, tmp_path, hours_old):
    """Each staged copy has a name of its own, so nothing else would ever claim one; a fresh one may be in progress."""
    backups = tmp_path / "backups"
    stale_generation = _left_by_a_killed_copy(backups, "catalogue-20261001T120000Z.sqlite", hours_old=hours_old)
    stale_snapshot = _left_by_a_killed_copy(backups, "pre-migration-20261001T120000Z.sqlite", hours_old=hours_old)
    in_progress = _left_by_a_killed_copy(backups, "catalogue-20261002T115959Z.sqlite", hours_old=1)
    someone_elses = backups / ".notes.sqlite.x.tmp"
    someone_elses.write_bytes(b"not ours")
    os.utime(someone_elses, (0, 0))

    job.run()

    assert not stale_generation.exists()
    assert not stale_snapshot.exists()
    assert in_progress.exists()
    assert someone_elses.exists()
