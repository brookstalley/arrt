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
outputs may not share a name, nor two label outputs, since the name is how a wall
or a label is placed on one.
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

#: The label output kinds `player-contract.md` names: an e-paper panel.
LABEL_OUTPUT_KINDS: Final[frozenset[str]] = frozenset({"epaper"})

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
    #: Who the display is, as the client read it from the device; None for an
    #: output with no identity a client can read (an HDMI connector), and for a
    #: Frame whose id could not be read this time.
    identity: str | None = None


@dataclass(frozen=True, slots=True)
class ReportedLabelOutput:
    """One label output as the client last reported it."""

    name: str
    kind: str
    connected: bool
    #: (width, height) in pixels, or None when the client does not know it.
    size: tuple[int, int] | None


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
    #: Empty when none were reported, which is also what a client before label
    #: outputs existed says.
    label_outputs: Sequence[ReportedLabelOutput] = ()

    def output_names(self) -> set[str] | None:
        """The names of the outputs last reported, or None when none have been readably."""
        if self.absent or self.problem is not None:
            return None
        return {output.name for output in self.outputs}

    def label_output_names(self) -> set[str] | None:
        """The names of the label outputs last reported, or None when nothing has been readably."""
        if self.absent or self.problem is not None:
            return None
        return {label.name for label in self.label_outputs}

    def describe(self) -> str:
        """This reading as one sentence, the same words on every surface that shows it.

        Three states and three sentences, because they send the curator to three
        different places: a client that has never reported has not been started
        (or cannot reach this server), a report that cannot be read is a Player
        writing something this server does not understand, and a report with an
        age is the ordinary case, whose age is the whole of what it says.
        """
        if self.absent:
            return "It has not reported its outputs yet."
        if self.problem is not None:
            return f"Its last report could not be read: {self.problem}"
        # A report present and readable always carries its age: `observe` sets a
        # problem for every document whose instant it cannot read.
        return f"It last reported {observations.ago(self.age_seconds or 0.0)}."


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
    return _problem_with_label_outputs(document)


def _problem_with_label_outputs(document: dict[str, Any]) -> str | None:
    if "label_outputs" not in document:
        return None
    label_outputs = document["label_outputs"]
    if not isinstance(label_outputs, list):
        return "'label_outputs' is a list of the client's label outputs, when it carries one."
    seen: set[str] = set()
    for index, label_output in enumerate(label_outputs):
        problem = _problem_with_label_output(label_output)
        if problem is not None:
            return f"label output {index}: {problem}"
        if label_output["name"] in seen:
            return (
                f"two label outputs are both called {label_output['name']!r}; "
                "a label output's name is how a label is placed on it."
            )
        seen.add(label_output["name"])
    return None


def _problem_with_label_output(label_output: object) -> str | None:
    if not isinstance(label_output, dict):
        return "each label output is a JSON object."
    name = label_output.get("name")
    if not isinstance(name, str) or not name:
        return "'name' is the label output's name, non-empty text."
    if label_output.get("kind") not in LABEL_OUTPUT_KINDS:
        return f"'kind' is one of {', '.join(sorted(LABEL_OUTPUT_KINDS))}."
    if not isinstance(label_output.get("connected"), bool):
        return "'connected' is true or false."
    if "size" not in label_output or not _is_size(label_output["size"]):
        return "'size' is [width, height] in pixels, or null when unknown."
    return None


def _is_size(size: object) -> bool:
    """[width, height] in whole pixels, or null."""
    return size is None or (
        isinstance(size, list)
        and len(size) == 2  # noqa: PLR2004 -- a size is [width, height]
        and all(isinstance(side, int) and not isinstance(side, bool) and side >= 1 for side in size)
    )


def _problem_with_output(output: object) -> str | None:  # noqa: PLR0911 -- one return per field check, each naming its problem
    if not isinstance(output, dict):
        return "each output is a JSON object."
    name = output.get("name")
    if not isinstance(name, str) or not name:
        return "'name' is the output's name, non-empty text."
    if output.get("kind") not in OUTPUT_KINDS:
        return f"'kind' is one of {', '.join(sorted(OUTPUT_KINDS))}."
    if not isinstance(output.get("connected"), bool):
        return "'connected' is true or false."
    if "screen" not in output or not _is_size(output["screen"]):
        return "'screen' is [width, height] in pixels, or null when unknown."
    if "identity" in output and not (isinstance(output["identity"], str) and output["identity"]):
        return "'identity' is the id the client read from the device, non-empty text, or absent."
    return None


def read(path: Path, *, now: datetime | None = None) -> ClientHeartbeatReading:
    """Observe a client's heartbeat file. Absent is an answer, not a failure."""
    seen = observations.observe(path, key=REPORTED_AT_KEY, now=now)
    problem = seen.problem
    outputs: list[ReportedOutput] = []
    label_outputs: list[ReportedLabelOutput] = []
    if seen.contents is not None and problem is None:
        problem = problem_with(seen.contents)
        if problem is None:
            outputs = [_output(entry) for entry in seen.contents["outputs"]]
            label_outputs = [_label_output(entry) for entry in seen.contents.get("label_outputs", [])]
    return ClientHeartbeatReading(
        path=seen.path,
        reported_at=seen.at,
        age_seconds=seen.age_seconds,
        outputs=outputs,
        problem=problem,
        absent=seen.absent,
        label_outputs=label_outputs,
    )


def _output(entry: dict[str, Any]) -> ReportedOutput:
    screen = entry["screen"]
    return ReportedOutput(
        name=entry["name"],
        kind=entry["kind"],
        connected=entry["connected"],
        screen=None if screen is None else (screen[0], screen[1]),
        identity=entry.get("identity"),
    )


def _label_output(entry: dict[str, Any]) -> ReportedLabelOutput:
    size = entry["size"]
    return ReportedLabelOutput(
        name=entry["name"],
        kind=entry["kind"],
        connected=entry["connected"],
        size=None if size is None else (size[0], size[1]),
    )
