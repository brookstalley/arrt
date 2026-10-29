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
def hangable(work_with_an_image, service, settings, decodable_jpeg):
    """A work with its image on disk, a mat and a presentation master: one a wall can show."""

    def _hangable(title="Nighthawks"):
        work = work_with_an_image(title)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        decodable_jpeg(settings.art_root / f"presentation/{work.id}.jpg", width=400, height=300)
        service.record_rendition(
            artwork_id=work.id,
            kind=RenditionKind.PRESENTATION_MASTER,
            target_width=7680,
            target_height=7680,
            path=f"presentation/{work.id}.jpg",
        )
        return work

    return _hangable


@pytest.fixture
def api(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def first_wall(services):
    return services.display.survey_walls()[0].wall


def open_work(ui, work, *, debug=False):
    ui.open(f"{'?debug' if debug else ''}#work/{work.id}")
    ui.page.wait_for_selector(".state-strip dl")


# The page's acts are in its toolbar, under the title (ruling 8 of 2026-10-27):
# Hang… and Add to theme… on its face, the rarer acts behind ⋯.
HANG = ".page-toolbar button:text-is('Hang…')"
ADD = ".page-toolbar button:text-is('Add to theme…')"
MORE = ".page-toolbar .action-menu-trigger"


def more(ui, item):
    """Choose `item` from ⋯, as a pointer does."""
    ui.page.click(MORE)
    ui.page.click(f".toolbar-menu [role='menuitem']:text-is('{item}')")


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
    # A landscape work spans its column, however few pixels the copy served
    # has: the thumbnail is smaller than the column on any desktop. What spans
    # it is the work in its mat, as a wall shows it (the owner, 2026-10-07):
    # the picture alone sits inside the mat's margins (`test_the_mat.py`).
    spans = ui.page.evaluate("""() => {
        const matted = document.querySelector('.work-hero .mat-surround');
        const column = document.querySelector('.work-picture-button');
        const style = getComputedStyle(column);
        const inner = column.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        return matted.getBoundingClientRect().width / inner;
    }""")
    assert spans > 0.95
    largest = ui.page.evaluate("""() => {
        const area = (node) => { const box = node.getBoundingClientRect(); return box.width * box.height; };
        const picture = area(document.querySelector('img.work-picture'));
        const others = [...document.querySelectorAll(
            '#view h1, #view dl, #view table, #view p, #view button:not(.work-picture-button), #view img:not(.work-picture)')];
        return others.every((node) => area(node) < picture);
    }""")
    assert largest


def test_hang_is_the_one_filled_act_and_archive_is_behind_more(ui, hangable):
    """Ruling 8: Hang is the page's one filled act, Add to theme beside it, and
    Archive and Match on Wikidata behind ⋯, named for the work, never the glyph."""
    work = hangable("Automat")

    open_work(ui, work)

    acts = ui.page.locator(".page-toolbar-actions > button, .page-toolbar-actions > .toolbar-menu-wrap > button")
    assert acts.all_inner_texts() == ["Hang…", "Add to theme…", "⋯"]
    assert ui.page.locator(".page-toolbar button.action:not(.quiet)").all_inner_texts() == ["Hang…"]
    assert ui.page.get_attribute(MORE, "aria-label") == "More acts on Automat"
    assert ui.page.locator("#view button:has-text('Archive')").count() == 0
    ui.page.click(MORE)
    assert ui.page.locator(".toolbar-menu [role='menuitem']").all_inner_texts() == ["Archive…", "Match on Wikidata…"]


def test_the_page_opens_with_its_title_a_line_of_facts_and_its_toolbar(ui, hangable, service):
    """Ruling 1's page head, in order, with the mat a fact that is its own control."""
    work = hangable("Automat")

    open_work(ui, work)
    ui.page.wait_for_selector(".work-facts .mat-trigger:not(:disabled)")

    order = ui.page.evaluate("""() => [...document.querySelectorAll('#view > *')].slice(0, 4).map((node) =>
        node.matches('h1') ? 'title'
        : node.matches('.work-facts') ? 'facts'
        : node.matches('.page-toolbar') ? 'toolbar'
        : node.querySelector('a') ? 'back' : node.className)""")
    assert order == ["back", "title", "facts", "toolbar"]
    assert ui.page.locator(".work-facts .mat-trigger").inner_text().strip().endswith("▾")


@pytest.mark.parametrize("width", [390, 1280], ids=["phone", "desktop"])
def test_the_mat_fact_keeps_its_word_and_sits_on_the_line(ui, hangable, width):
    """ "Mat" never wraps away from its value, and the value's middle is the text's,
    within two pixels (three without the rule): found by photograph, both faults
    invisible to the DOM."""
    work = hangable("Automat")
    ui.page.set_viewport_size({"width": width, "height": 900})

    open_work(ui, work)
    ui.page.wait_for_selector(".work-facts .mat-trigger:not(:disabled)")

    word, value = ui.page.evaluate("""() => {
        const box = (node) => { const b = node.getBoundingClientRect(); return [b.top, b.bottom]; };
        return [box(document.querySelector('.fact-with-control > span')), box(document.querySelector('.mat-trigger'))];
    }""")
    assert value[0] <= (word[0] + word[1]) / 2 <= value[1], "Mat wrapped away from its value"
    assert abs((value[0] + value[1]) / 2 - (word[0] + word[1]) / 2) <= 2


# -- absences --------------------------------------------------------------------


def test_there_is_no_rights_fact_and_no_edit(ui, service):
    """Ruling 8: no rights, "good database info but not useful in the home"; and no
    Edit…, which has nothing to open until a work has a setting (the owner, 2026-10-29)."""
    work = service.add_artwork(title="Automat", rights="Public domain in the United States")

    open_work(ui, work)

    assert "Public domain in the United States" not in ui.page.inner_text("#view")
    assert ui.page.locator("#view dt:text-is('Rights')").count() == 0
    assert ui.page.locator("#view button:has-text('Edit')").count() == 0
    ui.page.click(MORE)
    assert ui.page.locator(".toolbar-menu [role='menuitem']:has-text('Edit')").count() == 0


def test_a_work_not_kept_off_says_nothing_about_being_kept_off(ui, hangable):
    work = hangable("Automat")

    open_work(ui, work)

    assert ui.page.locator(".state-strip .kept-off").count() == 0
    assert "Kept off" not in ui.page.inner_text("#view")


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
    ui.page.click(HANG)
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
    ui.page.click(HANG)
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
    ui.page.click(HANG)
    # A dialog of walls, in place of the row of buttons beside the strip (ruling 8).
    ui.page.wait_for_selector("dialog.panel-dialog[open] .wall-choices")
    assert sorted(ui.page.locator(".wall-choices button").all_inner_texts()) == sorted([hall.name, "Study"])
    ui.page.click(".wall-choices button:text-is('Study')")
    ui.page.wait_for_selector("dialog.confirm[open]")

    assert ui.page.locator("dialog.panel-dialog[open]").count() == 0
    assert ui.page.inner_text(".confirm-title") == "Hang Automat on Study?"
    ui.page.click(".confirm-actions button:text-is('Hang')")
    ui.page.wait_for_selector(".state-strip .strip-said:text-is('Hung on Study.')")

    assert hanging_on(api, study.id)[1] == [work.id]
    assert hanging_on(api, hall.id) == (None, [])
    assert strip_value(ui, "Walls") == "Study"


def test_a_work_hung_that_cannot_be_shown_yet_says_why(ui, services, work_with_an_image):
    """No presentation master yet: the hang lands, and the build says the work is not on the wall."""
    work = work_with_an_image("Automat")
    wall = first_wall(services)

    open_work(ui, work)
    ui.page.click(HANG)
    ui.page.click(".confirm-actions button:text-is('Hang')")
    ui.page.wait_for_selector(".state-strip .strip-said:has-text('cannot be shown yet')")

    assert ui.page.inner_text(".state-strip .strip-said").startswith(f"Hung on {wall.name}, but it cannot be shown yet: ")


def test_cancel_and_escape_in_the_walls_dialog_hang_nothing(ui, api, services, hangable):
    work = hangable("Automat")
    hall = first_wall(services)
    study = services.display.add_wall(name="Study")

    open_work(ui, work)
    for close in ("Cancel", "Escape"):
        ui.page.click(HANG)
        ui.page.wait_for_selector("dialog.panel-dialog[open] .wall-choices")
        if close == "Escape":
            ui.page.keyboard.press("Escape")
        else:
            ui.page.click("dialog.panel-dialog[open] button:text-is('Cancel')")
        ui.page.wait_for_selector("dialog[open]", state="detached")
        assert ui.focused() == "Hang…"

    assert ui.page.locator("dialog.confirm").count() == 0
    assert hanging_on(api, study.id) == (None, [])
    assert hanging_on(api, hall.id) == (None, [])


# -- Add to theme… ---------------------------------------------------------------


def theme_ids_holding(api, work_id):
    placements = api.get(f"/api/works/{work_id}/placements").json()
    return {placement["theme"]["name"] for placement in placements["themes"]}


def test_add_to_theme_offers_the_themes_without_it_and_adds_it(ui, api, services, hangable):
    """Ruling 8: Add to theme…, the selection's dialog for this one work, read back
    from the server, into the second theme offered rather than the default first."""
    work = hangable("Automat")
    holding = services.display.add_theme(name="Already")
    services.display.add_to_theme(theme_id=holding.id, artwork_id=work.id)
    services.display.add_theme(name="Late night")
    services.display.add_theme(name="Quiet")

    open_work(ui, work)
    ui.page.click(ADD)
    ui.page.wait_for_selector("dialog.panel-dialog[open] #add-to-theme")

    offered = ui.page.locator("#add-to-theme option").all_inner_texts()
    assert "Already" not in offered
    assert {"Late night", "Quiet", "New theme…"} <= set(offered)
    ui.page.select_option("#add-to-theme", label="Quiet")
    assert ui.page.inner_text("dialog[open] .add-confirm") == "Add to Quiet"
    ui.page.click("dialog[open] .add-confirm")
    ui.page.wait_for_selector(".state-strip .strip-said:text-is('Added Automat to Quiet.')")

    assert theme_ids_holding(api, work.id) == {"Already", "Quiet"}
    assert ui.page.locator("dialog[open]").count() == 0
    assert "Quiet" in strip_value(ui, "Themes")
    assert ui.focused() == "Add to theme…"


def test_add_to_a_new_theme_makes_it_and_adds_the_work(ui, api, services, hangable):
    work = hangable("Automat")
    services.display.add_theme(name="Late night")

    open_work(ui, work)
    ui.page.click(ADD)
    ui.page.wait_for_selector("dialog.panel-dialog[open] #add-to-theme")
    ui.page.select_option("#add-to-theme", label="New theme…")
    assert ui.page.locator("dialog[open] .add-confirm").is_disabled(), "a new theme needs its name"
    ui.page.fill("#add-to-theme-name", "Rainy days")
    ui.page.click("dialog[open] .add-confirm:text-is('Add to Rainy days')")
    ui.page.wait_for_selector(".state-strip .strip-said:text-is('Added Automat to Rainy days.')")

    assert theme_ids_holding(api, work.id) == {"Rainy days"}
    assert [theme["theme"]["name"] for theme in api.get("/api/themes").json()["themes"]].count("Rainy days") == 1


def test_cancel_and_escape_in_add_to_theme_add_nothing(ui, api, services, hangable):
    work = hangable("Automat")
    services.display.add_theme(name="Late night")
    before = len(api.get("/api/themes").json()["themes"])

    open_work(ui, work)
    for close in ("Cancel", "Escape"):
        ui.page.click(ADD)
        ui.page.wait_for_selector("dialog.panel-dialog[open] #add-to-theme")
        ui.page.select_option("#add-to-theme", label="New theme…")
        ui.page.fill("#add-to-theme-name", "Not made")
        if close == "Escape":
            ui.page.keyboard.press("Escape")
        else:
            ui.page.click("dialog[open] button:text-is('Cancel')")
        ui.page.wait_for_selector("dialog[open]", state="detached")
        assert ui.focused() == "Add to theme…"

    assert theme_ids_holding(api, work.id) == set()
    assert len(api.get("/api/themes").json()["themes"]) == before


# -- ⋯ ---------------------------------------------------------------------------


def test_more_opens_and_closes_from_the_keyboard(ui, hangable):
    """The menu's keyboard (`core/toolbar.js`): Enter opens on the first act,
    arrows move and wrap, Escape closes and hands the keyboard back to ⋯."""
    work = hangable("Automat")

    open_work(ui, work)
    ui.page.focus(MORE)
    ui.page.keyboard.press("Enter")
    ui.page.wait_for_selector(".toolbar-menu[role='menu']:visible")
    assert ui.page.get_attribute(MORE, "aria-expanded") == "true"
    assert ui.focused() == "Archive…"
    ui.page.keyboard.press("ArrowDown")
    assert ui.focused() == "Match on Wikidata…"
    ui.page.keyboard.press("ArrowDown")
    assert ui.focused() == "Archive…"
    ui.page.keyboard.press("ArrowUp")
    assert ui.focused() == "Match on Wikidata…"
    ui.page.keyboard.press("Escape")

    assert ui.page.locator(".toolbar-menu[role='menu']").is_hidden()
    assert ui.page.get_attribute(MORE, "aria-expanded") == "false"
    assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')") == "More acts on Automat"


def test_enter_on_an_item_runs_its_act(ui, hangable):
    work = hangable("Automat")

    open_work(ui, work)
    ui.page.focus(MORE)
    ui.page.keyboard.press("Enter")
    ui.page.keyboard.press("ArrowDown")
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("dialog.panel-dialog[open] .identity")
    assert ui.page.inner_text("dialog[open] .confirm-title") == "Match Automat on Wikidata"
    assert ui.page.locator(".toolbar-menu[role='menu']").is_hidden()
    # The menu closed onto ⋯ before the act opened its dialog, so closing the
    # dialog hands the keyboard back to ⋯, not to a menu item that is hidden.
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_selector("dialog[open]", state="detached")
    assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')") == "More acts on Automat"


# -- kept off every wall -------------------------------------------------------


def test_a_work_kept_off_every_wall_says_so_and_offers_the_undo(ui, api, services, hangable):
    work = hangable("Automat")
    wall = first_wall(services)
    theme = services.display.add_theme(name="Late night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=wall.id)
    services.display.exclude_work(work.id, wall_id=wall.id)

    open_work(ui, work)

    # An exception, quiet: one muted line, its undo a quiet act (ruling 1), and
    # Hang… gone from the toolbar while every wall is told to keep it down.
    assert ui.page.inner_text(".state-strip .kept-off").startswith("Kept off every wall since ")
    assert ui.page.locator(".state-strip dt:text-is('Walls')").count() == 0
    assert ui.page.locator(HANG).is_hidden()
    undo = ui.page.locator(".state-strip .kept-off button:text-is('Allow on walls again')")
    assert undo.get_attribute("class") == "action quiet"
    undo.click()
    ui.page.wait_for_selector(f"{HANG}:visible")

    assert api.get("/api/exclusions").json()["exclusions"] == []
    assert strip_value(ui, "Walls") == wall.name
    assert (
        ui.page.inner_text(".state-strip .strip-said")
        == "It goes back into the rotation of every wall hanging a theme that holds it."
    )
    assert ui.page.evaluate("() => document.activeElement.textContent") == "Hang…"


def test_an_archived_work_offers_no_hang(ui, service, hangable):
    work = hangable("Automat")
    service.archive_artwork(work.id)

    open_work(ui, work)

    # Ruling 8: an archived work cannot hang, so Restore takes the filled place.
    assert ui.page.locator(".state-strip button").count() == 0
    assert ui.page.locator(".state-strip dt:text-is('Walls')").count() == 0
    assert ui.page.locator("#view button:has-text('Hang')").count() == 0
    assert ui.page.locator(".page-toolbar button.action:not(.quiet)").all_inner_texts() == ["Restore"]
    ui.page.click(MORE)
    assert ui.page.locator(".toolbar-menu [role='menuitem']").all_inner_texts() == ["Match on Wikidata…"]


def test_restoring_puts_the_keyboard_on_hang(ui, service, hangable):
    work = hangable("Automat")
    service.archive_artwork(work.id)

    open_work(ui, work)
    ui.page.click(".page-toolbar button:text-is('Restore')")
    ui.page.click(".confirm-actions button:text-is('Restore')")
    ui.page.wait_for_selector(HANG)

    assert service.get_artwork(work.id).artwork.status == "accepted"
    assert ui.focused() == "Hang…"


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


# -- the wall label's layout -----------------------------------------------------

RECORD = ["Master image", "Where it can be obtained", "What has been rendered", "Mat colour"]


def _layout(ui):
    return ui.page.evaluate("""() => {
          const hero = document.querySelector('.work-head > .work-hero').getBoundingClientRect();
          const label = document.querySelector('.work-head > .work-label').getBoundingClientRect();
          const record = [...document.querySelectorAll('.work-record > .panel')];
          return {
            side_by_side: label.left >= hero.right && Math.abs(label.top - hero.top) < 2,
            stacked: label.top >= hero.bottom,
            headings: record.map((panel) => panel.querySelector('h2')?.textContent),
            boxed: record.some((panel) => getComputedStyle(panel).borderLeftStyle !== 'none'),
            ruled: record.every((panel) => getComputedStyle(panel).borderTopStyle === 'solid'),
          };
        }""")


@pytest.mark.parametrize("held", [True, False], ids=["held", "nothing-acquired"])
def test_the_picture_sits_beside_its_label_and_the_record_is_ruled_not_boxed(ui, hangable, service, held):
    """Wide: picture and label side by side, then every part of the record, in
    its order, set off by a rule rather than a box. Narrow: the label stacks
    under the picture. A work with nothing acquired keeps every section."""
    work = hangable("Automat") if held else service.add_artwork(title="Automat")
    ui.page.set_viewport_size({"width": 1280, "height": 900})
    # What this checks shows only in debug (ruling 1 of 2026-10-11).
    open_work(ui, work, debug=True)
    wide = _layout(ui)
    ui.page.set_viewport_size({"width": 800, "height": 900})
    narrow = _layout(ui)

    assert wide["side_by_side"]
    assert narrow["stacked"]
    assert [h for h in wide["headings"] if h in RECORD] == RECORD
    assert not wide["boxed"]
    assert wide["ruled"]


def test_the_description_is_set_in_the_label_serif_at_a_reading_measure(ui, service):
    work = service.add_artwork(title="Untitled", description="A description. " * 80)
    # Just under 60rem the label takes the main column's whole width, which is
    # a little wider than 68ch; on a wide screen the label's own column is
    # narrower than the cap, so a check there would pass without it.
    ui.page.set_viewport_size({"width": 959, "height": 900})
    open_work(ui, work)
    family, width, ch = ui.page.locator(".facts dd .described").evaluate("""(node) => {
          const probe = document.createElement('span');
          probe.textContent = '0';
          node.append(probe);
          const ch = probe.getBoundingClientRect().width;
          probe.remove();
          return [getComputedStyle(node).fontFamily, node.getBoundingClientRect().width, ch];
        }""")
    assert family.strip('"').startswith("Newsreader")
    assert width <= 68 * ch + 1
