---
artifact: build-plan
version: 1
scope: wave-1-contract
depends_on:
  - artifact: re-architecture
  - artifact: api-contract
  - artifact: architecture
  - artifact: data-model
  - artifact: security-model
governed_by:
  - artifact: architecture
    dispositions:
      - "the theme manifest file is the only channel from curation to display (in-transition; target: the per-wall manifest and immutable media, pulled into a Player-local cache) → conforms: this plan specifies the target channel and builds none of it. No code path changes; the file channel is untouched"
      - "a display device renders its own label, and the label travels as metadata → conforms: both schema majors carry label text only. No geometry, type size or layout crosses the contract"
      - "the Library/Programming seam norms (in-transition) → inapplicable because: no service code changes. The contract is Programming's outbound surface and names no Library table"
  - artifact: nonfunctional-requirements
    dispositions:
      - "the display plane never requires the curation plane to be reachable (in-transition) → conforms: Chunk 01's display tests read fixtures from disk and never open a connection. The contract's error model (keep the cache on every failure) is the norm stated for the network"
  - artifact: project-preferences
    dispositions:
      - "the two planes agree on the heartbeat's filename and its instant's key by construction → strengthened: Chunk 01 adds a schema both planes are tested against, beside the existing text-level check, which stays"
      - "plane isolation (display imports no curation module) → conforms: display's contract tests read JSON files under contract/, never curation's code"
      - "the mechanical norm-index rows (formatting, naming, imports, logging-not-print, type annotations, specific exceptions) → conforms: every chunk runs each touched plane's lint, format and tests"
last_validated: null
---

# Build Plan — Wave 1: The Player Contract

## What this plan is

Wave 1 of `re-architecture.md` § Order of work: write the contract between
Curatarr (the server) and Displayarr (the player) **before** wave 2 builds
either side of the HTTP channel. The contract is a JSON Schema per document,
example documents (fixtures), and one artifact that states the semantics a schema
cannot: when a Player refuses, what it keeps, what a time means.

**Why a schema and fixtures, not prose alone.** The contract outlives this repo.
At wave 5 Displayarr moves to its own repository and pins these fixtures, and from
then on a field that changes on one side and not the other is found by a test in
one repo, not by a wall that goes dark. Tests land here too, now, so the
contract is proved against the code that exists before anything is built against
it.

**Major 1 is described; major 2 is designed.** Major 1 is what runs today plus
wave 2's additive changes. Its schema is derived from the builder and the reader,
and tests prove it matches both. Major 2 (wave 4) is a **draft**: the schedule,
scenes, staging, wall settings and capabilities from `re-architecture.md` § What
is showing, and how it is shown, given concrete fields. Nothing reads major 2 until
wave 4, so the draft can change freely until then. It is written now because the
wave 2 channel must not paint wave 4 into a corner.

| Chunk | What it is |
|---|---|
| 01 | Major 1: the as-built manifest and heartbeat, the HTTP transport, tokens and errors, and the tests that pin both planes to them |
| 02 | Major 2, as a draft: schedule, scenes, staging, wall settings, capabilities, presentation master |
| 03 | The wave 2 build plan |

## Requirements Confidence

**Overall: Medium.** High for major 1, lower for the major 2 draft.

- **Major 1: High.** It describes documents the code writes today. The risk is a
  schema that is subtly looser or stricter than the builder, which the tests in
  Chunk 01 close by validating real builder output and real display parsing.
- **Transport: Medium.** The routes, the ETag poll and the per-wall token are
  decided (`re-architecture.md` § Seam 2). The status codes, the header and the
  hash format are this plan's choices.
  - `[ASSUMPTION: the token travels as "Authorization: Bearer <token>"; a missing
    or wrong token is 401, a token for another wall is 403]`
  - `[ASSUMPTION: media is addressed as sha256 over the file's bytes, written
    "sha256-<64 hex>" in the URL, and the Player verifies the hash after
    download and discards a mismatch]`
- **Major 2: Medium-Low, and labelled draft in the artifact.**
  - `[ASSUMPTION: schedule times are RFC 3339 instants in UTC; the Player's clock
    is kept by NTP, and a Player whose clock is wrong plays the wrong slot, which
    it reports in its heartbeat rather than detecting]`
  - `[ASSUMPTION: after the horizon ends with no fresh manifest, the Player
    replays the published schedule shifted by whole days, so dark hours keep
    their time of day; a horizon is therefore a whole number of days]`
  - `[ASSUMPTION: every work id the schedule, scene or staging list names is a
    key of the document's works map, so a Player never holds a reference it
    cannot resolve; a document that breaks this is malformed and refused]`
  - `[ASSUMPTION: show_now and next map onto the schedule: show_now republishes
    the schedule starting now with that work, next republishes it from the next
    work. Neither needs a directive block in major 2, and the sequence counter
    retires]`
  - `[ASSUMPTION: the label shows every fact the typesetter can fit, as today; a
    per-wall choice of facts is not added until someone asks for it]`

## Status

- [x] Chunk 01: Major 1 — the as-built documents, the HTTP transport, and the tests that pin both planes
- [x] Chunk 02: Major 2 as a draft — schedule, scenes, staging, wall settings, capabilities
- [ ] Chunk 03: The wave 2 build plan

Critic mode: cumulative-final. One cumulative review covers the plan when Chunk
03 lands, because the three chunks are one contract and a reviewer reading them
apart would miss disagreements between majors.

### Chunk 01: Major 1 — the as-built documents, the HTTP transport, and the tests that pin both planes

- **Depends on:** none
- **Artifacts consumed:** `re-architecture.md` § Seam 2; `api-contract.md`
  § How `art_display` reaches the display plane and § The Server↔Player surface;
  `data-model.md` § Directive; `curation/src/curation/manifest/builder.py`;
  `display/src/display/manifest.py`; `display/src/display/heartbeat.py`;
  `curation/src/curation/manifest/heartbeat.py`
- **Deliverables:**
  - `.prawduct/artifacts/player-contract.md`: the home of the contract. It
    covers the documents, versioning (major refused, minor ignored), the
    transport (routes, ETag and `304`, the bearer token, status codes, the
    error model) and the media hash. It says when each wave adds what. Directive
    semantics stay in `data-model.md` § Directive and are pointed at, not
    restated.
  - `contract/schemas/manifest.v1.schema.json` (Draft 2020-12). It describes
    minor 1 as built, plus minor 2's optional `media` reference per entry
    (wave 2). `render_path` stays required throughout major 1, because removing
    it is breaking.
  - `contract/schemas/heartbeat.v1.schema.json`: the as-built document, plus
    wave 2's optional `schema` key. Additive keys are allowed.
  - `contract/fixtures/`: valid and invalid examples of each document. Every
    invalid fixture names, in its filename, the one rule it breaks.
  - **Tests:**
    - Root suite, `tests/preferences/test_player_contract.py`: every schema is
      valid Draft 2020-12, every valid fixture validates, and every invalid one
      fails.
    - Curation suite: a manifest built from real records through `as_document`
      validates against the major 1 schema, for a wall with entries, an empty
      one, and one with a pin.
    - Display suite: every valid major 1 fixture parses with `display.manifest.parse`.
      Every invalid fixture that the reader must refuse is refused.
      `Health.document()` validates against the heartbeat schema.
  - `jsonschema` declared in the root, curation and display `dev` groups. It is
    test-only, and curation's indirect copy via `mcp` is not relied on.
  - `api-contract.md` § The Server↔Player surface points at the new artifact,
    and records authentication as settled.
- **Tests:** as above. A mutation check proves at least one pin works: loosen a
  schema field, and a builder-output test goes red.
- **Done when:** all three suites and their lint pass; the tests above pass; a
  mutation of the schema is caught.

### Chunk 02: Major 2 as a draft — schedule, scenes, staging, wall settings, capabilities

- **Depends on:** Chunk 01
- **Artifacts consumed:** `re-architecture.md` § What is showing, and how it is
  shown and § Compositing moves to the Player; `data-model.md` § Planned
  entities
- **Deliverables:**
  - `contract/schemas/manifest.v2.schema.json`: a works map (media, mat colour,
    label per work), a schedule of (work, from, until) with gaps as dark hours,
    an optional scene, a staging list, and wall settings (label mode, mat
    proportions, viewing distance). There is no directive block and no
    `render_path`.
  - Capabilities in the heartbeat: geometry, backend and label hardware, as an
    optional block. The heartbeat has no major 2, because adding a block is
    additive.
  - Fixtures, valid and invalid. The invalid ones include a schedule naming a
    work absent from the works map, and overlapping slots.
  - `player-contract.md` § Major 2 (draft): the semantics the schema cannot
    carry. These are clocks and the replay rule, scene lifetime and precedence,
    staging, referential completeness, and the cutover (a major 1 Player refuses
    major 2 and keeps its wall).
  - **Tests:**
    - Root suite: the schema is valid, and the fixtures classify.
    - The rules the schema cannot express (references resolve, slots do not
      overlap) are checked by a small validator in the root test.
    - Display suite: a major 2 fixture is refused by today's reader as an
      unsupported major, and the reader keeps its last manifest. This pins the
      cutover rule the whole of wave 4 relies on.
- **Done when:** all three suites and lint pass; the draft is marked as a draft
  wherever it appears.

### Chunk 03: The wave 2 build plan

- **Depends on:** Chunks 01 and 02
- **Deliverables:** `build-plan-wave-2-seams-and-http.md`, the chunks of
  `re-architecture.md`'s wave 2 row in build order. The order is the package
  rename to `curatarr` and `displayarr`, then the Library/Programming package
  split with the facade, events and reconciliation, then the HTTP routes with
  tokens, then the Player's pull-to-cache. Each chunk has its dispositions and
  tests. `active_build_plan` points at it once this plan is archived.
- **Done when:** the plan exists, and the cumulative review of this plan is
  resolved.
