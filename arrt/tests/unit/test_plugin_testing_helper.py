"""`arrt.library.sources.testing`: a plugin tested as the host runs it, shown on the misbehaving fixture plugins.

The fixture distribution of `tests/integration/test_a_misbehaving_plugin.py`
(`tests/fixtures/plugins/misbehaving/`, six plugins declaring 1.4 to 1.7) is
what the helper is shown on: each plugin gets, through the helper alone and with
no server, the outcome that end-to-end test already proves for it over `/api`.
The helper's own claim is that it runs the host's code, so the second half of
this file swaps a piece of the host and watches the helper's answer move.

The guide's section on the helper (`docs/source-plugins.md` § A plugin tested as
the host runs it) is held to the module here: its names, its parameters, its
fields, and the version rule it states.
"""

import dataclasses
import importlib
import importlib.metadata
import inspect
import pathlib
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from types import ModuleType
from typing import Final

import pytest
from fakes import FakeRegistry

from arrt.library import sources as interface
from arrt.library.discovery.images import FoundImage, ImageQuery
from arrt.library.sources import Declined, FetchLocator, ImageSearchFailure, ItemId, SourceParts, SourcePlugin
from arrt.library.sources import testing as plugin_testing
from arrt.library.sources.loading import DEADLINE_CEILING_SECONDS, ENTRY_POINT_GROUP
from arrt.library.sources.testing import (
    AskOutcome,
    FetchOutcome,
    JudgedInstance,
    NotAvailable,
    PluginHost,
    RetryRule,
    UnresolvedReason,
    WouldFetch,
    host,
)

FIXTURE: Final = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "misbehaving"
PACKAGE: Final = "arrt_misbehaving"
#: The plugin author's guide: outside `arrt/`, so the image's test stage carries it (`arrt/Dockerfile`).
GUIDE: Final = pathlib.Path(__file__).resolve().parents[3] / "docs" / "source-plugins.md"
SECTION: Final = "### A plugin tested as the host runs it"

#: Real seconds anything waited on may take.
SETTLE: Final = 10.0

MISBEHAVING_URL: Final = "https://misbehaving.example.org/works/1"
STEADY_URL: Final = "https://steady.example.org/works/1"
GONE_URL: Final = "https://gone.example.org/works/1"
NOBODYS_URL: Final = "https://nobody.example.net/works/1"


class FixtureClock:
    """The fixture's clock: a call that takes time parks until the test lets it go."""

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.taken: list[float] = []

    def take(self, seconds: float) -> None:
        self.taken.append(seconds)
        self.gate.wait(SETTLE * 3)


@pytest.fixture
def fixture() -> Iterator[ModuleType]:
    """The fixture distribution's module, freshly imported; every call it parked is let go at the end."""
    sys.path.insert(0, str(FIXTURE))
    sys.modules.pop(PACKAGE, None)
    try:
        module = importlib.import_module(PACKAGE)
        module.CONTROL.clock = FixtureClock()
        yield module
    finally:
        control = module.CONTROL
        control.clock.gate.set()
        ends = time.monotonic() + SETTLE
        while control.returned < control.entered and time.monotonic() < ends:
            time.sleep(0.01)
        sys.modules.pop(PACKAGE, None)
        sys.path.remove(str(FIXTURE))
        assert control.returned == control.entered, "a plugin call outlived its test"


def asked_for(title: str, **fields: object) -> ImageQuery:
    return ImageQuery(title=title, **fields)  # type: ignore[arg-type]


def never_in_time(done: threading.Event, seconds: float) -> bool:
    """The host's wait, when the plugin's call is not answered within the deadline."""
    return False


def waiting_and_noting(noted: list[float]) -> Callable[[threading.Event, float], bool]:
    """The host's own wait, which says what deadline it was given."""

    def wait(done: threading.Event, seconds: float) -> bool:
        noted.append(seconds)
        return done.wait(seconds)

    return wait


# -- the fixture plugins, each given through the helper the outcome its end-to-end test proves ------


@pytest.mark.plugin_fault_expected
def test_a_finder_that_raises_is_unreachable_and_a_fault_and_the_work_it_might_hold_waits(fixture):
    fixture.CONTROL.mode = "raises"
    gallery = host(fixture.MISBEHAVING, name="misbehaving")

    asked = gallery.ask(asked_for("A Painting Only the Gallery Has"))

    assert (asked.outcome, asked.faulted, asked.images) == (AskOutcome.UNREACHABLE, True, ())
    assert asked.failure == "the Misbehaving Gallery plugin faulted: KeyError"
    assert (gallery.reading.faults, gallery.reading.last_fault) == (1, "KeyError: 'a field the page no longer has'")
    settled = gallery.resolve(asked_for("A Painting Only the Gallery Has"))
    assert settled.waits is not None
    assert settled.instances == ()


@pytest.mark.plugin_fault_expected
@pytest.mark.parametrize(
    ("mode", "said"),
    [
        ("wrong_type", "find_images answered an image whose estimated_width is '6949', not a positive int or None"),
        ("oversized", "find_images answered an image whose title is 5,000 characters, past 2,000"),
        ("not_a_list", "find_images answered a NoneType, not a list of FoundImage"),
    ],
)
def test_a_malformed_answer_is_a_contained_fault_and_nothing_of_it_is_kept(fixture, mode, said):
    fixture.CONTROL.mode = mode
    fixture.CONTROL.misbehaving_holds = {"The Elephants"}
    gallery = host(fixture.MISBEHAVING, name="misbehaving")

    asked = gallery.ask(asked_for("The Elephants"))

    assert (asked.outcome, asked.faulted, asked.images) == (AskOutcome.UNREACHABLE, True, ())
    assert gallery.reading.last_fault == f"_InterfaceBreach: {said}"


def test_a_finder_that_found_nothing_is_an_answer_and_no_fault(fixture):
    fixture.CONTROL.mode = "nothing"
    gallery = host(fixture.MISBEHAVING, name="misbehaving")

    asked = gallery.ask(asked_for("The Elephants"))
    settled = gallery.resolve(asked_for("The Elephants"))

    assert (asked.outcome, asked.faulted, asked.failure) == (AskOutcome.ANSWERED, False, None)
    assert (settled.waits, settled.instances, settled.refusals) == (None, (), frozenset())
    reading = gallery.reading
    assert (reading.state, reading.faults, reading.unasked, reading.answered) == ("loaded", 0, 0, 2)


def test_a_hung_finder_is_could_not_be_asked_at_the_deadline_it_declared_and_no_fault(fixture):
    fixture.CONTROL.mode = "hangs"
    noted: list[float] = []
    gallery = host(fixture.MISBEHAVING, name="misbehaving", wait_for=lambda done, seconds: noted.append(seconds) or False)

    asked = gallery.ask(asked_for("The Elephants"))

    assert noted == [90.0], "the host waited for the deadline the plugin declared"
    assert (asked.outcome, asked.faulted) == (AskOutcome.UNREACHABLE, False)
    assert asked.failure == "the Misbehaving Gallery plugin could not be asked: it did not answer within 90 seconds"
    assert (gallery.reading.faults, gallery.reading.unasked) == (
        0,
        1,
    ), "a call past its deadline is could not be asked, not a fault"


def test_a_fifth_call_while_four_are_still_running_is_not_made(fixture):
    fixture.CONTROL.mode = "hangs"
    gallery = host(fixture.MISBEHAVING, name="misbehaving", wait_for=never_in_time)

    answers = [gallery.ask(asked_for(f"Study No. {n}")) for n in range(5)]

    assert fixture.CONTROL.entered == 4, "the fifth call was made while four were still running"
    assert {each.outcome for each in answers} == {AskOutcome.UNREACHABLE}
    assert answers[4].failure == (
        "the Misbehaving Gallery plugin could not be asked: it was not asked, because 4 of its earlier calls are "
        "still running past their deadline"
    )


def test_a_1_5_plugin_that_says_a_dead_link_the_old_way_is_could_not_be_asked_exactly_as_before(fixture):
    fixture.CONTROL.mode = "dead_link"
    gallery = host(fixture.MISBEHAVING, name="misbehaving")

    asked = gallery.ask(asked_for("The Elephants"))
    settled = gallery.resolve(asked_for("The Elephants"))

    assert (asked.outcome, asked.faulted) == (AskOutcome.UNREACHABLE, False)
    assert asked.failure == "every page the item links at the gallery answered 404"
    assert settled.waits is not None, "the work waits and is asked again"
    reading = gallery.reading
    assert (reading.faults, reading.unasked, reading.answered) == (0, 2, 0)
    assert reading.last_unasked == "every page the item links at the gallery answered 404"


def test_a_finder_answering_that_every_page_is_gone_settles_the_work_and_counts_as_an_answer(fixture):
    fixture.CONTROL.gone_for = {"A Painting Only the Gallery Has"}
    archive = host(fixture.GONE, name="gone")

    asked = archive.ask(asked_for("A Painting Only the Gallery Has"))
    settled = archive.resolve(asked_for("A Painting Only the Gallery Has"))

    assert (asked.outcome, asked.faulted, asked.images) == (AskOutcome.LINK_GONE, False, ())
    assert asked.failure == "every page the item links at the Gone Archive answered 404"
    assert (settled.waits, settled.instances) == (None, ()), "settled as held by nobody, not waiting for ever"
    reading = archive.reading
    assert (reading.state, reading.faults, reading.unasked, reading.answered) == ("loaded", 0, 0, 2)


def test_a_finder_that_has_the_work_answers_with_it(fixture):
    archive = host(fixture.GONE, name="gone")

    asked = archive.ask(asked_for("The Elephants"))

    assert asked.outcome is AskOutcome.ANSWERED
    assert [image.provider for image in asked.images] == ["gone"]
    settled = archive.resolve(asked_for("The Elephants"))
    assert [(each.found.provider, each.meets_minimum) for each in settled.instances] == [("gone", True)]
    assert settled.instances[0].confidence > 0


def test_a_reader_answering_that_the_page_is_gone_is_link_gone_settled_until_the_item_changes(fixture):
    archive = host(fixture.GONE, name="gone")

    read = archive.read(GONE_URL)

    assert (read.plugin, read.outcome, read.again, read.fetch) == ("gone", FetchOutcome.LINK_GONE, RetryRule.SETTLED, None)
    assert read.detail == f"the Gone Archive plugin read that this source's page is gone: {GONE_URL} answered 410"


@pytest.mark.plugin_fault_expected
def test_a_reader_that_raises_is_faulted_and_waits_for_the_plugins_next_load(fixture):
    gallery = host(fixture.MISBEHAVING, name="misbehaving")

    read = gallery.read(MISBEHAVING_URL)

    assert (read.outcome, read.again) == (FetchOutcome.FAULTED, RetryRule.NEXT_LOAD)
    assert read.detail == "the Misbehaving Gallery plugin faulted while reading this source: RuntimeError"
    assert gallery.reading.last_fault == "RuntimeError: the page has no 'image' key"


def test_a_reader_that_answers_is_not_fetched_and_says_what_the_host_would_fetch(fixture):
    steady = host(fixture.STEADY, name="steady")

    read = steady.read(STEADY_URL)

    assert (read.plugin, read.outcome, read.again, read.fetch) == ("steady", None, None, WouldFetch("direct", STEADY_URL))


def test_the_address_the_reader_answered_is_checked_as_the_host_checks_it(fixture):
    steady = host(fixture.STEADY, name="steady")

    read = steady.read(STEADY_URL, resolve=lambda name: ["127.0.0.1"])

    assert (read.outcome, read.again, read.fetch) == (FetchOutcome.FAILED, RetryRule.SCHEDULE, None)
    assert "the address the Steady Museum plugin read was refused" in read.detail
    assert "which is not a public address" in read.detail


def test_a_url_no_plugin_claims_is_fetched_as_recorded(fixture):
    steady = host(fixture.STEADY, name="steady")

    read = steady.read(NOBODYS_URL)

    assert (read.plugin, read.outcome, read.fetch) == (None, None, WouldFetch("direct", NOBODYS_URL))


def test_a_plugin_that_uses_all_of_the_deadline_it_declared_is_waited_for_and_heard(fixture):
    fixture.CONTROL.clock.gate.set()
    noted: list[float] = []
    patient = host(fixture.PATIENT, name="patient", wait_for=waiting_and_noting(noted))

    asked = patient.ask(asked_for("The Elephants"))

    assert noted == [DEADLINE_CEILING_SECONDS]
    assert (asked.outcome, [image.provider for image in asked.images]) == (AskOutcome.ANSWERED, ["patient"])


def test_a_deadline_past_the_ceiling_is_refused_at_load_by_name(fixture):
    overdue = host(fixture.OVERDUE, name="overdue")

    assert (overdue.reading.state, overdue.reading.reason) == (
        "failed",
        "its finder deadline of 3601 seconds is past this Arrt's ceiling of 3600",
    )
    with pytest.raises(NotAvailable, match="did not load"):
        overdue.ask(asked_for("The Elephants"))


def test_a_plugin_needing_interface_1_7_is_refused_at_load_by_name(fixture):
    newer = host(fixture.NEWER, name="newer")

    assert (newer.reading.state, newer.reading.reason) == ("failed", "it needs source interface 1.7, and this Arrt is 1.6")


def test_an_entry_point_is_loaded_the_way_the_host_loads_it_so_a_typo_in_one_fails_here():
    sys.path.insert(0, str(FIXTURE))
    try:
        good = importlib.metadata.EntryPoint("gone", f"{PACKAGE}:GONE", ENTRY_POINT_GROUP)
        typo = importlib.metadata.EntryPoint("gone", f"{PACKAGE}:GONNE", ENTRY_POINT_GROUP)
        assert host(good).reading.state == "loaded"
        assert host(typo).reading.state == "failed"
        assert "it could not be imported" in (host(typo).reading.reason or "")
    finally:
        sys.modules.pop(PACKAGE, None)
        sys.path.remove(str(FIXTURE))


def test_a_plugin_in_hand_is_loaded_under_a_name():
    with pytest.raises(TypeError, match="pass `name`"):
        host(SourcePlugin(api_major=1, create=lambda context: Declined("not configured")))


# -- what the host says of a plugin that is installed and not loaded --------------------------------


def test_a_plugin_that_declined_has_its_reason_and_the_urls_it_claims_are_a_deployment_fault_not_a_failed_fetch():
    plugin = SourcePlugin(
        api_major=1,
        create=lambda context: Declined("FOO_AGENT is not set"),
        claims=lambda url: url.startswith("https://foo.example.org/"),
        museum="Foo Museum",
    )
    foo = host(plugin, name="foo")

    assert (foo.reading.state, foo.reading.reason) == ("declined", "FOO_AGENT is not set")
    read = foo.read("https://foo.example.org/works/1")
    assert (read.plugin, read.outcome, read.fetch) == ("foo", None, None)
    assert read.unavailable == "the Foo Museum source plugin is installed and not loaded: FOO_AGENT is not set"
    with pytest.raises(NotAvailable, match="declined"):
        foo.ask(asked_for("The Elephants"))


def test_a_plugin_with_no_finder_has_nothing_to_ask():
    plugin = SourcePlugin(
        api_major=1,
        create=lambda context: SourceParts(reader=_Reader()),
        claims=lambda url: url.startswith("https://foo.example.org/"),
    )
    reader_only = host(plugin, name="foo")

    with pytest.raises(NotAvailable, match="no finder"):
        reader_only.ask(asked_for("The Elephants"))
    assert reader_only.read("https://foo.example.org/works/1").fetch == WouldFetch("direct", "https://foo.example.org/works/1")


class _Reader:
    def read(self, url: str) -> FetchLocator:
        return FetchLocator.direct(url)


@pytest.mark.parametrize(
    ("what", "locator", "outcome", "again"),
    [
        ("holds nothing", FetchLocator.none("the record shows no image"), FetchOutcome.NONE_HELD, RetryRule.SETTLED),
        ("could not be asked", ImageSearchFailure("the site is down"), FetchOutcome.UNASKED, RetryRule.NEXT_PASS),
    ],
)
def test_a_readers_other_answers_reach_the_outcomes_the_guide_tabulates(what, locator, outcome, again):
    class Answers:
        def read(self, url: str) -> FetchLocator:
            if isinstance(locator, Exception):
                raise locator
            return locator

    plugin = SourcePlugin(
        api_major=1,
        create=lambda context: SourceParts(reader=Answers()),
        claims=lambda url: url.startswith("https://foo.example.org/"),
        museum="Foo Museum",
    )

    read = host(plugin, name="foo").read("https://foo.example.org/works/1")

    assert (read.outcome, read.again) == (outcome, again), what


# -- phase two's verdict on one image ------------------------------------------------------------


def a_found(title: str, artist: str | None, url: str = "https://steady.example.org/works/1", **fields: object) -> FoundImage:
    base: dict[str, object] = {
        "url": url,
        "provider": "steady",
        "source_class": interface.SourceClass.INSTITUTIONAL,
        "acquisition_method": interface.AcquisitionMethod.DIRECT_HTTP,
        "title": title,
        "artist": artist,
        "estimated_width": 6949,
        "estimated_height": 8400,
        "rights_status": interface.RightsStatus.PUBLIC_DOMAIN,
    }
    return FoundImage(**{**base, **fields})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("found", "verdict"),
    [
        (a_found("The Elephants", "Salvador Dali"), "kept"),
        (a_found("The Elephants", "Giorgio de Chirico"), UnresolvedReason.IDENTITY_REFUSED),
        (a_found("A Different Work", "Salvador Dali"), UnresolvedReason.NOT_HELD),
        (a_found("The Elephants", "Salvador Dali", estimated_width=None), UnresolvedReason.SIZE_UNKNOWN),
    ],
    ids=["kept", "another-artist", "another-work", "no-size"],
)
def test_phase_twos_verdict_on_an_image_is_the_gate_that_refused_it_or_the_judgement(fixture, found, verdict):
    steady = host(fixture.STEADY, name="steady")

    judged = steady.judge(asked_for("The Elephants", artist="Salvador Dali"), found)

    if verdict == "kept":
        assert isinstance(judged, JudgedInstance)
        assert judged.meets_minimum
        assert judged.confidence > 0.9
    else:
        assert judged is verdict


def test_an_image_whose_title_differs_is_kept_when_the_registry_given_records_its_page(fixture):
    linked_page = "https://steady.example.org/works/linked"
    query = asked_for("The Elephants", artist="Salvador Dali", qid=ItemId("Q1"))
    found = a_found("Les Elephants", "Salvador Dali", url=linked_page)

    without = host(fixture.STEADY, name="steady").judge(query, found)
    with_the_item = host(fixture.STEADY, name="steady", registry=FakeRegistry(pages={"Q1": [linked_page]})).judge(query, found)

    assert without is UnresolvedReason.NOT_HELD
    assert isinstance(with_the_item, JudgedInstance)
    assert "Wikidata" in with_the_item.rationale


def test_the_minimum_judged_against_is_the_testers(fixture):
    steady = host(fixture.STEADY, name="steady")
    query = asked_for("The Elephants", artist="Salvador Dali")
    found = a_found("The Elephants", "Salvador Dali", estimated_width=1500, estimated_height=1200)

    assert steady.judge(query, found).meets_minimum is True
    assert steady.judge(query, found, minimum_long_edge_px=2000).meets_minimum is False


# -- the helper runs the host's own code: swap a piece of it and the helper's answer moves ------------


def test_a_reader_s_outcome_is_the_one_acquisitions_own_function_chooses(fixture, monkeypatch):
    from arrt.library.acquisition import service

    archive = host(fixture.GONE, name="gone")
    assert archive.read(GONE_URL).outcome is FetchOutcome.LINK_GONE
    monkeypatch.setattr(service, "_read_failure", lambda exc, museum: (f"swapped: {exc}", FetchOutcome.UNASKED))

    assert archive.read(GONE_URL).outcome is FetchOutcome.UNASKED


def test_when_the_host_asks_again_is_the_queues_own_table(fixture, monkeypatch):
    from arrt.library.acquisition import queue

    archive = host(fixture.GONE, name="gone")
    monkeypatch.setitem(queue.RETRY_RULES, FetchOutcome.LINK_GONE, RetryRule.NEXT_PASS)

    assert archive.read(GONE_URL).again is RetryRule.NEXT_PASS


def test_how_a_finders_answer_is_sorted_is_the_pools_own_function(fixture, monkeypatch):
    from arrt.library.discovery import pool

    archive = host(fixture.GONE, name="gone")
    fixture.CONTROL.gone_for = {"The Elephants"}
    assert archive.ask(asked_for("The Elephants")).outcome is AskOutcome.LINK_GONE
    monkeypatch.setattr(pool, "LinkGone", type("NotTheInterfacesLinkGone", (Exception,), {}))

    assert archive.ask(asked_for("The Elephants")).outcome is AskOutcome.UNREACHABLE


def test_the_gate_that_refuses_an_image_is_phase_twos_own(fixture, monkeypatch):
    from arrt.library.discovery import phase_two

    steady = host(fixture.STEADY, name="steady")
    query = asked_for("The Elephants", artist="Salvador Dali")
    found = a_found("The Elephants", "Giorgio de Chirico")
    assert steady.judge(query, found) is UnresolvedReason.IDENTITY_REFUSED
    monkeypatch.setattr(phase_two, "_confidence", lambda query, found: 0.5)

    assert isinstance(steady.judge(query, found), JudgedInstance)


def test_what_the_loader_refuses_is_the_loaders_own(fixture, monkeypatch):
    from arrt.library.sources import loading

    assert host(fixture.GONE, name="gone").reading.state == "loaded"
    monkeypatch.setattr(loading, "API_VERSION", (1, 5))

    refused = host(fixture.GONE, name="gone").reading
    assert (refused.state, refused.reason) == ("failed", "it needs source interface 1.6, and this Arrt is 1.5")


def test_the_deadline_the_host_waits_is_the_one_the_loader_took_from_the_plugin(fixture):
    noted: list[float] = []
    steady = host(fixture.STEADY, name="steady", wait_for=waiting_and_noting(noted))
    patient = host(fixture.PATIENT, name="patient", wait_for=waiting_and_noting(noted))
    fixture.CONTROL.clock.gate.set()

    steady.ask(asked_for("The Elephants"))
    patient.ask(asked_for("The Elephants"))

    assert noted == [60.0, 3600.0], "the host's default for a finder, then the one the plugin declared"


# -- the guide's section is held to the module -------------------------------------------------------


def _section() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index(SECTION)
    following = re.search(r"^\*\*The built-ins are the examples\*\*", text[start + len(SECTION) :], re.MULTILINE)
    return text[start : len(text) if following is None else start + len(SECTION) + following.start()]


def _table(header: str) -> list[list[str]]:
    lines = _section().splitlines()
    start = lines.index(header)
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip().strip("`") for cell in line.strip("|").split("|")])
    return rows


def _parameters(function: Callable[..., object]) -> str:
    """A callable's parameters as the guide writes them: names, `*` before keyword-only ones, `=` where there is a default."""
    shown, starred = [], False
    for name, parameter in inspect.signature(function).parameters.items():
        if name == "self":
            continue
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY and not starred:
            shown.append("*")
            starred = True
        shown.append(name + ("=" if parameter.default is not inspect.Parameter.empty else ""))
    return "(" + ", ".join(shown) + ")"


def _public_callables() -> dict[str, Callable[..., object]]:
    found: dict[str, Callable[..., object]] = {"host": host}
    for name in ("ask", "resolve", "judge", "read"):
        found[f"PluginHost.{name}"] = getattr(PluginHost, name)
    return found


def test_the_guide_lists_exactly_the_names_the_module_makes_public():
    rows = _table("| Name | What it is |")

    assert sorted(row[0] for row in rows) == sorted(plugin_testing.__all__)


def test_the_guide_gives_each_callable_the_parameters_the_code_has():
    rows = _table("| Callable | Parameters |")

    assert {row[0]: row[1] for row in rows} == {name: _parameters(function) for name, function in _public_callables().items()}


@pytest.mark.parametrize("kind", ["Reading", "Asked", "JudgedInstance", "Settled", "WouldFetch", "Read"])
def test_the_guide_gives_each_result_the_fields_the_code_has(kind):
    rows = {row[0]: row[1] for row in _table("| Result | Fields |")}

    assert rows[kind] == ", ".join(field.name for field in dataclasses.fields(getattr(plugin_testing, kind)))
    assert set(rows) == {"Reading", "Asked", "JudgedInstance", "Settled", "WouldFetch", "Read"}


def test_every_public_result_type_is_frozen_so_a_plugin_s_test_cannot_change_what_the_host_said():
    for kind in (
        plugin_testing.Reading,
        plugin_testing.Asked,
        JudgedInstance,
        plugin_testing.Settled,
        WouldFetch,
        plugin_testing.Read,
    ):
        assert kind.__dataclass_params__.frozen, kind


def test_the_guide_states_the_version_rule_in_the_interfaces_own_words():
    section = " ".join(_section().split())

    for sentence in (
        "within a major, a name, a parameter and a field stay and keep their meaning",
        "a minor may add a name, a field or a keyword parameter with a default",
        "a removal or a changed meaning is a new major",
    ):
        assert sentence in section


def test_the_helper_is_not_part_of_the_interface_and_loading_the_interface_does_not_load_it():
    assert "testing" not in interface.__all__
    assert not any(name.startswith("Plugin") and name.endswith("Host") for name in interface.__all__)
    probe = "import sys, arrt.library.sources; print('arrt.library.sources.testing' in sys.modules)"
    answer = subprocess.run(  # noqa: S603 -- this interpreter, running the fixed probe above
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True
    )
    assert answer.stdout.strip() == "False"


def test_the_fixture_plugins_declare_the_interface_minors_the_issue_names():
    sys.path.insert(0, str(FIXTURE))
    try:
        module = importlib.import_module(PACKAGE)
        declared = {name: getattr(module, name).api_minor for name in ("STEADY", "MISBEHAVING", "GONE", "NEWER")}
    finally:
        sys.modules.pop(PACKAGE, None)
        sys.path.remove(str(FIXTURE))
    assert declared == {"STEADY": 4, "MISBEHAVING": 5, "GONE": 6, "NEWER": 7}


def test_two_hosts_in_one_test_each_speak_under_their_own_museums_name(fixture):
    """Loading declares museum names process-wide; each call declares its host's own again, so a later load renames nothing."""
    archive = host(fixture.GONE, name="gone")
    host(fixture.STEADY, name="steady")  # loaded after, declaring "Steady Museum" and not "Gone Archive"

    read = archive.read(GONE_URL)

    assert read.detail.startswith("the Gone Archive plugin read that")
