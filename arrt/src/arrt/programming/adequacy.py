"""Whether a work is too small for a wall: Programming's judgement, from the screen the wall's Player reports.

`re-architecture.md` § Compositing moves to the Player: the Library keeps only
panel-independent facts (a picture's width and height, judged against its
quality profile), and **adequacy for a wall is Programming's**, comparing a
work's pixels with the geometry that wall's Player reports in its heartbeat. The
answer is one per wall ("too small for the living room"), and it informs the
curator; it takes nothing off the schedule, because a picture below the line is
shown rather than refused (`nonfunctional-requirements.md` § Output Quality).

**The line is half the box.** The box is the screen less a mat: 6% of the
shorter side at the sides and top and 1.15 of that below, the contract's rule for
a Player that knows no density (`player-contract.md` § Layout). A Player never
enlarges a work, so one smaller than the box is drawn at its own size, and a
work filling less than half the box along its longer reach reads as a postage
stamp. The 1,000 px quality minimum was chosen as right for a 1080p screen
(`re-architecture.md` § Open questions), and half a 4K box is about that, so the
two lines agree where they meet. The server does not know a Player's own mat
settings, so it judges with the contract's defaults: a judgement about whether a
work is big enough, not a prediction of pixels.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

#: The mat a Player with no density draws, as a share of the screen's shorter
#: side (`player-contract.md` § Layout; `contract/vectors/mat-geometry.json`'s
#: `relative_width`).
RELATIVE_MAT_WIDTH: Final[float] = 0.06
#: The bottom margin as a multiple of the side margin, the Player's default.
BOTTOM_WEIGHT: Final[float] = 1.15
#: Below this share of the box, along the work's longer reach, a work is too small.
TOO_SMALL_SHARE: Final[float] = 0.5


def box(screen: tuple[int, int]) -> tuple[int, int]:
    """The space a work is drawn into on this screen, inside the default mat."""
    width, height = screen
    side = _round_half_up(RELATIVE_MAT_WIDTH * min(width, height))
    bottom = _round_half_up(side * BOTTOM_WEIGHT)
    return max(1, width - 2 * side), max(1, height - side - bottom)


def too_small(screen: tuple[int, int], work: tuple[int, int]) -> bool:
    """Whether a work of this many pixels fills less than half of this screen's box."""
    box_width, box_height = box(screen)
    width, height = work
    return max(width / box_width, height / box_height) < TOO_SMALL_SHARE


def _round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
