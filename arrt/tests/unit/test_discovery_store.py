"""The pipeline's half of the file: its schema, its round trip, its own indexes.

The service tests above cover the rules. These cover the file, because a rule
enforced perfectly against records that do not survive being written and read
back is a rule about nothing. The schema is asserted column by column for the
same reason the catalogue's is: a mapping change shows up one column at a time,
and the backup path restores whatever the file actually holds.
"""

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from arrt.persistence.catalogue import StorageError
from arrt.persistence.discovery_records import (
    SEARCHES_COUNTED,
    CandidateImage,
    CandidateWork,
    Confirmation,
    CostStatus,
    DiscoveryRun,
    InitiatedBy,
    ResolutionStatus,
    ResolveRunWork,
    RunKind,
    RunStatus,
    SearchOutcome,
    SearchTally,
    SourceSearch,
    SpendCategory,
    SpendRecord,
    Verdict,
    WorkProvenance,
)
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass
from arrt.persistence.sqlite_discovery import _SEARCH_TALLIES, DISCOVERY_SCHEMA, SqliteDiscovery

_EXPECTED_SCHEMA = {
    "discovery_runs": {
        "id",
        "kind",
        "parent_run_id",
        "intent_text",
        "strategy",
        "initiated_by",
        "status",
        "estimated_cost_usd",
        "actual_cost_usd",
        "approval_required",
        "unresolved_work_count",
        "started_at",
        "completed_at",
        "destination_theme_id",
        "end_reason",
        "watch_id",
    },
    "candidate_works": {
        "id",
        "discovery_run_id",
        "artwork_id",
        "proposed_title",
        "proposed_artist",
        "rationale",
        "work_dedup_key",
        "provenance",
        "offered_for_artist",
        "offered_artist_matched",
        "offered_by",
        "wikidata_qid",
        "source_confirmed",
        "resolution_status",
        "unresolved_reason",
        "verdict",
        "rejected_reason",
        "decided_at",
    },
    "candidate_images": {
        "id",
        "candidate_work_id",
        "url",
        "preview_url",
        "preview_path",
        "provider",
        "source_class",
        "acquisition_method",
        "estimated_width",
        "estimated_height",
        "rights_status",
        "confidence",
        "quality_score",
        "selection_rationale",
        "is_selected",
        "rejected_at",
    },
    "spend_records": {
        "id",
        "discovery_run_id",
        "artwork_id",
        "category",
        "model_id",
        "input_tokens",
        "output_tokens",
        "units",
        "cost_usd",
        "occurred_at",
        # Widened 2026-11-19: whether cost_usd is the provider's figure or a
        # call sent that never said.
        "cost_status",
    },
    "affinities": {
        "id",
        "kind",
        "value",
        "sentiment",
        "open_to_more",
        "derivation",
        "rationale",
        "artist_id",
        "created_at",
        "updated_at",
    },
    "settings": {"key", "value", "updated_at", "updated_by"},
    # Added 2026-11-20: the newest search of each work at each source. A new table, so growth within the shape generation.
    "source_searches": {
        "candidate_work_id",
        "provider",
        "asked_at",
        "outcome",
        "answered_at",
        "images",
        "late",
    },
    "resolve_run_works": {"resolve_run_id", "candidate_work_id"},
    "sightings": {"wikidata_qid", "url"},
    "run_citations": {"discovery_run_id", "url", "position"},
    "watches": {
        "id",
        "intent_text",
        "enabled",
        "cadence",
        "monthly_cap_usd",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "last_attempt_at",
        "last_run_id",
        "last_refusal",
    },
}

_STARTED = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)
_FINISHED = datetime(2026, 7, 27, 9, 44, 12, tzinfo=UTC)


def _run(**fields) -> DiscoveryRun:
    return DiscoveryRun(
        id=fields.pop("id", "r1"),
        kind=fields.pop("kind", RunKind.DISCOVERY),
        initiated_by=fields.pop("initiated_by", InitiatedBy.MCP_CLIENT),
        status=fields.pop("status", RunStatus.RESOLVING_WORKS),
        approval_required=fields.pop("approval_required", False),
        started_at=fields.pop("started_at", _STARTED),
        **fields,
    )


def _work(**fields) -> CandidateWork:
    return CandidateWork(
        id=fields.pop("id", "c1"),
        discovery_run_id=fields.pop("discovery_run_id", "r1"),
        proposed_title=fields.pop("proposed_title", "The Persistence of Memory"),
        rationale=fields.pop("rationale", "The best-known Surrealist painting."),
        work_dedup_key=fields.pop("work_dedup_key", "dali::persistence-of-memory"),
        **fields,
    )


def _image(**fields) -> CandidateImage:
    return CandidateImage(
        id=fields.pop("id", "i1"),
        candidate_work_id=fields.pop("candidate_work_id", "c1"),
        url=fields.pop("url", "https://moma.example/79018"),
        provider=fields.pop("provider", "moma"),
        source_class=fields.pop("source_class", SourceClass.INSTITUTIONAL),
        acquisition_method=fields.pop("acquisition_method", AcquisitionMethod.DEZOOMIFY),
        confidence=fields.pop("confidence", 0.97),
        **fields,
    )


def _tables_made_by(schema: str) -> set[str]:
    """The tables a schema the code declares creates, read from SQLite running it rather than from its text."""
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(schema)
        return {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()


def test_the_file_carries_the_schema_the_backup_path_expects(tmp_path):
    """Every table `DISCOVERY_SCHEMA` makes is pinned, column for column, and none is pinned that the file lacks.

    **Exact, in the form `test_catalogue_store.py` takes.** Which tables are the pipeline's is
    asked of SQLite running
    `DISCOVERY_SCHEMA`, never listed here, and the file a store opened is what
    holds them. A subset check (`_EXPECTED_SCHEMA.keys() <= tables`) would pass tables
    nobody had listed, so a table could
    arrive with no one answering the migration question for it. The catalogue's own
    tables are `test_catalogue_store.py`'s.
    """
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()

    connection = sqlite3.connect(path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        held = tables & _tables_made_by(DISCOVERY_SCHEMA)
        unlisted = sorted(held - _EXPECTED_SCHEMA.keys())
        assert unlisted == [], f"the file holds pipeline tables _EXPECTED_SCHEMA does not list; add an entry for each: {unlisted}"
        missing = sorted(_EXPECTED_SCHEMA.keys() - held)
        assert missing == [], f"_EXPECTED_SCHEMA lists tables the pipeline's schema does not make in the file: {missing}"
        differing = {
            table: {"unlisted": sorted(found - columns), "missing": sorted(columns - found)}
            for table, columns in _EXPECTED_SCHEMA.items()
            if (found := {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}) != columns
        }
        assert differing == {}, f"columns differ from _EXPECTED_SCHEMA (list the unlisted; explain the missing): {differing}"
    finally:
        connection.close()


# -- the search record ------------------------------------------------------------


def _search(**fields) -> SourceSearch:
    return SourceSearch(
        candidate_work_id=fields.pop("candidate_work_id", "c1"),
        provider=fields.pop("provider", "moma"),
        asked_at=fields.pop("asked_at", _STARTED),
        outcome=fields.pop("outcome", SearchOutcome.ANSWERED),
        **fields,
    )


def test_the_search_record_holds_no_address(tmp_path):
    """Keyed by the work and the source's name (`data-model.md` § Direction): no column holds a URL.

    Read from the file's own description of the table, anchored on the columns
    that are there, so an empty table cannot pass it.
    """
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    try:
        columns = {row[1]: row for row in connection.execute('PRAGMA table_info("source_searches")')}
        key = sorted((row[5], name) for name, row in columns.items() if row[5])
    finally:
        connection.close()

    assert key == [(1, "candidate_work_id"), (2, "provider")]
    assert [name for name in columns if "url" in name.lower() or "address" in name.lower() or "page" in name.lower()] == []


def test_two_searches_of_one_work_at_one_source_leave_one_row_the_newer(discovery_store, quiet_catalogue_file):
    discovery_store.add_run(_run())
    discovery_store.add_candidate_work(_work())
    later = _STARTED + timedelta(days=1)

    discovery_store.record_search(_search(outcome=SearchOutcome.OWED))
    discovery_store.record_search(_search(asked_at=later, outcome=SearchOutcome.ANSWERED, answered_at=later, images=3, late=True))
    discovery_store.record_search(_search(provider="tate", outcome=SearchOutcome.UNREACHABLE))

    assert discovery_store.searches_of("c1") == {
        "moma": _search(asked_at=later, outcome=SearchOutcome.ANSWERED, answered_at=later, images=3, late=True),
        "tate": _search(provider="tate", outcome=SearchOutcome.UNREACHABLE),
    }
    assert len(quiet_catalogue_file.select_rows("SELECT * FROM source_searches")) == 2


def test_a_search_of_a_work_the_file_does_not_hold_is_refused(discovery_store):
    with pytest.raises(StorageError):
        discovery_store.record_search(_search(candidate_work_id="nobody"))


def test_each_sources_searches_are_counted_by_what_it_said_and_survive_the_process(tmp_path):
    """What Status reads after a restart: counted from the record, one row per source, an answer of any kind counted."""
    path = tmp_path / "catalogue.sqlite"
    writer = SqliteDiscovery(open_catalogue_file(path))
    writer.add_run(_run())
    said = {
        "c1": SearchOutcome.ANSWERED,
        "c2": SearchOutcome.DECLINED,
        "c3": SearchOutcome.LINK_GONE,
        "c4": SearchOutcome.UNREACHABLE,
        "c5": SearchOutcome.UNREACHABLE,
        "c6": SearchOutcome.OWED,
    }
    for n, (work_id, outcome) in enumerate(said.items()):
        writer.add_candidate_work(_work(id=work_id, work_dedup_key=f"k{work_id}"))
        answered = None if outcome in (SearchOutcome.OWED, SearchOutcome.UNREACHABLE) else _STARTED + timedelta(minutes=n)
        writer.record_search(
            _search(candidate_work_id=work_id, asked_at=_STARTED + timedelta(minutes=n), outcome=outcome, answered_at=answered)
        )
    writer.record_search(_search(candidate_work_id="c1", provider="tate", outcome=SearchOutcome.UNREACHABLE))
    writer.close()

    reader = SqliteDiscovery(open_catalogue_file(path))
    try:
        assert reader.search_tallies(["moma", "tate", "never-asked"]) == {
            "moma": SearchTally(
                provider="moma",
                searched=6,
                answered=3,
                unasked=2,
                owed=1,
                last_answered_at=_STARTED + timedelta(minutes=2),
                last_asked_at=_STARTED + timedelta(minutes=5),
                # Each answered the moment it was asked, with no image.
                with_images=0,
                median_latency_seconds=0.0,
            ),
            "tate": SearchTally(
                provider="tate", searched=1, answered=0, unasked=1, owed=0, last_answered_at=None, last_asked_at=_STARTED
            ),
        }
    finally:
        reader.close()


def test_the_count_status_reads_reads_the_index_and_never_the_rows(quiet_catalogue_file):
    """Status reads `search_tallies` on every page, so its own statement is planned as a search of a covering index.

    A search by the source, read in the index's order: no table scan, and no sort.
    """
    plan = quiet_catalogue_file.select_rows("EXPLAIN QUERY PLAN " + _SEARCH_TALLIES, ("moma", SEARCHES_COUNTED))
    details = " ".join(row["detail"] for row in plan)

    assert "SEARCH source_searches USING COVERING INDEX source_searches_counted (provider=?)" in details, plan
    assert "TEMP B-TREE" not in details, plan


def test_a_file_written_with_the_index_before_images_is_read_through_the_index_that_holds_them(tmp_path):
    """A catalogue from before the hit rate carries `source_searches_by_provider`, which lacks `images`.

    Opened by this release, the older index is gone and the one that covers the
    hit rate is there, so Status still reads index entries and never the rows.
    """
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX source_searches_counted")
        connection.execute(
            "CREATE INDEX source_searches_by_provider ON source_searches(provider, asked_at, outcome, answered_at)"
        )

    reopened = open_catalogue_file(path)
    try:
        listed = "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'source_searches'"
        indexes = {row["name"] for row in reopened.select_rows(listed)}
        plan = reopened.select_rows("EXPLAIN QUERY PLAN " + _SEARCH_TALLIES, ("moma", SEARCHES_COUNTED))
    finally:
        reopened.close()

    assert "source_searches_counted" in indexes, indexes
    assert "source_searches_by_provider" not in indexes, indexes
    assert "USING COVERING INDEX source_searches_counted" in " ".join(row["detail"] for row in plan), plan


def _seed_the_three_columns_case(store: SqliteDiscovery) -> None:
    """Three works answered with images, one answered with none, one still owed; the answers took 2, 4, 10 and 30 s.

    The answer with no image is the slowest, so a median taken over the works
    with images alone (2, 4 and 10: 4 s) and one over every answer (2, 4, 10
    and 30: 7 s) differ, as do a hit rate over the searches (3 of 5) and over
    the answers (3 of 4).
    """
    store.add_run(_run())
    said = [(2, 3), (10, 1), (4, 6), (30, 0)]
    for n, (seconds, images) in enumerate(said):
        store.add_candidate_work(_work(id=f"c{n}", work_dedup_key=f"k{n}"))
        asked = _STARTED + timedelta(minutes=n)
        store.record_search(
            _search(
                candidate_work_id=f"c{n}",
                asked_at=asked,
                outcome=SearchOutcome.ANSWERED,
                answered_at=asked + timedelta(seconds=seconds),
                images=images,
            )
        )
    store.add_candidate_work(_work(id="c9", work_dedup_key="k9"))
    store.record_search(_search(candidate_work_id="c9", asked_at=_STARTED + timedelta(minutes=9), outcome=SearchOutcome.OWED))


def test_a_sources_hit_rate_is_over_what_it_answered_and_its_latency_is_the_median_of_its_answers(discovery_store):
    """Status's three columns: Searches 5, Hit rate 3 of 4, Median latency 7 s (2, 4, 10, 30: the middle two's mean)."""
    _seed_the_three_columns_case(discovery_store)

    (tally,) = discovery_store.search_tallies(["moma"]).values()

    assert (tally.searched, tally.answered, tally.with_images, tally.owed) == (5, 4, 3, 1)
    assert tally.median_latency_seconds == 7.0


def test_the_three_columns_survive_the_process_that_wrote_them(tmp_path):
    """#313's "survive a restart": the figures are read from the record, so a reopened file gives the same."""
    path = tmp_path / "catalogue.sqlite"
    writer = SqliteDiscovery(open_catalogue_file(path))
    _seed_the_three_columns_case(writer)
    before = writer.search_tallies(["moma"])
    writer.close()

    reader = SqliteDiscovery(open_catalogue_file(path))
    try:
        after = reader.search_tallies(["moma"])
    finally:
        reader.close()

    assert after == before
    assert (after["moma"].searched, after["moma"].with_images, after["moma"].median_latency_seconds) == (5, 3, 7.0)


@pytest.mark.parametrize(
    ("latencies", "median"),
    [((5,), 5.0), ((1, 9), 5.0), ((1, 2, 60), 2.0), ((0.25, 0.5, 0.75, 120), 0.625)],
    ids=["one", "two", "three", "four"],
)
def test_the_median_latency_is_the_middle_answer_or_the_mean_of_the_middle_two(discovery_store, latencies, median):
    discovery_store.add_run(_run())
    for n, seconds in enumerate(latencies):
        discovery_store.add_candidate_work(_work(id=f"c{n}", work_dedup_key=f"k{n}"))
        asked = _STARTED + timedelta(minutes=n)
        discovery_store.record_search(
            _search(candidate_work_id=f"c{n}", asked_at=asked, answered_at=asked + timedelta(seconds=seconds), images=1)
        )

    (tally,) = discovery_store.search_tallies(["moma"]).values()

    assert tally.median_latency_seconds == median


def test_a_source_that_answered_nothing_has_no_latency_and_no_hit(discovery_store):
    """Only could-not-be-asked and owed: nothing answered, so Status reads "—" in both columns."""
    discovery_store.add_run(_run())
    for n, outcome in enumerate((SearchOutcome.UNREACHABLE, SearchOutcome.OWED)):
        discovery_store.add_candidate_work(_work(id=f"c{n}", work_dedup_key=f"k{n}"))
        asked = _STARTED + timedelta(minutes=n)
        # A could-not-be-asked answer is stamped when it came, as the pool writes
        # it: its time is not an answer's latency.
        answered = asked + timedelta(seconds=3) if outcome is SearchOutcome.UNREACHABLE else None
        discovery_store.record_search(
            _search(candidate_work_id=f"c{n}", asked_at=asked, outcome=outcome, answered_at=answered, images=0)
        )

    (tally,) = discovery_store.search_tallies(["moma"]).values()

    assert (tally.searched, tally.answered, tally.with_images, tally.median_latency_seconds) == (2, 0, 0, None)


def test_status_counts_a_sources_newest_searches_and_no_more(discovery_store):
    """Bounded by `SEARCHES_COUNTED`, the newest by when they were asked: an old outage is not this morning's."""
    discovery_store.add_run(_run())
    for n in range(SEARCHES_COUNTED + 2):
        discovery_store.add_candidate_work(_work(id=f"c{n}", work_dedup_key=f"k{n}"))
        # The two oldest could not be asked; every search since was answered.
        outcome = SearchOutcome.UNREACHABLE if n < 2 else SearchOutcome.ANSWERED
        asked = _STARTED + timedelta(minutes=n)
        discovery_store.record_search(_search(candidate_work_id=f"c{n}", asked_at=asked, outcome=outcome, answered_at=asked))

    (tally,) = discovery_store.search_tallies(["moma"]).values()

    assert (tally.searched, tally.answered, tally.unasked) == (SEARCHES_COUNTED, SEARCHES_COUNTED, 0)
    assert tally.last_asked_at == _STARTED + timedelta(minutes=SEARCHES_COUNTED + 1)


def test_the_pipeline_survives_the_process_that_wrote_it(tmp_path):
    """Every field, because a mapping change shows up one column at a time."""
    path = tmp_path / "catalogue.sqlite"
    first = open_catalogue_file(path)
    writer = SqliteDiscovery(first)
    writer.add_run(
        _run(
            strategy="Enumerate the artist's best-known works, then verify each.",
            intent_text="Surrealist paintings",
            estimated_cost_usd=Decimal("0.42"),
            actual_cost_usd=Decimal("0.3175"),
            unresolved_work_count=2,
            approval_required=True,
            status=RunStatus.COMPLETED,
            completed_at=_FINISHED,
        )
    )
    writer.add_run(_run(id="r2", kind=RunKind.RESOLVE, parent_run_id="r1", status=RunStatus.RESOLVING_IMAGES))
    writer.add_candidate_work(
        _work(
            proposed_artist="Salvador Dalí",
            resolution_status=ResolutionStatus.RESOLVED,
            verdict=Verdict.REJECTED,
            rejected_reason="Too well known.",
            decided_at=_FINISHED,
        )
    )
    writer.add_candidate_image(
        _image(
            preview_url="https://moma.example/79018/thumb.jpg",
            preview_path="api-cache/previews/79018.jpg",
            estimated_width=6000,
            estimated_height=4000,
            rights_status=RightsStatus.IN_COPYRIGHT,
            quality_score=0.81,
            selection_rationale="The museum's own plate.",
            is_selected=True,
            rejected_at=_FINISHED,
        )
    )
    writer.add_spend_record(
        SpendRecord(
            id="s1",
            category=SpendCategory.WEB_SEARCH,
            cost_usd=Decimal("0.0625"),
            occurred_at=_STARTED,
            discovery_run_id="r1",
            model_id="anthropic/claude-sonnet-4.5",
            input_tokens=1200,
            output_tokens=340,
            units=5,
        )
    )
    writer.add_coverage(ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1"))
    writer.add_run(_run(id="r3", kind=RunKind.GET, status=RunStatus.RESOLVING_IMAGES))
    writer.add_candidate_work(_work(id="c2", discovery_run_id="r3", provenance=WorkProvenance.CHOSEN, wikidata_qid="Q45585"))
    first.close()

    reopened = open_catalogue_file(path)
    try:
        store = SqliteDiscovery(reopened)

        run = store.get_run("r1")
        assert (run.kind, run.initiated_by, run.status) == (RunKind.DISCOVERY, InitiatedBy.MCP_CLIENT, RunStatus.COMPLETED)
        assert (run.intent_text, run.strategy) == (
            "Surrealist paintings",
            "Enumerate the artist's best-known works, then verify each.",
        )
        assert (run.estimated_cost_usd, run.actual_cost_usd) == (Decimal("0.42"), Decimal("0.3175"))
        assert (run.approval_required, run.unresolved_work_count) == (True, 2)
        assert (run.started_at, run.completed_at) == (_STARTED, _FINISHED)
        assert run.parent_run_id is None
        assert store.get_run("r2").parent_run_id == "r1"

        work = store.get_candidate_work("c1")
        assert (work.discovery_run_id, work.proposed_title, work.proposed_artist) == (
            "r1",
            "The Persistence of Memory",
            "Salvador Dalí",
        )
        assert (work.rationale, work.work_dedup_key) == ("The best-known Surrealist painting.", "dali::persistence-of-memory")
        assert (work.resolution_status, work.verdict) == (ResolutionStatus.RESOLVED, Verdict.REJECTED)
        assert (work.rejected_reason, work.decided_at, work.artwork_id) == ("Too well known.", _FINISHED, None)
        assert work.wikidata_qid is None, "a proposed work names no item"
        chosen = store.get_candidate_work("c2")
        assert (store.get_run("r3").kind, chosen.provenance, chosen.wikidata_qid) == (
            RunKind.GET,
            WorkProvenance.CHOSEN,
            "Q45585",
        )

        image = store.list_candidate_images("c1")[0]
        assert (image.url, image.provider, image.source_class) == (
            "https://moma.example/79018",
            "moma",
            SourceClass.INSTITUTIONAL,
        )
        assert image.acquisition_method is AcquisitionMethod.DEZOOMIFY
        assert (image.preview_url, image.preview_path) == ("https://moma.example/79018/thumb.jpg", "api-cache/previews/79018.jpg")
        assert (image.estimated_width, image.estimated_height) == (6000, 4000)
        assert (image.rights_status, image.confidence, image.quality_score) == (RightsStatus.IN_COPYRIGHT, 0.97, 0.81)
        assert (image.selection_rationale, image.is_selected, image.rejected_at) == ("The museum's own plate.", True, _FINISHED)

        spend = store.list_spend_records(run_id="r1")[0]
        assert (spend.category, spend.cost_usd, spend.occurred_at) == (SpendCategory.WEB_SEARCH, Decimal("0.0625"), _STARTED)
        assert (spend.model_id, spend.input_tokens, spend.output_tokens, spend.units) == (
            "anthropic/claude-sonnet-4.5",
            1200,
            340,
            5,
        )
        assert spend.artwork_id is None

        assert store.list_coverage_by_run("r2") == [ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1")]
        assert store.list_coverage_by_work("c1") == [ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1")]
    finally:
        reopened.close()


def _spend(id_: str, cost: str, status: CostStatus = CostStatus.KNOWN) -> SpendRecord:
    return SpendRecord(
        id=id_,
        category=SpendCategory.DISCOVERY_TOKENS,
        cost_usd=Decimal(cost),
        occurred_at=_STARTED,
        discovery_run_id="r1",
        model_id="lab/m",
        cost_status=status,
    )


def test_a_cost_status_survives_the_round_trip(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    opened = open_catalogue_file(path)
    try:
        store = SqliteDiscovery(opened)
        store.add_run(_run())
        store.add_spend_record(_spend("known", "0.07"))
        store.add_spend_record(_spend("unknown", "0", CostStatus.UNKNOWN))
    finally:
        opened.close()

    reopened = open_catalogue_file(path)
    try:
        read = {record.id: record.cost_status for record in SqliteDiscovery(reopened).list_spend_records()}
    finally:
        reopened.close()

    assert read == {"known": CostStatus.KNOWN, "unknown": CostStatus.UNKNOWN}


def _without_cost_status(path) -> None:
    """Take the column away, leaving `spend_records` as every release before it declared the table."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE spend_records DROP COLUMN cost_status")
        connection.commit()
        assert "cost_status" not in {row[1] for row in connection.execute("PRAGMA table_info(spend_records)")}
    finally:
        connection.close()


def test_a_row_written_before_the_column_existed_reads_as_known(tmp_path):
    """The widening's default is what an older row is, and it held the provider's figure."""
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()
    _without_cost_status(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO discovery_runs (id, kind, initiated_by, status, approval_required, started_at) "
            "VALUES ('r1', 'discovery', 'mcp_client', 'completed', 0, '2026-07-27T09:30:00+00:00')"
        )
        connection.execute(
            "INSERT INTO spend_records (id, discovery_run_id, category, cost_usd, occurred_at) "
            "VALUES ('old', 'r1', 'discovery_tokens', '0.42', '2026-07-27T09:30:00+00:00')"
        )
        connection.commit()
    finally:
        connection.close()

    reopened = open_catalogue_file(path)
    try:
        [record] = SqliteDiscovery(reopened).list_spend_records()
    finally:
        reopened.close()

    assert (record.id, record.cost_usd, record.cost_status) == ("old", Decimal("0.42"), CostStatus.KNOWN)


def test_a_row_whose_cost_is_unknown_sums_as_nothing_to_a_reader_that_ignores_the_column(tmp_path):
    """What v0.11.0 makes of such a row, which reads every column but this one.

    With the column gone and the file reopened, the row is what a release that
    never heard of it sees: a known cost of $0, which is what such a release
    says today of a call that left no row at all. (Measured against the
    v0.11.0 release itself as well; the change record says how.)
    """
    path = tmp_path / "catalogue.sqlite"
    opened = open_catalogue_file(path)
    try:
        store = SqliteDiscovery(opened)
        store.add_run(_run())
        store.add_spend_record(_spend("billed", "0.07"))
        store.add_spend_record(_spend("unanswered", "0", CostStatus.UNKNOWN))
    finally:
        opened.close()
    _without_cost_status(path)

    reopened = open_catalogue_file(path)
    try:
        records = SqliteDiscovery(reopened).list_spend_records()
    finally:
        reopened.close()

    assert sum((record.cost_usd for record in records), Decimal(0)) == Decimal("0.07")
    assert {record.id: record.cost_usd for record in records} == {"billed": Decimal("0.07"), "unanswered": Decimal(0)}


def test_a_cost_status_the_reader_does_not_know_is_refused_rather_than_read_as_known(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    opened = open_catalogue_file(path)
    try:
        store = SqliteDiscovery(opened)
        store.add_run(_run())
        store.add_spend_record(_spend("s", "0"))
    finally:
        opened.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE spend_records SET cost_status = 'estimated'")
        connection.commit()
    finally:
        connection.close()

    reopened = open_catalogue_file(path)
    try:
        with pytest.raises(ValueError, match="estimated"):
            SqliteDiscovery(reopened).list_spend_records()
    finally:
        reopened.close()


def test_a_cost_is_stored_as_a_decimal_rather_than_a_float(tmp_path):
    """A binary float cannot hold 0.07 exactly, and money read back wrong is worse
    than money not stored at all — nothing would ever report the drift."""
    path = tmp_path / "catalogue.sqlite"
    opened = open_catalogue_file(path)
    try:
        store = SqliteDiscovery(opened)
        store.add_run(_run())
        for index, amount in enumerate(("0.07", "0.07", "0.07")):
            store.add_spend_record(
                SpendRecord(
                    id=f"s{index}",
                    category=SpendCategory.DISCOVERY_TOKENS,
                    cost_usd=Decimal(amount),
                    occurred_at=_STARTED,
                    discovery_run_id="r1",
                )
            )

        total = sum((record.cost_usd for record in store.list_spend_records(run_id="r1")), Decimal(0))

        assert total == Decimal("0.21")
        assert str(total) == "0.21"
    finally:
        opened.close()


def test_the_file_itself_refuses_a_second_selected_instance(discovery_store):
    """The rule is the service layer's; this is what catches a path that forgets it.

    Enforcement in two places would be a defect if the two could disagree. They
    cannot: the index states strictly less than the rule does — at most one,
    where the rule says exactly one while any instance survives.
    """
    discovery_store.add_run(_run())
    discovery_store.add_candidate_work(_work())
    discovery_store.add_candidate_image(_image(is_selected=True))

    with pytest.raises(StorageError, match="already stored"):
        discovery_store.add_candidate_image(_image(id="i2", url="https://other.example/1", is_selected=True))


def test_a_work_is_covered_at_most_once_by_one_resolve_run(discovery_store):
    discovery_store.add_run(_run())
    discovery_store.add_run(_run(id="r2", kind=RunKind.RESOLVE, parent_run_id="r1"))
    discovery_store.add_candidate_work(_work())
    discovery_store.add_coverage(ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1"))

    with pytest.raises(StorageError, match="already stored"):
        discovery_store.add_coverage(ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1"))


def test_a_candidate_cannot_belong_to_a_run_that_does_not_exist(discovery_store):
    with pytest.raises(StorageError, match="not stored"):
        discovery_store.add_candidate_work(_work(discovery_run_id="no-such-run"))


def test_instances_read_with_the_chosen_one_first(discovery_store):
    """The store's ranking puts a work's selected instance first.

    A claim about this read, not about what a review card shows: that card is
    capped and keeps refused scans, so its own leading row is whatever ranks
    first among the ones it kept.
    """
    discovery_store.add_run(_run())
    discovery_store.add_candidate_work(_work())
    discovery_store.add_candidate_image(_image(id="i1", confidence=0.4, is_selected=True))
    discovery_store.add_candidate_image(_image(id="i2", url="https://other.example/1", confidence=0.9))

    assert [image.id for image in discovery_store.list_candidate_images("c1")] == ["i1", "i2"]


def test_runs_read_newest_first_because_a_run_list_is_a_history(discovery_store):
    discovery_store.add_run(_run(id="older", started_at=_STARTED))
    discovery_store.add_run(_run(id="newer", started_at=_FINISHED))

    assert [run.id for run in discovery_store.list_runs()] == ["newer", "older"]


def test_a_refusal_about_a_candidate_does_not_call_it_a_catalogue_record(discovery_store):
    """The store cannot see which table it refused, so it must not name one.

    A candidate work is precisely *not* in the catalogue — acceptance is what puts
    one there, and that distinction is the model's spine. A refusal reading "it is
    already in the catalogue" travels through `ServiceError` to whoever asked and
    tells them the opposite of what the model says.
    """
    discovery_store.add_run(_run())
    discovery_store.add_candidate_work(_work())

    with pytest.raises(StorageError) as refused:
        discovery_store.add_candidate_work(_work())

    assert "catalogue" not in str(refused.value)
    assert "candidate work" in str(refused.value)


def test_a_work_written_before_provenance_existed_reads_as_proposed(tmp_path):
    """The null a widened file carries has one honest meaning, not a third state.

    A candidate work on disk before collections could be browsed came from phase
    1, because nothing else could mint one. Reading that row as anything other
    than `proposed` — an absent value, a distinct "unknown" — would invent a
    provenance nobody recorded and put works of unknown origin in front of a
    curator who is being asked to trust the distinction.

    The legacy file is made by removing the column from a real one rather than by
    hand-writing an old schema, so the rest of the table stays exactly what the
    code creates and this cannot drift into testing a shape the product never had.
    """
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()

    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE candidate_works DROP COLUMN provenance")
        connection.execute(
            "INSERT INTO discovery_runs (id, kind, initiated_by, status, approval_required, started_at) "
            "VALUES ('r1', 'discovery', 'mcp_client', 'resolving_works', 0, '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO candidate_works (id, discovery_run_id, proposed_title, rationale, work_dedup_key, "
            "resolution_status, verdict) VALUES ('c1', 'r1', 'The Night Watch', 'A famous work.', 'k', "
            "'pending', 'pending')"
        )
        connection.commit()
        assert "provenance" not in {row[1] for row in connection.execute("PRAGMA table_info(candidate_works)")}
    finally:
        connection.close()

    store = SqliteDiscovery(open_catalogue_file(path))
    try:
        held = store.get_candidate_work("c1")
        assert held.provenance is WorkProvenance.PROPOSED

        # And the widened file takes a write that names the column.
        store.update_candidate_work(replace(held, provenance=WorkProvenance.OFFERED))
        assert store.get_candidate_work("c1").provenance is WorkProvenance.OFFERED
    finally:
        store.close()


def test_a_file_from_before_gets_opens_and_takes_a_chosen_work(tmp_path):
    """A catalogue written before a Get could name an item gains the column and keeps its works.

    Made by removing the column from a real file, as the provenance test above
    does, so the rest of the table is exactly what the code creates.
    """
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()

    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE candidate_works DROP COLUMN wikidata_qid")
        connection.execute(
            "INSERT INTO discovery_runs (id, kind, initiated_by, status, approval_required, started_at) "
            "VALUES ('r1', 'discovery', 'mcp_client', 'resolving_works', 0, '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO candidate_works (id, discovery_run_id, proposed_title, rationale, work_dedup_key, "
            "resolution_status, verdict) VALUES ('c1', 'r1', 'The Night Watch', 'A famous work.', 'k', "
            "'pending', 'pending')"
        )
        connection.commit()
        assert "wikidata_qid" not in {row[1] for row in connection.execute("PRAGMA table_info(candidate_works)")}
    finally:
        connection.close()

    store = SqliteDiscovery(open_catalogue_file(path))
    try:
        assert store.get_candidate_work("c1").wikidata_qid is None, "an older work names no item"
        store.add_run(_run(id="r2", kind=RunKind.GET, status=RunStatus.RESOLVING_IMAGES))
        store.add_candidate_work(_work(id="c2", discovery_run_id="r2", provenance=WorkProvenance.CHOSEN, wikidata_qid="Q45585"))
        assert store.get_candidate_work("c2").wikidata_qid == "Q45585"
    finally:
        store.close()


def test_a_file_from_before_destinations_opens_and_takes_a_run_that_names_one(tmp_path):
    """A catalogue written before a Get could name a theme gains the column; its runs name none.

    Made by removing the column from a real file, as the tests above do. The
    null an older run reads back means the default theme, which is where every
    acceptance went before a run could say otherwise.
    """
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()

    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE discovery_runs DROP COLUMN destination_theme_id")
        connection.execute(
            "INSERT INTO discovery_runs (id, kind, initiated_by, status, approval_required, started_at) "
            "VALUES ('r1', 'get', 'mcp_client', 'resolving_images', 0, '2026-01-01T00:00:00+00:00')"
        )
        connection.commit()
        assert "destination_theme_id" not in {row[1] for row in connection.execute("PRAGMA table_info(discovery_runs)")}
    finally:
        connection.close()

    store = SqliteDiscovery(open_catalogue_file(path))
    try:
        assert store.get_run("r1").destination_theme_id is None, "an older run names no theme"
        store.add_run(_run(id="r2", kind=RunKind.GET, status=RunStatus.RESOLVING_IMAGES, destination_theme_id="t-1"))
        assert store.get_run("r2").destination_theme_id == "t-1"
    finally:
        store.close()


def test_a_file_from_before_end_reasons_opens_and_its_failed_runs_give_none(tmp_path):
    """A catalogue written before a run kept why it ended gains the column; its old runs read null.

    Made by removing the column from a real file, as the tests above do. The old
    run is a *failed* one, because that is the row a reader would most expect to
    carry a reason, and the null is what the run page falls back on.
    """
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()

    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE discovery_runs DROP COLUMN end_reason")
        connection.execute(
            "INSERT INTO discovery_runs (id, kind, intent_text, initiated_by, status, approval_required, started_at) "
            "VALUES ('r1', 'discovery', 'Lucy Bull', 'web_ui', 'failed', 0, '2026-10-05T00:00:00+00:00')"
        )
        connection.commit()
        assert "end_reason" not in {row[1] for row in connection.execute("PRAGMA table_info(discovery_runs)")}
    finally:
        connection.close()

    store = SqliteDiscovery(open_catalogue_file(path))
    try:
        assert store.get_run("r1").status is RunStatus.FAILED
        assert store.get_run("r1").end_reason is None, "a run that failed before the column gives no reason"
        store.add_run(_run(id="r2", status=RunStatus.FAILED, end_reason="Phase 1 returned an empty answer."))
        assert store.get_run("r2").end_reason == "Phase 1 returned an empty answer."
    finally:
        store.close()


@pytest.mark.parametrize("said", [True, False, None], ids=["confirmed", "unconfirmed", "no-word"])
def test_phase_ones_word_on_a_source_survives_the_file_with_no_word_kept_apart(tmp_path, said):
    """Three values in one nullable column: a no-word read back as `False` would mark every older proposal unconfirmed."""
    path = tmp_path / "catalogue.sqlite"
    first = open_catalogue_file(path)
    writer = SqliteDiscovery(first)
    writer.add_run(_run())
    writer.add_candidate_work(_work(source_confirmed=said))
    first.close()

    reopened = open_catalogue_file(path)
    try:
        assert SqliteDiscovery(reopened).get_candidate_work("c1").source_confirmed is said
    finally:
        reopened.close()


@pytest.mark.parametrize(
    ("provenance", "said", "confirmation"),
    [
        (WorkProvenance.PROPOSED, True, Confirmation.CONFIRMED),
        (WorkProvenance.PROPOSED, False, Confirmation.UNCONFIRMED),
        (WorkProvenance.PROPOSED, None, Confirmation.UNKNOWN),
        # Confirmed by where they came from, whatever the column holds.
        (WorkProvenance.CHOSEN, None, Confirmation.CONFIRMED),
        (WorkProvenance.OFFERED, None, Confirmation.CONFIRMED),
    ],
)
def test_a_work_is_confirmed_by_a_source_or_by_where_it_came_from_and_no_word_is_never_confirmed(provenance, said, confirmation):
    assert _work(provenance=provenance, source_confirmed=said).confirmation is confirmation


def test_rejected_works_are_the_newest_decisions_first_one_per_work_and_bounded(tmp_path):
    """What phase 1 is told not to propose: rejected only, each work once at its latest rejection."""
    store = SqliteDiscovery(open_catalogue_file(tmp_path / "catalogue.sqlite"))
    store.add_run(_run())
    store.add_run(_run(id="r2"))

    def decided(minutes: int) -> datetime:
        return _STARTED + timedelta(minutes=minutes)

    for id_, run, key, verdict, minutes in [
        ("old", "r1", "a::old", Verdict.REJECTED, 1),
        ("again-early", "r1", "a::twice", Verdict.REJECTED, 2),
        ("again-late", "r2", "a::twice", Verdict.REJECTED, 9),
        ("newest", "r2", "a::newest", Verdict.REJECTED, 5),
        ("kept", "r1", "a::kept", Verdict.ACCEPTED, 20),
        ("wanted", "r1", "a::wanted", Verdict.WANTED, 21),
    ]:
        store.add_candidate_work(
            _work(id=id_, discovery_run_id=run, work_dedup_key=key, verdict=verdict, decided_at=decided(minutes))
        )
    store.add_candidate_work(_work(id="pending", work_dedup_key="a::pending"))

    assert [work.id for work in store.list_rejected_works(10)] == ["again-late", "newest", "old"]
    assert [work.id for work in store.list_rejected_works(2)] == ["again-late", "newest"]
    assert store.list_rejected_works(0) == ()
