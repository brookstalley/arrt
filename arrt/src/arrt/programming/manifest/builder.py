"""What a theme would put on a wall, and the helpers every published document shares.

**Membership in a wall's feed IS catalogue readiness.** Readiness is the
Library's judgement, asked through `arrt.library.facade` at build time, and
the display plane sees only the works it passed.

**The cost of that design is paid here, in full.** A work can sit in a theme and
never reach the wall. Silence is this product's characteristic failure, so this
build does not get to be silent: every excluded work is named, with a reason, in
what the build returns. A builder that returned only a list would be an
incomplete implementation of the design, not a simpler one.

Every published document is written temp-and-rename (`write_atomically`). POSIX
rename is atomic within a filesystem, so a reader never observes a half-written
one. The feed itself is spelled by `v2.py`.
"""

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from arrt.counting import agree, agree_partitive, counted
from arrt.library.facade import Media, PlayableWork, Unplayable, UnplayableReason
from arrt.persistence.records import Theme, Wall


class KeptOff(StrEnum):
    """Why Programming leaves a work the Library would show off a wall.

    Beside `UnplayableReason` rather than in it, because the Library judges
    whether a work *can* go on a wall and this is the curator saying it *should
    not*: a different owner, and a different thing to undo.
    """

    #: *Not this one again*, from every wall. Undone from the work's page.
    EVERY_WALL = "kept_off_every_wall"


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One work that is in the theme and not on the wall, and why."""

    work_id: str
    #: The work's id when the id names no work the catalogue holds, because an
    #: exclusion is read by a curator scanning a list and every row needs a name.
    title: str
    reason: UnplayableReason | KeptOff
    #: A sentence a curator can act on, not a restatement of the enum.
    detail: str

    @classmethod
    def of(cls, unplayable: Unplayable) -> Exclusion:
        """Programming's report of the Library's refusal."""
        return cls(
            work_id=unplayable.work_id,
            title=unplayable.title if unplayable.title is not None else unplayable.work_id,
            reason=unplayable.reason,
            detail=unplayable.detail,
        )

    @classmethod
    def kept_off(cls, answer: PlayableWork | Unplayable) -> Exclusion:
        """A work the curator said not to show again, on any wall."""
        return cls(
            work_id=answer.work_id,
            title=answer.title if answer.title is not None else answer.work_id,
            reason=KeptOff.EVERY_WALL,
            detail="You said not to show this again on any wall. Allow it again from its page to put it back.",
        )


@dataclass(frozen=True, slots=True)
class ManifestBuild:
    """What one build produced — including, deliberately, what it left out."""

    #: Which wall this build is about. Carried so that a surface can name it in
    #: the confirmation — "Hang Winter in the living room" — without asking a
    #: second question; a confirmation that reads correctly only because there is
    #: one possible target silently becomes wrong when a second display arrives.
    wall: Wall
    theme: Theme
    #: The Library's answer for each work that goes on the wall, in the theme's
    #: order. The feed is built from these, so what the curator is told and what
    #: the wall is sent are one verdict.
    entries: Sequence[PlayableWork]
    exclusions: Sequence[Exclusion]
    #: The slot length the schedule gives each work.
    rotation_interval_seconds: int
    shuffle: bool

    @property
    def considered(self) -> int:
        """Every member the theme offered. Entries plus exclusions account for all of them."""
        return len(self.entries) + len(self.exclusions)

    def summarise(self) -> str:
        """One sentence saying how much of the theme reached the wall.

        **It lives on the build rather than on either surface.** Both the tool
        result and the browser response state this same fact, and two
        hand-written sentences drift — a caller told "9 of 12" by one surface and
        "all 12" by the other has no way to tell which is lying. Formatting may
        differ per surface; what is *claimed* may not.

        Stated on the clean build too, deliberately. A message that appeared only
        when something was wrong would train a reader to skim past its absence,
        and "12 of 12" is the sentence that makes "9 of 12" legible.

        **It stops at the counts and does not tell the reader where to look.**
        Each surface knows what it put in front of whoever is reading — a field
        name in a tool result, a table on a page — and this cannot. An earlier
        version ended "each for the reason given", which left the tool result
        saying the same thing twice once its own pointer was appended.
        """
        if self.considered == 0:
            return "This theme holds no works yet, so nothing is on the wall."
        if not self.exclusions:
            # The no-exclusions branch agrees with its sibling below, and both
            # were fixed together: taking one and leaving the other makes this
            # method correct when a theme has exclusions and wrong when it does
            # not, which is the harder of the two to notice.
            return f"All {counted(self.considered, 'work')} in this theme {agree(self.considered, 'is', 'are')} on the wall."
        # A partitive, so the verb agrees with the numerator: "1 of 3 works in
        # this theme **is** on the wall". `considered` is the count printed
        # immediately before the verb, which is why keying `agree` on it read
        # right and was wrong. The sibling branch above keys on `considered` and
        # is right to — there the subject really is "All N works". Same helper,
        # different subject, and the nearest count is the wrong one exactly half
        # the time.
        return (
            f"{len(self.entries)} of {counted(self.considered, 'work')} in this theme "
            f"{agree_partitive(len(self.entries), self.considered, 'is', 'are')} on the wall; "
            f"{len(self.exclusions)} {agree(len(self.exclusions), 'is', 'are')} not currently displayable."
        )


def media_document(media: Media) -> dict[str, Any]:
    """An entry's `media` as the document spells it."""
    return {"url": media.url, "sha256": media.sha256, "bytes": media.byte_size, "content_type": media.content_type}


def write_atomically(path: Path, document: dict[str, Any]) -> None:
    """Replace the manifest in one step, so no reader ever sees a partial one.

    The temp file is created in the destination's own directory because
    `os.replace` is only atomic within a filesystem, and the obvious temp
    location is frequently a different one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            # The rename below publishes whatever is in the file. Without this the
            # bytes may still be in a buffer, and a reader would be handed a
            # truncated document that parses as invalid JSON rather than as absent.
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; the temp file must go on any exit
        # Wider than `Exception` deliberately, and it swallows nothing: a
        # `KeyboardInterrupt` or an early close leaves this body just as surely
        # as an error does, and each one would strand a `.theme-manifest-….v2.json.*`
        # file beside the real manifest. The same exception continues.
        Path(temporary).unlink(missing_ok=True)
        raise
