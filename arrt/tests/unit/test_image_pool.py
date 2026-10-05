"""Every image source asked at once, and a source that could not be asked kept apart.

The pool's promise has three halves: the sources are asked in parallel, a source
that could not be asked never reads as one that holds nothing, and each instance's
preview goes back to the source that found it (its tiles go to the plugin that
claims its URL, `test_acquisition_reading.py`). The engine-level tests at
the bottom are where the second half matters, because only phase 2's judgement
can say whether what the reachable sources found settles the work.
"""

import logging
import threading

import pytest
from fakes import an_image

from arrt.library.discovery.images import FoundImage, ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.services.display_fit import ArtworkBox

#: The engine tests' 42" geometry: the floor sits at about 1,260 px on the long edge.
BOX = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.9, floor_inches=12.0)

TITLE = "The Elephants"
ARTIST = "Salvador Dalí"


class Source:
    """An image source with a name of its own, answering what it was built to answer."""

    def __init__(
        self,
        name: str,
        *instances: FoundImage,
        fails: bool = False,
        declines: bool = False,
        meet: threading.Barrier | None = None,
    ) -> None:
        self._name = name
        self._instances = instances
        self._fails = fails
        self._declines = declines
        self._meet = meet
        self.previews: list[str] = []

    @property
    def provider(self) -> str:
        return self._name

    def find_images(self, query: ImageQuery):
        if self._meet is not None:
            # Returns only once every source has been asked, so a pool that asks
            # one after another breaks the barrier instead of answering.
            self._meet.wait()
        if self._fails:
            raise ImageSearchFailure(f"{self._name} could not be reached")
        if self._declines:
            raise ImageQueryUnanswerable(f"{self._name} cannot look this up")
        return self._instances

    def fetch_preview(self, url: str) -> bytes | None:
        self.previews.append(url)
        return self._name.encode()


def found(provider: str, *, width: int = 6949, height: int = 8400, title: str = TITLE) -> FoundImage:
    return an_image(
        title, artist=ARTIST, width=width, height=height, provider=provider, url=f"https://{provider}.example/{width}"
    )


def query() -> ImageQuery:
    return ImageQuery(title=TITLE, artist=ARTIST)


def test_every_source_is_asked_at_once():
    meet = threading.Barrier(2, timeout=5)
    pool = ImageSourcePool([Source("first", found("first"), meet=meet), Source("second", found("second"), meet=meet)])

    answer = pool.find_images(query())

    assert {image.provider for image in answer.images} == {"first", "second"}
    assert answer.unreachable == ()


def test_a_source_that_holds_nothing_is_an_answer_not_a_failure():
    answer = ImageSourcePool([Source("first"), Source("second")]).find_images(query())

    assert answer.images == ()
    assert answer.unreachable == ()


def test_a_source_that_could_not_be_asked_is_named_and_logged(caplog):
    with caplog.at_level(logging.WARNING):
        answer = ImageSourcePool([Source("first", fails=True), Source("second", found("second"))]).find_images(query())

    assert [image.provider for image in answer.images] == ["second"]
    assert answer.unreachable == ("first",)
    assert [record.provider for record in caplog.records if getattr(record, "event", "") == "image_pool.unreachable"] == ["first"]


def test_no_source_answering_is_a_failure():
    with pytest.raises(ImageSearchFailure, match="first, second"):
        ImageSourcePool([Source("first", fails=True), Source("second", fails=True)]).find_images(query())


def test_a_preview_goes_back_to_the_source_that_found_it():
    first, second = Source("first"), Source("second")
    pool = ImageSourcePool([first, second])

    assert pool.fetch_preview("second", "https://second.example/p.jpg") == b"second"
    assert (first.previews, second.previews) == ([], ["https://second.example/p.jpg"])


def test_a_source_the_pool_does_not_hold_is_refused_by_name():
    with pytest.raises(ValueError, match="'elsewhere'"):
        ImageSourcePool([Source("first")]).fetch_preview("elsewhere", "https://elsewhere.example/p.jpg")


def test_two_sources_may_not_share_a_name():
    with pytest.raises(ValueError, match="first"):
        ImageSourcePool([Source("first"), Source("first")])


def test_a_pool_needs_a_source():
    with pytest.raises(ValueError):
        ImageSourcePool([])


def resolve(*sources: Source):
    return PhaseTwoEngine(ImageSourcePool(list(sources)), box=BOX).resolve(query())


def test_a_tie_goes_to_the_source_listed_first():
    """Identical instances from two sources rank level, so preference decides.

    The first-listed source's URL sorts after the other's, so a ranking that fell
    through to the URL would pick the second.
    """
    top, _other = resolve(Source("zeta", found("zeta")), Source("alpha", found("alpha"))).instances

    assert top.found.provider == "zeta"


def test_preference_never_outranks_a_better_image():
    """The first source's smaller image loses to the second's larger one."""
    top, _other = resolve(Source("first", found("first", width=2000, height=2400)), Source("second", found("second"))).instances

    assert top.found.provider == "second"


def test_a_down_source_does_not_stop_an_image_another_source_found():
    resolution = resolve(Source("first", fails=True), Source("second", found("second")))

    assert [entry.found.provider for entry in resolution.instances] == ["second"]


def test_a_down_source_leaves_a_work_the_others_did_not_find_unsettled():
    """Nothing found while a source was down is not "nobody holds it"."""
    with pytest.raises(ImageSearchFailure, match="first"):
        resolve(Source("first", fails=True), Source("second"))


def test_a_down_source_leaves_a_work_with_only_a_small_image_unsettled():
    """The source that was down may hold the image that clears the floor."""
    with pytest.raises(ImageSearchFailure, match="first"):
        resolve(Source("first", fails=True), Source("second", found("second", width=600, height=700)))


def test_a_work_nobody_holds_is_settled_when_every_source_answered():
    resolution = resolve(Source("first"), Source("second"))

    assert resolution.instances == []


def test_a_source_that_cannot_answer_leaves_the_others_answer_standing():
    """One source declining is not one source down: the other's empty answer settles the work."""
    answer = ImageSourcePool([Source("first", declines=True), Source("second")]).find_images(query())

    assert (answer.images, answer.unreachable) == ((), ())


def test_when_no_source_can_answer_nothing_is_known():
    """Every source declining is no answer at all, never "nobody holds it"."""
    with pytest.raises(ImageSearchFailure, match="cannot"):
        ImageSourcePool([Source("first", declines=True)]).find_images(query())


def test_a_source_down_and_one_declining_is_still_a_failure_to_ask():
    with pytest.raises(ImageSearchFailure, match="second"):
        ImageSourcePool([Source("first", declines=True), Source("second", fails=True)]).find_images(query())


def test_what_a_source_logs_on_its_worker_carries_the_run_it_works_for():
    """The run id is bound in the caller's context; a worker thread would otherwise start without it."""
    from arrt.logs import current_run_id, run_context

    seen: list[str | None] = []

    class Seeing(Source):
        def find_images(self, query: ImageQuery):
            seen.append(current_run_id())
            return ()

    with run_context("run-7"):
        ImageSourcePool([Seeing("first"), Seeing("second")]).find_images(query())

    assert seen == ["run-7", "run-7"]
