"""Library › Topics offers centuries and movements before any is held, and a Topic page fills as Wikidata answers.

S12 starts "Library › Topics → 16th century". Before this the index listed only
topics the library already held, so a curator who knew nothing of the period
had to think to type its name; and a fresh topic's works held "Asking
Wikidata…" until the last of Wikidata's answers. The registry is a fake
installed where the entry point builds Wikidata's; its makers' answer is held
back by an event, so the page is seen between the two answers.
"""

import re
import threading

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry
from playwright.sync_api import expect

from arrt.library.registry import (
    ItemId,
    RegistryCreator,
    RegistryText,
    RegistryTopic,
    RegistryTopicRef,
    RegistryTopicWork,
    TopicKind,
)

SIXTEENTH = "Q7017"
HUNTERS = "Q500985"
HARVESTERS = "Q1170284"
BRUEGEL = RegistryCreator(qid=ItemId("Q43270"), name=RegistryText("Pieter Bruegel the Elder"))

PERIODS = "section[aria-labelledby='topics-period']"
MOVEMENTS = "section[aria-labelledby='topics-movement']"
WORKS = "section[aria-labelledby='representative-works']"


@pytest.fixture
def registry():
    century = RegistryTopicRef(qid=ItemId(SIXTEENTH), label=RegistryText("16th century"), kind=TopicKind.PERIOD)
    return FakeRegistry(
        work_topics={HUNTERS: [century]},
        topics={
            SIXTEENTH: RegistryTopic(
                qid=ItemId(SIXTEENTH), label=RegistryText("16th century"), kinds=(TopicKind.PERIOD,), start=1501, end=1600
            )
        },
        topic_works={
            SIXTEENTH: [
                RegistryTopicWork(
                    qid=ItemId(HUNTERS),
                    title=RegistryText("The Hunters in the Snow"),
                    sitelinks=39,
                    year=1565,
                    creators=(BRUEGEL,),
                ),
                RegistryTopicWork(
                    qid=ItemId(HARVESTERS), title=RegistryText("The Harvesters"), sitelinks=25, year=1565, creators=(BRUEGEL,)
                ),
            ]
        },
    )


def test_an_empty_library_reaches_the_16th_century_without_typing(ui):
    ui.open("#topics")
    ui.page.wait_for_selector(f"{PERIODS} h3")

    expect(ui.page.locator(f"{PERIODS} h3")).to_have_text("Centuries", use_inner_text=True)
    expect(ui.page.locator(f"{PERIODS} ul.topic-offered li")).to_have_text(
        [f"{n}{'st' if n == 21 else 'th'} century" for n in range(13, 22)], use_inner_text=True
    )
    expect(ui.page.locator(f"{MOVEMENTS} h3")).to_have_text("Major movements", use_inner_text=True)
    # The names as a set: membership and their case, which no assertion on the
    # list asks. Read once the heading above them has painted.
    movements = ui.page.locator(f"{MOVEMENTS} ul.topic-offered li").all_inner_texts()  # one-shot: a set, read after its heading
    assert "Impressionism" in movements
    # Wikidata writes "realism" lower-case; a list of names is in one case.
    assert "Realism" in movements
    assert all(name[0].isupper() for name in movements)
    # Said once for the whole library, not once per kind.
    expect(ui.view).to_contain_text("None of your works is in a topic yet.", use_inner_text=True)
    expect(ui.page.locator(f"{PERIODS} p")).to_have_count(0)

    # Navigation, so a link.
    ui.page.get_by_role("link", name="16th century", exact=True).click()
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=SIXTEENTH)
    ui.page.wait_for_selector("#view h1:text-is('16th century')")


def test_a_held_century_is_listed_once_with_its_count(ui, service, services):
    service.add_artwork(title="The Hunters in the Snow", date_created="1565", wikidata_qid=HUNTERS)
    services.topic_sweep.run()

    ui.open("#topics")
    ui.page.wait_for_selector(f"{PERIODS} ul.topic-held li")

    # Whitespace-normalised, as the join over `split()` was.
    expect(ui.page.locator(f"{PERIODS} ul.topic-held li")).to_have_text(["16th century · 1 work"], use_inner_text=True)
    expect(ui.page.locator(f"{PERIODS} h3")).to_have_text("Other centuries", use_inner_text=True)
    # No offered item is the century itself: an item whose whole text is it.
    expect(ui.page.locator(f"{PERIODS} ul.topic-offered li", has_text=re.compile(r"^16th century$"))).to_have_count(0)
    expect(ui.page.locator("#view a", has_text="16th century")).to_have_count(1)


def test_a_topic_page_shows_its_first_works_before_wikidata_has_said_who_made_them(ui, registry):
    registry.makers_gate = threading.Event()
    try:
        ui.open(f"#topic/{SIXTEENTH}")
        ui.page.wait_for_selector(f"{WORKS} tbody tr")

        expect(ui.page.locator(f"{WORKS} tbody td.work-title > a")).to_have_text(
            ["The Hunters in the Snow", "The Harvesters"], use_inner_text=True
        )
        expect(ui.page.locator(f"{WORKS} [aria-live]")).to_have_text("Still asking Wikidata who made them…", use_inner_text=True)
        expect(ui.page.locator(f"{WORKS} td.by-col")).to_have_text(["Still asking…", "Still asking…"], use_inner_text=True)
        # Nothing to tick yet, so nothing ticked is lost when the whole list
        # arrives. Held so by the gate, which the makers' answer waits on.
        expect(ui.page.locator(f"{WORKS} input[type='checkbox']")).to_have_count(0)
        expect(ui.page.locator(WORKS)).not_to_contain_text("Pieter Bruegel the Elder", use_inner_text=True)
    finally:
        registry.makers_gate.set()

    ui.page.wait_for_selector(f"{WORKS} td.by-col a:text-is('Pieter Bruegel the Elder')")
    expect(ui.page.locator(WORKS)).not_to_contain_text("Still asking", use_inner_text=True)
    expect(ui.page.locator(f"{WORKS} tbody tr")).to_have_count(2)
    expect(ui.page.locator(f"{WORKS} input[type='checkbox']")).to_have_count(2)


def test_the_get_column_shows_only_while_there_are_ticks_to_show(ui, registry):
    """Outside Select mode, and while the works are still arriving, the list has
    no ticks; a "Get" heading over an empty column there says nothing."""
    registry.makers_gate = threading.Event()
    try:
        ui.open(f"#topic/{SIXTEENTH}")
        ui.page.wait_for_selector(f"{WORKS} tbody tr")
        expect(ui.page.locator(f"{WORKS} th", has_text="Get")).to_be_hidden()
    finally:
        registry.makers_gate.set()
    ui.page.wait_for_selector(f"{WORKS} td.by-col a:text-is('Pieter Bruegel the Elder')")
    expect(ui.page.locator(f"{WORKS} th", has_text="Get")).to_be_hidden()

    ui.page.click("button.select-toggle")
    expect(ui.page.locator(f"{WORKS} th", has_text="Get")).to_be_visible()
    ui.page.click("button.select-toggle")
    expect(ui.page.locator(f"{WORKS} th", has_text="Get")).to_be_hidden()
