"""Phase 2: one work, a provider's instances, and which of them is the work.

This is the judgement the seam deliberately keeps out of a provider. A museum
reports what its collection holds; whether any of it is the painting a curator
asked for is decided here, once, in terms that do not vary by provider.

**Confidence is an identity comparison, never a relevance score.** The Art
Institute's search was measured returning a real work by a real artist, at a
comfortable score, for a painting it does not hold: asking for *The Persistence
of Memory* surfaces *Ann-In Memory* by Joseph Cornell. Ranking by the provider's
own number attaches that to the request and reports success. So the test is
whether the title the provider returned *is* the requested title, and whether the
artists agree — derived from `dedup`, which is where this product's answer to
"are these the same work" already lives and was measured. Reimplementing the
normalisation here would be a second answer free to drift from the one the dedup
key is built with.

**A page the work's Wikidata item records is about the work, whatever its title
says.** A holder may catalogue a work under a shorter or another title — MoMA
holds Taeuber-Arp's *Composition of Circles and Overlapping Angles* as
*Composition* — and accepting a shorter title on its own would match every
*Composition* by that painter. The item naming the page settles which one it is,
so a result whose `url` is such a page passes the title comparison, and the
artist comparison still runs. The registry is asked here, not read from the pages
the sources answered, because any finder may answer a page, one found by a search
included, and a search's page is no evidence of identity.

**An artist disagreement is disqualifying, not a deduction.** The same collection
holds *American Gothic* by Grant Wood and *American Gothic* by Elizabeth Layton.
A scheme that scored the wrong one slightly lower would still select it whenever
the right one was absent, which is precisely the case that matters.

**Two names Wikidata records for one of the item's creators are not a
disagreement, on a page the item records.** Holders write the names they write:
"Laurence Stephen Lowry" for the Library's "L. S. Lowry", "Rembrandt van Rijn"
for "Rembrandt", "Vassily Kandinsky" for "Wassily Kandinsky", and the key alone
refused a quarter of the NGA's imaged items for it
(`artist-name-identity-findings.md`). Aliases are open to anyone and some name
two people, so they count only where the item already vouches for the page,
never beside a title match alone (`_renaming`).

**Quality is whether the scan meets the quality profile's minimum**, graded by
its long edge in pixels — deliberately *not* by any size it would render at on a
screen, which the Library does not know. The verdict comes from the same profile
the review grid judges against, so phase 2 does not grow a resolution policy of
its own.

Quality breaks ties; it never overturns confidence, because a gorgeous scan of
the wrong painting is worse than a modest scan of the right one.

**The ordering is unconditional, and the `source_class`-dependent dominance the
data model describes is deliberately not built.** Nothing produces a
`contemporary_web` candidate — every instance phase 2 records comes from a museum
API and is `institutional` — so a switch on it would have one reachable branch and
one branch no deployment could exercise. What stands in its place is stronger
where it matters: confidence is not a weight but a gate, so an instance that is
not the requested work is refused rather than ranked lower, which for a work with
a single candidate image is the whole of the `contemporary_web` concern. Among
several institutional copies of one work, from more than one source, resolution
and rights still decide, and the order the sources are listed in breaks a level
tie; `data-model.md` records why no source is preferred outright.

**Below the minimum is not a rejection.** Such an instance is recorded, offered,
and labelled with its size — it is simply not selected without a curator saying
so. A work whose every instance is below the minimum holds no
selection and is reported `unresolved`, which is a first-class outcome rather
than an absent row.
"""

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from arrt.library.discovery.dedup import artist_key, title_key
from arrt.library.discovery.images import FoundImage, FoundPage, ImageQuery, ImageSearchFailure
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry import Registry, RegistryUnavailable
from arrt.library.services.quality import PRESENTATION_MASTER_LONG_EDGE_PX, Fit, QualityProfile
from arrt.library.sources.names import museum_name
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import RightsStatus

log = logging.getLogger(__name__)

#: Confidence when the provider's title and artist both match what was asked for.
#: Not 1.0: this is a strong textual identity match, not an inspection of the
#: picture, and a number reserved for certainty leaves somewhere for a provider
#: that can actually verify the image to go.
CONFIDENT: Final[float] = 0.95

#: Confidence when the titles match and the *request* named no artist. Lower
#: because a title alone is a weaker identity — the collection holds two
#: different *American Gothic*s — and phase 1 not naming an artist is exactly
#: when that ambiguity is unresolvable here.
TITLE_ONLY: Final[float] = 0.75

#: Confidence when the titles match and the *provider* names no artist. Lower
#: still: the request was specific and the record cannot confirm the half that
#: would have settled it.
UNATTRIBUTED_RECORD: Final[float] = 0.6

#: How much of `quality_score` is resolution rather than rights. Rights are a
#: component of quality in the data model and a genuine provenance signal — an
#: institution's own public-domain scan is usually the authoritative file — but
#: they are weighted to break a tie and never to overturn a resolution
#: difference. **This is not a rights gate** (constraint 13): nothing is
#: excluded, filtered or refused on rights, and an in-copyright instance with
#: better resolution still wins.
_RESOLUTION_WEIGHT: Final[float] = 0.85

_RIGHTS_TERM: Final[dict[RightsStatus | None, float]] = {
    RightsStatus.PUBLIC_DOMAIN: 1.0,
    RightsStatus.IN_COPYRIGHT: 0.5,
    RightsStatus.UNKNOWN: 0.5,
    None: 0.5,
}

#: Where each verdict's band starts. The verdict dominates and the long edge
#: grades within it, so an instance meeting the minimum always outranks one
#: below it, however close the second came.
_BAND_BASE: Final[dict[Fit, float]] = {
    Fit.BELOW_MINIMUM: 0.0,
    Fit.MEETS_MINIMUM: 1 / 2,
}

_BAND_WIDTH: Final[float] = 1 / 2


@dataclass(frozen=True, slots=True)
class JudgedImage:
    """One instance, judged against the work it was found for.

    The verdict travels with the judgement rather than being recomputed by a
    caller, because computing it twice is how the label on the review card and
    the decision come to disagree.
    """

    found: FoundImage
    confidence: float
    quality_score: float
    rationale: str
    fit: Fit

    @property
    def below_minimum(self) -> bool:
        """Whether this falls short of the quality profile's minimum."""
        return self.fit is Fit.BELOW_MINIMUM


@dataclass(frozen=True, slots=True)
class Resolution:
    """What one work's search produced: what survived, and why the rest did not.

    The refusals travel back because they cannot be recovered downstream. A
    result discarded here never becomes a row, so a work that ends with nothing
    looks identical from the store whether the collection holds no such title, or
    holds it under another artist, or holds it in a scan too small to judge —
    and those are the distinctions a curator needs to act on.

    It is a set rather than a tally deliberately: what the reason derivation asks
    is *whether* a gate refused anything, never how often, and a count nobody
    reads is a number that can be wrong without anything noticing. The per-result
    detail is already in the log, one line per discard, where diagnosis wants it.
    """

    instances: Sequence[JudgedImage]
    refusals: frozenset[UnresolvedReason]
    #: Pages the sources found and do not read, passed on unjudged: there is
    #: nothing in one to judge (`FoundPage`), and what becomes of it is decided
    #: where the work's item is known.
    pages: tuple[FoundPage, ...] = ()


class PhaseTwoEngine:
    """Turn one work into the instances that are credibly it, best first."""

    def __init__(self, sources: ImageSourcePool, *, profile: QualityProfile, registry: Registry | None = None) -> None:
        self._sources = sources
        self._profile = profile
        #: Where a work's item says it is described. `None` is a deployment with
        #: no registry, where only the title comparison identifies a work.
        self._registry = registry

    def resolve(self, query: ImageQuery) -> Resolution:
        """Every credible instance for this work, most confident first, and the refusals.

        An empty result is a real answer and the caller must record it as one,
        together with the reason it came back empty: whether nothing this
        provider holds carries the title, or something did and disagreed on the
        artist, or something matched and could not be sized. Raises
        `ImageSearchFailure` when the provider could not be asked at all — a
        different fact, and one that says nothing about the work.

        A provider that returns nothing at all refuses nothing, and the empty
        refusal set is read downstream as `NOT_HELD`: no record came back whose
        title matched, which is exactly what happened, vacuously.

        **When a source could not be asked, only an instance that meets the
        minimum settles the work.** Without one, the source that was down may hold
        the image the others lack, so the work is reported unreachable, as it is
        when no source answers, and is searched again later. Calling it
        unresolved would record a fact about the work that nobody observed.
        """
        answer = self._sources.find_images(query)
        judged: list[JudgedImage] = []
        refusals: set[UnresolvedReason] = set()
        link = self.link(query)
        for found in answer.images:
            outcome = self.judge(query, found, link)
            if isinstance(outcome, UnresolvedReason):
                refusals.add(outcome)
            else:
                judged.append(outcome)
        judged.sort(key=self.rank)
        if answer.unreachable and all(entry.below_minimum for entry in judged):
            raise ImageSearchFailure(
                f"{', '.join(answer.unreachable)} could not be asked, and no other source has an image of "
                f"{query.title!r} that meets the quality minimum."
            )
        log.info(
            "judged a work's instances",
            extra={
                "event": "phase_two.judged",
                "work_title": query.title,
                "instances_credible": len(judged),
                "instances_below_floor": sum(1 for entry in judged if entry.below_minimum),
                "refused_at": sorted(str(reason) for reason in refusals),
                "unreachable": list(answer.unreachable),
            },
        )
        return Resolution(instances=judged, refusals=frozenset(refusals), pages=answer.pages)

    def link(self, query: ImageQuery) -> WikidataLink:
        """The pages this work's Wikidata item records, to be asked once for every instance judged against it."""
        return WikidataLink(self._registry, query)

    def rank(self, entry: JudgedImage) -> tuple[bool, float, float, int, str]:
        """Where an instance stands among a work's, best first: the order `resolve` returns them in.

        Meeting the minimum first, then confidence, then quality, then the order
        the sources are listed in, and the URL last, so two runs over the same
        answers order them alike.
        """
        return (
            entry.below_minimum,
            -entry.confidence,
            -entry.quality_score,
            self._sources.precedence(entry.found.provider),
            entry.found.url,
        )

    def judge(self, query: ImageQuery, found: FoundImage, link: WikidataLink) -> JudgedImage | UnresolvedReason:
        """Score one instance, or name the gate that refused it.

        The gate is returned rather than a bare `None` because the three refusals
        here are three different facts — about the collection, about two
        spellings of a name, and about the record — and collapsing them is what
        left a run that resolved nothing unable to say anything about why.
        """
        linked = False
        if title_key(query.title) != title_key(found.title):
            unlinked = link.unlinked(found.url)
            if unlinked is not None:
                log.info(
                    "discarding a result whose title is a different work entirely",
                    extra={
                        "event": "phase_two.not_the_work",
                        "work_title": query.title,
                        "found_title": found.title,
                        "found_artist": found.artist,
                        "found_url": found.url,
                        "qid": query.qid,
                        "link": unlinked,
                    },
                )
                return UnresolvedReason.NOT_HELD
            linked = True
            log.info(
                "keeping a result whose title differs, because the work's Wikidata item records its page",
                extra={
                    "event": "phase_two.linked",
                    "work_title": query.title,
                    "found_title": found.title,
                    "found_url": found.url,
                    "qid": query.qid,
                },
            )
        confidence = _confidence(query, found)
        renamed = False
        if confidence is None:
            # `_confidence` answers None only when both name an artist and the two disagree.
            unnamed = _renaming(link, found, asked=query.artist or "", holds=found.artist or "")
            if unnamed is not None:
                log.info(
                    "discarding a result identified by its title or its page, whose artist does not match",
                    extra={
                        "event": "phase_two.not_the_work",
                        "work_title": query.title,
                        "found_title": found.title,
                        "found_artist": found.artist,
                        "found_url": found.url,
                        "qid": query.qid,
                        "link": "linked" if linked else "title_matched",
                        "names": unnamed,
                    },
                )
                return UnresolvedReason.IDENTITY_REFUSED
            confidence, renamed = CONFIDENT, True
            log.info(
                "keeping a result whose artist is named differently, because Wikidata records both names for the work's creator",
                extra={
                    "event": "phase_two.renamed",
                    "work_title": query.title,
                    "work_artist": query.artist,
                    "found_artist": found.artist,
                    "found_url": found.url,
                    "qid": query.qid,
                },
            )
        if found.estimated_width is None or found.estimated_height is None:
            # An instance whose size is unknown cannot be judged against the
            # minimum, and one recorded anyway is indistinguishable from one
            # that meets it — which is the single thing the minimum
            # exists to make visible. Dropped rather than recorded unassessable,
            # and logged so a provider that stops reporting dimensions shows up
            # as a run finding nothing rather than as a run finding everything.
            log.info(
                "discarding an instance whose size the provider did not report",
                extra={"event": "phase_two.size_unknown", "work_title": query.title, "found_title": found.title},
            )
            return UnresolvedReason.SIZE_UNKNOWN
        fit = self._profile.judge(width=found.estimated_width, height=found.estimated_height)
        quality = _quality(
            fit,
            found.rights_status,
            long_edge=max(found.estimated_width, found.estimated_height),
            profile=self._profile,
        )
        return JudgedImage(
            found=found,
            confidence=confidence,
            quality_score=quality,
            rationale=_rationale(found, confidence=confidence, fit=fit, linked=linked, renamed=renamed),
            fit=fit,
        )


class WikidataLink:
    """What a work's Wikidata item says about where it is described and who made it, each asked once, only if needed.

    The pages are asked only when a result's title or artist differs, and the
    creators' names only when an artist differs on a page the item records, so a
    work every source names alike costs the registry nothing. A registry that
    cannot be asked means no link and no names, and the comparison decides as it
    would without them: refusing is the direction a later search can undo.

    **Safe to share between threads.** A look judges each source's answer on
    that source's own thread, against one link per work, so two answers arriving
    together must still ask the registry once.
    """

    def __init__(self, registry: Registry | None, query: ImageQuery) -> None:
        self._registry = registry
        self._query = query
        self._pages: frozenset[str] | None = None
        self._pages_unavailable = False
        #: Each recorded creator's names, keyed as `artist_key` keys them.
        self._names: tuple[frozenset[str], ...] | None = None
        self._names_unavailable = False
        self._asking = threading.Lock()

    @property
    def unavailable(self) -> bool:
        """Whether the registry could not be asked something, so a comparison decided without what it would have said."""
        with self._asking:
            return self._pages_unavailable or self._names_unavailable

    def unlinked(self, url: str) -> str | None:
        """`None` when the work's item records `url`, exactly as the item spells it; else why not.

        The reason is a word for the journal, one per way of having no link, so a
        refusal of a page somebody expected to pass says which it was: no
        registry here, no item for the work, a registry that could not be asked,
        or an item that names other pages.
        """
        if self._registry is None:
            return "no_registry"
        if self._query.qid is None:
            return "no_qid"
        with self._asking:
            if self._pages is None:
                try:
                    self._pages = frozenset(self._registry.pages_about(self._query.qid))
                except RegistryUnavailable as exc:
                    log.warning(
                        "could not ask Wikidata which pages describe a work, so no page of it is taken as the work: %s",
                        exc,
                        extra={
                            "event": "phase_two.link_unavailable",
                            "work_title": self._query.title,
                            "qid": self._query.qid,
                        },
                    )
                    self._pages_unavailable = True
                    self._pages = frozenset()
            pages, unavailable = self._pages, self._pages_unavailable
        if url in pages:
            return None
        return "registry_unavailable" if unavailable else "not_recorded"

    def unnamed(self, asked: str, holds: str) -> str | None:
        """`None` when both names are names Wikidata records for one of the work's creators; else why not.

        Compared under `artist_key`, so the names agree as the rest of the
        identity check's names do: case, accents and punctuation aside, and in
        order. `names_unavailable` when Wikidata could not be asked;
        `not_a_creators_name` when it answered and no one creator carries both.
        """
        if self._registry is None:
            return "no_registry"
        if self._query.qid is None:
            return "no_qid"
        with self._asking:
            if self._names is None:
                try:
                    recorded = self._registry.creator_names(self._query.qid)
                    self._names = tuple(
                        frozenset(key for key in map(artist_key, written) if key) for written in recorded.values()
                    )
                except RegistryUnavailable as exc:
                    log.warning(
                        "could not ask Wikidata the names of a work's creators, so a differently named artist is refused: %s",
                        exc,
                        extra={
                            "event": "phase_two.names_unavailable",
                            "work_title": self._query.title,
                            "qid": self._query.qid,
                        },
                    )
                    self._names_unavailable = True
                    self._names = ()
            names, unavailable = self._names, self._names_unavailable
        asked_key, held_key = artist_key(asked), artist_key(holds)
        if asked_key and held_key and any(asked_key in keys and held_key in keys for keys in names):
            return None
        return "names_unavailable" if unavailable else "not_a_creators_name"


def _renaming(link: WikidataLink, found: FoundImage, *, asked: str, holds: str) -> str | None:
    """`None` when two differing names are one artist by the work's own item; else why not.

    **Both names must be names Wikidata records for one creator the item
    records, and the page must be one the item records.** A holder writes
    "Laurence Stephen Lowry" where the Library's label is "L. S. Lowry", and
    "Rembrandt van Rijn" for "Rembrandt"; Wikidata carries both forms for that
    person. But anyone can add an alias, and some name another person as well:
    "Canaletto" is an alias of Bellotto, his nephew. So a recorded name is
    accepted only where the item already identifies the record. On a title match
    alone, an alias would take a Brueghel the Younger copy for his father's work,
    under the same title (`artist-name-identity-findings.md`).

    The reason is a word for the journal: the page link's own word when the page
    is not the item's (`no_registry`, `no_qid`, `registry_unavailable`,
    `not_recorded`), `names_unavailable` when Wikidata could not be asked the
    names, and `not_a_creators_name` when it was asked and the names are not one
    creator's.
    """
    unlinked = link.unlinked(found.url)
    if unlinked is not None:
        return unlinked
    return link.unnamed(asked, holds)


def _confidence(query: ImageQuery, found: FoundImage) -> float | None:
    """How sure we are this is that work, or `None` when the artist disagrees.

    **Called only for a record whose title already matches**, or whose page the
    work's Wikidata item records — the caller checks that first so it can tell a
    title nobody holds apart from a title held under another name, which are
    different facts about the collection. So the `None`
    here means exactly one thing: the two names disagree.

    `None` is deliberately not a low score. A near-match kept at low confidence
    is still selected the moment nothing better exists, which is exactly the
    situation a work the museum does not hold produces — so the only safe
    representation of "this is a different painting" is absence.
    """
    asked = artist_key(query.artist) if query.artist else ""
    holds = artist_key(found.artist) if found.artist else ""
    if asked and holds:
        return CONFIDENT if asked == holds else None
    if not asked:
        return TITLE_ONLY
    return UNATTRIBUTED_RECORD


def _quality(fit: Fit, rights: RightsStatus | None, *, long_edge: int, profile: QualityProfile) -> float:
    """How good this file is, as one number in 0..1.

    **The verdict picks the band and the long edge grades within it.** Crossing
    the minimum is a genuine step rather than a continuous one, because it is
    the point where the scan may be chosen without a curator asking.

    **The long edge, not megapixels or a rendered size.** Megapixels undercount
    a tall narrow work, and a rendered size needs a screen the Library does not
    hold. The long edge is what the minimum, the presentation master's cap and
    the upgrade tiers all measure.
    """
    resolution = _BAND_BASE.get(fit, 0.0) + _BAND_WIDTH * _within_band(fit, long_edge=long_edge, profile=profile)
    # `.get` with the neutral term rather than indexing: a rights value added to
    # the enum later is an unranked one, not a crash in a worker thread that
    # would end the run.
    return _RESOLUTION_WEIGHT * resolution + (1 - _RESOLUTION_WEIGHT) * _RIGHTS_TERM.get(rights, 0.5)


def _within_band(fit: Fit, *, long_edge: int, profile: QualityProfile) -> float:
    """Where in its band this instance sits, in 0..1.

    Below the minimum, how close it came to reaching it. Above it, how far it
    goes towards the presentation master's cap, and level beyond: a master is
    never larger than the cap, so two scans both past it show identically on
    every wall, and the losing instance is retained anyway.
    """
    minimum = profile.minimum_long_edge_px
    if fit is Fit.BELOW_MINIMUM:
        return min(1.0, long_edge / minimum)
    headroom = PRESENTATION_MASTER_LONG_EDGE_PX - minimum
    if headroom <= 0:
        # A minimum at or above the cap leaves nothing to grade: every scan that
        # meets it is cut to the same master.
        return 1.0
    return min(1.0, (long_edge - minimum) / headroom)


def _rationale(found: FoundImage, *, confidence: float, fit: Fit, linked: bool = False, renamed: bool = False) -> str:
    """Why this instance was chosen, in the words a curator asking gets back.

    Written for the review card rather than for a log: it names what the museum
    calls the work, how the identity was established, and the scan's size — the
    last because a curator judging a small instance needs the number, not the
    verdict.

    **The size is the scan's pixels, never inches on a wall** (the owner's
    ruling, 2026-10-02). A size on a wall belongs to one screen, and the Library
    holds none. The verdict's consequence is still said in words. A sentence
    already stored is a record of what the run said and is left as written;
    this governs runs from now on.
    """
    holder = f"{museum_name(found.provider)} holds this as {found.title!r}"
    holder += f" by {found.artist}" if found.artist else ", with no artist recorded"
    if renamed:
        # The artist's name differs too, so the sentence says what made it the
        # requested artist: a curator reading another name on the card needs it.
        title = "a different title" if linked else "matching the requested title"
        identity = (
            f"{title}, on the page the work's Wikidata item records, by the requested artist "
            "under another name Wikidata records for them"
        )
    elif linked:
        # The title differs, so the sentence says what identified it instead:
        # a curator reading another title on the card needs the reason it is here.
        identity = "a different title, on the page the work's Wikidata item records"
        if confidence >= CONFIDENT:
            identity += ", by the requested artist"
        elif confidence >= TITLE_ONLY:
            identity += "; the request named no artist"
        else:
            identity += "; the record names no artist to confirm it"
    elif confidence >= CONFIDENT:
        identity = "matching the requested title and artist"
    elif confidence >= TITLE_ONLY:
        identity = "matching the requested title; the request named no artist"
    else:
        identity = "matching the requested title; the record names no artist to confirm it"
    size = f"It is {found.estimated_width:,} × {found.estimated_height:,} px"
    if fit is Fit.BELOW_MINIMUM:
        size += ", below the quality minimum, so it is offered but not selected automatically"
    else:
        size += ", which meets the quality minimum"
    return f"{holder}, {identity}. {size}."
