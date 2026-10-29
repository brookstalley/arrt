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


HELD_ACTS = ["button.selection-add", "button.selection-archive"]
GET_ACTS = [".get-control button.action"]

#: Each list, the address that opens it, and the acts its bar must offer. A
#: list holding both kinds offers both halves' acts: one that wires only one
#: half fails here by name (#317).
LISTS = {
    "artworks": ("#collection", HELD_ACTS),
    "artist": (f"#artist/{BRUEGEL}", GET_ACTS),
    "search": ("#search?q=harvest", HELD_ACTS + GET_ACTS),
    "topic": (f"#topic/{SIXTEENTH}", HELD_ACTS + GET_ACTS),
}


@pytest.fixture
def a_search_held(service):
    """A held work the search for "harvest" finds, beside Wikidata's two it does not hold."""
    return service.add_artwork(title="Harvest at Dusk", date_created="1890")


@pytest.fixture
def a_list(request, seeded_service):
    """The list named by the test's parameter, with what it needs to have works on it."""
    if request.param == "topic":
        request.getfixturevalue("a_topic_held")
    if request.param == "search":
        request.getfixturevalue("a_search_held")
    if HELD_ACTS[0] in LISTS[request.param][1]:
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


def toolbar_position(ui) -> str:
    return ui.page.locator("#view .page-toolbar").first.evaluate("(bar) => getComputedStyle(bar).position")


@pytest.mark.parametrize("a_list", list(LISTS), indirect=True)
def test_the_acts_on_a_selection_take_the_toolbar_s_left_side(ui, a_list):
    """`design-direction.md` § Component Patterns, "How a page reads": a list's
    acts on what is selected take the toolbar's left side, beside *Select*. They
    sat in a bar at the window's foot until the rule (ruling 1 of 2026-10-27).

    The half with Select off is the one an over-eager toolbar fails: it holds
    *Select* and nothing else, and it scrolls away with the page."""
    address, acts = a_list
    open_list(ui, address)
    left = ui.page.locator("#view .page-toolbar-actions").first

    assert left.locator(":scope > :visible").count() == 1
    assert left.locator(":scope > :visible").first.inner_text() == "Select"
    assert toolbar_position(ui) == "static"

    ui.page.click("#view button.select-toggle")

    for act in acts:
        assert left.locator(f".selection {act}").is_visible(), f"{act} is not in the toolbar"
    # After the toggle, in that order: the acts follow the control that showed them.
    assert left.evaluate("(side) => [...side.children].map((child) => child.className)")[:2] == [
        "action quiet select-toggle",
        "selection",
    ]
    assert toolbar_position(ui) == "sticky"

    ui.page.click("#view button.select-toggle")

    assert toolbar_position(ui) == "static"


def test_the_acts_stay_in_reach_at_the_end_of_a_long_list(ui, studies):
    """Asserted from where the toolbar is drawn, not from its class: a sticky rule
    that a containing block defeats would leave the class and lose the acts."""
    ui.open("#collection?q=study")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")

    ui.page.locator("ul.grid li.card").last.scroll_into_view_if_needed()
    ui.page.mouse.wheel(0, 4000)
    ui.page.wait_for_function("() => window.scrollY > 600")

    box = ui.page.locator("#view .page-toolbar").first.bounding_box()
    assert box is not None
    assert 0 <= box["y"] < 5, f"the toolbar scrolled away: {box}"
    assert ui.page.locator("button.selection-add").is_visible()


@pytest.mark.parametrize(("width", "hidden_while_selecting"), [(390, True), (1280, False)])
def test_on_a_phone_view_and_sort_step_aside_while_selecting(ui, seeded_service, width, hidden_while_selecting):
    """A phone's sticky toolbar held a third of the screen over the works; View,
    Sort and the filters leave it while *Select* is on, since each repaints the
    list and drops the selection. A wide window has the room, and keeps them."""
    ui.page.set_viewport_size({"width": width, "height": 800})
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    controls = ui.page.locator("#view .page-toolbar-controls")

    assert controls.is_visible()
    ui.page.click("button.select-toggle")
    assert controls.is_hidden() is hidden_while_selecting
    ui.page.click("button.select-toggle")
    assert controls.is_visible()


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

    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", "new")
    ui.page.fill("#add-to-theme-name", "Night pieces")
    assert ui.page.inner_text("dialog button.add-confirm") == "Add 2 works to Night pieces"
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 2 works to Night pieces.')")

    assert ui.page.url.endswith("#collection")
    theme = next(t for t in services.display.list_themes() if t.name == "Night pieces")
    assert set(services.display.theme_work_ids(theme.id)) == {works[0].id, works[1].id}
    # The dialog closed on the add, and the keyboard is on the sentence saying so.
    assert ui.page.locator("dialog").count() == 0
    assert ui.page.evaluate("() => document.activeElement.classList.contains('selection-status')")
    # Made once and then chosen, so a second add joins it rather than making another.
    ui.page.check(f"li.card[data-artwork='{works[2].id}'] input.tile-select")
    ui.page.click("button.selection-add")
    assert ui.page.input_value("#add-to-theme") == theme.id
    assert ui.page.locator("#add-to-theme-name").is_hidden()


@pytest.mark.parametrize("leave", ["Escape", "Cancel"])
def test_leaving_the_add_dialog_adds_nothing_and_returns_to_add(ui, services, seeded_service, leave):
    """Asserted from the server: a dialog that closed but had added would pass a
    check of the page alone."""
    theme = services.display.add_theme(name="Somewhere")
    work = seeded_service.list_artworks().entries[0].artwork
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")
    ui.page.check(f"li.card[data-artwork='{work.id}'] input.tile-select")
    ui.page.click("button.selection-add")
    ui.page.wait_for_selector("dialog[open]")

    if leave == "Escape":
        ui.page.keyboard.press("Escape")
    else:
        ui.page.click("dialog button:text-is('Cancel')")

    ui.page.wait_for_selector("dialog", state="detached")
    assert services.display.theme_work_ids(theme.id) == []
    assert ui.page.evaluate("() => document.activeElement.classList.contains('selection-add')")
    assert ui.page.inner_text(".selection-status") == "1 selected."


def test_a_typed_name_that_is_already_a_theme_joins_it(ui, services, seeded_service):
    existing = services.display.add_theme(name="Night Pieces")
    work = seeded_service.list_artworks().entries[0].artwork
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")
    ui.page.check(f"li.card[data-artwork='{work.id}'] input.tile-select")

    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", "new")
    ui.page.fill("#add-to-theme-name", " night pieces ")
    ui.page.click("dialog button.add-confirm")
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
    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("dialog button.add-confirm")
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


# -- held works on Search and a Topic (#317) ------------------------------------

#: The two lists that once offered only the not-held half, the address of each,
#: and the fixture that puts a held work on it.
HELD_ON = {
    "search": ("#search?q=harvest", "a_search_held"),
    "topic": (f"#topic/{SIXTEENTH}", "a_topic_held"),
}


@pytest.fixture
def held_on(request, seeded_service):
    """The list named by the parameter, and the held work on it."""
    address, fixture = HELD_ON[request.param]
    request.getfixturevalue(fixture)
    titles = {"search": "Harvest at Dusk", "topic": "The Hunters in the Snow"}
    work = next(entry.artwork for entry in seeded_service.list_artworks().entries if entry.artwork.title == titles[request.param])
    return address, work


def tick_held(ui, address, work):
    open_list(ui, address)
    ui.page.click("#view button.select-toggle")
    ui.page.check(f"#view [data-artwork='{work.id}'] input[type='checkbox']")


@pytest.mark.parametrize("held_on", list(HELD_ON), indirect=True)
def test_a_held_work_is_added_to_a_theme_from_here(ui, services, held_on):
    address, work = held_on
    theme = services.display.add_theme(name="Somewhere")
    tick_held(ui, address, work)

    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Somewhere.')")

    assert services.display.theme_work_ids(theme.id) == [work.id]
    assert ui.page.url.endswith(address)


@pytest.mark.parametrize("held_on", list(HELD_ON), indirect=True)
def test_a_held_work_makes_a_new_theme_from_here(ui, services, held_on):
    address, work = held_on
    tick_held(ui, address, work)

    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", "new")
    ui.page.fill("#add-to-theme-name", "Harvests")
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Harvests.')")

    theme = next(t for t in services.display.list_themes() if t.name == "Harvests")
    assert services.display.theme_work_ids(theme.id) == [work.id]


@pytest.mark.parametrize("held_on", list(HELD_ON), indirect=True)
def test_a_held_work_is_archived_from_here(ui, seeded_service, held_on):
    address, work = held_on
    tick_held(ui, address, work)

    ui.page.click("button.selection-archive")
    ui.page.click("dialog.confirm button:has-text('Archive')")
    ui.page.wait_for_selector(".selection-status:has-text('Archived 1 work.')")

    assert seeded_service.get_artwork(work.id).artwork.status is ArtworkStatus.ARCHIVED
    # Out of circulation, so off the held list, without a repaint.
    assert ui.page.locator(f"#view [data-artwork='{work.id}']").count() == 0
    # Only the held work: the works Wikidata lists are still there to get.
    assert ui.page.locator("#view .get-control").count() == 1


def test_a_topic_whose_works_wikidata_cannot_list_still_selects_its_held_works(
    ui, services, registry, a_topic_held, seeded_service
):
    """The selection waits for Wikidata's works, so an outage must still make it.

    Wikidata goes down after the sweep has filed the work under the topic, so
    the page is the library's own and every question to Wikidata fails."""
    registry.failing = True
    theme = services.display.add_theme(name="Somewhere")
    work = next(
        entry.artwork for entry in seeded_service.list_artworks().entries if entry.artwork.title == "The Hunters in the Snow"
    )

    tick_held(ui, f"#topic/{SIXTEENTH}", work)
    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Somewhere.')")

    assert services.display.theme_work_ids(theme.id) == [work.id]
