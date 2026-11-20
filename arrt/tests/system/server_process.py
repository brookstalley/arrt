"""`python -m arrt` run as a process over a scratch art root, for the system tests, and the guards it is held to.

Here rather than in `conftest.py` so a test can import it: `conftest` in
`sys.modules` is whichever conftest was imported last, so `from conftest import`
finds the wrong file depending on what else was collected. `conftest.py` makes
`arrt_process` of it.

**What it reads outside `arrt/src`:** through `tools/ux_walk.py`, the repository
root's `.env.example` (`conftest.py`'s docstring says why).
"""

import contextlib
import dataclasses
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from unittest import mock

import httpx
import pytest
from feed_guard import published_problems

_CURATION: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_CURATION / "tools"))

import ux_walk  # noqa: E402 -- tools/ is not a package; the path is inserted above

# -- the server as a process -------------------------------------------------------
#
# **What the process boundary changes about the suite's guards.** The feed guard
# in `tests/conftest.py` patches the feed builder in this process; a server
# started with `python -m arrt` imports its own copy of every module and is out of
# that patch's reach. Two things cross the boundary, and the guards here hold each:
#
# - **The environment the child inherits** decides where it writes. Every path it
#   writes (each wall's feed and heartbeat, the catalogue, the backup
#   generations) it resolves itself, from `ART_ROOT` and `BACKUP_DIR`, relative to
#   its own working directory, which is this project's directory in the checkout.
#   So before any child starts, `contained` resolves the environment it is about to
#   be given with the server's own `Settings.from_env` and refuses, by name, any
#   path setting that resolves outside the test's scratch root. A relative
#   `ART_ROOT` would otherwise write into the checkout.
# - **What it leaves on disk** is the only account of what it published. When a
#   server test ends, every wall's feed under every art root that server served
#   is held to the Player contract (`feed_guard.published_problems`), and the test
#   fails naming each wall whose feed a Player would refuse. In addition to the
#   in-process guard, which still checks every feed this process builds (a
#   fixture's hang before the server starts), never instead.

#: How long a start may take before the test calls it hung: the server imports,
#: opens and migrates the catalogue, and reconciles before it answers. About ten
#: seconds on an idle development Mac (2026-11-19); a runner busy with other
#: suites has been seen to take several times that, so the bound is generous and
#: a start past it fails naming what the server last said.
_START_SECONDS: Final[float] = 180.0
#: How long SIGTERM is given: uvicorn runs the app's shutdown, which stops the
#: backup thread (itself bounded at 30 s) and closes the catalogue.
_STOP_SECONDS: Final[float] = 45.0
#: How many ports a start tries. A port is chosen free and handed to the server,
#: which binds it a moment later; another process can take it between the two
#: (the server refuses port 0, so it cannot be asked to choose). A start that
#: loses that race is started again on another port; three lost in a row is not a
#: race, and fails naming each port.
_PORT_ATTEMPTS: Final[int] = 3
#: What uvicorn logs once it holds the port, and only then: the start waits for
#: this line in its own server's output as well as an answer, so an answer from
#: whatever else took the port is never taken for this server's. Copied from an
#: observed start (2026-11-20, macOS):
#: `{"logger": "uvicorn.error", "message": "Uvicorn running on http://127.0.0.1:51418 (Press CTRL+C to quit)"}`.
_LISTENING: Final[str] = "Uvicorn running on http://127.0.0.1:{port} "
#: What uvicorn logs when the port was taken first, before it exits. Copied from
#: an observed start on a port this test held (2026-11-20, macOS; uvicorn builds
#: the sentence itself, so only the errno differs on Linux): `{"level": "ERROR",
#: "logger": "uvicorn.error", "message": "[Errno 48] error while attempting to bind
#: on address ('127.0.0.1', 51418): [errno 48] address already in use"}`.
_BIND_LOST: Final[str] = "error while attempting to bind on address"


def free_port() -> int:
    """A port nothing holds now. Another process may take it before the server binds it: `ArrtProcess.start` tries again."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def contained(environment: Mapping[str, str], *, scratch_root: Path, cwd: Path = _CURATION) -> None:
    """Refuse, naming the setting, an environment under which the server would write outside `scratch_root`.

    Resolved by the server's own `Settings.from_env`, under exactly that
    environment and with `.env` loading stubbed as the launcher stubs it, so the
    paths checked are the ones the child will use. Every `Path` the settings hold
    is checked, so a path setting added later is checked without this changing;
    the feeds, heartbeats and catalogue are named beneath `art_root`. A relative
    path is resolved against `cwd`, the child's working directory.
    """
    from arrt import config

    with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(config, "load_dotenv", return_value=False):
        resolved = config.Settings.from_env()
    scratch = scratch_root.resolve()
    escaped = []
    for setting in dataclasses.fields(resolved):
        value = getattr(resolved, setting.name)
        if isinstance(value, Path):
            where = (cwd / value).resolve()
            if not where.is_relative_to(scratch):
                escaped.append(f"{setting.name} resolves to {where}")
    if escaped:
        pytest.fail(f"a server under test would write outside its scratch root {scratch}: {'; '.join(escaped)}; not started")


@dataclass
class ArrtProcess:
    """`python -m arrt` over one art root, started and stopped as the operator would, its output kept for a failure.

    `scratch_root` is the one directory it may write beneath (`contained`).
    `ports` chooses the port each start tries; a test of the retry hands it the
    port another process holds.
    """

    art_root: Path
    scratch_root: Path
    environment: Mapping[str, str] = field(default_factory=dict)
    log_path: Path | None = None
    ports: Callable[[], int] = free_port
    _process: subprocess.Popen | None = None
    #: Every art root a start served, so the feeds of each are checked at the end.
    served: list[Path] = field(default_factory=list)
    base_url: str = ""

    def _environment(self, port: int) -> dict[str, str]:
        declared = ux_walk.names_to_blank()
        environment = ux_walk.synthetic_environment(os.environ, art_root=self.art_root, port=port, declared=declared)
        environment.update(self.environment)
        contained(environment, scratch_root=self.scratch_root)
        return environment

    def _log(self) -> Path:
        self.log_path = self.log_path or self.art_root.parent / f"{self.art_root.name}-server.log"
        return self.log_path

    def start(self) -> str:
        """Start it and wait until it answers as itself; return its URL. A server that exits first fails naming its last lines."""
        lost: list[int] = []
        while len(lost) < _PORT_ATTEMPTS:
            port = self.ports()
            environment = self._environment(port)
            log_path = self._log()
            offset = log_path.stat().st_size if log_path.exists() else 0
            with log_path.open("a", encoding="utf-8") as log:
                self._process = subprocess.Popen(  # noqa: S603 -- this interpreter, running the product's own entry point
                    ux_walk.synthetic_command(), cwd=_CURATION, env=environment, stdout=log, stderr=subprocess.STDOUT
                )
            self.served.append(self.art_root)
            if self._listening(port, offset):
                self.base_url = f"http://127.0.0.1:{port}"
                return self.base_url
            lost.append(port)
        pytest.fail(f"the server lost the race for {_PORT_ATTEMPTS} ports in a row ({lost}), so it is not a race:\n{self.tail()}")

    def _listening(self, port: int, offset: int) -> bool:
        """Wait until this start's own output says it holds `port` and the port answers. False when it lost the port."""
        assert self._process is not None
        listening = _LISTENING.format(port=port)
        deadline = time.monotonic() + _START_SECONDS
        while time.monotonic() < deadline:
            said = [event.get("message", "") for event in self.events(since=offset)]
            if self._process.poll() is not None:
                if any(_BIND_LOST in message for message in said):
                    return False
                pytest.fail(f"the server exited with {self._process.returncode} before it answered:\n{self.tail()}")
            if any(message.startswith(listening) for message in said):
                try:
                    httpx.get(f"http://127.0.0.1:{port}/api/walls", timeout=2.0)
                except httpx.HTTPError:
                    pass
                else:
                    return True
            time.sleep(0.2)
        self.stop()
        pytest.fail(f"the server did not answer within {_START_SECONDS:.0f} s:\n{self.tail()}")

    def run_to_exit(self, timeout: float = _START_SECONDS) -> int:
        """Start it expecting it to refuse: wait for it to exit and return its code, never waiting for it to answer."""
        environment = self._environment(self.ports())
        self.served.append(self.art_root)
        try:
            with self._log().open("a", encoding="utf-8") as log:
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

    def check_feeds(self) -> None:
        """Fail naming each wall whose feed, under any art root this served (or was given), a Player would refuse."""
        refused = {
            f"{wall_id} (under {root})": found
            for root in dict.fromkeys([self.art_root, *self.served])
            for wall_id, found in published_problems(root).items()
        }
        if refused:
            walls = "\n".join(f"  wall {wall}: {found}" for wall, found in refused.items())
            pytest.fail(
                f"a feed the server left on disk breaks the Player contract:\n{walls}\n--- the server's log ---\n{self.tail()}"
            )

    def tail(self, lines: int = 40) -> str:
        if self.log_path is None or not self.log_path.exists():
            return "(no output)"
        return "\n".join(self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])

    def events(self, since: int = 0) -> list[dict]:
        """Every JSON line the server logged from byte `since` on, in order; a line that is not JSON is left out."""
        if self.log_path is None or not self.log_path.exists():
            return []
        with self.log_path.open("rb") as log:
            log.seek(since)
            text = log.read().decode("utf-8", errors="replace")
        found = []
        for line in text.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                found.append(event)
        return found


@contextlib.contextmanager
def serving(art_root: Path, scratch_root: Path) -> Iterator[ArrtProcess]:
    """A server process over `art_root`, stopped however the block ends, and its feeds then held to the contract.

    `arrt_process` is this, as a fixture; a test of the guard drives it directly.
    """
    process = ArrtProcess(art_root=art_root, scratch_root=scratch_root)
    try:
        yield process
    finally:
        process.stop()
    process.check_feeds()
