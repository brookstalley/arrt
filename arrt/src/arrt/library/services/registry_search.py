"""What the registry finds for a few typed words: the other half of one-world search.

Ruling 2: a search covers the library and the registry together, each match
with its state. The library half is the catalogue's own search; this is the
registry's, asked separately so that a registry that is slow, off or down never
holds the library's matches back.

**Artists and works are asked at once**, on two threads: each is one query of
about half a second (`wikidata-findings.md` § Searching for works), and a
typeahead pays for every one in sequence.

**Kept per query for a week, across restarts.** Typing back over a word asks
nothing, and the same words searched twice give the same answer. A failure is
not kept.

**Each match is folded into what the library holds of it**, by QID or, for a
held work or artist with none, by title and artist or name and life dates
(`twins.py`), so a held work is never also offered as not held. A work a run has
found and that waits for a verdict says so, with where it waits.

**Nothing a curator types reaches the registry as search syntax.** The query is
cut into words, and the registry's client drops any word that is not one.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from arrt.library.registry import Registry, RegistryPerson, RegistryUnavailable, RegistryWorkMatch
from arrt.library.services.artists import REGISTRY_KEPT_FOR, WantedItems, artist_ids_by_qid
from arrt.library.services.remembered import NOT_CONFIGURED_NOTE, REMEMBERED
from arrt.library.services.twins import AwaitingReview, InReview, Twins
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.folding import search_fold
from arrt.persistence.kept import JsonCodec, Kept, KeptAnswers

log = logging.getLogger(__name__)

#: Fewer letters than this match too much to be worth a registry query: the
#: typeahead shows the library's matches alone until the third.
SHORTEST: Final[int] = 3

#: How many of each the search returns. The typeahead shows them all.
ARTISTS_FOUND: Final[int] = 3
WORKS_FOUND: Final[int] = 5

#: How many of each a `wide` search returns, for the results page: a page to
#: read down rather than a dropdown to pick from.
ARTISTS_FOUND_WIDE: Final[int] = 10
WORKS_FOUND_WIDE: Final[int] = 20

#: What the registry found for one query: its artists, then its works.
type _Found = tuple[tuple[RegistryPerson, ...], tuple[RegistryWorkMatch, ...]]

#: A word as the search cuts a query into them, the characters names carry included.
_WORDS: Final[re.Pattern[str]] = re.compile(r"\w[\w'’-]*")


def search_words(text: str) -> list[str]:
    """The words a registry search is asked for: letters and digits, apostrophes and hyphens kept inside a word.

    Whitespace alone is not enough, because the registry's adapter drops any
    token that is not a plain word, so "Life," or "(Premonition" would vanish
    from the search rather than be asked for.
    """
    return _WORDS.findall(text)


class RegistrySearchState(StrEnum):
    """Why the registry's half of a search says what it says."""

    #: The registry answered, with matches or without.
    KNOWN = "known"
    #: Too few letters to ask about.
    TOO_SHORT = "too_short"
    #: No registry is configured (`WIKIDATA_USER_AGENT` unset).
    NOT_CONFIGURED = "not_configured"
    #: The registry was asked and could not answer.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RegistrySearch:
    """The registry's matches for a query, each with what the library holds of it."""

    state: RegistrySearchState
    #: A sentence for the curator when the state is `NOT_CONFIGURED` or `UNAVAILABLE`.
    note: str | None = None
    artists: Sequence[RegistryPerson] = ()
    works: Sequence[RegistryWorkMatch] = ()
    #: The library's artist for each artist found, and each work's maker, that it holds, by QID.
    held_artists: Mapping[str, str] = field(default_factory=dict)
    #: The library's works in circulation for each work found that it holds, by QID.
    held_works: Mapping[str, Sequence[str]] = field(default_factory=dict)
    #: The QIDs among the works found that a wanted work names.
    wanted_works: frozenset[str] = frozenset()
    #: The proposed work awaiting a verdict that each work found and not held is, by QID.
    waiting_works: Mapping[str, InReview] = field(default_factory=dict)
    #: For each artist found and not held, a proposed work of theirs awaiting a verdict, by QID.
    waiting_artists: Mapping[str, InReview] = field(default_factory=dict)


class RegistrySearchService:
    """Search the registry for artists and works, and mark what the library holds."""

    def __init__(
        self,
        store: CatalogueStore,
        registry: Registry | None,
        *,
        kept: KeptAnswers,
        wanted: WantedItems,
        awaiting: AwaitingReview,
    ) -> None:
        self._store = store
        self._registry = registry
        self._wanted = wanted
        self._awaiting = awaiting
        self._kept: Kept[tuple[str, bool, bool], _Found] = kept.namespace(
            "registry.search", codec=JsonCodec(_Found), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )

    def search(self, query: str, *, prefix: bool, wide: bool = False) -> RegistrySearch:
        """The registry's artists and works for `query`.

        `prefix` reads its last word as the start of one; `wide` returns the
        results page's longer lists rather than the typeahead's.
        """
        words = _WORDS.findall(query)
        if sum(len(word) for word in words) < SHORTEST:
            return RegistrySearch(state=RegistrySearchState.TOO_SHORT)
        if self._registry is None:
            return RegistrySearch(
                state=RegistrySearchState.NOT_CONFIGURED,
                # The shared sentence, continued: what the curator is shown instead.
                note=f"{NOT_CONFIGURED_NOTE.removesuffix('.')}, so only your library is searched.",
            )
        try:
            artists, works = self._found(words, self._registry, prefix=prefix, wide=wide)
        except RegistryUnavailable as exc:
            log.warning("Could not search Wikidata for %r: %s", query, exc)
            return RegistrySearch(state=RegistrySearchState.UNAVAILABLE, note="Wikidata could not be searched just now.")
        return self._marked(artists, works)

    def _marked(self, artists: Sequence[RegistryPerson], works: Sequence[RegistryWorkMatch]) -> RegistrySearch:
        """The registry's matches, each marked held, waiting for review, or wanted."""
        ours = artist_ids_by_qid(self._store)
        twins = Twins(self._store, self._awaiting)
        held_artists: dict[str, str] = {}
        waiting_artists: dict[str, InReview] = {}
        for person in artists:
            held = ours.get(person.qid) or twins.held_artist(person)
            if held is not None:
                held_artists[person.qid] = held
            elif (review := twins.waiting_artist(person.label)) is not None:
                waiting_artists[person.qid] = review
        # A maker the library holds links to its page whether or not the name
        # search found them; by QID only, since a maker carries no life dates.
        for work in works:
            if work.creator and work.creator.qid in ours:
                held_artists.setdefault(work.creator.qid, ours[work.creator.qid])
        held_works: dict[str, Sequence[str]] = {}
        waiting_works: dict[str, InReview] = {}
        for work in works:
            maker, maker_qid = (work.creator.name, work.creator.qid) if work.creator else (None, None)
            if found := twins.held_work(work.qid, work.title, maker=maker, maker_qid=maker_qid):
                held_works[work.qid] = found
            elif (review := twins.waiting_work(work.qid, work.title, maker=maker, maker_qid=maker_qid)) is not None:
                waiting_works[work.qid] = review
        wanted = self._wanted.wanted_qids()
        return RegistrySearch(
            state=RegistrySearchState.KNOWN,
            artists=artists,
            works=works,
            held_artists=held_artists,
            held_works=held_works,
            wanted_works=frozenset(work.qid for work in works if work.qid in wanted),
            waiting_works=waiting_works,
            waiting_artists=waiting_artists,
        )

    def _found(self, words: Sequence[str], registry: Registry, *, prefix: bool, wide: bool) -> _Found:
        key = (search_fold(" ".join(words)), prefix, wide)
        artists_found, works_found = (ARTISTS_FOUND_WIDE, WORKS_FOUND_WIDE) if wide else (ARTISTS_FOUND, WORKS_FOUND)
        kept = self._kept.get(key)
        if kept is not None:
            return kept
        # Asked under no lock, and both at once: see the module's note.
        with ThreadPoolExecutor(max_workers=2) as pool:
            people = pool.submit(registry.people_named, " ".join(words))
            matching = pool.submit(registry.works_matching, words, prefix=prefix, limit=works_found)
            found = (tuple(people.result())[:artists_found], tuple(matching.result()))
        self._kept.put(key, found)
        return found
