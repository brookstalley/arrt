"""Which Player may read which wall: one token per wall, kept only as a verifier.

`security-model.md` records the decision: every request a Player makes carries its
wall's token as `Authorization: Bearer <token>`. A missing or wrong token is
refused as unauthenticated, and a token for another wall as forbidden, so a
misconfigured Player is told which mistake it made. Media accepts any wall's
valid token, because a render is shared by every wall that shows it.

**The token is shown once and never stored.** The wall keeps the SHA-256 of it. A
token is 32 random bytes, so its hash cannot be searched for, and a slow password
hash would buy nothing: it exists to make guessing cheap passwords expensive, and
there is no cheap password here. Comparisons are constant-time all the same,
because that costs nothing.

**The token never reaches the journal.** A refusal is logged by wall and by
status, once per wall per interval, so a Player retrying every second with a
stale token says so once rather than every second.
"""

import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from curatarr.persistence.records import Wall
from curatarr.programming.store import ProgrammingStore
from curatarr.services.errors import ServiceError
from curatarr.services.store import store_write

log = logging.getLogger(__name__)

#: How long one wall's refusals stay quiet after the first is logged.
REFUSAL_LOG_INTERVAL_SECONDS: Final[float] = 600.0


class Admission(StrEnum):
    """What a presented token proves."""

    #: It is the named wall's current token.
    ADMITTED = "admitted"
    #: It is no wall's current token, or there was none: unauthenticated.
    UNKNOWN = "unknown"
    #: It is another wall's current token: authenticated, and not for this wall.
    OTHER_WALL = "other_wall"


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """A new token, the only time it exists outside the Player that holds it."""

    wall_id: str
    token: str
    issued_at: datetime


def verifier_of(token: str) -> str:
    """What is stored in place of a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PlayerAccess:
    """Issue wall tokens, and decide whether a presented one opens a wall."""

    def __init__(self, store: ProgrammingStore, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._store = store
        self._clock = clock
        self._last_logged: dict[str, float] = {}
        self._logging = threading.Lock()

    def issue(self, wall_id: str) -> IssuedToken:
        """Give this wall a new token, replacing any it had.

        Rotating is issuing again: the old token stops working the moment this
        commits, and the Player holding it is refused until it is given the new
        one. That is the point of a rotation, and it is why the issue time is kept
        and shown.
        """
        wall = self._require_wall(wall_id)
        token = secrets.token_urlsafe(32)
        issued_at = datetime.now(UTC)
        store_write(self._store.update_wall, replace(wall, token_verifier=verifier_of(token), token_issued_at=issued_at))
        log.info("Issued a new Player token for wall %r; any earlier one no longer works.", wall.name)
        return IssuedToken(wall_id=wall.id, token=token, issued_at=issued_at)

    def admit(self, wall_id: str, token: str | None) -> Admission:
        """Whether this token opens this wall. A refusal is logged, never the token."""
        walls = self._store.list_walls()
        admission = self._judge(walls, wall_id, token)
        if admission is not Admission.ADMITTED:
            # Keyed and named by a wall this plane holds, never by the id in the
            # URL: that id is the caller's choice, and keying on it would give a
            # caller a fresh log line, and a fresh entry to keep, per id it
            # invents, and put whatever it typed into the journal.
            known = next((wall.name for wall in walls if wall.id == wall_id), None)
            self._log_refusal(f"wall {known!r}" if known is not None else "an unknown wall", admission)
        return admission

    def admit_any(self, token: str | None) -> Admission:
        """Whether this token opens any wall, which is what media asks."""
        walls = self._store.list_walls()
        presented = None if not token else verifier_of(token)
        if presented is not None and any(_matches(wall, presented) for wall in walls):
            return Admission.ADMITTED
        self._log_refusal("any wall", Admission.UNKNOWN)
        return Admission.UNKNOWN

    @staticmethod
    def _judge(walls: Sequence[Wall], wall_id: str, token: str | None) -> Admission:
        if not token:
            return Admission.UNKNOWN
        presented = verifier_of(token)
        # Every wall is compared, the named one included, so the time taken does
        # not depend on which wall the token belongs to.
        matched = [wall.id for wall in walls if _matches(wall, presented)]
        if wall_id in matched:
            return Admission.ADMITTED
        return Admission.OTHER_WALL if matched else Admission.UNKNOWN

    def _log_refusal(self, subject: str, admission: Admission) -> None:
        now = self._clock()
        with self._logging:
            last = self._last_logged.get(subject)
            if last is not None and now - last < REFUSAL_LOG_INTERVAL_SECONDS:
                return
            self._last_logged[subject] = now
        reason = "a token for another wall" if admission is Admission.OTHER_WALL else "no valid token"
        log.warning(
            "Refused a Player request for %s: it presented %s. Further refusals for it are quiet for %d minutes.",
            subject,
            reason,
            int(REFUSAL_LOG_INTERVAL_SECONDS // 60),
        )

    def _require_wall(self, wall_id: str) -> Wall:
        wall = self._store.get_wall(wall_id)
        if wall is None:
            raise ServiceError(f"No wall with id {wall_id!r} is in the catalogue.")
        return wall


def _matches(wall: Wall, presented: str) -> bool:
    return wall.token_verifier is not None and hmac.compare_digest(wall.token_verifier, presented)
