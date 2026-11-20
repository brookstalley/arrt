"""A real Arrt Player against a real Arrt: the shipped pair, two processes, one verdict.

**Why this exists.** The Player is tested against a hand-written double of this
server, and this server against fixtures of what a Player sends; each half can
be green while the pair disagrees (audit-7 C1). Here the server is `python -m
arrt` (chunk 06's fixture, or the built app image, below) and the Player is
`python -m arrt_player` from the commit in `player-ref.txt`, installed from git
into an environment of its own, the way a Pi installs it (`uv sync --frozen
--no-dev`), never from a checkout on this disk.

**What the Player gives a test** (`.env.example` § "Drawing to files: a Player
with no hardware", in its repository): with `FILE_OUTPUT_DIR` set it reports a
screen output `file-screen-0` and a label output `file-label-0`, and draws to
files, writing `shown.json` beside each. The keys and paths are spelled here as
an outsider reads them, never imported from the Player.

**Seen from both sides.** The server's API, its log and the catalogue's files on
one; the Player's `shown.json`, its picture and its journal on the other; and,
between them, every request the Player made and the status it was answered with,
recorded by a relay the Player is pointed at (`Relay`). The relay changes no
byte: it is there because the server deliberately writes no line for a poll it
answered `2xx` or `304` (`arrt.logs.QuietPlayerPolls`), so without it a `304`
would be visible to neither side.

**What it reaches outside.** GitHub, to fetch the Player's commit and its git
dependency, and uv's Python downloads, for the Player's own interpreter (3.13,
the Pi's). So it is marked `player_e2e` and deselected by default, and checks
that `git` and `uv` are on the path first, failing by name without them
(`docs/testing.md` § The real-Player test). Run it with `-m player_e2e -n0`.

**No fixed sleeps.** Every wait is on something one of the processes makes true,
with a deadline, and its failure prints both processes' output. Each process has
a private directory and a port of its own, and both are always reaped.

**Against the built image.** With `ARRT_SERVER_IMAGE` naming a local image of
`arrt/Dockerfile`'s app stage, the server is that image, run with the art root
mounted at `/art` (`.github/workflows/image.yml`, on a pull request into `main`).
"""

import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

import httpx
import pytest

from arrt.persistence.records import RenditionKind

pytestmark = [
    pytest.mark.player_e2e,
    pytest.mark.uncacheable("installs Arrt Player from GitHub and runs it against the server as two processes"),
]

_HERE: Final = Path(__file__).resolve().parent
_REPOSITORY: Final = _HERE.parents[2]

#: Where the Player's source is fetched from, and the file naming the commit.
PLAYER_REPOSITORY: Final[str] = "https://github.com/brookstalley/arrt-player"
PLAYER_REF_FILE: Final = _HERE / "player-ref.txt"
#: The Player's interpreter: the Pi's, which its own CI pins too (3.13.5 there).
PLAYER_PYTHON: Final[str] = "3.13"

#: How long any one thing a process does may take. Generous for a busy runner: the
#: first picture waits on the client document, the feed, two downloads and a
#: composition. A wait that passes it fails naming what it waited for.
DEADLINE_SECONDS: Final[float] = 60.0
#: An install from cold: a fetch from GitHub, a resolve and, the first time, an interpreter.
INSTALL_SECONDS: Final[float] = 600.0
#: The Player's unit gives SIGTERM 20 s (`deploy/display.service` there).
STOP_SECONDS: Final[float] = 20.0
#: The file screen, small so that composing is cheap.
SCREEN: Final = (320, 180)
#: The refused polls the wall must outlast before the test calls its cache kept.
REFUSALS_OUTLASTED: Final[int] = 5


def player_ref(path: Path = PLAYER_REF_FILE) -> str:
    """The one 40-hex commit `player-ref.txt` names, refused by name when it names anything else."""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    named = [line for line in lines if line and not line.startswith("#")]
    if len(named) != 1 or not re.fullmatch(r"[0-9a-f]{40}", named[0]):
        pytest.fail(f"{path} must name exactly one 40-hex commit of {PLAYER_REPOSITORY}, and it names {named}")
    return named[0]


# -- the Player's environment, from git --------------------------------------------------


def _cache_root() -> Path:
    """Where installed Players are kept between runs, by commit: outside the repository, always."""
    named = os.environ.get("ARRT_PLAYER_E2E_CACHE")
    if named:
        root = Path(named).resolve()
    else:
        root = (Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "arrt" / "player-e2e").resolve()
    if root.is_relative_to(_REPOSITORY):
        pytest.fail(f"the Player's install cache {root} is inside the repository; set ARRT_PLAYER_E2E_CACHE elsewhere")
    return root


#: The only names the install's git and uv inherit. Nothing of this test's own
#: environment (`VIRTUAL_ENV`, `UV_PROJECT_ENVIRONMENT`, a `UV_*` an image sets)
#: may steer the Player's sync into the server's environment or off its lockfile.
_INSTALL_INHERITS: Final = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "UV_CACHE_DIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)


def _install_environment(root: Path) -> dict[str, str]:
    environment = {name: value for name, value in os.environ.items() if name in _INSTALL_INHERITS}
    environment.update(
        {
            # The Player's interpreter is its own, under the cache, so a machine's
            # read-only interpreter directory (the pool image's) is never asked to take it.
            "UV_PYTHON_INSTALL_DIR": str(root / "python"),
            "UV_NO_CONFIG": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _step(what: str, command: list[str], environment: dict[str, str], cwd: Path | None = None) -> str:
    """Run one install step, failing by name with its output when it fails or hangs."""
    try:
        done = subprocess.run(  # noqa: S603 -- git and uv, with arguments this file composes
            command, env=environment, cwd=cwd, capture_output=True, text=True, timeout=INSTALL_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{what} did not finish within {INSTALL_SECONDS:.0f} s: {' '.join(command)}")
    if done.returncode != 0:
        pytest.fail(f"{what} failed ({done.returncode}): {' '.join(command)}\n{done.stdout}\n{done.stderr}")
    return done.stdout


def install_player(ref: str) -> Path:
    """The Player at `ref`, synced from its own lockfile as a Pi syncs it; returns its interpreter.

    Kept by commit under the cache root, so a warm run fetches nothing; built
    under a lock, so two runs on one machine never build one directory at once;
    marked ready only once whole, so an install that died half-way is rebuilt.
    The `raster` and `epaper` groups are not installed: the file label is laid
    out on a surface that needs no typesetter (`panel/file_surface.py` there,
    which imports no Pango), and nothing else in file-output mode needs either.
    """
    missing = [tool for tool in ("git", "uv") if shutil.which(tool) is None]
    if missing:
        pytest.fail(
            f"the real-Player test installs Arrt Player from git with uv, and {missing} is not on PATH "
            "(docs/testing.md § The real-Player test)"
        )
    root = _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    checkout = root / ref
    ready = checkout / ".arrt-player-e2e-ready"
    environment = _install_environment(root)
    with (root / f"{ref}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not ready.exists():
            shutil.rmtree(checkout, ignore_errors=True)
            _step("making the Player's checkout", ["git", "init", "-q", str(checkout)], environment)
            _step(
                f"fetching Arrt Player {ref} from GitHub (this test needs the network to github.com)",
                ["git", "-C", str(checkout), "fetch", "-q", "--depth", "1", PLAYER_REPOSITORY, ref],
                environment,
            )
            _step("checking out the Player", ["git", "-C", str(checkout), "checkout", "-q", "--detach", ref], environment)
            _step(
                "syncing the Player's environment from its lockfile",
                ["uv", "sync", "--frozen", "--no-dev", "--managed-python", "--python", PLAYER_PYTHON],
                environment,
                cwd=checkout,
            )
            ready.write_text(f"{ref}\n", encoding="utf-8")
    head = _step("reading the Player's commit", ["git", "-C", str(checkout), "rev-parse", "HEAD"], environment).strip()
    if head != ref:
        pytest.fail(f"the cached Player at {checkout} is at {head}, not {ref}; remove it and run again")
    return checkout / ".venv" / "bin" / "python"


@pytest.fixture(scope="session")
def player_python() -> Path:
    return install_player(player_ref())


# -- what passes between them ------------------------------------------------------------

#: Hop-by-hop headers, and the two the relay sets itself from the body it has.
_NOT_RELAYED: Final = frozenset(
    {"connection", "keep-alive", "transfer-encoding", "te", "upgrade", "content-length", "content-encoding", "host"}
)


@dataclass
class Relay:
    """Every request the Player makes, passed to the server unchanged, with the status it was answered.

    A recorder, not a double: the server answers every request, and the relay
    hands its status, headers and bytes back as they came.
    """

    upstream: str
    exchanges: list[tuple[str, str, int]] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> str:
        relay = self
        client = httpx.Client(base_url=self.upstream, timeout=30.0)

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _relay(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                headers = {name: value for name, value in self.headers.items() if name.lower() not in _NOT_RELAYED}
                try:
                    answer = client.request(self.command, self.path, headers=headers, content=body)
                    status, answered, content = answer.status_code, answer.headers, answer.content
                except httpx.HTTPError:
                    status, answered, content = 502, httpx.Headers(), b""
                with relay._lock:
                    relay.exchanges.append((self.command, self.path.partition("?")[0], status))
                self.send_response(status)
                for name, value in answered.multi_items():
                    if name.lower() not in _NOT_RELAYED:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            do_GET = do_POST = do_PUT = do_DELETE = _relay  # noqa: N815 -- the names http.server dispatches on

            def log_message(self, *_args: object) -> None:
                return

        class Quiet(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request: object, client_address: object) -> None:
                # A Player that closes a kept-alive connection as it stops is not news.
                return

        self._server = Quiet(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def seen(self, method: str, path: str, status: int | None = None) -> list[int]:
        """The statuses `method path` was answered with, in order; with `status`, only those."""
        with self._lock:
            return [got for (m, p, got) in self.exchanges if m == method and p == path and status in (None, got)]

    def log(self) -> str:
        with self._lock:
            return "\n".join(f"{m} {p} {s}" for m, p, s in self.exchanges[-40:])


# -- the server, as a process or as the built image ---------------------------------------


def _docker(*arguments: str) -> subprocess.CompletedProcess[str]:
    """One docker command, its output captured; the run fails naming it when docker is not on the path."""
    found = shutil.which("docker")
    if found is None:
        pytest.fail("ARRT_SERVER_IMAGE names an image to run, and `docker` is not on PATH")
    return subprocess.run(  # noqa: S603 -- the docker client, with arguments this file composes
        [found, *arguments], capture_output=True, text=True, check=False
    )


@dataclass
class ArrtContainer:
    """The app image over one art root, mounted at `/art`, with the interface `ArrtProcess` has."""

    art_root: Path
    image: str
    name: str = field(default_factory=lambda: f"arrt-player-e2e-{uuid.uuid4().hex[:12]}")
    base_url: str = ""
    _started: bool = False

    def start(self) -> str:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        started = _docker(
            "run",
            "--detach",
            "--name",
            self.name,
            # The test's own user, so the server writes the art root this test made.
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--volume",
            f"{self.art_root}:/art",
            "--publish",
            f"127.0.0.1:{port}:8770",
            self.image,
        )
        if started.returncode != 0:
            pytest.fail(f"docker could not start {self.image} ({started.returncode}):\n{started.stderr}")
        self._started = True
        self.base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + DEADLINE_SECONDS * 3
        while time.monotonic() < deadline:
            if _docker("inspect", "--format", "{{.State.Running}}", self.name).stdout.strip() != "true":
                pytest.fail(f"the server image exited before it answered:\n{self.tail()}")
            try:
                httpx.get(self.base_url + "/api/walls", timeout=2.0)
            except httpx.HTTPError:
                time.sleep(0.2)
            else:
                return self.base_url
        pytest.fail(f"the server image did not answer within {DEADLINE_SECONDS * 3:.0f} s:\n{self.tail()}")

    def stop(self) -> None:
        if self._started:
            _docker("stop", "--time", "45", self.name)
            _docker("rm", "--force", self.name)
            self._started = False

    def tail(self, lines: int = 40) -> str:
        done = _docker("logs", "--tail", str(lines), self.name)
        return (done.stdout + done.stderr) or "(no output)"

    def events(self) -> list[dict]:
        done = _docker("logs", self.name)
        found = []
        for line in (done.stdout + done.stderr).splitlines():
            with contextlib.suppress(ValueError):
                found.append(json.loads(line))
        return found


@pytest.fixture
def server(arrt_process, settings) -> Iterator[object]:
    """Chunk 06's server process, or with `ARRT_SERVER_IMAGE` the built image, over the suite's art root."""
    image = os.environ.get("ARRT_SERVER_IMAGE")
    if not image:
        yield arrt_process
        return
    container = ArrtContainer(art_root=settings.art_root, image=image)
    try:
        yield container
    finally:
        container.stop()


# -- the Player, as a process -------------------------------------------------------------


@dataclass
class PlayerProcess:
    """`python -m arrt_player` with nothing inherited but `PATH`, drawing to files, its journal kept."""

    python: Path
    directory: Path
    server_url: str
    token: str
    _process: subprocess.Popen | None = None

    @property
    def drawn(self) -> Path:
        return self.directory / "drawn"

    @property
    def cache(self) -> Path:
        return self.directory / "cache"

    @property
    def journal_path(self) -> Path:
        return self.directory / "journal.jsonl"

    def environment(self) -> dict[str, str]:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            ui_port = probe.getsockname()[1]
        return {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.directory / "home"),
            # The Player reads a `.env` from its own directory upward; none may reach it.
            "PYTHON_DOTENV_DISABLED": "1",
            "CACHE_DIR": str(self.cache),
            "SERVER_URL": self.server_url,
            "CLIENT_TOKEN": self.token,
            "FILE_OUTPUT_DIR": str(self.drawn),
            "FILE_OUTPUT_SCREEN": f"{SCREEN[0]}x{SCREEN[1]}",
            "FILE_OUTPUT_LABEL": "on",
            "MANIFEST_POLL_SECONDS": "0.2",
            "UI_BIND": "127.0.0.1",
            "UI_PORT": str(ui_port),
        }

    def start(self) -> None:
        (self.directory / "home").mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("ab") as journal:
            self._process = subprocess.Popen(  # noqa: S603 -- the Player's own interpreter and entry point
                [str(self.python), "-m", "arrt_player"],
                env=self.environment(),
                cwd=self.directory / "home",
                stdout=journal,
                stderr=journal,
            )

    def exited(self) -> int | None:
        return None if self._process is None else self._process.poll()

    def terminate(self) -> int:
        """SIGTERM, as `systemctl stop` sends it; the exit code."""
        assert self._process is not None
        self._process.send_signal(signal.SIGTERM)
        return self._process.wait(timeout=STOP_SECONDS)

    def reap(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
            self._process.wait()

    def lines(self) -> list[dict]:
        found = []
        text = self.journal_path.read_text(encoding="utf-8", errors="replace") if self.journal_path.exists() else ""
        for line in text.splitlines():
            with contextlib.suppress(ValueError):
                found.append(json.loads(line))
        return found

    def events(self, name: str) -> list[dict]:
        return [line for line in self.lines() if line.get("event") == name]

    def tail(self, lines: int = 40) -> str:
        if not self.journal_path.exists():
            return "(no output)"
        return "\n".join(self.journal_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])

    def record(self, output: str) -> dict | None:
        """An output's `shown.json`: absent, or whole (the Player replaces it atomically)."""
        try:
            return json.loads((self.drawn / output / "shown.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None


@pytest.fixture
def players(player_python: Path, tmp_path_factory) -> Iterator[Callable[[str, str], PlayerProcess]]:
    """Starts Players, each in a directory of its own outside the art root, and reaps every one."""
    started: list[PlayerProcess] = []

    def start(server_url: str, token: str) -> PlayerProcess:
        player = PlayerProcess(player_python, tmp_path_factory.mktemp("player"), server_url, token)
        started.append(player)
        player.start()
        return player

    yield start
    for player in started:
        player.reap()


# -- the household -----------------------------------------------------------------------


def _seed_work(service, settings, ready_work, decodable_jpeg, title: str, size: tuple[int, int], colour: tuple[int, int, int]):
    """A ready work whose presentation master is a real picture of its own, so no two works share media."""
    work = ready_work(title, master=False, content_hash=f"original-{title}")
    path = f"masters/{work.id}.jpg"
    decodable_jpeg(settings.art_root / path, width=size[0], height=size[1], color=colour)
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
    )
    return work


def _ok(response: httpx.Response) -> dict:
    assert (
        response.is_success
    ), f"{response.request.method} {response.request.url.path} answered {response.status_code}: {response.text}"
    return response.json()


@dataclass
class Waiting:
    """Waits on a condition with a deadline, failing with both processes' output and the wire."""

    server: object
    relay: Relay
    player: PlayerProcess | None = None

    def until(self, condition: Callable[[], object], what: str, seconds: float = DEADLINE_SECONDS) -> object:
        deadline = time.monotonic() + seconds
        while True:
            found = condition()
            if found:
                return found
            if self.player is not None and self.player.exited() is not None:
                pytest.fail(f"the Player exited with {self.player.exited()} while waiting for {what}\n{self.story()}")
            if time.monotonic() > deadline:
                pytest.fail(f"timed out after {seconds:g} s waiting for {what}\n{self.story()}")
            time.sleep(0.05)

    def story(self) -> str:
        player = self.player.tail() if self.player is not None else "(not started)"
        return (
            f"--- the Player's journal ---\n{player}\n"
            f"--- the server's log ---\n{self.server.tail()}\n"
            f"--- the wire (method, path, status) ---\n{self.relay.log()}"
        )


@pytest.fixture
def relay(server) -> Iterator[Relay]:
    recorder = Relay(upstream="")
    yield recorder
    recorder.stop()


@dataclass
class Pair:
    """The two running, and what the curator set up between them."""

    api: httpx.Client
    relay: Relay
    player: PlayerProcess
    wait: Waiting
    wall_id: str
    client_id: str
    label_id: str
    titles: dict[str, str]

    @property
    def manifest_path(self) -> str:
        return f"/walls/{self.wall_id}/manifest/v2"

    def wall(self) -> dict:
        return next(wall for wall in _ok(self.api.get("/walls"))["walls"] if wall["wall_id"] == self.wall_id)

    def client(self) -> dict:
        return next(entry for entry in _ok(self.api.get("/clients"))["clients"] if entry["client_id"] == self.client_id)


def _hang_two_works_for_a_file_player(api: httpx.Client, wall_id: str, works) -> dict[str, str]:
    """The curator's half, through the API as the operator's page does it; returns the ids and the token."""
    client_id = _ok(api.post("/clients", json={"name": "The file Player"}))["client_id"]
    token = _ok(api.post(f"/clients/{client_id}/token"))["token"]
    _ok(api.post(f"/walls/{wall_id}/client", json={"client_id": client_id, "output": "file-screen-0"}))
    label_id = _ok(api.post(f"/walls/{wall_id}/labels", json={"client_id": client_id, "output": "file-label-0"}))["label_id"]
    # A pace longer than the test, so the work on the screen stays while it is read from three places.
    _ok(api.put(f"/walls/{wall_id}/playback", json={"rotation_interval_seconds": 86400}))
    theme_id = _ok(api.post("/themes", json={"name": "Two works"}))["theme_id"]
    for work in works:
        _ok(api.post(f"/themes/{theme_id}/works", json={"artwork_id": work.id}))
    _ok(api.post(f"/themes/{theme_id}/activate", json={"wall_id": wall_id}))
    return {"client_id": client_id, "token": token, "label_id": label_id}


def _published_media(base_url: str, pair_wall: str, token: str, settings, works) -> dict[str, str]:
    """Each work's media hash as the wall's feed names it, checked against the master on the server's disk."""
    feed = httpx.get(f"{base_url}/walls/{pair_wall}/manifest/v2", headers={"Authorization": f"Bearer {token}"}).json()
    assert set(feed["works"]) == {work.id for work in works}, "the wall's feed does not carry the two works hung"
    media = {work_id: entry["media"]["sha256"] for work_id, entry in feed["works"].items()}
    assert len(set(media.values())) == len(works), "two works share one picture, so a fetch could not tell them apart"
    for work in works:
        master = settings.art_root / "masters" / f"{work.id}.jpg"
        assert media[work.id] == hashlib.sha256(master.read_bytes()).hexdigest(), "the feed's hash is not its master's"
    return media


def _the_feed_is_adopted(pair: Pair, media: dict[str, str]) -> None:
    """The client document read; both works' media fetched by hash and kept under it; the next feed poll a 304."""
    wait, relay = pair.wait, pair.relay
    wait.until(lambda: relay.seen("GET", "/client", 200), "the client document to be read")
    for work_id, sha in media.items():
        held = pair.player.cache / pair.wall_id / "media" / f"sha256-{sha}"
        name = pair.titles[work_id]
        wait.until(lambda sha=sha: relay.seen("GET", f"/media/sha256-{sha}", 200), f"the media of {name} to be fetched")
        wait.until(
            lambda held=held, sha=sha: held.is_file() and hashlib.sha256(held.read_bytes()).hexdigest() == sha,
            f"the media of {name} to be kept in the Player's cache under its hash",
        )
    wait.until(lambda: relay.seen("GET", pair.manifest_path, 304), "a later poll of the wall's feed to be answered 304")


def _the_wall_is_drawn(pair: Pair) -> dict:
    """One of the wall's works on the file screen, and the picture its record names; returns the record."""
    player = pair.player
    shown = pair.wait.until(
        lambda: (record := player.record("file-screen-0")) and record.get("outcome") == "picture" and record,
        "the wall's first work to be drawn on the file screen",
    )
    assert (shown["format"], shown["output"], shown["wall_id"]) == (1, "file-screen-0", pair.wall_id)
    assert shown["work_id"] in pair.titles, f"the screen shows {shown['work_id']}, which the wall does not hang"
    assert shown["screen"] == list(SCREEN)
    picture = player.drawn / "file-screen-0" / shown["picture"]
    assert hashlib.sha256(picture.read_bytes()).hexdigest() == shown["picture_sha256"]
    return shown


def _the_server_hears_it(pair: Pair, shown: dict) -> None:
    """Both heartbeats taken, and the server's account of the wall and of the client read from them."""
    wait, relay = pair.wait, pair.relay
    wait.until(lambda: relay.seen("POST", f"/walls/{pair.wall_id}/heartbeat", 204), "the wall's heartbeat to be taken")
    wait.until(lambda: relay.seen("POST", "/client/heartbeat", 204), "the client's heartbeat to be taken")
    state = wait.until(
        lambda: (found := pair.wall()["display_state"])["state"] == "showing_art" and found,
        "/api/walls to report the wall showing art",
    )
    assert state["work_id"] == shown["work_id"], "the server reports a different work on the wall from the one drawn"
    wall = pair.wall()
    assert (wall["client_id"], wall["output"]) == (pair.client_id, "file-screen-0")
    assert [(label["label_id"], label["output"]) for label in wall["labels"]] == [(pair.label_id, "file-label-0")]
    heard = pair.client()["heartbeat"]
    assert heard["problem"] is None, f"the server could not read the Player's client heartbeat: {heard}"
    assert [(output["name"], output["kind"], output["connected"], output["screen"]) for output in heard["outputs"]] == [
        ("file-screen-0", "framebuffer", True, list(SCREEN))
    ]
    assert [(output["name"], output["connected"]) for output in heard["label_outputs"]] == [("file-label-0", True)]


def _the_label_is_drawn(pair: Pair, shown: dict) -> None:
    """The label's document read, and the work on the wall captioned with its title."""
    pair.wait.until(lambda: pair.relay.seen("GET", f"/labels/{pair.label_id}", 200), "the label's document to be read")
    caption = pair.wait.until(
        lambda: (record := pair.player.record("file-label-0")) and record.get("outcome") == "caption" and record,
        "the label to be drawn as a caption",
    )
    assert (caption["format"], caption["output"], caption["label_id"], caption["wall_id"]) == (
        1,
        "file-label-0",
        pair.label_id,
        pair.wall_id,
    )
    assert (caption["state"], caption["work_id"]) == ("showing_art", shown["work_id"])
    assert pair.titles[shown["work_id"]] in caption["lines"], f"the caption does not set the title: {caption['lines']}"


def _the_revoked_token_is_refused_and_the_wall_kept(pair: Pair, server, shown: dict) -> None:
    """A second token issued: the first refused everywhere, each side saying so, and the wall showing from its cache."""
    wait, relay, player = pair.wait, pair.relay, pair.player
    _ok(pair.api.post(f"/clients/{pair.client_id}/token"))
    wait.until(lambda: relay.seen("GET", pair.manifest_path, 401), "the revoked token to be refused the wall's feed")
    wait.until(
        lambda: [line for line in player.events("pull.refused") if line.get("status") == 401],
        "the Player's journal to say the wall's feed was refused its token",
    )
    wait.until(
        lambda: [
            event
            for event in server.events()
            if event.get("logger") == "arrt.programming.access" and "Refused a Player request" in event.get("message", "")
        ],
        "the server's log to record the refusal",
    )
    wait.until(lambda: relay.seen("GET", "/client", 401), "the revoked token to be refused the client document", seconds=75.0)
    refused = wait.until(
        lambda: [line for line in player.events("client.refused") if line.get("status") == 401],
        "the Player's journal to say the server refused its client document",
    )
    assert "CLIENT_TOKEN" in refused[0]["message"]

    outlasted = len(relay.seen("GET", pair.manifest_path, 401)) + REFUSALS_OUTLASTED
    wait.until(lambda: len(relay.seen("GET", pair.manifest_path, 401)) >= outlasted, f"{REFUSALS_OUTLASTED} more refused polls")
    kept = player.record("file-screen-0")
    assert (kept["outcome"], kept["wall_id"], kept["work_id"]) == ("picture", pair.wall_id, shown["work_id"]), wait.story()
    assert hashlib.sha256((player.drawn / "file-screen-0" / kept["picture"]).read_bytes()).hexdigest() == kept["picture_sha256"]
    still = player.record("file-label-0")
    assert (still["outcome"], still["work_id"]) == ("caption", shown["work_id"]), wait.story()


def test_a_real_player_shows_the_wall_the_server_hangs_and_keeps_it_when_its_token_is_revoked(
    settings, service, wall_id, ready_work, decodable_jpeg, server, relay, players
):
    # Two works, each a real picture of its own, before the server starts.
    works = [
        _seed_work(service, settings, ready_work, decodable_jpeg, "Nighthawks", (400, 300), (160, 40, 40)),
        _seed_work(service, settings, ready_work, decodable_jpeg, "Automat", (300, 400), (40, 120, 160)),
    ]
    base_url = server.start()
    relay.upstream = base_url
    relay_url = relay.start()
    api = httpx.Client(base_url=base_url + "/api", timeout=30.0)
    hung = _hang_two_works_for_a_file_player(api, wall_id, works)
    media = _published_media(base_url, wall_id, hung["token"], settings, works)

    player = players(relay_url, hung["token"])
    wait = Waiting(server, relay, player)
    pair = Pair(api, relay, player, wait, wall_id, hung["client_id"], hung["label_id"], {w.id: w.title for w in works})

    _the_feed_is_adopted(pair, media)
    shown = _the_wall_is_drawn(pair)
    _the_server_hears_it(pair, shown)
    _the_label_is_drawn(pair, shown)

    # The client document polled again, unchanged: a 304. The Player polls it every
    # 30 s, a constant of its own with no setting, so this is the test's longest wait.
    wait.until(lambda: relay.seen("GET", "/client", 304), "a later poll of the client document to be answered 304", seconds=75.0)

    # Nothing either side said was refused or an error, while they agreed.
    assert not [line for line in player.lines() if line.get("level") in ("ERROR", "CRITICAL")], wait.story()
    assert not [exchange for exchange in relay.exchanges if exchange[2] >= 400], wait.story()

    _the_revoked_token_is_refused_and_the_wall_kept(pair, server, shown)

    # SIGTERM ends it, cleanly.
    assert player.terminate() == 0, wait.story()
