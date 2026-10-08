"""A work's dimensions as a label sets them: one system, whole units, the first measurement.

**The corpus is every distinct dimensions string in the reference library on
2026-10-08**, read from the server, each checked by hand against what a wall
label should say. It is the shapes museums actually send: centimetres with
inches in brackets, inches first, one system only, millimetres, a comma for a
decimal point, a letter on each value, a qualifier, and several measurements
in one string.
"""

import pytest

from arrt.library.dimensions import Units, for_label
from arrt.library.facade import LibraryFacade
from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.discovery import DiscoveryService
from arrt.persistence.sqlite_discovery import SqliteDiscovery

CORPUS = [
    ("74.8 × 59.7 cm (29 1/2 × 23 1/2 in.)", "30 × 24 in", "75 × 60 cm"),
    ("74.7 × 109.6 cm (29 7/16 × 43 3/16 in.)", "29 × 43 in", "75 × 110 cm"),
    ("w203 x h432 x d127 mm", "w8 × h17 × d5 in", "w20 × h43 × d13 cm"),
    (
        "Image/paper: 19.2 × 24.2 cm (7 9/16 × 9 9/16 in.); Mount: 20.2 × 25.3 cm (8 × 10 in.)",
        "Image/paper: 8 × 10 in",
        "Image/paper: 19 × 24 cm",
    ),
    ("22.9 × 29.8 cm (9 1/16 × 11 3/4 in.)", "9 × 12 in", "23 × 30 cm"),
    (
        "Including frame: 146.4 × 191.1 cm (57 11/16 × 75 1/4 in.); 146.4 × 191.2 cm (57 5/8 × 75 1/4 in.)",
        "Including frame: 58 × 75 in",
        "Including frame: 146 × 191 cm",
    ),
    ("91.4 × 61 cm (36 × 24 in.)", "36 × 24 in", "91 × 61 cm"),
    ("52.4 × 23.5 cm (20 5/8 × 9 1/4 in.)", "21 × 9 in", "52 × 24 cm"),
    ("30.4 × 45.9 cm (12 × 18 1/8 in.)", "12 × 18 in", "30 × 46 cm"),
    ("28 x 28 cm", "11 × 11 in", "28 × 28 cm"),
    ("217.8 × 29.9 × 29.9 cm (86 × 11 3/4 × 11 3/4 in.)", "86 × 12 × 12 in", "218 × 30 × 30 cm"),
    ("H.: 21 cm (8 1/4 in.)", "H.: 8 in", "H.: 21 cm"),
    ("60 × 75.2 cm (23 5/8 × 29 5/8 in.)", "24 × 30 in", "60 × 75 cm"),
    ("76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)", "30 × 38 in", "77 × 97 cm"),
    ("68 x 68 cm", "27 × 27 in", "68 × 68 cm"),
    ("H.: 22.1 cm (8 11/16 in.)", "H.: 9 in", "H.: 22 cm"),
    ("132.8 × 120 cm (52 1/4 × 47 1/4 in.); Repeat: 84.2 × 39.6 cm (33 1/8 × 15 3/8 in.)", "52 × 47 in", "133 × 120 cm"),
    ("78.8 × 100.4 cm (31 × 39 1/2 in.)", "31 × 40 in", "79 × 100 cm"),
    ("60 × 60 cm (23 5/8 × 23 5/8 in.)", "24 × 24 in", "60 × 60 cm"),
    ("40 x 30,2 cm", "16 × 12 in", "40 × 30 cm"),
    ("195.6 × 254 cm (77 × 100 in.)", "77 × 100 in", "196 × 254 cm"),
    ("108.9 × 118.4 cm (43 1/4 × 47 1/2 in.)", "43 × 48 in", "109 × 118 cm"),
    ("h53 x w44.5 in", "h53 × w45 in", "h135 × w113 cm"),
    ("93.3 × 74.4 cm (36 3/4 × 29 5/16 in.)", "37 × 29 in", "93 × 74 cm"),
    ("99.1 × 350.2 cm (39 × 138 in.)", "39 × 138 in", "99 × 350 cm"),
    ("72.6 × 91.6 cm (28 1/2 × 36 in.)", "29 × 36 in", "73 × 92 cm"),
    ("55.3 × 74.9 cm (21 3/4 × 29 1/2 in.)", "22 × 30 in", "55 × 75 cm"),
    ("243.8 × 731.5 cm (96 × 288 in.)", "96 × 288 in", "244 × 732 cm"),
    ("46.1 × 70.5 cm (18 1/8 × 27 3/4 in.)", "18 × 28 in", "46 × 71 cm"),
    ("167.6 × 167.6 cm (66 × 66 in.)", "66 × 66 in", "168 × 168 cm"),
    ("97.3 × 130.3 cm (38 1/4 × 51 1/4 in.)", "38 × 51 in", "97 × 130 cm"),
    ("248 × 194.9 cm (97 5/8 × 76 3/4 in.)", "98 × 77 in", "248 × 195 cm"),
    ("111.8 × 111.8 cm (44 × 44 in.)", "44 × 44 in", "112 × 112 cm"),
    (
        "Center panel: 35 1/4 × 43 in. (89.5 × 109.2 cm)\nTwo side panels: 36 × 7 3/4 in. (91.4 × 19.7 cm) (each)",
        "Center panel: 35 × 43 in",
        "Center panel: 90 × 109 cm",
    ),
    ("18.1 × 14.1 cm (7 1/8 × 5 7/16 in.)", "7 × 5 in", "18 × 14 cm"),
    (
        "Unframed: 265.1 × 298.1 cm (104 3/8 × 117 3/8 in.); 265.2 × 298.2 cm (104 3/8 × 117 3/8 in.)",
        "Unframed: 104 × 117 in",
        "Unframed: 265 × 298 cm",
    ),
    (
        "Unframed: 197.5 × 207.7 cm (77 13/16 × 81 13/16 in.); 197.5 × 207.7 cm (77 3/4 × 81 3/4 in.)",
        "Unframed: 78 × 82 in",
        "Unframed: 198 × 208 cm",
    ),
    ("33.4 × 56.3 cm (13 1/8 × 22 1/8 in.); Framed: 62.3 × 84.2 cm (24 1/2 × 33 1/8 in.)", "13 × 22 in", "33 × 56 cm"),
]


@pytest.mark.parametrize(("source", "imperial", "metric"), CORPUS, ids=[row[0][:40] for row in CORPUS])
def test_a_label_states_one_system_rounded_to_whole_units(source, imperial, metric):
    assert for_label(source, Units.IMPERIAL) == imperial
    assert for_label(source, Units.METRIC) == metric


def test_the_owners_example_reads_as_asked():
    """The request that made this: "not 30 1/8 x 38 1/4 in, just 30 x 38 in"."""
    assert for_label("76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)", Units.IMPERIAL) == "30 × 38 in"


def test_a_half_rounds_up_rather_than_to_the_even_number():
    """Python's `round` sends 28.5 to 28; a label states 29."""
    assert for_label("28 1/2 × 30 1/2 in.", Units.IMPERIAL) == "29 × 31 in"


def test_the_sources_own_figures_win_over_a_conversion():
    """When both systems are stated, the asked-for one is read, not converted from
    the other: the source measured it, and the two disagree by a rounding."""
    assert for_label("10 × 10 cm (5 × 5 in.)", Units.IMPERIAL) == "5 × 5 in"


def test_a_value_under_one_unit_keeps_a_decimal_rather_than_stating_nothing():
    assert for_label("0.8 × 12 cm", Units.IMPERIAL) == "0.3 × 5 in"


@pytest.mark.parametrize("source", ["irregular", "dimensions variable", "Sheet: various", ""])
def test_a_string_with_no_measurement_is_left_as_the_source_wrote_it(source):
    assert for_label(source, Units.IMPERIAL) == source


def test_no_dimensions_stay_none():
    assert for_label(None, Units.METRIC) is None


@pytest.mark.parametrize(
    ("source", "imperial"),
    [
        # A fraction alone was read as two numbers, "13 × 16 in".
        ("H.: 2 cm (13/16 in.)", "H.: 0.8 in"),
        # The "h" ending "Width" was taken for a dimension letter.
        ("Width 30 cm", "Width 12 in"),
        # The Met's height with no colon kept its "H." only by luck of a colon.
        ("H. 8 1/4 in. (21 cm)", "H. 8 in"),
        # A non-breaking space between a whole number and its fraction, as text
        # taken from a web page carries; it matched and then failed to parse.
        ("74.7 × 109.6 cm (29\u00a07/16 × 43\u00a03/16 in.)", "29 × 43 in"),
    ],
)
def test_words_and_fractions_around_a_measurement_are_read_as_written(source, imperial):
    assert for_label(source, Units.IMPERIAL) == imperial


@pytest.mark.parametrize(
    "source",
    [
        # Two measurements in one system: converting the first would drop the 40.
        "30 cm × 40 cm",
        # A figure outside any measurement: "Sheet 3" is not a dimension.
        "Sheet 3: 10 × 12 cm",
    ],
)
def test_a_part_not_wholly_read_is_left_as_the_source_wrote_it(source):
    assert for_label(source, Units.IMPERIAL) == source


def test_a_value_too_small_to_state_is_never_stated_as_nothing():
    assert for_label("0.01 × 5 cm", Units.IMPERIAL) == "0.1 × 2 in"


@pytest.mark.parametrize(("units", "stated"), [(Units.METRIC, "77 × 97 cm"), (Units.IMPERIAL, "30 × 38 in")])
def test_the_label_a_wall_is_given_states_the_deployments_units(store, units, stated):
    """Through the facade Programming reads a label from, so a `label_of` that
    stopped converting would show here and not only in the parser's tests."""
    catalogue = CatalogueService(store)
    facade = LibraryFacade(catalogue, DiscoveryService(SqliteDiscovery(store._store), catalogue), label_units=units)
    work = catalogue.add_artwork(title="Nighthawks", dimensions="76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)")

    assert facade.labels([work.id])[work.id]["dimensions"] == stated
    assert (
        catalogue.get_artwork(work.id).artwork.dimensions == "76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)"
    ), "the stored string changed"
