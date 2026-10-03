"""Wikimedia Commons, as one image source behind the seam, reached from a Wikidata item.

Commons answers only a query that names the work's Wikidata item, and says it
cannot answer any other (`ImageQueryUnanswerable`) rather than that it holds
nothing. It reads the
item's image (P18) through the registry, asks Commons what that file is, and
reports one instance. It searches Commons by title for nothing, because a title
search over Commons returns photographs of museum walls, posters and details, and
the item's own image is the one Wikidata's editors chose to stand for the work.

Every shape below was measured against the live API on 2026-10-02
(`wikidata-findings.md` § Commons). Three of them decide what this module does:

**The original can be far too large to fetch.** Starry Night's original is a
44,567 x 35,291 JPEG of 696,195,208 bytes, past the acquisition path's 512 MiB
ceiling, and decoding it would need gigabytes of memory on a Pi. Commons serves a
scaled rendering of any file, so a file wider than `DOWNLOAD_WIDTH` is fetched as
that rendering and reported at the rendering's size, which is the size that will
arrive.

**Renderings come only in fixed widths, and 3840 is the widest.** A request for
any other width is answered with the next fixed width, while `thumbwidth` reports
the width asked for, so a size computed from a non-standard request is wrong. A
URL for a wider rendering is refused with HTTP 400. So both widths used here are
fixed widths, and the reported size is the one Commons returns for them.

**The metadata endpoint is one constant address, asked with no redirect
followed**, as the registry client asks Wikidata. The image URLs it returns
(`upload.wikimedia.org`, `thumb.wikimedia.org`) are fetched later by the
acquisition path's checked transport, one hop at a time, like every other source's.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Final
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from arrt.library.sources import (
    DEFAULT_PREVIEW_MAX_BYTES,
    AcquisitionMethod,
    Declined,
    FoundImage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
    Registry,
    RegistryUnavailable,
    RightsStatus,
    SourceClass,
    SourceContext,
    SourceParts,
    SourcePlugin,
)

log = logging.getLogger(__name__)

#: The name these instances are recorded under.
PROVIDER: Final[str] = "commons"

API_URL: Final[str] = "https://commons.wikimedia.org/w/api.php"

#: The widest rendering Commons serves (measured: 3840 answered, 5000 and 7680
#: refused with HTTP 400). It is also the panel's width, so for today's walls a
#: wider file adds nothing a wall can show.
DOWNLOAD_WIDTH: Final[int] = 3840

#: A fixed rendering width close to the 843 px previews the Art Institute serves.
PREVIEW_WIDTH: Final[int] = 960

#: The file types the acquisition path can decode. Commons also holds SVG, PDF,
#: DjVu and video, none of which is a picture of a painting at a size.
_RASTER: Final[frozenset[str]] = frozenset({"image/jpeg", "image/png", "image/tiff", "image/webp"})

_TIMEOUT_SECONDS: Final[float] = 20.0

_FILE_PATH_PREFIX: Final[str] = "https://commons.wikimedia.org/wiki/Special:FilePath/"


class CommonsImageSearch:
    """The image a work's Wikidata item names, as Commons holds it."""

    def __init__(
        self,
        *,
        registry: Registry,
        user_agent: str,
        client: httpx.Client | None = None,
        preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
    ) -> None:
        self._registry = registry
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._preview_max_bytes = preview_max_bytes
        self._http = client or httpx.Client(timeout=httpx.Timeout(_TIMEOUT_SECONDS, connect=10.0), follow_redirects=False)

    @property
    def provider(self) -> str:
        return PROVIDER

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        if query.qid is None:
            raise ImageQueryUnanswerable("Commons looks a work up by its Wikidata item, and this work has none.")
        try:
            work = self._registry.work(query.qid)
        except RegistryUnavailable as exc:
            raise ImageSearchFailure(f"Wikidata could not be asked about {query.qid}: {exc}") from exc
        if work is None or work.image is None:
            return ()
        name = _file_name(work.image)
        download = self._image_info(name, width=DOWNLOAD_WIDTH)
        if download is None:
            return ()
        mime = download.get("mime")
        if mime not in _RASTER:
            log.info(
                "skipping a Commons file that is not a raster image",
                extra={"event": "commons.not_raster", "work_title": query.title, "mime": mime},
            )
            return ()
        chosen = self._what_to_fetch(download)
        if chosen is None:
            return ()
        url, width, height = chosen
        try:
            preview = self._image_info(name, width=PREVIEW_WIDTH)
        except ImageSearchFailure as exc:
            # A missing preview degrades the review card; it says nothing about
            # the image, which was already found and sized above.
            log.warning(
                "could not ask Commons for a preview rendering: %s",
                exc,
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "work_title": query.title},
            )
            preview = None
        return (
            FoundImage(
                url=url,
                provider=PROVIDER,
                source_class=SourceClass.INSTITUTIONAL,
                acquisition_method=AcquisitionMethod.DIRECT_HTTP,
                title=work.title,
                artist=work.creators[0].name if work.creators else None,
                preview_url=_without_query(preview.get("thumburl")) if preview else None,
                estimated_width=width,
                estimated_height=height,
                rights_status=_rights(download.get("extmetadata")),
            ),
        )

    def fetch_preview(self, url: str) -> bytes | None:
        """The preview bytes, read against the preview ceiling, or `None`."""
        try:
            with self._http.stream("GET", url, headers=self._headers) as response:
                if response.status_code != 200:
                    log.warning(
                        "could not cache a Commons preview",
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
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache a Commons preview",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)

    def tile_url(self, url: str) -> str:
        """A Commons image is fetched whole, so its recorded URL is where it is served."""
        return url

    def _what_to_fetch(self, info: Mapping[str, Any]) -> tuple[str, int | None, int | None] | None:
        """The original when it is no wider than the widest rendering, else that rendering.

        A file that narrow is a few megabytes at most, and the acquisition path's
        own byte ceiling still applies when it is fetched.

        Either way the size reported is the size of what will be fetched, since
        that is what the wall will show. None when Commons gave no file URL.
        """
        width, height = _integer(info.get("width")), _integer(info.get("height"))
        original = _without_query(info.get("url"))
        if original is None:
            return None
        if width is None or height is None:
            # Without the original's size nothing says whether a rendering exists
            # or how large it is, so no size is reported and phase 2 discards the
            # instance as one it cannot judge against the floor.
            return original, None, None
        if width <= DOWNLOAD_WIDTH:
            return original, width, height
        rendering = _without_query(info.get("thumburl"))
        if rendering is None:
            raise ImageSearchFailure("Commons answered without a rendering of a file too large to fetch whole.")
        return rendering, _integer(info.get("thumbwidth")), _integer(info.get("thumbheight"))

    def _image_info(self, name: str, *, width: int) -> Mapping[str, Any] | None:
        """What Commons says about one file, with a rendering at `width`, or None when it has no such file."""
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "imageinfo",
            "iiprop": "size|url|mime|extmetadata",
            "iiextmetadatafilter": "Copyrighted|LicenseShortName",
            "iiurlwidth": str(width),
            "titles": f"File:{name}",
        }
        try:
            response = self._http.get(API_URL, params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Commons could not be reached: {exc}") from exc
        if response.status_code != 200:
            # A redirect lands here too: the endpoint is asked with none followed.
            raise ImageSearchFailure(f"Commons answered HTTP {response.status_code}.")
        try:
            pages = response.json()["query"]["pages"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ImageSearchFailure("Commons' answer was not the imageinfo shape it documents.") from exc
        if not isinstance(pages, list) or not pages:
            raise ImageSearchFailure("Commons' answer carried no page for the file asked about.")
        page = pages[0]
        if not isinstance(page, Mapping) or page.get("missing") or not page.get("imageinfo"):
            return None
        info = page["imageinfo"][0]
        return info if isinstance(info, Mapping) else None


def _file_name(image: str) -> str:
    """The file's name from the registry's `Special:FilePath` URL."""
    if not image.startswith(_FILE_PATH_PREFIX):
        raise ImageSearchFailure(f"The registry's image is not a Commons file path: {image!r}.")
    return unquote(image[len(_FILE_PATH_PREFIX) :])


def _without_query(url: object) -> str | None:
    """An image URL with Commons' tracking parameters removed, or None when there is no URL."""
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _rights(metadata: object) -> RightsStatus:
    """Commons' own `Copyrighted` flag, read for what it says and nothing more."""
    if not isinstance(metadata, Mapping):
        return RightsStatus.UNKNOWN
    flag = metadata.get("Copyrighted", {})
    value = flag.get("value") if isinstance(flag, Mapping) else None
    if value == "False":
        return RightsStatus.PUBLIC_DOMAIN
    if value == "True":
        return RightsStatus.IN_COPYRIGHT
    return RightsStatus.UNKNOWN


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _create(context: SourceContext) -> SourceParts | Declined:
    """Commons, reached through a work's Wikidata item, or why it cannot be.

    It needs the registry to find the item's image, and it names itself to
    Wikimedia with `WIKIDATA_USER_AGENT`, which has no default for the reason the
    registry gives (`wikidata-findings.md`).
    """
    user_agent = context.environ.get("WIKIDATA_USER_AGENT") or None
    if user_agent is None:
        return Declined("WIKIDATA_USER_AGENT is unset, and Commons is reached only through a work's Wikidata item")
    if context.registry is None:
        return Declined("no registry is configured, and Commons is reached only through a work's Wikidata item")
    return SourceParts(
        finder=CommonsImageSearch(registry=context.registry, user_agent=user_agent, preview_max_bytes=context.preview_max_bytes)
    )


#: What the `commons` entry point names. Written for interface major 1 as a
#: literal, as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create)
