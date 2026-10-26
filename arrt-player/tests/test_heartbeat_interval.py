"""The Player reports each heartbeat at the interval the contract states.

Arrt and the browser call a report stale past three intervals of the contract's
timing (`contract/timing.json`). A Player reporting less often than that would
read as stale between healthy reports; more often, and a stopped Player would go
on reading as current for longer than three missed reports. Arrt's half is
`arrt/tests/contract/test_staleness_threshold.py`.
"""

from arrt_contract import timing

from arrt_player.heartbeat import INTERVAL_SECONDS


def test_the_player_reports_at_the_contracts_interval():
    assert timing()["heartbeat_interval_seconds"] == INTERVAL_SECONDS
