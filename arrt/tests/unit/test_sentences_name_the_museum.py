"""Every sentence the server composes about a source names the museum, never the plugin id.

A plugin records what it finds under its id (`artic`, `smk`), and the client
maps ids to names before it shows them (`core/providers.js`). Sentences composed
on the server arrive already written, so the client's map never reaches them:
"smk holds this as…" on the Work page, "artic is installed…" on Status. Each
sentence here is run for every installed source plugin, read from the real entry
points, and fails on the id as a word in it.

The id is matched case-sensitively and as a whole word, which is how it appears
when it leaks: "ARTIC_USER_AGENT" is a setting's name, and "Wikimedia Commons"
is a museum's.
"""

import importlib.metadata
import re
from datetime import UTC, datetime

import pytest
from fakes import FakeReader
from plugin_fakes import StubReader

from arrt.library.discovery.images import FoundImage, ImageQuery, ImageSearchFailure
from arrt.library.discovery.phase_two import CONFIDENT, _rationale
from arrt.library.discovery.pool import ImageSourcePool, NoSourceCanAnswer
from arrt.library.services.quality import Fit
from arrt.library.sources.loading import (
    ENTRY_POINT_GROUP,
    NotAskedThisPass,
    PluginReading,
    PluginState,
    SourceRoster,
    one_pass,
)
from arrt.library.sources.names import built_in_museums, museum_name
from arrt.library.sources.reading import FetchLocator
from arrt.persistence.records import AcquisitionMethod, SourceClass
from arrt.services.health import SourceHealth

INSTALLED = sorted({point.name for point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)})


def test_enough_plugins_are_installed_for_this_file_to_mean_anything():
    assert len(INSTALLED) >= 10, INSTALLED


def test_every_installed_built_in_declares_the_name_a_curator_knows_it_by():
    """A built-in without a `MUSEUM` would be named by its id in every sentence below."""
    assert set(INSTALLED) <= set(built_in_museums()), set(INSTALLED) - set(built_in_museums())


def names_the_museum(sentence: str, plugin: str) -> None:
    assert not re.search(rf"(?<![\w-]){re.escape(plugin)}(?![\w-])", sentence), f"names the plugin id {plugin!r}: {sentence}"
    assert museum_name(plugin) in sentence, f"does not name {museum_name(plugin)!r}: {sentence}"


# -- Status ---------------------------------------------------------------------


def _reading(plugin: str, state: PluginState, *, reason=None, faults=0, last_fault=None) -> PluginReading:
    return PluginReading(
        name=plugin,
        state=state,
        reason=reason,
        faults=faults,
        last_fault_at=None if not faults else datetime(2026, 10, 8, tzinfo=UTC),
        last_fault=last_fault,
    )


@pytest.mark.parametrize("plugin", INSTALLED)
@pytest.mark.parametrize(
    ("state", "fields"),
    [
        (PluginState.DECLINED, {"reason": "A_SETTING is unset"}),
        (PluginState.FAILED, {"reason": "it could not be imported"}),
        (PluginState.LOADED, {}),
        (PluginState.LOADED, {"faults": 2, "last_fault": "KeyError: 'x'"}),
    ],
    ids=["declined", "failed", "loaded", "faulted"],
)
def test_status_describes_a_plugin_by_its_museum(plugin, state, fields):
    health = SourceHealth(reading=_reading(plugin, state, **fields), last_fault_age_seconds=12 if fields.get("faults") else None)
    names_the_museum(health.describe(), plugin)


@pytest.mark.parametrize("plugin", INSTALLED)
def test_a_plugin_that_declined_names_its_museum_where_its_urls_are_refused(plugin):
    roster = SourceRoster.of(unavailable={plugin: (lambda url: True, "A_SETTING is unset")})
    names_the_museum(roster.route("https://example.org/works/7").unavailable, plugin)


@pytest.mark.parametrize("plugin", INSTALLED)
def test_a_plugin_that_could_not_be_imported_names_its_museum_where_its_rows_are_refused(plugin):
    roster = SourceRoster.of(unknowable={plugin: "it could not be imported"})
    names_the_museum(roster.route("https://example.org/works/7", provider=plugin).unavailable, plugin)


@pytest.mark.parametrize("plugin", INSTALLED)
@pytest.mark.plugin_fault_expected
def test_a_plugin_that_faulted_names_its_museum(plugin):
    roster = SourceRoster.of(readers={plugin: (lambda url: True, StubReader(raises=KeyError("img")))})
    with pytest.raises(ImageSearchFailure) as fault:
        roster.route("https://example.org/works/7").reader.read("https://example.org/works/7")
    names_the_museum(str(fault.value), plugin)


# -- the Work page's look, and a review card's reason ---------------------------


@pytest.mark.parametrize("plugin", INSTALLED)
def test_a_reason_for_a_scan_names_the_museum_that_holds_it(plugin):
    found = FoundImage(
        url="https://example.org/works/7.jpg",
        provider=plugin,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        title="Nighthawks",
        artist="Edward Hopper",
        estimated_width=4000,
        estimated_height=3000,
    )
    fit = Fit.MEETS_MINIMUM
    pool = ImageSourcePool([_Unreachable(plugin)])
    names_the_museum(_rationale(found, pool.museum(plugin), confidence=CONFIDENT, fit=fit), plugin)


# -- when no source can answer ----------------------------------------------------


class _Unreachable:
    offers_images = True

    def __init__(self, provider):
        self.provider = provider

    def find_images(self, query):
        raise ImageSearchFailure("down")


@pytest.mark.parametrize("plugin", INSTALLED)
def test_a_work_no_source_could_be_asked_about_names_the_museums(plugin):
    with pytest.raises(ImageSearchFailure) as failure:
        ImageSourcePool([_Unreachable(plugin)]).find_images(ImageQuery(title="Nighthawks"))
    names_the_museum(str(failure.value), plugin)


# -- acquisition ------------------------------------------------------------------


@pytest.mark.parametrize("plugin", INSTALLED)
@pytest.mark.parametrize(
    "reader",
    [FakeReader(unreachable=True), FakeReader(answer=FetchLocator.none("no image of it is published"))],
    ids=["could-not-read", "found-none"],
)
def test_a_failed_read_names_the_museum_against_the_source(plugin, reader, service, tmp_path):
    from arrt.library.acquisition.service import AcquisitionService, AcquisitionSettings
    from arrt.persistence.records import RightsStatus

    settings = AcquisitionSettings(
        art_root=tmp_path,
        originals_path=tmp_path / "raw",
        tile_cache_path=tmp_path / "tile-cache",
        user_agent="arrt (test)",
        tile_binary="/nonexistent/dezoomify-rs",
        tile_max_pixels=8192,
        tile_timeout_seconds=30,
        max_image_bytes=10_000_000,
        min_free_bytes=1,
    )
    roster = SourceRoster.of(readers={plugin: (lambda url: True, reader)})
    work = service.add_artwork(title="Nighthawks")
    service.add_source(
        artwork_id=work.id,
        url="https://example.org/works/7",
        provider=plugin,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    acquisition = AcquisitionService(
        service, settings, open_stream=None, route=roster.route, resolve=lambda _host: ["93.184.216.34"]
    )

    names_the_museum(acquisition.acquire(work.id).detail, plugin)


def test_the_estimate_s_basis_names_no_phase_of_the_engine(runner):
    """`art_discovery(action='estimate')` hands its basis to an agent to say aloud; "phase 1" is internal."""
    basis = runner.estimate().basis
    assert "phase" not in basis.lower(), basis


def test_a_work_no_source_can_look_up_names_the_museums():
    class _Declining:
        offers_images = True
        provider = "smk"

        def find_images(self, query):
            from arrt.library.discovery.images import ImageQueryUnanswerable

            raise ImageQueryUnanswerable("needs a Wikidata item")

    with pytest.raises(NoSourceCanAnswer) as failure:
        ImageSourcePool([_Declining()]).find_images(ImageQuery(title="Nighthawks"))
    names_the_museum(str(failure.value), "smk")


# -- a plugin that declares its own name, and the process knows no declaration ----------------
#
# `load_sources` hands every sentence the declared names of the latest load through `names.py`,
# which is process state: a second load replaces them, and a roster assembled without a load
# (`SourceRoster.of`) never declared any. Each sentence below is therefore built from the name
# the plugin's own roster holds, with `declare_museums` never called (the autouse fixture in
# `conftest.py` clears it), and names the plugin by it. "Quill Gallery" is declared under the id
# `quill`, which no built-in uses: a built-in's own `MUSEUM` is named first (`museum_name`).

DECLARED = {"quill": "Quill Gallery"}


class _Quill:
    """A finder under the id `quill`, which answers as it was told to."""

    offers_images = True
    provider = "quill"

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises

    def find_images(self, query):
        if self._raises is not None:
            raise self._raises
        return []


def names_the_declared_museum(sentence: str) -> None:
    assert "Quill Gallery" in sentence, f"does not name the museum the plugin declares: {sentence}"
    assert not re.search(r"(?<![\w-])quill(?![\w-])", sentence), f"names the plugin id: {sentence}"


def _quill_pool(*, raises: Exception | None) -> ImageSourcePool:
    roster = SourceRoster.of(finders=[_Quill(raises=raises)], museums=DECLARED)
    return ImageSourcePool(roster.finders)


def test_a_work_no_source_could_be_asked_about_names_the_museum_the_plugin_declares():
    with pytest.raises(ImageSearchFailure) as failure:
        _quill_pool(raises=ImageSearchFailure("down")).find_images(ImageQuery(title="Nighthawks"))
    names_the_declared_museum(str(failure.value))


def test_a_work_no_source_can_look_up_names_the_museum_the_plugin_declares():
    from arrt.library.discovery.images import ImageQueryUnanswerable

    with pytest.raises(NoSourceCanAnswer) as failure:
        _quill_pool(raises=ImageQueryUnanswerable("needs a Wikidata item")).find_images(ImageQuery(title="Nighthawks"))
    names_the_declared_museum(str(failure.value))


def test_a_source_the_run_stopped_waiting_for_is_named_by_the_museum_it_declares():
    source = SourceRoster.of(finders=[_Quill()], museums=DECLARED).finders[0]
    answer = ImageSourcePool([source], window_seconds=1.0, deadline_seconds=1.0)._not_heard(source, owed=True)
    assert answer.failure is not None
    names_the_declared_museum(answer.failure)


@pytest.mark.plugin_fault_expected
def test_a_plugin_that_faulted_is_named_by_the_museum_it_declares():
    source = SourceRoster.of(finders=[_Quill(raises=KeyError("img"))], museums=DECLARED).finders[0]
    with pytest.raises(ImageSearchFailure) as fault:
        source.find_images(ImageQuery(title="Nighthawks"))
    names_the_declared_museum(str(fault.value))


def test_a_plugin_held_back_for_a_pass_is_named_by_the_museum_it_declares():
    source = SourceRoster.of(finders=[_Quill(raises=ImageSearchFailure("down"))], museums=DECLARED).finders[0]
    with one_pass(after=1):
        with pytest.raises(ImageSearchFailure):
            source.find_images(ImageQuery(title="Nighthawks"))
        with pytest.raises(NotAskedThisPass) as held:
            source.find_images(ImageQuery(title="Nighthawks"))
    names_the_declared_museum(str(held.value))


def test_a_source_that_declined_names_the_museum_it_declares_where_its_urls_are_refused():
    roster = SourceRoster.of(unavailable={"quill": (lambda url: True, "A_SETTING is unset")}, museums=DECLARED)
    names_the_declared_museum(roster.route("https://example.org/works/7").unavailable)


def test_the_sources_that_leave_a_work_in_doubt_are_named_by_the_museums_they_declare():
    from arrt.library.discovery.phase_two import PhaseTwoEngine
    from arrt.library.services.quality import QualityProfile

    engine = PhaseTwoEngine(_quill_pool(raises=ImageSearchFailure("down")), profile=QualityProfile(minimum_long_edge_px=1000))
    with pytest.raises(ImageSearchFailure) as failure:
        engine.resolve(ImageQuery(title="Nighthawks"))
    names_the_declared_museum(str(failure.value))


def test_a_reason_for_a_scan_names_the_museum_the_plugin_declares():
    found = FoundImage(
        url="https://example.org/works/7.jpg",
        provider="quill",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        title="Nighthawks",
        artist="Edward Hopper",
        estimated_width=4000,
        estimated_height=3000,
    )
    pool = _quill_pool(raises=None)
    names_the_declared_museum(_rationale(found, pool.museum("quill"), confidence=CONFIDENT, fit=Fit.MEETS_MINIMUM))


@pytest.mark.parametrize(
    "reader",
    [FakeReader(unreachable=True), FakeReader(answer=FetchLocator.none("no image of it is published"))],
    ids=["could-not-read", "found-none"],
)
def test_a_failed_read_names_the_museum_the_plugin_declares(reader, service, tmp_path):
    from arrt.library.acquisition.service import AcquisitionService, AcquisitionSettings
    from arrt.persistence.records import RightsStatus

    settings = AcquisitionSettings(
        art_root=tmp_path,
        originals_path=tmp_path / "raw",
        tile_cache_path=tmp_path / "tile-cache",
        user_agent="arrt (test)",
        tile_binary="/nonexistent/dezoomify-rs",
        tile_max_pixels=8192,
        tile_timeout_seconds=30,
        max_image_bytes=10_000_000,
        min_free_bytes=1,
    )
    roster = SourceRoster.of(readers={"quill": (lambda url: True, reader)}, museums=DECLARED)
    work = service.add_artwork(title="Nighthawks")
    service.add_source(
        artwork_id=work.id,
        url="https://example.org/works/7",
        provider="quill",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    acquisition = AcquisitionService(
        service, settings, open_stream=None, route=roster.route, resolve=lambda _host: ["93.184.216.34"]
    )

    names_the_declared_museum(acquisition.acquire(work.id).detail)


def test_two_loads_in_one_process_name_each_plugin_by_its_own_roster():
    """The second load's names replace the process-wide ones; a roster's sentences keep the names it was built with."""
    from arrt.library.sources import names

    first = SourceRoster.of(finders=[_Quill(raises=ImageSearchFailure("down"))], museums=DECLARED)
    names.declare_museums({"quill": "Somebody Else's Quill"})
    with pytest.raises(ImageSearchFailure) as failure:
        ImageSourcePool(first.finders).find_images(ImageQuery(title="Nighthawks"))
    names_the_declared_museum(str(failure.value))
