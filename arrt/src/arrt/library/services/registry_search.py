"""What the registry finds for a few typed words: the other half of one-world search.

Ruling 2: a search covers the library and the registry together, each match
with its state. The library half is the catalogue's own search; this is the
registry's, asked separately so that a registry that is slow, off or down never
holds the library's matches back.

**Artists and works are asked at once**, on two threads: each is one query of
about half a second (`wikidata-findings.md` § Searching for works), and a
typeahead pays for every one in sequence.

**Remembered per query for the life of the process.** Typing back over a word
asks nothing, and the same words searched twice give the same answer. A failure
is not remembered.

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
from arrt.library.services.artists import artist_ids_by_qid
from arrt.library.services.remembered import NOT_CONFIGURED_NOTE, Remembered
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.folding import search_fold

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

#: A word as the search cuts a query into them, the characters names carry included.
_WORDS: Final[re.Pattern[str]] = re.compile(r"\w[\w'’-]*")


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


class RegistrySearchService:
    """Search the registry for artists and works, and mark what the library holds."""

    def __init__(self, store: CatalogueStore, registry: Registry | None) -> None:
        self._store = store
        self._registry = registry
        self._remembered: Remembered[tuple[str, bool, bool], tuple[Sequence[RegistryPerson], Sequence[RegistryWorkMatch]]] = (
            Remembered()
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
            artists, works = self._found(words, prefix, wide, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not search Wikidata for %r: %s", query, exc)
            return RegistrySearch(state=RegistrySearchState.UNAVAILABLE, note="Wikidata could not be searched just now.")
        ours = artist_ids_by_qid(self._store)
        holdings = self._store.circulating_ids_by_qid()
        return RegistrySearch(
            state=RegistrySearchState.KNOWN,
            artists=artists,
            works=works,
            # The artists found and the works' makers both: a maker the library
            # holds links to its page whether or not the name search found them.
            held_artists={
                qid: ours[qid]
                for qid in {person.qid for person in artists} | {work.creator.qid for work in works if work.creator}
                if qid in ours
            },
            held_works={work.qid: holdings[work.qid] for work in works if work.qid in holdings},
        )

    def _found(
        self, words: Sequence[str], prefix: bool, wide: bool, registry: Registry
    ) -> tuple[Sequence[RegistryPerson], Sequence[RegistryWorkMatch]]:
        key = (search_fold(" ".join(words)), prefix, wide)
        artists_found, works_found = (ARTISTS_FOUND_WIDE, WORKS_FOUND_WIDE) if wide else (ARTISTS_FOUND, WORKS_FOUND)
        remembered = self._remembered.get(key)
        if remembered is not None:
            return remembered
        # Asked outside the lock, and both at once: see the module's note.
        with ThreadPoolExecutor(max_workers=2) as pool:
            people = pool.submit(registry.people_named, " ".join(words))
            matching = pool.submit(registry.works_matching, words, prefix=prefix, limit=works_found)
            found = (tuple(people.result())[:artists_found], tuple(matching.result()))
        self._remembered.put(key, found)
        return found
