"""Within one pass, a plugin that keeps answering "could not be asked" is not asked again until the next.

The rule (`library/sources/loading.py`, `one_pass`, `HOLD_BACK_AFTER`): a work its
plugin could not be asked about is asked again on the next pass, with no limit,
so during a museum's outage every pass would ask every such work, one at a
time, each up to the plugin's deadline. After three could-not-be-asked answers
in a row from one plugin within one pass, the rest of the pass does not ask it.

Held on the two passes there are, each built the way the server builds it
(`Services.bind`): the acquisition queue's, over contained readers, and phase
2's over a run's works, over contained finders. Each plugin here is a stub
contained by `SourceRoster.of` exactly as a loaded plugin is, and none reaches
anything.
"""

import contextvars
import logging
import threading
from contextlib import contextmanager

import pytest
from fakes import a_decodable_jpeg, a_work, an_image

from arrt.library.discovery.engine import WorkList
from arrt.library.discovery.images import ImageQuery, ImageSearchFailure
from arrt.library.sources.loading import HOLD_BACK_AFTER, NotAskedThisPass, PassHold, SourceRoster, one_pass
from arrt.library.sources.reading import FetchLocator
from arrt.persistence.discovery_records import InitiatedBy
from arrt.persistence.records import AcquisitionMethod, FetchOutcome, QueuedAcquisition, RightsStatus, SourceClass

#: How many works the down museum holds in the queue: more than the pass asks.
DOWN_WORKS = 7


class Museum:
    """A plugin's reader and finder: up, or down (could not be asked), counting every call that reached it."""

    def __init__(self, name: str, *, down: bool) -> None:
        self.name = name
        self.down = down
        self.reads = 0
        self.finds = 0

    @property
    def provider(self) -> str:
        return self.name

    def claims(self, url: str) -> bool:
        return url.startswith(f"https://{self.name}.example/")

    def read(self, url: str) -> FetchLocator:
        self.reads += 1
        if self.down:
            raise ImageSearchFailure(f"{self.name} answered 503")
        return FetchLocator.direct(url)

    def find_images(self, query: ImageQuery):
        self.finds += 1
        if self.down:
            raise ImageSearchFailure(f"{self.name} answered 503")
        return (an_image(query.title, provider=self.name, url=f"https://{self.name}.example/{query.title}"),)

    def fetch_preview(self, url: str) -> bytes | None:
        return a_decodable_jpeg()


@pytest.fixture
def down() -> Museum:
    return Museum("down", down=True)


@pytest.fixture
def up() -> Museum:
    return Museum("up", down=False)


@pytest.fixture
def sources(down, up) -> SourceRoster:
    return SourceRoster.of(finders=[down, up], readers={"down": (down.claims, down), "up": (up.claims, up)})


@pytest.fixture
def open_stream():
    @contextmanager
    def _open(url: str):
        yield iter([a_decodable_jpeg()])

    return _open


def accepted(service, museum: Museum, title: str):
    work = service.add_artwork(title=title)
    service.add_source(
        artwork_id=work.id,
        url=f"https://{museum.name}.example/{work.id}",
        provider=museum.name,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    return work


def rows(quiet_catalogue_file, ids) -> dict[str, dict | None]:
    """Each work's queue row as the file holds it, column for column, or None for no row."""
    found = {}
    for artwork_id in ids:
        held = quiet_catalogue_file.select_rows("SELECT * FROM acquisition_queue WHERE artwork_id = ?", (artwork_id,))
        found[artwork_id] = held[0] if held else None
    return found


def held_back_lines(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if getattr(record, "event", None) == "source.plugin_held_back"]


# -- the queue's pass ------------------------------------------------------------------


def test_a_queue_pass_asks_a_museum_that_is_down_three_times_and_leaves_the_rest_exactly_as_they_were(
    services, service, store, quiet_catalogue_file, down, up, caplog
):
    """Bounded calls, rows untouched for the works not asked, another plugin asked for every one of its works."""
    downs = [accepted(service, down, f"Down {n}") for n in range(DOWN_WORKS)]
    ups = [accepted(service, up, f"Up {n}") for n in range(2)]
    # Six of the down works failed on an earlier pass, as a pass leaves them; the
    # last was accepted since and has no row at all.
    for n, work in enumerate(downs[:-1]):
        store.set_queued_acquisition(
            QueuedAcquisition(
                artwork_id=work.id,
                failures=n + 1,
                detail=f"the down plugin could not read this source: earlier {n}",
                outcome=FetchOutcome.UNASKED,
                plugin="down",
            )
        )
    ids = [work.id for work in downs]
    before = rows(quiet_catalogue_file, ids)
    assert before[downs[-1].id] is None

    with caplog.at_level(logging.WARNING, logger="arrt.library.sources.loading"):
        result = services.acquisition_queue.run()

    assert down.reads == HOLD_BACK_AFTER, f"the pass asked the down museum {down.reads} times"
    assert up.reads == len(ups), "a plugin held back held another back"
    after = rows(quiet_catalogue_file, ids)
    asked = [work.id for work in downs if before[work.id] != after[work.id]]
    assert len(asked) == HOLD_BACK_AFTER, "the works asked are the only ones whose rows changed"
    assert all(after[artwork_id]["outcome"] == "unasked" for artwork_id in asked)
    left = [artwork_id for artwork_id in ids if artwork_id not in asked]
    assert {artwork_id: after[artwork_id] for artwork_id in left} == {artwork_id: before[artwork_id] for artwork_id in left}
    assert asked == [work.id for work in downs[:HOLD_BACK_AFTER]], "the pass asks in turn, oldest acceptance first"
    assert after[downs[-1].id] is None, "a work held back that had no row was given one"
    (line,) = held_back_lines(caplog)
    assert (line.plugin, line.not_asked, line.after) == ("down", DOWN_WORKS - HOLD_BACK_AFTER, HOLD_BACK_AFTER)
    assert result.acquired == len(ups)
    assert result.failed == HOLD_BACK_AFTER


def test_the_next_pass_asks_the_museum_again_and_one_that_answers_again_is_asked_about_every_work(services, service, down, up):
    downs = [accepted(service, down, f"Down {n}") for n in range(DOWN_WORKS)]
    services.acquisition_queue.run()
    assert down.reads == HOLD_BACK_AFTER

    services.acquisition_queue.run()
    assert down.reads == 2 * HOLD_BACK_AFTER, "a museum still down is asked three times again on the next pass"

    down.down = False
    services.acquisition_queue.run()
    assert down.reads == 2 * HOLD_BACK_AFTER + len(downs), "a museum that answers again is asked about every work"
    assert services.acquisition_queue.state_of([work.id for work in downs]) == {}


def test_an_answer_between_could_not_be_asked_answers_starts_the_count_again():
    flaky = Museum("flaky", down=True)
    roster = SourceRoster.of(readers={"flaky": (flaky.claims, flaky)})
    reader = roster.route("https://flaky.example/1").reader
    said = []

    with one_pass():
        for down in (True, True, False, True, True, False, True, True, True, True):
            flaky.down = down
            try:
                reader.read("https://flaky.example/1")
            except NotAskedThisPass:
                said.append("held")
            except ImageSearchFailure:
                said.append("unasked")
            else:
                said.append("answered")

    assert said == [*["unasked"] * 2, "answered", *["unasked"] * 2, "answered", *["unasked"] * 3, "held"]


def test_outside_a_pass_nothing_is_held_back():
    """A look, a preview, a Retry's own read: only a pass holds a plugin back."""
    down = Museum("down", down=True)
    roster = SourceRoster.of(readers={"down": (down.claims, down)})
    reader = roster.route("https://down.example/1").reader

    for _ in range(HOLD_BACK_AFTER + 2):
        with pytest.raises(ImageSearchFailure):
            reader.read("https://down.example/1")

    assert down.reads == HOLD_BACK_AFTER + 2


def test_a_pass_counts_each_plugin_apart_and_counts_the_works_it_did_not_ask():
    """One plugin held back holds no other back, and each refusal is one work not asked."""
    hold = PassHold()
    for _ in range(HOLD_BACK_AFTER):
        hold.heard("down", unasked=True)
    with pytest.raises(NotAskedThisPass):
        hold.ask("down")
    hold.ask("up")
    assert hold.not_asked() == {"down": 1}


# -- phase 2's pass, a run ---------------------------------------------------------------


def test_a_run_asks_a_museum_that_is_down_about_three_of_its_works_and_every_other_museum_about_all(
    services, engine, down, up, caplog
):
    services.runner._spawn = lambda work: work()
    titles = [f"Study No. {n}" for n in range(6)]
    engine.result = WorkList(works=tuple(a_work(title) for title in titles))

    with caplog.at_level(logging.WARNING, logger="arrt.library.sources.loading"):
        services.runner.start(intent_text="Studies", initiated_by=InitiatedBy.MCP_CLIENT)

    assert down.finds == HOLD_BACK_AFTER
    assert up.finds == len(titles)
    (line,) = held_back_lines(caplog)
    assert (line.plugin, line.not_asked) == ("down", len(titles) - HOLD_BACK_AFTER)


def test_an_answer_that_lands_after_its_pass_ended_counts_in_that_pass_and_never_the_next():
    """A call started in one pass and answered during the next counts where it was asked.

    Phase 2's workers run in a copy of the pass's context, so a late answer reaches
    the pass that asked it, which has ended, and never the one under way.
    """
    gate = threading.Event()
    asked = threading.Event()

    class Waits(Museum):
        def find_images(self, query: ImageQuery):
            asked.set()
            assert gate.wait(10), "the test never opened the gate"
            return super().find_images(query)

    earlier = SourceRoster.of(finders=[Waits("down", down=True)]).finders[0]
    with one_pass():
        worker = threading.Thread(target=contextvars.copy_context().run, args=(_unasked, earlier), name="image-source-down")
        worker.start()
        assert asked.wait(10)
    down = Museum("down", down=True)
    finder = SourceRoster.of(finders=[down]).finders[0]
    with one_pass():
        gate.set()
        worker.join(10)
        assert not worker.is_alive()
        for _ in range(HOLD_BACK_AFTER):
            _unasked(finder)

    assert down.finds == HOLD_BACK_AFTER, "the earlier pass's late answer was counted in this one"


def _unasked(finder) -> None:
    with pytest.raises(ImageSearchFailure):
        list(finder.find_images(ImageQuery(title="Study")))
