"""Source plugins: loading them, leaving out the ones that cannot load, and containing faults.

The contract is `source-plugins.md`. The loader is driven with entry points built
here, which load through `EntryPoint.load` exactly as an installed plugin's do; one
test reads this distribution's real entry points, because a typo in
`pyproject.toml` would pass every test that builds its own.
"""

import ast
import importlib.metadata
import logging
import pathlib
from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeRegistry
from plugin_fakes import FakeCollection, FakeFinder

from arrt.http.api import _health
from arrt.library.discovery.browse import CollectionBrowseFailure
from arrt.library.discovery.images import ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.services.display_fit import ArtworkBox
from arrt.library.sources import API_VERSION, Declined, SourceContext, SourceParts, SourcePlugin
from arrt.library.sources.loading import ENTRY_POINT_GROUP, PluginState, load_sources
from arrt.services.health import HealthReading, HealthService

SOURCES = pathlib.Path(__file__).resolve().parents[2] / "src" / "arrt" / "library" / "sources"


def entry(name: str, target: str) -> importlib.metadata.EntryPoint:
    return importlib.metadata.EntryPoint(name=name, value=f"plugin_fakes:{target}", group=ENTRY_POINT_GROUP)


def context(**environ: str) -> SourceContext:
    return SourceContext(environ=environ, user_agent="arrt-tests/0", preview_max_bytes=1_000_000)


def states(roster) -> dict[str, tuple[PluginState, str | None]]:
    return {reading.name: (reading.state, reading.reason) for reading in roster.observe()}


# -- loading ------------------------------------------------------------------


def test_a_plugin_named_by_an_entry_point_loads_with_its_finder_and_collection():
    roster = load_sources(context(), entry_points=[entry("good", "GOOD")])

    assert [finder.provider for finder in roster.finders] == ["good"]
    assert roster.collection is not None and roster.collection.provider == "good"
    assert states(roster) == {"good": (PluginState.LOADED, None)}


def test_a_plugin_written_for_another_major_is_refused_by_name():
    roster = load_sources(context(), entry_points=[entry("future", "FUTURE")])

    state, reason = states(roster)["future"]
    assert state is PluginState.FAILED
    assert "written for source interface 2" in reason
    assert f"provides {API_VERSION[0]}.{API_VERSION[1]}" in reason
    assert roster.finders == ()


def test_a_factory_that_raises_leaves_the_plugin_out_and_the_rest_loaded():
    roster = load_sources(context(), entry_points=[entry("raising", "RAISING"), entry("good", "GOOD")])

    assert states(roster)["raising"] == (
        PluginState.FAILED,
        "its factory raised RuntimeError: the factory could not reach its service",
    )
    assert [finder.provider for finder in roster.finders] == ["good"]


def test_a_plugin_that_cannot_be_imported_is_left_out_and_named():
    broken = importlib.metadata.EntryPoint(name="gone", value="no_such_module:PLUGIN", group=ENTRY_POINT_GROUP)

    roster = load_sources(context(), entry_points=[broken])

    state, reason = states(roster)["gone"]
    assert state is PluginState.FAILED
    assert reason.startswith("it could not be imported: ModuleNotFoundError")


@pytest.mark.parametrize(
    ("target", "said"),
    [
        ("NOT_A_PLUGIN", "its entry point names a object, not a SourcePlugin"),
        ("NOT_PARTS", "its factory answered a str, not SourceParts or Declined"),
        ("MISNAMED", "its finder records images under 'somebody-else'"),
    ],
)
def test_a_plugin_that_breaks_the_interface_is_left_out_and_says_how(target, said):
    roster = load_sources(context(), entry_points=[entry("bad", target)])

    state, reason = states(roster)["bad"]
    assert state is PluginState.FAILED
    assert said in reason


def test_a_collection_recorded_under_another_name_is_refused_too():
    plugin = SourcePlugin(api_major=1, create=lambda _c: SourceParts(collection=FakeCollection("elsewhere")))
    point = importlib.metadata.EntryPoint(name="mine", value="plugin_fakes:GOOD", group=ENTRY_POINT_GROUP)

    roster = load_sources(context(), entry_points=[_Fixed(point, plugin)])

    state, reason = states(roster)["mine"]
    assert state is PluginState.FAILED
    assert "its collection records images under 'elsewhere'" in reason


def test_two_distributions_registering_one_name_load_neither():
    roster = load_sources(context(), entry_points=[entry("good", "GOOD"), entry("good", "OTHER")])

    assert states(roster) == {"good": (PluginState.FAILED, "two installed distributions register this name; neither is loaded")}
    assert roster.finders == ()


def test_a_plugin_this_deployment_has_not_configured_declines_with_its_reason(caplog):
    with caplog.at_level(logging.INFO, logger="arrt.library.sources.loading"):
        roster = load_sources(context(), entry_points=[entry("configured", "CONFIGURED")])

    assert states(roster) == {"configured": (PluginState.DECLINED, "FAKE_SOURCE_KEY is unset")}
    assert "source plugin configured declined: FAKE_SOURCE_KEY is unset" in caplog.text
    assert roster.finders == ()


def test_a_plugin_is_given_the_deployments_user_agent_and_preview_ceiling():
    """What the startup wiring puts in the context, through the real entry point."""
    seen = []
    plugin = SourcePlugin(api_major=1, create=lambda given: seen.append(given) or Declined("only looking"))

    load_sources(
        SourceContext(environ={}, user_agent="arrt (+https://example.org)", preview_max_bytes=4096),
        entry_points=[_Fixed(entry("looking", "GOOD"), plugin)],
    )

    assert (seen[0].user_agent, seen[0].preview_max_bytes) == ("arrt (+https://example.org)", 4096)


def test_a_plugin_reads_its_own_settings_from_the_environment_it_is_given():
    roster = load_sources(context(FAKE_SOURCE_KEY="set"), entry_points=[entry("configured", "CONFIGURED")])

    assert [finder.provider for finder in roster.finders] == ["configured"]


def test_order_names_the_preferred_plugins_and_the_rest_follow_by_name():
    points = [entry("good", "GOOD"), entry("other", "OTHER"), entry("configured", "CONFIGURED")]

    roster = load_sources(context(FAKE_SOURCE_KEY="set"), entry_points=points, order=("other",))

    assert [finder.provider for finder in roster.finders] == ["other", "configured", "good"]
    assert [reading.name for reading in roster.observe()] == ["other", "configured", "good"]


def test_the_collection_is_the_most_preferred_plugins_that_offers_one():
    points = [entry("other", "OTHER"), entry("good", "GOOD")]

    roster = load_sources(context(), entry_points=points, order=("other", "good"))

    # `other` is preferred but offers no collection, so the run supplements from `good`.
    assert roster.collection is not None and roster.collection.provider == "good"


# -- containing faults --------------------------------------------------------


@pytest.mark.plugin_fault_expected
def test_a_finder_that_faults_is_counted_as_not_asked_and_the_others_answers_stand(caplog):
    moment = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    roster = load_sources(context(), entry_points=[entry("faulty", "FAULTY"), entry("good", "GOOD")], now=lambda: moment)
    pool = ImageSourcePool(roster.finders)

    with caplog.at_level(logging.ERROR, logger="arrt.library.sources.loading"):
        answer = pool.find_images(ImageQuery(title="Nighthawks", artist="Edward Hopper"))

    assert answer.unreachable == ("faulty",)
    assert [image.provider for image in answer.images] == ["good"]
    faulty = next(reading for reading in roster.observe() if reading.name == "faulty")
    assert (faulty.faults, faulty.last_fault_at) == (1, moment)
    assert faulty.last_fault == "KeyError: 'a field the page no longer has'"
    assert [getattr(record, "event", None) for record in caplog.records] == ["source.plugin_fault"]


def test_cannot_answer_passes_through_as_itself_and_is_not_a_fault():
    roster = load_sources(context(), entry_points=[entry("unanswerable", "UNANSWERABLE")])

    with pytest.raises(ImageQueryUnanswerable):
        roster.finders[0].find_images(ImageQuery(title="Nighthawks"))
    assert roster.observe()[0].faults == 0


@pytest.mark.plugin_fault_expected
def test_every_call_a_plugin_answers_is_contained():
    """Preview, tiles and browse as well as search: every way in, not the one remembered."""
    fault = ValueError("unexpected")
    plugin = SourcePlugin(
        api_major=1,
        create=lambda _c: SourceParts(
            finder=FakeFinder("wobbly", raises=fault), collection=FakeCollection("wobbly", raises=fault)
        ),
    )
    roster = load_sources(context(), entry_points=[_Fixed(entry("wobbly", "GOOD"), plugin)])
    finder, collection = roster.finders[0], roster.collection

    assert finder.fetch_preview("https://wobbly.example/p.jpg") is None
    with pytest.raises(ImageSearchFailure, match="wobbly plugin faulted"):
        finder.tile_url("https://wobbly.example/object/1")
    with pytest.raises(CollectionBrowseFailure, match="wobbly plugin faulted"):
        collection.browse([], per_query=3)
    assert roster.observe()[0].faults == 3


# -- the health panel ---------------------------------------------------------


@pytest.mark.plugin_fault_expected
def test_the_health_reading_states_each_plugin_with_the_age_of_its_last_fault():
    moment = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    roster = load_sources(
        context(),
        entry_points=[entry("faulty", "FAULTY"), entry("raising", "RAISING"), entry("configured", "CONFIGURED")],
        now=lambda: moment,
    )
    with pytest.raises(ImageSearchFailure):
        roster.finders[0].find_images(ImageQuery(title="Nighthawks"))

    reading = _health_of(roster, now=moment + timedelta(seconds=42))
    out = {source.name: source for source in _health(reading).sources}

    assert out["faulty"].state == "loaded"
    assert out["faulty"].faults == 1
    assert out["faulty"].last_fault_age_seconds == 42
    assert "1 fault since startup, the last 42 seconds ago" in out["faulty"].description
    assert out["raising"].state == "failed"
    assert "was not loaded: its factory raised RuntimeError" in out["raising"].description
    assert out["configured"].state == "declined"
    assert out["configured"].description == "configured is installed and not configured here: FAKE_SOURCE_KEY is unset."


def test_a_loaded_plugin_with_no_faults_says_so_and_carries_no_fault_age():
    roster = load_sources(context(), entry_points=[entry("good", "GOOD")])

    (good,) = _health(_health_of(roster)).sources

    assert good.description == "good is loaded, with no faults since startup."
    assert (good.last_fault_at, good.last_fault_age_seconds, good.last_fault) == (None, None, None)


# -- the built-in plugins ------------------------------------------------------


def test_this_distribution_registers_the_built_in_plugins_as_entry_points():
    """Read from the installed metadata: the injected tests above cannot see a typo in pyproject."""
    installed = {point.name: point for point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)}

    assert {"commons", "artic"} <= set(installed)
    for name in ("commons", "artic"):
        assert isinstance(installed[name].load(), SourcePlugin), name


def test_the_built_in_plugins_load_through_the_real_entry_points():
    roster = load_sources(
        SourceContext(
            environ={"ARTIC_USER_AGENT": "arrt-tests/0", "WIKIDATA_USER_AGENT": "arrt-tests/0"},
            user_agent="arrt-tests/0",
            preview_max_bytes=1_000_000,
            registry=FakeRegistry(),
        )
    )

    assert [finder.provider for finder in roster.finders][:2] == ["commons", "artic"]
    assert roster.collection is not None and roster.collection.provider == "artic"


@pytest.mark.parametrize(
    ("name", "environ", "said"),
    [
        ("artic", {}, "ARTIC_USER_AGENT is unset"),
        ("commons", {"WIKIDATA_USER_AGENT": "arrt-tests/0"}, "no registry is configured"),
        ("commons", {}, "WIKIDATA_USER_AGENT is unset"),
    ],
)
def test_a_built_in_plugin_declines_when_its_setting_is_missing(name, environ, said):
    """Commons declines without a registry even when its user agent is set: it finds by item."""
    plugin = next(p for p in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP) if p.name == name).load()

    answer = plugin.create(SourceContext(environ=environ, user_agent="arrt-tests/0", preview_max_bytes=1_000_000, registry=None))

    assert isinstance(answer, Declined)
    assert said in answer.reason


def test_the_built_in_plugins_import_nothing_from_arrt_but_the_interface():
    """They are the examples a plugin author copies, so they may not reach past it."""
    offences = []
    for module in ("artic.py", "commons.py"):
        tree = ast.parse((SOURCES / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            offences += [f"{module} imports {n}" for n in names if n.split(".")[0] == "arrt" and n != "arrt.library.sources"]

    assert offences == []


# -- helpers ------------------------------------------------------------------


class _Fixed:
    """An entry point whose `load` returns a given object: for plugins built inside a test."""

    def __init__(self, point: importlib.metadata.EntryPoint, plugin: object) -> None:
        self.name = point.name
        self._plugin = plugin

    def load(self) -> object:
        return self._plugin


class _NoWalls:
    """The one display question the health service asks, answered with no walls."""

    def survey_wall_status(self) -> list:
        return []


def _health_of(roster, *, now: datetime | None = None) -> HealthReading:
    """The reading the real health service takes, so the fault's age is its arithmetic, not this file's."""
    moment = now or datetime.now(UTC)
    service = HealthService(
        _NoWalls(),
        backup_receipt_path=pathlib.Path("/nonexistent/backup-receipt.json"),
        box=ArtworkBox(width=3000, height=2000, pixels_per_inch=88.0, floor_inches=12.0),
        sources=roster,
        now=lambda: moment,
    )
    return service.observe()
