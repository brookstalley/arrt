"""The creator names the identity check leans on, as a test rather than as prose.

`artist-name-identity-findings.md` measured holders naming an artist in a form
the Library's label does not key to. Wikidata records the holder's form as a
label or an alias of the same person. On a page the work's item records, phase 2
accepts the image for that reason. Anyone can edit an alias, so these pin the
measured cases, one per shape, against the live service:

- a full name against initials (Art UK's Lowry and Turner);
- a fuller name (NGA's Rembrandt);
- another language's form (the Pompidou's Kandinsky);
- a mononym (the Pompidou's Kisling).

**Deselected by default** and free: a handful of queries. Run deliberately, one
process:

    uv run pytest -m live_museum -n0 tests/live/test_wikidata_creator_names_are_still_real.py
"""

import pytest

from arrt.library.discovery.dedup import artist_key
from arrt.library.discovery.images import FoundImage, ImageQuery
from arrt.library.discovery.phase_two import CONFIDENT, PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry.wikidata import WikidataRegistry
from arrt.library.services.display_fit import ArtworkBox
from arrt.persistence.records import AcquisitionMethod, SourceClass

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"

#: (work, the Library's artist as Wikidata labels them, the holder's name), each measured 2026-10-06.
CASES = [
    ("Q119294634", "L. S. Lowry", "Laurence Stephen Lowry"),
    ("Q257580", "J. M. W. Turner", "Joseph Mallord William Turner"),
    ("Q219831", "Rembrandt", "Rembrandt van Rijn"),
    ("Q112684840", "Wassily Kandinsky", "Vassily Kandinsky"),
    ("Q135874124", "Moïse Kisling", "Kisling"),
]

#: Lowry's *Portrait of a House*, whose item records its Art UK page through P1679.
LOWRY_WORK = "Q119294634"
ARTUK_PAGE = "https://artuk.org/discover/artworks/portrait-of-a-house-162388"


@pytest.fixture(scope="module")
def registry():
    opened = WikidataRegistry(user_agent=USER_AGENT)
    yield opened
    opened.close()


@pytest.mark.parametrize(("work", "label", "holder"), CASES, ids=[case[2] for case in CASES])
def test_both_names_are_still_one_creators(registry, work, label, holder):
    names = registry.creator_names(work)

    assert names, f"{work} has no recorded creator with a name"
    keyed = [{artist_key(name) for name in written} for written in names.values()]
    assert any(
        artist_key(label) in keys and artist_key(holder) in keys for keys in keyed
    ), f"no creator of {work} carries both {label!r} and {holder!r}"


class ArtUkPage:
    """A source holding Art UK's record of the Lowry under Art UK's own name for him."""

    provider = "artuk"

    def find_images(self, query: ImageQuery):
        return (
            FoundImage(
                url=ARTUK_PAGE,
                provider="artuk",
                source_class=SourceClass.INSTITUTIONAL,
                acquisition_method=AcquisitionMethod.DIRECT_HTTP,
                title="Portrait of a House",
                artist="Laurence Stephen Lowry",
                estimated_width=3000,
                estimated_height=2400,
            ),
        )

    def fetch_preview(self, url: str):
        return None


def test_the_lowry_art_uk_holds_is_accepted_through_the_live_registry(registry):
    box = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.9, floor_inches=12.0)
    engine = PhaseTwoEngine(ImageSourcePool([ArtUkPage()]), box=box, registry=registry)

    (entry,) = engine.resolve(ImageQuery(title="Portrait of a House", artist="L. S. Lowry", qid=LOWRY_WORK)).instances

    assert entry.confidence == CONFIDENT
    assert "under another name Wikidata records for them" in entry.rationale
