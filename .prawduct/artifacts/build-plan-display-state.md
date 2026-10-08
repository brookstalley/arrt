---
artifact: build-plan
version: 1
scope: display-state
# branch: feature/labels-and-display-state — merged in #310 and deleted. Chunk 05, the only one left, is the operator's at the wall and claims no branch; it is ticked in whichever PR follows the walk.
partition: Chunk 01 serial (the contract both sides build to); then delegates in worktrees — A the Player (02, 03; postarr/ only), B the server and Walls (04; arrt/ only); coordinator integrates, reviews and verifies. Chunk 05 is the operator's.
depends_on:
  - artifact: labels-and-surfaces
  - artifact: player-contract
  - artifact: samsung-tv-state-findings
  - artifact: clients
last_validated: null
---

# Build Plan — Each wall controller reports its display state

## What this plan is

Step 1 of `labels-and-surfaces.md` § What changes, in order: the wall controller
reports what its screen is doing, on change, and the server keeps it. Walls reads
it, and today's panel (still on the Frame loop) follows the note's label table.
Label outputs and their mapping (#188) are the next plan, not this one.

| Chunk | What |
|---|---|
| 01 | The contract: heartbeat minor 3 carries `display_state`, with fixtures on both sides |
| 02 | The Frame controller reports its state, a remote-control change resolved to a work, and its panel follows the table |
| 03 | The HDMI controller reports its state |
| 04 | The server keeps each wall's state, adds `unassigned` and `silent`, and Walls shows it |
| 05 | On the wall: a remote change, TV in use, and the set off, each seen on Walls (the operator) |

**Not in this plan:** label outputs, their mapping and renderers on other clients
(#188); caption mode. The 30-minute rule for a *silent* wall belongs with label
renderers off the wall's own device, where silence is possible; the Frame loop's own
panel applies it to `unreachable` here.

## Requirements Confidence

**High** for the states and the label table: ruled 2026-10-08
(`labels-and-surfaces.md` § Rulings). **Medium** for mechanism:

- `[DECISION: display_state rides the heartbeat as minor 3, not a sibling document,
  and the heartbeat is written on a display-state change as well as on its interval
  | because the pull already forwards a changed heartbeat file within about a
  second (pull.py), the server already validates and stores it, and the field is
  additive | builder's call]`
- `[DECISION: on a Frame, a remote-control change is resolved to a work by the
  set's content id through the Player's bindings; a content id with no binding is
  showing_art with work_id null (a picture this wall did not put there) | builder's
  call]`
- `[ASSUMPTION, corrected while building: the daemon never read PowerState, and
  television and dark read alike except by it. So the Frame takes one read-only
  PowerState read (a REST GET, never a key press) only right after a get_artmode read
  says off: standby is dark, on is in_use, a failed read is in_use. Unmeasured on the
  set until chunk 05 (samsung-tv-state-findings.md § What is still owed).]`
- `[ASSUMPTION: an HDMI connector reported "no screen detected" (#274's reading) is
  dark; an output absent from the client is no_screen.]`

## Status

- [x] Chunk 01: The contract
- [x] Chunk 02: The Frame controller
- [x] Chunk 03: The HDMI controller
- [x] Chunk 04: The server and Walls
- [ ] Chunk 05: On the wall

### Chunk 01: The contract

Done when:

1. `contract/schemas/heartbeat.v1.schema.json` accepts minor 3's `display_state`:
   `{state: showing_art|in_use|dark|no_screen|unreachable, work_id: string|null,
   since: RFC 3339}`, `work_id` non-null only with `showing_art` (or null for a
   picture this wall did not put there). Absent means a pre-minor-3 Player.
2. Valid and invalid fixtures for each state and for the work_id rule;
   `player-contract.md` § The heartbeat, minor 3 says what each state means and
   points at `labels-and-surfaces.md`.
3. The three suites' contract tests pass over the new fixtures.

### Chunk 02: The Frame controller

Done when:

1. The daemon derives `display_state` from what it already reads: a confirmed
   selection or `image_selected` announcement (resolved through bindings) is
   `showing_art`; art mode off with the panel lit is `in_use`; standby is `dark`;
   no answer is `unreachable`.
2. A change writes the heartbeat at once; an unchanged state keeps the interval.
3. The panel follows `labels-and-surfaces.md`'s table: blank for `in_use` and
   `dark`; the work's caption for `showing_art`; a remote change gets the right
   caption (today's behaviour kept); `unreachable` keeps the last caption for 30
   minutes and then blanks (the owner, 2026-10-08), one named constant.
4. Tests in `postarr/tests` drive the TV double through each transition, including
   a remote change and TV in use then back to art; the existing label wiring tests
   stay green or change deliberately with the reason recorded.

### Chunk 03: The HDMI controller

Done when:

1. `ScreenWall` reports `showing_art` with the work it drew, `dark` when its
   connector reports no screen detected, `no_screen` when its output is absent.
2. A change writes the heartbeat at once. Tests in `postarr/tests/test_screen.py`.

### Chunk 04: The server and Walls

Done when:

1. The server keeps each wall's latest `display_state` from its heartbeat, and
   derives `unassigned` (no display output mapped) and `silent` (report older than
   `STALE_AFTER_SECONDS`, the threshold Walls already uses).
2. `/api/walls` and the MCP walls read carry it; a pre-minor-3 heartbeat maps
   `current_work_id` to `showing_art` so today's Players still read.
3. Walls' card leads with the state: the work when `showing_art`; "Somebody is
   using the screen", "Its screen is off" (the labels rule refuses a short label opening "The "), "No screen", "Not known" otherwise,
   in the product's voice; `current_work_id` alone is no longer read.
4. Browser tests seed real heartbeats for each state.

### Chunk 05: On the wall

Done when the operator, with the Player and server deployed, sees on Walls: a
remote-control change on the Frame within 15 s, the TV in use, and the set off,
and the panel blank while the TV is in use. *(Needs the Frame back on a wall; the
HDMI states are seen on the Pi's own wall.)*

## Verification

All three suites at each chunk boundary; the contract tests are the seam. Chunk
05 is hardware and the operator's.
