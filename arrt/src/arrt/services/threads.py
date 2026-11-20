"""The threads MCP's tool calls and Ask's run on: a bounded pool for each surface.

The service layer is synchronous, and two of its calls hold their thread on
purpose: `art_discovery(status)` until the run changes, up to
`STATUS_HOLD_SECONDS` (45 s), and a look until its sources answer, up to
`LOOK_HOLD_SECONDS` (30 s). Called from an event loop, each call needs a thread
of its own for as long as it runs.

**Each surface has its own pool, so a hold on one never takes a thread from the
other.** On asyncio's default executor the two shared min(32, CPUs + 4)
threads, eight on a four-core machine, and eight held status calls left an MCP
call and an Ask reply waiting for a hold to end. Within a surface a short call
waits only when every one of that surface's threads is busy.

**What the shared executor bounded, and what bounds it now.** At most eight
service calls from MCP and Ask together were in flight on a four-core machine.
The pools raise that to `MCP_CALL_THREADS` plus `ASK_CALL_THREADS`. The HTTP
handlers' own pool (anyio's) and the background threads are outside both, as
they were. The paid paths keep their own limits, which no thread count sets.

A call that finds every thread of its pool busy waits for the next one to
finish, in the order the calls came, and says so in the journal (`QUEUED_EVENT`).
"""

import asyncio
import contextvars
import functools
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Final

log = logging.getLogger(__name__)

#: MCP's tool calls in flight at once. Every held status call or look keeps one,
#: so this many less one can hold while a short call still finds a thread: twice
#: the eight a four-core machine's default executor had for both surfaces.
MCP_CALL_THREADS: Final[int] = 16

#: Ask's tool calls and its taste read in flight at once. None of Ask's actions
#: holds, and one step's calls run together, so this is a step's calls across a
#: few replies at once.
ASK_CALL_THREADS: Final[int] = 8

#: The service calls MCP and Ask can have in flight together.
SURFACE_CALL_THREADS: Final[int] = MCP_CALL_THREADS + ASK_CALL_THREADS

#: The pools' names: a journal line's `pool`, and the start of each thread's name.
MCP_POOL: Final[str] = "mcp"
ASK_POOL: Final[str] = "ask"

#: The journal's `event` for a call that waits because every thread of its pool is busy.
QUEUED_EVENT: Final[str] = "tool_call.queued"


class CallPool:
    """Runs synchronous calls from an event loop on at most `size` threads, which start as calls need them."""

    def __init__(self, name: str, size: int) -> None:
        self.name = name
        self.size = size
        self._executor = ThreadPoolExecutor(max_workers=size, thread_name_prefix=f"arrt-{name}-call")
        self._counting = threading.Lock()
        #: Calls submitted and not yet finished, running or waiting for a thread.
        self._in_flight = 0

    @property
    def in_flight(self) -> int:
        """The calls running or waiting for a thread."""
        with self._counting:
            return self._in_flight

    async def run[T](self, function: Callable[..., T], /, *args: object) -> T:
        """`function(*args)` on one of this pool's threads, in the caller's context, as `asyncio.to_thread` runs it.

        Cancelling the caller stops a call still waiting for a thread; one
        already running finishes on its thread, and its thread is counted busy
        until it does.
        """
        context = contextvars.copy_context()
        with self._counting:
            self._in_flight += 1
            in_flight = self._in_flight
        if in_flight > self.size:
            log.warning(
                "A %s call waits for a thread: all %d are busy.",
                self.name,
                self.size,
                extra={"event": QUEUED_EVENT, "pool": self.name, "threads": self.size, "waiting": in_flight - self.size},
            )
        try:
            submitted = self._executor.submit(functools.partial(context.run, function, *args))
        except BaseException:
            self._release_one()
            raise
        # On the future, not after the await: a cancelled caller stops awaiting
        # while the thread may still be running the call.
        submitted.add_done_callback(lambda _done: self._release_one())
        return await asyncio.wrap_future(submitted)

    def _release_one(self) -> None:
        with self._counting:
            self._in_flight -= 1


def mcp_pool() -> CallPool:
    """A pool for one MCP server's tool calls."""
    return CallPool(MCP_POOL, MCP_CALL_THREADS)


def ask_pool() -> CallPool:
    """A pool for one Ask's tool calls and taste reads."""
    return CallPool(ASK_POOL, ASK_CALL_THREADS)
