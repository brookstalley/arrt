"""Every picture Arrt fetches from outside, kept for good under `ART_ROOT/pictures/`.

**The norm this module carries is the owner's** (`data-model.md` § Direction,
2026-10-06): a picture Arrt fetches from outside is kept forever, re-encoded as
JPEG and keyed by its source, and an ask of 2,048 px or less is answered from
here, never from the source again. Fewer requests to museums, faster pages, and
pictures that outlive a source going down.

**The layout is files only**: `pictures/<2 hex>/<digest>.<tier>.jpg`. There is
no table, because every row that points at a picture already carries the
`provider` and `url` the key is computed from; a table would make kept pictures a
catalogue class the backup and the derived-artifacts rule would then have to
cover. The store is a cache of outside pictures on this server's own disk: never
transported, and not in the backup, because it can be fetched again.

**Two tiers, 480 and 2,048 px on the long edge.** The smaller answers a review
card and the model's inline copy; the larger answers the picture a card enlarges.
Both are written from one fetch, the larger first in memory and the smaller cut
from it, and neither is ever enlarged: a source smaller than a tier is written at
its own size, and that file is then the whole of what the source served, so it
answers a larger ask too.

**Every byte here was re-encoded by this module.** A source's bytes are decoded
(through `encode_downscaled`, so Pillow's decompression-bomb guard applies) and
written as JPEG; what a source served is never stored as it came. So a file in
this tree is always a JPEG the store wrote, and a picture route can serve one
without decoding it again.

**Nothing here deletes a picture.** The only deletion is of this module's own
temporary files: each write's own on its way out, and strays from a process that
died mid-write, removed at startup by `clean`.

**Only this module calls a source's `fetch_preview`**
(`tests/unit/test_only_the_store_fetches_previews.py`). Anything that wants a
picture asks the store, so the norm's "never from the source again" has one place
to hold.
"""

import hashlib
import logging
import re
import string
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final, Protocol
from urllib.parse import parse_qsl, quote, urlsplit

from PIL import Image, UnidentifiedImageError

from arrt.library.services.imaging import encode_downscaled, measure
from arrt.services.errors import ServiceError

if TYPE_CHECKING:
    from arrt.library.services.discovery import DiscoveryService

log = logging.getLogger(__name__)

#: The long edges kept, smallest first. 480 is the review card's box on a retina
#: display; 2,048 is the enlarged view's, which keeps a scan opened at review as
#: sharp as it was when it was re-rendered per request (owner, 2026-10-06).
TIERS: Final[tuple[int, ...]] = (480, 2048)

#: JPEG quality for every tier. The browser card's figure, because these bytes
#: land on a screen a curator is looking at.
JPEG_QUALITY: Final[int] = 82

#: What a write's temporary file ends with. `clean` removes exactly these.
_TEMPORARY_SUFFIX: Final[str] = ".tmp"

#: A stored file's name: the key, its tier, and `.jpg`.
_STORED_NAME: Final[re.Pattern[str]] = re.compile(r"([0-9a-f]{64})\.(\d+)\.jpg")

#: Characters RFC 3986 never needs escaped. An escape of one of these is decoded
#: by `_normalise`; every other escape is kept, upper-cased.
_UNRESERVED: Final[frozenset[str]] = frozenset(string.ascii_letters + string.digits + "-._~")

_ESCAPE: Final[re.Pattern[str]] = re.compile(r"%([0-9A-Fa-f]{2})")

#: Characters a path or fragment may carry unescaped (RFC 3986 `pchar`, plus `/`
#: and, for a fragment, `?`).
_PATH_SAFE: Final[str] = "/:@!$&'()*+,;=?"

_DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}

#: How long one walk of the store answers the health panel. The store has no
#: ceiling (owner, 2026-10-06), so the walk grows with it; ten minutes keeps a
#: panel repainted every few seconds from walking a tree of tens of thousands of
#: files each time, and the reading carries its age so nobody mistakes it for now.
SIZE_REUSED_FOR: Final[timedelta] = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class StoreSize:
    """What the store holds, as of one walk: every kept tier file and their bytes.

    Temporary files are not counted: they are a write in flight, or debris the
    next start removes, and never a picture.
    """

    pictures_bytes: int
    pictures_files: int
    measured_at: datetime


class PictureRefused(Exception):
    """Bytes the store will not keep: not a picture, or one too large to open safely."""


class _NotKept(Exception):
    """Why `keep` has no picture to hand back. Never leaves this module."""


class PreviewSource(Protocol):
    """The one thing the store asks of a source: a preview's bytes, or `None`."""

    def fetch_preview(self, provider: str, url: str) -> bytes | None: ...


def _normalise(url: str) -> str:
    """One spelling for every way of writing the same URL.

    Lower-cases the scheme and host, drops a default port, sorts the query's
    parameters, and settles percent-encoding: an escaped unreserved character is
    decoded, every other escape is upper-cased, and a character that needs
    escaping is escaped.

    **The fragment is kept, and settled like the path.** SMK reports an image
    under the page a Wikidata item records, and `collection.smk.dk` names its
    object only in the fragment (`#/en/detail/KMS8010`), so dropping fragments
    would give every such work one key and answer each work's card with another's
    picture. An encoded slash in a fragment (`KKS12485%2F6`) stays encoded, since
    decoding it would change what the fragment says.

    **Every query parameter is kept**, only reordered: SMK's API spelling of an
    object (`api.smk.dk/api/v1/art?object_number=KMS1`) carries the object in
    its query. A `+` reads as a space there, as a form would read it.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        # A port that is not a number. Kept as written rather than refused: the
        # key only has to be stable, and this URL is one a source reported.
        port = None
        host = parts.netloc.rpartition("@")[2].lower()
    netloc = host if port is None or port == _DEFAULT_PORTS.get(scheme) else f"{host}:{port}"
    if parts.username is not None:
        userinfo = parts.username if parts.password is None else f"{parts.username}:{parts.password}"
        netloc = f"{userinfo}@{netloc}"
    path = _settled(parts.path or "/")
    query = "&".join(
        f"{quote(name, safe='')}={quote(value, safe='')}"
        for name, value in sorted(parse_qsl(parts.query, keep_blank_values=True))
    )
    fragment = _settled(parts.fragment)
    return f"{scheme}://{netloc}{path}" + (f"?{query}" if query else "") + (f"#{fragment}" if fragment else "")


def _settled(component: str) -> str:
    """Escape what must be escaped, then decode the escapes nothing needs and upper-case the rest."""
    escaped = quote(component, safe=_PATH_SAFE + "%")

    def settle(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        return character if character in _UNRESERVED else f"%{match.group(1).upper()}"

    return _ESCAPE.sub(settle, escaped)


def picture_key(provider: str, url: str) -> str:
    """The key a picture is kept under: `sha256(provider + "\\n" + _normalise(url))`.

    `url` is the instance's own (`FoundImage.url`, `CandidateImage.url`), never
    its preview's: the instance is what the picture is of, and a source may serve
    one instance's preview from more than one address. The same picture at two
    holders is two keys, deliberately — two instances.
    """
    return hashlib.sha256(f"{provider}\n{_normalise(url)}".encode()).hexdigest()


class PictureStore:
    """Pictures fetched from outside, kept at two sizes and answered from disk."""

    def __init__(
        self,
        directory: Path,
        *,
        art_root: Path,
        sources: PreviewSource | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Refuse a store outside the tree, at wiring time rather than mid-run.

        Every catalogue path is relative to `ART_ROOT`, so a picture written
        anywhere else has no path a row could record.

        `sources` is `None` in a deployment with no image source: it still
        answers from what is kept, and fetches nothing.
        """
        if not directory.is_relative_to(art_root):
            raise ServiceError(f"The picture store at {directory} must sit inside ART_ROOT at {art_root}.")
        self._directory = directory
        self._art_root = art_root
        self._prefix = directory.relative_to(art_root).parts
        self._sources = sources
        self._guard = threading.Lock()
        #: One lock per key being asked for, and how many asks hold or await it.
        #: Removed when the last one leaves, so the map holds only keys in flight.
        self._locks: dict[str, tuple[threading.Lock, int]] = {}
        self._now = now
        #: The last walk, reused for `SIZE_REUSED_FOR`.
        self._size: StoreSize | None = None
        self._size_lock = threading.Lock()

    @property
    def art_root(self) -> Path:
        """The tree every path this store hands out is relative to."""
        return self._art_root

    @property
    def directory(self) -> Path:
        """Where the pictures are kept."""
        return self._directory

    # -- reading ---------------------------------------------------------------

    def find(self, stored: str, *, max_edge: int) -> Path | None:
        """The kept file that answers an ask of `max_edge` px, for a path a row records.

        `stored` is a `preview_path` this store handed out. A path of any other
        shape is not this store's, and is answered with `None`, as is a picture
        not kept. Reading the disk failing is answered the same way and logged:
        a card without a picture is the outcome either way.
        """
        key = self.key_of(stored)
        if key is None:
            return None
        try:
            return self._find(key, max_edge=max_edge)
        except OSError as exc:
            log.warning(
                "the picture store could not be read",
                extra={"event": "picture.unreadable", "path": stored, "reason": str(exc)},
            )
            return None

    def find_for(self, provider: str, url: str, *, max_edge: int) -> Path | None:
        """The kept file that answers an ask of `max_edge` px for this instance, or `None`."""
        return self._find(picture_key(provider, url), max_edge=max_edge)

    def key_of(self, stored: str) -> str | None:
        """The key a path this store handed out names, or `None` for any other path."""
        parts = PurePosixPath(stored).parts
        if len(parts) != len(self._prefix) + 2 or parts[: len(self._prefix)] != self._prefix:
            return None
        bucket, name = parts[len(self._prefix) :]
        matched = _STORED_NAME.fullmatch(name)
        if matched is None or bucket != matched.group(1)[:2] or int(matched.group(2)) not in TIERS:
            return None
        return matched.group(1)

    def owns(self, stored: str) -> bool:
        """Whether `stored` is under this store's directory, whatever its shape."""
        return PurePosixPath(stored).parts[: len(self._prefix)] == self._prefix

    def relative(self, path: Path) -> str:
        """`path` as a row records it: relative to `ART_ROOT`."""
        return path.relative_to(self._art_root).as_posix()

    def _find(self, key: str, *, max_edge: int) -> Path | None:
        """The smallest tier at or above the ask; else a smaller tier that is the source's full size."""
        for tier in TIERS:
            if tier >= max_edge and _present(self._path(key, tier)):
                return self._path(key, tier)
        # Nothing at or above the ask. A tier whose file is smaller than the tier
        # is everything the source served, so nothing larger exists to be had.
        for tier in reversed(TIERS):
            path = self._path(key, tier)
            if tier < max_edge and _present(path) and _long_edge(path) < tier:
                return path
        return None

    def _path(self, key: str, tier: int) -> Path:
        return self._directory / key[:2] / f"{key}.{tier}.jpg"

    # -- writing ---------------------------------------------------------------

    def keep(self, provider: str, url: str, preview_url: str) -> str | None:
        """The kept picture of this instance, fetching `preview_url` once if it is not kept yet.

        Returns the largest tier's path relative to `ART_ROOT`, which is what a
        row records as its `preview_path`, or `None` when no picture is kept.

        **Never raises.** A picture that will not arrive costs its instance a
        card picture, never its place in a run: the instance is still real,
        selectable, and carries its source URL. Each way it fails is logged with
        its own reason.

        **Two asks for one key in this process make one fetch.** The second waits
        for the first and then finds what it wrote.
        """
        key = picture_key(provider, url)
        try:
            with self._held(key):
                kept = self._kept_or_fetched(key, provider, preview_url)
        except _NotKept as exc:
            return self._absent(url, str(exc))
        return self.relative(kept)

    def _kept_or_fetched(self, key: str, provider: str, preview_url: str) -> Path:
        """The largest tier, fetched and written first if it is not kept. Raises `_NotKept` with the reason."""
        largest = self._path(key, TIERS[-1])
        try:
            # The largest tier is written last, so its presence means every tier is.
            if _present(largest):
                return largest
        except OSError as exc:
            raise _NotKept(f"the store could not be read: {exc}") from exc
        if self._sources is None:
            raise _NotKept("no image source is configured to fetch it from")
        try:
            payload = self._sources.fetch_preview(provider, preview_url)
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a provider fault must not fail a work
            # The seam promises `None` for a preview it cannot get, and a
            # provider raising past that would otherwise fail a whole run over
            # one picture. Enforced here rather than trusted.
            raise _NotKept(f"the provider raised {type(exc).__name__}: {exc}") from exc
        if not payload:
            raise _NotKept("the provider returned no bytes")
        try:
            return self._put(key, payload)
        except PictureRefused as exc:
            raise _NotKept(f"the bytes are not a picture it will keep: {exc}") from exc
        except OSError as exc:
            # A full or read-only disk degrades the card; it must not end a run
            # that has already found its images.
            raise _NotKept(f"the picture could not be written: {exc}") from exc

    def put(self, provider: str, url: str, payload: bytes) -> Path:
        """Re-encode `payload` and keep it as this instance's picture, returning the largest tier.

        Raises `PictureRefused` for bytes that are not a picture, or are one too
        large to open safely, and `OSError` when the disk refuses the write.
        """
        key = picture_key(provider, url)
        with self._held(key):
            return self._put(key, payload)

    def _put(self, key: str, payload: bytes) -> Path:
        try:
            frames = [encode_downscaled(BytesIO(payload), max_edge=TIERS[-1], quality=JPEG_QUALITY).data]
            # Each smaller tier is cut from the largest, never from the source again.
            for tier in reversed(TIERS[:-1]):
                frames.insert(0, encode_downscaled(BytesIO(frames[-1]), max_edge=tier, quality=JPEG_QUALITY).data)
        except Image.DecompressionBombError as exc:
            # Pillow's own guard, named apart because a file engineered to
            # exhaust memory is worth a different line from a corrupt one.
            raise PictureRefused(f"it is too large to open safely: {exc}") from exc
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            # `ValueError` for the mode `convert` refuses (`La`); see `imaging.py`.
            raise PictureRefused(f"it could not be read as a picture: {exc}") from exc
        # Smallest first, so the largest tier's presence means every tier is
        # written: `keep` asks only after the largest.
        for tier, data in zip(TIERS, frames, strict=True):
            self._write(self._path(key, tier), data)
        largest = self._path(key, TIERS[-1])
        log.info(
            "kept a picture",
            extra={
                "event": "picture.kept",
                "path": self.relative(largest),
                "bytes": {str(tier): len(data) for tier, data in zip(TIERS, frames, strict=True)},
            },
        )
        return largest

    def _write(self, destination: Path, data: bytes) -> None:
        """Write `data` at `destination` through a temporary name of its own, then rename it."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        # A name per attempt, so two writers can never interleave bytes in one
        # temporary file; rename is atomic, so a reader sees the old file or the
        # new one and never a half.
        staging = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}{_TEMPORARY_SUFFIX}")
        try:
            staging.write_bytes(data)
            staging.replace(destination)
        finally:
            # A no-op after a successful rename. After a failed one, the cleanup
            # may fail for the reason the write did, and the write's failure is
            # the one worth raising.
            with suppress(OSError):
                staging.unlink(missing_ok=True)

    @contextmanager
    def _held(self, key: str) -> Iterator[None]:
        """Hold this key's lock, so a second ask waits for the first rather than fetching too."""
        with self._guard:
            lock, users = self._locks.get(key, (threading.Lock(), 0))
            self._locks[key] = (lock, users + 1)
        try:
            with lock:
                yield
        finally:
            with self._guard:
                lock, users = self._locks[key]
                if users == 1:
                    del self._locks[key]
                else:
                    self._locks[key] = (lock, users - 1)

    def _absent(self, url: str, why: str) -> None:
        """One exit for every way a picture fails to be kept, so the log line cannot drift."""
        log.info(
            "no picture was kept for an instance; review will fall back to its source URL",
            extra={"event": "picture.absent", "image_url": url, "reason": why},
        )

    # -- the health panel -----------------------------------------------------------

    def size(self) -> StoreSize:
        """How many picture files the store keeps and their bytes, from a walk at most ten minutes old.

        One walk at a time: a second caller while one is running waits for it
        and gets its answer, rather than walking the tree again beside it.
        """
        with self._size_lock:
            now = self._now()
            if self._size is None or now - self._size.measured_at >= SIZE_REUSED_FOR:
                self._size = self._walk(now)
            return self._size

    def _walk(self, now: datetime) -> StoreSize:
        total = files = 0
        if self._directory.is_dir():
            for path in self._directory.rglob("*.jpg"):
                try:
                    if not path.is_file():
                        continue
                    total += path.stat().st_size
                except OSError:
                    # Gone between listing and stat, or unreadable: it is not
                    # counted, and the next walk counts it if it is there.
                    continue
                files += 1
        return StoreSize(pictures_bytes=total, pictures_files=files, measured_at=now)

    # -- startup -----------------------------------------------------------------

    def clean(self) -> int:
        """Remove the temporary files a process that died mid-write left behind. Run at startup.

        The store's only deletion: it removes files ending in `.tmp` and nothing
        else, and a temporary file is never a picture anything reads.
        """
        removed = 0
        if self._directory.is_dir():
            for stray in self._directory.rglob(f"*{_TEMPORARY_SUFFIX}"):
                if stray.is_file():
                    stray.unlink(missing_ok=True)
                    removed += 1
        log.info("cleaned the picture store", extra={"event": "pictures.cleaned", "removed": removed})
        return removed


def _present(path: Path) -> bool:
    """Whether a kept file is there. A zero-byte file is not a picture and does not count."""
    try:
        return path.stat().st_size > 0
    except FileNotFoundError:
        return False


#: What a kept file's header can fail with. Named rather than written in place: the
#: formatter's 3.14 style unparenthesises a bare multi-type `except`, which the
#: root suite's older interpreter cannot parse when it reads this source.
_UNREADABLE_HEADER: Final = (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError)


def _long_edge(path: Path) -> int:
    """A kept file's long edge, read from its header. A file that will not say is never full size."""
    try:
        return max(measure(path))
    except _UNREADABLE_HEADER:
        return TIERS[-1]


# -- the import of what `previews/` held ------------------------------------------


@dataclass(frozen=True, slots=True)
class PreviewImport:
    """What one import of the old preview directory did, by row and by file."""

    #: Rows now pointing at the store.
    imported: int
    #: Rows naming a file that is not there. Left as they are.
    missing: int
    #: Rows naming a file that is not a picture the store will keep. Left as they are.
    refused: int
    #: Rows whose file could not be read, or whose picture or row could not be written.
    failed: int
    #: Files in the old directory that no row names. Imported nowhere, left in place.
    unnamed: int

    @property
    def done(self) -> bool:
        """Whether the old directory holds nothing a row still needs: it may be removed by hand."""
        return self.failed == 0


def import_previews(store: PictureStore, discovery: DiscoveryService, *, legacy: Path) -> PreviewImport:
    """Import every file in `legacy` that a row names, under that row's key, and repoint the row.

    Idempotent: a row already pointing at the store is not under `legacy`, so a
    second import finds nothing to do. A picture already kept under the row's key
    (two rows sharing one old file, or a row recorded since) repoints the row
    without reading the file again. Nothing is deleted: the operator removes
    `legacy` by hand once the log line reports `done`.
    """
    prefix = PurePosixPath(legacy.relative_to(store.art_root).as_posix()).parts
    named: set[str] = set()
    imported = missing = refused = failed = 0
    for run in discovery.list_runs():
        for work in discovery.list_candidate_works(run.id):
            for image in discovery.list_candidate_images(work.id):
                if image.preview_path is None or PurePosixPath(image.preview_path).parts[: len(prefix)] != prefix:
                    continue
                named.add(image.preview_path)
                try:
                    kept = store.find_for(image.provider, image.url, max_edge=TIERS[-1])
                    if kept is None:
                        source = store.art_root / image.preview_path
                        if not source.is_file():
                            missing += 1
                            continue
                        kept = store.put(image.provider, image.url, source.read_bytes())
                    discovery.repoint_preview(image.id, store.relative(kept))
                except PictureRefused:
                    refused += 1
                    continue
                except (OSError, ServiceError) as exc:
                    log.warning(
                        "a preview could not be imported into the picture store",
                        extra={"event": "pictures.import_failed", "candidate_image_id": image.id, "reason": str(exc)},
                    )
                    failed += 1
                    continue
                imported += 1
    unnamed = 0
    if legacy.is_dir():
        unnamed = sum(1 for path in legacy.iterdir() if path.is_file() and store.relative(path) not in named)
    report = PreviewImport(imported=imported, missing=missing, refused=refused, failed=failed, unnamed=unnamed)
    # At INFO whatever it found, so an operator waiting to remove `previews/`
    # can see the import ran and whether it is done.
    log.info(
        "imported candidate previews into the picture store",
        extra={
            "event": "pictures.imported",
            "imported": imported,
            "missing": missing,
            "refused": refused,
            "failed": failed,
            "unnamed": unnamed,
            "done": report.done,
        },
    )
    return report
