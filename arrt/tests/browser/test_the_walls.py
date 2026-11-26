"""The Walls — the product's home, in a real browser against a real server.

**The four empty reasons are what this file exists for.** No theme hung, an empty
theme, a Player that has never spoken, and a Player this screen could not
reach: four states, four sentences, four fixes. The failure worth guarding
against is not that one of them renders wrongly — it is that they collapse into
one branch with four strings, which reads as coverage and is not. So every test
here asserts which reasons the screen is naming, not merely that its own one
appears; a branch that started answering for two would fail the test about the
other one.

The fourth is reached differently from the other three and that is deliberate:
three are read off responses that arrived, and the fourth is a request that did
not. It is stubbed for that reason — a server cannot be asked to fail on purpose
— while the other three are seeded for real, including the silent Player, which is
the state every deployment with no display attached is actually in.
"""

import json
import re
from datetime import UTC, datetime

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

from arrt.persistence.records import MatMethod, RenditionKind
from arrt.programming.client_heartbeat import client_heartbeat_path_in

#: The phrase each reason states, keyed by the reason. Two for the silent one,
#: because "nothing has reported" and "something reported and cannot be read"
#: send a person to different places on the Player while being one reason: its
#: Player is not speaking, and the wall is dark either way. In the household's
#: words since audit 2026-11-19 (F5): no plane, no heartbeat, no display for a
#: Player. Every phrase is the walls answer's or the manifest's: the cards ask
#: the status reading for nothing, so none is said of it.
REASONS = {
    "no theme hung": ("Nothing is hanging on",),
    "an empty theme": ("holds no works yet",),
    "its Player silent": (
        "has not reported for",
        "last report cannot be read",
    ),
    "a reading out of reach": (
        "The walls could not be read",
        "The server could not work out what",
    ),
}


def _expect_reasons_named(ui, *named):
    """The screen gives exactly these of the four reasons, by name.

    Asserted as a whole set rather than by looking for one phrase, because the
    defect this file is written against is a branch that answers for a state it
    was not asked about — which no test of its own state can see.

    Each named reason is waited for first, then each of the others is asserted
    absent: the absences stand after the positives, which is what shows the
    screen has painted. A phrase is a regular expression, matched against the
    raw `innerText` as the `in` it replaces was.
    """
    view = ui.view
    for name in named:
        expect(view).to_contain_text(_said(name), use_inner_text=True)
    for name in (each for each in REASONS if each not in named):
        expect(view).not_to_contain_text(_said(name), use_inner_text=True)


def _said(name):
    """Any of the phrases that reason states."""
    return re.compile("|".join(re.escape(phrase) for phrase in REASONS[name]))


@pytest.fixture
def a_displayable_work(work_with_an_image, service, settings, decodable_jpeg):
    """A work that would actually reach a wall: master on disk, matted, rendered.

    `work_with_an_image` stops at the master, which is right for a thumbnail test
    and not enough here — a work with no mat colour and no rendition is excluded
    from every manifest, so a theme built from one is a theme that puts nothing
    up and would exercise the wrong branch of this screen entirely.
    """

    def _work(title="Nighthawks"):
        artwork = work_with_an_image(title=title)
        service.record_mat_color(artwork_id=artwork.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        presented = f"presentation/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / presented, width=400, height=300)
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.PRESENTATION_MASTER,
            target_width=7680,
            target_height=7680,
            path=presented,
        )
        return artwork

    return _work


@pytest.fixture
def a_theme(services):
    """One theme, hanging nowhere. What a curator has just after creating one."""
    return services.display.add_theme(name="Late night")


@pytest.fixture
def a_full_theme(services, a_displayable_work):
    """A theme holding one work that can really be shown."""
    theme = services.display.add_theme(name="Winter")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=a_displayable_work().id)
    return theme


@pytest.fixture
def an_all_excluded_theme(services, work_with_an_image):
    """A theme holding one work that cannot reach a wall: a master and nothing else.

    Not the same state as an empty theme, and the screen must not read it as one:
    `considered` counts entries *plus* exclusions, so a theme whose works were all
    excluded is a theme that published a rotation with nothing in it. No mat colour
    and no rendition is the cheapest way to be excluded — `a_displayable_work`
    exists because that is the default a work arrives in.
    """
    theme = services.display.add_theme(name="Winter")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work_with_an_image(title="Nighthawks").id)
    return theme


@pytest.fixture
def the_wall(services):
    return services.display.survey_walls()[0].wall


@pytest.fixture
def a_hung_wall(services, a_full_theme, the_wall):
    """A populated theme published to the one wall this deployment has.

    Nothing has written a heartbeat, which is not a gap in the fixture: no
    Player is attached to a test deployment, so this is the silent state
    reached honestly rather than stubbed.
    """
    services.display.activate_theme(a_full_theme.id, wall_id=the_wall.id)
    return the_wall


@pytest.fixture
def a_shown_wall(services, a_hung_wall):
    """The hung wall on a Player's screen, the Player holding its token and never having reported.

    Reason three is about a wall whose Player is silent, so the wall has one:
    a wall no Player shows says *No Player* instead, once (audit 2026-11-19,
    finding 6), and is `test_a_wall_no_player_shows_says_so_once_and_not_twice`.
    """
    hall = services.clients.add_client(name="Hall Pi")
    services.access.issue(hall.id)
    services.clients.assign_wall(a_hung_wall.id, client_id=hall.id, output="hdmi-a-1")
    return a_hung_wall


@pytest.fixture
def a_reporting_wall(services, a_shown_wall):
    """The shown wall, its Player reporting it shows the theme's work: the server's own `showing_art`.

    Reported through the route a Player's POST takes, so `/api/walls` and
    `/api/health` both say it, as a real server would. These tests served a
    health answer saying the wall had reported beside a walls answer saying it
    had not, which the card reads its state from.
    """
    feed = json.loads(services.display.published_manifest_v2(a_shown_wall.id))
    services.display.record_heartbeat(
        a_shown_wall.id,
        {"reported_at": datetime.now(UTC).isoformat(timespec="seconds"), "current_work_id": next(iter(feed["works"]))},
    )
    return a_shown_wall


@pytest.fixture
def a_quiet_wall(services, a_shown_wall):
    """The shown wall, its Player reporting while nothing has ever been written for the wall: a wall gone quiet.

    A Player with a token that has not reported at all is a step of its setup,
    and its walls wait for it: reason three is a Player that
    reports and a wall it does not speak for.
    """
    [hall] = [view.client for view in services.clients.list_clients() if view.client.name == "Hall Pi"]
    services.clients.record_heartbeat(
        hall.id,
        {
            "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "outputs": [{"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]}],
        },
    )
    return a_shown_wall


# -- reason one: no theme hung ------------------------------------------------


def test_a_wall_with_no_theme_names_that_wall_and_carries_the_control_that_fixes_it(ui, a_theme, the_wall):
    """The fix is on this screen, not a signpost to another one.

    This state used to offer "Choose a theme to hang" and navigate away, which
    made the product's home a screen you leave to do the thing it is named for.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    _expect_reasons_named(ui, "no theme hung")
    expect(ui.view).to_contain_text(f"Nothing is hanging on {the_wall.name}.", use_inner_text=True)
    # The control is the Hanging fact itself (ruling 3 of 2026-10-27: a fact that
    # can be changed is its own control), named for this wall in its label.
    # There is no separate Hang button to press after choosing.
    expect(ui.page.locator("label", has_text=f"Hanging on {the_wall.name}")).to_have_count(1)
    expect(ui.page.locator(f"select#hang-{the_wall.id}")).to_have_count(1)
    expect(ui.page.locator("button", has_text="Hang on")).to_have_count(0)


def test_a_wall_with_no_theme_and_no_theme_to_hang_offers_the_step_before(ui, the_wall):
    """A picker with nothing in it is a dead end, so it is not what is drawn.

    An empty catalogue reaches this before it reaches anything else, and a
    control that cannot be used is worse than one that is not there: it says the
    curator has done something wrong.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    expect(ui.view).to_contain_text("No theme has been created yet", use_inner_text=True)
    expect(ui.page.locator("a", has_text="Create a theme")).to_have_count(1)
    expect(ui.page.locator("select")).to_have_count(0)
    # Nor does the reason point at a picker that is not there.
    expect(ui.view).to_contain_text(f"Nothing is hanging on {the_wall.name}.", use_inner_text=True)
    expect(ui.view).not_to_contain_text("Choose a theme under Hanging", use_inner_text=True)


# -- reason two: an empty theme -----------------------------------------------


def test_the_take_down_note_for_one_empty_wall_sits_inside_its_card(ui, a_theme, the_wall):
    """Audit 2026-11-19, finding 6: outside the card it sat wider than it and touching it.

    One wall hanging nothing: the note is about that wall, so it is in that
    wall's card. Several: it is said once, under the cards
    (`test_hanging_a_theme.py`, the take-down note said once).
    """
    ui.open("#walls")
    card = ui.page.locator(f"section.wall[data-wall='{the_wall.id}']")
    note = ui.page.locator("p", has_text="goes on showing what it was showing until a theme is hung")
    expect(note).to_have_count(1)
    expect(card.locator("p", has_text="goes on showing what it was showing until a theme is hung")).to_have_count(1)
    expect(ui.page.locator("#view > p.walls-note")).to_have_count(0)


def test_an_empty_theme_says_the_theme_is_empty_and_offers_to_fill_it(ui, services, a_theme, the_wall):
    """A different state from "no theme", and a different next move.

    Both leave the wall showing nothing, which is exactly why they must not share
    a sentence: one is answered by choosing something to hang and the other by
    putting works into what is already hung.
    """
    services.display.activate_theme(a_theme.id, wall_id=the_wall.id)

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    _expect_reasons_named(ui, "an empty theme")
    expect(ui.view).to_contain_text(f"{a_theme.name} holds no works yet, so nothing is on {the_wall.name}.", use_inner_text=True)
    expect(ui.page.locator("a", has_text=f"Add works to {a_theme.name}")).to_have_count(1)


def test_the_empty_themes_control_lands_on_that_theme_rather_than_the_list(ui, services, a_theme, the_wall):
    """ "a wall's theme control" is an entry point the IA names, and it names one theme.

    A button that says "Add works to Winter" and lands on a list of every theme
    makes the curator find Winter again — on the screen whose sentence directly
    above it says which theme is the problem. It could not do otherwise until the
    Theme screen had an address for one theme.
    """
    # A second theme, so "opened the one named" is distinguishable from "opened
    # the only one there is" — which is the whole claim.
    services.display.add_theme(name="Winter")
    services.display.activate_theme(a_theme.id, wall_id=the_wall.id)

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")
    ui.page.click(f"a:has-text('Add works to {a_theme.name}')")
    ui.page.wait_for_selector(f"h1:has-text('{a_theme.name}')")

    # The id, and the opener beside it. Theme's default return is Collection, so
    # arriving from a wall is the case `?from=` exists for — without it the back
    # link would send a curator to the grid from a screen they reached by asking
    # about a wall.
    expect(ui.page).to_have_url(re.compile(re.escape(f"#theme/{a_theme.id}?from=walls") + "$"))
    expect(ui.page.locator("a:has-text('← Walls')")).to_have_count(1)
    expect(ui.page.locator("text=Winter")).to_have_count(0)


def test_an_empty_theme_still_states_the_walls_standing_facts(ui, services, a_theme, the_wall):
    """The setup's panels are not withheld because the wall is empty.

    The exclusions are no longer one of them: the owner's page rules of
    2026-10-27 (`design-direction.md`, "How a page reads") keep an exception
    quiet until it blocks, so the works a wall cannot show are a link at the
    card's foot, there only when there are some (`test_the_card_lists_no_theme_inventory`
    and the footer tests hold that).
    """
    services.display.activate_theme(a_theme.id, wall_id=the_wall.id)

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    # The wall's settings, in its Edit… dialog (ruling 4 of 2026-10-27), and
    # nothing else.
    ui.page.get_by_role("button", name=f"Edit {the_wall.name}…").click()
    # It opens once it has read the wall, which it does when pressed.
    ui.page.locator("dialog.panel-dialog").wait_for()
    expect(ui.page.locator("dialog.panel-dialog .panel h3")).to_have_text(
        [
            "Name",
            "Where it shows",
            "Label panel",
            "How it rotates",
            "Shapes it shows",
            "Mat",
            "Delete",
        ]
    )


# -- reason three: its Player silent ------------------------------------------


def test_a_wall_whose_player_has_never_reported_says_so_and_points_at_status(ui, a_quiet_wall):
    """Published is not showing, and this screen must not conflate them.

    The feed is written and correct; nothing has ever picked it up. A screen
    that showed the pictures and said nothing would be reporting the server's
    intention as the television's state. The way to its reading is a link named
    for the page it opens, Status (audit 2026-11-19, finding 6: it was "Open the
    reading for …"). On a Player that reports (`a_quiet_wall`):
    one that has not reported at all makes its wall wait, which is a step
    (`test_a_wall_waiting_for_its_players_first_report_is_a_step_and_no_notice`).
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    _expect_reasons_named(ui, "its Player silent")
    expect(ui.view).to_contain_text(f"Hall Pi has not reported for {a_quiet_wall.name} yet", use_inner_text=True)
    status = ui.page.locator("section.wall").get_by_role("link", name=f"Status, for {a_quiet_wall.name}'s reading")
    expect(status).to_have_text("Status", use_inner_text=True)
    expect(status).to_have_attribute("href", "#health")
    expect(ui.page.locator("a", has_text="Open the reading")).to_have_count(0)


@pytest.mark.parametrize("token", [True, False], ids=["awaiting_report", "no_token"])
def test_a_wall_waiting_for_its_players_first_report_is_a_step_and_no_notice(ui, services, a_hung_wall, token):
    """A wall whose Player is still being set up says it waits, as Status does, never that it is not reporting.

    Its badge is the Player's state in the contract's word with a setup step's
    mark (○), never ▲ "Not reporting"; its line is the server's words
    (`waiting_for`), linking to the Player; and the card holds no fault's notice.
    """
    hall = services.clients.add_client(name="Hall Pi")
    if token:
        services.access.issue(hall.id)
    services.clients.assign_wall(a_hung_wall.id, client_id=hall.id, output="hdmi-a-1")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    card = ui.page.locator("section.wall")
    state, word, words = (
        ("awaiting_report", "Waiting for its first report", f"{a_hung_wall.name} waits for Hall Pi's first report")
        if token
        else ("no_token", "No token yet", f"{a_hung_wall.name} waits for Hall Pi, which has no token yet")
    )
    badge = card.locator(f".wall-badge[data-state='{state}']")
    expect(badge).to_have_text(re.compile(rf"^○\s*{re.escape(word)}\s*$"), use_inner_text=True)
    expect(badge).to_have_class(re.compile(r"\bwall-badge-setup\b"))
    waits = card.locator("p.wall-waits")
    expect(waits.get_by_role("link", name=words)).to_have_attribute("href", f"#clients?client={hall.id}")
    expect(card.locator(".wall-badge[data-state='silent']")).to_have_count(0)
    expect(card.locator("p.note")).to_have_count(0)
    _expect_reasons_named(ui)
    expect(card).not_to_contain_text("Not reporting", use_inner_text=True)


def test_a_report_that_cannot_be_read_is_the_same_reason_in_different_words(ui, services, settings, a_quiet_wall):
    """Still its Player not speaking, and still the same way on, said from the walls answer with Status out of reach.

    A report that cannot be parsed leaves the wall exactly as dark as no report
    at all, so it is one reason rather than two — but the sentence carries what
    could not be read, because that is the half a person acts on. On a Player
    that reports (`a_quiet_wall`), the wall's own report not JSON: what made it
    unreadable is the walls answer's (`report_problem`), read from the server's
    own reading, so the card says it with `/api/health` refused. Before, the
    card asked the health answer for it, and with that refused said the wall's
    reading was out of reach.
    """
    settings.heartbeat_path(a_quiet_wall.id).write_text("{not json", encoding="utf-8")
    problem = services.health.observe_walls(a_quiet_wall.id).report_problems.get(a_quiet_wall.id)
    assert problem, "the server reads the report as readable, so there is nothing to say of it"
    ui.serve("**/api/health", (500, {"error": "the reading could not be taken"}))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    _expect_reasons_named(ui, "its Player silent")
    expect(ui.view).to_contain_text(f"{a_quiet_wall.name}'s last report cannot be read: {problem}.", use_inner_text=True)
    expect(ui.page.locator("section.wall").get_by_role("link", name=f"Status, for {a_quiet_wall.name}'s reading")).to_have_count(
        1
    )
    expect(ui.page.locator("section.wall").get_by_role("link", name=f"Status, for {a_quiet_wall.name}'s reading")).to_have_count(
        1
    )


def test_a_wall_answered_without_its_state_is_never_read_as_well(ui, services, a_quiet_wall):
    """A wall reported as fine because its observation was missing is the failure this product refuses.

    The walls answer is the one reading a card is said from, so a wall that
    arrives in it with no `display_state` (a shape change) reads as not
    reported, never as hanging well. An answer the server would not send, so
    the real answer is edited here: its one wall's state taken out. Before, the
    case was a status reading carrying no entry for the wall, which the cards
    no longer ask for.
    """
    from arrt.http import api as http_api

    answer = http_api._walls(services).model_dump()
    [entry] = [wall for wall in answer["walls"] if wall["wall_id"] == a_quiet_wall.id]
    del entry["display_state"]
    ui.serve("**/api/walls", answer)

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    _expect_reasons_named(ui, "its Player silent")
    expect(ui.view).to_contain_text(f"has not reported for {a_quiet_wall.name} yet", use_inner_text=True)


def test_a_wall_no_player_shows_says_so_once_and_not_twice(ui, a_hung_wall):
    """No Player and not reported were two notices saying one thing (audit 2026-11-19, finding 6).

    A wall no Player shows has nothing that could report for it, so its *No
    Player* line is the whole of what is wrong: no second notice that it has not
    reported, and no link to a reading that cannot exist.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    card = ui.page.locator("section.wall")
    # The sentence first: it shows the card has painted, so the absences after it
    # are not met by a card still on its way.
    expect(card.locator("p.wall-problem")).to_have_text(re.compile(r"^No Player shows this wall\."), use_inner_text=True)
    _expect_reasons_named(ui)
    expect(card.locator("p.note")).to_have_count(0)
    expect(card.get_by_role("link", name="Status", exact=False)).to_have_count(0)


def test_a_wall_waiting_on_several_players_names_them_a_b_and_c(ui, services, a_hung_wall):
    """Players added with a token and not yet reporting are listed as the one joiner lists them, and agree: "have", "Their".

    One waiting Player reads "Hall Pi has not reported yet. Its screens ..."
    (`test_setting_up_a_wall.py`); with several the sentence is the list's
    (`listed`, `core/counting.js`), held here: a joiner
    broken to join with "+" left this line's tests green.
    """
    for name in ("Hall Pi", "Study Pi", "Landing Pi"):
        services.access.issue(services.clients.add_client(name=name).id)
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    waiting = ui.page.locator("section.wall p.wall-waiting")
    one = "Hall Pi|Study Pi|Landing Pi"
    expect(waiting).to_have_text(
        re.compile(
            rf"^(?:{one}), (?:{one}) and (?:{one}) have not reported yet\. "
            r"Their screens can be chosen here once they are running with their tokens and report\.$"
        ),
        use_inner_text=True,
    )
    for name in ("Hall Pi", "Study Pi", "Landing Pi"):
        expect(waiting).to_contain_text(name, use_inner_text=True)


def test_a_dark_wall_whose_player_has_not_reported_is_one_notice(ui, services, an_all_excluded_theme, the_wall):
    """The theme puts nothing on the wall, and its Player has not reported: one notice, both facts.

    The pair the audit saw stacked (finding 6): "… so the wall is dark." over
    "… has not reported …". Each stays said, in one notice, the dark one first.
    The Player reports and nothing is written for the wall: one that has not
    reported at all makes the wall wait, a step and no notice.
    """
    services.display.activate_theme(an_all_excluded_theme.id, wall_id=the_wall.id)
    hall = services.clients.add_client(name="Hall Pi")
    services.access.issue(hall.id)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.record_heartbeat(
        hall.id,
        {
            "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "outputs": [{"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]}],
        },
    )
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    card = ui.page.locator("section.wall")
    notices = card.locator("p.note")
    expect(notices).to_have_count(1)
    # The dark sentence, then the silent one, in the one notice: an order, so a
    # pattern with the first before the second (the dot of "dark." escaped).
    dark_first = re.escape("so the wall is dark.") + r"[\s\S]*" + re.escape(f"Hall Pi has not reported for {the_wall.name} yet")
    expect(notices).to_have_text(re.compile(dark_first), use_inner_text=True)
    expect(card.locator(".wall-dark-summary")).to_have_text(
        re.compile(re.escape("so the wall is dark.") + "$"), use_inner_text=True
    )


def test_a_dark_wall_no_player_shows_keeps_its_dark_notice(ui, services, an_all_excluded_theme, the_wall):
    """The other branch: with no Player, the dark notice stands alone and is not dropped with the silent one."""
    services.display.activate_theme(an_all_excluded_theme.id, wall_id=the_wall.id)
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    card = ui.page.locator("section.wall")
    expect(card.locator("p.note")).to_have_count(1)
    expect(card.locator(".wall-dark-summary")).to_have_text(
        re.compile(re.escape("so the wall is dark.") + "$"), use_inner_text=True
    )
    expect(card).not_to_contain_text("has not reported", use_inner_text=True)


def test_a_wall_that_has_reported_shows_the_pictures_and_names_no_reason_at_all(ui, a_reporting_wall):
    """The paired positive: the four reasons must not be the only thing this screen can say.

    Without this, every reason could be widened until it always fired and the
    tests above would all still pass.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    # The Skip button first: only a card that has read what is on the wall offers
    # it, so the four absences are not met by a card still on its way.
    expect(_skip(ui, a_reporting_wall.name)).to_have_count(1)
    _expect_reasons_named(ui)


# -- reason four: a reading this screen could not reach ------------------------


def test_a_quiet_walls_card_says_what_its_player_reports_with_status_out_of_reach_and_never_asks_it(ui, a_quiet_wall):
    """A hung wall a Player shows, silent with nothing it last said and waiting for no one: said from the walls answer alone.

    The one card that asked the status reading, for what made a report
    unreadable; the walls answer carries that now (`report_problem`), so with
    `/api/health` refused the card still says its Player has not reported for
    it, and the page asks `/api/health` once, for the top bar
    (`core/status.js`). Before, the card said the wall was read and what its
    Player reports was not, with *Ask again*.
    """
    ui.serve("**/api/health", (500, {"error": "the heartbeat directory could not be opened"}))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    _expect_reasons_named(ui, "its Player silent")
    expect(ui.view).to_contain_text(f"has not reported for {a_quiet_wall.name} yet", use_inner_text=True)
    expect(ui.view).not_to_contain_text("the heartbeat directory could not be opened", use_inner_text=True)
    expect(ui.page.locator("button", has_text="Ask again")).to_have_count(0)
    # The top bar's read has been answered too, so every read the page makes is in.
    ui.page.wait_for_selector("#status[data-state='unwell']")
    assert len(ui.requests_matching("/api/health")) == 1, ui.requests_matching("/api/health")


def test_a_waiting_wall_says_whom_it_waits_for_with_status_out_of_reach_and_never_asks_it(ui, services, a_hung_wall):
    """Whom a wall waits for is the walls answer's (`waiting_for`), so the card says it with `/api/health` refused.

    And the page asks `/api/health` only for the top bar (`core/status.js`, one
    read a page): its cards need nothing that reading holds. Before, the card
    took the wait from a second reading, and with that reading refused it said
    the wall's reading was out of reach instead of whom it waits for.
    """
    living = services.clients.add_client(name="The living room Pi")
    services.clients.assign_wall(a_hung_wall.id, client_id=living.id, output="hdmi-a-1")
    ui.serve("**/api/health", (500, {"error": "the reading could not be taken"}))

    ui.open("#walls")

    card = ui.page.locator("section.wall")
    words = f"{a_hung_wall.name} waits for The living room Pi, which has no token yet"
    expect(card.locator("p.wall-waits").get_by_role("link", name=words)).to_have_attribute("href", f"#clients?client={living.id}")
    expect(card.locator(".wall-badge[data-state='no_token']")).to_have_count(1)
    _expect_reasons_named(ui)
    # The top bar's read has been answered too, so every read the page makes is in.
    ui.page.wait_for_selector("#status[data-state='unwell']")
    assert len(ui.requests_matching("/api/health")) == 1, ui.requests_matching("/api/health")


def test_a_manifest_that_cannot_be_built_names_the_wall_it_was_asked_about(ui, a_hung_wall):
    """The same reason from the other side, and the side that refused is the other one.

    Here the server is the one that refused, and it refused about one wall — so
    the sentence says which, rather than blanking a screen that may be reporting
    three rooms correctly, and that what the Player reports is not what decided it.
    """
    ui.serve("**/api/manifest*", (500, {"error": "the theme could not be evaluated"}))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    _expect_reasons_named(ui, "a reading out of reach")
    expect(ui.view).to_contain_text(f"The server could not work out what {a_hung_wall.name} should show", use_inner_text=True)
    expect(ui.view).to_contain_text("the theme could not be evaluated", use_inner_text=True)
    expect(ui.view).to_contain_text("whatever its Player reports.", use_inner_text=True)


def test_a_wall_list_that_never_arrives_says_nothing_can_be_said_about_any_wall(ui):
    """The one failure that cannot be stated per wall, because there are no walls to state it about."""
    ui.serve("**/api/walls", (500, {"error": "the catalogue is locked"}))

    ui.open("#walls")
    ui.page.wait_for_selector("h1")

    _expect_reasons_named(ui, "a reading out of reach")
    expect(ui.view).to_contain_text("The walls could not be read", use_inner_text=True)
    expect(ui.view).to_contain_text("the catalogue is locked", use_inner_text=True)
    expect(ui.page.locator("button", has_text="Ask again")).to_have_count(1)


# -- hanging, and the question asked first -------------------------------------


def test_hanging_from_this_screen_asks_a_question_that_names_the_wall(ui, a_player_shows, a_full_theme, the_wall):
    """ "Hang Winter on The wall?", never "Hang Winter?".

    Even with one wall, and that is the point: a sentence that reads correctly
    today only because there is one possible target silently becomes wrong.
    The wall is on a Player's screen, since the question promises the house
    sees a change only where a Player shows the wall (audit 2026-11-19, finding
    19; the other branches are the two tests after this one). The Player has
    its token and has reported: one with no token shows nothing yet.
    """
    a_player_shows(the_wall.id)
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    # Choosing in the Hanging picker is the act (ruling 3 of 2026-10-27: it was
    # a picker and a "Hang on …" button); the question still comes first.
    ui.page.select_option(f"select#hang-{the_wall.id}", a_full_theme.id)
    ui.page.wait_for_selector("dialog.confirm[open]")

    expect(ui.page.locator("dialog.confirm .confirm-title")).to_have_text(
        f"Hang {a_full_theme.name} on {the_wall.name}?", use_inner_text=True
    )
    consequence = ui.page.locator("dialog.confirm .confirm-consequence")
    # The build's own summary, evaluated by the server without writing anything,
    # rather than a sentence this screen composed about what it expects.
    expect(consequence).to_contain_text("The one work in this theme is on the wall.", use_inner_text=True)
    expect(consequence).to_contain_text(f"Everyone in the house sees {the_wall.name} change.", use_inner_text=True)


def test_hanging_on_a_wall_no_player_shows_promises_no_one_sees_it(ui, a_full_theme, the_wall):
    """Finding 19 of audit 2026-11-19: the question said everyone would see a wall change that nothing shows."""
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    ui.page.select_option(f"select#hang-{the_wall.id}", a_full_theme.id)
    consequence = ui.page.locator("dialog.confirm[open] .confirm-consequence")
    expect(consequence).to_contain_text(f"No Player shows {the_wall.name} yet, so nothing shows it until one does.")
    expect(consequence).not_to_contain_text("Everyone in the house", use_inner_text=True)


def test_hanging_on_a_wall_whose_player_has_no_token_says_it_waits_in_the_servers_words(ui, services, a_full_theme, the_wall):
    """The question does not tell a person everyone will see a wall change that its Player cannot show yet.

    The words are the server's (`waiting_for.words`, `GET /api/walls`), the
    ones the health panel says; the hang is still asked, and allowed.
    """
    hall = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    waits = services.health.observe_walls().waiting[the_wall.id]
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    ui.page.select_option(f"select#hang-{the_wall.id}", a_full_theme.id)
    consequence = ui.page.locator("dialog.confirm[open] .confirm-consequence")
    expect(consequence).to_contain_text(f"{waits.words}.", use_inner_text=True)
    assert waits.words == f"{the_wall.name} waits for Hall Pi, which has no token yet"
    expect(consequence).not_to_contain_text("Everyone in the house", use_inner_text=True)
    expect(consequence).not_to_contain_text("No Player shows", use_inner_text=True)
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Hang')")
    ui.page.wait_for_selector("section.wall .wall-hanging dt:text-is('Changes')")
    assert services.display.hanging_on(the_wall.id).id == a_full_theme.id


def test_declining_the_question_leaves_the_wall_exactly_as_it_was(ui, services, a_full_theme, the_wall):
    """A confirmation that acts anyway is worse than none: it teaches that the answer is not read."""
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    # Choosing in the Hanging picker is the act (ruling 3 of 2026-10-27: it was
    # a picker and a "Hang on …" button); the question still comes first.
    ui.page.select_option(f"select#hang-{the_wall.id}", a_full_theme.id)
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert services.display.hanging_on(the_wall.id) is None
    _expect_reasons_named(ui, "no theme hung")
    # The picker is put back, so it does not claim a theme the wall does not hang.
    expect(ui.page.locator(f"select#hang-{the_wall.id}")).to_have_value("")


def test_confirming_hangs_it_and_the_wall_repaints_from_what_was_published(ui, services, a_full_theme, the_wall):
    """The wall repaints from the published manifest rather than from optimism.

    The heading that comes back is built from the response to a fresh read, so a
    screen that had guessed the new state would be showing a guess.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    # Choosing in the Hanging picker is the act (ruling 3 of 2026-10-27: it was
    # a picker and a "Hang on …" button); the question still comes first.
    ui.page.select_option(f"select#hang-{the_wall.id}", a_full_theme.id)
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Hang')")
    # The card is drawn again from a fresh read: its picker names what now hangs
    # ("until changed" is gone, ruling 3 of 2026-10-27), and with every work of the
    # theme on the wall there is no count of works it cannot show.
    # Waited for by the "Changes" fact, which only a wall with a published theme
    # has: the picker's own value is set the moment it is chosen, before the
    # question is even answered, so it cannot tell a repaint from a choice.
    ui.page.wait_for_selector("section.wall .wall-hanging dt:text-is('Changes')")
    expect(ui.page.locator(f"select#hang-{the_wall.id}")).to_have_value(a_full_theme.id)

    assert services.display.hanging_on(the_wall.id).id == a_full_theme.id
    expect(ui.page.locator("section.wall button.wall-kept")).to_have_count(0)


# -- skip ----------------------------------------------------------------------


def _skip(ui, wall_name):
    return ui.page.get_by_role("button", name=f"Skip the work on {wall_name}")


def _press_skip(ui, wall):
    """Press Skip and wait for the step's own answer, as `test_walls_lead_with_the_work.py` does.

    So a red says which link broke (#442): no POST at all is the click lost, an
    answer that is not ok is the server refusing, and an ok answer with no
    "Skipped." after it is the card.
    """

    def is_the_step(response):
        return response.request.method == "POST" and response.url.endswith(f"/api/walls/{wall.id}/next")

    with ui.page.expect_response(is_the_step) as answered:
        _skip(ui, wall.name).click()
    return answered.value


def test_skip_names_that_wall_and_steps_only_that_wall(ui, services, a_reporting_wall):
    """A Skip in the living room must not step the study.

    Two walls is the smallest arrangement that can tell the two behaviours apart;
    with one, a route that stepped everything would look perfect. Skip replaces
    "Move on".
    """
    a_hung_wall = a_reporting_wall
    study = services.display.add_wall(name="Study")
    before = services.display.published_manifest_v2(a_hung_wall.id)

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")
    expect(_skip(ui, a_hung_wall.name)).to_have_text("Skip", use_inner_text=True)
    step = _press_skip(ui, a_hung_wall)
    assert step.ok, f"the step was answered {step.status}: {step.text()}"  # one-shot: the response's body, not the page
    card = ui.page.locator(f"section.wall[data-wall='{a_hung_wall.id}']")
    # Asserted rather than waited for, and on the whole card first, so a red
    # prints everything the card says, a failure beside Skip included (#442).
    expect(card).to_contain_text("Skipped.", use_inner_text=True)
    expect(card.locator(".wall-said")).to_contain_text(f"Skipped. {a_hung_wall.name} shows its next work", use_inner_text=True)

    assert services.display.published_manifest_v2(a_hung_wall.id) != before
    assert services.display.published_manifest_v2(study.id) is None
    # The wall with nothing on it is not offered a skip at all: it has no
    # schedule to move on through.
    expect(_skip(ui, "Study")).to_have_count(0)
    # textContent, as it was read: a hidden word counts too. A pattern, because
    # a string would be trimmed and "Move " is the word and the space after it.
    expect(ui.view).not_to_contain_text(re.compile("Move "))
    expect(ui.view).not_to_contain_text("Directive sequence")


def test_a_wall_whose_theme_is_entirely_excluded_is_not_offered_a_skip(ui, services, an_all_excluded_theme, the_wall):
    """The wall reads as hanging and has nothing on it, which is one state, not two.

    `considered` is entries plus exclusions, so a theme whose works were all
    excluded is not an empty theme and does not name one of the four reasons —
    the Not-showing panel answers it per work, which is the better answer. What
    it must not do is offer a skip: the rotation this would advance is empty.
    """
    services.display.activate_theme(an_all_excluded_theme.id, wall_id=the_wall.id)
    # On a Player that reports, through the server, so the wall reads as
    # hanging there too: a stubbed health answer beside a walls answer saying no
    # Player shows it made this pass for the other reason, that no Player does.
    hall = services.clients.add_client(name="Hall Pi")
    services.access.issue(hall.id)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.display.record_heartbeat(the_wall.id, {"reported_at": datetime.now(UTC).isoformat(timespec="seconds")})

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")
    expect(ui.page.locator("section.wall .wall-badge")).not_to_have_attribute("data-state", "unassigned")

    # The card's foot first: it shows the card has read what the wall cannot show,
    # so the four absences are not met by a card still on its way.
    expect(ui.page.locator("section.wall button.wall-kept")).to_be_visible()
    _expect_reasons_named(ui)
    # The panel that does answer it, naming the work and what it is missing,
    # opened from the card's foot (the page rules of 2026-10-27 put the works a
    # wall cannot show there, as a count that opens the list).
    ui.page.click("section.wall button.wall-kept")
    panel = ui.page.locator("dialog.panel-dialog")
    expect(panel).to_contain_text("No mat colour has been chosen", use_inner_text=True)
    expect(_skip(ui, the_wall.name)).to_have_count(0)


def test_a_wall_with_a_work_on_it_is_offered_the_skip(ui, a_reporting_wall):
    """The paired positive: the gate must be a gate rather than an off switch."""
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    expect(_skip(ui, a_reporting_wall.name)).to_have_count(1)


def test_a_wall_its_player_has_not_reported_for_is_not_offered_a_skip_either(ui, a_quiet_wall):
    """The other half of the gate: something is published, and nothing is showing it."""
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    _expect_reasons_named(ui, "its Player silent")
    expect(_skip(ui, a_quiet_wall.name)).to_have_count(0)


def test_a_wall_waiting_for_its_player_is_not_offered_a_skip(ui, a_shown_wall):
    """A waiting wall is said as waiting, and the card offers no Skip, since nothing reports what is on it."""
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall p.wall-waits")

    expect(_skip(ui, a_shown_wall.name)).to_have_count(0)


def test_the_card_lists_no_theme_inventory(ui, a_reporting_wall):
    """The card is about the work on the wall; the theme in full is the theme's page."""
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    # The Skip button first: only a card that has read what is on the wall offers
    # it, so the absences after it are not met by a card still on its way.
    expect(_skip(ui, a_reporting_wall.name)).to_have_count(1)
    # textContent, as it was read. The read took "Not showing (" out first, but
    # that is lower-case "showing (", which the capital-S pattern never matched.
    expect(ui.view).not_to_contain_text(re.compile(r"Showing \("))
    expect(ui.page.locator("ul.hanging")).to_have_count(0)


def _reads(services, wall, majors):
    """A heartbeat from a Player that reads these manifest majors."""
    capabilities = {"screen": {"width_px": 3840, "height_px": 2160}, "backend": "frame", "label_modes": ["none"]}
    services.display.record_heartbeat(
        wall.id,
        {
            "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "capabilities": {**capabilities, "manifest_majors": majors},
        },
    )


def test_a_wall_whose_player_cannot_read_the_feed_says_so_on_its_card(ui, services, a_hung_wall, a_player_shows):
    """The one sign of a Player missed in the upgrade: it asks for a feed that is no longer published."""
    a_player_shows(a_hung_wall.id)
    _reads(services, a_hung_wall, [1])

    ui.open("#walls")
    notice = ui.page.locator(f"section.wall[data-wall='{a_hung_wall.id}'] .wall-feed")
    notice.wait_for()

    expect(notice).to_contain_text("can't read this server's feed", use_inner_text=True)
    expect(notice).to_contain_text("Update Arrt Player", use_inner_text=True)


def test_a_wall_whose_player_reads_the_feed_says_nothing_about_it(ui, services, a_hung_wall, a_player_shows):
    a_player_shows(a_hung_wall.id)
    _reads(services, a_hung_wall, [2, 1])

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    # The card's own controls first: they are painted with the card, after its
    # heartbeat and feed are read, so the absences are not met by a card on its way.
    expect(ui.page.locator("section.wall .wall-controls")).to_be_visible()
    expect(ui.page.locator(".wall-feed")).to_have_count(0)
    # textContent, as it was read: a hidden notice counts too.
    expect(ui.view).not_to_contain_text("can't read this server's feed")


def test_a_card_holds_one_notice_chosen_by_state_and_one_filled_act(
    ui, services, an_all_excluded_theme, the_wall, a_player_shows
):
    """Audit-6 6: a card was a column of notices at one weight. Two faults here, one notice.

    The wall's Player cannot read the feed, and none of its theme reaches it,
    which would be two notices stacked. The card
    says the one that comes first (`cardNotice`: a Player that cannot read
    the feed is mended before the theme's works matter), and the other is not
    said until it is mended.
    """
    services.display.activate_theme(an_all_excluded_theme.id, wall_id=the_wall.id)
    a_player_shows(the_wall.id)
    _reads(services, the_wall, [1])
    ui.open("#walls")
    card = ui.page.locator(f"section.wall[data-wall='{the_wall.id}']")
    card.locator(".wall-controls").wait_for()

    notices = card.locator(".note")
    expect(notices).to_have_count(1)
    expect(notices).to_have_attribute("data-notice", "feed")
    expect(notices).to_contain_text("can't read this server's feed", use_inner_text=True)
    expect(card).not_to_contain_text("so the wall is dark", use_inner_text=True)
    filled = card.locator("button.action:not(.quiet), a.action:not(.quiet)")
    assert filled.count() <= 1, "more than one filled act on one card"  # one-shot: the card has painted (the notice above)


def test_a_card_whose_only_fault_is_its_dark_theme_says_that_one(ui, services, an_all_excluded_theme, the_wall, a_player_shows):
    """The paired case: with the Player reading the feed, the next notice in the order is the one said."""
    services.display.activate_theme(an_all_excluded_theme.id, wall_id=the_wall.id)
    a_player_shows(the_wall.id)
    _reads(services, the_wall, [2, 1])
    ui.open("#walls")
    card = ui.page.locator(f"section.wall[data-wall='{the_wall.id}']")
    card.locator(".wall-controls").wait_for()

    notices = card.locator(".note")
    expect(notices).to_have_count(1)
    expect(notices).to_have_attribute("data-notice", "dark")
    expect(notices).to_contain_text("so the wall is dark", use_inner_text=True)


# -- one wall is the degenerate case of many -----------------------------------


def test_one_wall_reads_as_a_single_wall_home_and_two_add_a_section(ui, services, a_theme, the_wall):
    """The acceptance criterion, asserted as one rendering rather than two.

    The single-wall view is the many-wall view with one entry in it: the same
    section, the same heading rank, the same control naming its own wall. A
    second display adds one of them and replaces nothing.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    expect(ui.page.locator("section.wall")).to_have_count(1)
    expect(ui.page.locator("h2.wall-title")).to_have_text([the_wall.name], use_inner_text=True)
    # The control naming its own wall is the Hanging picker's label (ruling 3 of
    # 2026-10-27; it was a "Hang on …" button).
    expect(ui.page.locator("label", has_text="Hanging on ")).to_have_text([f"Hanging on {the_wall.name}"])

    services.display.add_wall(name="Study")
    # Reloaded rather than navigated to: the address is already `#walls`, and a
    # `goto` at the fragment the page is standing on changes nothing at all — so
    # the second half of this test would assert against the first half's paint.
    ui.page.reload()
    ui.page.wait_for_selector("section.wall")

    expect(ui.page.locator("section.wall")).to_have_count(2)
    expect(ui.page.locator("h2.wall-title")).to_have_text(["Study", the_wall.name], use_inner_text=True)
    # The two labels, in either order (the read sorted them): two of them, and one
    # for each wall, which together are the sorted pair.
    labels = ui.page.locator("label", has_text="Hanging on ")
    expect(labels).to_have_count(2)
    expect(labels.filter(has_text=f"Hanging on {the_wall.name}")).to_have_text([f"Hanging on {the_wall.name}"])
    expect(labels.filter(has_text="Hanging on Study")).to_have_text(["Hanging on Study"])


def test_each_walls_controls_belong_to_that_walls_own_section(ui, services, a_theme, the_wall):
    """Named controls are worth nothing if they are not where the wall is.

    Two rooms' worth of identically shaped controls in one row would be named
    correctly and impossible to use, which is the failure a count of buttons
    cannot see.
    """
    services.display.add_wall(name="Study")

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    study = ui.page.locator("section.wall", has_text="Study")
    # The Hanging picker and its label, inside Study's own card (ruling 3 of
    # 2026-10-27 made the picker the control; it was a picker and a Hang button).
    expect(study.locator("label", has_text="Hanging on ")).to_have_text(["Hanging on Study"])
    expect(study.locator("select.fact-picker")).to_have_count(1)


# -- the focus rule ------------------------------------------------------------

#: The run view's poll interval, which is the fastest anything on this client
#: repaints itself. Waiting past two of them is what makes "nothing came and took
#: the focus" a statement rather than a coincidence of timing.
POLL_MS = 2000


def test_nothing_takes_the_focus_off_this_screens_decision(ui, a_theme, the_wall):
    """A poll must never move focus, and this screen keeps that by not polling.

    `core/status.js` records the decision: mean time to detection on this surface
    is bounded by how often the curator opens the page, and a background timer
    would add load to a Pi without changing it. So the guarantee here is the
    stronger one — nothing repaints behind the curator at all — and it is
    asserted where a curator actually stands still, on the control that decides
    what the whole house sees.

    Written as a wait rather than as a claim about the source, because a poll
    added later would be added in the client and would fail here.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    ui.page.focus(f"select#hang-{the_wall.id}")
    ui.page.wait_for_timeout(
        POLL_MS * 2 + POLL_MS // 2
    )  # sleep: the claim is that nothing repaints or takes the focus across two polls

    assert ui.focused() == f"hang-{the_wall.id}"
    # Not decoration: if the screen had fetched nothing at all this would pass
    # against a page that never painted. One request each, and no more.
    assert len(ui.requests_matching("/api/walls")) == 1


def test_a_repaint_this_screen_did_not_navigate_to_does_not_send_focus_to_the_view(ui, a_theme):
    """The mechanism half of the same rule, pinned so a future poll inherits it.

    `refresh(true)` moves the keyboard to the view, which is right after a
    navigation and is the exact defect when a timer does it. Any poll added to
    this screen repaints through `refresh()` with no argument, and this is what
    says which of the two that is.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    ui.page.evaluate("() => window.refresh()")
    ui.page.wait_for_selector("section.wall")

    assert ui.focused() != "view"


# -- which client shows each wall ------------------------------------------------------


def test_the_walls_screen_issues_no_wall_token_and_says_which_client_shows_each_wall(ui, services, the_wall):
    """Wall tokens are retired: no panel, no button, no route behind one.

    Rewritten from *…and says where players connect*, which held the interim note
    ("Settings › Clients, where they are managed, is not built yet") that stood in
    for Settings › Clients. That page now exists, so the one global note became a
    line per wall saying which client shows it; the no-token half is kept as it
    was, and the per-wall lines have tests of their own below.
    """
    hall = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    study = services.display.add_wall(name="Study")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    expect(ui.page.locator("section.wall")).to_have_count(2)
    expect(ui.page.locator(".player-token")).to_have_count(0)
    expect(ui.page.locator("button", has_text="Player token")).to_have_count(0)
    expect(ui.view).not_to_contain_text("Player token", use_inner_text=True)
    expect(ui.view).not_to_contain_text("WALL_TOKEN", use_inner_text=True)
    expect(ui.view).not_to_contain_text("is not built yet", use_inner_text=True)
    # Which client shows each wall is in that wall's Edit… dialog since ruling 4
    # of 2026-10-27, not on the cards; the card says it only when it is a
    # problem, here the study, which no Player shows.
    expect(ui.page.locator("#view p.wall-client")).to_have_count(0)
    expect(_client_line(ui, the_wall.name)).to_have_count(1)
    study_card = ui.page.locator("section.wall", has=ui.page.locator(f"h2.wall-title:has-text('{study.name}')"))
    expect(study_card.locator(".wall-problem")).to_have_count(1)
    expect(ui.view).to_contain_text(study.name, use_inner_text=True)


def _client_line(ui, wall_name):
    """The wall's Where-it-shows line, in its Edit… dialog (ruling 4 of 2026-10-27
    moved it off the card). One dialog is open at a time, so any other closes first."""
    if ui.page.locator(
        "dialog.panel-dialog[open]"
    ).count():  # one-shot: close an earlier line's dialog only if the test left one open
        ui.page.keyboard.press("Escape")
        ui.page.locator("dialog.panel-dialog").wait_for(state="detached")
    section = ui.page.locator("section.wall", has=ui.page.locator(f"h2.wall-title:has-text('{wall_name}')"))
    section.get_by_role("button", name=f"Edit {wall_name}…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.wait_for()
    return dialog.locator("p.wall-client")


#: Stamped when written (`_report`), so the report is young enough to speak for
#: the screen: one older than three heartbeats says nothing about now, and has
#: its own tests. Stamping it here, at import, made it stale for any test run
#: more than three heartbeats after collection, which a full suite is.
HALL_REPORT = {
    "reported_at": None,
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ],
}


def _report(settings, client, document=HALL_REPORT):
    """What a running client's heartbeat leaves under the art root."""
    path = client_heartbeat_path_in(settings.art_root, client.id)
    if isinstance(document, dict):
        document = document | {"reported_at": datetime.now(UTC).isoformat(timespec="seconds")}
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")


def test_an_assigned_wall_says_which_client_shows_it_and_on_which_output(ui, services, settings, the_wall):
    """Shown, because the client reports a screen detected on that output.

    Rewritten when "Shown by" stopped being said from the assignment alone: a
    wall on an output with nothing detected is not shown by anything, and the
    tests below say what it reads instead. This one keeps its claim, with the
    report that makes it true.
    """
    hall = services.clients.add_client(name="Hall Pi")
    services.access.issue(hall.id)
    _report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.display.add_wall(name="Study")
    # The output by its port name is engineering detail, named with `?debug`
    # (the owner's ruling 1 of 2026-10-11); without it the line ends at the client.
    ui.open("?debug#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    expect(_client_line(ui, the_wall.name)).to_have_text("Shown by Hall Pi on hdmi-a-1", use_inner_text=True)
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")
    expect(_client_line(ui, the_wall.name)).to_have_text("Shown by Hall Pi", use_inner_text=True)
    # The other wall's line is its own: an assignment painted under every wall
    # would read correctly with one wall and be wrong with two.
    # A wall with no Player says so on its card (the page rules of 2026-10-27); its
    # Edit… dialog's Player picker reads None rather than repeating the sentence.
    study = ui.page.locator("section.wall", has=ui.page.locator("h2.wall-title:has-text('Study')"))
    expect(study.locator(".wall-problem")).to_have_text(re.compile(r"^No Player shows this wall\."), use_inner_text=True)


def test_a_wall_on_an_output_with_no_screen_detected_is_not_said_to_be_shown(ui, services, settings, the_wall):
    """A television switched off drops its hotplug line, and the client reports that.

    Two walls on one client, one output each, so a line read from the wrong
    output — or from the client rather than the output — reads wrong for one.
    """
    hall = services.clients.add_client(name="Hall Pi")
    services.access.issue(hall.id)
    _report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-2")
    study = services.display.add_wall(name="Study")
    services.clients.assign_wall(study.id, client_id=hall.id, output="hdmi-a-1")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    # The dark wall's line is asserted whole before the Study's line is opened:
    # the line is the one dialog's, and opening the other closes this one.
    dark = _client_line(ui, the_wall.name)
    expect(dark).to_have_text("Assigned to Hall Pi, where no screen is detected (off or unplugged)", use_inner_text=True)
    expect(dark).not_to_contain_text("Shown", use_inner_text=True)
    # Told apart by what each output reports, not by its name, which the line
    # leaves out without `?debug`.
    expect(_client_line(ui, "Study")).to_have_text("Shown by Hall Pi", use_inner_text=True)


@pytest.mark.parametrize(
    ("document", "words"),
    [
        (None, "Hall Pi has not reported its outputs yet, so whether a screen is there is not known."),
        ("{not json", "Hall Pi's last report could not be read, so whether a screen is there is not known."),
        (
            HALL_REPORT | {"outputs": HALL_REPORT["outputs"][1:]},
            "Hall Pi's last report does not list the output this wall is assigned to.",
        ),
    ],
    ids=["never-reported", "unreadable", "output-not-reported"],
)
def test_a_screen_the_client_has_not_reported_on_is_neither_shown_nor_dark(ui, services, settings, the_wall, document, words):
    """Unknown is its own state: neither "Shown by" nor "no screen detected".

    Each reason is its own sentence, because they send the curator to different
    places: a client not yet running, a report on the client that is corrupt, and
    an assignment naming an output the client does not have.
    """
    hall = services.clients.add_client(name="Hall Pi")
    services.access.issue(hall.id)
    if document is not None:
        _report(settings, hall, document)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    line = _client_line(ui, the_wall.name)
    expect(line).to_have_text(f"Assigned to Hall Pi. {words}", use_inner_text=True)
    expect(line).not_to_contain_text("Shown", use_inner_text=True)
    expect(line).not_to_contain_text("no screen is detected", use_inner_text=True)


def test_an_unassigned_wall_says_no_player_shows_it_and_opens_where_one_is_chosen(ui, services, the_wall):
    hall = services.clients.add_client(name="Hall Pi")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    # Said on the card itself, because it is a problem (the page rules of
    # 2026-10-27), and in the ruled word, Player. Its mend is the wall's own
    # Edit…, where a Player is chosen since ruling 7 of 2026-10-27 took that
    # off Settings › Players, which it linked to until then.
    line = ui.page.locator("section.wall p.wall-problem")
    expect(line).to_have_text("No Player shows this wall. Choose its Player…", use_inner_text=True)
    expect(line.get_by_role("link")).to_have_count(0)
    line.get_by_role("button", name=f"Choose the Player for {the_wall.name}…").click()

    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.wait_for()
    expect(dialog.locator(".confirm-title")).to_have_text(f"Edit {the_wall.name}", use_inner_text=True)
    picker = dialog.get_by_label(f"Player for {the_wall.name}", exact=True)
    # One option whose whole text is the Player's name, in whatever place in the
    # list: a subsequence of one, which is how a list holds an item.
    expect(picker.locator("option")).to_contain_text([re.compile("^" + re.escape(hall.name) + "$")], use_inner_text=True)


def test_a_client_listing_that_never_arrives_still_says_which_output_shows_the_wall(ui, services, the_wall):
    """The listing is where a client's name is; without it the wall still knows its output.

    Stubbed, for the reason the unreachable-Player tests are: a server cannot be
    asked to fail on purpose. Nothing else on the screen may go with it.
    """
    hall = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    ui.serve("**/api/clients", (503, {"error": "the Player listing is down"}))
    # Which output is engineering detail, said with `?debug` (ruling 1 of 2026-10-11).
    ui.open("?debug#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    line = _client_line(ui, the_wall.name)
    # The listing carries the client's report as well as its name, so without it
    # whether a screen is there is unknown too, and "Shown" would claim it.
    expect(line).to_have_text(
        "Assigned to hdmi-a-1 of a Player whose name and report could not be read — the Player listing is down",
        use_inner_text=True,
    )
    expect(ui.page.locator("#error")).to_be_hidden()
    expect(ui.view).to_contain_text("Nothing is hanging on", use_inner_text=True)
