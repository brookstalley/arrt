"""The server's feed writer is held to every manifest rule, including those a Player need not refuse.

A Player may be more tolerant than the schema (`player-contract.md` § Versioning):
the index's `player_must_refuse` says which rules a reader enforces, and the rest
are the writer's alone. So a row marked `false` is no licence for the server to
write that document. Every feed this suite publishes passes through
`feed_guard.checked`, and here each invalid manifest fixture is handed to that same
check as if the builder had produced it: each must be stopped, the ones a Player
tolerates as much as the ones it refuses.

This file reads `contract/fixtures/` through `arrt_contract`, which the image's
test stage installs from `/contract`.
"""

import json
from pathlib import Path

import pytest
from arrt_contract import fixtures, root
from feed_guard import checked

INVALID_FEEDS = [row for row in fixtures() if row["path"].startswith("fixtures/manifest.v2/invalid/")]

#: The rules a writer must keep and a Player need not refuse, which are the ones a loosened check would let through unseen.
TOLERATED_BY_A_PLAYER = [row for row in INVALID_FEEDS if not row["player_must_refuse"]]


def _document(row: dict) -> dict:
    return json.loads((root() / row["path"]).read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", INVALID_FEEDS, ids=lambda row: Path(row["path"]).stem)
def test_the_feed_writers_check_stops_every_invalid_manifest(row):
    document = _document(row)
    build = checked(lambda: document)

    with pytest.raises(AssertionError, match="breaks the Player contract"):
        build()


def test_the_rules_a_player_tolerates_include_the_instant_it_never_reads_and_a_master_of_an_unknown_kind():
    """The rows a reader need not refuse, named: the writer's check above is what still holds the server to them."""
    names = {Path(row["path"]).stem for row in TOLERATED_BY_A_PLAYER}

    assert {"generated-at-malformed", "generated-at-not-text", "work-media-content-type-unknown"} <= names
    assert "staging-repeated" not in names
