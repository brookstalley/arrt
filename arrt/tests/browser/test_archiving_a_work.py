"""Archiving a work, and putting it back, in a real browser.

**The label is the deliverable.** `information-architecture.md` rules that
"Remove" is the wrong word for a work — the record survives, every theme holding
it survives, and restoration is one click away — so the control reads *Archive*
with *Restore* as its undo. That rule is only true if it is true on the page, and
no Python suite reads a line of the page.

**The confirmation is the other half, and it is the half that reaches the room.**
Archiving a work that a wall is showing takes a picture off it, and
`architecture.md` calls silence about that "precisely this product's
characteristic failure". So the question names the walls — and it names them by
building each wall's manifest, which is the only thing that can tell a picture
that is *hanging* from one that is merely in a hung theme and excluded from it.

The asymmetry is the point of most of this file: a sentence when there is a
consequence, no sentence at all when there is not. A confirmation that always
said something about walls would be indistinguishable from one that had never
looked.
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

from playwright.sync_api import expect


@pytest.fixture
def hang(services):
    """Put works in a theme and hang it on a wall, which is what "showing" means.

    Named for the act rather than for the fixtures it composes, because every
    test here is about the difference between a work that a room is showing and
    one that it is not.
    """

    def _hang(*works, wall_name=None, theme_name="Late night"):
        wall = services.display.add_wall(name=wall_name) if wall_name else services.display.survey_walls()[0].wall
        theme = services.display.add_theme(name=theme_name)
        for position, work in enumerate(works):
            services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        services.display.activate_theme(theme.id, wall_id=wall.id)
        return wall

    return _hang


def open_work(ui, work, *, debug=False):
    ui.open(f"{'?debug' if debug else ''}#work/{work.id}")
    ui.page.wait_for_selector("#view h1")


MORE = ".page-toolbar .action-menu-trigger"


def ask(ui, label):
    """Take the act and wait for the platform to make its question modal.

    Archive… is behind ⋯ and Restore is the toolbar's filled act on an archived
    work (ruling 8 of 2026-10-27)."""
    if label == "Archive":
        ui.page.click(MORE)
        ui.page.click(".toolbar-menu [role='menuitem']:text-is('Archive…')")
    else:
        ui.page.click(f".page-toolbar button:text-is('{label}')")
    ui.page.wait_for_selector("dialog.confirm[open]")


# -- the label -----------------------------------------------------------------


def test_the_act_reads_archive_and_is_behind_more(ui, service):
    """Behind ⋯: not `danger`, and not the filled primary either.

    Archive's whole point is that Restore exists. Dressing a cheap reversible act
    as a destructive one produces exactly the hesitation the IA argues the word
    "Remove" produces — and teaches the operator that this dialog means danger,
    which is the wrong lesson on the day one of them is not. And it is not the
    page's primary: a wall card opens this page, and the loudest button in reach
    of a curator who wanted one picture off one wall must not take it out of the
    whole library (`ux-review-2026-10.md` finding 3). Ruling 8 of 2026-10-27
    moves it from a quiet button under the facts to ⋯, with "…" because it asks.
    """
    work = service.add_artwork(title="Chop Suey")
    open_work(ui, work)

    # The toolbar is drawn (its ⋯ is there), so a missing button is missing from a drawn page.
    expect(ui.page.locator(MORE)).to_be_visible()
    expect(ui.page.locator("#view button", has_text="Archive")).to_have_count(0)
    ui.page.click(MORE)
    item = ui.page.locator(".toolbar-menu [role='menuitem']", has_text="Archive")
    expect(item).to_have_count(1)
    expect(item).to_have_text("Archive…", use_inner_text=True)
    expect(item).not_to_have_attribute("class", re.compile("danger"))


@pytest.mark.parametrize("word", ["Remove", "Delete"])
def test_no_control_on_this_screen_offers_to_get_rid_of_the_work(ui, service, word):
    """The acceptance criterion, asserted where a curator would meet a violation."""
    work = service.add_artwork(title="Chop Suey")
    open_work(ui, work)

    expect(ui.page.locator(MORE)).to_be_visible()
    expect(ui.page.locator("#view button", has_text=word)).to_have_count(0)
    ui.page.click(MORE)
    # The menu is open and holds the act this screen does offer, so a missing
    # word is missing from a drawn menu.
    expect(ui.page.locator(".toolbar-menu [role='menuitem']", has_text="Archive")).to_have_count(1)
    expect(ui.page.locator(".toolbar-menu [role='menuitem']", has_text=word)).to_have_count(0)


def test_an_archived_work_offers_the_way_back(ui, service):
    """Restoration has to be discoverable, and this is the only place it is offered.

    A work whose only route back was an agent's tool call would be archived in
    practice as well as in status — the curator who archived it by mistake has
    nothing to press.
    """
    work = service.add_artwork(title="Chop Suey")
    service.archive_artwork(work.id)

    open_work(ui, work)

    control = ui.page.locator("#view button", has_text="Restore")
    expect(control).to_have_count(1)
    expect(control).to_have_text("Restore", use_inner_text=True)
    expect(control).to_have_attribute("class", "action")


# -- the wall consequence ------------------------------------------------------


def test_the_confirmation_names_the_wall_that_is_showing_the_work(ui, ready_work, hang):
    """Which room loses the picture, evaluated from that wall's own manifest."""
    work = ready_work(title="Nighthawks")
    wall = hang(work)

    open_work(ui, work)
    ask(ui, "Archive")

    expect(ui.page.locator(".confirm-title")).to_have_text("Archive Nighthawks?", use_inner_text=True)
    expect(ui.page.locator(".confirm-consequence")).to_contain_text(wall.name, use_inner_text=True)


def test_the_confirmation_says_the_room_loses_it_now(ui, ready_work, hang):
    """When the room loses the picture: now, as the archive lands.

    Programming takes an archived work off every published manifest that
    carries it as soon as the Library announces the archive (pinned by
    `tests/unit/test_reconciliation.py`). This confirmation once said the room
    would lose it "the next time its theme is hung" and offered re-hanging as
    the way to make it catch up, which promised a delay and a remedy that no
    longer exist.
    """
    work = ready_work(title="Nighthawks")
    hang(work)

    open_work(ui, work)
    ask(ui, "Archive")

    consequence = ui.page.locator(".confirm-consequence")
    expect(consequence).to_contain_text("loses it now", use_inner_text=True)
    expect(consequence).not_to_contain_text("next time", use_inner_text=True)
    expect(consequence).not_to_contain_text("Re-hanging", use_inner_text=True)


def test_a_work_hanging_in_two_rooms_names_both(ui, ready_work, hang):
    """One wall is the degenerate case of many, and the sentence does not switch.

    A confirmation that named the first room it found would be silent about the
    second — the same silence, arrived at by being nearly right.
    """
    work = ready_work(title="Nighthawks")
    first = hang(work)
    second = hang(work, wall_name="Study", theme_name="Small hours")

    open_work(ui, work)
    ask(ui, "Archive")

    consequence = ui.page.locator(".confirm-consequence")
    expect(consequence).to_contain_text(first.name, use_inner_text=True)
    expect(consequence).to_contain_text(second.name, use_inner_text=True)
    # Joined as the one joiner joins two (`listed`, `core/counting.js`), in either wall order.
    expect(consequence).to_contain_text(
        re.compile(rf"^(?:{first.name} and {second.name}|{second.name} and {first.name}) are showing this work, and lose it now\."),
        use_inner_text=True,
    )


def test_a_work_hanging_in_three_rooms_lists_them_a_b_and_c(ui, ready_work, hang):
    """Three rooms read "A, B and C": the joiner is a list's, not "and" between every pair."""
    work = ready_work(title="Nighthawks")
    walls = [hang(work), hang(work, wall_name="Study", theme_name="Small hours"), hang(work, wall_name="Hall", theme_name="Mornings")]

    open_work(ui, work)
    ask(ui, "Archive")

    names = "|".join(re.escape(wall.name) for wall in walls)
    expect(ui.page.locator(".confirm-consequence")).to_contain_text(
        re.compile(rf"^(?:{names}), (?:{names}) and (?:{names}) are showing this work, and lose it now\."), use_inner_text=True
    )


def test_a_work_no_wall_is_showing_gets_no_sentence_about_walls(ui, ready_work, hang):
    """The other branch, and the reason the sentence is worth reading when it appears.

    A room is hanging a theme; this work is not in it. `confirmAct` renders no
    description element for an empty consequence, so the question is the title
    alone — which is the difference between a confirmation that says nothing
    because there is nothing to say and one that says nothing because it never
    looked.
    """
    hanging = ready_work(title="Nighthawks")
    work = ready_work(title="Chop Suey", content_hash="hash-2")
    hang(hanging)

    open_work(ui, work)
    ask(ui, "Archive")

    expect(ui.page.locator(".confirm-title")).to_have_text("Archive Chop Suey?", use_inner_text=True)
    expect(ui.page.locator(".confirm-consequence")).to_have_count(0)


def test_a_work_in_a_hung_theme_that_the_wall_cannot_show_is_not_a_consequence(ui, ready_work, hang):
    """Membership is not hanging, and only the manifest knows the difference.

    This work is in the theme the room is showing and has no rendition, so the
    build puts it in that wall's *exclusions* and never on its wall. Archiving it
    costs the room nothing, and a confirmation that answered from theme
    membership would name a wall that was never showing the picture — teaching
    the curator that these sentences are guesses.
    """
    work = ready_work(title="Nighthawks", master=False)
    hang(work)

    open_work(ui, work)
    ask(ui, "Archive")

    # The question is drawn and titled, so a missing sentence is missing from a drawn question.
    expect(ui.page.locator(".confirm-title")).to_have_text("Archive Nighthawks?", use_inner_text=True)
    expect(ui.page.locator(".confirm-consequence")).to_have_count(0)


def test_a_room_with_nothing_hanging_is_not_asked_and_does_not_break_the_question(ui, ready_work, hang, services):
    """The manifest route refuses a wall with nothing on it, and correctly.

    There is no theme to evaluate, and a room showing nothing cannot lose a
    picture — so it is skipped rather than asked. Asking it would turn every
    archive in a house with one empty room into a refusal the curator cannot act
    on, with no dialog at all.
    """
    work = ready_work(title="Nighthawks")
    wall = hang(work)
    services.display.add_wall(name="The empty room")

    open_work(ui, work)
    ask(ui, "Archive")

    consequence = ui.page.locator(".confirm-consequence")
    expect(consequence).to_contain_text(wall.name, use_inner_text=True)
    expect(consequence).not_to_contain_text("The empty room", use_inner_text=True)
    expect(ui.page.locator("#error:not([hidden])")).to_have_count(0)


# -- the act -------------------------------------------------------------------


@pytest.mark.parametrize("decline", ["Cancel", "Escape"])
def test_declining_the_question_leaves_the_work_where_it_was(ui, ready_work, hang, service, decline):
    """The caller owns the act, and a "no" is an answer rather than a delay."""
    work = ready_work(title="Nighthawks")
    hang(work)

    open_work(ui, work)
    ask(ui, "Archive")
    if decline == "Escape":
        ui.page.keyboard.press("Escape")
    else:
        ui.page.click(".confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert service.get_artwork(work.id).artwork.status == "accepted"
    # Archive… stays behind ⋯, and the keyboard is back on ⋯ (ruling 8).
    expect(ui.page.locator(MORE)).to_be_visible()
    expect(ui.page.locator("#view button", has_text="Restore")).to_have_count(0)
    assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')") == "More acts on Nighthawks"


def test_confirming_archives_the_work_and_the_screen_becomes_its_own_undo(ui, ready_work, hang, service):
    """Repainted from the answer the server gave, with the keyboard on the new control.

    The button the curator pressed is replaced by its opposite, so a screen that
    rebuilt itself under a focused control would drop focus to the body and leave
    the next Tab at the top of the page. This is the direct result of a press
    rather than a poll, which is the distinction the focus rule turns on.
    """
    work = ready_work(title="Nighthawks")
    hang(work)

    open_work(ui, work)
    ask(ui, "Archive")
    ui.page.click(".confirm-actions button:has-text('Archive')")
    ui.page.wait_for_selector("#view button:has-text('Restore')")

    assert service.get_artwork(work.id).artwork.status == "archived"
    assert ui.focused() == "Restore"
    expect(ui.page.locator(".badge", has_text="archived")).to_have_count(1)


def test_restoring_says_which_act_it_is_and_what_the_wall_will_do(ui, ready_work, service):
    """The undo asks too, and its sentence says what the room does: take the work back by itself."""
    work = ready_work(title="Nighthawks")
    service.archive_artwork(work.id)

    open_work(ui, work)
    ask(ui, "Restore")

    expect(ui.page.locator(".confirm-title")).to_have_text("Restore Nighthawks?", use_inner_text=True)
    expect(ui.page.locator(".confirm-consequence")).to_have_text(
        "It goes back into the rotation of every wall hanging a theme that holds it.", use_inner_text=True
    )

    ui.page.click(".confirm-actions button:has-text('Restore')")
    ui.page.wait_for_selector(".page-toolbar button:text-is('Restore')", state="detached")

    assert service.get_artwork(work.id).artwork.status == "accepted"
    # This work has no picture to hang, so the keyboard goes to the first act
    # that stands where Restore stood (ruling 8; `test_the_work_page.py` holds Hang…).
    assert ui.focused() == "Add to theme…"


@pytest.mark.parametrize("decline", ["Cancel", "Escape"])
def test_declining_restore_leaves_the_work_archived(ui, ready_work, service, decline):
    work = ready_work(title="Nighthawks")
    service.archive_artwork(work.id)

    open_work(ui, work)
    ask(ui, "Restore")
    if decline == "Escape":
        ui.page.keyboard.press("Escape")
    else:
        ui.page.click(".confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert service.get_artwork(work.id).artwork.status == "archived"
    assert ui.focused() == "Restore"


def test_a_refused_archive_is_announced_rather_than_silently_ignored(ui, service):
    """The catalogue's own sentence, said beside the button that was pressed.

    The work is archived out from under the open screen — which is what a second
    tab, or an agent over MCP, does — so the button the curator presses is
    offering an act the service will refuse.
    """
    work = service.add_artwork(title="Chop Suey")
    open_work(ui, work)
    service.archive_artwork(work.id)

    ask(ui, "Archive")
    ui.page.click(".confirm-actions button:has-text('Archive')")
    # Beside ⋯, the control that was pressed (ruling 8).
    said = ui.said_beside(ui.page.locator(MORE))

    assert said.startswith("Couldn't archive Chop Suey: ")
    assert "already archived" in said


# -- what the work is said to be -----------------------------------------------


def test_only_the_sourced_facet_is_marked_and_the_default_is_a_footnote(ui, service):
    """Inferred is the rule, so the rule is stated once and the exception is marked.

    Nearly every facet in this catalogue was read off the work by a model — the
    wired collection publishes no style field at all — so a badge on each of
    those is a label on almost everything, which is a label nobody reads. The
    mark is a tick rather than a word because an annotation must not outrank the
    value it qualifies, and the word survives for assistive technology so neither
    shape nor colour carries this alone.
    """
    work = service.add_artwork(title="Chop Suey")
    service.record_facet(artwork_id=work.id, kind="movement", value="Precisionism", derivation="sourced")
    service.record_facet(artwork_id=work.id, kind="subject", value="diner", derivation="inferred")

    open_work(ui, work)

    movement = ui.page.locator(".facets dt:has-text('Movement') + dd")
    subject = ui.page.locator(".facets dt:has-text('Subject') + dd")
    expect(movement.locator(".sourced")).to_have_count(1)
    expect(subject.locator(".sourced")).to_have_count(0)
    # The word, for the reader who cannot see a tick, and the tick hidden from
    # them so the mark is announced once rather than as "check mark sourced".
    expect(movement).to_contain_text("sourced")
    expect(movement.locator(".tick")).to_have_attribute("aria-hidden", "true")


def test_the_footnote_sits_below_the_facts_it_qualifies(ui, service):
    """A rule holding for every work must not outrank the facts of this one.

    It sat above them first. A museum label puts its qualifications at the foot
    for the same reason, and the position is the whole of the correction.
    """
    work = service.add_artwork(title="Chop Suey")
    service.record_facet(artwork_id=work.id, kind="era", value="20th c.", derivation="inferred")

    open_work(ui, work)

    panel = ui.page.locator(".panel", has=ui.page.locator("dl.facets"))
    footnote = "inferred unless it carries ✓"
    expect(panel).to_contain_text(footnote, use_inner_text=True)
    # The value comes before the first place the footnote is said: a prefix
    # free of the footnote, then the value.
    expect(panel).to_contain_text(re.compile(rf"^(?:(?!{re.escape(footnote)})[\s\S])*?20th c\."), use_inner_text=True)


def test_a_work_with_no_facets_gets_no_footnote_about_them(ui, service):
    """A default stated under an empty list is a rule about nothing."""
    work = service.add_artwork(title="Chop Suey")

    open_work(ui, work)

    # The work is loaded (its own title heads the page), so a missing list is
    # missing from a drawn page.
    expect(ui.page.locator("#view h1")).to_have_text("Chop Suey", use_inner_text=True)
    expect(ui.page.locator("dl.facets")).to_have_count(0)
    expect(ui.view).not_to_contain_text("inferred unless", use_inner_text=True)


# -- the fact stated once ------------------------------------------------------


def test_the_status_is_stated_by_the_badge_and_not_again_as_a_row(ui, service):
    """A screen states a fact once; two copies invite a search for the difference.

    The badge marks the exception and says nothing when a work is in circulation,
    which is the same inversion the derivation footnote uses — and the control
    below the facts already names which direction is available.
    """
    work = service.add_artwork(title="Chop Suey")
    service.archive_artwork(work.id)

    open_work(ui, work)

    expect(ui.page.locator(".badge", has_text="archived")).to_have_count(1)
    expect(ui.page.locator("dl.facts dt", has_text="Status")).to_have_count(0)


def test_the_mat_shows_its_colour_and_nothing_else(ui, ready_work):
    """The record keeps the method and the date; the label does not show them.

    That history exists so "the new model picked a worse colour" stays answerable
    and reversible, and so the engine's silent fallback to a darkened dominant
    colour is visible in the data. It is a diagnostic question asked rarely, and
    putting its answer on every work's label is putting the audit trail where the
    label goes. **Nothing about this reduces what is stored.**
    """
    work = ready_work(title="Nighthawks")

    # What this checks shows only in debug (ruling 1 of 2026-10-11).
    open_work(ui, work, debug=True)

    swatch = ui.page.locator(".mat .mat-swatch")
    expect(swatch).to_have_count(1)
    expect(ui.page.locator(".mat")).to_contain_text("#27285b", use_inner_text=True)
    expect(ui.view).not_to_contain_text("vision_model", use_inner_text=True)
    expect(ui.page.locator("table caption", has_text="Superseded")).to_have_count(0)
