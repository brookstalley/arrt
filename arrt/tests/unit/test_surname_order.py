"""Where an artist sorts on the Artists index: by surname, the owner's ruling on #173."""

import pytest

from arrt.library.services.artists import surname_key
from arrt.persistence.records import Artist


def an_artist(name, family_name=None):
    return Artist(id=f"id-{name}", name=name, family_name=family_name)


@pytest.mark.parametrize(
    ("name", "surname"),
    [
        ("Hans Holbein the Younger", "holbein"),
        ("Pieter Bruegel the Elder", "bruegel"),
        ("Vincent van Gogh", "gogh"),
        ("Anthony van Dyck", "dyck"),
        ("Leonardo da Vinci", "vinci"),
        ("Moche", "moche"),
        ("Salvador Dalí", "dali"),
        ("Martin Luther King Jr.", "king"),
    ],
)
def test_the_surname_is_the_last_word_once_a_generational_suffix_is_set_aside(name, surname):
    assert surname_key(an_artist(name))[0] == surname


def test_a_stored_family_name_wins_over_the_last_word():
    assert surname_key(an_artist("Zed Alpha", family_name="Zed"))[0] == "zed"


def test_a_name_that_is_only_a_suffix_word_still_sorts():
    """Nothing is left once the suffix goes, so the whole name is the key."""
    assert surname_key(an_artist("Jr."))[0] == "jr."


def test_shelf_order():
    names = ["Vincent van Gogh", "Hans Holbein the Younger", "Moche", "Salvador Dalí", "Charles Demuth"]

    shelved = sorted((an_artist(name) for name in names), key=surname_key)

    assert [artist.name for artist in shelved] == [
        "Salvador Dalí",
        "Charles Demuth",
        "Vincent van Gogh",
        "Hans Holbein the Younger",
        "Moche",
    ]
