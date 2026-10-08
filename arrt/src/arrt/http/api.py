"""The JSON surface the browser client reads, and the shaping that feeds it.

A handler unpacks the request, composes service calls, and formats the result,
and it never branches on a service call's answer to decide what happens next —
that decision belongs to the service layer, which the MCP tools call too
(`architecture.md` § Direction, as the owner amended it on 2026-10-05). Reading
back what a write produced, or joining two reads for one page, is composition and
conforms; so are the transport's own shapes: a conditional request answered with
`304`, and a service's "no such thing" mapped to `404`. A composition the MCP
surface needs too lives in a service, or is pinned by a test both surfaces run.
This is the same rule `mcp/bindings.py` states, and it is stated twice on purpose:
it is the only thing keeping an agent and a click from disagreeing about the same
catalogue.

**Handlers are synchronous `def`, deliberately.** The service layer is
synchronous and its work is real — sqlite reads, `fsync` on write, and a JPEG
downscale that can take a tenth of a second. Starlette runs a sync handler in a
worker thread, so none of that sits on the event loop, where it would stall the
MCP session manager sharing this process. The catalogue's one connection is
opened `check_same_thread=False` behind a re-entrant lock, which is what makes
that safe.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from arrt.http.models import (
    AcquisitionQueueOut,
    AcquisitionStateOut,
    AddWork,
    AffinityListOut,
    AffinityOut,
    ArtistCandidateOut,
    ArtistListOut,
    ArtistOut,
    ArtistRegistryOut,
    AssignWall,
    BackupOut,
    BudgetOut,
    CandidateCardOut,
    CandidatePageOut,
    CandidateWorkOut,
    CauseWorksOut,
    ClientHeartbeatOut,
    ClientListOut,
    ClientOut,
    ClientTokenOut,
    ClientWallOut,
    CommitDirection,
    ConversationDeletionOut,
    ConversationListOut,
    ConversationOut,
    ConversationTurnOut,
    ConversationViewOut,
    CostTiersOut,
    CreateTheme,
    CreateWall,
    DirectiveOut,
    DisplayStateOut,
    EstimateOut,
    ExcludedWorkListOut,
    ExcludedWorkOut,
    ExclusionOut,
    FacetGroupOut,
    FacetOptionOut,
    FailureCauseOut,
    FailureCausesOut,
    FitOut,
    GetOut,
    HangSelection,
    HangTheme,
    HealthOut,
    HeartbeatOut,
    HeldArtistOut,
    HeldTopicOut,
    HistoryEventOut,
    HistoryPageOut,
    ImageOut,
    InReviewOut,
    InstanceListingOut,
    InstanceOut,
    LookOut,
    LookPictureOut,
    LookSourceOut,
    ManifestEntryOut,
    ManifestOut,
    MatColorOut,
    MoveWork,
    NameClient,
    NotAgainOut,
    NotAgainRequest,
    OriginalOut,
    PickItem,
    PicturesOut,
    QueuedWorkOut,
    QueuePauseOut,
    RefusedRetryOut,
    RegistryCreatorOut,
    RegistryHolderOut,
    RegistryHoldingOut,
    RegistryPersonFoundOut,
    RegistrySearchOut,
    RegistryWorkFoundOut,
    RegistryWorkOut,
    RegistryWorkPageOut,
    RenameTheme,
    RenditionOut,
    ReportedOutputOut,
    ReportedStateOut,
    RetryCause,
    RetryCauseOut,
    RunListOut,
    RunOut,
    RunTallyOut,
    RunViewOut,
    SampleOut,
    SearchUsageOut,
    SelectedImageOut,
    SelectImage,
    SetAffinity,
    SetIdentity,
    SetVerdict,
    SightingHostOut,
    SightingHostsOut,
    SimilarArtistOut,
    SimilarArtistsOut,
    SkippedOut,
    SourceOut,
    SourcePluginOut,
    SourcesOut,
    SourceYieldOut,
    SourceYieldsOut,
    Speak,
    SpendOut,
    StartGet,
    StartResolve,
    StartRun,
    StepDisplay,
    SuggestionOut,
    ThemeDetailOut,
    ThemeListOut,
    ThemeOptionOut,
    ThemeOut,
    ThemePlacementOut,
    ThemeSummaryOut,
    TopicArtistsOut,
    TopicFoundOut,
    TopicKindOut,
    TopicPageOut,
    TopicRegistryOut,
    TopicSearchOut,
    TopicsOut,
    TopicWorkOut,
    TopicWorksOut,
    UnlinkedArtistOut,
    VerdictOut,
    WallAssignmentOut,
    WallHeartbeatOut,
    WallListOut,
    WallOut,
    WallRefOut,
    WantedListingOut,
    WantedWorkOut,
    WantWork,
    WorkDetailOut,
    WorkFacetOut,
    WorkMatchesOut,
    WorkMatchOut,
    WorkOut,
    WorkPageOut,
    WorkPlacementsOut,
)
from arrt.library.acquisition.queue import AcquisitionState, FailureCause, QueueEntry, QueuePause
from arrt.library.services.artists import HeldArtist, RegistryView
from arrt.library.services.catalogue import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT, FacetGroup, RenditionView
from arrt.library.services.conversation import ConversationDeletion, ConversationView, TurnView
from arrt.library.services.discovery import VerdictOutcome
from arrt.library.services.display_fit import FitAssessment
from arrt.library.services.look import LookPicture, LookView, SourceLook
from arrt.library.services.review import CandidatePage, CandidateView, InstanceListing, InstanceView, WantedView
from arrt.library.services.runner import Estimate, RunView, SpendReport
from arrt.library.services.spending import CENTS_BELOW, DIMES_BELOW
from arrt.library.services.survey import WorkDossier, WorkSurvey
from arrt.library.services.taste import AffinityView
from arrt.library.services.thumbnails import ThumbnailUnavailable
from arrt.library.services.topics import TopicIndex, TopicPage
from arrt.library.services.twins import InReview
from arrt.library.sources.plugin import API_VERSION
from arrt.persistence.discovery_records import (
    CandidateImage,
    CandidateWork,
    Conversation,
    DiscoveryRun,
    InitiatedBy,
)
from arrt.persistence.records import (
    Artist,
    BackupReading,
    Directive,
    HistoryEvent,
    IdentitySetBy,
    MatColor,
    Original,
    Source,
    Theme,
    WorkFacet,
)
from arrt.programming.clients import ClientView
from arrt.programming.display import ThemeCount, ThemePlacement, WallView
from arrt.programming.display_state import DisplayState
from arrt.programming.manifest.builder import ManifestBuild
from arrt.programming.manifest.heartbeat import HeartbeatReading
from arrt.services.container import Services
from arrt.services.errors import ServiceError
from arrt.services.health import HealthReading, PicturesReading, SourceHealth

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

#: Thumbnails and wall previews are revalidated rather than held for a fixed
#: window. A replaced master, or a recomposed canvas, regenerates the file under
#: the same name, so a cached copy is a
#: *superseded acquisition* on screen — the exact thing the staleness rule
#: refuses everywhere else. The cost of that correctness is one conditional
#: request per card, answered below with a 304 rather than the bytes.
THUMBNAIL_CACHE_CONTROL: str = "private, no-cache"

#: A candidate preview, by contrast, is held rather than revalidated — and the
#: difference between the two lines is a property of the data rather than a
#: preference. A thumbnail is named for its *work*, and a re-acquired master
#: regenerates it under the same name, so a cached copy can become a superseded
#: acquisition on screen. A candidate preview is named for its *instance*: the
#: picture store keeps one picture per instance, never re-fetches what it keeps
#: and never deletes it, so the bytes behind an image id are written once. An id
#: whose content cannot change is the case `immutable` exists for, and it is what
#: keeps a repaint of a thirty-card grid from asking the server thirty times.
#:
#: A row the old sweep reclaimed is not a hole in that: its card is told by the
#: listing that no picture travels, so it never asks, and a copy still in a
#: browser cache is never shown.
PREVIEW_CACHE_CONTROL: str = "private, max-age=86400, immutable"


def _services(request: Request) -> Services:
    """The services this application was built around.

    Read off application state rather than injected per route, because they are
    constructed once at startup over one open catalogue file — a per-request
    dependency would suggest a lifetime they do not have.
    """
    return request.app.state.services


# -- works --------------------------------------------------------------------


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
    """
    services = _services(request)
    within = None if theme is None else services.display.theme_work_ids(theme)
    chosen = {"artist": artist, "movement": movement, "era": era, "subject": subject, "medium": medium, "palette": palette}
    facets = {kind: values for kind, values in chosen.items() if values}
    page = services.survey.list_works(
        status=status,
        q=q,
        facets=facets,
        limit=limit,
        offset=offset,
        sort=sort,
        artist_id=artist_id,
        within=within,
    )
    # The theme options, counted as the facets are, with the theme's own
    # selection ignored: the Library names what the other filters select, and
    # Programming counts each theme's members among them.
    others = services.catalogue.matching_ids(status=status, q=q, facets=facets, artist_id=artist_id)
    return WorkPageOut(
        works=[_work(entry) for entry in page.entries],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        truncated=page.truncated,
        facets=[_facet_group(group) for group in page.facets],
        themes=[_theme_option(option) for option in services.display.theme_counts(others, selected=theme)],
    )


@router.get("/works/{artwork_id}")
def get_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """One work in full — metadata, artist, sources, renditions and mats."""
    return _dossier(_services(request).survey.get_work(artwork_id))


@router.post("/works/{artwork_id}/acquisition/retry")
def retry_acquisition(request: Request, artwork_id: str) -> AcquisitionStateOut:
    """Forget the work's failures and put it at the front of the acquisition queue.

    Fetches nothing in the request: a tiled fetch may take half an hour, and the
    queue fetches one work at a time. Answers with where the work now stands.
    """
    return _acquisition(_services(request).acquisition_queue.retry(artwork_id))


@router.get("/acquisitions")
def list_acquisitions(
    request: Request,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> AcquisitionQueueOut:
    """The queue's pause if any, then one page of the works still in line, in the order it will try them.

    A work that failed or was given up on is listed under its cause instead
    (`/acquisitions/causes`), so thousands of works failing for one reason are
    one row there rather than thousands here; this answer counts them.
    """
    listing = _services(request).acquisition_queue.listing()
    in_line = listing.in_line
    limit, page = _queue_page(in_line, limit, offset)
    return AcquisitionQueueOut(
        pause=None if listing.pause is None else _queue_pause(listing.pause),
        works=[_queued_work(entry) for entry in page],
        total=len(in_line),
        limit=limit,
        offset=offset,
        failing=len(listing.entries) - len(in_line),
        causes=len(listing.causes),
    )


@router.get("/acquisitions/causes")
def list_failure_causes(
    request: Request,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> FailureCausesOut:
    """Every reason the queue's failed works failed for, one row each with how many, the largest first.

    Grouped by the reason's words with the work's own name taken out, so works
    that failed the same way share a row whatever they are called.
    """
    causes = _services(request).acquisition_queue.listing().causes
    limit, page = _queue_page(causes, limit, offset)
    return FailureCausesOut(causes=[_failure_cause(each) for each in page], total=len(causes), limit=limit, offset=offset)


@router.get("/acquisitions/causes/works")
def list_cause_works(
    request: Request,
    cause: Annotated[str, Query()],
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> CauseWorksOut:
    """One page of the works that failed for `cause`, worded as `/acquisitions/causes` words it.

    A cause no work holds any more answers with no works rather than a refusal:
    the group emptied because the queue tried them again, which is not an error.
    """
    group = next((each for each in _services(request).acquisition_queue.listing().causes if each.cause == cause), None)
    entries = () if group is None else group.entries
    limit, page = _queue_page(entries, limit, offset)
    return CauseWorksOut(
        cause=cause, works=[_queued_work(entry) for entry in page], total=len(entries), limit=limit, offset=offset
    )


@router.post("/acquisitions/causes/retry")
def retry_failure_cause(request: Request, body: RetryCause) -> RetryCauseOut:
    """Retry all: every work that failed for `cause`, in one request, fetching nothing in it.

    Each is put back in line as its own Retry would put it; one the queue
    refuses (no source, being fetched now) is counted under why, naming no work.
    """
    result = _services(request).acquisition_queue.retry_cause(body.cause)
    return RetryCauseOut(
        cause=result.cause,
        retried=result.retried,
        refused=[RefusedRetryOut(reason=reason, works=count) for reason, count in result.refused.items()],
    )


@router.post("/works/{artwork_id}/wikidata")
def set_work_identity(request: Request, artwork_id: str, body: SetIdentity) -> WorkDetailOut:
    """Say which Wikidata item this work is, or that there is none.

    Answers with the dossier, the shape every act on the Work screen repaints
    from. The matcher never overwrites what is set here (`identity.py`).
    """
    services = _services(request)
    services.identity.set_work_identity(artwork_id, body.qid)
    return _dossier(services.survey.get_work(artwork_id))


@router.get("/artists")
def list_artists(request: Request, q: Annotated[str | None, Query()] = None) -> ArtistListOut:
    """Library › Artists: every artist with a work in circulation, by surname (`surname_key`).

    `q` narrows to names containing it, ignoring case and accents, which is what
    the top-bar search asks when it offers artists.

    **Not capped, and what bounds it is the catalogue**: one row per artist with a
    work in circulation, so never more rows than works, and an artist's row is a
    name, a count and one work id. At the NFR's thousands of works that is a few
    hundred rows.
    If it is ever paged, the typeahead's `q` lookup is the caller that needs it.
    """
    return ArtistListOut(artists=[_held_artist(entry) for entry in _services(request).artists.index(q)])


@router.get("/artists/{artist_id}")
def get_artist(request: Request, artist_id: str) -> HeldArtistOut:
    """One artist, from the library alone: answerable whatever the registry is doing."""
    return _held_artist(_services(request).artists.get(artist_id))


@router.get("/artists/{artist_id}/registry")
def get_artist_registry(request: Request, artist_id: str) -> ArtistRegistryOut:
    """What Wikidata knows about this artist, asked separately so a slow or absent registry delays nothing else.

    Always a 200 for an artist the catalogue holds: a registry that is not
    configured, cannot be asked, or has nothing for this artist is a state the
    page shows, named in `state` and said in `note`.
    """
    return _artist_registry(_services(request).artists.registry_view(artist_id))


@router.get("/registry/artists/{qid}")
def get_registry_artist(request: Request, qid: str) -> ArtistRegistryOut:
    """What Wikidata knows about an artist reached by QID, whether or not the library holds them.

    The same shape and states as an artist's `/registry`, but `no_identity` cannot
    occur. When the library holds an artist with this QID, `state` is `held`,
    `artist_id` names them, the page goes there instead, and the registry is not
    asked. A malformed QID is a 400.
    """
    held, view = _services(request).artists.registry_view_by_qid(qid)
    return _artist_registry(view, artist_id=held)


@router.get("/registry/search")
def search_registry(
    request: Request,
    q: Annotated[str, Query()] = "",
    prefix: Annotated[bool, Query()] = False,  # noqa: FBT002 -- a query parameter FastAPI passes by name
    wide: Annotated[bool, Query()] = False,  # noqa: FBT002 -- a query parameter FastAPI passes by name
) -> RegistrySearchOut:
    """Wikidata's artists and works for a few typed words, the other half of the top-bar search.

    `prefix=true` reads the last word as the start of one, as the typeahead does
    mid-word; `wide=true` returns the results page's longer lists. Always a 200:
    `state` says whether anything was asked and what the registry did.
    Kept per query for a week, across restarts; a failure is not.
    """
    found = _services(request).registry_search.search(q, prefix=prefix, wide=wide)
    held_artists, held_works = found.held_artists, found.held_works
    return RegistrySearchOut(
        state=str(found.state),
        note=found.note,
        artists=[
            RegistryPersonFoundOut(
                qid=p.qid,
                name=p.label,
                born=p.born,
                died=p.died,
                artist_id=held_artists.get(p.qid),
                in_review=_in_review(found.waiting_artists.get(p.qid)),
            )
            for p in found.artists
        ],
        works=[
            RegistryWorkFoundOut(
                qid=w.qid,
                title=w.title,
                sitelinks=w.sitelinks,
                image=w.image,
                creator=(
                    None
                    if w.creator is None
                    else RegistryCreatorOut(qid=w.creator.qid, name=w.creator.name, artist_id=held_artists.get(w.creator.qid))
                ),
                held_artwork_ids=list(held_works.get(w.qid, ())),
                wanted=w.qid in found.wanted_works,
                in_review=_in_review(found.waiting_works.get(w.qid)),
            )
            for w in found.works
        ],
    )


@router.get("/registry/artists/{qid}/similar")
def get_similar_artists(request: Request, qid: str) -> SimilarArtistsOut:
    """*Similar artists* for the Artist page, by the artist's QID, held or not.

    Asked after the page is drawn: the query takes one to seven seconds. Always a
    200 for a well-formed QID; a malformed one is a 400.
    """
    view = _services(request).artists.similar(qid)
    return SimilarArtistsOut(
        state=str(view.state),
        note=view.note,
        artists=[
            SimilarArtistOut(qid=p.qid, name=p.name, born=p.born, died=p.died, images=p.images, artist_id=view.held.get(p.qid))
            for p in view.people
        ],
    )


@router.get("/registry/works/{qid}")
def get_registry_work(request: Request, qid: str) -> RegistryWorkPageOut:
    """One work as Wikidata knows it, and the library's works that are it, for the Work page by QID.

    Always a 200 for a well-formed QID: `state` says what the registry did, and
    `held_artwork_ids` is filled whatever it did. A malformed QID is a 400.
    """
    view = _services(request).registry_works.view(qid)
    known = view.known
    return RegistryWorkPageOut(
        state=str(view.state),
        note=view.note,
        qid=qid,
        title=None if known is None else known.title,
        year=None if known is None else known.year,
        sitelinks=None if known is None else known.sitelinks,
        image=None if known is None else known.image,
        creators=(
            []
            if known is None
            else [RegistryCreatorOut(qid=c.qid, name=c.name, artist_id=view.artists.get(c.qid)) for c in known.creators]
        ),
        media=[] if known is None else list(known.media),
        holders=(
            [] if known is None else [RegistryHolderOut(qid=h.qid, name=h.name, inventory=h.inventory) for h in known.holders]
        ),
        held_artwork_ids=list(view.held),
        wanted=view.wanted,
        height_cm=view.height_cm,
        width_cm=view.width_cm,
        image_width=None if view.image_size is None else view.image_size.width,
        image_height=None if view.image_size is None else view.image_size.height,
        fit=None if view.fit is None else _fit(view.fit),
    )


#: What a browser is told when a picture key is not one a work's current look
#: names: another work's, a refused find's, or one from a look no longer kept.
LOOK_AGAIN: str = "This picture is not part of a current look at this work. Look again."


@router.get("/registry/works/{qid}/look")
def get_registry_work_look(request: Request, qid: str) -> LookOut:
    """What every image source holds of the work, asked before any Get.

    Starts the asking, or joins it, and answers at once with each source's
    state: the page polls while `state` is `asking`. Nothing is written to the
    catalogue. A malformed QID is a 400.
    """
    return _look(_services(request).look.look(qid))


@router.get("/registry/works/{qid}/look/pictures/{key}", response_class=Response)
def get_registry_work_look_picture(
    request: Request,
    qid: str,
    key: str,
    size: Annotated[Literal["card", "large"], Query()] = "card",
) -> Response:
    """A picture the work's current look found, from the picture store.

    `key` is one the look's answer names, never a URL: any other key, or one
    from a look no longer kept, is a 404 saying to look again. A key the look
    names whose picture could not be kept is a 400, as a review card's is.
    `size` is the review card's: `card`, or `large` for the enlarged view.
    """
    rendered = _services(request).look.picture(qid, key, enlarged=size == "large")
    if rendered is None:
        return JSONResponse(status_code=404, content={"error": LOOK_AGAIN})
    return Response(content=rendered.data, media_type=rendered.media_type, headers={"Cache-Control": PREVIEW_CACHE_CONTROL})


# -- topics -------------------------------------------------------------------


@router.get("/topics")
def list_topics(request: Request) -> TopicsOut:
    """Library › Topics: every topic the library's works in circulation are in, by kind, with counts.

    Read from the facet rows the topic sweep writes, so it never waits on
    Wikidata. Always a 200.
    """
    return _topics(_services(request).topics.index())


@router.get("/registry/topics")
def search_topics(request: Request, q: Annotated[str, Query()] = "") -> TopicSearchOut:
    """Topics Wikidata finds for a typed name: periods, movements, kinds of work, and subjects.

    Always a 200: `state` says whether the registry was asked and what it did.
    Kept for `REGISTRY_KEPT_FOR`, like every registry answer: a typeahead asks with
    every word, and the same word asked again is answered from disk.
    """
    found = _services(request).topics.named(q)
    return TopicSearchOut(
        state=str(found.state),
        note=found.note,
        topics=[
            TopicFoundOut(
                qid=topic.qid,
                label=topic.label,
                kinds=[kind.value for kind in topic.kinds],
                description=topic.description,
                start=topic.start,
                end=topic.end,
            )
            for topic in found.topics
        ],
    )


@router.get("/topics/{qid}")
def get_topic(request: Request, qid: str) -> TopicPageOut:
    """The library's half of a Topic page: the topic as its works carry it, and those works. No network.

    A topic none of the library's works is in answers with no label and no
    works rather than a 404: a Topic page reached by search is ordinary. A
    malformed QID is a 400.
    """
    services = _services(request)
    page = services.topics.page(qid)
    # Two calls composed, as a theme's works are: the topic says which works,
    # and the survey says what each is as a card.
    return _topic_page(page, [_work(entry) for entry in services.survey.survey_works(page.work_ids)])


@router.get("/topics/{qid}/registry")
def get_topic_registry(request: Request, qid: str) -> TopicRegistryOut:
    """The topic as Wikidata knows it, the page's head, asked separately so it delays nothing.

    Always a 200 for a well-formed QID; a malformed one is a 400. Kept per topic
    for a week, across restarts; a missing item and a failure are not.
    """
    view = _services(request).topics.topic(qid)
    known = view.known
    return TopicRegistryOut(
        state=str(view.state),
        note=view.note,
        qid=qid,
        label=None if known is None else known.label,
        kinds=[] if known is None else [kind.value for kind in known.kinds],
        description=None if known is None else known.description,
        start=None if known is None else known.start,
        end=None if known is None else known.end,
    )


@router.get("/topics/{qid}/works")
def get_topic_works(request: Request, qid: str) -> TopicWorksOut:
    """*Representative works*: the topic's most renowned works, each with what marks it: held, wanted, its image.

    Asked after the page is drawn: a period's works took 7 to 26 seconds to
    ask for. Always a 200 for a well-formed QID; a malformed one is a 400.
    """
    view = _services(request).topics.works(qid)
    return TopicWorksOut(
        state=str(view.state),
        note=view.note,
        works=[
            TopicWorkOut(
                qid=entry.work.qid,
                title=entry.work.title,
                sitelinks=entry.work.sitelinks,
                year=entry.work.year,
                image=entry.work.image,
                creators=[
                    RegistryCreatorOut(qid=creator.qid, name=creator.name, artist_id=view.artists.get(creator.qid))
                    for creator in entry.work.creators
                ],
                creator_unknown=entry.work.creator_unknown,
                state=str(entry.state),
                held_artwork_ids=list(entry.held),
                wanted=entry.wanted,
            )
            for entry in view.works
        ],
    )


@router.get("/topics/{qid}/artists")
def get_topic_artists(request: Request, qid: str) -> TopicArtistsOut:
    """The topic's *Artists*, the most renowned first, each with the library's artist where held.

    Asked after the page is drawn, as *Representative works* is. Always a 200
    for a well-formed QID; a malformed one is a 400.
    """
    view = _services(request).topics.artists(qid)
    return TopicArtistsOut(
        state=str(view.state),
        note=view.note,
        artists=[
            SimilarArtistOut(qid=p.qid, name=p.name, born=p.born, died=p.died, images=p.images, artist_id=view.held.get(p.qid))
            for p in view.people
        ],
    )


def _topics(index: TopicIndex) -> TopicsOut:
    return TopicsOut(
        state=str(index.state),
        note=index.note,
        kinds=[
            TopicKindOut(
                kind=group.kind.value,
                topics=[HeldTopicOut(qid=topic.qid, label=topic.label, works=topic.works) for topic in group.topics],
            )
            for group in index.groups
        ],
    )


def _topic_page(page: TopicPage, works: list[WorkOut]) -> TopicPageOut:
    return TopicPageOut(
        state=str(page.state),
        note=page.note,
        qid=page.qid,
        label=page.label,
        kinds=[kind.value for kind in page.kinds],
        works=works,
    )


def _in_review(waiting: InReview | None) -> InReviewOut | None:
    return None if waiting is None else InReviewOut(run_id=waiting.run_id, candidate_work_id=waiting.candidate_work_id)


def _artist_registry(view: RegistryView, *, artist_id: str | None = None) -> ArtistRegistryOut:
    known = view.known
    return ArtistRegistryOut(
        state=str(view.state),
        note=view.note,
        qid=None if known is None else known.qid,
        name=None if known is None else known.name,
        born=None if known is None else known.born,
        died=None if known is None else known.died,
        artist_id=artist_id,
        description=None if known is None else known.description,
        movements=[] if known is None else list(known.movements),
        works=(
            []
            if known is None
            else [
                RegistryWorkOut(
                    qid=entry.qid,
                    title=entry.title,
                    year=entry.year,
                    sitelinks=entry.sitelinks,
                    image=entry.image,
                    held_artwork_ids=list(view.held.get(entry.qid, ())),
                    wanted=entry.qid in view.wanted,
                    in_review=_in_review(view.waiting.get(entry.qid)),
                )
                for entry in known.works
            ]
        ),
        works_total=0 if known is None else known.works_total,
        holdings=([] if known is None else [RegistryHoldingOut(qid=h.qid, name=h.name, works=h.works) for h in known.holdings]),
        candidates=[
            ArtistCandidateOut(
                qid=candidate.person.qid,
                name=candidate.person.label,
                born=candidate.person.born,
                died=candidate.person.died,
                years_agree=candidate.years_agree,
            )
            for candidate in view.candidates
        ],
        unlinked=[
            UnlinkedArtistOut(artist_id=artist.id, name=artist.name, born=artist.born, died=artist.died)
            for artist in view.unlinked
        ],
    )


@router.post("/artists/{artist_id}/wikidata")
def set_artist_identity(request: Request, artist_id: str, body: SetIdentity) -> ArtistOut:
    """Say which Wikidata item this artist is, or that there is none."""
    return _artist(_services(request).identity.set_artist_identity(artist_id, body.qid))


@router.post("/works/{artwork_id}/archive")
def archive_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """Take a work out of circulation, keeping its record and its mat history.

    **Archive rather than delete, and the noun in the path is the whole point.**
    `Artwork.status` has two values and restoration is permitted, so there is no
    route here that destroys a work; `information-architecture.md` argues the
    label follows the route, and the control this binds to reads *Archive*.

    The work stays in every theme that holds it — membership is curatorial and
    readiness is technical — so what changes is what the next manifest build puts
    on a wall. A standing pin naming this work is withdrawn in the same
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
    return _dossier(services.survey.get_work(artwork_id))


@router.post("/works/{artwork_id}/restore")
def restore_work(request: Request, artwork_id: str) -> WorkDetailOut:
    """Return an archived work to circulation.

    The undo of the route above, and its existence is what makes archiving an
    ordinary act rather than a destructive one. Nothing is republished: a theme
    holding this work carries it again at the next manifest build, so the wall
    goes on showing what it was showing until then.
    """
    services = _services(request)
    services.catalogue.restore_artwork(artwork_id)
    return _dossier(services.survey.get_work(artwork_id))


# -- themes -------------------------------------------------------------------


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
def rename_theme(request: Request, theme_id: str, body: RenameTheme) -> ThemeOut:
    """Change a theme's name.

    **`POST` rather than `PATCH`**, following this surface's own convention: it
    writes with `POST` and removes with `DELETE`, and one surface with two
    spellings for "change this" costs more than the orthodoxy is worth.

    Answers with the theme, so the screen repaints the name it now has rather
    than the one it sent. Those differ whenever the service normalises — a name
    surrounded by whitespace comes back trimmed — and a screen painting its own
    input would show a name the catalogue does not hold.
    """
    return _theme(_services(request).display.update_theme(theme_id, name=body.name))


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


@router.delete("/themes/{theme_id}/works/{artwork_id}")
def remove_from_theme(request: Request, theme_id: str, artwork_id: str) -> ThemeDetailOut:
    """Take a work out of a theme, and return the order that results."""
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


# -- walls --------------------------------------------------------------------


@router.get("/walls")
def list_walls(request: Request) -> WallListOut:
    """Every wall, and what is hanging on each."""
    return WallListOut(walls=[_wall(view) for view in _services(request).display.survey_walls()])


@router.post("/walls")
def create_wall(request: Request, body: CreateWall) -> WallOut:
    """Record a wall. It arrives with nothing hanging on it.

    **A wall recorded here lights up once a client is assigned to show it.**
    Hanging a theme writes that wall's own manifest, named by the id this route
    returns, and a client is admitted only to the walls assigned to it — so a
    second room needs a client output of its own, and nothing about it disturbs
    the first. Until 2026-08-12 there was one manifest for the installation and
    a second wall overwrote it silently.
    """
    services = _services(request)
    return _wall(services.display.get_wall_view(services.display.add_wall(name=body.name).id))


@router.post("/walls/{wall_id}/client")
def assign_wall(request: Request, wall_id: str, body: AssignWall) -> WallAssignmentOut:
    """Show this wall on one of a client's outputs, by the output's name.

    Read-back-after-mutate, for the reason `clear_wall` gives: the answer is the
    wall as it now stands, with a notice when the output could not be checked
    against what the client last reported.
    """
    services = _services(request)
    assignment = services.clients.assign_wall(wall_id, client_id=body.client_id, output=body.output)
    return WallAssignmentOut(wall=_wall(services.display.get_wall_view(wall_id)), notice=assignment.notice)


@router.delete("/walls/{wall_id}/client")
def unassign_wall(request: Request, wall_id: str) -> WallOut:
    """Take the wall off whichever client showed it. Its theme stays hung."""
    services = _services(request)
    services.clients.unassign_wall(wall_id)
    return _wall(services.display.get_wall_view(wall_id))


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
    return _wall(services.display.get_wall_view(wall_id))


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
        wall=_wall(services.display.get_wall_view(wall_id)),
        left_theme=None if done.left_theme is None else _theme(done.left_theme),
        excluded_at=None if done.exclusion is None else done.exclusion.excluded_at.isoformat(),
    )


@router.get("/exclusions")
def list_exclusions(request: Request) -> ExcludedWorkListOut:
    """Every work kept off every wall, oldest first. Each is still held."""
    return _exclusions(_services(request))


@router.delete("/exclusions/{artwork_id}")
def allow_again(request: Request, artwork_id: str) -> ExcludedWorkListOut:
    """Let a work kept off every wall go on walls again: the undo, from the work's page.

    Nothing is republished. A theme holding the work carries it again at its
    next build, as with a restored work. Answers with the exclusions that remain.
    """
    services = _services(request)
    services.display.allow_work(artwork_id)
    return _exclusions(services)


def _exclusions(services: Services) -> ExcludedWorkListOut:
    return ExcludedWorkListOut(
        exclusions=[
            ExcludedWorkOut(artwork_id=exclusion.artwork_id, excluded_at=exclusion.excluded_at.isoformat())
            for exclusion in services.display.excluded_works()
        ]
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


# -- history ------------------------------------------------------------------


@router.get("/history")
def list_history(
    request: Request,
    kind: Annotated[list[str] | None, Query()] = None,
    wall_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> HistoryPageOut:
    """What happened, newest first: Gets started and finished, verdicts, archives, restores, hangs.

    `kind` repeats, and any of those named matches (`?kind=work.accepted&kind=
    work.rejected`); none named is every kind. `wall_id` narrows to one wall's
    history: what was hung there, and what was kept off from there. Events are
    recorded from the day the history arrived, and nothing earlier is recovered.
    """
    page = _services(request).catalogue.list_events(kinds=kind or (), wall_id=wall_id, limit=limit, offset=offset)
    return HistoryPageOut(
        events=[_history_event(event) for event in page.events],
        total=page.total,
        # The service's default, stated so a reader can page without guessing it.
        limit=DEFAULT_LIST_LIMIT if limit is None else limit,
        offset=offset,
    )


def _history_event(event: HistoryEvent) -> HistoryEventOut:
    return HistoryEventOut(
        event_id=event.id,
        kind=str(event.kind),
        occurred_at=event.occurred_at.isoformat(),
        artwork_id=event.work_id,
        run_id=event.run_id,
        wall_id=event.wall_id,
        theme_id=event.theme_id,
        detail=dict(event.detail or {}),
    )


# -- clients ------------------------------------------------------------------


@router.get("/clients")
def list_clients(request: Request) -> ClientListOut:
    """Every client, with its walls and what it last reported about its outputs."""
    return ClientListOut(clients=[_client(view) for view in _services(request).clients.list_clients()])


@router.post("/clients")
def add_client(request: Request, body: NameClient) -> ClientOut:
    """Record a client. It has no token until one is issued."""
    services = _services(request)
    return _client(services.clients.get_client_view(services.clients.add_client(name=body.name).id))


@router.post("/clients/{client_id}")
def rename_client(request: Request, client_id: str, body: NameClient) -> ClientOut:
    """Rename a client. Its token and its walls are unchanged."""
    services = _services(request)
    services.clients.rename_client(client_id, name=body.name)
    return _client(services.clients.get_client_view(client_id))


@router.delete("/clients/{client_id}")
def remove_client(request: Request, client_id: str) -> ClientListOut:
    """Forget a client. Its token stops working and its walls become unassigned."""
    services = _services(request)
    services.clients.remove_client(client_id)
    return ClientListOut(clients=[_client(view) for view in services.clients.list_clients()])


@router.post("/clients/{client_id}/token")
def issue_client_token(request: Request, client_id: str) -> ClientTokenOut:
    """Issue the client's token, replacing any it had. It is shown here once.

    Nothing can read it back afterwards, because only a verifier is kept. The
    host puts it in the Player's environment file.
    """
    issued = _services(request).access.issue(client_id)
    return ClientTokenOut(client_id=issued.client_id, token=issued.token, token_issued_at=issued.issued_at.isoformat())


@router.post("/directives")
def step_display(request: Request, body: StepDisplay) -> DirectiveOut:
    """Tell the display serving one wall to move on to the next work.

    **The Walls screen's `next`, and until now the one screen action with an MCP
    action and no HTTP route at all.** `art_display(action='next')` has stepped a
    wall since the tool surface was built; the browser could only ever *read*
    `directive_sequence` off a manifest, so a curator standing in front of the
    television had no way to do the one thing they were most likely to want.

    The shape was left open while a directive was still a singleton, on the
    grounds that writing an installation-wide route would be writing the shape
    that had to change. It is per wall now, so the wall is named here as it is
    named in every other act that changes one.

    It returns the directive rather than the wall: what a step changes is what
    the wall was told to do, and nothing about what hangs there.
    """
    return _directive(_services(request).display.step_display(body.wall_id))


# -- the wall -----------------------------------------------------------------


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


@router.get("/health")
def get_health(request: Request) -> HealthOut:
    """Every observation the panel states, read at one instant.

    One service call, not three. This handler used to assemble the panel from a
    heartbeat here and a geometry there, which made "what signals does the panel
    make" a decision taken in the binding — and the next signal would have had to
    be added in two places with nothing to notice if it reached only one. The
    assembly is `HealthService.observe`'s now, and this is a dispatch again.
    """
    return _health(_services(request).health.observe())


@router.get("/sources")
def get_sources(request: Request) -> SourcesOut:
    """Every installed source plugin, where it came from, and what became of it at startup.

    Settings › Sources reads this: the inventory, where Status reads the same
    plugins for how they are doing. One reading, so the two pages cannot
    describe a plugin differently.
    """
    major, minor = API_VERSION
    return SourcesOut(
        interface_version=f"{major}.{minor}",
        sources=[_source_plugin(each) for each in _services(request).health.observe_sources()],
    )


@router.get("/sources/yields")
def get_source_yields(request: Request) -> SourceYieldsOut:
    """What each installed source plugin has given the library: offered, chosen, only here, median size.

    Status's sources table reads it beside `GET /api/health`'s `sources`. Its own
    route rather than a field of the health reading, because the top bar reads
    that on every page and these are counts across the whole library.
    """
    return SourceYieldsOut(
        sources=[
            SourceYieldOut(
                name=each.provider,
                offered=each.offered,
                chosen=each.chosen,
                only_here=each.only_here,
                median_long_edge=each.median_long_edge,
            )
            for each in _services(request).health.observe_yields()
        ]
    )


# -- discovery runs -----------------------------------------------------------


@router.get("/estimate")
def get_estimate(request: Request, run_id: Annotated[str | None, Query()] = None) -> EstimateOut:
    """What a search would cost, before anyone commits to it.

    Answered without a run id for "what does asking cost", and with one for "what
    does resolving what this run found cost". Estimating spends nothing, which is
    what lets the intent screen show the price beside the field rather than after
    the decision.
    """
    return _estimate(_services(request).runner.estimate(run_id))


@router.get("/budget")
def get_budget(request: Request) -> BudgetOut:
    """What is left of this month's budget, for the sidebar, read from the provider's key.

    Always a 200: `state` says how the figure is known, or why there is none.
    Display only, and up to a minute old; the provider's own refusal at its
    limit is what stops spending. The tier boundaries ride along so every
    spending control words its estimate the same way.
    """
    view = _services(request).budget.view()
    return BudgetOut(
        state=str(view.state),
        remaining_usd=_usd(view.remaining_usd),
        budget_usd=_usd(view.budget_usd),
        spent_usd=_usd(view.spent_usd),
        note=view.note,
        tiers=CostTiersOut(cents_below_usd=str(CENTS_BELOW), dimes_below_usd=str(DIMES_BELOW)),
    )


def _usd(amount: Decimal | None) -> str | None:
    return None if amount is None else str(amount)


@router.post("/runs")
def start_run(request: Request, body: StartRun) -> RunOut:
    """Begin a discovery run and return its handle at once.

    Phase 1 proceeds on a worker behind this response. Waiting for it here would
    hold the request open for the minutes the search takes, which no browser will
    sit through — so the client is handed an id and follows it.
    """
    return _run(
        _services(request).runner.start(
            intent_text=body.intent,
            # Provenance, never authorisation: every surface has identical
            # authority, and this records which one asked so that "who wanted
            # forty Dalí candidates" is answerable from the data afterwards.
            initiated_by=InitiatedBy.WEB_UI,
        )
    )


@router.post("/gets")
def start_get(request: Request, body: StartGet) -> GetOut:
    """Get the works these Wikidata items name, and say which were skipped.

    Returns at once with the run, which looks for images behind the response as
    any run does. Held items, items a Get is already looking for, and items the
    registry does not have are skipped and listed rather than refused.

    With a `theme_id`, the accepted works join that theme instead of the
    default. Two calls composed, with no branch on the first's answer:
    Programming says the theme exists (refusing an unknown one, so nothing
    starts), and the Library starts the Get.
    """
    services = _services(request)
    destination = None if body.theme_id is None else services.display.get_listed_theme(body.theme_id).id
    outcome = services.get.start(body.qids, initiated_by=InitiatedBy.WEB_UI, destination_theme_id=destination)
    return GetOut(
        run=None if outcome.run is None else _run(outcome.run),
        skipped=[SkippedOut(qid=entry.qid, reason=str(entry.reason)) for entry in outcome.skipped],
    )


@router.get("/runs")
def list_runs(
    request: Request,
    status: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    awaiting: Annotated[bool, Query()] = False,  # noqa: FBT002 -- a query parameter FastAPI passes by name
) -> RunListOut:
    """The newest runs, optionally narrowed, capped in the service layer.

    **`status` and `kind` are filters, not limits.** Omit both and this asked for
    the whole `discovery_runs` table — one row per search plus one per re-search,
    for ever, with nothing pruning them. What made it tolerable was a fact about
    the deployment rather than a mechanism: one household, one operator, so a
    year of use is hundreds of rows. A real bound, but an editorial one, and it
    stopped holding the moment this surface served anything else.

    The cap is `RunnerService.list_runs`', not this handler's, so this surface
    and the MCP twin cannot come to disagree about how much history exists —
    which is what the note here used to warn would happen if either were fixed
    alone. Both now read the same bound and report the same total.

    **There is still no paging parameter**, and that is a smaller gap than the
    one just closed: `total` says what was left out, and the two filters are how
    a caller reaches it. A `limit`/`offset` pair would change the contract of a
    shipped surface and earns its own review rather than riding along here.
    """
    listing = _services(request).runner.list_runs(status=status, kind=kind, awaiting=awaiting)
    return RunListOut(
        runs=[_run(run) for run in listing.runs],
        awaiting_works=listing.awaiting_works,
        awaiting={run.id: listing.awaiting[run.id] for run in listing.runs if run.id in listing.awaiting},
        count=len(listing.runs),
        total=listing.total,
        truncated=listing.truncated,
    )


@router.get("/runs/{run_id}")
def get_run(request: Request, run_id: str) -> RunViewOut:
    """Where a run is, answered immediately rather than held open.

    **The MCP surface long-polls here and this one deliberately does not.** A
    model calls `status` once and waits, so holding the call is what keeps it
    from spinning. A browser is already an event loop: it polls on a timer, and a
    held request would occupy one of the worker threads Starlette runs these
    synchronous handlers in for the whole hold window — with a couple of tabs
    open that starves the same pool that serves thumbnails. The client asks
    again; nothing is lost but the hold.
    """
    return _run_view(_services(request).runner.run_status(run_id, wait=False))


@router.post("/runs/{run_id}/approve")
def approve_run(request: Request, run_id: str) -> RunViewOut:
    """Accept the work list and its price; phase 2 begins behind the response."""
    return _run_view(_services(request).runner.approve(run_id))


@router.post("/runs/{run_id}/decline")
def decline_run(request: Request, run_id: str) -> RunViewOut:
    """Refuse the work list. The run ends without phase 2 ever spending."""
    return _run_view(_services(request).runner.decline(run_id))


@router.post("/runs/{run_id}/cancel")
def cancel_run(request: Request, run_id: str) -> RunViewOut:
    """Stop a run from wherever it is. Money already spent stays recorded."""
    return _run_view(_services(request).runner.cancel(run_id))


@router.get("/runs/{run_id}/spend")
def get_run_spend(request: Request, run_id: str) -> SpendOut:
    """What a run has actually cost, including every re-search descended from it."""
    return _spend(_services(request).runner.spend_report(run_id=run_id))


@router.post("/runs/resolve")
def start_resolve_run(request: Request, body: StartResolve) -> RunOut:
    """Look again for images of works whose scans the curator turned down.

    A re-search is a run, which is what lets the run view follow it with nothing
    special to know — `status`, `cancel` and `spend` all take its id. The handle
    comes back at once and the search proceeds behind it, exactly as `start` does
    and for the same reason: this takes minutes.

    **Listed above `/runs/{run_id}` on purpose is not what makes this safe** — the
    paths do not overlap, since nothing serves `POST /api/runs/{id}`. It sits here
    because it is the third way a run begins and belongs beside the other two.
    """
    return _run(
        _services(request).runner.resolve_images(
            candidate_work_ids=body.work_ids,
            initiated_by=InitiatedBy.WEB_UI,
        )
    )


# -- review -------------------------------------------------------------------


@router.get("/runs/{run_id}/candidates")
def list_candidates(
    request: Request,
    run_id: str,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> CandidatePageOut:
    """A page of the works a run is responsible for, each with a picture.

    Paged where the run view's own work list is not, and the difference is the
    payload rather than an inconsistency: that list is text, and this one carries
    a card per work. A curator scrolls a grid; they do not scroll two hundred
    pictures fetched at once on a Pi.
    """
    # `pictures=False`: this surface fetches each picture by URL, so inlining
    # them here would re-encode thirty images per page and discard the output.
    return _candidate_page(_services(request).review.list_works(run_id, limit=limit, offset=offset, pictures=False))


@router.get("/candidates/{work_id}")
def get_candidate(request: Request, work_id: str) -> CandidateCardOut:
    """One proposed work with the instance standing for it.

    What a card repaints from after a verdict or an image choice: the response to
    those calls says what changed, and this says what the card now looks like.
    """
    return _candidate_card(_services(request).review.get_work(work_id, pictures=False))


@router.get("/candidates/{work_id}/images")
def list_candidate_images(request: Request, work_id: str) -> InstanceListingOut:
    """Every scan found for this work, in the order the card offers them, capped.

    The alternates behind a card. Fetched on demand rather than with the grid: a
    thirty-work page would otherwise carry up to twelve instances each, and a
    curator opens the alternates for the few works whose first answer they doubt.
    """
    return _instance_listing(_services(request).review.list_images(work_id, pictures=False))


@router.post("/candidates/{work_id}/verdict")
def set_verdict(request: Request, work_id: str, body: SetVerdict) -> VerdictOut:
    """Accept or reject a proposed work. Acceptance promotes it into the catalogue."""
    return _verdict(_services(request).discovery.set_verdict(work_id, body.verdict, reason=body.reason))


@router.post("/candidates/{work_id}/want")
def want_candidate(request: Request, work_id: str, body: WantWork) -> CandidateWorkOut:
    """Want this work, turning down the named scan on the way if there is one. The one way into `wanted`.

    Nothing looks for a scan until a re-search is asked for, which is a separate call (free today:
    `RunnerSettings.phase2_estimate_usd`).
    """
    return _candidate_work(_services(request).discovery.want(work_id, turning_down=body.turning_down))


@router.get("/wanted")
def list_wanted(request: Request) -> WantedListingOut:
    """Every work the curator wants, across runs, newest run first."""
    # No bytes read: the listing is uncapped, so each row's picture costs a stat.
    return WantedListingOut(works=[_wanted_work(view) for view in _services(request).review.list_wanted(pictures=False)])


@router.get("/sightings/hosts")
def sighting_hosts(request: Request) -> SightingHostsOut:
    """Which hosts have pages for open works that no installed source plugin reads, by how many works. Names only."""
    return SightingHostsOut(
        hosts=[SightingHostOut(host=entry.host, works=entry.works) for entry in _services(request).sightings.hosts()]
    )


@router.get("/candidates/{work_id}/wikidata-matches")
def wikidata_matches(request: Request, work_id: str) -> WorkMatchesOut:
    """Wikidata's items matching a wanted work's title, the proposed artist's first. Stores nothing."""
    found = _services(request).wikidata_match.matches(work_id)
    return WorkMatchesOut(
        work_id=found.work.id,
        title=found.work.proposed_title,
        state=str(found.state),
        note=found.note,
        matches=[
            WorkMatchOut(
                qid=str(entry.match.qid),
                title=str(entry.match.title),
                creator=None if entry.match.creator is None else str(entry.match.creator.name),
                sitelinks=entry.match.sitelinks,
                has_image=entry.match.image is not None,
                by_proposed_artist=entry.by_proposed_artist,
            )
            for entry in found.matches
        ],
    )


@router.put("/candidates/{work_id}/wikidata-item")
def pick_wikidata_item(request: Request, work_id: str, body: PickItem) -> CandidateWorkOut:
    """Record the item the curator picked; a re-search then asks Commons by it."""
    return _candidate_work(_services(request).wikidata_match.pick(work_id, body.qid))


@router.post("/candidate-images/{image_id}/select")
def select_candidate_image(request: Request, image_id: str, body: SelectImage) -> SelectedImageOut:
    """Make this the scan the work stands on, over the one the pipeline chose."""
    return _selected(_services(request).discovery.select_image(image_id, rationale=body.rationale))


@router.post("/candidate-images/{image_id}/reject")
def reject_candidate_image(request: Request, image_id: str) -> CandidateWorkOut:
    """Turn down a scan and keep the work. Nothing looks again until asked.

    Returns the work rather than the instance, because the work may be what
    changed: turning down the scan on offer makes it `wanted` — "I want this
    painting; this scan is not good enough" — while turning down an alternate
    leaves its verdict where it was. The card repaints from whichever it is.
    """
    return _candidate_work(_services(request).discovery.reject_image(image_id))


@router.get("/candidate-images/{image_id}/preview", response_class=Response)
def get_candidate_preview(
    request: Request,
    image_id: str,
    size: Annotated[Literal["card", "large"], Query()] = "card",
) -> Response:
    """The picture for one instance, from the picture store, never from a source.

    `size=large` is the picture a review card opens in place when it is
    clicked: the store's larger tier, the source's preview at its own size up to
    2,048 px (`ENLARGED_MAX_EDGE_PX`). The default is the card's own, the
    smaller tier, small enough for a page of them. Any other value is refused
    rather than read as the default, so a misspelt request is not quietly
    answered small.

    The kept file's bytes as they are: the store re-encoded every picture as
    JPEG when it kept it, so one media type is already true and nothing is
    rendered per request.

    No conditional handling, unlike the catalogue's thumbnail. That one is a file
    regenerated under the same name when a master is replaced, so a client must
    revalidate it; these never change behind an image id, so `immutable` answers
    instead.
    """
    rendered = _services(request).review.preview_image(image_id, enlarged=size == "large")
    return Response(content=rendered.data, media_type=rendered.media_type, headers={"Cache-Control": PREVIEW_CACHE_CONTROL})


# -- images -------------------------------------------------------------------


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
    """The wall render, mat and all, at a size the Work page's column draws sharply.

    Drawn from the current television canvas, or from the master where the work
    has none yet; the work's `image.source_kind` says which.
    """
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

    Stated as three cases because the previous version described the `*` one in
    its docstring and did not implement it — which is exactly the defect the
    conditional check above exists to fix, one function later.
    """
    if not header:
        return False
    offered = {tag.strip() for tag in header.split(",")}
    if "*" in offered:
        return True
    return etag in {tag.removeprefix("W/") for tag in offered}


# -- shaping ------------------------------------------------------------------


def service_error_response(message: str) -> JSONResponse:
    """The one error shape this surface returns.

    A single status for every refusal, because the service layer raises a single
    type by design and a per-error translation table here is what turns a thin
    binding into a thick one. The message is written to be shown: it names what
    was wrong and, where there is one, the thing to do instead.
    """
    return JSONResponse(status_code=400, content={"error": message})


def _theme_detail(services: Services, theme_id: str) -> ThemeDetailOut:
    """A theme with its works, in curated order."""
    theme = services.display.get_theme(theme_id)
    return ThemeDetailOut(
        theme=_theme(theme),
        # Two calls composed, as the MCP binding composes them: Programming's
        # order, and the Library's account of each work.
        works=[_work(entry) for entry in services.survey.survey_works(services.display.theme_work_ids(theme_id))],
        shuffled=services.display.shuffles(theme),
    )


#: How many pictures a Themes index card draws. Enough to say what a theme looks
#: like at a glance, few enough that ten cards fit on one screen.
THEME_CARD_PICTURES = 4


def _theme_list(services: Services) -> ThemeListOut:
    """Every theme the index lists, each with what its card shows.

    Two planes composed, as `_theme_detail` composes them: Programming names
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


def _theme_option(option: ThemeCount) -> ThemeOptionOut:
    return ThemeOptionOut(
        theme_id=option.theme.id,
        name=option.theme.name,
        count=option.count,
        selected=option.selected,
        disabled=option.disabled,
    )


def _work(survey: WorkSurvey) -> WorkOut:
    artwork = survey.detail.artwork
    return WorkOut(
        artwork_id=artwork.id,
        title=artwork.title,
        artist=None if survey.detail.artist is None else _artist(survey.detail.artist),
        date_created=artwork.date_created,
        medium=artwork.medium,
        dimensions=artwork.dimensions,
        description=artwork.description,
        commentary=artwork.commentary,
        rights=artwork.rights,
        status=str(artwork.status),
        wikidata_qid=artwork.wikidata_qid,
        wikidata_qid_set_by=_set_by(artwork.wikidata_qid_set_by),
        fit=None if survey.fit is None else _fit(survey.fit),
        fit_note=survey.fit_note,
        image=ImageOut(
            available=survey.image.available,
            source_kind=survey.image.source_kind,
            note=survey.image.note,
        ),
    )


def _dossier(dossier: WorkDossier) -> WorkDetailOut:
    return WorkDetailOut(
        work=_work(dossier.survey),
        original=None if dossier.original is None else _original(dossier.original),
        sources=[_source(source) for source in dossier.sources],
        renditions=[_rendition(view) for view in dossier.renditions],
        mat_colors=[_mat_color(mat) for mat in dossier.mat_colors],
        facets=[_facet(facet) for facet in dossier.facets],
        acquisition=None if dossier.acquisition is None else _acquisition(dossier.acquisition),
    )


def _acquisition(state: AcquisitionState) -> AcquisitionStateOut:
    return AcquisitionStateOut(
        artwork_id=state.artwork_id,
        phase=str(state.phase),
        failures=state.failures,
        detail=state.detail,
        next_try_at=None if state.next_try_at is None else state.next_try_at.isoformat(),
        since=None if state.since is None else state.since.isoformat(),
        condition=state.condition,
        remedy=state.remedy,
    )


def _queue_pause(pause: QueuePause) -> QueuePauseOut:
    return QueuePauseOut(condition=pause.condition, detail=pause.detail, since=pause.since.isoformat(), remedy=pause.remedy)


def _queued_work(entry: QueueEntry) -> QueuedWorkOut:
    return QueuedWorkOut(title=entry.title, acquisition=_acquisition(entry.state))


def _failure_cause(group: FailureCause) -> FailureCauseOut:
    return FailureCauseOut(cause=group.cause, works=len(group.entries), failed=group.failed, gave_up=group.gave_up)


def _queue_page[T](items: Sequence[T], limit: int | None, offset: int) -> tuple[int, Sequence[T]]:
    """One page of a queue listing, at the service's default size and within its cap, as the other listings page.

    The listing is built whole and sliced here: the queue owes a few thousand
    works at most, and grouping by cause needs every one of them in hand.
    """
    resolved = DEFAULT_LIST_LIMIT if limit is None else limit
    if not 1 <= resolved <= MAX_LIST_LIMIT:
        raise ServiceError(f"limit must be between 1 and {MAX_LIST_LIMIT}, got {resolved}.")
    if offset < 0:
        raise ServiceError(f"offset cannot be negative, got {offset}.")
    return resolved, items[offset : offset + resolved]


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


def _artist(artist: Artist) -> ArtistOut:
    return ArtistOut(
        artist_id=artist.id,
        name=artist.name,
        nationality=artist.nationality,
        born=artist.born,
        died=artist.died,
        lifespan_text=artist.lifespan_text,
        biography=artist.biography,
        family_name=artist.family_name,
        given_name=artist.given_name,
        display_nationality=artist.display_nationality,
        wikidata_qid=artist.wikidata_qid,
        wikidata_qid_set_by=_set_by(artist.wikidata_qid_set_by),
    )


def _held_artist(entry: HeldArtist) -> HeldArtistOut:
    return HeldArtistOut(artist=_artist(entry.artist), held=entry.held, pictured_artwork_id=entry.pictured)


def _set_by(value: IdentitySetBy | None) -> str | None:
    return None if value is None else str(value)


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


def _theme(theme: Theme) -> ThemeOut:
    return ThemeOut(
        theme_id=theme.id,
        name=theme.name,
        description=theme.description,
        rotation_interval_seconds=theme.rotation_interval_seconds,
        shuffle=theme.shuffle,
        created_at=theme.created_at.isoformat(),
        is_default=theme.is_default,
        hidden=theme.hidden,
    )


def _wall(view: WallView) -> WallOut:
    return WallOut(
        wall_id=view.wall.id,
        name=view.wall.name,
        created_at=view.wall.created_at.isoformat(),
        theme=None if view.hanging is None else _theme(view.hanging),
        directive_sequence=view.directive.sequence,
        pinned_work_id=view.directive.pinned_work_id,
        client_id=view.wall.client_id,
        output=view.wall.output,
        display_state=_display_state(view.display_state),
    )


def _instant(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


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


def _client(view: ClientView) -> ClientOut:
    client = view.client
    reading = view.heartbeat
    return ClientOut(
        client_id=client.id,
        name=client.name,
        created_at=client.created_at.isoformat(),
        token_issued_at=None if client.token_issued_at is None else client.token_issued_at.isoformat(),
        # Every wall a client listing holds is assigned, so it has an output.
        walls=[ClientWallOut(wall_id=wall.id, name=wall.name, output=wall.output or "") for wall in view.walls],
        heartbeat=ClientHeartbeatOut(
            reported_at=None if reading.reported_at is None else reading.reported_at.isoformat(),
            age_seconds=reading.age_seconds,
            absent=reading.absent,
            problem=reading.problem,
            description=reading.describe(),
            outputs=[
                ReportedOutputOut(
                    name=output.name,
                    kind=output.kind,
                    connected=output.connected,
                    screen=None if output.screen is None else list(output.screen),
                )
                for output in reading.outputs
            ],
        ),
    )


def _directive(directive: Directive) -> DirectiveOut:
    return DirectiveOut(
        wall_id=directive.wall_id,
        sequence=directive.sequence,
        pinned_work_id=directive.pinned_work_id,
    )


def _placement(placement: ThemePlacement) -> ThemePlacementOut:
    return ThemePlacementOut(
        theme=_theme(placement.theme),
        hanging_on=[WallRefOut(wall_id=wall.id, name=wall.name) for wall in placement.walls],
    )


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
                render_path=entry.render_path,
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
        directive_sequence=build.directive_sequence,
        pinned_work_id=build.pinned_work_id,
        # The build's own sentence, not a second one written here: the tool
        # surface states the same fact, and two hand-written versions drift.
        summary=build.summarise(),
    )


def _run(run: DiscoveryRun) -> RunOut:
    return RunOut(
        run_id=run.id,
        kind=str(run.kind),
        status=str(run.status),
        is_terminal=run.status.is_terminal,
        initiated_by=str(run.initiated_by),
        intent=run.intent_text,
        strategy=run.strategy,
        approval_required=run.approval_required,
        estimated_cost_usd=None if run.estimated_cost_usd is None else str(run.estimated_cost_usd),
        actual_cost_usd=None if run.actual_cost_usd is None else str(run.actual_cost_usd),
        unresolved_work_count=run.unresolved_work_count,
        parent_run_id=run.parent_run_id,
        started_at=run.started_at.isoformat(),
        completed_at=None if run.completed_at is None else run.completed_at.isoformat(),
        destination_theme_id=run.destination_theme_id,
        end_reason=run.end_reason,
    )


def _run_view(view: RunView) -> RunViewOut:
    """A run with its works and both of its tallies.

    Every figure is read off the view's own properties rather than recomputed
    here. The counts and the list they describe would otherwise be two
    derivations of one fact, and the second is the one that goes wrong — which is
    not hypothetical: a run-level figure computed as `len(works)` beside a view
    that counted provenance apart is exactly the defect that reached a review.
    """
    return RunViewOut(
        run=_run(view.run),
        tally=RunTallyOut(
            total=view.work_count,
            proposed=view.proposed_count,
            offered=view.offered_count,
            chosen=view.chosen_count,
            resolved=view.resolved,
            resolved_proposals=view.resolved_proposals,
            unresolved=view.unresolved,
            pending=view.pending,
        ),
        works=[_candidate_work(work) for work in view.works],
        searches=SearchUsageOut(
            used=view.searches_used,
            allowance=view.search_allowance,
            exhausted=view.searches_exhausted,
        ),
        image_resolution_available=view.image_resolution_available,
    )


def _candidate_work(work: CandidateWork) -> CandidateWorkOut:
    return CandidateWorkOut(
        work_id=work.id,
        artwork_id=work.artwork_id,
        title=work.proposed_title,
        artist=work.proposed_artist,
        rationale=work.rationale,
        provenance=str(work.provenance),
        offered_for_artist=work.offered_for_artist,
        offered_artist_matched=work.offered_artist_matched,
        wikidata_qid=work.wikidata_qid,
        verdict=str(work.verdict),
        decided=work.verdict.is_terminal,
        resolution_status=str(work.resolution_status),
        unresolved_reason=None if work.unresolved_reason is None else str(work.unresolved_reason),
        confirmation=str(work.confirmation),
    )


def _wanted_work(view: WantedView) -> WantedWorkOut:
    entry = view.wanted
    work = entry.work
    return WantedWorkOut(
        work_id=work.id,
        title=work.proposed_title,
        artist=work.proposed_artist,
        run_id=work.discovery_run_id,
        wikidata_qid=work.wikidata_qid,
        scans_turned_down=entry.scans_turned_down,
        shown=None if view.shown is None else _instance(view.shown),
    )


def _candidate_page(page: CandidatePage) -> CandidatePageOut:
    return CandidatePageOut(
        run=_run(page.run),
        works=[_candidate_card(entry) for entry in page.entries],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        # The page's own property, not `offset + len(works) < total` recomputed
        # here. Two derivations of one fact is how a grid comes to promise a next
        # page that does not exist, and the second derivation is the wrong one.
        truncated=page.truncated,
    )


def _candidate_card(view: CandidateView) -> CandidateCardOut:
    return CandidateCardOut(
        work=_candidate_work(view.work),
        shown=None if view.shown is None else _instance(view.shown),
        shown_is_on_offer=view.shown_is_on_offer,
        instances_held=view.instances_held,
        instances_surviving=view.instances_surviving,
        held_artwork_id=view.held_artwork_id,
    )


def _instance_listing(listing: InstanceListing) -> InstanceListingOut:
    return InstanceListingOut(
        work=_candidate_work(listing.work),
        instances=[_instance(instance) for instance in listing.instances],
        held=listing.held,
        surviving_held=listing.surviving_held,
        truncated=listing.truncated,
        shows_every_choosable_instance=listing.shows_every_choosable_instance,
    )


def _instance(view: InstanceView) -> InstanceOut:
    image = view.image
    return InstanceOut(
        image_id=image.id,
        work_id=image.candidate_work_id,
        url=image.url,
        provider=image.provider,
        confidence=image.confidence,
        is_selected=image.is_selected,
        rejected=view.rejected,
        rights_status=None if image.rights_status is None else str(image.rights_status),
        selection_rationale=image.selection_rationale,
        width=image.estimated_width,
        height=image.estimated_height,
        fit=None if view.fit is None else _fit(view.fit),
        fit_note=view.fit_note,
        # The view's own property. It is not `preview is not None` here, because
        # this surface asks for its pictures by URL and takes none inline — see
        # `InstanceView.preview_available`, which is why that property exists.
        preview_available=view.preview_available,
        preview_note=view.preview_note,
    )


def _verdict(outcome: VerdictOutcome) -> VerdictOut:
    work = outcome.work
    return VerdictOut(
        work=_candidate_work(work),
        artwork_id=work.artwork_id,
        decided_at=None if work.decided_at is None else work.decided_at.isoformat(),
        minted_artist=None if outcome.minted_artist is None else _artist(outcome.minted_artist),
        possible_duplicate_artists=[_artist(artist) for artist in outcome.duplicate_candidates],
        notice=_verdict_notice(outcome),
    )


def _verdict_notice(outcome: VerdictOutcome) -> str | None:
    """Say what acceptance did that the work's own fields do not show.

    Only the artist. Minting one is the single part of a promotion a curator can
    neither see in the accepted work nor undo from it — a duplicate row looks
    exactly like a painter newly encountered — so it is said in words at the
    moment it happens, where a field on a payload nobody re-reads would not
    reach them.

    **This is a byte-for-byte copy of `mcp/bindings.py`'s, and that is now
    stated rather than explained away.** The paragraph here used to claim the
    divergence the run-view sentence really has — "that one is written for a
    model and names tool calls in backticks; this one is read by a person" —
    which is true of `runSentence` and simply false of this: the text names
    artists, not tool calls, and the two functions are identical.

    They stay two, because the day one of them does need a reader-specific
    word is the day sharing them would be in the way, and because merging a
    formatter across the surfaces is what `architecture.md`'s 2026-07-27 entry
    declines. What changed is that the copy is held identical by
    `tests/unit/test_surface_parity.py` rather than by a docstring asserting a
    difference that was not there.
    """
    minted = outcome.minted_artist
    # Both conditions rather than the one that carries the message. Near-misses
    # are reported only alongside a mint, so `minted is None` here is currently
    # unreachable — but the sentence names the minted row, and deriving that it
    # exists from a *different* field being non-empty is how a payload comes to
    # say `None` where a name belongs the day the service reports near-misses for
    # anything else.
    if minted is None or not outcome.duplicate_candidates:
        return None
    names = ", ".join(repr(artist.name) for artist in outcome.duplicate_candidates)
    return (
        f"A new artist {minted.name!r} was recorded, and the catalogue already holds {names}. They may be "
        "the same painter under different spellings; matching is exact, because a wrong merge puts another "
        "painter's name on a label and leaves no trace. Both rows stand until someone decides."
    )


def _selected(image: CandidateImage) -> SelectedImageOut:
    return SelectedImageOut(
        image_id=image.id,
        work_id=image.candidate_work_id,
        url=image.url,
        selection_rationale=image.selection_rationale,
    )


def _estimate(estimate: Estimate) -> EstimateOut:
    return EstimateOut(
        phase=estimate.phase,
        # A string rather than a float, for the same reason the MCP surface does
        # it: a price through binary floating point comes back as
        # 0.12699999999999999.
        estimated_cost_usd=str(estimate.cost_usd),
        tier=str(estimate.tier),
        basis=estimate.basis,
        run_id=estimate.run_id,
    )


def _spend(report: SpendReport) -> SpendOut:
    return SpendOut(
        scope=report.scope,
        cost_usd=str(report.cost_usd),
        run_id=report.run_id,
        year=report.year,
        month=report.month,
    )


def _health(reading: HealthReading) -> HealthOut:
    return HealthOut(
        walls=[
            WallHeartbeatOut(wall_id=seen.wall.id, wall_name=seen.wall.name, heartbeat=_heartbeat(seen.heartbeat))
            for seen in reading.walls
        ],
        description=reading.describe(),
        backup=_backup(reading.backup),
        sources=[_source_plugin(each) for each in reading.sources],
        pictures=_pictures(reading.pictures),
    )


def _pictures(reading: PicturesReading) -> PicturesOut:
    return PicturesOut(
        pictures_bytes=reading.pictures_bytes,
        pictures_files=reading.pictures_files,
        age_seconds=reading.age_seconds,
        unreadable=reading.unreadable,
        description=reading.describe(),
    )


def _source_plugin(health: SourceHealth) -> SourcePluginOut:
    reading = health.reading
    return SourcePluginOut(
        name=reading.name,
        state=reading.state.value,
        reason=reading.reason,
        faults=reading.faults,
        last_fault_at=None if reading.last_fault_at is None else reading.last_fault_at.isoformat(),
        last_fault_age_seconds=health.last_fault_age_seconds,
        last_fault=reading.last_fault,
        description=health.describe(),
        distribution=reading.identity.distribution,
        version=reading.identity.version,
        api_major=reading.identity.api_major,
        provides=[part.value for part in reading.identity.provides],
    )


def _heartbeat(reading: HeartbeatReading) -> HeartbeatOut:
    return HeartbeatOut(
        path=str(reading.path),
        reported_at=None if reading.reported_at is None else reading.reported_at.isoformat(),
        age_seconds=reading.age_seconds,
        absent=reading.absent,
        problem=reading.problem,
        description=reading.describe(),
        reported=reading.contents,
    )


def _backup(reading: BackupReading) -> BackupOut:
    return BackupOut(
        path=str(reading.path),
        completed_at=None if reading.completed_at is None else reading.completed_at.isoformat(),
        age_seconds=reading.age_seconds,
        absent=reading.absent,
        problem=reading.problem,
        description=reading.describe(),
        reported=reading.contents,
    )


def _look(view: LookView) -> LookOut:
    return LookOut(
        qid=view.qid,
        state=str(view.state),
        note=view.note,
        held_artwork_ids=list(view.held),
        sources=[_look_source(source) for source in view.sources],
        pictures=[_look_picture(picture) for picture in view.pictures],
    )


def _look_source(source: SourceLook) -> LookSourceOut:
    return LookSourceOut(
        provider=source.provider,
        state=str(source.state),
        found=len(source.pictures),
        refusals=sorted(str(reason) for reason in source.refusals),
        answered_at=None if source.answered_at is None else source.answered_at.isoformat(),
        retry_at=None if source.retry_at is None else source.retry_at.isoformat(),
    )


def _look_picture(picture: LookPicture) -> LookPictureOut:
    judged = picture.judged
    found = judged.found
    return LookPictureOut(
        key=picture.key,
        provider=found.provider,
        url=found.url,
        title=found.title,
        artist=found.artist,
        width=found.estimated_width,
        height=found.estimated_height,
        fit=_fit(judged.fit),
        below_floor=judged.below_floor,
        confidence=judged.confidence,
        rights_status=None if found.rights_status is None else str(found.rights_status),
        selection_rationale=judged.rationale,
    )


def _fit(fit: FitAssessment) -> FitOut:
    """A display-fit verdict as every surface that shows one carries it: the work, a scan, a registry picture."""
    return FitOut(
        verdict=str(fit.fit),
        rendered_width=fit.rendered_width,
        rendered_height=fit.rendered_height,
        rendered_long_edge_inches=fit.rendered_long_edge_inches,
    )


# -- conversations ------------------------------------------------------------
#
# One block at the foot of the file rather than routes among the routes and
# mappers among the mappers, and it is a merge decision rather than a taste one:
# three chunks were appending to this module at once, and a block that touches no
# existing line cannot conflict with the other two. Route registration is by
# decorator at import, so position changes nothing about what is served.


@router.get("/conversations")
def list_conversations(request: Request) -> ConversationListOut:
    conversations = _services(request).conversation.list_conversations()
    return ConversationListOut(
        conversations=[_conversation(conversation) for conversation in conversations],
        count=len(conversations),
    )


@router.post("/conversations")
def start_conversation(request: Request) -> ConversationViewOut:
    """Open an empty thread.

    No body, and nothing spent. A curator who opens a conversation and thinks
    better of it has cost the household a row; the first question is a turn like
    every other.
    """
    return _conversation_view(_services(request).conversation.start())


@router.get("/conversations/{conversation_id}")
def get_conversation(request: Request, conversation_id: str) -> ConversationViewOut:
    return _conversation_view(_services(request).conversation.get(conversation_id))


@router.get("/conversations/{conversation_id}/estimate")
def get_turn_estimate(request: Request, conversation_id: str) -> EstimateOut:
    """What the next turn in this conversation may cost, for the tier beside Say it.

    Free and read-only, like `GET /api/estimate`, and the same shape with
    `phase` `conversation_turn`: an estimate shown before spending, never a
    reading of what was spent.
    """
    return _estimate(_services(request).conversation.estimate(conversation_id))


@router.post("/conversations/{conversation_id}/turns")
def speak(request: Request, conversation_id: str, body: Speak) -> ConversationViewOut:
    """Ask something, or — with no text — ask again for the last answer.

    **A turn that could not be answered is a 200, not a 400.** The requirement is
    that a failed turn stays in the thread and is retryable, and an error body
    carries no thread: the client would show a sentence with the curator's
    question nowhere on screen. So the refusal travels as `failure` on the view,
    and only a request that recorded nothing at all — an unknown conversation,
    empty text with nothing outstanding to retry — is a refusal.
    """
    return _conversation_view(_services(request).conversation.speak(conversation_id, body.text))


@router.post("/conversations/{conversation_id}/commit")
def commit_conversation(request: Request, conversation_id: str, body: CommitDirection) -> ConversationViewOut:
    """Seed a discovery run from this thread, and stay in the thread.

    Returns the conversation rather than the run, and the difference is the whole
    seam: a response shaped like a run is a response a client navigates to. What
    comes back is the transcript with a committed turn at the end of it, which is
    what the commit card repaints itself from without going anywhere.
    """
    return _conversation_view(_services(request).conversation.commit(conversation_id, body.intent))


def _conversation(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        conversation_id=conversation.id,
        started_at=conversation.started_at.isoformat(),
        last_turn_at=conversation.last_turn_at.isoformat(),
        summary=conversation.summary,
    )


def _conversation_view(view: ConversationView) -> ConversationViewOut:
    unanswered = view.unanswered
    return ConversationViewOut(
        conversation=_conversation(view.conversation),
        turns=[_conversation_turn(turn) for turn in view.turns],
        committed_run_id=view.committed_run_id,
        failure=view.failure,
        unanswered_turn_id=None if unanswered is None else unanswered.id,
    )


def _conversation_turn(view: TurnView) -> ConversationTurnOut:
    return ConversationTurnOut(
        turn_id=view.turn.id,
        ordinal=view.turn.ordinal,
        role=str(view.turn.role),
        text=view.turn.text,
        suggested=[
            SuggestionOut(
                kind=suggestion.kind,
                value=suggestion.value,
                samples=[SampleOut(title=sample.title, artist=sample.artist, image_url=sample.image_url) for sample in samples],
            )
            for suggestion, samples in view.suggested
        ],
        committed_run_id=view.turn.committed_run_id,
        created_at=view.turn.created_at.isoformat(),
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(request: Request, conversation_id: str) -> ConversationDeletionOut:
    """Destroy the thread and its turns, and detach everything derived from them.

    **The one operation in this product that genuinely destroys a record**, which
    is exactly why what stands on it is detached rather than destroyed with it:
    `Affinity.source_turn_id` and `SpendRecord.conversation_turn_id` are nulled,
    and nothing else is touched. An affinity is a judgment accumulated across
    conversations and cannot be reconstructed from a thread that no longer exists;
    a spend record is a ledger entry, and a month total that fell because somebody
    tidied would be a number that lies about the past.

    **The response names the consequence, not the row count.** What the curator
    loses is the ability to rebuild those judgments when the derivation improves,
    and `description` says so in those terms — the counts are there to qualify it.
    """
    return _conversation_deletion(_services(request).conversation.delete(conversation_id))


def _conversation_deletion(deletion: ConversationDeletion) -> ConversationDeletionOut:
    return ConversationDeletionOut(
        conversation_id=deletion.conversation_id,
        turns_deleted=deletion.turns_deleted,
        affinities_detached=deletion.affinities_detached,
        spend_records_detached=deletion.spend_records_detached,
        runs_unattributed=deletion.runs_unattributed,
        # Composed by the service so this surface and the tool one cannot come to
        # describe the same destruction differently.
        description=deletion.describe(),
    )


# -- taste --------------------------------------------------------------------


@router.get("/affinities")
def list_affinities(
    request: Request,
    kind: Annotated[str | None, Query()] = None,
    sentiment: Annotated[str | None, Query()] = None,
    derivation: Annotated[str | None, Query()] = None,
) -> AffinityListOut:
    """The curator's standing judgments, narrowed by any of the three.

    Unpaged: this is a household's whole taste, which is tens of rows, and a page
    over it would be a second way to read what one call hands back whole.
    """
    affinities = _services(request).taste.list_affinities(kind=kind, sentiment=sentiment, derivation=derivation)
    return AffinityListOut(affinities=[_affinity(entry) for entry in affinities], count=len(affinities))


@router.post("/affinities")
def set_affinity(request: Request, body: SetAffinity) -> AffinityOut:
    """Write one judgment over whatever was there, or write the first one.

    `POST` rather than `PATCH` because this surface writes with `POST` everywhere
    and one surface with two spellings for "change this" costs more than the
    orthodoxy is worth. It is an upsert addressed by (`kind`, `value`), so a
    correction needs no id — which is right for the caller that has a name in a
    sentence rather than a row it fetched.
    """
    return _affinity(
        _services(request).taste.set_affinity(
            kind=body.kind,
            value=body.value,
            sentiment=body.sentiment,
            open_to_more=body.open_to_more,
            derivation=body.derivation,
            rationale=body.rationale,
            source_turn_id=body.source_turn_id,
        )
    )


@router.delete("/affinities/{affinity_id}")
def delete_affinity(request: Request, affinity_id: str) -> AffinityOut:
    """Forget one judgment, and answer with what was forgotten.

    The row rather than an acknowledgement of the id, because this is not
    recoverable: a confirmation should name the thing that is gone rather than the
    handle it was addressed by.
    """
    return _affinity(_services(request).taste.delete_affinity(affinity_id))


def _affinity(view: AffinityView) -> AffinityOut:
    affinity = view.affinity
    return AffinityOut(
        affinity_id=affinity.id,
        kind=str(affinity.kind),
        value=affinity.value,
        sentiment=str(affinity.sentiment),
        open_to_more=affinity.open_to_more,
        derivation=str(affinity.derivation),
        rationale=affinity.rationale,
        source_turn_id=affinity.source_turn_id,
        # Resolved by the service from the cited turn rather than stored, so the
        # link and the citation cannot come apart — and absent for a judgment
        # whose conversation was deleted, which is what stops the screen offering
        # a way through to a thread that is not there.
        conversation_id=view.conversation_id,
        artist_id=affinity.artist_id,
        created_at=affinity.created_at.isoformat(),
        updated_at=affinity.updated_at.isoformat(),
    )
