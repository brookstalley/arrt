"""The HDMI output: fitting a render to its screen, and what it does as screens come and go.

The device is a double that records what it was asked to put on a connector;
`LibdrmDevice` itself is exercised on the Pi's connector (`hdmi-output-findings.md`).
Whether a screen is present is read from a `/sys/class/drm` built per test, as
the client heartbeat reads it, and a test plugs and unplugs by rewriting it.
"""

import logging
from pathlib import Path

import pytest
from fakes import drm_tree
from PIL import Image

from arrt_player import __main__ as entry
from arrt_player.kms import KmsOutput, ScreenAbsent, fitted, scanout_bytes

MATTE = (28, 28, 28)
PAINT = (230, 200, 20)


def render(path: Path, size: tuple[int, int]) -> Path:
    """A matted render: paint inside a mat, so an edge lost to cropping would show."""
    image = Image.new("RGB", size, MATTE)
    image.paste(Image.new("RGB", (size[0] // 2, size[1] // 2), PAINT), (size[0] // 4, size[1] // 4))
    image.save(path, quality=95)
    return path


# -- fitting -----------------------------------------------------------------------


def test_a_16_by_9_render_on_a_4_by_3_screen_is_letterboxed_whole(tmp_path):
    picture = fitted(render(tmp_path / "w.jpg", (3840, 2160)), (1024, 768))

    assert picture.size == (1024, 768)
    # 3840x2160 scaled to 1024 wide is 576 high: 96 rows of black above and below.
    assert picture.getpixel((512, 40)) == (0, 0, 0)
    assert picture.getpixel((512, 727)) == (0, 0, 0)
    assert _near(picture.getpixel((512, 100)), MATTE), "the mat's top edge was lost"
    assert _near(picture.getpixel((512, 667)), MATTE), "the mat's bottom edge was lost"
    assert _near(picture.getpixel((3, 384)), MATTE), "the picture does not reach the screen's sides"
    assert _near(picture.getpixel((512, 384)), PAINT)


def test_a_portrait_render_on_a_wide_screen_is_pillarboxed_and_centred(tmp_path):
    picture = fitted(render(tmp_path / "w.jpg", (1000, 2000)), (1920, 1080))

    # 1000x2000 scaled to 1080 high is 540 wide, centred: black to x=690, from x=1230.
    assert picture.getpixel((680, 540)) == (0, 0, 0)
    assert picture.getpixel((1240, 540)) == (0, 0, 0)
    assert _near(picture.getpixel((700, 540)), MATTE)
    assert _near(picture.getpixel((960, 540)), PAINT)


def test_a_render_smaller_than_the_screen_is_scaled_up_to_fill_it(tmp_path):
    picture = fitted(render(tmp_path / "w.jpg", (640, 360)), (3840, 2160))

    assert _near(picture.getpixel((4, 4)), MATTE), "a small render was left small in the middle of the screen"
    assert _near(picture.getpixel((3835, 2155)), MATTE)


def test_a_render_already_the_screens_size_is_drawn_as_it_is(tmp_path):
    source = render(tmp_path / "w.png", (1920, 1080))

    assert fitted(source, (1920, 1080)).tobytes() == Image.open(source).convert("RGB").tobytes()


def test_the_scanout_is_blue_green_red_then_an_unused_byte():
    # XRGB8888 is little-endian: yellow drawn as anything but 00 FF FF is the
    # red/blue swap that turns it pale blue on the screen.
    assert scanout_bytes(Image.new("RGB", (1, 1), (255, 255, 0)))[:3] == bytes([0, 255, 255])
    assert len(scanout_bytes(Image.new("RGB", (4, 3)))) == 4 * 3 * 4


# -- screens coming and going ------------------------------------------------------------


class FakeDevice:
    """A card whose connectors are whatever the test says, recording every picture put on one."""

    def __init__(self, modes: dict[str, tuple[int, int] | None]) -> None:
        self.modes = modes
        self.presented: list[tuple[str, tuple[int, int], int]] = []
        self.fails: Exception | None = None

    def mode(self, connector: str) -> tuple[int, int]:
        size = self.modes.get(connector)
        if size is None:
            raise ScreenAbsent(connector)
        return size

    def present(self, connector: str, size: tuple[int, int], pixels: bytes) -> None:
        if self.fails is not None:
            raise self.fails
        if self.modes.get(connector) != size:
            raise ScreenAbsent(connector)
        self.presented.append((connector, size, len(pixels)))


class Bench:
    """One connector on card1, a device double, and the means to plug and unplug."""

    def __init__(self, tmp_path: Path, *, status: str = "connected", size: tuple[int, int] | None = (1280, 720)) -> None:
        self.root = drm_tree(
            tmp_path / "drm",
            {
                "card1-HDMI-A-1": (status, f"{size[0]}x{size[1]}\n" if size else ""),
                "card1-HDMI-A-2": ("disconnected", ""),
            },
        )
        self.device = FakeDevice({"hdmi-a-1": size if status == "connected" else None})
        self.opened: list[Path] = []
        self.output = KmsOutput("hdmi-a-1", drm_root=self.root, dev_root=tmp_path / "dev", device_for=self._open)
        self.render = render(tmp_path / "w1.jpg", (1920, 1080))

    def _open(self, path: Path) -> FakeDevice:
        self.opened.append(path)
        return self.device

    def plug(self, size: tuple[int, int]) -> None:
        connector = self.root / "card1-HDMI-A-1"
        (connector / "status").write_text("connected\n")
        (connector / "modes").write_text(f"{size[0]}x{size[1]}\n{size[0] // 2}x{size[1] // 2}\n")
        self.device.modes["hdmi-a-1"] = size

    def unplug(self) -> None:
        connector = self.root / "card1-HDMI-A-1"
        (connector / "status").write_text("disconnected\n")
        (connector / "modes").write_text("")
        self.device.modes["hdmi-a-1"] = None

    @property
    def sizes(self) -> list[tuple[int, int]]:
        return [size for _, size, _ in self.device.presented]


def test_a_render_is_drawn_at_the_connected_screens_size_on_the_card_that_lists_it(tmp_path):
    bench = Bench(tmp_path, size=(1280, 720))

    bench.output.show(bench.render)

    assert bench.device.presented == [("hdmi-a-1", (1280, 720), 1280 * 720 * 4)]
    assert bench.opened == [tmp_path / "dev" / "card1"]
    assert (bench.output.connected, bench.output.screen) == (True, (1280, 720))


def test_with_no_screen_nothing_is_drawn_nothing_raises_and_it_is_said_once(tmp_path, caplog):
    bench = Bench(tmp_path, status="disconnected", size=None)

    with caplog.at_level(logging.INFO):
        bench.output.show(bench.render)
        bench.output.refresh()
        bench.output.show(bench.render)

    assert bench.device.presented == []
    assert [record.__dict__.get("event") for record in caplog.records] == ["screen.absent"]
    assert (bench.output.connected, bench.output.screen) == (False, None)


def test_a_screen_plugged_in_after_the_render_arrived_is_drawn_on_the_next_refresh(tmp_path, caplog):
    bench = Bench(tmp_path, status="disconnected", size=None)
    with caplog.at_level(logging.INFO):
        bench.output.show(bench.render)
        bench.plug((3840, 2160))
        bench.output.refresh()
        bench.output.refresh()

    assert bench.sizes == [(3840, 2160)], "drawn other than once for one screen arriving"
    assert [record.__dict__.get("event") for record in caplog.records] == ["screen.absent", "screen.returned"]


def test_a_refresh_with_nothing_changed_draws_nothing(tmp_path):
    bench = Bench(tmp_path)
    bench.output.show(bench.render)

    for _ in range(3):
        bench.output.refresh()

    assert len(bench.device.presented) == 1


def test_a_screen_unplugged_and_plugged_back_is_drawn_again(tmp_path):
    # The kernel kept the picture through a replug on the Pi, but what comes back
    # need not be the screen that left, so the output draws regardless.
    bench = Bench(tmp_path, size=(1920, 1080))
    bench.output.show(bench.render)

    bench.unplug()
    bench.output.refresh()
    bench.plug((1920, 1080))
    bench.output.refresh()
    bench.output.refresh()

    assert bench.sizes == [(1920, 1080), (1920, 1080)]


def test_a_different_screen_is_drawn_at_its_own_size(tmp_path):
    bench = Bench(tmp_path, size=(1920, 1080))
    bench.output.show(bench.render)

    bench.plug((1024, 768))
    bench.output.refresh()

    assert bench.sizes == [(1920, 1080), (1024, 768)]


def test_a_refresh_before_anything_was_shown_draws_nothing(tmp_path):
    bench = Bench(tmp_path)

    bench.output.refresh()

    assert bench.device.presented == []


def test_a_screen_gone_between_reading_its_size_and_drawing_is_absent_not_an_error(tmp_path, caplog):
    bench = Bench(tmp_path)
    bench.device.modes["hdmi-a-1"] = None  # the kernel has noticed; sysfs has not yet

    with caplog.at_level(logging.WARNING):
        bench.output.show(bench.render)

    assert bench.device.presented == []
    assert [record.__dict__.get("event") for record in caplog.records] == ["screen.absent"]


def test_a_device_that_refuses_raises_from_show_and_is_tried_again_by_refresh(tmp_path):
    bench = Bench(tmp_path)
    bench.device.fails = PermissionError(13, "Permission denied")

    with pytest.raises(PermissionError):
        bench.output.show(bench.render)
    with pytest.raises(PermissionError):
        bench.output.refresh()
    bench.device.fails = None
    bench.output.refresh()

    assert bench.sizes == [(1280, 720)]


def test_a_connector_the_kernel_does_not_list_is_never_connected(tmp_path):
    bench = Bench(tmp_path)
    output = KmsOutput("hdmi-a-3", drm_root=bench.root, device_for=bench._open)

    output.show(bench.render)

    assert bench.opened == []
    assert (output.connected, output.screen) == (False, None)


def test_listed_tells_a_connector_with_no_screen_from_one_the_kernel_does_not_list(tmp_path):
    """`dark` and `no_screen` are different states, and `connected` alone says false for both."""
    bench = Bench(tmp_path, status="disconnected", size=None)
    absent = KmsOutput("hdmi-a-3", drm_root=bench.root, device_for=bench._open)

    assert (bench.output.listed, bench.output.connected) == (True, False)
    assert (absent.listed, absent.connected) == (False, False)


def test_a_wall_on_an_hdmi_connector_draws_through_kernel_mode_setting(client_settings):
    output = entry.screen_output(client_settings.wall("living-room"), "hdmi-a-2")

    assert isinstance(output, KmsOutput)
    assert output._name == "hdmi-a-2"


def _near(pixel: tuple[int, ...], colour: tuple[int, int, int], tolerance: int = 12) -> bool:
    """JPEG moves a flat colour by a few levels."""
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour, strict=True))
