"""What each wall has shown, kept one report at a time.

A Player's heartbeat says what its screen is doing now (`display_state`). Kept
one file per wall and overwritten, that answers nothing about yesterday. This
turns each report into the showings it implies, so Walls can say what a dark
screen last showed and Artworks can find the works no wall has shown.

**A showing is one stretch of one work on one wall**, identified by the wall
and when it started. A minor 3 Player says when (`since`), and resets it
whenever the state or the work changes, so a report sent twice extends its
showing rather than starting another. A Player before minor 3 says no `since`,
and its showing is the run of reports naming one work with no gap longer than
`STALE_AFTER_SECONDS` between them.

**A report is believed only for a work the wall's feed carries.** Anything
else on screen (a work this wall was never sent, a picture it did not put
there, television) ends the showing before it and starts none. A report of
`unreachable` ends it at the last report that named it, because the
controller cannot tell what came after.

Pure: `advance` takes the wall's latest showing and one report, and returns
what to save, so the rules are tested without a store.
"""

from collections.abc import Collection, Sequence
from dataclasses import replace
from datetime import datetime, timedelta

from arrt.persistence.records import Showing
from arrt.programming.display_state import ReportedState, ScreenState
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS

#: Past this gap between two reports from a Player that sends no `since`, the
#: same work named again is a second showing: the wall was silent between.
_JOINS_WITHIN = timedelta(seconds=STALE_AFTER_SECONDS)


def advance(
    latest: Showing | None,
    reported: ReportedState,
    *,
    wall_id: str,
    at: datetime,
    playable: Collection[str],
) -> Sequence[Showing]:
    """The showings to save for one report made `at`: the open one extended or ended, and a new one begun.

    `latest` is the wall's showing that started last, ended or not. `playable`
    is the works the wall's feed carries now. A report older than the latest
    showing's last sight is one already superseded, and changes nothing.
    """
    if superseded(latest, at):
        return []
    open_ = latest if latest is not None and latest.ended_at is None else None
    names = believed_work(reported, playable)
    if names is None:
        return [] if open_ is None else [replace(open_, ended_at=_end_of(open_, reported, at))]
    start = reported.since if reported.since is not None else at
    if open_ is not None and open_.work_id == names and _continues(open_, reported, start=start, at=at):
        return [replace(open_, last_seen_at=at)]
    if latest is not None and start <= latest.started_at:
        # A showing that began no later than the latest one and is not it: an
        # echo of a state already superseded.
        return []
    ended = [] if open_ is None else [replace(open_, ended_at=_end_of(open_, reported, at))]
    # Not before the showing it follows ended: a wall shows one thing at a time,
    # and a later report naming this one's `since` still extends it.
    floor = None if latest is None else (ended[0] if ended else latest).ended_at
    begun = Showing(wall_id=wall_id, work_id=names, started_at=start if floor is None else max(start, floor), last_seen_at=at)
    return [*ended, begun]


def believed_work(reported: ReportedState, playable: Collection[str]) -> str | None:
    """The work a report says is on screen, if it is one the wall's feed carries; None otherwise."""
    shown = reported.work_id if reported.state is ScreenState.SHOWING_ART else None
    return shown if shown in playable else None


def unbelieved_work(reported: ReportedState, playable: Collection[str]) -> str | None:
    """The work a report says is on screen when the wall's feed does not carry it; None otherwise."""
    shown = reported.work_id if reported.state is ScreenState.SHOWING_ART else None
    return shown if shown is not None and shown not in playable else None


def superseded(latest: Showing | None, at: datetime) -> bool:
    """Whether a report made `at` is older than the latest sight already kept, and so says nothing about now."""
    return latest is not None and at < latest.last_seen_at


def _continues(open_: Showing, reported: ReportedState, *, start: datetime, at: datetime) -> bool:
    """Whether a report of `open_`'s work is still `open_`: the same `since`, or before minor 3 no long gap."""
    return start <= open_.started_at if reported.since is not None else _joins(open_, at)


def _joins(open_: Showing, at: datetime) -> bool:
    return at - open_.last_seen_at <= _JOINS_WITHIN


def _end_of(open_: Showing, reported: ReportedState, at: datetime) -> datetime:
    """When `open_` ended, given a report of something else: the latest instant the reports support."""
    if reported.state is ScreenState.UNREACHABLE:
        end = open_.last_seen_at
    elif reported.since is not None:
        end = reported.since
    else:
        end = at if _joins(open_, at) else open_.last_seen_at
    # Never before it was last seen: a controller contradicting its own earlier
    # report has not made the showing shorter than it was observed to be.
    return max(end, open_.last_seen_at)
