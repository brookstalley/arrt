---
artifact: build-plan
version: 1
scope: shown-record
branch: feature/ux-second-walk
partition: serial, one worktree. 02 and 03 both read 01's store methods, and 02 and 03 both edit `http/api.py`, `http/models.py` and `mcp/bindings.py`
depends_on:
  - artifact: data-model
  - artifact: api-contract
  - artifact: player-contract
governed_by:
  - artifact: data-model
    dispositions:
      - "§ Direction (per-device runtime state never lives in the catalogue) → conforms, an interpretation recorded here: a showing names a wall (a place) and a work, never a display, client or screen. It survives replacing the television, which is the test that norm gives. § Wall's forbidden list (last-heartbeat among it) binds the Wall table, and this is a table of its own"
      - "§ Direction (identity is never a source URL; a work is distinct from an image) → inapplicable because the record holds Library work ids only"
      - "§ Direction (derived artifacts are regenerated, never transported) → inapplicable because a showing is an observation, not a render"
  - artifact: architecture
    dispositions:
      - "§ Direction (operation logic lives only in the service layer) → conforms: 03 moves the Artworks narrowing out of `http/api.py` into a composer under `services/`, so the HTTP and MCP bindings call one thing"
      - "§ Direction seam rule 1 (one-way imports through a facade) → conforms: Programming writes and reads the record and hands out opaque ids; the composer meets them with the Library's as sets"
      - "§ Direction seam rule 3 (separate stores, no cross-seam foreign keys; in-transition, #216) → conforms: the table is Programming's, reached only through `ProgrammingStore`, and `work_id` is an opaque reference with no foreign key, like `history_events`"
      - "§ Direction seam rule 4 (Library changes reach Programming as events) → inapplicable because the record is written from a Player's report, not from a Library change"
      - "§ Direction (the manifest is the only channel from curation to display) → conforms: the record reads the heartbeat channel and sends nothing to a Player"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ Direction (the display plane never depends on the curation plane) → conforms: the Player's heartbeat posting is unchanged, and a refused or failed record write never fails the heartbeat route"
      - "§ Direction (spend ceilings by the provider) → inapplicable because nothing here spends"
  - artifact: information-architecture
    dispositions:
      - "§ Direction (the *arr layout) → conforms: the facet is one more rail group on Artworks, and nothing moves"
      - "§ Direction (navigation is a link, an act is a button) → conforms: facet options are the rail's existing controls"
last_validated: null
lifecycle: completed
archived: 2026-10-16
released_in: v0.5.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan: what each wall has shown (#316)

## What this plan is

A durable log of what each wall has shown, written from the heartbeat, and
the three reads the owner named on it: Walls' last-shown work and next three,
and the Artworks facets "Never shown" and "Not shown since…". The last two
upgrade #288's *Not on any wall*.

`build-plan-ux-second-walk.md` chunk 04 (#354) draws Walls on the read that
chunk 02 here serves. That chunk waits on this plan (the owner's ruling,
2026-10-14), and the two plans share the branch.

## Goals

- **Response taken:** proceed, on the owner's rulings and answers.
  - #316's rulings of 2026-10-14:
    - Walls reads this record, and it is built first.
    - Its source is the heartbeat's `display_state` `showing_art`, now,
      without waiting for #309.
    - Its scope is the record, Walls' last-shown work and next three, and the
      Artworks facets.
  - Answered by the owner on 2026-10-15, asked as the persisted-format
    question:
    - **A log of showings**, one row per showing, not a first/last summary
      per wall and work. Asked with the cost stated: about 480 rows a day per
      wall at the 3-minute default, about 175k a year, and nothing pruned.
    - **"Not shown since…" offered as fixed periods**, a single choice in one
      rail group with a count on each option: *Never shown*, *Not in the
      last month*, *Not in 3 months*, *Not in a year*. Each period includes
      the never-shown works. *Not on any wall* stays, because it answers
      "hung now", a different question.
- **Product:** a curator cleaning up (scenario S9) finds the works that never
  reached a wall, or have not been up for a while. Someone at a dark screen
  sees what was last on it and what is coming. A household can later ask
  "what was on the living-room wall at dinner on Tuesday?". The log keeps that
  answer from now on, and no surface asks it yet (Q57 below).
- **Architecture:**
  - The record belongs to Programming. It lives in its store, behind
    `ProgrammingStore`, and works are opaque ids in it.
  - Bindings never compose across the seam themselves. A composer under
    `services/` does it, and both surfaces call that composer.
  - **What must stay possible:**
    - #309 later feeds the same record from display state reported on change.
      The writer takes a reported state, not a heartbeat file, so #309 adds
      a caller and changes no write path.
    - #216's store split moves the table with Programming's others.
- **Constraints:**
  - The heartbeat route stays the Player's: a record that cannot be written
    is logged, never a refused heartbeat. The display plane must not depend
    on curation's bookkeeping.
  - Times come from the Player's own report (`display_state.since`,
    `reported_at`), as every heartbeat reader here already takes them.
  - The MCP list reaches parity with Artworks. `art_catalogue(action='list')`
    has neither of #288's filters (`fit`, `not_on_wall`), which is a gap in
    the built product found while planning. Chunk 03 closes it, per "no
    pre-existing exception".
- **Tradeoffs accepted:**
  - Until #309's Frame half lands, a Frame's record can be up to 60 s late,
    and wrong after a remote-control change (ruling 2). An HDMI wall already
    reports on change (#309's comment of 2026-10-08).
  - The log is unbounded: nothing prunes it. Worth revisiting if the
    catalogue file's size reaches the health panel's attention, or if a
    query over it is measured past 50 ms. Not backlogged, because it may
    never matter.
- **Inferred (not ruled by the owner):**
  - **A showing is identified by its wall, its work, and the controller's
    `since`.** The Player resets `since` whenever the state or the work
    changes (`DisplayReport.moved_to`). A re-sent heartbeat therefore
    extends its showing rather than adding one, and a work shown, taken off
    and shown again is two showings. A Player before minor 3 has no `since`.
    Its showing is the run of consecutive reports naming one work, each
    within `STALE_AFTER_SECONDS` of the last, and it starts at the first
    report's `reported_at`.
  - **A showing ends when the wall next reports anything else**, at that
    report's `since` (minor 3) or `reported_at` (before it). Until then its
    end is unknown, and `last_seen_at` says how far it is known to have run.
  - **"A work the manifest never sent" means a work absent from the wall's
    published feed's `works` at the moment the heartbeat arrives.** Such a
    report is not recorded, and is logged. A sync keeps the work on screen
    in its new feed (`_write_v2`), so the case this loses is a work shown
    for its last seconds after a curator removed it, which costs at most one
    slot. Checking every feed the wall was ever sent would need a second
    record.
  - **"Ignores a heartbeat from an unassigned client"** is already the route's
    admission (`_admitted_to_the_wall`), so the acceptance is a test through
    the route, not new code.
  - **Last shown on Walls is the wall's latest showing**, whatever the screen
    is doing now. Chunk 04 of the other plan decides when to draw it.
  - **"Not in the last month" is 30 days, "3 months" 90, "a year" 365**,
    counted back from the moment of the request. A curator's "month" is not
    calendar arithmetic.
  - **A showing on a wall since deleted still counts.** The work was shown.
    There is no foreign key to a wall (as with `history_events`), and a wall
    is never named by the facet.
- **Decisions made mid-build:**
  - [DECISION, 01: the rules live in a pure module, `programming/showings.py`,
    and `DisplayService` only feeds it the latest showing and the feed] Settled
    by the architecture goal that the writer takes a reported state, so #309
    adds a caller, and by `display.py`'s size.
  - [DECISION, 01: a showing never starts before the one it follows ended, and
    a report older than the latest sight changes nothing] Settled by "a wall
    shows one thing at a time", which makes `(wall_id, started_at)` the key.
    Both cases are a controller contradicting itself, or a report arriving
    late, and a later report of the moved showing still extends it.
  - [DECISION, 01: the two new log lines are structured events,
    `showings.not_recorded` and `showings.not_in_feed`, in
    `observability-strategy.md`'s table] Matched to the picture store's events
    (`extra={"event": …}`), which are the product's way of naming a line.
  - [DECISION, 01: verified through the booted-server contract test, which
    posts a real heartbeat over HTTP, rather than by hand against the dev
    server] The dev server reads the operator's `.env`, whose art root is real
    data. The contract test is the same wire, and it is repeatable.
  - [DECISION, 01, from its review: the showing write is a bulkhead, a broad
    catch waived in place, logged as `showings.not_recorded`] The store
    translates only a refused row into `StorageError`, so a full disk refused
    the Player's heartbeat with a 500, and skipped the horizon roll after it.
    Catching the driver's error by name is forbidden above the persistence
    package (`test_persistence_boundary.py`), and any failure of the record,
    a bug in its rules included, must leave the roll running. Pinned through
    the route with the driver's own error.
  - [DECISION, 01, from its review: `keep_showing(wall_id, reported, at=)` is
    the writer, and the heartbeat is one caller] So #309 adds a caller and
    changes no write path, as the architecture goal asks.
  - [DECISION, 02: the field is `upcoming`, not the plan's `next`, and each
    entry says `starts_at`] `next` shadows a Python builtin in both bindings,
    and `from` is a keyword. The ia-proposal's words, "the next three", stay
    the Walls page's copy.
  - [DECISION, 02: `upcoming` reads the published feed, whatever hangs] The
    feed is what the Player plays, so a wall taken down whose feed still
    carries slots shows them. Settled by the plan's "from the published
    schedule".
  - [DECISION, 03: `work_ids_shown(since=)` is replaced by
    `last_shown_by_work()`, a map from each work to its latest sight] The
    composer needs the instants to count four periods from one read, and a
    method read only by tests would be dead code. Chunk 01's tests now assert
    the instants, which is stronger than the sets they asserted.
  - [DECISION, 03: the periods are 30, 90 and 365 days, named `month`,
    `quarter` and `year`] The owner chose fixed periods on 2026-10-15; the
    day counts are the inference already listed under Inferred. The rail says
    "Not in the last month", "Not in 3 months" and "Not in a year".
  - [DECISION, 03: the period edge is inclusive: a work last seen exactly 30
    days ago was shown in the month] "Not in the last month" excludes what was
    up within it, to the second. Pinned by `test_works_filter.py`.
  - [DECISION, 03: *Last shown* is drawn once some option counts fewer than
    the filter's total, or one is chosen] The same rule as *Not on any wall*:
    before any wall has shown anything, every option selects every work.
  - [DECISION, 03: #288 is closed, so its scope-out line is not edited] The
    supersession is recorded here and in `api-contract.md`'s `GET /api/works`
    row, which is where a reader of that facet looks.
- **Level: High.** The source exists and is parsed today
  (`display_state.reported_state`), the store has a precedent for
  heartbeat-derived rows (`reported_screens`), and the facet composition has a
  precedent (`not_on_wall`).

## What the data must answer

Enumerated before any field, as a persisted format requires. Each becomes a row
in `data-model.md` § What this data must answer.

| # | Question | Asked by |
|---|---|---|
| Q53 | Which work did this wall show last, and until when, whatever its screen does now? | Walls (#354, ruling 3 of 2026-10-11), and its MCP twin |
| Q54 | Has this work ever been shown on any wall? | Artworks' *Never shown* |
| Q55 | Which works has no wall shown since this instant? | Artworks' *Not in the last month / 3 months / a year* |
| Q56 | When, and on which walls, was this work last shown? | Not asked yet. A work's page would ask it, and the record must not prevent it |
| Q57 | What was this wall showing at this instant? | Not asked yet. A wall's History, or "what was that painting?" |

## The record: Showing

A sketch, which chunk 01 settles and `data-model.md` records:

| Field | Type | Answers |
|---|---|---|
| `wall_id` | UUID, not a foreign key | Q53, Q56, Q57 |
| `work_id` | UUID, not a foreign key, opaque | Q54–Q57 |
| `started_at` | datetime | Q57; the identity, with the two above |
| `last_seen_at` | datetime | Q53 (until when, while unended), Q55 |
| `ended_at` | datetime, nullable | Q53, Q57 |

Primary key `(wall_id, started_at)`, because a wall shows one thing at a time.
Indexed on `(work_id, last_seen_at)` for Q54–Q56. The latest row per wall is
Q53, read through the primary key.

## Chunks

### Chunk 01: the log of showings, written from the heartbeat

- **Type:** code. **Critic mode:** final. This is the keystone, a persisted
  format, and it is reviewed before anything reads it.
- New table `showings` in the store schema (`arrt/src/arrt/persistence/sqlite.py`), with its
  methods on `ProgrammingStore`:
  - record a reported state against the wall's open showing;
  - the wall's latest showing;
  - the ids of works shown, optionally since an instant.
- `DisplayService.record_heartbeat` feeds it the heartbeat's reported state
  (`display_state.reported_state`), after the file is written. The writer's
  failure is logged under its own event name and does not refuse the
  heartbeat.
- Trust rules: a work not in the wall's published feed, and a `showing_art`
  that names no work, record nothing. Every other state closes the open
  showing.
- `DisplayService` reads: `last_showing(wall_id)` and
  `last_shown_by_work()` (each work's latest sight; chunk 03 replaced
  `work_ids_shown(since=)`, which only it read), ids opaque as `work_ids_on_walls` returns
  them.
- **Records:**
  - `data-model.md`: the Showing entity, with Q53–Q57 in § What this data
    must answer.
  - `architecture.md`: the inventory of Programming's tables, wherever it
    lists them.
- **Tests (service and store, real SQLite):**
  - a re-sent heartbeat extends a showing, and a new `since` starts another;
  - the same work shown twice makes two showings;
  - a pre-minor-3 run is joined, and a report later than `STALE_AFTER_SECONDS`
    splits it;
  - another state ends the open showing at its `since`;
  - a work outside the feed is not recorded, and neither is a foreign picture;
  - the record survives reopening the store;
  - an unassigned client's heartbeat is refused at the route and records
    nothing;
  - a failing store write still answers the heartbeat 204.

### Chunk 02: Walls' read: the last-shown work and the next three

- **Type:** code.
- `WallOut` gains:
  - `last_shown`: the work id, `started_at`, and `until` (`ended_at`, else
    `last_seen_at`), or null when the wall has shown nothing;
  - `next`: up to three upcoming slots from the published schedule
    (`Published.on_the_wall` and its successors), each a work id and when it
    starts.
- Both are served on the MCP walls read too (`test_surface_parity.py`).
- **Records:** `api-contract.md`'s `GET /api/walls` row. Additive.
- **Tests:** contract tests on both fields, over both surfaces:
  - a dark wall with a past showing;
  - a wall never shown;
  - a horizon with fewer than three slots left;
  - a wall with nothing hung.

### Chunk 03: Artworks' *Last shown* facet, and MCP parity for the clean-up facets

- **Type:** code. **Visual change:** yes.
- The narrowing moves from `http/api.py` (`_Narrowing`, `_narrowing`) into a
  composer under `services/`, which both bindings call. It gains:
  - `shown=never|month|quarter|year`, a single choice, refused by name when
    it is anything else;
  - each option counted over every other filter but its own, as `fit` and
    `not_on_wall` already are.
- `art_catalogue(action='list')` takes `fit`, `not_on_wall` and `shown`, and
  returns their options.
- The Artworks rail draws a *Last shown* group. The address carries the
  choice, so Back and Forward keep it, as the other filters already do.
- **Records:**
  - `api-contract.md`'s `GET /api/works` row: drop "Which works a wall has
    *shown* is not recorded".
  - `information-architecture.md`'s Artworks row, if it lists the rail's
    groups.
  - #288's scope-out line, which this plan supersedes.
  - `work_ids_on_walls`'s docstring: drop "Not what a wall has shown… this
    does not pretend to", which this record now answers elsewhere.
- **Tests:**
  - a contract test over both surfaces;
  - a browser test choosing each option, with counts that move with another
    filter;
  - a never-shown work in every period, and a recently shown work in none.

## Verification strategy

- Chunk 01 is exercised through the booted-server contract test, which posts a
  real heartbeat over HTTP the way a Player does (§ Decisions: not by hand
  against the dev server, whose art root is the operator's real library).
- Chunk 03 is seen in the browser on a library with a few seeded showings,
  through `ux_walk.py`'s Artworks capture.
- The owner's NAS deployment is the first real feed. One HDMI wall reports on
  change, so the owner's first look at *Never shown* is a real reading within a
  day of deploy.

## Done when (every chunk)

1. The chunk's tests pass, each new one seen red against the unfixed code or a re-break. The curation suite and the root suite pass, plus `-m browser` for chunk 03.
2. `/prawduct:critic` run (`final` for 01 as declared; inferred after), blocking findings resolved.
3. Committed, the box below ticked, #316 and #288 updated.
4. Chunk 03 enqueues its rail in `.prawduct/operator-verification.md`.

## Status

- [x] Chunk 01: the log of showings, written from the heartbeat
- [x] Chunk 02: Walls' read: the last-shown work and the next three
- [x] Chunk 03: Artworks' *Last shown* facet, and MCP parity for the clean-up facets
