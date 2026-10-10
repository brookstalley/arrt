"""Seeding the real 2024 index, and putting what it produced on a wall.

This runs against the tracked index itself rather than a fixture of it, because
the acceptance this chunk owes is about that corpus: the counts below were
measured from it, and a fixture would only prove the seeder survives a corpus
nobody has.

The image tree is synthesised. The deployed one lives on the Pi and holds
multi-megabyte museum scans; what the seeder does with a file is measure it, and
a stand-in of the right size at the right path exercises that identically.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from arrt.library.acquisition.mat import below_the_floor
from arrt.library.facade import UnplayableReason
from arrt.persistence.records import MatMethod, RenditionKind
from arrt.seed.ingest import SeedNote, seed_catalogue
from arrt.seed.legacy import read_index

#: The tracked index the 2024 wall is curated from, four levels up from here.
INDEX = Path(__file__).parents[3] / "all.json"

#: Measured from that file on 2026-08-01. Records and works differ because two
#: records describe one painting — same URL, same master, same title, differing
#: only in the mat colour someone chose for it.
RECORDS = 41
WORKS = 40

#: Works whose label will read short, by cause. Each is a count of *works* — not
#: of artists and not of records — because a label is set per work, and the three
#: units give different numbers for the same corpus.
#:
#: These are what remains *after* the source's own words are read. The index's
#: own parse of them leaves 14 works with no nationality; going back to the text
#: it parsed recovers nine of those, which is the whole reason that text is
#: treated as the authority.
WITHOUT_NATIONALITY = 5
WITHOUT_BIRTH_YEAR = 9
WITHOUT_MEDIUM = 2
WITHOUT_DIMENSIONS = 2


@pytest.fixture(scope="module")
def records():
    assert INDEX.exists(), f"the 2024 index should be tracked at {INDEX}"
    return read_index(INDEX)


@pytest.fixture
def art_root(records, tmp_path, jpeg):
    """A tree holding a master image for every record."""
    for record in records:
        jpeg(tmp_path / record.raw_path, width=6000, height=4000)
    return tmp_path


def _titles_below_the_floor(records):
    """The works whose 2024 mat is darker than the floor, from the index itself.
    By the last record for each URL, since the last is the one seeding takes."""
    last = {record.url: record for record in records}
    return {record.title for record in last.values() if below_the_floor(record.mat_hex)}


def _with_masters(service, report, art_root, decodable_jpeg):
    """Give each seeded work a presentation master, as its first preparation would.

    Seeding records what the 2024 tree holds; the master is made by the work's
    first preparation, which the startup queue runs. A small decodable picture
    stands in for it, because the corpus's own files are headers around no
    pixels and decoding forty 6000 px masters would only slow the suite.
    """
    for work in report.works:
        path = f"presentation/{work.work_id}.jpg"
        decodable_jpeg(art_root / path, width=400, height=300)
        service.record_rendition(
            artwork_id=work.work_id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
        )


def _as_their_first_preparation_would(service, report, art_root, decodable_jpeg):
    """Give each work a master, and a colour above the floor where the seed left it none.

    Seeding does not carry a 2024 colour below the floor, and the work's first
    preparation chooses one (the startup queue makes that happen). The tests
    about labels are not about that, so they start from where it leaves them.
    """
    _with_masters(service, report, art_root, decodable_jpeg)
    for work in report.works:
        if service.current_mat_color(work.work_id) is None:
            service.record_mat_color(artwork_id=work.work_id, hex_rgb="#2d2d3c", method=MatMethod.VISION_MODEL)


def counted(report, note):
    return [work for work in report.works if note in {entry.note for entry in work.notes}]


class TestTheIndexItself:
    def test_it_holds_the_records_this_chunk_was_measured_against(self, records):
        assert len(records) == RECORDS

    def test_two_of_them_describe_one_work(self, records):
        assert len({record.url for record in records}) == WORKS


class TestSeedingIt:
    def test_every_record_becomes_a_work_or_is_accounted_for(self, records, service, art_root):
        report = seed_catalogue(records, catalogue=service, art_root=art_root)

        assert len(report.works) == WORKS
        assert report.records_collapsed == RECORDS - WORKS
        assert len(report.works) + report.records_collapsed == report.records_read

    def test_the_catalogue_holds_exactly_those_works(self, records, service, art_root):
        seed_catalogue(records, catalogue=service, art_root=art_root)

        assert service.list_artworks(limit=1).total == WORKS

    def test_running_it_twice_does_not_double_the_catalogue(self, records, service, art_root):
        seed_catalogue(records, catalogue=service, art_root=art_root)
        second = seed_catalogue(records, catalogue=service, art_root=art_root)

        assert service.list_artworks(limit=1).total == WORKS
        assert second.created == []

    def test_no_work_carries_a_source_url_as_its_identity(self, records, service, art_root):
        report = seed_catalogue(records, catalogue=service, art_root=art_root)

        assert not [work for work in report.works if work.url in work.work_id]

    def test_the_collapsed_record_names_the_colour_it_dropped(self, records, service, art_root):
        report = seed_catalogue(records, catalogue=service, art_root=art_root)

        (collapsed,) = counted(report, SeedNote.DUPLICATE_RECORD_DISCARDED)
        (note,) = [entry for entry in collapsed.notes if entry.note is SeedNote.DUPLICATE_RECORD_DISCARDED]
        assert "#433735" in note.detail
        # The last record's colour, #1c1818, is below the floor, so the work
        # arrives with none, and the report says so.
        assert service.current_mat_color(collapsed.work_id) is None
        assert SeedNote.MAT_BELOW_FLOOR in {entry.note for entry in collapsed.notes}


class TestWhatTheReportSays:
    """The gap in the corpus is visible now rather than discovered at the wall."""

    @pytest.fixture
    def report(self, records, service, art_root):
        return seed_catalogue(records, catalogue=service, art_root=art_root)

    def test_it_names_every_work_whose_label_has_no_nationality(self, report):
        assert len(counted(report, SeedNote.NATIONALITY_ABSENT)) == WITHOUT_NATIONALITY

    def test_it_names_every_work_whose_artist_has_no_birth_year(self, report):
        assert len(counted(report, SeedNote.BIRTH_YEAR_ABSENT)) == WITHOUT_BIRTH_YEAR

    def test_it_names_every_work_with_no_medium(self, report):
        assert len(counted(report, SeedNote.MEDIUM_ABSENT)) == WITHOUT_MEDIUM

    def test_it_names_both_works_with_no_physical_dimensions(self, report):
        titles = {work.title for work in counted(report, SeedNote.DIMENSIONS_ABSENT)}
        assert titles == {"Homage to the Square, Sonorous", "Kaldor Public Art Project 10: Jeff Koons 1995"}

    def test_a_dimensionless_work_stores_nothing_rather_than_a_default_size(self, report, service):
        for work in counted(report, SeedNote.DIMENSIONS_ABSENT):
            assert service.get_artwork(work.work_id).artwork.dimensions is None

    def test_it_names_every_work_whose_2024_mat_is_below_the_floor(self, report, records):
        """The owner's floor of 2026-10-03, against the corpus: those colours are
        not carried, and the report is where a person sees which works wait for
        a mat."""
        assert {work.title for work in counted(report, SeedNote.MAT_BELOW_FLOOR)} == _titles_below_the_floor(records)
        assert _titles_below_the_floor(records), "the corpus has mats below the floor, or this test proves nothing"

    def test_a_complete_tree_leaves_no_work_short_of_an_image(self, report):
        assert counted(report, SeedNote.ORIGINAL_FILE_ABSENT) == []


class TestPuttingThemOnTheWall:
    """Seeding is proven by a manifest, which is the only channel to the display plane."""

    @pytest.fixture
    def built(self, records, service, display, art_root, wall_id, decodable_jpeg):
        report = seed_catalogue(records, catalogue=service, art_root=art_root)
        _as_their_first_preparation_would(service, report, art_root, decodable_jpeg)
        theme = display.add_theme(name="Everything")
        for work in report.works:
            display.add_to_theme(theme_id=theme.id, artwork_id=work.work_id)
        return display.build_manifest(wall_id, theme.id)

    def test_entries_and_exclusions_together_account_for_every_work(self, built):
        assert built.considered == WORKS

    def test_a_seeded_work_with_all_four_requirements_reaches_the_wall(self, built):
        assert len(built.entries) == WORKS
        assert built.exclusions == []

    def test_a_work_whose_2024_mat_is_below_the_floor_waits_for_its_first_preparation(
        self, records, service, display, art_root, wall_id, decodable_jpeg
    ):
        """Until preparation chooses it a mat, it is off the wall by name, not on it
        in a mat the owner ruled out."""
        report = seed_catalogue(records, catalogue=service, art_root=art_root)
        _with_masters(service, report, art_root, decodable_jpeg)
        theme = display.add_theme(name="Everything")
        for work in report.works:
            display.add_to_theme(theme_id=theme.id, artwork_id=work.work_id)
        built = display.build_manifest(wall_id, theme.id)

        assert {exclusion.title for exclusion in built.exclusions} == _titles_below_the_floor(records)
        assert {exclusion.reason for exclusion in built.exclusions} == {UnplayableReason.NO_MAT_COLOR}
        assert len(built.entries) == WORKS - len(built.exclusions)

    def test_a_work_with_no_physical_dimensions_still_reaches_it(self, built):
        """Readiness asks for an original, a mat and a current master — never a size in centimetres."""
        titles = {entry.label["title"] for entry in built.entries}
        assert "Homage to the Square, Sonorous" in titles

    def test_a_label_renders_legibly_when_the_artist_is_barely_described(self, built):
        """A partial label is a real outcome here; a label with no title is not."""
        assert all(entry.label["title"] for entry in built.entries)
        (albers,) = [entry for entry in built.entries if entry.label["title"] == "Homage to the Square, Sonorous"]
        assert albers.label["artist"] == "Josef Albers"
        assert albers.label["artist_nationality"] is None
        assert albers.label["artist_dates"] is None

    def test_a_living_artists_label_does_not_read_as_a_missing_death_date(self, built):
        """Rendered from the years alone this would say "1930–", which looks like a fault."""
        johns = [entry for entry in built.entries if entry.label["artist"] == "Jasper Johns"]
        assert johns
        assert all(entry.label["artist_dates"] == "born 1930" for entry in johns)

    def test_the_index_own_parse_is_corrected_on_the_way_in(self, built):
        """The index stored Brancusi's death as 1952; its own details text says 1957."""
        (brancusi,) = [entry for entry in built.entries if entry.label["artist"] == "Constantin Brancusi"]
        assert brancusi.label["artist_dates"] == "1876–1957"

    def test_a_work_the_tree_had_no_master_image_for_is_excluded_by_name(
        self, records, service, display, tmp_path, jpeg, wall_id, decodable_jpeg
    ):
        """The report and the feed's build have to agree about which work is not ready."""
        for record in records[1:]:
            jpeg(tmp_path / record.raw_path, width=6000, height=4000)
        report = seed_catalogue(records, catalogue=service, art_root=tmp_path)
        assert [work.title for work in counted(report, SeedNote.ORIGINAL_FILE_ABSENT)] == [records[0].title]
        held = [work for work in report.works if service.get_original(work.work_id) is not None]
        _as_their_first_preparation_would(service, replace(report, works=held), tmp_path, decodable_jpeg)

        theme = display.add_theme(name="Everything")
        for work in report.works:
            display.add_to_theme(theme_id=theme.id, artwork_id=work.work_id)
        built = display.build_manifest(wall_id, theme.id)

        assert built.considered == WORKS
        assert [(exclusion.title, exclusion.reason) for exclusion in built.exclusions] == [
            (records[0].title, UnplayableReason.NO_ORIGINAL)
        ]
