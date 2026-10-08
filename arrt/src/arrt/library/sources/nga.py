"""The National Gallery of Art (Washington), through its open data, as one image source.

It finds a work's object at the NGA from the NGA artwork ID its Wikidata item
records (P4683), and reports NGA's image of it: the original through the IIIF
tiles, or, where NGA serves only a capped copy, that copy as a placeholder. It
needs no key. Every shape below was measured on 2026-10-06 (`nga-api-findings.md`),
and the copy's lifetime is the owner's ruling of the same day. Five things decide
what this module does:

**No NGA interface turns an object ID into its image** except its open data's
`published_images.csv` (89 MB; 26.6 MB gzipped on the wire) and the artwork's
web page. So this plugin keeps a copy of the open data and never fetches a page.
The image file has no title and no artist, which the identity check needs in
NGA's own words, so `objects.csv` (16.5 MB on the wire) is kept beside it.

**The copy costs nothing while nobody asks** (the owner's ruling): the files sit
on disk gzipped, in the plugin's own directory, refreshed at most once a day with
a conditional request; they are parsed into memory only when a query asks NGA,
and released after six hours with no NGA query. About 80 MB while warm.

**`maxpixels` decides what is served, not `openaccess`.** An image with none is
served in full through its IIIF service's tiles; a direct `full/full` is capped
at 4,096 px, so it is not the original. One with `maxpixels` (900, or 4000 for a
few) redirects every request to `<uuid>__<maxpixels>`, a copy at most that size
on its long side, which upscales whatever larger size is asked of it, so only
its stated size is trusted.

**`openaccess=0` does not mean "in copyright"**: Escher's *Castrovalva*, public
domain in the US since 2026, is capped. So it is recorded as unknown.

**NGA's artwork pages are the old site's**, as P4683's formatter builds them
(`/collection/art-object-page.<id>.html`); the new site redirects them. An image
is reported under the page exactly as the item spells it, because that link is
what identifies it.
"""

import csv
import gzip
import json
import logging
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Final, NamedTuple
from urllib.parse import urlsplit

import httpx

from arrt.library.sources import (
    DEFAULT_PREVIEW_MAX_BYTES,
    AcquisitionMethod,
    Declined,
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
PROVIDER: Final[str] = "nga"

#: The name a curator knows this source by, for every sentence that names it
#: (`names.museum_name`).
MUSEUM: Final[str] = "National Gallery of Art, Washington"

_SITE_HOST: Final[str] = "www.nga.gov"
_IIIF_HOST: Final[str] = "api.nga.gov"
_IIIF_PREFIX: Final[str] = f"https://{_IIIF_HOST}/iiif/"

#: Where the open data is published (its README's own link, on GitHub's raw host).
DATA_URL: Final[str] = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/"

#: How often a file is asked for again, at most: once a day (the owner's ruling).
#: NGA publishes the files once a day, at about 10:00 UTC.
REFRESH_SECONDS: Final[float] = 24 * 60 * 60

#: How long the parsed copy is kept with no NGA query before it is released (the owner's ruling).
IDLE_SECONDS: Final[float] = 6 * 60 * 60

#: The most of one file read off the wire: about five times the larger file
#: gzipped (26.6 MB), and about one and a half times it served plain (89 MB).
_MAX_DOWNLOAD_BYTES: Final[int] = 128 * 1024 * 1024

#: Where a file's validators and last check are kept, beside the files.
_STATE_FILENAME: Final[str] = "state.json"

#: What reading the state file raises when it is missing or not JSON. A named
#: tuple rather than `except OSError, ValueError:` because the root suite's seam
#: guards parse this plane's source on Python 3.12, which cannot read the
#: unparenthesised form this plane's formatter writes (backlog #166).
_UNREADABLE_STATE: Final[tuple[type[Exception], ...]] = (OSError, ValueError)


class _OpenDataFile(NamedTuple):
    name: str
    #: The columns read. A download whose header lacks any is not the file expected.
    columns: frozenset[str]


_IMAGES: Final[_OpenDataFile] = _OpenDataFile(
    "published_images.csv",
    frozenset({"uuid", "viewtype", "width", "height", "maxpixels", "openaccess", "depictstmsobjectid"}),
)
_OBJECTS: Final[_OpenDataFile] = _OpenDataFile("objects.csv", frozenset({"objectid", "title", "attribution"}))
_FILES: Final[tuple[_OpenDataFile, ...]] = (_IMAGES, _OBJECTS)

#: An NGA object ID, as P4683's own pattern allows and a little more.
_ID: Final[str] = r"([1-9][0-9]{0,6})"

#: NGA's artwork pages: P4683's two formatters, and the new site's own address.
_PAGE_PATHS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(rf"/collection/art-object-page\.{_ID}\.html"),
    re.compile(rf"/content/ngaweb/Collection/art-object-page\.{_ID}\.html"),
    re.compile(rf"/artworks/{_ID}-[a-z0-9]+(?:-[a-z0-9]+)*"),
)

#: An image's id on NGA's IIIF service.
_UUID: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

#: The longest side a preview is asked at.
_PREVIEW_SIZE: Final[int] = 400

#: How many artworks one work reads. The identity check, not this number, decides what survives.
_RESULT_LIMIT: Final[int] = 10

_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
_READ_TIMEOUT_SECONDS: Final[float] = 60.0


def claims(url: str) -> bool:
    """Whether `url` is one of NGA's artwork pages, in a shape Wikidata records."""
    return object_id(url) is not None


def object_id(url: str) -> int | None:
    """The object ID an NGA artwork page names, or None when `url` is not one."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme not in ("http", "https")
        or parts.hostname != _SITE_HOST
        or port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        return None
    for path in _PAGE_PATHS:
        match = path.fullmatch(parts.path)
        if match:
            return int(match.group(1))
    return None


class Entry(NamedTuple):
    """One object's primary image, as NGA's open data describes it."""

    uuid: str
    width: int
    height: int
    #: The longest side NGA serves, or None when it serves the original.
    maxpixels: int | None
    open_access: bool
    title: str | None
    attribution: str | None

    @property
    def service(self) -> str:
        """The IIIF service that serves this image: the original's, or the capped copy's."""
        base = f"{_IIIF_PREFIX}{self.uuid}"
        return base if self.maxpixels is None else f"{base}__{self.maxpixels}"

    @property
    def served_size(self) -> tuple[int, int]:
        """What that service serves: the original, or the original scaled to `maxpixels` on its long side.

        The capped service's stated size was measured equal to this (887 × 900
        for a 3605 × 3659 original, 895 × 900 for 9139 × 9189).
        """
        longest = max(self.width, self.height)
        if self.maxpixels is None or longest <= self.maxpixels:
            return self.width, self.height
        scale = self.maxpixels / longest
        return round(self.width * scale), round(self.height * scale)


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
        # No redirect is followed: the data host and the IIIF host answer in
        # place, and a redirect would take a read somewhere never checked.
        follow_redirects=False,
    )


def _daemon_timer(delay: float, call: Callable[[], None]) -> None:
    timer = threading.Timer(delay, call)
    timer.daemon = True
    timer.start()


class _RefreshFailed(Exception):
    """A download that did not give the file expected."""


class NgaCatalogue:
    """NGA's open data, kept on disk and in memory only while it is being asked.

    One per plugin, shared by its finder and reader, and safe to ask from several
    threads: one lock covers the files, the index and the timer.
    """

    def __init__(
        self,
        *,
        directory: Path,
        user_agent: str,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.time,
        schedule: Callable[[float, Callable[[], None]], None] = _daemon_timer,
    ) -> None:
        self._directory = directory
        self._http = _client(transport)
        self._user_agent = user_agent
        self._clock = clock
        self._schedule = schedule
        self._lock = threading.Lock()
        self._index: dict[int, Entry] | None = None
        self._state: dict[str, dict[str, Any]] | None = None
        self._last_asked = 0.0
        self._armed = False
        self._swept = False

    @property
    def loaded(self) -> bool:
        """Whether the copy is parsed into memory now."""
        return self._index is not None

    def entry(self, object_id: int) -> Entry | None:
        """The object's primary image, or None when NGA's open data has none.

        Refreshes a file whose day is up first, and parses the copy if it is not
        in memory or a file changed. Raises `ImageSearchFailure` when there is no
        copy on disk and none could be got.
        """
        with self._lock:
            now = self._clock()
            self._last_asked = now
            self._sweep()
            changed = False
            for data_file in _FILES:
                changed = self._refresh(data_file, now) or changed
            if self._index is None or changed:
                self._index = self._parse()
            self._arm(IDLE_SECONDS)
            return self._index.get(object_id)

    def _sweep(self) -> None:
        """Remove what a download killed before its `finally` left behind, once per process.

        A temporary file is only ever this process's own in flight, and nothing
        is in flight before the first query, so every one found then is debris.
        """
        if self._swept:
            return
        self._swept = True
        for debris in self._directory.glob(".*.part") if self._directory.is_dir() else ():
            debris.unlink(missing_ok=True)
            log.info(
                "removed a download the last process did not finish",
                extra={"event": "nga.catalogue_debris_removed", "provider": PROVIDER, "file": debris.name},
            )

    def release_if_idle(self) -> None:
        """Release the parsed copy if no query has asked NGA for `IDLE_SECONDS`, else wait out the rest."""
        with self._lock:
            self._armed = False
            if self._index is None:
                return
            idle = self._clock() - self._last_asked
            if idle >= IDLE_SECONDS:
                self._index = None
                log.info(
                    "released NGA's catalogue copy after six hours unasked",
                    extra={"event": "nga.catalogue_released", "provider": PROVIDER},
                )
                return
            self._arm(IDLE_SECONDS - idle)

    def _arm(self, delay: float) -> None:
        if not self._armed:
            self._armed = True
            self._schedule(delay, self.release_if_idle)

    # -- the files on disk ----------------------------------------------------------------

    def _path(self, data_file: _OpenDataFile) -> Path:
        return self._directory / f"{data_file.name}.gz"

    def _states(self) -> dict[str, dict[str, Any]]:
        if self._state is None:
            try:
                loaded = json.loads((self._directory / _STATE_FILENAME).read_text(encoding="utf-8"))
            except _UNREADABLE_STATE:
                loaded = {}
            self._state = loaded if isinstance(loaded, dict) else {}
        return self._state

    def _record(self, data_file: _OpenDataFile, **fields: object) -> None:
        states = self._states()
        state = states.get(data_file.name)
        states[data_file.name] = {**(state if isinstance(state, dict) else {}), **fields}
        try:
            _write_atomically(self._directory / _STATE_FILENAME, json.dumps(states, indent=1).encode("utf-8"))
        except OSError as exc:
            # The files still stand; the next process re-asks sooner than it need, and no more.
            log.warning(
                "could not record when NGA's open data was last asked",
                extra={"event": "nga.state_unwritten", "provider": PROVIDER, "error": str(exc)},
            )

    def _refresh(self, data_file: _OpenDataFile, now: float) -> bool:
        """Ask for the file again if its day is up; whether it changed.

        A failure keeps the file there is, and is not retried until its next day.
        With no file to keep, it is could-not-be-asked, and the next query tries again.
        """
        path = self._path(data_file)
        state = self._states().get(data_file.name)
        state = state if isinstance(state, dict) else {}
        checked_at = state.get("checked_at")
        have = path.is_file()
        if have and isinstance(checked_at, (int, float)) and now - checked_at < REFRESH_SECONDS:
            return False
        headers = {"User-Agent": self._user_agent, "Accept-Encoding": "gzip"}
        if have:
            if isinstance(state.get("etag"), str):
                headers["If-None-Match"] = state["etag"]
            if isinstance(state.get("last_modified"), str):
                headers["If-Modified-Since"] = state["last_modified"]
        # Said before the request: the first download of a day holds every NGA
        # query, and so the run asking, for the seconds it takes.
        log.info(
            "asking for NGA's open data",
            extra={"event": "nga.catalogue_requested", "provider": PROVIDER, "file": data_file.name, "conditional": have},
        )
        try:
            with self._http.stream("GET", f"{DATA_URL}{data_file.name}", headers=headers) as response:
                if response.status_code == httpx.codes.NOT_MODIFIED and have:
                    self._record(data_file, checked_at=now)
                    log.info(
                        "NGA's open data is unchanged",
                        extra={"event": "nga.catalogue_unchanged", "provider": PROVIDER, "file": data_file.name},
                    )
                    return False
                received = self._download(data_file, response)
                etag, last_modified = response.headers.get("ETag"), response.headers.get("Last-Modified")
        except (httpx.HTTPError, OSError, _RefreshFailed) as exc:
            if not have:
                raise ImageSearchFailure(f"NGA's open data could not be got ({data_file.name}): {exc}") from exc
            self._record(data_file, checked_at=now)
            log.warning(
                "could not refresh NGA's open data; yesterday's copy stands",
                extra={"event": "nga.catalogue_refresh_failed", "provider": PROVIDER, "file": data_file.name, "error": str(exc)},
            )
            return False
        self._record(data_file, checked_at=now, etag=etag, last_modified=last_modified)
        log.info(
            "downloaded NGA's open data",
            extra={"event": "nga.catalogue_downloaded", "provider": PROVIDER, "file": data_file.name, "bytes": received},
        )
        return True

    def _download(self, data_file: _OpenDataFile, response: httpx.Response) -> int:
        """Write the body, gzipped, beside the file, check it is the file expected, and put it in place."""
        if response.status_code != httpx.codes.OK:
            raise _RefreshFailed(f"HTTP {response.status_code}")
        self._directory.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=self._directory, prefix=f".{data_file.name}.", suffix=".part")
        received = 0
        try:
            with os.fdopen(handle, "wb") as raw:
                gzipped = response.headers.get("Content-Encoding", "").strip().lower() == "gzip"
                # A gzipped body is written as it came; a plain one is compressed here.
                with _writer(raw, compress=not gzipped) as write:
                    for chunk in response.iter_raw() if gzipped else response.iter_bytes():
                        received += len(chunk)
                        if received > _MAX_DOWNLOAD_BYTES:
                            raise _RefreshFailed(f"larger than {_MAX_DOWNLOAD_BYTES} bytes")
                        write(chunk)
            _check(Path(temporary), data_file)
            Path(temporary).replace(self._path(data_file))
        finally:
            Path(temporary).unlink(missing_ok=True)
        return received

    def _parse(self) -> dict[int, Entry]:
        """Every object's primary image, with its title and attribution, from the files on disk."""
        started = time.monotonic()
        index: dict[int, Entry] = {}
        try:
            for row in _rows(self._path(_IMAGES)):
                parsed = _image_row(row)
                if parsed is not None:
                    index.setdefault(*parsed)
            for row in _rows(self._path(_OBJECTS)):
                number = _number(row.get("objectid"))
                entry = index.get(number) if number is not None else None
                if entry is not None:
                    index[number] = entry._replace(title=_text(row.get("title")), attribution=_text(row.get("attribution")))
        except (OSError, EOFError, csv.Error, UnicodeDecodeError) as exc:
            raise ImageSearchFailure(f"NGA's open data on disk could not be read: {exc}") from exc
        log.info(
            "read NGA's catalogue copy into memory",
            extra={
                "event": "nga.catalogue_loaded",
                "provider": PROVIDER,
                "objects": len(index),
                "seconds": round(time.monotonic() - started, 2),
            },
        )
        return index


@contextmanager
def _writer(raw: BinaryIO, *, compress: bool) -> Iterator[Callable[[bytes], object]]:
    if not compress:
        yield raw.write
        return
    with gzip.GzipFile(fileobj=raw, mode="wb") as zipped:
        yield zipped.write


def _check(path: Path, data_file: _OpenDataFile) -> None:
    """Whether the gzipped file is the CSV expected: its header names the columns read, and it reads to the end."""
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as text:
            reader = csv.reader(text)
            header = next(reader, None)
            if header is None or not data_file.columns <= set(header):
                raise _RefreshFailed(f"{data_file.name} did not arrive with the columns it is read for")
            # Every row is read, so a body whose gzip breaks past its first rows
            # never replaces a file that reads whole (about a second, once a day).
            if sum(1 for _ in reader) == 0:
                raise _RefreshFailed(f"{data_file.name} arrived with no rows")
    except (OSError, EOFError, csv.Error, UnicodeDecodeError) as exc:
        raise _RefreshFailed(f"{data_file.name} arrived unreadable: {exc}") from exc


def _rows(path: Path) -> Iterator[Mapping[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as text:
        yield from csv.DictReader(text)


def _image_row(row: Mapping[str, str | None]) -> tuple[int, Entry] | None:
    """A primary image's object ID and entry, its title and attribution still to come; None for any other row.

    A row cut short has None where its missing fields are (`csv.DictReader`), so
    every field is read as possibly absent, and such a row is skipped like any
    other that is not a primary image's.
    """
    uuid = row.get("uuid") or ""
    if row.get("viewtype") != "primary" or not _UUID.fullmatch(uuid):
        return None
    object_id, width, height = _number(row.get("depictstmsobjectid")), _number(row.get("width")), _number(row.get("height"))
    maxpixels = _number(row.get("maxpixels")) if row.get("maxpixels") else None
    if object_id is None or width is None or height is None or (row.get("maxpixels") and maxpixels is None):
        return None
    return object_id, Entry(uuid, width, height, maxpixels, row.get("openaccess") == "1", title=None, attribution=None)


def _number(value: str | None) -> int | None:
    """A positive whole number, or None for anything else (absent, blank, not a number, zero)."""
    try:
        number = int(value or "")
    except ValueError:
        return None
    return number if number > 0 else None


def _text(value: str | None) -> str | None:
    # NGA's text carries stray line ends (`… Holbein the Younger\r\n`).
    if not value:
        return None
    return " ".join(value.split()) or None


def _write_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".part")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(content)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _on_iiif_host(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname == _IIIF_HOST
        and port is None
        and parts.path.startswith("/iiif/")
        and not parts.query
    )


def _pages(registry: Registry, qid: ItemId) -> list[tuple[int, str]]:
    """Each object the item's NGA pages name, once, under the first page that names it."""
    try:
        pages = registry.pages_about(qid)
    except RegistryUnavailable as exc:
        raise ImageSearchFailure(f"Wikidata could not be asked for {qid}'s NGA pages: {exc}") from exc
    named: dict[int, str] = {}
    for page in pages:
        found = object_id(page)
        if found is not None:
            named.setdefault(found, page)
    return list(named.items())


class NgaFinder:
    """NGA's image of a work, found from the NGA artwork ID its Wikidata item records."""

    def __init__(
        self,
        *,
        catalogue: NgaCatalogue,
        registry: Registry | None,
        user_agent: str,
        transport: httpx.BaseTransport | None = None,
        preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
    ) -> None:
        self._catalogue = catalogue
        self._registry = registry
        self._http = _client(transport)
        self._headers = {"User-Agent": user_agent, "Accept": "image/*"}
        self._preview_max_bytes = preview_max_bytes

    @property
    def provider(self) -> str:
        return PROVIDER

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        """The image of each object the work's item names at the NGA, each under the page as the item spells it."""
        if query.qid is None or self._registry is None:
            raise ImageQueryUnanswerable("The NGA is reached through a work's Wikidata item, and this work has none.")
        pages = _pages(self._registry, query.qid)
        read = pages[:_RESULT_LIMIT]
        found: list[FoundImage] = []
        for number, page in read:
            entry = self._catalogue.entry(number)
            if entry is None or entry.title is None:
                log.info(
                    "NGA's open data has no image, or no title, for an object the item names",
                    extra={"event": "nga.no_image", "provider": PROVIDER, "object_id": number},
                )
                continue
            found.append(_found(entry, url=page))
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
        if not _on_iiif_host(url):
            log.warning(
                "refused an NGA preview off its IIIF host",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER},
            )
            return None
        try:
            with self._http.stream("GET", url, headers=self._headers) as response:
                if response.status_code != httpx.codes.OK:
                    log.warning(
                        "could not cache an NGA preview",
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
                "could not cache an NGA preview",
                extra={"event": "phase_two.preview_failed", "provider": PROVIDER, "error": str(exc)},
            )
            return None
        return b"".join(chunks)


def _found(entry: Entry, *, url: str) -> FoundImage:
    width, height = entry.served_size
    return FoundImage(
        url=url,
        provider=PROVIDER,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY if entry.maxpixels is None else AcquisitionMethod.DIRECT_HTTP,
        title=entry.title or "",
        artist=entry.attribution,
        preview_url=f"{entry.service}/full/!{_PREVIEW_SIZE},{_PREVIEW_SIZE}/0/default.jpg",
        estimated_width=width,
        estimated_height=height,
        rights_status=RightsStatus.PUBLIC_DOMAIN if entry.open_access else RightsStatus.UNKNOWN,
    )


class NgaReader:
    """Read an NGA artwork page into its image: the original's tiles, or the capped copy."""

    def __init__(self, *, catalogue: NgaCatalogue) -> None:
        self._catalogue = catalogue

    def read(self, url: str) -> FetchLocator:
        number = object_id(url)
        if number is None:
            raise ImageSearchFailure(f"{url!r} is not an NGA artwork page, so there is no object to read.")
        entry = self._catalogue.entry(number)
        if entry is None:
            return FetchLocator.none(f"NGA's open data has no image of object {number}.")
        if entry.maxpixels is None:
            return FetchLocator.tiles(f"{entry.service}/info.json")
        return FetchLocator.direct(f"{entry.service}/full/full/0/default.jpg")


def _create(context: SourceContext) -> SourceParts | Declined:
    """The NGA, found by Wikidata item when a registry is configured, and read always.

    It needs a directory of its own for the copy of NGA's open data (interface
    1.2), and declines without one. It needs no setting otherwise, and names
    itself with the deployment's own agent (`ACQUISITION_USER_AGENT`).
    """
    directory = getattr(context, "data_dir", None)
    if directory is None:
        return Declined(
            "this Arrt gives plugins no directory of their own (source interface 1.2), "
            "and the NGA is read from a copy of its open data kept there"
        )
    catalogue = NgaCatalogue(directory=directory, user_agent=context.user_agent)
    reader = NgaReader(catalogue=catalogue)
    if context.registry is None:
        return SourceParts(reader=reader)
    finder = NgaFinder(
        catalogue=catalogue,
        registry=context.registry,
        user_agent=context.user_agent,
        preview_max_bytes=context.preview_max_bytes,
    )
    return SourceParts(finder=finder, reader=reader)


#: What the `nga` entry point names. Written for interface major 1 as a literal,
#: as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create, claims=claims)
