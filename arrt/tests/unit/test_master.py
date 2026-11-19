"""The presentation master: the Original, upright, unmatted, capped, never enlarged."""

from pathlib import Path

import pytest
from PIL import Image

from arrt.library.acquisition.master import make_master
from arrt.library.services.quality import PRESENTATION_MASTER_LONG_EDGE_PX
from arrt.services.errors import ServiceError


def _source(tmp_path, width, height, *, exif_orientation=None, mode="RGB"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "original.jpg"
    image = Image.new(mode, (width, height), (200, 30, 30) if mode == "RGB" else 128)
    if exif_orientation is None:
        image.save(path, format="JPEG", quality=90)
    else:
        exif = image.getexif()
        exif[0x0112] = exif_orientation
        image.save(path, format="JPEG", quality=90, exif=exif)
    return path


def test_a_large_original_is_brought_to_the_cap_in_its_own_aspect(tmp_path):
    source = _source(tmp_path, 9000, 6000)

    master = make_master(source, destination=tmp_path / "presentation" / "w.jpg")

    assert (master.width, master.height) == (PRESENTATION_MASTER_LONG_EDGE_PX, 5120)
    with Image.open(master.path) as written:
        assert written.size == (PRESENTATION_MASTER_LONG_EDGE_PX, 5120)
        assert written.format == "JPEG"


def test_a_portrait_original_is_capped_on_its_long_edge(tmp_path):
    source = _source(tmp_path, 4000, 9600)

    master = make_master(source, destination=tmp_path / "w.jpg")

    assert (master.width, master.height) == (3200, PRESENTATION_MASTER_LONG_EDGE_PX)


def test_a_small_original_is_kept_at_its_own_size_never_enlarged(tmp_path):
    source = _source(tmp_path, 900, 700)

    master = make_master(source, destination=tmp_path / "w.jpg")

    assert (master.width, master.height) == (900, 700)


def test_an_original_stored_sideways_comes_out_upright(tmp_path):
    """A Player composes from this file alone, so an orientation left in a tag
    would be a sideways work on a screen nobody here can see."""
    source = _source(tmp_path, 3000, 1500, exif_orientation=6)

    master = make_master(source, destination=tmp_path / "w.jpg")

    assert (master.width, master.height) == (1500, 3000)
    with Image.open(master.path) as written:
        assert written.getexif().get(0x0112) in (None, 1)


def test_a_greyscale_original_becomes_rgb(tmp_path):
    source = _source(tmp_path, 800, 600, mode="L")

    master = make_master(source, destination=tmp_path / "w.jpg")

    with Image.open(master.path) as written:
        assert written.mode == "RGB"


def test_an_undecodable_original_is_refused_by_name_and_writes_nothing(tmp_path):
    source = tmp_path / "broken.jpg"
    source.write_bytes(b"not a picture")
    destination = tmp_path / "presentation" / "w.jpg"

    with pytest.raises(ServiceError, match=r"broken\.jpg could not be read"):
        make_master(source, destination=destination)

    assert not destination.exists()
    # No staging file either, whatever it is named.
    assert not destination.parent.exists() or list(destination.parent.iterdir()) == []


def test_two_makings_of_one_master_at_once_leave_a_whole_file_and_both_succeed(tmp_path, monkeypatch):
    """The queue's prepare and a regenerate can make one work's master at the same moment.

    The second making runs to the end while the first is between writing its
    bytes and renaming them into place. Staged at one shared name, the second
    overwrote the first's staging file and renamed it away, and the first's
    rename then found nothing: `FileNotFoundError`, and a master whose bytes
    were whichever writer's landed.
    """
    first_source = _source(tmp_path / "a", 1200, 800)
    second_source = _source(tmp_path / "b", 600, 900)
    destination = tmp_path / "presentation" / "w.jpg"
    rename = Path.replace
    seconds = []

    def interleave(self, target):
        # The first rename is the first making's; the second making runs whole
        # before it, its own rename passing straight through.
        if not seconds:
            seconds.append(None)
            seconds[0] = make_master(second_source, destination=destination)
        return rename(self, target)

    monkeypatch.setattr(Path, "replace", interleave)

    first = make_master(first_source, destination=destination)

    assert seconds, "the second making never ran inside the first, so nothing raced"
    with Image.open(destination) as written:
        written.load()
        assert written.size == (first.width, first.height) == (1200, 800)
    assert sorted(path.name for path in destination.parent.iterdir()) == ["w.jpg"]
