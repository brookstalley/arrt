"""Yale's two art museums, through their IIIF manifests, as one image source.

The Yale University Art Gallery (YUAG) and the Yale Center for British Art
(YCBA). It finds a work's object from the museum page its Wikidata item records,
and reports the object's image from the museum's IIIF manifest. It needs no key.
Every shape below was measured on 2026-10-07 (`linked-art-findings.md`). Five
of them decide what this module does:

**The object pages are behind a Cloudflare challenge and the manifests are not.**
A page answers 403 with "Just a moment...". The manifest, built from the same
number at `manifests.collections.yale.edu/{yuag|ycba}/obj/<n>`, answers 200, and
so does the image service on `images.collections.yale.edu`. So this plugin never
fetches a page. It reads the number out of it and asks for the manifest.

**Wikidata's IDs already name the pages.** YUAG's ID (P8583) and YCBA's Lido ID
(P9789) are formatted as `artgallery.yale.edu/collections/objects/<n>` and
`collections.britishart.yale.edu/catalog/tms:<n>`, which `Registry.pages_about`
returns. Of the YUAG items with no image on Wikidata, 4,053 of 4,068 carry the
ID. An image is reported under the page exactly as the item spells it, because
that link is what identifies it (`source-plugins.md` § What a finder or reader
must report). YCBA's VuFind number (P4738) does not map to a manifest and is
not read.

**The manifest carries everything the identity check needs**: the object's
`Title`, its creator (YUAG: "Artist: Vincent van Gogh (Dutch, …)"; YCBA: "Joseph
Mallord William Turner, born in London, …"), and each canvas's size, image
service and `Image Use Rights`. The manifest's own `rights` is CC0 on every
manifest, Rothko's included: it licenses the record, not the image, so it is
never read as the image's.

**Most works with no image on Wikidata are served at 480 pixels.** In a random
draw of 25 such YUAG items, 2 had no manifest, 18 were 480 px on the long side
(public domain and in copyright alike), and 5 were served in full (2,255 to
9,143 px). Every in-copyright work measured was 480 px (Rothko, de Kooning,
Hopper's *Rooms by the Sea*, Albers, Gottlieb). A small image of a work asked
for is worth having until a better one is found (the owner's ruling of
2026-10-03), so these are reported at the size served.

**One request serves the original, up to a size.** The image service declares no
limit and serves `full/full` at the size `info.json` and the canvas state (5 of 5
read from the JPEG header, up to 14,484 px). A 46,800-pixel original answered
HTTP 500, so an original longer than `_DIRECT_MAX_SIDE` is fetched as tiles.
"""

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Final, NamedTuple
from urllib.parse import urlsplit

import httpx

from arrt.library.sources import (
    DEFAULT_PREVIEW_MAX_BYTES,
    AcquisitionMethod,
    CanvasImage,
    FetchLocator,
    FoundImage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
    ImageService,
    ItemId,
    Registry,
    RegistryUnavailable,
    RightsStatus,
    SourceClass,
    SourceContext,
    SourceParts,
    SourcePlugin,
    manifest_images,
    manifest_metadata,
)

log = logging.getLogger(__name__)

#: The name these instances are recorded under.
PROVIDER: Final[str] = "yale"

_MANIFEST_HOST: Final[str] = "manifests.collections.yale.edu"
_IMAGE_HOST: Final[str] = "images.collections.yale.edu"
_IMAGE_PREFIX: Final[str] = f"https://{_IMAGE_HOST}/iiif/2/"

#: Each museum's page shape, as its Wikidata formatter builds it, and the
#: manifest path its number is asked under.
_PAGES: Final[Mapping[str, tuple[str, re.Pattern[str]]]] = {
    "artgallery.yale.edu": ("yuag", re.compile(r"/collections/objects/([1-9]\d{0,9})/?")),
    "collections.britishart.yale.edu": ("ycba", re.compile(r"/catalog/tms:([1-9]\d{0,9})")),
}

#: The longest side asked for in one request. The largest measured to be served
#: whole was 14,484 px and the smallest to fail 46,800 (HTTP 500, with no limit
#: declared); this is the next power of two above the one, well below the other.
_DIRECT_MAX_SIDE: Final[int] = 16384

#: The longest side a preview is asked at.
_PREVIEW_SIZE: Final[int] = 400

#: How many objects one work reads. The identity check above the seam, not this
#: number, decides what survives.
_RESULT_LIMIT: Final[int] = 10

#: What a canvas's `Image Use Rights` says, read for what it says. A value never
#: seen ("Not Assigned", "Copyright Not Evaluated") is unknown, not guessed at.
_PUBLIC_DOMAIN: Final[frozenset[str]] = frozenset({"No Copyright - United States"})
_CC0_PREFIX: Final[str] = "No Copyright: You can copy, modify, distribute and perform the work"
_IN_COPYRIGHT: Final[frozenset[str]] = frozenset({"In Copyright"})

#: The creator's role YUAG writes before the name of the work's maker.
_ARTIST_ROLE: Final[str] = "Artist"

_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
_READ_TIMEOUT_SECONDS: Final[float] = 20.0


class ObjectRef(NamedTuple):
    """One object at one of the two museums."""

    museum: str
    number: str

    @property
    def manifest_url(self) -> str:
        return f"https://{_MANIFEST_HOST}/{self.museum}/obj/{self.number}"

    def __str__(self) -> str:
        return f"{self.museum.upper()} object {self.number}"


def claims(url: str) -> bool:
    """Whether `url` is a YUAG or YCBA object page: the shapes this plugin records, on the museums' hosts only."""
    return object_ref(url) is not None


def object_ref(url: str) -> ObjectRef | None:
    """The object a YUAG or YCBA page names, or None when `url` is not one."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or port is not None or parts.username is not None or parts.password is not None:
        return None
    if parts.query or parts.fragment:
        return None
    page = _PAGES.get(parts.hostname or "")
    if page is None:
        return None
    museum, path = page
    match = path.fullmatch(parts.path)
    return ObjectRef(museum, match.group(1)) if match else None


def _on_image_host(url: object) -> bool:
    """Whether `url` is on Yale's image service, the one place this plugin reads or offers an image from.

    The prefix pins the scheme, the host and the absence of a port and of
    credentials together: a URL's authority ends at its first `/`, and the
    prefix carries that `/`.
    """
    return isinstance(url, str) and url.startswith(_IMAGE_PREFIX)


def _client(transport: httpx.BaseTransport | None) -> httpx.Client:
    """The one client policy. A test passes a transport, never a client, so it runs under this policy too."""
    return httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(
            connect=_CONNECT_TIMEOUT_SECONDS,
            read=_READ_TIMEOUT_SECONDS,
            write=_READ_TIMEOUT_SECONDS,
            pool=_READ_TIMEOUT_SECONDS,
        ),
        # No redirect is followed: both hosts answer in place, and a redirect
        # would take a read somewhere `_on_image_host` never checked.
        follow_redirects=False,
    )


class _Yale:
    """The three things this plugin asks Yale, shared by the finder and the reader."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None) -> None:
        self._http = _client(transport)
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._image_headers = {"User-Agent": user_agent, "Accept": "image/*"}

    def manifest(self, ref: ObjectRef) -> Mapping[str, Any] | None:
        """The object's manifest, or None when Yale has none for it (HTTP 404: an object with no image)."""
        response = self._get(ref.manifest_url, what=f"read the manifest of {ref}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        return self._json(response, what=f"read the manifest of {ref}")

    def service(self, canvas: CanvasImage, *, ref: ObjectRef) -> ImageService:
        """The image service the canvas names, read from its `info.json`, on Yale's image host only."""
        if canvas.service is None:
            raise ImageSearchFailure(f"Yale's manifest of {ref} names an image that is not a IIIF image service.")
        if not _on_image_host(canvas.service):
            raise ImageSearchFailure(f"Yale's manifest of {ref} names an image service off {_IMAGE_HOST}.")
        what = f"read the image service of {ref}"
        service = ImageService.from_info(self._json(self._get(f"{canvas.service}/info.json", what=what), what=what))
        if service.id != canvas.service:
            raise ImageSearchFailure(f"The image service of {ref} describes another image ({service.id}).")
        return service

    @contextmanager
    def preview(self, url: str) -> Iterator[httpx.Response]:
        """A streamed read of a rendering on Yale's image host, and of nothing anywhere else."""
        if not _on_image_host(url):
            raise ImageSearchFailure(f"{url!r} is not on Yale's image service, so it is not read.")
        with self._http.stream("GET", url, headers=self._image_headers) as response:
            yield response

    def _get(self, url: str, *, what: str) -> httpx.Response:
        try:
            return self._http.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Could not {what} at Yale: {exc}") from exc

    def _json(self, response: httpx.Response, *, what: str) -> Mapping[str, Any]:
        if response.status_code != httpx.codes.OK:
            # A redirect lands here too: none is followed.
            raise ImageSearchFailure(f"Could not {what} at Yale: HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise ImageSearchFailure(f"Could not {what} at Yale: the answer was not a JSON object.")
        return payload


def _rights(canvas: CanvasImage) -> RightsStatus:
    """The canvas's own statement about its image; the manifest's CC0 is about the record."""
    stated = canvas.metadata.get("Image Use Rights", ())
    if not stated:
        return RightsStatus.UNKNOWN
    first = stated[0].strip()
    if first in _PUBLIC_DOMAIN or (first.startswith(_CC0_PREFIX) and "(CC0 1.0)" in first):
        return RightsStatus.PUBLIC_DOMAIN
    if first in _IN_COPYRIGHT:
        return RightsStatus.IN_COPYRIGHT
    return RightsStatus.UNKNOWN


def _artist(metadata: Mapping[str, Sequence[str]]) -> str | None:
    """The work's maker, in Yale's words without the biography after the name; None for an unknown hand.

    YUAG writes each maker as "<role>: <name> (<nationality, dates, degrees>)" and
    YCBA as "<name>, <where and when born and died>". A YUAG role other than
    "Artist" ("Artist, copy after") is kept, because a copy after Romanelli is not
    Romanelli's work, and the identity check should be told so.
    """
    yuag = [line.strip() for line in metadata.get("Creator(s)", ()) if line.strip()]
    if yuag:
        made = [line.partition(": ") for line in yuag]
        role, _, name = next((entry for entry in made if entry[0] == _ARTIST_ROLE), made[0])
        name = name.split(" (", 1)[0].strip().rstrip(" ,")
        if not name or name.startswith("Unknown"):
            return None
        return name if role == _ARTIST_ROLE else f"{role}: {name}"
    ycba = [line.strip() for line in metadata.get("Creator", ()) if line.strip()]
    if ycba:
        name = ycba[0].split(",", 1)[0].strip()
        return None if not name or name.startswith("Unknown") else name
    return None


def _first_canvas(manifest: Mapping[str, Any]) -> CanvasImage | None:
    """The object's image: the manifest's first canvas. Later canvases are other views (a verso, an X-ray)."""
    images = manifest_images(manifest)
    return images[0] if images else None


class YaleFinder:
    """The image of a work at YUAG or YCBA, found from the museum page its Wikidata item records."""

    def __init__(
        self,
        *,
        user_agent: str,
        registry: Registry,
        transport: httpx.BaseTransport | None = None,
        preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
    ) -> None:
        self._yale = _Yale(user_agent=user_agent, transport=transport)
        self._registry = registry
        self._preview_max_bytes = preview_max_bytes

    @property
    def provider(self) -> str:
        return PROVIDER

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        """The image of each Yale object the work's item names a page of, in copyright or not, unjudged."""
        if query.qid is None:
            raise ImageQueryUnanswerable("Yale is found by a work's Wikidata item, and this work has none.")
        found = self._by_item(query.qid)
        log.info(
            "searched a museum collection for a work",
            extra={
                "event": "phase_two.searched",
                "provider": PROVIDER,
                "work_title": query.title,
                "by": "wikidata",
                "instances_usable": len(found),
            },
        )
        return found

    def fetch_preview(self, url: str) -> bytes | None:
        """The preview bytes, read against the preview ceiling, or `None`."""
        try:
            with self._yale.preview(url) as response:
                if response.status_code != httpx.codes.OK:
                    log.warning(
                        "could not cache a Yale preview",
                        extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "status": response.status_code},
                    )
                    return None
                chunks: list[bytes] = []
                received = 0
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > self._preview_max_bytes:
                        log.warning(
                            "a preview exceeded the size ceiling and was refused",
                            extra={"event": "phase_two.preview_too_large", "provider": PROVIDER, "preview_url": url},
                        )
                        return None
                    chunks.append(chunk)
        except ImageSearchFailure as exc:
            log.warning(
                "refused a Yale preview from elsewhere",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache a Yale preview",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)

    def _by_item(self, qid: ItemId) -> list[FoundImage]:
        """The images of the objects the item's Yale pages name, each under the page as the item spells it."""
        try:
            pages = self._registry.pages_about(qid)
        except RegistryUnavailable as exc:
            raise ImageSearchFailure(f"Wikidata could not be asked for {qid}'s Yale pages: {exc}") from exc
        objects: dict[ObjectRef, str] = {}
        for page in pages:
            ref = object_ref(page)
            if ref is not None:
                objects.setdefault(ref, page)
        found: list[FoundImage] = []
        for ref, page in list(objects.items())[:_RESULT_LIMIT]:
            image = self._image(ref, page=page)
            if image is not None:
                found.append(image)
        return found

    def _image(self, ref: ObjectRef, *, page: str) -> FoundImage | None:
        """The object's image, reported under `page`; None when Yale shows none of it."""
        manifest = self._yale.manifest(ref)
        if manifest is None:
            log.info(
                "Yale has no manifest for an object a Wikidata item names",
                extra={"event": "yale.no_manifest", "provider": PROVIDER, "object": str(ref)},
            )
            return None
        canvas = _first_canvas(manifest)
        if canvas is None:
            return None
        if canvas.service is None or not _on_image_host(canvas.service):
            raise ImageSearchFailure(f"Yale's manifest of {ref} names an image this plugin does not read.")
        metadata = manifest_metadata(manifest)
        title = next((text.strip() for text in metadata.get("Title", ()) if text.strip()), None)
        if title is None:
            raise ImageSearchFailure(f"Yale's manifest of {ref} gives the object no title.")
        width, height = canvas.width, canvas.height
        whole = width is not None and height is not None and max(width, height) <= _DIRECT_MAX_SIDE
        return FoundImage(
            url=page,
            provider=PROVIDER,
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP if whole else AcquisitionMethod.DEZOOMIFY,
            title=title,
            artist=_artist(metadata),
            preview_url=f"{canvas.service}/full/!{_PREVIEW_SIZE},{_PREVIEW_SIZE}/0/default.jpg",
            estimated_width=width,
            estimated_height=height,
            rights_status=_rights(canvas),
        )


class YaleReader:
    """Read a YUAG or YCBA page into its object's image, through the manifest, never the page."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None = None) -> None:
        self._yale = _Yale(user_agent=user_agent, transport=transport)

    def read(self, url: str) -> FetchLocator:
        ref = object_ref(url)
        if ref is None:
            raise ImageSearchFailure(f"{url!r} is not a YUAG or YCBA object page, so there is no manifest to read.")
        manifest = self._yale.manifest(ref)
        if manifest is None:
            return FetchLocator.none(f"Yale has no image of {ref}.")
        canvas = _first_canvas(manifest)
        if canvas is None:
            return FetchLocator.none(f"Yale's manifest of {ref} has no image.")
        return self._yale.service(canvas, ref=ref).locator(direct_max_side=_DIRECT_MAX_SIDE)


def _create(context: SourceContext) -> SourceParts:
    """Yale, found by Wikidata item when a registry is configured, and read always.

    It never declines: the manifests need no key, and it names itself with the
    deployment's own agent (`ACQUISITION_USER_AGENT`). With no registry it has
    no way to find a work, so it offers its reader alone and is not listed as
    an image source; the rows it found before still read.
    """
    reader = YaleReader(user_agent=context.user_agent)
    if context.registry is None:
        return SourceParts(reader=reader)
    finder = YaleFinder(user_agent=context.user_agent, registry=context.registry, preview_max_bytes=context.preview_max_bytes)
    return SourceParts(finder=finder, reader=reader)


#: What the `yale` entry point names. Written for interface major 1 as a literal,
#: as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create, claims=claims)
