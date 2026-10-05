"""What waits for the curator's verdict, counted over real HTTP and a real MCP client.

*To review* is read from the run listing: `awaiting` by run, `awaiting_works` in
all, and `awaiting=true` to narrow the listing to the runs holding any. A work
waits when it found an image and has no verdict; one with no image has nothing to
accept and does not wait. Each work is counted on the run that first named it, so
a re-search looking at it again does not count it twice.

Runs and works are written straight to the store, because the states under test
(a verdict given, a re-search covering a work, fifty newer runs) are the point,
and reaching them through phase 2 would test phase 2.
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from arrt.library.services.runner import MAX_RUNS_LISTED
from arrt.persistence.discovery_records import (
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    ResolutionStatus,
    ResolveRunWork,
    RunKind,
    RunStatus,
    Verdict,
    WorkProvenance,
)

START = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def a_run(store, run_id: str, *, kind=RunKind.DISCOVERY, minutes: int = 0, parent: str | None = None) -> None:
    store.add_run(
        DiscoveryRun(
            id=run_id,
            kind=kind,
            initiated_by=InitiatedBy.MCP_CLIENT,
            status=RunStatus.COMPLETED,
            approval_required=False,
            started_at=START + timedelta(minutes=minutes),
            parent_run_id=parent,
            intent_text=f"intent {run_id}" if kind is RunKind.DISCOVERY else None,
        )
    )


def a_work(store, work_id: str, run_id: str, *, verdict=Verdict.PENDING, resolution=ResolutionStatus.RESOLVED) -> None:
    store.add_candidate_work(
        CandidateWork(
            id=work_id,
            discovery_run_id=run_id,
            proposed_title=f"Work {work_id}",
            rationale="Named.",
            work_dedup_key=f"key-{work_id}",
            provenance=WorkProvenance.PROPOSED,
            resolution_status=resolution,
            verdict=verdict,
        )
    )


@pytest.fixture
def runs(discovery_store):
    """Three runs: one with mixed verdicts, one re-search over it, one with nothing waiting.

    - `mixed`: two waiting, one accepted, one rejected, one that found no image.
    - `again`: a re-search covering one of `mixed`'s waiting works, owning none.
    - `settled`: every work judged.
    """
    a_run(discovery_store, "mixed", minutes=1)
    a_work(discovery_store, "m1", "mixed")
    a_work(discovery_store, "m2", "mixed")
    a_work(discovery_store, "m3", "mixed", verdict=Verdict.ACCEPTED)
    a_work(discovery_store, "m4", "mixed", verdict=Verdict.REJECTED)
    a_work(discovery_store, "m5", "mixed", resolution=ResolutionStatus.UNRESOLVED)
    a_run(discovery_store, "again", kind=RunKind.RESOLVE, minutes=2, parent="mixed")
    discovery_store.add_coverage(ResolveRunWork(resolve_run_id="again", candidate_work_id="m1"))
    a_run(discovery_store, "settled", minutes=3)
    a_work(discovery_store, "s1", "settled", verdict=Verdict.ACCEPTED)
    return discovery_store


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


def test_the_listing_counts_what_waits_by_the_run_that_owns_it(server_url, runs):
    listing = httpx.get(f"{server_url}/api/runs", timeout=10).json()

    assert listing["awaiting_works"] == 2
    assert listing["awaiting"] == {"mixed": 2}, "the re-search owns no work, and the settled run has none waiting"


def test_narrowed_to_what_waits_the_listing_holds_only_those_runs(server_url, runs):
    listing = httpx.get(f"{server_url}/api/runs?awaiting=true", timeout=10).json()

    assert [run["run_id"] for run in listing["runs"]] == ["mixed"]
    assert (listing["total"], listing["awaiting_works"]) == (1, 2)


def test_a_verdict_takes_a_work_off_the_count(server_url, services, runs):
    services.discovery.set_verdict("m1", Verdict.REJECTED)

    listing = httpx.get(f"{server_url}/api/runs", timeout=10).json()

    assert (listing["awaiting_works"], listing["awaiting"]) == (1, {"mixed": 1})


def test_an_old_run_with_works_waiting_is_not_lost_behind_newer_ones(server_url, discovery_store):
    """Narrowed before the cap, so the oldest run is listed when it is the one waiting."""
    a_run(discovery_store, "oldest", minutes=0)
    a_work(discovery_store, "o1", "oldest")
    for index in range(MAX_RUNS_LISTED + 1):
        a_run(discovery_store, f"newer-{index}", minutes=10 + index)

    listing = httpx.get(f"{server_url}/api/runs?awaiting=true", timeout=10).json()

    assert [run["run_id"] for run in listing["runs"]] == ["oldest"]


async def test_an_agent_reads_the_same_counts(server_url, runs):
    payload, errored = await call(server_url, "art_discovery", action="list_runs", awaiting=True)

    assert errored is False, payload
    assert [run["run_id"] for run in payload["runs"]] == ["mixed"]
    assert (payload["awaiting_works"], payload["awaiting"]) == (2, {"mixed": 2})
