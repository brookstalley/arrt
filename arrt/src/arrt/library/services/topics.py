"""Topics as a registry knows them: a period, a movement, a subject or a medium.

The registry half of a Topic page (`build-plan-topics-and-destinations.md`):
what the topic is, the works it is known for, and its artists. Each is its own
call, as the Artist page's sections are, so a slow or failed one leaves the rest
of the page standing and says which it was.

**Remembered per topic for the life of the process**, as the Artist page's
sections are: a century's works took seven to twenty-six seconds to ask for
(`wikidata-findings.md` § Topics), and a curator going back and forth between a
topic and a work in it should not wait again. A failure is not remembered, and
neither is an item the registry does not have, so the next visit asks again.

**Held is the library's to say, and is said fresh each time.** The registry's
answer is remembered; which of its works the library holds in circulation is
read from the catalogue on every call, so a work accepted a minute ago is
marked *Held* without forgetting the topic.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from arrt.library.registry import (
    Registry,
    RegistrySimilar,
    RegistryTopic,
    RegistryTopicWork,
    RegistryUnavailable,
)
from arrt.library.services.artists import artist_ids_by_qid
from arrt.library.services.remembered import Remembered, checked_qid
from arrt.persistence.catalogue import CatalogueStore

log = logging.getLogger(__name__)

#: How many of a topic's works the page lists: the most renowned.
WORKS_SHOWN: Final[int] = 50

#: How many of its artists it lists, as *Similar artists* does.
ARTISTS_SHOWN: Final[int] = 12

#: What every topic section says when `WIKIDATA_USER_AGENT` is unset: topics
#: exist only in the registry, so without it there are none.
TOPICS_NOT_CONFIGURED_NOTE: Final[str] = (
    "Topics come from Wikidata, which is not configured on this server (WIKIDATA_USER_AGENT is unset)."
)

#: What a section says when the registry was asked and could not answer.
UNAVAILABLE_NOTE: Final[str] = "Wikidata could not be asked just now. Try again later."


class TopicState(StrEnum):
    """Why a topic section says what it says."""

    #: The registry answered.
    KNOWN = "known"
    #: The registry was asked and has no such item.
    NOT_FOUND = "not_found"
    #: No registry is configured (`WIKIDATA_USER_AGENT` unset).
    NOT_CONFIGURED = "not_configured"
    #: The registry was asked and could not answer.
    UNAVAILABLE = "unavailable"


class WorkState(StrEnum):
    """What the library can do with one of a topic's works, as the Artist page marks it."""

    #: The library holds it in circulation.
    HELD = "held"
    #: Not held, and the registry has a free image of it.
    IMAGE_FOUND = "image_found"
    #: Not held, and the registry knows no image. Listed rather than hidden, so
    #: a curator sees what a Get cannot supply.
    NO_IMAGE = "no_image"


@dataclass(frozen=True, slots=True)
class TopicView:
    """The head of a Topic page: what the topic is, or why there is nothing to show."""

    state: TopicState
    #: A sentence for the curator when the state is not `KNOWN`.
    note: str | None = None
    known: RegistryTopic | None = None


@dataclass(frozen=True, slots=True)
class TopicWork:
    """One of a topic's works, with what the library holds of it."""

    work: RegistryTopicWork
    state: WorkState
    #: The library's works in circulation that are this one. Usually one;
    #: several when held works share a QID, which the page shows rather than hides.
    held: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class TopicWorksView:
    """*Representative works*: the most renowned first, or why there are none."""

    state: TopicState
    note: str | None = None
    works: Sequence[TopicWork] = ()


@dataclass(frozen=True, slots=True)
class TopicArtistsView:
    """*Artists*: the most renowned first, each marked where the library holds them."""

    state: TopicState
    note: str | None = None
    people: Sequence[RegistrySimilar] = ()
    #: The library's artist for each listed artist it holds, by QID.
    held: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TopicSearchView:
    """Topics a typed name finds, or why the search could not be made."""

    state: TopicState
    note: str | None = None
    topics: Sequence[RegistryTopic] = ()


class TopicService:
    """Ask the registry about a topic, and say what the library holds of it."""

    def __init__(self, store: CatalogueStore, registry: Registry | None) -> None:
        self._store = store
        self._registry = registry
        self._topics: Remembered[str, RegistryTopic] = Remembered()
        self._works: Remembered[str, tuple[RegistryTopicWork, ...]] = Remembered()
        self._artists: Remembered[str, tuple[RegistrySimilar, ...]] = Remembered()

    def topic(self, qid: str) -> TopicView:
        """What this item is as a topic: its name, description, kinds and, for a period, its years."""
        qid = checked_qid(qid)
        if self._registry is None:
            return TopicView(state=TopicState.NOT_CONFIGURED, note=TOPICS_NOT_CONFIGURED_NOTE)
        try:
            known = self._known(qid, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata about topic %s: %s", qid, exc)
            return TopicView(state=TopicState.UNAVAILABLE, note=UNAVAILABLE_NOTE)
        if known is None:
            return TopicView(state=TopicState.NOT_FOUND, note=_not_found(qid))
        return TopicView(state=TopicState.KNOWN, known=known)

    def works(self, qid: str) -> TopicWorksView:
        """The topic's most renowned works of visual art, each marked Held, Image found or no image known."""
        qid = checked_qid(qid)
        if self._registry is None:
            return TopicWorksView(state=TopicState.NOT_CONFIGURED, note=TOPICS_NOT_CONFIGURED_NOTE)
        registry = self._registry
        try:
            known = self._known(qid, registry)
            if known is None:
                return TopicWorksView(state=TopicState.NOT_FOUND, note=_not_found(qid))
            listed = self._works.get(qid)
            if listed is None:
                # Asked outside the memory's lock, as the Artist page's half is:
                # another page must not wait on this one's query.
                listed = tuple(registry.topic_works(known, limit=WORKS_SHOWN))
                self._works.put(qid, listed)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata for the works of topic %s: %s", qid, exc)
            return TopicWorksView(state=TopicState.UNAVAILABLE, note=UNAVAILABLE_NOTE)
        # "Held" means in circulation, as on the Artist page, so an archived
        # work is not marked.
        holdings = self._store.circulating_ids_by_qid()
        return TopicWorksView(
            state=TopicState.KNOWN,
            works=tuple(_marked(work, holdings.get(work.qid, ())) for work in listed),
        )

    def artists(self, qid: str) -> TopicArtistsView:
        """The topic's artists, the most renowned first, each marked where the library holds them."""
        qid = checked_qid(qid)
        if self._registry is None:
            return TopicArtistsView(state=TopicState.NOT_CONFIGURED, note=TOPICS_NOT_CONFIGURED_NOTE)
        registry = self._registry
        try:
            known = self._known(qid, registry)
            if known is None:
                return TopicArtistsView(state=TopicState.NOT_FOUND, note=_not_found(qid))
            people = self._artists.get(qid)
            if people is None:
                people = tuple(registry.topic_artists(known, limit=ARTISTS_SHOWN))
                self._artists.put(qid, people)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata for the artists of topic %s: %s", qid, exc)
            return TopicArtistsView(state=TopicState.UNAVAILABLE, note=UNAVAILABLE_NOTE)
        ours = artist_ids_by_qid(self._store)
        return TopicArtistsView(
            state=TopicState.KNOWN,
            people=people,
            held={person.qid: ours[person.qid] for person in people if person.qid in ours},
        )

    def named(self, text: str) -> TopicSearchView:
        """Topics the registry finds for a typed name: periods, movements, media, and subjects something depicts.

        Not remembered: a typeahead asks with every word, and few are asked twice.
        """
        wanted = text.strip()
        if self._registry is None:
            return TopicSearchView(state=TopicState.NOT_CONFIGURED, note=TOPICS_NOT_CONFIGURED_NOTE)
        if not wanted:
            return TopicSearchView(state=TopicState.KNOWN)
        try:
            found = tuple(self._registry.topics_named(wanted))
        except RegistryUnavailable as exc:
            log.warning("Could not search Wikidata for topics named %r: %s", wanted, exc)
            return TopicSearchView(state=TopicState.UNAVAILABLE, note=UNAVAILABLE_NOTE)
        return TopicSearchView(state=TopicState.KNOWN, topics=found)

    def _known(self, qid: str, registry: Registry) -> RegistryTopic | None:
        remembered = self._topics.get(qid)
        if remembered is not None:
            return remembered
        known = registry.topic(qid)
        if known is not None:
            # A missing item is not remembered: it can be created, and a curator
            # who mistyped will try again with the right one.
            self._topics.put(qid, known)
        return known


def _marked(work: RegistryTopicWork, held: Sequence[str]) -> TopicWork:
    if held:
        return TopicWork(work=work, state=WorkState.HELD, held=tuple(held))
    return TopicWork(work=work, state=WorkState.IMAGE_FOUND if work.image is not None else WorkState.NO_IMAGE)


def _not_found(qid: str) -> str:
    return f"Wikidata has no item {qid}. It may have been merged into another, or the address is mistyped."
