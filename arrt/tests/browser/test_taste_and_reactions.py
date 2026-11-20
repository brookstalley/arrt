"""The Taste screen: every judgment with where it came from, correctable.

The reactions that fill it are drawn by `core/taste.js` wherever something can
be judged; on Ask's cards they are driven by `test_asking.py`. What is here is
the screen's own and visible only to a browser:

- **every judgment says where it came from**, with the model's rationale beside
  an inferred one;
- **a correction is written as the curator's own words**, never carrying the
  overruled judgment's account across;
- **Taste is a page under Settings.** The sidebar is derived from the route
  table, so registering the screen in the `settings` section is what puts it
  there rather than in a section of its own — and only a browser can see that.
"""

import json
import re

import pytest
from payloads import a_taste, an_affinity

from arrt.persistence.discovery_records import AffinityDerivation, AffinitySentiment

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

# -- the Taste screen ---------------------------------------------------------


def test_taste_is_a_page_under_settings(ui):
    """Rewritten from *Taste is not a fourth destination*: the amended navigation
    norm places it under Settings, where Radarr keeps the profiles that rank what
    it finds. The sidebar is derived from the route table, so this is what says
    the entry was registered in that section rather than as a section of its own.
    """
    ui.serve("**/api/affinities*", a_taste([an_affinity()]))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    settings = ui.page.locator("nav.sidebar li.section[data-section='settings']")
    expect(settings.locator("ul.pages a[aria-current='page']")).to_have_text("Taste", use_inner_text=True)
    # No section is labelled Taste: `:text-is` is the whole label, as a list's membership was.
    expect(ui.page.locator("nav.sidebar a.section-link .label:text-is('Taste')")).to_have_count(0)


def test_every_judgment_shows_where_it_came_from(ui):
    """The screen's whole reason to exist.

    A taste model that cannot say where a judgment came from is one the curator
    can only argue with, never fix — so the derivation is on the row rather than
    behind a hover, and the model's own rationale is beside it where there is
    one.
    """
    ui.serve(
        "**/api/affinities*",
        a_taste(
            [
                an_affinity("Agnes Martin"),
                an_affinity(
                    "Kandinsky",
                    derivation=AffinityDerivation.INFERRED.value,
                    rationale="they asked for stillness, and said the room is pale",
                ),
            ]
        ),
    )
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    expect(ui.view).to_contain_text("You said this", use_inner_text=True)
    expect(ui.view).to_contain_text("Read out of something you said", use_inner_text=True)
    expect(ui.view).to_contain_text("they asked for stillness, and said the room is pale", use_inner_text=True)


def test_an_inferred_judgment_renders_with_its_rationale_and_no_way_back(ui):
    """An inferred row came from a conversation the product no longer keeps.

    It has to render, since a screen that dropped it would hide a judgment still
    shaping what the curator is offered, and it must not offer a way through to
    a thread, because there is none.
    """
    ui.serve(
        "**/api/affinities*",
        a_taste(
            [
                an_affinity(
                    "Kandinsky",
                    derivation=AffinityDerivation.INFERRED.value,
                    rationale="they asked for stillness",
                )
            ]
        ),
    )
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    expect(ui.view).to_contain_text("Kandinsky", use_inner_text=True)
    expect(ui.view).to_contain_text("Read out of something you said", use_inner_text=True)
    expect(ui.view).to_contain_text("they asked for stillness", use_inner_text=True)
    expect(ui.page.locator(".affinity-provenance a")).to_have_count(0)


def test_correcting_a_judgment_writes_it_as_the_curators_own_words(ui):
    """The correction path, and the provenance it writes.

    A correction made here is the curator saying so, whatever the row said
    before. Writing it as anything weaker would let the product go on attributing
    to a model a judgment the person overruled by hand, and a later rebuild would
    act on that.
    """
    written = []
    reads = [
        # The row being corrected carries a rationale, deliberately: without
        # one, a correction that copied the old provenance across would send the
        # same nothing as a correct one and this test would pass against it.
        a_taste(
            [
                an_affinity(
                    "Kandinsky",
                    derivation=AffinityDerivation.INFERRED.value,
                    rationale="a guess",
                )
            ]
        ),
        a_taste([an_affinity("Kandinsky", sentiment=AffinitySentiment.DECLINES.value, open_to_more=False)]),
    ]
    ui.page.route("**/api/affinities**", lambda route: _taste_route(route, reads, written))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    ui.page.click("button:has-text('Not this')")
    # The repainted row, which says the opposite of what the first payload did —
    # so it is false before the click and true only after the correction lands.
    ui.page.wait_for_selector("text=Not to be offered again unless you say otherwise.")

    assert len(written) == 1
    assert written[0]["derivation"] == AffinityDerivation.STATED.value
    assert written[0]["sentiment"] == AffinitySentiment.DECLINES.value
    # And it does not carry the overruled judgment's account across. A row
    # explained by an account that did not produce it is indistinguishable
    # afterwards from real provenance.
    assert written[0].get("rationale") is None


def test_declining_and_keeping_open_are_different_pairs_of_the_two_fields(ui):
    """The two-fields rule, where the control that could collapse it lives.

    *Keep showing me* is `cool` and **still open**: the curator's "meh on
    Magritte, but open to learning more". A single warmth score would render it
    as a low number indistinguishable from *Not this*, and the honest lukewarm
    reaction would shut out an artist they asked to keep hearing about. Moved here
    from Ask's cards when they dropped *tell me more* (the owner, 2026-10-09).
    """
    written = []
    reads = [
        a_taste([an_affinity("Magritte")]),
        a_taste([an_affinity("Magritte", sentiment=AffinitySentiment.DECLINES.value, open_to_more=False)]),
        a_taste([an_affinity("Magritte", sentiment=AffinitySentiment.COOL.value, open_to_more=True)]),
    ]
    ui.page.route("**/api/affinities**", lambda route: _taste_route(route, reads, written))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    ui.page.get_by_role("button", name="Not this: Magritte").click()
    ui.page.wait_for_selector("text=Not to be offered again unless you say otherwise.")
    ui.page.get_by_role("button", name="Keep showing me: Magritte").click()
    ui.page.wait_for_selector("text=Still open to being shown more of this.")

    assert [(each["sentiment"], each["open_to_more"]) for each in written] == [("declines", False), ("cool", True)]


def test_forgetting_a_judgment_asks_first_and_says_what_is_lost(ui):
    """Not recoverable, so the dialog names the consequence rather than the row.

    And the distinction the screen exists to make: forgetting leaves the product
    knowing *nothing*, which is a different state from being told to leave a
    thing alone.
    """
    ui.page.route("**/api/affinities**", lambda route: _taste_route(route, [a_taste([an_affinity("Kandinsky")])], []))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    ui.page.click("button:has-text('Forget this')")
    ui.page.wait_for_selector("dialog.confirm")

    dialog = ui.page.locator("dialog.confirm")
    expect(dialog).to_contain_text("Forget Kandinsky?", use_inner_text=True)
    expect(dialog).to_contain_text("stop knowing anything about Kandinsky", use_inner_text=True)
    expect(dialog).to_contain_text("“Not this”", use_inner_text=True)
    expect(dialog, "a stated judgment is gone for good").not_to_contain_text("Arrt next starts", use_inner_text=True)


def test_forgetting_an_observed_judgment_says_review_will_read_it_again(ui):
    """Review re-derives an observed judgment, so forgetting one is not for good, and the dialog says so."""
    observed = an_affinity(
        "Klimt",
        derivation=AffinityDerivation.OBSERVED.value,
        sentiment=AffinitySentiment.DECLINES.value,
        open_to_more=False,
        rationale="Rejected 5 of the 5 works by Klimt decided in review.",
    )
    ui.page.route("**/api/affinities**", lambda route: _taste_route(route, [a_taste([observed])], []))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    ui.page.click("button:has-text('Forget this')")
    ui.page.wait_for_selector("dialog.confirm")

    said = ui.page.locator("dialog.confirm")
    expect(said).to_contain_text(
        "until you next accept or turn down one of their works in review, or Arrt next starts", use_inner_text=True
    )
    expect(said).not_to_contain_text("nothing brings the judgment back", use_inner_text=True)


def test_declining_the_forget_destroys_nothing(ui):
    """Asking is only a guard if the answer is read.

    A mutation sweep deleted the `if (!agreed) return;` and every assertion above
    still passed: they all describe the *question*, and none of them describes
    what happens when the curator says no. This is the one that does — and it is
    the harder direction to get right, because the dialog's own text is what a
    test naturally reaches for.
    """
    deleted = []
    ui.page.route("**/api/affinities**", lambda route: _taste_route(route, [a_taste([an_affinity("Kandinsky")])], [], deleted))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    ui.page.click("button:has-text('Forget this')")
    ui.page.wait_for_selector("dialog.confirm")
    ui.page.keyboard.press("Escape")
    # The dialog removes itself from the document once it settles, so its absence
    # is a state that is true only after the decline.
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert deleted == []
    expect(ui.view).to_contain_text("Kandinsky", use_inner_text=True)


def test_a_taste_nobody_has_expressed_says_what_would_create_one(ui):
    """The screen's empty state, which is not a "no results".

    There is nothing to clear and no filter to blame — there is a thing the
    curator has not done yet, so the state names it and offers the way to it.
    """
    ui.serve("**/api/affinities*", a_taste())
    ui.open("#taste")
    ui.page.wait_for_selector(".empty")

    expect(ui.view).to_contain_text("Nothing is known about your taste yet.", use_inner_text=True)
    expect(ui.page.locator("a:has-text('Ask for something')")).to_have_count(1)


def _capture(route, written):
    """Answer an affinity write, recording the body the client actually sent."""
    written.append(json.loads(route.request.post_data))
    body = an_affinity(json.loads(route.request.post_data)["value"]).model_dump(mode="json")
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def _taste_route(route, reads, written, deleted=None):
    """One handler for the affinities route, because reads and writes share the URL.

    Playwright matches a route by address and not by method, so a read stub and a
    write stub over the same path race: whichever was registered last answers
    both, and the test either sees no write or paints an affinity list from the
    response to a POST. Dispatching on the method here is what keeps a screen
    that reads back after writing testable at all — and the read list advances
    per GET, so "what the screen showed after the correction" is expressible.
    """
    if route.request.method == "POST":
        _capture(route, written)
        return
    if route.request.method == "DELETE":
        if deleted is not None:
            deleted.append(route.request.url)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(an_affinity().model_dump(mode="json")))
        return
    body = reads[min(len(written), len(reads) - 1)]
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def test_the_help_names_review_and_telling_ask_among_the_ways_a_judgment_is_recorded(ui):
    """The help lists every way a judgment gets here: review writes observed taste, and Ask records stated taste."""
    ui.serve("**/api/affinities*", a_taste([an_affinity()]))
    ui.open("#taste")
    ui.page.wait_for_selector(".taste-help li")

    # Each is the start of one of the help's lines, as the raw text of the line (`has_text` is the raw text).
    for start in ("or tell Ask", "accept, or turn down, at least five of an artist's works in review"):
        ways = ui.page.locator(".taste-help li").filter(has_text=re.compile("^" + re.escape(start)))
        expect(ways.first, f"no line of the help starts {start!r}").to_be_attached()
