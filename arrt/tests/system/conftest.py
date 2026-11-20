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
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import httpx
import pytest

_CURATION: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_CURATION / "tools"))

import ux_walk  # noqa: E402 -- tools/ is not a package; the path is inserted above

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


# -- the server as a process -------------------------------------------------------

#: How long a start may take before the test calls it hung: the server imports,
#: opens and migrates the catalogue, and reconciles before it answers. About ten
#: seconds on an idle development Mac (2026-11-19); a runner busy with other
#: suites has been seen to take several times that, so the bound is generous and
#: a start past it fails naming what the server last said.
_START_SECONDS: Final[float] = 180.0
#: How long SIGTERM is given: uvicorn runs the app's shutdown, which stops the
#: backup thread (itself bounded at 30 s) and closes the catalogue.
_STOP_SECONDS: Final[float] = 45.0


def _free_port() -> int:
    """A port nothing holds now. The window before the server binds it is accepted: a lost race fails the start by name."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@dataclass
class ArrtProcess:
    """`python -m arrt` over one art root, started and stopped as the operator would, its output kept for a failure."""

    art_root: Path
    environment: Mapping[str, str] = field(default_factory=dict)
    log_path: Path | None = None
    _process: subprocess.Popen | None = None
    base_url: str = ""

    def start(self) -> str:
        """Start it and wait until it answers; return its URL. A server that exits first fails naming its last lines."""
        declared = ux_walk.names_to_blank()
        port = _free_port()
        environment = ux_walk.synthetic_environment(os.environ, art_root=self.art_root, port=port, declared=declared)
        environment.update(self.environment)
        self.log_path = self.log_path or self.art_root.parent / f"{self.art_root.name}-server.log"
        log = self.log_path.open("a", encoding="utf-8")
        self._process = subprocess.Popen(  # noqa: S603 -- this interpreter, running the product's own entry point
            ux_walk.synthetic_command(), cwd=_CURATION, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
        log.close()
        self.base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + _START_SECONDS
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                pytest.fail(f"the server exited with {self._process.returncode} before it answered:\n{self.tail()}")
            try:
                httpx.get(self.base_url + "/api/walls", timeout=2.0)
            except httpx.HTTPError:
                time.sleep(0.2)
            else:
                return self.base_url
        self.stop()
        pytest.fail(f"the server did not answer within {_START_SECONDS:.0f} s:\n{self.tail()}")

    def run_to_exit(self, timeout: float = _START_SECONDS) -> int:
        """Start it expecting it to refuse: wait for it to exit and return its code, never waiting for it to answer."""
        declared = ux_walk.names_to_blank()
        environment = ux_walk.synthetic_environment(os.environ, art_root=self.art_root, port=_free_port(), declared=declared)
        environment.update(self.environment)
        self.log_path = self.log_path or self.art_root.parent / f"{self.art_root.name}-server.log"
        try:
            with self.log_path.open("a", encoding="utf-8") as log:
                finished = subprocess.run(  # noqa: S603 -- this interpreter, running the product's own entry point
                    ux_walk.synthetic_command(),
                    cwd=_CURATION,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            pytest.fail(f"the server neither refused nor exited within {timeout:.0f} s:\n{self.tail()}")
        return finished.returncode

    def stop(self) -> None:
        """SIGTERM, as a service manager stops it, so the app's shutdown runs."""
        if self._process is None or self._process.poll() is not None:
            return
        self._process.send_signal(signal.SIGTERM)
        try:
            self._process.wait(timeout=_STOP_SECONDS)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
            pytest.fail(f"the server did not stop within {_STOP_SECONDS:.0f} s of SIGTERM:\n{self.tail()}")

    def tail(self, lines: int = 40) -> str:
        if self.log_path is None or not self.log_path.exists():
            return "(no output)"
        return "\n".join(self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])

    def events(self) -> list[dict]:
        """Every JSON line the server logged, in order; a line that is not JSON is left out."""
        found = []
        for line in (self.log_path.read_text(encoding="utf-8").splitlines() if self.log_path else []):
            try:
                found.append(json.loads(line))
            except ValueError:
                continue
        return found


@pytest.fixture
def arrt_process(tmp_path) -> Iterator[ArrtProcess]:
    """A server process over `tmp_path`'s art root (the suite's `settings` fixture's), stopped when the test ends."""
    process = ArrtProcess(art_root=tmp_path)
    try:
        yield process
    finally:
        process.stop()
