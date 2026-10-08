"""Whether a work can go on a wall, and what the wall is told about it if it can.

**Readiness is the Library's question.** Whether a work has an acquired master,
a current mat colour and a current render, and is not archived, is a fact about
what the collection holds. What a curator has chosen to put on which wall is
Programming's. Programming asks through `facade.py` and receives the answer as
plain data, never as the records it was judged from.

**Readiness is evaluated, never stored.** There is no readiness flag on a work to
drift out of step with the facts. It is judged here, once per ask, and the wall
sees only what survived. That is what makes "the wall selects a work it cannot
render" structurally impossible rather than defended against.

**The cost of that design is that a work can sit in a theme and never reach the
wall**, and silence is this product's characteristic failure. So every refusal
here carries a reason a curator can act on, and the manifest build reports each
one by name.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Final

from arrt.persistence.records import (
    Artist,
    Artwork,
    ArtworkStatus,
    MatColor,
    Original,
    Rendition,
    is_current,
    tv_renditions_newest_first,
)


class UnplayableReason(StrEnum):
    """Why a work cannot go on a wall.

    Each value is a distinct thing a curator would do something different about,
    which is the test for whether a reason earns its own name: an archived work
    is a decision, a missing original is acquisition's job, and a stale rendition
    is the renderer's.
    """

    #: Out of circulation. Theme membership is curatorial and survives archiving,
    #: so the work stays in the theme and simply stops being shown.
    ARCHIVED = "archived"
    #: No master image has been acquired, so there is nothing to render from.
    NO_ORIGINAL = "no_original"
    #: Nothing has been rendered for the television yet.
    NO_RENDITION = "no_rendition"
    #: A render exists but was made from a different image than the work now
    #: holds — showing it would put the previous acquisition on the wall.
    STALE_RENDITION = "stale_rendition"
    #: No mat colour is current, so the work has no composed presentation.
    NO_MAT_COLOR = "no_mat_color"
    #: The id names no work the catalogue holds. Programming keeps work ids as
    #: references that may fail to resolve, because once its tables live in a
    #: file of their own nothing stops a work being deleted out from under a
    #: theme. Answered as a reason rather than raised, so a manifest build can
    #: name it beside the others and carry on.
    NOT_IN_CATALOGUE = "not_in_catalogue"


#: Where the Library serves a render, by the hash of its bytes. The Library's,
#: because the manifest names Library-served media: after a split this is
#: rewritten to name the Library's host and no Player changes, since each one
#: resolves the URL against the manifest's own. `contract/routes.json` holds the
#: same template, and the HTTP route is mounted from it.
MEDIA_PATH_TEMPLATE: Final[str] = "/media/sha256-{sha256}"

#: The content types the contract allows, by file suffix. A render in any other
#: format is not offered as media.
CONTENT_TYPES: Final[Mapping[str, str]] = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


@dataclass(frozen=True, slots=True)
class Media:
    """Where a render is fetched from and how to know it arrived whole."""

    url: str
    sha256: str
    byte_size: int
    content_type: str


def media_of(rendition: Rendition) -> Media | None:
    """The render as media, or None if it has no recorded hash or an unservable type."""
    content_type = CONTENT_TYPES.get(PurePosixPath(rendition.relative_path).suffix.lower())
    if rendition.content_sha256 is None or rendition.byte_size is None or content_type is None:
        return None
    return Media(
        url=MEDIA_PATH_TEMPLATE.format(sha256=rendition.content_sha256),
        sha256=rendition.content_sha256,
        byte_size=rendition.byte_size,
        content_type=content_type,
    )


@dataclass(frozen=True, slots=True)
class PlayableWork:
    """A work that can go on a wall, as the wall is to be told about it."""

    work_id: str
    title: str
    #: Relative to `ART_ROOT`. No stored path is absolute, so the two planes can
    #: disagree about where the tree is mounted without disagreeing about this.
    render_path: str
    label: Mapping[str, str | None]
    #: None when the render's file could not be hashed. The work still plays on
    #: the file channel, which reads `render_path`; a Player on HTTP skips it.
    media: Media | None = None


@dataclass(frozen=True, slots=True)
class Unplayable:
    """A work that cannot go on a wall, and why."""

    work_id: str
    #: None only when the id names no work, so there is no title to give.
    title: str | None
    reason: UnplayableReason
    #: A sentence a curator can act on, not a restatement of the enum.
    detail: str


@dataclass(frozen=True, slots=True)
class WorkInputs:
    """Everything the readiness rule needs about one work, gathered by the caller.

    A record rather than a store handle so the rule below is a pure function of
    stated facts: it can be read, and tested, without a database.
    """

    artwork: Artwork
    artist: Artist | None
    original: Original | None
    tv_rendition: Rendition | None
    mat_color: MatColor | None


def not_in_catalogue(work_id: str) -> Unplayable:
    """The answer for an id that resolves to nothing.

    The detail is the sentence the catalogue service refuses an unknown id with,
    so a curator hears the same thing whichever way they asked.
    """
    return Unplayable(
        work_id=work_id,
        title=None,
        reason=UnplayableReason.NOT_IN_CATALOGUE,
        detail=f"No artwork with id {work_id!r} is in the catalogue.",
    )


def assess(inputs: WorkInputs) -> Unplayable | None:
    """Judge one work's readiness. `None` means it can go on a wall.

    **"The fetch succeeded" is deliberately not a sixth check.** Holding an
    original is what a succeeded fetch produces, so the condition is already
    carried by `NO_ORIGINAL`. Reading it as "the *last* fetch attempt succeeded"
    would take a work off the wall because a later re-acquisition failed while a
    perfectly good original and a current render were still held — a regression
    dressed as a safety check.
    """
    artwork = inputs.artwork
    if artwork.status is ArtworkStatus.ARCHIVED:
        return _unplayable(artwork, UnplayableReason.ARCHIVED, "It has been archived, so it is out of circulation.")
    if inputs.original is None:
        return _unplayable(
            artwork,
            UnplayableReason.NO_ORIGINAL,
            "No master image has been acquired for it yet.",
        )
    if inputs.mat_color is None:
        return _unplayable(
            artwork,
            UnplayableReason.NO_MAT_COLOR,
            "No mat colour has been chosen, so it has no composed presentation.",
        )
    if inputs.tv_rendition is None:
        return _unplayable(
            artwork,
            UnplayableReason.NO_RENDITION,
            "It has a master image but has not been rendered for the television yet.",
        )
    # Through the shared predicate, because it already owns what "current"
    # means. This re-derived it inline, so a change to the rule would have
    # decided manifest membership by the old one while the review grid used the
    # new — the work badged current and silently dropped from the wall.
    if not is_current(inputs.tv_rendition, inputs.original):
        return _unplayable(
            artwork,
            UnplayableReason.STALE_RENDITION,
            "Its render was made from an earlier acquisition and needs regenerating.",
        )
    return None


def playable_from(inputs: WorkInputs) -> PlayableWork:
    """Turn a ready work into what the wall is told about it.

    Label *text* crosses to the display plane; label *rendering* does not. The
    e-paper panel's geometry belongs to the plane that owns that panel, so what
    goes here is the words and nothing about how they are set.

    **The artist's name crosses three times over, and that is not redundancy.**
    `artist` is what the source called them, `artist_family_name` and
    `artist_given_name` are which part is which. A display plane setting the
    family name apart needs the parts; one drawing a plain line needs
    the whole; and a work whose artist has no recorded parts has only the whole.
    Sending the parts alone would make the third case unlabelable, and sending
    the whole alone would put the split back where it was refused — in a rule
    over a string that is wrong for "van Gogh".
    """
    if inputs.tv_rendition is None:
        # Raised rather than asserted: `assert` disappears under -O, and what it
        # would have caught is a caller that skipped `assess` — which would put a
        # work with no render into the manifest and take the wall down to a
        # missing file rather than to a named exclusion.
        raise ValueError(f"Work {inputs.artwork.id!r} has no television render; call assess before playable_from.")
    return PlayableWork(
        work_id=inputs.artwork.id,
        title=inputs.artwork.title,
        render_path=inputs.tv_rendition.relative_path,
        media=media_of(inputs.tv_rendition),
        label=label_of(inputs.artwork, inputs.artist),
    )


def label_of(artwork: Artwork, artist: Artist | None) -> Mapping[str, str | None]:
    """The ten text keys a label is set from, for the manifest and the label document alike.

    One function for both, so a wall's manifest and the label captioning that
    wall cannot set one work in two ways.
    """
    # Read-only, so the answer is as frozen as the dataclass holding it: nothing
    # a caller does to the label can change what the next caller is told.
    return MappingProxyType(
        {
            "title": artwork.title,
            "artist": None if artist is None else artist.name,
            "artist_family_name": None if artist is None else artist.family_name,
            "artist_given_name": None if artist is None else artist.given_name,
            # **The short form wins, and the fallback resolves here rather than at
            # the panel.** The manifest is what the display plane parses, not a
            # catalogue export, so it carries the string the label should set;
            # which of two recorded strings that is, is a question about content,
            # and content is the Library's. A display told to choose would be
            # re-deciding curation policy from the far side of the seam.
            "artist_nationality": None if artist is None else (artist.display_nationality or artist.nationality),
            "artist_dates": None if artist is None else _artist_dates(artist),
            "date_created": artwork.date_created,
            "medium": artwork.medium,
            "dimensions": artwork.dimensions,
            "commentary": artwork.commentary,
        }
    )


def tv_rendition_of(renditions: Sequence[Rendition]) -> Rendition | None:
    """The television render the wall would use, or None if there is none.

    The preference itself lives with the records, so the thumbnail service can
    walk the same order and the two cannot pick different pictures of the same
    work. Stale renders are included on purpose — `assess` needs one in hand to
    say "needs regenerating" rather than "never rendered".
    """
    ordered = tv_renditions_newest_first(renditions)
    return ordered[0] if ordered else None


def _unplayable(artwork: Artwork, reason: UnplayableReason, detail: str) -> Unplayable:
    return Unplayable(work_id=artwork.id, title=artwork.title, reason=reason, detail=detail)


def _artist_dates(artist: Artist) -> str | None:
    """The dates as they should read on a label.

    The stored text wins when there is any, because it came from the source and
    carries forms — "c. 1450–1516", "active 1520s" — that two integers cannot.
    Falling back to the years means a work whose artist has only one known date
    still gets a legible label rather than nothing.
    """
    if artist.lifespan_text:
        return artist.lifespan_text
    if artist.born is None and artist.died is None:
        return None
    return f"{artist.born or ''}–{artist.died or ''}"
