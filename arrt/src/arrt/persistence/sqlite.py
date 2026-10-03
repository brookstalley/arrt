"""A `CatalogueStore`, and Programming's `ProgrammingStore`, over a SQLite file.

SQLite was chosen because it has no dependency to resolve, no server to run, and
a file that can be copied to a backup and back again — which is how this
catalogue's restore path is meant to work.

This module is one domain adapter over that file: it owns the catalogue's
tables, the mapping between its records and rows, and the ordering and paging
decisions that make a listing stable. Everything about connections, statements,
locking and constraint translation lives in `durable.py`, and what every adapter
does identically lives in `adapter.py` — so what remains here reads as the
catalogue rather than as SQL plumbing. `sqlite_discovery.py` is the other
adapter, over the same open file.

Ordering is decided here rather than below because it is a product judgement, not
a storage one: title is what a curator scans by, and id breaks ties so that the
same page request never comes back in a different order.

**The unique indexes below do not replace the service layer's rules.** Every
catalogue rule is applied in the service layer, where a refusal can be phrased for
whoever asked; a partial index here catches the case where some path forgets to,
and its message names only the table. Enforcement in two places would be a defect
if they could disagree — they cannot, because the index is strictly the weaker
statement of the same rule.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from arrt.persistence.adapter import BY_ID, TableAdapter, from_iso, require_datetime, to_iso
from arrt.persistence.catalogue import TopicTally, WorkOrder, WorkQuery, WorkToAcquire
from arrt.persistence.durable import OrderBy, SqliteDurableStore
from arrt.persistence.errors import StorageError
from arrt.persistence.folding import search_fold
from arrt.persistence.records import (
    AcquisitionMethod,
    Artist,
    Artwork,
    ArtworkPage,
    ArtworkStatus,
    Client,
    Directive,
    FacetDerivation,
    FetchStatus,
    IdentitySetBy,
    MatColor,
    MatMethod,
    Original,
    QueuedAcquisition,
    Rendition,
    RenditionKind,
    RightsStatus,
    Source,
    SourceClass,
    Theme,
    ThemeAssignment,
    ThemeMembership,
    VocabularyKind,
    Wall,
    WorkFacet,
)

log = logging.getLogger(__name__)

CATALOGUE_SCHEMA = """
-- `family_name` and `given_name` are nullable because a record that is not a
-- person — a culture, a workshop, an anonymous master — has neither, and
-- because a file written before they existed has neither either. Both cases
-- read the same way downstream and are meant to: the label falls back to `name`
-- rather than splitting one by a rule that is wrong for "van Gogh".
--
-- `display_nationality` is the same shape of decision one field over: what a
-- museum printed is prose rather than a demonym — "Born Moscow (formerly Russian
-- Empire, now Russia)", "American, born Russia (Latvia)" — and a wall label has
-- no room for it. Null means the label uses `nationality` as recorded, so a
-- record nobody has shortened reads exactly as it did before the column existed.
CREATE TABLE IF NOT EXISTS artists (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    nationality    TEXT,
    born           INTEGER,
    died           INTEGER,
    lifespan_text  TEXT,
    biography      TEXT,
    family_name    TEXT,
    given_name     TEXT,
    display_nationality TEXT,
    wikidata_qid   TEXT,
    wikidata_qid_set_by TEXT
);

CREATE TABLE IF NOT EXISTS artworks (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    artist_id     TEXT REFERENCES artists(id),
    date_created  TEXT,
    medium        TEXT,
    dimensions    TEXT,
    description   TEXT,
    rights        TEXT,
    status        TEXT NOT NULL,
    accepted_at   TEXT,
    created_at    TEXT NOT NULL,
    commentary    TEXT,
    wikidata_qid  TEXT,
    wikidata_qid_set_by TEXT
);

CREATE INDEX IF NOT EXISTS artworks_by_status ON artworks(status);

-- What a work IS, in the same typed vocabulary the curator's taste is expressed
-- in. A new table rather than columns on `artworks`, because a work has many
-- facets and each carries its own derivation and provenance note.
--
-- This table needed no written migration: `CREATE TABLE IF NOT EXISTS` and
-- `CREATE UNIQUE INDEX IF NOT EXISTS` both reach a catalogue file written before
-- they existed, which is the case `durable.py`'s widening step and
-- `migrations.py` between them exist to cover. Adding a *table* is neither.
-- `value` is COLLATE NOCASE, and the column is where it has to be said. Every
-- read of a facet value — the uniqueness below, the filter's match, the
-- `GROUP BY` the counts are taken over, the vocabulary's ordering — has to agree
-- about whether "Baroque" and "baroque" are one value. Declared on the column,
-- they cannot disagree; declared per statement, the first one written without it
-- splits a rail in two and halves both counts, silently and only on real data.
--
-- Set before the first row existed, because after it this is a migration and a
-- de-duplication rather than one word in the DDL. The writers disagree about
-- case by nature: the topic sweep writes Wikidata's labels ("painting",
-- "Impressionism"), and inference from museum text and a model's answer, still
-- to come, is the documented source of inconsistent casing.
CREATE TABLE IF NOT EXISTS work_facets (
    id           TEXT PRIMARY KEY,
    artwork_id   TEXT NOT NULL REFERENCES artworks(id),
    kind         TEXT NOT NULL,
    value        TEXT NOT NULL COLLATE NOCASE,
    derivation   TEXT NOT NULL,
    source_note  TEXT,
    created_at   TEXT NOT NULL,
    value_qid    TEXT
);

-- A work is Baroque once. Load-bearing rather than tidy: a facet's count is a
-- plain `COUNT(*)` over this table, so a second identical row on one work would
-- inflate the number a curator reads off the collection — and would do it
-- invisibly, since the grid it labels would still show that work once.
CREATE UNIQUE INDEX IF NOT EXISTS work_facets_once_per_work ON work_facets(artwork_id, kind, value);

-- Serves the two reads that are asked once per request per kind: "which works
-- carry this value" (the filter's subquery) and "every value of this kind" (the
-- counts). It enforces nothing — the uniqueness above is the constraint.
CREATE INDEX IF NOT EXISTS work_facets_by_value ON work_facets(kind, value);

CREATE INDEX IF NOT EXISTS work_facets_by_artwork ON work_facets(artwork_id);

-- `value_qid` is the Wikidata item a value names, where one does: the Topic page
-- the value opens. Nullable, because an inferred facet may name no item, and
-- because the widening step can only add a column that allows NULL to a file
-- written before it existed. Indexed for the Topic page's one read, "which works
-- carry this item"; it enforces nothing.
CREATE INDEX IF NOT EXISTS work_facets_by_item ON work_facets(value_qid);

-- `rotation_interval_seconds` and `shuffle` are nullable because null means
-- "inherit the global default" rather than "unset": a theme that has never
-- expressed a pace is a normal theme, not an incomplete one.
--
-- A theme is global: nothing here says where it is hanging. `is_active` and its
-- `themes_one_active` partial index were dropped on 2026-08-12, when hanging
-- became an act against a named wall; `migrations.py` carries the file that
-- still has them.
CREATE TABLE IF NOT EXISTS themes (
    id                        TEXT PRIMARY KEY,
    name                      TEXT NOT NULL UNIQUE,
    description               TEXT,
    created_at                TEXT NOT NULL,
    rotation_interval_seconds INTEGER,
    shuffle                   INTEGER,
    is_default                INTEGER NOT NULL DEFAULT 0
);

-- New works join the default theme, and there is at most one. "At most", not
-- "exactly": a catalogue with no theme marked is ordinary, and acceptance then
-- joins nothing.
CREATE UNIQUE INDEX IF NOT EXISTS themes_one_default ON themes(is_default) WHERE is_default = 1;

-- An installed Player, by name and the verifier of its one token. Nothing about
-- the device: what outputs it has is what it reports in its heartbeat file.
CREATE TABLE IF NOT EXISTS clients (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL,
    token_verifier   TEXT,
    token_issued_at  TEXT
);

-- A place where art hangs, and which client shows it on which of its outputs,
-- by name. The forbidden columns are listed on the `Wall` record; the rule is
-- that this table must survive its television being replaced.
--
-- `client_id` and `output` arrived 2026-10-02 and reach an older file through
-- the widening step, which carries the reference. The wall token columns that
-- preceded them are dropped by `migrations.retire_wall_tokens`.
CREATE TABLE IF NOT EXISTS walls (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL,
    client_id        TEXT REFERENCES clients(id),
    output           TEXT
);

-- One wall per output of a client, since one screen shows one picture. The
-- service refuses a second by name first; this is the weaker statement of the
-- same rule, for a path that forgets to. It also answers "which walls does this
-- client drive", asked on every poll a client makes.
CREATE UNIQUE INDEX IF NOT EXISTS walls_one_per_output ON walls(client_id, output) WHERE client_id IS NOT NULL;

-- What is hanging on one wall. `wall_id` alone is the key, so "at most one theme
-- per wall" is the key rather than a rule anything has to check: a second theme
-- on a wall is a row that cannot be inserted. A wall with no row hangs nothing,
-- which is an ordinary state.
CREATE TABLE IF NOT EXISTS theme_assignments (
    wall_id      TEXT PRIMARY KEY REFERENCES walls(id),
    theme_id     TEXT NOT NULL REFERENCES themes(id),
    assigned_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS theme_assignments_by_theme ON theme_assignments(theme_id);

CREATE TABLE IF NOT EXISTS sources (
    id                   TEXT PRIMARY KEY,
    artwork_id           TEXT NOT NULL REFERENCES artworks(id),
    url                  TEXT NOT NULL,
    provider             TEXT NOT NULL,
    source_class         TEXT NOT NULL,
    acquisition_method   TEXT NOT NULL,
    rights_status        TEXT NOT NULL,
    is_primary           INTEGER NOT NULL,
    confidence           REAL,
    selection_rationale  TEXT,
    last_fetch_status    TEXT,
    last_fetched_at      TEXT
);

CREATE INDEX IF NOT EXISTS sources_by_artwork ON sources(artwork_id);

-- Which source produced the held original is a single fact about the work.
CREATE UNIQUE INDEX IF NOT EXISTS sources_one_primary ON sources(artwork_id) WHERE is_primary = 1;

CREATE TABLE IF NOT EXISTS originals (
    id             TEXT PRIMARY KEY,
    artwork_id     TEXT NOT NULL UNIQUE REFERENCES artworks(id),
    source_id      TEXT NOT NULL REFERENCES sources(id),
    relative_path  TEXT NOT NULL,
    width          INTEGER NOT NULL,
    height         INTEGER NOT NULL,
    -- A zero-byte file is the 2024 pipeline's known download failure. The
    -- catalogue must not be able to record one as a held original.
    byte_size      INTEGER NOT NULL CHECK (byte_size > 0),
    content_hash   TEXT NOT NULL,
    -- How the fetch that produced these bytes ended. Nullable, because the column
    -- was added to a table that already had rows on disk and the widening step
    -- can only add columns that allow NULL — a null here means "written before
    -- this was recorded", which readers treat as complete rather than as partial.
    fetch_status   TEXT
);

CREATE TABLE IF NOT EXISTS renditions (
    id                   TEXT PRIMARY KEY,
    artwork_id           TEXT NOT NULL REFERENCES artworks(id),
    kind                 TEXT NOT NULL,
    target_width         INTEGER NOT NULL,
    target_height        INTEGER NOT NULL,
    relative_path        TEXT NOT NULL,
    source_content_hash  TEXT NOT NULL,
    generated_at         TEXT NOT NULL,
    content_sha256       TEXT,
    byte_size            INTEGER
);

-- Media is fetched by content hash, so the hash is how a render is found.
CREATE INDEX IF NOT EXISTS renditions_by_content
    ON renditions(content_sha256);

-- One rendition per work per kind per geometry: a second row for the same
-- target is two answers to "is this current", and only one of them is right.
CREATE UNIQUE INDEX IF NOT EXISTS renditions_by_geometry
    ON renditions(artwork_id, kind, target_width, target_height);

CREATE TABLE IF NOT EXISTS mat_colors (
    id          TEXT PRIMARY KEY,
    artwork_id  TEXT NOT NULL REFERENCES artworks(id),
    hex_rgb     TEXT NOT NULL,
    method      TEXT NOT NULL,
    is_current  INTEGER NOT NULL,
    lab_l       REAL,
    lab_a       REAL,
    lab_b       REAL,
    reason      TEXT,
    model_id    TEXT,
    chosen_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS mat_colors_by_artwork ON mat_colors(artwork_id);

-- Superseded choices stay; exactly one of them is the one in force.
CREATE UNIQUE INDEX IF NOT EXISTS mat_colors_one_current ON mat_colors(artwork_id) WHERE is_current = 1;

CREATE TABLE IF NOT EXISTS theme_memberships (
    theme_id    TEXT NOT NULL REFERENCES themes(id),
    artwork_id  TEXT NOT NULL REFERENCES artworks(id),
    position    INTEGER,
    added_at    TEXT NOT NULL,
    PRIMARY KEY (theme_id, artwork_id)
);

CREATE INDEX IF NOT EXISTS theme_memberships_by_artwork ON theme_memberships(artwork_id);

-- Every work that has been offered the theme it was accepted into (the default,
-- or the theme its Get named), joined or not, so that a work is offered once:
-- neither a restore, which the Library announces as an acceptance, nor startup
-- reconciliation puts back a work the curator took out. Named for the default
-- because that was the only destination when the table was made, and renaming a
-- table is a written migration that buys nothing.
-- `artwork_id` is deliberately not a foreign key: it is Programming's reference
-- to a Library work, which the seam keeps opaque.
CREATE TABLE IF NOT EXISTS default_theme_offers (
    artwork_id  TEXT PRIMARY KEY,
    offered_at  TEXT NOT NULL
);

-- One row per wall, seeded when the wall is created so no caller ever has to
-- make one. The standing directive is a property of the *wall* rather than of
-- any theme, because the sequence has to survive every manifest rebuild and
-- every theme switch to stay monotonic — and a singleton, which is what this
-- was until 2026-08-12, cannot say which display an advance was meant for.
CREATE TABLE IF NOT EXISTS directives (
    wall_id         TEXT PRIMARY KEY REFERENCES walls(id),
    sequence        INTEGER NOT NULL,
    pinned_work_id  TEXT REFERENCES artworks(id)
);

CREATE INDEX IF NOT EXISTS directives_by_pin ON directives(pinned_work_id);

-- The acquisition queue's memory of each work it has started on and not
-- finished: how many attempts failed in a row, when the next may be made, why the
-- last one failed, and a source someone named for the next. Deleted once the work
-- is fetched and prepared, so the table holds only the works still owing
-- something. "Gave up" is `failures` reaching the queue's limit, read rather than
-- stored, and what is in flight or why the queue is paused is not stored at all.
-- A new table, so `CREATE TABLE IF NOT EXISTS` reaches a file written before it
-- and no migration is needed.
CREATE TABLE IF NOT EXISTS acquisition_queue (
    artwork_id   TEXT PRIMARY KEY REFERENCES artworks(id),
    failures     INTEGER NOT NULL DEFAULT 0 CHECK (failures >= 0),
    next_try_at  TEXT,
    detail       TEXT,
    source_id    TEXT REFERENCES sources(id)
);
"""

#: The queue's table is keyed by the work alone: one row per work it owes something.
_BY_ARTWORK: Final[tuple[str, ...]] = ("artwork_id",)

#: The join's own key. A work appears at most once in a theme.
_MEMBERSHIP_KEY: Final[tuple[str, ...]] = ("theme_id", "artwork_id")

#: Both tables that hang off a wall are keyed by it alone, which is what makes
#: "one theme per wall" and "one directive per wall" keys rather than claims.
_BY_WALL: Final[tuple[str, ...]] = ("wall_id",)

#: What a curator scans by, then a tie-break that makes paging repeatable.
_BY_TITLE: Final[tuple[OrderBy, ...]] = (OrderBy("title", ignore_case=True), OrderBy("id"))
_BY_NAME: Final[tuple[OrderBy, ...]] = (OrderBy("name", ignore_case=True), OrderBy("id"))

#: The source that produced the held original leads; the rest are alternates.
_BY_PRIMARY: Final[tuple[OrderBy, ...]] = (
    OrderBy("is_primary", descending=True),
    OrderBy("url", ignore_case=True),
    OrderBy("id"),
)

#: Grouped by what the output is for, then by how big it is.
_BY_GEOMETRY: Final[tuple[OrderBy, ...]] = (
    OrderBy("kind"),
    OrderBy("target_width"),
    OrderBy("target_height"),
    OrderBy("id"),
)

#: Newest first, because a mat colour list is a history and the current choice
#: is the one at the top of it.
_BY_RECENCY: Final[tuple[OrderBy, ...]] = (OrderBy("chosen_at", descending=True), OrderBy("id"))

#: The only order a set of rows keyed by a wall has. Stated rather than left to
#: the file, because a listing with no ORDER BY is a different order on a
#: different day and every caller here is comparing sets.
_BY_WALL_ID: Final[tuple[OrderBy, ...]] = (OrderBy("wall_id"),)

#: Grouped by kind so a work's facets read as a vocabulary rather than a list.
_BY_KIND_VALUE: Final[tuple[OrderBy, ...]] = (OrderBy("kind"), OrderBy("value", ignore_case=True), OrderBy("id"))

#: Curated order, with the entries nobody placed after the ones somebody did.
_BY_POSITION: Final[tuple[OrderBy, ...]] = (
    OrderBy("position", nulls_last=True),
    OrderBy("added_at"),
    OrderBy("artwork_id"),
)


#: The artist table, joined only when something is searched across its name. The
#: join is `LEFT` because an unattributed work is ordinary and must still be
#: listed, and it cannot multiply rows — `artists.id` is a primary key — which is
#: what lets the count beside a page be a plain `COUNT(*)`.
_JOIN_ARTISTS: Final[str] = " LEFT JOIN artists ar ON ar.id = a.artist_id"

#: What a curator scans by, then a tie-break that makes paging repeatable — the
#: same decision `_BY_TITLE` carries, spelled for the joined statement.
_WORKS_ORDER: Final[str] = 'a."title" COLLATE NOCASE, a."id"'

#: The artist's name, read by a correlated lookup rather than through
#: `_JOIN_ARTISTS`, which the statement carries only when a search needs it.
_ARTIST_NAME: Final[str] = '(SELECT ar2."name" FROM artists ar2 WHERE ar2."id" = a."artist_id")'

#: Every order the toolbar's Sort offers, each ending in a tie-break so a page
#: boundary falls in the same place on every request.
_WORKS_ORDERS: Final[dict[WorkOrder, str]] = {
    WorkOrder.TITLE: _WORKS_ORDER,
    # Unattributed last: `IS NULL` sorts false before true.
    WorkOrder.ARTIST: f"{_ARTIST_NAME} IS NULL, {_ARTIST_NAME} COLLATE NOCASE, {_WORKS_ORDER}",
    # `rowid` breaks a tie between works added within one clock tick, in the
    # order they were inserted; the id, a random uuid, would not.
    WorkOrder.NEWEST: 'a."created_at" DESC, a.rowid DESC',
}

#: What free text is searched across, and it is the work's own words plus its
#: artist's name. **Facet values are deliberately not among them**: a facet is
#: chosen from a control that shows its count, and folding it into the text box
#: would give the same word two meanings — one exact and counted, one fuzzy and
#: not — with nothing on screen to say which had been used.
_SEARCHED: Final[tuple[str, ...]] = (
    "a.title",
    "a.description",
    "a.commentary",
    "a.medium",
    "a.date_created",
    "ar.name",
)

#: What SQL calls `search_fold` by, on both sides of every searched `LIKE`.
_FOLD: Final[str] = "search_fold"

#: The searched columns as one string, so the fold is one call and one
#: remembered entry per work rather than six (see `_FOLDS_REMEMBERED` in `folding.py`). They are
#: joined by the unit separator, which `str.split` treats as whitespace, so no
#: term can contain it and no match can run from one column into the next.
_SEARCHED_TEXT: Final[str] = " || char(31) || ".join(f"coalesce({column}, '')" for column in _SEARCHED)

#: `LIKE`'s own wildcards, which have to survive a curator typing one. Escaped
#: with a backslash declared per-clause as `ESCAPE '\'`; SQLite has no default
#: escape character, so without the clause a searched `%` would match everything.
_LIKE_SPECIAL: Final[str] = "\\%_"


def _like_pattern(term: str) -> str:
    """One search term as a contains-match, with its wildcards defused."""
    escaped = "".join(f"\\{character}" if character in _LIKE_SPECIAL else character for character in term)
    return f"%{escaped}%"


def _known_kind(value: str) -> VocabularyKind | None:
    try:
        return VocabularyKind(value)
    except ValueError:
        log.warning("Ignoring facet of unknown kind %r; this build knows %s.", value, ", ".join(VocabularyKind))
        return None


@dataclass(frozen=True, slots=True)
class _Restriction:
    """A `WorkQuery` rendered for SQL: which works, and how to ask for them."""

    #: The WHERE body over `artworks a`. `"1"` when nothing narrows.
    where: str
    values: tuple[Any, ...]
    #: True when the clause reads `ar.name`, so the artist table has to be joined.
    #: Tracked rather than always joining: on this catalogue the unconditional
    #: join cost measurably more than the search clause it exists for.
    reads_the_artist: bool

    @property
    def narrows(self) -> bool:
        """False when this selects the whole catalogue, and every caller checks it.

        A restriction that narrows nothing still renders as valid SQL — but a
        `WHERE artwork_id IN (SELECT id FROM artworks)` over a table of facets
        makes SQLite build an ephemeral index of every work and probe it once per
        facet row, to arrive at "all of them". Measured on the 4,000-work corpus,
        dropping that subquery took a facet count from 7.0 ms to 0.5 ms — and the
        unnarrowed case is the collection's *first* screen, so it is the one a
        curator meets before they have asked for anything.
        """
        return self.where != "1"

    def over_works(self, *, column: str) -> str:
        """The tail restricting a facet-table read to the works this selects.

        Empty when nothing narrows — see `narrows`.
        """
        if not self.narrows:
            return ""
        return f" AND {column} IN (SELECT a.id {self.source} WHERE {self.where})"

    @property
    def source(self) -> str:
        return "FROM artworks a" + (_JOIN_ARTISTS if self.reads_the_artist else "")


def _matching(query: WorkQuery) -> _Restriction:
    """Render `query` as a WHERE clause over `artworks a`, with its values to bind.

    One renderer for the page, its total, the facet counts and the vocabulary —
    which is the point. Four statements describing the same set in four
    hand-written clauses is four chances for the numbers beside a grid to be
    right about a different set from the one on screen.

    Every value is bound; nothing a caller typed is interpolated. `"1"` is the
    clause for an unnarrowed query, so the caller can always write `WHERE {where}`
    rather than deciding whether to write `WHERE` at all.
    """
    clauses: list[str] = []
    values: list[Any] = []

    if query.status is not None:
        clauses.append('a."status" = ?')
        values.append(str(query.status))

    if query.artist_id is not None:
        clauses.append('a."artist_id" = ?')
        values.append(query.artist_id)

    # ANDed across terms, ORed across columns: "blue harbour" means both words
    # appear somewhere about the work, which is what a person typing two words
    # means. ORing the terms instead would make every extra word widen the
    # result, so a search would get less useful the more precisely it was asked.
    #
    # Folded on both sides by `search_fold`, and the term before its wildcards
    # are escaped, so the escaping is the last thing done to it.
    for term in query.terms:
        clauses.append(f"{_FOLD}({_SEARCHED_TEXT}) LIKE ? ESCAPE '\\'")
        values.append(_like_pattern(search_fold(term)))

    # ORed within a kind, ANDed across kinds — see `WorkQuery.facets`. A kind
    # present with nothing chosen narrows nothing, rather than selecting nothing:
    # an empty list is what a control sends when the curator has cleared it.
    for kind, chosen in query.facets.items():
        if not chosen:
            continue
        placeholders = ", ".join("?" for _ in chosen)
        clauses.append(f'a."id" IN (SELECT artwork_id FROM work_facets WHERE kind = ? AND value IN ({placeholders}))')
        values.append(str(kind))
        values.extend(chosen)

    return _Restriction(
        where=" AND ".join(clauses) if clauses else "1",
        values=tuple(values),
        reads_the_artist=bool(query.terms),
    )


class SqliteCatalogue(TableAdapter):
    """The catalogue's own tables, mapped to its records."""

    def __init__(self, store: SqliteDurableStore) -> None:
        super().__init__(store)
        # Defined by the adapter whose search calls it rather than where the file
        # is opened, so every way of reaching this adapter can search.
        store.define_function(_FOLD, search_fold)

    # -- artists --------------------------------------------------------------

    def add_artist(self, artist: Artist) -> None:
        self._add("artists", _artist_row(artist), subject=f"artist {artist.id!r}")

    def get_artist(self, artist_id: str) -> Artist | None:
        return self._get("artists", {"id": artist_id}, _artist)

    def update_artist(self, artist: Artist) -> None:
        self._update("artists", BY_ID, _artist_row(artist), subject=f"artist {artist.id!r}")

    def list_artists(self) -> Sequence[Artist]:
        return self._list("artists", None, _BY_NAME, _artist)

    # -- artworks -------------------------------------------------------------

    def add_artwork(self, artwork: Artwork) -> None:
        self._add("artworks", _artwork_row(artwork), subject=f"artwork {artwork.id!r}")

    def get_artwork(self, artwork_id: str) -> Artwork | None:
        return self._get("artworks", {"id": artwork_id}, _artwork)

    def update_artwork(self, artwork: Artwork) -> None:
        self._update("artworks", BY_ID, _artwork_row(artwork), subject=f"artwork {artwork.id!r}")

    def list_artworks(self, query: WorkQuery, *, limit: int, offset: int, order: WorkOrder = WorkOrder.TITLE) -> ArtworkPage:
        selects = _matching(query)
        # Counted first and from the same clause as the page, so "showing 20 of
        # 84" cannot describe a different 84 from the twenty beside it.
        total = int(
            self._store.select_rows(f"SELECT COUNT(*) AS total {selects.source} WHERE {selects.where}", selects.values)[0][
                "total"
            ]
        )
        rows = self._store.select_rows(
            f"SELECT a.* {selects.source} WHERE {selects.where} ORDER BY {_WORKS_ORDERS[order]} LIMIT ? OFFSET ?",
            (*selects.values, limit, offset),
        )
        return ArtworkPage(artworks=[_artwork(row) for row in rows], total=total)

    def held_artists(self) -> Sequence[tuple[Artist, int]]:
        rows = self._store.select_rows(
            'SELECT ar.*, COUNT(a."id") AS held FROM artists ar JOIN artworks a ON a."artist_id" = ar."id" '
            'WHERE a."status" = ? GROUP BY ar."id" ORDER BY ar."name" COLLATE NOCASE, ar."id"',
            (str(ArtworkStatus.ACCEPTED),),
        )
        return [(_artist(row), int(row["held"])) for row in rows]

    def circulating_ids_by_qid(self) -> Mapping[str, Sequence[str]]:
        rows = self._store.select_rows(
            'SELECT a."wikidata_qid" AS qid, a."id" AS id FROM artworks a '
            'WHERE a."wikidata_qid" IS NOT NULL AND a."status" = ? ORDER BY a."created_at", a.rowid',
            (str(ArtworkStatus.ACCEPTED),),
        )
        found: dict[str, list[str]] = {}
        for row in rows:
            found.setdefault(row["qid"], []).append(row["id"])
        return found

    def accepted_artwork_ids(self) -> Sequence[str]:
        # Oldest first, `rowid` breaking a tie within one clock tick, so a catch-up
        # joins works to a theme in the order they arrived.
        rows = self._store.select_rows(
            'SELECT a."id" AS id FROM artworks a WHERE a."status" = ? ORDER BY a."created_at", a.rowid',
            (str(ArtworkStatus.ACCEPTED),),
        )
        return [row["id"] for row in rows]

    # -- what a work is, and what a filter would select -----------------------

    def add_facet(self, facet: WorkFacet) -> None:
        # Named by what it claims rather than by its id, for the reason `add_wall`
        # gives: the id is a fresh uuid4 and can never collide, so the only way
        # this refuses is the (artwork_id, kind, value) uniqueness — and a refusal
        # quoting a uuid nobody has seen would name the wrong thing entirely.
        self._add("work_facets", _facet_row(facet), subject=f"facet {facet.kind}={facet.value!r} on artwork {facet.artwork_id!r}")

    def remove_facet(self, facet_id: str) -> None:
        self._store.delete("work_facets", {"id": facet_id})

    def list_facets(self, artwork_id: str) -> Sequence[WorkFacet]:
        # Unknown kinds skipped, the same way `facet_vocabulary` and
        # `count_facet_values` skip them and for the same downgrade case: a file
        # written by a later build must not make one work unreadable when it
        # already cannot make the collection unreadable. Raising here was the
        # inconsistency — and it raised `ValueError`, which is not a
        # `StorageError`, so it reached the HTTP layer as a 500 rather than as
        # the sentence a refusal owes its caller.
        rows = self._list("work_facets", {"artwork_id": artwork_id}, _BY_KIND_VALUE, dict)
        return [_facet(row) for row in rows if _known_kind(row["kind"]) is not None]

    def facet_vocabulary(self, *, status: ArtworkStatus | None) -> Mapping[VocabularyKind, Sequence[str]]:
        selects = _matching(WorkQuery(status=status))
        rows = self._store.select_rows(
            f"SELECT f.kind AS kind, f.value AS value FROM work_facets f "
            f"WHERE 1{selects.over_works(column='f.artwork_id')} "
            f"GROUP BY f.kind, f.value ORDER BY f.kind, f.value COLLATE NOCASE",
            selects.values,
        )
        vocabulary: dict[VocabularyKind, list[str]] = {}
        for row in rows:
            # A row whose kind this build does not know is skipped rather than
            # raising: a file written by a later version is a thing a downgrade
            # meets, and one unrecognised value must not make the whole
            # collection unreadable.
            kind = _known_kind(row["kind"])
            if kind is not None:
                vocabulary.setdefault(kind, []).append(row["value"])
        return vocabulary

    def count_facet_values(self, kinds: Sequence[VocabularyKind], query: WorkQuery) -> Mapping[VocabularyKind, Mapping[str, int]]:
        if not kinds:
            return {}
        selects = _matching(query)
        placeholders = ", ".join("?" for _ in kinds)
        rows = self._store.select_rows(
            # `COUNT(*)` and not `COUNT(DISTINCT ...)`: `work_facets_once_per_work`
            # makes a second row for the same work and value impossible, so the
            # two are the same number and the cheaper one says so.
            f"SELECT f.kind AS kind, f.value AS value, COUNT(*) AS tally FROM work_facets f "
            f"WHERE f.kind IN ({placeholders}){selects.over_works(column='f.artwork_id')} "
            f"GROUP BY f.kind, f.value",
            (*(str(kind) for kind in kinds), *selects.values),
        )
        counted: dict[VocabularyKind, dict[str, int]] = {kind: {} for kind in kinds}
        for row in rows:
            kind = _known_kind(row["kind"])
            if kind is not None:
                counted[kind][row["value"]] = int(row["tally"])
        return counted

    def topic_tallies(self, *, status: ArtworkStatus | None, qid: str | None = None) -> Sequence[TopicTally]:
        selects = _matching(WorkQuery(status=status))
        narrowed, bound = ("", ()) if qid is None else (" AND f.value_qid = ?", (qid,))
        rows = self._store.select_rows(
            # `COUNT(DISTINCT ...)` here, unlike `count_facet_values`: the
            # uniqueness is per value, and two values on one work may name one
            # item. `MIN` picks one label deterministically where two rows wrote
            # the item's name differently.
            f"SELECT f.kind AS kind, f.value_qid AS qid, MIN(f.value) AS label, COUNT(DISTINCT f.artwork_id) AS tally "
            f"FROM work_facets f WHERE f.value_qid IS NOT NULL{narrowed}{selects.over_works(column='f.artwork_id')} "
            f"GROUP BY f.kind, f.value_qid ORDER BY f.kind, label COLLATE NOCASE, f.value_qid",
            (*bound, *selects.values),
        )
        tallies: list[TopicTally] = []
        for row in rows:
            # Skipped, as everywhere a facet kind is read: a later build's kind
            # must not make the index unreadable.
            kind = _known_kind(row["kind"])
            if kind is not None:
                tallies.append(TopicTally(kind=kind, qid=row["qid"], label=row["label"], works=int(row["tally"])))
        return tallies

    def works_with_topic(self, qid: str, *, status: ArtworkStatus | None, kinds: Sequence[VocabularyKind]) -> Sequence[str]:
        if not kinds:
            return []
        selects = _matching(WorkQuery(status=status))
        placeholders = ", ".join("?" for _ in kinds)
        rows = self._store.select_rows(
            f"SELECT a.id AS id {selects.source} WHERE {selects.where} "
            f"AND a.id IN (SELECT artwork_id FROM work_facets WHERE value_qid = ? AND kind IN ({placeholders})) "
            f"ORDER BY {_WORKS_ORDERS[WorkOrder.TITLE]}",
            (*selects.values, qid, *(str(kind) for kind in kinds)),
        )
        return [row["id"] for row in rows]

    # -- sources --------------------------------------------------------------

    def add_source(self, source: Source) -> None:
        self._add("sources", _source_row(source), subject=f"source {source.id!r}")

    def get_source(self, source_id: str) -> Source | None:
        return self._get("sources", {"id": source_id}, _source)

    def update_source(self, source: Source) -> None:
        self._update("sources", BY_ID, _source_row(source), subject=f"source {source.id!r}")

    def list_sources(self, artwork_id: str) -> Sequence[Source]:
        return self._list("sources", {"artwork_id": artwork_id}, _BY_PRIMARY, _source)

    # -- originals ------------------------------------------------------------

    def add_original(self, original: Original) -> None:
        self._add("originals", _original_row(original), subject=f"original for artwork {original.artwork_id!r}")

    def get_original(self, artwork_id: str) -> Original | None:
        # Addressed by the work rather than by its own id: one work holds at most
        # one original, and every caller arrives holding the work.
        rows = self._store.scan("originals", {"artwork_id": artwork_id})
        return _original(rows[0]) if rows else None

    def update_original(self, original: Original) -> None:
        self._update("originals", BY_ID, _original_row(original), subject=f"original for artwork {original.artwork_id!r}")

    # -- renditions -----------------------------------------------------------

    def add_rendition(self, rendition: Rendition) -> None:
        self._add("renditions", _rendition_row(rendition), subject=f"rendition {rendition.id!r}")

    def update_rendition(self, rendition: Rendition) -> None:
        self._update("renditions", BY_ID, _rendition_row(rendition), subject=f"rendition {rendition.id!r}")

    def list_renditions(self, artwork_id: str) -> Sequence[Rendition]:
        return self._list("renditions", {"artwork_id": artwork_id}, _BY_GEOMETRY, _rendition)

    def find_renditions_by_content(self, content_sha256: str) -> Sequence[Rendition]:
        return self._list("renditions", {"content_sha256": content_sha256}, _BY_GEOMETRY, _rendition)

    # -- mat colours ----------------------------------------------------------

    def add_mat_color(self, mat_color: MatColor) -> None:
        self._add("mat_colors", _mat_color_row(mat_color), subject=f"mat colour {mat_color.id!r}")

    def update_mat_color(self, mat_color: MatColor) -> None:
        self._update("mat_colors", BY_ID, _mat_color_row(mat_color), subject=f"mat colour {mat_color.id!r}")

    def list_mat_colors(self, artwork_id: str) -> Sequence[MatColor]:
        return self._list("mat_colors", {"artwork_id": artwork_id}, _BY_RECENCY, _mat_color)

    # -- the acquisition queue ------------------------------------------------

    def works_to_acquire(self) -> Sequence[WorkToAcquire]:
        # Oldest acceptance first, so a backlog is worked in the order it was
        # asked for. `accepted_at` is null on rows written before it existed,
        # which then fall back to when the work was catalogued; `rowid` breaks a
        # tie within one clock tick.
        rows = self._store.select_rows(
            'SELECT a."id" AS work_id, o."id" IS NOT NULL AS held, q."artwork_id" AS queued_id, '
            'q."failures", q."next_try_at", q."detail", q."source_id" '
            "FROM artworks a "
            'LEFT JOIN originals o ON o."artwork_id" = a."id" '
            'LEFT JOIN acquisition_queue q ON q."artwork_id" = a."id" '
            'WHERE a."status" = ? AND (o."id" IS NULL OR q."artwork_id" IS NOT NULL) '
            'ORDER BY coalesce(a."accepted_at", a."created_at"), a.rowid',
            (str(ArtworkStatus.ACCEPTED),),
        )
        return [
            WorkToAcquire(
                artwork_id=row["work_id"],
                holds_original=bool(row["held"]),
                queued=None if row["queued_id"] is None else _queued({**row, "artwork_id": row["queued_id"]}),
            )
            for row in rows
        ]

    def get_queued_acquisition(self, artwork_id: str) -> QueuedAcquisition | None:
        return self._get("acquisition_queue", {"artwork_id": artwork_id}, _queued)

    def set_queued_acquisition(self, entry: QueuedAcquisition) -> None:
        # `update` rather than `raise`: the row is the queue's working memory of
        # one work, rewritten after every attempt, and there is no "add" that a
        # second write could be a mistaken repeat of.
        self._store.upsert("acquisition_queue", _queued_row(entry), pk=_BY_ARTWORK, on_conflict="update")

    def remove_queued_acquisition(self, artwork_id: str) -> None:
        self._delete("acquisition_queue", {"artwork_id": artwork_id})

    # -- themes ---------------------------------------------------------------

    def add_theme(self, theme: Theme) -> None:
        self._add("themes", _theme_row(theme), subject=f"theme {theme.id!r}")

    def get_theme(self, theme_id: str) -> Theme | None:
        return self._get("themes", {"id": theme_id}, _theme)

    def update_theme(self, theme: Theme) -> None:
        self._update("themes", BY_ID, _theme_row(theme), subject=f"theme {theme.id!r}")

    def list_themes(self) -> Sequence[Theme]:
        return self._list("themes", None, _BY_NAME, _theme)

    def remove_theme(self, theme_id: str) -> None:
        self._store.delete("themes", {"id": theme_id})

    # -- theme membership -----------------------------------------------------

    def add_membership(self, membership: ThemeMembership) -> None:
        self._add(
            "theme_memberships",
            _membership_row(membership),
            subject=f"artwork {membership.artwork_id!r} in theme {membership.theme_id!r}",
            key=_MEMBERSHIP_KEY,
        )

    def get_membership(self, theme_id: str, artwork_id: str) -> ThemeMembership | None:
        return self._get("theme_memberships", {"theme_id": theme_id, "artwork_id": artwork_id}, _membership)

    def update_membership(self, membership: ThemeMembership) -> None:
        self._update(
            "theme_memberships",
            _MEMBERSHIP_KEY,
            _membership_row(membership),
            subject=f"artwork {membership.artwork_id!r} in theme {membership.theme_id!r}",
        )

    def remove_membership(self, theme_id: str, artwork_id: str) -> None:
        self._store.delete("theme_memberships", {"theme_id": theme_id, "artwork_id": artwork_id})

    def list_memberships(self, theme_id: str) -> Sequence[ThemeMembership]:
        return self._list("theme_memberships", {"theme_id": theme_id}, _BY_POSITION, _membership)

    # -- the default theme ----------------------------------------------------

    def get_default_theme(self) -> Theme | None:
        marked = self._list("themes", {"is_default": 1}, _BY_NAME, _theme)
        return marked[0] if marked else None

    def mark_default_theme(self, theme_id: str) -> None:
        # Cleared before set, in one transaction: the partial unique index
        # refuses a second mark, so setting first would be refused, and a clear
        # without its set would leave no default that anybody chose.
        with self._store.transaction():
            for theme in self._list("themes", {"is_default": 1}, _BY_NAME, _theme):
                if theme.id != theme_id:
                    self._update("themes", BY_ID, {**_theme_row(theme), "is_default": 0}, subject=f"theme {theme.id!r}")
            theme = self.get_theme(theme_id)
            if theme is None:
                reason = "it is not stored."
                raise StorageError(f"Could not mark theme {theme_id!r} the default: {reason}", reason=reason)
            self._update("themes", BY_ID, {**_theme_row(theme), "is_default": 1}, subject=f"theme {theme_id!r}")

    def record_offer(self, artwork_id: str, offered_at: datetime) -> None:
        self._add(
            "default_theme_offers",
            {"artwork_id": artwork_id, "offered_at": to_iso(offered_at)},
            subject=f"the default theme's offer of artwork {artwork_id!r}",
            key=("artwork_id",),
        )

    def offered_work_ids(self) -> set[str]:
        return {row["artwork_id"] for row in self._store.scan("default_theme_offers")}

    # -- walls ----------------------------------------------------------------

    def add_wall(self, wall: Wall) -> None:
        # Named rather than identified, unlike every neighbour here. The id is a
        # fresh uuid4 and can never be the thing already stored, so the only way
        # this insert refuses is the UNIQUE on `name` — and "could not store wall
        # '<uuid>'" would report a collision on a value nobody has ever seen, to
        # a curator who typed a room's name. The refusal has to name what
        # collided.
        self._add("walls", _wall_row(wall), subject=f"wall {wall.name!r}")

    def get_wall(self, wall_id: str) -> Wall | None:
        return self._get("walls", {"id": wall_id}, _wall)

    def list_walls(self) -> Sequence[Wall]:
        return self._list("walls", None, _BY_NAME, _wall)

    def update_wall(self, wall: Wall) -> None:
        self._update("walls", BY_ID, _wall_row(wall), subject=f"wall {wall.name!r}")

    # -- clients --------------------------------------------------------------

    def add_client(self, client: Client) -> None:
        # Named rather than identified, for the reason `add_wall` gives.
        self._add("clients", _client_row(client), subject=f"client {client.name!r}")

    def get_client(self, client_id: str) -> Client | None:
        return self._get("clients", {"id": client_id}, _client)

    def update_client(self, client: Client) -> None:
        self._update("clients", BY_ID, _client_row(client), subject=f"client {client.name!r}")

    def list_clients(self) -> Sequence[Client]:
        return self._list("clients", None, _BY_NAME, _client)

    def remove_client(self, client_id: str) -> None:
        self._store.delete("clients", {"id": client_id})

    # -- what is hanging ------------------------------------------------------

    def get_assignment(self, wall_id: str) -> ThemeAssignment | None:
        return self._get("theme_assignments", {"wall_id": wall_id}, _assignment)

    def set_assignment(self, assignment: ThemeAssignment) -> None:
        # `update` rather than `raise`, because hanging a theme on a wall that
        # already holds one replaces it. That is the whole operation — there is
        # no take-down-then-hang pair a reader could be caught between.
        self._store.upsert("theme_assignments", _assignment_row(assignment), pk=_BY_WALL, on_conflict="update")

    def remove_assignment(self, wall_id: str) -> None:
        self._store.delete("theme_assignments", {"wall_id": wall_id})

    def list_assignments(self) -> Sequence[ThemeAssignment]:
        return self._list("theme_assignments", None, _BY_WALL_ID, _assignment)

    # -- the display directives -----------------------------------------------

    def add_directive(self, directive: Directive) -> None:
        self._add("directives", _directive_row(directive), subject=f"directive for wall {directive.wall_id!r}", key=_BY_WALL)

    def get_directive(self, wall_id: str) -> Directive:
        row = self._store.fetch_one("directives", {"wall_id": wall_id})
        if row is None:
            # Seeded when the wall is created, so its absence means either an
            # unknown wall or a file edited by something other than this code.
            raise StorageError(f"Wall {wall_id!r} has no display directive row.")
        return _directive(row)

    def set_directive(self, directive: Directive) -> None:
        self._update(
            "directives",
            _BY_WALL,
            _directive_row(directive),
            subject=f"the display directive for wall {directive.wall_id!r}",
        )

    def list_directives(self) -> Sequence[Directive]:
        return self._list("directives", None, _BY_WALL_ID, _directive)


# -- record to row ------------------------------------------------------------


def _artist_row(artist: Artist) -> dict[str, Any]:
    return {
        "id": artist.id,
        "name": artist.name,
        "nationality": artist.nationality,
        "born": artist.born,
        "died": artist.died,
        "lifespan_text": artist.lifespan_text,
        "biography": artist.biography,
        "family_name": artist.family_name,
        "given_name": artist.given_name,
        "display_nationality": artist.display_nationality,
        "wikidata_qid": artist.wikidata_qid,
        "wikidata_qid_set_by": None if artist.wikidata_qid_set_by is None else str(artist.wikidata_qid_set_by),
    }


def _artwork_row(artwork: Artwork) -> dict[str, Any]:
    return {
        "id": artwork.id,
        "title": artwork.title,
        "artist_id": artwork.artist_id,
        "date_created": artwork.date_created,
        "medium": artwork.medium,
        "dimensions": artwork.dimensions,
        "description": artwork.description,
        "rights": artwork.rights,
        "status": str(artwork.status),
        "accepted_at": to_iso(artwork.accepted_at),
        "created_at": to_iso(artwork.created_at),
        "commentary": artwork.commentary,
        "wikidata_qid": artwork.wikidata_qid,
        "wikidata_qid_set_by": None if artwork.wikidata_qid_set_by is None else str(artwork.wikidata_qid_set_by),
    }


def _facet_row(facet: WorkFacet) -> dict[str, Any]:
    return {
        "id": facet.id,
        "artwork_id": facet.artwork_id,
        "kind": str(facet.kind),
        "value": facet.value,
        "derivation": str(facet.derivation),
        "source_note": facet.source_note,
        "created_at": to_iso(facet.created_at),
        "value_qid": facet.value_qid,
    }


def _source_row(source: Source) -> dict[str, Any]:
    return {
        "id": source.id,
        "artwork_id": source.artwork_id,
        "url": source.url,
        "provider": source.provider,
        "source_class": str(source.source_class),
        "acquisition_method": str(source.acquisition_method),
        "rights_status": str(source.rights_status),
        "is_primary": int(source.is_primary),
        "confidence": source.confidence,
        "selection_rationale": source.selection_rationale,
        "last_fetch_status": None if source.last_fetch_status is None else str(source.last_fetch_status),
        "last_fetched_at": to_iso(source.last_fetched_at),
    }


def _original_row(original: Original) -> dict[str, Any]:
    return {
        "id": original.id,
        "artwork_id": original.artwork_id,
        "source_id": original.source_id,
        "relative_path": original.relative_path,
        "width": original.width,
        "height": original.height,
        "byte_size": original.byte_size,
        "content_hash": original.content_hash,
        "fetch_status": None if original.fetch_status is None else original.fetch_status.value,
    }


def _queued_row(entry: QueuedAcquisition) -> dict[str, Any]:
    return {
        "artwork_id": entry.artwork_id,
        "failures": entry.failures,
        "next_try_at": to_iso(entry.next_try_at),
        "detail": entry.detail,
        "source_id": entry.source_id,
    }


def _rendition_row(rendition: Rendition) -> dict[str, Any]:
    return {
        "id": rendition.id,
        "artwork_id": rendition.artwork_id,
        "kind": str(rendition.kind),
        "target_width": rendition.target_width,
        "target_height": rendition.target_height,
        "relative_path": rendition.relative_path,
        "source_content_hash": rendition.source_content_hash,
        "generated_at": to_iso(rendition.generated_at),
        "content_sha256": rendition.content_sha256,
        "byte_size": rendition.byte_size,
    }


def _mat_color_row(mat_color: MatColor) -> dict[str, Any]:
    return {
        "id": mat_color.id,
        "artwork_id": mat_color.artwork_id,
        "hex_rgb": mat_color.hex_rgb,
        "method": str(mat_color.method),
        "is_current": int(mat_color.is_current),
        "lab_l": mat_color.lab_l,
        "lab_a": mat_color.lab_a,
        "lab_b": mat_color.lab_b,
        "reason": mat_color.reason,
        "model_id": mat_color.model_id,
        "chosen_at": to_iso(mat_color.chosen_at),
    }


def _theme_row(theme: Theme) -> dict[str, Any]:
    return {
        "id": theme.id,
        "name": theme.name,
        "description": theme.description,
        "created_at": to_iso(theme.created_at),
        "rotation_interval_seconds": theme.rotation_interval_seconds,
        # None survives as null — "inherit the global default" — where int(None)
        # would raise and bool(None) would silently write a decision the curator
        # never made.
        "shuffle": None if theme.shuffle is None else int(theme.shuffle),
        # `is_default` is not written from the record: only `mark_default_theme`
        # writes it, so saving a theme leaves the mark where it is.
    }


def _membership_row(membership: ThemeMembership) -> dict[str, Any]:
    return {
        "theme_id": membership.theme_id,
        "artwork_id": membership.artwork_id,
        "position": membership.position,
        "added_at": to_iso(membership.added_at),
    }


def _client_row(client: Client) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "created_at": to_iso(client.created_at),
        "token_verifier": client.token_verifier,
        "token_issued_at": to_iso(client.token_issued_at),
    }


def _wall_row(wall: Wall) -> dict[str, Any]:
    return {
        "id": wall.id,
        "name": wall.name,
        "created_at": to_iso(wall.created_at),
        "client_id": wall.client_id,
        "output": wall.output,
    }


def _assignment_row(assignment: ThemeAssignment) -> dict[str, Any]:
    return {
        "wall_id": assignment.wall_id,
        "theme_id": assignment.theme_id,
        "assigned_at": to_iso(assignment.assigned_at),
    }


def _directive_row(directive: Directive) -> dict[str, Any]:
    return {
        "wall_id": directive.wall_id,
        "sequence": directive.sequence,
        "pinned_work_id": directive.pinned_work_id,
    }


# -- row to record ------------------------------------------------------------


def _artist(row: Mapping[str, Any]) -> Artist:
    return Artist(
        id=row["id"],
        name=row["name"],
        nationality=row["nationality"],
        born=row["born"],
        died=row["died"],
        lifespan_text=row["lifespan_text"],
        biography=row["biography"],
        family_name=row["family_name"],
        given_name=row["given_name"],
        display_nationality=row["display_nationality"],
        wikidata_qid=row["wikidata_qid"],
        wikidata_qid_set_by=_set_by(row["wikidata_qid_set_by"]),
    )


def _artwork(row: Mapping[str, Any]) -> Artwork:
    return Artwork(
        id=row["id"],
        title=row["title"],
        created_at=require_datetime(row["created_at"], "created_at"),
        status=ArtworkStatus(row["status"]),
        artist_id=row["artist_id"],
        date_created=row["date_created"],
        medium=row["medium"],
        dimensions=row["dimensions"],
        description=row["description"],
        rights=row["rights"],
        accepted_at=from_iso(row["accepted_at"]),
        commentary=row["commentary"],
        wikidata_qid=row["wikidata_qid"],
        wikidata_qid_set_by=_set_by(row["wikidata_qid_set_by"]),
    )


def _set_by(value: str | None) -> IdentitySetBy | None:
    return None if value is None else IdentitySetBy(value)


def _facet(row: Mapping[str, Any]) -> WorkFacet:
    return WorkFacet(
        id=row["id"],
        artwork_id=row["artwork_id"],
        kind=VocabularyKind(row["kind"]),
        value=row["value"],
        derivation=FacetDerivation(row["derivation"]),
        created_at=require_datetime(row["created_at"], "created_at"),
        source_note=row["source_note"],
        value_qid=row["value_qid"],
    )


def _source(row: Mapping[str, Any]) -> Source:
    return Source(
        id=row["id"],
        artwork_id=row["artwork_id"],
        url=row["url"],
        provider=row["provider"],
        source_class=SourceClass(row["source_class"]),
        acquisition_method=AcquisitionMethod(row["acquisition_method"]),
        rights_status=RightsStatus(row["rights_status"]),
        is_primary=bool(row["is_primary"]),
        confidence=row["confidence"],
        selection_rationale=row["selection_rationale"],
        last_fetch_status=None if row["last_fetch_status"] is None else FetchStatus(row["last_fetch_status"]),
        last_fetched_at=from_iso(row["last_fetched_at"]),
    )


def _original(row: Mapping[str, Any]) -> Original:
    return Original(
        id=row["id"],
        artwork_id=row["artwork_id"],
        source_id=row["source_id"],
        relative_path=row["relative_path"],
        width=row["width"],
        height=row["height"],
        byte_size=row["byte_size"],
        content_hash=row["content_hash"],
        # `.get`, not `[...]`: a catalogue file written before this column existed
        # is widened on open, but a row read through a mapping built from an older
        # file's columns would raise KeyError where the contract is "unrecorded".
        fetch_status=None if row.get("fetch_status") is None else FetchStatus(row["fetch_status"]),
    )


def _queued(row: Mapping[str, Any]) -> QueuedAcquisition:
    return QueuedAcquisition(
        artwork_id=row["artwork_id"],
        failures=row["failures"],
        next_try_at=from_iso(row["next_try_at"]),
        detail=row["detail"],
        source_id=row["source_id"],
    )


def _rendition(row: Mapping[str, Any]) -> Rendition:
    return Rendition(
        id=row["id"],
        artwork_id=row["artwork_id"],
        kind=RenditionKind(row["kind"]),
        target_width=row["target_width"],
        target_height=row["target_height"],
        relative_path=row["relative_path"],
        source_content_hash=row["source_content_hash"],
        generated_at=require_datetime(row["generated_at"], "generated_at"),
        content_sha256=row["content_sha256"],
        byte_size=row["byte_size"],
    )


def _mat_color(row: Mapping[str, Any]) -> MatColor:
    return MatColor(
        id=row["id"],
        artwork_id=row["artwork_id"],
        hex_rgb=row["hex_rgb"],
        method=MatMethod(row["method"]),
        chosen_at=require_datetime(row["chosen_at"], "chosen_at"),
        is_current=bool(row["is_current"]),
        lab_l=row["lab_l"],
        lab_a=row["lab_a"],
        lab_b=row["lab_b"],
        reason=row["reason"],
        model_id=row["model_id"],
    )


def _theme(row: Mapping[str, Any]) -> Theme:
    return Theme(
        id=row["id"],
        name=row["name"],
        created_at=require_datetime(row["created_at"], "created_at"),
        description=row["description"],
        rotation_interval_seconds=row["rotation_interval_seconds"],
        shuffle=None if row["shuffle"] is None else bool(row["shuffle"]),
        is_default=bool(row["is_default"]),
    )


def _wall(row: Mapping[str, Any]) -> Wall:
    return Wall(
        id=row["id"],
        name=row["name"],
        created_at=require_datetime(row["created_at"], "created_at"),
        client_id=row["client_id"],
        output=row["output"],
    )


def _client(row: Mapping[str, Any]) -> Client:
    return Client(
        id=row["id"],
        name=row["name"],
        created_at=require_datetime(row["created_at"], "created_at"),
        token_verifier=row["token_verifier"],
        token_issued_at=from_iso(row["token_issued_at"]),
    )


def _assignment(row: Mapping[str, Any]) -> ThemeAssignment:
    return ThemeAssignment(
        wall_id=row["wall_id"],
        theme_id=row["theme_id"],
        assigned_at=require_datetime(row["assigned_at"], "assigned_at"),
    )


def _directive(row: Mapping[str, Any]) -> Directive:
    return Directive(wall_id=row["wall_id"], sequence=row["sequence"], pinned_work_id=row["pinned_work_id"])


def _membership(row: Mapping[str, Any]) -> ThemeMembership:
    return ThemeMembership(
        theme_id=row["theme_id"],
        artwork_id=row["artwork_id"],
        added_at=require_datetime(row["added_at"], "added_at"),
        position=row["position"],
    )
