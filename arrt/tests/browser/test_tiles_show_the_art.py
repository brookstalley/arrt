"""Library tiles show the work itself; the Work page shows the wall render.

The owner's ruling on tiles (`ia-proposal.md` § Rulings 2026-10-07, ruling 7):
a tile is the work at its own aspect, never the wall render's mat and bars, and
the wall render is the Work page's, where it is the subject. Every work here is
a **portrait master under a landscape canvas**, so a tile showing the canvas and
a tile showing the work cannot be mistaken for each other by their shape — the
picture the browser actually decoded is what is measured, not the address it
asked for.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import RenditionKind


@pytest.fixture
def composed(work_with_an_image, service, settings, decodable_jpeg):
    """A held work whose master is portrait and whose wall render is 16:9."""

    def _composed(title="Nighthawks"):
        # Well over the quality minimum, so its fit draws no badge.
        work = work_with_an_image(title, width=3000, height=4000)
        rendered = f"ready/{work.id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=work.id,
            kind=RenditionKind.TV_DISPLAY,
            target_width=3840,
            target_height=2160,
            path=rendered,
        )
        return work

    return _composed


def _decoded_shape(locator):
    locator.wait_for()
    locator.evaluate(
        "img => img.complete && img.naturalWidth ? null : new Promise(r => img.addEventListener('load', r, { once: true }))"
    )
    return locator.evaluate("img => [img.naturalWidth, img.naturalHeight]")


def test_an_artworks_tile_is_the_work_at_its_own_aspect(ui, composed):
    work = composed()
    ui.open("#collection?density=catalogue")
    width, height = _decoded_shape(ui.page.locator(f"li.card[data-artwork='{work.id}'] .card-image img"))
    assert height > width, "the tile shows the 16:9 wall render, not the portrait work"


def test_a_posters_tile_is_the_work_at_its_own_aspect(ui, composed):
    work = composed()
    ui.open("#collection?density=contact")
    width, height = _decoded_shape(ui.page.locator(f"li.tile[data-artwork='{work.id}'] .card-image img"))
    assert height > width


def test_the_work_page_shows_the_wall_render_larger_than_a_tile(ui, composed):
    work = composed()
    ui.open(f"#work/{work.id}")
    width, height = _decoded_shape(ui.page.locator(".work-hero img.work-picture"))
    assert width / height == pytest.approx(3840 / 2160, abs=0.02), "the Work page lost the wall render"
    assert width > 480, "the Work page draws a tile-sized picture across its column"


def test_a_tile_carries_no_badge_that_says_nothing(ui, composed, work_with_an_image):
    """Meeting the minimum and the picture's source say nothing on a tile; a fit that is news still shows.

    Two works, so the absence is not the badge row failing to draw: the small
    one (below the minimum at 400 px) keeps its fit badge in the same grid.
    """
    big = composed("Nighthawks")
    small = work_with_an_image("Automat", width=400, height=300)
    ui.open("#collection?density=catalogue")
    ui.page.wait_for_selector(f"li.card[data-artwork='{small.id}'] .card-footer .badge")

    verdict = ui.page.evaluate(f"() => fetch('/api/works/{big.id}').then(r => r.json()).then(d => d.work.fit.verdict)")
    assert verdict == "meets_minimum", "the fixture no longer makes the case this test is about"
    footer = ui.page.locator(f"li.card[data-artwork='{big.id}'] .card-footer").inner_text()
    for word in ("minimum", "wall render", "master image"):
        assert word not in footer, f"the tile still says {word!r}"
    small_footer = ui.page.locator(f"li.card[data-artwork='{small.id}'] .card-footer").inner_text()
    assert small_footer.strip(), "a fit worth saying went with the ones that say nothing"
    assert "below minimum" in small_footer
