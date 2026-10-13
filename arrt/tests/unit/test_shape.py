"""A wall's range of shapes: how a curator spells a bound, how it is spoken back, and what fits."""

import pytest

from arrt.programming import shape
from arrt.services.errors import ServiceError


@pytest.mark.parametrize(
    ("spelled", "ratio"),
    [("1:1", 1.0), ("4:5", 0.8), ("16:9", 16 / 9), (" 0.8 ", 0.8), ("1.5", 1.5), ("2.39:1", 2.39), ("ANY", None), ("any", None)],
)
def test_a_bound_is_read_as_a_curator_writes_it(spelled, ratio):
    assert shape.parse(spelled) == (None if ratio is None else pytest.approx(ratio))


@pytest.mark.parametrize("spelled", ["", "wide", "0:1", "1:0", "4:", ":5", "-1", "0", "nan", "inf", "4:-5", "none"])
def test_anything_else_is_refused_by_name(spelled):
    with pytest.raises(ServiceError, match="width:height"):
        shape.parse(spelled)


@pytest.mark.parametrize(
    ("ratio", "spoken"),
    [(1.0, "1:1"), (16 / 9, "16:9"), (9 / 16, "9:16"), (0.8, "4:5"), (2 / 3, "2:3"), (3000 / 3003, "1:1"), (2.35, "2.35:1")],
)
def test_a_shape_is_spoken_as_a_curator_would_say_it(ratio, spoken):
    assert shape.spoken(ratio) == spoken


@pytest.mark.parametrize("spelled", ["1:1", "4:5", "16:9", "9:16", "2:3", "21:9", "1.618", "2.39"])
def test_sending_back_a_spoken_bound_does_not_move_it(spelled):
    """The client sends back what it was given, so a round trip must leave the bound where the curator put it."""
    ratio = shape.parse(spelled)

    assert shape.parse(shape.spoken(ratio)) == pytest.approx(ratio, rel=shape.TOLERANCE / 2)
    # And a second trip moves it no further.
    assert shape.spoken(shape.parse(shape.spoken(ratio))) == shape.spoken(ratio)


@pytest.mark.parametrize(
    ("size", "fits"),
    [
        ((1000, 1000), True),
        # One per cent of give each way, and no more.
        ((1010, 1000), True),
        ((1011, 1000), False),
        ((990, 1000), True),
        ((989, 1000), False),
        ((1600, 900), False),
        ((900, 1600), False),
    ],
)
def test_a_square_only_wall_takes_squares_within_one_per_cent(size, fits):
    assert shape.fits(size, tallest=1.0, widest=1.0) is fits


def test_each_bound_limits_one_side_only():
    landscape, portrait = (1600, 900), (900, 1600)

    assert shape.fits(portrait, tallest=None, widest=1.0)
    assert not shape.fits(landscape, tallest=None, widest=1.0)
    assert shape.fits(landscape, tallest=1.0, widest=None)
    assert not shape.fits(portrait, tallest=1.0, widest=None)
    assert shape.fits(portrait, tallest=None, widest=None)
    assert shape.fits(landscape, tallest=None, widest=None)


def test_a_tallest_wider_than_the_widest_is_refused_and_an_equal_pair_is_not():
    with pytest.raises(ServiceError, match="tallest shape, 16:9, is wider than the widest, 1:1"):
        shape.require_range(16 / 9, 1.0)

    shape.require_range(1.0, 1.0)
    shape.require_range(None, 1.0)
    shape.require_range(16 / 9, None)


@pytest.mark.parametrize(
    ("tallest", "widest", "phrase"),
    [
        (None, 1.0, "nothing wider than 1:1"),
        (1.0, None, "nothing taller than 1:1"),
        (0.8, 16 / 9, "works from 4:5 to 16:9"),
        (1.0, 1.0, "only works of about 1:1"),
        (None, None, ""),
    ],
)
def test_the_range_is_described_in_words(tallest, widest, phrase):
    assert shape.described(tallest, widest) == phrase
