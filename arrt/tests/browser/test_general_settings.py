"""Settings › General, in a real browser against a real server.

Each setting is its own control, applied when chosen (`information-architecture.md`
§ Screen Inventory, General). A change reaches the next label with no restart; a
setting the environment gives shows its value and the variable, with no control;
a refused change is said beside the picker, which returns to the value it had.
"""

import re
from decimal import Decimal

import pytest

from arrt.http.models import SettingListOut, SettingOut
from arrt.library.dimensions import Units
from arrt.library.discovery.openrouter import KeyStatus
from arrt.library.services.settings import LABEL_UNITS

expect = pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
).expect

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
        kind="choice",
        section="General",
        updated_at=None,
        updated_by=None,
        set_aside_reason=None,
    )
    return SettingListOut(settings=[locked]).model_dump(mode="json")


def test_the_settings_index_offers_general_between_sources_and_taste(ui):
    ui.open("#settings")

    pages = ui.page.locator(".settings-index li").evaluate_all("items => items.map(item => item.dataset.page)")
    assert pages == ["clients", "sources", "watches", "general", "taste"]

    ui.page.locator(".settings-index li[data-page=general] a").click()
    ui.page.wait_for_selector(PICKER)
    expect(ui.page.locator("h1")).to_have_text("General", use_inner_text=True)


def test_a_unit_chosen_here_reaches_the_next_label_with_no_restart(ui, services, seeded_service):
    work = seeded_service.add_artwork(title="Nighthawks", dimensions="76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)")
    ui.open("#general")
    picker = ui.page.locator(PICKER)
    expect(picker).to_have_value("imperial")
    expect(ui.page.locator("label[for='setting-label_units']")).to_have_text("Label units", use_inner_text=True)

    picker.select_option("metric")
    ui.page.wait_for_selector("[data-setting=label_units] .setting-source time")

    assert services.settings.value(LABEL_UNITS) is Units.METRIC
    assert services.library.labels([work.id])[work.id]["dimensions"] == "77 × 97 cm"
    expect(ui.page.locator(PICKER), "the repainted page must show the value chosen").to_have_value("metric")
    expect(ui.page.locator("[data-setting=label_units] .setting-source")).to_have_text(
        re.compile("^Changed "), use_inner_text=True
    )


def test_a_setting_nobody_has_changed_says_nothing_about_where_it_came_from(ui):
    ui.open("#general")
    ui.page.wait_for_selector(PICKER)

    expect(ui.page.locator(".page-facts")).to_have_text("Settings for the whole of this Arrt.", use_inner_text=True)
    expect(ui.page.locator("[data-setting=label_units] .setting-source")).to_have_count(0)


def test_a_choice_set_aside_says_so_and_why_and_its_control_still_offers_a_new_one(ui, discovery_store):
    """A stored choice this release no longer allows reads as the default, and the screen says it was set aside (#417)."""
    from datetime import UTC, datetime

    from arrt.persistence.discovery_records import InitiatedBy, StoredSetting

    discovery_store.put_setting(StoredSetting("label_units", "cubits", datetime.now(UTC), InitiatedBy.WEB_UI))
    ui.open("#general")
    ui.page.wait_for_selector("[data-setting=label_units] .setting-set-aside")

    expect(ui.page.locator("[data-setting=label_units] .setting-set-aside")).to_have_text(
        "Your choice was set aside, so the default applies: Label units must be imperial or metric, got 'cubits'. "
        "Choose again to replace it.",
        use_inner_text=True,
    )
    expect(ui.page.locator(PICKER)).to_have_value("imperial")
    expect(ui.page.locator("[data-setting=unattended_work] .setting-set-aside"), "only the set-aside one says so").to_have_count(
        0
    )


def test_a_setting_the_environment_gives_shows_its_value_and_the_variable_and_no_control(ui):
    ui.serve("**/api/settings", [a_locked_listing()])
    ui.open("#general")
    ui.page.wait_for_selector("[data-setting=label_units] .setting-locked")

    expect(ui.page.locator("[data-setting=label_units] .setting-locked")).to_have_text(
        "Metric (centimetres)", use_inner_text=True
    )
    expect(ui.page.locator("[data-setting=label_units] select"), "a locked setting offered a control").to_have_count(0)
    expect(ui.page.locator("[data-setting=label_units] .setting-source")).to_contain_text(
        "Set by LABEL_UNITS in this Arrt's environment", use_inner_text=True
    )
    expect(ui.page.locator(".page-facts")).to_have_text(
        "Settings for the whole of this Arrt. 1 set in its environment.", use_inner_text=True
    )


def test_a_refused_change_is_said_beside_the_picker_which_returns_to_what_it_was(ui, services):
    refusal = "label_units is set by LABEL_UNITS in the environment, to 'imperial'."
    ui.serve("**/api/settings/label_units", [(400, {"success": False, "error": refusal})])
    ui.open("#general")
    picker = ui.page.locator(PICKER)

    picker.select_option("metric")

    said = ui.said_beside(picker)
    assert said.startswith("Couldn't set label units to metric (centimetres): ")
    assert said.endswith("Nothing was changed.")
    expect(picker).to_have_value("imperial")
    assert services.settings.value(LABEL_UNITS) is Units.IMPERIAL


# -- unattended work --------------------------------------------------------------

STANDING = ".unattended-standing"
SPEND = ".unattended-spend"


def test_unattended_work_is_its_own_section_off_and_saying_so(ui):
    ui.open("#general")
    ui.page.wait_for_selector(STANDING)

    section = ui.page.locator("[data-section='Unattended work']")
    expect(section.locator("h2")).to_have_text("Unattended work", use_inner_text=True)
    expect(section.locator("#setting-unattended_work")).to_have_value("off")
    expect(section.locator("#setting-unattended_allowance_usd")).to_have_value("0.00")
    expect(section.locator("#setting-unattended_model")).to_have_attribute("placeholder", "Discovery model")
    expect(ui.page.locator(STANDING)).to_have_text(
        "Unattended work is off, so nothing runs with nobody watching.", use_inner_text=True
    )
    expect(ui.page.locator(SPEND)).to_have_text("Spent this month: $0.00, of a $0.00 allowance; $0.00 left.", use_inner_text=True)
    expect(
        ui.page.locator("[data-section='Unattended work'] #setting-label_units"), "label units is the page's own"
    ).to_have_count(0)


def test_switched_on_with_an_allowance_but_no_key_it_says_the_key_is_missing(ui, services):
    ui.open("#general")
    ui.page.wait_for_selector(STANDING)

    ui.page.locator("#setting-unattended_work").select_option("on")
    ui.page.wait_for_selector("[data-setting=unattended_work] .setting-source time")
    allowance = ui.page.locator("#setting-unattended_allowance_usd")
    allowance.fill("2.5")
    allowance.press("Enter")
    ui.page.wait_for_function("document.querySelector('#setting-unattended_allowance_usd').value === '2.50'")

    assert services.unattended.standing().allowance_usd == 2.5
    # The suite's deployment has no model key, so switched on it is refused for that, said in words.
    expect(ui.page.locator(STANDING)).to_have_text(
        "There is no model key, so unattended work has nothing to spend with.", use_inner_text=True
    )
    expect(ui.page.locator(SPEND)).to_have_text("Spent this month: $0.00, of a $2.50 allowance; $2.50 left.", use_inner_text=True)


class TestWithAModelKey:
    @pytest.fixture
    def key_status(self):
        return lambda: KeyStatus(limit_usd=Decimal(20), usage_usd=Decimal(1), remaining_usd=Decimal(19))

    def test_switched_on_with_an_allowance_and_a_key_it_says_it_may_run(self, ui):
        ui.open("#general")
        ui.page.wait_for_selector(STANDING)

        ui.page.locator("#setting-unattended_work").select_option("on")
        ui.page.wait_for_selector("[data-setting=unattended_work] .setting-source time")
        allowance = ui.page.locator("#setting-unattended_allowance_usd")
        allowance.fill("2.5")
        allowance.press("Enter")
        ui.page.wait_for_function("document.querySelector('#setting-unattended_allowance_usd').value === '2.50'")

        expect(ui.page.locator(STANDING)).to_have_text(
            "Unattended work may run: this month's allowance is $2.50, of which it has spent $0.00.", use_inner_text=True
        )


def test_an_allowance_that_is_not_an_amount_is_refused_beside_the_field_which_puts_it_back(ui, services):
    ui.open("#general")
    allowance = ui.page.locator("#setting-unattended_allowance_usd")
    allowance.wait_for()

    allowance.fill("ten")
    allowance.press("Enter")

    said = ui.said_beside(allowance)
    assert said.startswith("Couldn't set monthly allowance to $ten: UNATTENDED_ALLOWANCE_USD must be an amount in dollars")
    assert said.endswith("Nothing was changed.")
    expect(allowance).to_have_value("0.00")
    assert str(services.unattended.standing().allowance_usd) == "0.00"


def test_on_a_phone_each_label_stands_over_its_field_and_a_dollar_sign_stays_beside_its_input(ui):
    """Beside each other the fields were about 210px wide and the "$" sat above its input (audit-6 finding 18)."""
    ui.page.set_viewport_size({"width": 390, "height": 844})
    ui.open("#general")
    allowance = ui.page.locator("#setting-unattended_allowance_usd")
    expect(allowance).to_be_visible()

    label = ui.page.locator("label[for='setting-unattended_allowance_usd']").bounding_box()  # one-shot: geometry
    field = allowance.bounding_box()  # one-shot: geometry
    sign = ui.page.locator(".money-field > span[aria-hidden]").first.bounding_box()  # one-shot: geometry
    unit = ui.page.locator(PICKER).bounding_box()  # one-shot: geometry

    assert label["y"] + label["height"] <= field["y"], "the label is beside its field, not over it"
    assert abs((sign["y"] + sign["height"] / 2) - (field["y"] + field["height"] / 2)) < 4, "the $ is not on its input's line"
    assert sign["x"] + sign["width"] <= field["x"], "the $ is not before its input"
    assert unit["x"] < 40, "the picker is indented under a label column"
    column = ui.page.locator("dd[data-setting='unattended_allowance_usd']").bounding_box()  # one-shot: geometry, once drawn
    assert column["width"] > 300, f"the value column is {column['width']:.0f}px wide"
