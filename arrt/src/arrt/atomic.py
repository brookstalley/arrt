"""Writing a file so that whoever reads it sees the old one or the new one, never half of either.

**One writer, because every hand-written copy of it differed in the step it
left out.** Some staged at a fixed name, which two writers of the same file
share: one's rename moves the other's half-written bytes into place, and the
second rename finds nothing to move. Most never flushed, so a rename could
publish a name whose bytes were still in a buffer when the power went. So the
steps are written once, here, in the order that makes each one count:

1. **Stage beside the destination**, because a rename is atomic only within one
   file system, and the obvious temporary directory is often another.
2. **Under a name no other writer can hold**: created exclusively under a
   name the temporary-file module draws for this attempt, or under the token a
   caller passes, which is refused rather than shared if it ever repeats.
3. **Flush and fsync the file**, so the bytes are on the disk before any name
   points at them.
4. **Rename it over the destination**, the one step a reader can observe.
5. **Fsync the directory**, so the rename itself survives a power cut rather
   than reverting to the old name with the new bytes nowhere.
6. **Remove the staging file on any failure**, including an interrupt, so a
   failed write strands nothing.

A staged name is hidden and ends `.tmp`: hidden so nothing that lists a
directory for its real files takes one for a finished file, and `.tmp` so a
store that sweeps its own debris at start-up (`pictures.py`) finds it.

**Neutral ground.** Both sides of the Library/Programming seam write files this
way, so it sits at the package root, importing nothing from either.
"""

import contextlib
import errno
import logging
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO, Final

log = logging.getLogger(__name__)

#: How old a staged file must be before a later attempt at the same destination
#: removes it as debris. A process killed mid-write leaves its staging file
#: behind, and with a fresh name per attempt nothing else would ever claim it.
#: Longer than any one write here can take (the slowest, a tiled fetch, is
#: stopped at its own timeout), so a writer still at work is never swept.
STALE_STAGING_AFTER: Final[timedelta] = timedelta(days=1)

#: What `fsync` on a directory raises on a file system that does not sync
#: directories. The rename has already happened by then, so the write stands.
_DIRECTORY_SYNC_UNSUPPORTED: Final[frozenset[int]] = frozenset({errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP})


def _shape(destination: Path, *, keep_suffix: bool) -> tuple[str, str]:
    """The prefix and suffix a staging name for `destination` is made of, around its token."""
    if keep_suffix:
        return f".{destination.stem}.", f".partial{destination.suffix}"
    return f".{destination.name}.", ".tmp"


def staging_path(destination: Path, *, token: str | None = None, keep_suffix: bool = False) -> Path:
    """A free name beside `destination` for a writer that creates the file itself. Nothing is left there.

    For a writer that is handed a path and refuses one that exists — the tile
    fetcher's binary, and `VACUUM INTO` — so the name is drawn by creating it
    exclusively and removing it again. `keep_suffix` keeps the destination's
    extension last, for a writer that chooses its encoder by the extension
    (`.<stem>.<token>.partial<suffix>`); otherwise `.<name>.<token>.tmp`. The
    directory must exist.
    """
    prefix, suffix = _shape(destination, keep_suffix=keep_suffix)
    if token is not None:
        return destination.with_name(f"{prefix}{token}{suffix}")
    # Drawn by `tempfile` rather than from `uuid`: the same unguessable,
    # exclusively-created name, and one a test runner does not count as a read
    # of randomness the way it counts `uuid4`.
    descriptor, name = tempfile.mkstemp(dir=destination.parent, prefix=prefix, suffix=suffix)
    os.close(descriptor)
    os.unlink(name)  # noqa: PTH108 -- the descriptor-level half of the draw `mkstemp` began, not a discard
    return Path(name)


def _create_staging(destination: Path, token: str | None) -> tuple[Path, BinaryIO]:
    """Create a staging file of this attempt's own, exclusively, and open it for writing."""
    if token is not None:
        path = staging_path(destination, token=token)
        # "x": created here or refused, so two attempts can never write one file.
        return path, path.open("xb")
    prefix, suffix = _shape(destination, keep_suffix=False)
    descriptor, name = tempfile.mkstemp(dir=destination.parent, prefix=prefix, suffix=suffix)
    return Path(name), os.fdopen(descriptor, "wb")


def sync_file(path: Path) -> None:
    """Put a file's bytes on the disk, for a file some other process wrote."""
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def sync_directory(directory: Path) -> None:
    """Make a rename into `directory` durable. A file system that cannot is let be."""
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno not in _DIRECTORY_SYNC_UNSUPPORTED:
            raise
        log.debug("this file system does not sync directories: %s", directory)
    finally:
        os.close(descriptor)


def promote(staged: Path, destination: Path) -> None:
    """Rename a whole, synced staging file over `destination`, and make the rename durable."""
    staged.replace(destination)
    sync_directory(destination.parent)


@contextmanager
def staged(destination: Path, *, token: str | None = None) -> Iterator[tuple[Path, BinaryIO]]:
    """Open a fresh staging file beside `destination`; on leaving, it is synced and closed, never renamed.

    For a writer that must look at what it wrote before deciding whether it
    becomes the destination (`direct.py`, which hands the staged file back to be
    proved an image first). Any exception out of the body removes the file and
    continues. On a clean exit the file stays, synced, and its owner promotes or
    discards it.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Outside the cleanup below, because a refused name is another attempt's
    # file, and removing it would be the very collision this prevents.
    path, handle = _create_staging(destination, token)
    try:
        with handle:
            yield path, handle
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; the staging file must go on any exit
        # Wider than `Exception` on purpose, and it swallows nothing: an
        # interrupt leaves the body as surely as an error, and either would
        # strand a file. The removal may fail for the reason the write did; the
        # write's failure is the one worth raising.
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
        raise


def write_with(destination: Path, fill: Callable[[BinaryIO], None], *, token: str | None = None) -> None:
    """Write whatever `fill` writes to the handle it is given, then make that the file at `destination`.

    A reader of `destination` sees the previous file until the rename, and the
    whole new one after. A `fill` that raises leaves the previous file and no
    staging file.
    """
    with staged(destination, token=token) as (path, handle):
        fill(handle)
    try:
        promote(path, destination)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; a failed rename leaves debris
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
        raise


def write_bytes(destination: Path, data: bytes, *, token: str | None = None) -> None:
    """Make `data` the file at `destination`, atomically and durably."""

    def fill(handle: BinaryIO) -> None:
        handle.write(data)

    write_with(destination, fill, token=token)


def sweep_stale(destination: Path, *, older_than: timedelta = STALE_STAGING_AFTER, now: float | None = None) -> int:
    """Remove staging files for `destination` that a killed writer left, if older than `older_than`.

    Only names this module would have staged for this destination, in either
    shape, so nothing a person or another writer put there is touched. A
    removal that fails is logged and the sweep carries on: debris is worth a line
    in the journal, never a failed write. Returns how many went.
    """
    directory = destination.parent
    if not directory.is_dir():
        return 0
    patterns = (f".{destination.name}.*.tmp", f".{destination.stem}.*.partial{destination.suffix}")
    # A file's mtime is stamped by the wall clock, so its age is measured by that one.
    cutoff = (now if now is not None else time.time()) - older_than.total_seconds()
    removed = 0
    for pattern in patterns:
        for stray in directory.glob(pattern):
            try:
                if stray.is_file() and stray.stat().st_mtime < cutoff:
                    stray.unlink()
                    removed += 1
            except OSError as exc:
                log.warning("could not remove the stale staging file at %s: %s", stray, exc)
    if removed:
        log.info("removed %d stale staging file(s) beside %s", removed, destination)
    return removed


__all__ = [
    "STALE_STAGING_AFTER",
    "promote",
    "staged",
    "staging_path",
    "sweep_stale",
    "sync_directory",
    "sync_file",
    "write_bytes",
    "write_with",
]
