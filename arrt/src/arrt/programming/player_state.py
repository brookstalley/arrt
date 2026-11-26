"""What state each Player is in, and each of its outputs, as the server can say it.

The wall's half of the one health model is `display_state.py`: what a wall's
screen is doing. This is the Player's half: whether the device at the wall has
been given a token, has reported, is reporting now, or has stopped. Settings ›
Players, Status, the top bar and the System badge read it from the clients and
health routes, so none of them derives a Player's state from the raw report.

**The keys are the contract's** (`contract/vocabulary.json` `player_states`, from
contract 1.3.0); the words for them are said by the screens, which quote the
package. The server cannot read the package at run time (`arrt-contract` is a
development dependency, and the image's app stage installs none), so the one fact
about a state the server acts on, whether it is a step not yet taken rather than a
fault, is quoted here as `SETUP` and held to the package by
`arrt/tests/unit/test_player_state.py`, as `adequacy.py` quotes the bottom weight.

**State is per output, as well as per Player** (the owner's ruling 8 of
2026-11-19: a label is an output a Player has zero or more of, as a display is,
and a Player with labels and no display must be describable). Each display output
and each label output the Player reports, or the server has recorded for it, has
an `OutputState` of its own, so two label panels on one Player, one reported and
one named by the curator before the Player had it, read apart.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from arrt.programming.client_heartbeat import ClientHeartbeatReading
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS


class PlayerState(StrEnum):
    """A Player's state: the five keys `vocabulary.json`'s `player_states` words."""

    #: No token has been issued, so the Player is admitted nowhere whatever an
    #: old report says.
    NO_TOKEN = "no_token"  # noqa: S105 -- a state key (vocabulary.json player_states), not a secret
    #: A token, and no report yet: the evening the Player was added.
    AWAITING_REPORT = "awaiting_report"
    #: Its last report is readable and no older than `STALE_AFTER_SECONDS`.
    REPORTING = "reporting"
    #: Its last report is readable and older than `STALE_AFTER_SECONDS`.
    NOT_HEARD_FROM = "not_heard_from"
    #: A report is there and this server cannot read it.
    REPORT_UNREADABLE = "report_unreadable"


#: The states that are a step not yet taken rather than a fault: never a trouble
#: on the top bar or the System badge. Quoted from `vocabulary.json`'s
#: `player_states` setup flags; `test_player_state.py` holds the two alike.
SETUP: Final[frozenset[PlayerState]] = frozenset({PlayerState.NO_TOKEN, PlayerState.AWAITING_REPORT})

#: The states that are a fault the household is told of. Never a setup state.
TROUBLES: Final[frozenset[PlayerState]] = frozenset({PlayerState.NOT_HEARD_FROM, PlayerState.REPORT_UNREADABLE})


class OutputKind(StrEnum):
    """Which of a Player's two kinds of output: a screen a wall is shown on, or a label panel."""

    DISPLAY = "display"
    LABEL = "label"


@dataclass(frozen=True, slots=True)
class OutputState:
    """One output of a Player, in the state the Player's report puts it in.

    Its state is its Player's, but for one case only an output can be in: the
    Player is reporting and its report does not list this output, which the
    server recorded for it (a curator named it before the Player had it), so the
    output is `awaiting_report` while the Player is `reporting`.
    """

    kind: OutputKind
    #: The output's name, as the Player names it and a wall or label is placed on it.
    name: str
    state: PlayerState
    #: As the current report says, only while the output's state is `reporting`;
    #: null otherwise, because an old or unreadable report says nothing about now.
    connected: bool | None


@dataclass(frozen=True, slots=True)
class PlayerReading:
    """One Player's state and each of its outputs', read from its token and its last report."""

    state: PlayerState
    #: When the Player entered this state, where the server knows it: the last
    #: report's instant for `reporting` and `not_heard_from` ("Not heard from since
    #: {date}"); for `report_unreadable` because this server refused its reports,
    #: the first refusal since one was accepted (`clients.view_of`); null otherwise.
    since: datetime | None
    #: Every output the Player reports or the server has recorded for it: the
    #: report's displays in its order, then its label outputs in its order, then
    #: recorded outputs the report does not list, by name.
    outputs: Sequence[OutputState]

    @property
    def setup(self) -> bool:
        """Whether the Player's state is a step not yet taken, never a fault."""
        return self.state in SETUP


def player_state_of(*, token_issued: bool, reading: ClientHeartbeatReading) -> PlayerState:
    """The Player's state from whether it holds a token and what its report file holds.

    No token wins over any report, because a Player with none is admitted
    nowhere: a report left from before its token was revoked says nothing it can
    act on.
    """
    if not token_issued:
        return PlayerState.NO_TOKEN
    if reading.absent:
        return PlayerState.AWAITING_REPORT
    if reading.problem is not None:
        return PlayerState.REPORT_UNREADABLE
    if reading.age_seconds is not None and reading.age_seconds > STALE_AFTER_SECONDS:
        return PlayerState.NOT_HEARD_FROM
    return PlayerState.REPORTING


def player_reading(
    *,
    token_issued: bool,
    reading: ClientHeartbeatReading,
    recorded_displays: Sequence[str] = (),
    recorded_labels: Sequence[str] = (),
) -> PlayerReading:
    """The Player's state and each output's, from its token, its report and the outputs recorded for it.

    `recorded_displays` and `recorded_labels` are the output names the server
    holds a display or label output record for on this Player.
    """
    state = player_state_of(token_issued=token_issued, reading=reading)
    reporting = state is PlayerState.REPORTING
    outputs: list[OutputState] = []
    seen: set[tuple[OutputKind, str]] = set()
    # A report that is not current says nothing about which outputs exist now,
    # so only a current one lists them; the rest come from the records.
    if reporting:
        for output in reading.outputs:
            outputs.append(OutputState(OutputKind.DISPLAY, output.name, PlayerState.REPORTING, output.connected))
            seen.add((OutputKind.DISPLAY, output.name))
        for label in reading.label_outputs:
            outputs.append(OutputState(OutputKind.LABEL, label.name, PlayerState.REPORTING, label.connected))
            seen.add((OutputKind.LABEL, label.name))
    recorded = [(OutputKind.DISPLAY, name) for name in recorded_displays] + [(OutputKind.LABEL, name) for name in recorded_labels]
    for kind, name in sorted(set(recorded) - seen, key=lambda each: (each[0] is OutputKind.LABEL, each[1])):
        outputs.append(OutputState(kind, name, PlayerState.AWAITING_REPORT if reporting else state, None))
    # Report-less states list only recorded outputs, which can include none:
    # what a Player not reporting has is the records' to say, not an old file's.
    since = reading.reported_at if state in {PlayerState.REPORTING, PlayerState.NOT_HEARD_FROM} else None
    return PlayerReading(state=state, since=since, outputs=tuple(outputs))
