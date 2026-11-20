"""The values several parts of the server start from, and the paths one root gives them.

**This module imports no other `arrt` module**, so configuration can read a
default from here without loading the service layer, and the service layer can
read the same default without reaching up into configuration. Each value has one
owner, here; the module a value used to live in still names it, as this same
object (`tests/unit/test_config_imports_leaves.py` holds both halves).
"""

from pathlib import Path
from typing import Final

#: The largest preview body a museum may serve before it is refused. Enforced
#: while streaming, for the same reason `config.DEFAULT_MAX_IMAGE_BYTES` is: the ceiling
#: exists to protect memory, and `Content-Length` is the source's claim about
#: itself.
#:
#: **This one bounds RAM rather than the disk**, which is why it is three orders
#: of magnitude smaller. A preview is read whole into memory before anything
#: touches the filesystem, and the URL comes out of a museum's JSON with
#: redirects followed, so the final host need not even be the one that was asked.
#: `architecture.md` § Scaling Model ranks memory during acquisition as the one
#: input that could exhaust the Pi; the unit's `MemoryMax` contains the blast to
#: "curation dies" rather than "the wall goes dark", which is the cap working and
#: not the absence of a problem — a run lost to a thumbnail is still the tail
#: wagging the dog.
#:
#: Sized against measurement, not intuition: five Art Institute previews sampled
#: 2026-08-05 ran 89-193 KiB, the service serves exactly one derivative width
#: (843 px, every other request redirects to it), and this ceiling is some eighty
#: times the largest of those. It is not a prediction of the biggest legitimate
#: preview — it is the point past which a body has stopped being one.
DEFAULT_PREVIEW_MAX_BYTES: Final[int] = 16 * 1024 * 1024

#: The order a deployment gets when it names none: Commons first, then the Art
#: Institute, by the owner's ruling of 2026-10-01. Order only breaks ties between
#: images ranked level; every finder is asked at once.
DEFAULT_SOURCE_ORDER: Final[tuple[str, ...]] = ("commons", "artic")

#: What the deployment's one wall is called when nobody has said. Deliberately
#: not a place — "Living room" would be a confident lie on every deployment that
#: is not one — and deliberately not empty, because the name is the noun every
#: confirmation about that wall is built around.
DEFAULT_WALL_NAME: Final[str] = "The wall"

#: One file per wall under `ART_ROOT`, named by the wall's id. Not configurable:
#: the server and its tools have to agree where it is. One file per wall rather
#: than one carrying every wall, so a rewrite for one room changes no other
#: room's bytes, and so no other room's ETag.
MANIFEST_V2_FILENAME_TEMPLATE: Final[str] = "theme-manifest-{wall_id}.v2.json"

#: Written into `ART_ROOT` by the server from each Player's POST, **one file
#: per wall**. Not configurable, for the same reason the feed's name is not: the
#: server and its tools have to agree where it is.
#:
#: Per wall because health has to be able to name *which* wall is silent, and one
#: shared file has no way to say it — the second display would simply overwrite
#: the first's report, and a wall that had stopped reporting would look like a
#: wall that was fine.
HEARTBEAT_FILENAME_TEMPLATE: Final[str] = "display-heartbeat-{wall_id}.json"


def manifest_v2_path_in(art_root: Path, wall_id: str) -> Path:
    """Where one wall's feed lives under a given art root."""
    return art_root / MANIFEST_V2_FILENAME_TEMPLATE.format(wall_id=wall_id)


def heartbeat_path_in(art_root: Path, wall_id: str) -> Path:
    """Where one wall's heartbeat lives under a given art root.

    The one place the template is filled in, so the file `record_heartbeat` writes
    is the one every reader opens.
    """
    return art_root / HEARTBEAT_FILENAME_TEMPLATE.format(wall_id=wall_id)
