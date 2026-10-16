"""What a curator sees when they look at a work — composed once, for both surfaces.

A review surface does not want a work; it wants a work together with everything
needed to judge it: whether the held image meets the quality profile, and whether
there is an image to look at at all. `api-contract.md` requires exactly that
pairing of `art_review`'s listings, and the browser grid needs the same thing — so
composing it here is what stops an agent and a click disagreeing about whether a
work is big enough.

**Nothing is decided here that is decided elsewhere.** The size verdict is the
quality profile's, the choice of which held image to show is the thumbnail
service's, and paging is the catalogue's. This gathers them, and its only
judgement of its own is that a missing answer is reported as a stated reason
rather than as an absent field — a card that shows no size because a work has no
master must not look like a card whose work is small.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from arrt.library.acquisition.queue import AcquisitionState
from arrt.library.services.catalogue import ArtworkDetail, CatalogueService, FacetGroup, RenditionView
from arrt.library.services.quality import Fit, QualityProfile
from arrt.library.services.thumbnails import ThumbnailService, ThumbnailUnavailable
from arrt.persistence.records import MatColor, Original, Source, WorkFacet

#: The band of a work whose size cannot be said, because it holds no master
#: yet. Beside `Fit`'s values rather than one of them: it is
#: not a verdict about a picture, and a fit value meaning "no picture" would be
#: read as one.
NO_SIZE_KNOWN = "unknown"

#: The *Size* facet's bands, in the order the rail offers them: meeting the
#: minimum first, and the works nobody can size last.
FIT_BANDS: tuple[str, ...] = (*(str(fit) for fit in Fit), NO_SIZE_KNOWN)


@dataclass(frozen=True, slots=True)
class ImageAvailability:
    """Whether this work can be shown."""

    available: bool
    #: Present exactly when `available` is false, saying what is missing.
    note: str | None


@dataclass(frozen=True, slots=True)
class WorkSurvey:
    """One work as a review surface needs it."""

    detail: ArtworkDetail
    #: None when the work holds no master, in which case `fit_note` says so.
    fit: Fit | None
    fit_note: str | None
    image: ImageAvailability


@dataclass(frozen=True, slots=True)
class WorkSurveyPage:
    """One page of works, carrying enough to describe its own place in the set."""

    entries: Sequence[WorkSurvey]
    total: int
    limit: int
    offset: int
    truncated: bool
    #: What the facet controls beside this grid should offer, with each option's
    #: count over the *rest* of the filter. Travels with the page rather than
    #: from a second route, so the numbers and the works cannot describe
    #: different sets.
    facets: Sequence[FacetGroup] = ()


@dataclass(frozen=True, slots=True)
class WorkDossier:
    """One work in full — what a detail view shows."""

    survey: WorkSurvey
    original: Original | None
    sources: Sequence[Source]
    renditions: Sequence[RenditionView]
    mat_colors: Sequence[MatColor]
    #: What this work is said to be. On the dossier rather than on every grid
    #: card: the Work screen states a work's facets, and a grid states the
    #: collection's counts — one card carrying its own six kinds would be a read
    #: per work per page for something no card shows.
    facets: Sequence[WorkFacet] = ()
    #: Where the work stands in the acquisition queue: queued, being fetched,
    #: failed, given up on, or held back by a pause. None when the queue owes it
    #: nothing — it holds its image and is prepared, or it is archived.
    acquisition: AcquisitionState | None = None


class AcquisitionStates(Protocol):
    """The one question the survey asks the acquisition queue."""

    def state_of(self, artwork_ids: Sequence[str]) -> Mapping[str, AcquisitionState]: ...


class SurveyService:
    """Read works the way a surface that shows them to a human needs them."""

    def __init__(
        self,
        catalogue: CatalogueService,
        thumbnails: ThumbnailService,
        profile: QualityProfile,
        *,
        acquisition: AcquisitionStates,
    ) -> None:
        self._catalogue = catalogue
        self._thumbnails = thumbnails
        self._profile = profile
        #: Required rather than defaulted: a dossier with no acquisition state
        #: reads exactly like a work the queue owes nothing, which is the
        #: silence the Work page exists to break.
        self._acquisition = acquisition

    def list_works(
        self,
        *,
        status: str | None = None,
        q: str | None = None,
        facets: Mapping[str, Sequence[str]] | None = None,
        limit: int | None = None,
        offset: int = 0,
        sort: str | None = None,
        artist_id: str | None = None,
        within: Sequence[str] | None = None,
    ) -> WorkSurveyPage:
        """A page of works, each with its fit verdict and its image state.

        The narrowing arguments are passed straight through: what `q` and
        `facets` mean, and how the facet counts beside the page are computed, is
        `CatalogueService.list_artworks`'s to decide. Restating any of it here
        would be the second implementation of "list the catalogue" that the shared
        service layer exists to prevent.
        """
        listing = self._catalogue.list_artworks(
            status=status, q=q, facets=facets, limit=limit, offset=offset, sort=sort, artist_id=artist_id, within=within
        )
        return WorkSurveyPage(
            entries=[self._survey(entry) for entry in listing.entries],
            total=listing.total,
            limit=listing.limit,
            offset=listing.offset,
            truncated=listing.truncated,
            facets=listing.facets,
        )

    def fit_of(self, artwork_id: str) -> Fit | None:
        """Whether the work's held image meets the quality minimum, or None when it holds none."""
        original = self._catalogue.get_original(artwork_id)
        return None if original is None else self._catalogue.fit(artwork_id, profile=self._profile)

    def fit_bands(self, artwork_ids: Sequence[str] | frozenset[str]) -> Mapping[str, str]:
        """Each work's size, as a band: a `Fit` value, or `NO_SIZE_KNOWN`.

        Artworks' *Size* facet counts and filters by this, so it is the same
        verdict a card shows — the quality profile's — reached in one read of
        the masters' sizes rather
        than one per work. A work with no master is `NO_SIZE_KNOWN`, its own
        band rather than left out, so the bands' counts add up to the works.
        """
        sizes = self._catalogue.original_sizes(artwork_ids)
        bands: dict[str, str] = {}
        for artwork_id in artwork_ids:
            size = sizes.get(artwork_id)
            if size is None or size[0] <= 0 or size[1] <= 0:
                bands[artwork_id] = NO_SIZE_KNOWN
            else:
                bands[artwork_id] = str(self._profile.judge(width=size[0], height=size[1]))
        return bands

    def survey_works(self, artwork_ids: Sequence[str]) -> Sequence[WorkSurvey]:
        """These works in the order given, each judged the way a grid card needs.

        **The order is the caller's.** A theme's order is Programming's to decide,
        and the Library never reads it: the surface asks Programming for the ids
        and hands them here, rather than this service re-deriving "which works, in
        what order", which is exactly the divergence a surface must not
        introduce.
        """
        return [self._survey(detail) for detail in self._catalogue.resolve_details(artwork_ids)]

    def get_work(self, artwork_id: str) -> WorkDossier:
        """One work with everything a detail view shows."""
        detail = self._catalogue.get_artwork(artwork_id)
        return WorkDossier(
            survey=self._survey(detail),
            original=self._catalogue.get_original(artwork_id),
            sources=self._catalogue.list_sources(artwork_id),
            renditions=self._catalogue.list_renditions(artwork_id),
            mat_colors=self._catalogue.mat_color_history(artwork_id),
            facets=self._catalogue.facets_for(artwork_id),
            acquisition=self._acquisition.state_of([artwork_id]).get(artwork_id),
        )

    def _survey(self, detail: ArtworkDetail) -> WorkSurvey:
        artwork_id = detail.artwork.id
        original = self._catalogue.get_original(artwork_id)
        fit = None if original is None else self._catalogue.fit(artwork_id, profile=self._profile)
        fit_note = None if original is not None else "No master image has been acquired, so its size is unknown."
        try:
            self._thumbnails.source_for(artwork_id)
        except ThumbnailUnavailable as absent:
            # The type exists for this: "there is no image yet" is an ordinary
            # state of a catalogue mid-acquisition, and its message is written to
            # be shown beside the work rather than raised at the curator.
            image = ImageAvailability(available=False, note=str(absent))
        else:
            image = ImageAvailability(available=True, note=None)
        return WorkSurvey(detail=detail, fit=fit, fit_note=fit_note, image=image)
