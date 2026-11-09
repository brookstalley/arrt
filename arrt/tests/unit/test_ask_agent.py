"""Ask's agent on its own: the step limit it is given, the lines it shows, and a reply the client abandons."""

import asyncio
import json
import logging
import sqlite3
import threading
from decimal import Decimal

import pytest
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from scripted_model import (
    ANSWERED_BY,
    COST_PER_REPLY,
    INPUT_TOKENS_PER_REPLY,
    OUTPUT_TOKENS_PER_REPLY,
    ScriptedModel,
    answered_by,
    calls,
    says,
    unpriced,
    unreported,
)
from threetears.agent.tools.builtin.web_search import create_web_search_tool

from arrt.ask.agent import _SAID, TURNS_REMEMBERED, Ask, ReplyCost, Threads, said, surface_tools
from arrt.ask.prompt import ASK_SCOPE, ASK_SYSTEM
from arrt.services.errors import ServiceError

SEARCH = ("art_discovery", {"action": "search", "q": "bruegel"})


def answered(_name, _arguments):
    return {"success": True, "works": []}


def unrecorded(_cost: ReplyCost) -> None:
    """For a test about something other than spend."""


#: One scripted call's cost, as the ledger holds it.
PER_CALL = Decimal(str(COST_PER_REPLY))


async def events_of(ask: Ask, words: str = "Bruegel") -> list[dict]:
    thread = ask.threads.open()
    return [json.loads(line) async for line in ask.reply(thread, words)]


async def test_the_step_limit_it_is_given_is_the_one_that_binds():
    model = ScriptedModel(replies=[calls(SEARCH) for _ in range(5)])
    ask = Ask(answered, model, step_limit=3, record_cost=unrecorded)

    events = await events_of(ask)

    assert events[-1]["code"] == "STEP_LIMIT"
    assert "stopped after 3 steps" in events[-1]["message"]
    assert len(model.seen) == 3


async def test_a_step_that_reported_no_cost_is_counted_rather_than_read_as_free():
    model = ScriptedModel(replies=[unpriced(calls(SEARCH)), says("Done.")])
    ask = Ask(answered, model, step_limit=8, record_cost=unrecorded)

    events = await events_of(ask)

    [end] = [event for event in events if event["type"] == "stream_end"]
    assert end["metadata"]["uncosted"] == 1
    assert end["metadata"]["cost_usd"] == COST_PER_REPLY
    assert end["metadata"]["steps"] == 2


async def test_a_thread_is_replying_until_its_stream_is_read_to_the_end():
    ask = Ask(answered, ScriptedModel(replies=[says("Hello.")]), step_limit=8, record_cost=unrecorded)
    thread = ask.threads.open()

    lines = ask.reply(thread, "Hi")
    assert thread.replying is True
    [line async for line in lines]

    assert thread.replying is False


async def test_a_reply_the_client_abandons_stops_and_frees_the_thread():
    release = threading.Event()

    def held(_name, _arguments):
        release.wait(timeout=10)
        return {"success": True}

    model = ScriptedModel(replies=[calls(SEARCH), says("Never reached.")])
    ask = Ask(held, model, step_limit=8, record_cost=unrecorded)
    thread = ask.threads.open()
    lines = ask.reply(thread, "Bruegel")

    first = json.loads(await anext(lines))
    while json.loads(await anext(lines))["type"] != "tool_call_start":
        pass
    await lines.aclose()
    release.set()
    await asyncio.sleep(0.05)

    assert first["type"] == "stream_start"
    assert thread.replying is False
    assert len(model.seen) == 1, "the model was asked again after the client left"


def test_the_threads_kept_are_the_most_recently_used():
    threads = Threads(kept=2)
    first, second = threads.open(), threads.open()
    threads.get(first.id)
    threads.open()

    assert threads.get(first.id) is first
    assert threads.get(second.id) is None


def test_the_agent_is_offered_exactly_the_scoped_tools_whole():
    offered = {tool.name: tool for tool in surface_tools(answered)}

    assert set(offered) == set(ASK_SCOPE)
    # Whole: every action the tool has is in the schema the model reads, not only those in scope.
    actions = offered["art_discovery"].args_schema["properties"]["action"]["enum"]
    assert "start" in actions
    assert "start" not in ASK_SCOPE["art_discovery"]


def test_each_tool_call_is_said_in_the_curators_words():
    web_search = create_web_search_tool({"base_url": "http://searxng.invalid"}, "Search the web.")

    assert said(web_search.name, {"query": "Dalí early works"}) == "Searching the web for “Dalí early works”"
    assert said("art_discovery", {"action": "search", "q": "Dalí"}) == "Searching Wikidata for “Dalí”"
    assert said("art_catalogue", {"action": "help"}) == "Reading how art_catalogue works"
    assert said("art_display", {"action": "show_now"}) == "Trying art_display show_now"
    assert said("art_catalogue", None) == "Trying art_catalogue None"
    assert (
        said("art_taste", {"action": "set", "kind": "artist", "value": "Klimt", "sentiment": "declines"})
        == "Recording your taste: declines “Klimt”"
    )


def test_every_action_in_scope_has_a_line_in_the_curators_words_and_none_outside_it():
    """`_SAID` copies the scope; one added to `ASK_SCOPE` alone would show as "Trying …"."""
    in_scope = {(tool, action) for tool, actions in ASK_SCOPE.items() for action in actions}

    assert set(_SAID) == in_scope


async def test_a_reply_stopped_before_it_said_anything_is_remembered_as_a_sentence():
    ask = Ask(answered, ScriptedModel(replies=[calls(SEARCH) for _ in range(3)]), step_limit=2, record_cost=unrecorded)
    thread = ask.threads.open()
    [line async for line in ask.reply(thread, "Bruegel")]

    assert thread.messages[-1].content == "(I stopped without answering: step_limit.)"


def test_a_reply_dropped_before_it_starts_frees_the_thread():
    """The server can drop a stream before it first reads it, when the client goes while the response starts.

    The stream's own `finally` never runs then, so without a release on
    collection the thread would refuse every send until it was evicted.
    """
    ask = Ask(answered, ScriptedModel(replies=[]), step_limit=8, record_cost=unrecorded)
    thread = ask.threads.open()

    lines = ask.reply(thread, "Hi")
    assert thread.replying is True
    del lines

    assert thread.replying is False


def test_an_old_reply_collected_late_does_not_free_a_newer_one():
    ask = Ask(answered, ScriptedModel(replies=[]), step_limit=8, record_cost=unrecorded)
    thread = ask.threads.open()
    first = ask.reply(thread, "Hi")
    thread.claim = None  # the first reply ended
    second = ask.reply(thread, "Again")

    del first

    assert thread.replying is True
    del second


async def test_the_model_is_sent_only_the_turns_remembered_and_the_thread_keeps_no_more():
    """Every reply resends the thread, so a thread is bounded by turns, cut where the curator spoke."""
    turns = TURNS_REMEMBERED + 3
    model = ScriptedModel(replies=[reply for _ in range(turns) for reply in (calls(SEARCH), says("Noted."))])
    ask = Ask(answered, model, step_limit=8, record_cost=unrecorded)
    thread = ask.threads.open()

    for index in range(turns):
        [line async for line in ask.reply(thread, f"Ask {index}")]

    last_sent = model.seen[-2]
    asked = [message.content for message in last_sent if isinstance(message, HumanMessage)]
    assert asked == [f"Ask {index}" for index in range(turns - TURNS_REMEMBERED, turns)]
    # A tool result is never sent without the call it answers.
    assert not isinstance(last_sent[0], ToolMessage)
    assert [turn.asked for turn in thread.turns] == [f"Ask {index}" for index in range(turns - TURNS_REMEMBERED, turns)]
    assert sum(isinstance(message, HumanMessage) for message in thread.messages) == TURNS_REMEMBERED


def system_prompt_of(model: ScriptedModel, call: int = 0) -> str:
    [system] = [message for message in model.seen[call] if isinstance(message, SystemMessage)]
    return str(system.content)


async def test_the_taste_is_in_the_system_prompt_below_the_standing_instruction():
    model = ScriptedModel(replies=[says("Noted.")])
    ask = Ask(answered, model, step_limit=8, record_cost=unrecorded, taste=lambda: "- loves artist “Klimt”: keep offering more")

    await events_of(ask)

    sent = system_prompt_of(model)
    assert sent.startswith(ASK_SYSTEM)
    assert sent.endswith("- loves artist “Klimt”: keep offering more")


async def test_no_taste_sends_the_standing_instruction_alone():
    model = ScriptedModel(replies=[says("Noted.")])
    ask = Ask(answered, model, step_limit=8, record_cost=unrecorded, taste=lambda: "")

    await events_of(ask)

    assert system_prompt_of(model) == ASK_SYSTEM


async def test_the_taste_is_read_afresh_for_every_reply():
    """A judgment recorded in one reply has to be in the next reply's prompt."""
    taste = ["- likes artist “Klimt”: keep offering more"]
    model = ScriptedModel(replies=[says("One."), says("Two.")])
    ask = Ask(answered, model, step_limit=8, record_cost=unrecorded, taste=lambda: taste[0])
    thread = ask.threads.open()

    [line async for line in ask.reply(thread, "first")]
    taste[0] = "- declines artist “Klimt”: offer no more"
    [line async for line in ask.reply(thread, "second")]

    assert system_prompt_of(model, 0).endswith("likes artist “Klimt”: keep offering more")
    assert system_prompt_of(model, 1).endswith("declines artist “Klimt”: offer no more")


async def test_a_reply_that_records_taste_says_so_in_its_log_line(caplog):
    """Threads are not stored, so the reply's log line is what says Ask wrote a judgment, and in which thread."""
    record = ("art_taste", {"action": "set", "kind": "artist", "value": "Klimt", "sentiment": "loves", "open_to_more": True})
    reads = ("art_taste", {"action": "list"})
    ask = Ask(answered, ScriptedModel(replies=[calls(record, reads), says("Noted.")]), step_limit=8, record_cost=unrecorded)
    thread = ask.threads.open()

    with caplog.at_level("INFO", logger="arrt.ask"):
        [line async for line in ask.reply(thread, "I love Klimt")]

    [logged] = [entry.getMessage() for entry in caplog.records if entry.getMessage().startswith("ask reply")]
    assert f"thread={thread.id}" in logged
    assert "tool_calls=2 taste_writes=1" in logged


async def test_ask_may_record_taste_but_never_forget_it():
    """`set` reaches the surface; `delete` is answered with the teaching error and never dispatched."""
    reached = []

    def recording(name, arguments):
        reached.append((name, arguments["action"]))
        return {"success": True}

    record = ("art_taste", {"action": "set", "kind": "artist", "value": "Klimt", "sentiment": "loves", "open_to_more": True})
    forget = ("art_taste", {"action": "delete", "affinity_id": "affinity-1"})
    model = ScriptedModel(replies=[calls(record), calls(forget), says("Done.")])
    ask = Ask(recording, model, step_limit=8, record_cost=unrecorded)

    events = await events_of(ask)

    assert reached == [("art_taste", "set")]
    ends = [event for event in events if event["type"] == "tool_call_end"]
    assert [event["success"] for event in ends] == [True, False]


# -- what a reply spent reaches the ledger ---------------------------------------


async def test_a_reply_records_once_what_all_its_calls_were_billed():
    recorded: list[ReplyCost] = []
    ask = Ask(
        answered, ScriptedModel(replies=[calls(SEARCH), calls(SEARCH), says("Done.")]), step_limit=8, record_cost=recorded.append
    )

    await events_of(ask)

    assert recorded == [
        ReplyCost(
            cost_usd=3 * PER_CALL,
            model_id=ANSWERED_BY,
            input_tokens=3 * INPUT_TOKENS_PER_REPLY,
            output_tokens=3 * OUTPUT_TOKENS_PER_REPLY,
        )
    ]
    assert isinstance(recorded[0].cost_usd, Decimal)


async def test_a_reply_whose_calls_reported_no_usage_or_model_records_none_rather_than_zero():
    recorded: list[ReplyCost] = []
    replies = [unreported(calls(SEARCH)), unreported(says("Done."))]
    ask = Ask(answered, ScriptedModel(replies=replies), step_limit=8, record_cost=recorded.append)

    await events_of(ask)

    assert recorded == [ReplyCost(cost_usd=2 * PER_CALL, model_id=None, input_tokens=None, output_tokens=None)]


async def test_a_reply_whose_calls_reported_usage_only_sometimes_sums_what_was_reported():
    recorded: list[ReplyCost] = []
    replies = [unreported(calls(SEARCH)), says("Done.")]
    ask = Ask(answered, ScriptedModel(replies=replies), step_limit=8, record_cost=recorded.append)

    await events_of(ask)

    [cost] = recorded
    assert (cost.model_id, cost.input_tokens, cost.output_tokens) == (
        ANSWERED_BY,
        INPUT_TOKENS_PER_REPLY,
        OUTPUT_TOKENS_PER_REPLY,
    )


async def test_a_reply_answered_by_more_than_one_model_names_none_of_them():
    recorded: list[ReplyCost] = []
    replies = [calls(SEARCH), answered_by("scripted/another-model", says("Done."))]
    ask = Ask(answered, ScriptedModel(replies=replies), step_limit=8, record_cost=recorded.append)

    await events_of(ask)

    [cost] = recorded
    assert cost.model_id is None
    assert cost.cost_usd == 2 * PER_CALL


async def test_each_reply_in_a_thread_records_its_own_cost():
    recorded: list[ReplyCost] = []
    ask = Ask(
        answered, ScriptedModel(replies=[says("One."), calls(SEARCH), says("Two.")]), step_limit=8, record_cost=recorded.append
    )
    thread = ask.threads.open()

    [line async for line in ask.reply(thread, "First")]
    [line async for line in ask.reply(thread, "Second")]

    assert [cost.cost_usd for cost in recorded] == [PER_CALL, 2 * PER_CALL]


async def test_a_reply_stopped_at_the_step_limit_still_records_what_it_spent():
    recorded: list[ReplyCost] = []
    ask = Ask(answered, ScriptedModel(replies=[calls(SEARCH) for _ in range(5)]), step_limit=3, record_cost=recorded.append)

    events = await events_of(ask)

    assert events[-1]["code"] == "STEP_LIMIT"
    assert [cost.cost_usd for cost in recorded] == [3 * PER_CALL]


async def test_a_reply_the_client_abandons_records_what_it_spent_before_it_stopped():
    release = threading.Event()

    def held(_name, _arguments):
        release.wait(timeout=10)
        return {"success": True}

    recorded: list[ReplyCost] = []
    ask = Ask(held, ScriptedModel(replies=[calls(SEARCH), says("Never reached.")]), step_limit=8, record_cost=recorded.append)
    lines = ask.reply(ask.threads.open(), "Bruegel")
    while json.loads(await anext(lines))["type"] != "tool_call_start":
        pass
    await lines.aclose()
    release.set()

    assert [cost.cost_usd for cost in recorded] == [PER_CALL]


async def test_a_reply_whose_calls_reported_no_cost_records_nothing():
    recorded: list[ReplyCost] = []
    ask = Ask(
        answered,
        ScriptedModel(replies=[unpriced(calls(SEARCH)), unpriced(says("Done."))]),
        step_limit=8,
        record_cost=recorded.append,
    )

    events = await events_of(ask)

    assert events[-1]["type"] == "stream_end"
    assert recorded == []


class RefusedAfterOneCall(ScriptedModel):
    """Answers its first call, then raises `refusal` as the provider's client would."""

    refusal: Exception

    def _next(self, messages):
        if self.seen:
            self.seen.append(list(messages))
            raise self.refusal
        return super()._next(messages)


class KeySpent(Exception):
    """OpenRouter's 403 at the key's credit limit, as its client raises it: a status and a message."""

    status_code = 403
    message = "Key limit exceeded (total limit)"


async def test_a_reply_refused_at_the_cap_records_what_it_spent_before_the_refusal():
    recorded: list[ReplyCost] = []
    model = RefusedAfterOneCall(replies=[calls(SEARCH)], refusal=KeySpent())
    ask = Ask(answered, model, step_limit=8, record_cost=recorded.append)

    events = await events_of(ask)

    assert events[-1]["code"] == "BUDGET_SPENT"
    assert [cost.cost_usd for cost in recorded] == [PER_CALL]


async def test_a_reply_that_fails_records_what_it_spent_before_the_fault():
    recorded: list[ReplyCost] = []
    model = RefusedAfterOneCall(replies=[calls(SEARCH)], refusal=ConnectionError("the provider went away"))
    ask = Ask(answered, model, step_limit=8, record_cost=recorded.append)

    events = await events_of(ask)

    assert events[-1]["type"] == "stream_error"
    assert events[-1]["code"] != "BUDGET_SPENT"
    assert [cost.cost_usd for cost in recorded] == [PER_CALL]


@pytest.mark.parametrize(
    "refusal",
    [ServiceError("the catalogue file is read-only"), sqlite3.OperationalError("attempt to write a readonly database")],
    ids=["refused-in-the-services-words", "refused-by-the-driver"],
)
async def test_a_cost_the_ledger_refuses_is_logged_and_the_reply_still_ends(caplog, refusal):
    def refusing(_cost: ReplyCost) -> None:
        raise refusal

    ask = Ask(answered, ScriptedModel(replies=[says("Done.")]), step_limit=8, record_cost=refusing)
    thread = ask.threads.open()

    with caplog.at_level(logging.INFO, logger="arrt.ask"):
        events = [json.loads(line) async for line in ask.reply(thread, "Hi")]

    assert events[-1]["type"] == "stream_end"
    assert thread.replying is False
    messages = [record.getMessage() for record in caplog.records if record.name == "arrt.ask"]
    assert any("its cost was not recorded" in message for message in messages)
    assert any("ended=answered" in message for message in messages), "the reply's own log line was lost"
