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
from typing import Final, Protocol

from arrt.library.registry.identifiers import IdentifierScheme

#: A Wikidata item id, as the service writes it and as the library stores it. One
#: definition, because the client relies on it to keep an id from closing a query
#: and the identity service to refuse a URL pasted where an id belongs.
QID: Final[re.Pattern[str]] = re.compile(r"^Q[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class RegistryPerson:
    """A person a registry knows by a name, with what can tell two of them apart."""

    qid: str
    label: str
    #: Birth and death years, where the registry records them. A year rather than
    #: a date, because the library's own records hold years.
    born: int | None = None
    died: int | None = None


@dataclass(frozen=True, slots=True)
class RegistryWorkEntry:
    """One work a registry lists for an artist, as the Artist page shows it."""

    qid: str
    title: str
    #: How many Wikipedias cover the work: renown, as the page sorts by it.
    sitelinks: int
    year: int | None = None
    #: A free image of it, as an `https://commons.wikimedia.org/wiki/Special:FilePath/…`
    #: URL and nothing else: anything else the registry returns is dropped, because
    #: it becomes an `img` source in the curator's browser.
    image: str | None = None


@dataclass(frozen=True, slots=True)
class RegistryHolding:
    """A collection holding the artist's work, and how many."""

    qid: str
    name: str
    works: int


@dataclass(frozen=True, slots=True)
class RegistryArtist:
    """What a registry knows about one artist, for the Artist page.

    Every string here is registry text: written by anyone, rendered as text and
    never as markup.
    """

    qid: str
    description: str | None = None
    movements: tuple[str, ...] = ()
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

    def works_by_identifier(self, scheme: IdentifierScheme, values: Sequence[str]) -> Mapping[str, frozenset[str]]:
        """Every item carrying each museum identifier, keyed by the identifier. An unknown one is absent."""
        ...

    def creators_of(self, work_qids: Sequence[str]) -> Mapping[str, frozenset[str]]:
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
