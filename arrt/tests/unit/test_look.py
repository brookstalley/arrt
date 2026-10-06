"""A look at a work the library does not hold: what each image source holds, before any Get.

The service is built here over its own finders and a clock the test moves, so the
cache's ages are stated rather than waited for. Its asks run on its own threads,
as they do in the plane; a held look (`hold=`) is how a test waits for them.
"""

import logging
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeRegistry, a_decodable_jpeg, a_roster, an_image

from arrt.config import PICTURES_DIRNAME
from arrt.library.discovery.images import FoundImage, ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry import ItemId, RegistryCreator, RegistryText, RegistryWork
from arrt.library.services.discovery import ChosenWork
from arrt.library.services.look import (
    ANSWER_KEPT_FOR,
    MAX_LOOKS,
    UNREACHABLE_KEPT_FOR,
    UNWATCHED_AFTER,
    LookService,
    LookState,
    SourceState,
)
from arrt.library.services.pictures import PictureStore, picture_key
from arrt.logs import RunCorrelationFilter
from arrt.persistence.discovery_records import InitiatedBy, RunStatus
from arrt.services.errors import ServiceError

TANTRA = ItemId("Q20267229")
SLEEP = ItemId("Q1003")
BILLE = RegistryCreator(qid=ItemId("Q5001"), name=RegistryText("Ejler Bille"))

#: How long a test waits for the look's own threads, at most. Generous, because a
#: loaded CI runner is slow; a passing test never waits it out.
SETTLE = 10.0


def a_work(qid: str, title: str, *, creators: tuple[RegistryCreator, ...] = (BILLE,)) -> RegistryWork:
    return RegistryWork(qid=ItemId(qid), title=RegistryText(title), sitelinks=3, creators=creators)


class Clock:
    """The look's clock, moved by the test."""

    def __init__(self) -> None:
        self.at = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.at

    def advance(self, **delta: float) -> None:
        self.at += timedelta(**delta)


class Source:
    """An image source answering by title, which counts its asks and can be held at a gate.

    `blocks` names titles whose ask waits at `gate` until the test opens it, so a
    test can hold a source busy while it arranges what happens next.
    """

    def __init__(
        self,
        provider: str = "smk",
        holdings: dict[str, Sequence[FoundImage]] | None = None,
        *,
        fails: bool = False,
        declines: bool = False,
        blocks: frozenset[str] = frozenset(),
    ) -> None:
        self._provider = provider
        self.holdings = holdings or {}
        self.fails = fails
        self.declines = declines
        self.blocks = blocks
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.asked: list[ImageQuery] = []
        self.fetched: list[str] = []

    @property
    def provider(self) -> str:
        return self._provider

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        self.asked.append(query)
        self.entered.set()
        if query.title in self.blocks:
            assert self.gate.wait(SETTLE), "the test never opened the gate"
        if self.fails:
            raise ImageSearchFailure(f"{self._provider} is down")
        if self.declines:
            raise ImageQueryUnanswerable(f"{self._provider} looks works up by item only")
        return tuple(self.holdings.get(query.title, ()))

    def fetch_preview(self, url: str) -> bytes | None:
        self.fetched.append(url)
        return a_decodable_jpeg()

    def titles_asked(self) -> list[str]:
        return [query.title for query in self.asked]


def smk_image(title: str, *, artist: str | None = "Ejler Bille", width: int = 2201, height: int = 2221) -> FoundImage:
    return an_image(
        title,
        artist=artist,
        width=width,
        height=height,
        provider="smk",
        url=f"https://open.smk.dk/artwork/image/{title.replace(' ', '-')}/{width}",
    )


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry(works={TANTRA: a_work(TANTRA, "Tantra-Vision"), SLEEP: a_work(SLEEP, "Sleep")})


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def build(services, settings, registry, clock):
    """A look over these finders, the plane's own registry pages, discovery and picture store."""

    def build(*finders, pool: ImageSourcePool | None = None) -> LookService:
        """A look over `finders`, or over `pool` when the test needs to share it with a run."""
        pool = pool or ImageSourcePool(finders)
        return LookService(
            works=services.registry_works,
            discovery=services.discovery,
            pool=pool,
            judge=PhaseTwoEngine(pool, box=settings.tv_artwork_box, registry=registry),
            # The plane's store directory, fetching from these finders, as the
            # plane's store fetches from the pool its looks ask.
            pictures=PictureStore(
                services.pictures.art_root / PICTURES_DIRNAME, art_root=services.pictures.art_root, sources=pool
            ),
            now=clock,
        )

    return build


def until(condition, *, within: float = SETTLE) -> None:
    deadline = time.monotonic() + within
    while not condition():
        assert time.monotonic() < deadline, "the look's threads never got there"
        time.sleep(0.01)


# -- what it says --------------------------------------------------------------------


def test_a_source_holding_the_work_is_found_with_a_key_per_picture(build):
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")]})

    view = build(smk).look(TANTRA, hold=SETTLE)

    assert view.state is LookState.ANSWERED
    (source,) = view.sources
    assert (source.provider, source.state) == ("smk", SourceState.FOUND)
    (picture,) = view.pictures
    found = picture.judged.found
    assert picture.key == picture_key("smk", found.url)
    assert found.estimated_width == 2201
    assert "matching the requested title and artist" in picture.judged.rationale
    assert view.note is None


def test_a_find_by_another_artist_is_refused_shown_as_such_and_has_no_key(build):
    """Phase 2's identity gate, applied: the title held under another name is not the work."""
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision", artist="Somebody Else")]})
    look = build(smk)

    view = look.look(TANTRA, hold=SETTLE)

    (source,) = view.sources
    assert source.state is SourceState.REFUSED
    assert view.pictures == ()
    assert [str(reason) for reason in source.refusals] == ["identity_refused"]
    refused_url = smk.holdings["Tantra-Vision"][0].url
    assert look.picture(TANTRA, picture_key("smk", refused_url)) is None, "a refused find has no picture to serve"


def test_a_source_holding_only_other_works_holds_none(build):
    smk = Source(holdings={"Tantra-Vision": [smk_image("A Different Painting")]})

    view = build(smk).look(TANTRA, hold=SETTLE)

    assert view.sources[0].state is SourceState.HOLDS_NONE
    assert view.note == "No image source holds a picture of this work now."


def test_a_source_that_cannot_look_the_work_up_says_so_and_is_kept(build, clock):
    commons = Source("commons", declines=True)
    look = build(commons)

    first = look.look(TANTRA, hold=SETTLE)
    clock.advance(hours=5)
    again = look.look(TANTRA, hold=SETTLE)

    assert first.sources[0].state is SourceState.CANNOT
    assert again.sources[0].state is SourceState.CANNOT
    assert len(commons.asked) == 1, "'can't look this up' is an answer, kept as one"


def test_one_source_failing_leaves_the_others_answers_standing(build):
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")]})
    met = Source("met", fails=True)

    view = build(smk, met).look(TANTRA, hold=SETTLE)

    states = {source.provider: source.state for source in view.sources}
    assert states == {"smk": SourceState.FOUND, "met": SourceState.UNREACHABLE}
    assert len(view.pictures) == 1


# -- the cache -------------------------------------------------------------------------


def test_an_answer_is_kept_six_hours_and_asked_again_after(build, clock):
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")]})
    look = build(smk)
    look.look(TANTRA, hold=SETTLE)

    clock.advance(seconds=ANSWER_KEPT_FOR.total_seconds() - 60)
    kept = look.look(TANTRA, hold=SETTLE)
    assert len(smk.asked) == 1
    assert kept.sources[0].state is SourceState.FOUND

    clock.advance(seconds=120)
    look.look(TANTRA, hold=SETTLE)
    assert len(smk.asked) == 2


def test_holds_nothing_is_kept_as_an_answer(build, clock):
    smk = Source()
    look = build(smk)
    look.look(TANTRA, hold=SETTLE)

    clock.advance(hours=5)
    view = look.look(TANTRA, hold=SETTLE)

    assert view.sources[0].state is SourceState.HOLDS_NONE
    assert len(smk.asked) == 1


def test_a_failure_is_kept_ten_minutes_and_never_as_holding_none(build, clock):
    met = Source("met", fails=True)
    look = build(met)

    first = look.look(TANTRA, hold=SETTLE)
    (source,) = first.sources
    assert source.state is SourceState.UNREACHABLE
    assert source.retry_at == clock() + UNREACHABLE_KEPT_FOR
    assert first.note == "No image source that answered holds a picture of this work now."

    clock.advance(minutes=9)
    assert look.look(TANTRA, hold=SETTLE).sources[0].state is SourceState.UNREACHABLE
    assert len(met.asked) == 1

    met.fails = False
    clock.advance(minutes=2)
    after = look.look(TANTRA, hold=SETTLE)
    assert len(met.asked) == 2
    assert after.sources[0].state is SourceState.HOLDS_NONE


def test_the_least_recently_looked_at_work_is_forgotten_past_the_bound(build, registry):
    qids = [ItemId(f"Q{900000 + n}") for n in range(MAX_LOOKS + 1)]
    for qid in qids:
        registry.works[qid] = a_work(qid, f"Work {qid}")
    smk = Source()
    look = build(smk)
    for qid in qids:
        look.look(qid, hold=SETTLE)
    assert len(smk.asked) == MAX_LOOKS + 1

    look.look(qids[1], hold=SETTLE)
    assert len(smk.asked) == MAX_LOOKS + 1, "the second-oldest is still kept"
    look.look(qids[0], hold=SETTLE)
    assert len(smk.asked) == MAX_LOOKS + 2, "the oldest was dropped when the bound was passed"


def test_a_second_look_joins_the_first_and_the_source_is_asked_once(build):
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")]}, blocks=frozenset({"Tantra-Vision"}))
    look = build(smk)

    first = look.look(TANTRA)
    assert smk.entered.wait(SETTLE)
    second = look.look(TANTRA)
    smk.gate.set()
    settled = look.look(TANTRA, hold=SETTLE)

    assert first.state is LookState.ASKING
    assert second.state is LookState.ASKING
    assert second.sources[0].state is SourceState.ASKING
    assert settled.sources[0].state is SourceState.FOUND
    assert len(smk.asked) == 1


def test_an_ask_queued_for_a_work_nobody_is_looking_at_is_dropped_before_it_starts(build, clock, caplog):
    smk = Source(blocks=frozenset({"Tantra-Vision"}))
    look = build(smk)
    look.look(TANTRA)
    assert smk.entered.wait(SETTLE)
    look.look(SLEEP)  # queued behind Tantra-Vision at the one source

    clock.advance(seconds=UNWATCHED_AFTER.total_seconds() + 1)
    with caplog.at_level(logging.INFO, logger="arrt.library.services.look"):
        smk.gate.set()
        until(lambda: any(getattr(r, "event", None) == "look.abandoned" for r in caplog.records))

    assert smk.titles_asked() == ["Tantra-Vision"], "nobody was waiting for Sleep, so nobody asked"
    again = look.look(SLEEP, hold=SETTLE)
    assert smk.titles_asked() == ["Tantra-Vision", "Sleep"], "looking again queues it again"
    assert again.sources[0].state is SourceState.HOLDS_NONE


def test_an_ask_that_has_started_finishes_and_is_kept_even_when_nobody_waits(build, clock):
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")]}, blocks=frozenset({"Tantra-Vision"}))
    look = build(smk)
    look.look(TANTRA)
    assert smk.entered.wait(SETTLE)

    clock.advance(seconds=UNWATCHED_AFTER.total_seconds() + 1)
    smk.gate.set()
    view = look.look(TANTRA, hold=SETTLE)

    assert view.sources[0].state is SourceState.FOUND
    assert len(smk.asked) == 1


def test_a_run_asking_a_source_goes_first_and_the_look_waits_behind_it(build):
    """A Get's run is what a curator pressed for; a look's question waits until the run is done with the source."""
    smk = Source(blocks=frozenset({"A Work A Run Wants"}))
    pool = ImageSourcePool([smk])
    look = build(pool=pool)
    run = threading.Thread(target=lambda: pool.find_images(ImageQuery(title="A Work A Run Wants")), daemon=True)
    run.start()
    assert smk.entered.wait(SETTLE)

    asking = look.look(TANTRA)
    time.sleep(0.5)
    assert smk.titles_asked() == ["A Work A Run Wants"], "the look asked while a run was using the source"
    assert asking.sources[0].state is SourceState.ASKING

    smk.gate.set()
    run.join(SETTLE)
    look.look(TANTRA, hold=SETTLE)
    assert smk.titles_asked() == ["A Work A Run Wants", "Tantra-Vision"]


# -- its question is a Get's ----------------------------------------------------------


@pytest.fixture
def got_registry(registry) -> FakeRegistry:
    # Padded, as a label can be: a Get's row stores it stripped, and the look must ask the same.
    registry.works[TANTRA] = a_work(TANTRA, "  Tantra-Vision ")
    return registry


@pytest.fixture
def get_source() -> Source:
    return Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")]})


@pytest.fixture
def sources(got_registry, get_source):
    """The plane's own sources, which a Get's run asks: here, `get_source`."""
    return a_roster(get_source)


def test_the_look_asks_the_sources_exactly_what_a_get_of_the_work_asks(services, build, get_source):
    outcome = services.get.start([TANTRA], initiated_by=InitiatedBy.WEB_UI)
    assert outcome.run is not None
    until(lambda: services.runner.run_status(outcome.run.id, wait=False).run.status is not RunStatus.RESOLVING_IMAGES)
    (get_query,) = get_source.asked

    look_source = Source()
    build(look_source).look(TANTRA, hold=SETTLE)
    (look_query,) = look_source.asked

    assert look_query == get_query
    assert look_query.title == "Tantra-Vision"


# -- what it asks nothing for ------------------------------------------------------------


def test_a_work_a_get_is_already_asking_about_asks_nothing(services, build, sources):
    services.discovery.start_get_run(works=[ChosenWork(TANTRA, "Tantra-Vision")], initiated_by=InitiatedBy.WEB_UI)
    smk = Source()

    view = build(smk).look(TANTRA, hold=SETTLE)

    assert view.state is LookState.BEING_GOT
    assert view.note == "A Get is already asking the sources about this work."
    assert smk.asked == []


def test_a_held_work_asks_nothing_and_names_the_library_s_works(services, build, ready_work):
    work = ready_work()
    services.identity.set_work_identity(work.id, TANTRA)
    smk = Source()

    view = build(smk).look(TANTRA, hold=SETTLE)

    assert view.state is LookState.HELD
    assert view.held == (work.id,)
    assert smk.asked == []


def test_a_work_wikidata_has_no_item_for_asks_nothing(build):
    smk = Source()

    view = build(smk).look("Q1999", hold=SETTLE)

    assert view.state is LookState.NOT_FOUND
    assert smk.asked == []


def test_a_malformed_qid_is_refused(build):
    with pytest.raises(ServiceError, match="not a Wikidata item id"):
        build(Source()).look("tantra")


# -- pictures ---------------------------------------------------------------------------


def test_a_picture_is_served_from_the_store_only_for_a_key_this_work_s_look_names(build, registry, clock):
    registry.works[SLEEP] = a_work(SLEEP, "Sleep")
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")], "Sleep": [smk_image("Sleep")]})
    look = build(smk)
    tantra = look.look(TANTRA, hold=SETTLE).pictures[0].key
    sleep = look.look(SLEEP, hold=SETTLE).pictures[0].key

    served = look.picture(TANTRA, tantra)
    assert served is not None
    assert served.data.startswith(b"\xff\xd8\xff")
    assert look.picture(TANTRA, sleep) is None, "another work's key"
    assert look.picture(TANTRA, "0" * 64) is None, "a key no look names"
    assert len(smk.fetched) == 1, "only the picture served was fetched"

    look.picture(TANTRA, tantra, enlarged=True)
    assert len(smk.fetched) == 1, "the store answers the second ask, at either size"

    clock.advance(seconds=ANSWER_KEPT_FOR.total_seconds() + 1)
    assert look.picture(TANTRA, tantra) is None, "a key from a look no longer kept"


def test_the_look_writes_nothing_to_the_catalogue(build, catalogue_file):
    def every_row() -> dict[str, list]:
        tables = [row["name"] for row in catalogue_file.select_rows("SELECT name FROM sqlite_master WHERE type = 'table'")]
        # The names are sqlite's own, read just above; nothing outside the file reaches the statement.
        return {table: sorted(map(repr, catalogue_file.select_rows(f"SELECT * FROM {table}"))) for table in tables}  # noqa: S608

    before = every_row()
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")]})
    look = build(smk)
    view = look.look(TANTRA, hold=SETTLE)
    look.picture(TANTRA, view.pictures[0].key)

    assert view.pictures, "the look found something, so a write would have had something to write"
    assert every_row() == before


def test_a_look_s_lines_carry_its_qid(build, caplog):
    smk = Source(holdings={"Tantra-Vision": [smk_image("Tantra-Vision")]})
    caplog.handler.addFilter(RunCorrelationFilter())
    with caplog.at_level(logging.INFO):
        build(smk).look(TANTRA, hold=SETTLE)

    answered = [r for r in caplog.records if getattr(r, "event", None) == "look.source_answered"]
    started = [r for r in caplog.records if getattr(r, "event", None) == "look.started"]
    assert [r.look_qid for r in answered] == [TANTRA]
    assert [r.look_qid for r in started] == [TANTRA]


def test_two_answers_judged_at_once_ask_the_registry_for_the_work_s_pages_once(settings, registry):
    """A look judges each source's answer on that source's thread, against one link per work."""
    entered, release = threading.Event(), threading.Event()
    asked = registry.pages_about

    def slowly(qid):
        entered.set()
        assert release.wait(SETTLE)
        return asked(qid)

    registry.pages_about = slowly
    pool = ImageSourcePool([Source()])
    link = PhaseTwoEngine(pool, box=settings.tv_artwork_box, registry=registry).link(
        ImageQuery(title="Tantra-Vision", qid=TANTRA)
    )
    answers: list[str | None] = []
    first = threading.Thread(target=lambda: answers.append(link.unlinked("https://a.example/1")))
    second = threading.Thread(target=lambda: answers.append(link.unlinked("https://a.example/2")))
    first.start()
    assert entered.wait(SETTLE)
    second.start()
    time.sleep(0.2)
    release.set()
    first.join(SETTLE)
    second.join(SETTLE)

    assert registry.pages_asked == [TANTRA]
    assert answers == ["not_recorded", "not_recorded"]
