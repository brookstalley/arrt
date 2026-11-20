"""Scenes: a work per wall, assembled as a draft, then applied together over each wall's schedule.

`Scenes` is the draft and its pins, applying, releasing and running out, and
what each wall in a scene is doing (`scene_walls`). `DisplayService`
(`display.py`) composes it and delegates to it; every surface still calls
`services.display`.

A scene reaches a wall through its feed, whose control layer the one
`FeedPublisher` the facade built derives (`feeds.py`).

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Final

from arrt.library.facade import (
    EventKind,
    LibraryFacade,
    PlayableWork,
    ProgrammingAct,
    Unplayable,
)
from arrt.persistence.records import (
    Scene,
    SceneEnding,
    SceneLifetime,
    ScenePin,
    SceneStatus,
    Wall,
)
from arrt.programming.display_state import ScreenState
from arrt.programming.feeds import FeedPublisher, applied_at
from arrt.programming.lookups import Lookups
from arrt.programming.manifest import heartbeat
from arrt.programming.settings import DisplaySettings
from arrt.programming.store import ProgrammingStore
from arrt.programming.themes import Themes
from arrt.programming.walls import Walls
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member
from arrt.services.store import store_write

#: Named for the module these lines were said from before it had a module of its
#: own, and kept, for the reason `feeds.py` gives: a logger's name is what a
#: reader of the journal filters on.
log = logging.getLogger("arrt.programming.display")


@dataclass(frozen=True, slots=True)
class SceneView:
    """A scene and its pins, as one read found them."""

    scene: Scene
    pins: Sequence[ScenePin]

    @property
    def wall_ids(self) -> list[str]:
        return [pin.wall_id for pin in self.pins]


@dataclass(frozen=True, slots=True)
class SceneWall:
    """One wall in a scene, as Walls shows it: its work, and whether it has reached the scene.

    `reached` is the wall's own word: its last heartbeat names this scene
    (`player-contract.md` § The heartbeat, minor 2, `scene_id`). Never stored,
    because whether a wall reached a scene is the wall's runtime state.
    """

    wall_id: str
    wall_name: str
    work_id: str
    #: The work's title as the Library gives it; None for an id it does not hold.
    title: str | None
    reached: bool
    #: Why the wall cannot show its work in the scene now, in the Library's or
    #: the curator's words, or None. A work archived or kept off every wall
    #: after it was pinned leaves the wall's feed, so the wall shows its
    #: schedule; it returns if the work is restored or allowed again.
    cannot_show: str | None
    #: What the wall's screen is doing now, so a wall not there yet can say why:
    #: `in_use` is somebody watching television, and the Player waits for it.
    screen: ScreenState


#: A scene just ended, its pins, how, and the words its journal line says.
type _Ended = tuple[Scene, Sequence[ScenePin], SceneEnding, str]


class Scenes:
    """Assemble, apply and release scenes, and say where each wall is in one."""

    def __init__(
        self,
        store: ProgrammingStore,
        library: LibraryFacade,
        settings: DisplaySettings,
        lookups: Lookups,
        feeds: FeedPublisher,
        themes: Themes,
        walls: Walls,
    ) -> None:
        self._store = store
        self._library = library
        self._settings = settings
        #: The facade's one set of lookups (`lookups.py`).
        self._lookups = lookups
        self._feeds = feeds
        self._themes = themes
        self._walls = walls

    # -- scenes ---------------------------------------------------------------
    #
    # A scene is a work per wall, applied together over each wall's schedule
    # (`player-contract.md` § Scenes). While a draft, each pin stages its work
    # on its wall, so a Frame has its upload done before Apply and the walls
    # switch together. Every act writes the store, then patches each wall it
    # touched: the schedule is republished exactly as it stands, and the one
    # feed writer derives the control layer (`FeedPublisher._publish_feed`). Expiry is
    # observed, not scheduled: a Player returns to its schedule at `until` on
    # its own, so the server keeps no timer.

    def draft_scene(self) -> SceneView:
        """The scene being assembled: the one already started, else a new empty one.

        One draft at a time, because the builder on Walls holds one; the store
        would take more, and only the newest stages anything (`Lookups.current_draft`).
        """
        with self._store.transaction():
            ended = self.settle_scenes()
            draft = self._lookups.current_draft()
            if draft is None:
                draft = Scene(id=str(uuid.uuid4()), status=SceneStatus.DRAFT, created_at=datetime.now(UTC))
                store_write(self._store.add_scene, draft)
            view = self._scene_view(draft)
        self.record_ended(ended)
        return view

    def pin_scene(self, scene_id: str, wall_id: str, artwork_id: str) -> SceneView:
        """Put this work on this wall in the draft, replacing the wall's earlier pick, and stage it there.

        **Refused as show now refuses**, in its words: a work the Library will
        not show, or one kept off every wall. Refused too for a wall with no
        feed, whose Player has nothing to show a scene over. A refusal changes
        nothing in the draft.
        """
        # Every check inside the act, so a work kept off every wall or a wall
        # deleted meanwhile is refused rather than pinned.
        with self._feeds.publishing():
            wall = self._lookups.get_wall(wall_id)
            answer = self._themes.require_showable(artwork_id)
            scene = self._require_scene(scene_id, SceneStatus.DRAFT)
            if self._feeds.published(wall_id) is None:
                raise ServiceError(
                    f"Nothing has been hung on {wall.name!r} yet, so it has no feed to show a scene over. "
                    "Hang a theme there first."
                )
            store_write(self._store.set_pin, ScenePin(scene_id=scene.id, wall_id=wall_id, work_id=answer.work_id))
            self._feeds.patch_walls([wall_id])
        _log_scene("staged", scene_id, [wall_id], f"staging {answer.work_id} on wall {wall.name!r}")
        return self.get_scene(scene_id)

    def unpin_scene(self, scene_id: str, wall_id: str) -> SceneView:
        """Take this wall out of the draft and stop staging its work there."""
        with self._feeds.publishing():
            wall = self._lookups.get_wall(wall_id)
            self._require_scene(scene_id, SceneStatus.DRAFT)
            store_write(self._store.remove_pin, scene_id, wall_id)
            self._feeds.patch_walls([wall_id])
        _log_scene("unstaged", scene_id, [wall_id], f"nothing staged on wall {wall.name!r} any more")
        return self.get_scene(scene_id)

    def discard_scene(self, scene_id: str) -> None:
        """Forget a draft, and stop staging its works."""
        with self._feeds.publishing():
            self._require_scene(scene_id, SceneStatus.DRAFT)
            walls = [pin.wall_id for pin in self._store.list_pins(scene_id)]
            for wall_id in walls:
                store_write(self._store.remove_pin, scene_id, wall_id)
            store_write(self._store.remove_scene, scene_id)
            self._feeds.patch_walls(walls)
        _log_scene("discarded", scene_id, walls, "discarded before it was applied")

    def apply_scene(self, scene_id: str, *, lifetime: SceneLifetime | str, minutes: int | None = None) -> SceneView:
        """Show the draft on every wall it pins, now: for `minutes` as a preview, or until released as a hold.

        A preview with no length is `PREVIEW_MINUTES` long. **Any other live
        scene ends**, because a wall shows one scene and the builder offers one.
        Each pin is checked again as it was when made, and a refusal names its
        wall and applies nothing.
        """
        chosen = SceneLifetime(require_member(lifetime, enum=SceneLifetime, field="lifetime"))
        if chosen is SceneLifetime.HOLD and minutes is not None:
            raise ServiceError("A held scene stays until it is released, so it takes no length.")
        length = PREVIEW_MINUTES if minutes is None else minutes
        if chosen is SceneLifetime.PREVIEW and length <= 0:
            raise ServiceError(f"A preview must last at least a minute, got {length}.")
        if chosen is SceneLifetime.PREVIEW and length > MAX_PREVIEW_MINUTES:
            raise ServiceError(
                f"A preview lasts at most {MAX_PREVIEW_MINUTES} minutes, got {length}. Hold the scene to keep it longer."
            )
        with self._feeds.publishing():
            ended = self.settle_scenes()
            scene = self._require_scene(scene_id, SceneStatus.DRAFT)
            pins = self._store.list_pins(scene_id)
            if not pins:
                raise ServiceError("This scene has no walls in it yet. Pick a work for a wall first.")
            for pin in pins:
                wall = self._lookups.get_wall(pin.wall_id)
                try:
                    self._themes.require_showable(pin.work_id)
                except ServiceError as refusal:
                    raise ServiceError(f"{wall.name}: {refusal}") from refusal
            now = datetime.now(UTC)
            ended += [
                self._end(other, at=now, how=SceneEnding.REPLACED, words=f"replaced by scene {scene_id}")
                for other in self._store.list_scenes(SceneStatus.LIVE)
                if other.status_at(now) is SceneStatus.LIVE
            ]
            applied = replace(
                scene,
                status=SceneStatus.LIVE,
                lifetime=chosen,
                starts_at=now,
                until=now + timedelta(minutes=length) if chosen is SceneLifetime.PREVIEW else None,
            )
            store_write(self._store.update_scene, applied)
            walls = [pin.wall_id for pin in pins]
            replaced = (pin.wall_id for _, ended_pins, how, _ in ended if how is SceneEnding.REPLACED for pin in ended_pins)
            self._feeds.patch_walls([*walls, *replaced])
        self.record_ended(ended)
        self._record_scene(EventKind.SCENE_APPLIED, applied, pins, lifetime=str(chosen), until=_iso(applied.until))
        _log_scene(
            "applied",
            scene_id,
            walls,
            f"applied on {self._wall_names(walls)}, "
            + (f"until {applied.until.isoformat()}" if applied.until else "held until released"),
        )
        return self.get_scene(scene_id)

    def release_scene(self, scene_id: str) -> SceneView:
        """End a live scene now; each of its walls returns to its schedule where the schedule is now."""
        with self._feeds.publishing():
            ended = self.settle_scenes()
            scene = self._require_scene(scene_id, SceneStatus.LIVE)
            released = self._end(scene, at=datetime.now(UTC), how=SceneEnding.RELEASED, words="released")
            self._feeds.patch_walls(pin.wall_id for pin in released[1])
        self.record_ended([*ended, released])
        return self.get_scene(scene_id)

    def live_scene(self) -> SceneView | None:
        """The scene on the walls now, or None. A preview whose end has passed is not live, written or not."""
        now = datetime.now(UTC)
        with self._store.reading():
            live = [scene for scene in self._store.list_scenes(SceneStatus.LIVE) if scene.status_at(now) is SceneStatus.LIVE]
            return self._scene_view(max(live, key=applied_at)) if live else None

    def scene_draft(self) -> SceneView | None:
        """The scene being assembled, or None."""
        with self._store.reading():
            draft = self._lookups.current_draft()
            return None if draft is None else self._scene_view(draft)

    def get_scene(self, scene_id: str) -> SceneView:
        """A scene and its pins, with its status as of now."""
        with self._store.reading():
            scene = self._store.get_scene(scene_id)
            if scene is None:
                raise ServiceError(f"No scene with id {scene_id!r}.")
            return self._scene_view(scene)

    def scene_walls(self, view: SceneView) -> list[SceneWall]:
        """Each wall a scene pins, with its work and whether its last heartbeat reports the scene.

        The walls, the exclusions and each screen are read in one scope, and each
        wall from the one listing that decides which pins are on held walls: a
        wall deleted between that listing and a read of its own was asserted
        present, and the answer was a fault (C2).
        """
        walls: list[SceneWall] = []
        answers = self._library.playable(sorted({pin.work_id for pin in view.pins}))
        with self._store.reading():
            kept_off = {exclusion.artwork_id for exclusion in self._store.list_exclusions()}
            for pin, wall in self._held_walls(view.pins):
                contents = heartbeat.read(self._settings.heartbeat_path(wall.id)).contents or {}
                walls.append(
                    SceneWall(
                        wall_id=wall.id,
                        wall_name=wall.name,
                        work_id=pin.work_id,
                        title=answers[pin.work_id].title if pin.work_id in answers else None,
                        reached=contents.get("scene_id") == view.scene.id,
                        cannot_show=_cannot_show(answers.get(pin.work_id), kept_off=pin.work_id in kept_off),
                        screen=self._walls.display_state(wall).state,
                    )
                )
        return walls

    def _scene_view(self, scene: Scene) -> SceneView:
        now = datetime.now(UTC)
        if scene.status_at(now) is not scene.status:
            scene = replace(scene, status=scene.status_at(now), ended_at=scene.until)
        return SceneView(scene=scene, pins=tuple(self._store.list_pins(scene.id)))

    def _require_scene(self, scene_id: str, status: SceneStatus) -> Scene:
        scene = self._store.get_scene(scene_id)
        if scene is None:
            raise ServiceError(f"No scene with id {scene_id!r}.")
        actual = scene.status_at(datetime.now(UTC))
        if actual is not status:
            raise ServiceError(_SCENE_NOT[status].format(status=actual.value))
        return scene

    def _end(self, scene: Scene, *, at: datetime, how: SceneEnding, words: str) -> _Ended:
        """Write a live scene's end and return it with its pins: the one place a scene ends.

        Released or replaced ends it now; a preview run out ends it at its
        `until`. The caller republishes the walls, or, for a preview run out,
        leaves them: their Players returned to the schedule on their own. The
        caller says it and records it in History once its transaction commits
        (`record_ended`), so a refusal that rolls the end back leaves no line
        claiming it.
        """
        ended = replace(scene, status=SceneStatus.ENDED, ended_at=at)
        store_write(self._store.update_scene, ended)
        return ended, self._store.list_pins(scene.id), how, words

    def record_ended(self, ended: Iterable[_Ended]) -> None:
        """Say each scene's end in the journal and History, with when it ended, once the end has committed."""
        for scene, pins, how, words in ended:
            walls = [pin.wall_id for pin in pins]
            _log_scene(how.event.removeprefix("scene."), scene.id, walls, f"{words} on {self._wall_names(walls)}")
            # When it ended, not when this line is written: a preview noticed
            # after a restart ended at its `until`, while the server was down.
            self._record_scene(EventKind.SCENE_ENDED, scene, pins, how=str(how), ended_at=_iso(scene.ended_at))

    def _record_scene(self, kind: EventKind, scene: Scene, pins: Sequence[ScenePin], **detail: object) -> None:
        """One History line per wall a scene pins, naming the wall's work, with the words it is read by."""
        titles = {
            work_id: answer.title
            for work_id, answer in self._library.playable(sorted({pin.work_id for pin in pins})).items()
            if isinstance(answer, PlayableWork)
        }
        # Each wall from the one listing that decides which are held, for the
        # reason `scene_walls` gives: this runs after its act commits, and a wall
        # deleted meanwhile failed an act that had already happened.
        for pin, wall in self._held_walls(pins):
            words: dict[str, object] = {"scene_id": scene.id, **detail, "wall_name": wall.name}
            if pin.work_id in titles:
                words["title"] = titles[pin.work_id]
            self._library.record(ProgrammingAct(kind=kind, wall_id=pin.wall_id, work_id=pin.work_id, detail=words))

    def settle_scenes(self) -> list[_Ended]:
        """Write down that each preview whose `until` has passed has ended, as of that `until`.

        Nothing about the walls changes: each Player returned to its schedule
        at `until` on its own, and the expired scene left in its feed until the
        next write is contract-valid and ignored. This only makes the store and
        the journal say so.
        """
        now = datetime.now(UTC)
        return [
            self._end(scene, at=scene.until, how=SceneEnding.RAN_OUT, words=f"ran out at {scene.until.isoformat()}")
            for scene in self._store.list_scenes(SceneStatus.LIVE)
            if scene.status_at(now) is SceneStatus.ENDED and scene.until is not None
        ]

    def _held_walls(self, pins: Iterable[ScenePin]) -> list[tuple[ScenePin, Wall]]:
        """The pins whose wall the store still holds, each with that wall, from one listing of the walls.

        A wall deleted while a scene was live leaves its pin as the scene's record
        (`delete_wall`), and has left the scene: it is shown nothing, named in no
        new history line, and its feed, removed with it, is not republished.
        Every path that acts on a scene's pins takes them through here, so none
        meets the deleted wall in a way of its own. Each wall comes from the
        listing that decided it is held, never from a read of its own after it,
        which a delete could land before (C2).
        """
        held = {wall.id: wall for wall in self._store.list_walls()}
        return [(pin, held[pin.wall_id]) for pin in pins if pin.wall_id in held]

    def _wall_names(self, wall_ids: Iterable[str]) -> str:
        held = {wall.id: wall.name for wall in self._store.list_walls()}
        return ", ".join(repr(held[wall_id]) for wall_id in wall_ids if wall_id in held) or "no wall"


#: How long a preview lasts when nobody says (the owner, 2026-10-08, confirmed 2026-10-26).
PREVIEW_MINUTES: Final[int] = 20


#: The longest preview: a day. Longer is what a hold is for, and a bound keeps
#: an agent's length from overflowing the date arithmetic into a fault.
MAX_PREVIEW_MINUTES: Final[int] = 24 * 60


#: What `_require_scene` says when a scene is not in the state an act needs.
_SCENE_NOT: Final[Mapping[SceneStatus, str]] = {
    SceneStatus.DRAFT: "That scene is {status}, not being assembled, so its walls cannot be changed.",
    SceneStatus.LIVE: "That scene is {status}, not on the walls, so there is nothing to release.",
    SceneStatus.ENDED: "That scene is {status}.",
}


def _cannot_show(answer: PlayableWork | Unplayable | None, *, kept_off: bool) -> str | None:
    """Why a scene's wall cannot show its work now, in words, or None when it can."""
    if kept_off:
        return "It is kept off every wall."
    if answer is None:
        return "The Library does not hold it."
    return None if isinstance(answer, PlayableWork) else answer.detail


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def _log_scene(act: str, scene_id: str, wall_ids: Sequence[str], words: str) -> None:
    """Say one act on a scene, naming its walls, under the event `scene.<act>`.

    Every act that changes what a wall stages or shows says so, because a Frame
    uploading or evicting a work nobody hung is otherwise a mystery in the journal.
    """
    log.info("Scene %s: %s.", scene_id, words, extra={"event": f"scene.{act}", "scene_id": scene_id, "wall_ids": list(wall_ids)})
