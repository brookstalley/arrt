"""The routes for the curator's standing judgments of taste."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from arrt.http.models import AffinityListOut, AffinityOut, SetAffinity
from arrt.http.routes.common import API_PREFIX, _services
from arrt.persistence.discovery_records import Affinity

router = APIRouter(prefix=API_PREFIX)


@router.get("/affinities")
def list_affinities(
    request: Request,
    kind: Annotated[str | None, Query()] = None,
    sentiment: Annotated[str | None, Query()] = None,
    derivation: Annotated[str | None, Query()] = None,
) -> AffinityListOut:
    """The curator's standing judgments, narrowed by any of the three.

    Unpaged: this is a household's whole taste, which is tens of rows, and a page
    over it would be a second way to read what one call hands back whole.
    """
    affinities = _services(request).taste.list_affinities(kind=kind, sentiment=sentiment, derivation=derivation)
    return AffinityListOut(affinities=[_affinity(entry) for entry in affinities], count=len(affinities))


@router.post("/affinities")
def set_affinity(request: Request, body: SetAffinity) -> AffinityOut:
    """Write one judgment over whatever was there, or write the first one.

    `POST` rather than `PATCH` because this surface writes with `POST` everywhere
    and one surface with two spellings for "change this" costs more than the
    orthodoxy is worth. It is an upsert addressed by (`kind`, `value`), so a
    correction needs no id — which is right for the caller that has a name in a
    sentence rather than a row it fetched.
    """
    return _affinity(
        _services(request).taste.set_affinity(
            kind=body.kind,
            value=body.value,
            sentiment=body.sentiment,
            open_to_more=body.open_to_more,
            derivation=body.derivation,
            rationale=body.rationale,
        )
    )


@router.delete("/affinities/{affinity_id}")
def delete_affinity(request: Request, affinity_id: str) -> AffinityOut:
    """Forget one judgment, and answer with what was forgotten.

    The row rather than an acknowledgement of the id, because this is not
    recoverable: a confirmation should name the thing that is gone rather than the
    handle it was addressed by.
    """
    return _affinity(_services(request).taste.delete_affinity(affinity_id))


def _affinity(affinity: Affinity) -> AffinityOut:
    return AffinityOut(
        affinity_id=affinity.id,
        kind=str(affinity.kind),
        value=affinity.value,
        sentiment=str(affinity.sentiment),
        open_to_more=affinity.open_to_more,
        derivation=str(affinity.derivation),
        rationale=affinity.rationale,
        artist_id=affinity.artist_id,
        created_at=affinity.created_at.isoformat(),
        updated_at=affinity.updated_at.isoformat(),
    )
