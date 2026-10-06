"""Settings › Sources, in a real browser: every installed plugin, where it came from, what it provides.

The JSON tests assert that `GET /api/sources` carries each plugin's package,
version and parts. Whether the page says them in words a curator reads, keeps a
declined plugin beside the loaded ones, and says an unknown in words rather than
leaving a blank, is not expressible as JSON.
"""

import pytest

from arrt.http.models import SourcePluginOut, SourcesOut

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


def a_listing(sources, interface_version="1.1"):
    """`GET /api/sources` as the API's own model defines it."""
    return SourcesOut(interface_version=interface_version, sources=[SourcePluginOut(**s) for s in sources]).model_dump()


def panels(ui):
    ui.page.wait_for_selector("h2:has-text('Sources')")
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

    ui.open("#sources")
    entries = panels(ui)

    assert entries.locator("h3").all_inner_texts() == ["commons", "artic", "moma", "wikidata"]
    moma = entries.nth(2)
    assert "arrt-sources 0.4.1" in moma.inner_text()
    assert "Finds images of a work; reads the addresses it claims." in moma.inner_text()
    assert "3 of 4" in moma.inner_text()
    artic = entries.nth(1)
    # Declined is said with its reason, and a plugin that did not load says it provides nothing.
    assert "ARTIC_USER_AGENT is unset" in artic.inner_text()
    assert "Nothing here, because it did not load." in artic.inner_text()
    assert "Finds pages about a work, for other plugins to read." in entries.nth(3).inner_text()
    assert "This Arrt provides plugin interface 1.1." in ui.page.locator("main").inner_text()


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

    ui.open("#sources")
    gone, future = panels(ui).nth(0).inner_text(), panels(ui).nth(1).inner_text()

    assert "Not known: no installed package names this plugin alone." in gone
    assert "Not known: it failed before saying which interface it was written for." in gone
    assert "Written for interface 2; this Arrt provides 1." in future
    assert "Written for interface 1, which this Arrt provides." not in future


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

    ui.open("#sources")
    entry = panels(ui).nth(0)

    assert entry.locator("h3").inner_text() == "<img src=x onerror=window.__ran=1>"
    assert "<i>pkg</i> 0.3.0" in entry.inner_text()
    assert ui.page.evaluate("window.__ran") is None
    assert entry.locator("img, b, i").count() == 0


def test_no_plugin_installed_is_said(ui):
    ui.serve("**/api/sources", a_listing([]))

    ui.open("#sources")
    ui.page.wait_for_selector("h2:has-text('Sources')")

    assert "No source plugin is installed" in ui.page.locator("main").inner_text()


def test_the_page_is_under_settings_after_clients(ui):
    ui.serve("**/api/sources", a_listing([]))

    ui.open("#sources")
    ui.page.wait_for_selector("h2:has-text('Sources')")

    links = ui.page.locator("nav a").all_inner_texts()
    assert links.index("Sources") == links.index("Clients") + 1
