"""The Walls — the product's home, in a real browser against a real server.

**The four empty reasons are what this file exists for.** No theme hung, an empty
theme, a display plane that has never spoken, and a plane this screen could not
reach: four states, four sentences, four fixes. The failure worth guarding
against is not that one of them renders wrongly — it is that they collapse into
one branch with four strings, which reads as coverage and is not. So every test
here asserts which reasons the screen is naming, not merely that its own one
appears; a branch that started answering for two would fail the test about the
other one.

The fourth is reached differently from the other three and that is deliberate:
three are read off responses that arrived, and the fourth is a request that did
not. It is stubbed for that reason — a server cannot be asked to fail on purpose
— while the other three are seeded for real, including the silent plane, which is
the state every deployment with no display attached is actually in.
"""

import json
from datetime import UTC, datetime

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import MatMethod, RenditionKind
from arrt.programming.client_heartbeat import client_heartbeat_path_in

#: The phrase each reason states, keyed by the reason. Several for the silent
#: one, because "nothing was ever written", "something was written and cannot be
#: parsed" and "the reading names no heartbeat for this wall" send an operator to
#: three different places on the appliance while being one reason: the display
#: plane is not speaking, and the wall is dark either way.
REASONS = {
    "no theme hung": ("Nothing is hanging on",),
    "an empty theme": ("holds no works yet",),
    "the display plane silent": (
        "No display has ever reported for",
        "heartbeat cannot be read",
        "carries no heartbeat for",
    ),
    "a plane out of reach": ("The curation plane answered", "The curation plane did not answer"),
}


def _reasons_named(ui):
    """Which of the four the screen is currently giving, by name.

    Asserted as a whole set rather than by looking for one phrase, because the
    defect this file is written against is a branch that answers for a state it
    was not asked about — which no test of its own state can see.
    """
    text = ui.text()
    return sorted(name for name, phrases in REASONS.items() if any(phrase in text for phrase in phrases))


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
        rendered = f"ready/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=artwork.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
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
    display plane is attached to a test deployment, so this is the silent state
    reached honestly rather than stubbed.
    """
    services.display.activate_theme(a_full_theme.id, wall_id=the_wall.id)
    return the_wall


# -- reason one: no theme hung ------------------------------------------------


def test_a_wall_with_no_theme_names_that_wall_and_carries_the_control_that_fixes_it(ui, a_theme, the_wall):
    """The fix is on this screen, not a signpost to another one.

    This state used to offer "Choose a theme to hang" and navigate away, which
    made the product's home a screen you leave to do the thing it is named for.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert _reasons_named(ui) == ["no theme hung"]
    assert f"Nothing is hanging on {the_wall.name}." in ui.text()
    # The control, named for this wall in its label as well as on its button.
    assert ui.page.locator("label", has_text=f"Theme for {the_wall.name}").count() == 1
    assert ui.page.locator("button", has_text=f"Hang on {the_wall.name}").count() == 1
    assert ui.page.locator(f"select#hang-{the_wall.id}").count() == 1


def test_a_wall_with_no_theme_and_no_theme_to_hang_offers_the_step_before(ui, the_wall):
    """A picker with nothing in it is a dead end, so it is not what is drawn.

    An empty catalogue reaches this before it reaches anything else, and a
    control that cannot be used is worse than one that is not there: it says the
    curator has done something wrong.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert "No theme has been created yet" in ui.text()
    assert ui.page.locator("a", has_text="Create a theme").count() == 1
    assert ui.page.locator("select").count() == 0


# -- reason two: an empty theme -----------------------------------------------


def test_an_empty_theme_says_the_theme_is_empty_and_offers_to_fill_it(ui, services, a_theme, the_wall):
    """A different state from "no theme", and a different next move.

    Both leave the wall showing nothing, which is exactly why they must not share
    a sentence: one is answered by choosing something to hang and the other by
    putting works into what is already hung.
    """
    services.display.activate_theme(a_theme.id, wall_id=the_wall.id)

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert _reasons_named(ui) == ["an empty theme"]
    assert f"{a_theme.name} holds no works yet, so nothing is on {the_wall.name}." in ui.text()
    assert ui.page.locator("a", has_text=f"Add works to {a_theme.name}").count() == 1


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
    assert ui.page.evaluate("() => window.location.hash") == f"#theme/{a_theme.id}?from=walls"
    assert ui.page.locator("a:has-text('← Walls')").count() == 1
    assert ui.page.locator("text=Winter").count() == 0


def test_an_empty_theme_still_states_the_walls_standing_facts(ui, services, a_theme, the_wall):
    """The panels are not withheld because the wall is empty.

    A section that appeared only when there was something to report would train a
    reader to take its absence for "everything is fine" — which is the same rule
    the exclusions panel is never omitted under.
    """
    services.display.activate_theme(a_theme.id, wall_id=the_wall.id)

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    # The setup's two panels, behind their disclosure, and nothing else.
    assert ui.page.locator("section.wall details.wall-setup .panel h3").all_text_contents() == [
        "Not showing (0)",
        "How it rotates",
    ]


# -- reason three: the display plane silent -----------------------------------


def test_a_wall_whose_display_has_never_reported_says_so_and_points_at_the_reading(ui, a_hung_wall):
    """Published is not showing, and this screen must not conflate them.

    The manifest is written and correct; nothing has ever picked it up. A screen
    that showed the pictures and said nothing would be reporting the curation
    plane's intention as the television's state.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert _reasons_named(ui) == ["the display plane silent"]
    assert f"No display has ever reported for {a_hung_wall.name}." in ui.text()
    assert ui.page.locator("a", has_text=f"Open the reading for {a_hung_wall.name}").count() == 1


def test_a_heartbeat_that_cannot_be_read_is_the_same_reason_in_different_words(ui, a_hung_wall, a_health_reading, a_wall_reading):
    """Still the display plane not speaking, and still the same fix.

    A report that cannot be parsed leaves the wall exactly as dark as no report
    at all, so it is one reason rather than two — but the sentence carries what
    could not be read, because that is the half an operator acts on.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(walls=[a_wall_reading(wall_id=a_hung_wall.id, name=a_hung_wall.name, problem="the file is not JSON")]),
    )

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert _reasons_named(ui) == ["the display plane silent"]
    assert f"{a_hung_wall.name}'s heartbeat cannot be read: the file is not JSON." in ui.text()
    assert ui.page.locator("a", has_text=f"Open the reading for {a_hung_wall.name}").count() == 1


def test_a_reading_that_names_no_heartbeat_for_this_wall_is_never_read_as_well(ui, a_hung_wall, a_health_reading):
    """A wall reported as fine because its observation was missing is the failure this product refuses.

    The aggregate can arrive carrying no reading for a wall — a shape change, a
    wall created between two requests — and the safe direction is to say so.
    """
    ui.serve("**/api/health", a_health_reading(walls=[]))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert _reasons_named(ui) == ["the display plane silent"]
    assert f"The health reading carries no heartbeat for {a_hung_wall.name}" in ui.text()


def test_a_wall_that_has_reported_shows_the_pictures_and_names_no_reason_at_all(
    ui, a_hung_wall, a_health_reading, a_wall_reading
):
    """The paired positive: the four reasons must not be the only thing this screen can say.

    Without this, every reason could be widened until it always fired and the
    tests above would all still pass.
    """
    ui.serve("**/api/health", a_health_reading(walls=[a_wall_reading(wall_id=a_hung_wall.id, name=a_hung_wall.name)]))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    assert _reasons_named(ui) == []


# -- reason four: a plane this screen could not reach --------------------------


def test_a_health_reading_that_never_arrives_says_which_plane_did_answer(ui, a_hung_wall):
    """Not "something went wrong": which of the two planes spoke.

    The distinction is the curator's next move. The curation plane answering and
    the display plane's reading not arriving is a fault in one place; the
    curation plane not answering at all is a fault in another.
    """
    ui.serve("**/api/health", (500, {"error": "the heartbeat directory could not be opened"}))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert _reasons_named(ui) == ["a plane out of reach"]
    assert f"The curation plane answered for {a_hung_wall.name}" in ui.text()
    assert "the reading that speaks for the display plane did not" in ui.text()
    assert "the heartbeat directory could not be opened" in ui.text()
    assert ui.page.locator("button", has_text="Ask again").count() == 1


def test_a_manifest_that_cannot_be_built_names_the_wall_it_was_asked_about(ui, a_hung_wall):
    """The same reason from the other side, and the plane that answered is the other one.

    Here the curation plane is the one that refused, and it refused about one
    wall — so the sentence says which, rather than blanking a screen that may be
    reporting three rooms correctly.
    """
    ui.serve("**/api/manifest*", (500, {"error": "the theme could not be evaluated"}))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert _reasons_named(ui) == ["a plane out of reach"]
    assert f"refused {a_hung_wall.name}'s build" in ui.text()
    assert "The display plane was not asked." in ui.text()


def test_a_wall_list_that_never_arrives_says_nothing_can_be_said_about_any_wall(ui):
    """The one failure that cannot be stated per wall, because there are no walls to state it about."""
    ui.serve("**/api/walls", (500, {"error": "the catalogue is locked"}))

    ui.open("#walls")
    ui.page.wait_for_selector("h1")

    assert _reasons_named(ui) == ["a plane out of reach"]
    assert "The curation plane did not answer" in ui.text()
    assert "the catalogue is locked" in ui.text()
    assert ui.page.locator("button", has_text="Ask again").count() == 1


# -- hanging, and the question asked first -------------------------------------


def test_hanging_from_this_screen_asks_a_question_that_names_the_wall(ui, a_full_theme, the_wall):
    """ "Hang Winter on The wall?", never "Hang Winter?".

    Even with one wall, and that is the point: a sentence that reads correctly
    today only because there is one possible target silently becomes wrong.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    ui.page.click(f"button:has-text('Hang on {the_wall.name}')")
    ui.page.wait_for_selector("dialog.confirm[open]")

    assert ui.page.inner_text("dialog.confirm .confirm-title") == f"Hang {a_full_theme.name} on {the_wall.name}?"
    consequence = ui.page.inner_text("dialog.confirm .confirm-consequence")
    # The build's own summary, evaluated by the server without writing anything,
    # rather than a sentence this screen composed about what it expects.
    assert "All 1 work in this theme is on the wall." in consequence
    assert f"Everyone in the house sees {the_wall.name} change." in consequence


def test_declining_the_question_leaves_the_wall_exactly_as_it_was(ui, services, a_full_theme, the_wall):
    """A confirmation that acts anyway is worse than none: it teaches that the answer is not read."""
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    ui.page.click(f"button:has-text('Hang on {the_wall.name}')")
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert services.display.hanging_on(the_wall.id) is None
    assert _reasons_named(ui) == ["no theme hung"]


def test_confirming_hangs_it_and_the_wall_repaints_from_what_was_published(ui, services, a_full_theme, the_wall):
    """The wall repaints from the published manifest rather than from optimism.

    The heading that comes back is built from the response to a fresh read, so a
    screen that had guessed the new state would be showing a guess.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    ui.page.click(f"button:has-text('Hang on {the_wall.name}')")
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Hang')")
    ui.page.wait_for_selector(f".wall-source:has-text('Drawing from {a_full_theme.name}, until changed.')")

    assert services.display.hanging_on(the_wall.id).id == a_full_theme.id
    assert "All 1 work in this theme is on the wall." in ui.text()


# -- skip ----------------------------------------------------------------------


def _skip(ui, wall_name):
    return ui.page.get_by_role("button", name=f"Skip the work on {wall_name}")


def test_skip_names_that_wall_and_steps_only_that_wall(ui, services, a_hung_wall, a_health_reading, a_wall_reading):
    """A Skip in the living room must not step the study.

    Two walls is the smallest arrangement that can tell the two behaviours apart;
    with one, a route that stepped everything would look perfect. Skip replaces
    "Move on", and the directive's counter is not a thing a curator reads.
    """
    study = services.display.add_wall(name="Study")
    ui.serve(
        "**/api/health",
        a_health_reading(
            walls=[
                a_wall_reading(wall_id=a_hung_wall.id, name=a_hung_wall.name),
                a_wall_reading(wall_id=study.id, name=study.name),
            ]
        ),
    )
    before = services.display.read_directive(a_hung_wall.id).sequence

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")
    skip = _skip(ui, a_hung_wall.name)
    assert skip.inner_text() == "Skip"
    skip.click()
    ui.page.wait_for_selector(f".wall-said:has-text('Skipped. {a_hung_wall.name} shows its next work')")

    assert services.display.read_directive(a_hung_wall.id).sequence == before + 1
    assert services.display.read_directive(study.id).sequence == 0
    # The wall with nothing on it is not offered a skip at all: advancing a wall
    # that is showing nothing writes a directive nobody can act on.
    assert _skip(ui, "Study").count() == 0
    whole = ui.page.locator("#view").text_content()
    assert "Move " not in whole
    assert "Directive sequence" not in whole


def test_a_wall_whose_theme_is_entirely_excluded_is_not_offered_a_skip(
    ui, services, an_all_excluded_theme, the_wall, a_health_reading, a_wall_reading
):
    """The wall reads as hanging and has nothing on it, which is one state, not two.

    `considered` is entries plus exclusions, so a theme whose works were all
    excluded is not an empty theme and does not name one of the four reasons —
    the Not-showing panel answers it per work, which is the better answer. What
    it must not do is offer a skip: the rotation this would advance is empty.
    """
    services.display.activate_theme(an_all_excluded_theme.id, wall_id=the_wall.id)
    ui.serve("**/api/health", a_health_reading(walls=[a_wall_reading(wall_id=the_wall.id, name=the_wall.name)]))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    assert _reasons_named(ui) == []
    # The panel that does answer it, naming the work and what it is missing.
    ui.page.click(f"summary:has-text('How {the_wall.name} is set up')")
    assert "Not showing (1)" in ui.text()
    assert "No mat colour has been chosen" in ui.text()
    assert _skip(ui, the_wall.name).count() == 0


def test_a_wall_with_a_work_on_it_is_offered_the_skip(ui, a_hung_wall, a_health_reading, a_wall_reading):
    """The paired positive: the gate must be a gate rather than an off switch."""
    ui.serve("**/api/health", a_health_reading(walls=[a_wall_reading(wall_id=a_hung_wall.id, name=a_hung_wall.name)]))

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    assert _skip(ui, a_hung_wall.name).count() == 1


def test_a_wall_no_display_has_reported_for_is_not_offered_a_skip_either(ui, a_hung_wall):
    """The other half of the gate: something is published, and nothing is showing it."""
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    assert _reasons_named(ui) == ["the display plane silent"]
    assert _skip(ui, a_hung_wall.name).count() == 0


def test_the_card_lists_no_theme_inventory(ui, a_hung_wall, a_health_reading, a_wall_reading):
    """The card is about the work on the wall; the theme in full is the theme's page."""
    ui.serve("**/api/health", a_health_reading(walls=[a_wall_reading(wall_id=a_hung_wall.id, name=a_hung_wall.name)]))
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")

    assert "Showing (" not in ui.page.locator("#view").text_content().replace("Not showing (", "")
    assert ui.page.locator("ul.hanging").count() == 0


# -- one wall is the degenerate case of many -----------------------------------


def test_one_wall_reads_as_a_single_wall_home_and_two_add_a_section(ui, services, a_theme, the_wall):
    """The acceptance criterion, asserted as one rendering rather than two.

    The single-wall view is the many-wall view with one entry in it: the same
    section, the same heading rank, the same control naming its own wall. A
    second display adds one of them and replaces nothing.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall")

    assert ui.page.locator("section.wall").count() == 1
    assert ui.page.locator("h2.wall-title").all_inner_texts() == [the_wall.name]
    assert ui.page.locator("button", has_text="Hang on ").all_inner_texts() == [f"Hang on {the_wall.name}"]

    services.display.add_wall(name="Study")
    # Reloaded rather than navigated to: the address is already `#walls`, and a
    # `goto` at the fragment the page is standing on changes nothing at all — so
    # the second half of this test would assert against the first half's paint.
    ui.page.reload()
    ui.page.wait_for_selector("section.wall")

    assert ui.page.locator("section.wall").count() == 2
    assert ui.page.locator("h2.wall-title").all_inner_texts() == ["Study", the_wall.name]
    assert sorted(ui.page.locator("button", has_text="Hang on ").all_inner_texts()) == [
        "Hang on Study",
        f"Hang on {the_wall.name}",
    ]


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
    assert study.locator("button", has_text="Hang on ").all_inner_texts() == ["Hang on Study"]
    assert study.locator("label").all_inner_texts() == ["Theme for Study"]


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
    ui.page.wait_for_timeout(POLL_MS * 2 + POLL_MS // 2)

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
    ui.page.wait_for_selector("section.wall p.wall-client")

    assert ui.page.locator("section.wall").count() == 2
    assert ui.page.locator(".player-token").count() == 0
    assert ui.page.locator("button", has_text="Player token").count() == 0
    assert "Player token" not in ui.text()
    assert "WALL_TOKEN" not in ui.text()
    assert "is not built yet" not in ui.text()
    # One line inside each wall's own section, and none outside them.
    assert ui.page.locator("section.wall p.wall-client").count() == 2
    assert ui.page.locator("#view > p.wall-client").count() == 0
    assert study.name in ui.text()


def _client_line(ui, wall_name):
    section = ui.page.locator("section.wall", has=ui.page.locator(f"h2.wall-title:has-text('{wall_name}')"))
    return section.locator("p.wall-client")


#: Stamped now, so the report is young enough to speak for the screen: one
#: older than three heartbeats says nothing about now, and has its own tests.
HALL_REPORT = {
    "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ],
}


def _report(settings, client, document=HALL_REPORT):
    """What a running client's heartbeat leaves under the art root."""
    path = client_heartbeat_path_in(settings.art_root, client.id)
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")


def test_an_assigned_wall_says_which_client_shows_it_and_on_which_output(ui, services, settings, the_wall):
    """Shown, because the client reports a screen detected on that output.

    Rewritten when "Shown by" stopped being said from the assignment alone: a
    wall on an output with nothing detected is not shown by anything, and the
    tests below say what it reads instead. This one keeps its claim, with the
    report that makes it true.
    """
    hall = services.clients.add_client(name="Hall Pi")
    _report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.display.add_wall(name="Study")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall p.wall-client")

    assert _client_line(ui, the_wall.name).inner_text() == "Shown by Hall Pi on hdmi-a-1"
    # The other wall's line is its own: an assignment painted under every wall
    # would read correctly with one wall and be wrong with two.
    assert _client_line(ui, "Study").inner_text().startswith("No client shows this wall.")


def test_a_wall_on_an_output_with_no_screen_detected_is_not_said_to_be_shown(ui, services, settings, the_wall):
    """A television switched off drops its hotplug line, and the client reports that.

    Two walls on one client, one output each, so a line read from the wrong
    output — or from the client rather than the output — reads wrong for one.
    """
    hall = services.clients.add_client(name="Hall Pi")
    _report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-2")
    study = services.display.add_wall(name="Study")
    services.clients.assign_wall(study.id, client_id=hall.id, output="hdmi-a-1")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall p.wall-client")

    dark = _client_line(ui, the_wall.name).inner_text()
    assert dark == "Assigned to Hall Pi on hdmi-a-2, where no screen is detected (off or unplugged)"
    assert "Shown" not in dark
    assert _client_line(ui, "Study").inner_text() == "Shown by Hall Pi on hdmi-a-1"


@pytest.mark.parametrize(
    ("document", "words"),
    [
        (None, "Hall Pi has not reported its outputs yet, so whether a screen is there is not known."),
        ("{not json", "Hall Pi's last report could not be read, so whether a screen is there is not known."),
        (HALL_REPORT | {"outputs": HALL_REPORT["outputs"][1:]}, "Hall Pi's last report lists no output called hdmi-a-1."),
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
    if document is not None:
        _report(settings, hall, document)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall p.wall-client")

    line = _client_line(ui, the_wall.name).inner_text()
    assert line == f"Assigned to Hall Pi on hdmi-a-1. {words}"
    assert "Shown" not in line
    assert "no screen is detected" not in line


def test_an_unassigned_wall_says_no_client_shows_it_and_links_to_where_one_is_assigned(ui, services, the_wall):
    services.clients.add_client(name="Hall Pi")
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall p.wall-client")

    line = _client_line(ui, the_wall.name)
    assert line.inner_text() == "No client shows this wall. Assign it in Settings › Clients"
    link = line.get_by_role("link", name="Assign it in Settings › Clients")
    assert link.get_attribute("href") == "#clients"

    link.click()
    ui.page.wait_for_selector("#view h1:has-text('Clients')")
    assert ui.page.locator("nav.sidebar a[data-view='clients'][aria-current='page']").count() == 1


def test_a_client_listing_that_never_arrives_still_says_which_output_shows_the_wall(ui, services, the_wall):
    """The listing is where a client's name is; without it the wall still knows its output.

    Stubbed, for the reason the unreachable-plane tests are: a server cannot be
    asked to fail on purpose. Nothing else on the screen may go with it.
    """
    hall = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    ui.serve("**/api/clients", (503, {"error": "the client listing is down"}))
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall p.wall-client")

    line = _client_line(ui, the_wall.name).inner_text()
    # The listing carries the client's report as well as its name, so without it
    # whether a screen is there is unknown too, and "Shown" would claim it.
    assert line == "Assigned to hdmi-a-1 of a client whose name and report could not be read — the client listing is down"
    assert ui.page.locator("#error").is_hidden()
    assert "Nothing is hanging on" in ui.text()
