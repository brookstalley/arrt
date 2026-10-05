"""The navigation, in a real browser: the *arr sidebar, and what hangs off it.

`information-architecture.md` § Direction is the norm this file is the executed
half of. It was amended by the owner on 2026-09-30 — *"More important to be
familiar than to have our own thing"* — from three flat destinations to the
sidebar Sonarr and Radarr use, and § The *arr layout is the target this file
holds the code to. Placement and naming stay the Critic's to judge; what a test
can hold is asserted here: which sections there are and in what order, which
pages sit under each and when they show, the home page, that a contextual screen
returns where it was opened from, and that the status indicator still speaks.

**What became of the three-destinations tests, since a norm change is the one
legitimate reason to rewrite a test's assertion.** The count-and-labels test is
rewritten against the sections, keeping its point: addition is the failure, so
the whole list is asserted, not membership. *No entry names a pipeline stage*
and *the navigation is flat* are retired — the amended norm deliberately
accepts Activity and System, and deliberately nests pages under sections. *The
product opens on the Walls* becomes *opens on Artworks*, and *Health is not in
the navigation* becomes *Status is under System*, because the ruling changed
those facts. Everything about the indicator, search, back and old addresses is
carried over, with the labels the ruling renamed.
"""

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

#: The sidebar's sections, in order: § The *arr layout's table. Artworks first
#: because every *arr app puts its library first; Walls second, in Calendar's
#: slot; then Activity, Settings and System in Sonarr's order.
SECTIONS = ["Artworks", "Walls", "Activity", "Settings", "System"]

#: The pages each section lists beneath its own name, when it is the current one.
#: A page named like its section *is* the section's link and is not repeated.
PAGES = {
    "Artworks": ["Ask", "Themes", "Topics", "Artists"],
    "Walls": [],
    "Activity": ["To review", "Queue", "History"],
    "Settings": ["Taste", "Clients"],
    "System": ["Status"],
}

#: Every sidebar page: its route, and a heading that proves it painted.
SIDEBAR_PAGES = [
    ("collection", "works"),
    ("discover", "Ask"),
    ("theme", "Themes"),
    ("topics", "Topics"),
    ("artist", "Artists"),
    ("walls", "Walls"),
    ("to_review", "To review"),
    ("queue", "Queue"),
    ("history", "History"),
    ("taste", "What this product thinks you like"),
    ("clients", "Clients"),
    ("health", "Status"),
]

SECTION_LINKS = "nav.sidebar a.section-link"


def lit(ui, view: str):
    """The sidebar link for `view`, if it is the one marked as the current page."""
    return ui.page.locator(f"nav.sidebar a[data-view='{view}'][aria-current='page']")


def visible_pages(ui) -> dict[str, list[str]]:
    """What the sidebar shows beneath each section, read from the page."""
    return ui.page.evaluate("""() => Object.fromEntries(
        [...document.querySelectorAll('nav.sidebar li.section')].map((section) => [
          section.querySelector('a.section-link .label').textContent,
          [...section.querySelectorAll('ul.pages a')]
            .filter((a) => a.checkVisibility())
            .map((a) => (a.querySelector('.label') || a).textContent),
        ]))""")


# -- the sidebar ---------------------------------------------------------------


def test_the_sidebar_is_the_arr_sections_and_nothing_else(ui, seeded_service):
    """Rewritten from *the three destinations and nothing else*, to the amended norm.

    The whole list is asserted, not membership, for the reason the old test gave:
    the failure the norm exists to catch is *addition* — a subsystem that gains a
    UI wanting a section of its own. A test checking only that these four were
    present would pass against a sidebar that had grown a fifth.
    """
    ui.open()
    ui.page.wait_for_selector(SECTION_LINKS)

    assert ui.page.locator(f"{SECTION_LINKS} .label").all_inner_texts() == SECTIONS


#: The page each section's own link opens: its first page in the route table.
OPENS = {"Artworks": "collection", "Walls": "walls", "Activity": "to_review", "Settings": "taste", "System": "health"}


@pytest.mark.parametrize("section", SECTIONS)
def test_each_section_lists_exactly_its_pages(ui, seeded_service, section):
    """Every section, so a page added to or dropped from any one of them fails by name."""
    ui.open(f"#{OPENS[section]}")
    # The links exist before the router opens the current section, so waiting
    # on them alone reads the pages too early under load. `lightSidebar` opens
    # the section and marks `aria-current` in one step: wait for the mark.
    ui.page.wait_for_selector("nav.sidebar li.section[data-open] [aria-current='page']")

    assert visible_pages(ui)[section] == PAGES[section]


def test_pages_show_only_under_the_current_section(ui, seeded_service):
    """As in Sonarr: the current section opens, the others show just their names.

    Checked from two sections, and the second is the half that matters — a
    sidebar that showed every page everywhere would pass a check made only from
    the section whose pages it happens to list.
    """
    ui.open("#collection")
    ui.page.wait_for_selector(SECTION_LINKS)
    assert visible_pages(ui) == {**{name: [] for name in SECTIONS}, "Artworks": PAGES["Artworks"]}

    ui.open("#health")
    ui.page.wait_for_selector("#view h2:has-text('Status')")
    assert visible_pages(ui) == {**{name: [] for name in SECTIONS}, "System": PAGES["System"]}


@pytest.mark.parametrize(("view", "heading"), SIDEBAR_PAGES)
def test_each_page_is_reachable_by_clicking_and_says_where_it_landed(ui, seeded_service, view, heading):
    """Clicked through its section, the way a curator gets to it.

    The section's own link first, so the page's link is showing; then the page.
    """
    ui.open("#walls")
    ui.page.wait_for_selector(SECTION_LINKS)

    section = ui.page.locator("nav.sidebar li.section", has=ui.page.locator(f"a[data-view='{view}']"))
    section.locator("a.section-link").click()
    ui.page.locator(f"nav.sidebar a[data-view='{view}']").last.click()
    ui.page.wait_for_selector(f"#view h2:has-text('{heading}')")

    assert lit(ui, view).count() == 1


@pytest.mark.parametrize(("view", "heading"), SIDEBAR_PAGES)
def test_each_page_is_addressable(ui, seeded_service, view, heading):
    """Reachable by clicking is not the requirement; every page has a URL."""
    ui.open(f"#{view}")
    ui.page.wait_for_selector(f"#view h2:has-text('{heading}')")

    assert lit(ui, view).count() == 1


def test_only_one_link_is_the_current_page(ui, seeded_service):
    """Settings' link and Taste's point at the same address, and only one may say so.

    `aria-current="page"` on two links tells a screen reader it is on two pages.
    The page's own link carries it; the section link is only styled as open.
    """
    ui.open("#taste")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.locator("nav.sidebar [aria-current='page']").count() == 1
    assert lit(ui, "taste").inner_text() == "Taste"


def test_the_sidebar_links_are_real_addresses(ui, seeded_service):
    """Links rather than buttons, so a page opens in a new tab like any *arr link."""
    ui.open()
    ui.page.wait_for_selector(SECTION_LINKS)

    for view, _heading in SIDEBAR_PAGES:
        assert ui.page.locator(f"nav.sidebar a[data-view='{view}']").first.get_attribute("href") == f"#{view}"


def test_the_product_opens_on_artworks(ui, seeded_service):
    """Rewritten from *opens on the Walls*: the owner ruled the home is the library,
    as it is in every *arr app."""
    ui.open()
    ui.page.wait_for_selector("#view h2:has-text('works')")

    assert lit(ui, "collection").count() == 1


def test_an_address_naming_nothing_lands_on_artworks(ui, seeded_service):
    ui.open("#nonsense")
    ui.page.wait_for_selector("#view h2:has-text('works')")

    assert lit(ui, "collection").count() == 1


def test_the_skip_link_skips_rather_than_navigating(ui, seeded_service):
    """The fragment router reads every `#…` as an address, including `#view`.

    A skip link written as a plain `href="#view"` is therefore a link to a page
    called "view", which does not exist, so it sends the keyboard user to the
    home page instead of past the sidebar. It must move focus and leave the
    address alone.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2:has-text('Walls')")

    ui.page.keyboard.press("Tab")
    assert ui.page.evaluate("() => document.activeElement.className") == "skip-link"
    ui.page.keyboard.press("Enter")

    assert ui.page.evaluate("() => document.activeElement.id") == "view"
    assert ui.page.evaluate("() => window.location.hash") == "#walls"
    assert "Walls" in ui.page.inner_text("#view h2")


# -- the drawer, on a phone -----------------------------------------------------


@pytest.fixture
def phone(ui):
    ui.page.set_viewport_size({"width": 375, "height": 740})
    return ui


def test_on_a_phone_the_sidebar_is_behind_the_menu_button(phone, seeded_service):
    phone.open("#collection")
    phone.page.wait_for_selector("#view h2")

    assert not phone.page.locator("nav.sidebar").is_visible()
    menu = phone.page.locator("button.menu-button")
    assert menu.is_visible()
    assert menu.get_attribute("aria-expanded") == "false"

    menu.click()
    assert phone.page.locator("nav.sidebar").is_visible()
    assert menu.get_attribute("aria-expanded") == "true"


def test_the_drawer_closes_on_escape_and_hands_focus_back(phone, seeded_service):
    """A drawer that swallows focus when it closes strands a keyboard user in nothing."""
    phone.open("#collection")
    phone.page.wait_for_selector("#view h2")

    phone.page.focus("button.menu-button")
    phone.page.keyboard.press("Enter")
    assert phone.page.locator("nav.sidebar").is_visible()
    assert phone.page.evaluate("() => document.activeElement.closest('nav.sidebar') !== null")

    phone.page.keyboard.press("Escape")
    assert not phone.page.locator("nav.sidebar").is_visible()
    assert phone.page.evaluate("() => document.activeElement.classList.contains('menu-button')")


def test_tapping_beside_the_drawer_closes_it(phone, seeded_service):
    """A phone has no Escape key, and the open drawer covers the menu button."""
    phone.open("#collection")
    phone.page.wait_for_selector("#view h2")

    phone.page.click("button.menu-button")
    assert phone.page.locator("nav.sidebar").is_visible()
    # To the right of the drawer, which is at most 85% of the width.
    phone.page.mouse.click(365, 400)

    assert not phone.page.locator("nav.sidebar").is_visible()
    assert phone.page.locator("button.menu-button").get_attribute("aria-expanded") == "false"


def test_picking_a_page_from_the_drawer_closes_it(phone, seeded_service):
    phone.open("#collection")
    phone.page.wait_for_selector("#view h2")

    phone.page.click("button.menu-button")
    phone.page.click("nav.sidebar a[data-view='walls']")
    phone.page.wait_for_selector("#view h2:has-text('Walls')")

    assert not phone.page.locator("nav.sidebar").is_visible()


def test_on_a_wide_window_there_is_no_menu_button(ui, seeded_service):
    """The paired negative: the drawer is a phone's answer, not a desktop's."""
    ui.page.set_viewport_size({"width": 1280, "height": 800})
    ui.open("#collection")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.locator("nav.sidebar").is_visible()
    assert not ui.page.locator("button.menu-button").is_visible()


# -- System › Status -------------------------------------------------------------


def test_status_is_under_system(ui, seeded_service):
    """Rewritten from *Health is not in the navigation*: the amended norm puts it
    where every *arr app keeps its health checks."""
    ui.open("#health")
    ui.page.wait_for_selector("#view h2:has-text('Status')")

    system = ui.page.locator("nav.sidebar li.section", has=ui.page.locator("a.section-link[data-view='health']"))
    assert system.locator("a.section-link .label").inner_text() == "System"
    assert lit(ui, "health").inner_text() == "Status"


def test_status_is_reached_by_the_top_bar_indicator(ui, seeded_service, a_health_reading):
    """The indicator still opens the page it summarises, from anywhere."""
    ui.serve("**/api/health", a_health_reading())
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    ui.page.click("#status")
    ui.page.wait_for_selector("#view h2:has-text('Status')")

    assert "This deployment's geometry" in ui.text()


def test_status_keeps_the_address_health_had(ui, seeded_service, a_health_reading):
    """A failure links to it and a curator bookmarks it, so the address outlives the rename."""
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    ui.page.wait_for_selector("#view h2:has-text('Status')")

    assert "The living room" in ui.text()
    assert "The catalogue was last backed up" in ui.text()


def test_health_names_each_wall_rather_than_one_display_plane(ui, a_health_reading, a_wall_reading):
    """One reading for an installation with two rooms cannot name the room.

    That is the whole reason the heartbeat became one per wall, and the screen has
    to carry the distinction through: two panels, each headed by the wall it is
    about, with the silent one identifiable.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(
            walls=[
                a_wall_reading(wall_id="wall-1", name="The living room"),
                a_wall_reading(wall_id="wall-2", name="The study", absent=True),
            ]
        ),
    )
    ui.open("#health")
    ui.page.wait_for_selector("#view h2:has-text('Status')")

    headings = ui.page.locator("#view .panel h3").all_inner_texts()
    assert "The living room" in headings
    assert "The study" in headings
    # "for this wall", not "here". Both wave-1 chunks reworded this sentence and
    # pinned their own wording; the per-wall one survives the merge, because with
    # a panel per room "here" has several possible referents and names none of
    # them — the ambiguity that splitting the heartbeat per wall removed.
    assert "Nothing has ever written a heartbeat for this wall" in ui.text()


def test_a_health_reading_the_screen_cannot_parse_is_stated_rather_than_thrown(ui):
    """The product's only alerting surface must not answer a bad payload with a stack trace.

    An exception here reaches the page's error banner reading like the server is
    down, which is a different fact leading to a different next move. Saying what
    the reading was missing is the honest answer, and it keeps the rest of the
    screen — the backup and the geometry — readable.
    """
    ui.serve(
        "**/api/health",
        {
            "backup": {
                "path": "/art/backup-receipt.json",
                "completed_at": "2026-08-12T03:00:00+00:00",
                "age_seconds": 22440.0,
                "absent": False,
                "problem": None,
                "description": "The catalogue was last backed up 6 hours ago.",
                "reported": None,
            },
            "artwork_box": {"width": 3840, "height": 2160, "pixels_per_inch": 72.0, "floor_inches": 20.0},
        },
    )
    ui.open("#health")
    ui.page.wait_for_selector("#view h2:has-text('Status')")

    assert "carries no walls" in ui.text()
    assert "The catalogue was last backed up" in ui.text()
    assert ui.page.locator("#error:not([hidden])").count() == 0


# -- the status indicator ------------------------------------------------------


def test_the_indicator_is_on_every_page(ui, seeded_service):
    """Always present is the whole contract. An indicator you have to reach is a tab."""
    for view, _heading in SIDEBAR_PAGES:
        ui.open(f"#{view}")
        ui.page.wait_for_selector("#view h2")
        assert ui.page.locator("#status").is_visible(), view


def test_the_indicator_is_on_a_phone_too(ui, seeded_service):
    """The drawer hides the sidebar, and with it the System badge, so the top bar's
    indicator is the only status a phone shows without a tap."""
    ui.page.set_viewport_size({"width": 375, "height": 740})
    ui.open("#collection")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.locator("#status").is_visible()


# -- the System badge ------------------------------------------------------------


def system_link(ui):
    return ui.page.locator("nav.sidebar a.section-link[data-view='health']")


def test_the_system_badge_counts_the_problems(ui, a_health_reading, a_wall_reading, a_backup_reading):
    """Sonarr's badge: a number on System. Two problems here, from two subjects,
    so a badge counting walls alone (or a badge that only knows "some") fails."""
    ui.serve(
        "**/api/health",
        a_health_reading(
            walls=[
                a_wall_reading(wall_id="wall-1", name="The living room"),
                a_wall_reading(wall_id="wall-2", name="The study", absent=True),
            ],
            backup=a_backup_reading(absent=True),
        ),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert system_link(ui).locator(".status-count").inner_text() == "2"
    # A number alone is no word, so the link's name carries one.
    assert system_link(ui).get_attribute("aria-label") == "System: 2 problems"


def test_one_problem_is_not_called_problems(ui, a_health_reading, a_wall_reading):
    ui.serve("**/api/health", a_health_reading(walls=[a_wall_reading(name="The study", absent=True)]))
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert system_link(ui).get_attribute("aria-label") == "System: 1 problem"


def test_a_well_system_shows_no_badge_and_says_so(ui, a_health_reading):
    """The paired negative. Sonarr shows nothing when all is well, and the link's
    name says "all well" so the silence is a statement rather than a gap."""
    ui.serve("**/api/health", a_health_reading())
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='well']")

    assert system_link(ui).locator(".status-count").count() == 0
    assert system_link(ui).get_attribute("aria-label") == "System: all well"


def test_a_reading_that_cannot_be_fetched_is_not_a_well_badge(ui):
    ui.serve("**/api/health", [(503, {"error": "the panel is unavailable"})])
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert system_link(ui).get_attribute("aria-label") != "System: all well"
    assert system_link(ui).locator(".status-count").count() == 1


def test_the_indicator_names_which_wall_went_quiet(ui, a_health_reading, a_wall_reading):
    """Colour is never the sole carrier — and here nor is the glyph.

    "Something is wrong somewhere" is a sentence a curator cannot act on, and it
    is what a single aggregated heartbeat could say. The reading is per wall so
    that this one names the room, and the other room is not implicated.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(
            walls=[
                a_wall_reading(wall_id="wall-1", name="The living room"),
                a_wall_reading(wall_id="wall-2", name="The study", absent=True),
            ]
        ),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    indicator = ui.page.locator("#status")
    words = indicator.inner_text()
    assert "The study has not reported" in words
    assert "The living room" not in words, "the wall that is reporting was named as a problem"
    # Three carriers, and the glyph is the one a stylesheet cannot supply.
    assert indicator.locator(".glyph").count() == 1


def test_the_indicator_says_well_when_every_observation_is_well(ui, a_health_reading):
    """The paired negative: an indicator that always warns is one nobody reads.

    Stubbed rather than seeded, because "the backup ran and the display plane is
    reporting" is a state a test deployment cannot be asked for — there is no
    display plane, by design.
    """
    ui.serve("**/api/health", a_health_reading())
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='well']")

    assert ui.page.inner_text("#status").strip().endswith("Well")


def test_the_indicator_takes_its_state_from_the_readings_and_not_from_the_summary(ui, a_health_reading, a_wall_reading):
    """The aggregate's `description` is a summary, never a fourth signal.

    It applies no threshold and reaches no verdict, deliberately: whether four
    minutes is late depends on whether that television was switched off on
    purpose, which the curation plane does not know. A client that read the words
    would be inventing the judgement the plane declined to make — so a cheerful
    sentence over a silent wall must not turn the indicator green.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(
            walls=[a_wall_reading(name="The study", absent=True)],
            description="Every wall has reported.",
        ),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "The study has not reported" in ui.page.inner_text("#status")


def test_the_indicator_names_a_reading_that_could_not_be_read(ui, a_health_reading, a_wall_reading):
    """`absent` and `unreadable` are different answers, and the indicator keeps them apart.

    Nothing has ever written one is a normal state on a fresh deployment; a file
    that exists and will not parse is a fault, and the observation records the two
    separately for exactly that reason. An indicator that read only `absent` would
    report a corrupted receipt as well.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(walls=[a_wall_reading(name="The study", problem="Expecting value: line 1 column 1")]),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    words = ui.page.inner_text("#status")
    assert "The study's heartbeat cannot be read" in words
    assert "has not reported" not in words, "an unreadable file was reported as a silent one"


def test_the_indicator_names_a_backup_that_has_never_run(ui, a_health_reading, a_backup_reading):
    """The catalogue is the irreplaceable asset, and its absence is the reading to watch.

    Held apart from the wall readings because it is a different subject: a wall
    going quiet costs an evening's pictures, and no backup costs everything.
    """
    ui.serve("**/api/health", a_health_reading(backup=a_backup_reading(absent=True)))
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "The catalogue has never been backed up" in ui.page.inner_text("#status")


def test_the_indicator_refuses_to_report_well_from_a_reading_it_did_not_take(ui, a_health_reading):
    """A green dot computed from nothing is this product's characteristic failure in a costume.

    `GET /api/health`'s shape is another chunk's to change — it changed once
    during this very work — and the indicator has no field name of its own to
    fall back on. What it must never do is treat an observation it cannot find as
    an observation that was fine.
    """
    reading = a_health_reading()
    del reading["walls"]
    ui.serve("**/api/health", reading)
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "carries no walls" in ui.page.inner_text("#status")


def test_a_deployment_with_no_wall_at_all_is_not_reported_as_well(ui, a_health_reading):
    """A wall is created when the plane first opens the catalogue, so none is a state.

    Nothing can be shown at all, and there is no missing heartbeat to say so —
    which is exactly the shape of silence an empty list would sail through.
    """
    ui.serve("**/api/health", a_health_reading(walls=[]))
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "No wall is recorded" in ui.page.inner_text("#status")


def test_a_health_reading_that_cannot_be_fetched_does_not_read_as_well(ui):
    """And it does not take the screen underneath it down either.

    The indicator's own failure is not a refusal of whatever the curator just
    did, so it says so in the indicator rather than in the page's error banner.
    """
    ui.serve("**/api/health", [(503, {"error": "the panel is unavailable"})])
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert "could not be fetched" in ui.page.inner_text("#status")
    # The grid still painted, and nothing shouted at the curator about it.
    assert ui.page.locator("#error:not([hidden])").count() == 0


# -- a contextual screen returns where it was opened from ---------------------


@pytest.fixture
def one_work(service, seeded_service):
    """The catalogue's first work, whichever it is."""
    return service.list_artworks(limit=1).entries[0].artwork


def test_a_work_opened_from_artworks_returns_to_artworks(ui, one_work):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    ui.page.click("ul.grid li.card .card-title button")
    # The back link, not a heading: Collection has an `h2` of its own, so waiting
    # for one after the click waits for nothing and everything below reads the
    # grid rather than the work. Only a contextual screen draws a way back, which
    # makes its arrival the fact that the work opened — and what it *says* is
    # still the assertion.
    ui.page.wait_for_selector("#view button:has-text('←')")

    back = ui.page.locator("#view button", has_text="←").first
    assert back.inner_text() == "← Artworks"
    back.click()
    ui.page.wait_for_selector("ul.grid")
    assert lit(ui, "collection").count() == 1


def test_the_same_work_opened_from_the_walls_returns_to_the_walls(ui, one_work):
    """The requirement, and the failure it replaces.

    The route out of a detail screen used to be a fixed parent — "← All works",
    whatever route in had been taken — so a Work reached from anywhere but the
    grid sent the curator somewhere they had not been. Nothing about the work
    changes here; only where it was opened from.
    """
    ui.open(f"#work/{one_work.id}?from=walls")
    ui.page.wait_for_selector("#view h2")

    back = ui.page.locator("#view button", has_text="←").first
    assert back.inner_text() == "← Walls"
    back.click()
    ui.page.wait_for_selector("#view h2:has-text('Walls')")


def test_the_page_a_work_was_opened_from_stays_lit(ui, one_work):
    """A contextual screen is *in* the page it came from, and says so."""
    ui.open(f"#work/{one_work.id}?from=walls")
    ui.page.wait_for_selector("#view h2")

    assert lit(ui, "walls").count() == 1


def test_where_a_work_was_opened_from_is_in_the_address(ui, one_work):
    """Which is what makes browser back do this natively, and a link carry it."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")
    ui.page.evaluate(f"() => go('work', {one_work.id!r})")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.evaluate("() => window.location.hash") == f"#work/{one_work.id}?from=walls"


def test_the_default_opener_is_left_out_of_the_address(ui, one_work):
    """A parameter that says what its absence already says is noise in a copied URL.

    A Work opened from Collection is the ordinary case, and `?from=collection`
    changes nothing — a missing opener resolves to exactly that. The parameter
    earns its place only when it carries information.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.evaluate(f"() => go('work', {one_work.id!r})")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.evaluate("() => window.location.hash") == f"#work/{one_work.id}"


def test_browser_back_leaves_a_work_for_the_page_it_was_opened_from(ui, one_work):
    """Every contextual screen is a real URL, so the browser's own back does this."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2:has-text('Walls')")
    ui.page.evaluate(f"() => go('work', {one_work.id!r})")
    ui.page.wait_for_selector("#view h2")

    ui.page.go_back()
    ui.page.wait_for_selector("#view h2:has-text('Walls')")


def test_a_work_reached_with_no_opener_still_has_a_way_out(ui, one_work):
    """A bookmark and an agent's link carry no opener, and must not be a dead end."""
    ui.open(f"#work/{one_work.id}")
    ui.page.wait_for_selector("#view h2")

    assert ui.page.locator("#view button", has_text="←").first.inner_text() == "← Artworks"


@pytest.fixture
def a_theme(services):
    return services.display.add_theme(name="Late night")


def test_a_theme_reached_with_no_opener_returns_to_themes(ui, a_theme):
    """One theme's default return is its own index, now that Themes is a page.

    A bookmark or an agent's link carries no opener. Without this default a theme
    reached that way had no way back and nothing lit in the sidebar, because a
    page has no `opensFrom` to fall back to.
    """
    ui.open(f"#theme/{a_theme.id}")
    ui.page.wait_for_selector("#view h2:has-text('Late night')")

    assert ui.page.locator("#view button", has_text="←").first.inner_text() == "← Themes"
    assert lit(ui, "theme").count() == 1


def test_a_theme_opened_from_the_themes_page_carries_no_opener(ui, a_theme):
    """The default is left out of the address, as it is for every contextual screen."""
    ui.open("#theme")
    ui.page.wait_for_selector("#view h2:has-text('Themes')")
    ui.page.evaluate(f"() => go('theme', {a_theme.id!r})")
    ui.page.wait_for_selector("#view h2:has-text('Late night')")

    assert ui.page.evaluate("() => window.location.hash") == f"#theme/{a_theme.id}"


# -- the persistent search affordance -----------------------------------------


def test_the_search_box_is_on_every_page(ui, seeded_service):
    """Persistent because at thousands of works it is the primary way in, and a
    retrieval mechanism you must first navigate to is one more step on the most
    frequent action."""
    for view, _heading in SIDEBAR_PAGES:
        ui.open(f"#{view}")
        ui.page.wait_for_selector("#view h2")
        assert ui.page.locator("#search-form input#search").count() == 1, view


def test_searching_from_anywhere_lands_in_artworks(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2:has-text('Walls')")

    ui.page.fill("#search", "Nighthawks")
    ui.page.press("#search", "Enter")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    assert lit(ui, "collection").count() == 1


def test_a_search_is_in_the_address_and_narrows_the_grid(ui, service, seeded_service):
    """Addressable state, and the affordance actually doing something.

    A search box that navigates and changes nothing is a dead control, which
    teaches a curator the collection cannot be searched.
    """
    service.add_artwork(title="A singular study of nothing")

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    everything = ui.page.locator("ul.grid li.card").count()

    ui.page.fill("#search", "singular study")
    ui.page.press("#search", "Enter")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    assert ui.page.evaluate("() => window.location.hash") == "#collection?q=singular%20study"
    found = ui.page.locator("ul.grid li.card").count()
    assert found == 1
    assert found < everything, "the search matched everything, so it cannot have narrowed anything"


def test_the_search_is_the_catalogue_s_and_not_this_screen_s(ui, service, seeded_service):
    """The query goes to the server, which searches more than the grid holds.

    This screen filtered client-side over title and artist for exactly as long as
    there was no server-side search to send the query to. `GET /api/works` grew
    `q` in the same wave as this chunk, and it searches six fields — the medium
    among them — over the whole catalogue rather than over whatever one screen
    happened to load.

    Medium is the field that tells the two apart: a client-side filter reading
    title and artist cannot find this work however many pages it fetched, so this
    test fails the moment the search stops being the catalogue's. The count in
    the heading is the second half of the same claim — it is a statement about
    the catalogue, not about this page.
    """
    service.add_artwork(title="Untitled", medium="Tempera on panel")

    ui.open("#collection?q=Tempera")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    assert ui.page.locator("ul.grid li.card").count() == 1
    # "1 work", not "1 works". The heading pluralises as of the chunk that gave
    # the grid its rails: a theme holding one work made the old wording visible
    # often enough to fix, and this line is the copy it was asserting.
    assert ui.page.inner_text("#view h2") == "1 work matching \u201cTempera\u201d"


def test_a_search_finds_a_work_by_its_artist(ui, seeded_service):
    """Attribution is the first thing anyone judges a work by, so it is searchable.

    The seeded work is "The Persistence of Memory", which holds none of the
    letters of the artist searched for — so a search reading only the title
    cannot pass this, which is the point.
    """
    ui.open("#collection?q=Dal%C3%AD")
    ui.page.wait_for_selector("ul.grid li.card")

    assert ui.page.locator("ul.grid li.card").count() == 1
    assert "The Persistence of Memory" in ui.text()


def test_a_search_that_matches_nothing_says_so_and_offers_the_way_back(ui, seeded_service):
    """An empty grid with no sentence reads as an empty collection."""
    ui.open("#collection?q=nothingwhatevermatchesthis")
    # The empty state itself, rather than the heading above it: Collection's
    # loading placeholder is an `h2` too, so waiting on one could return before
    # the search had answered. Same assertion, sounder wait.
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing held matches" in ui.text()
    ui.page.click("#view button:has-text('Show everything')")
    ui.page.wait_for_selector("ul.grid li.card")


def test_a_bookmarked_search_reopens_with_the_box_filled_in(ui, seeded_service):
    """Otherwise the grid is narrowed and the control that narrowed it is blank —
    a curator seeing a short collection with no visible reason."""
    ui.open("#collection?q=study")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    assert ui.page.input_value("#search") == "study"


def test_browser_back_undoes_a_search(ui, seeded_service):
    """A search is a navigation, so the way out of one is the way out of any of them."""
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")
    everything = ui.page.locator("ul.grid li.card").count()

    ui.page.fill("#search", "study")
    ui.page.press("#search", "Enter")
    ui.page.wait_for_selector("#view h2:has-text('matching')")

    ui.page.go_back()
    # The searched screen holds no grid at all — nothing seeded matches — so
    # waiting on one is what distinguishes the repaint from the stale DOM.
    ui.page.wait_for_selector("ul.grid li.card")
    assert ui.page.locator("ul.grid li.card").count() == everything


# -- the addresses the surface used to answer to ------------------------------


def aliases(ui) -> dict[str, str]:
    """`FRAGMENT_ALIASES`, read from the module the router uses, not copied here."""
    return ui.page.evaluate("async () => (await import('/static/core/route.js')).FRAGMENT_ALIASES")


def test_every_old_address_opens_the_page_that_took_over(ui, seeded_service):
    """Parametrised over the alias table itself, so an alias added later is tested
    the day it is added. A bookmark that lands on the home page is a curator told,
    wrongly, that what they saved is gone."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")
    table = aliases(ui)
    assert table, "the alias table read as empty, which would make this test pass vacuously"

    for old, now in table.items():
        ui.open(f"#{old}")
        ui.page.wait_for_function(f"() => window.location.hash === '#{now}'")
        ui.page.wait_for_selector("#view h2")
        # The address bar is corrected, so what a curator copies is what this
        # surface would produce, and the page that took over is the one lit.
        assert lit(ui, now).count() == 1, old


def test_the_system_badge_counts_a_source_that_failed_or_faulted_and_not_one_that_declined(
    ui, a_health_reading, a_source_reading
):
    """A failed plugin makes works read as held by nobody, which looks like a fact
    about art, and a faulting one leaves them waiting with nothing saying why; a
    declined one is configured off on purpose. Three
    plugins, two problems, so a badge that counted every non-loaded plugin, or
    ignored faults, fails."""
    ui.serve(
        "**/api/health",
        a_health_reading(
            sources=[
                a_source_reading(name="commons", state="declined", reason="WIKIDATA_USER_AGENT is unset"),
                a_source_reading(name="artic", faults=3),
                a_source_reading(name="gallery", state="failed", reason="it could not be imported"),
            ]
        ),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")

    assert system_link(ui).get_attribute("aria-label") == "System: 2 problems"
    words = ui.page.locator("#status").inner_text()
    assert "The gallery source could not be loaded" in words
    assert "The artic source has faulted since startup" in words
    assert "commons" not in words
