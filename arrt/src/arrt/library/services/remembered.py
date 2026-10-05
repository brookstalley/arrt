"""What the registry's pages share: how many answers each keeps, the sentence for a
registry that is not configured, and the check on a QID an address carries.

The answers themselves are kept across restarts by `persistence/kept.py`, each
page section in a namespace of its own, bounded at `REMEMBERED` entries.
"""

from typing import Final

from arrt.library.registry import QID
from arrt.services.errors import ServiceError

#: The sentence every registry page shows when `WIKIDATA_USER_AGENT` is unset.
NOT_CONFIGURED_NOTE: Final[str] = "Wikidata is not configured on this server (WIKIDATA_USER_AGENT is unset)."

#: How many answers each page section keeps. Above the library's artist count by a
#: margin, so browsing never evicts the page a curator came from.
REMEMBERED: Final[int] = 512


def checked_qid(qid: str) -> str:
    """A QID as an address carries it, refused as the curator's mistake when it is not one."""
    if not QID.match(qid):
        raise ServiceError(f"{qid!r} is not a Wikidata item id (Q followed by digits).")
    return qid
