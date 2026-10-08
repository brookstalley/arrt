"""The Metropolitan Museum of Art's open-access API, as one image source behind the seam.

It finds a work's object at the Met, from the work's Wikidata item or by search,
and reports the object's original image. It needs no key. Every shape below was
measured against the live API on 2026-10-06 (`met-api-findings.md`). Four of
them decide what this module does:

**Only public-domain objects carry an image.** An in-copyright object answers
with empty `primaryImage` fields, though the Met's web pages show its picture.
Those pages sit behind a bot checkpoint, so reading them is a private plugin's
job, not this one's.

**This plugin records, and claims, only the API's object URL**, never the Met's
web page. Arrt routes a stored source by its URL, never by the plugin that found
it, so a web page claimed here would send a private page reader's rows to this
reader, which can only say "no image" for an in-copyright work. Disjoint shapes
let both plugins be installed in any order (`source-plugins.md` § One holder,
two plugins). The cost: the web page Wikidata gives stays a sighting while the
work is open, and this plugin's URL is not a page the item records, so its
instances get no title shortcut in the identity check.

**The search's order is not relevance.** A broad title (`Window`, 886 objects)
comes back in what looks like id order, so its first ten are a lottery. A title
search is therefore intersected with the artist's objects when the Met knows
the artist.

**No pixel size is given anywhere.** The original's size is read from its JPEG
header with a ranged request, which the image host honours; the start-of-frame
of *Wheat Field with Cypresses* sat at byte 40,798, behind its metadata.
"""

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Final
from urllib.parse import urlsplit

import httpx

from arrt.library.sources import (
    DEFAULT_PREVIEW_MAX_BYTES,
    AcquisitionMethod,
    FetchLocator,
    FoundImage,
    ImageQuery,
    ImageSearchFailure,
    ItemId,
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
PROVIDER: Final[str] = "met"

#: The name a curator knows this source by, for every sentence that names it
#: (`names.museum_name`).
MUSEUM: Final[str] = "Metropolitan Museum of Art"

_API_HOST: Final[str] = "collectionapi.metmuseum.org"

#: Where one object is read, and the address every instance here is recorded
#: under (`object_url`). `/v1.1/objects` does not exist (HTTP 404, measured).
_OBJECT_PREFIX: Final[str] = f"https://{_API_HOST}/public/collection/v1/objects/"

#: `/v1/search` was retired on 2026-10-01; this one pages with `offset`/`limit`.
_SEARCH_URL: Final[str] = f"https://{_API_HOST}/public/collection/v1.1/search"

#: The only host an image or preview is read from. The API names it, and a name
#: from a JSON answer is checked rather than taken, because this plugin reads
#: what it names and its own requests pass no other guard.
_IMAGE_HOST: Final[str] = "images.metmuseum.org"

#: Wikidata's form of a Met object id (P3634's own pattern).
_ID: Final[str] = r"([1-9][0-9]{0,8})"

#: The object's place in the API URL this plugin records and claims.
_API_OBJECT: Final[re.Pattern[str]] = re.compile(rf"/public/collection/v1/objects/{_ID}")

#: The object's place in the Met's web page, which Wikidata's preferred
#: formatter builds. Read for its id, never claimed.
_WEB_HOST: Final[str] = "www.metmuseum.org"
_WEB_OBJECT: Final[re.Pattern[str]] = re.compile(rf"/art/collection/search/{_ID}/?")

#: How many objects one work reads. Each is one request for the record and one
#: for the image's head, and it is the identity check above the seam, not this
#: number, that decides what survives.
_RESULT_LIMIT: Final[int] = 10

#: The most ids one search answers with, the API's own maximum. The title search
#: and the artist's objects are intersected, so each must reach far enough to
#: hold the other's members.
_SEARCH_LIMIT: Final[int] = 500

#: The most of an image read to find its size. Generous against the 40,798 bytes
#: measured, because the metadata ahead of the frame varies by photograph.
_HEAD_BYTES: Final[int] = 256 * 1024

#: The Met's own words for an id it does not have, with HTTP 404. Any other 404
#: is an answer this plugin does not recognise.
_NOT_FOUND: Final[str] = "ObjectID not found"

_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
_READ_TIMEOUT_SECONDS: Final[float] = 20.0

#: Start-of-frame markers: every SOFn except DHT (C4), JPG (C8) and DAC (CC),
#: which share the range and carry no frame size.
_START_OF_FRAME: Final[frozenset[int]] = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}

#: Markers that stand alone, with no length after them.
_STANDALONE: Final[frozenset[int]] = frozenset({0x01, *range(0xD0, 0xD9)})

#: The byte every marker starts with, and that may repeat as fill before one.
_MARKER: Final[int] = 0xFF

#: A segment's length counts its own two length bytes, so none is shorter.
_SHORTEST_SEGMENT: Final[int] = 2

#: A frame header's precision byte, then its height and width, two bytes each.
_FRAME_HEADER: Final[int] = 5


def object_url(object_id: int) -> str:
    """The address an instance of this object is recorded under, and the one this plugin's reader reads."""
    return f"{_OBJECT_PREFIX}{object_id}"


def claims(url: str) -> bool:
    """Whether `url` is the API object URL this plugin records: https, the API's host, the object's path, nothing else."""
    return _api_id(url) is not None


def _api_id(url: str) -> int | None:
    return _object_id(url, host=_API_HOST, path=_API_OBJECT)


def _web_id(url: str) -> int | None:
    return _object_id(url, host=_WEB_HOST, path=_WEB_OBJECT)


def _object_id(url: str, *, host: str, path: re.Pattern[str]) -> int | None:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.hostname != host or port is not None or parts.query or parts.fragment:
        return None
    match = path.fullmatch(parts.path)
    return int(match.group(1)) if match else None


def _on_image_host(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return parts.scheme == "https" and parts.hostname == _IMAGE_HOST and port is None


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
        # No redirect is followed: the API answers in place, and an image host
        # that redirected would take a read somewhere `_on_image_host` never checked.
        follow_redirects=False,
    )


class _Api:
    """The two questions this plugin asks the Met's API, shared by the finder and the reader."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None) -> None:
        self._http = _client(transport)
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        # The image host answers HTTP 406 to `Accept: application/json` (measured
        # 2026-10-06), so an image is asked for as one.
        self._image_headers = {"User-Agent": user_agent, "Accept": "image/*"}

    @contextmanager
    def image(self, url: str, *, first_bytes: int | None = None) -> Iterator[httpx.Response]:
        """A streamed read of an image on the Met's image host, and of nothing anywhere else.

        The one place this plugin reads an image, so the host check
        `security-model.md` § Source plugins claims has one owner. Transport
        errors propagate as `httpx.HTTPError`; each caller says what one means.
        """
        if not _on_image_host(url):
            raise ImageSearchFailure(f"{url!r} is not on the Met's image host, so it is not read.")
        headers = dict(self._image_headers)
        if first_bytes is not None:
            headers["Range"] = f"bytes=0-{first_bytes - 1}"
        with self._http.stream("GET", url, headers=headers) as response:
            yield response

    def object(self, object_id: int) -> Mapping[str, Any] | None:
        """The object's record, or None when the Met says it has no such object."""
        response = self._get(object_url(object_id), what=f"read object {object_id}")
        if response.status_code == httpx.codes.NOT_FOUND:
            if _json(response).get("message") == _NOT_FOUND:
                return None
            raise ImageSearchFailure(f"The Met answered HTTP 404 for object {object_id} without saying it has none.")
        payload = self._ok(response, what=f"read object {object_id}")
        if payload.get("objectID") != object_id:
            # Not the record asked for: that is could-not-be-asked, never "no image".
            raise ImageSearchFailure(f"The Met answered the read of object {object_id} without that object's record.")
        return payload

    def search(self, query: str, *, field: str) -> tuple[list[int], bool]:
        """The ids of objects with images whose `field` matches `query`, in the Met's order, and whether that is all of them.

        One page of `_SEARCH_LIMIT`. A match larger than that is cut, and says
        so, because an absence from a cut list is not evidence of anything.
        """
        params = {field: "true", "hasImages": "true", "q": query, "limit": str(_SEARCH_LIMIT)}
        response = self._get(_SEARCH_URL, what=f"search for {query!r}", params=params)
        payload = self._ok(response, what=f"search for {query!r}")
        total, ids = payload.get("total"), payload.get("objectIDs")
        if total == 0 and ids is None:
            return [], True
        if (
            not isinstance(total, int)
            or not isinstance(ids, list)
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)
        ):
            raise ImageSearchFailure(f"The Met's search for {query!r} answered in a shape it does not document.")
        return ids, total <= len(ids)

    def _get(self, url: str, *, what: str, params: Mapping[str, str] | None = None) -> httpx.Response:
        try:
            return self._http.get(url, params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Could not {what} at the Met: {exc}") from exc

    def _ok(self, response: httpx.Response, *, what: str) -> Mapping[str, Any]:
        if response.status_code != httpx.codes.OK:
            # A redirect lands here too: none is followed.
            raise ImageSearchFailure(f"Could not {what} at the Met: HTTP {response.status_code}.")
        payload = _json(response)
        if not payload:
            raise ImageSearchFailure(f"Could not {what} at the Met: the answer was not a JSON object.")
        return payload


def _json(response: httpx.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


#: What the image host answers for an image it no longer has. The record named
#: it, and the host says it is gone: this object offers nothing, and the rest of
#: the work's search stands. Any other refusal (403, 429, 5xx) says nothing about
#: the image, so it fails the search as could-not-be-asked.
_GONE: Final[frozenset[int]] = frozenset({httpx.codes.NOT_FOUND, httpx.codes.GONE})


class _ImageGone(Exception):
    """The image host says the image a record names is not there."""


class MetFinder:
    """The Met's public-domain originals of a work, found by Wikidata item or by search."""

    def __init__(
        self,
        *,
        user_agent: str,
        registry: Registry | None = None,
        transport: httpx.BaseTransport | None = None,
        preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
    ) -> None:
        self._api = _Api(user_agent=user_agent, transport=transport)
        self._registry = registry
        self._preview_max_bytes = preview_max_bytes

    @property
    def provider(self) -> str:
        return PROVIDER

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        """Every public-domain original the Met holds for this work, unjudged."""
        ids = self._recorded_ids(query.qid) if query.qid is not None else []
        how = "wikidata"
        if not ids:
            ids, how = self._searched_ids(query)
        read = ids[:_RESULT_LIMIT]
        found = []
        for object_id in read:
            record = self._api.object(object_id)
            image = None if record is None else self._image(object_id, record)
            if image is not None:
                found.append(image)
        log.info(
            "searched a museum collection for a work",
            extra={
                "event": "phase_two.searched",
                "provider": PROVIDER,
                "work_title": query.title,
                "by": how,
                "objects_matched": len(ids),
                "objects_read": len(read),
                "instances_usable": len(found),
            },
        )
        return found

    def fetch_preview(self, url: str) -> bytes | None:
        """The preview bytes, read against the preview ceiling, or `None`."""
        try:
            with self._api.image(url) as response:
                if response.status_code != httpx.codes.OK:
                    log.warning(
                        "could not cache a Met preview",
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
            # Off the image host: refused before any request, and said, as every
            # other preview that does not arrive is.
            log.warning(
                "refused a Met preview off its image host",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache a Met preview",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)

    def _recorded_ids(self, qid: ItemId) -> list[int]:
        """The Met objects the work's Wikidata item names, or none when it names none or no registry is configured."""
        if self._registry is None:
            return []
        try:
            pages = self._registry.pages_about(qid)
        except RegistryUnavailable as exc:
            raise ImageSearchFailure(f"Wikidata could not be asked for {qid}'s Met objects: {exc}") from exc
        ids: list[int] = []
        for page in pages:
            # Both of P3634's formatters are read, so a change in which one
            # Wikidata ranks first changes nothing here.
            object_id = _web_id(page) or _api_id(page)
            if object_id is not None and object_id not in ids:
                ids.append(object_id)
        return ids

    def _searched_ids(self, query: ImageQuery) -> tuple[list[int], str]:
        """Objects titled as the work, narrowed to the artist's when the Met knows the artist; and how they were chosen.

        **An empty answer says the Met holds nothing**, so one is given only
        when the lists behind it are whole. An artist the Met finds nothing for,
        perhaps spelt another way, and an intersection of lists cut at one page,
        leave the title's own first results instead, for the identity check to
        judge.
        """
        titled, titles_whole = self._api.search(query.title, field="title")
        if not titled or not query.artist:
            return titled, "title"
        by_artist, artist_whole = self._api.search(query.artist, field="artistOrCulture")
        if not by_artist:
            return titled, "title, the artist unknown to the Met"
        artists = set(by_artist)
        narrowed = [object_id for object_id in titled if object_id in artists]
        if not narrowed and not (titles_whole and artist_whole):
            return titled, "title, the artist's objects too many to narrow by"
        return narrowed, "title and artist"

    def _image(self, object_id: int, record: Mapping[str, Any]) -> FoundImage | None:
        original = record.get("primaryImage")
        if not original:
            # In copyright, or never photographed: the API offers no image.
            return None
        title = record.get("title")
        if not _on_image_host(original) or not isinstance(title, str) or not title.strip():
            log.warning(
                "skipping a Met object whose answer is not the shape measured",
                extra={"event": "met.unexpected_object", "provider": PROVIDER, "object_id": object_id},
            )
            return None
        artist = record.get("artistDisplayName")
        preview = record.get("primaryImageSmall")
        try:
            size = self._size(original)
        except _ImageGone:
            log.warning(
                "skipping a Met object whose image the image host says is gone",
                extra={"event": "met.image_gone", "provider": PROVIDER, "object_id": object_id},
            )
            return None
        return FoundImage(
            url=object_url(object_id),
            provider=PROVIDER,
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            title=title.strip(),
            artist=artist.strip() if isinstance(artist, str) and artist.strip() else None,
            preview_url=preview if _on_image_host(preview) else None,
            estimated_width=size[0] if size else None,
            estimated_height=size[1] if size else None,
            rights_status=RightsStatus.PUBLIC_DOMAIN if record.get("isPublicDomain") is True else RightsStatus.UNKNOWN,
        )

    def _size(self, url: str) -> tuple[int, int] | None:
        """The original's pixel size from its header, or None when the head holds no frame.

        Without a size phase 2 cannot judge the image against the floor and
        leaves it out, as it does Commons' unsized files. A host that cannot be
        read is could-not-be-asked, because the image was named and nothing
        was learned about it.
        """
        head = bytearray()
        try:
            with self._api.image(url, first_bytes=_HEAD_BYTES) as response:
                if response.status_code in _GONE:
                    raise _ImageGone(url)
                if response.status_code not in (httpx.codes.OK, httpx.codes.PARTIAL_CONTENT):
                    raise ImageSearchFailure(f"The Met's image host answered HTTP {response.status_code} for {url}.")
                for chunk in response.iter_bytes():
                    head.extend(chunk[: _HEAD_BYTES - len(head)])
                    size = jpeg_size(bytes(head))
                    if size is not None or len(head) >= _HEAD_BYTES:
                        return size
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Could not read the head of {url}: {exc}") from exc
        return jpeg_size(bytes(head))


class MetReader:
    """Read a Met object's API URL into its original image, fetched over plain HTTP."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api = _Api(user_agent=user_agent, transport=transport)

    def read(self, url: str) -> FetchLocator:
        object_id = _api_id(url)
        if object_id is None:
            raise ImageSearchFailure(f"{url!r} is not a Met API object URL, so there is no record to read.")
        record = self._api.object(object_id)
        if record is None:
            return FetchLocator.none(f"The Met has no object {object_id}.")
        original = record.get("primaryImage")
        if not original:
            return FetchLocator.none(f"The Met offers no open-access image of object {object_id}.")
        if not _on_image_host(original):
            raise ImageSearchFailure(f"The Met named an image for object {object_id} off its image host.")
        return FetchLocator.direct(original)


def jpeg_size(head: bytes) -> tuple[int, int] | None:
    """The (width, height) in a JPEG's start-of-frame segment, or `None` when `head` holds none.

    `None` covers a body that is not a JPEG and a head cut short before the
    frame, which the caller cannot tell apart and need not: either way the size
    is unknown.
    """
    if head[:2] != b"\xff\xd8":
        return None
    position = 2
    while position + 4 <= len(head):
        if head[position] != _MARKER:
            return None
        marker = head[position + 1]
        if marker == _MARKER:
            # Fill bytes before a marker are allowed.
            position += 1
            continue
        if marker in _STANDALONE:
            position += 2
            continue
        length = int.from_bytes(head[position + 2 : position + 4], "big")
        if length < _SHORTEST_SEGMENT:
            return None
        if marker in _START_OF_FRAME:
            frame = head[position + 4 : position + 4 + _FRAME_HEADER]
            if len(frame) < _FRAME_HEADER:
                return None
            height = int.from_bytes(frame[1:3], "big")
            width = int.from_bytes(frame[3:5], "big")
            return (width, height) if width and height else None
        position += 2 + length
    return None


def _create(context: SourceContext) -> SourceParts:
    """The Met, found by Wikidata item when a registry is configured and by search always.

    It never declines: the API needs no key, and it names itself with the
    deployment's own agent (`ACQUISITION_USER_AGENT`).
    """
    return SourceParts(
        finder=MetFinder(user_agent=context.user_agent, registry=context.registry, preview_max_bytes=context.preview_max_bytes),
        reader=MetReader(user_agent=context.user_agent),
    )


#: What the `met` entry point names. Written for interface major 1 as a literal,
#: as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create, claims=claims)
