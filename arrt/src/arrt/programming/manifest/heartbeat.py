"""The narrow reverse channel: what the display plane says about itself.

The manifest runs curation → display. This is the only thing that runs the other
way, and it is deliberately not a dependency: display writes this file and never
checks whether anyone read it, so curation being absent changes nothing about the
wall. Curation reading a stale one, or none at all, is likewise not an error — it
is an observation, and this module's job is to report it as one.

**Nothing here decides whether the display plane is healthy.** It reports what was
found and how old it is, in absolute terms. A green dot is a verdict, and a
verdict computed from a file that may simply be young is how a health surface
starts lying: the reader is told the age and decides.

The writer is the display plane's — `arrt-player/src/arrt_player/heartbeat.py`, which
declares the same two names and is held to them by
`tests/preferences/test_heartbeat_contract.py`, since neither plane can import
the other to check. A heartbeat that has never been written is still an ordinary
answer and is reported as one: a fresh deployment has no writer running yet, and
that is a true and useful thing to say rather than a zero that reads like a
reading.

The parse is `observations.observe`'s, shared with the backup receipt — the same
document-with-an-instant, read for the same panel. Three things are this module's
own: the filename, the key, and the sentence.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from arrt import observations

#: Written into `ART_ROOT` by the display plane, **one file per wall**. Not
#: configurable, for the same reason the manifest's name is not: both planes must
#: agree where it is.
#:
#: Per wall because health has to be able to name *which* wall is silent, and one
#: shared file has no way to say it — the second display would simply overwrite
#: the first's report, and a wall that had stopped reporting would look like a
#: wall that was fine.
HEARTBEAT_FILENAME_TEMPLATE: Final[str] = "display-heartbeat-{wall_id}.json"

#: The key carrying the instant, and a contract rather than a preference. A writer
#: that spells it `timestamp` produces a plane that looks *down* to curation while
#: running perfectly — this product's defining failure mode manufactured by the
#: mechanism built to detect it. `observability-strategy.md` names it for the same
#: reason. Everything else in the document is the writer's to shape.
REPORTED_AT_KEY: Final[str] = "reported_at"

#: How often a Player reports each wall's heartbeat: `arrt-player/src/arrt_player/
#: heartbeat.py`'s `INTERVAL_SECONDS`. Written again here because neither plane
#: imports the other; `tests/preferences/test_staleness_threshold.py` holds this,
#: the Player's and the browser's (`static/core/outputs.js`) to one number.
INTERVAL_SECONDS: Final[float] = 60.0

#: Past this age a wall's report says nothing about now, and the wall is
#: `silent`. Three missed reports, not one: a report a few seconds late is a busy
#: Pi, and three in a row is a Player that has stopped. The browser's
#: `STALE_AFTER_SECONDS` is the same expression, so Walls and the server cannot
#: call one report current and stale at once.
STALE_AFTER_SECONDS: Final[float] = 3 * INTERVAL_SECONDS

#: Minor 3's `display_state.state`: what a wall's controller can say its screen
#: is doing (`contract/schemas/heartbeat.v1.schema.json`).
REPORTED_DISPLAY_STATES: Final[frozenset[str]] = frozenset({"showing_art", "in_use", "dark", "no_screen", "unreachable"})

#: RFC 3339 with an offset, the schema's pattern for `display_state.since`.
_INSTANT: Final[re.Pattern[str]] = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})"
)


@dataclass(frozen=True, slots=True)
class HeartbeatReading:
    """What curation can observe about the display plane, stated as observation.

    `absent` and `unreadable` are different answers on purpose. Nothing has ever
    run is a normal state on a fresh deployment; a file that exists and will not
    parse is a fault, and collapsing the two would hide it.
    """

    path: Path
    #: None when no heartbeat file exists at all.
    reported_at: datetime | None
    #: How long ago it was written, in seconds. None when there is nothing to age.
    age_seconds: float | None
    #: The document as display wrote it, or None if absent or unreadable.
    contents: dict[str, Any] | None
    #: Set when a file is present but could not be read as a heartbeat.
    problem: str | None

    @property
    def absent(self) -> bool:
        """True when the display plane has never written a heartbeat here."""
        return self.contents is None and self.problem is None

    def describe(self) -> str:
        """One sentence stating what was observed, never a verdict about it.

        The age is in the unit a person reads it in rather than in seconds. A
        display plane down since Tuesday reported "345600 seconds ago", which is
        a conversion the reader has to do on the one surface built so they would
        not have to — and `observability-strategy.md` states the target wording.
        """
        if self.absent:
            return f"No heartbeat file exists at {self.path}; the display plane has not reported yet."
        if self.problem is not None:
            return f"The heartbeat file at {self.path} could not be read: {self.problem}"
        return f"The display plane last reported {observations.ago(self.age_seconds)}."


def heartbeat_path_in(art_root: Path, wall_id: str) -> Path:
    """Where one wall's heartbeat lives under a given art root.

    The one place the template is filled in on this side, mirroring the display
    plane's `path_in` — which is the only thing this has to agree with.
    """
    return art_root / HEARTBEAT_FILENAME_TEMPLATE.format(wall_id=wall_id)


def problem_with(document: object) -> str | None:
    """Why this document is not a heartbeat this plane can read, or None if it is.

    The same test `read` applies to a file, so a heartbeat accepted over HTTP is
    one the health panel will show and never one it reports as unreadable. A
    `schema` major other than 1 is refused too, because the contract says a
    reader refuses a major it does not know.
    """
    if not isinstance(document, dict):
        return "a heartbeat is a JSON object."
    if observations.instant(document.get(REPORTED_AT_KEY)) is None:
        return f"a heartbeat carries a readable {REPORTED_AT_KEY!r} timestamp."
    schema = document.get("schema")
    if schema is not None and (not isinstance(schema, dict) or schema.get("major") != 1):
        return "this plane reads heartbeat schema major 1."
    if "capabilities" in document:
        problem = _problem_with_screen(document["capabilities"])
        if problem is not None:
            return problem
    if "display_state" in document:
        return _problem_with_display_state(document["display_state"])
    return None


def _problem_with_screen(capabilities: object) -> str | None:
    """Minor 2's `capabilities.screen`, the one part of the capabilities this server reads.

    Refused rather than dropped: Programming judges which works are too small
    for the wall from it, and a size it quietly ignored would leave that
    judgement unmade with nothing saying why. The rest of the capabilities is
    not checked here, because nothing here reads it yet.
    """
    if not isinstance(capabilities, dict):
        return "'capabilities' is an object."
    screen = capabilities.get("screen")
    if not isinstance(screen, dict):
        return "'capabilities.screen' is an object of 'width_px' and 'height_px'."
    for key in ("width_px", "height_px"):
        value = screen.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return f"'capabilities.screen.{key}' is a whole number of pixels, at least 1."
    return None


def _problem_with_display_state(value: object) -> str | None:
    """Minor 3's `display_state`, checked as the schema states it.

    Refused rather than stored, because Walls and every label read this record:
    a malformed one, or a work named beside a screen that is not showing art,
    would be shown as a fact about the room. **A state name this server does
    not know is not refused**: minors only add, and Players upgrade before the
    server (`player-contract.md`), so refusing it would turn every heartbeat of
    an upgraded Player into a silent wall. It is read as unreachable instead
    (`display_state.reported_state`), and the rest of the heartbeat stands.
    """
    if not isinstance(value, dict) or set(value) != {"state", "work_id", "since"}:
        return "'display_state' is an object of exactly 'state', 'work_id' and 'since'."
    state = value["state"]
    if not isinstance(state, str) or not state:
        return "'display_state.state' is a state name."
    work_id = value["work_id"]
    if work_id is not None and not isinstance(work_id, str):
        return "'display_state.work_id' is a work id, or null."
    if work_id is not None and state in REPORTED_DISPLAY_STATES and state != "showing_art":
        return "'display_state.work_id' names a work only while the state is showing_art."
    since = value["since"]
    if not isinstance(since, str) or _INSTANT.fullmatch(since) is None:
        return "'display_state.since' is an RFC 3339 timestamp with an offset."
    return None


def read(path: Path, *, now: datetime | None = None) -> HeartbeatReading:
    """Observe the heartbeat file. Absent is an answer, not a failure."""
    seen = observations.observe(path, key=REPORTED_AT_KEY, now=now)
    # The same test the HTTP route applies, so a file written some other way
    # reads as unreadable on every screen alike, never current on one and
    # silent on another.
    problem = seen.problem or (problem_with(seen.contents) if seen.contents is not None else None)
    return HeartbeatReading(
        path=seen.path,
        reported_at=seen.at,
        age_seconds=seen.age_seconds,
        contents=seen.contents,
        problem=problem,
    )
