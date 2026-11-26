"""The shared fixture's report guard: a wall's report kept while no Player shows the wall.

`conftest.py`'s `reports_only_where_a_player_shows` wraps the writers of a wall's
report with `ReportsForNoPlayer` and fails a test that kept one for a wall no Player
shows, unless the test carries `NO_PLAYER_REPORTS_MARKER`.

Here rather than in `conftest.py` so a test can import it, for the reason
`system/server_process.py` gives: `conftest` in `sys.modules` is whichever conftest
was imported last, so `from conftest import` finds `system/conftest.py` whenever the
system tests are collected in the same run.
"""

import functools
import threading
from collections.abc import Callable
from typing import Any, Final

from arrt.programming.reports import Reports

#: The marker a test carries when it keeps a wall's report for a wall no Player
#: shows on purpose (a test of that impossible state), with its reason.
NO_PLAYER_REPORTS_MARKER: Final = "reports_for_a_wall_no_player_shows"


def _a_player_shows(reports: Reports, wall_id: str) -> bool:
    """Whether a Player with a token is placed on this wall, read from the store alone (no clock, no file)."""
    store: Any = reports._store
    with store.reading():
        wall = store.get_wall(wall_id)
        display = None if wall is None or wall.display_id is None else store.get_display(wall.display_id)
        client = None if display is None or display.client_id is None else store.get_client(display.client_id)
    return client is not None and client.token_verifier is not None


class ReportsForNoPlayer:
    """Every report a test kept for a wall no Player showed, by writer and wall, while attached."""

    def __init__(self) -> None:
        self.kept: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def watching(self, writer: str, real: Callable[..., Any]) -> Callable[..., Any]:
        # Wrapped, so whatever asks the writer its signature gets the real one.
        @functools.wraps(real)
        def kept(reports: Reports, wall_id: str, *args: Any, **kwargs: Any) -> Any:
            shown = _a_player_shows(reports, wall_id)
            answer = real(reports, wall_id, *args, **kwargs)
            # After the call, so a report refused (and so never written) is not one.
            if not shown:
                with self._lock:
                    self.kept.append((writer, wall_id))
            return answer

        return kept

    def complaint(self) -> str | None:
        if not self.kept:
            return None
        named = ", ".join(sorted({f"{writer} for wall {wall_id}" for writer, wall_id in self.kept}))
        return (
            f"The test kept a wall's report while no Player showed the wall ({named}). A report is what the wall's "
            "Player sends, and only a Player with a token reports, so ask for `a_player_shows_the_wall` (or place one) "
            f"first; a test of that impossible state says so with @pytest.mark.{NO_PLAYER_REPORTS_MARKER}(why)."
        )
