---
artifact: build-plan
version: 1
scope: wave-4d-compositing
branch: feature/wave-4d-compositing
partition: serial — 02 builds on 01's compositor and geometry, and 03 changes the requested majors only once 02 has the wall composing; 02 and 03 both edit the drivers and `wall.py`
depends_on:
  - artifact: re-architecture
  - artifact: feeds-and-players
  - artifact: player-contract
  - artifact: nonfunctional-requirements
governed_by:
  - artifact: player-contract
    dispositions:
      - "§ Layout (mat width by inch rule or 6% of the shorter side, the box, the three mat modes, one pixel of tolerance) → conforms: 01 runs every `contract/vectors/mat-geometry.json` vector, all three modes, with and without a density, from the Player's suite"
      - "§ Presentation settings (a Player applies what its display can honour and ignores the rest; a setting is never a reason to refuse) → conforms: 02 applies `settings.mat.mode` and ignores label, overlay, fade, text scale, viewing distance and facts, which nothing on this Player draws yet"
      - "§ Staging (the Player fetches and composes staged works ahead) → conforms: 02 composes staged works with the rest; nothing staged is shown"
      - "§ The cutover (a Player requests the highest major it reads; a heartbeat with no capabilities counts as [1]) → conforms: 03 changes the requested majors to (2, 1) and the Frame starts writing capabilities, so both walls report [2, 1]; the note that a Frame asks only for major 1 'until the Player owns its geometry' is amended in 03 to say that has happened"
      - "§ The heartbeat, minor 2 (`label_modes` are the modes of text on the display itself) → conforms: both drivers keep reporting ['none'], because the caption in the mat is wave 6+ (below)"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ The mat is geometric (work-shaped mat, black beyond, bottom weighted, no upscaling) → conforms: 01 ports the server's drawing rule, and the vectors that hold the server to it hold the Player"
      - "§ Performance, composing on the Player ≤ 5 s and ≤ 1 GB per composition on a Pi 4, once per work and geometry, ahead of the slot → conforms: 02 composes off the loop in a thread, once per (master, colour, mode, geometry), and caches the result; a work whose composition is not ready yet is skipped for that pass, as an uncached one is"
      - "§ The television belongs to whoever is using it → conforms: nothing here touches the art-mode gate or power; the Frame driver uploads a composed file where it uploaded a render"
      - "§ Availability, the wall never goes black over one missing work → conforms: a work that cannot be composed (unreadable master, full disk) is skipped and said once, like a missing render"
  - artifact: feeds-and-players
    dispositions:
      - "ruling 2, rendering is the client's → conforms: this plan is that move for the mat"
      - "ruling 7, the mat's width is the client's; MAT_* moves into the Player's configuration beside the panel's geometry → conforms: 01 adds the Frame's geometry and mat width to the Player's configuration under the same key names; the server's copies stay until 4g removes them"
  - artifact: accessibility-spec
    dispositions:
      - "§ Nothing may reason about a panel's geometry anywhere but on that panel → conforms: this plan moves the Frame's geometry onto the device that drives it"
      - "Direction norm 1 and the caption-in-the-mat rules (floor, tiers, fill) → inapplicable because no caption is drawn in 4d; the caption in the mat is wave 6+"
  - artifact: re-architecture
    dispositions:
      - "§ Compositing moves to the Player (the Player composes, the Library keeps the original, colour and label; the Player composes and does not judge) → conforms: no adequacy judgement here; Programming's per-wall judgement is 4e"
      - "§ Order of work, wave 4 row (4d compositing; 4g the removals) → conforms: the server's compositor, `tv_display`, `TV_PANEL_*` and `MAT_*` stay, because walls pull major 1 renders until 4e publishes major 2 and 4g cuts over"
  - artifact: data-model
    dispositions:
      - "derived artifacts are regenerated, never transported (in-transition) → conforms for major 2: the composed picture is derived on the Player from the master and never leaves it; major 1's composed render is still transported until 4g"
  - artifact: architecture
    dispositions:
      - "the plane isolation rules (no HTTP client outside `pull.py`; the Player knows a screen only through its configuration and its drivers) → conforms: the compositor reads files and configuration only; `test_plane_isolation.py` is unchanged"
last_validated: null
---

# Build Plan — Wave 4d: compositing moves to the Player

## What this plan is

The fourth of wave 4's seven plans (`re-architecture.md` § Order of work,
row 4). Wave 4c gave the Player one wall loop and a reader for majors 1 and 2,
but it still asks only for major 1. A major 2 work arrives as an unmatted
presentation master of up to 7,680 px, and nothing on the Player can draw a
mat around it yet. This plan adds that compositor. It gives the Player the
Frame's geometry, which the server held until now. Then it asks for major 2.

4d ends with a Player that composes every major 2 work for its own screen,
asks for `v2` first, and falls back to `v1`. Until 4e builds the server's major
2 feed, `v2` answers 404 and the walls run major 1 exactly as today. Major 1's
composed render is still shown as it arrives and is never matted again.

**Not in this plan:**
- The server's removals (`tv_display`, `TV_PANEL_*`, `MAT_*`, its compositor):
  4g. Walls pull major 1 renders until the cutover.
- Per-wall adequacy and wall settings: 4e.
- Scenes as a curator feature: 4f.
- **The caption in the mat**, descoped from what 4c's handoff expected:
  `re-architecture.md` § Order of work puts it in wave 6+ ("Player: ... caption
  in the mat"), `clients.md` § Out of scope says the same, and the label and
  overlay layout has no vectors yet (`player-contract.md` § Layout). So both
  drivers keep `label_modes` at `["none"]`, and `settings.label.mode` is
  ignored as a setting this display cannot honour.

## Goals

**Response taken:** build. The owner, 2026-10-09: "yes let's get 4d". The scope
is the wave 4 row's 4d, and the 4c handoff's inherited items.

**Product:** the walls show works from the presentation master, matted for
the screen in front of the viewer, rather than a 3840×2160 canvas fitted to
whatever screen it lands on. This is what lets a 1920×1200 screen or a 1080p
Frame show a correctly proportioned mat, and it is the precondition for 4e
publishing major 2 at all.

**Architecture:** one compositor in the Player, held to the contract's
vectors. Geometry belongs to the driver: the Frame's comes from configuration
with a pixel density, and a screen's comes from the connector's mode with
none. Composing is a preparation cost and never a wait in the loop.

**Constraints:**
- The vectors are the definition (`contract/vectors/mat-geometry.json`).
- The composing budget is ≤ 5 s and ≤ 1 GB on a Pi 4
  (`nonfunctional-requirements.md` § Performance).
- Major 1 behaviour is unchanged, because the wall runs on it until 4e.

**Tradeoffs accepted:**
- Two compositors exist until 4g, the server's for major 1 and the Player's
  for major 2, both held to the same vectors. Deleting the server's is 4g's
  job.
- The Frame's geometry is now configured twice: once on the server
  (`TV_PANEL_*`, for major 1) and once on the Player (for major 2). That
  lasts until 4g.

**Level:** Medium. The geometry is fixed by vectors, and the drawing rule is a
port of code already run on the wall. The uncertainty is in where composing
sits in the loop: the Frame uploads across ticks, a screen draws in one call,
and a 3 s compose must happen in neither.
*What would raise it:* 02 begins by listing, for each driver, the pass on which
a work is composed, uploaded or drawn, and shown, before any code moves.

**Open assumptions** (each inferred by the builder, not ruled by the owner):
- *Inferred:* when no layer sets `mat.mode`, the Player's default is
  `proportional`, which is what every wall has shown since wave 2. [LOW impact |
  user can override]
- *Inferred:* a work whose `mat_color` is unreadable (the 4c decision left this
  to the compositor) is composed as `none`, the work on black. Inventing a
  colour would show a mat the Library never chose. [LOW impact | user can
  override]
- *Inferred:* the Player reads the Frame's geometry under the server's own key
  names: `TV_PANEL_WIDTH_PX`, `TV_PANEL_HEIGHT_PX`, `TV_PANEL_DIAGONAL_INCHES`,
  `MAT_WIDTH_INCHES` and `MAT_BOTTOM_WEIGHT`, with the server's defaults. The two
  read different `.env` files on different hosts, so the names cannot collide.
  `.env.example`'s header already says `TV_PANEL_*` "becomes player
  configuration" in wave 4. Reusing the names means the key the operator
  already knows moves with its meaning, and 4g deletes the server's copy
  without renaming anything. The `.env.example` header's line saying `MAT_*`
  "becomes a wall setting on the server" is corrected here: ruling 7 made the
  mat's width the client's. The operator sets the real diagonal in their
  deployment, which this public repo does not carry. [MED impact: a wrong
  diagonal draws a wrong mat width | user can override]
- *Inferred:* a screen without a density takes the bottom weight from
  `MAT_BOTTOM_WEIGHT` too, so the conservator's rule holds on every display.
  [LOW impact | user can override]
- *Inferred:* the composed file is named by a key over everything that moves
  a pixel: the master's sha256, the colour, the mode, the screen size, the
  margins and a drawing-rule version. A changed geometry therefore recomposes,
  and the Frame's binding, which keys on path and fingerprint, uploads the
  new picture. Composed files are evicted when no work the feed names produces
  their key. [LOW impact | user can override]

**Decisions made mid-build:**
- 01: the relative mat width is a constant in `compose.py` held to the vector
  file by a test, not read from `contract/` at run time. A Player must run with
  no checkout of the contract beside it, which it will once the repos split
  (settled by the Architecture goal; the plan's wording said "read from").
- 01: the drawing sizes the work to `layout`'s rectangle exactly, rather than
  letting `thumbnail` choose a size. One answer to where the work goes, which
  the Architecture goal asks for, and no off-by-one between the geometry and
  the picture.
- 01: the mat settings are the client's (`ClientSettings`, copied to every
  wall), not the Frame's, because a screen composes with the bottom weight too.
  The panel geometry is the Frame's. (Settled by ruling 7.)
- 01: `test_config.py`'s guard that "the plane holds no fact about the
  television's physical size" is replaced by its opposite: the Frame's geometry
  and the mat are read and named in the startup line. Ruling 7 reversed the
  rule that test encoded; the new test pins the obligation that replaced it
  (`operational-spec.md`: each plane logs its own panel geometry at startup).
- 02: composed files are evicted by the schedule programme (`_tidy`), not by
  the pull as the plan said. Only the schedule knows the composition keys
  (feed × geometry), and a screen's mode change owes a tidy that the pull
  never sees. The tidy runs between compositions, so it never takes a file
  being written, and it also removes a `.composing` file a killed process
  left (Chunk 01 review observation 2).
- 02: the geometry reaches the schedule as a callable from the wall's builder,
  not as a new `Display` method. A screen's mode is asked on every pass, and
  the `Display` protocol stays as 4c left it.
- 02: a switch of major calls `Programme.entered()` before the adoption. The
  schedule forgets the picture it last put up. The rotation treats the switch
  as a restart: it re-selects the work on the wall in its own form, at once,
  rather than at its next interval (the 4c cumulative review's O-1, which
  named "the rotation's equivalent"). `test_majors.py`'s switch-back test
  changed accordingly: major 1 takes the wall on the switching pass, not 60 s
  later. *Inferred, not settled by the goals:* showing major 1's own render at
  once was preferred over leaving major 2's picture of another work up for an
  interval, because the switch means major 2 is gone.
- 02: `Schedule.settle()` is public, for a caller that must see compositions
  finished (the tests), as `Wall.tick` is public for the tests. The loop
  never calls it.
- 02, the passes on which a work is composed, uploaded and shown (the step
  Level said would raise confidence, written after the review asked for it):
  *Frame* — the pass that adopts a feed lists every work's composed path in
  `pictures`; `prepare` uploads only files that exist, so it uploads nothing
  yet; `step` starts the target's composition and passes it over. A later
  pass finds the composition finished, `prepare` uploads it (one upload per
  pass, as for a major 1 render), and `step` selects it. *Screen* — no
  upload: the pass whose `step` finds the composition finished draws it.
  The rest of the feed is composed one work per pass in between.
- 02: the tidy keeps the picture on the wall until another replaces it, and
  the replaced one is removed when the new one is shown (Chunk 02 review,
  blocking: a screen redraws its picture on a mode change, and in a gap
  nothing replaces it). The tidy passes over directories, and a composed
  directory it cannot read or empty is said once and costs nothing else.
- 02: one name for a composed file, `compose.composed_path`, used by both
  `compose` and the schedule (Chunk 02 review), so the two cannot drift.
- 03: the pull asks for a higher major about once a minute while it is served
  a lower one (`HIGHER_MAJOR_SECONDS`), and at once if that major stops
  answering. The contract allows this ("may"); the plan did not ask for it.
  At a one-second poll, asking `v2` each time doubles every wall's requests
  and logs a 404 a second until 4e publishes major 2 (settled by the
  Constraints goal: major 1 behaviour unchanged, which includes its load on
  the server).
- 03: `test_pull.py`'s `two_major_pull` fixture no longer patches
  `REQUESTED_MAJORS`. The constant it stood in for is now real, so the
  fallback tests run against what ships.
- 02: `settle()` composes each file at most once per call. A sweep mutation
  that left a composed work owed made it loop for hours rather than fail; a
  test helper that can hang reads as a slow suite, not a finding.
- 02: `_collect` has no branch for a cancelled task. A composition is
  cancelled only when the wall shuts down, and no pass follows that, so the
  branch was unreachable; the sweep showed nothing could test it, and it was
  deleted rather than kept as a guard nobody defends.
- 02: the major 2 tests that asserted the master reached the display now
  assert the composition does, from real JPEG masters. That is the behaviour
  this chunk exists to change, not a weakened test; each still names the same
  file it did, by the key the schedule names it.

## Status

- [x] Chunk 01: The compositor and the Player's geometry
- [x] Chunk 02: The wall composes major 2 works
- [ ] Chunk 03: Ask for major 2

Context: branched from develop after #335 (wave 4c). A second session builds
the server's Ask work (`feature/ask-agent`), then 4e and 4g. This plan touches
nothing under `arrt/`.

### Chunk 01: The compositor and the Player's geometry

- **Critic mode:** final. This is the keystone 02 composes with, and its
  geometry decides every pixel of the mat.
- **Surfaces:** new `arrt-player/src/arrt_player/compose.py` (the geometry, a
  pure function returning the work's and the mat's rectangles from a screen,
  an optional density, a mode, the work's size, a mat width and a bottom
  weight; and the drawing, which writes a composed JPEG atomically, named by its
  key); `config.py` (the Frame's geometry and the mat settings, read only for a
  Frame wall); new `arrt-player/tests/test_compose.py`; `.env.example` (its
  header's wave 4 note, and the panel and mat keys marked as read by the
  Player too).
- **What:**
  - Port the server's drawing rule (`arrt/src/arrt/library/acquisition/compose.py`):
    the work is fitted into the box and never enlarged, upright, in RGB,
    LANCZOS; a work-shaped mat; black beyond.
  - Add the two modes the server never drew: `full` (mat colour to every
    edge) and `none` (the work fitted on black, the box being the whole
    screen).
  - Take the mat width from inches times the density when one is known, and
    otherwise from `relative_width` times the shorter side. The constant lives
    in the Player's code, and a test holds it to the vector file's own
    `relative_width`, so the two cannot drift.
  - An unreadable colour composes as `none` (assumption above).
  - Decode with `draft` to the screen's size, as the server does. The
    measured budget assumed that.
- **Tests:**
  - Every `mat-geometry.json` vector through the geometry, to within the
    contract's one pixel. The test is parametrised over the file, so a vector
    added later is run.
  - It is watched failing once against a deliberately wrong margin.
  - The drawing tested on small synthetic masters: pixels sampled inside the
    work, in the mat, and beyond it for each mode; a small work not enlarged;
    an EXIF-rotated master upright; a CMYK master composed.
  - A failed write leaves no partial file and no previous file harmed.
  - The key changes when each of its inputs changes, and only then.
  - Configuration: defaults, overrides, and a non-positive value refused by
    name.
  - A mutation sweep over `compose.py`.
- **Not:** no driver or programme calls this yet.

### Chunk 02: The wall composes major 2 works

- **Critic mode:** final. It changes what the Frame driver uploads and what a
  screen draws.
- **Surfaces:** `arrt-player/src/arrt_player/programmes/schedule.py` (a work's
  picture becomes its composed file); `arrt-player/src/arrt_player/programmes/memory.py`
  (its docstring); `arrt-player/src/arrt_player/wall.py` (`Picture`, if it needs the
  master's dimensions); both drivers (each says its geometry: the
  Frame from configuration with a density, a screen from its connector's mode
  without one); `pull.py` (evict composed files with the media); `kms.py`
  (`fitted` already passes a picture of the screen's own size through, which
  a test pins); `arrt-player/tests/test_schedule*.py`, `test_wall.py`, and the
  driver tests.
- **What:**
  - When a major 2 feed is adopted, the schedule programme composes each work
    it can show, scheduled, scene or staged, for the driver's geometry and
    the feed's `settings.mat.mode`.
  - Composing runs in a thread, off the loop, one work at a time, and is
    skipped when the composed file already exists.
  - A work whose composition is not ready is skipped for the pass, as a work
    whose media is not cached is today.
  - A work that cannot be composed is said once per feed and skipped.
  - When a screen's mode changes, its works recompose, because the geometry is
    in the key.
  - Major 1's renders are handed to the driver as they arrive, never matted
    again. A test pins that a major 1 render reaches the driver byte for byte.
  - **The 4c carry-over:** clear `Schedule._shown_path` (and the rotation's
    equivalent) when the wall switches majors (4c cumulative review O-1). A
    test switches 2 → 1 → 2 and sees the work shown again. Fix the `Memory`
    docstring in `arrt-player/src/arrt_player/programmes/memory.py` in the same commit (O-3).
- **Tests:**
  - Against each driver's double: a major 2 feed shown as composed pictures
    at that driver's geometry. On the Frame, its configured size; on a screen,
    its connector's mode.
  - The Frame uploads the composed file and binds it.
  - A slow compose does not delay the loop: a double compositor that blocks
    until released, while the wall keeps passing.
  - Staged works composed and not shown.
  - Eviction of composed files whose work the feed no longer names.
  - The major switch above.
  - A mutation sweep over the changed lines.

### Chunk 03: Ask for major 2

- **Type:** cumulative-final
- **Surfaces:** `arrt-player/src/arrt_player/manifest.py` (`REQUESTED_MAJORS` becomes `(2, 1)`, and its
  comment says why now); `arrt-player/src/arrt_player/displays/frame.py` (`capabilities()` reports the
  configured screen); `arrt-player/src/arrt_player/wall.py` (`_capabilities`, if the Frame-is-silent
  branch retires); `.prawduct/artifacts/player-contract.md` § The cutover (the note that a Frame
  asks only for major 1 until the Player owns its geometry); `arrt-player/tests/test_pull.py`,
  `test_heartbeat*.py`, `test_majors.py`; `.prawduct/operator-verification.md`; `arrt-player/src/arrt_player/pull.py` (asking for a higher major less often than it polls).
- **What:**
  - The pull asks for `v2` first and falls back to `v1` on 404 (built in 4c).
  - The heartbeat's `manifest_majors` is `[2, 1]`, for both drivers.
  - The Frame now writes `capabilities`, with its configured size, `frame` and
    `["none"]`.
- **Tests:**
  - Against `server_double.py`: a wall served only `v1` runs major 1 as
    before; a wall served `v2` shows composed works.
  - Every written heartbeat validates against `heartbeat.v1.schema.json`, for
    each driver, with `manifest_majors` `[2, 1]`.
  - The existing test holding the pull's majors and the heartbeat's to one
    constant still passes.
- **Operator verification:** one run on the Pi against the real server.
  - Both walls still rotate on major 1, because `v2` is 404 until 4e.
  - The heartbeat reports `[2, 1]` and the Frame's size.
  - The real major 2 walk at the wall waits for 4e, and the entry says so.

**Done when (whole plan):**
- All three suites, lint and format are green (the display leg with
  `--group raster`).
- `/prawduct:critic cumulative` over the branch finds nothing blocking.
- The change-log entry for `wave-4d-compositing` is written.
- The operator-verification entry is queued.
- One PR to `develop`.
