"""Whether a held image is big enough to keep — the one place that is decided.

**The Library judges a picture against its quality profile, never against a
screen.** A screen's size is a fact about one wall, and the Library has no
concept of a wall: per-wall adequacy ("too small for the living room") is
Programming's comparison against the geometry each Player reports. What the
Library asks is only whether a scan is big enough that it is worth choosing
without a curator asking for it, and that is a number of pixels that names no
device — Radarr's quality profile, minus the cutoff, which the owner ruled out
on 2026-10-02 (`upgrades.md` ruling 1).

**Judged on the long edge.** Megapixels were ruled out long ago, because a tall
narrow work has few of them and is not small; the long edge is the measure the
minimum, the presentation master's cap and the upgrade tiers all share.

The verdict is **derived and never stored**: the minimum is a deployment value,
and a stored verdict would go quietly wrong the day it changed. What is stored
is the pair of facts it is derived from, the picture's width and height.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from arrt.services.errors import ServiceError

#: The longest edge a presentation master is given, and so the most of any scan
#: a wall can ever show. Beyond it extra pixels are discarded when the master is
#: made, which is why ranking stops rewarding them here: two scans both larger
#: than this show identically. 7,680 is the size the Player's compositing budget
#: was measured against on a Pi 4 (`nonfunctional-requirements.md` § Performance).
PRESENTATION_MASTER_LONG_EDGE_PX: Final[int] = 7680


class Fit(StrEnum):
    """Whether a picture meets the quality profile's minimum.

    Two values and no third. A picture smaller than some screen is not a fact
    the Library can state, because it holds no screen; a picture whose size
    nobody recorded is not a verdict at all, and callers carry it as `None`.
    """

    #: The long edge reaches the minimum. Chosen automatically when it ranks first.
    MEETS_MINIMUM = "meets_minimum"
    #: The long edge falls short. Not a rejection: the picture is offered,
    #: labelled, and a curator may choose it; it is only never chosen for them.
    BELOW_MINIMUM = "below_minimum"


@dataclass(frozen=True, slots=True)
class QualityProfile:
    """What the Library will choose without being asked: a minimum, in pixels."""

    #: The shortest long edge a picture may have and still be chosen automatically.
    minimum_long_edge_px: int

    def __post_init__(self) -> None:
        if self.minimum_long_edge_px <= 0:
            raise ServiceError(f"The quality minimum must be a positive number of pixels, got {self.minimum_long_edge_px}.")

    def judge(self, *, width: int, height: int) -> Fit:
        """The verdict for a picture of `width` x `height` pixels."""
        if width <= 0 or height <= 0:
            raise ServiceError(f"An image must have a positive width and height, got {width}x{height}.")
        return Fit.MEETS_MINIMUM if max(width, height) >= self.minimum_long_edge_px else Fit.BELOW_MINIMUM
