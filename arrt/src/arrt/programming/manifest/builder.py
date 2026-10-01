"""The theme manifest — the one channel from curation to the display plane.

**Membership in this document IS catalogue readiness.** Readiness is the
Library's judgement, asked through `arrt.library.facade` at build time, and
the display plane sees only the works it passed.

**The cost of that design is paid here, in full.** A work can sit in a theme and
never reach the wall. Silence is this product's characteristic failure, so this
build does not get to be silent: every excluded work is named, with a reason, in
what the build returns. A builder that returned only a list would be an
incomplete implementation of the design, not a simpler one.

The document is written temp-and-rename. POSIX rename is atomic within a
filesystem, so the display plane polling this path never observes a half-written
manifest — which is the entire concurrency-control story between the two planes.
"""

import json
import logging
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from arrt.counting import agree, agree_partitive, counted
from arrt.library.facade import Media, PlayableWork, Unplayable, UnplayableReason
from arrt.persistence.records import Theme, Wall

log = logging.getLogger(__name__)

#: The manifest's filename under `ART_ROOT`, **one file per wall**. Not
#: configurable: both planes have to agree where it is, and a setting is only a
#: way for them to stop agreeing.
#:
#: One file per wall rather than one file carrying a section per wall. Change
#: detection on the other side is an mtime poll at about a second, so a shared
#: file would wake every wall's display on every other wall's change — and would
#: make "the manifest's sequence" ambiguous exactly where the coalescing and
#: sequence-regression rules need it to be singular. Per file also leaves a
#: display plane structurally unable to read a wall it does not serve: it is
#: configured with one wall's id and stats one path.
MANIFEST_FILENAME_TEMPLATE: Final[str] = "theme-manifest-{wall_id}.json"

#: Bumped only by a change that would stop an existing display plane reading a
#: manifest correctly — a removed field, a changed meaning, a new required key.
#: Display refuses a major it does not recognise and keeps the last manifest it
#: had, so a bump is a deliberate cutover rather than a silent break.
SCHEMA_MAJOR: Final[int] = 1

#: Bumped by additive changes. Display ignores a minor it does not know, which is
#: what makes adding a field free.
SCHEMA_MINOR: Final[int] = 2


def manifest_path_in(art_root: Path, wall_id: str) -> Path:
    """Where one wall's manifest lives under a given art root.

    The one place the template is filled in on this side, so a caller cannot
    spell the name a second way — and so the display plane's own copy of the
    template has exactly one thing to agree with.
    """
    return art_root / MANIFEST_FILENAME_TEMPLATE.format(wall_id=wall_id)


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One work that is in the theme and not on the wall, and why."""

    work_id: str
    #: The work's id when the id names no work the catalogue holds, because an
    #: exclusion is read by a curator scanning a list and every row needs a name.
    title: str
    reason: UnplayableReason
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


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One work as the display plane receives it."""

    work_id: str
    #: Relative to `ART_ROOT`. No stored path is absolute, so the two planes can
    #: disagree about where the tree is mounted without disagreeing about this.
    render_path: str
    label: dict[str, str | None]
    #: Minor 2: where a Player on HTTP fetches the render, and how it checks it.
    #: Absent when the Library could not hash the render, and then the entry
    #: plays on the file channel alone.
    media: Media | None = None

    @classmethod
    def of(cls, playable: PlayableWork) -> ManifestEntry:
        """The entry for a work the Library says can go on a wall."""
        return cls(
            work_id=playable.work_id,
            render_path=playable.render_path,
            label=dict(playable.label),
            media=playable.media,
        )


@dataclass(frozen=True, slots=True)
class ManifestBuild:
    """What one build produced — including, deliberately, what it left out."""

    #: Which wall this build is about. Carried so that a surface can name it in
    #: the confirmation — "Hang Winter in the living room" — without asking a
    #: second question; a confirmation that reads correctly only because there is
    #: one possible target silently becomes wrong when a second display arrives.
    #: It is deliberately **not** a field inside the document `as_document`
    #: writes: the wall is carried by the *filename*, which is what makes a
    #: display plane unable to open a wall it does not serve rather than merely
    #: unwilling to act on it. A field would be a second answer to the same
    #: question, and the two could disagree.
    wall: Wall
    theme: Theme
    entries: Sequence[ManifestEntry]
    exclusions: Sequence[Exclusion]
    rotation_interval_seconds: int
    shuffle: bool
    directive_sequence: int
    pinned_work_id: str | None

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


def as_document(build: ManifestBuild) -> dict[str, Any]:
    """The manifest as the display plane parses it.

    Exclusions are **not** in the document. They are curation's report to a
    curator about its own catalogue; the display plane has no use for a list of
    things it is not being asked to show, and putting them here would invite a
    reader to treat the manifest as a catalogue export.
    """
    return {
        "schema": {"major": SCHEMA_MAJOR, "minor": SCHEMA_MINOR},
        "generated_at": datetime.now(UTC).isoformat(),
        "theme": {"id": build.theme.id, "name": build.theme.name},
        "rotation": {
            "interval_seconds": build.rotation_interval_seconds,
            "shuffle": build.shuffle,
        },
        "directive": {
            "sequence": build.directive_sequence,
            "pinned_work_id": build.pinned_work_id,
        },
        "entries": [_entry_document(entry) for entry in build.entries],
    }


def _entry_document(entry: ManifestEntry) -> dict[str, Any]:
    document: dict[str, Any] = {"work_id": entry.work_id, "render_path": entry.render_path, "label": entry.label}
    if entry.media is not None:
        document["media"] = media_document(entry.media)
    return document


def media_document(media: Media) -> dict[str, Any]:
    """An entry's `media` as the document spells it."""
    return {"url": media.url, "sha256": media.sha256, "bytes": media.byte_size, "content_type": media.content_type}


def read_published(path: Path) -> dict[str, Any] | None:
    """The manifest as last published to this path, or None if there is none to patch.

    Programming reads back its own output, never the Library's tables, to learn
    what a wall was last told. A missing file is ordinary: nothing has been hung
    there. An unreadable one is logged and treated the same way, because the
    only thing a caller does with the answer is patch it. A document that cannot
    be read cannot be patched, and the next sync replaces it whole.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("The manifest at %s is not valid JSON (%s); leaving it for the next sync to replace.", path, exc)
        return None
    entries = document.get("entries") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) and isinstance(entry.get("work_id"), str) for entry in entries
    ):
        log.warning("The manifest at %s has no well-formed entry list; leaving it for the next sync to replace.", path)
        return None
    return document


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
        os.replace(temporary, path)
    except BaseException:  # prawduct:allow prawduct/broad-except -- cleanup-and-reraise; the temp file must go on any exit
        # Wider than `Exception` deliberately, and it swallows nothing: a
        # `KeyboardInterrupt` or an early close leaves this body just as surely
        # as an error does, and each one would strand a `.theme-manifest.json.*`
        # file beside the real manifest. The same exception continues.
        Path(temporary).unlink(missing_ok=True)
        raise
