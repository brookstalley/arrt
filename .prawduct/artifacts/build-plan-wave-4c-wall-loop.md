---
artifact: build-plan
version: 1
scope: wave-4c-wall-loop
branch: feature/wave-4c-wall-loop
partition: serial — 02 and 03 both build on 01's seam (the wall loop and the driver protocol), and 02 and 03 both edit `pull.py` and `heartbeat.py`
depends_on:
  - artifact: re-architecture
  - artifact: feeds-and-players
  - artifact: player-contract
  - artifact: labels-and-surfaces
governed_by:
  - artifact: feeds-and-players
    dispositions:
      - "§ Repository shape after wave 5, the two wall loops become one wall loop, a display driver per kind, and a label renderer → conforms: 01 builds the loop and the two drivers; the label renderer has already been split out (`label_renderer.py`; the Frame's loop 'draws no label'), so 4c has nothing to add there"
      - "the split is done 'when rotation leaves the Player, rather than before it, so the code about to be deleted is not refactored first' → conforms: 01 moves major 1's rotation and directive behind the programme seam unchanged rather than rewriting them, and 4g deletes them whole"
      - "ruling 3, the Player core consumes only a feed → conforms: 02's major 2 programme reads only feed keys plus `scene`, which reaches the Player as a republished feed"
      - "ruling 1 and 9, displays configured explicitly on the client's host → conforms: no driver discovers anything; the Frame driver keeps `TV_ADDRESS`"
      - "ruling 2, rendering is the client's → inapplicable because composing is 4d; 4c hands each driver a picture file and does not draw a mat"
  - artifact: player-contract
    dispositions:
      - "§ The cutover, a Player requests the highest major it reads and falls back on 404, misconfigured only when every major answers 404 → conforms: 03"
      - "§ The cutover, Arrt Player's suite pins the refusal of every major 2 fixture → amendment proposed: that sentence describes a major 1 reader, and 02 makes this reader one of majors 1 and 2. The test is rewritten in the same commit to pin the contract's real rule — valid major 2 adopted whole, invalid major 2 refused, an unknown major refused as a version — and § The cutover is amended to say what the suite pins from 4c on (recorded as a decision below)"
      - "§ Rules a schema cannot state, a malformed document is refused and the last good one kept → conforms: 02's reader runs the schema and the five semantic rules before adopting"
      - "§ Time (half-open spans, replay by whole horizons, gaps keep the last work until power control, a scene never moved) → conforms: 02 runs `contract/vectors/schedule.json` from the Player's suite"
      - "§ The heartbeat, minor 2, capabilities and scene_id → conforms: 03 writes them"
  - artifact: architecture
    dispositions:
      - "the manifest and content-addressed media are the only channel, and the Player makes only the requests `contract/routes.json` names → conforms: 03 moves the manifest request from `manifest` to `manifest_major`, which `routes.json` already names; `test_plane_isolation.py` holds `pull.py` to that file"
      - "every failure keeps the cache → conforms: 02 caches major 2 media under the same rule as major 1 renders (a mismatched or missing media is left out, the rest of the wall goes on)"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ The television belongs to whoever is using it (no change while the set is not in art mode; no power key) → conforms: the art-mode gate moves into the Frame driver unchanged, and 01's tests that pin it (`test_availability.py`, `test_selection_observers.py`) pass with their assertions untouched"
      - "§ Availability, the wall never goes black over one missing work → conforms: both programmes skip what cannot be shown"
  - artifact: data-model
    dispositions:
      - "per-device runtime state never lives in the catalogue → conforms: the Frame's bindings and its resume state stay in the Player's own store (`state/store.py`), now reached through the Frame driver"
      - "derived artifacts are regenerated, never transported (in-transition) → inapplicable because 4c changes no rendition; major 1's composed render is still transported until 4g, and 02 caches the untransformed presentation master"
last_validated: null
---

# Build Plan — Wave 4c: one wall loop, a driver per display, a reader for majors 1 and 2

## What this plan is

The third of wave 4's seven plans (`re-architecture.md` § Order of work, row
4). The Pi Player runs two wall loops that duplicate the wall logic: the
Frame's (`daemon.py`, 1,261 lines) and the HDMI screen's (`screen.py`). Both
adopt a manifest, act on a directive, rotate, advance, show and beat, and they
already disagree in small ways (the Frame keeps its directive baseline and its
place on disk, the screen keeps them in memory). `feeds-and-players.md` § Repository
shape after wave 5 asks for one wall loop and a driver per kind of display
before the repository split. Major 2 is the reason to do it now: the schedule
replaces rotation and the directive, and writing a major 2 reader twice, once
per loop, is the duplication this removes.

4c ends with a Player that reads major 2 correctly and is tested against the
contract's vectors, but **does not yet ask for it**. Showing a major 2 work
needs a composed picture (a mat around the presentation master), and composing
is 4d. So the majors the Player requests and reports stay `[1]` until 4d adds
the compositor and changes them to `[2, 1]` (recorded as a decision below).

**Not in this plan:** composing (4d); anything on the server (4e builds the
major 2 feed; until then `v2` answers 404); the removals (4g); scenes as a
curator feature (4f). The major 2 reader does honour `scene` and `staging`,
because they are keys of the document it must read.

## Requirements Confidence

**Level:** Medium

**Why:** The behaviour is fixed by the contract and its vectors, and the
refactor is behaviour-preserving with a large suite behind it. The uncertainty
is in the seam: where the line between "the wall" and "the display" falls for
the Frame, whose loop interleaves the set's state (art mode, bindings,
uploads, announcements, brightness) with rotation.

**Open assumptions / unknowns:**
- [ASSUMPTION: the seam is a `Programme` (what should be on the wall now: major 1's rotation and directive, or major 2's schedule and scene) and a `Display` driver (put a picture on this screen, say what the screen is doing, report capabilities). The wall loop owns the heartbeat, the display-state record and the "say it once" episodes; the Frame driver owns art mode, bindings, uploads, reconciliation, brightness and the set's announcements | MED impact | user can override]
- [ASSUMPTION: major 1's resume and directive-baseline rules stay as each display has them today — persisted for the Frame, because the set holds the picture across restarts, and in memory for a screen, which is black after one. The major 1 programme takes an optional store, and the Frame driver's construction passes it. Unifying them is not worth touching code 4g deletes | LOW impact | user can override]
- [ASSUMPTION: in a schedule gap, a major 2 wall keeps the last work it showed (`player-contract.md` § Time: the Player cannot yet act on dark), and reports `showing_art` for it, not `dark` | MED impact | user can override]
- [ASSUMPTION: `label_modes` reports `["none"]` for both drivers in 4c. A display that can composite reports `caption` (`labels-and-surfaces.md` § The model), and nothing composites until 4d | LOW impact | user can override]
- [ASSUMPTION: `capabilities.backend` is `frame` for the Frame and `framebuffer` for an HDMI connector, the two values the schema names | LOW impact | user can override]

**What would raise confidence:** 01's protocol written first and the Frame
driver's methods listed against `Daemon.tick`'s current order of operations,
step by step, before any code moves.

`[DECISION: the Player reads major 2 from 4c but requests and reports only major 1 until 4d | a Player that asked for v2 before it could compose would show a 7,680-px master with no mat on an HDMI screen and upload one to a Frame, and the order 4d-before-4e guarantees nothing only while every deploy follows it; holding the requested set at [1] makes the order a property of the code. The cost is that 4c's v2 path runs only in the suite, and 03's fallback runs live only as v1 | the builder's, 2026-10-09; user can veto]`

`[DECISION: the Player suite's pin "every major 2 fixture is refused" becomes "valid major 2 fixtures are adopted whole, invalid ones refused, an unknown major refused as a version", and player-contract.md § The cutover is amended to match | the sentence describes a major 1 reader, which this Player stops being; keeping it would forbid the reader the program exists to build. The rule it protected — a reader refuses a major it cannot read and keeps its wall — is kept and pinned with major 3 | the builder's, 2026-10-09; user can veto]`

`[DECISION: where the two loops disagreed and only the Frame's tests pinned a version, the screen takes the Frame's: an empty wall retries as soon as a new manifest lands, a directive that shows nothing does not restamp the rotation timer, the baseline is said in the journal, and a crash is logged as one. Where each loop's tests pinned its own version (the missing-render report; where the rotation's memory lives) the difference survives as a parameter of the programme | the Frame's rules were each written against a failure seen on the wall, and the screen's versions were the absence of that work, not a choice; settling them costs nothing a screen test held, and a second set of rules in code 4g deletes buys nothing | the builder's, 2026-10-09, surfaced by Chunk 01's review; user can veto]`

## Status

- [x] Chunk 01: One wall loop, a Frame driver and a screen driver
- [ ] Chunk 02: The major 2 reader and its schedule
- [ ] Chunk 03: Per-major requests and the heartbeat's capabilities

Context: branched from develop after #334 (wave 4b). Chunk 01 committed as
49269c52 after a `final` review with no blocking finding; its observations
O-1, O-7, O-8 and O-9 (the screen's changed rules said nowhere, two log lines
naming no wall) are fixed in the commit after it, which Chunk 02's review
covers; O-2 to O-6 are accepted on the record. O-5's acceptance owes Chunk 02 a
test that the schedule programme asks `may_attempt` and `is_ours` before it
shows anything.

### Chunk 01: One wall loop, a Frame driver and a screen driver

- **Critic mode:** final — the keystone 02 and 03 build on, and a refactor of
  the code that drives the television.
- **Surfaces:** new `arrt-player/src/arrt_player/wall.py` (the loop, the
  `Programme` and `Display` protocols); new
  `arrt-player/src/arrt_player/displays/` (the Frame driver from `daemon.py`,
  the screen driver from `screen.py` over `kms.KmsOutput`); new
  `arrt-player/src/arrt_player/programmes/` (major 1's rotation and directive);
  `__main__.py` (`run_frame_wall`, `run_screen_wall` build one loop each);
  `daemon.py` and `screen.py` emptied and removed. The tests that construct
  `Daemon(` or `ScreenWall(` (12 call sites in six files: `conftest.py`, `test_pull.py`, `test_directives.py`, `test_screen.py`, `test_rotation.py`, `test_main.py`) are changed at construction only.
- **What:** one loop that, each pass: polls the watcher and hands a new
  manifest to the programme; asks the programme what to show; asks the driver
  to show it; observes the display's state; beats. Major 1's programme is
  today's rotation and directive, moved, with each display's current resume
  rule (assumption above). The Frame driver keeps every behaviour the Frame's
  loop's docstring names: uploads spread across ticks, the art-mode gate, the
  wall-unchanged backoff, reconciliation owed until done, the set's
  announcements, brightness, closing the art channel on every way out. Where the
  two loops disagree today (the screen re-shows its place in memory, the Frame on
  disk), the disagreement survives and is named in the code, not resolved.
- **Tests:** every existing Player test passes with its assertions untouched.
  The diff to each test file is construction only, and the commit message
  lists the files to make that checkable. A mutation sweep over `wall.py` and
  the two drivers, read as `docs/testing.md` says, catches what the old suite
  caught over `daemon.py` and `screen.py`. New: one test per driver that runs
  the shared loop through a full rotation against its double, so the loop is
  shown to be shared rather than only the code.

### Chunk 02: The major 2 reader and its schedule

- **Surfaces:** `manifest.py` (parse by major; major 2 into a `Feed`);
  new `arrt-player/src/arrt_player/programmes/schedule.py` (what to show at an
  instant: scene, then slot by replay, then gap); `pull.py` (cache major 2's
  media named by `works`, scene and staging, and evict what none names);
  `tests/test_player_contract.py`; a new test running
  `contract/vectors/schedule.json`; `player-contract.md` § The cutover.
- **What:** the watcher adopts a valid major 2 document whole and refuses an
  invalid one, keeping the last good one, by the schema and the five rules
  `player-contract.md` § Rules a schema cannot state lists. The rules are
  checked in the Player's own code, not by importing the root suite's
  `semantic_errors`. Major 2's programme answers each pass with the scene's
  work while a scene is active, else the slot's work after moving the instant
  into the horizon by whole horizons, else (a gap) the last work shown. It
  reports `scene_id`. A work whose media is not in the cache is skipped, as a
  missing render is under major 1. The driver is handed the presentation
  master's path; composing it is 4d. Staged works are fetched and never shown.
- **Tests:** every `schedule.json` vector run through the Player's programme,
  watched failing once on a deliberately wrong vector. Every valid major 2
  fixture adopted whole and every invalid one refused, each for the rule its
  name gives. A major 3 document refused as a version. The pull caches a major
  2 feed's media and leaves out one whose bytes do not match its hash, against
  `server_double.py`. A switch from a major 1 manifest to a major 2 one (and
  back) changes the programme without restarting the wall.

### Chunk 03: Per-major requests and the heartbeat's capabilities

- **Type:** cumulative-final
- **Surfaces:** `pull.py` (`manifest_major`; the `MANIFEST_ROUTE` constant
  retires); `heartbeat.py` (minor 2 `capabilities` and `scene_id`); both
  drivers (their capabilities); `tests/test_pull.py`, `tests/test_heartbeat.py`,
  `tests/test_player_contract.py`; `server_double.py` (serves `v{major}`);
  `player-contract.md` § Transport, where it names the unversioned route.
- **What:** the pull asks for each major the Player requests, highest first
  (`[1]` until 4d), takes the first that answers, and calls the wall
  misconfigured only when every one answers 404. It may keep the major that
  last answered and ask for a higher one less often than it polls. The
  heartbeat carries `capabilities`: `screen` from the driver (reported again
  when it changes), `backend`, `label_modes`, and `manifest_majors` (the same
  constant the pull requests from), plus `scene_id` from the programme.
- **Tests:** against `server_double.py`: v2 404 then v1 answers, so the wall is
  served v1; every major 404, so the wall is misconfigured; a token refused on
  the first major stops there and does not fall back. The written heartbeat
  validates against `heartbeat.v1.schema.json` with capabilities, for each
  driver. `manifest_majors` and the pull's requested majors read one constant,
  and a test fails if they differ.

**Done when (whole plan):** all three suites, lint and format green (the
display leg with `--group raster`); `/prawduct:critic cumulative` over the
branch with no blocking finding; the change-log entry for `wave-4c-wall-loop`
written; one run of the Player against the real server on the Pi (by the
operator, queued in `operator-verification.md`) showing the Frame and the HDMI
wall rotating as before.
