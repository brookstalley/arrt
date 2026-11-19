"""The one atomic writer, and the writers that use it.

Every file this server writes whole — a manifest, a master, a picture, a
thumbnail, the backup receipt — goes through `arrt.atomic`, so a reader sees the
old file or the new one and never half of either. The cases here are the ones a
hand-written copy got wrong: two writers of one file at once, bytes renamed into
place before they reach the disk, and a failure part-way that strands a staging
file or costs the destination what it held.
"""

import errno
import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from arrt import atomic
from arrt.library.acquisition.master import make_master
from arrt.persistence.backup import BACKUP_RECEIPT_FILENAME, CatalogueBackup
from arrt.programming.manifest.builder import write_atomically

NOON = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _opened_path(descriptor: int) -> str:
    """The name an open descriptor was opened by, so a fault can be aimed at one writer's staging file."""
    if sys.platform.startswith("linux"):
        return str(Path(f"/proc/self/fd/{descriptor}").readlink())
    import fcntl

    return fcntl.fcntl(descriptor, fcntl.F_GETPATH, bytes(1024)).rstrip(b"\0").decode()


def _refuse_syncing_staged(monkeypatch, destination: Path) -> list[str]:
    """Make the disk refuse to sync `destination`'s staging file, as a full disk does; return what was refused."""
    real = os.fsync
    refused: list[str] = []

    def fsync(descriptor):
        name = Path(_opened_path(descriptor)).name
        if name.startswith(f".{destination.name}.") and name.endswith(".tmp"):
            refused.append(name)
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(descriptor)

    monkeypatch.setattr(atomic.os, "fsync", fsync)
    return refused


# -- the writer itself --------------------------------------------------------------


def test_a_write_replaces_the_file_whole_and_leaves_nothing_beside_it(tmp_path):
    destination = tmp_path / "nested" / "file.bin"

    atomic.write_bytes(destination, b"first")
    atomic.write_bytes(destination, b"the second, longer body")

    assert destination.read_bytes() == b"the second, longer body"
    assert sorted(path.name for path in destination.parent.iterdir()) == ["file.bin"]


@pytest.mark.parametrize("raised", [RuntimeError("the source went away"), KeyboardInterrupt()])
def test_a_failure_from_inside_the_stream_keeps_the_old_file_and_no_staging_file(tmp_path, raised):
    """Bytes already staged when the stream fails, by an error or an interrupt alike."""
    destination = tmp_path / "file.bin"
    destination.write_bytes(b"what readers have now")
    staged_when_raised = []

    def fill(handle):
        handle.write(b"half of the new")
        handle.flush()
        staged_when_raised.extend(path.name for path in tmp_path.iterdir() if path.name.startswith("."))
        raise raised

    with pytest.raises(type(raised)):
        atomic.write_with(destination, fill)

    assert staged_when_raised, "nothing was staged, so the cleanup was not exercised"
    assert destination.read_bytes() == b"what readers have now"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["file.bin"]


def test_the_bytes_are_synced_before_the_rename_and_the_directory_after(tmp_path, monkeypatch):
    """The steps only one of the hand-written writers took, in the order that makes them count."""
    destination = tmp_path / "file.bin"
    events = []
    real_fsync = os.fsync
    real_replace = Path.replace

    def fsync(descriptor):
        events.append("sync directory" if Path(_opened_path(descriptor)).is_dir() else "sync file")
        return real_fsync(descriptor)

    def replace(self, target):
        events.append("rename")
        return real_replace(self, target)

    monkeypatch.setattr(atomic.os, "fsync", fsync)
    monkeypatch.setattr(Path, "replace", replace)

    atomic.write_bytes(destination, b"durable")

    assert events == ["sync file", "rename", "sync directory"]


def test_a_file_made_again_when_missing_is_staged_and_renamed_but_never_synced(tmp_path, monkeypatch):
    destination = tmp_path / "file.bin"
    destination.write_bytes(b"what readers have now")
    events = []
    real_replace = Path.replace

    def replace(self, target):
        events.append(("rename", self.name != target.name))
        return real_replace(self, target)

    monkeypatch.setattr(atomic.os, "fsync", lambda descriptor: events.append("sync"))
    monkeypatch.setattr(Path, "replace", replace)

    atomic.write_bytes(destination, b"cached", durable=False)

    assert events == [("rename", True)], "not renamed from a name of its own, or synced"
    assert destination.read_bytes() == b"cached"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["file.bin"]


def test_each_attempt_stages_under_a_name_of_its_own(tmp_path):
    destination = tmp_path / "file.bin"

    names = {atomic.staging_path(destination) for _ in range(50)}

    assert len(names) == 50
    assert all(name.parent == tmp_path for name in names)
    assert all(name.name.startswith(".file.bin.") and name.name.endswith(".tmp") for name in names)


def test_a_repeated_token_is_refused_rather_than_shared(tmp_path):
    """The file is created exclusively, so even two attempts handed one token never write one file."""
    destination = tmp_path / "file.bin"

    with atomic.staged(destination, token="same") as (path, handle):
        handle.write(b"the first attempt's")
        with pytest.raises(FileExistsError), atomic.staged(destination, token="same"):
            pass
        assert path.exists(), "the refused attempt removed the first attempt's file"

    assert path.read_bytes() == b"the first attempt's"


def test_the_extension_can_be_kept_last_for_a_writer_that_reads_it(tmp_path):
    staged = atomic.staging_path(tmp_path / "work.jpg", token="t", keep_suffix=True)

    assert staged.name == ".work.t.partial.jpg"
    assert staged.suffix == ".jpg"


@pytest.mark.parametrize(
    ("code", "survives"),
    [(errno.EINVAL, True), (errno.ENOTSUP, True), (errno.EIO, False)],
)
def test_a_directory_that_cannot_be_synced_is_let_be_and_any_other_fault_is_raised(tmp_path, monkeypatch, code, survives):
    def fsync(_descriptor):
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(atomic.os, "fsync", fsync)

    if survives:
        atomic.sync_directory(tmp_path)
    else:
        with pytest.raises(OSError, match=os.strerror(code)):
            atomic.sync_directory(tmp_path)


@pytest.mark.parametrize(("hours", "swept"), [(2, False), (30, True)])
def test_only_this_writer_s_stale_staging_files_for_the_destination_are_swept(tmp_path, hours, swept):
    """A killed writer's file goes once it is older than any write takes; nothing else is touched."""
    destination = tmp_path / "work.jpg"
    ours = [atomic.staging_path(destination), atomic.staging_path(destination, keep_suffix=True)]
    strangers = [tmp_path / "work.jpg.notes.tmp", tmp_path / ".other.jpg.abc.tmp", destination]
    aged = time.time() - hours * 3600
    for path in (*ours, *strangers):
        path.write_bytes(b"x")
        os.utime(path, (aged, aged))

    removed = atomic.sweep_stale(destination)

    assert removed == (len(ours) if swept else 0)
    assert all(path.exists() is not swept for path in ours)
    assert all(path.exists() for path in strangers)


# -- each writer that uses it -------------------------------------------------------


def _jpeg(path: Path, size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 40, 40)).save(path, format="JPEG")
    return path


def _write_manifest(tmp_path, attempt):
    destination = tmp_path / "theme-manifest.v2.json"
    return destination, lambda: write_atomically(destination, {"attempt": attempt})


def _write_master(tmp_path, attempt):
    destination = tmp_path / "presentation" / "w.jpg"
    source = _jpeg(tmp_path / f"source-{attempt}" / "original.jpg", (300 + attempt * 100, 200))
    return destination, lambda: make_master(source, destination=destination)


def _write_receipt(tmp_path, attempt):
    catalogue = tmp_path / "catalogue.sqlite"
    if not catalogue.exists():
        sqlite3.connect(catalogue).close()
    destination = tmp_path / BACKUP_RECEIPT_FILENAME
    job = CatalogueBackup(
        catalogue_path=catalogue,
        directory=tmp_path / "backups",
        receipt_path=destination,
        keep=5,
        clock=lambda: NOON + timedelta(days=attempt),
    )
    return destination, job.run


@pytest.mark.parametrize("writer", [_write_manifest, _write_master, _write_receipt], ids=["manifest", "master", "receipt"])
def test_a_writer_whose_disk_refuses_the_new_file_keeps_the_old_one_and_strands_nothing(tmp_path, monkeypatch, writer):
    destination, first = writer(tmp_path, 1)
    first()
    before = destination.read_bytes()
    destination, second = writer(tmp_path, 2)
    refused = _refuse_syncing_staged(monkeypatch, destination)

    with pytest.raises(OSError, match="No space left"):
        second()

    assert refused, "the fault never reached this writer's staging file, so nothing was tested"
    assert destination.read_bytes() == before
    assert [path.name for path in destination.parent.iterdir() if path.name.startswith(f".{destination.name}.")] == []


@pytest.mark.parametrize("writer", [_write_manifest, _write_master, _write_receipt], ids=["manifest", "master", "receipt"])
def test_a_file_that_cannot_be_made_again_is_synced_with_its_rename(tmp_path, monkeypatch, writer):
    destination, write = writer(tmp_path, 1)
    synced = []
    real = os.fsync
    monkeypatch.setattr(atomic.os, "fsync", lambda descriptor: synced.append(_opened_path(descriptor)) or real(descriptor))

    write()

    assert any(Path(name).name.startswith(f".{destination.name}.") for name in synced), "the file was not synced"
    assert any(Path(name) == destination.parent.resolve() for name in synced), "the rename was not synced"


def test_the_manifest_s_text_is_what_was_serialised(tmp_path):
    """The manifest writes text through a binary handle; the bytes must still be its JSON, whole."""
    destination = tmp_path / "theme-manifest.v2.json"

    write_atomically(destination, {"title": "Nuit étoilée", "entries": [1, 2]})

    assert json.loads(destination.read_text(encoding="utf-8")) == {"title": "Nuit étoilée", "entries": [1, 2]}
    assert destination.read_text(encoding="utf-8").endswith("}\n")


# -- the mode a written file has ---------------------------------------------------


def _write_plain(tmp_path):
    destination = tmp_path / "file.bin"
    atomic.write_bytes(destination, b"bytes")
    return destination


def _write_with_token(tmp_path):
    destination = tmp_path / "picture.jpg"
    atomic.write_bytes(destination, b"bytes", token="t-1")
    return destination


def _stage_then_promote(tmp_path):
    destination = tmp_path / "raw" / "original.jpg"
    with atomic.staged(destination) as (path, handle):
        handle.write(b"bytes")
    atomic.promote(path, destination)
    return destination


def _master(tmp_path):
    destination = tmp_path / "presentation" / "w.jpg"
    make_master(_jpeg(tmp_path / "source" / "original.jpg", (300, 200)), destination=destination)
    return destination


@pytest.mark.parametrize("umask", [0o022, 0o027], ids=["022", "027"])
@pytest.mark.parametrize(
    "write",
    [_write_plain, _write_with_token, _stage_then_promote, _master],
    ids=["write_bytes", "write_bytes with a token", "staged then promoted", "master"],
)
def test_a_written_file_has_the_mode_the_process_umask_gives_it(tmp_path, write, umask):
    """As `open` gives any file: a backup job or a share under another user reads what this writes.

    Two umasks, so a writer that fixed one mode (`mkstemp`'s `0o600`, or a
    hard-coded `0o644`) fails one of them.
    """
    previous = os.umask(umask)
    try:
        destination = write(tmp_path)
    finally:
        os.umask(previous)

    assert destination.stat().st_mode & 0o777 == 0o666 & ~umask
