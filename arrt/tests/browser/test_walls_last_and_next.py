"""Walls with the screen off, and what comes next (#354).

`ia-proposal.md` § Walls, ruling 3 of 2026-10-11: with the screen off, Walls shows
the last-shown work, large, and the next three from the wall's schedule. Ruling 1:
port names only with `?debug`. And the screen being off is said once, in words.

**The record is real.** Each test reports the wall's screen through
`record_heartbeat`, the path a Player's POST takes, so the last-shown work is the
server's log of showings (`programming/showings.py`) and the next three are the
schedule hanging a theme published.
"""

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import MatMethod, RenditionKind

#: Each work's slot: long enough that no test crosses one while it runs.
SLOT = 900


@pytest.fixture
def hall(services):
    return services.clients.add_client(name="Hall Pi")


@pytest.fixture
def the_wall(services, hall):
    wall = services.display.survey_walls()[0].wall
    services.clients.assign_wall(wall.id, client_id=hall.id, output="hdmi-a-1")
    return services.display.get_wall(wall.id)


@pytest.fixture
def works(work_with_an_image, service, settings, decodable_jpeg):
    """Four works that reach a wall, so the next three are three different works."""
    made = []
    for title in ("Nighthawks", "Automat", "Gas", "Chop Suey"):
        artwork = work_with_an_image(title=title)
        service.record_mat_color(artwork_id=artwork.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        presented = f"presentation/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / presented, width=400, height=300)
        service.record_rendition(
            artwork_id=artwork.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=presented
        )
        made.append(artwork)
    return made


@pytest.fixture
def hopper(services, the_wall, works):
    """The four, in order, hung on the wall."""
    theme = services.display.add_theme(name="Hopper")
    for position, work in enumerate(works):
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
    services.display.set_playback(the_wall.id, rotation_interval_seconds=SLOT, shuffle=False)
    services.display.activate_theme(theme.id, wall_id=the_wall.id)
    return theme


def report_state(services, wall, state, work_id=None, *, since, at=None):
    """What a minor 3 Player says its wall's screen is doing."""
    at = at or datetime.now(UTC)
    services.display.record_heartbeat(
        wall.id,
        {
            "reported_at": at.isoformat(timespec="seconds"),
            "schema": {"major": 1, "minor": 3},
            "display_state": {"state": state, "work_id": work_id, "since": since.isoformat(timespec="seconds")},
        },
    )


def screen_off_on(services, hall):
    """The client reports nothing plugged into the wall's output: what made the walk read "off" twice."""
    services.clients.record_heartbeat(
        hall.id,
        {
            "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "outputs": [{"name": "hdmi-a-1", "kind": "framebuffer", "connected": False, "screen": None}],
            "label_outputs": [{"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]}],
        },
    )


@pytest.fixture
def went_dark(services, the_wall, hopper, works, hall):
    """Automat was up, then the screen went off."""
    now = datetime.now(UTC)
    automat = works[1]
    report_state(services, the_wall, "showing_art", automat.id, since=now - timedelta(minutes=10), at=now - timedelta(minutes=2))
    report_state(services, the_wall, "dark", since=now - timedelta(minutes=1), at=now)
    screen_off_on(services, hall)
    return automat


def card(ui, wall):
    return ui.page.locator(f"section.wall[data-wall='{wall.id}']")


def setup_line(ui, wall, kind):
    """A line of the wall's Edit… dialog, opened first: which Player and screen
    show it, and which label captions it, moved off the card by ruling 4 of
    2026-10-27."""
    if not ui.page.locator("dialog.panel-dialog[open]").count():
        card(ui, wall).get_by_role("button", name=f"Edit {wall.name}…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.wait_for()
    return dialog.locator(kind)


def open_walls(ui, *, debug=False):
    ui.open(f"{'?debug' if debug else ''}#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")


def test_with_the_screen_off_the_card_shows_the_last_shown_work_large(ui, the_wall, went_dark):
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    last = lead.locator("figure.wall-last")
    last.wait_for()
    # "Screen off" is the card's badge; the lead says since when (ruling 6 of
    # 2026-10-27, which also dims the work: it is not on the wall now).
    assert lead.locator(".wall-now-state").inner_text().startswith("Off since ")
    assert "wall-dim" in lead.get_attribute("class")
    assert last.locator(".wall-now-when").inner_text().startswith("Last on the wall, until ")
    assert last.get_by_alt_text("Automat").count() == 1
    assert last.get_by_role("link", name="Automat").get_attribute("href").startswith(f"#work/{went_dark.id}")
    assert "size=large" in last.locator("img").get_attribute("src")


def test_a_wall_that_has_shown_nothing_leads_with_the_next_work_dimmed(ui, services, the_wall, hopper):
    """Ruling 6 of 2026-10-27: with nothing logged, the work that comes on when the
    screen does. Renamed from *…leads with its state alone*, which the ruling replaced."""
    upcoming = services.display.get_wall_view(the_wall.id).upcoming
    assert upcoming, "the fixture must schedule works, or there is no next work to lead with"
    report_state(services, the_wall, "dark", since=datetime.now(UTC) - timedelta(minutes=1))
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    lead.wait_for()
    assert lead.locator(".wall-now-state").inner_text().startswith("Off since ")
    figure = lead.locator("figure.wall-last")
    assert figure.locator(".wall-now-when").inner_text().startswith("Next, when the screen comes on")
    assert figure.locator("a").get_attribute("href").startswith(f"#work/{upcoming[0].work_id}")
    # The row under it starts at the second, so the first is not drawn twice.
    nxt = card(ui, the_wall).locator(".wall-next")
    assert nxt.locator("h3").inner_text() == "Then"
    assert upcoming[0].work_id not in (nxt.inner_html())


def test_a_dark_wall_with_nothing_scheduled_leads_with_its_state_alone(ui, services, the_wall):
    report_state(services, the_wall, "dark", since=datetime.now(UTC) - timedelta(minutes=1))
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    lead.wait_for()
    assert lead.locator(".wall-now-state").inner_text().startswith("Off since ")
    assert lead.locator("figure").count() == 0


def test_the_screen_being_off_is_said_once(ui, the_wall, went_dark):
    open_walls(ui)
    card(ui, the_wall).locator("figure.wall-last").wait_for()

    text = card(ui, the_wall).inner_text()
    # Once, in the badge (ruling 6 of 2026-10-27 put the state there).
    assert text.lower().count("screen off") == 1
    assert "screen is off" not in text
    assert "no screen is detected" not in text
    assert setup_line(ui, the_wall, ".wall-client").inner_text() == "Assigned to Hall Pi"


def test_no_port_is_named_without_debug(ui, services, the_wall, went_dark, hall):
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    open_walls(ui)
    card(ui, the_wall).locator("figure.wall-last").wait_for()

    text = card(ui, the_wall).inner_text()
    assert "hdmi-a-1" not in text
    assert "epd-0" not in text
    assert setup_line(ui, the_wall, ".wall-labels").inner_text().startswith("Captioned by a label on Hall Pi.")


def test_debug_names_the_ports(ui, services, the_wall, went_dark, hall):
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    open_walls(ui, debug=True)
    card(ui, the_wall).locator("figure.wall-last").wait_for()

    assert setup_line(ui, the_wall, ".wall-client").inner_text() == "Assigned to Hall Pi on hdmi-a-1"
    assert setup_line(ui, the_wall, ".wall-labels").inner_text().startswith("Captioned by epd-0 on Hall Pi.")


def test_the_next_three_are_the_schedules_next_three(ui, services, the_wall, hopper, went_dark):
    upcoming = services.display.get_wall_view(the_wall.id).upcoming
    open_walls(ui)

    nxt = card(ui, the_wall).locator(".wall-next")
    nxt.locator("li").first.wait_for()
    links = nxt.locator("li a")
    assert links.count() == 3
    assert [href.split("/")[1].split("?")[0] for href in (links.nth(at).get_attribute("href") for at in range(3))] == [
        slot.work_id for slot in upcoming
    ]
    assert all(text.startswith("From ") for text in nxt.locator(".wall-next-when").all_inner_texts())


def test_a_wall_with_no_feed_says_nothing_is_next(ui, the_wall):
    open_walls(ui)

    # The card is drawn (its controls are what `open_walls` waited for), and
    # its Next is there and empty, rather than missing because nothing drew.
    assert card(ui, the_wall).locator(".wall-controls").count() == 1
    assert card(ui, the_wall).locator(".wall-next").count() == 1
    assert card(ui, the_wall).locator(".wall-next").is_hidden()
    assert card(ui, the_wall).locator(".wall-next li").count() == 0


def test_history_is_a_link_and_hanging_is_a_control(ui, the_wall, went_dark):
    """Renamed from *…and change is a button*: Change became the Hanging picker
    (ruling 3 of 2026-10-27), which is a form control with a border, and History
    stays a link with none, in the card's foot."""
    open_walls(ui)
    history = card(ui, the_wall).locator("footer.wall-foot").get_by_role("link", name=f"History of {the_wall.name}")
    picker = card(ui, the_wall).locator(f"select#hang-{the_wall.id}")

    assert "action" not in (history.get_attribute("class") or "")

    def border(locator):
        return locator.evaluate("node => getComputedStyle(node).borderTopStyle")

    assert border(picker) == "solid"
    assert border(history) == "none"


def test_a_wall_no_screen_shows_leads_with_that_and_not_with_what_it_showed(ui, services, the_wall, went_dark):
    services.clients.unassign_wall(the_wall.id)
    open_walls(ui)

    # Hidden since 2026-10-27: the badge says No Player and the line under it has
    # the way to fix it, so the lead adds nothing (a state is worded once).
    lead = card(ui, the_wall).locator(".wall-now")
    lead.wait_for(state="attached")
    assert lead.get_attribute("data-state") == "unassigned"
    assert lead.is_hidden()
    assert lead.locator("figure").count() == 0
    assert card(ui, the_wall).locator("figure").count() == 0


@pytest.mark.parametrize(("state", "words"), [("in_use", "Somebody is using the screen"), ("unreachable", "Not known")])
def test_a_screen_showing_nothing_of_ours_leads_with_the_last_shown_work(ui, services, the_wall, hopper, works, state, words):
    """Not only off: in use, or not known, the work last up is still the best picture of the room."""
    now = datetime.now(UTC)
    report_state(services, the_wall, "showing_art", works[2].id, since=now - timedelta(minutes=10), at=now - timedelta(minutes=2))
    report_state(services, the_wall, state, since=now - timedelta(minutes=1), at=now)
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    lead.locator("figure.wall-last").wait_for()
    assert lead.locator(".wall-now-state").inner_text() == words
    assert lead.locator("figure.wall-last").get_by_role("link", name="Gas").count() == 1


def test_a_silent_wall_whose_last_report_named_no_work_leads_with_the_last_shown_work(ui, services, the_wall, hopper, works):
    """Its last report said the screen was off, ten minutes ago: silent, and the work before that still leads."""
    now = datetime.now(UTC)
    report_state(
        services, the_wall, "showing_art", works[3].id, since=now - timedelta(minutes=30), at=now - timedelta(minutes=20)
    )
    report_state(services, the_wall, "dark", since=now - timedelta(minutes=15), at=now - timedelta(minutes=10))
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    lead.locator("figure.wall-last").wait_for()
    assert lead.get_attribute("data-state") == "silent"
    assert lead.locator("figure.wall-last").get_by_role("link", name="Chop Suey").count() == 1
    assert lead.locator("figure.wall-last .wall-now-when").inner_text().startswith("Last on the wall, until ")


def test_a_wall_whose_report_cannot_be_read_says_when_its_last_work_was_last_seen(
    ui, services, settings, the_wall, hopper, works
):
    """A showing with no end yet, and nothing readable about the screen: "last seen", not "until"."""
    now = datetime.now(UTC)
    report_state(services, the_wall, "showing_art", works[0].id, since=now - timedelta(minutes=5), at=now - timedelta(minutes=1))
    (settings.art_root / f"display-heartbeat-{the_wall.id}.json").write_text("{not json", encoding="utf-8")
    open_walls(ui)

    last = card(ui, the_wall).locator(".wall-now figure.wall-last")
    last.wait_for()
    assert last.locator(".wall-now-when").inner_text().startswith("Last seen on the wall ")
    assert last.get_by_role("link", name="Nighthawks").count() == 1


def test_a_last_shown_work_that_cannot_be_read_is_said_to_be_one(ui, the_wall, went_dark):
    ui.serve(f"**/api/works/{went_dark.id}", (503, {"error": "the library is busy"}))
    open_walls(ui)

    last = card(ui, the_wall).locator(".wall-now .wall-last")
    last.wait_for()
    assert "last showed a work that could not be read — the library is busy" in last.inner_text()


def test_a_next_work_that_cannot_be_read_is_said_in_its_place(ui, services, the_wall, went_dark):
    first = services.display.get_wall_view(the_wall.id).upcoming[0]
    ui.serve(f"**/api/works/{first.work_id}", (503, {"error": "the library is busy"}))
    open_walls(ui)

    nxt = card(ui, the_wall).locator(".wall-next li")
    nxt.first.wait_for()
    assert nxt.count() == 3
    assert nxt.first.inner_text().startswith("A work that could not be read — the library is busy")


def test_after_a_skip_next_is_redrawn_from_the_new_schedule(ui, services, the_wall, hopper, works):
    """The watch replaces the lead and Next together, so Next never names the work now up."""
    now = datetime.now(UTC)
    report_state(services, the_wall, "showing_art", works[0].id, since=now - timedelta(minutes=1), at=now)
    open_walls(ui)
    nxt = card(ui, the_wall).locator(".wall-next li a")
    nxt.first.wait_for()
    before = nxt.all_inner_texts()

    ui.page.get_by_role("button", name=f"Skip the work on {the_wall.name}").click()
    said = card(ui, the_wall).locator(".wall-said")
    said.filter(has_text="Skipped.").wait_for()
    up = services.display.get_wall_view(the_wall.id).upcoming
    report_state(services, the_wall, "showing_art", works[1].id, since=datetime.now(UTC))
    said.filter(has_text=f"{the_wall.name} now shows Automat.").wait_for(timeout=10_000)

    after = nxt.all_inner_texts()
    titles = {work.id: work.title for work in works}
    assert after == [titles[slot.work_id] for slot in up]
    assert after != before
