"""Finding the installed source plugins, loading them, and containing their faults.

Arrt's own code, not part of the plugin interface: a plugin imports
`arrt.library.sources`, never this module.

**A plugin that cannot load is left out, and Arrt starts without it.** An import
error, a factory that raises, a plugin written for another interface major, or
parts that break the interface's rules each become a recorded failure naming the
plugin, logged at error and stated on the health panel. Refusing to start
instead would let one broken package, after an upgrade, take every wall's new art
with it, and the startup log already names what did load.

**A fault in a loaded plugin is contained to the call.** A plugin is answering
one of three things (holds nothing, could not be asked, cannot answer this kind of
work), and anything else it does is a fault: raising something else, or answering
in a shape the interface does not allow (an image recorded under another plugin's
name, a `None` where a list belongs). A fault is recorded as "could not be asked"
for that plugin, logged at error, and counted per plugin for the health panel.
Before plugins, a fault propagated and failed the run, which was right when every
source was this repository's code and a fault was a bug the suite should see. The
suites keep that strictness by failing any test that logs `source.plugin_fault`
on `FAULT_LOGGER` (`tests/fault_guard.py`).

The containment is a wrapper around each plugin's parts, made here, rather than a
`try` at each place a part is called. A wrapper covers every caller, including the
next one somebody adds, and a `try` covers the callers someone remembered.

**A plugin's error text is scrubbed before it is shown or logged.** An HTTP
client's error names the URL it asked, and a paid source's key often travels in
the query string, so query strings are cut from anything a plugin's exception
says before it reaches the journal, `/api/health` or the panel.
"""

import importlib.metadata
import logging
import threading
import traceback
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, NoReturn

from arrt.library.discovery.browse import BrowseQuery, CollectionBrowse, CollectionBrowseFailure, OfferedGroup
from arrt.library.discovery.images import (
    Finder,
    FoundImage,
    FoundPage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
    offers_images,
)
from arrt.library.sources.plugin import API_VERSION, Declined, SourceContext, SourceParts, SourcePlugin
from arrt.library.sources.reading import FetchLocator, Reader
from arrt.logs import scrub

log = logging.getLogger(__name__)

#: The entry-point group a plugin registers in.
ENTRY_POINT_GROUP: Final[str] = "arrt.sources"

#: The order a deployment gets when it names none: Commons first, then the Art
#: Institute, by the owner's ruling of 2026-10-01. Order only breaks ties between
#: images ranked level; every finder is asked at once.
DEFAULT_SOURCE_ORDER: Final[tuple[str, ...]] = ("commons", "artic")

#: The log event a contained fault carries, and the logger it is written to. The
#: suites fail any test that logs it, and read both names from here so that moving
#: the containment cannot leave the guard listening to a logger nothing writes to.
FAULT_EVENT: Final[str] = "source.plugin_fault"
FAULT_LOGGER: Final[str] = log.name


def _reraise_scrubbed(exc: Exception, kind: type[Exception]) -> NoReturn:
    """Raise `exc` itself when its message carries no query string; else a `kind` saying the same without one.

    For the interface's own answers, which a plugin raises in its own words: they
    pass the containment as themselves, and reach the journal, a source's recorded
    failure and the Work page. A scrubbed one is raised `from None`, because the
    original, chained, would print the query string beside it in any traceback.
    """
    cleaned = scrub(str(exc))
    if cleaned == str(exc):
        raise exc
    raise kind(cleaned) from None


def describe_exception(exc: BaseException) -> str:
    """An exception as its type and message, with every URL's query string cut.

    For anything a plugin raised: its message reaches the journal and the health
    panel, and an HTTP client's message names the URL it asked, key and all.
    """
    return f"{type(exc).__name__}: {scrub(str(exc))}"


class PluginState(StrEnum):
    """What became of one installed plugin at startup."""

    LOADED = "loaded"
    #: Installed, and this deployment has not configured it. Not a fault.
    DECLINED = "declined"
    #: Installed, and could not be loaded. The reason says why.
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PluginReading:
    """One installed plugin, as the health panel states it: an observation, never a verdict."""

    name: str
    state: PluginState
    #: Why a plugin declined or failed; `None` when it loaded.
    reason: str | None
    #: Faults contained since startup.
    faults: int
    #: When the most recent of those happened, or `None` when there were none.
    last_fault_at: datetime | None
    #: What the most recent fault was, as its type and scrubbed message.
    last_fault: str | None


@dataclass(frozen=True, slots=True)
class Route:
    """Which plugin a URL needs, and whether that plugin can read it here.

    Three cases, and acquisition treats each differently:

    - `plugin` set and `reader` set: the plugin is loaded, and its reader decides
      the fetch.
    - `plugin` set and `reader` `None`: the plugin claims the URL and is installed
      but not loaded, and `unavailable` says why. A fault in this deployment, not
      in the source.
    - `plugin` `None`: no installed plugin claims the URL, which is fetched as
      recorded.
    """

    plugin: str | None = None
    reader: Reader | None = None
    unavailable: str | None = None


class _InterfaceBreach(Exception):
    """A plugin answered in a shape the interface does not allow."""


class _Faults:
    """Per-plugin fault counts, written from the pool's worker threads."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._count: dict[str, int] = {}
        self._last: dict[str, tuple[datetime, str]] = {}

    def record(self, plugin: str, operation: str, exc: BaseException) -> None:
        said = describe_exception(exc)
        # The frames without the message, because the message is what may carry a
        # key and the frames are what a maintainer needs. `exc_info` would print
        # the unscrubbed message beside them.
        frames = "".join(traceback.format_tb(exc.__traceback__))
        log.error(
            "source plugin %s faulted during %s, outside its interface; recorded as could not be asked: %s\n%s",
            plugin,
            operation,
            said,
            frames,
            extra={"event": FAULT_EVENT, "plugin": plugin, "operation": operation},
        )
        with self._lock:
            self._count[plugin] = self._count.get(plugin, 0) + 1
            self._last[plugin] = (self._now(), said)

    def of(self, plugin: str) -> tuple[int, datetime | None, str | None]:
        with self._lock:
            last = self._last.get(plugin)
            return self._count.get(plugin, 0), None if last is None else last[0], None if last is None else last[1]


def _images(answer: object, plugin: str, *, pages_only: bool = False) -> tuple[FoundImage | FoundPage, ...]:
    """A finder's answer, checked. Each image is recorded under its own `provider`,
    and previews and fetches are routed back by it, so an image under another
    plugin's name would be stored and fetched as that plugin's. A page carries no
    name, because nothing is recorded under one.

    A finder that declared it offers pages only may not answer an image: the pool
    does not count it as having answered, so its image would sit beside a work
    left waiting as if no source could be asked."""
    if isinstance(answer, str | bytes) or not isinstance(answer, Iterable):
        raise _InterfaceBreach(f"find_images answered a {type(answer).__name__}, not a list of FoundImage")
    images = tuple(answer)
    for image in images:
        if isinstance(image, FoundPage):
            continue
        if not isinstance(image, FoundImage):
            raise _InterfaceBreach(f"find_images answered a {type(image).__name__} among its images")
        if pages_only:
            raise _InterfaceBreach("find_images answered a FoundImage from a finder that declares offers_images = False")
        if image.provider != plugin:
            raise _InterfaceBreach(
                f"find_images answered an image recorded under {image.provider!r}; a plugin's images "
                f"are recorded under its own name, {plugin!r}"
            )
    return images


def _preview(answer: object) -> bytes | None:
    if answer is not None and not isinstance(answer, bytes):
        raise _InterfaceBreach(f"fetch_preview answered a {type(answer).__name__}, not bytes or None")
    return answer


def _locator(answer: object) -> FetchLocator:
    """A reader's answer, checked for its type. Its words are left as they are here: a
    `none` reason and a URL both reach anyone only through acquisition, which scrubs
    them where it records and journals them, and a URL to fetch must stay whole."""
    if not isinstance(answer, FetchLocator):
        raise _InterfaceBreach(f"read answered a {type(answer).__name__}, not a FetchLocator")
    return answer


def _groups(answer: object) -> tuple[OfferedGroup, ...]:
    if isinstance(answer, str | bytes) or not isinstance(answer, Iterable):
        raise _InterfaceBreach(f"browse answered a {type(answer).__name__}, not a list of OfferedGroup")
    groups = tuple(answer)
    if not all(isinstance(group, OfferedGroup) for group in groups):
        raise _InterfaceBreach("browse answered something other than OfferedGroup among its groups")
    return groups


class _ContainedFinder:
    """A plugin's finder, with anything outside its interface turned into "could not be asked"."""

    def __init__(self, inner: Finder, plugin: str, faults: _Faults) -> None:
        self._inner = inner
        self._plugin = plugin
        self._faults = faults
        #: Carried from the plugin's finder, so the pool can tell a finder of
        #: pages from one of images through the containment.
        self.offers_images = offers_images(inner)

    @property
    def provider(self) -> str:
        return self._plugin

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage | FoundPage]:
        try:
            return _images(self._inner.find_images(query), self._plugin, pages_only=not self.offers_images)
        # Two of the interface's three answers, passed through as themselves with
        # their message scrubbed (`_reraise_scrubbed`). Two clauses rather than one
        # tuple, because the formatter writes a bare tuple in a form Python 3.12
        # cannot parse, and the root suite's guards parse this file under 3.12 (#166).
        except ImageSearchFailure as exc:
            _reraise_scrubbed(exc, ImageSearchFailure)
        except ImageQueryUnanswerable as exc:
            _reraise_scrubbed(exc, ImageQueryUnanswerable)
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a plugin fault must not fail a run
            self._faults.record(self._plugin, "find_images", exc)
            raise ImageSearchFailure(f"the {self._plugin} plugin faulted: {type(exc).__name__}") from exc

    def fetch_preview(self, url: str) -> bytes | None:
        try:
            return _preview(self._inner.fetch_preview(url))
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- None is the interface's own failed preview
            self._faults.record(self._plugin, "fetch_preview", exc)
            return None


class _ContainedReader:
    """A plugin's reader, with anything outside its interface turned into "could not be asked"."""

    def __init__(self, inner: Reader, plugin: str, faults: _Faults) -> None:
        self._inner = inner
        self._plugin = plugin
        self._faults = faults

    def read(self, url: str) -> FetchLocator:
        try:
            return _locator(self._inner.read(url))
        except ImageSearchFailure as exc:
            _reraise_scrubbed(exc, ImageSearchFailure)
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- recorded against the source instead
            self._faults.record(self._plugin, "read", exc)
            raise ImageSearchFailure(f"the {self._plugin} plugin faulted: {type(exc).__name__}") from exc


class _ContainedCollection:
    """A plugin's collection, with anything outside its interface turned into a browse failure."""

    def __init__(self, inner: CollectionBrowse, plugin: str, faults: _Faults) -> None:
        self._inner = inner
        self._plugin = plugin
        self._faults = faults

    @property
    def provider(self) -> str:
        return self._plugin

    def browse(self, queries: Sequence[BrowseQuery], *, per_query: int) -> Sequence[OfferedGroup]:
        try:
            return _groups(self._inner.browse(queries, per_query=per_query))
        except CollectionBrowseFailure as exc:
            _reraise_scrubbed(exc, CollectionBrowseFailure)
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a plugin fault must not fail a run
            self._faults.record(self._plugin, "browse", exc)
            raise CollectionBrowseFailure(f"the {self._plugin} plugin faulted: {type(exc).__name__}") from exc


@dataclass(frozen=True, slots=True)
class _Claimant:
    name: str
    claims: Callable[[str], bool]
    #: `None` when the plugin is installed and not loaded.
    reader: Reader | None
    #: Why it is not loaded; `None` when it is.
    unavailable: str | None


class SourceRoster:
    """The plugins this process loaded, in preference order, and what became of the rest."""

    def __init__(
        self,
        *,
        finders: Sequence[Finder],
        collection: CollectionBrowse | None,
        claimants: Sequence[_Claimant],
        states: Sequence[tuple[str, PluginState, str | None]],
        faults: _Faults,
        unknowable: Mapping[str, str] | None = None,
    ) -> None:
        self._finders = tuple(finders)
        self._collection = collection
        self._claimants = tuple(claimants)
        self._states = tuple(states)
        self._faults = faults
        #: Installed plugins that failed before a `SourcePlugin` was got from them
        #: (an import error, an entry point naming something else, a name two
        #: distributions share), each with its reason. Which URLs they read cannot
        #: be asked, so their own rows are recognised by the provider they record.
        self._unknowable = dict(unknowable or {})

    @classmethod
    def empty(cls) -> SourceRoster:
        """A roster with no plugins, for a process assembled without loading any."""
        return cls.of()

    @classmethod
    def of(
        cls,
        *,
        finders: Sequence[Finder] = (),
        collection: CollectionBrowse | None = None,
        readers: Mapping[str, tuple[Callable[[str], bool], Reader]] | None = None,
        unavailable: Mapping[str, tuple[Callable[[str], bool], str]] | None = None,
        unknowable: Mapping[str, str] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> SourceRoster:
        """A roster from parts in hand, without entry points: for tests, and for hand-assembled sources.

        Each part is named as a plugin of its own: a finder by its `provider`, a
        collection likewise, and a reader by its key, which carries the claims that
        route URLs to it. `unavailable` names plugins that claim URLs and declined,
        each with its reason, and `unknowable` plugins that failed before their
        claims could be read. Every part is contained exactly as a loaded plugin's is.
        """
        faults = _Faults(now)
        readers = dict(readers or {})
        unavailable = dict(unavailable or {})
        names = [finder.provider for finder in finders]
        if collection is not None:
            names.append(collection.provider)
        names.extend(readers)
        return cls(
            finders=[_ContainedFinder(finder, finder.provider, faults) for finder in finders],
            collection=None if collection is None else _ContainedCollection(collection, collection.provider, faults),
            claimants=[
                *(
                    _Claimant(name, claims, _ContainedReader(reader, name, faults), None)
                    for name, (claims, reader) in readers.items()
                ),
                *(
                    _Claimant(name, claims, None, f"the {name} source plugin is installed and not loaded: {reason}")
                    for name, (claims, reason) in unavailable.items()
                ),
            ],
            states=[
                *((name, PluginState.LOADED, None) for name in dict.fromkeys(names)),
                *((name, PluginState.DECLINED, reason) for name, (_claims, reason) in unavailable.items()),
                *((name, PluginState.FAILED, reason) for name, reason in (unknowable or {}).items()),
            ],
            faults=faults,
            unknowable=unknowable,
        )

    @property
    def finders(self) -> tuple[Finder, ...]:
        """Every loaded plugin's finder, most preferred first."""
        return self._finders

    @property
    def finds_images(self) -> bool:
        """Whether any loaded finder can answer with an image.

        The one test of whether phase 2 has a source, read by the wiring, the
        previews setting and the startup line alike. A roster holding only a finder
        of pages has none: a pool built from it would accept every Get and leave
        each work waiting, because no answer from it says whether an image exists.
        """
        return any(offers_images(finder) for finder in self._finders)

    @property
    def collection(self) -> CollectionBrowse | None:
        """The collection a run supplements from: the most preferred plugin's that offers one."""
        return self._collection

    def route(self, url: str, provider: str | None = None) -> Route:
        """Which plugin `url` needs, and whether it can be read here; the first claimant in preference order.

        `provider`, the name a stored source was recorded under, is consulted only
        when no claimant claims the URL and that name is a plugin whose claims could
        not be read. Its own rows are then a deployment fault naming it, as a
        declined plugin's are, rather than a fetch of a page only it can read.
        """
        for claimant in self._claimants:
            try:
                claimed = bool(claimant.claims(url))
            except Exception as exc:  # prawduct:allow prawduct/broad-except -- a raising claims check claims nothing
                self._faults.record(claimant.name, "claims", exc)
                claimed = False
            if claimed:
                return Route(plugin=claimant.name, reader=claimant.reader, unavailable=claimant.unavailable)
        if provider is not None and provider in self._unknowable:
            return Route(
                plugin=provider,
                unavailable=f"the {provider} source plugin is installed and could not be loaded: {self._unknowable[provider]}",
            )
        return Route()

    def observe(self) -> tuple[PluginReading, ...]:
        """Every installed plugin, now, with its faults since startup."""
        readings = []
        for name, state, reason in self._states:
            faults, last_at, last = self._faults.of(name)
            readings.append(
                PluginReading(name=name, state=state, reason=reason, faults=faults, last_fault_at=last_at, last_fault=last)
            )
        return tuple(readings)


def load_sources(
    context: SourceContext,
    *,
    order: Sequence[str] = DEFAULT_SOURCE_ORDER,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> SourceRoster:
    """Load every installed plugin, and say what became of each.

    `order` names plugins most preferred first; plugins it does not name follow,
    by name. `entry_points` defaults to what this interpreter has installed in
    `ENTRY_POINT_GROUP`, and is a parameter so the loader can be tested without
    installing a distribution per case.
    """
    found = list(importlib.metadata.entry_points(group=ENTRY_POINT_GROUP) if entry_points is None else entry_points)
    faults = _Faults(now)
    states: dict[str, tuple[PluginState, str | None]] = {}
    parts: dict[str, SourceParts] = {}
    plugins: dict[str, SourcePlugin] = {}
    for entry in found:
        if entry.name in states:
            # Two distributions registering one name would record their images
            # under one provider, and every stored row would then belong to
            # whichever loaded last. Neither is loaded.
            reason = "two installed distributions register this name; neither is loaded"
            states[entry.name] = (PluginState.FAILED, reason)
            parts.pop(entry.name, None)
            plugins.pop(entry.name, None)
            continue
        # Before the factory runs, so a factory that hangs leaves its name in the
        # journal rather than a startup that simply stops.
        log.info("loading source plugin %s", entry.name, extra={"event": "source.loading", "plugin": entry.name})
        plugin, loaded = _load_one(entry, context)
        if plugin is not None:
            plugins[entry.name] = plugin
        if isinstance(loaded, SourceParts):
            states[entry.name] = (PluginState.LOADED, None)
            parts[entry.name] = loaded
        elif isinstance(loaded, Declined):
            states[entry.name] = (PluginState.DECLINED, scrub(loaded.reason))
        else:
            states[entry.name] = (PluginState.FAILED, loaded)

    unknown = [name for name in order if name not in states]
    if unknown:
        # A misspelt name would otherwise reorder the sources in silence.
        log.warning(
            "SOURCE_ORDER names %s, which no installed plugin is; it is ignored",
            ", ".join(unknown),
            extra={"event": "source.order_unknown"},
        )
    ranked = sorted(states, key=lambda name: (order.index(name) if name in order else len(order), name))
    for name in ranked:
        state, reason = states[name]
        if state is PluginState.LOADED:
            log.info("source plugin %s loaded", name, extra={"event": "source.loaded", "plugin": name})
        elif state is PluginState.DECLINED:
            log.info("source plugin %s declined: %s", name, reason, extra={"event": "source.declined", "plugin": name})
        else:
            log.error("source plugin %s was not loaded: %s", name, reason, extra={"event": "source.failed", "plugin": name})

    finders = [_ContainedFinder(parts[n].finder, n, faults) for n in ranked if n in parts and parts[n].finder is not None]
    collections = [
        _ContainedCollection(parts[n].collection, n, faults) for n in ranked if n in parts and parts[n].collection is not None
    ]
    claimants = [
        _Claimant(
            name=n,
            claims=plugins[n].claims,
            reader=(_ContainedReader(parts[n].reader, n, faults) if n in parts and parts[n].reader is not None else None),
            unavailable=None if n in parts else f"the {n} source plugin is installed and not loaded: {states[n][1]}",
        )
        for n in ranked
        if n in plugins and plugins[n].claims is not None
    ]
    return SourceRoster(
        finders=finders,
        collection=collections[0] if collections else None,
        claimants=claimants,
        states=[(name, *states[name]) for name in ranked],
        faults=faults,
        unknowable={n: states[n][1] or "" for n in ranked if n not in plugins and states[n][0] is PluginState.FAILED},
    )


def _load_one(
    entry: importlib.metadata.EntryPoint, context: SourceContext
) -> tuple[SourcePlugin | None, SourceParts | Declined | str]:
    """The plugin object, if one was got, and its parts, its decline, or why it could not be loaded."""
    try:
        plugin = entry.load()
    except Exception as exc:  # prawduct:allow prawduct/broad-except -- a plugin that cannot import is left out, and named
        return None, f"it could not be imported: {describe_exception(exc)}"
    if not isinstance(plugin, SourcePlugin):
        return None, f"its entry point names a {type(plugin).__name__}, not a SourcePlugin"
    if plugin.api_major != API_VERSION[0]:
        return plugin, (
            f"it was written for source interface {plugin.api_major}, and this Arrt provides "
            f"{API_VERSION[0]}.{API_VERSION[1]}"
        )
    try:
        answer = plugin.create(context)
    except Exception as exc:  # prawduct:allow prawduct/broad-except -- a factory that raises is left out, and named
        return plugin, f"its factory raised {describe_exception(exc)}"
    if isinstance(answer, Declined):
        return plugin, answer
    if not isinstance(answer, SourceParts):
        return plugin, f"its factory answered a {type(answer).__name__}, not SourceParts or Declined"
    try:
        breach = _breach(entry.name, plugin, answer)
    except Exception as exc:  # prawduct:allow prawduct/broad-except -- raising parts are left out, and named
        return plugin, f"its parts raised while being checked: {describe_exception(exc)}"
    return plugin, answer if breach is None else breach


def _breach(name: str, plugin: SourcePlugin, parts: SourceParts) -> str | None:
    """How a plugin's parts break the interface, or `None` when they do not.

    Reading a part's `provider` and checking it against a protocol both run the
    plugin's code, which is why the caller holds this inside a `try`.
    """
    for part, value, kind in (
        ("finder", parts.finder, Finder),
        ("reader", parts.reader, Reader),
        ("collection", parts.collection, CollectionBrowse),
    ):
        if value is not None and not isinstance(value, kind):
            return f"its {part} is a {type(value).__name__}, which is not a {kind.__name__}"
    for part, recorded in (("finder", parts.finder), ("collection", parts.collection)):
        if recorded is not None and recorded.provider != name:
            return (
                f"its {part} records images under {recorded.provider!r}, and a plugin's parts must use the "
                f"plugin's own name, {name!r}, so stored rows name the plugin that found them"
            )
    if parts.finder is not None and not isinstance(getattr(parts.finder, "offers_images", True), bool):
        return "its finder's offers_images is not a bool, so whether it finds images cannot be read"
    if parts.reader is not None and plugin.claims is None:
        return "it provides a reader and declares no claims, so no URL would ever reach it"
    if parts.reader is None and plugin.claims is not None:
        return "it declares claims and provides no reader, so every URL it claims would fail"
    return None


def environment_of(source: Mapping[str, str]) -> Mapping[str, str]:
    """A read-only copy of an environment, for `SourceContext.environ`."""
    return MappingProxyType(dict(source))
