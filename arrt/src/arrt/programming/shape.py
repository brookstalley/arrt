"""Which shapes of work a wall shows: the curator's range, how it is spelled, and what fits it.

A shape is width over height, measured on the work's presentation master, which
is written upright: a portrait photograph stored sideways is portrait here. A
wall holds a range: the tallest shape it shows and the widest, either of which
may be absent. Every wall that has chosen nothing shows every shape.

**Spelled `W:H`, or a decimal, or `any`.** A curator says "nothing wider than
1:1", so that is what the surfaces take and give back. `any` removes a bound in
words, because MCP drops a null argument before the binding sees it, so null
could never mean "no limit" there.

**Inclusive, with one per cent of give.** A square painting scanned at 3000 ×
3003 is square to anyone looking at it; a strict comparison would leave it off a
wall showing "nothing wider than 1:1".
"""

import math
from fractions import Fraction
from typing import Final

from arrt.services.errors import ServiceError

#: How far, as a share of the bound, a work's shape may stray past a bound and
#: still count as inside it.
TOLERANCE: Final[float] = 0.01

#: The word that removes a bound.
ANY: Final[str] = "any"

#: What reading a bound raises when it is not a number or divides by zero. A
#: named tuple rather than the unparenthesised form this plane's formatter writes,
#: because the root suite's seam guards parse this source on Python 3.12
#: (backlog #166).
_UNREADABLE: Final[tuple[type[Exception], ...]] = (ValueError, ZeroDivisionError)

#: The largest side a shape is spoken with, so 1.7778 reads "16:9" and an
#: irrational ratio still reads as something a person can picture.
_LARGEST_SIDE: Final[int] = 21


def parse(text: str) -> float | None:
    """A bound as a curator wrote it, as width over height; None for `any`.

    Refused by name when it is neither `W:H` with two positive numbers, a
    positive decimal, nor `any`.
    """
    spelled = text.strip().lower()
    if spelled == ANY:
        return None
    try:
        if ":" in spelled:
            width, _, height = spelled.partition(":")
            ratio = float(width) / float(height)
        else:
            ratio = float(spelled)
    except _UNREADABLE:
        ratio = math.nan
    if not math.isfinite(ratio) or ratio <= 0:
        raise ServiceError(
            f"A shape is width:height, such as 4:5 or 16:9, a positive decimal such as 0.8, or {ANY!r}; not {text!r}."
        )
    return ratio


def spoken(ratio: float) -> str:
    """A shape as a curator would say it: `16:9`, `1:1`, `4:5`."""
    near = Fraction(ratio).limit_denominator(_LARGEST_SIDE)
    if near.numerator <= _LARGEST_SIDE and abs(near - Fraction(ratio)) / Fraction(ratio) <= TOLERANCE / 2:
        return f"{near.numerator}:{near.denominator}"
    return f"{ratio:.2f}:1"


def require_range(tallest: float | None, widest: float | None) -> None:
    """Refuse a range whose tallest shape is wider than its widest, rather than swap it silently."""
    if tallest is not None and widest is not None and tallest > widest:
        raise ServiceError(
            f"The tallest shape, {spoken(tallest)}, is wider than the widest, {spoken(widest)}, "
            "so no work could fit. Swap them, or remove one."
        )


def fits(size: tuple[int, int], *, tallest: float | None, widest: float | None) -> bool:
    """Whether a work of this size is inside the range, each bound counted inclusively with `TOLERANCE`."""
    width, height = size
    ratio = width / height
    if tallest is not None and ratio < tallest * (1 - TOLERANCE):
        return False
    return not (widest is not None and ratio > widest * (1 + TOLERANCE))


def described(tallest: float | None, widest: float | None) -> str:
    """The range as a phrase finishing "This wall shows …", or the empty string when it has no limit."""
    if tallest is not None and widest is not None:
        if spoken(tallest) == spoken(widest):
            return f"only works of about {spoken(widest)}"
        return f"works from {spoken(tallest)} to {spoken(widest)}"
    if widest is not None:
        return f"nothing wider than {spoken(widest)}"
    if tallest is not None:
        return f"nothing taller than {spoken(tallest)}"
    return ""
