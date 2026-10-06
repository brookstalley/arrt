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
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields, replace
from typing import Final

from arrt.library.registry import QID, Registry, RegistryPerson, RegistryUnavailable
from arrt.library.registry.identifiers import IdentifierScheme, museum_identifier
from arrt.persistence.catalogue import CatalogueStore, WorkQuery
from arrt.persistence.records import Artist, Artwork, IdentitySetBy
from arrt.services.errors import ServiceError
from arrt.services.store import store_write

log = logging.getLogger(__name__)


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

    def __init__(
        self, store: CatalogueStore, registry: Registry | None, *, on_changed: Callable[[], None] = lambda: None
    ) -> None:
        self._store = store
        self._registry = registry
        #: Called after any QID is set, cleared or matched: what a work's topics
        #: come from has changed, and the topic sweep asks again.
        self._on_changed = on_changed

    # -- by hand --------------------------------------------------------------

    # Every rule here binds both surfaces: the browser's control shows the item
    # before offering to store it and checks only that what was typed is an item
    # id, so a click and an agent's `art_catalogue` action get the same
    # refusals, from here.

    def set_work_identity(self, artwork_id: str, qid: str | None) -> Artwork:
        """Set or clear a work's QID as the curator. Clearing records "there is none", which the matcher respects.

        A QID must name an item the registry has, when one is configured. Two
        works may share one: a duplicate the Artist page shows as *Held ×2*.
        """
        artwork = self._store.get_artwork(artwork_id)
        if artwork is None:
            raise ServiceError(f"No artwork with id {artwork_id!r} is in the catalogue.")
        checked = self._existing(_require_qid(qid))
        updated = replace(artwork, wikidata_qid=checked, wikidata_qid_set_by=IdentitySetBy.CURATOR)
        store_write(self._store.update_artwork, updated)
        self._on_changed()
        return updated

    def set_artist_identity(self, artist_id: str, qid: str | None) -> Artist:
        """Set or clear an artist's QID as the curator. Clearing records "there is none", which the matcher respects.

        A QID must name an item the registry has, when one is configured, and no
        other artist in the catalogue may carry it: two artists with one item
        would collapse into one on every page that finds an artist by QID.
        """
        artist = self._store.get_artist(artist_id)
        if artist is None:
            raise ServiceError(f"No artist with id {artist_id!r} is in the catalogue.")
        wanted = _require_qid(qid)
        if wanted is not None:
            other = next((a for a in self._store.list_artists() if a.wikidata_qid == wanted and a.id != artist_id), None)
            if other is not None:
                raise ServiceError(f"{other.name} already has {wanted}. Correct that artist first, or merge the two.")
        updated = replace(artist, wikidata_qid=self._existing(wanted), wikidata_qid_set_by=IdentitySetBy.CURATOR)
        store_write(self._store.update_artist, updated)
        self._on_changed()
        return updated

    def _existing(self, qid: str | None) -> str | None:
        """`qid`, once the registry has said it names something; unchecked when no registry is configured.

        With no registry the curator's word stands: there is nothing to check it
        against, and refusing would leave no way to record a known identity. A
        registry that cannot be asked is a refusal, not a pass, because an
        unchecked id is how a typo becomes an identity.
        """
        if qid is None or self._registry is None:
            return qid
        try:
            label = self._registry.label_of(qid)
        except RegistryUnavailable as exc:
            raise ServiceError(f"Wikidata could not be asked, so {qid} could not be checked. Try again.") from exc
        if label is None:
            raise ServiceError(f"Wikidata has no item {qid}.")
        return qid

    # -- by the matcher -------------------------------------------------------

    def match(self) -> IdentityReport:
        """Fill every identity nobody has set that the registry answers unambiguously."""
        registry = self._registry
        if registry is None:
            raise ServiceError("No registry is configured, so nothing can be matched. Set WIKIDATA_USER_AGENT.")
        work_report = self._match_works(registry, [work for work in self._all_works() if open_to_match(work)])
        # Read again, so the artists see the works this pass just identified.
        artist_report = self._match_artists(registry, self._all_works())
        # Each half fills only its own fields, so every field the works half set
        # (its name begins `works_`) is taken from it, whatever fields are added.
        report = replace(
            artist_report,
            **{spec.name: getattr(work_report, spec.name) for spec in fields(IdentityReport) if spec.name.startswith("works_")},
        )
        if report.works_matched or report.artists_matched:
            self._on_changed()
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
        artists = [artist for artist in self._store.list_artists() if open_to_match(artist)]
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
        # One item, one artist: a QID another catalogue artist already carries
        # is reported as ambiguous rather than given twice.
        taken = {other.wikidata_qid: other.id for other in self._store.list_artists() if other.wikidata_qid}
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
                    if (not pinned or person.qid in pinned) and years_agree(artist, person)
                ]
                if len(candidates) != 1:
                    (ambiguous if candidates else unknown).append(artist.name)
                    continue
                qid = candidates[0].qid
            if taken.get(qid, artist.id) != artist.id:
                ambiguous.append(artist.name)
                continue
            taken[qid] = artist.id
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


def open_to_match(record: Artwork | Artist) -> bool:
    """Whether the matcher may fill this identity: none known, and the curator has not spoken."""
    return record.wikidata_qid is None and record.wikidata_qid_set_by is not IdentitySetBy.CURATOR


def years_agree(artist: Artist, person: RegistryPerson) -> bool:
    """At least one year compared, and every year compared within tolerance."""
    pairs = [(mine, theirs) for mine, theirs in ((artist.born, person.born), (artist.died, person.died)) if mine and theirs]
    return bool(pairs) and all(abs(mine - theirs) <= YEAR_TOLERANCE for mine, theirs in pairs)


def _require_qid(qid: str | None) -> str | None:
    if qid is None:
        return None
    stripped = qid.strip().upper()
    if not QID.match(stripped):
        raise ServiceError(f"{qid!r} is not a Wikidata item id. An item id is Q followed by digits, as in Q160149.")
    return stripped
