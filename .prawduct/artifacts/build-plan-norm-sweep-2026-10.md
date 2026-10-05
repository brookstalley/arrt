---
artifact: build-plan
version: 1
scope: norm-sweep-2026-10
branch: chore/norm-sweep-2026-10
partition: serial — one builder; the two ruff chunks touch most files in their plane, so nothing runs beside them
depends_on:
  - artifact: project-preferences
  - artifact: architecture
  - artifact: information-architecture
governed_by:
  - artifact: architecture
    dispositions:
      - "§ Direction, service layer: amended by the owner 2026-10-05 (this plan's Chunk 01 writes it); Chunk 03 builds to the amended text"
  - artifact: information-architecture
    dispositions:
      - "§ Direction, *arr layout: Wanted moves to a top-level section, by the owner's 2026-10-05 ruling (Chunk 06)"
  - artifact: security-model
    dispositions:
      - "§ Direction, outside text: Chunk 01 corrects § Direction's claim of a client-side host check to the server-side mechanism; no code change"
last_validated: null
---

# Build Plan — Norm Health sweep, October 2026

## What this plan is

The fixes and amendments from the Norm Health sweep of 2026-10-05. The
measurements and the owner's rulings are recorded in `project-state.yaml` under
`norm_health` (the 2026-10-05 entry). This plan builds them. It is maintenance:
no new functionality beyond the Wanted move, which the owner ruled.

## Requirements Confidence

**High.** Every item is either a measured defect with an obvious fix (18, which
the owner confirmed in bulk) or a fork the owner ruled on 2026-10-05.

- [DECISION: ruff ALL on arrt and postarr, minus a named ignore list, each ignore with its why in `pyproject.toml` | the owner asked to "go big on ruff"; ALL brings rules ruff adds later without anyone choosing them | owner approved 2026-10-05]
- [DECISION: the ignore list is formatter conflicts (COM812, ISC001), docstring convention (D), copyright header (CPY), exception-message style (EM101, EM102, TRY003), typographic Unicode in prose (RUF001-003), argument counts on keyword-only signatures (PLR0913, PLR0917), deliberate lazy imports (PLC0415), typing-only import moves (TC001-003), implicit namespace packages for tools and tests (INP001), exception-name suffixes (N818); tests also ignore S101, PLR2004, ARG, SLF001, FBT, ANN | each contradicts a house style the code follows on purpose, measured 2026-10-05 at ~1,900 sites across the two planes | owner approved the shape 2026-10-05; individual entries are the builder's and the Critic's to challenge]
- [DECISION: the root plane adds only N and BLE001 | its 2024 modules leave at wave 5, so fixing them for ALL buys nothing | owner approved 2026-10-05]
- [ASSUMPTION: the residual after the ignore list is fixed, not waived, except where a site is a deliberate exception that gets a reasoned per-line `noqa` | MED impact: hundreds of edits | owner can correct]
- [ASSUMPTION: the deployment guard reads its forbidden values from `.env` keys it already loads (`TV_ADDRESS`, `ART_ROOT`, `LATITUDE`, `LONGITUDE`) and from `$HOME`, and adds a structural check: no private-range IPv4 literal and no `/Users/<name>` or `/home/<name>` literal in source. With no values supplied it still runs the structural half and says so | MED impact | owner can correct]

**Not in this plan:** the Wikidata inception plausibility check (filed as a
ready item); seam rule 3's store split, e-paper caption mode and a host check on
browse-plugin previews (filed); #166 (filed for its open choice); rewriting git
history (the owner ruled fix forward).

## Status

- [ ] Chunk 01: Records: amendments, index rows, stale references
- [ ] Chunk 02: The deployment guard stops publishing the deployment
- [ ] Chunk 03: Guards and small fixes the sweep found
- [ ] Chunk 04: Ruff ALL on the display plane; N and BLE001 at the root
- [ ] Chunk 05: Ruff ALL on the curation plane
- [ ] Chunk 06: Wanted becomes a top-level section

### Chunk 01: Records: amendments, index rows, stale references

`.prawduct/` and docs only; no code.

Done when:

- `architecture.md` § Direction: the service-layer norm reads as amended (compose,
  never branch on results; transport-only shapes named; a shared composition lives
  in a service or is pinned by a test both surfaces run); the manifest norm says
  "the routes `contract/routes.json` names" and is steady-state; the heartbeat row
  is re-scoped to the posted payload's key and schema. The departures row for
  handlers is retired, and the docstrings that cite it (`http/api.py`,
  `mcp/bindings.py` module heads) are left for Chunk 03, which changes that code.
- `project-preferences.md`: rows corrected for every plane (black, I, T20 with
  the `.github/scripts` carve-out, ANN naming postarr); print departure says 19;
  secret-log row names the arrt and postarr guards; TV row and NFR point at
  Postarr power control (wave 6+), not Chunks 20/25/27; Wikidata row loses
  "nothing reads them today"; display-independence promoted to Test with
  `test_pull.py`; broad-except row amended (re-raise exempt, same-line pragma);
  naming moved to Linter; four data-model norm rows added; four target
  preferences assigned; Known departures gain `tv_display`/`TV_PANEL_*` (wave 4),
  the root's direct driver imports and `OPENAI_KEY` (wave 5); "dies at the
  legacy retirement" dispositions name wave 5; WCAG rows corrected; *arr row names
  its two tests; fix-not-file row records the "filed, not fixed, because" line.
- `nonfunctional-requirements.md` display-independence transition closed;
  `data-model.md` § Direction: derived and per-device norms in-transition to wave
  4, the Wall ruling moved into Rulings; `design-direction.md:56` Retroactivity;
  `security-model.md` § Direction's host-check sentence describes the server
  mechanism; `information-architecture.md` § Direction records the Wanted move;
  `re-architecture.md` wave 5 names the root tools' move to `postarr/tools`.
- Backlog: four items filed (inception plausibility, ready; seam rule 3 store
  split; e-paper caption mode, cited on the norm's Status line; browse-plugin
  preview host check); #24 updated to the amended boundary; #94 and #130 tidied;
  the 9 recent non-user items without a filing reason get one.
- `uv run pytest tests` green (the root suite reads these artifacts).

### Chunk 02: The deployment guard stops publishing the deployment

Done when:

- `tests/test_config.py`'s guard holds no deployment literal; it takes the
  forbidden values from the environment and `$HOME` and adds the structural check
  (ASSUMPTION above). Its fixtures use documentation values (RFC 5737 addresses,
  made-up coordinates).
- Watched to fail: a planted private-range literal and a planted home path in a
  scratch source file each turn it red; the same plant with no environment values
  set still turns the structural half red.
- `platform-and-dependency-findings.md` and `deploy/README.md` no longer name the
  Pi's hostname or login.
- `git grep` for the old values over tracked files returns nothing.

### Chunk 03: Guards and small fixes the sweep found

Done when:

- `commons.py`: a page record with no `imageinfo` raises `ImageSearchFailure`;
  only `missing` reads as "nothing here". Test watched to fail first.
- `test_design_tokens.py` checks the scrim text pair over the worst-case image.
- arrt's startup secret test iterates `_SECRET_FIELDS`.
- `mcp/tools.py` stops importing `persistence.catalogue`; a test holds that the
  surface layers (`http/`, `mcp/`) import no persistence store or driver module.
- The Player routes' token check is a FastAPI dependency, so the handlers no
  longer branch on its answer; the module heads of `http/api.py` and
  `mcp/bindings.py` describe the amended norm.
- Root module set frozen by a test (File organization); each plane's tests live
  under its own `tests/` (Test location).
- #212: the mat fallback's stored reason and MCP tip name the
  twice-below-the-floor case; tested through the stored reason.
- #198: the discovery-run thread no longer outlives its test's database.
- Every declared suite green; browser suite green.

### Chunk 04: Ruff ALL on the display plane; N and BLE001 at the root

Done when:

- `postarr/pyproject.toml` selects ALL with the ignore list, each entry with its
  why; the residual is fixed or carries a reasoned per-line `noqa`.
- The root selects N and BLE001; the KEY_POWER test name is fixed; the
  re-raise catches pass BLE001 without pragmas; the off-line pragmas move to the
  `except` line.
- No-op and reasonless waivers removed or given reasons.
- postarr suite (with `--group raster`) and root suite green; `ruff check` and
  `black --check` clean on both.

### Chunk 05: Ruff ALL on the curation plane

Done when: as Chunk 04 for `arrt/`, plus the browser suite green (the client is
untouched, but the server it drives is). S608 sites are each read: a query built
from code constants gets a reasoned `noqa`; one built from input is a defect.
ASYNC210 sites in tests are fixed, not waived.

### Chunk 06: Wanted becomes a top-level section

Done when:

- The sidebar shows Wanted as its own section, as in Sonarr and Radarr; Activity
  keeps the rest. `information-architecture.md`'s tables match, and
  `test_screen_tables.py` and the browser suite's sidebar test are updated to the
  new tables, not weakened.
- Operator verification entry queued (visual change).
- Browser suite green.
