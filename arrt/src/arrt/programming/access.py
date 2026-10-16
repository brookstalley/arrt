"""Which Player may read which wall: one token per client, kept only as a verifier.

`security-model.md` records the decision, and `clients.md` the ruling that moved
it from walls to clients on 2026-10-02: every request a Player makes carries its
**client's** token as `Authorization: Bearer <token>`, and a client is admitted to
the walls assigned to it. A missing or unknown token is refused as
unauthenticated, and a valid token asking for a wall that is not its client's as
forbidden, so a misconfigured Player is told which mistake it made. Media accepts
any client's valid token, because a render is shared by every wall that shows it.

**Wall tokens are retired, and admit nothing.** Nothing here reads a wall for a
credential; the columns that held wall verifiers are dropped by
`migrations.retire_wall_tokens`.

**The token is shown once and never stored.** The client keeps the SHA-256 of
it. A token is 32 random bytes, so its hash cannot be searched for, and a slow
password hash would buy nothing: it exists to make guessing cheap passwords
expensive, and there is no cheap password here. Comparisons are constant-time all
the same, because that costs nothing.

**Which client a wall is assigned to is `clients.Placements`' answer**, the one
`GET /client` and every display state also take: the client of the wall's
display, and no client while two report that display. A label output is opened
by the client that holds it.

**The token never reaches the journal.** A refusal is logged by the client it
came from, or as "an unknown client", once per that subject per interval, so a
Player retrying every second with a stale token says so once rather than every
second.
"""

import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from arrt.persistence.records import Client
from arrt.programming.clients import Placements
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import ServiceError
from arrt.services.store import store_write

log = logging.getLogger(__name__)

#: How long one subject's refusals stay quiet after the first is logged.
REFUSAL_LOG_INTERVAL_SECONDS: Final[float] = 600.0

#: What a refusal is keyed and named by when no client presented itself. One
#: subject for every such request, so a caller cannot buy a fresh log line, or a
#: fresh entry to keep, by inventing tokens or wall ids.
_UNKNOWN_CLIENT: Final[str] = "an unknown client"


class Admission(StrEnum):
    """What a presented token proves."""

    #: It is the current token of the client the wall is assigned to.
    ADMITTED = "admitted"
    #: It is no client's current token, or there was none: unauthenticated.
    UNKNOWN = "unknown"
    #: It is a client's current token, and the wall is not assigned to that client.
    NOT_ITS_WALL = "not_its_wall"
    #: It is a client's current token, and the label output is not that client's.
    NOT_ITS_LABEL = "not_its_label"


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """A new client token, the only time it exists outside the host that holds it."""

    client_id: str
    token: str
    issued_at: datetime


def verifier_of(token: str) -> str:
    """What is stored in place of a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PlayerAccess:
    """Issue client tokens, and decide whether a presented one opens a wall."""

    def __init__(self, store: ProgrammingStore, placements: Placements, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._store = store
        self._placements = placements
        self._clock = clock
        self._last_logged: dict[str, float] = {}
        self._logging = threading.Lock()

    def issue(self, client_id: str) -> IssuedToken:
        """Give this client a new token, replacing any it had.

        Rotating is issuing again: the old token stops working the moment this
        commits, and the host holding it is refused until it is given the new
        one. That is the point of a rotation, and it is why the issue time is kept
        and shown.
        """
        client = self._store.get_client(client_id)
        if client is None:
            raise ServiceError(f"No client with id {client_id!r} is recorded.")
        token = secrets.token_urlsafe(32)
        issued_at = datetime.now(UTC)
        store_write(self._store.update_client, replace(client, token_verifier=verifier_of(token), token_issued_at=issued_at))
        log.info("Issued a new token for client %r; any earlier one no longer works.", client.name)
        return IssuedToken(client_id=client.id, token=token, issued_at=issued_at)

    def identify(self, token: str | None) -> Client | None:
        """The client this token belongs to, or None. A refusal is logged, never the token."""
        client = self._match(token)
        if client is None:
            self._log_refusal(_UNKNOWN_CLIENT, "it presented no valid client token")
        return client

    def admit(self, wall_id: str, token: str | None) -> Admission:
        """Whether this token opens this wall: its client must be the one that shows the wall now."""
        client = self.identify(token)
        if client is None:
            return Admission.UNKNOWN
        wall = self._store.get_wall(wall_id)
        shown_by = None if wall is None else self._placements.placement_of(wall).shown_by
        if shown_by is not None and shown_by.id == client.id:
            return Admission.ADMITTED
        # Named by a wall this plane holds, never by the id in the URL: that id
        # is the caller's choice, and whatever it typed must not reach the journal.
        asked = f"wall {wall.name!r}" if wall is not None else "a wall this server does not hold"
        self._log_refusal(f"client {client.name!r}", f"it asked for {asked}, which is not assigned to it")
        return Admission.NOT_ITS_WALL

    def admit_label(self, label_id: str, token: str | None) -> Admission:
        """Whether this token opens this label output's document: its client must hold the label output."""
        client = self.identify(token)
        if client is None:
            return Admission.UNKNOWN
        label = self._store.get_label_output(label_id)
        if label is not None and label.client_id == client.id:
            return Admission.ADMITTED
        # Named by what this plane holds, never by the id in the URL, for the
        # reason `admit` gives.
        asked = (
            f"label output {label.output!r} of another client"
            if label is not None
            else "a label output this server does not hold"
        )
        self._log_refusal(f"client {client.name!r}", f"it asked for {asked}")
        return Admission.NOT_ITS_LABEL

    def admit_any(self, token: str | None) -> Admission:
        """Whether this token is any client's, which is what media asks."""
        return Admission.ADMITTED if self.identify(token) is not None else Admission.UNKNOWN

    def _match(self, token: str | None) -> Client | None:
        if not token:
            return None
        presented = verifier_of(token)
        # Every client is compared, the matching one included, so the time taken
        # does not depend on which client the token belongs to.
        matched = [client for client in self._store.list_clients() if _matches(client, presented)]
        return matched[0] if matched else None

    def _log_refusal(self, subject: str, reason: str) -> None:
        now = self._clock()
        with self._logging:
            last = self._last_logged.get(subject)
            if last is not None and now - last < REFUSAL_LOG_INTERVAL_SECONDS:
                return
            self._last_logged[subject] = now
        log.warning(
            "Refused a Player request from %s: %s. Further refusals for it are quiet for %d minutes.",
            subject,
            reason,
            int(REFUSAL_LOG_INTERVAL_SECONDS // 60),
        )


def _matches(client: Client, presented: str) -> bool:
    return client.token_verifier is not None and hmac.compare_digest(client.token_verifier, presented)
