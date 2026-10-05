"""The services a surface is handed, and how they relate to each other.

Operation logic is split by concern rather than gathered into one class: the
catalogue owns works already accepted, discovery owns everything before
acceptance, and display owns what reaches the wall — themes, the standing
directive, and the manifest built from them. A surface takes this container
rather than any single service, so adding a concern changes the wiring here and
nothing in `create_app` or in an MCP binding — which is what keeps a surface from
quietly binding to one service and becoming the reason a second one is awkward to
add.

How the services relate is decided here, once. Both discovery and display hold
the catalogue, and neither is held by it: acceptance is a promotion *into* the
catalogue, and a theme is a grouping *of* catalogue works. Both directions are
facts about the product rather than conveniences of one call site, which is why
they are settled in one place instead of per constructor.
"""

import logging
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

# Module scope, and the three `_default_*` helpers below used to import this at
# function scope instead, explained as breaking a cycle: "config reads this
# package to compose its settings objects". It does not. `arrt.config`
# imports `manifest.builder`, `manifest.heartbeat`, `services.display_fit` and
# `services.runner`, and none of those reaches this module — `services/__init__`
# is a docstring. The deferral hid container→config from anything reading the
# import graph while teaching a pattern on a premise that was never true. If a
# real cycle ever appears, the fix is to move the constants, not to hide the edge.
from arrt.config import (
    DEFAULT_ACQUISITION_USER_AGENT,
    DEFAULT_MAT_IMAGE_MAX_EDGE,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MIN_FREE_BYTES,
    DEFAULT_TILE_BINARY,
    DEFAULT_TILE_MAX_PIXELS,
    DEFAULT_TILE_TIMEOUT_SECONDS,
    DEFAULT_TV_PANEL_HEIGHT_PX,
    DEFAULT_TV_PANEL_WIDTH_PX,
    ORIGINALS_DIRNAME,
    READY_DIRNAME,
    TILE_CACHE_DIRNAME,
)
from arrt.library.acquisition.direct import StreamOpener
from arrt.library.acquisition.mat import MatEngine
from arrt.library.acquisition.preparation import PreparationService, PreparationSettings
from arrt.library.acquisition.queue import AcquisitionQueue
from arrt.library.acquisition.service import AcquisitionService, AcquisitionSettings
from arrt.library.acquisition.transport import no_transport
from arrt.library.acquisition.urls import Resolver, check_fetchable
from arrt.library.discovery.conversation import NO_CONVERSATION_KEY, ConversationEngine, UnavailableConversation
from arrt.library.discovery.engine import DiscoveryEngine
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.events import WorkChange
from arrt.library.facade import LibraryFacade
from arrt.library.registry import Registry
from arrt.library.services.artists import ArtistService
from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.conversation import ConversationService
from arrt.library.services.discovery import DiscoveryService
from arrt.library.services.display_fit import ArtworkBox
from arrt.library.services.get import GetService
from arrt.library.services.identity import IdentityService
from arrt.library.services.previews import PreviewCache, PreviewSettings
from arrt.library.services.registry_search import RegistrySearchService
from arrt.library.services.registry_works import RegistryWorkService
from arrt.library.services.review import ReviewService
from arrt.library.services.runner import DiscoveryRunner, DiscoverySettings
from arrt.library.services.sightings import SightingService
from arrt.library.services.survey import SurveyService
from arrt.library.services.sweep import PreviewSweep
from arrt.library.services.taste import TasteService
from arrt.library.services.thumbnails import ThumbnailService, ThumbnailSettings
from arrt.library.services.topic_sweep import TopicSweep
from arrt.library.services.topics import TopicService
from arrt.library.services.wikidata_match import WikidataMatchService
from arrt.library.sources.loading import SourceRoster
from arrt.persistence.backup import BACKUP_RECEIPT_FILENAME
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.kept import KeptAnswers
from arrt.programming.access import PlayerAccess
from arrt.programming.clients import ClientService
from arrt.programming.display import DisplayService, DisplaySettings
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import ServiceError
from arrt.services.health import HealthService

log = logging.getLogger(__name__)


class OneCatalogueFile(CatalogueStore, ProgrammingStore, Protocol):
    """The one open file, which answers the Library's protocol and Programming's.

    Named here, where both sides are composed, because nowhere else may know
    that one object serves both. When Programming's tables move to a file of
    their own, `bind` takes two stores and this type goes.
    """


@dataclass(frozen=True, slots=True)
class Services:
    """Every service the curation plane offers, assembled over one open file."""

    catalogue: CatalogueService
    #: The Library as Programming reaches it. Held here so that a test or a
    #: binding asking "can this work go on a wall" gets the answer the manifest
    #: build gets, from the same object.
    library: LibraryFacade
    #: Which Player may read which wall, by its client's token.
    access: PlayerAccess
    #: The installed Players the server knows, and which walls each shows.
    clients: ClientService
    discovery: DiscoveryService
    display: DisplayService
    thumbnails: ThumbnailService
    #: Works composed the way a surface showing them to a human needs them. It is
    #: its own concern rather than a method on the catalogue because it spans
    #: three of them, and because both surfaces need the identical composition —
    #: which is the same reason the service layer exists at all.
    survey: SurveyService
    #: The same composition on the other side of acceptance: proposed works and
    #: the instances found for them, each with the size it would render at and a
    #: picture small enough to travel. Separate from `survey` because they read
    #: different entities entirely — one the catalogue, one the pipeline — and a
    #: single service spanning both would hold the catalogue and discovery stores
    #: at once for no shared logic.
    review: ReviewService
    #: Everything the health panel states, gathered in one call. Its own concern
    #: rather than a composite the handler assembles, because the panel is the
    #: product's only alerting surface and "which signals does it make" is a
    #: product rule — one that belongs where it can be tested without HTTP, and
    #: where the next signal is added in one place rather than two.
    health: HealthService
    #: Running a discovery run, as distinct from recording one. It sits above
    #: `discovery` rather than inside it because the record layer is deliberately
    #: synchronous and knows nothing of processes, and everything about starting
    #: work behind a handle does.
    runner: DiscoveryRunner
    #: Reclaiming the previews of works the curator has decided. Built
    #: unconditionally, unlike the phase-2 pair it cleans up after: a deployment
    #: that never cached a preview has nothing to sweep, and the pass costs one
    #: walk of a household's rows to find that out. An optional here would mean
    #: a deployment could disable phase 2, keep the files it already wrote, and
    #: lose the only thing that reclaims them.
    sweep: PreviewSweep
    #: Acquiring the master image a work was accepted for. Held beside the
    #: catalogue rather than inside it because it is the one service that reaches
    #: outside the machine to do its job — a subprocess and an HTTP transport —
    #: and the record layer is deliberately free of both.
    acquisition: AcquisitionService
    #: Turning a held original into a mat and a television canvas. Its own service
    #: rather than the tail of acquisition: a work is prepared repeatedly over its
    #: life — whenever the panel changes, the mat is re-chosen, or a rendition
    #: goes stale — while it is acquired once. Folding the two together would make
    #: every re-render look like a re-fetch to whatever reads the journal.
    preparation: PreparationService
    #: Fetching, then preparing, every accepted work that holds no image, in the
    #: background and one at a time. Built whatever the deployment, like `sweep`;
    #: it runs only when the application is asked to start it.
    acquisition_queue: AcquisitionQueue
    #: Intent-forming, upstream of every run. Beside `runner` rather than inside
    #: it because a conversation is not a run and must never become one: it
    #: acquires nothing, has no status to poll and nothing to approve. What it has
    #: is one edge onto the runner, and that edge is the whole relationship.
    conversation: ConversationService
    #: The curator's standing judgments. Its own concern rather than a corner of
    #: the conversation service, because taste outlives every thread that
    #: contributed to it: an affinity is accumulated across conversations, is
    #: correctable from a screen that has no conversation in front of it, and is
    #: what discovery consults. Folding it into intent-forming would tie the
    #: product's memory of its operator to the lifetime of a transcript, which is
    #: precisely what deleting one must not do.
    taste: TasteService
    #: Which registry item each held work and artist is (ruling 7). The
    #: curator's corrections work without a registry; matching needs one, and
    #: says so when it is absent rather than matching nothing quietly.
    identity: IdentityService
    #: The artists the library holds, and what the registry knows about each,
    #: for the Artist page. Over the same registry as `identity`.
    artists: ArtistService
    #: One registry work, for the page of a work the library may not hold, and
    #: which held works are it. Over the same registry as `artists`.
    registry_works: RegistryWorkService
    #: The registry's half of one-world search: artists and works found for a
    #: few typed words, each marked where the library holds it.
    registry_search: RegistrySearchService
    #: A Get: works chosen by their Wikidata items, turned into one run over the
    #: image sources. Over the same registry and runner as the services above.
    get: GetService
    #: Topics: the library's, from the facet rows, and a topic's registry
    #: sections. Over the same registry as `artists`.
    topics: TopicService
    #: Keeping the library's works' topics as facets. Built whatever the
    #: registry, like `sweep`; without one it does nothing, and the application
    #: says so once when it would have started it.
    topic_sweep: TopicSweep
    #: Wikidata's items for a wanted work, for the curator to pick from. Over the
    #: same registry as `identity`; says it is off without one.
    wikidata_match: WikidataMatchService
    #: The pages found for works that no installed plugin reads, by host. Over
    #: the same routing acquisition uses, so a page a plugin claims is not one.
    sightings: SightingService

    @classmethod
    def bind(
        cls,
        *,
        catalogue: OneCatalogueFile,
        discovery: DiscoveryStore,
        display_settings: DisplaySettings,
        thumbnails: ThumbnailSettings,
        artwork_box: ArtworkBox,
        engine: DiscoveryEngine,
        discovery_settings: DiscoverySettings,
        previews: PreviewSettings | None = None,
        acquisition: AcquisitionSettings | None = None,
        open_stream: StreamOpener | None = None,
        #: How a hostname becomes addresses for the fetch policy. Defaults to the
        #: system resolver, which is what a deployment wants and what a test suite
        #: must not have — a suite whose job is to be green cannot depend on DNS.
        #: Exposed here rather than left to whoever knows the attribute name: a
        #: caller reaching past this to write `acquisition._resolve` gets no error
        #: when the attribute is renamed, it just silently resolves for real again.
        resolve: Resolver | None = None,
        preparation: PreparationSettings | None = None,
        mat_engine: MatEngine | None = None,
        #: Defaults to an engine that refuses and says why, exactly as phase 1's
        #: does — and for the same reason. A stand-in that answered would put
        #: invented replies in a transcript, indistinguishable from real ones, so
        #: the curator's evidence that the product works would be the product
        #: fabricating it.
        conversation_engine: ConversationEngine | None = None,
        #: Wikidata, or None while `WIKIDATA_USER_AGENT` is unset. Never a default
        #: client, for the reason `sources` has none: a test suite must not
        #: be able to reach a foreign API through a wiring default.
        registry: Registry | None = None,
        #: Where the registry pages keep answers across restarts. Defaults to
        #: keeping them for the life of the process, which is a real deployment
        #: and not a stub: it is what every registry page did before the file.
        kept: KeptAnswers | None = None,
        #: Every installed source plugin: the finders phase 2 asks, the collection
        #: a run supplements from, the readers acquisition routes a source's URL
        #: to, and what the health panel states. **The only source input**, so the
        #: four cannot disagree: a process assembled with finders and no roster
        #: would search while the panel said no plugin is installed. `None` is a
        #: process with no plugins, which is what most tests are.
        sources: SourceRoster | None = None,
    ) -> Services:
        """Assemble the services over an already-open file.

        The engines are injected rather than constructed here for the reason
        every foreign dependency is: a container that built its own model client
        or museum client would make "run the service layer without touching a
        foreign API" impossible to arrange, and that is the arrangement most of
        this product's tests need.

        A roster with no finder and no `previews` go together. Without either the
        plane runs phase 1 and stops, which is a coherent deployment — and the
        one every test that has no business reaching a museum uses.
        """
        catalogue_service = CatalogueService(catalogue, art_root=thumbnails.art_root)
        kept = kept or KeptAnswers.in_memory()
        # The artwork box reaches discovery for one reason: automatic selection
        # must withhold an instance that would render below the floor, and the
        # floor is a size on the wall rather than a pixel count — so the rule
        # cannot be evaluated without the panel geometry that converts one to the
        # other.
        sources = SourceRoster.empty() if sources is None else sources
        pool = ImageSourcePool(sources.finders) if sources.finds_images else None
        discovery_service = DiscoveryService(
            discovery, catalogue_service, artwork_box, precedence=None if pool is None else pool.precedence
        )
        # Discovery before the facade, because the facade answers where a Get
        # sent its accepted works, and only the run knows.
        library = LibraryFacade(catalogue_service, discovery_service)
        # The same open file passed as Programming's store: one object serves
        # both protocols until Programming's tables get a file of their own.
        display_service = DisplayService(catalogue, library, display_settings)
        # Programming hears the Library's changes here, where both are composed,
        # rather than subscribing itself: the subscription is wiring, and a
        # service that wired itself could not be built for a test without it.
        library.subscribe(display_service.on_work_changed)
        thumbnail_service = ThumbnailService(catalogue_service, thumbnails)
        topic_sweep = TopicSweep(catalogue, catalogue_service, registry)
        # The Library's own announcement, heard by the Library's own sweep: an
        # accepted or restored work is asked about now rather than at the
        # interval. Identity changes reach it through `identity` below.
        catalogue_service.subscribe(lambda event: topic_sweep.nudge() if event.change is WorkChange.ACCEPTED else None)
        if (pool is None) != (previews is None):
            # Refused here rather than defaulted, because either half alone is a
            # misconfiguration that would otherwise disable phase 2 silently —
            # and a deployment that meant to enable it would see runs stop at
            # `resolving_images` with nothing saying why.
            raise ServiceError(
                "Phase 2 needs both an image source and a preview directory, or neither. A deployment "
                "selects both by configuring a source — the preview directory is derived from ART_ROOT, so "
                "passing one of these without the other is a wiring mistake rather than a configuration one."
            )
        acquisition_service = AcquisitionService(
            catalogue_service,
            acquisition or _default_acquisition(thumbnails.art_root),
            # Defaults to a transport that refuses rather than to a live one.
            # A plane assembled without wiring one has a wiring mistake, and
            # a real client here would let that mistake reach a museum from a
            # test suite instead of failing where it was made.
            open_stream=open_stream or no_transport,
            # A source's URL reaches the reader of the plugin that claims it. A
            # plugin that claims it and is not loaded is a deployment fault named
            # by that plugin; a URL nobody claims is fetched as recorded.
            route=sources.route,
            **({} if resolve is None else {"resolve": resolve}),
        )
        preparation_service = PreparationService(
            catalogue_service,
            # Defaults to an engine with no client, which is not a stub: it is
            # exactly the keyless deployment, and it produces recorded
            # dominant-colour mats. A real client here would let a wiring
            # mistake spend money from a test suite rather than failing where
            # it was made — the same reason `open_stream` defaults to refusing.
            mat_engine or _default_mat_engine(),
            preparation or _default_preparation(thumbnails.art_root, artwork_box),
            # The ledger is discovery's today, reached through its one method.
            spend=discovery_service,
        )
        acquisition_queue = AcquisitionQueue(catalogue, catalogue_service, acquisition_service, preparation_service)
        # Acceptance, and a restore, wake the queue, as they wake the topic
        # sweep: the work is fetched now rather than at the next pass. A lost
        # announcement delays the fetch until the next start, which catches up.
        catalogue_service.subscribe(lambda event: acquisition_queue.nudge() if event.change is WorkChange.ACCEPTED else None)
        sighting_service = SightingService(discovery, catalogue, route=sources.route)
        runner_service = DiscoveryRunner(
            discovery_service,
            engine,
            discovery_settings,
            images=None if pool is None else PhaseTwoEngine(pool, box=artwork_box, registry=registry),
            previews=None if pool is None or previews is None else PreviewCache(previews, pool.fetch_preview),
            # Independent of the phase-2 pair: a deployment may resolve images
            # without supplementing, and a run with no collection simply offers
            # nothing.
            collection=sources.collection,
            sightings=sighting_service,
            # The pages a run's search cited reach a plugin only past the fetch
            # policy, resolving names the way acquisition does: a suite's stated
            # answers, or the system's.
            **({} if resolve is None else {"check_page": partial(check_fetchable, resolve=resolve)}),
        )
        return cls(
            catalogue=catalogue_service,
            library=library,
            access=PlayerAccess(catalogue),
            clients=ClientService(catalogue, display_settings),
            discovery=discovery_service,
            display=display_service,
            thumbnails=thumbnail_service,
            survey=SurveyService(catalogue_service, thumbnail_service, artwork_box, acquisition=acquisition_queue),
            # `art_root` is read off the thumbnail settings rather than taken as
            # an argument of its own. It is the same deployment value — every
            # catalogue path is relative to it — and it is already required and
            # validated there. A third copy would be a third chance for the
            # copies to disagree, and nothing would notice which was right.
            review=ReviewService(discovery_service, box=artwork_box, art_root=thumbnails.art_root),
            # The receipt is located the same way, and for the same reason. It is
            # not a `DisplaySettings` field beside the art root the heartbeats are
            # named from: that settings object carries what the *walls'*
            # operations need, and the backup is this plane's own business rather
            # than the display plane's.
            health=HealthService(
                display_service,
                backup_receipt_path=thumbnails.art_root / BACKUP_RECEIPT_FILENAME,
                box=artwork_box,
                sources=sources,
            ),
            runner=runner_service,
            # `art_root` off the thumbnail settings for the same reason `review`
            # takes it from there: it is one deployment value, already validated,
            # and a second copy is a second chance for the two to disagree.
            sweep=PreviewSweep(discovery_service, art_root=thumbnails.art_root),
            acquisition=acquisition_service,
            preparation=preparation_service,
            acquisition_queue=acquisition_queue,
            conversation=ConversationService(
                discovery,
                conversation_engine or _default_conversation_engine(),
                # The two foreign services this one needs, each through the one
                # method it needs. `record_spend` lives on the discovery service
                # and `start` on the runner; taking either whole would deepen the
                # coupling the accounting split is filed to remove.
                discovery_service,
                runner_service,
                collection=sources.collection,
            ),
            # Over the same store the conversations live in, because a judgment's
            # citation and the turn it cites have to be detachable in one
            # transaction — the delete's whole correctness is that it commits or
            # does not.
            taste=TasteService(discovery),
            identity=IdentityService(catalogue, registry, on_changed=topic_sweep.nudge),
            artists=ArtistService(catalogue, registry, kept=kept, wanted=discovery_service),
            registry_works=RegistryWorkService(catalogue, registry, kept=kept, wanted=discovery_service),
            registry_search=RegistrySearchService(catalogue, registry, kept=kept, wanted=discovery_service),
            get=GetService(store=catalogue, discovery=discovery_service, runner=runner_service, registry=registry),
            topics=TopicService(catalogue, registry, kept=kept, wanted=discovery_service),
            topic_sweep=topic_sweep,
            wikidata_match=WikidataMatchService(discovery_service, registry),
            sightings=sighting_service,
        )

    def reconcile(self) -> None:
        """Repair whatever the file on disk may predate. Run once, as the plane starts.

        A catalogue file outlives any single version of this code, so a rule
        added after a file was written has to be brought to that file rather than
        assumed of it. Each service owns the repairs for its own records; this is
        the one call a process start has to remember, so a service gaining a
        repair does not mean an entry point gaining a line.

        **The display service reconciles too, and for a different reason**: not
        a rule the file predates, but an announcement it may have missed. The
        Library tells Programming when a work changes, after the change commits,
        and a crash between the two loses the announcement. So every start takes
        any work the Library now refuses off every published manifest and pin,
        and offers any accepted work never offered its theme (the default, or
        the one its Get named), so a lost announcement delays either until the
        next start rather than leaving it undone.
        """
        self.discovery.reconcile()
        # Canvases drawn with another mat, panel or drawing rule are queued to be
        # recomposed. Nothing is drawn here; the queue does it once serving.
        self.acquisition_queue.owe_recomposition(self.preparation.layout)
        # Mats darker than the floor, all of them older than it, are chosen
        # again the same way: a queue row each, the queue's `prepare` choosing.
        self.acquisition_queue.owe_mats_over_the_floor()
        # Before the walls, and outside their `OSError` guard: it writes no
        # manifest, only the catalogue, and a failure here is one to see.
        self.display.catch_up_offers()
        try:
            self.display.reconcile()
        except OSError:
            # A manifest that cannot be rewritten (a full disk, a directory gone
            # read-only) must not keep the curation interface down: the wall
            # goes on showing its last manifest, which is where it would be with
            # this plane stopped, and the interface is where a curator finds out
            # why. Nothing is half-applied, because the reconciliation runs in
            # one transaction that the failure rolled back, and the next start
            # tries again.
            log.exception("Could not reconcile the walls' manifests against the Library at startup; serving anyway.")


def _default_acquisition(art_root: Path) -> AcquisitionSettings:
    """Acquisition settings for a caller that expressed no preference.

    Every value here is a library default rather than a deployment value, which
    is right for a test and wrong for the Pi — so the entry point passes its own,
    resolved from the environment like everything else it configures.
    """
    return AcquisitionSettings(
        art_root=art_root,
        originals_path=art_root / ORIGINALS_DIRNAME,
        tile_cache_path=art_root / TILE_CACHE_DIRNAME,
        user_agent=DEFAULT_ACQUISITION_USER_AGENT,
        tile_binary=DEFAULT_TILE_BINARY,
        tile_max_pixels=DEFAULT_TILE_MAX_PIXELS,
        tile_timeout_seconds=DEFAULT_TILE_TIMEOUT_SECONDS,
        max_image_bytes=DEFAULT_MAX_IMAGE_BYTES,
        min_free_bytes=DEFAULT_MIN_FREE_BYTES,
    )


def _default_mat_engine() -> MatEngine:
    """A mat engine for a caller that wired no model client.

    **No client is a real deployment, not a stub.** A plane with no
    `OPENROUTER_API_KEY` serves its whole catalogue and pays for nothing; works
    acquired there get dominant-colour mats recorded as such. So the default is
    that deployment rather than something that would fail if used.
    """
    return MatEngine(None, image_max_edge=DEFAULT_MAT_IMAGE_MAX_EDGE)


def _default_conversation_engine() -> ConversationEngine:
    """The conversation engine a caller that wired no model client gets.

    **Unlike the mat engine's keyless default, this one refuses.** A mat has an
    honest mechanical producer — the work's own dominant colour — and a
    conversation does not: there is no non-model way to answer a curator asking
    what would suit a calm wall, and anything written here that tried would be
    the product inventing a reply and putting it in a transcript beside real
    ones. So the keyless deployment gets a thread that says what is missing.
    """
    return UnavailableConversation(NO_CONVERSATION_KEY)


def _default_preparation(art_root: Path, artwork_box: ArtworkBox) -> PreparationSettings:
    """Preparation settings for a caller that expressed no preference.

    The panel comes from the reference defaults, as every other value in this
    file's defaults does. **A caller passing its own `artwork_box` and letting
    the panel default would get a mismatched pair**, which is why the entry point
    passes both from one resolved `Settings` — the box is *derived from* the
    panel there, so the two cannot disagree.
    """
    return PreparationSettings(
        art_root=art_root,
        ready_path=art_root / READY_DIRNAME,
        panel_width=DEFAULT_TV_PANEL_WIDTH_PX,
        panel_height=DEFAULT_TV_PANEL_HEIGHT_PX,
        box=artwork_box,
    )
