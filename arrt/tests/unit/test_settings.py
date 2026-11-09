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


def test_a_setting_the_environment_leaves_alone_is_not_locked_by_another_it_gives(discovery):
    """Locking is per setting: a lock keyed on 'the environment gave something' would lock them all."""
    service = SettingsService(discovery, environment={})

    service.set("label_units", "metric", surface=InitiatedBy.WEB_UI)

    assert state_of(service, "label_units").locked is False


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
