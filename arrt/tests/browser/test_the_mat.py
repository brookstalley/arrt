"""The Work page shows the work inside its mat, as a wall shows it (#346).

The owner's ruling of 2026-10-07: the Work page shows the work as a wall does,
mat and all. The server composes no canvas, so the browser draws the mat by
the rule every Player draws by (`player-contract.md` § Layout), from
`core/mat.js`. The rule's numbers are not copied here: the module is run
against the contract's own vectors, and the page is measured against what
those vectors require of a screen with no known density.
"""

import json
import math
from pathlib import Path

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.library.acquisition.mat import MAT_PRESETS, derive
from arrt.persistence.records import MatMethod

VECTORS = json.loads(
    (Path(__file__).resolve().parents[3] / "contract" / "vectors" / "mat-geometry.json").read_text(encoding="utf-8")
)

#: The colour current on the work, and the older one it superseded.
CURRENT = "#27285b"
OLDER = "#5a3d2b"


def run_layout(ui, vector):
    """One vector's input through the browser's own module."""
    given = vector["input"]
    return ui.page.evaluate(
        """async (given) => {
            const { matLayout } = await import('/static/core/mat.js');
            return matLayout({
              screen: { width: given.screen.width_px, height: given.screen.height_px },
              work: { width: given.work.width_px, height: given.work.height_px },
              mode: given.mat_mode,
              pixelsPerInch: given.pixels_per_inch,
              matWidthInches: given.mat_width_inches,
              bottomWeight: given.bottom_weight,
            });
        }""",
        given,
    )


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=[v["name"] for v in VECTORS["vectors"]])
def test_the_module_draws_every_contract_vector(ui, seeded_service, vector):
    """Exact, though the contract allows a Player one pixel: this is a port of
    the reference Player's arithmetic, so a pixel off is a porting fault."""
    ui.open("#walls")
    assert run_layout(ui, vector) == vector["expect"]


def test_the_modules_constants_are_the_contracts(ui, seeded_service):
    ui.open("#walls")
    width, weight = ui.page.evaluate(
        "async () => { const m = await import('/static/core/mat.js'); return [m.RELATIVE_MAT_WIDTH, m.BOTTOM_WEIGHT]; }"
    )
    assert width == VECTORS["relative_width"]
    no_density = [v["input"] for v in VECTORS["vectors"] if v["input"]["pixels_per_inch"] is None]
    assert no_density, "the vectors no longer hold a screen of unknown density"
    assert {given["bottom_weight"] for given in no_density} == {weight}


@pytest.fixture
def matted(work_with_an_image, service):
    """A work with a current mat colour that superseded another."""

    def _matted(width, height):
        work = work_with_an_image(f"A work {width} by {height}", width=width, height=height)
        service.record_mat_color(artwork_id=work.id, hex_rgb=OLDER, method=MatMethod.VISION_MODEL)
        service.record_mat_color(artwork_id=work.id, hex_rgb=CURRENT, method=MatMethod.MANUAL)
        return work

    return _matted


def current_listed_second(ui, work):
    """The server lists the newest mat first, so the current one is first; a page
    taking the first row would pass. Reordered, it must find the current one."""

    def reorder(route):
        response = route.fetch()
        body = response.json()
        body["mat_colors"] = sorted(body["mat_colors"], key=lambda mat: mat["is_current"])
        route.fulfill(response=response, json=body)

    ui.page.route(f"**/api/works/{work.id}", reorder)


def open_matted(ui, work):
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_selector(".work-hero .matted[data-layout]")


def measured(ui):
    """The mat's four margins around the picture, and the screen it was laid out for."""
    return ui.page.evaluate("""() => {
            const frame = document.querySelector('.work-hero .matted');
            const mat = frame.querySelector('.mat-surround').getBoundingClientRect();
            const work = frame.querySelector('img.work-picture').getBoundingClientRect();
            return {
              left: work.left - mat.left,
              top: work.top - mat.top,
              right: mat.right - work.right,
              bottom: mat.bottom - work.bottom,
              matWidth: mat.width,
              frameWidth: frame.clientWidth,
              screenHeight: Math.floor(window.innerHeight * 0.75),
              colour: getComputedStyle(frame.querySelector('.mat-surround')).backgroundColor,
            };
        }""")


def rgb(hex_rgb):
    return f"rgb({int(hex_rgb[1:3], 16)}, {int(hex_rgb[3:5], 16)}, {int(hex_rgb[5:7], 16)})"


def test_the_mat_is_the_works_current_colour(ui, matted):
    work = matted(1600, 1200)
    current_listed_second(ui, work)
    open_matted(ui, work)

    assert measured(ui)["colour"] == rgb(CURRENT)


@pytest.mark.parametrize("shape", [(1600, 1200), (1200, 1800), (1500, 1500)], ids=["landscape", "portrait", "square"])
def test_the_mats_margins_are_the_contracts(ui, matted, shape):
    """6% of the screen's shorter side on the sides and top, that times 1.15 at
    the bottom, each rounded half up; within a pixel, for the browser's own
    rounding of a laid-out box."""
    open_matted(ui, matted(*shape))
    seen = measured(ui)

    side = math.floor(0.06 * min(seen["frameWidth"], seen["screenHeight"]) + 0.5)
    bottom = math.floor(side * 1.15 + 0.5)
    for edge in ("left", "top", "right"):
        assert seen[edge] == pytest.approx(side, abs=1), edge
    assert seen["bottom"] == pytest.approx(bottom, abs=1)
    assert bottom > side, "the bottom is not weighted"


def test_the_mat_follows_the_picture_not_the_column(ui, matted):
    """A portrait work in a wide column: the mat hugs the picture, so it is
    narrower than the column, with its margins the same on every side."""
    open_matted(ui, matted(1200, 1800))
    seen = measured(ui)

    assert seen["matWidth"] < seen["frameWidth"] * 0.9
    assert seen["left"] == pytest.approx(seen["right"], abs=1)


def test_a_work_with_no_mat_is_shown_without_one_and_says_so(ui, work_with_an_image):
    work = work_with_an_image("Not yet prepared")
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_selector(".work-hero .matted[data-layout]")

    assert ui.page.locator(".work-hero .mat-surround").is_hidden()
    assert ui.page.locator(".work-hero .no-mat").inner_text() == "No mat has been chosen for it yet, so it is shown without one."


def test_a_work_with_a_mat_says_nothing_about_one(ui, matted):
    open_matted(ui, matted(1600, 1200))

    assert ui.page.locator(".work-hero .mat-surround").is_visible()
    assert ui.page.locator(".work-hero .no-mat").count() == 0


def detail_rewritten(ui, work, change):
    """The work's detail as the server sends it, changed by `change` in the browser."""

    def rewrite(route):
        response = route.fetch()
        body = response.json()
        change(body)
        route.fulfill(response=response, json=body)

    ui.page.route(f"**/api/works/{work.id}", rewrite)


def mat_shape(ui):
    return ui.page.evaluate(
        "() => { const box = document.querySelector('.work-hero .mat-surround').getBoundingClientRect();"
        " return [box.width, box.height]; }"
    )


def test_a_master_recorded_on_its_side_is_drawn_the_right_way_up(ui, matted):
    """The catalogue can record a master's size as stored, sideways to the
    picture served: the mat follows the picture's orientation, not the record's."""
    work = matted(1200, 1800)
    detail_rewritten(ui, work, lambda body: body["original"].update(width=1800, height=1200))
    open_matted(ui, work)

    width, height = mat_shape(ui)
    assert height > width, "a portrait work was matted as a landscape"


def test_a_work_with_no_recorded_master_is_matted_at_its_pictures_shape(ui, matted):
    work = matted(1200, 1800)
    detail_rewritten(ui, work, lambda body: body.update(original=None))
    open_matted(ui, work)

    width, height = mat_shape(ui)
    assert height > width
    assert ui.page.locator(".work-hero .mat-surround").is_visible()


# -- the mat control (#91) --------------------------------------------------------


def open_control(ui, work):
    """Open the folded control, as a curator does, once it has read the mat."""
    open_matted(ui, work)
    ui.page.wait_for_selector(".mat-control summary:has-text('Mat:')")
    assert not ui.page.locator(".mat-control").evaluate("(node) => node.open"), "the control starts open"
    ui.page.click(".mat-control summary")
    ui.page.wait_for_selector(".mat-control .mat-option")


def option(ui, label):
    return ui.page.locator(".mat-control button.mat-option", has_text=label)


def hero_colour(ui):
    return ui.page.evaluate("() => getComputedStyle(document.querySelector('.work-hero .mat-surround')).backgroundColor")


def test_a_preset_is_previewed_on_the_picture_and_recorded_only_when_used(ui, service, matted):
    work = matted(1600, 1200)
    second = MAT_PRESETS[1]
    open_control(ui, work)

    option(ui, second.label).click()

    assert hero_colour(ui) == rgb(second.hex_rgb)
    assert ui.page.locator(".mat-confirm").is_visible()
    assert service.current_mat_color(work.id).hex_rgb == CURRENT, "a preview recorded the colour"

    ui.page.click(".mat-confirm button.mat-use")
    ui.page.wait_for_selector(f".mat-status:has-text('The mat is now {second.label.lower()}.')")

    assert service.current_mat_color(work.id).hex_rgb == second.hex_rgb
    assert hero_colour(ui) == rgb(second.hex_rgb)
    assert option(ui, f"{second.label} (current)").is_disabled()


def test_keeping_the_current_mat_puts_the_picture_back(ui, service, matted):
    work = matted(1600, 1200)
    open_control(ui, work)

    option(ui, MAT_PRESETS[0].label).click()
    ui.page.click(".mat-confirm button.mat-keep")

    assert hero_colour(ui) == rgb(CURRENT)
    assert ui.page.locator(".mat-confirm").is_hidden()
    assert service.current_mat_color(work.id).hex_rgb == CURRENT


def test_a_refused_choice_is_said_beside_the_control(ui, service, matted):
    work = matted(1600, 1200)
    ui.page.route(
        f"**/api/works/{work.id}/mat",
        lambda route: (
            route.fulfill(status=400, json={"error": "That colour is darker than the mat floor."})
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    open_control(ui, work)

    option(ui, MAT_PRESETS[0].label).click()
    ui.page.click(".mat-confirm button.mat-use")

    failure = ui.page.locator(".mat-confirm button.mat-use + .act-failure")
    failure.wait_for()
    assert "darker than the mat floor" in failure.inner_text()
    assert "Nothing was changed." in failure.inner_text()


def test_the_derivation_is_offered_when_it_would_change_the_mat(ui, matted):
    open_control(ui, matted(1600, 1200))

    assert option(ui, "From the picture").count() == 1


def test_the_derivation_is_not_offered_when_it_is_already_the_mat(ui, service, settings, matted):
    work = matted(1600, 1200)
    original = service.get_original(work.id)
    service.record_mat_color(
        artwork_id=work.id,
        hex_rgb=derive(settings.art_root / original.relative_path).hex_rgb,
        method=MatMethod.DERIVED,
    )
    open_control(ui, work)

    assert option(ui, "From the picture").count() == 0
    assert ui.page.locator(".mat-control summary").inner_text() == "Mat: From the picture"
