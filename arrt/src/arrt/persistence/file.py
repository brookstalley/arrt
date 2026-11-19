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

from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Protocol

from arrt.persistence.backup import finish_migration, take_pre_migration_snapshot
from arrt.persistence.durable import SqliteDurableStore
from arrt.persistence.migrations import (
    DEFAULT_WALL_NAME,
    carry_rotation_to_walls,
    establish_the_wall,
    file_had_table,
    mark_the_default_theme,
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


def open_catalogue_file(
    path: Path | str,
    *,
    wall_name: str = DEFAULT_WALL_NAME,
    now: Callable[[], datetime] = system_now,
    new_id: Callable[[], str] = random_id,
    snapshot_directory: Path | None = None,
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
    """
    take_pre_migration_snapshot(
        Path(path),
        directory=snapshot_directory if snapshot_directory is not None else Path(path).parent,
        would_drop=pending_drops,
        now=now(),
    )
    return SqliteDurableStore(
        path,
        CATALOGUE_SCHEMA + DISCOVERY_SCHEMA,
        migrations=(
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
