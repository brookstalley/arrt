"""The instant a browser test that asserts a date or an age stands both clocks at.

The browser suite keeps the machine's clock (`conftest.py`'s `shared_clock` says why): its page
reads the browser's own `Date.now` against the server's instants, so a clock fixed on one side
only would put every age a screen shows months out. A test whose assertion reads a date or an
age says so with `@pytest.mark.at_a_fixed_instant(instant)`, and then **both** clocks stand
there: the services read a `Ticking` clock that starts at the instant, and the page's `Date`
is fixed at it (`browser/conftest.py`'s `ui`). The test seeds what it ages from the clock it
takes (`shared_clock()`), never `datetime.now()`, and asserts the words the instant makes.

Here rather than in `conftest.py` so both conftest files and a test can import it, for the
reason `report_guard.py` gives.
"""

from datetime import UTC, datetime
from typing import Final

import pytest

#: The marker's name.
AT_A_FIXED_INSTANT_MARKER: Final = "at_a_fixed_instant"

#: Noon UTC on a day in the middle of a month and a year: whatever time zone the browser is in,
#: the same day, month and year are said, and no boundary of any of them is near.
A_FIXED_NOON: Final = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

#: How `A_FIXED_NOON` reads in the page, in either order the locale writes it.
A_FIXED_NOON_WORDS: Final = "20 Nov 2026|Nov 20, 2026"


def fixed_instant(request: pytest.FixtureRequest) -> datetime | None:
    """The instant the test fixed both clocks at, or None when it keeps the machine's."""
    marker = request.node.get_closest_marker(AT_A_FIXED_INSTANT_MARKER)
    if marker is None:
        return None
    if len(marker.args) != 1 or not isinstance(marker.args[0], datetime) or marker.args[0].tzinfo is None:
        raise pytest.UsageError(
            f"@pytest.mark.{AT_A_FIXED_INSTANT_MARKER} takes one timezone-aware datetime, got {marker.args!r}"
        )
    return marker.args[0]
