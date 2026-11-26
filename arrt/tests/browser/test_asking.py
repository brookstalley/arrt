"""Ask's thread in the browser, against a scripted model and a fake Wikidata.

Everything between the model and the page is real: the agent loop, the
surface's tools, the stream, and the client drawing it as it arrives.
"""

import json
import re
import threading

import pytest
from fakes import FakeRegistry
from payloads import a_run
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
from arrt.persistence.discovery_records import RunStatus

expect = pytest.importorskip("playwright.sync_api").expect

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
            "painters": [
                RegistryPerson(qid=ItemId(f"Q10{n}"), label=RegistryText(f"Painter {n}"), born=1800 + n, died=1880 + n)
                for n in range(5)
            ],
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


def away_and_back(ui) -> None:
    """Leave Ask for Walls and come back, as a curator would, keeping what the client holds.

    Walls is waited for by its own heading. Any `h1` would not do: Ask has one,
    so that wait was met before Walls drew anything, the return began with Ask's
    turn still on screen, and every wait after it could be met by the page that
    was never left (#402). Once Walls has drawn, Ask's turn is gone, and what
    the caller waits for next can only come from the returning page.
    """
    ui.navigate("#walls")
    ui.page.wait_for_selector("#view h1:text-is('Walls')")
    ui.navigate("#discover")


def test_a_reply_shows_what_it_looked_at_its_answer_its_cards_and_its_cost(ui, ask_model):
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")

    turn = ui.page.locator(".ask-turn").last
    expect(turn.locator(".ask-asked")).to_have_text("You: Something wintry", use_inner_text=True)
    step = turn.locator(".ask-step")
    expect(step.locator(".glyph")).to_have_text("●", use_inner_text=True)
    expect(step).to_have_text(re.compile(re.escape("Searching Wikidata for “bruegel”") + r"\s*$"), use_inner_text=True)
    answer = turn.locator(".ask-answer")
    expect(answer).to_contain_text("Bruegel's winter is the obvious place to start.", use_inner_text=True)
    expect(answer, "the cited items are cards, not identifiers in the words").not_to_contain_text("[Q", use_inner_text=True)
    expect(turn.locator(".ask-answer li")).to_have_count(2)
    cards = turn.locator(".ask-card")
    expect(cards).to_have_count(2)
    expect(cards.nth(0)).to_contain_text("The Hunters in the Snow", use_inner_text=True)
    expect(cards.nth(0).get_by_role("button", name="Get this work")).to_have_count(1)
    expect(cards.nth(1)).to_contain_text("Pieter Brueghel the Elder", use_inner_text=True)
    expect(cards.nth(1).get_by_role("button", name="more like this: Pieter Brueghel the Elder")).to_have_count(1)
    # The server's words (`summary`, `SpendTotal.words`): two calls at $0.0012, said as they are.
    expect(turn.locator(".ask-ending")).to_have_text("This reply cost $0.0024.", use_inner_text=True)


def test_a_work_card_gets_into_the_default_theme_with_nothing_beside_its_get(ui, services, ask_model):
    """No *Add to* and no tier on a poster (the owner, 2026-10-09): the Get sends
    no `theme_id`, and the sentence it leaves names where the work went. The
    default is not called *All works* here, so the name is read, not assumed."""
    services.display.make_default(services.display.add_theme(name="Everyday").id)
    bodies = []

    def answer(route):
        bodies.append(json.loads(route.request.post_data))
        run = a_run(run_id="get-from-ask", kind="get", intent=None, status=RunStatus.RESOLVING_IMAGES.value)
        body = {"run": run.model_dump(mode="json"), "skipped": []}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    ui.page.route("**/api/gets", answer)
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    card = ui.page.locator(".ask-card[data-ask-card='work']")
    card.get_by_role("button", name="Get this work").wait_for()

    expect(card.locator("select")).to_have_count(0)
    expect(card).not_to_contain_text("Add to", use_inner_text=True)
    expect(card.locator(".badge-tier")).to_have_count(0)
    expect(card).not_to_contain_text("Cost", use_inner_text=True)

    card.get_by_role("button", name="Get this work").click()
    card.locator(".get-status a:text-is('Open the Get')").wait_for()
    assert bodies == [{"qids": [HUNTERS]}], "the default is the absence of a theme_id"
    expect(card.locator(".get-status")).to_have_text("Getting 1 work into Everyday. Open the Get", use_inner_text=True)


def test_a_work_card_whose_themes_cannot_be_read_starts_nothing_and_says_why(ui, ask_model):
    """With no choice on the card, a Get must still not go to a default it could not find."""
    bodies = []
    ui.page.route("**/api/gets", lambda route: bodies.append(route.request.post_data))
    ui.serve("**/api/themes", (500, {"error": "The theme listing failed."}))
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    card = ui.page.locator(".ask-card[data-ask-card='work']")
    card.get_by_role("button", name="Get this work").click()

    ui.page.wait_for_selector("text=The theme listing failed.")
    assert bodies == []


def test_a_reply_with_a_step_that_reported_no_cost_says_so(ui, ask_model):
    """Not "This reply cost $0.0012." alone, which would read as cheaper than it was: "at least", in the Spend page's words."""
    ask_model.replies += [unpriced(calls(SEARCH)), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")

    expect(ui.page.locator(".ask-turn").last.locator(".ask-ending")).to_have_text(
        "This reply cost at least $0.0012, and 1 call whose cost is unknown.", use_inner_text=True
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

    def picture(kind):
        return ui.page.locator(f".ask-card[data-ask-card='{kind}'] .card-image img")

    expect(picture("work")).to_have_attribute("src", "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg?width=330")
    expect(picture("artist")).to_have_attribute("src", f"{HARVESTERS_FILE}?width=330")
    expect(picture("topic")).to_have_attribute("src", f"{MENINAS_FILE}?width=330")
    # Nothing is said of what the library does not hold.
    expect(ui.page.locator(".ask-cards")).not_to_contain_text("Not held", use_inner_text=True)
    expect(ui.page.locator(".ask-cards")).not_to_contain_text("In your library", use_inner_text=True)


def test_a_held_artist_is_pictured_as_library_artists_pictures_them(pictures_load, services, service, ready_work, ask_model):
    """By their own work's thumbnail, and marked as held, without asking Wikidata for their works.

    The work holds a master, since only a work that does pictures an artist
    (2026-10-14, #358): one that does not has no thumbnail to show.
    """
    ui = pictures_load
    rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    work = ready_work("Untitled", artist_id=rothko.id)
    services.identity.set_artist_identity(rothko.id, ROTHKO)
    ask_model.replies += [calls(("art_discovery", {"action": "search", "q": "rothko"})), says(f"Rothko [{ROTHKO}].")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Colour fields")
    ui.page.wait_for_selector(".ask-card[data-ask-card='artist'] .card-image img")

    card = ui.page.locator(".ask-card[data-ask-card='artist']")
    expect(card.locator(".card-image img")).to_have_attribute("src", f"/api/works/{work.id}/thumbnail")
    expect(card).to_contain_text("In your library", use_inner_text=True)


def test_a_held_work_is_pictured_by_its_thumbnail_marked_and_not_offered_for_get(pictures_load, services, service, ask_model):
    """A work the agent read from the library: its own thumbnail, *In your library*, and no Get."""
    ui = pictures_load
    work = service.add_artwork(title="The Hunters in the Snow")
    services.identity.set_work_identity(work.id, HUNTERS)
    ask_model.replies += [
        calls(("art_catalogue", {"action": "get", "artwork_id": work.id})),
        says(f"You hold it [{HUNTERS}]."),
    ]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "What do I have of Bruegel?")
    ui.page.wait_for_selector(".ask-card[data-ask-card='work'] .card-image img")

    card = ui.page.locator(".ask-card[data-ask-card='work']")
    expect(card.locator(".card-image img")).to_have_attribute("src", f"/api/works/{work.id}/thumbnail")
    expect(card).to_contain_text("In your library", use_inner_text=True)
    expect(card.get_by_role("button", name="Get this work")).to_have_count(0)


def test_a_picture_that_cannot_be_had_is_said_apart_from_one_that_does_not_exist(ui, ask_model):
    """An outage counted as "no picture" would read as a gap in how pictures are chosen."""
    ui.page.route(f"**/api/registry/artists/{BRUEGEL}", lambda route: route.abort())
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-card[data-ask-card='artist'] .card-image-absent")

    expect(ui.page.locator(".ask-card[data-ask-card='artist'] .card-image-absent")).to_have_text(
        "Picture unavailable", use_inner_text=True
    )


def test_the_cards_ask_wikidata_three_at_a_time(ui, ask_model):
    """Five artists named, five lookups owed: three go at once and the rest wait, so a
    reply naming fifteen never becomes fifteen registry queries together."""
    held = []

    def hold(route):
        held.append(route)

    ui.page.route("**/api/registry/artists/*", hold)
    names = " ".join(f"[Q10{n}]" for n in range(5))
    ask_model.replies += [calls(("art_discovery", {"action": "search", "q": "painters"})), says(f"Five painters: {names}")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Some painters")
    ui.page.wait_for_selector(".ask-card[data-ask-card='artist'] >> nth=4")
    ui.page.wait_for_timeout(500)  # sleep: proves a fourth lookup does not go while three are held
    assert len(held) == 3

    # The next lookup going is a request the page makes: wait for it, then
    # for a moment more, which proves it is one and not two.
    with ui.page.expect_request("**/api/registry/artists/*"):
        held.pop(0).abort()
    ui.page.wait_for_selector(".card-image-absent")
    ui.page.wait_for_timeout(
        300
    )  # sleep: proves a finished lookup lets one go, not two; `held` is the test's own list, which no page condition reads
    assert len(held) == 3, "a finished lookup did not let the next one go"
    for route in held:
        route.abort()


def test_a_card_with_nothing_to_picture_says_so(ui, ask_model):
    """Rothko is found by the search but Wikidata lists no work of his here."""
    ask_model.replies += [calls(("art_discovery", {"action": "search", "q": "rothko"})), says(f"Rothko [{ROTHKO}].")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Colour fields")
    ui.page.wait_for_selector(".ask-card[data-ask-card='artist'] .card-image-absent")

    expect(ui.page.locator(".ask-card .card-image-absent")).to_have_text("No picture", use_inner_text=True)
    expect(ui.page.locator(".ask-card .card-title")).to_have_text("Mark Rothko", use_inner_text=True)


def test_a_step_that_could_not_answer_is_marked_as_gone_wrong(ui, ask_model):
    ask_model.replies += [calls(("art_discovery", {"action": "start", "intent": "Bruegel"})), says("I cannot start a Get.")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Get me Bruegel")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")

    step = ui.page.locator(".ask-step")
    expect(step.locator(".glyph")).to_have_text("▲", use_inner_text=True)
    expect(step).to_have_text(
        re.compile(re.escape("Trying art_discovery start — it could not answer") + r"\s*$"), use_inner_text=True
    )
    expect(ui.page.locator(".ask-status")).to_have_text("This reply cost $0.0024.", use_inner_text=True)


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

        expect(ui.page.locator(".ask-turn"), "Enter sent while a reply was streaming").to_have_count(1)
        ask_model.release.set()
        ui.page.wait_for_selector(".ask-turn .ask-ending:has-text('cost')")
        expect(ui.page.locator("#view .act-failure, #view .error-text, #error:not([hidden])")).to_have_count(0)
        assert len(ask_model.seen) == 1

        # Nothing streaming now: Enter sends what is in the box.
        ui.page.press("#ask-words", "Enter")
        ui.page.wait_for_selector(".ask-turn:nth-child(2) .ask-ending:has-text('cost')")
        expect(ui.page.locator(".ask-asked")).to_have_text(["You: Something wintry", "You: Not Bruegel"], use_inner_text=True)

    def test_a_page_opened_mid_reply_waits_for_it_and_fills_in_when_it_ends(self, ui, ask_model):
        """Leaving Ask mid-reply and coming back: the server refuses a second send until the reply ends, so the page waits too."""
        ui.open("#discover")
        ui.page.wait_for_selector("#ask-words")
        ask(ui, "Something wintry")
        ui.page.wait_for_selector(".ask-turn")

        away_and_back(ui)
        ui.page.wait_for_selector(".ask-waiting")

        expect(ui.page.locator("#view button:text-is('Ask')")).to_be_disabled()
        ask_model.release.set()
        ui.page.wait_for_selector(".ask-turn .ask-ending:has-text('cost')", timeout=15_000)
        expect(ui.page.locator(".ask-waiting")).to_have_count(0)
        expect(ui.page.locator("#view button:text-is('Ask')")).to_be_enabled()


def test_an_empty_ask_offers_examples_that_fill_the_box_and_send_nothing(ui, ask_model):
    ask_model.replies += [says("The Delaunays' circle: Kupka, Léger.")]
    ui.open("#discover")
    ui.page.wait_for_selector(".ask-examples")

    # The shipped module's own list, so the test cannot drift from it.
    examples = ui.page.evaluate('async () => (await import("/static/core/asking.js")).EXAMPLES')
    assert len(examples) >= 2
    expect(ui.page.locator(".ask-examples button")).to_have_text(examples, use_inner_text=True)
    ui.page.locator(".ask-examples button").first.click()

    expect(ui.page.locator("#ask-words")).to_have_value(examples[0])
    assert ask_model.seen == [], "an example fills the box; it does not ask"
    expect(ui.page.locator(".ask-examples")).to_have_count(0)


def test_a_thread_with_something_said_offers_no_examples(ui, ask_model):
    ask_model.replies += [says("Bruegel, perhaps.")]
    ui.open("#discover")
    ui.page.wait_for_selector(".ask-examples")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('cost')")

    expect(ui.page.locator(".ask-examples")).to_have_count(0)
    away_and_back(ui)
    ui.page.wait_for_selector(".ask-turn")
    expect(ui.page.locator(".ask-examples")).to_have_count(0)


def test_a_returning_page_draws_the_thread_as_it_was(ui, ask_model):
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")
    live = _settled_turn(ui)

    away_and_back(ui)
    ui.page.wait_for_selector(".ask-turn")

    # Whole and as written, line breaks and all: a pattern, since a string is
    # compared with its whitespace folded.
    _settle(ui)
    expect(ui.page.locator(".ask-turn")).to_have_text(re.compile("^" + re.escape(live) + "$"), use_inner_text=True)


def test_the_thread_s_pictures_are_not_fetched_from_commons_under_test(ui, ask_model):
    """The suite's page reaches no origin but its own server (`ui`, #343).

    Through a real reply, whose cards ask Commons for their pictures: the
    requests are made and every one fails here, so no answer from outside
    reaches the page and each box says why it has no picture.
    """
    answered = []
    ui.page.on("response", lambda response: answered.append(response.url))
    ask_model.replies += [calls(SEARCH), says(ANSWER)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-ending:has-text('This reply cost')")
    _settle(ui)

    assert any("commons.wikimedia.org" in url for url in ui.requests), "no card asked Commons, so nothing here was guarded"
    assert [url for url in answered if not url.startswith(f"{ui.base_url}/")] == []
    expect(ui.page.locator(".ask-turn .card-image-absent")).to_have_text(
        ["Picture unavailable", "Picture unavailable"], use_inner_text=True
    )


def _settle(ui) -> None:
    """Wait until everything a card fills in after it is drawn has arrived.

    Two things do: a work card's theme picker reads the themes, and each
    picture box is filled when its picture answers — with the picture, or with
    words saying why there is none. Read before a box settled, the text lacks
    words it later gains, and a comparison of two reads races the picture (#343).
    """
    ui.page.wait_for_function("() => !document.querySelector('.ask-turn').innerText.includes('Reading themes')")
    ui.page.wait_for_function(
        "() => [...document.querySelectorAll('.ask-turn .card-image')].every((box) =>"
        " box.querySelector('.card-image-absent')"
        " || [...box.querySelectorAll('img')].some((img) => img.complete && img.naturalWidth > 0))"
    )


def _settled_turn(ui) -> str:
    """The turn's text once it has settled, for a test that compares it with the page's later one."""
    _settle(ui)
    return ui.page.locator(
        ".ask-turn"
    ).inner_text()  # one-shot: the value a later `expect` compares, read once `_settle` has waited


def test_a_second_turn_follows_the_first_and_start_over_clears_them(ui, ask_model):
    ask_model.replies += [says("Bruegel, perhaps."), says("Then Rothko.")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Something wintry")
    ui.page.wait_for_selector(".ask-turn:nth-child(1) .ask-ending:has-text('cost')")
    ask(ui, "Not Bruegel")
    ui.page.wait_for_selector(".ask-turn:nth-child(2) .ask-ending:has-text('cost')")

    expect(ui.page.locator(".ask-asked")).to_have_text(["You: Something wintry", "You: Not Bruegel"], use_inner_text=True)
    ui.page.click("#view button:text-is('Start over')")
    ui.page.wait_for_function("() => document.querySelectorAll('.ask-turn').length === 0")


def test_a_reply_that_reaches_the_step_limit_says_so_in_the_thread(ui, ask_model):
    ask_model.replies += [calls(SEARCH) for _ in range(DEFAULT_ASK_STEP_LIMIT + 1)]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")

    ask(ui, "Everything by everyone")
    ui.page.wait_for_selector(".ask-ending .error-text")

    expect(ui.page.locator(".ask-ending")).to_contain_text(
        f"Ask stopped after {DEFAULT_ASK_STEP_LIMIT} steps without finishing an answer", use_inner_text=True
    )
    expect(ui.page.locator(".ask-step")).to_have_count(DEFAULT_ASK_STEP_LIMIT)


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
    2026-10-09). *Tell me more*, cool and still open, is offered on the Artist
    page and Taste's rows, where `test_taste_and_reactions.py` holds it apart
    from *not this*."""
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
    expect(ui.page.locator(".ask-answer")).to_contain_text("Bruegel's winter is the obvious place to start.", use_inner_text=True)


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

    expect(ui.page.locator(".ask-turn").nth(1)).to_contain_text("Second.", use_inner_text=True)
    expect(ui.view).not_to_contain_text("That thread has gone.", use_inner_text=True)


def test_a_thread_the_server_forgot_is_an_empty_page_when_it_is_opened_and_the_next_words_start_a_new_one(ui, ask_model):
    """Coming back to Ask after a restart: the read of the old thread is a 404, and the page is empty, not broken.

    The client keeps the thread's id while the app is open. A server that restarted does not
    hold it, and answers the read of it with a 404 (`http/ask.py`); `core/asking.js` takes that
    as "nothing said yet", drops the id and draws the box. **The 404 stubbed is the server's own
    answer**, asked here of a thread id it does not hold, never a sentence written in this file
    (the one the send's test above stubs is, and differs from the server's).
    """
    ask_model.replies += [says("First."), says("Second.")]
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ask(ui, "One")
    ui.page.wait_for_selector(".ask-ending:has-text('cost')")
    gone = ui.page.request.get(f"{ui.base_url}/api/ask/threads/a-thread-this-server-never-held")
    assert gone.status == 404, "the server's answer for a thread it does not hold is the premise of this test"
    ui.page.route(
        re.compile(r"/api/ask/threads/[^/]+$"),
        lambda route: (
            route.fulfill(status=gone.status, content_type="application/json", body=json.dumps(gone.json()))
            if route.request.method == "GET"
            else route.fallback()
        ),
    )

    away_and_back(ui)
    ui.page.wait_for_selector("#ask-words")

    expect(ui.page.locator(".ask-turn")).to_have_count(0)
    expect(ui.page.locator("#error")).to_be_hidden()
    expect(ui.view).not_to_contain_text(gone.json()["error"], use_inner_text=True)
    ask(ui, "Two")
    ui.page.wait_for_selector(".ask-turn:has-text('Second.') .ask-ending:has-text('cost')")
    expect(ui.page.locator(".ask-turn")).to_have_count(1)


class TestWithNoKey:
    """Ask on a server with no key: disabled with its reason, never accepted and then refused."""

    @pytest.fixture
    def ask_model(self):
        return None

    def test_ask_is_disabled_with_one_sentence_and_nothing_is_asked_and_refused(self, ui):
        ui.open("#discover")
        ui.page.wait_for_selector("#ask-words")

        expect(ui.page.locator("#ask-words")).to_be_disabled()
        expect(ui.page.locator("#view button:text-is('Ask')")).to_be_disabled()
        sentence = ui.page.locator("#ask-unavailable")
        expect(sentence).to_have_count(1)
        expect(sentence).to_contain_text("Ask needs an OpenRouter key")
        expect(ui.page.locator(".panel.ask .ask-examples")).to_have_count(0)
        # One sentence, and the variable is the operator's to read on Sources and Status.
        expect(ui.page.locator(".panel.ask")).not_to_contain_text("OPENROUTER_API_KEY")
        assert ui.requests_matching("/api/ask/threads") == [], "a thread was opened for a page that cannot ask"

    def test_the_search_dropdown_does_not_offer_ask(self, ui):
        ui.open("#collection")
        ui.page.wait_for_selector("#search")
        ui.page.fill("#search", "Dali")

        expect(ui.page.locator("#search-suggestions #suggestion-all-results")).to_be_visible()
        expect(ui.page.locator("#search-suggestions #suggestion-ask")).to_have_count(0)
        expect(ui.page.locator("#search-suggestions")).not_to_contain_text("Ask about")


def test_a_refusal_for_no_key_after_the_page_was_drawn_is_said_once_as_a_refusal(ui, ask_model):
    """A server restarted without its key answers 503 to a page that drew Ask as ready.

    It is the refusal, once, in the page's own sentence, and not "the server
    failed while doing it", which is what a 5xx otherwise says.
    """
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    ui.page.route(
        "**/api/ask/threads/*/replies",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"error": "Ask needs an OpenRouter key to answer, and this server has none; nothing was spent."}),
        ),
    )

    ask(ui, "Winter landscapes")

    expect(ui.page.locator("#ask-words")).to_be_disabled()
    expect(ui.page.locator("#ask-unavailable")).to_have_count(1)
    expect(ui.page.locator(".panel.ask")).not_to_contain_text("the server failed")
    expect(ui.page.locator(".panel.ask")).not_to_contain_text("Couldn't ask")
    expect(ui.page.locator(".ask-turn")).to_have_count(0)
    expect(ui.page.locator("#ask-words")).to_have_value("Winter landscapes")
