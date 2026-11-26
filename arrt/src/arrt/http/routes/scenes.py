"""The routes for scenes: drafting one across walls, pinning, applying, releasing and discarding.

A scene is a work per wall, applied together over each wall's schedule (`player-contract.md` § Scenes).
Each route is one `DisplayService` act; the answer is the scene read back, with each wall's work and
whether the wall's heartbeat reports the scene."""

from fastapi import APIRouter, Request

from arrt.http.models import ApplyScene, PinScene, SceneOut, ScenesOut, SceneWallOut
from arrt.http.routes.common import API_PREFIX, _services
from arrt.programming.display import SceneView
from arrt.services.container import Services

router = APIRouter(prefix=API_PREFIX)


@router.get("/scenes/live")
def get_scenes(request: Request) -> ScenesOut:
    """The scene on the walls now and the one being assembled, either null."""
    return _scenes(_services(request))


@router.post("/scenes")
def draft_scene(request: Request) -> SceneOut:
    """Start assembling a scene, or answer with the one already being assembled."""
    services = _services(request)
    return _scene(services, services.display.draft_scene())


@router.put("/scenes/{scene_id}/pins/{wall_id}")
def pin_scene(request: Request, scene_id: str, wall_id: str, body: PinScene) -> SceneOut:
    """Put a work on a wall in the scene being assembled, and stage it there. Refused as show now refuses."""
    services = _services(request)
    return _scene(services, services.display.pin_scene(scene_id, wall_id, body.work_id))


@router.delete("/scenes/{scene_id}/pins/{wall_id}")
def unpin_scene(request: Request, scene_id: str, wall_id: str) -> SceneOut:
    """Take a wall out of the scene being assembled, and stop staging its work."""
    services = _services(request)
    return _scene(services, services.display.unpin_scene(scene_id, wall_id))


@router.post("/scenes/{scene_id}/apply")
def apply_scene(request: Request, scene_id: str, body: ApplyScene) -> SceneOut:
    """Show the scene on every wall it pins, now, ending any other live scene."""
    services = _services(request)
    return _scene(services, services.display.apply_scene(scene_id, lifetime=body.lifetime, minutes=body.minutes))


@router.post("/scenes/{scene_id}/release")
def release_scene(request: Request, scene_id: str) -> SceneOut:
    """End a live scene now; each wall returns to its schedule where the schedule is now."""
    services = _services(request)
    return _scene(services, services.display.release_scene(scene_id))


@router.delete("/scenes/{scene_id}")
def discard_scene(request: Request, scene_id: str) -> ScenesOut:
    """Forget a scene being assembled, and stop staging its works. Answers with what is left."""
    services = _services(request)
    services.display.discard_scene(scene_id)
    return _scenes(services)


def _scene(services: Services, view: SceneView) -> SceneOut:
    scene = view.scene
    return SceneOut(
        scene_id=scene.id,
        status=str(scene.status),
        lifetime=None if scene.lifetime is None else str(scene.lifetime),
        starts_at=None if scene.starts_at is None else scene.starts_at.isoformat(),
        until=None if scene.until is None else scene.until.isoformat(),
        ended_at=None if scene.ended_at is None else scene.ended_at.isoformat(),
        walls=[
            SceneWallOut(
                wall_id=wall.wall_id,
                wall_name=wall.wall_name,
                work_id=wall.work_id,
                title=wall.title,
                reached=wall.reached,
                cannot_show=wall.cannot_show,
                screen=str(wall.screen),
            )
            for wall in services.display.scene_walls(view)
        ],
    )


def _scenes(services: Services) -> ScenesOut:
    live, draft = services.display.live_scene(), services.display.scene_draft()
    return ScenesOut(
        live=None if live is None else _scene(services, live),
        draft=None if draft is None else _scene(services, draft),
    )
