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
    description: RegistryText | None = None
    movements: tuple[RegistryText, ...] = ()
    #: The most renowned first, capped; `works_total` is how many there are.
    works: tuple[RegistryWorkEntry, ...] = ()
    works_total: int = 0
    holdings: tuple[RegistryHolding, ...] = ()


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
