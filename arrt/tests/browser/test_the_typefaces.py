"""Both typefaces load, and the page is drawn in them.

`app.css` declares Newsreader and Instrument Sans with `font-display: swap`,
which draws the fallback face while a font loads and keeps it if the font
never arrives. So a missing file, a wrong `url()` or a refused request gives a
page that works, in Georgia and the system sans. No other test can tell, because
the text and the layout are right either way. What this test reads is the
browser's own record of each face it tried to load.

Only the Latin, upright faces are required. The browser fetches a face only
when a page uses a character in its range in that style, so an italic or Latin
Extended face that stays unloaded on this page is correct, not a failure.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

FAMILIES = ("Newsreader", "Instrument Sans")


def _faces(ui) -> list[dict]:
    return ui.page.evaluate("""async () => {
          await document.fonts.ready;
          return [...document.fonts].map((face) => ({
            family: face.family.replace(/^"|"$/g, ''),
            style: face.style,
            latin: face.unicodeRange.startsWith('U+0-FF'),
            status: face.status,
          }));
        }""")


def test_both_typefaces_load_on_a_page(ui):
    ui.open("#collection")
    ui.page.wait_for_selector("#view h1")
    faces = _faces(ui)
    for family in FAMILIES:
        upright = [f for f in faces if f["family"] == family and f["style"] == "normal" and f["latin"]]
        assert len(upright) == 1, f"{family}: expected one Latin upright face, found {upright}"
        assert upright[0]["status"] == "loaded", f"{family} did not load, so the page is in its fallback face"


def test_a_page_name_is_set_in_the_serif_and_its_text_in_the_sans(ui):
    ui.open("#collection")
    ui.page.wait_for_selector("#view h1")
    heading, body = ui.page.evaluate(
        "() => [getComputedStyle(document.querySelector('#view h1')).fontFamily," " getComputedStyle(document.body).fontFamily]"
    )
    assert heading.strip('"').startswith("Newsreader")
    assert body.strip('"').startswith("Instrument Sans")
