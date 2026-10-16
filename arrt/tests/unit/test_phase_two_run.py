"""Phase 2 as the run actually performs it: instances recorded, and what is not.

Driven through the runner rather than the engine, because what is under test
here is the difference between judging an instance and *acting* on the
judgement — which instance the work ends up representing itself by, which works
end up `unresolved`, and where a run stops.

Phase 2 runs on the calling thread in these tests, via the `spawn` seam. The
threaded path is exercised where its behaviour matters, against a real server
over real HTTP.
"""

import logging
from dataclasses import replace

import pytest
from fakes import FakeFinder, a_decodable_jpeg, a_roster, a_work, an_image
from PIL import Image

from arrt.library.discovery.engine import WorkList
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.services.pictures import PictureStore
from arrt.library.services.previews import PreviewCache
from arrt.library.services.runner import DiscoveryRunner
from arrt.persistence.discovery_records import InitiatedBy, ResolutionStatus, RunStatus, Verdict
from arrt.persistence.records import AcquisitionMethod, SourceClass
from arrt.services.container import Services
from arrt.services.errors import ServiceError


def a_list(*titles: str, artist: str | None = "Salvador Dalí") -> WorkList:
    return WorkList(works=tuple(a_work(title, artist=artist) for title in titles))


@pytest.fixture
def museum() -> FakeFinder:
    return FakeFinder()


@pytest.fixture
def previews(settings, museum) -> PreviewCache:
    return PreviewCache(PictureStore(settings.pictures_path, art_root=settings.art_root, sources=ImageSourcePool([museum])))


@pytest.fixture
def runner(services, engine, settings, museum, previews) -> DiscoveryRunner:
    """A runner that resolves images, everything on the calling thread."""
    return DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(ImageSourcePool([museum]), profile=settings.quality_profile),
        previews=previews,
        spawn=lambda work: work(),
    )


def start(runner: DiscoveryRunner):
    return runner.start(intent_text="Surrealist paintings with strong blues", initiated_by=InitiatedBy.MCP_CLIENT)


# -- the happy path, end to end -------------------------------------------------


def test_a_run_that_finds_images_completes_under_its_own_power(services, engine, runner, museum):
    """The state that used to be a dead end is now one a run passes through."""
    engine.result = a_list("The Elephants")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).status is RunStatus.COMPLETED
    work = services.discovery.list_candidate_works(run_id)[0]
    assert work.resolution_status is ResolutionStatus.RESOLVED
    images = services.discovery.list_candidate_images(work.id)
    assert len(images) == 1
    assert images[0].is_selected is True
    assert images[0].selection_rationale, "the card has to be able to say why this one"


def test_the_selected_instance_carries_the_facts_a_review_card_needs(services, engine, runner, museum):
    engine.result = a_list("The Elephants")
    museum.holdings = {"The Elephants": (an_image("The Elephants", width=6949, height=8400),)}

    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    image = services.discovery.list_candidate_images(work.id)[0]

    assert image.provider == "artic"
    assert (image.estimated_width, image.estimated_height) == (6949, 8400)
    assert image.confidence > 0
    assert image.quality_score is not None
    assert image.preview_path is not None


def test_alternates_are_retained_rather_than_discarded(services, engine, runner, museum):
    """Losing instances are the alternates a card offers and the sources a work keeps."""
    engine.result = a_list("The Elephants")
    museum.holdings = {
        "The Elephants": (
            an_image("The Elephants", width=2000, height=1500),
            an_image("The Elephants", width=6949, height=8400),
        )
    }

    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    images = services.discovery.list_candidate_images(work.id)

    assert len(images) == 2
    assert sum(1 for image in images if image.is_selected) == 1
    assert next(image for image in images if image.is_selected).estimated_width == 6949


# -- unresolved is an outcome, never an omission --------------------------------


def test_a_work_no_museum_holds_lands_unresolved_and_is_reported(services, engine, runner, museum):
    """The fake answers as the live API does: plausible results, none of them the work."""
    engine.result = a_list("The Persistence of Memory")
    museum.holdings = {}

    run_id = start(runner).id

    work = services.discovery.list_candidate_works(run_id)[0]
    assert work.resolution_status is ResolutionStatus.UNRESOLVED
    assert services.discovery.list_candidate_images(work.id) == []
    # Reported, not dropped: the run still knows about it.
    results = services.discovery.run_results(run_id)
    assert [candidate.id for candidate in results.unresolved] == [work.id]


def test_a_mixed_run_reports_both_outcomes_and_still_completes(services, engine, runner, museum):
    engine.result = a_list("The Elephants", "The Persistence of Memory")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}

    run_id = start(runner).id

    results = services.discovery.run_results(run_id)
    assert services.discovery.get_run(run_id).status is RunStatus.COMPLETED
    assert len(results.resolved) == 1
    assert len(results.unresolved) == 1


# -- the floor ------------------------------------------------------------------


def test_a_below_floor_instance_is_recorded_but_never_selected_for_the_curator(services, engine, runner, museum):
    """Shown, labelled, and left unselected — and the work is `unresolved` because of it.

    This is the specified behaviour in full: nothing is hidden and nothing is
    silently accepted. A curator who wants the small scan can still choose it; a
    curator who does nothing does not end up with a postage stamp on the wall.
    """
    engine.result = a_list("Small Study")
    museum.holdings = {"Small Study": (an_image("Small Study", width=600, height=450),)}

    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    images = services.discovery.list_candidate_images(work.id)

    assert len(images) == 1, "the instance is offered, not hidden"
    assert images[0].is_selected is False, "and never chosen without being asked for"
    assert "below the quality minimum" in images[0].selection_rationale
    assert work.resolution_status is ResolutionStatus.UNRESOLVED


def test_a_curator_may_still_select_a_below_floor_instance_by_name(services, engine, runner, museum):
    """Not a rejection. The floor withholds automatic selection and nothing else."""
    engine.result = a_list("Small Study")
    museum.holdings = {"Small Study": (an_image("Small Study", width=600, height=450),)}
    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    small = services.discovery.list_candidate_images(work.id)[0]

    chosen = services.discovery.select_image(small.id, rationale="I want this one anyway")

    assert chosen.is_selected is True


def test_rejecting_the_selected_instance_does_not_fall_through_to_a_below_floor_one(services, engine, runner, museum):
    """The fall-through obeys the same floor the original selection did.

    A curator who turns down the good scan is asking for a better one, not for
    the postage stamp underneath it — and being handed the postage stamp silently
    is the one outcome that would make rejecting an image worse than doing
    nothing. The work goes to `wanted` holding no selection, which is what a
    re-search then acts on.
    """
    engine.result = a_list("The Elephants")
    museum.holdings = {
        "The Elephants": (
            an_image("The Elephants", width=6949, height=8400),
            an_image("The Elephants", width=600, height=450),
        )
    }
    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    selected = next(image for image in services.discovery.list_candidate_images(work.id) if image.is_selected)

    services.discovery.reject_image(selected.id)

    images = services.discovery.list_candidate_images(work.id)
    assert len(images) == 2, "the rejected instance and the small one are both retained"
    assert not any(image.is_selected for image in images), "nothing below the floor was promoted"
    assert services.discovery.get_candidate_work(work.id).verdict is Verdict.WANTED


def test_rejecting_the_selected_instance_does_fall_through_to_one_that_clears_the_floor(services, engine, runner, museum):
    """The floor withholds the inadequate alternate, not every alternate."""
    engine.result = a_list("The Elephants")
    museum.holdings = {
        "The Elephants": (
            an_image("The Elephants", width=6949, height=8400),
            an_image("The Elephants", width=3000, height=2000),
        )
    }
    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    selected = next(image for image in services.discovery.list_candidate_images(work.id) if image.is_selected)

    services.discovery.reject_image(selected.id)

    promoted = [image for image in services.discovery.list_candidate_images(work.id) if image.is_selected]
    assert len(promoted) == 1
    assert promoted[0].estimated_width == 3000


def test_an_instance_that_clears_the_floor_is_preferred_over_one_that_does_not(services, engine, runner, museum):
    engine.result = a_list("The Elephants")
    museum.holdings = {
        "The Elephants": (
            an_image("The Elephants", width=600, height=450),
            an_image("The Elephants", width=6949, height=8400),
        )
    }

    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    selected = next(image for image in services.discovery.list_candidate_images(work.id) if image.is_selected)

    assert selected.estimated_width == 6949
    assert work.resolution_status is ResolutionStatus.RESOLVED


def test_the_minimum_is_the_deployment_s_setting_rather_than_a_constant(
    store, discovery_store, wall_settings, thumbnail_settings, settings, engine, museum
):
    """The same image meets one deployment's minimum and not another's.

    Each minimum gets a whole container built by the same `Services.bind` a
    deployment uses, rather than one service with its profile reassigned —
    reaching into the service to swap a private would test a state no wiring
    produces. Neither value is the default, so a profile left unwired fails.
    """
    engine.result = a_list("Modest Scan")
    museum.holdings = {"Modest Scan": (an_image("Modest Scan", width=1500, height=1200),)}

    verdicts = []
    for minimum in (1200, 2000):
        geometry = replace(settings, quality_minimum_px=minimum)
        plane = Services.bind(
            catalogue=store,
            discovery=discovery_store,
            display_settings=wall_settings,
            thumbnails=thumbnail_settings,
            quality_profile=geometry.quality_profile,
            engine=engine,
            discovery_settings=geometry.discovery_settings,
            sources=a_roster(museum),
        )
        runner = DiscoveryRunner(
            plane.discovery,
            engine,
            geometry.discovery_settings,
            images=PhaseTwoEngine(ImageSourcePool([museum]), profile=geometry.quality_profile),
            previews=PreviewCache(
                PictureStore(geometry.pictures_path, art_root=geometry.art_root, sources=ImageSourcePool([museum]))
            ),
            spawn=lambda work: work(),
        )
        run_id = runner.start(intent_text="anything", initiated_by=InitiatedBy.MCP_CLIENT).id
        verdicts.append(plane.discovery.list_candidate_works(run_id)[0].resolution_status)

    assert verdicts == [ResolutionStatus.RESOLVED, ResolutionStatus.UNRESOLVED]


# -- previews -------------------------------------------------------------------


def test_a_preview_is_cached_on_disk_so_review_survives_the_museum_going_down(services, engine, runner, museum, settings):
    engine.result = a_list("The Elephants")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}

    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    image = services.discovery.list_candidate_images(work.id)[0]

    cached = settings.art_root / image.preview_path
    assert cached.is_file()
    assert cached.is_relative_to(settings.pictures_path)
    # The museum's bytes re-encoded and kept at their own size (the fixture's
    # preview is 1200 x 900, under the store's larger tier), not as they came.
    with Image.open(cached) as kept:
        assert (kept.format, kept.size) == ("JPEG", (1200, 900))
    # Relative to ART_ROOT, like every other path the catalogue holds.
    assert not image.preview_path.startswith("/")
    # And the point of keeping it: the museum gone, the card still has its picture.
    museum.preview_bytes = None
    museum.unreachable = True
    assert services.review.preview_image(image.id).media_type == "image/jpeg"


def test_an_instance_whose_preview_will_not_download_is_still_recorded(services, engine, runner, museum):
    """A missing thumbnail degrades a card; it does not invalidate an instance."""
    engine.result = a_list("The Elephants")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}
    museum.preview_bytes = None

    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    image = services.discovery.list_candidate_images(work.id)[0]

    assert image.preview_path is None
    assert image.preview_url is not None, "the card falls back to the source URL"
    assert image.is_selected is True
    assert work.resolution_status is ResolutionStatus.RESOLVED


# -- reaching the provider, and failing to --------------------------------------


def test_a_work_whose_provider_could_not_be_reached_is_not_called_unresolved(services, engine, runner, museum):
    """ "We looked and it is not there" and "we could not look" lead to opposite actions."""
    engine.result = a_list("The Elephants", "The Persistence of Memory")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}
    museum.fails_for = {"The Persistence of Memory"}

    run_id = start(runner).id

    works = {work.proposed_title: work for work in services.discovery.list_candidate_works(run_id)}
    assert works["The Elephants"].resolution_status is ResolutionStatus.RESOLVED
    assert works["The Persistence of Memory"].resolution_status is ResolutionStatus.PENDING
    assert services.discovery.get_run(run_id).status is RunStatus.COMPLETED


def test_the_completed_notice_does_not_call_an_unreachable_work_unresolved(services, engine, runner, museum):
    """The distinction the chunk exists to protect has to survive to the sentence.

    A run that completed with some works unreachable used to be described as
    having works "reported as unresolved… the signal a proposed work may not
    exist" — which is false about exactly the works it was describing, and false
    in the direction that tells a curator their painting does not exist because a
    museum was briefly down.

    The rate is stated over *proposed* works, because a run may also carry works
    the collection offered, and those arrive with their images already attached:
    counting them would report a retrieval rate nothing achieved.
    """
    from arrt.mcp.bindings import _run_notice

    engine.result = a_list("The Elephants", "The Persistence of Memory", "Galatea of the Spheres")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}
    museum.fails_for = {"Galatea of the Spheres"}
    run_id = start(runner).id

    notice = _run_notice(runner.run_status(run_id, wait=False))

    assert "1 of 3 proposed works has an image" in notice
    assert "1 could not be matched to any image" in notice
    assert "1 could not be looked up at all" in notice
    assert "the image provider was unreachable" in notice


def test_the_completed_notice_stays_a_single_sentence_when_everything_resolved(services, engine, runner, museum):
    """No dangling clauses about zero works — the branches are counted, not always printed."""
    from arrt.mcp.bindings import _run_notice

    engine.result = a_list("The Elephants")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}
    run_id = start(runner).id

    notice = _run_notice(runner.run_status(run_id, wait=False))

    assert notice == "This run finished: 1 of 1 proposed work has an image."


def test_a_run_that_could_not_reach_the_provider_for_anything_fails(services, engine, runner, museum):
    """Completing would report a fact about the works that was never established."""
    engine.result = a_list("The Elephants", "The Persistence of Memory")
    museum.unreachable = True

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).status is RunStatus.FAILED
    assert services.discovery.get_run(run_id).end_reason.startswith(
        "Phase 2 could not reach an image provider for any of this run's 2 works."
    )
    assert all(work.resolution_status is ResolutionStatus.PENDING for work in services.discovery.list_candidate_works(run_id))


def test_a_refusal_recording_phase_two_ends_the_run_with_the_refusal_named(services, engine, runner, museum, monkeypatch):
    """The record layer's own words reach the run, because they say what it would not record.

    Refused at `record_resolution`, the write phase 2 makes for every work, while
    the run is still live: that is what tells this site apart from a cancel, and
    a refusal of `complete_run` itself is read as one by design.
    """
    engine.result = a_list("The Elephants")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}

    def refuse(*args, **kwargs):
        raise ServiceError("Candidate work 'c1' has no image to resolve against.")

    monkeypatch.setattr(services.discovery, "record_resolution", refuse)

    run = services.discovery.get_run(start(runner).id)

    assert run.status is RunStatus.FAILED
    assert run.end_reason == "Phase 2 could not record what it found: Candidate work 'c1' has no image to resolve against."


def test_a_fault_in_phase_two_points_the_run_at_the_log_and_keeps_its_text_there(services, engine, runner, museum, monkeypatch):
    """Exception text can carry paths and addresses; a curator is told where to look instead."""
    engine.result = a_list("The Elephants")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}

    def broken(*args, **kwargs):
        raise RuntimeError("cannot write /srv/arrt/images/tmp")

    monkeypatch.setattr(services.discovery, "record_resolution", broken)

    run = services.discovery.get_run(start(runner).id)

    assert run.status is RunStatus.FAILED
    assert run.end_reason.startswith("Phase 2 failed unexpectedly")
    assert "server log" in run.end_reason
    assert "/srv/arrt" not in run.end_reason


def test_the_failure_log_line_agrees_with_itself_over_a_single_work(services, engine, runner, museum, caplog):
    """Three agreements over one count, on the sentence this failure leaves behind.

    The seventh site of #113 and the last found — in a module the fix had already
    edited and already imported `counted` into, with every test that reaches it
    proposing two works, where all three spellings are right.

    **It is a log line, not a screen**, which is why no surface test could have
    caught it and why it is asserted through `caplog`: `_end` passes the sentence
    to `log.warning` and nothing stores it on the run. That makes it the operator's
    reading rather than the curator's — and the operator is the one person here
    who reads it while deciding whether their museum API is down, so it is held
    to the same rule.
    """
    engine.result = a_list("The Elephants")
    museum.unreachable = True

    with caplog.at_level(logging.WARNING, logger="arrt.library.services.runner"):
        start(runner)

    said = [record.message for record in caplog.records if "could not reach an image provider for any" in record.message]
    assert len(said) == 1, f"the failure sentence was not logged once: {said}"
    notice = said[0]
    assert "any of this run's 1 work." in notice
    assert "whether it exists" in notice
    assert "the work is unchanged" in notice
    # The plural spellings of the same three clauses, so a partial fix fails here
    # rather than passing on the sentence merely being present.
    assert "1 works" not in notice
    assert "they exist" not in notice
    assert "works are unchanged" not in notice


# -- a curator's decision outranks whatever phase 2 is doing --------------------


def test_a_verdict_reached_while_phase_2_ran_is_not_overwritten(services, engine, settings, museum, previews):
    """Only the curator's verdict is authoritative; a resolution reports, never applies.

    Reachable the moment phase 2 exists at all, because a curator reviewing a
    partly resolved run can decide a work while the next one is still being
    searched. `test_resolve_run.py` exercises the same guard against a
    re-search, where the window is wide open rather than incidental.
    """
    engine.result = a_list("The Elephants")
    museum.holdings = {"The Elephants": (an_image("The Elephants"),)}
    run_id = start(
        DiscoveryRunner(
            services.discovery,
            engine,
            settings.discovery_settings,
            images=PhaseTwoEngine(ImageSourcePool([museum]), profile=settings.quality_profile),
            previews=previews,
            spawn=lambda work: work(),
        )
    ).id
    work = services.discovery.list_candidate_works(run_id)[0]
    services.discovery.set_verdict(work.id, Verdict.REJECTED, reason="not for this wall")

    outcome = services.discovery.record_resolution(work.id)

    assert outcome.applied is False
    assert outcome.resolution_status is ResolutionStatus.RESOLVED, "the result is still reported"
    assert services.discovery.get_candidate_work(work.id).verdict is Verdict.REJECTED


def test_a_run_cancelled_mid_resolve_stops_where_it_was(services, engine, settings, museum, previews):
    """A decision arriving partway through is honoured for the works not yet reached."""
    engine.result = a_list("The Elephants", "Swans Reflecting Elephants", "Galatea of the Spheres")
    museum.holdings = {title: (an_image(title),) for title in ("The Elephants", "Swans Reflecting Elephants")}
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(ImageSourcePool([museum]), profile=settings.quality_profile),
        previews=previews,
        spawn=lambda work: work(),
    )

    stop_after_first = museum.find_images

    def cancel_once_started(query):
        result = stop_after_first(query)
        if len(museum.asked) == 1:
            services.discovery.cancel_run(run_id_holder["id"])
        return result

    run_id_holder: dict[str, str] = {}
    original_start = services.discovery.start_discovery_run

    def remember(**kwargs):
        run = original_start(**kwargs)
        run_id_holder["id"] = run.id
        return run

    services.discovery.start_discovery_run = remember
    museum.find_images = cancel_once_started

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).status is RunStatus.CANCELLED
    # It stopped rather than working through the rest.
    assert len(museum.asked) < 3


# -- a deployment with no provider ----------------------------------------------


def test_a_deployment_without_a_provider_leaves_the_run_where_it_is(services, engine, settings):
    """Nothing fails: a capability being absent is not a run breaking."""
    engine.result = a_list("The Elephants")
    runner = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())

    run_id = start(runner).id

    assert services.discovery.get_run(run_id).status is RunStatus.RESOLVING_IMAGES
    assert runner.run_status(run_id, wait=False).image_resolution_available is False


def test_half_a_phase_two_wiring_is_refused_at_construction(services, engine, settings, museum):
    """One without the other finds instances it cannot show, or caches for nothing."""
    with pytest.raises(ServiceError, match="both an image engine and a preview cache"):
        DiscoveryRunner(
            services.discovery,
            engine,
            settings.discovery_settings,
            images=PhaseTwoEngine(ImageSourcePool([museum]), profile=settings.quality_profile),
        )


# -- more than one source -------------------------------------------------------


class SecondSource:
    """A source beside the museum, with a name of its own and its own previews."""

    def __init__(self, *instances) -> None:
        self._instances = instances
        self.fetched: list[str] = []

    @property
    def provider(self) -> str:
        return "second"

    def find_images(self, query):
        return self._instances

    def fetch_preview(self, url: str) -> bytes | None:
        self.fetched.append(url)
        # A real picture: the store keeps only what decodes.
        return a_decodable_jpeg(640, 480)


def test_an_instance_from_a_second_source_is_selected_and_its_preview_fetched_from_it(services, engine, settings, museum):
    """The runner hands each instance's own source name to the preview cache."""
    second = SecondSource(
        replace(
            an_image("The Elephants", width=6949, height=8400, provider="second", url="https://second.example/1"),
            preview_url="https://second.example/1/preview.jpg",
        )
    )
    museum.holdings = {"The Elephants": (an_image("The Elephants", width=2000, height=1500),)}
    pool = ImageSourcePool([museum, second])
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(pool, profile=settings.quality_profile),
        previews=PreviewCache(PictureStore(settings.pictures_path, art_root=settings.art_root, sources=pool)),
        spawn=lambda work: work(),
    )
    engine.result = a_list("The Elephants")

    run_id = start(runner).id
    work = services.discovery.list_candidate_works(run_id)[0]
    images = services.discovery.list_candidate_images(work.id)

    selected = next(image for image in images if image.is_selected)
    assert (selected.provider, selected.preview_path is not None) == ("second", True)
    assert len(second.fetched) == 1
    assert len(museum.fetched) == 1, "the museum's own instance still has its preview fetched from the museum"


def test_a_level_tie_between_sources_is_stored_for_the_source_listed_first(
    store, discovery_store, wall_settings, thumbnail_settings, engine, settings, museum
):
    """The stored selection breaks a tie as phase 2 did, not on a random id.

    Eight works, each found at the same size by both sources, so a ranking that
    fell through to the id would pick the wrong source for at least one of them
    all but once in 256 runs. Wired through the container, which is what hands the
    pool's order to the discovery service.
    """
    titles = [f"Work {n}" for n in range(8)]

    class EachTitle(SecondSource):
        def find_images(self, query):
            return tuple(image for image in self._instances if image.title == query.title)

    second = EachTitle(
        *(
            replace(
                an_image(title, width=6949, height=8400, provider="second", url=f"https://second.example/{n}"),
                preview_url=f"https://second.example/{n}/preview.jpg",
            )
            for n, title in enumerate(titles)
        )
    )
    museum.holdings = {title: (an_image(title, width=6949, height=8400),) for title in titles}
    plane = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        quality_profile=settings.quality_profile,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        sources=a_roster(second, museum),
    )
    plane.runner._spawn = lambda work: work()
    engine.result = a_list(*titles)

    run_id = start(plane.runner).id

    for work in plane.discovery.list_candidate_works(run_id):
        selected = [image.provider for image in plane.discovery.list_candidate_images(work.id) if image.is_selected]
        assert selected == ["second"], (work.proposed_title, selected)


def test_with_commons_the_only_source_a_work_named_by_title_is_not_called_unheld(
    store, discovery_store, wall_settings, thumbnail_settings, engine, settings, caplog
):
    """Commons cannot look a title up, so a proposal waits rather than being recorded `not_held`."""
    import httpx
    from fakes import FakeRegistry

    from arrt.library.sources.commons import CommonsFinder

    def no_request(request):
        raise AssertionError(f"Commons was asked about a work it cannot look up: {request.url}")

    commons = CommonsFinder(
        registry=FakeRegistry(),
        user_agent="arrt-tests/0",
        client=httpx.Client(transport=httpx.MockTransport(no_request)),
    )
    plane = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        quality_profile=settings.quality_profile,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        sources=a_roster(commons),
    )
    plane.runner._spawn = lambda work: work()
    engine.result = a_list("The Elephants")

    with caplog.at_level(logging.WARNING):
        run_id = start(plane.runner).id

    (work,) = plane.discovery.list_candidate_works(run_id)
    assert (work.resolution_status, work.unresolved_reason) == (ResolutionStatus.PENDING, None)
    events = {getattr(record, "event", None) for record in caplog.records}
    assert "phase_two.unanswerable" in events, events
    assert "phase_two.unreachable" not in events, events


def test_a_row_from_a_source_no_longer_wired_ranks_after_the_wired_ones(services, engine, settings):
    """A deployment that drops a source keeps its rows; ranking them must not raise.

    The two instances rank level, the unwired source's first recorded and so first
    selected. Resolving the work moves the selection to the wired source's row,
    because a source the order no longer names ranks last.
    """
    plain = DiscoveryRunner(services.discovery, engine, settings.discovery_settings, spawn=lambda work: work())
    engine.result = a_list("The Elephants")
    run_id = start(plain).id
    (work,) = services.discovery.list_candidate_works(run_id)
    services.discovery.precedence = ImageSourcePool([SecondSource()]).precedence
    for provider in ("artic", "second"):
        services.discovery.record_image(
            candidate_work_id=work.id,
            url=f"https://{provider}.example/elephants",
            provider=provider,
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            confidence=0.95,
            estimated_width=6949,
            estimated_height=8400,
            quality_score=0.9,
        )

    outcome = services.discovery.record_resolution(work.id)

    assert outcome.selected is not None
    assert outcome.selected.provider == "second"


# -- the Wikidata link, as the container wires it -------------------------------


def test_a_holders_other_title_resolves_through_the_deployments_registry(
    store, discovery_store, wall_settings, thumbnail_settings, engine, settings
):
    """The registry the deployment configures is the one phase 2 asks.

    Built by `Services.bind`, because the link is only as good as its wiring: an
    engine assembled without the registry refuses MoMA's *Composition* on its
    title, which is what run 3 recorded, and every engine-level test still passes.
    """
    from fakes import FakeRegistry

    from arrt.library.services.discovery import ChosenWork

    qid, page = "Q19884054", "https://www.moma.org/collection/works/37346"
    long_title = "Composition of Circles and Overlapping Angles"
    museum = FakeFinder(
        holdings={long_title: (an_image("Composition", artist="Sophie Taeuber-Arp", width=2000, height=1992, url=page),)}
    )
    registry = FakeRegistry(pages={qid: [page]})
    plane = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        quality_profile=settings.quality_profile,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        registry=registry,
        sources=a_roster(museum),
    )
    plane.runner._spawn = lambda work: work()

    run = plane.runner.get(
        works=[ChosenWork(qid=qid, title=long_title, artist="Sophie Taeuber-Arp")],
        initiated_by=InitiatedBy.MCP_CLIENT,
    )

    (work,) = plane.discovery.list_candidate_works(run.id)
    assert work.resolution_status is ResolutionStatus.RESOLVED
    assert [image.url for image in plane.discovery.list_candidate_images(work.id)] == [page]
    assert registry.pages_asked == [qid]
