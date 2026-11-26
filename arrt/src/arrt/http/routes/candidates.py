"""The routes for what a discovery run found: a candidate, its images, the verdict on each, and the wanted list."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from arrt.http.models import (
    CandidateCardOut,
    CandidateWorkOut,
    InstanceListingOut,
    InstanceOut,
    PickItem,
    SelectedImageOut,
    SelectImage,
    SetVerdict,
    SightingHostOut,
    SightingHostsOut,
    VerdictOut,
    WantedListingOut,
    WantedWorkOut,
    WantWork,
    WorkMatchesOut,
    WorkMatchOut,
)
from arrt.http.routes.common import API_PREFIX, PREVIEW_CACHE_CONTROL, _services
from arrt.http.routes.shapes import _artist, _fit
from arrt.library.services.discovery import VerdictOutcome
from arrt.library.services.review import CandidateView, InstanceListing, InstanceView, WantedView
from arrt.persistence.discovery_records import CandidateImage, CandidateWork

router = APIRouter(prefix=API_PREFIX)


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
        offered_by=work.offered_by,
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

    **This is a byte-for-byte copy of `mcp/bindings.py`'s, and that is stated
    rather than explained away.** The run-view sentence really does diverge —
    that one is written for a model and names tool calls in backticks; this one
    is read by a person — which is true of `runSentence` and false of this: the
    text names artists, not tool calls, and the two functions are identical.

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
        f"A new artist {minted.name!r} was recorded, and the Library already holds {names}. They may be "
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
