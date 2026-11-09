"""A calendar month as spend counts it: UTC, from its first instant to the next month's.

UTC rather than the operator's local month, because the provider's own credit
limit resets at midnight UTC, and a figure on any other boundary would disagree
with the only one that can stop spending. The month's spend report and the
unattended allowance both count by it, so they cannot disagree with each other.
"""

from datetime import UTC, datetime
from typing import Final

_DECEMBER: Final[int] = 12


def utc_month(year: int, month: int) -> tuple[datetime, datetime]:
    """The month's first instant and the next month's, `since` inclusive and `until` exclusive."""
    since = datetime(year, month, 1, tzinfo=UTC)
    until = datetime(year + (month == _DECEMBER), month % _DECEMBER + 1, 1, tzinfo=UTC)
    return since, until


def utc_month_of(moment: datetime) -> tuple[datetime, datetime]:
    """The UTC month `moment` falls in."""
    instant = moment.astimezone(UTC)
    return utc_month(instant.year, instant.month)
