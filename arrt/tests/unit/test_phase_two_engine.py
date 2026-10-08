"""Which of a museum's results is actually the work that was asked for.

The case this exists for is the one the live API produced: asking the Art
Institute for *The Persistence of Memory* — which it does not hold, MoMA does —
returns *Ann-In Memory* by Joseph Cornell at a comfortable relevance score. Any
scheme that ranks by the provider's own number attaches that to the request and
reports success, with nothing anywhere saying a different painting was
substituted.

So the tests below are mostly about refusal: what must *not* come back, and the
`unresolved` outcome that must come back instead.
"""

import logging

import pytest
from fakes import FakeRegistry

from arrt.library.discovery.images import FoundImage, ImageQuery, ImageSearchFailure
from arrt.library.discovery.phase_two import CONFIDENT, TITLE_ONLY, UNATTRIBUTED_RECORD, JudgedImage, PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry import RegistryUnavailable
from arrt.library.services.display_fit import ArtworkBox, DisplayFit
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

#: A 42" panel, as `Settings.tv_artwork_box` composes it — a fixed geometry chosen
#: so the numbers below are checkable, NOT the operator's set, which is 50". A
#: 12-inch floor sits at about 1,260 pixels on the long edge here.
BOX = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.9, floor_inches=12.0)


def an_instance(title: str, *, artist: str | None = None, width: int = 6949, height: int = 8400, **kwargs) -> FoundImage:
    return FoundImage(
        url=f"https://api.artic.edu/api/v1/artworks/{abs(hash(title)) % 10000}",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        title=title,
        artist=artist,
        preview_url="https://www.artic.edu/iiif/2/x/full/843,/0/default.jpg",
        estimated_width=width,
        estimated_height=height,
        **kwargs,
    )


class StubSearch:
    """A provider that answers with what it was built to answer."""

    def __init__(self, *instances: FoundImage, fails: bool = False) -> None:
        self._instances = instances
        self._fails = fails

    @property
    def provider(self) -> str:
        return "artic"

    def find_images(self, query: ImageQuery):
        if self._fails:
            raise ImageSearchFailure("the museum could not be reached")
        return self._instances

    def fetch_preview(self, url: str) -> bytes | None:
        return b"jpeg"


def resolve(*instances: FoundImage, title: str, artist: str | None = None):
    """The instances that survived, which is what most of this module is about.

    Tests that care *why* the rest did not survive call `refusals` below; keeping
    them separate means a test asserting on the surviving list cannot pass by
    accidentally reading a refusal set that happens to be empty.
    """
    return (
        PhaseTwoEngine(ImageSourcePool([StubSearch(*instances)]), box=BOX)
        .resolve(ImageQuery(title=title, artist=artist))
        .instances
    )


def refusals(*instances: FoundImage, title: str, artist: str | None = None) -> frozenset[UnresolvedReason]:
    """Which gates turned results away for this work."""
    return (
        PhaseTwoEngine(ImageSourcePool([StubSearch(*instances)]), box=BOX)
        .resolve(ImageQuery(title=title, artist=artist))
        .refusals
    )


# -- the near-match, which is the whole point -----------------------------------


def test_a_real_work_by_a_real_artist_is_refused_when_it_is_not_the_work_asked_for():
    """The measured case: the museum does not hold this painting and says so by omission.

    Every candidate here scored well against the live query. None is the
    requested work, and the correct answer is nothing at all — because an empty
    result makes the work `unresolved` for the one reason that carries the
    invented-work signal, `NOT_HELD`, and a low-confidence near-match launders
    exactly that signal away. Scoped to this case on purpose: the other routes to
    `unresolved` say the collection *has* the work, which is nearly the opposite.
    """
    judged = resolve(
        an_instance("Ann-In Memory", artist="Joseph Cornell"),
        an_instance("In Memory of My Father", artist="Sylvia Plimack Mangold"),
        an_instance("A Memory", artist="Gene Charlton"),
        title="The Persistence of Memory",
        artist="Salvador Dalí",
    )

    assert judged == []


def test_the_same_title_by_a_different_painter_is_refused_rather_than_scored_lower():
    """A deduction still selects the wrong one whenever the right one is absent.

    The collection really does hold two *American Gothic*s, so this is not a
    hypothetical: a scheme that merely ranked Grant Wood above Elizabeth Layton
    would attach hers to a request for his the moment his was missing.
    """
    judged = resolve(an_instance("American Gothic", artist="Elizabeth Layton"), title="American Gothic", artist="Grant Wood")

    assert judged == []


# -- which gate refused, which is what an empty result has to be able to say ----
#
# An empty judgement is the same object however it was arrived at, so the reason
# has to be carried out of here or it is gone: the discarded results never become
# rows, and nothing downstream can reconstruct why they were discarded.


def test_a_collection_holding_no_such_title_reports_not_held():
    """The invented-work signal, and the only refusal that carries it."""
    refused = refusals(
        an_instance("Ann-In Memory", artist="Joseph Cornell"),
        title="The Persistence of Memory",
        artist="Salvador Dalí",
    )

    assert refused == {UnresolvedReason.NOT_HELD}


def test_a_collection_holding_the_title_under_another_painter_reports_identity_refused():
    """Nearly the opposite of `not_held`: the collection has it, under another name."""
    refused = refusals(an_instance("American Gothic", artist="Elizabeth Layton"), title="American Gothic", artist="Grant Wood")

    assert refused == {UnresolvedReason.IDENTITY_REFUSED}


def test_a_matching_record_the_provider_could_not_size_reports_size_unknown():
    sizeless = an_instance("American Gothic", artist="Grant Wood", width=None, height=None)

    refused = refusals(sizeless, title="American Gothic", artist="Grant Wood")

    assert refused == {UnresolvedReason.SIZE_UNKNOWN}


def test_the_two_ways_a_result_can_fail_identity_are_reported_apart():
    """The distinction the whole column exists for, in one search.

    A single query returns both a different painting and the right title under
    the wrong painter. Reporting one label for the pair would answer "the museum
    does not have it" about a museum that demonstrably does.
    """
    refused = refusals(
        an_instance("A Memory", artist="Gene Charlton"),
        an_instance("American Gothic", artist="Elizabeth Layton"),
        title="American Gothic",
        artist="Grant Wood",
    )

    assert refused == {UnresolvedReason.NOT_HELD, UnresolvedReason.IDENTITY_REFUSED}


def test_a_provider_that_returns_nothing_at_all_refuses_nothing():
    """No record came back to refuse, which downstream reads as `not_held` — vacuously true.

    Asserted here rather than left implicit because an empty refusal set and a
    `not_held` refusal are different objects that mean the same thing, and a
    derivation that defaulted the other way would call an empty search a
    disagreement about an artist nobody named.
    """
    assert refusals(title="American Gothic", artist="Grant Wood") == frozenset()


def test_a_work_that_resolves_cleanly_refuses_nothing():
    """An assertion that would pass on an always-empty set is worth nothing, so this pins the other side."""
    held = an_instance("American Gothic", artist="Grant Wood")

    assert refusals(held, title="American Gothic", artist="Grant Wood") == frozenset()


def test_the_engine_never_reports_a_reason_that_is_read_from_stored_rows():
    """The engine's vocabulary is the shallow gates only, and the depth ranking relies on it.

    `BELOW_FLOOR` and `ALL_REJECTED` share a depth, which is safe precisely
    because they are derived where the rows are and can never appear in a
    refusal set to be ranked against each other. Nothing else states that, so an
    engine that started emitting one would introduce a silent tie broken by set
    iteration order — a wrong label on a work, chosen by nothing.

    Written as a set difference rather than as a list of the three it may emit,
    so a sixth member added to the enum is covered by the rule instead of missed
    by an inventory taken today.
    """
    from_rows = {UnresolvedReason.BELOW_FLOOR, UnresolvedReason.ALL_REJECTED}
    emitted = refusals(
        an_instance("A Memory", artist="Gene Charlton"),
        an_instance("American Gothic", artist="Elizabeth Layton"),
        an_instance("American Gothic", artist="Grant Wood", width=None, height=None),
        an_instance("Small Study", artist="Grant Wood", width=300, height=200),
        title="American Gothic",
        artist="Grant Wood",
    )

    assert emitted & from_rows == set(), "the engine emitted a reason only the store may derive"
    assert emitted, "the fixture refused nothing, so this would pass with the check removed"


def test_the_right_painter_is_kept_when_both_are_offered():
    judged = resolve(
        an_instance("American Gothic", artist="Elizabeth Layton"),
        an_instance("American Gothic", artist="Grant Wood"),
        title="American Gothic",
        artist="Grant Wood",
    )

    assert [entry.found.artist for entry in judged] == ["Grant Wood"]
    assert judged[0].confidence == CONFIDENT


# -- identity, derived from the module that already owns it ---------------------


@pytest.mark.parametrize(
    ("asked", "held"),
    [
        ("The Persistence of Memory", "The Persistence of Memory (1931)"),
        ("Coquelicots", "Coquelicots (The Poppies)"),
        ("Nighthawks", "nighthawks"),
        ("Dalí's Study", "Dali's Study"),
    ],
)
def test_cataloguing_variation_in_a_title_is_not_a_different_work(asked, held):
    """Normalisation comes from `dedup`, so this agrees with the dedup key by construction.

    A second normalisation written here would be free to drift from the one the
    persisted identity is built with, and the two disagreeing is how one painting
    becomes two rows.
    """
    judged = resolve(an_instance(held, artist="Someone"), title=asked, artist="Someone")

    assert len(judged) == 1


@pytest.mark.parametrize(
    ("asked_artist", "held_artist", "expected"),
    [
        ("Grant Wood", "Grant Wood", CONFIDENT),
        ("El Greco", "El Greco (Domenikos Theotokopoulos)", CONFIDENT),
        (None, "Grant Wood", TITLE_ONLY),
        ("Grant Wood", None, UNATTRIBUTED_RECORD),
    ],
)
def test_confidence_reflects_how_much_of_the_identity_was_confirmable(asked_artist, held_artist, expected):
    """Three tiers, because a title alone is a weaker identity than a title and a painter."""
    judged = resolve(an_instance("American Gothic", artist=held_artist), title="American Gothic", artist=asked_artist)

    assert judged[0].confidence == expected


def test_confidence_never_reaches_certainty():
    """This is a textual identity match, not an inspection of the picture.

    Reserving the top of the range leaves somewhere for a provider that can
    actually verify the image to go, and stops a strong-but-textual match from
    reading as proof.
    """
    judged = resolve(an_instance("American Gothic", artist="Grant Wood"), title="American Gothic", artist="Grant Wood")

    assert 0 < judged[0].confidence < 1.0


# -- the floor ------------------------------------------------------------------


def test_a_below_floor_instance_is_kept_and_labelled_rather_than_hidden():
    """Not a rejection: shown, sized, and selectable by a curator who wants it."""
    judged = resolve(an_instance("Small Study", artist="Someone", width=600, height=400), title="Small Study", artist="Someone")

    assert len(judged) == 1
    assert judged[0].below_floor is True
    assert judged[0].fit.fit is DisplayFit.BELOW_FLOOR
    assert "too small to reach this wall's size floor" in judged[0].rationale
    assert "not selected automatically" in judged[0].rationale


@pytest.mark.parametrize(
    ("width", "height", "said"),
    [
        pytest.param(600, 400, "too small to reach this wall's size floor", id="below the floor"),
        pytest.param(2000, 1500, "matted wider rather than downscaled", id="matted small"),
        pytest.param(6000, 4000, "enough to fill the artwork box", id="native"),
    ],
)
def test_the_selection_sentence_names_the_scan_s_pixels_and_no_inches(width, height, said):
    """The owner's ruling, 2026-10-02: the scan's size in pixels, and no inches.

    This replaced an assertion that the sentence carried the rendered size in
    inches. Inches are the long edge on the one panel this server is configured
    for, after the mat, and beside a picture they read as a fact about the
    picture; the number a curator judging a below-floor scan needs is still in
    the sentence, as the scan's pixels. Every verdict, because each has its own
    clause and any of them could carry a unit back in.
    """
    judged = resolve(an_instance("Study", artist="Someone", width=width, height=height), title="Study", artist="Someone")

    sentence = judged[0].rationale
    assert f"{width:,} × {height:,} px" in sentence
    assert said in sentence
    assert "inch" not in sentence
    assert "″" not in sentence


def test_below_floor_instances_sort_behind_every_instance_that_clears_it():
    """Ordering is what makes the first-recorded instance the one that gets selected."""
    judged = resolve(
        an_instance("Study", artist="Someone", width=600, height=400),
        an_instance("Study", artist="Someone", width=6000, height=4000),
        title="Study",
        artist="Someone",
    )

    assert [entry.below_floor for entry in judged] == [False, True]


def test_a_bigger_scan_of_the_same_work_outranks_a_smaller_one():
    """Quality breaks ties between instances that are equally, credibly the work."""
    judged = resolve(
        an_instance("Nighthawks", artist="Edward Hopper", width=1600, height=1200),
        an_instance("Nighthawks", artist="Edward Hopper", width=6000, height=4500),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert judged[0].found.estimated_width == 6000
    assert judged[0].quality_score > judged[1].quality_score


def test_a_tall_master_with_resolution_to_spare_outranks_a_smaller_one_that_suits_the_shape():
    """Aspect ratio must not be read as resolution — the requirement says so outright.

    The artwork box is much wider than it is tall, so a 6949x8400 portrait is
    limited by the box's height and renders *shorter* on the wall than a
    2000x1500 landscape that happens to fit the shape. It nonetheless has four
    times the resolution to spare, and it is the better file: canvas occupancy is
    dominated by aspect-ratio mismatch, and what isolates resolution is whether
    the render is a downscale or a native-size paste.

    An earlier ranking here used rendered inches and preferred the smaller file.
    """
    portrait = an_instance("Study", artist="Someone", width=6949, height=8400)
    landscape = an_instance("Study", artist="Someone", width=2000, height=1500)

    judged = resolve(landscape, portrait, title="Study", artist="Someone")

    assert judged[0].found is portrait
    # And the reason is visible in the verdict, not only in the ordering.
    assert judged[0].fit.fit is DisplayFit.NATIVE
    assert judged[1].fit.fit is DisplayFit.MATTED_SMALL
    assert judged[1].fit.rendered_long_edge_inches > judged[0].fit.rendered_long_edge_inches


def test_quality_never_overturns_confidence():
    """A gorgeous scan of the wrong painting is worse than a modest scan of the right one.

    Both survive the identity check here — the request names no artist, so a
    record naming one and a record naming none are both credible — and the
    weaker identity must still lose despite being the larger file.
    """
    judged = resolve(
        an_instance("Nighthawks", artist=None, width=9000, height=7000),
        an_instance("Nighthawks", artist="Edward Hopper", width=1400, height=1100),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert judged[0].found.artist == "Edward Hopper"
    assert judged[0].quality_score < judged[1].quality_score


def test_an_instance_the_provider_could_not_size_is_dropped():
    """One recorded without dimensions is indistinguishable from one that clears the floor."""
    judged = resolve(
        FoundImage(
            url="https://example.org/1",
            provider="somewhere",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            title="Nighthawks",
            artist="Edward Hopper",
        ),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert judged == []


# -- rights, which inform quality without gating anything -----------------------


def test_rights_break_a_tie_between_otherwise_identical_instances():
    """An institution's own public-domain scan is usually the authoritative file."""
    judged = resolve(
        an_instance("Nighthawks", artist="Edward Hopper", rights_status=RightsStatus.IN_COPYRIGHT),
        an_instance("Nighthawks", artist="Edward Hopper", rights_status=RightsStatus.PUBLIC_DOMAIN),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert judged[0].found.rights_status is RightsStatus.PUBLIC_DOMAIN


def test_rights_never_exclude_an_instance_and_never_beat_resolution():
    """Constraint 13: rights gate nothing. An in-copyright larger scan still wins."""
    judged = resolve(
        an_instance("Nighthawks", artist="Edward Hopper", width=1400, height=1100, rights_status=RightsStatus.PUBLIC_DOMAIN),
        an_instance("Nighthawks", artist="Edward Hopper", width=8000, height=6000, rights_status=RightsStatus.IN_COPYRIGHT),
        title="Nighthawks",
        artist="Edward Hopper",
    )

    assert len(judged) == 2, "nothing is excluded on rights"
    assert judged[0].found.rights_status is RightsStatus.IN_COPYRIGHT


# -- failure is not the same as finding nothing ---------------------------------


def test_a_provider_that_cannot_be_reached_raises_rather_than_answering_empty():
    """Empty means "your painting is not in this collection"; that is a different claim."""
    engine = PhaseTwoEngine(ImageSourcePool([StubSearch(fails=True)]), box=BOX)

    with pytest.raises(ImageSearchFailure):
        engine.resolve(ImageQuery(title="Nighthawks"))


def test_a_rationale_names_the_museums_own_title_so_a_substitution_would_be_visible():
    """The card says what the provider calls it, which is how a curator catches a wrong match."""
    judged = resolve(
        an_instance("American Gothic (1930)", artist="Grant Wood"),
        title="American Gothic",
        artist="Grant Wood",
    )

    assert "American Gothic (1930)" in judged[0].rationale
    assert "Grant Wood" in judged[0].rationale


# -- a page the work's Wikidata item records ------------------------------------
#
# MoMA holds Taeuber-Arp's *Composition of Circles and Overlapping Angles* as
# *Composition*. A shorter title alone would match every Composition she made, so
# what identifies the record is the work's item recording its page.

MOMA_PAGE = "https://www.moma.org/collection/works/37346"
LONG_TITLE = "Composition of Circles and Overlapping Angles"


def a_moma_page(title: str = "Composition", *, artist: str | None = "Sophie Taeuber-Arp", url: str = MOMA_PAGE) -> FoundImage:
    return FoundImage(
        url=url,
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        title=title,
        artist=artist,
        estimated_width=2000,
        estimated_height=1992,
    )


def linked_resolution(*instances: FoundImage, registry, qid: str | None = "Q19884054", artist: str | None = "Sophie Taeuber-Arp"):
    return PhaseTwoEngine(ImageSourcePool([StubSearch(*instances)]), box=BOX, registry=registry).resolve(
        ImageQuery(title=LONG_TITLE, artist=artist, qid=qid)
    )


def test_a_page_the_works_item_records_is_the_work_under_its_holders_title():
    """The case run 3 refused: the right record, under MoMA's shorter title."""
    resolution = linked_resolution(a_moma_page(), registry=FakeRegistry(pages={"Q19884054": [MOMA_PAGE]}))

    assert [entry.found.url for entry in resolution.instances] == [MOMA_PAGE]
    assert resolution.instances[0].confidence == CONFIDENT
    assert resolution.refusals == frozenset()


def test_the_card_says_the_title_differs_and_what_identified_it():
    """A curator reading "Composition" on a card for a longer title needs the reason it is there."""
    rationale = linked_resolution(a_moma_page(), registry=FakeRegistry(pages={"Q19884054": [MOMA_PAGE]})).instances[0].rationale

    assert "'Composition'" in rationale
    assert "Wikidata item records" in rationale
    assert "matching the requested title" not in rationale


def test_a_page_the_works_item_does_not_record_is_refused_on_its_title():
    """Another *Composition* page, which the item does not name, is one of the others."""
    registry = FakeRegistry(pages={"Q19884054": [MOMA_PAGE]})
    resolution = linked_resolution(a_moma_page(url="https://www.moma.org/collection/works/99999"), registry=registry)

    assert resolution.instances == []
    assert resolution.refusals == frozenset({UnresolvedReason.NOT_HELD})


def test_a_recorded_page_by_another_artist_is_still_refused():
    """The link settles the title, not the artist: an item recording a page whose
    record names somebody else is a disagreement to refuse, not to resolve."""
    resolution = linked_resolution(a_moma_page(artist="Jean Arp"), registry=FakeRegistry(pages={"Q19884054": [MOMA_PAGE]}))

    assert resolution.instances == []
    assert resolution.refusals == frozenset({UnresolvedReason.IDENTITY_REFUSED})


def test_a_page_the_item_spells_differently_fails_closed():
    """Matched exactly, as the item spells it: a guess at which spellings are one
    address would be a second identity rule, and refusing is the direction a later
    search can undo."""
    resolution = linked_resolution(
        a_moma_page(url="https://moma.org/collection/works/37346"), registry=FakeRegistry(pages={"Q19884054": [MOMA_PAGE]})
    )

    assert resolution.instances == []


def test_a_work_with_no_item_never_asks_the_registry():
    registry = FakeRegistry(pages={"Q19884054": [MOMA_PAGE]})

    resolution = linked_resolution(a_moma_page(), registry=registry, qid=None)

    assert resolution.instances == []
    assert registry.pages_asked == []


def test_a_work_whose_titles_all_match_never_asks_the_registry():
    registry = FakeRegistry(pages={"Q19884054": [MOMA_PAGE]})

    resolution = linked_resolution(a_moma_page(LONG_TITLE), registry=registry)

    assert len(resolution.instances) == 1
    assert registry.pages_asked == []


def test_the_registry_is_asked_once_however_many_titles_differ():
    """One question per work, not per result: a search answering a page of near-matches
    would otherwise ask Wikidata once for each."""
    registry = FakeRegistry(pages={"Q19884054": [MOMA_PAGE]})

    linked_resolution(
        a_moma_page(),
        a_moma_page("Composition with Lines", url="https://www.moma.org/collection/works/2"),
        a_moma_page("Untitled", url="https://www.moma.org/collection/works/3"),
        registry=registry,
    )

    assert registry.pages_asked == ["Q19884054"]


def test_a_registry_that_cannot_be_asked_leaves_the_titles_to_decide(caplog):
    """No link is not a fault in the run: the work is refused on its title, as
    before there was a link, and the reason is logged where it can be read."""
    with caplog.at_level(logging.WARNING):
        resolution = linked_resolution(a_moma_page(), registry=FakeRegistry(failing=True))

    assert resolution.instances == []
    assert resolution.refusals == frozenset({UnresolvedReason.NOT_HELD})
    assert [getattr(record, "event", None) for record in caplog.records] == ["phase_two.link_unavailable"]


def test_with_no_registry_only_the_title_identifies_a_work():
    resolution = linked_resolution(a_moma_page(), registry=None)

    assert resolution.instances == []


@pytest.mark.parametrize(
    ("asked_artist", "held_artist", "confidence", "said"),
    [
        ("Sophie Taeuber-Arp", "Sophie Taeuber-Arp", CONFIDENT, ", by the requested artist"),
        (None, "Sophie Taeuber-Arp", TITLE_ONLY, "; the request named no artist"),
        ("Sophie Taeuber-Arp", None, UNATTRIBUTED_RECORD, "; the record names no artist to confirm it"),
    ],
)
def test_a_linked_record_is_kept_at_the_confidence_its_artists_allow(asked_artist, held_artist, confidence, said):
    """The link settles the title only, so the artist tiers decide as they do for a
    matching title, and the card says which half confirmed it."""
    (entry,) = linked_resolution(
        a_moma_page(artist=held_artist), registry=FakeRegistry(pages={"Q19884054": [MOMA_PAGE]}), artist=asked_artist
    ).instances

    assert entry.confidence == confidence
    assert said in entry.rationale


@pytest.mark.parametrize(
    ("registry", "qid", "url", "link"),
    [
        (None, "Q19884054", MOMA_PAGE, "no_registry"),
        (FakeRegistry(pages={"Q19884054": [MOMA_PAGE]}), None, MOMA_PAGE, "no_qid"),
        (FakeRegistry(failing=True), "Q19884054", MOMA_PAGE, "registry_unavailable"),
        (FakeRegistry(pages={"Q19884054": [MOMA_PAGE]}), "Q19884054", "https://www.moma.org/collection/works/9", "not_recorded"),
    ],
)
def test_a_refusal_on_its_title_says_why_no_link_settled_it(registry, qid, url, link, caplog):
    """Run 3's refusal of row 13 had one journal line for four different facts.
    Each has its own word now, with the page and the item beside it."""
    with caplog.at_level(logging.INFO):
        linked_resolution(a_moma_page(url=url), registry=registry, qid=qid)

    (refused,) = [record for record in caplog.records if getattr(record, "event", None) == "phase_two.not_the_work"]
    assert (refused.link, refused.found_url, refused.qid) == (link, url, qid)


@pytest.mark.parametrize(("title", "link"), [("Composition", "linked"), (LONG_TITLE, "title_matched")])
def test_an_artist_refusal_says_how_the_title_was_settled(title, link, caplog):
    with caplog.at_level(logging.INFO):
        linked_resolution(a_moma_page(title, artist="Jean Arp"), registry=FakeRegistry(pages={"Q19884054": [MOMA_PAGE]}))

    (refused,) = [record for record in caplog.records if getattr(record, "event", None) == "phase_two.not_the_work"]
    assert refused.link == link


def test_a_holders_leading_article_passes_the_title_gate():
    """Run 3's other refusal: MoMA's *The Tree*, asked for as "Tree", with no link to help."""
    assert len(resolve(an_instance("The Tree", artist="Agnes Martin"), title="Tree", artist="Agnes Martin")) == 1


# -- a holder's name for the artist that Wikidata records -----------------------
#
# Art UK writes "Laurence Stephen Lowry"; the Library's artist is Wikidata's label,
# "L. S. Lowry". Under the key alone the two disagree, and the right image was
# refused even on the page Lowry's work's item records.

LOWRY_WORK = "Q119294634"
LOWRY = "Q1354277"
ARTUK_PAGE = "https://artuk.org/discover/artworks/portrait-of-a-house-162388"
LOWRY_NAMES = {LOWRY: {"L. S. Lowry", "Laurence Stephen Lowry", "Lowry, Lawrence Stephen", "LS Lowry"}}
TAEUBER_ARP = "Q123307"
JEAN_ARP = "Q153739"
#: Both makers of a collaboration, each with their own names: neither name is the other's.
COUPLE_NAMES = {
    TAEUBER_ARP: {"Sophie Taeuber-Arp", "Sophie Taeuber", "Sophie Henriette Taeuber-Arp"},
    JEAN_ARP: {"Jean Arp", "Hans Arp"},
}


def an_artuk_record(title: str = "Portrait of a House", *, artist: str = "Laurence Stephen Lowry", url: str = ARTUK_PAGE):
    return FoundImage(
        url=url,
        provider="artic",  # the stub provider this module wires; the page is Art UK's
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        title=title,
        artist=artist,
        estimated_width=3000,
        estimated_height=2400,
    )


def lowry_registry(*, pages=(ARTUK_PAGE,), names=None) -> FakeRegistry:
    return FakeRegistry(pages={LOWRY_WORK: list(pages)}, names={LOWRY_WORK: LOWRY_NAMES if names is None else names})


def lowry_resolution(*instances: FoundImage, registry, artist: str | None = "L. S. Lowry", qid: str | None = LOWRY_WORK):
    return PhaseTwoEngine(ImageSourcePool([StubSearch(*instances)]), box=BOX, registry=registry).resolve(
        ImageQuery(title="Portrait of a House", artist=artist, qid=qid)
    )


def refusal_line(caplog) -> logging.LogRecord:
    (refused,) = [record for record in caplog.records if getattr(record, "event", None) == "phase_two.not_the_work"]
    return refused


def test_a_holders_full_name_is_the_artist_wikidata_labels_by_initials_on_the_items_page(caplog):
    with caplog.at_level(logging.INFO):
        resolution = lowry_resolution(an_artuk_record(), registry=lowry_registry())

    (entry,) = resolution.instances
    assert entry.confidence == CONFIDENT
    assert resolution.refusals == frozenset()
    assert "matching the requested title, on the page the work's Wikidata item records" in entry.rationale
    assert "by the requested artist under another name Wikidata records for them" in entry.rationale
    (renamed,) = [record for record in caplog.records if getattr(record, "event", None) == "phase_two.renamed"]
    assert (renamed.work_artist, renamed.found_artist, renamed.qid) == ("L. S. Lowry", "Laurence Stephen Lowry", LOWRY_WORK)


def test_a_differing_title_and_a_differing_name_on_the_items_page_say_both():
    (entry,) = lowry_resolution(an_artuk_record("A House, Portrait"), registry=lowry_registry()).instances

    assert entry.rationale.startswith(
        "Art Institute of Chicago holds this as 'A House, Portrait' by Laurence Stephen Lowry, a different title,"
    )
    assert "under another name Wikidata records for them" in entry.rationale


def test_the_same_name_off_the_items_page_is_still_refused(caplog):
    """A title match alone is not enough beside an alias: "Bruegel" names the father and the son who copied him."""
    with caplog.at_level(logging.INFO):
        resolution = lowry_resolution(
            an_artuk_record(url="https://artuk.org/discover/artworks/another-house-1"), registry=lowry_registry()
        )

    assert resolution.instances == []
    assert resolution.refusals == {UnresolvedReason.IDENTITY_REFUSED}
    assert refusal_line(caplog).names == "not_recorded"


def test_an_exact_artist_asks_wikidata_nothing_and_says_nothing_of_other_names(caplog):
    registry = lowry_registry()
    with caplog.at_level(logging.INFO):
        (entry,) = lowry_resolution(an_artuk_record(artist="L. S. Lowry"), registry=registry).instances

    assert (registry.pages_asked, registry.names_asked) == ([], [])
    assert "another name" not in entry.rationale
    assert "matching the requested title and artist" in entry.rationale
    assert not [record for record in caplog.records if getattr(record, "event", None) == "phase_two.renamed"]


def test_the_names_are_asked_once_however_many_records_need_them():
    registry = lowry_registry(pages=(ARTUK_PAGE, ARTUK_PAGE + "-2"))
    resolution = lowry_resolution(an_artuk_record(), an_artuk_record(url=ARTUK_PAGE + "-2"), registry=registry)

    assert len(resolution.instances) == 2
    assert (registry.pages_asked, registry.names_asked) == ([LOWRY_WORK], [LOWRY_WORK])


@pytest.mark.parametrize(
    ("asked", "holds"),
    [
        # Two people, two names, on the item's own page: the cross-check this must keep.
        ("Sophie Taeuber-Arp", "Jean Arp"),
        # Each a name of one of the work's two makers, but not of the same one.
        ("Hans Arp", "Sophie Taeuber"),
        # The holder's name is the creator's; the Library's is nobody's.
        ("Somebody Else", "Sophie Taeuber"),
    ],
)
def test_two_names_that_are_not_one_creators_are_refused_on_the_items_page(asked, holds, caplog):
    registry = FakeRegistry(pages={"Q19884054": [MOMA_PAGE]}, names={"Q19884054": COUPLE_NAMES})
    with caplog.at_level(logging.INFO):
        resolution = linked_resolution(a_moma_page(artist=holds), registry=registry, artist=asked)

    assert resolution.instances == []
    assert resolution.refusals == {UnresolvedReason.IDENTITY_REFUSED}
    assert refusal_line(caplog).names == "not_a_creators_name"


def test_one_creators_two_names_on_a_two_maker_work_pass():
    """The falsifying sibling of the case above: the same table, one person's two names."""
    registry = FakeRegistry(pages={"Q19884054": [MOMA_PAGE]}, names={"Q19884054": COUPLE_NAMES})
    (entry,) = linked_resolution(a_moma_page(artist="Hans Arp"), registry=registry, artist="Jean Arp").instances

    assert entry.confidence == CONFIDENT


def test_a_name_wikidata_does_not_record_is_refused():
    """`Sir Muirhead Bone` and `Robert Havell after John James Audubon` stay refused: no name of theirs says so."""
    resolution = lowry_resolution(an_artuk_record(artist="Sir L. S. Lowry RA"), registry=lowry_registry())

    assert resolution.refusals == {UnresolvedReason.IDENTITY_REFUSED}


def test_names_wikidata_could_not_be_asked_refuse_and_say_so(caplog):
    registry = lowry_registry()

    def down(qid):
        raise RegistryUnavailable("Wikidata is down")

    registry.creator_names = down
    engine = PhaseTwoEngine(ImageSourcePool([StubSearch()]), box=BOX, registry=registry)
    query = ImageQuery(title="Portrait of a House", artist="L. S. Lowry", qid=LOWRY_WORK)
    link = engine.link(query)
    with caplog.at_level(logging.INFO):
        outcome = engine.judge(query, an_artuk_record(), link)

    assert outcome is UnresolvedReason.IDENTITY_REFUSED
    assert refusal_line(caplog).names == "names_unavailable"
    assert "phase_two.names_unavailable" in [getattr(record, "event", None) for record in caplog.records]
    # Read by a look, to keep a "none" only as long as an outage is kept.
    assert link.unavailable


def test_a_pages_outage_on_a_title_match_with_a_differing_artist_marks_the_link_unavailable():
    """The title matched, so before this rule nothing was asked; now the page is, and a look must read its outage."""
    engine = PhaseTwoEngine(ImageSourcePool([StubSearch()]), box=BOX, registry=FakeRegistry(failing=True))
    query = ImageQuery(title="Portrait of a House", artist="L. S. Lowry", qid=LOWRY_WORK)
    link = engine.link(query)

    assert engine.judge(query, an_artuk_record(), link) is UnresolvedReason.IDENTITY_REFUSED
    assert link.unavailable


def test_a_link_that_asked_everything_successfully_is_not_unavailable():
    engine = PhaseTwoEngine(ImageSourcePool([StubSearch()]), box=BOX, registry=lowry_registry())
    query = ImageQuery(title="Portrait of a House", artist="L. S. Lowry", qid=LOWRY_WORK)
    link = engine.link(query)

    assert isinstance(engine.judge(query, an_artuk_record(), link), JudgedImage)
    assert not link.unavailable


@pytest.mark.parametrize(("registry", "qid", "reason"), [(None, LOWRY_WORK, "no_registry"), (lowry_registry(), None, "no_qid")])
def test_a_link_asked_names_with_nothing_to_ask_says_why_and_asks_nothing(registry, qid, reason):
    """The engine asks for the page first, which answers these two already; a link asked directly must not reach the registry."""
    link = PhaseTwoEngine(ImageSourcePool([StubSearch()]), box=BOX, registry=registry).link(
        ImageQuery(title="Portrait of a House", artist="L. S. Lowry", qid=qid)
    )

    assert link.unnamed("L. S. Lowry", "Laurence Stephen Lowry") == reason
    assert registry is None or registry.names_asked == []


@pytest.mark.parametrize(
    ("registry", "qid", "names"),
    [
        (None, LOWRY_WORK, "no_registry"),
        (lowry_registry(), None, "no_qid"),
        (FakeRegistry(failing=True), LOWRY_WORK, "registry_unavailable"),
    ],
)
def test_with_no_item_to_vouch_for_the_page_a_differing_name_is_refused(registry, qid, names, caplog):
    with caplog.at_level(logging.INFO):
        resolution = lowry_resolution(an_artuk_record(), registry=registry, qid=qid)

    assert resolution.instances == []
    assert refusal_line(caplog).names == names
