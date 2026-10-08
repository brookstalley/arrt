"""What each wall's screen is doing, as the server can say it.

`labels-and-surfaces.md` § Display state. A wall's controller reports one of five
states in its heartbeat (minor 3's `display_state`); the server adds two that no
controller can report about itself:

- **`unassigned`**: no client output shows the wall, so there is no screen to
  speak of whatever any file says.
- **`silent`**: the wall's last report is older than `STALE_AFTER_SECONDS`, or
  there is no readable report at all. What it last said is kept as `last`, so a
  label can hold its caption for a while and Walls can say what was last seen.

A Player before minor 3 says nothing of its screen beyond `current_work_id`, which
is read as `showing_art` with that work (`player-contract.md` § The heartbeat,
minor 3). One that names no work has not said what is on its screen, which is
`unreachable`: the controller cannot tell, as far as the server can know.

One function, so `/api/walls` and the MCP walls read cannot come to state two
different answers for one wall.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from arrt import observations
from arrt.persistence.records import Wall
from arrt.programming.manifest import heartbeat
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS, HeartbeatReading


class ScreenState(StrEnum):
    """A wall's display state: the controller's five, then the server's two."""

    SHOWING_ART = "showing_art"
    IN_USE = "in_use"
    DARK = "dark"
    NO_SCREEN = "no_screen"
    UNREACHABLE = "unreachable"
    UNASSIGNED = "unassigned"
    SILENT = "silent"


#: The states a controller reports, and the only ones a heartbeat may carry.
REPORTED: Final[frozenset[ScreenState]] = frozenset(ScreenState(value) for value in heartbeat.REPORTED_DISPLAY_STATES)


@dataclass(frozen=True, slots=True)
class ReportedState:
    """What the wall's controller last said, read from a readable heartbeat."""

    state: ScreenState
    #: The work on screen, only with `showing_art`; null there for a picture this
    #: wall did not put there.
    work_id: str | None
    #: When the screen entered this state. Null from a Player before minor 3,
    #: which never said.
    since: datetime | None


@dataclass(frozen=True, slots=True)
class DisplayState:
    """One wall's display state, with the report it was read from."""

    state: ScreenState
    #: Only with `showing_art`.
    work_id: str | None
    #: When the wall entered this state, where that is known: the controller's
    #: `since`, or for `silent` the instant of the last report.
    since: datetime | None
    #: When the wall's heartbeat was written, and how old it is; null when there
    #: is no readable one.
    reported_at: datetime | None
    age_seconds: float | None
    #: For `silent`, what the last readable report said; null otherwise, and null
    #: for a wall that has never readably reported.
    last: ReportedState | None


def reported_state(contents: dict[str, object]) -> ReportedState:
    """The controller's state from a heartbeat `heartbeat.problem_with` accepts.

    Minor 3 says it; before that, `current_work_id` is all there is.
    """
    stated = contents.get("display_state")
    if isinstance(stated, dict):
        work_id = stated["work_id"]
        if stated["state"] not in heartbeat.REPORTED_DISPLAY_STATES:
            # A state a later minor added: the controller said something this
            # server cannot name, so it shows as not known and names no work.
            return ReportedState(state=ScreenState.UNREACHABLE, work_id=None, since=observations.instant(stated["since"]))
        return ReportedState(
            state=ScreenState(stated["state"]),
            work_id=work_id if isinstance(work_id, str) else None,
            since=observations.instant(stated["since"]),
        )
    current = contents.get("current_work_id")
    if isinstance(current, str) and current:
        return ReportedState(state=ScreenState.SHOWING_ART, work_id=current, since=None)
    return ReportedState(state=ScreenState.UNREACHABLE, work_id=None, since=None)


def display_state_of(wall: Wall, reading: HeartbeatReading) -> DisplayState:
    """The wall's state: unassigned, else silent, else what its controller reported."""
    if wall.client_id is None or wall.output is None:
        return DisplayState(state=ScreenState.UNASSIGNED, work_id=None, since=None, reported_at=None, age_seconds=None, last=None)
    readable = reading.contents is not None and reading.problem is None
    last = reported_state(reading.contents) if readable and reading.contents is not None else None
    stale = reading.age_seconds is not None and reading.age_seconds > STALE_AFTER_SECONDS
    if last is None or stale:
        return DisplayState(
            state=ScreenState.SILENT,
            work_id=None,
            since=reading.reported_at if last is not None else None,
            reported_at=reading.reported_at if last is not None else None,
            age_seconds=reading.age_seconds if last is not None else None,
            last=last,
        )
    return DisplayState(
        state=last.state,
        work_id=last.work_id,
        since=last.since,
        reported_at=reading.reported_at,
        age_seconds=reading.age_seconds,
        last=None,
    )
