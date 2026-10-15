"""The way back out of a page, and a page whose thing is not there.

`information-architecture.md` § Direction rules that a back link "returns to the
page it was opened from". The second UX walk (`ux-review-2026-10.md` finding 35,
#356) found it built for a Work opened from a list and nothing else: a work
opened from Dalí's page said "← Artists", an artist opened from a work said
"← Artworks", and a work opened from search results lost the query. The
browser's Back was right every time, so the two disagreed.

The same walk (finding 42, #361) found that an address naming nothing left the
previous page painted under the new title, and that a fresh load of a dead
work's address sat on "Loading the catalogue…" for good.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

BACK = "#view > p:first-child a"


def back_link(ui):
    """The page's way back, once the page has painted one."""
    ui.page.wait_for_selector(BACK)
    return ui.page.locator(BACK).first


def hash_now(ui) -> str:
    return ui.page.evaluate("() => window.location.hash")


@pytest.fixture
def varo(service):
    return service.add_artist(name="Remedios Varo", nationality="Spanish", born=1908, died=1963)


@pytest.fixture
def pablum(service, varo):
    return service.add_artwork(title="Celestial Pablum", artist_id=varo.id, date_created="1958")


@pytest.fixture
def a_theme_holding_it(services, pablum):
    theme = services.display.add_theme(name="Night kitchens")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=pablum.id)
    return theme


# -- the way back names its opener and returns to it --------------------------------


def test_a_work_opened_from_an_artist_returns_to_that_artist(ui, varo, pablum):
    ui.open(f"#artist/{varo.id}")
    ui.page.click(f"#view a:text-is('{pablum.title}')")
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")

    back = back_link(ui)
    assert back.inner_text() == "← Remedios Varo"
    back.click()
    ui.page.wait_for_function("() => document.title === 'Remedios Varo - Arrt'")
    assert hash_now(ui) == f"#artist/{varo.id}"


def test_an_artist_opened_from_a_work_returns_to_that_work(ui, varo, pablum):
    ui.open(f"#work/{pablum.id}")
    ui.page.click(f"#view a:text-is('{varo.name}')")
    ui.page.wait_for_function("() => document.title === 'Remedios Varo - Arrt'")

    back = back_link(ui)
    assert back.inner_text() == "← Celestial Pablum"
    back.click()
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")
    assert hash_now(ui).startswith(f"#work/{pablum.id}")


def test_a_theme_opened_from_a_work_returns_to_that_work(ui, pablum, a_theme_holding_it):
    ui.open(f"#work/{pablum.id}")
    ui.page.click(f"#view a:text-is('{a_theme_holding_it.name}')")
    ui.page.wait_for_function("() => document.title === 'Night kitchens - Arrt'")

    back = back_link(ui)
    assert back.inner_text() == "← Celestial Pablum"
    back.click()
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")


def test_a_work_opened_from_search_results_returns_to_them_with_the_query(ui, pablum):
    ui.open("#search?q=Pablum")
    ui.page.wait_for_function("() => document.title.startsWith('Results for')")
    ui.page.click(f"#view a:text-is('{pablum.title}')")
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")

    back = back_link(ui)
    assert back.inner_text() == "← Results for “Pablum”"
    back.click()
    ui.page.wait_for_function("() => document.title.startsWith('Results for')")
    assert "q=Pablum" in hash_now(ui)


def test_search_results_opened_from_an_artist_return_to_that_artist(ui, varo):
    ui.open(f"#artist/{varo.id}")
    ui.page.wait_for_function("() => document.title === 'Remedios Varo - Arrt'")
    box = ui.page.locator("#search")
    box.fill("Pablum")
    box.press("Enter")
    ui.page.wait_for_function("() => document.title.startsWith('Results for')")

    back = back_link(ui)
    assert back.inner_text() == "← Remedios Varo"
    back.click()
    ui.page.wait_for_function("() => document.title === 'Remedios Varo - Arrt'")


def test_a_page_opened_from_a_link_elsewhere_still_names_where_it_returns(ui, varo, pablum):
    """A bookmark that carries its opener knows where it goes, if not yet its name."""
    ui.open(f"#work/{pablum.id}?from=artist%2F{varo.id}")
    back = back_link(ui)
    assert back.inner_text() == "← Artist"
    assert back.get_attribute("href") == f"#artist/{varo.id}"


def test_a_page_opened_cold_returns_to_its_index(ui, pablum):
    ui.open(f"#work/{pablum.id}")
    assert back_link(ui).inner_text() == "← Artworks"


# -- an address that names nothing -------------------------------------------------------

DEAD = "00000000-0000-4000-8000-000000000000"


@pytest.mark.parametrize(
    ("address", "index"),
    [
        (f"#work/{DEAD}", "Artworks"),
        (f"#artist/{DEAD}", "Artists"),
        (f"#theme/{DEAD}", "Themes"),
    ],
)
def test_a_dead_address_reached_from_a_live_page_shows_nothing_of_that_page(ui, pablum, address, index):
    ui.open(f"#work/{pablum.id}")
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")
    ui.page.evaluate("(address) => { window.location.hash = address; }", address)

    ui.page.wait_for_selector("#view .not-found")
    assert "Celestial Pablum" not in ui.page.locator("#view").inner_text()
    assert ui.page.locator("#view .not-found a", has_text=index).count() == 1


def test_a_fresh_load_of_a_dead_works_address_says_so(ui):
    ui.open(f"#work/{DEAD}")
    ui.page.wait_for_selector("#view .not-found")
    assert "Loading" not in ui.page.locator("#view").inner_text()


# -- a topic, both ways ------------------------------------------------------------------

WINTER = "Q1311"


@pytest.fixture
def a_wintry_work(service, pablum):
    service.record_facet(artwork_id=pablum.id, kind="subject", value="winter", derivation="sourced", value_qid=WINTER)
    return pablum


def test_a_topic_opened_from_a_work_returns_to_that_work(ui, a_wintry_work):
    ui.open(f"#work/{a_wintry_work.id}")
    ui.page.click("#view dl.facets a:text-is('winter')")
    # The address changes, and the router titles the page "Topic", before the
    # topic paints, while the work's own way back ("← Artworks") still satisfies
    # `back_link`; so wait for the topic's own name, as every other arrival here
    # waits on its destination's title.
    ui.page.wait_for_function("() => document.title === 'Winter - Arrt'")

    back = back_link(ui)
    assert back.inner_text() == "← Celestial Pablum"
    back.click()
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")


def test_a_work_opened_from_a_topic_returns_to_that_topic(ui, a_wintry_work):
    ui.open(f"#topic/{WINTER}")
    ui.page.click(f"#view a:text-is('{a_wintry_work.title}')")
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")

    assert f"from=topic%2F{WINTER}" in hash_now(ui)
    back = back_link(ui)
    assert back.get_attribute("href") == f"#topic/{WINTER}"
    back.click()
    ui.page.wait_for_function("(qid) => window.location.hash === `#topic/${qid}`", arg=WINTER)


# -- the rest of the screens about one thing ---------------------------------------------


def test_a_dead_reviews_address_says_so(ui, pablum):
    ui.open(f"#work/{pablum.id}")
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")
    ui.page.evaluate("(address) => { window.location.hash = address; }", f"#review/{DEAD}")
    ui.page.wait_for_selector("#view .not-found")
    assert ui.page.locator("#view h1").inner_text() == "That review is not here"
    assert "Celestial Pablum" not in ui.page.locator("#view").inner_text()


# -- a page that could not be read -------------------------------------------------------


def test_a_page_whose_read_fails_on_arrival_shows_nothing_of_the_last(ui, pablum, varo):
    """A fault is the banner's, and the view says only that this page could not be shown."""
    ui.open(f"#work/{pablum.id}")
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")
    ui.page.route(
        f"**/api/artists/{varo.id}",
        lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "boom"}'),
    )
    ui.page.evaluate("(address) => { window.location.hash = address; }", f"#artist/{varo.id}")

    ui.page.wait_for_selector("#view .not-shown")
    assert ui.page.locator("#error").inner_text() == "boom"
    assert "Celestial Pablum" not in ui.page.locator("#view").inner_text()
    # A fault is not an absence: no page says the artist is gone.
    assert ui.page.locator("#view .not-found").count() == 0


def test_a_failed_repaint_of_the_page_showing_keeps_it(ui, pablum, varo):
    """A change of state on the same screen is a repaint, not an arrival: a fault
    leaves the page the curator was reading.

    The Work page with its opener changed is the same work, so the router
    repaints rather than arrives (Artworks would not do: it clears its own grid
    before it reads, whatever the router does).
    """
    ui.open(f"#work/{pablum.id}")
    ui.page.wait_for_function("() => document.title === 'Celestial Pablum - Arrt'")
    ui.page.route(
        f"**/api/works/{pablum.id}",
        lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "boom"}'),
    )
    ui.page.evaluate("(address) => { window.location.hash = address; }", f"#work/{pablum.id}?from=artist%2F{varo.id}")

    ui.page.wait_for_selector("#error:not([hidden])")
    assert ui.page.locator("#view h1").inner_text() == "Celestial Pablum"
    assert ui.page.locator("#view .not-shown").count() == 0
