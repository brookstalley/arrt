"""What the registry's pages share: a bounded memory of answers, the sentence for a
registry that is not configured, and the check on a QID an address carries.

Every registry answer a page asks for is kept for the life of the process, because
a query takes from half a second to several, and a curator moving between pages
asks the same thing again. A failure is never kept, so the next visit asks again;
that rule is the callers', who only `put` what answered.
"""

import threading
from collections import OrderedDict
from collections.abc import Hashable
from typing import Final

from arrt.library.registry import QID
from arrt.services.errors import ServiceError

#: The sentence every registry page shows when `WIKIDATA_USER_AGENT` is unset.
NOT_CONFIGURED_NOTE: Final[str] = "Wikidata is not configured on this server (WIKIDATA_USER_AGENT is unset)."

#: How many answers each memory keeps. Above the library's artist count by a
#: margin, so browsing never evicts the page a curator came from.
REMEMBERED: Final[int] = 512


class Remembered[K: Hashable, V]:
    """The most recently used answers, up to `size`, safe to share between request threads.

    Asking the registry happens outside the lock, between `get` and `put`, so one
    slow query never holds another page's lookup back.
    """

    def __init__(self, size: int = REMEMBERED) -> None:
        self._size = size
        self._answers: OrderedDict[K, V] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: K) -> V | None:
        with self._lock:
            if key not in self._answers:
                return None
            self._answers.move_to_end(key)
            return self._answers[key]

    def put(self, key: K, value: V) -> None:
        with self._lock:
            self._answers[key] = value
            self._answers.move_to_end(key)
            while len(self._answers) > self._size:
                self._answers.popitem(last=False)


def checked_qid(qid: str) -> str:
    """A QID as an address carries it, refused as the curator's mistake when it is not one."""
    if not QID.match(qid):
        raise ServiceError(f"{qid!r} is not a Wikidata item id (Q followed by digits).")
    return qid
