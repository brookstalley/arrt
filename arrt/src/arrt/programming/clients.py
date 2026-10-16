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
(Settings › Clients, Walls) and MCP (`art_display`) both bind it.

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
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from arrt.library.facade import LibraryFacade
from arrt.persistence.records import Client, Display, LabelOutput, Wall
from arrt.programming import client_heartbeat
from arrt.programming.client_heartbeat import ClientHeartbeatReading
from arrt.programming.display_state import DisplayState, ScreenState, display_state_of
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.builder import write_atomically
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS, HeartbeatReading, heartbeat_path_in
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import ServiceError
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
            "A display is configured on one client; remove it from the others' settings."
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
    """

    def __init__(self, store: ProgrammingStore, art_root: Path) -> None:
        self._store = store
        self._art_root = art_root

    def survey(self) -> PlacementSurvey:
        with self._store.reading():
            clients = {client.id: client for client in self._store.list_clients()}
            displays = {display.id: display for display in self._store.list_displays()}
            walls = list(self._store.list_walls())
            label_outputs = list(self._store.list_label_outputs())
        readings = {
            client_id: client_heartbeat.read(client_heartbeat.client_heartbeat_path_in(self._art_root, client_id))
            for client_id in clients
        }
        return PlacementSurvey(
            clients=clients,
            displays=displays,
            walls=walls,
            label_outputs=label_outputs,
            readings=readings,
            faults=_faults(clients, displays, walls, readings),
        )

    def placement_of(self, wall: Wall) -> WallPlacement:
        return self.survey().placement_of(wall)

    def wall_state(self, wall: Wall) -> WallState:
        """The wall's display state, the one answer Walls, the MCP walls read and every label give."""
        reading = heartbeat.read(heartbeat_path_in(self._art_root, wall.id))
        shown = self.placement_of(wall).shown_by is not None
        return WallState(state=display_state_of(reading, shown=shown), reading=reading)


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

    def __init__(self, store: ProgrammingStore, settings: DisplaySettings, library: LibraryFacade) -> None:
        self._store = store
        self._settings = settings
        self._library = library
        self.placements = Placements(store, settings.art_root)
        #: Identities whose fault has been said in the journal this episode, so
        #: a fault is said once rather than at every heartbeat that meets it.
        self._faults_said: set[str] = set()

    # -- reads ----------------------------------------------------------------

    def get_client(self, client_id: str) -> Client:
        client = self._store.get_client(client_id)
        if client is None:
            raise ServiceError(f"No client with id {client_id!r} is recorded.")
        return client

    def list_clients(self) -> Sequence[ClientView]:
        """Every client, with what it shows, holds and last reported."""
        survey = self.placements.survey()
        return [self._view(client, survey) for client in self._store.list_clients()]

    def get_client_view(self, client_id: str) -> ClientView:
        client = self.get_client(client_id)
        return self._view(client, self.placements.survey())

    def walls_of(self, client_id: str) -> Sequence[Wall]:
        """The walls this client shows now, in the order walls are listed."""
        self.get_client(client_id)
        return [shown.wall for shown in self.placements.survey().shown_walls(client_id)]

    def placement_of(self, wall_id: str) -> WallPlacement:
        return self.placements.placement_of(self._require_wall(wall_id))

    def get_display(self, display_id: str) -> Display:
        display = self._store.get_display(display_id)
        if display is None:
            raise ServiceError(f"No display with id {display_id!r} is recorded.")
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
        wall's, from `Placements.wall_state`, the one answer Walls gives too. The
        label text is the work's, read through the Library facade: the work on
        screen with `showing_art`; with `silent` the work the last report showed;
        with `unreachable` the work the heartbeat last named; otherwise none, and
        none for a picture this wall did not put there. The renderer runs the
        label rule over it (`contract/vectors/label-rule.json`).
        """
        label = self._store.get_label_output(label_id)
        if label is None or label.wall_id is None:
            return None
        wall = self._store.get_wall(label.wall_id)
        if wall is None:
            return None
        found = self.placements.wall_state(wall)
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

    def read_heartbeat(self, client_id: str) -> ClientHeartbeatReading:
        return client_heartbeat.read(self._heartbeat_path(client_id))

    # -- writes: clients ------------------------------------------------------

    def add_client(self, *, name: str) -> Client:
        """Record a client. It has no token until one is issued, and drives no wall."""
        client = Client(id=str(uuid.uuid4()), name=require_text(name, field="name"), created_at=datetime.now(UTC))
        store_write(self._store.add_client, client)
        log.info("Recorded client %r.", client.name)
        return client

    def rename_client(self, client_id: str, *, name: str) -> Client:
        """Give a client a new name. Its token and its walls are unchanged."""
        renamed = replace(self.get_client(client_id), name=require_text(name, field="name"))
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
        wall = self._require_wall(wall_id)
        client = self.get_client(client_id)
        output = require_text(output, field="output")
        with self._store.transaction():
            display = self._display_on(client.id, output) or self._record_place(client, output)
            placed = self._place(wall, display, client)
        log.info("Wall %r is now shown by client %r on output %r.", wall.name, client.name, output)
        return WallAssignment(wall=placed, display=display, client=client, notice=self._notice(display, client))

    def assign_display(self, wall_id: str, *, display_id: str) -> WallAssignment:
        """Show this wall on a display, by the display's id. Refused when it already shows another wall."""
        wall = self._require_wall(wall_id)
        display = self.get_display(display_id)
        client = None if display.client_id is None else self._store.get_client(display.client_id)
        with self._store.transaction():
            placed = self._place(wall, display, client)
        log.info("Wall %r is now on display %r.", wall.name, display.identity)
        return WallAssignment(wall=placed, display=display, client=client, notice=self._notice(display, client))

    def unassign_wall(self, wall_id: str) -> Wall:
        """Take a wall off its display. Unassigning an unassigned wall is not an error."""
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
                label = LabelOutput(id=str(uuid.uuid4()), client_id=client.id, output=output)
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
        wall = self._require_wall(wall_id)
        label = self._store.get_label_output(label_id)
        if label is None:
            raise ServiceError(f"No label output with id {label_id!r} is recorded.")
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
        read — so the listing never shows a report it would call unreadable. The
        file is what Settings › Clients reads; the records are what walls and
        labels are placed on (`_reconcile_display` says how each output is
        matched to one).
        """
        client = self.get_client(client_id)
        problem = client_heartbeat.problem_with(document)
        if problem is not None:
            raise ServiceError(f"That is not a client heartbeat this server can read: {problem}")
        write_atomically(self._heartbeat_path(client_id), document)
        # A dict by now: `problem_with` refuses anything else.
        report = cast("dict[str, Any]", document)
        with self._store.transaction():
            for output in report["outputs"]:
                self._reconcile_display(client, output["name"], output["kind"], output.get("identity"))
            for label in report.get("label_outputs", []):
                if self._label_output_on(client.id, label["name"]) is None:
                    store_write(
                        self._store.add_label_output,
                        LabelOutput(id=str(uuid.uuid4()), client_id=client.id, output=label["name"]),
                    )

    # -- helpers --------------------------------------------------------------

    def _reconcile_display(self, client: Client, output: str, kind: str, identity: str | None) -> None:
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
                self._record_place(client, output, kind=kind)
            elif here.kind != kind:
                store_write(self._store.update_display, replace(here, kind=kind))
            return
        known = next((display for display in self._store.list_displays() if display.identity == identity), None)
        if known is None:
            self._first_report(client, output, kind, identity, here)
            return
        if known.client_id == client.id and known.output == output:
            self._faults_said.discard(identity)
            if known.kind != kind:
                store_write(self._store.update_display, replace(known, kind=kind))
            return
        if known.client_id not in (None, client.id) and self._still_reports(known.client_id, identity):
            self._say_fault(client, known)
            return
        self._faults_said.discard(identity)
        if here is not None and here.id != known.id:
            if here.identity == place_identity(client.id, output):
                self._merge_place(here, into=known)
            else:
                self._release(here)
        store_write(self._store.update_display, replace(known, client_id=client.id, output=output, kind=kind))
        log.info("The display %s is now on client %r's output %r, with its walls.", identity, client.name, output)

    def _first_report(self, client: Client, output: str, kind: str, identity: str, here: Display | None) -> None:
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
                id=str(uuid.uuid4()),
                identity=identity,
                client_id=client.id,
                output=output,
                kind=kind,
                first_seen=datetime.now(UTC),
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

    def _still_reports(self, client_id: str, identity: str) -> bool:
        reading = self.read_heartbeat(client_id)
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

    def _record_place(self, client: Client, output: str, *, kind: str | None = None) -> Display:
        """The display on a client's output that no device has named, recorded by place.

        One left with no client under that identity is taken back rather than
        recorded twice, since the identity is unique.
        """
        identity = place_identity(client.id, output)
        if kind is None:
            reported = {entry.name: entry for entry in self.read_heartbeat(client.id).outputs}.get(output)
            kind = None if reported is None else reported.kind
        orphan = next((display for display in self._store.list_displays() if display.identity == identity), None)
        if orphan is not None:
            restored = replace(orphan, client_id=client.id, output=output, kind=kind or orphan.kind)
            store_write(self._store.update_display, restored)
            return restored
        display = Display(
            id=str(uuid.uuid4()),
            identity=identity,
            client_id=client.id,
            output=output,
            kind=kind,
            first_seen=datetime.now(UTC),
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

    def _view(self, client: Client, survey: PlacementSurvey) -> ClientView:
        return ClientView(
            client=client,
            walls=survey.shown_walls(client.id),
            displays=survey.displays_of(client.id),
            label_outputs=survey.label_outputs_of(client.id),
            faults=survey.faults_of(client.id),
            heartbeat=survey.readings.get(client.id) or self.read_heartbeat(client.id),
        )

    def _notice(self, display: Display, client: Client | None) -> str | None:
        if client is None:
            return (
                f"No client reports the display {display.identity} now, so nothing shows this wall until one does. "
                "The assignment is kept either way."
            )
        fault = self.placements.survey().faults.get(display.identity)
        if fault is not None:
            return fault.describe()
        return self._unconfirmed(client, display.output)

    def _unconfirmed(self, client: Client, output: str) -> str | None:
        names = self.read_heartbeat(client.id).output_names()
        if names is None:
            return (
                f"{client.name} has not reported its outputs yet, so whether it has one called {output!r} "
                "cannot be checked. The assignment is kept either way."
            )
        if output not in names:
            reported = ", ".join(repr(name) for name in sorted(names)) or "none"
            return (
                f"{client.name} last reported these outputs: {reported}. {output!r} is not among them, "
                "so the client cannot show this wall until it has an output by that name."
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
                "so nothing captions this wall there until the client has a label output by that name."
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

    def _require_wall(self, wall_id: str) -> Wall:
        wall = self._store.get_wall(wall_id)
        if wall is None:
            raise ServiceError(f"No wall with id {wall_id!r} is in the catalogue.")
        return wall

    def _heartbeat_path(self, client_id: str) -> Path:
        return client_heartbeat.client_heartbeat_path_in(self._settings.art_root, client_id)


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
