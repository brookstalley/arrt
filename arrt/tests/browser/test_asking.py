"""Ask's thread in the browser, against a scripted model and a fake Wikidata.

Everything between the model and the page is real: the agent loop, the
surface's tools, the stream, and the client drawing it as it arrives.
"""

import json
import threading

import pytest
from fakes import FakeRegistry
from scripted_model import HeldModel, ScriptedModel, calls, says, unpriced

from arrt.config import DEFAULT_ASK_STEP_LIMIT
from arrt.library.registry import (
    CommonsFile,
    ItemId,
    RegistryArtist,
    RegistryCreator,
    RegistryPerson,
    RegistryText,
    RegistryTopic,
    RegistryTopicWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
    TopicKind,
)

pytestmark = pytest.mark.browser

HUNTERS = "Q500985"
BAROQUE = "Q37853"
BRUEGEL = "Q43270"
ROTHKO = "Q160149"
SEARCH = ("art_discovery", {"action": "search", "q": "bruegel"})
HARVESTERS_FILE = CommonsFile("https://commons.wikimedia.org/wiki/Special:FilePath/Harvesters.jpg")
MENINAS_FILE = CommonsFile("https://commons.wikimedia.org/wiki/Special:FilePath/Meninas.jpg")
ANSWER = (
    "Bruegel's winter is the obvious place to start.\n\n"
    f"- The Hunters in the Snow, Pieter Brueghel the Elder [{HUNTERS}]\n"
    f"- Pieter Brueghel the Elder [{BRUEGEL}]"
)


@pytest.fixture
def registry():
    bruegel = RegistryCreator(qid=ItemId(BRUEGEL), name=RegistryText("Pieter Brueghel the Elder"))
    return FakeRegistry(
        # A period, so the card's reactions have to write it as taste's `era`.
        topics_found={"baroque": [RegistryTopic(qid=ItemId(BAROQUE), label=RegistryText("Baroque"), kinds=(TopicKind.PERIOD,))]},
        # An artist's and a topic's works, each led by one with no picture, so a
        # card pictured by the first work rather than the first *pictured* one
        # draws nothing.
        artists={
            BRUEGEL: RegistryArtist(
                qid=ItemId(BRUEGEL),
                name=RegistryText("Pieter Brueghel the Elder"),
                born=1525,
                died=1569,
                works=(
                    RegistryWorkEntry(qid=ItemId("Q1"), title=RegistryText("A lost panel"), sitelinks=60),
                    RegistryWorkEntry(
                        qid=ItemId("Q2"), title=RegistryText("The Harvesters"), sitelinks=50, image=HARVESTERS_FILE
                    ),
                ),
                works_total=2,
            ),
        },
        topics={BAROQUE: RegistryTopic(qid=ItemId(BAROQUE), label=RegistryText("Baroque"), kinds=(TopicKind.PERIOD,))},
        topic_works={
            BAROQUE: [
                RegistryTopicWork(qid=ItemId("Q3"), title=RegistryText("Unpictured"), sitelinks=90),
                RegistryTopicWork(qid=ItemId("Q4"), title=RegistryText("Las Meninas"), sitelinks=80, image=MENINAS_FILE),
            ]
        },
        people={
            "rothko": [RegistryPerson(qid=ItemId(ROTHKO), label=RegistryText("Mark Rothko"), born=1903, died=1970)],
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


def test_a_reply_with_a_step_that_reported_no_cost_says_so(ui, ask_model):
    """Not "This reply cost under $0.01." alone, which would read as cheaper than it was."""
    ask_model.replies += [unpriced(calls(SEARCH)), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")

    assert (
        ui.page.locator(".ask-turn").last.locator(".ask-ending").inner_text()
        == "This reply cost under $0.01, and 1 of its steps reported no cost."
    )


def test_each_card_is_a_poster_pictured_by_what_it_names(pictures_load, ask_model):
    """A work by its own picture, an artist by their most renowned pictured work,
    a topic by its first pictured work (the owner, 2026-10-09: "there should
    always be one thumbnail"). Each filled in after the card draws."""
    ui = pictures_load
    ask_model.replies += [
        calls(SEARCH, ("art_discovery", {"action": "find_topics", "q": "baroque"})),
        says(f"{ANSWER}\n- The Baroque [{BAROQUE}]"),
    ]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    for kind in ("work", "artist", "topic"):
        ui.page.wait_for_selector(f".ask-card[data-ask-card='{kind}'] .card-image img")

    def src(kind):
        return ui.page.locator(f".ask-card[data-ask-card='{kind}'] .card-image img").get_attribute("src")

    assert src("work") == "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg?width=330"
    assert src("artist") == f"{HARVESTERS_FILE}?width=330"
    assert src("topic") == f"{MENINAS_FILE}?width=330"
    # Nothing is said of what the library does not hold.
    assert "Not held" not in ui.page.locator(".ask-cards").inner_text()
    assert "In your library" not in ui.page.locator(".ask-cards").inner_text()


def test_a_held_artist_is_pictured_as_library_artists_pictures_them(pictures_load, services, service, ask_model):
    """By their own work's thumbnail, and marked as held, without asking Wikidata for their works."""
    ui = pictures_load
    rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    work = service.add_artwork(title="Untitled", artist_id=rothko.id)
    services.identity.set_artist_identity(rothko.id, ROTHKO)
    ask_model.replies += [calls(("art_discovery", {"action": "search", "q": "rothko"})), says(f"Rothko [{ROTHKO}].")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Colour fields")
    ui.page.wait_for_selector(".ask-card[data-ask-card='artist'] .card-image img")

    card = ui.page.locator(".ask-card[data-ask-card='artist']")
    assert card.locator(".card-image img").get_attribute("src") == f"/api/works/{work.id}/thumbnail"
    assert "In your library" in card.inner_text()


def test_a_card_with_nothing_to_picture_says_so(ui, ask_model):
    """Rothko is found by the search but Wikidata lists no work of his here."""
    ask_model.replies += [calls(("art_discovery", {"action": "search", "q": "rothko"})), says(f"Rothko [{ROTHKO}].")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Colour fields")
    ui.page.wait_for_selector(".ask-card[data-ask-card='artist'] .card-image-absent")

    assert ui.page.locator(".ask-card .card-image-absent").inner_text() == "No picture"
    assert ui.page.locator(".ask-card .card-title").inner_text() == "Mark Rothko"


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

    def test_a_page_opened_mid_reply_waits_for_it_and_fills_in_when_it_ends(self, ui, ask_model):
        """Leaving Ask mid-reply and coming back: the server refuses a second send until the reply ends, so the page waits too."""
        ui.open("#discover")
        ui.page.wait_for_selector("#ask-words")
        ask(ui, "Something wintry")
        ui.page.wait_for_selector(".ask-turn")

        ui.open("#walls")
        ui.page.wait_for_selector("#view h1")
        ui.open("#discover")
        ui.page.wait_for_selector(".ask-waiting")

        assert ui.page.locator("#view button:text-is('Ask')").is_disabled()
        ask_model.release.set()
        ui.page.wait_for_selector(".ask-turn .ask-ending:has-text('cost')", timeout=15_000)
        assert ui.page.locator(".ask-waiting").count() == 0
        assert ui.page.locator("#view button:text-is('Ask')").is_enabled()


def test_an_empty_ask_offers_examples_that_fill_the_box_and_send_nothing(ui, ask_model):
    ask_model.replies += [says("The Delaunays' circle: Kupka, Léger.")]
    ui.open("#discover")
    ui.page.wait_for_selector(".ask-examples")

    # The shipped module's own list, so the test cannot drift from it.
    examples = ui.page.evaluate('async () => (await import("/static/core/asking.js")).EXAMPLES')
    assert len(examples) >= 2
    assert ui.page.locator(".ask-examples button").all_inner_texts() == examples
    ui.page.locator(".ask-examples button").first.click()

    assert ui.page.input_value("#ask-words") == examples[0]
    assert ask_model.seen == [], "an example fills the box; it does not ask"
    assert ui.page.locator(".ask-examples").count() == 0


def test_a_thread_with_something_said_offers_no_examples(ui, ask_model):
    ask_model.replies += [says("Bruegel, perhaps.")]
    ui.open("#discover")
    ui.page.wait_for_selector(".ask-examples")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('cost')")

    assert ui.page.locator(".ask-examples").count() == 0
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")
    ui.open("#discover")
    ui.page.wait_for_selector(".ask-turn")
    assert ui.page.locator(".ask-examples").count() == 0


def test_a_returning_page_draws_the_thread_as_it_was(ui, ask_model):
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")
    live = _settled_turn(ui)

    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")
    ui.open("#discover")
    ui.page.wait_for_selector(".ask-turn")

    assert _settled_turn(ui) == live


def _settled_turn(ui) -> str:
    """The turn's text once a work card's theme picker has read the themes, which it does after the card is drawn."""
    ui.page.wait_for_function("() => !document.querySelector('.ask-turn').innerText.includes('Reading themes')")
    return ui.page.locator(".ask-turn").inner_text()


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


def _affinities(ui) -> dict:
    return json.loads(ui.page.evaluate("async () => JSON.stringify(await (await fetch('/api/affinities')).json())"))


def test_a_card_offers_two_reactions_and_not_this_closes_the_door(ui, ask_model):
    """Two reactions, not three: a reply can name fifteen artists, and three
    buttons a card made the grid buttons rather than pictures (the owner,
    2026-10-09). *Tell me more*, cool and still open, is offered on Taste's rows,
    where `test_taste_and_reactions.py` holds it apart from *not this*."""
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-card")

    artist = ui.page.locator(".ask-card[data-ask-card='artist']")
    assert artist.locator("button").evaluate_all("els => els.map(e => e.getAttribute('aria-label'))") == [
        "more like this: Pieter Brueghel the Elder",
        "not this: Pieter Brueghel the Elder",
    ]
    ui.page.get_by_role("button", name="not this: Pieter Brueghel the Elder").click()
    ui.page.wait_for_selector(".ask-card button:has-text('not this — recorded')")
    (declined,) = _affinities(ui)["affinities"]

    assert (declined["sentiment"], declined["open_to_more"]) == ("declines", False)


def test_reacting_does_not_redraw_the_thread_under_the_curator(ui, ask_model):
    """A judgment is recorded elsewhere and nothing in the thread changes.

    A page that repainted here would move the card the curator was looking at
    out from under the button they had just pressed. Asserted on the node
    itself, which a repaint replaces even when the words come back the same.
    """
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-card")
    ui.page.evaluate("() => { document.querySelector('.ask-answer').dataset.seen = 'before'; }")

    ui.page.get_by_role("button", name="more like this: Pieter Brueghel the Elder").click()
    ui.page.wait_for_selector(".ask-card button:has-text('more like this — recorded')")

    assert ui.page.evaluate("() => document.querySelector('.ask-answer').dataset.seen") == "before"
    assert "Bruegel's winter is the obvious place to start." in ui.page.locator(".ask-answer").inner_text()


def test_reacting_to_a_topic_records_it_under_taste_s_kind_for_it(ui, ask_model):
    """A topic card's reactions write the topic's kind as taste names it: a period is an `era`."""
    ask_model.replies += [
        calls(("art_discovery", {"action": "find_topics", "q": "baroque"})),
        says(f"Try the Baroque [{BAROQUE}]."),
    ]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "Something theatrical")
    ui.page.wait_for_selector(".ask-card")

    ui.page.get_by_role("button", name="more like this: Baroque").click()
    ui.page.wait_for_selector(".ask-card button:has-text('more like this — recorded')")

    (recorded,) = _affinities(ui)["affinities"]
    assert (recorded["kind"], recorded["value"], recorded["derivation"]) == ("era", "Baroque", "stated")


def test_a_thread_the_server_forgot_is_replaced_and_the_words_still_go(ui, ask_model):
    """After a restart the page still holds the old thread's id; the send gets a 404 and must not keep getting it."""
    ask_model.replies += [says("First."), says("Second.")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "One")
    ui.page.wait_for_selector(".ask-turn:nth-child(1) .ask-ending:has-text('cost')")

    # The next send only, as the restarted server answers it.
    ui.page.route(
        "**/api/ask/threads/*/replies",
        lambda route: route.fulfill(
            status=404, content_type="application/json", body=json.dumps({"error": "That thread has gone."})
        ),
        times=1,
    )
    ask(ui, "Two")
    ui.page.wait_for_selector(".ask-turn:nth-child(2) .ask-ending:has-text('cost')")

    assert "Second." in ui.page.locator(".ask-turn").nth(1).inner_text()
    assert "That thread has gone." not in ui.page.inner_text("#view")


class TestWithNoKey:
    @pytest.fixture
    def ask_model(self):
        return None

    def test_ask_says_it_needs_a_key(self, ui):
        ui.open("#discover")
        ui.page.wait_for_selector("#ask-words")

        assert "Ask needs an OpenRouter key" in ui.page.locator(".panel.ask").inner_text()
