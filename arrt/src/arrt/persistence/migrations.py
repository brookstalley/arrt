"""Schema changes a catalogue file cannot be widened into.

`SqliteDurableStore` widens a file by adding columns the declared schema has and
the file does not, which is the one change SQLite applies in place and the only
one that cannot lose data. Everything else — a column that goes away, a table
that is replaced by a differently-keyed one, rows that have to be carried from
the first to the second — has to be written down, and this is where it is
written.

**A migration here is idempotent and safe to interrupt.** It runs on every open,
against a file that may already have had it applied, may have had half of it
applied, or may never have seen it; every step is guarded by what the file
actually holds rather than by a version number the file would have to be trusted
to keep. The order is chosen so that any prefix of it leaves a file the next open
finishes correctly: rows are carried before anything that held them is dropped.

**A migration that takes something away says so first, without taking it.**
Each one that drops a column or a table decides whether it will act by asking a
function of its own what it would drop, and `pending_drops` asks all of them.
That is what the open asks before it lets any migration run, so a copy of the
file is taken before anything is lost (`backup.take_pre_migration_snapshot`),
and only then. The question is each migration's own guard rather than a second
opinion beside it, so the two cannot disagree about whether it will act.
"""

import logging
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

log = logging.getLogger(__name__)

#: What the deployment's one wall is called when nobody has said. Deliberately
#: not a place — "Living room" would be a confident lie on every deployment that
#: is not one — and deliberately not empty, because the name is the noun every
#: confirmation about that wall is built around.
#:
#: Declared here rather than in `config.py` so that this module, which is where
#: the name is first needed and where the default has to be applied, does not
#: have to reach up into configuration for it. `config.py` reads it back down.
DEFAULT_WALL_NAME: Final[str] = "The wall"

#: The oldest SQLite measured to drop a column from this catalogue's tables.
#: `ALTER TABLE ... DROP COLUMN` arrived in 3.35 (2021), but up to at least 3.50.4
#: it refuses ("incomplete input") when a `--` comment holding a backtick-quoted
#: word sits just before the dropped column, as this repository's DDL comments
#: do. Measured 2026-11-08 on uv's builds: 3.45.1, 3.46.0, 3.47.1, 3.49.1 and
#: 3.50.4 refused, 3.53.1 dropped. Named rather than assumed: below it the drop
#: fails naming neither the version nor the remedy, on the machine nobody is at;
#: the refusal names both.
_DROP_COLUMN_SINCE: Final[tuple[int, int, int]] = (3, 53, 1)


def system_now() -> datetime:
    """The moment a migration stamps the rows it writes, unless its caller passes one."""
    return datetime.now(UTC)


def random_id() -> str:
    """A new row's id, unless the migration's caller passes a way to name it."""
    return str(uuid.uuid4())


def establish_the_wall(
    connection: sqlite3.Connection,
    *,
    wall_name: str,
    seed: bool = True,
    now: Callable[[], datetime] = system_now,
    new_id: Callable[[], str] = random_id,
) -> None:
    """Move a single-wall catalogue onto `Wall` and `ThemeAssignment`.

    Before 2026-08-12 a theme was hung by a boolean on the theme itself — one
    that could only ever mean "active on the one television". This carries it
    onto a named wall: whichever theme was active is hung on it, so no
    deployment loses its picture.

    **It also seeds the wall on a fresh file**, which is not a separate concern
    wearing this one's clothes: a catalogue with no wall has nowhere to hang
    anything, and every operation that changes a wall names one. A wall cannot
    be seeded in the DDL because its name is a deployment value and its id is a
    UUID.

    **The name is written once.** A wall that already exists keeps the name it
    has — it is the curator's word by then, and configuration must not overwrite
    it on the next restart. Nothing here renames a wall.

    **`seed` is false for a file that already had a `walls` table**, which the
    caller reads before the schema runs. Such a file with no wall in it is one
    whose curator deleted them all, which is theirs to do: seeding one back on
    every restart would undo the delete. A file with no `walls` table is new, or
    predates walls, and both still get one; one from before walls is recognised
    by its `themes.is_active` too, so an open interrupted before this ran still
    carries its hung theme. One edge is accepted: a *new* file interrupted after
    its schema committed and before this ran opens next time with no wall, and
    Walls offers *Add wall…*.

    `now` and `new_id` stamp and name the seeded wall; a caller passes its own
    so that opening a file need read neither the clock nor randomness.
    """
    # A file from before walls still carries `themes.is_active` until this has
    # run to the end, so it is carried even when an interrupted open left an
    # empty `walls` table behind and the caller saw one.
    carry = seed or _has_column(connection, "themes", "is_active")
    if _walls(connection) or not carry:
        if not _walls(connection):
            log.info("No wall is recorded; Walls offers Add wall….")
        _drop_what_the_wall_replaced(connection)
        return

    hung_theme_id = _theme_that_was_active(connection)
    stamped = now().isoformat()
    wall_id = new_id()

    connection.execute("INSERT INTO walls (id, name, created_at) VALUES (?, ?, ?)", (wall_id, wall_name, stamped))
    if hung_theme_id is not None:
        connection.execute(
            "INSERT INTO theme_assignments (wall_id, theme_id, assigned_at) VALUES (?, ?, ?)",
            (wall_id, hung_theme_id, stamped),
        )
    # Committed before the drops below, so that an interrupted open leaves a file
    # holding the carried rows and the columns they came from — which the next
    # open reads as "already migrated, still to tidy" rather than as a fresh file.
    connection.commit()

    log.info(
        "Established wall %r (%s); %s.",
        wall_name,
        wall_id,
        f"hung theme {hung_theme_id}" if hung_theme_id else "nothing is hanging on it",
    )
    _drop_what_the_wall_replaced(connection)


def _walls(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM walls").fetchone()[0])


def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall())


def _has_table(connection: sqlite3.Connection, table: str) -> bool:
    found = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return found is not None


def _theme_that_was_active(connection: sqlite3.Connection) -> str | None:
    """Which theme the single-wall file had on the wall, or None.

    None is the ordinary answer on a fresh file and on a catalogue with no themes
    — and it is also the honest answer for a file whose themes all sat inactive,
    which the partial index always permitted. Nothing is promoted to fill it: a
    wall with nothing hanging on it is a designed state, and with more than one
    wall there is no defensible answer to which theme should appear on a wall the
    curator has not hung anything on.
    """
    if not _has_column(connection, "themes", "is_active"):
        return None
    # Oldest first so that a file which somehow held two active themes — the
    # partial index made that unreachable, but a hand-edited file is not bound by
    # it — resolves the same way on every machine that opens it.
    row = connection.execute("SELECT id FROM themes WHERE is_active = 1 ORDER BY created_at, id LIMIT 1").fetchone()
    return None if row is None else str(row["id"])


def _drop_what_the_wall_replaced(connection: sqlite3.Connection) -> None:
    """Take away the single-wall shape, once nothing needs to read it.

    Separate from the carry above so that both halves are guarded by the file
    rather than by each other: this runs on every open and does nothing to a file
    that has already had it.
    """
    leftovers = _wall_replaced_leftovers(connection)
    if "themes.is_active" in leftovers:
        _require_drop_column()
        # The index has to go first — SQLite refuses to drop a column an index
        # names, and this one is over exactly that column.
        connection.execute("DROP INDEX IF EXISTS themes_one_active")
        connection.execute("ALTER TABLE themes DROP COLUMN is_active")
        log.info("Dropped themes.is_active and its partial index; hanging is now a row on theme_assignments.")
    if "table directive" in leftovers:
        connection.execute("DROP TABLE directive")
        log.info("Dropped the singleton directive table, which no wall reads.")
    connection.commit()


def _wall_replaced_leftovers(connection: sqlite3.Connection) -> tuple[str, ...]:
    """What `_drop_what_the_wall_replaced` would take from this file: the single-wall column and table."""
    return (
        *(("themes.is_active",) if _has_column(connection, "themes", "is_active") else ()),
        *(("table directive",) if _has_table(connection, "directive") else ()),
    )


def _require_drop_column(*, predates: str = "per-wall hanging") -> None:
    # Takes no connection: the capability is the interpreter's, not this file's,
    # and a connection parameter here would suggest the answer could differ per
    # file. `predates` names the change, so the refusal says which migration needs it.
    version = tuple(int(part) for part in sqlite3.sqlite_version.split("."))
    if version < _DROP_COLUMN_SINCE:
        raise RuntimeError(
            f"This catalogue file predates {predates} and migrating it needs SQLite "
            f"{'.'.join(str(part) for part in _DROP_COLUMN_SINCE)} or newer to drop a column; "
            f"this interpreter is linked against {sqlite3.sqlite_version}. Run it under the "
            f"uv-managed Python the repository's `.python-version` names, which carries one."
        )


#: The theme the owner's catalogue already holds every work in, and so the one
#: made the default when the default arrived. Matched ignoring case.
DEFAULT_THEME_NAME: Final[str] = "All works"


def mark_the_default_theme(connection: sqlite3.Connection, *, now: Callable[[], datetime] = system_now) -> None:
    """Bring a file written before the default theme onto it, once.

    Two things, guarded together by what the file holds: **works present and no
    offers recorded**, which is a file this code has never opened, because from
    then on every work is offered as it arrives. On such a file:

    - the theme named *All works* becomes the default, unless some theme already
      is; a catalogue with no theme of that name gets no default until the curator
      makes one;
    - every work already held is recorded as offered, because the curator placed
      those works by hand before the default existed, and startup would otherwise
      offer all of them at once.

    An empty file is left alone, because nothing on it predates the default. Run
    a second time, the guard is false whatever themes exist by then, so a theme
    the curator later names *All works* is not marked behind their back.

    This crosses the Library/Programming seam, reading `artworks` to write
    Programming's offers. It is allowed here as a migration over the one file
    both still share; when Programming's tables get a file of their own, the
    back-fill becomes a one-off against the facade.
    """
    if connection.execute("SELECT 1 FROM default_theme_offers LIMIT 1").fetchone() is not None:
        return
    if connection.execute("SELECT 1 FROM artworks LIMIT 1").fetchone() is None:
        return
    if connection.execute("SELECT 1 FROM themes WHERE is_default = 1").fetchone() is None:
        named = connection.execute(
            "SELECT id FROM themes WHERE name = ? COLLATE NOCASE ORDER BY created_at LIMIT 1", (DEFAULT_THEME_NAME,)
        ).fetchone()
        if named is not None:
            connection.execute("UPDATE themes SET is_default = 1 WHERE id = ?", (named[0],))
            log.info("Made the theme %r the default: works accepted from now on join it.", DEFAULT_THEME_NAME)
    connection.execute(
        "INSERT INTO default_theme_offers (artwork_id, offered_at) SELECT id, ? FROM artworks",
        (now().isoformat(),),
    )


def rename_awaiting_to_wanted(connection: sqlite3.Connection) -> None:
    """Rewrite the verdict `awaiting_better_image` as `wanted`, wherever a row still holds it.

    The verdict was renamed because its old name was false of a work that never
    had a scan, and the curator now wants such works too. Nothing reads the old
    spelling any more — `Verdict` has no member for it, so a row left holding it
    would fail to load rather than be read as something else.

    Guarded by the rows themselves: the statement touches only rows still holding
    the old value, so a second open finds none and does nothing. It is one
    statement, so an interrupted open leaves every row either rewritten or not,
    and the next open finishes the rest.
    """
    rewritten = connection.execute(
        "UPDATE candidate_works SET verdict = 'wanted' WHERE verdict = 'awaiting_better_image'"
    ).rowcount
    connection.commit()
    if rewritten:
        log.info("Rewrote %d candidate works from 'awaiting_better_image' to 'wanted'.", rewritten)


#: The wall token columns, which clients replaced on 2026-10-02 (`clients.md`).
_RETIRED_WALL_TOKEN_COLUMNS: Final[tuple[str, ...]] = ("token_verifier", "token_issued_at")


def retire_wall_tokens(connection: sqlite3.Connection) -> None:
    """Drop the per-wall token columns, so a wall's old token is not kept anywhere.

    A Player is now admitted by its *client's* token, and a wall token admits
    nothing. Dropping the verifiers rather than leaving them unread makes that
    true of the file as well as of the code: there is no stored verifier left for
    a later change to start honouring again by mistake. No transition is kept,
    by the plan's ruling: there is one Player, and it moves to a client token in
    the same change.

    Guarded by the file: a column already gone is skipped, so a second open, or
    one after an interrupted first, does what is left and nothing more.
    """
    retired = _present(connection, "walls", _RETIRED_WALL_TOKEN_COLUMNS)
    if not retired:
        return
    _require_drop_column(predates="client tokens")
    for column in retired:
        connection.execute(f'ALTER TABLE walls DROP COLUMN "{column}"')
    connection.commit()
    log.info("Dropped walls.%s: Players are admitted by their client's token now.", " and walls.".join(retired))


#: The columns a wall named its screen by before displays were records.
_WALL_PLACEMENT_COLUMNS: Final[tuple[str, ...]] = ("client_id", "output")


def walls_name_displays(
    connection: sqlite3.Connection,
    *,
    now: Callable[[], datetime] = system_now,
    new_id: Callable[[], str] = random_id,
) -> None:
    """Move each wall from a client and an output name onto a display record, keeping it where it hangs.

    Before 2026-10-08 a wall named the client that showed it and the name of that
    client's output. A wall now names a display, the server's record of the
    screen, which names its client. Every assigned wall gets a display keyed
    `{client_id}/{output}`, the identity a client-attached output has, on the
    same client and output, so `GET /client` names the same walls on the same
    outputs before and after. A Frame's display is re-keyed to the set's own
    identity the first time its client reports one on that output
    (`ClientService.record_heartbeat`), and keeps its walls.

    Guarded by the file, and ordered so that any prefix is finished by the next
    open: the rows are carried and committed before the columns that held them
    are dropped, and a wall that already names a display is not carried again.
    """
    present = _present(connection, "walls", _WALL_PLACEMENT_COLUMNS)
    if not present:
        return
    # Both or neither, except after an open interrupted between the two drops
    # below, when only `output` is left and there is nothing to carry.
    carried = (
        connection.execute(
            "SELECT id, client_id, output FROM walls WHERE client_id IS NOT NULL AND output IS NOT NULL AND display_id IS NULL"
        ).fetchall()
        if len(present) == len(_WALL_PLACEMENT_COLUMNS)
        else []
    )
    # Read once there is something to stamp, so an open with nothing to carry
    # reads no clock.
    stamped = now().isoformat() if carried else ""
    for wall in carried:
        identity = f"{wall['client_id']}/{wall['output']}"
        found = connection.execute("SELECT id FROM displays WHERE identity = ?", (identity,)).fetchone()
        if found is None:
            display_id = new_id()
            # Kind is left unknown: the file never held it, and the client's next
            # report states it. Guessed from the output's name, it would be a fact
            # this server made up.
            connection.execute(
                "INSERT INTO displays (id, identity, client_id, output, kind, first_seen) VALUES (?, ?, ?, ?, NULL, ?)",
                (display_id, identity, wall["client_id"], wall["output"], stamped),
            )
        else:
            display_id = found["id"]
        connection.execute("UPDATE walls SET display_id = ? WHERE id = ?", (display_id, wall["id"]))
    connection.commit()

    _require_drop_column(predates="displays")
    # The index first: SQLite refuses to drop a column an index names.
    connection.execute("DROP INDEX IF EXISTS walls_one_per_output")
    for column in present:
        connection.execute(f'ALTER TABLE walls DROP COLUMN "{column}"')
    connection.commit()
    log.info(
        "Moved %d assigned wall(s) onto display records and dropped walls.client_id and walls.output.",
        len(carried),
    )


#: The citing columns and the index over each, which has to go before its column.
_TURN_CITATIONS: Final[tuple[tuple[str, str, str], ...]] = (
    ("affinities", "source_turn_id", "affinities_by_turn"),
    ("spend_records", "conversation_turn_id", "spend_records_by_turn"),
)


def retire_conversations(connection: sqlite3.Connection) -> None:
    """Drop the stored conversations, and the two columns that cited a turn.

    Before 2026-10-09 Ask kept its threads here. They are no longer stored: the
    owner ruled that old ones may simply go (2026-10-08). Deleting a conversation
    always nulled `affinities.source_turn_id` and `spend_records.conversation_turn_id`
    and left the rows, because a judgment and a cent outlive the thread they came
    from. So this keeps every row in both tables and only takes the citations away.

    Guarded by the file, and ordered so that any prefix is finished by the next
    open: the citing columns go before the tables they point at, and each step is
    skipped where it is already done.
    """
    citing = _turn_citations(connection)
    if citing:
        _require_drop_column(predates="the retirement of stored conversations")
    for table, column, index in citing:
        # SQLite refuses to drop a column an index names.
        connection.execute(f'DROP INDEX IF EXISTS "{index}"')
        connection.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
        log.info("Dropped %s.%s: conversations are no longer stored, so there is no turn to cite.", table, column)
    connection.commit()
    for table in _conversation_tables(connection):
        connection.execute(f'DROP TABLE "{table}"')
        log.info("Dropped table %s: Ask's threads are not stored.", table)
    connection.commit()


def _turn_citations(connection: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """The turn-citing columns this file still has, each with the index over it."""
    return [(table, column, index) for table, column, index in _TURN_CITATIONS if _has_column(connection, table, column)]


def _conversation_tables(connection: sqlite3.Connection) -> list[str]:
    """The stored-conversation tables this file still has, the citing one first."""
    return [table for table in ("conversation_turns", "conversations") if _has_table(connection, table)]


def _conversation_leftovers(connection: sqlite3.Connection) -> tuple[str, ...]:
    """What `retire_conversations` would take from this file."""
    return (
        *(f"{table}.{column}" for table, column, _ in _turn_citations(connection)),
        *(f"table {table}" for table in _conversation_tables(connection)),
    )


def retire_directives(connection: sqlite3.Connection) -> None:
    """Drop each wall's directive: its counter and the work it pinned.

    A Player read the directive from manifest major 1, which is no longer
    published. Show now and next republish the wall's schedule instead
    (`player-contract.md` § What happens to `show_now` and `next`), so nothing
    reads a counter or a pin, and nothing is carried. The table also held
    `pinned_work_id`, a key across the Library/Programming seam
    (`architecture.md` § Direction, rule 3), which goes with it.

    Guarded by the file: a file without the table, or a fresh one, is left alone.
    """
    if not _directive_leftovers(connection):
        return
    # Its index over the pin goes with it: SQLite drops a table's indexes with the table.
    connection.execute("DROP TABLE directives")
    log.info("Dropped table directives: show now and next republish the wall's schedule instead.")
    connection.commit()


def _directive_leftovers(connection: sqlite3.Connection) -> tuple[str, ...]:
    """What `retire_directives` would take from this file."""
    return ("table directives",) if _has_table(connection, "directives") else ()


def retire_television_canvases(connection: sqlite3.Connection) -> None:
    """Forget every composed television canvas, and the previews drawn from them, once.

    Each Player draws its own mat on the presentation master (`architecture.md`,
    the label and the mat belong to the device). So the `tv_display` rows go, and
    with them every `wall_preview` row, because a preview drawn from a canvas
    passes the hash test against the original and would go on showing the old
    matted picture; without its row it is drawn again from the master on next
    view. Then the `mat_hex` column, which only a canvas filled.

    **Keyed on that column, so it happens once.** Wall previews are still made,
    from the master, after this; deleting them on every open would throw each one
    away at each start. A file still carrying `mat_hex` is one this has not run
    on, and the deletes and the drop are its single pass: the column goes last,
    so an open interrupted before it repeats the pass rather than skipping it.

    **The files are left where they are.** `ART_ROOT/ready/` holds the canvases,
    and removing a directory of the operator's files is the operator's act;
    `deploy/README.md` names it as safe to delete. The line says how many rows
    went, 0 included, so the operator has one line to look for either way.

    **A file from before `mat_hex` still has canvases** (v0.1.0's: the column
    arrived in v0.2.0, the `tv_display` rows long before). Opened by today's code
    without a release between, it has no column to key the pass on, and its
    canvas rows name a kind `RenditionKind` no longer has, so reading the work's
    renditions failed (`tests/system/test_migration_chain.py`, found 2026-11-19).
    Such a file loses its `tv_display` rows, and only those: it never held a
    `wall_preview`, the kind came later, and a preview on a file without the
    column is one this code drew from a master. Keyed on the rows, so a second
    open finds none.
    """
    if not _canvas_leftovers(connection):
        return
    if not _has_column(connection, "renditions", "mat_hex"):
        gone = connection.execute("DELETE FROM renditions WHERE kind = 'tv_display'").rowcount
        connection.commit()
        log.info("Forgot %d television canvases from before renditions.mat_hex; ART_ROOT/ready/ can be deleted.", gone)
        return
    gone = connection.execute("DELETE FROM renditions WHERE kind IN ('tv_display', 'wall_preview')").rowcount
    connection.commit()
    _require_drop_column(predates="the retirement of television canvases")
    connection.execute("ALTER TABLE renditions DROP COLUMN mat_hex")
    connection.commit()
    log.info(
        "Forgot %d television canvases and previews drawn from them, and dropped renditions.mat_hex; "
        "ART_ROOT/ready/ can be deleted.",
        gone,
    )


def _canvas_leftovers(connection: sqlite3.Connection) -> tuple[str, ...]:
    """What `retire_television_canvases` would take from this file: the column, and the rows with it.

    Or, on a file from before the column, its canvas rows alone.
    """
    if not _has_table(connection, "renditions"):
        return ()
    if _has_column(connection, "renditions", "mat_hex"):
        return ("renditions.mat_hex", "the television canvases and wall previews in renditions")
    if connection.execute("SELECT 1 FROM renditions WHERE kind = 'tv_display' LIMIT 1").fetchone() is not None:
        return ("the television canvases in renditions",)
    return ()


#: The theme's two playing settings, which became the wall's: the order is the
#: carry's, and both go in one pass.
_THEME_ROTATION_COLUMNS: Final[tuple[str, ...]] = ("rotation_interval_seconds", "shuffle")


def carry_rotation_to_walls(connection: sqlite3.Connection) -> None:
    """Move how long a work stays up and whether it is shuffled from each theme to the walls hanging it.

    A theme has an order and is never shuffled; shuffle and the interval are
    settings of the wall that plays it (the owner's ruling 2 of 2026-10-11,
    `ia-proposal.md`). So that no wall shows anything differently after, each
    wall hanging a theme that set a value takes that value. A theme that set
    nothing gives its walls nothing, which is the same deployment default. A
    theme hanging nowhere has no wall to give its value to, and the value goes:
    each is logged by theme and value, because it is a setting nobody took away.

    Guarded by the file, and ordered so that any prefix is finished by the next
    open: the values are carried and committed before the theme columns are
    dropped, and a wall that already has a value of its own keeps it, so a
    carry repeated after an interrupted drop changes nothing.
    """
    present = _present(connection, "themes", _THEME_ROTATION_COLUMNS)
    if not present:
        return
    # Both or neither, except after an open interrupted between the two drops
    # below, when only `shuffle` is left and has already been carried.
    if len(present) == len(_THEME_ROTATION_COLUMNS):
        themes = connection.execute(
            "SELECT id, name, rotation_interval_seconds, shuffle FROM themes "
            "WHERE rotation_interval_seconds IS NOT NULL OR shuffle IS NOT NULL"
        ).fetchall()
        carried = 0
        hung = 0
        for theme in themes:
            walls = connection.execute("SELECT wall_id FROM theme_assignments WHERE theme_id = ?", (theme["id"],)).fetchall()
            if not walls:
                log.warning(
                    "Theme %r set rotation_interval_seconds=%s, shuffle=%s and hangs on no wall; "
                    "these are a wall's settings now, so they were not kept.",
                    theme["name"],
                    theme["rotation_interval_seconds"],
                    None if theme["shuffle"] is None else bool(theme["shuffle"]),
                )
            else:
                hung += 1
            for wall in walls:
                connection.execute(
                    "UPDATE walls SET "
                    "rotation_interval_seconds = COALESCE(rotation_interval_seconds, ?), "
                    "shuffle = COALESCE(shuffle, ?) WHERE id = ?",
                    (theme["rotation_interval_seconds"], theme["shuffle"], wall["wall_id"]),
                )
                carried += 1
        connection.commit()
        log.info("Carried the rotation settings of %d hung theme(s) onto %d wall(s).", hung, carried)

    _require_drop_column(predates="rotation as a wall setting")
    for column in present:
        connection.execute(f'ALTER TABLE themes DROP COLUMN "{column}"')
    connection.commit()
    log.info("Dropped themes.rotation_interval_seconds and themes.shuffle; they are the wall's now.")


def _present(connection: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> list[str]:
    """Which of `columns` this file's `table` still has, in the order given."""
    return [column for column in columns if _has_column(connection, table, column)]


def _columns_left(table: str, columns: tuple[str, ...]) -> Callable[[sqlite3.Connection], tuple[str, ...]]:
    """What a migration that drops `columns` from `table` would take from a file."""

    def leftovers(connection: sqlite3.Connection) -> tuple[str, ...]:
        return tuple(f"{table}.{column}" for column in _present(connection, table, columns))

    return leftovers


#: Every function here that drops a column or a table, and the question it asks
#: itself first: what it would drop from this file. Keyed by the function that
#: runs the `DROP`, which is what `test_pre_migration_snapshot.py` checks every
#: such function in this module against, so a new drop without a question fails
#: there by name rather than going unsnapshotted.
WOULD_DROP: Final[Mapping[Callable[..., None], Callable[[sqlite3.Connection], tuple[str, ...]]]] = {
    _drop_what_the_wall_replaced: _wall_replaced_leftovers,
    retire_wall_tokens: _columns_left("walls", _RETIRED_WALL_TOKEN_COLUMNS),
    walls_name_displays: _columns_left("walls", _WALL_PLACEMENT_COLUMNS),
    retire_conversations: _conversation_leftovers,
    retire_directives: _directive_leftovers,
    retire_television_canvases: _canvas_leftovers,
    carry_rotation_to_walls: _columns_left("themes", _THEME_ROTATION_COLUMNS),
}


def pending_drops(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Everything the migrations would take from this file if it were opened now. Takes nothing.

    Empty for a file already on the current shape and for a new one, which is
    the open that takes no copy.
    """
    return tuple(dropped for would_drop in WOULD_DROP.values() for dropped in would_drop(connection))


def file_had_table(path: Path | str, table: str) -> bool:
    """Whether the file holds `table` before this open's schema creates it.

    Asked before the store opens, because the schema creates every table it
    names: afterwards a new file and an emptied one look alike. A path that does
    not exist yet is answered without opening it, so asking never creates one.
    """
    if not Path(path).exists():
        return False
    connection = open_existing(path)
    try:
        found = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    finally:
        connection.close()
    return found is not None


def open_existing(path: Path | str) -> sqlite3.Connection:
    """A connection to a catalogue file that exists, for asking it something before the store opens it.

    **Read-write, though nothing here writes, and that is measured.** A process
    killed inside a transaction leaves a hot rollback journal beside the file,
    and the next reader has to roll it back before it can read anything. A
    `mode=ro` connection cannot, and refuses every read with "attempt to write a
    readonly database" (measured on SQLite 3.53.1 with a journal left by a
    killed writer): a server asking that way would refuse to start after every
    such crash, and every restart would ask again. Rolling the journal back
    returns the file to its last commit, which is what the store's own open
    would do first anyway.
    """
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


# -- the file's record of which release last opened it ------------------------------
#
# The record is `file.py`'s (`OPENED_SCHEMA`, `SCHEMA_GENERATION`, and the guard
# that reads it before anything else touches the file). Its reads and writes are
# here, beside `file_had_table` and `open_existing`, because this module is where
# the open's work on the file as a file reaches the driver: `file.py` asks, and
# imports no driver of its own (`tests/unit/test_persistence_boundary.py`).


@dataclass(frozen=True, slots=True)
class CatalogueOpened:
    """What the file's record says of the last open."""

    release: str
    opened_at: str
    migrations_completed: bool
    #: The catalogue shape generation the opening code expects (`file.SCHEMA_GENERATION`).
    #: None on a row written before the record carried one (a build from before
    #: 2026-11-19's amendment, which records a release and no shape), and the
    #: stored text when it is not a whole number, which no release writes.
    schema_generation: int | str | None


def last_opened(connection: sqlite3.Connection) -> CatalogueOpened | None:
    """The file's record of its last open, or None when it has none (a new file, or one no release carrying it opened).

    Reads a row that predates the generation column too: the guard asks before
    the store has widened the file, so the column may not be there yet.
    """
    if not _has_table(connection, "catalogue_opened"):
        return None
    generation = "schema_generation" if _has_column(connection, "catalogue_opened", "schema_generation") else "NULL"
    row = connection.execute(
        f"SELECT release, opened_at, migrations_completed, {generation} FROM catalogue_opened WHERE id = 1"  # noqa: S608 -- one of two fixed words
    ).fetchone()
    if row is None:
        return None
    stored = row[3]
    return CatalogueOpened(
        release=str(row[0]),
        opened_at=str(row[1]),
        migrations_completed=bool(row[2]),
        schema_generation=stored if stored is None or type(stored) is int else str(stored),
    )


def record_of_a_copy(path: Path) -> CatalogueOpened | Literal["unreadable"] | None:
    """What a copy of the catalogue (a pre-migration copy, a backup generation) says of its last open.

    **Read-only, unlike `open_existing`**: a copy is never written by anything
    but the copy that made it, so it has no journal to roll back, and asking it
    must not change it. A file that is not a catalogue this code can read (not a
    database, a journal beside it, a record of another shape) answers
    "unreadable" rather than raising, because the caller is listing copies for a
    person and one bad file must not hide the rest.
    """
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return "unreadable"
    try:
        connection.row_factory = sqlite3.Row
        return last_opened(connection)
    except sqlite3.Error:
        return "unreadable"
    finally:
        connection.close()


class ShapeGenerationRise(str):
    """The item a generation rise adds to what an open replaces: a raise, never a drop.

    `what_an_open_replaces` answers one tuple, the migrations' drops and this
    beside them, because the pre-migration copy is taken for either. A plain
    string there read as one more thing dropped ("needs a migration that drops
    catalogue shape generation 1"), so a rise is told apart by its type and
    `backup.SnapshotFailed`'s sentence says what it is. Still a `str`, so the
    copy's log lines carry it in their `drops` list as before.
    """

    __slots__ = ()


def generation_rise(connection: sqlite3.Connection, *, generation: int) -> tuple[str, ...]:
    """What this open replaces beyond the migrations' drops: the shape generation a release of `generation` moves the file off.

    Empty unless the file records a generation, and a lower one. A file with no
    record, or a record from before generations, answers empty, so the first
    release carrying them copies nothing for them (`pending_drops` decides as
    before); every rise after it is copied first, so the release it leaves
    behind, which refuses the file from then on, has a copy it opens.
    """
    recorded = last_opened(connection)
    if recorded is None or type(recorded.schema_generation) is not int or recorded.schema_generation >= generation:
        return ()
    return (ShapeGenerationRise(f"the catalogue shape generation from {recorded.schema_generation} to {generation}"),)


def what_an_open_replaces(connection: sqlite3.Connection, *, generation: int) -> tuple[str, ...]:
    """The pre-migration copy's question: what the migrations would drop, and a shape generation the open would raise.

    `pending_drops` as before, so every file it copied is still copied and none
    it did not copy is, until a file recording a generation meets a release of
    a higher one (`generation_rise`).
    """
    return pending_drops(connection) + generation_rise(connection, generation=generation)


def begin_the_open(
    connection: sqlite3.Connection, *, release: str, generation: int, now: Callable[[], datetime] = system_now
) -> None:
    """Write this open into the file's record as begun: this release, its shape generation, the instant, not completed.

    The first step of every open, before any migration, so that a start killed
    in the middle of migrating leaves the file saying so: this release opened
    it, and did not finish. The next start rewrites the row and finishes.
    Every column is set, so a row an earlier build left keeps nothing of it.
    """
    connection.execute(
        "INSERT INTO catalogue_opened (id, release, opened_at, migrations_completed, schema_generation) "
        "VALUES (1, ?, ?, 0, ?) ON CONFLICT (id) DO UPDATE SET release = excluded.release, "
        "opened_at = excluded.opened_at, migrations_completed = 0, schema_generation = excluded.schema_generation",
        (release, now().isoformat(), generation),
    )
    connection.commit()


def complete_the_open(connection: sqlite3.Connection) -> None:
    """Mark the open `begin_the_open` recorded as completed: the last step of every open, after every migration."""
    connection.execute("UPDATE catalogue_opened SET migrations_completed = 1 WHERE id = 1")
    connection.commit()
