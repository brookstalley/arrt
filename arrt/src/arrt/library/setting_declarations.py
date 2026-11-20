"""The household's settings as declared: what each is called, defaults to, and how it reads as text.

**This module imports no other `arrt` module**, so the deployment's configuration can
check the settings its environment gives without loading the service that stores them
(`arrt.library.services.settings`, which re-exports every name here as the same
object). The settings' own rules are in that module's docstring; what is declared
here is only the tuple and the way a value is read, checked and written.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final

from arrt.library.dimensions import Units


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


def dollars(raw: str) -> Decimal:
    """An amount in dollars, from zero to a million, to the cent, or `SettingRefused` saying what it must be.

    The allowance's own reading, for any amount held to the same rules (a Watch's cap).
    """
    return _money(raw)


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
