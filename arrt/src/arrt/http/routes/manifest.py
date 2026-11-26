"""The route for the manifest a Player reads, and the shaping of one."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from arrt.http.models import ExclusionOut, ManifestEntryOut, ManifestOut
from arrt.http.routes.common import API_PREFIX, _services
from arrt.http.routes.shapes import _theme
from arrt.programming.manifest.builder import ManifestBuild

router = APIRouter(prefix=API_PREFIX)


@router.get("/manifest")
def get_manifest(
    request: Request,
    wall_id: Annotated[str, Query()],
    theme_id: Annotated[str | None, Query()] = None,
) -> ManifestOut:
    """What a theme would put on one wall, and every work it would leave off.

    Evaluates without writing, so a curator can ask what would happen before
    changing what is on the wall. The wall is required and the theme is not:
    exclusions belong to a wall once two walls can hang different themes, and the
    theme defaults to whatever is already hanging there.
    """
    return _manifest(_services(request).display.build_manifest(wall_id, theme_id))


def _manifest(build: ManifestBuild) -> ManifestOut:
    return ManifestOut(
        wall_id=build.wall.id,
        wall_name=build.wall.name,
        theme=_theme(build.theme),
        entries=[
            ManifestEntryOut(
                artwork_id=entry.work_id,
                title=entry.label.get("title") or "",
                artist=entry.label.get("artist"),
            )
            for entry in build.entries
        ],
        exclusions=[
            ExclusionOut(
                artwork_id=exclusion.work_id,
                title=exclusion.title,
                reason=str(exclusion.reason),
                detail=exclusion.detail,
            )
            for exclusion in build.exclusions
        ],
        considered=build.considered,
        rotation_interval_seconds=build.rotation_interval_seconds,
        shuffle=build.shuffle,
        # The build's own sentence, not a second one written here: the tool
        # surface states the same fact, and two hand-written versions drift.
        summary=build.summarise(),
    )
