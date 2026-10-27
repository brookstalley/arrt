"""The server's and the browser's idea of a stale report is the contract's.

Walls and Clients call a report stale past three heartbeat intervals
(`static/core/outputs.js`), and the server calls a wall `silent` past the same
threshold (`programming/manifest/heartbeat.py`). Both are written against the
contract's timing (`contract/timing.json`), which the Player paces its heartbeats
by and holds itself to in its own suite. Walls reads the server's display state
beside the browser's report ages, so one report must not be current to one and
stale to the other.
"""

import re
from pathlib import Path

from arrt_contract import timing

from arrt.programming.manifest import heartbeat

OUTPUTS_JS = Path(__file__).resolve().parents[2] / "src" / "arrt" / "http" / "static" / "core" / "outputs.js"

_CLIENT_INTERVAL = re.compile(r"^export const HEARTBEAT_INTERVAL_SECONDS = (\d+(?:\.\d+)?);$", re.MULTILINE)
_CLIENT_THRESHOLD = re.compile(r"^export const STALE_AFTER_SECONDS = (\d+) \* HEARTBEAT_INTERVAL_SECONDS;$", re.MULTILINE)


def client_interval(source: str) -> float:
    found = _CLIENT_INTERVAL.findall(source)
    assert len(found) == 1, "core/outputs.js declares HEARTBEAT_INTERVAL_SECONDS once, as a number"
    return float(found[0])


def client_intervals_to_stale(source: str) -> int:
    found = _CLIENT_THRESHOLD.findall(source)
    assert len(found) == 1, "core/outputs.js declares STALE_AFTER_SECONDS once, as a count of intervals"
    return int(found[0])


def test_the_server_paces_staleness_by_the_contract():
    agreed = timing()

    assert agreed["heartbeat_interval_seconds"] == heartbeat.INTERVAL_SECONDS
    assert agreed["stale_after_intervals"] * agreed["heartbeat_interval_seconds"] == heartbeat.STALE_AFTER_SECONDS


def test_the_browser_paces_staleness_by_the_contract():
    source = OUTPUTS_JS.read_text(encoding="utf-8")
    agreed = timing()

    assert client_interval(source) == agreed["heartbeat_interval_seconds"]
    assert client_intervals_to_stale(source) == agreed["stale_after_intervals"]


def test_the_comparison_can_fail():
    """A browser that drifted is caught, not read as agreeing."""
    drifted = (
        "export const HEARTBEAT_INTERVAL_SECONDS = 30;\nexport const STALE_AFTER_SECONDS = 2 * HEARTBEAT_INTERVAL_SECONDS;\n"
    )

    assert client_interval(drifted) != timing()["heartbeat_interval_seconds"]
    assert client_intervals_to_stale(drifted) != timing()["stale_after_intervals"]
