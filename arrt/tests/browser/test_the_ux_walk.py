"""`tools/ux_walk.py` against the suite's real server: it walks, photographs, and cannot write.

The harness is pointed at the operator's real library, so the guard that keeps
it read-only is the claim that matters most here, and it is tested by asking the
server afterwards whether the write arrived — not by trusting the abort.
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above


def _themes(server_url: str) -> list[str]:
    """Asked of the server directly, outside any guarded browser context."""
    return [theme["name"] for theme in httpx.get(f"{server_url}/api/themes", timeout=10).json()["themes"]]


def test_a_write_from_the_page_is_refused_and_never_reaches_the_server(browser, server_url):
    context = browser.new_context()
    refused: list[dict] = []
    ux_walk.guard_writes(context, refused)
    page = context.new_page()
    page.goto(f"{server_url}/")

    outcome = page.evaluate("""async () => {
          try {
            await fetch('/api/themes', {method: 'POST', headers: {'content-type': 'application/json'},
                                        body: JSON.stringify({name: 'Written by the walk'})});
            return 'sent';
          } catch (failure) { return 'refused'; }
        }""")
    context.close()

    assert outcome == "refused"
    assert [entry["method"] for entry in refused] == ["POST"]
    assert refused[0]["url"].endswith("/api/themes")
    assert "Written by the walk" not in _themes(server_url)


def test_a_read_passes_through_the_guard(browser, server_url):
    """The member that makes the refusal test falsifiable: a guard refusing everything would pass it."""
    context = browser.new_context()
    refused: list[dict] = []
    ux_walk.guard_writes(context, refused)
    page = context.new_page()
    page.goto(f"{server_url}/")

    status = page.evaluate("async () => (await fetch('/api/themes')).status")
    context.close()

    assert status == 200
    assert refused == []


def test_the_walk_visits_every_declared_screen_and_writes_its_sheet(browser, server_url, tmp_path):
    inventory = ux_walk.run_walk(
        browser, server_url, tmp_path, scan_accessibility=False, variants=[("phone", "dark")], clicks_per_page=0
    )

    declared = ux_walk.declared_routes(ux_walk.APP_JS.read_text(encoding="utf-8"))
    visits = inventory["visits"]
    visited_routes = {fragment.lstrip("#").split("?")[0].split("/")[0] for fragment in visits}
    summary = inventory["summary"]

    # Every declared screen is either photographed or named as never visited — never silently absent.
    assert set(declared) == visited_routes | set(summary["declared_never_visited"])
    # The shell's skip link (`href="#view"`) is an anchor, not a screen nobody declared.
    assert summary["reached_not_declared"] == []
    # A screen needing no id is always reachable by address, so it is always photographed.
    assert {key for key, route in declared.items() if route.detail != "required"} <= visited_routes

    home = [visit for visit in visits.values() if visit["reached_by"] == "home"]
    assert len(home) == 1
    assert home[0]["depth"] == 0
    assert home[0]["address"] == "#collection"

    for visit in visits.values():
        assert [capture["variant"] for capture in visit["captures"]] == ["phone-dark"]
        capture = visit["captures"][0]
        assert (tmp_path / capture["image"]).stat().st_size > 0
        # Not scanned, and saying so — a skipped scan never reads as a clean one.
        assert capture["accessibility"] == "not run: --no-axe"

    assert summary["refused_on_load"] == []
    sheet = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "phone-dark" in sheet
    assert "Synthetic corpus" not in sheet


def test_a_screen_reached_only_by_address_is_marked_so(browser, server_url, tmp_path):
    """`#search` has no link to it until something is typed; the walk still photographs it, and says how."""
    inventory = ux_walk.run_walk(
        browser,
        server_url,
        tmp_path,
        scan_accessibility=False,
        variants=[("desktop", "light")],
        requested=["#search?q=night"],
        clicks_per_page=0,
    )

    requested = inventory["visits"]["#search?q=night"]
    assert requested["reached_by"] == "requested"
    by_address = [v for v in inventory["visits"].values() if v["reached_by"] == "address"]
    assert by_address  # `wanted` is hidden until something is wanted, so it is only ever reached by address
    assert all(v["address"].lstrip("#") in inventory["summary"]["declared_not_reached_by_link"] for v in by_address)


def test_a_work_opened_from_artworks_is_reached_by_a_link(browser, server_url, tmp_path):
    """Artworks opens a work with a link (`information-architecture.md` § Direction),
    so the walk records it as reached by link and not as reached only by script.

    This test pinned the opposite while Artworks opened works with a button that
    called the router; the norm ruled that a defect and the client was migrated.
    """
    inventory = ux_walk.run_walk(
        browser, server_url, tmp_path, scan_accessibility=False, variants=[("desktop", "light")], clicks_per_page=40
    )

    works = [visit for fragment, visit in inventory["visits"].items() if fragment.startswith("#work/")]
    assert works
    assert {visit["reached_by"] for visit in works} == {"link"}
    assert "work" not in inventory["summary"]["reached_only_by_button"]


def test_without_clicks_a_work_is_still_reached(browser, server_url, tmp_path):
    """The probe off, and the works are reached anyway: by the links alone."""
    inventory = ux_walk.run_walk(
        browser, server_url, tmp_path, scan_accessibility=False, variants=[("desktop", "light")], clicks_per_page=0
    )

    assert [fragment for fragment in inventory["visits"] if fragment.startswith("#work/")]
    assert "work" not in inventory["summary"]["declared_never_visited"]


#: A stand-in for axe-core with axe's own result shape, so the three states the
#: scan reports can be told apart without the network the real one is fetched from.
FAKE_AXE = """window.axe = {run: async () => ({violations: document.querySelector('img:not([alt])')
  ? [{id: 'image-alt', impact: 'critical', help: 'Images must have alternative text', nodes: [{target: ['img']}]}]
  : []})};"""


def test_the_scan_reports_clean_violations_and_not_run_as_three_states(browser):
    page = browser.new_page()

    page.set_content("<main><img src='x.png' alt='A harbour'></main>")
    clean = ux_walk.scan(page, FAKE_AXE, "unused")
    page.set_content("<main><img src='x.png'></main>")
    found = ux_walk.scan(page, FAKE_AXE, "unused")
    skipped = ux_walk.scan(page, None, "not run: axe-core could not be fetched")
    page.close()

    assert clean == ("clean", [])
    assert found[0] == "violations"
    assert [(v["id"], v["impact"], v["nodes"], v["targets"]) for v in found[1]] == [("image-alt", "critical", 1, ["img"])]
    assert skipped == ("not run: axe-core could not be fetched", [])


def test_a_screen_that_never_paints_is_recorded_blank_not_fatal(browser):
    page = browser.new_page()
    page.set_content("<main id='view'></main>")

    state = ux_walk._settle(page, paint_ms=300)
    page.close()

    assert state == "blank"
