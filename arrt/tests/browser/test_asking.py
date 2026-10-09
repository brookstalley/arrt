"""Ask's thread in the browser, against a scripted model and a fake Wikidata.

Everything between the model and the page is real: the agent loop, the
surface's tools, the stream, and the client drawing it as it arrives.
"""

import json
import threading

import pytest
from fakes import FakeRegistry
from scripted_model import HeldModel, ScriptedModel, calls, says

from arrt.config import DEFAULT_ASK_STEP_LIMIT
from arrt.library.registry import CommonsFile, ItemId, RegistryCreator, RegistryPerson, RegistryText, RegistryWorkMatch

pytestmark = pytest.mark.browser

HUNTERS = "Q500985"
BRUEGEL = "Q43270"
SEARCH = ("art_discovery", {"action": "search", "q": "bruegel"})
ANSWER = (
    "Bruegel's winter is the obvious place to start.\n\n"
    f"- The Hunters in the Snow, Pieter Brueghel the Elder [{HUNTERS}]\n"
    f"- Pieter Brueghel the Elder [{BRUEGEL}]"
)


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
            ]
        },
    )


@pytest.fixture
def ask_model():
    return ScriptedModel(replies=[])


def ask(ui, words: str) -> None:
    ui.page.fill("#ask-words", words)
    ui.page.click("#view button:text-is('Ask')")


def test_a_reply_shows_what_it_looked_at_its_answer_its_cards_and_its_cost(ui, ask_model):
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")

    turn = ui.page.locator(".ask-turn").last
    assert turn.locator(".ask-asked").inner_text() == "You: Something wintry"
    step = turn.locator(".ask-step")
    assert step.locator(".glyph").inner_text() == "●"
    assert step.inner_text().endswith("Searching Wikidata for “bruegel”")
    answer = turn.locator(".ask-answer").inner_text()
    assert "Bruegel's winter is the obvious place to start." in answer
    assert "[Q" not in answer, "the cited items are cards, not identifiers in the words"
    assert turn.locator(".ask-answer li").count() == 2
    cards = turn.locator(".ask-card")
    assert cards.count() == 2
    assert "The Hunters in the Snow" in cards.nth(0).inner_text()
    assert cards.nth(0).get_by_role("button", name="Get this work").count() == 1
    assert "Pieter Brueghel the Elder" in cards.nth(1).inner_text()
    assert cards.nth(1).get_by_role("button", name="more like this: Pieter Brueghel the Elder").count() == 1
    assert turn.locator(".ask-ending").inner_text() == "This reply cost under $0.01."


def test_a_step_that_could_not_answer_is_marked_as_gone_wrong(ui, ask_model):
    ask_model.replies += [calls(("art_discovery", {"action": "start", "intent": "Bruegel"})), says("I cannot start a Get.")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Get me Bruegel")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")

    step = ui.page.locator(".ask-step")
    assert step.locator(".glyph").inner_text() == "▲"
    assert step.inner_text().endswith("Trying art_discovery start — it could not answer")
    assert ui.page.locator(".ask-status").inner_text() == "This reply cost under $0.01."


class TestEnter:
    @pytest.fixture
    def ask_model(self):
        return HeldModel(replies=[says("At last."), says("And again.")], release=threading.Event())

    def test_enter_sends_and_waits_while_a_reply_streams(self, ui, ask_model):
        ui.open("#discover")
        ui.page.wait_for_selector("#ask-words")

        ui.page.fill("#ask-words", "Something wintry")
        ui.page.press("#ask-words", "Enter")
        ui.page.wait_for_selector(".ask-turn")
        ui.page.fill("#ask-words", "Not Bruegel")
        ui.page.press("#ask-words", "Enter")

        assert ui.page.locator(".ask-turn").count() == 1, "Enter sent while a reply was streaming"
        ask_model.release.set()
        ui.page.wait_for_selector(".ask-turn .ask-ending:has-text('cost')")
        assert ui.page.locator("#view .act-failure, #view .error-text, #error:not([hidden])").count() == 0
        assert len(ask_model.seen) == 1

        # Nothing streaming now: Enter sends what is in the box.
        ui.page.press("#ask-words", "Enter")
        ui.page.wait_for_selector(".ask-turn:nth-child(2) .ask-ending:has-text('cost')")
        assert ui.page.locator(".ask-asked").all_inner_texts() == ["You: Something wintry", "You: Not Bruegel"]


def test_a_returning_page_draws_the_thread_as_it_was(ui, ask_model):
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")
    live = ui.page.locator(".ask-turn").inner_text()

    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")
    ui.open("#discover")
    ui.page.wait_for_selector(".ask-turn")

    assert ui.page.locator(".ask-turn").inner_text() == live


def test_a_second_turn_follows_the_first_and_start_over_clears_them(ui, ask_model):
    ask_model.replies += [says("Bruegel, perhaps."), says("Then Rothko.")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-turn:nth-child(1) .ask-ending:has-text('cost')")
    ask(ui, "Not Bruegel")
    ui.page.wait_for_selector(".ask-turn:nth-child(2) .ask-ending:has-text('cost')")

    assert ui.page.locator(".ask-asked").all_inner_texts() == ["You: Something wintry", "You: Not Bruegel"]
    ui.page.click("#view button:text-is('Start over')")
    ui.page.wait_for_function("() => document.querySelectorAll('.ask-turn').length === 0")


def test_a_reply_that_reaches_the_step_limit_says_so_in_the_thread(ui, ask_model):
    ask_model.replies += [calls(SEARCH) for _ in range(DEFAULT_ASK_STEP_LIMIT + 1)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Everything by everyone")
    ui.page.wait_for_selector(".ask-ending .error-text")

    ending = ui.page.locator(".ask-ending").inner_text()
    assert f"Ask stopped after {DEFAULT_ASK_STEP_LIMIT} steps without finishing an answer" in ending
    assert ui.page.locator(".ask-step").count() == DEFAULT_ASK_STEP_LIMIT


def test_reacting_to_an_artist_records_it_as_the_curators_own(ui, ask_model, discovery):
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-card")

    ui.page.get_by_role("button", name="more like this: Pieter Brueghel the Elder").click()
    ui.page.wait_for_selector(".ask-card button:has-text('more like this — recorded')")

    affinities = json.loads(ui.page.evaluate("async () => JSON.stringify(await (await fetch('/api/affinities')).json())"))
    (recorded,) = affinities["affinities"]
    assert (recorded["kind"], recorded["value"], recorded["derivation"]) == ("artist", "Pieter Brueghel the Elder", "stated")


class TestWithNoKey:
    @pytest.fixture
    def ask_model(self):
        return None

    def test_ask_says_it_needs_a_key_and_the_page_still_works(self, ui):
        ui.open("#discover")
        ui.page.wait_for_selector("#ask-words")

        assert "Ask needs an OpenRouter key" in ui.page.locator(".panel.ask").inner_text()
        assert ui.page.locator("#intent").count() == 1
