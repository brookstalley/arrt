"""The suite's own guard against a source plugin faulting where no test expected it.

The loader contains a plugin's fault so that one bad package cannot stop a run,
and that containment would hide a bug in the built-in plugins from the suite,
which before plugins saw it as a raised exception. `tests/conftest.py` puts the
strictness back: any test that logs a contained fault fails, unless it is marked
`plugin_fault_expected`.

Kept here rather than inside the fixture so it can be tested itself
(`tests/unit/test_fault_guard.py`): a guard that is never seen to fail is a guard
nobody knows works. Both names it listens for come from the loader, so moving the
containment cannot leave it listening to a logger nothing writes to.
"""

import logging

from arrt.library.sources.loading import FAULT_EVENT, FAULT_LOGGER


class FaultRecords(logging.Handler):
    """Collects the contained faults written while it is attached."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.faults: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "event", None) == FAULT_EVENT:
            self.faults.append(record)

    def attach(self) -> None:
        logging.getLogger(FAULT_LOGGER).addHandler(self)

    def detach(self) -> None:
        logging.getLogger(FAULT_LOGGER).removeHandler(self)

    def complaint(self, *, expected: bool) -> str | None:
        """Why the test should fail, or `None` when it should not."""
        if not self.faults or expected:
            return None
        return "a source plugin faulted: " + "; ".join(
            f"{getattr(record, 'plugin', '?')} in {getattr(record, 'operation', '?')}" for record in self.faults
        )
