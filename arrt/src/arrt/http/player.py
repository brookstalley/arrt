"""The Player's surface: its client, a wall's manifest, a label's document, media by content hash, and the heartbeats.

`player-contract.md` § Transport is the specification, and `contract/routes.json`
holds these routes' spelling, so the server and a Player in another repository
agree on them the way both planes already agree on the heartbeat's filename. They
sit at the root, beside `/api` rather than under it: `/api` is the curator's
surface, and this one is the Player's.

**Every request carries a client's token** (`clients.md`). A client learns its
walls and labels from `GET /client`, reports its outputs to
`POST /client/heartbeat`, is admitted to the per-wall routes for the walls
assigned to it, and to `GET /labels/{label_id}` for the label outputs it holds.

**Bindings, like every route.** Admission is a dependency each route declares:
it asks the access service, and a refused token raises `Refused`, which the
application turns into the `401` or `403` (`app.py`), so no handler branches on
the answer. A handler then makes its service call and turns the answer into a
response. The token check is the access service's, and the refusal log with it.

**Synchronous `def`**, for the reason `api.py` gives: the work is real file and
database I/O, and Starlette runs a sync handler in a worker thread. The client
heartbeat is the one `async def`, because it reads the raw body so that a body
that is not JSON is refused with the same `400` as one that is the wrong JSON;
its token check and its write still run in a worker thread.
"""

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Annotated, Any, Final

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from arrt.library.readiness import CONTENT_TYPES, MEDIA_PATH_TEMPLATE
from arrt.persistence.records import Client
from arrt.programming.access import Admission
from arrt.services.container import Services

router = APIRouter()

#: The routes, as `contract/routes.json` spells them. The media route is the
#: Library's own template, so the URL a manifest names and the route that answers
#: it are one string.
CLIENT_ROUTE: Final[str] = "/client"
CLIENT_HEARTBEAT_ROUTE: Final[str] = "/client/heartbeat"
MANIFEST_ROUTE: Final[str] = "/walls/{wall_id}/manifest"
MANIFEST_MAJOR_ROUTE: Final[str] = "/walls/{wall_id}/manifest/v{major}"
MEDIA_ROUTE: Final[str] = MEDIA_PATH_TEMPLATE
HEARTBEAT_ROUTE: Final[str] = "/walls/{wall_id}/heartbeat"
LABEL_ROUTE: Final[str] = "/labels/{label_id}"

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


class Refused(Exception):
    """A presented token that does not open what it asked for, as the access service judged it."""

    def __init__(self, admission: Admission) -> None:
        super().__init__(admission.value)
        self.admission = admission


def refusal(admission: Admission) -> JSONResponse:
    """`401` for no valid client token, `403` for a wall or label output not the client's. None names the token."""
    if admission is Admission.NOT_ITS_WALL:
        return JSONResponse(status_code=403, content={"error": "That wall is not assigned to this client."})
    if admission is Admission.NOT_ITS_LABEL:
        return JSONResponse(status_code=403, content={"error": "That label output is not this client's."})
    return JSONResponse(
        status_code=401,
        content={"error": "A valid client token is required."},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _presenting_client(request: Request) -> Client:
    """The client whose token this is. A dependency, so a refusal never reaches the handler."""
    presenting = _services(request).access.identify(_token(request))
    if presenting is None:
        raise Refused(Admission.UNKNOWN)
    return presenting


def _admitted_to_the_wall(request: Request, wall_id: str) -> None:
    """The token's client is the one this wall is assigned to."""
    admission = _services(request).access.admit(wall_id, _token(request))
    if admission is not Admission.ADMITTED:
        raise Refused(admission)


def _admitted_to_the_label(request: Request, label_id: str) -> None:
    """The token's client holds this label output."""
    admission = _services(request).access.admit_label(label_id, _token(request))
    if admission is not Admission.ADMITTED:
        raise Refused(admission)


def _admitted_to_media(request: Request) -> None:
    """The token is any client's, which is all media asks: a hash names nothing secret."""
    admission = _services(request).access.admit_any(_token(request))
    if admission is not Admission.ADMITTED:
        raise Refused(admission)


def _etagged(request: Request, body: bytes) -> Response:
    """The body with its hash as the ETag, or `304` when the caller already holds it."""
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if etag in _entity_tags(request.headers.get("if-none-match")):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


@router.get(CLIENT_ROUTE, include_in_schema=False)
def client(request: Request, presenting: Annotated[Client, Depends(_presenting_client)]) -> Response:
    """The presenting client and the walls assigned to it, each with the output it is shown on."""
    return _etagged(request, _services(request).clients.client_document(presenting.id))


@router.post(CLIENT_HEARTBEAT_ROUTE, status_code=204, include_in_schema=False)
async def client_heartbeat(request: Request, presenting: Annotated[Client, Depends(_presenting_client)]) -> Response:
    """What a client says about its outputs, kept where the curator's client listing reads it."""
    services = _services(request)
    try:
        document = json.loads(await request.body())
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "A client heartbeat is a JSON object, and this body is not JSON."})
    await run_in_threadpool(services.clients.record_heartbeat, presenting.id, document)
    return Response(status_code=204)


@router.get(MANIFEST_ROUTE, include_in_schema=False, dependencies=[Depends(_admitted_to_the_wall)])
def wall_manifest(request: Request, wall_id: str) -> Response:
    """The wall's manifest as last published, with its hash as the ETag."""
    body = _services(request).display.published_manifest(wall_id)
    if body is None:
        # The contract classes a 404 on the wall as a configuration error: a
        # wall with nothing hanging has no manifest to serve.
        return JSONResponse(status_code=404, content={"error": "Nothing has been published for this wall yet."})
    return _etagged(request, body)


@router.get(MANIFEST_MAJOR_ROUTE, include_in_schema=False, dependencies=[Depends(_admitted_to_the_wall)])
def wall_manifest_at_major(request: Request, wall_id: str, major: str) -> Response:
    """The wall's manifest at one major, so a Player can ask for the highest it reads.

    Major 1 is the document the unversioned route serves, and major 2 the wall's
    feed. Any other spelling answers 404, which is how a Player learns to step
    down a major (`player-contract.md` § The cutover); so does a major 2 not yet
    published for this wall, so its Player stays on major 1 until a sync. The
    match is on the exact string, so `01` is not a second URL for major 1.
    """
    if major == "1":
        return wall_manifest(request, wall_id)
    if major == "2":
        body = _services(request).display.published_manifest_v2(wall_id)
        if body is not None:
            return _etagged(request, body)
    return JSONResponse(status_code=404, content={"error": f"No manifest major {major} is published for this wall."})


@router.get(LABEL_ROUTE, include_in_schema=False, dependencies=[Depends(_admitted_to_the_label)])
def label(request: Request, label_id: str) -> Response:
    """The label document: the state of the wall this label output captions, and its text, with its hash as the ETag."""
    body = _services(request).clients.label_document(label_id)
    if body is None:
        # Its client was told of no such label (`GET /client` lists only label
        # outputs that caption a wall), so asking is a configuration error.
        return JSONResponse(status_code=404, content={"error": "This label output captions no wall."})
    return _etagged(request, body)


@router.get(MEDIA_ROUTE, include_in_schema=False, dependencies=[Depends(_admitted_to_media)])
def media(request: Request, sha256: str) -> Response:
    """A render's bytes, by the hash of those bytes. Any client's token opens it."""
    found = _services(request).catalogue.read_media(sha256) if _SHA256.fullmatch(sha256) else None
    if found is None:
        return JSONResponse(status_code=404, content={"error": "No render with that hash is held."})
    rendition, data = found
    content_type = CONTENT_TYPES.get(PurePosixPath(rendition.relative_path).suffix.lower(), "application/octet-stream")
    return Response(content=data, media_type=content_type, headers={"Cache-Control": _IMMUTABLE})


@router.post(HEARTBEAT_ROUTE, status_code=204, include_in_schema=False, dependencies=[Depends(_admitted_to_the_wall)])
def heartbeat(request: Request, wall_id: str, document: Annotated[dict[str, Any], Body()]) -> Response:
    """What a Player says about one wall, kept where the health panel reads it."""
    _services(request).display.record_heartbeat(wall_id, document)
    return Response(status_code=204)


def _entity_tags(header: str | None) -> set[str]:
    """The tags an `If-None-Match` header lists. `*` is not honoured: a Player always sends a tag."""
    if not header:
        return set()
    return {tag.strip().removeprefix("W/") for tag in header.split(",")}
