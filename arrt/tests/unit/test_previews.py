"""Candidate previews through the phase-two caller: kept once, asked for once, never a run-ender.

The store's own rules are `test_pictures.py`'s. What is tested here is the seam
the runner holds: that the path a row records is the store's, keyed by the
instance rather than its preview, that a second record of the same picture asks
no source, and that a picture which cannot be kept costs a card and not a run.
Each drives a whole run, because the caller is `DiscoveryRunner._record_instance`
and testing the cache beside the engine would prove each half and not the seam.
"""

import pytest
from fakes import FakeFinder, a_work, an_image

from arrt.library.discovery.engine import WorkList
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.services.pictures import PictureStore, picture_key
from arrt.library.services.previews import PreviewCache
from arrt.library.services.runner import DiscoveryRunner
from arrt.persistence.discovery_records import InitiatedBy, ResolutionStatus, RunStatus


@pytest.fixture
def museum() -> FakeFinder:
    """Two works resolving to one picture at one holder, as when phase 2 resolves two titles to one scan."""
    shared = "https://api.artic.edu/api/v1/artworks/4884"
    return FakeFinder(
        holdings={
            "The Elephants": (an_image("The Elephants", url=shared),),
            "Swans Reflecting Elephants": (an_image("Swans Reflecting Elephants", url=shared),),
        }
    )


@pytest.fixture
def pictures(settings, museum) -> PictureStore:
    return PictureStore(settings.pictures_path, art_root=settings.art_root, sources=ImageSourcePool([museum]))


def a_run(services, engine, settings, museum, pictures, *titles: str) -> str:
    engine.result = WorkList(works=tuple(a_work(title) for title in titles))
    runner = DiscoveryRunner(
        services.discovery,
        engine,
        settings.discovery_settings,
        images=PhaseTwoEngine(ImageSourcePool([museum]), box=settings.tv_artwork_box),
        previews=PreviewCache(pictures),
        spawn=lambda work: work(),
    )
    return runner.start(intent_text="elephants", initiated_by=InitiatedBy.MCP_CLIENT).id


def test_a_row_records_the_stores_path_keyed_by_the_instance_not_its_preview(services, engine, settings, museum, pictures):
    run_id = a_run(services, engine, settings, museum, pictures, "The Elephants")

    (work,) = services.discovery.list_candidate_works(run_id)
    (image,) = services.discovery.list_candidate_images(work.id)
    assert pictures.key_of(image.preview_path) == picture_key(image.provider, image.url)
    assert pictures.key_of(image.preview_path) != picture_key(image.provider, image.preview_url)
    assert museum.fetched == [image.preview_url], "the source was asked for the preview, by its preview URL"


def test_a_second_record_of_the_same_picture_asks_no_source(services, engine, settings, museum, pictures):
    """Two works, one picture (one scan resolved for two titles): the second is answered from the store."""
    run_id = a_run(services, engine, settings, museum, pictures, "The Elephants", "Swans Reflecting Elephants")

    rows = [
        image
        for work in services.discovery.list_candidate_works(run_id)
        for image in services.discovery.list_candidate_images(work.id)
    ]
    assert len(rows) == 2, "two works, each holding an instance"
    assert rows[0].preview_path == rows[1].preview_path is not None
    assert len(museum.fetched) == 1, "the museum was asked once for a picture two rows show"


def test_a_re_search_after_the_picture_is_kept_asks_no_source(services, engine, settings, museum, pictures):
    """Varying the run, not only repeating it: a later run over another title still finds it kept."""
    a_run(services, engine, settings, museum, pictures, "The Elephants")
    a_run(services, engine, settings, museum, pictures, "Swans Reflecting Elephants")

    assert len(museum.fetched) == 1


def test_a_run_completes_when_no_picture_can_be_written(services, engine, settings, museum, pictures, monkeypatch):
    """`keep` returning `None` is only worth anything if the caller carries on."""

    def explode(self, _data):
        raise OSError("no space left on device")

    monkeypatch.setattr("pathlib.Path.write_bytes", explode)

    run_id = a_run(services, engine, settings, museum, pictures, "The Elephants")

    assert services.discovery.get_run(run_id).status is RunStatus.COMPLETED
    (work,) = services.discovery.list_candidate_works(run_id)
    assert work.resolution_status is ResolutionStatus.RESOLVED
    (image,) = services.discovery.list_candidate_images(work.id)
    assert image.is_selected is True
    assert image.preview_path is None, "nothing was written, and the row says so"
    assert image.preview_url, "the card falls back to the source URL"
