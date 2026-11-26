"""The routes for themes: list, create, edit, delete, the works in one, and hanging one on walls."""

from fastapi import APIRouter, Request

from arrt.http.models import (
    AddWork,
    CreateTheme,
    EditTheme,
    HangTheme,
    ManifestOut,
    MoveWork,
    ThemeAdditionOut,
    ThemeDetailOut,
    ThemeListOut,
    ThemeOut,
    ThemeRemovalOut,
    ThemeSummaryOut,
    WorkSelection,
)
from arrt.http.routes.common import API_PREFIX, _services
from arrt.http.routes.manifest import _manifest
from arrt.http.routes.shapes import _placement, _theme, _work
from arrt.http.routes.works import _selected_ids
from arrt.library.services.thumbnails import ThumbnailUnavailable
from arrt.programming.display import UNSET, ThemePlacement
from arrt.services.container import Services

router = APIRouter(prefix=API_PREFIX)


@router.get("/themes")
def list_themes(request: Request) -> ThemeListOut:
    """Every theme, and the walls each is hanging on."""
    return _theme_list(_services(request))


@router.get("/themes/{theme_id}")
def get_theme(request: Request, theme_id: str) -> ThemeDetailOut:
    """A theme and the works it holds, in curated order."""
    return _theme_detail(_services(request), theme_id)


@router.post("/themes")
def create_theme(request: Request, body: CreateTheme) -> ThemeOut:
    """Record a theme."""
    return _theme(_services(request).display.add_theme(name=body.name, description=body.description))


@router.post("/themes/{theme_id}")
def edit_theme(request: Request, theme_id: str, body: EditTheme) -> ThemeOut:
    """Change a theme's name, and its description when the body names one.

    **`POST` rather than `PATCH`**, following this surface's own convention: it
    writes with `POST` and removes with `DELETE`, and one surface with two
    spellings for "change this" costs more than the orthodoxy is worth.

    Answers with the theme, so the screen repaints the name it now has rather
    than the one it sent. Those differ whenever the service normalises — a name
    surrounded by whitespace comes back trimmed — and a screen painting its own
    input would show a name the catalogue does not hold.
    """
    description = body.description if "description" in body.model_fields_set else UNSET
    return _theme(_services(request).display.update_theme(theme_id, name=body.name, description=description))


@router.delete("/themes/{theme_id}")
def delete_theme(request: Request, theme_id: str) -> ThemeListOut:
    """Remove a theme and its membership rows. The works themselves are untouched.

    **The refusal is the service's, not this handler's.** `delete_theme` refuses
    a theme hanging on any wall and names the walls, and the same rule reaches
    `art_theme(action='delete')`; a guard written here would be a second copy for
    a click and an agent to disagree over. What arrives is a 400 carrying a
    sentence written to be shown, by the same path every other refusal takes.

    Answers with the themes that remain, because what a delete changes is the
    list it was performed from — and the alternative, an empty 204, would leave
    the screen re-reading a listing it has just been told the shape of.
    """
    services = _services(request)
    services.display.delete_theme(theme_id)
    return _theme_list(services)


@router.post("/themes/{theme_id}/default")
def make_default_theme(request: Request, theme_id: str) -> ThemeListOut:
    """Make this the theme new works join, taking the mark off whichever had it.

    Answers with every theme, because the act changes two of them: the one
    marked and the one that stopped being.
    """
    services = _services(request)
    services.display.make_default(theme_id)
    return _theme_list(services)


@router.post("/themes/{theme_id}/works")
def add_to_theme(request: Request, theme_id: str, body: AddWork) -> ThemeDetailOut:
    """Place a work in a theme, and return the order that results.

    The membership alone would be a truthful answer and a useless one: a curator
    reordering a theme is looking at the list, and returning the list is what
    lets the surface repaint from the response instead of guessing where the
    work landed and then asking.
    """
    services = _services(request)
    services.display.add_to_theme(theme_id=theme_id, artwork_id=body.artwork_id, position=body.position)
    return _theme_detail(services, theme_id)


@router.post("/themes/{theme_id}/works/bulk")
def add_selection_to_theme(request: Request, theme_id: str, body: WorkSelection) -> ThemeAdditionOut:
    """Put a selection at the end of a theme, in the order its listing shows it.

    The selection is by id or by a filter, so *Select all* on Artworks reaches
    every work the filter matches rather than the ones loaded. Works the theme
    already holds are passed over and counted; one transaction.
    """
    services = _services(request)
    added, already = services.display.add_works_to_theme(theme_id=theme_id, artwork_ids=_selected_ids(services, body))
    return ThemeAdditionOut(added=added, already=already)


@router.post("/themes/{theme_id}/works/remove")
def remove_selection_from_theme(request: Request, theme_id: str, body: WorkSelection) -> ThemeRemovalOut:
    """Take a selection out of a theme, by id or by a filter, and say which works left."""
    services = _services(request)
    removed = services.display.remove_works_from_theme(theme_id=theme_id, artwork_ids=_selected_ids(services, body))
    return ThemeRemovalOut(removed=list(removed))


@router.delete("/themes/{theme_id}/works/{artwork_id}")
def remove_from_theme(request: Request, theme_id: str, artwork_id: str) -> ThemeDetailOut:
    """Take a work out of a theme, and every wall hanging it, and return the order that results."""
    services = _services(request)
    services.display.remove_from_theme(theme_id=theme_id, artwork_id=artwork_id)
    return _theme_detail(services, theme_id)


@router.post("/themes/{theme_id}/works/{artwork_id}/position")
def move_in_theme(request: Request, theme_id: str, artwork_id: str, body: MoveWork) -> ThemeDetailOut:
    """Move a work within a theme's curated order, and return that order."""
    services = _services(request)
    services.display.move_in_theme(theme_id=theme_id, artwork_id=artwork_id, position=body.position)
    return _theme_detail(services, theme_id)


@router.post("/themes/{theme_id}/activate")
def activate_theme(request: Request, theme_id: str, body: HangTheme) -> ManifestOut:
    """Hang this theme on the named wall, and publish the manifest that follows.

    Returns the build, so the curator sees what actually reached that wall in the
    same response that put it there — including everything that did not, and
    including the wall's own name.
    """
    return _manifest(_services(request).display.activate_theme(theme_id, wall_id=body.wall_id))


def _theme_detail(services: Services, theme_id: str) -> ThemeDetailOut:
    """A theme with its works, in curated order."""
    theme = services.display.get_theme(theme_id)
    return ThemeDetailOut(
        theme=_theme(theme),
        # Two calls composed, as the MCP binding composes them: Programming's
        # order, and the Library's account of each work.
        works=[_work(entry) for entry in services.survey.survey_works(services.display.theme_work_ids(theme_id))],
        too_small_for={work_id: list(walls) for work_id, walls in services.display.too_small_for_walls(theme_id).items()},
        sizes_unjudged={
            name: judgement.unjudged.value
            for name, judgement in services.display.size_judgements(theme_id).items()
            if judgement.unjudged is not None
        },
    )


#: How many pictures a Themes index card draws. Enough to say what a theme looks
#: like at a glance, few enough that ten cards fit on one screen.
THEME_CARD_PICTURES = 4


def _theme_list(services: Services) -> ThemeListOut:
    """Every theme the index lists, each with what its card shows.

    Two sides of the seam composed, as `_theme_detail` composes them: Programming names
    each theme's works in order, and the Library says which of them has a
    picture. The pictures are looked for in curated order and the search stops
    at the fourth. What bounds the cost is the membership read, one per theme,
    plus one picture check per work until four are found: a few checks for a
    theme whose works hold images, and one per work only for a theme where
    almost none do. No work is surveyed in full, which is what reading every
    theme's detail would cost.
    """
    return ThemeListOut(themes=[_summary(services, placement) for placement in services.display.survey_themes()])


def _summary(services: Services, placement: ThemePlacement) -> ThemeSummaryOut:
    work_ids = services.display.theme_work_ids(placement.theme.id)
    pictured: list[str] = []
    for work_id in work_ids:
        if len(pictured) == THEME_CARD_PICTURES:
            break
        try:
            services.thumbnails.tile_source(work_id)
        except ThumbnailUnavailable:
            continue
        pictured.append(work_id)
    return ThemeSummaryOut(
        **_placement(placement).model_dump(),
        work_count=len(work_ids),
        picture_ids=pictured,
    )
