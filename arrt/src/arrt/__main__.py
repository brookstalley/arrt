"""Run the curation plane: `uv run python -m arrt`."""

import argparse
import logging
import os
import shutil
import sys
from collections.abc import Callable, Sequence

import uvicorn
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from arrt import art_root, logs
from arrt.app import create_app
from arrt.config import Settings, retired_settings_in
from arrt.library.acquisition.mat import MatEngine
from arrt.library.acquisition.preparation import PreparationSettings
from arrt.library.acquisition.service import AcquisitionSettings
from arrt.library.acquisition.transport import http_stream
from arrt.library.discovery.engine import DiscoveryEngine, unavailable_engine
from arrt.library.discovery.images import offers_images
from arrt.library.discovery.openrouter import KeyStatus, OpenRouterClient
from arrt.library.discovery.phase_one import build_engine
from arrt.library.registry import Registry
from arrt.library.registry.wikidata import INTERACTIVE_TIMEOUT_SECONDS, WikidataRegistry
from arrt.library.services.thumbnails import ThumbnailSettings
from arrt.library.sources import SourceContext
from arrt.library.sources.loading import SourceRoster, environment_of, load_sources
from arrt.persistence.backup import BACKUP_RECEIPT_FILENAME, CatalogueBackup
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.kept import KeptAnswers
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.persistence.sqlite_discovery import SqliteDiscovery
from arrt.programming.display import DisplaySettings
from arrt.services.container import Services

#: What a deployment with no key is told when it tries to discover. Written for
#: the curator or agent who reads it back off a refusal, and it names the one
#: thing that fixes it rather than describing the internals that noticed.
NO_KEY: str = (
    "Discovery cannot start: this deployment has no OPENROUTER_API_KEY set, and phase 1 needs a model "
    "to turn an intent into a list of works. Set it in .env — the spend ceiling is that key's own credit "
    "limit. Every other art_discovery action works on runs that already exist."
)


def _engine(settings: Settings) -> DiscoveryEngine:
    """The real engine when a key is configured, and an honest refusal when not.

    Deliberately not a stand-in. A convincing double reachable from a deployment
    is one somebody eventually wires up, and the result would be invented works
    written into a real catalogue with nothing to distinguish them from found
    ones — the curator's evidence that discovery worked would be the product
    fabricating it.
    """
    if not settings.openrouter_api_key:
        return unavailable_engine(NO_KEY)
    return build_engine(
        settings.openrouter_api_key,
        model=settings.discovery_model,
        max_output_tokens=settings.discovery_max_output_tokens,
        search_results=settings.discovery_search_results,
        search_engine=settings.discovery_search_engine,
    )


def _mat_engine(settings: Settings) -> MatEngine:
    """The mat engine, asking a vision model when there is a key to ask with.

    **Unlike `_engine` above, no key is not a refusal here.** Discovery with no
    key must refuse, because a stand-in would write invented works into a real
    catalogue. A mat has an honest mechanical producer — the work's own dominant
    colour, darkened — and `MatColor.method` records which one chose it, so the
    keyless deployment gets real mats that say what they are rather than works
    that cannot be rendered.
    """
    client = None
    if settings.openrouter_api_key:
        client = OpenRouterClient(
            settings.openrouter_api_key,
            model=settings.mat_model,
            max_output_tokens=settings.mat_max_output_tokens,
        )
    return MatEngine(client, image_max_edge=settings.mat_image_max_edge)


def _key_status(settings: Settings) -> Callable[[], KeyStatus] | None:
    """How the budget asks the provider what is left of the month, or None with no key.

    Its own client rather than an engine's: reading `/key` is free, takes no
    model, and must not wait behind a run's completion on one session.
    """
    if not settings.openrouter_api_key:
        return None
    client = OpenRouterClient(
        settings.openrouter_api_key,
        model=settings.discovery_model,
        max_output_tokens=settings.discovery_max_output_tokens,
    )
    return client.key_status


def _ask_model(settings: Settings) -> BaseChatModel | None:
    """The model Ask's agent runs on, or None when there is no key and Ask answers nothing."""
    if not settings.openrouter_api_key:
        return None
    from threetears.models import create_chat_model

    return create_chat_model(settings.ask_model, api_key=settings.openrouter_api_key, provider="openrouter")


def _ask_tools(settings: Settings) -> list[BaseTool]:
    """Web search through 3tears when a SearXNG instance is configured, and nothing otherwise."""
    if not settings.searxng_url:
        return []
    from threetears.agent.tools.builtin.web_search import create_web_search_tool

    return [create_web_search_tool({"base_url": settings.searxng_url}, "Search the web. Returns titles, addresses and snippets.")]


def _sources(settings: Settings, registry: Registry | None) -> SourceRoster:
    """Every installed source plugin, loaded against this deployment, in its order of preference.

    Nothing here names a plugin: the Art Institute and Commons register as entry
    points like any other (`arrt/pyproject.toml`), so this is the same path a
    plugin from outside this repository takes. Each plugin reads its own settings
    from the environment, because a plugin nobody here has written cannot have a
    field in `Settings`.

    **Called after `Settings.from_env`**, which is what loads `.env` into the
    process environment. A plugin's variable set in `.env` reaches it only
    because of that order.
    """
    return load_sources(
        SourceContext(
            environ=environment_of(os.environ),
            user_agent=settings.acquisition_user_agent,
            preview_max_bytes=settings.preview_max_bytes,
            registry=registry,
        ),
        order=settings.source_order,
        data_root=settings.source_data_path,
    )


def _no_finder(sources: SourceRoster) -> str:
    """Why no finder loaded, from each plugin's own answer, for the startup line.

    A loaded plugin that finds no image (one that only reads, only offers a
    collection, or only finds pages) is named as such, so the line never says
    nothing is installed while something is.
    """
    reasons = [f"{reading.name}: {reading.reason or 'loaded, and finds no image'}" for reading in sources.observe()]
    return f"none ({'; '.join(reasons)})" if reasons else "none (no source plugin is installed)"


def _registry(settings: Settings) -> WikidataRegistry | None:
    """Wikidata, or nothing while this deployment has not named itself to it."""
    if not settings.wikidata_user_agent:
        return None
    # The pages' timeout, not the matcher's: see INTERACTIVE_TIMEOUT_SECONDS.
    return WikidataRegistry(user_agent=settings.wikidata_user_agent, timeout=INTERACTIVE_TIMEOUT_SECONDS)


def main(argv: Sequence[str] = ()) -> None:
    """Resolve configuration, open the catalogue, and serve.

    **Arguments are passed in rather than read off `sys.argv`.** The default is
    "no arguments", so calling `main()` from a test parses nothing instead of
    parsing pytest's own command line — which is what it did for one commit, and
    it turned seven startup tests into `SystemExit: 2`. The process entry point
    below supplies the real ones.
    """
    parser = argparse.ArgumentParser(
        prog="python -m arrt",
        description="Run the curation plane.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help=(
            "Create ART_ROOT as a new, empty art root if it is not one already. "
            "Needed once per deployment; without it a directory that is not an art root is refused, "
            "so a mistyped ART_ROOT reports an error instead of quietly becoming a second collection."
        ),
    )
    arguments = parser.parse_args(argv)

    logs.configure(level=logging.INFO)
    settings = Settings.from_env()
    log = logging.getLogger(__name__)
    log.info("catalogue=%s bind=%s:%s", settings.catalogue_path, settings.host, settings.port)
    # The resolved root and this plane's own panel, on one line, so a
    # misconfiguration is a journal read rather than a mystery. The television's
    # panel — never the e-paper one, which belongs to the display plane.
    box = settings.tv_artwork_box
    log.info(
        'art_root=%s manifests=%s tv_panel=%dx%dpx/%.1f" (%.1f px per inch) rotation=%ds shuffle=%s',
        settings.art_root,
        settings.manifest_pattern,
        settings.tv_panel_width_px,
        settings.tv_panel_height_px,
        settings.tv_panel_diagonal_inches,
        settings.tv_pixels_per_inch,
        settings.rotation_interval_seconds,
        settings.rotation_shuffle,
    )
    # The derived geometry as well as its inputs: where the mat ends depends on
    # this box, and a wrong mat is otherwise only visible on the wall. The
    # quality minimum beside it, because a wrong one is otherwise only visible
    # as scans labelled oddly in the grid.
    log.info(
        'artwork_box=%dx%dpx mat=%.2f" (bottom x%.2f) quality_minimum=%dpx',
        box.width,
        box.height,
        settings.mat_width_inches,
        settings.mat_bottom_weight,
        settings.quality_minimum_px,
    )
    # A setting this server no longer reads is named, once each, rather than
    # left to look like one still in force.
    for retired in retired_settings_in(os.environ):
        log.warning(retired, extra={"event": "config.retired_setting"})
    # What discovery may spend and what it is priced at, on one line, because a
    # bounded estimate a curator authorises against is only as good as the
    # numbers behind it — and those are the ones most likely to be stale.
    discovery = settings.discovery_settings
    # The engine and its per-request price on the same line as the estimate they
    # produce. They are one decision — parallel bills $0.001 and the other
    # back-ends $0.005 — and a deployment that pins the price without the engine
    # puts a five-fold error into the only figure a curator authorises against.
    # Nothing refuses to boot over it: two optional settings disagreeing is not
    # worth failing a household product to start. But it is not silent either,
    # because the test that reads as the guard here deliberately cannot see a
    # deployment's own `.env` — see `test_the_search_price_matches_the_engine_that_is_pinned`.
    log.info(
        "discovery phase1_searches=%d phase2_searches_per_work=%d offered_works_per_run=%s "
        "search_engine=%s search_price=$%s phase1_estimate=$%s",
        discovery.phase1_search_allowance,
        discovery.phase2_searches_per_work,
        # Named rather than left at 0, because this is the setting whose "off" is
        # otherwise invisible: a run that offers nothing because the supplement is
        # disabled looks exactly like one whose collection held nothing.
        "disabled" if discovery.offered_works_per_run <= 0 else discovery.offered_works_per_run,
        settings.discovery_search_engine,
        discovery.search_cost_usd,
        discovery.phase1_estimate_usd,
    )
    # Which model spends the money and whether there is a key to spend it with —
    # the key's *presence*, never its value. "Is the key even set" is the first
    # question a discovery misconfiguration raises, and answering it costs
    # nothing; the repository is public and journals are read over shoulders.
    log.info(
        "discovery model=%s max_output_tokens=%d search_results=%d openrouter_key=%s",
        settings.discovery_model,
        settings.discovery_max_output_tokens,
        settings.discovery_search_results,
        settings.redacted()["openrouter_api_key"],
    )

    # Which museum phase 2 asks, and whether it can be asked at all. Logged for
    # the same reason the key's presence is: "is it even configured" is the first
    # question a run stuck at `resolving_images` raises.
    registry = _registry(settings)
    sources = _sources(settings, registry)
    log.info(
        "phase2 image_sources=%s pictures=%s fetching=%s",
        ",".join(source.provider for source in sources.finders if offers_images(source)) or _no_finder(sources),
        # Where every fetched picture is kept, printed whatever the sources: the
        # store answers review from what it keeps whether or not anything here
        # can fetch, and `fetching` says which.
        settings.pictures_path,
        "on" if sources.finds_images else "off",
    )

    # Whether tiled acquisition can run at all, and where the master images go.
    # Logged for the same reason the key's presence and the image provider are: the
    # binary is the one dependency this plane does not install, it is resolved off
    # PATH at call time, and a deployment missing it fails every tiled fetch at
    # once — a state worth reading at startup rather than discovering per work.
    tile_binary = shutil.which(settings.tile_binary)
    log.info(
        "acquisition originals=%s tile_cache=%s tile_binary=%s min_free=%.1fGiB",
        settings.originals_path,
        settings.tile_cache_path,
        tile_binary or f"MISSING ({settings.tile_binary} is not on PATH; tiled acquisition will refuse)",
        settings.min_free_bytes / (1024**3),
    )

    # Which model chooses mat colours, and where the composed canvases go. Worth
    # its own line for the reason the discovery model's is: a deployment with no
    # key still renders, using the mechanical fallback, and "every mat on this
    # machine says dominant_color_fallback" is a question best answered at
    # startup rather than by reading forty rows.
    log.info(
        "mat model=%s max_output_tokens=%d image_max_edge=%d ready=%s",
        settings.mat_model if settings.openrouter_api_key else "none (no key; every mat comes from the dominant colour)",
        settings.mat_max_output_tokens,
        settings.mat_image_max_edge,
        settings.ready_path,
    )

    # Ask's agent: which model, how many steps a reply may take, and whether it
    # can search the web. Not the SearXNG address itself, which is the operator's.
    log.info(
        "ask model=%s step_limit=%d web_search=%s",
        settings.ask_model if settings.openrouter_api_key else "none (no key; Ask answers nothing)",
        settings.ask_step_limit,
        "on" if settings.searxng_url else "off (SEARXNG_URL is not set)",
    )

    log.info(
        "registry=%s",
        "wikidata" if settings.wikidata_user_agent else "none (WIKIDATA_USER_AGENT unset; works and artists are not matched)",
    )

    # Before anything is created, and before the catalogue is opened. The two
    # steps this replaces were individually reasonable and silent together: a
    # `mkdir(exist_ok=True)` followed by `CREATE TABLE IF NOT EXISTS` turned a
    # typo in ART_ROOT into a fresh empty collection that started cleanly.
    art_root.prepare(settings.art_root, settings.catalogue_path, initialise=arguments.init)
    # One connection behind both halves of the model: acceptance promotes a
    # candidate's image instances into a work's sources, and that has to commit
    # once or not at all.
    catalogue_file = open_catalogue_file(settings.catalogue_path, wall_name=settings.wall_name)
    # After `prepare`, so a mistyped root refuses before anything is written to it.
    kept = KeptAnswers(settings.kept_answers_path)
    try:
        services = Services.bind(
            catalogue=SqliteCatalogue(catalogue_file),
            discovery=SqliteDiscovery(catalogue_file),
            display_settings=DisplaySettings(
                art_root=settings.art_root,
                rotation_interval_seconds=settings.rotation_interval_seconds,
                shuffle=settings.rotation_shuffle,
            ),
            label_units=settings.label_units,
            thumbnails=ThumbnailSettings(art_root=settings.art_root, directory=settings.thumbnails_path),
            quality_profile=settings.quality_profile,
            engine=_engine(settings),
            discovery_settings=settings.discovery_settings,
            key_status=_key_status(settings),
            monthly_budget_usd=settings.monthly_budget_usd,
            sources=sources,
            acquisition=AcquisitionSettings(
                art_root=settings.art_root,
                originals_path=settings.originals_path,
                tile_cache_path=settings.tile_cache_path,
                user_agent=settings.acquisition_user_agent,
                tile_binary=settings.tile_binary,
                tile_max_pixels=settings.tile_max_pixels,
                tile_timeout_seconds=settings.tile_timeout_seconds,
                max_image_bytes=settings.max_image_bytes,
                min_free_bytes=settings.min_free_bytes,
            ),
            # The one place a live transport is wired. Everything below the seam
            # takes it as an argument, so this line is what separates a process
            # that can fetch from a suite that cannot.
            open_stream=http_stream(settings.acquisition_user_agent),
            preparation=PreparationSettings(
                art_root=settings.art_root,
                ready_path=settings.ready_path,
                panel_width=settings.tv_panel_width_px,
                panel_height=settings.tv_panel_height_px,
                # The same object logged above, derived once: it is *computed
                # from* the panel dimensions on the lines above it, so a second
                # derivation here is the only way the canvas and the box could
                # disagree about where the mat ends.
                box=box,
            ),
            mat_engine=_mat_engine(settings),
            registry=registry,
            kept=kept,
        )
        # The catalogue file outlives any single version of this code, so rules
        # added since it was written are brought to it here rather than assumed
        # of it. Before serving, because a surface must not answer from a
        # catalogue still in a state its own rules forbid.
        services.reconcile()
        # `log_config=None` so uvicorn installs nothing of its own. Its default
        # config attaches plain-text handlers to `uvicorn` and `uvicorn.access`
        # with `propagate: False`, which would put the startup banner, every
        # access line and every unhandled ASGI traceback into the journal as
        # multi-line text — beside this plane's JSON. One non-JSON line aborts
        # `journalctl | jq 'select(.run_id == …)'`, which is the whole reason the
        # log shape exists, so the failure would be the documented way of
        # reconstructing a run quietly not working. With no config of its own,
        # uvicorn's loggers propagate to the root handler installed above.
        uvicorn.run(
            create_app(
                services,
                sweep_topics=True,
                acquire_queue=True,
                backup=(
                    None
                    if settings.backup_dir is None
                    else CatalogueBackup(
                        catalogue_path=settings.catalogue_path,
                        directory=settings.backup_dir,
                        receipt_path=settings.art_root / BACKUP_RECEIPT_FILENAME,
                        keep=settings.backup_keep,
                    )
                ),
                backup_interval_seconds=settings.backup_interval_seconds,
                ask_model=_ask_model(settings),
                ask_step_limit=settings.ask_step_limit,
                ask_tools=_ask_tools(settings),
            ),
            host=settings.host,
            port=settings.port,
            log_config=None,
        )
    finally:
        kept.close()
        catalogue_file.close()


if __name__ == "__main__":
    main(sys.argv[1:])
