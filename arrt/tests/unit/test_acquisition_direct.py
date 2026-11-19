"""The single-request fetch path, and the ceilings it enforces on the way in."""

import errno
import hashlib
import os
from contextlib import contextmanager

import pytest

from arrt import atomic
from arrt.library.acquisition.direct import direct_fetch


def _serves(*chunks: bytes, raises: Exception | None = None):
    @contextmanager
    def open_stream(_url: str):
        def gen():
            yield from chunks
            if raises is not None:
                raise raises

        yield gen()

    return open_stream


def _run(tmp_path, open_stream, *, max_bytes=10_000_000, name="work.jpg"):
    return direct_fetch(
        "https://gallery.example.com/image.jpg",
        destination=tmp_path / "raw" / name,
        open_stream=open_stream,
        max_bytes=max_bytes,
    )


class TestTheHappyPath:
    def test_bytes_land_at_the_destination(self, tmp_path):
        result = _run(tmp_path, _serves(b"abc", b"def"))
        assert result.usable
        assert result.path.read_bytes() == b"abcdef"

    def test_the_size_and_hash_describe_what_arrived(self, tmp_path):
        result = _run(tmp_path, _serves(b"abc", b"def"))
        assert result.byte_size == 6
        assert result.content_hash == hashlib.sha256(b"abcdef").hexdigest()

    def test_the_parent_directory_is_created(self, tmp_path):
        result = _run(tmp_path, _serves(b"x"))
        assert result.path.parent.is_dir()

    def test_the_destination_is_never_written_here(self, tmp_path):
        # Promotion is the caller's step, taken only once the bytes are proved
        # readable — so a failing fetch can never cost a work the image it holds.
        result = _run(tmp_path, _serves(b"x"))
        assert result.path != tmp_path / "raw" / "work.jpg"
        assert not (tmp_path / "raw" / "work.jpg").exists()


class TestTheZeroByteGuard:
    def test_an_empty_body_is_not_usable(self, tmp_path):
        result = _run(tmp_path, _serves())
        assert not result.usable
        assert "no bytes" in result.detail

    def test_an_empty_body_leaves_no_file_behind(self, tmp_path):
        # A zero-byte file is indistinguishable from a good one by name, which is
        # the failure the catalogue refuses to record.
        _run(tmp_path, _serves())
        assert not (tmp_path / "raw" / "work.jpg").exists()
        # Nothing at all, hidden staging files included, whatever they are named.
        assert list((tmp_path / "raw").iterdir()) == []

    def test_a_body_of_only_empty_chunks_is_empty(self, tmp_path):
        result = _run(tmp_path, _serves(b"", b"", b""))
        assert not result.usable


class TestTheSizeCeiling:
    def test_a_body_over_the_ceiling_is_refused(self, tmp_path):
        result = _run(tmp_path, _serves(b"x" * 100), max_bytes=50)
        assert not result.usable
        assert "ceiling" in result.detail

    def test_an_oversized_body_leaves_nothing_on_disk(self, tmp_path):
        # Truncating would record a half-image nothing downstream could detect.
        _run(tmp_path, _serves(b"x" * 100), max_bytes=50)
        assert not (tmp_path / "raw" / "work.jpg").exists()
        # Nothing at all, hidden staging files included, whatever they are named.
        assert list((tmp_path / "raw").iterdir()) == []

    def test_a_body_exactly_at_the_ceiling_is_kept(self, tmp_path):
        result = _run(tmp_path, _serves(b"x" * 50), max_bytes=50)
        assert result.usable
        assert result.byte_size == 50

    def test_the_ceiling_is_enforced_across_chunks_not_per_chunk(self, tmp_path):
        # Ten small chunks over the limit must refuse just as one large one does.
        result = _run(tmp_path, _serves(*[b"x" * 10] * 10), max_bytes=50)
        assert not result.usable


class TestFailures:
    def test_a_transport_raising_mid_stream_is_a_recorded_failure(self, tmp_path):
        result = _run(tmp_path, _serves(b"abc", raises=RuntimeError("connection reset")))
        assert not result.usable
        assert "connection reset" in result.detail

    def test_a_partial_stream_leaves_no_file_at_the_destination(self, tmp_path):
        _run(tmp_path, _serves(b"abc", raises=RuntimeError("boom")))
        assert not (tmp_path / "raw" / "work.jpg").exists()

    def test_an_os_error_is_reported_rather_than_raised(self, tmp_path):
        result = _run(tmp_path, _serves(b"abc", raises=OSError("disk full")))
        assert not result.usable
        assert "disk full" in result.detail

    def test_a_failure_never_returns_a_hash(self, tmp_path):
        # A hash beside a failed fetch would be a hash of nothing in particular.
        result = _run(tmp_path, _serves(b"abc", raises=RuntimeError("boom")))
        assert result.content_hash is None
        assert result.byte_size == 0


class _FillsUp:
    """A staging file on a disk that refuses the write: it opens, and every write fails with `number`."""

    def __init__(self, handle, number):
        self._handle = handle
        self._number = number

    def write(self, _data):
        raise OSError(self._number, os.strerror(self._number))

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._handle.close()

    def __getattr__(self, name):
        return getattr(self._handle, name)


def _the_disk_refuses(monkeypatch, where, number):
    """The disk refuses at `where`: creating the staging file, or writing into it."""
    real = atomic._create_staging

    def create(destination, token):
        if where == "create":
            raise OSError(number, os.strerror(number))
        path, handle = real(destination, token)
        return path, _FillsUp(handle, number)

    monkeypatch.setattr(atomic, "_create_staging", create)


class TestTheDisksOwnFaults:
    """A full or read-only disk is no fault of the work's, so it is raised for the queue to pause on, not recorded."""

    @pytest.mark.parametrize(
        ("where", "number"),
        [("create", errno.EROFS), ("write", errno.ENOSPC), ("write", errno.EROFS)],
        ids=["read-only at create", "full mid-write", "read-only mid-write"],
    )
    def test_it_is_raised_and_leaves_nothing_staged(self, tmp_path, monkeypatch, where, number):
        _the_disk_refuses(monkeypatch, where, number)

        with pytest.raises(OSError, match=os.strerror(number)) as raised:
            _run(tmp_path, _serves(b"abc", b"def"))

        assert raised.value.errno == number
        assert list((tmp_path / "raw").iterdir()) == []

    def test_any_other_fault_writing_the_file_is_recorded_against_the_work(self, tmp_path, monkeypatch):
        """A refused permission is about this path, not the disk, so it stays one work's failed fetch."""
        _the_disk_refuses(monkeypatch, "write", errno.EACCES)

        result = _run(tmp_path, _serves(b"abc"))

        assert not result.usable
        assert os.strerror(errno.EACCES) in result.detail


class TestRefetching:
    def test_a_second_fetch_replaces_what_the_first_staged(self, tmp_path):
        _run(tmp_path, _serves(b"old"))
        result = _run(tmp_path, _serves(b"newer bytes"))
        assert result.path.read_bytes() == b"newer bytes"

    def test_a_failed_fetch_leaves_an_already_held_image_untouched(self, tmp_path):
        # The destination stands in for an image a previous acquisition promoted.
        # Nothing here may reach it, on success or on failure.
        held = tmp_path / "raw" / "work.jpg"
        held.parent.mkdir(parents=True)
        held.write_bytes(b"the image the work is displaying")

        _run(tmp_path, _serves(b"partial", raises=RuntimeError("boom")))

        assert held.read_bytes() == b"the image the work is displaying"
        # And the failed attempt's staging file went with it: the held image is all there is.
        assert list(held.parent.iterdir()) == [held]

    def test_two_fetches_of_one_work_at_once_each_keep_their_own_bytes(self, tmp_path):
        """The queue and a curator's retry can fetch one work at the same moment.

        The second fetch starts while the first is still streaming. Sharing one
        staging name, the second truncated the first's file under it and both
        handed back the same path, holding neither body whole.
        """
        inner = {}

        @contextmanager
        def first_stream(_url):
            def chunks():
                yield b"first-"
                inner["result"] = _run(tmp_path, _serves(b"second body"))
                yield b"body"

            yield chunks()

        outer = _run(tmp_path, first_stream)
        second = inner["result"]

        assert outer.path != second.path
        assert outer.path.read_bytes() == b"first-body"
        assert second.path.read_bytes() == b"second body"
        assert outer.content_hash == hashlib.sha256(b"first-body").hexdigest()


@pytest.mark.parametrize("chunks", [(b"a",), (b"a", b"b"), (b"a" * 1000,)])
def test_the_hash_always_matches_the_file_on_disk(tmp_path, chunks):
    # The hash is computed while streaming rather than by re-reading, so this is
    # the assertion that the two cannot drift.
    result = direct_fetch(
        "https://gallery.example.com/image.jpg",
        destination=tmp_path / "work.jpg",
        open_stream=_serves(*chunks),
        max_bytes=10_000,
    )
    assert result.content_hash == hashlib.sha256(result.path.read_bytes()).hexdigest()
