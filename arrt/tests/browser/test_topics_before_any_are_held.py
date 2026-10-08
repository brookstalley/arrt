"""Library › Topics offers centuries and movements before any is held, and a Topic page fills as Wikidata answers.

S12 starts "Library › Topics → 16th century". Before this the index listed only
topics the library already held, so a curator who knew nothing of the period
had to think to type its name; and a fresh topic's works held "Asking
Wikidata…" until the last of Wikidata's answers. The registry is a fake
installed where the entry point builds Wikidata's; its makers' answer is held
back by an event, so the page is seen between the two answers.
"""

import threading

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry

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

    assert ui.page.locator(f"{PERIODS} h3").inner_text() == "Centuries"
    centuries = ui.page.locator(f"{PERIODS} ul.topic-offered li").all_inner_texts()
    assert centuries == [f"{n}{'st' if n == 21 else 'th'} century" for n in range(13, 22)]
    assert ui.page.locator(f"{MOVEMENTS} h3").inner_text() == "Major movements"
    assert "Impressionism" in ui.page.locator(f"{MOVEMENTS} ul.topic-offered li").all_inner_texts()
    # Said once for the whole library, not once per kind.
    assert "None of your works is in a topic yet." in ui.text()
    assert ui.page.locator(f"{PERIODS} p").count() == 0

    # Navigation, so a link.
    ui.page.get_by_role("link", name="16th century", exact=True).click()
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=SIXTEENTH)
    ui.page.wait_for_selector("#view h1:text-is('16th century')")


def test_a_held_century_is_listed_once_with_its_count(ui, service, services):
    service.add_artwork(title="The Hunters in the Snow", date_created="1565", wikidata_qid=HUNTERS)
    services.topic_sweep.run()

    ui.open("#topics")
    ui.page.wait_for_selector(f"{PERIODS} ul.topic-held li")

    assert [" ".join(row.split()) for row in ui.page.locator(f"{PERIODS} ul.topic-held li").all_inner_texts()] == [
        "16th century · 1 work"
    ]
    assert ui.page.locator(f"{PERIODS} h3").inner_text() == "Other centuries"
    assert "16th century" not in ui.page.locator(f"{PERIODS} ul.topic-offered li").all_inner_texts()
    assert ui.page.locator("#view a", has_text="16th century").count() == 1


def test_a_topic_page_shows_its_first_works_before_wikidata_has_said_who_made_them(ui, registry):
    registry.makers_gate = threading.Event()
    try:
        ui.open(f"#topic/{SIXTEENTH}")
        ui.page.wait_for_selector(f"{WORKS} tbody tr")

        titles = ui.page.locator(f"{WORKS} tbody td.work-title > a").all_inner_texts()
        assert titles == ["The Hunters in the Snow", "The Harvesters"]
        assert ui.page.locator(f"{WORKS} [aria-live]").inner_text() == "Still asking Wikidata who made them…"
        assert ui.page.locator(f"{WORKS} td.by-col").all_inner_texts() == ["Still asking…", "Still asking…"]
        # Nothing to tick yet, so nothing ticked is lost when the whole list arrives.
        assert ui.page.locator(f"{WORKS} input[type='checkbox']").count() == 0
        assert "Pieter Bruegel the Elder" not in ui.page.locator(WORKS).inner_text()
    finally:
        registry.makers_gate.set()

    ui.page.wait_for_selector(f"{WORKS} td.by-col a:text-is('Pieter Bruegel the Elder')")
    assert "Still asking" not in ui.page.locator(WORKS).inner_text()
    assert ui.page.locator(f"{WORKS} tbody tr").count() == 2
    assert ui.page.locator(f"{WORKS} input[type='checkbox']").count() == 2
