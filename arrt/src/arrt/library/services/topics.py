"""Topics as a registry knows them: a period, a movement, a subject or a medium.

The registry half of a Topic page (`build-plan-topics-and-destinations.md`):
what the topic is, the works it is known for, and its artists. Each is its own
call, as the Artist page's sections are, so a slow or failed one leaves the rest
of the page standing and says which it was.

**Kept per topic for a week, across restarts** (`persistence/kept.py`), as the
Artist page's sections are: a century's works took seven to twenty-six seconds
to ask for and some periods timed out (`wikidata-findings.md` § Topics), so a
topic asked once should not be slow again after a deploy. A failure is not
kept, and neither is an item the registry does not have, so the next visit asks
again.

**Held is the library's to say, and is said fresh each time.** The registry's
answer is kept; which of its works the library holds in circulation is
read from the catalogue on every call, so a work accepted a minute ago is
marked *Held* without forgetting the topic.

**The library's half asks no registry at all.** `index` and `page` read the
facet rows the topic sweep (`topic_sweep.py`) writes, so Library › Topics and a
Topic page's *In your library* draw at once, whatever Wikidata is doing; the
registry sections are asked for separately, as the Artist page's are.
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
    TopicKind,
)
from arrt.library.services.artists import REGISTRY_KEPT_FOR, artist_ids_by_qid
from arrt.library.services.remembered import REMEMBERED, checked_qid
from arrt.persistence.catalogue import CatalogueStore, TopicTally
from arrt.persistence.kept import JsonCodec, Kept, KeptAnswers
from arrt.persistence.records import ArtworkStatus, VocabularyKind

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

#: The facet kind each topic kind is recorded under. A period is an `era`, the
#: shared vocabulary's word for it; the other three are the same word.
FACET_KINDS: Final[Mapping[TopicKind, VocabularyKind]] = {
    TopicKind.PERIOD: VocabularyKind.ERA,
    TopicKind.MOVEMENT: VocabularyKind.MOVEMENT,
    TopicKind.SUBJECT: VocabularyKind.SUBJECT,
    TopicKind.MEDIUM: VocabularyKind.MEDIUM,
}

#: The order Library › Topics lists the kinds in: the owner's, period first.
INDEX_ORDER: Final[tuple[TopicKind, ...]] = (TopicKind.PERIOD, TopicKind.MOVEMENT, TopicKind.SUBJECT, TopicKind.MEDIUM)

#: Which topic kind a facet kind is, for the facets that are topics.
_TOPIC_KINDS: Final[Mapping[VocabularyKind, TopicKind]] = {facet: topic for topic, facet in FACET_KINDS.items()}


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
    #: The library's artist for each listed maker it holds, by QID, so a maker
    #: links to the library's own Artist page.
    artists: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TopicArtistsView:
    """*Artists*: whose works in the topic are most famous first, their own fame breaking ties, each marked if held."""

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


@dataclass(frozen=True, slots=True)
class HeldTopic:
    """A topic the library's works are in, and how many of them."""

    qid: str
    #: The registry's name for it, as the facet rows recorded it.
    label: str
    works: int


@dataclass(frozen=True, slots=True)
class TopicGroup:
    """Every topic of one kind the library's works are in, by name."""

    kind: TopicKind
    topics: Sequence[HeldTopic] = ()


@dataclass(frozen=True, slots=True)
class TopicIndex:
    """Library › Topics: every topic the library's works are in, grouped by kind, one group per kind."""

    #: `KNOWN` with a registry configured; `NOT_CONFIGURED` without one, when the
    #: groups hold whatever an earlier configuration recorded and nothing renews it.
    state: TopicState
    note: str | None = None
    groups: Sequence[TopicGroup] = ()


@dataclass(frozen=True, slots=True)
class TopicPage:
    """The library's half of a Topic page: the topic as the facets name it, and the works in it."""

    qid: str
    state: TopicState
    note: str | None = None
    #: The name the facet rows hold, or None where no work of the library's is in it.
    label: str | None = None
    #: The kinds the library's works carry it under, in `INDEX_ORDER`. Usually
    #: one; two where, say, a movement is also what a work is said to be of.
    kinds: tuple[TopicKind, ...] = ()
    #: The library's works in circulation in it, by title.
    work_ids: Sequence[str] = ()


class TopicService:
    """Ask the registry about a topic, and say what the library holds of it."""

    def __init__(self, store: CatalogueStore, registry: Registry | None, *, kept: KeptAnswers) -> None:
        self._store = store
        self._registry = registry
        self._topics: Kept[str, RegistryTopic] = kept.namespace(
            "registry.topic", codec=JsonCodec(RegistryTopic), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )
        self._works: Kept[str, tuple[RegistryTopicWork, ...]] = kept.namespace(
            "registry.topic_works",
            codec=JsonCodec(tuple[RegistryTopicWork, ...]),
            max_age=REGISTRY_KEPT_FOR,
            size=REMEMBERED,
        )
        # Named for the ranking: an answer kept under an earlier rule's name is
        # never read as this one's, and is thrown away when it ages out.
        self._named: Kept[str, tuple[RegistryTopic, ...]] = kept.namespace(
            "registry.topics_named",
            codec=JsonCodec(tuple[RegistryTopic, ...]),
            max_age=REGISTRY_KEPT_FOR,
            size=REMEMBERED,
        )
        self._artists: Kept[str, tuple[RegistrySimilar, ...]] = kept.namespace(
            "registry.topic_artists.by_fame",
            codec=JsonCodec(tuple[RegistrySimilar, ...]),
            max_age=REGISTRY_KEPT_FOR,
            size=REMEMBERED,
        )

    def index(self) -> TopicIndex:
        """Every topic the library's works in circulation are in, by kind, each with how many. No network."""
        state, note = self._configured()
        tallies = self._store.topic_tallies(status=ArtworkStatus.ACCEPTED)
        held: dict[TopicKind, list[HeldTopic]] = {kind: [] for kind in INDEX_ORDER}
        for tally in tallies:
            kind = _TOPIC_KINDS.get(tally.kind)
            if kind is not None:
                held[kind].append(HeldTopic(qid=tally.qid, label=tally.label, works=tally.works))
        return TopicIndex(
            state=state, note=note, groups=tuple(TopicGroup(kind=kind, topics=tuple(held[kind])) for kind in INDEX_ORDER)
        )

    def page(self, qid: str) -> TopicPage:
        """The topic as the library's facets name it, and its works in circulation. No network.

        A topic no held work is in answers with no label and no works, rather
        than refusing: a Topic page reached by search is ordinary, and its
        registry sections still have something to say.
        """
        qid = checked_qid(qid)
        state, note = self._configured()
        tallies = [
            tally for tally in self._store.topic_tallies(status=ArtworkStatus.ACCEPTED, qid=qid) if tally.kind in _TOPIC_KINDS
        ]
        kinds = {_TOPIC_KINDS[tally.kind] for tally in tallies}
        return TopicPage(
            qid=qid,
            state=state,
            note=note,
            label=_label(tallies),
            kinds=tuple(kind for kind in INDEX_ORDER if kind in kinds),
            work_ids=tuple(self._store.works_with_topic(qid, status=ArtworkStatus.ACCEPTED, kinds=tuple(FACET_KINDS.values()))),
        )

    def _configured(self) -> tuple[TopicState, str | None]:
        if self._registry is None:
            return TopicState.NOT_CONFIGURED, TOPICS_NOT_CONFIGURED_NOTE
        return TopicState.KNOWN, None

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
        ours = artist_ids_by_qid(self._store)
        makers = {creator.qid for work in listed for creator in work.creators}
        return TopicWorksView(
            state=TopicState.KNOWN,
            works=tuple(_marked(work, holdings.get(work.qid, ())) for work in listed),
            artists={qid: ours[qid] for qid in sorted(makers) if qid in ours},
        )

    def artists(self, qid: str) -> TopicArtistsView:
        """The topic's artists, the fame of their works in it first, their own breaking ties, each marked if held."""
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

        Kept for a week by what was typed, ignoring case, as the registry's own
        search is: the top bar asks this beside that search on every word, and
        Wikidata has refused a run of questions before (`wikidata-findings.md`).
        """
        wanted = text.strip()
        if self._registry is None:
            return TopicSearchView(state=TopicState.NOT_CONFIGURED, note=TOPICS_NOT_CONFIGURED_NOTE)
        if not wanted:
            return TopicSearchView(state=TopicState.KNOWN)
        key = wanted.casefold()
        found = self._named.get(key)
        if found is None:
            try:
                found = tuple(self._registry.topics_named(wanted))
            except RegistryUnavailable as exc:
                log.warning("Could not search Wikidata for topics named %r: %s", wanted, exc)
                return TopicSearchView(state=TopicState.UNAVAILABLE, note=UNAVAILABLE_NOTE)
            self._named.put(key, found)
        return TopicSearchView(state=TopicState.KNOWN, topics=found)

    def _known(self, qid: str, registry: Registry) -> RegistryTopic | None:
        kept = self._topics.get(qid)
        if kept is not None:
            return kept
        known = registry.topic(qid)
        if known is not None:
            # A missing item is not kept: it can be created, and a curator
            # who mistyped will try again with the right one.
            self._topics.put(qid, known)
        return known


def _marked(work: RegistryTopicWork, held: Sequence[str]) -> TopicWork:
    if held:
        return TopicWork(work=work, state=WorkState.HELD, held=tuple(held))
    return TopicWork(work=work, state=WorkState.IMAGE_FOUND if work.image is not None else WorkState.NO_IMAGE)


def _label(tallies: Sequence[TopicTally]) -> str | None:
    """One name for the topic where its rows hold more than one: the one most works carry, then the first by name."""
    if not tallies:
        return None
    return min(tallies, key=lambda tally: (-tally.works, tally.label.casefold(), tally.label)).label


def _not_found(qid: str) -> str:
    return f"Wikidata has no item {qid}. It may have been merged into another, or the address is mistyped."
