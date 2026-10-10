"""The Player as a client: one process, one worker per wall the server assigns it.

`clients.md` § The Player. A client is configured with the server, its token and
its cache, and nothing about walls. It asks the server which walls it drives
(`GET /client`, about every 30 seconds), starts a worker for each on the output
the curator chose, stops the worker for a wall taken away, and tells the server
which outputs it has (`POST /client/heartbeat`) so a curator can choose one by
name. `player-contract.md` § Transport is the specification of both routes.

**Labels are run the same way, beside the walls** (`labels-and-surfaces.md`).
The client reports its label outputs too, and the document names which of them
caption a wall; the supervisor runs one label renderer per mapped label output,
keyed on the output, and stops it when the mapping goes. A label's wall need not
be one this client shows.

**This module speaks no HTTP.** The two requests are made by `pull.py`, the one
module the plane-isolation guard lets hold a client, and handed in by the entry
point as a `ClientLink`. So is the worker itself: what runs a wall on the Frame
names the television's library, and only the composition root may.

**Every failure keeps the walls running** (`player-contract.md`: every failure
keeps the cache). A server that cannot be reached, refuses this client's token
or sends a document this reader cannot use changes nothing: the walls already
running go on rotating their caches. The last good document is kept on disk
(`ClientLink.cached`), so a client restarted while the server is down starts
the walls it last knew rather than none.

**A worker that fails is restarted here rather than taking the process down.**
One process drives every wall this client has, so a fault in one wall's worker
— its pull dying on a full disk, its television's library raising something
nobody predicted — must not blank the others. Each crash is logged at ERROR with
its traceback, and the worker is started again after a wait that doubles to a
ceiling. The supervisor's own failure is not caught: that ends the process, and
systemd restarts it.
"""

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Protocol

from arrt_player import heartbeat as heartbeat_module
from arrt_player.config import FRAME_OUTPUT, ClientSettings, WallIdUnusable, WallSettings
from arrt_player.episodes import Backoff, ReportOnce

log = logging.getLogger(__name__)

#: Where the kernel lists display connectors. Injectable everywhere it is read,
#: so the suite reads a directory it built rather than the machine it runs on.
DRM_ROOT: Final[Path] = Path("/sys/class/drm")

#: An HDMI connector's sysfs directory: `card0-HDMI-A-1`. The card number is
#: dropped from the output's name, because it is the driver's enumeration order
#: rather than anything a person plugged a cable into, and it can change across a
#: kernel update while the socket on the board does not.
_HDMI_CONNECTOR: Final = re.compile(r"card\d+-HDMI-A-(\d+)")

#: A mode as `modes` lists it: `1920x1080`, sometimes with a suffix (`i`).
_MODE: Final = re.compile(r"(\d+)x(\d+)")

#: The two output kinds the client heartbeat names.
FRAME_KIND: Final[str] = "frame"
FRAMEBUFFER_KIND: Final[str] = "framebuffer"
#: The one label output kind the client heartbeat names.
EPAPER_KIND: Final[str] = "epaper"

#: How long the Frame's identity read may take before this report goes without it.
#: The read has its own shorter bound inside the television's seam; this one is
#: the supervisor's, so no seam can hold a client poll for longer.
IDENTITY_READ_BUDGET_SECONDS: Final[float] = 5.0

#: Bounds on the wait before a crashed worker is started again. Short enough
#: that a passing fault costs the wall seconds; capped so a worker that fails
#: on every start costs a line every five minutes rather than a line a second.
RESTART_MIN_SECONDS: Final[float] = 5.0
RESTART_MAX_SECONDS: Final[float] = 300.0


# -- the client document ---------------------------------------------------------------


class ClientDocumentUnreadable(Exception):
    """A `GET /client` answer this reader will not act on."""


@dataclass(frozen=True)
class Assignment:
    """One wall this client drives, and the output it is shown on."""

    wall_id: str
    name: str
    output: str
    #: The server's id for the display behind `output`, or None from a server
    #: that does not name one. A worker is keyed on the output, never on this.
    display: str | None = None


@dataclass(frozen=True)
class LabelAssignment:
    """One of this client's label outputs, and the wall it captions."""

    label_id: str
    output: str
    wall_id: str


@dataclass(frozen=True)
class ClientDocument:
    """What `GET /client` answered: this client, its walls, and its labels."""

    client_id: str
    name: str
    walls: tuple[Assignment, ...]
    #: Empty from a server that names no labels, which is the same as none.
    labels: tuple[LabelAssignment, ...] = ()


def parse_client_document(text: str) -> ClientDocument:
    """Read a client document (`contract/schemas/client.v1.schema.json`), or refuse it.

    **Refused whole rather than read in part.** A document that names a wall
    without its output, or whose walls are not a list, is one where acting on the
    readable part would stop workers for every wall the unreadable part named. So
    a refusal keeps the walls already running, which is what every other failure
    here does too. Unknown keys are allowed, as the schema allows them.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClientDocumentUnreadable(f"the client document is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ClientDocumentUnreadable(f"the client document is a {type(document).__name__}, not an object")
    client_id, name, walls = document.get("client_id"), document.get("name"), document.get("walls")
    if not _text(client_id) or not _text(name):
        raise ClientDocumentUnreadable("the client document carries no client_id or name")
    if not isinstance(walls, list):
        raise ClientDocumentUnreadable("the client document's walls are not a list")
    assignments = []
    for position, wall in enumerate(walls):
        if not isinstance(wall, dict):
            raise ClientDocumentUnreadable(f"wall {position} is a {type(wall).__name__}, not an object")
        for key in ("wall_id", "name", "output"):
            if not _text(wall.get(key)):
                raise ClientDocumentUnreadable(f"wall {position} carries no {key}")
        if "display" in wall and not _text(wall["display"]):
            raise ClientDocumentUnreadable(f"wall {position} names its display without an id")
        assignments.append(
            Assignment(wall_id=wall["wall_id"], name=wall["name"], output=wall["output"], display=wall.get("display"))
        )
    return ClientDocument(client_id=client_id, name=name, walls=tuple(assignments), labels=_labels(document))


def _labels(document: dict) -> tuple[LabelAssignment, ...]:
    """The document's labels, absent read as none, and refused whole like its walls."""
    labels = document.get("labels", [])
    if not isinstance(labels, list):
        raise ClientDocumentUnreadable("the client document's labels are not a list")
    read = []
    for position, label in enumerate(labels):
        if not isinstance(label, dict):
            raise ClientDocumentUnreadable(f"label {position} is a {type(label).__name__}, not an object")
        for key in ("label_id", "output", "wall_id"):
            if not _text(label.get(key)):
                raise ClientDocumentUnreadable(f"label {position} carries no {key}")
        read.append(LabelAssignment(label_id=label["label_id"], output=label["output"], wall_id=label["wall_id"]))
    return tuple(read)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


# -- outputs -------------------------------------------------------------------------


@dataclass(frozen=True)
class OutputReport:
    """One output this client can drive, as the client heartbeat states it."""

    name: str
    kind: str
    connected: bool
    #: `(width, height)` in pixels, or None when the client does not know it.
    screen: tuple[int, int] | None
    #: Who the display is, as read from the device itself; None for an output
    #: with no identity a client can read, and then the key is left out.
    identity: str | None = None

    def document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "connected": self.connected,
            "screen": list(self.screen) if self.screen is not None else None,
        }
        if self.identity is not None:
            document["identity"] = self.identity
        return document


@dataclass(frozen=True)
class LabelOutputReport:
    """One label output this client holds, as the client heartbeat states it."""

    name: str
    kind: str
    #: Whether the panel answers now: false for one that would not open, and
    #: for one whose last draw failed.
    connected: bool
    #: `(width, height)` in pixels, or None when the client does not know it.
    size: tuple[int, int] | None

    def document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "connected": self.connected,
            "size": list(self.size) if self.size is not None else None,
        }


class FrameIdentity:
    """The Frame's device id, read once it can be and then kept.

    **Read by the client, not by a wall's worker**, because a Frame with no wall on
    it must still say who it is: a Frame moved to a new client has no wall there
    yet, and its walls follow it only once the server hears its identity
    (`player-contract.md` § Transport). The read is the television seam's
    `read_identity`, which opens no art channel and presses no key.

    **Asked again on each report until it answers, then never again**, so a set
    asleep at boot is identified once it wakes, and an identity once read does
    not flap away when a later read would have failed. A failure is said once per
    episode.
    """

    def __init__(self, read: Callable[[], Awaitable[str]], *, budget_seconds: float = IDENTITY_READ_BUDGET_SECONDS) -> None:
        self._read = read
        self._budget = budget_seconds
        self.value: str | None = None
        self._unreadable = ReportOnce()

    async def refresh(self) -> None:
        """Read the identity if it is not yet known. Never raises."""
        if self.value is not None:
            return
        try:
            self.value = await asyncio.wait_for(self._read(), timeout=self._budget)
        # An identity is an annotation: whatever stops the read, the Frame is reported without one.
        except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- see above
            if self._unreadable.begin():
                log.warning(
                    "the Frame's device id could not be read (%s); it is reported without an identity until it can be",
                    f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
                    extra={"event": "client.identity_unreadable", "output": FRAME_OUTPUT},
                )
            return
        if self._unreadable.end():
            log.info("the Frame's device id was read", extra={"event": "client.identity_read", "output": FRAME_OUTPUT})


def hdmi_outputs(drm_root: Path = DRM_ROOT) -> list[OutputReport]:
    """The HDMI connectors the kernel lists, named `hdmi-a-1`, `hdmi-a-2`, connected or not.

    **A connector with nothing plugged in is still listed**, as `connected:
    false`: it is an output a curator may place a wall on before the screen
    arrives, and the worker draws once it does. `connected` is the connector's
    `status` reading `connected`; anything else, `unknown` included, is false,
    because a screen this client cannot confirm is not one it should claim. The
    screen is the first line of `modes`, which the kernel lists preferred mode
    first, and None when nothing is connected or no mode is listed.

    A machine with no DRM directory (a Mac, a container) has no HDMI outputs, and
    that is an answer rather than an error.
    """
    found: dict[str, OutputReport] = {}
    try:
        connectors = sorted(drm_root.iterdir())
    except OSError:
        return []
    for connector in connectors:
        matched = _HDMI_CONNECTOR.fullmatch(connector.name)
        if matched is None:
            continue
        name = f"hdmi-a-{matched.group(1)}"
        if name in found:
            # Two cards exposing the same connector number. The heartbeat may not
            # carry one name twice, and the first card is the one the board's
            # display controller enumerates first.
            continue
        connected = _read_first_line(connector / "status") == "connected"
        found[name] = OutputReport(
            name=name,
            kind=FRAMEBUFFER_KIND,
            connected=connected,
            screen=_mode(_read_first_line(connector / "modes")) if connected else None,
        )
    return list(found.values())


def _read_first_line(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as handle:
            return handle.readline().strip()
    except OSError:
        return ""


def _mode(line: str) -> tuple[int, int] | None:
    matched = _MODE.match(line)
    if matched is None:
        return None
    width, height = int(matched.group(1)), int(matched.group(2))
    return (width, height) if width > 0 and height > 0 else None


def client_outputs(
    settings: ClientSettings, *, drm_root: Path = DRM_ROOT, frame_identity: str | None = None
) -> list[OutputReport]:
    """Every output this client can drive: the Frame when it has one, and its HDMI connectors.

    **The Frame is reported connected because it is configured**, with no screen
    size. It is a television on the network rather than a cable this host can
    sense, and whether it answers is a fact about the wall shown on it, which
    that wall's own heartbeat reports (`television_reachable`). Its size is the
    wall's to report: this Player composes for the panel it is configured with,
    and the wall's heartbeat carries it (`capabilities`). Its identity is what
    `FrameIdentity` has read, if anything yet.
    """
    outputs = (
        [OutputReport(name=FRAME_OUTPUT, kind=FRAME_KIND, connected=True, screen=None, identity=frame_identity)]
        if settings.frame
        else []
    )
    return outputs + hdmi_outputs(drm_root)


def client_heartbeat(
    outputs: list[OutputReport], *, reported_at: datetime, label_outputs: list[LabelOutputReport] | None = None
) -> dict[str, Any]:
    """The client heartbeat (`contract/schemas/client-heartbeat.v1.schema.json`).

    `label_outputs` is left out for a client that holds none, which is how the
    schema reads a client with no label outputs.
    """
    heartbeat: dict[str, Any] = {
        heartbeat_module.REPORTED_AT_KEY: reported_at.isoformat(),
        "outputs": [output.document() for output in outputs],
    }
    if label_outputs:
        heartbeat["label_outputs"] = [output.document() for output in label_outputs]
    return heartbeat


# -- the supervisor --------------------------------------------------------------------


class ClientLink(Protocol):
    """The two client routes, as the supervisor needs them. `pull.ClientPull` is the real one."""

    def cached(self) -> ClientDocument | None:
        """The last good document, from before this process started, or None."""

    async def fetch(self) -> ClientDocument | None:
        """A new document when the server sent one this reader accepts, else None: keep what you have."""

    async def report(self, heartbeat: dict[str, Any]) -> bool:
        """POST the client heartbeat. True when the server took it."""

    async def close(self) -> None: ...


#: What runs one wall: given its settings, the output it is on, and the event
#: that stops it, run until stopped. It may raise; the supervisor restarts it.
Worker = Callable[[WallSettings, OutputReport, asyncio.Event], Awaitable[None]]

#: What runs one label output: given its assignment, the event that stops it and
#: the event set beside it when the mapping went (rather than the client
#: stopping), run until stopped. It may raise; the supervisor restarts it.
LabelWorker = Callable[[LabelAssignment, asyncio.Event, asyncio.Event], Awaitable[None]]


@dataclass
class _Running:
    assignment: Assignment
    stop: asyncio.Event
    task: asyncio.Task[None]


@dataclass
class _RunningLabel:
    assignment: LabelAssignment
    stop: asyncio.Event
    retired: asyncio.Event
    task: asyncio.Task[None]


class Supervisor:
    """Keeps one worker running per wall the server assigns this client, on its output."""

    def __init__(
        self,
        *,
        settings: ClientSettings,
        link: ClientLink,
        worker: Worker,
        outputs: Callable[[], list[OutputReport]],
        now: Callable[[], datetime],
        monotonic: Callable[[], float],
        label_worker: LabelWorker | None = None,
        label_outputs: Callable[[], list[LabelOutputReport]] = list,
        frame_identity: FrameIdentity | None = None,
        restart_min_seconds: float = RESTART_MIN_SECONDS,
        restart_max_seconds: float = RESTART_MAX_SECONDS,
    ) -> None:
        self._settings = settings
        self._link = link
        self._worker = worker
        self._outputs = outputs
        self._label_worker = label_worker
        self._label_outputs = label_outputs
        self._frame_identity = frame_identity
        self._now = now
        self._monotonic = monotonic
        self._restart_min = restart_min_seconds
        self._restart_max = restart_max_seconds
        self._running: dict[str, _Running] = {}
        #: One renderer per label output, keyed on the output's name: a label is
        #: drawn on a surface, and two renderers on one surface would fight.
        self._labels: dict[str, _RunningLabel] = {}
        #: Workers asked to stop and not yet finished, so shutdown can wait for
        #: each to close what it holds — on the Frame, the art channel.
        self._stopping: set[asyncio.Task[None]] = set()
        #: Assignments already reported as impossible, so each is said once. Keyed
        #: on the wall *and* the output: a wall moved to another output it also
        #: lacks is news.
        self._reported_unplaceable: set[tuple[str, str]] = set()
        self._reported_unplaceable_labels: set[tuple[str, str]] = set()
        self._reported_outputs: tuple[list[OutputReport], list[LabelOutputReport]] | None = None
        self._reported_at: float | None = None

    @property
    def running(self) -> dict[str, str]:
        """Each wall with a worker, and the output it is on."""
        return {wall_id: running.assignment.output for wall_id, running in self._running.items()}

    @property
    def labels(self) -> dict[str, LabelAssignment]:
        """Each label output with a renderer, and what it captions."""
        return {output: running.assignment for output, running in self._labels.items()}

    async def run(self, stop: asyncio.Event) -> None:
        """Supervise until asked to stop, then stop every worker and wait for each."""
        log.info(
            "client starting against %s",
            self._settings.server_url,
            extra={"event": "client.started", **self._settings.startup_lines()},
        )
        try:
            cached = self._link.cached()
            if cached is not None:
                # **Before the first request**, so a server that is down at boot
                # costs the walls nothing.
                self.reconcile(cached)
            while not stop.is_set():
                await self.cycle()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self._settings.client_poll_seconds)
        finally:
            await self.stop_all()
            await self._link.close()
            log.info("client stopped", extra={"event": "client.stopped"})

    async def cycle(self) -> None:
        """One poll: the outputs reported if they are due, then the walls."""
        await self._report_outputs()
        document = await self._link.fetch()
        if document is not None:
            self.reconcile(document)

    # -- the walls ------------------------------------------------------------------

    def reconcile(self, document: ClientDocument) -> None:
        """Make the running workers match the document: start, stop, move."""
        available = {output.name: output for output in self._outputs()}
        wanted: dict[str, Assignment] = {}
        claimed: dict[str, str] = {}
        for assignment in document.walls:
            output = available.get(assignment.output)
            if output is None:
                self._unplaceable(assignment, "this client has no output by that name")
                continue
            if assignment.output in claimed:
                # The server refuses two walls on one output; a client that met
                # it anyway shows the first and says so, rather than letting two
                # workers fight over one screen.
                self._unplaceable(assignment, f"wall {claimed[assignment.output]} is already shown there")
                continue
            claimed[assignment.output] = assignment.wall_id
            wanted[assignment.wall_id] = assignment

        for wall_id, running in list(self._running.items()):
            target = wanted.get(wall_id)
            if target is None or target.output != running.assignment.output:
                self._stop(wall_id, moved_to=target.output if target is not None else None)

        for wall_id, assignment in wanted.items():
            if wall_id in self._running:
                continue
            try:
                wall = self._settings.wall(wall_id)
            except WallIdUnusable as exc:
                self._unplaceable(assignment, str(exc))
                continue
            self._start(wall, assignment, available[assignment.output])

        self._reconcile_labels(document)

    # -- the labels -----------------------------------------------------------------

    def _reconcile_labels(self, document: ClientDocument) -> None:
        """Make the running label renderers match the document's labels.

        A renderer is restarted when its output's label changes (another wall, or
        another label id), and **retired** when its output is no longer mapped at
        all, which tells it to leave the panel blank rather than captioning a wall
        it no longer belongs to.
        """
        if self._label_worker is None:
            return
        available = {output.name for output in self._label_outputs()}
        wanted: dict[str, LabelAssignment] = {}
        for label in document.labels:
            if label.output not in available:
                self._label_unplaceable(label, "this client has no label output by that name")
                continue
            if label.output in wanted:
                self._label_unplaceable(label, f"label {wanted[label.output].label_id} is already drawn there")
                continue
            wanted[label.output] = label

        for output, running in list(self._labels.items()):
            target = wanted.get(output)
            if target != running.assignment:
                self._stop_label(output, retired=target is None)

        for output, label in wanted.items():
            if output not in self._labels:
                self._start_label(label)

    def _start_label(self, label: LabelAssignment) -> None:
        stop, retired = asyncio.Event(), asyncio.Event()
        worker = self._label_worker
        assert worker is not None  # noqa: S101 -- reconcile returns before here without one
        # After every renderer still stopping, for the reason walls wait: two
        # renderers drawing on one panel at once.
        stopping = tuple(self._stopping)
        task = asyncio.create_task(
            self._keep_running(
                lambda: worker(label, stop, retired),
                stop,
                what=f"the renderer for label {label.label_id} on {label.output}",
                event="client.label",
                extra={"label_id": label.label_id, "output": label.output, "wall_id": label.wall_id},
                after=stopping,
            ),
            name=f"label:{label.output}",
        )
        self._labels[label.output] = _RunningLabel(assignment=label, stop=stop, retired=retired, task=task)
        self._reported_unplaceable_labels = {key for key in self._reported_unplaceable_labels if key[0] != label.label_id}
        log.info(
            "captioning wall %s with label %s on %s",
            label.wall_id,
            label.label_id,
            label.output,
            extra={"event": "client.label_started", "label_id": label.label_id, "output": label.output, "wall_id": label.wall_id},
        )

    def _stop_label(self, output: str, *, retired: bool) -> None:
        running = self._labels.pop(output)
        if retired:
            running.retired.set()
        running.stop.set()
        self._stopping.add(running.task)
        running.task.add_done_callback(self._stopping.discard)
        log.info(
            "label %s on %s %s; stopping its renderer",
            running.assignment.label_id,
            output,
            "captions no wall now" if retired else "captions another wall now",
            extra={
                "event": "client.label_stopped",
                "label_id": running.assignment.label_id,
                "output": output,
                "wall_id": running.assignment.wall_id,
            },
        )

    def _label_unplaceable(self, label: LabelAssignment, why: str) -> None:
        key = (label.label_id, label.output)
        if key in self._reported_unplaceable_labels:
            return
        self._reported_unplaceable_labels.add(key)
        log.error(
            "label %s for wall %s is assigned to label output %s, and it is not started: %s",
            label.label_id,
            label.wall_id,
            label.output,
            why,
            extra={"event": "client.label_unplaceable", "label_id": label.label_id, "output": label.output},
        )

    # -- starting and stopping --------------------------------------------------------

    def _start(self, wall: WallSettings, assignment: Assignment, output: OutputReport) -> None:
        stop = asyncio.Event()
        # **After every worker still stopping has finished.** A wall moved to
        # another output would otherwise run two workers on its one directory for
        # a moment, and an output handed from one wall to another two workers on
        # one screen — on the Frame, two art channels at a set that refuses a
        # second while the first is open.
        stopping = tuple(self._stopping)
        task = asyncio.create_task(
            self._keep_running(
                lambda: self._worker(wall, output, stop),
                stop,
                what=f"the worker for wall {wall.wall_id} on {assignment.output}",
                event="client.worker",
                extra={"wall_id": wall.wall_id, "output": assignment.output},
                after=stopping,
            ),
            name=f"wall:{wall.wall_id}",
        )
        self._running[wall.wall_id] = _Running(assignment=assignment, stop=stop, task=task)
        self._reported_unplaceable = {key for key in self._reported_unplaceable if key[0] != wall.wall_id}
        log.info(
            "showing wall %s (%s) on %s",
            assignment.name,
            wall.wall_id,
            assignment.output,
            extra={"event": "client.wall_started", "wall_id": wall.wall_id, "output": assignment.output},
        )

    def _stop(self, wall_id: str, *, moved_to: str | None) -> None:
        """Ask a worker to stop. Its task finishes on its own; `stop_all` waits for every one."""
        running = self._running.pop(wall_id)
        running.stop.set()
        self._stopping.add(running.task)
        running.task.add_done_callback(self._stopping.discard)
        log.info(
            "wall %s is %s; stopping its worker on %s",
            wall_id,
            f"moved to {moved_to}" if moved_to is not None else "no longer assigned to this client",
            running.assignment.output,
            extra={"event": "client.wall_stopped", "wall_id": wall_id, "output": running.assignment.output},
        )

    def _unplaceable(self, assignment: Assignment, why: str) -> None:
        key = (assignment.wall_id, assignment.output)
        if key in self._reported_unplaceable:
            return
        self._reported_unplaceable.add(key)
        log.error(
            "wall %s (%s) is assigned to output %s, and it is not started: %s",
            assignment.name,
            assignment.wall_id,
            assignment.output,
            why,
            extra={"event": "client.wall_unplaceable", "wall_id": assignment.wall_id, "output": assignment.output},
        )

    async def stop_all(self) -> None:
        """Stop every worker and renderer, and wait for each to finish closing what it holds.

        Renderers are stopped, never retired: a client going down leaves each
        panel as it was, which on e-paper is the caption it last drew.
        """
        for wall_id in list(self._running):
            running = self._running.pop(wall_id)
            running.stop.set()
            self._stopping.add(running.task)
        for output in list(self._labels):
            label = self._labels.pop(output)
            label.stop.set()
            self._stopping.add(label.task)
        if self._stopping:
            await asyncio.gather(*self._stopping, return_exceptions=True)
            self._stopping.clear()

    async def _keep_running(
        self,
        run: Callable[[], Awaitable[None]],
        stop: asyncio.Event,
        *,
        what: str,
        event: str,
        extra: dict[str, str],
        after: tuple[asyncio.Task[None], ...] = (),
    ) -> None:
        """Run one worker or renderer until stopped, starting it again whenever it fails.

        `what` names it in the journal and `event` is the prefix of its two
        events, `_crashed` and `_ended`.
        """
        if after:
            await asyncio.gather(*after, return_exceptions=True)
        wait = Backoff(minimum=self._restart_min, maximum=self._restart_max, monotonic=self._monotonic)
        while not stop.is_set():
            started = self._monotonic()
            try:
                await run()
            except Exception:  # prawduct:allow prawduct/broad-except -- logged and restarted
                log.exception(
                    "%s stopped on an error; starting it again",
                    what,
                    extra={"event": f"{event}_crashed", **extra},
                )
            else:
                if stop.is_set():
                    return
                log.error(
                    "%s ended without being asked to; starting it again",
                    what,
                    extra={"event": f"{event}_ended", **extra},
                )
            if self._monotonic() - started > self._restart_max:
                # A worker that ran for longer than the longest wait has earned a
                # fresh ladder: this failure is a new one, not the next in a loop.
                wait.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=wait.hold())

    # -- the outputs ----------------------------------------------------------------

    async def _report_outputs(self) -> None:
        """POST the client heartbeat when the outputs changed, or once per heartbeat interval.

        **Changed is news and is sent at once**: a screen plugged in is what a
        curator is waiting to see on the Clients page before choosing it. An
        unchanged report is sent once a minute, so the server can say how long
        ago this client was heard from.
        """
        if self._frame_identity is not None:
            await self._frame_identity.refresh()
        outputs = (self._outputs(), self._label_outputs())
        elapsed = self._monotonic()
        due = self._reported_at is None or elapsed - self._reported_at >= heartbeat_module.INTERVAL_SECONDS
        if outputs == self._reported_outputs and not due:
            return
        if await self._link.report(client_heartbeat(outputs[0], label_outputs=outputs[1], reported_at=self._now())):
            self._reported_outputs = outputs
            self._reported_at = elapsed
