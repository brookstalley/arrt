---
artifact: build-plan
version: 1
scope: wave-2b-seams-and-http
branch: feature/wave-2b-seams-and-http
partition: serial — Chunk 02 builds on Chunk 01's packages, 03 serves what 01 and 02 publish, and 04 pulls what 03 serves
depends_on:
  - artifact: re-architecture
  - artifact: player-contract
  - artifact: architecture
  - artifact: data-model
  - artifact: security-model
  - artifact: api-contract
  - artifact: observability-strategy
governed_by:
  - artifact: architecture
    dispositions:
      - "the Library/Programming seam norms 1, 2 and 4 (in-transition; migrate in wave 2) → this plan IS their migration. Chunk 01 does rules 1 and 2 and adds the import guard; Chunk 02 does rule 4 with its reconciliation duty. Rule 3, the store split, stays wave 3 by the recorded schedule"
      - "operation logic lives only in the service layer; HTTP handlers are thin bindings → conforms: Chunk 03's routes unpack, call one Programming service method and format. Token checking is a dependency the router applies, not logic in a handler"
      - "the theme manifest file is the only channel (in-transition; target: per-wall manifest and immutable media pulled into a Player-local cache) → conforms to the interim rule: the file channel keeps working throughout, and Chunk 04's HTTP mode renders only from the local cache, never from a live request"
      - "a display device renders its own label → conforms: no chunk moves label rendering. Media in waves 2 and 3 is the composed render the file channel already carries"
  - artifact: nonfunctional-requirements
    dispositions:
      - "the display plane never requires the curation plane to be reachable (in-transition) → conforms: Chunk 04's pull is additive and cache-first, a server outage keeps the last good manifest and media, and a restarted Player starts from its cache. A test stops the server while the wall runs"
      - "spend ceilings are provider-enforced → inapplicable because: no chunk adds a paid path"
  - artifact: security-model
    dispositions:
      - "the repository is public and no credential is committed → conforms: tokens are generated at runtime, shown once, stored only as a verifier, never logged, and read by the Player from its environment file"
      - "Player authentication on the LAN (decided: a token per wall) → Chunk 03 builds it, before the heartbeat POST ships, as the recorded deadline requires"
  - artifact: project-preferences
    dispositions:
      - "plane isolation (display imports no curation module, opens no HTTP client) → amendment scheduled by the norm's own row: Chunk 04 narrows the no-HTTP clause to one manifest-client module and three endpoints, in the same chunk that adds the pull, and keeps the no-curatarr-import clause whole"
      - "the two planes agree on the heartbeat by construction → conforms, and extended: the POST writes the same document to the same place the file reader looks"
      - "the mechanical norm-index rows → conforms: every chunk runs each touched project's lint, format and tests"
last_validated: null
---

# Build Plan — Wave 2b: The Seams, and the HTTP Channel Beside the File

## What this plan is

The rest of `re-architecture.md`'s wave 2, after the rename (`build-plan-wave-2a-rename.md`).
Curatarr splits into Library and Programming packages, with a facade and events
between them. It then serves each wall's manifest, media and heartbeat over HTTP
under a token per wall, and Arrt gains a mode that pulls them into a local
cache. **The file channel keeps working throughout.** The Pi can run either mode,
and wave 3 retires the file only once HTTP has run on the real wall.

Paths below use the names 2a gives them (`curatarr/`, `arrt/`).

| Chunk | What it is |
|---|---|
| 01 | Library and Programming packages, the `playable()` facade, and the import guard |
| 02 | Library events, and Programming's reconciliation at startup |
| 03 | Curatarr's HTTP surface: manifest, media by content hash, heartbeat, and wall tokens |
| 04 | Arrt's HTTP mode: pull into a cache, render only from it, and survive the server |

## What I would do differently

The plan follows the agreed order, with one scope question and one cut I'd
defend.

- **Should a Library change republish walls on its own?** Today it doesn't.
  Archiving a work withdraws its pins, but the published manifest keeps
  listing the work until somebody syncs, so a wall can go on showing an
  archived work. Events make automatic republishing easy. I recommend it for
  changes that **remove** readiness (archiving, an image change that makes a
  render stale), because a wall should never show what the curator withdrew.
  I recommend against it for changes that add, because deciding when new work
  reaches the wall is what `sync` is for. That changes behaviour, so it was
  the operator's call. **The operator confirmed it on 2026-09-30: removals
  republish, additions wait for sync.** Chunk 02 builds it.
- **The cut: no Player-side "HTTP by default" in wave 2.** Chunk 04 builds the
  mode, and the Pi switches to it by configuration after a soak. Making it the
  default is wave 3's retirement of the file, not this plan's.

## Requirements Confidence

**Medium.** The shape is settled by `re-architecture.md` and `player-contract.md`.
These are unconfirmed:

- **Confirmed by the operator 2026-09-30, no longer an assumption:** a Library
  change that removes a work's readiness (archive, a stale render) republishes
  every wall whose published manifest carries the work; a change that adds
  readiness waits for sync.
- `[ASSUMPTION: the published manifest stays a file in ART_ROOT through wave 2,
  written by sync as today, and GET /walls/{id}/manifest serves that file's
  bytes with an ETag of their SHA-256; the snapshot semantics of sync are
  unchanged | MED impact | user can correct]`
- `[ASSUMPTION: a POSTed heartbeat is written atomically to the same
  display-heartbeat-{wall}.json the file channel uses, so every existing reader,
  the health panel included, sees it with no change | MED impact | user can
  correct]`
- `[ASSUMPTION: wall tokens are 32 random bytes, stored as their SHA-256 (a
  high-entropy token needs no slow hash), issued and rotated from the Walls
  screen and by an art_display action, and shown once | MED impact | user can
  correct]`
- `[ASSUMPTION: a render's SHA-256 and size are recorded when the render is
  written; renders that predate the column are hashed on first need and
  recorded then | MED impact | user can correct]`

**What would raise it:** the one HIGH-impact question, automatic republishing,
is answered. What remains is MED, and each is checked by its chunk's tests.

## Persisted formats, and the questions each must answer

Each is lock-in, so the questions come before the fields.

- **`renditions.content_sha256`, `renditions.byte_size`** (Chunk 03). The
  questions: which file does `GET /media/sha256-<hex>` serve (by hash, indexed),
  and what goes in a manifest entry's `media`. Written at render time;
  backfilled on first need.
- **`walls.token_verifier`, `walls.token_issued_at`** (Chunk 03). The
  questions: does this bearer token open this wall (hash and compare in
  constant time); does a wall have a token at all (the UI shows "no token yet");
  when was it issued (the UI shows it, so a curator knows which Player is on
  the old one after a rotation). Programming's table, so it moves with Programming
  at the wave 3 store split.
- **The Player's cache directory** (Chunk 04). The questions: what was the last
  good manifest, and its ETag (it survives a restart, so a Player that boots
  while the server is down still shows the wall); do I have media X; what may I
  evict (anything no entry of the last good manifest names, once a newer
  manifest is adopted). Layout: `manifest.json`, `manifest.etag`,
  `media/sha256-<hex>`.

## New surfaces and the cross-cutting concerns

- **Curatarr's `/walls` and `/media` routes** (Chunk 03).
  - *Auth:* the wall token, a new credential kind, gets its row in
    `security-model.md` § Inventory.
  - *Errors:* the contract's model.
  - *Observability:* one journal line per refused token, rate-limited per wall,
    and the heartbeat's age is already on the health panel.
  - *Versioning:* the contract's, recorded in `player-contract.md`.
- **Arrt's pull client and cache** (Chunk 04).
  - *Errors:* keep the cache; back off.
  - *Observability:* report-once journal lines for "server unreachable",
    "token refused" and "hash mismatch", in the style the manifest watcher
    already uses.
  - *Storage:* bounded by eviction.
  - *Auth:* the token is read from the environment file, never logged.

## Status

- [ ] Chunk 01: Library and Programming packages, the `playable()` facade, and the import guard
- [ ] Chunk 02: Library events, and Programming's reconciliation at startup
- [ ] Chunk 03: Curatarr's HTTP surface — manifest, media by content hash, heartbeat, and wall tokens
- [ ] Chunk 04: Arrt's HTTP mode — pull into a cache, render only from it, and survive the server

### Chunk 01: Library and Programming packages, the `playable()` facade, and the import guard

- **Type:** code (a refactor: behaviour is preserved, so no existing test's
  assertions change)
- **Depends on:** `build-plan-wave-2a-rename.md` merged
- **Description:** `curatarr.library` takes the catalogue, discovery,
  acquisition, preparation, conversation, taste and spend services.
  `curatarr.programming` takes themes, walls, hanging, directives and the
  manifest builder. The MCP and HTTP bindings stay above both, the only code
  that may call both. Programming reaches the Library only through
  `curatarr.library.facade`, whose central call is
  `playable(work_ids) -> {id: PlayableWork | Unplayable(reason)}`. It returns
  plain frozen data, never a store record. The manifest's readiness rule
  (`assess`, `entry_for`'s inputs) moves behind it. Persistence stays one
  SQLite file in this wave. Programming gets its own store protocol over
  Programming's tables, so wave 3's split changes an implementation and no
  caller.
- **Tests:** the existing suites, unchanged in their assertions. The facade gets
  unit tests for every `Unplayable` reason, carried over from the readiness
  tests. A static import guard (`tests/preferences/test_seam_imports.py`, in
  the style of the plane-isolation test, following imports transitively) fails
  if Programming imports any Library module other than the facade, or the
  Library imports Programming. A mutation proves the guard: one deliberate
  cross-seam import turns it red.
- **Done when:** the suites and lint pass; the guard is green and proved; the
  norm's row in `project-preferences.md` moves rule 1 from Critic to Test.

### Chunk 02: Library events, and Programming's reconciliation at startup

- **Depends on:** Chunk 01
- **Description:** The Library announces `work.accepted`, `work.archived`,
  `work.image_changed` and `work.mat_changed` through an in-process publisher
  it owns. Programming subscribes. The pin withdrawal that
  `archive_artwork` performs today by writing Programming's directives moves to
  Programming's `work.archived` handler, so the Library stops writing a
  Programming table. That behaviour is preserved and its tests move with it. Readiness-removing
  events (`work.archived`, and `work.image_changed` when it leaves a render
  stale) also republish every wall whose published manifest carries the work.
  Events that add readiness do not, and wait for sync (the operator's ruling,
  2026-09-30). At startup,
  Programming reconciles each published manifest and each pin against
  `playable()`, so an event lost to a crash delays a correction until the next
  start and never leaves it undone.
- **Tests:** each event reaches its handler. Archiving withdraws pins on every
  wall, as today. Archiving a work republishes exactly the walls whose manifest
  carries it, and no other wall's manifest changes. Accepting a work republishes
  nothing. The Library no longer imports or writes any Programming
  table (the import guard plus a store-level assertion). Reconciliation repairs
  a manifest and a pin that a dropped event left stale: simulated by writing
  the Library change with the publisher disconnected, then starting. A
  multi-hop test covers two starts in a row: the second finds nothing to do and
  says so.
- **Related open item:** backlog #35. `activate_theme` commits before it
  publishes, so a failed manifest write leaves the catalogue naming a theme the
  wall is not showing. This chunk reworks that publish path, so fix #35 here or
  say in the chunk's review why not.
- **Done when:** the suites and lint pass; the norm's rule 4 is marked migrated
  in `architecture.md`.

### Chunk 03: Curatarr's HTTP surface — manifest, media by content hash, heartbeat, and wall tokens

- **Exposed API:** the Player surface, versioned and error-modelled by
  `player-contract.md`
- **Depends on:** Chunk 02
- **Description:** Three routes, as `player-contract.md` § Transport states them:
  - `GET /walls/{id}/manifest` serves the published manifest with an `ETag` and
    `304`. It now carries minor 2's `media` per entry.
  - `GET /media/sha256-{hex}` serves a render by content hash, immutable.
  - `POST /walls/{id}/heartbeat` validates the document and writes it where the
    file reader looks.

  Every route requires the wall's bearer token: `401` without a valid one, `403`
  for another wall's. Tokens are issued and rotated from the Walls screen (shown
  once, with its issue date after) and by an `art_display` action for MCP
  parity. The three route templates go into a new `contract/routes.json`, which
  the server's route tests assert against here and the Player's client tests
  assert against in Chunk 04. That is what keeps the route's spelling agreed
  across the repo split, as the heartbeat filename is agreed today. Media `url` is
  `format: uri-reference` in the schemas, which no installed validator checks, so
  this chunk either adds a pattern beside the format or states the obligation in
  prose, and adds a fixture with an absolute URL, when it first writes one. Renders gain `content_sha256` and `byte_size`, with the backfill the
  assumption above describes. `SCHEMA_MINOR` becomes 2.
- **Tests:** against a real booted server, as the suite's surface tests already
  run:
  - the contract's major 1 schema validates a served manifest;
  - an unchanged manifest answers `304`;
  - media bytes hash to their name;
  - a POSTed heartbeat is read back by the existing health surface;
  - each auth case (no token, wrong token, another wall's token, a rotated-out
    token);
  - a token is never logged: the test captures the journal while a request
    fails.

  The browser suite covers issuing and rotating a token. The curatarr contract
  test also validates a builder-written manifest that carries `media`, **beside**
  the contract's `minor-2-with-media` fixture, never in place of it. That fixture
  is the only valid major 1 manifest carrying `media`, and the Player's suite,
  Chunk 04's stub server and Arrt after the repo split all read it.
- **Carried from wave 1's cumulative review** (`rev-20260930T151634Z-9a02d6ac`),
  because this chunk already edits the contract's fixtures and its tests:
  - R-2: an invalid major 2 fixture for each of the two unreached branches of
    `semantic_errors` in `tests/preferences/test_player_contract.py`: a slot that
    starts before the horizon, and a horizon of zero or negative length. Delete
    each branch once and watch its fixture go red.
  - R-5/R-9: one root assertion that each fixture's `valid/` or `invalid/`
    directory agrees with its `valid` flag in `index.json`.
  - R-6: drop `_errors`' unused `schema_name` parameter in curatarr's contract
    test.
  - R-10: correct the root test docstring that says a row missing
    `player_must_refuse` is skipped by the display suite. It errors at
    collection.
- **Visual change:** yes. The token panel on the Walls screen goes on the
  operator-verification queue.
- **Done when:** the suites, the browser suite and lint pass; the `security-model.md`
  inventory row exists; the queue entry exists.

### Chunk 04: Arrt's HTTP mode — pull into a cache, render only from it, and survive the server

- **Depends on:** Chunk 03 (built against the contract, not against Chunk 03's
  code, so it could start once the contract fixtures exist)
- **Description:**
  - **The mode.** `MANIFEST_SOURCE=http` with `SERVER_URL`, `WALL_TOKEN` and
    `CACHE_DIR` switches Arrt from reading the manifest file to pulling it.
    The file mode stays the default.
  - **The pull client.** One module polls `GET /walls/{id}/manifest` with
    `If-None-Match` about once a second. On a new manifest it fetches each
    entry's media it lacks and verifies the hash. Only once every entry is in
    the cache does it write `manifest.json` into the cache atomically. The
    existing watcher reads the cache file exactly as it reads the shared one
    today, so rotation, directives and the label are untouched.
  - **Rendering.** Render paths resolve to cached media.
  - **The heartbeat** is POSTed as well as written.
  - **The isolation test.** `test_plane_isolation.py`'s no-HTTP clause narrows to
    that one module and those three endpoints, in this chunk and not before.
- **Tests:** against a local stub server serving the contract's fixtures:
  - a new manifest is adopted only after its media is cached and verified;
  - a hash mismatch is discarded and reported once;
  - `401` and `403` are reported once and the cache is kept;
  - **the server is stopped while the wall runs, and rotation continues from
    the cache;**
  - a restarted Player with the server down starts from its cached manifest;
  - eviction removes only unreferenced media;
  - the token never reaches the journal.
- **Carried from wave 1's cumulative review** (R-1): display's contract test
  asserts the whole adopted manifest (pin, rotation, shuffle, theme,
  `render_path`, label), not only work ids and directives, with fallback values
  no fixture carries. This chunk already rewrites how that manifest is adopted.
- **Visual change:** no. **Operator verification:** yes. Switch the Pi to HTTP
  mode against the Pi's own Curatarr and let it soak before wave 3 retires the
  file. The entry names what to watch in the journal and on the health panel.
- **Done when:** all three suites and lint pass; the isolation test is narrowed
  and still fails on a second HTTP client module (proved by mutation); the queue
  entry exists.
