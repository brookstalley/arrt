"""Library tiles show the work itself, and so does the Work page, larger.

The owner's ruling on tiles (`ia-proposal.md` § Rulings 2026-10-07, ruling 7):
a tile is the work at its own aspect, with no mat. The Work page's picture is
the same work, drawn from the master too, since each wall's Player draws its
own mat. Every work here is a **portrait master**, so a picture in a screen's
16:9 shape cannot be mistaken for the work — the picture the browser actually
decoded is what is measured, not the address it asked for.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


@pytest.fixture
def composed(work_with_an_image):
    """A held work whose master is portrait."""

    def _composed(title="Nighthawks"):
        # Well over the quality minimum, so its fit draws no badge.
        return work_with_an_image(title, width=3000, height=4000)

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
    assert height > width, "the tile is not the portrait work"


def test_a_posters_tile_is_the_work_at_its_own_aspect(ui, composed):
    work = composed()
    ui.open("#collection?density=contact")
    width, height = _decoded_shape(ui.page.locator(f"li.tile[data-artwork='{work.id}'] .card-image img"))
    assert height > width


def test_the_work_page_shows_the_work_at_its_own_aspect_larger_than_a_tile(ui, composed):
    work = composed()
    ui.open(f"#work/{work.id}")
    width, height = _decoded_shape(ui.page.locator(".work-hero img.work-picture"))
    assert height / width == pytest.approx(4000 / 3000, abs=0.02), "the Work page is not the portrait work"
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
