"""Public registries of who made what, behind one narrow seam.

Wikidata is the only one today (`wikidata-findings.md`). What the Library asks a
registry is small and stated as data: which items carry this museum identifier,
who created these items, and which people go by this name. Judging whether an
answer identifies a held work or artist is the identity service's job
(`library/services/identity.py`), so a second registry would answer the same
three questions and inherit the same judgement.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from arrt.library.registry.identifiers import IdentifierScheme


@dataclass(frozen=True, slots=True)
class RegistryPerson:
    """A person a registry knows by a name, with what can tell two of them apart."""

    qid: str
    label: str
    #: Birth and death years, where the registry records them. A year rather than
    #: a date, because the library's own records hold years.
    born: int | None = None
    died: int | None = None


class RegistryUnavailable(Exception):
    """The registry could not be asked, or did not answer in the shape it promises.

    Distinct from an answer of "nothing": a matcher that read an outage as no
    match would record nothing and look finished.
    """


class Registry(Protocol):
    """The three questions the Library asks a registry."""

    def works_by_identifier(self, scheme: IdentifierScheme, values: Sequence[str]) -> Mapping[str, frozenset[str]]:
        """Every item carrying each museum identifier, keyed by the identifier. An unknown one is absent."""
        ...

    def creators_of(self, work_qids: Sequence[str]) -> Mapping[str, frozenset[str]]:
        """Each item's recorded creators, keyed by the item. An item with none is absent."""
        ...

    def people_named(self, name: str) -> Sequence[RegistryPerson]:
        """People the registry's own search finds for this name who made something or work in the visual arts."""
        ...
