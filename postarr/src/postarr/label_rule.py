"""The label rule: caption, card or blank, from one label document and one clock.

`labels-and-surfaces.md` § What a label says, as one pure function run identically
by every renderer, wherever it is. The server sends what is so (the wall's display
state, with since, and the text a caption would carry) and never what to draw;
the renderer decides here. **It decides rather than being told because the
30-minute hold has to run while the server is unreachable**, and only a rule the
renderer holds can run then (`player-contract.md` § Transport).

Every renderer, on every platform, runs `contract/vectors/label-rule.json`; this
one does in `tests/test_label_rule.py`. Nothing here does I/O, reads a clock or
logs: the renderer (`label_renderer.py`) does all three and hands this its
answers, which is what lets a mutation sweep and the vectors reach every branch.
"""

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final

#: The label document's major (`contract/schemas/label.v1.schema.json`). A
#: document of another major is refused whole, and the last good one is kept.
SCHEMA_MAJOR: Final[int] = 1

#: Every state the label schema names: the controller's five and the server's two.
SHOWING_ART: Final[str] = "showing_art"
UNASSIGNED: Final[str] = "unassigned"
UNREACHABLE: Final[str] = "unreachable"
#: Somebody is using the screen, it is off, or there is none: nothing to caption.
BLANK_STATES: Final[frozenset[str]] = frozenset({"in_use", "dark", "no_screen"})
#: The wall cannot say what it shows: the last caption is held, then blanked.
HELD_STATES: Final[frozenset[str]] = frozenset({"silent", UNREACHABLE})
STATES: Final[frozenset[str]] = BLANK_STATES | HELD_STATES | {SHOWING_ART, UNASSIGNED}

#: How long a held state keeps its caption. **The owner's number, 2026-10-08**
#: (`labels-and-surfaces.md` § Rulings 4): long enough that an overnight Wi-Fi
#: blip leaves the room its caption, short enough that a wall gone for good stops
#: naming a picture nobody can confirm. The vectors carry it as `hold_seconds`.
HOLD: Final[timedelta] = timedelta(minutes=30)


class Outcome(StrEnum):
    """What a label surface shows."""

    #: The work's label text.
    CAPTION = "caption"
    #: A quiet card with the wall's name.
    CARD = "card"
    #: Nothing.
    BLANK = "blank"


class LabelDocumentUnreadable(Exception):
    """A label document this reader will not act on."""


@dataclass(frozen=True)
class LabelDocument:
    """What `GET /labels/{label_id}` answered, as this reader holds it."""

    wall_id: str
    wall_name: str
    #: As the server spelled it, kept even when this reader does not know it: the
    #: rule reads an unknown state as unreachable, and a log line should say what
    #: was actually sent.
    state: str
    work_id: str | None
    since: datetime | None
    #: The ten text keys, or None.
    label: dict[str, Any] | None


def parse_label_document(text: str) -> LabelDocument:
    """Read a label document, or refuse it whole.

    **Refused rather than read in part**, as the client document is: a document
    with no state, or an unreadable since, is one where any outcome would be a
    guess. A state name this reader does not know is not a refusal; the rule reads
    it as unreachable, which is the contract's instruction for a later minor.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LabelDocumentUnreadable(f"the label document is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise LabelDocumentUnreadable(f"the label document is a {type(document).__name__}, not an object")
    schema = document.get("schema")
    major = schema.get("major") if isinstance(schema, dict) else None
    if major != SCHEMA_MAJOR:
        raise LabelDocumentUnreadable(f"the label document is major {major!r}, and this reader knows {SCHEMA_MAJOR}")
    wall_id, wall_name = document.get("wall_id"), document.get("wall_name")
    if not _text(wall_id) or not _text(wall_name):
        raise LabelDocumentUnreadable("the label document carries no wall_id or wall_name")
    shown = document.get("display_state")
    if not isinstance(shown, dict) or not _text(shown.get("state")):
        raise LabelDocumentUnreadable("the label document carries no display state")
    work_id = shown.get("work_id")
    if work_id is not None and not _text(work_id):
        raise LabelDocumentUnreadable("the label document's work_id is not an id")
    label = document.get("label")
    if label is not None and not isinstance(label, dict):
        raise LabelDocumentUnreadable("the label document's label is not an object")
    return LabelDocument(
        wall_id=wall_id,
        wall_name=wall_name,
        state=shown["state"],
        work_id=work_id,
        since=_instant(shown.get("since")),
        label=label,
    )


def _instant(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LabelDocumentUnreadable("the label document's since is not a string")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LabelDocumentUnreadable(f"the label document's since is not an instant: {value!r}") from exc
    if instant.tzinfo is None:
        raise LabelDocumentUnreadable(f"the label document's since carries no offset: {value!r}")
    return instant


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def outcome(document: LabelDocument, now: datetime) -> Outcome:
    """caption, card or blank for one label document at one instant. The rule, whole."""
    state = document.state if document.state in STATES else UNREACHABLE
    if state == SHOWING_ART:
        return Outcome.CAPTION if document.label is not None else Outcome.CARD
    if state == UNASSIGNED:
        return Outcome.CARD
    if state in BLANK_STATES:
        return Outcome.BLANK
    if document.label is None or document.since is None:
        return Outcome.BLANK
    # A since later than now is a held state just entered, so it captions.
    return Outcome.CAPTION if now - document.since < HOLD else Outcome.BLANK


def offline(document: LabelDocument | None, last_answer: datetime | None) -> LabelDocument | None:
    """The document as this renderer reads it while it cannot reach the server.

    **The server going away is the wall going silent, as far as a label can
    tell**, so the last document is read as `unreachable` from the last instant
    the server answered, and the rule's hold runs from there. A document already
    in a held state keeps its own since, which is earlier. Only a caption is
    held: a blank stays blank, and a card (which names the wall, not a work) has
    no caption to hold, so it blanks. With no document at all there is nothing to
    hold either.
    """
    if document is None:
        return None
    state = document.state if document.state in STATES else UNREACHABLE
    if state in HELD_STATES:
        return document
    label = document.label if state == SHOWING_ART else None
    return replace(document, state=UNREACHABLE, work_id=None, since=last_answer, label=label)


@dataclass(frozen=True)
class Drawing:
    """What a panel is to show, compared by what it would look like.

    **Two drawings are equal when they would put the same ink down**, which is
    what decides a redraw: an e-paper redraw flashes the panel for about 2 s, so
    one is spent only when the outcome or its content changes. The work and the
    state ride along for the journal and are left out of the comparison.
    """

    outcome: Outcome
    #: The label text, with `CAPTION`.
    label: dict[str, Any] | None = None
    #: The wall's name, with `CARD`.
    wall_name: str | None = None
    work_id: str | None = field(default=None, compare=False)
    state: str | None = field(default=None, compare=False)


def drawing_for(document: LabelDocument | None, now: datetime) -> Drawing:
    """The drawing a document asks for at an instant; blank with no document."""
    if document is None:
        return Drawing(Outcome.BLANK)
    chosen = outcome(document, now)
    if chosen is Outcome.CAPTION:
        return Drawing(Outcome.CAPTION, label=document.label, work_id=document.work_id, state=document.state)
    if chosen is Outcome.CARD:
        return Drawing(Outcome.CARD, wall_name=document.wall_name, state=document.state)
    return Drawing(Outcome.BLANK, state=document.state)
