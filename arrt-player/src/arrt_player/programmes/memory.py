"""What a wall's programmes remember about what is on it, wherever the display keeps that.

Shared by every programme, so a wall switched between majors never re-shows the
work already up for want of knowing it, and kept apart from any one programme so
that deleting major 1's rotation (wave 4g) takes nothing the schedule needs.
"""

from typing import Protocol


class Memory(Protocol):
    """What the rotation remembers about the wall. `state.DisplayState` is one."""

    @property
    def last_acted_sequence(self) -> int | None: ...

    def set_last_acted_sequence(self, sequence: int) -> None: ...

    @property
    def last_selected_work_id(self) -> str | None: ...

    def set_last_selected_work_id(self, work_id: str) -> None: ...


class InMemory:
    """A `Memory` that lasts as long as the process."""

    def __init__(self) -> None:
        self._sequence: int | None = None
        self._work_id: str | None = None

    @property
    def last_acted_sequence(self) -> int | None:
        return self._sequence

    def set_last_acted_sequence(self, sequence: int) -> None:
        self._sequence = sequence

    @property
    def last_selected_work_id(self) -> str | None:
        return self._work_id

    def set_last_selected_work_id(self, work_id: str) -> None:
        self._work_id = work_id
