"""The history's own rules, below the surface: who may write what, the order it reads in, and older files.

What each act writes is held through the HTTP caller in
`tests/integration/test_history_surface.py`; this file holds what no route can
reach on its own.
"""

import sqlite3

import pytest

from arrt.library.facade import PROGRAMMING_ACTS, ProgrammingAct
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import EventKind
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.services.errors import ServiceError


class TestProgrammingWritesOnlyActsOnTheWalls:
    @pytest.mark.parametrize("kind", sorted(set(EventKind) - PROGRAMMING_ACTS))
    def test_a_library_act_is_refused_from_programming(self, library, service, kind):
        with pytest.raises(ServiceError, match=str(kind)):
            library.record(ProgrammingAct(kind=kind, work_id="w"))

        assert service.list_events().total == 0

    @pytest.mark.parametrize("kind", sorted(PROGRAMMING_ACTS))
    def test_an_act_on_the_walls_is_recorded_as_given(self, library, service, kind):
        library.record(ProgrammingAct(kind=kind, wall_id="study", theme_id="t-1", work_id="w-1", detail={"theme_name": "X"}))

        [event] = service.list_events().events
        assert (event.kind, event.wall_id, event.theme_id, event.work_id, event.detail) == (
            kind,
            "study",
            "t-1",
            "w-1",
            {"theme_name": "X"},
        )


class TestReadingTheHistory:
    def test_two_acts_in_one_clock_tick_read_newest_written_first(self, service, monkeypatch):
        """`rowid` breaks the tie, so a page boundary never falls differently between two reads."""
        for title in ("first", "second", "third"):
            service.record_event(EventKind.ARCHIVED, work_id=title, detail={"title": title})
        frozen = service.list_events().events[0].occurred_at
        from arrt.library.services import catalogue as module

        class _Frozen:
            @staticmethod
            def now(_tz=None):
                return frozen

        monkeypatch.setattr(module, "datetime", _Frozen)
        service.record_event(EventKind.RESTORED, work_id="tied-a")
        service.record_event(EventKind.RESTORED, work_id="tied-b")

        assert [event.work_id for event in service.list_events().events][:2] == ["tied-b", "tied-a"]

    def test_a_works_history_is_counted_from_the_same_clause_as_its_page(self, service):
        """The total beside one work's page counts that work's events, not every event."""
        for kind in (EventKind.ARCHIVED, EventKind.RESTORED, EventKind.ARCHIVED):
            service.record_event(kind, work_id="nighthawks")
        service.record_event(EventKind.ARCHIVED, work_id="automat")

        page = service.list_events(work_id="nighthawks", limit=2)

        assert ([event.kind for event in page.events], page.total) == ([EventKind.ARCHIVED, EventKind.RESTORED], 3)
        assert service.list_events(work_id="nighthawks", kinds=[EventKind.RESTORED]).total == 1

    def test_the_get_that_brought_a_work_is_its_acceptance(self, service):
        service.record_event(EventKind.ACCEPTED, work_id="elephants", run_id="run-1", detail={"title": "The Elephants"})
        service.record_event(EventKind.ACCEPTED, work_id="swans", run_id="run-2")
        service.record_event(EventKind.ARCHIVED, work_id="elephants", run_id="not-a-get")

        brought = service.get_that_brought("elephants")

        assert brought is not None
        assert (brought.kind, brought.run_id) == (EventKind.ACCEPTED, "run-1")
        assert service.get_that_brought("added-by-hand") is None

    def test_limits_outside_the_range_are_refused(self, service):
        with pytest.raises(ServiceError, match="limit"):
            service.list_events(limit=0)
        with pytest.raises(ServiceError, match="offset"):
            service.list_events(offset=-1)


def test_a_file_written_before_selections_gains_the_hidden_flag_and_its_themes_read_as_shown(tmp_path):
    """Widened in place: every theme that existed before is an ordinary one."""
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE themes DROP COLUMN is_hidden")
        connection.execute("DROP TABLE history_events")
        connection.execute("DROP TABLE work_exclusions")
        connection.execute("INSERT INTO themes (id, name, created_at) VALUES ('t-1', 'All works', '2026-10-01T00:00:00+00:00')")
        connection.commit()
    finally:
        connection.close()

    store = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert [(theme.name, theme.hidden) for theme in store.list_themes()] == [("All works", False)]
        assert store.list_events(limit=10, offset=0).total == 0
        assert store.list_exclusions() == []
    finally:
        store.close()
