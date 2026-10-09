"""Pull each wall's manifest and renders into its cache, report its heartbeat, and ask the server which walls this client drives.

**The only module in this plane that speaks HTTP**, and
`tests/preferences/test_plane_isolation.py` holds it to that. It spells five
routes — the client document and the client heartbeat, a wall's manifest and a
wall's heartbeat, and a label's document — as `contract/routes.json` spells them. Renders are fetched
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
import contextlib
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import aiohttp

from arrt_player.client import ClientDocument, ClientDocumentUnreadable, parse_client_document
from arrt_player.config import CACHED_MANIFEST_FILENAME, ClientSettings, WallSettings
from arrt_player.episodes import ReportOnce
from arrt_player.heartbeat import path_in as heartbeat_path_in
from arrt_player.label_rule import LabelDocument, LabelDocumentUnreadable, parse_label_document
from arrt_player.manifest import MEDIA_DIRNAME, Feed, ManifestUnreadable, parse

log = logging.getLogger(__name__)

#: The routes this module requests, as `contract/routes.json` spells them.
CLIENT_ROUTE: Final[str] = "/client"
CLIENT_HEARTBEAT_ROUTE: Final[str] = "/client/heartbeat"
MANIFEST_ROUTE: Final[str] = "/walls/{wall_id}/manifest"
HEARTBEAT_ROUTE: Final[str] = "/walls/{wall_id}/heartbeat"
LABEL_ROUTE: Final[str] = "/labels/{label_id}"

#: Beside the cached manifest: the ETag it was served with, so a restarted Player
#: asks "has it changed since this?" rather than downloading it again.
ETAG_FILENAME: Final[str] = "manifest.etag"
#: Beside the cached client document, for the same reason.
CLIENT_ETAG_FILENAME: Final[str] = ".client.etag"

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
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=wait)

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

    async def _pull_manifest(  # noqa: C901, PLR0911, PLR0912 -- one branch per answer the server can give, each keeping the cache
        self, session: aiohttp.ClientSession
    ) -> _Poll:
        headers = self._auth()
        etag = self._cached_etag()
        if etag is not None:
            headers["If-None-Match"] = etag
        try:
            async with session.get(self._manifest_url, headers=headers) as response:
                status = response.status
                body = await response.read() if status == HTTPStatus.OK else b""
                served_etag = response.headers.get("ETag")
        except _UNREACHABLE as exc:
            self._report_unreachable(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)
            return _Poll.UNREACHABLE
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            self._report_unreachable(f"it answered {status}")
            return _Poll.UNREACHABLE
        self._report_reachable()

        if status not in (200, 304):
            self._report_refused(status)
            return _Poll.ANSWERED
        # A 304 is the server accepting this client's token for a manifest it has
        # already sent, so it ends a refusal just as a 200 does.
        self._report_accepted()
        if status == HTTPStatus.NOT_MODIFIED:
            return _Poll.ANSWERED

        try:
            text = body.decode("utf-8")
            parsed = parse(
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

        if isinstance(parsed, Feed):
            return await self._adopt_feed(session, parsed, document, served_etag)

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

    async def _adopt_feed(
        self, session: aiohttp.ClientSession, feed: Feed, document: dict[str, Any], served_etag: str | None
    ) -> _Poll:
        """Cache a major 2 feed's media, then the feed itself, whole.

        **Kept whole, unlike a major 1 manifest, whose entries without a render
        are left out**: every work the schedule names must be a key of `works`
        (`player-contract.md` § Rules a schema cannot state), so dropping one
        would cache a document this reader refuses. A work whose media could not
        be had stays in the feed, and the programme skips it until its file is
        here. Every work the feed carries is fetched, staged ones included, so a
        scene is a switch rather than a download.
        """
        for work in feed.works.values():
            outcome = await self._cache_media(
                session, {"work_id": work.work_id, "media": {"sha256": work.sha256, "url": work.url}}
            )
            if isinstance(outcome, _Retry):
                if self._media_failing.begin():
                    log.warning(
                        "a work's media for this wall could not be fetched (%s); keeping the manifest already cached",
                        outcome.why,
                        extra={"event": "pull.media_failing"},
                    )
                return _Poll.MEDIA_FAILING
        if self._media_failing.end():
            log.info("renders for this wall arrive again", extra={"event": "pull.media_ok"})
        previous = self._cached_render_names()
        _write_atomically(self._cache / CACHED_MANIFEST_FILENAME, json.dumps(document, indent=2).encode("utf-8"))
        if served_etag:
            _write_atomically(self._cache / ETAG_FILENAME, served_etag.encode("utf-8"))
        held = {Path(work.media_path).name for work in feed.works.values() if (self._cache / work.media_path).is_file()}
        kept = self._evict(held | previous)
        log.info(
            "cached the feed for this wall with %d of %d works' media; %d held",
            len(held),
            len(feed.works),
            kept,
            extra={"event": "pull.adopted", "works": len(feed.works), "media_held": len(held)},
        )
        return _Poll.ANSWERED

    async def _cache_media(  # noqa: PLR0911 -- one return per way a render can be had, skipped or retried
        self, session: aiohttp.ClientSession, entry: dict[str, Any]
    ) -> "str | bool | _Retry":
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
                data = await response.read() if status == HTTPStatus.OK else b""
        except _UNREACHABLE as exc:
            return _Retry(f"{type(exc).__name__} fetching it")
        if status == HTTPStatus.NOT_FOUND:
            self._skip_once(f"missing:{sha}", "the render for work %s is not held by the server; skipping it", work_id)
            return False
        if status != HTTPStatus.OK:
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
        if isinstance(cached.get("works"), dict):
            # A major 2 feed: each work's media, by the name the pull gives it.
            return {
                f"sha256-{work['media']['sha256']}"
                for work in cached["works"].values()
                if isinstance(work, dict) and isinstance(work.get("media"), dict) and isinstance(work["media"].get("sha256"), str)
            }
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
        if status == HTTPStatus.NO_CONTENT:
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
        self._uncacheable = ReportOnce()
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

    async def fetch(  # noqa: C901, PLR0911, PLR0912 -- one branch per answer the server can give, each keeping the walls running
        self,
    ) -> ClientDocument | None:
        """A new client document, or None to keep the walls already running."""
        headers = self._auth()
        etag = self._cached_etag()
        if etag is not None:
            headers["If-None-Match"] = etag
        try:
            async with self._client().get(self._client_url, headers=headers) as response:
                status = response.status
                body = await response.read() if status == HTTPStatus.OK else b""
                served_etag = response.headers.get("ETag")
        except _UNREACHABLE as exc:
            self._report_unreachable(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)
            return None
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
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
        if status == HTTPStatus.NOT_MODIFIED:
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
        # **A cache that cannot be written costs the cache, not the walls.** The
        # document is handed over all the same: a full disk would otherwise end
        # the process, and every restart would meet the same disk.
        try:
            self._document_path.parent.mkdir(parents=True, exist_ok=True)
            _write_atomically(self._document_path, text.encode("utf-8"))
            if served_etag:
                _write_atomically(self._etag_path, served_etag.encode("utf-8"))
            else:
                self._etag_path.unlink(missing_ok=True)
        except OSError as exc:
            if self._uncacheable.begin():
                log.error(  # noqa: TRY400 -- the message is the finding
                    "the client document cannot be cached at %s (%s); the walls follow it, and a restart "
                    "while the server is down starts from the last one cached",
                    self._document_path,
                    exc,
                    extra={"event": "client.cache_unwritable"},
                )
            return document
        if self._uncacheable.end():
            log.info("the client document is cached again", extra={"event": "client.cache_writable"})
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
        if status == HTTPStatus.NO_CONTENT:
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
        except (OSError, UnicodeDecodeError):
            # Missing or unreadable, the answer is the same: ask without one,
            # and the server sends the whole document.
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
class LabelAnswer:
    """What one poll of a label document found."""

    #: False when the server could not be reached (no answer, a timeout, a 5xx):
    #: the renderer reads its last document as offline. True for every answer,
    #: a refusal included.
    reachable: bool
    #: A new document this reader accepted, or None to keep the one it has.
    document: LabelDocument | None = None


class LabelPull:
    """`GET /labels/{label_id}` with this client's token and an ETag: a label renderer's link.

    **Read with the manifest's posture.** A refusal (`401`, `403`, `404`) or a
    document this reader cannot use keeps the last good one; transport errors,
    timeouts and `5xx` mean the server is unreachable, which the renderer answers
    by holding its caption for the rule's 30 minutes. Each is said once when it
    starts and once when it ends. The ETag is held in memory beside the document
    the renderer holds, so a restarted renderer asks for the whole document.
    """

    def __init__(self, settings: ClientSettings, label_id: str) -> None:
        self._server = settings.server_url
        self._token = settings.client_token
        self._label_id = label_id
        self._url = self._server + LABEL_ROUTE.format(label_id=label_id)
        self._etag: str | None = None
        self._session: aiohttp.ClientSession | None = None
        self._unreachable = ReportOnce()
        self._refused_status: dict[int, ReportOnce] = {}
        self._unreadable = ReportOnce()

    async def fetch(self) -> LabelAnswer:  # noqa: C901 -- one branch per answer the server can give
        headers = {"Authorization": f"Bearer {self._token}"}
        if self._etag is not None:
            headers["If-None-Match"] = self._etag
        try:
            async with self._client().get(self._url, headers=headers) as response:
                status = response.status
                body = await response.read() if status == HTTPStatus.OK else b""
                served_etag = response.headers.get("ETag")
        except _UNREACHABLE as exc:
            self._report_unreachable(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)
            return LabelAnswer(reachable=False)
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            self._report_unreachable(f"it answered {status}")
            return LabelAnswer(reachable=False)
        if self._unreachable.end():
            log.info(
                "the server answers label %s again",
                self._label_id,
                extra={"event": "label.server_reachable", "label_id": self._label_id},
            )
        if status not in (200, 304):
            episode = self._refused_status.setdefault(status, ReportOnce())
            if episode.begin():
                reason = {
                    401: "it does not accept this client's token (CLIENT_TOKEN)",
                    403: "this label output is not this client's, or the server holds no such label",
                }.get(status, f"it answered {status}")
                log.error(
                    "the server refused label %s: %s; keeping what the panel shows",
                    self._label_id,
                    reason,
                    extra={"event": "label.refused", "label_id": self._label_id, "status": status},
                )
            return LabelAnswer(reachable=True)
        for refused, episode in self._refused_status.items():
            if episode.end():
                log.info(
                    "the server serves label %s again after %d",
                    self._label_id,
                    refused,
                    extra={"event": "label.accepted", "label_id": self._label_id, "status": refused},
                )
        if status == HTTPStatus.NOT_MODIFIED:
            return LabelAnswer(reachable=True)
        try:
            document = parse_label_document(body.decode("utf-8"))
        except (UnicodeDecodeError, LabelDocumentUnreadable) as exc:
            if self._unreadable.begin():
                log.error(  # noqa: TRY400 -- the message is the finding
                    "refusing the label document the server sent for %s (%s); keeping the last one",
                    self._label_id,
                    exc,
                    extra={"event": "label.document_refused", "label_id": self._label_id},
                )
            return LabelAnswer(reachable=True)
        if self._unreadable.end():
            log.info(
                "the server's label document for %s can be read again",
                self._label_id,
                extra={"event": "label.document_readable", "label_id": self._label_id},
            )
        self._etag = served_etag or None
        return LabelAnswer(reachable=True, document=document)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _client(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10, connect=5))
        return self._session

    def _report_unreachable(self, why: str) -> None:
        if self._unreachable.begin():
            log.warning(
                "the server at %s cannot be reached for label %s (%s); the label holds its caption for 30 minutes",
                self._server,
                self._label_id,
                why,
                extra={"event": "label.server_unreachable", "label_id": self._label_id, "server_url": self._server},
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
        temporary.replace(path)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; the temp file must go on any exit
        temporary.unlink(missing_ok=True)
        raise
