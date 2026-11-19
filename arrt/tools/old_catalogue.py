"""Make the catalogues past releases left, as SQL dumps under `tests/fixtures/catalogues/`.

`tests/system/test_migration_chain.py` opens each dump with today's code and
asserts what survived and what was dropped. **The files are made by the old
releases themselves**, never by writing today's schema backwards: for each
release tag this extracts that tag's `arrt/src` from git into a scratch
directory, runs that code's own `open_catalogue_file` on a new file in a child
interpreter whose `PYTHONPATH` puts the old package first, and seeds it there
with the synthetic rows below, inserting into each table only the columns that
release's schema has. Then it dumps the file (`Connection.iterdump`, which is
what `sqlite3 .dump` prints) and keeps the dump only when the release's schema
differs from the release before it.

**The seed is small and synthetic** (no row from any real library) and states
one household in every shape a release could hold it: the same works, themes,
walls and hangs, each where that release kept it. A theme's rotation sits on the
theme until v0.5.0 and on the wall hanging it after; a wall names its client and
output until v0.5.0 and a display record after; a verdict is
`awaiting_better_image` where that release's `Verdict` has it. So one list of
expectations in the test reads every dump. Rows only an older release could
hold are seeded wherever their table exists, so each later migration has
something to carry or drop: the wall tokens, the stored conversations and the
turn citations, the directives, the television canvases and their `mat_hex`,
and the theme rotation columns.

**Ids and instants are fixed**, the wall each old release seeds on a new file
included (renamed after its open), so running this again over the same tags
writes the same bytes, and a diff in a fixture is a change in a release.

Run from `arrt/`, in a checkout with the tags: ``uv run python tools/old_catalogue.py``.
It needs git and the tags; the tests that read its output need neither. A new
release whose schema changed gets its dump by adding its tag to `RELEASES`.
"""

import argparse
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Final

_CURATION: Final = Path(__file__).resolve().parent.parent
FIXTURES: Final = _CURATION / "tests" / "fixtures" / "catalogues"

#: Every release tag, oldest first. A dump is kept for each whose schema differs
#: from the one before it.
RELEASES: Final[tuple[str, ...]] = (
    "v0.1.0",
    "v0.2.0",
    "v0.3.0",
    "v0.4.0",
    "v0.5.0",
    "v0.6.0",
    "v0.7.0",
    "v0.8.0",
    "v0.9.0",
    "v0.9.1",
    "v0.10.0",
    "v0.11.0",
)

#: Every instant the seed writes. Before v0.1.0, so no stamp a test compares can
#: be mistaken for one today's open wrote.
SEEDED_AT: Final[str] = "2026-09-01T12:00:00+00:00"


#: The four works, by id, title and status: one archived, so a restore of the
#: archived kind is read back too.
WORKS: Final[tuple[tuple[str, str, str], ...]] = (
    ("work-nighthawks", "Nighthawks", "accepted"),
    ("work-automat", "Automat", "accepted"),
    ("work-sunday", "Early Sunday Morning", "accepted"),
    ("work-rooms", "Rooms by the Sea", "archived"),
)


class _Rows:
    """The old release's new file, and how to write into it only what its schema has."""

    def __init__(self, connection: sqlite3.Connection, *, kinds: set[str], verdicts: set[str]) -> None:
        self.connection = connection
        self.columns = {
            table: {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        #: The release's own `RenditionKind` and `Verdict` values.
        self.kinds = kinds
        self.verdicts = verdicts

    def has(self, table: str, column: str | None = None) -> bool:
        return table in self.columns and (column is None or column in self.columns[table])

    def insert(self, table: str, **values: object) -> None:
        """Insert the values whose columns this release's table has; a table it lacks takes nothing."""
        if table not in self.columns:
            return
        kept = {column: value for column, value in values.items() if column in self.columns[table]}
        names = ", ".join(f'"{column}"' for column in kept)
        marks = ", ".join("?" for _ in kept)
        self.connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', tuple(kept.values()))  # noqa: S608


def seed(path: Path) -> None:
    """Run inside the old release's interpreter: open a new catalogue with its code, and seed it.

    Imports `arrt` from whatever `PYTHONPATH` puts first, which is the point:
    this function and the ones it calls are the only code here that runs under
    the old release.
    """
    from arrt.persistence import discovery_records, records
    from arrt.persistence.file import open_catalogue_file

    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    rows = _Rows(
        connection,
        kinds={member.value for member in records.RenditionKind},
        verdicts={member.value for member in discovery_records.Verdict},
    )
    # The wall the release's own open seeded, and every row it wrote naming it
    # (v0.1.0 gives it a directive), renamed to a fixed id and instant before
    # foreign keys are enforced for the seed.
    (seeded_wall,) = connection.execute("SELECT id FROM walls").fetchall()
    connection.execute("UPDATE walls SET id = 'wall-main', created_at = ? WHERE id = ?", (SEEDED_AT, seeded_wall[0]))
    for table, names in rows.columns.items():
        if table != "walls" and "wall_id" in names:
            connection.execute(f'UPDATE "{table}" SET wall_id = ? WHERE wall_id = ?', ("wall-main", seeded_wall[0]))  # noqa: S608
    connection.commit()
    connection.execute("PRAGMA foreign_keys = ON")
    for part in (_library, _programming, _players, _discovery, _conversations, _later):
        part(rows)
    connection.commit()
    problems = connection.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(f"the seed broke a foreign key: {problems}")
    connection.close()


def _library(rows: _Rows) -> None:
    """The Library's works, their sources, the one original, renditions, mat and facet."""
    rows.insert("artists", id="artist-hopper", name="Edward Hopper", nationality="American", born=1882, died=1967)
    for work_id, title, status in WORKS:
        rows.insert(
            "artworks",
            id=work_id,
            title=title,
            artist_id="artist-hopper",
            date_created="1942",
            medium="Oil on canvas",
            status=status,
            accepted_at=SEEDED_AT,
            created_at=SEEDED_AT,
        )
        rows.insert(
            "sources",
            id=f"source-{work_id}",
            artwork_id=work_id,
            url=f"https://museum.example/{work_id}",
            provider="artic",
            source_class="institutional",
            acquisition_method="dezoomify",
            rights_status="public_domain",
            is_primary=1,
            last_fetch_status="ok",
            last_fetched_at=SEEDED_AT,
        )
    rows.insert(
        "originals",
        id="original-nighthawks",
        artwork_id="work-nighthawks",
        source_id="source-work-nighthawks",
        relative_path="raw/work-nighthawks.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-nighthawks",
        fetch_status="ok",
    )
    rendition = {
        "artwork_id": "work-nighthawks",
        "target_width": 400,
        "target_height": 300,
        "source_content_hash": "hash-nighthawks",
        "generated_at": SEEDED_AT,
    }
    rows.insert("renditions", id="rendition-thumbnail", kind="thumbnail", relative_path="thumbs/work-nighthawks.jpg", **rendition)
    if "tv_display" in rows.kinds:
        # A composed canvas, matted on the server: what `retire_television_canvases` forgets.
        rows.insert(
            "renditions",
            id="rendition-canvas",
            kind="tv_display",
            relative_path="ready/work-nighthawks.jpg",
            mat_hex="#27285b",
            **rendition,
        )
    if "presentation_master" in rows.kinds:
        rows.insert(
            "renditions",
            id="rendition-master",
            kind="presentation_master",
            relative_path="masters/work-nighthawks.jpg",
            **rendition,
        )
    rows.insert(
        "mat_colors",
        id="mat-nighthawks",
        artwork_id="work-nighthawks",
        hex_rgb="#27285b",
        method="vision_model",
        is_current=1,
        chosen_at=SEEDED_AT,
    )
    rows.insert(
        "work_facets",
        id="facet-diner",
        artwork_id="work-nighthawks",
        kind="subject",
        value="diner",
        derivation="sourced",
        created_at=SEEDED_AT,
    )


def _programming(rows: _Rows) -> None:
    """The themes, what each holds, the walls, what hangs on each, and how the main wall plays."""
    # Themes. "All works" is the default where the release has one; v0.1.0 has
    # none, and today's open makes it so.
    rows.insert("themes", id="theme-all", name="All works", created_at=SEEDED_AT, is_default=1)
    rows.insert("themes", id="theme-late", name="Late night", created_at=SEEDED_AT)
    rows.insert("themes", id="theme-mornings", name="Mornings", created_at=SEEDED_AT)
    for position, (work_id, _title, _status) in enumerate(WORKS, start=1):
        rows.insert("theme_memberships", theme_id="theme-all", artwork_id=work_id, position=position, added_at=SEEDED_AT)
        rows.insert("default_theme_offers", artwork_id=work_id, offered_at=SEEDED_AT)
    rows.insert("theme_memberships", theme_id="theme-late", artwork_id="work-nighthawks", position=1, added_at=SEEDED_AT)
    rows.insert("theme_memberships", theme_id="theme-late", artwork_id="work-automat", position=2, added_at=SEEDED_AT)
    rows.insert("theme_memberships", theme_id="theme-mornings", artwork_id="work-sunday", position=1, added_at=SEEDED_AT)

    # Walls, and what is hung on them.
    rows.insert("walls", id="wall-study", name="Study", created_at=SEEDED_AT)
    rows.insert("theme_assignments", wall_id="wall-main", theme_id="theme-late", assigned_at=SEEDED_AT)
    rows.insert("theme_assignments", wall_id="wall-study", theme_id="theme-all", assigned_at=SEEDED_AT)
    # Late night plays every ten minutes, shuffled; Mornings every twenty, in
    # order, and hangs nowhere. On the theme while the theme held it.
    if rows.has("themes", "rotation_interval_seconds"):
        rows.connection.execute("UPDATE themes SET rotation_interval_seconds = 600, shuffle = 1 WHERE id = 'theme-late'")
        rows.connection.execute("UPDATE themes SET rotation_interval_seconds = 1200, shuffle = 0 WHERE id = 'theme-mornings'")
    else:
        rows.connection.execute("UPDATE walls SET rotation_interval_seconds = 600, shuffle = 1 WHERE id = 'wall-main'")
    if rows.has("walls", "token_verifier"):
        rows.connection.execute(
            "UPDATE walls SET token_verifier = 'verifier-of-the-wall-token', token_issued_at = ? WHERE id = 'wall-main'",
            (SEEDED_AT,),
        )


def _players(rows: _Rows) -> None:
    """The hall's Player, where the release has clients, and what it shows."""
    # The Player in the hall, where the release has clients, showing the main wall.
    rows.insert(
        "clients",
        id="client-hall",
        name="The Pi in the hall",
        created_at=SEEDED_AT,
        token_verifier="verifier-of-the-hall-token",  # noqa: S106 -- a synthetic verifier, not a credential
        token_issued_at=SEEDED_AT,
    )
    if rows.has("walls", "client_id"):
        rows.connection.execute("UPDATE walls SET client_id = 'client-hall', output = 'hdmi-a-1' WHERE id = 'wall-main'")
    if rows.has("displays"):
        rows.insert(
            "displays",
            id="display-hall",
            identity="client-hall/hdmi-a-1",
            client_id="client-hall",
            output="hdmi-a-1",
            first_seen=SEEDED_AT,
        )
        rows.connection.execute("UPDATE walls SET display_id = 'display-hall' WHERE id = 'wall-main'")
        rows.insert("reported_screens", display_id="display-hall", width_px=3840, height_px=2160, last_reported_at=SEEDED_AT)
    rows.insert("label_outputs", id="label-hall", client_id="client-hall", output="epd-0", wall_id="wall-main")
    if rows.has("directives"):
        # The release's own open gave each wall one; this pins a work on it.
        rows.connection.execute("DELETE FROM directives")
        rows.insert("directives", wall_id="wall-main", sequence=7, pinned_work_id="work-nighthawks")


def _discovery(rows: _Rows) -> None:
    """Discovery: a run, a work accepted from it, and one still wanted."""
    # Discovery: a run, a work accepted from it, and one still wanted.
    rows.insert(
        "watches",
        id="watch-hopper",
        intent_text="More Hopper",
        enabled=1,
        created_at=SEEDED_AT,
        created_by="web_ui",
        updated_at=SEEDED_AT,
        updated_by="web_ui",
    )
    rows.insert(
        "discovery_runs",
        id="run-1",
        kind="discovery",
        intent_text="American realism",
        initiated_by="web_ui",
        status="completed",
        estimated_cost_usd="0.05",
        actual_cost_usd="0.04",
        approval_required=0,
        started_at=SEEDED_AT,
        completed_at=SEEDED_AT,
        watch_id="watch-hopper",
    )
    candidate = {
        "discovery_run_id": "run-1",
        "proposed_artist": "Edward Hopper",
        "rationale": "A realist of the American city.",
        "provenance": "proposed",
        "resolution_status": "resolved",
        "decided_at": SEEDED_AT,
    }
    rows.insert(
        "candidate_works",
        id="candidate-automat",
        artwork_id="work-automat",
        proposed_title="Automat",
        work_dedup_key="hopper|automat",
        verdict="accepted",
        **candidate,
    )
    rows.insert(
        "candidate_works",
        id="candidate-hotel",
        proposed_title="Hotel Room",
        work_dedup_key="hopper|hotel room",
        verdict="awaiting_better_image" if "awaiting_better_image" in rows.verdicts else "wanted",
        **candidate,
    )
    rows.insert(
        "candidate_images",
        id="image-hotel",
        candidate_work_id="candidate-hotel",
        url="https://museum.example/hotel-room.jpg",
        provider="artic",
        source_class="institutional",
        acquisition_method="direct_http",
        confidence=0.7,
        is_selected=1,
    )
    rows.insert("sightings", wikidata_qid="Q900001", url="https://museum.example/hotel-room")
    rows.insert("run_citations", discovery_run_id="run-1", url="https://encyclopedia.example/hopper", position=0)


def _conversations(rows: _Rows) -> None:
    """Ask's stored threads, while they were stored, and the two rows that cited a turn."""
    # Ask's stored threads, while they were stored, and the two rows that cited a turn.
    rows.insert("conversations", id="conversation-1", started_at=SEEDED_AT, last_turn_at=SEEDED_AT, summary="Hopper")
    rows.insert(
        "conversation_turns",
        id="turn-1",
        conversation_id="conversation-1",
        ordinal=0,
        role="user",
        text="More like Nighthawks.",
        created_at=SEEDED_AT,
    )
    turn = "turn-1" if rows.has("conversation_turns") else None
    rows.insert(
        "affinities",
        id="affinity-hopper",
        kind="artist",
        value="Edward Hopper",
        sentiment="loves",
        open_to_more=1,
        derivation="stated",
        source_turn_id=turn,
        artist_id="artist-hopper",
        created_at=SEEDED_AT,
        updated_at=SEEDED_AT,
    )
    rows.insert(
        "spend_records",
        id="spend-discovery",
        discovery_run_id="run-1",
        category="discovery_tokens",
        cost_usd="0.04",
        occurred_at=SEEDED_AT,
    )
    rows.insert(
        "spend_records",
        id="spend-conversation",
        conversation_turn_id=turn,
        category="conversation_tokens",
        cost_usd="0.01",
        occurred_at=SEEDED_AT,
    )


def _later(rows: _Rows) -> None:
    """What the later releases record of the wall's life."""
    # What the later releases record of the wall's life.
    rows.insert(
        "history_events", id="event-1", kind="wall.hung", occurred_at=SEEDED_AT, wall_id="wall-main", theme_id="theme-late"
    )
    rows.insert("showings", wall_id="wall-main", started_at=SEEDED_AT, work_id="work-nighthawks", last_seen_at=SEEDED_AT)
    rows.insert("work_exclusions", artwork_id="work-sunday", excluded_at=SEEDED_AT)
    rows.insert("acquisition_queue", artwork_id="work-sunday", failures=1, detail="the museum did not answer")
    rows.insert("scenes", id="scene-1", status="ended", lifetime="hold", created_at=SEEDED_AT, ended_at=SEEDED_AT)
    rows.insert("scene_pins", scene_id="scene-1", wall_id="wall-main", work_id="work-nighthawks")
    rows.insert("settings", key="label_units", value="metric", updated_at=SEEDED_AT, updated_by="web_ui")


def _schema(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return sorted(sql for (sql,) in connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
    finally:
        connection.close()


def _dump(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return "\n".join(connection.iterdump()) + "\n"
    finally:
        connection.close()


def _extract(repository: Path, tag: str, into: Path) -> Path:
    """The tag's `arrt/src`, from git, into `into`; returns the directory to put on `PYTHONPATH`."""
    archive = subprocess.run(  # noqa: S603 -- git, with a tag from RELEASES
        ["git", "archive", tag, "arrt/src"], cwd=repository, capture_output=True, check=True  # noqa: S607
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(into, filter="data")
    return into / "arrt" / "src"


def make(tag: str, repository: Path, scratch: Path) -> tuple[str, list[str]]:
    """The dump of the catalogue `tag` makes over the seed, and its schema."""
    source = _extract(repository, tag, scratch / tag)
    path = scratch / f"{tag}.sqlite"
    environment = {**os.environ, "PYTHONPATH": str(source)}
    child = (
        "import sys, pathlib, arrt\n"
        "assert pathlib.Path(arrt.__file__).is_relative_to(sys.argv[2]), f'arrt came from {arrt.__file__}'\n"
        "sys.path.insert(0, sys.argv[3])\n"
        "import old_catalogue\n"
        "old_catalogue.seed(pathlib.Path(sys.argv[1]))\n"
    )
    subprocess.run(  # noqa: S603 -- this interpreter, running the fixed script above
        [sys.executable, "-c", child, str(path), str(source), str(Path(__file__).parent)], env=environment, check=True
    )
    return _dump(path), _schema(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=FIXTURES)
    parser.add_argument("--repository", type=Path, default=_CURATION.parent)
    arguments = parser.parse_args()
    arguments.out.mkdir(parents=True, exist_ok=True)
    kept: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="old-catalogue-") as scratch:
        previous: list[str] | None = None
        for tag in RELEASES:
            dump, schema = make(tag, arguments.repository, Path(scratch))
            if schema == previous:
                print(f"{tag}: schema as before, no dump")
                continue
            previous = schema
            header = f"-- The catalogue Arrt {tag} made over the synthetic seed in tools/old_catalogue.py, which wrote this.\n"
            (arguments.out / f"{tag}.sql").write_text(header + dump, encoding="utf-8")
            kept[tag] = f"{tag}.sql"
            print(f"{tag}: wrote {tag}.sql")
    (arguments.out / "releases.json").write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
