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
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
    #: A stored choice this release or this deployment no longer allows: the
    #: default applies, and the state says why, so the screen does not pass the
    #: household's choice off as one nobody made.
    SET_ASIDE = "set_aside"


class SettingRefused(ValueError):
    """A value a setting cannot take, in words that name what it can."""


class SettingKind(StrEnum):
    """What control a setting takes: a picker of its choices, an amount of money, or words."""

    CHOICE = "choice"
    MONEY = "money"
    TEXT = "text"


@dataclass(frozen=True)
class Limits:
    """The deployment's facts a setting's value is checked against, beside its own rules."""

    #: The month's budget on a key with no limit of its own (`MONTHLY_BUDGET_USD`).
    monthly_budget_usd: Decimal | None = None


@dataclass(frozen=True)
class Setting[T]:
    """One setting: what it is called, what it defaults to, and how it reads and writes as text."""

    key: str
    #: Its name as the screen and an agent say it, in sentence case.
    label: str
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
    kind: SettingKind = SettingKind.CHOICE
    #: The heading it is listed under, on the screen and in the tool's list.
    section: str = "General"
    #: A rule that needs the deployment's facts, raising `SettingRefused`.
    check: Callable[[T, Limits], None] | None = None

    def checked(self, raw: str, limits: Limits) -> T:
        """`raw` read as this setting's value and held to every rule it has, or `SettingRefused`.

        A refusal is named by the setting's variable here, once, so a parser
        never spells a variable it could get wrong.
        """
        try:
            return self.unnamed_check(raw, limits)
        except SettingRefused as exc:
            raise SettingRefused(f"{self.environment_variable} {exc}") from exc

    def unnamed_check(self, raw: str, limits: Limits) -> T:
        """As `checked`, with the refusal left for the caller to name: "must be …", "is a share …"."""
        value = self.parse(raw)
        if self.check is not None:
            self.check(value, limits)
        return value


def _choice[E: StrEnum](kind: type[E]) -> Callable[[str], E]:
    """Read one of `kind`'s members by its value, refusing anything else by naming them."""
    allowed = " or ".join(str(member) for member in kind)

    def parse(raw: str) -> E:
        try:
            return kind(raw.strip().lower())
        except ValueError as exc:
            raise SettingRefused(f"must be {allowed}, got {raw!r}.") from exc

    return parse


#: The system a label states a work's dimensions in. Imperial because the
#: reference wall's household reads inches.
LABEL_UNITS: Final[Setting[Units]] = Setting(
    key="label_units",
    label="Label units",
    environment_variable="LABEL_UNITS",
    default=Units.IMPERIAL,
    description="The system every wall label states a work's size in, rounded to whole units.",
    choices=tuple(str(member) for member in Units),
    parse=_choice(Units),
    render=str,
)


class Switch(StrEnum):
    """On or off, spelled as the screen and the environment say it."""

    OFF = "off"
    ON = "on"


class Cadence(StrEnum):
    """How often a standing piece of unattended work runs at most."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


#: The section the settings for agent work with nobody watching are listed under.
UNATTENDED_SECTION: Final[str] = "Unattended work"

#: Whether Arrt may spend on agent work with nobody watching (`agents-and-memory.md`
#: ruling 5). Off until a household chooses it, because the source is public and
#: nothing in the defaults may assume this household.
UNATTENDED_WORK: Final[Setting[Switch]] = Setting(
    key="unattended_work",
    label="Unattended work",
    environment_variable="UNATTENDED_WORK",
    default=Switch.OFF,
    description="Whether Arrt may spend on agent work, such as a standing search, with nobody watching.",
    choices=tuple(str(member) for member in Switch),
    parse=_choice(Switch),
    render=str,
    section=UNATTENDED_SECTION,
)


#: More than any household's month: past it a value is a typo, and far past it
#: rounding to the cent overflows the decimal context.
_MOST_DOLLARS: Final[Decimal] = Decimal(1_000_000)


def _money(raw: str) -> Decimal:
    """Read an amount in dollars, from zero to a million, to the cent."""
    text = raw.strip().removeprefix("$")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise SettingRefused(f"must be an amount in dollars, such as 2.50, got {raw!r}.") from exc
    if not amount.is_finite() or amount < 0:
        raise SettingRefused(f"must be an amount in dollars of at least 0, got {raw!r}.")
    if amount > _MOST_DOLLARS:
        raise SettingRefused(f"must be at most ${_MOST_DOLLARS:,}, got {raw!r}.")
    cents = amount.quantize(Decimal("0.01"))
    if amount != cents:
        raise SettingRefused(f"is in whole cents, got {raw!r}.")
    # `abs` so "-0" is held as 0.00, not shown as $-0.00.
    return abs(cents)


def _within_the_budget(amount: Decimal, limits: Limits) -> None:
    """An allowance is a share of the month's budget, so it may not exceed it where one is set."""
    if limits.monthly_budget_usd is not None and amount > limits.monthly_budget_usd:
        raise SettingRefused(
            f"is a share of the month's budget, ${limits.monthly_budget_usd}, " f"and cannot be more than it; got ${amount}."
        )


#: What unattended work may spend in a UTC calendar month, a share of the budget.
#: Nothing until a household chooses an amount.
UNATTENDED_ALLOWANCE: Final[Setting[Decimal]] = Setting(
    key="unattended_allowance_usd",
    label="Monthly allowance",
    environment_variable="UNATTENDED_ALLOWANCE_USD",
    default=Decimal("0.00"),
    description=(
        "What unattended work may spend in a calendar month, in dollars, out of the month's budget. "
        "Work stops starting once it is spent."
    ),
    choices=(),
    parse=_money,
    render=lambda amount: f"{amount:.2f}",
    kind=SettingKind.MONEY,
    section=UNATTENDED_SECTION,
    check=_within_the_budget,
)

#: How often a standing piece of unattended work runs at most, by default.
UNATTENDED_CADENCE: Final[Setting[Cadence]] = Setting(
    key="unattended_cadence",
    label="How often",
    environment_variable="UNATTENDED_CADENCE",
    default=Cadence.DAILY,
    description="How often a piece of unattended work, such as a standing search, runs at most.",
    choices=tuple(str(member) for member in Cadence),
    parse=_choice(Cadence),
    render=str,
    section=UNATTENDED_SECTION,
)

#: A provider's model id: an organisation, a slash, and the model's name.
_MODEL_ID: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][\w.-]*/[\w.:-]+")


def _model(raw: str) -> str:
    """A model id, or empty for the discovery model."""
    model = raw.strip()
    if model and not _MODEL_ID.fullmatch(model):
        raise SettingRefused(f"must be a model id such as 'provider/model', or empty, got {raw!r}.")
    return model


#: Which model unattended work runs on. Empty means the discovery model
#: (`DISCOVERY_MODEL`), which is what it should be unless a household has reason
#: to pay for a different one.
UNATTENDED_MODEL: Final[Setting[str]] = Setting(
    key="unattended_model",
    label="Model",
    environment_variable="UNATTENDED_MODEL",
    default="",
    description="The model unattended work runs on, as the provider names it. Empty is the discovery model.",
    choices=(),
    parse=_model,
    render=str,
    kind=SettingKind.TEXT,
    section=UNATTENDED_SECTION,
)

#: Every setting, in the order the screen and the tool list them.
SETTINGS: Final[tuple[Setting[object], ...]] = (  # type: ignore[assignment]
    LABEL_UNITS,
    UNATTENDED_WORK,
    UNATTENDED_ALLOWANCE,
    UNATTENDED_CADENCE,
    UNATTENDED_MODEL,
)

SETTINGS_BY_KEY: Final[dict[str, Setting[object]]] = {setting.key: setting for setting in SETTINGS}


def from_environment(environ: Mapping[str, str], limits: Limits | None = None) -> dict[str, str]:
    """The settings the environment gives, by key, as text, each checked.

    Raises `SettingRefused` for the first value a setting cannot take, so a
    deployment with a misspelt value refuses to start rather than starting on
    the default.
    """
    given: dict[str, str] = {}
    for setting in SETTINGS:
        raw = environ.get(setting.environment_variable)
        if raw:
            given[setting.key] = setting.render(setting.checked(raw, limits or Limits()))
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
    #: Why a stored choice was set aside, in a sentence naming the setting and the
    #: stored value; None unless `source` is `set_aside`.
    set_aside_reason: str | None = None

    @property
    def locked(self) -> bool:
        return self.source is SettingSource.ENVIRONMENT


class SettingsService:
    """Reads and changes the settings in `SETTINGS`."""

    def __init__(
        self, store: DiscoveryStore, *, environment: Mapping[str, str] | None = None, limits: Limits | None = None
    ) -> None:
        self._store = store
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
            parsed = setting.checked(value, self._limits)
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
