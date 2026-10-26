"""The Player reports each heartbeat's instant under the key the contract requires.

**This is the one agreement whose violation looks like the opposite of itself.**
Arrt reads a heartbeat without that key as unreadable and says so on Walls, so a
Player that spelled it `timestamp` would be reported as *down* while running
perfectly: the product's defining failure, made by the mechanism built to
detect it.

The Player and Arrt each spell the key as a constant of their own, and neither
can import the other. Each holds its constant to the contract's
`instant_key`, so the two agree because each agrees with the contract; Arrt's
half is `arrt/tests/contract/test_heartbeat_key.py`. Pinned to the contract
rather than to each other, because both sides renaming together would still
break every Player built from the published schemas.
"""

import pytest
from arrt_contract import instant_key

from arrt_player.heartbeat import REPORTED_AT_KEY


@pytest.mark.parametrize("schema", ["schemas/heartbeat.v1.schema.json", "schemas/client-heartbeat.v1.schema.json"])
def test_both_heartbeats_carry_their_instant_under_the_contracts_key(schema):
    """One constant writes both bodies' instant, so it is held to both schemas."""
    assert instant_key(schema) == REPORTED_AT_KEY
