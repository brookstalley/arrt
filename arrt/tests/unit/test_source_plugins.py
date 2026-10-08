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

import plugin_fakes
import pytest
from fakes import FakeRegistry
from plugin_fakes import Answers, StubCollection, StubFinder, StubReader, claims_example

from arrt.http.api import _health
from arrt.library.discovery.browse import CollectionBrowseFailure
from arrt.library.discovery.images import ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.services.pictures import PictureStore
from arrt.library.sources import API_VERSION, Declined, SourceContext, SourceParts, SourcePlugin
from arrt.library.sources.loading import (
    ENTRY_POINT_GROUP,
    FAULT_LOGGER,
    PluginIdentity,
    PluginPart,
    PluginState,
    SourceRoster,
    load_sources,
)
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
    assert roster.collection is not None
    assert roster.collection.provider == "good"
    assert states(roster) == {"good": (PluginState.LOADED, None)}


@pytest.mark.parametrize(
    ("name", "own"),
    [("alpha", "alpha"), ("beta.2", "beta.2"), ("../catalogue", None), ("a/b", None), ("..", None), (".hidden", None)],
)
def test_each_plugin_is_handed_a_directory_of_its_own_under_the_data_root_and_no_other(tmp_path, caplog, name, own):
    """1.2: `data_dir` is the plugin's name under the root, and a name that is not one plain segment gets none, said."""
    plugin_fakes.DIRECTORIES_HANDED.clear()

    load_sources(context(), entry_points=[entry(name, "DIRECTORY")], data_root=tmp_path / "sources")

    assert [None if own is None else tmp_path / "sources" / own] == plugin_fakes.DIRECTORIES_HANDED
    withheld = [r.plugin for r in caplog.records if getattr(r, "event", None) == "source.no_directory"]
    assert withheld == ([] if own is not None else [name])
    assert not (tmp_path / "sources").exists(), "the loader creates nothing; a plugin creates its directory when it writes"


def test_two_plugins_are_handed_two_directories_and_no_root_hands_none(tmp_path):
    plugin_fakes.DIRECTORIES_HANDED.clear()

    load_sources(context(), entry_points=[entry("one", "DIRECTORY"), entry("two", "DIRECTORY")], data_root=tmp_path)
    load_sources(context(), entry_points=[entry("three", "DIRECTORY")])

    assert [tmp_path / "one", tmp_path / "two", None] == plugin_fakes.DIRECTORIES_HANDED


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
    plugin = SourcePlugin(api_major=1, create=lambda _c: SourceParts(collection=StubCollection("elsewhere")))
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
    assert roster.collection is not None
    assert roster.collection.provider == "good"


@pytest.mark.parametrize(
    ("target", "said"),
    [
        ("RAISING_PROVIDER", "its parts raised while being checked: RuntimeError: the provider property broke"),
        ("NOT_A_FINDER", "its finder is a str, which is not a Finder"),
        ("UNCLEAR_ABOUT_IMAGES", "its finder's offers_images is not a bool"),
        ("READER_WITHOUT_CLAIMS", "it provides a reader and declares no claims"),
        ("CLAIMS_WITHOUT_READER", "it declares claims and provides no reader"),
    ],
)
def test_parts_that_break_the_interface_leave_the_plugin_out_and_arrt_running(target, said):
    """Each would otherwise reach startup or a run as an exception nobody contains."""
    name = "claimer" if target == "CLAIMS_WITHOUT_READER" else "x"

    roster = load_sources(context(), entry_points=[entry(name, target), entry("good", "GOOD")], order=())

    (failed,) = [reading for reading in roster.observe() if reading.state is PluginState.FAILED]
    assert failed.name == name
    assert said in failed.reason
    assert [finder.provider for finder in roster.finders] == ["good"]


def test_a_plugins_error_text_loses_its_query_strings_before_anyone_reads_it(caplog):
    """An HTTP client's error names the URL it asked, and a key often travels in the query."""
    with caplog.at_level(logging.INFO, logger=FAULT_LOGGER):
        roster = load_sources(context(), entry_points=[entry("leaky", "LEAKY")], order=())

    (reading,) = roster.observe()
    assert "sk-live-123" not in reading.reason
    assert "https://api.example.net/v1/search?…" in reading.reason
    assert "sk-live-123" not in caplog.text


def test_a_name_in_the_order_that_no_plugin_has_is_said_out_loud(caplog):
    """A misspelt name would otherwise reorder the sources in silence."""
    with caplog.at_level(logging.WARNING, logger=FAULT_LOGGER):
        load_sources(context(), entry_points=[entry("good", "GOOD")], order=("comons", "good"))

    assert "SOURCE_ORDER names comons, which no installed plugin is" in caplog.text


def test_each_plugin_is_named_in_the_journal_before_its_factory_runs(caplog):
    """So a factory that hangs leaves its name behind rather than a startup that stops."""
    seen = []
    plugin = SourcePlugin(api_major=1, create=lambda _c: seen.append(list(caplog.messages)) or Declined("looking"))

    with caplog.at_level(logging.INFO, logger=FAULT_LOGGER):
        load_sources(context(), entry_points=[_Fixed(entry("slow", "GOOD"), plugin)], order=())

    assert "loading source plugin slow" in seen[0]


# -- containing faults --------------------------------------------------------


@pytest.mark.plugin_fault_expected
def test_a_finder_that_faults_is_counted_as_not_asked_and_the_others_answers_stand(caplog):
    moment = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    roster = load_sources(
        context(), entry_points=[entry("faulty", "FAULTY"), entry("good", "GOOD")], order=(), now=lambda: moment
    )
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
    """Preview, reading and browse as well as search: every way in, not the one remembered."""
    fault = ValueError("unexpected")
    plugin = SourcePlugin(
        api_major=1,
        create=lambda _c: SourceParts(
            finder=StubFinder("wobbly", raises=fault),
            reader=StubReader(raises=fault),
            collection=StubCollection("wobbly", raises=fault),
        ),
        claims=claims_example,
    )
    roster = load_sources(context(), entry_points=[_Fixed(entry("wobbly", "GOOD"), plugin)], order=())
    finder, collection = roster.finders[0], roster.collection
    reader = roster.route("https://example.org/works/1").reader

    assert finder.fetch_preview("https://wobbly.example/p.jpg") is None
    with pytest.raises(ImageSearchFailure, match="wobbly plugin faulted"):
        reader.read("https://example.org/works/1")
    with pytest.raises(CollectionBrowseFailure, match="wobbly plugin faulted"):
        collection.browse([], per_query=3)
    assert roster.observe()[0].faults == 3


@pytest.mark.plugin_fault_expected
@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (None, "find_images answered a NoneType, not a list of FoundImage"),
        ("a string", "find_images answered a str, not a list of FoundImage"),
        ([object()], "find_images answered a object among its images"),
    ],
)
def test_a_finder_answer_of_the_wrong_shape_is_a_contained_fault(answer, said):
    plugin = SourcePlugin(api_major=1, create=lambda _c: SourceParts(finder=Answers("shapeless", answer)))
    roster = load_sources(context(), entry_points=[_Fixed(entry("shapeless", "GOOD"), plugin)], order=())

    with pytest.raises(ImageSearchFailure, match="shapeless plugin faulted"):
        roster.finders[0].find_images(ImageQuery(title="Nighthawks"))

    assert said in roster.observe()[0].last_fault


@pytest.mark.plugin_fault_expected
def test_an_image_recorded_under_another_plugins_name_is_a_contained_fault():
    """It would be stored, and fetched, as the other plugin's."""
    other = StubFinder("artic").find_images(ImageQuery(title="Nighthawks"))
    plugin = SourcePlugin(api_major=1, create=lambda _c: SourceParts(finder=Answers("impostor", other)))
    roster = load_sources(context(), entry_points=[_Fixed(entry("impostor", "GOOD"), plugin)], order=())

    answer = ImageSourcePool((*roster.finders, StubFinder("good"))).find_images(ImageQuery(title="Nighthawks"))

    assert answer.unreachable == ("impostor",)
    assert "recorded under 'artic'" in roster.observe()[0].last_fault


@pytest.mark.plugin_fault_expected
def test_a_claims_check_that_raises_claims_nothing_and_is_counted():
    def broken(_url: str) -> bool:
        raise ValueError("bad pattern")

    roster = SourceRoster.of(readers={"broken": (broken, StubReader()), "good": (claims_example, StubReader())})

    route = roster.route("https://example.org/works/1")

    assert route.plugin == "good"
    assert {r.name: r.faults for r in roster.observe()} == {"broken": 1, "good": 0}


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
    assert (
        out["configured"].description == "The configured plugin is installed and not configured here: FAKE_SOURCE_KEY is unset."
    )


def test_a_loaded_plugin_with_no_faults_says_so_and_carries_no_fault_age():
    roster = load_sources(context(), entry_points=[entry("good", "GOOD")])

    (good,) = _health(_health_of(roster)).sources

    assert good.description == "The good plugin is loaded, with no faults since startup."
    assert (good.last_fault_at, good.last_fault_age_seconds, good.last_fault) == (None, None, None)


# -- the built-in plugins ------------------------------------------------------


def test_this_distribution_registers_the_built_in_plugins_as_entry_points():
    """Read from the installed metadata: the injected tests above cannot see a typo in pyproject."""
    installed = {point.name: point for point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)}

    assert {"commons", "artic", "wikidata", "met", "smk", "navigart", "nga", "yale", "getty", "rijksmuseum"} <= set(installed)
    for name in ("commons", "artic", "wikidata", "met", "smk", "navigart", "nga", "yale", "getty", "rijksmuseum"):
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

    # Named by the default order first, then the rest by name.
    assert [finder.provider for finder in roster.finders][:3] == ["commons", "artic", "getty"]
    assert roster.collection is not None
    assert roster.collection.provider == "artic"


def test_each_installed_plugin_says_which_distribution_and_version_it_came_from(tmp_path):
    """Read from the installed metadata, for loaded, declined and page-only plugins alike."""
    version = importlib.metadata.version("arrt")
    roster = load_sources(
        SourceContext(
            environ={"WIKIDATA_USER_AGENT": "arrt-tests/0"},
            user_agent="arrt-tests/0",
            preview_max_bytes=1_000_000,
            registry=FakeRegistry(),
        ),
        data_root=tmp_path,
    )
    identity = {reading.name: reading.identity for reading in roster.observe()}

    for name in ("met", "smk", "navigart", "nga", "yale", "getty", "rijksmuseum"):
        assert identity[name] == PluginIdentity(
            distribution="arrt", version=version, api_major=1, provides=(PluginPart.FINDS_IMAGES, PluginPart.READS)
        ), name
    assert identity["wikidata"].provides == (PluginPart.FINDS_PAGES,)
    # Declined: where it came from is known, and it provides nothing here.
    assert identity["artic"] == PluginIdentity(distribution="arrt", version=version, api_major=1, provides=())


def test_a_plugin_registered_by_hand_or_unimportable_says_what_could_be_read():
    broken = importlib.metadata.EntryPoint(name="gone", value="no_such_module:PLUGIN", group=ENTRY_POINT_GROUP)

    roster = load_sources(
        context(), entry_points=[entry("good", "GOOD"), broken, entry("twice", "GOOD"), entry("twice", "OTHER")]
    )
    identity = {reading.name: reading.identity for reading in roster.observe()}

    assert identity["good"].distribution is None
    assert identity["good"].api_major == API_VERSION[0]
    assert identity["good"].provides  # loaded, so its parts are read
    assert identity["gone"] == PluginIdentity()
    assert identity["twice"] == PluginIdentity(api_major=None)


def test_a_name_two_packages_register_names_neither_as_its_origin():
    """Both entries carry a real package, so the rule, not a missing package, is what empties it."""
    met = next(point for point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP) if point.name == "met")
    assert met.dist is not None

    roster = load_sources(context(), entry_points=[met, met])

    (reading,) = roster.observe()
    assert reading.state is PluginState.FAILED
    assert reading.identity == PluginIdentity()


def test_a_package_whose_metadata_cannot_be_read_costs_its_origin_and_not_startup():
    class _Unreadable:
        @property
        def metadata(self):
            raise RuntimeError("corrupt METADATA")

        version = "0"

    point = _Fixed(entry("good", "GOOD"), _plugin_from("GOOD"))
    point.dist = _Unreadable()

    roster = load_sources(context(), entry_points=[point])

    (reading,) = roster.observe()
    assert reading.state is PluginState.LOADED
    assert (reading.identity.distribution, reading.identity.version) == (None, None)


@pytest.mark.parametrize(
    ("name", "environ", "said"),
    [
        ("artic", {}, "ARTIC_USER_AGENT is unset"),
        ("commons", {"WIKIDATA_USER_AGENT": "arrt-tests/0"}, "no registry is configured"),
        ("commons", {}, "WIKIDATA_USER_AGENT is unset"),
        ("wikidata", {"WIKIDATA_USER_AGENT": "arrt-tests/0"}, "no registry is configured"),
    ],
)
def test_a_built_in_plugin_declines_when_its_setting_is_missing(name, environ, said):
    """Commons declines without a registry even when its user agent is set: it finds by item."""
    plugin = next(p for p in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP) if p.name == name).load()

    answer = plugin.create(SourceContext(environ=environ, user_agent="arrt-tests/0", preview_max_bytes=1_000_000, registry=None))

    assert isinstance(answer, Declined)
    assert said in answer.reason


def _built_in_modules() -> list[str]:
    """The file of every plugin this distribution registers, read from its installed entry points.

    Derived rather than listed, so a built-in added to `pyproject.toml` is held to
    the rule below without anyone remembering to name it here.
    """
    modules = [
        point.value.split(":")[0]
        for point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        if point.dist is not None and point.dist.name == "arrt"
    ]
    return sorted(f"{module.rsplit('.', 1)[1]}.py" for module in modules if module.startswith("arrt.library.sources."))


def test_the_built_in_plugin_modules_are_read_from_the_entry_points():
    """An empty or short list would let the guard below pass over nothing."""
    assert _built_in_modules() == [
        "artic.py",
        "commons.py",
        "getty.py",
        "met.py",
        "navigart.py",
        "nga.py",
        "rijksmuseum.py",
        "smk.py",
        "wikidata.py",
        "yale.py",
    ]


def test_the_built_in_plugins_import_nothing_from_arrt_but_the_interface():
    """They are the examples a plugin author copies, so they may not reach past it."""
    offences = []
    for module in _built_in_modules():
        tree = ast.parse((SOURCES / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                # `from .loading import …` reaches past the interface as surely as
                # the absolute spelling does, and reads nothing like it.
                offences.append(f"{module} imports {'.' * node.level}{node.module or ''} relatively")
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            offences += [f"{module} imports {n}" for n in names if n.split(".")[0] == "arrt" and n != "arrt.library.sources"]

    assert offences == []


# -- helpers ------------------------------------------------------------------


def _plugin_from(target: str) -> object:
    return entry("x", target).load()


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
        sources=roster,
        yields=dict,
        pictures=PictureStore(pathlib.Path("/nonexistent/art/pictures"), art_root=pathlib.Path("/nonexistent/art")),
        now=lambda: moment,
    )
    return service.observe()


# -- a plugin's words, scrubbed wherever they leave the containment -----------

SECRET = "sk-live-123"
LEAKING_URL = f"https://api.example.net/v1/search?key={SECRET}&q=x"


class TestAPluginsWordsLoseTheirQueryStringsOnEveryWayOut:
    """An HTTP client's message names the URL it asked, key and all, and the built-ins pass such messages on."""

    def test_through_the_pools_journal_when_a_finder_could_not_be_asked(self, caplog):
        finder = StubFinder("leaky", raises=ImageSearchFailure(f"Could not search: 401 for url {LEAKING_URL}"))
        roster = SourceRoster.of(finders=[finder, StubFinder("good")])

        with caplog.at_level(logging.WARNING):
            answer = ImageSourcePool(roster.finders).find_images(ImageQuery(title="Nighthawks"))

        assert answer.unreachable == ("leaky",)
        assert "api.example.net/v1/search?…" in caplog.text
        assert SECRET not in caplog.text

    def test_through_a_cannot_answer_which_keeps_its_kind(self):
        finder = StubFinder("leaky", raises=ImageQueryUnanswerable(f"only by item, see {LEAKING_URL}"))
        roster = SourceRoster.of(finders=[finder])

        with pytest.raises(ImageQueryUnanswerable) as raised:
            roster.finders[0].find_images(ImageQuery(title="Nighthawks"))

        assert SECRET not in str(raised.value)

    def test_through_a_browse_failure(self):
        collection = StubCollection("leaky", raises=CollectionBrowseFailure(f"browse failed at {LEAKING_URL}"))
        roster = SourceRoster.of(collection=collection)

        with pytest.raises(CollectionBrowseFailure) as raised:
            roster.collection.browse([], per_query=3)

        assert SECRET not in str(raised.value)

    def test_through_a_readers_failure(self):
        roster = SourceRoster.of(
            readers={"leaky": (claims_example, StubReader(raises=ImageSearchFailure(f"401 for url {LEAKING_URL}")))}
        )

        with pytest.raises(ImageSearchFailure) as raised:
            roster.route("https://example.org/w/1").reader.read("https://example.org/w/1")

        assert SECRET not in str(raised.value)
        assert raised.value.__cause__ is None
        assert raised.value.__suppress_context__

    @pytest.mark.plugin_fault_expected
    def test_through_a_contained_fault_its_log_line_and_the_panel(self, caplog):
        finder = StubFinder("leaky", raises=KeyError(f"no field in {LEAKING_URL}"))
        roster = SourceRoster.of(finders=[finder])

        with caplog.at_level(logging.ERROR, logger=FAULT_LOGGER), pytest.raises(ImageSearchFailure):
            roster.finders[0].find_images(ImageQuery(title="Nighthawks"))

        assert SECRET not in roster.observe()[0].last_fault
        assert SECRET not in caplog.text

    def test_through_a_decline_reason_on_the_health_reading(self):
        plugin = SourcePlugin(api_major=1, create=lambda _c: Declined(f"the key at {LEAKING_URL} was refused"))
        roster = load_sources(context(), entry_points=[_Fixed(entry("leaky", "GOOD"), plugin)], order=())

        (out,) = _health(_health_of(roster)).sources

        assert SECRET not in out.reason
        assert SECRET not in out.description

    def test_a_message_with_nothing_to_scrub_is_the_plugins_own_exception(self):
        failure = ImageSearchFailure("the collection is down")
        roster = SourceRoster.of(finders=[StubFinder("plain", raises=failure)])

        with pytest.raises(ImageSearchFailure) as raised:
            roster.finders[0].find_images(ImageQuery(title="Nighthawks"))

        assert raised.value is failure


def test_claimants_follow_the_order_the_loader_was_given():
    """Two plugins claiming one URL: the one first in `SOURCE_ORDER` reads it, through the real loader."""
    first = SourcePlugin(api_major=1, create=lambda _c: SourceParts(reader=StubReader()), claims=claims_example)
    second = SourcePlugin(api_major=1, create=lambda _c: SourceParts(reader=StubReader()), claims=claims_example)
    points = [_Fixed(entry("alpha", "GOOD"), first), _Fixed(entry("beta", "GOOD"), second)]

    assert load_sources(context(), entry_points=points, order=("beta", "alpha")).route("https://example.org/1").plugin == "beta"
    assert load_sources(context(), entry_points=points, order=("alpha", "beta")).route("https://example.org/1").plugin == "alpha"
