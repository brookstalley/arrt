"""The routes for walls: create, rename, delete, assign, mat and playback, labels, selections and the step to the next work."""

from typing import Any

from fastapi import APIRouter, Request

from arrt.http.models import (
    AddLabel,
    AssignDisplay,
    AssignWall,
    ClientNameOut,
    CreateWall,
    DisplayFaultOut,
    DisplayOut,
    DisplayStateOut,
    HangSelection,
    LabelAssignmentOut,
    LastShownOut,
    ManifestOut,
    NextOut,
    NotAgainOut,
    NotAgainRequest,
    ReportedStateOut,
    ScreenSizeOut,
    SetMatMode,
    SetPlayback,
    UpcomingOut,
    WallAssignmentOut,
    WallLabelOut,
    WallListOut,
    WallOut,
    WallWaitOut,
)
from arrt.http.routes.common import API_PREFIX, _services
from arrt.http.routes.manifest import _manifest
from arrt.http.routes.shapes import _instant, _theme
from arrt.persistence.records import Display, Showing, Wall
from arrt.programming import shape
from arrt.programming.clients import DisplayFault, PlacementSurvey
from arrt.programming.display import UNSET, SizeJudgement, WallView, feed_notice
from arrt.programming.display_state import DisplayState
from arrt.services.container import Services
from arrt.services.health import WallsNow, WallWait

router = APIRouter(prefix=API_PREFIX)


@router.get("/walls")
def list_walls(request: Request) -> WallListOut:
    """Every wall, what is hanging on each, and where each is shown."""
    return _walls(_services(request))


@router.post("/walls")
def create_wall(request: Request, body: CreateWall) -> WallOut:
    """Record a wall. It arrives with nothing hanging on it.

    **A wall recorded here lights up once a client is assigned to show it.**
    Hanging a theme writes that wall's own manifest, named by the id this route
    returns, and a client is admitted only to the walls assigned to it — so a
    second room needs a client output of its own, and nothing about it disturbs
    the first: a second wall never overwrites it.
    """
    services = _services(request)
    return _one_wall(services, services.display.add_wall(name=body.name).id)


@router.post("/walls/{wall_id}")
def rename_wall(request: Request, wall_id: str, body: CreateWall) -> WallOut:
    """Rename a wall. Nothing a Player reads carries the name, so nothing is republished."""
    services = _services(request)
    services.display.rename_wall(wall_id, name=body.name)
    return _one_wall(services, wall_id)


@router.delete("/walls/{wall_id}")
def delete_wall(request: Request, wall_id: str) -> WallListOut:
    """Forget a wall for good: what it hangs comes down, its screen and label panels are freed.

    Its history stays. Answers with the walls that remain, for the reason
    `delete_theme` gives: a delete changes the list it was made from.
    """
    services = _services(request)
    services.display.delete_wall(wall_id)
    return _walls(services)


@router.post("/walls/{wall_id}/client")
def assign_wall(request: Request, wall_id: str, body: AssignWall) -> WallAssignmentOut:
    """Show this wall on one of a client's outputs, by the output's name.

    Read-back-after-mutate, for the reason `clear_wall` gives: the answer is the
    wall as it now stands, with a notice when the output could not be checked
    against what the client last reported.
    """
    services = _services(request)
    assignment = services.clients.assign_wall(wall_id, client_id=body.client_id, output=body.output)
    return WallAssignmentOut(wall=_one_wall(services, wall_id), notice=assignment.notice)


@router.post("/walls/{wall_id}/display")
def assign_display(request: Request, wall_id: str, body: AssignDisplay) -> WallAssignmentOut:
    """Show this wall on a display, by the display's id: one a client reported, wherever it now is.

    Read-back-after-mutate, for the reason `clear_wall` gives.
    """
    services = _services(request)
    assignment = services.clients.assign_display(wall_id, display_id=body.display_id)
    return WallAssignmentOut(wall=_one_wall(services, wall_id), notice=assignment.notice)


@router.put("/walls/{wall_id}/mat")
def set_mat_mode(request: Request, wall_id: str, body: SetMatMode) -> WallOut:
    """Choose how this wall's Player draws the mat, or with null leave it to the Player.

    Read-back-after-mutate, for the reason `clear_wall` gives. The wall's feed is
    republished with the setting and nothing else in it moves.
    """
    services = _services(request)
    services.display.set_mat_mode(wall_id, body.mode)
    return _one_wall(services, wall_id)


@router.put("/walls/{wall_id}/playback")
def set_playback(request: Request, wall_id: str, body: SetPlayback) -> WallOut:
    """Choose how this wall plays its theme: pace, order and shapes (`SetPlayback`).

    Read-back-after-mutate, for the reason `clear_wall` gives. The wall's feed is
    republished at once, keeping the work on the wall now.
    """
    services = _services(request)
    # A field the body leaves out is left as it is, and null is "the default" or
    # "no limit": so a page that sets the shapes cannot put back a pace another
    # surface set since that page was drawn.
    sent = body.model_fields_set
    services.display.set_playback(
        wall_id,
        **{field: getattr(body, field) if field in sent else UNSET for field in SetPlayback.model_fields},
    )
    return _one_wall(services, wall_id)


@router.post("/walls/{wall_id}/labels")
def add_label(request: Request, wall_id: str, body: AddLabel) -> LabelAssignmentOut:
    """Caption this wall with a client's label output, by the name the client reports. A wall may have several."""
    services = _services(request)
    assignment = services.clients.add_label(wall_id, client_id=body.client_id, output=body.output)
    return LabelAssignmentOut(wall=_one_wall(services, wall_id), label_id=assignment.label.id, notice=assignment.notice)


@router.delete("/walls/{wall_id}/labels/{label_id}")
def remove_label(request: Request, wall_id: str, label_id: str) -> WallOut:
    """Stop a label output captioning this wall. The label output stays recorded, captioning nothing."""
    services = _services(request)
    services.clients.remove_label(wall_id, label_id=label_id)
    return _one_wall(services, wall_id)


@router.delete("/walls/{wall_id}/client")
def unassign_wall(request: Request, wall_id: str) -> WallOut:
    """Take the wall off whichever client showed it. Its theme stays hung."""
    services = _services(request)
    services.clients.unassign_wall(wall_id)
    return _one_wall(services, wall_id)


@router.delete("/walls/{wall_id}/theme")
def clear_wall(request: Request, wall_id: str) -> WallOut:
    """Take down whatever is hanging, leaving the wall holding nothing.

    Returns the wall, because the interesting change is what it now shows — the
    read-back-after-mutate shape the theme-membership routes already take, for
    the same reason and recorded as the same known departure.

    The wall keeps showing what it was showing until something else is hung: no
    manifest is rewritten, because publishing an empty one would blank the wall
    as a side effect of tidying up.
    """
    services = _services(request)
    services.display.clear_wall(wall_id)
    return _one_wall(services, wall_id)


@router.post("/walls/{wall_id}/selection")
def hang_selection(request: Request, wall_id: str, body: HangSelection) -> ManifestOut:
    """Hang one or more chosen works on this wall, until something else is hung there.

    Answers with the build, as hanging a theme does: what reached the wall, and
    every work that did not, with why.
    """
    return _manifest(_services(request).display.hang_selection(body.artwork_ids, wall_id=wall_id))


@router.post("/walls/{wall_id}/not-again")
def not_this_one_again(request: Request, wall_id: str, body: NotAgainRequest) -> NotAgainOut:
    """*Not this one again*, from this theme (`scope=theme`) or from every wall (`scope=every_wall`).

    From this theme takes the work out of what hangs on this wall. From every
    wall keeps it off every wall until allowed again, and the work stays held.
    Either way the walls carrying it lose it now. Answers with the wall as it
    now stands, read back after the act, for the reason `clear_wall` gives.
    """
    services = _services(request)
    done = services.display.not_this_one_again(body.artwork_id, wall_id=wall_id, scope=body.scope)
    return NotAgainOut(
        scope=str(done.scope),
        artwork_id=done.artwork_id,
        wall=_one_wall(services, wall_id),
        left_theme=None if done.left_theme is None else _theme(done.left_theme),
        excluded_at=None if done.exclusion is None else done.exclusion.excluded_at.isoformat(),
    )


@router.post("/walls/{wall_id}/next")
def step_wall(request: Request, wall_id: str) -> NextOut:
    """Move one wall on to the next work: the Walls screen's Skip.

    A republish of the wall's feed starting now, so its Player shows the work
    when it next reads the feed. The answer names that work; it is what was
    published, not a report from the screen.
    """
    return NextOut(wall_id=wall_id, work_id=_services(request).display.step_display(wall_id))


def _walls(services: Services) -> WallListOut:
    """Every wall's answer, from one reading taken now (`HealthService.observe_walls`)."""
    now = services.health.observe_walls()
    return WallListOut(walls=[_wall(services, view, now) for view in now.views])


def _one_wall(services: Services, wall_id: str) -> WallOut:
    """One wall's answer, from a reading of it taken now: after the act that answers with it has written."""
    now = services.health.observe_walls(wall_id)
    [view] = now.views
    return _wall(services, view, now)


def _wall(services: Services, view: WallView, now: WallsNow) -> WallOut:
    """One wall's answer, every part of it from `now`, the one reading `view` was built from.

    **One answer, one reading** (`HealthService.observe_walls`): the display
    state, the wait, who shows the wall, its display and its labels, and
    whether its Player reads the feed. Read apart, a report or an assignment
    landing between two reads made one answer say two instants: the wall
    waiting beside a badge showing a work, or unassigned beside the Player
    that shows it.
    """
    survey = now.survey
    placement = survey.placement_of(view.wall)
    return WallOut(
        wall_id=view.wall.id,
        name=view.wall.name,
        created_at=view.wall.created_at.isoformat(),
        theme=None if view.hanging is None else _theme(view.hanging),
        reads_feed=view.reads_feed,
        feed_notice=feed_notice(reads_feed=view.reads_feed),
        client_id=None if placement.client is None else placement.client.id,
        output=placement.output,
        display_id=view.wall.display_id,
        display=None if placement.display is None else _display(placement.display, survey),
        labels=[
            WallLabelOut(
                label_id=label.id,
                client_id=label.client_id,
                client_name=survey.clients[label.client_id].name if label.client_id in survey.clients else "",
                output=label.output,
            )
            for label in placement.labels
        ],
        display_state=_display_state(view.display_state),
        mat_mode=view.wall.mat_mode,
        rotation_interval_seconds=view.wall.rotation_interval_seconds,
        shuffle=view.wall.shuffle,
        **_shape_fields(view.wall),
        **_size_fields(services.display.judge_sizes_of(view.wall)),
        last_shown=None if view.last_shown is None else _last_shown(view.last_shown),
        upcoming=[UpcomingOut(work_id=slot.work_id, starts_at=slot.start.isoformat()) for slot in view.upcoming],
        waiting_for=_wall_wait(now.waiting.get(view.wall.id)),
        report_problem=now.report_problems.get(view.wall.id),
    )


def _last_shown(showing: Showing) -> LastShownOut:
    until = showing.ended_at if showing.ended_at is not None else showing.last_seen_at
    return LastShownOut(
        work_id=showing.work_id,
        started_at=showing.started_at.isoformat(),
        until=until.isoformat(),
        ended=showing.ended_at is not None,
    )


def _shape_fields(wall: Wall) -> dict[str, Any]:
    """The shapes a wall shows, as `WallOut` carries them: each bound spoken, and the range as a phrase."""
    return {
        "tallest": None if wall.min_aspect_ratio is None else shape.spoken(wall.min_aspect_ratio),
        "widest": None if wall.max_aspect_ratio is None else shape.spoken(wall.max_aspect_ratio),
        "shapes": shape.described(wall.min_aspect_ratio, wall.max_aspect_ratio) or None,
    }


def _size_fields(judgement: SizeJudgement) -> dict[str, Any]:
    """A wall's size judgement as `WallOut` carries it: the works, and what they were judged against or why not."""
    return {
        "too_small": sorted(judgement.too_small),
        "sizes_judged_against": (
            None
            if judgement.screen is None
            else ScreenSizeOut(
                width_px=judgement.screen[0],
                height_px=judgement.screen[1],
                shape=shape.spoken(judgement.screen[0] / judgement.screen[1]),
            )
        ),
        "sizes_unjudged": None if judgement.unjudged is None else judgement.unjudged.value,
    }


def _display(display: Display, survey: PlacementSurvey) -> DisplayOut:
    fault = survey.faults.get(display.identity)
    wall = next((wall for wall in survey.walls if wall.display_id == display.id), None)
    return DisplayOut(
        display_id=display.id,
        identity=display.identity,
        kind=display.kind,
        client_id=display.client_id,
        output=display.output,
        first_seen=display.first_seen.isoformat(),
        wall_id=None if wall is None else wall.id,
        fault=None if fault is None else _fault(fault),
    )


def _fault(fault: DisplayFault) -> DisplayFaultOut:
    return DisplayFaultOut(
        identity=fault.identity,
        clients=[ClientNameOut(client_id=client.id, name=client.name) for client in fault.clients],
        display_id=None if fault.display is None else fault.display.id,
        wall_id=None if fault.wall is None else fault.wall.id,
        description=fault.describe(),
    )


def _display_state(shown: DisplayState) -> DisplayStateOut:
    last = shown.last
    return DisplayStateOut(
        state=str(shown.state),
        work_id=shown.work_id,
        since=_instant(shown.since),
        reported_at=_instant(shown.reported_at),
        age_seconds=shown.age_seconds,
        last=None if last is None else ReportedStateOut(state=str(last.state), work_id=last.work_id, since=_instant(last.since)),
    )


def _wall_wait(wait: WallWait | None) -> WallWaitOut | None:
    return (
        None if wait is None else WallWaitOut(client_id=wait.client_id, name=wait.name, state=str(wait.state), words=wait.words)
    )
