---
artifact: build-plan
version: 1
scope: wave-4e-schedule
branch: feature/wave-4e-schedule
partition: serial — 02 publishes what 01 computes, 03 adds a key to the document 02 builds, and 03 and 04 both edit the Walls screen (`static/screens/walls.js`) and `programming/display.py`
depends_on:
  - artifact: re-architecture
  - artifact: feeds-and-players
  - artifact: player-contract
  - artifact: architecture
governed_by:
  - artifact: player-contract
    dispositions:
      - "§ Major 2, § Rules a schema cannot state (every named work is a key of works; slots run forward without overlap, inside the horizon; the horizon is whole days) → conforms: 02 validates every published document against `manifest.v2.schema.json` and `semantic_errors` in the curation suite, and 01's tests assert the rules over generated schedules"
      - "§ Time (absolute instants; gaps are dark; half-open spans) → conforms: 01 publishes RFC 3339 instants with offsets and abutting half-open slots. It publishes no gaps, because the dark hours are deferred (decision below)"
      - "§ Settled before wave 4 (a three-day horizon; works may carry works nothing names, but should not) → conforms: 01 builds three days, and 02's works map holds exactly the works the schedule names"
      - "§ What happens to show_now and next (each republishes the schedule starting now) → conforms: 02. Major 1's directive is still written beside it until 4g, because major 1 walls still read it"
      - "§ The cutover (each major served at its own URL while a reader may exist) → conforms: 02 serves v2 beside v1 and the unversioned route; retiring v1 is 4g"
      - "§ Scenes, § Staging → inapplicable because scenes are 4f; 02 publishes neither key"
      - "§ The heartbeat, minor 2 (capabilities; Programming judges size from the largest screen reported recently) → conforms: 04"
  - artifact: feeds-and-players
    dispositions:
      - "ruling 3, a feed plus a control layer; the Player core consumes only a feed → conforms: the v2 document is the wall's private feed"
      - "§ Presentation settings come in three layers; Programming offers a wall only what its display can honour → conforms: 03 adds the one wall setting every compositing Player can honour, mat mode. Label, overlay, fades, text scale and facts are not offered, because every display reports label_modes ['none'] until the caption in the mat (wave 6+)"
      - "ruling 7, the feed carries only the mat colour; the mode is a setting and the width is the client's → conforms: 02 sends mat_color per work, 03 sends settings.mat.mode, nothing sends a width"
  - artifact: re-architecture
    dispositions:
      - "§ Order of work, wave 4 row (4e: Programming's schedule, wall settings and the major 2 feed beside major 1; one household rule, no work on two walls at the same moment; per-wall interval and shuffle carry over as slot length and order) → conforms: 01, 02, 03"
      - "§ Order of work, wave 4 row (rotation moves to Programming along with the wake/sleep window) → exception, recorded as a decision below: the dark hours wait for power control"
      - "§ Compositing moves to the Player (image adequacy for a wall is Programming's judgement from reported geometry; the Player composes and does not judge) → conforms: 04"
  - artifact: architecture
    dispositions:
      - "the Library/Programming seam rules 1, 2 and 4 → conforms: 02 reads the presentation master only through a new facade field (plain data, content-addressed URL), and the existing work events drive v2 the way they drive v1"
      - "seam rule 3 (separate stores; in-transition, #216) → conforms with the interim rule: 03's and 04's new state is Programming's own, keyed by wall id and display id, with no cross-seam foreign key"
      - "the manifest and content-addressed media are the only channel to a Player → conforms: v2 is a second manifest major on the same channel, and its media URLs are the Library's"
      - "operation logic lives only in the service layer; MCP and HTTP are thin → conforms: 03's setting is one service method behind both"
  - artifact: data-model
    dispositions:
      - "derived artifacts are regenerated, never transported (in-transition) → conforms: v2 names the presentation master, which is rendered for no geometry (the ruling in data-model.md § Direction)"
      - "per-device runtime state never lives in the catalogue → conforms: 04's reported screens are Programming state about a display, not catalogue state about a work"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ Availability, the wall never goes black because the server is down → conforms: the Player replays the horizon; 02 rolls it forward long before it runs out"
      - "§ Output Quality, a picture below the minimum is shown rather than refused → conforms: 04's 'too small for this wall' informs the curator and takes nothing off the schedule"
last_validated: null
---

# Build Plan — Wave 4e: Programming's schedule, wall settings and the major 2 feed

## What this plan is

The fifth of wave 4's seven plans (`re-architecture.md` § Order of work, row
4). Waves 4a–4d settled the major 2 contract, gave the Library a presentation
master, and gave the Player a reader and a compositor that ask for `v2` first.
The server still answers `v2` with 404, so every wall runs on major 1. This plan
builds what the Player has been waiting for: Programming computes a schedule for
every wall together, publishes it as each wall's major 2 feed beside major 1,
and the walls start showing works the Player matted itself.

**Not in this plan:**
- The removals (`tv_display`, `TV_PANEL_*`, `MAT_*`, the major 1 builder, the
  directive, the unversioned route): 4g. Every path that publishes major 1 keeps
  doing so.
- Scenes and staging as a curator feature: 4f.
- The caption in the mat, and every label or overlay setting: wave 6+.
- **The dark hours**, descoped from the wave 4 row (decision below).
- The store split (#216): its own scope.

## Goals

**Response taken:** proceed, citing the plan of record. The owner ruled wave 4's
order on 2026-10-08, and on 2026-10-09 said "go as fast as we can to the right
long term solution". 4d's plan names this session for 4e.

**Product:** what a wall shows becomes a schedule the curator can see and the
whole house shares, not a rotation each Player runs on its own. That is the
precondition for the schedule-shaped features the product is heading to
(scenes, dark hours, playlists across rooms; `re-architecture.md` § The
manifest is a schedule), and the point at which a 1080p screen or a
non-4K Frame gets a correct mat.

**Architecture:**
- The schedule is computed in one pure function over every wall at once. The
  household rule needs all walls, and a pure function is what makes its
  property tests cheap.
- The **published document is the schedule's state**, as major 1's published
  document already is. A republish reads the last published v2 to keep the
  slot on the wall now, so editing a theme never jumps a wall mid-work.
- Major 2 is published on **every path that publishes major 1**, from one place.
  Two publish paths that each remember the other would drift.
- Must stay possible: scenes (4f) as a republished feed; dark hours as gaps;
  more wall settings once a display reports it can honour them.

**Constraints:**
- The contract, its schema, its five semantic rules and the three-day horizon.
- Major 1 behaviour unchanged until 4g. The suite that holds it stays green
  untouched.
- The interim seam rule: no new cross-seam foreign keys, no new catalogue reads
  from Programming.

**Tradeoffs accepted:**
- Both majors are built on every publish until 4g, which doubles publish work.
  Publishing is milliseconds per wall.
- New Programming state goes into the shared SQLite file until #216 splits the
  store, so that split moves two more tables.

**Level:** Medium. The contract fixes the document, and the publish paths exist.
The uncertainty is in schedule stability: which republishes keep the current
slot and which start fresh. And in the household rule's unsatisfiable cases.
*What would raise it:* 01 begins by listing every caller of `sync` and
`activate_theme`, with each one's answer to "keep the current slot or start
now", before writing the function.

**Open assumptions** (each inferred by the builder, not ruled by the owner):
- *Inferred:* slots run back to back with no gaps, one slot per work, the slot
  length being the theme's rotation interval (its own, or the default). Order is
  the theme's order, or a shuffle that shows every work once before any repeats,
  as the Player's rotation does today. [LOW impact | user can override]
- *Inferred:* a republish keeps the slot covering *now* from the last published
  schedule and starts the new schedule at that slot's end. Except that
  `show_now`, `next`, hanging a theme or a selection, and a refused work on the
  wall now start fresh at *now*. [MED impact | user can override]
- *Inferred:* when the household rule cannot hold, because a wall has no other
  work to show in that slot (one work hanging on two walls), the wall with the
  lower id keeps it, and the other wall shows it too. The build names the clash
  rather than leaving a wall dark. [LOW impact | user can override]
- *Inferred:* the horizon rolls forward on the wall's heartbeat. When a Player
  reports and its published horizon has less than two days left, the wall is
  republished. The heartbeat already arrives every few seconds from every live
  wall, so this needs no scheduler. A wall nobody is watching doesn't need its
  horizon extended. [LOW impact | user can override]
- *Inferred:* a work with no presentation master yet (4b builds them in the
  background) is left out of major 2 and named in the build's exclusions, and
  stays on major 1. [LOW impact | user can override]
- *Inferred:* "too small for this wall" means the master, fitted inside the
  wall's largest recently reported screen with the 6% relative mat, would be
  drawn at less than half the box's long edge. The 1,000 px minimum was chosen
  as right for a 1080p screen (`re-architecture.md` § Open questions), and half
  a 4K box is about that. [MED impact | user can override]

`[DECISION: the dark hours (the v1 plan's Chunk 26 window, re-architecture.md's wave 4 row) are deferred to wave 6+ power control rather than built in 4e | a gap tells the Player to go dark, and until power control exists every Player keeps showing the last work through a gap (player-contract.md § Time), so dark hours built now would change nothing on any wall while adding a setting, its UI and its tests; the contract already carries gaps, so nothing has to change to add them later | the builder's, 2026-10-09; user can veto]`

## Status

- [ ] Chunk 01: The schedule
- [ ] Chunk 02: The major 2 feed, published and served
- [ ] Chunk 03: A wall's mat mode
- [ ] Chunk 04: Too small for this wall

Context: branched from develop after #341. Wave 4d (`feature/wave-4d-compositing`,
the Player) is built in a sibling worktree and touches nothing under `arrt/`.

### Chunk 01: The schedule

- **Critic mode:** final. This is the keystone 02 publishes, and stability and the
  household rule are where the design can be wrong.
- **Surfaces:** new `arrt/src/arrt/programming/schedule.py` (pure: walls, their
  ordered playable work ids, each theme's interval and shuffle, the last
  published schedules, *now*, and each wall's "start fresh" flag go in; slots per
  wall and the named clashes come out); new `arrt/tests/unit/test_schedule.py`.
- **What:** three days of abutting half-open slots per wall, from *now* or from
  the end of the kept slot. Shuffle cycles that show every work once. The
  household rule: a work never in two walls' slots over overlapping spans,
  except a clash the build names. A seeded shuffle, so a test and a rebuild are
  reproducible.
- **Done when:**
  1. Property tests over generated walls and themes hold: the five semantic
     rules; no overlap of one work across walls except named clashes; every work
     appears once before any repeats; a keep-the-slot rebuild leaves the slot
     covering *now* byte-identical; a start-fresh rebuild begins at *now* with
     the requested work.
  2. Example tests pin the cases the properties found or the assumptions name:
     one work on two walls, two walls with different intervals, an empty theme,
     a refused current work.
  3. Mutation sweep over the new module, with every surviving mutant explained.

### Chunk 02: The major 2 feed, published and served

- **Surfaces:** `library/facade.py` (the master as a `Media` on `PlayableWork`,
  or None); `programming/manifest/` (new `v2.py`: document from schedule, works,
  settings); `programming/display.py` (one publish step writing both majors,
  called from every path that publishes major 1, including the event patch
  and startup reconciliation; `show_work_now` and `step_display` republish v2
  starting fresh; the heartbeat rolls the horizon); `http/player.py`
  (`/walls/{id}/manifest/v2` serves the published v2 with its ETag); the tests
  for each; `player-contract.md` § The cutover if the built behaviour teaches
  it anything.
- **Done when:**
  1. Every published v2 in the suite passes the schema and `semantic_errors`,
     asserted at the publish step, not just in one test.
  2. Each major 1 publish path is tested to publish v2 as well. The list of
     callers is derived from the code, not from this plan.
  3. A refused work leaves both majors, and a v2 wall that was showing it starts
     fresh.
  4. `v2` answers 200 with an ETag and 304 on a match; `v1` and the unversioned
     route are unchanged.
  5. **End to end:** the Player from `feature/wave-4d-compositing` (or develop,
     once 4d merges), pointed at a local server built from this branch, adopts
     v2, composes, and its heartbeat lists `[2, 1]`. Recorded in the change log
     with what was observed.

### Chunk 03: A wall's mat mode

- **Visual change:** yes
- **Surfaces:** Programming's store (a wall's settings, keyed by wall id: a
  persisted format, so questions first; below); `programming/display.py` (set
  it, republish); `http/api.py` and `mcp/tools.py` (one service call each);
  `static/screens/walls.js` (a control on the wall's card: No mat, Mat around
  the work, Mat to the edges); `information-architecture.md` (the Walls row);
  browser tests.
- **The questions the stored setting must answer:** what mode a wall's feed
  carries now; whether a curator ever set one (unset means the Player's own
  default, so a channel and an unset wall behave alike); and, once more settings
  exist, which of them a wall has set. A sparse per-wall settings record, one
  key per setting, answers all three.
- **Done when:** setting the mode republishes v2 with `settings.mat.mode`, and
  unsetting it removes the key. The control is tested in the browser. The IA row
  says what the control does.

### Chunk 04: Too small for this wall

- **Type:** cumulative-final
- **Surfaces:** `programming/manifest/heartbeat.py` or a sibling (reading
  `capabilities` from minor 2 heartbeats); Programming's store (the largest
  screen each display reported in the last 7 days); `programming/display.py`
  (the judgement per wall and work); `http/api.py` (on the wall view and the
  theme page's members); `static/` (a "too small for {wall}" note); browser
  tests; IA rows.
- **Done when:**
  1. A wall whose display has never reported a screen judges nothing and says
     nothing.
  2. A reported screen makes a small work say so on the Walls card and the
     theme page, and a later, smaller report does not clear it within the
     window.
  3. The judgement takes nothing off the schedule.
  4. Then the cumulative review, and `/prawduct:pr create`.

## Verification strategy

Beyond the suites: run the real Player against a local server from this branch
(02's end-to-end step), with an HDMI screen double and a Frame double. Then, on
the wall Pi after 4d merges, watch one wall adopt v2 and show a matted master.
The change log records what was seen, and where the real walk had to wait.
