"""What the system tests share: the catalogues old releases left, and the server run as a process.

**These tests run the product as it is assembled**, not a service under a
fixture: a catalogue a past release made, opened through the call the server
makes; and `python -m arrt` started as its own process on a seeded art root,
stopped, and started again. Nothing here reaches the network, git or a museum,
so they run on the pool and in the image's test stage alike.

**What they read outside `arrt/src`:** the dumps in `tests/fixtures/catalogues/`
(made once by `tools/old_catalogue.py`, which does need git and the release
tags; the tests read only its output), and, through `tools/ux_walk.py`, the
repository root's `.env.example`, which names every setting the server process
must start with blank so that no `.env` on the machine reaches it. Without that
file the server is refused by name (`ux_walk.names_to_blank`) rather than
started inheriting the operator's settings; the image's test stage carries it at
`/.env.example`.
"""

import json
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Final

import pytest
from server_process import ArrtProcess, serving

_CURATION: Final = Path(__file__).resolve().parents[2]

#: The dumps, and the index of which release each one is.
CATALOGUES: Final = _CURATION / "tests" / "fixtures" / "catalogues"


def _releases() -> dict[str, Path]:
    """Each release whose schema differed from the one before it, oldest first, and its dump."""
    index = json.loads((CATALOGUES / "releases.json").read_text(encoding="utf-8"))
    return {tag: CATALOGUES / name for tag, name in index.items()}


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """A test asking for `release` runs once per dump, named by its tag."""
    if "release" in metafunc.fixturenames:
        found = _releases()
        metafunc.parametrize("release", list(found), ids=list(found))


@pytest.fixture
def catalogue_dumps() -> dict[str, Path]:
    """Every dump, by release tag, oldest first."""
    return _releases()


@pytest.fixture
def load_release() -> Callable[[str, Path], Path]:
    """Write the catalogue a release left to a path, from its dump; returns the path."""

    def load(tag: str, path: Path) -> Path:
        connection = sqlite3.connect(path)
        try:
            connection.executescript(_releases()[tag].read_text(encoding="utf-8"))
        finally:
            connection.close()
        return path

    return load


@pytest.fixture
def arrt_process(tmp_path, tmp_path_factory) -> Iterator[ArrtProcess]:
    """A server process over `tmp_path`'s art root (the suite's `settings` fixture's), stopped when the test ends.

    Its scratch root is the run's base temporary directory, which holds `tmp_path`
    and every `tmp_path_factory.mktemp` directory a test gives it besides
    (a backup directory, a second art root).
    """
    with serving(tmp_path, tmp_path_factory.getbasetemp()) as process:
        yield process
