---
artifact: build-plan
version: 1
scope: wave-4a-contract
branch: feature/wave-4a-contract
partition: serial — every chunk edits `contract/` and `tests/preferences/test_player_contract.py`, and 03's vectors read 01's shape
depends_on:
  - artifact: re-architecture
  - artifact: feeds-and-players
  - artifact: player-contract
governed_by:
  - artifact: feeds-and-players
    dispositions:
      - "ruling 3, a feed plus an optional control layer → conforms: 01 reshapes major 2 so a document with no wall-only key is a complete feed a channel could serve"
      - "ruling 4, each major at its own URL → conforms: 02 spells the per-major route and rewrites § The cutover to it"
      - "ruling 7, the feed carries only the mat colour; mode and width are the client's → conforms: 01 removes `settings.mat` (inches); a wall may name a mode, never a width"
      - "ruling 8, which facts an overlay shows is a setting in every layer → conforms: 01 adds it to `settings`"
      - "§ Reuse across platforms, layout and timeline as conformance vectors → conforms in part: 03 writes the mat-geometry and (feed, now) vectors wave 4 builds against; the label and overlay layout vectors wait for the first non-Pi Player, recorded as a decision below"
  - artifact: player-contract
    dispositions:
      - "a new major is breaking, a reader refuses a major it does not know and keeps what it has → conforms: major 2 is still a draft no reader acts on, and Arrt Player's suite keeps pinning its refusal of every major 2 fixture"
      - "schemas allow unknown keys; every invalid fixture breaks exactly one rule → conforms: the existing index test applies unchanged to every fixture this plan adds"
      - "every instant is RFC 3339 with an offset, backed by a pattern → conforms: no new instant field is added without the shared `instant` definition"
  - artifact: architecture
    dispositions:
      - "the manifest and content-addressed media are the only channel, and the Player makes only the requests `contract/routes.json` names (amended 2026-10-05) → conforms: 02 adds the per-major manifest route to `routes.json` itself, which is what the amendment says a new route is; `test_plane_isolation.py` reads that file, so the Player may request it from 4c on"
      - "the Library/Programming seam's four norms (in-transition) → inapplicable because this plan builds no Programming or Library code; 02's route change is in `http/`, serving the existing major 1 document"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ The mat is geometric (inch rule, bottom weighted, work-shaped mat, no upscaling) → conforms: 03's `proportional` vectors are derived from the server's compositor as it draws today, so the Player's port in 4d has a target that already holds the rule"
last_validated: null
---

# Build Plan — Wave 4a: the major 2 contract, settled

## What this plan is

The first of wave 4's seven plans (`re-architecture.md` § Order of work, row 4).
Major 2 was drafted in wave 1 and reshaped on paper by `feeds-and-players.md` on
2026-10-08, but the schema, fixtures and validator still carry the wave 1 draft:
mat width in inches, no mat mode, no overlay or facts settings, one manifest
route. Plans 4c (the Player's reader), 4d (its compositor) and 4e (the server's
builder) all build against this contract, and a Player must read the final shape
before the server switches, so the shape is fixed first and with no runtime code
behind it.

The owner's values for what was still open are already recorded (2026-10-08):
a three-day horizon and a twenty-minute preview default (server values,
`player-contract.md` § Settled before wave 4), and a relative mat of 6% of the
shorter side (`feeds-and-players.md` § Open questions). This plan carries the
6% into the layout spec, where it becomes a contract rule every Player computes
the same way.

**Not in this plan:** anything that serves or reads major 2 at runtime. Arrt
Player's reader is 4c, the server's builder 4e.

## Requirements Confidence

**Level:** Medium

**Why:** The shape is set by rulings, but several field spellings and defaults
are the builder's, and two of them (the label mode values and the route's
spelling) are read by both planes for as long as major 2 lives.

**Open assumptions / unknowns:**
- [ASSUMPTION: `scene` and `staging` stay optional keys of the major 2 document, absent from a channel's feed, rather than moving to a separate control route; a scene reaches the Player "as a republished feed" (`feeds-and-players.md` § Feed and control), and a separate route would be a second document to poll | MED impact | user can override]
- [ASSUMPTION: the per-major route is `GET /walls/{wall_id}/manifest/v{major}`, beside today's unversioned path, which keeps answering major 1 until 4g retires it | MED impact | user can override]
- [ASSUMPTION: `label_modes` becomes values from `none`, `caption` (static, burned in or on a separate label), and `overlay` (timed, with fades); a Frame reports no `overlay` | MED impact | user can override]
- [ASSUMPTION: presentation-setting keys are all optional in the feed, and a missing key means the Player's own default, so a channel can say nothing about presentation | LOW impact | user can override]

**What would raise confidence:** 01's reshaped schema read against
`feeds-and-players.md` § Presentation settings come in three layers, key by key,
before the fixtures are written.

`[DECISION: 03 writes only the vectors wave 4 builds against — mat geometry, and (feed, now) → what to show. The label and overlay layout vectors (regions, type sizes, opacity over time) wait for the first non-Pi Player | `feeds-and-players.md` § Reuse across platforms writes them "before a second platform ports" the Pi's label code, and wave 4 has one platform; vectors with no second implementation to disagree with would only restate the Pi's code | the builder's, 2026-10-08; user can veto]`

## Status

- [ ] Chunk 01: Major 2 as a feed with layered settings
- [ ] Chunk 02: Capabilities, the per-major route, and the cutover rewritten
- [ ] Chunk 03: The layout spec's mat rule and the schedule behaviour vectors

Context: branched from develop after #332. The owner's 2026-10-08 rulings
(horizon, preview, relative mat, the wave 4 split and its one household rule)
are recorded in the artifacts on this branch, committed with this plan.

### Chunk 01: Major 2 as a feed with layered settings

- **Surfaces:** `contract/schemas/manifest.v2.schema.json`;
  `contract/fixtures/manifest.v2/` and `contract/fixtures/index.json`;
  `tests/preferences/test_player_contract.py` (`semantic_errors`);
  `player-contract.md` § Major 2 (the table, the draft banner, the prose that
  names `settings.mat`).
- **What:** `settings` loses `mat` (inches; ruling 7) and gains, each optional:
  `mat.mode` (`none` | `proportional` | `full`), `label.mode`, `overlay`
  (`lead_seconds`, `tail_seconds`: shown for the first and last of a slot),
  `fade_seconds`, `text_scale`, `viewing_distance_m` (kept), and `facts` (which
  of the label's keys an overlay or caption shows, from the keys major 1's label
  carries). The document's description says which keys are the feed and which
  the control layer, and that a document carrying no control key is a complete
  channel feed.
- **Tests:** a valid channel-shaped fixture (no `scene`, no `staging`, no
  settings); an invalid fixture per new rule the schema states (unknown mat
  mode, a negative fade, a fact that is not a label key); the existing fixtures
  re-checked against the new shape, and any that named `settings.mat` rewritten
  with the change recorded in the index. Each new invalid fixture watched failing
  for exactly the rule its name gives.

### Chunk 02: Capabilities, the per-major route, and the cutover rewritten

- **Surfaces:** `contract/schemas/heartbeat.v1.schema.json` (`capabilities`);
  its fixtures; `contract/routes.json`; the server's manifest route
  (`arrt/src/arrt/http/player.py`) and `arrt/tests/contract/test_player_surface.py`;
  `player-contract.md` § The heartbeat, minor 2, and § The cutover.
- **What:** `capabilities.label_modes` takes the three values above.
  `capabilities.screen` is documented as reported when it changes, with
  Programming judging adequacy from the largest recent size (`feeds-and-players.md`
  § What a display reports it can do). `routes.json` gains
  `manifest_major`, `/walls/{wall_id}/manifest/v{major}`; the server mounts it now,
  answering `v1` with today's document and `404` for a major it does not build,
  so 4c's Player can request the highest major it reads against a real server.
  § The cutover is rewritten to ruling 4: each major is served while a heartbeat
  lists it, and the server retires major 1 once none does. The dated
  direction-changed banner goes, because the text it warned about is gone.
- **Tests:** the server's route test asserts `v1` answers the same bytes as the
  unversioned route and `v2` (not yet built) and `v0` answer 404, through the
  real server as that suite does. Heartbeat fixtures for each label mode and
  for an unknown one.

### Chunk 03: The layout spec's mat rule and the schedule behaviour vectors

- **Type:** cumulative-final
- **Surfaces:** new `contract/vectors/mat-geometry.json`; new
  `contract/vectors/schedule.json`; `tests/preferences/test_player_contract.py`
  (or a new sibling) holding the reference implementation of (feed, now) → what
  to show; `arrt/tests/` gaining a test that checks the `proportional` vectors
  against the server's compositor geometry; `player-contract.md` § Time and a new
  § Layout.
- **What:** **Mat geometry vectors:** inputs (screen pixels, pixel density or
  none, mat mode, work pixels, mat width and bottom weight where density is
  known), output (the work's rectangle and the mat's rectangle). Cases: each
  mode; with density (the inch rule) and without (6% of the shorter side, bottom
  weighted the same); a work smaller than its box (no upscaling); portrait,
  landscape, square, and a work of the screen's own shape. **Schedule vectors:**
  (feed, now) → the work to show, or dark, or the scene's work: inside a slot, in
  a gap, after the horizon (replay by one and by two horizons), across the
  clock-change fixture, a scene active, a scene expired, a held scene.
- **Tests:** the reference implementation runs every schedule vector in the
  root suite; the server's compositor reproduces every `proportional` vector
  with density, within one pixel; both are watched failing on a deliberately
  wrong vector. 4c and 4d run these same files from the Player's suite.

**Done when (whole plan):** all three suites, lint and format green;
`/prawduct:critic cumulative` over the branch with no blocking finding; the
change-log entry for `wave-4a-contract` written.
