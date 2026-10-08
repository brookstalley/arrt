"""The browser's idea of a heartbeat interval is the Player's.

Walls and Clients call a report stale past three heartbeat intervals
(`arrt/src/arrt/http/static/core/outputs.js`), and the interval is the Player's
own `INTERVAL_SECONDS` (`postarr/src/postarr/heartbeat.py`), which paces both the
wall heartbeat and the client heartbeat. Neither plane can import the other, so
the number is written twice, and this compares the two, reading both sources as
`test_heartbeat_contract.py` does.

If the Player reported less often than the client believes, every healthy wall
would read as stale between reports; more often, and a stopped client would go on
reading as current for longer than three missed reports.
"""

import ast
import pathlib
import re

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PLAYER = REPOSITORY_ROOT / "postarr" / "src" / "postarr" / "heartbeat.py"
CLIENT = REPOSITORY_ROOT / "arrt" / "src" / "arrt" / "http" / "static" / "core" / "outputs.js"

_CLIENT_INTERVAL = re.compile(r"^export const HEARTBEAT_INTERVAL_SECONDS = (\d+(?:\.\d+)?);$", re.MULTILINE)
_CLIENT_THRESHOLD = re.compile(r"^export const STALE_AFTER_SECONDS = (.+);$", re.MULTILINE)


def player_interval(source: str) -> float:
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "INTERVAL_SECONDS":
            return float(ast.literal_eval(node.value))
    raise AssertionError("postarr/heartbeat.py declares no INTERVAL_SECONDS")


def client_interval(source: str) -> float:
    found = _CLIENT_INTERVAL.findall(source)
    assert len(found) == 1, "core/outputs.js declares HEARTBEAT_INTERVAL_SECONDS once, as a number"
    return float(found[0])


def test_the_client_paces_staleness_by_the_players_interval():
    assert client_interval(CLIENT.read_text(encoding="utf-8")) == player_interval(PLAYER.read_text(encoding="utf-8"))


def test_the_threshold_is_three_intervals():
    """The owner-confirmed threshold, stated where it is decided."""
    found = _CLIENT_THRESHOLD.findall(CLIENT.read_text(encoding="utf-8"))
    assert found == ["3 * HEARTBEAT_INTERVAL_SECONDS"]


def test_the_comparison_can_fail():
    """A client that drifted from the Player is caught, not read as agreeing."""
    drifted = "export const HEARTBEAT_INTERVAL_SECONDS = 30;\n"
    assert client_interval(drifted) != player_interval(PLAYER.read_text(encoding="utf-8"))
