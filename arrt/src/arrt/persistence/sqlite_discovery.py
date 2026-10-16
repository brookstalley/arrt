"""A `DiscoveryStore` over the same SQLite file the catalogue uses.

The counterpart to `sqlite.py`: it owns the pipeline's tables, the mapping
between its records and rows, and the ordering that makes each listing stable.
Both adapters run over one `SqliteDurableStore`, which is what lets acceptance
write on both sides of the pipeline boundary in one transaction.

Ordering is decided here rather than below because it is a product judgement.
Runs read newest first because a run list is a history. Instances read with the
selected one first where a selection exists, so the automatic choice and any
surface showing it cannot come to disagree about which scan is on offer.

**That ordering is not a statement about which instances are offerable.** A work
whose scans are all below the floor or all turned down has no selection, and then
the leading row is simply the highest-ranked — which may be one already refused,
since refusing a scan does not change how good the picture is. `is_selected` and
`rejected_at` are what answer those questions; position is not. A reader who takes
this order as an offerability guarantee writes a surface that shows a curator
scans they cannot choose.

**The unique index below does not replace the service layer's rules.** Every rule
is applied in the service layer, where a refusal can be phrased for whoever
asked; the index catches the case where some path forgets to, and its message
names only the table.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from arrt.persistence.adapter import (
    BY_ID,
    TableAdapter,
    from_iso,
    from_money,
    require_datetime,
    require_money,
    to_iso,
    to_money,
)
from arrt.persistence.discovery_records import (
    Affinity,
    AffinityDerivation,
    AffinitySentiment,
    CandidateImage,
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    ResolutionStatus,
    ResolveRunWork,
    RunKind,
    RunStatus,
    Sighting,
    SourceYield,
    SpendCategory,
    SpendRecord,
    UnresolvedReason,
    Verdict,
    WorkProvenance,
)
from arrt.persistence.durable import OrderBy
from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass, VocabularyKind

#: How many ids one `IN (...)` binds. Well under SQLite's bound on a statement's
#: parameters, which is 999 on builds older than 3.32.
_IDS_PER_STATEMENT: Final[int] = 500

#: Every provider's offers and holdings, one row per provider (`source_yields`).
#:
#: - **offers**: one row per (provider, address), from candidate images and the
#:   catalogue's sources alike, so a work held from before searching recorded
#:   candidates still counts its source as having offered. An address offered
#:   again by a later search is one offer. The long edge is known only from a
#:   candidate image's estimate.
#: - **chosen**: each work's primary source, which is its chosen image.
#: - **work_offers**: which providers offered anything for each held work: its
#:   catalogue sources, and the candidate images of every proposal of the same
#:   work (by `work_dedup_key`) as the one acceptance minted it from, since a
#:   search that found the work again in another run offered it too.
#: - The median is the middle offer by long edge, or the mean of the two
#:   middle ones, over the offers whose size is known.
_SOURCE_YIELDS: Final[str] = """
WITH offers AS (
    SELECT provider, url, MAX(long_edge) AS long_edge FROM (
        SELECT provider, url,
               CASE WHEN estimated_width IS NULL AND estimated_height IS NULL THEN NULL
                    ELSE MAX(COALESCE(estimated_width, 0), COALESCE(estimated_height, 0)) END AS long_edge
          FROM candidate_images
        UNION ALL
        SELECT provider, url, NULL FROM sources
    ) GROUP BY provider, url
),
offered AS (
    SELECT provider, COUNT(*) AS offered FROM offers GROUP BY provider
),
ranked AS (
    SELECT provider, long_edge,
           ROW_NUMBER() OVER (PARTITION BY provider ORDER BY long_edge) AS position,
           COUNT(*) OVER (PARTITION BY provider) AS sized
      FROM offers WHERE long_edge IS NOT NULL
),
medians AS (
    SELECT provider, AVG(long_edge) AS median_long_edge FROM ranked
     WHERE position IN ((sized + 1) / 2, (sized + 2) / 2) GROUP BY provider
),
chosen AS (
    SELECT artwork_id, provider FROM sources WHERE is_primary = 1
),
work_offers AS (
    SELECT artwork_id, provider FROM sources
    UNION
    SELECT minted.artwork_id, ci.provider
      FROM candidate_works minted
      JOIN candidate_works proposal ON proposal.work_dedup_key = minted.work_dedup_key
      JOIN candidate_images ci ON ci.candidate_work_id = proposal.id
     WHERE minted.artwork_id IS NOT NULL
),
holdings AS (
    SELECT c.provider, COUNT(*) AS chosen,
           SUM(CASE WHEN EXISTS (
                   SELECT 1 FROM work_offers o WHERE o.artwork_id = c.artwork_id AND o.provider <> c.provider
               ) THEN 0 ELSE 1 END) AS only_here
      FROM chosen c GROUP BY c.provider
)
SELECT o.provider AS provider, o.offered AS offered,
       COALESCE(h.chosen, 0) AS chosen, COALESCE(h.only_here, 0) AS only_here,
       m.median_long_edge AS median_long_edge
  FROM offered o
  LEFT JOIN holdings h ON h.provider = o.provider
  LEFT JOIN medians m ON m.provider = o.provider
"""

DISCOVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS discovery_runs (
    id                     TEXT PRIMARY KEY,
    kind                   TEXT NOT NULL,
    -- A resolve run's parent is the run that originally proposed these works.
    -- Cost rolls up through this chain, which is what keeps "what did asking for
    -- Dali cost" answerable once spend is spread across several runs.
    parent_run_id          TEXT REFERENCES discovery_runs(id),
    intent_text            TEXT,
    strategy               TEXT,
    initiated_by           TEXT NOT NULL,
    status                 TEXT NOT NULL,
    estimated_cost_usd     TEXT,
    actual_cost_usd        TEXT,
    approval_required      INTEGER NOT NULL,
    unresolved_work_count  INTEGER,
    started_at             TEXT NOT NULL,
    completed_at           TEXT,
    -- The theme a Get's accepted works join instead of the default. Programming's
    -- id, so deliberately no REFERENCES clause: it is an opaque reference across
    -- the Library/Programming seam that may fail to resolve once the theme is
    -- deleted. Null means the default, and is what every run before Gets could
    -- name a theme reads as; nullable so widening reaches older files.
    destination_theme_id   TEXT,
    -- Why the run's worker ended it, written only by `failed` and
    -- `halted_by_budget`. Nullable so widening reaches older files, whose runs
    -- ended before a reason was kept and read back as giving none.
    end_reason             TEXT
);

-- Startup reconciliation reads runs by status, on every process start.
CREATE INDEX IF NOT EXISTS discovery_runs_by_status ON discovery_runs(status);
CREATE INDEX IF NOT EXISTS discovery_runs_by_parent ON discovery_runs(parent_run_id);

CREATE TABLE IF NOT EXISTS candidate_works (
    id                 TEXT PRIMARY KEY,
    discovery_run_id   TEXT NOT NULL REFERENCES discovery_runs(id),
    artwork_id         TEXT REFERENCES artworks(id),
    proposed_title     TEXT NOT NULL,
    proposed_artist    TEXT,
    rationale          TEXT NOT NULL,
    work_dedup_key     TEXT NOT NULL,
    -- Nullable so the widening step can add it to files written before
    -- collections could be browsed. A null is `proposed`: nothing but phase 1
    -- could mint a candidate work then, so the absent value has one meaning.
    provenance         TEXT,
    -- Which browse query produced an offered work, and how many works that query
    -- matched in the collection. Both null for a proposed work, which no query
    -- produced. They are stored as facts rather than composed into `rationale`
    -- because the sentence they belong to is per-QUERY: `product-brief.md` asks
    -- that a curator be able to tell one-of-four-hundred from one-of-one, and the
    -- surface says that once for the group. `matched` is the collection's total
    -- and is deliberately not capped by `offered_works_per_run` — the cap is what
    -- the reader reconciles it against, so capping it here would destroy the
    -- comparison the requirement exists for.
    offered_for_artist     TEXT,
    offered_artist_matched INTEGER,
    -- The source (provider id) that offered the work, kept on the work because
    -- the scan it arrived with can be turned down and replaced by another
    -- museum's. Null on proposed and chosen works, and on offers recorded before
    -- it was kept; nullable so widening reaches older files.
    offered_by             TEXT,
    -- The Wikidata item a chosen work was asked for by. Null on proposed and
    -- offered works, which no item named; nullable so widening reaches older files.
    wikidata_qid           TEXT,
    -- Phase 1's word on whether a source it was given confirms a work it
    -- proposed: 1, 0, or null for no word. Nullable so widening reaches older
    -- files, whose proposals read as unconfirmed-or-not unknown, never confirmed.
    source_confirmed       INTEGER,
    resolution_status  TEXT NOT NULL,
    unresolved_reason  TEXT,
    verdict            TEXT NOT NULL,
    rejected_reason    TEXT,
    decided_at         TEXT
);

-- Work-scoped suppression is a lookup by this key on every proposal, and it
-- spans runs on purpose: a work declined in March must not return in April.
CREATE INDEX IF NOT EXISTS candidate_works_by_dedup_key ON candidate_works(work_dedup_key);
CREATE INDEX IF NOT EXISTS candidate_works_by_run ON candidate_works(discovery_run_id);

CREATE TABLE IF NOT EXISTS candidate_images (
    id                   TEXT PRIMARY KEY,
    candidate_work_id    TEXT NOT NULL REFERENCES candidate_works(id),
    url                  TEXT NOT NULL,
    preview_url          TEXT,
    preview_path         TEXT,
    provider             TEXT NOT NULL,
    source_class         TEXT NOT NULL,
    acquisition_method   TEXT NOT NULL,
    estimated_width      INTEGER,
    estimated_height     INTEGER,
    rights_status        TEXT,
    confidence           REAL NOT NULL,
    quality_score        REAL,
    selection_rationale  TEXT,
    is_selected          INTEGER NOT NULL,
    rejected_at          TEXT
);

CREATE INDEX IF NOT EXISTS candidate_images_by_work ON candidate_images(candidate_work_id);

-- Which instance a work is represented by is a single fact about the work.
CREATE UNIQUE INDEX IF NOT EXISTS candidate_images_one_selected
    ON candidate_images(candidate_work_id) WHERE is_selected = 1;

-- What the curator has reacted to, and how. Retained, and consulted when
-- discovery proposes.
CREATE TABLE IF NOT EXISTS affinities (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    -- The thing itself as it was named, and a string rather than a foreign key.
    -- The artists the curator reacts to are often ones they could not
    -- have named, so the common case at the moment a judgment is written is a
    -- name with no row in this catalogue at all.
    value          TEXT NOT NULL,
    sentiment      TEXT NOT NULL,
    -- Independent of `sentiment`, because one scalar is a bug: "meh on Magritte,
    -- but open to learning more" is two facts, and collapsing them silently
    -- blacklists an artist the curator asked to keep hearing about.
    open_to_more   INTEGER NOT NULL,
    derivation     TEXT NOT NULL,
    -- Required by the write path for `inferred` and `observed`, and NOT NULL
    -- here would say the same thing wrongly: it is a rule about which
    -- derivations need evidence, not about the column.
    rationale      TEXT,
    artist_id      TEXT REFERENCES artists(id),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

-- One live judgment per thing, corrected in place. An index rather than a table
-- constraint because `CREATE UNIQUE INDEX IF NOT EXISTS` reaches a file written
-- before it and a column clause does not.
CREATE UNIQUE INDEX IF NOT EXISTS affinities_one_per_thing ON affinities(kind, value);

CREATE TABLE IF NOT EXISTS spend_records (
    id                TEXT PRIMARY KEY,
    discovery_run_id  TEXT REFERENCES discovery_runs(id),
    artwork_id        TEXT REFERENCES artworks(id),
    category          TEXT NOT NULL,
    model_id          TEXT,
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    units             INTEGER,
    -- Decimal text rather than a REAL. This column is money, and SQLite's only
    -- numeric types are integers and IEEE doubles.
    cost_usd          TEXT NOT NULL,
    occurred_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS spend_records_by_time ON spend_records(occurred_at);
CREATE INDEX IF NOT EXISTS spend_records_by_run ON spend_records(discovery_run_id);
-- Which works a resolve run covers. Rows are never deleted: coverage records a
-- fact about the run's scope, which does not change when the run's status does,
-- and the history of earlier resolve attempts is worth keeping.
CREATE TABLE IF NOT EXISTS resolve_run_works (
    resolve_run_id     TEXT NOT NULL REFERENCES discovery_runs(id),
    candidate_work_id  TEXT NOT NULL REFERENCES candidate_works(id),
    PRIMARY KEY (resolve_run_id, candidate_work_id)
);

CREATE INDEX IF NOT EXISTS resolve_run_works_by_work ON resolve_run_works(candidate_work_id);

-- Pages about a work that no installed plugin reads (`Sighting`). A new table, so
-- `CREATE TABLE IF NOT EXISTS` reaches a file written before it. Keyed by the
-- item and the page together: the same page found again is the same sighting.
-- Not tied to a candidate work, because a work is one item across every run that
-- proposed it; rows are never deleted, since a page seen stays seen.
CREATE TABLE IF NOT EXISTS sightings (
    wikidata_qid  TEXT NOT NULL,
    url           TEXT NOT NULL,
    PRIMARY KEY (wikidata_qid, url)
);

-- The pages a run's phase-1 web search read, in the search's order. Phase 2 hands
-- them to the finders, on approval, on a re-search and after a restart alike, so
-- they are stored rather than held in memory. A new table, so `CREATE TABLE IF
-- NOT EXISTS` reaches a file written before it; a run from before it simply has
-- none. Written once, when phase 1 closes, and never changed.
CREATE TABLE IF NOT EXISTS run_citations (
    discovery_run_id  TEXT NOT NULL REFERENCES discovery_runs(id),
    url               TEXT NOT NULL,
    position          INTEGER NOT NULL,
    PRIMARY KEY (discovery_run_id, url)
);
"""

#: The join's own key. A work appears at most once per resolve run.
_COVERAGE_KEY: Final[tuple[str, ...]] = ("resolve_run_id", "candidate_work_id")

#: The table's own key: one row per page per item.
_SIGHTING_KEY: Final[tuple[str, ...]] = ("wikidata_qid", "url")

#: One row per page per run: a search that cited a page twice read it once.
_CITATION_KEY: Final[tuple[str, ...]] = ("discovery_run_id", "url")

#: Newest first: a run list is a history, and the run someone is asking about is
#: almost always the last one.
_BY_START: Final[tuple[OrderBy, ...]] = (OrderBy("started_at", descending=True), OrderBy("id"))

#: What a curator scans by, then a tie-break that makes the order repeatable.
_BY_TITLE: Final[tuple[OrderBy, ...]] = (OrderBy("proposed_title", ignore_case=True), OrderBy("id"))

#: The chosen instance leads where one exists. Rejected instances keep their place
#: in this order rather than sorting last, so a surface that caps this list decides
#: for itself which rows a curator can still act on — see `library/services/review.py`.
_BY_SELECTION: Final[tuple[OrderBy, ...]] = (
    OrderBy("is_selected", descending=True),
    OrderBy("confidence", descending=True),
    OrderBy("id"),
)

#: Newest first, because spend is read as a history and as a running total.
_BY_OCCURRENCE: Final[tuple[OrderBy, ...]] = (OrderBy("occurred_at", descending=True), OrderBy("id"))

#: A join with no fields of its own; the key is the only stable order it has.
_BY_COVERAGE: Final[tuple[OrderBy, ...]] = (OrderBy("resolve_run_id"), OrderBy("candidate_work_id"))

#: Taste reads as a list a curator scans for a name, so it is ordered by the
#: name — grouped by kind first, because the screen groups by kind and an order
#: the screen has to re-impose is an order that can disagree with it.
_BY_THING: Final[tuple[OrderBy, ...]] = (OrderBy("kind"), OrderBy("value", ignore_case=True), OrderBy("id"))


class SqliteDiscovery(TableAdapter):
    """The pre-acceptance pipeline, persisted alongside the catalogue."""

    # -- runs -----------------------------------------------------------------

    def add_run(self, run: DiscoveryRun) -> None:
        self._add("discovery_runs", _run_row(run), subject=f"discovery run {run.id!r}")

    def get_run(self, run_id: str) -> DiscoveryRun | None:
        return self._get("discovery_runs", {"id": run_id}, _run)

    def update_run(self, run: DiscoveryRun) -> None:
        self._update("discovery_runs", BY_ID, _run_row(run), subject=f"discovery run {run.id!r}")

    def list_runs(self, *, status: RunStatus | None = None, kind: RunKind | None = None) -> Sequence[DiscoveryRun]:
        filters: dict[str, Any] = {}
        if status is not None:
            filters["status"] = str(status)
        if kind is not None:
            filters["kind"] = str(kind)
        return self._list("discovery_runs", filters or None, _BY_START, _run)

    # -- candidate works ------------------------------------------------------

    def add_candidate_work(self, work: CandidateWork) -> None:
        self._add("candidate_works", _candidate_work_row(work), subject=f"candidate work {work.id!r}")

    def get_candidate_work(self, candidate_work_id: str) -> CandidateWork | None:
        return self._get("candidate_works", {"id": candidate_work_id}, _candidate_work)

    def update_candidate_work(self, work: CandidateWork) -> None:
        self._update("candidate_works", BY_ID, _candidate_work_row(work), subject=f"candidate work {work.id!r}")

    def list_candidate_works(self, run_id: str) -> Sequence[CandidateWork]:
        return self._list("candidate_works", {"discovery_run_id": run_id}, _BY_TITLE, _candidate_work)

    def list_works_awaiting_verdict(self) -> Sequence[CandidateWork]:
        return self._list(
            "candidate_works",
            {"verdict": str(Verdict.PENDING), "resolution_status": str(ResolutionStatus.RESOLVED)},
            _BY_TITLE,
            _candidate_work,
        )

    def list_wanted_works(self) -> Sequence[CandidateWork]:
        return self._list("candidate_works", {"verdict": str(Verdict.WANTED)}, _BY_TITLE, _candidate_work)

    def list_candidate_works_by_dedup_key(self, work_dedup_key: str) -> Sequence[CandidateWork]:
        return self._list("candidate_works", {"work_dedup_key": work_dedup_key}, _BY_TITLE, _candidate_work)

    def destinations_of_artworks(self, artwork_ids: Sequence[str]) -> Mapping[str, str]:
        found: dict[str, str] = {}
        wanted = list(dict.fromkeys(artwork_ids))
        # In slices, because the catch-up at start may ask about every work the
        # catalogue holds and SQLite bounds how many values one statement binds.
        for start in range(0, len(wanted), _IDS_PER_STATEMENT):
            chunk = wanted[start : start + _IDS_PER_STATEMENT]
            rows = self._store.select_rows(
                'SELECT cw."artwork_id" AS artwork_id, r."destination_theme_id" AS theme_id '  # noqa: S608 -- constants and ? placeholders only
                'FROM candidate_works cw JOIN discovery_runs r ON r."id" = cw."discovery_run_id" '
                f'WHERE r."destination_theme_id" IS NOT NULL AND cw."artwork_id" IN ({", ".join("?" * len(chunk))})',
                chunk,
            )
            found.update({row["artwork_id"]: row["theme_id"] for row in rows})
        return found

    def source_yields(self) -> Mapping[str, SourceYield]:
        rows = self._store.select_rows(_SOURCE_YIELDS)
        return {
            row["provider"]: SourceYield(
                provider=row["provider"],
                offered=row["offered"],
                chosen=row["chosen"],
                only_here=row["only_here"],
                median_long_edge=None if row["median_long_edge"] is None else round(row["median_long_edge"]),
            )
            for row in rows
        }

    # -- candidate images -----------------------------------------------------

    def add_candidate_image(self, image: CandidateImage) -> None:
        self._add("candidate_images", _candidate_image_row(image), subject=f"candidate image {image.id!r}")

    def get_candidate_image(self, candidate_image_id: str) -> CandidateImage | None:
        return self._get("candidate_images", {"id": candidate_image_id}, _candidate_image)

    def update_candidate_image(self, image: CandidateImage) -> None:
        self._update("candidate_images", BY_ID, _candidate_image_row(image), subject=f"candidate image {image.id!r}")

    def list_candidate_images(self, candidate_work_id: str) -> Sequence[CandidateImage]:
        return self._list("candidate_images", {"candidate_work_id": candidate_work_id}, _BY_SELECTION, _candidate_image)

    # -- affinities -----------------------------------------------------------

    def add_affinity(self, affinity: Affinity) -> None:
        self._add("affinities", _affinity_row(affinity), subject=f"affinity {affinity.kind}/{affinity.value!r}")

    def get_affinity(self, affinity_id: str) -> Affinity | None:
        return self._get("affinities", {"id": affinity_id}, _affinity)

    def find_affinity(self, *, kind: VocabularyKind, value: str) -> Affinity | None:
        """The one live judgment about this thing, by the handle a caller has.

        (`kind`, `value`) rather than an id, because the thing being judged is a
        name in a sentence rather than a row anybody fetched — which is what makes
        the write an upsert.
        """
        found = self._list("affinities", {"kind": str(kind), "value": value}, _BY_THING, _affinity)
        return found[0] if found else None

    def update_affinity(self, affinity: Affinity) -> None:
        self._update("affinities", BY_ID, _affinity_row(affinity), subject=f"affinity {affinity.id!r}")

    def delete_affinity(self, affinity_id: str) -> None:
        self._delete("affinities", {"id": affinity_id})

    def list_affinities(
        self,
        *,
        kind: VocabularyKind | None = None,
        sentiment: AffinitySentiment | None = None,
        derivation: AffinityDerivation | None = None,
    ) -> Sequence[Affinity]:
        """Every matching judgment, grouped by kind and then by name."""
        filters: dict[str, Any] = {}
        if kind is not None:
            filters["kind"] = str(kind)
        if sentiment is not None:
            filters["sentiment"] = str(sentiment)
        if derivation is not None:
            filters["derivation"] = str(derivation)
        return self._list("affinities", filters or None, _BY_THING, _affinity)

    # -- spend ----------------------------------------------------------------

    def add_spend_record(self, record: SpendRecord) -> None:
        self._add("spend_records", _spend_row(record), subject=f"spend record {record.id!r}")

    def list_spend_records(
        self,
        *,
        run_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[SpendRecord]:
        """Return matching costs newest first, `since` inclusive and `until` exclusive.

        The window is applied here rather than in SQL because the durable store's
        contract is equality filters and a deterministic order, deliberately — it
        is the shape a collection layer can sit on. A household's spend table
        holds a few hundred rows a year, so narrowing the read is not worth
        widening that contract; the day it is, this method is where the change
        lands and no caller sees it.
        """
        filters: dict[str, Any] = {}
        if run_id is not None:
            filters["discovery_run_id"] = run_id
        records = self._list("spend_records", filters or None, _BY_OCCURRENCE, _spend)
        return [
            record
            for record in records
            if (since is None or record.occurred_at >= since) and (until is None or record.occurred_at < until)
        ]

    # -- resolve-run coverage -------------------------------------------------

    def add_coverage(self, coverage: ResolveRunWork) -> None:
        self._add(
            "resolve_run_works",
            _coverage_row(coverage),
            subject=f"candidate work {coverage.candidate_work_id!r} on resolve run {coverage.resolve_run_id!r}",
            key=_COVERAGE_KEY,
        )

    def list_coverage_by_run(self, resolve_run_id: str) -> Sequence[ResolveRunWork]:
        return self._list("resolve_run_works", {"resolve_run_id": resolve_run_id}, _BY_COVERAGE, _coverage)

    def list_coverage_by_work(self, candidate_work_id: str) -> Sequence[ResolveRunWork]:
        return self._list("resolve_run_works", {"candidate_work_id": candidate_work_id}, _BY_COVERAGE, _coverage)

    # -- sightings --------------------------------------------------------------

    def add_sighting(self, sighting: Sighting) -> bool:
        row = {"wikidata_qid": sighting.wikidata_qid, "url": sighting.url}
        return self._store.upsert("sightings", row, pk=_SIGHTING_KEY, on_conflict="ignore") == 1

    def list_open_sightings(self) -> Sequence[Sighting]:
        rows = self._store.select_rows(
            'SELECT s."wikidata_qid" AS wikidata_qid, s."url" AS url FROM sightings s WHERE s."wikidata_qid" IN '
            '(SELECT cw."wikidata_qid" FROM candidate_works cw WHERE cw."verdict" = ? '
            'OR (cw."resolution_status" = ? AND cw."verdict" = ?)) ORDER BY s."wikidata_qid", s."url"',
            (str(Verdict.WANTED), str(ResolutionStatus.UNRESOLVED), str(Verdict.PENDING)),
        )
        return [Sighting(wikidata_qid=row["wikidata_qid"], url=row["url"]) for row in rows]

    # -- citations --------------------------------------------------------------

    def add_run_citations(self, run_id: str, urls: Sequence[str]) -> None:
        for position, url in enumerate(urls):
            row = {"discovery_run_id": run_id, "url": url, "position": position}
            self._store.upsert("run_citations", row, pk=_CITATION_KEY, on_conflict="ignore")

    def list_run_citations(self, run_id: str) -> Sequence[str]:
        rows = self._store.select_rows(
            'SELECT "url" FROM run_citations WHERE "discovery_run_id" = ? ORDER BY "position"', (run_id,)
        )
        return [row["url"] for row in rows]


# -- record to row ------------------------------------------------------------


def _run_row(run: DiscoveryRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "kind": str(run.kind),
        "parent_run_id": run.parent_run_id,
        "intent_text": run.intent_text,
        "strategy": run.strategy,
        "initiated_by": str(run.initiated_by),
        "status": str(run.status),
        "estimated_cost_usd": to_money(run.estimated_cost_usd),
        "actual_cost_usd": to_money(run.actual_cost_usd),
        "approval_required": int(run.approval_required),
        "unresolved_work_count": run.unresolved_work_count,
        "started_at": to_iso(run.started_at),
        "completed_at": to_iso(run.completed_at),
        "destination_theme_id": run.destination_theme_id,
        "end_reason": run.end_reason,
    }


def _candidate_work_row(work: CandidateWork) -> dict[str, Any]:
    return {
        "id": work.id,
        "discovery_run_id": work.discovery_run_id,
        "artwork_id": work.artwork_id,
        "proposed_title": work.proposed_title,
        "proposed_artist": work.proposed_artist,
        "rationale": work.rationale,
        "work_dedup_key": work.work_dedup_key,
        "provenance": str(work.provenance),
        "offered_for_artist": work.offered_for_artist,
        "offered_artist_matched": work.offered_artist_matched,
        "offered_by": work.offered_by,
        "wikidata_qid": work.wikidata_qid,
        "source_confirmed": None if work.source_confirmed is None else int(work.source_confirmed),
        "resolution_status": str(work.resolution_status),
        "unresolved_reason": str(work.unresolved_reason) if work.unresolved_reason else None,
        "verdict": str(work.verdict),
        "rejected_reason": work.rejected_reason,
        "decided_at": to_iso(work.decided_at),
    }


def _candidate_image_row(image: CandidateImage) -> dict[str, Any]:
    return {
        "id": image.id,
        "candidate_work_id": image.candidate_work_id,
        "url": image.url,
        "preview_url": image.preview_url,
        "preview_path": image.preview_path,
        "provider": image.provider,
        "source_class": str(image.source_class),
        "acquisition_method": str(image.acquisition_method),
        "estimated_width": image.estimated_width,
        "estimated_height": image.estimated_height,
        "rights_status": None if image.rights_status is None else str(image.rights_status),
        "confidence": image.confidence,
        "quality_score": image.quality_score,
        "selection_rationale": image.selection_rationale,
        "is_selected": int(image.is_selected),
        "rejected_at": to_iso(image.rejected_at),
    }


def _spend_row(record: SpendRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "discovery_run_id": record.discovery_run_id,
        "artwork_id": record.artwork_id,
        "category": str(record.category),
        "model_id": record.model_id,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "units": record.units,
        "cost_usd": to_money(record.cost_usd),
        "occurred_at": to_iso(record.occurred_at),
    }


def _affinity_row(affinity: Affinity) -> dict[str, Any]:
    return {
        "id": affinity.id,
        "kind": str(affinity.kind),
        "value": affinity.value,
        "sentiment": str(affinity.sentiment),
        "open_to_more": int(affinity.open_to_more),
        "derivation": str(affinity.derivation),
        "rationale": affinity.rationale,
        "artist_id": affinity.artist_id,
        "created_at": to_iso(affinity.created_at),
        "updated_at": to_iso(affinity.updated_at),
    }


def _coverage_row(coverage: ResolveRunWork) -> dict[str, Any]:
    return {"resolve_run_id": coverage.resolve_run_id, "candidate_work_id": coverage.candidate_work_id}


# -- row to record ------------------------------------------------------------


def _run(row: Mapping[str, Any]) -> DiscoveryRun:
    return DiscoveryRun(
        id=row["id"],
        kind=RunKind(row["kind"]),
        initiated_by=InitiatedBy(row["initiated_by"]),
        status=RunStatus(row["status"]),
        approval_required=bool(row["approval_required"]),
        started_at=require_datetime(row["started_at"], "started_at"),
        parent_run_id=row["parent_run_id"],
        intent_text=row["intent_text"],
        strategy=row["strategy"],
        estimated_cost_usd=from_money(row["estimated_cost_usd"]),
        actual_cost_usd=from_money(row["actual_cost_usd"]),
        unresolved_work_count=row["unresolved_work_count"],
        completed_at=from_iso(row["completed_at"]),
        destination_theme_id=row["destination_theme_id"],
        end_reason=row["end_reason"],
    )


def _candidate_work(row: Mapping[str, Any]) -> CandidateWork:
    return CandidateWork(
        id=row["id"],
        discovery_run_id=row["discovery_run_id"],
        proposed_title=row["proposed_title"],
        rationale=row["rationale"],
        work_dedup_key=row["work_dedup_key"],
        # A row written before the column existed is a work phase 1 proposed —
        # nothing else could write one — so the absent value has a single honest
        # reading rather than being a third state.
        provenance=WorkProvenance(row["provenance"]) if row["provenance"] else WorkProvenance.PROPOSED,
        # Absent on every row written before offered works carried their query,
        # and absent for ever on proposed works. `None` is the honest reading in
        # both cases — no query produced them — so no default is invented here.
        offered_for_artist=row["offered_for_artist"],
        offered_artist_matched=row["offered_artist_matched"],
        offered_by=row["offered_by"],
        wikidata_qid=row["wikidata_qid"],
        source_confirmed=None if row["source_confirmed"] is None else bool(row["source_confirmed"]),
        resolution_status=ResolutionStatus(row["resolution_status"]),
        unresolved_reason=UnresolvedReason(row["unresolved_reason"]) if row["unresolved_reason"] else None,
        verdict=Verdict(row["verdict"]),
        artwork_id=row["artwork_id"],
        proposed_artist=row["proposed_artist"],
        rejected_reason=row["rejected_reason"],
        decided_at=from_iso(row["decided_at"]),
    )


def _candidate_image(row: Mapping[str, Any]) -> CandidateImage:
    return CandidateImage(
        id=row["id"],
        candidate_work_id=row["candidate_work_id"],
        url=row["url"],
        provider=row["provider"],
        source_class=SourceClass(row["source_class"]),
        acquisition_method=AcquisitionMethod(row["acquisition_method"]),
        confidence=row["confidence"],
        is_selected=bool(row["is_selected"]),
        preview_url=row["preview_url"],
        preview_path=row["preview_path"],
        estimated_width=row["estimated_width"],
        estimated_height=row["estimated_height"],
        rights_status=None if row["rights_status"] is None else RightsStatus(row["rights_status"]),
        quality_score=row["quality_score"],
        selection_rationale=row["selection_rationale"],
        rejected_at=from_iso(row["rejected_at"]),
    )


def _spend(row: Mapping[str, Any]) -> SpendRecord:
    return SpendRecord(
        id=row["id"],
        category=SpendCategory(row["category"]),
        cost_usd=require_money(row["cost_usd"], "cost_usd"),
        occurred_at=require_datetime(row["occurred_at"], "occurred_at"),
        discovery_run_id=row["discovery_run_id"],
        artwork_id=row["artwork_id"],
        model_id=row["model_id"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        units=row["units"],
    )


def _affinity(row: Mapping[str, Any]) -> Affinity:
    return Affinity(
        id=row["id"],
        kind=VocabularyKind(row["kind"]),
        value=row["value"],
        sentiment=AffinitySentiment(row["sentiment"]),
        open_to_more=bool(row["open_to_more"]),
        derivation=AffinityDerivation(row["derivation"]),
        created_at=require_datetime(row["created_at"], "created_at"),
        updated_at=require_datetime(row["updated_at"], "updated_at"),
        rationale=row["rationale"],
        artist_id=row["artist_id"],
    )


def _coverage(row: Mapping[str, Any]) -> ResolveRunWork:
    return ResolveRunWork(resolve_run_id=row["resolve_run_id"], candidate_work_id=row["candidate_work_id"])
