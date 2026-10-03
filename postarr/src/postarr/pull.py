"""Pull each wall's manifest and renders into its cache, report its heartbeat, and ask the server which walls this client drives.

**The only module in this plane that speaks HTTP**, and
`tests/preferences/test_plane_isolation.py` holds it to that. It spells four
routes — the client document and the client heartbeat, a wall's manifest and a
wall's heartbeat — as `contract/routes.json` spells them. Renders are fetched
from the address each manifest entry's `media.url` gives, resolved against the
manifest's own URL: today the same server's media route, after a
Library/Programming split perhaps another host. The client's token is sent to
the server's own origin only.

**The cache is the only thing a wall renders from.** A worker's watcher reads
`CACHE_DIR/<wall id>/manifest.json`, and this module writes that file only once
every render it names is in the cache and has been checked against its hash. So
a server that goes away changes nothing about what is on the wall: the last good
manifest stays, and so do its renders. The client document is kept the same way,
so a client restarted while the server is down still knows its walls.

**Every failure keeps the cache** (`player-contract.md` § Transport). A transport
error, a timeout or a `5xx` means the server is unreachable: back off and try
again. `401`, `403` and a `404` on the wall are configuration errors. A render
whose bytes do not match its hash, or that answers `404`, is left out of the
cached manifest and the rest of the wall goes on. Each is said once in the
journal when it starts and once when it ends. None names the token.

**The heartbeat rides along.** Each worker goes on writing its wall's heartbeat
file into the wall's cache (`WallSettings.heartbeat_root` says why there), and
this module POSTs it whenever it holds a report not yet sent, so a worker needs
no second way of reporting.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import aiohttp

from postarr.client import ClientDocument, ClientDocumentUnreadable, parse_client_document
from postarr.config import CACHED_MANIFEST_FILENAME, ClientSettings, WallSettings
from postarr.episodes import ReportOnce
from postarr.heartbeat import path_in as heartbeat_path_in
from postarr.manifest import ManifestUnreadable, parse

log = logging.getLogger(__name__)

#: The routes this module requests, as `contract/routes.json` spells them.
CLIENT_ROUTE: Final[str] = "/client"
CLIENT_HEARTBEAT_ROUTE: Final[str] = "/client/heartbeat"
MANIFEST_ROUTE: Final[str] = "/walls/{wall_id}/manifest"
HEARTBEAT_ROUTE: Final[str] = "/walls/{wall_id}/heartbeat"

#: Beside the cached manifest: the ETag it was served with, so a restarted Player
#: asks "has it changed since this?" rather than downloading it again.
ETAG_FILENAME: Final[str] = "manifest.etag"
#: Beside the cached client document, for the same reason.
CLIENT_ETAG_FILENAME: Final[str] = ".client.etag"
#: Renders, named by the SHA-256 of their bytes.
MEDIA_DIRNAME: Final[str] = "media"

_SHA256: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")

#: How long to wait before asking again after the server could not be reached,
#: doubling to the ceiling and reset on the next answer.
BACKOFF_START_SECONDS: Final[float] = 2.0
BACKOFF_MAX_SECONDS: Final[float] = 60.0

_UNREACHABLE: Final = (aiohttp.ClientError, asyncio.TimeoutError, OSError)


class _Poll(Enum):
    """What one manifest poll found."""

    #: The manifest route answered, and nothing needs retrying.
    ANSWERED = "answered"
    #: The manifest route answered, and a render did not arrive: back off, but the server is there.
    MEDIA_FAILING = "media_failing"
    #: No answer, or a 5xx: back off, and send nothing else.
    UNREACHABLE = "unreachable"


class Pull:
    """Keeps one wall's directory holding the newest manifest this Player can fully render."""

    def __init__(self, settings: WallSettings, *, interval_seconds: float | None = None) -> None:
        self._settings = settings
        self._server = settings.server_url
        self._token = settings.client_token
        self._cache = settings.wall_dir
        self._media = settings.wall_dir / MEDIA_DIRNAME
        self._manifest_url = self._server + MANIFEST_ROUTE.format(wall_id=settings.wall_id)
        self._heartbeat_url = self._server + HEARTBEAT_ROUTE.format(wall_id=settings.wall_id)
        self._interval = settings.poll_interval_seconds if interval_seconds is None else interval_seconds
        self._backoff = BACKOFF_START_SECONDS
        self._heartbeat_seen: tuple[int, int] | None = None
        self._heartbeat_sent: str | None = None
        # One episode per kind of trouble, so each is said once when it starts
        # and once when it clears, rather than once a second.
        self._unreachable = ReportOnce()
        self._refused_status: dict[int, ReportOnce] = {}
        self._unreadable = ReportOnce()
        self._heartbeat_failing = ReportOnce()
        self._media_failing = ReportOnce()
        self._skipped: set[str] = set()

    # -- the loop ---------------------------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> None:
        """Pull until asked to stop, backing off while the server cannot be reached."""
        self._media.mkdir(parents=True, exist_ok=True)
        log.info(
            "pulling the manifest for wall %s from %s into %s",
            self._settings.wall_id,
            self._server,
            self._cache,
            extra={
                "event": "pull.started",
                "wall_id": self._settings.wall_id,
                "server_url": self._server,
                "cache_dir": str(self._cache),
            },
        )
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while not stop.is_set():
                reachable = await self.cycle(session)
                wait = self._interval if reachable else self._next_backoff()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=wait)
                except TimeoutError:
                    pass

    async def cycle(self, session: aiohttp.ClientSession) -> bool:
        """One poll: the manifest, then the heartbeat. False when the next poll should back off.

        **Backing off and being heard are separate.** A render that keeps
        failing backs the manifest poll off, but the server's manifest route just
        answered, so the heartbeat still goes: the health panel must not report a
        live Player as silent because one render will not download.
        """
        polled = await self._pull_manifest(session)
        if polled is not _Poll.UNREACHABLE:
            await self._forward_heartbeat(session)
        if polled is _Poll.ANSWERED:
            self._backoff = BACKOFF_START_SECONDS
        return polled is _Poll.ANSWERED

    def _next_backoff(self) -> float:
        wait = self._backoff
        self._backoff = min(self._backoff * 2, BACKOFF_MAX_SECONDS)
        return wait

    # -- the manifest -----------------------------------------------------------------------

    async def _pull_manifest(self, session: aiohttp.ClientSession) -> _Poll:
        headers = self._auth()
        etag = self._cached_etag()
        if etag is not None:
            headers["If-None-Match"] = etag
        try:
            async with session.get(self._manifest_url, headers=headers) as response:
                status = response.status
                body = await response.read() if status == 200 else b""
                served_etag = response.headers.get("ETag")
        except _UNREACHABLE as exc:
            self._report_unreachable(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)
            return _Poll.UNREACHABLE
        if status >= 500:
            self._report_unreachable(f"it answered {status}")
            return _Poll.UNREACHABLE
        self._report_reachable()

        if status not in (200, 304):
            self._report_refused(status)
            return _Poll.ANSWERED
        # A 304 is the server accepting this client's token for a manifest it has
        # already sent, so it ends a refusal just as a 200 does.
        self._report_accepted()
        if status == 304:
            return _Poll.ANSWERED

        try:
            text = body.decode("utf-8")
            parse(
                text,
                rotation_interval_fallback=self._settings.rotation_interval_fallback_seconds,
                shuffle_fallback=self._settings.rotation_shuffle_fallback,
            )
            document = json.loads(text)
        except (UnicodeDecodeError, ManifestUnreadable) as exc:
            # Checked with the same parser the watcher uses, before anything is
            # cached: a refused document must never become the "last good" one a
            # restart would start from.
            if self._unreadable.begin():
                log.error(  # noqa: TRY400 -- the message is the finding
                    "refusing the manifest the server sent (%s); keeping the one already cached",
                    exc,
                    extra={"event": "pull.manifest_refused"},
                )
            return _Poll.ANSWERED
        if self._unreadable.end():
            log.info("the server's manifest can be read again", extra={"event": "pull.manifest_readable"})

        offered = document.get("entries", [])
        cached_entries = []
        for entry in offered:
            outcome = await self._cache_media(session, entry)
            if isinstance(outcome, _Retry):
                # A render did not arrive: adopt nothing, keep the manifest
                # already cached, and ask again. The ETag is not stored, so the
                # next poll is a full one. Said once per kind of failure, and
                # reported as the server being unreachable so the loop backs off
                # rather than asking every second.
                if self._media_failing.begin():
                    log.warning(
                        "a render for this wall could not be fetched (%s); keeping the manifest already cached",
                        outcome.why,
                        extra={"event": "pull.media_failing"},
                    )
                return _Poll.MEDIA_FAILING
            if outcome:
                cached_entries.append({**entry, "render_path": outcome})

        if self._media_failing.end():
            log.info("renders for this wall arrive again", extra={"event": "pull.media_ok"})
        document["entries"] = cached_entries
        # The renders the manifest being replaced names are kept one generation
        # longer: the daemon adopts the new file on its next poll, and until then
        # it may still reach for a render only the old one names.
        previous = self._cached_render_names()
        _write_atomically(self._cache / CACHED_MANIFEST_FILENAME, json.dumps(document, indent=2).encode("utf-8"))
        if served_etag:
            _write_atomically(self._cache / ETAG_FILENAME, served_etag.encode("utf-8"))
        kept = self._evict({Path(entry["render_path"]).name for entry in cached_entries} | previous)
        log.info(
            "cached the manifest for this wall with %d of %d entries; %d renders held",
            len(cached_entries),
            len(offered),
            kept,
            extra={"event": "pull.adopted", "entries": len(cached_entries)},
        )
        return _Poll.ANSWERED

    async def _cache_media(self, session: aiohttp.ClientSession, entry: dict[str, Any]) -> "str | bool | _Retry":
        """The cached render's path, relative to the cache; False to skip the work; `_Retry` to try again later."""
        work_id = entry.get("work_id")
        media = entry.get("media")
        sha = media.get("sha256") if isinstance(media, dict) else None
        url = media.get("url") if isinstance(media, dict) else None
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha) or not isinstance(url, str):
            self._skip_once(f"no-media:{work_id}", "work %s has no usable media, so this Player skips it", work_id)
            return False
        name = f"sha256-{sha}"
        relative = f"{MEDIA_DIRNAME}/{name}"
        if (self._media / name).is_file():
            return relative

        address = urljoin(self._manifest_url, url)
        # The token is this client's credential on this server. A render named on
        # another host is fetched without it, so a manifest can never be used to
        # send the token somewhere else.
        headers = self._auth() if _same_origin(address, self._server) else {}
        try:
            async with session.get(address, headers=headers) as response:
                status = response.status
                data = await response.read() if status == 200 else b""
        except _UNREACHABLE as exc:
            return _Retry(f"{type(exc).__name__} fetching it")
        if status == 404:
            self._skip_once(f"missing:{sha}", "the render for work %s is not held by the server; skipping it", work_id)
            return False
        if status != 200:
            return _Retry(f"the media route answered {status}")
        if hashlib.sha256(data).hexdigest() != sha:
            self._skip_once(
                f"mismatch:{sha}",
                "the render for work %s did not match its hash and was discarded; skipping it",
                work_id,
            )
            return False
        _write_atomically(self._media / name, data)
        return relative

    def _evict(self, referenced: set[str]) -> int:
        """Remove every cached render the newly cached manifest does not name. Returns how many remain."""
        kept = 0
        for path in self._media.iterdir():
            if path.name in referenced:
                kept += 1
                continue
            path.unlink(missing_ok=True)
        return kept

    def _cached_render_names(self) -> set[str]:
        """The render files the manifest now in the cache names, or none if there is none."""
        try:
            cached = json.loads((self._cache / CACHED_MANIFEST_FILENAME).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return set()
        return {Path(entry["render_path"]).name for entry in cached.get("entries", []) if "render_path" in entry}

    def _cached_etag(self) -> str | None:
        """The ETag to send, but only while the manifest it describes is still cached."""
        if not (self._cache / CACHED_MANIFEST_FILENAME).is_file():
            return None
        try:
            return (self._cache / ETAG_FILENAME).read_text(encoding="utf-8").strip() or None
        except FileNotFoundError:
            return None

    # -- the heartbeat ----------------------------------------------------------------------

    async def _forward_heartbeat(self, session: aiohttp.ClientSession) -> None:
        path = heartbeat_path_in(self._settings.heartbeat_root, self._settings.wall_id)
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stamp == self._heartbeat_seen:
                return
            body = path.read_bytes()
        except FileNotFoundError:
            return
        # Keyed on the report's own instant as well as the file's stamp: a file
        # rewritten with the same report, by anything, is not a new heartbeat,
        # and posting it again is how a shared directory turns into a loop.
        try:
            reported_at = json.loads(body).get("reported_at")
        except (ValueError, AttributeError):
            reported_at = None
        if reported_at is not None and reported_at == self._heartbeat_sent:
            self._heartbeat_seen = stamp
            return
        try:
            async with session.post(
                self._heartbeat_url, data=body, headers={**self._auth(), "Content-Type": "application/json"}
            ) as response:
                status = response.status
        except _UNREACHABLE:
            return
        if status == 204:
            self._heartbeat_seen = stamp
            self._heartbeat_sent = reported_at
            if self._heartbeat_failing.end():
                log.info("the server is accepting this wall's heartbeat again", extra={"event": "pull.heartbeat_ok"})
            return
        if self._heartbeat_failing.begin():
            log.warning(
                "the server refused this wall's heartbeat with %d; it will be sent again when it next changes",
                status,
                extra={"event": "pull.heartbeat_refused", "status": status},
            )

    # -- reporting --------------------------------------------------------------------------

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _report_unreachable(self, why: str) -> None:
        if self._unreachable.begin():
            log.warning(
                "the server at %s cannot be reached (%s); the wall keeps showing what is cached",
                self._server,
                why,
                extra={"event": "pull.unreachable", "server_url": self._server},
            )

    def _report_reachable(self) -> None:
        if self._unreachable.end():
            log.info("the server at %s answers again", self._server, extra={"event": "pull.reachable"})

    def _report_refused(self, status: int) -> None:
        episode = self._refused_status.setdefault(status, ReportOnce())
        if episode.begin():
            reason = {
                401: "it does not accept this client's token (CLIENT_TOKEN)",
                403: "this wall is not assigned to this client, or the server holds no such wall",
                404: "it has published nothing for this wall, or no theme hangs there yet",
            }.get(status, f"it answered {status}")
            log.error(
                "the server refused this wall's manifest: %s; keeping the one already cached",
                reason,
                extra={"event": "pull.refused", "status": status},
            )

    def _report_accepted(self) -> None:
        for status, episode in self._refused_status.items():
            if episode.end():
                log.info(
                    "the server serves this wall's manifest again after %d",
                    status,
                    extra={"event": "pull.accepted", "status": status},
                )

    def _skip_once(self, key: str, message: str, work_id: object) -> None:
        if key in self._skipped:
            return
        self._skipped.add(key)
        log.warning(message, work_id, extra={"event": "pull.work_skipped", "work_id": work_id})


class ClientPull:
    """`GET /client` and `POST /client/heartbeat`, with this client's token: the supervisor's `ClientLink`.

    **Read with the same posture as a wall's manifest.** A document is cached,
    with its ETag, only once it has been read and accepted, so the file a
    restart starts from is always one this reader could act on. Every way the
    server can fail to give a new one — unreachable, refusing the token, sending
    something unreadable — answers None, which the supervisor reads as "keep the
    walls you have", and each is said once when it starts and once when it ends.
    """

    def __init__(self, settings: ClientSettings) -> None:
        self._server = settings.server_url
        self._token = settings.client_token
        self._document_path = settings.client_document_path
        self._etag_path = settings.cache_dir / CLIENT_ETAG_FILENAME
        self._client_url = self._server + CLIENT_ROUTE
        self._heartbeat_url = self._server + CLIENT_HEARTBEAT_ROUTE
        self._session: aiohttp.ClientSession | None = None
        self._unreachable = ReportOnce()
        self._refused_status: dict[int, ReportOnce] = {}
        self._unreadable = ReportOnce()
        self._heartbeat_failing = ReportOnce()

    def cached(self) -> ClientDocument | None:
        """The last document this client accepted, or None if there is none it can read."""
        try:
            return parse_client_document(self._document_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, ClientDocumentUnreadable) as exc:
            log.warning(
                "the cached client document at %s cannot be read (%s); starting with no walls until the server answers",
                self._document_path,
                exc,
                extra={"event": "client.cache_unreadable"},
            )
            return None

    async def fetch(self) -> ClientDocument | None:
        """A new client document, or None to keep the walls already running."""
        headers = self._auth()
        etag = self._cached_etag()
        if etag is not None:
            headers["If-None-Match"] = etag
        try:
            async with self._client().get(self._client_url, headers=headers) as response:
                status = response.status
                body = await response.read() if status == 200 else b""
                served_etag = response.headers.get("ETag")
        except _UNREACHABLE as exc:
            self._report_unreachable(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)
            return None
        if status >= 500:
            self._report_unreachable(f"it answered {status}")
            return None
        if self._unreachable.end():
            log.info("the server at %s answers this client again", self._server, extra={"event": "client.reachable"})
        if status not in (200, 304):
            episode = self._refused_status.setdefault(status, ReportOnce())
            if episode.begin():
                reason = {401: "it does not accept this client's token (CLIENT_TOKEN)"}.get(status, f"it answered {status}")
                log.error(
                    "the server would not say which walls this client drives: %s; the walls already running keep going",
                    reason,
                    extra={"event": "client.refused", "status": status},
                )
            return None
        for refused, episode in self._refused_status.items():
            if episode.end():
                log.info(
                    "the server answers this client's token again after %d",
                    refused,
                    extra={"event": "client.accepted", "status": refused},
                )
        if status == 304:
            return None
        try:
            text = body.decode("utf-8")
            document = parse_client_document(text)
        except (UnicodeDecodeError, ClientDocumentUnreadable) as exc:
            if self._unreadable.begin():
                log.error(  # noqa: TRY400 -- the message is the finding
                    "refusing the client document the server sent (%s); the walls already running keep going",
                    exc,
                    extra={"event": "client.document_refused"},
                )
            return None
        if self._unreadable.end():
            log.info("the server's client document can be read again", extra={"event": "client.document_readable"})
        self._document_path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomically(self._document_path, text.encode("utf-8"))
        if served_etag:
            _write_atomically(self._etag_path, served_etag.encode("utf-8"))
        else:
            self._etag_path.unlink(missing_ok=True)
        return document

    async def report(self, heartbeat: dict[str, Any]) -> bool:
        """POST the client heartbeat. True when the server answered 204."""
        try:
            async with self._client().post(
                self._heartbeat_url,
                data=json.dumps(heartbeat).encode("utf-8"),
                headers={**self._auth(), "Content-Type": "application/json"},
            ) as response:
                status = response.status
        except _UNREACHABLE:
            # Said by `fetch`, which runs on the same poll; a second line here
            # would be the same outage told twice.
            return False
        if status == 204:
            if self._heartbeat_failing.end():
                log.info("the server is accepting this client's heartbeat again", extra={"event": "client.heartbeat_ok"})
            return True
        if self._heartbeat_failing.begin():
            log.warning(
                "the server refused this client's heartbeat with %d; it will be sent again",
                status,
                extra={"event": "client.heartbeat_refused", "status": status},
            )
        return False

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _client(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30, connect=10))
        return self._session

    def _cached_etag(self) -> str | None:
        """The ETag to send, but only while the document it describes is still cached."""
        if not self._document_path.is_file():
            return None
        try:
            return self._etag_path.read_text(encoding="utf-8").strip() or None
        except FileNotFoundError:
            return None

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _report_unreachable(self, why: str) -> None:
        if self._unreachable.begin():
            log.warning(
                "the server at %s cannot be reached (%s); this client keeps its walls as they are",
                self._server,
                why,
                extra={"event": "client.unreachable", "server_url": self._server},
            )


@dataclass(frozen=True)
class _Retry:
    """A render that did not arrive for a reason that may clear, and the reason."""

    why: str


def _same_origin(address: str, server: str) -> bool:
    first, second = urlsplit(address), urlsplit(server)
    return (first.scheme, first.netloc) == (second.scheme, second.netloc)


def _write_atomically(path: Path, data: bytes) -> None:
    """Replace a cache file in one step, so the watcher never reads half of one."""
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; the temp file must go on any exit
        temporary.unlink(missing_ok=True)
        raise
