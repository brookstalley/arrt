---
artifact: build-plan
version: 2
scope: wave-4f-scenes
branch: feature/wave-4f-scenes
base: develop
working-branches: []
partition: serial, one worktree. Three chunks; 02 builds on 01's service and both edit `arrt/src/arrt/programming/display.py`, and 02's client reads the API shape 02 itself writes, so there is nothing to hand a second builder. 03 is the operator's, at the wall.
depends_on:
  - artifact: re-architecture
  - artifact: feeds-and-players
  - artifact: player-contract
  - artifact: information-architecture
  - artifact: data-model
  - artifact: api-contract
  - artifact: architecture
  - artifact: labels-and-surfaces
governed_by:
  - artifact: player-contract
    dispositions:
      - "§ Scenes (a scene wins from `from` until `until`, or indefinitely when null; the wall returns on its own; one scene per wall, the same id in each wall's manifest; the Player respects its guardrails and reports the scene it is waiting on as not shown; keeping is not a Player concern) → conforms: 01 publishes exactly that object, and the Player already honours it (`arrt-player/src/arrt_player/programmes/schedule.py`, `what_to_show`). Keep is deferred (decision below), which the Player never sees"
      - "§ Staging (works to fetch and compose ahead; nothing is shown because of it; a Player may evict what nothing names once staging drops it) → conforms: 01 publishes the draft's works under `staging` on each pinned wall, and clears it when the scene goes live, because the scene then names them"
      - "§ Rules a schema cannot state, rule 1 (every work the schedule, the scene or staging names is a key of `works`) and rule 5 (a scene with an end time ends after it starts) → conforms: 01 adds the pinned and staged works' entries to `works` before writing, and `arrt/tests/feed_guard.py` validates every feed the suite publishes against `manifest.v2.schema.json` and `semantic_errors`, as it did for 4e"
      - "§ Time (absolute instants with offsets; half-open spans) → conforms: `from` and `until` are RFC 3339 instants in UTC, written by the same `_instant` the slots use"
      - "§ The heartbeat, minor 2 (`scene_id`, the scene the wall is showing or null) → conforms: 02 reads it from the stored heartbeat to say which walls a scene reached. No heartbeat change"
  - artifact: feeds-and-players
    dispositions:
      - "ruling 3 (a feed plus a control layer; a channel serves a feed with neither `scene` nor `staging`) → conforms: both keys are written only into a wall's private feed, by the one writer every publish path already uses"
      - "§ Presentation settings (three layers) → inapplicable because a scene changes what is shown, not how; it carries no settings"
  - artifact: re-architecture
    dispositions:
      - "§ Scenes (one object spanning walls; a lifetime of preview, hold or keep; it stays a pull; the UI stages before applying; a scene respects the Player's guardrails and the UI shows the wall as waiting) → conforms for preview, hold, staging, pull and waiting: 01 and 02. Keep → exception, recorded as a decision below: deferred until Programming has a pin or a playlist for a scene to become"
      - "§ Order of work, wave 4 row (4f: scenes, after the cutover, because `show_now` and `next` already become republishes in 4e and scenes have no place in the information architecture yet) → conforms: 4g is shipped, and the owner placed scenes on Walls on 2026-10-26 (Goals)"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer; MCP and HTTP are thin → conforms: every scene act is a `DisplayService` method, and 02's routes and tools each make one call"
      - "the manifest and content-addressed media are the only channel to a Player → conforms: a scene reaches a wall as two keys of the feed it already polls; nothing new is served"
      - "the Library/Programming seam, rules 1, 2 and 4 → conforms: a pinned work is read through the facade's `playable()`, the same call `show_work_now` makes, and it is refused with the same reasons"
      - "seam rule 3 (separate stores; in-transition, #216) → conforms with the interim rule: the scene and its pins are Programming's own tables, keyed by wall id and work id, with no cross-seam foreign key"
  - artifact: data-model
    dispositions:
      - "per-device runtime state never lives in the catalogue → conforms: whether a wall reached a scene is read from its heartbeat each time, never stored on the scene"
      - "derived artifacts are regenerated, never transported → conforms: a scene names works by id; the Player composes them as it composes a slot's"
      - "§ Scene (planned entity, wave 4) → conforms: 01 builds it as planned, less keep; 03 marks the entry built"
  - artifact: information-architecture
    dispositions:
      - "§ Direction (the *arr layout; navigation is a link, an act is a button) → conforms: the scene section's picks, Apply and Release are buttons, because they write; a wall's name in it is the link it is everywhere else"
      - "§ More than one wall (every act that changes a wall names which wall, in its control and its confirmation) → conforms: a scene is assembled per named wall, and Apply's confirmation lists the walls it will change"
      - "§ Boundaries (no editing of artwork metadata; no in-browser image editing) → conforms: a scene chooses works and nothing about them"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ The television belongs to whoever is using it (no unattended code presses a power key; nothing selects on a set not in art mode) → conforms: a scene is a feed the Player reads; the Frame driver's `get_artmode` guard runs before it selects, and the UI says the wall is waiting"
      - "§ Availability (the wall never goes black because the server is down) → conforms: a preview's `until` travels in the feed, so a wall returns to its schedule with the server gone; a hold with the server gone holds, as the contract says"
  - artifact: security-model
    dispositions:
      - "§ Direction (text from outside Arrt reaches the page as text) → conforms: a scene's only text is a work's label, already rendered as text everywhere; a scene has no free-text field (decision below)"
  - artifact: api-contract
    dispositions:
      - "the recorded versioning and error model for `/api` (internal, unversioned; `ServiceError` becomes the error envelope) → conforms: 02's routes follow the walls routes beside them, and the contract's route table gains their rows"
last_validated: 2026-10-26
---

# Build Plan — Wave 4f: scenes and staging

## What this plan is

The sixth of wave 4's seven plans (`re-architecture.md` § Order of work, the
wave 4 row), and the last before the repo split. Wave 4g retired manifest
major 1, so every wall reads a feed whose contract already carries the two keys
this plan is about: `scene`, a live override with a lifetime, and `staging`,
works to prepare ahead. The Player has honoured both since wave 4c, in doubles:
an active scene wins over the schedule, staged works are fetched and composed
with the rest, the Frame carries one pending upload per pass, and the heartbeat
reports the scene a wall is showing. **Nothing on the server writes either key,
and no screen offers them.** This plan builds that half.

**The owner's MVP (2026-10-26):** "the HDMI display on rpi and samsung frame
transitioning at the same time to related works that I pick manually." Two
walls, works chosen by hand, switching together. *Together* is what staging is
for: a Frame upload takes the better part of ten seconds and an HDMI
composition a fraction of one, so a scene applied without staging lands on the
two walls ten seconds apart. The owner also said this "is not as high of a
priority as just getting art, presentation, download, etc all working", so the
plan is kept lean: three chunks, one new section on one screen, and nothing a
later scene feature would have to undo.

**Not in this plan:**
- **Keep**, the third lifetime: a scene becoming ordinary Programming state.
  Deferred (decision below).
- A heartbeat field saying which staged works a wall has ready. The UI says
  the walls are preparing, and after Apply which walls reached the scene
  (tradeoff below).
- Scenes on a channel's public feed. A channel carries neither key
  (`feeds-and-players.md` ruling 3), and channels are wave 6+.
- The dark hours, power control, and anything that presses the set.
- A scene from the Work page ("show this on a wall now"). The owner chose the
  builder on Walls (2026-10-26); the Work page's act stays `show_now`.

## Goals

**Response taken:** ask, in one batch; the owner answered 2026-10-26.
1. Where a scene lives: **Walls, as a collection** ("yes walls, as a collection").
2. How it is assembled: **a builder on Walls where you pick a work per wall**
   ("yes the second"), not from the work's page.
3. Keep versus hold: the owner did not know the difference. Explained as: hold
   stays up until released and the wall then returns to its schedule; keep
   makes the scene the walls' ordinary programming with no scene in play. The
   owner did not rule; keep is deferred by the builder's decision below.
4. The twenty-minute preview default and the three-day horizon are **confirmed**
   as ruled 2026-10-08. The preview length is per scene (inference below).

Then, mid-turn: the MVP sentence above, which fixes the first user of this plan
as two walls on one Pi switching together to hand-picked works.

**Product:** the operator's case from `re-architecture.md` § Scenes: put three
Dalís next to each other in the living room and see what that looks like,
without writing a schedule and waiting. The brief's near-term is one household
with more than one wall; this is the first feature that treats the walls as
one room rather than one at a time.

**Architecture:**
- **The scene is Programming state, and the feed is derived from it on every
  write.** 4e made the published document the schedule's state, read back for
  a keep or a roll. A scene is not read back: the one feed writer asks the
  store for the wall's live scene and its draft's staging on every write, the
  way `_feed_settings` asks for the mat mode. That is what makes "every
  publish path carries a live scene" one function instead of a property of
  each path.
- **The Player is not changed.** If building the server shows the Player
  needs a change, that is a finding to record, not a chunk to add quietly.
- **Must stay possible:** keep, as a fourth act on a live scene; a scene named
  by an agent over MCP; a scene from the Work page; several live scenes on
  disjoint walls (the store allows it; only the UI assumes one).

**Constraints:**
- The contract as written: `scene` is one object per wall with `id`,
  `work_id`, `from`, `until`; `staging` a list of ids; rules 1 and 5. No
  contract change, no schema bump.
- The interim seam rule: no new cross-seam foreign keys, no new catalogue
  reads from Programming beyond `playable()`.
- The Frame's guardrails are the Player's and are not consulted by the server.

**Tradeoffs accepted:**
- **No "ready" signal before Apply.** The heartbeat does not say which staged
  works a wall has composed or uploaded, so the UI cannot promise the switch
  will be simultaneous; it says the walls are preparing and, after Apply,
  which walls reached the scene. A Frame has its upload done within about
  fifteen seconds of the pin (one pending upload per one-second pass), which
  is less than the time a person takes to pick a second work. Revisit with a
  heartbeat minor if the walk in 03 shows the walls landing apart. Not
  backlogged until measured.
- **One live scene at a time, in the UI.** The builder holds one draft and
  Walls shows one live scene. The store does not enforce it (a scene is rows
  keyed by scene id; pins by scene and wall), so a second concurrent scene is
  a UI change, not a migration.
- New tables go into the shared SQLite file until #216 splits the store, so
  that split moves two more tables.

**Open assumptions** (each the builder's inference, not the owner's ruling):
- *Inferred:* a scene has no name and no free text. It is identified by its
  works and its walls, and Walls shows it as "Scene: {work} on {wall}, {work}
  on {wall}". A name is a field to add later, never to remove. [LOW impact |
  user can override]
- *Inferred:* the preview length is chosen per scene when it is applied, from
  a short list (5, 20 and 60 minutes; 20 the default), not typed. [LOW impact
  | user can override]
- *Inferred:* applying a scene while another is live ends the other. Two
  scenes on the same wall is what the contract's "one scene per wall" forbids,
  and the MVP has two walls and one person. [LOW impact | user can override]
- *Inferred:* a pinned work must be displayable and not kept off every wall,
  judged exactly as `show_work_now` judges it, and a scene is refused by name
  for a wall whose pin fails. It is not judged against the wall's shapes:
  shapes filter a theme's cycle, and a scene is the curator's own hand. [MED
  impact | user can override]
- *Inferred:* `Skip` and `Show now` on a wall with a live scene republish the
  schedule beneath it and change nothing on the wall until the scene ends;
  the Walls card says so beside the control rather than hiding the control.
  [LOW impact | user can override]
- *Inferred:* a scene's end, by expiry or release, is a republish of each
  pinned wall keeping the slot on it now, so the schedule resumes where it
  would have been, not from the top. [LOW impact | user can override]
- *Inferred:* the wall's History records a scene applied and a scene ended
  as events, since History is where "why did the wall change" is answered
  (`build-plan-walls-work-and-trust.md` Chunk 03). [LOW impact | user can
  override]
- *Inferred:* the draft's staging is written only to walls the draft pins,
  and the draft is forgotten (its staging cleared) when it is discarded or
  when its scene ends. [LOW impact | user can override]

`[DECISION: keep, the lifetime that turns a scene into ordinary Programming state, is not built in 4f; preview and hold are | the contract makes keep "pins or a playlist" (player-contract.md § Scenes; re-architecture.md § Scenes), and Programming has neither today: the per-wall pin retired with the directive in 4g and playlists beyond a hung theme are wave 6+, so keep would have to invent the state it keeps into; hold covers the owner's case (a scene that stays until they say), and keep is one act on a live scene when its target exists | the builder's, 2026-10-26; user can veto]`

`[DECISION: the scene and its staging are derived from the store at every feed write, by the one writer, rather than carried in the published document and read back as the schedule is | a scene missing from any one publish path (a roll, a withdrawal, a mat patch, a neighbour's rebuild) would silently take a live scene off a wall mid-preview, and a property over every caller is harder to hold than one lookup in one function; the schedule is read back because its stability rule needs the previous document, which a scene does not | the builder's, 2026-10-26; user can veto]`

**Decisions made mid-build:** *(appended while building; one line each, naming
what settled it)*
- 01: every act patches its walls (`_patch_v2_works`) rather than republishing them keeping the slot, so pin, apply and release move no slot at all. Settled by the plan's own goal for a scene's end ("the schedule resumes where it would have been"), which a patch meets exactly and a rebuild only approximately.
- 01: the funnel is a new `_publish_feed`, the one function that spells and writes a feed; `_write_v2` and `_patch_v2_works` hand it a schedule. The plan's `_control_layer(wall_id)` is called there and nowhere else. Settled by the plan's decision that the control layer is derived in one writer.
- 01: `Published.works` reads back only the schedule's works; the scene's and staging's entries are `control_works`, and `carried` is both. Otherwise a staged work would join the wall's cycle on its next rebuild and make two walls look like they share works. Settled by "do it right": the 4e read-back meant the schedule's works, and a control-layer work is not one.
- 01: withdrawal, reconciliation and the showings record consider every carried work, so a pinned work kept off every wall or archived leaves a live scene at once, and a wall showing its scene keeps a showing. Found while reading `exclude_work`; the plan did not name these paths.
- 01: `draft_scene` returns the draft being assembled if there is one. Settled by the plan's "the builder holds one draft".
- 01: History events for a scene applied and ended move to 02, with their rendering in `activity.js`. A kind recorded before the client can name it shows as "Something the history records as …". Alignment-pass miss: the plan's inference put History in the plan, not in a chunk.
- 01: a pin is refused for a wall with no feed, by name, as show now is. Inferred; the plan was silent.
- 01: the data model's Scene entry is marked built at 01 rather than 03, because the tables exist now and the entry describes stored state.
- 01, after its review: ending a scene has one owner (`_end`), used by release, replacement and expiry; only the newest draft stages (`_current_draft`), matching what the builder shows; pin, unpin and discard log `scene.staged`, `scene.unstaged` and `scene.discarded`; expiry bookkeeping on the heartbeat sits behind a bulkhead so it never costs the roll; `Published` no longer parses the scene and staging back, since nothing reads them and a malformed one hid the whole feed.
- 01, accepted: `Published.works` keeps its name though it now means the schedule's works. Its docstring says so, `carried` is beside it, and every reader in `display.py` was re-read. `judge_sizes` judging only scheduled works is deliberate: too-small speaks for what a theme puts up, and a scene is the curator's own hand, as the shapes inference above says of shapes.

**01's mutation sweep (Done when 6)**, `arrt/tools/mutation_sweep.py` over `tests/unit/test_scenes.py` and `tests/unit/test_major_2_feed.py`, 2026-10-26. Each mutation matched once and the base run collected and passed.
- *First pass, 24 mutations:* the funnel (scene, staging, control works dropped), the control layer (expired counted live, other walls' pins or staging, kept-off or refused works not dropped, latest-applied tie-break), `keep_showing`, reconciliation and withdrawal reading only scheduled works, Apply not ending others, settle doing nothing, `status_at` ignoring `until`, `as_document`'s works, scene key, staging key and hold's null `until`, the read-back filter, the pin's feed check and Apply's recheck. 23 caught. The survivor, the latest-applied tie-break, is unreachable through the service, since Apply ends every other live scene; a store-built case now catches it and its twin in `live_scene`.
- *After the review, 11 mutations:* the heartbeat bulkhead, single-draft staging, the newest-draft pick, the honest withdrawal line, each new event and the replaced scene's event, Apply's walls, and the Feed's rule 5 and widened rule 1. 10 caught. The survivor, the withdrawal line, survived because the test looked for the work's id and the mutated line names none; the assertion now refuses any such line, and it is caught.

**Level:** Medium. The contract fixes both keys and the Player already reads
them, so what the feed must say is not in doubt. What is: whether every
publish path can be made to carry the scene through one writer without
special cases, which `_patch_v2_works` (it rewrites the document from
`Published`) and `_rebuild_beside` may resist. *What would raise it:* 01 begins
by listing every function that writes a wall's v2 file, derived from the
code, and makes each one call the same `_control_layer(wall_id)` before
writing anything else.

**The feed writers** (derived 2026-10-26 from `display.py`; 01 re-derives it
and corrects this table if it has moved):

| Writer | Reached from | What it must carry |
|---|---|---|
| `_write_v2` | `_sync_v2` (hang, re-hang, selection, reconcile), `_rebuild_v2` (restart, withdraw, roll), `_rebuild_beside` | the wall's live scene and its draft staging, with their works in `works` |
| `_patch_v2_works` | `_reconcile_v2` (a work re-rendered or re-coloured) | the same; today it rewrites from `Published`, which does not hold them |

*(01, as built: both writers hand a schedule to `_publish_feed`, which adds the
control layer and is the only function that spells a feed.
`tests/unit/test_scenes.py` derives the writers from the source and drives
each publish path through them.)*

## Scaffolding

No new project, dependency or tool. The curation suite (`cd arrt && uv run
pytest`), its browser marker for 02, and the root suite's contract tests
(`tests/preferences/test_player_contract.py`, which validate every fixture the
server publishes) are the whole harness.

### Verification Strategy

Beyond the suites: after 02, run the real Player from `develop` on this Mac
against a local server from this branch, with the suite's Frame double and an
HDMI double, and watch a scene staged, applied and released reach both walls
(the step 4e's Chunk 02 took). Then 03, on the wall, with the operator.

## Build Chunks

### Chunk 01: The scene in the feed

- **Critic mode:** final. The writer design is the keystone 02 builds its
  screen on, and "every path carries the scene" is where it can be wrong.
- **Surfaces:** `arrt/src/arrt/persistence/sqlite.py` and
  `arrt/src/arrt/programming/store.py` (two tables, `scenes` and `scene_pins`,
  gained by an older file when opened; the questions below);
  `arrt/src/arrt/programming/display.py` (`DisplayService`: `draft_scene`,
  `pin_scene`, `unpin_scene`, `discard_scene`, `apply_scene`,
  `release_scene`, `live_scene`, and the one control-layer lookup every
  writer calls); `arrt/src/arrt/programming/manifest/v2.py` (`Feed` gains
  `scene` and `staging`; `as_document` spells them; `Published` reads them
  back only so a test can assert what was written); the tests for each; one
  log event per act (`scene.applied`, `scene.released`, `scene.expired`,
  each naming the walls) in the shape `_log_published` uses.
- **The questions the stored scene must answer** (a persisted format, so
  these come before fields): which scene is live now, and until when or
  whether it holds; which walls it pins and to which work; whether a scene
  is still a draft, and what its draft stages on each wall; when it was
  applied and ended, so History can say so. Two tables answer all of them: a
  scene (id, status of `draft`, `live` or `ended`, lifetime of `preview` or
  `hold`, `from`, `until`, `created_at`, `ended_at`) and its pins (scene id,
  wall id, work id).
- **What:** a draft is created empty. Pinning a work to a wall writes the pin
  and republishes that wall keeping its slot, so its feed stages the work;
  unpinning does the reverse. Apply sets `from` to now and `until` to now plus
  the chosen minutes (or null for hold), marks it live, ends any other live
  scene, and republishes every pinned wall with `scene` set and `staging`
  cleared. Release ends it now and republishes. Expiry is observed, not
  scheduled: the Player returns to the schedule at `until` on its own, and
  the server needs no timer to match it. A preview whose `until` has passed
  is not live: `live_scene` says `ended` the moment it passes, so Walls never
  shows an expired scene as live, and the wall's next feed write, whenever
  one comes, publishes without it. The expired object left in the feed until
  then is contract-valid (rule 5 holds) and the Player ignores it.
- **Done when:**
  1. Every feed the suite publishes still passes `arrt/tests/feed_guard.py`
     (the schema and `semantic_errors`), with a scene and with staging.
  2. Each feed writer is tested to carry a live scene and a draft's staging.
     The list of writers is derived from the code, not from this plan, and
     the test is parametrised over it.
  3. A pin to a wall stages the work in that wall's feed and no other's;
     Apply puts the same scene id in every pinned wall's feed with `from`
     before `until`; Release and an expired preview both leave the next feed
     without a scene, keeping the slot on the wall now.
  4. A pin of a work the Library refuses, or one kept off every wall, is
     refused with `show_work_now`'s reason, and the draft is unchanged.
  5. Applying while another scene is live ends it, and its walls' next feeds
     carry the new scene or none.
  6. Mutation sweep over the control-layer lookup and `as_document`'s two new
     keys, each survivor explained.

### Chunk 02: Scenes on Walls, over HTTP and MCP

- **Type:** cumulative-final
- **Visual change:** yes
- **Surfaces:** `arrt/src/arrt/http/api.py` (`POST /scenes` makes the draft;
  `PUT /scenes/{id}/pins/{wall_id}` and its `DELETE`; `POST /scenes/{id}/apply`
  with `{lifetime, minutes}`; `POST /scenes/{id}/release`; `DELETE /scenes/{id}`
  discards a draft; `GET /scenes/live` the live scene or the draft with, per
  wall, the work, and whether the wall's last heartbeat reports this scene);
  `arrt/src/arrt/mcp/bindings.py` and `arrt/src/arrt/mcp/tools.py` (the same
  acts as thin tools, so an agent can say "show these three on the two
  walls"); `arrt/src/arrt/http/static/screens/walls.js` (a **Scene** section
  above the wall cards: one row per wall with a work picker, *Apply* with the
  preview length or *Hold*, and once live, each wall's work and whether it
  reached the scene or is waiting, with *Release*; on a wall's card, one line
  naming the scene's work while one is live, beside *Skip*); the picker
  searches held works through `GET /api/works` with `q` and the held status
  (the listing Artworks already reads), and lives in `core/` if a second
  screen will need it, else in `walls.js`;
  `.prawduct/artifacts/information-architecture.md` (the Walls row of the
  screen inventory, the hierarchy and the screen states);
  `.prawduct/artifacts/api-contract.md` (the route rows); browser tests under
  `arrt/tests/browser/`.
- **The words** (so the walk can judge them, and `test_copy_says_it_once.py`
  can hold them): "Preparing the walls" while a draft stages; "{wall} is
  showing it" and "{wall} is waiting for the television to be free" from the
  heartbeat's `scene_id` and `display_state`; "Scene until {time}" or "Scene,
  held until released"; the confirmation before Apply names each wall and its
  work, as hanging names the wall.
- **Done when:**
  1. The browser suite drives the flow: pick a work for each of two walls,
     Apply as a preview, see both walls listed with their works, Release,
     see the section empty. A draft refused for one wall shows the reason
     beside that wall and keeps the other pin.
  2. Each route and each tool is one service call, tested through the
     service's own errors (a refused pin, a release with nothing live).
  3. `GET /api/walls` is unchanged in shape; the scene line on a card comes
     from the live scene read, not from the wall.
  4. **End to end:** the real Player on this Mac, pointed at a local server
     built from this branch with a Frame double and an HDMI double, stages
     on a pin, switches both doubles on Apply, reports the scene id in both
     heartbeats, and returns both to their schedules on Release and at a
     preview's expiry. Recorded in the change log with what was observed.
  5. The IA rows and the api-contract rows say what was built. The
     operator-verification entry for 03 is written. Then, committed, the one
     `/prawduct:critic cumulative`, and `/prawduct:pr create` when asked.

### Chunk 03: On the wall

The operator's, with both walls up and the Frame in art mode, from the
operator-verification entry 02 writes. It claims no branch and is ticked in
whichever PR follows the walk.

- Pick a work for the HDMI wall and one for the Frame; watch the journal log
  the Frame's upload before Apply. Apply as a five-minute preview, and time
  the gap between the two walls changing. The tradeoff above expects under
  two seconds; a gap near ten means the Frame was not staged, and that is a
  defect in 01 or 02, not in the Player.
- Switch the Frame to a programme, apply a scene, and see Walls say the
  Frame is waiting; switch back and see it reach. This is the first time the
  display state's `in_use` is seen on the set rather than a double
  (`samsung-tv-state-findings.md` § What is still owed, item 6). If the
  reading is wrong, that is #309's Chunk 05 finding, named here so it is not
  lost.
- Let a preview expire with the server stopped (`docker stop` on the NAS, or
  the local server), and see both walls return to their schedules on their
  own; start the server and see Walls agree.
- Hold, then Release, and see both walls resume where their schedules were.

## Early Feedback Milestone

**Milestone chunk:** 02
**What the user can do:** on Walls, pick a work for each wall, apply the scene,
and watch both walls change.

## Governance Checkpoints

**Commit & PR cadence:** commit per chunk after its review. 01 declares
`Critic mode: final`, so this is not a short plan: 01 is reviewed before 02
builds its screen on the writer, and 02's review is the one
`/prawduct:critic cumulative` that makes the branch PR-ready. One PR to
`develop`, as the other wave 4 plans shipped.

- After 01: confirm every writer carries the scene through one lookup, with
  no path special-cased, before any screen reads it.
- After 02 (cumulative): the full bundle, and the end-to-end record in the
  change log.

## Status

- [ ] Chunk 01: The scene in the feed
- [ ] Chunk 02: Scenes on Walls, over HTTP and MCP
- [ ] Chunk 03: On the wall

Context: branched from `develop` at v0.6.0 (`a0e2a5f4`), 2026-10-26. No other
plan is live.
