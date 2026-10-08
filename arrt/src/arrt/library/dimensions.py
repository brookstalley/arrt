"""A work's dimensions as a label sets them: one system of units, whole numbers.

**The stored string is the source's and stays the source's** (`data-model.md`,
`dimensions`: "as the source states them"). Museums write both systems, in
either order, with fractions of an inch, a comma for a decimal point, a letter
on each number, and several measurements in one string. A wall label reads
better with one system and round numbers, so this turns the first measurement
into the units the deployment asks for, at the moment the label's text is set,
and never writes anything back.

**What it cannot read, it leaves alone.** A string with no measurement this
recognises comes back unchanged: the source's own words are a better label than
nothing, and a better one than a guess.
"""

import math
import re
from enum import StrEnum
from fractions import Fraction
from typing import Final


class Units(StrEnum):
    """The system a label states a work's dimensions in."""

    IMPERIAL = "imperial"
    METRIC = "metric"


#: How many of each unit make an inch.
_PER_INCH: Final[dict[str, Fraction]] = {
    "in": Fraction(1),
    "cm": Fraction(254, 100),
    "mm": Fraction(254, 10),
}

#: A number as museums write one: a whole number and a fraction ("29 7/16"), a
#: fraction alone ("13/16"), or whole or decimal (with a point or a comma). The
#: fractions come first, because an alternation takes the first branch that
#: matches, and "13" alone matches the start of "13/16".
_NUMBER: Final = r"\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?"

#: One measured value, with the letter some sources put on it ("w203", "h53").
#: The letter must begin a word, so the "h" ending "Width" is not taken for one.
_VALUE: Final = rf"(?:\b[whdWHD]\s*)?(?:{_NUMBER})"

#: Values joined by "×" or "x", then the unit they are all in.
_MEASUREMENT: Final = re.compile(
    rf"(?P<values>{_VALUE}(?:\s*[×xX]\s*{_VALUE})*)\s*(?P<unit>cm|mm|inches|inch|in\b\.?|\")",
)

_ONE_VALUE: Final = re.compile(rf"(?:\b(?P<letter>[whdWHD]))?\s*(?P<number>{_NUMBER})")


def for_label(dimensions: str | None, units: Units) -> str | None:
    """The first measurement in `dimensions`, in `units`, rounded to whole units.

    "76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)" is "30 × 38 in" in imperial and
    "77 × 97 cm" in metric. Words before the first measurement stay with it
    ("Image/paper: 8 × 10 in", "H. 8 in"); later measurements (a mount, a frame,
    a repeat, side panels) are dropped. The source's figures in the asked-for
    system are preferred to a conversion of the other's, since they are what it
    measured.

    **A part this does not wholly read is left as the source wrote it**: two
    measurements in one system ("30 cm × 40 cm"), or a figure outside any
    measurement, would otherwise lose a dimension without saying so.
    """
    if dimensions is None:
        return None
    first = _first_part(dimensions)
    found = list(_MEASUREMENT.finditer(first))
    if not found or not _wholly_read(first, found):
        return dimensions
    qualifier = first[: found[0].start()].strip()
    measurements = [(match.group("values"), _unit(match.group("unit"))) for match in found]
    target = "in" if units is Units.IMPERIAL else "cm"
    values, unit = next(
        ((values, unit) for values, unit in measurements if _system(unit) == _system(target)),
        measurements[0],
    )
    stated = " × ".join(_converted(match, unit, target) for match in _ONE_VALUE.finditer(values))
    text = f"{stated} {target}"
    return f"{qualifier} {text}" if qualifier else text


def _wholly_read(part: str, found: list[re.Match[str]]) -> bool:
    """At most one measurement per system, and no figure left outside them."""
    systems = [_system(_unit(match.group("unit"))) for match in found]
    if len(systems) != len(set(systems)):
        return False
    outside = part
    for match in found:
        outside = outside.replace(match.group(0), "", 1)
    return not re.search(r"\d", outside)


def _first_part(dimensions: str) -> str:
    """The first measurement's stretch of the string: up to a semicolon or a line break."""
    for part in re.split(r"[;\n]", dimensions):
        if part.strip():
            return part.strip()
    return dimensions.strip()


def _unit(spelled: str) -> str:
    spelled = spelled.lower().rstrip(".")
    return "in" if spelled in {"in", "inch", "inches", '"'} else spelled


def _system(unit: str) -> str:
    return "imperial" if unit == "in" else "metric"


def _converted(value: re.Match[str], unit: str, target: str) -> str:
    """One value, in the target unit, rounded half up to a whole number.

    A value under one whole unit keeps one decimal place, and is never stated
    as less than 0.1, because rounding it would state a size of nothing.
    """
    amount = _parsed(value.group("number")) / _PER_INCH[unit] * _PER_INCH[target]
    shown = f"{max(float(amount), 0.1):.1f}" if amount < 1 else str(math.floor(amount + Fraction(1, 2)))
    return f"{(value.group('letter') or '').lower()}{shown}"


def _parsed(number: str) -> Fraction:
    whole, _, fraction = number.replace(",", ".").partition(" ")
    if "/" in whole:
        return Fraction(whole)
    amount = Fraction(whole)
    return amount + Fraction(fraction.strip()) if fraction.strip() else amount
