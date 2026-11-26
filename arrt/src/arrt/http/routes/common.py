"""What every route module needs: the services a request reads, the error shape, and the cache policies."""

from fastapi import Request
from fastapi.responses import JSONResponse

from arrt.services.container import Services

#: The path every route here is mounted under.
API_PREFIX: str = "/api"


#: Thumbnails and wall previews are revalidated rather than held for a fixed
#: window. A replaced master, or a recomposed canvas, regenerates the file under
#: the same name, so a cached copy is a
#: *superseded acquisition* on screen — the exact thing the staleness rule
#: refuses everywhere else. The cost of that correctness is one conditional
#: request per card, answered with a 304 rather than the bytes (`works._revalidated_file`).
THUMBNAIL_CACHE_CONTROL: str = "private, no-cache"


#: A candidate preview, by contrast, is held rather than revalidated — and the
#: difference between the two lines is a property of the data rather than a
#: preference. A thumbnail is named for its *work*, and a re-acquired master
#: regenerates it under the same name, so a cached copy can become a superseded
#: acquisition on screen. A candidate preview is named for its *instance*: the
#: picture store keeps one picture per instance, never re-fetches what it keeps
#: and never deletes it, so the bytes behind an image id are written once. An id
#: whose content cannot change is the case `immutable` exists for, and it is what
#: keeps a repaint of a thirty-card grid from asking the server thirty times.
#:
#: A row a sweep has reclaimed is not a hole in that: its card is told by the
#: listing that no picture travels, so it never asks, and a copy still in a
#: browser cache is never shown.
PREVIEW_CACHE_CONTROL: str = "private, max-age=86400, immutable"


def _services(request: Request) -> Services:
    """The services this application was built around.

    Read off application state rather than injected per route, because they are
    constructed once at startup over one open catalogue file — a per-request
    dependency would suggest a lifetime they do not have.
    """
    return request.app.state.services


def service_error_response(message: str, *, not_found: bool = False) -> JSONResponse:
    """The one error shape this surface returns: `404` for a thing named that is not there, `400` for every other refusal.

    Two statuses and no more, because the service layer draws one distinction
    (`NotFound`, a `ServiceError` naming a thing that does not exist) and a
    per-error translation table here is what turns a thin binding into a thick
    one. The message is written to be shown either way: it names what was wrong
    and, where there is one, the thing to do instead. The caller says which it
    is (`app.py`), since only `/api` tells the two apart.
    """
    return JSONResponse(status_code=404 if not_found else 400, content={"error": message})
