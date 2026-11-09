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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from arrt.library.dimensions import Units
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.discovery_records import InitiatedBy, StoredSetting
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member
from arrt.services.store import store_write

log = logging.getLogger(__name__)


class SettingSource(StrEnum):
    """Where a setting's value came from."""

    ENVIRONMENT = "environment"
    STORED = "stored"
    DEFAULT = "default"


class SettingRefused(ValueError):
    """A value a setting cannot take, in words that name what it can."""


@dataclass(frozen=True)
class Setting[T]:
    """One setting: what it is called, what it defaults to, and how it reads and writes as text."""

    key: str
    #: The variable that sets it from the deployment and locks it there.
    environment_variable: str
    default: T
    #: One line for whoever changes it, on the screen and over MCP.
    description: str
    #: The values it can take, in the order a control offers them; empty for
    #: a setting that is not a choice.
    choices: tuple[str, ...]
    parse: Callable[[str], T]
    render: Callable[[T], str]


def _choice[E: StrEnum](kind: type[E], name: str) -> Callable[[str], E]:
    """Read one of `kind`'s members by its value, refusing anything else by name."""
    allowed = " or ".join(str(member) for member in kind)

    def parse(raw: str) -> E:
        try:
            return kind(raw.strip().lower())
        except ValueError as exc:
            raise SettingRefused(f"{name} must be {allowed}, got {raw!r}.") from exc

    return parse


#: The system a label states a work's dimensions in. Imperial because the
#: reference wall's household reads inches.
LABEL_UNITS: Final[Setting[Units]] = Setting(
    key="label_units",
    environment_variable="LABEL_UNITS",
    default=Units.IMPERIAL,
    description="The system every wall label states a work's size in, rounded to whole units.",
    choices=tuple(str(member) for member in Units),
    parse=_choice(Units, "LABEL_UNITS"),
    render=str,
)

#: Every setting, in the order the screen and the tool list them.
SETTINGS: Final[tuple[Setting[object], ...]] = (LABEL_UNITS,)  # type: ignore[assignment]

SETTINGS_BY_KEY: Final[dict[str, Setting[object]]] = {setting.key: setting for setting in SETTINGS}


def from_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """The settings the environment gives, by key, as text, each checked.

    Raises `SettingRefused` for the first value a setting cannot take, so a
    deployment with a misspelt value refuses to start rather than starting on
    the default.
    """
    given: dict[str, str] = {}
    for setting in SETTINGS:
        raw = environ.get(setting.environment_variable)
        if raw:
            given[setting.key] = setting.render(setting.parse(raw))
    return given


@dataclass(frozen=True)
class SettingState:
    """A setting as the screen and the tool describe it."""

    setting: Setting[object]
    value: str
    source: SettingSource
    #: When and from where it was last changed, while a stored value exists.
    updated_at: datetime | None
    updated_by: InitiatedBy | None

    @property
    def locked(self) -> bool:
        return self.source is SettingSource.ENVIRONMENT


class SettingsService:
    """Reads and changes the settings in `SETTINGS`."""

    def __init__(self, store: DiscoveryStore, *, environment: Mapping[str, str] | None = None) -> None:
        self._store = store
        # Checked here as well as at startup, so a suite passing a misspelt value
        # fails where it passed it rather than at the first read.
        self._environment = dict(environment or {})
        for key, raw in self._environment.items():
            self._known(key).parse(raw)

    def value[T](self, setting: Setting[T]) -> T:
        """This setting's value now: the environment's, else the stored one, else the default."""
        return setting.parse(self._state(setting).value)

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
            parsed = setting.parse(value)
        except SettingRefused as exc:
            raise ServiceError(str(exc)) from exc
        before = self._state(setting)
        stored = StoredSetting(
            key=key,
            value=setting.render(parsed),
            updated_at=datetime.now(UTC),
            updated_by=require_member(surface, enum=InitiatedBy, field="surface"),
        )
        store_write(self._store.put_setting, stored)
        log.info("setting %s changed from %r to %r by %s", key, before.value, stored.value, stored.updated_by)
        return self._state(setting)

    def _known(self, key: str) -> Setting[object]:
        setting = SETTINGS_BY_KEY.get(key)
        if setting is None:
            raise ServiceError(f"There is no setting {key!r}. The settings are {', '.join(SETTINGS_BY_KEY)}.")
        return setting

    def _state(self, setting: Setting[object]) -> SettingState:
        stored = self._store.get_setting(setting.key)
        updated_at = None if stored is None else stored.updated_at
        updated_by = None if stored is None else stored.updated_by
        if setting.key in self._environment:
            return SettingState(setting, self._environment[setting.key], SettingSource.ENVIRONMENT, updated_at, updated_by)
        if stored is not None:
            try:
                return SettingState(
                    setting, setting.render(setting.parse(stored.value)), SettingSource.STORED, updated_at, updated_by
                )
            except SettingRefused:
                # A value an earlier release could take and this one cannot: the
                # default applies, and the log says so rather than the read failing.
                log.warning("stored setting %s=%r is not one this release takes; using the default", setting.key, stored.value)
        return SettingState(setting, setting.render(setting.default), SettingSource.DEFAULT, updated_at, updated_by)
