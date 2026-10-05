"""Deployment configuration for the Player.

Every value here differs between the dev Mac and the Pi, so none of them may be a
literal in source. A fresh checkout runs by copying `.env.example` to `.env` and
filling it in — never by editing a module.

**A Player is a client** (`clients.md`): one install, one token, driving any
number of walls. The host is told three things — the server, its token and where
to keep its cache — and learns its walls from the server. So nothing here names a
wall. What a wall needs on this host (its manifest, its renders, its heartbeat,
the Frame's store) is derived from `CACHE_DIR` and the wall's id by `wall()`, so
two walls on one client can never share a file.

**The Frame is an output this client may or may not have.** `TV_ADDRESS` present
means it has one, named `frame`, and the television's and the label panel's
settings are read; absent means it has none, and none of them are required.

Resolution is a function rather than module-level constants, so importing this
module does not require an environment — otherwise the test suite and every tool
that merely wants to read a docstring would need one. Fail-fast is preserved by
resolving at process start, which is where a missing value should stop things.

**This plane knows nothing about the television's physical size.** The mat is
already composed into the render it is handed, so the only panel geometry here is
the e-paper label's, and a value for the TV's diagonal appearing in this file
would be the cross-plane drift `operational-spec.md` § Configuration warns about.
"""

import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# The heartbeat's own module owns what its file is called; this only reports it
# in the startup line.
from postarr.heartbeat import path_in as heartbeat_path_in

#: The Frame's own store, in the wall's directory beside the manifest it reads.
#: The Frame worker is its sole writer and nothing else ever opens it.
STATE_FILENAME: Final[str] = "display-state.sqlite"

#: The last good pulled manifest, in the wall's directory.
CACHED_MANIFEST_FILENAME: Final[str] = "manifest.json"

#: The last good client document (`GET /client`), directly under `CACHE_DIR`, so
#: a client that starts while the server is down still knows its walls. **A
#: leading dot, and that is what keeps it apart from the walls' directories**: a
#: wall id may not begin with one (`wall()`), so no wall's directory can be named
#: this.
CLIENT_DOCUMENT_FILENAME: Final[str] = ".client.json"

#: The name of this client's Frame output, as it reports it and as a curator
#: assigns a wall to it. One per client: a client drives at most one television.
FRAME_OUTPUT: Final[str] = "frame"

#: How often the client asks the server which walls it drives. Assigning a wall
#: therefore reaches the screen within about this long; it is a curatorial act,
#: not a `next`, and half a minute of latency is nothing beside it.
DEFAULT_CLIENT_POLL_SECONDS: Final[float] = 30.0

#: The settings a Player configured for one wall used, each with what replaced
#: it. **Refused by name rather than ignored**, because a stale `.env` that was
#: half-read would start a Player that pulls nothing for the wall its operator
#: thinks it serves — and says nothing, since every one of these was read once
#: and never consulted again.
RETIRED_SETTINGS: Final[dict[str, str]] = {
    "WALL_ID": (
        "a client learns its walls from the server: assign the wall to this client on Settings › Clients "
        "and remove WALL_ID from .env"
    ),
    "WALL_TOKEN": "the per-wall token is replaced by this client's token: set CLIENT_TOKEN and remove WALL_TOKEN",
    "MANIFEST_SOURCE": (
        "a client always pulls from SERVER_URL into CACHE_DIR; the file channel is retired, "
        "so remove MANIFEST_SOURCE from .env"
    ),
}

#: The name this process pairs to the television under. **Changing it costs a
#: pairing prompt somebody has to walk over and accept**: the set issues a token
#: per client name, so a new name is a new client to it and the existing token in
#: `TV_TOKEN_FILE` will not be honoured. It is `tvpi` because that is the name the
#: 2024 loader paired under, and the cutover replacing that process should
#: continue as the same client rather than arrive as a stranger.
DEFAULT_TV_CLIENT_NAME: Final[str] = "tvpi"

#: The e-paper label panel, in pixels. Defaults are the reference deployment's
#: 1448×1072 IT8951; overridable because nothing may hardcode a panel's size —
#: this product must run on any panel, and the 2024 plane's baked-in 648×480 is
#: the anti-pattern being retired.
DEFAULT_EPD_PANEL_WIDTH_PX: Final[int] = 1448
DEFAULT_EPD_PANEL_HEIGHT_PX: Final[int] = 1072


#: How far the rendered label is turned before it reaches the panel. 180 is what
#: the reference wall runs today — that panel is mounted with its ribbon uppermost
#: — and it is configuration because the next device's mounting is the next
#: device's business. Only half turns are made; `panel/epaper.py` says why.
DEFAULT_EPD_ROTATE_DEGREES: Final[int] = 180

#: How often the manifest's mtime is read. **Set by `next`, not by theme
#: switching** — a theme change tolerates seconds of latency happily, while a
#: human pressing "next" and waiting three seconds thinks the product is broken.
#: One `stat()` a second is free.
DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 1.0

#: Fallbacks for rotation, used only when a manifest carries no usable values.
#: The manifest normally resolves them — curation writes the theme's settings or
#: the deployment default into every one it publishes — so these are the answer
#: to "the file said nothing", not a second place the pace is configured.
DEFAULT_ROTATION_INTERVAL_SECONDS: Final[int] = 180
DEFAULT_ROTATION_SHUFFLE: Final[bool] = True

#: The television's brightness scale, which is neither 0-100 nor 0-10: this set
#: takes -4 through 10, and the sun-position curve is mapped onto that range.
#: Carried forward from the 2024 plane, which runs the wall on these numbers.
DEFAULT_TV_MIN_BRIGHTNESS: Final[int] = -4
DEFAULT_TV_MAX_BRIGHTNESS: Final[int] = 10

#: How often the sun is re-consulted. The sun moves slowly and the scale above
#: has fifteen steps, so anything under a minute would compute the same answer
#: repeatedly; five minutes puts a step boundary within half a step of when it
#: is due. The television is only written to when the computed value *changes*,
#: so this interval costs a local calculation and no traffic.
DEFAULT_BRIGHTNESS_INTERVAL_SECONDS: Final[float] = 300.0

#: The wait for the set's `image_added` acknowledgement. **A correctness value,
#: not a tuning knob**: the library's own default of 10 seconds was measured
#: failing on this deployment's 4K composites while the image landed anyway, so a
#: caller at the default is told an upload failed that succeeded, and a retry
#: duplicates it on the wall. Sized well above the 8.4 s a real upload measured.
DEFAULT_UPLOAD_TIMEOUT_SECONDS: Final[float] = 60.0

#: The ceiling on opening the art channel. `start_listening()` has been observed
#: **hanging** rather than raising, so a caller that does not impose its own bound
#: never returns at all — which for an unattended daemon is a wedge, not an error.
#: The trigger is not art mode being off, as this note once said: the channel
#: opens against a dark panel, and the hang has been seen in art mode after many
#: connections in quick succession.
DEFAULT_TV_CONNECT_TIMEOUT_SECONDS: Final[float] = 30.0

#: How long a work whose upload failed is left alone before it is tried again.
#: **A television that is reachable and refuses one image is a different fault
#: from one that is asleep**, and it does not back off with the connection: the
#: pass would otherwise retry it every second, each attempt costing a round trip,
#: a WARNING and a row rewritten. `observability-strategy.md` sizes writes on this
#: medium deliberately, and an unbounded small-write source on an SD card is the
#: thing it says not to build. Wall time rather than elapsed, so the wait survives
#: a restart — a crash loop must not turn into a retry loop.
DEFAULT_UPLOAD_RETRY_SECONDS: Final[float] = 300.0

#: How long the set is given to announce that it is displaying an image it was
#: asked for. **A selection is confirmed rather than assumed, and this is the
#: window.** The announcement has been measured arriving 0.49 s and 1.04 s after
#: the request, so this is sized well above that; the reason it exists at all is
#: the failure it catches. A television whose panel is dark accepts
#: `select_image`, returns no error, emits no event, and goes on displaying
#: whatever it displayed before — indefinitely. A daemon that trusted the call's
#: return would report a rotation it did not perform, once per interval, for as
#: long as the set stayed dark.
#:
#: **It is a ceiling on the failing path only.** A set that is working answers
#: inside a second and the wait ends there, so raising this does not slow
#: rotation; it only lengthens how long a dark wall takes to be reported.
DEFAULT_SELECT_CONFIRM_SECONDS: Final[float] = 8.0

#: Reconnection backoff after the television goes away. An asleep set is the
#: expected operating condition rather than an incident, so the ceiling is low
#: enough that the wall resumes promptly when someone turns it on and high enough
#: that a night of standby is not a night of connection attempts.
DEFAULT_TV_RETRY_MIN_SECONDS: Final[float] = 5.0
DEFAULT_TV_RETRY_MAX_SECONDS: Final[float] = 300.0


class ConfigError(RuntimeError):
    """A deployment value is missing or unusable, and starting would be worse."""


class WallIdUnusable(ValueError):
    """A wall id this client will not make a directory of.

    Ids are minted by the server, and every one it mints today is a UUID. The id
    names a directory under `CACHE_DIR`, so one that is not a single plain path
    component (`..`, `a/b`, a leading dot) would put a wall's files somewhere
    other than its own directory — beside another wall's, or outside the cache.
    Refused by name rather than cleaned, because a cleaned id is a second wall's
    directory waiting to happen.
    """


_PLAIN_COMPONENT: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*")


@dataclass(frozen=True)
class WallSettings:
    """One wall as this client serves it: where its files live and how it is reached.

    Every worker has one, whatever output it draws on. **The paths are derived,
    never configured**: the wall's directory is `CACHE_DIR/<wall id>`, and its
    manifest, renders and heartbeat are fixed names inside it. That is the whole
    mechanism keeping two walls on one client apart — there is no listing, no
    glob and no wall id read from a document to choose a file.
    """

    wall_id: str
    #: `CACHE_DIR/<wall id>`: the pulled manifest, the renders it names, the
    #: wall's heartbeat and, on the Frame, the wall's store.
    wall_dir: Path
    #: The server's base URL, with no trailing slash.
    server_url: str
    #: This client's token. Kept out of `repr` and out of every startup line,
    #: because both reach the journal.
    client_token: str = field(repr=False)
    poll_interval_seconds: float
    rotation_interval_fallback_seconds: int
    rotation_shuffle_fallback: bool

    @property
    def manifest_path(self) -> Path:
        """The last good manifest the pull cached, and the only file the wall waits on.

        Written only once every render it names is cached and verified, so the
        watcher reads a document whose every picture is already here.
        """
        return self.wall_dir / CACHED_MANIFEST_FILENAME

    @property
    def render_root(self) -> Path:
        """What an entry's `render_path` is relative to: this wall's own cache."""
        return self.wall_dir

    @property
    def heartbeat_root(self) -> Path:
        """Where this wall's heartbeat file is written, for the pull to forward.

        **Never a directory the server writes into.** A server sharing this host
        keeps each heartbeat it is POSTed under its own `ART_ROOT`, and a Player
        that wrote there too would see the server's write as a new heartbeat, post
        it again, and loop once a poll. In the wall's own cache the file is this
        wall's alone.
        """
        return self.wall_dir

    @property
    def state_path(self) -> Path:
        """The Frame's store for this wall. The Frame worker is its sole writer."""
        return self.wall_dir / STATE_FILENAME

    def wall_lines(self) -> dict[str, object]:
        """The wall's part of a worker's startup line. Never the token."""
        return {
            # **The wall, first among the paths it decides.** A wall the server
            # has published nothing for produces a manifest that never arrives;
            # this puts which wall, and which directory, one `journalctl` away.
            "wall_id": self.wall_id,
            "wall_dir": str(self.wall_dir),
            "manifest_path": str(self.manifest_path),
            "heartbeat_path": str(heartbeat_path_in(self.heartbeat_root, self.wall_id)),
            "server_url": self.server_url,
        }


@dataclass(frozen=True)
class FrameSettings:
    """The Frame output: the television, the sun it follows, and the label panel beside it.

    Present only on a client configured with `TV_ADDRESS`. **The label panel is
    here rather than on the client**, because it annotates the picture on the
    Frame and belongs to the wall shown there: one worker decides both, so they
    can never disagree.
    """

    tv_address: str
    tv_port: int
    tv_token_file: Path
    tv_client_name: str

    #: The **e-paper label** panel, never the television's. This plane is handed
    #: a composed canvas and never needs the TV's size; holding one here is how
    #: the two panels' geometry came to be confused in the first place.
    epd_panel_width_px: int
    epd_panel_height_px: int
    epd_rotate_degrees: int

    #: The two physical facts that decide how large the label's type has to be,
    #: and **the only values in this class with no default**. Everything else
    #: falls back to the reference wall's number; these two may not, because a
    #: guessed viewing distance produces type that is silently illegible — the
    #: failure that shipped here undetected through a hardware probe, a review and
    #: a cutover, at half the size a letter must reach to be resolvable at all.
    #:
    #: Unset is `None` rather than an error: a device with a panel configured and
    #: no stated viewing conditions loses its *label surface*, with a named
    #: reason, while the television keeps rotating. Refusing to start would break
    #: two rules this plane holds — nothing about the label may stop the wall, and
    #: a device with no usable label surface is a configuration rather than a
    #: fault. `panel/legibility.py` is where the arithmetic and the refusal live.
    #:
    #: Inches for both, so nobody has to remember which one is feet.
    epd_panel_diagonal_inches: float | None
    epd_viewing_distance_inches: float | None

    #: The clear border, **when the deployment overrides the derived one**. It
    #: normally derives from the type scale, because a border trades directly
    #: against how many lines survive the drop rule and so cannot be picked
    #: independently of the floor that decides how many lines there are. The
    #: override exists for the surface whose border is a physical fact rather than
    #: a typographic choice — a device drawing its label into the mat area around
    #: an artwork does not get to choose where the picture ends.
    epd_margin_px: int | None

    #: omni-epd's identifier for this device's panel, or empty for a device that
    #: has none. **Empty is a supported deployment, not a broken one**
    #: (`architecture.md` § Direction): a wall whose device drives a television
    #: and nothing else is exactly what most of them are, and it must not be
    #: reported as a fault. `omni_epd.mock` drives the library's own no-op device
    #: on a machine where the panel is absent but the driver is installed.
    epd_device: str

    latitude: float
    longitude: float
    location_name: str
    location_region: str

    tv_min_brightness: int
    tv_max_brightness: int

    brightness_interval_seconds: float
    upload_timeout_seconds: float
    upload_retry_seconds: float
    select_confirm_seconds: float
    tv_connect_timeout_seconds: float
    tv_retry_min_seconds: float
    tv_retry_max_seconds: float

    def _viewing_conditions(self) -> str:
        """The panel's diagonal and its reading distance, or what their absence costs.

        Says the consequence rather than the word "unset", because "unset" reads
        as a value nobody needed: a reader who has not met this pair cannot tell
        from that whether their label is missing on purpose.
        """
        if self.epd_panel_diagonal_inches is None or self.epd_viewing_distance_inches is None:
            return "(not stated — no label can be sized, so this device draws none)"
        return f'{self.epd_panel_diagonal_inches}" panel read from {self.epd_viewing_distance_inches}"'

    def frame_lines(self) -> dict[str, object]:
        """The Frame's part of a startup line, so a misconfiguration is one line away.

        This plane's own panel geometry, per `operational-spec.md`
        § Configuration — a wrong panel otherwise shows up as a label that renders
        off the edge of a display nobody is looking at closely.

        No secret is resolvable from these. The pairing token is a **path** here,
        never its contents.
        """
        return {
            "epd_panel_px": f"{self.epd_panel_width_px}x{self.epd_panel_height_px}",
            # **The line that would have caught the defect this pair exists for.**
            # A wrong viewing distance is invisible everywhere else: the daemon
            # starts, the panel draws, every test passes, and the only symptom is
            # type nobody can read from where they stand. Naming both facts in the
            # startup line puts them one `journalctl` away from the person who
            # typed them.
            "epd_viewing": self._viewing_conditions(),
            # Named even when empty, because "this device has no panel" and "this
            # device's panel is broken" look identical in a journal otherwise, and
            # only one of them is worth acting on.
            "epd_device": self.epd_device or "(none — this device renders no label)",
            "tv_address": f"{self.tv_address}:{self.tv_port}",
            "tv_token_file": str(self.tv_token_file),
            "tv_client_name": self.tv_client_name,
        }


@dataclass(frozen=True)
class Settings(WallSettings, FrameSettings):
    """One wall on the Frame: what the Frame's loop (`Daemon`) is built from.

    **Both halves, as one object, because the loop reads both.** It is a
    `WallSettings`, so the same pull that serves a wall on any output serves this
    one, and a `FrameSettings`, so the label surface is built from it as it was
    when a Player served one wall. Made by `ClientSettings.frame_wall`.
    """

    def startup_lines(self) -> dict[str, object]:
        return {**self.wall_lines(), "state_path": str(self.state_path), **self.frame_lines()}


@dataclass(frozen=True)
class ClientSettings:
    """Everything this Player needs from its environment, resolved once."""

    server_url: str
    client_token: str = field(repr=False)
    #: Local disk, not a network mount: the point of the cache is that it is
    #: there when the server is not.
    cache_dir: Path
    poll_interval_seconds: float
    rotation_interval_fallback_seconds: int
    rotation_shuffle_fallback: bool
    #: The Frame output, or None for a client that has none.
    frame: FrameSettings | None
    client_poll_seconds: float = DEFAULT_CLIENT_POLL_SECONDS

    @property
    def client_document_path(self) -> Path:
        return self.cache_dir / CLIENT_DOCUMENT_FILENAME

    def wall(self, wall_id: str) -> WallSettings:
        """One wall's settings, its directory derived from its id. Raises `WallIdUnusable`."""
        if not _PLAIN_COMPONENT.fullmatch(wall_id):
            raise WallIdUnusable(
                f"the server named a wall {wall_id!r}, which is not a plain directory name; "
                "this client keeps each wall's files in a directory named by its id, so it will not serve it"
            )
        return WallSettings(
            wall_id=wall_id,
            wall_dir=self.cache_dir / wall_id,
            server_url=self.server_url,
            client_token=self.client_token,
            poll_interval_seconds=self.poll_interval_seconds,
            rotation_interval_fallback_seconds=self.rotation_interval_fallback_seconds,
            rotation_shuffle_fallback=self.rotation_shuffle_fallback,
        )

    def frame_wall(self, wall_id: str) -> Settings:
        """One wall on this client's Frame. Raises `ValueError` on a client with no Frame."""
        if self.frame is None:
            raise ValueError("this client has no Frame output (TV_ADDRESS is not set)")
        wall = self.wall(wall_id)
        return Settings(**_fields_of(wall), **_fields_of(self.frame))

    def startup_lines(self) -> dict[str, object]:
        """The client's startup line. Never the token: a journal is what gets pasted into an issue."""
        return {
            "server_url": self.server_url,
            "cache_dir": str(self.cache_dir),
            "frame": self.frame.frame_lines() if self.frame is not None else "(none — TV_ADDRESS is not set)",
        }


def _fields_of(instance: object) -> dict[str, object]:
    """A dataclass's fields as keyword arguments, shallowly — `asdict` would copy the paths."""
    return {item.name: getattr(instance, item.name) for item in fields(instance)}  # type: ignore[arg-type]


def load(environ: dict[str, str] | None = None) -> ClientSettings:
    """Resolve the environment into `ClientSettings`, or refuse to start.

    `environ` is injectable so tests do not have to mutate the process's own — a
    test that set a value globally would leak it into every test after it.
    """
    load_dotenv()
    env = dict(os.environ) if environ is None else environ

    for name, replaced_by in RETIRED_SETTINGS.items():
        if env.get(name):
            raise ConfigError(f"{name} is retired: {replaced_by}.")

    cache_dir = Path(_require(env, "CACHE_DIR")).expanduser()
    return ClientSettings(
        server_url=_require(env, "SERVER_URL").rstrip("/"),
        client_token=_require(env, "CLIENT_TOKEN"),
        cache_dir=cache_dir,
        poll_interval_seconds=_float(env, "MANIFEST_POLL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS),
        rotation_interval_fallback_seconds=_int(env, "ROTATION_INTERVAL_SECONDS", DEFAULT_ROTATION_INTERVAL_SECONDS),
        rotation_shuffle_fallback=_bool(env, "ROTATION_SHUFFLE", DEFAULT_ROTATION_SHUFFLE),
        frame=_frame(env, cache_dir),
    )


def _frame(env: dict[str, str], cache_dir: Path) -> FrameSettings | None:
    """The Frame output when `TV_ADDRESS` is set, and None when it is not.

    **Its own required values are required only once it is asked for.** The sun
    drives the television's brightness and nothing else, so a client with no
    Frame has no use for a location; requiring one anyway is how an installer
    learns to type plausible values into keys that do nothing.

    A label panel with no Frame is refused rather than dropped: it is configured
    to caption the picture on a television this client does not drive.
    """
    if not env.get("TV_ADDRESS"):
        if (env.get("EPD_DEVICE") or "").strip():
            raise ConfigError(
                "EPD_DEVICE is set and TV_ADDRESS is not. The label panel captions the wall on this client's Frame, "
                "and without TV_ADDRESS this client has no Frame; set TV_ADDRESS or empty EPD_DEVICE."
            )
        return None

    token_file = env.get("TV_TOKEN_FILE") or ""
    return FrameSettings(
        tv_address=_require(env, "TV_ADDRESS"),
        tv_port=_int(env, "TV_PORT", 8002),
        tv_token_file=Path(token_file).expanduser() if token_file else cache_dir / "token_file",
        tv_client_name=env.get("TV_CLIENT_NAME") or DEFAULT_TV_CLIENT_NAME,
        epd_panel_width_px=_int(env, "EPD_PANEL_WIDTH_PX", DEFAULT_EPD_PANEL_WIDTH_PX),
        epd_panel_height_px=_int(env, "EPD_PANEL_HEIGHT_PX", DEFAULT_EPD_PANEL_HEIGHT_PX),
        epd_panel_diagonal_inches=_optional_float(env, "EPD_PANEL_DIAGONAL_INCHES"),
        epd_viewing_distance_inches=_optional_float(env, "EPD_VIEWING_DISTANCE_INCHES"),
        epd_margin_px=_optional_int(env, "EPD_MARGIN_PX"),
        epd_rotate_degrees=_int(env, "EPD_ROTATE_DEGREES", DEFAULT_EPD_ROTATE_DEGREES),
        epd_device=(env.get("EPD_DEVICE") or "").strip(),
        latitude=_float(env, "LATITUDE", None),
        longitude=_float(env, "LONGITUDE", None),
        location_name=_require(env, "LOCATION_NAME"),
        location_region=env.get("LOCATION_REGION") or "",
        tv_min_brightness=_int(env, "TV_MIN_BRIGHTNESS", DEFAULT_TV_MIN_BRIGHTNESS),
        tv_max_brightness=_int(env, "TV_MAX_BRIGHTNESS", DEFAULT_TV_MAX_BRIGHTNESS),
        brightness_interval_seconds=_float(env, "BRIGHTNESS_INTERVAL_SECONDS", DEFAULT_BRIGHTNESS_INTERVAL_SECONDS),
        upload_timeout_seconds=_float(env, "TV_UPLOAD_TIMEOUT_SECONDS", DEFAULT_UPLOAD_TIMEOUT_SECONDS),
        upload_retry_seconds=_float(env, "TV_UPLOAD_RETRY_SECONDS", DEFAULT_UPLOAD_RETRY_SECONDS),
        select_confirm_seconds=_float(env, "TV_SELECT_CONFIRM_SECONDS", DEFAULT_SELECT_CONFIRM_SECONDS),
        tv_connect_timeout_seconds=_float(env, "TV_CONNECT_TIMEOUT_SECONDS", DEFAULT_TV_CONNECT_TIMEOUT_SECONDS),
        tv_retry_min_seconds=_float(env, "TV_RETRY_MIN_SECONDS", DEFAULT_TV_RETRY_MIN_SECONDS),
        tv_retry_max_seconds=_float(env, "TV_RETRY_MAX_SECONDS", DEFAULT_TV_RETRY_MAX_SECONDS),
    )


def _require(env: dict[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def _int(env: dict[str, str], name: str, default: int | None) -> int:
    raw = env.get(name)
    if not raw:
        if default is None:
            raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
        return default
    try:
        return int(raw)
    except ValueError as exc:
        # Refused rather than defaulted: a value somebody typed and got wrong is
        # a different thing from one they never typed, and quietly substituting
        # the default hides the typo behind behaviour that looks deliberate.
        raise ConfigError(f"{name} is {raw!r}, which is not a whole number.") from exc


def _optional_int(env: dict[str, str], name: str) -> int | None:
    """A whole number the deployment may simply not have. Still refused if mistyped.

    Absent and wrong stay different things here: not saying a value is a choice
    with a defined meaning downstream, while typing one badly is a mistake that
    must not be smoothed into `None`.
    """
    return None if not env.get(name) else _int(env, name, None)


def _optional_float(env: dict[str, str], name: str) -> float | None:
    """A measurement the deployment may not have taken. See `_optional_int`."""
    return None if not env.get(name) else _float(env, name, None)


def _float(env: dict[str, str], name: str, default: float | None) -> float:
    raw = env.get(name)
    if not raw:
        if default is None:
            raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} is {raw!r}, which is not a number.") from exc


def _bool(env: dict[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if not raw:
        return default
    return raw.strip().lower() not in {"false", "0", "no", "off"}
