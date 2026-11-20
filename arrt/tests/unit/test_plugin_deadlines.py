"""Every call into a plugin answers within its deadline, and one that does not is "could not be asked".

A hung finder used to hold every Get, because the pool waited for every source
with no bound, and every look at that source waited behind the Get. The deadline
is the plugin containment's (`library/sources/loading.py`), with the pool's own as
a backstop for a finder handed to it directly (`library/discovery/pool.py`). A
call past its deadline is not stopped, because Python cannot stop a thread: these
tests also pin what happens when its answer finally arrives, after everyone has
moved on.

Every deadline here is a fraction of a second, given through `Deadlines` or the
pool's `deadline_seconds`; nothing waits out the real ones.
"""

import dataclasses
import importlib.metadata
import logging
import threading
import time
from collections.abc import Iterator

import pytest
from fakes import FakeRegistry, an_image, counted_tokens
from plugin_fakes import StubFinder, StubReader, claims_example

from arrt.config import PICTURES_DIRNAME
from arrt.library.discovery.browse import CollectionBrowseFailure
from arrt.library.discovery.images import FoundImage, ImageQuery, ImageSearchFailure
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import RUN_DEADLINE_SECONDS, AskOutcome, ImageSourcePool
from arrt.library.registry import ItemId, RegistryCreator, RegistryText, RegistryWork
from arrt.library.services.look import LookService, SourceState
from arrt.library.services.pictures import PictureStore
from arrt.library.sources import SourceContext, SourceParts, SourcePlugin
from arrt.library.sources.loading import (
    DEADLINE_CEILING_SECONDS,
    DEADLINE_KINDS,
    ENTRY_POINT_GROUP,
    FINDER_DEADLINE_SECONDS,
    Deadlines,
    PluginState,
    SourceRoster,
    declared_deadlines,
    load_sources,
)

#: A deadline a test can pass in a moment.
QUICK = 0.2
#: How much later than its deadline a call may return and still count as "within"
#: it: thread start-up and a loaded runner, never another deadline's worth.
MARGIN = 2.0
#: How long a test waits for a thread it started, at most; a passing test never waits it out.
SETTLE = 10.0

QUERY = ImageQuery(title="Nighthawks", artist="Edward Hopper")


class Hung:
    """A finder (and reader, and collection) that answers nothing until the test opens its gate, then answers.

    `entered` counts the calls that reached it, so a test can tell a call that was
    started from one refused before it began.
    """

    def __init__(self, provider: str = "slow", *, yields: tuple[FoundImage, ...] = ()) -> None:
        self._provider = provider
        self._yields = yields
        self.gate = threading.Event()
        self.entered = 0
        self.returned = 0
        self._lock = threading.Lock()

    @property
    def provider(self) -> str:
        return self._provider

    def _hang(self) -> None:
        with self._lock:
            self.entered += 1
        assert self.gate.wait(SETTLE), "the test never opened the gate"
        with self._lock:
            self.returned += 1

    def find_images(self, query: ImageQuery) -> Iterator[FoundImage]:
        # A generator, so what it yields before it hangs is said before the deadline.
        yield from self._yields
        self._hang()
        yield an_image(query.title, provider=self._provider, url=f"https://{self._provider}.example/late")

    def fetch_preview(self, url: str) -> bytes | None:
        self._hang()
        return b"late"

    def read(self, url: str):
        self._hang()
        return StubReader().read(url)

    def browse(self, queries, *, per_query: int):
        self._hang()
        return []


def until(condition, *, within: float = SETTLE) -> None:
    ends = time.monotonic() + within
    while not condition():
        assert time.monotonic() < ends, "it never got there"
        time.sleep(0.01)


def late_lines(caplog, event: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if getattr(record, "event", None) == event]


def reading(roster: SourceRoster, name: str):
    return next(r for r in roster.observe() if r.name == name)


# -- the containment's deadline ----------------------------------------------------


def test_the_named_deadlines_are_the_plans_and_the_pools_backstop_is_past_the_finders():
    """60 s a finder and a reader, 30 s a preview, 120 s a browse; the pool's cuts in only after a finder's."""
    assert (Deadlines().finder, Deadlines().reader, Deadlines().preview, Deadlines().browse) == (60.0, 60.0, 30.0, 120.0)
    assert RUN_DEADLINE_SECONDS > FINDER_DEADLINE_SECONDS


def test_a_hung_plugin_finder_is_could_not_be_asked_within_its_deadline_and_the_others_answer(caplog):
    slow = Hung()
    roster = SourceRoster.of(finders=[slow, StubFinder("good")], deadlines=Deadlines(finder=QUICK))
    pool = ImageSourcePool(roster.finders)

    started = time.monotonic()
    with caplog.at_level(logging.WARNING):
        answer = pool.find_images(QUERY)
    took = time.monotonic() - started

    try:
        assert took < QUICK + MARGIN, f"find_images waited {took:.1f} s for a source past its {QUICK} s deadline"
        assert answer.unreachable == ("slow",)
        assert [image.provider for image in answer.images] == ["good"]
        slow_reading = reading(roster, "slow")
        assert (slow_reading.unasked, slow_reading.answered, slow_reading.faults) == (1, 0, 0)
        assert "did not answer within 0.2 seconds" in slow_reading.last_unasked
        assert [r.plugin for r in late_lines(caplog, "source.plugin_deadline")] == ["slow"]
        # The run stopped counting it, so a look at the source is not held behind it.
        assert pool.wait_for_runs("slow", timeout=0)
    finally:
        slow.gate.set()


def test_a_late_answer_after_the_deadline_is_discarded_and_logged_and_never_counted_as_an_answer(caplog):
    slow = Hung()
    roster = SourceRoster.of(finders=[slow], deadlines=Deadlines(finder=QUICK))

    with pytest.raises(ImageSearchFailure, match="did not answer within"):
        list(roster.finders[0].find_images(QUERY))
    with caplog.at_level(logging.WARNING):
        slow.gate.set()
        until(lambda: late_lines(caplog, "source.plugin_late"))

    (late,) = late_lines(caplog, "source.plugin_late")
    assert (late.plugin, late.operation) == ("slow", "find_images")
    assert "past its deadline; discarded" in late.getMessage()
    slow_reading = reading(roster, "slow")
    assert (slow_reading.unasked, slow_reading.answered) == (1, 0), "the late answer was counted"


def test_calls_still_running_past_their_deadline_are_bounded_and_a_returned_one_frees_its_place(caplog):
    slow = Hung()
    roster = SourceRoster.of(finders=[slow], deadlines=Deadlines(finder=QUICK, stragglers=2))
    finder = roster.finders[0]
    try:
        for _ in range(2):
            with pytest.raises(ImageSearchFailure, match="did not answer within"):
                list(finder.find_images(QUERY))
        assert slow.entered == 2

        started = time.monotonic()
        with pytest.raises(ImageSearchFailure, match="2 of its earlier calls are still running past their deadline"):
            list(finder.find_images(QUERY))
        assert time.monotonic() - started < QUICK, "a refused call waited out a deadline"
        assert slow.entered == 2, "the refused call was started anyway"
    finally:
        slow.gate.set()

    with caplog.at_level(logging.WARNING):
        until(lambda: len(late_lines(caplog, "source.plugin_late")) == 2)
    assert len(list(finder.find_images(QUERY))) == 1, "with its stragglers returned, the plugin is asked again"
    assert slow.entered == 3
    assert reading(roster, "slow").unasked == 3


def test_a_reader_a_preview_and_a_browse_each_have_their_deadline():
    slow = Hung()
    roster = SourceRoster.of(
        finders=[slow],
        collection=slow,
        readers={"slow": (claims_example, slow)},
        deadlines=Deadlines(reader=QUICK, preview=QUICK, browse=QUICK),
    )
    try:
        assert roster.finders[0].fetch_preview("https://slow.example/p.jpg") is None
        with pytest.raises(ImageSearchFailure, match="did not answer within"):
            roster.route("https://example.org/works/1").reader.read("https://example.org/works/1")
        with pytest.raises(CollectionBrowseFailure, match="did not answer within"):
            roster.collection.browse([], per_query=3)
    finally:
        slow.gate.set()

    slow_reading = reading(roster, "slow")
    assert (slow_reading.unasked, slow_reading.faults, slow_reading.answered) == (3, 0, 0)


def test_what_a_finder_said_before_its_deadline_is_kept():
    """The pool keeps what a source handed over before it failed, and a deadline is a way of failing."""
    early = an_image("Nighthawks", artist="Edward Hopper", provider="slow", url="https://slow.example/early")
    slow = Hung(yields=(early,))
    roster = SourceRoster.of(finders=[slow, StubFinder("good")], deadlines=Deadlines(finder=QUICK))
    try:
        answer = ImageSourcePool(roster.finders).find_images(QUERY)
    finally:
        slow.gate.set()

    assert answer.unreachable == ("slow",)
    assert sorted(image.url for image in answer.images) == [
        "https://good.example/Nighthawks",
        "https://slow.example/early",
    ]


# -- the pool's own deadline, for a finder handed to it unwrapped ---------------------


def test_the_pool_stops_waiting_for_an_unwrapped_finder_and_releases_it_to_looks():
    slow = Hung()
    pool = ImageSourcePool([slow, StubFinder("good")], deadline_seconds=QUICK)

    started = time.monotonic()
    try:
        answer = pool.find_images(QUERY)
        took = time.monotonic() - started
        assert took < QUICK + MARGIN, f"the pool waited {took:.1f} s"
        assert answer.unreachable == ("slow",)
        assert pool.wait_for_runs("slow", timeout=0)
    finally:
        slow.gate.set()


def test_a_late_answer_after_the_pool_moved_on_does_not_release_a_later_runs_ask(caplog):
    """The late ask ending releases nothing: the second run is still asking, and a look must still wait behind it."""
    first, second = threading.Event(), threading.Event()
    gates = iter((first, second))
    entered: list[int] = []

    class Twice(StubFinder):
        def find_images(self, query):
            gate = next(gates)
            entered.append(1)
            assert gate.wait(SETTLE)
            return super().find_images(query)

    pool = ImageSourcePool([Twice("slow"), StubFinder("good")], deadline_seconds=3.0)
    try:
        assert pool.find_images(QUERY).unreachable == ("slow",)
        later = threading.Thread(target=pool.find_images, args=(QUERY,), daemon=True)
        later.start()
        until(lambda: len(entered) == 2)
        assert not pool.wait_for_runs("slow", timeout=0), "the second run is asking"

        with caplog.at_level(logging.WARNING):
            first.set()
            until(lambda: late_lines(caplog, "image_pool.late"))

        assert not pool.wait_for_runs("slow", timeout=0), "the first run's late answer released the second run's ask"
    finally:
        first.set()
        second.set()
    later.join(SETTLE)
    assert pool.wait_for_runs("slow", timeout=0)


def test_a_source_that_answers_in_time_is_unchanged_by_the_deadline():
    pool = ImageSourcePool([StubFinder("good")], deadline_seconds=SETTLE)

    assert pool.ask("good", QUERY).outcome is AskOutcome.ANSWERED
    assert [image.provider for image in pool.find_images(QUERY).images] == ["good"]


# -- through the look, the caller that waited behind a hung run ------------------------

TANTRA = ItemId("Q20267229")
BILLE = RegistryCreator(qid=ItemId("Q5001"), name=RegistryText("Ejler Bille"))


@pytest.fixture
def registry() -> FakeRegistry:
    """The registry the services are built over, which knows the work the look asks about."""
    return FakeRegistry(
        works={TANTRA: RegistryWork(qid=TANTRA, title=RegistryText("Tantra-Vision"), sitelinks=3, creators=(BILLE,))}
    )


class HangsForTheRun(StubFinder):
    """A source that hangs only on the run's work, and answers the look's at once."""

    def __init__(self) -> None:
        super().__init__("smk")
        self.gate = threading.Event()
        self.entered = threading.Event()

    def find_images(self, query):
        if query.title == "A Work A Run Wants":
            self.entered.set()
            assert self.gate.wait(SETTLE)
        return ()


def test_a_look_is_not_kept_waiting_behind_a_run_whose_source_hung(services, settings, registry):
    smk = HangsForTheRun()
    pool = ImageSourcePool([smk], deadline_seconds=QUICK)
    look = LookService(
        works=services.registry_works,
        discovery=services.discovery,
        pool=pool,
        judge=PhaseTwoEngine(pool, profile=settings.quality_profile, registry=registry),
        pictures=PictureStore(
            services.pictures.art_root / PICTURES_DIRNAME,
            art_root=services.pictures.art_root,
            sources=pool,
            staging_token=counted_tokens(),
        ),
    )
    ended: list[str] = []

    def a_run() -> None:
        try:
            pool.find_images(ImageQuery(title="A Work A Run Wants"))
        except ImageSearchFailure as failure:
            ended.append(str(failure))

    run = threading.Thread(target=a_run, daemon=True)
    try:
        run.start()
        assert smk.entered.wait(SETTLE)

        # Held well short of the hung call's own give-up (SETTLE), so the look cannot
        # be freed by the run's call ending, only by the run letting the source go.
        view = look.look(TANTRA, hold=3.0)

        assert view.sources[0].state is not SourceState.ASKING, "the look waited behind the hung run"
        assert not smk.gate.is_set(), "the run's call is still hung: the look did not wait for it to end"
    finally:
        smk.gate.set()
        run.join(SETTLE)
    # The run settled without the hung source, as could not be asked.
    assert ended == ["No image source could be asked: SMK, National Gallery of Denmark."]


# -- a plugin may declare a longer deadline (1.5) --------------------------------------
#
# A page read through the private plugins' browser was measured at 77-100 s, and
# its worst case is 480 s, so the default 60 s would leave such a plugin "could
# not be asked" on every call. These run on simulated time: the plugin says when
# it would answer, and the host's wait is told how long it may wait, so 300 s is
# never waited out.


class SimulatedTime:
    """The host's wait for a call, on a clock the plugin moves: a call answering at `t` beats a deadline `d` when `t <= d`."""

    def __init__(self) -> None:
        self._asked = threading.Event()
        self._gate = threading.Event()
        self.answers_at: float | None = None
        self.waited_for: list[float] = []

    def sleep(self, seconds: float) -> None:
        """What the plugin calls instead of taking `seconds`: it returns when the host's wait has decided."""
        self.answers_at = seconds
        self._asked.set()
        assert self._gate.wait(SETTLE), "the host never decided"

    def wait_for(self, done: threading.Event, seconds: float) -> bool:
        """The host's wait: whether the call ended within `seconds` of simulated time."""
        self.waited_for.append(seconds)
        assert self._asked.wait(SETTLE), "the plugin was never asked"
        if self.answers_at is not None and self.answers_at <= seconds:
            self._gate.set()
            return done.wait(SETTLE)
        # Past the deadline: the call is left hung until the test releases it,
        # so it cannot finish in the moment between this answer and the host's.
        return False

    def release(self) -> None:
        """Let a call the host gave up on return, late."""
        self._gate.set()


def slow_plugin(clock: SimulatedTime, *, takes: float, deadlines=None) -> SourcePlugin:
    class Slow(StubFinder):
        def find_images(self, query):
            clock.sleep(takes)
            return super().find_images(query)

    return SourcePlugin(api_major=1, create=lambda _c: SourceParts(finder=Slow("slowpage")), api_minor=5, deadlines=deadlines)


def load_slow(clock: SimulatedTime, plugin: SourcePlugin) -> SourceRoster:
    point = importlib.metadata.EntryPoint(name="slowpage", value="plugin_fakes:GOOD", group=ENTRY_POINT_GROUP)
    return load_sources(
        SourceContext(environ={}, user_agent="arrt-tests/0", preview_max_bytes=1_000_000),
        entry_points=[_Fixed(point, plugin)],
        wait_for=clock.wait_for,
    )


class _Fixed:
    def __init__(self, point, plugin) -> None:
        self.name = point.name
        self._plugin = plugin

    def load(self):
        return self._plugin


def test_a_plugin_declaring_300_seconds_that_answers_at_200_is_not_cut_off():
    clock = SimulatedTime()
    roster = load_slow(clock, slow_plugin(clock, takes=200, deadlines={"finder": 300}))

    found = list(roster.finders[0].find_images(QUERY))

    assert [image.provider for image in found] == ["slowpage"]
    assert clock.waited_for == [300]
    assert reading(roster, "slowpage").answered == 1


def test_the_same_plugin_answering_at_301_is_cut_off_at_its_declared_300():
    clock = SimulatedTime()
    roster = load_slow(clock, slow_plugin(clock, takes=301, deadlines={"finder": 300}))

    try:
        with pytest.raises(ImageSearchFailure, match="did not answer within 300 seconds"):
            list(roster.finders[0].find_images(QUERY))
    finally:
        clock.release()
    assert reading(roster, "slowpage").unasked == 1


@pytest.mark.parametrize(("takes", "cut"), [(60, False), (61, True)])
def test_a_plugin_declaring_nothing_is_cut_at_the_default(takes, cut):
    clock = SimulatedTime()
    roster = load_slow(clock, slow_plugin(clock, takes=takes))

    if cut:
        try:
            with pytest.raises(ImageSearchFailure, match="did not answer within 60 seconds"):
                list(roster.finders[0].find_images(QUERY))
        finally:
            clock.release()
    else:
        assert len(list(roster.finders[0].find_images(QUERY))) == 1
    assert clock.waited_for == [FINDER_DEADLINE_SECONDS]


def test_a_declaration_for_one_kind_of_call_leaves_the_others_at_their_defaults():
    clock = SimulatedTime()
    roster = load_slow(clock, slow_plugin(clock, takes=1, deadlines={"preview": 90}))

    list(roster.finders[0].find_images(QUERY))

    assert clock.waited_for == [FINDER_DEADLINE_SECONDS]


# -- every kind a plugin may declare reaches the call it is for ----------------------
#
# `DEADLINE_KINDS` is the one list of kinds and `declared_deadlines` builds the
# `Deadlines` from a plugin's declaration. A kind in the list that the builder does
# not carry would load, validate, and run at the default: a plugin declaring an hour
# for it would be cut off at a minute with nothing said. These tests are
# parametrised over the list, so a kind added to it without its field, or a field
# the builder does not carry, fails by naming the kind.


def declared_value(kind: str) -> float:
    """A value no kind's default equals, different for each kind so a crossed wire shows."""
    return 1000.0 + 100.0 * DEADLINE_KINDS.index(kind) + 7.0


@pytest.mark.parametrize("kind", DEADLINE_KINDS)
def test_every_deadline_kind_is_a_float_field_of_deadlines(kind):
    fields = {field.name: field for field in dataclasses.fields(Deadlines)}
    assert kind in fields, f"{kind!r} is a deadline kind but not a field of Deadlines"
    assert isinstance(fields[kind].default, float), f"Deadlines.{kind} is not a float"


@pytest.mark.parametrize("kind", DEADLINE_KINDS)
def test_a_value_declared_for_any_kind_arrives_on_the_deadlines_and_no_other_changes(kind):
    base = Deadlines()
    declared = declared_value(kind)
    assert getattr(base, kind) != declared

    plugin = SourcePlugin(api_major=1, create=_never_called, api_minor=5, deadlines={kind: declared})
    got = declared_deadlines(plugin, base)

    assert isinstance(got, Deadlines), got
    assert getattr(got, kind) == declared, f"a plugin declared {declared} for {kind!r} and it runs at {getattr(got, kind)}"
    for other in dataclasses.fields(Deadlines):
        if other.name != kind:
            assert getattr(got, other.name) == getattr(base, other.name), f"declaring {kind!r} changed {other.name!r}"


class _Waits:
    """The host's wait, recording how long each call was told it may take, and then letting it finish."""

    def __init__(self) -> None:
        self.seconds: list[float] = []

    def wait_for(self, done: threading.Event, seconds: float) -> bool:
        self.seconds.append(seconds)
        return done.wait(SETTLE)


class _Browses:
    def __init__(self, provider: str) -> None:
        self.provider = provider

    def browse(self, queries, *, per_query: int):
        return []


#: What makes the call each kind is the deadline of, on a roster the loader built.
CALLS = {
    "finder": lambda roster: list(roster.finders[0].find_images(QUERY)),
    "preview": lambda roster: roster.finders[0].fetch_preview("https://waits.example/p.jpg"),
    "reader": lambda roster: roster.route("https://example.org/works/1").reader.read("https://example.org/works/1"),
    "browse": lambda roster: roster.collection.browse([], per_query=3),
}


@pytest.mark.parametrize("kind", DEADLINE_KINDS)
def test_a_deadline_declared_for_any_kind_is_what_the_loaded_plugin_is_waited_for(kind):
    """Through the loader: the plugin declares one kind, and the call of that kind is waited for that long."""
    assert kind in CALLS, f"teach CALLS to make a {kind!r} call: a deadline kind this test does not drive"
    waits = _Waits()
    plugin = SourcePlugin(
        api_major=1,
        create=lambda _c: SourceParts(finder=StubFinder("waits"), reader=StubReader(), collection=_Browses("waits")),
        api_minor=5,
        claims=claims_example,
        deadlines={kind: declared_value(kind)},
    )
    point = importlib.metadata.EntryPoint(name="waits", value="plugin_fakes:GOOD", group=ENTRY_POINT_GROUP)
    roster = load_sources(
        SourceContext(environ={}, user_agent="arrt-tests/0", preview_max_bytes=1_000_000),
        entry_points=[_Fixed(point, plugin)],
        wait_for=waits.wait_for,
    )
    (only,) = roster.observe()
    assert only.state is PluginState.LOADED, only.reason

    CALLS[kind](roster)

    assert waits.seconds == [declared_value(kind)]


@pytest.mark.parametrize(
    ("declared", "said"),
    [
        ({"finder": 3601}, "its finder deadline of 3601 seconds is past this Arrt's ceiling of 3600"),
        ({"reader": 0}, "its reader deadline of 0 is not a number of seconds above zero"),
        ({"browse": -5}, "its browse deadline of -5 is not a number of seconds above zero"),
        ({"finder": float("inf")}, "its finder deadline of inf is not a number of seconds above zero"),
        ({"finder": float("nan")}, "its finder deadline of nan is not a number of seconds above zero"),
        ({"finder": "300"}, "its finder deadline of '300' is not a number of seconds above zero"),
        ({"finder": True}, "its finder deadline of True is not a number of seconds above zero"),
        ({"finders": 300}, "it declares a deadline for 'finders', which is not a kind of call (finder, reader, preview, browse)"),
        (["finder"], "its deadlines are a list, not a mapping of kind of call to seconds"),
    ],
)
def test_a_declaration_out_of_bounds_is_refused_at_load_by_name(declared, said):
    plugin = SourcePlugin(api_major=1, create=_never_called, api_minor=5, deadlines=declared)  # type: ignore[arg-type]

    roster = load_slow(SimulatedTime(), plugin)

    (slow,) = roster.observe()
    assert (slow.state, slow.reason) == (PluginState.FAILED, said)
    assert roster.finders == ()


def _never_called(_context):
    raise AssertionError("a plugin refused at load has its factory called")


def test_a_declaration_at_the_ceiling_loads():
    assert DEADLINE_CEILING_SECONDS == 3600
    clock = SimulatedTime()
    roster = load_slow(clock, slow_plugin(clock, takes=3600, deadlines={"finder": 3600, "reader": 3600.0}))

    assert len(list(roster.finders[0].find_images(QUERY))) == 1


@pytest.mark.parametrize("seconds", [1012, 2044], ids=["one_page", "one_holder_behind_a_crawl_delay"])
def test_the_browser_plugins_honest_worst_case_loads_and_is_waited_for(seconds):
    """The private browser plugins' bounds allow these at worst; a ceiling below them would refuse the plugin at load."""
    clock = SimulatedTime()
    roster = load_slow(clock, slow_plugin(clock, takes=seconds, deadlines={"finder": seconds, "reader": seconds}))

    (slow,) = roster.observe()
    assert slow.state is not PluginState.FAILED, slow.reason
    assert len(list(roster.finders[0].find_images(QUERY))) == 1


def test_the_pool_waits_for_a_declared_deadline_and_no_longer_than_the_slowest_source_needs():
    """A run's backstop follows each source's own deadline, so it never cuts a declared plugin short.

    The fast source hangs and is cut by its own (default) deadline; the slow one
    declared longer and answers inside it. A pool waiting only the default would
    lose the slow one's answer.
    """
    hung = Hung("fast")
    late_gate = threading.Event()

    class Declared(StubFinder):
        def find_images(self, query):
            assert late_gate.wait(SETTLE)
            return super().find_images(query)

    plugin_fast = SourcePlugin(api_major=1, create=lambda _c: SourceParts(finder=hung))
    plugin_slow = SourcePlugin(
        api_major=1, create=lambda _c: SourceParts(finder=Declared("declared")), api_minor=5, deadlines={"finder": 1.5}
    )
    point = importlib.metadata.EntryPoint(name="x", value="plugin_fakes:GOOD", group=ENTRY_POINT_GROUP)
    fast_point, slow_point = _Fixed(point, plugin_fast), _Fixed(point, plugin_slow)
    fast_point.name, slow_point.name = "fast", "declared"
    roster = load_sources(
        SourceContext(environ={}, user_agent="arrt-tests/0", preview_max_bytes=1_000_000),
        entry_points=[fast_point, slow_point],
        deadlines=Deadlines(finder=QUICK),
    )
    pool = ImageSourcePool(roster.finders, margin_seconds=0.1)
    threading.Timer(0.8, late_gate.set).start()
    try:
        answer = pool.find_images(QUERY)
    finally:
        hung.gate.set()
        late_gate.set()

    assert answer.unreachable == ("fast",)
    assert [image.provider for image in answer.images] == ["declared"]
