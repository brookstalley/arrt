"""The tool loop: a model on one end, the real MCP surface on the other.

Nothing here is a mock. The tools the model is offered are the ones
`list_tools` renders from the registry — the same descriptions, the same
schemas, byte for byte — and every call it makes goes over HTTP to a running
server and through the real service layer. That is the whole point: a harness
that reconstructed the tool definitions would be measuring its own copy, and a
description edit, which is the drift this is most needed for, would not reach
it.

Execution goes through the contract suite's `Caller`, so a model-driven run and
a scripted one produce the same `Transcript` and the same envelope invariant
checks. The reference route the scripted flow takes is the yardstick a model's
route is compared against.
"""

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, ToolException
from mcp.shared.exceptions import McpError

from arrt.ask.agent import outside

# The contract suite's runner. Its directory is on `sys.path` under pytest's
# default import mode, but only once something in it has been collected, and
# collection order is not something to rest on.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "contract"))

from scenarios import REFERENCE_ROUTE, Call, Transcript, connect

#: What the scripted flow takes to put a work on the wall, derived from the one
#: place that route is written rather than counted here. If the flow ever needs
#: another round trip the model's allowance follows it, instead of silently
#: tightening while both numbers stay individually true.
REFERENCE_CALLS = len(REFERENCE_ROUTE)

#: Deliberately thin. The surface is supposed to explain itself — the server's
#: own instructions tell a client to start at `help`, and every error teaches.
#: A system prompt that coached the model through the five tools would be
#: measuring the prompt instead of the surface.
SYSTEM = (
    "You are helping a curator manage the art shown on a Samsung Frame television. "
    "Use the available tools to accomplish what is asked, then state plainly what you did "
    "or what you found. If a tool call fails, read the error — it lists what is valid."
)


#: What a tool call to something outside the run's scope is recorded under.
#: The tool name is the one the model sent; the action is this marker.
LOCAL = "<local>"


@dataclass
class Outcome:
    """What a driven run produced, and what it cost to get there."""

    transcript: Transcript
    answer: str
    stopped_on_budget: bool
    #: How many times the model was asked: one per reply, tool-calling or final.
    steps: int = 0
    #: The provider's own figure, summed over the replies that carried one.
    cost_usd: float = 0.0
    #: Replies that carried no cost, so `cost_usd` is known to be short by them.
    uncosted: int = 0
    #: Each reply's `finish_reason`, in order, as the provider gave it.
    finish_reasons: list[str] = field(default_factory=list)

    @property
    def answered(self) -> bool:
        return bool(self.answer.strip())

    @property
    def provider_failed(self) -> bool:
        """The last reply was the provider's error, not the model's answer.

        Its own state rather than a quiet `answered=False`: a provider refusing
        mid-run and a model that never answers read alike otherwise, and only the
        second says anything about the model or the surface.
        """
        return bool(self.finish_reasons) and self.finish_reasons[-1] == "error"

    def __str__(self) -> str:
        parts = [
            f"{len(self.transcript.calls)} calls ({len(self.transcript.failures)} failed), {self.steps} steps",
            f"cost: ${self.cost_usd:.5f}" + (f" ({self.uncosted} replies uncosted)" if self.uncosted else ""),
            f"route: {self.transcript}",
        ]
        if self.stopped_on_budget:
            parts.append("STOPPED: exhausted the call budget")
        if self.provider_failed:
            parts.append("STOPPED: the provider answered with an error")
        if self.answered:
            parts.append(f"answer: {self.answer[:400]}")
        return "\n  ".join(["", *parts])


def _as_openai_tool(tool: Any) -> dict[str, Any]:
    """One MCP tool definition in the shape `bind_tools` accepts.

    A translation of the envelope only — name, description and schema are
    passed through untouched, so what the model reads is what the registry
    rendered.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema,
        },
    }


async def drive(
    server_url: str,
    model: Any,
    *,
    goal: str,
    budget: int,
    system: str = SYSTEM,
    scope: Mapping[str, frozenset[str]] | None = None,
    local_tools: Sequence[BaseTool] = (),
) -> Outcome:
    """Give a model the live tool surface and a goal; run until it stops.

    `budget` caps tool calls, not turns. A model that loops — the failure this
    guards against, and one a confusing surface provokes — stops at the cap and
    the run is reported as budget-exhausted rather than hanging.

    `scope`, when given, names the tools offered and the actions each may take
    beside `help`. The definitions offered are still the server's own, whole: a
    model reads every action a tool has, and one outside the scope is answered
    with a teaching error naming what is in it, never sent. That is the
    measurement Ask needs, since its agent is offered the same definitions.

    `local_tools` run in this process beside the surface, such as web search.
    """
    async with connect(server_url) as caller:
        offered = [tool for tool in await caller.list_tools() if scope is None or tool.name in scope]
        local = {tool.name: tool for tool in local_tools}
        bound = model.bind_tools([*(_as_openai_tool(tool) for tool in offered), *local.values()])

        messages: list[Any] = [SystemMessage(system), HumanMessage(goal)]
        stopped_on_budget = False
        outcome = Outcome(transcript=caller.transcript, answer="", stopped_on_budget=False)

        while True:
            reply: AIMessage = await bound.ainvoke(messages)
            messages.append(reply)
            _count(outcome, reply)

            if not reply.tool_calls:
                break

            if len(caller.transcript.calls) + len(reply.tool_calls) > budget:
                stopped_on_budget = True
                break

            for request in reply.tool_calls:
                if request["name"] in local:
                    payload = await _run_local(caller, local[request["name"]], request)
                elif (refused := _outside(scope, request)) is not None:
                    payload = refused
                    action = (request.get("args") or {}).get("action")
                    caller.transcript.calls.append(Call(request["name"], str(action), False, payload))
                else:
                    payload = await _execute(caller, request)
                # **The model is fed the payload and not the image blocks, and
                # that is a stated limitation rather than an oversight.** A tool
                # result may carry pictures — `art_review` does — and relaying
                # them would mean assembling a multimodal tool message per
                # provider. Until that lands, this harness cannot measure the one
                # claim the review gate rests on: that the model was shown the
                # image. `caller.transcript` still records the block counts, so a
                # scenario asserting the pictures arrived is meaningful; what is
                # not yet measurable here is whether a *model* uses them.
                messages.append(
                    ToolMessage(
                        content=json.dumps(payload, default=str),
                        tool_call_id=request["id"],
                    )
                )

        outcome.answer = _text_of(reply)
        outcome.stopped_on_budget = stopped_on_budget
        return outcome


def _count(outcome: Outcome, reply: AIMessage) -> None:
    """Add one reply to the run's steps, cost and finish reasons."""
    outcome.steps += 1
    metadata = reply.response_metadata or {}
    outcome.finish_reasons.append(str(metadata.get("finish_reason")))
    cost = metadata.get("cost")
    if isinstance(cost, int | float):
        outcome.cost_usd += float(cost)
    else:
        outcome.uncosted += 1


def _outside(scope: Mapping[str, frozenset[str]] | None, request: Mapping[str, Any]) -> dict[str, Any] | None:
    """The teaching error for a call outside the run's scope, or None for one inside it.

    The shipped agent's own refusal, so the eval measures a model against what
    Ask actually says rather than against a copy of it.
    """
    if scope is None:
        return None
    return outside(scope, request["name"], (request.get("args") or {}).get("action"))


async def _run_local(caller: Any, tool: BaseTool, request: Mapping[str, Any]) -> dict[str, Any]:
    """Run a tool that lives in this process, and record it as the surface's calls are recorded.

    A `ToolException` is the tool saying it could not answer, which a model can
    read and recover from; anything else is a defect in the harness or the tool
    and is left to raise.
    """
    try:
        payload = {"success": True, "result": str(await tool.ainvoke(request.get("args") or {}))}
    except ToolException as exc:
        payload = {"success": False, "error": str(exc)}
    caller.transcript.calls.append(Call(tool.name, LOCAL, payload["success"], payload))
    return payload


async def _execute(caller: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Run one requested call, turning a rejected tool name into a readable result.

    A model naming a tool that does not exist is a navigation failure worth
    measuring, not an exception worth raising — and the surface already answers
    an unknown *action* with a teaching error, so the unknown-*tool* case is
    given the same shape rather than crashing the run.
    """
    arguments = request.get("args") or {}
    try:
        return await caller.invoke(request["name"], arguments)
    except McpError as exc:
        # Narrow on purpose. `invoke` asserts the envelope invariants, and a
        # broad catch here would turn a real contract violation into "the model
        # made a bad call" — hiding the finding inside the measurement.
        payload = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
        caller.transcript.calls.append(Call(request["name"], "<rejected>", False, payload))
        return payload


def _text_of(reply: AIMessage) -> str:
    """The model's final text, across the shapes providers return it in."""
    content = reply.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return str(content)
