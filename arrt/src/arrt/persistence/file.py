"""Opening the one file both halves of the model live in.

The catalogue and the pre-acceptance pipeline are separate concerns with separate
contracts and separate adapters, and they share a single SQLite file on purpose.
Acceptance is a promotion — a candidate work becomes an Artwork and its image
instances become that work's Sources — which writes on both sides and has to
commit once or not at all. Two connections cannot do that, so there is one, and
this is where it is opened with every table either adapter will ask for.

A schema fragment omitted here is not a subtle failure: the durable store
validates identifiers against the schema the file actually declares, so an
adapter reaching for a table nobody created is refused by name on its first call.
"""

import importlib.metadata
import logging
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Final, Protocol

from arrt.persistence.backup import finish_migration, take_pre_migration_snapshot
from arrt.persistence.durable import SqliteDurableStore
from arrt.persistence.migrations import (
    DEFAULT_WALL_NAME,
    carry_rotation_to_walls,
    establish_the_wall,
    file_had_table,
    mark_the_default_theme,
    open_existing,
    pending_drops,
    random_id,
    rename_awaiting_to_wanted,
    retire_conversations,
    retire_directives,
    retire_television_canvases,
    retire_wall_tokens,
    system_now,
    walls_name_displays,
)
from arrt.persistence.sqlite import CATALOGUE_SCHEMA
from arrt.persistence.sqlite_discovery import DISCOVERY_SCHEMA

log = logging.getLogger(__name__)

# -- which release last opened the file -------------------------------------------

#: The one row saying which release last opened this file, when, and whether
#: that open's migrations all ran. It answers three questions and holds nothing
#: else: the operator's before a rollback (which release last opened this, and
#: when), the server's at start (was this opened by a newer release than me),
#: and support's after a failed upgrade (did the last open finish migrating).
#:
#: **Not `PRAGMA user_version`**, which is the migration-in-progress mark
#: (`backup.MIGRATION_BEGUN`), and **neither adapter's**: the record is the
#: file's, so it is declared here beside the two schemas rather than in either.
#: An addition, so no migration takes anything for it, and a release from before
#: it ignores the table.
OPENED_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS catalogue_opened (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    release               TEXT NOT NULL,
    opened_at             TEXT NOT NULL,
    migrations_completed  INTEGER NOT NULL
);
"""

#: The part of a release's version this compares: three numbers. A suffix after
#: them (`rc1`, `+local`) is not ordered, so a candidate counts as its release.
_RELEASE: Final[re.Pattern[str]] = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def this_release() -> str:
    """The release this code is, as its installed package states it.

    **Raises rather than guessing** when the package is not installed: the
    release is what the file's record compares, and a placeholder written there
    would read as older than every real release, or newer, depending on its
    spelling. Every way the server runs (`uv run`, the image) installs it.
    """
    try:
        return importlib.metadata.version("arrt")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            "the arrt package is not installed, so this code cannot say which release it is, and the catalogue "
            "records that on every open; run it with `uv run` in arrt/, which installs it"
        ) from exc


def _release_order(release: str) -> tuple[int, int, int] | None:
    found = _RELEASE.match(release)
    return None if found is None else (int(found[1]), int(found[2]), int(found[3]))


@dataclass(frozen=True, slots=True)
class CatalogueOpened:
    """What the file's record says of the last open."""

    release: str
    opened_at: str
    migrations_completed: bool


class NewerRelease(RuntimeError):
    """The file was last opened by a release newer than this one, so this one does not open it."""


def last_opened(connection: sqlite3.Connection) -> CatalogueOpened | None:
    """The file's record of its last open, or None when it has none (a new file, or one no release carrying it opened)."""
    has_table = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'catalogue_opened'").fetchone()
    if has_table is None:
        return None
    row = connection.execute("SELECT release, opened_at, migrations_completed FROM catalogue_opened WHERE id = 1").fetchone()
    if row is None:
        return None
    return CatalogueOpened(release=str(row[0]), opened_at=str(row[1]), migrations_completed=bool(row[2]))


def refuse_a_newer_release(path: Path, *, release: str) -> CatalogueOpened | None:
    """Raise `NewerRelease` if the file says a release newer than `release` opened it last; return what it says.

    Asked before anything else touches the file, so a refused file is left
    exactly as the newer release left it: no copy, no widening, no record. A
    recorded release whose version cannot be read is refused too, by name,
    because this code writes only versions it can read, so one it cannot is
    from a release that writes something this one does not know. A file with no
    record, or one recording this release or an older one, opens.

    Read-write though it only reads, for the reason `migrations.open_existing`
    gives: a hot journal has to be rolled back before the file can be read.
    """
    if not path.exists():
        return None
    connection = open_existing(path)
    try:
        recorded = last_opened(connection)
    finally:
        connection.close()
    if recorded is None:
        return recorded
    theirs, ours = _release_order(recorded.release), _release_order(release)
    if ours is None:
        raise RuntimeError(f"this code's release {release!r} is not a version it can compare")
    if theirs is None or theirs > ours:
        log.error(
            "the catalogue was last opened by release %s, newer than this release %s; not opening it",
            recorded.release,
            release,
            extra={
                "event": "catalogue.newer_release_refused",
                "path": str(path),
                "recorded_release": recorded.release,
                "release": release,
                "opened_at": recorded.opened_at,
            },
        )
        raise NewerRelease(
            f"The catalogue at {path} was last opened by Arrt {recorded.release} on {recorded.opened_at}, and this is "
            f"Arrt {release}, an older release. It may have changed the file in ways this release would misread, so "
            "this release does not open it, and nothing in the file has been changed. Start Arrt "
            f"{recorded.release} or newer, or, to go back to this release, restore the copy taken before the newer "
            "release migrated the file (operational-spec.md § Routine Operations, Rollback)."
        )
    if not recorded.migrations_completed:
        log.warning(
            "the last open of the catalogue, by release %s on %s, did not finish its migrations; this open finishes them",
            recorded.release,
            recorded.opened_at,
            extra={
                "event": "catalogue.migrations_unfinished",
                "recorded_release": recorded.release,
                "opened_at": recorded.opened_at,
            },
        )
    return recorded


def record_the_open(
    connection: sqlite3.Connection, *, release: str, now: Callable[[], datetime] = system_now, completed: bool
) -> None:
    """Write this open into the file's record: first as begun, before any migration, then as completed, after all of them.

    Two writes rather than one after the migrations, so that a start killed in
    the middle of migrating leaves the file saying so: this release opened it,
    and did not finish. The next start rewrites the row as begun and finishes.
    The instant is the open's, written with the first.
    """
    if completed:
        connection.execute("UPDATE catalogue_opened SET migrations_completed = 1 WHERE id = 1")
    else:
        connection.execute(
            "INSERT INTO catalogue_opened (id, release, opened_at, migrations_completed) VALUES (1, ?, ?, 0) "
            "ON CONFLICT (id) DO UPDATE SET release = excluded.release, opened_at = excluded.opened_at, "
            "migrations_completed = 0",
            (release, now().isoformat()),
        )
    connection.commit()


def open_catalogue_file(
    path: Path | str,
    *,
    wall_name: str = DEFAULT_WALL_NAME,
    now: Callable[[], datetime] = system_now,
    new_id: Callable[[], str] = random_id,
    snapshot_directory: Path | None = None,
    release: str | None = None,
) -> SqliteDurableStore:
    """Open the catalogue file, creating whatever tables it does not yet have.

    The caller owns closing it. Both adapters are views over the returned store
    rather than owners of it, so there is exactly one place the connection is
    released.

    **`wall_name` is used only when this file has no wall at all** — on a fresh
    catalogue, and on the one-time move of a single-wall file onto the per-wall
    shape. A wall that exists keeps the name it has, because by then the name is
    the curator's rather than the deployment's; nothing here renames one. The
    default is what a deployment that has said nothing gets.

    `now` and `new_id` are what the migrations stamp and name the rows they
    write with: the system clock and a random UUID unless a caller passes its own.

    **A file a migration would drop something from is copied first**, before the
    store touches it, to `snapshot_directory` (`BACKUP_DIR` when the deployment
    sets one) or beside the catalogue otherwise: the rollback across a migration
    is a restore of that copy (`operational-spec.md` § Routine Operations). A
    file on the current shape, and a new one, take no copy, and nor does a start
    after one whose migrations failed: its copy is of the file before any of
    them ran. A copy that cannot be
    written raises `SnapshotFailed` with the file untouched, so no column goes
    without one. An entry point that holds the deployment's settings opens the
    file through `open_configured_catalogue`, which names the directory for it.

    **A file last opened by a newer release is refused first** (`NewerRelease`),
    before the copy and before the store touches it, and every open records
    `release` (this code's, `this_release()`, unless a caller says) in the file's
    `catalogue_opened` row: begun before the migrations, completed after them.
    The guard protects a downgrade only to a release that carries it; one from
    before it ignores the row and starts.
    """
    release = this_release() if release is None else release
    refuse_a_newer_release(Path(path), release=release)
    take_pre_migration_snapshot(
        Path(path),
        directory=snapshot_directory if snapshot_directory is not None else Path(path).parent,
        would_drop=pending_drops,
        now=now(),
    )
    return SqliteDurableStore(
        path,
        CATALOGUE_SCHEMA + DISCOVERY_SCHEMA + OPENED_SCHEMA,
        migrations=(
            # First: an open killed in any migration below leaves the file
            # saying this release opened it and did not finish.
            partial(record_the_open, release=release, now=now, completed=False),
            partial(establish_the_wall, wall_name=wall_name, seed=not file_had_table(path, "walls"), now=now, new_id=new_id),
            partial(mark_the_default_theme, now=now),
            rename_awaiting_to_wanted,
            retire_wall_tokens,
            # After the wall tokens go: both take columns off `walls`, and this
            # one carries rows onto `displays` before it does.
            partial(walls_name_displays, now=now, new_id=new_id),
            retire_conversations,
            retire_directives,
            retire_television_canvases,
            # After the walls take their final shape: this writes onto columns
            # the widening step has just added to `walls`.
            carry_rotation_to_walls,
            # Last: the copy taken for these migrations stands until they have
            # all run, and the next upgrade that drops something takes its own.
            finish_migration,
            # After the mark is cleared: completed means every step above ran.
            partial(record_the_open, release=release, now=now, completed=True),
        ),
    )


class CatalogueSettings(Protocol):
    """What a deployment says about its catalogue: `config.Settings` has these, read from the environment."""

    @property
    def catalogue_path(self) -> Path: ...

    @property
    def wall_name(self) -> str: ...

    @property
    def backup_dir(self) -> Path | None: ...


def open_configured_catalogue(settings: CatalogueSettings) -> SqliteDurableStore:
    """Open the deployment's catalogue as the server does, the copy before a migration going to `BACKUP_DIR`.

    Every entry point that can open the file can be the first open after an
    upgrade, and so the one that migrates it: the server, and the seed and
    identify commands. Each opens it here, so none can put the copy anywhere
    but where `operational-spec.md` § Backup and Restore sends the operator for it.
    """
    return open_catalogue_file(settings.catalogue_path, wall_name=settings.wall_name, snapshot_directory=settings.backup_dir)
