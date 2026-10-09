---
artifact: player-contract
version: 1
depends_on:
  - artifact: re-architecture
  - artifact: api-contract
  - artifact: data-model
  - artifact: security-model
last_validated: null
status: major 1 describes the running system plus wave 2's additive changes; major 2 is a draft
---

# The Player Contract

**What Arrt publishes for a wall, what Arrt Player reports back, and how both
travel.** This file is the contract's home. `api-contract.md` § The Server↔Player
surface points here. `re-architecture.md` § Seam 2 is where the decisions behind
it were made.

The contract is three things, and they are kept together because each is only
half an answer alone (the routes' spelling is a fourth file, `contract/routes.json`):

- **Schemas** in `contract/schemas/`, JSON Schema Draft 2020-12, one per document
  and major. A schema states the **writer's obligations**: what a conforming
  document contains.
- **Fixtures** in `contract/fixtures/`, example documents, valid and invalid.
  `contract/fixtures/index.json` lists every one with the schema it is judged by.
  For an invalid manifest, the index also says whether a Player must refuse it.
- **This file**, for what a schema cannot carry. That covers when a reader
  refuses, what it keeps when it does, what a time means, and which wave brings
  what.

**Who tests what.** The root suite (`tests/preferences/test_player_contract.py`)
checks that the fixtures and schemas agree. Every invalid fixture must break
exactly one rule, the one its filename names. Arrt's suite validates
manifests its real builder writes, runs its heartbeat reader over the
heartbeat fixtures, validates the `GET /client` document it serves against the
client schema, and holds its client-heartbeat reader to the client-heartbeat
fixtures (`arrt/tests/contract/test_client_surface.py`). Arrt Player's suite runs its manifest reader over the manifest
fixtures and validates the heartbeat it writes. When Arrt Player moves to its own
repository (wave 5), it pins a copy of `contract/` and runs the same tests
against it. Arrt owns the contract, and a Player that needs a field asks
for it here.

## Versioning

The manifest, the wall heartbeat and the label document carry `schema: {major,
minor}`; the two client documents do not (§ Transport). The manifest has always carried
it. The heartbeat gains it in wave 2, and a heartbeat without one is 1.0.

- **A new major is a breaking change**: a field removed, a meaning changed, a new
  required key. A reader refuses a major it does not know and **keeps what it
  already has**. For the Player that means the last good manifest, so the wall
  goes on showing yesterday's theme rather than a misreading of today's.
- **A new minor is additive** and free. A reader ignores a minor it does not know,
  and ignores keys it does not recognise.
- **The schemas allow unknown keys** for that reason, and `unknown-minor-and-key`
  is a valid fixture.
- **A reader may be more tolerant than a schema.** The schema says what a writer
  must produce. A Player refuses only what the index marks `player_must_refuse`,
  which is what it cannot act on safely, and it tolerates the rest. The manifest
  fixtures `absolute-render-path`, `media-sha256-not-hex` and
  `generated-at-without-offset` break writer obligations that today's reader
  does not police.

**Every instant is RFC 3339 with an offset.** Each schema backs its `date-time`
with an explicit pattern, because a JSON Schema validator does not have to check
`format`, and the common Python one does not unless an optional package is
installed. A timestamp without an offset would then pass silently.

**Integers are written without a fractional part.** JSON Schema's `integer`
admits `1.0`, and the Player's reader refuses it where a count matters (the
directive sequence) or falls back to its default (the rotation interval). The
schema is the looser of the two, so the writer's obligation is stated here:
Arrt writes `1`, never `1.0`, as Python's `json` does.

## Major 1

### The manifest

`contract/schemas/manifest.v1.schema.json`. Minor 1 is what the curation plane's
`programming/manifest/builder.py` wrote until 2026-09-30. Minor 2 adds `media` to each entry, and the builder has
written it since wave 2b Chunk 03, omitting `media` for a render whose file it could not hash.

- **The wall is named by where the document lives**, never inside it: today by
  the file name `theme-manifest-{wall_id}.json`, from wave 2 by the URL
  `/walls/{wall_id}/manifest`. A Player configured for one wall cannot read
  another's by mistake.
- **A wall with nothing hanging has no manifest.** The builder refuses to build
  one. A wall whose theme holds nothing ready has a manifest with an empty
  `entries` list, which is an ordinary state.
- **Membership is readiness.** Every entry can be rendered, and works that
  cannot are reported to the curator, never sent to the Player.
- **`directive.sequence` and `pinned_work_id`** carry `show_now` and `next`. Their
  semantics (when a sequence counts as consumed, what an unresolvable pin does,
  and why a pin issued while the set is asleep waits) live in `data-model.md`
  § Directive and `api-contract.md` § How `art_display` reaches the display plane.
  They are not restated here.
- **`render_path` stays required for all of major 1.** From wave 3 no Player
  reads it, because the file channel is retired, but removing a required field
  is breaking, so it goes with major 2.
- **`label` carries text only.** The artist's name crosses whole and in parts,
  because a work whose artist has no recorded parts has only the whole. Every
  label key is present, with `null` for a fact the catalogue lacks.

### The heartbeat

`contract/schemas/heartbeat.v1.schema.json`. It holds facts, not a verdict: no
"healthy", no threshold. The reader decides what the facts mean.

- **`reported_at` is the one key the server depends on.** Arrt treats a
  heartbeat without it as unreadable, which reports the Player as broken. The
  spelling is fixed for that reason, and `tests/preferences/test_heartbeat_contract.py`
  checks both planes spell it the same.
- **`has_label_surface` is never null.** It separates a Player with no panel from
  a Player whose panel has not drawn yet, a distinction `null` used to blur.
- **Written every 60 seconds.** On the file channel that is an SD-card wear
  budget. Over HTTP it stays, because it sits under the shortest rotation
  interval with margin.
- **Minor 1 (wave 2)** adds the `schema` key.

### Transport (wave 2; clients from 2026-10-02)

A Player no longer reads the file channel: from `build-plan-clients.md` Chunk 03 it
always pulls, and refuses a configuration that asks otherwise. Over HTTP, a Player is a
**client** (`clients.md`): an installed Player with one token, driving any number
of walls, each on one of its outputs. It learns its walls from the server.

| Route | Body | Answers |
|---|---|---|
| `GET /client` | none | `200` with the client document (`contract/schemas/client.v1.schema.json`): `{client_id, name, walls: [{wall_id, name, output, display}], labels: [{label_id, output, wall_id}]}`, only the walls assigned to this client and only its label outputs that caption a wall, and an `ETag`; `304` when `If-None-Match` matches. Polled about every 30 seconds |
| `POST /client/heartbeat` | the client heartbeat (`contract/schemas/client-heartbeat.v1.schema.json`): `{reported_at, outputs: [{name, kind, connected, screen, identity?}], label_outputs?: [{name, kind, connected, size}]}` | `204`; `400` naming the problem for a body that is not JSON or not a client heartbeat |
| `GET /labels/{label_id}` | none | `200` with the label document (`contract/schemas/label.v1.schema.json`): `{schema, wall_id, wall_name, display_state: {state, work_id, since}, label}`, and an `ETag`; `304` when `If-None-Match` matches. Polled about once a second by the label's renderer. `403` for a label output this client does not hold, or one the server does not; `404` for its own label output that captions no wall. Named in `contract/routes.json` (`label`) |
| `GET /walls/{wall_id}/manifest` | none | `200` with the manifest and an `ETag`; `304` when `If-None-Match` matches. Polled about once a second |
| `GET /media/sha256-{hex}` | none | `200` with the image, `Cache-Control: public, max-age=31536000, immutable`. A hash never serves different bytes |
| `POST /walls/{wall_id}/heartbeat` | the heartbeat | `204` |

- **Every request carries the client's token** as `Authorization: Bearer <token>`.
  Arrt issues one per client, shows it once and keeps only a verifier. A
  missing or unknown token is `401`. A valid token on a per-wall route for a wall
  not assigned to that client, or one the server does not hold, is `403`.
  `/media/...` accepts any client's valid token, whatever walls it drives.
- **Wall tokens are retired, and this is a breaking change** for a Player
  configured with a wall token (`WALL_TOKEN`): every request it makes is `401`
  from the change on, and its operator moves it to a client token. No
  transition is kept, because there was one deployment and it moves in the same
  change (`build-plan-clients.md` Chunk 05). The server drops the stored wall
  verifiers when it opens a catalogue that holds them.
- **A client learns its walls; the host is not told them.** Assigning a wall to
  a client, or taking one away, changes `GET /client`'s document and so its
  `ETag`; the client starts or stops showing that wall on its next poll.
- **The output is a name the client chose and reported.** A wall is placed on
  `hdmi-a-1` or `frame` by that name. The server keeps only the name; the
  output's kind, whether it is connected and its size stay on the client, which
  reports them in the client heartbeat. **No two outputs in one report share a
  name**, which a schema cannot state and the server refuses. An output of one
  client shows at most one wall.
- **A display is a record, and its identity is what the client reads from the
  device.** A display output that can say who it is reports `identity`: a Frame
  gives its device id from its REST device description (`/api/v2/`,
  `device.duid`), read without a key press. The server keys the display on it,
  so a Frame moved from one client to another keeps its walls. An output with no
  readable identity, such as an HDMI connector, reports none, and the server keys
  it on the client and the output's name. `GET /client` names each wall's
  display beside its output; the client keys its worker on the output. While two
  clients report one identity, a configuration fault, `GET /client` lists that
  display's wall for neither until one stops (a report counts while it is no
  older than three heartbeat intervals).
- **A label output is a surface that captions a wall rather than showing one.**
  The client reports each in `label_outputs` (`epaper` today), and no two share a
  name, which the server refuses as it does for outputs. A wall has any number of
  labels, on any clients; a label captions at most one wall. `GET /client` lists
  this client's labels that caption a wall, and a client with labels and no
  display is an ordinary client.
- **A label renderer decides what to draw itself, by one rule.** The label
  document carries the wall's display state, as Walls states it, and the text
  the label would show; never a layout. The renderer applies the rule in
  `labels-and-surfaces.md` § What a label says, whose conformance vectors are
  `contract/vectors/label-rule.json`: every renderer, on every platform, runs
  them. It runs the rule rather than being told the outcome because the
  30-minute hold must still run while the server is unreachable. A state the
  renderer does not know is read as `unreachable`.
- **As built in Arrt Player** (`label_rule.py`, `label_renderer.py`; build plan
  displays-and-label-outputs, Chunks 05 and 06). The Frame's identity is read
  by the client, not by a wall's worker, with one `GET /api/v2/` on a REST-only
  client that opens no art channel and checks no token, so a Frame with no wall
  on it is still identified; it is asked again on each report until it answers
  and then kept, and a failure is said once per episode. A configured panel is
  the label output `epd-0`, `connected: false` when it would not open or its
  last draw failed. While the server cannot be reached (no answer, a timeout, a
  `5xx`), the renderer reads its last document as `unreachable` from the last
  instant the server answered, holding a caption and nothing else; a refusal or
  an unreadable document keeps the last one as it is. It redraws only when the
  drawing would change (outcome, label text or the card's wall name), and a
  label output whose mapping goes is drawn blank; a client stopping leaves the
  panel as it was.
- **Media is identified by the SHA-256 of its bytes and located by its `url`.**
  The manifest gives `url`, `sha256`, `bytes` and `content_type`. The `url` is
  a URI reference resolved against the manifest's own URL. Today it is
  `/media/sha256-<hex>` on the same server; after a Library/Programming split it
  may name the Library's host, and no Player changes. The Player verifies the
  bytes against `sha256` and discards a mismatch. So a corrupted transfer, or a
  `url` that disagrees with its hash, is never shown.
- **`url` is an RFC 3986 URI reference, relative or absolute, and that is the
  writer's obligation.** The schemas mark it `format: uri-reference`, which no
  validator installed here checks, so a malformed `url` passes the schema. A
  pattern would either reject real references or check nothing, so the rule is
  stated here instead. The fixture `minor-2-media-on-another-host` carries an
  absolute `url`, which is what a manifest looks like once the Library serves
  media from its own host.
- **Every failure keeps the cache.** Transport errors, timeouts and `5xx` mean
  the server is unreachable: the Player backs off and keeps showing what it
  has. `401`, `403` and a `404` on the wall are configuration errors, stated
  once in the journal. A `404` on a media hash skips that work and keeps
  rotating. An unknown major is refused and the last good manifest is kept. The
  wall going black is always worse than the wall being incomplete.
- **In waves 2 and 3, `/media/...` serves the composed render** that
  `render_path` names. From wave 4 it serves the presentation master.
- **Neither the client document nor the client heartbeat carries a `schema` key.** Both allow unknown keys,
  so additions are free; a breaking change to either is a new schema major and a
  new route.

## Major 2 (draft)

> **Direction changed 2026-10-08 (`feeds-and-players.md`).** Major 2 is
> reshaped before wave 4 builds it: the manifest becomes a **feed** (schedule,
> works, default presentation settings) that a public channel serves with no
> token and no reporting, and everything wall-specific is the **control** layer.
> `settings` widens into three layers (feed, wall, device) with mat mode,
> overlay timing and which facts an overlay shows.

**A draft until wave 4 builds it.** Nothing reads major 2 before then, so every
field here can still change, and should, if building wave 2 or 3 teaches
something. It is written now so the wave 2 channel does not paint wave 4 into a
corner. It gives concrete fields to `re-architecture.md` § What is showing, and
how it is shown.

`contract/schemas/manifest.v2.schema.json`. Major 2 carries every breaking change
at once, so walls cut over once:

| Major 1 | Major 2 |
|---|---|
| `entries`, each with a composed `render_path` | `works`, a map from id to a presentation master, a mat colour and a label. The Player composes |
| `rotation` and a Player-side shuffle | `schedule`: time-anchored slots computed centrally for all walls |
| `directive` (`sequence`, `pinned_work_id`) | `scene`, a live override with a lifetime, and republishing the schedule (below) |
| `theme` | `playlist`, the same thing under its planned name |
| settings in each Player's configuration | `settings`: label mode, mat proportions, viewing distance |

### Rules a schema cannot state

A document that breaks any of these is malformed, and a Player refuses it and
keeps what it has. `semantic_errors` in `tests/preferences/test_player_contract.py`
is the reference statement, and each rule has an invalid fixture.

1. **Every work the schedule, the scene or staging names is a key of `works`.** A
   Player never holds a reference it cannot resolve. That makes the major 1 case
   of a pin naming a work the manifest does not carry impossible, rather than
   handled.
2. **Each slot starts before it ends, and the slots run forward in time without
   overlapping.**
3. **Every slot lies inside the horizon.**
4. **The horizon is a whole number of days of absolute time**, a multiple of 24
   hours, which the replay rule under § Time depends on.
5. **A scene with an end time ends after it starts.**

### Time

- **Every instant is absolute** (RFC 3339 with an offset). Programming turns the
  household's local times ("dark from 23:00") into instants when it builds the
  schedule, so the Player never needs a time zone.
- **The Player's clock is kept by NTP.** A Player with a wrong clock shows the
  wrong slot. It cannot detect that itself, so its heartbeat's `reported_at`
  is how the server can: a heartbeat stamped far from the server's own time is a
  clock fault.
- **A time no slot covers is dark.** The dark hours are gaps, not a flag. Until
  Arrt Player power control exists (wave 6+), a Player that reaches a gap keeps
  showing the last slot's work, because it cannot yet send the set to sleep. The
  gap still means dark; the Player just cannot act on it.
- **When the horizon ends with no fresh manifest,** the Player replays the slots
  shifted by one horizon, then by two, and so on. Because the horizon is whole
  days, each slot keeps its time of day, and so does each dark gap. A wall cut
  off from the server for a week goes on keeping its household's hours. It never
  goes dark because it has not heard from the server.
- **Clock changes.** Days here are 24 hours of absolute time, not calendar days
  in the household's zone. Programming computes slots in local time and
  publishes them as instants, so a published schedule is right across a clock
  change: the `across-a-clock-change` fixture spans one. The one cost is in
  replay. A Player replaying its schedule across a clock change, because the
  server has been out of reach that long, keeps the dark hours an hour off local
  time until it hears from the server again. That was chosen over putting a
  time zone in the Player, which would make every Player keep a zone database
  current to fix a case that needs an outage of days.

### Scenes

- **A scene wins over the schedule while it is active:** from `from` until
  `until`, or indefinitely when `until` is null (hold). When `until` passes, the
  wall returns to the schedule on its own. A test cannot strand a wall, even if
  the server goes away mid-test.
- **One scene per wall.** A scene that spans walls is published as the same `id`
  in each wall's manifest. Each wall's heartbeat reports the `scene_id` it is
  showing, which is how the UI shows which walls a scene has reached and which
  are waiting.
- **A scene still respects the Player's guardrails.** It does not interrupt
  someone watching the set. The Player shows it when it can, and reports the
  scene it is waiting on as not yet shown.
- **Keeping a scene** is not a Player concern. The server turns it into ordinary
  Programming state and republishes the schedule.

### Staging

`staging` lists works a scene being assembled will need. The Player fetches and
composes them ahead, so applying the scene is only a switch. On a Frame, that is
selecting an image already uploaded. Nothing is shown because a work is staged,
and a Player may evict staged work that no slot or scene names once staging
drops it.

### What happens to `show_now` and `next`

The MCP and UI actions keep their names, and their mechanism changes. `show_now`
republishes the wall's schedule starting now with that work. `next` republishes
it starting now with the following work. Either is a new document, noticed on
the next poll like any other. The directive `sequence` and its consumption rules
retire with major 1, because a schedule is state rather than a command, and
state needs no counter to say whether it was acted on.

### The heartbeat, minor 2

The heartbeat does not need a new major: capabilities are additive. Minor 2 adds:

- **`capabilities`:** `screen` (pixels), `backend` (`frame` or `framebuffer`),
  the `label_modes` this Player can do, and the `manifest_majors` it reads.
  Programming chooses a wall's label mode from `label_modes`. It judges whether a
  work is big enough for that wall from `screen`, and uses `manifest_majors` to
  say before a cutover which Players it would leave on yesterday's wall.
- **`scene_id`:** the scene the wall is showing, or null.

### The heartbeat, minor 3

Minor 3 adds **`display_state`**: `{state, work_id, since}`, what the wall's screen
is doing as its controller sees it, written when it changes rather than on the
heartbeat's interval (`labels-and-surfaces.md` § Display state, ruled
2026-10-08). `state` is one of `showing_art`, `in_use` (somebody else has the
screen: a Frame showing television), `dark` (off, or no screen detected on the
connector), `no_screen` (the output is absent) or `unreachable` (the controller
cannot tell). `work_id` names the work only with `showing_art`, and is null there
for a picture this wall did not put there; the schema refuses a work beside any
other state. Every label of the wall reads this record and shows a caption only
while it says `showing_art`. A heartbeat without it is a Player before minor 3,
whose `current_work_id` the server reads as `showing_art`.
`television_showing_art` stays for older readers. **A reader reads a state name
it does not know as `unreachable`**, naming no work, and keeps the rest of the
heartbeat: a later minor may add a state, and Players upgrade before the server.

### The cutover

> **Direction changed 2026-10-08 (`feeds-and-players.md` § Versioning when
> Players cannot be upgraded).** App Store Players cannot be upgraded on demand,
> so each major is served at its own URL while a reader of it may exist, and a
> Player requests the highest it reads. The single-major cutover below holds
> until wave 4 builds that.

A major 1 Player refuses a major 2 manifest as an unsupported version and keeps
its wall. Arrt Player's suite pins that refusal for every major 2 fixture. So
wave 4 upgrades Players first and switches the server second, and a Player
missed in the upgrade is visible, because its heartbeat's `manifest_majors`
lacks 2. The server publishes one major for all walls. Serving each Player the
major it reads was considered and not planned: it would mean building two
documents for every wall through a transition that lasts minutes in a household.

### Still open in the draft

These are settled before wave 4 builds major 2, not in wave 1. Wave 1 wrote the
fields that carry them.

- **The horizon's length.** One day is the proposal. The schema allows any whole
  number of days, and a week costs a few hundred kilobytes at a three-minute
  rotation.
- **A preview's default lifetime.** Twenty minutes is the proposal. It is a
  server default, not a contract field, because `until` is always explicit.
- **Whether `works` may carry works nothing names.** It is allowed. It is not
  needed, and a server that sends them only makes the Player fetch less wisely.
