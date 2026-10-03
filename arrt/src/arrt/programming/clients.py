"""Clients: the installed Players the server knows, and which walls each shows on which output.

`clients.md` is the requirement. A client is a name and one credential (issued by
`access.py`); it drives any number of walls, each on one of its outputs, and it
learns which from `GET /client`, so assigning a wall to a client needs no edit on
the host. Assigning is a curatorial act, like hanging a theme, and so lives here
in Programming beside the walls it changes.

**Every rule about a valid assignment is here**, and the store's partial unique
index is only the weaker statement of one of them: a client's output shows one
wall. HTTP (Settings › Clients) and MCP (`art_display`) both bind it.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from arrt.persistence.records import Client, Wall
from arrt.programming import client_heartbeat
from arrt.programming.client_heartbeat import ClientHeartbeatReading
from arrt.programming.display import DisplaySettings
from arrt.programming.manifest.builder import write_atomically
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import ServiceError
from arrt.services.fields import require_text
from arrt.services.store import store_write

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ClientView:
    """One client with the walls it shows and what it last reported, read together."""

    client: Client
    #: In the order walls are listed everywhere else.
    walls: Sequence[Wall]
    heartbeat: ClientHeartbeatReading


@dataclass(frozen=True, slots=True)
class WallAssignment:
    """A wall just placed on a client's output, and anything the curator should know about it."""

    wall: Wall
    client: Client
    #: Set when the output could not be confirmed against what the client last
    #: reported: it has not reported, or reported outputs without this name.
    #: The assignment is made either way, because a client that has not started
    #: yet has nothing to report, and the curator may be setting it up first.
    notice: str | None


class ClientService:
    """Record clients, and place walls on their outputs."""

    def __init__(self, store: ProgrammingStore, settings: DisplaySettings) -> None:
        self._store = store
        self._settings = settings

    # -- reads ----------------------------------------------------------------

    def get_client(self, client_id: str) -> Client:
        client = self._store.get_client(client_id)
        if client is None:
            raise ServiceError(f"No client with id {client_id!r} is recorded.")
        return client

    def list_clients(self) -> Sequence[ClientView]:
        """Every client, with its walls and its last heartbeat."""
        walls = self._store.list_walls()
        return [self._view(client, walls) for client in self._store.list_clients()]

    def get_client_view(self, client_id: str) -> ClientView:
        return self._view(self.get_client(client_id), self._store.list_walls())

    def walls_of(self, client_id: str) -> Sequence[Wall]:
        """The walls assigned to this client, in the order walls are listed."""
        self.get_client(client_id)
        return [wall for wall in self._store.list_walls() if wall.client_id == client_id]

    def client_document(self, client_id: str) -> bytes:
        """What `GET /client` answers: this client and its walls, as the bytes the ETag hashes.

        `contract/schemas/client.v1.schema.json` is the shape. Serialised here,
        once, so the ETag is a hash of exactly what a client was sent.
        """
        client = self.get_client(client_id)
        document = {
            "client_id": client.id,
            "name": client.name,
            "walls": [
                {"wall_id": wall.id, "name": wall.name, "output": wall.output}
                for wall in self._store.list_walls()
                if wall.client_id == client.id
            ],
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
        """Forget a client; its token stops working and the walls it drove become unassigned.

        Returns the walls released, so a caller can say which rooms now have
        nothing showing them. They keep their themes: a wall nobody drives is an
        ordinary state, and hanging survives it.
        """
        client = self.get_client(client_id)
        released = []
        with self._store.transaction():
            for wall in self._store.list_walls():
                if wall.client_id == client.id:
                    unassigned = replace(wall, client_id=None, output=None)
                    store_write(self._store.update_wall, unassigned)
                    released.append(unassigned)
            store_write(self._store.remove_client, client.id)
        # After the commit: the report of a client the server no longer knows
        # would otherwise sit under the art root with nothing ever reading it.
        self._heartbeat_path(client.id).unlink(missing_ok=True)
        log.info("Removed client %r; %d wall(s) it drove are now unassigned.", client.name, len(released))
        return released

    # -- writes: assignment ---------------------------------------------------

    def assign_wall(self, wall_id: str, *, client_id: str, output: str) -> WallAssignment:
        """Show this wall on one of this client's outputs, by the output's name.

        The output need not be among those the client last reported — it may not
        have reported yet — and the answer says so when it is not. Refused when
        that output of that client already shows another wall, because one
        screen shows one picture.
        """
        wall = self._require_wall(wall_id)
        client = self.get_client(client_id)
        output = require_text(output, field="output")
        for other in self._store.list_walls():
            if other.id != wall.id and other.client_id == client.id and other.output == output:
                raise ServiceError(
                    f"{client.name}'s output {output!r} already shows {other.name}. "
                    f"Unassign {other.name} first, or choose another output."
                )
        assigned = replace(wall, client_id=client.id, output=output)
        store_write(self._store.update_wall, assigned)
        log.info("Wall %r is now shown by client %r on output %r.", wall.name, client.name, output)
        return WallAssignment(wall=assigned, client=client, notice=self._unconfirmed(client, output))

    def unassign_wall(self, wall_id: str) -> Wall:
        """Take a wall off whichever client showed it. Unassigning an unassigned wall is not an error."""
        wall = self._require_wall(wall_id)
        unassigned = replace(wall, client_id=None, output=None)
        if wall.client_id is not None:
            store_write(self._store.update_wall, unassigned)
        return unassigned

    # -- what a client writes -------------------------------------------------

    def record_heartbeat(self, client_id: str, document: object) -> None:
        """Keep what a client said about its outputs, where the curator's listing reads it.

        Refused, and nothing written, if it is not a document this server can
        read — so the listing never shows a report it would call unreadable.
        """
        self.get_client(client_id)
        problem = client_heartbeat.problem_with(document)
        if problem is not None:
            raise ServiceError(f"That is not a client heartbeat this server can read: {problem}")
        write_atomically(self._heartbeat_path(client_id), document)

    # -- helpers --------------------------------------------------------------

    def _view(self, client: Client, walls: Sequence[Wall]) -> ClientView:
        return ClientView(
            client=client,
            walls=[wall for wall in walls if wall.client_id == client.id],
            heartbeat=self.read_heartbeat(client.id),
        )

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

    def _require_wall(self, wall_id: str) -> Wall:
        wall = self._store.get_wall(wall_id)
        if wall is None:
            raise ServiceError(f"No wall with id {wall_id!r} is in the catalogue.")
        return wall

    def _heartbeat_path(self, client_id: str) -> Path:
        return client_heartbeat.client_heartbeat_path_in(self._settings.art_root, client_id)
