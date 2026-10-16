"""Pictures where a person decides what to hang.

The second UX walk (`ux-review-2026-10.md` findings 37, 38 and 34; #358) found:
- Two works whose master the museum refuses read as text everywhere, in three
  wordings of the server's exception across four screens, with thumbnails
  asked for and refused.
- The search dropdown pictured strangers' works and not the library's own.
- Result pictures sat small inside the state's badge.
- The Work page's picture could not be enlarged.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

PLACEHOLDER = "No picture"
WINTER = "Q1311"


@pytest.fixture
def ekster(service):
    return service.add_artist(name="Aleksandra Ekster", born=1882, died=1949)


@pytest.fixture
def masterless(service, ekster):
    """A held work whose museum refuses its master: in circulation, with no image."""
    work = service.add_artwork(title="Crak!", artist_id=ekster.id, date_created="1915")
    service.record_facet(artwork_id=work.id, kind="subject", value="winter", derivation="sourced", value_qid=WINTER)
    return work


def placeholder_for(ui, work):
    card = ui.page.locator(f"#view [data-artwork='{work.id}'] .card-image-absent").first
    card.wait_for()
    return card.inner_text().strip()


@pytest.mark.parametrize(
    "where",
    ["#collection", "#artist/{artist}", f"#topic/{WINTER}"],
    ids=["artworks", "artist", "topic"],
)
def test_a_work_with_no_master_reads_the_same_on_every_screen_and_asks_for_nothing(ui, ekster, masterless, where):
    ui.open(where.format(artist=ekster.id))
    assert placeholder_for(ui, masterless) == PLACEHOLDER
    ui.page.wait_for_load_state("networkidle")
    assert ui.requests_matching(f"/api/works/{masterless.id}/thumbnail") == []


def test_the_work_page_draws_the_same_placeholder(ui, masterless):
    ui.open(f"#work/{masterless.id}")
    hero = ui.page.locator("#view .work-hero .card-image-absent")
    hero.wait_for()
    assert hero.inner_text().strip() == PLACEHOLDER
    ui.page.wait_for_load_state("networkidle")
    assert ui.requests_matching(f"/api/works/{masterless.id}/thumbnail") == []
    assert ui.requests_matching(f"/api/works/{masterless.id}/wall-preview") == []


def test_the_artists_index_pictures_an_artist_with_no_master_by_the_placeholder(ui, ekster, masterless):
    ui.open("#artist")
    poster = ui.page.locator(f"#view li.card[data-artist='{ekster.id}'] .card-image-absent")
    poster.wait_for()
    assert poster.inner_text().strip() == PLACEHOLDER
    ui.page.wait_for_load_state("networkidle")
    assert [url for url in ui.requests_matching("/thumbnail") if masterless.id in url] == []


def test_the_servers_reason_is_shown_only_to_debug(ui, masterless):
    ui.open("#collection")
    ui.page.locator(f"#view [data-artwork='{masterless.id}'] .card-image-absent").wait_for()
    assert ui.page.locator(f"#view [data-artwork='{masterless.id}'] .no-picture-note").count() == 0

    ui.page.goto(f"{ui.base_url}/?debug#collection")
    ui.page.locator(f"#view [data-artwork='{masterless.id}'] .card-image-absent").wait_for()
    note = ui.page.locator(f"#view [data-artwork='{masterless.id}'] .no-picture-note")
    assert note.count() == 1
    assert note.inner_text().strip()


# -- search --------------------------------------------------------------------------------


def type_in_search(ui, words):
    ui.open("#collection")
    ui.page.fill("#search", words)
    ui.page.wait_for_selector("#search-suggestions [role='option']")


def test_a_held_work_in_the_dropdown_carries_its_picture(ui, work_with_an_image):
    work = work_with_an_image(title="Nighthawks at the diner")
    type_in_search(ui, "Nighthawks at")
    option = ui.page.locator("#search-suggestions [role='option']", has_text="Nighthawks at the diner").first
    picture = option.locator("img")
    picture.wait_for()
    assert f"/api/works/{work.id}/thumbnail" in picture.get_attribute("src")
    # Beside the name, not inside a badge.
    assert option.locator(".badge img").count() == 0


def test_a_held_work_with_no_master_in_the_dropdown_asks_for_no_picture(ui, masterless):
    type_in_search(ui, "Crak")
    option = ui.page.locator("#search-suggestions [role='option']", has_text="Crak!").first
    option.wait_for()
    assert option.locator("img").count() == 0
    assert ui.requests_matching(f"/api/works/{masterless.id}/thumbnail") == []


def test_a_search_result_leads_with_its_picture_large_enough_to_judge(ui, work_with_an_image):
    work = work_with_an_image(title="Nighthawks at the diner")
    ui.open("#search?q=Nighthawks")
    row = ui.page.locator("#view li.row-pictured", has=ui.page.locator(f"a[href^='#work/{work.id}']")).first
    row.wait_for()
    # First of what is drawn: the row's tick comes before it and is hidden
    # outside Select mode, which takes it out of the layout as well.
    first, size, in_badge = row.evaluate("""(li) => {
          const pic = li.querySelector('.work-pic');
          const shown = [...li.children].find((child) => !child.hidden);
          return [shown === pic, pic.getBoundingClientRect().width, !!pic.closest('.badge')];
        }""")
    assert first
    assert size >= 64
    assert not in_badge


# -- the Work page's picture ----------------------------------------------------------------


def test_the_work_pages_picture_opens_large_and_closes_by_keyboard(ui, work_with_an_image):
    work = work_with_an_image(title="Nighthawks")
    ui.open(f"#work/{work.id}")
    button = ui.page.locator("#view .work-picture-button")
    button.wait_for()
    assert button.get_attribute("aria-label") == "Enlarge Nighthawks"

    button.focus()
    ui.page.keyboard.press("Enter")
    dialog = ui.page.locator("dialog.enlarged[open]")
    dialog.wait_for()
    assert f"/api/works/{work.id}/wall-preview" in dialog.locator("img").get_attribute("src")

    ui.page.keyboard.press("Escape")
    ui.page.wait_for_selector("dialog.enlarged[open]", state="detached")
    assert ui.page.evaluate("() => document.activeElement.classList.contains('work-picture-button')")
