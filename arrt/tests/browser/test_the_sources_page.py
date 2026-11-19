"""Settings › Sources, in a real browser: every installed plugin, where it came from, what it provides.

The JSON tests assert that `GET /api/sources` carries each plugin's package,
version and parts. Whether the page says them in words a curator reads, keeps a
declined plugin beside the loaded ones, and says an unknown in words rather than
leaving a blank, is not expressible as JSON.
"""

import re

import pytest

from arrt.http.models import SourcePluginOut, SourcesOut

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect


def a_listing(sources, interface_version="1.1"):
    """`GET /api/sources` as the API's own model defines it."""
    return SourcesOut(interface_version=interface_version, sources=[SourcePluginOut(**s) for s in sources]).model_dump()


def panels(ui):
    ui.page.wait_for_selector("h1:has-text('Sources')")
    return ui.page.locator(".source-entry")


def test_every_installed_plugin_is_listed_in_order_with_its_package_and_version(ui, a_source_reading):
    ui.serve(
        "**/api/sources",
        a_listing(
            [
                a_source_reading(name="commons"),
                a_source_reading(
                    name="artic",
                    state="declined",
                    reason="ARTIC_USER_AGENT is unset, and the Art Institute is never asked anonymously",
                ),
                a_source_reading(name="moma", distribution="arrt-sources", version="0.4.1"),
                a_source_reading(name="wikidata", provides=["finds_pages"]),
            ]
        ),
    )

    # What this checks shows only in debug (ruling 1 of 2026-10-11).
    ui.open("?debug#sources")
    entries = panels(ui)

    # Each by the museum's name, and one this client has no name for by its own id.
    expect(entries.locator("h2")).to_have_text(
        ["Wikimedia Commons", "Art Institute of Chicago", "moma", "Wikidata"], use_inner_text=True
    )
    # The label and its value stand on two lines: a pattern, which sees the line break a string would fold away.
    expect(entries.nth(1)).to_contain_text(re.compile("Plugin\nartic"), use_inner_text=True)
    moma = entries.nth(2)
    expect(moma).to_contain_text("arrt-sources 0.4.1", use_inner_text=True)
    expect(moma).to_contain_text("Finds images of a work; reads the addresses it claims.", use_inner_text=True)
    expect(moma).to_contain_text("3 of 4", use_inner_text=True)
    artic = entries.nth(1)
    # Declined is said with its reason, and a plugin that did not load says it provides nothing.
    expect(artic).to_contain_text("ARTIC_USER_AGENT is unset", use_inner_text=True)
    expect(artic).to_contain_text("Nothing here, because it did not load.", use_inner_text=True)
    expect(entries.nth(3)).to_contain_text("Finds pages about a work, for other plugins to read.", use_inner_text=True)
    expect(ui.page.locator("main")).to_contain_text("This Arrt provides plugin interface 1.1.", use_inner_text=True)


def test_what_could_not_be_read_is_said_in_words(ui, a_source_reading):
    ui.serve(
        "**/api/sources",
        a_listing(
            [
                a_source_reading(
                    name="gone",
                    state="failed",
                    reason="it could not be imported: ModuleNotFoundError",
                    distribution=None,
                    version=None,
                    api_major=None,
                ),
                a_source_reading(name="future", state="failed", reason="it was written for source interface 2", api_major=2),
            ]
        ),
    )

    # What this checks shows only in debug (ruling 1 of 2026-10-11).
    ui.open("?debug#sources")
    gone, future = panels(ui).nth(0), panels(ui).nth(1)

    expect(gone).to_contain_text("Not known: no installed package names this plugin alone.", use_inner_text=True)
    expect(gone).to_contain_text("Not known: it failed before saying which interface it was written for.", use_inner_text=True)
    expect(future).to_contain_text("Written for interface 2; this Arrt provides 1.", use_inner_text=True)
    expect(future).not_to_contain_text("Written for interface 1, which this Arrt provides.", use_inner_text=True)


def test_a_plugins_text_is_shown_as_text(ui, a_source_reading):
    """A plugin's name, package and reason are text a third party wrote."""
    ui.serve(
        "**/api/sources",
        a_listing(
            [
                a_source_reading(
                    name="<img src=x onerror=window.__ran=1>",
                    state="declined",
                    reason="<b>bold</b>",
                    distribution="<i>pkg</i>",
                )
            ]
        ),
    )

    # What this checks shows only in debug (ruling 1 of 2026-10-11).
    ui.open("?debug#sources")
    entry = panels(ui).nth(0)

    expect(entry.locator("h2")).to_have_text("<img src=x onerror=window.__ran=1>", use_inner_text=True)
    expect(entry).to_contain_text("<i>pkg</i> 0.3.0", use_inner_text=True)
    assert ui.page.evaluate("window.__ran") is None
    expect(entry.locator("img, b, i")).to_have_count(0)


def test_no_plugin_installed_is_said(ui):
    ui.serve("**/api/sources", a_listing([]))

    ui.open("#sources")
    ui.page.wait_for_selector("h1:has-text('Sources')")

    expect(ui.page.locator("main")).to_contain_text("No source plugin is installed", use_inner_text=True)


def test_the_page_is_under_settings_after_players(ui):
    ui.serve("**/api/sources", a_listing([]))

    ui.open("#sources")
    ui.page.wait_for_selector("h1:has-text('Sources')")

    # The listing is a list of items: the one after Players' is Sources'.
    expect(ui.page.locator("nav a[data-view='clients']")).to_have_text("Players", use_inner_text=True)
    expect(ui.page.locator("nav ul.pages li:has(a[data-view='clients']) + li a")).to_have_text("Sources", use_inner_text=True)


def test_a_plugin_that_names_its_museum_is_called_by_it_on_every_page(ui, a_source_reading, service):
    """1.4: a plugin from elsewhere says which museum it answers for, and the client learns it at start."""
    from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

    ui.serve("**/api/sources", a_listing([a_source_reading(name="moma", museum="The Museum of Modern Art")]))
    work = service.add_artwork(title="The Starry Night")
    service.add_source(
        artwork_id=work.id,
        url="https://www.moma.org/collection/works/79802",
        provider="moma",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.UNKNOWN,
        is_primary=True,
    )

    ui.open("#sources")
    expect(panels(ui).locator("h2")).to_have_text(["The Museum of Modern Art"], use_inner_text=True)

    ui.open(f"#work/{work.id}")
    obtained = ui.page.locator(".panel", has=ui.page.locator("h2:text-is('Where it can be obtained')"))
    obtained.wait_for()
    expect(obtained).to_contain_text("The Museum of Modern Art", use_inner_text=True)
    # The id on a line of its own is the plugin's name shown raw: a pattern, which sees the line break.
    expect(obtained).not_to_contain_text(re.compile("moma\n"), use_inner_text=True)
