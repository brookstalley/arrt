"""The suite's feed guard reports a malformed feed by the schema's own words.

`problems` is what every publish path in this suite is checked through. The
semantic rules read keys the schema requires, so a feed missing one must come
back as the schema's message, never as a `KeyError` from the rules that
presumed it.
"""

import json

from arrt_contract import fixtures, root
from feed_guard import problems


def _valid_feed() -> dict:
    row = next(row for row in fixtures() if row["schema"] == "schemas/manifest.v2.schema.json" and row["valid"])
    return json.loads((root() / row["path"]).read_text(encoding="utf-8"))


def test_a_feed_missing_a_required_key_is_reported_by_the_schema_not_raised():
    feed = _valid_feed()
    del feed["works"]

    found = problems(feed)

    assert found
    assert any("works" in message for message in found)


def test_a_schema_valid_feed_is_still_held_to_the_semantic_rules():
    """The other half: skipping the rules on a schema error must not skip them on a schema-valid feed."""
    feed = _valid_feed()
    feed["schedule"]["slots"] = [{**slot, "work_id": "a-work-nobody-carries"} for slot in feed["schedule"]["slots"]]
    assert feed["schedule"]["slots"], "the fixture needs a slot for this to say anything"

    assert problems(feed) == ["a work is named that is not in works"]
