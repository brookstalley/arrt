"""Ask's agent on its own: the step limit it is given, the lines it shows, and a reply the client abandons."""

import asyncio
import json
import logging
import sqlite3
import threading
from decimal import Decimal
from typing import Any

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

from arrt.app import _record_ask_cost
from arrt.ask.agent import _SAID, TURNS_REMEMBERED, Ask, ReplyCost, Threads, said, surface_tools
from arrt.ask.prompt import ASK_SCOPE, ASK_SYSTEM
from arrt.library.services.discovery import SpendTotal
from arrt.persistence.discovery_records import CostStatus, SpendCategory
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
    # The figure in the one writer's words, "at least" for the call that said nothing.
    assert end["metadata"]["summary"] == SpendTotal(cost_usd=PER_CALL, unknown_calls=1).words
    assert end["metadata"]["summary"].startswith("at least $")
    assert end["metadata"]["summary"].endswith(", and 1 call whose cost is unknown")


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


async def test_a_reply_whose_calls_reported_no_cost_records_each_as_unknown_never_as_nothing():
    """Chunk 62: a call answered with no cost on it may have been billed, so the ledger is told so.

    Until then this recorded nothing at all, and the month's total read those
    calls as a known $0.
    """
    recorded: list[ReplyCost] = []
    ask = Ask(
        answered,
        ScriptedModel(replies=[unpriced(calls(SEARCH)), unpriced(says("Done."))]),
        step_limit=8,
        record_cost=recorded.append,
    )

    events = await events_of(ask)

    assert events[-1]["type"] == "stream_end"
    [cost] = recorded
    assert (cost.cost_usd, cost.unknown_calls, cost.unknown_model_id) == (Decimal(0), 2, ANSWERED_BY)
    assert events[-1]["metadata"]["summary"] == "at least $0.00, and 2 calls whose cost is unknown"


async def test_a_reply_with_one_call_costed_and_one_not_records_the_known_cost_and_one_unknown():
    recorded: list[ReplyCost] = []
    ask = Ask(
        answered, ScriptedModel(replies=[calls(SEARCH), unpriced(says("Done."))]), step_limit=8, record_cost=recorded.append
    )

    await events_of(ask)

    [cost] = recorded
    assert (cost.cost_usd, cost.unknown_calls) == (PER_CALL, 1)


async def test_the_step_limits_sentence_says_its_cost_in_the_one_writers_words():
    """Not `$0.0030` formatted here: "at least" when a step said no cost (`SpendTotal.words`)."""
    ask = Ask(
        answered,
        ScriptedModel(replies=[unpriced(calls(SEARCH)), calls(SEARCH), calls(SEARCH)]),
        step_limit=3,
        record_cost=unrecorded,
    )

    events = await events_of(ask)

    assert events[-1]["code"] == "STEP_LIMIT"
    said = SpendTotal(cost_usd=2 * PER_CALL, unknown_calls=1).words
    assert events[-1]["message"].endswith(f" It cost {said}.")
    assert said.startswith("at least $")


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


# -- a call sent that never said what it cost (audit-2 S5) ---------------------------


class CaughtMidCall(ScriptedModel):
    """Answers its first `answers` calls; the next one signals `begun` and holds until `release`.

    The call has been made when `begun` is set, which is the moment a client
    going away leaves a call sent and unanswered. Streaming runs on a worker
    thread, so the hold is the reply's and not the event loop's.
    """

    answers: int = 0
    begun: Any = None
    release: Any = None

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        if len(self.seen) == self.answers:
            self.begun.set()
            self.release.wait(timeout=20)
        yield from super()._stream(messages, stop, run_manager, **kwargs)


async def _abandoned_mid_call(answers: int, replies: list) -> list[ReplyCost]:
    """A reply whose client goes while its call number `answers` + 1 runs; what it recorded."""
    begun, release = threading.Event(), threading.Event()
    recorded: list[ReplyCost] = []
    model = CaughtMidCall(replies=replies, answers=answers, begun=begun, release=release)
    ask = Ask(answered, model, step_limit=8, record_cost=recorded.append)
    lines = ask.reply(ask.threads.open(), "Bruegel")
    assert json.loads(await anext(lines))["type"] == "stream_start"
    assert await asyncio.to_thread(begun.wait, 10), "the held call never began"

    # Released just after the cancel, as a provider answers a client that has
    # gone; the worker thread cannot be interrupted and would otherwise wait out
    # its bound after the test.
    threading.Timer(0.2, release.set).start()
    await lines.aclose()

    return recorded


async def test_a_reply_cancelled_while_its_model_call_runs_records_that_call_as_one_whose_cost_is_unknown():
    """The client goes while the model is answering: the call was sent, nothing said what it cost."""
    [cost] = await _abandoned_mid_call(0, [says("Never read.")])

    assert (cost.cost_usd, cost.unknown_calls) == (Decimal(0), 1)


async def test_a_reply_cancelled_after_a_billed_call_records_both_the_bill_and_the_unanswered_call():
    [cost] = await _abandoned_mid_call(1, [calls(SEARCH), says("Never read.")])

    assert (cost.cost_usd, cost.unknown_calls) == (PER_CALL, 1)


class Answered(Exception):
    """A provider's error as its client raises it: a status, and a message."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.message = f"HTTP {status_code}"


@pytest.mark.parametrize(
    ("refusal", "unknown"),
    [
        (ConnectionError("the provider went away"), 1),
        (TimeoutError("read timed out"), 1),
        (Answered(502), 1),
        (Answered(408), 1),
        (Answered(429), 0),
        (Answered(400), 0),
        (KeySpent(), 0),
    ],
    ids=["no status", "timeout", "502", "408", "429", "400", "403 at the cap"],
)
async def test_a_call_that_failed_is_unknown_unless_the_provider_answered_it(refusal, unknown):
    recorded: list[ReplyCost] = []
    model = RefusedAfterOneCall(replies=[calls(SEARCH)], refusal=refusal)
    ask = Ask(answered, model, step_limit=8, record_cost=recorded.append)

    await events_of(ask)

    [cost] = recorded
    assert (cost.cost_usd, cost.unknown_calls) == (PER_CALL, unknown)


async def test_a_reply_that_answered_leaves_no_call_unknown():
    recorded: list[ReplyCost] = []
    ask = Ask(answered, ScriptedModel(replies=[calls(SEARCH), says("Done.")]), step_limit=8, record_cost=recorded.append)

    await events_of(ask)

    assert [cost.unknown_calls for cost in recorded] == [0]


async def test_a_reply_stopped_at_the_step_limit_leaves_no_call_unknown():
    """The limit stops the loop before the next call is made, so nothing is running when it stops."""
    recorded: list[ReplyCost] = []
    ask = Ask(answered, ScriptedModel(replies=[calls(SEARCH) for _ in range(5)]), step_limit=3, record_cost=recorded.append)

    await events_of(ask)

    assert [cost.unknown_calls for cost in recorded] == [0]


def test_a_reply_s_unanswered_calls_reach_the_ledger_as_rows_whose_cost_is_unknown(services, discovery_store):
    """`_record_ask_cost`, the wiring `create_app` hands Ask: the bill is one row, each unanswered call another at $0."""
    _record_ask_cost(
        services,
        ReplyCost(
            cost_usd=PER_CALL, model_id=ANSWERED_BY, input_tokens=1, output_tokens=1, unknown_calls=2, unknown_model_id="m"
        ),
    )

    rows = [record for record in discovery_store.list_spend_records() if record.category is SpendCategory.ASK_TOKENS]
    assert sorted((record.cost_status, record.cost_usd, record.model_id) for record in rows) == [
        (CostStatus.KNOWN, PER_CALL, ANSWERED_BY),
        (CostStatus.UNKNOWN, Decimal(0), "m"),
        (CostStatus.UNKNOWN, Decimal(0), "m"),
    ]


def test_a_reply_with_only_an_unanswered_call_writes_no_zero_bill(services, discovery_store):
    _record_ask_cost(
        services, ReplyCost(cost_usd=Decimal(0), model_id=None, input_tokens=None, output_tokens=None, unknown_calls=1)
    )

    [row] = discovery_store.list_spend_records()
    assert row.cost_status is CostStatus.UNKNOWN
