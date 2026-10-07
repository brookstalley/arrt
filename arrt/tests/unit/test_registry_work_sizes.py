"""A work's size read from Wikidata is checked for plausibility before the page shows it.

The owner's ruling (`procurement-corpus.md` § Gaps, 4; `project-preferences.md`):
whatever first reads a size from the registry checks it before relying on it.
The corpus found sizes swapped, wrong or mis-scaled on Wikidata, and two of its
rows are the cases here, with the values Wikidata gave on 2026-10-05.
"""

import pytest

from arrt.library.registry import RegistryImageSize
from arrt.library.services.registry_works import plausible_size


def _picture(width, height):
    return RegistryImageSize(width=width, height=height)


@pytest.mark.parametrize(
    ("height", "width", "picture"),
    [
        (145.0, 113.0, _picture(2081, 2668)),  # Rhythms, from a photograph that includes its frame
        (79.4, 53.4, _picture(7479, 11146)),  # Mona Lisa
        (72.4, 48.5, _picture(512, 790)),  # Man with a Tulip: the widest good gap measured, 3.4%
        (134.0, 134.0, _picture(240, 238)),  # Simultaneous Disc, round on a square canvas
        (528.0, 24.8, None),  # a handscroll, 21:1, with no picture to compare
    ],
)
def test_a_size_that_agrees_with_its_picture_stands(height, width, picture):
    assert plausible_size(height, width, picture) == (height, width)


def test_a_size_whose_shape_disagrees_with_its_picture_is_unknown():
    """Corpus row 33, *Whaam!*: Wikidata gives it 406.4 tall and 272 wide; its picture is 2.35 : 1 the other way."""
    assert plausible_size(406.4, 272.0, _picture(3648, 2406)) == (None, None)


def test_a_mis_scaled_size_is_unknown_with_or_without_a_picture():
    """Corpus row 12, *Tête Dada*: 2,943 cm tall and 14 cm wide, a 29.43 cm head entered a hundredfold."""
    assert plausible_size(2943.0, 14.0, _picture(1044, 2180)) == (None, None)
    assert plausible_size(2943.0, 14.0, None) == (None, None)


@pytest.mark.parametrize(
    ("height", "width"),
    [(0.2, 30.0), (30.0, 0.2), (12500.0, 300.0), (300.0, 12500.0)],
    ids=["too-short", "too-narrow", "too-tall", "too-wide"],
)
def test_a_side_outside_what_any_work_measures_is_unknown(height, width):
    assert plausible_size(height, width, None) == (None, None)


def test_the_tolerance_sits_between_the_good_and_the_bad():
    """A shape 20% off its picture stands; 30% off does not (the good measured within 3.4%, the bad at 2.3x)."""
    picture = _picture(1000, 1000)

    assert plausible_size(120.0, 100.0, picture) == (120.0, 100.0)
    assert plausible_size(130.0, 100.0, picture) == (None, None)


def test_one_side_alone_is_checked_only_against_the_bounds():
    """With no width there is no shape to compare, so the picture cannot speak to it."""
    assert plausible_size(145.0, None, _picture(2081, 2668)) == (145.0, None)
    assert plausible_size(None, 14000.0, None) == (None, None)
    assert plausible_size(None, None, None) == (None, None)
