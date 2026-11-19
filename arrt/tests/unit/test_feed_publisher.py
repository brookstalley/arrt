"""What `DisplayService` guaranteed about the feeds before `FeedPublisher` was cut out of it, held after.

The feed publisher moved from `display.py` to `feeds.py` on 2026-11-19 (audit
wave 2, Chunk 20). A move keeps what the old arrangement guaranteed only if each
guarantee is checked where it now lives:

- **One subscriber reconciles each announcement.** The container subscribes the
  facade's `on_work_changed`, which reconciles through the publisher. A second
  subscription, or the publisher subscribing itself as well, would reconcile
  every announcement twice; none would reconcile nothing.
- **The feed's journal lines keep their logger.** A logger's name is what a
  reader of the journal filters on, so the lines `feeds.py` says are said under
  `arrt.programming.display`, as they were.
"""

import logging

import pytest


@pytest.fixture
def reconciled(display, monkeypatch):
    """Each reconciliation the publisher runs, as the works it was asked about: the one place one runs."""
    asked: list[list[str] | None] = []
    reconcile = display._feeds.reconcile

    def counted(work_ids=None, **keywords):
        asked.append(None if work_ids is None else sorted(work_ids))
        return reconcile(work_ids, **keywords)

    monkeypatch.setattr(display._feeds, "reconcile", counted)
    return asked


def test_one_announcement_reconciles_once_through_the_publisher(services, ready_work, reconciled):
    first, second = ready_work(title="Nighthawks"), ready_work(title="Automat")
    reconciled.clear()

    services.catalogue.archive_artworks([first.id, second.id])

    assert reconciled == [sorted([first.id, second.id])]


def test_an_acceptance_is_reconciled_and_offered_its_theme_once(services, display, monkeypatch, reconciled):
    """The other half of the subscriber: an accepted work is offered once, after the one reconciliation."""
    offered: list[list[str]] = []
    monkeypatch.setattr(display, "offer_destinations", lambda work_ids: offered.append(list(work_ids)) or [])

    work = services.catalogue.add_artwork(title="Nighthawks")

    assert offered == [[work.id]]
    assert reconciled == [[work.id]]


def test_the_feed_s_lines_and_the_facade_s_are_said_under_one_logger(display, ready_work, wall_id, caplog):
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)

    with caplog.at_level(logging.INFO):
        display.activate_theme(theme.id, wall_id=wall_id)
        display.rename_wall(wall_id, name="The hall")

    published = [record for record in caplog.records if record.getMessage().startswith("Published the feed for wall")]
    renamed = [record for record in caplog.records if "is now called" in record.getMessage()]
    assert published, "the hang said nothing about its feed, so the logger was not read"
    assert renamed, "the rename said nothing, so the facade's logger was not read"
    assert {record.name for record in published + renamed} == {"arrt.programming.display"}
