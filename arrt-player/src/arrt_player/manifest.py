"""Reading the one channel from curation, and refusing to guess at a bad one.

The manifest is **desired display state**, not a list: it carries the ordered
entries, the pace to show them at, and a directive block through which a curator's
`next` and `show_now` reach this plane. The pull caches each wall's copy
atomically — a temp file in the same directory, then `os.replace` — so a reader
never observes a partial document and no lock is needed on either side.

**Change is detected by polling the mtime**, roughly once a second, rather than by
inotify. A poll is a mechanism that cannot silently unsubscribe; a watch is one
that can, and the failure is a wall that stops responding with nothing in the
journal to say why.

Two refusals live here, and they share a posture: **when the channel says
something impossible, keep what you have and say so, rather than guess.**

* An unrecognised **major** version is refused by contract. Breaking changes bump
  the major, and the two processes restart independently even in a co-located
  deploy, so there is always a window where a new writer's file meets an old
  reader. Rendering a misparse in that window puts wrong art on the wall; keeping
  yesterday's theme and logging is strictly better.
* A **malformed** document is refused the same way, which is the same rule read
  through its own reason: refusing to guess beats rendering a misparse, and a
  document that is not shaped like a manifest is the case where guessing is most
  tempting and least defensible.

An unrecognised **minor** is not a refusal — additive changes are free, and a
reader that rejected them would make every new field a breaking one.

**Two majors are read.** Major 1 is a list of composed renders with a rotation
and a directive (`Manifest`); major 2 is a feed: the works, a schedule of
absolute slots, and a scene and staging when the wall has a control layer
(`Feed`, `player-contract.md` § Major 2). A major 2 document is refused for the
rules a Player acts on — its shape where this reader reads it, the instants,
and the five rules a schema cannot state — and **never for a presentation
setting**: a Player applies the settings its display can honour and ignores the
rest (§ Presentation settings), so a mat mode this Player does not know costs a
mat, never the wall.
"""

import itertools
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

log = logging.getLogger(__name__)

#: The manifest majors this reader understands. Anything else is kept off the wall.
SUPPORTED_SCHEMA_MAJORS: Final[tuple[int, ...]] = (1, 2)

#: The majors this Player asks the server for, highest first, and reports in its
#: heartbeat's `manifest_majors` (`player-contract.md` § The cutover). **Narrower
#: than what it reads, on purpose**: a major 2 work is a presentation master that
#: needs a mat drawn around it, and until this Player composes (wave 4d) asking
#: for major 2 would put an unmatted master on the wall the moment a server
#: published one. One constant for both, so the Player never reports a major it
#: does not ask for.
REQUESTED_MAJORS: Final[tuple[int, ...]] = (1,)

#: Where the pull keeps media, relative to the wall's directory, each file named
#: by the SHA-256 of its bytes: a major 1 render and a major 2 work's master alike.
MEDIA_DIRNAME: Final[str] = "media"

#: `player-contract.md` § Time: RFC 3339 with an offset, as the schema's
#: `instant` pattern states it. Checked before parsing, because
#: `datetime.fromisoformat` accepts forms the contract does not, and a time with
#: no offset is the one a Player could only guess the zone of.
_INSTANT: Final[re.Pattern[str]] = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})"
)
_SHA256: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")


class ManifestUnreadable(Exception):
    """The file is not a manifest this reader can act on."""


class ManifestVersionUnsupported(ManifestUnreadable):
    """The file is a manifest of a major version this reader does not know.

    A subclass rather than a sibling, because every caller that wants to keep the
    last good manifest wants to do so for both — but the two are logged
    differently, since one means "upgrade the display plane" and the other means
    "something wrote a broken file".
    """

    def __init__(self, major: int) -> None:
        super().__init__(
            f"manifest schema major {major} is not supported by this display plane (it understands "
            f"{', '.join(str(known) for known in SUPPORTED_SCHEMA_MAJORS)}); keeping the manifest already loaded"
        )
        self.major = major


@dataclass(frozen=True)
class Entry:
    """One work on the wall: what to show, and what a label would say about it."""

    work_id: str
    #: Relative to the render root, never absolute: the wall's own directory in
    #: this Player's cache, where the pull names each render by its hash. The
    #: path crossing as a relative one is what keeps where the cache is from
    #: being load-bearing.
    render_path: str
    #: Label *text* crosses the channel; label *rendering* does not. Nothing in
    #: this chunk reads it, and it is carried rather than dropped because the
    #: plane that renders the label reads the same manifest object.
    label: dict[str, Any]


@dataclass(frozen=True)
class Manifest:
    """One published desired-state document, already checked."""

    schema_major: int
    schema_minor: int
    theme_id: str | None
    theme_name: str | None
    rotation_interval_seconds: int
    shuffle: bool
    directive_sequence: int
    pinned_work_id: str | None
    entries: tuple[Entry, ...]

    def index_of(self, work_id: str) -> int | None:
        """Where a work sits in the published order, or None if it is not carried.

        None is the ordinary answer rather than an error: `show_now` checks that a
        work *could* reach the wall, not that it is in the active theme, so a pin
        naming a work this manifest does not list is a supported outcome.
        """
        for position, entry in enumerate(self.entries):
            if entry.work_id == work_id:
                return position
        return None


@dataclass(frozen=True)
class Work:
    """One work a major 2 feed names: its media, its mat colour and its label."""

    work_id: str
    #: The media's SHA-256, lowercase hex: its name in the cache.
    sha256: str
    #: Where the pull fetches it, resolved against the manifest's own URL.
    url: str
    #: Carried for the compositor; this reader does not judge it (a setting
    #: of the work's presentation is never a reason to refuse the document).
    mat_color: object
    label: dict[str, Any]

    @property
    def media_path(self) -> str:
        """Where the pull keeps the media, relative to the wall's directory."""
        return f"{MEDIA_DIRNAME}/sha256-{self.sha256}"


@dataclass(frozen=True)
class Slot:
    """A half-open span of absolute time and the work it shows."""

    work_id: str
    start: datetime
    until: datetime


@dataclass(frozen=True)
class Scene:
    """A live override with a lifetime; `until` None holds it until it is released."""

    scene_id: str
    work_id: str
    start: datetime
    until: datetime | None


@dataclass(frozen=True)
class Feed:
    """One published major 2 document, already checked (`player-contract.md` § Major 2)."""

    schema_major: int
    schema_minor: int
    playlist_id: str | None
    playlist_name: str | None
    works: dict[str, Work]
    horizon_start: datetime
    horizon_until: datetime
    slots: tuple[Slot, ...]
    scene: Scene | None
    staging: tuple[str, ...]
    #: The feed's presentation defaults, as sent. Read by the compositor, never
    #: a reason to refuse the document.
    settings: dict[str, Any]

    @property
    def theme_id(self) -> str | None:
        """The playlist, under the name the heartbeat has always given it."""
        return self.playlist_id

    def named(self) -> tuple[str, ...]:
        """Every work the schedule, the scene or staging names, each once, in that order."""
        order = [slot.work_id for slot in self.slots]
        if self.scene is not None:
            order.append(self.scene.work_id)
        order.extend(self.staging)
        return tuple(dict.fromkeys(order))


def parse(text: str, *, rotation_interval_fallback: int, shuffle_fallback: bool) -> "Manifest | Feed":
    """Turn the file's bytes into a `Manifest` (major 1) or a `Feed` (major 2), or refuse it.

    Version is checked **before** structure, because a future major is expected to
    be shaped differently: reporting "entries is missing" for a document whose
    major says plainly that this reader should not be reading it would send
    whoever finds it looking for a bug in the writer.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestUnreadable(f"the manifest is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise ManifestUnreadable(f"the manifest is a {type(document).__name__}, not an object")

    schema = document.get("schema")
    if not isinstance(schema, dict) or not isinstance(schema.get("major"), int):
        raise ManifestUnreadable("the manifest carries no schema major version")
    major = schema["major"]
    if major not in SUPPORTED_SCHEMA_MAJORS:
        raise ManifestVersionUnsupported(major)
    if major == 2:  # noqa: PLR2004 -- the major is the name of a shape, not a magnitude
        return _feed(document)

    entries_raw = document.get("entries")
    if not isinstance(entries_raw, list):
        raise ManifestUnreadable("the manifest carries no entries list")

    entries = tuple(_entry(item, position) for position, item in enumerate(entries_raw))

    rotation = document.get("rotation") if isinstance(document.get("rotation"), dict) else {}
    directive = document.get("directive") if isinstance(document.get("directive"), dict) else {}
    theme = document.get("theme") if isinstance(document.get("theme"), dict) else {}

    sequence = directive.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        # Not defaulted to zero: the sequence is the whole directive mechanism,
        # and a reader that invented a value for it would re-baseline against a
        # number the writer never published — silently disarming `next` and
        # `show_now` rather than reporting that the file is wrong.
        raise ManifestUnreadable("the manifest's directive carries no integer sequence")

    pinned = directive.get("pinned_work_id")
    if pinned is not None and not isinstance(pinned, str):
        raise ManifestUnreadable(f"the manifest's pinned_work_id is a {type(pinned).__name__}, not a string or null")

    interval = rotation.get("interval_seconds")
    shuffle = rotation.get("shuffle")
    return Manifest(
        schema_major=major,
        schema_minor=schema.get("minor") if isinstance(schema.get("minor"), int) else 0,
        theme_id=theme.get("id") if isinstance(theme.get("id"), str) else None,
        theme_name=theme.get("name") if isinstance(theme.get("name"), str) else None,
        # Falling back rather than refusing, and the asymmetry with `sequence`
        # above is deliberate: a missing pace has a right answer this deployment
        # already knows, while a missing sequence has none that is safe to invent.
        rotation_interval_seconds=(
            interval
            if isinstance(interval, int) and not isinstance(interval, bool) and interval > 0
            else rotation_interval_fallback
        ),
        shuffle=shuffle if isinstance(shuffle, bool) else shuffle_fallback,
        directive_sequence=sequence,
        pinned_work_id=pinned,
        entries=entries,
    )


def _feed(document: dict[str, Any]) -> Feed:  # noqa: C901 -- one refusal per rule, each said where it is checked
    """A major 2 document, refused for anything a Player acts on and nothing else."""
    schema = document["schema"]
    works_raw = document.get("works")
    if not isinstance(works_raw, dict):
        raise ManifestUnreadable("the feed carries no works object")
    works = {work_id: _work(work_id, item) for work_id, item in works_raw.items()}

    schedule = document.get("schedule")
    if not isinstance(schedule, dict):
        raise ManifestUnreadable("the feed carries no schedule")
    horizon = schedule.get("horizon")
    if not isinstance(horizon, dict):
        raise ManifestUnreadable("the feed's schedule carries no horizon")
    horizon_start = _instant(horizon.get("from"), "the horizon's from")
    horizon_until = _instant(horizon.get("until"), "the horizon's until")
    slots_raw = schedule.get("slots")
    if not isinstance(slots_raw, list):
        raise ManifestUnreadable("the feed's schedule carries no slots list")
    slots = tuple(_slot(item, position) for position, item in enumerate(slots_raw))

    scene_raw = document.get("scene")
    scene = None if scene_raw is None else _scene(scene_raw)
    staging_raw = document.get("staging", [])
    if not isinstance(staging_raw, list) or not all(isinstance(item, str) and item for item in staging_raw):
        raise ManifestUnreadable("the feed's staging is not a list of work ids")

    playlist = document.get("playlist") if isinstance(document.get("playlist"), dict) else {}
    settings = document.get("settings")
    feed = Feed(
        schema_major=2,
        schema_minor=schema.get("minor") if isinstance(schema.get("minor"), int) else 0,
        playlist_id=playlist.get("id") if isinstance(playlist.get("id"), str) else None,
        playlist_name=playlist.get("name") if isinstance(playlist.get("name"), str) else None,
        works=works,
        horizon_start=horizon_start,
        horizon_until=horizon_until,
        slots=slots,
        scene=scene,
        staging=tuple(staging_raw),
        settings=settings if isinstance(settings, dict) else {},
    )

    # `player-contract.md` § Rules a schema cannot state, in its order.
    if any(work_id not in works for work_id in feed.named()):
        raise ManifestUnreadable("the feed names a work that is not in its works")
    if any(slot.start >= slot.until for slot in slots):
        raise ManifestUnreadable("a slot ends before it starts")
    if any(first.until > second.start for first, second in itertools.pairwise(slots)):
        raise ManifestUnreadable("the slots overlap or run out of order")
    span = horizon_until - horizon_start
    if span <= timedelta(0) or span % timedelta(days=1):
        raise ManifestUnreadable("the horizon is not a whole number of days")
    if any(slot.start < horizon_start or slot.until > horizon_until for slot in slots):
        raise ManifestUnreadable("a slot falls outside the horizon")
    if scene is not None and scene.until is not None and scene.until <= scene.start:
        raise ManifestUnreadable("the scene ends before it starts")
    return feed


def _work(work_id: object, item: object) -> Work:
    if not isinstance(work_id, str) or not work_id:
        raise ManifestUnreadable("the feed's works has an empty id")
    if not isinstance(item, dict):
        raise ManifestUnreadable(f"work {work_id} is not an object")
    media = item.get("media")
    sha = media.get("sha256") if isinstance(media, dict) else None
    url = media.get("url") if isinstance(media, dict) else None
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha) or not isinstance(url, str) or not url:
        raise ManifestUnreadable(f"work {work_id} carries no media with a sha256 and a url")
    label = item.get("label")
    return Work(
        work_id=work_id, sha256=sha, url=url, mat_color=item.get("mat_color"), label=label if isinstance(label, dict) else {}
    )


def _slot(item: object, position: int) -> Slot:
    if not isinstance(item, dict):
        raise ManifestUnreadable(f"slot {position} is not an object")
    work_id = item.get("work_id")
    if not isinstance(work_id, str) or not work_id:
        raise ManifestUnreadable(f"slot {position} carries no work_id")
    return Slot(
        work_id=work_id,
        start=_instant(item.get("from"), f"slot {position}'s from"),
        until=_instant(item.get("until"), f"slot {position}'s until"),
    )


def _scene(item: object) -> Scene:
    if not isinstance(item, dict):
        raise ManifestUnreadable("the scene is neither null nor an object")
    scene_id, work_id = item.get("id"), item.get("work_id")
    if not isinstance(scene_id, str) or not scene_id or not isinstance(work_id, str) or not work_id:
        raise ManifestUnreadable("the scene carries no id or no work_id")
    if "until" not in item:
        # Null means "held until released"; absent is a document that forgot to say.
        raise ManifestUnreadable("the scene carries no until")
    until = item["until"]
    return Scene(
        scene_id=scene_id,
        work_id=work_id,
        start=_instant(item.get("from"), "the scene's from"),
        until=None if until is None else _instant(until, "the scene's until"),
    )


def _instant(value: object, what: str) -> datetime:
    """An RFC 3339 instant with an offset, or a refusal naming which one it is not."""
    if value is None:
        raise ManifestUnreadable(f"{what} is missing")
    if not isinstance(value, str) or not _INSTANT.fullmatch(value):
        raise ManifestUnreadable(f"{what} is not an instant with an offset")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ManifestUnreadable(f"{what} is not a real instant ({exc})") from exc


def _entry(item: object, position: int) -> Entry:
    if not isinstance(item, dict):
        raise ManifestUnreadable(f"entry {position} is a {type(item).__name__}, not an object")
    work_id = item.get("work_id")
    render_path = item.get("render_path")
    if not isinstance(work_id, str) or not work_id:
        raise ManifestUnreadable(f"entry {position} carries no work_id")
    if not isinstance(render_path, str) or not render_path:
        raise ManifestUnreadable(f"entry {position} ({work_id}) carries no render_path")
    label = item.get("label")
    return Entry(work_id=work_id, render_path=render_path, label=label if isinstance(label, dict) else {})


class Watcher:
    """Polls one path and hands back a manifest only when a *new, good* one lands.

    Holds the last good manifest so a refusal costs nothing: the wall keeps
    showing what it was showing.

    **A refusal is reported once per file, not once per poll.** At one poll a
    second an unchanged bad manifest would otherwise write 86,400 identical ERROR
    lines a day, which is how a journal stops being readable and how the *next*
    fault gets buried. The mtime that was refused is remembered, so the line is
    written when the file changes and not again until it changes once more.
    """

    def __init__(self, path: Path, *, rotation_interval_fallback: int, shuffle_fallback: bool) -> None:
        self._path = path
        self._rotation_interval_fallback = rotation_interval_fallback
        self._shuffle_fallback = shuffle_fallback
        self._seen_stamp: tuple[int, int] | None = None
        self._current: Manifest | Feed | None = None
        self._reported_absent = False
        self._reported_unstatable = False

    @property
    def current(self) -> "Manifest | Feed | None":
        """The last manifest that was good, or None if none ever has been."""
        return self._current

    def poll(  # noqa: C901, PLR0911 -- each way a manifest file can be refused keeps the loaded one, said where it happens
        self,
    ) -> "Manifest | Feed | None":
        """Read the file if it changed; return the new manifest, or None.

        None means "nothing to do" in every case that is not a fresh, valid
        document — unchanged, absent, unparseable or a major from the future.
        """
        try:
            stat = self._path.stat()
        except FileNotFoundError:
            if not self._reported_absent:
                # INFO, not WARNING: a plane that has not published yet is a
                # normal state on a fresh install, and this plane holding still
                # until it does is the availability norm working rather than a
                # fault. Said once, so the wait is visible in the journal without
                # becoming the journal.
                log.info(
                    "no manifest at %s yet; waiting for the curation plane to publish one",
                    self._path,
                    extra={"event": "manifest.absent", "manifest_path": str(self._path)},
                )
                self._reported_absent = True
            return None
        except OSError as exc:
            if not self._reported_unstatable:
                # **Once, for the same reason the arm above says its piece once.**
                # The faults that reach here do not clear on their own — EIO from
                # a failing SD card, EACCES, ESTALE on a mount that went away —
                # so at a one-second poll this is 86,400 identical WARNINGs a day
                # into a journal that rate-limits, and the lines it drops are the
                # ERRORs that are this plane's only failure channel. Said again
                # when it recovers, so the log carries both ends.
                log.warning(
                    "could not stat the manifest at %s (%s); keeping the one already loaded",
                    self._path,
                    exc,
                    extra={"event": "manifest.unstatable", "manifest_path": str(self._path)},
                )
                self._reported_unstatable = True
            return None

        if self._reported_unstatable:
            log.info(
                "the manifest at %s can be read again",
                self._path,
                extra={"event": "manifest.statable", "manifest_path": str(self._path)},
            )
            self._reported_unstatable = False
        self._reported_absent = False
        # Size joins mtime because a filesystem whose mtime has one-second
        # resolution can land two writes in the same tick, and the second would
        # then never be read. `os.replace` makes that a real sequence rather than
        # a theoretical one: `sync` and a `next` can arrive inside the same second.
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp == self._seen_stamp:
            return None
        self._seen_stamp = stamp

        try:
            text = self._path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            # **Not an `OSError`** — it is a `ValueError`, so it escaped the clause
            # below and every frame above it, taking the process down over a
            # malformed file this module exists to refuse. A truncated write from a
            # filesystem that lost power mid-`replace` produces exactly this.
            log.error(  # noqa: TRY400 -- the byte offset is the finding; the stack is codecs internals
                "the manifest at %s is not valid UTF-8 (%s); keeping the one already loaded",
                self._path,
                exc,
                extra={"event": "manifest.not_text", "manifest_path": str(self._path)},
            )
            return None
        except OSError as exc:
            log.warning(
                "could not read the manifest at %s (%s); keeping the one already loaded",
                self._path,
                exc,
                extra={"event": "manifest.unreadable", "manifest_path": str(self._path)},
            )
            return None

        try:
            manifest = parse(
                text,
                rotation_interval_fallback=self._rotation_interval_fallback,
                shuffle_fallback=self._shuffle_fallback,
            )
        except ManifestVersionUnsupported as exc:
            # `log.error` rather than `log.exception` here and below, deliberately.
            # A traceback for these two is noise that buries the finding: the
            # refusal is a *decision this reader made about a document*, not a
            # crash, and the whole of it is already in the message — the path, the
            # major, and what the parser objected to. A stack through `json.loads`
            # tells the reader nothing they can act on.
            log.error(  # noqa: TRY400 -- the message is the finding; the stack is json.loads internals
                "%s",
                exc,
                extra={
                    "event": "manifest.version_refused",
                    "manifest_path": str(self._path),
                    "observed_major": exc.major,
                    "supported_majors": list(SUPPORTED_SCHEMA_MAJORS),
                },
            )
            return None
        except ManifestUnreadable as exc:
            log.error(  # noqa: TRY400 -- the message is the finding; the stack is json.loads internals
                "refusing the manifest at %s (%s); keeping the one already loaded",
                self._path,
                exc,
                extra={"event": "manifest.refused", "manifest_path": str(self._path)},
            )
            return None

        self._current = manifest
        if isinstance(manifest, Feed):
            log.info(
                "adopted the feed for playlist %s with %d slots over %d works",
                manifest.playlist_name or manifest.playlist_id or "(unnamed)",
                len(manifest.slots),
                len(manifest.works),
                extra={
                    "event": "manifest.adopted",
                    "theme_id": manifest.playlist_id,
                    "slots": len(manifest.slots),
                    "works": len(manifest.works),
                    "scene_id": manifest.scene.scene_id if manifest.scene is not None else None,
                    "schema": f"{manifest.schema_major}.{manifest.schema_minor}",
                },
            )
            return manifest
        log.info(
            "adopted manifest for theme %s with %d entries",
            manifest.theme_name or manifest.theme_id or "(unnamed)",
            len(manifest.entries),
            extra={
                "event": "manifest.adopted",
                "theme_id": manifest.theme_id,
                "entries": len(manifest.entries),
                "sequence": manifest.directive_sequence,
                "schema": f"{manifest.schema_major}.{manifest.schema_minor}",
            },
        )
        return manifest
