"""The curation plane's log shape, and the run id every line inside a run carries.

**Failure here is silent by construction**: the only feedback channel the
household has is a picture on a wall, and a stalled loader is indistinguishable
from a working one showing a static image. Logs are the primary signal, which
makes their shape load-bearing rather than cosmetic.

**One line is one JSON object.** A discovery run fans one curator action out
across minutes and many external calls, and reconstructing it from prose means
grepping for a substring and hoping the message text has not been reworded. A
machine-readable line means `journalctl | jq 'select(.run_id == "...")'` returns
the run and nothing else. Nothing is exported anywhere: there is no collector, no
metrics store and no tracing backend, and an exporter with no collector is
machinery pretending to be observability.

**`run_id` is bound, not passed.** It rides a context variable and is stamped
onto every record by a filter, so a module that logs inside a run carries the
correlation key without knowing it exists. The alternative — threading the id
into every call site that might log — is a discipline, and a discipline is
exactly what one forgotten call site defeats. The lines that go missing that way
are the ones logged from deep inside a failure, which are the ones worth having.

**No secret may ever reach a line here.** This repository is public and log
excerpts are what gets pasted into an issue. Nothing in this module reads the
environment or renders a configuration object; what is logged is what a call site
passed. **Every URL's query string is cut from the finished line**, message,
fields and traceback alike, because that is where a paid source's key travels,
and a source plugin's URLs and error text reach lines this repository's authors
never wrote (`source-plugins.md`). Cutting it here, once, covers every call site,
including the next one. Prompts, intents and model output are not secrets and may be logged
freely — they carry artwork metadata and curatorial intent, nothing personal.
"""

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Final

#: The correlation key for the run currently being worked on, if any. A context
#: variable rather than a thread local because it must survive both — the run
#: lifecycle runs on a worker thread while surfaces answer on others, and a
#: context variable is the one mechanism that behaves under both.
_RUN_ID: ContextVar[str | None] = ContextVar("curation_run_id", default=None)

#: The work a look is asking the image sources about (`library/services/look.py`),
#: bound as `run_id` is and for its reason: a look fans one page's question out
#: across every source, on threads of its own, and its lines are found by this.
_LOOK_QID: ContextVar[str | None] = ContextVar("curation_look_qid", default=None)

#: What every line carries. Ordered so a raw line reads left to right the way a
#: person scans one: when, how bad, where from, what happened.
_ALWAYS: Final[tuple[str, ...]] = ("time", "level", "logger", "message")

#: `LogRecord`'s own attributes. Anything a call site passes through `extra=`
#: lands on the record beside these, and the only way to tell the two apart is to
#: know the built-in set — so it is written out rather than guessed at. Built
#: from a real record so a Python release adding an attribute cannot turn it into
#: a field that appears in every log line.
_BUILT_IN: Final[frozenset[str]] = frozenset(
    vars(logging.LogRecord(name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None))
) | {"message", "asctime", "taskName"}


#: A URL's query string, which is where a paid source's key usually travels.
#: The address and the query each run to whitespace, `"`, `<` or `>`, the
#: characters an HTTP client always encodes; the address also stops at `?` and
#: `#`. Neither stops at `'` or `\\`, which httpx leaves in a path and a query as
#: they are (`/artists/O'Keeffe`, `?q=O'Keeffe&key=…`): a cut that ended there
#: kept the rest of the URL, key and all. Running past a closing quote costs only
#: that quote. `tests/unit/test_logs.py` checks every character httpx leaves
#: unencoded, read from httpx itself.
_QUERY: Final[re.Pattern[str]] = re.compile(r"(https?://[^\s?#\"<>]+)\?[^\s\"<>]*")


def scrub(text: str) -> str:
    """`text` with every URL's query string cut, leaving the address it was asked of."""
    return _QUERY.sub(r"\1?…", text)


@contextmanager
def run_context(run_id: str) -> Iterator[None]:
    """Bind a run id to everything logged inside this block, on this task or thread.

    Restores whatever was bound before rather than clearing, so a nested block —
    a resolve run inside the run that spawned it — leaves the outer id in place
    on the way out instead of silently dropping correlation for the rest of it.
    """
    token = _RUN_ID.set(run_id)
    try:
        yield
    finally:
        _RUN_ID.reset(token)


@contextmanager
def look_context(qid: str) -> Iterator[None]:
    """Bind a look's QID to everything logged inside this block, restoring what was bound before."""
    token = _LOOK_QID.set(qid)
    try:
        yield
    finally:
        _LOOK_QID.reset(token)


def current_run_id() -> str | None:
    """The run being worked on here, if this is inside one."""
    return _RUN_ID.get()


class RunCorrelationFilter(logging.Filter):
    """Stamp the bound run id, and a look's QID, onto every record that passes through.

    A filter rather than a formatter concern: the id belongs to the record, so
    anything that later formats or routes it can see it. Never rejects a record —
    a log filter that dropped lines would make the absence of a signal mean two
    different things.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        run_id = _RUN_ID.get()
        if run_id is not None:
            record.run_id = run_id
        look_qid = _LOOK_QID.get()
        if look_qid is not None:
            record.look_qid = look_qid
        return True


class JsonFormatter(logging.Formatter):
    """One log record as one JSON object, with whatever the call site attached.

    Fields passed through `extra=` are carried through verbatim, so adding
    structure to a line is a keyword argument rather than a change here. Values
    that will not serialise are rendered with `str` rather than dropped: a line
    that vanished because one field was an odd type is the worst outcome
    available to a logger.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        run_id = getattr(record, "run_id", None)
        if run_id is not None:
            payload["run_id"] = run_id
        payload.update({name: value for name, value in vars(record).items() if name not in _BUILT_IN and name != "run_id"})
        if record.exc_info:
            # The trace goes to the journal and never to a caller. It is one
            # field rather than trailing lines so a multi-line traceback cannot
            # break the one-line-one-object rule the whole shape rests on.
            payload["exception"] = self.formatException(record.exc_info)
        # Scrubbed value by value, before the line is JSON: encoding first turns
        # an accented letter into an escape, and a cut that stopped there left the
        # rest of the query, key and all. Every value is scrubbed, so a key cannot
        # arrive by a route this line did not think of: a field, an argument, or
        # the message a traceback repeats.
        return json.dumps(_scrubbed(payload), default=str)


def _scrubbed(value: object) -> object:
    """`value` with every string in it scrubbed; anything JSON cannot hold becomes its scrubbed `str`."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {scrub(str(key)): _scrubbed(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_scrubbed(item) for item in value]
    # Rendered here rather than by `json.dumps(default=str)`, which would render
    # it after the scrub: an `httpx.URL` or an exception in a field carries its
    # query string in its `str`.
    return scrub(str(value))


#: Marks the handler this module installed, so a second call can replace its own
#: rather than evicting handlers it knows nothing about.
_INSTALLED: Final[str] = "_curation_log_handler"


def configure(level: int = logging.INFO) -> None:
    """Install the plane's log shape on the root logger.

    Called once, from the entry point. Calling it twice replaces the handler
    from the first call rather than adding a second, so lines cannot start
    arriving in duplicate.

    **Only this module's own handler is removed.** Evicting every root handler
    would be the tidier-looking implementation and a badly behaved one: it
    silently disables anything else attached to the root logger, and the first
    casualty is a test harness's capture — which fails as "no lines were logged"
    rather than as "your logging setup removed my handler".
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RunCorrelationFilter())
    setattr(handler, _INSTALLED, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _INSTALLED, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
