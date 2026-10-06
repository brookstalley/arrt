"""Candidate previews: kept in the picture store, and re-encoded for whoever reads them.

The review grid — in the browser and over MCP alike — has to show the picture. A
source-side URL alone means a curator reviewing an hour later sees broken images
when a museum is down or rate-limiting, and it means the MCP surface has nothing
local to inline. So the picture is fetched once, when the instance is found, and
kept for good in the picture store (`pictures.py`), which is the only thing that
asks a source for one. The catalogue records where it landed.

**A preview that will not download is not a failure.** The instance is still
real, still selectable, and still carries a source-side URL to fall back on.
Losing a work over a missing thumbnail would be the tail wagging the dog, so
every failure path here reports absence rather than raising. The re-encoder
below holds the same posture for the same reason, one step further along: a file
that will not decode costs its instance a picture, never its place in the
listing.

**Two readers with unrelated budgets.** A model pays for a picture in context
tokens and a curator pays for it in pixels on a screen. The browser is answered
with a kept tier's bytes as they are; the model's copy is re-encoded smaller from
the smallest tier — see the box constants, which say why sharing one would be a
slow leak from the visual side into the model's context.
"""

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, UnidentifiedImageError

from arrt.library.services.imaging import EncodedFrame, encode_downscaled
from arrt.library.services.pictures import PictureStore

log = logging.getLogger(__name__)

#: The box an inlined preview is fitted into, in pixels on its long edge.
#:
#: **This is a token budget, not a visual one.** An image costs a client roughly
#: `width * height / 750` tokens, so 400 px on the long edge is about 160 tokens
#: for a landscape scan and a forty-work batch is about 6,400 — under the 10,000
#: at which Claude Code warns, and well under its 25,000 ceiling, with room left
#: for the text beside it. Raising a client's own limit does not buy headroom
#: here: `_meta["anthropic/maxResultSizeChars"]` governs text and images do not
#: benefit from it.
#:
#: Deliberately smaller than the catalogue thumbnail's 480 px and deliberately
#: not shared with it. That one is fitted to a browser grid on a retina display
#: and is bounded by what looks right; this one is fitted to a model's context
#: and is bounded by arithmetic. One constant serving both would be moved by
#: whichever pressure spoke last, and the visual pressure only ever pushes up.
#:
#: It is sufficient for the judgement the review gate exists to make — is this
#: the right painting, and is it appropriate for a living room. It is *not*
#: sufficient for judging mat colour, which happens after acceptance on a real
#: screen.
INLINE_MAX_EDGE_PX: Final[int] = 400

#: Quality for the re-encode. Lower than the browser thumbnail's, because every
#: byte here is spent inside a model's context rather than on a screen, and the
#: artefacts a curator would notice at 480 px on a retina panel are invisible in
#: the judgement this image is for.
INLINE_JPEG_QUALITY: Final[int] = 75

#: The long edge a review card asks the picture store for, in pixels.
#:
#: **Its own constant, not `INLINE_MAX_EDGE_PX` reused, and that separation is the
#: point rather than an accident.** That one is bounded by arithmetic — an image
#: costs a model roughly `width * height / 750` tokens — and this one is bounded
#: by a review card on a screen. One constant serving both would be moved by
#: whichever pressure spoke last, and the visual pressure only ever pushes up,
#: which would silently spend a curator's model context on pixels it cannot use.
#:
#: The value matches the catalogue thumbnail's for the reason both were sized:
#: cards of about this width on a retina display, and it is the store's smaller
#: tier, so a card is answered with that file as it is.
#:
#: Sufficient for the judgement the review gate exists to make: is this the right
#: painting, and is it appropriate for a living room. It is emphatically *not*
#: how a curator judges resolution — a 900 px scan and a 6000 px scan look
#: identical at any card size, which is why every instance travels with the size
#: it would render at on the wall, in inches, beside the picture.
BROWSER_MAX_EDGE_PX: Final[int] = 480

#: The long edge the *enlarged* picture asks for: what a review card opens in
#: place when it is clicked, the largest picture the server keeps.
#:
#: **A bound, not a size.** What the store keeps is the provider's preview —
#: ARTIC's is 843 px wide (`artic._PREVIEW_WIDTH`) and Commons' 960
#: (`commons.PREVIEW_WIDTH`) — at its own size when smaller than the store's
#: larger tier, so the enlarged picture is that file and nothing is scaled up.
#: Not the master: a work under review has none yet.
ENLARGED_MAX_EDGE_PX: Final[int] = 2048

#: What a preview is declared as on the wire, whichever reader asked. Everything
#: the store keeps is JPEG it encoded itself — museums serve JPEG, PNG and the
#: occasional TIFF — and one media type for both readers is not merely tidy. For
#: a model, a content block whose type varied per instance would make the cost
#: per image depend on the museum's choice of format rather than on the picture.
#: For a browser, a TIFF served under a type it cannot paint is a blank card with
#: nothing saying why.
PREVIEW_MEDIA_TYPE: Final[str] = "image/jpeg"

#: How every JPEG begins (the start-of-image marker). A kept file is checked for
#: it before it is served as `image/jpeg`, so a file that is not one is reported
#: unreadable rather than painted as a blank box.
_JPEG_START: Final[bytes] = b"\xff\xd8\xff"


class PreviewCache:
    """Keep each found instance's preview in the picture store, and hand back the path its row records.

    A client of the store, not a cache of its own: the store looks first, fetches
    on a miss, and writes, so a second record of the same image asks no source.
    What this adds is the phase-2 seam the runner holds — the store is the
    runner's only way to a picture.
    """

    def __init__(self, pictures: PictureStore) -> None:
        self._pictures = pictures

    def store(self, provider: str, url: str, preview_url: str) -> str | None:
        """The kept picture of the instance at `url`, as a path relative to `ART_ROOT`.

        `url` is the instance's own address, which the picture is kept under;
        `preview_url` is where its source serves the preview. `None` means no
        picture is kept — the fetch failed, or what came back is not a picture —
        and the caller records the instance regardless, with its source-side URL
        and no `preview_path`. Never raises (`PictureStore.keep`).
        """
        return self._pictures.keep(provider, url, preview_url)


@dataclass(frozen=True, slots=True)
class InlinePreview:
    """One kept picture, small enough to travel inside a tool result.

    The bytes are base64 already, because that is the only form the wire takes
    them in and handing a caller raw bytes it must encode is an invitation for
    two call sites to encode them differently.

    The dimensions are the *encoded* ones rather than the box that was asked
    for: fitting preserves aspect ratio, so one edge comes out shorter, and a
    caller reporting the box would state a size the picture does not have.
    """

    data: str
    media_type: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RenderedPreview:
    """One kept picture, as bytes a browser paints directly.

    Raw bytes rather than base64: these travel as an HTTP response body, and
    encoding them for a transport that does not need it would cost a third more
    bytes on every card of a thirty-work grid.

    No dimensions. The MCP twin reports them because a model cannot see the
    picture and prices it by area; a browser lays the image out from the bytes
    themselves, so a size in the payload would be a number nothing reads.
    """

    data: bytes
    media_type: str


def inline_preview(path: Path) -> InlinePreview | None:
    """Downscale a kept picture into something a tool result can carry.

    `None` means this instance travels without a picture, and it is never an
    error: a picture on a card is a convenience beside the work, and the same reasoning that
    makes a failed *download* report absence makes a failed *decode* report it
    too. The instance is still real, still listed, and still carries its
    source-side URL. Raising instead would lose a curator the other thirty-nine
    works over one museum's malformed JPEG.
    """
    frame = _rendered(path, max_edge=INLINE_MAX_EDGE_PX, quality=INLINE_JPEG_QUALITY)
    if frame is None:
        return None
    return InlinePreview(
        data=base64.b64encode(frame.data).decode("ascii"),
        media_type=PREVIEW_MEDIA_TYPE,
        width=frame.width,
        height=frame.height,
    )


def kept_preview(path: Path) -> RenderedPreview | None:
    """A kept picture's bytes as they are, for a browser to paint.

    Not re-encoded: the store wrote this file as JPEG at the size asked for, so
    decoding it again would cost a Pi a re-render per card for nothing. Absence is
    reported the same way and for the same reason as above: a review card whose
    picture will not read still shows the work, its size on the wall, and its
    source URL, and is still selectable.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        return _no_inline(path, f"it could not be read: {exc}")
    if not data.startswith(_JPEG_START):
        return _no_inline(path, "it is not a JPEG, which is all the picture store writes")
    return RenderedPreview(data=data, media_type=PREVIEW_MEDIA_TYPE)


def _rendered(path: Path, *, max_edge: int, quality: int) -> EncodedFrame | None:
    """Re-encode a kept picture, reporting absence rather than raising.

    **Only the model's copy is re-encoded on the way out**, from the store's
    smaller tier, because its box and quality are a token budget the store's
    tiers are not sized for. Nothing is kept of it: the 480 px tier is already
    small, and `draft` decodes it at a reduced scale.
    """
    try:
        return encode_downscaled(path, max_edge=max_edge, quality=quality)
    except Image.DecompressionBombError as exc:
        # Pillow's own guard against a decompression bomb. Caught by name rather
        # than swept up with the rest, because a file engineered to exhaust
        # memory is worth a different log line from one that is merely corrupt.
        return _no_inline(path, f"it is too large to open safely: {exc}")
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        # `OSError` and `UnidentifiedImageError` are the ordinary two — a
        # truncated download, a file that is not an image — and are what the
        # tests exercise.
        #
        # `ValueError` is boundary defence rather than a covered path, and the
        # measurement is worth recording so nobody re-derives it: Pillow raises
        # it from `convert` for at least one mode (`La`, premultiplied greyscale
        # alpha), but no image format round-trips to that mode through
        # `Image.open`, so it was not reachable from a file on disk when this was
        # written. It is caught anyway because the alternative is one museum's
        # unusual file costing a curator the other thirty-nine works in the
        # listing, which is the outcome this whole module exists to prevent.
        return _no_inline(path, f"it could not be read: {exc}")


def _no_inline(path: Path, why: str) -> None:
    """Report that no picture travels with this instance, with the reason.

    One exit for every way a kept picture can fail to be read or re-encoded, so
    the log line cannot drift between them — the same shape the store's
    `_absent` holds for the download it mirrors.
    """
    log.info(
        "a kept picture could not be rendered; the instance is listed without a picture",
        extra={"event": "preview.not_inlined", "path": str(path), "reason": why},
    )
