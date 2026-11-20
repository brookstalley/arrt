"""`?debug`: engineering detail shown only to whoever asks for it (ruling 1 of 2026-10-11).

Without the flag, no page shows a file path, a content hash, a rendition table,
a mat's hex, raw keys, or a plugin's id; with it, each shows where it always
did. The flag is the page's own query (`/?debug#work/<id>`), so the tests open
it that way and follow links inside the app to show it stays.
"""

import re

import pytest

from arrt.http.models import SourcePluginOut, SourcesOut
from arrt.persistence.records import MatMethod, RenditionKind

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect


@pytest.fixture
def a_prepared_work(work_with_an_image, service, settings, decodable_jpeg):
    """A work with a master on disk, a mat and a presentation master: every debug panel has something to show."""
    work = work_with_an_image("Nighthawks")
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


def _work_page(ui, work, *, debug: bool):
    ui.open(f"{'?debug' if debug else ''}#work/{work.id}")
    ui.page.wait_for_selector(".state-strip dl")
    ui.page.wait_for_selector("h2:text-is('Where it can be obtained')")


def _raw(fragment: str) -> re.Pattern:
    """A fragment as the page prints it, line breaks and all: a pattern, which sees what a string folds away."""
    return re.compile(r"\n".join(re.escape(line) for line in fragment.split("\n")))


#: What only debug shows on a Work page, each as the page would print it.
def _engineering(work):
    return [f"raw/{work.id}.jpg", "Content hash", "What has been rendered", "presentation_master", "Mat colour", "#27285b"]


def test_a_work_page_ends_at_what_a_person_can_act_on(ui, a_prepared_work):
    _work_page(ui, a_prepared_work, debug=False)

    # What stays: where it can be obtained, by the museum's name. First, so
    # the absences below are of a page that has painted what it keeps.
    expect(ui.view).to_contain_text("Art Institute of Chicago", use_inner_text=True)
    for fragment in _engineering(a_prepared_work):
        expect(ui.view, fragment).not_to_contain_text(_raw(fragment), use_inner_text=True)


def test_debug_shows_a_work_s_files_renditions_and_mat(ui, a_prepared_work):
    _work_page(ui, a_prepared_work, debug=True)

    for fragment in _engineering(a_prepared_work):
        expect(ui.view, fragment).to_contain_text(_raw(fragment), use_inner_text=True)


def test_the_flag_survives_following_links_inside_the_app(ui, a_prepared_work):
    ui.open("?debug#sources")
    ui.page.get_by_role("link", name="Artworks", exact=True).first.click()
    ui.page.locator(f'#view a[href^="#work/{a_prepared_work.id}"]').first.click()
    ui.page.wait_for_selector("h2:text-is('What has been rendered')")

    assert ui.page.evaluate("() => location.search") == "?debug"


def test_status_keeps_its_raw_fields_for_debug(ui, a_health_reading):
    reading = a_health_reading()
    ui.serve("**/api/health", reading)

    ui.open("#health")
    ui.page.wait_for_selector("h1")
    ui.page.wait_for_selector(".wall-reading")
    expect(ui.page.locator(".raw-details")).to_have_count(0)

    ui.open("?debug#health")
    ui.page.wait_for_selector(".raw-details")
    # The server's own sentence for the wall, which names the file it read, is
    # debug's (#359): beside the curator's "Last heard from", not instead of it.
    raw = ui.page.locator(".wall-reading .raw-sentence")
    expect(raw).to_have_count(1)
    # The server's sentence itself, word for word. Until 2026-11-19 this looked
    # for "display plane" in it, the server's wording then; the server now says
    # "This wall's Player last reported …" (`HeartbeatReading.describe`), and the
    # payload the suite serves says what the server would.
    expect(raw).to_have_text(reading["walls"][0]["heartbeat"]["description"], use_inner_text=True)
    expect(ui.page.locator(".wall-reading .reading-sentence")).to_have_text(
        re.compile("^" + re.escape("Last heard from ")), use_inner_text=True
    )


def test_sources_names_a_plugin_s_id_package_and_interface_only_in_debug(ui, a_source_reading):
    listing = SourcesOut(
        interface_version="1.1",
        sources=[SourcePluginOut(**a_source_reading(name="artic", distribution="arrt-sources", version="0.4.1"))],
    ).model_dump()
    ui.serve("**/api/sources", listing)

    ui.open("#sources")
    entry = ui.page.locator(".source-entry")
    entry.wait_for()
    expect(entry).to_contain_text("Art Institute of Chicago", use_inner_text=True)
    for fragment in ("Plugin\nartic", "arrt-sources 0.4.1", "Interface"):
        expect(entry, fragment).not_to_contain_text(_raw(fragment), use_inner_text=True)

    ui.open("?debug#sources")
    entry = ui.page.locator(".source-entry")
    entry.wait_for()
    for fragment in ("Plugin\nartic", "arrt-sources 0.4.1", "Interface"):
        expect(entry, fragment).to_contain_text(_raw(fragment), use_inner_text=True)


def test_a_get_shows_the_model_s_reading_of_the_request_only_in_debug(ui):
    from payloads import a_candidate, a_candidate_page, a_card, a_run, a_run_view, a_spend

    from arrt.persistence.discovery_records import RunStatus

    reading = "Extract specific, named artworks; cite each with a domain-based markdown link."
    run = a_run(status=RunStatus.COMPLETED.value, is_terminal=True, strategy=reading)
    work = a_candidate()
    ui.serve("**/api/runs/run-1", a_run_view(run=run, works=[work]))
    ui.serve("**/api/runs/run-1/candidates*", a_candidate_page([a_card(work=work)], run=run))
    ui.serve("**/api/runs/run-1/spend", a_spend())
    ui.serve_image("**/api/candidate-images/**")

    ui.open("#get/run-1")
    ui.page.wait_for_selector("#view section.asked-for")
    expect(ui.view).not_to_contain_text("Extract specific, named artworks", use_inner_text=True)

    ui.open("?debug#get/run-1")
    ui.page.wait_for_selector("#view section.asked-for")
    expect(ui.view).to_contain_text(f"How it read the request: {reading}", use_inner_text=True)


def test_status_still_says_what_failed_on_a_wall_without_debug(ui, a_health_reading, a_wall_reading):
    """The failure rows `observability-strategy.md` gives Status a reader for are not engineering detail.

    Rewritten in audit wave 2b (chunk 31). It asserted "Television: Not
    reachable" and "Label panel: Not working", read from `television_reachable`
    and `label_surface_working`, which the contract marks superseded (1.2.0):
    the screen's state is now the wall's display state as the server states it
    (a Player that names no work and says nothing of its screen is `unreachable`,
    "Not known"), and a label panel is an output of its Player, said with the
    Player's other outputs, where one not connected is said as one. The last
    error is still the wall's row.
    """
    wall = a_wall_reading(
        reported={
            "television_reachable": False,
            "television_showing_art": None,
            "has_label_surface": True,
            "label_surface_working": False,
            "last_error": "the television refused the connection",
        }
    )
    ui.serve("**/api/health", a_health_reading(walls=[wall], player={"labels": [("epd-0", False)]}))

    ui.open("#health")
    panel = ui.page.locator(".wall-reading")
    panel.wait_for()
    expect(panel.locator(".wall-state")).to_have_text(re.compile(r"Not known$"), use_inner_text=True)
    expect(panel).to_contain_text(_raw("Last error\nthe television refused the connection"), use_inner_text=True)
    expect(panel).not_to_contain_text("Television", use_inner_text=True)
    label = ui.page.locator(".players-reading li[data-kind='label']")
    expect(label).to_have_text("Label panel epd-0 · ○ not connected", use_inner_text=True)
    expect(ui.page.locator(".raw-details")).to_have_count(0)


def test_a_wall_reporting_no_failure_says_so_in_words(ui, a_health_reading, a_wall_reading):
    """The screen's state is the display state, never the superseded `television_showing_art` beside it.

    Acceptance 4 of audit wave 2b's chunk 31: a heartbeat claiming the
    television shows art, with `display_state: dark`, reads "Screen off". It
    asserted "Television: Showing art" from that superseded field until then.
    """
    wall = a_wall_reading(
        reported={
            "television_reachable": True,
            "television_showing_art": True,
            "has_label_surface": False,
            "label_surface_working": None,
            "last_error": None,
            "schema": {"major": 1, "minor": 3},
            "display_state": {"state": "dark", "work_id": None, "since": "2026-08-12T09:00:00+00:00"},
        }
    )
    reading = a_health_reading(walls=[wall])
    assert reading["walls"][0]["display_state"]["state"] == "dark"
    ui.serve("**/api/health", reading)

    ui.open("#health")
    panel = ui.page.locator(".wall-reading")
    panel.wait_for()
    expect(panel.locator(".wall-state")).to_have_text(re.compile(r"^○\s*Screen off$"), use_inner_text=True)
    expect(panel).not_to_contain_text("Showing art", use_inner_text=True)
    expect(panel).not_to_contain_text("Television", use_inner_text=True)
    # No label panel, so no row about one; and no error, so no error row.
    expect(panel).not_to_contain_text("Label panel", use_inner_text=True)
    expect(panel).not_to_contain_text("Last error", use_inner_text=True)


def test_every_page_still_paints_when_the_source_names_cannot_be_read(ui, a_prepared_work):
    """The client waits for `/api/sources` before its first paint; a failure there must cost only the names."""
    ui.serve("**/api/sources", [(500, {"detail": "down"})])

    ui.open(f"#work/{a_prepared_work.id}")
    ui.page.wait_for_selector("h2:text-is('Where it can be obtained')")
    # A built-in source is still named by its museum.
    expect(ui.view).to_contain_text("Art Institute of Chicago", use_inner_text=True)
