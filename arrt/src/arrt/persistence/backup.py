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

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from arrt import observations
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
#: A copy in progress. Never matched by the glob above, so a pass that dies
#: half-way leaves nothing retention or a restorer mistakes for a generation.
_PARTIAL_SUFFIX: Final[str] = ".partial"

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

    def __init__(self, *, catalogue_path: Path, directory: Path, receipt_path: Path, keep: int) -> None:
        if keep < 1:
            raise ValueError(f"keep must be at least 1, got {keep}")
        self._catalogue_path = catalogue_path
        self._directory = directory
        self._receipt_path = receipt_path
        self._keep = keep

    def run(self, *, now: datetime | None = None) -> BackupResult:
        """Take one generation. Raises on failure, after logging it, with the previous receipt untouched."""
        started = now or datetime.now(UTC)
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
            },
        )
        return result

    def _take(self, started: datetime) -> BackupResult:
        self._directory.mkdir(parents=True, exist_ok=True)
        final = self._directory / started.strftime(_GENERATION_FORMAT)
        partial = final.with_name(final.name + _PARTIAL_SUFFIX)
        partial.unlink(missing_ok=True)
        # A connection of its own, read-only: VACUUM INTO reads one consistent
        # snapshot and never takes the server's write lock.
        try:
            source = sqlite3.connect(f"file:{self._catalogue_path}?mode=ro", uri=True)
            try:
                source.execute("VACUUM INTO ?", (str(partial),))
            finally:
                source.close()
            _require_intact(partial)
            os.replace(partial, final)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        removed = self._retain()
        byte_size = final.stat().st_size
        kept = len(self._generations())
        self._write_receipt(started=started, path=final, byte_size=byte_size, kept=kept)
        return BackupResult(path=final, byte_size=byte_size, kept=kept, removed=removed)

    def _generations(self) -> list[Path]:
        return sorted(self._directory.glob(_GENERATION_GLOB))

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
            COMPLETED_AT_KEY: datetime.now(UTC).isoformat(),
            "started_at": started.isoformat(),
            "path": str(path),
            "bytes": byte_size,
            "generations_kept": kept,
        }
        partial = self._receipt_path.with_name(self._receipt_path.name + _PARTIAL_SUFFIX)
        partial.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        os.replace(partial, self._receipt_path)


class BackupFailed(Exception):
    """A backup pass that ran and produced nothing it could trust."""


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
    """Back up once now, then every `interval_seconds`, on a daemon thread; return the call that stops it.

    Now rather than after the first interval, for the reason the preview sweep
    gives: a server that restarts more often than the interval would otherwise
    never back up. A failed pass is logged by the job and the loop carries on —
    the receipt's age on the health panel is what says it has been failing.
    """
    stop = threading.Event()

    def loop() -> None:
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
