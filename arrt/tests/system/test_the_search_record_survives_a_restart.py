"""What Status says of a plugin's searches is read from the record, so the server's restart keeps it.

Before the search record (audit-wave-2b Chunk 33), the could-not-be-asked count
lived in the server's memory and a restart reset it, so a museum that had not
answered a single search read as healthy every morning. Here the server runs as
a process (`ArrtProcess`): started; the record written as phase 2 leaves it, a
plugin the server loaded having been asked about four works and unable to
answer three; stopped; started again; and Status read over HTTP.

The record is written with the store's own method, between the starts, rather
than by a Get: the server process loads the built-in plugins, and a Get would
send them to museums. That the pool writes the record is held by
`tests/unit/test_phase_two_run.py`, through the same wiring.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from arrt.library.sources.loading import PluginReading, PluginState
from arrt.persistence.discovery_records import (
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    RunKind,
    RunStatus,
    SearchOutcome,
    SearchTally,
    SourceSearch,
)
from arrt.services.health import SourceHealth

ASKED = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)


def _sources(base_url: str) -> list[dict]:
    answer = httpx.get(f"{base_url}/api/health", timeout=30.0)
    assert answer.status_code == 200, answer.text
    return answer.json()["sources"]


@pytest.mark.uncacheable("starts the server as a process twice")
def test_a_plugin_that_could_not_be_asked_about_its_searches_still_reads_so_after_a_restart(arrt_process, discovery_store):
    base_url = arrt_process.start()
    loaded = [source for source in _sources(base_url) if source["state"] == "loaded"]
    assert loaded, "the server loaded no plugin, so there is nothing whose searches could be recorded"
    plugin = loaded[0]["name"]
    assert (loaded[0]["searched"], loaded[0]["searches_unasked"]) == (0, 0)

    # Recorded while the server runs, as a run's searches would be.
    discovery_store.add_run(
        DiscoveryRun(
            id="r1",
            kind=RunKind.GET,
            initiated_by=InitiatedBy.WEB_UI,
            status=RunStatus.COMPLETED,
            approval_required=False,
            started_at=ASKED,
        )
    )
    for n, outcome in enumerate((SearchOutcome.UNREACHABLE,) * 3 + (SearchOutcome.ANSWERED,)):
        discovery_store.add_candidate_work(
            CandidateWork(
                id=f"c{n}", discovery_run_id="r1", proposed_title=f"Study No. {n}", rationale="Chosen.", work_dedup_key=f"k{n}"
            )
        )
        asked = ASKED + timedelta(minutes=n)
        discovery_store.record_search(
            SourceSearch(
                candidate_work_id=f"c{n}",
                provider=plugin,
                asked_at=asked,
                outcome=outcome,
                answered_at=asked if outcome is SearchOutcome.ANSWERED else None,
            )
        )
    arrt_process.stop()

    base_url = arrt_process.start()
    source = next(source for source in _sources(base_url) if source["name"] == plugin)

    assert (source["searched"], source["searches_answered"], source["searches_unasked"], source["searches_owed"]) == (
        4,
        1,
        3,
        0,
    )
    assert source["last_search_answered_at"] == (ASKED + timedelta(minutes=3)).isoformat()
    assert "Of the 4 works it was last searched for, it could not be asked about 3." in source["description"]
    # Since startup, nothing: the in-memory counts are the new process's.
    assert source["unasked"] == 0


@pytest.mark.parametrize(
    ("tally", "said"),
    [
        (
            SearchTally(provider="met", searched=5, answered=0, unasked=4, owed=1),
            (
                " It has answered none of the 5 works it was last searched for: it could not be asked about 4, and "
                "still owes an answer about 1."
            ),
        ),
        (SearchTally(provider="met", searched=1, answered=1, unasked=0, owed=0), ""),
        (None, ""),
    ],
)
def test_what_status_says_of_the_record_is_its_counts_and_nothing_when_nothing_is_in_doubt(tally, said):
    """The record's sentence follows the since-startup one, and is absent when every search was answered."""
    reading = PluginReading(name="met", state=PluginState.LOADED, reason=None, faults=0, last_fault_at=None, last_fault=None)

    described = SourceHealth(reading=reading, last_fault_age_seconds=None, searches=tally).describe()

    assert described == "The Metropolitan Museum of Art plugin is loaded, with no faults since startup." + said
