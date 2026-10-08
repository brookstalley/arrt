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
"""

import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Final

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

#: `ALTER TABLE ... DROP COLUMN` arrived in SQLite 3.35 (2021). Named rather than
#: assumed: without it the drop below fails with a syntax error naming neither
#: the version nor the remedy, on the one machine old enough to hit it.
_DROP_COLUMN_SINCE: Final[tuple[int, int, int]] = (3, 35, 0)


def establish_the_wall(connection: sqlite3.Connection, *, wall_name: str) -> None:
    """Move a single-wall catalogue onto `Wall`, `ThemeAssignment` and per-wall directives.

    Before 2026-08-12 a theme was hung by a boolean on the theme itself — one
    that could only ever mean "active on the one television" — and the display
    plane's standing directive was a single row for the whole installation. This
    carries both onto a named wall: whichever theme was active is hung on it, and
    the singleton directive's counter and pin become that wall's, so no
    deployment loses its picture and no advance is fired by the migration itself.

    **It also seeds the wall on a fresh file**, which is not a separate concern
    wearing this one's clothes: a catalogue with no wall has nowhere to hang
    anything, and every operation that changes a wall names one. The old schema
    seeded its singleton directive row the same way, in the DDL; a wall cannot be
    seeded there because its name is a deployment value and its id is a UUID.

    **The name is written once.** A wall that already exists keeps the name it
    has — it is the curator's word by then, and configuration must not overwrite
    it on the next restart. Nothing here renames a wall.
    """
    if _walls(connection):
        _drop_what_the_wall_replaced(connection)
        return

    hung_theme_id = _theme_that_was_active(connection)
    sequence, pinned_work_id = _directive_that_was_the_only_one(connection)
    now = datetime.now(UTC).isoformat()
    wall_id = str(uuid.uuid4())

    connection.execute("INSERT INTO walls (id, name, created_at) VALUES (?, ?, ?)", (wall_id, wall_name, now))
    connection.execute(
        "INSERT INTO directives (wall_id, sequence, pinned_work_id) VALUES (?, ?, ?)",
        (wall_id, sequence, pinned_work_id),
    )
    if hung_theme_id is not None:
        connection.execute(
            "INSERT INTO theme_assignments (wall_id, theme_id, assigned_at) VALUES (?, ?, ?)",
            (wall_id, hung_theme_id, now),
        )
    # Committed before the drops below, so that an interrupted open leaves a file
    # holding the carried rows and the columns they came from — which the next
    # open reads as "already migrated, still to tidy" rather than as a fresh file.
    connection.commit()

    log.info(
        "Established wall %r (%s) carrying directive sequence %d; %s.",
        wall_name,
        wall_id,
        sequence,
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


def _directive_that_was_the_only_one(connection: sqlite3.Connection) -> tuple[int, str | None]:
    """The singleton directive's counter and pin, or a fresh wall's zero.

    The counter is carried rather than restarted because the display plane acts
    once each time it observes the number go up: a wall whose counter dropped to
    zero at migration would see the next ordinary advance as a step it had
    already taken, or — worse, on a file whose counter was zero — see nothing at
    all where an advance was issued.
    """
    if not _has_table(connection, "directive"):
        return 0, None
    row = connection.execute("SELECT sequence, pinned_work_id FROM directive WHERE id = 1").fetchone()
    if row is None:
        return 0, None
    return int(row["sequence"]), row["pinned_work_id"]


def _drop_what_the_wall_replaced(connection: sqlite3.Connection) -> None:
    """Take away the single-wall shape, once nothing needs to read it.

    Separate from the carry above so that both halves are guarded by the file
    rather than by each other: this runs on every open and does nothing to a file
    that has already had it.
    """
    if _has_column(connection, "themes", "is_active"):
        _require_drop_column()
        # The index has to go first — SQLite refuses to drop a column an index
        # names, and this one is over exactly that column.
        connection.execute("DROP INDEX IF EXISTS themes_one_active")
        connection.execute("ALTER TABLE themes DROP COLUMN is_active")
        log.info("Dropped themes.is_active and its partial index; hanging is now a row on theme_assignments.")
    if _has_table(connection, "directive"):
        connection.execute("DROP TABLE directive")
        log.info("Dropped the singleton directive table; each wall now carries its own.")
    connection.commit()


def _require_drop_column(*, predates: str = "per-wall hanging") -> None:
    # Takes no connection: the capability is the interpreter's, not this file's,
    # and a connection parameter here would suggest the answer could differ per
    # file. `predates` names the change, so the refusal says which migration needs it.
    version = tuple(int(part) for part in sqlite3.sqlite_version.split("."))
    if version < _DROP_COLUMN_SINCE:
        raise RuntimeError(
            f"This catalogue file predates {predates} and migrating it needs SQLite "
            f"{'.'.join(str(part) for part in _DROP_COLUMN_SINCE)} or newer to drop a column; "
            f"this interpreter is linked against {sqlite3.sqlite_version}."
        )


#: The theme the owner's catalogue already holds every work in, and so the one
#: made the default when the default arrived. Matched ignoring case.
DEFAULT_THEME_NAME: Final[str] = "All works"


def mark_the_default_theme(connection: sqlite3.Connection) -> None:
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
        (datetime.now(UTC).isoformat(),),
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
    retired = [column for column in _RETIRED_WALL_TOKEN_COLUMNS if _has_column(connection, "walls", column)]
    if not retired:
        return
    _require_drop_column(predates="client tokens")
    for column in retired:
        connection.execute(f'ALTER TABLE walls DROP COLUMN "{column}"')
    connection.commit()
    log.info("Dropped walls.%s: Players are admitted by their client's token now.", " and walls.".join(retired))


#: The columns a wall named its screen by before displays were records.
_WALL_PLACEMENT_COLUMNS: Final[tuple[str, ...]] = ("client_id", "output")


def walls_name_displays(connection: sqlite3.Connection) -> None:
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
    present = [column for column in _WALL_PLACEMENT_COLUMNS if _has_column(connection, "walls", column)]
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
    now = datetime.now(UTC).isoformat()
    for wall in carried:
        identity = f"{wall['client_id']}/{wall['output']}"
        found = connection.execute("SELECT id FROM displays WHERE identity = ?", (identity,)).fetchone()
        if found is None:
            display_id = str(uuid.uuid4())
            # Kind is left unknown: the file never held it, and the client's next
            # report states it. Guessed from the output's name, it would be a fact
            # this server made up.
            connection.execute(
                "INSERT INTO displays (id, identity, client_id, output, kind, first_seen) VALUES (?, ?, ?, ?, NULL, ?)",
                (display_id, identity, wall["client_id"], wall["output"], now),
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
