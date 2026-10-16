"""Constraint 12: the size verdict is derived, in one place, and never stored.

The Library judges a picture against its quality profile, a minimum in pixels on
the long edge that names no screen. These pin the rule at its boundary and on the
shapes that used to fool a panel-relative judgement.
"""

import pytest

from arrt.library.services.quality import Fit, QualityProfile
from arrt.services.errors import ServiceError

#: The owner's minimum (2026-10-06).
_PROFILE = QualityProfile(minimum_long_edge_px=1000)


def test_a_picture_exactly_at_the_minimum_meets_it():
    assert _PROFILE.judge(width=1000, height=700) is Fit.MEETS_MINIMUM


def test_a_picture_one_pixel_short_falls_below_it():
    assert _PROFILE.judge(width=999, height=700) is Fit.BELOW_MINIMUM


def test_a_tall_narrow_work_is_judged_on_its_long_edge():
    """Megapixels would call a 400 x 2400 scroll small; its long edge is not."""
    assert _PROFILE.judge(width=400, height=2400) is Fit.MEETS_MINIMUM
    assert _PROFILE.judge(width=2400, height=400) is Fit.MEETS_MINIMUM


def test_a_picture_smaller_than_a_television_box_but_over_the_minimum_meets_it():
    """The case the retired `matted_small` used to catch: 2000 x 1300 is smaller
    than the 3316 x 1597 box of a 42" Frame, which was a fact about that one
    television. Against the profile it is simply a scan that meets the minimum."""
    assert _PROFILE.judge(width=2000, height=1300) is Fit.MEETS_MINIMUM


def test_the_minimum_is_what_decides_not_a_constant():
    """A second profile moves the boundary, so the verdict reads the setting."""
    stricter = QualityProfile(minimum_long_edge_px=3840)

    assert _PROFILE.judge(width=2000, height=1300) is Fit.MEETS_MINIMUM
    assert stricter.judge(width=2000, height=1300) is Fit.BELOW_MINIMUM


@pytest.mark.parametrize(("width", "height"), [(0, 500), (500, 0), (-1, 500)])
def test_a_picture_with_no_size_is_refused_rather_than_judged(width, height):
    with pytest.raises(ServiceError, match="positive width and height"):
        _PROFILE.judge(width=width, height=height)


@pytest.mark.parametrize("minimum", [0, -1])
def test_a_minimum_that_is_not_positive_is_refused(minimum):
    """Zero would let any scan at all be chosen without a curator asking."""
    with pytest.raises(ServiceError, match="positive number of pixels"):
        QualityProfile(minimum_long_edge_px=minimum)


def test_there_is_no_verdict_about_a_screen():
    """Two values, and neither names a screen: the Library holds none."""
    assert {str(fit) for fit in Fit} == {"meets_minimum", "below_minimum"}
