"""Answers from slow foreign sources, kept on disk so a restart does not ask again.

A page section that asks a foreign service can wait seconds for its answer, and
some answers take tens of seconds. Keeping them only in memory meant every
restart, deploy or crash put the next curator back behind the slowest query.
This keeps them in a file of their own under
`ART_ROOT`, for any service that asks anything slow: each use names a
**namespace**, how long its answers stay usable, how many it keeps, and how its
answers are written and read.

**Disposable, and nothing here may make it otherwise.** Deleting the file loses
time and nothing else: the next visit asks again. So it lives apart from the
catalogue, a backup skips it, and once it is open every way it can fail is a
miss rather than an error: an entry that cannot be read back is dropped and
asked again, and a read or write the disk refuses is logged and the page goes on
without it. When it is opened, a file that is not a database, is damaged, or is
of another format is replaced; one that cannot even be created stops the start,
as a catalogue that cannot be opened does, because the root is unwritable.

**What the callers keep, the callers decide.** Two rules hold for every
caller: a failure is never kept, because a caller only `put`s what
answered, and the slow question is asked outside any lock, between `get` and
`put`, so one page's query never holds another's lookup back.

**What is thrown away first**, per namespace: anything older than its maximum
age, then the least recently used beyond its size. Answers of a namespace
nobody asks for any more are thrown away once their age passes, when the file
is next opened.
"""

import contextlib
import dataclasses
import enum
import json
import logging
import sqlite3
import threading
import time
import types
import typing
from collections.abc import Callable, Hashable, Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, Final, Protocol

log = logging.getLogger(__name__)

#: The file's format. A file of any other format is replaced when opened, not
#: migrated: what it holds can be asked again.
FORMAT: Final[int] = 1

_SCHEMA: Final[str] = """
CREATE TABLE answers (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    -- When the answer was given, in seconds since the epoch: its age is read
    -- against the namespace's maximum age as the namespace sets it today.
    written REAL NOT NULL,
    -- When it stops being usable at the age it was kept for, so an answer of a
    -- namespace nobody registers any more is still thrown away in time.
    expires REAL NOT NULL,
    -- Larger is more recently used. A counter rather than a time, so two uses
    -- within one tick of the clock are still ordered.
    used INTEGER NOT NULL,
    PRIMARY KEY (namespace, key)
);
CREATE INDEX answers_by_use ON answers (namespace, used);
"""


class Codec[V](Protocol):
    """How a namespace's answers are written to text and read back.

    `decode` may raise anything for text it cannot read: the entry is then a
    miss, so a changed answer shape costs one more question, never an error.
    """

    def encode(self, value: V) -> str: ...

    def decode(self, text: str) -> V: ...


class Kept[K: Hashable, V]:
    """One namespace's answers: `get` what is kept and fresh, `put` what answered."""

    def __init__(self, answers: KeptAnswers, name: str, codec: Codec[V], max_age: timedelta, size: int) -> None:
        self._answers = answers
        self.name = name
        self._codec = codec
        self._max_age = max_age.total_seconds()
        self._size = size

    def get(self, key: K) -> V | None:
        """The kept answer for `key`, or None when there is none, it is too old, or it cannot be read."""
        stored = _key_text(key)
        found = self._answers._read(self.name, stored)  # noqa: SLF001 -- KeptAnswers' module-private API
        if found is None:
            return None
        text, written = found
        age = self._answers._clock() - written  # noqa: SLF001 -- KeptAnswers' module-private API
        # A negative age is a clock that went back, and an answer from the future
        # would otherwise stay fresh for however far it went.
        if age < 0 or age >= self._max_age:
            self._answers._forget(self.name, stored)  # noqa: SLF001 -- KeptAnswers' module-private API
            return None
        try:
            value = self._codec.decode(text)
        except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- caller's codec: unreadable is a miss
            log.info(
                "a kept answer could not be read back and will be asked again",
                extra={"event": "kept.unreadable", "namespace": self.name, "error": type(exc).__name__},
            )
            self._answers._forget(self.name, stored)  # noqa: SLF001 -- KeptAnswers' module-private API
            return None
        self._answers._touch(self.name, stored)  # noqa: SLF001 -- KeptAnswers' module-private API
        return value

    def put(self, key: K, value: V) -> None:
        """Keep `value` as the answer for `key`. Never raises: an answer not kept is asked again."""
        try:
            text = self._codec.encode(value)
        except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- caller's codec: unwritable is not kept
            log.warning(
                "an answer could not be written and is not kept",
                extra={"event": "kept.unwritable", "namespace": self.name, "error": repr(exc)},
            )
            return
        self._answers._write(  # noqa: SLF001 -- KeptAnswers' module-private API
            self.name, _key_text(key), text, max_age=self._max_age, size=self._size
        )


class KeptAnswers:
    """The file every namespace keeps its answers in, safe to share between request threads."""

    def __init__(self, path: Path | str, *, clock: Callable[[], float] = time.time) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._names: set[str] = set()
        self._connection = self._open()
        with self._lock:
            row = self._connection.execute("SELECT COALESCE(MAX(used), 0), COUNT(*) FROM answers").fetchone()
            self._used: int = row[0]
            # Answers of a namespace nobody registers any more would otherwise
            # stay for good: nothing puts to it, so nothing evicts from it.
            gone = self._connection.execute("DELETE FROM answers WHERE expires <= ?", (self._clock(),)).rowcount
            self._connection.commit()
        log.info(
            "kept answers opened",
            extra={"event": "kept.opened", "path": str(path), "entries": row[1] - gone, "expired": gone},
        )

    @classmethod
    def in_memory(cls, *, clock: Callable[[], float] = time.time) -> KeptAnswers:
        """Answers kept for the life of the process only: what a caller that wired no file gets."""
        return cls(":memory:", clock=clock)

    def namespace[K: Hashable, V](self, name: str, *, codec: Codec[V], max_age: timedelta, size: int) -> Kept[K, V]:
        """A namespace of this file, for one use. A name may be registered once per file.

        `max_age` is how long an answer stays usable; `size` how many the namespace
        keeps. Keys are JSON values: strings, numbers, flags and tuples of them.
        """
        if not name:
            raise ValueError("A namespace needs a name.")
        if max_age <= timedelta(0) or size < 1:
            raise ValueError(f"Namespace {name!r} must keep at least one answer for some time.")
        with self._lock:
            # Two uses under one name would read each other's answers with the
            # wrong codec, which looks like a stream of unreadable entries.
            if name in self._names:
                raise ValueError(f"Namespace {name!r} is already registered on this file.")
            self._names.add(name)
        return Kept(self, name, codec, max_age, size)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    # -- the file ------------------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        """A connection to a file of this format: the one there, or a new one in its place."""
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            fault = self._fault(connection)
        except sqlite3.DatabaseError as exc:
            fault = f"it could not be read ({exc})"
        if fault is None and connection is not None:
            return connection
        if connection is not None:
            connection.close()
        log.warning(
            "the kept answers file was replaced; its answers will be asked again",
            extra={"event": "kept.replaced", "path": str(self._path), "reason": fault},
        )
        if self._path != ":memory:":
            for suffix in ("", "-wal", "-shm"):
                Path(f"{self._path}{suffix}").unlink(missing_ok=True)
        connection = self._connect()
        if self._fault(connection) is not None:
            raise RuntimeError(f"A new kept answers file at {self._path} is not usable.")
        return connection

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._path), check_same_thread=False)
        # Every hit records its use, so commits are frequent; the write-ahead log
        # without a sync per commit keeps them cheap on an SD card. A crash may
        # lose the last few, which costs those answers one more question.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @staticmethod
    def _fault(connection: sqlite3.Connection) -> str | None:
        """Why this file cannot be used as it is, or None. Creates the table in an empty one."""
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            return "it is damaged"
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
        if version == 0 and tables == 0:
            connection.executescript(_SCHEMA)
            connection.execute(f"PRAGMA user_version = {FORMAT}")
            connection.commit()
            return None
        if version != FORMAT:
            return f"it is format {version}, not {FORMAT}"
        return None

    # -- what a namespace asks of it ------------------------------------------

    def _read(self, namespace: str, key: str) -> tuple[str, float] | None:
        try:
            with self._lock:
                row = self._connection.execute(
                    "SELECT value, written FROM answers WHERE namespace = ? AND key = ?", (namespace, key)
                ).fetchone()
        except sqlite3.Error as exc:
            self._failed("read", namespace, exc)
            return None
        return None if row is None else (row[0], row[1])

    def _touch(self, namespace: str, key: str) -> None:
        self._change(namespace, "UPDATE answers SET used = ? WHERE namespace = ? AND key = ?", key, used=True)

    def _forget(self, namespace: str, key: str) -> None:
        self._change(namespace, "DELETE FROM answers WHERE namespace = ? AND key = ?", key, used=False)

    def _change(self, namespace: str, statement: str, key: str, *, used: bool) -> None:
        try:
            with self._lock:
                if used:
                    self._used += 1
                    self._connection.execute(statement, (self._used, namespace, key))
                else:
                    self._connection.execute(statement, (namespace, key))
                self._connection.commit()
        except sqlite3.Error as exc:
            self._failed("write", namespace, exc)

    def _write(self, namespace: str, key: str, value: str, *, max_age: float, size: int) -> None:
        now = self._clock()
        try:
            with self._lock:
                self._used += 1
                self._connection.execute(
                    "INSERT INTO answers (namespace, key, value, written, expires, used) VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (namespace, key) DO UPDATE SET value = excluded.value, written = excluded.written,"
                    " expires = excluded.expires, used = excluded.used",
                    (namespace, key, value, now, now + max_age, self._used),
                )
                # Too old first, then the least recently used beyond the size.
                self._connection.execute("DELETE FROM answers WHERE namespace = ? AND written <= ?", (namespace, now - max_age))
                self._connection.execute(
                    "DELETE FROM answers WHERE namespace = ? AND key IN"
                    " (SELECT key FROM answers WHERE namespace = ? ORDER BY used DESC LIMIT -1 OFFSET ?)",
                    (namespace, namespace, size),
                )
                self._connection.commit()
        except sqlite3.Error as exc:
            self._failed("write", namespace, exc)

    def _failed(self, what: str, namespace: str, exc: sqlite3.Error) -> None:
        # A failed statement can leave the driver's implicit transaction open,
        # which would hold the file's write lock until the next commit. A
        # rollback that fails too (a closed connection) leaves nothing worse.
        with self._lock, contextlib.suppress(sqlite3.Error):
            if self._connection.in_transaction:
                self._connection.rollback()
        log.warning(
            "the kept answers file could not be used; the answer is asked fresh",
            extra={"event": "kept.failed", "namespace": namespace, "operation": what, "error": repr(exc)},
        )


def _key_text(key: Hashable) -> str:
    """A key as the file stores it: JSON, so a tuple of strings and flags is one string."""
    return json.dumps(key, separators=(",", ":"), ensure_ascii=False)


# -- a codec derived from the answer's type -------------------------------------


class JsonCodec[V]:
    """Answers written as JSON and read back strictly against the type they were declared as.

    For frozen dataclasses of strings, numbers, flags, enums, `NewType`s of those,
    optionals, tuples, sequences and string-keyed mappings, nested to any depth.
    The type is checked when the codec is made, so a shape it cannot keep fails
    where it is wired, not as a miss on every visit.

    **Strict on reading, which is what makes a changed shape a miss.** A
    dataclass's fields must be exactly the ones the entry holds, and every value
    the type it is declared as: a field added, removed or retyped since the
    answer was kept makes it unreadable, so it is asked again rather than read
    back with a default it never had.
    """

    def __init__(self, shape: Any) -> None:  # noqa: ANN401 -- a type form, which Python cannot annotate
        _check_shape(shape, set())
        self._shape = shape

    def encode(self, value: V) -> str:
        return json.dumps(_to_json(self._shape, value), separators=(",", ":"), ensure_ascii=False)

    def decode(self, text: str) -> V:
        return _from_json(self._shape, json.loads(text))


_SCALARS: Final[tuple[type, ...]] = (str, int, float, bool)


def _parts(shape: Any) -> tuple[Any, tuple[Any, ...]]:  # noqa: ANN401 -- a type form
    return typing.get_origin(shape), typing.get_args(shape)


def _unaliased(shape: Any) -> Any:  # noqa: ANN401 -- a type form
    """The type a `type X = ...` statement names, so an alias keeps what it stands for."""
    while isinstance(shape, typing.TypeAliasType):
        shape = shape.__value__
    return shape


def _is_union(origin: Any) -> bool:  # noqa: ANN401 -- a type form
    return origin is typing.Union or origin is types.UnionType


def _check_shape(shape: Any, seen: set[type]) -> None:  # noqa: ANN401, C901, PLR0911 -- a type form; a branch per kind of form
    shape = _unaliased(shape)
    if shape is type(None) or shape in _SCALARS:
        return
    if isinstance(shape, typing.NewType):
        _check_shape(shape.__supertype__, seen)
        return
    if isinstance(shape, type) and issubclass(shape, enum.Enum):
        return
    if isinstance(shape, type) and dataclasses.is_dataclass(shape):
        if shape in seen:
            return
        seen.add(shape)
        for hint in typing.get_type_hints(shape).values():
            _check_shape(hint, seen)
        return
    origin, args = _parts(shape)
    if _is_union(origin) or origin is tuple:
        for arg in args:
            if arg is not Ellipsis:
                _check_shape(arg, seen)
        return
    if origin in (list, Sequence):
        _check_shape(args[0], seen)
        return
    if origin in (dict, Mapping):
        if _scalar_of(args[0]) is not str:
            raise TypeError(f"A kept mapping's keys must be strings, not {args[0]!r}.")
        _check_shape(args[1], seen)
        return
    raise TypeError(f"{shape!r} cannot be kept as JSON.")


def _scalar_of(shape: Any) -> Any:  # noqa: ANN401 -- a type form
    while isinstance(shape, typing.NewType):
        shape = shape.__supertype__
    return shape


def _to_json(shape: Any, value: Any) -> Any:  # noqa: ANN401, C901, PLR0911, PLR0912 -- JSON and type forms; a branch per form
    shape = _unaliased(shape)
    origin, args = _parts(shape)
    if _is_union(origin):
        for arg in args:
            try:
                return _to_json(arg, value)
            except TypeError:
                continue
        raise TypeError(f"{value!r} is none of {shape!r}.")
    shape = _scalar_of(shape)
    if shape is type(None):
        if value is not None:
            raise TypeError(f"{value!r} is not None.")
        return None
    if shape in _SCALARS:
        _require_scalar(shape, value)
        return value
    if isinstance(shape, type) and issubclass(shape, enum.Enum):
        if not isinstance(value, shape):
            raise TypeError(f"{value!r} is not a {shape.__name__}.")
        return value.value
    if isinstance(shape, type) and dataclasses.is_dataclass(shape):
        if not isinstance(value, shape):
            raise TypeError(f"{value!r} is not a {shape.__name__}.")
        hints = typing.get_type_hints(shape)
        return {f.name: _to_json(hints[f.name], getattr(value, f.name)) for f in dataclasses.fields(shape)}
    origin, args = _parts(shape)
    if origin in (tuple, list, Sequence):
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
            raise TypeError(f"{value!r} is not a sequence.")
        return [_to_json(arg, item) for arg, item in zip(_items(args, len(value)), value, strict=True)]
    if origin in (dict, Mapping):
        if not isinstance(value, Mapping):
            raise TypeError(f"{value!r} is not a mapping.")
        return {_require_scalar(str, key): _to_json(args[1], item) for key, item in value.items()}
    raise TypeError(f"{shape!r} cannot be kept as JSON.")


#: What a member's constructor raises for a value that is not one of it. A named
#: tuple rather than `except TypeError, ValueError:` because the root suite's
#: seam guards parse this plane's source on Python 3.12, which cannot read the
#: unparenthesised form this plane's formatter writes.
_NOT_ITS_VALUE: Final[tuple[type[Exception], ...]] = (TypeError, ValueError)


def _from_json(shape: Any, data: Any) -> Any:  # noqa: ANN401, C901, PLR0911, PLR0912 -- JSON and type forms; a branch per form
    shape = _unaliased(shape)
    origin, args = _parts(shape)
    if _is_union(origin):
        for arg in args:
            try:
                return _from_json(arg, data)
            except _NOT_ITS_VALUE:
                continue
        raise TypeError(f"{data!r} is none of {shape!r}.")
    shape = _scalar_of(shape)
    if shape is type(None):
        if data is not None:
            raise TypeError(f"{data!r} is not None.")
        return None
    if shape in _SCALARS:
        return _require_scalar(shape, data)
    if isinstance(shape, type) and issubclass(shape, enum.Enum):
        return shape(data)
    if isinstance(shape, type) and dataclasses.is_dataclass(shape):
        names = [f.name for f in dataclasses.fields(shape)]
        if not isinstance(data, dict) or set(data) != set(names):
            raise TypeError(f"An entry does not have the fields of {shape.__name__}.")
        hints = typing.get_type_hints(shape)
        return shape(**{name: _from_json(hints[name], data[name]) for name in names})
    origin, args = _parts(shape)
    if origin in (tuple, list, Sequence):
        if not isinstance(data, list):
            raise TypeError(f"{data!r} is not a list.")
        return tuple(_from_json(arg, item) for arg, item in zip(_items(args, len(data)), data, strict=True))
    if origin in (dict, Mapping):
        if not isinstance(data, dict):
            raise TypeError(f"{data!r} is not an object.")
        return {key: _from_json(args[1], item) for key, item in data.items()}
    raise TypeError(f"{shape!r} cannot be kept as JSON.")


def _items(args: tuple[Any, ...], length: int) -> Sequence[Any]:
    """The type of each item of a sequence of `length`: one for all, or one each for a fixed tuple."""
    if len(args) == 2 and args[1] is Ellipsis:  # noqa: PLR2004 -- tuple[X, ...] has exactly two args
        return [args[0]] * length
    if len(args) == 1:
        return [args[0]] * length
    if len(args) != length:
        raise TypeError(f"A fixed tuple of {len(args)} does not hold {length}.")
    return args


def _require_scalar(shape: type, value: Any) -> Any:  # noqa: ANN401 -- JSON
    # `bool` is an `int` to Python and never one to a page, and an `int` is a
    # fine `float`; nothing else crosses.
    if shape is float and type(value) in (int, float):
        return float(value)
    if type(value) is not shape:
        raise TypeError(f"{value!r} is not a {shape.__name__}.")
    return value
