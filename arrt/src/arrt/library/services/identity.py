"""Which registry item each held work and artist is: matched once, corrected by hand.

The owner's ruling 7, and the rules are `data-model.md` § Artwork, Registry
identity, measured into shape by `wikidata-findings.md`:

- **A work is matched only through a museum identifier** its sources carry, and
  only when every identifier it carries names the same one item.
- **An artist is the one creator of their matched works**, or failing that the
  one person a name search finds whose birth and death years agree with the
  library's. A name alone is never enough: a search for *Moche*, a culture, finds
  exactly one painter born in 1633.
- **The matcher fills only what nobody has set.** A curator's QID, and a curator's
  "there is none", both stand, so a correction survives every later pass and a
  second pass over an unchanged catalogue writes nothing.

A wrong QID marks the wrong work *Held* on an artist's page and is worse than
none, so every rule above leans towards storing nothing.
"""

import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Final

from arrt.library.registry import Registry, RegistryPerson
from arrt.library.registry.identifiers import IdentifierScheme, museum_identifier
from arrt.persistence.catalogue import CatalogueStore, WorkQuery
from arrt.persistence.records import Artist, Artwork, IdentitySetBy
from arrt.services.errors import ServiceError
from arrt.services.store import store_write

log = logging.getLogger(__name__)

#: A Wikidata item id.
_QID: Final[re.Pattern[str]] = re.compile(r"^Q[1-9][0-9]*$")

#: How far a registry's year may sit from the library's and still agree. One,
#: because a death recorded in early January by one source is the previous year
#: in another's reckoning, and life dates are what tell two namesakes apart.
YEAR_TOLERANCE: Final[int] = 1

#: Works read per page while walking the catalogue.
_PAGE: Final[int] = 500


@dataclass(frozen=True, slots=True)
class IdentityReport:
    """What one matching pass found, worst news first when it is printed."""

    works_matched: int = 0
    #: Titles whose identifiers named more than one item.
    works_ambiguous: Sequence[str] = field(default_factory=tuple)
    #: Works whose identifiers the registry does not know.
    works_unknown: int = 0
    #: Works whose sources carry no identifier this knows, so nothing was asked.
    works_without_identifier: int = 0
    artists_matched: int = 0
    #: Names with more than one candidate left after every rule.
    artists_ambiguous: Sequence[str] = field(default_factory=tuple)
    #: Names the library holds no birth or death year for and no matched work
    #: pins, so a name search could not be trusted.
    artists_undated: Sequence[str] = field(default_factory=tuple)
    #: Names nothing in the registry matched.
    artists_unknown: Sequence[str] = field(default_factory=tuple)


class IdentityService:
    """Match the catalogue to a registry, and let the curator say otherwise."""

    def __init__(self, store: CatalogueStore, registry: Registry | None) -> None:
        self._store = store
        self._registry = registry

    # -- by hand --------------------------------------------------------------

    def set_work_identity(self, artwork_id: str, qid: str | None) -> Artwork:
        """Set or clear a work's QID as the curator. Clearing records "there is none", which the matcher respects."""
        artwork = self._store.get_artwork(artwork_id)
        if artwork is None:
            raise ServiceError(f"No artwork with id {artwork_id!r} is in the catalogue.")
        updated = replace(artwork, wikidata_qid=_require_qid(qid), wikidata_qid_set_by=IdentitySetBy.CURATOR)
        store_write(self._store.update_artwork, updated)
        return updated

    def set_artist_identity(self, artist_id: str, qid: str | None) -> Artist:
        """Set or clear an artist's QID as the curator. Clearing records "there is none", which the matcher respects."""
        artist = self._store.get_artist(artist_id)
        if artist is None:
            raise ServiceError(f"No artist with id {artist_id!r} is in the catalogue.")
        updated = replace(artist, wikidata_qid=_require_qid(qid), wikidata_qid_set_by=IdentitySetBy.CURATOR)
        store_write(self._store.update_artist, updated)
        return updated

    # -- by the matcher -------------------------------------------------------

    def match(self) -> IdentityReport:
        """Fill every identity nobody has set that the registry answers unambiguously."""
        registry = self._registry
        if registry is None:
            raise ServiceError("No registry is configured, so nothing can be matched. Set WIKIDATA_USER_AGENT.")
        work_report = self._match_works(registry, [work for work in self._all_works() if _open(work)])
        # Read again, so the artists see the works this pass just identified.
        artist_report = self._match_artists(registry, self._all_works())
        report = replace(artist_report, **{name: getattr(work_report, name) for name in _WORK_FIELDS})
        log.info(
            "Matched %d work(s) and %d artist(s) to Wikidata; %d work(s) and %d artist(s) ambiguous.",
            report.works_matched,
            report.artists_matched,
            len(report.works_ambiguous),
            len(report.artists_ambiguous),
        )
        return report

    def _match_works(self, registry: Registry, works: Sequence[Artwork]) -> IdentityReport:
        asked: dict[str, set[tuple[IdentifierScheme, str]]] = {}
        for work in works:
            identifiers = {found for source in self._store.list_sources(work.id) if (found := museum_identifier(source.url))}
            if identifiers:
                asked[work.id] = identifiers
        by_scheme: dict[IdentifierScheme, set[str]] = defaultdict(set)
        for identifiers in asked.values():
            for scheme, value in identifiers:
                by_scheme[scheme].add(value)
        answers = {scheme: registry.works_by_identifier(scheme, sorted(values)) for scheme, values in by_scheme.items()}

        matched = unknown = 0
        ambiguous: list[str] = []
        with self._store.transaction():
            for work in works:
                if work.id not in asked:
                    continue
                items = set().union(*(answers[scheme].get(value, frozenset()) for scheme, value in asked[work.id]))
                if len(items) == 1:
                    (qid,) = items
                    store_write(
                        self._store.update_artwork,
                        replace(work, wikidata_qid=qid, wikidata_qid_set_by=IdentitySetBy.MATCHED),
                    )
                    matched += 1
                elif items:
                    ambiguous.append(work.title)
                else:
                    unknown += 1
        return IdentityReport(
            works_matched=matched,
            works_ambiguous=tuple(ambiguous),
            works_unknown=unknown,
            works_without_identifier=len(works) - len(asked),
        )

    def _match_artists(self, registry: Registry, works: Sequence[Artwork]) -> IdentityReport:
        artists = [artist for artist in self._store.list_artists() if _open(artist)]
        identified: dict[str, list[str]] = defaultdict(list)
        for work in works:
            if work.artist_id and work.wikidata_qid:
                identified[work.artist_id].append(work.wikidata_qid)
        wanted = sorted({qid for artist in artists for qid in identified.get(artist.id, ())})
        creators = registry.creators_of(wanted) if wanted else {}

        matched = 0
        ambiguous: list[str] = []
        undated: list[str] = []
        unknown: list[str] = []
        for artist in artists:
            pinned = set().union(*(creators.get(qid, frozenset()) for qid in identified.get(artist.id, ())))
            if len(pinned) == 1:
                (qid,) = pinned
            else:
                if artist.born is None and artist.died is None:
                    undated.append(artist.name)
                    continue
                candidates = [
                    person
                    for person in registry.people_named(artist.name)
                    if (not pinned or person.qid in pinned) and _years_agree(artist, person)
                ]
                if len(candidates) != 1:
                    (ambiguous if candidates else unknown).append(artist.name)
                    continue
                qid = candidates[0].qid
            # One write per artist rather than one transaction for the pass: the
            # name searches between them are network calls, and the store's lock
            # would hold every other request back for as long as they took.
            store_write(self._store.update_artist, replace(artist, wikidata_qid=qid, wikidata_qid_set_by=IdentitySetBy.MATCHED))
            matched += 1
        return IdentityReport(
            artists_matched=matched,
            artists_ambiguous=tuple(ambiguous),
            artists_undated=tuple(undated),
            artists_unknown=tuple(unknown),
        )

    def _all_works(self) -> list[Artwork]:
        works: list[Artwork] = []
        while True:
            page = self._store.list_artworks(WorkQuery(), limit=_PAGE, offset=len(works))
            works.extend(page.artworks)
            if len(works) >= page.total or not page.artworks:
                return works


_WORK_FIELDS: Final[tuple[str, ...]] = ("works_matched", "works_ambiguous", "works_unknown", "works_without_identifier")


def _open(record: Artwork | Artist) -> bool:
    """Whether the matcher may fill this identity: none known, and the curator has not spoken."""
    return record.wikidata_qid is None and record.wikidata_qid_set_by is not IdentitySetBy.CURATOR


def _years_agree(artist: Artist, person: RegistryPerson) -> bool:
    """At least one year compared, and every year compared within tolerance."""
    pairs = [(mine, theirs) for mine, theirs in ((artist.born, person.born), (artist.died, person.died)) if mine and theirs]
    return bool(pairs) and all(abs(mine - theirs) <= YEAR_TOLERANCE for mine, theirs in pairs)


def _require_qid(qid: str | None) -> str | None:
    if qid is None:
        return None
    stripped = qid.strip().upper()
    if not _QID.match(stripped):
        raise ServiceError(f"{qid!r} is not a Wikidata item id. An item id is Q followed by digits, as in Q160149.")
    return stripped
