"""A misbehaving source plugin, installed as a real one is, asked by a real Get, read back as a curator reads it.

The plugin host's parts have their own tests (`tests/unit/test_plugin_deadlines.py`,
`tests/unit/test_source_plugins.py`). This is the whole product around them: the
fixture distribution (`tests/fixtures/plugins/misbehaving/`) is installed into a
directory of this test's own, as an installer would lay it out, and found by the
loader through `importlib.metadata`, the call the loader makes, beside the
`steady` plugin of the same distribution. A Get is started over `/api` on the
suite's real uvicorn server, and what each case asserts is read off the routes
the browser reads: the run (`/api/runs/{id}`), the work's scans
(`/api/candidates/{id}/images`), Status (`/api/health`), Settings › Sources
(`/api/sources`), the Queue (`/api/acquisitions`) and the work (`/api/works/{id}`).

Every case holds the three things a household needs: the steady plugin beside
the misbehaving one still answers and its images arrive; the run finishes, and
Status says in words which source could not be asked and why; and no work is
recorded as held by nobody when the source that might hold it faulted.

**Time is simulated** (`SimulatedTime`): the host's wait is the loader's own
`wait_for` seam, and a plugin that takes minutes says so to the clock instead
of sleeping. A call the host gave up on stays parked on a real thread until the
test lets it go, and the fixture lets every one go, and waits for it, before the
test ends.

The built-in plugins are installed in this interpreter too, and four of them
search the network when loaded with no settings, so the loader is handed this
distribution's entry points, read from the installed metadata by the group scan
the loader itself makes, and no others.
"""

import importlib
import importlib.metadata
import logging
import shutil
import sys
import threading
import time
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Final

import httpx
import pytest
from fakes import FakeRegistry, a_decodable_jpeg

from arrt.library.registry import CommonsFile, ItemId, RegistryCreator, RegistryText, RegistryWork
from arrt.library.sources import SourceContext
from arrt.library.sources.loading import (
    DEADLINE_CEILING_SECONDS,
    ENTRY_POINT_GROUP,
    HOLD_BACK_AFTER,
    STRAGGLERS_PER_PLUGIN,
    SourceRoster,
    load_sources,
)
from arrt.mcp import bindings

FIXTURE: Final = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "misbehaving"
#: The distribution's metadata, in pyproject's `[project]` shape, in a file not
#: named `pyproject.toml`: a fixture is not one of the repository's projects.
PROJECT: Final = tomllib.loads((FIXTURE / "distribution.toml").read_text(encoding="utf-8"))["project"]
DISTRIBUTION: Final = PROJECT["name"]
PACKAGE: Final = "arrt_misbehaving"

#: Real seconds a run may take to finish once its sources have been decided.
#: The hung plugin's own deadline is 90 simulated seconds and the pool's
#: backstop 95 real ones, so a host that did not stop waiting at the deadline
#: fails here long before the backstop could rescue it.
FINISH_WITHIN: Final = 20.0
#: Real seconds anything a test waits on may take before the test fails.
SETTLE: Final = 20.0

DALI = RegistryCreator(qid=ItemId("Q5577"), name=RegistryText("Salvador Dalí"))
#: What steady holds.
HELD = ItemId("Q2001")
#: What only the misbehaving plugin could hold: steady looks and holds nothing.
ONLY_THERE = ItemId("Q2002")
#: Five works steady holds, for the stragglers' case.
FIVE = tuple(ItemId(f"Q21{n}") for n in range(5))
#: A work asked for after a hung call's late answer was let go.
LATER = ItemId("Q2003")

TITLES: Final = {
    HELD: "The Elephants",
    ONLY_THERE: "A Painting Only the Gallery Has",
    LATER: "Swans Reflecting Elephants",
    **{qid: f"Study No. {n}" for n, qid in enumerate(FIVE)},
}


class SimulatedTime:
    """The host's wait for a call, on a clock the plugin moves.

    `wait_for` is what the loader is handed. A deadline in `simulated` is a
    call of a plugin that takes its time on this clock (`take`): the call
    answers within it when the time it takes is at most the deadline, and is
    otherwise left parked, as a real call past its deadline is, until
    `release`. Any other deadline (steady's 60 s, a preview's 30 s) is waited
    for really, and those calls answer at once.

    `proceed` holds the host's decision until the test sets it, so a test can
    look at the server while a call is hanging.
    """

    def __init__(self, simulated: set[float]) -> None:
        self._simulated = frozenset(simulated)
        self._lock = threading.Lock()
        self._pending: list[_Take] = []
        self._parked: list[_Take] = []
        self.proceed = threading.Event()
        self.proceed.set()
        #: Every simulated decision: the deadline, the time the call took, whether it was in time.
        self.decisions: list[tuple[float, float, bool]] = []

    def take(self, seconds: float) -> None:
        """The plugin's side: block until the host has decided, then, if it gave up, until released."""
        taking = _Take(seconds)
        with self._lock:
            self._pending.append(taking)
        # Long, because a parked call is let go only at the test's end; never
        # reached by a passing test, whose fixture releases every call.
        taking.gate.wait(SETTLE * 3)

    def wait_for(self, done: threading.Event, seconds: float) -> bool:
        if seconds not in self._simulated:
            return done.wait(seconds)
        assert self.proceed.wait(SETTLE), "the test never let the host decide"
        ends = time.monotonic() + SETTLE
        while True:
            # A call of this plugin that took no time (it raised, or answered at once).
            if done.wait(0.005):
                return True
            with self._lock:
                if self._pending:
                    taking = self._pending.pop(0)
                    break
            assert time.monotonic() < ends, "a plugin call neither answered nor took time on the clock"
        in_time = taking.seconds <= seconds
        self.decisions.append((seconds, taking.seconds, in_time))
        if in_time:
            taking.gate.set()
            return done.wait(SETTLE)
        with self._lock:
            self._parked.append(taking)
        return False

    def release(self) -> None:
        """Let every call the host gave up on return, late."""
        with self._lock:
            parked, self._parked = self._parked, []
        for taking in parked:
            taking.gate.set()


@dataclass
class _Take:
    seconds: float
    gate: threading.Event = field(default_factory=threading.Event)


def install(site: Path) -> None:
    """Lay the fixture distribution out in `site` as an installer does: its package, and a `.dist-info` from its metadata file."""
    shutil.copytree(FIXTURE / PACKAGE, site / PACKAGE, ignore=shutil.ignore_patterns("__pycache__"))
    info = site / f"{DISTRIBUTION.replace('-', '_')}-{PROJECT['version']}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {DISTRIBUTION}\nVersion: {PROJECT['version']}\n", encoding="utf-8"
    )
    points = PROJECT["entry-points"][ENTRY_POINT_GROUP]
    (info / "entry_points.txt").write_text(
        f"[{ENTRY_POINT_GROUP}]\n" + "".join(f"{name} = {value}\n" for name, value in points.items()), encoding="utf-8"
    )
    (info / "INSTALLER").write_text("arrt-tests\n", encoding="utf-8")


def a_registry_work(qid: str) -> RegistryWork:
    return RegistryWork(
        qid=ItemId(qid),
        title=RegistryText(TITLES[qid]),
        sitelinks=10,
        image=CommonsFile(f"https://commons.wikimedia.org/wiki/Special:FilePath/{qid}.jpg"),
        creators=(DALI,),
    )


# -- the server, over the installed plugin ---------------------------------------------


@pytest.fixture
def clock() -> SimulatedTime:
    return SimulatedTime({90.0, DEADLINE_CEILING_SECONDS})


@pytest.fixture
def plugin(tmp_path, monkeypatch, clock) -> Iterator[ModuleType]:
    """The fixture distribution, installed and on the path, and its module as the loader will import it.

    At the end, every call the host gave up on is let go and waited for, so no
    plugin thread outlives the test.
    """
    site = tmp_path / "site-packages"
    site.mkdir()
    install(site)
    sys.modules.pop(PACKAGE, None)
    monkeypatch.syspath_prepend(str(site))
    module = importlib.import_module(PACKAGE)
    module.CONTROL.clock = clock
    module.CONTROL.preview = a_decodable_jpeg()
    module.CONTROL.steady_holds = {TITLES[HELD], *(TITLES[qid] for qid in FIVE)}
    try:
        yield module
    finally:
        clock.proceed.set()
        clock.release()
        control = module.CONTROL
        ends = time.monotonic() + SETTLE
        while control.returned < control.entered and time.monotonic() < ends:
            time.sleep(0.01)
        sys.modules.pop(PACKAGE, None)
        assert control.returned == control.entered, "a plugin call outlived its test"


@pytest.fixture
def plugin_names() -> tuple[str, ...]:
    """Which of the distribution's plugins this test's server loads."""
    return ("misbehaving", "steady")


@pytest.fixture
def sources(plugin, clock, plugin_names, settings) -> SourceRoster:
    """The installed distribution's plugins, found by the group scan the loader makes, waited for on simulated time."""
    found = [
        point
        for point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        if point.dist is not None and point.dist.name == DISTRIBUTION
    ]
    assert sorted(point.name for point in found) == sorted(
        PROJECT["entry-points"][ENTRY_POINT_GROUP]
    ), "the installed distribution's entry points are not what the loader's scan finds"
    return load_sources(
        SourceContext(environ={}, user_agent="arrt-tests/0", preview_max_bytes=settings.preview_max_bytes),
        entry_points=[point for point in found if point.name in plugin_names],
        wait_for=clock.wait_for,
    )


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry(works={qid: a_registry_work(qid) for qid in TITLES})


@pytest.fixture
def open_stream():
    """A holder serving one decodable image for every direct fetch."""
    served: list[str] = []

    @contextmanager
    def _open(url: str):
        served.append(url)
        yield iter([a_decodable_jpeg(6949, 8400)])

    _open.served = served
    return _open


@pytest.fixture
def http(server_url) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def start_get(http: httpx.Client, *qids: str) -> str:
    response = http.post("/api/gets", json={"qids": list(qids)})
    assert response.status_code == 200, response.text
    assert response.json()["skipped"] == []
    return response.json()["run"]["run_id"]


def finished(http: httpx.Client, run_id: str) -> dict:
    """The run once it has ended, within `FINISH_WITHIN` real seconds, or the test fails saying where it stood."""
    ends = time.monotonic() + FINISH_WITHIN
    while True:
        view = http.get(f"/api/runs/{run_id}").json()
        if view["run"]["is_terminal"]:
            return view
        assert time.monotonic() < ends, f"the Get did not finish within {FINISH_WITHIN:g} s: {view['run']['status']}"
        time.sleep(0.02)


def work_of(view: dict, qid: str) -> dict:
    return next(work for work in view["works"] if work["wikidata_qid"] == qid)


def scans(http: httpx.Client, work: dict) -> list[tuple[str, str]]:
    listing = http.get(f"/api/candidates/{work['work_id']}/images").json()
    return [(instance["provider"], instance["url"]) for instance in listing["instances"]]


def on_status(http: httpx.Client, name: str) -> dict:
    return next(source for source in http.get("/api/health").json()["sources"] if source["name"] == name)


def in_settings(http: httpx.Client, name: str) -> dict:
    return next(source for source in http.get("/api/sources").json()["sources"] if source["name"] == name)


def steady_still_answers(http: httpx.Client, view: dict, qid: str = HELD) -> None:
    """The household's first need: the well-behaved plugin's image is the work's, its picture kept."""
    work = work_of(view, qid)
    assert work["resolution_status"] == "resolved", work
    assert [provider for provider, _url in scans(http, work)] == ["steady"]
    card = http.get(f"/api/candidates/{work['work_id']}").json()
    assert card["shown"]["provider"] == "steady"
    assert card["shown"]["preview_available"] is True, card["shown"]["preview_note"]
    steady = on_status(http, "steady")
    assert (steady["state"], steady["faults"]) == ("loaded", 0)
    assert steady["description"] == "The Steady Museum plugin is loaded, with no faults since startup."


def not_recorded_as_held_by_nobody(view: dict, qid: str = ONLY_THERE) -> None:
    """The third: a work only the faulting source might hold waits, and is not called unresolved."""
    work = work_of(view, qid)
    assert (work["resolution_status"], work["unresolved_reason"]) == ("pending", None), work


# -- the cases ------------------------------------------------------------------------


@pytest.mark.plugin_fault_expected
def test_a_finder_that_raises_is_a_fault_on_status_and_the_work_it_might_hold_waits(http, plugin):
    plugin.CONTROL.mode = "raises"

    view = finished(http, start_get(http, HELD, ONLY_THERE))

    assert view["run"]["status"] == "completed", view["run"]
    steady_still_answers(http, view)
    not_recorded_as_held_by_nobody(view)
    gallery = on_status(http, "misbehaving")
    assert (gallery["state"], gallery["faults"]) == ("loaded", 2)
    assert gallery["last_fault"] == "KeyError: 'a field the page no longer has'"
    assert gallery["description"].startswith("The Misbehaving Gallery plugin is loaded, with 2 faults since startup")
    assert "works it would have answered wait instead of being settled" in gallery["description"]
    assert "It has answered nothing else since startup." in gallery["description"]
    assert in_settings(http, "misbehaving")["faults"] == 2, "Settings › Sources reads the plugin as Status does"


@pytest.mark.parametrize(
    ("mode", "said"),
    [
        ("wrong_type", "find_images answered an image whose estimated_width is '6949', not a positive int or None"),
        ("oversized", "find_images answered an image whose title is 5,000 characters, past 2,000"),
        ("not_a_list", "find_images answered a NoneType, not a list of FoundImage"),
    ],
)
@pytest.mark.plugin_fault_expected
def test_a_malformed_answer_is_a_contained_fault_on_status_and_nothing_of_it_is_kept(http, plugin, mode, said):
    plugin.CONTROL.mode = mode
    plugin.CONTROL.misbehaving_holds = {TITLES[HELD], TITLES[ONLY_THERE]}

    view = finished(http, start_get(http, HELD, ONLY_THERE))

    assert view["run"]["status"] == "completed", view["run"]
    steady_still_answers(http, view)
    not_recorded_as_held_by_nobody(view)
    gallery = on_status(http, "misbehaving")
    assert gallery["faults"] == 2
    assert gallery["last_fault"] == f"_InterfaceBreach: {said}"
    assert "Misbehaving Gallery plugin is loaded, with 2 faults" in gallery["description"]


def test_a_plugin_that_found_nothing_is_an_answer_and_the_work_nobody_holds_is_unresolved(http, plugin):
    """The control case: a real "found nothing", from every source, is recorded as one, and is no fault."""
    plugin.CONTROL.mode = "nothing"

    view = finished(http, start_get(http, HELD, ONLY_THERE))

    assert view["run"]["status"] == "completed", view["run"]
    steady_still_answers(http, view)
    nobody = work_of(view, ONLY_THERE)
    assert (nobody["resolution_status"], nobody["unresolved_reason"]) == ("unresolved", "not_held")
    gallery = on_status(http, "misbehaving")
    assert (gallery["faults"], gallery["description"]) == (
        0,
        "The Misbehaving Gallery plugin is loaded, with no faults since startup.",
    )


def test_a_hung_finder_is_could_not_be_asked_at_its_deadline_while_the_server_answers(http, plugin, clock, caplog):
    """Past its 90 s deadline the run moves on; meanwhile the server answers; the late answer is discarded."""
    plugin.CONTROL.mode = "hangs"
    clock.proceed.clear()

    run_id = start_get(http, HELD, ONLY_THERE)
    ends = time.monotonic() + SETTLE
    while plugin.CONTROL.entered < 1:
        assert time.monotonic() < ends, "the hung finder was never asked"
        time.sleep(0.01)
    # A second request, answered while the finder hangs and the run waits for it.
    health = http.get("/api/health")
    assert health.status_code == 200
    assert http.get(f"/api/runs/{run_id}").json()["run"]["is_terminal"] is False
    clock.proceed.set()
    with caplog.at_level(logging.WARNING):
        view = finished(http, run_id)

    assert view["run"]["status"] == "completed", view["run"]
    steady_still_answers(http, view)
    not_recorded_as_held_by_nobody(view)
    assert clock.decisions == [(90.0, 600.0, False), (90.0, 600.0, False)]
    gallery = on_status(http, "misbehaving")
    assert gallery["faults"] == 0, "a call past its deadline is could not be asked, not a fault"
    assert gallery["description"].startswith(
        "The Misbehaving Gallery plugin is loaded and has answered nothing since startup but that it could not be "
        "asked: 2 times"
    )
    assert "(the Misbehaving Gallery plugin could not be asked: it did not answer within 90 seconds)" in gallery["description"]

    # The late answers, let go in the middle of a later run, land in neither.
    plugin.CONTROL.mode = "nothing"

    def release_the_stragglers(_query) -> None:
        clock.release()
        ends = time.monotonic() + SETTLE
        while plugin.CONTROL.returned < 2 or len(_late(caplog)) < 2:
            assert time.monotonic() < ends, "the late answers never came back"
            time.sleep(0.01)

    plugin.CONTROL.on_steady_find = release_the_stragglers
    with caplog.at_level(logging.WARNING):
        later = finished(http, start_get(http, LATER))

    assert len(_late(caplog)) == 2, "each late answer is said to be discarded"
    every_scan = [scan for each in (view, later) for work in each["works"] for scan in scans(http, work)]
    assert not [url for provider, url in every_scan if provider == "misbehaving"], every_scan
    assert work_of(later, LATER)["resolution_status"] == "unresolved", "the later run heard only its own answers"


def _late(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if getattr(record, "event", None) == "source.plugin_late"]


def test_a_fifth_call_while_four_are_still_running_is_not_made_and_every_work_still_resolves(http, plugin, clock):
    """Two Gets, three works then two, because one Get is one pass.

    Since 2026-11-20 a pass stops asking a plugin after three could-not-be-asked
    answers in a row (`one_pass`), so one Get of five hung works makes
    three calls and never reaches the fourth still running. The straggler bound
    is the process's, across passes: the second Get's first call is the fourth
    still running, and its second is the fifth, which is not made.
    """
    plugin.CONTROL.mode = "hangs"
    assert STRAGGLERS_PER_PLUGIN == 4
    assert HOLD_BACK_AFTER == 3

    first = finished(http, start_get(http, *FIVE[:3]))
    view = finished(http, start_get(http, *FIVE[3:]))

    for each, qids in ((first, FIVE[:3]), (view, FIVE[3:])):
        assert each["run"]["status"] == "completed", each["run"]
        for qid in qids:
            steady_still_answers(http, each, qid)
    assert plugin.CONTROL.entered == 4, "the fifth call was made while four were still running"
    assert len(clock.decisions) == 4
    gallery = on_status(http, "misbehaving")
    assert "could not be asked: 5 times" in gallery["description"]
    assert (
        "(the Misbehaving Gallery plugin could not be asked: it was not asked, because 4 of its earlier calls are "
        "still running past their deadline)"
    ) in gallery["description"]


@pytest.mark.parametrize("plugin_names", [("overdue", "steady")])
def test_a_deadline_past_the_ceiling_is_refused_at_load_by_name_and_the_get_goes_on(http, plugin):
    view = finished(http, start_get(http, HELD))

    assert view["run"]["status"] == "completed", view["run"]
    steady_still_answers(http, view)
    overdue = in_settings(http, "overdue")
    assert (overdue["state"], overdue["reason"]) == (
        "failed",
        "its finder deadline of 3601 seconds is past this Arrt's ceiling of 3600",
    )
    assert (overdue["distribution"], overdue["version"]) == (DISTRIBUTION, PROJECT["version"])
    assert on_status(http, "overdue")["description"] == (
        "The Overdue Archive plugin is installed and was not loaded: "
        "its finder deadline of 3601 seconds is past this Arrt's ceiling of 3600."
    )


@pytest.mark.parametrize("plugin_names", [("patient", "steady")])
def test_a_plugin_that_uses_all_of_the_deadline_it_declared_is_waited_for_and_heard(http, plugin, clock):
    view = finished(http, start_get(http, HELD))

    assert view["run"]["status"] == "completed", view["run"]
    assert clock.decisions == [(DEADLINE_CEILING_SECONDS, DEADLINE_CEILING_SECONDS, True)]
    work = work_of(view, HELD)
    assert sorted(provider for provider, _url in scans(http, work)) == ["patient", "steady"]
    patient = on_status(http, "patient")
    assert patient["description"] == "The Patient Collection plugin is loaded, with no faults since startup."


@pytest.mark.plugin_fault_expected
def test_a_reader_that_raises_is_a_fault_on_status_and_the_steady_work_still_arrives(http, plugin, services):
    """Acquisition: the work the misbehaving plugin found cannot be read; the steady plugin's is fetched and held.

    The fault reaches the work as `faulted`, apart from could-not-be-asked, and
    waits for Arrt's next load of its plugins rather than the schedule: asking
    the same plugin again cannot help.
    """
    plugin.CONTROL.mode = "answers"
    plugin.CONTROL.misbehaving_holds = {TITLES[ONLY_THERE]}
    view = finished(http, start_get(http, HELD, ONLY_THERE))
    assert [provider for provider, _url in scans(http, work_of(view, ONLY_THERE))] == ["misbehaving"]

    accepted = {}
    for qid in (HELD, ONLY_THERE):
        answer = http.post(f"/api/candidates/{work_of(view, qid)['work_id']}/verdict", json={"verdict": "accepted"})
        assert answer.status_code == 200, answer.text
        accepted[qid] = answer.json()["artwork_id"]
    services.acquisition_queue.run()

    assert http.get(f"/api/works/{accepted[HELD]}").json()["acquisition"] is None, "the steady work's image is held"
    stuck = http.get(f"/api/works/{accepted[ONLY_THERE]}").json()["acquisition"]
    assert (stuck["phase"], stuck["outcome"], stuck["plugin"]) == ("failed", "faulted", "misbehaving"), stuck
    assert stuck["next_try_at"] is None, "a fault waits for the plugins' next load, not the schedule"
    assert stuck["failed_at"] is not None
    assert stuck["detail"] == "the Misbehaving Gallery plugin faulted while reading this source: RuntimeError"
    services.acquisition_queue.run()
    assert plugin.CONTROL.reads == 1, "a work the plugin faulted on was asked again under the same load"
    gallery = on_status(http, "misbehaving")
    assert (gallery["faults"], gallery["last_fault"]) == (1, "RuntimeError: the page has no 'image' key")


# -- interface 1.6: the page is gone ---------------------------------------------------


def test_a_1_5_plugin_that_says_a_dead_link_the_old_way_is_could_not_be_asked_exactly_as_before(http, plugin):
    """`misbehaving` declares 1.5 and raises `ImageSearchFailure` for a dead link: 1.6 changes nothing for it."""
    plugin.CONTROL.mode = "dead_link"

    view = finished(http, start_get(http, HELD, ONLY_THERE))

    assert view["run"]["status"] == "completed", view["run"]
    steady_still_answers(http, view)
    not_recorded_as_held_by_nobody(view)
    gallery = on_status(http, "misbehaving")
    assert (gallery["state"], gallery["faults"], gallery["unasked"], gallery["answered"]) == ("loaded", 0, 2, 0)
    assert gallery["last_unasked"] == "every page the item links at the gallery answered 404"
    assert in_settings(http, "misbehaving")["unasked"] == 2, "Settings › Sources counts it as Status does"


@pytest.mark.parametrize("plugin_names", [("gone", "steady")])
def test_a_finder_answering_that_every_page_is_gone_settles_the_work_it_alone_might_hold(http, plugin):
    """A work whose only page at a holder is dead settled nowhere, searched again for ever."""
    plugin.CONTROL.gone_for = {TITLES[ONLY_THERE]}

    view = finished(http, start_get(http, HELD, ONLY_THERE))

    assert view["run"]["status"] == "completed", view["run"]
    nobody = work_of(view, ONLY_THERE)
    assert (nobody["resolution_status"], nobody["unresolved_reason"]) == ("unresolved", "not_held"), nobody
    archive = on_status(http, "gone")
    assert (archive["state"], archive["faults"], archive["unasked"]) == ("loaded", 0, 0), archive
    assert archive["answered"] == 2, "a page gone is an answer, counted as one"


@pytest.mark.parametrize("plugin_names", [("gone", "steady")])
def test_a_reader_answering_that_the_page_is_gone_settles_the_work_and_queue_groups_it_by_the_plugin(http, plugin, services):
    view = finished(http, start_get(http, ONLY_THERE))
    work = work_of(view, ONLY_THERE)
    assert [provider for provider, _url in scans(http, work)] == ["gone"]
    answer = http.post(f"/api/candidates/{work['work_id']}/verdict", json={"verdict": "accepted"})
    assert answer.status_code == 200, answer.text
    artwork_id = answer.json()["artwork_id"]

    services.acquisition_queue.run()

    settled = http.get(f"/api/works/{artwork_id}").json()
    acquisition = settled["acquisition"]
    assert (acquisition["phase"], acquisition["outcome"], acquisition["plugin"]) == ("gave_up", "link_gone", "gone")
    (source,) = [each for each in settled["sources"] if each["provider"] == "gone"]
    assert source["last_fetch_status"] == "failed", "the coarse status an older release reads is unchanged"
    # The served catalogue's seeded works fail too, each under its own words.
    (cause,) = [each for each in http.get("/api/acquisitions/causes").json()["causes"] if each["outcome"]]
    assert (cause["outcome"], cause["plugin"], cause["museum"], cause["gave_up"]) == (
        "link_gone",
        "gone",
        "Gone Archive",
        1,
    )
    assert cause["cause"].startswith("The Gone Archive plugin read that the source's page is gone")
    assert services.acquisition_queue.run().due == 0, "a settled work is not asked again"


@pytest.mark.parametrize("plugin_names", [("gone", "steady")])
def test_every_sentence_and_field_naming_a_plugin_from_outside_names_the_museum_it_declares(http, plugin, services):
    """The source's sentence, its troubles' words, the sources answer and a failure cause's museum: one name, the plugin's own.

    Each is read from the plugin's own reading (`SourceHealth.museum`), never
    from what the latest load declared process-wide: a second load in this
    process (another host, the plugin-testing helper's) replaces that, and
    the sentence then named the plugin by its id beside a `museum` field that
    named the museum.
    """
    view = finished(http, start_get(http, ONLY_THERE))
    answer = http.post(f"/api/candidates/{work_of(view, ONLY_THERE)['work_id']}/verdict", json={"verdict": "accepted"})
    assert answer.status_code == 200, answer.text
    services.acquisition_queue.run()
    from arrt.library.sources import names

    names.declare_museums({})  # as another load in this process would

    assert on_status(http, "gone")["description"].startswith("The Gone Archive plugin is loaded"), on_status(http, "gone")
    assert on_status(http, "gone")["museum"] == in_settings(http, "gone")["museum"] == "Gone Archive"
    (cause,) = [each for each in http.get("/api/acquisitions/causes").json()["causes"] if each["outcome"]]
    assert (cause["plugin"], cause["museum"]) == ("gone", "Gone Archive")
    # The cause's sentence names the museum its `museum` field beside it names:
    # one owner, so the two cannot differ however the process-wide names stand.
    assert cause["cause"].startswith(f"The {cause['museum']} plugin read"), cause
    over_mcp = bindings._failures(services, {})
    assert [each["museum"] for each in over_mcp["causes"] if each["outcome"]] == ["Gone Archive"]
    assert [each["cause"] for each in over_mcp["causes"] if each["outcome"]] == [cause["cause"]]
    assert {each["name"]: each["museum"] for each in bindings._image_sources(services, {})["sources"]}["gone"] == "Gone Archive"


@pytest.mark.parametrize("plugin_names", [("newer", "steady")])
def test_a_plugin_needing_interface_1_7_is_refused_at_load_by_name_and_the_get_goes_on(http, plugin):
    view = finished(http, start_get(http, HELD))

    assert view["run"]["status"] == "completed", view["run"]
    steady_still_answers(http, view)
    newer = in_settings(http, "newer")
    assert (newer["state"], newer["reason"]) == ("failed", "it needs source interface 1.7, and this Arrt is 1.6")
