"""Settings › General, in a real browser against a real server.

Each setting is its own control, applied when chosen (`information-architecture.md`
§ Screen Inventory, General). A change reaches the next label with no restart; a
setting the environment gives shows its value and the variable, with no control;
a refused change is said beside the picker, which returns to the value it had.
"""

import pytest

from arrt.http.models import SettingListOut, SettingOut
from arrt.library.dimensions import Units
from arrt.library.services.settings import LABEL_UNITS

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

PICKER = "#setting-label_units"


def a_locked_listing() -> dict:
    """The listing a server whose environment sets LABEL_UNITS answers, in the route's own model."""
    locked = SettingOut(
        key="label_units",
        label="Label units",
        value="metric",
        default="imperial",
        source="environment",
        locked=True,
        environment_variable="LABEL_UNITS",
        description=LABEL_UNITS.description,
        choices=["imperial", "metric"],
        updated_at=None,
        updated_by=None,
    )
    return SettingListOut(settings=[locked]).model_dump(mode="json")


def test_the_settings_index_offers_general_between_sources_and_taste(ui):
    ui.open("#settings")

    pages = ui.page.locator(".settings-index li").evaluate_all("items => items.map(item => item.dataset.page)")
    assert pages == ["clients", "sources", "general", "taste"]

    ui.page.locator(".settings-index li[data-page=general] a").click()
    ui.page.wait_for_selector(PICKER)
    assert ui.page.locator("h1").inner_text() == "General"


def test_a_unit_chosen_here_reaches_the_next_label_with_no_restart(ui, services, seeded_service):
    work = seeded_service.add_artwork(title="Nighthawks", dimensions="76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)")
    ui.open("#general")
    picker = ui.page.locator(PICKER)
    assert picker.input_value() == "imperial"
    assert ui.page.locator("label[for='setting-label_units']").inner_text() == "Label units"

    picker.select_option("metric")
    ui.page.wait_for_selector("[data-setting=label_units] .setting-source time")

    assert services.settings.value(LABEL_UNITS) is Units.METRIC
    assert services.library.labels([work.id])[work.id]["dimensions"] == "77 × 97 cm"
    assert ui.page.locator(PICKER).input_value() == "metric", "the repainted page must show the value chosen"
    assert ui.page.locator("[data-setting=label_units] .setting-source").inner_text().startswith("Changed ")


def test_a_setting_nobody_has_changed_says_nothing_about_where_it_came_from(ui):
    ui.open("#general")
    ui.page.wait_for_selector(PICKER)

    assert ui.page.locator("[data-setting=label_units] .setting-source").count() == 0
    assert ui.page.locator(".page-facts").inner_text() == "Settings for the whole of this Arrt."


def test_a_setting_the_environment_gives_shows_its_value_and_the_variable_and_no_control(ui):
    ui.serve("**/api/settings", [a_locked_listing()])
    ui.open("#general")
    ui.page.wait_for_selector("[data-setting=label_units] .setting-locked")

    assert ui.page.locator("[data-setting=label_units] select").count() == 0, "a locked setting offered a control"
    assert ui.page.locator("[data-setting=label_units] .setting-locked").inner_text() == "Metric (centimetres)"
    assert (
        "Set by LABEL_UNITS in this Arrt's environment"
        in ui.page.locator("[data-setting=label_units] .setting-source").inner_text()
    )
    assert ui.page.locator(".page-facts").inner_text() == "Settings for the whole of this Arrt. 1 set in its environment."


def test_a_refused_change_is_said_beside_the_picker_which_returns_to_what_it_was(ui, services):
    refusal = "label_units is set by LABEL_UNITS in the environment, to 'imperial'."
    ui.serve("**/api/settings/label_units", [(400, {"success": False, "error": refusal})])
    ui.open("#general")
    picker = ui.page.locator(PICKER)

    picker.select_option("metric")

    said = ui.said_beside(picker)
    assert said.startswith("Couldn't set label units to metric (centimetres): ")
    assert said.endswith("Nothing was changed.")
    assert picker.input_value() == "imperial"
    assert services.settings.value(LABEL_UNITS) is Units.IMPERIAL
