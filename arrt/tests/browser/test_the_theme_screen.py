"""The four acts that are a theme's own, in a real browser against a real server.

A theme's name, the order its works reach the wall in, where it hangs, and
whether it exists — none of it expressible as JSON, so neither Python suite runs
a line of it. Works are added from Artworks and taken out here, on a selection
(ruling 9 of 2026-10-27; until then each row had its own *Remove* and the page
an *Add a work* picker). Since that ruling the page opens with its name, its
facts and a toolbar: *Hang…* (a dialog of walls), *Edit…* (name, description,
default, delete) and *Add works*; the order is a drag handle per row, which the
keyboard moves too; and every changed assertion below says so.

**Two of these are debts this screen carried into the chunk that owns it.** Its
membership control read "Remove", which promises a *work* is gone when it is
still catalogued and in every other theme; and its hang button changed a room
with no question asked, while flow 6 makes activation the one act that gets one.
Both are asserted here, because both were invisible to every suite that existed.

**The reorder tests are a pair and neither is redundant.** One drives the real
server and proves the new order survives a reload; the other hands the client an
answer no catalogue would produce and proves the table shows *that*. A screen
that repainted optimistically, or that threw the answer away and read the order
back, passes the first and fails the second — and the first alone is what "the
reorder works" usually means.
"""

import re

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from payloads import a_catalogue_work, a_theme_detail
from playwright.sync_api import expect

#: Titles chosen so curated order and alphabetical order agree at the start —
#: which is what lets a moved row be told from an unmoved one by reading.
POLLOCKS = ("Autumn Rhythm", "Blue Poles", "Convergence")


@pytest.fixture
def winter(services, service):
    """A theme holding three works in a known order, hanging nowhere."""
    theme = services.display.add_theme(name="Winter")
    for position, title in enumerate(POLLOCKS):
        work = service.add_artwork(title=title)
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
    return theme


def _expect_titles(ui, titles):
    """The member table's Title column reads `titles`, in the order it is painted."""
    expect(ui.page.locator("tbody tr td[data-label='Title']")).to_have_text(list(titles), use_inner_text=True)


def _painted(ui):
    """Wait until the member table has arrived, which the first paint does not carry."""
    ui.page.wait_for_selector("tbody tr")


def _index_painted(ui):
    """Wait until the index's cards have arrived."""
    ui.page.wait_for_selector("li.theme-card")


def _first_row_becomes(ui, title):
    """A wait that is false before the act and true only after it.

    The member table exists throughout a reorder, so waiting on the table, on a
    heading or on the panel waits for nothing and the assertions beneath read the
    order that was already there — which passes for exactly as long as the write
    happens to win a race nothing is holding open.
    """
    ui.page.wait_for_function(
        "(title) => { const cell = document.querySelector(\"tbody tr td[data-label='Title']\");"
        " return cell && cell.textContent === title; }",
        arg=title,
    )


def _row_becomes(ui, index, title):
    """`_first_row_becomes` for a move that leaves the first row where it was."""
    ui.page.wait_for_function(
        "([index, title]) => { const cells = document.querySelectorAll(\"tbody tr td[data-label='Title']\");"
        " return cells[index] && cells[index].textContent === title; }",
        arg=[index, title],
    )


def _press(ui, title, key):
    """Press a key on a work's drag handle, as a curator moving it by keyboard does."""
    ui.page.locator(f"button.drag-handle[aria-label='Move {title}']").press(key)


def _expect_count(ui, words):
    """The member count, the first of the page's facts, says `words` and the facts run on after it or end."""
    expect(ui.page.locator("#view .theme-facts")).to_have_text(re.compile(rf"^{re.escape(words)}(?: · |$)"), use_inner_text=True)


def _tick(ui, title):
    """A work's tick, shown while *Select* is on, by its accessible name."""
    return ui.page.locator(f"tbody input.select-box[aria-label='Select {title}']")


def _remove(ui, *titles):
    """Select these works and remove them from the theme, from the toolbar."""
    toggle = ui.page.locator("button.select-toggle")
    expect(toggle).to_have_text(re.compile(r"^(?:Select|Stop selecting)$"), use_inner_text=True)
    if toggle.inner_text() == "Select":  # one-shot: whether Select is already on, read once the toggle has said one or the other
        ui.page.click("button.select-toggle")
    for title in titles:
        _tick(ui, title).check()
    ui.page.click("button.selection-remove")


def _edit(ui):
    """Open the theme's *Edit…* and return the dialog."""
    ui.page.locator("#view .page-toolbar button", has_text="Edit…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.wait_for()
    return dialog


def _rename(ui, name):
    dialog = _edit(ui)
    dialog.get_by_label("Name", exact=True).fill(name)
    save = dialog.get_by_role("button", name="Save", exact=False)
    save.click()
    return save


def _delete(ui):
    """*Edit…*, then *Delete…*: the question opens with the dialog closed."""
    _edit(ui).get_by_role("button", name="Delete", exact=False).click()


def _hang(ui, *ticked):
    """Open *Hang…*, tick exactly these walls, and press *Hang*."""
    ui.page.locator("#view .page-toolbar button", has_text="Hang…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.wait_for()
    expect(dialog.locator("input[type='checkbox']").first).to_be_attached()
    for box in dialog.locator("input[type='checkbox']").all():
        label = f"label[for='{box.get_attribute('id')}']"  # one-shot: the box's id, to find the label that names its wall
        name = dialog.locator(label).inner_text()  # one-shot: the wall this box is for, which decides whether it is ticked
        box.set_checked(name in ticked)
    dialog.get_by_role("button", name="Hang", exact=True).click()


def _labels(ui, selector):
    """Every accessible name matching the selector, which Playwright has no one call for."""
    return sorted(ui.page.locator(selector).evaluate_all("els => els.map((el) => el.getAttribute('aria-label'))"))


def _confirm(ui, label):
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click(f"dialog.confirm .confirm-actions button:has-text('{label}')")


class TestReordering:
    def test_a_move_takes_effect_and_survives_a_reload(self, ui, winter):
        """The order is the theme's, so it has to be the catalogue's and not the page's.

        The reload is the half that matters: a table that reordered itself and
        told nobody looks identical until the curator comes back to it.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        _expect_titles(ui, list(POLLOCKS))

        _press(ui, "Autumn Rhythm", "ArrowDown")
        _first_row_becomes(ui, "Blue Poles")
        _expect_titles(ui, ["Blue Poles", "Autumn Rhythm", "Convergence"])

        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        _expect_titles(ui, ["Blue Poles", "Autumn Rhythm", "Convergence"])

    def test_a_work_added_through_artworks_can_then_be_moved(self, ui, winter, service):
        """The whole round trip through the doors a curator actually uses.

        Every other test here starts from a fixture that hands `add_to_theme` an
        explicit dense position, and an add from a browser posts an artwork and
        nothing else — so the shape those fixtures build is one no browser can
        produce. While an add left the work unplaced, the list this table renders
        and the list the service renumbered were different lists, and a move
        against a theme built this way either did nothing or sent the work the
        wrong way. Adding first is what makes this test able to see that. The add
        is the route Artworks' *Add to theme…* sends (`POST .../works/bulk`),
        since ruling 9 of 2026-10-27 took the picker off this page.
        """
        number_1 = service.add_artwork(title="Number 1")
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        ui.page.evaluate(
            "([theme, work]) => fetch(`/api/themes/${theme}/works/bulk`, {method: 'POST',"
            " headers: {'Content-Type': 'application/json'}, body: JSON.stringify({artwork_ids: [work]})})",
            [winter.id, number_1.id],
        )
        ui.open(f"#theme/{winter.id}")
        ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 4")
        _expect_titles(ui, [*POLLOCKS, "Number 1"])

        # Waiting on a row that is *not* already what it will become — the first
        # row never changes here, so waiting on it would wait for nothing and the
        # assertion below would read the order that was already on screen.
        _press(ui, "Number 1", "ArrowUp")
        _row_becomes(ui, 2, "Number 1")
        _expect_titles(ui, ["Autumn Rhythm", "Blue Poles", "Number 1", "Convergence"])

        # And back down, which is the direction that had never worked.
        _press(ui, "Number 1", "End")
        _row_becomes(ui, 2, "Convergence")
        _expect_titles(ui, ["Autumn Rhythm", "Blue Poles", "Convergence", "Number 1"])

    def test_the_table_is_painted_from_the_answer_and_not_from_the_move_it_sent(self, ui, winter):
        """`POST .../position` answers with the resulting order precisely so this is possible.

        The stub answers with a list no catalogue on this server holds, so three
        different implementations are told apart in one assertion: a client that
        swapped the rows itself would show the three Pollocks reordered, one that
        threw the answer away and read the order back would show them unmoved,
        and only one that repaints from the response shows what is below.

        Which is not a quibble about round trips. The service clamps and
        renumbers a position, so where a work actually lands is its answer to
        give — a screen that predicts it is right until the day it is not, and
        wrong silently.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        ui.serve(
            "**/api/themes/*/works/*/position",
            a_theme_detail([a_catalogue_work(artwork_id="only-1", title="Only what the answer said")]),
        )
        _press(ui, "Autumn Rhythm", "ArrowDown")
        _first_row_becomes(ui, "Only what the answer said")

        _expect_titles(ui, ["Only what the answer said"])

    def test_the_ends_of_the_order_offer_no_move_that_would_do_nothing(self, ui, winter):
        """A move to where a work already is sends nothing.

        *(Until 2026-10-14 the order was four buttons a row, and this test held
        that the first work's ↑ and the last's ↓ were disabled. #352 made the
        order one Position field a row, and ruling 9 of 2026-10-27 a drag handle
        a row; the same rule is held on the handle's keys: Up and Home on the
        first work, Down and End on the last, send nothing.)*
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        for title, key in (
            ("Autumn Rhythm", "ArrowUp"),
            ("Autumn Rhythm", "Home"),
            ("Convergence", "ArrowDown"),
            ("Convergence", "End"),
        ):
            _press(ui, title, key)
        ui.page.wait_for_timeout(300)  # sleep: nothing is sent, so only waiting shows it
        assert ui.requests_matching("/position") == []
        _expect_titles(ui, list(POLLOCKS))
        expect(ui.page.locator("input.theme-position")).to_have_count(0)


class TestTheMembershipControl:
    def test_it_names_the_theme_the_work_is_leaving_rather_than_saying_remove(self, ui, winter):
        """ "Remove" alone promises the work is gone, and it is not.

        `information-architecture.md` rules the bare word out for a work: there
        is no delete of one, the work stays catalogued and stays in every other
        theme, and a curator who believes removal is destructive hesitates over
        something cheap. Naming the theme is the fix that stays true — borrowing
        "Archive" would say something false about the catalogue instead. Since
        ruling 9 of 2026-10-27 it is one act on a selection, in the toolbar, and
        no row has a button of its own.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        _expect_titles(ui, POLLOCKS)
        expect(ui.page.locator("tbody button", has_text="Remove")).to_have_count(0)

        ui.page.click("button.select-toggle")
        _tick(ui, "Blue Poles").check()
        _tick(ui, "Convergence").check()

        remove = ui.page.locator("button.selection-remove")
        expect(remove).to_have_text("Remove 2 works from Winter", use_inner_text=True)
        # Nothing anywhere on the screen says the bare word.
        expect(ui.page.locator("button:text-is('Remove')")).to_have_count(0)

    def test_removing_a_work_leaves_the_rest_in_order(self, ui, winter):
        """And repaints from the answer, which is the same shape a move gets back."""
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _remove(ui, "Blue Poles")
        ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 2")

        _expect_titles(ui, ["Autumn Rhythm", "Convergence"])

    def test_the_theme_says_how_many_works_it_holds(self, ui, winter):
        """The count `information-architecture.md` makes this screen's secondary content.

        The numbered column is not it: reading the last row's number is
        arithmetic performed on a table, and a curator deciding whether a theme
        is worth hanging wants the size stated. It follows a removal because an
        add and a remove both answer with the new order, so a count painted once
        would be wrong on the second glance rather than absent.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        _expect_count(ui, "3 works")

        _remove(ui, "Blue Poles")
        ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 2")

        _expect_count(ui, "2 works")

    def test_one_work_is_not_one_works(self, ui, winter):
        """The count is read, so it is written the way it is read."""
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _remove(ui, "Blue Poles", "Convergence")
        ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 1")

        _expect_count(ui, "1 work")


class TestTheToolbarHasTheListsLayout:
    """A theme's page draws its toolbar as every list does: its own acts on the
    left, the acts on a selection after them, *Select* last on the right.

    It handed the toolbar *Select* and its bar as two more acts until it moved
    to `toolbar({ selection })`, which stood *Select* among the acts on the left
    and left the page's own acts in the sticky toolbar of a phone."""

    @staticmethod
    def _sides(ui):
        bar = ui.page.locator("#view .page-toolbar")
        return bar.locator(".page-toolbar-actions"), bar.locator(".page-toolbar-controls")

    def test_select_is_last_on_the_right_and_the_acts_it_brings_follow_the_pages_own(self, ui, winter):
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        left, right = self._sides(ui)

        expect(left.locator(":scope > :visible")).to_have_text(["Hang…", "Edit…", "Add works"])
        expect(right.locator(":scope > :visible")).to_have_text(["Select"])
        expect(right.locator("button.select-toggle")).to_have_attribute("data-control", "select")
        expect(left.locator("button.select-toggle")).to_have_count(0)
        expect(ui.page.locator("#view .page-toolbar")).to_have_css("position", "static")

        ui.page.click("#view button.select-toggle")

        expect(right.locator(":scope > :visible")).to_have_text(["Stop selecting"])
        expect(left.locator(":scope > .selection")).to_be_visible()
        expect(left.locator(":scope > :last-child")).to_have_class("selection")
        expect(left.locator(":scope > .selection button.selection-remove")).to_be_visible()
        expect(ui.page.locator("#view .page-toolbar")).to_have_css("position", "sticky")

        ui.page.click("#view button.select-toggle")

        expect(right.locator(":scope > :visible")).to_have_text(["Select"])
        expect(ui.page.locator("#view .page-toolbar")).to_have_css("position", "static")

    @pytest.mark.parametrize(("width", "hidden_while_selecting"), [(390, True), (1280, False)])
    def test_on_a_phone_the_pages_own_acts_step_aside_and_stop_selecting_stays(self, ui, winter, width, hidden_while_selecting):
        ui.page.set_viewport_size({"width": width, "height": 800})
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        left, right = self._sides(ui)
        own = left.locator(".page-act")
        # Every act the page itself offers is marked, so none is left in the
        # sticky toolbar of a phone: Hang…, Edit… and Add works.
        expect(own).to_have_count(3)

        ui.page.click("#view button.select-toggle")

        # The toolbar in selecting mode first: only then is an act's being hidden
        # the toolbar's doing and not a toolbar not yet drawn.
        expect(right.locator(":scope > :visible")).to_have_text(["Stop selecting"])
        expect(left.locator(".selection button.select-all")).to_be_visible()
        for act in own.all():
            if hidden_while_selecting:
                expect(act).to_be_hidden()
            else:
                expect(act).to_be_visible()

        ui.page.click("#view button.select-toggle")

        for act in own.all():
            expect(act).to_be_visible()


class TestRenaming:
    def test_the_controls_that_act_on_a_theme_say_which_theme(self, ui, winter, services):
        """Three themes, three identical panels, and one of these buttons destroys something.

        `accessibility-spec.md` asks a control to name what it acts on, and the
        membership table in this same panel already does. These three did not:
        somebody moving through the form controls one at a time heard "Name, edit
        text", "Rename", "Delete" once per theme with nothing distinguishing
        them, and had to reconstruct which panel they were in from reading order.
        Two themes rather than one, because with one theme every naming scheme
        including no scheme at all announces unambiguously.

        These controls were on every panel of the index and are now on each
        theme's own page, so the claim is checked on two pages: each names its
        own theme and not the other.
        """
        late = services.display.add_theme(name="Late night")
        for theme in (winter, late):
            ui.open(f"#theme/{theme.id}")
            ui.page.wait_for_selector(f"#view h1:has-text('{theme.name}')")
            # The toolbar's acts, and in *Edit…* the ones that change or destroy
            # it (ruling 9 of 2026-10-27 moved them there from beside the name).
            assert _labels(ui, "#view .page-toolbar button[aria-label^='Hang ']") == [f"Hang {theme.name}…"]
            assert _labels(ui, "#view .page-toolbar button[aria-label^='Edit ']") == [f"Edit {theme.name}…"]
            _edit(ui)
            assert _labels(ui, "dialog button[aria-label^='Save ']") == [f"Save {theme.name}"]
            assert _labels(ui, "dialog button[aria-label^='Delete ']") == [f"Delete {theme.name}…"]
            ui.page.keyboard.press("Escape")

    def test_the_accessible_names_follow_the_new_name_too(self, ui, winter):
        """A control announcing a theme by its old name is worse than one naming none.

        The visible words on these three never change, so nothing on screen shows
        this going stale — which is exactly why it would.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _rename(ui, "Late night")
        ui.page.wait_for_selector("h1:has-text('Late night')")

        expect(ui.page.locator("button[aria-label='Edit Late night…']")).to_have_count(1)
        expect(ui.page.locator("button[aria-label='Edit Winter…']")).to_have_count(0)
        _edit(ui)
        expect(ui.page.locator("dialog button[aria-label='Delete Late night…']")).to_have_count(1)

    def test_the_heading_and_the_membership_controls_both_follow_the_new_name(self, ui, winter):
        """Two places name the theme, and a rename that moved one is worse than neither.

        A toolbar still offering "Remove from Winter" under a heading reading
        "Late night" leaves a curator working out which of the two to believe.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _rename(ui, "Late night")
        ui.page.wait_for_selector("h1:has-text('Late night')")
        ui.page.click("button.select-toggle")

        expect(ui.page.locator("button.selection-remove")).to_have_text("Remove from Late night", use_inner_text=True)
        expect(ui.page.locator("button", has_text="Remove from Winter")).to_have_count(0)
        expect(ui.page).to_have_title(re.compile(r"^Late night"))

    def test_the_field_shows_the_name_the_catalogue_stored_rather_than_the_one_typed(self, ui, winter):
        """The service trims, so the two differ — and the field is where it shows.

        A screen painting its own input would leave the field reading " Late
        night " beside a heading and a listing that both say "Late night", and
        the next rename would send the untrimmed string back.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _rename(ui, "  Late night  ")
        ui.page.wait_for_selector("h1:has-text('Late night')")

        expect(_edit(ui).get_by_label("Name", exact=True)).to_have_value("Late night")

    def test_a_name_with_nothing_in_it_is_refused_in_the_servers_words(self, ui, winter):
        """The rule lives in the service, and its refusal reaches the curator unchanged."""
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        save = _rename(ui, "   ")

        assert ui.said_beside(save) == "Couldn't save Winter: name cannot be empty. Nothing was changed."
        expect(ui.page.locator("h1", has_text="Winter")).to_have_count(1)


class TestHanging:
    def test_the_room_is_not_changed_until_the_question_has_been_answered(self, ui, winter, services, a_player_shows):
        """Flow 6's one confirmation, on the screen that had none at all.

        The dialog names the theme *and* the wall, even in a house with one wall:
        a question that reads correctly today only because there is one possible
        target is the last place a mistake could have been caught.

        The wall is given a Player: since 2026-11-19 the question promises
        "Everyone in the house sees" only of a wall a Player shows (chunk 06 of
        `build-plan-audit-wave-1.md`, audit 6 finding 19), and the wall with no
        Player is `test_setting_up_a_wall.py`'s case. The Player has its token
        and has reported: one with no token shows nothing yet, the next test.
        """
        wall = services.display.survey_walls()[0].wall
        a_player_shows(wall.id)
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _hang(ui, wall.name)
        ui.page.wait_for_selector("dialog.confirm[open]")

        expect(ui.page.locator("dialog.confirm .confirm-title").first).to_have_text(
            f"Hang Winter on {wall.name}?", use_inner_text=True
        )
        expect(ui.page.locator("dialog.confirm .confirm-consequence").first).to_contain_text(
            f"Everyone in the house sees {wall.name} change.", use_inner_text=True
        )
        assert services.display.hanging_on(wall.id) is None

    def test_a_wall_whose_player_has_no_token_is_said_to_wait_in_the_servers_words(self, ui, winter, services):
        """Chunk 66, through a theme's *Hang…*: nothing shows the wall until its Player is set up, so nobody sees it change."""
        wall = services.display.survey_walls()[0].wall
        hall = services.clients.add_client(name="Hall Pi")
        services.clients.assign_wall(wall.id, client_id=hall.id, output="hdmi-a-1")
        words = services.health.observe_walls().waiting[wall.id].words
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _hang(ui, wall.name)
        consequence = ui.page.locator("dialog.confirm[open] .confirm-consequence").first
        expect(consequence).to_contain_text(f"{words}.", use_inner_text=True)
        assert words == f"{wall.name} waits for Hall Pi, which has no token yet"
        expect(consequence).not_to_contain_text("Everyone in the house", use_inner_text=True)
        expect(consequence).not_to_contain_text("No Player shows", use_inner_text=True)

    def test_the_consequence_is_the_builds_own_summary_rather_than_a_guess(self, ui, winter, services):
        """Evaluated with `GET /api/manifest`, which answers without writing.

        The works here hold no images, so the honest answer is that none of them
        would reach the wall — which is exactly what a curator wants to be told
        before pressing the button rather than after. A sentence composed on the
        client could only have said "3 works".
        """
        wall = services.display.survey_walls()[0].wall
        preview = services.display.build_manifest(wall.id, winter.id)

        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        _hang(ui, wall.name)
        ui.page.wait_for_selector("dialog.confirm[open]")

        # One wall's question, worded as Walls' is (`core/hanging.js`): the title
        # names the wall, and the build's own summary leads the consequence.
        expect(ui.page.locator("dialog.confirm .confirm-consequence").first).to_have_text(
            re.compile("^" + re.escape(preview.summarise())), use_inner_text=True
        )

    def test_declining_leaves_the_wall_alone(self, ui, winter, services):
        """Escape is a no, and a no here means nothing was published."""
        wall = services.display.survey_walls()[0].wall
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _hang(ui, wall.name)
        ui.page.wait_for_selector("dialog.confirm[open]")
        ui.page.keyboard.press("Escape")
        ui.page.wait_for_selector("dialog.confirm", state="detached")

        assert services.display.hanging_on(wall.id) is None
        # Still offered, so declining left the screen able to try again.
        expect(ui.page.locator("#view .page-toolbar button", has_text="Hang…")).to_be_enabled()

    def test_confirming_hangs_it_and_the_facts_say_where(self, ui, winter, services):
        """The page stays, and its facts say where the theme now hangs, read again
        from the server; the wall the act changed is a link there. *(Until ruling
        9 of 2026-10-27 it left for Walls, since hanging was a button per wall
        and the page did not say where a theme hung.)*
        """
        wall = services.display.survey_walls()[0].wall
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _hang(ui, wall.name)
        _confirm(ui, "Hang")
        ui.page.wait_for_selector(f"#view .theme-facts a:text-is('{wall.name}')")

        assert services.display.hanging_on(wall.id).id == winter.id
        assert ui.page.evaluate("() => window.location.hash") == f"#theme/{winter.id}"


class TestDeleting:
    def test_the_question_says_the_works_survive_and_the_grouping_does_not(self, ui, winter):
        """Which is the fact a curator needs and cannot infer from the word "Delete".

        One who believes they are about to lose three paintings will hesitate
        over something cheap; one who does not know the grouping is gone for good
        will do it without reading.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _delete(ui)
        ui.page.wait_for_selector("dialog.confirm[open]")

        expect(ui.page.locator("dialog.confirm .confirm-title").first).to_have_text("Delete Winter?", use_inner_text=True)
        expect(ui.page.locator("dialog.confirm .confirm-consequence").first).to_have_text(
            "The 3 works it holds stay in the Library. Only the grouping goes, and it cannot be brought back.",
            use_inner_text=True,
        )

    def test_declining_leaves_the_theme_where_it_was(self, ui, winter):
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _delete(ui)
        ui.page.wait_for_selector("dialog.confirm[open]")
        ui.page.keyboard.press("Escape")
        ui.page.wait_for_selector("dialog.confirm", state="detached")

        expect(ui.page.locator("h1", has_text="Winter")).to_have_count(1)

    def test_confirming_lands_on_the_index_with_the_theme_gone(self, ui, winter, services):
        """A deleted theme's page is an address naming nothing, so the delete goes to the index.

        Rewritten from *removes the panel by repainting from what remains*: the
        delete lived on the index, beside every other theme, and repainted the
        list from the answer naming the themes left. It now lives on the theme's
        own page, which the answer cannot repaint, so it goes to the index; with
        one theme that index is empty.
        """
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _delete(ui)
        _confirm(ui, "Delete")
        ui.page.wait_for_selector("text=No themes yet.")

        expect(ui.page.locator("li.theme-card")).to_have_count(0)
        assert [theme.name for theme in services.display.list_themes()] == []

    def test_the_themes_that_are_left_are_the_ones_the_index_shows(self, ui, winter, services):
        """The half of landing on the index that can be wrong: which themes are there.

        With one theme, "the index after the delete" and "an index of nothing"
        are the identical empty screen, so the test above passes against an index
        that lost every theme. Two themes is the smallest state that tells them
        apart: the one that survives has to be there, and the one deleted not.
        """
        late = services.display.add_theme(name="Late night")
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _delete(ui)
        _confirm(ui, "Delete")
        ui.page.wait_for_selector("#view h1:has-text('Themes')")
        ui.page.wait_for_selector("li.theme-card")

        expect(ui.page.locator("li.theme-card h2")).to_have_text(["Late night"], use_inner_text=True)
        expect(ui.page.locator(f"li.theme-card[data-theme='{late.id}']")).to_have_count(1)
        expect(ui.page.locator("text=No themes yet.")).to_have_count(0)

    def test_a_theme_hanging_in_two_rooms_refuses_and_says_what_to_do_about_it(self, ui, winter, services):
        """The acceptance criterion, met where a curator actually meets it.

        Two walls rather than one, because that is the case a single wall cannot
        tell apart: a message naming only the first room, or a guard counting
        themes rather than assignments, reads as correct against one wall and
        loses a room against two. The sentence is the server's own — nothing on
        this screen predicts the refusal from what it knows about hanging, which
        would be a second copy of the rule and would be wrong about a theme hung
        from another tab a moment ago.
        """
        the_wall = services.display.survey_walls()[0].wall
        study = services.display.add_wall(name="The study")
        services.display.activate_theme(winter.id, wall_id=the_wall.id)
        services.display.activate_theme(winter.id, wall_id=study.id)

        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        _delete(ui)
        _confirm(ui, "Delete")

        # Said beside the page's *Edit…*, which opened the act: the dialog that
        # held *Delete…* closed as the question was asked.
        edit = ui.page.locator("#view .page-toolbar button", has_text="Edit…")
        assert ui.said_beside(edit) == (
            "Couldn't delete Winter: Theme 'Winter' is hanging on 'The study', 'The wall'. Hang another theme "
            "there first, or take this one down, so that what those walls show next is a choice rather than "
            "whatever was on them before. Nothing was changed."
        )
        # Refused, not partly done: the theme is still there and still hanging in
        # both rooms.
        expect(ui.page.locator("h1", has_text="Winter")).to_have_count(1)
        assert [wall.name for wall in services.display.walls_hanging(winter.id)] == ["The study", "The wall"]


class TestOneThemeHasItsOwnAddress:
    """`#theme/<id>` — the address a theme had no way to be given (#133).

    `information-architecture.md` § Navigation Structure requires that every
    screen and every consequential state be addressable, and one theme is one:
    it is what a wall's theme control is about, what a curator bookmarks, and
    what an agent has to be able to link to. The built screen was a themes
    *index* and offered no such address, which the rule had no enforcement to
    catch.

    **Two themes in every test here, not one.** With a single theme, "opened the
    theme I asked for" and "opened the only theme there is" produce the same
    page, and the first is what these are about.
    """

    @pytest.fixture
    def two_themes(self, ui, winter, services):
        """Winter, holding three works, beside a theme that must not appear."""
        services.display.add_theme(name="Late night")
        return winter

    def test_an_addressed_theme_shows_that_theme_and_no_other(self, ui, two_themes):
        ui.open(f"#theme/{two_themes.id}")
        _painted(ui)

        expect(ui.page.locator("h1", has_text="Winter")).to_have_count(1)
        _expect_titles(ui, list(POLLOCKS))
        expect(ui.page.locator("text=Late night")).to_have_count(0)

    def test_the_index_still_shows_every_theme(self, ui, two_themes):
        """The paired negative: an addressable detail must not cost the index.

        Creating a theme and managing the set of them have no other home — the
        rail in Collection is a filter over the grid — so the index surviving is
        the whole reason the id is optional rather than required.
        """
        ui.open("#theme")
        _index_painted(ui)

        expect(ui.page.locator("li.theme-card h2", has_text="Winter")).to_have_count(1)
        expect(ui.page.locator("li.theme-card h2", has_text="Late night")).to_have_count(1)
        # Creating is the index's one act, behind *New theme…* (ruling 9 of 2026-10-27).
        expect(ui.page.get_by_role("button", name="New theme…")).to_have_count(1)

    def test_every_act_is_offered_from_the_addressed_view(self, ui, two_themes):
        """Every act on a theme is on its own page, which is now the only place they are.

        Asserted as the controls rather than by performing each: the acts
        themselves are exercised in the classes above, and what a route into
        the page can lose is a control, not a behaviour.
        """
        ui.open(f"#theme/{two_themes.id}")
        _painted(ui)

        # In the toolbar since ruling 9 of 2026-10-27, and renaming and deleting
        # in its *Edit…*; the order on a handle per row.
        toolbar = ui.page.locator("#view .page-toolbar")
        expect(toolbar.locator("button[aria-label='Hang Winter…']")).to_have_count(1)
        expect(toolbar.locator("button[aria-label='Edit Winter…']")).to_have_count(1)
        expect(toolbar.get_by_role("link", name="Add works")).to_have_attribute("href", "#collection")
        expect(ui.page.locator("button.drag-handle[aria-label='Move Autumn Rhythm']")).to_have_count(1)
        dialog = _edit(ui)
        expect(dialog.locator("button[aria-label='Save Winter']")).to_have_count(1)
        expect(dialog.locator("button[aria-label='Delete Winter…']")).to_have_count(1)

    def test_reordering_works_from_the_addressed_view(self, ui, two_themes):
        """One act driven end to end, because "the control is there" is not "it works".

        Reorder is the one chosen: it is the act the IA gives this screen alone,
        it repaints from the server's answer rather than from the move it sent,
        and it is the one whose subject is the theme rather than a work.
        """
        ui.open(f"#theme/{two_themes.id}")
        _painted(ui)

        _press(ui, "Autumn Rhythm", "ArrowDown")
        _first_row_becomes(ui, "Blue Poles")

        _expect_titles(ui, ["Blue Poles", "Autumn Rhythm", "Convergence"])

    def test_deleting_the_addressed_theme_lands_on_the_index(self, ui, two_themes):
        """The screen cannot stay pointed at what it just destroyed.

        So this path navigates, and it navigates to the list where the survivors
        are rather than leaving a curator on an address that now resolves to
        nothing.
        """
        ui.open(f"#theme/{two_themes.id}")
        _painted(ui)

        _delete(ui)
        _confirm(ui, "Delete")
        ui.page.wait_for_selector("li.theme-card h2:has-text('Late night')")

        expect(ui.page.locator("h1", has_text="Themes")).to_have_count(1)
        expect(ui.page.locator("text=Winter")).to_have_count(0)

    def test_an_address_whose_theme_is_gone_says_so_rather_than_going_home(self, ui, two_themes):
        """A bookmark outlives the theme it names, and that is an ordinary state.

        Falling back to the product's home would put the curator somewhere with
        no account of why — which is the failure the path fallback was added to
        stop for `/discover`, arriving here by a different route.
        """
        ui.open("#theme/theme-that-never-existed")
        ui.page.wait_for_selector("h1:has-text('That theme is not here')")

        expect(ui.view).to_contain_text("most likely deleted", use_inner_text=True)
        ui.page.click("#view .not-found a:text-is('Themes')")
        ui.page.wait_for_selector("li.theme-card h2:has-text('Winter')")

    def test_the_address_survives_a_reload(self, ui, two_themes):
        """Bookmarkable is the requirement, and it is not the same as reachable.

        A screen that only ever arrives through a click can be produced by state
        the address does not carry, which is exactly the shape the navigation
        rule forbids.
        """
        ui.open(f"#theme/{two_themes.id}")
        _painted(ui)

        ui.page.reload()
        _painted(ui)

        expect(ui.page.locator("h1", has_text="Winter")).to_have_count(1)
        _expect_titles(ui, list(POLLOCKS))


class TestTheDefaultTheme:
    """The theme new works join: marked in glyph, word and colour, and movable from its page.

    The mark is on the default's card in the index and on its own page; the act
    that moves it is on each other theme's page.
    """

    @pytest.fixture
    def all_works(self, services, winter):
        theme = services.display.add_theme(name="All works")
        services.display.make_default(theme.id)
        return theme

    @staticmethod
    def _card(ui, theme):
        return ui.page.locator(f"li.theme-card[data-theme='{theme.id}']")

    @staticmethod
    def _open(ui, theme):
        ui.open(f"#theme/{theme.id}")
        ui.page.wait_for_selector(f"#view h1:has-text('{theme.name}')")

    @staticmethod
    def _expect_edit_offers_no_default(ui):
        """*Edit…* opens with its own acts drawn and none of them *Make this the default*."""
        dialog = _edit(ui)
        expect(dialog.get_by_role("button", name="Delete", exact=False)).to_be_visible()
        expect(dialog.locator("button", has_text="the default")).to_have_count(0)

    def test_the_default_says_so_in_words_and_the_others_offer_to_become_it(self, ui, all_works, winter):
        ui.open("#theme")
        _index_painted(ui)

        badge = self._card(ui, all_works).locator(".badge-default")
        expect(badge).to_have_text(re.compile(r"default\s*$"), use_inner_text=True)
        # The star is decoration beside the word, not a second announcement of it.
        expect(badge.locator(".glyph")).to_have_attribute("aria-hidden", "true")
        expect(self._card(ui, winter).locator(".badge-default")).to_have_count(0)

        # The default's own page says so too, in its facts (ruling 9 of
        # 2026-10-27: a badge beside the name until then), and its *Edit…*
        # offers no act to become what it is.
        self._open(ui, all_works)
        expect(ui.page.locator("#view .theme-facts")).to_contain_text("Default: works you accept join it", use_inner_text=True)
        self._expect_edit_offers_no_default(ui)
        ui.page.keyboard.press("Escape")
        self._open(ui, winter)
        _expect_count(ui, "3 works")
        expect(ui.page.locator("#view .theme-facts")).not_to_contain_text("Default", use_inner_text=True)
        _edit(ui)
        assert _labels(ui, "dialog button:has-text('Make this the default')") == ["Make Winter the default"]

    def test_making_another_the_default_moves_the_mark(self, ui, services, all_works, winter):
        self._open(ui, winter)

        _edit(ui).locator("button[aria-label='Make Winter the default']").click()
        ui.page.wait_for_selector("#view .theme-facts:has-text('Default')")

        self._expect_edit_offers_no_default(ui)
        assert services.display.default_theme().id == winter.id
        # And it moved rather than being added: the index marks one card.
        ui.open("#theme")
        _index_painted(ui)
        expect(self._card(ui, winter).locator(".badge-default")).to_have_count(1)
        expect(self._card(ui, all_works).locator(".badge-default")).to_have_count(0)

    def test_with_no_default_the_screen_says_where_acceptances_go(self, ui, winter):
        """On the index a quiet line after the cards (the exception rule of 2026-10-27:
        it does not stop the index's job), and the facts line says it too."""
        ui.open("#theme")
        _index_painted(ui)

        line = ui.page.locator("#view p.no-default")
        expect(line).to_have_count(1)
        expect(line).to_contain_text("No theme is the default", use_inner_text=True)
        expect(line).to_have_class(re.compile(r"(^|\s)muted(\s|$)"))
        # Said once: the facts line names a default only when there is one.
        expect(ui.page.locator("#view .page-facts")).not_to_contain_text("default", use_inner_text=True)
        # After the cards, not above them.
        assert line.evaluate("(node) => !!node.previousElementSibling.matches('ul.theme-cards')")

    def test_one_themes_own_page_says_it_too(self, ui, winter):
        """The note is about where acceptances go, not about the index, so both paths carry it,
        quiet on each since ruling 1 of 2026-10-27 (it does not stop either page's job)."""
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        line = ui.page.locator("#view p.no-default")
        expect(line).to_have_count(1)
        expect(line).to_contain_text("No theme is the default", use_inner_text=True)
        expect(line).to_have_class(re.compile(r"(^|\s)muted(\s|$)"))

    def test_only_the_default_says_what_joins_it(self, ui, all_works, winter):
        # In the facts since ruling 9 of 2026-10-27 (a line under the name until then).
        joins = "works you accept join it"
        self._open(ui, all_works)
        expect(ui.page.locator("#view .theme-facts")).to_contain_text(joins, use_inner_text=True)
        self._open(ui, winter)
        _expect_count(ui, "3 works")
        expect(ui.page.locator("#view .theme-facts")).not_to_contain_text(joins, use_inner_text=True)

    def test_the_note_is_absent_once_a_theme_is_the_default(self, ui, all_works):
        ui.open("#theme")
        _index_painted(ui)

        expect(ui.page.locator("#view .page-facts")).to_have_text(
            re.compile(r"All works is the default\s*$"), use_inner_text=True
        )
        expect(ui.page.locator("#view p.no-default")).to_have_count(0)

    def test_deleting_the_default_shows_the_servers_reason(self, ui, all_works):
        self._open(ui, all_works)

        _delete(ui)
        _confirm(ui, "Delete")

        # Beside the page's *Edit…*, whose dialog held *Delete…* (ruling 9 of 2026-10-27).
        edit = ui.page.locator("#view .page-toolbar button", has_text="Edit…")
        assert "Make another theme the default first" in ui.said_beside(edit)


class TestEditingTheDescription:
    """A theme's description, edited in its *Edit…* with its name (ruling 9 of
    2026-10-27), each read back from the server.

    *Save* sends the name and the description together, so a rename keeps the
    description only because the box holds it: the second test is the one that
    fails if the box stopped being filled from the theme.
    """

    def _save(self, ui, *, name=None, description=None):
        dialog = _edit(ui)
        if name is not None:
            dialog.get_by_label("Name", exact=True).fill(name)
        if description is not None:
            dialog.get_by_label("Description", exact=True).fill(description)
        dialog.get_by_role("button", name="Save", exact=False).click()
        dialog.wait_for(state="detached")

    def test_a_description_set_in_edit_is_stored_and_shown(self, ui, winter, services):
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        self._save(ui, description="Snow and ice")
        ui.page.wait_for_selector("#view .theme-description:text-is('Snow and ice')")

        assert services.display.get_theme(winter.id).description == "Snow and ice"

    def test_renaming_keeps_the_description_the_theme_has(self, ui, winter, services):
        services.display.update_theme(winter.id, description="After hours")
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        expect(_edit(ui).get_by_label("Description", exact=True)).to_have_value("After hours")
        ui.page.keyboard.press("Escape")

        self._save(ui, name="Late night")
        ui.page.wait_for_selector("#view h1:has-text('Late night')")

        stored = services.display.get_theme(winter.id)
        assert (stored.name, stored.description) == ("Late night", "After hours")

    def test_a_description_cleared_to_spaces_is_no_description(self, ui, winter, services):
        services.display.update_theme(winter.id, description="After hours")
        ui.open(f"#theme/{winter.id}")
        _painted(ui)

        self._save(ui, description="   ")
        ui.page.wait_for_function("() => !document.querySelector('#view .theme-description')")

        assert services.display.get_theme(winter.id).description is None

    @pytest.mark.parametrize("leave", ["Close", "Escape"])
    def test_leaving_edit_changes_nothing(self, ui, winter, services, leave):
        services.display.update_theme(winter.id, description="After hours")
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        dialog = _edit(ui)
        dialog.get_by_label("Name", exact=True).fill("Late night")
        dialog.get_by_label("Description", exact=True).fill("Something else")
        if leave == "Escape":
            ui.page.keyboard.press("Escape")
        else:
            dialog.get_by_role("button", name="Close").click()
        dialog.wait_for(state="detached")

        stored = services.display.get_theme(winter.id)
        assert (stored.name, stored.description) == ("Winter", "After hours")
        expect(ui.page.locator("#view h1")).to_have_text("Winter", use_inner_text=True)

    @pytest.mark.parametrize("leave", ["Cancel", "Escape"])
    def test_declining_delete_keeps_the_theme_in_the_catalogue(self, ui, winter, services, leave):
        ui.open(f"#theme/{winter.id}")
        _painted(ui)
        _delete(ui)
        ui.page.wait_for_selector("dialog.confirm[open]")
        if leave == "Escape":
            ui.page.keyboard.press("Escape")
        else:
            ui.page.click("dialog.confirm .confirm-actions button:has-text('Cancel')")
        ui.page.wait_for_selector("dialog.confirm", state="detached")

        assert winter.id in [theme.id for theme in services.display.list_themes()]
        _expect_titles(ui, list(POLLOCKS))
