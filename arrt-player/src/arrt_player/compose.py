"""Composing a major 2 work for this Player's own screen: the mat and the picture.

**The geometry is the contract's, not this module's.** `player-contract.md`
§ Layout states it and `contract/vectors/mat-geometry.json` gives it as numbers,
and this Player's suite runs every vector through `layout`. The drawing then
places pixels exactly where `layout` says, so there is one answer to "where does
the work go", never a second one worked out by an image library's fitting
arithmetic.

**The mat takes the work's shape, and everything beyond it is black**
(`nonfunctional-requirements.md` § The mat is geometric). `full` is the one mode
that paints the mat colour to the screen's edges, and `none` puts the work on
black. **No work is ever enlarged**: a small master is drawn at its own size,
inside a mat of the usual width, with more black around it.

The server's compositor draws the same rule for major 1 until the cutover
(wave 4g), and both are held to the same vectors.
"""

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)

#: The mat modes `settings.mat.mode` may name.
MAT_MODES: Final[tuple[str, ...]] = ("none", "proportional", "full")

#: What a wall shows when no layer of settings names a mode, or names one this
#: Player does not know: the work-shaped mat every wall has shown since wave 2.
DEFAULT_MAT_MODE: Final[str] = "proportional"

#: The mat's side and top margin as a fraction of the screen's shorter side, for
#: a display that cannot know its pixel density (the owner, 2026-10-08). On a 50"
#: Frame it is within a few pixels of the 1.5 inch rule, so a screen and a Frame
#: show the same proportion. A test holds it to the vector file's own value.
RELATIVE_MAT_WIDTH: Final[float] = 0.06

#: The drawing rule, named. It is part of every composed file's key, so a change
#: to how the same geometry is drawn recomposes the files drawn the old way.
#: Change it whenever that happens.
DRAWING_RULE: Final[str] = "work-shaped-mat-1"

#: JPEG at the presentation master's own quality: both the Frame and the screen
#: read it, and the file is regenerable from the cached master at any time.
JPEG_QUALITY: Final[int] = 95

_HEX: Final = re.compile(r"^#[0-9a-f]{6}$")

#: EXIF orientations that turn the picture a quarter, so its upright width is its
#: stored height.
_QUARTER_TURNS: Final[frozenset[int]] = frozenset({5, 6, 7, 8})
_ORIENTATION_TAG: Final[int] = 0x0112


class Uncomposable(Exception):
    """The master could not be read as an image. It costs this work, never the wall."""


@dataclass(frozen=True)
class Geometry:
    """One screen, as a driver knows it.

    `pixels_per_inch` is None for a display that cannot know its physical size,
    which then takes the relative mat width. The mat's inches and its bottom
    weight are the Player's configuration (`feeds-and-players.md` ruling 7).
    """

    screen: tuple[int, int]
    pixels_per_inch: float | None
    mat_width_inches: float
    bottom_weight: float

    def margins(self, mode: str) -> tuple[int, int]:
        """The side-and-top margin and the bottom margin, in whole pixels."""
        if mode == "none":
            return 0, 0
        if self.pixels_per_inch is None:
            side = _round_half_up(RELATIVE_MAT_WIDTH * min(self.screen))
        else:
            side = _round_half_up(self.mat_width_inches * self.pixels_per_inch)
        return side, _round_half_up(side * self.bottom_weight)


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class Layout:
    """Where the work and its mat go on the screen. `mat` is None in mode `none`."""

    work: Rect
    mat: Rect | None


def pixels_per_inch(*, width_px: int, height_px: int, diagonal_inches: float) -> float:
    """A panel's density from its pixel size and its diagonal."""
    return math.hypot(width_px, height_px) / diagonal_inches


def mat_mode(setting: object) -> str:
    """The mode to draw for a feed's `settings.mat.mode`.

    A mode this Player does not know is a setting it cannot honour, which it
    ignores (`player-contract.md` § Presentation settings) rather than refusing
    the feed or drawing nothing.
    """
    return setting if isinstance(setting, str) and setting in MAT_MODES else DEFAULT_MAT_MODE


def mat_rgb(mat_color: object) -> tuple[int, int, int] | None:
    """A work's mat colour, or None when it cannot be read.

    A work with an unreadable colour is drawn on black with no mat, because
    inventing a colour would put up a mat the Library never chose.
    """
    if not isinstance(mat_color, str) or not _HEX.fullmatch(mat_color):
        return None
    return int(mat_color[1:3], 16), int(mat_color[3:5], 16), int(mat_color[5:7], 16)


def layout(geometry: Geometry, mode: str, work_size: tuple[int, int]) -> Layout:
    """`player-contract.md` § Layout: the work and its mat on one screen.

    **The work is centred in the box, not on the screen.** The box sits higher
    than centre because its bottom margin is the deeper one, and centring on the
    screen would undo the bottom weighting while every size stayed right.
    """
    screen_w, screen_h = geometry.screen
    work_w, work_h = work_size
    side, bottom = geometry.margins(mode)
    box_w = max(1, screen_w - 2 * side)
    box_h = max(1, screen_h - side - bottom)
    scale = min(box_w / work_w, box_h / work_h, 1.0)
    width = max(1, _round_half_up(work_w * scale))
    height = max(1, _round_half_up(work_h * scale))
    work = Rect(left=side + (box_w - width) // 2, top=side + (box_h - height) // 2, width=width, height=height)
    if mode == "none":
        mat = None
    elif mode == "full":
        mat = Rect(left=0, top=0, width=screen_w, height=screen_h)
    else:
        mat = Rect(left=work.left - side, top=work.top - side, width=width + 2 * side, height=height + side + bottom)
    return Layout(work=work, mat=mat)


def composition_key(*, master_sha256: str, mat_color: object, mode: str, geometry: Geometry) -> str:
    """The name of the file this work composes to on this screen.

    **Keyed on everything that moves a pixel and nothing else**: the master,
    the colour and mode actually drawn, the screen and the margins in pixels,
    and the drawing rule. So a changed mat width, density or screen mode
    recomposes, and a change that moves no pixel does not. The Frame binds an
    upload to a file's path, so a new key is a new upload.
    """
    drawn_mode, rgb = _drawn(mode, mat_color)
    side, bottom = geometry.margins(drawn_mode)
    colour = "none" if rgb is None else "".join(f"{channel:02x}" for channel in rgb)
    parts = (
        DRAWING_RULE,
        master_sha256,
        drawn_mode,
        colour,
        f"{geometry.screen[0]}x{geometry.screen[1]}",
        f"{side},{bottom}",
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def compose(
    master: Path,
    *,
    master_sha256: str,
    mat_color: object,
    mode: str,
    geometry: Geometry,
    directory: Path,
) -> Path:
    """Draw `master` for `geometry` into `directory`, named by its key, and return the file.

    A file already composed under the same key is returned as it is. The file
    appears only once a whole picture has been written, so a compose that fails
    partway leaves nothing a driver could pick up.

    Raises `Uncomposable` for a master that cannot be decoded, and lets an
    `OSError` from writing through: a full disk is this machine's fault, not
    the master's, and the two send whoever reads the journal to different places.
    """
    key = composition_key(master_sha256=master_sha256, mat_color=mat_color, mode=mode, geometry=geometry)
    destination = directory / f"{key}.jpg"
    if destination.is_file():
        return destination
    drawn_mode, rgb = _drawn(mode, mat_color)
    canvas = _draw(master, geometry=geometry, mode=drawn_mode, rgb=rgb)

    directory.mkdir(parents=True, exist_ok=True)
    staged = destination.with_name(f"{destination.name}.composing")
    try:
        canvas.save(staged, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        staged.replace(destination)
    except OSError:
        staged.unlink(missing_ok=True)
        raise
    log.info(
        "composed %s for %sx%s in mode %s",
        master.name,
        geometry.screen[0],
        geometry.screen[1],
        drawn_mode,
        extra={"event": "compose.done", "composed_path": str(destination)},
    )
    return destination


def _drawn(mode: str, mat_color: object) -> tuple[str, tuple[int, int, int] | None]:
    """The mode and colour actually drawn: a mat with no readable colour is no mat."""
    rgb = mat_rgb(mat_color)
    if rgb is None or mode == "none":
        return "none", None
    return mode, rgb


def _draw(master: Path, *, geometry: Geometry, mode: str, rgb: tuple[int, int, int] | None) -> Image.Image:
    """The composed picture, in memory. Only reading the master is translated to `Uncomposable`."""
    try:
        with Image.open(master) as image:
            upright_size = _upright_size(image)
            placed = layout(geometry, mode, upright_size)
            # Decoding a 7,680 px JPEG at a reduced scale is most of what keeps a
            # compose inside the Pi's budget. The request is square on the longer
            # side so it holds whichever way the picture is turned.
            longer = max(placed.work.width, placed.work.height)
            image.draft("RGB", (longer, longer))
            upright = (ImageOps.exif_transpose(image) or image).convert("RGB")
            if upright.size != (placed.work.width, placed.work.height):
                upright = upright.resize((placed.work.width, placed.work.height), Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise Uncomposable(f"{master.name} could not be read as an image ({exc})") from exc

    canvas = Image.new("RGB", geometry.screen, (0, 0, 0))
    if placed.mat is not None and rgb is not None:
        mat = placed.mat
        canvas.paste(rgb, (mat.left, mat.top, mat.left + mat.width, mat.top + mat.height))
    canvas.paste(upright, (placed.work.left, placed.work.top))
    return canvas


def _upright_size(image: Image.Image) -> tuple[int, int]:
    """The picture's size as it is shown, which a quarter-turn EXIF orientation swaps."""
    width, height = image.size
    if image.getexif().get(_ORIENTATION_TAG) in _QUARTER_TURNS:
        return height, width
    return width, height


def _round_half_up(value: float) -> int:
    """The contract's rounding. Python's `round` goes to even on a half, which no other Player's language does."""
    return math.floor(value + 0.5)


__all__ = [
    "DEFAULT_MAT_MODE",
    "DRAWING_RULE",
    "MAT_MODES",
    "RELATIVE_MAT_WIDTH",
    "Geometry",
    "Layout",
    "Rect",
    "Uncomposable",
    "compose",
    "composition_key",
    "layout",
    "mat_mode",
    "mat_rgb",
    "pixels_per_inch",
]
