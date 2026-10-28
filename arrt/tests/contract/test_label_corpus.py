"""The contract's label corpus quotes the name splits and nationalities Arrt seeds.

`contract/vectors/label-corpus.json` is the real records every renderer is
measured against, and its promise is that the artist, the name split and the
nationality are what the wall carries for them. Arrt is where that is decided:
the seed tables (`arrt/src/arrt/seed/names.py`) store each split, and the
manifest carries the short nationality where one is authored. So this suite
holds the corpus to those tables, and each renderer's suite holds its own copy
to the corpus.

**Written because the promise has broken before.** A preview tool's copy of the
reference record drifted from the suite's for as long as somebody kept the two
in step by hand, and a corpus quoting a split the table no longer holds is an
instrument showing records that are not on the wall, while every test over it
stays green because they all read the same stale copy.
"""

import json

import pytest
from arrt_contract import root

from arrt.seed.names import SEEDED_DISPLAY_NATIONALITIES, SEEDED_NAME_PARTS

CORPUS = json.loads((root() / "vectors" / "label-corpus.json").read_text(encoding="utf-8"))["records"]


def test_the_tables_and_the_corpus_were_read():
    """The failure this file is most likely to have is silence: every comparison below holds over nothing."""
    assert len(SEEDED_NAME_PARTS) >= 20
    assert SEEDED_DISPLAY_NATIONALITIES
    assert len(CORPUS) >= 8


def test_every_record_naming_a_seeded_artist_quotes_the_seeded_split():
    """**`moche` is compared like any other record.** The table carries it as `(None, None)`,
    an authored answer that a culture has no family name, so stating no parts is the agreement."""
    compared = 0
    for key, record in CORPUS.items():
        artist = record.get("artist")
        if artist is None or artist not in SEEDED_NAME_PARTS:
            continue
        family, given = SEEDED_NAME_PARTS[artist]
        compared += 1
        assert record.get("artist_family_name") == family, f"{key}: {artist}'s family name"
        assert record.get("artist_given_name") == given, f"{key}: {artist}'s given name"
    assert compared >= 4, f"only {compared} record(s) were checked against the table"


def test_a_record_the_table_says_nothing_about_carries_no_split():
    """A forward guard: an artist absent from the table gets no parts, so a record that invented
    them would exercise a renderer against a manifest Arrt cannot produce. Today every artist the
    corpus names is in the table, so the loop body not running is the expected state."""
    for key, record in CORPUS.items():
        artist = record.get("artist")
        if artist is None or artist in SEEDED_NAME_PARTS:
            continue
        assert "artist_family_name" not in record, key
        assert "artist_given_name" not in record, key


def test_every_record_quotes_the_nationality_the_manifest_would_carry():
    """The manifest carries the authored short form where there is one, never the recorded prose."""
    compared = 0
    for key, record in CORPUS.items():
        artist = record.get("artist")
        if artist is None or artist not in SEEDED_DISPLAY_NATIONALITIES:
            continue
        compared += 1
        assert record.get("artist_nationality") == SEEDED_DISPLAY_NATIONALITIES[artist], key
    assert compared, "no corpus record covers an artist the short-nationality table carries"


@pytest.mark.parametrize("artist", ["Katsushika Hokusai", "Frank Lloyd Wright", "Moche"])
def test_the_records_that_defeat_each_heuristic_are_seeded(artist):
    """The records the corpus exists for, so dropping one from the table is noticed here."""
    assert artist in SEEDED_NAME_PARTS
