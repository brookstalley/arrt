---
artifact: build-plan
version: 1
scope: audit-wave-2
branch: fix/audit-wave-2
base: develop
working-branches: []
last_validated: null
depends_on:
  - artifact: build-plan-audit-wave-1
  - artifact: architecture
  - artifact: re-architecture
  - artifact: player-contract
  - artifact: data-model
  - artifact: information-architecture
  - artifact: security-model
  - artifact: operational-spec
  - artifact: observability-strategy
  - artifact: source-plugins
  - artifact: labels-and-surfaces
  - artifact: project-preferences
governed_by:
  - artifact: architecture
    dispositions:
      - "the Library/Programming seam (one-way imports, facade written as if remote, no new cross-seam foreign key, change carried by events) → conforms: 20 and 21 move code inside `arrt/src/arrt/programming/` only; the guards wave 1 left (the import guard, the foreign-key ratchet) are kept and neither extended nor removed (ruling 9 of 2026-11-19: the store split is not a requirement now); 09 puts the seam's Protocols under a strict type check, which is the mechanism `boundary-patterns.md` assumed and did not have"
      - "operation logic lives only in the service layer; MCP and HTTP are thin → conforms: no chunk of this plan edits `arrt/src/arrt/mcp/`, `arrt/src/arrt/http/api.py` or `arrt/src/arrt/http/models.py` except 11's type fixes, which change no behaviour (the MCP surface belongs to wave 2b's Chunk 45, ruling 3 of 2026-11-19)"
      - "the Player makes only the requests `contract/routes.json` names → conforms: 03 adds no route; 08's Player makes the requests it always makes, against a real server"
      - "seam rule 3 (two SQLite files, no foreign key across the seam) → amended by ruling 9 of 2026-11-19: 01 records under § Direction that it has no wave and is not built toward"
      - "Direction norm 1's home (audit-1 S6) → ruling needed: question 1 of `decisions-arrt-wave-2.md`; 01 does not reword it"
  - artifact: player-contract
    dispositions:
      - "a minor is additive, a released tag is not moved → conforms: 03 cuts contract-v1.2.0 with additions and description changes only, and adds the mechanical check (audit-1 M2) that every valid fixture of a released minor still validates at HEAD"
      - "the contract's text is the package's (`contract/player-contract.md` is a link to the artifact) → conforms: 03 is the only chunk that edits `.prawduct/artifacts/player-contract.md`"
  - artifact: data-model
    dispositions:
      - "per-device runtime state never lives in the catalogue → ruling needed: question 1 of `decisions-arrt-wave-2.md`; 02 corrects only the description beside it (what the file holds today), never the norm's wording"
      - "a persisted format is designed from its consumers' questions → conforms: 06's last-opened record lists its questions before its fields"
  - artifact: labels-and-surfaces
    dispositions:
      - "a label is an output a Player has zero or more of, as a display is (ruling 8 of 2026-11-19) → conforms after 03, which marks the wall heartbeat's two singular label fields superseded by the client heartbeat's per-output report and adds a fixture and a server test of a Player with several labels and no display"
  - artifact: security-model
    dispositions:
      - "§ Direction (outside text reaches the page as text; links only from a named host or checked id) → conforms: 03's `settings_url` is a schema field with a stated check; nothing in this plan renders it (wave 2b's Chunk 31 does, under that check)"
      - "public-repository residue (the token incident's remedy) → conforms after 02, which records the history's addresses and hostname as accepted residue, as the owner ruled ('leave commits alone'; keys not rotated)"
  - artifact: operational-spec
    dispositions:
      - "§ Backup and Restore (the restore path is a deliverable, not a paragraph) → conforms after 06, which makes the restore a test and corrects the runbook's steps to what the test ran"
  - artifact: project-preferences
    dispositions:
      - "a found problem is fixed, not filed → conforms: every server-side row of the audit not closed by wave 1 has a chunk here or in wave 2b, a question, or a stated reason (`ledger-arrt-wave-2.md`)"
      - "delegation policy (feature tests only, fail-first proof, full repo-relative deliverables checked by verify-chunk-refs) → conforms: each chunk names its ceiling and the red it returns; verify-chunk-refs was run on every chunk before this plan was presented"
      - "§ Code Style's tooling list → amendment proposed in 09 (a type checker is added to the lint tier) as a recorded DECISION, not a norm edit by the builder"

partition: "delegated, in four dispatch waves on one integration branch, fix/audit-wave-2, every build delegate in its own isolated worktree reset to that branch. Dispatch A (parallel, eleven delegates): 01, 02, 03, 04, 05, 06, 07, 09, 12, 20, plus 10 once 09's config has merged. Dispatch B (parallel, after 12 merges): 13-19, seven browser delegates on disjoint files; with 21 after 20 merges. Dispatch C: 11 after 09, 10 and 21 merge; 08 after 06 merges AND Arrt Player has tagged a release carrying its recording output (if that tag is not there when C starts, 08 moves to wave 2b and is said so). Dispatch D: 22, the coordinator's integration and boundary review. Serial seams: 20 then 21 then 11 (all write `arrt/src/arrt/programming/display.py` or what it becomes); 09 then 10 then 11 (one mypy override list); 12 then 13-19 (the guard's baseline and the conversion table). Opus-class for 01, 03, 04, 06, 07, 08, 09, 12, 20, 21, which carry design judgment; Sonnet-class for 02, 05, 10, 11, 13-19, which are fully specified. The coordinator holds the integration branch (or names one integrator) and merges each delegate branch with a scoped merge commit (§ Commit subjects). Chunks 30-46 are wave 2b, drafted here and built under their own plan and branch after this one merges (frontmatter `dropped:`)."
dropped:
  - "30: wave 2b, built under build-plan-audit-wave-2b.md on fix/audit-wave-2b after this plan merges"
  - "31: wave 2b, as 30"
  - "32: wave 2b, as 30"
  - "33: wave 2b, as 30"
  - "34: wave 2b, as 30"
  - "35: wave 2b, as 30"
  - "36: wave 2b, as 30"
  - "37: wave 2b, as 30"
  - "38: wave 2b, as 30"
  - "39: wave 2b, as 30"
  - "40: wave 2b, as 30"
  - "41: wave 2b, as 30"
  - "42: wave 2b, as 30"
  - "43: wave 2b, as 30"
  - "44: wave 2b, as 30"
  - "45: wave 2b, as 30"
  - "46: wave 2b, as 30"
---

# Build Plan — Audit wave 2: the ground (2a), and the behaviour it carries (2b)

## What this plan is

Wave 1 of the 2026-11-19 audit merged as #445 (`build-plan-audit-wave-1.md`, still
live until the develop→main release). This plan is **wave 2**: what wave 1 left,
the larger and dependent work, in two plans' worth.

- **Wave 2a, this plan's chunks 01-22, on `fix/audit-wave-2`:** the records, the
  contract's next minor, CI that survives a pool outage, tests of what ships, a type
  checker, the browser suite's retrying assertions, and `DisplayService` split. Almost
  none of it changes what a person or a Player sees; it changes what is checked and
  where code lives.
- **Wave 2b, chunks 30-46, drafted at the end of this file:** the behaviour — one
  health vocabulary, the plugin host's second half, hang on any selection, spend,
  the surface layer, the MCP break the owner allowed once, and the small carried
  items. They are listed under `dropped:` so this plan does not wait on them. When
  this plan merges, the coordinator moves their sections, unchanged and with their
  ids, into `build-plan-audit-wave-2b.md` (`scope: audit-wave-2b`, `branch:
  fix/audit-wave-2b`), and deletes them and the `dropped:` entries here.

**Why two.** Wave 1 was 205 files and 100 commits in one pull request, reviewable
once because each chunk was small. Wave 2 whole would be about 400 files: the
browser conversion alone rewrites 70 test files, the type checker touches 33 source
files, and the split moves 3,000 lines. Mixed with behaviour changes that is not
reviewable honestly, and it fails `planning.md`'s "split when the change types
differ": 2a is moves, checks and records, judged by "nothing changed meaning"; 2b is
behaviour, judged by acceptance. 2b also needs 2a merged: its feature chunks write
their tests on the converted browser files, against the split `DisplayService`, under
the type gate.

Every finding not closed by wave 1 has one row in the gitignored
`.ux-walk/audit-2026-11-19/ledger-arrt-wave-2.md` of the main checkout (a
delegate's worktree does not carry it: the coordinator pastes the cited findings into
each brief or gives the absolute path). The questions still open for the owner are
`decisions-arrt-wave-2.md` beside it. The owner's rulings of 2026-11-19 (ten) are in
`.prawduct/owner-rulings.md` § "2026-11-19: after wave 1 of the audit fixes, nine
rulings", cited below as *ruling N of 2026-11-19*.

| Chunk | Title | Model, effort | Waits for |
|---|---|---|---|
| 01 | Records I: the architecture as built, the re-architecture's status, the seam's rule 3 not built toward | Opus-class, medium | — |
| 02 | Records II: data model, information architecture, the public residue, the dated banners | Sonnet-class, high | — |
| 03 | Contract 1.2.0: transport table, vocabulary, settings address, label shapes, mat default, cross-tag check | Opus-class, high | — |
| 04 | CI that survives a pool outage (ruling 4) | Opus-class, medium | — |
| 05 | The API-drift alarm's known-blocked probes (ruling 5) | Sonnet-class, high | — |
| 06 | The catalogue's life: a migration chain from real old files, a restore, a last-opened record | Opus-class, high | — |
| 07 | A misbehaving plugin, end to end | Opus-class, medium | — |
| 08 | A real Player against a real server | Opus-class, high | 06; Arrt Player's tag with a recording output |
| 09 | A type checker: mypy, the seam strict, the gate, the first modules | Opus-class, medium | — |
| 10 | Types II: the Library's sources, services and acquisition | Sonnet-class, high | 09 |
| 11 | Types III: Programming, the HTTP layer and Ask; no overrides left | Sonnet-class, high | 09, 10, 21 |
| 12 | Browser I: the guard, the conversion table, the two flaky files | Opus-class, medium | — |
| 13 | Browser II: Walls | Sonnet-class, high | 12 |
| 14 | Browser III: Players, the sidebar, Settings and Status | Sonnet-class, high | 12 |
| 15 | Browser IV: Artworks and the Work page | Sonnet-class, high | 12 |
| 16 | Browser V: Themes, Topics and the Artist page | Sonnet-class, high | 12 |
| 17 | Browser VI: Search and identity | Sonnet-class, high | 12 |
| 18 | Browser VII: Ask, Get and Queue | Sonnet-class, high | 12 |
| 19 | Browser VIII: Review | Sonnet-class, high | 12 |
| 20 | `DisplayService` I: the feed publisher | Opus-class, high | — |
| 21 | `DisplayService` II: scenes, reports, themes and walls; the facade | Opus-class, medium | 20 |
| 22 | Integration and the boundary review (the coordinator's) | — | all |

## Goals

- **Response taken:** proceed. The owner asked for substantially all identified
  product issues to be fixed by delegated builders under this repository's
  governance, and answered every question put to them on 2026-11-19 (*rulings 1-10*;
  WAL was left to the coordinator's judgement, recorded below). Nothing older is held;
  three new questions are asked (`decisions-arrt-wave-2.md`).
- **Product:** the household's server is checked where it is assembled — a real
  Player against it, a real old catalogue migrated, a backup restored, a hung plugin
  through a real Get — and its records say what is true, so the next session reads
  the present once.
- **Architecture, what must hold:** the four seam rules (`architecture.md` §
  Direction) get a mechanical check (09). `DisplayService`'s public surface does not
  change in 2a (20, 21): every caller and every test keeps calling
  `services.display.<method>`. The contract moves to 1.2.0 additively (03). Nothing
  here edits `arrt/src/arrt/mcp/` (ruling 3 gives the MCP surface to one chunk of
  2b).
- **What must stay possible (ruling 8):** several label outputs on one Player, and a
  Player with labels and no display. 03 checks the contract describes both and
  removes the one singular assumption it carries.
- **Constraints:** a delegate runs feature tests only (`project-preferences.md` §
  Workflow, `Delegate verification`); every new or rewritten check comes back with its
  failing output against today's code or a re-break, naming the input that trips it
  (`Delegation`, rule 2). A test is a contract: where a chunk must change an existing
  assertion, the assertion is listed in its section (§ Rewritten assertions), never
  changed quietly.
- **Tradeoffs accepted:**
  - 20 and 21 keep `DisplayService` as a facade of one-line delegations, so the class
    still has its ~66 public names. Cohesion moves into five modules; the surface
    keeps one door. Worth revisiting when 2b's Chunk 45 rewrites MCP's bindings and
    2b's Chunk 38 rewrites HTTP's: they can call the collaborators directly, and the
    facade can then shrink.
  - 04's fallback runs no browser suite: during a pool outage a pull request merges
    on governance, contract and curation evidence alone. The next pool run on
    `develop` is the browser's verdict.
    *(Note, 2026-11-19, after the boundary review: there is no such run. No workflow
    runs on a push to `develop` or `main` (`tests.yml` runs on `pull_request` and
    `workflow_dispatch` only), so a fallback's tree gets no browser verdict on its own.
    What exists instead: a second, non-required job in `tests.yml`, "The browser suite
    ran on the pool", green when the pool gave the verdict and red after a fallback,
    naming how to get one (re-run all jobs once the pool is back, or `testament run
    --json=summary --suite browser` on the branch's head). The required check stays
    green on a fallback, per ruling 4.)*
  - The type gate (09-11) is mypy's defaults plus five flags, not `--strict`, except
    for the seam's modules. A strict tree is a later ratchet.
- **What I would do differently (the advisor's position):** cut 13-19 to the files
  with flake history and leave the rest to a guard that forbids *new* one-shot reads
  — about half the cost for most of the value. I have not, because the owner asked
  for substantially all, the conversion is mechanical, and a partial conversion
  leaves two styles in one suite for a year. If the pool is loaded, run 13-19 two or
  three at a time; they share nothing.
- **Decisions made in this plan** (each vetoable):
  - `[DECISION: wave 2 is two plans: 2a here (chunks 01-22, fix/audit-wave-2) and 2b (chunks 30-46, fix/audit-wave-2b, its own plan after this one merges) | about 400 files in one pull request mixes moves with behaviour and is not reviewable; 2b's tests are written on 2a's converted files and split service | user can veto/override]`
  - `[DECISION: the type checker is mypy, configured in arrt/pyproject.toml and contract/pyproject.toml, run as a lint-tier step (uv run mypy) beside ruff and black in the CLAUDE.md table and in tests.yml's lint step; the tree runs at mypy's defaults plus check_untyped_defs, warn_unused_ignores, warn_redundant_casts, strict_equality and no_implicit_reexport; the seam's modules (library/facade.py, library/readiness.py, library/events.py, programming/store.py, persistence/catalogue.py, services/container.py's OneCatalogueFile) and contract/src run --strict; the root project is not type-checked | mypy runs under uv with no node toolchain (pyright would add one to the pool image and the dev loop), it is what the audit measured with, and its per-module overrides make a ratchet the config itself states; --strict everywhere would turn 110 errors into several hundred annotation-only ones | user can veto/override]`
  - `[DECISION: the ratchet is a [[tool.mypy.overrides]] block with ignore_errors = true listing modules by name, which 09 starts at the modules failing on its head, 10 and 11 empty, and a root test holds: it fails when a listed module checks clean (so the list only shrinks) and when the list is not sorted | an inline # type: ignore baseline would put 110 ignores in the code for warn_unused_ignores to ratchet, which is noise in every file; a module list is one place, and checking each listed module clean is cheap | user can veto/override]`
  - `[DECISION: the browser conversion maps each one-shot read to Playwright's retrying assertion by a fixed table (Chunk 12), keeping innerText semantics with use_inner_text=True; Page.evaluate reads are out of scope | to_have_text compares textContent by default, which includes hidden text that inner_text omits, so a bare conversion would change what 549 assertions mean; evaluate returns computed values (styles, geometry) that no expect method retries | user can veto/override]`
  - `[DECISION: DisplayService is split into programming/feeds.py, programming/scenes.py, programming/reports.py, programming/themes.py and programming/walls.py, and stays in programming/display.py as the composition facade with its public methods unchanged; it is not renamed in this plan | the facade keeps ~95 surface call sites and ~40 test files (half of them browser files 13-19 own) untouched; the rename is wave 2b's, where 38 and 45 rewrite the callers anyway | user can veto/override]`
  - `[DECISION: the catalogue stays on SQLite's rollback journal; WAL is not adopted in this wave | the durable store holds one connection serialised by a lock, so WAL's main gain (readers not blocked by a writer) has nothing to act on; what it would buy is the daily backup's VACUUM INTO not holding commits for its few seconds, against new failure modes (a -wal and -shm beside the file, recovery that needs a writable directory on a read-only open, a restore by file copy that misses the -wal) in the code that guards the owner's library, one wave after that code's commit, rollback and start-up behaviour all changed. Reopen it when the store has more than one connection, when "database is locked" pauses appear in the journal, or when a backup is measured holding commits long enough to notice (06 makes the backup log its copy's duration, so the last is observable) | the coordinator's judgement, at the owner's delegation ("For WAL, please use your judgment", ruling 10 of 2026-11-19); the owner can veto/override]`
  - `[DECISION: nothing in this wave prepares a Library/Programming split: the store split (#216), moving Programming's file-kept state, the seam's crossing inventory and media authorisation after a split are not planned; what is built and guarded (one-way imports through the facade, events after commit, reconciliation at start, the import guard, the foreign-key ratchet) is kept as it is | ruling 9 of 2026-11-19, "Right now, it's not a requirement"; the DisplayService split (20, 21), the seam's strict type check (09) and the one health model (2b) are cohesion and correctness work that share files with the split and stay | user can veto/override]`
  - `[DECISION: the real-Player test lives in Arrt, on the pool, and runs Arrt Player from a pinned git ref in an environment of its own, with a recording output the Player provides | Arrt's pool tests the shipped pair on every server change; installing the Player into the server's environment would clash on arrt-contract (the server uses its editable HEAD, the Player its tag); the Player's planner recommended the same (W2-1) | user can veto/override]`
  - `[DECISION: when the pool cannot give a verdict, CI retries for ten minutes and then runs lint, the governance, contract and curation suites on the GitHub runner directly with uv (no testament), skipping only the browser suite, and says so in the job summary; the job then passes or fails on what it ran | ruling 4 wants an outage not to block every merge, and the 2026-11-18 ruling wants no heavy builds on GitHub's runners: the fallback spends minutes only during an outage, about five, and the browser suite (the heavy one, needing Chrome) is the one it gives up | user can veto/override]`
  - `[DECISION: a known-blocked probe is a row in .github/known-blocked.json (the test it covers, the issue, an expiry no more than 60 days out), the freshness check counts it fresh while unexpired, and an expired row fails by name | ruling 5; an expiry keeps "blocked" from becoming permanent silence | user can veto/override]`
  - `[DECISION: the catalogue records which release last opened it, and when, in a one-row catalogue_opened table (not PRAGMA user_version, which wave 1 uses as the migration-in-progress mark); a release opening a file whose recorded release is newer refuses to start, naming both | audit-2 S9's remainder and audit-2's suspected silent downgrade; the guard protects only downgrades to releases that carry it, and says so | user can veto/override]`
    - *Amended 2026-11-19, after the boundary review (Chunk 06's fix):* **the guard compares a catalogue shape generation, not release numbers.** `catalogue_opened` gains `schema_generation`, the integer `persistence/file.SCHEMA_GENERATION` its code expects; a release refuses a file recorded at a higher generation and opens one at its own or lower, whatever release wrote it, so a rollback across no shape change (0.12.1 to 0.12.0, or two `develop` builds sharing one version string) opens. The generation is raised by hand at every step added to the open and at any table, column or index taken away or redeclared; `arrt/tests/unit/test_schema_generation.py` holds each generation's shape and steps (`arrt/tests/fixtures/catalogue-generations.json`), lets the shape only grow within a generation, and fails otherwise. The open that raises a recorded generation copies the file first, and the refusal names the copies beside the file that the refusing release opens, or says there are none. A row from before generations (release, no generation) opens unless its release is numbered later than this code's (the earlier guard's one refusal, kept); a recorded release this code cannot read no longer stops a start; this code's own release must be three numbers before anything is written. *Rejected:* a fingerprint of the DDL text, which a reformat changes and which refuses rollbacks across additions an older release ignores; comparing the file's shape with this code's, which cannot tell a column a newer release dropped from one an older file never had, and so cannot see the downgrade it exists for. *Limit:* a new value written into a column an older release reads (a new enum member) moves no shape and is seen only if the generation is raised by hand.
  - `[DECISION: contract 1.2.0 marks television_reachable, television_showing_art, has_label_surface and label_surface_working superseded in heartbeat.v1's descriptions, keeps them required, and removes nothing; their removal is heartbeat major 2, which nothing needs yet | a required key made optional is a writer change an older reader refuses; the server can stop reading them now (wave 2b's Chunk 30) without the schema moving | user can veto/override]`
  - `[DECISION: the words a person reads for a wall's display states live in the contract, contract/vocabulary.json, and every reader quotes them: the server's client module and the Player's settings page, each with a test against the package | lesson 3 of wave 1: a value two repositories state gets one owner; the contract is the shared ground both already pin | user can veto/override]`
  - `[DECISION: the history's private addresses and hostname are recorded in security-model.md as accepted residue, nothing in use is changed, and the private readers' methods are taken out of the public artifacts' current text (they stay in history) | the owner: "leave commits alone, later we can get that" and "don't sweat the keys"; the private specifics belong in the private repository either way, and procurement-corpus.md already says so of itself | user can veto/override]`
- **Level:** High for 02, 05, 10, 11 and 13-19 (fully specified, mechanical). Medium
  for 01, 03, 04, 06, 07, 08, 09, 12, 20 and 21: each has one design choice its
  builder makes against stated acceptance. What would raise it: 12 and 20 are
  keystones — the coordinator reviews 12's conversion table and 20's first commit (the
  feed guard re-pointed and seen to fire) before 13-19 and 21 are dispatched.

## Commit subjects, so the review can attribute each chunk

Wave 1's boundary review could not attribute most chunks: the delegates' subjects
named the chunk without the plan's scope. Prawduct attributes a commit to a chunk
**only by its subject**, and only when the subject carries this plan's scope
(`plugin/lib/plan_status.py`, `_carries_scope` and `_CHUNK_COMMIT_RE`): the scope as a
conventional commit's `<type>(<scope>):` or as the subject's first word, and the chunk
in one of `(Chunk NN)`, `: Chunk NN`, `closes Chunk NN` or `Chunk NN:`. A path in a
chunk's Deliverables earns no credit. The coverage gate reads the interval along
**first parents**, so the merge commit that brings a delegate's branch in must carry
it too. Every brief quotes this:

- **Every commit a delegate makes:** `<type>(audit-wave-2): <what changed> (Chunk NN)`,
  with `<type>` one of `fix`, `feat`, `test`, `refactor`, `docs`, `ci`, `chore`. For
  example `test(audit-wave-2): the feed guard fires on a feed built in feeds.py (Chunk 20)`.
- **The integrator's merge of each branch:** `git merge --no-ff -m
  "merge(audit-wave-2): <the chunk's title> (Chunk NN)" <branch>`. Never a fast-forward
  and never the default "Merge branch …" subject.
- **The integrator's own fixes:** `fix(audit-wave-2): <what> (Chunk 22)`.
- **The boundary review** names the chunks it covers with `critic-begin --chunks
  01,02,…`, so a subject that slipped is still certified on the record.
- Wave 2b uses `audit-wave-2b` in the same places.

## What wave 1 taught, built into every chunk

1. **Attribution:** § Commit subjects.
2. **Implicit guarantees.** A chunk that replaces or consolidates a mechanism lists,
   under *Implicit guarantees*, what the old one guaranteed without saying so, each
   with the test that holds it. Wave 1 lost three: a file's mode, which errors a broad
   class held, which backup copy a rollback needs.
3. **Shared values.** A value two repositories or two chunks state has one named owner
   (§ Shared values this wave); the other side quotes it and has a test that fails when
   they diverge.
4. **The image.** A chunk whose test reads a file outside `arrt/` says so under *Reads
   outside arrt/*, and the integration step (Chunk 22) builds the image's test stage
   (`docker build --target test`, from `arrt/` with `--build-context repo=.`), not only
   the pool run.
5. **Rewritten tests.** A chunk that must change an existing assertion lists it under
   *Rewritten assertions* with the old assertion and the reason.

## Shared values this wave

| Value | Owner | Quoted by, with the test that fails on divergence |
|---|---|---|
| The display states' household words | 03 (`contract/vocabulary.json`) | wave 2b's Chunk 31 (`core/states.js`); Arrt Player's settings page (the Player's planner) |
| The mat's bottom weight (1.15) | 03 (`contract/vectors/mat-geometry.json`, `defaults`) | `arrt/src/arrt/programming/adequacy.py` (03 itself); `core/mat.js`'s vector test; the Player's `config.py` (the Player's planner) |
| The transport rules (codes, ETag/304, the 404 step-down, the error shape) | 03 (new `contract/transport.json`) | `arrt/tests/contract/test_player_surface.py` (03); the Player's `tests/server_double.py` (the Player's planner) |
| The Player release Arrt tests against | 08 (new `arrt/tests/system/player-ref.txt`) | the Player's planner moves it when it tags; 08's test names it in every failure |
| The mypy override list | 09, then 10, then 11 (serially) | the root ratchet test 09 writes |
| The one-shot-read baseline | 12, then 13-19 each for its own files | the guard 12 writes |

## Shared seams this wave

- `.github/workflows/tests.yml`: 04 owns the job's structure and the pool steps; 09
  adds only the mypy lines inside the existing lint step. Merge 04 first.
- `CLAUDE.md`: 01 edits only § "Change of direction"; 09 edits only the dev-command
  table's rows (adds Type-check). No one else.
- `.testament.toml`: 06 only (it adds `arrt/tests/system` to the curation suite's
  default selection).
- `arrt/pyproject.toml`: 09 owns `[tool.mypy]` and the dev group's mypy line; 06 owns
  `[tool.pytest.ini_options]` markers. No one else.
- `contract/pyproject.toml`: 03 only (its mypy config included).
- `.prawduct/artifacts/operational-spec.md`: 06 owns § Backup and Restore; 02 owns only
  the dated banners.
- `.prawduct/artifacts/project-preferences.md`: 01 owns the norm index's seam row only;
  09 owns § Tooling's list only.
- `.prawduct/artifacts/observability-strategy.md`: 06 owns the `backup.completed` event's
  row only; 02 owns only the dated banner.
- `.prawduct/artifacts/re-architecture.md`: 01 only. `architecture.md`: 01 only.
  `data-model.md`: 02, except the `catalogue_opened` entity, which 06 adds.
- `arrt/tests/conftest.py`: 20 owns the `every_feed_keeps_the_contract` fixture; no one
  else edits it.
- `arrt/tests/browser/conftest.py`: 12 only.
- `arrt/src/arrt/programming/display.py`: 20, then 21, then 11 — never two at
  once.

## Decisions made mid-build

Appended while building, each in the plan's form and as vetoable as the ones above.
Where one changes a chunk's text, the chunk is left as planned and this section is the
later word.

- **2026-11-19 (Chunk 22), as built:** the Library/Programming store split was taken out of
  this wave by the owner's ruling ("Let's not worry about library and programming split.
  Right now, it's not a requirement."), and WAL was not adopted, with the reopening
  conditions the Goals give; both reasons are in `.prawduct/owner-rulings.md` § "2026-11-19:
  after wave 1 of the audit fixes, ten rulings", items 9 and 10. No chunk of 2a prepares
  either.
- **2026-11-19 (Chunk 08), as built, after the boundary review:** the Goals say the
  real-Player test "lives in Arrt, on the pool", so that Arrt's pool tests the shipped pair
  on every server change. As built it is selected only by `-m player_e2e`: the default
  suites deselect it, and the one place that runs it unasked is `image.yml`'s `player` job,
  on a pull request into `main`. The reason recorded for deselecting it (it installs the
  Player from GitHub) holds for the image's test stage and for a machine offline; it does
  not hold for the pool, whose runners reach GitHub (`docs/testing.md` § The real-Player
  test). So the decision is half built: a server change that breaks the pair in a way the
  fixtures miss is found at the release pull request, not at its own. Giving the test a
  suite of its own on the pool, run on every pull request, is the first chunk of the next
  plan (`build-plan-audit-wave-2b.md`); it was not added here because it changes what the
  required check runs and its fallback, which this wave's review had just found wanting.
- **2026-11-19 (Chunks 09 and 11), as built, after the boundary review:** the Goals say the
  type checker runs "as a lint-tier step … in `tests.yml`'s lint step", and that a ratchet
  block lists the modules still failing. Both are superseded. The lint step is ruff and
  black alone again, because running mypy there installed the server's whole runtime on
  GitHub's runner on every pull request, against the 2026-11-18 ruling on GitHub's minutes
  (`.prawduct/owner-rulings.md`). The type check runs once per change, on the pool, as a
  test of the governance suite (`tests/preferences/test_type_gate.py`), over `arrt/` and
  `contract/` with each project's own configuration; `cd arrt && uv run mypy` stays the
  local command. The ratchet was emptied by Chunk 11 and a test now refuses any
  `ignore_errors` override, so there is no list to keep: a type error is fixed.
- **2026-11-19 (Chunk 06), as built, after the boundary review:** the migration chain's list
  of past releases (`RELEASES` in `arrt/tools/old_catalogue.py`, and the dumps beside
  `arrt/tests/fixtures/catalogues/releases.json`) grows by hand, and nothing fails when a
  release that changed the catalogue's shape ships without its dump; the one check holds a
  floor of two. The norm ("a catalogue every past release left opens on today's shape") is
  therefore true only while someone adds the tag. Until a test enforces it, **cutting a
  release whose catalogue shape changed includes adding its tag to `RELEASES` and
  regenerating the dumps**; the next release is one, because this wave adds
  `catalogue_opened`. The enforcing test (the newest release with a schema change has a
  dump, or the release check refuses) is a chunk of the next plan.

## Chunks

### Chunk 01: Records I — the architecture as built, the re-architecture's status, the seam's rule 3 not built toward

- **Type:** doc-only
- **Closes:** audit-1 S5 (the as-built layer, the status headers, the wave-4 row),
  ruling 9 of 2026-11-19 in the records (seam rule 3 has no wave; rule 5's media promise
  corrected), audit-1 M6 (`arrt.services`
  as a surface-side composition tier), audit-7 S2 (the re-architecture's closed waves;
  CLAUDE.md's framing), ruling 1 of 2026-11-19 in the re-architecture
  ("Themes (now *playlists*)").
- **Owns:** `.prawduct/artifacts/architecture.md`,
  `.prawduct/artifacts/re-architecture.md`, `.prawduct/artifacts/feeds-and-players.md`,
  `.prawduct/artifacts/product-brief.md` (its dated banner only), `CLAUDE.md` (§ "Change
  of direction" only), `.prawduct/artifacts/project-preferences.md` (the norm index's row
  for the seam only), and new `.prawduct/artifacts/archive/re-architecture-closed-waves.md`.
- **Must not touch:** any norm's wording (each § Direction's numbered statements) except
  the dated note ruling 9 makes: Direction norm 1's home is question 1 for the owner; `player-contract.md` (03's);
  `data-model.md` (02's).
- **Deliverables:**
  - `.prawduct/artifacts/architecture.md`: § Overview & Topology, § Components &
    Responsibilities (the `display` component), § Communication & Boundaries (the channel
    table), § Failure Modes & Resilience and § Deployment & Version Skew rewritten to
    today's shape — the server on the NAS in one container, Players on their own hosts
    over HTTP on the LAN, the Player routes an inbound surface, no file channel — and the
    2026-07 single-Pi record moved into § Decision Log as a dated entry. `arrt.services`
    recorded as the surface-side composition tier, spanning both roles. Under § Direction's
    seam rules, a dated note (2026-11-19, ruling 9): rule 3 (two SQLite files, no foreign key
    across the seam) has no wave and is not built toward; the rules built and guarded stand.
  - `.prawduct/artifacts/re-architecture.md`: frontmatter `status` and the wave rows
    true (waves 0-5 closed, 4f shipped in v0.7.0); the closed waves' text moved to
    new `.prawduct/artifacts/archive/re-architecture-closed-waves.md` with a pointer;
    § Seam 1 gains the same dated note as `architecture.md` (rule 3 not built toward,
    ruling 9), and § Order of work says #216 has no wave by that ruling; rule 5's sentence
    promising that media could move to the Library's host with no Player change is replaced
    by what is true today (media is served by this server and admitted by any client's
    token) and promises no future; "Themes (now *playlists*)" says *theme*, with the
    contract's `playlist` field named as the one exception until the next breaking
    contract (ruling 1).
  - `.prawduct/artifacts/project-preferences.md`: the norm index's seam row says rule 3's
    foreign-key count is tested and the rest of rule 3 is not built toward (ruling 9),
    where it now says the rest stays the Critic's.
  - `.prawduct/artifacts/feeds-and-players.md`: its status header says what is built.
  - `CLAUDE.md` § "Change of direction": the dated framing becomes the present (two
    products, the contract, the rules that still hold), keeping its four bullets' rules.
- **Acceptance:**
  1. No sentence in the rewritten sections says one host, a file channel, or no network
     between the server and a Player (grep the section text for "one host", "File in
     ART_ROOT", "no network between": none; return the grep).
  2. `uv run pytest tests/preferences/test_citations_resolve.py
     tests/preferences/test_artifact_manifest.py tests/preferences/test_norm_index.py`
     passes with the moved text and the reworded row.
  3. `grep -n "no Player changes"` over `re-architecture.md` returns nothing.
- **Verification ceiling:** `testament run --json --suite governance --
  tests/preferences/test_citations_resolve.py tests/preferences/test_artifact_manifest.py
  tests/preferences/test_norm_index.py`.
- **Model:** Opus-class, medium: rewriting an as-built layer needs reading the code it
  describes.

### Chunk 02: Records II — data model, information architecture, the public residue, the dated banners

- **Type:** doc-only
- **Closes:** audit-1 S7 (the description half: what the catalogue holds per device; the
  norm is question 1), audit-5 F17 (`ia-proposal.md` marked where superseded, the IA's
  header and authority chain), audit-5 F8's record half and ia-proposal's "Library only"
  (ruling 1), audit-5 F11's record half (ruling 2: *the Library*; the screen *Artworks*),
  ruling 6 of 2026-11-19 in the IA ("copy for the walls" and Select-on-the-right are
  confirmed: the "the owner has not ruled" marks go), audit-7 S2 (`data-model.md`'s header
  and planned entities; the dated `Direction changed 2026-09-30` banners whose waves have
<!-- prawduct:allow prawduct/chunk-ref-missing -- the path's absence is the point: this chunk moved the old backlog file into the archive -->
  landed; `.prawduct/backlog.md` archived), audit-4 13 and audit-8 F18 (the public
  residue, as ruled), audit-1 M4's text half is 03's.
- **Owns:** `.prawduct/artifacts/data-model.md` (except the `catalogue_opened` entity, 06's),
  `.prawduct/artifacts/information-architecture.md`, `.prawduct/artifacts/ia-proposal.md`,
  `.prawduct/artifacts/security-model.md`, `.prawduct/artifacts/met-api-findings.md`,
<!-- prawduct:allow prawduct/chunk-ref-missing -- the path's absence is the point: this chunk moved the old backlog file into the archive -->
  `.prawduct/artifacts/procurement-corpus.md`, `.prawduct/backlog.md` (moved to
  new `.prawduct/artifacts/archive/backlog-2026.md`), and the dated banner paragraph only in
  each of `.prawduct/artifacts/api-contract.md`, `.prawduct/artifacts/accessibility-spec.md`,
  `.prawduct/artifacts/boundary-patterns.md`, `.prawduct/artifacts/design-direction.md`,
  `.prawduct/artifacts/nonfunctional-requirements.md`,
  `.prawduct/artifacts/observability-strategy.md`, `.prawduct/artifacts/operational-spec.md`,
  `.prawduct/artifacts/openrouter-api-findings.md` and
  `.prawduct/artifacts/3tears-integration-findings.md`.
- **Must not touch:** any norm's numbered wording; `.prawduct/owner-rulings.md`,
  `.prawduct/reflections.md`, `.prawduct/operator-verification.md` (governance records:
  the coordinator's); `.prawduct/artifacts/architecture.md`, `re-architecture.md` (01's);
  `player-contract.md` (03's).
- **Deliverables:**
  - `data-model.md`: the header's "three changes are planned and not built" and
    § Planned entities say what is built (Watch is); beside the per-device norm, a
    description of what the file holds today (`reported_screens`, `displays.identity`
    and `kind`, `showings`) marked "the norm's wording awaits the owner (question 1 of
    the wave-2 decisions)", the norm itself untouched.
  - `information-architecture.md`: the header true (Watches and four Settings pages are
    built); the authority chain stated as it now runs (the 2026-10-27 rulings live in
    the IA's tables); § Vocabulary gains *theme* (never *playlist* where a person reads,
    ruling 1) and *the Library* (the household's holdings, *Artworks* the screen,
    *collection* only a museum's, ruling 2); "copy for the walls" and Select's place
    cite ruling 6 and lose their awaiting marks, in § Vocabulary and § Open questions.
  - `ia-proposal.md`: each superseded section marked with what superseded it; "Library
    only" for a theme corrected to Programming's.
  - `security-model.md`: the history's residue (the 2024 commits carrying an RFC1918
    address, the commit carrying the Pi's mDNS hostname and login) recorded as accepted
    by the owner's words of 2026-11-19, nothing in use changed; the CI OpenRouter key's
    ceiling stays recorded as unknown.
  - `met-api-findings.md` and `procurement-corpus.md`: the private readers' methods (how
    the bot checks are passed, the embedded field names) replaced by one sentence saying
    they are in the private repository; the contradiction at `procurement-corpus.md`'s
    MoMA section resolved.
<!-- prawduct:allow prawduct/chunk-ref-missing -- the path's absence is the point: this chunk moved the old backlog file into the archive -->
  - `.prawduct/backlog.md` moved to new `.prawduct/artifacts/archive/backlog-2026.md`,
    its two "no live tracking home" items named in the move's commit body for the
    coordinator to file or close.
  - Each listed artifact's `Direction changed 2026-09-30` banner rewritten to one line
    pointing at what landed, where every wave it waited on has landed; a banner whose
    wave has not landed stays.
- **Acceptance:**
  1. `grep -rn "Direction changed 2026-09-30"` over the owned files returns only banners
     whose wave is still open, each named in the report with the open wave.
  2. `grep -n "playlist" information-architecture.md ia-proposal.md` returns only the
     contract field, named as such.
  3. The root citation and manifest tests pass after the moves.
- **Verification ceiling:** `testament run --json --suite governance --
  tests/preferences/test_citations_resolve.py tests/preferences/test_artifact_manifest.py
  tests/preferences/test_screen_tables.py tests/preferences/test_norm_index.py
  tests/test_repo_hygiene.py`.
- **Model:** Sonnet-class, high.

### Chunk 03: Contract 1.2.0 — transport table, vocabulary, settings address, label shapes, mat default, cross-tag check

- **Type:** code
- **Exposed API:** the Player contract (`arrt-contract`)
- **Closes:** audit-1 M8 and audit-3's contract conformance (a machine-readable transport
  table), audit-1 M2 and audit-7 M6 (a mechanical cross-tag compatibility check), audit-1
  M3 (the mat's bottom weight as a named default), audit-1 M4 (`mat-geometry.json`'s stale
  `_about`), audit-5 F6b (the Player's settings address; the Player planner's W2-4), the
  vocabulary for audit-5 F4 and audit-6 3 (consumed in wave 2b), ruling 8 of 2026-11-19
  (several labels, a label-only Player), the media sentence corrected (audit-1 S1;
  ruling 9 of 2026-11-19: no split is built toward, so the sentence promises nothing),
  the contract package's own
  type errors (audit-2 S1, the contract half).
- **Owns:** everything under `contract/` (`contract/pyproject.toml` included),
  `.prawduct/artifacts/player-contract.md`, `.prawduct/artifacts/labels-and-surfaces.md`,
  `arrt/src/arrt/programming/adequacy.py`, `arrt/tests/unit/test_adequacy.py`,
  `arrt/tests/contract/test_player_surface.py`, `arrt/tests/contract/test_client_surface.py`,
  `arrt/tests/contract/test_label_surface.py`, and
  new `arrt/tests/contract/test_transport_table.py`.
- **Must not touch:** `arrt/src/arrt/programming/client_heartbeat.py` and every reader of
  the new fields (wave 2b's Chunk 30 reads `settings_url`; Chunk 31 the vocabulary);
  `.github/workflows/tests.yml` (09 adds contract's mypy line).
- **Deliverables:**
  - new `contract/transport.json`: per route in `routes.json`, the answers a Player may
    meet and what each means (`200`, `304` only when `If-None-Match` matches, `401`,
    `403`, `404` and its step-down across majors, `413`'s existence without its number,
    which stays the server's), the error body's shape, and the ETag's stability rule;
    shipped in the wheel (`force-include`) and read through the package.
  - new `contract/vocabulary.json`: the household word for each display state a label or
    wall can be in (`showing_art`, `in_use`, `dark`, `no_screen`, `unreachable`, and the
    server's `unassigned` and `silent`), from the words Walls shows today
    (`arrt/src/arrt/http/static/screens/walls.js`'s badge table), with `unassigned` as
    *No Player yet*, a setup step.
  - `contract/schemas/client-heartbeat.v1.schema.json`: optional `settings_url`, an
    absolute `http` or `https` URI with no user information, query or fragment; its
    description states the server's obligation (render it as a link only after that
    check, never as markup); valid and invalid fixtures.
  - `contract/schemas/heartbeat.v1.schema.json`: `television_reachable`,
    `television_showing_art`, `has_label_surface` and `label_surface_working` described
    as superseded (by `display_state`, and by the client heartbeat's `label_outputs`,
    which reports each label), still required, removal at heartbeat major 2.
  - Ruling 8: a valid client-document fixture with several labels and no walls
    (new `contract/fixtures/client.v1/valid/several-labels-and-no-walls.json`), its index
    row, and a server test in `arrt/tests/contract/test_client_surface.py` that a client
    reporting `panels-and-no-display` is accepted and served a client document naming
    both labels; `labels-and-surfaces.md` states the recorded limit (one panel per Player
    built today) and that nothing in the contract or the tables assumes it.
  - `contract/vectors/mat-geometry.json`: `_about` names what holds the vectors today
    (`arrt/src/arrt/programming/adequacy.py`, `arrt/src/arrt/http/static/core/mat.js`, the Player's compose module), and a `defaults` object
    carrying `bottom_weight`; `arrt/src/arrt/programming/adequacy.py` reads it through the
    package instead of its own constant.
  - The cross-tag check: new `contract/released/1.1.0/` holding the released minor's
    fixtures, index and routes as frozen copies, with new `contract/tests/test_released.py`
    asserting every valid fixture there validates at HEAD, no route or fixture name of a
    released minor is gone within major 1, and each frozen file's hash matches a manifest
    written once; the release step in `player-contract.md` § The package adds "copy the
    release into `contract/released/<version>/`".
  - `player-contract.md`: § Transport points at `transport.json` as the rule's statement;
    the media sentence ("after a Library/Programming split it may name the Library's host,
    and no Player changes") replaced by what holds today: media is served by this server
    and admitted by any client's valid token, and a `url` may still be absolute (the
    fixture `minor-2-media-on-another-host` stands as a reader's obligation), with no
    promise about a split (ruling 9). This file is the package's specification
    (`contract/player-contract.md` links to it and `specification()` serves it from the
    wheel), so a change to its text is a release: by § The package, "a correction that
    changes no document's meaning is a patch" — this one rides 1.2.0 with the rest; the 1.2.0 additions in § Versioning's history; a § "What a
    Player does at 1.2.0" for the Player's planner.
  - `contract/src/arrt_contract/__init__.py` checks clean under `mypy --strict`, with
    `[tool.mypy]` in `contract/pyproject.toml`.
  - `contract/pyproject.toml` version 1.2.0. **The tag `contract-v1.2.0` is cut by the
    coordinator after this plan merges into `develop`**, not by the delegate.
- **Implicit guarantees:** `adequacy.py`'s constant made the server's too-small judgement
  independent of the package at runtime; reading the default through the package must not
  make the production image import a dev-only dependency — `arrt-contract` is a runtime
  dependency of `arrt` (`arrt/pyproject.toml` line naming it under `dependencies`), and a
  test imports `adequacy` with the package's data present (`root()` refuses by name
  otherwise).
- **Reads outside arrt/:** the new test (new `arrt/tests/contract/test_transport_table.py`) reads
  `contract/transport.json` through `arrt_contract`, which the image's test stage installs
  from `/contract` (it copies `contract` already).
- **Acceptance:**
  1. `test_released.py` fails when a valid fixture of `contract/released/1.1.0/` is
     edited at HEAD to break it, and when a route is removed from `routes.json` (return
     both reds).
  2. `test_transport_table.py` drives the real server through every row of
     `transport.json` and fails when a row's code is changed (return the red).
  3. A client heartbeat with `settings_url: "javascript:alert(1)"`, one with user
     information, and one with a query are invalid fixtures that fail validation.
  4. `test_adequacy.py` fails when `defaults.bottom_weight` is changed in the vector file.
  5. The several-labels fixture validates, and the server test serves both labels.
  6. `cd contract && uv run mypy` and `uv run pytest` pass.
- **What the Player must do when `contract-v1.2.0` is cut** (said in
  `player-contract.md` and in the change record): nothing is required, since every change
  is additive. To use it, the Player's planner moves the pin to `contract-v1.2.0`; sends
  `settings_url` from its settings page's bound address; reads `vocabulary.json` for its
  page's status line; replaces its server double's hand-copied rules (arrt-player's tests/server_double.py) with
  `transport.json`; reads the mat's bottom weight from `defaults`; may stop reading the
  superseded fields it writes (it keeps writing them).
- **Verification ceiling:** `testament run --json --suite contract`; `testament run --json
  --suite curation -- arrt/tests/contract arrt/tests/unit/test_adequacy.py`; `cd contract
  && uv run ruff check . && uv run black --check .`. (`contract/` runs all four suites at
  integration, Chunk 22.)
- **Model:** Opus-class, high: a released contract's shape is a lock-in decision.
- **Note, 2026-11-19 (built; Chunk 22):** two departures from the text above, both
  taken by the builder and kept. `adequacy.py` *quotes* the bottom weight (1.15) with a
  test that fails if it differs from `defaults.bottom_weight`, instead of reading it
  through the package at run time: `arrt-contract` is a dev dependency of the server and
  the image's app stage installs without dev dependencies, so reading it would stop the
  server starting. The media fixture the chunk relied on no longer existed, so
  `contract/fixtures/manifest.v2/valid/media-on-another-host.json` and its must-refuse
  twin `contract/fixtures/manifest.v2/invalid/media-url-empty.json` were added. Not built: a must-refuse fixture per schema
  constraint (many constraints still have none), and a duplicate-label-name fixture (no
  schema refuses one). The wall heartbeat answers `422` in FastAPI's own body, not the
  contract's error shape, for a body that is not a JSON object; `transport.json` states
  it as it is, and the fix is wave 2b's. Chunk 22 also corrected `manifest.v2`'s title and
  description, which still said it was a draft nothing read.

### Chunk 04: CI that survives a pool outage (ruling 4)

- **Type:** code
- **Closes:** ruling 4 of 2026-11-19 (the fallback half; branch protection is Chunk 22's
  coordinator step), audit-7 S3's single-point-of-failure half.
- **Owns:** `.github/workflows/tests.yml` (structure and pool steps),
  `.github/scripts/assert_tests_ran.py`, `tests/test_assert_tests_ran.py`,
  `tests/test_default_suite_ci_scope.py`, `docs/testing.md` (its CI paragraph), and
  new `tests/test_ci_fallback.py`.
- **Must not touch:** the lint step's tool lines (09 adds mypy inside it);
  `.github/workflows/image.yml` (08's job is added there).
- **Deliverables:**
  - `tests.yml`: when installing testament from the pool fails, or `testament run`
    answers `verdict: unavailable` (exit 75), the job retries with backoff for up to ten
    minutes, then falls back: it runs on the runner, directly with uv, the commands the
    CLAUDE.md table names for lint, the governance suite, the contract suite and the
    curation suite (no browser suite), and writes in the job summary which suites ran
    where and that the browser suite did not. A `failed` verdict from the pool never
    falls back.
  - `assert_tests_ran.py` reads either path's results, so a fallback that collected
    nothing still fails.
  - `docs/testing.md`: the fallback and its trade, one paragraph.
- **Implicit guarantees:** today's `--no-fallback` guaranteed (a) that green means the
  pool ran every suite, browser included, and (b) that GitHub's minutes are never spent on
  suites. After the change, (a) holds only when the summary says "pool"; `tests/test_ci_fallback.py`
  asserts the summary line exists on both paths and the fallback path names the browser
  suite as not run. (b) holds except during an outage; the test asserts the fallback is
  reachable only from the two unavailable conditions, never from a failed verdict.
- **Acceptance:**
  1. `tests/test_ci_fallback.py` parses the workflow and fails when the fallback can be
     reached from a `failed` verdict, when it would run the browser suite, or when the
     summary step is missing (return each red against a re-break of the workflow).
  2. `actionlint` clean on `tests.yml`.
  3. Unproven until a run: the coordinator forces one fallback run (a bad
     `TESTAMENT_CONSOLE` on a scratch branch) before branch protection goes on (Chunk 22).
- **Verification ceiling:** `testament run --json --suite governance -- tests/test_ci_fallback.py
  tests/test_assert_tests_ran.py tests/test_default_suite_ci_scope.py tests/test_actions_pinned.py`;
  `uv run ruff check . && uv run black --check .` at the root.
- **Model:** Opus-class, medium: the trade between ruling 4 and the 2026-11-18 ruling.

### Chunk 05: The API-drift alarm's known-blocked probes (ruling 5)

- **Type:** code
- **Closes:** audit-7 C2 (#109, #110, #150), ruling 5 of 2026-11-19.
- **Owns:** `.github/workflows/api-drift.yml`, `.github/workflows/drift-freshness.yml`,
  `.github/scripts/check_drift_freshness.py`, `.github/scripts/report_drift_failure.py`,
  `tests/test_check_drift_freshness.py`, `tests/test_report_drift_failure.py`, and
  new `.github/known-blocked.json`.
- **Must not touch:** `arrt/tests/live/` (the probes themselves are unchanged).
- **Deliverables:** `.github/known-blocked.json` names the three blocked probes (by test
  id, issue and an expiry 60 days from the commit); the freshness check counts a tier
  whose only failures are unexpired known-blocked tests as fresh, and an expired row as a
  failure naming the row; the drift report comments "known-blocked until {date}" instead
  of "still failing"; the workflow's header comment says what the file is for.
- **Acceptance:** `test_check_drift_freshness.py` gains: a known-blocked failure is fresh;
  an expired row fails naming it; a failure of a test not in the file still fails (return
  the three reds against the unmodified script where applicable).
- **Verification ceiling:** `testament run --json --suite governance --
  tests/test_check_drift_freshness.py tests/test_report_drift_failure.py tests/test_actions_pinned.py`.
- **Model:** Sonnet-class, high.

### Chunk 06: The catalogue's life — a migration chain from real old files, a restore, a last-opened record

- **Type:** code
- **Closes:** audit-7 S6 (the chain, and restore untested), audit-8 F5a, audit-2 S9's
  remainder (which code last opened the file), audit-2 "suspected" (an older release
  starting silently on a migrated file), the runbook half of #180's context (not #180
  itself, which is a requirements item).
- **Owns:** `arrt/src/arrt/persistence/file.py`, `arrt/src/arrt/persistence/migrations.py`,
  `arrt/src/arrt/persistence/durable.py` (the opening path only), `.testament.toml`,
  `arrt/pyproject.toml` (`[tool.pytest.ini_options]` only),
  `.prawduct/artifacts/operational-spec.md` (§ Backup and Restore),
  `.prawduct/artifacts/data-model.md` (the new entity only), and new
  new `arrt/tests/system/conftest.py`, new `arrt/tests/system/test_migration_chain.py`,
  new `arrt/tests/system/test_restore.py`, new `arrt/tests/unit/test_catalogue_opened.py`,
  new `arrt/tests/fixtures/catalogues/` (one SQL dump per release whose schema differed),
  new `arrt/tools/old_catalogue.py` (how each dump was made, reproducible).
- **Also owns:** `arrt/src/arrt/persistence/backup.py` (the `backup.completed` event only),
  `arrt/tests/unit/test_backup_writer.py`, and `.prawduct/artifacts/observability-strategy.md`
  (that event's row only).
- **Must not touch:** `arrt/src/arrt/programming/` (20 and 21's).
- **The persisted format, its questions first:** the `catalogue_opened` record answers
  (1) the operator before a rollback: which release last opened this file, and when;
  (2) the server at start: was this file opened by a newer release than me; (3) support
  after a failed upgrade: did the last open finish its migrations. Fields follow from
  those three (release version, instant, whether migrations completed) and nothing else.
- **Deliverables:**
  - The fixtures: for each release tag from `v0.1.0` to `v0.11.0` whose catalogue
    schema differs from the one before, a `sqlite3 .dump` of a catalogue that release
    made over a small synthetic seed (no real data), made by the new `arrt/tools/old_catalogue.py`
    in a scratch worktree of the tag.
  - `test_migration_chain.py`: each fixture opened by today's server path
    (`open_configured_catalogue`) migrates to today's schema, keeps its works, themes,
    walls and hangs, clears the migration mark, and leaves the pre-migration copy the
    rollback instructions name.
  - `catalogue_opened` written on every open; a start that finds a newer release recorded
    refuses, naming both versions; `operational-spec.md` records that the guard protects
    only downgrades to releases carrying it, and the one-off measurement of what
    `v0.11.0` does against a file today's code migrated (run once by the delegate, its
    result written there).
  - `test_restore.py`: a real server process (the shared fixture in `conftest.py`: boot
    `python -m arrt` on a free port over a seeded `ART_ROOT`) makes a backup generation;
    the test stops it, restores the generation by the runbook's steps, starts it, and reads
    the works, themes, walls and each wall's published feed back over HTTP.
    `operational-spec.md`'s restore steps are rewritten to what the test runs (whether
    "hang each wall's theme again" is still needed is settled by the test, not by reading).
  - `.testament.toml`: the new `arrt/tests/system` in the curation suite's default selection.
  - `backup.completed` carries `copy_seconds`, the monotonic time `VACUUM INTO` took (today
    it carries path, bytes, kept and removed, and no duration), so the WAL decision's third
    trigger is observable; `test_backup_writer.py` asserts the field is a non-negative number
    read from an injected clock.
- **Implicit guarantees:** the migrations' "any prefix finishes on the next open" holds
  with `catalogue_opened` written (the record is written after migrations, so a crash
  mid-migration leaves "did not finish" — tested); the opening path's hot-journal handling
  from wave 1 (a read-write open, because a read-only one cannot read a hot journal) is kept
  (wave 1's test stays green).
- **Reads outside arrt/:** none at test time (the fixtures are under `arrt/tests/`).
  `.testament.toml` is the root's; the image's test stage collects the new `arrt/tests/system`, so
  the system fixture must run there (no network, no git).
- **Acceptance:**
  1. `test_migration_chain.py` is red on a re-break that drops a column's carry in one
     migration (return it) and green on today's code.
  2. A file recorded as opened by a newer release refuses to start; red today (it starts).
  3. `test_restore.py` reads back the seeded works after restore; a re-break that restores
     without removing the stale journal fails it.
- **Verification ceiling:** `testament run --json --suite curation -- arrt/tests/system
  arrt/tests/unit/test_catalogue_opened.py arrt/tests/unit/test_pre_migration_snapshot.py
  arrt/tests/unit/test_wall_migration.py arrt/tests/unit/test_durable.py
  arrt/tests/unit/test_backup_writer.py`; `cd arrt && uv run ruff check . && uv run black --check .`.
- **Model:** Opus-class, high: a persisted record, a start-up refusal, and a runbook.

### Chunk 07: A misbehaving plugin, end to end

- **Type:** code
- **Closes:** audit-7 S5's end-to-end half (wave 1 tested the host's parts), audit-4 1a's
  end-to-end proof.
- **Owns:** new `arrt/tests/integration/test_a_misbehaving_plugin.py`,
  new `arrt/tests/fixtures/plugins/misbehaving/` (a plugin distribution with an entry point:
  a finder that hangs past its declared deadline, a reader that raises, a finder that
  answers a malformed `FoundImage`), `arrt/tests/plugin_fakes.py`.
- **Must not touch:** `arrt/src/arrt/library/sources/` and `arrt/src/arrt/library/discovery/`
  (wave 2b's 32 and 33 change them; this chunk pins today's behaviour for them to keep).
- **Deliverables:** a real server (the suite's uvicorn fixture) whose loader discovers the
  fixture plugin through its entry point, beside one well-behaved fake; a Get started over
  `/api` finishes within the hung finder's deadline plus a margin, carries the good
  source's answer, and `/api/health` and `/api/sources` show the hung plugin's
  could-not-be-asked count and the raising reader's fault; a second request answered
  while the finder hangs.
- **Acceptance:** red against a re-break that removes the deadline in
  `arrt/src/arrt/library/sources/loading.py` (return it: the Get does not finish); the
  malformed answer is a contained fault on Status.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/integration/test_a_misbehaving_plugin.py arrt/tests/unit/test_plugin_deadlines.py
  arrt/tests/unit/test_source_plugins.py`.
- **Model:** Opus-class, medium: making the real loader find a test plugin without
  installing it into the shared environment.

### Chunk 08: A real Player against a real server

- **Type:** code
- **Closes:** audit-7 C1 (the Arrt half: the sources-derived image's own tests are the
  sources planner's).
- **Waits for:** 06 (the system fixture), and **a tagged Arrt Player release that offers
  a recording output**: an output kind selectable by configuration that needs no device
  and writes what it would draw (each wall's work id and media hash, each label's text)
  to a directory. That is a request to the Player's planner, stated here for it to read.
- **Owns:** new `arrt/tests/system/test_a_real_player.py`, new
  new `arrt/tests/system/player-ref.txt`, `.github/workflows/image.yml` (one job added),
  `arrt/Dockerfile` (a comment only, naming the marker its test stage deselects),
  `docs/testing.md` (one paragraph).
- **Deliverables:**
  - The test boots the server (06's fixture), issues a client token, assigns a wall, hangs
    a theme with two works, then runs Arrt Player from the ref in `player-ref.txt` in an
    environment of its own (`uv tool run --from git+https://github.com/brookstalley/arrt-player@<ref>`,
    cached) with the recording output and a label output. It asserts, from both sides:
    the client poll and its `304` round, the manifest adopted and both works' media fetched
    by hash, the heartbeat read by `/api/walls` as the wall's display state, the label
    drawn, and a revoked token refused and said so in the Player's log.
  - Marked `player_e2e`; the image's test stage deselects it (no network for git there),
    and says so.
  - `image.yml`: on pull requests into `main`, the built `app` image is run and this test
    pointed at it, so the shipped image meets a real Player once a release.
- **Reads outside arrt/:** `player-ref.txt` is inside `arrt/`; the test needs network and
  git on the pool runner (stated in `docs/testing.md`), which it checks first and fails by
  name without, rather than skipping quietly.
- **Acceptance:** red on today's code is not available (nothing exists); instead, red
  against two re-breaks: the server answering `200` where `304` is due, and `/media`
  serving the wrong bytes for a hash (the Player discards them; the test sees no adoption).
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/system/test_a_real_player.py`.
- **Model:** Opus-class, high: two processes, two environments, one verdict.
- **Note, 2026-11-19 (built; Chunk 22):** four differences from the text above. (1) The
  verification line needs the marker: `-m player_e2e` is not in `--suite curation --
  arrt/tests/system/test_a_real_player.py`, and the marker is deselected by `addopts`, so
  as written it collects nothing; the working commands are in `docs/testing.md` § The
  real-Player test. (2) The Player is installed by `git fetch` of the pinned commit and
  `uv sync --frozen --no-dev` into a cache outside the repository, not by `uv tool run
  --from`: that form ignores the Player's lockfile, so it would test a Player no Pi runs.
  (3) `player-ref.txt` pins a commit of the Player's integration branch
  (`fix/audit-wave-2`), not a tag, because no Player tag carrying the file outputs
  existed; it moves to the Player's release commit when one is cut. (4) The `player` job in
  `image.yml` has never run: the docker path (`ARRT_SERVER_IMAGE`) is proven only by a
  pull request into `main` (`operator-verification.md`). The pin of (3) moved the same day
  to the merge of the Player's wave 2 into its `develop`, which no branch deletion can
  leave unfetchable.

### Chunk 09: A type checker — mypy, the seam strict, the gate, the first modules

- **Type:** code
- **Closes:** audit-2 S1 (adoption, the seam, and the modules below: about 45 of today's
  110 errors).
- **Owns:** `arrt/pyproject.toml` (`[tool.mypy]` and the dev group's mypy line),
  `arrt/uv.lock`, `CLAUDE.md` (the dev-command table only), `.github/workflows/tests.yml`
  (the lint step's mypy lines only), `.prawduct/artifacts/project-preferences.md` (§
  Tooling's list only, as the recorded DECISION), new `tests/preferences/test_type_gate.py`,
  new `arrt/src/arrt/services/conformance.py`, and the type fixes in
  `arrt/src/arrt/library/registry/wikidata.py`, `arrt/src/arrt/library/discovery/pool.py`,
  `arrt/src/arrt/library/services/watches.py`, `arrt/src/arrt/persistence/sqlite.py`,
  `arrt/src/arrt/persistence/records.py`, `arrt/src/arrt/logs.py`, `arrt/src/arrt/app.py`,
  `arrt/src/arrt/services/container.py` and `arrt/src/arrt/services/fields.py`.
- **Must not touch:** `arrt/src/arrt/programming/` (20 and 21's), `arrt/src/arrt/mcp/`
  (2b's 45), `arrt/src/arrt/http/`, `contract/` (03 makes it clean).
- **Deliverables:**
  - mypy configured per the plan's DECISION; the override list holds exactly the modules
    still failing after this chunk's fixes.
  - new `arrt/src/arrt/services/conformance.py`: typed assignments that state the SQLite adapter satisfies
    `OneCatalogueFile`, `CatalogueStore` and `ProgrammingStore`, so "written as if remote"
    is checked.
  - The real confusions fixed first: `wikidata.py`'s `ItemId`/`RegistryText` NewTypes,
    `pool.py`'s union appended to typed lists, `watches.py`'s `replace(**dict)`.
  - `test_type_gate.py`: fails when a module in the override list checks clean, when the
    list is unsorted, when a seam module is missing from the strict list, and when the
    lint step or the CLAUDE.md table lacks the mypy command.
- **Acceptance:**
  1. A planted wrong type in `arrt/src/arrt/library/facade.py` fails `uv run mypy` (return the output),
     and a planted Protocol break in the adapter fails it through `conformance.py`.
  2. `cd arrt && uv run mypy` exits 0 on the chunk's head.
  3. `test_type_gate.py` is red when one listed module is fixed and left listed.
- **Verification ceiling:** `cd arrt && uv run mypy && uv run ruff check . && uv run black
  --check .`; `testament run --json --suite governance -- tests/preferences/test_type_gate.py
  tests/preferences/test_tool_config.py`; `testament run --json --suite curation --
  arrt/tests/unit/test_wikidata_client.py arrt/tests/unit/test_image_pool.py
  arrt/tests/unit/test_watches.py arrt/tests/unit/test_container.py`.
- **Model:** Opus-class, medium.
- **Note, 2026-11-19 (built; Chunk 22):** the strict seam names `--strict`'s eight flags
  one by one in the override, not `strict = true`: a `strict` key inside an override turned
  strict on for every module (measured: ten new errors outside the seam).
  `arrt.services.conformance` is the seventh strict module.

### Chunk 10: Types II — the Library's sources, services and acquisition

- **Type:** code
- **Closes:** audit-2 S1 (about 57 errors: `arrt/src/arrt/library/sources/`, `arrt/src/arrt/library/services/`,
  `arrt/src/arrt/library/acquisition/`).
- **Owns:** the type fixes in `arrt/src/arrt/library/sources/loading.py`,
  `arrt/src/arrt/library/sources/smk.py`, `arrt/src/arrt/library/sources/rijksmuseum.py`,
  `arrt/src/arrt/library/sources/navigart.py`, `arrt/src/arrt/library/sources/getty.py`,
  `arrt/src/arrt/library/sources/yale.py`, `arrt/src/arrt/library/sources/nga.py`,
  `arrt/src/arrt/library/services/identity.py`, `arrt/src/arrt/library/services/look.py`,
  `arrt/src/arrt/library/services/previews.py`, `arrt/src/arrt/library/services/pictures.py`,
  `arrt/src/arrt/library/services/settings.py`, `arrt/src/arrt/library/services/get.py`,
  `arrt/src/arrt/library/services/catalogue.py`, `arrt/src/arrt/library/acquisition/mat.py`,
  `arrt/src/arrt/library/acquisition/urls.py`, and `arrt/pyproject.toml` (removing those
  modules from the override list only).
- **Must not touch:** behaviour. A fix that would change what a function returns is
  reported, not made.
- **Acceptance:** each module leaves the override list and `uv run mypy` exits 0; the
  module's existing tests pass unchanged; for each `cast` or narrowing added, the report
  says why it holds.
- **Verification ceiling:** `cd arrt && uv run mypy`; `testament run --json --suite
  curation -- arrt/tests/unit/test_source_plugins.py arrt/tests/unit/test_identity.py
  arrt/tests/unit/test_look.py arrt/tests/unit/test_mat_engine.py
  arrt/tests/unit/test_acquisition_urls.py`.
- **Model:** Sonnet-class, high.

### Chunk 11: Types III — Programming, the HTTP layer and Ask; no overrides left

- **Type:** code
- **Closes:** audit-2 S1 (the rest, except `arrt/src/arrt/mcp/`, which 2b's 45 makes
  clean and removes from the list).
- **Owns:** the type fixes in `arrt/src/arrt/programming/` (after 21),
  `arrt/src/arrt/http/api.py`, `arrt/src/arrt/ask/agent.py`, `arrt/src/arrt/ask/cards.py`,
  and `arrt/pyproject.toml` (the override list, reduced to `arrt.mcp.*`).
- **Acceptance:** the override list names only `arrt.mcp.*`; `uv run mypy` exits 0;
  behaviour unchanged (existing tests unchanged and green).
- **Verification ceiling:** `cd arrt && uv run mypy`; `testament run --json --suite
  curation -- arrt/tests/unit/test_displays.py arrt/tests/unit/test_scenes.py
  arrt/tests/unit/test_ask_agent.py arrt/tests/unit/test_ask_cards.py
  arrt/tests/integration/test_browser_surface.py`.
- **Model:** Sonnet-class, high.
- **Note, 2026-11-19 (built; Chunk 22):** the override list is **empty**, not "reduced to
  `arrt.mcp.*`": no module is excused from `uv run mypy`, `arrt.mcp` included.
  `tests/preferences/test_type_gate.py` still holds the shape, and wave 2b's Chunk 45 must
  keep `uv run mypy` clean while it rewrites that surface.

### Chunk 12: Browser I — the guard, the conversion table, the two flaky files

- **Type:** code
- **Critic mode:** final
- **Closes:** audit-7 S1a (the mechanism and the guard), #441, #442.
- **Owns:** `arrt/tests/browser/conftest.py`, `arrt/tests/browser/test_navigation.py`,
  `arrt/tests/browser/test_walls_last_and_next.py`, `docs/testing.md` (the browser
  section's assertion rule), and new `arrt/tests/unit/test_browser_reads_retry.py`.
- **Deliverables:**
  - The conversion table, written into `docs/testing.md` and quoted by every brief of
    13-19: `assert loc.inner_text() == s` → `expect(loc).to_have_text(s, use_inner_text=True)`;
    `s in loc.inner_text()` → `to_contain_text(s, use_inner_text=True)`; `not in` →
    `not_to_contain_text`; `loc.all_inner_texts() == [..]` → `to_have_text([..], use_inner_text=True)`;
    `loc.count() == n` → `to_have_count(n)`; `loc.get_attribute(a) == v` →
    `to_have_attribute(a, v)`; `assert loc.is_visible()` → `to_be_visible()` (and
    hidden, checked, disabled, enabled, `input_value` → `to_have_value`); a read used to
    compute rather than to assert stays, behind an `expect` of the state it reads. A fixed
    sleep becomes a wait on the condition it stood for; one that proves nothing happens for
    a while stays and says so. A test that seeds a time from `datetime.now` and asserts on
    elapsed time is listed for 2b's Chunk 43 (clocks), not changed.
  - The guard (`test_browser_reads_retry.py`, AST over `arrt/tests/browser/*.py`): counts
    one-shot reads inside `assert` statements and fixed sleeps per file, and fails when a
    file's count differs from its baseline in the test (higher: a new one-shot read;
    lower: the baseline was not lowered with the conversion). Baselines for 13-19's files
    are today's counts; this chunk's files are zero.
  - `test_navigation.py` and `test_walls_last_and_next.py` converted; #442's suspected race
    (reading Next once after waiting on another element, state from `datetime.now`)
    removed by waiting on the Next list's own state.
- **How a conversion proves it changed no meaning (for 12-19):** (1) every changed line
  is one of the table's rows, and the report lists any that is not, with its reason;
  (2) the file's guard count goes to zero; (3) the converted file passes three times on
  the pool; (4) two converted assertions per file, chosen by the coordinator, are mutated
  in the client (`arrt/tools/mutation_sweep.py` with `-m browser`) and caught.
- **Rewritten assertions:** none change their expected value; each changes from a
  one-shot read to a retrying assertion of the same value (the table).
- **Acceptance:** the guard is red when one one-shot read is added to a zero-baseline
  file (return it); the two files pass three runs on the pool.
- **Verification ceiling:** `testament run --json --suite browser --
  arrt/tests/browser/test_navigation.py arrt/tests/browser/test_walls_last_and_next.py`
  (three times); `testament run --json --suite curation --
  arrt/tests/unit/test_browser_reads_retry.py`.
- **Model:** Opus-class, medium. The keystone: the coordinator reviews the table before 13-19.

### Chunk 13: Browser II — Walls

- **Type:** refactor
- **Closes:** audit-7 S1a for its files.
- **Owns:** `arrt/tests/browser/test_walls_lead_with_the_work.py`,
  `arrt/tests/browser/test_the_walls.py`, `arrt/tests/browser/test_editing_a_wall.py`,
  `arrt/tests/browser/test_scenes_on_walls.py`, `arrt/tests/browser/test_displays_and_labels.py`,
  `arrt/tests/browser/test_hanging_a_theme.py`, `arrt/tests/browser/test_setting_up_a_wall.py`,
  and their baselines in Chunk 12's guard (set to zero).
- **Deliverables:** about 266 reads converted by Chunk 12's table; the fixed sleeps in
  `test_the_walls.py`, `test_editing_a_wall.py` and `test_hanging_a_theme.py` replaced.
- **Acceptance and proof:** Chunk 12's four steps.
- **Verification ceiling:** `testament run --json --suite browser --` the owned files (three
  times); `testament run --json --suite curation -- arrt/tests/unit/test_browser_reads_retry.py`.
- **Model:** Sonnet-class, high.

### Chunk 14: Browser III — Players, the sidebar, Settings and Status

- **Type:** refactor
- **Closes:** audit-7 S1a for its files.
- **Owns:** `arrt/tests/browser/test_the_clients.py`, `arrt/tests/browser/test_the_sidebar.py`,
  `arrt/tests/browser/test_general_settings.py`, `arrt/tests/browser/test_the_sources_page.py`,
  `arrt/tests/browser/test_watches_screen.py`, `arrt/tests/browser/test_the_history.py`,
  `arrt/tests/browser/test_the_settings_index.py`, `arrt/tests/browser/test_taste_and_reactions.py`,
  `arrt/tests/browser/test_activity.py`, `arrt/tests/browser/test_the_health_panel.py`,
  `arrt/tests/browser/test_spend.py`, `arrt/tests/browser/test_the_status_sources_table.py`,
  `arrt/tests/browser/test_the_debug_view.py`, `arrt/tests/browser/test_the_controls.py`,
  `arrt/tests/browser/test_the_brand_goes_home.py`, `arrt/tests/browser/test_the_shell.py`,
  `arrt/tests/browser/test_keyboard_and_phone.py`, and their baselines.
- **Deliverables:** about 280 reads converted; the fixed sleep in `test_the_shell.py`.
- **Acceptance and proof:** Chunk 12's four steps.
- **Verification ceiling:** as 13, over the owned files.
- **Model:** Sonnet-class, high.

### Chunk 15: Browser IV — Artworks and the Work page

- **Type:** refactor
- **Closes:** audit-7 S1a for its files.
- **Owns:** `arrt/tests/browser/test_the_collection.py`, `arrt/tests/browser/test_the_work_page.py`,
  `arrt/tests/browser/test_one_selection_model.py`, `arrt/tests/browser/test_archiving_a_work.py`,
  `arrt/tests/browser/test_the_grid.py`, `arrt/tests/browser/test_clean_up_facets.py`,
  `arrt/tests/browser/test_tiles_show_the_art.py`, `arrt/tests/browser/test_fact_lists_on_a_phone.py`,
  `arrt/tests/browser/test_the_toolbar.py`, and their baselines.
- **Deliverables:** about 262 reads converted; the fixed sleeps in `test_the_collection.py`
  and `test_the_grid.py`.
- **Acceptance and proof:** Chunk 12's four steps.
- **Verification ceiling:** as 13, over the owned files.
- **Model:** Sonnet-class, high.

### Chunk 16: Browser V — Themes, Topics and the Artist page

- **Type:** refactor
- **Closes:** audit-7 S1a for its files.
- **Owns:** `arrt/tests/browser/test_the_theme_screen.py`, `arrt/tests/browser/test_the_themes_index.py`,
  `arrt/tests/browser/test_the_theme_page_shows_its_art.py`, `arrt/tests/browser/test_the_mat.py`,
  `arrt/tests/browser/test_topics.py`, `arrt/tests/browser/test_topics_before_any_are_held.py`,
  `arrt/tests/browser/test_the_artist_page.py`, and their baselines.
- **Deliverables:** about 263 reads converted; the fixed sleeps in `test_the_theme_screen.py`,
  `test_the_themes_index.py` and `test_topics.py`.
- **Acceptance and proof:** Chunk 12's four steps.
- **Verification ceiling:** as 13, over the owned files.
- **Model:** Sonnet-class, high.

### Chunk 17: Browser VI — Search and identity

- **Type:** refactor
- **Closes:** audit-7 S1a for its files; #371's first case
  (`test_search_and_artist_states.py`; the second case is a curation test and stays on #371).
- **Owns:** `arrt/tests/browser/test_search_one_world.py`,
  `arrt/tests/browser/test_the_search_results_page.py`,
  `arrt/tests/browser/test_pages_for_what_is_not_held.py`,
  `arrt/tests/browser/test_search_in_two_scopes.py`,
  `arrt/tests/browser/test_similar_artists_and_identity.py`,
  `arrt/tests/browser/test_names_that_link.py`, `arrt/tests/browser/test_search_and_artist_states.py`,
  `arrt/tests/browser/test_the_way_back.py`, `arrt/tests/browser/test_copy_says_it_once.py`,
  and their baselines.
- **Deliverables:** about 250 reads converted; the fixed sleeps in `test_search_one_world.py`,
  `test_search_in_two_scopes.py` and `test_similar_artists_and_identity.py`.
- **Acceptance and proof:** Chunk 12's four steps.
- **Verification ceiling:** as 13, over the owned files.
- **Model:** Sonnet-class, high.

### Chunk 18: Browser VII — Ask, Get and Queue

- **Type:** refactor
- **Closes:** audit-7 S1a for its files.
- **Owns:** `arrt/tests/browser/test_asking.py`, `arrt/tests/browser/test_getting.py`,
  `arrt/tests/browser/test_acquisition_states.py`, `arrt/tests/browser/test_the_run_view.py`,
  `arrt/tests/browser/test_wanted.py`, `arrt/tests/browser/test_the_look.py`,
  `arrt/tests/browser/test_failures_beside_the_control.py`, `arrt/tests/browser/test_the_confirmation.py`,
  `arrt/tests/browser/test_component_rules.py`, `arrt/tests/browser/test_shared_rules_and_phone.py`,
  `arrt/tests/browser/test_no_machine_dates.py`, and their baselines.
- **Deliverables:** about 235 reads converted; the fixed sleeps in `test_asking.py`,
  `test_the_run_view.py` (eight), `test_wanted.py`, `test_the_look.py` and
  `test_no_machine_dates.py`.
- **Acceptance and proof:** Chunk 12's four steps.
- **Verification ceiling:** as 13, over the owned files.
- **Model:** Sonnet-class, high.

### Chunk 19: Browser VIII — Review

- **Type:** refactor
- **Closes:** audit-7 S1a for its files.
- **Owns:** `arrt/tests/browser/test_the_review_grid.py`, `arrt/tests/browser/test_reviewing_a_get.py`,
  `arrt/tests/browser/test_review_trust.py`, `arrt/tests/browser/test_review_folds.py`,
  `arrt/tests/browser/test_pictures_where_a_person_decides.py`, `arrt/tests/browser/test_to_review.py`,
  and their baselines.
- **Deliverables:** about 146 reads converted; the fixed sleeps in `test_reviewing_a_get.py`
  and `test_review_trust.py`.
- **Acceptance and proof:** Chunk 12's four steps.
- **Verification ceiling:** as 13, over the owned files.
- **Model:** Sonnet-class, high.

### Chunk 20: `DisplayService` I — the feed publisher

- **Type:** refactor
- **Critic mode:** final
- **Closes:** audit-1 S4 and audit-2 S6 (the feed half; #382 and #307 partly).
- **Owns:** `arrt/src/arrt/programming/display.py`, new `arrt/src/arrt/programming/feeds.py`,
  `arrt/src/arrt/services/container.py` (the wiring of Programming only),
  `arrt/tests/conftest.py` (the `every_feed_keeps_the_contract` fixture only),
  `arrt/tests/unit/test_feed_guard.py`, and new `arrt/tests/unit/test_feed_publisher.py`.
- **Must not touch:** any public method's name or signature on `DisplayService`; the
  surfaces; browser tests.
- **Deliverables:** `FeedPublisher` in the new `arrt/src/arrt/programming/feeds.py` holds the feeds'
  transaction (`_publishing`, `_published`, `_write_staged`), the manifest
  (`build_manifest`, `sync`), keeping feeds true to the Library (`on_work_changed`,
  `reconcile` and its helpers), and the feed's schedule (`_sync_v2` through
  `_pinned_work_ids`); `DisplayService` delegates. Moves verbatim where they can be
  (reviewable with `git diff --color-moved`), and the report lists every line that is not
  a move.
- **Implicit guarantees (each with its test):**
  1. **The feed guard checks every published feed.** `conftest.py` patches
     `as_v2_document` *in `display.py`'s namespace*; once the builder lives in `feeds.py`
     that patch checks nothing and every test still passes. The fixture moves to the name
     the publisher calls, and `test_feed_guard.py` gains a case that publishes a feed
     breaking the contract through the real publisher and sees the guard fail.
  2. A feed is written as the publishing transaction's last step, under the store's lock,
     and a failed write rolls the act back (wave 1's decision): wave 1's
     `test_a_hang_whose_manifest_cannot_be_written_is_not_recorded` stays green unchanged.
  3. One reconcile per bulk act (`WorkChanged.work_ids`): `test_reconciliation.py` unchanged.
  4. `on_work_changed` is subscribed to the Library's events exactly once: a new test
     counts the subscriptions after the container is built.
  5. Startup `reconcile` still runs from `__main__.py` and republishes a feed whose theme
     is not the one hung: `test_startup.py` unchanged.
  6. Scenes and heartbeats reach the publisher through the same store transaction (no
     second lock): the scene and showings tests unchanged.
- **Acceptance:** the five unchanged test files above pass; the new guard case is red when
  the fixture is left patching `display.py` (return it); `display.py` loses the moved
  lines (return the line counts before and after).
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_feed_guard.py arrt/tests/unit/test_feed_publisher.py
  arrt/tests/unit/test_reconciliation.py arrt/tests/unit/test_major_2_feed.py
  arrt/tests/unit/test_manifest.py arrt/tests/unit/test_programming_consistency.py
  arrt/tests/unit/test_scenes.py arrt/tests/unit/test_showings.py
  arrt/tests/integration/test_startup.py arrt/tests/contract/test_player_surface.py`.
- **Model:** Opus-class, high. A keystone: the coordinator reads the first commit (the
  guard re-pointed and seen to fire) before 21.
- **Note, 2026-11-19 (built; Chunk 22):** `on_work_changed` stays on the facade (it composes
  the publisher's `reconcile` with the themes' `offer_destinations`), and `get_wall`,
  `get_theme` and `pace` were added to `FeedPublisher` as well as kept on the facade.
  `feeds.py` logs as `arrt.programming.display`, as the four modules of Chunk 21 do, and a
  test holds that name.

### Chunk 21: `DisplayService` II — scenes, reports, themes and walls; the facade

- **Type:** refactor
- **Closes:** #382 (scenes in `scenes.py`), audit-1 S4 and audit-2 S6 (the rest), audit-1
  M9b for the moved files ("display plane" words in what moves).
- **Owns:** `arrt/src/arrt/programming/display.py`, new `arrt/src/arrt/programming/scenes.py`,
  new `arrt/src/arrt/programming/reports.py` (heartbeats, showings, size judgements),
  new `arrt/src/arrt/programming/themes.py` (themes, membership, *not this one again*),
  new `arrt/src/arrt/programming/walls.py` (walls and their settings),
  `arrt/src/arrt/services/container.py` (Programming's wiring only), and
  new `arrt/tests/unit/test_display_facade.py`.
- **Deliverables:** the four collaborators, each holding its section of today's
  `DisplayService`; `DisplayService` in `display.py` is the composition facade, its module
  docstring saying so and naming each collaborator; `describe_wall_status`,
  `feed_notice` and the view dataclasses stay importable from `display.py` (re-exported)
  so no caller changes.
- **Implicit guarantees (each with its test):** every public name `DisplayService` had
  still exists with the same signature (`test_display_facade.py` compares against the
  list taken from the class on this chunk's base, written into the test once); reads inside
  the transaction in the twelve acts wave 1 fixed stay inside it
  (`test_programming_consistency.py` unchanged); the scene settling a heartbeat triggers
  still runs inside the heartbeat's act (`test_scenes.py` unchanged).
- **Acceptance:** every existing test that calls `services.display` passes unchanged;
  `display.py` holds only the facade (return its length).
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_display_facade.py arrt/tests/unit/test_displays.py
  arrt/tests/unit/test_scenes.py arrt/tests/unit/test_showings.py arrt/tests/unit/test_schedule.py
  arrt/tests/unit/test_programming_consistency.py arrt/tests/unit/test_deleting_a_wall.py
  arrt/tests/unit/test_artwork_lifecycle.py arrt/tests/integration/test_theme_routes.py
  arrt/tests/integration/test_scene_routes.py arrt/tests/contract/test_mcp_scenarios.py`.
- **Model:** Opus-class, medium.

### Chunk 22: Integration and the boundary review (the coordinator's)

- **Type:** cumulative-final
- **Owner:** the coordinator, or one integrator it names; no build delegate.
- **Deliverables:** each delegate branch merged with its scoped merge commit (§ Commit
  subjects), 03 before 09 and 04 before 09; new `.prawduct/changes/audit-wave-2.md`, the
  change record, naming each chunk's findings, the contract's 1.2.0 additions and what the
  Player does about them; the operator-verification entries for 08 and 06's runbook.
- **Done when:** on the merged head the four suites pass (`testament run --json`); the
  image's test stage builds (`docker build --target test` in `arrt/` with
  `--build-context repo=.`), because 03, 06 and 08 add tests that read through the package
  or deselect by marker; the coordinator has read each delegate's fail-first evidence and
  12's and 20's keystones; the Critic's cumulative review finds nothing blocking.
- **After the merge into `develop`:** cut `contract-v1.2.0`; force one fallback run of 04
  on a scratch branch and see it pass on the runner; **then** turn on required checks on
  `develop` and `main` in this repository (ruling 4), and tell the Player's and the
  sources' coordinators (the sources repository's CI runs on the pool and needs the same
  fallback before its protection goes on; the Player's runs on GitHub and needs none). Move
  chunks 30-46 into `build-plan-audit-wave-2b.md` and cut `fix/audit-wave-2b`.

## Wave 2b — drafted here, built under its own plan

Chunks 30-46 are listed under `dropped:` above and are not this plan's work. Their
dispatch order, for the 2b plan's `partition:`: **first, in parallel:** 30, 32, 34, 35, 37,
39, 40, 42, 43, 44; **then:** 31 (after 30), 33 (after 32), 36 (after 35), 38 (after 37),
41 (after 31 and 40); **then** 45, which owns `arrt/src/arrt/mcp/` for the whole of wave 2
and is dispatched after 30, 32, 33, 35, 38 and 40 have merged, so it brings MCP to their
new fields in the one break the owner allowed; **last** 46. 2b's own decisions:

- `[DECISION: the household words for a wall's and a Player's states are: Showing, Screen off, In use, No screen, Not known, Not reporting, No Player yet (walls, from contract/vocabulary.json); No token yet, Waiting for its first report, Reporting, Not heard from since {date}, Report unreadable (Players); a setup step (No Player yet, No token yet, Waiting for its first report) is never a fault on the top bar or the System badge | audit-6 3 and audit-5 F4 ask for one story, and a wall with no Player is a step the household has not taken yet, not "Unwell" | user can veto/override]`
- `[DECISION: works the queue holds as failed are a health observation: their count, with the age of the newest, reaches the top bar and the System badge, linking to Queue | audit-6 3: 2,000 failed fetches raised nothing | user can veto/override]`
- `[DECISION: an acquisition's outcome is one of ok, partial_tiles, none_held, unasked, faulted, link_gone or failed (legacy and unclassified); unasked is retried on the queue's next pass, faulted after the plugin's next load, none_held and link_gone are settled until the work's Wikidata item changes | audit-4 14 and #318: the interface's three answers survive only as prose today; the retry rule follows from what each answer means | user can veto/override]`
- `[DECISION: a finder may answer link_gone (interface 1.6, additive): every page the registry linked for this work is gone at the museum; phase two treats it as settled for that source and records it apart from could-not-be-asked | audit-4 4's second half: the host could not tell "every page gone" from "could not be asked", so such a work never settled | user can veto/override]`
- `[DECISION: the pool answers with the sources that answered within the look's window (30 s) and keeps the slower ones' answers for the work's durable search record, which phase two reads on its next pass | a plugin may now declare up to an hour; a Get must not wait for the slowest; #313 asks for the record anyway | user can veto/override]`
- `[DECISION: a paid call that fails after it was sent records a spend row whose cost is unknown (cost_usd null, settled = unknown), with its model and run; when the provider answered with a generation id, the cost is looked up and the row settled; the month's total reads "at least $X, and N calls whose cost is unknown" | audit-2 S5; a timed-out non-streaming request returns no id, so its cost, and whether it was billed, is unknowable from the client: the ledger says so instead of saying nothing | user can veto/override]`
- `[DECISION: spend has a page of its own at #spend, reached from the sidebar's budget line and from Status, not a sidebar item: months, each month's categories and Gets, and the calls whose cost is unknown | audit-6 10 and audit-5 F12; the sidebar is guarded by its tables and gains nothing | user can veto/override]`
- `[DECISION: Remove takes a thing out of a set (a theme, a wall); Forget drops a record the household made of something outside (a Player, a Watch, a Wanted item, a taste); Delete destroys a thing with dependents (a wall, a theme); Players' and Watches' Remove… become Forget… | audit-5 F14's UI half | user can veto/override]`
- `[DECISION: the acts on a wall gather on art_display (activate, hang_selection, not_again and the scene acts move there from art_theme); art_theme keeps themes and membership; no tool name is added or removed; art_display's description budget is re-derived in api-contract.md for the larger tool | ruling 3; organised around the browser's objects, Walls and Themes; keeping the frozen tool names breaks agents only where the ruling allows | user can veto/override]`

### Chunk 30: One health model — the server (2b)

- **Type:** code
- **Closes:** audit-5 F4 and audit-6 3 (the server half), the failed-fetches half of audit-6
  3, audit-5 F6b's server half (`settings_url` read and checked).
- **Owns:** `arrt/src/arrt/services/health.py`, `arrt/src/arrt/programming/display_state.py`,
  new `arrt/src/arrt/programming/player_state.py`, `arrt/src/arrt/programming/client_heartbeat.py`,
  `arrt/src/arrt/http/models.py` (the health, wall-state and client models only),
  `arrt/src/arrt/http/api.py` (their handlers only), `arrt/tests/unit/test_display_state.py`,
  and new `arrt/tests/unit/test_player_state.py`.
- **Deliverables:** one server model for a wall's state (`ScreenState`, words quoted from
  the contract's vocabulary) and a Player's (the plan's DECISION), served on `/api/walls`,
  `/api/clients` and `/api/health`; Status's reading carries each wall's state and each
  label output's own state from the client heartbeat, never the superseded fields; the
  failed-acquisition count with its age; `settings_url` exposed only when it passes the
  contract's check. MCP's twins are 45's.
- **Acceptance:** a wall with no Player reads `unassigned` and counts as no fault in
  `/api/health`'s troubles (red today); a heartbeat claiming `television_showing_art: true`
  with `display_state: dark` reads dark on every route (red today on Status's data); a
  `settings_url` of `javascript:` is not served.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_display_state.py arrt/tests/unit/test_player_state.py
  arrt/tests/integration/test_healthz.py arrt/tests/contract/test_client_surface.py`.
- **Model:** Opus-class, high.

### Chunk 31: One health model — the screens (2b)

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-5 F4 and audit-6 3 (the client half), audit-6 6 (the Walls card's
  layout), audit-5 F6b's link (the Players row links to its settings page).
- **Owns:** new `arrt/src/arrt/http/static/core/states.js`,
  `arrt/src/arrt/http/static/screens/walls.js`, `arrt/src/arrt/http/static/screens/clients.js`,
  `arrt/src/arrt/http/static/screens/health.js`, `arrt/src/arrt/http/static/core/status.js`,
  `arrt/src/arrt/http/static/core/sidebar.js`, `.prawduct/artifacts/information-architecture.md`
  (the Walls, Players, Status and top bar rows), and the browser files of those screens.
- **Deliverables:** every screen draws a state's word and glyph from the new
  `arrt/src/arrt/http/static/core/states.js`, which a test holds to the new `contract/vocabulary.json` (Chunk 03's); Status reads the state, not
  `television_reachable`; the Walls card holds at most one notice, chosen by state, and one
  filled act; the top bar and the System badge count faults and failed fetches, never a
  setup step; the Players row's settings link is text and `rel="noopener noreferrer"`.
- **Rewritten assertions:** `test_the_sidebar.py` and `test_the_health_panel.py`
  assertions of "has not reported" for a wall with no Player become "No Player yet",
  because a setup step stops being a fault (the plan's DECISION).
- **Verification ceiling:** `testament run --json --suite browser --` the walls, clients,
  sidebar and health panel files.
- **Model:** Opus-class, high.

### Chunk 32: The plugin host's second half — three answers kept apart (2b)

- **Type:** code
- **Closes:** audit-4 14 (#318), audit-4 4's second half (with the sources planner), the
  Queue's grouping by message text (#318).
- **The persisted format, its questions first:** the acquisition outcome answers (1) the
  queue: retry when, and how soon; (2) Queue: how to group "why these works have no
  picture" without per-work text; (3) Status: which plugin is not answering; (4) MCP and
  `/api/acquisitions/causes`: the same groups by cause; (5) a migration: what an existing
  `failed` row becomes (it stays `failed`, unclassified).
- **Owns:** `arrt/src/arrt/persistence/records.py` (`FetchStatus` only),
  `arrt/src/arrt/persistence/migrations.py` (one widening), `arrt/src/arrt/library/acquisition/service.py`,
  `arrt/src/arrt/library/acquisition/queue.py`, `arrt/src/arrt/library/sources/plugin.py`,
  `arrt/src/arrt/library/sources/loading.py`, `arrt/src/arrt/library/discovery/images.py`,
  `arrt/src/arrt/library/discovery/phase_two.py`, `arrt/src/arrt/http/static/screens/activity.js`
  (Queue's grouping), `docs/source-plugins.md`, `.prawduct/artifacts/source-plugins.md`, and
  the tests of those modules.
- **Deliverables:** the outcomes and retry rule of the plan's DECISION; interface 1.6's
  `link_gone`; Queue groups by outcome and source.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_acquisition_service.py arrt/tests/unit/test_acquisition_queue.py
  arrt/tests/unit/test_source_plugins.py arrt/tests/integration/test_acquisition_routes.py
  arrt/tests/integration/test_a_misbehaving_plugin.py`; `testament run --json --suite
  browser -- arrt/tests/browser/test_acquisition_states.py`.
- **Model:** Opus-class, high.

### Chunk 33: The pool answers fast sources first, and each search is recorded (2b)

- **Type:** code
- **Closes:** #313 (a durable record of each search; audit-4 3a's remainder), the pool's
  wait for every source (wave 1's stated residual).
- **The persisted format, its questions first:** a search record answers (1) Status after a
  restart: has this plugin answered anything in N searches; (2) phase two: is any source
  still owed an answer for this work; (3) Sources' yields: what each source contributed;
  (4) retention: how long a record is kept (tied to #308's rule when it lands; until then,
  the newest per work and source).
- **Owns:** `arrt/src/arrt/library/discovery/pool.py`, `arrt/src/arrt/library/services/look.py`,
  `arrt/src/arrt/persistence/discovery.py`, `arrt/src/arrt/persistence/sqlite_discovery.py`,
  `arrt/src/arrt/services/health.py` (the plugin section only, after 30), and their tests.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_image_pool.py arrt/tests/unit/test_look.py
  arrt/tests/unit/test_discovery_runner.py arrt/tests/integration/test_a_misbehaving_plugin.py`.
- **Model:** Opus-class, high.

### Chunk 34: Hang on any selection (2b)

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-5 F9 (the selection half; a wall-side entry and hanging for a duration
  are question 2).
- **Owns:** `arrt/src/arrt/http/static/core/selecting.js`, `arrt/src/arrt/http/static/core/selection.js`,
  `arrt/src/arrt/http/static/screens/artists.js`, `arrt/src/arrt/http/static/screens/search.js`,
  `arrt/src/arrt/http/static/screens/topics.js`, `arrt/src/arrt/http/static/screens/collection.js`,
  `.prawduct/artifacts/information-architecture.md` (those rows), and
  new `arrt/tests/browser/test_hanging_a_selection.py`.
- **Deliverables:** *Hang…* in every selection's toolbar (Artworks, an Artist's works, Search,
  a Topic's held works; an Artists selection hangs their held works), through `hang_selection`.
- **Verification ceiling:** `testament run --json --suite browser --
  arrt/tests/browser/test_hanging_a_selection.py arrt/tests/browser/test_one_selection_model.py`.
- **Model:** Sonnet-class, high.

### Chunk 35: Spend — the paid call that fails after it was sent (2b)

- **Type:** code
- **Foreign API:** OpenRouter (the generation lookup)
- **Closes:** audit-2 S5.
- **The persisted format, its questions first:** a spend row answers (1) the month's total
  and how sure it is; (2) a run's cost; (3) Ask's reply cost; (4) which calls' cost is
  unknown and why; (5) whether a row was later settled by the provider.
- **Owns:** `arrt/src/arrt/library/discovery/openrouter.py`, `arrt/src/arrt/library/discovery/phase_one.py`,
  `arrt/src/arrt/library/acquisition/mat.py`, `arrt/src/arrt/ask/agent.py`,
  `arrt/src/arrt/persistence/discovery_records.py` (`SpendRecord`),
  `arrt/src/arrt/persistence/sqlite_discovery.py` (`spend_records`),
  `arrt/src/arrt/library/services/spending.py`, and their tests.
- **Deliverables:** step 0, verify-api: read OpenRouter's generation lookup and what a
  timeout returns, from its documentation and one paid probe by hand on this machine
  (`live_api`, the operator's), recorded in `openrouter-api-findings.md`; then the plan's
  DECISION.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_openrouter_client.py arrt/tests/unit/test_phase_one_engine.py
  arrt/tests/unit/test_spending.py arrt/tests/unit/test_mat_engine.py arrt/tests/unit/test_ask_agent.py`.
- **Model:** Opus-class, high.

### Chunk 36: Spend — a page (2b)

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-6 10 and audit-5 F12 (the page halves).
- **Owns:** new `arrt/src/arrt/http/static/screens/spend.js`, `arrt/src/arrt/http/static/app.js`
  (the route only), `arrt/src/arrt/http/static/core/spend.js`, `arrt/src/arrt/http/api.py`
  (one route), `arrt/src/arrt/http/models.py` (one model), `.prawduct/artifacts/information-architecture.md`
  (one row), `tests/preferences/test_screen_tables.py` (the route's name), and
  new `arrt/tests/browser/test_the_spend_page.py`.
- **Verification ceiling:** `testament run --json --suite browser --
  arrt/tests/browser/test_the_spend_page.py arrt/tests/browser/test_spend.py`;
  `testament run --json --suite governance -- tests/preferences/test_screen_tables.py`.
- **Model:** Sonnet-class, high.

### Chunk 37: The surface's edges — not found is 404, configuration imports no service, Ask's own executor (2b)

- **Type:** code
- **Closes:** audit-2 M8, audit-2 M12, audit-2 M10 (Ask's half, after a measurement; MCP's
  half is 45's).
- **Owns:** `arrt/src/arrt/services/errors.py` (a `NotFound` subclass of `ServiceError`), `arrt/src/arrt/http/api.py` (the error handler only),
  `arrt/src/arrt/config.py`, `arrt/src/arrt/ask/agent.py` (the executor only, after 35), and
  their tests.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/integration/test_browser_surface.py arrt/tests/unit/test_container.py
  arrt/tests/unit/test_ask_agent.py`.
- **Model:** Sonnet-class, high.

### Chunk 38: One view model per entity, and one mat act (2b)

- **Type:** code
- **Closes:** audit-2 S7 (the HTTP half and the service half), audit-2 S6's `api.py` by
  resource router, audit-2 M9 if the measurement says so; the `DisplayService` rename (the
  facade's callers move to the collaborators).
- **Owns:** `arrt/src/arrt/http/api.py`, new `arrt/src/arrt/http/routes/`, `arrt/src/arrt/http/models.py`,
  new `arrt/src/arrt/services/views.py`, `arrt/src/arrt/library/acquisition/preparation.py`
  (`set_mat`), `arrt/src/arrt/programming/display.py`, and `arrt/tests/unit/test_surface_parity.py`.
- **Deliverables:** view models in the service layer that HTTP renders and 45 makes MCP
  dump; `PreparationService.set_mat(choice)` taking one tagged choice; `api.py` split by
  resource router with no route's path or answer changed.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_surface_parity.py arrt/tests/integration arrt/tests/contract`.
- **Model:** Opus-class, high.

### Chunk 39: A periodic reconcile (2b)

- **Type:** code
- **Closes:** audit-1 M7.
- **Owns:** new `arrt/src/arrt/programming/feeds.py` (created by Chunk 20; the scheduled
  entry only), `arrt/src/arrt/library/services/scheduler.py` (the job), and
  `arrt/tests/unit/test_scheduler.py`.
- **New execution context:** a scheduled job — logging (one INFO line a pass), the
  bulkhead the other workers use, and shutdown's join are stated and tested.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_scheduler.py arrt/tests/unit/test_reconciliation.py`.
- **Model:** Sonnet-class, high.

### Chunk 40: Small server items (2b)

- **Type:** code
- **Closes:** the `DEZOOMIFY_PATH` and `ARTIC_USER_AGENT` remedies naming settings on
  household pages; `arrt/src/arrt/library/sources/nga.py`'s hand-written rename (onto `arrt/src/arrt/atomic.py`);
  a full disk inside `dezoomify-rs` showing only as an exit code; `ManifestBuild.summarise`'s
  "0 of 1 work … is" (audit-6 19b); the "display plane" and "curation plane" words left in
  `arrt/src` outside `arrt/src/arrt/mcp/` (audit-1 M9b); the cap on outputs one client may report
  (audit-8 F10's remainder); `pictured_artwork_id` on the Artist, Topic and Work pages'
  registry rows (the server half); rulings 1 and 2 in the sentences the server sends a
  person (*theme*, *the Library*); History filtered by work, and a work's record naming the
  Get that brought it (audit-5 F18, the server half: one query parameter on the history
  route and one field on the work's detail model).
- **Owns:** `arrt/src/arrt/library/acquisition/service.py` (`DEPLOYMENT_REMEDIES`),
  `arrt/src/arrt/library/sources/nga.py`, `arrt/src/arrt/library/acquisition/dezoomify.py`,
  `arrt/src/arrt/programming/manifest/builder.py` (`summarise`), `arrt/src/arrt/programming/client_heartbeat.py`
  (the count cap, after 30), `arrt/src/arrt/http/models.py` (the three registry-row models,
  after 30), and the tests that assert those sentences.
- **Rewritten assertions:** the MCP and HTTP tests asserting `summarise`'s sentence verbatim
  change to the corrected sentence (the old one is ungrammatical, audit-6 19b); each is listed
  in the report.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_acquisition_dezoomify.py arrt/tests/unit/test_acquisition_service.py
  arrt/tests/unit/test_manifest.py arrt/tests/unit/test_clients.py
  arrt/tests/integration/test_registry_pages.py`.
- **Model:** Sonnet-class, high.

### Chunk 41: Small client items (2b)

- **Type:** code
- **Visual change:** yes
- **Closes:** `walls.js` `liveScene` joining three walls with " and " (onto `listed`);
  the joiner's untested callers in `work.js` and the Walls "waiting" line; the registry
  rows' thumbnails on the Artist, Topic and Work pages (the client half); numbers formatted
  one way through `arrt/src/arrt/http/static/core/counting.js` (audit-6 16); the Work page linking its
  Get and its own History (audit-5 F18, the client half); a second skip link, past Artworks'
  facets to the first tile (audit-6 22); Remove and Forget (audit-5 F14's UI half);
  rulings 1 and 2 in the client's copy (*the Library*, never *collection* or *catalogue* for
  the household).
- **Owns:** `arrt/src/arrt/http/static/screens/walls.js` (after 31), `arrt/src/arrt/http/static/screens/work.js`,
  `arrt/src/arrt/http/static/screens/topics.js` (after 34), `arrt/src/arrt/http/static/core/counting.js`,
  `arrt/src/arrt/http/static/index.html`, the screens whose copy names the holdings, and their
  browser files.
- **Rewritten assertions:** Players' and Watches' "Remove…" button tests become "Forget…"
  (the plan's DECISION); copy assertions naming "the collection" for the household become
  "the Library" (ruling 2); each listed in the report.
- **Verification ceiling:** the browser files of the screens changed.
- **Model:** Sonnet-class, high.

### Chunk 42: The compose example, hardened (2b)

- **Type:** code
- **Closes:** audit-8's answers (`cap_drop: [ALL]`, a read-only root with named writable
  mounts), `compose.example.yaml`'s retired-unit clause.
- **Owns:** `deploy/nas/compose.example.yaml`, `deploy/README.md` (its compose section),
  `tests/preferences/test_deployment_values.py`.
- **Deliverables:** measured on a scratch container of the `app` image first: the server
  starts, serves `/api/health`, backs up and writes a feed with those settings; then the
  example carries them, and the retired unit's `MemoryMax` clause goes.
- **Verification ceiling:** `testament run --json --suite governance --
  tests/preferences/test_deployment_values.py tests/test_repo_hygiene.py`.
- **Model:** Sonnet-class, high.

### Chunk 43: Test-suite health (2b)

- **Type:** code
- **Closes:** audit-7 S7 (#438: clocks and ids injected into `CatalogueService`,
  `DiscoveryService` and `PictureStore`; curation areas declared), audit-7 M8 (the four long
  UX-walk tests split or cheapened), the browser tests Chunk 12 listed as seeding from
  `datetime.now`.
- **Owns:** `arrt/src/arrt/library/services/catalogue.py`, `arrt/src/arrt/library/services/discovery.py`,
  `arrt/src/arrt/library/services/pictures.py` (the clock and id seams only),
  `.testament.toml` (areas), `arrt/tests/browser/test_the_ux_walk.py`, and the listed tests.
- **Verification ceiling:** the listed tests; `testament run --json --suite curation --`
  the three services' unit tests.
- **Model:** Opus-class, medium.

### Chunk 44: A supported plugin-testing helper (2b)

- **Type:** code
- **Closes:** audit-1 M10 and audit-4 12 (Arrt's half; arrt-sources' imports are the sources
  planner's).
- **Owns:** `arrt/src/arrt/library/sources/__init__.py` (the exported helper),
  new `arrt/src/arrt/library/sources/testing.py`, `docs/source-plugins.md`, and
  new `arrt/tests/unit/test_plugin_testing_helper.py`.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_plugin_testing_helper.py arrt/tests/unit/test_source_plugins.py`.
- **Model:** Sonnet-class, high.

### Chunk 45: The MCP surface, broken once (ruling 3) (2b)

- **Type:** code
- **Exposed API:** the MCP surface
- **Closes:** audit-5 F3 (`work_id` → `artwork_id` in wall outputs), audit-5 F2b (the acts on
  a wall in one tool), audit-5 F14's MCP half (`not_again(scope='theme')` and `remove`),
  audit-5 § 3's retry-by-cause twin, `history` filtered by work (audit-5 F18's MCP half),
  `display_plane_has_reported` renamed, `art_catalogue`'s
  topics description naming `WIKIDATA_USER_AGENT`, rulings 1 and 2 in the descriptions, the
  MCP twins of 30, 32, 33 and 35's new fields, MCP dumping 38's view models (audit-2 S7's
  MCP half), MCP's executor (audit-2 M10's MCP half), and `arrt.mcp.*` leaving the type
  override list.
- **Owns:** everything under `arrt/src/arrt/mcp/` for the whole of wave 2,
  `arrt/src/arrt/ask/prompt.py` (`ASK_SCOPE`), `.prawduct/artifacts/api-contract.md` (the MCP
  surface table, the parity table and the description budget), `arrt/pyproject.toml` (the
  override list's last entry), `arrt/tests/contract/test_mcp_surface.py`,
  `arrt/tests/contract/test_mcp_scenarios.py`, `arrt/tests/unit/test_surface_parity.py` (after 38),
  and the integration tests of the tools.
- **Rewritten assertions:** every MCP test reading `work_id` from a wall output reads
  `artwork_id`; every test calling a wall act on `art_theme` calls it on `art_display`; each is
  a recorded contract change (ruling 3), listed in the report and in the change record.
- **If one delegate cannot finish it:** split at one seam, serially, same owner: (a) the
  break, the regrouping, the descriptions and `ASK_SCOPE`; (b) the twins and the view models.
- **Verification ceiling:** `testament run --json --suite curation -- arrt/tests/contract
  arrt/tests/integration/test_theme_and_display_tools.py arrt/tests/integration/test_mcp_preview_and_sync.py
  arrt/tests/unit/test_surface_parity.py arrt/tests/unit/test_ask_agent.py`.
- **Model:** Opus-class, high.
- **Note, 2026-11-19 (Chunk 22, from 2a's Chunk 11):** the type override list is already
  empty, so "`arrt.mcp.*` leaving the type override list" is done: this chunk keeps
  `uv run mypy` clean while it rewrites `arrt/src/arrt/mcp/`, and puts no override back.

### Chunk 46: Dated history out of the docstrings (2b)

- **Type:** cleanup
- **Closes:** audit-2's comment finding (136 dates and 21 issue numbers in module docstrings).
- **Owns:** the module docstrings under `arrt/src/arrt/` only, dispatched after every other
  chunk of 2b has merged.
- **Deliverables:** a dated correction note whose present-tense statement stands alone is
  reduced to that statement; history the change log does not hold is named in the commit body.
- **Verification ceiling:** `cd arrt && uv run ruff check . && uv run black --check . && uv run mypy`.
- **Model:** Sonnet-class, high.
