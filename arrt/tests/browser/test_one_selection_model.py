"""One selection model on every list: Artworks, an Artist's page, the search results, a Topic.

`build-plan-lists-settings-and-scale.md` Chunk 05 (#285, `ux-review-2026-10.md`
finding 23): selection worked three ways and offered one action. Now every list
has a *Select* toggle whose label says which mode the page is in, ticks only in
that mode, and a bar at the foot of the window with *Select all* and every act
valid for what is ticked — Add to theme (with *New theme…*), Archive, Get.

**Select all means every work the filter matches, loaded or not.** The test
of that uses a filter larger than one server page, and reads what the client
sent: a list of the loaded ids would pass a count check on a small catalogue
and act on the wrong works at a large one.
"""

import json

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry

from arrt.library.registry import (
    CommonsFile,
    ItemId,
    RegistryArtist,
    RegistryCreator,
    RegistryText,
    RegistryTopic,
    RegistryTopicRef,
    RegistryTopicWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
    TopicKind,
)
from arrt.library.services.catalogue import DEFAULT_LIST_LIMIT
from arrt.persistence.records import ArtworkStatus

BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HARVESTERS = "Q1170284"
CORN = "Q1170285"
SIXTEENTH = "Q7017"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"
BY = RegistryCreator(qid=ItemId(BRUEGEL), name=RegistryText("Pieter Brueghel the Elder"))

#: More than one server page, and not a multiple of it.
PAST_ONE_PAGE = DEFAULT_LIST_LIMIT * 2 + 3


@pytest.fixture
def registry():
    century = RegistryTopicRef(qid=ItemId(SIXTEENTH), label=RegistryText("16th century"), kind=TopicKind.PERIOD)
    return FakeRegistry(
        artists={
            BRUEGEL: RegistryArtist(
                qid=BRUEGEL,
                name="Pieter Brueghel the Elder",
                works=(
                    RegistryWorkEntry(qid=HARVESTERS, title="The Harvesters", sitelinks=25),
                    RegistryWorkEntry(qid=CORN, title="The Corn Harvest", sitelinks=12, image=COMMONS),
                ),
                works_total=2,
            ),
        },
        matches={
            "harvest": [
                RegistryWorkMatch(qid=HARVESTERS, title="The Harvesters", sitelinks=25, creator=BY),
                RegistryWorkMatch(qid=CORN, title="The Corn Harvest", sitelinks=12, image=COMMONS, creator=BY),
            ]
        },
        work_topics={HUNTERS: [century]},
        topics={
            SIXTEENTH: RegistryTopic(
                qid=ItemId(SIXTEENTH), label=RegistryText("16th century"), kinds=(TopicKind.PERIOD,), start=1501, end=1600
            )
        },
        topic_works={
            SIXTEENTH: [
                RegistryTopicWork(
                    qid=ItemId(HARVESTERS), title=RegistryText("The Harvesters"), sitelinks=25, year=1565, creators=(BY,)
                ),
                RegistryTopicWork(
                    qid=ItemId(CORN),
                    title=RegistryText("The Corn Harvest"),
                    sitelinks=12,
                    year=1565,
                    image=CommonsFile(COMMONS),
                    creators=(BY,),
                ),
            ]
        },
    )


@pytest.fixture
def a_topic_held(services, service):
    """One held work in the 16th century, so the topic has a page."""
    service.add_artwork(title="The Hunters in the Snow", date_created="1565", wikidata_qid=HUNTERS)
    services.topic_sweep.run()


#: Each list, the address that opens it, and the acts its bar must offer.
LISTS = {
    "artworks": ("#collection", ["button.selection-add", "button.selection-archive"]),
    "artist": (f"#artist/{BRUEGEL}", [".get-control button.action"]),
    "search": ("#search?q=harvest", [".get-control button.action"]),
    "topic": (f"#topic/{SIXTEENTH}", [".get-control button.action"]),
}


@pytest.fixture
def a_list(request, seeded_service):
    """The list named by the test's parameter, with what it needs to have works on it."""
    if request.param == "topic":
        request.getfixturevalue("a_topic_held")
    if request.param == "artworks":
        # A theme to add to, so Add is live once works are ticked; with none,
        # it waits for *New theme…*'s name (`test_a_theme_is_made_…`).
        request.getfixturevalue("services").display.add_theme(name="Somewhere")
    return LISTS[request.param]


def open_list(ui, address):
    ui.open(address)
    # The toggle is offered once there is something to tick, which on a
    # registry list is when Wikidata's answer has been drawn.
    ui.page.wait_for_selector("#view button.select-toggle:visible")


def ticks(ui):
    return ui.page.locator("#view input[type='checkbox']")


@pytest.mark.parametrize("a_list", list(LISTS), indirect=True)
def test_every_list_offers_the_same_select_controls(ui, a_list):
    address, acts = a_list
    open_list(ui, address)

    toggle = ui.page.locator("#view button.select-toggle")
    assert toggle.inner_text() == "Select"
    # Ticks exist and none shows: a list with no ticks at all would pass the second half alone.
    assert ticks(ui).count() > 0
    assert ticks(ui).locator("visible=true").count() == 0
    assert ui.page.locator("#view .selection").is_hidden()

    toggle.click()

    assert toggle.inner_text() == "Stop selecting"
    bar = ui.page.locator("#view .selection")
    assert bar.is_visible()
    assert bar.locator(".selection-status").inner_text() == "No works selected."
    for act in acts:
        assert bar.locator(act).is_visible(), f"the bar does not offer {act}"
        assert bar.locator(act).is_disabled(), f"{act} is live with nothing ticked"
    shown = ticks(ui).locator("visible=true").count()
    assert shown > 0

    bar.locator("button.select-all").click()

    assert bar.locator(".selection-status").inner_text() == f"{shown} selected."
    assert ticks(ui).locator("visible=true").evaluate_all("boxes => boxes.every((box) => box.checked)")
    assert bar.locator("button.select-all").inner_text() == "Select none"
    for act in acts:
        assert bar.locator(act).is_enabled()

    toggle.click()

    assert toggle.inner_text() == "Select"
    assert ticks(ui).evaluate_all("boxes => boxes.every((box) => !box.checked)"), "leaving the mode kept the ticks"


def tab_stops(ui, presses=120) -> list[str]:
    """What the keyboard lands on, Tab by Tab from the top of the page."""
    ui.page.evaluate("() => document.activeElement && document.activeElement.blur()")
    landed = []
    for _ in range(presses):
        ui.page.keyboard.press("Tab")
        landed.append(
            ui.page.evaluate(
                "() => { const e = document.activeElement; return e ? `${e.tagName.toLowerCase()}:${e.type || ''}` : ''; }"
            )
        )
    return landed


@pytest.mark.parametrize("a_list", list(LISTS), indirect=True)
def test_no_tick_is_a_tab_stop_outside_select_mode(ui, a_list):
    """Finding 30: a tick on every card was one more Tab stop per card.

    Walked with the keyboard rather than read off the markup, since what
    matters is where Tab lands; and walked again in *Select* mode, where the
    ticks must be reachable, so a walk that never reaches the cards cannot pass.
    """
    address, _ = a_list
    open_list(ui, address)

    assert "input:checkbox" not in tab_stops(ui)

    ui.page.click("#view button.select-toggle")

    assert "input:checkbox" in tab_stops(ui)


def test_a_theme_is_made_from_a_selection_without_leaving_artworks(ui, services, seeded_service):
    """S7: select works, make a theme of them, and stay where you are."""
    works = [entry.artwork for entry in seeded_service.list_artworks().entries]
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")
    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")

    ui.page.select_option("#add-to-theme", "new")
    ui.page.fill("#add-to-theme-name", "Night pieces")
    assert ui.page.inner_text("button.selection-add") == "Add 2 works to Night pieces"
    ui.page.click("button.selection-add")
    ui.page.wait_for_selector(".selection-status:has-text('Added 2 works to Night pieces.')")

    assert ui.page.url.endswith("#collection")
    theme = next(t for t in services.display.list_themes() if t.name == "Night pieces")
    assert set(services.display.theme_work_ids(theme.id)) == {works[0].id, works[1].id}
    # Made once and then chosen, so a second press joins it rather than making another.
    assert ui.page.input_value("#add-to-theme") == theme.id
    assert ui.page.locator("#add-to-theme-name").is_hidden()


def test_a_typed_name_that_is_already_a_theme_joins_it(ui, services, seeded_service):
    existing = services.display.add_theme(name="Night Pieces")
    work = seeded_service.list_artworks().entries[0].artwork
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")
    ui.page.check(f"li.card[data-artwork='{work.id}'] input.tile-select")

    ui.page.select_option("#add-to-theme", "new")
    ui.page.fill("#add-to-theme-name", " night pieces ")
    ui.page.click("button.selection-add")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Night Pieces.')")

    assert [t.name for t in services.display.list_themes()] == ["Night Pieces"]
    assert services.display.theme_work_ids(existing.id) == [work.id]


@pytest.fixture
def studies(seeded_service):
    """More works than one page, all matching "study", beside three seeded ones that do not."""
    return [seeded_service.add_artwork(title=f"Study number {number:03d}").id for number in range(PAST_ONE_PAGE)]


def bodies_sent(ui, pattern) -> list[dict]:
    sent: list[dict] = []
    ui.page.on("request", lambda request: sent.append(json.loads(request.post_data)) if pattern in request.url else None)
    return sent


def test_select_all_on_a_filter_larger_than_one_page_adds_every_match(ui, services, studies):
    theme = services.display.add_theme(name="Studies")
    sent = bodies_sent(ui, "/works/bulk")
    ui.open("#collection?q=study")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")

    ui.page.click(".selection button.select-all")
    assert ui.page.inner_text(".selection-status") == f"{PAST_ONE_PAGE} selected."
    # One unticked after Select all is left out, by id, beside the filter.
    unticked = studies[0]
    ui.page.uncheck(f"[data-artwork='{unticked}'] input.tile-select")
    assert ui.page.inner_text(".selection-status") == f"{PAST_ONE_PAGE - 1} selected."
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("button.selection-add")
    ui.page.wait_for_selector(f".selection-status:has-text('Added {PAST_ONE_PAGE - 1} works to Studies.')")

    assert sent == [{"filter": {"q": "study"}, "except_ids": [unticked]}], "Select all sent ids, not the filter"
    assert set(services.display.theme_work_ids(theme.id)) == set(studies) - {unticked}


def test_select_all_then_archive_archives_every_match(ui, seeded_service, studies):
    ui.open("#collection?q=study")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")
    ui.page.click(".selection button.select-all")

    ui.page.click("button.selection-archive")
    ui.page.click("dialog.confirm button:has-text('Archive')")
    ui.page.wait_for_selector(f".selection-status:has-text('Archived {PAST_ONE_PAGE} works.')")

    statuses = {seeded_service.get_artwork(artwork_id).artwork.status for artwork_id in studies}
    assert statuses == {ArtworkStatus.ARCHIVED}
    # The search left the seeded works out, and so did the archive.
    assert seeded_service.list_artworks(q="nighthawks").entries[0].artwork.status is ArtworkStatus.ACCEPTED
    # The tiles say so where they stand, without a repaint.
    assert ui.page.locator("ul.grid li.card .badge-archived").count() == ui.page.locator("ul.grid li.card").count()


def test_archiving_asks_first_and_a_no_changes_nothing(ui, seeded_service):
    work = seeded_service.list_artworks().entries[0].artwork
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")
    ui.page.check(f"li.card[data-artwork='{work.id}'] input.tile-select")

    ui.page.click("button.selection-archive")
    ui.page.wait_for_selector("dialog.confirm:has-text('Archive 1 work?')")
    ui.page.click("dialog.confirm button:has-text('Cancel')")

    assert seeded_service.get_artwork(work.id).artwork.status is ArtworkStatus.ACCEPTED
    assert ui.page.locator(f"li.card[data-artwork='{work.id}'] input.tile-select").is_checked()
