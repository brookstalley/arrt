"""Small images of held works, for a browser that shows forty of them at once.

A grid of the real files is not a page: the masters in this corpus run to 47
megapixels and 40 MB each, and the television renditions are 4K. So the browser
surface is served downscaled copies, cached on disk and **recorded in the
catalogue as renditions**, which is what keeps them from becoming an
untracked pile of files nothing owns.

**Two products, told apart by their parent, which their kind records.**

* A **thumbnail** (`RenditionKind.THUMBNAIL`) is the work itself, drawn from the
  master, for a library tile: the owner's ruling on tiles is that they show the
  work at its own aspect, and the wall render's mat and black bars are the
  wall's, not the work's. Its parent is the original, so the catalogue's own
  staleness rule is the whole answer to whether it is current.
* A **wall preview** (`RenditionKind.WALL_PREVIEW`) is what the wall shows,
  brought down to a size a browser column draws sharply, for the Work page,
  where the wall render is the subject. It is drawn from the current television
  canvas when there is one and from the master when there is not.

**The wall preview's staleness is the catalogue's rule plus one this kind alone
needs.** A rendition carries the content hash of the master it was made from, so
it goes stale when the work's original changes. A wall preview is the one
rendition drawn from *another rendition*: once a work has a canvas, the preview
is a copy of the canvas, and composing or recomposing one never touches the
original the hash test asks about. `_drawn_from` is that second test, and it is
deliberately not in `records.py` beside `is_current` — the shared rule is shared
because three surfaces must not disagree about it, while this one has a single
consumer and covers a relation only this kind has.

**Which image a wall preview is drawn from is reported, never assumed.** The
television rendition is preferred when it is current: it is what the wall is
actually showing. A stale one is refused outright rather than used — serving it
would put a superseded acquisition in front of the curator, which is precisely
what the staleness rule exists to prevent — and the master is used instead.
Callers are told which, because a curator looking at the Work page deserves to
know whether they are seeing the composed presentation or the raw scan.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from PIL import Image

from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.imaging import UNDECODABLE, encode_downscaled
from arrt.persistence.records import Rendition, RenditionKind, tv_renditions_newest_first
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
#: visibly soft. 1536 is sharp at either bound for any aspect, and is not the
#: wall preview's 1920 because that one is the canvas, mat and bars included,
#: which a Walls lead must not show. One more fixed size, for the reason the
#: tile has one.
LARGE_THUMBNAIL_MAX_EDGE_PX: Final[int] = 1536

#: Quality for the re-encode. High enough that the grid is not visibly artefacted
#: on a retina display, low enough that forty of them are a page.
THUMBNAIL_JPEG_QUALITY: Final[int] = 82

#: The box a wall preview is fitted into. The Work page draws the wall render
#: across its column, up to most of the screen's height, and a 480 px copy is
#: visibly soft there on any display; 1920 is sharp across a laptop column at
#: twice its CSS pixels and still a tenth of the 4K canvas's bytes. One size, for
#: the reason the thumbnail has one.
WALL_PREVIEW_MAX_EDGE_PX: Final[int] = 1920

#: A shade higher than the thumbnail's: one picture on a page, looked at closely,
#: where a mat's flat colour is where JPEG banding shows first.
WALL_PREVIEW_JPEG_QUALITY: Final[int] = 85

#: Each product's own subdirectory of the cache. Separate names because the
#: two are drawn from different parents, and a file at a thumbnail's path that
#: was drawn from a canvas — which the cache held before thumbnails became the
#: bare work — would otherwise be served as current forever: nothing on its row
#: records what it was drawn from, and the master's hash still matches.
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
    """Which held image a thumbnail or wall preview is made from."""

    #: `tv_display` or `original` — what the curator is actually looking at.
    kind: str
    path: Path
    #: When this source image was itself produced, and `None` for the master.
    #:
    #: The asymmetry is the point rather than an omission. A copy of the
    #: master goes stale when the master changes, and the catalogue's own
    #: staleness rule already answers that by hash. A wall preview of a *canvas*
    #: has no such cover: the canvas is a rendition too, and composing or
    #: recomposing one leaves the original untouched, so the hash says "current"
    #: for a preview drawn from an image that no longer exists. Comparing against
    #: this is what closes it, and only the canvas branch needs it.
    #:
    #: **Undefaulted on purpose**, though `None` is one of its two legitimate
    #: values. `kind` already says which branch this is, so a default here would
    #: make the two fields able to disagree silently — a future `tv_display`
    #: construction that omitted the stamp would restore the defect this rule
    #: exists to close, and no consumer would notice, because every other reader
    #: of this type looks only at `kind`.
    generated_at: datetime | None


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


def _drawn_from(preview: Rendition, source: ThumbnailSource) -> bool:
    """Whether this cached wall preview can have been made from `source`.

    **The catalogue's staleness rule does not reach this question**, and the gap
    is structural rather than an oversight. `is_current` compares a rendition
    against the *original*, which is right for every rendition drawn from the
    original — and a wall preview is the one that is not: when a work has a
    canvas, the preview is drawn from the canvas, a rendition itself. Composing a
    canvas, or recomposing one in a new mat colour, never touches the original,
    so the hash test answers "current" about an image the preview has never
    seen. The two ways that surfaces: a Work page badged "wall render" over the
    bare master, and a mat colour a curator sets that changes the wall and not
    the picture in front of them.

    Time is the comparison because it is the only fact both rows carry that moves
    when the canvas is redrawn — the path does not (a recompose writes the same
    file) and the hash does not (it is the original's). `record_rendition` upserts
    the geometry row and stamps `generated_at` afresh, so a redrawn canvas is
    newer than a preview taken before it — for as long as the wall clock runs
    forwards. `datetime.now(UTC)` is not monotonic, so a backwards correction
    landing between the two writes reinstates the defect until the original
    changes. Not engineered around: this is a single-operator local application,
    and the alternative is carrying a monotonic counter on a row that has no other
    use for one.

    An exact tie regenerates, which is the harmless direction: the two writes are
    separated by an image encode so it does not arise in practice, and paying one
    needless re-encode is the right side of a trade against serving a picture that
    is not what the work looks like. The window the other way is knowingly
    accepted and is the same shape: `wall_preview()` reads its source, encodes,
    and only then stamps its own row, so a canvas recomposed *inside* that window
    yields a preview row postdating a canvas it was never drawn from. One image
    encode wide, on a surface one person drives.

    **What this deliberately does not answer, and cannot: what the cached
    preview was actually drawn from.** Nothing records it, so the master branch
    below has to assume, and the assumption is wrong in one reachable state — a
    `tv_display` row that is current by hash but whose file has gone, which
    `preparation.py` documents as what a restored catalogue or a cleared `ready/`
    leaves. `source_for` then falls back to the master while the cache still holds
    the canvas-derived picture, and a curator is served a matted 16:9 preview
    under a badge reading "master image" — this defect with its two sides swapped.
    It predates this rule rather than arriving with it, and closing it needs the
    preview's provenance modelled on the row rather than inferred from the
    current source's timestamp. Filed as #116; do not close it by regenerating whenever an
    absent-file `tv_display` row exists, which spends a re-encode on every load for
    a preview legitimately drawn from the master. (A thumbnail has no such case:
    it is drawn from the master and nothing else.)
    """
    if source.generated_at is None:
        # Drawn from the master *now* — see the docstring for why "now" is not the
        # same claim as "when this preview was made", and what that costs.
        return True
    return preview.generated_at > source.generated_at


class ThumbnailService:
    """Produce and cache small copies of held works: thumbnails and wall previews."""

    def __init__(self, catalogue: CatalogueService, settings: ThumbnailSettings) -> None:
        self._catalogue = catalogue
        self._settings = settings

    def source_for(self, artwork_id: str) -> ThumbnailSource:
        """The held image this work's wall preview would be made from.

        Separate from `wall_preview` so a listing can say what the Work page will
        show — and say why it will show nothing — without decoding an image to
        find out. A thumbnail is drawn from the master alone, so whether this
        raises is also whether a tile has a picture.
        """
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ThumbnailUnavailable("No master image has been acquired for this work yet.")

        # Newest first, which is the order the wall prefers them in — expressed
        # once, beside the records, so a card and the wall cannot show different
        # pictures of the same work. This walked the store's own order and took
        # the first current row it met; two television renders at different
        # geometries are reachable under the unique index, and on such a work the
        # two would have disagreed with nothing saying which was right.
        views = {view.rendition.id: view for view in self._catalogue.list_renditions(artwork_id)}
        for rendition in tv_renditions_newest_first([view.rendition for view in views.values()]):
            if views[rendition.id].stale:
                continue
            rendered = self._settings.art_root / rendition.relative_path
            # Kept walking rather than falling straight to the master: a recorded
            # render whose file has gone is not a reason to ignore an older one
            # that is still there and still current.
            if rendered.is_file():
                return ThumbnailSource(
                    kind=RenditionKind.TV_DISPLAY.value,
                    path=rendered,
                    generated_at=rendition.generated_at,
                )

        return self._master(original.relative_path)

    def _master(self, relative: str) -> ThumbnailSource:
        master = self._settings.art_root / relative
        if not master.is_file():
            raise ThumbnailUnavailable(f"The master image is recorded at {relative} but no file is there.")
        return ThumbnailSource(kind="original", path=master, generated_at=None)

    def thumbnail(self, artwork_id: str, *, large: bool = False) -> Path:
        """An absolute path to a current thumbnail — the work itself — generating one if needed.

        Drawn from the master and nothing else, whatever canvas the work has, so
        a tile shows the work at its own aspect rather than the wall's mat and
        bars. Its parent is the original, so the catalogue's staleness rule is
        the whole currency test.

        `large` is the same product in a bigger box (`LARGE_THUMBNAIL_MAX_EDGE_PX`),
        cached in its own directory and recorded as its own row: the catalogue
        keys a rendition on its kind *and* its box, so the two sizes are two
        rows and neither overwrites the other.
        """
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ThumbnailUnavailable("No master image has been acquired for this work yet.")
        source = self._master(original.relative_path)
        return self._cached(
            artwork_id,
            source,
            kind=RenditionKind.THUMBNAIL,
            dirname=_LARGE_THUMBNAIL_DIRNAME if large else _THUMBNAIL_DIRNAME,
            max_edge=LARGE_THUMBNAIL_MAX_EDGE_PX if large else THUMBNAIL_MAX_EDGE_PX,
            quality=THUMBNAIL_JPEG_QUALITY,
        )

    def wall_preview(self, artwork_id: str) -> Path:
        """An absolute path to a current wall preview, generating one if needed.

        Drawn from what `source_for` names: the current canvas, mat and all, or
        the master where the work has none yet.
        """
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
        # All five conditions, because each one alone is satisfiable while the
        # cached file is wrong: a fresh row can point at a file someone deleted,
        # or at another path than this product's (a row written before the
        # products had their own directories, whose file may be a canvas copy
        # under a thumbnail's name), a present file can predate the master it
        # claims to depict, and a wall preview of the master can outlive the
        # moment a canvas replaced it as what this work looks like.
        if held is not None and not held.stale and recorded_here and cached.is_file() and _drawn_from(held.rendition, source):
            return cached

        if held is not None and not held.stale and recorded_here and cached.is_file():
            # Reached only when `_drawn_from` is the condition that failed, which
            # is the one whose *wrong* answer costs work rather than a wrong
            # picture: anything holding the comparison false — a canvas upsert
            # that stopped restamping, a clock correction, a caller passing the
            # wrong stamp — re-encodes a 4K canvas per page load and reaches the
            # operator as "the Work page got slow", against a journal with
            # nothing in it. INFO rather than DEBUG for that reason: the
            # deployment where this matters is the one running with DEBUG off.
            log.info(
                "regenerating the %s for %s: it predates the %s it would be drawn from",
                kind.value,
                artwork_id,
                source.kind,
                extra={
                    "event": "thumbnail.superseded",
                    "work_id": artwork_id,
                    "rendition_kind": kind.value,
                    "source_kind": source.kind,
                    "thumbnail_generated_at": held.rendition.generated_at.isoformat(),
                    "source_generated_at": None if source.generated_at is None else source.generated_at.isoformat(),
                },
            )

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
