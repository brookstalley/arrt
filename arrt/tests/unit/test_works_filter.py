"""*Last shown*'s periods, at their edges: `works_filter.shown_since`, with the instant held still.

The surfaces' cases are `tests/integration/test_last_shown_facet.py`, which read
the server's own clock and so cannot stand on an edge.
"""

from datetime import UTC, datetime, timedelta

from arrt.services.works_filter import SHOWN_PERIODS, shown_since

NOW = datetime(2026, 10, 15, 20, 0, tzinfo=UTC)


def test_a_work_last_seen_exactly_a_period_ago_was_shown_in_it():
    """'Not in the last month' leaves out a work up thirty days ago to the second: it was up within the month."""
    edge = NOW - SHOWN_PERIODS["month"]

    assert shown_since({"on-the-edge": edge}, NOW, "month") == {"on-the-edge"}
    assert shown_since({"just-before": edge - timedelta(seconds=1)}, NOW, "month") == frozenset()


def test_never_counts_every_work_ever_shown_however_long_ago():
    long_ago = NOW - timedelta(days=3650)

    assert shown_since({"once": long_ago}, NOW, "never") == {"once"}
