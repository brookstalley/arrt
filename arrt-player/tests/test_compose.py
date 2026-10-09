"""The Player's compositor: the contract's geometry, drawn where it says.

`contract/vectors/mat-geometry.json` is the definition, and every vector in it is
run here, so a vector added to the contract is a test of this Player the moment it
lands. The drawing is then held to the same geometry by sampling pixels well
inside each region, away from the edges where JPEG rings.
"""

import json
from pathlib import Path
from typing import ClassVar

import pytest
from PIL import Image

from arrt_player import compose as compose_module
from arrt_player.compose import (
    DEFAULT_MAT_MODE,
    RELATIVE_MAT_WIDTH,
    Geometry,
    Rect,
    Uncomposable,
    compose,
    composition_key,
    layout,
    mat_mode,
    mat_rgb,
)

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
VECTORS = json.loads((CONTRACT / "vectors" / "mat-geometry.json").read_text(encoding="utf-8"))

SHA = "a" * 64
MAT = "#336699"
MAT_RGB = (0x33, 0x66, 0x99)
RED = (220, 20, 20)
BLUE = (20, 20, 220)
BLACK = (0, 0, 0)

#: A small screen with no density, so a test's arithmetic is checkable by hand:
#: the side margin is 6% of 300 = 18, the bottom 18 x 1.15 = 20.7, rounded to 21.
SCREEN = Geometry(screen=(400, 300), pixels_per_inch=None, mat_width_inches=1.5, bottom_weight=1.15)


def _geometry(case: dict) -> Geometry:
    """A vector's screen. One with no density carries no mat width, and NaN fails any arithmetic that reads it."""
    return Geometry(
        screen=(case["screen"]["width_px"], case["screen"]["height_px"]),
        pixels_per_inch=case["pixels_per_inch"],
        mat_width_inches=case.get("mat_width_inches", float("nan")),
        bottom_weight=case.get("bottom_weight", float("nan")),
    )


def _rect(expected: dict | None) -> Rect | None:
    return None if expected is None else Rect(**expected)


def a_master(path: Path, size: tuple[int, int], *, colour=RED, mode: str = "RGB", exif=None) -> Path:
    image = Image.new(mode, size, colour if mode == "RGB" else (0, 255, 255, 0))
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(path, format="JPEG", quality=95, **kwargs)
    return path


def close_to(pixel: tuple[int, ...], expected: tuple[int, int, int], tolerance: int = 12) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel[:3], expected, strict=True))


class TestTheContractsGeometry:
    @pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["name"])
    def test_each_vector_is_where_this_player_puts_the_work_and_its_mat(self, vector: dict):
        case = vector["input"]

        placed = layout(_geometry(case), case["mat_mode"], (case["work"]["width_px"], case["work"]["height_px"]))

        assert placed.work == _rect(vector["expect"]["work"])
        assert placed.mat == _rect(vector["expect"]["mat"])

    def test_the_relative_width_is_the_contracts(self):
        assert VECTORS["relative_width"] == RELATIVE_MAT_WIDTH

    def test_the_work_is_centred_in_the_box_not_on_the_screen(self):
        """Centring on the screen keeps every size right and undoes the bottom weighting."""
        placed = layout(SCREEN, "proportional", (100, 100))

        below = SCREEN.screen[1] - (placed.work.top + placed.work.height)
        assert below > placed.work.top, "the work sits higher than centre, so the deeper margin is below it"


class TestTheModeAndColourDrawn:
    @pytest.mark.parametrize("mode", ["none", "proportional", "full"])
    def test_a_mode_the_contract_names_is_drawn(self, mode: str):
        assert mat_mode(mode) == mode

    @pytest.mark.parametrize("setting", [None, "", "floating", 3, {"mode": "full"}])
    def test_a_mode_this_player_does_not_know_is_the_default(self, setting: object):
        assert mat_mode(setting) == DEFAULT_MAT_MODE == "proportional"

    def test_a_readable_colour_is_its_rgb(self):
        assert mat_rgb(MAT) == MAT_RGB

    @pytest.mark.parametrize(
        "colour", [None, "", "336699", "#33669", "#3366999", "#33669g", "#336699 ", "#336699\n", "#FFFFFF", 0x336699]
    )
    def test_a_colour_that_is_not_the_contracts_hex_is_unreadable(self, colour: object):
        assert mat_rgb(colour) is None


class TestTheDrawing:
    def test_proportional_is_the_work_in_a_mat_of_its_shape_on_black(self, tmp_path: Path):
        master = a_master(tmp_path / "m.jpg", (600, 400))

        path = compose(master, master_sha256=SHA, mat_color=MAT, mode="proportional", geometry=SCREEN, directory=tmp_path)

        placed = layout(SCREEN, "proportional", (600, 400))
        with Image.open(path) as drawn:
            assert drawn.size == SCREEN.screen
            work, mat = placed.work, placed.mat
            assert close_to(drawn.getpixel((work.left + work.width // 2, work.top + work.height // 2)), RED)
            assert close_to(drawn.getpixel((work.left + work.width // 2, mat.top + 4)), MAT_RGB), "the mat above the work"
            assert close_to(
                drawn.getpixel((work.left + work.width // 2, mat.top + mat.height - 4)), MAT_RGB
            ), "the deeper mat below it"
            assert close_to(drawn.getpixel((2, 2)), BLACK), "beyond the mat is black"

    def test_full_paints_the_mat_to_every_edge(self, tmp_path: Path):
        master = a_master(tmp_path / "m.jpg", (100, 300))

        path = compose(master, master_sha256=SHA, mat_color=MAT, mode="full", geometry=SCREEN, directory=tmp_path)

        with Image.open(path) as drawn:
            for corner in [(2, 2), (397, 2), (2, 297), (397, 297)]:
                assert close_to(drawn.getpixel(corner), MAT_RGB), corner

    def test_none_is_the_work_on_black(self, tmp_path: Path):
        master = a_master(tmp_path / "m.jpg", (100, 300))

        path = compose(master, master_sha256=SHA, mat_color=MAT, mode="none", geometry=SCREEN, directory=tmp_path)

        placed = layout(SCREEN, "none", (100, 300))
        with Image.open(path) as drawn:
            assert placed.work.height == SCREEN.screen[1], "with no mat the box is the whole screen"
            assert close_to(drawn.getpixel((placed.work.left - 4, 150)), BLACK)
            assert close_to(drawn.getpixel((placed.work.left + 50, 150)), RED)

    def test_a_work_with_an_unreadable_colour_is_drawn_as_none(self, tmp_path: Path):
        """Inventing a colour would put up a mat the Library never chose."""
        master = a_master(tmp_path / "m.jpg", (600, 400))

        path = compose(master, master_sha256=SHA, mat_color="#zzzzzz", mode="proportional", geometry=SCREEN, directory=tmp_path)

        placed = layout(SCREEN, "none", (600, 400))
        with Image.open(path) as drawn:
            assert close_to(drawn.getpixel((200, placed.work.top - 4)), BLACK)
            assert close_to(drawn.getpixel((200, 150)), RED)

    def test_a_small_work_is_never_enlarged(self, tmp_path: Path):
        master = a_master(tmp_path / "m.jpg", (50, 40))

        path = compose(master, master_sha256=SHA, mat_color=MAT, mode="proportional", geometry=SCREEN, directory=tmp_path)

        placed = layout(SCREEN, "proportional", (50, 40))
        assert (placed.work.width, placed.work.height) == (50, 40)
        with Image.open(path) as drawn:
            assert close_to(drawn.getpixel((placed.work.left - 6, placed.work.top + 20)), MAT_RGB), "a mat of the usual width"
            assert close_to(drawn.getpixel((placed.mat.left - 6, placed.work.top + 20)), BLACK), "and black around it"

    def test_a_turned_master_is_composed_upright(self, tmp_path: Path):
        """EXIF orientation 6 stores a landscape picture turned a quarter, its right edge uppermost.

        The master is two colours, so a picture that is only stretched to the
        upright shape, rather than turned, is told apart from one turned.
        """
        stored = Image.new("RGB", (200, 400), RED)
        stored.paste(BLUE, (0, 200, 200, 400))
        exif = Image.Exif()
        exif[0x0112] = 6
        master = tmp_path / "m.jpg"
        stored.save(master, format="JPEG", quality=95, exif=exif)

        path = compose(master, master_sha256=SHA, mat_color=MAT, mode="none", geometry=SCREEN, directory=tmp_path)

        upright = layout(SCREEN, "none", (400, 200)).work
        assert upright.width > upright.height
        with Image.open(path) as drawn:
            # Turned upright, the stored bottom (blue) is on the left and the stored
            # top (red) on the right; stretched without turning, both of these
            # upper-quarter points would be red.
            assert close_to(drawn.getpixel((upright.left + 10, upright.top + upright.height // 4)), BLUE)
            assert close_to(drawn.getpixel((upright.left + upright.width - 10, upright.top + upright.height // 4)), RED)

    def test_a_cmyk_master_is_composed(self, tmp_path: Path):
        master = a_master(tmp_path / "m.jpg", (300, 200), mode="CMYK")

        path = compose(master, master_sha256=SHA, mat_color=MAT, mode="proportional", geometry=SCREEN, directory=tmp_path)

        with Image.open(path) as drawn:
            assert drawn.mode == "RGB"
            assert drawn.size == SCREEN.screen

    def test_a_large_master_is_drawn_at_exactly_the_layouts_size(self, tmp_path: Path):
        """Decoded at a reduced scale, then sized to the layout, never to an image library's own fit."""
        master = a_master(tmp_path / "m.jpg", (4000, 3000))
        frame = Geometry(screen=(1920, 1080), pixels_per_inch=50.0, mat_width_inches=1.5, bottom_weight=1.15)

        path = compose(master, master_sha256=SHA, mat_color=MAT, mode="none", geometry=frame, directory=tmp_path)

        placed = layout(frame, "none", (4000, 3000))
        with Image.open(path) as drawn:
            left, right = placed.work.left, placed.work.left + placed.work.width
            assert close_to(drawn.getpixel((left + 3, 540)), RED)
            assert close_to(drawn.getpixel((left - 3, 540)), BLACK)
            assert close_to(drawn.getpixel((right - 3, 540)), RED)
            assert close_to(drawn.getpixel((right + 3, 540)), BLACK)

    def test_a_master_that_is_not_an_image_is_uncomposable(self, tmp_path: Path):
        master = tmp_path / "m.jpg"
        master.write_bytes(b"not a picture")

        with pytest.raises(Uncomposable, match=r"m\.jpg"):
            compose(master, master_sha256=SHA, mat_color=MAT, mode="proportional", geometry=SCREEN, directory=tmp_path / "out")

        assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())

    def test_a_failed_write_leaves_no_file_a_driver_could_pick_up(self, tmp_path: Path, monkeypatch):
        master = a_master(tmp_path / "m.jpg", (600, 400))
        out = tmp_path / "out"
        out.mkdir()
        neighbour = out / "another-work.jpg"
        neighbour.write_bytes(b"composed earlier")

        def full_disk(self, fp, *args, **kwargs):
            Path(fp).write_bytes(b"half a pic")
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(Image.Image, "save", full_disk)

        with pytest.raises(OSError, match="No space"):
            compose(master, master_sha256=SHA, mat_color=MAT, mode="proportional", geometry=SCREEN, directory=out)

        assert sorted(p.name for p in out.iterdir()) == ["another-work.jpg"]
        assert neighbour.read_bytes() == b"composed earlier"

    def test_a_work_already_composed_is_not_composed_again(self, tmp_path: Path, monkeypatch):
        master = a_master(tmp_path / "m.jpg", (600, 400))
        first = compose(master, master_sha256=SHA, mat_color=MAT, mode="proportional", geometry=SCREEN, directory=tmp_path)

        def no_decode(*args, **kwargs):
            raise AssertionError("decoded again")

        monkeypatch.setattr(compose_module, "_draw", no_decode)

        again = compose(master, master_sha256=SHA, mat_color=MAT, mode="proportional", geometry=SCREEN, directory=tmp_path)

        assert again == first


class TestTheKey:
    """Everything that moves a pixel, and nothing else."""

    BASE: ClassVar[dict] = {"master_sha256": SHA, "mat_color": MAT, "mode": "proportional", "geometry": SCREEN}

    def key(self, **changes) -> str:
        return composition_key(**{**self.BASE, **changes})

    @pytest.mark.parametrize(
        "changes",
        [
            {"master_sha256": "b" * 64},
            {"mat_color": "#336698"},
            {"mode": "full"},
            {"mode": "none"},
            {"geometry": Geometry(screen=(400, 301), pixels_per_inch=None, mat_width_inches=1.5, bottom_weight=1.15)},
            {"geometry": Geometry(screen=(400, 300), pixels_per_inch=None, mat_width_inches=1.5, bottom_weight=1.4)},
            {"geometry": Geometry(screen=(400, 300), pixels_per_inch=10.0, mat_width_inches=1.5, bottom_weight=1.15)},
        ],
    )
    def test_a_change_that_moves_a_pixel_changes_it(self, changes: dict):
        assert self.key(**changes) != self.key()

    def test_the_drawing_rule_is_in_it(self, monkeypatch):
        before = self.key()
        monkeypatch.setattr(compose_module, "DRAWING_RULE", "another-rule")
        assert self.key() != before

    def test_a_mat_width_in_inches_moves_nothing_on_a_screen_with_no_density(self):
        unchanged = Geometry(screen=(400, 300), pixels_per_inch=None, mat_width_inches=3.0, bottom_weight=1.15)
        assert self.key(geometry=unchanged) == self.key()

    def test_a_colour_moves_nothing_with_no_mat(self):
        assert self.key(mode="none", mat_color="#000000") == self.key(mode="none")

    def test_an_unreadable_colour_is_the_same_picture_as_no_mat(self):
        assert self.key(mat_color="#zzzzzz") == self.key(mode="none")
