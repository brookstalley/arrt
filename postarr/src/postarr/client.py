"""The Player as a client: one process, one worker per wall the server assigns it.

`clients.md` § The Player. A client is configured with the server, its token and
its cache, and nothing about walls. It asks the server which walls it drives
(`GET /client`, about every 30 seconds), starts a worker for each on the output
the curator chose, stops the worker for a wall taken away, and tells the server
which outputs it has (`POST /client/heartbeat`) so a curator can choose one by
name. `player-contract.md` § Transport is the specification of both routes.

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
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Protocol

from postarr import heartbeat as heartbeat_module
from postarr.config import FRAME_OUTPUT, ClientSettings, WallIdUnusable, WallSettings
from postarr.episodes import Backoff

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


@dataclass(frozen=True)
class ClientDocument:
    """What `GET /client` answered: this client, and its walls."""

    client_id: str
    name: str
    walls: tuple[Assignment, ...]


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
        assignments.append(Assignment(wall_id=wall["wall_id"], name=wall["name"], output=wall["output"]))
    return ClientDocument(client_id=client_id, name=name, walls=tuple(assignments))


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

    def document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "connected": self.connected,
            "screen": list(self.screen) if self.screen is not None else None,
        }


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


def client_outputs(settings: ClientSettings, *, drm_root: Path = DRM_ROOT) -> list[OutputReport]:
    """Every output this client can drive: the Frame when it has one, and its HDMI connectors.

    **The Frame is reported connected because it is configured**, with no screen
    size. It is a television on the network rather than a cable this host can
    sense, and whether it answers is a fact about the wall shown on it, which
    that wall's own heartbeat reports (`television_reachable`). Its size is the
    server's to know: the render arrives composed for it.
    """
    outputs = [OutputReport(name=FRAME_OUTPUT, kind=FRAME_KIND, connected=True, screen=None)] if settings.frame else []
    return outputs + hdmi_outputs(drm_root)


def client_heartbeat(outputs: list[OutputReport], *, reported_at: datetime) -> dict[str, Any]:
    """The client heartbeat (`contract/schemas/client-heartbeat.v1.schema.json`)."""
    return {
        heartbeat_module.REPORTED_AT_KEY: reported_at.isoformat(),
        "outputs": [output.document() for output in outputs],
    }


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


@dataclass
class _Running:
    assignment: Assignment
    stop: asyncio.Event
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
        restart_min_seconds: float = RESTART_MIN_SECONDS,
        restart_max_seconds: float = RESTART_MAX_SECONDS,
    ) -> None:
        self._settings = settings
        self._link = link
        self._worker = worker
        self._outputs = outputs
        self._now = now
        self._monotonic = monotonic
        self._restart_min = restart_min_seconds
        self._restart_max = restart_max_seconds
        self._running: dict[str, _Running] = {}
        #: Workers asked to stop and not yet finished, so shutdown can wait for
        #: each to close what it holds — on the Frame, the art channel.
        self._stopping: set[asyncio.Task[None]] = set()
        #: Assignments already reported as impossible, so each is said once. Keyed
        #: on the wall *and* the output: a wall moved to another output it also
        #: lacks is news.
        self._reported_unplaceable: set[tuple[str, str]] = set()
        self._reported_outputs: list[OutputReport] | None = None
        self._reported_at: float | None = None

    @property
    def running(self) -> dict[str, str]:
        """Each wall with a worker, and the output it is on."""
        return {wall_id: running.assignment.output for wall_id, running in self._running.items()}

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
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self._settings.client_poll_seconds)
                except TimeoutError:
                    pass
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

    def _start(self, wall: WallSettings, assignment: Assignment, output: OutputReport) -> None:
        stop = asyncio.Event()
        # **After every worker still stopping has finished.** A wall moved to
        # another output would otherwise run two workers on its one directory for
        # a moment, and an output handed from one wall to another two workers on
        # one screen — on the Frame, two art channels at a set that refuses a
        # second while the first is open.
        stopping = tuple(self._stopping)
        task = asyncio.create_task(
            self._keep_running(wall, assignment, output, stop, after=stopping), name=f"wall:{wall.wall_id}"
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
        """Stop every worker and wait for each to finish closing what it holds."""
        for wall_id in list(self._running):
            running = self._running.pop(wall_id)
            running.stop.set()
            self._stopping.add(running.task)
        if self._stopping:
            await asyncio.gather(*self._stopping, return_exceptions=True)
            self._stopping.clear()

    async def _keep_running(
        self,
        wall: WallSettings,
        assignment: Assignment,
        output: OutputReport,
        stop: asyncio.Event,
        *,
        after: tuple[asyncio.Task[None], ...] = (),
    ) -> None:
        """Run one wall's worker until stopped, starting it again whenever it fails."""
        if after:
            await asyncio.gather(*after, return_exceptions=True)
        wait = Backoff(minimum=self._restart_min, maximum=self._restart_max, monotonic=self._monotonic)
        while not stop.is_set():
            started = self._monotonic()
            try:
                await self._worker(wall, output, stop)
            except Exception:  # prawduct:allow prawduct/broad-except -- logged and restarted
                log.exception(
                    "the worker for wall %s on %s stopped on an error; starting it again",
                    wall.wall_id,
                    assignment.output,
                    extra={"event": "client.worker_crashed", "wall_id": wall.wall_id, "output": assignment.output},
                )
            else:
                if stop.is_set():
                    return
                log.error(
                    "the worker for wall %s on %s ended without being asked to; starting it again",
                    wall.wall_id,
                    assignment.output,
                    extra={"event": "client.worker_ended", "wall_id": wall.wall_id, "output": assignment.output},
                )
            if self._monotonic() - started > self._restart_max:
                # A worker that ran for longer than the longest wait has earned a
                # fresh ladder: this failure is a new one, not the next in a loop.
                wait.clear()
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait.hold())
            except TimeoutError:
                pass

    # -- the outputs ----------------------------------------------------------------

    async def _report_outputs(self) -> None:
        """POST the client heartbeat when the outputs changed, or once per heartbeat interval.

        **Changed is news and is sent at once**: a screen plugged in is what a
        curator is waiting to see on the Clients page before choosing it. An
        unchanged report is sent once a minute, so the server can say how long
        ago this client was heard from.
        """
        outputs = self._outputs()
        elapsed = self._monotonic()
        due = self._reported_at is None or elapsed - self._reported_at >= heartbeat_module.INTERVAL_SECONDS
        if outputs == self._reported_outputs and not due:
            return
        if await self._link.report(client_heartbeat(outputs, reported_at=self._now())):
            self._reported_outputs = outputs
            self._reported_at = elapsed
