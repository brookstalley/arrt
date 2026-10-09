"""Drawing a render on an HDMI connector: kernel mode setting, with no desktop.

The host has no display server (it boots to `multi-user.target`), so the Player
takes the connector itself. `libdrm` is the kernel's own userspace library and is
present wherever the `vc4` driver is, and the five calls this needs are reached
through `ctypes` rather than a binding package: the Pi's packaged binding
(`python3-kms++`) is built for the system's Python and not the Player's, and the
calls are few and have not changed shape in a decade. The measurements this is
built on, on the Pi and a 4K LG, are `hdmi-output-findings.md`.

Three things the measurements decided:

* **The picture is a dumb buffer handed to the connector's CRTC with a legacy
  `SetCrtc`.** No crossfade is asked for, so there is no plane composition and no
  atomic commit: two buffers per connector, the next picture written into the one
  not on screen and then made current, so a half-copied picture is never shown.
* **The mode is the first the kernel lists**, which is the one the client
  heartbeat reports as the screen's size. The monitor's own preferred mode is not
  always offered: a 4K monitor's 60 Hz mode is dropped unless the firmware enables
  it, and with it the flag that marks a mode preferred.
* **The device stays open for the life of the process.** The program holding
  the connector is its DRM master, and when it closes the device the kernel gives
  the screen back to the text console. One process may drive both connectors of a
  card, and only one opener can be master, so the device is shared between them.

The kernel keeps scanning out through a cable being pulled and pushed back, and
the picture came back by itself when it was; the output still draws again
whenever a screen returns, because a different screen may be what came back.
"""

import ctypes
import ctypes.util
import fcntl
import logging
import mmap
import os
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from PIL import Image, ImageOps

from arrt_player.client import DRM_ROOT, FRAMEBUFFER_KIND, OutputReport, hdmi_outputs
from arrt_player.episodes import ReportOnce

log = logging.getLogger(__name__)

#: Where the kernel puts the device nodes for the cards `DRM_ROOT` lists.
DEV_ROOT: Final[Path] = Path("/dev/dri")


class ScreenAbsent(Exception):
    """Nothing is on the connector, or what is there offers no mode."""


# -- fitting -------------------------------------------------------------------------


def fitted(render: Path, screen: tuple[int, int]) -> Image.Image:
    """The render scaled to fit the screen whole, centred on black.

    The render arrives matted for the Frame; fitting keeps all of it, mat and
    all, so a screen of another shape shows bars rather than losing an edge of
    the picture. The render is already black outside the mat, so the bars are
    more of the same black rather than a second boundary.
    """
    with Image.open(render) as opened:
        picture = ImageOps.exif_transpose(opened).convert("RGB")
    if picture.size != screen:
        picture = ImageOps.contain(picture, screen, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", screen)
    canvas.paste(picture, ((screen[0] - picture.width) // 2, (screen[1] - picture.height) // 2))
    return canvas


def scanout_bytes(picture: Image.Image) -> bytes:
    """The picture as the connector scans it out: `XRGB8888`, which in memory is B, G, R, unused."""
    return picture.tobytes("raw", "BGRX")


# -- the device ------------------------------------------------------------------------


class Device(Protocol):
    """One display card, shared by every output on it."""

    def mode(self, connector: str) -> tuple[int, int]:
        """The size the connector will be driven at. Raises `ScreenAbsent`."""

    def present(self, connector: str, size: tuple[int, int], pixels: bytes) -> None:
        """Put `XRGB8888` pixels of this size on the connector. Raises `ScreenAbsent`."""


u32, u16, i32, u64 = ctypes.c_uint32, ctypes.c_uint16, ctypes.c_int, ctypes.c_uint64


class _ModeRes(ctypes.Structure):
    _fields_ = [
        ("count_fbs", i32),
        ("fbs", ctypes.POINTER(u32)),
        ("count_crtcs", i32),
        ("crtcs", ctypes.POINTER(u32)),
        ("count_connectors", i32),
        ("connectors", ctypes.POINTER(u32)),
        ("count_encoders", i32),
        ("encoders", ctypes.POINTER(u32)),
        ("min_width", u32),
        ("max_width", u32),
        ("min_height", u32),
        ("max_height", u32),
    ]


class _ModeInfo(ctypes.Structure):
    _fields_ = [
        ("clock", u32),
        ("hdisplay", u16),
        ("hsync_start", u16),
        ("hsync_end", u16),
        ("htotal", u16),
        ("hskew", u16),
        ("vdisplay", u16),
        ("vsync_start", u16),
        ("vsync_end", u16),
        ("vtotal", u16),
        ("vscan", u16),
        ("vrefresh", u32),
        ("flags", u32),
        ("type", u32),
        ("name", ctypes.c_char * 32),
    ]


class _Connector(ctypes.Structure):
    _fields_ = [
        ("connector_id", u32),
        ("encoder_id", u32),
        ("connector_type", u32),
        ("connector_type_id", u32),
        ("connection", i32),
        ("mmWidth", u32),
        ("mmHeight", u32),
        ("subpixel", i32),
        ("count_modes", i32),
        ("modes", ctypes.POINTER(_ModeInfo)),
        ("count_props", i32),
        ("props", ctypes.POINTER(u32)),
        ("prop_values", ctypes.POINTER(u64)),
        ("count_encoders", i32),
        ("encoders", ctypes.POINTER(u32)),
    ]


class _Encoder(ctypes.Structure):
    _fields_ = [
        ("encoder_id", u32),
        ("encoder_type", u32),
        ("crtc_id", u32),
        ("possible_crtcs", u32),
        ("possible_clones", u32),
    ]


#: `DRM_MODE_CONNECTOR_HDMIA` and `DRM_MODE_CONNECTED`, from `drm_mode.h`.
_HDMIA: Final = 11
_CONNECTED: Final = 1


def _iowr(number: int, size: int) -> int:
    return (3 << 30) | (size << 16) | (ord("d") << 8) | number


#: The dumb-buffer ioctls, `drm.h`: create (`drm_mode_create_dumb`, 32 bytes), map
#: (`drm_mode_map_dumb`, 16), destroy (`drm_mode_destroy_dumb`, 4).
_CREATE_DUMB: Final = _iowr(0xB2, 32)
_MAP_DUMB: Final = _iowr(0xB3, 16)
_DESTROY_DUMB: Final = _iowr(0xB4, 4)


def _load_libdrm() -> ctypes.CDLL:
    lib = ctypes.CDLL(ctypes.util.find_library("drm") or "libdrm.so.2", use_errno=True)
    lib.drmModeGetResources.restype = ctypes.POINTER(_ModeRes)
    lib.drmModeGetResources.argtypes = [i32]
    lib.drmModeFreeResources.argtypes = [ctypes.POINTER(_ModeRes)]
    lib.drmModeGetConnector.restype = ctypes.POINTER(_Connector)
    lib.drmModeGetConnector.argtypes = [i32, u32]
    lib.drmModeFreeConnector.argtypes = [ctypes.POINTER(_Connector)]
    lib.drmModeGetEncoder.restype = ctypes.POINTER(_Encoder)
    lib.drmModeGetEncoder.argtypes = [i32, u32]
    lib.drmModeFreeEncoder.argtypes = [ctypes.POINTER(_Encoder)]
    lib.drmModeAddFB.argtypes = [i32, u32, u32, ctypes.c_uint8, ctypes.c_uint8, u32, u32, ctypes.POINTER(u32)]
    lib.drmModeRmFB.argtypes = [i32, u32]
    lib.drmModeSetCrtc.argtypes = [i32, u32, u32, u32, u32, ctypes.POINTER(u32), i32, ctypes.POINTER(_ModeInfo)]
    return lib


def _failed(call: str) -> OSError:
    number = ctypes.get_errno()
    return OSError(number, f"{call}: {os.strerror(number)}")


@dataclass
class _Buffer:
    framebuffer: int
    handle: int
    pitch: int
    memory: mmap.mmap


@dataclass
class _Scanout:
    """A connector this process drives: its CRTC, its mode, and its two buffers."""

    crtc: int
    size: tuple[int, int]
    mode: _ModeInfo
    buffers: tuple[_Buffer, _Buffer]
    #: Which of the two buffers is on screen.
    front: int = 0


class LibdrmDevice:
    """A display card driven through `libdrm`, opened on first use and held open."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._fd: int | None = None
        self._lib: ctypes.CDLL | None = None
        self._connector_ids: dict[str, int] = {}
        self._scanouts: dict[str, _Scanout] = {}

    def mode(self, connector: str) -> tuple[int, int]:
        with self._lock:
            mode, _ = self._probe(connector)
            return (mode.hdisplay, mode.vdisplay)

    def present(self, connector: str, size: tuple[int, int], pixels: bytes) -> None:
        with self._lock:
            mode, crtc = self._probe(connector)
            if (mode.hdisplay, mode.vdisplay) != size:
                raise ScreenAbsent(f"{connector} now offers {mode.hdisplay}x{mode.vdisplay}, not {size[0]}x{size[1]}")
            held = self._scanouts.get(connector)
            scanout = held
            if held is None or held.size != size or held.crtc != crtc:
                # A new screen, or a new size: a new pair, and the old pair freed
                # only once the screen shows the new one.
                scanout = _Scanout(crtc=crtc, size=size, mode=mode, buffers=self._pair(size), front=1)
            scanout.mode = mode
            back = 1 - scanout.front
            try:
                self._fill(scanout.buffers[back], size, pixels)
                self._set_crtc(scanout, back, self._connector_ids[connector])
            except BaseException:
                if scanout is not held:
                    for buffer in scanout.buffers:
                        self._destroy(buffer)
                raise
            scanout.front = back
            if scanout is not held:
                self._scanouts[connector] = scanout
                if held is not None:
                    for buffer in held.buffers:
                        self._destroy(buffer)

    # -- below the lock --------------------------------------------------------------

    def _libdrm(self) -> ctypes.CDLL:
        if self._lib is None:
            self._lib = _load_libdrm()
        return self._lib

    def _open(self) -> int:
        if self._fd is None:
            self._fd = os.open(self._path, os.O_RDWR | os.O_CLOEXEC)
        return self._fd

    def _probe(self, connector: str) -> tuple[_ModeInfo, int]:
        """The connector's first mode and the CRTC to drive it with. Probing reads the screen's EDID afresh."""
        lib, fd = self._libdrm(), self._open()
        connector_id = self._connector_id(connector)
        found = lib.drmModeGetConnector(fd, connector_id)
        if not found:
            raise _failed("drmModeGetConnector")
        try:
            details = found.contents
            if details.connection != _CONNECTED or details.count_modes < 1:
                raise ScreenAbsent(f"nothing is connected to {connector}")
            mode = _ModeInfo.from_buffer_copy(details.modes[0])
            return mode, self._crtc_for(connector, details)
        finally:
            lib.drmModeFreeConnector(found)

    def _connector_id(self, connector: str) -> int:
        if not self._connector_ids:
            lib, fd = self._libdrm(), self._open()
            resources = lib.drmModeGetResources(fd)
            if not resources:
                raise _failed("drmModeGetResources")
            try:
                for index in range(resources.contents.count_connectors):
                    found = lib.drmModeGetConnector(fd, resources.contents.connectors[index])
                    if not found:
                        continue
                    if found.contents.connector_type == _HDMIA:
                        self._connector_ids[f"hdmi-a-{found.contents.connector_type_id}"] = found.contents.connector_id
                    lib.drmModeFreeConnector(found)
            finally:
                lib.drmModeFreeResources(resources)
        try:
            return self._connector_ids[connector]
        except KeyError:
            raise ScreenAbsent(f"{self._path} has no connector {connector}") from None

    def _crtc_for(self, connector: str, details: _Connector) -> int:
        """The CRTC already driving this connector, else the first free one its encoders can use."""
        held = self._scanouts.get(connector)
        if held is not None:
            return held.crtc
        lib, fd = self._libdrm(), self._open()
        taken = {scanout.crtc for scanout in self._scanouts.values()}
        resources = lib.drmModeGetResources(fd)
        if not resources:
            raise _failed("drmModeGetResources")
        try:
            crtcs = [resources.contents.crtcs[index] for index in range(resources.contents.count_crtcs)]
        finally:
            lib.drmModeFreeResources(resources)
        candidates = [details.encoder_id] + [details.encoders[index] for index in range(details.count_encoders)]
        for encoder_id in candidates:
            if not encoder_id:
                continue
            encoder = lib.drmModeGetEncoder(fd, encoder_id)
            if not encoder:
                continue
            try:
                if encoder.contents.crtc_id and encoder.contents.crtc_id not in taken:
                    return encoder.contents.crtc_id
                for index, crtc in enumerate(crtcs):
                    if encoder.contents.possible_crtcs & (1 << index) and crtc not in taken:
                        return crtc
            finally:
                lib.drmModeFreeEncoder(encoder)
        raise OSError(f"no free CRTC can drive {connector}")

    def _pair(self, size: tuple[int, int]) -> tuple[_Buffer, _Buffer]:
        first = self._buffer(size)
        try:
            return (first, self._buffer(size))
        except BaseException:
            self._destroy(first)
            raise

    def _buffer(self, size: tuple[int, int]) -> _Buffer:
        fd, (width, height) = self._open(), size
        request = bytearray(struct.pack("<IIIIIIQ", height, width, 32, 0, 0, 0, 0))
        fcntl.ioctl(fd, _CREATE_DUMB, request)
        handle, pitch, length = struct.unpack("<IIQ", request[16:32])
        try:
            framebuffer = self._add_framebuffer(size, pitch, handle)
            try:
                mapping = bytearray(struct.pack("<IIQ", handle, 0, 0))
                fcntl.ioctl(fd, _MAP_DUMB, mapping)
                offset = struct.unpack("<IIQ", mapping)[2]
                memory = mmap.mmap(fd, length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=offset)
            except BaseException:
                self._libdrm().drmModeRmFB(fd, framebuffer)
                raise
        except BaseException:
            fcntl.ioctl(fd, _DESTROY_DUMB, bytearray(struct.pack("<I", handle)))
            raise
        return _Buffer(framebuffer=framebuffer, handle=handle, pitch=pitch, memory=memory)

    def _add_framebuffer(self, size: tuple[int, int], pitch: int, handle: int) -> int:
        framebuffer = u32()
        if self._libdrm().drmModeAddFB(self._open(), size[0], size[1], 24, 32, pitch, handle, ctypes.byref(framebuffer)):
            raise _failed("drmModeAddFB")
        return framebuffer.value

    def _set_crtc(self, scanout: _Scanout, buffer: int, connector_id: int) -> None:
        ids = (u32 * 1)(connector_id)
        framebuffer = scanout.buffers[buffer].framebuffer
        if self._libdrm().drmModeSetCrtc(self._open(), scanout.crtc, framebuffer, 0, 0, ids, 1, ctypes.byref(scanout.mode)):
            raise _failed("drmModeSetCrtc")

    @staticmethod
    def _fill(buffer: _Buffer, size: tuple[int, int], pixels: bytes) -> None:
        row = size[0] * 4
        if len(pixels) != row * size[1]:
            raise ValueError(f"{len(pixels)} bytes is not a {size[0]}x{size[1]} XRGB8888 picture")
        if buffer.pitch == row:
            buffer.memory[: len(pixels)] = pixels
            return
        for y in range(size[1]):
            buffer.memory[y * buffer.pitch : y * buffer.pitch + row] = pixels[y * row : (y + 1) * row]

    def _destroy(self, buffer: _Buffer) -> None:
        fd = self._open()
        self._libdrm().drmModeRmFB(fd, buffer.framebuffer)
        buffer.memory.close()
        fcntl.ioctl(fd, _DESTROY_DUMB, bytearray(struct.pack("<I", buffer.handle)))


_devices: dict[Path, LibdrmDevice] = {}
_devices_lock = threading.Lock()


def shared_device(path: Path) -> Device:
    """The one `LibdrmDevice` for this card in this process."""
    with _devices_lock:
        return _devices.setdefault(path, LibdrmDevice(path))


# -- the output ------------------------------------------------------------------------


class KmsOutput:
    """A wall's screen on one HDMI connector (`hdmi-a-1`), behind `ScreenOutput`.

    Whether a screen is there, and its size, are read from `DRM_ROOT` exactly as
    the client heartbeat reads them, so the output never draws at a size other
    than the one the curator was told. A screen that is absent costs nothing but
    a line: the render is remembered and drawn when `refresh` sees one arrive.
    """

    def __init__(
        self,
        name: str,
        *,
        drm_root: Path = DRM_ROOT,
        dev_root: Path = DEV_ROOT,
        device_for: Callable[[Path], Device] = shared_device,
    ) -> None:
        self._name = name
        self._drm_root = drm_root
        self._dev_root = dev_root
        self._device_for = device_for
        #: The render this output should be showing.
        self._render: Path | None = None
        #: What is on the screen, as `(render, size)`, or None when nothing this
        #: output drew is known to be there.
        self._drawn: tuple[Path, tuple[int, int]] | None = None
        self._absent = ReportOnce()

    @property
    def listed(self) -> bool:
        """Whether the kernel lists this connector at all — the same listing `connected` is read from."""
        return any(report.name == self._name for report in hdmi_outputs(self._drm_root))

    @property
    def connected(self) -> bool:
        return self._report().connected

    @property
    def screen(self) -> tuple[int, int] | None:
        return self._report().screen

    def show(self, render: Path) -> None:
        self._render = render
        self._draw(render)

    def refresh(self) -> None:
        """Draw the current render again if the screen went away and came back, or changed size."""
        if self._render is None:
            return
        report = self._report()
        if not report.connected or report.screen is None:
            self._gone()
            return
        if self._drawn != (self._render, report.screen):
            self._draw(self._render)

    def _draw(self, render: Path) -> None:
        report = self._report()
        if not report.connected or report.screen is None:
            self._gone()
            return
        try:
            device = self._device_for(self._card())
            size = device.mode(self._name)
            device.present(self._name, size, scanout_bytes(fitted(render, size)))
        except ScreenAbsent:
            self._gone()
            return
        self._drawn = (render, report.screen)
        if self._absent.end():
            log.info(
                "a screen is on %s again (%dx%d); drawing the wall's picture",
                self._name,
                size[0],
                size[1],
                extra={"event": "screen.returned", "output": self._name, "screen": f"{size[0]}x{size[1]}"},
            )

    def _gone(self) -> None:
        self._drawn = None
        if self._absent.begin():
            log.warning(
                "no screen is connected to %s; the wall keeps rotating and draws when one is",
                self._name,
                extra={"event": "screen.absent", "output": self._name},
            )

    def _report(self) -> OutputReport:
        for report in hdmi_outputs(self._drm_root):
            if report.name == self._name:
                return report
        return OutputReport(name=self._name, kind=FRAMEBUFFER_KIND, connected=False, screen=None)

    def _card(self) -> Path:
        """The device node of the card listing this connector: the first, as `hdmi_outputs` takes the first."""
        number = self._name.removeprefix("hdmi-a-")
        cards = sorted(path.name.split("-", 1)[0] for path in self._drm_root.glob(f"card*-HDMI-A-{number}"))
        if not cards:
            raise ScreenAbsent(f"the kernel lists no connector {self._name}")
        return self._dev_root / cards[0]
