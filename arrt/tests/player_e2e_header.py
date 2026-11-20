"""What a run says about the real-Player test, so leaving it out is never silent.

`player_e2e` is off by default (`pyproject.toml`'s `addopts`, for the network it
installs over), and under `-n auto` pytest prints no deselected count, so a run
that leaves it out would otherwise say nothing. `conftest.py` says it twice:

- **before collection** (`pytest_report_header`), `WHERE`: where the test runs
  (testament's `player` suite, on the pool, never on GitHub's runner) and how to
  run it by hand. True of every run, so it decides nothing.
- **after collection** (`pytest_terminal_summary`), `after_collection(...)`: what
  this run did with it, read from the items pytest collected and the ones it
  deselected (`pytest_collection_finish`, `pytest_deselected`), never from the
  marker expression. Under xdist the controller collects nothing, so each worker
  hands what it saw to the controller in `config.workeroutput`, which arrives in
  `pytest_testnodedown`.

Public hooks and attributes only: nothing here, or in the conftest's hooks, reads
pytest's private modules (`tests/unit/test_player_e2e_header.py` holds both).
The test is known by its file, so a mark added to or dropped from its module is
what the run reports, not what this file expects.

`SUITE` and `ON_THE_POOL` quote `.testament.toml`, which owns the suites;
`tests/test_default_suite_ci_scope.py`, at the repository's root, holds them to it.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterable, Mapping

TEST_MODULE = pathlib.Path(__file__).resolve().parent / "system" / "test_a_real_player.py"
SUITE = "player"
ON_THE_POOL = f"testament run --json=summary --suite {SUITE}"
BY_HAND = "cd arrt && uv run pytest -m player_e2e -n0 tests/system/test_a_real_player.py"
WHERE = (
    f"player_e2e: the real-Player test runs as testament's `{SUITE}` suite, on the pool only "
    f"({ON_THE_POOL}); by hand: {BY_HAND}"
)

#: What one process saw of the test. A plain dict of booleans, because it crosses from
#: an xdist worker to the controller in `workeroutput`.
Seen = dict[str, bool]
#: The key the conftest stores it under, in `config.stash` and in `workeroutput`.
KEY = "player_e2e"


def is_the_real_player_test(path: pathlib.Path | str) -> bool:
    """Whether a collected item's file (`item.path`) is the real-Player test's module."""
    return pathlib.Path(path).resolve() == TEST_MODULE


def seen(selected: Iterable[pathlib.Path | str], deselected: Iterable[pathlib.Path | str]) -> Seen:
    """What one process's collection held: the real-Player test among the items it kept, and among those it dropped."""
    return {
        "reported": True,
        "selected": any(is_the_real_player_test(p) for p in selected),
        "deselected": any(is_the_real_player_test(p) for p in deselected),
    }


def merged(reports: Iterable[Mapping[str, bool]]) -> Seen:
    """Several processes' views as one: every xdist worker collects the same items."""
    reports = list(reports)
    return {key: any(r.get(key, False) for r in reports) for key in ("reported", "selected", "deselected")}


def after_collection(state: Mapping[str, bool] | None) -> str:
    """The line the run ends with: one wording for each thing the run can have done with the test."""
    state = state or {}
    elsewhere = f"it runs as testament's `{SUITE}` suite ({ON_THE_POOL}); by hand: {BY_HAND}"
    if not state.get("reported"):
        return (
            "player_e2e: no collection reached this process, so it cannot say what this run did with the "
            f"real-Player test; {elsewhere}"
        )
    if state.get("selected"):
        return "player_e2e: this run selects the real-Player test, which needs the network to GitHub, git and uv"
    if state.get("deselected"):
        return f"player_e2e: this run deselected the real-Player test; {elsewhere}"
    return f"player_e2e: this run did not collect the real-Player test; {elsewhere}"
