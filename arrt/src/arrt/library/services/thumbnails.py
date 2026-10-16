"""Small images of held works, for a browser that shows forty of them at once.

A grid of the real files is not a page: the masters in this corpus run to 47
megapixels and 40 MB each, and the television renditions are 4K. So the browser
surface is served downscaled copies, cached on disk and **recorded in the
catalogue as renditions**, which is what keeps them from becoming an
untracked pile of files nothing owns.

**Two products, told apart by their parent, which their kind records.**

* A **thumbnail** (`RenditionKind.THUMBNAIL`) is the work itself, drawn from the
  master, for a library tile: the owner's ruling on tiles is that they show the
  work at its own aspect, with no mat. Its parent is the original, so the catalogue's own
  staleness rule is the whole answer to whether it is current.
* A **wall preview** (`RenditionKind.WALL_PREVIEW`) is the same work at the
  size the Work page's column draws sharply. It is drawn from the master too:
  the mat is drawn by the Player that owns the screen, so there is no composed
  picture on this side to show. Its parent is the original, so the catalogue's
  staleness rule is the whole answer for it as well.
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image

from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.imaging import UNDECODABLE, encode_downscaled
from arrt.persistence.records import RenditionKind
from arrt.services.errors import ServiceError

log = logging.getLogger(__name__)

#: The box a thumbnail is fitted into, in pixels. One size rather than a
#: per-request parameter: a caller-chosen size makes the cache unbounded and the
#: rendition rows meaningless, and every tile in the library draws this one.
THUMBNAIL_MAX_EDGE_PX: Final[int] = 480

#: The box a *large* thumbnail is fitted into: the work itself, bare, for a
#: surface that draws it far larger than a tile. Walls leads each card with the
#: work on the wall in a box up to 48rem wide and 32rem tall, which on a 2x
#: screen is 1536 by 1024 device pixels; a 480 px tile is a third of that and
#: visibly soft. 1536 is sharp at either bound for any aspect. One more fixed
#: size, for the reason the tile has one.
LARGE_THUMBNAIL_MAX_EDGE_PX: Final[int] = 1536

#: Quality for the re-encode. High enough that the grid is not visibly artefacted
#: on a retina display, low enough that forty of them are a page.
THUMBNAIL_JPEG_QUALITY: Final[int] = 82

#: The box a wall preview is fitted into. The Work page draws the picture across
#: its column, up to most of the screen's height, and a 480 px copy is visibly
#: soft there on any display; 1920 is sharp across a laptop column at twice its
#: CSS pixels. One size, for the reason the thumbnail has one.
WALL_PREVIEW_MAX_EDGE_PX: Final[int] = 1920

#: A shade higher than the thumbnail's: one picture on a page, looked at closely.
WALL_PREVIEW_JPEG_QUALITY: Final[int] = 85

#: Each product's own subdirectory of the cache. Separate names because a file
#: at one product's path drawn for another would otherwise be served as current
#: forever: nothing on its row records what it was drawn from, and the master's
#: hash still matches.
_THUMBNAIL_DIRNAME: Final[str] = "tiles"
_LARGE_THUMBNAIL_DIRNAME: Final[str] = "tiles-large"
_WALL_PREVIEW_DIRNAME: Final[str] = "wall-previews"


class ThumbnailUnavailable(ServiceError):
    """No thumbnail can be produced, and the message says what is missing.

    A distinct type because "this work has no image yet" is a normal state on a
    catalogue mid-acquisition, not a refused operation: a surface reports it
    beside the work rather than as an error the curator did something to cause.
    """


@dataclass(frozen=True, slots=True)
class ThumbnailSource:
    """The held image a thumbnail or wall preview is made from: the master."""

    path: Path


@dataclass(frozen=True, slots=True)
class ThumbnailSettings:
    """Where the images are and where their downscaled copies go.

    Passed in rather than resolved here for the reason `DisplaySettings` gives: a
    service that read its own configuration could not be tested against two
    deployments and would make every caller share one.
    """

    art_root: Path
    directory: Path

    def __post_init__(self) -> None:
        """Refuse a cache outside the tree, at wiring time rather than mid-request.

        Every catalogue path is relative to `ART_ROOT`, so a thumbnail written
        anywhere else has no representable path. Caught here, that is a startup
        failure naming both directories; caught where the row is written, it is a
        `ValueError` from `relative_to` on the fortieth image of a page load.
        """
        if not self.directory.is_relative_to(self.art_root):
            raise ServiceError(f"The thumbnail cache at {self.directory} must sit inside ART_ROOT at {self.art_root}.")


class ThumbnailService:
    """Produce and cache small copies of held works: thumbnails and wall previews."""

    def __init__(self, catalogue: CatalogueService, settings: ThumbnailSettings) -> None:
        self._catalogue = catalogue
        self._settings = settings

    def source_for(self, artwork_id: str) -> ThumbnailSource:
        """The held image this work's wall preview would be made from, or `ThumbnailUnavailable` saying why there is none.

        Separate from `wall_preview` so a listing can say whether the Work page
        will show a picture, and why not, without decoding an image to find out.
        """
        return self.tile_source(artwork_id)

    def tile_source(self, artwork_id: str) -> ThumbnailSource:
        """The master a tile is drawn from, or `ThumbnailUnavailable` saying why there is none."""
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ThumbnailUnavailable("No master image has been acquired for this work yet.")
        return self._master(original.relative_path)

    def _master(self, relative: str) -> ThumbnailSource:
        master = self._settings.art_root / relative
        if not master.is_file():
            raise ThumbnailUnavailable(f"The master image is recorded at {relative} but no file is there.")
        return ThumbnailSource(path=master)

    def thumbnail(self, artwork_id: str, *, large: bool = False) -> Path:
        """An absolute path to a current thumbnail — the work itself — generating one if needed.

        Drawn from the master, so a tile shows the work at its own aspect. Its
        parent is the original, so the catalogue's staleness rule is the whole
        currency test.

        `large` is the same product in a bigger box (`LARGE_THUMBNAIL_MAX_EDGE_PX`),
        cached in its own directory and recorded as its own row: the catalogue
        keys a rendition on its kind *and* its box, so the two sizes are two
        rows and neither overwrites the other.
        """
        source = self.tile_source(artwork_id)
        return self._cached(
            artwork_id,
            source,
            kind=RenditionKind.THUMBNAIL,
            dirname=_LARGE_THUMBNAIL_DIRNAME if large else _THUMBNAIL_DIRNAME,
            max_edge=LARGE_THUMBNAIL_MAX_EDGE_PX if large else THUMBNAIL_MAX_EDGE_PX,
            quality=THUMBNAIL_JPEG_QUALITY,
        )

    def wall_preview(self, artwork_id: str) -> Path:
        """An absolute path to a current wall preview, generating one if needed."""
        return self._cached(
            artwork_id,
            self.source_for(artwork_id),
            kind=RenditionKind.WALL_PREVIEW,
            dirname=_WALL_PREVIEW_DIRNAME,
            max_edge=WALL_PREVIEW_MAX_EDGE_PX,
            quality=WALL_PREVIEW_JPEG_QUALITY,
        )

    def _cached(
        self,
        artwork_id: str,
        source: ThumbnailSource,
        *,
        kind: RenditionKind,
        dirname: str,
        max_edge: int,
        quality: int,
    ) -> Path:
        """A current downscaled copy of `source`, from the cache or freshly encoded."""
        directory = self._settings.directory / dirname
        cached = directory / f"{artwork_id}.jpg"
        # The id reaches this filename from a URL path segment. Nothing that is
        # not a catalogue id gets this far — the original is looked up first and
        # an unknown work has none — but the guard is here rather than resting on
        # that, because a traversal is only ever one refactor away from being
        # written to disk and this check costs nothing.
        if not cached.resolve().is_relative_to(directory.resolve()):
            raise ServiceError(f"Artwork id {artwork_id!r} does not name a file inside the thumbnail cache.")

        held = next(
            (
                view
                for view in self._catalogue.list_renditions(artwork_id)
                if view.rendition.kind is kind
                and view.rendition.target_width == max_edge
                and view.rendition.target_height == max_edge
            ),
            None,
        )
        recorded_here = held is not None and self._settings.art_root / held.rendition.relative_path == cached
        # All four conditions, because each one alone is satisfiable while the
        # cached file is wrong: a fresh row can point at a file someone deleted,
        # or at another path than this product's (a row written before the
        # products had their own directories), and a present file can predate
        # the master it claims to depict.
        if held is not None and not held.stale and recorded_here and cached.is_file():
            return cached

        self._write(source.path, cached, max_edge=max_edge, quality=quality)
        # Recorded after the file exists, so a row can never promise an image
        # that is not there. The reverse — a file with no row — costs one
        # regeneration and nothing else.
        self._catalogue.record_rendition(
            artwork_id=artwork_id,
            kind=kind,
            # The box requested, not the size produced: fitting preserves aspect
            # so one edge comes out shorter, and recording that would give every
            # work its own geometry and defeat the upsert this depends on.
            target_width=max_edge,
            target_height=max_edge,
            path=str(cached.relative_to(self._settings.art_root)),
        )
        if held is not None and not recorded_here:
            # The file the row used to name is now named by nothing, so it goes
            # with the row's move rather than staying as a pile nothing owns.
            # Only a file inside the cache: the row is the catalogue's, but this
            # service deletes only what it wrote.
            superseded = self._settings.art_root / held.rendition.relative_path
            if superseded.resolve().is_relative_to(self._settings.directory.resolve()):
                superseded.unlink(missing_ok=True)
        return cached

    def _write(self, source: Path, destination: Path, *, max_edge: int, quality: int) -> None:
        """Downscale `source` into `destination`, atomically."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        # A distinct name per attempt, so two requests for the same work racing
        # each other cannot write the same temp file: rename is atomic, but two
        # writers sharing one path are interleaving their bytes before it.
        staging = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.tmp")
        # **Cleanup in `finally`, not per handler.** The staging name is unique
        # per attempt, so anything this method fails to unlink is stranded for
        # good and every retry strands another — and cleaning up only inside the
        # handlers meant an exception neither of them named leaked a file as well
        # as a 500. After a successful `replace` the name is already gone, so
        # the unlink is a no-op on the happy path.
        try:
            frame = encode_downscaled(source, max_edge=max_edge, quality=quality)
            staging.write_bytes(frame.data)
            staging.replace(destination)
        except Image.DecompressionBombError as exc:
            raise ThumbnailUnavailable(f"The image at {source.name} is too large to open safely: {exc}") from exc
        except UNDECODABLE as exc:
            raise ThumbnailUnavailable(f"The image at {source.name} could not be read: {exc}") from exc
        finally:
            staging.unlink(missing_ok=True)
