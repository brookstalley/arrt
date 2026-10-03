"""What a client says about its outputs: which exist, which are connected, at what size.

`clients.md` § What stays on the client. The server stores which output a wall is
shown on *by name*, and nothing else about the device; the client reports the
rest here so a curator can choose an output by its name. Kept as a file under the
art root beside the wall heartbeats, which is where `clients.md` puts it, and read
as an observation with an age, never a verdict.

**The checks in `problem_with` are `contract/schemas/client-heartbeat.v1.schema.json`
stated in code**, because the server does not carry a schema validator at run
time. `arrt/tests/contract/test_client_surface.py` holds the two to each other:
every fixture the contract calls valid is accepted here, and every invalid one is
refused. One rule is the server's own, because a schema cannot state it: two
outputs may not share a name, since the name is how a wall is placed on one.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from arrt import observations

#: One file per client, beside `display-heartbeat-{wall_id}.json`.
CLIENT_HEARTBEAT_FILENAME_TEMPLATE: Final[str] = "client-heartbeat-{client_id}.json"

#: The key carrying the instant, spelled as the wall heartbeat spells it.
REPORTED_AT_KEY: Final[str] = "reported_at"

#: The output kinds `player-contract.md` names: a Samsung Frame's own art store,
#: and a screen the client draws to itself.
OUTPUT_KINDS: Final[frozenset[str]] = frozenset({"frame", "framebuffer"})

#: RFC 3339 with an offset, the schema's pattern exactly, so the server and the
#: schema refuse the same spellings.
_INSTANT: Final[re.Pattern[str]] = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})"
)


@dataclass(frozen=True, slots=True)
class ReportedOutput:
    """One output as the client last reported it."""

    name: str
    kind: str
    connected: bool
    #: (width, height) in pixels, or None when the client does not know it — an
    #: unplugged connector, or a Frame that is asleep.
    screen: tuple[int, int] | None


@dataclass(frozen=True, slots=True)
class ClientHeartbeatReading:
    """What the server can observe about one client, stated as observation."""

    path: Path
    reported_at: datetime | None
    age_seconds: float | None
    #: Empty when nothing readable has been reported, which `absent` and
    #: `problem` tell apart.
    outputs: Sequence[ReportedOutput]
    problem: str | None
    absent: bool

    def output_names(self) -> set[str] | None:
        """The names of the outputs last reported, or None when none have been readably."""
        if self.absent or self.problem is not None:
            return None
        return {output.name for output in self.outputs}


def client_heartbeat_path_in(art_root: Path, client_id: str) -> Path:
    """Where one client's heartbeat lives under a given art root."""
    return art_root / CLIENT_HEARTBEAT_FILENAME_TEMPLATE.format(client_id=client_id)


def problem_with(document: object) -> str | None:
    """Why this is not a client heartbeat, in words a Player's operator can act on, or None."""
    if not isinstance(document, dict):
        return "a client heartbeat is a JSON object."
    instant = document.get(REPORTED_AT_KEY)
    if not isinstance(instant, str) or _INSTANT.fullmatch(instant) is None:
        return f"it carries {REPORTED_AT_KEY!r} as an RFC 3339 timestamp with an offset."
    outputs = document.get("outputs")
    if not isinstance(outputs, list):
        return "it carries 'outputs', a list of the client's outputs (which may be empty)."
    seen: set[str] = set()
    for index, output in enumerate(outputs):
        problem = _problem_with_output(output)
        if problem is not None:
            return f"output {index}: {problem}"
        if output["name"] in seen:
            return f"two outputs are both called {output['name']!r}; an output's name is how a wall is placed on it."
        seen.add(output["name"])
    return None


def _problem_with_output(output: object) -> str | None:
    if not isinstance(output, dict):
        return "each output is a JSON object."
    name = output.get("name")
    if not isinstance(name, str) or not name:
        return "'name' is the output's name, non-empty text."
    if output.get("kind") not in OUTPUT_KINDS:
        return f"'kind' is one of {', '.join(sorted(OUTPUT_KINDS))}."
    if not isinstance(output.get("connected"), bool):
        return "'connected' is true or false."
    if "screen" not in output:
        return "'screen' is [width, height] in pixels, or null when unknown."
    screen = output["screen"]
    if screen is not None and not (
        isinstance(screen, list)
        and len(screen) == 2
        and all(isinstance(side, int) and not isinstance(side, bool) and side >= 1 for side in screen)
    ):
        return "'screen' is [width, height] in pixels, or null when unknown."
    return None


def read(path: Path, *, now: datetime | None = None) -> ClientHeartbeatReading:
    """Observe a client's heartbeat file. Absent is an answer, not a failure."""
    seen = observations.observe(path, key=REPORTED_AT_KEY, now=now)
    problem = seen.problem
    outputs: list[ReportedOutput] = []
    if seen.contents is not None and problem is None:
        problem = problem_with(seen.contents)
        if problem is None:
            outputs = [_output(entry) for entry in seen.contents["outputs"]]
    return ClientHeartbeatReading(
        path=seen.path,
        reported_at=seen.at,
        age_seconds=seen.age_seconds,
        outputs=outputs,
        problem=problem,
        absent=seen.absent,
    )


def _output(entry: dict[str, Any]) -> ReportedOutput:
    screen = entry["screen"]
    return ReportedOutput(
        name=entry["name"],
        kind=entry["kind"],
        connected=entry["connected"],
        screen=None if screen is None else (screen[0], screen[1]),
    )
