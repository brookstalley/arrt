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
from arrt.library.services.display_fit import DisplayFit, FitAssessment
from arrt.library.sources.loading import ENTRY_POINT_GROUP, PluginReading, PluginState, SourceRoster
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
    fit = FitAssessment(fit=DisplayFit.NATIVE, rendered_width=3000, rendered_height=2250, rendered_long_edge_inches=40.0)
    names_the_museum(_rationale(found, confidence=CONFIDENT, fit=fit), plugin)


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
