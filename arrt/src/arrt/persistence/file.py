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
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Final, Protocol

from arrt.counting import agree, counted
from arrt.persistence.backup import finish_migration, take_pre_migration_snapshot
from arrt.persistence.durable import Migration, SqliteDurableStore
from arrt.persistence.migrations import (
    DEFAULT_WALL_NAME,
    CatalogueOpened,
    begin_the_open,
    carry_rotation_to_walls,
    complete_the_open,
    establish_the_wall,
    file_had_table,
    last_opened,
    mark_the_default_theme,
    open_existing,
    random_id,
    record_of_a_copy,
    rename_awaiting_to_wanted,
    retire_conversations,
    retire_directives,
    retire_television_canvases,
    retire_wall_tokens,
    system_now,
    walls_name_displays,
    what_an_open_replaces,
)
from arrt.persistence.sqlite import CATALOGUE_SCHEMA
from arrt.persistence.sqlite_discovery import DISCOVERY_SCHEMA

log = logging.getLogger(__name__)

# -- which release last opened the file, and the shape it expects ------------------

#: The one row saying which release last opened this file, when, which catalogue
#: shape that release expects, and whether that open's migrations all ran. It
#: answers three questions and holds nothing else: the operator's before a
#: rollback (which release last opened this, and when), the server's at start
#: (was this opened by code expecting a shape this code does not know), and
#: support's after a failed upgrade (did the last open finish migrating).
#:
#: **Not `PRAGMA user_version`**, which is the migration-in-progress mark
#: (`backup.MIGRATION_BEGUN`), and **neither adapter's**: the record is the
#: file's, so it is declared here beside the two schemas rather than in either.
#: An addition, so no migration takes anything for it, and a release from before
#: it ignores the table. `schema_generation` is nullable because widening adds it
#: to a row that a build from before generations wrote (2026-11-19).
OPENED_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS catalogue_opened (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    release               TEXT NOT NULL,
    opened_at             TEXT NOT NULL,
    migrations_completed  INTEGER NOT NULL,
    schema_generation     INTEGER
);
"""

#: **The catalogue shape this code expects, as a number raised by hand.** The
#: file records it on every open, and the guard compares it: a file recorded by
#: code expecting a higher generation is refused before anything touches it.
#: Release numbers are not compared, because a rollback across no change to the
#: shape must open (the commonest rollback, a bad patch release), and because
#: `develop` carries one version string across many schema changes.
#:
#: **Raise it when a release would leave a file that an older release of this
#: generation would mishandle**: a step added to the open (`catalogue_migrations`;
#: every one does something older code does not know), and any table, column or
#: index taken away or declared differently. A table, column or index only
#: *added* leaves it as it is, since an older release ignores what it does not
#: declare; raise it for an addition too when older code ignoring it would be
#: wrong (a column whose value changes what a row means). The open that raises
#: it copies the file first, so the release left behind has a copy it opens.
#: `tests/unit/test_schema_generation.py` holds the shape and the steps each
#: generation was raised at (`tests/fixtures/catalogue-generations.json`) and
#: fails when either moves beyond an addition while this stays; a new value
#: written into a column an older release reads is beyond what it can see.
SCHEMA_GENERATION: Final[int] = 1

#: The part of a release's version this reads: three numbers. A suffix after
#: them (`rc1`, `+local`) is not ordered, so a candidate counts as its release.
_RELEASE: Final[re.Pattern[str]] = re.compile(r"(\d+)\.(\d+)\.(\d+)")

#: The two kinds of copy a refusal can name, as `backup` names them: the copy
#: taken before a migration, and a backup generation. `backup` owns the names;
#: `test_catalogue_opened.py` holds these equal to its own.
_PRE_MIGRATION_COPIES: Final[str] = "pre-migration-*Z.sqlite"
_GENERATIONS: Final[str] = "catalogue-*Z.sqlite"
#: How many copies a refusal names; the rest are counted.
_COPIES_NAMED: Final[int] = 3


def this_release() -> str:
    """The release this code is, as its installed package states it.

    **Raises rather than guessing** when the package is not installed: the
    release is what the file's record says opened it, and a placeholder written
    there would tell the operator nothing true. Every way the server runs
    (`uv run`, the image) installs it.
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


class UnreadableRelease(RuntimeError):
    """This code's own release is not a version of three numbers, so it does not write it into the catalogue."""


def require_a_readable_release(release: str) -> tuple[int, int, int]:
    """Raise `UnreadableRelease` unless `release` starts with three numbers; return them.

    Asked before anything is written, because the file keeps what the open
    writes: a release recorded there that a build from before shape generations
    cannot read is one that build refuses the file over, as newer than itself.
    """
    order = _release_order(release)
    if order is None:
        raise UnreadableRelease(
            f"This code's release is {release!r}, which is not a version of three numbers (such as 0.12.0), so it "
            "does not open the catalogue: every open records its release there, and a release from before catalogue "
            "shape generations reads one it cannot order as newer than itself and refuses the file. Give "
            "arrt/pyproject.toml a version of three numbers. Nothing in the catalogue has been changed."
        )
    return order


class NewerRelease(RuntimeError):
    """The file was last opened by code expecting a catalogue shape this code does not know, so this code does not open it."""


def _why_not(recorded: CatalogueOpened, release: str) -> str | None:
    """Why this code does not open a file whose record is `recorded`, or None when it does.

    **The shape generation decides**, and the release is not compared: a file
    recorded at this generation or a lower one opens, whatever release wrote it.
    **A row from before generations** (a release and no generation) was written
    by a build that predates them, so by one whose shape this code knows. Its
    release is read as the old guard read it only to keep the one refusal that
    guard made, of a release numbered later than this one; a release it cannot
    read opens, with a warning, rather than stopping a start.
    """
    generation = recorded.schema_generation
    if isinstance(generation, str):
        return f"whose record holds a catalogue shape generation this release cannot read ({generation!r})"
    if generation is not None:
        return f"which expects catalogue shape generation {generation}" if generation > SCHEMA_GENERATION else None
    theirs = _release_order(recorded.release)
    if theirs is None:
        log.warning(
            "the catalogue's record names release %r, which is not a version this release can read; the record "
            "predates shape generations, so its shape is one this release knows, and it opens",
            recorded.release,
            extra={"event": "catalogue.unreadable_release_recorded", "recorded_release": recorded.release},
        )
        return None
    if theirs > require_a_readable_release(release):
        return "a release numbered later than this one, from before catalogue shape generations"
    return None


def _copies_beside(path: Path, directory: Path, release: str) -> tuple[list[tuple[Path, CatalogueOpened | None]], int]:
    """The copies in `directory` and beside the file that `release` would open, newest first; and how many it would not."""
    found: set[Path] = set()
    for place in {directory, path.parent}:
        if place.is_dir():
            for pattern in (_PRE_MIGRATION_COPIES, _GENERATIONS):
                found.update(place.glob(pattern))
    opens: list[tuple[Path, CatalogueOpened | None]] = []
    refused = 0
    # Newest first: both kinds end in their UTC instant after a fixed prefix.
    for copy in sorted(found, key=lambda each: each.name.rsplit("-", 1)[-1], reverse=True):
        recorded = record_of_a_copy(copy)
        if recorded == "unreadable" or (recorded is not None and _why_not(recorded, release) is not None):
            refused += 1
        else:
            opens.append((copy, recorded))
    return opens, refused


def _ways_back(path: Path, directory: Path, recorded: CatalogueOpened, release: str) -> str:
    """The remedies a refusal names: the copies beside the file that this release opens, or that there are none."""
    opens, refused = _copies_beside(path, directory, release)
    steps = (
        "by the numbered steps in operational-spec.md § Backup and Restore (deploy/README.md § The way back across "
        "such a migration), which stop the server and remove catalogue.sqlite-journal before the copy goes in"
    )
    forward = f"start Arrt {recorded.release} or a newer release on it"
    if not opens:
        places = " or ".join(sorted({str(directory), str(path.parent)}))
        others = f" ({counted(refused, 'copy', 'copies')} {agree(refused, 'is', 'are')} there that this release refuses too)"
        return (
            f"No copy this release opens is in {places}{others if refused else ''}: a pre-migration copy "
            f"({_PRE_MIGRATION_COPIES}) is written only before an open that drops something or raises the shape "
            f"generation, and a backup generation ({_GENERATIONS}) only when BACKUP_DIR is set. To go on, {forward}; "
            f"or restore a copy you keep elsewhere {steps}."
        )
    named = "; ".join(
        str(copy) + (f" (last opened by Arrt {opened.release} on {opened.opened_at})" if opened is not None else "")
        for copy, opened in opens[:_COPIES_NAMED]
    )
    more = f"; and {len(opens) - _COPIES_NAMED} older" if len(opens) > _COPIES_NAMED else ""
    return (
        f"To go on, {forward}. To go back to this release, restore one of these copies, which it opens, {steps}: "
        f"{named}{more}. What changed in the catalogue after that copy was taken is not in it."
    )


def refuse_an_unknown_shape(path: Path, *, release: str, directory: Path) -> CatalogueOpened | None:
    """Raise `NewerRelease` if the file says code expecting a shape this code does not know opened it last; return what it says.

    Asked before anything else touches the file, so a refused file is left
    exactly as the newer release left it: no copy, no widening, no record. A
    file with no record opens, and so does one recording this shape generation
    or a lower one, whatever release it names (`_why_not` says how a row from
    before generations is read). The refusal names the copies of the file in
    `directory` and beside it that this release opens, newest first, or says
    there are none and which kinds there could have been.

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
    why = _why_not(recorded, release)
    if why is not None:
        log.error(
            "the catalogue was last opened by release %s, %s; this release %s knows shape generations up to %d; "
            "not opening it",
            recorded.release,
            why,
            release,
            SCHEMA_GENERATION,
            extra={
                "event": "catalogue.newer_release_refused",
                "path": str(path),
                "recorded_release": recorded.release,
                "recorded_generation": recorded.schema_generation,
                "release": release,
                "generation": SCHEMA_GENERATION,
                "opened_at": recorded.opened_at,
            },
        )
        raise NewerRelease(
            f"The catalogue at {path} was last opened by Arrt {recorded.release} on {recorded.opened_at}, {why}. "
            f"This is Arrt {release}, which knows catalogue shape generations up to {SCHEMA_GENERATION}, so it would "
            "misread the file and does not open it; nothing in the file has been changed. "
            + _ways_back(path, directory, recorded, release)
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


def catalogue_migrations(
    *,
    release: str,
    wall_name: str,
    seed_wall: bool,
    now: Callable[[], datetime],
    new_id: Callable[[], str],
) -> tuple[Migration, ...]:
    """Every step the open runs after the schema, in order; a step added here is what `SCHEMA_GENERATION` is raised for."""
    return (
        # First: an open killed in any step below leaves the file saying this
        # release opened it and did not finish.
        partial(begin_the_open, release=release, generation=SCHEMA_GENERATION, now=now),
        partial(establish_the_wall, wall_name=wall_name, seed=seed_wall, now=now, new_id=new_id),
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
        complete_the_open,
    )


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
    is a restore of that copy (`operational-spec.md` § Backup and Restore). So is
    a file recording a lower shape generation than `SCHEMA_GENERATION`, whose
    release would refuse it once this open has run. A file on the current shape,
    and a new one, take no copy, and nor does a start after one whose migrations
    failed: its copy is of the file before any of them ran. A copy that cannot be
    written raises `SnapshotFailed` with the file untouched, so no column goes
    without one. An entry point that holds the deployment's settings opens the
    file through `open_configured_catalogue`, which names the directory for it.

    **This code's release is checked first** (`UnreadableRelease` unless it is a
    version of three numbers), and then **a file last opened by code expecting a
    shape this code does not know is refused** (`NewerRelease`), both before the
    copy and before the store touches the file. Every open records `release`
    (this code's, `this_release()`, unless a caller says) and `SCHEMA_GENERATION`
    in the file's `catalogue_opened` row: begun before the migrations, completed
    after them. The guard protects a downgrade only to a release that carries
    it; one from before it ignores the row and starts.
    """
    release = this_release() if release is None else release
    require_a_readable_release(release)
    directory = snapshot_directory if snapshot_directory is not None else Path(path).parent
    refuse_an_unknown_shape(Path(path), release=release, directory=directory)
    take_pre_migration_snapshot(
        Path(path),
        directory=directory,
        would_drop=partial(what_an_open_replaces, generation=SCHEMA_GENERATION),
        now=now(),
    )
    return SqliteDurableStore(
        path,
        CATALOGUE_SCHEMA + DISCOVERY_SCHEMA + OPENED_SCHEMA,
        migrations=catalogue_migrations(
            release=release, wall_name=wall_name, seed_wall=not file_had_table(path, "walls"), now=now, new_id=new_id
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
