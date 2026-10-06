"""Run 1's finds from the procurement corpus, found again through the loaded plugins.

`procurement-corpus.md` § Results records what the first Get found before sources
were plugins: four works from Commons and two from the Art Institute, each at a
size. Loading those sources as plugins must not change what they find, so this
asks the same questions (the titles and artists run 1 proposed, read from that
run's rows) through plugins loaded from the installed entry points, and expects
the same source at the same size. A size moving means the holder replaced its
file, which is worth knowing too.

**Deselected by default** and free: Commons, Wikidata and the Art Institute are
unmetered. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_corpus_finds_through_the_plugins.py
"""

import pytest

from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.sources import FoundImage, ImageQuery, ItemId, SourceContext
from arrt.library.sources.loading import PluginState, load_sources

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: Corpus row, the item, run 1's proposed title and artist, and what it found.
RUN_1_FINDS = [
    (1, "Q19861807", "Windows Open Simultaneously (First Part, Second Motif)", "Robert Delaunay", "commons", 3168, 3564),
    (2, "Q19861802", "Hommage to Blériot", "Robert Delaunay", "commons", 3840, 3805),
    (3, "Q18927491", "Rythme n°1, décoration pour le Salon des Tuileries", "Robert Delaunay", "commons", 2985, 2715),
    (9, "Q124646012", "City at Night", "Aleksandra Ekster", "commons", 952, 1200),
    (19, "Q20268302", "In the Third Sleep", "Kay Sage", "artic", 8786, 5798),
    (35, "Q16155640", "Crak!", "Roy Lichtenstein", "artic", 11073, 7794),
]


@pytest.fixture(scope="module")
def roster():
    registry = WikidataRegistry(user_agent=USER_AGENT)
    loaded = load_sources(
        SourceContext(
            environ={"ARTIC_USER_AGENT": USER_AGENT, "WIKIDATA_USER_AGENT": USER_AGENT},
            user_agent=USER_AGENT,
            preview_max_bytes=16 * 1024 * 1024,
            registry=registry,
        )
    )
    yield loaded
    registry.close()


def test_the_built_in_plugins_load_from_their_entry_points(roster):
    states = {reading.name: reading.state for reading in roster.observe()}

    assert states == {
        "commons": PluginState.LOADED,
        "artic": PluginState.LOADED,
        "met": PluginState.LOADED,
        "wikidata": PluginState.LOADED,
    }


@pytest.mark.parametrize(
    ("row", "qid", "title", "artist", "provider", "width", "height"), RUN_1_FINDS, ids=[f"row {row[0]}" for row in RUN_1_FINDS]
)
def test_run_1_s_find_comes_back_from_the_same_source_at_the_same_size(roster, row, qid, title, artist, provider, width, height):
    finder = next(finder for finder in roster.finders if finder.provider == provider)

    found = finder.find_images(ImageQuery(title=title, artist=artist, qid=ItemId(qid)))

    sizes = [(image.estimated_width, image.estimated_height) for image in found if isinstance(image, FoundImage)]
    assert (width, height) in sizes, f"row {row}: {provider} answered {sizes}"
