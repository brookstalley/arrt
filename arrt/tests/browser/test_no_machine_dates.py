"""No screen shows a machine timestamp outside a Details disclosure.

`ux-review-2026-10.md` finding 20: To review and History showed
`2026-10-05T14:46:52.225416+00:00`, wrapping every row. Every moment a screen
shows is written by `core/dates.js` as a readable date and how long ago; the
instant itself lives only in a `<time datetime>`, which nobody reads, or inside
a `<details>`, where Status keeps its raw fields on purpose.

Each screen here is reached with real records carrying real timestamps — a Get
and its works, a verdict and an archive in History, a wanted work, a
conversation, a client with a token — and Status from a reading whose heartbeat
and backup both carry instants. The whole visible page is read, sidebar and
banner included, with every `<details>` left out.
"""

import re

import pytest

from arrt.persistence.discovery_records import InitiatedBy

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")

#: The page's text, as a reader meets it, with every Details disclosure taken
#: out — open or closed, since what is inside one is there to be raw.
READ_OUTSIDE_DETAILS = """() => {
  const copy = document.body.cloneNode(true);
  for (const node of copy.querySelectorAll('details, script, style, [hidden]')) node.remove();
  return copy.innerText || copy.textContent;
}"""


@pytest.fixture
def records(services, discovery, conversation, run, resolved_work, propose, ready_work):
    """Something dated on every screen that shows a date."""
    resolved_work("Nighthawks")
    wanted = propose("Lobster Telephone")
    discovery.record_resolution(wanted.id)
    discovery.want(wanted.id)
    work = ready_work(title="Christina's World")
    services.catalogue.archive_artwork(work.id)
    services.catalogue.restore_artwork(work.id)
    services.display.exclude_work(work.id, wall_id=services.display.survey_walls()[0].wall.id)
    conversation.start()
    client = services.clients.add_client(name="Hall Pi")
    services.access.issue(client.id)
    other = discovery.start_discovery_run(intent_text="Quiet interiors", initiated_by=InitiatedBy.WEB_UI)
    return {"run": run.id, "other": other.id, "work": work.id}


def screens(records):
    return [
        "#to_review",
        "#queue",
        "#history",
        "#wanted",
        "#discover",
        "#clients",
        "#walls",
        "#health",
        f"#get/{records['run']}",
        f"#get/{records['other']}",
        f"#review/{records['run']}",
        f"#work/{records['work']}",
    ]


def test_no_screen_shows_an_iso_timestamp_outside_details(ui, records, a_health_reading):
    reading = a_health_reading()
    reading["walls"][0]["heartbeat"]["reported"] = {
        "reported_at": "2026-08-12T09:14:02+00:00",
        "current_work_id": records["work"],
    }
    ui.serve("**/api/health", reading)

    seen = {}
    for fragment in screens(records):
        ui.open(fragment)
        ui.page.wait_for_selector("#view h1")
        # Every request a screen makes after its heading, settled.
        ui.page.wait_for_load_state("networkidle")
        ui.page.wait_for_timeout(300)
        text = ui.page.evaluate(READ_OUTSIDE_DETAILS)
        found = ISO.findall(text)
        if found:
            seen[fragment] = found

    assert seen == {}, f"machine timestamps on screen, outside any Details: {seen}"


def test_the_check_sees_an_iso_timestamp_where_one_is_shown(ui, records):
    """The member that makes the check falsifiable: the same reader finds one put on the page."""
    ui.open("#queue")
    ui.page.wait_for_selector("#view h1")
    ui.page.evaluate("() => document.querySelector('#view').append('2026-10-05T14:46:52.225416+00:00')")

    assert ISO.search(ui.page.evaluate(READ_OUTSIDE_DETAILS))


def test_status_keeps_the_raw_instant_behind_details(ui, records, a_health_reading):
    """The raw fields are not lost, only put away: they are inside the disclosure."""
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    ui.page.wait_for_selector("#view h1:text-is('Status')")

    raw = ui.page.locator("details.raw-details").first
    assert ISO.search(raw.text_content())
    assert raw.locator("summary").inner_text() == "Details"
