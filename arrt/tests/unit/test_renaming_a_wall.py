"""Renaming a wall: the service rule both surfaces bind.

A wall's name is the owner's word for a room, read on Walls, in History and in
every confirmation that names the wall. Nothing a Player reads carries it
(`player-contract.md`: a feed names works and slots, never the wall), so a
rename changes what people read and nothing a screen shows.
"""

import pytest

from arrt.programming.manifest.v2 import read_published
from arrt.services.errors import ServiceError


def test_a_wall_takes_its_new_name_trimmed(display, wall_id):
    renamed = display.rename_wall(wall_id, name="  The hall  ")

    assert renamed.name == "The hall"
    assert display.get_wall(wall_id).name == "The hall"


def test_renaming_keeps_everything_else_about_the_wall(display, wall_id):
    display.set_playback(wall_id, rotation_interval_seconds=900, shuffle=True)
    before = display.get_wall(wall_id)

    display.rename_wall(wall_id, name="The hall")

    after = display.get_wall(wall_id)
    assert (after.id, after.created_at, after.rotation_interval_seconds, after.shuffle) == (
        before.id,
        before.created_at,
        900,
        True,
    )


def test_a_blank_name_is_refused_and_the_old_one_kept(display, wall_id):
    before = display.get_wall(wall_id).name

    with pytest.raises(ServiceError, match="name cannot be empty"):
        display.rename_wall(wall_id, name="   ")

    assert display.get_wall(wall_id).name == before


def test_a_name_another_wall_has_is_refused_by_that_name(display, wall_id):
    display.add_wall(name="The study")

    with pytest.raises(ServiceError, match="The study"):
        display.rename_wall(wall_id, name="The study")


def test_renaming_a_wall_to_its_own_name_is_not_a_clash(display, wall_id):
    name = display.get_wall(wall_id).name

    assert display.rename_wall(wall_id, name=name).name == name


def test_an_unknown_wall_is_refused_by_id(display):
    with pytest.raises(ServiceError, match="nobody"):
        display.rename_wall("nobody", name="The hall")


def test_renaming_republishes_nothing(display, wall_id, wall_settings, ready_work):
    work = ready_work("Nighthawks")
    theme = display.add_theme(name="Evenings")
    display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=0)
    display.activate_theme(theme.id, wall_id=wall_id)
    path = wall_settings.manifest_v2_path(wall_id)
    assert read_published(path) is not None, "the fixture must publish a feed, or this test compares nothing"
    published = path.read_bytes()

    display.rename_wall(wall_id, name="The hall")

    assert path.read_bytes() == published
