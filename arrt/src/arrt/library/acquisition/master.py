"""The presentation master: one device-independent image of a held work.

**Rendered for no screen.** It is the Original, upright, in RGB, with no mat,
brought down to at most `PRESENTATION_MASTER_LONG_EDGE_PX` on its long edge and
never enlarged. A Player composes its own wall from it (re-architecture wave 4),
so it carries nothing that belongs to a screen: no mat, no bars, no label. That
is why transporting it conforms to "derived artifacts are regenerated, never
transported" (`data-model.md` § Direction, the ruling of 2026-09-30): the norm
covers what is rendered for a specific output geometry, and this is rendered
for none.

**Capped, because a Pi decodes it.** A gigapixel Original would cost a Player
far more than any screen can show; 7,680 px is the size the Player's compositing
budget was measured against on a Pi 4 (`nonfunctional-requirements.md`
§ Performance).

**JPEG at the Player's compositor's own quality**, so a master loses nothing the
compositor would keep, and sRGB as read:
`color.py` treats every image as sRGB, with no colour management.

**Content-addressed once recorded.** A Player's cached copy cannot go stale
silently, because a new master has a new hash; the Library knows a master is
stale the way it knows any Rendition is, by its `source_content_hash`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from arrt.library.services.imaging import encode_downscaled, reading
from arrt.library.services.quality import PRESENTATION_MASTER_LONG_EDGE_PX

#: What a master is encoded at: JPEG at high quality, the quality a Player's
#: compositor writes too. It is part of `MASTER_RULE`, so changing it makes
#: every master again.
JPEG_QUALITY: Final[int] = 95

#: How a master is made, recorded on its Rendition's `layout`. A master is current only while it was made by this rule *and* from
#: the Original held now: the hash alone cannot see a changed cap or quality,
#: and every master made the old way would stay current for good.
MASTER_RULE: Final[str] = f"presentation-master long-edge={PRESENTATION_MASTER_LONG_EDGE_PX} jpeg-q={JPEG_QUALITY}"

#: Where masters live under `ART_ROOT`, one file per work.
MASTERS_DIRNAME: Final[str] = "presentation"

_FILENAME: Final[str] = "{artwork_id}.jpg"


@dataclass(frozen=True, slots=True)
class Master:
    """A master written to disk, and the size it came out at."""

    path: Path
    width: int
    height: int


def master_path(masters: Path, artwork_id: str) -> Path:
    """Where this work's master is written: its name carries no size, so a rewrite replaces it."""
    return masters / _FILENAME.format(artwork_id=artwork_id)


def make_master(source: Path, *, destination: Path) -> Master:
    """Derive the master of the Original at `source` and write it to `destination`.

    **Only the decode is translated** into a refusal naming the file, as the
    compositor's is: bytes a museum served can fail to decode, and that is a
    different fault from this host's disk refusing the write, which still raises
    `OSError`. The file at `destination` is replaced only once a whole master has
    been written, so a failure partway costs the work nothing it already had.
    """
    frame = reading(source, lambda: encode_downscaled(source, max_edge=PRESENTATION_MASTER_LONG_EDGE_PX, quality=JPEG_QUALITY))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_name(f"{destination.name}.making")
    try:
        staged.write_bytes(frame.data)
        staged.replace(destination)
    except OSError:
        staged.unlink(missing_ok=True)
        raise
    return Master(path=destination, width=frame.width, height=frame.height)


__all__ = ["MASTERS_DIRNAME", "MASTER_RULE", "Master", "make_master", "master_path"]
