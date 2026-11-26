"""The routes for the artists the Library holds, and the identity a person sets on one."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from arrt.http.models import ArtistListOut, ArtistOut, ArtistRegistryOut, HeldArtistOut, SetIdentity
from arrt.http.routes.common import API_PREFIX, _services
from arrt.http.routes.registry import _artist_registry
from arrt.http.routes.shapes import _artist
from arrt.library.services.artists import HeldArtist

router = APIRouter(prefix=API_PREFIX)


@router.get("/artists")
def list_artists(request: Request, q: Annotated[str | None, Query()] = None) -> ArtistListOut:
    """Library › Artists: every artist with a work in circulation, by surname (`surname_key`).

    `q` narrows to names containing it, ignoring case and accents, which is what
    the top-bar search asks when it offers artists.

    **Not capped, and what bounds it is the catalogue**: one row per artist with a
    work in circulation, so never more rows than works, and an artist's row is a
    name, a count and one work id. At the NFR's thousands of works that is a few
    hundred rows.
    If it is ever paged, the typeahead's `q` lookup is the caller that needs it.
    """
    return ArtistListOut(artists=[_held_artist(entry) for entry in _services(request).artists.index(q)])


@router.get("/artists/{artist_id}")
def get_artist(request: Request, artist_id: str) -> HeldArtistOut:
    """One artist, from the library alone: answerable whatever the registry is doing."""
    return _held_artist(_services(request).artists.get(artist_id))


@router.get("/artists/{artist_id}/registry")
def get_artist_registry(request: Request, artist_id: str) -> ArtistRegistryOut:
    """What Wikidata knows about this artist, asked separately so a slow or absent registry delays nothing else.

    Always a 200 for an artist the catalogue holds: a registry that is not
    configured, cannot be asked, or has nothing for this artist is a state the
    page shows, named in `state` and said in `note`.
    """
    services = _services(request)
    return _artist_registry(services.artists.registry_view(artist_id), pictured=services.catalogue.pictured)


@router.post("/artists/{artist_id}/wikidata")
def set_artist_identity(request: Request, artist_id: str, body: SetIdentity) -> ArtistOut:
    """Say which Wikidata item this artist is, or that there is none."""
    return _artist(_services(request).identity.set_artist_identity(artist_id, body.qid))


def _held_artist(entry: HeldArtist) -> HeldArtistOut:
    return HeldArtistOut(artist=_artist(entry.artist), held=entry.held, pictured_artwork_id=entry.pictured)
