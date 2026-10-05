"""One work as a registry knows it, for the page of a work the library may not hold.

Ruling 2 puts the library and the registry in one world: a work Wikidata lists
has a page here whether or not the library holds it, instead of a link out. The
page asks this by QID. A QID the library holds is answered with the works that
are it, so the page can send the curator to the library's own; one it does not
is answered with what the registry says, and with the library's artist for any
creator it holds, so the page can link there rather than out.

**Kept per work for a week, across restarts**, as the Artist page's half is: a
work's facts change rarely and a curator going back and forth between a work
and its artist should not wait on the network each time. A failure is not
kept, so the next visit asks again.

**Its picture's pixel size is asked of the registry too, and judged against
the wall** by `assess_display_fit`, the function the review grid's verdict
comes from, so the page and the review cannot disagree about one file. The
size is kept per file, as the work is per QID. Only Commons knows it, and
Commons can be down while the query service answers, so a failure to ask
leaves the work known and its size unknown, and is not kept. The verdict is
on the file as Commons holds it: a Get of a file wider than Commons' widest
rendering fetches that rendering, which on a panel no wider than it judges
the same. A work the library holds is not asked about: its page goes to the
library's own, and should not wait on Commons first.

**The work's size is checked for plausibility before the page shows it**
(`plausible_size`), as the owner ruled for anything that reads a size from the
registry (`procurement-corpus.md` § Gaps, 4): Wikidata holds sizes swapped,
wrong and mis-scaled. A size that fails is unknown, not shown with a doubt.
"""

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from arrt.library.registry import CommonsFile, Registry, RegistryImageSize, RegistryUnavailable, RegistryWork
from arrt.library.services.artists import REGISTRY_KEPT_FOR, WantedItems, artist_ids_by_qid
from arrt.library.services.display_fit import ArtworkBox, FitAssessment, assess_display_fit
from arrt.library.services.remembered import NOT_CONFIGURED_NOTE, REMEMBERED, checked_qid
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.kept import JsonCodec, Kept, KeptAnswers

log = logging.getLogger(__name__)

#: How far a work's shape (height over width) may differ from its picture's
#: before the size is doubted, as a factor either way. Measured 2026-10-05: 14
#: well-recorded works, a photograph with its frame among them, were within
#: 1.034; the corpus's two known-bad sizes were 2.27 (*Whaam!*, row 33) and about
#: 100 (*Tête Dada*, row 12) off. A picture that is a detail or an installation
#: view fails too, which costs a true size its showing, not a wrong one.
SHAPE_TOLERANCE: Final[float] = 1.25

#: The sides a work can have, in centimetres: a miniature's half centimetre to a
#: panorama's 120 m (the Racławice Panorama is 114 m long).
SMALLEST_CM: Final[float] = 0.5
LARGEST_CM: Final[float] = 12_000.0

#: How much longer than wide a work can be, either way. A Chinese handscroll
#: runs to about 21 : 1; *Tête Dada* as Wikidata records it is 210 : 1.
MOST_ELONGATED: Final[float] = 50.0


class RegistryWorkState(StrEnum):
    """Why a registry work's page says what it says."""

    #: The registry answered with the work.
    KNOWN = "known"
    #: The registry was asked and has no such item.
    NOT_FOUND = "not_found"
    #: No registry is configured (`WIKIDATA_USER_AGENT` unset).
    NOT_CONFIGURED = "not_configured"
    #: The registry was asked and could not answer.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RegistryWorkView:
    """A registry work's page: the work, or why there is none, and what the library holds of it."""

    state: RegistryWorkState
    #: A sentence for the curator when the state is not `KNOWN`.
    note: str | None = None
    known: RegistryWork | None = None
    #: The library's works in circulation that are this one, by QID. Answered
    #: whatever the registry is doing, because it is the library's to say.
    held: Sequence[str] = ()
    #: A wanted work names this item. Answered whatever the registry is doing,
    #: as `held` is, because it is the library's to say.
    wanted: bool = False
    #: The library's artist for each creator it holds, by the creator's QID.
    artists: Mapping[str, str] = field(default_factory=dict)
    #: The work's own size, where the registry gives it and it is plausible
    #: (`plausible_size`): what the page may show, unlike `known`'s raw values.
    height_cm: float | None = None
    width_cm: float | None = None
    #: The pixel size of the work's picture, where it has one and Commons said.
    image_size: RegistryImageSize | None = None
    #: How that picture would meet this deployment's wall, beside its size.
    fit: FitAssessment | None = None


class RegistryWorkService:
    """Ask the registry about one work, and say what the library holds of it."""

    def __init__(
        self, store: CatalogueStore, registry: Registry | None, *, kept: KeptAnswers, wanted: WantedItems, box: ArtworkBox
    ) -> None:
        self._store = store
        self._registry = registry
        self._wanted = wanted
        self._box = box
        self._kept: Kept[str, RegistryWork] = kept.namespace(
            "registry.work", codec=JsonCodec(RegistryWork), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )
        self._sizes: Kept[str, RegistryImageSize] = kept.namespace(
            "registry.image_size", codec=JsonCodec(RegistryImageSize), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )

    def view(self, qid: str) -> RegistryWorkView:
        checked_qid(qid)
        held = tuple(self._store.circulating_ids_by_qid().get(qid, ()))
        wanted = qid in self._wanted.wanted_qids()
        if self._registry is None:
            return RegistryWorkView(
                state=RegistryWorkState.NOT_CONFIGURED,
                note=NOT_CONFIGURED_NOTE,
                held=held,
                wanted=wanted,
            )
        try:
            known = self._known(qid, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata about work %s: %s", qid, exc)
            return RegistryWorkView(
                state=RegistryWorkState.UNAVAILABLE,
                note="Wikidata could not be asked just now. Try again later.",
                held=held,
                wanted=wanted,
            )
        if known is None:
            return RegistryWorkView(
                state=RegistryWorkState.NOT_FOUND,
                note=f"Wikidata has no item {qid}. It may have been merged into another, or the address is mistyped.",
                held=held,
                wanted=wanted,
            )
        ours = artist_ids_by_qid(self._store)
        size = None if known.image is None or held else self._size(known.image, self._registry)
        height_cm, width_cm = plausible_size(known.height_cm, known.width_cm, size)
        if (height_cm, width_cm) != (known.height_cm, known.width_cm):
            log.info(
                "an implausible size from Wikidata is treated as unknown",
                extra={
                    "event": "registry.size_implausible",
                    "qid": qid,
                    "height_cm": known.height_cm,
                    "width_cm": known.width_cm,
                },
            )
        return RegistryWorkView(
            state=RegistryWorkState.KNOWN,
            known=known,
            held=held,
            wanted=wanted,
            artists={creator.qid: ours[creator.qid] for creator in known.creators if creator.qid in ours},
            height_cm=height_cm,
            width_cm=width_cm,
            image_size=size,
            fit=None if size is None else assess_display_fit(width=size.width, height=size.height, box=self._box),
        )

    def _size(self, image: CommonsFile, registry: Registry) -> RegistryImageSize | None:
        kept = self._sizes.get(image)
        if kept is not None:
            return kept
        try:
            size = registry.image_size(image)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Commons how big %s is: %s", image, exc)
            return None
        if size is not None:
            # A missing file is not kept, as a missing item is not: it can be uploaded.
            self._sizes.put(image, size)
        return size

    def _known(self, qid: str, registry: Registry) -> RegistryWork | None:
        kept = self._kept.get(qid)
        if kept is not None:
            return kept
        # Asked between `get` and `put`, under no lock, as the Artist page's half
        # is: another page must not wait on this one's query.
        known = registry.work(qid)
        if known is None:
            # Not kept either: an item can be created, and a curator who
            # mistyped will try again with the right one.
            return None
        self._kept.put(qid, known)
        return known


def plausible_size(
    height_cm: float | None, width_cm: float | None, picture: RegistryImageSize | None
) -> tuple[float | None, float | None]:
    """A registry's size for a work, or `(None, None)` when it is not believable.

    Each side must be one a work can have (`SMALLEST_CM`, `LARGEST_CM`); with both,
    the work no more elongated than any is (`MOST_ELONGATED`), and, where its
    picture's size is known, its shape that picture's within `SHAPE_TOLERANCE`.
    Swapped sides fail the last, and a side entered in the wrong unit fails one
    of the first two. Doubt about either side withdraws both, since a height
    beside a mis-scaled width would be read as the pair it was entered as.
    """
    sides = [side for side in (height_cm, width_cm) if side is not None]
    if any(not SMALLEST_CM <= side <= LARGEST_CM for side in sides):
        return None, None
    if height_cm is None or width_cm is None:
        return height_cm, width_cm
    if max(height_cm, width_cm) / min(height_cm, width_cm) > MOST_ELONGATED:
        return None, None
    if picture is not None:
        disagreement = abs(math.log((height_cm / width_cm) / (picture.height / picture.width)))
        if disagreement > math.log(SHAPE_TOLERANCE):
            return None, None
    return height_cm, width_cm
