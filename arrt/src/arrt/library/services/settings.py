"""The household's settings: declared once, stored in the catalogue, read when used.

**Every setting is a `Setting` in `SETTINGS`**, which says its key, its default,
the environment variable that may set it, and how a value is read and written
as text. The service, the route, the MCP tool, the screen and the tests all
read that tuple, so a setting cannot reach one of them and miss another.

**The environment wins and locks the setting.** A value the deployment gives in
its environment is the value, and a change from the browser or an agent is
refused naming the variable. A stored value applies only where the environment
says nothing, and the default where neither does. So a deployment pinned in its
env file is never silently overridden, and a change made in the browser is
never silently undone at the next restart.

**Each read is made when the value is used.** Nothing captures a setting at
startup, so a change reaches the next label built without a restart.

Every surface may change every setting (the owner, 2026-11-09: "settings can be
changed by MCP, definitely"). Which surface made a change is recorded, for
tracing a surprise; it decides nothing.
"""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

from arrt.library.setting_declarations import (
    LABEL_UNITS,
    SETTINGS,
    SETTINGS_BY_KEY,
    UNATTENDED_ALLOWANCE,
    UNATTENDED_CADENCE,
    UNATTENDED_MODEL,
    UNATTENDED_SECTION,
    UNATTENDED_WORK,
    Cadence,
    Limits,
    Setting,
    SettingKind,
    SettingRefused,
    Switch,
    dollars,
    from_environment,
)
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.discovery_records import InitiatedBy, StoredSetting
from arrt.services.errors import NotFound, ServiceError
from arrt.services.fields import require_member
from arrt.services.store import store_write

#: Re-exported from `arrt.library.setting_declarations`, where they are declared: importing them from here gives the same object.
__all__ = [
    "LABEL_UNITS",
    "SETTINGS",
    "SETTINGS_BY_KEY",
    "UNATTENDED_ALLOWANCE",
    "UNATTENDED_CADENCE",
    "UNATTENDED_MODEL",
    "UNATTENDED_SECTION",
    "UNATTENDED_WORK",
    "Cadence",
    "Limits",
    "Setting",
    "SettingKind",
    "SettingRefused",
    "Switch",
    "dollars",
    "from_environment",
]

log = logging.getLogger(__name__)


class SettingSource(StrEnum):
    """Where a setting's value came from."""

    ENVIRONMENT = "environment"
    STORED = "stored"
    DEFAULT = "default"
    #: A stored choice this release or this deployment no longer allows: the
    #: default applies, and the state says why, so the screen does not pass the
    #: household's choice off as one nobody made.
    SET_ASIDE = "set_aside"


@dataclass(frozen=True)
class SettingState:
    """A setting as the screen and the tool describe it."""

    setting: Setting[object]
    value: str
    source: SettingSource
    #: When and from where it was last changed, while a stored value exists.
    updated_at: datetime | None
    updated_by: InitiatedBy | None
    #: Why a stored choice was set aside, in a sentence naming the setting and the
    #: stored value; None unless `source` is `set_aside`.
    set_aside_reason: str | None = None

    @property
    def locked(self) -> bool:
        return self.source is SettingSource.ENVIRONMENT


class SettingsService:
    """Reads and changes the settings in `SETTINGS`."""

    def __init__(
        self,
        store: DiscoveryStore,
        *,
        environment: Mapping[str, str] | None = None,
        limits: Limits | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        #: The instant a change is stamped at: the machine's, or the one `Services.bind` builds every service over.
        self._now = now
        self._limits = limits or Limits()
        # Each set-aside stored value is logged once, not at every read: a value
        # is read at every label build and every pass, and a warning repeated
        # that often buries the one line that says why.
        self._reported: set[tuple[str, str]] = set()
        self._reported_lock = threading.Lock()
        # Checked here as well as at startup, so a suite passing a misspelt value
        # fails where it passed it rather than at the first read. Held in each
        # setting's own spelling, as `from_environment` gives it, so a direct
        # caller's " Metric " reads back as "metric" like any other.
        self._environment = {
            key: self._known(key).render(self._known(key).checked(raw, self._limits)) for key, raw in (environment or {}).items()
        }

    def value[T](self, setting: Setting[T]) -> T:
        """This setting's value now: the environment's, else the stored one, else the default."""
        # `_state` reads a setting only through its key, `unnamed_check`, `render`
        # and `default`, which agree with one another for any `T`; it never feeds
        # `T` a value of another type. The registry above already holds every
        # `Setting[T]` as a `Setting[object]` for the same reason.
        return setting.parse(self._state(cast("Setting[object]", setting)).value)

    def describe(self) -> Sequence[SettingState]:
        """Every setting, in `SETTINGS`' order, with its value and where that came from."""
        return [self._state(setting) for setting in SETTINGS]

    def set(self, key: str, value: str, *, surface: InitiatedBy) -> SettingState:
        """Store a new value for `key`, refusing an unknown key, a locked one, or a value it cannot take."""
        setting = self._known(key)
        if key in self._environment:
            raise ServiceError(
                f"{key} is set by {setting.environment_variable} in the environment, to "
                f"{self._environment[key]!r}. Change it there and restart Arrt, or remove it there to change it here."
            )
        try:
            parsed = setting.checked(value, self._limits)
        except SettingRefused as exc:
            raise ServiceError(str(exc)) from exc
        before = self._state(setting)
        # A choice set aside is named as it was stored, so the change line says
        # what the household's new choice replaced, not the default standing in.
        prior = self._store.get_setting(key) if before.source is SettingSource.SET_ASIDE else None
        was = f"{prior.value!r} (set aside)" if prior is not None else repr(before.value)
        stored = StoredSetting(
            key=key,
            value=setting.render(parsed),
            updated_at=self._now(),
            updated_by=require_member(surface, enum=InitiatedBy, field="surface"),
        )
        store_write(self._store.put_setting, stored)
        log.info("setting %s changed from %s to %r by %s", key, was, stored.value, stored.updated_by)
        return self._state(setting)

    def _known(self, key: str) -> Setting[object]:
        setting = SETTINGS_BY_KEY.get(key)
        if setting is None:
            raise NotFound(f"There is no setting {key!r}. The settings are {', '.join(SETTINGS_BY_KEY)}.")
        return setting

    def _state(self, setting: Setting[object]) -> SettingState:
        stored = self._store.get_setting(setting.key)
        updated_at = None if stored is None else stored.updated_at
        updated_by = None if stored is None else stored.updated_by
        if setting.key in self._environment:
            return SettingState(setting, self._environment[setting.key], SettingSource.ENVIRONMENT, updated_at, updated_by)
        if stored is not None:
            try:
                value = setting.unnamed_check(stored.value, self._limits)
            except SettingRefused as exc:
                # A value an earlier release could take and this one cannot, or
                # one a later change to the deployment rules out (an allowance
                # above a budget since lowered): the default applies, and the
                # state says why rather than the read failing.
                return self._set_aside(setting, stored.value, f"{setting.label} {exc}", updated_at, updated_by)
            return SettingState(setting, setting.render(value), SettingSource.STORED, updated_at, updated_by)
        return SettingState(setting, setting.render(setting.default), SettingSource.DEFAULT, updated_at, updated_by)

    def _set_aside(
        self,
        setting: Setting[object],
        stored: str,
        reason: str,
        updated_at: datetime | None,
        updated_by: InitiatedBy | None,
    ) -> SettingState:
        with self._reported_lock:
            first = (setting.key, stored) not in self._reported
            self._reported.add((setting.key, stored))
        if first:
            log.warning("stored setting %s=%r is set aside (%s); using the default", setting.key, stored, reason)
        return SettingState(
            setting, setting.render(setting.default), SettingSource.SET_ASIDE, updated_at, updated_by, set_aside_reason=reason
        )
