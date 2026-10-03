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
work), and anything else it raises is a fault: recorded as "could not be asked"
for that plugin, logged at error with the traceback, and counted per plugin for
the health panel. Before plugins, a fault propagated and failed the run, which was
right when every source was this repository's code and a fault was a bug the
suite should see. The suites keep that strictness by failing any test that logs
`source.plugin_fault` (`tests/conftest.py`).

The containment is a wrapper around each plugin's parts, made here, rather than a
`try` at each place a finder is called. A wrapper covers every caller, including
the next one somebody adds, and a `try` covers the callers someone remembered.
"""

import importlib.metadata
import logging
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from arrt.library.discovery.browse import BrowseQuery, CollectionBrowse, CollectionBrowseFailure, OfferedGroup
from arrt.library.discovery.images import Finder, FoundImage, ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.sources.plugin import API_VERSION, Declined, SourceContext, SourceParts, SourcePlugin

log = logging.getLogger(__name__)

#: The entry-point group a plugin registers in.
ENTRY_POINT_GROUP: Final[str] = "arrt.sources"

#: The order a deployment gets when it names none: Commons first, then the Art
#: Institute, by the owner's ruling of 2026-10-01. Order only breaks ties between
#: images ranked level; every finder is asked at once.
DEFAULT_SOURCE_ORDER: Final[tuple[str, ...]] = ("commons", "artic")

#: The log event a contained fault carries. The suites fail any test that logs it.
FAULT_EVENT: Final[str] = "source.plugin_fault"


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
    #: What the most recent fault was, as its exception type and message.
    last_fault: str | None


class _Faults:
    """Per-plugin fault counts, written from the pool's worker threads."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._count: dict[str, int] = {}
        self._last: dict[str, tuple[datetime, str]] = {}

    def record(self, plugin: str, operation: str, exc: BaseException) -> None:
        log.error(
            "source plugin %s raised during %s, which is outside its interface; recorded as could not be asked",
            plugin,
            operation,
            exc_info=exc,
            extra={"event": FAULT_EVENT, "plugin": plugin, "operation": operation},
        )
        with self._lock:
            self._count[plugin] = self._count.get(plugin, 0) + 1
            self._last[plugin] = (self._now(), f"{type(exc).__name__}: {exc}")

    def of(self, plugin: str) -> tuple[int, datetime | None, str | None]:
        with self._lock:
            last = self._last.get(plugin)
            return self._count.get(plugin, 0), None if last is None else last[0], None if last is None else last[1]


class _ContainedFinder:
    """A plugin's finder, with anything outside its interface turned into "could not be asked"."""

    def __init__(self, inner: Finder, plugin: str, faults: _Faults) -> None:
        self._inner = inner
        self._plugin = plugin
        self._faults = faults

    @property
    def provider(self) -> str:
        return self._plugin

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        try:
            return self._inner.find_images(query)
        # Two of the interface's three answers, passed through as themselves. Two
        # clauses rather than one tuple, because the formatter writes a bare tuple
        # in a form Python 3.12 cannot parse, and the root suite's import guards
        # parse this file under 3.12 (#166).
        except ImageSearchFailure:
            raise
        except ImageQueryUnanswerable:
            raise
        except (
            Exception
        ) as exc:  # prawduct:allow prawduct/broad-except -- a plugin's fault must not fail the run; logged and counted
            self._faults.record(self._plugin, "find_images", exc)
            raise ImageSearchFailure(f"the {self._plugin} plugin faulted: {type(exc).__name__}") from exc

    def fetch_preview(self, url: str) -> bytes | None:
        try:
            return self._inner.fetch_preview(url)
        except (
            Exception
        ) as exc:  # prawduct:allow prawduct/broad-except -- a missing preview is the interface's own answer to a failure
            self._faults.record(self._plugin, "fetch_preview", exc)
            return None

    def tile_url(self, url: str) -> str:
        try:
            return self._inner.tile_url(url)
        except ImageSearchFailure:
            raise
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a fault becomes a failure recorded against the source
            self._faults.record(self._plugin, "tile_url", exc)
            raise ImageSearchFailure(f"the {self._plugin} plugin faulted: {type(exc).__name__}") from exc


class _ContainedCollection:
    """A plugin's collection, with anything outside its interface turned into a browse failure."""

    def __init__(self, inner: CollectionBrowse, plugin: str, faults: _Faults) -> None:
        self._inner = inner
        self._plugin = plugin
        self._faults = faults

    @property
    def provider(self) -> str:
        return self._inner.provider

    def browse(self, queries: Sequence[BrowseQuery], *, per_query: int) -> Sequence[OfferedGroup]:
        try:
            return self._inner.browse(queries, per_query=per_query)
        except CollectionBrowseFailure:
            raise
        except (
            Exception
        ) as exc:  # prawduct:allow prawduct/broad-except -- a plugin's fault must not fail the run; logged and counted
            self._faults.record(self._plugin, "browse", exc)
            raise CollectionBrowseFailure(f"the {self._plugin} plugin faulted: {type(exc).__name__}") from exc


class SourceRoster:
    """The plugins this process loaded, in preference order, and what became of the rest."""

    def __init__(
        self,
        *,
        finders: Sequence[Finder],
        collection: CollectionBrowse | None,
        states: Sequence[tuple[str, PluginState, str | None]],
        faults: _Faults,
    ) -> None:
        self._finders = tuple(finders)
        self._collection = collection
        self._states = tuple(states)
        self._faults = faults

    @classmethod
    def empty(cls) -> SourceRoster:
        """A roster with no plugins, for a process assembled without loading any."""
        return cls(finders=(), collection=None, states=(), faults=_Faults(lambda: datetime.now(UTC)))

    @property
    def finders(self) -> tuple[Finder, ...]:
        """Every loaded plugin's finder, most preferred first."""
        return self._finders

    @property
    def collection(self) -> CollectionBrowse | None:
        """The collection a run supplements from: the most preferred plugin's that offers one."""
        return self._collection

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
    for entry in found:
        if entry.name in states:
            # Two distributions registering one name would record their images
            # under one provider, and every stored row would then belong to
            # whichever loaded last. Neither is loaded.
            reason = "two installed distributions register this name; neither is loaded"
            states[entry.name] = (PluginState.FAILED, reason)
            parts.pop(entry.name, None)
            continue
        loaded = _load_one(entry, context)
        if isinstance(loaded, SourceParts):
            states[entry.name] = (PluginState.LOADED, None)
            parts[entry.name] = loaded
        elif isinstance(loaded, Declined):
            states[entry.name] = (PluginState.DECLINED, loaded.reason)
        else:
            states[entry.name] = (PluginState.FAILED, loaded)

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
    return SourceRoster(
        finders=finders,
        collection=collections[0] if collections else None,
        states=[(name, *states[name]) for name in ranked],
        faults=faults,
    )


def _load_one(entry: importlib.metadata.EntryPoint, context: SourceContext) -> SourceParts | Declined | str:
    """One plugin's parts, its decline, or a sentence saying why it could not be loaded."""
    try:
        plugin = entry.load()
    except Exception as exc:  # prawduct:allow prawduct/broad-except -- a plugin that cannot import is left out, and named
        log.exception("source plugin %s could not be imported", entry.name)
        return f"it could not be imported: {type(exc).__name__}: {exc}"
    if not isinstance(plugin, SourcePlugin):
        return f"its entry point names a {type(plugin).__name__}, not a SourcePlugin"
    if plugin.api_major != API_VERSION[0]:
        return (
            f"it was written for source interface {plugin.api_major}, and this Arrt provides "
            f"{API_VERSION[0]}.{API_VERSION[1]}"
        )
    try:
        answer = plugin.create(context)
    except Exception as exc:  # prawduct:allow prawduct/broad-except -- a factory that raises is left out, and named
        log.exception("source plugin %s raised while being created", entry.name)
        return f"its factory raised {type(exc).__name__}: {exc}"
    if isinstance(answer, Declined):
        return answer
    if not isinstance(answer, SourceParts):
        return f"its factory answered a {type(answer).__name__}, not SourceParts or Declined"
    for part, recorded in (("finder", answer.finder), ("collection", answer.collection)):
        if recorded is not None and recorded.provider != entry.name:
            return (
                f"its {part} records images under {recorded.provider!r}, and a plugin's parts must use the "
                f"plugin's own name, {entry.name!r}, so stored rows name the plugin that found them"
            )
    return answer


def environment_of(source: Mapping[str, str]) -> Mapping[str, str]:
    """A read-only copy of an environment, for `SourceContext.environ`."""
    return MappingProxyType(dict(source))
