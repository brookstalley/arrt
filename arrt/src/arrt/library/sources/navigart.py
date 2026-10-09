"""navigart.fr, Videomuseum's collection platform, through its API, as one image source.

One host serves dozens of French public collections, each a *publication* with
its own *vault* on `api.navigart.fr`. This plugin finds a work's artwork from the
navigart pages the work's Wikidata item records, and reports the largest image
navigart serves, which is never more than 1,000 pixels on its long side: at
most the quality minimum, so a stand-in until a better copy is found. It needs no key. Every
shape below was measured against the live API on 2026-10-06
(`navigart-api-findings.md`). Five of them decide what this module does:

**The pages are a JavaScript front end, and the API is documented and public.**
A publication's records are public to everyone unless its managers make it
private. This plugin never fetches a page: it takes the artwork's ID from the
page and asks the API.

**Which vault to ask is the publication's, not the ID's.** Most IDs begin with
their vault's number, but `matisse_lecateau`'s begin with 7 and its vault is 701.
So the publications are a table, read from each one's own front end, and a page
of a publication not in it is not claimed: it stays a sighting.

**Only a few sizes are served**, by `images.navigart.fr/<size>/<file>`: 100, 200,
300, 400, 600, 800 and 1000. Asked for 1000, the host serves the record's
`max_width` × `max_height`, which is under 1,000 for some images and never over.

**An artwork the vault does not have is HTTP 404 with `{"error": "Not found"}`.**
A vault that does not exist is nginx's own 404 page, and a private one is 401.

**An artist is written surname first, in capitals, with any alias in brackets**
(`TAEUBER-ARP Sophie (TAEUBER Sophie-Henriette, dite)`). The identity check
compares artists by a normalised key, in which `delaunay sonia` is not `sonia
delaunay`, so the name is reported in reading order (`Sophie Taeuber-Arp`).
"""

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Final, NamedTuple
from urllib.parse import unquote, urlsplit

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
PROVIDER: Final[str] = "navigart"

#: The name a curator knows this source by, for every sentence that names it
#: (`names.museum_name`).
MUSEUM: Final[str] = "Navigart (French public collections)"

_SITE_HOST: Final[str] = "www.navigart.fr"
_API_HOST: Final[str] = "api.navigart.fr"
_IMAGE_HOST: Final[str] = "images.navigart.fr"

#: Publication slug → the vault its front end asks, each read from that
#: publication's own front end on 2026-10-06. The slugs are those of the navigart
#: pages Wikidata items record. A slug is matched exactly, case included, as the
#: site spells it. `fnac` and `grenoble-collections` now redirect elsewhere (the
#: CNAP's own site, and `grenoble`), and their vaults still answer their IDs.
PUBLICATIONS: Final[Mapping[str, int]] = {
    "bonnard": 51,
    "bourdelle": 19,
    "cantini": 53,
    "capc": 4,
    "carredart": 50,
    "ceret": 5,
    "fac-pariscollections": 20,
    "fcac": 58,
    "fnac": 14,
    "fontevraud": 63,
    "fracal": 31,
    "fracgrandlarge": 43,
    "fracsud": 45,
    "grenoble": 6,
    "grenoble-collections": 6,
    "lam": 28,
    "lapiscine": 23,
    "lesabattoirs": 27,
    "MAMC-saint-etienne-collections": 24,
    "macs": 30,
    "macval": 29,
    "mamcs": 25,
    "mamparis": 18,
    "matisse_lecateau": 701,
    "mdig": 65,
    "museedartsdenantes": 11,
    "picassoparis": 16,
    "ungerer": 26,
}

_VAULTS: Final[frozenset[int]] = frozenset(PUBLICATIONS.values())

#: An artwork ID: fourteen to seventeen digits (Grenoble's are fourteen, most are fifteen).
_ID: Final[str] = r"([1-9][0-9]{13,16})"

#: The page's path when the artwork is in it: `/<slug>/artwork/<id>`, or with the
#: artist's and title's words before the ID (`/lam/artwork/kees-van-dongen-femme-lippue-<id>`).
_PATH_ARTWORK: Final[re.Pattern[str]] = re.compile(rf"/([^/]+)/artwork/(?:[a-z0-9]+(?:-[a-z0-9]+)*-)?{_ID}", re.IGNORECASE)

#: The page's path when the artwork is in the fragment: `/<slug>/` or `/<slug>`.
_PATH_PUBLICATION: Final[re.Pattern[str]] = re.compile(r"/([^/]+)/?")

#: That fragment: `/artwork/<id>`, sometimes with a query of its own (`?note=no`).
_FRAGMENT_ARTWORK: Final[re.Pattern[str]] = re.compile(rf"/artwork/{_ID}(?:\?[^#]*)?")

#: The API's artwork URL, the reader's other shape.
_API_ARTWORK: Final[re.Pattern[str]] = re.compile(rf"/([1-9][0-9]{{0,3}})/artworks/{_ID}")

#: How navigart names an image's URL. Any other template is not the shape measured.
_URL_TEMPLATE: Final[str] = f"https://{_IMAGE_HOST}/{{size}}/{{file_name}}"

#: An image's file name: path segments of letters, digits, dots, hyphens and
#: underscores (`5E/76/5E76440.JPG`), none of them `.` or `..`.
_FILE_SEGMENT: Final[str] = r"[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*"
_FILE_NAME: Final[re.Pattern[str]] = re.compile(rf"{_FILE_SEGMENT}(?:/{_FILE_SEGMENT})*")

#: The largest size the image host serves, and the one a preview is read at.
_ORIGINAL_SIZE: Final[int] = 1000
_PREVIEW_SIZE: Final[int] = 400

#: navigart's own words for an artwork the vault does not have, with HTTP 404.
#: Any other 404 (nginx's page, for a vault that does not exist) is not that answer.
_NOT_FOUND: Final[str] = "Not found"

#: The holder's statements read as rights. Anything else is not guessed at.
_PUBLIC_DOMAIN: Final[str] = "Domaine public"
_COPYRIGHT_MARK: Final[str] = "©"

#: A surname word has at least this many letters: a capital initial (`J.`) is a given name's.
_SHORTEST_SURNAME_WORD: Final[int] = 2

#: An author navigart records as nobody in particular ("sans auteur").
_ANONYMOUS: Final[str] = "anonyme"

#: How many artworks one work reads. The identity check above the seam, not this
#: number, decides what survives.
_RESULT_LIMIT: Final[int] = 10

_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
_READ_TIMEOUT_SECONDS: Final[float] = 20.0


class Artwork(NamedTuple):
    """Where one artwork's record is asked for."""

    vault: int
    artwork_id: str


def claims(url: str) -> bool:
    """Whether `url` is a navigart artwork page of a known publication, or the API's artwork URL for one."""
    return artwork(url) is not None


def artwork(url: str) -> Artwork | None:
    """The vault and artwork ID a navigart page or API artwork URL names, or None when `url` is not one."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if port is not None or parts.username is not None or parts.password is not None:
        return None
    host = parts.hostname or ""
    if host == _SITE_HOST and parts.scheme in ("http", "https"):
        return _page_artwork(parts.path, parts.query, parts.fragment)
    if host == _API_HOST and parts.scheme == "https" and not parts.query and not parts.fragment:
        match = _API_ARTWORK.fullmatch(parts.path)
        if match and int(match.group(1)) in _VAULTS:
            return Artwork(int(match.group(1)), match.group(2))
    return None


def _page_artwork(path: str, query: str, fragment: str) -> Artwork | None:
    if query:
        return None
    if not fragment:
        match = _PATH_ARTWORK.fullmatch(unquote(path))
        if match is None:
            return None
        slug, artwork_id = match.groups()
    else:
        publication = _PATH_PUBLICATION.fullmatch(path)
        in_fragment = _FRAGMENT_ARTWORK.fullmatch(unquote(fragment))
        if publication is None or in_fragment is None:
            return None
        slug, artwork_id = publication.group(1), in_fragment.group(1)
    vault = PUBLICATIONS.get(slug)
    return Artwork(vault, artwork_id) if vault is not None else None


def api_url(where: Artwork) -> str:
    """The API's record of one artwork: what the reader asks, and a URL `claims` accepts."""
    return f"https://{_API_HOST}/{where.vault}/artworks/{where.artwork_id}"


def _on_image_host(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return parts.scheme == "https" and parts.hostname == _IMAGE_HOST and port is None and not parts.query


def reading_order(name: str) -> str:
    """navigart's `SURNAME Given (alias)` as `Given Surname`, or the name unchanged when it is not in that form.

    The surname is the run of words at the start whose letters are all capitals,
    put in title case; the alias in brackets is dropped, as the identity check
    drops it too. A name with no given part (`MATTA`, a group) is its surname alone.
    """
    bare = re.sub(r"\s*\(.*\)\s*$", "", " ".join(name.split()))
    words = bare.split(" ")
    surname: list[str] = []
    for word in words:
        letters = [ch for ch in word if ch.isalpha()]
        if len(letters) < _SHORTEST_SURNAME_WORD or not all(ch.isupper() for ch in letters):
            break
        surname.append(word)
    if not surname:
        return bare
    given = words[len(surname) :]
    titled = [re.sub(r"[^\W\d_]+", lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), word) for word in surname]
    return " ".join([*given, *titled])


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
    """The one question this plugin asks navigart's API, and its one image read, shared by the finder and the reader."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None) -> None:
        self._http = _client(transport)
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._image_headers = {"User-Agent": user_agent, "Accept": "image/*"}

    @contextmanager
    def image(self, url: str) -> Iterator[httpx.Response]:
        """A streamed read of an image on navigart's image host, and of nothing anywhere else."""
        if not _on_image_host(url):
            raise ImageSearchFailure(f"{url!r} is not on navigart's image host, so it is not read.")
        with self._http.stream("GET", url, headers=self._image_headers) as response:
            yield response

    def record(self, where: Artwork) -> Mapping[str, Any] | None:
        """The artwork's `ua` section, or None when the vault says it has no such artwork."""
        what = f"read artwork {where.artwork_id} in vault {where.vault}"
        try:
            response = self._http.get(api_url(where), headers=self._headers)
        except httpx.HTTPError as exc:
            raise ImageSearchFailure(f"Could not {what} at navigart: {exc}") from exc
        payload = _json(response)
        if response.status_code == httpx.codes.NOT_FOUND and payload.get("error") == _NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            # A redirect, nginx's 404 for a vault that does not exist, and a
            # private vault's 401 all land here: none says what the vault holds.
            raise ImageSearchFailure(f"Could not {what} at navigart: HTTP {response.status_code}.")
        results = payload.get("results")
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise ImageSearchFailure(f"navigart answered the {what} in a shape it does not document.")
        (result,) = results
        source = result.get("_source")
        ua = source.get("ua") if isinstance(source, dict) else None
        if result.get("_id") != where.artwork_id or not isinstance(ua, dict):
            # Not the record asked for: that is could-not-be-asked, never "no image".
            raise ImageSearchFailure(f"navigart answered the {what} without that artwork's record.")
        return ua


def _json(response: httpx.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


class _NotTheShape(Exception):
    """An answer that is not the shape measured."""


class _Image(NamedTuple):
    file_name: str
    width: int | None
    height: int | None


def _image(ua: Mapping[str, Any]) -> _Image | None:
    """The artwork's first image, or None when navigart records none.

    Raises `_NotTheShape` for an image that is not the shape measured, which each
    caller reports in its own terms.
    """
    medias = ua.get("medias")
    if medias is None:
        return None
    if not isinstance(medias, list):
        raise _NotTheShape("medias is not a list")
    for media in medias:
        if not isinstance(media, dict) or media.get("type") != "image":
            continue
        file_name = media.get("file_name")
        if media.get("url_template") != _URL_TEMPLATE or not isinstance(file_name, str) or not _FILE_NAME.fullmatch(file_name):
            raise _NotTheShape("the image is not named on navigart's image host")
        width, height = _served(_dimension(media.get("max_width")), _dimension(media.get("max_height")))
        return _Image(file_name, width, height)
    return None


def _served(width: int | None, height: int | None) -> tuple[int | None, int | None]:
    """The size the host serves at `_ORIGINAL_SIZE`: the stated size, its long side held to that.

    Every record measured states 1,000 or less, which the host serves as stated.
    One that stated more would still be read at 1,000, so its size is what that
    read returns, not the record's, or a placeholder would pass for a full image.
    """
    if width is None or height is None or max(width, height) <= _ORIGINAL_SIZE:
        return width, height
    scale = _ORIGINAL_SIZE / max(width, height)
    return round(width * scale), round(height * scale)


def _dimension(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return round(value)


def _image_url(file_name: str, size: int) -> str:
    return _URL_TEMPLATE.format(size=size, file_name=file_name)


def _rights(artwork_record: Mapping[str, Any]) -> RightsStatus:
    """The holder's own statement, read for what it says; a value never seen is not guessed at."""
    statement = artwork_record.get("copyright")
    if not isinstance(statement, str):
        return RightsStatus.UNKNOWN
    statement = statement.strip()
    if statement == _PUBLIC_DOMAIN:
        return RightsStatus.PUBLIC_DOMAIN
    if statement.startswith(_COPYRIGHT_MARK):
        return RightsStatus.IN_COPYRIGHT
    return RightsStatus.UNKNOWN


def _artist(ua: Mapping[str, Any]) -> str | None:
    """The first author navigart does not record as anonymous, in reading order."""
    authors = ua.get("authors")
    if not isinstance(authors, list):
        return None
    for author in authors:
        if not isinstance(author, dict) or author.get("type") == _ANONYMOUS:
            continue
        name = author.get("name")
        notice = name.get("notice") if isinstance(name, dict) else None
        if isinstance(notice, str) and notice.strip():
            return reading_order(notice)
    return None


def _title(artwork_record: Mapping[str, Any]) -> str | None:
    title = artwork_record.get("title_notice")
    if not isinstance(title, str):
        return None
    # Some titles carry a line break between their parts (`Composition n°27\nJaune assez animé`).
    return " ".join(title.split()) or None


def _pages(registry: Registry, qid: ItemId) -> list[tuple[Artwork, str]]:
    """Each artwork the item's navigart pages name, once, under the first page that names it."""
    try:
        pages = registry.pages_about(qid)
    except RegistryUnavailable as exc:
        raise ImageSearchFailure(f"Wikidata could not be asked for {qid}'s navigart pages: {exc}") from exc
    named: dict[Artwork, str] = {}
    for page in pages:
        where = artwork(page)
        if where is not None:
            named.setdefault(where, page)
    return list(named.items())


class NavigartFinder:
    """navigart's largest image of a work, found from the navigart pages the work's Wikidata item records."""

    def __init__(
        self,
        *,
        user_agent: str,
        registry: Registry | None,
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
        """The image of each artwork the work's item links on navigart, each under the page as the item spells it.

        navigart has no search across its publications, so a work is reached
        only through its item.
        """
        if query.qid is None or self._registry is None:
            raise ImageQueryUnanswerable("navigart is reached through a work's Wikidata item, and this work has none.")
        pages = _pages(self._registry, query.qid)
        found: list[FoundImage] = []
        read = pages[:_RESULT_LIMIT]
        for where, page in read:
            ua = self._api.record(where)
            if ua is None:
                log.warning(
                    "skipping a navigart page whose artwork its vault says it does not have",
                    extra={"event": "navigart.artwork_not_found", "provider": PROVIDER, **_where(where)},
                )
                continue
            image = self._found(where, ua, url=page)
            if image is not None:
                found.append(image)
        log.info(
            "searched a museum collection for a work",
            extra={
                "event": "phase_two.searched",
                "provider": PROVIDER,
                "work_title": query.title,
                "by": "wikidata",
                "objects_matched": len(pages),
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
                        "could not cache a navigart preview",
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
                "refused a navigart preview off its image host",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        except httpx.HTTPError as exc:
            log.warning(
                "could not cache a navigart preview",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)

    def _found(self, where: Artwork, ua: Mapping[str, Any], *, url: str) -> FoundImage | None:
        """The artwork's image, reported under `url`; None when navigart offers none."""
        record = ua.get("artwork")
        record = record if isinstance(record, dict) else {}
        try:
            image = _image(ua)
        except _NotTheShape:
            return _unexpected(where)
        if image is None:
            return None
        title = _title(record)
        if title is None:
            return _unexpected(where)
        return FoundImage(
            url=url,
            provider=PROVIDER,
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            title=title,
            artist=_artist(ua),
            preview_url=_image_url(image.file_name, _PREVIEW_SIZE),
            estimated_width=image.width,
            estimated_height=image.height,
            rights_status=_rights(record),
        )


def _where(where: Artwork) -> dict[str, object]:
    return {"vault": where.vault, "artwork_id": where.artwork_id}


def _unexpected(where: Artwork) -> None:
    log.warning(
        "skipping a navigart artwork whose answer is not the shape measured",
        extra={"event": "navigart.unexpected_artwork", "provider": PROVIDER, **_where(where)},
    )


class NavigartReader:
    """Read a navigart page or API artwork URL into the artwork's largest image, fetched over plain HTTP."""

    def __init__(self, *, user_agent: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api = _Api(user_agent=user_agent, transport=transport)

    def read(self, url: str) -> FetchLocator:
        where = artwork(url)
        if where is None:
            raise ImageSearchFailure(f"{url!r} is not a navigart artwork page, so there is no record to read.")
        ua = self._api.record(where)
        if ua is None:
            return FetchLocator.none(f"navigart's vault {where.vault} has no artwork {where.artwork_id}.")
        try:
            image = _image(ua)
        except _NotTheShape as exc:
            raise ImageSearchFailure(f"navigart named an image for artwork {where.artwork_id} it does not serve: {exc}.") from exc
        if image is None:
            return FetchLocator.none(f"navigart offers no image of artwork {where.artwork_id}.")
        return FetchLocator.direct(_image_url(image.file_name, _ORIGINAL_SIZE))


def _create(context: SourceContext) -> SourceParts:
    """navigart, found by Wikidata item when a registry is configured, and read always.

    It never declines: the API needs no key, and it names itself with the
    deployment's own agent (`ACQUISITION_USER_AGENT`). With no registry it has
    no way to find a work, so it offers its reader alone and is not listed as
    an image source; the rows it found before still read.
    """
    reader = NavigartReader(user_agent=context.user_agent)
    if context.registry is None:
        return SourceParts(reader=reader)
    finder = NavigartFinder(user_agent=context.user_agent, registry=context.registry, preview_max_bytes=context.preview_max_bytes)
    return SourceParts(finder=finder, reader=reader)


#: What the `navigart` entry point names. Written for interface major 1 as a
#: literal, as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create, claims=claims)
