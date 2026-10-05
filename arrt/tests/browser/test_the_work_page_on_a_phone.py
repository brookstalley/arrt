"""The Work page fits a phone, whatever its tables hold.

A source's URL and a rendition's file path are single unbroken words, and a
table sizes itself to its widest word. On a 375 px screen the owner's held
Rothko made the whole page 333 px wider than the screen (measured 2026-10-01
against a copy of their catalogue), so every line of the page scrolled sideways
rather than one table. The tables now scroll inside their own panel.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

#: As long as a real museum URL with a title slug in it, and unbroken.
LONG_URL = "https://www.artic.edu/artworks/100472/untitled-purple-white-and-red-" + "x" * 60


def test_a_long_source_url_does_not_widen_the_page(ui, service):
    work = service.add_artwork(title="Untitled (Purple, White, and Red)", date_created="1953")
    service.add_source(
        artwork_id=work.id,
        url=LONG_URL,
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    ui.page.set_viewport_size({"width": 375, "height": 740})
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_selector(f"#view td:has-text('{LONG_URL[:40]}')")

    assert ui.page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth") <= 0
