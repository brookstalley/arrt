"""The presentation master: the Original, upright, unmatted, capped, never enlarged."""

import pytest
from PIL import Image

from arrt.library.acquisition.master import make_master
from arrt.library.services.quality import PRESENTATION_MASTER_LONG_EDGE_PX
from arrt.services.errors import ServiceError


def _source(tmp_path, width, height, *, exif_orientation=None, mode="RGB"):
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
    assert not destination.with_name("w.jpg.making").exists()
