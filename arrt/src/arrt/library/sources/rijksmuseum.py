"""The Rijksmuseum, through its Linked Art records, its search and IIIF, as one image source.

It finds a work's object from the record its Wikidata item names, or by searching
the museum's collection for the work's maker and title, and reports the object's
image from its IIIF image service. It needs no key and reads no web page. Every
shape below was measured on 2026-10-07 (`linked-art-findings.md`). Six of them
decide what this module does:

**Wikidata reaches few of the museum's works, so the finder also searches.** The
museum holds hundreds of thousands of imaged objects, and 6,413 Wikidata items
carry its ID. An item naming a record is read through that record; any other work
is searched for, as `getty` does.

**The ID is the record's number.** P13234's formatter builds
`https://id.rijksmuseum.nl/<n>`, which answers the object's Linked Art record to a
Linked Art `Accept`, and sends a browser to the museum's page. A number the museum
does not know answers 400 or 404.

**The search matches the museum's own spelling of a maker.** "Piet Mondrian" finds
nothing and "Piet Mondriaan" finds his prints. It folds accents for some makers and
not others ("Isaac Israëls" finds nothing, "Isaac Israels" finds his paintings), so a
name with accents that finds nothing is asked once more without them. Each hit costs
four requests, so a work with no maker is not searched for.

**The image is three records away.** The object `shows` a VisualItem, which is
`digitally_shown_by` a DigitalObject, whose `access_point` is a `full/max` request
on the museum's IIIF host. The VisualItem carries the rights: the Public Domain
Mark, or rightsstatements.org's `InC` on in-copyright works, which the museum
serves too. They gate nothing.

**The maker is stated three ways.** A part of the production names the person
inline; or assigns them, with the evidence ("signed by artist", "mentioned on
object") in parentheses after the name; or assigns them under an attribution
("attributed to Rembrandt van Rijn"). Evidence is not an attribution, so it is
dropped; an attribution is kept, so the identity check is told the work is not
certainly the master's.

**The image service declares a 17.55 MP ceiling.** Most originals are larger, and
are fetched as tiles, which `TILE_MAX_PIXELS` bounds; the rest in one request.
"""

import logging
import re
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Final, NamedTuple
from urllib.parse import urlsplit

import httpx

from arrt.library.sources import (
    DEFAULT_PREVIEW_MAX_BYTES,
    AcquisitionMethod,
    FetchLocator,
    FoundImage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
    ImageService,
    ItemId,
    LocatorKind,
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
PROVIDER: Final[str] = "rijksmuseum"

_RECORD_HOST: Final[str] = "id.rijksmuseum.nl"
#: An object's number, as Wikidata's format for P13234 states it.
_OBJECT_NUMBER: Final[re.Pattern[str]] = re.compile(r"/(\d{7,9})")
#: Any record on the museum's ID host: objects, VisualItems and DigitalObjects alike.
_RECORD: Final[re.Pattern[str]] = re.compile(r"https://id\.rijksmuseum\.nl/\d+")
_SEARCH_URL: Final[str] = "https://data.rijksmuseum.nl/search/collection"
_SERVICE: Final[re.Pattern[str]] = re.compile(r"https://iiif\.micr\.io/[0-9A-Za-z]+")
_ACCESS_POINT: Final[re.Pattern[str]] = re.compile(rf"({_SERVICE.pattern})/full/max/0/default\.jpg")
_IMAGE_PREFIX: Final[str] = "https://iiif.micr.io/"

#: The statuses with which the museum answers a number it does not know.
_UNKNOWN: Final[frozenset[int]] = frozenset({httpx.codes.BAD_REQUEST, httpx.codes.NOT_FOUND})

#: The longest side asked for in one request. The service's declared `maxArea`
#: (17,550,000) binds long before it, so this only refuses an absurdly thin strip.
_DIRECT_MAX_SIDE: Final[int] = 16384

#: The longest side a preview is asked at.
_PREVIEW_SIZE: Final[int] = 400

#: How many objects one work reads. The identity check above the seam, not this
#: number, decides what survives.
_RESULT_LIMIT: Final[int] = 10

#: How the record classifies a preferred title, a maker's name statement, and English.
_PREFERRED: Final[str] = "http://vocab.getty.edu/aat/300404670"
_NAME_STATEMENT: Final[str] = "http://vocab.getty.edu/aat/300435417"
_ENGLISH: Final[str] = "http://vocab.getty.edu/aat/300388277"

#: The museum's names for an unknown hand, in English and Dutch.
_ANONYMOUS: Final[frozenset[str]] = frozenset({"anonymous", "anoniem"})

#: The evidence for an assignment, after the name ("Karel Appel (signed by artist)").
_EVIDENCE: Final[re.Pattern[str]] = re.compile(r"\s*\([^()]*\)$")

#: What the VisualItem's rights say, read for what they say. Anything else is unknown, not guessed at.
_PUBLIC_DOMAIN: Final[re.Pattern[str]] = re.compile(r"https?://creativecommons\.org/publicdomain/(mark|zero)/1\.0/?")
_IN_COPYRIGHT: Final[re.Pattern[str]] = re.compile(r"https?://rightsstatements\.org/vocab/InC(-[A-Z]+)*/1\.0/?")

_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
_READ_TIMEOUT_SECONDS: Final[float] = 20.0


def claims(url: str) -> bool:
    """Whether `url` is a Rijksmuseum object record: the shape Wikidata's formatter builds, on the museum's ID host only."""
    return number_of(url) is not None


def number_of(url: str) -> str | None:
    """The object number a Rijksmuseum record URL names, or None when `url` is not one."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or port is not None or parts.username is not None or parts.password is not None:
        return None
    if parts.query or parts.fragment or parts.hostname != _RECORD_HOST:
        return None
    match = _OBJECT_NUMBER.fullmatch(parts.path)
    return match.group(1) if match else None


def _record_url(number: str) -> str:
    return f"https://{_RECORD_HOST}/{number}"


def _folded(name: str) -> str:
    """`name` with its accents removed: "Israëls" is "Israels"."""
    return "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))


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
        # No redirect is followed: every host answers in place, and a redirect
        # would take a read somewhere the plugin's own checks never saw.
        follow_redirects=False,
    )


class _Rijksmuseum:
    """The things this plugin asks the Rijksmuseum, shared by the finder and the reader."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None) -> None:
        self._http = _client(transport)
        self._headers = {"User-Agent": user_agent, "Accept": "application/ld+json"}
        self._info_headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._image_headers = {"User-Agent": user_agent, "Accept": "image/*"}

    def search(self, *, title: str, creator: str) -> list[tuple[str, str]]:
        """The records of objects with an image whose title and maker match, each with its number, in the museum's order."""
        what = f"search for {title!r} by {creator!r}"
        params = {"title": title, "creator": creator, "imageAvailable": "true"}
        page = self._json(self._get(_SEARCH_URL, headers=self._headers, params=params, what=what), what=what)
        items = page.get("orderedItems")
        if page.get("type") != "OrderedCollectionPage" or not isinstance(items, list):
            raise ImageSearchFailure(f"Could not {what} at the Rijksmuseum: the answer was not a page of results.")
        found = []
        for item in items:
            record = item.get("id") if isinstance(item, Mapping) else None
            number = number_of(record) if isinstance(record, str) else None
            if number is None:
                raise ImageSearchFailure("The Rijksmuseum's search answered with something other than its object records.")
            found.append((str(record), number))
        return found

    def object(self, number: str) -> Mapping[str, Any] | None:
        """An object's Linked Art record; None when the museum does not know the number."""
        what = f"read object {number}"
        response = self._get(_record_url(number), headers=self._headers, what=what)
        if response.status_code in _UNKNOWN:
            log.warning(
                "skipping a Rijksmuseum number the museum does not know",
                extra={"event": "rijksmuseum.object_not_found", "provider": PROVIDER, "number": number},
            )
            return None
        record = self._json(response, what=what)
        if record.get("type") != "HumanMadeObject":
            raise ImageSearchFailure(f"The Rijksmuseum's record {number} is not an object.")
        return record

    def linked(self, url: object, *, kind: str) -> Mapping[str, Any]:
        """A record another record links to, on the museum's ID host only, of the type expected."""
        if not isinstance(url, str) or _RECORD.fullmatch(url) is None:
            raise ImageSearchFailure(f"The Rijksmuseum names a {kind} off its ID host ({url!r}).")
        what = f"read a {kind}"
        record = self._json(self._get(url, headers=self._headers, what=what), what=what)
        if record.get("type") != kind:
            raise ImageSearchFailure(f"The Rijksmuseum's {url} is not a {kind}.")
        return record

    def service(self, base: str) -> ImageService:
        """The image service at `base`, read from its `info.json`.

        `base` is only ever the service an access point of `_ACCESS_POINT`'s shape
        names, which pins it to the museum's image host.
        """
        what = "read an image service"
        info = self._json(self._get(f"{base}/info.json", headers=self._info_headers, what=what), what=what)
        service = ImageService.from_info(info)
        if service.id != base:
            raise ImageSearchFailure(f"The Rijksmuseum's image service describes another image ({service.id}).")
        return service

    @contextmanager
    def preview(self, url: str) -> Iterator[httpx.Response]:
        """A streamed read of a rendering on the museum's image host, and of nothing anywhere else."""
        if not _on_image_host(url):
            raise ImageSearchFailure(f"{url!r} is not on the Rijksmuseum's image service, so it is not read.")
        with self._http.stream("GET", url, headers=self._image_headers) as response:
            yield response

    def _get(self, url: str, *, headers: Mapping[str, str], what: str, params: Mapping[str, str] | None = None) -> httpx.Response:
        try:
            return self._http.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Could not {what} at the Rijksmuseum: {exc}") from exc

    def _json(self, response: httpx.Response, *, what: str) -> Mapping[str, Any]:
        if response.status_code != httpx.codes.OK:
            # A redirect lands here too: none is followed.
            raise ImageSearchFailure(f"Could not {what} at the Rijksmuseum: HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise ImageSearchFailure(f"Could not {what} at the Rijksmuseum: the answer was not a JSON object.")
        return payload


def _on_image_host(url: object) -> bool:
    """Whether `url` is on the museum's image service, the one place this plugin reads or offers an image from.

    The prefix pins the scheme, the host and the absence of a port and of
    credentials together: a URL's authority ends at its first `/`, and the prefix
    carries that `/`.
    """
    return isinstance(url, str) and url.startswith(_IMAGE_PREFIX)


def _classified(entry: Mapping[str, Any], kind: str) -> bool:
    return any(k.get("id") == kind for k in _entries(entry, "classified_as"))


def _english(entry: Mapping[str, Any]) -> bool:
    return any(language.get("id") == _ENGLISH for language in _entries(entry, "language"))


def _entries(record: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = record.get(key)
    return [entry for entry in value if isinstance(entry, Mapping)] if isinstance(value, list) else []


def _text(value: object) -> str | None:
    return " ".join(value.split()) if isinstance(value, str) and value.strip() else None


def _title(record: Mapping[str, Any], *, asked: str | None) -> str | None:
    """The record's title equal to the one asked for, ignoring case and spacing; else its preferred English title.

    Failing those, its first preferred title in any language (some objects are
    titled only in Dutch), then its first title.
    """
    titles = [
        (text, _classified(name, _PREFERRED), _english(name))
        for name in _entries(record, "identified_by")
        if name.get("type") == "Name" and (text := _text(name.get("content"))) is not None
    ]
    if asked is not None:
        wanted = " ".join(asked.split()).casefold()
        same = next((text for text, _, _ in titles if text.casefold() == wanted), None)
        if same is not None:
            return same
    preferred = [(text, english) for text, is_preferred, english in titles if is_preferred]
    return next(
        (text for text, english in preferred if english),
        preferred[0][0] if preferred else titles[0][0] if titles else None,
    )


def _notation(person: Mapping[str, Any]) -> str | None:
    """A person's name as the record writes it inline, in English where it has English."""
    names = [
        (entry.get("@language"), text)
        for entry in _entries(person, "notation")
        if (text := _text(entry.get("@value"))) is not None
    ]
    return next((text for language, text in names if language == "en"), names[0][1] if names else None)


def _statement(part: Mapping[str, Any]) -> str | None:
    """The part's statement of its maker's name, in English where it has English."""
    statements = [
        (_english(entry), text)
        for entry in _entries(part, "referred_to_by")
        if _classified(entry, _NAME_STATEMENT) and (text := _text(entry.get("content"))) is not None
    ]
    return next((text for english, text in statements if english), statements[0][1] if statements else None)


def _artist(record: Mapping[str, Any]) -> str | None:
    """The work's maker, with any attribution the museum makes; None for an unknown hand.

    The first part of the production that names a maker is read, in the museum's
    order; later parts name a publisher or printer, and a part naming the design
    a print is after names no maker of this object.
    """
    production = record.get("produced_by")
    if not isinstance(production, Mapping):
        return None
    for part in _entries(production, "part"):
        makers = _entries(part, "carried_out_by")
        assignments = [a for a in _entries(part, "assigned_by") if a.get("assigned_property") == "carried_out_by"]
        if makers:
            name = _notation(makers[0])
        elif assignments:
            name = _statement(part)
            if name is not None and not any(_entries(a, "classified_as") for a in assignments):
                # Evidence the maker made it ("signed by artist"), not an
                # attribution: the name is compared without it.
                name = _EVIDENCE.sub("", name) or None
        else:
            continue
        return None if name is None or name.casefold() in _ANONYMOUS else name
    return None


def _rights(visual_item: Mapping[str, Any]) -> RightsStatus:
    """What the VisualItem's rights say about the object's image, which the museum states per image."""
    for right in _entries(visual_item, "subject_to"):
        for kind in _entries(right, "classified_as"):
            stated = kind.get("id")
            if isinstance(stated, str) and _PUBLIC_DOMAIN.fullmatch(stated):
                return RightsStatus.PUBLIC_DOMAIN
            if isinstance(stated, str) and _IN_COPYRIGHT.fullmatch(stated):
                return RightsStatus.IN_COPYRIGHT
    return RightsStatus.UNKNOWN


class _Shown(NamedTuple):
    """An object's image, as the three records past the object describe it."""

    service: ImageService
    rights: RightsStatus


def _shown(rijks: _Rijksmuseum, record: Mapping[str, Any]) -> _Shown | None:
    """The object's image service and its rights; None when the museum shows no image of it."""
    shows = _entries(record, "shows")
    if not shows:
        return None
    visual_item = rijks.linked(shows[0].get("id"), kind="VisualItem")
    shown_by = _entries(visual_item, "digitally_shown_by")
    if not shown_by:
        return None
    digital = rijks.linked(shown_by[0].get("id"), kind="DigitalObject")
    points = _entries(digital, "access_point")
    match = _ACCESS_POINT.fullmatch(str(points[0].get("id"))) if points else None
    if match is None:
        raise ImageSearchFailure(f"The Rijksmuseum's {digital.get('id')} names an image this plugin does not read.")
    return _Shown(rijks.service(match.group(1)), _rights(visual_item))


def _numbered(pages: Sequence[str]) -> list[tuple[str, str]]:
    """Each Rijksmuseum object the pages name, once, under the first page naming it, at most `_RESULT_LIMIT` of them."""
    numbers: dict[str, str] = {}
    for page in pages:
        number = number_of(page)
        if number is not None:
            numbers.setdefault(number, page)
    return list(numbers.items())[:_RESULT_LIMIT]


class RijksmuseumFinder:
    """The image of a work at the Rijksmuseum, found from the record its Wikidata item names, or by its maker and title."""

    def __init__(
        self,
        *,
        user_agent: str,
        registry: Registry | None,
        transport: httpx.BaseTransport | None = None,
        preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
    ) -> None:
        self._rijks = _Rijksmuseum(user_agent=user_agent, transport=transport)
        self._registry = registry
        self._preview_max_bytes = preview_max_bytes

    @property
    def provider(self) -> str:
        return PROVIDER

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        """The image of each Rijksmuseum object the work's item names, or else its search finds, in copyright or not, unjudged.

        **An item whose records name no object the museum knows is searched
        for**, as an item with no record is: a number the museum has dropped says
        nothing about whether it holds the work under another.
        """
        found: list[FoundImage] | None = None
        how = "wikidata"
        if query.qid is not None:
            found = self._by_item(query.qid)
        if found is None:
            found, how = self._by_search(query), "maker and title"
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
            with self._rijks.preview(url) as response:
                if response.status_code != httpx.codes.OK:
                    log.warning(
                        "could not cache a Rijksmuseum preview",
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
                "refused a Rijksmuseum preview from elsewhere",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache a Rijksmuseum preview",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)

    def _by_item(self, qid: ItemId) -> list[FoundImage] | None:
        """The images of the objects the item's records name. None when the item names no object the museum knows."""
        if self._registry is None:
            return None
        try:
            pages = self._registry.pages_about(qid)
        except RegistryUnavailable as exc:
            raise ImageSearchFailure(f"Wikidata could not be asked for {qid}'s Rijksmuseum records: {exc}") from exc
        records = [(page, record) for number, page in _numbered(pages) if (record := self._rijks.object(number)) is not None]
        if not records:
            return None
        return [image for page, record in records if (image := self._image(record, page=page, title=None)) is not None]

    def _by_search(self, query: ImageQuery) -> list[FoundImage]:
        """The objects with an image whose maker and title match the work's, as the museum's search matches them."""
        if not query.artist or not query.artist.strip():
            raise ImageQueryUnanswerable("The Rijksmuseum is searched by a work's maker, and this work names none.")
        title, artist = " ".join(query.title.split()), " ".join(query.artist.split())
        if not title:
            raise ImageQueryUnanswerable("The Rijksmuseum is searched by a work's title, and this work's is blank.")
        hits = self._rijks.search(title=title, creator=artist)
        if not hits and _folded(artist) != artist:
            hits = self._rijks.search(title=title, creator=_folded(artist))
        found = []
        for hit, number in hits[:_RESULT_LIMIT]:
            record = self._rijks.object(number)
            if record is not None and (image := self._image(record, page=hit, title=title)) is not None:
                found.append(image)
        return found

    def _image(self, record: Mapping[str, Any], *, page: str, title: str | None) -> FoundImage | None:
        """The object's image, reported under `page`; None when the museum shows none of it.

        An object found through the item is reported under its record's URL as the
        item spells it, which is what the identity check compares; a search hit
        under the URL the search named.
        """
        shown = _shown(self._rijks, record)
        if shown is None:
            log.info(
                "the Rijksmuseum shows no image of an object",
                extra={"event": "rijksmuseum.no_image", "provider": PROVIDER, "record": page},
            )
            return None
        reported = _title(record, asked=title)
        if reported is None:
            raise ImageSearchFailure(f"The Rijksmuseum's record {page} gives the object no title.")
        service = shown.service
        whole = service.locator(direct_max_side=_DIRECT_MAX_SIDE).kind is LocatorKind.DIRECT
        return FoundImage(
            url=page,
            provider=PROVIDER,
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP if whole else AcquisitionMethod.DEZOOMIFY,
            title=reported,
            artist=_artist(record),
            preview_url=service.preview_url(_PREVIEW_SIZE),
            estimated_width=service.width,
            estimated_height=service.height,
            rights_status=shown.rights,
        )


class RijksmuseumReader:
    """Read a Rijksmuseum record URL into its object's image, through the museum's data, never its page."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None = None) -> None:
        self._rijks = _Rijksmuseum(user_agent=user_agent, transport=transport)

    def read(self, url: str) -> FetchLocator:
        number = number_of(url)
        if number is None:
            raise ImageSearchFailure(f"{url!r} is not a Rijksmuseum object record, so there is nothing to read.")
        record = self._rijks.object(number)
        if record is None:
            return FetchLocator.none(f"The Rijksmuseum knows no object {number}.")
        shown = _shown(self._rijks, record)
        if shown is None:
            return FetchLocator.none(f"The Rijksmuseum shows no image of object {number}.")
        return shown.service.locator(direct_max_side=_DIRECT_MAX_SIDE)


def _create(context: SourceContext) -> SourceParts:
    """The Rijksmuseum, found by Wikidata item when a registry is configured and by search always.

    It never declines: the museum's data needs no key, and it names itself with
    the deployment's own agent (`ACQUISITION_USER_AGENT`).
    """
    return SourceParts(
        finder=RijksmuseumFinder(
            user_agent=context.user_agent, registry=context.registry, preview_max_bytes=context.preview_max_bytes
        ),
        reader=RijksmuseumReader(user_agent=context.user_agent),
    )


#: What the `rijksmuseum` entry point names. Written for interface major 1 as a
#: literal, as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create, claims=claims)
