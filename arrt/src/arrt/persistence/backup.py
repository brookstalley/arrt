"""Whether the catalogue has been backed up lately, and how long ago.

The catalogue is the irreplaceable asset, and the only thing this backs up: the
image tree is the storage's own snapshots' to keep (a restore carries both,
`operational-spec.md` § Backup and Restore; #180). So "a backup that
silently stopped succeeding a month ago" is the failure this reading exists to
make visible, and `operational-spec.md` names surfacing its age on the health
panel as part of the backup's design rather than as a nicety.

**The receipt is written only on success**, which is what makes its age mean what
the panel says it means. A job that stamped every attempt would report a fresh
age for a backup that has been failing since Tuesday, and the panel would be
confidently wrong about the one asset nothing else protects.

**The writer is `CatalogueBackup`, below** (`build-plan-nas.md` Chunk 02), and
it runs on the server's own schedule when `BACKUP_DIR` is set. Without it the
panel says *no backup has ever been recorded*, which is a true and useful
observation on a deployment that has never run one: the panel states
observations with ages and never verdicts.

The parse is `observations.observe`'s, shared with the display heartbeat. Both
ends of this one are ours, so the key cannot drift the way the heartbeat's could
across planes — but the reader and the writer still belong in one module, and
this is where the writer lands.
"""

import contextlib
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from arrt import atomic, observations
from arrt.persistence import migrations
from arrt.persistence.records import BackupReading

log = logging.getLogger(__name__)

#: Written beside the catalogue's own directory, under `ART_ROOT`. Beside the
#: catalogue rather than *inside* it, which is not a filing preference: the
#: backup copies the catalogue, so a receipt recorded as a row could only ever be
#: written after the copy was taken — every restored catalogue would then carry
#: the previous backup's receipt and report an age older than the file it came
#: from. A file beside it is stamped by the run that succeeded and restores as
#: whatever the destination actually holds.
BACKUP_RECEIPT_FILENAME: Final[str] = "backup-status.json"

#: The key carrying the instant the backup finished. Named for the fact the panel
#: states — when the catalogue was last safely copied — rather than for when the
#: document was written, because a writer that stamps an attempt and a writer that
#: stamps a success would otherwise both be spelling this correctly.
COMPLETED_AT_KEY: Final[str] = "completed_at"


def read(path: Path, *, now: datetime | None = None) -> BackupReading:
    """Observe the backup receipt. Absent is an answer, not a failure."""
    seen = observations.observe(path, key=COMPLETED_AT_KEY, now=now)
    return BackupReading(
        path=seen.path,
        completed_at=seen.at,
        age_seconds=seen.age_seconds,
        contents=seen.contents,
        problem=seen.problem,
    )


# -- the writer -----------------------------------------------------------------

#: A generation's name: the instant it was taken, so names sort as times do and
#: retention can keep the newest by name alone. UTC, and no colons, which some
#: file systems a backup directory may be mounted from refuse.
_GENERATION_FORMAT: Final[str] = "catalogue-%Y%m%dT%H%M%SZ.sqlite"
_GENERATION_GLOB: Final[str] = "catalogue-*Z.sqlite"
#: A copy in progress is staged under `atomic.staging_path`'s hidden name, which
#: the glob above never matches, so a pass that dies half-way leaves nothing
#: retention or a restorer mistakes for a generation; what it does leave is
#: swept once stale (`_sweep_staging`).

#: The copy taken before a migration drops anything, named like a generation
#: but never matched by its glob: it sits outside the generations' count, so no
#: number of starts after an upgrade can prune it (`operational-spec.md`
#: § Backup and Restore).
_SNAPSHOT_FORMAT: Final[str] = "pre-migration-%Y%m%dT%H%M%SZ.sqlite"
_SNAPSHOT_GLOB: Final[str] = "pre-migration-*Z.sqlite"
#: Pre-migration copies kept. Three, so the copy from before one upgrade
#: survives the next two.
SNAPSHOTS_KEPT: Final[int] = 3

#: What the catalogue's `PRAGMA user_version` holds from the moment its copy is
#: taken until the migrations that copy was taken for have all run. A start that
#: finds it takes no second copy: the file is no longer as the previous release
#: left it, and the copy that is already holds what a rollback needs. Nothing
#: else in the catalogue reads `user_version`, and the previous release leaves it
#: 0, so a file it wrote never carries the mark. ("arrt" in ASCII.)
MIGRATION_BEGUN: Final[int] = 0x61727274

#: How long a stopping job is waited for: one copy of a household catalogue
#: takes well under a second, so a job still running after this is wedged.
_SHUTDOWN_JOIN_SECONDS: Final[float] = 30.0


@dataclass(frozen=True, slots=True)
class BackupResult:
    """What one pass did: the generation it wrote, and what retention removed."""

    path: Path
    byte_size: int
    kept: int
    removed: tuple[str, ...]
    #: How long the `VACUUM INTO` took, by the monotonic clock: the copy holds a
    #: SHARED lock the server's commits wait on, so this is how long they could
    #: have waited, and the figure that would reopen the WAL decision.
    copy_seconds: float


class CatalogueBackup:
    """Copy the catalogue to the backup directory, keep the newest generations, and record success.

    `operational-spec.md` § Backup and Restore is the design: the catalogue
    alone (the image tree is the storage's snapshots' to keep, #180;
    `kept-answers.sqlite` is disposable),
    with `VACUUM INTO` rather than a file copy, which could capture a torn
    database from under a live writer; several generations, because a
    destination can be away; and **the receipt written only on success**, so its
    age means what the health panel says it means.

    Each generation is checked before it counts: `PRAGMA integrity_check` on the
    copy, then a rename from its partial name. A copy that fails the check is
    deleted and the pass fails, leaving the previous receipt in place.
    """

    def __init__(
        self,
        *,
        catalogue_path: Path,
        directory: Path,
        receipt_path: Path,
        keep: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """`clock` says when a pass starts, unless `run` is told, and when it completes; `monotonic` times the copy."""
        if keep < 1:
            raise ValueError(f"keep must be at least 1, got {keep}")
        self._catalogue_path = catalogue_path
        self._directory = directory
        self._receipt_path = receipt_path
        self._keep = keep
        self._clock = clock
        self._monotonic = monotonic

    def run(self, *, now: datetime | None = None) -> BackupResult:
        """Take one generation. Raises on failure, after logging it, with the previous receipt untouched."""
        started = now or self._clock()
        log.debug("backing up the catalogue", extra={"event": "backup.started", "directory": str(self._directory)})
        try:
            result = self._take(started)
        except (OSError, sqlite3.Error, BackupFailed) as exc:
            log.warning(
                "the catalogue backup failed: %s",
                exc,
                extra={"event": "backup.failed", "directory": str(self._directory), "detail": str(exc)},
            )
            raise
        log.info(
            "backed up the catalogue",
            extra={
                "event": "backup.completed",
                "path": str(result.path),
                "bytes": result.byte_size,
                "kept": result.kept,
                "removed": len(result.removed),
                "copy_seconds": result.copy_seconds,
            },
        )
        return result

    def _take(self, started: datetime) -> BackupResult:
        self._directory.mkdir(parents=True, exist_ok=True)
        # A pass killed mid-copy leaves its staged copy, under a name of its
        # own that nothing else claims and the generations' glob never counts.
        _sweep_staging(self._directory)
        final = self._directory / started.strftime(_GENERATION_FORMAT)
        # A connection of its own, read-only: VACUUM INTO reads one consistent
        # snapshot and takes no lock a writer needs to *begin*, but it holds a
        # SHARED lock for the whole copy. The catalogue runs on the default
        # rollback journal, where a commit needs every SHARED lock released, so
        # the server's commits wait on the copy (Python's default busy timeout,
        # 5 s) and fail with "database is locked" past that. A household
        # catalogue copies in well under a second; one that grew past the
        # timeout would show as refused writes while the backup runs.
        copy_began = self._monotonic()
        _copy_intact(sqlite3.connect(f"file:{self._catalogue_path}?mode=ro", uri=True), final)
        copy_seconds = self._monotonic() - copy_began
        removed = self._retain()
        byte_size = final.stat().st_size
        kept = len(self._generations())
        self._write_receipt(started=started, path=final, byte_size=byte_size, kept=kept)
        return BackupResult(path=final, byte_size=byte_size, kept=kept, removed=removed, copy_seconds=copy_seconds)

    def _generations(self) -> list[Path]:
        return sorted(self._directory.glob(_GENERATION_GLOB))

    def newest_age(self, *, now: datetime | None = None) -> timedelta | None:
        """How long ago the newest generation was taken, read from its name; None when there is none."""
        named = [moment for moment in (_instant(path.name, _GENERATION_FORMAT) for path in self._generations()) if moment]
        if not named:
            return None
        return (now or self._clock()) - max(named)

    def _retain(self) -> tuple[str, ...]:
        """Remove all but the newest `keep` generations; only files this job named."""
        generations = self._generations()
        doomed = generations[: max(0, len(generations) - self._keep)]
        for path in doomed:
            path.unlink(missing_ok=True)
        return tuple(path.name for path in doomed)

    def _write_receipt(self, *, started: datetime, path: Path, byte_size: int, kept: int) -> None:
        """Written last, and atomically: a reader sees the old receipt or the new one, never half of one."""
        document = {
            COMPLETED_AT_KEY: self._clock().isoformat(),
            "started_at": started.isoformat(),
            "path": str(path),
            "bytes": byte_size,
            "generations_kept": kept,
        }
        atomic.write_bytes(self._receipt_path, (json.dumps(document, indent=2) + "\n").encode("utf-8"))


class BackupFailed(Exception):
    """A backup pass that ran and produced nothing it could trust."""


def _copy_intact(source: sqlite3.Connection, final: Path) -> None:
    """Copy what `source` holds to `final` with `VACUUM INTO`, checked and synced before it is named. Closes `source`.

    Staged under a name of its own and renamed only once SQLite calls the copy
    intact, so `final` is a whole copy or absent; a failure anywhere removes the
    staged copy and continues.
    """
    staging = atomic.staging_path(final)
    try:
        try:
            source.execute("VACUUM INTO ?", (str(staging),))
        finally:
            source.close()
        _require_intact(staging)
        atomic.sync_file(staging)
        atomic.promote(staging, final)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; a half copy must go on any exit
        with contextlib.suppress(OSError):
            staging.unlink(missing_ok=True)
        raise


def _sweep_staging(directory: Path) -> int:
    """Remove the copies a killed pass or open left staged here, once stale: generations' and pre-migration copies'.

    The age rule is the art tree's (`atomic.STALE_STAGING_AFTER`), far longer
    than any copy of a household catalogue takes, so a copy in progress is never
    swept. Only names this module stages under are touched.
    """
    return sum(atomic.sweep_stale_in(directory, names=names) for names in (_GENERATION_GLOB, _SNAPSHOT_GLOB))


def _instant(name: str, form: str) -> datetime | None:
    """The moment a file of ours is named for, or None for a name that is not one of them."""
    try:
        return datetime.strptime(name, form).replace(tzinfo=UTC)
    except ValueError:
        return None


def _require_intact(copy: Path) -> None:
    """Refuse a copy SQLite does not call intact, before it is named as a generation."""
    check = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
    try:
        verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if verdict != "ok":
        raise BackupFailed(f"the copy failed its integrity check: {verdict}")


def start_backups(
    job: CatalogueBackup,
    *,
    interval_seconds: float,
    after_pass: Callable[[], None] = lambda: None,
) -> Callable[[], None]:
    """Back up now unless a recent generation stands, then every `interval_seconds`; return the call that stops it.

    **Now rather than after the first interval**, so a server that restarts more
    often than the interval still backs up. **Not now while the newest
    generation is younger than the interval**: that generation already is the
    backup the start-up pass exists to take, and retention keeps generations by
    count, so a server restarting every few minutes after an upgrade would
    otherwise replace every generation from before it with copies of the
    upgraded file within the hour. The first pass then waits out what is left of
    the interval since that generation. A newest generation named later than now
    (a clock set back) is not trusted to stand in, and the pass runs.

    Decided before the thread starts, so by the time this returns the start-up
    pass has been skipped or is under way. A failed pass is logged by the job
    and the loop carries on — the receipt's age on the health panel is what says
    it has been failing.
    """
    stop = threading.Event()
    first_wait = _start_up_wait(job, interval_seconds)

    def loop() -> None:
        if first_wait > 0 and stop.wait(first_wait):
            return
        while True:
            try:
                job.run()
            except Exception:  # prawduct:allow prawduct/broad-except -- a dead backup loop stops protecting silently
                log.exception("a catalogue backup pass raised", extra={"event": "backup.pass_raised"})
            after_pass()
            if stop.wait(interval_seconds):
                return

    thread = threading.Thread(target=loop, name="catalogue-backup", daemon=True)
    thread.start()

    def halt() -> None:
        stop.set()
        thread.join(timeout=_SHUTDOWN_JOIN_SECONDS)
        if thread.is_alive():
            log.warning(
                "a catalogue backup did not stop when asked and is still running",
                extra={"event": "backup.wedged", "waited_seconds": _SHUTDOWN_JOIN_SECONDS},
            )

    return halt


def _start_up_wait(job: CatalogueBackup, interval_seconds: float) -> float:
    """Seconds before the first pass: none, unless the newest generation is younger than the interval."""
    try:
        age = job.newest_age()
    except OSError as exc:
        # A directory that cannot be listed cannot vouch for a recent backup:
        # the pass runs, and fails or succeeds on its own terms.
        log.warning("could not list the backup directory: %s", exc, extra={"event": "backup.unlisted", "detail": str(exc)})
        return 0.0
    if age is None or age < timedelta(0) or age.total_seconds() >= interval_seconds:
        return 0.0
    remaining = interval_seconds - age.total_seconds()
    log.info(
        "skipped the start-up backup: the newest generation is %ds old, younger than the interval",
        int(age.total_seconds()),
        extra={"event": "backup.skipped_recent", "age_seconds": age.total_seconds(), "next_in_seconds": remaining},
    )
    return remaining


# -- the copy taken before a migration drops anything ---------------------------


class SnapshotFailed(RuntimeError):
    """The copy a destructive migration needs first could not be taken, so no migration may run."""


def take_pre_migration_snapshot(
    catalogue_path: Path,
    *,
    directory: Path,
    would_drop: Callable[[sqlite3.Connection], tuple[str, ...]],
    now: datetime,
    keep: int = SNAPSHOTS_KEPT,
) -> Path | None:
    """Copy the catalogue aside if opening it would drop anything; return the copy, or None when nothing would go.

    `would_drop` is the migrations' own question (`migrations.pending_drops`),
    asked of the file before any of them runs, so a file already on the current
    shape, and a new one, take no copy. The copy is the file as the previous
    release left it, taken before the store widens it or creates a table, and
    named `pre-migration-<UTC instant>.sqlite` in `directory`, outside the
    generations' count.

    **One copy per migration, however many starts it takes.** Once the copy is
    written the file is marked (`MIGRATION_BEGUN`), and the mark stays until
    the last migration has run (`finish_migration`). A start that finds the
    mark, and a copy in `directory`, takes none: by then the store has widened
    the file and may have rewritten or dropped some of it, so a copy of it
    would not be the file as the previous release left it, and the one that is
    stays the newest. A migration that fails on every start therefore leaves
    that copy where the rollback looks for it, whatever the steps before the
    failing one changed. A marked file with no copy in `directory` (the copy was
    removed, or `BACKUP_DIR` moved) is copied again, since a later copy is
    better than none.

    **Raises `SnapshotFailed` when the copy cannot be taken**, with the
    catalogue untouched and no half copy left: a disk that is full or a
    directory that is read-only stops the open rather than letting it drop
    anything without a copy.
    """
    if not catalogue_path.exists():
        return None
    # Read-write though it mostly reads: a hot journal left by a killed writer
    # has to be rolled back before the file can be read at all.
    source = migrations.open_existing(catalogue_path)
    try:
        drops = would_drop(source)
        if not drops:
            # A start killed between the last migration and its mark's removal.
            finish_migration(source)
            source.close()
            return None
        begun = _marked(source)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; the connection must close on any exit
        source.close()
        raise
    earlier = _snapshots(directory) if directory.is_dir() else []
    if begun and earlier:
        source.close()
        log.info(
            "took no second copy: the migration the copy %s was taken for has not finished",
            earlier[-1].name,
            extra={"event": "catalogue.snapshot_kept", "path": str(earlier[-1]), "drops": list(drops)},
        )
        return earlier[-1]
    final = directory / now.astimezone(UTC).strftime(_SNAPSHOT_FORMAT)
    if final.exists():
        # An earlier open in this same second already copied the file, from a
        # state no later than this one; it is kept rather than overwritten.
        source.close()
        log.info(
            "kept the pre-migration copy already taken this second",
            extra={"event": "catalogue.snapshot_kept", "path": str(final), "drops": list(drops)},
        )
        return final
    try:
        directory.mkdir(parents=True, exist_ok=True)
        _sweep_staging(directory)
        _copy_intact(source, final)
    except (OSError, sqlite3.Error, BackupFailed) as exc:
        source.close()
        log.error(  # noqa: TRY400 -- the reason is the message; the traceback goes with the raise below
            "the catalogue was not migrated: the copy taken first could not be written to %s: %s",
            directory,
            exc,
            extra={"event": "catalogue.snapshot_failed", "directory": str(directory), "detail": str(exc), "drops": list(drops)},
        )
        raise SnapshotFailed(
            f"The catalogue at {catalogue_path} needs a migration that {_what_it_does(drops)}, and the copy "
            f"taken first could not be written to {directory}: {exc}. Nothing in the catalogue has been changed. "
            "Free space there or make it writable (or set BACKUP_DIR to a directory that is), then start again."
        ) from exc
    if not begun:
        _mark(catalogue_path)
    removed = _retain_snapshots(directory, keep=keep)
    log.info(
        "copied the catalogue aside before migrating it",
        extra={"event": "catalogue.snapshot_taken", "path": str(final), "drops": list(drops), "removed": list(removed)},
    )
    return final


def _what_it_does(replaced: tuple[str, ...]) -> str:
    """What the migration a copy is taken for does, as `SnapshotFailed` says it: what it drops, then a generation it raises.

    A rise (`migrations.ShapeGenerationRise`) is said as one, "raises the
    catalogue shape generation from 1 to 2", never as something dropped.
    """
    dropped = [item for item in replaced if not isinstance(item, migrations.ShapeGenerationRise)]
    raised = [item for item in replaced if isinstance(item, migrations.ShapeGenerationRise)]
    said = [f"drops {', '.join(dropped)}"] if dropped else []
    if raised:
        said.append(f"raises {', '.join(raised)}")
    return " and ".join(said)


def finish_migration(connection: sqlite3.Connection) -> None:
    """Remove the mark a pre-migration copy left on the catalogue: every migration it was taken for has run.

    The open runs it after every other migration, so the mark goes only once
    they have all succeeded, and the next upgrade that drops something takes a
    copy of its own. A `user_version` other than the mark is left as it is.
    """
    if _marked(connection):
        connection.execute("PRAGMA user_version = 0")
        connection.commit()


def _marked(connection: sqlite3.Connection) -> bool:
    return connection.execute("PRAGMA user_version").fetchone()[0] == MIGRATION_BEGUN


def _mark(catalogue_path: Path) -> None:
    """Mark the catalogue as copied for the migration about to run; after the copy, so a failed copy marks nothing."""
    connection = migrations.open_existing(catalogue_path)
    try:
        connection.execute(f"PRAGMA user_version = {MIGRATION_BEGUN}")
        connection.commit()
    finally:
        connection.close()


def _snapshots(directory: Path) -> list[Path]:
    """The pre-migration copies in `directory`, oldest first; only files named as this module names them."""
    return sorted(path for path in directory.glob(_SNAPSHOT_GLOB) if _instant(path.name, _SNAPSHOT_FORMAT) is not None)


def _retain_snapshots(directory: Path, *, keep: int) -> tuple[str, ...]:
    """Remove all but the newest `keep` pre-migration copies; return the names that went.

    After the new copy is written and checked, so a removal that fails costs
    nothing the open needs: it is logged and the open goes on, rather than
    stopping the server over a copy it no longer wants.
    """
    snapshots = _snapshots(directory)
    removed: list[str] = []
    for path in snapshots[: max(0, len(snapshots) - keep)]:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            log.warning(
                "could not remove the older pre-migration copy %s: %s",
                path,
                exc,
                extra={"event": "catalogue.snapshot_prune_failed", "path": str(path), "detail": str(exc)},
            )
            continue
        removed.append(path.name)
    return tuple(removed)
