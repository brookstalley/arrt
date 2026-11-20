"""MCP's and Ask's calls each on a bounded pool of threads of their own.

`art_discovery(status)` holds its thread until the run changes, up to
`STATUS_HOLD_SECONDS`. On asyncio's default executor, MCP's calls and Ask's
shared min(32, CPUs + 4) threads, so on a four-core machine eight held status
calls left every other MCP call and every Ask reply waiting for a hold to end.
The machine is made to look like a four-core one here, so a pool still sized from
the processor count would get those eight threads.

Every wait below is on an event a call sets, never on a sleep: a pool's threads
are all busy exactly when every call it runs is blocked on an event the test
holds.
"""

import asyncio
import contextvars
import json
import logging
import os
import threading
import time
from typing import Any

import httpx
import pytest
from scripted_model import ScriptedModel, calls, says

from arrt.ask.agent import Ask, ReplyCost
from arrt.services.threads import (
    ASK_CALL_THREADS,
    ASK_POOL,
    MCP_CALL_THREADS,
    MCP_POOL,
    QUEUED_EVENT,
    SURFACE_CALL_THREADS,
    CallPool,
    ask_pool,
    mcp_pool,
)

#: The threads asyncio's default executor has on a four-core machine: min(32, 4 + 4).
FOUR_CORE_DEFAULT_THREADS = 8

#: How long a call made beside the holds may take and still have been answered at once.
ANSWERED_AT_ONCE_SECONDS = 1.0

#: The bound on any one wait for an event a call sets; reached only by a defect.
EVENT_SECONDS = 20.0

THREADS_LOGGER = "arrt.services.threads"


@pytest.fixture(autouse=True)
def four_cores(monkeypatch):
    """Report four processors, before the server's loop builds any pool from the count."""
    monkeypatch.setattr(os, "process_cpu_count", lambda: 4)


@pytest.fixture
def ask_model():
    return ScriptedModel(replies=[calls(("art_catalogue", {"action": "list"})), says("Three works.")])


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


async def reply(server_url: str, words: str) -> list[dict]:
    """Ask's reply through the real route, every event it streamed."""
    async with httpx.AsyncClient(base_url=server_url, timeout=60) as client:
        thread_id = (await client.post("/api/ask/threads")).json()["thread_id"]
        async with client.stream("POST", f"/api/ask/threads/{thread_id}/replies", json={"words": words}) as response:
            assert response.status_code == 200
            return [json.loads(line) async for line in response.aiter_lines() if line.strip()]


async def timed(awaitable) -> tuple[float, Any]:
    began = time.monotonic()
    answer = await awaitable
    return time.monotonic() - began, answer


async def waited_for(event: threading.Event) -> bool:
    return await asyncio.to_thread(event.wait, EVENT_SECONDS)


class Holds:
    """`art_discovery(status)` calls held on a run the engine's gate keeps in flight, counted as they reach the runner."""

    def __init__(self, server_url: str, services, engine) -> None:
        self._server_url = server_url
        self._engine = engine
        self._reached = threading.Condition()
        self.threads: list[str] = []
        self.tasks: list[asyncio.Task] = []
        self.run_id = ""
        run_status = services.runner.run_status

        def held_status(run: str, *, wait: bool = True):
            with self._reached:
                self.threads.append(threading.current_thread().name)
                self._reached.notify_all()
            return run_status(run, wait=wait)

        services.runner.run_status = held_status

    async def start(self) -> None:
        self._engine.gate = threading.Event()
        payload, errored = await call(self._server_url, "art_discovery", action="start", intent="Dutch still life")
        assert errored is False, payload
        self.run_id = payload["run_id"]

    async def hold(self, count: int) -> None:
        """Put `count` more status calls in flight and return once every one has reached the runner."""
        target = len(self.tasks) + count
        self.tasks += [
            asyncio.create_task(call(self._server_url, "art_discovery", action="status", run_id=self.run_id))
            for _ in range(count)
        ]

        def reached() -> bool:
            with self._reached:
                return self._reached.wait_for(lambda: len(self.threads) >= target, EVENT_SECONDS)

        assert await asyncio.to_thread(reached), f"only {len(self.threads)} of {target} status calls were held"

    async def release(self) -> None:
        self._engine.gate.set()
        answers = await asyncio.gather(*self.tasks)
        assert all(errored is False for _, errored in answers), answers


class Queued(logging.Handler):
    """The journal's `QUEUED_EVENT` lines, each pool's arrival an event a test can wait on."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[logging.LogRecord] = []
        self.arrived = {MCP_POOL: threading.Event(), ASK_POOL: threading.Event()}

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "event", None) == QUEUED_EVENT:
            self.lines.append(record)
            self.arrived[record.pool].set()

    def of(self, pool: str) -> list[logging.LogRecord]:
        return [line for line in self.lines if line.pool == pool]


@pytest.fixture
def journal():
    """The pools' logger, read by a handler of the test's own."""
    logger = logging.getLogger(THREADS_LOGGER)
    handler = Queued()
    level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(level)


# -- through the real server ------------------------------------------------------


async def test_beside_eight_held_status_calls_an_mcp_call_and_an_ask_reply_each_answer_at_once(server_url, services, engine):
    """As many holds as a four-core machine's default executor had threads, which left both waiting."""
    holds = Holds(server_url, services, engine)
    await holds.start()
    try:
        await holds.hold(FOUR_CORE_DEFAULT_THREADS)
        (mcp_waited, (listed, listed_errored)), (ask_waited, events) = await asyncio.gather(
            timed(call(server_url, "art_catalogue", action="list")),
            timed(reply(server_url, "What is in the Library?")),
        )
    finally:
        await holds.release()

    assert listed_errored is False, listed
    assert listed["total"] == 3, "the ninth call should have read the seeded works"
    assert events[-1]["type"] == "stream_end", events[-1]
    assert next(event for event in events if event["type"] == "tool_call_end")["success"] is True
    assert mcp_waited < ANSWERED_AT_ONCE_SECONDS, f"the ninth MCP call waited {mcp_waited:.2f}s for a hold"
    assert ask_waited < ANSWERED_AT_ONCE_SECONDS, f"Ask's reply waited {ask_waited:.2f}s for a hold"
    # Held on MCP's own threads, not the default executor's.
    assert all(name.startswith(f"arrt-{MCP_POOL}-call") for name in holds.threads), holds.threads


async def test_mcp_holds_queue_a_short_mcp_call_only_once_all_its_threads_hold_and_never_an_ask_reply(
    server_url, services, engine, journal
):
    """MCP's pool is `MCP_CALL_THREADS` threads: one fewer holds leaves a thread, that many leaves none."""
    holds = Holds(server_url, services, engine)
    await holds.start()
    try:
        await holds.hold(MCP_CALL_THREADS - 1)
        waited, (_, errored) = await timed(call(server_url, "art_catalogue", action="list"))
        assert errored is False
        assert waited < ANSWERED_AT_ONCE_SECONDS, f"a call with one thread free waited {waited:.2f}s"
        assert journal.of(MCP_POOL) == []

        await holds.hold(1)
        # Ask's threads are its own: a full MCP pool leaves its reply unhindered.
        ask_waited, events = await timed(reply(server_url, "What is in the Library?"))
        assert events[-1]["type"] == "stream_end", events[-1]
        assert ask_waited < ANSWERED_AT_ONCE_SECONDS, f"Ask's reply waited {ask_waited:.2f}s behind MCP's holds"

        short = asyncio.create_task(call(server_url, "art_catalogue", action="list"))
        assert await waited_for(journal.arrived[MCP_POOL]), "the call past the pool's size wrote no journal line"
        assert not short.done(), "the call past the pool's size did not wait for a thread"
    finally:
        await holds.release()

    _, errored = await short
    assert errored is False, "the waiting call should run once a hold ended"
    [line] = journal.of(MCP_POOL)
    assert (line.threads, line.waiting, line.levelno) == (MCP_CALL_THREADS, 1, logging.WARNING)
    assert journal.of(ASK_POOL) == []


# -- Ask's own pool ---------------------------------------------------------------


def unrecorded(_cost: ReplyCost) -> None:
    """For a test about something other than spend."""


async def test_one_step_of_ask_runs_at_most_its_pools_size_of_calls_at_once_and_queues_the_rest(journal):
    asked = ASK_CALL_THREADS + 1
    release = threading.Event()
    counting = threading.Lock()
    running: list[str] = []
    all_running = threading.Event()

    def held(_name: str, _arguments: object) -> dict[str, Any]:
        with counting:
            running.append(threading.current_thread().name)
            if len(running) == ASK_CALL_THREADS:
                all_running.set()
        assert release.wait(EVENT_SECONDS)
        return {"success": True, "works": []}

    model = ScriptedModel(replies=[calls(*[("art_catalogue", {"action": "list"})] * asked), says("Done.")])
    ask = Ask(held, model, step_limit=4, record_cost=unrecorded)
    lines = ask.reply(ask.threads.open(), "Everything")
    finished = asyncio.create_task(_drained(lines))
    try:
        assert await waited_for(all_running), f"only {len(running)} of Ask's calls started"
        assert await waited_for(journal.arrived[ASK_POOL]), "the call past Ask's pool wrote no journal line"
        with counting:
            assert len(running) == ASK_CALL_THREADS
    finally:
        release.set()
    events = await finished

    assert events[-1]["type"] == "stream_end", events[-1]
    assert len(running) == asked
    assert all(name.startswith(f"arrt-{ASK_POOL}-call") for name in running), running
    [line] = journal.of(ASK_POOL)
    assert (line.threads, line.waiting) == (ASK_CALL_THREADS, 1)


async def _drained(lines) -> list[dict]:
    return [json.loads(line) async for line in lines]


async def test_asks_taste_read_runs_on_asks_own_pool():
    read_on: list[str] = []

    def taste() -> str:
        read_on.append(threading.current_thread().name)
        return ""

    ask = Ask(
        lambda *_: {"success": True}, ScriptedModel(replies=[says("Hello.")]), step_limit=2, record_cost=unrecorded, taste=taste
    )
    await _drained(ask.reply(ask.threads.open(), "Hello"))

    assert [name.split("_")[0] for name in read_on] == [f"arrt-{ASK_POOL}-call"]


# -- the pools themselves ---------------------------------------------------------


def test_each_surfaces_pool_is_its_named_size_and_the_total_is_their_sum():
    assert (mcp_pool().name, mcp_pool().size) == (MCP_POOL, MCP_CALL_THREADS)
    assert (ask_pool().name, ask_pool().size) == (ASK_POOL, ASK_CALL_THREADS)
    assert SURFACE_CALL_THREADS == MCP_CALL_THREADS + ASK_CALL_THREADS
    # The shared executor's bound on a four-core machine, which the pools replace.
    assert MCP_CALL_THREADS > FOUR_CORE_DEFAULT_THREADS


async def test_a_pool_never_runs_more_than_its_size_and_a_finished_call_wakes_the_first_waiting():
    size = 2
    pool = CallPool("test", size)
    gates = [threading.Event() for _ in range(size + 2)]
    started = [threading.Event() for _ in range(size + 2)]
    order: list[int] = []

    def blocked(index: int) -> int:
        order.append(index)
        started[index].set()
        assert gates[index].wait(EVENT_SECONDS)
        return index

    tasks = [asyncio.create_task(pool.run(blocked, index)) for index in range(size + 2)]
    try:
        assert all([await waited_for(started[index]) for index in range(size)]), "the first calls did not all start"
        # Every thread is blocked on a gate the test holds, so the waiting calls cannot have started.
        assert not started[size].is_set()
        assert not started[size + 1].is_set()
        assert pool.in_flight == size + 2

        gates[0].set()
        assert await waited_for(started[size]), "a finished call did not wake the first waiting one"
        assert not started[size + 1].is_set()
    finally:
        for gate in gates:
            gate.set()

    assert await asyncio.gather(*tasks) == list(range(size + 2))
    assert order == list(range(size + 2))
    assert pool.in_flight == 0


async def test_a_call_runs_in_its_callers_context_and_raises_what_it_raised():
    """As `asyncio.to_thread` does: a context variable the caller set is set on the pool's thread."""
    pool = CallPool("test", 1)
    marked: contextvars.ContextVar[str] = contextvars.ContextVar("marked", default="unset")
    marked.set("the caller's")

    assert await pool.run(marked.get) == "the caller's"
    with pytest.raises(LookupError, match="refused"):
        await pool.run(_refuses)
    assert pool.in_flight == 0


def _refuses() -> None:
    raise LookupError("refused")


async def test_a_cancelled_caller_frees_its_thread_only_when_its_call_has_finished():
    pool = CallPool("test", 1)
    release, started = threading.Event(), threading.Event()

    def blocked() -> None:
        started.set()
        assert release.wait(EVENT_SECONDS)

    running = asyncio.create_task(pool.run(blocked))
    waiting = asyncio.create_task(pool.run(blocked))
    assert await waited_for(started)

    waiting.cancel()
    running.cancel()
    await asyncio.gather(running, waiting, return_exceptions=True)
    # The waiting call never started and is gone; the running one still holds its thread.
    assert pool.in_flight == 1

    release.set()
    # One thread: this runs only once the cancelled caller's call has finished on it.
    assert await pool.run(lambda: "free") == "free"
    assert pool.in_flight == 0
