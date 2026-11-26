"""`fixed_instant.py`: what a browser test's `at_a_fixed_instant` marker asks of both clocks, and what it refuses."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fixed_instant import A_FIXED_NOON, A_FIXED_NOON_WORDS, AT_A_FIXED_INSTANT_MARKER, fixed_instant


def _request_carrying(*args: object) -> SimpleNamespace:
    """What `fixed_instant` reads of a request: a node that answers `get_closest_marker`."""
    marker = SimpleNamespace(args=args)
    return SimpleNamespace(
        node=SimpleNamespace(get_closest_marker=lambda name: marker if name == AT_A_FIXED_INSTANT_MARKER else None)
    )


def test_a_test_with_no_marker_keeps_the_machines_clock():
    request = SimpleNamespace(node=SimpleNamespace(get_closest_marker=lambda name: None))

    assert fixed_instant(request) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "instant", [A_FIXED_NOON, A_FIXED_NOON + timedelta(days=40), datetime(2027, 1, 1, tzinfo=timezone(timedelta(hours=-5)))]
)
def test_the_marked_instant_is_the_one_both_clocks_start_at(instant):
    assert fixed_instant(_request_carrying(instant)) == instant  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "args",
    [
        (A_FIXED_NOON.replace(tzinfo=None),),
        ("2026-11-20T12:00:00+00:00",),
        (),
        (A_FIXED_NOON, A_FIXED_NOON),
    ],
    ids=["naive", "text", "none given", "two given"],
)
def test_an_instant_the_page_and_the_server_could_read_differently_is_refused(args):
    """A naive datetime is read as local time by the page and as UTC by the server: two instants."""
    with pytest.raises(pytest.UsageError, match=AT_A_FIXED_INSTANT_MARKER):
        fixed_instant(_request_carrying(*args))  # type: ignore[arg-type]


def test_the_noon_reads_as_the_same_day_in_any_time_zone():
    """Noon UTC is the 20th from UTC-11 to UTC+11, so `A_FIXED_NOON_WORDS` holds wherever the browser is."""
    assert (A_FIXED_NOON.hour, A_FIXED_NOON.minute) == (12, 0)
    assert A_FIXED_NOON.utcoffset() == timedelta(0)
    for hours in range(-11, 12):
        local = A_FIXED_NOON.astimezone(timezone(timedelta(hours=hours)))
        assert local.date() == A_FIXED_NOON.date(), f"UTC{hours:+d} moves the day"


def test_the_words_the_page_reads_it_as_follow_the_instant():
    day, month, year = A_FIXED_NOON.day, A_FIXED_NOON.strftime("%b"), A_FIXED_NOON.year
    assert f"{day} {month} {year}|{month} {day}, {year}" == A_FIXED_NOON_WORDS
