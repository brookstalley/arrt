"""The suite's feed guard reports a malformed feed by the schema's own words, and is wired where feeds are built.

`problems` is what every publish path in this suite is checked through. The
semantic rules read keys the schema requires, so a feed missing one must come
back as the schema's message, never as a `KeyError` from the rules that
presumed it. And `conftest.py` wraps the builder in the namespace the feed
publisher calls it from, which the last test here proves through the real
publisher: a wrapper on a name nothing calls checks nothing, silently.
"""

import json

import pytest
from arrt_contract import fixtures, root
from feed_guard import problems

from arrt.programming import feeds as feeds_module


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


def test_a_feed_the_publisher_spells_that_breaks_the_contract_fails_the_test(display, ready_work, wall_id, monkeypatch):
    """Through `conftest.py`'s guard as wired, not a wrapper of this test's own: a hang whose feed lacks `media` is stopped.

    Red when the guard wraps the builder in a namespace the publisher does not
    call it from (`display.py`, not `feeds.py`): the hang then
    publishes the broken feed and nothing raises.
    """
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)
    spelled = feeds_module.work_document

    def without_media(work):
        return {key: value for key, value in spelled(work).items() if key != "media"}

    monkeypatch.setattr(feeds_module, "work_document", without_media)

    with pytest.raises(AssertionError, match="breaks the Player contract") as stopped:
        display.activate_theme(theme.id, wall_id=wall_id)

    assert "'media' is a required property" in str(stopped.value)
    assert display.hanging_on(wall_id) is None, "the act the guard stopped was rolled back"


def test_a_test_that_lifts_its_own_patches_still_has_its_feeds_checked(display, ready_work, wall_id, monkeypatch):
    """`monkeypatch.undo()` lifts the test's patches, never the guard's: a broken feed published after it is still stopped.

    Red while the guard patched through the test's own `monkeypatch` (until
    2026-11-20): the undo lifted it, and the hang below published a feed lacking
    `media` with nothing raised.
    """
    monkeypatch.setattr(feeds_module, "write_atomically", feeds_module.write_atomically)
    monkeypatch.undo()
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)
    spelled = feeds_module.work_document
    monkeypatch.setattr(feeds_module, "work_document", lambda work: {k: v for k, v in spelled(work).items() if k != "media"})

    with pytest.raises(AssertionError, match="breaks the Player contract"):
        display.activate_theme(theme.id, wall_id=wall_id)
