"""The routes for the image sources: their health and what each has yielded."""

from fastapi import APIRouter, Request

from arrt.http.models import SourcePluginOut, SourcesOut, SourceYieldOut, SourceYieldsOut
from arrt.http.routes.common import API_PREFIX, _services
from arrt.library.sources.plugin import API_VERSION
from arrt.services.health import SourceHealth

router = APIRouter(prefix=API_PREFIX)


@router.get("/sources")
def get_sources(request: Request) -> SourcesOut:
    """Every installed source plugin, where it came from, and what became of it at startup.

    Settings › Sources reads this: the inventory, where Status reads the same
    plugins for how they are doing. One reading, so the two pages cannot
    describe a plugin differently.
    """
    major, minor = API_VERSION
    return SourcesOut(
        interface_version=f"{major}.{minor}",
        sources=[_source_plugin(each) for each in _services(request).health.observe_sources()],
    )


@router.get("/sources/yields")
def get_source_yields(request: Request) -> SourceYieldsOut:
    """What each installed source plugin has given the library: offered, chosen, only here, median size.

    Status's sources table reads it beside `GET /api/health`'s `sources`. Its own
    route rather than a field of the health reading, because the top bar reads
    that on every page and these are counts across the whole library.
    """
    return SourceYieldsOut(
        sources=[
            SourceYieldOut(
                name=each.provider,
                offered=each.offered,
                chosen=each.chosen,
                only_here=each.only_here,
                median_long_edge=each.median_long_edge,
            )
            for each in _services(request).health.observe_yields()
        ]
    )


def _source_plugin(health: SourceHealth) -> SourcePluginOut:
    reading = health.reading
    searches = health.searches
    return SourcePluginOut(
        name=reading.name,
        museum=health.museum,
        state=reading.state.value,
        reason=reading.reason,
        faults=reading.faults,
        last_fault_at=None if reading.last_fault_at is None else reading.last_fault_at.isoformat(),
        last_fault_age_seconds=health.last_fault_age_seconds,
        last_fault=reading.last_fault,
        unasked=reading.unasked,
        last_unasked_at=None if reading.last_unasked_at is None else reading.last_unasked_at.isoformat(),
        last_unasked_age_seconds=health.last_unasked_age_seconds,
        last_unasked=reading.last_unasked,
        answered=reading.answered,
        searched=0 if searches is None else searches.searched,
        searches_answered=0 if searches is None else searches.answered,
        searches_unasked=0 if searches is None else searches.unasked,
        searches_owed=0 if searches is None else searches.owed,
        last_search_answered_at=(
            None if searches is None or searches.last_answered_at is None else searches.last_answered_at.isoformat()
        ),
        searches_with_images=0 if searches is None else searches.with_images,
        searches_median_latency_seconds=None if searches is None else searches.median_latency_seconds,
        description=health.describe(),
        distribution=reading.identity.distribution,
        version=reading.identity.version,
        api_major=reading.identity.api_major,
        provides=[part.value for part in reading.identity.provides],
    )
