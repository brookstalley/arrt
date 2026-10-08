"""SMK (Statens Museum for Kunst, the National Gallery of Denmark) through its open API, as one image source.

It finds a work's object at SMK from the work's Wikidata item or by search, and
reports the object's original image, in copyright or not. It needs no key. Every
shape below was measured against the live API on 2026-10-06
(`smk-api-findings.md`). Five of them decide what this module does:

**SMK serves its in-copyright works at full size**, and says which they are:
`public_domain` is false and `rights` is SMK's own page on the use of its
material. Rights are recorded, never a reason to leave an image out.

**The pages Wikidata records are a JavaScript front end**, and the item spells
them several ways (`collection.smk.dk/#/en/detail/<n>`, the same without the
language, `open.smk.dk/artwork/image/<n>`, with `/en/`, with a search's query
string). This plugin never fetches one: it takes the object number from the page
and asks the API. An image found from a page is reported under the page exactly
as the item spells it, because that link is what identifies it
(`source-plugins.md` § What a finder or reader must report).

**An object number may hold a slash** (`KKS2020-3/16`), which an item may spell
percent-encoded in a fragment (`KKS12485%2F6`), and a letter outside ASCII
(`KMSst28Ø`). The API matches it without regard to case.

**`image_native` is the largest image SMK gives, at the size the record
states**, served by the API's own host with no redirect. For an object with a
IIIF image it is the full original (7174 × 5536 for a public-domain object and
6296 × 4370 for an in-copyright one, as stated); for one without, it is the same
file as the thumbnail, 1600 pixels on its long side (1229 × 1600, as stated). So
the reader answers with it, and the record's size is the master's.

**An object number SMK does not have is an empty `items` list, with HTTP 200.**
"""

import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Final
from urllib.parse import SplitResult, parse_qsl, unquote, urlsplit

import httpx

from arrt.library.sources import (
    DEFAULT_PREVIEW_MAX_BYTES,
    AcquisitionMethod,
    FetchLocator,
    FoundImage,
    ImageQuery,
    ImageQueryUnanswerable,
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
PROVIDER: Final[str] = "smk"

#: The name a curator knows this source by, for every sentence that names it
#: (`names.museum_name`).
MUSEUM: Final[str] = "SMK, National Gallery of Denmark"

_API_HOST: Final[str] = "api.smk.dk"
_OBJECT_URL: Final[str] = f"https://{_API_HOST}/api/v1/art/"
_SEARCH_URL: Final[str] = f"https://{_API_HOST}/api/v1/art/search/"

#: Where `image_native` points, on the API's own host: the IIIF original's
#: download, or, for an object with no IIIF image, its only file.
_DOWNLOAD_PATH: Final[str] = "/api/v1/download/"
_THUMBNAIL_PATH: Final[str] = "/api/v1/thumbnail/"

#: Where `image_thumbnail` points for an object with a IIIF image: a
#: 1024-pixel-wide rendering. One without names its file on `_THUMBNAIL_PATH`.
_THUMBNAIL_HOST: Final[str] = "iip-thumb.smk.dk"

#: The front end's two hosts, whose pages Wikidata records and search answers name.
_COLLECTION_HOST: Final[str] = "collection.smk.dk"
_OPEN_HOST: Final[str] = "open.smk.dk"

#: `collection.smk.dk`'s object page is a fragment: `#/en/detail/<n>`, or `#/detail/<n>`.
_COLLECTION_FRAGMENT: Final[re.Pattern[str]] = re.compile(r"/(?:[a-z]{2}/)?detail/(.+)")

#: `open.smk.dk`'s object page: `/artwork/image/<n>`, or `/en/artwork/image/<n>`,
#: with a trailing slash on some items.
_OPEN_PATH: Final[re.Pattern[str]] = re.compile(r"/(?:[a-z]{2}/)?artwork/image/(.+?)/?")

#: The API's object URL, as a record's own `object_url` spells it, with or without the slash.
_API_PATH: Final[re.Pattern[str]] = re.compile(r"/api/v1/art/?")

#: An object number: word characters, dots and hyphens, in parts a slash may
#: join (`KMS1`, `KKS2020-3/16`, `KMSst28Ø`). Anything else is not one, and a URL
#: carrying it is claimed by nobody.
_OBJECT_NUMBER: Final[re.Pattern[str]] = re.compile(r"\w[\w.\-]*(?:/[\w.\-]+)*")
_OBJECT_NUMBER_MAX: Final[int] = 64

#: SMK's own page on the use of its material, which `rights` names for a work in
#: copyright: the Danish page by default, the English one when asked in English.
#: Any other value with `public_domain` false is not a statement read here.
_IN_COPYRIGHT: Final[frozenset[str]] = frozenset(
    {
        "https://www.smk.dk/section/brug-af-museets-materiale/",
        "https://www.smk.dk/en/section/use-of-smk-material/",
    }
)

#: The API answers titles in English where SMK has one, and in Danish where not.
#: A work's title here is in English (Wikidata's English label, or Ask's
#: proposal), so English is what the identity check can compare.
_LANGUAGE: Final[str] = "en"

#: How many objects one work reads, by item or by search. The identity check
#: above the seam, not this number, decides what survives.
_RESULT_LIMIT: Final[int] = 10

_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
_READ_TIMEOUT_SECONDS: Final[float] = 20.0


def claims(url: str) -> bool:
    """Whether `url` is an SMK object page or API object URL: the shapes this plugin records, on SMK's hosts only."""
    return object_number(url) is not None


def object_number(url: str) -> str | None:
    """The object number an SMK page or API object URL names, or None when `url` is not one."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if port is not None or parts.username is not None or parts.password is not None:
        return None
    read = _READERS.get((parts.scheme, parts.hostname or ""))
    number = read(parts) if read is not None else None
    if number is None or len(number) > _OBJECT_NUMBER_MAX or not _OBJECT_NUMBER.fullmatch(number):
        return None
    return number


def _collection_number(parts: SplitResult) -> str | None:
    if parts.path not in ("", "/") or parts.query:
        return None
    match = _COLLECTION_FRAGMENT.fullmatch(unquote(parts.fragment))
    return match.group(1) if match else None


def _open_number(parts: SplitResult) -> str | None:
    # A query string is kept: items record pages a search on the site opened
    # (`?q=KMS4585&page=0`), and the object is in the path.
    if parts.fragment:
        return None
    match = _OPEN_PATH.fullmatch(unquote(parts.path))
    return match.group(1) if match else None


def _api_number(parts: SplitResult) -> str | None:
    if not _API_PATH.fullmatch(parts.path) or parts.fragment:
        return None
    query = parse_qsl(parts.query, keep_blank_values=True)
    if len(query) != 1 or query[0][0] != "object_number":
        return None
    return query[0][1]


#: (scheme, host) → where that URL keeps its object number. Items record the
#: front end's pages over http as well as https; the API is https only.
_READERS: Final[Mapping[tuple[str, str], Callable[[SplitResult], str | None]]] = {
    **{(scheme, _COLLECTION_HOST): _collection_number for scheme in ("http", "https")},
    **{(scheme, _OPEN_HOST): _open_number for scheme in ("http", "https")},
    ("https", _API_HOST): _api_number,
}


def _on_host(url: object, *, host: str, paths: tuple[str, ...] = ("/",)) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return parts.scheme == "https" and parts.hostname == host and port is None and parts.path.startswith(paths)


def _is_original(url: object) -> bool:
    """Whether `url` is on the API's image paths, the one place this plugin takes an original from."""
    return _on_host(url, host=_API_HOST, paths=(_DOWNLOAD_PATH, _THUMBNAIL_PATH))


def _is_thumbnail(url: object) -> bool:
    """Whether `url` is where SMK keeps previews, the one place this plugin reads one from."""
    return _on_host(url, host=_THUMBNAIL_HOST) or _on_host(url, host=_API_HOST, paths=(_THUMBNAIL_PATH,))


def _words(text: str) -> str:
    """`text` as the words in it.

    The search reads its keys as a query language: a title with quotes and
    brackets found nothing where its words alone found the work (measured).
    """
    return " ".join(re.findall(r"\w+", text))


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
        # No redirect is followed: the API answers in place, and a thumbnail
        # host that redirected would take a read somewhere `_is_thumbnail` never checked.
        follow_redirects=False,
    )


class _Api:
    """The two questions this plugin asks SMK's API, shared by the finder and the reader."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None) -> None:
        self._http = _client(transport)
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._image_headers = {"User-Agent": user_agent, "Accept": "image/*"}

    @contextmanager
    def thumbnail(self, url: str) -> Iterator[httpx.Response]:
        """A streamed read of a thumbnail on SMK's thumbnail host, and of nothing anywhere else."""
        if not _is_thumbnail(url):
            raise ImageSearchFailure(f"{url!r} is not where SMK keeps its previews, so it is not read.")
        with self._http.stream("GET", url, headers=self._image_headers) as response:
            yield response

    def object(self, number: str) -> Mapping[str, Any] | None:
        """The object's record, or None when SMK says it has no such object."""
        what = f"read object {number}"
        items = _items(self._ok(self._get(_OBJECT_URL, what=what, params=[("object_number", number)]), what=what), what=what)
        if not items:
            return None
        answered = items[0].get("object_number")
        if len(items) != 1 or not isinstance(answered, str) or answered.casefold() != number.casefold():
            # Not the record asked for: that is could-not-be-asked, never "no image".
            raise ImageSearchFailure(f"SMK answered the read of object {number} without that object's record.")
        return items[0]

    def search(self, keys: str, *, fields: Sequence[str]) -> list[Mapping[str, Any]]:
        """The first `_RESULT_LIMIT` objects with an image whose `fields` hold every word of `keys`, in SMK's order."""
        params = [("keys", keys), *(("qfields", field) for field in fields), ("filters", "[has_image:true]")]
        params.append(("rows", str(_RESULT_LIMIT)))
        what = f"search for {keys!r}"
        payload = self._ok(self._get(_SEARCH_URL, what=what, params=params), what=what)
        found = payload.get("found")
        if not isinstance(found, int) or isinstance(found, bool):
            raise ImageSearchFailure(f"SMK's {what} answered in a shape it does not document.")
        return _items(payload, what=what)[:_RESULT_LIMIT]

    def _get(self, url: str, *, what: str, params: list[tuple[str, str]]) -> httpx.Response:
        try:
            return self._http.get(url, params=[*params, ("lang", _LANGUAGE)], headers=self._headers)
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Could not {what} at SMK: {exc}") from exc

    def _ok(self, response: httpx.Response, *, what: str) -> Mapping[str, Any]:
        if response.status_code != httpx.codes.OK:
            # A redirect lands here too: none is followed.
            raise ImageSearchFailure(f"Could not {what} at SMK: HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise ImageSearchFailure(f"Could not {what} at SMK: the answer was not a JSON object.")
        return payload


def _items(payload: Mapping[str, Any], *, what: str) -> list[Mapping[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ImageSearchFailure(f"SMK's answer to the {what} is not a list of objects.")
    return items


def _rights(record: Mapping[str, Any]) -> RightsStatus:
    """SMK's own statement, read for what it says; a value never seen is not guessed at."""
    if record.get("public_domain") is True:
        return RightsStatus.PUBLIC_DOMAIN
    if record.get("public_domain") is False and record.get("rights") in _IN_COPYRIGHT:
        return RightsStatus.IN_COPYRIGHT
    return RightsStatus.UNKNOWN


def _first_text(values: object, key: str | None = None) -> str | None:
    """The first non-blank string in a list of strings, or of objects under `key`."""
    if not isinstance(values, list):
        return None
    for value in values:
        text = value.get(key) if key is not None and isinstance(value, dict) else value
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _dimension(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


class SmkFinder:
    """SMK's originals of a work, found by the pages its Wikidata item records or by search."""

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
        """Every original SMK holds for this work, in copyright or not, unjudged.

        **An item whose SMK pages name no object SMK knows is searched for**,
        as an item with no SMK page is: a number SMK has dropped says nothing
        about whether SMK holds the work under another.
        """
        found: list[FoundImage] | None = None
        how = "wikidata"
        if query.qid is not None:
            found = self._by_item(query.qid)
        if found is None:
            found, how = self._by_search(query)
        log.info(
            "searched a museum collection for a work",
            extra={
                "event": "phase_two.searched",
                "provider": PROVIDER,
                "work_title": query.title,
                "by": how,
                "instances_usable": len(found),
            },
        )
        return found

    def fetch_preview(self, url: str) -> bytes | None:
        """The preview bytes, read against the preview ceiling, or `None`."""
        try:
            with self._api.thumbnail(url) as response:
                if response.status_code != httpx.codes.OK:
                    log.warning(
                        "could not cache an SMK preview",
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
                "refused an SMK preview from elsewhere",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache an SMK preview",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)

    def _by_item(self, qid: ItemId) -> list[FoundImage] | None:
        """The images of the objects the item's SMK pages name, each under its page; None when they name none SMK knows."""
        if self._registry is None:
            return None
        try:
            pages = self._registry.pages_about(qid)
        except RegistryUnavailable as exc:
            raise ImageSearchFailure(f"Wikidata could not be asked for {qid}'s SMK pages: {exc}") from exc
        numbered: dict[str, tuple[str, str]] = {}
        for page in pages:
            number = object_number(page)
            if number is not None:
                numbered.setdefault(number.casefold(), (number, page))
        known = False
        found: list[FoundImage] = []
        for number, page in list(numbered.values())[:_RESULT_LIMIT]:
            record = self._api.object(number)
            if record is None:
                log.warning(
                    "skipping an SMK page whose object SMK says it does not have",
                    extra={"event": "smk.object_not_found", "provider": PROVIDER, "object_number": number},
                )
                continue
            known = True
            image = self._image(record, url=page)
            if image is not None:
                found.append(image)
        return found if known else None

    def _by_search(self, query: ImageQuery) -> tuple[list[FoundImage], str]:
        """Objects whose titles hold the title's words, narrowed to the artist's where SMK finds any by both.

        **A search by title and artist that finds nothing leaves the title's own
        results**, because an artist SMK spells another way would otherwise
        read as SMK holding nothing.
        """
        title = _words(query.title)
        if not title:
            raise ImageQueryUnanswerable(f"{query.title!r} has no words to search SMK's titles for.")
        artist = _words(query.artist) if query.artist else ""
        records: list[Mapping[str, Any]] = []
        how = "title"
        if artist:
            records = self._api.search(f"{title} {artist}", fields=("titles", "creator"))
            how = "title and artist" if records else "title, the artist unknown to SMK"
        if not records:
            records = self._api.search(title, fields=("titles",))
        found = []
        for record in records:
            page = record.get("frontend_url")
            number = object_number(page) if isinstance(page, str) else None
            answered = record.get("object_number")
            if number is None or not isinstance(answered, str) or number.casefold() != answered.casefold():
                # Reported under a page the reader could not read back to this object.
                log.warning(
                    "skipping an SMK search hit whose page is not the shape measured",
                    extra={"event": "smk.unexpected_object", "provider": PROVIDER, "object_number": answered},
                )
                continue
            image = self._image(record, url=page)
            if image is not None:
                found.append(image)
        return found, how

    def _image(self, record: Mapping[str, Any], *, url: str) -> FoundImage | None:
        """The object's original, reported under `url`; None when SMK offers no image of it."""
        original = record.get("image_native")
        if record.get("has_image") is not True or not original:
            return None
        title = _first_text(record.get("titles"), "title")
        if not _is_original(original) or title is None:
            log.warning(
                "skipping an SMK object whose answer is not the shape measured",
                extra={"event": "smk.unexpected_object", "provider": PROVIDER, "object_number": record.get("object_number")},
            )
            return None
        preview = record.get("image_thumbnail")
        return FoundImage(
            url=url,
            provider=PROVIDER,
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            title=title,
            artist=_first_text(record.get("artist")),
            preview_url=preview if _is_thumbnail(preview) else None,
            estimated_width=_dimension(record.get("image_width")),
            estimated_height=_dimension(record.get("image_height")),
            rights_status=_rights(record),
        )


class SmkReader:
    """Read an SMK page or API object URL into the object's original, fetched over plain HTTP."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api = _Api(user_agent=user_agent, transport=transport)

    def read(self, url: str) -> FetchLocator:
        number = object_number(url)
        if number is None:
            raise ImageSearchFailure(f"{url!r} is not an SMK object page, so there is no record to read.")
        record = self._api.object(number)
        if record is None:
            return FetchLocator.none(f"SMK has no object {number}.")
        original = record.get("image_native")
        if record.get("has_image") is not True or not original:
            return FetchLocator.none(f"SMK offers no image of object {number}.")
        if not _is_original(original):
            raise ImageSearchFailure(f"SMK named an image for object {number} off the API's image paths.")
        return FetchLocator.direct(original)


def _create(context: SourceContext) -> SourceParts:
    """SMK, found by Wikidata item when a registry is configured and by search always.

    It never declines: the API needs no key, and it names itself with the
    deployment's own agent (`ACQUISITION_USER_AGENT`).
    """
    return SourceParts(
        finder=SmkFinder(user_agent=context.user_agent, registry=context.registry, preview_max_bytes=context.preview_max_bytes),
        reader=SmkReader(user_agent=context.user_agent),
    )


#: What the `smk` entry point names. Written for interface major 1 as a literal,
#: as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create, claims=claims)
