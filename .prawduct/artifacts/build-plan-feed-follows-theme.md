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
- **02: a hung theme's feed carries every work of the theme the Library will
  show, without waiting for a re-hang.** Whenever a wall's hung theme would
  send a different set of works than its feed carries, or the wall has no feed
  for it, the server republishes the theme's feed, keeping the slot on the wall
  now (as re-hanging the same theme does). It is checked at start, on every
  Library announcement about a work the hung theme holds, and on every change
  to the theme's membership or to the exclusions.
- Done when: both suites green; the regression tests seen red against the
  unfixed code; the records say what the code does; deployed, with Walls
  showing no feed notice for the Pi with its screen unplugged.

### Decisions

- **[DECISION: the 2026-09-30 ruling is superseded, not amended.]** The record
  (`archive/build-plan-wave-2b-seams-and-http.md`) says the operator confirmed
  "removals republish, additions wait for sync". The owner's 2026-10-10 ruling
  reverses its second half. Every place that cites it is rewritten to say what
  happens now; the archived plan stays as history.
- **[INFERENCE, flagged for the boundary: the feed follows membership in both
  directions.]** The owner spoke of adding. Taking a work out of a hung theme
  from the Theme screen now also takes it off the wall at once, as
  *Not this one again* from the theme already did. Following only additions
  would leave a start-up check that removes what the act itself did not, so a
  restart would change the wall.
- **[INFERENCE: order and pace still wait for a re-hang.]** Moving a work in
  the theme, or changing its pace or shuffle, changes when works show, not
  which; the owner's ruling is about which works. A republish for any other
  reason carries them, as a re-hang does.
- **[DECISION: the feed is compared as a set of works, not rebuilt every
  time.]** Republishing reshuffles the future slots, so it is done only when
  the set of works the theme would send differs from the set of its members
  the feed carries (guests finishing a slot are not members, and are not
  counted). A changed master or colour stays a patch, as it is now.
- **[DECISION: offering a newly accepted work its theme publishes nothing by
  itself.]** `offer_destinations` adds memberships without following, and its
  callers (the announcement handler, and start-up after `catch_up_offers`)
  reconcile afterwards, so a bulk acceptance builds each wall once and
  `catch_up_offers` stays outside the start-up guard for unwritable feeds.
- **[DECISION: deploy server first, a departure from § Versioning.]** A minor 4
  heartbeat without a screen fails a minor 3 server's check (it refuses
  `capabilities` with no `screen`). There is one server and one Player, and
  they deploy together; the deploy guide says server first.
- **Cost:** a check that finds a difference builds the wall's whole theme, as
  a hang does. An announcement builds only the walls whose hung theme holds the
  work.

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

- `programming/display.py`: a `_follow(walls)` step; `reconcile` runs it for
  every wall with a theme hung (narrowed, for an announcement, to walls whose
  hung theme holds the work); `add_to_theme`, `add_works_to_theme`,
  `remove_from_theme`, `remove_works_from_theme` and `allow_work` run it for
  the walls hanging the theme concerned; `on_work_changed` offers before it
  reconciles. Docstrings citing the old ruling rewritten.
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
- [ ] Chunk 02: the feed follows the hung theme (#349)
