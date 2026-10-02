"""Public registries of who made what, behind one narrow seam.

Wikidata is the only one today (`wikidata-findings.md`). What the Library asks a
registry is small and stated as data: which items carry this museum identifier,
who created these items, which people go by this name, and what is known about
one artist. Judging whether an answer identifies a held work or artist is the
identity service's job (`library/services/identity.py`), so a second registry
would answer the same questions and inherit the same judgement.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, NewType, Protocol

from arrt.library.registry.identifiers import IdentifierScheme

#: A Wikidata item id, as the service writes it and as the library stores it. One
#: definition, because the client relies on it to keep an id from closing a query
#: and the identity service to refuse a URL pasted where an id belongs.
QID: Final[re.Pattern[str]] = re.compile(r"^Q[1-9][0-9]*$")

# What each string a registry hands over is, so that none is a plain `str`
# (`security-model.md` § Direction, held by `tests/unit/test_registry_strings.py`).
# A new field has to pick one, and only a Commons file may become a URL.

#: An item id, matching `QID`.
ItemId = NewType("ItemId", str)

#: Words a registry wrote: a name, a title, a description. Anyone can edit a
#: registry, so these reach the page as text and never as markup.
RegistryText = NewType("RegistryText", str)

#: A museum's identifier for a work, and always one the caller asked about: the
#: registry's answer names it, so the client keeps only the values it was given.
MuseumIdentifier = NewType("MuseumIdentifier", str)

#: A free image, as an `https://commons.wikimedia.org/wiki/Special:FilePath/…` URL
#: and nothing else. It becomes an `img` source in the curator's browser, so the
#: client drops anything else the registry offers as an image.
CommonsFile = NewType("CommonsFile", str)


@dataclass(frozen=True, slots=True)
class RegistryPerson:
    """A person a registry knows by a name, with what can tell two of them apart."""

    qid: ItemId
    label: RegistryText
    #: Birth and death years, where the registry records them. A year rather than
    #: a date, because the library's own records hold years.
    born: int | None = None
    died: int | None = None


@dataclass(frozen=True, slots=True)
class RegistryWorkEntry:
    """One work a registry lists for an artist, as the Artist page shows it."""

    qid: ItemId
    title: RegistryText
    #: How many Wikipedias cover the work: renown, as the page sorts by it.
    sitelinks: int
    year: int | None = None
    #: A free image of it, where the registry has one.
    image: CommonsFile | None = None


@dataclass(frozen=True, slots=True)
class RegistryHolding:
    """A collection holding the artist's work, and how many."""

    qid: ItemId
    name: RegistryText
    works: int


@dataclass(frozen=True, slots=True)
class RegistryArtist:
    """What a registry knows about one artist, for the Artist page.

    Every string here is registry text: written by anyone, rendered as text and
    never as markup.
    """

    qid: ItemId
    #: The registry's name for them, or the QID itself where it has no English or
    #: language-neutral one (the label service's answer, kept as given).
    name: RegistryText | None = None
    born: int | None = None
    died: int | None = None
    description: RegistryText | None = None
    movements: tuple[RegistryText, ...] = ()
    #: The most renowned first, capped; `works_total` is how many there are.
    works: tuple[RegistryWorkEntry, ...] = ()
    works_total: int = 0
    holdings: tuple[RegistryHolding, ...] = ()


@dataclass(frozen=True, slots=True)
class RegistryCreator:
    """Someone a registry records as having made a work."""

    qid: ItemId
    name: RegistryText


@dataclass(frozen=True, slots=True)
class RegistryHolder:
    """A collection a registry says holds a work, and its number for it there."""

    qid: ItemId
    name: RegistryText
    #: The collection's inventory or accession number, where the registry pairs
    #: one with this collection. A work held in two places has two.
    inventory: RegistryText | None = None


@dataclass(frozen=True, slots=True)
class RegistryWork:
    """What a registry knows about one work, for the page of a work the library may not hold."""

    qid: ItemId
    #: The label service's answer: the QID itself where there is no readable title.
    title: RegistryText
    sitelinks: int
    year: int | None = None
    image: CommonsFile | None = None
    creators: tuple[RegistryCreator, ...] = ()
    media: tuple[RegistryText, ...] = ()
    holders: tuple[RegistryHolder, ...] = ()


@dataclass(frozen=True, slots=True)
class RegistryWorkMatch:
    """A work a registry's search found, with what a list of matches shows of it."""

    qid: ItemId
    title: RegistryText
    sitelinks: int
    image: CommonsFile | None = None
    #: Its first recorded creator, where it has one: what tells two *The Kiss*es apart.
    creator: RegistryCreator | None = None


@dataclass(frozen=True, slots=True)
class RegistrySimilar:
    """An artist sharing a movement with another, and how much of their work can be seen."""

    qid: ItemId
    name: RegistryText
    sitelinks: int
    born: int | None = None
    died: int | None = None
    #: Their works with a free image: what tells a curator whether anyone can
    #: supply them before they commit to the artist (Pollock has none).
    images: int = 0


class RegistryUnavailable(Exception):
    """The registry could not be asked, or did not answer in the shape it promises.

    Distinct from an answer of "nothing": a matcher that read an outage as no
    match would record nothing and look finished.
    """


class Registry(Protocol):
    """The questions the Library asks a registry."""

    def works_by_identifier(
        self, scheme: IdentifierScheme, values: Sequence[str]
    ) -> Mapping[MuseumIdentifier, frozenset[ItemId]]:
        """Every item carrying each museum identifier, keyed by the identifier. An unknown one is absent."""
        ...

    def creators_of(self, work_qids: Sequence[str]) -> Mapping[ItemId, frozenset[ItemId]]:
        """Each item's recorded creators, keyed by the item. An item with none is absent."""
        ...

    def people_named(self, name: str) -> Sequence[RegistryPerson]:
        """People the registry's own search finds for this name who made something or work in the visual arts."""
        ...

    def artist(self, qid: str, *, works: int, holdings: int, include: Sequence[str] = ()) -> RegistryArtist:
        """What the registry knows about this person: the `works` most renowned, the `holdings` largest collections.

        `include` names works to list whatever their renown (the ones the library
        holds), after the most renowned and in the same shape.
        """
        ...

    def work(self, qid: str) -> RegistryWork | None:
        """What the registry knows about this work, or None when it has no such item."""
        ...

    def similar_to(self, qid: str, *, limit: int) -> Sequence[RegistrySimilar]:
        """Visual artists sharing a movement with this one, the most renowned first."""
        ...

    def works_matching(self, words: Sequence[str], *, prefix: bool, limit: int) -> Sequence[RegistryWorkMatch]:
        """Works of visual art whose text matches every word, the most renowned first.

        `prefix` lets the last word be the start of one, as a curator mid-word
        types it. The words are plain words: the caller strips anything the
        registry's search would read as an operator.
        """
        ...
