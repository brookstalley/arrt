"""The evaluation harness's own machinery, driven by a scripted model.

Unmarked and free: nothing here reaches a provider. The "model" is a stub that
emits a fixed sequence of tool calls, which makes the loop deterministic and
means these run in the ordinary suite — `uv run pytest`, with no extra group.
That is why `langchain-core` is declared in `dev` rather than `eval`: these
guards were briefly declared only in `eval`, which left every one of them
skipping in the suite CI and the gates actually run, so hand-written harness
code sat green without a single guard executing.

They exist because the driver is code this repo wrote, and the first real run
is the worst possible place to discover a bug in it — a failure there is
ambiguous between "the surface is hard to navigate", which is the finding the
evaluation is for, and "the loop is broken", which is not a finding at all.
Everything the driver does that is not the model's doing is pinned here: that
the tools handed over are the server's own, that calls reach the real service
layer, that the transcript records them, that a bad tool name is survived, and
that a looping model is stopped.
"""

from driver import drive
from langchain_core.messages import AIMessage


class ScriptedModel:
    """A stand-in for a chat model that replays a fixed list of turns.

    Mirrors only the surface `drive` uses: `bind_tools` returns something with
    `ainvoke`. It records what it was offered, so a test can assert the driver
    handed over the server's real definitions rather than a reconstruction.
    """

    def __init__(self, turns):
        self._turns = list(turns)
        self.offered_tools = None
        self.prompts = []

    def bind_tools(self, tools):
        self.offered_tools = tools
        return self

    async def ainvoke(self, messages):
        self.prompts.append(messages)
        if not self._turns:
            return AIMessage(content="I have run out of scripted turns.")
        return self._turns.pop(0)


def _call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


async def test_the_model_is_offered_the_servers_own_tool_definitions(server_url):
    """Not a reconstruction. A description edit has to reach the model."""
    model = ScriptedModel([AIMessage(content="Nothing to do.")])

    await drive(server_url, model, goal="Say nothing.", budget=4)

    offered = {tool["function"]["name"]: tool["function"] for tool in model.offered_tools}
    assert set(offered) == {"art_catalogue", "art_discovery", "art_display", "art_review", "art_taste", "art_theme"}

    # The description is the server's, carried through untouched — this is the
    # property that makes the evaluation able to see description drift at all.
    from arrt.mcp import registry
    from arrt.mcp.tools import TOOLS_BY_NAME

    assert offered["art_theme"]["description"] == registry.description(TOOLS_BY_NAME["art_theme"])
    assert offered["art_theme"]["parameters"] == registry.input_schema(TOOLS_BY_NAME["art_theme"])


async def test_a_tool_call_reaches_the_real_service_and_is_recorded(server_url, ready_work):
    """The loop's actual work: execute, feed the result back, record the call."""
    work = ready_work(title="The Starry Night")
    model = ScriptedModel([_call("art_catalogue", {"action": "list"}), AIMessage(content="One work.")])

    outcome = await drive(server_url, model, goal="List the works.", budget=4)

    assert outcome.transcript.steps == ["art_catalogue(action='list')"]
    assert not outcome.transcript.failures
    assert outcome.answer == "One work."

    # The result was fed back rather than dropped — the model's second turn saw
    # a tool message carrying the payload, which is what lets it answer at all.
    fed_back = str(model.prompts[-1])
    assert work.id in fed_back
    assert "The Starry Night" in fed_back


async def test_a_failing_call_is_recorded_and_the_run_continues(server_url):
    """A model's bad action is a measurement, not a crash."""
    model = ScriptedModel(
        [
            _call("art_theme", {"action": "sculpt"}),
            _call("art_theme", {"action": "list"}, call_id="c2"),
            AIMessage(content="Recovered."),
        ]
    )

    outcome = await drive(server_url, model, goal="List the themes.", budget=6)

    assert [call.succeeded for call in outcome.transcript.calls] == [False, True]
    assert len(outcome.transcript.failures) == 1
    assert outcome.answer == "Recovered."


async def test_a_tool_name_that_does_not_exist_is_survived(server_url):
    """The one failure the surface cannot answer with a teaching error."""
    model = ScriptedModel([_call("art_frame", {"action": "list"}), AIMessage(content="That tool is not there.")])

    outcome = await drive(server_url, model, goal="Use a tool that does not exist.", budget=4)

    assert len(outcome.transcript.calls) == 1
    assert outcome.transcript.calls[0].succeeded is False
    assert outcome.answered, "the run did not survive an unknown tool name"


async def test_a_looping_model_is_stopped_at_the_budget(server_url):
    """The failure a confusing surface provokes, and it must not hang the suite."""
    model = ScriptedModel([_call("art_catalogue", {"action": "list"}, call_id=f"c{n}") for n in range(20)])

    outcome = await drive(server_url, model, goal="Loop forever.", budget=3)

    assert outcome.stopped_on_budget
    assert len(outcome.transcript.calls) <= 3
    assert "STOPPED" in str(outcome)


async def test_a_scope_offers_only_its_tools_and_refuses_an_action_outside_it_unsent(server_url, ready_work, service):
    """Ask's agent is offered whole definitions and refused what it may not do; the refusal must not reach the server."""
    work = ready_work(title="The Starry Night")
    model = ScriptedModel(
        [
            _call("art_catalogue", {"action": "archive", "artwork_id": work.id}),
            _call("art_catalogue", {"action": "help"}, call_id="c2"),
            _call("art_catalogue", {"action": "list"}, call_id="c3"),
            AIMessage(content="Listed."),
        ]
    )

    outcome = await drive(server_url, model, goal="Archive it.", budget=6, scope={"art_catalogue": frozenset({"list"})})

    assert [tool["function"]["name"] for tool in model.offered_tools] == ["art_catalogue"]
    assert [(call.action, call.succeeded) for call in outcome.transcript.calls] == [
        ("archive", False),
        ("help", True),
        ("list", True),
    ]
    refusal = outcome.transcript.calls[0].payload["error"]
    assert "not available here" in refusal
    assert "art_catalogue(action='list')" in refusal
    assert service.get_artwork(work.id).artwork.status == "accepted", "the refused archive reached the service"


async def test_a_local_tool_runs_in_process_and_is_recorded(server_url):
    from langchain_core.tools import tool

    @tool
    def web_search(query: str) -> str:
        """Search the web."""
        return f"1. A page about {query}"

    model = ScriptedModel([_call("web_search", {"query": "Hunters in the Snow"}), AIMessage(content="Found it.")])

    outcome = await drive(server_url, model, goal="Search.", budget=4, scope={}, local_tools=[web_search])

    assert [(call.tool, call.action, call.succeeded) for call in outcome.transcript.calls] == [("web_search", "<local>", True)]
    assert "A page about Hunters in the Snow" in str(model.prompts[-1])


async def test_steps_and_cost_are_summed_and_an_uncosted_reply_is_counted(server_url):
    costed = _call("art_catalogue", {"action": "list"})
    costed.response_metadata = {"finish_reason": "tool_calls", "cost": 0.002}
    final = AIMessage(content="Done.", response_metadata={"finish_reason": "stop"})
    model = ScriptedModel([costed, final])

    outcome = await drive(server_url, model, goal="List.", budget=4)

    assert (outcome.steps, outcome.cost_usd, outcome.uncosted) == (2, 0.002, 1)
    assert outcome.finish_reasons == ["tool_calls", "stop"]
    assert not outcome.provider_failed


async def test_a_provider_error_is_its_own_outcome_not_a_silent_model(server_url):
    model = ScriptedModel([AIMessage(content="", response_metadata={"finish_reason": "error"})])

    outcome = await drive(server_url, model, goal="List.", budget=4)

    assert outcome.provider_failed
    assert not outcome.answered
    assert "the provider answered with an error" in str(outcome)
