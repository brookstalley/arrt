"""The routes for works: the listing, one work's detail, identity, archive and restore, its mat, placements and pictures."""

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse

from arrt.http.models import (
    ArchivedWorksOut,
    FacetGroupOut,
    FacetOptionOut,
    MatColorOut,
    MatPresetOut,
    OriginalOut,
    RenditionOut,
    SetIdentity,
    SetWorkMat,
    SourceOut,
    ThemeOptionOut,
    WorkDetailOut,
    WorkFacetOut,
    WorkGetOut,
    WorkMatOut,
    WorkPageOut,
    WorkPlacementsOut,
    WorkSelection,
    WorksFilter,
)
from arrt.http.routes.acquisitions import _acquisition
from arrt.http.routes.common import API_PREFIX, THUMBNAIL_CACHE_CONTROL, _services
from arrt.http.routes.shapes import _placement, _work
from arrt.library.acquisition.preparation import MatRequest
from arrt.library.services.catalogue import FacetGroup, RenditionView
from arrt.library.services.survey import WorkDossier
from arrt.persistence.records import HistoryEvent, MatColor, Original, Source, WorkFacet
from arrt.programming.display import ThemeCount
from arrt.services import works_filter
from arrt.services.container import Services
from arrt.services.errors import ServiceError
from arrt.services.works_filter import FilterOption

router = APIRouter(prefix=API_PREFIX)


@router.get("/works")
def list_works(
    request: Request,
    status: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    artist: Annotated[list[str] | None, Query()] = None,
    movement: Annotated[list[str] | None, Query()] = None,
    era: Annotated[list[str] | None, Query()] = None,
    subject: Annotated[list[str] | None, Query()] = None,
    medium: Annotated[list[str] | None, Query()] = None,
    palette: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
    sort: Annotated[str | None, Query()] = None,
    artist_id: Annotated[str | None, Query()] = None,
    theme: Annotated[str | None, Query()] = None,
    fit: Annotated[list[str] | None, Query()] = None,
    not_on_wall: Annotated[bool, Query()] = False,  # noqa: FBT002 -- a query parameter FastAPI passes by name
    shown: Annotated[str | None, Query()] = None,
) -> WorkPageOut:
    """A page of works with the facet controls for exactly this filter.

    `q` is free text; every word must appear somewhere in the work's own text or
    its artist's name. **One repeatable parameter per facet kind** — `?movement=
    Baroque&movement=Rococo` means either, and adding `&era=17th+c.` means both.
    Repeated rather than comma-joined because a facet value may itself contain a
    comma, and a separator a value can hold is a parser that goes wrong on the
    data rather than on the request.

    The six are spelled out rather than gathered from the raw query string:
    FastAPI generates this route's schema from the signature, so a named
    parameter is what makes the filter set discoverable and an unknown one a
    stated refusal instead of a silent no-op.

    `theme` narrows to one theme's works, and every other filter and every facet
    count narrows within it. Two calls composed, as `_theme_detail` composes
    them: Programming names the theme's works, and the Library lists them. An
    unknown theme is refused by name rather than ignored, because ignoring it
    would answer with the whole catalogue labelled as the theme's.

    `fit` narrows to works whose size is in one of the bands named
    (`meets_minimum`, `below_minimum`, or `unknown` for a work with no
    master), `not_on_wall` to works no wall plays now, and `shown` to works
    no wall has shown in a period (`never`, `month`, `quarter`, `year`,
    `works_filter.SHOWN_PERIODS`). Each is counted like a facet, ignoring its
    own selection, and every other count narrows by them
    (`services/works_filter.py`).
    """
    services = _services(request)
    chosen = {"artist": artist, "movement": movement, "era": era, "subject": subject, "medium": medium, "palette": palette}
    facets = {kind: values for kind, values in chosen.items() if values}
    narrowing = works_filter.narrowing(
        services,
        status=status,
        q=q,
        facets=facets,
        artist_id=artist_id,
        theme=theme,
        fit=fit or [],
        not_on_wall=not_on_wall,
        shown=shown,
    )
    page = services.survey.list_works(
        status=status,
        q=q,
        facets=facets,
        limit=limit,
        offset=offset,
        sort=sort,
        artist_id=artist_id,
        within=narrowing.within(),
    )
    # The theme options, counted as the facets are, with the theme's own
    # selection ignored: the Library names what the other filters select, and
    # Programming counts each theme's members among them.
    return WorkPageOut(
        works=[_work(entry) for entry in page.entries],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        truncated=page.truncated,
        facets=[_facet_group(group) for group in page.facets],
        themes=[_theme_option(option) for option in services.display.theme_counts(narrowing.among(but="theme"), selected=theme)],
        fits=[_option(option) for option in narrowing.fit_options()],
        not_on_wall=_option(narrowing.off_wall_option()),
        shown=[_option(option) for option in narrowing.shown_options()],
    )


def _option(option: FilterOption) -> FacetOptionOut:
    return FacetOptionOut(value=option.value, count=option.count, selected=option.selected, disabled=option.disabled)


def _filtered_ids(services: Services, narrowing: WorksFilter) -> Sequence[str]:
    """Every work `narrowing` selects, in the order its listing shows them.

    Composed exactly as `list_works` composes it (`works_filter.narrowing`), so *Select all*
    acts on the works the grid beside it is counting.
    """
    chosen = {
        "artist": narrowing.artist,
        "movement": narrowing.movement,
        "era": narrowing.era,
        "subject": narrowing.subject,
        "medium": narrowing.medium,
        "palette": narrowing.palette,
    }
    facets = {kind: values for kind, values in chosen.items() if values}
    composed = works_filter.narrowing(
        services,
        status=narrowing.status,
        q=narrowing.q,
        facets=facets,
        artist_id=narrowing.artist_id,
        theme=narrowing.theme,
        fit=narrowing.fit,
        not_on_wall=narrowing.not_on_wall,
        shown=narrowing.shown,
    )
    return services.catalogue.matching_ids_in_order(
        status=narrowing.status,
        q=narrowing.q,
        facets=facets,
        artist_id=narrowing.artist_id,
        within=composed.within(),
        sort=narrowing.sort,
    )


def _selected_ids(services: Services, selection: WorkSelection) -> Sequence[str]:
    """The works a selection means, by id, with the ones it leaves out taken away."""
    if (selection.artwork_ids is None) == (selection.filter is None):
        raise ServiceError("Name the works either by their ids or by a filter, and not both.")
    named: Sequence[str]
    if selection.artwork_ids is not None:
        named = selection.artwork_ids
    else:
        assert selection.filter is not None  # noqa: S101 -- the check at the top refused ids and filter both unset
        named = _filtered_ids(services, selection.filter)
    leaving = set(selection.except_ids)
    return [artwork_id for artwork_id in dict.fromkeys(named) if artwork_id not in leaving]


@router.post("/works/archive")
def archive_works(request: Request, body: WorkSelection) -> ArchivedWorksOut:
    """Archive a selection: by id, or every work a filter matches.

    *Select all* on Artworks means every work the filter matches, loaded or
    not, so the filter travels rather than the ids the screen happens to hold.
    One transaction: an id the catalogue does not hold refuses the whole act.
    A work already archived is passed over and counted.
    """
    services = _services(request)
    ids = _selected_ids(services, body)
    archived = services.catalogue.archive_artworks(ids)
    return ArchivedWorksOut(archived=list(archived), already=len(ids) - len(archived))


@router.get("/works/{artwork_id}")
def get_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """One work in full — metadata, artist, sources, renditions and mats, and the Get it came from."""
    services = _services(request)
    return _work_detail(services, artwork_id)


@router.post("/works/{artwork_id}/wikidata")
def set_work_identity(request: Request, artwork_id: str, body: SetIdentity) -> WorkDetailOut:
    """Say which Wikidata item this work is, or that there is none.

    Answers with the dossier, the shape every act on the Work screen repaints
    from. The matcher never overwrites what is set here (`identity.py`).
    """
    services = _services(request)
    services.identity.set_work_identity(artwork_id, body.qid)
    return _work_detail(services, artwork_id)


@router.post("/works/{artwork_id}/archive")
def archive_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """Take a work out of circulation, keeping its record and its mat history.

    **Archive rather than delete, and the noun in the path is the whole point.**
    `Artwork.status` has two values and restoration is permitted, so there is no
    route here that destroys a work; `information-architecture.md` argues the
    label follows the route, and the control this binds to reads *Archive*.

    The work stays in every theme that holds it — membership is curatorial and
    readiness is technical — and every wall's feed loses it as the archive
    lands. A standing pin naming this work is withdrawn in the same
    transaction, without advancing the sequence; both rules belong to the
    catalogue service and are not restated here.

    Returns the dossier, which is the same shape `GET /api/works/{id}` answers
    with: the interesting change is the work's whole state, the screen that
    archives is the screen that shows it, and a slimmer body would send that
    screen straight back for the rest. The read-back-after-mutate departure the
    theme routes take, for the same reason.
    """
    services = _services(request)
    services.catalogue.archive_artwork(artwork_id)
    return _work_detail(services, artwork_id)


@router.post("/works/{artwork_id}/restore")
def restore_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """Return an archived work to circulation.

    The undo of `archive_work`, and its existence is what makes archiving an
    ordinary act rather than a destructive one. Every wall hanging a theme that
    holds the work takes it back as the restore lands, if it can be shown.
    """
    services = _services(request)
    services.catalogue.restore_artwork(artwork_id)
    return _work_detail(services, artwork_id)


@router.get("/works/{artwork_id}/mat")
def get_work_mat(request: Request, artwork_id: str) -> WorkMatOut:
    """The Work page's mat control: the current mat, the presets, and what re-deriving would give."""
    return _work_mat(_services(request), artwork_id)


@router.post("/works/{artwork_id}/mat")
def set_work_mat(request: Request, artwork_id: str, body: SetWorkMat) -> WorkMatOut:
    """Choose a work's mat: a preset, recorded as the curator's, or the derivation,
    recorded as `derived`. Free either way, and the previous colour is kept.

    Read-back-after-mutate, so the control repaints from what was recorded.
    """
    services = _services(request)
    services.preparation.set_work_mat(artwork_id, MatRequest.named(preset=body.preset, derived=body.derive))
    return _work_mat(services, artwork_id)


def _work_mat(services: Services, artwork_id: str) -> WorkMatOut:
    offer = services.preparation.mat_offer(artwork_id)
    return WorkMatOut(
        current=None if offer.current is None else _mat_color(offer.current),
        presets=[MatPresetOut(key=preset.key, label=preset.label, hex_rgb=preset.hex_rgb) for preset in offer.presets],
        derived_hex_rgb=offer.derived_hex_rgb,
    )


@router.get("/works/{artwork_id}/placements")
def work_placements(request: Request, artwork_id: str) -> WorkPlacementsOut:
    """Where a held work is: every theme holding it with the walls hanging each, and whether it is kept off every wall.

    Selections (hidden themes) are included, because a selection is how a work
    hangs on a wall by itself. The Work page's state strip reads this, and an
    agent reaches the same facts through `art_theme`'s `list`, `get` and
    `kept_off`. Refused for a work the catalogue does not hold.
    """
    services = _services(request)
    services.catalogue.get_artwork(artwork_id)
    placements = services.display.placements_of(artwork_id)
    return WorkPlacementsOut(
        artwork_id=artwork_id,
        themes=[_placement(placement) for placement in placements.themes],
        excluded_at=None if placements.exclusion is None else placements.exclusion.excluded_at.isoformat(),
    )


@router.get("/works/{artwork_id}/thumbnail", response_class=FileResponse)
def get_thumbnail(
    request: Request,
    artwork_id: str,
    size: Annotated[Literal["tile", "large"], Query()] = "tile",
) -> Response:
    """A small copy of the work itself, drawn from its master, generated on first ask.

    What a library tile shows: the work at its own aspect, never the wall
    render's mat and bars, which are the wall's and appear only on the Work
    page (`get_wall_preview`). `size=large` is the same bare work in a box sharp
    across Walls' lead picture on a 2x screen (`LARGE_THUMBNAIL_MAX_EDGE_PX`).
    Any other value is refused rather than read as the default, so a misspelt
    request is not quietly answered small.
    """
    return _revalidated_file(request, _services(request).thumbnails.thumbnail(artwork_id, large=size == "large"))


@router.get("/works/{artwork_id}/wall-preview", response_class=FileResponse)
def get_wall_preview(request: Request, artwork_id: str) -> Response:
    """The work at a size the Work page's column draws sharply, drawn from its master."""
    return _revalidated_file(request, _services(request).thumbnails.wall_preview(artwork_id))


def _revalidated_file(request: Request, path: Path) -> Response:
    """A cached image, answered with a 304 when the client already holds it.

    **The conditional check is done here because nothing else does it.**
    `FileResponse` *sets* an `ETag` and never *reads* one — only Starlette's
    `StaticFiles` compares them, and these files are generated rather than
    served from a directory. Without this, `no-cache` means every repaint of a
    forty-card grid re-downloads every thumbnail; with it, it costs forty empty
    304s. Passing `stat_result` makes the header available before the response
    is sent and, more importantly, means the value compared against is the one
    Starlette itself would have produced rather than a second implementation of
    its formula.
    """
    headers = {"Cache-Control": THUMBNAIL_CACHE_CONTROL}
    response = FileResponse(path, media_type="image/jpeg", headers=headers, stat_result=path.stat())
    etag = response.headers.get("etag")
    if etag is not None and _matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers={**headers, "ETag": etag})
    return response


def _matches(header: str | None, etag: str) -> bool:
    """Whether an `If-None-Match` header already covers this thumbnail.

    Three cases, all of them real rather than defensive:

    * **A list of tags.** A client that has seen two versions of a URL may offer
      both, so comparing the raw header against one tag would miss a match it was
      handed.
    * **`*`.** RFC 9110 makes it match any current representation. By the time
      this is asked the file exists — `thumbnail()` returned its path — so there
      is one, and the answer is yes.
    * **The weak marker.** `W/"abc"` and `"abc"` are the same tag for a weak
      comparison, which is what a conditional GET performs.

    Stated as three cases because a docstring that describes the `*` one without
    implementing it is exactly the defect `_revalidated_file`'s conditional
    check exists to prevent.
    """
    if not header:
        return False
    offered = {tag.strip() for tag in header.split(",")}
    if "*" in offered:
        return True
    return etag in {tag.removeprefix("W/") for tag in offered}


def _theme_option(option: ThemeCount) -> ThemeOptionOut:
    return ThemeOptionOut(
        theme_id=option.theme.id,
        name=option.theme.name,
        count=option.count,
        selected=option.selected,
        disabled=option.disabled,
    )


def _work_detail(services: Services, artwork_id: str) -> WorkDetailOut:
    """The work in full, as every route answering with one answers: its dossier and the Get it came from."""
    return _dossier(services.survey.get_work(artwork_id), services.catalogue.get_that_brought(artwork_id))


def _dossier(dossier: WorkDossier, brought: HistoryEvent | None) -> WorkDetailOut:
    return WorkDetailOut(
        work=_work(dossier.survey),
        original=None if dossier.original is None else _original(dossier.original),
        sources=[_source(source) for source in dossier.sources],
        renditions=[_rendition(view) for view in dossier.renditions],
        mat_colors=[_mat_color(mat) for mat in dossier.mat_colors],
        facets=[_facet(facet) for facet in dossier.facets],
        acquisition=None if dossier.acquisition is None else _acquisition(dossier.acquisition),
        get=(
            None
            if brought is None or brought.run_id is None
            else WorkGetOut(run_id=brought.run_id, accepted_at=brought.occurred_at.isoformat())
        ),
    )


def _facet(facet: WorkFacet) -> WorkFacetOut:
    return WorkFacetOut(
        facet_id=facet.id,
        kind=str(facet.kind),
        value=facet.value,
        derivation=str(facet.derivation),
        source_note=facet.source_note,
        value_qid=facet.value_qid,
    )


def _facet_group(group: FacetGroup) -> FacetGroupOut:
    return FacetGroupOut(
        kind=str(group.kind),
        options=[
            FacetOptionOut(value=option.value, count=option.count, selected=option.selected, disabled=option.disabled)
            for option in group.options
        ],
        total_values=group.total_values,
        # The group's own property rather than `len(options) < total_values`
        # recomputed here, so a client and the service cannot disagree about
        # whether a rail is showing everything.
        truncated=group.truncated,
    )


def _original(original: Original) -> OriginalOut:
    return OriginalOut(
        relative_path=original.relative_path,
        width=original.width,
        height=original.height,
        byte_size=original.byte_size,
        content_hash=original.content_hash,
    )


def _source(source: Source) -> SourceOut:
    return SourceOut(
        source_id=source.id,
        url=source.url,
        provider=source.provider,
        source_class=str(source.source_class),
        acquisition_method=str(source.acquisition_method),
        rights_status=str(source.rights_status),
        is_primary=source.is_primary,
        confidence=source.confidence,
        selection_rationale=source.selection_rationale,
        last_fetch_status=None if source.last_fetch_status is None else str(source.last_fetch_status),
        last_fetched_at=source.last_fetched_at,
    )


def _rendition(view: RenditionView) -> RenditionOut:
    return RenditionOut(
        rendition_id=view.rendition.id,
        kind=str(view.rendition.kind),
        target_width=view.rendition.target_width,
        target_height=view.rendition.target_height,
        relative_path=view.rendition.relative_path,
        stale=view.stale,
        generated_at=view.rendition.generated_at.isoformat(),
    )


def _mat_color(mat: MatColor) -> MatColorOut:
    return MatColorOut(
        hex_rgb=mat.hex_rgb,
        method=str(mat.method),
        is_current=mat.is_current,
        reason=mat.reason,
        chosen_at=mat.chosen_at.isoformat(),
    )
