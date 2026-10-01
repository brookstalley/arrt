"""The Player's surface: a wall's manifest, media by content hash, and the heartbeat.

`player-contract.md` § Transport is the specification, and `contract/routes.json`
holds these three routes' spelling, so the server and a Player in another
repository agree on them the way both planes already agree on the heartbeat's
filename. They sit at the root, beside `/api` rather than under it: `/api` is the
curator's surface, and this one is the Player's.

**Bindings, like every route.** Each handler checks the wall's token, makes one
service call, and turns the answer into a response. The token check is the
access service's, and the refusal log with it.

**Synchronous `def`**, for the reason `api.py` gives: the work is real file and
database I/O, and Starlette runs a sync handler in a worker thread.
"""

import hashlib
import re
from pathlib import PurePosixPath
from typing import Annotated, Any, Final

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from arrt.library.readiness import CONTENT_TYPES, MEDIA_PATH_TEMPLATE
from arrt.programming.access import Admission
from arrt.services.container import Services

router = APIRouter()

#: The three routes, as `contract/routes.json` spells them. The media route is
#: the Library's own template, so the URL a manifest names and the route that
#: answers it are one string.
MANIFEST_ROUTE: Final[str] = "/walls/{wall_id}/manifest"
MEDIA_ROUTE: Final[str] = MEDIA_PATH_TEMPLATE
HEARTBEAT_ROUTE: Final[str] = "/walls/{wall_id}/heartbeat"

_SHA256: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")

#: Media never changes under its name, so a Player or anything between it and
#: here may keep it for as long as it likes.
_IMMUTABLE: Final[str] = "public, max-age=31536000, immutable"


def _services(request: Request) -> Services:
    return request.app.state.services


def _token(request: Request) -> str | None:
    """The bearer token, or None when the header is absent or not a bearer credential."""
    scheme, _, credential = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return credential.strip() or None


def _refused(admission: Admission) -> JSONResponse:
    """`401` for no valid token, `403` for another wall's. Neither names the token."""
    if admission is Admission.OTHER_WALL:
        return JSONResponse(status_code=403, content={"error": "That token is for another wall."})
    return JSONResponse(
        status_code=401,
        content={"error": "A valid wall token is required."},
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get(MANIFEST_ROUTE, include_in_schema=False)
def wall_manifest(request: Request, wall_id: str) -> Response:
    """The wall's manifest as last published, with its hash as the ETag."""
    services = _services(request)
    admission = services.access.admit(wall_id, _token(request))
    if admission is not Admission.ADMITTED:
        return _refused(admission)
    body = services.display.published_manifest(wall_id)
    if body is None:
        # The contract classes a 404 on the wall as a configuration error: a
        # wall with nothing hanging has no manifest to serve.
        return JSONResponse(status_code=404, content={"error": "Nothing has been published for this wall yet."})
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if etag in _entity_tags(request.headers.get("if-none-match")):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


@router.get(MEDIA_ROUTE, include_in_schema=False)
def media(request: Request, sha256: str) -> Response:
    """A render's bytes, by the hash of those bytes. Any wall's token opens it."""
    services = _services(request)
    admission = services.access.admit_any(_token(request))
    if admission is not Admission.ADMITTED:
        return _refused(admission)
    found = services.catalogue.read_media(sha256) if _SHA256.fullmatch(sha256) else None
    if found is None:
        return JSONResponse(status_code=404, content={"error": "No render with that hash is held."})
    rendition, data = found
    content_type = CONTENT_TYPES.get(PurePosixPath(rendition.relative_path).suffix.lower(), "application/octet-stream")
    return Response(content=data, media_type=content_type, headers={"Cache-Control": _IMMUTABLE})


@router.post(HEARTBEAT_ROUTE, status_code=204, include_in_schema=False)
def heartbeat(request: Request, wall_id: str, document: Annotated[dict[str, Any], Body()]) -> Response:
    """What a Player says about itself, kept where the health panel reads it."""
    services = _services(request)
    admission = services.access.admit(wall_id, _token(request))
    if admission is not Admission.ADMITTED:
        return _refused(admission)
    services.display.record_heartbeat(wall_id, document)
    return Response(status_code=204)


def _entity_tags(header: str | None) -> set[str]:
    """The tags an `If-None-Match` header lists. `*` is not honoured: a Player always sends a tag."""
    if not header:
        return set()
    return {tag.strip().removeprefix("W/") for tag in header.split(",")}
