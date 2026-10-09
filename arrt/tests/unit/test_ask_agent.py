"""Ask's agent on its own: the step limit it is given, the lines it shows, and a reply the client abandons."""

import asyncio
import json
import threading

from langchain_core.messages import HumanMessage, ToolMessage
from scripted_model import ScriptedModel, calls, says
from threetears.agent.tools.builtin.web_search import create_web_search_tool

from arrt.ask.agent import TURNS_REMEMBERED, Ask, Threads, said, surface_tools
from arrt.ask.prompt import ASK_SCOPE

SEARCH = ("art_discovery", {"action": "search", "q": "bruegel"})


def answered(_name, _arguments):
    return {"success": True, "works": []}


async def events_of(ask: Ask, words: str = "Bruegel") -> list[dict]:
    thread = ask.threads.open()
    return [json.loads(line) async for line in ask.reply(thread, words)]


async def test_the_step_limit_it_is_given_is_the_one_that_binds():
    model = ScriptedModel(replies=[calls(SEARCH) for _ in range(5)])
    ask = Ask(answered, model, step_limit=3)

    events = await events_of(ask)

    assert events[-1]["code"] == "STEP_LIMIT"
    assert "stopped after 3 steps" in events[-1]["message"]
    assert len(model.seen) == 3


async def test_a_thread_is_replying_until_its_stream_is_read_to_the_end():
    ask = Ask(answered, ScriptedModel(replies=[says("Hello.")]), step_limit=8)
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
    ask = Ask(held, model, step_limit=8)
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


async def test_a_reply_stopped_before_it_said_anything_is_remembered_as_a_sentence():
    ask = Ask(answered, ScriptedModel(replies=[calls(SEARCH) for _ in range(3)]), step_limit=2)
    thread = ask.threads.open()
    [line async for line in ask.reply(thread, "Bruegel")]

    assert thread.messages[-1].content == "(I stopped without answering: step_limit.)"


def test_a_reply_dropped_before_it_starts_frees_the_thread():
    """The server can drop a stream before it first reads it, when the client goes while the response starts.

    The stream's own `finally` never runs then, so without a release on
    collection the thread would refuse every send until it was evicted.
    """
    ask = Ask(answered, ScriptedModel(replies=[]), step_limit=8)
    thread = ask.threads.open()

    lines = ask.reply(thread, "Hi")
    assert thread.replying is True
    del lines

    assert thread.replying is False


def test_an_old_reply_collected_late_does_not_free_a_newer_one():
    ask = Ask(answered, ScriptedModel(replies=[]), step_limit=8)
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
    ask = Ask(answered, model, step_limit=8)
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
