"""The Work page: the picture, the title, where the work hangs, and Hang….

S1 is the scenario this page exists for: from a work's page, hang it on a wall.
Its evidence is read back from the API — the wall's own record of what hangs on
it — as well as from the page's strip, because a strip that repainted from its
own idea of what it asked for would agree with itself whatever the server did.
Two walls appear wherever a wall is named, since with one wall "the wall it is
on" and "some wall" look the same.
"""

import httpx
import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import MatMethod, RenditionKind


@pytest.fixture
def hangable(work_with_an_image, service):
    """A work with its image on disk, a mat and a wall render: one a wall can show."""

    def _hangable(title="Nighthawks"):
        work = work_with_an_image(title)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        service.record_rendition(
            artwork_id=work.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=f"ready/{work.id}.jpg",
        )
        return work

    return _hangable


@pytest.fixture
def api(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def first_wall(services):
    return services.display.survey_walls()[0].wall


def open_work(ui, work):
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_selector(".state-strip dl")


def strip_value(ui, term):
    """The strip's value for `term`, as read."""
    return ui.page.locator(f".state-strip dt:text-is('{term}') + dd").inner_text()


def hanging_on(api, wall_id):
    """What the server says hangs on a wall: its theme, and that theme's works."""
    wall = next(wall for wall in api.get("/api/walls").json()["walls"] if wall["wall_id"] == wall_id)
    if wall["theme"] is None:
        return None, []
    detail = api.get(f"/api/themes/{wall['theme']['theme_id']}").json()
    return wall["theme"], [work["artwork_id"] for work in detail["works"]]


# -- anatomy -------------------------------------------------------------------


def test_the_title_is_the_one_h1_and_the_picture_is_the_largest_thing(ui, hangable):
    work = hangable("Automat")

    open_work(ui, work)
    ui.page.wait_for_function("() => document.querySelector('img.work-picture')?.complete")

    assert ui.page.locator("h1").all_inner_texts() == ["Automat"]
    # A landscape picture spans its column, however few pixels the copy served
    # has: the thumbnail is smaller than the column on any desktop.
    spans = ui.page.evaluate("""() => {
        const picture = document.querySelector('img.work-picture');
        const column = picture.parentElement;
        const style = getComputedStyle(column);
        const inner = column.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        return picture.getBoundingClientRect().width / inner;
    }""")
    assert spans > 0.95
    largest = ui.page.evaluate("""() => {
        const area = (node) => { const box = node.getBoundingClientRect(); return box.width * box.height; };
        const picture = area(document.querySelector('img.work-picture'));
        const others = [...document.querySelectorAll(
            '#view h1, #view dl, #view table, #view p, #view button, #view img:not(.work-picture)')];
        return others.every((node) => area(node) < picture);
    }""")
    assert largest


def test_archive_is_secondary_and_hang_is_the_act_in_reach(ui, hangable):
    work = hangable("Automat")

    open_work(ui, work)

    assert ui.page.locator("#view button:text-is('Archive')").get_attribute("class") == "action quiet"
    assert ui.page.locator(".state-strip button:text-is('Hang…')").get_attribute("class") == "action"


# -- the state strip -----------------------------------------------------------


def test_the_strip_names_real_themes_and_a_selection_as_its_wall(ui, services, hangable):
    work = hangable("Automat")
    other = hangable("Chop Suey")
    hall = first_wall(services)
    study = services.display.add_wall(name="Study")
    late = services.display.add_theme(name="Late night")
    services.display.add_to_theme(theme_id=late.id, artwork_id=work.id)
    services.display.add_to_theme(theme_id=late.id, artwork_id=other.id)
    services.display.activate_theme(late.id, wall_id=hall.id)
    unhung = services.display.add_theme(name="Quiet")
    services.display.add_to_theme(theme_id=unhung.id, artwork_id=work.id)
    without = services.display.add_theme(name="Without it")
    services.display.add_to_theme(theme_id=without.id, artwork_id=other.id)
    services.display.hang_selection([work.id], wall_id=study.id)

    open_work(ui, work)

    assert strip_value(ui, "Walls") == f"{hall.name}, Study"
    assert strip_value(ui, "Themes") == f"Late night (on {hall.name}); Quiet"
    assert ui.page.locator(".state-strip a:text-is('Quiet')").get_attribute("href").startswith(f"#theme/{unhung.id}")
    assert "Selection" not in ui.page.inner_text(".state-strip")


def test_an_old_selection_hanging_nowhere_is_not_said(ui, services, hangable):
    work = hangable("Automat")
    other = hangable("Chop Suey")
    wall = first_wall(services)
    services.display.hang_selection([work.id], wall_id=wall.id)
    services.display.hang_selection([other.id], wall_id=wall.id)

    open_work(ui, work)

    assert strip_value(ui, "Walls") == "Not hanging on any wall."
    assert strip_value(ui, "Themes") == "In no theme."


# -- S1: hang one work ---------------------------------------------------------


def test_s1_hanging_a_work_from_its_page_puts_it_on_the_wall(ui, api, services, hangable):
    work = hangable("Automat")
    hangable("Chop Suey")
    wall = first_wall(services)
    theme = services.display.add_theme(name="Late night")
    services.display.activate_theme(theme.id, wall_id=wall.id)

    open_work(ui, work)
    ui.page.click(".state-strip button:text-is('Hang…')")
    ui.page.wait_for_selector("dialog.confirm[open]")

    assert ui.page.inner_text(".confirm-title") == f"Hang Automat on {wall.name}?"
    assert "in place of Late night" in ui.page.inner_text(".confirm-consequence")
    ui.page.click(".confirm-actions button:text-is('Hang')")
    ui.page.wait_for_selector(f".state-strip .strip-said:text-is('Hung on {wall.name}.')")

    hung, works = hanging_on(api, wall.id)
    assert hung["hidden"] is True
    assert works == [work.id]
    assert strip_value(ui, "Walls") == wall.name
    # The keyboard is back on the control that stands where the pressed one did.
    assert ui.page.evaluate("() => document.activeElement.textContent") == "Hang…"


def test_declining_the_question_hangs_nothing(ui, api, services, hangable):
    work = hangable("Automat")
    wall = first_wall(services)
    theme = services.display.add_theme(name="Late night")
    services.display.activate_theme(theme.id, wall_id=wall.id)

    open_work(ui, work)
    ui.page.click(".state-strip button:text-is('Hang…')")
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click(".confirm-actions button:text-is('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    hung, _ = hanging_on(api, wall.id)
    assert hung["theme_id"] == theme.id


def test_with_two_walls_hang_asks_which_and_hangs_only_there(ui, api, services, hangable):
    work = hangable("Automat")
    hall = first_wall(services)
    study = services.display.add_wall(name="Study")

    open_work(ui, work)
    ui.page.click(".state-strip button:text-is('Hang…')")
    ui.page.click(".wall-picker button:text-is('Study')")
    ui.page.wait_for_selector("dialog.confirm[open]")

    assert ui.page.inner_text(".confirm-title") == "Hang Automat on Study?"
    ui.page.click(".confirm-actions button:text-is('Hang')")
    ui.page.wait_for_selector(".state-strip .strip-said:text-is('Hung on Study.')")

    assert hanging_on(api, study.id)[1] == [work.id]
    assert hanging_on(api, hall.id) == (None, [])
    assert strip_value(ui, "Walls") == "Study"


def test_a_work_hung_that_cannot_be_shown_yet_says_why(ui, services, work_with_an_image):
    """No wall render yet: the hang lands, and the build says the work is not on the wall."""
    work = work_with_an_image("Automat")
    wall = first_wall(services)

    open_work(ui, work)
    ui.page.click(".state-strip button:text-is('Hang…')")
    ui.page.click(".confirm-actions button:text-is('Hang')")
    ui.page.wait_for_selector(".state-strip .strip-said:has-text('cannot be shown yet')")

    assert ui.page.inner_text(".state-strip .strip-said").startswith(f"Hung on {wall.name}, but it cannot be shown yet: ")


# -- kept off every wall -------------------------------------------------------


def test_a_work_kept_off_every_wall_says_so_and_offers_the_undo(ui, api, services, hangable):
    work = hangable("Automat")
    wall = first_wall(services)
    theme = services.display.add_theme(name="Late night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=wall.id)
    services.display.exclude_work(work.id, wall_id=wall.id)

    open_work(ui, work)

    assert strip_value(ui, "Walls").startswith("Kept off every wall since ")
    assert ui.page.locator(".state-strip button:text-is('Hang…')").count() == 0
    ui.page.click(".state-strip button:text-is('Allow on walls again')")
    ui.page.wait_for_selector(".state-strip button:text-is('Hang…')")

    assert api.get("/api/exclusions").json()["exclusions"] == []
    assert strip_value(ui, "Walls") == wall.name
    assert ui.page.inner_text(".state-strip .strip-said") == (
        "It may go on walls again the next time a theme holding it is hung. " "Re-hanging a wall's current theme does that now."
    )
    assert ui.page.evaluate("() => document.activeElement.textContent") == "Hang…"


def test_an_archived_work_offers_no_hang(ui, service, hangable):
    work = hangable("Automat")
    service.archive_artwork(work.id)

    open_work(ui, work)

    assert ui.page.locator(".state-strip button").count() == 0
    assert ui.page.locator(".state-strip dt:text-is('Walls')").count() == 0
    assert ui.page.locator("#view button:text-is('Restore')").get_attribute("class") == "action"


# -- the description's emphasis ------------------------------------------------


def test_a_museum_description_shows_its_emphasis_and_no_tags(ui, service):
    work = service.add_artwork(
        title="Untitled",
        description="<em>Untitled</em> follows the <strong>format</strong> &amp; more.<p>Second paragraph.",
    )

    open_work(ui, work)
    description = ui.page.locator(".facts dd .described")

    assert description.locator("i").inner_text() == "Untitled"
    assert description.locator("b").inner_text() == "format"
    text = description.inner_text()
    assert "<" not in text
    assert "&amp;" not in text
    assert "format & more." in text
    assert "\n" in text
    assert text.endswith("Second paragraph.")


@pytest.mark.parametrize(
    ("markup", "tags", "text"),
    [
        # Only the four tags become elements; everything else is its own characters.
        ('<img src=x onerror="alert(1)"><i>a</i>', ["I"], '<img src=x onerror="alert(1)">a'),
        ("&lt;i&gt;not emphasis&lt;/i&gt;", [], "<i>not emphasis</i>"),
        ("<i class=x>a</i>", [], "<i class=x>a</i>"),
        ("&nbsp;&#60;", [], "&nbsp;&#60;"),
        ("</b>stray<b>open", ["B"], "</b>strayopen"),
        ("<i><b>both</b></i>", ["I", "B"], "both"),
    ],
)
def test_the_tokeniser_builds_only_i_and_b(ui, service, markup, tags, text):
    ui.open("#")
    built = ui.page.evaluate(
        """async (markup) => {
            const { emphasised } = await import('/static/core/render.js');
            const node = emphasised(markup);
            return { tags: [...node.querySelectorAll('*')].map((child) => child.tagName), text: node.textContent };
        }""",
        markup,
    )

    assert built == {"tags": tags, "text": text}
