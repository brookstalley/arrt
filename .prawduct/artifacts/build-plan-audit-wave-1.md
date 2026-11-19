---
artifact: build-plan
version: 1
scope: audit-wave-1
branch: fix/audit-wave-1
base: develop
working-branches: []
last_validated: null
depends_on:
  - artifact: architecture
  - artifact: security-model
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: api-contract
  - artifact: player-contract
  - artifact: operational-spec
  - artifact: observability-strategy
  - artifact: source-plugins
  - artifact: project-preferences
governed_by:
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer; MCP and HTTP are thin → conforms: 01's preview is one service call (`build_manifest`), and dropping `theme_id` from MCP `sync` is a declared-parameter change the registry refuses by name, not a branch in a binding. 02's could-not-be-asked count reaches the surfaces through the per-plugin sentence `services/health.py` already composes"
      - "the Library/Programming seam (one-way imports, facade written as if remote, no new cross-seam foreign key, change carried by events) → conforms: 03 batches the Library's announcements without Programming reading a Library table; 04's shared write helper is a neutral top-level module both sides may import; 10 tightens the guard rather than relaxing it"
      - "the Player makes only the requests `contract/routes.json` names → conforms: no route is added or removed; 09's body cap answers an existing route"
      - "a display device renders its own label → inapplicable because nothing here changes what a Player draws"
  - artifact: security-model
    dispositions:
      - "§ Direction (outside text reaches the page as text; images and links only from a named host or checked id) → conforms: 06-08 add copy and a Copy button through `el()`, and set no markup"
      - "§ Prompt injection's trigger ('any credential becoming reachable from a tool') → amendment proposed in 09, as the DECISION on `issue_client_token` below, because the trigger has already fired and the artifact says it would re-derive"
      - "§ Credentials › Inventory → conforms after 09, which adds the two CI secrets it omits and corrects the client-token sentence"
  - artifact: information-architecture
    dispositions:
      - "§ Direction, navigation is a link and an act is a button → conforms: 07 redraws back links as links (ruling 1 of 2026-10-27) and 08 makes the sidebar budget a link"
      - "§ Direction, the *arr layout → conforms: no section or page is added; 08's spend link goes to History filtered to Gets, a page that exists"
      - "§ Vocabulary (a Player is never a client or a display on a screen a person reads) → conforms after 06, which removes 'plane', 'display' (for the Player) and 'heartbeat' from Walls, Players and Status copy"
  - artifact: design-direction
    dispositions:
      - "§ Component Patterns, one filled act per region; never one button per row → conforms after 06 (the Edit wall dialog) and 08 (Queue's per-row Retry)"
      - "§ Tiles, the label sits beneath on the page's ground → conforms after 07 (Posters on Artworks)"
      - "§ Direction, token values live in `app.css` → conforms: no colour is added outside the token blocks"
  - artifact: accessibility-spec
    dispositions:
      - "norm 2 (WCAG 2.1 AA; colour never the sole carrier of state) → conforms: every changed screen keeps its axe scan in the browser files it runs, and a disabled control carries its reason in text"
      - "norm 1 (the e-paper label) → inapplicable because nothing here changes what a Player draws"
  - artifact: data-model
    dispositions:
      - "per-device runtime state never lives in the catalogue → conforms: nothing per-device is added; 04's pre-migration snapshot is a copy of the file, not a table"
      - "a work is distinct from an image of it → conforms after 05: a scan the curator turned down no longer becomes a Source of the work"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are provider-enforced, never application-enforced → conforms: 05 moves a mat's spend record ahead of the mat write and adds no application meter"
  - artifact: operational-spec
    dispositions:
      - "§ Backup and Restore (a rollback across a migration is a restore from the backup taken before the deploy) → conforms after 04, which takes that copy itself before any destructive migration and keeps it out of the generations' retention"
  - artifact: observability-strategy
    dispositions:
      - "one JSON line per event, `run_id` lines reconstructable → conforms after 09, which takes successful Player polls out of the access log so the lines the shape exists for are not buried"
  - artifact: project-preferences
    dispositions:
      - "a found problem is fixed, not filed → conforms: every finding of the 2026-11-19 audit that needs no ruling and depends on no other chunk is in a chunk here; the rest are in the gitignored ledger beside the reports with their reason"
      - "delegation policy (feature tests only, fail-first proof for every new check, plan refs that resolve) → conforms: each chunk names its ceiling and asks for the failing output; `prawduct-hook verify-chunk-refs` is run on every chunk before dispatch"
      - "each plane's tests live in its `tests/` → conforms: every new test file is under `arrt/tests/` or the root's `tests/`"

partition: "delegated, one wave. Chunks 01-10 are ten build delegates, each in its own isolated worktree reset to fix/audit-wave-1, with disjoint files; where a shared seam is unavoidable (`arrt/src/arrt/__main__.py`, `arrt/src/arrt/programming/manifest/builder.py`, `arrt/src/arrt/http/static/app.css`, `.prawduct/artifacts/information-architecture.md`, `deploy/README.md`) each chunk's section names the one region it may edit. Opus-class for 02, 03, 04, 06 and 07, which carry design judgment; Sonnet-class for 01, 05, 08, 09 and 10, which are fully specified. The coordinator integrates on fix/audit-wave-1, merges 10 last (its scan may touch lines in prose files others edited), runs the heavy suites on the merged head and the Critic, and owns Chunk 11. It may stagger dispatch to the machine's load; nothing here depends on another chunk's output."
---

# Build Plan — Audit wave 1: the fixes that need no ruling

## What this plan is

Eight reviewers audited Arrt on 2026-11-19 (reports in the gitignored
`.ux-walk/audit-2026-11-19/` of the main checkout; a delegate's worktree does not
carry them, so the coordinator pastes each cited finding into its brief or points
at the main checkout's absolute path). The owner asked for substantially all of
the product issues to be fixed by delegated builders under this repository's
governance. This plan is **wave 1**: every fix that needs no owner ruling and does
not depend on another chunk's output. The larger and dependent work is the wave-2
outline, and the questions only the owner can answer are the decision sheet, both
beside the reports. Every server-side finding has a row in the ledger there,
`ledger-arrt.md`, with the chunk that closes it or the reason it is not here.

Findings are cited as *report, id*: audit-1 is the seams review, audit-2 the
server, audit-4 the source plugins (host half only), audit-5 the information
architecture, audit-6 the rendered interface, audit-7 tests, CI and docs, audit-8
security and operations.

| Chunk | Title | Model, effort | Ledger rows |
|---|---|---|---|
| 01 | SV-1 MCP surface: a read-only preview, a `sync` that cannot hang a foreign theme, true descriptions | Sonnet-class, high | 3 |
| 02 | SV-2 the plugin host: deadlines, one Wikidata answer per work, honest health | Opus-class, high | 9 |
| 03 | SV-3 Programming consistency: reads in the transaction, feeds after commit, one reconcile per bulk act | Opus-class, high | 8 |
| 04 | SV-4 persistence and files: one atomic writer, a snapshot before a destructive migration, backups that survive a crash loop | Opus-class, high | 6 |
| 05 | SV-8 Library consistency: turned-down scans, Watch starts, mat spend, host faults in the queue, one preparation per work | Sonnet-class, high | 5 |
| 06 | SV-5a browser: Walls, Players and Status | Opus-class, high | 10 |
| 07 | SV-5b browser: Artworks, Work, Search and Artists | Opus-class, medium | 7 |
| 08 | SV-5c browser: Activity, Ask, Topics, Settings, and the words the server sends | Sonnet-class, high | 7 |
| 09 | SV-6 server edges and operations | Sonnet-class, high | 12 |
| 10 | SV-7 root guards and CI | Sonnet-class, high | 7 |
| 11 | Integration and the boundary review (the coordinator's) | — | — |

## Goals

- **Response taken:** proceed. The owner asked for "substantially all identified
  product issues to be fixed by delegated build agents under this repo's
  governance". The coordinator's proposed partition is adjusted where the code
  showed two chunks writing one file (see *Changes from the proposed partition*).
- **Product:** the household's server says what is true, and does what its
  surfaces say: an agent's check does not change a wall, a hung plugin does not
  stall every Get, a crash loop does not take the backups, a wall can be set up in
  the order the screens give it, and the synthetic walk spends nothing.
- **Architecture, what must hold:** the four seam rules (`architecture.md` §
  Direction), and the seam guard gets stricter, not looser (10). Thin bindings.
  The contract package does not change, so no `contract-v*` tag is cut in this
  wave. The interface for source plugins moves to 1.5, additively (02).
- **Constraints:** a delegate runs feature tests only (`project-preferences.md` §
  Workflow, `Delegate verification`). Every new or rewritten check comes back with
  its failing output against today's code or a deliberate re-break, naming the
  input that trips it (`Delegation`, rule 2). A test is a contract: where a
  finding changes behaviour an existing test encodes, the test's *setup* may
  change and its *assertions* may not be weakened, and the chunk's report says
  which tests and why.
- **Tradeoffs accepted:**
  - Thread deadlines in 02 cannot kill a hung plugin thread; they stop waiting
    for it. A hung plugin still holds a thread until it returns. Worth revisiting
    if a plugin is seen holding threads for hours (then: a subprocess per call).
  - 03's fix to S3 was planned as a feed written after commit, with a per-wall
    lock to pay for the window that reopens. **That is not what was built.** A
    feed is decided in the transaction and written as its last step, under the
    store's lock, which already serialises every build with its write, so no lock
    of the service's own exists and the window the plan feared is not reopened;
    what remains is a crash between the renames and the commit, which startup
    `reconcile` heals (see *Decisions made mid-build*).
  - Several findings ship as copy and structure fixes only (06's Walls card,
    the health words). The one health model across top bar, Walls, Status and
    Players is wave 2, because it is a redesign the copy fixes do not pre-empt.
- **What I would do differently (the advisor's position):** ten parallel
  delegates is the most this branch should take at once, and 06 and 03 are the
  two most likely to need a second round. If the machine is loaded, dispatch 03,
  04, 06 and 10 first: they carry the most risk and 10's scan is merged last
  anyway. I would not grow this wave further; everything else waits for wave 1 to
  merge, because DisplayService's split (#382), the type checker and the browser
  suite's retrying assertions all touch files this wave edits.
- **Decisions made in this plan** (each vetoable; the owner's decision sheet holds
  only what genuinely needs the owner):
  - `[DECISION: MCP sync stops taking theme_id; an agent that passes one is refused by name ("does not take theme_id"), and the new art_display(action='preview', wall_id, theme_id?) is the read-only twin of GET /api/manifest | audit-5 F1: the only way an agent could check a theme against a wall was a write that hangs it without recording the hang; the registry already refuses an undeclared argument by name, so the binding stays thin | user can veto/override]`
  - `[DECISION: the MCP tests that used sync with a theme as a shortcut to publish an unhung theme hang it first (art_theme activate), and keep every assertion | the behaviour they leaned on is the defect; their claims (what is left off, the pace, the feed written) are unchanged | user can veto/override]`
  - `[DECISION: a plugin call's deadline is 60 s for a finder and a reader, 30 s for a preview and 120 s for a collection browse, each a named constant; a call past it is "could not be asked", recorded against the plugin beside its faults | the private browser plugins allow 240 s per page, but a finder answers for one work and a look waits 30 s for an answer; 60 s keeps a run moving and still lets a paced HTTP plugin finish its turn | user can veto/override]` **The coordinator overrode the fixed 60 s mid-build and later raised the ceiling: see *Decisions made mid-build*.**
  - `[DECISION: the host's registry remembers pages_about per QID for ten minutes and collapses concurrent asks for one QID into one request | audit-4 finding 2: one Get sends up to 19 identical queries at once; ten minutes outlasts a run's phase 2 and is short enough that an edit on Wikidata is seen the same session | user can veto/override]`
  - `[DECISION: the pre-migration snapshot is written to BACKUP_DIR when it is set and beside the catalogue otherwise, named pre-migration-<UTC instant>.sqlite, and the three newest are kept outside the generations' count | operational-spec.md says the rollback across a migration is a restore from the copy taken before it; a copy under the generations' retention is the one a crash loop evicts (audit-8 F4) | user can veto/override]`
  - `[DECISION: the start-up backup pass is skipped when the newest generation is younger than the backup interval | the start-up pass exists so a server that restarts more often than the interval still backs up; a generation younger than the interval already satisfies that, and fourteen restarts then write nothing | user can veto/override]`
  - `[DECISION: Settings › Sources and Status keep naming the environment variable a declined source or Ask needs, because those are the operator's pages and the act they ask for is setting it; Topics, the search dropdown, Ask and the Work page say it in the household's words | ruling 1 of 2026-10-11 put engineering detail behind ?debug; a variable name is the operator's remedy on the operator's page and plumbing everywhere else | user can veto/override]`
  - `[DECISION: the top bar's search box is labelled "Search" with the accessible name "Search works, artists and topics" | audit-5 F11: it searches more than artworks; the library's one name is held for the owner, so the label names what it searches and no noun for the holdings | user can veto/override]`
  - `[DECISION: issue_client_token stays on MCP, and security-model.md's prompt-injection section is re-derived to say so: a client token is reachable from a full MCP client (never from Ask, whose scope excludes it), it opens art manifests and heartbeats only, and minting one revokes the Player's | audit-8 F9: the section's own trigger fired; taking the action off MCP would remove the only agent path to re-pair a Player, for a credential whose reach is a wall's art | user can veto/override]`
  - `[DECISION: a Frame moving between Players on a heartbeat (clients.md) stays automatic; the move is logged at WARNING naming both Players, and the inventory sentence states what the code holds | audit-8 F10: the move is ruled as a feature; the sentence overstated the guarantee | user can veto/override]`
  - `[DECISION: the Player routes refuse a request body over 256 KiB with 413 | a heartbeat is a few KiB; the cap is ten times anything valid, and player-contract.md § Transport records it as a server limit, not a schema rule, so no contract tag is cut | user can veto/override]`
  - `[DECISION: HostGuard refuses an /api or /mcp request whose Sec-Fetch-Site is cross-site, and every HTML response carries Content-Security-Policy frame-ancestors 'none' with X-Frame-Options DENY | audit-8 F7 and F8: a no-cors GET from a hostile page carries no Origin, but every current browser sends Sec-Fetch-Site; MCP clients send neither header and are unaffected | user can veto/override]`
  - `[DECISION: deploy/curation.service is retired, with its README section and the two hygiene tests that guarded only that file | audit-1 M9: nothing has run it since 2026-10-02; build-plan-wave-5-split.md left its retirement to a later plan, and this is that plan | user can veto/override]`
  - `[DECISION: image.yml also runs, unfiltered, on pull requests into main | audit-7 S4: the image is otherwise built only by hand before a release and nothing makes anyone do it; a release PR is weekly at most, so this is one build a week, inside the owner's 2026-11-18 ruling against heavy builds on every pull request | user can veto/override]`
  - `[DECISION: actions are pinned by commit SHA with the tag in a trailing comment, and no Dependabot is added | audit-7 M5 and audit-8 F6; Dependabot would open pull requests on a public repository and spend the minutes the 2026-11-18 ruling saves | user can veto/override]`
- **Level:** High for 01, 05, 08, 09 and 10. Medium for 02, 03, 04, 06 and 07:
  each has one design choice its builder makes against stated acceptance (the
  deadline mechanism, the feed write after commit, which migrations count as
  destructive, the Edit wall dialog's one commit, the Artworks toolbar). What
  would raise it: the builder's first commit is the failing test, reviewed by the
  coordinator before the fix is built on it.

## Changes from the proposed partition

- **SV-4 split into 04 (persistence and files) and 05 (SV-8, Library
  consistency).** The per-work preparation lock and the mat-spend reorder both
  edit `arrt/src/arrt/library/acquisition/preparation.py`; the turned-down scans,
  the Watch start and the queue's host faults are three more Library services.
  One owner each keeps 04 to the store, the backup and the writers.
- **SV-5b split into 07 (Artworks, Work, Search, Artists) and 08 (SV-5c:
  Activity, Ask, Topics, Settings, and the server's copy).** Audit-6's minor
  findings fit wave 1 and fall on screens neither SV-5a nor SV-5b owned; together
  they would have made one delegate's diff span eleven screens.
- **Audit-6 finding 7 (the Edit wall dialog) moved from SV-5b to 06 (SV-5a)**,
  because the dialog is `arrt/src/arrt/http/static/screens/walls.js`, which 06
  owns. "The token dialog half of 9" is read as audit-6 finding 15 (finding 9 is
  Ask), and is in 06.
- **SV-6's CI and hygiene items moved to 10 (SV-7)**: F19, F22, the SHA pins and
  the image build on release PRs are root-suite and `.github/` files only, which
  10 already owns. 09 keeps the server's edges and the documents that describe
  them.
- **Audit-4 finding 14 (three answers recorded as one fetch status) moved to wave
  2.** It changes `FetchStatus`, a persisted enum, and the queue's retry rule with
  it (#318): a persisted format, which this plan does not design in passing.
- **Audit-2 M10 (the shared executor) and M8 (every refusal a 400) are wave 2**:
  M10 is inferred and wants a measurement first; M8 adds an error type every
  surface maps, in `arrt/src/arrt/http/api.py`, which is wave 2's serializer work.
- **The server half of the Hang confirmation's "0 of 1 work … is" (audit-6
  finding 19)** is in wave 2's copy and count sweep: the sentence is
  `ManifestBuild.summarise`, which MCP tests in 01's files assert word for word.
  06 fixes the client half (no promise when no Player shows the wall).

## Shared seams this wave

- `arrt/src/arrt/__main__.py`: 02 edits only `_registry`; 04 edits only the
  `open_catalogue_file(...)` call and the `CatalogueBackup(...)` arguments. No
  one else edits it.
- `arrt/src/arrt/programming/manifest/builder.py`: 04 re-implements
  `write_atomically` over the shared helper, keeping its name and signature. No
  one else edits the file.
- `arrt/src/arrt/http/static/app.css`: 06 may append one block at the end of
  the file; 07 and 08 edit only rules whose selectors belong to their own
  screens, in place, and append nothing at the end.
- `.prawduct/artifacts/information-architecture.md`: 07 edits only the rows for
  Artworks, Work, Search results, Artists and Artist; 08 only the Status row's
  spend sentence and the rows for Activity, Ask, Topics and Settings; 06 edits
  none and reports any row its change makes false.
- `deploy/README.md`: 10 edits only the paragraph on running `image.yml` by
  hand; 09 edits the rest.
- `arrt/src/arrt/http/api.py`, `arrt/src/arrt/http/models.py` and
  `arrt/src/arrt/mcp/bindings.py`: only 01 edits `bindings.py` (and
  `arrt/src/arrt/mcp/tools.py`); nobody edits `api.py` or `models.py` this wave.
- Prose files 10's scan flags: 10 edits only the lines its scan names, and is
  merged last.

## Decisions made mid-build

Decisions taken after the plan was written, by the coordinator, an integrator or a
chunk's builder, each in the plan's own form and each as vetoable as the ones above.
Where one changes what a chunk above says, the chunk's text is left as it was
planned and this section is the later word.

- [DECISION: a plugin's deadlines are declarable per plugin (interface 1.5, `SourcePlugin.deadlines`, keys finder, reader, preview and browse), the defaults above unchanged, and the host refuses at load a deadline beyond a ceiling of 3,600 s | the plan fixed 60 s for every finder and reader, but the private browser plugins take 77-100 s a page, so shipped together they would become permanently "could not be asked". The ceiling began at 900 s and was raised once the plugins' bounds were measured: one page's worst case is 1,012 s, and 2,044 s for Stedelijk's reader, both over 900 s, so the plugins could not have declared them. The ceiling is a sanity bound on code the owner already runs in this process, not a security boundary. **Gate:** no image is built from this server with the private plugins until they declare their deadlines | user can veto/override]
- [DECISION: a published feed is decided inside the transaction and written as its last step (staged beside its file, the act's feeds renamed together, the staged files removed and the act rolled back if a write fails), where the plan wrote "after commit" with a per-wall lock | an existing contract test (`test_a_hang_whose_manifest_cannot_be_written_is_not_recorded`, backlog #35) requires that a hang whose feed cannot be written is not recorded, which a write after commit cannot keep. The store's lock is held throughout and already serialises a build with its write, so no lock of the service's own is needed. The residual window is a crash between the renames and the commit, which leaves a feed the catalogue disowns; startup `reconcile` republishes a feed whose theme is not the one hung, and that is the heal | user can veto/override]
- [DECISION: the lost update the audit marked as inferred is treated as real, and reads sit inside the transaction in twelve wall and client acts | requests run on a threadpool and the store's lock covers each statement, not the read-modify-write. A forced interleaving failed on the old code with `FOREIGN KEY constraint failed`, and `rename_client` racing `access.issue` lost a newly issued token. `update_theme` is left as it was, because the adapter never writes the default's mark from the record, so no edit can put one back | user can veto/override]
- [DECISION: chunk 03's acceptance 5 (delete `Published.on_the_wall` and `Published.after`) is not done | its premise was false: `Published.on_the_wall` has 17 callers in tests, and `after` is called by `_restart`. The audit read "no caller in `src`" as "dead" | user can veto/override]
- [DECISION: a bulk act is announced as one event naming every work the commit changed (`WorkChanged.work_ids`), where the plan allowed the display subscriber to coalesce instead | the event stays remote-shaped (a list is what a webhook would carry), and delivering the ids one commit changed together means one reconcile per bulk act with no window to tune in the subscriber. The builder's choice, recorded as the plan asked | user can veto/override]
- [DECISION: a Watch's "due" reads the newest run carrying the Watch's id, keyed on the Watch's own note naming another run, where the plan allowed the start and its note to commit together | the run row is written when the run starts and the note is a second write that can fail, so the run is the record of the attempt; keying on the note naming another run leaves a Watch whose notes are in order reading exactly as it did. The builder's choice, recorded as the plan asked | user can veto/override]
- [DECISION: a copy before a migration that would drop exactly what the newest copy would replaces that copy instead of adding to the three kept, and staging debris older than a day is swept | "the three newest are kept" would let a migration that fails on every start push the copy from before the upgrade out, which is the failure the copy exists to prevent; a fresh staging name per attempt leaves a killed writer's file behind, which nothing else would claim | user can veto/override]
- [DECISION: the copy before a migration opens the catalogue read-write, though it only reads | a process killed mid-transaction leaves a hot journal that a read-only open cannot read ("attempt to write a readonly database", measured on SQLite 3.53.1), and the same read-only open in `file_had_table` failed on every start after such a kill, so the server would not start at all. This was the first of two defects the chunk found and fixed; the second was that its own first writer could delete another write's staging file, caught by a test before commit | user can veto/override]
- [DECISION: every `sqlite3.OperationalError` met in the middle of one work, a locked database included, pauses the acquisition queue for fifteen minutes and counts against no work, as a full or read-only disk (`ENOSPC`, `EROFS`) does | each fails every work in turn, so counting them gave every work up in about four days; treating "database is locked" as the host's fault is broader than the disk faults the plan was thinking of, and is accepted because a locked database blocks every work the same way | user can veto/override]
- [DECISION: a disk fault's pause is named by its error code (`ENOSPC`, `EROFS`), not by the exception's type | `remedy_for("OSError")` must stay None, because `OSError` by name is also what a surprise records, and a surprise has no remedy to give; two of the chunk's assertions changed to match | user can veto/override]
- [DECISION: the Edit wall dialog keeps one commit per section, every one quiet, with *Show it there* the one filled act and *Close* naming the sections left unset, where the plan allowed one *Save* over every section | each section is its own write on its own route, and the server can refuse one or keep one with a notice the curator has to read where it was made, which one Save would have to report as several partial outcomes at once. The builder's choice, recorded as the plan asked | user can veto/override]
- [DECISION: on the list screens' toolbar *Select* is last on the right, after View, Sort and the filters' toggle, and its acts are on the left | `design-direction.md` § Component Patterns, "How a page reads", records it from the owner's page rules of 2026-10-27, and this plan said so. An older passage of `information-architecture.md` (2026-10-08) put the toggle beside its acts; it is corrected with a dated note, and the owner is asked to confirm, since no entry in `owner-rulings.md` states where Select stands. A Topic's page and a theme's page keep the old layout until they adopt the shared toolbar | user can veto/override]
- [DECISION: the token dialog quotes the Player's own field names, *Token* and *Server address*, in place of the names the plan gave (*Client token*, *Server › Address*) | the Player's own settings-page work renamed those fields while this was built, so the two fixes for one finding crossed; the server's dialog is what a person follows, so it names what that person sees | user can veto/override]
- [DECISION: `deploy/curation.service` was retired with all five tests that guarded only it, where the plan said two | the other three guarded the same file and nothing else, and a test of a file that does not exist cannot pass | user can veto/override]

## Chunks

### Chunk 01: SV-1 MCP surface — a read-only preview, a sync that cannot hang a foreign theme, true descriptions

- **Type:** code
- **Closes:** audit-5 F1 (critical); audit-5 F10; the description half of
  audit-5 F2; audit-5 § 3 parity row "Preview a hang without writing".
- **Owns:** `arrt/src/arrt/mcp/tools.py`, `arrt/src/arrt/mcp/bindings.py`,
  `arrt/tests/integration/test_theme_and_display_tools.py`,
  `arrt/tests/contract/test_mcp_surface.py`, `.prawduct/artifacts/api-contract.md`
  (the MCP surface table and the `sync` row only), and
  new `arrt/tests/integration/test_mcp_preview_and_sync.py`.
- **Must not touch:** `arrt/src/arrt/programming/display.py` (03's),
  `arrt/src/arrt/programming/manifest/builder.py`, `arrt/src/arrt/ask/prompt.py`
  (preview stays out of Ask's scope, which reaches no wall), `arrt/src/arrt/http/api.py`.
- **Deliverables:**
  - `arrt/src/arrt/mcp/tools.py`: a `preview` action on `art_display` (wall_id
    required, theme_id optional, the same report shape as `sync`, its notice
    saying "would be", never "is"); `sync` declares only `wall_id`, and its tips
    say it republishes what is hanging; the `art_theme` `get` tip points at
    `preview`; the stale descriptions audit-5 F10 lists are rewritten from the
    bindings (activate/sync "no television writes", add_wall "nothing about a
    television is recorded", status "each wall's display writes its own
    heartbeat", not_again "Not this one again:"); `art_theme`'s summary names
    `hang_selection` as how a work or a few go up on a wall, and `show_now`'s tip
    says it lasts one slot and points at `hang_selection` for "put this up".
    `art_display`'s description is at its 2 KB budget (`.prawduct/artifacts/api-contract.md`), so the
    preview's text is paid for out of the existing tips.
  - `arrt/src/arrt/mcp/bindings.py`: `_preview` calling `build_manifest` once,
    through the shared report builder `_built`; `_sync` passes the wall only.
  - `.prawduct/artifacts/api-contract.md`: `preview` in the `art_display` row,
    and the `sync` row says it no longer takes a theme.
- **Acceptance:**
  1. `art_display(action='preview', wall_id=W, theme_id=T)` for a theme not
     hanging on W reports what T would put on W and leaves the feed file's bytes,
     `art_display(walls)`'s `hanging` and the history unchanged. Red today: the
     action does not exist.
  2. `art_display(action='sync', wall_id=W, theme_id=T)` is refused, naming
     `theme_id`, and nothing is written. Red today: it publishes T.
  3. No tip or description of any action in any MCP tool contains the retired
     phrases F10 lists: parametrised over the registry's own tool records, not a
     copied list of actions. Red today on four of them.
  4. The `art_theme` `get` tip names `preview` and no write. Red today.
  5. The existing sync tests in
     `arrt/tests/integration/test_theme_and_display_tools.py` hang their theme
     first and keep their assertions; the report lists each one changed.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/integration/test_theme_and_display_tools.py
  arrt/tests/integration/test_mcp_preview_and_sync.py
  arrt/tests/contract/test_mcp_surface.py arrt/tests/contract/test_mcp_scenarios.py
  arrt/tests/unit/test_surface_parity.py`, then `cd arrt && uv run ruff check .
  && uv run black --check .`.
- **Model:** Sonnet-class, high effort. The behaviour is fully specified; the
  descriptions need care because agents read them every session.

### Chunk 02: SV-2 the plugin host — deadlines, one Wikidata answer per work, honest health

- **Type:** code
- **Closes:** audit-4 finding 1 (host half), 2, 3 (host half; partly #313), 7, 9,
  10, 11 and the public half of 15; audit-7 S5.
- **Owns:** `arrt/src/arrt/library/discovery/pool.py`,
  `arrt/src/arrt/library/sources/loading.py`,
  `arrt/src/arrt/library/sources/plugin.py`,
  `arrt/src/arrt/library/discovery/images.py`,
  `arrt/src/arrt/library/services/look.py` (only where the pool's run count meets
  `wait_for_runs`), `arrt/src/arrt/services/health.py` (the plugin section,
  `PluginHealth`, only), `arrt/src/arrt/__main__.py` (`_registry` only),
  new `arrt/src/arrt/library/registry/remembering.py`, `docs/source-plugins.md`,
  `.prawduct/artifacts/source-plugins.md`,
  `arrt/tests/unit/test_source_plugins.py`, `arrt/tests/unit/test_image_pool.py`,
  `arrt/tests/browser/test_the_status_sources_table.py`,
  new `arrt/tests/unit/test_plugin_deadlines.py` and
  new `arrt/tests/unit/test_remembered_registry.py`.
- **Must not touch:** `arrt/src/arrt/http/models.py`, `arrt/src/arrt/http/api.py`,
  `arrt/src/arrt/mcp/bindings.py`, `arrt/src/arrt/http/static/`,
  `arrt/src/arrt/library/acquisition/service.py` (finding 14 is wave 2),
  `deploy/README.md` (09's), and the rest of `arrt/src/arrt/__main__.py`.
- **Deliverables:**
  - **Deadlines (finding 1, audit-7 S5).** Every contained finder, reader,
    preview and collection call (`_ContainedFinder`, `_ContainedReader`,
    `_ContainedCollection` in `arrt/src/arrt/library/sources/loading.py`) answers
    within its named deadline or is "could not be asked", recorded against the
    plugin. The pool in `arrt/src/arrt/library/discovery/pool.py` stops waiting
    for a source past its deadline and does not block on the executor's exit, and
    the source's run count falls when the pool stops waiting, so a look is not
    left in `wait_for_runs` behind a hung source.
  - **Partial answers kept (finding 10).** What a finder yielded before it raised
    reaches the pool, as `SourceAnswer`'s docstring says it always has, or the
    docstring is corrected; the builder's choice, recorded.
  - **Answers checked (finding 9).** A `FoundImage` whose dimensions are not
    positive ints or `None`, or whose title, artist or a locator's reason exceeds
    a named length, is an interface breach (contained); a preview over the
    deployment's `preview_max_bytes` is a failed preview.
  - **Overlapping claims (finding 11).** When two loaded plugins claim one URL,
    the roster routes to the first and logs the overlap once per pair, naming
    both.
  - **Minor version (finding 7).** `SourcePlugin` gains an optional `api_minor`;
    a plugin needing a newer minor than this Arrt is refused at load naming both
    ("needs 1.6, this Arrt is 1.5"); `API_VERSION` in
    `arrt/src/arrt/library/sources/plugin.py` becomes (1, 5). An import that
    fails with a `TypeError` naming an unexpected keyword says the plugin may
    need a newer Arrt.
  - **One Wikidata answer per work (finding 2).**
    New `arrt/src/arrt/library/registry/remembering.py` wraps the registry: it
    remembers `pages_about` per QID for the plan's ten minutes and collapses
    concurrent asks for one QID into one request; `_registry` in
    `arrt/src/arrt/__main__.py` hands that wrapper to the plugins and to phase 2.
  - **Health (finding 3, host half).** The plugin reading counts could-not-be-asked
    answers beside faults, with the last message; `PluginHealth`'s sentence in
    `arrt/src/arrt/services/health.py` says a plugin that has only ever answered
    "could not be asked" since startup, and how many times. No new field on any
    surface: the sentence already reaches Status, Sources and MCP.
  - **Documents (finding 15, public half).** `docs/source-plugins.md` says the
    host's deadlines and that a timeout is "could not be asked", the minor-version
    field, that "claims without a reader" fails at load, and that the built-ins
    name their museum with a module-level `MUSEUM` rather than `museum=`;
    `.prawduct/artifacts/source-plugins.md` records interface 1.5.
- **Acceptance:**
  1. A finder that sleeps past its deadline makes `find_images` return within the
     deadline plus a margin, with that source among `unreachable`; a look asking
     the same source afterwards is not kept waiting behind it. Red today: the
     call blocks until the finder returns.
  2. Nineteen finders asking `pages_about` for one QID at once cause one request
     to the wrapped registry; a second ask inside ten minutes causes none; one
     after it, one. Red today: nineteen.
  3. A finder that yields one image and then raises `ImageSearchFailure` leaves
     that image in the pool's answer (or the docstring no longer claims it, and a
     test pins whichever is true). Red today against the docstring.
  4. A width given as a string, a 20 MB preview against a 16 MB cap, and two
     plugins claiming one URL each produce their named outcome. Red today: all
     three pass silently.
  5. A plugin declaring `api_minor=6` is refused at load with both versions named.
     Red today: `SourcePlugin(api_minor=…)` raises `TypeError` at import.
  6. After five could-not-be-asked answers and no other, the plugin's Status
     sentence says so. Red today: it reads "loaded, 0 faults".
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_source_plugins.py arrt/tests/unit/test_image_pool.py
  arrt/tests/unit/test_plugin_deadlines.py arrt/tests/unit/test_remembered_registry.py
  arrt/tests/unit/test_registry.py arrt/tests/unit/test_wikidata_pages.py
  arrt/tests/unit/test_discovery_runner.py`; `testament run --json --suite browser
  -- arrt/tests/browser/test_the_status_sources_table.py` if the sentence it
  asserts changed; then `cd arrt && uv run ruff check . && uv run black --check .`.
  No live marker: nothing here may reach a museum or Wikidata.
- **Model:** Opus-class, high effort: the deadline mechanism, the run count's
  release, and the coalescing are concurrency design.

### Chunk 03: SV-3 Programming consistency — reads in the transaction, feeds after commit, one reconcile per bulk act

- **Type:** code
- **Closes:** audit-2 S2, S3 (with the false comment at `arrt/src/arrt/services/container.py` it names),
  S4, the comment half of M6 for `arrt/src/arrt/library/services/catalogue.py`;
  audit-1 M5 and the Programming half of M9 (the stale comments in
  `arrt/src/arrt/programming/display.py` and `arrt/src/arrt/programming/manifest/heartbeat.py`); audit-8 F10 (the log half); the
  server half of audit-6 finding 2 (the refusal "output cannot be empty").
- **Owns:** `arrt/src/arrt/programming/display.py`,
  `arrt/src/arrt/programming/clients.py`, `arrt/src/arrt/programming/store.py`,
  `arrt/src/arrt/programming/manifest/v2.py`,
  `arrt/src/arrt/programming/manifest/heartbeat.py`,
  `arrt/src/arrt/library/events.py`,
  `arrt/src/arrt/library/services/catalogue.py`,
  `arrt/src/arrt/services/container.py` (comments only),
  `arrt/tests/unit/test_reconciliation.py`, `arrt/tests/unit/test_clients.py`,
  `arrt/tests/unit/test_library_events.py`, `arrt/tests/unit/test_manifest.py`,
  `arrt/tests/unit/test_displays.py`, and
  new `arrt/tests/unit/test_programming_consistency.py`.
- **Must not touch:** `arrt/src/arrt/programming/manifest/builder.py` (04 owns
  `write_atomically`; `summarise` is wave 2), `arrt/src/arrt/persistence/`
  (04's), `arrt/src/arrt/mcp/`, `arrt/src/arrt/http/`.
- **Deliverables:**
  - **S2, lost updates.** Every `DisplayService` and `ClientService` method that
    reads a wall, display or client and writes the whole row back does both inside
    one `transaction()` (the pattern, not a list of lines: every method in
    `arrt/src/arrt/programming/display.py` and
    `arrt/src/arrt/programming/clients.py` that calls `get_wall`, `get_display`
    or `get_client` before `with self._store.transaction()` and then writes the
    record it read). `_merge_place` and `_reconcile_display` included.
  - **S3, the feed after commit.** A published feed is written only after the
    transaction that decided it commits (`ProgrammingStore` in
    `arrt/src/arrt/programming/store.py` declares the `after_commit` the shared
    adapter already has), with a per-wall lock so two writers cannot interleave a
    build and a write. `activate_theme`'s comment states both directions truly.
    Startup `reconcile` compares a feed's playlist with the hung theme and
    republishes on a mismatch. The sentence at
    `arrt/src/arrt/services/container.py` claiming "nothing is half-applied" says
    what holds.
  - **S4, one reconcile per bulk act.** A bulk archive (and any other act that
    announces several works from one commit) reaches `DisplayService` as one
    `reconcile(ids)`: the Library's publisher in `arrt/src/arrt/library/events.py`
    delivers the ids announced from one commit together, or the display subscriber
    coalesces them; the builder's choice, recorded. The event stays remote-shaped
    (a list is the webhook a split would send).
  - **Dead code and false comments.** `Published.on_the_wall` and
    `Published.after` in `arrt/src/arrt/programming/manifest/v2.py` are deleted
    (no caller in `src` or `tests`); the "never written by this plane" and "the
    directory both planes share" comments in `arrt/src/arrt/programming/display.py` and the file-channel
    docstring in `arrt/src/arrt/programming/manifest/heartbeat.py` say what is
    true; the "a render is a few megabytes" justification in
    `arrt/src/arrt/library/services/catalogue.py` states its real bound; "plane"
    words go from the files this chunk owns.
  - **F10.** A display moved to another Player on a heartbeat is logged at
    WARNING naming both Players (the plan's DECISION).
  - **Audit-6 finding 2, server half.** `assign_wall` with no output says that the
    Player has not reported its screens yet and what to do, in place of "output
    cannot be empty".
- **Acceptance:**
  1. A wall read for `set_playback`, a Player heartbeat that merges its display
     between the read and the write, then the write: the wall keeps the merged
     `display_id`. Red today: the old one is written back.
  2. A hang whose transaction raises after the build leaves the published feed's
     bytes unchanged. Red today: the file already carries the new theme.
  3. A feed whose playlist differs from the hung theme is republished by startup
     `reconcile`. Red today.
  4. Archiving 50 works on 3 walls in one request calls `reconcile` once with 50
     ids and rewrites each wall's feed at most once. Red today: 50 calls.
  5. `Published.on_the_wall` and `Published.after` no longer exist, and the
     schedule vector tests still pass.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_programming_consistency.py arrt/tests/unit/test_reconciliation.py
  arrt/tests/unit/test_clients.py arrt/tests/unit/test_library_events.py
  arrt/tests/unit/test_manifest.py arrt/tests/unit/test_displays.py
  arrt/tests/unit/test_schedule.py arrt/tests/integration/test_archive_routes.py
  arrt/tests/integration/test_selections_and_exclusions.py
  arrt/tests/contract/test_player_contract.py`, then `cd arrt && uv run ruff check .
  && uv run black --check .`.
- **Model:** Opus-class, high effort: S3 reopens the window the transaction
  closes today, and the lock that replaces it is the chunk's design.

### Chunk 04: SV-4 persistence and files — one atomic writer, a snapshot before a destructive migration, backups that survive a crash loop

- **Type:** code
- **Closes:** audit-2 S8 (the writers; the per-work lock is 05's), S9, the
  comment half of M1 (the backup's lock), the `arrt/src/arrt/persistence/durable.py` halves of the
  comment-accuracy table (rows 1 and the two-threads claim of M6), M7, and M6's
  `arrt/src/arrt/library/services/survey.py` wrong noun; audit-8 F4.
- **Owns:** new `arrt/src/arrt/atomic.py`,
  `arrt/src/arrt/library/acquisition/master.py`,
  `arrt/src/arrt/library/acquisition/direct.py`,
  `arrt/src/arrt/library/acquisition/dezoomify.py`,
  `arrt/src/arrt/library/services/pictures.py`,
  `arrt/src/arrt/library/services/thumbnails.py`,
  `arrt/src/arrt/library/services/survey.py`, `arrt/src/arrt/library/readiness.py`,
  `arrt/src/arrt/programming/manifest/builder.py` (`write_atomically` only),
  `arrt/src/arrt/persistence/backup.py`, `arrt/src/arrt/persistence/file.py`,
  `arrt/src/arrt/persistence/durable.py`, `arrt/src/arrt/persistence/migrations.py`,
  `arrt/src/arrt/__main__.py` (the `open_catalogue_file(...)` call and the
  `CatalogueBackup(...)` arguments only), `.prawduct/artifacts/operational-spec.md`
  (§ Backup and Restore and § Routine Operations' rollback sentence only),
  `arrt/tests/unit/test_backup_writer.py`, `arrt/tests/unit/test_master.py`,
  `arrt/tests/unit/test_acquisition_direct.py`,
  `arrt/tests/unit/test_acquisition_dezoomify.py`, `arrt/tests/unit/test_pictures.py`,
  `arrt/tests/unit/test_thumbnails.py`, `arrt/tests/unit/test_durable.py`,
  `arrt/tests/unit/test_wall_migration.py`, new `arrt/tests/unit/test_atomic_writes.py`
  and new `arrt/tests/unit/test_pre_migration_snapshot.py`.
- **Must not touch:** `arrt/src/arrt/library/acquisition/preparation.py` and
  `arrt/src/arrt/library/acquisition/queue.py` (05's),
  `arrt/src/arrt/persistence/discovery.py` and
  `arrt/src/arrt/persistence/sqlite_discovery.py` (05 may add one method),
  `arrt/src/arrt/library/sources/nga.py` (a built-in plugin, held to the plugin
  interface, which already stages under a unique name), the rest of
  `arrt/src/arrt/programming/`, and the rest of `arrt/src/arrt/__main__.py`.
- **Deliverables:**
  - **One writer (S8).** New `arrt/src/arrt/atomic.py`, a neutral module both
    sides of the seam may import: write bytes or a stream to a unique staging name
    beside the destination, fsync the file, rename it into place, fsync the
    directory, and remove the staging file on any failure. The Library's writers
    in `arrt/src/arrt/library/acquisition/master.py`, `arrt/src/arrt/library/acquisition/direct.py`, `arrt/src/arrt/library/services/pictures.py`, `arrt/src/arrt/library/services/thumbnails.py` and the backup
    receipt use it; `arrt/src/arrt/library/acquisition/dezoomify.py` keeps the extension the binary needs in a
    unique staging name; `write_atomically` in
    `arrt/src/arrt/programming/manifest/builder.py` keeps its name and signature
    and delegates.
  - **A snapshot before a destructive migration (S9).** Before any migration that
    would drop a column or a table acts on a file, the file is copied (`VACUUM
    INTO`) to the plan's pre-migration snapshot, outside the generations'
    retention; a migration that would act on nothing takes no copy. Each
    destructive migration in `arrt/src/arrt/persistence/migrations.py` answers
    whether it would act, without acting, so the decision is the migrations' own.
  - **Backups survive a crash loop (F4).** The start-up pass in
    `arrt/src/arrt/persistence/backup.py` is skipped while the newest generation
    is younger than the interval (the plan's DECISION).
  - **Comments.** `arrt/src/arrt/persistence/backup.py`'s "never takes the server's write lock"
    states the SHARED lock a rollback-journal copy holds; `arrt/src/arrt/persistence/durable.py`
    states the precondition its "single writer, so no `cas`" claim needs (the read
    inside the same transaction) and the threads that really reach the
    connection.
  - **Copy (M7).** Where "master" means the Original, curator-facing text in
    `arrt/src/arrt/library/services/survey.py`, `arrt/src/arrt/library/services/thumbnails.py` and `arrt/src/arrt/library/readiness.py` says "original image"; the
    presentation master keeps its name. M6's "masters' sizes" in `arrt/src/arrt/library/services/survey.py`
    reads "originals' sizes".
  - **Records.** `.prawduct/artifacts/operational-spec.md` § Backup and Restore
    says where the pre-migration snapshot is, how many are kept, and that the
    start-up pass is skipped while a recent generation stands.
- **Acceptance:**
  1. Two writers staging the same master at once leave a whole file under the
     final name and no `FileNotFoundError`. Red today: both stage at
     `<name>.making`.
  2. Opening a file shaped like the pre-wall schema writes a pre-migration
     snapshot that still holds the dropped column; opening the current schema
     writes none. Red today: no snapshot.
  3. Fourteen starts within an hour, after one generation from before the
     upgrade, leave that generation in place. Red today: it is pruned.
  4. A failure mid-write (raised from inside the stream) leaves no staging file
     and the old destination intact, for each writer converted.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_atomic_writes.py arrt/tests/unit/test_pre_migration_snapshot.py
  arrt/tests/unit/test_backup_writer.py arrt/tests/unit/test_master.py
  arrt/tests/unit/test_acquisition_direct.py arrt/tests/unit/test_acquisition_dezoomify.py
  arrt/tests/unit/test_pictures.py arrt/tests/unit/test_thumbnails.py
  arrt/tests/unit/test_durable.py arrt/tests/unit/test_wall_migration.py
  arrt/tests/unit/test_manifest.py`, then `cd arrt && uv run ruff check . && uv run
  black --check .`. The `live_binary` dezoomify probe is not run (by hand only).
- **Model:** Opus-class, high effort: which migrations count as destructive, and
  the probe each answers without acting, is the chunk's design.

### Chunk 05: SV-8 Library consistency — turned-down scans, Watch starts, mat spend, host faults in the queue, one preparation per work

- **Type:** code
- **Closes:** audit-2 M2, M3 (known: `.prawduct/artifacts/observability-strategy.md`), M4, M13, and
  the per-work half of S8.
- **Owns:** `arrt/src/arrt/library/services/discovery.py` (acceptance's promotion
  of images only), `arrt/src/arrt/library/services/scheduler.py`,
  `arrt/src/arrt/library/services/watches.py`,
  `arrt/src/arrt/library/acquisition/preparation.py`,
  `arrt/src/arrt/library/acquisition/queue.py`,
  `arrt/src/arrt/persistence/discovery.py` and
  `arrt/src/arrt/persistence/sqlite_discovery.py` (one read method each, if the
  Watch fix needs it), `arrt/tests/unit/test_scheduler.py`,
  `arrt/tests/unit/test_watches.py`, `arrt/tests/unit/test_preparation.py`,
  `arrt/tests/unit/test_acquisition_queue.py`, and
  new `arrt/tests/unit/test_acceptance_leaves_turned_down_scans.py`.
- **Must not touch:** the rest of `arrt/src/arrt/persistence/` (04's), the
  acquisition writers (04's), `arrt/src/arrt/library/services/runner.py` unless
  the Watch fix cannot be made without it (then one call, reported).
- **Deliverables:**
  - **M2.** Acceptance promotes no image the curator turned down
    (`rejected_at` set) into a Source of the work.
  - **M3.** A Watch whose start was not recorded is not started again on the next
    pass: either `due` reads the latest run carrying the Watch's id, or the start
    and its note commit together; the builder's choice, recorded.
  - **M4.** A mat's spend is recorded before its colour is written, so a refused
    write keeps the billed cost.
  - **M13.** `OSError` with `ENOSPC` or `EROFS`, and `sqlite3.OperationalError`,
    pause the queue as a deployment fault, as `NotEnoughSpace` does, instead of
    counting against each work.
  - **S8, the per-work half.** `PreparationService` prepares one work at a time:
    a second `prepare` or `regenerate` of the same work waits for the first, and
    different works do not wait for each other.
- **Acceptance:**
  1. Accepting a candidate with one turned-down scan and one kept scan leaves one
     Source. Red today: two.
  2. A scheduler pass whose `record_started` raises, followed by another pass,
     starts one run. Red today: two.
  3. A mat whose `record_mat_color` raises leaves its spend row. Red today: none.
  4. A fetch that raises `OSError(ENOSPC)` pauses the queue and leaves the work's
     failure count unchanged. Red today: it counts.
  5. Two threads preparing one work run one after the other (an instrumented fake
     records no overlap); two works overlap. Red today: they overlap.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_acceptance_leaves_turned_down_scans.py
  arrt/tests/unit/test_scheduler.py arrt/tests/unit/test_watches.py
  arrt/tests/unit/test_preparation.py arrt/tests/unit/test_acquisition_queue.py
  arrt/tests/unit/test_discovery_store.py arrt/tests/unit/test_discovery_constraints.py`,
  then `cd arrt && uv run ruff check . && uv run black --check .`.
- **Model:** Sonnet-class, high effort: five small, fully specified fixes.

### Chunk 06: SV-5a browser — Walls, Players and Status

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-6 finding 2 (the client half), 6 (copy and duplication only),
  7, 8 (the Walls and Status sites), 15, 19 (the client half), 20; audit-5 F5,
  the copy half of F6, and F12's comment in `arrt/src/arrt/http/static/screens/health.js`; ux-review-2026-10 §20
  and §44's residue.
- **Owns:** `arrt/src/arrt/http/static/screens/walls.js`,
  `arrt/src/arrt/http/static/screens/clients.js`,
  `arrt/src/arrt/http/static/screens/health.js`,
  `arrt/src/arrt/http/static/core/status.js`,
  `arrt/src/arrt/http/static/core/hanging.js`,
  `arrt/src/arrt/http/static/core/selection.js` (the Hang consequence sentence
  only), `arrt/src/arrt/http/static/app.css` (one appended block at the end),
  `arrt/tests/browser/test_the_walls.py`, `arrt/tests/browser/test_editing_a_wall.py`,
  `arrt/tests/browser/test_the_clients.py`,
  `arrt/tests/browser/test_the_health_panel.py`,
  `arrt/tests/browser/test_walls_lead_with_the_work.py`, and
  new `arrt/tests/browser/test_setting_up_a_wall.py`.
- **Must not touch:** `arrt/src/arrt/http/static/core/router.js`,
  `arrt/src/arrt/http/static/core/toolbar.js`, `arrt/src/arrt/http/static/app.js`,
  `.prawduct/artifacts/information-architecture.md` (report any row made false),
  any server file.
- **Deliverables:**
  - **Setting up a wall (finding 2).** In Walls › Edit… › *Where it shows*, *Show
    it there* is disabled while the chosen Player has reported no screen, with a
    sentence beside it saying the Player must be running with its token and that
    its screens appear here once it reports. The Players lead line and a newly
    added Player's row say "waiting for it to report" until it does.
  - **The token dialog (finding 15, F6's copy half).** A Copy button beside the
    token (with a fallback for a page served over plain http, where the
    clipboard API is absent), the instructions in the Player page's own field
    names (*Server › Address*, *Client token*), and the list behind the dialog
    refreshed when the dialog opens, not when it closes.
  - **One filled act (finding 7).** The Edit wall dialog has one filled commit;
    the builder chooses between one Save over every changed section and quiet
    per-section commits with one filled default, records why, and makes Close
    say which sections are unsaved.
  - **The Walls card (finding 6).** The two notices that both say the wall is
    dark or unreported become one; "Open the reading for X" becomes a link named
    for Status; the explanatory note before anything is hung sits inside the
    card.
  - **Words (F5, finding 8, finding 20).** No user-visible string on Walls,
    Players, Status or the top bar says "plane", "heartbeat", or "display" for
    the Player; Status says one count's age once; the backup record's temporary
    path is behind `?debug`; `arrt/src/arrt/http/static/screens/health.js`'s header comment no longer says Status
    holds the spend record.
  - **The Hang confirmation (finding 19, client half).** "Everyone in the house
    sees X change" only when a Player shows X; otherwise it says nothing shows X
    yet.
- **Acceptance:**
  1. With a Player that has never reported, *Show it there* is disabled and the
     reason is visible; with one that reported a screen, it is enabled. Red today:
     enabled, and pressing it shows "output cannot be empty".
  2. After *Add Player…*, the list behind the token dialog shows the new Player,
     and the Copy button puts the token on the clipboard. Red today.
  3. The Edit wall dialog has exactly one filled button. Red today: five.
  4. A scan of every string these screens render, in each state the browser
     files seed, finds none of the retired words: parametrised over the screens'
     states, not a copied list of sentences. Red today.
- **Verification ceiling:** `testament run --json --suite browser --
  arrt/tests/browser/test_the_walls.py arrt/tests/browser/test_editing_a_wall.py
  arrt/tests/browser/test_the_clients.py arrt/tests/browser/test_the_health_panel.py
  arrt/tests/browser/test_walls_lead_with_the_work.py
  arrt/tests/browser/test_walls_last_and_next.py
  arrt/tests/browser/test_scenes_on_walls.py
  arrt/tests/browser/test_setting_up_a_wall.py`; `testament run --json --suite
  curation -- arrt/tests/unit/test_navigation_is_a_link.py
  arrt/tests/unit/test_glyphs_have_one_meaning.py arrt/tests/unit/test_stylesheet_is_whole.py`;
  then `cd arrt && uv run ruff check . && uv run black --check .`. At close, an
  entry in `.prawduct/operator-verification.md` for the walk at the wall.
- **Model:** Opus-class, high effort: the Edit dialog's one commit and the setup
  sequence are interaction design inside a ruled pattern.

### Chunk 07: SV-5b browser — Artworks, Work, Search and Artists

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-6 findings 4, 5, 12 (ruling 1 of 2026-10-27), 13, 14 and 23;
  audit-5 F11 (the search label only); ux-review-2026-10 #27's toolbar residue.
- **Owns:** `arrt/src/arrt/http/static/screens/collection.js`,
  `arrt/src/arrt/http/static/screens/work.js`,
  `arrt/src/arrt/http/static/screens/search.js`,
  `arrt/src/arrt/http/static/screens/artists.js`,
  `arrt/src/arrt/http/static/core/toolbar.js`,
  `arrt/src/arrt/http/static/core/router.js` (`backLink` and `backRow` only),
  `arrt/src/arrt/http/static/index.html` (the search box's label only),
  `arrt/src/arrt/http/static/app.css` (rules for these screens' selectors, in
  place), `.prawduct/artifacts/information-architecture.md` (the Artworks, Work,
  Search results, Artists and Artist rows only), `arrt/tests/browser/test_the_collection.py`,
  `arrt/tests/browser/test_the_work_page.py`,
  `arrt/tests/browser/test_the_search_results_page.py`,
  `arrt/tests/browser/test_the_artist_page.py`, and
  new `arrt/tests/browser/test_list_toolbars_agree.py`.
- **Must not touch:** `arrt/src/arrt/http/static/core/search.js` and
  `arrt/src/arrt/http/static/core/sidebar.js` (08's), the screens 06 and 08 own,
  any server file.
- **Deliverables:**
  - **Posters carry their titles (finding 4).** On Artworks, every Posters tile
    has its title and artist beneath it on the page's ground, as the Artists
    Posters view does; no label is hover-only.
  - **Hang… on a work with no picture (finding 5).** The Work page shows *Hang…*
    disabled with its reason (no picture yet) rather than omitting it.
  - **One toolbar (finding 12).** Artworks, Artists, Search and Artist share one
    toolbar shape through `arrt/src/arrt/http/static/core/toolbar.js`: acts on the
    left; View, Sort, Filters and Select on the right; the count in one place.
  - **Back links are links (finding 13).** `backLink` draws a breadcrumb link
    above the name, never a button shape.
  - **Search (finding 14).** "Held" is said once per result group, and a held
    work with no picture says so.
  - **"No picture" has one treatment (finding 23).**
  - **The search label (F11).** As the plan's DECISION.
- **Acceptance:**
  1. On a touch-sized viewport, every Posters tile on Artworks shows its title
     without hover. Red today.
  2. A work with no picture shows a disabled *Hang…* with its reason. Red today:
     absent.
  3. The four list screens' toolbars hold their controls in the same order,
     asserted over the screens, not a copied list. Red today.
  4. No back link has the button class. Red today.
- **Verification ceiling:** `testament run --json --suite browser --
  arrt/tests/browser/test_the_collection.py arrt/tests/browser/test_the_work_page.py
  arrt/tests/browser/test_the_work_page_on_a_phone.py
  arrt/tests/browser/test_the_search_results_page.py
  arrt/tests/browser/test_the_artist_page.py
  arrt/tests/browser/test_search_and_artist_states.py
  arrt/tests/browser/test_archiving_a_work.py
  arrt/tests/browser/test_list_toolbars_agree.py`; `testament run --json --suite
  curation -- arrt/tests/unit/test_navigation_is_a_link.py
  arrt/tests/unit/test_stylesheet_is_whole.py`; `testament run --json --suite
  governance -- tests/preferences/test_screen_tables.py`; then `cd arrt && uv run
  ruff check . && uv run black --check .`. At close, an operator-verification
  entry.
- **Model:** Opus-class, medium effort: the toolbar's one shape is a design
  choice inside ruling 1 of 2026-10-27.

### Chunk 08: SV-5c browser — Activity, Ask, Topics, Settings, and the words the server sends

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-6 findings 8 (the Work, Topics, search and Ask sites), 9, 10
  (the link; the spend page is wave 2), 11, 18 and 21; audit-5 F12 (the IA
  sentence).
- **Owns:** `arrt/src/arrt/http/static/screens/activity.js`,
  `arrt/src/arrt/http/static/screens/discover.js`,
  `arrt/src/arrt/http/static/screens/topics.js`,
  `arrt/src/arrt/http/static/screens/general.js`,
  `arrt/src/arrt/http/static/screens/watches.js`,
  `arrt/src/arrt/http/static/core/asking.js`,
  `arrt/src/arrt/http/static/core/acquiring.js`,
  `arrt/src/arrt/http/static/core/search.js`,
  `arrt/src/arrt/http/static/core/sidebar.js`,
  `arrt/src/arrt/http/static/core/spend.js`,
  `arrt/src/arrt/http/static/app.css` (rules for these screens' selectors, in
  place), `arrt/src/arrt/http/ask.py`, `arrt/src/arrt/library/services/topics.py`,
  `arrt/src/arrt/library/services/identity.py`,
  `arrt/src/arrt/library/services/wikidata_match.py`,
  `arrt/src/arrt/library/acquisition/service.py` (the message in
  `_select_source` only), `.prawduct/artifacts/information-architecture.md` (the
  Status row's spend sentence and the Activity, Ask, Topics and Settings rows
  only), `arrt/tests/browser/test_activity.py`, `arrt/tests/browser/test_asking.py`,
  `arrt/tests/browser/test_the_sidebar.py`, `arrt/tests/browser/test_spend.py`,
  `arrt/tests/browser/test_general_settings.py`,
  `arrt/tests/browser/test_watches_screen.py`, `arrt/tests/browser/test_topics.py`,
  and the unit tests that assert the server sentences changed.
- **Must not touch:** the screens 06 and 07 own, `arrt/src/arrt/http/api.py`,
  `arrt/src/arrt/library/sources/` (a plugin's decline reason is the operator's,
  shown on Sources), the rest of `arrt/src/arrt/library/acquisition/service.py`.
- **Deliverables:**
  - **Ask with no key (finding 9).** Ask's box and its filled act are disabled
    with one plain sentence when the server has no key; the search dropdown does
    not offer "Ask about …" then; a 503 refusal is shown as a refusal, once,
    never as "the server failed".
  - **Spend has somewhere to go (finding 10, F12).** The sidebar's budget line is
    a link, and a Tab stop, to History filtered to Gets (`#history?kind=gets`);
    `.prawduct/artifacts/information-architecture.md`'s Status row stops claiming the spend record.
  - **Queue (finding 11).** One heading for the failures; one filled act on the
    page; *Retry N* over more than a handful of works asks first, naming the
    count; no per-row *Retry now*.
  - **Plumbing (finding 8).** No environment variable name, UUID or file path in
    the Work, Topics, search or Ask copy: the server's sentences in
    `arrt/src/arrt/library/services/topics.py`, `arrt/src/arrt/library/services/identity.py`, `arrt/src/arrt/library/services/wikidata_match.py`, `arrt/src/arrt/http/ask.py` and
    `_select_source` say it in the household's words (the plan's DECISION keeps
    the names on Sources and Status).
  - **General on a phone (finding 18)** stacks label over field.
  - **Words (finding 21).** Watches says "Ask", not "Discover"; Wanted's empty
    state says what Wanted is, not a click path.
- **Acceptance:**
  1. With no key, Ask's act is disabled with one sentence, and the search
     dropdown offers no Ask. Red today.
  2. The budget line is a link to `#history?kind=gets` reachable by Tab. Red today.
  3. *Retry 2000* opens a confirmation naming 2000 before any request is sent.
     Red today: it posts at once.
  4. No string the server sends to these screens names `WIKIDATA_USER_AGENT`,
     `OPENROUTER_API_KEY` or a work's UUID: asserted against the services'
     answers, not a copy of their text. Red today.
- **Verification ceiling:** `testament run --json --suite browser --
  arrt/tests/browser/test_activity.py arrt/tests/browser/test_asking.py
  arrt/tests/browser/test_the_sidebar.py arrt/tests/browser/test_spend.py
  arrt/tests/browser/test_general_settings.py arrt/tests/browser/test_watches_screen.py
  arrt/tests/browser/test_topics.py arrt/tests/browser/test_topics_before_any_are_held.py`;
  `testament run --json --suite curation --` the unit and integration files that
  assert the changed sentences, plus `arrt/tests/unit/test_navigation_is_a_link.py`;
  `testament run --json --suite governance -- tests/preferences/test_screen_tables.py`;
  then `cd arrt && uv run ruff check . && uv run black --check .`. At close, an
  operator-verification entry.
- **Model:** Sonnet-class, high effort: each fix is specified; the copy needs
  the vocabulary in `.prawduct/artifacts/information-architecture.md` § Vocabulary.

### Chunk 09: SV-6 server edges and operations

- **Type:** code
- **Closes:** audit-8 F3, F6 (the inventory half), F7, F8, F9, F10 (the
  inventory sentence and the body cap), F11, F12; audit-6 finding 1 (critical);
  audit-1 M9's `deploy/curation.service`; audit-2 M6's `arrt/src/arrt/app.py` description;
  audit-4 finding 15's `deploy/README.md` half.
- **Owns:** `arrt/src/arrt/logs.py`, `arrt/src/arrt/http/hosts.py`,
  `arrt/src/arrt/http/pages.py`, `arrt/src/arrt/http/player.py` (the body cap
  only), `arrt/src/arrt/app.py` (its description string only),
  `arrt/tools/ux_walk.py`, `deploy/nas/compose.example.yaml`, `deploy/README.md`
  (all but the `.github/workflows/image.yml` paragraph, which is 10's), `deploy/curation.service`
  (retired), `tests/test_repo_hygiene.py` (the unit's guards only),
  `tests/preferences/test_citations_resolve.py` (its tracked-file fixture only),
  `.prawduct/artifacts/security-model.md`, `.prawduct/artifacts/player-contract.md`
  (§ Transport's body limit only), `.prawduct/artifacts/observability-strategy.md`
  (the access-log sentence only), `arrt/tests/unit/test_logs.py`,
  `arrt/tests/unit/test_ux_walk_parsing.py`,
  new `arrt/tests/unit/test_ux_walk_isolation.py`,
  new `arrt/tests/integration/test_edge_headers.py`, and
  `arrt/tests/contract/test_player_surface.py` (the body-cap case only).
- **Must not touch:** `arrt/src/arrt/config.py`, `arrt/src/arrt/__main__.py`,
  `contract/`, `.github/`, the root guards 10 owns.
- **Deliverables:**
  - **The synthetic walk is a throwaway (audit-6 finding 1).** `boot_synthetic`
    in `arrt/tools/ux_walk.py` builds the server's environment from an
    allowlist, and blanks every name `.env.example` declares that it does not
    set, so `load_dotenv` cannot fill a key from the operator's `.env`.
  - **Player polls out of the access log (F3).** A successful (2xx or 304)
    request to a Player route writes no access line; refusals and every other
    request still do. `deploy/nas/compose.example.yaml` caps the json-file log.
  - **Cross-site requests and framing (F7, F8).** As the plan's DECISION, in
    `arrt/src/arrt/http/hosts.py` and `arrt/src/arrt/http/pages.py`.
  - **The body cap (F10).** As the plan's DECISION, in
    `arrt/src/arrt/http/player.py`, and recorded in `.prawduct/artifacts/player-contract.md` §
    Transport.
  - **The published port (F12).** The compose example binds the port to the
    proxy's network or loopback, and `deploy/README.md` says the boundary is
    every network that can route to the published port.
  - **Retire `deploy/curation.service`** (the plan's DECISION), its README
    section, and the `LIVE_UNITS` guards in `tests/test_repo_hygiene.py`; the
    citation test's fixture names another tracked file.
  - **`deploy/README.md` § A private source plugin (audit-4 15)** shows the
    plugin-lock step and the built-ins' true count.
  - **`.prawduct/artifacts/security-model.md`:** the inventory lists
    `TESTAMENT_KEY` and the CI `OPENROUTER_API_KEY` (and whether that key sits
    under the household's ceiling is recorded as unknown, for the owner); F9's
    re-derivation (the plan's DECISION); F10's sentence; F11's path into
    unattended runs named in that section's "what would change this"; F7 and F8
    as closed; the boundary F12 describes.
  - **`arrt/src/arrt/app.py`'s description** names Arrt, not the 2024 loader.
- **Acceptance:**
  1. With `OPENROUTER_API_KEY` in the process environment and in a `.env`,
     `boot_synthetic`'s server environment has it empty, and every name in
     `.env.example` is either set by the walk or blank: parametrised over
     `.env.example`'s names. Red today.
  2. A manifest poll answered 304 writes no `uvicorn.access` line; a refused one
     does. Red today: both do.
  3. A GET to `/api/registry/works/<qid>/look` with `Sec-Fetch-Site: cross-site`
     is refused before the handler; the same request same-origin is served; an
     MCP request without the header is served. Red today: served.
  4. `/` carries `frame-ancestors 'none'` and `X-Frame-Options: DENY`. Red today.
  5. A 300 KiB client heartbeat is refused with 413 and nothing is recorded. Red
     today: parsed.
- **Verification ceiling:** `testament run --json --suite curation --
  arrt/tests/unit/test_ux_walk_isolation.py arrt/tests/unit/test_ux_walk_parsing.py
  arrt/tests/unit/test_logs.py arrt/tests/integration/test_edge_headers.py
  arrt/tests/integration/test_healthz.py arrt/tests/contract/test_player_surface.py
  arrt/tests/contract/test_client_surface.py`; `testament run --json --suite
  governance -- tests/test_repo_hygiene.py tests/preferences/test_citations_resolve.py`;
  then `cd arrt && uv run ruff check . && uv run black --check .` and, at the
  root, `uv run ruff check . && uv run black --check .`. The UX walk itself
  (`arrt/tests/browser/test_the_ux_walk.py`) is not run: it is the browser
  suite's slowest file, and the coordinator runs it on the merged head.
- **Model:** Sonnet-class, high effort.

### Chunk 10: SV-7 root guards and CI

- **Type:** code
- **Closes:** audit-1 S2 and the ratchet half of S3 (#216); audit-8 F19 (the
  working tree only, never history), F22 (the permissions half), F6 (the
  pinning half); audit-7 M5 and S4.
- **Owns:** `tests/preferences/test_seam_imports.py`,
  `tests/preferences/test_deployment_values.py`,
  new `tests/preferences/test_seam_foreign_keys.py`,
  new `tests/test_actions_pinned.py`, `tests/test_default_suite_ci_scope.py`,
  `.github/workflows/tests.yml`, `.github/workflows/image.yml`,
  `.github/workflows/api-drift.yml`, `.github/workflows/drift-freshness.yml`,
  `deploy/README.md` (the `.github/workflows/image.yml` paragraph only), and the lines its scan
  flags in tracked prose files.
- **Must not touch:** `arrt/` and `contract/` source; `tests/test_repo_hygiene.py`
  and `tests/preferences/test_citations_resolve.py` (09's); any prose line its
  scan does not flag.
- **Deliverables:**
  - **The seam guard (S2).** `tests/preferences/test_seam_imports.py` treats the
    Library's storage modules (`arrt.persistence.catalogue`,
    `arrt.persistence.sqlite`, `arrt.persistence.discovery`,
    `arrt.persistence.sqlite_discovery`, `arrt.persistence.discovery_records`) as
    Library, forbidden to Programming, with a planted case; its docstring names
    what it still does not see.
  - **The foreign-key ratchet (S3).**
    New `tests/preferences/test_seam_foreign_keys.py` loads the catalogue schema
    (read from `arrt/src/arrt/persistence/sqlite.py` and
    `arrt/src/arrt/persistence/sqlite_discovery.py` without importing `arrt`)
    into an in-memory SQLite, classifies every table as Library or Programming,
    fails by name on a table it cannot classify, and holds the cross-seam foreign
    keys to exactly `theme_memberships.artwork_id`.
  - **The hygiene scan (F19).** `tests/preferences/test_deployment_values.py`
    adds CGNAT 100.64/10, IPv6 ULA and link-local, `.lan` and `.local` host
    names, and `user@host` shapes, and scans tracked documents and `.prawduct/`
    as well as code, with named exceptions for documented examples. Anything it
    finds in the working tree is scrubbed in this chunk; history is not
    rewritten (that is the owner's, on the decision sheet).
  - **Actions pinned (M5, F6).** Every `uses:` in `.github/workflows/` names a
    40-hex commit with its tag in a comment; new `tests/test_actions_pinned.py`
    fails on any that does not.
  - **Least privilege (F22).** `issues: write` only on the step or job that
    reports a drift failure, never on the job holding the OpenRouter key; the
    unpinned dezoomify download stays, as its comment says why.
  - **The image before a release (S4).** As the plan's DECISION, in
    `.github/workflows/image.yml`, with the `deploy/README.md` paragraph and
    `tests/test_default_suite_ci_scope.py`'s filter guard updated to match.
- **Acceptance:**
  1. A planted `from arrt.persistence.sqlite import SqliteCatalogue` in a
     Programming module is reported. Red today: passes.
  2. A planted second cross-seam foreign key fails the ratchet, naming it; a
     planted unclassified table fails, naming it. Red today: no such test.
  3. A planted `100.101.1.2`, `fd12::1`, `nas.lan` and `pi@frame.local` in a
     tracked document are each reported. Red today: none is.
  4. A planted `uses: actions/checkout@v4` fails the pin check. Red today: no
     such test.
- **Verification ceiling:** `testament run --json --suite governance --
  tests/preferences/test_seam_imports.py tests/preferences/test_seam_foreign_keys.py
  tests/preferences/test_deployment_values.py tests/test_actions_pinned.py
  tests/test_default_suite_ci_scope.py`, then at the root `uv run ruff check . &&
  uv run black --check .`. The workflows themselves are proven by the pull
  request's own run, which the coordinator watches.
- **Model:** Sonnet-class, high effort.

### Chunk 11: Integration and the boundary review

- **Type:** cumulative-final
- **Owner:** the coordinator; no delegate.
- **Deliverables:** each delegate branch merged into fix/audit-wave-1 (10 last);
  new `.prawduct/changes/audit-wave-1.md`, the change record, naming every chunk's
  findings and the wave-2 and held items it leaves; the operator-verification
  entries 06, 07 and 08 added.
- **Done when:** on the merged head, the curation, browser, governance and
  contract suites pass (`testament run --json`), the browser UX walk passes, the
  coordinator has read each delegate's fail-first evidence, and the Critic's
  cumulative review finds nothing blocking.
