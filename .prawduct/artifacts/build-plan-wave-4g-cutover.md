---
artifact: build-plan
version: 1
scope: wave-4g-cutover
branch: feature/wave-4g-cutover
partition: 01 serial (the contract both planes build to). Then 04 delegated to one agent in an isolated worktree on its own branch (`arrt-player/` only, plus its own tests), beside 02 and 03, which the coordinator builds serially in this worktree (`arrt/` only; 03 edits `readiness.py`, `container.py` and the test fixtures 02 also edits). The coordinator merges 04, then builds 05 and runs every review
depends_on:
  - artifact: re-architecture
  - artifact: feeds-and-players
  - artifact: player-contract
  - artifact: architecture
  - artifact: data-model
governed_by:
  - artifact: player-contract
    dispositions:
      - "§ The cutover (each major served at its own URL while a reader of it may exist; for a home wall the server stops building major 1, the composed render and the unversioned route once every Player reports 2; a Player missed in the upgrade is visible because its heartbeat lacks 2) → conforms: the precondition is observed on the real wall before merge (05), and 02 builds the visibility the clause promises, which nothing built until now"
      - "§ The cutover (a heartbeat with no capabilities counts as [1]) → conforms: 02 implements it as the Walls notice's reading of silence"
      - "§ Major 1, § Versioning → amendment proposed in 01: major 1 is recorded as retired, its schema leaves the contract, and the label definition both other schemas borrow from it moves to a home of its own"
      - "§ What happens to show_now and next → conforms: 02 leaves the republish as the only effect"
  - artifact: feeds-and-players
    dispositions:
      - "ruling 4, every major at its own URL while a reader may exist → conforms, as above"
      - "ruling 7, the mat's width is the client's → conforms: 03 retires the server's MAT_WIDTH_INCHES and MAT_BOTTOM_WEIGHT, which the Player already holds under the same names"
  - artifact: re-architecture
    dispositions:
      - "§ Order of work, wave 4 row, 4g (the cutover and the removals: tv_display, TV_PANEL_*, MAT_*, the major 1 builder, the directive) → conforms: 02, 03, 04. MAT_* means the two geometry keys; the mat-colour engine's MAT_MODEL, MAT_MAX_OUTPUT_TOKENS, MAT_IMAGE_MAX_EDGE stay, because they are the server's"
  - artifact: data-model
    dispositions:
      - "per-device runtime state never lives in the catalogue (in-transition, wave 4) → conforms, and 03 discharges it: the tv_display rows, their mat_hex column and TV_PANEL_* leave the server; 05 marks the norm steady-state"
      - "derived artifacts are regenerated, never transported (in-transition, wave 4) → conforms, and 03 discharges it: no geometry-specific render is served to a Player after 02; 05 marks the norm steady-state"
  - artifact: architecture
    dispositions:
      - "the Library/Programming seam rule 3 (in-transition, #216) → conforms: 02 drops the directives table, which takes `directives.pinned_work_id`, one of the two named cross-seam foreign keys, with it. `theme_memberships.artwork_id` remains for #216"
      - "seam rules 1, 2, 4 → conforms: 03 moves readiness onto the master inside the Library; Programming still reads it only through the facade"
      - "the label generalises across output geometry, ruling extending it to the mat → conforms: the last upstream composer goes in 03"
      - "operation logic lives only in the service layer; MCP and HTTP are thin → conforms: 02's Skip and show-now stay one service method behind both"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ Availability, the wall never goes black because the server is down → conforms: unchanged; the Player replays the v2 horizon"
last_validated: null
---

# Build Plan — Wave 4g: the cutover and the removals

## What this plan is

The sixth of wave 4's seven plans (`re-architecture.md` § Order of work, row
4). Wave 4e left the server publishing two feeds per wall: major 1 (a
pre-matted render for one panel, plus the directive) and major 2 (the
schedule, with presentation masters the Player mats itself). This plan
retires major 1 on both planes and removes everything only it needed.

**Not in this plan:**
- Scenes and staging: 4f, which comes next.
- The store split (#216): its own scope. Dropping the directives table
  removes one of its two cross-seam keys.
- The dark hours: deferred to power control in 4e.
- The two inferences PR #345 put to the owner (which republishes keep the
  work on the wall; where "too small" starts). 4g changes neither.

## Goals

**Response taken:** proceed, citing the plan of record. The owner ruled wave
4's order on 2026-10-08 and said on 2026-10-10 "let's do it now", after being
told the cutover waits on the wall reporting major 2.

**Product:** one feed, one way a picture reaches a wall. A wall's mat is
right for its own screen, whatever that screen is. The server stops holding
one television's geometry, and the next features (scenes, then the public
channel) are written once, against major 2 alone.

**Architecture:**
- After this plan, nothing upstream of a Player knows a panel's geometry. The
  server publishes a schedule and masters; the Player composes.
- Readiness ("can this work go on a wall?") is a fact about the presentation
  master, not a render.
- What a Player can read is visible to the curator. The contract has promised
  this since 4c, and it is what makes the next cutover (a future major 3, or an
  App Store Player that cannot be upgraded on demand) safe.
- Must stay possible: a major 3 served beside major 2 the same way 4e did it;
  a public channel retiring a major by decision.

**Constraints:**
- The contract (`player-contract.md`, `contract/`), and its rule that the home
  cutover waits for every Player to report 2.
- The interim seam rules: no new cross-seam keys, no new catalogue reads from
  Programming.
- Tests are contracts. A test that holds behaviour still true after the
  cutover moves to major 2 rather than being deleted. This matters most for
  the Frame driver's behaviour in the Player's `test_rotation.py` (art mode,
  backoff, somebody watching television), which today is exercised only
  through the major 1 programme.

**Tradeoffs accepted:**
- No server code decides "every Player reports 2". There is one household
  and one deployment, so the precondition is observed on the real wall before
  merge, and the Walls notice makes a missed Player visible afterwards. A
  server that refused to retire a major on its own would be worth building
  when there is more than one household. Nothing on the roadmap has that
  before the public channel, which retires by decision anyway.

**Level:** Medium. The removals are mapped (the inventory below came from the
code). The uncertainty is the size of the test migration: the server's
`ready_work` fixture creates a `tv_display` row and is used across most of the
curation suite, and the Player's `publish` fixture writes major 1 for about
fifteen test files. *What would raise it:* 03 starts by switching `ready_work`
to a master-backed work and running the suite, so the breakage is counted
before any production code moves.

**Open assumptions** (each inferred by the builder, not ruled by the owner):
- *Inferred:* the Player stops reading major 1 too: `REQUESTED_MAJORS`
  becomes `(2,)` and the major 1 programme is deleted, as `rotation.py`'s
  header, `memory.py` and `feeds-and-players.md` already say 4g does. A major
  1 document becomes a refusal fixture. [LOW impact | user can override]
- *Inferred:* the unversioned route and `v1` answer 404, which a Player
  already treats as "ask the next major down". [LOW impact | user can override]
- *Inferred:* `manifest.v1.schema.json` and its fixtures leave the contract.
  The `label` definition that `manifest.v2` and `label.v1` borrow from it moves
  into a schema of its own, unchanged. The contract's history keeps major 1's
  description in prose. [LOW impact | user can override]
- *Inferred:* a work is ready for a wall when it has a current presentation
  master. `no_rendition` and `stale_rendition` become the master's words for
  the same two states. The wall preview's thumbnail is drawn from the master.
  [MED impact | user can override]
- *Inferred:* a startup migration deletes the `tv_display` rows and drops
  `renditions.mat_hex`. The JPEGs under `ART_ROOT/ready/` are left on disk and
  named in the startup log and in `deploy/README.md` as safe to delete, because
  removing a directory of the operator's files is the operator's act. [LOW
  impact | user can override]
- *Inferred:* a Player's heartbeat lists the majors it reads. The Walls screen
  says, in words, when a wall's latest heartbeat does not list 2: "this Player
  can't read this server's feed". A heartbeat with no capabilities counts as
  `[1]` (contract), so it says so too. [MED impact | user can override]
- *Inferred:* Skip keeps its button and its MCP verb (`next`), and show-now its
  MCP verb, each now only republishing the schedule. The HTTP route moves off
  `/api/directives`, because the noun is gone; the new route is named for the
  act. [LOW impact | user can override]
- *Inferred:* `TV_PANEL_*`, `MAT_WIDTH_INCHES` and `MAT_BOTTOM_WEIGHT` join the
  server's `RETIRED_SETTINGS`, which warns and starts, so a NAS `.env` that
  still carries them keeps working. The Player keeps all of them under the same
  names. [LOW impact | user can override]
- *Inferred:* the Player's `ROTATION_INTERVAL_SECONDS` and `ROTATION_SHUFFLE`
  feed only the major 1 reader, so they retire. The Player's
  `RETIRED_SETTINGS` refuses to start on a retired key, so the operator walk
  (05) checks the Pi's environment file before deploying. [MED impact | user
  can override]

**Decisions made mid-build** (each settled by the goal or prior choice named):

## Inventory

Derived from the code on 2026-10-10 by grep over all three projects,
`contract/`, `deploy/`, `.env.example`, CI and the artifacts. Paths only; each
chunk re-derives its own list before editing (learning rule: an inventory
comes from the thing itself).

- **Major 1 and the route:** `programming/manifest/builder.py` (the major 1
  half; `Exclusion`, `KeptOff`, `media_document`, `write_atomically` are shared
  with v2 and the client feed and stay); `programming/display.py` (`sync`,
  `reconcile`, `_withdraw_v1`, `_media_moved`, `published_manifest`, the 4e
  gate in `_write_v2` and `_reconcile_v2`'s `carried`); `http/player.py`
  (both v1 routes); `config.py` (`manifest_path`, `manifest_pattern`);
  `contract/routes.json`; `contract/schemas/manifest.v1.schema.json` and its
  fixtures; `GET /api/manifest` and `ManifestOut` (the curator's preview, read
  by `hanging.js`, `work.js`, `walls.js`).
- **The directive:** the `Directive` record, the `directives` table and index,
  the store protocol, `establish_the_wall` and `add_wall` (both seed one),
  `step_display`, `show_work_now`, `_advance`, `_publish_directive`,
  `POST /api/directives`, `DirectiveOut`, `WallOut.directive_sequence` and
  `pinned_work_id`, MCP `art_display` (`show_now`, `next`, `walls`) and the
  server instructions, and Skip in `screens/walls.js`.
- **`tv_display`:** `RenditionKind.TV_DISPLAY`; `library/acquisition/preparation.py`
  and `compose.py`; `readiness.py` (`assess`, `playable_from`);
  `facade.py`; `thumbnails.py`; `survey.py`; `queue.py`'s two startup
  backfills and their store queries; `seed/ingest.py`; MCP `regenerate` and
  `set_mat_color`; `badges.js`; `ART_ROOT/ready/`.
- **Server panel geometry:** `config.py` (`TV_PANEL_*`, `MAT_WIDTH_INCHES`,
  `MAT_BOTTOM_WEIGHT`, `tv_pixels_per_inch`, `tv_artwork_box`); `__main__.py`;
  `container.py`; `.env.example`.
- **The Player's major 1 reader:** `programmes/rotation.py`, `programmes/memory.py`,
  `manifest.py` (the major 1 parse and types), `pull.py` (the entries path),
  `state/store.py` (`last_acted_sequence`), the `1:` programme registered in
  `displays/frame.py` and `displays/screen.py`, `config.py`'s two `ROTATION_*`
  keys; the `publish` fixture in `tests/conftest.py`, `server_double.py`,
  `test_rotation.py`, `test_directives.py`, `test_majors.py`.
- **Majors reported:** nothing on the server reads `manifest_majors`. It sits
  in the raw heartbeat file per wall; only `capabilities.screen` is parsed,
  into `reported_screens`.

## Status

- [ ] Chunk 01: The contract retires major 1
- [ ] Chunk 02: The server stops publishing major 1, and the directive goes
- [ ] Chunk 03: The server stops composing for a panel
- [ ] Chunk 04: The Player reads only major 2
- [ ] Chunk 05: Cutover on the wall, and the records

Context: branched from develop at the merge of #345 (wave 4e).

### Chunk 01: The contract retires major 1

- **Critic mode:** final. Both planes build to it.
- **Surfaces:** new `contract/schemas/label-def.schema.json` (or the name the
  schema index's conventions choose); `contract/schemas/manifest.v2.schema.json`
  and `contract/schemas/label.v1.schema.json` (their `$ref`); `contract/schemas/manifest.v1.schema.json`
  and `contract/fixtures/manifest.v1/` (retired; one major 1 document kept as a
  refusal fixture under major 2's reader); `contract/fixtures/index.json`;
  `contract/routes.json` (`manifest` retired); `tests/preferences/test_player_contract.py`;
  `.prawduct/artifacts/player-contract.md` (§ Major 1, § Versioning, § The cutover,
  each with a dated amendment note).
- **Done when:**
  1. Both borrowing schemas resolve the label definition from its new home,
     and every existing v2 and label fixture validates exactly as before.
  2. The root contract tests pass with no reference to the major 1 schema,
     and a major 1 document is in the index as one every Player must refuse.
  3. A re-break (the old `$ref` restored against the deleted file) is watched
     failing once.

### Chunk 02: The server stops publishing major 1, and the directive goes

- **Surfaces:** `arrt/src/arrt/programming/display.py`, `arrt/src/arrt/programming/manifest/builder.py`,
  `arrt/src/arrt/programming/store.py`, `arrt/src/arrt/persistence/` (records, sqlite, migrations,
  file), `arrt/src/arrt/http/player.py`, `arrt/src/arrt/http/api.py`, `arrt/src/arrt/http/models.py`,
  `arrt/src/arrt/mcp/` (tools, bindings, server), `arrt/src/arrt/config.py`, `arrt/src/arrt/__main__.py`,
  `arrt/src/arrt/http/static/` (`screens/walls.js`, `screens/hanging.js`, `screens/work.js`),
  `arrt/src/arrt/programming/manifest/heartbeat.py`; their tests.
- **What:** one feed per wall, built from the schedule. Every publish path
  writes major 2 only. The 4e gate that withheld v2 goes, along with v1's
  `carried` feeding v2. The curator's preview is read from the v2 document.
  Skip and show-now republish without a directive. A migration drops the
  `directives` table and its index, and `add_wall` and the wall migration stop
  seeding rows. `v1` and the unversioned route answer 404. The heartbeat's
  `manifest_majors` is parsed (silence counts as `[1]`) and the Walls screen
  says when a wall's Player cannot read major 2, with the same words on the MCP
  `walls` read.
- **Done when:**
  1. Every publish path, derived from the code, is tested to write v2 and no
     major 1 file. A grep for the major 1 filename template and `directive`
     (excluding the systemd sense) in `arrt/src` returns only the migration.
  2. The migration is idempotent, runs on a file carrying the table with rows,
     and on one without it, and is watched failing once against a re-break.
  3. The Walls notice is asserted present for `[1]`, for a heartbeat with no
     capabilities, and absent for `[2]` (learning rule: assert a conditional
     clause's absence where it must not appear).
  4. The browser suite runs green, with Skip and the preview exercised against
     a v2-only wall.
  5. Mutation sweep over the changed lines of `display.py` and the migration.

### Chunk 03: The server stops composing for a panel

- **Surfaces:** `arrt/src/arrt/library/readiness.py`, `arrt/src/arrt/library/facade.py`,
  `arrt/src/arrt/library/acquisition/preparation.py`, `arrt/src/arrt/library/acquisition/compose.py`
  (retired, and `JPEG_QUALITY` moved to `master.py`), `arrt/src/arrt/library/thumbnails.py`,
  `arrt/src/arrt/library/survey.py`, `arrt/src/arrt/library/acquisition/queue.py`,
  `arrt/src/arrt/persistence/` (records, sqlite, migrations), `arrt/src/arrt/seed/ingest.py`,
  `arrt/src/arrt/mcp/` (`regenerate`, `set_mat_color`), `arrt/src/arrt/config.py`, `arrt/src/arrt/__main__.py`,
  `arrt/src/arrt/services/container.py`, `arrt/src/arrt/http/static/` (`badges.js`, `screens/walls.js`'s reason
  words), `.env.example`, `arrt/tools/mat_masters.py` and `arrt/tests/contract/test_mat_corpus.py`
  (the corpus composes with the server compositor today); `arrt/tests/conftest.py`
  (`ready_work`) and the tests it feeds.
- **First:** switch `ready_work` to a master-backed work and run the suite, to
  count the breakage before any production code moves.
- **What:** readiness and `PlayableWork` rest on the master. Preparation stops
  composing; a mat colour change no longer re-renders anything (the colour
  rides the feed). The two backfills that existed only for the TV render go.
  A migration deletes the `tv_display` rows and drops `mat_hex`, leaving the
  shared `layout` column. The server's panel geometry settings retire with a
  warning.
- **Done when:**
  1. A grep for `TV_DISPLAY`, `tv_display`, `TV_PANEL`, `MAT_WIDTH_INCHES`,
     `MAT_BOTTOM_WEIGHT` and `ready_path` in `arrt/src` returns only the
     migration and `RETIRED_SETTINGS`.
  2. A work with a master and no TV render is playable; a work with neither
     is refused by name; a stale master is refused by name.
  3. The mat corpus test still checks every colour it checked before. If it
     needs a compositor to show a colour, it says why it no longer does, in
     the commit (learning rule: a dropped assertion is replaced in the same
     commit with a reason).
  4. The migration test, as in 02, and a startup with the retired settings
     present still starts and warns.
  5. Mutation sweep over `readiness.py`'s changed lines.

### Chunk 04: The Player reads only major 2

- **Delegated** to one agent in an isolated worktree, on its own branch cut
  from this one after 01 commits. It touches `arrt-player/` only.
- **Surfaces:** `arrt-player/src/arrt_player/manifest.py`, `arrt-player/src/arrt_player/pull.py`,
  `arrt-player/src/arrt_player/wall.py`, `arrt-player/src/arrt_player/programmes/` (`rotation.py`
  and `memory.py` retired), `arrt-player/src/arrt_player/state/store.py`,
  `arrt-player/src/arrt_player/displays/frame.py`, `arrt-player/src/arrt_player/displays/screen.py`,
  `arrt-player/src/arrt_player/config.py`; `arrt-player/tests/` (the `publish` fixture writes major 2;
  `server_double.py`; `test_rotation.py`'s Frame-driver cases move onto the
  schedule programme; `test_directives.py` and the major 1 half of
  `test_majors.py` retire, each retired assertion named with what replaces it
  or why nothing must).
- **Done when:**
  1. `REQUESTED_MAJORS == (2,)`, the heartbeat reports `[2]`, and a major 1
     document is refused as unsupported while the wall keeps what it shows.
  2. Every Frame-driver behaviour `test_rotation.py` held (art mode, backoff,
     somebody watching television, and the rest it lists) is held by a test
     through the major 2 programme. The delegate returns the list, old test →
     new test.
  3. `uv run --group raster pytest` green in `arrt-player/`, ruff and black
     clean, and a grep for `Rotation`, `directive`, `last_acted_sequence` and
     `ROTATION_` in `arrt-player/src` returning nothing.
  4. Mutation sweep over the changed lines of `pull.py` and `manifest.py`.

### Chunk 05: Cutover on the wall, and the records

- **Type:** cumulative-final
- **Visual change:** yes
- **Surfaces:** merge 04; the artifacts that describe major 1, the directive,
  `tv_display` or the server's panel geometry as current (`architecture.md`,
  `data-model.md` (both norms to steady-state), `api-contract.md`,
  `boundary-patterns.md`, `operational-spec.md`, `information-architecture.md`,
  `project-state.yaml`, `re-architecture.md`'s wave row), `README.md`, `CLAUDE.md`,
  `deploy/README.md`, `.prawduct/operator-verification.md`, the change log.
- **Done when:**
  1. Before merge, the real wall runs `develop` (wave 4e), adopts v2 and its
     heartbeat lists 2. That is the contract's precondition, observed and
     recorded with what was seen.
  2. End to end on this machine: a Player from this branch against a server
     from this branch adopts v2, composes, reports `[2]`, and the Walls screen
     shows no notice. A heartbeat listing only `[1]`, as a Player from before
     wave 4c would send, is shown the notice.
  3. A grep over the whole repo (no `--include`) for the retired nouns finds
     each survivor either rewritten or marked as history (learning rule: when
     you retire anything, grep for its nouns and old wording).
  4. All three suites, the browser suite, and the cumulative review.
