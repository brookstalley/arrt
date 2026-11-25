---
artifact: build-plan
version: 1
scope: audit-wave-3
branch: fix/audit-wave-3
base: develop
working-branches: []
last_validated: null
depends_on:
  - artifact: build-plan-audit-wave-2b
  - artifact: architecture
  - artifact: player-contract
  - artifact: api-contract
  - artifact: data-model
  - artifact: information-architecture
  - artifact: source-plugins
  - artifact: security-model
  - artifact: observability-strategy
  - artifact: nonfunctional-requirements
  - artifact: project-preferences
governed_by:
  - artifact: architecture
    dispositions:
      - "rule 1, one-way imports through the facade → conforms: 70 batches inside the Library's facade and adds no import across the seam; 72's over-bound trouble is read by HealthService from Programming through DisplayService, as every wall reading is; tests/preferences/test_seam_imports.py holds it"
      - "rule 2, the facade written as if remote → conforms: 70 keeps LibraryFacade.playable's signature and answer (ids in, frozen PlayableWork or Unplayable out, every id answered), and changes only how many store reads one call makes"
      - "rule 3, two stores → inapplicable because ruling 9 of 2026-11-19 took the store split out; no chunk adds a table or a foreign key"
      - "rule 4, Library changes reach Programming as events → conforms: 72's nudge of the acquisition queue on an identity change is the Library's own, inside the Library"
      - "operation logic lives only in the service layer; a handler that validates, orders or decides is the violation → conforms after 75: the mat act's two hand-written validators (http/api.py set_work_mat, mcp/bindings.py _set_mat_color) become one service method both bindings call"
      - "the 2026-07-27 Decision Log entry, scoped 2026-08-06 (each binding formats its own results; the parity test holds them alike) → conforms: this plan keeps it (the DECISION in § Goals); draft 38's view models are not built"
      - "Direction norm 1's home → ruling needed: Q1(d); 81 waits for it"
  - artifact: player-contract
    dispositions:
      - "a minor is additive, a released tag is not moved → ruling needed: contract 1.3.0's cap of 32 outputs is the second answer 1.3.0 does not add; 82 waits for the owner's ratification before contract-v1.3.0 is cut and frozen. Conforms otherwise: 87 changes only the unreleased 1.3.0 (three index rows read by the rule's own words, and one table row's wording), never contract/released/, and each change makes a reader's obligation smaller, never larger"
      - "a Player refuses only what the index marks player_must_refuse, which is what it acts on (shape it reads, instants, the semantic rules) and never a presentation setting → conforms after 87: three of the 28 manifest fixtures 1.3.0 marks must-refuse name fields no Player acts on, and 87 marks them as the rule says"
  - artifact: api-contract
    dispositions:
      - "the MCP surface's names are frozen and it only grows after the one break → conforms: 75 adds actions and result fields, renames and removes none; test_mcp_break.py and its recording stay byte-unchanged"
      - "the tool description budget (2,048 bytes, mcp/registry.py) → conforms: 75 measures each tool's bytes before code and places each new action where it fits"
      - "the HTTP API has no stability obligation, the browser its only reader → conforms: 78 moves routes and changes no path, method, model or answer; app.openapi() is held byte-identical"
  - artifact: data-model
    dispositions:
      - "a persisted format is designed from its consumers' questions → conforms: no chunk adds a column or a table; 73 reads the search record's existing columns (asked_at, answered_at, images) for questions its docstring already lists"
      - "per-device runtime state never lives in the catalogue → ruling needed: Q1(c); 81 waits for it"
  - artifact: information-architecture
    dispositions:
      - "the *arr layout and the toolbar's rules (Select last on the right, ruling 6 of 2026-11-19) → conforms: 71 shortens Artworks' chrome on a phone without moving Select or removing a control"
      - "the vocabulary (the Library) → ruling needed: whether 'your library' in about 31 client strings takes the capital; 83 waits for it"
  - artifact: security-model
    dispositions:
      - "outside text reaches the page as text → conforms: 71 draws the server's refusal sentence as text"
  - artifact: observability-strategy
    dispositions:
      - "every log line a person or a dashboard reads carries an event field → conforms: 68 and 72 name their new events, and 85 writes the rows"
  - artifact: nonfunctional-requirements
    dispositions:
      - "the household's scale (thousands of works, a few walls) and the availability norm → conforms: 70 measures at 2,000 and 5,000 works, as 2b's Chunk 60 did, and 68 at the NAS's thread count"
  - artifact: project-preferences
    dispositions:
      - "Commit attribution: none → conforms: every brief says the preference outranks a session reminder asking for trailers, and the integrator counts trailer lines before each merge"
      - "Delegation and Delegate verification (feature tests only, fail-first proof, full repo-relative paths checked before dispatch) → conforms: each chunk names its ceiling and the input that turns each new check red; verify-chunk-refs was run on every chunk; 72 and 73 change arrt/src/arrt/http/models.py and run the whole browser suite, the one exception the delegate brief allows"
      - "the async scope and the lint selection (norm texts false of the code) → ruling needed: Q1(a), Q1(b); 68 adds no coroutine module"
      - "Delegate verification's count of suites ('runs all five', where there are six) → ruling needed: the owner is asked whether five, the suites that read the contract, is meant; 81 waits for it"
partition: "delegated, in six dispatch groups on one integration branch, fix/audit-wave-3, every build delegate in its own isolated worktree reset to that branch, never more than six at once. Group A, parallel, six: 67, 68, 69, 70, 71, and 87 (contract/ alone, so it may run beside them; it is the one chunk the contract's tag waits for besides the owner). Group B, parallel: 72 (67, 70), 88 (67, 87). Group C, parallel: 73 (67, 71, 72), 76 (67, 69, 70, 72, 88). Group D, parallel: 74 (68, 69, 73), 75 (67, 73), 77 (72, 76). Group E, parallel: 78 (67, 73, 75), 79 (67, 71, 72, 73, 77). Group F: 80 (every build chunk). Then 81 to 84 as the owner answers each question, 85, and 86 the coordinator's. The order comes from the files: arrt/src/arrt/services/health.py 67 → 72 → 73 → 74; arrt/src/arrt/http/api.py and arrt/src/arrt/mcp/bindings.py 67 → 73 → 75 → 78; arrt/src/arrt/programming/feeds.py 70 → 72 → 76; arrt/src/arrt/services/container.py 72 → 76 → 77; arrt/src/arrt/programming/clients.py 67 → 88 → 76; contract/ and .prawduct/artifacts/player-contract.md 87 → 82; arrt/src/arrt/ask/agent.py 68 → 74; arrt/src/arrt/library/sources/loading.py and arrt/src/arrt/library/services/runner.py 69 → 74; arrt/src/arrt/http/static/app.css 71 → 73; arrt/tests/conftest.py 77 → 79. Opus-class, high: 67, 68, 70, 73, 75. Opus-class, medium: 71, 72, 77, 85, 87, 88. Sonnet-class, high: 69, 74, 76, 78, 79, 80, 81, 82, 83. The coordinator holds the integration branch or names one integrator, and merges each delegate branch with a scoped merge commit."
---

# Build Plan — Audit wave 3: the tail the server's audit still leaves

## What this plan is

Parts 2a (#446) and 2b (#448) of the audit's second wave merged into `develop` at
`35c12bf0`. 2b's change record (`.prawduct/changes/audit-wave-2b.md`) ends with three
lists of what it left: **the third part** (draft chunks 38 and 46, and a dozen smaller
items), **found by the boundary review, and left**, and **for the owner**. This plan is
that third part. It was derived from those lists, from 2b's plan (`build-plan-audit-wave-2b.md`:
chunks 38 and 46, § What moves to a third part, § Decisions made mid-build), from the
coordinator's running list in the landing log, and from the two server ledgers, and every
item was read against the code at `35c12bf0` before it became a chunk. Items the code
already settles are dropped by name in § What the code already settles.

**The size, honestly.** It is a tail: sixteen build chunks, most of them small, grouped by
the files they own; four that wait for the owner; the records; the coordinator's
integration. Chunks 87 and 88 were added after the first draft, from what the Player's
planner measured against the real Player's reader (unreleased 1.3.0 can still change
before its tag), and are numbered after it rather than renumbering the rest. Nothing here is a new feature except the three columns #313 asks for. Most
of it is one of three kinds: a reading that is still taken twice, a sentence or a figure
said two ways, and a test fixture that reads the machine's clock.

**What it does not do**, each by a decision below: build a view model per entity
(draft 38's first half), remove the `DisplayService` facade, or change how the top bar
counts failed fetches.

| Chunk | Title | Model, effort | Waits for |
|---|---|---|---|
| 67 | One reading for the Players answers, and the walls reading's three leftovers | Opus-class, high | — |
| 68 | Ask's and MCP's calls on threads of their own | Opus-class, high | — |
| 69 | Configuration imports only leaves | Sonnet-class, high | — |
| 70 | The reconcile's lookups, batched | Opus-class, high | — |
| 71 | A Get that is gone, and Artworks on a phone | Opus-class, medium | — |
| 87 | Contract 1.3.0 before its tag: three must-refuse rows, and when a refused report is sent again | Opus-class, medium | — |
| 72 | What Status does not say yet, and the queue's two couplings | Opus-class, medium | 67, 70 |
| 88 | A Player whose reports are refused says so | Opus-class, medium | 67, 87 |
| 73 | #313's remainder: Searches, Hit rate, Median latency | Opus-class, high | 67, 71, 72 |
| 74 | The server's sentences: counts said one way, museums by their declared names | Sonnet-class, high | 68, 69, 73 |
| 75 | One mat act, the six read twins, the write routes inventoried | Opus-class, high | 67, 73 |
| 76 | Programming takes its clock and ids, and one owner says what is kept off | Sonnet-class, high | 67, 69, 70, 72, 88 |
| 77 | The shared fixtures' clock and ids, and reports only for walls a Player shows | Opus-class, medium | 72, 76 |
| 78 | `arrt/src/arrt/http/api.py` by resource | Sonnet-class, high | 67, 73, 75 |
| 79 | The browser tests' instants, and the large catalogue | Sonnet-class, high | 67, 71, 72, 73, 77 |
| 80 | The comments sweep (draft 46) | Sonnet-class, high | 67-79 |
| 81 | Four norm texts, and the delegate-verification count | Sonnet-class, high | the owner: Q1; the count question |
| 82 | Contract 1.3.0 frozen beside the others | Sonnet-class, high | 87; the owner: the cap; then the operator's tag |
| 83 | "Your library" in what a person reads | Sonnet-class, high | the owner: the capital |
| 84 | What a household sets, and where (Q3) | written when ruled | the owner: Q3 |
| 85 | Records, and the change record | Opus-class, medium | 67-80, 87, 88, and each of 81-84 done or dropped |
| 86 | Integration and the boundary review (the coordinator's) | — | all |

## Goals

- **Response taken:** proceed. The owner's standing instruction is to fix substantially all
  of the identified product issues by delegated builders under this repository's
  governance. Five questions are open and unanswered (§ What waits for the owner); four
  chunks wait for them and nothing else does.
- **Product:** the household and an agent read one story wherever they read it. A Players
  answer, a walls answer and a scene's walls each say what they say from one reading, as
  2b made the walls answers do. Status names a wall whose feed stopped rolling forward
  because it grew past the contract's bound. Status's sources table says how often each
  museum is asked, how often it has a picture, and how long it takes (#313). Every count is
  written one way ("2,000 works", never "2000 works" beside it), and a museum is named as
  it names itself. An agent can read what the browser reads (the six read routes with no
  MCP twin). A Get that is gone says the server's sentence, and Artworks on a phone shows
  a picture before the fold. And the suite: tests that read the machine's clock through
  the shared fixtures stop doing so, so the pool can reuse them (#438).
- **Architecture, what must hold:** the four seam rules as built and guarded (ruling 9);
  `DisplayService`'s public names unchanged but for the one wrapper 67 removes, listed;
  the MCP surface only grows (its one break was 2b's); the contract is untouched except by
  87, which changes the unreleased 1.3.0 only where a reader's obligation gets smaller, and
  82, which freezes 1.3.0 once it is cut; `contract/released/` is never edited; the HTTP
  surface's paths, methods and answers do not change in 78. **What a Player receives
  changes in no chunk but 87** (three index rows and one table row of the unreleased
  1.3.0), met by the Player plan's Chunk 01 (the `4xx` row) and Chunk 07 (the fixtures, at
  the pin).
- **What must stay possible (ruling 8):** several label outputs on one Player, and a Player
  with labels and no display. 67's one reading of a Player carries each output as today.
- **Constraints:** a delegate runs feature tests only (`project-preferences.md` § Workflow,
  `Delegate verification`), and the governance suite whole when it adds, moves or renames a
  tracked file. Every new or rewritten check comes back with its failing output against
  today's code or a re-break, naming the input. A test is a contract. No chunk adds a step,
  a job or an install to a workflow that runs on GitHub's runner (the owner's ruling of
  2026-11-20: CI is kept small, and makes no paid call). An outage of the pool must not
  block a merge (ruling 4 of 2026-11-19). The MCP client truncates a tool's description at
  2,048 bytes (`DESCRIPTION_BUDGET_BYTES`, `arrt/src/arrt/mcp/registry.py`).
- **Tradeoffs accepted:**
  - Two serializers per entity stay, as the Decision Log says, held by
    `arrt/tests/unit/test_surface_parity.py` (the DECISION below). Revisit when a field
    added to one surface is found missing from the other in a released build.
  - The facade stays (the DECISION below). Revisit when a collaborator needs a caller the
    facade cannot express.
  - The route inventory pairs a route with an MCP action by name; whether the two answer
    alike is held only for the records `test_surface_parity.py` pairs (75 adds the six new
    twins to it). Revisit when a twin is found answering differently.
- **What I would do differently (the advisor's position):** cut 78 (`api.py` by resource)
  first if the plan stalls: it changes nothing anyone reads, its whole value is that a
  3,282-line file becomes several, and it is the one chunk that must follow every other
  chunk touching that file. 79's browser half is next: it is worth doing only if its own
  first measurement says the instants make a test either uncacheable or fragile. I would
  not build the view models at all (decided below), and would ask the owner the five open
  questions in one message now, so that 81 to 84 are not the last thing standing.
- **Decisions made in this plan** (each vetoable; each states its cost and what the thing it
  changes was guaranteeing without anyone writing it down, and was read against the norm
  index and the dated rulings in `.prawduct/owner-rulings.md`):
  - `[DECISION: draft 38's view models are not built: the 2026-07-27 Decision Log entry, as scoped on 2026-08-06, stands (each binding formats its own results; arrt/tests/unit/test_surface_parity.py holds the shapes alike) | audit-2 S7's first half asks for one view model per entity; the Decision Log already weighed it and kept MCP's plain dicts and HTTP's documented pydantic models, because a shared formatter costs one of them; nothing since has changed that weighing, and 2b's parity test now pairs every field HTTP added (Chunk 53); rulings checked: ruling 3 of 2026-11-19 (the one MCP break is spent, so a shared formatter could not change an MCP key anyway); what the two serializers guarantee today: an MCP answer shaped for a model and an HTTP answer shaped for a screen can differ where the Decision Log lets them (the artwork pair); cost: S7's first half stays open, and a field added to one surface still needs a hand edit on the other, caught by the parity test rather than prevented | user can veto/override]`
  - `[DECISION: the DisplayService facade (arrt/src/arrt/programming/display.py) stays | 2a split it into collaborators and kept it as a one-line delegation per method; its removal would rewrite 631 references to services.display in arrt/src and arrt/tests for no change anyone reads; what it guarantees implicitly, which a removal would have to re-establish at every caller: every collaborator built over one store and one FeedPublisher, so one act is one transaction with one set of feeds staged, and on_work_changed composing the reconcile with the theme offers in one place; rulings checked: none bears; cost: a 481-line delegating module and one hop per call | user can veto/override]`
  - `[DECISION: one mat act at the service layer: PreparationService (arrt/src/arrt/library/acquisition/preparation.py) gains one method taking a tagged choice (a preset, a colour, derive, or choose, the paid one), and both bindings map their own arguments onto it; no MCP name, argument or result key changes, and HTTP's body and answer do not change | the architecture norm says a handler that validates is the violation, and set_work_mat and _set_mat_color each validate the same act their own way (audit-2 S7's second half); what the two validators guaranteed: each surface refused in its own words, and HTTP could never reach the paid choose_mat (its body has no such choice); both are kept: the refusal sentences are the service's, and the HTTP binding has no way to send choose; also kept, from wave 1 (audit-2 M4): a paid mat's spend row is written before its colour; rulings checked: none bears; cost: one more type at the service layer | user can veto/override]`
  - `[DECISION: Ask's tool calls and MCP's tool calls each run on a bounded pool of threads of their own, sized from 68's measurement, instead of asyncio's default executor | audit-2 M10: MCP (arrt/src/arrt/mcp/server.py) and Ask (arrt/src/arrt/ask/agent.py) share the default executor, min(32, CPUs + 4) threads, 8 on a four-core NAS, and art_discovery(status) holds a thread up to 45 s (STATUS_HOLD_SECONDS) and a look up to 30 s (LOOK_HOLD_SECONDS); what the shared executor guaranteed without anyone writing it down: at most that many service calls from MCP and Ask together were ever in flight, so the store's writers and the paid paths saw a bound on concurrency that nobody set; separate pools raise that bound to their sum, so 68 states the new total, measures the store's lock waits at it, and keeps the paid paths' own limits (the unattended allowance, the provider's cap) untouched; rulings checked: none bears; cost: more threads at peak, and two numbers to keep where there was none | user can veto/override]`
  - `[DECISION: the reconcile asks the Library about a whole set of works with a fixed number of store reads, inside LibraryFacade.playable, whose signature and answer do not change | ruling 5 of 2026-11-20 accepted the half-hourly reconcile's wait "until its lookups are batched", and 2b measured 85-90% of a pass in the per-work lookups; what per-work reads guaranteed: each work was read at its own moment, so a work changed mid-pass was seen as it then was; one batch reads the set as one snapshot, which is at least as consistent, and holds that snapshot's rows in memory at once (5,000 works' inputs); the content hash of each master (with_content) is read no more often than before; rulings checked: ruling 5 (the wait it bounds), ruling 9 (rule 2's remote shape kept); cost: a batch query per input kind in the catalogue's store, and a test that counts store reads | user can veto/override]`
  - `[DECISION: Status's sources table gains three columns from the search record #313 asked for, defined as: Searches, the works this source was last searched for (at most SEARCHES_COUNTED, 100, its newest); Hit rate, of those it answered, the share it answered with at least one image (SourceSearch.images > 0); Median latency, the median of answered_at less asked_at over those it answered; a source with no answered search reads "—" in the last two | #313's acceptance asks that what the columns count be written; the record already keeps every value they need, so no column or table is added and nothing persisted changes; what the record's retention guarantees and this keeps: one row per work and source, the newest, so a latency or a hit rate is over each work's newest search only, never its history; rulings checked: none bears; cost: a rate over a source's last hundred works says how it does now, not over all time, and a source answering late (an owed answer arriving after the run stopped waiting) counts its true latency | user can veto/override]`
  - `[DECISION: every count the server writes in a sentence goes through arrt.counting, and counted groups digits from a thousand ("2,000 works"); a guard refuses a word chosen by a hand-written test of one (== 1 else) in a server module, as arrt/tests/unit/test_one_cost_formatter.py refuses a hand-formatted dollar | 2b's boundary review (R-5, accepted for this part): about twenty sentences chose their noun by hand and two grouped digits, so the server wrote a count of thousands two ways; what the two ways guaranteed: nothing anyone relied on, but sentences pinned verbatim by tests, which 74 lists as rewritten; rulings checked: none bears; cost: every count of a thousand or more in a sentence an agent or a person reads gains its comma, MCP notices and refusal texts included (no result key changes) | user can veto/override]`
  - `[DECISION: Programming's collaborators take a clock and an id source, each defaulting to the machine's, and an act reads its clock once | 2b's Chunk 43 did the same for CatalogueService and DiscoveryService, and Chunk 39 made each feed act read the clock once; arrt/src/arrt/programming/ reads datetime.now(UTC) at 23 sites and uuid.uuid4() at 9; what direct reads guaranteed: two reads within one act could differ, which Chunk 39 already found was a defect where it mattered; cost: as Chunk 43's, a constructor that forgets to pass one still reads the machine's | user can veto/override]`
  - `[DECISION: the shared fixtures in arrt/tests/conftest.py pass every service a clock that starts at a fixed instant and moves forward a fixed step on each read, and an id source that counts | 2b measured half the suite uncacheable, with a clock read the largest cause (testament's cache advice, its integrator's pass 11), and found that only the shared fixtures passing a clock would change it (landing log, Chunk 43); what the machine's clock and uuid4 guaranteed and the fakes must keep: instants strictly increasing across reads and threads within a test, ids unique across every service of a test and across the files they name under the art root; a fixed instant that never moved would break every test ordering by time; rulings checked: none bears; cost: a test that compares a service's instant with datetime.now() of its own must take the fixture's clock instead, each listed, and a run reads as on one fixed day, so a defect that shows only on some dates (a month's end) is not met by chance any more | user can veto/override]`
  - `[DECISION: arrt/src/arrt/http/api.py is split into one module per resource under a new arrt/src/arrt/http/routes/ package, with every route's path, method, name, model and registration order unchanged, held by app.openapi() and the route table compared byte for byte | draft 38's mechanical half (audit-2 S6: big files); what one file guaranteed: the order routes are registered, which FastAPI matches in, so a fixed path beside a parameter path (a /works/search beside a /works/{id}) answers the same only if the order is kept; and the three names tests import from arrt.http.api, kept by re-export; rulings checked: none bears; cost: every line reference to api.py in the records goes stale (85 re-points them), and a pull request open across the move meets a conflict | user can veto/override]`
  - `[DECISION: of the 28 manifest.v2 fixtures the unreleased 1.3.0 marks player_must_refuse, three are marked false before the tag: generated-at-malformed, generated-at-not-text and work-media-content-type-unknown; staging-repeated stays true | the index's own rule, unchanged since 1.2.0's _about: "a Player refuses what it acts on (shape it reads, instants, the semantic rules) and never a presentation setting", and player-contract.md § Versioning: "A Player refuses only what the index marks player_must_refuse, which is what it cannot act on safely"; no Player acts on generated_at (no rule of § Major 2 reads it; it is not a slot's instant), and none acts on content_type (a Player decodes the bytes and checks their sha256); an enum a later minor may widen (moving media, player-contract.md: content types are #424's second half) must be tolerated by a reader, or that minor is not additive for it; staging is acted on, and a repeated item is a fault in what the reader reads; measured by the Player's planner at its HEAD: its reader accepts all four and refuses the other 24; what marking them true guaranteed: nothing a Player relied on, and it made a minor narrow a reader's obligation, which § What a Player does at 1.3.0 says it does not ("Nothing a Player reads, writes or requests must change"); rulings checked: the 2026-11-13 ruling (a reader ignores a kind it does not know, the same reasoning for media kinds); cost: none to the server (its writer is held to the schema, which still refuses all four), none to a Player; a future Player that comes to act on generated_at must have its reader rule added in a later minor, which would then be a narrowing to record; staging-repeated stays a new reader obligation in a minor, and 87 checks whether 1.2.0's prose already obliged it, putting it to the owner beside the cap if it did not | user can veto/override]`
  - `[DECISION: the transport table stands: a refused client heartbeat (the 400 rows) is sent again when the report changes, and 1.3.0's row says what "changes" means, everything but reported_at; the server, which writes nothing of a refused report, now remembers the refusal's sentence per Player (88) | the Player's planner read in its code (Supervisor._report_outputs, not yet run) that a refused report is sent again every cycle, where the row says "say so once, and send again when the report changes"; the server's side at HEAD: the route refuses with ServiceError (arrt/src/arrt/programming/clients.py record_heartbeat), writes no journal line of its own, and uvicorn's access line for each 400 is kept (logs.QuietPlayerPolls drops only 2xx and 304), so a Player sending every cycle writes a line each cycle of its supervisor (about 30 s, as the Player's planner read it; the contract states no client-heartbeat interval), and Status calls that Player waiting for its first report or not heard from, never refused; nothing is a corrected record (corrected is a field of the contract's table, never written at run time); why the table and not the behaviour: the same bytes get the same answer, so resending says nothing new, and a heartbeat's liveness is already the report's age; but every report's reported_at differs, so the row read literally lets a Player resend every cycle, which is why it is clarified; what the resend guaranteed: a server fixed by an upgrade heard from the Player within one interval; under the table it is heard when the report next changes or the Player restarts, which is why 88 makes Status name the refused report rather than a Player merely not heard from; rulings checked: none bears; cost: after a server upgrade that would accept a report it refused, Status says the last report was refused until the Player's report changes or it restarts | user can veto/override]`
  - `[DECISION: AcquisitionQueue.failed_states keeps reading every owed work to count the failed ones, unchanged | 2b's boundary review left it: the top bar's health read grows with the works owed an image, not with the failed count; measured bounded at 2,000 failed works (Chunk 40); a household's owed works are those waiting for an image, usually far fewer than it holds; what a count query would change: Activity › Queue's "Failed (N)" and the badge are held alike today because both read the same rows through the same _state (test_failed_fetches.py), and a separate count would need a second statement of what failed means; rulings checked: none bears; cost: a read per health poll that grows with the owed works; reopen if GET /api/health is measured past a tenth of a second | user can veto/override]`
- **Inferred, not ruled:** that `/api` has no reader but the browser (`api-contract.md` §
  The HTTP surface says nothing outside this repository may bind to it; 78 rests on it).
  That browser tests are uncacheable for their server process whatever their instants
  (79 measures it first and stops if it is wrong).
- **Level:** High for 69, 74, 76, 78, 80, 81, 82, 83 (named sites, mechanical checks).
  Medium for the rest: each has a choice its builder makes against stated acceptance. What
  would raise it: 68's measurement before any code (does a held status call starve the
  ninth call on eight threads), 70's read count before any code, and 75's byte count of
  every tool before any code.

## Verification strategy

Beyond each chunk's tests, the product is exercised as its readers meet it:

- **What a person reads** (67's walls, 71, 72, 73): the coordinator walks the screens the
  chunk changed with `docs/ux-walkthrough.md`'s steps on the integrated head, at desktop and
  at 390 px, and each visual chunk adds its `.prawduct/operator-verification.md` entry.
  71's phone change is measured on the walk's own phone screenshot of Artworks before and
  after.
- **What an agent reads** (67, 73, 75): each new or changed MCP answer is compared with
  its HTTP twin on the same seeded Library by the parity test, and the integrator reads one
  real `tools/list` answer to see the descriptions fit (`test_mcp_surface.py` holds the
  budget).
- **Waiting and concurrency** (68, 70): measured in-process, seven passes after a warm one,
  as 2b's Chunk 60 measured the reconcile, at 2,000 and 5,000 works; each figure is a
  measurement with its machine and its N, never a guess, and the change record says that
  nothing was measured on the NAS.
- **The suite** (77, 79): testament's own cache advice, read from a full `--no-cache` run's
  envelope before and after, by cause; the figures go in the change record as measured.
- **CI's own guard** (86): the workflow's pool step and `assert_tests_ran.py` run over its
  report on the head, and the fallback's three steps in a clone without tags (2b's last
  required-check red came from never running the guard over the pool's report).

## Commit subjects, so the review can attribute each chunk

- **Every commit a delegate makes:** `<type>(audit-wave-3): <what is now true> (Chunk NN)`,
  `<type>` one of `fix`, `feat`, `test`, `refactor`, `docs`, `ci`, `chore`.
- **The integrator's merge of each branch:** `git merge --no-ff -m
  "merge(audit-wave-3): <the chunk's title> (Chunk NN)" <branch>`; never a fast-forward.
- **The integrator's own fixes:** `fix(audit-wave-3): <what> (Chunk 86)`.
- **No attribution trailers**, whatever a session reminder asks: `project-preferences.md`
  says `Commit attribution: none`, and the preference outranks the reminder. The integrator
  counts trailer lines on each branch before merging it and returns any that has them.
- **The boundary review** names the chunks it covers with `critic-begin --chunks`.

## What 2b taught, built into every chunk

The ten lessons of the delegate brief for part 2b are part of every chunk's acceptance
here, and each brief quotes them: (1) list and test a replaced mechanism's implicit
guarantees; (2) grep for the siblings of a fixed defect and fix or list them; (3) a value two
places state has one owner and a test that fails on divergence; (4) a rewritten assertion is
named in its commit with what it asserted and why, and nothing is loosened, skipped,
xfailed or deleted; (5) a test that reads a file outside `arrt/` says so (the image's test
stage carries only some root files); (6) a foreign tool's output is tested on lines copied
from an observed run; (7) a decision records its cost and is checked against the dated
rulings; (8) a scratch directory of the delegate's own; (9) a change to
`arrt/src/arrt/http/models.py` runs the whole browser suite, because
`arrt/tests/browser/payloads.py` builds its answers from those models; (10) run the guards
that read what you add (`arrt/tests/unit/test_browser_reads_retry.py` and
`arrt/tests/unit/test_client_vocabulary.py` for a browser test, every whole-answer
comparison for a new field, the governance suite whole for a tracked file).

And two from 2b's last passes:

11. **A reading is taken once per answer.** 2b's walls answers read a wall's report three
    times and could say a wall waits beside a badge showing its work. Every chunk here
    that builds an answer from several facts builds it from one reading and proves it with
    a count of reads and an interleaving test, as `arrt/tests/integration/test_client_tools.py`
    does for the walls.
12. **CI's own guard is run over the pool's report before a pull request**, not only the
    suites (86).

## Shared seams this wave

A file two chunks touch has one owner at a time; the order is the partition's. No two
chunks of one dispatch group own the same file.

- `arrt/src/arrt/services/health.py`: 67 (`observe_walls`, `WallsNow`), then 72 (the
  troubles, `failure_instant`), then 73 (`SourceHealth`'s search fields), then 74 (its count
  sentences).
- `arrt/src/arrt/http/api.py`: 67 (the clients answers), then 73 (the sources answer), then
  75 (`set_work_mat`), then 78 (the move). `arrt/src/arrt/mcp/bindings.py`: 67 (the clients
  actions), then 73 (`source_plugins`), then 75 (the mat act and the new actions).
- `arrt/src/arrt/http/models.py`: 72 (`TroubleOut`'s kinds), then 73 (`SourcePluginOut`).
  Each runs the whole browser suite.
- `arrt/src/arrt/programming/feeds.py`: 70 (the reconcile's calls into the Library), then 72
  (the over-bound record's reader), then 76 (its clock and the kept-off read).
- `arrt/src/arrt/programming/clients.py`, `walls.py`, `reports.py`, `scenes.py`,
  `display.py`: 67, then 76.
- `arrt/src/arrt/services/container.py`: 72 (the identity service's `on_changed`), then 76
  (Programming's construction), then 77 (`Services.bind`'s clock and id source).
- `arrt/src/arrt/ask/agent.py`: 68 (the executor), then 74 (two count lines).
- `arrt/src/arrt/library/sources/loading.py`, `arrt/src/arrt/library/services/runner.py`:
  69 (names moved out, re-exported), then 74 (their sentences).
- `arrt/src/arrt/http/static/app.css`: 71 (the phone toolbar), then 73 (the sources table's
  widths). `arrt/src/arrt/http/static/screens/health.js`: 72 (the new trouble's link), then 73.
- `arrt/tests/conftest.py`: 77, then 79 (`build_large_catalogue`).
- `arrt/tests/unit/test_surface_parity.py`: 67 (a clients reading pair, if needed), then 73,
  then 75 (the route inventory).
- `.prawduct/artifacts/api-contract.md`: 75 (the MCP rows), then 85 (the rest).
- `.prawduct/artifacts/project-preferences.md`, `.prawduct/artifacts/data-model.md`,
  `.prawduct/artifacts/architecture.md` § Direction: 81 only (the norm texts), then 85.
- `contract/` and `.prawduct/artifacts/player-contract.md`: 87 (the index's three rows, the
  client heartbeat's `400` rows, § Releases' 1.3.0 entry, § Transport's sentence), then 82
  (the frozen copy, § Releases, § Versioning).
- `arrt/src/arrt/programming/clients.py`: 67 (the Players reading), then 88 (the refusal
  remembered), then 76 (its clock and ids).

## Where each item went

Every item the inputs list, by source, with where it went. "Settled" items are in §
What the code already settles, with their evidence.

| # | Item, and where it was recorded | Goes to |
|---|---|---|
| T1 | Draft 38: view models per entity (audit-2 S7's first half; ledger row 29) | Not built: the first DECISION |
| T2 | Draft 38: `api.py` by resource router (audit-2 S6; row 28) | 78 |
| T3 | Draft 38: one mat act (audit-2 S7's second half; row 29) | 75 |
| T4 | Draft 38: the `DisplayService` facade's removal (2a's tradeoff) | Not built: the second DECISION |
| T5 | Draft 38: the N+1 reads per card and per wall, if measured (audit-2 M9; row 41) | 70 measures the walls' and Artworks' reads at 5,000 works and changes only the reconcile's; the figures go to the change record |
| T6 | #307: exclusions scanned at many sites (2b C42) | 76 (the one part left; the other two settled) |
| T7 | Draft 46: dates and issue numbers in module docstrings (audit-2 comments; row 47) | 80 |
| T8 | "display plane" and "curation plane" left in comments (audit-1 M9b's remainder; row 18) | 80 |
| T9 | Comments that cite a chunk by number alone (2b's records observation) | 80 |
| T10 | Configuration imports service modules (audit-2 M12; row 44) | 69 |
| T11 | Ask's and MCP's executors (audit-2 M10; row 42) | 68 |
| T12 | Six read routes with no MCP twin; no inventory of the write routes (2b Chunk 53) | 75 |
| T13 | #313's remainder: latency, found and found nothing, the three columns; `SourceSearch.images` unread | 73 |
| T14 | The shared fixtures' clock and id source (#438) | 77 |
| T15 | Batching the reconcile's per-work lookups (ruling 5 of 2026-11-20) | 70 |
| T16 | `museum_name(` without the declared name (2b's left-open list) | 74 |
| T17 | Direct clock reads in Programming's modules (2b's left-open list) | 76 |
| T18 | The prototype-scale test's `build_large_catalogue` (2b Chunk 43) | 79 |
| T19 | Browser tests that seed a time from `datetime.now` (#438's remainder) | 79, after its own measurement |
| T20 | About 28 client strings say "your library" (for the owner) | 83, waits for the owner |
| T21 | The run's not-found page draws the router's words | 71 |
| T22 | `walls.js` joins `waiting_for` from `/api/health` | 67 |
| T23 | A guard for fixtures that write a wall's report for a wall no Player shows (2b Chunk 63) | 77 |
| T24 | The cost words say a spend under a hundredth of a cent two ways | Settled by 2b's record: "both true and left so" |
| T25 | The route inventory pairs by name only | The tradeoff in § Goals; 75 pairs its six new twins by record |
| T26 | The Players answers pair a survey with a second one (boundary review) | 67 |
| T27 | Counts hand-rolled beside `arrt.counting`; digits grouped two ways (R-5) | 74 |
| T28 | A wall whose feed would exceed the bound stops rolling forward, said only once in the journal | 72 |
| T29 | Every top-bar health read scans every owed work | Not changed: the last DECISION |
| T30 | A Wikidata item changed while the queue sleeps waits for the next nudge or a day | 72 |
| T31 | `dezoomify.py`'s disk-fault words keyed by hand against `atomic.DISK_FAULT_ERRNOS` | 72 |
| T32 | `failure_instant` inverts the queue's `RETRY_AFTER` outside the queue | 72 |
| T33 | Native review 2's (6) two wrappers over one walls reading, (7) a wall's state carried twice, (8) a scene's walls read every report | 67 |
| T34 | Native review 2's (5) alternating failures never give up | Settled by 2b's record: accepted as its cost |
| T35 | A run that stopped waiting before its worker reached the check writes only `image_pool.late` at WARNING (the last review's demoted observation) | Not built: the line exists and names the late answer; no reader counts it |
| T36 | Q1, the four norm texts, and the forbidden-columns check (rows 7, 8, 37) | 81, waits for the owner |
| T37 | The delegate-verification norm says five where there are six suites | 81, waits for the owner |
| T38 | Contract 1.3.0's cap as a bounded exception; the tag and its frozen copy | 82, waits for the owner and the operator |
| T39 | Q3, which household settings are set where (rows 74, 81, 83, L33) | 84, waits for the owner |
| T40 | #318's measurement against the real library | The operator's, after a Retry of the real queue (86's checklist) |
| T41 | #442's cause | Not established; every Skip test now asserts its POST, so the next red names it. No chunk |
| T42 | #150, the paid probe re-checked by hand | The operator's (86's checklist) |
| T43 | `test_rerun_command` in `.prawduct/project-state.yaml` (#438's "Also") | The coordinator's, in 86 (a governance file no delegate writes) |
| T44 | Ledger "after wave 2": `import_graph.py` and governance code copied between repositories (rows 11, 128) | Not here: needs this and the Player's planner at once; the coordinator raises it with both plans in hand |
| T45 | Ledger "after wave 2": `discovery.py` (#48) and `runner.py` (#80) | Not here: each a design-stage backlog item of its own, unchanged by the audit |
| T46 | Ledger "after wave 2": the October items #252, #282, #320 and smart playlists (row 89) | Not here: each its own backlog item at requirements or research |
| T47 | Ledger "after wave 2": sighting hosts have no UI (row 91) | Not here: no scenario asks for it and a page needs a design; 85 files it if no issue holds it |
| T48 | Ledger "after wave 2": Artworks' chrome on a phone (row 108, ux-review #41) | 71 |
| T49 | Ledger "after wave 2": governance records moved at a release (row 120) | The coordinator's, at the release |
| T50 | `security-model.md` still says the CI OpenRouter key's ceiling is unknown, where CI holds no such key | 85 |
| T51 | Q4's runners ruled ("all runners are fine"); `security-model.md` does not record that third-party runners run this repository | 85 |
| T52 | Four of 1.3.0's 28 must-refuse manifest fixtures are accepted by the real Player's reader (the Player's planner, measured at its HEAD; the coordinator's message of 2026-11-20) | 87 (three marked by the rule; `staging-repeated` kept, the Player enforces it) |
| T53 | A refused client heartbeat is resent every cycle by the Player, where the table says when the report changes (read in the Player's code, not run) | 87 (the row clarified), the Player plan's Chunk 01 (its behaviour) |
| T54 | A Player whose every report the server refuses reads as waiting for its first report or not heard from, and the refusal's sentence reaches only the access log | 88 |

## What waits for the owner

Each was checked against `.prawduct/owner-rulings.md` (2026-11-19 and 2026-11-20); none has
a ruling. Asked once, together, as the advisor recommends.

- **Q1 (four norm texts):** may (a) the async scope (`project-preferences.md` § Architecture
  Patterns), (b) the lint selection (§ Code Style), (c) the per-device norm
  (`data-model.md` § Direction) and (d) Direction norm 1's home (`architecture.md`) be
  amended to state what the code does, each with a dated note, and (c) be held by
  `arrt/tests/unit/test_catalogue_store.py`'s forbidden-columns check? → 81.
- **The delegate-verification count:** `project-preferences.md` `## Workflow`, `Delegate
  verification`, says a change to `contract/` "runs all five" where there are six suites,
  and the same file's § Testing says a full run is "all six". Is five (the suites that read
  the contract) meant, or six? → 81.
- **Contract 1.3.0's cap:** ratify the cap of 32 outputs and 32 label outputs per client
  heartbeat as a second bounded exception to "a minor is additive" (`player-contract.md` §
  Versioning), or have the cap wait for a major? `contract-v1.3.0` is not cut until this is
  answered (the 2026-11-13 ruling: the owner approves a contract tag). Nothing in this plan
  assumes the answer. → 82. The Player plan's Chunk 07 (its pin to 1.3.0) waits for the
  same answer, the tag, and 87.
- **Possibly, `staging-repeated`:** if 87 finds that 1.2.0's prose did not already oblige a
  reader to refuse a repeated staging item, marking it must-refuse in 1.3.0 is a third
  narrowing, asked beside the cap (ratify, or mark it false and let the Player enforce it
  as its own choice). → 87, then 82.
- **"Your library":** 31 occurrences of "your library" in 13 client files at `35c12bf0`
  (some in comments) and five server sentences (`arrt/src/arrt/ask/agent.py`'s four
  progress words, `arrt/src/arrt/library/services/registry_search.py`'s note). Ruling 2
  says the holdings are *the Library*: do these take the capital, become "the Library", or
  stay as the household's lower-case phrase? → 83.
- **Q3 (settings):** which presentation and household settings the server lets a household
  set, and where (a wall's label facts and text size; a label output's viewing distance;
  the rest marked coming). → 84.

## Decisions made mid-build

- **2026-11-20 (Chunk 68, as integrated), a bound that the old shared pool was giving without
  anyone naming it:** Ask's and MCP's calls now run on pools of their own (16 and 8 threads),
  which ends the starvation the chunk measured (with eight calls held, a ninth MCP call and
  an Ask reply waited for a hold to end; now neither does). The old pool of eight was also
  the only bound on how many looks could run at once, and each look opens up to six preview
  fetches of up to 16 MiB each, which keep running past the look's deadline: sixteen looks
  can mean ninety-six preview reads, about 1.5 GiB at the cap, where eight meant about
  768 MiB. Read from the code by the integrator, not measured. The server's memory is
  bounded by its container's limit, which is the operator's and is not in this repository.
  Chunk 89 gives the preview fetches a bound of their own, so a pool's size does not set
  the server's memory.
- **2026-11-20 (Chunk 67), two acceptance items met in part, accepted:** a scene's walls read
  only their own walls' reports and still read every Player's report once, because whether a
  display is in fault lives only there; and Walls still asks the health answer for one case
  (a hung, Player-shown, silent wall with nothing it last said and waiting for no one),
  because the walls answer carries no report problem. Chunk 72 puts that problem on the
  walls answer.
- **2026-11-20 (Chunk 70), what batching did and did not buy:** the Library answers a set of
  works in five store reads where it sent about ten a work. Measured in-process on one
  loaded machine, old and new taking turns: a reconcile with nothing to fix went from 629 to
  250 ms at 2,000 works on four walls and from 3,454 to 1,534 ms at 5,000 on twelve. The
  cadence (every sixth scheduler pass) is left as it is: what remains of a pass is outside
  the Library (each wall's feed parsed about three times), and Chunk 72 takes that.
- **2026-11-20, the pool and this machine were saturated by other work while this plan was
  built:** runs lost their connection, fell back to this machine and queued for an hour, and
  the pool's one runner with a browser crashed renderers under load (counted by the
  integrator across its passes). Delegates and the integrator run with no fallback; a red
  that is only a renderer crash is rerun once by file and counted.

## Chunks

### Chunk 67: One reading for the Players answers, and the walls reading's three leftovers

- **Type:** code
- **Exposed API:** `/api` (the clients routes), MCP (`art_players(action='clients')`)
- **Closes:** T26, T33, T22.
- **Found at HEAD:** the Players answers take `placements.survey()` beside a reading of
  their own: `_clients` in `arrt/src/arrt/http/api.py`, the answers to adding and renaming a
  Player in the same file (each `_client(services.clients.get_client_view(...),
  services.clients.placements.survey())`), and `_list_clients` in
  `arrt/src/arrt/mcp/bindings.py`, so a Player assigned between the two reads can be
  answered unassigned beside the wall it shows. The walls reading has two wrappers over one
  `Placements.read_walls()`: `Walls.read_reports` (`arrt/src/arrt/programming/walls.py`,
  read by `arrt/src/arrt/programming/scenes.py`) and `Reports.read_wall_reports`
  (`arrt/src/arrt/programming/reports.py`, exposed as `DisplayService.read_wall_reports`
  in `arrt/src/arrt/programming/display.py`, read by `HealthService`). `WallsNow`
  (`arrt/src/arrt/services/health.py`) carries a wall's state twice, in each view's
  `display_state` and again in `walls[id].state` rebuilt by `wall_statuses`. A scene's wall
  list reads every wall's and every Player's report file inside the store's read scope,
  however few walls it pins. `arrt/src/arrt/http/static/screens/walls.js` reads `/api/health`
  to learn whom a wall waits for, though the walls answer has carried `waiting_for` since
  2b's Chunk 66, so the card and the wall can come from two readings.
- **Owns:** `arrt/src/arrt/programming/clients.py` (the Players reading),
  `arrt/src/arrt/programming/walls.py` and `arrt/src/arrt/programming/reports.py` (the
  reading's wrappers), `arrt/src/arrt/programming/scenes.py` (the scene's walls reading),
  `arrt/src/arrt/programming/display.py` (the wrapper's delegation),
  `arrt/src/arrt/services/health.py` (`observe_walls` and `WallsNow` only),
  `arrt/src/arrt/http/api.py` and `arrt/src/arrt/mcp/bindings.py` (the clients answers
  only), `arrt/src/arrt/http/static/screens/walls.js` (where `waiting_for` is read),
  `arrt/tests/integration/test_client_tools.py`, `arrt/tests/unit/test_display_facade.py`
  (`ADDED` only), `arrt/tests/unit/test_scenes.py`, `arrt/tests/browser/test_the_walls.py`.
- **Must not touch:** any answer's bytes at rest; `arrt/src/arrt/http/models.py`.
- **Deliverables:**
  - Every Players answer (the list, one Player, adding one, renaming one; HTTP and MCP)
    says everything it says of each Player from one reading, in one store scope, as
    `HealthService.observe_walls` does for walls.
  - One entry point to the walls reading; the other wrapper is gone and its callers read
    the one.
  - A wall's state is carried once in `WallsNow`; every reader takes it from there.
  - A scene's walls read only the reports of the walls it pins and the Players that show
    them.
  - Walls reads whom a wall waits for from the walls answer and no longer asks
    `/api/health` for it.
- **Implicit guarantees** of the second reading and the second wrapper, each tested: (a) a
  Player's answer still names every output it reported, several labels and no display
  included (ruling 8); (b) a wall deleted while a list is built does not refuse the whole
  answer (2b found and fixed this for walls); (c) the scene's walls keep their order.
- **Acceptance:**
  1. A Player assigned to a wall between the two reads of today's `_clients`, forced by an
     interleaving as `test_client_tools.py` forces the walls': the list says it shows that
     wall on both surfaces; red at `35c12bf0` on HTTP and on MCP.
  2. A count of report-file reads: a Players list over three Players and four walls reads
     each Player's report once; red today.
  3. A scene pinning one of ten walls reads that wall's report and its Player's, and no
     other; red today.
  4. A Walls page whose `/api/health` route is made to fail still says "waits for The
     living room Pi" on a waiting wall, and the page makes no request to `/api/health`;
     red today.
  5. Every answer's bytes at rest identical before and after (ids, times and ages
     normalised), as 2b's Chunk 55 compared the walls answers.
- **Rewritten assertions:** `test_display_facade.py`'s `ADDED` loses whichever wrapper goes,
  with the reason in the commit.
- **Records owed:** `.prawduct/artifacts/architecture.md` (the one reading, if it names the
  wrappers).
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/integration/test_client_tools.py arrt/tests/unit/test_display_facade.py
  arrt/tests/unit/test_scenes.py arrt/tests/unit/test_surface_parity.py
  arrt/tests/contract/test_client_surface.py arrt/tests/integration/test_browser_surface.py`;
  `testament run --json=summary --suite browser -- arrt/tests/browser/test_the_walls.py
  arrt/tests/browser/test_setting_up_a_wall.py`; the two browser guards; mypy, ruff and black
  in `arrt/`.
- **Model:** Opus-class, high: consistency across concurrent reads, on two surfaces, the
  shape 2b fixed twice and still left once.
- **Waits for:** —.

### Chunk 68: Ask's and MCP's calls on threads of their own

- **Type:** code
- **Closes:** T11 (audit-2 M10), after its measurement.
- **Found at HEAD:** MCP runs each tool call with `asyncio.to_thread`
  (`arrt/src/arrt/mcp/server.py`), and Ask runs its tools and its taste read the same way
  (`arrt/src/arrt/ask/agent.py`), so both share asyncio's default executor: min(32, CPUs +
  4) threads. `art_discovery(status)` holds its thread up to `STATUS_HOLD_SECONDS`, 45 s
  (`arrt/src/arrt/library/services/runner.py`), and a look up to `LOOK_HOLD_SECONDS`, 30 s
  (`arrt/src/arrt/library/services/look.py`). HTTP handlers use anyio's own pool. The audit
  marked the starvation inferred, not observed.
- **Owns:** `arrt/src/arrt/mcp/server.py`, `arrt/src/arrt/ask/agent.py` (where its calls
  are dispatched to threads only), a new module for the two pools if one is needed:
  new `arrt/src/arrt/services/threads.py`; and new tests:
  new `arrt/tests/integration/test_tool_call_threads.py`.
- **Must not touch:** the services the tools call; `arrt/src/arrt/http/`.
- **Deliverables:**
  - **First, the measurement**, returned before any code: with the default executor sized
    as on a four-core machine (8), eight concurrent `art_discovery(status)` holds and then
    a ninth MCP call and one Ask tool call; how long each of the last two waits. If neither
    waits for a hold, the chunk stops and reports the measurement, and the finding is
    closed as measured.
  - Otherwise: MCP's calls and Ask's each run on a bounded pool of their own, sized and
    named, so a hold on one surface never starves the other, and a held call on one never
    starves a short call on the same surface beyond its pool's size.
  - The new total of concurrent service calls stated, with the store's lock waits measured
    at it; a call refused or queued for want of a thread writes a journal line with an
    `event` field.
- **Implicit guarantees** of the shared executor (the DECISION): the bound it set on
  concurrent service calls from MCP and Ask together. The test states the new bound and
  that it holds.
- **Acceptance:** with eight holds in flight, the ninth MCP call and an Ask tool call each
  answer within a second; red today with the executor at 8 (the measurement is the red).
  A test that the pools' sizes are the named constants. Shown red first.
- **Records owed:** `.prawduct/artifacts/observability-strategy.md` (the event);
  `.prawduct/artifacts/architecture.md` § Cross-Cutting Runtime Concerns (the pools).
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/integration/test_tool_call_threads.py arrt/tests/unit/test_ask_agent.py
  arrt/tests/contract/test_mcp_surface.py arrt/tests/integration/test_ask_surface.py`; mypy,
  ruff and black in `arrt/`.
- **Model:** Opus-class, high: waiting and concurrency, and a guarantee nobody set that the
  change removes.
- **Waits for:** —.

### Chunk 69: Configuration imports only leaves

- **Type:** code
- **Closes:** T10 (audit-2 M12).
- **Found at HEAD:** `arrt/src/arrt/config.py` imports `DEFAULT_PREVIEW_MAX_BYTES`
  (`arrt/src/arrt/library/discovery/images.py`), `QualityProfile`
  (`arrt/src/arrt/library/services/quality.py`), `DiscoverySettings`
  (`arrt/src/arrt/library/services/runner.py`), `Limits`, `SettingRefused` and
  `from_environment` (`arrt/src/arrt/library/services/settings.py`),
  `DEFAULT_SOURCE_ORDER` (`arrt/src/arrt/library/sources/loading.py`), `DEFAULT_WALL_NAME`
  (`arrt/src/arrt/persistence/migrations.py`), `heartbeat_path_in`
  (`arrt/src/arrt/programming/manifest/heartbeat.py`) and the v2 feed's path helpers
  (`arrt/src/arrt/programming/manifest/v2.py`): configuration depends on the service layer.
- **Owns:** `arrt/src/arrt/config.py`; the named definitions in the modules above (moved
  out, re-exported where they were); one or more new leaf modules:
  new `arrt/src/arrt/defaults.py`; new `arrt/tests/unit/test_config_imports_leaves.py`;
  `arrt/tests/unit/test_config.py`.
- **Deliverables:**
  - Every `arrt` module `config.py` imports is a **leaf**: it imports no `arrt` module but
    other leaves. The rule is checked, not described.
  - Each moved name is still importable from its old home, as the same object.
- **Implicit guarantees** of the old imports, each tested: (a) every name a caller imports
  from its old home resolves to the same object (a test over the moved names, `is`); (b)
  `Settings.from_env` builds the same values from the same environment (the existing
  `test_config.py`, unchanged); (c) no import cycle at start (the server process starts in
  the system tests).
- **Acceptance:** the leaf guard is red at `35c12bf0`, naming each non-leaf import; red again
  when one import of `arrt.library.services.runner` is planted back; the moved names' test
  red when a re-export is removed.
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/unit/test_config.py arrt/tests/unit/test_config_imports_leaves.py
  arrt/tests/system`; the governance suite whole (it adds a tracked file);
  `tests/preferences/test_seam_imports.py` within it; mypy, ruff and black in `arrt/`.
- **Model:** Sonnet-class, high: named imports, a move, and a guard with a crisp rule.
- **Waits for:** —.

### Chunk 70: The reconcile's lookups, batched

- **Type:** code
- **Closes:** T15 (ruling 5 of 2026-11-20's condition), T5 (measured).
- **Found at HEAD:** `LibraryFacade.playable` (`arrt/src/arrt/library/facade.py`) takes a
  set of ids and answers each with `_answer`, which reads the work, its original, its
  renditions and its mat colour one by one through `CatalogueService`
  (`arrt/src/arrt/library/services/catalogue.py`), then the master's content and pixel size.
  The reconcile (`FeedPublisher.reconcile`, `arrt/src/arrt/programming/feeds.py`) asks it
  for every work of every wall's hung theme under the store's lock. 2b measured a pass with
  nothing to fix at about 0.4 s at 2,000 works and 1.1 to 2.5 s at 5,000 on one machine,
  85-90% of it these lookups, and an act arriving during a pass waits for it
  (`RECONCILE_EVERY_PASSES`, `arrt/src/arrt/services/container.py`).
- **Owns:** `arrt/src/arrt/library/facade.py` (`playable`'s internals),
  `arrt/src/arrt/library/services/catalogue.py` (batch reads),
  `arrt/src/arrt/persistence/sqlite.py` (the batch queries), the catalogue store's protocol
  if it declares them, `arrt/src/arrt/programming/feeds.py` (the reconcile's calls only),
  `arrt/tests/unit/test_library_facade.py`, `arrt/tests/unit/test_reconciliation.py`, and a
  new test (new `arrt/tests/integration/test_reconcile_reads.py`).
- **Must not touch:** `playable`'s signature and answer; the readiness rule
  (`arrt/src/arrt/library/readiness.py`).
- **Deliverables:**
  - **First, the count**, returned before any code: store reads per `playable` call at 10,
    100 and 1,000 works.
  - `playable` reads a set of works with a fixed number of store reads, however many works.
  - The reconcile's time measured as 2b measured it, at 2,000 and 5,000 works, before and
    after; and `GET /api/walls` and Artworks' first page at 5,000 works, reported only
    (T5).
- **Implicit guarantees** of per-work reads, each tested: (a) every id asked is answered,
  one the Library does not hold included, as `NOT_IN_CATALOGUE`; (b) an id asked twice is
  answered once; (c) one call states one set of units; (d) a master whose file cannot be
  read is refused by name, as before; (e) the answers are equal, field for field, to
  today's for a seeded Library of every readiness case (`test_library_facade.py`'s cases,
  run through both).
- **Acceptance:** the read count is constant in the number of works (red today: it grows
  with them); every answer equal to the per-work path's on the seeded cases; the pass time
  at 5,000 works measured and returned with its machine and N.
- **Records owed:** `.prawduct/artifacts/architecture.md` (rule 4's reconcile paragraph:
  the figures), the change record's consumer note (an act's wait).
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/unit/test_library_facade.py arrt/tests/unit/test_reconciliation.py
  arrt/tests/unit/test_feed_publisher.py arrt/tests/integration/test_reconcile_reads.py
  arrt/tests/integration/test_large_corpus.py`; mypy, ruff and black in `arrt/`.
- **Model:** Opus-class, high: a lock held across a household's whole Library, and the
  answer every feed rests on.
- **Waits for:** —.

### Chunk 71: A Get that is gone, and Artworks on a phone

- **Type:** code
- **Visual change:** yes
- **Closes:** T21, T48 (audit-6 17, ux-review #41).
- **Found at HEAD:** a Get whose run is gone gets the server's 404 with its own sentence;
  `arrt/src/arrt/http/static/screens/run.js` rethrows it and the router paints its own
  page, "That Get is not here" (`notFound`, `arrt/src/arrt/http/static/core/router.js`),
  whose second line says the thing "was most likely removed", not what the server said
  (`arrt/tests/browser/test_the_run_view.py`, the gone-run test, asserts the router's
  heading). On a phone, Artworks (`arrt/src/arrt/http/static/screens/collection.js`, its
  toolbar built by `arrt/src/arrt/http/static/core/toolbar.js`) put about 450 px of
  chrome before the first tile when the audit measured it, before wave 1 rebuilt the
  toolbar; it has not been measured since.
- **Owns:** `arrt/src/arrt/http/static/screens/run.js`,
  `arrt/src/arrt/http/static/core/router.js` (`notFound`'s second line only),
  `arrt/src/arrt/http/static/screens/collection.js`,
  `arrt/src/arrt/http/static/core/toolbar.js`, `arrt/src/arrt/http/static/app.css` (the
  phone toolbar's rules only), `arrt/tests/browser/test_the_run_view.py`,
  `arrt/tests/browser/test_the_toolbar.py`, `arrt/tests/browser/test_list_toolbars_agree.py`,
  `arrt/tests/browser/test_keyboard_and_phone.py`,
  `.prawduct/artifacts/information-architecture.md` (the toolbar row on a phone).
- **Must not touch:** the toolbar's order (Select last, on the right: ruling 6 of
  2026-11-19); any control's presence.
- **Deliverables:**
  - A Get that is gone shows the server's own sentence under the heading, as text.
  - **First, the measurement**: the height of chrome above Artworks' first tile at 390 ×
    844, from the walk's own screenshot; returned before any change.
  - On that phone, the first tile's title is on the first screen without scrolling, every
    control still reachable in the order the page rules give.
- **Acceptance:**
  1. The gone-run test reads the server's sentence on the page; red today.
  2. At 390 × 844, the first tile's title's top is inside the viewport on load; red today
     if the measurement says so (if it is already inside, the item is closed as measured
     and only the test is added).
  3. Every list screen's toolbar still agrees (`test_list_toolbars_agree.py`), and the
     keyboard order is unchanged (`test_keyboard_and_phone.py`).
- **Records owed:** `.prawduct/operator-verification.md` (the phone toolbar's look), the IA
  row.
- **Verification ceiling:** `testament run --json=summary --suite browser --` the four
  browser files above and `arrt/tests/browser/test_the_collection.py`; the two browser
  guards.
- **Model:** Opus-class, medium: what a person reads on a phone and on a dead link, under
  ruled page rules.
- **Waits for:** —.

### Chunk 87: Contract 1.3.0 before its tag: three must-refuse rows, and when a refused report is sent again

- **Type:** code
- **Exposed API:** the Player contract (`arrt-contract`, unreleased 1.3.0)
- **Closes:** T52, T53 (the table's half).
- **Found at HEAD:** `contract/fixtures/index.json` marks
  `contract/fixtures/manifest.v2/invalid/generated-at-malformed.json`,
  `contract/fixtures/manifest.v2/invalid/generated-at-not-text.json`,
  `contract/fixtures/manifest.v2/invalid/work-media-content-type-unknown.json` and
  `contract/fixtures/manifest.v2/invalid/staging-repeated.json` `player_must_refuse: true`;
  none of the four is in `contract/released/1.2.0/fixtures/index.json`, whose `_about`
  already says a Player refuses "what it acts on (shape it reads, instants, the semantic
  rules)". `.prawduct/artifacts/player-contract.md` says a Player at 1.3.0 need change
  nothing it reads. `contract/transport.json`'s client heartbeat `not_json` and
  `not_a_client_heartbeat` rows tell a Player "say so once, and send again when the report
  changes", and every report carries a new `reported_at`. The Player's planner measured its
  reader accepting the four, and read in its code that a refused report is resent each cycle.
- **Owns:** `contract/fixtures/index.json` (those four rows only), `contract/transport.json`
  (the client heartbeat's two `400` rows' `player` text only),
  `contract/tests/test_schemas_and_fixtures.py`, `contract/tests/test_transport.py`,
  `arrt/tests/contract/test_transport_table.py`, `.prawduct/artifacts/player-contract.md`
  (§ Releases' 1.3.0 entry, "What a Player does at 1.3.0", and § Transport's sentence on a
  refused report).
- **Must not touch:** `contract/released/`; the schemas (the server's writer stays held to
  all four constraints); the cap.
- **Deliverables:**
  - The three rows `player_must_refuse: false`, by the DECISION, each `refused_because`
    still saying what the writer broke.
  - `staging-repeated`: whether 1.2.0's § Major 2 prose (§ Staging) already obliged a reader
    to refuse it; if it did, the row stays and says so; if it did not, the row stays true
    only as a question put to the owner beside the cap (§ What waits for the owner), and the
    change record says which.
  - A test, parametrised over every `player_must_refuse: true` row, that names the field the
    reader acts on, red for a row whose field no rule of § Major 2 reads (seeded on
    `generated_at`).
  - The two `400` rows say a report is the same when everything but `reported_at` is; the
    server's own double of the table (`arrt/tests/contract/test_transport_table.py`) reads
    the new words.
  - § Releases' 1.3.0 entry: 25 must-refuse manifest fixtures, not 28, and why.
- **Acceptance:** the new test red at `35c12bf0` naming the three rows; `test_released.py`
  green (nothing in `contract/released/` moves); the server's writer still refuses each of the four
  (a test writing each through the feed writer's own check, red if the check is loosened).
- **Records owed:** the Player's coordinator is told the three rows and the row's words
  (86's checklist).
- **Verification ceiling:** `testament run --json=summary --suite contract`; `testament run
  --json=summary --suite curation -- arrt/tests/contract`; the governance suite whole.
- **Model:** Opus-class, medium: what two repositories read as the contract, decided from its
  own rule.
- **Waits for:** —. Met on the Player's side by its plan's Chunk 01 (a refused report held
  until it changes) and Chunk 07 (the fixtures, at the 1.3.0 pin). 82 waits for it.

### Chunk 89: A look's preview fetches have a bound of their own

- **Type:** code
- **Closes:** the bound Chunk 68 removed without replacing (§ Decisions made mid-build).
- **Found at HEAD:** `arrt/src/arrt/library/discovery/look.py` opens up to `INLINED` (6)
  preview fetches for each look, each reading up to the preview ceiling into memory, on an
  executor of the look's own that is shut down without waiting, so a fetch past the look's
  deadline runs on; nothing bounds how many run across looks. Before Chunk 68 the shared
  pool of eight threads bounded concurrent looks; MCP's pool is now sixteen.
- **Owns:** `arrt/src/arrt/library/discovery/look.py`, its tests, and
  `arrt/src/arrt/services/threads.py` only if the bound belongs beside the pools.
- **Deliverables:**
  - Measure first: with N looks in flight against a source whose previews never finish,
    how many preview fetches run at once and how many bytes they may hold, at N of 8 and 16.
  - A process-wide bound on preview fetches in flight, a fetch past its look's deadline
    included, set so that the bytes previews may hold at once are no more than they could
    be before Chunk 68 (state the number and its arithmetic beside the constant).
  - What a look does when the bound is reached is said: which previews it goes without, and
    what the person or agent who asked sees in their place (the look's answer already has a
    form for a preview that did not arrive: use it; add no new sentence unless none fits).
  - The count in flight is journalled where a person diagnosing memory would look.
- **Acceptance:** with sixteen looks in flight and previews that never finish, no more
  preview fetches run at once than the bound, counted with controlled time and no sleeps;
  a look past the bound still answers within its own deadline, with its previews marked as
  not arrived; a fetch that ends frees its place for the next; red on the code at HEAD.
  State what the old waiting bounded and what now wakes a fetch that was turned away.
- **Verification ceiling:** the look's and the pool's test files, `arrt/tests/system`,
  `arrt/tests/unit/test_surface_parity.py`, the governance suite whole if a file is added,
  mypy, ruff and black in `arrt/`.
- **Model:** Opus-class, high: a bound on concurrency, where the last two cost a review round each.
- **Waits for:** 68.

### Chunk 72: What Status does not say yet, and the queue's two couplings

- **Type:** code
- **Visual change:** yes
- **Exposed API:** `/api` (`GET /api/health`'s troubles), MCP (`art_display(action='status')`)
- **Closes:** T28, T30, T31, T32.
- **Found at HEAD:** a wall whose feed would pass `FEED_MAX_BYTES` keeps its old feed and
  stops rolling forward; the publisher says so once, in the journal (`feed.over_bound`,
  `FeedPublisher._over_bound`, `arrt/src/arrt/programming/feeds.py`), and Status says
  nothing. The identity service calls `on_changed` when a work's or an artist's Wikidata
  item changes, and the container wires it to the topic sweep only
  (`arrt/src/arrt/services/container.py`), so the acquisition queue learns of a changed item
  only at its next nudge or after `IDLE_SECONDS`, a day
  (`arrt/src/arrt/library/acquisition/queue.py`). `_DISK_FAULT_WORDS`
  (`arrt/src/arrt/library/acquisition/dezoomify.py`) is keyed by hand against
  `DISK_FAULT_ERRNOS` (`arrt/src/arrt/atomic.py`), so an errno added to the set raises
  `KeyError` where the queue pauses on `OSError`. `failure_instant`
  (`arrt/src/arrt/services/health.py`) works out an old row's instant by inverting the
  queue's `RETRY_AFTER`, outside the queue that owns the schedule.
- **Owns:** `arrt/src/arrt/services/health.py` (the troubles and `failure_instant` only),
  `arrt/src/arrt/programming/feeds.py` (the over-bound record's reader only),
  `arrt/src/arrt/programming/display.py` (its delegation only),
  `arrt/src/arrt/library/acquisition/queue.py` (the instant of a failure),
  `arrt/src/arrt/library/acquisition/dezoomify.py`, `arrt/src/arrt/services/container.py`
  (the identity service's `on_changed` only), `arrt/src/arrt/http/models.py`
  (`TroubleOut`'s list of kinds), `arrt/src/arrt/http/static/screens/health.js` and
  `arrt/src/arrt/http/static/core/status.js` (the new trouble's link and words),
  `arrt/tests/unit/test_failed_fetches.py`, `arrt/tests/unit/test_acquisition_queue.py`,
  `arrt/tests/unit/test_acquisition_dezoomify.py`, `arrt/tests/unit/test_feed_publisher.py`,
  `arrt/tests/integration/test_browser_surface.py` (its health cases),
  `arrt/tests/browser/test_the_health_panel.py`, `arrt/tests/browser/test_the_sidebar.py`.
- **Deliverables:**
  - A wall whose feed is held back for its size is a trouble (a new kind, `feed`, its
    subject the wall), named on Status in the household's words with what to do, linking to
    the wall, counted on the top bar and the System badge; it clears when the wall's feed is
    next published. Since the record is in memory, the first scheduler pass after a start
    (which reconciles) finds it again; the trouble says nothing it cannot know.
  - A changed Wikidata item wakes the acquisition queue.
  - The disk-fault words come from one table the set is derived from, or the words are
    looked up with a sentence for an errno that has none; never a `KeyError`.
  - The instant of a failure recorded before `failed_at` is answered by the queue, which owns
    `RETRY_AFTER`; the health model asks it.
- **Acceptance:**
  1. A theme grown past the bound on a wall (`FEED_MAX_BYTES` lowered, as 2b's Chunk 60
     tested the dialog): `GET /api/health` and `art_display(action='status')` carry the
     trouble, and Status shows it with its link; red today.
  2. Setting a work's item through the identity service wakes a sleeping queue within one
     pass; red today (the queue sleeps its day).
  3. With `DISK_FAULT_ERRNOS` given a third errno in the test, a tile fetch failing with it
     pauses the queue with a sentence; red today with `KeyError`.
  4. `failure_instant`'s cases give the same instants from the queue's function; a test that
     the health module no longer imports `RETRY_AFTER`, red today.
- **Rewritten assertions:** none expected; any test pinning the troubles' kinds whole lists
  the new one, named.
- **Records owed:** `.prawduct/artifacts/observability-strategy.md` § The one health model
  (the new trouble); `.prawduct/artifacts/api-contract.md` (the health row's kinds);
  `.prawduct/operator-verification.md` (the trouble's look).
- **Verification ceiling:** the curation files above and `arrt/tests/unit/test_identity.py`;
  `arrt/tests/unit/test_surface_parity.py`; **the whole browser suite** (it changes
  `arrt/src/arrt/http/models.py`, lesson 9); the two browser guards; mypy, ruff and black.
- **Model:** Opus-class, medium: a new fault a household is told of, and two couplings whose
  failure is a stalled queue.
- **Waits for:** 67 (`arrt/src/arrt/services/health.py`), 70
  (`arrt/src/arrt/programming/feeds.py`).

### Chunk 88: A Player whose reports are refused says so

- **Type:** code
- **Visual change:** yes
- **Exposed API:** `/api` (`GET /api/clients`, `GET /api/health`), MCP (`art_players`, `art_display(action='status')`)
- **Closes:** T54.
- **Found at HEAD:** `ClientService.record_heartbeat` (`arrt/src/arrt/programming/clients.py`)
  refuses a report it cannot read with `ServiceError` and records nothing; the route
  (`arrt/src/arrt/http/player.py`) writes no journal line of its own, and uvicorn's access
  line for the `400` is the only trace. `player_state` (`arrt/src/arrt/programming/player_state.py`)
  has `report_unreadable` ("Report unreadable", a trouble) for a report it holds and cannot
  read, so a Player whose every report is refused reads `awaiting_report`, a setup step that
  is never a trouble, or `not_heard_from`.
- **Owns:** `arrt/src/arrt/programming/clients.py` (the refusal remembered and read into the
  Player's reading only), `arrt/src/arrt/http/player.py` (the route's journal line only),
  `arrt/tests/unit/test_clients.py`, `arrt/tests/unit/test_player_state.py`,
  `arrt/tests/contract/test_client_surface.py`, `arrt/tests/browser/test_the_clients.py`.
- **Deliverables:**
  - The server remembers, per Player, the last refused report's instant and sentence (in
    memory: a refused report is still "nothing recorded" as the table says), cleared by the
    next accepted one; the Player then reads `report_unreadable`, a trouble, with the
    sentence beside it on Players and Status, on both surfaces.
  - The first refusal of a run of identical ones writes one journal line with an `event`
    field; a repeat writes none.
- **Acceptance:** a Player whose first report is refused reads "Report unreadable" with the
  server's sentence on `GET /api/clients`, `GET /api/health` and `art_players(action='clients')`,
  and counts as a trouble; red today (it reads as waiting for its first report). Ten identical
  refusals write one journal line; red if each writes one. An accepted report clears it.
- **Records owed:** `.prawduct/artifacts/observability-strategy.md` (the event, the state's
  new cause); `.prawduct/operator-verification.md` (the Players row's look); `.prawduct/artifacts/clients.md` if it states the states' causes.
- **Verification ceiling:** the curation files above and
  `arrt/tests/integration/test_client_tools.py`, `arrt/tests/unit/test_surface_parity.py`;
  the browser file above; the two browser guards; mypy, ruff and black.
- **Model:** Opus-class, medium: what a household is told about a Player that is talking and
  not being heard.
- **Waits for:** 67 (`clients.py`), 87 (the row's words it answers to). On the Player's side
  its plan's Chunk 01 makes the Player stop resending; this chunk is what Status says either
  way.

### Chunk 73: #313's remainder: Searches, Hit rate, Median latency

- **Type:** code
- **Visual change:** yes
- **Exposed API:** `/api` (`GET /api/sources`), MCP (`art_discovery(action='source_plugins')`)
- **Closes:** T13 (#313's last acceptance box and the requirement it asks to be written).
- **Found at HEAD:** the search record keeps, per work and source, `asked_at`, `answered_at`
  and `images` (`SourceSearch`, `arrt/src/arrt/persistence/discovery_records.py`), and
  `SearchTally` counts `searched`, `answered`, `unasked` and `owed` over a source's newest
  `SEARCHES_COUNTED` (100) works (`search_tallies`,
  `arrt/src/arrt/persistence/sqlite_discovery.py`). Nothing computes a latency, nothing
  divides `answered` by whether it found an image, and `SourceSearch.images` is read by
  nothing. `SourcePluginOut` (`arrt/src/arrt/http/models.py`) carries the counts; Status's
  sources table (`SOURCE_COLUMNS`, `arrt/src/arrt/http/static/screens/health.js`) has no
  column for them, and the counts reach Status only in the source's sentence.
- **Owns:** `arrt/src/arrt/persistence/discovery_records.py` (`SearchTally`),
  `arrt/src/arrt/persistence/sqlite_discovery.py` and `arrt/src/arrt/persistence/discovery.py`
  (`search_tallies`), `arrt/src/arrt/services/health.py` (`SourceHealth`'s search fields
  only), `arrt/src/arrt/http/models.py` (`SourcePluginOut`), `arrt/src/arrt/http/api.py` and
  `arrt/src/arrt/mcp/bindings.py` (the sources answers only),
  `arrt/src/arrt/http/static/screens/health.js` (the sources table),
  `arrt/src/arrt/http/static/app.css` (`.source-table`'s widths),
  `arrt/tests/unit/test_discovery_store.py`,
  `arrt/tests/integration/test_source_plugins_surface.py`,
  `arrt/tests/unit/test_surface_parity.py` (the new fields' pairing),
  `arrt/tests/browser/test_the_status_sources_table.py`, `arrt/tests/browser/payloads.py`
  (builders for the new fields, in its own pattern).
- **Deliverables:**
  - The tally gains, over the same works: those answered with an image, and the median
    latency of those answered, as the DECISION defines them.
  - `GET /api/sources` and `source_plugins` carry them, in the same names.
  - The sources table gains *Searches*, *Hit rate* and *Median latency*, each with its
    place in the narrowing order (`drops`) and its width, never colour alone; a source with
    nothing answered reads "—".
- **Acceptance:**
  1. A seeded record (three works answered with images, one with none, one owed; latencies
     2, 4 and 10 s): the route reads 5 searched, a hit rate of 3 of 4, and a median of 4 s,
     and the table shows them; red today.
  2. A restart (the store reopened) gives the same figures (#313's "survive a restart").
  3. At the narrowest width the table keeps Source, State, Offered and Chosen
     (`test_the_status_sources_table.py`'s width test, extended).
  4. Parity: `source_plugins` answers the new fields as the route does; red when one is
     left out.
- **Records owed:** `.prawduct/artifacts/data-model.md` (the record's columns read, nothing
  persisted changed; the three columns' definitions, which #313 asks to be written);
  `.prawduct/artifacts/information-architecture.md` (Status's sources table);
  `.prawduct/operator-verification.md` (the table's look); `.prawduct/artifacts/api-contract.md`.
- **Verification ceiling:** the curation files above and
  `arrt/tests/contract/test_mcp_surface.py`; **the whole browser suite** (models.py); the
  two browser guards; mypy, ruff and black.
- **Model:** Opus-class, high: definitions a household reads as a museum's worth, and a
  table that must stay legible on a phone.
- **Waits for:** 67 (`api.py`, `bindings.py`, `health.py`), 71 (`app.css`), 72 (`health.py`,
  `health.js`, `models.py`).

### Chunk 74: The server's sentences: counts said one way, museums by their declared names

- **Type:** code
- **Closes:** T27 (R-5), T16.
- **Found at HEAD:** 20 lines in `arrt/src/arrt` outside `arrt/src/arrt/http/static/` choose a word by `== 1 else`
  (in `arrt/src/arrt/services/health.py` 9, `arrt/src/arrt/library/sources/loading.py` 3,
  `arrt/src/arrt/library/discovery/pool.py` 2, `arrt/src/arrt/ask/agent.py` 2, and one each in
  `arrt/src/arrt/library/sources/iiif.py`, `arrt/src/arrt/observations.py`,
  `arrt/src/arrt/persistence/file.py` and `arrt/src/arrt/counting.py` itself), and
  `health.py` groups digits by hand where `counted` does not, so a count of thousands is
  written "2,000 works" and "2000 works". `museum_name(` is called without the plugin's
  declared name at 14 sites in five modules: `arrt/src/arrt/library/sources/loading.py` (8),
  `arrt/src/arrt/library/discovery/pool.py` (3), `arrt/src/arrt/library/acquisition/service.py`,
  `arrt/src/arrt/library/discovery/phase_two.py` and `arrt/src/arrt/library/services/runner.py`
  (one each), so a museum that declares its own name is named by its module's in those
  sentences.
- **Owns:** `arrt/src/arrt/counting.py`, and the sentences only in each module named above,
  `arrt/tests/unit/test_counting.py`, a new guard:
  new `arrt/tests/unit/test_one_count_writer.py`; and the tests that pin those sentences
  (found by grep, each listed).
- **Deliverables:**
  - `counted` groups digits from a thousand; every count in a server sentence goes through
    `arrt.counting`.
  - A guard over every server module refuses a word chosen by a test of one, as
    `test_one_cost_formatter.py` refuses a hand-formatted dollar, with its limits stated as
    that guard states its own.
  - Every sentence that names a museum names it as the plugin declares it.
- **Acceptance:** the guard red at `35c12bf0` on each of the 20 lines and on one planted in a
  module it had not seen; `counted(2000, "work")` reads "2,000 works", red today; a plugin
  declaring "The Met" under the module name `met` is named "The Met" in a could-not-be-asked
  sentence and a pool sentence, red today.
- **Rewritten assertions:** each test pinning a sentence whose count or museum changes, named
  with the old text.
- **Verification ceiling:** `testament run --json=summary --suite curation --` the tests
  pinning those sentences, `arrt/tests/unit/test_counting.py`,
  the new `arrt/tests/unit/test_one_count_writer.py`, `arrt/tests/unit/test_refusal_sentences.py`;
  mypy, ruff and black.
- **Model:** Sonnet-class, high: named sites, one function, one guard in an existing pattern.
- **Waits for:** 68 (`arrt/src/arrt/ask/agent.py`), 69 (`arrt/src/arrt/library/sources/loading.py`,
  `arrt/src/arrt/library/services/runner.py`), 73 (`arrt/src/arrt/services/health.py`).

### Chunk 75: One mat act, the six read twins, the write routes inventoried

- **Type:** code
- **Exposed API:** MCP (additive), `/api` (unchanged in shape)
- **Closes:** T3 (audit-2 S7's second half), T12, T25's half for the new twins.
- **Found at HEAD:** `set_work_mat` (`arrt/src/arrt/http/api.py`) validates "a preset or
  derive, not both" in the handler; `_set_mat_color` (`arrt/src/arrt/mcp/bindings.py`) takes
  `hex_rgb`, `preset`, `preset="derived"` or nothing (the paid `choose_mat`) and validates by
  its own rule; both call `PreparationService`'s four methods
  (`arrt/src/arrt/library/acquisition/preparation.py`). The route inventory
  (`arrt/tests/unit/test_surface_parity.py`, `READS_OWED_TO_MCP`) owes six read twins:
  `/api/artists`, `/api/artists/{artist_id}`, `/api/works/{artwork_id}/mat`,
  `/api/works/{artwork_id}/placements`, `/api/sources/yields`, `/api/budget`; it reads GET
  routes only, and `api.py` declares 60 write routes no inventory reads. The tools' sizes
  recorded at 2b's Chunk 53: `art_discovery` 2,046 bytes and `art_catalogue` 1,999 of 2,048.
- **Owns:** `arrt/src/arrt/library/acquisition/preparation.py` (the one act),
  `arrt/src/arrt/http/api.py` (`set_work_mat` only), `arrt/src/arrt/mcp/tools.py`,
  `arrt/src/arrt/mcp/bindings.py` (`_set_mat_color` and the new actions),
  `arrt/tests/unit/test_preparation.py`, `arrt/tests/integration/test_work_mat.py`,
  `arrt/tests/unit/test_surface_parity.py` (the inventory),
  `arrt/tests/contract/test_mcp_surface.py`, `.prawduct/artifacts/api-contract.md` (the MCP
  rows only).
- **Must not touch:** `arrt/tests/contract/test_mcp_break.py` and
  `arrt/tests/fixtures/mcp-surface-before-the-break.json` (byte-unchanged).
- **Deliverables:**
  - **First, the bytes**: every tool's description size, returned before any code, with
    where each new action is to go.
  - The one mat act (the DECISION); each binding maps its arguments to it and does no
    validating of its own.
  - An MCP twin for each of the six owed reads, in their routes' field names, each paired by
    record in the parity test.
  - The inventory reads every route of every method: each write route is paired with an MCP
    action, named not for an agent with its reason, or owed with its reason. An owed write
    twin is built here when it is one binding over an existing service method and its tool
    has room; any other stays in the owed map with why, and the change record lists them.
- **Acceptance:**
  1. The same mat refusals, word for word, from both surfaces for each invalid combination;
     the paid path unreachable from HTTP; red for a binding that validates (a test reading
     the two bindings for a raise of their own).
  2. Each new twin answers as its route on a seeded Library (parity), red when a field is
     dropped.
  3. The inventory red at `35c12bf0` naming each unpaired write route; red again when a
     paired route's action is renamed.
  4. Every tool still fits 2,048 bytes; the break's recording unchanged.
- **Records owed:** `.prawduct/artifacts/api-contract.md` (its own rows; the rest is 85's);
  the change record's consumer note for an agent (what MCP gained).
- **Verification ceiling:** the curation files above,
  `arrt/tests/contract/test_mcp_break.py`, `arrt/tests/contract/test_mcp_scenarios.py`;
  mypy, ruff and black.
- **Model:** Opus-class, high: where each act lives for an agent, under a byte budget, and the
  surface's parity norm.
- **Waits for:** 67 and 73 (`api.py`, `bindings.py`, `test_surface_parity.py`).

### Chunk 76: Programming takes its clock and ids, and one owner says what is kept off

- **Type:** code
- **Closes:** T17, T6 (#307's part left).
- **Found at HEAD:** `arrt/src/arrt/programming/` reads `datetime.now(UTC)` at 23 sites
  (`themes.py` 7, `scenes.py` 6, `feeds.py` 2, `reports.py` 2, `clients.py` 2, `walls.py` 2,
  `access.py` 1, `manifest/v2.py` 1) and mints `uuid.uuid4()` at 9. "Is this work kept off?"
  is answered by scanning `list_exclusions()` at ten sites: six in
  `arrt/src/arrt/programming/themes.py`, three in `arrt/src/arrt/programming/feeds.py`, one
  in `arrt/src/arrt/programming/scenes.py`.
- **Owns:** `arrt/src/arrt/programming/themes.py`, `scenes.py`, `feeds.py`, `reports.py`,
  `clients.py`, `walls.py`, `access.py`, `display.py`, `lookups.py`,
  `arrt/src/arrt/programming/manifest/v2.py` (their clocks, ids and the kept-off read only),
  `arrt/src/arrt/services/container.py` (Programming's construction only), and a new test
  (new `arrt/tests/unit/test_programming_clocks_and_ids.py`).
- **Deliverables:**
  - Each collaborator takes a clock and an id source, defaulting to the machine's; an act
    reads its clock once and passes the instant on.
  - One owner (`Lookups`, `arrt/src/arrt/programming/lookups.py`) answers what is kept off,
    read once per act; every site asks it.
- **Acceptance:** a fixed clock and a counting id source given to each collaborator are what
  every record it writes carries (a theme, a scene, a Player, a label output, a display, a
  wall, a token's instant, a feed's `generated_at`), red today, one case per collaborator;
  a test that `list_exclusions(` is called only by the owner, red today naming the ten.
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/unit/test_programming_clocks_and_ids.py arrt/tests/unit/test_scenes.py
  arrt/tests/unit/test_feed_publisher.py arrt/tests/unit/test_clients.py
  arrt/tests/unit/test_display_facade.py arrt/tests/unit/test_major_2_feed.py`; mypy, ruff and
  black.
- **Model:** Sonnet-class, high: named sites, the pattern 2b's Chunk 43 set, one owner.
- **Waits for:** 67 and 88 (the Programming files, `clients.py`), 69 (`manifest/v2.py`), 70
  and 72 (`feeds.py`, `container.py`). A feed's `generated_at` comes from the injected clock
  with the same shape, so nothing a Player receives changes.

### Chunk 77: The shared fixtures' clock and ids, and reports only for walls a Player shows

- **Type:** code
- **Closes:** T14 (#438's items 1 to 4, through the fixtures), T23.
- **Found at HEAD:** `Services.bind` (`arrt/src/arrt/services/container.py`) takes a look's
  clock and no other; the `services` fixture (`arrt/tests/conftest.py`) passes none, so
  `AcquisitionQueue`, `CatalogueService`, `DiscoveryService` and the rest read the machine's
  through their defaults (`machine_now`, `new_id`,
  `arrt/src/arrt/library/services/catalogue.py`). 2b's full `--no-cache` run measured about
  half the suite uncacheable, a clock read the largest single cause, and found that
  only the shared fixtures passing a clock would change it. 2b's Chunk 63 measured a probe
  over the report writers and left no guard that a test writes a report only for a wall a
  Player shows.
- **Owns:** `arrt/tests/conftest.py`, `arrt/src/arrt/services/container.py`
  (`Services.bind`'s clock and id source only), `arrt/tests/fakes.py`, and the test files
  that read the machine's clock against a service's (each listed).
- **Deliverables:**
  - `Services.bind` takes one clock and one id source and gives them to every service it
    builds; a deployment passes neither and gets the machine's.
  - The `services` fixture passes the DECISION's clock and ids.
  - A guard (a fixture-level probe over the report writers, with its exemptions named) that
    fails a test writing a wall's report for a wall no Player shows.
- **Implicit guarantees** (the DECISION), each tested: instants strictly increasing across
  threads within a test; ids unique across a test's services and the files they name.
- **Acceptance:** testament's cache advice from a full `--no-cache` run before and after, the
  clock cause's count by suite, returned as measured (no target number is promised; the
  figure is the result); a test that a service built by the fixture reads no machine clock
  (a planted `datetime.now` in one service turns it red); the report guard red when one
  fixture's Player is removed.
- **Rewritten assertions:** each test that compared a service's instant with its own
  `datetime.now()`, listed.
- **Verification ceiling:** the curation suite's areas `unit` and `integration` on the pool,
  by area (`--area`), as the one exception the coordinator grants because the shared
  fixture is under every curation test; mypy, ruff and black.
- **Model:** Opus-class, medium: a change under every test, whose fakes must keep what the
  real clock guaranteed.
- **Waits for:** 72 and 76 (`container.py`).

### Chunk 78: `arrt/src/arrt/http/api.py` by resource

- **Type:** refactor
- **Closes:** T2 (draft 38's mechanical half; audit-2 S6's `api.py`).
- **Found at HEAD:** `arrt/src/arrt/http/api.py` is 3,282 lines: one `APIRouter` with 53 GET
  and 60 write routes and every handler's helpers. Three tests import names from it
  (`_health`, `LOOK_AGAIN`, `list_works`).
- **Owns:** `arrt/src/arrt/http/api.py` (left as the router's assembly and re-exports),
  new `arrt/src/arrt/http/routes/` (one module per resource), `arrt/src/arrt/app.py` (the
  include only), a new test (new `arrt/tests/unit/test_route_table.py`).
- **Deliverables:** one module per resource; every route's path, method, name, response
  model and registration order unchanged; the three imported names still importable from
  `arrt.http.api`.
- **Acceptance:** `app.openapi()` and the ordered route table (method, path, endpoint name)
  equal to a recording taken at the chunk's base, held by the new test (red when one route
  moves ahead of another); every test passes unchanged.
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/unit/test_route_table.py arrt/tests/integration arrt/tests/contract`; the
  governance suite whole (new tracked files); mypy, ruff and black. The browser suite is the
  integrator's on the merged head.
- **Model:** Sonnet-class, high: a move held by a byte-for-byte comparison.
- **Waits for:** 67, 73, 75 (`api.py`).

### Chunk 79: The browser tests' instants, and the large catalogue

- **Type:** code
- **Closes:** T19, T18.
- **Found at HEAD:** 16 files under `arrt/tests/browser/` read `datetime.now` or
  `time.time()` to seed what they serve (11 sites in `test_walls_last_and_next.py`, the
  file of #442's flake); the browser tests run against a real server process.
  `build_large_catalogue` (`arrt/tests/conftest.py`) seeds 4,000 works one by one for
  `arrt/tests/integration/test_large_corpus.py` and
  `arrt/tests/browser/test_the_collection.py`, and the prototype-scale test took 12.5 s
  locally at 2b.
- **Owns:** the seeding lines of the 16 browser files, `arrt/tests/browser/conftest.py` (its
  one seed), `arrt/tests/conftest.py` (`build_large_catalogue` only).
- **Deliverables:**
  - **First, the measurement**: testament's cache cause for the browser suite's tests. If
    the server process makes every browser test uncacheable whatever its instants, the
    seeds change only where an assertion reads a date or an age (named, each), and the rest
    is left and said so.
  - `build_large_catalogue` seeds the same works, draw for draw, faster; its time before and
    after.
- **Acceptance:** the corpus's works identical before and after (a digest of titles, artists
  and facets for the default seed); its time returned; each changed browser test passes on
  the pool and is red when its fixed instant is moved across the boundary its assertion
  reads.
- **Verification ceiling:** the browser files it edits and `arrt/tests/browser/test_the_collection.py`
  on the pool; `arrt/tests/integration/test_large_corpus.py`; the two browser guards.
- **Model:** Sonnet-class, high: named sites, a measurement that decides the scope.
- **Waits for:** 77 (`arrt/tests/conftest.py`), and 67, 71, 72, 73 (the browser files they own).

### Chunk 80: The comments sweep (draft 46)

- **Type:** cleanup
- **Closes:** T7, T8, T9.
- **Found at HEAD:** module docstrings under `arrt/src/arrt` hold 35 dates in 29 files and 4
  issue numbers in 4 files; "display plane" or "curation plane" is in 24 lines in 14 files of
  `arrt/src/arrt` (the static files included); comments in `arrt/tests` cite a chunk by
  number alone (for example `arrt/tests/unit/test_display_facade.py`'s "chunk 21's base").
- **Owns:** comments and docstrings only, in any file under `arrt/src/arrt` and `arrt/tests`.
- **Deliverables:** a dated correction history leaves a docstring (what the code does now
  stays); **a date that dates a measurement or a ruling stays**, since it is the claim's
  evidence (`.claude/rules/learnings/core.md`); "display plane" and "curation plane" become
  the Player and the server except where they quote a norm's text; a chunk cited by number
  names its plan, or says the reason instead.
- **Acceptance:** no executable line changes (`git diff` read through `ast`: every module's
  AST without docstrings equal before and after); each kept date listed with what it dates;
  `arrt/tests/unit/test_refusal_sentences.py` and `arrt/tests/unit/test_client_vocabulary.py`
  green.
- **Verification ceiling:** the curation and browser guards that read comments or strings
  (`test_refusal_sentences.py`, `test_client_vocabulary.py`, `test_browser_reads_retry.py`);
  the governance suite whole; ruff and black.
- **Model:** Sonnet-class, high: a rule applied per instance, checked by an AST comparison.
- **Waits for:** 67 to 79.

### Chunk 81: Four norm texts, and the delegate-verification count

- **Type:** doc-only (one test)
- **Closes:** T36, T37, as ruled.
- **Found at HEAD:** `.prawduct/artifacts/project-preferences.md` says each project selects
  `E,F,I,UP,B,T20,TRY` where `arrt/pyproject.toml` selects `ALL`, and that nothing but
  `arrt/src/arrt/app.py` and `arrt/src/arrt/mcp/server.py` is a coroutine where `arrt/src/arrt/ask/agent.py`,
  `arrt/src/arrt/http/ask.py`, `arrt/src/arrt/http/player.py` and
  `arrt/src/arrt/http/hosts.py` are too; `.prawduct/artifacts/data-model.md` § Direction says
  the one device fact the server keeps is a wall's last heartbeat, where the catalogue holds
  `reported_screens`, `displays` and `showings`; `.prawduct/artifacts/architecture.md`'s
  Direction norm 1 is stated unamended beside the Player's narrowed copy. The same
  preferences file says a change to `contract/` "runs all five" and a full run "all six".
  `arrt/tests/unit/test_catalogue_store.py`'s `_FORBIDDEN_COLUMNS` holds one column.
- **Owns:** `.prawduct/artifacts/project-preferences.md`, `.prawduct/artifacts/data-model.md`
  § Direction, `.prawduct/artifacts/architecture.md` § Direction (norm 1 only),
  `arrt/tests/unit/test_catalogue_store.py` (the forbidden-columns check only).
- **Deliverables:** for each question answered, the norm amended to the ruling with a dated
  note citing it, and for Q1(c), the forbidden-columns check extended to hold it, shown red
  on a planted per-device column. A question not answered is left as it is, and 85 lists it.
- **Acceptance:** `tests/preferences/test_norm_index.py` and
  `tests/preferences/test_citations_resolve.py` green; the extended check red on its planted
  column; `prawduct-hook verify-records` clean.
- **Verification ceiling:** `testament run --json=summary --suite governance`;
  `testament run --json=summary --suite curation -- arrt/tests/unit/test_catalogue_store.py`.
- **Model:** Sonnet-class, high: the owner writes the decision; the chunk writes it down.
- **Waits for:** the owner: Q1, and the delegate-verification count. If neither is answered
  when 85 is dispatched, this chunk moves to `dropped:` with that reason.

### Chunk 82: Contract 1.3.0 frozen beside the others

- **Type:** code
- **Closes:** T38: the 2b record's "cut `contract-v1.3.0` on the merge commit and freeze it in
  the next plan's first commit", which could not be first because the tag is not cut.
- **Found at HEAD:** `contract/pyproject.toml` says 1.3.0; `contract/released/` holds 1.0.0,
  1.1.0 and 1.2.0; no `contract-v1.3.0` tag exists, here or on the remote; the cap of 32
  outputs (`MAX_OUTPUTS_PER_REPORT`, `contract/src/arrt_contract/__init__.py`) is the second
  answer 1.3.0 does not add, put to the owner; `contract/tools/freeze_release.py` writes a
  frozen copy from a tag.
- **Owns:** new `contract/released/1.3.0/`, `.prawduct/artifacts/player-contract.md` (§
  Releases' 1.3.0 entry, and § Versioning if the owner ratifies the cap as an exception).
- **Deliverables:** **if the owner ratifies the cap:** § Versioning records the second
  bounded exception, the operator cuts the tag, and this chunk freezes 1.3.0 with
  `contract/tools/freeze_release.py` and runs `release_tags` by hand (`git fetch origin
  --tags && cd contract && uv run pytest -m release_tags`). **If the owner has the cap wait
  for a major:** this chunk is rewritten then, since 1.3.0 would lose a rule and its two
  fixtures before it is cut and the server's refusal would need a decision of its own; it
  is not designed here.
- **Acceptance (the ratified case):** `contract/tests` green with the frozen copy;
  `release_tags` green by hand on this machine; the package's guard demands the copy (red
  with it removed).
- **Verification ceiling:** `testament run --json=summary --suite contract`; the governance
  suite whole (new tracked files); `release_tags` by hand.
- **Model:** Sonnet-class, high: a tool that exists, run once on a tag.
- **Waits for:** 87 (1.3.0's last changes before the tag); the owner: the cap, and
  `staging-repeated` if 87 puts it; then the operator: the `contract-v1.3.0` tag (the
  2026-11-13 ruling: the owner approves a contract tag). The Player plan's Chunk 07 moves its
  pin once the tag exists.

### Chunk 83: "Your library" in what a person reads

- **Type:** code
- **Closes:** T20, as ruled.
- **Found at HEAD:** "your library" occurs 31 times in 13 files under
  `arrt/src/arrt/http/static/` (some in comments) and in five server sentences
  (`arrt/src/arrt/ask/agent.py`, `arrt/src/arrt/library/services/registry_search.py`);
  `arrt/tests/unit/test_client_vocabulary.py` reads the client's words.
- **Owns:** those strings, `arrt/tests/unit/test_client_vocabulary.py` (the rule as ruled),
  the browser and curation tests pinning them (by grep, each listed).
- **Deliverables:** the strings as the owner rules, and the vocabulary guard holding the
  ruled form, shown red on one planted string of the old form.
- **Verification ceiling:** `arrt/tests/unit/test_client_vocabulary.py`,
  `arrt/tests/unit/test_refusal_sentences.py`, and the browser files pinning the strings, on
  the pool.
- **Model:** Sonnet-class, high: named strings, one guard.
- **Waits for:** the owner: whether the phrase takes the Library's capital.

### Chunk 84: What a household sets, and where (Q3)

- **Type:** doc-only until ruled
- **Closes:** T39, as ruled.
- **Found at HEAD:** `contract/schemas/manifest.v2.schema.json` carries label facts, viewing
  distance, text scale, fade and overlay settings; the server sends only the mat's mode
  (`_feed_settings`, `arrt/src/arrt/programming/feeds.py`); a label panel's viewing distance
  is in the Player's own environment, in inches.
- **Deliverables:** written when the owner answers. If the answer is the recommendation's
  first half (a wall's label facts and text size; a label output's viewing distance), it is a
  contract minor and a Player change and goes to a plan of its own, as a persisted format
  designed from its consumers' questions; this chunk then records the ruling and the IA's
  "coming" marks. If the answer is to mark them coming only, this chunk is that edit to
  `.prawduct/artifacts/information-architecture.md`.
- **Model:** decided with its scope.
- **Waits for:** the owner: Q3.

### Chunk 85: Records, and the change record

- **Type:** doc-only
- **Closes:** every chunk's *Records owed*, worked as a numbered checklist; T47, T50, T51.
- **Owns:** new `.prawduct/changes/audit-wave-3.md`,
  `.prawduct/artifacts/observability-strategy.md`, `.prawduct/artifacts/data-model.md` (not §
  Direction), `.prawduct/artifacts/api-contract.md` (the HTTP sections, and every line
  reference into `arrt/src/arrt/http/api.py` re-pointed after 78),
  `.prawduct/artifacts/architecture.md` (not § Direction),
  `.prawduct/artifacts/security-model.md`, `.prawduct/artifacts/information-architecture.md`,
  `.prawduct/artifacts/nonfunctional-requirements.md`, `docs/testing.md`,
  `.prawduct/operator-verification.md`.
- **Deliverables:** each sentence cites the file it describes and was read against the code
  before it was written (a delegate's report is evidence about intent); the change record
  names each chunk's findings, `closes:` derived from the plan and checked on GitHub (#313
  if 73 met every box; #438 only if its items are all met; #307 if 76 met it), the consumer
  notes (an agent's new actions; a household's new trouble and columns; a reader of `/api`:
  unchanged), and what is left open with its reason, the owner's questions unanswered by
  then included. `security-model.md` stops saying the CI OpenRouter key's ceiling is
  unknown (CI holds the pool's key alone, `tests/test_ci_makes_no_paid_call.py`) and records
  the ruling that every runner of the pool may run this repository's tests, with what a
  runner can see and do. The sighting-hosts page is filed as an issue if none holds it.
- **Acceptance:** `prawduct-hook verify-records` 0 findings; `prawduct-hook
  check-change-log-entry` valid; `tests/preferences/test_citations_resolve.py`,
  `tests/preferences/test_artifact_manifest.py` and `tests/preferences/test_norm_index.py`
  green; every checklist item ticked or named as not done with its reason.
- **Verification ceiling:** `testament run --json=summary --suite governance`.
- **Model:** Opus-class, medium: every sentence a reader of the records takes as true,
  checked against the code.
- **Waits for:** 67 to 80, 87 and 88, and each of 81 to 84 done or moved to `dropped:`.

### Chunk 86: Integration and the boundary review (the coordinator's)

- **Type:** cumulative-final
- **Owner:** the coordinator, or one integrator it names; no build delegate.
- **Deliverables:** each delegate branch merged with its scoped merge commit, trailers counted
  first; the governance suite whole after every merge that adds a tracked file; the whole
  browser suite after each merge that changed `arrt/src/arrt/http/static/` or
  `arrt/src/arrt/http/models.py`; the draft pull request opened once group A is in, so later
  pushes run under the required check.
- **Done when:**
  1. On the merged head, the six suites pass (`testament run --json`, the `image` suite and
     the real-Player suite among them).
  2. **CI's own guard, run as CI runs it:** the workflow's pool step,
     `python3 .github/scripts/pool_or_fallback.py pool --out "$OUT" -- testament run
     --json=summary --junit-xml "$OUT/all.xml" --no-fallback`, then
     `python3 .github/scripts/assert_tests_ran.py "$OUT/all.xml" --suites-from .testament.toml
     --decision "$OUT/decision.json"` over its report, both green.
  3. **The fallback's three steps in a clone without tags** (`git clone --no-tags` of the
     head): `pool_or_fallback.py fallback --out "$OUT" --suite governance`, `--suite curation`
     and `--suite contract`, each exit 0, and `assert_tests_ran.py` over what they wrote.
  4. The coordinator has read each delegate's fail-first evidence, and 68's, 70's and 75's
     measurements before their code.
  5. The Critic's cumulative review finds nothing blocking.
- **The operator's checklist, after the merge into `develop`:**
  1. Close by hand what the change record's `closes:` lists; `git-tidy --after-merge`.
  2. `test_rerun_command` in `.prawduct/project-state.yaml` (#438's "Also"), the coordinator's.
  3. #318's measurement: a Retry of the real queue, then Activity › Queue's groups read.
  4. The paid OpenRouter probe by hand when #150 is to be settled
     (`cd arrt && uv run pytest tests/live -m live_api -n0`).
  5. Tell the Player's coordinator what 87 changed in the unreleased 1.3.0 (three index rows,
     the `400` rows' words, and what became of `staging-repeated`), for its Chunks 01 and 07;
     and, if 82 has run, that `contract-v1.3.0` exists.
  6. The operator-verification entries 71, 72 and 73 owe.
  7. Raise with both coordinators the governance code copied between this repository and Arrt
     Player (ledger rows 11 and 128).

## What the code already settles

Each was checked at `35c12bf0`; none becomes a chunk.

- **#307's first and third parts.** `DisplayService._withdraw`, which re-implemented the
  reconcile's patch, no longer exists: `grep -rn _withdraw arrt/src` finds nothing, and
  `FeedPublisher.reconcile` (`arrt/src/arrt/programming/feeds.py`) is the one path. "Is this
  a theme a curator made" is `theme.hidden`, read inside `arrt/src/arrt/programming/themes.py`
  alone. The exclusions' scan is left (76).
- **Comments carrying 2b's chunk numbers or review ids.** None in `arrt/src`: the nine
  `Chunk NN` mentions there each name an earlier plan file beside the number. The bare ones
  left are in `arrt/tests` (80).
- **The queue's own museum words** (`queue.py` ~1046 in the landing log): the queue's cause
  sentence now asks `HealthService.museum_of`; no `museum_name(` call is left in
  `arrt/src/arrt/library/acquisition/queue.py`.
- **`WallView`'s two reads** (the landing log, pass 22): the walls answers read once
  (`HealthService.observe_walls`, 2b's boundary fixes); what is left of that shape is 67's.
- **The cost words' two ways under a hundredth of a cent** (T24): 2b's record calls both
  true and leaves them so; nothing to build.
- **Alternating failures never give up** (T34): 2b's record accepts it as the cost of its
  schedule fix.
- **The CI OpenRouter key's ceiling** (ledger L26): CI holds no model key
  (`tests/test_ci_makes_no_paid_call.py`; `gh secret list` names `TESTAMENT_KEY` alone); only
  the record still says otherwise (T50, 85).
- **Q4's runners** (ledger row 121's runner half): ruled 2026-11-20, "All runners are fine";
  only the record is owed (T51, 85).

## What the records say that the code does not

Found while planning, each for 85 or the coordinator:

- `.prawduct/artifacts/security-model.md` says the CI OpenRouter key's ceiling "stays
  recorded as unknown", a few lines after saying CI holds the pool's key and no other.
- 2b's change record says `contract-v1.3.0` is frozen "in the next plan's first commit"; no
  tag is cut, so 82 waits.
- 2b's counts drifted from the code: module docstrings hold 35 dates (the record said 33) in
  29 files; "display plane" and "curation plane" are in 24 lines in 14 files (about 28 in 15);
  "your library" is 31 occurrences in 13 client files (about 28); `museum_name(` without the
  declared name is 14 sites in five modules (six); Programming reads the clock directly at 23
  sites and mints 9 ids (25 clock reads).
- `.prawduct/artifacts/project-preferences.md` says "runs all five" in `Delegate verification`
  and "all six" in § Testing (the owner's question, 81).
