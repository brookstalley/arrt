---
artifact: operational-spec
version: 1
depends_on:
  - artifact: architecture
  - artifact: nonfunctional-requirements
  - artifact: observability-strategy
last_validated: null
---

# Operational Specification

One machine, two systemd units, one shared directory. Operations here should be
boring, and this document exists mostly to make sure the two things that are *not*
boring — getting Python 3.14 onto a Pi, and having a restore path that actually
works — are decided rather than discovered.

> **Landed (wave 3, 2026-10-02; `re-architecture.md`).** The **server** (curation, with
> its catalogue and art tree) runs on the operator's NAS (TrueNAS SCALE) as a
> container, and the Pi keeps only the **Player** (today's display plane), whose
> code is in Arrt Player's repository. The NAS deployment is recorded in the
> operator's homelab repository, not here. This file describes the Player's host
> as it was while the two planes shared one Pi, plus what the server image needs
> that is product-side: the container build, its configuration contract and its
> backup. Sections below carry dated notes where they moved.

## Deployment Target

| | |
|---|---|
| Host | Raspberry Pi 4 Model B, 8 GB |
| OS | Raspberry Pi OS Trixie (Debian 13) |
| Boot media | SD card — see Risks |
| Processes | `curation` (Python 3.14, uv-managed standalone) and `display` (Python 3.13, system interpreter), both under systemd |
| Shared state | `ART_ROOT` on local disk |

> **Target after wave 3 (2026-09-30, `re-architecture.md` § Deployment target):**
>
> | | Server | Player |
> |---|---|---|
> | Host | The operator's NAS (TrueNAS SCALE, x86_64), as a custom app | The Pi at the wall (today's Raspberry Pi 4), one Player per wall |
> | Packaging | A container image in the operator's LAN registry | systemd unit, as today |
> | State | Catalogue and art tree on NAS storage | A local media cache plus `display-state.sqlite` |
> | Reached as | A LAN hostname through the operator's reverse proxy | Makes outbound HTTP to the server, nothing inbound |
>
> **There is no shared state in the target.** `ART_ROOT` stops being a directory
> two processes share and becomes the server's private data root. The Player
> gets its own cache root. Choosing that cache root, and deciding whether it lives
> on the card, is a wave-2 decision. Its writes are bounded by playlist churn,
> which is the additive profile § Risks already reasons about.

> **The container is hardened, and what it writes is a list** *(audit wave 2b, 2026-11-20,
> Chunk 42; `deploy/nas/compose.example.yaml`, held by `tests/preferences/test_compose_example.py`)*.
> Every capability is dropped (`cap_drop: [ALL]`) beside `no-new-privileges`, and the
> root filesystem is read-only (`read_only: true`), so the server writes only to three
> places the compose file names: `/art` (the art root), `/backups` (`BACKUP_DIR`), and
> `/tmp`, a tmpfs of 64 MB (`noexec`, `nosuid`, mode 1777) counted against `mem_limit`.
> The `/tmp` is a measurement, not a habit: on a read-only root SQLite spills a sort of
> about twenty thousand rows to a temporary file and failed with "disk I/O error"
> without one. **Dropping every capability removes root's override of file
> permissions, so the `user:` the compose file names must own `/art` and `/backups` on
> the host.** Measured by the chunk on the v0.11.0 image as an unprivileged uid, with
> nothing built or deployed: writes only under `/art` and `/backups`, the root
> untouched, `dezoomify-rs` running against a local source. Not measured: a long run, a
> restore, a source plugin that writes anywhere else, which would fail loudly here.

## The Service Account — decided

**Both units run as `tvpi`** (settled 2026-08-04). The name was the only part in
question and it is kept: it is what the committed unit, `deploy/README.md` and
this product's own history already say, and renaming would have bought nothing
but a diff across every one of them.

**The account was created at the cutover on 2026-08-11 and now exists** (uid 102).
It had not survived the Pi's rebuild onto a fresh card — see
`arrt-player:.prawduct/artifacts/platform-and-dependency-findings.md` § That card is gone — so this table is the
record of what was made, and the specification for making it again on the next
machine:

| | |
|---|---|
| Login | None. `--system`, no password, shell `/usr/sbin/nologin` |
| Home | `/var/lib/tvpi`, for tool state only — see below |
| Privilege | No sudo. Nothing either plane does needs root |
| Groups | `spi` and `gpio` — the e-paper HAT is reached through both; `video` — an HDMI wall opens the display card (`/dev/dri/card*`) |
| Owns | `/srv/art` (`ART_ROOT`) and `/opt/samsung-frame-art-loader` (the checkout the units execute from) |

**Create it as part of the systemd-unit cutover, not before.** The account, its
group memberships, moving `ART_ROOT` under it, and both unit files are one
change: any of them landing alone leaves a machine that is neither the old
arrangement nor the new one. That cutover is the work that installs the new
systemd units, and this account is created as part of it.

### Where the two trees live — settled at the cutover, 2026-08-11

**`ART_ROOT` is `/srv/art`. The checkout is `/opt/samsung-frame-art-loader`.**
Both are off any home directory, which is the whole point: a `--system` account
with `/usr/sbin/nologin` has no use for one, and this section had already made
that argument about the art tree without noticing it applied twice.

| | | Why this one |
|---|---|---|
| `ART_ROOT` | `/srv/art` | FHS reads `/srv` as site-specific data this system serves, which is what 647 MB of the operator's masters are. `/var/lib/samsung-art` was the alternative and fits `catalogue.sqlite` better; it lost because the tree is overwhelmingly the operator's corpus rather than the product's private state, and a path they may want to browse or restore should not read as internals. |
| Checkout | `/opt/samsung-frame-art-loader` | FHS reads `/opt` as software installed outside the package manager. Keeping code apart from data is the backup story in one line: **back up `/srv/art`, re-clone `/opt`.** `/srv/samsung-frame-art-loader` was the alternative and lost because it puts the thing you can always re-fetch beside the thing you can never lose. |

**The checkout's path was a requirement nobody had written down.** This section
said the account owns "the checkout the units execute from" and never said where
it was; both unit files said `/home/<user>/source/samsung-frame-art-loader`, which
is not a location anyone chose so much as the path the 2024 card happened to
have. It surfaced at the cutover as a hard blocker rather than a preference: the
only checkout on the machine sat at `/home/<login>/source/…` under a home
directory at mode `0700`, which `tvpi` cannot traverse at all. A path a service
account cannot reach is not a configuration detail, so the answer is recorded
here rather than left to whoever next reads a unit file.

**The account has a home at `/var/lib/tvpi`, and it holds tool state rather than
data.** This was not planned; it was measured. Created with `--no-create-home`,
the account's `HOME` is `/nonexistent`, and the first thing attempted under it
failed outright:

    error: Failed to initialize cache at `/nonexistent/.cache/uv`
      Caused by: failed to create directory `/nonexistent/.cache/uv`: Permission denied

uv needs a writable cache, and the curation plane additionally needs somewhere to
put the managed CPython 3.14 that § The Curation Interpreter commits this
deployment to — two directories, and the count is the argument. The alternative
was naming each one through its own environment variable (`UV_CACHE_DIR`,
`UV_PYTHON_INSTALL_DIR`, and whatever a later uv adds) in both unit files; a home
directory covers all of them and anything either plane wants later, in one line
at account creation, and `/var/lib` is where Debian puts system-account state.

**This does not reopen the argument above.** What that argument objects to is the
*art tree* living in a home directory — 647 MB of the operator's masters behind a
path that exists only because an account does. Tool state is the case a home
directory is actually for. The two are kept apart deliberately: `/var/lib/tvpi`
is disposable and rebuilt by a sync, `/srv/art` is the thing that must never be
lost, and no backup should ever have to tell them apart.

**`uv` lives at `/usr/local/bin/uv`, and both units name it absolutely.** Same
failure, same shape: the machine's only `uv` was at `/home/<login>/.local/bin/uv`,
behind the same `0700`. `deploy/README.md` had flagged the `PATH` question as
settle-at-install and offered two fixes — an absolute `ExecStart=` or an
`Environment=PATH=` line. The absolute path wins because the other one is how the
recovered 2024 unit came to carry pyenv shims and a stray editor directory in its
`PATH`, and because a missing interpreter should fail where it is named.

Deciding all three cost nothing in code, because every reader of the art path is
already configuration — `ART_ROOT` in the root `.env`, which is where the existing
norm against deployment values in source put it. The unit files are the only
things that carry the other two, and they are version-controlled.

## The Curation Interpreter — decided

> **Landed (wave 3, `re-architecture.md`).** This section solved "3.14 on a Pi",
> a problem that ended when curation moved to a container image on the NAS. There
> the image installs exactly the version in `.python-version`, uv-managed only
> (`tests/test_one_python.py` holds it, 2026-11-08). The Player keeps the Pi's
> system 3.13 for the e-paper driver's reasons (`architecture.md` § Overview &
> Topology), so the two-interpreter split survives, across two machines instead of
> within one.

**Raspberry Pi OS Trixie ships Python 3.13. The curation plane gets its 3.14 from
a uv-managed standalone build.** Since 2026-11-08 that build is the exact release
`.python-version` names at the repository root, and uv takes no other Python
(`tests/test_one_python.py`); until then this read `uv python install 3.14`.

> **Amended 2026-07-27, amended again 2026-08-02.** The sentence above read
> "Nothing in this product needs 3.14 except `3tears`, whose packages declare
> `requires-python = ">=3.14"`", and the first amendment replaced that with
> `3tears-models`, "which arrive with the discovery work". Both are retired: the
> catalogue takes no `3tears` core dependency, and `3tears-models` went to the
> opt-in `eval` group on 2026-08-02. **What holds the floor is stated once, in
> `project-preferences.md` § Language & Runtime — this amendment deliberately does
> not restate it**, because restating it here is what let a retired claim survive
> two revisions in this file. **Everything in this section that reasons about `3tears` core
> should be read through this amendment**, including the build-versus-relax
> analysis below, which is retained because it is why the floor is affordable, not
> as a live dependency claim.

The premise that made this a problem was wrong. It was recorded as a choice
between a 30–45 minute pyenv compile per patch release, relaxing `3tears` to 3.13,
or adding Docker — and the first of those set the price. But a prebuilt CPython
3.14 for this exact target already exists and is what uv installs:

```
cpython-3.14.4-linux-aarch64-gnu
  releases.astral.sh/github/python-build-standalone/releases/download/
  20260414/cpython-3.14.4+20260414-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz
```

Verified 2026-07-20 against `uv python list --all-platforms --all-arches`. It is a
download and extract — no compiler, no build dependencies, minutes at most. Trixie's
glibc is far above the build's baseline, and the Pi is aarch64, which is the same
fact the wheel audit already established.

So the compile cost that made relaxing `3tears` attractive does not exist. That
matters beyond convenience: relaxing `3tears` carried a real, *untested* behavioural
risk — asyncio internals and pydantic/langchain annotation resolution under eager
(3.13) versus lazy (3.14) `__annotations__`, which the 2026-07-19 audit could not
close because it was static. Keeping `3tears` unmodified means that risk never has
to be taken, and the Python version pin stays intact as a rationale for the
two-plane split rather than leaving the split on its other two legs.

> **Rationale re-based 2026-07-27, re-based again 2026-08-02** (see the amendment at the head of this section). The paragraphs around this one reason about `3tears` *core*. The catalogue's durable tier is first-party code shaped to that framework's contract and imports none of it; since 2026-10-08 Ask's agent imports three 3tears packages, and 3tears core arrives with them (`arrt/pyproject.toml`). The compile-cost analysis above is still the reason the floor is affordable, which is why it is retained. **What the floor rests on is stated once, in `project-preferences.md` § Language & Runtime, and is not restated here.** The claim this passage used to carry — that `3tears-models` "requires" 3.14 and "the discovery work calls it" — was retired on 2026-08-02 when that package moved to the opt-in `eval` group. What holds the floor today is in `project-preferences.md` § Language & Runtime: Ask's 3tears packages, which require 3.14.


**The tradeoff this does incur:** curation's interpreter now comes from Astral's
distribution channel rather than Debian's, so CPython security fixes arrive by
raising `.python-version`, not by `apt upgrade` (before 2026-11-08, `uv python
upgrade`). That is a real patching obligation and it is
recorded in `security-model.md` § Supply Chain and in Routine Operations below.
The display plane is unaffected — it stays on the system 3.13, which is what gives
it the distro C bindings the e-paper driver needs.

**A standalone interpreter cannot see distro site-packages.** That is fine here, and
only because label rendering already moved to the display plane: curation's stack
(FastAPI, starlette, uvicorn, mcp, python-dotenv, pydantic, pillow, httpx) is all
wheels, verified against the PyPI JSON API. `pycairo` — the one source-only aarch64
dependency — is on the display side, where the GTK stack already lives. **If
anything needing distro C bindings is ever added to curation, this decision is what
it breaks.**

> **Corrected 2026-08-04, and the correction makes the argument stronger rather
> than weaker.** This sentence named *opencv, scikit-image and numpy* as part of
> curation's stack. They were forecast for "acquisition and the mat engine" and
> never declared: both landed 2026-08-03 needing none of the three, and
> `arrt/pyproject.toml` now records that as **a rejection rather than a
> deferral** — the LAB conversion and CIEDE2000 distance are thirty lines of
> fully-specified arithmetic in `library/acquisition/color.py`, and the dominant-colour
> fallback uses Pillow's median-cut quantiser where 2024 used OpenCV k-means.
>
> Worth noting how this survived: the same bundle that made the rejection wrote
> the rule that a descope must be walked back through every artifact that promised
> it, walked back the *fixture* descope, and left this one. The forecast lived in
> a sentence about interpreters, which is not where anyone looks when deciding a
> dependency.

## Process Management

Two systemd units, no ordering dependency between them — neither plane requires
the other to start, so either may come up first, in any order.

**`display`** — `Restart=always`. It is the plane whose downtime is visible, and
it should come back from anything without human action. Survives TV power-cycles,
websocket drops, and network outages by design.

**`curation`** — `Restart=on-failure`, plus a `MemoryMax`. The memory cap is the
one non-obvious setting and it exists because of co-location: a runaway
acquisition (a genuine gigapixel scan is 20–40× the measured corpus maximum) must
not be able to invoke the OOM killer against the display plane. Capping curation
converts a shared-fate failure into a contained one, which is most of what the
process split is for on a single box.

> **Landed (wave 3, 2026-10-02).** The `curation` unit and its `MemoryMax` existed
> because of co-location, and retired when the server left the Pi. Memory
> containment for a gigapixel acquisition is the container's memory limit, so a
> runaway fetch cannot starve the operator's other apps. *(The curation unit's file was deleted from `deploy/`
> on 2026-11-19: nothing had run it since the server moved to the NAS
> on 2026-10-02, and a file nothing ran was a second place for the paths and the
> memory bound to be wrong, and the five tests that held its environment file, its
> retrying, its clean-stop rule and its paths went with it. The container's `mem_limit` is the
> bound now; the Player's unit, and the rules in the paragraphs below as they
> apply to it, are `arrt-player`'s to hold.)*
> `display` keeps everything said here and
> below. The rate-limit rule applies to any unit the Player ships with.

**No unit may rely on systemd's stock start rate limit** (settled 2026-08-02).
The default is five starts in ten seconds, and `Restart=always` with a fault that
reproduces on every start exhausts it in about half a second — leaving the unit
permanently `failed`, having logged five lines, with nothing still trying. That
defeats the success criterion requiring an unattended failure to be visible
without inspecting the wall: it produces a dark television *and* a service that
gave up. Every unit therefore sets `StartLimitIntervalSec=0` in `[Unit]` (the
documented value for no rate limiting, and a `[Unit]` directive rather than a
`[Service]` one) together with a `RestartSec=` of at least five seconds, so a
persistent fault stays legible in `systemctl status` and keeps writing to the
journal instead of going quiet. The retry interval is also what makes the setting
safe: without it, "retry forever" would mean retrying at 100 ms.

*(Applied first to the recovered 2024 loader unit on 2026-08-02, which retired
with the 2024 plane at wave 5. The rule is stated for all units rather than that one,
because the same defaults ship with every unit file and the new display and
curation units are written against this section.)*

## Configuration

Environment variables via **one `.env` at the repository root, read by both
planes**, honouring the existing norm that deployment values never live in source.

**Every unit declares `EnvironmentFile=` pointing at that root `.env`, and never
prefixes it with `-`** (settled 2026-08-02). Both halves are the decision.

*Declared*, because the alternative on the table was to record the
`.env`-beside-`WorkingDirectory` placement as the contract and leave the unit
silent about it. A unit that names the file states its own dependency; one that
relies on a library's search path leaves the dependency discoverable only by
reading Python. The two resolve to the same file today, so this buys no new
capability — it buys the failure being attributable.

*Un-prefixed*, because that is the half that does real work. systemd treats a
missing un-prefixed `EnvironmentFile=` as fatal and refuses to start the unit,
naming the path it wanted. A `-` prefix makes it optional, which restores exactly
the silent failure this is meant to remove: the process starts, raises at import
against five missing variables, and dies for a reason nobody connects to a file
that was never placed.

**The directive is the value source — corrected 2026-08-06.** It was a presence
guard while `config.py` called `load_dotenv(override=True)`, which re-parsed the
same file inside the process and won. That `override=True` was retired, because
discarding an exported value in silence is this product's worst failure shape, so
python-dotenv now supplies *defaults* and whatever is already in the environment
wins. systemd has put this file's contents there before the process starts.

So the guarantee inverted, and the paragraph this replaces asserted the old one.
The two parsers **can** now disagree about what the process sees — they differ on
quoting and inline comments — and a mis-parsed value is live rather than
overwritten.

**Which plane is exposed, stated precisely, because a first version of this
correction was not.** `arrt.art_root` refuses to start against a directory
that is neither marked nor holding a catalogue, so a mis-parsed `ART_ROOT`
reports an error rather than quietly creating an empty second collection — for
the *curation* plane. The unit in `deploy/` starts `tvart.py`, the 2024 plane,
which reads `ART_ROOT` through the root `config.py` and calls `os.makedirs` on
what it finds. There is no curation unit there yet, so pointing at that guard
from the unit's own comment claimed a protection the process it starts does not
have.

For the 2024 plane the exposure stands. The other four required values raise at
import when a mis-parse leaves them empty, which covers the common case;
`ART_ROOT` is the one that silently creates instead. It closes when that plane is
retired and the curation unit lands beside it.

*(Settled 2026-08-01: this said "a `.env` file per plane", and what exists is one
shared root file — `.env.example` carries both planes' values, and
`arrt/config.py`'s bare `load_dotenv()` resolves it by walking up from the
module rather than from the working directory. One file is also the right answer
rather than merely the built one: the two values that **must** agree across planes
are `ART_ROOT` and the panel geometry, and two files are precisely how they come
to disagree. This matters before the systemd units are written — a per-plane
`.env` dropped beside a unit's `WorkingDirectory` is not the file the curation
plane reads, so it would be edited and have no effect.)*

**Two values must agree across both planes**, and both are silent failures when
they do not.

`ART_ROOT` is the first, which makes it the highest priority to hoist — already
scoped that way in the v1 list. A mismatch is a silent failure: curation writes
manifests nobody reads and display waits forever on a file that will never appear.

**`ART_ROOT` is also the only value both planes share** (corrected 2026-07-20).
Panel geometry was briefly listed as a second shared value; it is not, because
"panel geometry" named two different physical panels:

- **TV panel physical geometry** (this deployment: 50") — **curation only**. The mat is
  specified in physical units and the resolution floor is a minimum size on the
  wall, so curation needs it to judge whether a source is adequate, to show the
  curator what a work would look like, and to compose the mat. Display receives the
  `tv_display` rendition with the mat already in it and never needs the TV's size.
  *(Reversed by wave 4g, 2026-10-10: the TV panel's geometry and the mat's
  proportions are now **the Player's only**, below. The server judges a source
  against `QUALITY_MINIMUM_PX` and each wall's reported screens, and composes
  nothing.)*

  *(**Three values joined it on 2026-08-01** and are curation-only for the same
  reason: `MAT_WIDTH_INCHES`, `MAT_BOTTOM_WEIGHT` and `RESOLUTION_FLOOR_INCHES`.
  Panel geometry alone does not fix the artwork box — the mat has to be
  subtracted from it — so until these were configurable the box could not be
  constructed at all, and the readiness verdict that depends on it had been built
  and tested with no production caller. Each defaults to the reference
  deployment's figure, and the resolved box is logged at startup beside the panel
  it came from, because a wrong mat is otherwise visible only as works being
  labelled oddly in the review grid.)*

  *(**`RESOLUTION_FLOOR_INCHES` was retired on 2026-10-08** (wave 4b). The floor
  became the Library's quality profile, `QUALITY_MINIMUM_PX`, a minimum in pixels
  on the long edge that names no screen, default 1,000. The TV panel and the mat
  are now needed only to compose the canvas, and leave the server with
  compositing in wave 4. *(They did, in wave 4g, 2026-10-10. The server no
  longer reads `TV_PANEL_*`, `MAT_WIDTH_INCHES` or `MAT_BOTTOM_WEIGHT`, and does
  not warn about them either: they are the Player's settings under the same
  names, and one `.env` serves both planes on a development checkout, so a
  warning to remove them would break the Player.)* A deployment whose `.env` still sets the old key starts
  normally and logs a WARNING naming it and its replacement
  (`config.retired_setting`).)*

  *(**Three more joined them on 2026-08-03**, when the mat engine landed, and are
  curation-only for a different reason — display never asks a model anything:
  `MAT_MODEL`, `MAT_MAX_OUTPUT_TOKENS` and `MAT_IMAGE_MAX_EDGE`. The middle one
  is a correctness value rather than a limit: a reservation that does not clear
  the model's *reasoning* budget returns empty content billed in full, and the
  work is then matted by the mechanical fallback with only `MatColor.method`
  recording that anything went wrong. The model is logged at startup alongside
  the discovery model, and a deployment with no `OPENROUTER_API_KEY` logs that
  every mat will come from the dominant colour — which is a supported deployment,
  not a failure, but one worth reading in the journal rather than inferring from
  forty rows.)*
- **E-paper panel geometry** (1448×1072) — **display only**, for label typesetting.

  *(**Became configuration on 2026-08-06**, with the display plane's first
  modules: `EPD_PANEL_WIDTH_PX` and `EPD_PANEL_HEIGHT_PX`, defaulting to the
  reference panel's figures. Until then it was a number in prose, which is the
  same standing the TV's geometry had before it was hoisted — and the rule below
  that nothing may hardcode either panel's size applies to this one too. The
  plane logs the resolved pair at startup beside its `ART_ROOT`.)*

  *(**Read for the first time on 2026-08-07**, when the label reached the panel.
  Three values joined it, all display-only and all optional:*

  - *`EPD_DEVICE` — omni-epd's identifier for this device's panel
    (`waveshare_epd.it8951` on the reference wall, `omni_epd.mock` where the
    driver is installed and no panel is attached). **Empty means this device
    draws no label, which is a supported deployment rather than a broken one** —
    most display devices are a television and nothing else. It is also what
    decides whether the two optional dependency groups are needed at all, so it
    is the one value that changes what has to be installed.*
  - *`EPD_MARGIN_PX` (no default) — the clear border. **It derives from the type
    since 13B-1**, at half the primary tier, because it trades directly against
    how many lines survive the label's drop rule and so cannot be picked apart
    from the floor that decides how many lines there are. Set it only for a
    surface whose border is a physical fact rather than a typographic choice — a
    device drawing its label into the mat area around an artwork does not choose
    where the picture ends.*
  - *`EPD_ROTATE_DEGREES` (180) — how far the frame is turned before it reaches
    the panel, the reference wall's panel being mounted ribbon-uppermost. Only 0
    and 180 are accepted; a quarter turn exchanges the panel's width and height,
    so the label would have to be laid out against the swapped geometry.*

  *(**Two more joined them on 2026-08-11 with the derived type floor, and they are
  the only settings in this plane with no default and no fallback:**)*

  - *`EPD_PANEL_DIAGONAL_INCHES` and `EPD_VIEWING_DISTANCE_INCHES` — the label
    panel's diagonal and the distance it is read from, inches for both. Together
    they decide every type size on the label. **A guess is the one thing that must
    not happen here**: a wrong distance produces silently illegible type, which is
    what this deployment ran for as long as the sizes were fixed constants, and it
    looks like success from every direction except standing in front of the panel.
    A device that names a panel and states neither loses its **label surface**,
    with the missing key named, while the television goes on rotating — the same
    path a missing driver takes. It is not a refusal to start, because nothing
    about the label may stop the wall.*

  *The panel's own reported size is compared against the configured pair at
  startup and a disagreement is **warned about rather than refused**, the same
  call `panel_check` makes about the television's diagonal and for the same
  reason: a wrong size gives a label that looks wrong, a refusal gives no label at
  all, and the label may never be a reason the wall stops.)*

> **Landed (wave 4g, 2026-10-10; `re-architecture.md` § Compositing moves to the
> Player).** `TV_PANEL_*`, `MAT_WIDTH_INCHES` and `MAT_BOTTOM_WEIGHT` left curation's
> configuration and are the Player's, split along "settings flow down,
> capabilities flow up" (`re-architecture.md` § What is showing, and how it is
> shown). The label mode (e-ink panel, caption in the mat, or none) is a wall
> setting, chosen from what the Player reports. **Still open:** the caption mode,
> Player work in wave 6+ (#217), which is exactly the "device drawing its label
> into the mat area" the `EPD_MARGIN_PX` note above anticipated.
>
> *(Wave 4g, 2026-10-10: built. The server holds no screen geometry. The Player
> reads `TV_PANEL_*`, `MAT_WIDTH_INCHES` and `MAT_BOTTOM_WEIGHT`.
> `ROTATION_INTERVAL_SECONDS` and `ROTATION_SHUFFLE` are the server's alone (the
> pace a wall plays at when it has chosen none; a theme's until 2026-10-13, #353),
> and the Player no longer reads them.)*
>
> *(2026-10-08, pointer only: `feeds-and-players.md` ruling 7 made the mat's
> width the client's, so `MAT_*` moves to the Player's configuration with
> `TV_PANEL_*` rather than becoming a wall setting; the manifest carries only the
> mat's mode. The label mode's values are `none`, `caption` and `overlay`, a
> label on its own surface being a label output. `player-contract.md`
> § Presentation settings.)*
>
> In wave 2 the shared `.env` stops being shared. The Player gains the server's
> base URL and a cache directory, and keeps the `WALL_ID` it already has.
> *(2026-10-02, `clients.md`: the Player is now a client. It holds
> `SERVER_URL`, `CLIENT_TOKEN` and `CACHE_DIR`, learns its walls from the
> server, and refuses `WALL_ID`, `WALL_TOKEN` and `MANIFEST_SOURCE` by name.)* The server keeps its own configuration, delivered as
> container environment on the NAS. The single root `.env` read by both planes is
> a property of co-location and retires with it.

Because neither is shared, neither can drift between planes. A wrong TV size is
still a real defect — the mat comes out the wrong width and the review grid's
warnings are computed against a TV that isn't there — but it is a single-plane
misconfiguration, not a cross-plane mismatch. **Nothing may hardcode either panel's
size**; this deployment is a 50" Frame but the product must run on any.

**Each plane logs its resolved `ART_ROOT` and its own panel geometry at startup**,
so a misconfiguration is one journal line away rather than a mystery.

Secrets live in `.env`, never in source, never in a committed file — the
repository is public (`security-model.md`).

## Backup and Restore

**What is backed up: the catalogue, and nothing else.** The image tree is
deliberately excluded — every source image is re-fetchable from its source URL,
while the curatorial layer (verdicts, canonical-instance choices and their
reasons, hand-approved mat colours, theme membership, suppression scopes) is not
reproducible at any price except re-running discovery and re-asking the curator
every judgement they have already made.

> **Every kind of file under `ART_ROOT` is excluded.** Upstream originals in the
> image tree; derived renditions and `thumbs/`, regenerated per device; and — since
> 2026-10-06 — `pictures/`, the picture store, where every picture fetched from
> outside is kept for good (`data-model.md` § Direction). The store is excluded by
> the owner's ruling of that day: it can be rebuilt, and it has no ceiling.
> `arrt/tests/unit/test_backup_writer.py` asserts that a generation carries none of
> it. **A restore without the store is a degraded review surface, not a loss:** a
> card whose picture is not on disk reports its source URL, and the store fills
> again only as instances are found again, since nothing re-fetches a kept picture
> that is missing. The **judgements** made against those pictures — which instance
> was selected, the rationale, which images were rejected — are catalogue rows and
> are backed up. *(Until 2026-10-06 the third kind was `previews/`, disposable and
> swept; `previews/` is now read only by the startup import, and removed by hand
> once its log line reports `done`.)*

> **`kept-answers.sqlite` is not backed up either, and a backup may skip it**
> (2026-10-02, `build-plan-topics-and-destinations.md` Chunk 03c). It holds
> answers from slow foreign sources, Wikidata's first, kept for a week so a
> restart does not put the next page view behind a query of several seconds
> (`data-model.md` § KeptAnswer). Here **disposable does mean "it comes back"**:
> deleting the file, or restoring without it, costs each page section one more
> question of its source and loses no record. So it is a file apart from the
> catalogue, and its `-wal` and `-shm` companions go with it. The plane replaces
> it by itself when it is damaged or of another format (`kept.replaced` in the
> journal), so deleting it by hand is never a repair step, only a way to make
> every registry page ask again.

> **`sources/` is not backed up either** (2026-10-06, `build-plan-nga-source.md`).
> Each source plugin's own directory holds a copy of what it can fetch again; the
> first is `sources/nga/`, the NGA's open data (about 43 MB gzipped). Deleting it
> costs one download, of about 43 MB, at the next query that asks the NGA. The
> plugin asks for each file at most once a day, conditionally, and holds the parsed
> copy (about 80 MB) in memory only within six hours of an NGA query, which is the
> figure to keep under the container's memory limit (`nga.catalogue_loaded` and
> `nga.catalogue_released` in the journal mark both ends).

**Destination: another machine on the network** (desktop or NAS, over LAN or the
overlay network). Decided 2026-07-20. No third party, no cost, no credential on
the Pi beyond what already exists.

**Accepted limitation:** it only protects you if the destination is awake when the
backup runs. So the schedule assumes gaps and the retention keeps several
generations rather than one — a backup that silently stopped succeeding a month ago
is the failure mode, and it is the same silent-failure class as everything else in
this product. **Backup age is surfaced on the health panel** in absolute terms
alongside the display heartbeat: "last successful backup: 6 days ago".

**Use SQLite's backup API or `VACUUM INTO`, not a file copy.** Copying a SQLite
file out from under a live writer can capture a torn database. This is the sort of
thing that appears to work for a year and then does not.

### The restore path is a deliverable, not a paragraph

**A backup path that has never been restored from is a hope.** The restore path
ships with an exercise step: restore onto a scratch directory and confirm the
system comes up against it.

The design makes this unusually cheap to verify, and the reason is worth
understanding. **Restore is partial by design.** Drop the catalogue back with an
empty image tree, and:

- the manifest build finds no current render for any work *(a presentation
  master, since wave 4g)*,
- it excludes them all *and reports why*, per work,
- the health panel shows a theme with everything excluded and the reason,
- re-acquisition refills the tree, and works reappear as they complete.

The system self-heals **visibly**. Verifying a restore therefore does not require
staging gigabytes of imagery — which is exactly what makes the exercise something
that will actually get run rather than skipped.

> **Landed (wave 3, `re-architecture.md`).** The rule is the same: back up the
> curatorial layer, not the images. The source is the NAS, where the backup runs
> beside the server's storage, and "the destination is awake" is no longer the
> limitation it was from a Pi.
> - **The catalogue is one file**, holding both the Library's and Programming's
>   tables, so the backup takes one and a restore restores both halves together.
>   The split into two files, which would have the backup take the pair, is not
>   built and not a requirement now (the owner, ruling 9 of 2026-11-19). What a
>   Programming reference to a work the Library does not hold does after a restore
>   is the restore exercise's to test: Programming holds work ids as opaque
>   references and tolerates ones that no longer resolve
>   (`re-architecture.md` § Seam 1).
> - **The Player backs up nothing.** Its media cache re-pulls, and its TV bindings
>   are rebuilt by reconciliation against the set, as today.
> - **`presentation/` holds one master per work from wave 4b (2026-10-08)**,
>   excluded from backups like every derived class. At startup every accepted
>   work with no master *recorded* from its Original by today's rule (cap and
>   quality, `MASTER_RULE`) is queued to have one made. **A recorded master
>   whose file is gone is not found at startup**, since that is a query over rows;
>   it is remade the next time the work is prepared, which is the shape of #180
>   (a restored catalogue does not heal) and is tracked there. **Measured 2026-10-08** over the 46
>   originals in the owner's local 2024 tree (574 MB on disk): masters totalled
>   225 MB, about 4.9 MB a work on average (median 3.3 MB, largest 15.9 MB), 37%
>   of the originals; one original exceeded the 7,680 px cap. Making each took
>   0.34 s median and 1.8 s at most on the development Mac. So budget roughly
>   5 MB a work on the NAS, about 10 GB at 2,000 works. On the first start after
>   the upgrade the acquisition queue makes every held work's master, one at a
>   time, logging `preparation.masters_queued` with the count.
> - **The self-healing walk-through above changes shape in wave 4.** "No current
>   render" becomes "no presentation master", and a Player whose cache is empty
>   re-pulls once the server has regenerated the masters.

> **The backup writer is built, and a restore is not self-healing (2026-10-02,
> `build-plan-nas.md` Chunk 02).** With `BACKUP_DIR` set, the server takes a
> generation with `VACUUM INTO` at start (*since 2026-11-19, only when the
> newest generation is at least `BACKUP_INTERVAL_SECONDS` old; see below*) and
> then every `BACKUP_INTERVAL_SECONDS` (default daily), checks it with `PRAGMA
> integrity_check` before naming it, keeps the newest `BACKUP_KEEP` (default
> 14), and writes `backup-status.json` beside the catalogue only when all of that
> succeeded, which is what the health panel's age reads. Each pass logs
> `backup.completed` or `backup.failed`. **What a restore does, measured:** the
> walk-through above ("excludes them all and reports why", "re-acquisition
> refills the tree") is not what the code does today. Readiness checks a
> render's row, not its file, so a catalogue restored without its image tree
> publishes works whose renders are missing; and nothing re-fetches a master
> whose row survives its file. So a restore is **the catalogue plus the image
> tree**: the newest generation from `BACKUP_DIR` as `catalogue.sqlite`, and
> `raw/`, `ready/` and `thumbs/` from the art root's own snapshot. Making the
> partial restore self-heal is backlog. *(Wave 4g, 2026-10-10: readiness rests on
> the presentation master now and reads its file, so a master whose file is
> missing is refused by name (`no_rendition`) rather than published. The tree to
> restore is `raw/`, `presentation/` and `thumbs/`; nothing writes `ready/` any
> more.)* The exercise:
>
>     # into a scratch art root, never the live one
>     mkdir -p /tmp/restore && cp "$(ls -1 "$BACKUP_DIR"/catalogue-*Z.sqlite | tail -1)" /tmp/restore/catalogue.sqlite
>     cp -R "$ART_ROOT"/raw "$ART_ROOT"/presentation "$ART_ROOT"/thumbs /tmp/restore/
>     # BACKUP_DIR emptied: the scratch server's start-up backup would otherwise
>     # land in the live set and prune its oldest real generation
>     ART_ROOT=/tmp/restore BACKUP_DIR= CURATION_PORT=18790 uv run python -m arrt   # in arrt/
>
> **Then hang each wall's theme again** (Walls screen, or `POST
> /api/themes/{id}/activate`): a wall's published manifest is a file beside the
> catalogue, not a row in it, so a restored server answers "nothing has been
> published for this wall yet" until it is re-hung, while the wall keeps playing
> from its cache. Run on the Mac on 2026-10-02 against a copy of the dev
> library: the backup at start wrote its generation and receipt (the panel read
> "last backed up 2 seconds ago"); the restored server answered 404 for the
> wall's manifest until the theme was re-hung, then served 40 works, all 40 with
> media. *(Superseded 2026-11-19: no re-hang is needed today, and the restore
> has a step this omitted. See the next note.)*

> **The restore, as `arrt/tests/system/test_restore.py` runs it (2026-11-19,
> `build-plan-audit-wave-2.md` Chunk 06).** The test starts `python -m arrt` as
> a process over a seeded art root, lets its start-up pass write a generation,
> changes the household after it (a theme added, another hung), stops the
> server, restores, starts it again, and reads the works, the themes, each
> wall's hang and each wall's feed back over HTTP, as the wall's Player fetches
> it. It restores to two places: the same art root, over a catalogue a writer
> killed mid-transaction left with a hot journal; and a new art root given only
> the image tree. The steps (`restore` in that file is these, as code):
>
> 1. **Stop the server.**
> 2. **Remove what SQLite keeps beside the catalogue:** `catalogue.sqlite-journal`,
>    and a `-wal` and `-shm` if anything left them. *This step is new, and it is
>    the one that matters.* A server killed mid-write leaves a hot journal, and
>    the next open plays it into whatever file is then at the catalogue's path:
>    measured on SQLite 3.53.1, a generation copied in beside one opens as the
>    dead server's last commit, with `PRAGMA integrity_check` saying `ok`, so the
>    restore is silently undone (`test_a_restore_that_leaves_the_stale_journal_is_silently_undone`).
> 3. **Copy the newest `catalogue-*Z.sqlite` from `BACKUP_DIR` in beside the
>    catalogue, then rename it over `catalogue.sqlite`**, so the path holds the
>    old file or the whole generation, never half of one.
> 4. **On a new machine, restore the image tree** (`raw/`, `presentation/`,
>    `thumbs/`) from the art root's own snapshot. No feed file is needed.
> 5. **Start the server. Nothing needs re-hanging:** at every start
>    `services.reconcile()` publishes each wall's hung theme where the wall has
>    no feed on disk, and replaces a feed of another theme than the one hung, so
>    both a new art root and a stale feed left beside the restored catalogue are
>    answered with the restored hang's feed before the first request. Its
>    start-up backup is skipped while the newest generation is younger than
>    `BACKUP_INTERVAL_SECONDS`, so the generation restored from is not pruned.
>
> The exercise into a scratch art root is the same steps with `ART_ROOT` the
> scratch directory and `BACKUP_DIR` emptied, as in the block above. **Not
> measured:** a feed left beside the restored catalogue that names the theme
> hung but a work the generation does not hold (a work added after the backup);
> start-up `reconcile` asks the Library about every work a feed carries, and
> what it answers for an id it has never held is not exercised here. **A
> generation is refused by a release that carries the guard** when the release
> that took it expects a higher catalogue shape generation (below): restore it
> with that release or a newer one.

> **The catalogue records which release last opened it, and the shape that
> release expects (2026-11-19, `build-plan-audit-wave-2.md` Chunk 06; the shape
> generation since the boundary review the same day).** One row in the file's
> `catalogue_opened` table (`data-model.md` § CatalogueOpened): the release, the
> instant, the catalogue shape generation its code expects
> (`persistence/file.py` `SCHEMA_GENERATION`), and whether that open finished its
> migrations, written false before the first migration and true after the last.
> So before a rollback the operator can read which release last opened the file,
> when, and at which generation (`sqlite3 catalogue.sqlite 'SELECT * FROM
> catalogue_opened'`), and after a failed upgrade whether its migrations
> finished. **A release meeting a file recorded at a higher shape generation than
> its own refuses to start**, before it copies, widens or records anything, with a
> message naming both releases and both generations (journal: ERROR
> `catalogue.newer_release_refused`). **Release numbers are not compared**: a file
> recorded at the release's own generation or a lower one opens whatever release
> wrote it, so a rollback across no change to the shape (a bad patch release to
> the one before it) is the previous image alone. The generation is raised by
> hand at every migration and at any table, column or index taken away or
> redeclared, and `arrt/tests/unit/test_schema_generation.py` fails when the
> shape or the open's steps move that far without it; an addition alone leaves
> it. The open that raises it copies the file first (`pre-migration-*Z.sqlite`,
> as before a drop), so the release left behind has a copy it opens. **The
> refusal names the ways back that exist**: each `pre-migration-*Z.sqlite` and
> backup generation `catalogue-*Z.sqlite` in `BACKUP_DIR` and beside the
> catalogue whose own record that release would open, newest first, to be
> restored by the numbered steps above, journal step included; or, when there is
> none, says so, counts the copies it would refuse too, and names the newer
> release as the way on. A row from before generations (a release, no
> generation, written by a build of the audit's second wave before the boundary
> review) opens unless its release is numbered later than this one's, the one
> refusal the earlier guard made; a recorded release this code cannot read no
> longer stops a start (WARNING `catalogue.unreadable_release_recorded`). **This
> code's own release is checked before anything is written**: one that is not a
> version of three numbers stops the start by name (`UnreadableRelease`), because
> a build from before generations would refuse the file it was written into.
> **The guard protects a downgrade only to a release that carries it.** Measured
> once, 2026-11-19: v0.11.0's own code (`git archive v0.11.0`), opening a v0.1.0
> catalogue today's code had migrated and recorded as opened by 0.12.0, opened it
> without a word, read its four works and two walls, and left the row as it was;
> measured again after the generation was added, with the same result, the
> `schema_generation` column ignored. The build before the generation
> (`6e4faae5`) opens a file this code recorded under the same version string,
> keeping its generation, and refuses one recorded under a later version string,
> by release number, across no change to the shape. So a rollback to v0.11.0 or
> older across a migration is still the restore of the copy taken before it
> (§ Routine Operations, Rollback), never the image alone. **`PRAGMA
> user_version` is not this record**: it marks a migration in progress, from its
> copy until its last step.

> **Each generation says how long its copy took (2026-11-19).** `backup.completed`
> carries `copy_seconds`, the monotonic time `VACUUM INTO` took. The copy holds a
> SHARED lock the server's commits wait on, so this is the figure that would
> reopen the decision to stay on the rollback journal rather than WAL
> (`build-plan-audit-wave-2.md`, Goals): a copy measured long enough that commits
> wait on it.

> **A crash loop no longer takes the generations with it, and a destructive
> migration is copied first (2026-11-19,
> `build-plan-audit-wave-1.md`).** Retention counts generations, not days, so a server restarting every
> few minutes after an upgrade used to replace every generation from before it
> with copies of the migrated file within the hour. Two changes:
>
> - **The start-up pass is skipped while the newest generation is younger than
>   `BACKUP_INTERVAL_SECONDS`** (`backup.skipped_recent` in the journal), and
>   the first pass then comes when the interval since that generation ends. A
>   generation named later than the clock's now is not trusted, and the pass
>   runs. Fourteen starts within an hour leave the generation from before them
>   in place (`arrt/tests/unit/test_backup_writer.py`).
> - **Before any migration that drops a column or a table acts, the server
>   copies the catalogue** with `VACUUM INTO`, checked by `PRAGMA
>   integrity_check`, to `pre-migration-<UTC instant>.sqlite` in `BACKUP_DIR`,
>   or beside the catalogue when `BACKUP_DIR` is not set. The copy is the file
>   as the previous release left it, taken before the store widens it. A file
>   already on the current shape, or a new one, takes no copy. **The three
>   newest copies are kept, outside the generations' count**, so no number of
>   starts prunes them. **One copy is taken per migration, however many starts
>   it takes**: the copy marks the catalogue (`PRAGMA user_version`) until every
>   migration has run, and a start that finds the mark takes no copy, since the
>   file is no longer as the previous release left it. A migration failing on
>   every start therefore leaves the copy from before the upgrade the newest
>   one. A copy that
>   cannot be written (a full disk, a read-only directory) **stops the start**
>   with a message naming the directory and the remedy, and the catalogue is
>   left exactly as it was; nothing is dropped without its copy. The journal
>   says `catalogue.snapshot_taken` or `catalogue.snapshot_failed`.
>   (`arrt/tests/unit/test_pre_migration_snapshot.py`.)

## Routine Operations

| Operation | Procedure |
|---|---|
| Deploy | `git pull`, then `systemctl restart` each unit. No migration spans the planes — the manifest is regenerated, never migrated. **One-off after the 2026-08-12 upgrade: delete `theme-manifest.json` and `display-heartbeat.json` from `ART_ROOT`.** Both files became per-wall (`theme-manifest-{wall_id}.json`), nothing writes or reads the old paths any more, and nothing deletes them either — so they sit there holding whatever they held at the moment of the upgrade. Harmless to the running planes and *not* harmless to a person: a `jq` at the old path answers, with a document that will never change again, and looks exactly like a current one. Delete them and the ambiguity goes with them |
| Rollback | **The previous image alone, when the rollback crosses no change to the catalogue's shape** (2026-11-19): point the server's container at the image it ran before (`arrt:<commit>`, as `deploy/README.md` § The server on the NAS builds it; the compose file that names it is in the operator's homelab repository) and recreate the container. A release that carries the `catalogue_opened` record opens a file recorded at its own catalogue shape generation or a lower one, whatever release last opened it (§ Backup and Restore, the note on that record). **Across a raised generation it is a restore**: the older release refuses the file by name, changing nothing, and names the copies beside it that it opens (the `pre-migration-*Z.sqlite` the newer release's first start wrote, and any backup generation from before that start), or says there are none. Restore one by the numbered steps in § Backup and Restore, which `deploy/README.md` § The way back across such a migration gives too: they remove the journal before the copy goes in, without which the restore is silently undone. Then start the previous image. **A release from before the record (v0.11.0 and older) checks nothing**: it opens a file a newer release migrated without a word, so a rollback to one across a migration restores the copy first, every time. *(Until 2026-11-19 this row said `git checkout` the previous commit, restore, and restart both planes: a checkout is not how a container is rolled back, and its restore had no journal step. Until 2026-08-12 it was `git checkout` plus two restarts, which stopped being true the first time the schema dropped something.)* |
| Restart one plane | Safe at any time, in either order. The other is unaffected by design |
| **Cut a release** *(steps added in audit wave 2b, 2026-11-20)* | Two steps the tests hold, beside the release tooling's own: **(1) in the release's own commit**, add its tag to `RELEASES` in `arrt/tools/old_catalogue.py` and run `uv run python tools/old_catalogue.py` from `arrt/` in a checkout with the tags fetched; it makes the newest release from `HEAD`, since its tag does not exist yet, and writes its dump and its row in `arrt/tests/fixtures/catalogues/releases.json` (`tests/preferences/test_catalogue_release_dumps.py` is red until the row is there, Chunk 49). **(2) after a contract tag is cut**, `python3 contract/tools/freeze_release.py <version>` writes its frozen copy, `contract/released/<version>/` (`player-contract.md` § The package, Chunk 59); the next plan's first commit carries it. |
| Add disk headroom | **`tile-cache/` reclaims itself since 2026-08-03** and is no longer an operator chore: tiles are cached under the id of the source being fetched, and that directory is removed the moment the work holds a complete image. What survives a pass is exactly the tiles of a **partial** fetch, which is the one case they are worth their disk — they are what lets `art_catalogue(action='retry_acquisition')` finish the image without re-downloading what already arrived. So a `tile-cache/` that is large is a report that works are sitting partially fetched, and the remedy is to retry them rather than to delete the directory; deleting it is safe and costs those retries their head start. `temp/` belongs to the 2024 modules and is still pruned by hand until they are retired. **`api-cache/` needs no rule: the curation plane never creates one** — phase 2 asks museums over HTTP with no on-disk cache, and the directory exists only in the 2024 `config.py`. **`pictures/` is never reclaimed, by norm** (`data-model.md` § Direction, 2026-10-06): every picture fetched from outside is kept, two files each, and the store has no ceiling. Its files and bytes are on the health panel, counted at most ten minutes ago, so its growth is a figure to watch rather than a chore. **`previews/` is debris since the same day**: the startup import moves every file a row names into the store, logging `pictures.imported` with its counts; once that line reports `done`, `rm -rf previews/` loses nothing, including files no row ever named (#62). It matters here because § Risks opens with the SD card as the top operational risk |
| **Verify the spend ceiling** | In the OpenRouter console, confirm the key in `OPENROUTER_API_KEY` still carries a **USD 20 credit limit with a monthly reset**. **This setting is the entire cap** — nothing in this repository enforces one, by ratified decision, because an application-side meter that fails open is indistinguishable from one that works. A key whose limit was cleared, or a key swapped for an uncapped one, looks identical on every surface the product exposes right up to the bill. `cd arrt && uv run pytest -m live_api` asserts it mechanically (`test_the_key_reports_a_monthly_ceiling`) and costs a few cents to run |
| Bound the journal | On the Pi, install `arrt-player:deploy/journald.conf.d/10-bound-the-journal.conf` and restart `systemd-journald`. **`SystemMaxUse=` alone is not enough** — Raspberry Pi OS ships `Storage=volatile`, so the journal is in RAM and `RuntimeMaxUse=` is the directive that binds; the drop-in sets both. Verify with journald's own `Journal ... max` startup line, not `systemd-analyze cat-config`, which only proves the file parses — see § Risks |
| **Decide on a TV firmware update** | Auto-update is **off** (2026-08-04) and the set is held at 1310 with 1400 offered. Nothing arrives on its own, so this recurs whenever there is a reason to update. Default answer is stay: the update is one-way and every measured fact about this set is firmware-scoped. If one is ever taken, re-run `arrt-player:tools/tv_api_check.py --image <a 4K composite>` (`uv run python tools/tv_api_check.py` in an arrt-player checkout) — it is what says which behaviours moved |
| **Diagnosis after a reboot** | There is none from the journal: `Storage=volatile` means it does not survive one. If the wall froze and the Pi restarted, `journalctl` holds nothing about the run that failed. **Do not reach for `Storage=persistent` here** — it was declined on 2026-08-04 and switching it reverses a recorded decision and puts logging on the card, which is the top operational risk. Diagnose from the health surface's heartbeat age or the catalogue instead; see § Risks |
| Patch curation's CPython | Raise `.python-version` to the fixed release, at the root and in `arrt/` (`tests/test_one_python.py` holds the two equal), and land it. Then rebuild the image and redeploy it on the NAS; a checkout's next `uv sync` moves its venv onto the new pin. **Neither `uv python upgrade` nor `apt upgrade` does this:** the pin names an exact release, so uv reinstalls it, and `apt` patches only a system Python, which uv no longer takes. *(Changed 2026-11-08; until then this row read `uv python upgrade 3.14`, then rebuild the venv.)* |
| Re-pair the TV | Rotates the pairing token. Nothing to untrack first — `token_file` was untracked 2026-07-27 and the token now resolves under `ART_ROOT`, outside the checkout, so a `git pull` no longer deletes it and re-pairing needs no repo work at all. Just re-pair at the hardware. *(Updated 2026-08-01: this row still ordered an untracking step that is done, and carried a `git pull` hazard `security-model.md` withdrew on 2026-07-27.)* See `security-model.md` |

> **Landed (waves 3 and 5).** "Deploy" and "Rollback" are two: the server deploys as
> a new container image on the NAS, following the operator's homelab procedure, and
> the Player is deployed from its own repository (`arrt-player`), outside this
> file. "No migration spans the planes" stays true, because the manifest document is
> regenerated, never migrated. The HTTP contract's skew case, a Player older than
> the server's manifest major, is handled the way the file channel handled it:
> refuse the unknown major and keep the last manifest.
>
> *(Wave 4g, 2026-10-10: that case is now visible. The server publishes major 2
> only, and a wall whose Player's heartbeat does not list 2 (or lists no
> capabilities, which counts as major 1) carries a sentence on Walls and on the
> MCP `walls` read saying its Player cannot read the feed. The upgrade leaves two
> kinds of file behind in `ART_ROOT`, both read by nothing and safe to delete:
> each wall's major 1 manifest, `theme-manifest-{wall_id}.json`, and the
> composed canvases under `ready/`. The startup log names `ready/` when the
> migration forgets their rows.)*

## Failure Recovery

Mostly automatic; the table below is what a human would do when it is not.

| Symptom | First check | Action |
|---|---|---|
| TV showing one artwork indefinitely | Health panel: heartbeat age | If stale, `systemctl status display` and the journal |
| Label disagrees with the artwork | Journal for e-paper errors | The label path failed while rotation continued — by design, a panel failure never stops the TV |
| A theme shows fewer works than expected | The manifest build's exclusion report | It names the per-work reason. This is the designed surface, not a diagnostic dead end |
| Discovery refuses to start | The refusal text itself — it names the cause | *(Corrected 2026-08-02: this row sent the operator to `limit_remaining` on the health panel, a figure no surface exposes and which may not be trusted anyway — it lags by minutes, and was observed reporting credit remaining while live calls were already being refused.)* Two different refusals: **no key configured** says so and names `.env`; a run that started and then **halted_by_budget** means the provider refused the spend, for which the answer is the monthly UTC reset or a raised key limit |
| `resolve_images` refuses work ids as "already in flight" | The named run's status | It is always a `resolve` run, and a live one is always `resolving_images`. If it is genuinely searching, wait or `cancel` it. If nothing is actually working, startup reconciliation should have moved it to `interrupted`; that it did not is a bug, not an operator action. *(Corrected 2026-07-27: this row previously told the operator to approve or decline an `awaiting_approval` run to free the ids — a state a resolve run can never reach, so the advice named a run that cannot exist.)* |
| Acquisition fails on every work | Free disk space | The pre-acquisition guard should have caught it; if it did not, that is a bug in the guard. It refuses **before** a fetch begins and names the shortfall in GiB, so the refusal itself says whether disk is the cause. `MIN_FREE_BYTES` (default 2 GiB) is the floor, and it protects `catalogue.sqlite` on the same device rather than the fetch. A disk that fills, or turns read-only, in the middle of one work, or a database that cannot be written, pauses the queue and counts against no work (Activity › Queue says so, with a remedy), rather than giving every work up in turn |
| Acquisition fails on one work with a refused URL | `art_catalogue(action='sources')` for that work | The fetch policy refused the URL and the reason is recorded on the source. Schemes other than `http`/`https`, and hosts that resolve to this network rather than the open internet, are refused by design (`security-model.md` § The fetch trigger fired) — a source that needs one of those is a source this product will not fetch |
| Every tiled acquisition fails at once | `dezoomify-rs` on the unit's `PATH` | Acquisition raises rather than recording a failed fetch when the binary is absent, precisely so this is not mistaken for museums going away. Install it, or set `DEZOOMIFY_PATH` to where it lives |
| Every **Art Institute** acquisition raises, while other providers fetch fine | `ARTIC_USER_AGENT` in `.env` | An artic source records the museum's page for the object, and the tile fetcher needs the image service — which only the collection can be asked for. Unset, there is no way to reach those tiles, so acquisition raises by name rather than handing the fetcher a URL it cannot read. Set it and the same works fetch unchanged. Raises rather than records for the same reason the row above does: no source is at fault, and a `failed` row here would send its reader to the museum |
| Neither plane starts after a reboot | `systemctl status` — **not the journal** | The two ways this fails now are both refused by systemd *before* a process exists, so there is no application log line to find and `journalctl -u` is empty in exactly the cases you most want it. A missing `EnvironmentFile=` and a missing `/usr/local/bin/uv` are each named by `systemctl status`, which is the fastest diagnosis available and is why both are declared the way they are. `deploy/README.md` § How to tell your own install worked is the ordered set of checks |
| Both planes start, then exit at import | The journal, `journalctl -u <unit>` | Now there *is* a process, and this is the mismatched-or-missing-`ART_ROOT` case: `config.py` raises naming the first variable it could not resolve, and the unit retries visibly rather than giving up. Both planes log their resolved `ART_ROOT` on the way up, so a plane that got far enough to log it and still failed is a different fault from one that never started |

## Risks

**The SD card is the top operational risk, and it carries the irreplaceable
asset.** Write-heavy tile caching plus ~10 GB of artwork on consumer flash, with
`catalogue.sqlite` on the same device, in an always-on machine subject to
unexpected power loss. SQLite plus power loss on consumer flash is the classic Pi
corruption story.

**Decided 2026-08-04: the card stays.** `ART_ROOT` and the catalogue remain on the
128 GB SD card — no USB SSD, no SSD boot, no network storage. The reasoning is the
write *profile* rather than the medium's reputation. The image tree is additive and
written once: works are added, and rarely deleted or rebuilt, so the total bytes
written is bounded by the size of the collection rather than by churn. A collection
that eventually fills most of the card is on the order of a hundred gigabytes
written across years, which is a small fraction of any modern card's rated
endurance. What wears a card out is small writes that never stop, and this product
was thought to have exactly two — the journal and the display heartbeat.

> **Corrected 2026-08-04, on the machine: the journal is not one of them.**
> Raspberry Pi OS ships `Storage=volatile` in
> `/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf`, so the journal
> lives in `/run/log/journal` — a tmpfs — and **logging writes to RAM, not to the
> card.** Every sentence that treats journal growth as flash wear was describing a
> persistent journal this deployment does not have. **The display heartbeat is
> therefore the only continuous-write path to the card**, and its writer is not
> built, so no part of this wear reasoning is exercised by anything running today.
>
> The journal still gets an explicit bound, for the different reason given below,
> and **that bound is in force as of 2026-08-04** — evidenced by journald's own
> startup line moving from `max 156.1M` to `max 256M` across the restart, which is
> the check that proves the bound took. An earlier version of this paragraph
> cited `systemd-analyze cat-config` instead; that proves only that the drop-in
> parses, and it would have reported success just as happily while the directive
> bound nothing — which is exactly what was happening, because the file set only
> `SystemMaxUse=` and volatile storage is governed by `RuntimeMaxUse=`.

The heartbeat's bound is 60 s in `observability-strategy.md` § The Health Surface;
the journal's is the requirement below.

*The alternatives, and why they lost.* **USB SSD for `ART_ROOT`, or SSD boot** —
issue #13's two original options. Both work, and the Pi 4's USB 3.0 ports make
either comfortably fast, but they buy endurance this write profile does not need,
and USB boot adds a second failure class in enclosure and UASP behaviour for a
speed benefit nothing here requires. **`ART_ROOT` on network storage**, raised and
rejected the same day: `catalogue_path` resolves to `art_root / catalogue.sqlite`,
so this puts SQLite on a network filesystem — where advisory locking is unreliable,
and WAL, the mode that would otherwise reduce the exposure, cannot be used at all
because it requires shared memory between processes on a single host. It would also
put the wall's uptime behind a second machine, since the display plane polls the
manifest and reads the image tree continuously, and it would rest the manifest and
heartbeat channels' atomic write-and-rename on semantics a network filesystem
decides rather than the kernel.

> **Landed (wave 3, `re-architecture.md`).** Read this against the rejection above,
> which it does not overturn. The catalogue is on the NAS, but not on a network
> filesystem: the server process opens SQLite on storage **local to its own host**,
> so locking behaves as it did on the Pi. What was rejected on 2026-08-04 was the Pi
> reaching its catalogue over the network, and that stays rejected. The second
> objection (the wall's uptime behind a second machine) is answered by the Player's
> local cache, not ignored: the Player renders only from what it has already pulled
> (`nonfunctional-requirements.md` § Direction, amended 2026-09-30). The Pi's card
> holds no irreplaceable asset: the Player's cache and device state are both
> rebuildable, and the heartbeat is an HTTP POST that writes nothing to the card.

*The trade-off, stated plainly.* Card death costs a rebuild plus whatever curation
happened since the last backup, at an accepted frequency of once every few years.
**That makes the backup and restore path the entire mitigation for this risk rather
than a complement to it** — and it is not built. Until issue #14 lands, this risk is
*decided* rather than *closed*: nothing on the Pi today would survive the card. The
storage medium is no longer the open question; the backup is.

**The journal is bounded explicitly, for a narrower reason than this section once
gave.** Structured logging is the product's primary observability signal and both
planes log continuously to it. `arrt-player:deploy/journald.conf.d/10-bound-the-journal.conf`
sets **256M** with 32M segments, on **both** ceilings — `SystemMaxUse=` for a
persistent journal and `RuntimeMaxUse=` for the volatile one this machine actually
uses — so the file is correct whichever storage mode is in force.

> **Corrected twice on 2026-08-04, and the second correction reverses the first's
> premise.** This paragraph originally said the default "sizes itself as a fraction
> of the filesystem — so it grows with the disk you were trying to protect."
> Neither half survived contact with the machine: systemd caps its persistent
> default at 4G, and this journal is not on the filesystem at all. Two things
> follow.
>
> **The bound protects nothing about the card**, per the correction above. What it
> buys is a ceiling that is *chosen and visible* rather than inherited from
> defaulting rules a reviewer would have to know.
>
> **On this machine it is a raise, not a cap.** The runtime default was 156.1M of
> RAM; 256M is more. That is affordable on 8 GB and is the intent — but it is the
> opposite of what "bound the journal" suggests, so it is said plainly rather than
> left in the arithmetic. 256M was chosen against a measurement: 9.2 MB after first
> boot and a full provisioning run, so it is weeks of history at that rate.

**What volatile storage costs is diagnosis, and the operator decided 2026-08-04 to
accept that cost: the journal stays volatile.** It does not survive a reboot, so
"the wall froze and the Pi restarted" is precisely the case `journalctl` cannot
answer — and it is the case an operator is most likely to be investigating.
`Storage=persistent` would fix that and would move logging onto the card, making
the journal a wear path for the first time; it was declined. **Two consequences to
carry rather than rediscover.** Post-reboot diagnosis has to come from somewhere
other than the journal — the health surface's heartbeat age, or the catalogue —
which is a constraint on how failures are made visible, not merely a missing
convenience. And the top operational risk keeps its narrowest form: nothing this
product does writes continuously to the card except the display heartbeat. **That
writer is built and has been running unattended since the 2026-08-11 cutover**,
writing into `/srv/art` on the Pi — so this risk is live rather than pending, and
the wear path it names is the one currently in use.

The pre-acquisition free-space guard is unrelated to any of this: it is
curation-side and checks before a fetch.

**Second risk: vendor removal of the TV art-mode API — the auto-update question is
answered.** Samsung has already removed art mode from some units via firmware
(1710, Sept 2025). The capability the entire product rests on is controlled by a
vendor who has withdrawn it before.

**Firmware auto-update can be disabled on this television, and was disabled
2026-08-04.** The set is held at firmware **1310**; **1400** is offered and has not
been taken. Two consequences worth stating:

- **The risk is now a decision rather than an exposure.** Nothing arrives
  overnight; taking 1400 is a deliberate act.
- **Updating is effectively one-way** — there is no rollback — so the standing
  recommendation is to stay on 1310 unless a release note shows 1400 fixes
  something wanted. Staying costs nothing known and keeps the set on behaviour that
  has been *measured*; every figure in
  `arrt-player:.prawduct/artifacts/platform-and-dependency-findings.md` § The television was taken against 1310.
  The counter-argument, security patching, is weak for a LAN device behind NAT on a
  network `security-model.md` already treats as the trust boundary.
- **What makes this recoverable in knowledge, if not in firmware**, is
  `tv_api_check.py`: re-run it after any future update and it reports what moved.
  That is the defence against vendor change — not compatibility branching, which
  could not be tested here against a second set anyway.

**Third risk: the norms with no mechanical enforcement.** *(Re-scoped 2026-07-27.
This read "no test suite exists — zero tests across 2,216 lines"; that departure was
closed the same day and both planes now have suites, so the risk is no longer
absence of testing but the specific norms nothing yet checks.)* The **plane-isolation
test** that enforces a ratified Direction norm was built on 2026-08-06 with the
display plane's first modules (issue #7) — imports resolved transitively, HTTP-client
construction banned with the television websocket exempted, and planted violations
proving both halves can fail. What remains uncovered is the **service-layer norm**,
whose enforcement column says "Critic" — a reviewer reading handlers, with no test
that fails when logic creeps into a binding.
