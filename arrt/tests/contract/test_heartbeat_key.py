"""Arrt reads each heartbeat's instant under the key the contract requires.

A reader that looks for the instant under another spelling reads every heartbeat
as unreadable, which reports a running Player as down. Arrt reads the wall's and
the client's heartbeats with a constant each, and each is held to the contract's
`instant_key`; the Player holds its writer to the same key in its own suite. The
two agree because each agrees with the contract.
"""

import pytest
from arrt_contract import instant_key

from arrt.programming import client_heartbeat
from arrt.programming.manifest import heartbeat


@pytest.mark.parametrize(
    ("reader", "schema"),
    [
        (heartbeat, "schemas/heartbeat.v1.schema.json"),
        (client_heartbeat, "schemas/client-heartbeat.v1.schema.json"),
    ],
    ids=["wall", "client"],
)
def test_each_reader_looks_for_the_instant_under_the_contracts_key(reader, schema):
    assert instant_key(schema) == reader.REPORTED_AT_KEY
