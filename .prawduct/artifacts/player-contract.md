---
artifact: player-contract
version: 1
depends_on:
  - artifact: re-architecture
  - artifact: api-contract
  - artifact: data-model
  - artifact: security-model
last_validated: null
status: major 2 is the only manifest major published (wave 4g, 2026-10-10); major 1 is retired and kept as the record of what walls ran on until then
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

**Who tests what.** The contract is the `arrt-contract` package (`contract/`,
§ The package below), and its own suite (`contract/tests/`) checks that the
fixtures and schemas agree. Every invalid fixture must break
exactly one rule, the one its filename names. Arrt's suite validates
manifests its real builder writes, runs its heartbeat reader over the
heartbeat fixtures, validates the `GET /client` document it serves against the
client schema, and holds its client-heartbeat reader to the client-heartbeat
fixtures (`arrt/tests/contract/test_client_surface.py`). Arrt Player's suite runs its manifest reader over the manifest
fixtures and validates the heartbeat it writes. The conformance vectors in
`contract/vectors/` (the label rule, the mat's geometry, what a feed shows at
an instant) are held to reference statements in the package's suite, and each
Player's suite runs them against its own code. What each route answers, and what
each answer means to a Player, is `contract/transport.json`; Arrt's suite drives a
real server through every row of it (`arrt/tests/contract/test_transport_table.py`).
Each released version's fixtures and routes are kept frozen in
`contract/released/<version>/`, and the package's suite holds HEAD to them
(`contract/tests/test_released.py`). The label corpus
(`vectors/label-corpus.json`, real records chosen for the ways they break a
label engine) is held by Arrt's suite to the name splits and nationalities it
seeds, and each renderer's suite holds its own copy of the records to it. Every suite reads the files
through the package, never by a path of its own, so the version a Player
depends on is the contract it is tested against. Arrt owns the contract, and a Player that needs a field asks
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
  which is what it cannot act on safely, and it tolerates the rest. A major 2
  fixture whose index row says `player_must_refuse: false` breaks a writer
  obligation the reader does not police.

**Every instant is RFC 3339 with an offset.** Each schema backs its `date-time`
with an explicit pattern, because a JSON Schema validator does not have to check
`format`, and the common Python one does not unless an optional package is
installed. A timestamp without an offset would then pass silently.

**Integers are written without a fractional part.** JSON Schema's `integer`
admits `1.0`, and a reader may refuse it where a count matters. The schema is
the looser of the two, so the writer's obligation is stated here: Arrt writes
`1`, never `1.0`, as Python's `json` does.

### The package

The schemas, fixtures, vectors, routes and timing, `semantic_errors`, and this
file are released together as the Python distribution **`arrt-contract`**
(import name `arrt_contract`). Its source is `contract/` in Arrt's repository,
and Arrt owns it. A Player depends on a released version; a Player that needs a
field asks for it as a change to the package.

- **The package carries its own version, not the manifest's.** A new schema
  minor, fixture or vector is a package minor. A new manifest, heartbeat or
  label major is a package major. A correction that changes no document's
  meaning is a patch.
- **A release is an annotated tag `contract-v<version>`** on Arrt's repository,
  installed as
  `arrt-contract @ git+https://github.com/brookstalley/arrt@contract-v<version>#subdirectory=contract`.
  A released tag is not moved. Nothing on GitHub prevents moving one, so what
  holds a Player to the bytes it was tested against is its `uv.lock`, which
  records the commit the tag resolved to.
- **A release is copied into `contract/released/<version>/` when it is cut**:
  its `fixtures/` (index included) and `routes.json` as they are at the tag, and
  a `sha256.json` of each file's hash, written then and never again. The
  package's suite holds HEAD to every copy (`contract/tests/test_released.py`):
  every valid fixture of a release of this major still validates, every invalid
  one is still refused unless the loosening is recorded with its reason, and no
  route or fixture of it is gone. That is the mechanical form of "a minor is
  additive". The releases before 1.2.0 were copied from their tags when 1.2.0
  was built.
- **Read the data through the package:** `root()` is the directory holding
  `schemas/`, `fixtures/`, `vectors/` and `routes.json`, and it refuses by name
  a build without them. `validator(path)` registers every schema, so a
  reference between schemas resolves. `specification()` is this file as
  released. `transport()` is what each route answers (§ Transport),
  `vocabulary()` the household's words both sides say alike, and `released()`
  the frozen copies, by version.

### Releases

- **1.0.0** (2026-10-26): the first tag; heartbeat minor 4.
- **1.1.0** (2026-11-13): heartbeat minor 5, `capabilities.media`.
- **1.2.0** (audit wave 2, 2026-11-19): every change additive, nothing removed,
  no document's meaning changed.
  - `contract/transport.json`, `transport()`: each route's answers as data, with
    the ETag rule and its conditional-GET cases, a size bound per document, and
    what no answer means (§ Transport).
  - `contract/vocabulary.json`, `vocabulary()`: the word for each display state,
    and the pairing fields' names.
  - `client-heartbeat.v1`: optional `settings_url`, with two valid and five
    invalid fixtures, and `server_must_refuse` on every invalid client
    heartbeat's index row (§ Transport).
  - `heartbeat.v1`: `television_reachable`, `television_showing_art`,
    `has_label_surface` and `label_surface_working` described as superseded,
    still required (§ The heartbeat).
  - `client.v1`: a fixture of a Player with several labels and no walls, and its
    twin.
  - `manifest.v2`: a fixture whose `url` names another host, and its twin, an
    empty `url`, which a Player must refuse.
  - `vectors/mat-geometry.json`: `defaults.bottom_weight`, and its `_about`
    corrected to name what holds the vectors today.
  - `contract/released/1.0.0/` and `1.1.0/`, `released()`, and the check above.
  - The package's source checks clean under `mypy --strict`.
  - This file: § Transport points at the table, says what a `404` on a master
    and the client document's tag mean, and no longer promises what a
    Library/Programming split would require (§ Transport, media).

### What a Player does at 1.2.0

**Nothing a Player reads, writes or requests must change.** Every document a
1.1.0 Player writes is still valid, every document a 1.1.0 server sends still
is, and no route moved (`contract/tests/test_released.py`). One thing a Player's
suite must do, if it holds every must-refuse fixture to a stated reason as Arrt
Player's does: give one to the new must-refuse fixture,
`manifest.v2/invalid/media-url-empty.json`, which Arrt Player's reader already
refuses ("carries no media with a sha256 and a url"). A Player moving its pin to
`contract-v1.2.0` may:

- answer its server double from `transport()` rather than its own reading of
  this section, and replay `conditional_get.cases` against it;
- cap a document's read at its route's `max_bytes`, keeping what it has past it;
- send `settings_url` in its client heartbeat, from the address its settings page
  is bound to, and leave it out when the page is bound to loopback;
- quote `vocabulary()` for its settings page's state words and its two pairing
  fields' labels, with a test against the package;
- read its default bottom weight from `vectors/mat-geometry.json`'s `defaults`;
- stop reading the four superseded wall-heartbeat fields, which it keeps writing
  until heartbeat major 2;
- run its parsers and its writers over the new fixtures, and over
  `released()`'s, to hold itself to what an older server sent.

## Major 1

> **Retired in wave 4g (2026-10-10).** Nothing publishes or reads major 1: the
> server serves major 2 alone and Arrt Player reads only major 2 (§ The
> cutover). Its schema and fixtures left `contract/`, and a major 1 document is
> kept as a refusal fixture for a major 2 reader
> (`contract/fixtures/manifest.v2/invalid/major-1.json`). What follows is the
> record of what the walls ran on until then.

### The manifest

`manifest.v1.schema.json`, while it was in `contract/schemas/`. Minor 1 is what the curation plane's
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
  spelling is fixed for that reason: it is the schema's one required `date-time`
  property (`instant_key` in the package), and each side's suite holds its own
  constant to it.
- **`has_label_surface` is never null.** It separates a wall controller with no
  label surface from one whose surface has not drawn yet, a distinction `null`
  used to blur.
- **Four fields are superseded, and still required (contract 1.2.0).**
  `television_reachable` and `television_showing_art` by `display_state`
  (minor 3), which says what any display is doing; `has_label_surface` and
  `label_surface_working` by the client heartbeat's `label_outputs`, which
  reports every label output a Player holds, with `connected` for each. A wall
  heartbeat speaks for one wall's controller, so its two label fields can never
  say how many labels a Player has: a Player may hold several label outputs, or
  labels and no display at all (`labels-and-surfaces.md` § The recorded limit).
  A reader may stop reading the four; a writer keeps writing them, because a
  required key made optional is a writer change an older reader refuses. They go
  at heartbeat major 2, which nothing needs yet.
- **Written every 60 seconds.** On the file channel that is an SD-card wear
  budget. Over HTTP it stays, because it sits under the shortest rotation
  interval with margin. The number, and the three intervals after which a report
  is stale, are `contract/timing.json` (`timing()` in the package).
- **Minor 1 (wave 2)** adds the `schema` key.

### Transport (wave 2; clients from 2026-10-02)

A Player no longer reads the file channel: from `build-plan-clients.md` Chunk 03 it
always pulls, and refuses a configuration that asks otherwise. Over HTTP, a Player is a
**client** (`clients.md`): an installed Player with one token, driving any number
of walls, each on one of its outputs. It learns its walls from the server.

**`contract/transport.json` is this section's statement as data** (`transport()`
in the package, since 1.2.0): for every route in `routes.json`, each answer a
Player may meet, with its status, its body, what the server means by it and what
a Player does on meeting it; the ETag rule and its conditional-GET cases; a size
bound for each document; and what no answer, or any `5xx`, means. Arrt's suite
drives a real server through every row (`arrt/tests/contract/test_transport_table.py`),
so where the table below and the file differ, the file is what the server
answers, and the difference is a fault in this text. A status a route answers
that no row names is read by its class: a `5xx` as no answer, any other `4xx` on
a `GET` as a configuration error, and on a `POST` as that route's `400`.

| Route | Body | Answers |
|---|---|---|
| `GET /client` | none | `200` with the client document (`contract/schemas/client.v1.schema.json`): `{client_id, name, walls: [{wall_id, name, output, display}], labels: [{label_id, output, wall_id}]}`, only the walls assigned to this client and only its label outputs that caption a wall, and an `ETag`; `304` when `If-None-Match` matches. Polled about every 30 seconds |
| `POST /client/heartbeat` | the client heartbeat (`contract/schemas/client-heartbeat.v1.schema.json`): `{reported_at, outputs: [{name, kind, connected, screen, identity?}], label_outputs?: [{name, kind, connected, size}]}` | `204`; `400` naming the problem for a body that is not JSON or not a client heartbeat |
| `GET /labels/{label_id}` | none | `200` with the label document (`contract/schemas/label.v1.schema.json`): `{schema, wall_id, wall_name, display_state: {state, work_id, since}, label}`, and an `ETag`; `304` when `If-None-Match` matches. Polled about once a second by the label's renderer. `403` for a label output this client does not hold, or one the server does not; `404` for its own label output that captions no wall. Named in `contract/routes.json` (`label`) |
| `GET /walls/{wall_id}/manifest/v{major}` | none | `200` with the wall's manifest at that major (decimal, no leading zero) and an `ETag`; `304` when `If-None-Match` matches. Polled about once a second. `404` for a major the server does not publish for this wall, which since wave 4g is every major but 2, and for a wall with nothing hung (§ The cutover). Named in `contract/routes.json` (`manifest_major`). *(Wave 4g: the unversioned `GET /walls/{wall_id}/manifest`, major 1's original spelling, is retired and answers `404`.)* |
| `GET /media/sha256-{hex}` | none | `200` with the image, `Cache-Control: public, max-age=31536000, immutable`. A hash never serves different bytes |
| `POST /walls/{wall_id}/heartbeat` | the heartbeat | `204`; `400` naming the problem for a JSON object that is not a heartbeat this server can read; `422`, in the web framework's own body rather than the error shape, for a body that is not JSON or not an object (`transport.json`, `not_an_object`) |

- **Every request carries the client's token** as `Authorization: Bearer <token>`.
  Arrt issues one per client, shows it once and keeps only a verifier. A
  missing or unknown token is `401`. A valid token on a per-wall route for a wall
  not assigned to that client, or one the server does not hold, is `403`.
  `/media/...` accepts any client's valid token, whatever walls it drives.
- **A request body over 256 KiB is refused with `413`**, on every Player route that
  takes one, before it is parsed, and nothing is recorded (2026-11-19).
  A heartbeat is a few kilobytes, so the limit is ten times anything valid. It is a
  limit of this server's, `http/player.py` `BODY_LIMIT_BYTES`, and not a rule of
  any schema: a Player is never asked to know it, `contract/` carries no such number,
  and so changing it cuts no `contract-v` tag.
- **Wall tokens are retired, and this is a breaking change** for a Player
  configured with a wall token (`WALL_TOKEN`): every request it makes is `401`
  from the change on, and its operator moves it to a client token. No
  transition is kept, because there was one deployment and it moves in the same
  change (`build-plan-clients.md` Chunk 05). The server drops the stored wall
  verifiers when it opens a catalogue that holds them.
- **A client learns its walls; the host is not told them.** Assigning a wall to
  a client, or taking one away, changes `GET /client`'s document and so its
  `ETag`; the client starts or stops showing that wall on its next poll.
- **An `ETag` is a function of the body's bytes alone, and a document's bytes
  change if and only if its content does** (since 1.2.0, `transport.json`
  `conditional_get`). The server writes each document the same way every time,
  so an unchanged client document, feed or label keeps its tag, and `304` is
  answered only when `If-None-Match` names the tag of the very document that
  would be sent: a changed document always answers `200` with a new tag. A
  Player never computes a tag; it sends back the last one it was given.
- **A `404` for a master the feed names means the server does not hold those
  bytes, and it is final for that feed** (since 1.2.0). A Player skips the work
  and need not ask for that hash again until it adopts a changed feed; a home
  wall's feed changes at least once a day, when its horizon rolls.
- **A client may say where its settings page is** (since 1.2.0): the client
  heartbeat's optional `settings_url`, an absolute `http` or `https` URL with no
  user information, query or fragment, as the Player can be reached on the
  network it reaches the server from, and absent when the page is bound to
  loopback. The schema's pattern is the check. The server shows it only as a
  link, only after that check, and never as markup; a value that fails it is
  shown as no link and the rest of the report is kept, which the fixture index
  records as `server_must_refuse: false` on each of its invalid fixtures.
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
  last draw failed; one panel per Player is the limit Arrt Player is built to
  today, recorded by the owner's ruling of 2026-11-19, and nothing in this
  contract assumes it (`labels-and-surfaces.md` § The recorded limit). While the server cannot be reached (no answer, a timeout, a
  `5xx`), the renderer reads its last document as `unreachable` from the last
  instant the server answered, holding a caption and nothing else; a refusal or
  an unreadable document keeps the last one as it is. It redraws only when the
  drawing would change (outcome, label text or the card's wall name), and a
  label output whose mapping goes is drawn blank; a client stopping leaves the
  panel as it was.
- **Media is identified by the SHA-256 of its bytes and located by its `url`.**
  The manifest gives `url`, `sha256`, `bytes` and `content_type`. The `url` is
  a URI reference resolved against the manifest's own URL. Arrt writes
  `/media/sha256-<hex>`: media is served by this server, on the route above, and
  admitted by any client's valid token. A `url` may still be absolute and name
  another host, and a Player must read one; what it sends there is its own
  choice (Arrt Player sends its token only to the server's own origin). Nothing
  here promises how media would be served or admitted if the server were ever
  split: no such split is planned (the owner, 2026-11-19,
  `.prawduct/owner-rulings.md`). The Player verifies the
  bytes against `sha256` and discards a mismatch. So a corrupted transfer, or a
  `url` that disagrees with its hash, is never shown.
- **`url` is an RFC 3986 URI reference, relative or absolute, and that is the
  writer's obligation.** The schemas mark it `format: uri-reference`, which no
  validator installed here checks, so a malformed `url` passes the schema. A
  pattern would either reject real references or check nothing, so the rule is
  stated here instead. The valid fixture `manifest.v2/valid/media-on-another-host`
  carries an absolute `url` on another host, so every Player's reader is held to
  reading one, and its twin `media-url-empty` an empty one, which a Player must
  refuse. *(Since 1.2.0. Until then this named `minor-2-media-on-another-host`, a
  major 1 fixture that retired with major 1 in wave 4g and left no major 2
  fixture in its place.)*
- **Every failure keeps the cache.** Transport errors, timeouts and `5xx` mean
  the server is unreachable: the Player backs off and keeps showing what it
  has. `401`, `403` and a `404` on the wall are configuration errors, stated
  once in the journal; on the per-major route a `404` is one only when every
  major the Player reads answers it (§ The cutover). A `404` on a media hash skips that work and keeps
  rotating. An unknown major is refused and the last good manifest is kept. The
  wall going black is always worse than the wall being incomplete.
- **`/media/...` serves presentation masters**, by the hash a feed names. In
  waves 2 and 3 it served the composed render major 1's `render_path` named;
  since wave 4g the server composes nothing.
- **Neither the client document nor the client heartbeat carries a `schema` key.** Both allow unknown keys,
  so additions are free; a breaking change to either is a new schema major and a
  new route.

## Major 2

> **Reshaped 2026-10-08 (`feeds-and-players.md`), in the schema since wave 4a.**
> The manifest is a **feed** (schedule, works, default presentation settings)
> that a public channel serves with no token and no reporting; `scene` and
> `staging` are the **control** layer, and a document with neither is a complete
> channel feed. `settings` is the first of three layers (§ Presentation settings).

*(Built in waves 4a–4e, and since wave 4g the only major published. It was
written as a draft before wave 2 so the wave 2 channel would not paint wave 4
into a corner, and gives concrete fields to `re-architecture.md` § What is
showing, and how it is shown.)*

`contract/schemas/manifest.v2.schema.json`. Major 2 carries every breaking change
at once, so walls cut over once:

| Major 1 | Major 2 |
|---|---|
| `entries`, each with a composed `render_path` | `works`, a map from id to a presentation master, a mat colour and a label. The Player composes |
| `rotation` and a Player-side shuffle | `schedule`: time-anchored slots computed centrally for all walls |
| `directive` (`sequence`, `pinned_work_id`) | `scene`, a live override with a lifetime, and republishing the schedule (below) |
| `theme` | `playlist`, the same thing under its planned name |
| settings in each Player's configuration | `settings`, every key optional: label mode, mat mode, overlay timing, fades, text scale, viewing distance, and which label facts are shown (§ Presentation settings) |

### Presentation settings

`settings` holds the feed's defaults, the first of three layers
(`feeds-and-players.md` § Presentation settings come in three layers). A home
wall's curator settings override it, and a viewer's preferences on the device
override both, key by key. Every key is optional, and a key no layer sets is the
Player's own default, so a channel may say nothing about presentation.

- **The mat's colour is the work's; its mode is a setting; its width is the
  Player's.** `mat.mode` is `none`, `proportional` or `full`. No layer carries a
  width (`feeds-and-players.md` ruling 7): a Player that knows its pixel density
  keeps the inch rule, and one that does not uses a fraction of its screen's
  shorter side.
- **`label.mode` is text on the display itself**: `none`, `caption` (static for
  the slot, the only kind a Frame can show) or `overlay` (timed by `overlay`'s
  lead and tail, faded over `fade_seconds`). A label on its own surface is a label
  output with its own document (`labels-and-surfaces.md`), not a mode, which is
  why major 2 has no `panel`.
- **`facts`** lists which of a work's label keys a caption or overlay shows, in
  order. Its values are exactly the label's keys, a copy the contract package's suite holds
  to the label definition.
- **A Player applies what its display can honour** and ignores the rest, which
  is why a setting is never a reason to refuse a document.

### Rules a schema cannot state

A document that breaks any of these is malformed, and a Player refuses it and
keeps what it has. `semantic_errors` in the `arrt-contract` package
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
- **Every span is half-open.** A slot or a scene covers its `from` and not its
  `until`, so the slot that ends at an instant is over at it and the next has
  begun.
- **When the horizon ends with no fresh manifest,** the Player replays the slots
  shifted by one horizon, then by two, and so on. **An instant before the
  horizon begins** (a Player's clock behind the server's) is moved forward by
  whole horizons the same way, so the Player has one rule for every instant:
  move it into the horizon by whole horizons, then find its slot. A scene is
  never moved: it is shown at its own absolute times, past the horizon
  included. Because the horizon is whole
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

**Conformance vectors:** `contract/vectors/schedule.json` gives feeds and
instants and the work (or dark, and the scene) each must show. The contract package's suite
holds them to a reference statement of these rules
(`contract/tests/test_vectors.py`), and every Player's suite runs them.

### Layout

What a Player draws for one work on one screen, as numbers. The vectors are
`contract/vectors/mat-geometry.json`; the reference statement is in
`contract/tests/test_vectors.py`, and Arrt Player's compositor is
held to them in `arrt-player:tests/test_compose.py`. In Arrt, the box a work is
judged too small against (`programming/adequacy.py`) and the browser's drawing of
a wall (`http/static/core/mat.js`) are held to them too. *(Wave 4g: Arrt's own
compositor, which drew the `proportional` vectors with a density on the Frame
from wave 2, retired with major 1, and its check with it.)*

- **The mat width.** A Player that knows its pixel density (a configured Frame)
  takes its configured width in inches times the density. One that does not
  takes **6% of the screen's shorter side** (the owner, 2026-10-08), which on a
  50" Frame is within a few pixels of 1.5 inches. That is the side and top
  margin, rounded half up to whole pixels; the bottom is that rounded margin
  times the Player's bottom weight, **1.15 by default** (`defaults.bottom_weight`
  in the vectors, since 1.2.0, which is also the weight the server judges a
  work's size with), rounded half up again.
- **The box** is the screen less the side margins, the top margin and the
  bottom margin, at least a pixel each way. The work is scaled to fit it,
  **never up**, rounded half up, and centred in the box, an odd pixel left over
  going to the right and below. Because the box sits higher than centre, so does the work: centring it on
  the screen would undo the bottom weighting.
- **The mat**, by mode: `proportional` is the work's rectangle grown by the side
  margin left, right and above and by the bottom margin below, black beyond;
  `full` fills the screen with the mat colour; `none` has no mat, and the box is
  the whole screen.
- **A Player may differ from a vector by one pixel**, because image libraries
  round a fitted size differently.
- **The label and overlay layout** (regions, type sizes, an overlay's opacity
  over time) has no vectors yet. They are written before a second platform
  ports the Pi's label code (`feeds-and-players.md` § Reuse across platforms).

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
  `label_modes` are the modes of text on the display itself: `none`, `caption`
  (static for the slot, all a Frame can do) and `overlay` (timed, with fades),
  the same values as major 2's `settings.label.mode`; a label on its own surface
  is a label output, not a mode. Programming offers a wall only the modes its
  display reports. `screen` is reported again whenever it changes, and
  Programming judges whether a work is big enough for that wall from the largest
  size reported recently, not the latest (`feeds-and-players.md` § What a
  display reports it can do). `manifest_majors` says which majors a Player can
  be served (§ The cutover).
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

### The heartbeat, minor 4

Minor 4 makes **`capabilities.screen` optional**. A Player sends `backend`,
`label_modes` and `manifest_majors` always, and `screen` whenever its display
knows its size; a screen that is unplugged has none. A reader records no size
from capabilities without one, and refuses a `screen` it cannot read. *(Added
2026-10-10, the owner, #348: until then a Player whose screen was unplugged
sent no capabilities at all, and Walls told the curator to update a Player
that was reading the feed.)* A minor 3 server refuses capabilities with no
`screen`, so this minor is deployed server first, the one exception to
Players upgrading before the server.

### The heartbeat, minor 5

Minor 5 adds **`capabilities.media`**: `{kinds, video_max_frame}`, what media this
display can show, observed by the Player rather than configured. *(Added
2026-11-11, #424: the Player gained a renderer that plays moving media, and the
owner wants Arrt walls able to use it.)*

- **`kinds`** lists one or more of `image` (a still picture), `animated` (a moving
  image format with no sound track: an animated GIF, WebP or PNG) and `video` (a
  clip in a video container). **A reader ignores a kind it does not know**, so a
  later minor may add one.
- **`video_max_frame`** (`width_px`, `height_px`) is the largest video frame the
  Player plays with no dropped frames on this screen. It is optional, and the
  schema allows it only beside `video`. It exists because what a Player plays
  smoothly depends on its screen as well as its decoder: a Pi 4 driving a 4K
  screen played a 720p H.264 clip with no dropped frames and dropped about a
  third of a 1080p one's (measured by Arrt Player, 2026-11-10). Absent beside
  `video`, the Player has not measured one.
- **A clip fits the limit when its longer side is within the limit's longer
  side and its shorter side within the limit's shorter side**, whether either is
  portrait or landscape. The limit says what the Player can play smoothly, not which
  way its screen is hung: a 720×1280 clip costs a decoder what a 1280×720 one
  does (reasoned from the pixel count, not measured). A wall is hung portrait or
  landscape and never turns, and whether a portrait or landscape work belongs on
  it is the wall's shape range (`data-model.md` § The wall's shapes), which
  applies to a clip as to any work. *(The owner, 2026-11-13,
  `.prawduct/owner-rulings.md`.)*
- **Capabilities without `media` are a Player that shows still images**, read as
  `kinds: ["image"]`, as capabilities' absence is read as `manifest_majors: [1]`
  (§ The cutover).

The server keeps the heartbeat as it came and checks nothing in `media`, so a
Player may send minor 5 before its server knows the minor. No manifest carries
moving media yet: major 2's `media.content_type` admits only `image/jpeg` and
`image/png`. Adding moving media to a feed (its content types, a clip's
duration, the dwell rule for a clip, and what a Player that cannot play a work
does) is a separate change, #424's second half.

### The cutover

**Each major is served at its own URL while a reader of it may exist, and a
Player requests the highest major it reads** (`feeds-and-players.md` ruling 4,
which replaced a single-major cutover because an App Store Player cannot be
upgraded on demand).

- **The route is `GET /walls/{wall_id}/manifest/v{major}`.** A major the server
  does not publish for that wall answers `404`, and the Player asks for the next
  major down that it reads. It treats the wall as misconfigured only when every
  major it reads answers `404`. A Player may keep the major that last answered
  and ask for a higher one less often than it polls. Arrt Player asks again
  about once a minute, and at once if the major it was served stops answering.
- **A Player refuses a major it does not read** as an unsupported version and
  keeps its wall, as a major 1 Player refuses a major 2 document. *(Wave 4g:
  Arrt Player reads major 2 alone and refuses a major 1 document.)* From wave 4c
  until then Arrt Player read majors 1 and 2: its suite adopts every valid fixture of
  both whole, refuses every invalid one the index marks `player_must_refuse`
  (for major 2, never one that breaks only a presentation setting), and pins
  the version refusal with a major 3 document. *(Amended 2026-10-09, wave 4c:
  this said the suite pins a refusal of every major 2 fixture, which is the
  rule for a major 1 reader; `build-plan-wave-4c-wall-loop.md` records the
  decision.)*
- **For a home wall, the server serves each major it still builds and retires
  one once every heartbeat lists a higher major it publishes.** So wave 4
  upgrades the Players first, and the server stops building major 1, and with it
  the composed render and the unversioned route, once every Player reports 2. A
  Player missed in the upgrade is visible, because its heartbeat lacks 2: Walls
  and `art_display(action='walls')` say so for that wall (`reads_feed`,
  `feed_notice`). *(Amended 2026-10-10, wave 4g. This said "once no heartbeat
  lists it", which a Player reading both majors never satisfies, since it
  lists 1 for as long as it can read it; the sentence's own "once every Player
  reports 2" was the intent; the owner confirmed the amendment 2026-10-10. The home wall cut over in wave 4g: the server
  publishes major 2 alone, and Arrt Player reads only major 2.)* *(Wave 4e,
  2026-10-09, until wave 4g:)* while both majors were built, Arrt published a
  wall's major 2 only when it carried at least one of the works major 1 did, or
  when the theme was empty on both, so a Player stayed on major 1 rather than be
  sent a feed with nothing in it. With major 1 gone, a theme none of whose works
  can be sent publishes an empty feed, and a work without a master is not
  playable at all (it is named among the build's exclusions).
- **A heartbeat with no `capabilities` counts as `manifest_majors: [1]`**: it is
  a Player from before minor 2, which reads only major 1. *(Until minor 4 it
  could also be a Player whose display could not say its size, which is what
  made an up-to-date Player with its screen unplugged read as one that cannot
  read the feed, #348.)* Reading its silence as "lists nothing" would let the
  server retire the major that wall is running on. *(Added 2026-10-09, wave
  4c. Amended the same day, wave 4d: this named a Frame as a display that
  cannot say its size; Arrt Player now holds the Frame's geometry, composes
  for it, and reports `[2, 1]` from both of its drivers.)*
- **For a public channel, a major is retired by decision**, because nothing
  reports.

### Settled before wave 4

Wave 1 wrote the fields that carry these; the owner set the values on
2026-10-08, before wave 4 builds major 2.

- **The horizon's length: three days.** The server publishes a three-day
  horizon to home walls. The schema still allows any whole number of days, so
  this is the server's value, not a contract rule; a Player reads whatever
  horizon it is sent. Three days rides out a weekend with the server down
  before the replay rule takes over, at a few hundred kilobytes a week of
  schedule at a three-minute rotation. One day was the proposal.
- **A preview's default lifetime: twenty minutes.** It is a server default,
  not a contract field, because `until` is always explicit.
- **Whether `works` may carry works nothing names.** It is allowed. It is not
  needed, and a server that sends them only makes the Player fetch less wisely.
