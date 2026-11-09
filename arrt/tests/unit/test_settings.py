"""The household's settings: where a value comes from, what is refused, and that a change is read at once."""

import logging

import pytest

from arrt.library.dimensions import Units
from arrt.library.services.settings import (
    LABEL_UNITS,
    SETTINGS,
    SettingRefused,
    SettingSource,
    SettingsService,
    from_environment,
)
from arrt.persistence.discovery_records import InitiatedBy
from arrt.persistence.sqlite_discovery import SqliteDiscovery
from arrt.services.errors import ServiceError


@pytest.fixture
def discovery(store) -> SqliteDiscovery:
    return SqliteDiscovery(store._store)


def state_of(service: SettingsService, key: str):
    [state] = [state for state in service.describe() if state.setting.key == key]
    return state


def test_a_setting_nobody_has_chosen_reads_as_its_default(discovery):
    service = SettingsService(discovery)

    assert service.value(LABEL_UNITS) is Units.IMPERIAL
    state = state_of(service, "label_units")
    assert (state.value, state.source, state.locked) == ("imperial", SettingSource.DEFAULT, False)
    assert (state.updated_at, state.updated_by) == (None, None)


def test_a_chosen_value_is_stored_and_read_at_once_by_the_next_caller(discovery):
    service = SettingsService(discovery)

    service.set("label_units", "metric", surface=InitiatedBy.WEB_UI)

    assert service.value(LABEL_UNITS) is Units.METRIC
    assert SettingsService(discovery).value(LABEL_UNITS) is Units.METRIC, "a second service over the same file reads it"
    state = state_of(service, "label_units")
    assert (state.source, state.updated_by) == (SettingSource.STORED, InitiatedBy.WEB_UI)
    assert state.updated_at is not None


def test_a_value_is_stored_in_its_own_spelling_however_it_was_written(discovery):
    SettingsService(discovery).set("label_units", "  METRIC ", surface=InitiatedBy.MCP_CLIENT)

    assert discovery.get_setting("label_units").value == "metric"


def test_a_second_change_replaces_the_first_and_records_who_made_it(discovery):
    service = SettingsService(discovery)
    service.set("label_units", "metric", surface=InitiatedBy.WEB_UI)

    service.set("label_units", "imperial", surface=InitiatedBy.MCP_CLIENT)

    assert service.value(LABEL_UNITS) is Units.IMPERIAL
    assert state_of(service, "label_units").updated_by is InitiatedBy.MCP_CLIENT


def test_the_environment_wins_over_a_stored_value_and_locks_the_setting(discovery):
    SettingsService(discovery).set("label_units", "imperial", surface=InitiatedBy.WEB_UI)
    service = SettingsService(discovery, environment={"label_units": "metric"})

    assert service.value(LABEL_UNITS) is Units.METRIC
    state = state_of(service, "label_units")
    assert (state.source, state.locked) == (SettingSource.ENVIRONMENT, True)

    with pytest.raises(ServiceError, match="label_units is set by LABEL_UNITS in the environment"):
        service.set("label_units", "imperial", surface=InitiatedBy.MCP_CLIENT)
    assert service.value(LABEL_UNITS) is Units.METRIC


def test_an_unknown_setting_is_refused_naming_the_ones_there_are(discovery):
    with pytest.raises(ServiceError, match=r"There is no setting 'units'\. The settings are label_units"):
        SettingsService(discovery).set("units", "metric", surface=InitiatedBy.WEB_UI)


def test_a_value_a_setting_cannot_take_is_refused_naming_what_it_can(discovery):
    service = SettingsService(discovery)

    with pytest.raises(ServiceError, match="LABEL_UNITS must be imperial or metric, got 'metirc'"):
        service.set("label_units", "metirc", surface=InitiatedBy.WEB_UI)
    assert discovery.get_setting("label_units") is None, "a refused value must not be stored"


def test_a_misspelt_environment_value_is_refused_where_it_was_given(discovery):
    with pytest.raises(SettingRefused, match="got 'metirc'"):
        SettingsService(discovery, environment={"label_units": "metirc"})


def test_a_stored_value_this_release_cannot_take_reads_as_the_default_and_says_so(discovery, caplog):
    """A value an earlier or later release wrote must not make every label build fail."""
    from datetime import UTC, datetime

    from arrt.persistence.discovery_records import StoredSetting

    discovery.put_setting(StoredSetting("label_units", "cubits", datetime.now(UTC), InitiatedBy.WEB_UI))

    with caplog.at_level(logging.WARNING, logger="arrt.library.services.settings"):
        assert SettingsService(discovery).value(LABEL_UNITS) is Units.IMPERIAL
    assert any("label_units='cubits'" in record.getMessage() for record in caplog.records)


def test_a_change_is_logged_with_its_old_and_new_value_and_surface(discovery, caplog):
    with caplog.at_level(logging.INFO, logger="arrt.library.services.settings"):
        SettingsService(discovery).set("label_units", "metric", surface=InitiatedBy.MCP_CLIENT)

    assert "setting label_units changed from 'imperial' to 'metric' by mcp_client" in caplog.text


def test_the_environment_gives_only_what_it_sets_each_in_its_own_spelling():
    assert from_environment({}) == {}
    assert from_environment({"LABEL_UNITS": ""}) == {}
    assert from_environment({"LABEL_UNITS": " Metric "}) == {"label_units": "metric"}


@pytest.mark.parametrize("setting", SETTINGS, ids=lambda setting: setting.key)
def test_every_setting_reads_back_what_it_writes(setting):
    """A render the parse cannot read back would store a value no later read accepts."""
    assert setting.parse(setting.render(setting.default)) == setting.default
    for choice in setting.choices:
        assert setting.render(setting.parse(choice)) == choice


def test_a_catalogue_file_from_before_settings_opens_and_gains_the_table(tmp_path):
    """The table is additive: a file written before it is opened, not refused, and can store a setting."""
    import sqlite3

    from arrt.persistence.file import open_catalogue_file

    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()
    with sqlite3.connect(path) as raw:
        raw.execute("DROP TABLE settings")
    assert "settings" not in {row[0] for row in sqlite3.connect(path).execute("SELECT name FROM sqlite_master")}

    reopened = open_catalogue_file(path)
    try:
        service = SettingsService(SqliteDiscovery(reopened))
        assert service.value(LABEL_UNITS) is Units.IMPERIAL
        service.set("label_units", "metric", surface=InitiatedBy.WEB_UI)
        assert service.value(LABEL_UNITS) is Units.METRIC
    finally:
        reopened.close()


# -- the unattended settings ---------------------------------------------------


def test_a_setting_the_environment_gives_locks_only_itself(discovery):
    """Locking is per setting: a lock keyed on 'the environment gave something' would lock them all."""
    service = SettingsService(discovery, environment={"label_units": "metric"})

    service.set("unattended_work", "on", surface=InitiatedBy.WEB_UI)

    assert state_of(service, "label_units").locked is True
    assert state_of(service, "unattended_work").locked is False
    assert state_of(service, "unattended_work").value == "on"


def test_an_environment_value_given_in_any_spelling_reads_back_in_the_settings_own(discovery):
    service = SettingsService(discovery, environment={"label_units": " Metric ", "unattended_allowance_usd": "$2.5"})

    assert state_of(service, "label_units").value == "metric"
    assert state_of(service, "unattended_allowance_usd").value == "2.50"


def test_unattended_work_is_off_with_no_allowance_until_chosen(discovery):
    service = SettingsService(discovery)

    assert [(state.setting.key, state.value) for state in service.describe() if state.setting.section == "Unattended work"] == [
        ("unattended_work", "off"),
        ("unattended_allowance_usd", "0.00"),
        ("unattended_cadence", "daily"),
        ("unattended_model", ""),
    ]


@pytest.mark.parametrize(("typed", "stored"), [("2.5", "2.50"), ("$3", "3.00"), (" 0 ", "0.00"), ("12.34", "12.34")])
def test_an_allowance_is_dollars_to_the_cent_however_typed(discovery, typed, stored):
    service = SettingsService(discovery)

    service.set("unattended_allowance_usd", typed, surface=InitiatedBy.WEB_UI)

    assert state_of(service, "unattended_allowance_usd").value == stored


@pytest.mark.parametrize(
    ("typed", "said"),
    [
        ("-1", "of at least 0"),
        ("1.234", "in whole cents"),
        ("ten", "an amount in dollars"),
        ("NaN", "of at least 0"),
        ("", "an amount in dollars"),
    ],
)
def test_an_allowance_that_is_not_an_amount_is_refused_by_name(discovery, typed, said):
    with pytest.raises(ServiceError, match=f"UNATTENDED_ALLOWANCE_USD .*{said}"):
        SettingsService(discovery).set("unattended_allowance_usd", typed, surface=InitiatedBy.WEB_UI)


def test_an_allowance_above_the_months_budget_is_refused_naming_the_budget(discovery):
    from decimal import Decimal

    from arrt.library.services.settings import Limits

    service = SettingsService(discovery, limits=Limits(monthly_budget_usd=Decimal(20)))
    service.set("unattended_allowance_usd", "20", surface=InitiatedBy.WEB_UI)

    with pytest.raises(ServiceError, match=r"share of the month's budget, \$20, and cannot be more than it; got \$20\.01"):
        service.set("unattended_allowance_usd", "20.01", surface=InitiatedBy.WEB_UI)


def test_an_environment_allowance_above_the_budget_refuses_to_start():
    from decimal import Decimal

    from arrt.library.services.settings import Limits

    with pytest.raises(SettingRefused, match="cannot be more than it"):
        from_environment({"UNATTENDED_ALLOWANCE_USD": "25"}, Limits(monthly_budget_usd=Decimal(20)))
    assert from_environment({"UNATTENDED_ALLOWANCE_USD": "25"}) == {"unattended_allowance_usd": "25.00"}, "no budget, no bound"


@pytest.mark.parametrize("model", ["", "deepseek/deepseek-v4-flash", "anthropic/claude-haiku-5.5", "openai/gpt-x:free"])
def test_a_model_is_a_providers_id_or_empty_for_the_discovery_model(discovery, model):
    service = SettingsService(discovery)

    service.set("unattended_model", model, surface=InitiatedBy.WEB_UI)

    assert state_of(service, "unattended_model").value == model


@pytest.mark.parametrize("model", ["gpt-5", "a b/c", "/model", "provider/"])
def test_a_model_that_is_not_a_providers_id_is_refused(discovery, model):
    with pytest.raises(ServiceError, match="UNATTENDED_MODEL must be a model id"):
        SettingsService(discovery).set("unattended_model", model, surface=InitiatedBy.WEB_UI)


def test_an_empty_value_is_refused_by_a_setting_that_does_not_take_one(discovery):
    with pytest.raises(ServiceError, match="LABEL_UNITS must be imperial or metric, got ''"):
        SettingsService(discovery).set("label_units", "", surface=InitiatedBy.WEB_UI)
