"""Which Wikidata item a wanted work is, picked by the curator from what the registry finds.

A re-search asks Commons only by item (`ImageQuery.qid`), and a work proposed by
an Ask run carries none, so Search again on such a work finds no Commons scan
however famous the painting. `data-model.md` § Registry identity rules that a
work is never matched by title: a generic title cannot be told from another
work with the same name, and a candidate's QID becomes the artwork's identity at
acceptance. So this module **offers** the registry's matches and the curator
**picks** one (the owner's choice, 2026-10-02, `build-plan-after-review.md`);
nothing here stores a match on its own.

**Searched by the title and the artist's name together first.** Measured on the
seven Dalí works an August Ask run left with no scan (`wikidata-findings.md`
§ Matching a wanted work): the title alone put the right item first for six,
and found no Dalí *Mountain Lake* at all among eight landscapes by others; with
"Dalí" added it found that one item (Q28555476) and narrowed the rest. When the
narrower search finds nothing, the title alone is asked, since an artist spelled
differently by the run would otherwise hide every match.

**The proposed artist's matches lead**, then the registry's own order. Two items
by the right artist with one title is ordinary (*Lobster Telephone*: Q2990594 and
Q63109663), and is the case the curator's eye is for.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from arrt.library.registry import Registry, RegistryUnavailable, RegistryWorkMatch
from arrt.library.services.discovery import DiscoveryService
from arrt.library.services.registry_search import search_words
from arrt.persistence.discovery_records import CandidateWork
from arrt.persistence.folding import search_fold

log = logging.getLogger(__name__)

#: How many matches a picker shows. Enough for a title shared by a handful of
#: works; a list longer than this is a title too generic to pick from by eye.
MATCHES_SHOWN: Final[int] = 8

#: A trailing year a run writes after a title, "Lobster Telephone (1938)". The
#: registry's search ignores it, and so does the artist comparison; it is
#: removed so the narrower search is asked for the words that matter.
_TRAILING_YEAR = re.compile(r"\s*\(\s*\d{3,4}\s*\)\s*$")


class WorkMatchState(StrEnum):
    """Why the picker says what it says."""

    #: The registry answered, with matches or without.
    KNOWN = "known"
    #: No registry is configured (`WIKIDATA_USER_AGENT` unset).
    NOT_CONFIGURED = "not_configured"
    #: The registry was asked and could not answer.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class WorkMatch:
    """One item the registry found for a wanted work's title."""

    match: RegistryWorkMatch
    #: Whether its creator is the artist the run proposed: what puts it first.
    by_proposed_artist: bool


@dataclass(frozen=True, slots=True)
class WorkMatches:
    """The registry's candidates for a wanted work, and why there are or are not any."""

    work: CandidateWork
    state: WorkMatchState
    matches: Sequence[WorkMatch] = ()
    note: str | None = None


class WikidataMatchService:
    """Offer the registry's items for a wanted work, and record the one the curator picks."""

    def __init__(self, discovery: DiscoveryService, registry: Registry | None) -> None:
        self._discovery = discovery
        self._registry = registry

    def matches(self, candidate_work_id: str) -> WorkMatches:
        """Wikidata's works matching this work's title, the proposed artist's first."""
        work = self._discovery.get_candidate_work(candidate_work_id)
        registry = self._registry
        if registry is None:
            return WorkMatches(
                work=work,
                state=WorkMatchState.NOT_CONFIGURED,
                note="Matching a work to Wikidata needs WIKIDATA_USER_AGENT, which this deployment has not set.",
            )
        title = _TRAILING_YEAR.sub("", work.proposed_title)
        artist = work.proposed_artist or ""
        try:
            found = registry.works_matching(search_words(f"{title} {artist}"), prefix=False, limit=MATCHES_SHOWN)
            if not found:
                found = registry.works_matching(search_words(title), prefix=False, limit=MATCHES_SHOWN)
        except RegistryUnavailable as exc:
            log.warning(
                "Wikidata could not be asked for a wanted work's matches",
                extra={"event": "wanted.match_unavailable", "reason": str(exc)},
            )
            return WorkMatches(work=work, state=WorkMatchState.UNAVAILABLE, note=f"Wikidata could not be asked just now: {exc}")
        ranked = [WorkMatch(match=match, by_proposed_artist=_by(match, artist)) for match in found]
        # Stable, so the registry's own order holds within each half.
        ranked.sort(key=lambda entry: not entry.by_proposed_artist)
        return WorkMatches(work=work, state=WorkMatchState.KNOWN, matches=tuple(ranked))

    def pick(self, candidate_work_id: str, qid: str) -> CandidateWork:
        """Record the item the curator picked; it becomes the artwork's, as theirs, at acceptance."""
        return self._discovery.set_wikidata_item(candidate_work_id, qid)


def _by(match: RegistryWorkMatch, artist: str) -> bool:
    """Whether the registry's creator is the proposed artist, by name, accents and case aside.

    By containment, so "Salvador Dalí (with Edward James)" still counts Dalí. A
    match with no recorded creator is never counted: nothing says who made it.
    """
    if match.creator is None or not artist:
        return False
    creator = search_fold(str(match.creator.name)).strip()
    # An empty name is in every string, so it would put every match first.
    return bool(creator) and creator in search_fold(artist)
