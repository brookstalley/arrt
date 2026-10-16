"""A wall's major 2 manifest: its private feed, built from the wall's schedule.

`player-contract.md` § Major 2 is the definition and `contract/schemas/manifest.v2.schema.json`
the shape. It is the only major this server publishes (§ The cutover).

**The published document is the schedule's state.** Programming reads it back (`read_published`) to keep the slot on the
wall now and to check the household rule against every other wall, and never
keeps a second copy that could drift from what the Players were sent.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from arrt.library.facade import PlayableWork
from arrt.programming.manifest.builder import media_document
from arrt.programming.schedule import Schedule, Slot

log = logging.getLogger(__name__)

#: One file per wall under `ART_ROOT`, named by the wall's id. Not configurable:
#: the server and its tools have to agree where it is. One file per wall rather
#: than one carrying every wall, so a rewrite for one room changes no other
#: room's bytes, and so no other room's ETag.
MANIFEST_V2_FILENAME_TEMPLATE: Final[str] = "theme-manifest-{wall_id}.v2.json"

SCHEMA_MAJOR: Final[int] = 2
SCHEMA_MINOR: Final[int] = 0


def manifest_v2_path_in(art_root: Path, wall_id: str) -> Path:
    return art_root / MANIFEST_V2_FILENAME_TEMPLATE.format(wall_id=wall_id)


@dataclass(frozen=True, slots=True)
class Feed:
    """One wall's major 2 document, before it is spelled as JSON."""

    playlist_id: str
    playlist_name: str
    schedule: Schedule
    #: Each work's entry as the document spells it (`work_document`), keyed by id.
    #: Entries rather than the Library's answers, so a rebuild from the published
    #: document (a horizon rolled forward, a work withdrawn) needs nothing the
    #: Library would have to be asked again. Only the works the schedule names
    #: are written (`player-contract.md` § Settled before wave 4: others are
    #: allowed, but only make a Player fetch less wisely).
    works: Mapping[str, Mapping[str, Any]]
    #: The feed's presentation defaults (§ Presentation settings), each key optional.
    settings: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        named = {slot.work_id for slot in self.schedule.slots}
        missing = named - set(self.works)
        if missing:
            # The contract's first rule a schema cannot state. A Player refuses the
            # whole document over one dangling name, so it is refused here first.
            raise ValueError(f"The schedule names works the feed does not carry: {', '.join(sorted(missing))}.")


def as_document(feed: Feed) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": {"major": SCHEMA_MAJOR, "minor": SCHEMA_MINOR},
        "generated_at": datetime.now(UTC).isoformat(),
        "playlist": {"id": feed.playlist_id, "name": feed.playlist_name},
    }
    if feed.settings:
        document["settings"] = dict(feed.settings)
    named = {slot.work_id for slot in feed.schedule.slots}
    document["works"] = {work_id: dict(feed.works[work_id]) for work_id in sorted(named)}
    document["schedule"] = {
        "horizon": {"from": _instant(feed.schedule.horizon_from), "until": _instant(feed.schedule.horizon_until)},
        "slots": [{"work_id": s.work_id, "from": _instant(s.start), "until": _instant(s.until)} for s in feed.schedule.slots],
    }
    return document


def work_document(work: PlayableWork) -> dict[str, Any]:
    """One work as major 2 spells it: the master, its colour and its label."""
    media = {**media_document(work.master.media), "width": work.master.width, "height": work.master.height}
    return {"media": media, "mat_color": work.mat_color, "label": dict(work.label)}


@dataclass(frozen=True, slots=True)
class Published:
    """What a wall's major 2 document says, read back."""

    playlist_id: str
    playlist_name: str
    horizon_from: datetime
    horizon_until: datetime
    slots: tuple[Slot, ...]
    #: Each work's entry as published, keyed by id.
    works: Mapping[str, dict[str, Any]]
    #: The feed's presentation defaults as published, so a patch keeps them.
    settings: Mapping[str, Any] = field(default_factory=dict)

    def on_the_wall(self, now: datetime) -> Slot | None:
        """The slot covering `now`, if one does (a gap, or a horizon run out, has none)."""
        return next((slot for slot in self.slots if slot.covers(now)), None)

    def after(self, now: datetime) -> str | None:
        """The work the slot after the one on the wall now names, or None if there is none."""
        for here, following in zip(self.slots, self.slots[1:], strict=False):
            if here.covers(now):
                return following.work_id
        return None


def read_published(path: Path) -> Published | None:
    """The wall's major 2 document as last published, or None if there is none to build on.

    An unreadable document is logged and treated as absent: the next publish
    replaces it whole, starting the wall fresh.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("The major 2 manifest at %s cannot be read (%s); the next publish replaces it.", path, exc)
        return None
    try:
        schedule = document["schedule"]
        return Published(
            playlist_id=document["playlist"]["id"],
            playlist_name=document["playlist"]["name"],
            horizon_from=datetime.fromisoformat(schedule["horizon"]["from"]),
            horizon_until=datetime.fromisoformat(schedule["horizon"]["until"]),
            slots=tuple(
                Slot(slot["work_id"], datetime.fromisoformat(slot["from"]), datetime.fromisoformat(slot["until"]))
                for slot in schedule["slots"]
            ),
            works=dict(document["works"]),
            settings=dict(document.get("settings") or {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("The major 2 manifest at %s is not one this server wrote (%s); the next publish replaces it.", path, exc)
        return None


def _instant(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()
