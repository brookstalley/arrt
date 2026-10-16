---
artifact: build-plan
version: 1
scope: wall-shape-filter
branch: feature/wall-shape-filter
partition: serial, one worktree. Two chunks; 02's client reads the API shape 01 writes
Critic mode: cumulative-final
depends_on:
  - artifact: build-plan-wall-rotation-settings
  - artifact: data-model
governed_by:
  - artifact: architecture
    dispositions:
      - "§ Direction (operation logic only in the service layer; bindings thin) → conforms: one service method, two bindings"
      - "§ Direction (the manifest is the only channel from server to Player) → conforms: the filter is applied when the server builds the feed; the Player sees fewer works and learns nothing new"
      - "§ Direction (the Library/Programming seam) → conforms: the shape is read from the master's size the Library already returns (`PlayableWork.master`); the judgement is Programming's"
  - artifact: player-contract
    dispositions:
      - "§ A wall whose theme holds nothing ready has a manifest with an empty `entries` list, which is an ordinary state → conforms: a filter that leaves nothing publishes that ordinary state; no contract change"
  - artifact: information-architecture
    dispositions:
      - "§ Direction (*arr layout; no new section) → conforms: the control joins the wall's card on Walls, beside rotation"
  - artifact: accessibility-spec
    dispositions:
      - "§ Direction norm 1 (the label is legible) → inapplicable because no label is typeset here"
      - "§ Direction norm 2 (WCAG 2.1 AA; colour never the sole carrier of state) → conforms: the dark-wall warning is a sentence, and the presets and custom fields are labelled controls"
  - artifact: data-model
    dispositions:
      - "§ Direction (identity is never a source URL) → inapplicable because nothing here touches identity"
last_validated: null
lifecycle: completed
archived: 2026-10-16
released_in: v0.5.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — a wall filters its theme by shape (#370)

## What this plan is

A wall can say which shapes of work it shows. The owner's example: a portrait
wall that shows nothing wider than 1:1, so wide landscapes stop arriving as a
strip across the middle of the screen. Works outside the wall's range are left
off that wall's feed, by name, the way a work kept off every wall already is.

## Goals

- **Response taken:** proceed. The owner answered the design questions
  2026-10-13 (below), and #353's storage ruling of the same day placed the
  setting on `walls`.
- **Product:** a curator with walls of different shapes hangs one theme
  everywhere and each wall shows only what suits it, without curating a theme
  per screen.
- **Architecture:** the filter is applied where the server builds a wall's feed
  (`DisplayService.build_manifest`), as an exclusion with a reason, so the
  "every work left out is named" rule (`manifest/builder.py`) covers it with no
  second mechanism. The Player is unchanged.
- **Level:** High. The mechanism exists (exclusions, the wall's settings
  route), and each open question is answered or marked inferred below.

### The owner's rulings (2026-10-13)

1. **A min–max range of width ÷ height.** Either bound may be absent. The client
   offers presets and stores numbers.
2. **Set by hand, off by default.** A wall with neither bound shows every shape,
   which is every wall today. The screen the wall's Player reports is shown
   beside the control as a hint, never applied.
3. **A filter that leaves nothing makes the wall go dark, with a warning.** It is
   honoured exactly. The feed is the empty one the contract already calls an
   ordinary state; Walls says plainly that the shape matched nothing.

### Decisions (mine, for the boundary review to show the owner)

- **Spoken as `widest` and `tallest`, written `W:H`.** "Widest 1:1" is the
  owner's example in their words. The API and MCP take `"4:5"` strings or a
  decimal, and the word `any` to remove a bound, because MCP drops null
  arguments (`registry.validate`) and "remove this bound" must be a word.
  Stored as two nullable REAL columns, `max_aspect_ratio` and
  `min_aspect_ratio`, beside `shuffle`. *Inferred.*
- **Inclusive, with 1% tolerance on the ratio.** A 3000 × 3003 scan is square to
  any curator; a strict comparison would leave it off a "nothing wider than 1:1"
  wall. *Inferred.*
- **Measured on the master's pixels** (`PlayableWork.master.width/height`),
  which the feed already carries and the too-small judgement already uses. Step 0
  of chunk 01 confirms that size has the work's orientation applied.
- **`set_rotation` widens into `set_playback`.** `art_display`'s menu is 2046 of
  2048 bytes, so a second action does not fit. Pace, order and shape are all
  "how this wall plays its theme", and one panel on the card holds them. #353's
  action and route are unmerged and have no callers outside this repo, so the
  rename costs nothing: `DisplayService.set_playback`, `PUT
  /api/walls/{id}/playback`, `art_display(action='set_playback')`.
- **A tallest wider than the widest is refused by name**, never silently
  swapped.
- **On a wall with nothing hung, the range waits for the next hanging.**
  `set_rotation` re-paced the feed a cleared wall carries; trimming that feed
  by shape could not be undone, because there is no theme to rebuild from
  when the range is widened again. *Decided at build; not settled by the
  goals.*
- **Shapes are a panel of their own on the card**, *Shapes it shows*, beside
  the rotation, rather than a row inside a renamed *How it plays*. Each has
  its own Set, as the mat does, and the two share one current state so
  neither puts back what the other set. *Decided at build; the plan's
  chunk 02 text said one panel.*
- **After review: the HTTP body leaves an omitted field alone** rather than
  requiring all four, so neither panel nor another surface can be overwritten
  by a page drawn earlier; each panel sends only its own fields.
- **An explicit show-now still shows a work outside the wall's shapes**: it is
  the curator naming that work for that moment. *Decided after review; the
  goals did not settle it.*
- **The plan's verification against a copy of the catalogue was not run.** No
  catalogue copy is on this machine. What stands in for it: the integration
  test that publishes through HTTP and reads the feed and summary back, and the
  operator walk queued for the real wall.
- **The new reason is the curator's**, beside `KeptOff.EVERY_WALL`: a
  `KeptOff.WALL_SHAPE` (`"outside_wall_shape"`) whose detail names the work's
  shape and the wall's range, e.g. "This wall shows nothing wider than 1:1; this
  work is 16:9."
- **`summarise()` stops calling every exclusion "not currently displayable".**
  A work left off by the wall's shape is displayable; the summary counts it
  apart, so "0 of 12 on the wall" never reads as twelve broken works.
- **Stacked on #353.** This branch starts from `feature/wall-rotation-settings`
  rather than `develop`, because it builds on its columns and widens its route.
  It merges after #353, or #353's PR is closed in favour of this one.

### Not in this plan

- Filtering automatically from the reported screen (ruled out, ruling 2).
- The panel on a wall with nothing hung. The rotation panel lives inside the
  setup disclosure, which needs a hanging; that question is the owner's, still
  open from #353, and this control follows whatever it decides.

## Chunks

### 01 — store, service, exclusion, API, MCP

0. Confirm `Master.width/height` is the oriented size (read the code that fills
   `master_size`; a rotated-EXIF fixture if none pins it).
1. `Wall` gains `min_aspect_ratio` and `max_aspect_ratio`, both nullable; the
   additive migration and both store backends.
2. `DisplayService.set_playback(wall_id, *, shuffle, rotation_interval_seconds,
   tallest, widest)` with `UNSET`, replacing `set_rotation`, republishing the
   wall's feed as `set_rotation` does.
3. `build_manifest` excludes a playable work outside the range with
   `KeptOff.WALL_SHAPE`, after the kept-off check; `summarise()` and the sync
   warning count shape exclusions apart.
4. Bindings: `PUT /api/walls/{id}/playback`, `WallOut` carries the range,
   `art_display(action='set_playback')`, all within the description budget.
5. Tests, each seen red first: inclusive bounds and the tolerance at each edge,
   either bound alone, `any` clears, tallest > widest refused, an emptied wall
   publishes an empty feed and its summary says why, a range survives hanging
   another theme.

Files: `persistence/{records,sqlite,migrations,file}.py`, `programming/display.py`,
`programming/manifest/builder.py`, `http/{api,models}.py`, `mcp/{tools,bindings}.py`,
their tests, and `data-model.md` § Wall and § Rotation, `api-contract.md`.

### 02 — the client

The wall's *How it rotates* panel becomes *How it plays*, with a *Shapes*
row: presets (*Any shape*, *Portrait and square*, *Landscape and square*,
*Custom*), custom fields for widest and tallest in `W:H`, and the reported
screen's shape as a hint ("This screen is 16:9"). `EXCLUSION_WORDS` names the
new reason. When the shape leaves nothing, the card carries a warning at the
top, not only in the *Not showing* table: "The shapes you set leave nothing
from Winter to show, so this wall is dark."

Files: `http/static/screens/walls.js`, the browser tests and their payloads, the
Walls row in `information-architecture.md`.

**Visual change:** yes. Queue an operator-verification entry for the panel and
the dark-wall warning.

## Verification

Beyond the suites: run the curation plane against a copy of the catalogue, set
"widest 1:1" on a wall and read the published feed; then set a range that
matches nothing and confirm the feed has no works and Walls says why.

## Status

- [x] 01 — store, service, exclusion, API, MCP
- [x] 02 — the client
