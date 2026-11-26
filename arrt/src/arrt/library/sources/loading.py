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
one of four things (holds nothing, could not be asked, cannot answer this kind of
work, and since 1.6 the page is gone), and anything else it does is a fault:
raising something else, or answering in a shape the interface does not allow (an
image recorded under another plugin's name, a `None` where a list belongs). A
fault is recorded as "could not be asked" for that plugin (a `PluginFaulted`,
which acquisition alone tells apart, as `faulted`), logged at error, and counted
per plugin for the health panel.
Before plugins, a fault propagated and failed the run, which was right when every
source was this repository's code and a fault was a bug the suite should see. The
suites keep that strictness by failing any test that logs `source.plugin_fault`
on `FAULT_LOGGER` (`tests/fault_guard.py`).

The containment is a wrapper around each plugin's parts, made here, rather than a
`try` at each place a part is called. A wrapper covers every caller, including the
next one somebody adds, and a `try` covers the callers someone remembered.

**Every call into a plugin has a deadline, and one it misses is "could not be
asked".** A finder or reader gets `FINDER_DEADLINE_SECONDS` or
`READER_DEADLINE_SECONDS`, a preview `PREVIEW_DEADLINE_SECONDS` and a browse
`BROWSE_DEADLINE_SECONDS`. Without one, a plugin that hung (a server trickling
bytes, a lock waited on for ever) held every Get, because the pool waits for
every source, and every look at that source waited behind the Get. A call past
its deadline is recorded against the plugin beside its faults, and the caller
moves on. Python cannot stop a thread, so the call itself is not stopped:
`_Calls` says what becomes of it.

**Within one pass, a plugin that keeps answering "could not be asked" is not
asked again until the next.** A pass (the acquisition queue's, or phase 2's over
a run's works, each opened with `one_pass`) asks works one after another, and a
work its plugin could not be asked about is asked again on the next pass, with
no limit. During a museum's outage that would make every pass ask every such
work, one at a time, each up to the plugin's deadline: minutes each, for the
private plugins. So after `HOLD_BACK_AFTER` could-not-be-asked answers in a row
from one plugin within one pass, the rest of the pass does not ask it: its
finder or reader answers `NotAskedThisPass` at once, without being called or
counted, the caller leaves the work as it was, and the next pass starts a new
count. Any other answer resets the count, so a plugin that answers again is
asked again. Outside a pass (a look, a preview, Ask) nothing is held back. It
builds on the other hold this module keeps, `STRAGGLERS_PER_PLUGIN`, which
bounds the threads a plugin hung on every call can hold, for the life of the
process; it does nothing for a plugin that answers "could not be asked" just
inside its deadline, which is the costly case and the one this bounds.

**A plugin's error text is scrubbed before it is shown or logged.** An HTTP
client's error names the URL it asked, and a paid source's key often travels in
the query string, so query strings are cut from anything a plugin's exception
says before it reaches the journal, `/api/health` or the panel.
"""

import contextvars
import importlib.metadata
import logging
import math
import re
import threading
import time
import traceback
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final, NoReturn, TypeVar

from arrt.counting import agree, figure, noun
from arrt.defaults import DEFAULT_SOURCE_ORDER
from arrt.library.discovery.browse import BrowseQuery, CollectionBrowse, CollectionBrowseFailure, OfferedGroup
from arrt.library.discovery.images import (
    DEFAULT_PREVIEW_MAX_BYTES,
    Finder,
    FoundImage,
    FoundPage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
    LinkGone,
    offers_images,
)
from arrt.library.sources.names import declare_museums, museum_name
from arrt.library.sources.plugin import API_VERSION, Declined, SourceContext, SourceParts, SourcePlugin
from arrt.library.sources.reading import FetchLocator, Reader
from arrt.logs import scrub

#: Re-exported from `arrt.defaults`, where they are declared: importing them from here gives the same object.
__all__ = ["DEFAULT_SOURCE_ORDER"]

log = logging.getLogger(__name__)

#: The entry-point group a plugin registers in.
ENTRY_POINT_GROUP: Final[str] = "arrt.sources"

#: The log event a contained fault carries, and the logger it is written to. The
#: suites fail any test that logs it, and read both names from here so that moving
#: the containment cannot leave the guard listening to a logger nothing writes to.
FAULT_EVENT: Final[str] = "source.plugin_fault"
FAULT_LOGGER: Final[str] = log.name

#: Seconds a finder's `find_images` is waited for. A finder answers for one work;
#: a run asks every finder at once and answers within its window, so this is how
#: long a call is owed, and how long a run that heard no other source waits. Long enough for a paced HTTP plugin to
#: wait its turn and read its page; the private browser plugins allow a page far
#: longer, and such a page is then "could not be asked" and asked again later.
FINDER_DEADLINE_SECONDS: Final[float] = 60.0
#: Seconds a reader's `read` is waited for: one page, as a finder's search is.
READER_DEADLINE_SECONDS: Final[float] = 60.0
#: Seconds a `fetch_preview` is waited for. A look waits this long for a card's
#: picture, and a preview that does not arrive is a card without one.
PREVIEW_DEADLINE_SECONDS: Final[float] = 30.0
#: Seconds a collection's `browse` is waited for: it answers several queries in
#: one call, so it is given longer than one work's search.
BROWSE_DEADLINE_SECONDS: Final[float] = 120.0
#: The longest deadline a plugin may declare for one call (`SourcePlugin.deadlines`).
#: A sanity bound on in-process code the owner installed and already trusts, not a
#: security boundary: it catches a declaration that is a slip (a day, not a
#: minute), and refuses nothing an honest worst case needs. The private browser
#: plugins' own bounds allow 1,012 s for one page and 2,044 s for one holder read
#: behind a crawl delay; an hour covers those with room. A plugin declares its own
#: worst case rather than this: it is how long a call may run on, and a run that
#: heard no other source of images waits for one at most that long.
DEADLINE_CEILING_SECONDS: Final[float] = 3600.0
#: The kinds of call a plugin may declare a deadline for, each a field of `Deadlines`.
DEADLINE_KINDS: Final[tuple[str, ...]] = ("finder", "reader", "preview", "browse")

#: How many of one plugin's calls may still be running after their deadline
#: passed. A call that outlives its deadline keeps its thread until the plugin
#: returns, and a plugin hung on every call would otherwise add one per work for
#: ever. Past this many, a new call to that plugin is "could not be asked" at
#: once, without starting it, until one of them returns.
STRAGGLERS_PER_PLUGIN: Final[int] = 4

#: How many of one plugin's calls may be owed at once: still inside their
#: deadline, and no longer waited for, because the run that asked answered at
#: its window without them (`library/discovery/pool.py`). While one is, neither
#: a run nor a pass of the queue starts another call to that plugin; the work is
#: not asked (`StillAsking`). One, because the owed call is the museum still
#: answering, behind its own pace or crawl delay, and a second call there only
#: waits behind the first or doubles the load on it; without the bound a run
#: going from work to work started a call per work, about the plugin's deadline
#: over the window at once. Calls past their deadline are bounded apart
#: (`STRAGGLERS_PER_PLUGIN`).
OWED_CALLS_PER_PLUGIN: Final[int] = 1

#: Could-not-be-asked answers in a row, from one plugin within one pass, after
#: which the rest of that pass does not ask it (`one_pass`). Three, from what a
#: pass costs: the queue asks one work at a time, each up to the plugin's
#: deadline (60 s by default, minutes for a plugin that declares them, at most
#: `DEADLINE_CEILING_SECONDS`), so three bounds an outage at three deadlines a
#: pass per plugin, where it was one deadline per work it holds. One or two in a
#: row are an ordinary blip (a timeout, a 503) and hold nothing back; three in a
#: row, one work after another, is a museum not answering. The cost: a plugin
#: that fails three asks in a row for unrelated reasons is not asked again until
#: the next pass, and the works behind them wait that long.
#: Only the calls a pass makes are held back, a finder's search and a reader's
#: read; a preview or a browse never is.
HOLD_BACK_AFTER: Final[int] = 3

#: The longest title, artist, or reason for showing no image a plugin may answer.
#: Past it the text is not a title but a page, which every card, journal line and
#: record that carries it would then carry too.
ANSWER_TEXT_MAX_CHARS: Final[int] = 2_000


@dataclass(frozen=True, slots=True)
class Deadlines:
    """How long each kind of call into a plugin is waited for, and how many may outlive it.

    The named constants above, gathered so a test can give a plugin a deadline it
    can pass in a fraction of a second; the wiring takes the defaults.
    """

    finder: float = FINDER_DEADLINE_SECONDS
    reader: float = READER_DEADLINE_SECONDS
    preview: float = PREVIEW_DEADLINE_SECONDS
    browse: float = BROWSE_DEADLINE_SECONDS
    stragglers: int = STRAGGLERS_PER_PLUGIN


#: The deadlines the wiring runs with: the named constants above.
DEFAULT_DEADLINES: Final[Deadlines] = Deadlines()

#: How the host waits for a call: until `done` is set or `seconds` pass, and whether it was set.
#: A parameter of the loader only so a test can run a 300 s deadline on simulated time.
WaitFor = Callable[[threading.Event, float], bool]


def _wait(done: threading.Event, seconds: float) -> bool:
    return done.wait(seconds)


def declared_deadlines(plugin: SourcePlugin, base: Deadlines) -> Deadlines | str:
    """`base`, with what the plugin declares in its place; or why the declaration cannot load.

    Refused by name rather than clamped: a plugin that asked for more than the
    ceiling, or for nothing at all, would otherwise run under a deadline nobody
    chose, and be cut off as "could not be asked" where its author expected an
    answer.
    """
    declared = getattr(plugin, "deadlines", None)
    if declared is None:
        return base
    if not isinstance(declared, Mapping):
        return f"its deadlines are a {type(declared).__name__}, not a mapping of kind of call to seconds"
    chosen: dict[str, float] = {}
    for kind, seconds in declared.items():
        if kind not in DEADLINE_KINDS:
            return f"it declares a deadline for {kind!r}, which is not a kind of call ({', '.join(DEADLINE_KINDS)})"
        if isinstance(seconds, bool) or not isinstance(seconds, int | float) or not math.isfinite(seconds) or seconds <= 0:
            return f"its {kind} deadline of {seconds!r} is not a number of seconds above zero"
        if seconds > DEADLINE_CEILING_SECONDS:
            return f"its {kind} deadline of {seconds:g} seconds is past this Arrt's ceiling of {DEADLINE_CEILING_SECONDS:g}"
        chosen[kind] = float(seconds)
    # Each kind named, because `**chosen` would hand `stragglers` (an int) a float
    # as far as the checker can tell. `DEADLINE_KINDS` is exactly these four, which
    # nothing here can check: `tests/unit/test_plugin_deadlines.py` runs every kind in
    # it through this function and the loader, so a fifth kind not named below fails
    # there by name, rather than loading and running at its default.
    return replace(
        base,
        finder=chosen.get("finder", base.finder),
        reader=chosen.get("reader", base.reader),
        preview=chosen.get("preview", base.preview),
        browse=chosen.get("browse", base.browse),
    )


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


class PluginPart(StrEnum):
    """What a loaded plugin provides, read from its parts."""

    FINDS_IMAGES = "finds_images"
    #: A finder with `offers_images = False`: it offers pages for readers.
    FINDS_PAGES = "finds_pages"
    READS = "reads"
    BROWSES = "browses"


@dataclass(frozen=True, slots=True)
class PluginIdentity:
    """Where an installed plugin came from, and what it provides, as read at startup.

    Every field is `None` or empty when it could not be read: a plugin
    registered by hand rather than by an installed distribution has no
    distribution, one that failed before Arrt got its `SourcePlugin` has no
    interface major, and one that did not load has no parts.
    """

    #: The installed distribution that registers the entry point, as its metadata names it.
    distribution: str | None = None
    #: That distribution's version: what an operator compares when a plugin is upgraded.
    version: str | None = None
    #: The interface major the plugin says it was written for.
    api_major: int | None = None
    provides: tuple[PluginPart, ...] = ()
    #: The museum the plugin declares (interface 1.4), once it passed `_museum_of`;
    #: `None` when it declares none, or one that was refused.
    museum: str | None = None


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
    identity: PluginIdentity = PluginIdentity()
    #: Calls that were "could not be asked" since startup: the plugin's own
    #: `ImageSearchFailure` or `CollectionBrowseFailure`, or a call past its
    #: deadline. Faults are counted apart, in `faults`. A museum that redesigned
    #: its pages reads here, not there, because a parser that does not recognise
    #: a page says so in the interface's own words.
    unasked: int = 0
    #: When the most recent of those was, or `None` when there was none.
    last_unasked_at: datetime | None = None
    #: What the most recent of those said, scrubbed.
    last_unasked: str | None = None
    #: Calls that ended in any other answer of the interface's: something, nothing,
    #: or "cannot answer this kind of work". With none, and `unasked` above zero,
    #: the plugin has said nothing since startup but that it could not be asked.
    answered: int = 0


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
    #: The name the plugin declares for itself, where it declares one: what a sentence about
    #: this route names it by (`museum_name`), because the id is a key and not a name.
    museum: str | None = None


class _InterfaceBreach(Exception):
    """A plugin answered in a shape the interface does not allow."""


class PluginFaulted(ImageSearchFailure):
    """A plugin's call ended outside its interface, and the containment says so in Arrt's words.

    Not part of the interface: no plugin raises it, and `arrt.library.sources`
    does not export it. A subclass of `ImageSearchFailure`, so every caller that
    reads a plugin's call as answered or could-not-be-asked still reads a fault
    as the second, as it always has; acquisition alone tells it apart, and
    records the source's fetch as `faulted` rather than `unasked`
    (`FetchOutcome`), because a fault is fixed by a new release of the plugin,
    never by asking the holder again.
    """


class _DeadlinePassed(Exception):
    """A call into a plugin was not answered in time, or was not started because too many of its calls had not been."""


class NotAskedThisPass(Exception):
    """The pass did not ask the plugin, because its last answers on this pass were all "could not be asked".

    **Not an `ImageSearchFailure`, on purpose.** Nothing was asked, so nothing
    is recorded: acquisition passes it through untouched (it catches the
    interface's failures and records them against the source), the queue leaves
    the work exactly as it was, and the image pool answers it as this source
    not asked, writing no search. A caller outside a pass never meets it.
    """

    def __init__(self, plugin: str, after: int, *, museum: str | None = None) -> None:
        self.plugin = plugin
        super().__init__(
            f"the {museum_name(plugin, museum)} plugin was not asked on this pass: its last {after} answers on it were "
            "that it could not be asked, and the next pass asks it again"
        )


class StillAsking(NotAskedThisPass):
    """A pass did not ask the plugin about this work, because a call it owes another work is still under way.

    A `NotAskedThisPass`, so every caller leaves the work as a pass's hold-back
    leaves it: acquisition passes it through, the queue keeps the work's row as
    it was, and the image pool answers it as this source not asked, writing no
    search. Nothing is known of what the plugin holds for this work, and the
    plugin has said nothing wrong, so nothing is counted against it either.

    **When the later pass comes** is the caller's to arrange, and the refusal
    carries what it needs: `when_answered` calls back once the plugin owes
    fewer than `OWED_CALLS_PER_PLUGIN` calls, the moment its containment sees
    the owed call end (it answers, or its deadline passes). A refusal made
    without a containment to ask (the image pool's own, before it asks) has
    none, and says so by answering False.
    """

    def __init__(
        self,
        plugin: str,
        owed: int,
        *,
        when_answered: Callable[[Callable[[], None]], None] | None = None,
        museum: str | None = None,
    ) -> None:
        self.plugin = plugin
        self.owed = owed
        self._when_answered = when_answered
        Exception.__init__(
            self,
            f"the {museum_name(plugin, museum)} plugin was not asked about this work: it is still answering "
            f"{agree(owed, 'an earlier work', f'{figure(owed)} earlier works')} whose run did not wait for it, and a later "
            "pass asks it about this one",
        )

    def when_answered(self, callback: Callable[[], None]) -> bool:
        """Call `callback` once the plugin owes no call that refuses this one (now, if it already does not); whether it will.

        Called on whichever thread ends the owed call, so `callback` must not
        block: the acquisition queue's `nudge` sets an event and returns.
        """
        if self._when_answered is None:
            return False
        self._when_answered(callback)
        return True


class PassHold:
    """One pass's count of each plugin's could-not-be-asked answers in a row, and which it holds back.

    The count's one owner: `ask` and `heard` read and write it under one lock,
    so two asks of one plugin on two threads (phase 2 asks each source on a
    thread of its own, and a late answer can land while the next work is asked)
    cannot both read the count below the limit after it reached it, nor both be
    the answer that reaches it.
    """

    def __init__(self, after: int = HOLD_BACK_AFTER) -> None:
        if after < 1:
            raise ValueError(f"A pass holds a plugin back after at least one answer, not {after}.")
        self._after = after
        self._lock = threading.Lock()
        self._in_a_row: Counter[str] = Counter()
        self._not_asked: Counter[str] = Counter()

    @property
    def after(self) -> int:
        """How many could-not-be-asked answers in a row hold a plugin back."""
        return self._after

    def ask(self, plugin: str, *, museum: str | None = None) -> None:
        """Let a call to `plugin` start, or raise `NotAskedThisPass` and count the work not asked.

        `museum` is the name the plugin declares, for the sentence the refusal carries.
        """
        with self._lock:
            if self._in_a_row[plugin] < self._after:
                return
            self._not_asked[plugin] += 1
        raise NotAskedThisPass(plugin, self._after, museum=museum)

    def heard(self, plugin: str, *, unasked: bool) -> None:
        """A call to `plugin` ended: in "could not be asked", which counts, or in any other answer, which resets."""
        with self._lock:
            if unasked:
                self._in_a_row[plugin] += 1
            else:
                self._in_a_row.pop(plugin, None)

    def not_asked(self) -> Mapping[str, int]:
        """How many calls the pass did not make, by plugin: one per work it held back."""
        with self._lock:
            return dict(self._not_asked)


#: How the code that made a call in this context tells whether it has stopped
#: waiting for the answer, or None when it waits for every call it makes. Set by
#: the image pool on each of its workers (`caller_stops_waiting_when`), so a
#: plugin's calls can tell an owed call from one somebody is waiting on.
_STOPPED_WAITING: contextvars.ContextVar[Callable[[], bool] | None] = contextvars.ContextVar(
    "arrt_source_stopped_waiting", default=None
)


def caller_stops_waiting_when(stopped: Callable[[], bool]) -> None:
    """Say, for every call into a plugin this context makes from now on, how to tell that its caller stopped waiting.

    The image pool calls it on each worker, with whether its run has answered
    without that source: a call that is still inside its deadline then is
    *owed*, and `OWED_CALLS_PER_PLUGIN` bounds how many of those one plugin has.
    """
    _STOPPED_WAITING.set(stopped)


#: The pass the calling code is in, or None outside one. A context variable, so
#: a pass on one thread never holds back another's, and a worker that runs in a
#: copy of the pass's context (the image pool's, `_Calls`) counts into it.
_PASS: contextvars.ContextVar[PassHold | None] = contextvars.ContextVar("arrt_source_pass", default=None)


@contextmanager
def one_pass(*, after: int = HOLD_BACK_AFTER) -> Iterator[PassHold]:
    """Open one pass: within it, a plugin that answers "could not be asked" `after` times in a row is not asked again.

    Ends with one journal line per plugin held back, naming how many works the
    pass did not ask it about (`source.plugin_held_back`), so an outage reads as
    one line a pass and not as silence.
    """
    hold = PassHold(after)
    token = _PASS.set(hold)
    try:
        yield hold
    finally:
        _PASS.reset(token)
        for plugin, count in sorted(hold.not_asked().items()):
            log.warning(
                "source plugin %s was not asked about %d %s on this pass, after %d could-not-be-asked answers in a "
                "row; the next pass asks it again",
                plugin,
                count,
                noun(count, "work"),
                after,
                extra={"event": "source.plugin_held_back", "plugin": plugin, "not_asked": count, "after": after},
            )


def in_a_pass() -> bool:
    """Whether the calling code is within a pass (`one_pass`): what decides whether an owed call holds the next back."""
    return _PASS.get() is not None


def _pass_ask(plugin: str, museum: str | None) -> None:
    """Raise `NotAskedThisPass` when the pass the caller is in holds `plugin` back; nothing outside a pass."""
    hold = _PASS.get()
    if hold is not None:
        hold.ask(plugin, museum=museum)


def _pass_heard(plugin: str, *, unasked: bool) -> None:
    """Tell the pass the caller is in how a call to `plugin` ended; nothing outside a pass."""
    hold = _PASS.get()
    if hold is not None:
        hold.heard(plugin, unasked=unasked)


@dataclass(slots=True)
class _Count:
    """What one plugin's calls have ended in since startup."""

    faults: int = 0
    last_fault: tuple[datetime, str] | None = None
    unasked: int = 0
    last_unasked: tuple[datetime, str] | None = None
    answered: int = 0


class _Tally:
    """Per-plugin counts of faults, could-not-be-asked answers and other answers, written from many threads."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._counts: dict[str, _Count] = {}

    def _of(self, plugin: str) -> _Count:
        return self._counts.setdefault(plugin, _Count())

    def unasked(self, plugin: str, said: str) -> None:
        """A call that ended in "could not be asked", in the interface's words or past its deadline."""
        with self._lock:
            count = self._of(plugin)
            count.unasked += 1
            count.last_unasked = (self._now(), scrub(said))

    def answered(self, plugin: str) -> None:
        """A call that ended in any other answer the interface allows."""
        with self._lock:
            self._of(plugin).answered += 1

    def of(self, plugin: str) -> _Count:
        """A copy of one plugin's counts, as they stand."""
        with self._lock:
            count = self._counts.get(plugin, _Count())
            return _Count(count.faults, count.last_fault, count.unasked, count.last_unasked, count.answered)

    def fault(self, plugin: str, operation: str, exc: BaseException) -> None:
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
            count = self._of(plugin)
            count.faults += 1
            count.last_fault = (self._now(), said)


_Answer = TypeVar("_Answer")


@dataclass(slots=True)
class _Call:
    """One call on its own thread: what it ended in, and whether its caller stopped waiting for it."""

    done: threading.Event = field(default_factory=threading.Event)
    value: object = None
    error: BaseException | None = None
    finished: bool = False
    abandoned: bool = False
    #: Whether its caller stopped waiting for it (`caller_stops_waiting_when`);
    #: None for a caller that waits for every call it makes.
    stopped_waiting: Callable[[], bool] | None = None

    def owed(self) -> bool:
        """Still inside its deadline, and its caller no longer waits for it."""
        return not self.finished and not self.abandoned and self.stopped_waiting is not None and self.stopped_waiting()


def _call_back(listening: Iterable[Callable[[], None]]) -> None:
    """Tell each refused caller listening (`_Calls.when_none_owed`) that the plugin owes fewer calls; outside the lock."""
    for callback in listening:
        callback()


class _Calls:
    """One plugin's calls, each run on a thread of its own and waited for no longer than its deadline.

    **What becomes of a call that outlives its deadline.** Python cannot stop a
    thread, so the call runs on, on its own daemon thread, which holds nothing of
    the caller's: the caller has already been answered "could not be asked" and
    moved on. When the call finally returns, whatever it returned or raised is
    discarded and logged (`source.plugin_late`). It is never recorded as an
    answer, because the run or look that asked has settled without it, and an
    image arriving after that would belong to nobody. At most
    `Deadlines.stragglers` such calls per plugin run at once: past that, a new
    call is refused at once, as "could not be asked", without being started, so a
    plugin hung on every call holds a fixed number of threads rather than one
    more per work. Being daemon threads, they never hold the process open at exit.

    **What becomes of a call nobody waits for inside its deadline.** A run
    answers at its window and leaves a source still asking owed; its call runs
    on. While `OWED_CALLS_PER_PLUGIN` such calls run, a pass's call (a finder's
    search or a reader's read, within `one_pass`: `admit`) is not started, and
    raises `StillAsking`. Outside a pass nothing is refused for it, as nothing
    is held back: what multiplies calls at one museum is a pass going from
    work to work, and a question asked outside one (a look, a preview, Ask) is
    one at a time already, a look's to each source on one thread. The refused
    caller hears when the owed call ends (`StillAsking.when_answered`): each
    call that stops being owed, by answering or by passing its deadline, calls
    back whoever is listening once fewer than the bound are owed.
    """

    def __init__(self, plugin: str, limit: int, wait_for: WaitFor = _wait, *, museum: str | None = None) -> None:
        self._plugin = plugin
        #: The name the plugin declares, which every sentence about its calls carries (`museum_name`).
        self.museum = museum
        self._limit = limit
        self._wait_for = wait_for
        self._lock = threading.Lock()
        self._stragglers = 0
        #: Every call started and not yet ended, past its deadline included, by its identity.
        self._calls: dict[int, _Call] = {}
        #: Who a refusal told to wait for fewer owed calls (`when_none_owed`), each once.
        self._listening: list[Callable[[], None]] = []

    def owed(self) -> int:
        """How many of the plugin's calls are owed now: inside their deadline, their caller no longer waiting."""
        with self._lock:
            return self._owed()

    def _owed(self) -> int:
        """`owed`, under the lock its caller holds."""
        return sum(1 for call in self._calls.values() if call.owed())

    def when_none_owed(self, callback: Callable[[], None]) -> None:
        """Call `callback` once fewer than `OWED_CALLS_PER_PLUGIN` calls are owed: at once if that is so now.

        Checked and kept under the lock the calls end under, so a call ending
        between a refusal and this registration still calls back: at once, here.
        """
        with self._lock:
            if self._owed() >= OWED_CALLS_PER_PLUGIN:
                if callback not in self._listening:
                    self._listening.append(callback)
                return
        callback()

    def _answered(self) -> list[Callable[[], None]]:
        """Under the lock, after a call stopped being owed: the listeners to call back now, taken off the list."""
        if not self._listening or self._owed() >= OWED_CALLS_PER_PLUGIN:
            return []
        listening, self._listening = self._listening, []
        return listening

    def admit(self, operation: str) -> _Call:
        """A call a pass may hold back (a search or a read), counted as under way before it starts; or `StillAsking`.

        Within a pass, a call is not started while the plugin owes
        `OWED_CALLS_PER_PLUGIN` calls, and raises `StillAsking`. Checked and
        counted under one lock, so two callers (a run's worker and the queue's
        pass) cannot both see none owed and start two. The call it answers must
        be handed to `run` at once.

        Journalled here (`source.plugin_still_asking`) only for a caller that
        waits for every call it makes, the queue's pass: a run's worker (one
        that says when it stops waiting) hands the refusal to its run, which
        journals it as every refusal of a run is journalled, naming the work
        (`image_pool.still_asking`), so one refusal is one line.
        """
        pending = _Call(stopped_waiting=_STOPPED_WAITING.get())
        with self._lock:
            owed = self._owed()
            if owed < OWED_CALLS_PER_PLUGIN or _PASS.get() is None:
                self._calls[id(pending)] = pending
                return pending
            under_way = len(self._calls)
        refused = StillAsking(self._plugin, owed, when_answered=self.when_none_owed, museum=self.museum)
        if pending.stopped_waiting is not None:
            raise refused
        log.info(
            "source plugin %s was not asked during %s on this pass: %d of its calls %s owed to a run that did not "
            "wait; the work is left as it was",
            self._plugin,
            operation,
            owed,
            agree(owed, "is", "are"),
            extra={
                "event": "source.plugin_still_asking",
                "plugin": self._plugin,
                "operation": operation,
                "owed": owed,
                "under_way": under_way,
            },
        )
        raise refused

    def run(self, operation: str, deadline: float, call: Callable[[], _Answer], *, admitted: _Call | None = None) -> _Answer:
        """What `call` answers, or raises, if it does so within `deadline` seconds; else `_DeadlinePassed`.

        `admitted` is the call `admit` counted, for a call a pass may hold back.
        """
        pending = admitted if admitted is not None else _Call(stopped_waiting=_STOPPED_WAITING.get())
        with self._lock:
            if self._stragglers >= self._limit:
                self._calls.pop(id(pending), None)
                raise _DeadlinePassed(
                    f"it was not asked, because {self._stragglers} of its earlier calls are still running past their deadline"
                )
            self._calls[id(pending)] = pending
        started = time.monotonic()
        # The caller's context, so what the plugin logs still carries the run it works for.
        context = contextvars.copy_context()

        def work() -> None:
            try:
                pending.value = context.run(call)
            except BaseException as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- carried to the caller's thread
                pending.error = exc
            with self._lock:
                pending.finished = True
                self._calls.pop(id(pending), None)
                late = pending.abandoned
                if late:
                    self._stragglers -= 1
                answered = self._answered()
            pending.done.set()
            _call_back(answered)
            if late:
                ended = "answered" if pending.error is None else f"raised {describe_exception(pending.error)}"
                log.warning(
                    "source plugin %s %s during %s %.0f seconds after it was asked, past its deadline; discarded",
                    self._plugin,
                    ended,
                    operation,
                    time.monotonic() - started,
                    extra={"event": "source.plugin_late", "plugin": self._plugin, "operation": operation},
                )

        self._begin(work, pending)
        if not self._wait_for(pending.done, deadline):
            with self._lock:
                # It may have finished between the wait ending and the lock, and
                # then its answer stands.
                if not pending.finished:
                    pending.abandoned = True
                    self._stragglers += 1
                # Past its deadline it is a straggler, and no longer owed.
                answered = self._answered() if pending.abandoned else []
            _call_back(answered)
            if pending.abandoned:
                raise _DeadlinePassed(f"it did not answer within {deadline:g} seconds")
        if pending.error is not None:
            raise pending.error
        return pending.value  # type: ignore[return-value]  # what `call` returned

    def _begin(self, work: Callable[[], None], pending: _Call) -> None:
        """Start `work` on a daemon thread of its own; a call whose thread never started is no longer counted."""
        try:
            threading.Thread(target=work, name=f"source-plugin-{self._plugin}", daemon=True).start()
        except BaseException:
            # Never started, so never ends: still counted as under way, it would
            # read as owed for the life of the process.
            with self._lock:
                self._calls.pop(id(pending), None)
            raise


class _Said:
    """What a finder handed over before it failed, handed on as the finder handed it: yielded, then the failure raised.

    The pool keeps what a source said before it failed (`SourceAnswer`), and
    reads it by iterating. A finder whose generator yields an image and then
    raises has said that image, and collecting the answer whole inside the
    containment, as it once was, dropped it.
    """

    def __init__(self, said: tuple[FoundImage | FoundPage, ...], failure: Exception) -> None:
        self._said = said
        self._failure = failure

    def __iter__(self) -> Iterator[FoundImage | FoundPage]:
        yield from self._said
        raise self._failure


class _Heard:
    """What a finder has yielded so far, each checked: added to by the call's thread, read by its caller's."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._found: list[FoundImage | FoundPage] = []

    def add(self, found: FoundImage | FoundPage) -> None:
        with self._lock:
            self._found.append(found)

    def so_far(self) -> tuple[FoundImage | FoundPage, ...]:
        """Everything heard until now. Taken once, when the caller answers, so what a call
        yields past its deadline lands after the copy and reaches nobody."""
        with self._lock:
            return tuple(self._found)


def _check_found(found: object, plugin: str, *, pages_only: bool) -> FoundImage | FoundPage:
    """One thing a finder answered, checked.

    Each image is recorded under its own `provider`, and previews and fetches are
    routed back by it, so an image under another plugin's name would be stored
    and fetched as that plugin's. A page carries no name, because nothing is
    recorded under one. A finder that declared it offers pages only may not
    answer an image: the pool does not count it as having answered, so its image
    would sit beside a work left waiting as if no source could be asked.

    The dimensions are what a work's size on the wall is computed from: a width
    given as a string passed the type check alone and then failed the run in
    phase 2, outside this containment. The texts are bounded for the reason a
    museum's name is (`_museum_of`).
    """
    if isinstance(found, FoundPage):
        return found
    if not isinstance(found, FoundImage):
        raise _InterfaceBreach(f"find_images answered a {type(found).__name__} among its images")
    if pages_only:
        raise _InterfaceBreach("find_images answered a FoundImage from a finder that declares offers_images = False")
    if found.provider != plugin:
        raise _InterfaceBreach(
            f"find_images answered an image recorded under {found.provider!r}; a plugin's images "
            f"are recorded under its own name, {plugin!r}"
        )
    _check_image_fields(found)
    return found


def _check_image_fields(found: FoundImage) -> None:
    """An image's sizes and words, checked: positive whole numbers or `None`, and bounded text."""
    for name, size in (("estimated_width", found.estimated_width), ("estimated_height", found.estimated_height)):
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size <= 0):
            raise _InterfaceBreach(f"find_images answered an image whose {name} is {size!r}, not a positive int or None")
    for name, text in (("title", found.title), ("artist", found.artist)):
        if text is None and name == "artist":
            continue
        if not isinstance(text, str):
            raise _InterfaceBreach(f"find_images answered an image whose {name} is a {type(text).__name__}, not text")
        if len(text) > ANSWER_TEXT_MAX_CHARS:
            raise _InterfaceBreach(
                f"find_images answered an image whose {name} is {len(text):,} characters, past {ANSWER_TEXT_MAX_CHARS:,}"
            )


def _preview(answer: object, max_bytes: int) -> bytes | None:
    """A preview, checked: bytes or `None`, and no more bytes than this deployment's ceiling.

    The finder was told to stop reading at the ceiling (`Finder.fetch_preview`),
    and one that did not has already held the whole body in memory; refusing it
    here keeps it from going on into the picture store and Pillow.
    """
    if answer is not None and not isinstance(answer, bytes):
        raise _InterfaceBreach(f"fetch_preview answered a {type(answer).__name__}, not bytes or None")
    if answer is not None and len(answer) > max_bytes:
        raise _InterfaceBreach(
            f"fetch_preview answered {len(answer):,} bytes, past this deployment's preview_max_bytes of {max_bytes:,}"
        )
    return answer


def _locator(answer: object) -> FetchLocator:
    """A reader's answer, checked for its type and the length of its reason.

    Its words are otherwise left as they are here: a `none` reason and a URL both
    reach anyone only through acquisition, which scrubs them where it records and
    journals them, and a URL to fetch must stay whole.
    """
    if not isinstance(answer, FetchLocator):
        raise _InterfaceBreach(f"read answered a {type(answer).__name__}, not a FetchLocator")
    reason = answer.reason
    if reason is not None and (not isinstance(reason, str) or len(reason) > ANSWER_TEXT_MAX_CHARS):
        raise _InterfaceBreach(f"read answered a reason that is not text of at most {ANSWER_TEXT_MAX_CHARS:,} characters")
    return answer


def _past_deadline(plugin: str, museum: str | None, operation: str, passed: _DeadlinePassed, tally: _Tally) -> str:
    """Record a call past its deadline against the plugin, say so in the journal, and return the words to answer with."""
    said = f"the {museum_name(plugin, museum)} plugin could not be asked: {passed}"
    tally.unasked(plugin, said)
    log.warning(
        "source plugin %s, during %s: %s; recorded as could not be asked",
        plugin,
        operation,
        passed,
        extra={"event": "source.plugin_deadline", "plugin": plugin, "operation": operation},
    )
    return said


def _scrubbed[Failure: Exception](exc: Failure, kind: type[Failure]) -> Failure:
    """`exc` itself when its message carries no query string; else a `kind` saying the same without one.

    `_reraise_scrubbed`'s rule, for a failure raised later rather than now (`_Said`).
    """
    cleaned = scrub(str(exc))
    if cleaned == str(exc):
        return exc
    replacement = kind(cleaned)
    replacement.__suppress_context__ = True
    return replacement


def _heard_failure(exc: ImageSearchFailure, plugin: str, tally: _Tally) -> ImageSearchFailure:
    """A finder's or reader's own `ImageSearchFailure`, counted, and scrubbed as it passes on.

    `LinkGone` (1.6) is the holder's answer that the page is gone, so it counts
    as answered and keeps its type; any other is "could not be asked". Each is
    itself when its message carries no query string, else one of its kind
    saying the same without one (`_scrubbed`).
    """
    if isinstance(exc, LinkGone):
        tally.answered(plugin)
        return _scrubbed(exc, LinkGone)
    tally.unasked(plugin, str(exc))
    return _scrubbed(exc, ImageSearchFailure)


def _groups(answer: object) -> tuple[OfferedGroup, ...]:
    if isinstance(answer, str | bytes) or not isinstance(answer, Iterable):
        raise _InterfaceBreach(f"browse answered a {type(answer).__name__}, not a list of OfferedGroup")
    groups = tuple(answer)
    if not all(isinstance(group, OfferedGroup) for group in groups):
        raise _InterfaceBreach("browse answered something other than OfferedGroup among its groups")
    return groups


class _ContainedFinder:
    """A plugin's finder, with anything outside its interface, or past its deadline, turned into "could not be asked"."""

    def __init__(
        self,
        inner: Finder,
        plugin: str,
        tally: _Tally,
        *,
        calls: _Calls,
        deadlines: Deadlines,
        preview_max_bytes: int,
    ) -> None:
        self._inner = inner
        self._plugin = plugin
        self._tally = tally
        self._calls = calls
        self._deadlines = deadlines
        self._preview_max_bytes = preview_max_bytes
        #: Carried from the plugin's finder, so the pool can tell a finder of
        #: pages from one of images through the containment.
        self.offers_images = offers_images(inner)

    @property
    def provider(self) -> str:
        return self._plugin

    @property
    def museum(self) -> str | None:
        """The name the plugin declares for itself, or `None` when it declares none."""
        return self._calls.museum

    @property
    def deadline_seconds(self) -> float:
        """How long `find_images` is waited for: what the pool's own backstop is set past."""
        return self._deadlines.finder

    def owing(self) -> int:
        """How many of the plugin's calls are owed now (`OWED_CALLS_PER_PLUGIN`): what a run reads before it asks."""
        return self._calls.owed()

    def find_images(self, query: ImageQuery) -> Iterable[FoundImage | FoundPage]:
        """The finder's answer, checked; or, when it failed after saying something, that, then the failure.

        Eager when nothing was said: a failure with nothing before it is raised
        here, as it always was, and only an answer that has something to hand
        over before its failure is handed over to be iterated.
        """
        # Before anything starts, and outside the containment below: a pass not
        # asking the plugin is no answer of the plugin's, and no fault either.
        _pass_ask(self._plugin, self._calls.museum)
        heard = _Heard()
        pages_only = not self.offers_images

        def ask() -> None:
            answer = self._inner.find_images(query)
            if isinstance(answer, str | bytes) or not isinstance(answer, Iterable):
                raise _InterfaceBreach(f"find_images answered a {type(answer).__name__}, not a list of FoundImage")
            for found in answer:
                heard.add(_check_found(found, self._plugin, pages_only=pages_only))

        # Outside the containment below, as the pass's hold-back is: a call not
        # started because the plugin still owes another work an answer is no
        # answer of the plugin's, so nothing counts or resets.
        admitted = self._calls.admit("find_images")
        try:
            self._calls.run("find_images", self._deadlines.finder, ask, admitted=admitted)
        except _DeadlinePassed as passed:
            _pass_heard(self._plugin, unasked=True)
            failure: Exception = ImageSearchFailure(
                _past_deadline(self._plugin, self._calls.museum, "find_images", passed, self._tally)
            )
        # The interface's answers that are not a list, passed on as themselves
        # with their message scrubbed. One clause each rather than a tuple,
        # because the formatter writes a bare tuple in a form Python 3.12 cannot
        # parse, and the root suite's guards parse this file under 3.12.
        except ImageSearchFailure as exc:
            _pass_heard(self._plugin, unasked=not isinstance(exc, LinkGone))
            failure = _heard_failure(exc, self._plugin, self._tally)
        except ImageQueryUnanswerable as exc:
            _pass_heard(self._plugin, unasked=False)
            self._tally.answered(self._plugin)
            failure = _scrubbed(exc, ImageQueryUnanswerable)
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a plugin fault must not fail a run
            # Nothing it said is kept: a plugin answering outside its interface
            # has said nothing that can be trusted.
            # Neither counts nor resets the pass's count: a fault is fixed by a
            # new release of the plugin, and says nothing of whether it answers.
            self._tally.fault(self._plugin, "find_images", exc)
            raise PluginFaulted(
                f"the {museum_name(self._plugin, self._calls.museum)} plugin faulted: {type(exc).__name__}"
            ) from exc
        else:
            _pass_heard(self._plugin, unasked=False)
            self._tally.answered(self._plugin)
            return heard.so_far()
        said = heard.so_far()
        if not said:
            raise failure
        return _Said(said, failure)

    def fetch_preview(self, url: str) -> bytes | None:
        try:
            return self._calls.run(
                "fetch_preview",
                self._deadlines.preview,
                lambda: _preview(self._inner.fetch_preview(url), self._preview_max_bytes),
            )
        except _DeadlinePassed as passed:
            # None is the interface's failed preview: a card without its picture.
            _past_deadline(self._plugin, self._calls.museum, "fetch_preview", passed, self._tally)
            return None
        except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- None is the interface's failed preview
            self._tally.fault(self._plugin, "fetch_preview", exc)
            return None


class _ContainedReader:
    """A plugin's reader, with anything outside its interface, or past its deadline, turned into "could not be asked"."""

    def __init__(self, inner: Reader, plugin: str, tally: _Tally, *, calls: _Calls, deadlines: Deadlines) -> None:
        self._inner = inner
        self._plugin = plugin
        self._tally = tally
        self._calls = calls
        self._deadlines = deadlines

    def read(self, url: str) -> FetchLocator:
        # Before anything starts, as the finder's: see `_ContainedFinder.find_images`.
        _pass_ask(self._plugin, self._calls.museum)
        # As the finder's: not started while the plugin owes another work an answer.
        admitted = self._calls.admit("read")
        try:
            locator = self._calls.run("read", self._deadlines.reader, lambda: _locator(self._inner.read(url)), admitted=admitted)
        except _DeadlinePassed as passed:
            _pass_heard(self._plugin, unasked=True)
            raise ImageSearchFailure(_past_deadline(self._plugin, self._calls.museum, "read", passed, self._tally)) from None
        except ImageSearchFailure as exc:
            _pass_heard(self._plugin, unasked=not isinstance(exc, LinkGone))
            # As `_reraise_scrubbed`: itself when clean, else its scrubbed twin `from None`.
            heard = _heard_failure(exc, self._plugin, self._tally)
            if heard is exc:
                raise
            raise heard from None
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- recorded against the source instead
            self._tally.fault(self._plugin, "read", exc)
            raise PluginFaulted(
                f"the {museum_name(self._plugin, self._calls.museum)} plugin faulted: {type(exc).__name__}"
            ) from exc
        _pass_heard(self._plugin, unasked=False)
        self._tally.answered(self._plugin)
        return locator


class _ContainedCollection:
    """A plugin's collection, with anything outside its interface, or past its deadline, turned into a browse failure."""

    def __init__(self, inner: CollectionBrowse, plugin: str, tally: _Tally, *, calls: _Calls, deadlines: Deadlines) -> None:
        self._inner = inner
        self._plugin = plugin
        self._tally = tally
        self._calls = calls
        self._deadlines = deadlines

    @property
    def provider(self) -> str:
        return self._plugin

    def browse(self, queries: Sequence[BrowseQuery], *, per_query: int) -> Sequence[OfferedGroup]:
        try:
            groups = self._calls.run(
                "browse", self._deadlines.browse, lambda: _groups(self._inner.browse(queries, per_query=per_query))
            )
        except _DeadlinePassed as passed:
            raise CollectionBrowseFailure(
                _past_deadline(self._plugin, self._calls.museum, "browse", passed, self._tally)
            ) from None
        except CollectionBrowseFailure as exc:
            self._tally.unasked(self._plugin, str(exc))
            _reraise_scrubbed(exc, CollectionBrowseFailure)
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a plugin fault must not fail a run
            self._tally.fault(self._plugin, "browse", exc)
            raise CollectionBrowseFailure(
                f"the {museum_name(self._plugin, self._calls.museum)} plugin faulted: {type(exc).__name__}"
            ) from exc
        self._tally.answered(self._plugin)
        return groups


class _Containment:
    """What every wrapper of one roster shares: the counts, the deadlines, the preview ceiling, and each plugin's calls."""

    def __init__(
        self,
        tally: _Tally,
        deadlines: Deadlines,
        preview_max_bytes: int,
        *,
        declared: Mapping[str, Deadlines] | None = None,
        museums: Mapping[str, str] | None = None,
        wait_for: WaitFor = _wait,
    ) -> None:
        self.tally = tally
        self._deadlines = deadlines
        #: Each plugin's own deadlines, where it declared any (`declared_deadlines`).
        self._declared = dict(declared or {})
        #: The museum each plugin declares (interface 1.4), where it declares one.
        self._museums = dict(museums or {})
        self._preview_max_bytes = preview_max_bytes
        self._wait_for = wait_for
        #: Per plugin, not per part, so a plugin hung in its reader and its finder
        #: alike holds no more threads than one hung in either.
        self._calls: dict[str, _Calls] = {}

    def _calls_of(self, plugin: str) -> _Calls:
        return self._calls.setdefault(
            plugin, _Calls(plugin, self._deadlines.stragglers, self._wait_for, museum=self._museums.get(plugin))
        )

    def _deadlines_of(self, plugin: str) -> Deadlines:
        return self._declared.get(plugin, self._deadlines)

    def finder(self, inner: Finder, plugin: str) -> _ContainedFinder:
        return _ContainedFinder(
            inner,
            plugin,
            self.tally,
            calls=self._calls_of(plugin),
            deadlines=self._deadlines_of(plugin),
            preview_max_bytes=self._preview_max_bytes,
        )

    def reader(self, inner: Reader, plugin: str) -> _ContainedReader:
        deadlines = self._deadlines_of(plugin)
        return _ContainedReader(inner, plugin, self.tally, calls=self._calls_of(plugin), deadlines=deadlines)

    def collection(self, inner: CollectionBrowse, plugin: str) -> _ContainedCollection:
        deadlines = self._deadlines_of(plugin)
        return _ContainedCollection(inner, plugin, self.tally, calls=self._calls_of(plugin), deadlines=deadlines)


def _not_loaded(plugin: str, museum: str | None, reason: str | None) -> str:
    """Why a URL this plugin claims cannot be read here, naming the museum rather than the id."""
    return f"the {museum_name(plugin, museum)} source plugin is installed and not loaded: {reason}"


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
        tally: _Tally,
        unknowable: Mapping[str, str] | None = None,
        identities: Mapping[str, PluginIdentity] | None = None,
    ) -> None:
        self._identities = dict(identities or {})
        self._finders = tuple(finders)
        self._collection = collection
        self._claimants = tuple(claimants)
        self._states = tuple(states)
        self._tally = tally
        #: Pairs of plugins already said to claim one URL, so each pair is said once.
        self._overlaps: set[tuple[str, str]] = set()
        self._overlaps_lock = threading.Lock()
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
        deadlines: Deadlines = DEFAULT_DEADLINES,
        preview_max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
        museums: Mapping[str, str] | None = None,
    ) -> SourceRoster:
        """A roster from parts in hand, without entry points: for tests, and for hand-assembled sources.

        Each part is named as a plugin of its own: a finder by its `provider`, a
        collection likewise, and a reader by its key, which carries the claims that
        route URLs to it. `unavailable` names plugins that claim URLs and declined,
        each with its reason, and `unknowable` plugins that failed before their
        claims could be read. Every part is contained exactly as a loaded plugin's
        is, deadlines included.
        """
        tally = _Tally(now)
        museums = dict(museums or {})
        contain = _Containment(tally, deadlines, preview_max_bytes, museums=museums)
        readers = dict(readers or {})
        unavailable = dict(unavailable or {})
        names = [finder.provider for finder in finders]
        if collection is not None:
            names.append(collection.provider)
        names.extend(readers)
        return cls(
            finders=[contain.finder(finder, finder.provider) for finder in finders],
            collection=None if collection is None else contain.collection(collection, collection.provider),
            claimants=[
                *(_Claimant(name, claims, contain.reader(reader, name), None) for name, (claims, reader) in readers.items()),
                *(
                    _Claimant(name, claims, None, _not_loaded(name, museums.get(name), reason))
                    for name, (claims, reason) in unavailable.items()
                ),
            ],
            states=[
                *((name, PluginState.LOADED, None) for name in dict.fromkeys(names)),
                *((name, PluginState.DECLINED, reason) for name, (_claims, reason) in unavailable.items()),
                *((name, PluginState.FAILED, reason) for name, reason in (unknowable or {}).items()),
            ],
            tally=tally,
            unknowable=unknowable,
            identities={
                name: PluginIdentity(
                    museum=museums.get(name),
                    provides=_provides(
                        next((f for f in finders if f.provider == name), None),
                        readers[name][1] if name in readers else None,
                        collection if collection is not None and collection.provider == name else None,
                    ),
                )
                for name in dict.fromkeys(names)
            },
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

        Every claimant is asked, so that two plugins claiming one URL are said
        out loud (`source.claims_overlap`, once per pair) rather than kept apart
        by convention alone: the second never reads a URL the first claims, and
        a stored source it recorded would be read by the other's reader.

        `provider`, the name a stored source was recorded under, is consulted only
        when no claimant claims the URL and that name is a plugin whose claims could
        not be read. Its own rows are then a deployment fault naming it, as a
        declined plugin's are, rather than a fetch of a page only it can read.
        """
        chosen: _Claimant | None = None
        for claimant in self._claimants:
            try:
                claimed = bool(claimant.claims(url))
            except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- a raising check claims nothing
                self._tally.fault(claimant.name, "claims", exc)
                claimed = False
            if not claimed:
                continue
            if chosen is None:
                chosen = claimant
            else:
                self._overlap(chosen.name, claimant.name, url)
        if chosen is not None:
            return Route(
                plugin=chosen.name,
                reader=chosen.reader,
                unavailable=chosen.unavailable,
                museum=self._identities.get(chosen.name, PluginIdentity()).museum,
            )
        if provider is not None and provider in self._unknowable:
            return Route(
                plugin=provider,
                unavailable=(
                    f"the {museum_name(provider)} source plugin is installed and could not be loaded: "
                    f"{self._unknowable[provider]}"
                ),
            )
        return Route()

    def _overlap(self, first: str, second: str, url: str) -> None:
        """Say once per pair that two plugins claim one URL, naming both and the one that reads it."""
        with self._overlaps_lock:
            if (first, second) in self._overlaps:
                return
            self._overlaps.add((first, second))
        log.warning(
            "source plugins %s and %s both claim %s; %s reads it, being first in the order, and %s never will",
            first,
            second,
            scrub(url),
            first,
            second,
            extra={"event": "source.claims_overlap", "plugin": first, "other": second},
        )

    def observe(self) -> tuple[PluginReading, ...]:
        """Every installed plugin, now, with its faults and could-not-be-asked answers since startup."""
        readings = []
        for name, state, reason in self._states:
            count = self._tally.of(name)
            readings.append(
                PluginReading(
                    name=name,
                    state=state,
                    reason=reason,
                    faults=count.faults,
                    last_fault_at=None if count.last_fault is None else count.last_fault[0],
                    last_fault=None if count.last_fault is None else count.last_fault[1],
                    identity=self._identities.get(name, PluginIdentity()),
                    unasked=count.unasked,
                    last_unasked_at=None if count.last_unasked is None else count.last_unasked[0],
                    last_unasked=None if count.last_unasked is None else count.last_unasked[1],
                    answered=count.answered,
                )
            )
        return tuple(readings)


def load_sources(
    context: SourceContext,
    *,
    order: Sequence[str] = DEFAULT_SOURCE_ORDER,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    data_root: Path | None = None,
    deadlines: Deadlines = DEFAULT_DEADLINES,
    wait_for: WaitFor = _wait,
) -> SourceRoster:
    """Load every installed plugin, and say what became of each.

    `order` names plugins most preferred first; plugins it does not name follow,
    by name. `entry_points` defaults to what this interpreter has installed in
    `ENTRY_POINT_GROUP`, and is a parameter so the loader can be tested without
    installing a distribution per case. `data_root` is where plugins keep files:
    each is handed `data_root / <its name>` as `SourceContext.data_dir`
    (`_own_directory`). `deadlines` is how long each call into a loaded plugin is
    waited for unless the plugin declares its own (`SourcePlugin.deadlines`); the
    wiring takes the named defaults. `wait_for` is how the waiting is done, a
    parameter only so a test can run a long deadline on simulated time.
    """
    found = list(importlib.metadata.entry_points(group=ENTRY_POINT_GROUP) if entry_points is None else entry_points)
    tally = _Tally(now)
    states: dict[str, tuple[PluginState, str | None]] = {}
    parts: dict[str, SourceParts] = {}
    plugins: dict[str, SourcePlugin] = {}
    origins: dict[str, tuple[str | None, str | None]] = {}
    for entry in found:
        if entry.name in states:
            # Two distributions registering one name would record their images
            # under one provider, and every stored row would then belong to
            # whichever loaded last. Neither is loaded.
            clash = "two installed distributions register this name; neither is loaded"
            states[entry.name] = (PluginState.FAILED, clash)
            parts.pop(entry.name, None)
            plugins.pop(entry.name, None)
            # Neither distribution is this plugin's, so neither is named as its origin.
            origins[entry.name] = (None, None)
            continue
        origins[entry.name] = _origin(entry)
        # Before the factory runs, so a factory that hangs leaves its name in the
        # journal rather than a startup that simply stops.
        log.info("loading source plugin %s", entry.name, extra={"event": "source.loading", "plugin": entry.name})
        plugin, loaded = _load_one(entry, replace(context, data_dir=_own_directory(data_root, entry.name)))
        if plugin is not None:
            plugins[entry.name] = plugin
        if isinstance(loaded, SourceParts):
            states[entry.name] = (PluginState.LOADED, None)
            parts[entry.name] = loaded
        elif isinstance(loaded, Declined):
            states[entry.name] = (PluginState.DECLINED, scrub(loaded.reason))
        else:
            states[entry.name] = (PluginState.FAILED, loaded)

    # Each loaded plugin's deadlines: a declaration that could not load has already left it out (`_load_one`).
    declared = {name: own for name in parts if isinstance(own := declared_deadlines(plugins[name], deadlines), Deadlines)}
    museums = {name: museum for name, plugin in plugins.items() if (museum := _museum_of(name, plugin)) is not None}
    declare_museums(museums)
    contain = _Containment(tally, deadlines, context.preview_max_bytes, declared=declared, museums=museums, wait_for=wait_for)

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

    finders = [contain.finder(finder, n) for n in ranked if n in parts and (finder := parts[n].finder) is not None]
    collections = [contain.collection(browse, n) for n in ranked if n in parts and (browse := parts[n].collection) is not None]
    claimants = [
        _Claimant(
            name=n,
            claims=claims,
            reader=(contain.reader(reader, n) if n in parts and (reader := parts[n].reader) is not None else None),
            unavailable=None if n in parts else _not_loaded(n, museums.get(n), states[n][1]),
        )
        for n in ranked
        if n in plugins and (claims := plugins[n].claims) is not None
    ]
    return SourceRoster(
        finders=finders,
        collection=collections[0] if collections else None,
        claimants=claimants,
        states=[(name, *states[name]) for name in ranked],
        tally=tally,
        unknowable={n: states[n][1] or "" for n in ranked if n not in plugins and states[n][0] is PluginState.FAILED},
        identities={
            n: PluginIdentity(
                distribution=origins[n][0],
                version=origins[n][1],
                api_major=plugins[n].api_major if n in plugins else None,
                provides=() if n not in parts else _provides(parts[n].finder, parts[n].reader, parts[n].collection),
                museum=museums.get(n),
            )
            for n in ranked
        },
    )


#: Long enough for "Solomon R. Guggenheim Museum and Foundation" with room to
#: spare; a name past it is a paragraph, which every heading and table cell that
#: names a source would then carry.
_MUSEUM_MAX_CHARS: Final = 120


def _museum_of(name: str, plugin: SourcePlugin) -> str | None:
    """The museum a plugin declares, if it is one short line of text; else `None`, said once.

    Refusing it costs the plugin only its name: it is still loaded, and named by
    its id, as one that declares nothing is.
    """
    museum = getattr(plugin, "museum", None)
    if museum is None:
        return None
    if isinstance(museum, str) and museum.strip() and len(museum) <= _MUSEUM_MAX_CHARS and museum.isprintable():
        return museum.strip()
    log.warning(
        "source plugin %s declares a museum name that is not one short line of text; it is named by its id",
        name,
        extra={"event": "source.museum_refused", "plugin": name},
    )
    return None


def _origin(entry: importlib.metadata.EntryPoint) -> tuple[str | None, str | None]:
    """The distribution that registers an entry point, and its version; `None` for one registered by hand.

    Read from the installed metadata alone, before the plugin's code runs, so a
    plugin that cannot be imported still says which package it came from.
    """
    # `getattr`, because the loader is also handed entry points built by hand,
    # which carry no distribution at all.
    dist = getattr(entry, "dist", None)
    if dist is None:
        return None, None
    try:
        name, version = dist.metadata["Name"], dist.version
    # A package's metadata is foreign: a corrupt one costs its plugin's origin, never startup.
    except Exception:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- a corrupt package costs only its origin
        log.warning(
            "could not read the package that registers source plugin %s",
            entry.name,
            extra={"event": "source.origin_unread", "plugin": entry.name},
        )
        return None, None
    return (name if isinstance(name, str) else None), (version if isinstance(version, str) else None)


def _provides(finder: Finder | None, reader: Reader | None, collection: CollectionBrowse | None) -> tuple[PluginPart, ...]:
    """What a plugin's parts provide, in the order the guide lists the parts."""
    provided = []
    if finder is not None:
        provided.append(PluginPart.FINDS_IMAGES if offers_images(finder) else PluginPart.FINDS_PAGES)
    if reader is not None:
        provided.append(PluginPart.READS)
    if collection is not None:
        provided.append(PluginPart.BROWSES)
    return tuple(provided)


#: A plugin name that is one plain path segment, and so names one directory
#: under the data root. An entry point's name is any string a distribution
#: chooses, and `../catalogue` must not reach outside it. Its first character
#: is a letter or a digit, so neither `.` nor `..` is one.
_PLAIN_SEGMENT: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")


def _own_directory(data_root: Path | None, name: str) -> Path | None:
    """The directory this plugin may keep files in, or None when it gets none.

    None when the deployment gives no root, and when the name is not one plain
    path segment, so that no plugin is handed a directory that is not its own.
    """
    if data_root is None:
        return None
    if not _PLAIN_SEGMENT.fullmatch(name):
        log.warning(
            "source plugin %s is given no directory: its name is not one plain path segment",
            name,
            extra={"event": "source.no_directory", "plugin": name},
        )
        return None
    return data_root / name


def _load_one(  # noqa: PLR0911 -- one return per way a plugin can fail to load, each named
    entry: importlib.metadata.EntryPoint, context: SourceContext
) -> tuple[SourcePlugin | None, SourceParts | Declined | str]:
    """The plugin object, if one was got, and its parts, its decline, or why it could not be loaded."""
    try:
        plugin = entry.load()
    except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- an unimportable plugin is left out, named
        return None, _unimportable(exc)
    if not isinstance(plugin, SourcePlugin):
        return None, f"its entry point names a {type(plugin).__name__}, not a SourcePlugin"
    refused = _version_refusal(plugin)
    if refused is not None:
        return plugin, refused
    try:
        answer = plugin.create(context)
    except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- a raising factory is left out, and named
        return plugin, f"its factory raised {describe_exception(exc)}"
    if isinstance(answer, Declined):
        return plugin, answer
    if not isinstance(answer, SourceParts):
        return plugin, f"its factory answered a {type(answer).__name__}, not SourceParts or Declined"
    try:
        breach = _breach(entry.name, plugin, answer)
    except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- raising parts are left out, and named
        return plugin, f"its parts raised while being checked: {describe_exception(exc)}"
    return plugin, answer if breach is None else breach


def _unimportable(exc: Exception) -> str:
    """Why a plugin could not be imported, and, for a keyword this Arrt's types do not take, what that may mean.

    A plugin passing a field from a newer interface meets this rather than
    `_version_refusal`, because `SourcePlugin` refuses the keyword at import,
    before Arrt can read the minor the plugin declares beside it.
    """
    reason = f"it could not be imported: {describe_exception(exc)}"
    if isinstance(exc, TypeError) and "unexpected keyword argument" in str(exc):
        major, minor = API_VERSION
        reason += f"; it may need a newer Arrt than this one, which provides source interface {major}.{minor}"
    return reason


def _version_refusal(plugin: SourcePlugin) -> str | None:
    """Why a plugin's interface version cannot load here, or `None` when it can.

    A plugin needing a newer minor is refused rather than loaded: one reading a
    field this Arrt does not have would fault on every call instead of being
    named once, at startup.
    """
    major, minor = API_VERSION
    if plugin.api_major != major:
        return f"it was written for source interface {plugin.api_major}, and this Arrt provides {major}.{minor}"
    needs = getattr(plugin, "api_minor", 0)
    if isinstance(needs, bool) or not isinstance(needs, int) or needs < 0:
        return f"it declares an interface minor of {needs!r}, which is not a whole number"
    if needs > minor:
        return f"it needs source interface {major}.{needs}, and this Arrt is {major}.{minor}"
    declared = declared_deadlines(plugin, DEFAULT_DEADLINES)
    return declared if isinstance(declared, str) else None


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
