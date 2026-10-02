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
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from arrt.library.registry import Registry, RegistryPerson, RegistryUnavailable, RegistryWorkMatch
from arrt.library.services.artists import artist_ids_by_qid
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.folding import search_fold

log = logging.getLogger(__name__)

#: Fewer letters than this match too much to be worth a registry query: the
#: typeahead shows the library's matches alone until the third.
SHORTEST: Final[int] = 3

#: How many of each the search returns. The typeahead shows them all.
ARTISTS_FOUND: Final[int] = 3
WORKS_FOUND: Final[int] = 5

#: How many queries' answers are remembered. A curator's typing produces one per
#: pause, so this is hours of searching.
_REMEMBERED: Final[int] = 512

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
    #: The library's artist for each artist found that it holds, by QID.
    held_artists: Mapping[str, str] = field(default_factory=dict)
    #: The library's works in circulation for each work found that it holds, by QID.
    held_works: Mapping[str, Sequence[str]] = field(default_factory=dict)


class RegistrySearchService:
    """Search the registry for artists and works, and mark what the library holds."""

    def __init__(self, store: CatalogueStore, registry: Registry | None) -> None:
        self._store = store
        self._registry = registry
        self._remembered: OrderedDict[tuple[str, bool], tuple[Sequence[RegistryPerson], Sequence[RegistryWorkMatch]]] = (
            OrderedDict()
        )
        self._lock = threading.Lock()

    def search(self, query: str, *, prefix: bool) -> RegistrySearch:
        """The registry's artists and works for `query`; `prefix` reads its last word as the start of one."""
        words = _WORDS.findall(query)
        if sum(len(word) for word in words) < SHORTEST:
            return RegistrySearch(state=RegistrySearchState.TOO_SHORT)
        if self._registry is None:
            return RegistrySearch(
                state=RegistrySearchState.NOT_CONFIGURED,
                note=(
                    "Wikidata is not configured on this server (WIKIDATA_USER_AGENT is unset), "
                    "so only your library is searched."
                ),
            )
        try:
            artists, works = self._found(words, prefix, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not search Wikidata for %r: %s", query, exc)
            return RegistrySearch(state=RegistrySearchState.UNAVAILABLE, note="Wikidata could not be searched just now.")
        ours = artist_ids_by_qid(self._store)
        holdings = self._store.circulating_ids_by_qid()
        return RegistrySearch(
            state=RegistrySearchState.KNOWN,
            artists=artists,
            works=works,
            held_artists={person.qid: ours[person.qid] for person in artists if person.qid in ours},
            held_works={work.qid: holdings[work.qid] for work in works if work.qid in holdings},
        )

    def _found(
        self, words: Sequence[str], prefix: bool, registry: Registry
    ) -> tuple[Sequence[RegistryPerson], Sequence[RegistryWorkMatch]]:
        key = (search_fold(" ".join(words)), prefix)
        with self._lock:
            if key in self._remembered:
                self._remembered.move_to_end(key)
                return self._remembered[key]
        # Asked outside the lock, and both at once: see the module's note.
        with ThreadPoolExecutor(max_workers=2) as pool:
            people = pool.submit(registry.people_named, " ".join(words))
            matching = pool.submit(registry.works_matching, words, prefix=prefix, limit=WORKS_FOUND)
            found = (tuple(people.result())[:ARTISTS_FOUND], tuple(matching.result()))
        with self._lock:
            self._remembered[key] = found
            while len(self._remembered) > _REMEMBERED:
                self._remembered.popitem(last=False)
        return found
