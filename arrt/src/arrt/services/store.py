"""Calling the durable store from a service.

The store speaks in constraint violations; nothing above the service layer should
have to know that the catalogue happens to be SQL. One helper rather than a `try`
around every write keeps that translation in a single place — and keeps it
identical across the services that share the file, which is the point of having
it here rather than as a private method on one of them.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol

from arrt.persistence.errors import StorageError
from arrt.services.errors import ServiceError


def store_write[**P](operation: Callable[P, None], *args: P.args, **kwargs: P.kwargs) -> None:
    """Run a store write, reporting a refusal in the service's own terms.

    The arguments are passed through rather than closed over so that a write
    inside a loop cannot capture the wrong iteration's record.
    """
    try:
        operation(*args, **kwargs)
    except StorageError as exc:
        raise ServiceError(str(exc)) from exc


class _Transactional(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...

    def in_transaction(self) -> bool: ...


class ActState[T]:
    """What one act keeps for the length of the store transaction it opens, seen only from inside that act.

    A service is shared by every thread that serves a request, so state about
    the act in progress (the works it changed, the feeds it decided) cannot be
    an ordinary attribute: another thread reading it would act on an act that
    is not its own. The store's lock lets one thread at a time hold a
    transaction, and `in_transaction` answers for the calling thread, so state
    held here is the caller's exactly when the caller is inside the act that set
    it. One rule for every service that needs it, so a fix to it reaches all.
    """

    def __init__(self, store: _Transactional) -> None:
        self._store = store
        self._value: T | None = None

    def current(self) -> T | None:
        """The open act's state, to the thread inside it; None to any other, and while no act is open."""
        value = self._value
        return value if value is not None and self._store.in_transaction() else None

    @contextmanager
    def opened(self, value: T) -> Iterator[T]:
        """Open a store transaction and hold `value` as its act's state until it ends.

        The body's last steps (announcing, writing what was decided) run inside
        the transaction, before it commits. Whether an act may open inside
        another is the caller's to decide before calling this.
        """
        with self._store.transaction():
            self._value = value
            try:
                yield value
            finally:
                self._value = None
