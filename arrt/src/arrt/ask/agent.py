"""Ask's agent: one thread, the surface's read tools, replies streamed as 3tears events.

**The agent is a third thin binding over the services**, beside the MCP tools
and the HTTP handlers. It is offered the MCP surface's own tool definitions,
whole, and each call goes to the same `dispatch` an MCP client's call reaches,
in-process rather than over HTTP. An action outside `ASK_SCOPE` is answered
with a teaching error naming what is in scope, and is never dispatched.

**The stream is 3tears' vocabulary, unchanged**, one event per line:
`stream_start`, `stream_token`, `tool_call_start` and `tool_call_end`, then
exactly one of `stream_end` or `stream_error`. The lifecycle is driven here
rather than by `StreamingResponse.run_graph`, which emits no tool events and
ends without the reply's cost.

**Threads live in memory and a restart forgets them** (the owner,
2026-10-08: "nobody will care if old ones are just gone"). At most
`THREADS_KEPT` are held, the least recently used dropped first.
"""

import asyncio
import json
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID, uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from threetears.langgraph.streaming import CANCELLED_ERROR_CODE, DEFAULT_ERROR_CODE, StreamingResponse

from arrt.ask.cards import cards_for
from arrt.ask.prompt import ASK_SCOPE, ASK_SYSTEM, HELP
from arrt.mcp.envelope import IMAGE_BLOCKS
from arrt.mcp.server import tool_definitions

log = logging.getLogger("arrt.ask")

#: How many threads the server holds. Each holds every message of its thread,
#: tool results included, on a server with a memory cap; twenty is more than
#: one household has open at once.
THREADS_KEPT: Final[int] = 20

#: The terminal code for a reply stopped at the step limit. Its own code rather
#: than 3tears' `AGENT_FAILED`, because the client says something different:
#: the agent ran out of steps, nothing broke.
STEP_LIMIT_CODE: Final[str] = "STEP_LIMIT"

#: The events that end a reply's stream.
TERMINALS: Final[frozenset[str]] = frozenset({"stream_end", "stream_error", "stream_interrupt"})

#: Graph steps allowed per model call: far more than one call takes, so only the call limit binds.
_GRAPH_STEPS_PER_CALL: Final[int] = 10

#: One call to the surface: a tool name and its arguments in, a payload out.
Dispatch = Callable[[str, Mapping[str, Any]], dict[str, Any]]


@dataclass
class Turn:
    """One thing the curator said, and every event the reply sent, as sent."""

    asked: str
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Thread:
    id: str
    #: What the model is given next time: every message so far, tool results included.
    messages: list[BaseMessage] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    #: Set while a reply runs. A thread answers one thing at a time.
    replying: bool = False


class Threads:
    """The threads held in memory, the least recently used dropped first past `kept`."""

    def __init__(self, kept: int = THREADS_KEPT) -> None:
        self._kept = kept
        self._threads: OrderedDict[str, Thread] = OrderedDict()

    def open(self) -> Thread:
        thread = Thread(id=str(uuid4()))
        self._threads[thread.id] = thread
        while len(self._threads) > self._kept:
            self._threads.popitem(last=False)
        return thread

    def get(self, thread_id: str) -> Thread | None:
        thread = self._threads.get(thread_id)
        if thread is not None:
            self._threads.move_to_end(thread_id)
        return thread


class Ask:
    """The agent and its threads. Built once per process; `model=None` is a deployment with no key."""

    def __init__(
        self,
        dispatch: Dispatch,
        model: BaseChatModel | None,
        *,
        step_limit: int,
        local_tools: Sequence[BaseTool] = (),
        threads: Threads | None = None,
    ) -> None:
        self._dispatch = dispatch
        self._model = model
        self._step_limit = step_limit
        self._tools = [*surface_tools(dispatch), *local_tools]
        self.threads = threads or Threads()

    @property
    def available(self) -> bool:
        return self._model is not None

    def reply(self, thread: Thread, words: str) -> AsyncIterator[bytes]:
        """Answer `words` in `thread`, one NDJSON line per event.

        The caller checks `available` and `replying` first. This marks the
        thread replying before it returns, with no await in between, so a
        second send arriving while this one streams is refused.
        """
        thread.replying = True
        return self._lines(thread, words)

    async def _lines(self, thread: Thread, words: str) -> AsyncIterator[bytes]:
        turn = Turn(asked=words)
        thread.turns.append(turn)
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        task = asyncio.create_task(self._run(thread, words, queue))
        try:
            while (line := await queue.get()) is not None:
                turn.events.append(json.loads(line))
                yield line + b"\n"
            await task
        finally:
            # The client went away mid-reply: stop spending on an answer nobody reads.
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            thread.replying = False

    async def _run(self, thread: Thread, words: str, queue: asyncio.Queue[bytes | None]) -> None:
        started = time.monotonic()
        stream = StreamingResponse(transport=_Lines(queue), correlation_id=uuid4(), conversation_id=UUID(thread.id))
        tally = _Tally()
        sent = [*thread.messages, HumanMessage(words)]
        ended = "answered"
        try:
            await stream.start()
            agent = create_agent(
                self._model,
                self._tools,
                system_prompt=ASK_SYSTEM,
                middleware=[ModelCallLimitMiddleware(run_limit=self._step_limit, exit_behavior="error")],
            )
            # The graph's own step bound is set far past the call limit, so the call
            # limit is the one that binds. Each model call costs several graph steps
            # (the middleware's, the model's, the tools'), and LangGraph's default of
            # 25 stops an eight-call reply as a fault rather than at its limit.
            config = {"recursion_limit": _GRAPH_STEPS_PER_CALL * (self._step_limit + 1)}
            async for event in agent.astream_events({"messages": sent}, config=config, version="v2"):
                await tally.take(event, stream)
            answer = stream.accumulated_content
            await stream.end(
                metadata={
                    "cost_usd": tally.cost_usd,
                    "uncosted": tally.uncosted,
                    "steps": tally.steps,
                    "cards": cards_for(answer, tally.payloads),
                }
            )
        except ModelCallLimitExceededError:
            ended = "step_limit"
            await stream.error(code=STEP_LIMIT_CODE, message=_stopped_sentence(self._step_limit, tally))
        except asyncio.CancelledError:
            ended = "cancelled"
            await stream.error(code=CANCELLED_ERROR_CODE, message="The reply was stopped.")
            raise
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- reply boundary: a fault ends the stream with an error
            ended = "failed"
            log.exception("ask reply failed in thread %s", thread.id)
            await stream.error(code=DEFAULT_ERROR_CODE, message=f"Ask could not answer: {type(exc).__name__}.")
        finally:
            # A reply stopped before it wrote anything is still a turn the model
            # must see next time, and an empty assistant message is one a provider
            # may refuse; so it says what happened instead.
            said = stream.accumulated_content or f"(I stopped without answering: {ended}.)"
            thread.messages = tally.messages or [*sent, AIMessage(said)]
            log.info(
                "ask reply thread=%s ended=%s steps=%d tool_calls=%d cost_usd=%.5f uncosted=%d seconds=%.1f",
                thread.id,
                ended,
                tally.steps,
                tally.tool_calls,
                tally.cost_usd,
                tally.uncosted,
                time.monotonic() - started,
            )
            await queue.put(None)


class _Lines:
    """A 3tears `StreamTransport` that hands each event to the HTTP response's generator."""

    def __init__(self, queue: asyncio.Queue[bytes | None]) -> None:
        self._queue = queue

    async def publish(self, payload: bytes) -> None:
        await self._queue.put(payload)


@dataclass
class _Tally:
    """What one reply did, read off the graph's events as they pass."""

    steps: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0
    uncosted: int = 0
    payloads: list[object] = field(default_factory=list)
    messages: list[BaseMessage] = field(default_factory=list)
    _started: dict[str, float] = field(default_factory=dict)

    async def take(self, event: Mapping[str, Any], stream: StreamingResponse) -> None:
        kind = event["event"]
        data = event.get("data") or {}
        if kind == "on_chat_model_stream":
            token = _text_of(data["chunk"].content)
            if token:
                await stream.emit_token(token)
        elif kind == "on_chat_model_end":
            self.steps += 1
            cost = (getattr(data.get("output"), "response_metadata", None) or {}).get("cost")
            if isinstance(cost, int | float):
                self.cost_usd += float(cost)
            else:
                self.uncosted += 1
        elif kind == "on_tool_start":
            self.tool_calls += 1
            self._started[event["run_id"]] = time.monotonic()
            summary = said(event["name"], data.get("input"))
            await stream.emit_tool_call_start(tool_name=event["name"], arguments_summary=summary)
        elif kind in {"on_tool_end", "on_tool_error"}:
            elapsed = time.monotonic() - self._started.pop(event["run_id"], time.monotonic())
            payload = _payload_of(data.get("output")) if kind == "on_tool_end" else None
            if payload is not None:
                self.payloads.append(payload)
            succeeded = kind == "on_tool_end" and not (isinstance(payload, Mapping) and payload.get("success") is False)
            await stream.emit_tool_call_end(tool_name=event["name"], success=succeeded, elapsed_ms=int(elapsed * 1000))
        elif kind == "on_chain_end" and not event.get("parent_ids"):
            output = data.get("output")
            if isinstance(output, Mapping) and isinstance(output.get("messages"), list):
                self.messages = list(output["messages"])


def surface_tools(dispatch: Dispatch, scope: Mapping[str, frozenset[str]] = ASK_SCOPE) -> list[BaseTool]:
    """The MCP surface's tools in `scope`, as LangChain tools calling `dispatch` on a worker thread.

    The definitions are the surface's own, whole: the agent reads every action a
    tool has. The worker thread is there because the service layer is
    synchronous and one of its calls holds for up to 45 seconds; on the event
    loop that would stop every other request in the process.
    """
    return [
        StructuredTool(
            name=definition.name,
            description=definition.description or "",
            args_schema=definition.inputSchema,
            coroutine=_caller(dispatch, definition.name, scope),
        )
        for definition in tool_definitions()
        if definition.name in scope
    ]


def _caller(dispatch: Dispatch, name: str, scope: Mapping[str, frozenset[str]]) -> Callable[..., Any]:
    async def call(**arguments: object) -> str:
        refused = outside(scope, name, arguments.get("action"))
        payload = refused if refused is not None else await asyncio.to_thread(dispatch, name, arguments)
        # Pictures travel as image blocks on the MCP wire and are not relayed to the model here.
        return json.dumps({key: value for key, value in payload.items() if key != IMAGE_BLOCKS}, default=str)

    return call


def outside(scope: Mapping[str, frozenset[str]], tool: str, action: object) -> dict[str, Any] | None:
    """The teaching error for an action outside `scope`, or None for one inside it."""
    allowed = scope.get(tool)
    if allowed is not None and (action == HELP or action in allowed):
        return None
    available = sorted(f"{name}(action='{each}')" for name, actions in scope.items() for each in actions)
    return {
        "success": False,
        "error": f"{tool}(action={action!r}) is not available here. Available: {', '.join(available)}.",
    }


#: What each tool call is called in the thread, in the curator's words.
_SAID: Final[Mapping[tuple[str, str], str]] = {
    ("art_discovery", "search"): "Searching Wikidata for “{q}”",
    ("art_discovery", "find_topics"): "Looking for topics named “{q}”",
    ("art_discovery", "artist"): "Reading an artist's entry on Wikidata",
    ("art_discovery", "similar_artists"): "Finding artists like them",
    ("art_discovery", "work"): "Reading a work's entry on Wikidata",
    ("art_discovery", "topic"): "Reading a topic's works and artists",
    ("art_catalogue", "list"): "Looking through your library",
    ("art_catalogue", "get"): "Reading a work in your library",
    ("art_catalogue", "topics"): "Looking at your library's topics",
    ("art_catalogue", "topic"): "Looking at a topic in your library",
}


def said(tool: str, arguments: object) -> str:
    """One line for a tool call, as the thread shows it while the agent works."""
    if not isinstance(arguments, Mapping):
        arguments = {}
    if tool.rsplit(".", 1)[-1] == "web_search":  # 3tears names it `threetears.web_search`
        return f"Searching the web for “{arguments.get('query', '')}”"
    action = str(arguments.get("action"))
    if action == HELP:
        return f"Reading how {tool} works"
    template = _SAID.get((tool, action))
    if template is None:
        return f"Trying {tool} {action}"
    return template.format(q=arguments.get("q", ""))


def _stopped_sentence(limit: int, tally: _Tally) -> str:
    spent = f" It cost ${tally.cost_usd:.4f}." if tally.steps else ""
    return f"Ask stopped after {limit} steps without finishing an answer. Try asking for less at once.{spent}"


def _payload_of(output: object) -> object:
    """The JSON a tool returned, from the `ToolMessage` LangGraph hands back; None for one that is not JSON."""
    content = getattr(output, "content", output)
    if not isinstance(content, str):
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _text_of(content: object) -> str:
    """A streamed chunk's text, across the shapes providers send it in."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return ""
