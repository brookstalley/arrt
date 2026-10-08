---
artifact: build-plan
version: 1
scope: displays-and-label-outputs
# branch: feature/displays-and-label-outputs — merged to develop on 2026-10-08. Chunk 07, the only one left, is the operator's at the wall and claims no branch; it is ticked in whichever PR follows the walk.
partition: Chunk 01 serial (the contract both sides build to); then two delegates in isolated worktrees — A the server (02, 03; arrt/ and contract tests only), B the Player (05, 06; postarr/ only); the coordinator integrates, reviews and verifies. Chunk 04 (the interface) is serial and waits for feature/lists-settings-and-scale to merge, because that branch is rewriting the Walls and Settings screens. Chunk 07 is the operator's.
depends_on:
  - artifact: feeds-and-players
  - artifact: labels-and-surfaces
  - artifact: clients
  - artifact: player-contract
  - artifact: data-model
  - artifact: samsung-tv-state-findings
governed_by:
  - artifact: data-model
  - artifact: architecture
  - artifact: nonfunctional-requirements
  - artifact: security-model
  - artifact: api-contract
  - artifact: observability-strategy
last_validated: null
---

# Build Plan — Displays as records, and label outputs mapped to walls

## What this plan is

Step 2 of `labels-and-surfaces.md` § What changes, in order (#188), widened by
`feeds-and-players.md` § Displays are configured, never discovered (rulings 1
and 9), which made displays server records in the same change.

Today a wall points at a client and an output name, and the e-paper panel belongs
to whichever wall is on the client's Frame. After this plan:

- **A wall names a display**, a server record keyed by an identity the client reads
  from the device, so moving a Frame from one client to another moves no wall.
- **A wall has 0..n label outputs**, each on any client, mapped server-side.
- **A label renderer runs per assigned label output**, on whatever client holds the
  panel. It reads a small label document and applies `labels-and-surfaces.md`'s
  table. The Frame loop stops owning the panel.

| Chunk | What |
|---|---|
| 01 | The contract: display identity and label outputs in the client heartbeat; labels in the client document; the label document and its route; the label rule as conformance vectors |
| 02 | The server's records: displays and label outputs, with the migration from (client, output) |
| 03 | The server's routes: `GET /client` names labels, `GET /labels/{label_id}`, and the duplicate-display fault |
| 04 | The interface: Settings › Clients lists displays and label outputs; Walls maps a wall's display and labels |
| 05 | The Player reports: display identity, and label outputs |
| 06 | The Player's label renderer, and the Frame loop without the panel |
| 07 | On the wall (the operator) |

**Not in this plan:** the feed/control reshape of major 2, mat modes and
presentation settings (wave 4); several Frames per client (#184), though nothing
here forbids it; caption mode; any non-Pi Player.

## Requirements Confidence

**High** for the model: the owner ruled cardinality, the label table, the
30-minute blank and the no-discovery rule (`labels-and-surfaces.md` § Rulings,
`feeds-and-players.md` § Rulings). **Medium** for mechanism, because of these:

- `[ASSUMPTION: a Frame's /api/v2/ device description carries a stable device id (the set's "id" or "duid") that survives a reboot and a network change, so it can key the Display record | HIGH impact | PRESENCE VERIFIED 2026-10-08: id, duid and udn carry one uuid on 8001 and 8002 (samsung-tv-state-findings.md § The set's identity). Survival across a reboot or reset is still the UPnP standard's promise, not a measurement; a reset would show as a new display with no walls, which a curator maps again]`
- `[ASSUMPTION: an attached output (an HDMI connector, a panel) has no device id a client can read reliably, so its identity is the client's id plus the output's name, as clients.md does today. Such a display cannot move between clients, which is true of the hardware | MED impact | owner can correct]`
- `[DECISION: the label renderer applies the label table itself, from a label document carrying the wall's display state (the server's seven, with since) and the work's label text, rather than the server sending a finished "show this" | labels-and-surfaces.md § What a label says: "one pure rule, run identically by every renderer, wherever it is"; the 30-minute blank is a clock the renderer must run anyway when the server is unreachable | builder's call, from the note]`
- `[DECISION: the label rule ships as conformance vectors in contract/ (display state, since, now, label text → caption, card or blank), the first behaviour vectors of feeds-and-players.md § Reuse across platforms | the rule will be implemented again on Apple platforms, and vectors are the reuse mechanism ruled 2026-10-08 | builder's call]`
- `[DECISION: client-heartbeat and client documents grow by additive keys, with no schema major | both carry no schema key and allow unknown keys (player-contract.md § Transport): additions are free, and a breaking change would be a new route | conforms]`
- `[ASSUMPTION: a label output is held by at most one wall, like a display output | MED impact | the owner ruled "a label captions at most one wall"; this plan reads it as a store constraint]`

- `[DECISION: showing_art with no label (a picture this wall did not put there) is the quiet card, not a caption and not blank | the table's "no work to show" row; blank is kept for a screen somebody else is using | builder's call, owner can veto]`
- `[DECISION: for silent and unreachable, the label document's label is the work the wall last showed where the server knows it, and the renderer holds it for 30 minutes from since; with no label or no since it blanks at once | the hold must be a pure function of the document and the clock for the vectors to state it, so the renderer is never asked to remember its own last caption | builder's call]`
- `[DECISION: contract/routes.json gains the label route in Chunk 03, not Chunk 01 | arrt's route test holds the mounted routes and routes.json equal in both directions, so naming a route the server does not mount turns that suite red between chunks; player-contract.md describes the route from Chunk 01 | amended at Chunk 01]`

Recorded while building Chunks 02, 03, 05 and 06 (builder's calls, owner can veto):

- `[DECISION: the Frame's identity is read by the client, not by a wall's worker: one GET of /api/v2/ through the TV module, no art channel, no key, kept for the life of the process once read | a Frame with no wall on a new client would otherwise never report it and never move | coordinator]`
- `[DECISION: a display first reported without identity is re-keyed when its identity arrives and keeps its walls; a Frame moved to another client absorbs that client's placeholder display: no wall there, the placeholder is deleted; only the placeholder has a wall, the wall moves; both have one, the Frame's display keeps its own and the placeholder's is unassigned (logged at WARNING) | an output shows at most one wall | coordinator]`
- `[DECISION: Display.client_id is nullable: a different device reported on a client's output leaves the old display with its wall and no client; Display.kind is nullable until reported; removing a client deletes its displays and label outputs and unassigns their walls | builder]`
- `[DECISION: a duplicate-display fault counts only readable reports no older than STALE_AFTER_SECONDS, so a host switched off stops claiming; while in fault the display stays with its current client and neither client is admitted to the wall | builder]`
- `[DECISION: mapping a label output that already captions a wall is refused, not moved; GET /labels for the client's own unmapped label output is 404 | builder]`
- `[DECISION: label text is read through LibraryFacade.labels(), sharing label_of() with the manifest builder | playable() logs per call, and labels poll once a second | builder]`
- `[DECISION: assign_wall(client_id, output) stays, finding or creating the display, so today's browser screens work unchanged until Chunk 04 | builder]`
- `[DECISION: while the server is unreachable the renderer reads its last document as unreachable from the last answer, holding only a caption; a refusal (401/403/404) or an unreadable document keeps the last document without starting the hold; a renderer with no document yet draws blank (no disk cache); a retired renderer blanks its panel, a stopping client leaves it | builder]`
- `[DECISION: the panel and its draw gate live in LabelPanel, opened once per process, so a renderer restarted onto a panel mid-draw cannot send a second draw; the redraw check compares outcome, label text and wall name | builder]`
- `[DECISION: label outputs are mapped on Settings › Clients, in the client's panel beside "Assign a wall", not on Walls; Walls says which labels caption each wall (only when one does) and links there | walls are already assigned on that page, per client, as Radarr keeps Download Clients, and two places to map one thing would be two forms to keep in step | builder, departs from Chunk 04 item 2's "Walls maps"; owner can veto]`
- `[DECISION: Walls' sentence for an unreachable screen is "cannot say what its screen is showing", true both of a controller that cannot reach its screen and of a state the server has no name for and reads as unreachable | the two arrive identically, so only a sentence true of both is honest | builder]`
- `[GAP: why a panel would not open, and a geometry with no usable area, were wall-heartbeat signals; the client heartbeat has no field for them, so today they reach the journal only (observability-strategy.md says so). An additive key on label_outputs would carry them | not in this plan; #315]`

**What would raise it:** one read of the Frame's `/api/v2/` on the operator's set
(with the Player stopped, through the existing `power_probe.py` REST sample, no
key), recording the id fields into `samsung-tv-state-findings.md`.

**Prerequisite outside the plan:** #181, the panel failing to open after a fresh
install, blocks Chunk 07 only. Chunks 01 to 06 build and test against the panel
double, because the driver is passed into `EpaperSurface` rather than opened by
it.

## Governing norms

Seeded with `prawduct-hook jurisdiction`; dispositions:

- `data-model.md`, Wall record: "geometry, network address, panel model … are per-device runtime state and permanently forbidden here." **Conforms**: the Display record holds an identity, the client that reports it, the output name and kind; never an address or geometry (ruling 9 keeps the Frame's address on the Pi). Recorded as `[DECISION: the Display record carries kind (frame, framebuffer) | Walls and Settings must say what a display is without asking the client, and kind is a category, not a measurement | builder's call, owner can veto]`.
- `architecture.md` § Direction, the Player channel (pull-to-local-cache only; the Player never writes what the server owns): **conforms**: the label document is pulled with an ETag like the manifest; nothing is pushed.
- `nonfunctional-requirements.md`, the label redraws within 15 s of a picture change: **conforms by design** (on-change heartbeat, about 1 s polls, `labels-and-surfaces.md` § Latency); Chunk 07 measures it.
- `security-model.md`, client tokens: **conforms**: `GET /labels/{label_id}` admits only the client holding that label output (`403` otherwise), the same rule as the per-wall routes.
- `tests/preferences/test_plane_isolation.py` (an HTTP client only in `postarr/src/postarr/pull.py`): **conforms**: the renderer's fetch goes through `pull.py`, and its route is added to `contract/routes.json`.
- `architecture.md` § Direction, "a display device renders its own label, and the label travels as metadata": **conforms**: the label document carries the label's text and the wall's state, never a layout; the renderer lays out and draws.
- `architecture.md` § Direction, "operation logic lives only in the service layer": **conforms**: Chunk 03's mapping is one service that HTTP and MCP both call.
- `architecture.md` § Direction, the Library/Programming seam (`in-transition`): **conforms**: Display and LabelOutput are Programming records; the label document reads a work's label text through the Library facade, as the manifest builder does, never from Library tables.
- `api-contract.md` § The Server↔Player surface and § Versioning: **conforms**: one new route, a new document with its own schema and major, and additive keys elsewhere.
- `observability-strategy.md`, a new execution context (the label renderer): **conforms by design**: it reports as the panel does today, once per episode for an unavailable panel or an unreadable document, never once per poll.

## Status

- [x] Chunk 01: The contract
- [x] Chunk 02: The server's records
- [x] Chunk 03: The server's routes
- [x] Chunk 04: The interface
- [x] Chunk 05: The Player reports
- [x] Chunk 06: The label renderer
- [ ] Chunk 07: On the wall

### Chunk 01: The contract

Done when:

1. `contract/schemas/client-heartbeat.v1.schema.json` accepts, per display output,
   an optional `identity` (a non-empty string the client read from the device;
   absent for an attached output), and a new optional `label_outputs` list:
   `{name, kind: "epaper", connected, size: [w, h] | null}`.
2. `contract/schemas/client.v1.schema.json`'s walls gain `display` (the display's
   id) beside `output`, and the document gains `labels: [{label_id, output,
   wall_id}]` for this client's label outputs that are mapped.
3. new `contract/schemas/label.v1.schema.json`: `{schema: {major, minor}, wall_id,
   wall_name, display_state: {state, work_id, since}, label | null}`, where
   `state` is one of the server's seven (`labels-and-surfaces.md` § Display
   state) and `label` is the ten text keys the manifest already carries.
4. *(Moved to Chunk 03, see the decision above: `contract/routes.json` names the route when the server mounts it.)*
5. new `contract/vectors/label-rule.json`: (state, since, now, label) → `caption`,
   `card` or `blank`, covering every row of the table, the 30-minute boundary on
   both sides for `silent` and `unreachable`, and a state name the reader does not
   know (read as `unreachable`).
6. Valid and invalid fixtures for each new shape, listed in
   `contract/fixtures/index.json`; `player-contract.md` § Transport gains the
   route and the documents, and points at the vectors.
7. All three suites' contract tests pass over the new fixtures, and the root suite
   checks that every vector's inputs validate against the label schema.

### Chunk 02: The server's records

Done when:

1. A Display record (id, identity, client_id, output, kind, first_seen) and a
   LabelOutput record (id, client_id, output, wall_id nullable) exist in
   Programming, and Wall's `client_id`/`output` give way to `display_id`.
2. A migration turns each assigned wall's (client_id, output) into a Display with
   identity {client_id}/{output}, so walls stay where they hang. A test opens a
   catalogue in today's shape and finds every wall on the same screen after.
3. The store enforces, and the docstrings state exactly what it enforces: one
   identity per Display; one wall per Display; a LabelOutput's (client_id, output)
   unique; a LabelOutput on at most one wall (a wall may have many).
4. A client heartbeat creates or refreshes the Displays it reports, keyed on
   `identity` when present and on {client_id}/{name} otherwise, and the
   LabelOutputs it reports. A Display reported by a different client than last
   time moves to that client, with its walls (the Frame moved from Pi to Mac).
5. `data-model.md` gains both records, with § What this data must answer: which
   display does this wall use; which client drives it; which labels caption this
   wall; which client holds each; was a display reported by two clients.

### Chunk 03: The server's routes

Done when:

1. `GET /client` names each wall's display and lists the client's mapped labels.
   A client's walls are those whose display it reports.
2. `GET /labels/{label_id}` serves the label document with an ETag (`304` on a
   match). `401` without a token; `403` for a label output another client holds
   or an unknown id. The document's state is `display_state.py`'s, so a label and
   Walls cannot state different answers for one wall.
3. **Two clients reporting one identity is a fault the curator sees**: the
   display's walls are given to neither client until one stops, and Walls and
   Settings › Clients say so, naming both. No client arbitrates.
4. HTTP and MCP (`art_display`) can map a wall's display and add or remove its
   label outputs, through one service, with the assignment rules in one place
   (`programming/clients.py`).
5. `contract/routes.json` names `label: GET /labels/{label_id}`;
   `arrt/tests/contract/test_client_surface.py` validates every served document
   against its schema, and the route test asserts the mounted routes against
   `contract/routes.json`.
6. Carried in from the display-state review: a server test asserts that
   `ScreenState`'s members are exactly the heartbeat schema's states plus
   `unassigned` and `silent`, so a state added to one and not the other fails by
   name.

### Chunk 04: The interface

Starts after `feature/lists-settings-and-scale` merges to develop.

Done when:

1. Settings › Clients lists each client's displays (with kind and whether
   connected) and label outputs, and names the fault from Chunk 03 in place.
2. Walls maps a wall's display and its labels, and shows each label's client.
3. `information-architecture.md`'s screen tables say so, and
   `tests/preferences/test_screen_tables.py` passes.
4. The browser suite (`-m browser`) seeds a client with two HDMI outputs, a Frame
   and one panel, and maps the panel to each display in turn.
5. New screens follow the conventions that branch set: glyphs from
   `core/glyphs.js` by meaning (a test refuses a literal glyph), and
   `emptyState()` from `core/render.js` for an empty page.
6. Carried in from the display-state review: `walls.js` `nowShowing` loses its
   unused `reason` parameter; the words Walls gives each screen state
   (`STATE_WORDS` in `screens/walls.js`) are checked against the schema's states
   by a test; and a state name Walls does not know, read as
   `unreachable`, no longer says "cannot reach its screen", which is wrong for
   that case.
7. Carried in from Chunk 03: a wall whose display is in the duplicate-display
   fault still carries `client_id` in `/api/walls`, so today's Walls shows it
   assigned while its state is `unassigned`. Walls and Settings › Clients read
   `display.fault` (walls) and `faults` (clients) instead.

### Chunk 05: The Player reports

Done when:

1. The Frame output reports `identity` from the set's `/api/v2/` device
   description (`device.duid`), read once per connection and never by a key press. HDMI outputs report no identity.
2. A configured panel (`EPD_DEVICE`) is reported as a label output, and
   `config.py` no longer refuses `EPD_DEVICE` without `TV_ADDRESS`.
3. Tests in `postarr/tests` validate the heartbeat the client writes against the
   schema, with and without a panel, and with a Frame whose id cannot be read
   (reported without `identity`, said once in the journal).

### Chunk 06: The label renderer

Done when:

1. The supervisor starts one label renderer per label output that `GET /client`
   maps, and stops it when the mapping goes. The renderer polls its label
   document through `pull.py` about once a second, applies the rule, and redraws
   only when the outcome changes (an e-paper redraw flashes for about 2 s).
2. The rule is one pure function, and `postarr/tests` runs it over every vector
   in `contract/vectors/label-rule.json`.
3. With the server unreachable, the renderer keeps its last document and still
   runs the 30-minute clock from its own `since`, so a wall that goes away still
   blanks on time.
4. The Frame loop (`daemon.py`) no longer draws the panel: its label code moves
   to the renderer, and the label wiring tests move with it, each change to a test
   recorded with its reason. The Frame loop and the HDMI loop both only report.
5. All three suites pass; the mutation sweep is run over the rule and the
   renderer's redraw decision.

### Chunk 07: On the wall

Done when the operator, with #181 fixed and the server and Player deployed, sees:
the panel caption the HDMI wall, then the Frame wall, by a change on Walls alone;
the caption change within 15 s of a picture change; the panel blank while the
Frame shows television; and a Display that keeps its walls when its client is
restarted.

## Verification

All three suites at each chunk boundary, with the contract tests as the seam and
the label vectors run on both sides. Chunk 04 runs the browser suite. Chunk 07 is
hardware and the operator's.
