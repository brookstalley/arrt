"""The routes that read the registry (Wikidata) about an artist, a work or a look at one."""

from collections.abc import Callable, Sequence
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from arrt.http.models import (
    ArtistCandidateOut,
    ArtistRegistryOut,
    InReviewOut,
    LookOut,
    LookPictureOut,
    LookSourceOut,
    RegistryCreatorOut,
    RegistryHolderOut,
    RegistryHoldingOut,
    RegistryPersonFoundOut,
    RegistrySearchOut,
    RegistryWorkFoundOut,
    RegistryWorkOut,
    RegistryWorkPageOut,
    SimilarArtistOut,
    SimilarArtistsOut,
    UnlinkedArtistOut,
)
from arrt.http.routes.common import API_PREFIX, PREVIEW_CACHE_CONTROL, _services
from arrt.http.routes.shapes import _fit
from arrt.library.services.artists import RegistryView
from arrt.library.services.look import LookPicture, LookView, SourceLook
from arrt.library.services.twins import InReview

router = APIRouter(prefix=API_PREFIX)


@router.get("/registry/artists/{qid}")
def get_registry_artist(request: Request, qid: str) -> ArtistRegistryOut:
    """What Wikidata knows about an artist reached by QID, whether or not the library holds them.

    The same shape and states as an artist's `/registry`, but `no_identity` cannot
    occur. When the library holds an artist with this QID, `state` is `held`,
    `artist_id` names them, the page goes there instead, and the registry is not
    asked. A malformed QID is a 400.
    """
    held, view = _services(request).artists.registry_view_by_qid(qid)
    return _artist_registry(view, artist_id=held, pictured=_services(request).catalogue.pictured)


@router.get("/registry/search")
def search_registry(
    request: Request,
    q: Annotated[str, Query()] = "",
    prefix: Annotated[bool, Query()] = False,  # noqa: FBT002 -- a query parameter FastAPI passes by name
    wide: Annotated[bool, Query()] = False,  # noqa: FBT002 -- a query parameter FastAPI passes by name
) -> RegistrySearchOut:
    """Wikidata's artists and works for a few typed words, the other half of the top-bar search.

    `prefix=true` reads the last word as the start of one, as the typeahead does
    mid-word; `wide=true` returns the results page's longer lists. Always a 200:
    `state` says whether anything was asked and what the registry did.
    Kept per query for a week, across restarts; a failure is not.
    """
    found = _services(request).registry_search.search(q, prefix=prefix, wide=wide)
    held_artists, held_works = found.held_artists, found.held_works
    return RegistrySearchOut(
        state=str(found.state),
        note=found.note,
        artists=[
            RegistryPersonFoundOut(
                qid=p.qid,
                name=p.label,
                born=p.born,
                died=p.died,
                artist_id=held_artists.get(p.qid),
                in_review=_in_review(found.waiting_artists.get(p.qid)),
            )
            for p in found.artists
        ],
        works=[
            RegistryWorkFoundOut(
                qid=w.qid,
                title=w.title,
                sitelinks=w.sitelinks,
                image=w.image,
                creator=(
                    None
                    if w.creator is None
                    else RegistryCreatorOut(qid=w.creator.qid, name=w.creator.name, artist_id=held_artists.get(w.creator.qid))
                ),
                held_artwork_ids=list(held_works.get(w.qid, ())),
                pictured_artwork_id=found.pictured_works.get(w.qid),
                wanted=w.qid in found.wanted_works,
                in_review=_in_review(found.waiting_works.get(w.qid)),
            )
            for w in found.works
        ],
    )


@router.get("/registry/artists/{qid}/similar")
def get_similar_artists(request: Request, qid: str) -> SimilarArtistsOut:
    """*Similar artists* for the Artist page, by the artist's QID, held or not.

    Asked after the page is drawn: the query takes one to seven seconds. Always a
    200 for a well-formed QID; a malformed one is a 400.
    """
    view = _services(request).artists.similar(qid)
    return SimilarArtistsOut(
        state=str(view.state),
        note=view.note,
        artists=[
            SimilarArtistOut(qid=p.qid, name=p.name, born=p.born, died=p.died, images=p.images, artist_id=view.held.get(p.qid))
            for p in view.people
        ],
    )


@router.get("/registry/works/{qid}")
def get_registry_work(request: Request, qid: str) -> RegistryWorkPageOut:
    """One work as Wikidata knows it, and the library's works that are it, for the Work page by QID.

    Always a 200 for a well-formed QID: `state` says what the registry did, and
    `held_artwork_ids` is filled whatever it did. A malformed QID is a 400.
    """
    view = _services(request).registry_works.view(qid)
    known = view.known
    return RegistryWorkPageOut(
        state=str(view.state),
        note=view.note,
        qid=qid,
        title=None if known is None else known.title,
        year=None if known is None else known.year,
        sitelinks=None if known is None else known.sitelinks,
        image=None if known is None else known.image,
        creators=(
            []
            if known is None
            else [RegistryCreatorOut(qid=c.qid, name=c.name, artist_id=view.artists.get(c.qid)) for c in known.creators]
        ),
        media=[] if known is None else list(known.media),
        holders=(
            [] if known is None else [RegistryHolderOut(qid=h.qid, name=h.name, inventory=h.inventory) for h in known.holders]
        ),
        held_artwork_ids=list(view.held),
        wanted=view.wanted,
        height_cm=view.height_cm,
        width_cm=view.width_cm,
        image_width=None if view.image_size is None else view.image_size.width,
        image_height=None if view.image_size is None else view.image_size.height,
        fit=None if view.fit is None else _fit(view.fit),
    )


#: What a browser is told when a picture key is not one a work's current look
#: names: another work's, a refused find's, or one from a look no longer kept.
LOOK_AGAIN: str = "This picture is not part of a current look at this work. Look again."


@router.get("/registry/works/{qid}/look")
def get_registry_work_look(request: Request, qid: str) -> LookOut:
    """What every image source holds of the work, asked before any Get.

    Starts the asking, or joins it, and answers at once with each source's
    state: the page polls while `state` is `asking`. Nothing is written to the
    catalogue. A malformed QID is a 400.
    """
    return _look(_services(request).look.look(qid))


@router.get("/registry/works/{qid}/look/pictures/{key}", response_class=Response)
def get_registry_work_look_picture(
    request: Request,
    qid: str,
    key: str,
    size: Annotated[Literal["card", "large"], Query()] = "card",
) -> Response:
    """A picture the work's current look found, from the picture store.

    `key` is one the look's answer names, never a URL: any other key, or one
    from a look no longer kept, is a 404 saying to look again. A key the look
    names whose picture could not be kept is a 400, as a review card's is.
    `size` is the review card's: `card`, or `large` for the enlarged view.
    """
    rendered = _services(request).look.picture(qid, key, enlarged=size == "large")
    if rendered is None:
        return JSONResponse(status_code=404, content={"error": LOOK_AGAIN})
    return Response(content=rendered.data, media_type=rendered.media_type, headers={"Cache-Control": PREVIEW_CACHE_CONTROL})


def _in_review(waiting: InReview | None) -> InReviewOut | None:
    return None if waiting is None else InReviewOut(run_id=waiting.run_id, candidate_work_id=waiting.candidate_work_id)


def _artist_registry(
    view: RegistryView, *, pictured: Callable[[Sequence[str]], str | None], artist_id: str | None = None
) -> ArtistRegistryOut:
    known = view.known
    return ArtistRegistryOut(
        state=str(view.state),
        note=view.note,
        qid=None if known is None else known.qid,
        name=None if known is None else known.name,
        born=None if known is None else known.born,
        died=None if known is None else known.died,
        artist_id=artist_id,
        description=None if known is None else known.description,
        movements=[] if known is None else list(known.movements),
        works=(
            []
            if known is None
            else [
                RegistryWorkOut(
                    qid=entry.qid,
                    title=entry.title,
                    year=entry.year,
                    sitelinks=entry.sitelinks,
                    image=entry.image,
                    held_artwork_ids=list(view.held.get(entry.qid, ())),
                    pictured_artwork_id=pictured(view.held.get(entry.qid, ())),
                    wanted=entry.qid in view.wanted,
                    in_review=_in_review(view.waiting.get(entry.qid)),
                )
                for entry in known.works
            ]
        ),
        works_total=0 if known is None else known.works_total,
        holdings=([] if known is None else [RegistryHoldingOut(qid=h.qid, name=h.name, works=h.works) for h in known.holdings]),
        candidates=[
            ArtistCandidateOut(
                qid=candidate.person.qid,
                name=candidate.person.label,
                born=candidate.person.born,
                died=candidate.person.died,
                years_agree=candidate.years_agree,
            )
            for candidate in view.candidates
        ],
        unlinked=[
            UnlinkedArtistOut(artist_id=artist.id, name=artist.name, born=artist.born, died=artist.died)
            for artist in view.unlinked
        ],
    )


def _look(view: LookView) -> LookOut:
    return LookOut(
        qid=view.qid,
        state=str(view.state),
        note=view.note,
        held_artwork_ids=list(view.held),
        sources=[_look_source(source) for source in view.sources],
        pictures=[_look_picture(picture) for picture in view.pictures],
    )


def _look_source(source: SourceLook) -> LookSourceOut:
    return LookSourceOut(
        provider=source.provider,
        state=str(source.state),
        found=len(source.pictures),
        refusals=sorted(str(reason) for reason in source.refusals),
        answered_at=None if source.answered_at is None else source.answered_at.isoformat(),
        retry_at=None if source.retry_at is None else source.retry_at.isoformat(),
    )


def _look_picture(picture: LookPicture) -> LookPictureOut:
    judged = picture.judged
    found = judged.found
    return LookPictureOut(
        key=picture.key,
        provider=found.provider,
        url=found.url,
        title=found.title,
        artist=found.artist,
        width=found.estimated_width,
        height=found.estimated_height,
        fit=_fit(judged.fit),
        below_minimum=judged.below_minimum,
        confidence=judged.confidence,
        rights_status=None if found.rights_status is None else str(found.rights_status),
        selection_rationale=judged.rationale,
    )
