"""Activity › History reads the event log, in a real browser against a real server.

`ia-proposal.md` § Rulings (2026-10-07), ruling 6: history is events, from now
on. Every test seeds the history through the acts that write it (an archive, a
hang, *Not this one again*), or through the catalogue's own `record_event` for a
Get, whose run would take a model to start — never a stubbed listing, so what
is asserted is what the page makes of what the server really records.
"""

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import EventKind

#: A Get started from Ask, as `discovery.py`'s `_record_started` writes it.
ASKED = {"run_kind": "discovery", "intent": "Quiet interiors"}


@pytest.fixture
def the_wall(services):
    return services.display.survey_walls()[0].wall


def open_history(ui, fragment="#history"):
    ui.open(fragment)
    ui.page.wait_for_selector("#view h1")


def rows(ui) -> list[str]:
    return ui.page.locator("ol.history-events li").all_inner_texts()


def test_each_act_reads_as_a_sentence_newest_first(ui, services, work_with_an_image, the_wall):
    """An archive, a restore, a hang and *Not this one again*, in the order they happened, newest first."""
    work = work_with_an_image(title="Nighthawks")
    theme = services.display.add_theme(name="Winter")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.catalogue.archive_artwork(work.id)
    services.catalogue.restore_artwork(work.id)
    services.display.activate_theme(theme.id, wall_id=the_wall.id)
    services.display.exclude_work(work.id, wall_id=the_wall.id)
    services.display.allow_work(work.id)

    open_history(ui)
    ui.page.wait_for_selector("ol.history-events li")

    sentences = [row.split("\t")[-1].split("\n")[-1] for row in rows(ui)]
    assert sentences == [
        "Let Nighthawks back on the walls",
        f"Kept Nighthawks off every wall (from {the_wall.name})",
        f"Hung Winter on {the_wall.name}",
        "Restored Nighthawks",
        "Archived Nighthawks",
    ]
    # The title the walls' events do not carry is the work's own, read from the
    # library, and it opens the work.
    assert (
        ui.page.locator("ol.history-events li")
        .first.get_by_role("link", name="Nighthawks")
        .get_attribute("href")
        .startswith(f"#work/{work.id}")
    )


def test_a_date_is_said_as_how_long_ago_with_the_date_a_hover_away(ui, services, work_with_an_image):
    work = work_with_an_image(title="Nighthawks")
    services.catalogue.archive_artwork(work.id)

    open_history(ui)
    stamp = ui.page.locator("ol.history-events li time").first
    stamp.wait_for()

    assert stamp.inner_text() in {"0 seconds ago", "1 second ago", "2 seconds ago", "3 seconds ago"}
    # The machine instant is in the attribute, never in what is read.
    assert stamp.get_attribute("datetime").startswith(str(datetime.now(UTC).year))
    assert "T" not in ui.text()
    assert stamp.get_attribute("title")


def test_a_get_reads_as_what_was_asked_and_how_it_ended(ui, services):
    services.catalogue.record_event(EventKind.GET_STARTED, run_id="run-1", detail=ASKED)
    services.catalogue.record_event(
        EventKind.GET_FINISHED, run_id="run-1", detail={"run_kind": "discovery", "status": "halted_by_budget"}
    )

    open_history(ui)
    ui.page.wait_for_selector("ol.history-events li")

    text = ui.text()
    assert "Asked for “Quiet interiors”" in text
    assert "A search stopped at the spending cap" in text
    # The raw status is not what a curator reads.
    assert "halted_by_budget" not in text


def test_a_get_opened_from_history_returns_to_history(ui, services):
    """History is not a run's default return, so the opener travels in the address."""
    services.catalogue.record_event(EventKind.GET_STARTED, run_id="run-1", detail=ASKED)
    open_history(ui)
    link = ui.page.get_by_role("link", name="“Quiet interiors”")
    assert link.get_attribute("href") == "#run/run-1?from=history"


def test_the_kinds_filter_by_link_and_say_which_is_shown(ui, services, work_with_an_image, the_wall):
    """A filtered history is an address, and the page names the filter in force."""
    work = work_with_an_image(title="Nighthawks")
    theme = services.display.add_theme(name="Winter")
    services.catalogue.archive_artwork(work.id)
    services.display.activate_theme(theme.id, wall_id=the_wall.id)

    open_history(ui)
    ui.page.wait_for_selector("ol.history-events li")
    assert len(rows(ui)) == 2

    walls = ui.page.locator("ul.history-kinds").get_by_role("link", name="Walls")
    assert walls.get_attribute("href") == "#history?kind=walls"
    walls.click()
    ui.page.wait_for_function("() => document.querySelectorAll('ol.history-events li').length === 1")

    assert rows(ui)[0].endswith(f"Hung Winter on {the_wall.name}")
    assert ui.page.locator("ul.history-kinds a[aria-current='page']").inner_text() == "Walls"
    # The request named the walls' kinds and only those.
    asked = [url for url in ui.requests_matching("/api/history") if "kind=" in url][-1]
    assert "kind=wall.hung" in asked
    assert "kind=work.archived" not in asked


def test_a_kind_with_nothing_yet_says_so_rather_than_showing_everything(ui, services, work_with_an_image):
    services.catalogue.archive_artwork(work_with_an_image(title="Nighthawks").id)
    open_history(ui, "#history?kind=verdicts")
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing of this kind has happened yet." in ui.text()
    assert "Nighthawks" not in ui.text()


def test_an_empty_history_says_what_it_records(ui):
    open_history(ui)
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing has happened yet." in ui.text()
    assert "nothing from before the history began is" in ui.text()


def test_one_walls_history_holds_only_that_wall(ui, services, the_wall):
    """Opened from a wall's card: what was hung there, and not what was hung elsewhere."""
    study = services.display.add_wall(name="Study")
    winter = services.display.add_theme(name="Winter")
    summer = services.display.add_theme(name="Summer")
    services.display.activate_theme(winter.id, wall_id=the_wall.id)
    services.display.activate_theme(summer.id, wall_id=study.id)

    open_history(ui, f"#history?wall={study.id}")
    ui.page.wait_for_selector("ol.history-events li")

    assert ui.page.locator("#view h1").inner_text() == "History of Study"
    assert [row.split("\t")[-1].split("\n")[-1] for row in rows(ui)] == ["Hung Summer on Study"]
    assert ui.page.get_by_role("link", name="Every wall's history").get_attribute("href") == "#history"


def test_paging_is_by_link_and_says_where_it_is(ui, services):
    for index in range(55):
        services.catalogue.record_event(EventKind.GET_STARTED, run_id=f"run-{index}", detail={"run_kind": "get", "works": 1})

    open_history(ui)
    ui.page.wait_for_selector("ol.history-events li")
    assert len(rows(ui)) == 50
    assert "1–50 of 55" in ui.text()
    older = ui.page.get_by_role("link", name="Older")
    assert older.get_attribute("href") == "#history?offset=50"
    older.click()
    ui.page.wait_for_selector("text=51–55 of 55")
    assert len(rows(ui)) == 5
    assert ui.page.get_by_role("link", name="Newer").count() == 1
    assert ui.page.get_by_role("link", name="Older").count() == 0


def test_a_selection_hung_reads_as_a_selection_not_its_made_up_name(ui, services, work_with_an_image, the_wall):
    work = work_with_an_image(title="Nighthawks")
    services.display.hang_selection([work.id], wall_id=the_wall.id)

    open_history(ui)
    ui.page.wait_for_selector("ol.history-events li")

    assert rows(ui)[0].endswith(f"Hung a selection of 1 work on {the_wall.name}")
    assert "Selection for" not in ui.text()


def test_a_get_of_chosen_works_says_how_many(ui, services):
    """A Get has no intent of its own: the curator chose its works, so it is named by how many."""
    services.catalogue.record_event(EventKind.GET_STARTED, run_id="run-1", detail={"run_kind": "get", "works": 2})
    ui.open("#history")
    stamp = ui.page.locator("ol.history-events li time").first
    stamp.wait_for()
    occurred = datetime.fromisoformat(stamp.get_attribute("datetime"))
    assert datetime.now(UTC) - occurred < timedelta(minutes=1)
    assert "Started a Get for 2 works" in ui.text()
