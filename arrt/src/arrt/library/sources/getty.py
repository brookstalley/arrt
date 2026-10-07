"""The J. Paul Getty Museum, through its Linked Art records, its SPARQL endpoint and IIIF, as one image source.

It finds a work's object from the Getty page its Wikidata item records, or by
searching the museum's own data for the work's maker and title, and reports the
object's image from its IIIF manifest. It needs no key and reads no web page.
Every shape below was measured on 2026-10-07 (`linked-art-findings.md`). Six of
them decide what this module does:

**Wikidata reaches few of the Getty's works, so the finder also searches.** 2,596
items carry the Getty's object ID (P2582) and 30 of them have no image; the museum
holds 124,301 objects with images. An item naming a Getty page is read through
that page, and any other work is searched for, as `smk` does.

**The ID is the page's slug, and the museum's own data maps it.** P2582 holds the
six characters at the end of `www.getty.edu/art/collection/object/<slug>`, a page
that is a JavaScript shell. Each object's Linked Art record carries the slug as an
identifier (`urn:getty-local:idm:object:slug/<slug>`), so one query to the SPARQL
endpoint maps every slug an item names to its record (30 in 0.22 s).

**The endpoint has no text index.** A case-insensitive scan of every title took
11–14 s. Asking for the maker among the museum's 25,611 people first (0.6 s), then
for that maker's objects whose titles hold the title's words (0.3 s), does the
same work, so a work is searched for by its maker, and a work with no maker is not
searched for.

**The record carries the identity, and the manifest the image.** The record holds
the titles (preferred, primary, translated), the maker with Getty's attribution
("Workshop of", "Attributed to"), the page, and the IIIF manifest. The manifest's
first canvas is the main view; the record's `shows` lists images in no useful
order (a frame, which is another object, third on *Irises*). The manifest's text
drops every letter outside ASCII ("Fédèle Azari" is "Fdle Azari" in its bytes), so
names are read from the record, never the manifest.

**Rights are per object, in the manifest's `rights`**: CC0 on open content, and
rightsstatements.org's `InC` or `InC-RUU` on in-copyright works. They gate nothing.

**One request serves the original.** The image service declares `maxWidth` and
`maxHeight` 30,000, and `full/max` served every original asked whole, read from
the JPEG header: up to 8,409 × 12,441 in copyright. Getty keeps some in-copyright
works only at 600–768 px (its `thumbnail` clearance); those are reported at that
size, because a small image of a work asked for is worth having until a better one
is found (the owner's ruling of 2026-10-03).
"""

import json
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
)

log = logging.getLogger(__name__)

#: The name these instances are recorded under.
PROVIDER: Final[str] = "getty"

_PAGE_HOST: Final[str] = "www.getty.edu"
_PAGE_PATH: Final[re.Pattern[str]] = re.compile(r"/art/collection/object/([0-9A-Z]{6})/?")

_SPARQL_URL: Final[str] = "https://data.getty.edu/museum/collection/sparql"
_UUID: Final[str] = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_OBJECT: Final[re.Pattern[str]] = re.compile(rf"https://data\.getty\.edu/museum/collection/object/{_UUID}")
_PERSON: Final[re.Pattern[str]] = re.compile(rf"https://data\.getty\.edu/museum/collection/person/{_UUID}")
_MANIFEST: Final[re.Pattern[str]] = re.compile(rf"https://media\.getty\.edu/iiif/manifest/3/{_UUID}")
_IMAGE_PREFIX: Final[str] = "https://media.getty.edu/iiif/image/"

#: The record's slug identifier, which the endpoint is asked for.
_SLUG_URN: Final[str] = "urn:getty-local:idm:object:slug/"

_CRM: Final[str] = "PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"

#: The longest side asked for in one request: the service's own declared
#: `maxWidth` and `maxHeight`. It served every size asked whole, up to 12,441 px.
_DIRECT_MAX_SIDE: Final[int] = 30000

#: The longest side a preview is asked at.
_PREVIEW_SIZE: Final[int] = 400

#: How many objects one work reads, and how many people one name is taken to be.
#: The identity check above the seam, not these numbers, decides what survives.
_RESULT_LIMIT: Final[int] = 10
_PEOPLE_LIMIT: Final[int] = 5

#: What the record classifies its preferred title, and the parts of a maker's name, as.
_PREFERRED_TITLE: Final[str] = "http://vocab.getty.edu/aat/300404670"
_NAME: Final[str] = "https://data.getty.edu/local/thesaurus/producer-name"
_NAME_PREFIX: Final[str] = "https://data.getty.edu/local/thesaurus/producer-name-prefix"
_NAME_SUFFIX: Final[str] = "https://data.getty.edu/local/thesaurus/producer-name-suffix"

#: A suffix that names the maker's role and nationality ("maker, American"), not
#: who made the work, the way "and workshop" does.
_ROLE_SUFFIX: Final[str] = "maker"

#: What the manifest's `rights` says, read for what it says. Anything else is unknown, not guessed at.
_PUBLIC_DOMAIN: Final[tuple[str, ...]] = (
    "http://creativecommons.org/publicdomain/zero/",
    "https://creativecommons.org/publicdomain/zero/",
)
_IN_COPYRIGHT: Final[re.Pattern[str]] = re.compile(r"https?://rightsstatements\.org/vocab/InC(-[A-Z]+)*/1\.0/?")

_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
_READ_TIMEOUT_SECONDS: Final[float] = 20.0


def claims(url: str) -> bool:
    """Whether `url` is a Getty object page: the shape Wikidata's formatter builds, on the museum's host only."""
    return slug_of(url) is not None


def slug_of(url: str) -> str | None:
    """The object slug a Getty page names, or None when `url` is not one."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or port is not None or parts.username is not None or parts.password is not None:
        return None
    if parts.query or parts.fragment or parts.hostname != _PAGE_HOST:
        return None
    match = _PAGE_PATH.fullmatch(parts.path)
    return match.group(1) if match else None


def _literal(text: str) -> str:
    """`text` as a SPARQL string literal. JSON's escaping is a subset of SPARQL's, so no text leaves the literal."""
    return json.dumps(text, ensure_ascii=False)


def _words(text: str) -> list[str]:
    """The words of a title, lowercased, as the endpoint's `LCASE` reads them."""
    return re.findall(r"\w+", text.lower())


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


class _Getty:
    """The things this plugin asks the Getty, shared by the finder and the reader."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None) -> None:
        self._http = _client(transport)
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._sparql_headers = {"User-Agent": user_agent, "Accept": "application/sparql-results+json"}
        self._image_headers = {"User-Agent": user_agent, "Accept": "image/*"}

    def objects_by_slug(self, slugs: Sequence[str]) -> dict[str, str]:
        """Each slug the museum knows, with its record's URL; a slug it does not know is left out."""
        values = " ".join(_literal(_SLUG_URN + slug) for slug in slugs)
        query = (
            f"{_CRM}SELECT ?urn ?object WHERE {{ VALUES ?urn {{ {values} }} "
            "?id crm:P190_has_symbolic_content ?urn . ?object crm:P1_is_identified_by ?id . }"
        )
        known: dict[str, str] = {}
        for row in self._select(query, what="map Wikidata's Getty IDs to records"):
            urn, record = row.get("urn"), row.get("object")
            if not isinstance(urn, str) or not _is(_OBJECT, record):
                raise ImageSearchFailure("The Getty's endpoint answered the IDs with something other than its records.")
            known.setdefault(urn.removeprefix(_SLUG_URN), record)
        return known

    def people_named(self, name: str) -> list[str]:
        """The people the museum records under `name`, ignoring case."""
        query = (
            f"{_CRM}SELECT DISTINCT ?person WHERE {{ ?person a crm:E21_Person ; rdfs:label ?label . "
            f"FILTER(LCASE(STR(?label)) = LCASE({_literal(name)})) }} LIMIT {_PEOPLE_LIMIT}"
        )
        people = [row.get("person") for row in self._select(query, what=f"search for {name!r}")]
        if not all(_is(_PERSON, person) for person in people):
            raise ImageSearchFailure("The Getty's endpoint answered a name with something other than its people.")
        return [person for person in people if isinstance(person, str)]

    def objects_by(self, people: Sequence[str], words: Sequence[str]) -> list[str]:
        """The objects these people made, alone or with others, one of whose titles holds every word."""
        if not all(_is(_PERSON, person) for person in people):
            raise ImageSearchFailure("Only the Getty's own people are written into a question to it.")
        makers = " ".join(f"<{person}>" for person in people)
        holds = " && ".join(f"CONTAINS(LCASE(?title), {_literal(word)})" for word in words)
        query = (
            f"{_CRM}SELECT DISTINCT ?object WHERE {{ VALUES ?person {{ {makers} }} "
            "?object crm:P108i_was_produced_by/crm:P9_consists_of? ?production . "
            "?production crm:P14_carried_out_by ?person . "
            "?object crm:P1_is_identified_by ?name . ?name crm:P190_has_symbolic_content ?title . "
            f"FILTER({holds}) }} LIMIT {_RESULT_LIMIT}"
        )
        records = [row.get("object") for row in self._select(query, what="search a maker's objects")]
        if not all(_is(_OBJECT, record) for record in records):
            raise ImageSearchFailure("The Getty's endpoint answered a search with something other than its records.")
        return [record for record in records if isinstance(record, str)]

    def record(self, url: str) -> Mapping[str, Any]:
        """An object's Linked Art record, which the endpoint has just named."""
        if not _is(_OBJECT, url):
            raise ImageSearchFailure(f"{url!r} is not a Getty object record, so it is not read.")
        return self._json(self._get(url, headers=self._headers, what="read an object's record"), what="read an object's record")

    def manifest(self, url: str) -> Mapping[str, Any]:
        """The object's IIIF manifest, on the Getty's media host only."""
        if not _is(_MANIFEST, url):
            raise ImageSearchFailure(f"The Getty's record names a manifest off its media host ({url}).")
        return self._json(self._get(url, headers=self._headers, what="read a manifest"), what="read a manifest")

    def service(self, canvas: CanvasImage) -> ImageService:
        """The image service the canvas names, read from its `info.json`, on the Getty's image host only."""
        if canvas.service is None:
            raise ImageSearchFailure("The Getty's manifest names an image that is not a IIIF image service.")
        if not _on_image_host(canvas.service):
            raise ImageSearchFailure(f"The Getty's manifest names an image service off its image host ({canvas.service}).")
        what = "read an image service"
        info = self._json(self._get(f"{canvas.service}/info.json", headers=self._headers, what=what), what=what)
        service = ImageService.from_info(info)
        if service.id != canvas.service:
            raise ImageSearchFailure(f"The Getty's image service describes another image ({service.id}).")
        return service

    @contextmanager
    def preview(self, url: str) -> Iterator[httpx.Response]:
        """A streamed read of a rendering on the Getty's image host, and of nothing anywhere else."""
        if not _on_image_host(url):
            raise ImageSearchFailure(f"{url!r} is not on the Getty's image service, so it is not read.")
        with self._http.stream("GET", url, headers=self._image_headers) as response:
            yield response

    def _select(self, query: str, *, what: str) -> list[Mapping[str, str]]:
        """The rows a SELECT answers, each variable to its value."""
        response = self._get(_SPARQL_URL, headers=self._sparql_headers, params={"query": query}, what=what)
        results = self._json(response, what=what).get("results")
        rows = results.get("bindings") if isinstance(results, Mapping) else None
        if not isinstance(rows, list):
            raise ImageSearchFailure(f"Could not {what} at the Getty: the answer was not a SPARQL result.")
        return [
            {name: cell.get("value") for name, cell in row.items() if isinstance(cell, Mapping)}
            for row in rows
            if isinstance(row, Mapping)
        ]

    def _get(self, url: str, *, headers: Mapping[str, str], what: str, params: Mapping[str, str] | None = None) -> httpx.Response:
        try:
            return self._http.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Could not {what} at the Getty: {exc}") from exc

    def _json(self, response: httpx.Response, *, what: str) -> Mapping[str, Any]:
        if response.status_code != httpx.codes.OK:
            # A redirect lands here too: none is followed.
            raise ImageSearchFailure(f"Could not {what} at the Getty: HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise ImageSearchFailure(f"Could not {what} at the Getty: the answer was not a JSON object.")
        return payload


def _is(shape: re.Pattern[str], value: object) -> bool:
    return isinstance(value, str) and shape.fullmatch(value) is not None


def _on_image_host(url: object) -> bool:
    """Whether `url` is on the Getty's image service, the one place this plugin reads or offers an image from.

    The prefix pins the scheme, the host and the absence of a port and of
    credentials together: a URL's authority ends at its first `/`, and the prefix
    carries that `/`.
    """
    return isinstance(url, str) and url.startswith(_IMAGE_PREFIX)


def _classified(entry: Mapping[str, Any], kind: str) -> bool:
    kinds = entry.get("classified_as")
    return isinstance(kinds, list) and any(isinstance(k, Mapping) and k.get("id") == kind for k in kinds)


def _entries(record: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = record.get(key)
    return [entry for entry in value if isinstance(entry, Mapping)] if isinstance(value, list) else []


def _text(entry: Mapping[str, Any]) -> str | None:
    content = entry.get("content")
    return " ".join(content.split()) if isinstance(content, str) and content.strip() else None


def _titles(record: Mapping[str, Any]) -> list[tuple[str, bool]]:
    """Each title the record gives the object, and whether it is the preferred one."""
    return [
        (text, _classified(name, _PREFERRED_TITLE))
        for name in _entries(record, "identified_by")
        if name.get("type") == "Name" and (text := _text(name)) is not None
    ]


def _title(record: Mapping[str, Any], *, asked: str | None) -> str | None:
    """The record's title equal to the one asked for, ignoring case and spacing, where it has one; else its preferred title.

    Every title in the record is the Getty's own. The museum prefers the original
    language ("La Ville") and records a translation beside it ("The City").
    """
    titles = _titles(record)
    if asked is not None:
        wanted = " ".join(asked.split()).casefold()
        same = next((text for text, _ in titles if text.casefold() == wanted), None)
        if same is not None:
            return same
    return next((text for text, preferred in titles if preferred), titles[0][0] if titles else None)


def _artist(record: Mapping[str, Any]) -> str | None:
    """The work's maker, with the Getty's attribution around the name; None for an unknown hand.

    A work of several makers records each in a part of its production, and the
    first, in the Getty's order, is reported. "Workshop of" before the name, and
    "and workshop" after it, are kept: a workshop's work is not the master's, and
    the identity check should be told so. A suffix naming the maker's role and
    nationality ("maker, American") is not an attribution and is left out.
    """
    production = record.get("produced_by")
    if not isinstance(production, Mapping):
        return None
    parts = _entries(production, "part")
    if not _entries(production, "carried_out_by") and parts:
        production = parts[0]
    statements = _entries(production, "referred_to_by")

    def stated(kind: str) -> str | None:
        return next((text for entry in statements if _classified(entry, kind) and (text := _text(entry)) is not None), None)

    makers = _entries(production, "carried_out_by")
    label = makers[0].get("_label") if makers else None
    name = stated(_NAME) or (" ".join(label.split()) if isinstance(label, str) and label.strip() else None)
    if name is None or name.startswith("Unknown"):
        return None
    prefix, suffix = stated(_NAME_PREFIX), stated(_NAME_SUFFIX)
    if suffix is not None and suffix.startswith(_ROLE_SUFFIX):
        suffix = None
    return " ".join(part for part in (prefix, name, suffix) if part)


def _page(record: Mapping[str, Any]) -> str | None:
    """The object's page on the museum's site, as its record names it, when it is the shape this plugin reads."""
    for subject in _entries(record, "subject_of"):
        page = subject.get("id")
        if isinstance(page, str) and claims(page):
            return page
    return None


def _manifest_url(record: Mapping[str, Any]) -> str | None:
    """The record's IIIF Presentation 3 manifest, which it names beside the version 2 one."""
    for subject in _entries(record, "subject_of"):
        for url in (subject.get("id"), subject.get("has_format")):
            if isinstance(url, str) and "/iiif/manifest/3/" in url:
                return url
    return None


def _rights(manifest: Mapping[str, Any]) -> RightsStatus:
    """What the manifest's `rights` says about the object's image, which the Getty states per object."""
    stated = manifest.get("rights")
    if not isinstance(stated, str):
        return RightsStatus.UNKNOWN
    if stated.startswith(_PUBLIC_DOMAIN):
        return RightsStatus.PUBLIC_DOMAIN
    if _IN_COPYRIGHT.fullmatch(stated):
        return RightsStatus.IN_COPYRIGHT
    return RightsStatus.UNKNOWN


def _first_canvas(manifest: Mapping[str, Any]) -> CanvasImage | None:
    """The object's image: the manifest's first canvas, its main view. Later canvases are other views (a back, a frame)."""
    images = manifest_images(manifest)
    return images[0] if images else None


def _slugged(pages: Sequence[str]) -> list[tuple[str, str]]:
    """Each Getty object the pages name, once, under the first page naming it, at most `_RESULT_LIMIT` of them."""
    slugs: dict[str, str] = {}
    for page in pages:
        slug = slug_of(page)
        if slug is not None:
            slugs.setdefault(slug, page)
    return list(slugs.items())[:_RESULT_LIMIT]


class GettyFinder:
    """The image of a work at the Getty, found from the page its Wikidata item records, or by its maker and title."""

    def __init__(
        self,
        *,
        user_agent: str,
        registry: Registry | None,
        transport: httpx.BaseTransport | None = None,
        preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
    ) -> None:
        self._getty = _Getty(user_agent=user_agent, transport=transport)
        self._registry = registry
        self._preview_max_bytes = preview_max_bytes

    @property
    def provider(self) -> str:
        return PROVIDER

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        """The image of each Getty object the work's item names, or else its search finds, in copyright or not, unjudged.

        **An item whose Getty pages name no object the Getty knows is searched
        for**, as an item with no Getty page is: an ID the museum has dropped
        says nothing about whether it holds the work under another.
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
            with self._getty.preview(url) as response:
                if response.status_code != httpx.codes.OK:
                    log.warning(
                        "could not cache a Getty preview",
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
                "refused a Getty preview from elsewhere",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache a Getty preview",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)

    def _by_item(self, qid: ItemId) -> list[FoundImage] | None:
        """The images of the objects the item's Getty pages name, each under its page as the item spells it.

        None when the item names no object the Getty knows.
        """
        if self._registry is None:
            return None
        try:
            pages = self._registry.pages_about(qid)
        except RegistryUnavailable as exc:
            raise ImageSearchFailure(f"Wikidata could not be asked for {qid}'s Getty pages: {exc}") from exc
        named = _slugged(pages)
        if not named:
            return None
        records = self._getty.objects_by_slug([slug for slug, _ in named])
        for slug, _ in named:
            if slug not in records:
                log.warning(
                    "skipping a Getty page whose object the Getty's data does not name",
                    extra={"event": "getty.object_not_found", "provider": PROVIDER, "slug": slug},
                )
        if not records:
            return None
        found = []
        for slug, page in named:
            if slug in records and (image := self._image(records[slug], page=page, title=None)) is not None:
                found.append(image)
        return found

    def _by_search(self, query: ImageQuery) -> list[FoundImage]:
        """The objects of the work's maker whose titles hold the title's words, each under its page."""
        if not query.artist or not query.artist.strip():
            raise ImageQueryUnanswerable("The Getty is searched by a work's maker, and this work names none.")
        words = _words(query.title)
        if not words:
            raise ImageQueryUnanswerable(f"{query.title!r} has no words to search the Getty's titles for.")
        people = self._getty.people_named(" ".join(query.artist.split()))
        if not people:
            return []
        found = []
        for url in self._getty.objects_by(people, words):
            record = self._getty.record(url)
            page = _page(record)
            if page is None:
                # Reported under a page the reader could not read back to this object.
                log.warning(
                    "skipping a Getty search hit whose page is not the shape measured",
                    extra={"event": "getty.unexpected_page", "provider": PROVIDER, "record": url},
                )
                continue
            image = self._image(url, page=page, title=query.title, record=record)
            if image is not None:
                found.append(image)
        return found

    def _image(self, url: str, *, page: str, title: str | None, record: Mapping[str, Any] | None = None) -> FoundImage | None:
        """The object's image, reported under `page`; None when the Getty shows none of it."""
        record = record if record is not None else self._getty.record(url)
        manifest_url = _manifest_url(record)
        if manifest_url is None:
            log.info(
                "the Getty has no manifest for an object",
                extra={"event": "getty.no_manifest", "provider": PROVIDER, "record": url},
            )
            return None
        manifest = self._getty.manifest(manifest_url)
        canvas = _first_canvas(manifest)
        if canvas is None:
            return None
        if canvas.service is None or not _on_image_host(canvas.service):
            raise ImageSearchFailure(f"The Getty's manifest of {url} names an image this plugin does not read.")
        reported = _title(record, asked=title)
        if reported is None:
            raise ImageSearchFailure(f"The Getty's record {url} gives the object no title.")
        width, height = canvas.width, canvas.height
        whole = width is not None and height is not None and max(width, height) <= _DIRECT_MAX_SIDE
        return FoundImage(
            url=page,
            provider=PROVIDER,
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP if whole else AcquisitionMethod.DEZOOMIFY,
            title=reported,
            artist=_artist(record),
            preview_url=f"{canvas.service}/full/!{_PREVIEW_SIZE},{_PREVIEW_SIZE}/0/default.jpg",
            estimated_width=width,
            estimated_height=height,
            rights_status=_rights(manifest),
        )


class GettyReader:
    """Read a Getty object page into its object's image, through the museum's data, never the page."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None = None) -> None:
        self._getty = _Getty(user_agent=user_agent, transport=transport)

    def read(self, url: str) -> FetchLocator:
        slug = slug_of(url)
        if slug is None:
            raise ImageSearchFailure(f"{url!r} is not a Getty object page, so there is no record to read.")
        record_url = self._getty.objects_by_slug([slug]).get(slug)
        if record_url is None:
            return FetchLocator.none(f"The Getty's data names no object {slug}.")
        manifest_url = _manifest_url(self._getty.record(record_url))
        if manifest_url is None:
            return FetchLocator.none(f"The Getty has no image of object {slug}.")
        canvas = _first_canvas(self._getty.manifest(manifest_url))
        if canvas is None:
            return FetchLocator.none(f"The Getty's manifest of object {slug} has no image.")
        return self._getty.service(canvas).locator(direct_max_side=_DIRECT_MAX_SIDE)


def _create(context: SourceContext) -> SourceParts:
    """The Getty, found by Wikidata item when a registry is configured and by search always.

    It never declines: the museum's data needs no key, and it names itself with
    the deployment's own agent (`ACQUISITION_USER_AGENT`).
    """
    return SourceParts(
        finder=GettyFinder(user_agent=context.user_agent, registry=context.registry, preview_max_bytes=context.preview_max_bytes),
        reader=GettyReader(user_agent=context.user_agent),
    )


#: What the `getty` entry point names. Written for interface major 1 as a literal,
#: as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create, claims=claims)
