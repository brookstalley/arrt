"""Ask's thread through the real server: the agent loop, the surface's tools, and the stream.

The model is scripted (`scripted_model.py`); everything after it is real:
LangChain's `create_agent`, the MCP surface's tool definitions and `dispatch`,
the registry service over a fake Wikidata, 3tears' `StreamingResponse`, and the
HTTP stream a browser reads.
"""

import json
import logging
import threading
import time

import httpx
import pytest
from fakes import FakeRegistry
from openrouter.errors import ForbiddenResponseError, ForbiddenResponseErrorData
from scripted_model import COST_PER_REPLY, HeldModel, ScriptedModel, calls, says

from arrt.config import DEFAULT_ASK_STEP_LIMIT
from arrt.library.registry import CommonsFile, ItemId, RegistryCreator, RegistryPerson, RegistryText, RegistryWorkMatch

HUNTERS = "Q500985"
HARVESTERS = "Q1050250"
BRUEGEL = "Q43270"

SEARCH = ("art_discovery", {"action": "search", "q": "bruegel"})


@pytest.fixture
def registry():
    bruegel = RegistryCreator(qid=ItemId(BRUEGEL), name=RegistryText("Pieter Brueghel the Elder"))
    return FakeRegistry(
        people={
            "bruegel": [
                RegistryPerson(qid=ItemId(BRUEGEL), label=RegistryText("Pieter Brueghel the Elder"), born=1525, died=1569)
            ],
        },
        matches={
            "bruegel": [
                RegistryWorkMatch(
                    qid=ItemId(HUNTERS),
                    title=RegistryText("The Hunters in the Snow"),
                    sitelinks=39,
                    image=CommonsFile("https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"),
                    creator=bruegel,
                ),
                RegistryWorkMatch(qid=ItemId(HARVESTERS), title=RegistryText("The Harvesters"), sitelinks=30, creator=bruegel),
            ]
        },
    )


@pytest.fixture
def ask_model():
    return ScriptedModel(replies=[])


def open_thread(server_url: str) -> str:
    response = httpx.post(f"{server_url}/api/ask/threads")
    assert response.status_code == 201
    return response.json()["thread_id"]


def send(server_url: str, thread_id: str, words: str) -> list[dict]:
    with httpx.stream("POST", f"{server_url}/api/ask/threads/{thread_id}/replies", json={"words": words}, timeout=30) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("application/x-ndjson")
        return [json.loads(line) for line in response.iter_lines() if line.strip()]


def kinds(events: list[dict]) -> list[str]:
    return [event["type"] for event in events]


def test_a_reply_searches_streams_and_ends_with_its_cost_and_cards(server_url, ask_model):
    ask_model.replies += [
        calls(SEARCH),
        says(f"Bruegel's winter: The Hunters in the Snow, Pieter Brueghel the Elder [{HUNTERS}]. Also [Q999999999]."),
    ]
    thread_id = open_thread(server_url)

    events = send(server_url, thread_id, "Something wintry")

    assert kinds(events)[0] == "stream_start"
    assert kinds(events)[-1] == "stream_end"
    assert kinds(events).count("stream_end") + kinds(events).count("stream_error") == 1
    start = next(event for event in events if event["type"] == "tool_call_start")
    assert start["tool_name"] == "art_discovery"
    assert start["arguments_summary"] == "Searching Wikidata for “bruegel”"
    end_of_call = next(event for event in events if event["type"] == "tool_call_end")
    assert end_of_call["success"] is True
    # Tokens stream before the end, and add up to the answer the end carries.
    tokens = "".join(event["token"] for event in events if event["type"] == "stream_token")
    assert tokens == events[-1]["content"]
    assert len([event for event in events if event["type"] == "stream_token"]) > 1

    metadata = events[-1]["metadata"]
    assert metadata["steps"] == 2
    assert metadata["cost_usd"] == pytest.approx(2 * COST_PER_REPLY)
    assert metadata["uncosted"] == 0
    # The invented item gets no card, and Harvesters, returned but not named, gets none either.
    assert [card["qid"] for card in metadata["cards"]] == [HUNTERS]
    assert metadata["cards"][0]["kind"] == "work"
    assert metadata["cards"][0]["held"] is None


def test_the_tool_answered_is_the_surfaces_own_payload(server_url, ask_model):
    ask_model.replies += [calls(SEARCH), says("Done.")]
    send(server_url, open_thread(server_url), "Bruegel")

    tool_message = ask_model.seen[1][-1]
    payload = json.loads(tool_message.content)
    assert payload["success"] is True
    assert [work["qid"] for work in payload["works"]] == [HUNTERS, HARVESTERS]


def test_an_action_outside_the_scope_is_refused_with_a_teaching_error_and_never_run(server_url, ask_model):
    ask_model.replies += [calls(("art_discovery", {"action": "start", "intent": "Bruegel"})), says("I cannot start a Get.")]
    events = send(server_url, open_thread(server_url), "Get me Bruegel")

    refused = json.loads(ask_model.seen[1][-1].content)
    assert refused["success"] is False
    assert "is not available here" in refused["error"]
    assert "art_discovery(action='search')" in refused["error"]
    assert next(event for event in events if event["type"] == "tool_call_end")["success"] is False
    assert httpx.get(f"{server_url}/api/runs").json()["count"] == 0


def test_a_second_turn_is_given_the_first(server_url, ask_model):
    ask_model.replies += [says("Bruegel, perhaps."), says("Then try Rothko.")]
    thread_id = open_thread(server_url)

    send(server_url, thread_id, "Something wintry")
    send(server_url, thread_id, "Not Bruegel")

    shown = [message.content for message in ask_model.seen[1]]
    assert shown[-3:] == ["Something wintry", "Bruegel, perhaps.", "Not Bruegel"]


def test_a_reply_that_reaches_the_step_limit_says_so(server_url, ask_model):
    ask_model.replies += [calls(SEARCH) for _ in range(DEFAULT_ASK_STEP_LIMIT + 1)]
    events = send(server_url, open_thread(server_url), "Everything by everyone")

    assert kinds(events)[-1] == "stream_error"
    assert "stream_end" not in kinds(events)
    assert events[-1]["code"] == "STEP_LIMIT"
    assert f"stopped after {DEFAULT_ASK_STEP_LIMIT} steps" in events[-1]["message"]
    assert len(ask_model.seen) == DEFAULT_ASK_STEP_LIMIT


def test_a_thread_reads_back_the_events_it_sent(server_url, ask_model):
    ask_model.replies += [calls(SEARCH), says(f"[{HUNTERS}]")]
    thread_id = open_thread(server_url)
    events = send(server_url, thread_id, "Bruegel")

    thread = httpx.get(f"{server_url}/api/ask/threads/{thread_id}").json()

    assert thread["replying"] is False
    assert thread["turns"] == [{"asked": "Bruegel", "events": events}]


def test_a_reply_is_logged_with_its_steps_and_cost(server_url, ask_model, caplog):
    ask_model.replies += [calls(SEARCH), says("Done.")]
    with caplog.at_level(logging.INFO, logger="arrt.ask"):
        send(server_url, open_thread(server_url), "Bruegel")

    (line,) = [record.getMessage() for record in caplog.records if record.name == "arrt.ask"]
    assert "ended=answered" in line
    assert "steps=2" in line
    assert "tool_calls=1" in line
    assert f"cost_usd={2 * COST_PER_REPLY:.5f}" in line


def test_an_unknown_thread_is_a_404(server_url):
    response = httpx.post(f"{server_url}/api/ask/threads/nope/replies", json={"words": "hello"})

    assert response.status_code == 404
    assert "forgotten when the server restarts" in response.json()["error"]


class TestWithNoKey:
    @pytest.fixture
    def ask_model(self):
        return None

    def test_a_reply_is_refused_before_anything_is_spent(self, server_url):
        thread_id = open_thread(server_url)

        response = httpx.post(f"{server_url}/api/ask/threads/{thread_id}/replies", json={"words": "hello"})

        assert response.status_code == 503
        assert "OPENROUTER_API_KEY" in response.json()["error"]
        assert httpx.get(f"{server_url}/api/ask/threads/{thread_id}").json()["available"] is False
        assert httpx.get(f"{server_url}/api/ask").json() == {"available": False}


def test_ask_says_it_can_answer_when_it_has_a_model(server_url):
    assert httpx.get(f"{server_url}/api/ask").json() == {"available": True}


class TestWhileAReplyRuns:
    @pytest.fixture
    def ask_model(self):
        return HeldModel(replies=[says("At last.")], release=threading.Event())

    def test_a_second_send_is_refused_and_the_thread_keeps_one_turn(self, server_url, ask_model):
        thread_id = open_thread(server_url)
        sent: list[list[dict]] = []
        first = threading.Thread(target=lambda: sent.append(send(server_url, thread_id, "Something wintry")))
        first.start()
        deadline = time.monotonic() + 10
        while not httpx.get(f"{server_url}/api/ask/threads/{thread_id}").json()["replying"]:
            assert time.monotonic() < deadline, "the first reply never started"
            time.sleep(0.05)

        second = httpx.post(f"{server_url}/api/ask/threads/{thread_id}/replies", json={"words": "And another"})
        ask_model.release.set()
        first.join(timeout=20)

        assert [events[-1]["type"] for events in sent] == ["stream_end"], "the first reply did not finish"
        assert second.status_code == 409
        assert "still answering" in second.json()["error"]
        thread = httpx.get(f"{server_url}/api/ask/threads/{thread_id}").json()
        assert [turn["asked"] for turn in thread["turns"]] == ["Something wintry"]
        assert thread["replying"] is False


def test_a_fault_ends_the_stream_once_as_agent_failed_and_frees_the_thread(server_url, ask_model, caplog):
    # Nothing scripted: the model raises the moment it is asked.
    thread_id = open_thread(server_url)
    with caplog.at_level(logging.INFO, logger="arrt.ask"):
        events = send(server_url, thread_id, "Bruegel")

    terminals = [event for event in events if event["type"] in {"stream_end", "stream_error"}]
    assert [(event["type"], event["code"]) for event in terminals] == [("stream_error", "AGENT_FAILED")]
    assert terminals[0]["message"] == "Ask could not answer: AssertionError."
    failed = [record for record in caplog.records if record.name == "arrt.ask" and record.levelno == logging.ERROR]
    assert len(failed) == 1
    assert failed[0].exc_info is not None
    assert any("ended=failed" in record.getMessage() for record in caplog.records if record.name == "arrt.ask")
    assert httpx.get(f"{server_url}/api/ask/threads/{thread_id}").json()["replying"] is False


class RefusingModel(ScriptedModel):
    """A model whose provider refuses the call, as OpenRouter does when the key's limit is spent."""

    error: Exception

    def _next(self, messages):
        self.seen.append(list(messages))
        raise self.error


def a_403(message: str) -> ForbiddenResponseError:
    """The error the OpenRouter SDK raises for a 403, as Ask's model does in production."""
    body = {"error": {"message": message, "code": 403}}
    response = httpx.Response(403, json=body, request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    return ForbiddenResponseError(ForbiddenResponseErrorData.model_validate(body), response)


def terminals(events: list[dict]) -> list[dict]:
    return [event for event in events if event["type"] in {"stream_end", "stream_error"}]


class TestAtTheSpendingCap:
    """The owner's ruling 3 of 2026-10-07 (#290): a reply refused at the cap leads with the budget."""

    @pytest.fixture
    def ask_model(self):
        # OpenRouter's own words for a spent key (`openrouter-api-findings.md`, measured).
        return RefusingModel(replies=[], error=a_403("Key limit exceeded (total limit). Manage it using the API keys page."))

    def test_a_reply_refused_at_the_cap_says_the_budget_is_spent(self, server_url):
        (ending,) = terminals(send(server_url, open_thread(server_url), "Bruegel"))

        assert (ending["type"], ending["code"]) == ("stream_error", "BUDGET_SPENT")
        assert ending["message"].startswith("This month's budget is spent")
        assert "Key limit exceeded (total limit)." in ending["message"]


class TestAFlaggedInput:
    """OpenRouter also answers 403 when a moderated model flags the input, which is not the budget."""

    @pytest.fixture
    def ask_model(self):
        return RefusingModel(replies=[], error=a_403("Your chosen model requires moderation and your input was flagged."))

    def test_a_403_that_is_not_the_limit_is_not_called_the_budget(self, server_url):
        (ending,) = terminals(send(server_url, open_thread(server_url), "Bruegel"))

        assert (ending["type"], ending["code"]) == ("stream_error", "AGENT_FAILED")
        assert "budget" not in ending["message"]


def test_words_that_are_only_white_space_are_refused_before_anything_is_spent(server_url, ask_model):
    response = httpx.post(f"{server_url}/api/ask/threads/{open_thread(server_url)}/replies", json={"words": "  \n "})

    assert response.status_code == 422
    assert ask_model.seen == []
