"""Clients, their displays and label outputs, and which wall each shows or captions.

`clients.md` and `feeds-and-players.md` § Displays are configured, never
discovered, are the requirements. A client is a name and one credential (issued
by `access.py`). It reports its outputs; each display output becomes a
**display**, a record keyed by the identity the client read from the device, and
each label output a **label output**. A wall names a display, and any number of
label outputs name the wall. Assigning is a curatorial act, like hanging a
theme, and so lives here in Programming beside the walls it changes.

**Every rule about a valid assignment is here**, and the store's unique indexes
are only the weaker statements of three of them: one display per output of a
client, one wall per display, one label output per name on a client. HTTP
(Settings › Players, Walls) and MCP (`art_display`) both bind it.

**Who shows a wall is read in one place, `Placements`**, because three readers
ask it and must agree: `GET /client` (which walls a client starts), admission to
the per-wall routes, and every wall's display state, on Walls and on each label.
A wall is shown by its display's client, unless two clients report that
display's identity now, which is a configuration fault the curator sees: the
wall is then shown by neither, and nothing on the clients arbitrates.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import json
import logging
import threading
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from arrt.library.facade import LibraryFacade
from arrt.persistence.records import Client, Display, LabelOutput, Wall
from arrt.programming import client_heartbeat
from arrt.programming.client_heartbeat import ClientHeartbeatReading
from arrt.programming.display_state import DisplayState, ScreenState, display_state_of
from arrt.programming.lookups import Clock, IdSource, Lookups, machine_now, new_id
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.builder import write_atomically
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS, HeartbeatReading, heartbeat_path_in
from arrt.programming.player_state import PlayerReading, PlayerState, player_reading
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import NotFound, ServiceError
from arrt.services.fields import require_text
from arrt.services.store import store_write

if TYPE_CHECKING:
    # Only for the annotation: `display.py` reads `Placements` from here, so a
    # runtime import back would be a cycle.
    from arrt.programming.display import DisplaySettings

log = logging.getLogger(__name__)

#: The label document's schema major and minor (`contract/schemas/label.v1.schema.json`).
LABEL_SCHEMA: Final[Mapping[str, int]] = {"major": 1, "minor": 0}


def place_identity(client_id: str, output: str) -> str:
    """The identity of a display no client can name: the client it hangs on, and the output's name.

    An HDMI connector is one, and so is any display a curator placed a wall on
    before its client reported it. Such a display cannot move between clients,
    which is true of the hardware; a Frame's display starts this way when the set
    could not be asked, and is re-keyed to the set's own id when it can.
    """
    return f"{client_id}/{output}"


# -- reports refused ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefusedReport:
    """A Player's last report this server refused, remembered until it sends one it accepts."""

    #: Why it was refused, in `client_heartbeat.problem_with`'s words: what the
    #: Player's reading carries as its problem.
    problem: str
    #: When the last refused report arrived, by this server's clock.
    at: datetime
    #: When the first of the refusals since the Player last had a report
    #: accepted arrived (or since this server started), by this server's
    #: clock: the instant the Player's reading is `report_unreadable` since.
    since: datetime


class RefusedReports:
    """Each Player's last refused report, in memory only, cleared by the next report accepted.

    **In memory, never written**: a refused report is one the server writes
    nothing of (`player-contract.md` § Transport, the client heartbeat's `400`
    rows). What it keeps is what the household is told meanwhile: a Player whose
    every report is refused is a Player in trouble, not one that has not yet
    reported.

    **A restart forgets it.** The Player then reads as its file says: one whose
    report was accepted before reads `reporting`, then `not_heard_from` (a
    trouble) once that report is stale; one never accepted reads
    `awaiting_report`, a setup step that is counted nowhere. Either lasts until
    the server refuses its next report, which a Player at contract 1.3.0 sends
    only when its report changes or it restarts, so possibly never. Accepted
    for what a durable record would cost: the contract's sentence that the
    server writes nothing of a refused report, and, since a restart is most
    often an upgrade, a trouble kept about a report the new server might accept.
    """

    def __init__(self) -> None:
        # Heartbeats are recorded on worker threads while readers survey.
        self._lock = threading.Lock()
        self._by_client: dict[str, RefusedReport] = {}

    def note(self, client_id: str, problem: str, at: datetime) -> bool:
        """Remember a refusal; True when it starts a run, False when it repeats the last one's problem."""
        with self._lock:
            previous = self._by_client.get(client_id)
            since = at if previous is None else previous.since
            self._by_client[client_id] = RefusedReport(problem=problem, at=at, since=since)
        return previous is None or previous.problem != problem

    def clear(self, client_id: str) -> None:
        """Forget a Player's refusal: it sent a report that was accepted, or it was removed."""
        with self._lock:
            self._by_client.pop(client_id, None)

    def now(self) -> Mapping[str, RefusedReport]:
        """Every refusal remembered, by client id, as one copy taken at once."""
        with self._lock:
            return dict(self._by_client)


#: One memory per store. Programming builds more than one `Placements` over the
#: one store (`Walls` holds its own, and the health reading reads Players through
#: it), and every one of them must read the refusals `ClientService` notes; the
#: store is what they all share. Weak, so a store dropped takes its refusals
#: with it, as a restart does.
_REFUSALS: weakref.WeakKeyDictionary[object, RefusedReports] = weakref.WeakKeyDictionary()
_REFUSALS_LOCK: Final[threading.Lock] = threading.Lock()


def refused_reports_of(store: ProgrammingStore) -> RefusedReports:
    """The refusals remembered for the Players of this store."""
    with _REFUSALS_LOCK:
        found = _REFUSALS.get(store)
        if found is None:
            found = _REFUSALS[store] = RefusedReports()
        return found


def heard(reading: ClientHeartbeatReading, refused: RefusedReport | None) -> ClientHeartbeatReading:
    """The Player's report as the household is told of it: its file, unless its last report was refused.

    A refused report replaces the file's word: the Player is talking, and what
    it says cannot be read, which `player_state` calls `report_unreadable` and
    every surface states with `problem`. The file's outputs say nothing about
    now once a later report was refused, so none are carried; its settings page
    address is, because that page is where the Player's report is put right.
    """
    if refused is None:
        return reading
    return ClientHeartbeatReading(
        path=reading.path,
        reported_at=None,
        age_seconds=None,
        outputs=(),
        problem=refused.problem,
        absent=False,
        settings_url=reading.settings_url,
    )


# -- what is read together ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DisplayFault:
    """One display identity two or more clients report now: a configuration fault, not a contest."""

    identity: str
    #: Every client reporting it, in name order. Two or more.
    clients: Sequence[Client]
    #: The server's record under that identity, when there is one.
    display: Display | None
    #: The wall on that display, which neither client shows until one stops.
    wall: Wall | None

    def describe(self) -> str:
        """The fault in one sentence, the same words on every surface that shows it."""
        names = " and ".join(client.name for client in self.clients)
        shown = f"so neither shows {self.wall.name}" if self.wall is not None else "so neither may show a wall on it"
        return (
            f"{names} both report the display {self.identity}, {shown} until one of them stops. "
            "A display is configured on one Player; remove it from the others' settings."
        )


@dataclass(frozen=True, slots=True)
class WallPlacement:
    """Where one wall is: its display, that display's client, and the labels captioning it."""

    wall: Wall
    #: None while the wall has no display.
    display: Display | None
    #: The display's client, None while it has none (or the wall has no display).
    client: Client | None
    #: Set when two clients report the display now.
    fault: DisplayFault | None
    #: Every label output captioning the wall, by name.
    labels: Sequence[LabelOutput]

    @property
    def shown_by(self) -> Client | None:
        """The client that shows the wall now: the display's client, unless its display is in fault."""
        return None if self.fault is not None else self.client

    @property
    def output(self) -> str | None:
        """The name of the output the wall is on, where a client has it. None exactly when `client` is."""
        return None if self.client is None or self.display is None else self.display.output


@dataclass(frozen=True, slots=True)
class ShownWall:
    """A wall a client shows, and the display it shows it on."""

    wall: Wall
    display: Display


@dataclass(frozen=True, slots=True)
class PlacementSurvey:
    """Every client, display, wall and label output, and what each client reports, read at one instant."""

    clients: Mapping[str, Client]
    displays: Mapping[str, Display]
    #: In the order walls are listed everywhere else.
    walls: Sequence[Wall]
    label_outputs: Sequence[LabelOutput]
    readings: Mapping[str, ClientHeartbeatReading]
    #: Keyed by identity; only identities two or more clients report now.
    faults: Mapping[str, DisplayFault]
    #: Each Player's last refused report, by client id, read after `readings`
    #: (`RefusedReports`). Read into the Player's own reading only (`view_of`):
    #: who shows a wall, and its faults, are the files' to say.
    refused: Mapping[str, RefusedReport] = field(default_factory=dict)

    def placement_of(self, wall: Wall) -> WallPlacement:
        display = None if wall.display_id is None else self.displays.get(wall.display_id)
        client = None if display is None or display.client_id is None else self.clients.get(display.client_id)
        return WallPlacement(
            wall=wall,
            display=display,
            client=client,
            fault=None if display is None else self.faults.get(display.identity),
            labels=[label for label in self.label_outputs if label.wall_id == wall.id],
        )

    def shows(self, wall: Wall) -> bool:
        """Whether a client shows this wall now: what turns a wall's report into a display state, or `unassigned`."""
        return self.placement_of(wall).shown_by is not None

    def wall_state(self, wall: Wall, reading: HeartbeatReading) -> DisplayState:
        """The wall's display state from its report as read, by this survey's placements."""
        return display_state_of(reading, shown=self.shows(wall))

    def shown_walls(self, client_id: str) -> Sequence[ShownWall]:
        """The walls this client shows now, in the order walls are listed. Its own question, every poll."""
        shown = []
        for wall in self.walls:
            placement = self.placement_of(wall)
            if placement.shown_by is not None and placement.shown_by.id == client_id and placement.display is not None:
                shown.append(ShownWall(wall=wall, display=placement.display))
        return shown

    def displays_of(self, client_id: str) -> Sequence[Display]:
        return [display for display in self.displays.values() if display.client_id == client_id]

    def label_outputs_of(self, client_id: str) -> Sequence[LabelOutput]:
        return [label for label in self.label_outputs if label.client_id == client_id]

    def faults_of(self, client_id: str) -> Sequence[DisplayFault]:
        """The faults this client is one side of."""
        return [fault for fault in self.faults.values() if any(client.id == client_id for client in fault.clients)]


@dataclass(frozen=True, slots=True)
class WallsReading:
    """Who shows each wall and what each wall reported, every file read once: what one answer about walls says.

    **One answer, one reading.** A walls answer says of each wall its display
    state, whom it waits for, who shows it, its display and labels, and whether
    its Player reads the feed. Each of those read from a reading of its own let
    one answer contradict itself: a Player assigned between two reads, or a
    report arriving, gave `display_state: unassigned` beside a `shown_by`
    naming a Player, or a feed notice from one report beside a state from the
    next. Built by `Placements.read_walls`; every such answer reads it alone.
    """

    survey: PlacementSurvey
    #: Each wall's report as read, by wall id: the walls this reading was asked
    #: for, each of them in `survey.walls`.
    reports: Mapping[str, HeartbeatReading]

    @property
    def walls(self) -> Sequence[Wall]:
        """The walls read, in the order walls are listed everywhere else."""
        return [wall for wall in self.survey.walls if wall.id in self.reports]

    def state_of(self, wall: Wall) -> DisplayState:
        """The wall's display state from this reading's report of it and its placements."""
        return self.survey.wall_state(wall, self.reports[wall.id])

    def players(self) -> Sequence[ClientView]:
        """Every Player with its state, from this reading's read of its report, in the order clients are listed."""
        return [view_of(client, self.survey, self.survey.readings[client.id]) for client in self.survey.clients.values()]


@dataclass(frozen=True, slots=True)
class WallState:
    """A wall's display state, with the heartbeat it was read from."""

    state: DisplayState
    reading: HeartbeatReading


class Placements:
    """Who shows each wall, read from the records and from what each client reports now.

    Stateless, so every surface that asks gets the answer the files and the store
    give at that instant. **A client's report counts toward a fault only while it
    is current** — readable and no older than `STALE_AFTER_SECONDS`, the age past
    which Walls calls a report stale — so a host switched off stops claiming its
    display, and a Frame moved from it to another host is not held in fault by a
    report nobody will ever replace.

    Every report it reads is aged by `now`, read once a reading, so the reports
    one answer carries are aged from one instant, and by the clock the client
    service stamps its records with.
    """

    def __init__(self, store: ProgrammingStore, art_root: Path, *, now: Clock = machine_now) -> None:
        self._store = store
        self._art_root = art_root
        self._now = now
        self._refused = refused_reports_of(store)

    def survey(self, at: datetime | None = None) -> PlacementSurvey:
        """Every Player and its report, read now, or at `at` when the caller has read the clock for its whole answer."""
        at = self._now() if at is None else at
        with self._store.reading():
            clients = {client.id: client for client in self._store.list_clients()}
            displays = {display.id: display for display in self._store.list_displays()}
            walls = list(self._store.list_walls())
            label_outputs = list(self._store.list_label_outputs())
        readings = {
            client_id: client_heartbeat.read(client_heartbeat.client_heartbeat_path_in(self._art_root, client_id), now=at)
            for client_id in clients
        }
        # After the files: a report accepted meanwhile is written before its
        # refusal is cleared, so a refusal read here is never older than the
        # file read beside it.
        refused = {client_id: found for client_id, found in self._refused.now().items() if client_id in clients}
        return PlacementSurvey(
            clients=clients,
            displays=displays,
            walls=walls,
            label_outputs=label_outputs,
            readings=readings,
            faults=_faults(clients, displays, walls, readings),
            refused=refused,
        )

    def placement_of(self, wall: Wall) -> WallPlacement:
        return self.survey().placement_of(wall)

    def read_walls(self, wall_ids: frozenset[str] | None = None, at: datetime | None = None) -> WallsReading:
        """Every wall, or those named, with one survey and one read of each wall's report (`WallsReading`).

        **An answer about some walls reads their reports and every Player's, and
        no other wall's.** The survey reads every Player's because who shows a
        wall depends on them: a display two Players report now is in fault, and
        shown by neither, and no record says so but those reports. The Player
        that shows the wall is judged from the same read. A wall named that the
        survey does not hold is read as no wall: the caller has already looked
        it up, or answers for none. Every report is aged at `at`, the instant
        the caller read for its whole answer, or now.
        """
        at = self._now() if at is None else at
        survey = self.survey(at)
        walls = [wall for wall in survey.walls if wall_ids is None or wall.id in wall_ids]
        return WallsReading(
            survey=survey,
            reports={wall.id: heartbeat.read(heartbeat_path_in(self._art_root, wall.id), now=at) for wall in walls},
        )

    def captioned_wall(self, label_id: str) -> tuple[Wall, WallState] | None:
        """The wall a label output captions and that wall's display state, or None while it captions none.

        What a label's document says, and only that reads it. **One store
        scope for the label's row, the wall's, who shows the wall and the
        wall's report**, as `read_walls` takes the walls answers': a wall's row
        read apart from who shows it let a document judge the wall by a row a
        write had since replaced, and caption a wall as showing after it was
        taken off its screen and Walls said unassigned. The state is judged as
        `WallsReading.state_of` judges every wall's.
        """
        with self._store.reading():
            label = self._store.get_label_output(label_id)
            if label is None or label.wall_id is None:
                return None
            reading = self.read_walls(frozenset({label.wall_id}))
        if not reading.walls:
            return None
        [wall] = reading.walls
        return wall, WallState(state=reading.state_of(wall), reading=reading.reports[wall.id])


def is_current(reading: ClientHeartbeatReading) -> bool:
    """Whether a client's report says something about now: readable, and not stale."""
    return (
        not reading.absent
        and reading.problem is None
        and reading.age_seconds is not None
        and reading.age_seconds <= STALE_AFTER_SECONDS
    )


def _faults(
    clients: Mapping[str, Client],
    displays: Mapping[str, Display],
    walls: Sequence[Wall],
    readings: Mapping[str, ClientHeartbeatReading],
) -> dict[str, DisplayFault]:
    reporters: dict[str, list[Client]] = {}
    for client_id, reading in readings.items():
        if not is_current(reading):
            continue
        for identity in {output.identity for output in reading.outputs if output.identity is not None}:
            reporters.setdefault(identity, []).append(clients[client_id])
    faults = {}
    for identity, reporting in reporters.items():
        if len(reporting) < 2:  # noqa: PLR2004 -- two clients is what makes a fault
            continue
        display = next((display for display in displays.values() if display.identity == identity), None)
        wall = None if display is None else next((wall for wall in walls if wall.display_id == display.id), None)
        faults[identity] = DisplayFault(
            identity=identity,
            clients=sorted(reporting, key=lambda client: (client.name.casefold(), client.id)),
            display=display,
            wall=wall,
        )
    return faults


# -- what a service call answers -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClientView:
    """One client with what it shows, holds and last reported, read together."""

    client: Client
    #: The walls it shows now, in the order walls are listed.
    walls: Sequence[ShownWall]
    #: The displays whose client it is, a wall on one or not.
    displays: Sequence[Display]
    label_outputs: Sequence[LabelOutput]
    #: The display faults it is one side of.
    faults: Sequence[DisplayFault]
    heartbeat: ClientHeartbeatReading
    #: Its state and each of its outputs', from its token and `heartbeat`
    #: (`player_state.py`), so no surface derives them from the raw report.
    player: PlayerReading


@dataclass(frozen=True, slots=True)
class ClientsReading:
    """Every Player, or the one asked for, with who shows what, every report read once: what one Players answer says.

    **One answer, one reading**, as `WallsReading` is for walls. A Players
    answer says of each Player the walls it shows, its displays and the wall on
    each, its faults and its report. Each of those read from a reading of its
    own let one answer contradict itself: a Player assigned between two reads
    listed a wall it shows beside its display on no wall. Built by
    `ClientService.read_clients`; every such answer reads it alone.
    """

    #: Who shows what, and every Player's report as read.
    survey: PlacementSurvey
    #: Each Player read, from `survey` and its report there, in the order clients are listed.
    views: Sequence[ClientView]


@dataclass(frozen=True, slots=True)
class WallAssignment:
    """A wall just placed on a display, and anything the curator should know about it."""

    wall: Wall
    display: Display
    #: The display's client, None when no client reports the display now.
    client: Client | None
    #: Set when the output could not be confirmed against what the client last
    #: reported: it has not reported, or reported outputs without this name; or
    #: when the display has no client, or is in fault. The assignment is made
    #: either way, because a client that has not started yet has nothing to
    #: report, and the curator may be setting it up first.
    notice: str | None


@dataclass(frozen=True, slots=True)
class LabelAssignment:
    """A label output just set to caption a wall, and anything the curator should know about it."""

    label: LabelOutput
    wall: Wall
    client: Client
    #: Set when the label output could not be confirmed against the client's
    #: last report. The mapping is made either way, as for a wall.
    notice: str | None


class ClientService:
    """Record clients, keep their displays and label outputs, and place walls and labels on them."""

    def __init__(
        self,
        store: ProgrammingStore,
        settings: DisplaySettings,
        library: LibraryFacade,
        *,
        now: Clock = machine_now,
        mint_id: IdSource = new_id,
    ) -> None:
        self._store = store
        self._settings = settings
        self._library = library
        #: The clock a Player, a display or a refusal is recorded by (read once an act), and the source of their ids.
        self._now = now
        self._mint_id = mint_id
        self.placements = Placements(store, settings.art_root, now=now)
        self._refused = refused_reports_of(store)
        #: Identities whose fault has been said in the journal this episode, so
        #: a fault is said once rather than at every heartbeat that meets it.
        self._faults_said: set[str] = set()

    # -- reads ----------------------------------------------------------------

    def get_client(self, client_id: str) -> Client:
        client = self._store.get_client(client_id)
        if client is None:
            raise NotFound(f"No client with id {client_id!r} is recorded.")
        return client

    def list_clients(self) -> Sequence[ClientView]:
        """Every client, with what it shows, holds and last reported (`read_clients`)."""
        return self.read_clients().views

    def get_client_view(self, client_id: str) -> ClientView:
        """One client, with what it shows, holds and last reported (`read_clients`)."""
        [view] = self.read_clients(client_id).views
        return view

    def read_clients(self, client_id: str | None = None) -> ClientsReading:
        """Every client, or the one named, each view built from one survey of who shows what (`ClientsReading`).

        **One store scope for the rows and one read of each Player's report.**
        The scope excludes this process's writers for the whole read, so the
        clients listed, the walls each shows and the wall on each of its
        displays are one instant's; each report file is read once, inside it,
        and each Player's view is judged from that read. A named client the
        catalogue does not hold is refused, as `get_client` does.
        """
        with self._store.reading():
            if client_id is not None:
                self.get_client(client_id)
            survey = self.placements.survey()
        read = [client for client in survey.clients.values() if client_id is None or client.id == client_id]
        return ClientsReading(survey=survey, views=[view_of(client, survey, survey.readings[client.id]) for client in read])

    def walls_of(self, client_id: str) -> Sequence[Wall]:
        """The walls this client shows now, in the order walls are listed."""
        self.get_client(client_id)
        return [shown.wall for shown in self.placements.survey().shown_walls(client_id)]

    def placement_of(self, wall_id: str) -> WallPlacement:
        return self.placements.placement_of(self._require_wall(wall_id))

    def get_display(self, display_id: str) -> Display:
        display = self._store.get_display(display_id)
        if display is None:
            raise NotFound(f"No display with id {display_id!r} is recorded.")
        return display

    def client_document(self, client_id: str) -> bytes:
        """What `GET /client` answers: this client, its walls and its labels, as the bytes the ETag hashes.

        `contract/schemas/client.v1.schema.json` is the shape. Serialised here,
        once, so the ETag is a hash of exactly what a client was sent.
        """
        client = self.get_client(client_id)
        survey = self.placements.survey()
        walls = {wall.id for wall in survey.walls}
        document = {
            "client_id": client.id,
            "name": client.name,
            "walls": [
                {"wall_id": shown.wall.id, "name": shown.wall.name, "output": shown.display.output, "display": shown.display.id}
                for shown in survey.shown_walls(client.id)
            ],
            "labels": [
                {"label_id": label.id, "output": label.output, "wall_id": label.wall_id}
                for label in survey.label_outputs_of(client.id)
                if label.wall_id is not None and label.wall_id in walls
            ],
        }
        return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def label_document(self, label_id: str) -> bytes | None:
        """What `GET /labels/{label_id}` answers, as the bytes the ETag hashes; None while it captions no wall.

        `contract/schemas/label.v1.schema.json` is the shape. The state is the
        wall's, read with the label's row in one reading (`Placements.captioned_wall`). The
        label text is the work's, read through the Library facade: the work on
        screen with `showing_art`; with `silent` the work the last report showed;
        with `unreachable` the work the heartbeat last named; otherwise none, and
        none for a picture this wall did not put there. The renderer runs the
        label rule over it (`contract/vectors/label-rule.json`).
        """
        captioned = self.placements.captioned_wall(label_id)
        if captioned is None:
            return None
        wall, found = captioned
        shown = found.state
        work_id = _captioned_work(found)
        text = None if work_id is None else self._library.labels([work_id]).get(work_id)
        document = {
            "schema": dict(LABEL_SCHEMA),
            "wall_id": wall.id,
            "wall_name": wall.name,
            "display_state": {
                "state": str(shown.state),
                "work_id": shown.work_id,
                "since": None if shown.since is None else shown.since.isoformat(),
            },
            "label": None if text is None else dict(text),
        }
        return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def read_heartbeat(self, client_id: str, at: datetime | None = None) -> ClientHeartbeatReading:
        """A client's report, aged by this service's clock: read now, or at `at`, the instant the act already read."""
        return client_heartbeat.read(self._heartbeat_path(client_id), now=self._now() if at is None else at)

    # -- writes: clients ------------------------------------------------------

    def add_client(self, *, name: str) -> Client:
        """Record a client. It has no token until one is issued, and drives no wall."""
        name = require_text(name, field="name")
        # Stamped once the act holds the store, as a report's first display is.
        with self._store.transaction():
            client = Client(id=self._mint_id(), name=name, created_at=self._now())
            store_write(self._store.add_client, client)
        log.info("Recorded client %r.", client.name)
        return client

    def rename_client(self, client_id: str, *, name: str) -> Client:
        """Give a client a new name. Its token and its walls are unchanged."""
        chosen = require_text(name, field="name")
        # Read where it is written: the row carries the token's verifier, and a
        # client read before a token was issued would put the old one back.
        with self._store.transaction():
            renamed = replace(self.get_client(client_id), name=chosen)
            store_write(self._store.update_client, renamed)
        return renamed

    def remove_client(self, client_id: str) -> Sequence[Wall]:
        """Forget a client, its displays and its label outputs; its token stops working.

        The walls on its displays become unassigned, and its label outputs stop
        captioning. Returns the walls released, so a caller can say which rooms
        now have nothing showing them. They keep their themes: a wall nobody
        drives is an ordinary state, and hanging survives it. A Frame the client
        drove is recorded afresh when another client reports it.
        """
        client = self.get_client(client_id)
        released = []
        with self._store.transaction():
            displays = {display.id for display in self._store.list_displays() if display.client_id == client.id}
            for wall in self._store.list_walls():
                if wall.display_id in displays:
                    unassigned = replace(wall, display_id=None)
                    store_write(self._store.update_wall, unassigned)
                    released.append(unassigned)
            for display_id in displays:
                store_write(self._store.remove_display, display_id)
            for label in self._store.list_label_outputs():
                if label.client_id == client.id:
                    store_write(self._store.remove_label_output, label.id)
            store_write(self._store.remove_client, client.id)
        # After the commit: the report of a client the server no longer knows
        # would otherwise sit under the art root with nothing ever reading it.
        self._heartbeat_path(client.id).unlink(missing_ok=True)
        self._refused.clear(client.id)
        log.info("Removed client %r; %d wall(s) it drove are now unassigned.", client.name, len(released))
        return released

    # -- writes: walls on displays --------------------------------------------

    def assign_wall(self, wall_id: str, *, client_id: str, output: str) -> WallAssignment:
        """Show this wall on the display on one of this client's outputs, by the output's name.

        The display there is the one the client reported on that output; where
        it has reported none, one is recorded, keyed by the client and the output
        (`place_identity`), so a curator can set a client up before it first
        runs. The answer says when the output is not among those the client last
        reported. Refused when that display already shows another wall, because
        one screen shows one picture.
        """
        # Read where it is written, as every whole-row write of a wall is: a
        # setting changed meanwhile would otherwise be put back by this one.
        with self._store.transaction():
            # The act's one instant: a display it records and the reports it reads.
            now = self._now()
            wall = self._require_wall(wall_id)
            client = self.get_client(client_id)
            output = self._require_output(client, wall, output, at=now)
            display = self._display_on(client.id, output) or self._record_place(client, output, seen_at=now)
            placed = self._place(wall, display, client)
        log.info("Wall %r is now shown by client %r on output %r.", wall.name, client.name, output)
        return WallAssignment(wall=placed, display=display, client=client, notice=self._notice(display, client, at=now))

    def assign_display(self, wall_id: str, *, display_id: str) -> WallAssignment:
        """Show this wall on a display, by the display's id. Refused when it already shows another wall."""
        # Read where it is written, for the reason `assign_wall` gives.
        with self._store.transaction():
            now = self._now()
            wall = self._require_wall(wall_id)
            display = self.get_display(display_id)
            client = None if display.client_id is None else self._store.get_client(display.client_id)
            placed = self._place(wall, display, client)
        log.info("Wall %r is now on display %r.", wall.name, display.identity)
        return WallAssignment(wall=placed, display=display, client=client, notice=self._notice(display, client, at=now))

    def unassign_wall(self, wall_id: str) -> Wall:
        """Take a wall off its display. Unassigning an unassigned wall is not an error."""
        with self._store.transaction():
            wall = self._require_wall(wall_id)
            unassigned = replace(wall, display_id=None)
            if wall.display_id is not None:
                store_write(self._store.update_wall, unassigned)
        return unassigned

    # -- writes: labels -------------------------------------------------------

    def add_label(self, wall_id: str, *, client_id: str, output: str) -> LabelAssignment:
        """Caption this wall with one of a client's label outputs, by the label output's name.

        A wall may have any number of labels, on any clients. A label output
        captions at most one wall, so one that captions another is refused
        rather than moved: the curator takes it off that wall first, as for a
        display. Recorded if the client has not reported it yet, and the answer
        says so.
        """
        wall = self._require_wall(wall_id)
        client = self.get_client(client_id)
        output = require_text(output, field="output")
        with self._store.transaction():
            label = self._label_output_on(client.id, output)
            if label is None:
                label = LabelOutput(id=self._mint_id(), client_id=client.id, output=output)
                store_write(self._store.add_label_output, label)
            if label.wall_id not in (None, wall.id):
                other = self._store.get_wall(label.wall_id) if label.wall_id is not None else None
                other_name = other.name if other is not None else "another wall"
                raise ServiceError(
                    f"{client.name}'s label output {output!r} already captions {other_name}. "
                    f"Take it off {other_name} first, or choose another label output."
                )
            mapped = replace(label, wall_id=wall.id)
            store_write(self._store.update_label_output, mapped)
        log.info("Wall %r is now captioned by client %r's label output %r.", wall.name, client.name, output)
        return LabelAssignment(label=mapped, wall=wall, client=client, notice=self._label_notice(client, output))

    def remove_label(self, wall_id: str, *, label_id: str) -> LabelOutput:
        """Stop a label output captioning this wall. Removing one that captions no wall is not an error.

        Refused for a label output that captions a different wall, so a stale
        screen cannot take a label off a wall it was not showing.
        """
        with self._store.transaction():
            wall = self._require_wall(wall_id)
            label = self._store.get_label_output(label_id)
            if label is None:
                raise NotFound(f"No label output with id {label_id!r} is recorded.")
            if label.wall_id not in (None, wall.id):
                raise ServiceError(f"The label output {label.output!r} does not caption {wall.name}, so it was left as it is.")
            released = replace(label, wall_id=None)
            if label.wall_id is not None:
                store_write(self._store.update_label_output, released)
        return released

    # -- what a client writes -------------------------------------------------

    def record_heartbeat(self, client_id: str, document: object) -> None:
        """Keep what a client said about its outputs, and bring its displays and label outputs up to it.

        Refused, and nothing written, if it is not a document this server can
        read — so the listing never shows a report it would call unreadable —
        and the refusal remembered (`refused`). The file is what Settings ›
        Players reads; the records are what walls and labels are placed on
        (`_reconcile_display` says how each output is matched to one). A report
        accepted clears a refusal, after its file is written
        (`Placements.survey` says why in that order).
        """
        client = self.get_client(client_id)
        problem = client_heartbeat.problem_with(document)
        if problem is not None:
            self.refused(client.id, problem)
            raise ServiceError(f"That is not a client heartbeat this server can read: {problem}")
        # A dict by now: `problem_with` refuses anything else.
        report = cast("dict[str, Any]", document)
        write_atomically(self._heartbeat_path(client_id), report)
        self._refused.clear(client.id)
        with self._store.transaction():
            # Read once the act holds the store, so a report that waited for
            # another act is stamped after what that act wrote, never before.
            seen_at = self._now()
            for output in report["outputs"]:
                self._reconcile_display(client, output["name"], output["kind"], output.get("identity"), seen_at)
            for label in report.get("label_outputs", []):
                if self._label_output_on(client.id, label["name"]) is None:
                    store_write(
                        self._store.add_label_output,
                        LabelOutput(id=self._mint_id(), client_id=client.id, output=label["name"]),
                    )

    def refused(self, client_id: str, problem: str) -> None:
        """Remember that this Player's report was refused, and say so in the journal once per run of one problem.

        The Player then reads `report_unreadable`, with `problem`, until a report
        is accepted (`RefusedReports`). A Player that sends the same refused
        report every cycle writes one line, not one a cycle; a different problem
        starts a new run and writes again.
        """
        if self._refused.note(client_id, problem, self._now()):
            log.warning(
                "A report from client %s was refused; it reads as unreadable until one is accepted: %s",
                client_id,
                problem,
                extra={"event": "client.report_refused", "client_id": client_id, "problem": problem},
            )

    # -- helpers --------------------------------------------------------------

    def _reconcile_display(self, client: Client, output: str, kind: str, identity: str | None, seen_at: datetime) -> None:
        """Make the display this client reports on `output` the one recorded there.

        - **No identity** (an HDMI connector, or a Frame that could not be asked
          this time): whatever display is recorded on that output is it; if none
          is, one is recorded keyed by place (`place_identity`).
        - **An identity the server has not seen**: a display recorded by place on
          that output is that device, now named, and is re-keyed to the
          identity with its walls. A display of another identity there is a
          device no longer on that output, and is left with no client.
        - **An identity recorded elsewhere** (the Frame moved to this client, or
          to another of its outputs): it moves here with its walls, unless the
          client that has it still reports it, which is a fault left for the
          curator. A display recorded by place on this output is merged into it
          (`_merge_place`); one of another identity is left with no client.
        """
        here = self._display_on(client.id, output)
        if identity is None:
            if here is None:
                self._record_place(client, output, seen_at=seen_at, kind=kind)
            elif here.kind != kind:
                store_write(self._store.update_display, replace(here, kind=kind))
            return
        known = next((display for display in self._store.list_displays() if display.identity == identity), None)
        if known is None:
            self._first_report(client, output, kind, identity, here, seen_at)
            return
        if known.client_id == client.id and known.output == output:
            self._faults_said.discard(identity)
            if known.kind != kind:
                store_write(self._store.update_display, replace(known, kind=kind))
            return
        if known.client_id not in (None, client.id) and self._still_reports(known.client_id, identity, at=seen_at):
            self._say_fault(client, known)
            return
        self._faults_said.discard(identity)
        if here is not None and here.id != known.id:
            if here.identity == place_identity(client.id, output):
                self._merge_place(here, into=known)
            else:
                self._release(here)
        store_write(self._store.update_display, replace(known, client_id=client.id, output=output, kind=kind))
        self._say_moved(known, client, output)

    def _say_moved(self, display: Display, client: Client, output: str) -> None:
        """Say that a display is now on this client's output: at WARNING, naming both, when another client had it.

        The move is automatic (`clients.md`: a Frame moved to another Pi), and it
        is also what any Player's token can do by reporting a display another
        Player has stopped reporting, so a move nobody made is one
        an operator can find in the journal.
        """
        holder = None if display.client_id in (None, client.id) else self._store.get_client(display.client_id)
        if holder is None:
            log.info("The display %s is now on client %r's output %r, with its walls.", display.identity, client.name, output)
            return
        log.warning(
            "The display %s moved from client %r to client %r's output %r, with its walls; "
            "%r stopped reporting it, and is refused those walls from now on.",
            display.identity,
            holder.name,
            client.name,
            output,
            holder.name,
            extra={
                "event": "client.display_moved",
                "display": display.identity,
                "from_client": holder.name,
                "to_client": client.name,
                "output": output,
            },
        )

    def _first_report(
        self, client: Client, output: str, kind: str, identity: str, here: Display | None, seen_at: datetime
    ) -> None:
        """An identity the server has not seen, reported on `output`: name the display there, or record it."""
        if here is not None and here.identity == place_identity(client.id, output):
            store_write(self._store.update_display, replace(here, identity=identity, kind=kind))
            log.info("Client %r's output %r is the display %s; its walls stay on it.", client.name, output, identity)
            return
        if here is not None:
            self._release(here)
        store_write(
            self._store.add_display,
            Display(
                id=self._mint_id(),
                identity=identity,
                client_id=client.id,
                output=output,
                kind=kind,
                first_seen=seen_at,
            ),
        )

    def _merge_place(self, place: Display, *, into: Display) -> None:
        """Fold a display recorded by place into the identified display reported on the same output.

        They are one screen, so one record remains. Its wall goes with it where
        the identified display has none; where both have one, the identified
        display keeps its own and the place's is unassigned, since one screen
        shows one wall.
        """
        walls = self._store.list_walls()
        placed = next((wall for wall in walls if wall.display_id == place.id), None)
        kept = next((wall for wall in walls if wall.display_id == into.id), None)
        if placed is not None:
            if kept is None:
                store_write(self._store.update_wall, replace(placed, display_id=into.id))
            else:
                store_write(self._store.update_wall, replace(placed, display_id=None))
                log.warning(
                    "Wall %r was on %s's output %r, where the display %s now is, which already shows %r. "
                    "%r is now unassigned.",
                    placed.name,
                    place.client_id,
                    place.output,
                    into.identity,
                    kept.name,
                    placed.name,
                )
        store_write(self._store.remove_display, place.id)

    def _release(self, display: Display) -> None:
        """Leave a display that is no longer on its output with no client. Its wall stays, shown by nobody."""
        store_write(self._store.update_display, replace(display, client_id=None))
        log.info("The display %s is no longer on output %r; no client shows its wall.", display.identity, display.output)

    def _still_reports(self, client_id: str, identity: str, *, at: datetime) -> bool:
        reading = self.read_heartbeat(client_id, at)
        return is_current(reading) and any(output.identity == identity for output in reading.outputs)

    def _say_fault(self, client: Client, display: Display) -> None:
        if display.identity in self._faults_said:
            return
        self._faults_said.add(display.identity)
        holder = self._store.get_client(display.client_id) if display.client_id is not None else None
        log.warning(
            "Client %r reports the display %s, which client %r reports too. Neither shows its wall until one stops; "
            "a display is configured on one client.",
            client.name,
            display.identity,
            holder.name if holder is not None else "another client",
        )

    def _record_place(self, client: Client, output: str, *, seen_at: datetime, kind: str | None = None) -> Display:
        """The display on a client's output that no device has named, recorded by place.

        One left with no client under that identity is taken back rather than
        recorded twice, since the identity is unique.
        """
        identity = place_identity(client.id, output)
        if kind is None:
            reported = {entry.name: entry for entry in self.read_heartbeat(client.id, seen_at).outputs}.get(output)
            kind = None if reported is None else reported.kind
        orphan = next((display for display in self._store.list_displays() if display.identity == identity), None)
        if orphan is not None:
            restored = replace(orphan, client_id=client.id, output=output, kind=kind or orphan.kind)
            store_write(self._store.update_display, restored)
            return restored
        display = Display(
            id=self._mint_id(),
            identity=identity,
            client_id=client.id,
            output=output,
            kind=kind,
            first_seen=seen_at,
        )
        store_write(self._store.add_display, display)
        return display

    def _place(self, wall: Wall, display: Display, client: Client | None) -> Wall:
        for other in self._store.list_walls():
            if other.id != wall.id and other.display_id == display.id:
                where = (
                    f"{client.name}'s output {display.output!r}"
                    if client is not None
                    else f"The display on output {display.output!r}"
                )
                raise ServiceError(f"{where} already shows {other.name}. Unassign {other.name} first, or choose another output.")
        placed = replace(wall, display_id=display.id)
        store_write(self._store.update_wall, placed)
        return placed

    def _notice(self, display: Display, client: Client | None, *, at: datetime) -> str | None:
        if client is None:
            return (
                f"No Player reports the display {display.identity} now, so nothing shows this wall until one does. "
                "The assignment is kept either way."
            )
        fault = self.placements.survey(at).faults.get(display.identity)
        if fault is not None:
            return fault.describe()
        return self._unconfirmed(client, display.output, at=at)

    def _unconfirmed(self, client: Client, output: str, *, at: datetime) -> str | None:
        names = self.read_heartbeat(client.id, at).output_names()
        if names is None:
            return (
                f"{client.name} has not reported its outputs yet, so whether it has one called {output!r} "
                "cannot be checked. The assignment is kept either way."
            )
        if output not in names:
            reported = ", ".join(repr(name) for name in sorted(names)) or "none"
            return (
                f"{client.name} last reported these outputs: {reported}. {output!r} is not among them, "
                "so the Player cannot show this wall until it has an output by that name."
            )
        return None

    def _label_notice(self, client: Client, output: str) -> str | None:
        names = self.read_heartbeat(client.id).label_output_names()
        if names is None:
            return (
                f"{client.name} has not reported its outputs yet, so whether it has a label output called {output!r} "
                "cannot be checked. The label is kept either way."
            )
        if output not in names:
            reported = ", ".join(repr(name) for name in sorted(names)) or "none"
            return (
                f"{client.name} last reported these label outputs: {reported}. {output!r} is not among them, "
                "so nothing captions this wall there until the Player has a label output by that name."
            )
        return None

    def _display_on(self, client_id: str, output: str) -> Display | None:
        return next(
            (display for display in self._store.list_displays() if display.client_id == client_id and display.output == output),
            None,
        )

    def _label_output_on(self, client_id: str, output: str) -> LabelOutput | None:
        return next(
            (label for label in self._store.list_label_outputs() if label.client_id == client_id and label.output == output),
            None,
        )

    def _require_output(self, client: Client, wall: Wall, output: str, *, at: datetime) -> str:
        """The output's name, or a refusal that says what to do when none was chosen.

        An empty name is what Walls sends for a Player that has reported no
        screens, since it has none to offer; "output cannot be empty" told the
        curator nothing of that.
        """
        if output.strip():
            return output.strip()
        names = self.read_heartbeat(client.id, at).output_names()
        if names is None:
            raise ServiceError(
                f"{client.name} has not reported its screens yet, so there is no screen to show {wall.name} on. "
                "Start Arrt Player on that device and wait for it to report; then choose one of its screens here."
            )
        if not names:
            raise ServiceError(
                f"{client.name} reports no screens, so there is none to show {wall.name} on. "
                "Plug a screen into it and wait for its next report; then choose that screen here."
            )
        reported = ", ".join(repr(name) for name in sorted(names))
        raise ServiceError(f"Choose which of {client.name}'s screens shows {wall.name}: it reported {reported}.")

    def _require_wall(self, wall_id: str) -> Wall:
        # Programming's one wall lookup (`lookups.py`), so a refusal here reads
        # and raises as it does on every other surface that names a wall.
        return Lookups(self._store).get_wall(wall_id)

    def _heartbeat_path(self, client_id: str) -> Path:
        return client_heartbeat.client_heartbeat_path_in(self._settings.art_root, client_id)


def view_of(client: Client, survey: PlacementSurvey, reading: ClientHeartbeatReading) -> ClientView:
    """One client's view from a survey and its report as read: the clients route's row, and the health route's Player."""
    displays = survey.displays_of(client.id)
    labels = survey.label_outputs_of(client.id)
    refused = survey.refused.get(client.id)
    reading = heard(reading, refused)
    player = player_reading(
        token_issued=client.token_issued_at is not None,
        reading=reading,
        recorded_displays=[display.output for display in displays],
        recorded_labels=[label.output for label in labels],
    )
    if refused is not None and player.state is PlayerState.REPORT_UNREADABLE:
        # Its reports have been refused since then: what Status says beside the
        # server's words (`health._player_words`).
        player = replace(player, since=refused.since)
    return ClientView(
        client=client,
        walls=survey.shown_walls(client.id),
        displays=displays,
        label_outputs=labels,
        faults=survey.faults_of(client.id),
        heartbeat=reading,
        player=player,
    )


def _captioned_work(found: WallState) -> str | None:
    """The work a label document carries text for: what is on screen, or what was last, where the server knows it."""
    shown = found.state
    if shown.state is ScreenState.SHOWING_ART:
        return shown.work_id
    if shown.state is ScreenState.SILENT:
        # A report names a work only with showing_art (`heartbeat.problem_with`
        # refuses one beside any other state), so the last report's work is the
        # work it last showed, or none.
        return None if shown.last is None else shown.last.work_id
    if shown.state is ScreenState.UNREACHABLE:
        contents: dict[str, Any] | None = found.reading.contents
        current = None if contents is None else contents.get("current_work_id")
        return current if isinstance(current, str) and current else None
    return None
