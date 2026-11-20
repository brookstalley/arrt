"""A catalogue every past release left, opened by today's code: what survives, what goes, and the copy taken first.

Each migration step has tests of its own, against a file shaped for it. These
hold the chain: a file a real release made (`tests/fixtures/catalogues/`, made
by `tools/old_catalogue.py` with that release's own code), opened through
`open_configured_catalogue`, the call the server makes, carrying the household
it held into today's shape however many steps that takes.

The seed is one household in every release's shape, so one set of expectations
reads every dump: the four works, the three themes and what each holds, the two
walls and what hangs on each, the hall's Player showing the main wall, how the
main wall plays, the run and the work still wanted, and the judgment and the cents
that outlive Ask's retired threads.
"""

import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from arrt.persistence import backup
from arrt.persistence.catalogue import WorkQuery
from arrt.persistence.discovery_records import Verdict
from arrt.persistence.file import open_configured_catalogue, this_release
from arrt.persistence.records import ArtworkStatus, RenditionKind
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.persistence.sqlite_discovery import SqliteDiscovery

#: What the chain takes away, each as the place it lived: present in some dump,
#: and in none once today's code has opened it.
RETIRED_COLUMNS = (
    ("walls", "token_verifier"),
    ("walls", "token_issued_at"),
    ("walls", "client_id"),
    ("walls", "output"),
    ("themes", "rotation_interval_seconds"),
    ("themes", "shuffle"),
    ("renditions", "mat_hex"),
    ("affinities", "source_turn_id"),
    ("spend_records", "conversation_turn_id"),
)
RETIRED_TABLES = ("directives", "conversations", "conversation_turns")


def _columns(connection, table):
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _tables(connection):
    return {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _retired_in(connection) -> list[str]:
    tables = _tables(connection)
    return [
        f"{table}.{column}" for table, column in RETIRED_COLUMNS if table in tables and column in _columns(connection, table)
    ] + [f"table {table}" for table in RETIRED_TABLES if table in tables]


def _rows(path):
    """Every statement of the file's dump, sorted: two files holding the same schema and rows compare equal."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return sorted(connection.iterdump())
    finally:
        connection.close()


def _open(load_release, tmp_path, tag):
    path = load_release(tag, tmp_path / "catalogue.sqlite")
    settings = SimpleNamespace(catalogue_path=path, wall_name="A name no open may use", backup_dir=tmp_path / "backups")
    return path, settings


def test_there_are_dumps_of_at_least_two_releases_and_each_is_on_disk(catalogue_dumps):
    """Vacuity first: a chain test over one dump, or none, proves nothing about the chain."""
    assert len(catalogue_dumps) >= 2
    assert next(iter(catalogue_dumps)) == "v0.1.0", "the oldest release's catalogue is the one every later migration acts on"
    assert all(path.is_file() for path in catalogue_dumps.values())
    on_disk = {path.name for path in catalogue_dumps["v0.1.0"].parent.glob("*.sql")}
    assert on_disk == {path.name for path in catalogue_dumps.values()}, "a dump is on disk that releases.json does not name"


def test_every_release_old_catalogue_names_has_a_row_and_a_shared_one_names_an_earlier_dump(catalogue_dumps):
    """`releases.json` holds every release in `RELEASES`, in order, so the chain opens the catalogue each one left.

    A release whose schema is the one before it's shares that release's dump
    (`old_catalogue.rows`); before 2026-11-19 it had no row at all, and the
    chain held six of twelve releases. The change log's releases are held to
    `RELEASES` by `tests/preferences/test_catalogue_release_dumps.py`.
    """
    import old_catalogue

    assert list(catalogue_dumps) == list(old_catalogue.RELEASES)
    order = list(catalogue_dumps)
    own = [tag for tag, path in catalogue_dumps.items() if path.name == f"{tag}.sql"]
    wrong = [
        f"{tag}: {path.name}"
        for tag, path in catalogue_dumps.items()
        if (shared := path.name.removesuffix(".sql")) not in own or order.index(shared) > order.index(tag)
    ]
    assert wrong == [], f"rows naming no earlier release's own dump: {wrong}"


def test_a_release_shares_a_dump_only_with_the_release_before_it_of_the_same_schema():
    """`rows` against schemas that return to an earlier shape: a shape seen again is dumped again, never shared back."""
    import old_catalogue

    schemas = {"v1": ["a"], "v2": ["a"], "v3": ["b"], "v4": ["a"], "v5": ["a"]}
    assert old_catalogue.rows(schemas) == {
        "v1": "v1.sql",
        "v2": "v1.sql",
        "v3": "v3.sql",
        "v4": "v4.sql",
        "v5": "v4.sql",
    }


def test_the_dumps_hold_everything_the_chain_takes_away(catalogue_dumps):
    """So each retired column and table is exercised by some dump; a seed that lost one would pass the rest unread."""
    seen: set[str] = set()
    for dump in catalogue_dumps.values():
        connection = sqlite3.connect(":memory:")
        connection.executescript(dump.read_text(encoding="utf-8"))
        seen |= set(_retired_in(connection))
        connection.close()

    assert seen == {f"{table}.{column}" for table, column in RETIRED_COLUMNS} | {f"table {table}" for table in RETIRED_TABLES}


def _the_discovery_kept(discovery):
    # The work still wanted, by today's name for that verdict.
    assert discovery.get_candidate_work("candidate-hotel").verdict is Verdict.WANTED
    assert discovery.get_candidate_work("candidate-automat").artwork_id == "work-automat"
    # The judgment and the cents outlive Ask's threads.
    assert discovery.get_affinity("affinity-hopper").artist_id == "artist-hopper"
    assert {record.id for record in discovery.list_spend_records()} == {"spend-discovery", "spend-conversation"}


def test_a_catalogue_a_past_release_left_opens_on_today_s_shape_holding_the_household(tmp_path, load_release, release):
    path, settings = _open(load_release, tmp_path, release)

    store = open_configured_catalogue(settings)
    try:
        catalogue = SqliteCatalogue(store)
        discovery = SqliteDiscovery(store)

        # The works, read through today's adapter, so every enum the old rows hold is one today reads.
        page = catalogue.list_artworks(WorkQuery(), limit=10, offset=0)
        assert {(work.title, work.status) for work in page.artworks} == {
            ("Nighthawks", ArtworkStatus.ACCEPTED),
            ("Automat", ArtworkStatus.ACCEPTED),
            ("Early Sunday Morning", ArtworkStatus.ACCEPTED),
            ("Rooms by the Sea", ArtworkStatus.ARCHIVED),
        }
        assert {work.artist_id for work in page.artworks} == {"artist-hopper"}
        assert catalogue.get_artist("artist-hopper").name == "Edward Hopper"
        assert catalogue.get_original("work-nighthawks").content_hash == "hash-nighthawks"
        assert [source.url for source in catalogue.list_sources("work-sunday")] == ["https://museum.example/work-sunday"]
        assert [mat.hex_rgb for mat in catalogue.list_mat_colors("work-nighthawks")] == ["#27285b"]
        assert [facet.value for facet in catalogue.list_facets("work-nighthawks")] == ["diner"]
        # The canvas a server once matted is forgotten; the thumbnail stays.
        kinds = {rendition.kind for rendition in catalogue.list_renditions("work-nighthawks")}
        assert RenditionKind.THUMBNAIL in kinds
        assert "tv_display" not in {str(kind) for kind in kinds}

        # The themes, what each holds in what order, and the default.
        themes = {theme.name: theme for theme in catalogue.list_themes()}
        assert set(themes) == {"All works", "Late night", "Mornings"}
        assert catalogue.get_default_theme().name == "All works"

        def held(theme):
            return sorted((member.position, member.artwork_id) for member in catalogue.list_memberships(themes[theme].id))

        assert held("Late night") == [(1, "work-nighthawks"), (2, "work-automat")]
        assert held("Mornings") == [(1, "work-sunday")]
        assert len(held("All works")) == 4

        # The walls, what hangs on each, and how the main wall plays.
        walls = {wall.id: wall for wall in catalogue.list_walls()}
        assert {wall.name for wall in walls.values()} == {"The wall", "Study"}
        hung = {assignment.wall_id: assignment.theme_id for assignment in catalogue.list_assignments()}
        assert hung == {"wall-main": themes["Late night"].id, "wall-study": themes["All works"].id}
        assert (walls["wall-main"].rotation_interval_seconds, walls["wall-main"].shuffle) == (600, True)
        # Mornings hung nowhere, so its twenty minutes had no wall to go to.
        assert (walls["wall-study"].rotation_interval_seconds, walls["wall-study"].shuffle) == (None, None)

        # The hall's Player, where the release had clients: the main wall on its first output, by a display record.
        clients = catalogue.list_clients()
        if clients:
            (client,) = clients
            assert client.token_verifier == "verifier-of-the-hall-token"
            display = catalogue.get_display(walls["wall-main"].display_id)
            assert (display.identity, display.client_id, display.output) == ("client-hall/hdmi-a-1", "client-hall", "hdmi-a-1")

        _the_discovery_kept(discovery)
    finally:
        store.close()

    connection = sqlite3.connect(path)
    try:
        assert _retired_in(connection) == []
        assert connection.execute("SELECT COUNT(*) FROM default_theme_offers").fetchone()[0] == 4
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0, "the migration mark was left on"
        assert connection.execute("SELECT release, migrations_completed FROM catalogue_opened").fetchall() == [
            (this_release(), 1)
        ]
    finally:
        connection.close()


def test_a_release_whose_file_loses_something_leaves_the_copy_the_rollback_restores_and_no_other(tmp_path, load_release, release):
    """The rollback across a migration is a restore of the copy taken first: it must be the file as that release left it."""
    path, settings = _open(load_release, tmp_path, release)
    as_left = _rows(path)
    connection = sqlite3.connect(path)
    loses = _retired_in(connection)
    connection.close()

    open_configured_catalogue(settings).close()

    copies = sorted((tmp_path / "backups").glob("pre-migration-*Z.sqlite")) if (tmp_path / "backups").is_dir() else []
    if loses:
        (copy,) = copies
        assert _rows(copy) == as_left
    else:
        assert copies == [], f"{release}'s file loses nothing, so it takes no copy"


def test_a_second_start_on_a_migrated_file_changes_nothing_but_the_record(tmp_path, load_release, release):
    """Idempotence over different files: every dump, opened twice, the second open finding nothing to do."""
    path, settings = _open(load_release, tmp_path, release)
    open_configured_catalogue(settings).close()
    first = [line for line in _rows(path) if "catalogue_opened" not in line]

    open_configured_catalogue(settings).close()

    assert [line for line in _rows(path) if "catalogue_opened" not in line] == first
    assert len(sorted((tmp_path / "backups").glob("pre-migration-*Z.sqlite"))) <= 1


def test_a_start_that_dies_mid_chain_is_finished_by_the_next_and_keeps_the_first_copy(tmp_path, load_release, monkeypatch):
    """The oldest file, killed at the last migration that drops: the next start finishes, and the copy is still v0.1.0's."""
    from arrt.persistence import file

    path, settings = _open(load_release, tmp_path, "v0.1.0")
    as_left = _rows(path)
    with monkeypatch.context() as patch:

        def dies(_connection):
            raise RuntimeError("killed in the rotation carry")

        patch.setattr(file, "carry_rotation_to_walls", dies)
        with pytest.raises(RuntimeError, match="killed in the rotation carry"):
            open_configured_catalogue(settings)

    connection = sqlite3.connect(path)
    assert connection.execute("SELECT migrations_completed FROM catalogue_opened").fetchone() == (0,)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == backup.MIGRATION_BEGUN
    connection.close()

    store = open_configured_catalogue(settings)
    try:
        walls = {wall.id: wall for wall in SqliteCatalogue(store).list_walls()}
        assert walls["wall-main"].rotation_interval_seconds == 600
    finally:
        store.close()
    (copy,) = sorted((tmp_path / "backups").glob("pre-migration-*Z.sqlite"))
    assert _rows(copy) == as_left


def test_a_server_refuses_to_start_on_a_file_a_newer_release_opened_and_says_which(tmp_path, load_release, arrt_process):
    """Acceptance 2 through the entry point: the process exits before serving, naming both releases, the file untouched."""
    path = load_release("v0.10.0", tmp_path / "catalogue.sqlite")
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE catalogue_opened (id INTEGER PRIMARY KEY CHECK (id = 1), release TEXT NOT NULL, "
        "opened_at TEXT NOT NULL, migrations_completed INTEGER NOT NULL);"
    )
    connection.execute("INSERT INTO catalogue_opened VALUES (1, '99.0.0', ?, 1)", (datetime(2027, 1, 1, tzinfo=UTC).isoformat(),))
    connection.commit()
    connection.close()
    before = path.read_bytes()

    code = arrt_process.run_to_exit()

    assert code != 0
    output = arrt_process.tail(200)
    assert "99.0.0" in output
    assert this_release() in output
    assert any(event.get("event") == "catalogue.newer_release_refused" for event in arrt_process.events())
    assert path.read_bytes() == before
