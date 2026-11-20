"""Testing a source plugin against the host's own code, offline.

**For the people who write source plugins**, in their own test suites: a plugin's
test can say what Arrt would make of an answer without reaching into Arrt's
internals. This module is the one place that reaches past the interface for
them (`docs/source-plugins.md` § A plugin tested as the host runs it). It is not
part of the interface a plugin imports at run time: **a plugin never imports it**,
only its tests do, and `arrt.library.sources` does not import it.

**It runs the real host, never a copy of it.** `host` loads the plugin with
`load_sources`, so the version checks, the deadlines a plugin declared, the
containment of its faults and the scrubbing of its words are the loader's own.
`PluginHost.ask` asks the plugin's finder through `ImageSourcePool.ask`, the way
a run and a look do. `PluginHost.resolve` runs `PhaseTwoEngine.resolve`, the
verdicts phase two reaches on what the finder said. `PluginHost.read` runs
`AcquisitionService.acquire` for a stored source the plugin claims, routed by the
roster's `route`, so the outcome is the one acquisition would record and the
retry rule is the queue's. Nothing here classifies an answer: where a word below
says what the host did, the host's code said it.

**What it does not do.** It fetches nothing and reaches no network: a reader's
answer ends at what the host *would* fetch (`WouldFetch`), after the host's own
address check run against a resolver that answers every name with a public
address (so a locator on a private address is refused here as in a server). A
plugin's own requests are its own, and a test supplies the transport it makes
them over (`docs/source-plugins.md` § Testing). Previews and collections are not
covered.

**What is public, and its version.** The names in `__all__`, and each one's
parameters and fields, as `docs/source-plugins.md` lists them, held to this file
by a test. They follow the interface's rule (`API_VERSION`): within a major,
names, parameters and fields stay and keep their meaning; a minor may add a
name, a field or a keyword parameter with a default, and a plugin's test that
passes on one Arrt keeps passing on a later one of the same major unless the
host's *behaviour* changed in a way the minor's own notes list, which is the point
of running the host. A removal or a changed meaning is a new major. The enums
re-exported here are the host's vocabularies and grow the same way: a test that
compares an outcome to a name keeps working; one that lists every member does
not, and should not.

**A host leaves what the loader leaves.** Loading declares the plugin's museum
name process-wide (`names.declare_museums`), as a server's load does; each call
here declares this host's own again first, so two hosts in one test each speak
under their own name.
"""

import importlib.metadata
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NoReturn, cast

from arrt.library.acquisition.dezoomify import TileResult
from arrt.library.acquisition.queue import RETRY_RULES, RetryRule
from arrt.library.acquisition.service import AcquisitionService, AcquisitionSettings
from arrt.library.acquisition.service import SourcePluginUnavailable as _SourcePluginUnavailable
from arrt.library.discovery.images import (
    DEFAULT_PREVIEW_MAX_BYTES,
    FoundImage,
    FoundPage,
    ImageQuery,
    ImageSearchFailure,
)
from arrt.library.discovery.phase_two import PhaseTwoEngine, WikidataLink
from arrt.library.discovery.pool import AskOutcome, ImageSourcePool
from arrt.library.registry import Registry
from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.quality import QualityProfile
from arrt.library.sources.loading import (
    ENTRY_POINT_GROUP,
    PluginReading,
    PluginState,
    SourceRoster,
    WaitFor,
    load_sources,
)
from arrt.library.sources.names import declare_museums
from arrt.library.sources.plugin import SourceContext, SourcePlugin
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import AcquisitionMethod, FetchOutcome, FetchStatus, RightsStatus, Source, SourceClass

__all__ = [
    "AskOutcome",
    "Asked",
    "FetchOutcome",
    "JudgedInstance",
    "NotAvailable",
    "PluginHost",
    "Read",
    "Reading",
    "RetryRule",
    "Settled",
    "UnresolvedReason",
    "WouldFetch",
    "host",
]

#: The quality minimum `resolve` judges against unless a test names one: the
#: deployment default (`DEFAULT_QUALITY_MINIMUM_PX`), restated as the one number
#: a plugin's test should not have to know. A test of what a plugin does at a
#: given size passes its own.
DEFAULT_MINIMUM_LONG_EDGE_PX: Final[int] = 1000

#: What every name resolves to in `read`'s address check unless a test gives its
#: own resolver: an address of the open internet, so only a locator that is
#: itself refused (a literal private address, a `.local` name, another scheme)
#: is refused here.
_PUBLIC_ADDRESS: Final[str] = "93.184.216.34"


class NotAvailable(LookupError):
    """What the host does not have to ask: the plugin did not load, or provides no such part."""


@dataclass(frozen=True, slots=True)
class Reading:
    """What the host has observed of the plugin since `host` loaded it: the health panel's own counts."""

    #: `"loaded"`, `"declined"` or `"failed"` (`PluginState`).
    state: str
    #: Why the plugin declined or failed to load; `None` when it loaded.
    reason: str | None
    #: Calls that ended outside the interface, contained as faults.
    faults: int
    #: Calls that were could-not-be-asked, a call past its deadline included.
    unasked: int
    #: Calls that ended in any other answer of the interface's, `LinkGone` included.
    answered: int
    #: The most recent fault, or could-not-be-asked, as the host states it (scrubbed); `None` when there is none.
    last_fault: str | None
    last_unasked: str | None


@dataclass(frozen=True, slots=True)
class Asked:
    """How the host sorted one finder's answer to one question: `ImageSourcePool.ask`'s own `SourceAnswer`."""

    #: `answered` (images, pages, or nothing), `declined` (`ImageQueryUnanswerable`),
    #: `unreachable` (could not be asked, a fault and a missed deadline included),
    #: or `link_gone` (1.6).
    outcome: AskOutcome
    #: What the finder handed over, including what it handed over before it failed.
    images: tuple[FoundImage, ...]
    pages: tuple[FoundPage, ...]
    #: The failure's own words, scrubbed, when `outcome` is `unreachable` or `link_gone`.
    failure: str | None
    #: Whether the host contained a fault in this call (the plugin answered outside its interface).
    faulted: bool


@dataclass(frozen=True, slots=True)
class JudgedInstance:
    """One image phase two kept, as it judged it."""

    found: FoundImage
    #: How sure phase two is that this is the work asked for, 0 to 1.
    confidence: float
    #: Whether the image's size reaches the quality minimum.
    meets_minimum: bool
    #: The words phase two gives for keeping it.
    rationale: str


@dataclass(frozen=True, slots=True)
class Settled:
    """What phase two makes of the plugin's answer when the plugin is the only source: `PhaseTwoEngine.resolve`."""

    #: The images kept, best first.
    instances: tuple[JudgedInstance, ...]
    #: Which gates refused the rest (`UnresolvedReason`): empty when nothing was refused.
    refusals: frozenset[UnresolvedReason]
    #: Pages the finder found and does not read.
    pages: tuple[FoundPage, ...]
    #: `None` when the work is settled (kept, or held by nobody); else why it waits to be asked again:
    #: the plugin could not be asked, or cannot answer this kind of work.
    waits: str | None


@dataclass(frozen=True, slots=True)
class WouldFetch:
    """What the host would fetch after a reader's answer, which this helper does not."""

    #: `"direct"` (an image URL) or `"tiles"` (what `dezoomify-rs` reads).
    method: str
    #: The address the reader answered, after the host's address check.
    url: str


@dataclass(frozen=True, slots=True)
class Read:
    """What acquisition makes of a stored source URL the plugin claims, as it would record it."""

    #: The plugin the roster routed the URL to; `None` when no installed plugin claims it
    #: (acquisition would then fetch the URL as recorded).
    plugin: str | None
    #: What the fetch said (`FetchOutcome`). `None` when the reader answered a locator and the
    #: host would go on to fetch it: see `fetch`.
    outcome: FetchOutcome | None
    #: When the host asks again (`RetryRule`, the queue's own table); `None` when `outcome` is.
    again: RetryRule | None
    #: The words acquisition records against the source (scrubbed).
    detail: str
    #: Set exactly when `outcome` is `None`.
    fetch: WouldFetch | None
    #: Set when the plugin claims the URL and is installed but not loaded: acquisition raises
    #: for this rather than recording it, and this is the words it raises.
    unavailable: str | None = None


class _Entry:
    """An entry point for a plugin in hand: the three things the loader reads of one."""

    group = ENTRY_POINT_GROUP
    dist = None

    def __init__(self, name: str, plugin: SourcePlugin) -> None:
        self.name = name
        self.value = f"<in hand>:{name}"
        self._plugin = plugin

    def load(self) -> SourcePlugin:
        return self._plugin


class _Ledger:
    """The two things of the catalogue acquisition touches when a reader answers: one source, and what is recorded of it."""

    def __init__(self, source: Source) -> None:
        self.source = source
        self.recorded: list[tuple[FetchStatus, FetchOutcome | None]] = []

    def list_sources(self, _artwork_id: str) -> list[Source]:
        return [self.source]

    def record_fetch(self, _source_id: str, *, status: FetchStatus, outcome: FetchOutcome | None = None) -> None:
        self.recorded.append((status, outcome))


#: What `Read.detail` says when the reader answered a locator, which the host would fetch next.
_WOULD_FETCH_NEXT: Final[str] = "the reader answered; the host would fetch it next, and this helper does not"


class _Stopped(BaseException):
    """Raised where acquisition would fetch, and caught by `read`.

    A `BaseException`, so that no handler in acquisition's fetch paths (each
    turns an `Exception` into a recorded failure) takes it for a failed fetch:
    the helper stops there, with nothing recorded and nothing journalled.
    """


class _StopsBeforeFetching:
    """Acquisition's two fetches, the direct path's and the tiled path's, each replaced by one that says what it would fetch.

    Handed to `AcquisitionService` as its `open_stream` and `fetch_tiles`, the
    seams it fetches through, so everything before them is the host's: the
    routing, the reader call under its deadline and containment, the reader's
    answer sorted into an outcome, the address check of the locator. Only the
    bytes are not got, and neither fetch can run whatever acquisition's own
    methods are called.
    """

    def __init__(self) -> None:
        self.would_fetch: WouldFetch | None = None

    def open_stream(self, url: str) -> AbstractContextManager[Iterator[bytes]]:
        self._stop(WouldFetch("direct", url))

    def fetch_tiles(self, url: str, **_how: object) -> TileResult:
        self._stop(WouldFetch("tiles", url))

    def _stop(self, would: WouldFetch) -> NoReturn:
        # Kept before raising, so that a handler that took the stop for a
        # failure still leaves what the host would have fetched.
        self.would_fetch = would
        raise _Stopped


def _public(_host: str) -> Sequence[str]:
    return [_PUBLIC_ADDRESS]


class PluginHost:
    """One plugin, loaded by the host's own loader, to be asked as the host asks it.

    Made by `host`. A plugin that did not load has a `reading` that says why, and
    `ask`, `resolve` and `read` raise `NotAvailable` for it.
    """

    def __init__(
        self,
        roster: SourceRoster,
        name: str,
        *,
        registry: Registry | None,
        scratch: tempfile.TemporaryDirectory[str],
    ) -> None:
        self._roster = roster
        self._name = name
        self._registry = registry
        #: Held, so that the directory goes when the host does.
        self._directory = scratch
        self._scratch = Path(scratch.name)

    @property
    def name(self) -> str:
        """The name the plugin was loaded under: its entry point's name, and the provider its images carry."""
        return self._name

    @property
    def reading(self) -> Reading:
        """What the host has counted of the plugin so far."""
        reading = self._reading()
        return Reading(
            state=str(reading.state),
            reason=reading.reason,
            faults=reading.faults,
            unasked=reading.unasked,
            answered=reading.answered,
            last_fault=reading.last_fault,
            last_unasked=reading.last_unasked,
        )

    def ask(self, query: ImageQuery) -> Asked:
        """Ask the plugin's finder one question, and say how the host sorted its answer."""
        pool = self._pool()
        before = self._reading().faults
        self._declare()
        answer = pool.ask(self._name, query)
        return Asked(
            outcome=answer.outcome,
            images=answer.images,
            pages=answer.pages,
            failure=answer.failure,
            faulted=self._reading().faults > before,
        )

    def resolve(self, query: ImageQuery, *, minimum_long_edge_px: int = DEFAULT_MINIMUM_LONG_EDGE_PX) -> Settled:
        """What phase two makes of the plugin's answer to `query`, with the plugin as the only source.

        Asks the plugin once. A registry given to `host` is the one phase two
        consults for the work's recorded pages and its creators' names.
        """
        engine = PhaseTwoEngine(
            self._pool(), profile=QualityProfile(minimum_long_edge_px=minimum_long_edge_px), registry=self._registry
        )
        self._declare()
        try:
            resolution = engine.resolve(query)
        except ImageSearchFailure as exc:
            return Settled(instances=(), refusals=frozenset(), pages=(), waits=str(exc))
        return Settled(
            instances=tuple(
                JudgedInstance(
                    found=each.found, confidence=each.confidence, meets_minimum=not each.below_minimum, rationale=each.rationale
                )
                for each in resolution.instances
            ),
            refusals=frozenset(resolution.refusals),
            pages=resolution.pages,
            waits=None,
        )

    def judge(
        self, query: ImageQuery, found: FoundImage, *, minimum_long_edge_px: int = DEFAULT_MINIMUM_LONG_EDGE_PX
    ) -> JudgedInstance | UnresolvedReason:
        """Phase two's verdict on one image against the work asked for: kept as judged, or the gate that refused it.

        Asks the plugin nothing: `found` is whatever the test holds, from the plugin's
        finder or built by hand. Asks the registry (if one was given to `host`) only
        when the title or the artist differs, as phase two does.
        """
        engine = PhaseTwoEngine(
            self._pool(), profile=QualityProfile(minimum_long_edge_px=minimum_long_edge_px), registry=self._registry
        )
        judged = engine.judge(query, found, WikidataLink(self._registry, query))
        if isinstance(judged, UnresolvedReason):
            return judged
        return JudgedInstance(
            found=judged.found, confidence=judged.confidence, meets_minimum=not judged.below_minimum, rationale=judged.rationale
        )

    def read(self, url: str, *, resolve: Callable[[str], Sequence[str]] = _public) -> Read:
        """Acquire a stored source whose URL is `url` and say what the host records, and does next.

        `resolve` is the address check's lookup of a name; the default answers every name with a
        public address, so that nothing here touches the network.
        """
        source = Source(
            id="source-under-test",
            artwork_id="work-under-test",
            url=url,
            provider=self._name,
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
        )
        ledger = _Ledger(source)
        originals = self._scratch / "originals"
        originals.mkdir(parents=True, exist_ok=True)
        stops = _StopsBeforeFetching()
        service = AcquisitionService(
            cast("CatalogueService", ledger),
            AcquisitionSettings(
                art_root=self._scratch,
                originals_path=originals,
                tile_cache_path=self._scratch / "tiles",
                user_agent="plugin-tests",
                tile_binary="dezoomify-rs",
                tile_max_pixels=1,
                tile_timeout_seconds=1,
                max_image_bytes=1,
                min_free_bytes=0,
            ),
            open_stream=stops.open_stream,
            route=self._roster.route,
            resolve=resolve,
            fetch_tiles=stops.fetch_tiles,
        )
        route = self._roster.route(url, self._name)
        self._declare()
        try:
            result = service.acquire(source.artwork_id)
        except _SourcePluginUnavailable as unavailable:
            return Read(plugin=route.plugin, outcome=None, again=None, detail="", fetch=None, unavailable=str(unavailable))
        except _Stopped:
            pass
        if stops.would_fetch is not None:
            return Read(plugin=route.plugin, outcome=None, again=None, detail=_WOULD_FETCH_NEXT, fetch=stops.would_fetch)
        _status, outcome = ledger.recorded[-1]
        if outcome is None:
            raise RuntimeError("acquisition ended without recording an outcome or reaching a fetch")
        return Read(plugin=route.plugin, outcome=outcome, again=RETRY_RULES[outcome], detail=result.detail, fetch=None)

    # -- the host's own parts, as the methods above use them ----------------------

    def _reading(self) -> PluginReading:
        return next(each for each in self._roster.observe() if each.name == self._name)

    def _declare(self) -> None:
        museum = self._reading().identity.museum
        declare_museums({} if museum is None else {self._name: museum})

    def _pool(self) -> ImageSourcePool:
        if self._reading().state is not PluginState.LOADED:
            raise NotAvailable(f"the plugin did not load ({self._reading().state}): {self._reading().reason}")
        if not self._roster.finders:
            raise NotAvailable("the plugin provides no finder")
        return ImageSourcePool(self._roster.finders)


def host(
    plugin: SourcePlugin | importlib.metadata.EntryPoint,
    *,
    name: str | None = None,
    environ: Mapping[str, str] | None = None,
    registry: Registry | None = None,
    user_agent: str = "arrt-plugin-tests",
    preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
    data_root: Path | None = None,
    wait_for: WaitFor | None = None,
) -> PluginHost:
    """Load `plugin` as the host does, and return what to ask it with.

    `plugin` is the `SourcePlugin` a distribution's entry point names, with `name`
    the entry point's name (what `pyproject.toml` registers it as); or the entry
    point itself, which is loaded the way the host loads it, so a typo in it fails
    here. A plugin the host would refuse (another major, a newer minor than this
    Arrt provides, a deadline past the ceiling, parts that break the interface)
    is refused here, and its `reading` says why.

    `environ`, `user_agent`, `preview_max_bytes` and `registry` are the
    `SourceContext` the factory is given; `data_root` is where plugins keep their
    own directories (the plugin gets `data_root / name`). `wait_for` is how the
    host waits for a call, a parameter of the loader so that a deadline of
    minutes can run on a clock the test moves: it is called with the call's
    `threading.Event` and its seconds, and answers whether the event was set.
    """
    if isinstance(plugin, SourcePlugin):
        if name is None:
            raise TypeError("a plugin in hand is loaded under a name: pass `name`, as its entry point would carry")
        entry: importlib.metadata.EntryPoint | _Entry = _Entry(name, plugin)
    else:
        entry = plugin
        name = plugin.name
    context = SourceContext(
        environ={} if environ is None else dict(environ),
        user_agent=user_agent,
        preview_max_bytes=preview_max_bytes,
        registry=registry,
    )
    options: dict[str, Any] = {} if wait_for is None else {"wait_for": wait_for}
    roster = load_sources(
        context,
        entry_points=[cast("importlib.metadata.EntryPoint", entry)],
        data_root=data_root,
        order=(name,),
        **options,
    )
    return PluginHost(roster, name, registry=registry, scratch=tempfile.TemporaryDirectory(prefix="arrt-plugin-test-"))
