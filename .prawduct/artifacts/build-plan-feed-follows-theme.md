---
artifact: build-plan
version: 1
scope: feed-follows-theme
branch: feature/feed-follows-theme
partition: serial, one worktree. Two small chunks; 01 touches the contract and both planes, 02 only `arrt/`, and they share no file but the records
depends_on:
  - artifact: player-contract
  - artifact: data-model
governed_by:
  - artifact: player-contract
    dispositions:
      - "§ The heartbeat, minor 2 (capabilities carries screen) → amendment in 01: minor 4 makes `screen` optional inside `capabilities`, so a Player that cannot see its screen still says which majors it reads"
      - "§ The cutover (a heartbeat with no capabilities counts as [1]) → conforms: unchanged; 01 stops the Player sending no capabilities merely because its screen is unknown"
      - "§ Versioning (Players upgrade before the server) → departure, recorded in Goals: a minor 4 heartbeat with no screen is refused by a minor 3 server, so this one deploys server first"
  - artifact: data-model
    dispositions:
      - "the operator's ruling of 2026-09-30, removals republish and additions wait for sync → superseded by the owner, 2026-10-10 (Goals): a hung theme's feed follows the theme"
last_validated: null
---

# Build Plan — the feed follows the hung theme

## What this plan is

Two defects found deploying wave 4g (2026-10-10), and the owner's rulings on
both, given the same day:

- **#348.** Walls says an up-to-date Player cannot read the feed whenever its
  screen is disconnected, because the Player then sends no `capabilities` and a
  heartbeat without them reads as `[1]`. Ruled: `screen` becomes optional.
- **#349.** A wall with a theme hung had no feed after the upgrade until the
  theme was hung again. Ruled: "it is fine, even desirable, for the server to
  add works to a theme while it is already hung."

**Not in this plan:** wave 4f (scenes), which comes next; the operator walk
owed for 4g, which is done at the set.

## Goals

- **01: a Player that cannot see its screen still reports what it reads.**
  Heartbeat minor 4: `capabilities.screen` is optional. The Player sends
  `backend`, `label_modes` and `manifest_majors` always, and `screen` when it
  knows it. The server accepts capabilities with no screen, and records no
  size from them; the adequacy judgement already treats a wall with no size
  reported as unjudged. A heartbeat with no `capabilities` still reads as `[1]`.
- **02: a work of a wall's hung theme that the Library will show reaches the
  wall without a re-hang.** The server republishes the theme's feed, keeping
  the slot on the wall now (as re-hanging the same theme does), when an act or
  an announcement concerns a member the build would send and the feed lacks:
  adding to the theme, allowing a work back, and every Library announcement
  (a restore, a master, a mat). At start it publishes a feed for a wall with a
  theme hung and none on disk. The horizon rolls by building the hung theme,
  which also carries an addition whose announcement was lost, within a day.
- Done when: both suites green; the regression tests seen red against the
  unfixed code; the records say what the code does; deployed, with Walls
  showing no feed notice for the Pi with its screen unplugged.

### Decisions

- **[DECISION: the 2026-09-30 ruling is superseded, not amended.]** The record
  (`archive/build-plan-wave-2b-seams-and-http.md`) says the operator confirmed
  "removals republish, additions wait for sync". The owner's 2026-10-10 ruling
  reverses its second half. Every place that cites it is rewritten to say what
  happens now; the archived plan stays as history.
- **[CONFIRMED by the owner, 2026-10-10, at PR #351: the feed follows membership in both
  directions.]** (Recorded first as an inference.) The owner spoke of adding. Taking a work out of a hung theme
  from the Theme screen now also takes it off the wall at once, as
  *Not this one again* from the theme already did. Following only additions
  would leave a start-up check that removes what the act itself did not, so a
  restart would change the wall.
- **[CONFIRMED by the owner, 2026-10-10, at PR #351: order and pace reach the wall at the
  next roll, within a day.]** (Recorded first as an inference.) The plan first said they wait for a re-hang. The
  roll has to build the hung theme (below), and a build carries the theme's
  order and pace, so they arrive at the next roll; re-hanging still makes them
  immediate. Holding them back would mean the roll building from the old
  order, which nothing records. Amended after the boundary review.
- **[DECISION, amended mid-build: additions are decided by the works an act or
  announcement concerns, never by comparing the theme with the feed.]** The
  feed names only the works its three-day horizon schedules (`as_document`
  prunes `works` to the slots' names, as `player-contract.md` § Settled before
  wave 4 asks), so a theme with more works than one horizon schedules always
  "lacks" members that are simply not due. Comparing sets would republish at
  every start. A changed master or colour stays a patch.
  **Cost, accepted:** an announcement about a member that is not in the current
  horizon reads as joining, so the wall is republished and its future slots
  reshuffled (the slot on the wall now is kept). It matters only for themes
  larger than one horizon, and nobody sees a schedule before it plays.
- **[DECISION, found mid-build: the roll builds the hung theme.]** `_roll_v2`
  rebuilt from the works the last horizon named, so such a theme narrowed to
  its first horizon's works for good. It now builds the theme; a wall with
  nothing hung rolls what it carries.
- **[DECISION: offering a newly accepted work its theme publishes nothing.]**
  A work is offered when it is accepted, before it is prepared, so it has
  nothing a feed could send; the announcement of its master puts it on the
  wall. `catch_up_offers` stays outside the start-up guard for unwritable feeds.
- **[DECISION: a catalogue edit that adds or removes a hung work writes the
  feed in its transaction]**, as hanging and *Not this one again* already do:
  a feed that cannot be written refuses the edit rather than leave the wall
  and the theme disagreeing with nothing saying so.
- **[DECISION: deploy server first, a departure from § Versioning.]** A minor 4
  heartbeat without a screen fails a minor 3 server's check (it refuses
  `capabilities` with no `screen`). There is one server and one Player, and
  they deploy together; the deploy guide says server first.
- **Cost:** a republish builds the wall's whole theme, as a hang does. An
  announcement asks the Library about its own work alone, and builds only the
  walls whose hung theme holds the work and lacks it.

## Chunks

### Chunk 01: heartbeat minor 4, `screen` optional (#348)

- `contract/schemas/heartbeat.v1.schema.json`: `screen` leaves `required`;
  descriptions say minor 4. A valid fixture: capabilities with no screen.
- `player-contract.md` § The heartbeat: a minor 4 subsection; § The cutover
  bullet no longer names a display that cannot say its size as a reason for no
  capabilities.
- Server `manifest/heartbeat.py`: capabilities with no `screen` is accepted; a
  malformed `screen` is still refused.
- Player `wall.py`: `_capabilities()` always returns the block, `screen` only
  when known; `heartbeat.py` minor 4.
- Tests: the Player's heartbeat with no screen lists `manifest_majors`; the
  server reads it as reading major 2 and records no screen size; the Walls
  notice is absent for it (and still present for a heartbeat with no
  capabilities).

### Chunk 02: the feed follows the hung theme (#349)

- `programming/display.py`: `reconcile`, narrowed to the works concerned,
  publishes additions; `add_to_theme`, `add_works_to_theme` and `allow_work`
  call it; `remove_from_theme` and `remove_works_from_theme` withdraw from the
  walls hanging the theme; start-up publishes for a hung wall with no feed;
  `_roll_v2` builds the hung theme. Docstrings citing the old ruling rewritten.
- Tests rewritten where they asserted the superseded ruling
  (`test_reconciliation.py`, `test_major_2_feed.py`,
  `test_selections_and_exclusions.py`), each recording why; new tests: a wall
  with a theme hung and no feed has one after start; a work added to a hung
  theme, one gaining its master, one allowed back, one newly accepted into the
  hung default theme reach the feed; a removal leaves it; a check that finds
  nothing different rewrites nothing.
- Records: `api-contract.md` (the exclusion undo), `data-model.md` (the undo,
  and the stale "Still open (#116)"), `information-architecture.md` and the
  Work page's and MCP's undo sentence where they say "the next time a theme
  holding it is hung", `deploy/README.md` § Wave 4g (re-hang no longer needed
  after this; server first).

## Status

- [x] Chunk 01: heartbeat minor 4, `screen` optional (#348)
- [x] Chunk 02: the feed follows the hung theme (#349)
