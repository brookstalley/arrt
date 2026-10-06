"""Serving the browser client itself — the shell and its two assets.

The client is a static page and a script that reads `/api/*`. It is served from
this package rather than built, because the alternative is a Node toolchain on a
Raspberry Pi maintained for a single-operator tool on a private network, which
buys nothing a curator can see.

The shell answers on every UI path, not only `/`. In-page navigation writes a
fragment, so the server sees one path in practice — but a bookmarked or reloaded
deep link must not 404, and a catch-all that returned the shell for `/api/...`
too would turn a mistyped endpoint into a page of HTML that a client parses as
JSON. So the UI paths are listed rather than globbed.
"""

import os
from pathlib import Path
from typing import Final

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

router = APIRouter()

STATIC_DIR: Final[Path] = Path(__file__).parent / "static"

#: Every path the client renders a view for. Adding a view means adding it here;
#: a view reachable only by clicking is a view nobody can bookmark.
#:
#: The root, then every sidebar page: `information-architecture.md` requires
#: every screen and every consequential state to have a URL. The paths keep the
#: spellings they had before the *arr labels (`/collection` is Artworks,
#: `/discover` is Ask, `/health` is Status), because a bookmark is an address.
#:
#: `/works`, `/discovery`, `/themes` and `/manifest` are the spellings the
#: surface answered to before its first reshape. They are kept
#: because they have been real, bookmarkable paths since the client was built;
#: `core/route.js` maps each onto the screen that took over its job, and rewrites
#: the address bar to the new spelling on arrival. Nothing here generates one.
UI_PATHS: Final[tuple[str, ...]] = (
    "/",
    "/walls",
    "/to_review",
    "/queue",
    "/history",
    "/wanted",
    "/collection",
    "/discover",
    "/theme",
    "/artist",
    "/topics",
    "/taste",
    "/clients",
    "/search",
    "/health",
    "/works",
    "/discovery",
    "/themes",
    "/manifest",
)


#: Every file of the client is asked about again on every load. The client is a
#: tree of ES modules that import names from one another, and the image keeps
#: each file's checkout date, so without this a browser holds an unchanged-for-
#: days module for hours by heuristic. After a deploy that leaves a cached old
#: module beside a fetched new one importing a name only the new one exports,
#: and the client never starts (seen 2026-10-05: "Loading the catalogue" on a
#: phone). The ETag keeps an unchanged file to a 304, which on a LAN is nothing.
CLIENT_CACHE_CONTROL: Final[str] = "no-cache"


def index() -> FileResponse:
    """The client shell."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html", headers={"Cache-Control": CLIENT_CACHE_CONTROL})


class ClientFiles(StaticFiles):
    """The client's static files, each revalidated on every load (`CLIENT_CACHE_CONTROL`)."""

    def file_response(
        self, full_path: str | os.PathLike[str], stat_result: os.stat_result, scope: Scope, status_code: int = 200
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = CLIENT_CACHE_CONTROL
        return response


# Registered in a loop rather than with a decorator per path, so `UI_PATHS` is
# the single list and a route cannot be added to one without the other. Module
# scope on purpose: exporting a `register(router)` helper would invite a second
# call that silently double-registers every path.
for _path in UI_PATHS:
    router.add_api_route(_path, index, methods=["GET"], include_in_schema=False)
