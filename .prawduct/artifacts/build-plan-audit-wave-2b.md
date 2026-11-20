---
artifact: build-plan
version: 1
scope: audit-wave-2b
branch: fix/audit-wave-2b
base: develop
working-branches: []
last_validated: null
depends_on:
  - artifact: build-plan-audit-wave-2
  - artifact: architecture
  - artifact: player-contract
  - artifact: api-contract
  - artifact: data-model
  - artifact: information-architecture
  - artifact: source-plugins
  - artifact: security-model
  - artifact: observability-strategy
  - artifact: operational-spec
  - artifact: nonfunctional-requirements
  - artifact: project-preferences
governed_by:
  - artifact: architecture
    dispositions:
      - "rule 1, one-way imports through the facade → conforms: 39's scheduled reconcile is a Programming job handed to the Library's scheduler, never imported by it (test_seam_imports holds it); 32 and 33 stay inside the Library; no chunk adds a cross-seam import"
      - "rule 2, the facade written as if remote → conforms: no chunk widens LibraryFacade"
      - "rule 3, two stores → inapplicable because ruling 9 of 2026-11-19 took the store split out (no wave, not built toward); 32, 33 and 35 add columns and one table inside the catalogue file, none a cross-seam foreign key (test_seam_foreign_keys holds the count)"
      - "rule 4, Library changes reach Programming as events → conforms: 30's failed-fetch count is read through the queue, not by Programming"
      - "the operation logic lives in the service layer, MCP and HTTP thin → conforms: every new field is a service value both surfaces render; 45 and 53 are the only chunks that edit arrt/src/arrt/mcp/"
      - "Direction norm 1's home → ruling needed: question 1(d) of decisions-arrt-wave-2.md; no chunk rewords it"
      - "the 2026-07-27 Decision Log entry (each binding formats its own results) → conforms: the view-model chunk that would reverse it (draft 38) leaves this plan for a third part, with the reversal named as its first question"
  - artifact: player-contract
    dispositions:
      - "a minor is additive, a released tag is not moved → conforms: 28 freezes 1.2.0 as the package says; everything 2b changes in contract/ lands in 1.3.0 (47 and the vocabulary); one answer is corrected, not added (47's not_an_object row, 422 to 400), recorded as a DECISION because a Player's reaction to it does not change"
      - "the contract's text is the package's → conforms: 47 edits player-contract.md § Transport, 54 writes § Releases' 1.3.0 entry; no other chunk edits it"
  - artifact: api-contract
    dispositions:
      - "the MCP surface's names are frozen → amended once by ruling 3 of 2026-11-19: 45 makes the break, announced in the change record; 53 adds fields only"
      - "the tool description budget (2048 bytes, the client's truncation limit, mcp/registry.py) → conforms: 45 fits the regrouped tool under it; the draft's 're-derive the budget' is dropped because the budget is not ours to move"
  - artifact: data-model
    dispositions:
      - "identity is never a source URL → conforms: 33's search record is keyed by the work's id and the source's name, and holds no URL"
      - "per-device runtime state never lives in the catalogue → ruling needed: question 1(c); 49 makes the schema check exact without rewording the norm; the forbidden-columns extension waits for the ruling (54, conditional)"
      - "a persisted format is designed from its consumers' questions → conforms: 32, 33 and 35 list their questions before their fields"
  - artifact: information-architecture
    dispositions:
      - "the *arr layout: a page belongs to a section and is listed beneath it → conforms after a correction: the draft's spend page was 'not a sidebar item'; 36 lists Spend under System (the DECISION below says why it changed)"
      - "the vocabulary (theme, the Library, Artworks; Remove, Forget, Delete) → conforms: 37 and 41 carry rulings 1 and 2 into the words a person reads; 41 makes Players' and Watches' Remove… into Forget…"
  - artifact: security-model
    dispositions:
      - "outside text reaches the page as text; links only from a named host or a checked value → conforms: 30 serves settings_url only when it passes the contract's check, and 31 renders it as an href with rel=noopener noreferrer and its text as text"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider, never by application code → conforms: 35 records what a failed paid call may have cost and enforces nothing"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA, colour never the sole carrier → conforms: 31's states carry a word and a glyph; 41's second skip link; each screen chunk runs its keyboard tests"
  - artifact: design-direction
    dispositions:
      - "the stylesheet holds the token values → conforms: 31 and 36 add no colour outside the token blocks (test_design_tokens)"
  - artifact: observability-strategy
    dispositions:
      - "every log line a person or a dashboard reads carries an event field → conforms after 40, which gives the client-token refusal warning and the token-issued line theirs; 32, 33, 35 and 39 name their new events, and 54 writes the rows"
  - artifact: project-preferences
    dispositions:
      - "Commit attribution: none → conforms: every brief says the preference outranks a session reminder asking for trailers, and the integrator counts trailer lines on each branch before it merges"
      - "Delegation and Delegate verification (feature tests only, fail-first proof, full repo-relative paths checked before dispatch) → conforms: each chunk names its ceiling and the input that turns each new check red; verify-chunk-refs was run on every chunk"
      - "the async scope and the lint selection (norm texts false of the code) → ruling needed: question 1(a) and 1(b); no chunk adds a coroutine module or changes the lint selection"
      - "the restore and migration-chain norm row over-claims what is enforced → conforms after 49, which rewords it to what its guard enforces"
partition: "delegated, in five dispatch groups on one integration branch, fix/audit-wave-2b, every build delegate in its own isolated worktree reset to that branch, never more than eight at once. Group A, parallel, eight: 28, 29, 30, 32, 34, 35, 49, 51; as their slots free: 42, and 47 once 28 has merged. Group B, each as soon as what it waits for has merged: 31 (30, 47), 33 (30, 32, 35), 40 (30, 32), 44 (32), 45 (30, 32, 35), 48 (30), 50 (29, 48), 52 (29). Group C: 36 (31, 35), 41 (31, 34, 40), 39 (48, 50), 43 (29, 35, 40, 41). Group D: 37 (30, 35, 39, 40, 43, 48) and 53 (30, 32, 33, 35, 40, 45). Group E: 54 (every other chunk), then 55, the coordinator's integration and boundary review. The order comes from the files, not from the draft: 30 before 31, 33, 40 and 48 (health.py, client_heartbeat.py, clients.py, reports.py, the health and client regions of api.py and models.py); 32 before 33, 40 and 44 (pool.py, phase_two.py, loading.py, acquisition/service.py, sqlite.py, docs/source-plugins.md); 35 before 33 (sqlite_discovery.py, discovery_records.py); 29 before 43, 50 and 52 (.testament.toml, tests.yml, the system tests); 48 then 50 then 39 then 37 (feeds.py); 45 then 53 (mcp/); 31 then 36 then 41 (health.js, sidebar.js, walls.js, status.js); 34 then 41 (topics.js, collection.js). Opus-class, high: 29, 30, 31, 32, 33, 35, 45, 48, 53. Opus-class, medium: 37, 39, 43, 47, 49, 50, 51, 52. Sonnet-class, high: 28, 34, 36, 40, 41, 42, 44, 54. The coordinator holds the integration branch or names one integrator, and merges each delegate branch with a scoped merge commit. Chunks 38 and 46 leave this plan for a third part (dropped:)."
dropped:
  - "38: moved to a third part with the rest of the surface's shape (view models per entity, which reverses the 2026-07-27 Decision Log that each binding formats its own results; api.py by resource router; one mat act with no MCP name changed; the DisplayService facade's removal) - a move judged by nothing changed meaning, mixed here with behaviour judged by acceptance, and colliding with seven chunks' regions of api.py and models.py"
  - "46: moved to a third part with the display-plane and curation-plane words left in comments (a cleanup touching every module, last of everything, judged by nothing changed); its count is corrected there: module docstrings hold 33 dates and 4 issue numbers in 29 files, not 136 and 21"
---

# Build Plan — Audit wave 2b: the behaviour the ground carries

## What this plan is

Part 2a of the audit's second wave merged as #446 (`build-plan-audit-wave-2.md`, live
until the release). It split `DisplayService` into `arrt/src/arrt/programming/feeds.py`, `themes.py`,
`walls.py`, `scenes.py` and `reports.py` behind a facade, emptied the type ratchet (mypy
clean, and a test refuses any `ignore_errors` override), converted every browser test to
retrying assertions behind a guard, added `arrt/tests/system/` (the migration chain, a
restore, a real Player against a real server), a CI fallback, a catalogue shape
generation, and contract 1.2.0 (`transport.json`, `vocabulary.json`, optional
`settings_url`, `defaults.bottom_weight`, frozen `released/` copies). `contract-v1.2.0`
is cut.

**This plan is 2b: the behaviour.** One health vocabulary, the plugin host's second half,
hang on any selection, spend, the surface's edges, the MCP break the owner allowed once,
the small carried items, and everything 2a carried forward. The 2a plan drafted it as
chunks 30-46 before 2a was built; this plan keeps those ids, re-plans each against the code
at `aed12703` (one commit past `develop`), and adds new chunks: 28 and 29 first (decided
after 2a's boundary review), then 47-55.

**The size, honestly.** Twenty-five build chunks and the coordinator's. 2a was twenty-one
and shipped, because each chunk was small and the dispatch was wide. 2b is deeper: its
chunks change behaviour in shared files, so five dispatch groups instead of four, and
the critical path is 30 → 48 → 50 → 39 → 37. What does not fit is moved out whole, never
thinned: a **third part** (§ What moves to a third part) takes the surface's shape (draft
38), the docstring sweep (draft 46), and four smaller items. Nothing in it is begun here.

**The inputs.** The coordinator's log (`.ux-walk/audit-2026-11-19/landing-log.md` of the
main checkout, gitignored; § Wave 2), the audit and its ledger beside it, the owner's
rulings (`.prawduct/owner-rulings.md`, both 2026-11-19 sections), and the questions still
open (`decisions-arrt-wave-2.md`, Q1-Q4). A delegate's worktree carries none of the
gitignored files: the coordinator pastes the cited findings into each brief.

| Chunk | Title | Model, effort | Waits for |
|---|---|---|---|
| 28 | Contract 1.2.0 frozen beside the others | Sonnet-class, high | — |
| 29 | The real-Player test, a suite of its own, on every pull request | Opus-class, high | — |
| 30 | One health model — the server | Opus-class, high | — |
| 31 | One health model — the screens | Opus-class, high | 30, 47 |
| 32 | The plugin host's second half — the answers kept apart | Opus-class, high | — |
| 33 | Phase two answers within a window, and each search is recorded | Opus-class, high | 30, 32, 35 |
| 34 | Hang on any selection | Sonnet-class, high | — |
| 35 | Spend — the paid call that fails after it was sent | Opus-class, high | — |
| 36 | Spend — a page under System | Sonnet-class, high | 31, 35 |
| 37 | Not found is 404, and a refusal names the Library | Opus-class, medium | 30, 35, 39, 40, 43, 48 |
| 39 | The publisher's two promises: a periodic reconcile, a size bound | Opus-class, medium | 48, 50 |
| 40 | Small server items | Sonnet-class, high | 30, 32 |
| 41 | Small client items | Sonnet-class, high | 31, 34, 40 |
| 42 | The compose example, hardened | Sonnet-class, high | — |
| 43 | Test-suite health: clocks, ids, areas, the long tests | Opus-class, medium | 29, 35, 40, 41 |
| 44 | A supported plugin-testing helper | Sonnet-class, high | 32 |
| 45 | The MCP surface, broken once | Opus-class, high | 30, 32, 35 |
| 47 | Contract 1.3.0: the Player states' words, one corrected answer, the missing must-refuse fixtures | Opus-class, medium | 28 |
| 48 | Programming reads inside its writes; one home for the lookups; the facade's leftovers | Opus-class, high | 30 |
| 49 | The catalogue's shape guards: an exact schema, a release list a test holds, a generation's sentence | Opus-class, medium | — |
| 50 | The system tests guard what they run | Opus-class, medium | 29, 48 |
| 51 | Browser assertions that can fail; flake #442 | Opus-class, medium | — |
| 52 | The fallback runs what the manifest says | Opus-class, medium | 29 |
| 53 | MCP II: the twins of 2b's new fields | Opus-class, high | 30, 32, 33, 35, 40, 45 |
| 54 | Records, and the change record | Sonnet-class, high | every other chunk |
| 55 | Integration and the boundary review (the coordinator's) | — | all |

## Goals

- **Response taken:** proceed. The owner asked for substantially all identified product
  issues to be fixed by delegated builders under this repository's governance, ruled on
  every question put on 2026-11-19 (ten rulings after wave 1, two during wave 2), and left
  four open (Q1-Q4). No chunk of this plan waits on Q1-Q4 except two conditional
  deliverables of 54 (§ What waits for the owner).
- **Product:** the household reads one story about its walls and Players (a wall with no
  Player is a step not yet taken, not a fault; 2,000 failed fetches raise something); a
  work whose picture nobody has is told apart from one nobody could be asked about; a
  selection hangs like a work; money a failed call may have cost is counted as unknown, on a
  page; an agent finds every act on a wall in one tool and reads `artwork_id` where it meant
  one. And every check 2a added checks what it says: a real Player on every pull request, a
  schema check that cannot pass a missing table, a release list a test holds.
- **Architecture, what must hold:** the four seam rules as built and guarded (ruling 9: no
  split is prepared); `DisplayService`'s public surface unchanged (48 moves its internals and
  keeps every name; the facade's removal is the third part's); the contract moves to 1.3.0
  additively but for one corrected answer; the MCP surface breaks once, in 45, and only
  grows after it (53).
- **What must stay possible (ruling 8):** several label outputs on one Player, a Player with
  labels and no display. 30's Player state is per output; its acceptance includes that shape.
- **Constraints:** a delegate runs feature tests only (`project-preferences.md` § Workflow,
  `Delegate verification`), and the governance suite whole when it adds, moves or renames a
  tracked file (2a's first integration found five reds no delegate had run). Every new or
  rewritten check comes back with its failing output against today's code or a re-break,
  naming the input. A test is a contract: an assertion a chunk must change is listed under
  its *Rewritten assertions*, never changed quietly. No heavy builds on GitHub's runners
  (the 2026-11-18 ruling): minutes are spent on suites only during a pool outage. An outage
  of the pool must not block a merge (ruling 4). The pool's endpoints are public and stay
  repository variables (ruling 1 of 2026-11-19, during wave 2).
- **Tradeoffs accepted:**
  - The facade stays (2a's tradeoff, kept): 48 removes what it holds and never reads, and
    moves `DisplaySettings` out, but callers still say `services.display.<method>`. Revisit
    in the third part, with the view models.
  - HTTP keeps `work_id` where MCP says `artwork_id` (45's DECISION): one fact, two names, a
    rename map in the parity test. Revisit if `/api` gains a reader other than the browser.
  - Two serializers per entity stay (draft 38 moved): the parity test holds them alike.
  - 43 injects clocks and ids with defaults, so construction sites do not change and the
    tests are what pass a clock. A constructor that forgets one still reads the machine's.
- **What I would do differently (the advisor's position):** open the 2b pull request as a
  **draft as soon as 28 and 29 are integrated**, so every later integration push runs under
  the new required check and 29's acceptance is seen there rather than on a scratch branch
  alone. If the pool is loaded, run group A at six (hold 49 and 51, which nothing waits on).
  If the plan stalls past three sessions, the first to move to the third part are 43, 44 and
  52: each is whole on its own and nothing in 2b waits on it except 37's wait on 43, which
  then drops.
- **Decisions made in this plan** (each vetoable; each states its cost and was checked
  against the norm index **and** the dated rulings — lesson 2). Those marked *(draft)* are
  the 2a plan's, kept; *(corrected)* changed against the code, and say what changed:
  - `[DECISION: the real-Player test becomes a fifth testament suite, player, in .testament.toml (the curation project's command with -m player_e2e, selecting arrt/tests/system/test_a_real_player.py, no requires), so tests.yml, which runs testament run with no --suite, runs it on every pull request inside the required check "Lint, then every suite"; the fallback runs it on GitHub's runner too, because it needs only git, uv and GitHub | the 2a plan's decision that the pool tests the shipped pair on every server change is recorded as half built (2a § Decisions made mid-build, Chunk 08); rulings checked: 2026-11-18 (minutes only during an outage: holds, about three minutes more then), ruling 4 (an outage does not block a merge: a pool outage falls back; a GitHub outage blocks merges anyway); cost: every pull request waits for the pair, 81 s warm and 210 s cold on the pool (2026-11-19); a Player pin that will not install, or a fetch from GitHub that fails, turns the required check red rather than falling back; the check's name does not change | user can veto/override]`
  - `[DECISION: everything 2b changes in contract/ lands in contract-v1.3.0, cut by the coordinator after this plan merges and copied into contract/released/1.3.0/ in the next plan's first commit, as 1.2.0 is here: the Player states' words (vocabulary.json player_states), the missing must-refuse fixtures, and one corrected answer: the wall heartbeat's not_an_object case answers 400 in the error shape, as the client heartbeat's does, where 1.2.0's transport.json records 422 in the framework's body | the 422 is the server's inconsistency, recorded as found (2a Chunk 03); rulings checked: none bears; cost: the correction changes a documented answer, so it is not additive in the strict sense; a Player whose double replays transport() from 1.2.0 answers 422 where a 1.3.0 server answers 400, and both rows say the Player reacts as for 400, so no Player behaviour changes | user can veto/override]`
  - `[DECISION (draft, keys fixed): the household's words for a wall's states are contract/vocabulary.json's display_states (Showing, Screen off, In use, No screen, Not known, Not reporting, No Player yet); a Player's are its player_states, keyed no_token, awaiting_report, reporting, not_heard_from, report_unreadable and worded No token yet, Waiting for its first report, Reporting, Not heard from since {date}, Report unreadable; a state whose setup flag is true (unassigned, no_token, awaiting_report) is never a fault on the top bar or the System badge | audit-6 3 and audit-5 F4 ask for one story; the Player's settings page speaks of itself (the Player planner's W2-3), so its words live where both sides read them; cost: a contract key the Player need not adopt yet, and a server that cannot read the package at run time (arrt-contract is a dev dependency; the image's app stage installs none) quotes the setup flags in Python with a test against the package, as adequacy.py quotes the bottom weight | user can veto/override]`
  - `[DECISION (draft): works the queue holds as failed are a health observation: their count, with the age of the newest, reaches the top bar and the System badge, linking to Queue | audit-6 3: 2,000 failed fetches raised nothing; cost: the badge stays lit until the queue is cleared or retried, which is the point, and one more reason a household sees it lit | user can veto/override]`
  - `[DECISION (corrected): an acquisition's outcome is one of ok, partial_tiles, none_held, unasked, faulted, link_gone or failed (legacy and unclassified), kept in a new nullable column beside the coarse fetch status, which keeps its three values (ok, partial_tiles, failed); unasked is retried on the queue's next pass, faulted after the plugin's next load, none_held and link_gone are settled until the work's Wikidata item changes | the draft widened FetchStatus itself, but an older release reads that column with FetchStatus(row[...]) and would fail on a new value (persistence/sqlite.py), which the shape generation cannot see (file.py's comment: a new value in an existing column moves no shape) and which raising the generation would answer by refusing every rollback; rulings checked: ruling 10 (rollback stays the previous image alone, which this keeps); cost: two columns carry one fact, so a test holds them consistent (an outcome other than ok or partial_tiles has fetch status failed) | user can veto/override]`
  - `[DECISION (draft): a finder may answer link_gone (source plugin interface 1.6, additive): every page the registry linked for this work is gone at the museum; phase two treats it as settled for that source and records it apart from could-not-be-asked | audit-4 4's second half; a 1.5 plugin loads unchanged; cost: arrt-sources adopts it in its own plan, and until then a vanished page still reads as could-not-be-asked | user can veto/override]`
  - `[DECISION (corrected): phase two's pool answers with the sources that answered within the look's window (LOOK_HOLD_SECONDS, 30 s) and keeps the slower answers in a durable search record, a new discovery table keyed by work id and source, which phase two reads on its next pass | the draft said the pool waits for every source; the look already answers per source within its hold (library/services/look.py), and the wait for the slowest is phase two's (library/discovery/pool.py, the slowest source's deadline plus 5 s); a plugin may now declare up to an hour; #313 asks for the record; cost: a work may settle on fewer sources than will answer, and is revisited on the next pass rather than in the same Get | user can veto/override]`
  - `[DECISION (corrected): a paid call that fails after it was sent records a spend row whose cost is unknown: a new column cost_status (known, unknown) widened onto spend_records with known as its default, cost_usd kept NOT NULL and holding 0 for such a row, and every sum counting unknown rows apart, so the month reads "at least $X, and N calls whose cost is unknown"; no generation lookup is built | the draft looked the cost up by generation id; openrouter-api-findings.md records that the lookup answered 404 on every attempt and that the inline usage.cost replaced it, and a timed-out request returns no id; widening cannot make cost_usd nullable, and a table rebuild is a step that raises the shape generation and refuses every rollback; an older release sums such a row as $0, which is what it says today with no row at all; cost: the ledger never settles an unknown row; reopen if the operator's paid probe shows the lookup answering | user can veto/override]`
  - `[DECISION (corrected): spend has a page of its own at #spend, listed under System in the sidebar like every System page, and reached also from the sidebar's budget line and from Status | the draft made it "not a sidebar item"; the information architecture's Direction norm says a page belongs to a section and is listed beneath it, so the draft departed from a norm without recording it; cost: one more sidebar item | user can veto/override]`
  - `[DECISION (draft): Remove takes a thing out of a set (a theme, a wall); Forget drops a record the household made of something outside (a Player, a Watch, a Wanted item, a taste); Delete destroys a thing with dependents (a wall, a theme); Players' and Watches' Remove… become Forget… | audit-5 F14's UI half; cost: two buttons change their words | user can veto/override]`
  - `[DECISION (corrected): the MCP break (45) is: artwork_id for every work id in a wall output; every act on a wall gathered in one tool; not_again(scope='theme') removed in favour of remove; display_plane_has_reported renamed has_reported. The acts gather on art_display if they fit the client's 2048-byte description budget beside its other actions; if they do not, art_display keeps walls and every act on them, and its Player and display actions move to a new tool, art_players. HTTP keeps work_id, held to MCP by a rename map in test_surface_parity.py | ruling 3; the draft said no tool name is added and art_display's budget is re-derived, but the budget is the client's truncation limit (mcp/registry.py DESCRIPTION_BUDGET_BYTES, test_mcp_surface.py), art_display already uses 2045 of its 2048 bytes, and wave 4f put the scene acts on art_theme for exactly this reason (build-plan-wave-4f-scenes.md); ruling 3 is about the agent surface and /api's only reader is the browser, which gains nothing from a rename; cost: agents relearn where the wall acts are, possibly one more tool in every listing, and one fact named two ways across MCP and HTTP | user can veto/override]`
  - `[DECISION: not found becomes its own error, NotFound(ServiceError), which /api answers with 404 and every other ServiceError with 400 as today; MCP's error shape does not change | audit-2 M8; cost: 86 assertions of 400 in 32 test files are reviewed and those that mean not found become 404, each listed | user can veto/override]`
  - `[DECISION: the migration chain's release list is held by a governance test: every release the change log records with a version below arrt/pyproject.toml's has a row in releases.json, a dump or the release whose shape it shares | 2a § Decisions made mid-build (Chunk 06) recorded that nothing fails when a release ships without its dump; the dump can only be made from the tag, which exists after the release commit, so the test bites at the next version, not at the release itself; cost: the next release after a shape change cannot be cut without running old_catalogue.py with the tags present | user can veto/override]`
  - `[DECISION: the system tests are type-checked: arrt/pyproject.toml's [tool.mypy] files gains tests/system, and only that | 2a's integration found 18 "may be None" indexings in test_a_real_player.py and nothing checking them; the rest of the test tree is not in scope (several thousand annotations for little); cost: the type gate runs a little longer, and test code there needs its narrowings | user can veto/override]`
- **Inferred, not ruled:** that `/api` has no reader but the browser (the tradeoff above rests
  on it; 54 checks `api-contract.md` for a promise to another reader before the change
  record says so). That the pool's runners all reach GitHub (true of every run of
  2026-11-19; if a runner without the network joins, 29's suite needs a label, which 29
  records how to add).
- **Level:** High for 28, 34, 36, 40, 41, 42, 44, 54 (fully specified). Medium for the rest:
  each has a design choice its builder makes against stated acceptance. What would raise it:
  45's regroup measured first (the byte count of the gathered descriptions, before any code),
  and 29 seen on the draft pull request before group B is dispatched.

## Commit subjects, so the review can attribute each chunk

Prawduct attributes a commit to a chunk only by its subject, and only when the subject
carries this plan's scope; the coverage gate reads first parents, so the merge commit
carries it too. Every brief quotes this:

- **Every commit a delegate makes:** `<type>(audit-wave-2b): <what changed> (Chunk NN)`,
  `<type>` one of `fix`, `feat`, `test`, `refactor`, `docs`, `ci`, `chore`.
- **The integrator's merge of each branch:** `git merge --no-ff -m
  "merge(audit-wave-2b): <the chunk's title> (Chunk NN)" <branch>`; never a fast-forward.
- **The integrator's own fixes:** `fix(audit-wave-2b): <what> (Chunk 55)`.
- **No attribution trailers**, whatever a session reminder asks: `project-preferences.md`
  says `Commit attribution: none`, and the preference outranks the reminder. The integrator
  counts trailer lines on each branch before merging it and returns any that has them.
- **The boundary review** names the chunks it covers with `critic-begin --chunks`.

## What 2a taught, built into every chunk

The four the owner asked to be explicit, each repeated in the chunks it bears on:

1. **A parser of a foreign tool's output is tested on lines copied from an observed run.**
   2a's fallback driver matched `request <id> accepted` at the start of a line, which a run
   of one suite prints; a run of several prefixes `[suite] `, and every pull request fell
   back. Chunks 28 (§ Releases' lines), 29 and 52 (testament's progress lines), 47 (the
   framework's error body) and 51 (Playwright's behaviour under load) copy their inputs
   from an observed run or file and say where from.
2. **A decision records its cost as well as its reason, and is checked against the dated
   rulings as well as the norm index.** 2a's catalogue guard compared release numbers and
   refused the commonest rollback; its mypy step ran against the 2026-11-18 ruling the
   workflow itself quotes. Every DECISION above names its cost and the rulings it was read
   against; a builder who makes one mid-build does the same (§ Decisions made mid-build).
3. **A replaced mechanism's implicit guarantees are listed and tested.** Chunks 29
   (deselection), 31 (`STATE_WORDS`), 32 (`failed` as the only failure), 45 (the tool
   grouping), 48 (the lookups), 50 (the in-process feed guard) and 52 (the hand-written
   fallback) each carry *Implicit guarantees*, each with the test that holds it.
4. **A delegate's report is evidence about intent; the records chunk verifies each sentence
   against the code.** The Player's records chunk found a wrong rollback value and runbook
   steps that had never been written. 54 works every chunk's *Records owed* as a checklist,
   and each sentence it writes cites the file and line it read.

And the rest of 2a's, kept:

5. **Attribution:** § Commit subjects.
6. **The image.** A chunk whose test reads a file outside `arrt/` says so under *Reads
   outside arrt/*; 55 runs the image's test stage (`image.yml` by hand on the head).
7. **Rewritten tests** are listed with the old assertion and the reason.
8. **The governance suite whole** when a chunk adds, moves or renames a tracked file.
9. **A run overlapping an outage is no evidence**; it is run again.
10. **A scratch directory per delegate.** Three delegates of 2a found the shared session
    scratchpad overwritten by another's scripts. Each brief names
    `<scratchpad>/<chunk id>/` as that delegate's only scratch directory (C24).
11. **A check is shown red first**, and a negative claim (absence, "never", "exactly once")
    is anchored on something that is there first (2a's browser table, hazards 2 and 11).

## Shared values this wave

| Value | Owner | Quoted by, with the test that fails on divergence |
|---|---|---|
| The words for a wall's states | `contract/vocabulary.json` `display_states` (2a's 03) | new `arrt/src/arrt/http/static/core/states.js` (31); `arrt/tests/unit/test_wall_state_words.py`, rewritten by 31 to hold `states.js` and `ScreenState` to the package both ways |
| The words and keys for a Player's states | `contract/vocabulary.json` `player_states` (47) | `PlayerState` in new `arrt/src/arrt/programming/player_state.py` (30, keys from the DECISION); `states.js` (31); the same test (31) holds keys and words |
| What is a setup step, not a fault | the `setup` flags in `vocabulary.json` | `display_state.py` and `player_state.py` quote them (30), with a test parametrised over the package's states; `arrt/src/arrt/http/static/core/status.js` reads the server's troubles (31) |
| Acquisition outcomes and the plugin interface (1.6, `link_gone`) | `arrt/src/arrt/library/sources/plugin.py` (`API_VERSION`) and a new outcome enum in `arrt/src/arrt/persistence/records.py` (32) | `arrt/src/arrt/http/static/core/providers.js` words (`test_client_vocabulary.py`); the queue's retry rule (a test parametrised over the enum); `docs/source-plugins.md`'s table (a test reads it against the enum) |
| MCP tool and argument names | `arrt/src/arrt/mcp/tools.py` (45, then 53) | `api-contract.md`'s MCP table; `test_mcp_surface.py`'s frozen-name list; `arrt/src/arrt/ask/prompt.py`'s `ASK_SCOPE` (a subset of the tools, held there) |
| A work's id in a wall output | MCP says `artwork_id` (45) | HTTP's `work_id`, by a rename map in `test_surface_parity.py` that refuses a stale rename |
| The suites CI runs | `.testament.toml` (29) | `tests.yml` (no `--suite`); `pool_or_fallback.fallback_plan`; `CLAUDE.md`; `tests/test_ci_fallback.py` |
| The feed's size bound | `contract/transport.json`'s `max_bytes` | the publisher quotes it (39) with a test against the package |
| The catalogue's past releases | `RELEASES` in `arrt/tools/old_catalogue.py` (49) | `releases.json`; the change log's release tags; new `tests/preferences/test_catalogue_release_dumps.py` |
| The contract's version and its frozen releases | `contract/pyproject.toml` (47), `contract/released/` (28) | `test_released.py`; § Releases (54) |

**What other repositories read, and when it lands.** Contract 1.3.0 (47, 30's keys, 31's
quote) is cut after this plan merges; Arrt Player's next plan moves its pin and must give
each new must-refuse fixture a reason. Source plugin interface 1.6 (32) ships with the
server's next release; arrt-sources adopts `link_gone` and the testing helper (44) in its
own plan. Nothing here changes what a Player reads, writes or requests.

## Shared seams this wave

A file two chunks touch has one owner at a time; the order is the partition's.

- `.testament.toml`: 29 (`[suites.player]`), then 43 (curation areas).
- `.github/workflows/tests.yml`, `.github/scripts/pool_or_fallback.py`,
  `tests/test_ci_fallback.py`: 29, then 52.
- `docs/testing.md`: 29 (§ The real-Player test; the CI paragraph's suite list), 51 (§
  Assertions read the page through `expect`), 52 (the CI paragraph), 43 (areas, if it
  documents them). Each its own section.
- `CLAUDE.md`: 29 only (the dev-commands paragraph's suite list).
- `arrt/tests/conftest.py`: 29 (the report-header hook), 50 (`every_feed_keeps_the_contract`).
- `arrt/tests/browser/conftest.py`: 31 only (the wall fixture's no-Player shape).
- `arrt/pyproject.toml`: 50 only (`[tool.mypy]` files).
- `contract/`: 28 (`released/1.2.0/`, `tests/test_released.py`), 47 (everything else it
  names, `vocabulary.json` included). `player-contract.md`: 47 (§ Transport), 54 (§ Releases).
- `arrt/src/arrt/http/api.py` and `arrt/src/arrt/http/models.py`, by region: 30 (health, walls' state,
  clients), 32 (acquisition causes and the queue's models), 33 (`SourcePluginOut`), 35
  (`SpendReport`), 36 (a spend route only if one is missing), 40 (the history route's
  parameter, the registry rows, `WorkOut`'s Get), 37 (`service_error_response`). Merge order
  is the partition's; each brief names its regions.
- `arrt/tests/unit/test_surface_parity.py`: 30, 32, 33, 35 and 40 each add an exemption
  constant naming Chunk 53 for a field HTTP gains first; 45 adds the wall rename map; 53
  removes every exemption naming it. The file's own test refuses a stale exemption.
- `arrt/tests/unit/test_catalogue_store.py`: 49 makes `_EXPECTED_SCHEMA` exact; 32, 33 and
  35 each add the rows for what they add, or the integrator does at merge (one line each)
  when 49 merged after they were cut.
- `arrt/src/arrt/services/container.py`: 30 (`HealthService`'s construction), then 39 (the
  scheduler's jobs).
- `arrt/src/arrt/programming/feeds.py`: 48, then 50 (only if its stale-feed case is red),
  then 39, then 37. `arrt/src/arrt/programming/reports.py`: 30 (`survey_wall_status`,
  `describe_wall_status`), then 48 (`_record_screen`). `arrt/src/arrt/programming/client_heartbeat.py`: 30,
  then 40.
- `arrt/src/arrt/library/services/runner.py`, by region: 32 (`WorkOutcome`), 35
  (`SpendReport`), 33 (could-not-be-asked, after both).
- `arrt/src/arrt/library/services/discovery.py`: 35, then 43, then 37.
  `arrt/src/arrt/library/services/catalogue.py`: 40, then 43, then 37.
  `arrt/src/arrt/library/acquisition/service.py`: 32, then 40. `arrt/src/arrt/persistence/sqlite.py`: 32, then 40.
  `arrt/src/arrt/persistence/sqlite_discovery.py`, `discovery_records.py`, `discovery.py`: 35, then 33.
- `docs/source-plugins.md`: 32, then 44. `.prawduct/artifacts/source-plugins.md`: 32.
- Static files: `arrt/src/arrt/http/static/screens/walls.js`, `arrt/src/arrt/http/static/screens/clients.js`, `arrt/src/arrt/http/static/core/status.js`: 31, then 41;
  `arrt/src/arrt/http/static/screens/health.js`, `arrt/src/arrt/http/static/core/sidebar.js`: 31, then 36, then 41; `arrt/src/arrt/http/static/screens/topics.js`,
  `arrt/src/arrt/http/static/screens/collection.js`, `arrt/src/arrt/http/static/screens/artists.js`, `arrt/src/arrt/http/static/screens/search.js`: 34, then 41.
- `.prawduct/artifacts/information-architecture.md`, by rows: 31 (Walls, Players, Status, the
  top bar), 34 (the selection toolbar), 36 (System › Spend), 41 (the Work page, the
  vocabulary's Remove and Forget).
- `.prawduct/artifacts/api-contract.md`: 45, then 53 (the MCP sections); 54 (the rest).
- `.prawduct/artifacts/project-preferences.md`: 49 (the restore and chain row), then 54
  (any Q1 amendment the owner rules).
- `arrt/src/arrt/mcp/`: 45, then 53. Nobody else.

## Decisions made mid-build

Appended while building, each in the plan's form, with its cost and the rulings it was read
against, and as vetoable as the ones above. Where one changes a chunk's text, the chunk is
left as planned and this section is the later word.

- **2026-11-20, by the owner's ruling of the same day** (`.prawduct/owner-rulings.md`: CI is
  kept small, tests run on the pool first, CI makes no paid call): (a) Chunk 29's fallback
  does not run the real-Player suite on GitHub's runner; it leaves it out and says so by
  name, as it does for the browser suite. (b) Chunk 56 is added: the image's test stage
  stops building on GitHub's runner for every pull request. (c) No chunk of this plan adds a
  step, a job or an install to a workflow that runs on GitHub's runner except to remove or
  shorten one; a chunk that needs CI to do more gives the work to the pool.
- **2026-11-20 (Chunk 49), as built:** the Goals say the release-list test requires a dump for every
  release *below* the version `arrt/pyproject.toml` names. It was built as *at or below*: "below"
  would let a release ship without its own dump and refuse only at the one after. The cost is that
  `arrt/tools/old_catalogue.py` runs inside the release commit, before that release's tag exists;
  the tool builds the newest untagged release from `HEAD` for that reason, and any other missing
  tag fails by name. Between releases the version is still the last release's, so an ordinary pull
  request is green. Every release now has a row in `arrt/tests/fixtures/catalogues/releases.json`
  (a release that changed nothing in the catalogue reuses an earlier dump), which the norm row in
  `.prawduct/artifacts/project-preferences.md` now says.
- **2026-11-20 (Chunks 30, 32 and 40), a value three chunks share:** the acquisition queue kept no
  instant of a work's last failure, so the health model could count the works the queue gave up
  on and could not say how old the newest failure is. Chunk 32 adds a nullable `failed_at` to the
  queue row, written at every recorded failure, the give-up included; a row that failed before
  the column existed keeps none, which reads as "not recorded" (no instant is guessed). Chunk 30,
  built beside it, derives the instant for rows still being retried behind one function and
  answers "not known" for the rest; Chunk 40, which waits for both, makes that function read the
  column and keeps the derivation only for rows written before it.
- **2026-11-20 (Chunk 35), two edits outside its files, allowed by the coordinator:** one
  defaulted field `cost_status` on `EngineSpend` (`arrt/src/arrt/library/discovery/engine.py`,
  which no chunk of this plan owns) and one keyword in `_record_spend`'s call in
  `arrt/src/arrt/library/services/runner.py`, so that "cost not known" travels from the engine to
  the ledger.
- **2026-11-20 (Chunk 30), two assertions rewritten in test files Chunk 45 owns later, allowed by
  the coordinator:** the parity of the MCP `clients` tool with the browser's route holds except
  for a named set of fields the route answers and the tool does not yet, which Chunk 53 deletes
  when it adds them; and the status observation's test assigns its wall to a Player, with a new
  case for a wall that has none. No tool name, argument or result key changes in Chunk 30.
- **2026-11-20, by the owner's ruling of the same day** (`.prawduct/owner-rulings.md`: a hang
  can be started from Walls; hanging for a duration waits): Chunk 57 is added, the wall-side
  way to hang chosen works that Chunk 34 left out as the owner's to decide. Hanging for a
  duration stays out of this plan.
- **2026-11-20 (Chunk 58 added), from the integration of Chunk 47:** a frozen release holds
  its `fixtures/` and `routes.json` and not its `contract/transport.json` or
  `contract/vocabulary.json`, which contract 1.2.0 introduced. So nothing holds an answer or a
  word to the last release: the integrator changed one answer in the table with no
  `corrected` record and the contract's suite stayed green (only the server's own table test
  caught it, and only because the server had not moved with it). Chunk 58 puts both files in
  the frozen copy of 1.2.0, as they are at the tag, and makes the package's suite hold HEAD
  to them.
- **2026-11-20 (Chunk 33), a rule added to its work, from what Chunk 32 built:** a work that
  could not be asked is asked again on the next pass, with no limit (the Goals' rule). During
  a museum's outage that makes every pass ask every such work at that museum, one at a time,
  each up to the plugin's deadline. So within one pass, after a small number of consecutive
  could-not-be-asked answers from one plugin, the rest of that pass does not ask it: those
  works stay as they are and the next pass tries again. The number and its reason are
  recorded by Chunk 33, which first finds out whether the pool already holds a plugin back.
- **2026-11-20 (Chunk 40), four items added to its work, from what Chunks 30 and 32 built:**
  the health model's instant of a work's last failure reads the queue's `failed_at`, with
  the derivation kept only for rows written before that column; a read of the queue's failed
  states that reads no titles replaces the one the health route uses today (87 to 93 ms per
  read at two thousand failed works, measured, against 0.3 ms without the count); a Player
  not heard from and the walls it shows are one trouble, stated on the Player and naming
  the walls, not two; and a wall with no Player does not read "this wall's Player has not
  reported yet" (`arrt/src/arrt/programming/manifest/heartbeat.py`).
- **2026-11-20 (Chunk 43), a test added to its work:** `arrt/tests/unit/test_major_2_feed.py`'s
  test of a slower neighbour that cannot be rebuilt failed once in a five-suite run on a
  loaded runner (once in 39 recorded runs) and has not been reproduced. Chunk 43 establishes
  whether it reads the real clock and fixes the cause where it is.
- **2026-11-20 (Chunk 59 added), from Chunks 28, 50 and 58:** the writer of a frozen release
  copy was in no commit (two chunks used a script in a scratch directory); the contract
  package ships no `py.typed`, so the server's type check needs an allowance to import it;
  and `released()`'s docstring still says a copy holds only `fixtures/` and `routes.json`.
  Chunk 59 settles the three.
- **2026-11-20 (Chunk 33), as ruled while it was building:** the pass in which a plugin that
  is not answering is held back is the acquisition queue's (`AcquisitionQueue.run`), not
  the image pool's; three consecutive could-not-be-asked answers from one plugin, and the
  rest of that pass does not ask it. **A work the pass did not ask is left exactly as it
  was**: no new failure, no refreshed `failed_at`. The cost: a plugin that fails three asks
  in a row for unrelated reasons is not asked again until the next pass.
- **2026-11-20 (Chunk 39), two items added to its work:** the service's remove-from-theme
  writes the wall-history event `work.left_theme` for each wall the theme hangs on, so a
  wall's history says a work left whichever way it left (the MCP break removed
  `not_again`'s `scope`, which was the only path that wrote it for an MCP caller); and the
  double readings of the clock within one act that the schedule fix listed (the step to
  the next work; each wall's scene layer) are passed the act's one instant.
- **2026-11-20 (Chunk 40), as built:** a work's Get is on the work's detail answer, not on
  every card's, so a grid does not pay a read per card; `nga.py` was not moved onto
  `atomic.py`, because a built-in plugin may import only the plugin interface and widening
  that is a decision about the interface, not a tidy-up.
- **2026-11-20 (Chunk 45), as built:** the regrouped wall tool would not fit the MCP
  client's 2,048-byte description limit with the Player and assignment actions beside the
  wall acts (3,054 bytes), so those ten actions moved, under their old names, to a new
  tool, `art_players`. It is part of the one break ruling 3 allows.
- **2026-11-20 (Chunk 56), as built:** the pool cannot run the image's test stage for this
  project (a host suite is refused for it, and its container route has no build target and
  no Docker), so no suite was added; a root test holds what the stage must carry against
  what the tests open, and `image.yml` runs on pull requests into `main` and by hand. The
  cost: a Dockerfile, lockfile or interpreter change that no longer builds, and a test that
  passes only as the files' owner, are met at the pull request into `main`.
- **2026-11-20 (Chunk 39), a cost to settle:** the periodic reconcile runs every scheduler
  pass and holds the store's lock for the whole of it (170 to 420 ms with nothing to fix at
  300 works on one machine, most of it growing with the Library). Chunk 60 measures it at
  the size of a real Library and sets how often it runs from that.
- **2026-11-20 (Chunks 60 and 61 added):** what the chunks of groups B and C found and could
  not settle in their own files. Chunk 61 exists because two chunks together made the CI
  fallback's governance step red while the pool stayed green (the type check followed a
  tool into a package the fallback's environment does not install).
- **2026-11-20 (Chunk 37), a boundary ruled on:** with not-found answering 404, two client
  reads that took only a 400 would have broken (Artworks on a bookmarked theme that is
  gone; Get again with a candidate work gone). Those two lines are Chunk 37's, each with a
  browser test, because the fault exists only once its change merges. The server stays
  uniform: one meaning of not found, in one place.
- **2026-11-20 (Chunk 60), the reconcile's cadence:** measured in-process on one machine with
  nothing to fix, a pass took 0.4 s at 2,000 works and 1.1 to 2.5 s at 5,000, the store's
  lock held throughout, most of it per-work lookups. The reconcile runs at the first
  scheduler pass and then every sixth (half an hour). The cost left: an act that arrives
  during a reconcile waits for it, longer on the deployment's slower machine. Batching the
  lookups is the fix and goes to a third part.
- **2026-11-20 (Chunk 60, as integrated), one cause listed three times:** a Player with no
  token that shows two walls made three setup steps, and each wall's own panel still read
  as not reporting beside "nothing needs attention". Chunk 62 makes it one step per cause.
- **2026-11-20 (Chunk 43), what a cheaper test cost:** the UX walk visits each screen once,
  and three states it reached only as a second visit are no longer walked. Chunk 63 names
  them. Its cache result: about half the suite still cannot be cached; a clock read is why for about 2,250 of them, and a real server process or a socket
  for about 3,100. A third part
  takes the shared fixtures' clock.
- **2026-11-20 (Chunks 62 and 63 added):** what the last passes of integration found.
- **2026-11-20 (Chunks 60 and 63, as integrated), a guard nobody ran:** two chunks each
  reached integration with one red, from a guard that reads what the chunk added and that
  its delegate did not run (a whole-answer comparison; the browser suite's rule against a
  one-shot read of the page). Each was fixed on the integration branch by a commit that
  names its chunk. The delegates' brief now says to run the guards that read what you add.
- **2026-11-20 (Chunk 37, as integrated), five sentences left:** the refusals say the
  Library; five other sentences a person reads on a screen still said the catalogue, in
  files that chunk did not own. Chunk 64 changes them and holds the rest by a guard.
- **2026-11-20 (Chunk 64 added):** a last sweep of what the final passes of integration
  listed and no chunk owned.

## The items 2a carried forward, and where each went

Collected from `landing-log.md` § Wave 2 (the `arrt W2` entries, the integration passes, the
boundary review and its fixes), and from the 2a plan. Numbered so a brief and the records
chunk can cite them.

| # | Item | Goes to |
|---|---|---|
| C1 | Checks made outside the transaction that writes: `delete_theme`, `exclude_work`, `allow_work`, `remove_from_theme` (check before the act); `make_default`, `update_theme` (no transaction); `_record_screen` (reads known screens outside) | 48 |
| C2 | `scenes.py` `scene_walls` reads with no read scope; a wall deleted between `_pins_on_held_walls` and `get_wall` ends as a 500 | 48 |
| C3 | `walls.js` `liveScene` joins walls with " and " | 41 |
| C4 | The feed guard patches only inside the test process: feeds a real server process publishes are never checked | 50 |
| C5 | `test_restore` checks only `works` and `playlist.id` | 50 |
| C6 | Not measured: a feed left beside a restored catalogue naming a work the backup lacks | 50 |
| C7 | `transport.json` records the wall heartbeat's 422 in the framework's body where the client heartbeat answers 400 | 47 |
| C8 | `_EXPECTED_SCHEMA` lacks `reported_screens` and its `<=` check passes any unlisted table | 49 |
| C9 | `FeedPublisher` is every collaborator's wall and theme lookup (review R-3), to move before "not found is 404" | 48, before 37 |
| C10 | The migration chain's release list grows by hand; the enforcing test | 49 |
| C11 | The norm row claims "a catalogue every past release left opens" where the guard holds every release `releases.json` lists | 49 |
| C12 | `SnapshotFailed` says "needs a migration that drops catalogue shape generation N" on a generation rise; a wave-1 test pins "drops themes.is_active" | 49 |
| C13 | Three `# sleep:` markers that are not "nothing happens" claims (`test_no_machine_dates.py`, `test_wanted.py`, `test_the_run_view.py`) | 51 |
| C14 | `test_a_table_wider_than_its_box_takes_the_keyboard`'s fitting-box clause cannot fail | 51 |
| C15 | `test_no_page_calls_a_player_a_client` anchors on `#view h1`, which a screen paints before its data | 41 |
| C16 | The system tests are not type-checked (18 "may be None" indexings in `test_a_real_player.py`) | 50 |
| C17 | The deselection header uses a pytest internal (`_pytest.mark.expression`) | 29 |
| C18 | `DisplaySettings` lives in the facade module | 48 |
| C19 | The facade keeps `_library`, `_settings`, `_store` it never reads | 48 |
| C20 | `vocabulary.json`'s `_about` says Walls words `unassigned` as "No Player yet"; Walls says "No Player" | 31 |
| C21 | The client-token refusal warning (`arrt/src/arrt/programming/access.py`) has no `event` field; nor has the token-issued line | 40 |
| C22 | The fallback's suite commands are copied by hand into YAML (native review N8) | 52 |
| C23 | Flake #442, cause not established | 51 |
| C24 | A scratch directory per delegate | § What 2a taught (lesson 10), and every brief; no chunk |
| C25 | `contract/released/1.2.0/` owed in the first commit of 2b | 28 |
| C26 | The real-Player test on every pull request (review R-6; the 2a decision half built) | 29 |
| C27 | The publisher does not enforce the feed's 16 MiB bound | 39 |
| C28 | Contract: about 20 of 26, 17 of 22 and 81 of 86 schema constraints have no must-refuse fixture; no fixture for a duplicate label name | 47 |
| C29 | `monkeypatch.undo()` in `test_a_start_that_cannot_rewrite_a_manifest_still_serves` switches the feed guard off for the rest of that test | 50 |
| C30 | `test_one_function_writes_a_feed` matches only the alias `as_v2_document` | 50 |
| C31 | Chunk 12's three unmeasured claims: labels matched by accessible name in `expect_walls_offered`; the negative lookahead for "said exactly once"; whether `to_be_disabled` and `is_disabled` treat `aria-disabled` alike | 51 |
| C32 | `boundary-patterns.md` still says "do not rely on the type checker" | 54 |
| C33 | `CLAUDE.md` says `testament run --json` runs "all four" suites | 29 |
| C34 | Old backlog items REL-M5X8 (a mistyped `ART_ROOT` bootstraps an empty catalogue) and SEC-K3V9 (no Host/Origin check on `/mcp`), to verify and close or file | 54 |
| C35 | A fallback caused by a truly unreachable pool (the not-accepted path) has not been seen on GitHub | 52 (its acceptance) |
| C36 | The real-Player test's docker path (`ARRT_SERVER_IMAGE`) has never run | Dropped from chunks: it runs only on a pull request into `main`; the release's operator checklist (55) |
| C37 | The Player prints a plain-text line among its JSON journal lines | Dropped: Arrt Player's, for its next plan (54 tells its coordinator) |
| C38 | A `file` label-output kind (the Player's file label reports itself as `epaper`) | Dropped: nothing reads the kind to decide anything, and a new value loosens a writer's obligation, which `test_released.py` makes a recorded decision; revisit when the Player asks |
| C39 | The OpenRouter drift probes (#150) stay red monthly for want of a key | Dropped from chunks: an owner's act (provision the key or rule that the paid probes run by hand); asked with Q4 |
| C40 | `drift-freshness.yml` needs one manual dispatch after this reaches `main` | The operator's checklist (55) |
| C41 | The private homelab restore notes need the journal step | Dropped: the owner's private repository |
| C42 | #307, `list_exclusions()` scanned at about eight sites | Third part, with the view models, where one answer per entity is built |
| C43 | #371's second case (a curation test) | Dropped: stays on #371, outside the browser conversion; no 2b chunk owns its file |
| C44 | A fork's pull request always ends "Nothing ran" and could never pass a required check | The operator's checklist (55), with branch protection |
| C45 | A work only a plugin refused at load might hold is recorded "not held", by design | Dropped: informational for the owner, by design |
| C46 | The 2a plan's chunk-08 verification line lacked `-m player_e2e` | Dropped: done (2a's dated note) |
| C47 | Branch protection on `develop` and `main` (ruling 4) | The operator's checklist (55); 29 changes what the check runs, not its name |
| C48 | The fallback steps' time limits were guesses | Dropped: measured on #446's first run (governance 42 s, curation 5 m 19 s, contract 2 s), inside their limits |
| C49 | Q1(c)'s forbidden-columns extension of `test_catalogue_store.py` | 54, conditional on the ruling |
| C50 | What a curator is not told (2a Chunk 07): a reader's fault reads as an ordinary fetch failure; a finished Get with a pending work carries no reason; the could-not-be-asked count exists only in a description string; phase two's message names plugin ids, not museums | 32 (the first and third), 33 (the second and fourth) |
| C51 | `api-contract.md`'s HTTP rows for 2b's routes, and the 2a plan's § Wave 2b superseded by this plan | 54 |

## The drafted chunks: what 2a changed, and what this plan did

| Draft | What was found at `aed12703` | Here |
|---|---|---|
| 30 | `ScreenState` and `display_state_of` exist and `/api/walls` serves them; `/api/clients` and `/api/health` do not; no Player state; `settings_url` read nowhere; the health route's test is `test_browser_surface.py`, not `test_healthz.py` (which tests `/healthz`) | Shrunk to what is missing; Owns gains `reports.py`, `clients.py`, `container.py`; ceiling corrected |
| 31 | No screen quotes the vocabulary; Status reads the superseded fields; the "has not reported" assertions are in four files, not two, and their fixture has a Player | Owns names the twelve browser files; the fixture's shape is in scope |
| 32 | `FetchStatus` has three values; interface 1.5; widening is automatic (`durable.py`), so no migration step; a new value in the existing column would break an older release | Outcome in a new column (corrected DECISION); Owns gains `pool.py`, `runner.py`, `reading.py`, `providers.js`, the plugin fixtures |
| 33 | The look already answers per source; the wait is phase two's; the in-memory counts exist and reset on restart | The DECISION corrected to phase two; Owns gains `phase_two.py`, `runner.py`, `SourcePluginOut` |
| 34 | Hang only on a work and a theme; the toolbar is built in `selecting.js`; the who-sees sentence was fixed in wave 1 | As drafted, tests corrected |
| 35 | The generation lookup answered 404 (findings); `cost_usd` is NOT NULL; `spending.py` never touches the ledger | Corrected DECISION; Owns gains the ledger's writers and sums, loses `spending.py` |
| 36 | No `#spend` route; the budget line links to History | Listed under System (corrected DECISION); waits for 31 |
| 37 | The handler is in `app.py`; 21 not-found raises in 10 files; 86 asserts of 400; `config.py` imports more than three names; both executors use `asyncio.to_thread` | Shrunk to not found and the Library's name; configuration imports and both executors move to the third part |
| 38 | Reverses a recorded decision; collides with seven chunks in `api.py` and `models.py` | Moved to the third part (dropped:) |
| 39 | Reconcile is at start and per event, not periodic; the scheduler is the Library's | As drafted, plus the size bound (C27); `container.py` added; `feeds.py` is not new |
| 40 | `summarise`'s sentence is grammatical (`agree_partitive`) and pinned on purpose; the hang dialog's promise was fixed in wave 1; the body cap exists (256 KiB), the output cap does not; history by work needs the store's query | `summarise` item dropped (premise false); comment words to the third part; server sentences' words to 37; Owns gains the history query's path and `access.py` |
| 41 | Numbers formatted four ways, not two; about sixteen "collection" strings | As drafted, Owns made exact; gains C15 |
| 42 | `test_deployment_values.py` is a leak scanner and cannot hold the compose shape | A new test of the example's shape |
| 43 | `PictureStore` is already injected; areas undeclared; the prototype-scale test is also long | Two services, defaults kept so construction sites are untouched; the browser seeding item to the third part |
| 44 | As drafted | Owns gains the import-boundary test |
| 45 | The budget is the client's; `ASK_SCOPE` holds no wall act; HTTP carries the same `work_id` names | Split: 45 the break, 53 the additive twins (corrected DECISION) |
| 46 | 33 dates and 4 issue numbers in module docstrings, not 136 and 21 | Moved to the third part (dropped:) |

## What waits for the owner

- **Q1 (four norm texts):** nothing here depends on it. If the owner rules before 54 is
  dispatched, 54 amends the four norms with a dated note each and extends
  `test_catalogue_store.py`'s forbidden-columns check for (c) (C49); if not, 54 lists them
  as still open in the change record.
- **Q2 (hanging for a duration; a wall-side entry):** 34 builds hang on a selection only,
  which the ruled IA already asks for. Neither half of Q2 is in this plan.
- **Q3 (which settings a household can set, and where):** nothing here touches it.
- **Q4 (which runners may run this repository; the CI key's ceiling):** 29 does not depend on
  it, but it makes the required check run a real Player on whichever runner the pool picks;
  the coordinator should put Q4 again before branch protection goes on. #150 (C39) is asked
  with it.

## What moves to a third part

Each is whole and nothing in 2b begins it, so moving it leaves nothing half built:

- **The surface's shape (draft 38):** view models per entity, whose first question is whether
  to reverse the 2026-07-27 Decision Log; `api.py` by resource router; one mat act at the
  service layer with every MCP name unchanged (ruling 3's one break is 45's); the N+1 reads
  if measured; the `DisplayService` facade's removal; #307 (C42).
- **The docstring sweep (draft 46)** and the "display plane" and "curation plane" words left
  in about 28 comment lines in 15 files (audit-1 M9b's remainder).
- **Configuration imports no service** (audit-2 M12): more than the audit's three names, and
  types in `runner.py`, `settings.py` and the quality module move with it.
- **Ask's and MCP's executors** (audit-2 M10), after the measurement the finding is
  conditional on; the two halves together.
- **The browser tests that seed a time from `datetime.now`** (#438's remainder): their files
  are the ones 31, 34 and 41 rewrite here.

## Chunks

### Chunk 28: Contract 1.2.0 frozen beside the others

- **Type:** code
- **Exposed API:** the Player contract (`arrt-contract`)
- **Closes:** C25: `player-contract.md` § The package ("a release is copied into
  `contract/released/<version>/` when it is cut"), owed since `contract-v1.2.0` was cut on
  the merge commit of #446.
- **Owns:** new `contract/released/1.2.0/` (its fixtures with their index, its routes and
  its `sha256.json`) and `contract/tests/test_released.py`.
- **Must not touch:** any other file under `contract/` (47's), `contract/pyproject.toml`'s
  version (47 moves it).
- **Deliverables:**
  - The copy, from the tag and nothing else: `contract/fixtures/` and `contract/routes.json`
    as they are at `contract-v1.2.0`, and a `sha256.json` in the shape of
    `contract/released/1.1.0/sha256.json` (`_about`, `version`, `tag`, the commit the tag
    resolves to, `files`), written once.
  - `test_released.py`: `test_the_releases_a_player_may_pin_are_here` names 1.2.0 as the
    latest tag; and a new guard: **every release `player-contract.md` § Releases lists with a
    version below the package's own has a frozen copy**, read through `specification()`. It
    bites when the version moves past a release that was never copied, which is the next
    minor's first commit (47's).
- **Acceptance:**
  1. The suite passes with 1.2.0 frozen; report how many parametrised cases 1.2.0 added.
  2. Each copied file is byte-identical to `git show contract-v1.2.0:contract/<path>`
     (return the comparison); changing one byte of one copied fixture turns
     `test_each_frozen_file_is_the_bytes_it_was_when_it_was_copied` red.
  3. The new guard red with `contract/released/1.2.0/` removed and the package's version set
     to 1.3.0 (a re-break, reverted), naming 1.2.0; green with both restored.
  4. The guard's parser is tested on § Releases' own lines, copied from the file (lesson 1),
     and on a line it must not read as a release.
- **Verification ceiling:** `testament run --json=summary --suite contract --
  contract/tests/test_released.py`; `testament run --json=summary --suite governance` (it
  adds tracked files).
- **Model:** Sonnet-class, high: a mirror of how 1.1.0 was copied.
- **Waits for:** —.

### Chunk 29: The real-Player test, a suite of its own, on every pull request

- **Type:** code
- **Closes:** C26 (review R-6: the 2a decision "the pool tests the shipped pair on every
  server change" is half built), C17 (the header's pytest internal), C33 (`CLAUDE.md`'s
  "all four").
- **Owns:** `.testament.toml` (a new `[suites.player]` only), `.github/workflows/tests.yml`
  (one fallback step for the new suite and the header comment's suite list only),
  `.github/scripts/pool_or_fallback.py` (the headlines and messages that name the suites;
  nothing of the decision logic), `tests/test_ci_fallback.py`,
  `tests/test_default_suite_ci_scope.py`, `arrt/tests/player_e2e_header.py`,
  `arrt/tests/unit/test_player_e2e_header.py`, `arrt/tests/conftest.py` (the report-header
  hook only), `docs/testing.md` (§ The real-Player test, and the suite list in its CI
  paragraph), `CLAUDE.md` (the dev-commands paragraph's suite list only).
- **Must not touch:** the pool step, its deadlines and the browser job in `tests.yml`;
  `classify`, `drive` and `fallback_is_earned`; `.github/workflows/image.yml` (its `player`
  job, the docker path, stays as it is); the body of `arrt/tests/system/test_a_real_player.py`;
  `arrt/pyproject.toml` (the addopts keep deselecting it from every other run).
- **Found at HEAD:** `player_e2e` is deselected by `arrt/pyproject.toml`'s addopts and run
  unasked only by `image.yml` on a pull request into `main`; `tests.yml` runs `testament run`
  with no `--suite`, so a suite added to the manifest is in the required check the day it is
  added; `fallback_plan` runs every suite with no `requires` on GitHub's runner and
  `assert_tests_ran.py --suites-from .testament.toml` wants a report from each. No pool
  runner label stands for "reaches GitHub", and every runner did on 2026-11-19.
- **Deliverables:**
  - `[suites.player]`: the curation suite's command with `-m player_e2e`, selecting
    `arrt/tests/system/test_a_real_player.py`, no `requires`; its comment says why it is a
    suite (the DECISION) and what it costs.
  - The fallback step for it ("Fallback: the real-Player suite, here"), with a time limit, and
    the job's ceiling still the sum of its steps' (`tests/test_ci_fallback.py` holds the sum).
  - The header: says on every curation run that the real-Player test runs as the `player`
    suite and how to run it by hand, decided through **public pytest hooks only** (for
    example, after collection, from what was collected or deselected), never `_pytest`.
  - `docs/testing.md` and `CLAUDE.md`: five suites; `--suite player`; what the required check
    now runs.
- **Implicit guarantees of what it replaces** (deselection by default, and only `image.yml`
  running it), each with the test that holds it: (a) the curation suite never needs GitHub —
  a test that the curation command never selects `player_e2e`; (b) a pool outage never blocks
  a merge — the fallback runs the suite (`tests/test_ci_fallback.py`); (c) the image's test
  stage never runs it, having no git — `image.yml` untouched, `tests/preferences/test_test_image.py`
  green; (d) a bare `cd arrt && uv run pytest` reaches no network — the addopts unchanged, a
  test reads them.
- **Acceptance:**
  1. With the suite added and no fallback step, `test_a_manifest_suite_the_fallback_forgets_is_refused`
     (or its successor) is red, naming `player`; green with the step. Return the red.
  2. A new test: the player suite selects exactly the one test with `-m player_e2e`, and the
     curation suite's command does not select it — red when the suite's `-m` is removed, red
     when `player_e2e` leaves the addopts' exclusion.
  3. `test_player_e2e_header.py` red when the test module's `pytestmark` loses `player_e2e`
     (the header would lie), and red when `player_e2e_header.py` imports from `_pytest` (a
     test that reads the module's imports).
  4. `testament run --json=summary --suite player` passes on the pool (one test). The stderr
     lines a multi-suite run prints for the new suite are copied from an observed run into
     the fallback driver's tests, and its patterns are shown to read them (lesson 1).
  5. **Seen on a real pull request (the coordinator's, at integration):** the 2b pull request,
     opened as a draft once 29 is merged, shows in "Lint, then every suite"'s log
     `[player] request <id> accepted` and a `player` suite with one passed test in the
     report; and a scratch pull request whose `arrt/tests/system/player-ref.txt` names a
     commit that does not exist turns the required check red by name, with no fallback step
     run. Both runs' addresses go in the integration entry.
- **Rewritten assertions:** the header's expected text in `test_player_e2e_header.py`; any
  test pinning four suites. Each listed in the report.
- **Reads outside arrt/:** the governance tests read `.testament.toml`, `tests.yml`, `CLAUDE.md`.
- **Records owed:** `observability-strategy.md`'s CI row (the suite list); the operator's
  checklist (the check now waits for the pair).
- **Verification ceiling:** `testament run --json=summary --suite governance --
  tests/test_ci_fallback.py tests/test_default_suite_ci_scope.py tests/test_assert_tests_ran.py
  tests/test_actions_pinned.py`; `testament run --json=summary --suite curation --
  arrt/tests/unit/test_player_e2e_header.py`; `testament run --json=summary --suite player`
  once; `actionlint`; the governance suite whole (it edits tracked configuration).
- **Model:** Opus-class, high: it changes what CI's required check runs and its fallback, the
  place 2a's review fix went wrong.
- **Waits for:** —. Kept apart from every other CI change: 52 waits for it.

### Chunk 30: One health model — the server

- **Type:** code
- **Exposed API:** `/api` (the walls, clients and health routes)
- **Closes:** audit-5 F4 and audit-6 3 (the server half), the failed-fetches half of audit-6 3,
  audit-5 F6b's server half (`settings_url` read, checked and served).
- **Found at HEAD:** `ScreenState` and `display_state_of` (`arrt/src/arrt/programming/display_state.py`) are
  the wall-state model and the walls route serves them; the clients and health routes do not
  (the health route carries each wall's raw heartbeat); there is no Player-state model;
  `settings_url` is read nowhere under `arrt/src`; `describe_wall_status`
  (`arrt/src/arrt/programming/reports.py`) calls a wall with no Player one that "has not reported"; the
  failed count exists only on the acquisitions route, with no age; `HealthService` is built
  in `arrt/src/arrt/services/container.py` with no queue.
- **Owns:** `arrt/src/arrt/services/health.py`, `arrt/src/arrt/programming/display_state.py`,
  new `arrt/src/arrt/programming/player_state.py`,
  `arrt/src/arrt/programming/client_heartbeat.py` (the `settings_url` intake),
  `arrt/src/arrt/programming/clients.py` (a client's state on its view),
  `arrt/src/arrt/programming/reports.py` (`survey_wall_status` and `describe_wall_status`
  only), `arrt/src/arrt/services/container.py` (`HealthService`'s construction only),
  `arrt/src/arrt/http/models.py` and `arrt/src/arrt/http/api.py` (the health, wall-state and
  client models and handlers), `arrt/tests/unit/test_display_state.py`,
  new `arrt/tests/unit/test_player_state.py`, `arrt/tests/unit/test_clients.py`,
  `arrt/tests/contract/test_client_surface.py`, `arrt/tests/integration/test_browser_surface.py`
  (its health and client cases), and `arrt/tests/unit/test_surface_parity.py` (exemption
  constants naming Chunk 53 only).
- **Must not touch:** `contract/` (47 adds the Player states' words; this chunk uses the keys
  the plan fixes); `arrt/src/arrt/mcp/` (53 gives MCP the twins); `arrt/src/arrt/http/static/` (31).
- **Deliverables:**
  - `PlayerState` with the DECISION's five keys, read from the client heartbeat and the token's
    state; each label output's own state, so a Player with several labels and no display is
    described (ruling 8).
  - The clients route: each Player's state and each output's. The health route: each wall's
    display state (from `display_state_of`, never the superseded fields), each Player's state,
    troubles derived only from states whose `setup` flag is false, and the failed-fetch count
    with the age of the newest (the queue handed to `HealthService` in `container.py`).
  - `describe_wall_status` says nothing of a wall with no Player as a fault.
  - The setup flags quoted in `display_state.py` and `player_state.py`, with a test
    parametrised over the package's states (the server cannot read the package at run time).
  - `settings_url` served on a client's view only when it passes the contract's check; the
    server's check run over every `settings_url` fixture of `client-heartbeat.v1`, valid and
    invalid.
- **Acceptance:**
  1. A wall with no Player: its state reads `unassigned` and it is no trouble on the health
     route, and `describe_wall_status` does not name it — red today.
  2. A heartbeat claiming `television_showing_art: true` with `display_state: dark` reads dark
     on the walls and health routes — red today on the health route.
  3. A `settings_url` of `javascript:alert(1)`, and each invalid fixture, is not served; each
     valid fixture is — red with the check removed.
  4. A Player with two label outputs and no display: each label has its own state — red if the
     model keeps one per Player.
  5. Three failed queue rows, the newest two hours old: the health route reads 3 and the age;
     none: no observation — red with the wiring removed.
  6. A quoted setup flag that differs from the package's turns the parametrised test red.
- **Records owed:** `observability-strategy.md` (the health reading's new fields);
  `api-contract.md` (the three routes); `data-model.md` (nothing persisted, said so).
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/unit/test_display_state.py arrt/tests/unit/test_player_state.py
  arrt/tests/unit/test_clients.py arrt/tests/unit/test_surface_parity.py
  arrt/tests/contract/test_client_surface.py arrt/tests/integration/test_browser_surface.py
  arrt/tests/integration/test_client_tools.py`.
- **Model:** Opus-class, high.
- **Waits for:** —.

### Chunk 31: One health model — the screens

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-5 F4 and audit-6 3 (the client half), audit-6 6 (the Walls card's layout),
  audit-5 F6b's link, C20.
- **Found at HEAD:** no client file quotes `contract/vocabulary.json`; Walls words its states in
  `BADGES` and `STATE_WORDS` (`arrt/src/arrt/http/static/screens/walls.js`) and says "No Player"; `arrt/src/arrt/http/static/screens/health.js`
  reads `television_reachable`, `television_showing_art` and `has_label_surface`;
  `arrt/src/arrt/http/static/core/status.js` makes a wall's absent report a trouble; the "has not reported" assertions
  for a wall with no Player are in four files, and their fixture builds a wall with a Player
  and no heartbeat, which is not the same shape.
- **Owns:** new `arrt/src/arrt/http/static/core/states.js`,
  `arrt/src/arrt/http/static/screens/walls.js`, `arrt/src/arrt/http/static/screens/clients.js`,
  `arrt/src/arrt/http/static/screens/health.js`, `arrt/src/arrt/http/static/core/status.js`,
  `arrt/src/arrt/http/static/core/sidebar.js`, `arrt/src/arrt/http/static/core/outputs.js`,
  `.prawduct/artifacts/information-architecture.md` (the Walls, Players, Status and top bar
  rows), `arrt/tests/unit/test_wall_state_words.py`, `arrt/tests/browser/conftest.py` (the
  wall fixture's no-Player shape only), and the browser files of those screens:
  `arrt/tests/browser/test_the_walls.py`, `arrt/tests/browser/test_walls_lead_with_the_work.py`,
  `arrt/tests/browser/test_setting_up_a_wall.py`, `arrt/tests/browser/test_editing_a_wall.py`,
  `arrt/tests/browser/test_displays_and_labels.py`, `arrt/tests/browser/test_scenes_on_walls.py`,
  `arrt/tests/browser/test_the_clients.py`, `arrt/tests/browser/test_the_health_panel.py`,
  `arrt/tests/browser/test_the_status_sources_table.py`, `arrt/tests/browser/test_the_debug_view.py`,
  `arrt/tests/browser/test_the_sidebar.py`, `arrt/tests/browser/test_shared_rules_and_phone.py`.
- **Must not touch:** `arrt/tests/browser/test_walls_last_and_next.py` (51's); the server.
- **Deliverables:** every screen draws a state's word and glyph from `states.js`, which quotes
  the package's words; Status reads the state, never the superseded fields; the Walls card
  holds at most one notice, chosen by state, and one filled act; the top bar and the System
  badge count faults and failed fetches (linking to Queue), never a setup step; the Players
  row's settings link is an href only when the server serves one, its text is text, and it
  carries `rel="noopener noreferrer"`.
- **Implicit guarantees of `STATE_WORDS`:** every state the server can send has a word on
  Walls, and a state with no word reads as "Not known" — `test_wall_state_words.py`, rewritten,
  holds both against the package, both ways.
- **Rewritten assertions:** `test_wall_state_words.py` (reads `states.js` and the package, not
  `STATE_WORDS`); "has not reported" for a wall with **no Player** becomes "No Player yet" in
  `test_the_sidebar.py`, `test_the_health_panel.py` and `test_shared_rules_and_phone.py`, with
  the fixture given a no-Player wall (a wall with a Player and no report still says it has not
  reported); `test_walls_lead_with_the_work.py`'s `No Player\s*$` becomes "No Player yet". Each
  listed in the report.
- **Acceptance:**
  1. `test_wall_state_words.py` red when one word in `states.js` differs from the package (for
     example "No Player"), and red when the package gains a state `states.js` lacks.
  2. A wall with no Player puts nothing on the top bar or the System badge — red today.
  3. A wall with a Player and no report still does.
  4. Status shows "Screen off" for a heartbeat claiming the television shows art with
     `display_state: dark` — red today.
  5. A Player whose report carries no settings address has no link; one whose address the
     server served has a link with that rel; a script in the address never reaches an href.
  6. Failed fetches put a count on the badge that opens Queue — red with the count removed.
  Each owned browser file passes on the pool.
- **Records owed:** the IA rows (its own); `operator-verification.md` (the Walls card's look).
- **Verification ceiling:** `testament run --json=summary --suite browser --` the twelve files
  above; `testament run --json=summary --suite curation -- arrt/tests/unit/test_wall_state_words.py`.
- **Model:** Opus-class, high.
- **Waits for:** 30, 47.

### Chunk 32: The plugin host's second half — the answers kept apart

- **Type:** code
- **Exposed API:** the source plugin interface (1.6)
- **Closes:** audit-4 14 (#318), audit-4 4's second half (with the sources planner), the
  Queue's grouping by message text, C50's first and third items.
- **The persisted format, its questions first:** the outcome answers (1) the queue: retry when,
  and how soon; (2) Queue: how to group "why these works have no picture" without per-work text;
  (3) Status: which plugin is not answering; (4) MCP and the causes route: the same groups;
  (5) a migration: what an existing `failed` row becomes (it stays `failed`, unclassified);
  (6) an older release: what it reads (the coarse status, unchanged).
- **Found at HEAD:** `FetchStatus` is `ok`, `partial_tiles`, `failed`
  (`arrt/src/arrt/persistence/records.py`); every non-success ends in `_record_failure`
  (`arrt/src/arrt/library/acquisition/service.py`); a reader's "no image" and a search failure differ only
  in prose; interface 1.5 (`arrt/src/arrt/library/sources/plugin.py`); the pool's answers are `AskOutcome`
  and `PoolAnswer.unreachable`, so "pages gone" cannot be told from "not asked"; Queue groups
  by the message with the work's name scrubbed out (`arrt/src/arrt/library/acquisition/queue.py`). Widening
  adds a nullable column with no step (`arrt/src/arrt/persistence/durable.py`); the shape generation is not
  raised for an added column.
- **Owns:** `arrt/src/arrt/persistence/records.py` (the outcome enum, `QueuedAcquisition`),
  `arrt/src/arrt/persistence/sqlite.py` (the outcome column's DDL and reads),
  `arrt/src/arrt/library/acquisition/service.py`, `arrt/src/arrt/library/acquisition/queue.py`,
  `arrt/src/arrt/library/sources/plugin.py`, `arrt/src/arrt/library/sources/loading.py`,
  `arrt/src/arrt/library/sources/reading.py`, `arrt/src/arrt/library/sources/__init__.py` (its
  exports), `arrt/src/arrt/library/discovery/images.py`,
  `arrt/src/arrt/library/discovery/phase_two.py`, `arrt/src/arrt/library/discovery/pool.py`
  (`AskOutcome`), `arrt/src/arrt/library/services/runner.py` (`WorkOutcome` only),
  `arrt/src/arrt/http/static/screens/activity.js` (Queue's grouping),
  `arrt/src/arrt/http/static/core/providers.js` (the outcome words), `arrt/src/arrt/http/api.py`
  and `arrt/src/arrt/http/models.py` (the causes route and the queue's models),
  `docs/source-plugins.md`, `.prawduct/artifacts/source-plugins.md`, `arrt/tests/plugin_fakes.py`,
  `arrt/tests/fixtures/plugins/misbehaving/`, and the tests:
  `arrt/tests/unit/test_acquisition_service.py`, `arrt/tests/unit/test_acquisition_queue.py`,
  `arrt/tests/unit/test_source_plugins.py`, `arrt/tests/unit/test_image_pool.py`,
  `arrt/tests/unit/test_phase_two_run.py`, `arrt/tests/unit/test_phase_two_engine.py`,
  `arrt/tests/unit/test_client_vocabulary.py` (the outcome words only),
  `arrt/tests/integration/test_acquisition_routes.py`,
  `arrt/tests/integration/test_a_misbehaving_plugin.py`,
  `arrt/tests/browser/test_acquisition_states.py`, and `arrt/tests/unit/test_surface_parity.py`
  (exemptions naming Chunk 53).
- **Must not touch:** `arrt/src/arrt/mcp/` (53); `arrt/src/arrt/persistence/migrations.py` unless a written
  step proves necessary (then the shape generation and `catalogue-generations.json` are this
  chunk's, and the report says why).
- **Deliverables:** the DECISION's outcomes in their own column, the coarse status unchanged;
  the retry rule; interface 1.6 with `link_gone`; Queue grouped by outcome and source; the
  could-not-be-asked count a field, not only a sentence.
- **Implicit guarantees of "every non-success is `failed`":** a failed work is retried on the
  schedule `queue.py` documents (1 h, 1 d, 3 d, then given up) — the new rule keeps that for
  `failed` and is tested per outcome; an older release reads every non-success as `failed` —
  a test reads a written row as v0.11.0's `FetchStatus` would.
- **Acceptance:**
  1. The misbehaving plugin's reader fault reads `faulted`, not `failed` — red today
     (`test_a_misbehaving_plugin.py` pins it as a fetch failure: a rewritten assertion).
  2. A finder answering `link_gone` settles the work for that source — red today.
  3. A plugin declaring 1.5 loads unchanged; one declaring 1.7 is refused.
  4. The retry rule, parametrised over the enum: red when a member has no rule.
  5. Two works failing for one cause in two wordings group as one in Queue — red today.
  6. A row with an outcome has a coarse status in `ok`, `partial_tiles`, `failed` — red if a
     new value is written there.
  7. `test_client_vocabulary.py` red when an outcome has no words.
  8. A test reads `docs/source-plugins.md`'s answers table and its interface version against
     the code (today it says "(1, 5)" by hand) — red when they differ.
- **Rewritten assertions:** `test_a_misbehaving_plugin.py`'s reader-fault case; listed.
- **Records owed:** `observability-strategy.md` (the outcome on the acquisition events);
  `data-model.md` (the column); the sources coordinator (interface 1.6).
- **Verification ceiling:** `testament run --json=summary --suite curation --` the owned unit,
  integration and contract test files; `testament run --json=summary --suite browser --
  arrt/tests/browser/test_acquisition_states.py`; the governance suite whole if a tracked
  fixture file is added.
- **Model:** Opus-class, high.
- **Waits for:** —.

### Chunk 33: Phase two answers within a window, and each search is recorded

- **Type:** code
- **Closes:** #313 (a durable record of each search; audit-4 3a's remainder), phase two's wait
  for every source, C50's second and fourth items.
- **The persisted format, its questions first:** a search record answers (1) Status after a
  restart: has this plugin answered anything in N searches; (2) phase two: is any source still
  owed an answer for this work; (3) Sources' yields: what each source contributed; (4)
  retention: the newest per work and source (#308's rule when it lands); (5) the key: the
  work's id and the source's name, never a URL (`data-model.md` § Direction).
- **Found at HEAD:** the look answers per source within `LOOK_HOLD_SECONDS`
  (`arrt/src/arrt/library/services/look.py`); phase two's pool waits for the slowest source's deadline plus
  5 s (`arrt/src/arrt/library/discovery/pool.py`); the unasked and answered counts live in memory
  (`arrt/src/arrt/library/sources/loading.py`) and reset on restart, and `SourcePluginOut` carries none of
  them; no search is persisted.
- **Owns:** `arrt/src/arrt/library/discovery/pool.py`, `arrt/src/arrt/library/discovery/phase_two.py`,
  `arrt/src/arrt/library/services/runner.py` (the could-not-be-asked counting only),
  `arrt/src/arrt/library/sources/loading.py` (the counts read from the record),
  `arrt/src/arrt/persistence/discovery.py`, `arrt/src/arrt/persistence/sqlite_discovery.py`
  (the new table), `arrt/src/arrt/persistence/discovery_records.py` (the new record),
  `arrt/src/arrt/services/health.py` (the plugin section only),
  `arrt/src/arrt/http/models.py` and `arrt/src/arrt/http/api.py` (`SourcePluginOut` only), and
  the tests: `arrt/tests/unit/test_image_pool.py`, `arrt/tests/unit/test_discovery_runner.py`,
  `arrt/tests/unit/test_phase_two_run.py`, `arrt/tests/unit/test_discovery_store.py`,
  `arrt/tests/integration/test_a_misbehaving_plugin.py`,
  `arrt/tests/integration/test_source_plugins_surface.py`, and
  `arrt/tests/unit/test_surface_parity.py` (exemptions naming Chunk 53).
- **Must not touch:** `arrt/src/arrt/library/services/look.py` (it already answers per source);
  `arrt/src/arrt/mcp/`.
- **Deliverables:** the corrected DECISION; Status's plugin counts read from the record; a
  finished Get names the source for a work no source could be asked about, and phase two's
  message names the museum, not the plugin id.
- **Acceptance:**
  1. A plugin answering after 31 s does not hold phase two's answer for the others — red today;
     its late answer is in the record, and the next pass reads it.
  2. After a restart, Status's "not asked in N searches" survives — red today.
  3. A Get where every work was unreachable at one source names that source — red today.
  4. The table holds no URL column (a test of its DDL); two searches of one work at one source
     leave one row.
- **Records owed:** `data-model.md` (the table, its questions, its retention);
  `observability-strategy.md`.
- **Verification ceiling:** `testament run --json=summary --suite curation --` the owned test
  files.
- **Model:** Opus-class, high.
- **Waits for:** 30, 32, 35.

### Chunk 34: Hang on any selection

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-5 F9's selection half (hanging for a duration and a wall-side entry are Q2).
- **Found at HEAD:** Hang… is on a work (`arrt/src/arrt/http/static/screens/work.js`) and a theme (`arrt/src/arrt/http/static/screens/theme.js`)
  only; the selection toolbar is built in `arrt/src/arrt/http/static/core/selecting.js`; `arrt/src/arrt/http/static/core/selection.js` already
  says the IA gives Hang… to Artist, Search and Topic; the dialog's who-sees line is shared
  from `arrt/src/arrt/http/static/core/hanging.js` (wave 1 fixed its promise for a wall no Player shows).
- **Owns:** `arrt/src/arrt/http/static/core/selecting.js`,
  `arrt/src/arrt/http/static/core/selection.js`,
  `arrt/src/arrt/http/static/screens/collection.js` (its selection toolbar only),
  `arrt/src/arrt/http/static/screens/artists.js`, `arrt/src/arrt/http/static/screens/search.js`,
  `arrt/src/arrt/http/static/screens/topics.js`, `.prawduct/artifacts/information-architecture.md`
  (the selection toolbar's rows), `arrt/tests/browser/test_one_selection_model.py`,
  `arrt/tests/browser/test_list_toolbars_agree.py`, and
  new `arrt/tests/browser/test_hanging_a_selection.py`.
- **Deliverables:** *Hang…* in every selection's toolbar (Artworks, an Artist's works, Search,
  a Topic's held works), through `hang_selection`; an Artists selection hangs their held works.
- **Acceptance:**
  1. On each of the four, *Hang…* sends `hang_selection` with the selected ids (asserted on the
     request) — red today (no control).
  2. An Artists selection sends only held works — red if a work with no picture is sent.
  3. Select stays last, on the right (ruling 6): `test_list_toolbars_agree.py` red if Hang… is
     put after it.
- **Rewritten assertions:** `test_one_selection_model.py`'s control set, two-row fit, left side
  and topic layout; `test_list_toolbars_agree.py`'s control list; each listed.
- **Records owed:** the IA rows (its own); `operator-verification.md` (the toolbar at phone width).
- **Verification ceiling:** `testament run --json=summary --suite browser --
  arrt/tests/browser/test_hanging_a_selection.py arrt/tests/browser/test_one_selection_model.py
  arrt/tests/browser/test_list_toolbars_agree.py`.
- **Model:** Sonnet-class, high.
- **Waits for:** —.

### Chunk 35: Spend — the paid call that fails after it was sent

- **Type:** code
- **Foreign API:** OpenRouter (chat completions; the generation lookup)
- **Closes:** audit-2 S5, including Ask's reply cancelled after it was sent.
- **The persisted format, its questions first:** a spend row answers (1) the month's total and
  how sure it is; (2) a run's cost; (3) Ask's reply cost; (4) which calls' cost is unknown and
  why; (5) what an older release makes of a row this one writes.
- **Found at HEAD:** phase one turns an `OpenRouterError` into an `EngineFailure` with no spend
  (`arrt/src/arrt/library/discovery/phase_one.py`); the mat fallback carries a cost only from a completed
  answer (`arrt/src/arrt/library/acquisition/mat.py`); Ask's `_record` returns early on no cost
  (`arrt/src/arrt/ask/agent.py`); `_read_completion` never reads the response id
  (`arrt/src/arrt/library/discovery/openrouter.py`); `cost_usd` is `TEXT NOT NULL` (`arrt/src/arrt/persistence/sqlite_discovery.py`);
  the ledger is written by `record_spend` and summed in `arrt/src/arrt/library/services/discovery.py` and
  `arrt/src/arrt/library/services/unattended.py`; `arrt/src/arrt/library/services/spending.py` reads the provider's key and
  never the ledger.
- **Owns:** `arrt/src/arrt/library/discovery/openrouter.py`,
  `arrt/src/arrt/library/discovery/phase_one.py`, `arrt/src/arrt/library/acquisition/mat.py`,
  `arrt/src/arrt/library/acquisition/preparation.py` (its spend calls only),
  `arrt/src/arrt/library/services/discovery.py` (`record_spend`, `run_cost`, `spend_in_month`,
  `_spend_total`), `arrt/src/arrt/library/services/unattended.py`,
  `arrt/src/arrt/library/services/runner.py` (`SpendReport` only), `arrt/src/arrt/ask/agent.py`
  (`_record` only), `arrt/src/arrt/app.py` (`_record_ask_cost` only),
  `arrt/src/arrt/persistence/discovery_records.py` (`SpendRecord`),
  `arrt/src/arrt/persistence/sqlite_discovery.py` (`spend_records`),
  `arrt/src/arrt/persistence/discovery.py` (the store's spend methods),
  `arrt/src/arrt/http/models.py` and `arrt/src/arrt/http/api.py` (`SpendReport` only),
  `.prawduct/artifacts/openrouter-api-findings.md` (what step 0 read), and the tests:
  `arrt/tests/unit/test_openrouter_client.py`, `arrt/tests/unit/test_phase_one_engine.py`,
  `arrt/tests/unit/test_mat_engine.py`, `arrt/tests/unit/test_ask_agent.py`,
  `arrt/tests/unit/test_discovery_store.py`, `arrt/tests/unit/test_discovery_runner.py`,
  `arrt/tests/unit/test_preparation.py`, `arrt/tests/unit/test_unattended.py`,
  `arrt/tests/integration/test_budget_surface.py`, and `arrt/tests/unit/test_surface_parity.py`
  (exemptions naming Chunk 53).
- **Must not touch:** `arrt/src/arrt/library/services/spending.py`; `arrt/src/arrt/mcp/`; any
  `live_api` test (the operator's).
- **Deliverables:** step 0, verify-api: read `openrouter.py`'s request path, what a timeout
  (`COMPLETION_TIMEOUT_SECONDS`) leaves the client holding, and the findings' record of the
  lookup; record in `openrouter-api-findings.md` what was read, and that no paid probe was run
  (the operator's, in 55's checklist). Then the corrected DECISION.
- **Acceptance:**
  1. A phase-one call that times out after it was sent records a row with `cost_status`
     unknown, its model and its run — red today.
  2. The same for the mat's fallback call and for an Ask reply cancelled after it was sent.
  3. The month reads "at least $X, and N calls whose cost is unknown" — red today.
  4. A row written before this change reads as known (the widening's default) — red if the
     default is unknown.
  5. A row this change writes, read as v0.11.0 reads it, sums as $0.
- **Records owed:** `data-model.md` (the column and its questions); `nonfunctional-requirements.md`
  § Cost visibility (what the ledger can and cannot say); `observability-strategy.md`.
- **Verification ceiling:** `testament run --json=summary --suite curation --` the owned test
  files.
- **Model:** Opus-class, high.
- **Waits for:** —.

### Chunk 36: Spend — a page under System

- **Type:** code
- **Visual change:** yes
- **Closes:** audit-6 10 and audit-5 F12 (the page halves).
- **Found at HEAD:** no `#spend` route; the budget line links to `#history?kind=gets`
  (`arrt/src/arrt/http/static/core/spend.js`), which `test_spend.py` asserts.
- **Owns:** new `arrt/src/arrt/http/static/screens/spend.js`,
  `arrt/src/arrt/http/static/app.js` (the route only), `arrt/src/arrt/http/static/core/route.js`
  (its entry only), `arrt/src/arrt/http/static/core/spend.js`,
  `arrt/src/arrt/http/static/core/sidebar.js` (System's list and the budget line only),
  `arrt/src/arrt/http/static/screens/health.js` (one link only),
  `.prawduct/artifacts/information-architecture.md` (System › Spend),
  `tests/preferences/test_screen_tables.py` (the screen's name), `arrt/src/arrt/http/api.py` and
  `arrt/src/arrt/http/models.py` (a spend route only if the months are not served today),
  new `arrt/tests/browser/test_the_spend_page.py`, and `arrt/tests/browser/test_spend.py`.
- **Deliverables:** months, each month's categories and Gets, and the calls whose cost is
  unknown (35's); listed under System; reached from the budget line and from Status.
- **Rewritten assertions:** `test_spend.py`'s budget-line link (History → Spend), each listed.
- **Acceptance:**
  1. The page lists 35's unknown-cost calls apart, with the month's "at least" total.
  2. `test_screen_tables.py` red when the IA's System table lacks the row, or the sidebar lacks
     the item.
  3. The budget line opens `#spend` (rewritten test red on the old link).
- **Reads outside arrt/:** the governance test reads the IA.
- **Verification ceiling:** `testament run --json=summary --suite browser --
  arrt/tests/browser/test_the_spend_page.py arrt/tests/browser/test_spend.py
  arrt/tests/browser/test_the_sidebar.py`; `testament run --json=summary --suite governance --
  tests/preferences/test_screen_tables.py`.
- **Model:** Sonnet-class, high.
- **Waits for:** 31, 35.

### Chunk 37: Not found is 404, and a refusal names the Library

- **Type:** code
- **Exposed API:** `/api`
- **Closes:** audit-2 M8; rulings 1 and 2 in the sentences the server sends a person.
- **Found at HEAD:** the handler is `app.py`'s, delegating to `service_error_response` in
  `arrt/src/arrt/http/api.py`, which answers every `ServiceError` with 400; about 21 not-found raises in ten
  service modules; MCP turns any `ServiceError` into its failure shape (`arrt/src/arrt/mcp/server.py`), which
  a subclass leaves unchanged; 86 assertions of 400 in 32 test files.
- **Owns:** `arrt/src/arrt/services/errors.py` (`NotFound`), `arrt/src/arrt/app.py` (the handler),
  `arrt/src/arrt/http/api.py` (`service_error_response` only), every module that raises a
  not-found `ServiceError` (the raises only, listed by grep at dispatch: today
  `arrt/src/arrt/library/services/catalogue.py`, `arrt/src/arrt/programming/clients.py`,
  `arrt/src/arrt/library/services/discovery.py`, 48's lookups module,
  `arrt/src/arrt/programming/scenes.py`, `arrt/src/arrt/programming/access.py` and four more),
  the server's sentences naming the household's holdings, and the tests asserting 400 for a
  not-found.
- **Must not touch:** `arrt/src/arrt/mcp/`; the meaning of any other refusal.
- **Deliverables:** `NotFound(ServiceError)`, 404 on `/api`, 400 for every other refusal; each
  not-found raise converted; the server's sentences say *the Library* and *theme*, never the
  catalogue, the collection (for the household's) or playlist (ruling 1's one exception, the
  contract's field, stays).
- **Acceptance:**
  1. A wall that does not exist answers 404 in the error shape — red today (400).
  2. Deleting the default theme still answers 400.
  3. A guard: no `raise ServiceError(` with a not-found message is left under `arrt/src` (a test
     that reads the source and names the site) — red with one planted.
  4. An MCP tool called with an unknown id returns the same failure as before
     (`test_mcp_scenarios.py` unchanged and green).
  5. A grep of the returned sentences for "catalogue" and "collection" in the household's sense:
     before and after, in the report.
- **Rewritten assertions:** each 400 that meant not found becomes 404, listed by file.
- **Verification ceiling:** `testament run --json=summary --suite curation --` the test files it
  edits, `arrt/tests/integration/test_browser_surface.py` and `arrt/tests/contract/test_mcp_scenarios.py`.
- **Model:** Opus-class, medium: which refusals mean not found is a judgement at each site.
- **Waits for:** 30, 35, 39, 40, 43, 48.

### Chunk 38: The surface's shape — moved to a third part

- **Type:** doc-only
- Dropped (frontmatter): view models per entity reverse the 2026-07-27 Decision Log recorded in
  `.prawduct/artifacts/architecture.md` and quoted by `arrt/tests/unit/test_surface_parity.py`'s
  docstring; the router split collides with seven chunks' regions of `arrt/src/arrt/http/api.py`.
  § What moves to a third part names what goes with it.

### Chunk 39: The publisher's two promises: a periodic reconcile, a size bound

- **Type:** code
- **Closes:** audit-1 M7, C27.
- **Found at HEAD:** the full reconcile runs at start (`__main__.py` through `arrt/src/arrt/services/container.py`)
  and per event; nothing runs it periodically; the scheduler is the Library's
  (`arrt/src/arrt/library/services/scheduler.py`, a `Job` protocol, one job today); `transport.json` gives
  the feed a `max_bytes` the publisher does not enforce.
- **Owns:** `arrt/src/arrt/programming/feeds.py` (the reconcile's scheduled entry and the size
  check at publishing), `arrt/src/arrt/library/services/scheduler.py` (only if the `Job`
  protocol needs a field), `arrt/src/arrt/services/container.py` (the scheduler's jobs only),
  `arrt/tests/unit/test_scheduler.py`, `arrt/tests/unit/test_reconciliation.py`,
  `arrt/tests/unit/test_feed_publisher.py`.
- **New execution context:** a scheduled job. Logging (one INFO line a pass, with an `event`),
  the bulkhead the other jobs use, and shutdown's join are stated and tested; auth and
  correlation are inapplicable (no request), said so.
- **Deliverables:** a Programming job handed to the scheduler (never imported by the Library);
  a feed over the bound is not published, the last good one stays, and it is logged once with
  an event; the bound quoted from the package with a test (the server cannot read it at run time).
- **Acceptance:**
  1. A feed changed on disk behind the server's back is rewritten within one period — red today.
  2. A pass that raises does not stop the scheduler and is logged once.
  3. Shutdown joins the job.
  4. A feed over the bound is not written and the old one stays — red today.
  5. The quoted bound differs from the package's: red.
  6. `tests/preferences/test_seam_imports.py` stays green (the Library imports nothing of Programming).
- **Records owed:** `observability-strategy.md` (the pass's event; the bound's event);
  `architecture.md` (the job).
- **Verification ceiling:** `testament run --json=summary --suite curation -- arrt/tests/unit/test_scheduler.py
  arrt/tests/unit/test_reconciliation.py arrt/tests/unit/test_feed_publisher.py`;
  `testament run --json=summary --suite governance -- tests/preferences/test_seam_imports.py`.
- **Model:** Opus-class, medium.
- **Waits for:** 48, 50.

### Chunk 40: Small server items

- **Type:** code
- **Closes:** `DEPLOYMENT_REMEDIES` naming `DEZOOMIFY_PATH` and `ARTIC_USER_AGENT` on household
  pages; `nga.py`'s two hand-written temp-and-rename writers (onto `arrt/src/arrt/atomic.py`);
  a full disk inside `dezoomify-rs` showing only as an exit code; the cap on outputs one client
  may report (audit-8 F10's remainder; the body cap exists); `pictured_artwork_id` on the
  Artist, Topic and Work pages' registry rows (the server half); History filtered by work and a
  work's record naming the Get that brought it (audit-5 F18, the server half); C21; the one
  sentence a person reads that says "plane" (`art_root.py`).
- **Dropped from the draft, with reasons:** `ManifestBuild.summarise`'s "0 of 1 work … is" —
  the premise is false: the sentence is grammatical (`agree_partitive`) and pinned on purpose
  (`test_counting.py`, `test_browser_surface.py`), and the dialog's over-broad promise was fixed
  in wave 1 (`arrt/src/arrt/http/static/core/hanging.js`); the plane words in comments go to the third part; rulings 1
  and 2 in server sentences go to 37, which rewrites those lines.
- **Owns:** `arrt/src/arrt/library/acquisition/service.py` (`DEPLOYMENT_REMEDIES`),
  `arrt/src/arrt/library/sources/nga.py`, `arrt/src/arrt/library/acquisition/dezoomify.py`,
  `arrt/src/arrt/programming/client_heartbeat.py` (the output cap),
  `arrt/src/arrt/programming/access.py` (its two log lines), `arrt/src/arrt/art_root.py` (its
  sentence), `arrt/src/arrt/http/models.py` (the four registry-row models and `WorkOut`),
  `arrt/src/arrt/http/api.py` (the history route's parameter), the history query's path
  (`arrt/src/arrt/library/services/catalogue.py`, `arrt/src/arrt/persistence/catalogue.py`,
  `arrt/src/arrt/persistence/sqlite.py`, its history read only), and the tests that hold them:
  `arrt/tests/unit/test_acquisition_service.py`, `arrt/tests/unit/test_nga_source.py`,
  `arrt/tests/unit/test_acquisition_dezoomify.py`, `arrt/tests/unit/test_clients.py` (the cap),
  `arrt/tests/unit/test_history.py`, `arrt/tests/integration/test_history_surface.py`,
  `arrt/tests/integration/test_registry_pages.py`, and `arrt/tests/unit/test_surface_parity.py`
  (exemptions naming Chunk 53).
- **Acceptance:** each item red first: a remedy that names a setting on a household page; a
  rename by hand in `nga.py` (a test that its writes go through `atomic.py`); a `dezoomify-rs`
  that exits with a full disk reads "the disk is full" (from its stderr, copied from an
  observed run — lesson 1); a report of more outputs than the cap is refused by name; each
  registry row carries `pictured_artwork_id`; History by work returns that work's events only;
  a work's record names its Get; both log lines carry an `event`.
- **Records owed:** `observability-strategy.md` (the two events); `api-contract.md` (the history
  parameter, the fields). L6 of the ledger: the `live_binary` dezoomify probe is due at
  integration, by the operator.
- **Verification ceiling:** `testament run --json=summary --suite curation --` the owned test files.
- **Model:** Sonnet-class, high.
- **Waits for:** 30, 32.

### Chunk 41: Small client items

- **Type:** code
- **Visual change:** yes
- **Closes:** C3; the joiner's callers no test watches (`work.js`, the Walls "waiting" line,
  `clients.js`); the registry rows' thumbnails (the client half, after 40); numbers formatted
  one way through `arrt/src/arrt/http/static/core/counting.js` (audit-6 16: four ways today); the Work page linking its
  Get and its History (audit-5 F18, after 40); a second skip link past Artworks' facets
  (audit-6 22); Remove and Forget (audit-5 F14's UI half); rulings 1 and 2 in the client's copy
  (about sixteen strings); C15.
- **Owns:** `arrt/src/arrt/http/static/screens/walls.js`, `arrt/src/arrt/http/static/screens/work.js`,
  `arrt/src/arrt/http/static/screens/topics.js`, `arrt/src/arrt/http/static/screens/artists.js`,
  `arrt/src/arrt/http/static/screens/collection.js`, `arrt/src/arrt/http/static/screens/search.js`,
  `arrt/src/arrt/http/static/screens/health.js`, `arrt/src/arrt/http/static/screens/clients.js`,
  `arrt/src/arrt/http/static/screens/watches.js`, `arrt/src/arrt/http/static/screens/run.js`,
  `arrt/src/arrt/http/static/screens/theme.js`, `arrt/src/arrt/http/static/core/counting.js`,
  `arrt/src/arrt/http/static/core/badges.js`, `arrt/src/arrt/http/static/core/status.js`,
  `arrt/src/arrt/http/static/core/reviewing.js`, `.prawduct/artifacts/information-architecture.md`
  (the Work page row; § Vocabulary's Remove and Forget), and the browser files:
  `arrt/tests/browser/test_scenes_on_walls.py`, `arrt/tests/browser/test_the_walls.py`,
  `arrt/tests/browser/test_the_work_page.py`, `arrt/tests/browser/test_pages_for_what_is_not_held.py`,
  `arrt/tests/browser/test_topics.py`, `arrt/tests/browser/test_the_artist_page.py`,
  `arrt/tests/browser/test_the_collection.py`, `arrt/tests/browser/test_the_status_sources_table.py`,
  `arrt/tests/browser/test_the_clients.py`, `arrt/tests/browser/test_watches_screen.py`,
  `arrt/tests/browser/test_copy_says_it_once.py`, `arrt/tests/browser/test_the_sidebar.py`.
- **Rewritten assertions:** Players' and Watches' "Remove…" become "Forget…"; copy naming "the
  collection" for the household's holdings becomes "the Library"; `test_the_status_sources_table.py`'s
  number forms if they change; each listed.
- **Acceptance:**
  1. A scene on three walls says "A, B and C" — red today.
  2. A `listed` broken to join with "+" turns the Work page's and the Walls waiting line's tests
     red — they stay green today.
  3. One number format: 2000 reads "2,000" at each site the report lists — red at each site
     today that prints it bare.
  4. A Tab from Artworks' skip link reaches the first tile past the facets.
  5. Forget on a Player and a Watch; Remove stays on a wall and a theme.
  6. `test_no_page_calls_a_player_a_client` anchors on each screen's own data first, then
     asserts the absence — red under a client break that says "client" in a row painted late.
- **Verification ceiling:** `testament run --json=summary --suite browser --` the owned files.
- **Model:** Sonnet-class, high.
- **Waits for:** 31, 34, 40.

### Chunk 42: The compose example, hardened

- **Type:** code
- **Closes:** audit-8's answers (`cap_drop: [ALL]`, a read-only root with named writable
  mounts), the example's retired-unit `MemoryMax` comment.
- **Found at HEAD:** `deploy/nas/compose.example.yaml` has `no-new-privileges` and `mem_limit`,
  no `cap_drop`, no `read_only`; `MemoryMax` is a comment; `tests/preferences/test_deployment_values.py`
  is a leak scanner and cannot hold the file's shape. The app stage runs as user 568 and
  writes `/art` and `/backups`; `/tmp` and `HOME` are unverified.
- **Owns:** `deploy/nas/compose.example.yaml`, `deploy/README.md` (its compose section), and
  new `tests/preferences/test_compose_example.py`.
- **Deliverables:** measured first on a scratch container of the `app` image on the delegate's
  own machine (not a deployment): with `cap_drop: [ALL]`, `read_only: true` and the writable
  mounts it needs, the server starts, serves its health route, takes a backup and writes a
  feed; then the example carries exactly what was measured, and the comment goes. If no
  container runtime is on the delegate's machine, the measurement is the coordinator's at 55
  and the chunk ships the test and the example marked unmeasured.
- **Acceptance:** the new test red when `cap_drop` or `read_only` is removed, and red when a
  path the measurement needed writable is not mounted; the report lists what the container
  wrote and where.
- **Reads outside arrt/:** the governance test reads `deploy/`.
- **Records owed:** `operational-spec.md` (the hardening); `operator-verification.md` (the
  operator's own compose file, in the private repository, against the example).
- **Verification ceiling:** `testament run --json=summary --suite governance` (it adds a tracked file).
- **Model:** Sonnet-class, high.
- **Waits for:** —.

### Chunk 43: Test-suite health: clocks, ids, areas, the long tests

- **Type:** code
- **Closes:** audit-7 S7 (#438: clocks and ids in `CatalogueService` and `DiscoveryService`;
  curation areas), audit-7 M8 (the long UX-walk tests, and the prototype-scale test in
  `test_the_collection.py`).
- **Found at HEAD:** `PictureStore` already takes `now` and a staging token; the two services
  call `datetime.now(UTC)` and `uuid.uuid4()` directly (about 15 and 18 sites); no areas.
- **Owns:** `arrt/src/arrt/library/services/catalogue.py` and
  `arrt/src/arrt/library/services/discovery.py` (the clock and id seams only, with defaults, so
  `arrt/src/arrt/services/container.py` and the seed command do not change), `.testament.toml` (the curation
  suite's areas only), `arrt/tests/browser/test_the_ux_walk.py`,
  `arrt/tests/browser/test_the_collection.py` (the prototype-scale test only), and the two
  services' unit tests.
- **Deliverables:** measure first (`testament report --json` and the run's `slow_tests`) and
  name the long tests from the measurement; split or cheapen them; areas declared per
  `testament guide project`.
- **Acceptance:**
  1. A fixed clock and id source passed to each service is what every record it writes carries
     — red today, parametrised over the writing methods.
  2. A curation run no longer advises `areas`; the cacheability advice before and after, in the report.
  3. Each long test's `delay_s` before and after.
- **Verification ceiling:** `testament run --json=summary --suite curation --` the two services'
  unit tests; `testament run --json=summary --suite browser --` the two browser files; the
  governance suite whole (it edits `.testament.toml`).
- **Model:** Opus-class, medium.
- **Waits for:** 29, 35, 40, 41.

### Chunk 44: A supported plugin-testing helper

- **Type:** code
- **Closes:** audit-1 M10 and audit-4 12 (Arrt's half; arrt-sources' imports are the sources
  planner's).
- **Found at HEAD:** no helper; the private suite imports phase two's internals (the other
  repository, unverified); a helper wraps `PhaseTwoEngine.judge` with a `WikidataLink` and a
  `QualityProfile`; `test_source_plugins.py` holds the built-in plugins to importing only
  `arrt.library.sources`.
- **Owns:** `arrt/src/arrt/library/sources/__init__.py` (the helper's export),
  new `arrt/src/arrt/library/sources/testing.py`, `docs/source-plugins.md` (§ Testing only),
  `arrt/tests/unit/test_source_plugins.py` (the import-boundary test), and
  new `arrt/tests/unit/test_plugin_testing_helper.py`.
- **Acceptance:** a plugin test written against `arrt.library.sources.testing` alone reaches the
  verdict the host reaches for each of the cases the report lists; the boundary test still
  refuses a built-in plugin importing `phase_two` (red with one planted), and `testing.py` is
  excluded from that rule by name, with its reason.
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/unit/test_plugin_testing_helper.py arrt/tests/unit/test_source_plugins.py
  arrt/tests/unit/test_met_source.py`.
- **Model:** Sonnet-class, high.
- **Waits for:** 32.

### Chunk 45: The MCP surface, broken once

- **Type:** code
- **Exposed API:** the MCP surface
- **Closes:** audit-5 F3 (`artwork_id` in wall outputs), audit-5 F2b (the acts on a wall in one
  tool), audit-5 F14's MCP half (`not_again(scope='theme')` and `remove`), the rename of
  `display_plane_has_reported` (ledger L2). Ruling 3's one break: everything breaking is here.
- **Found at HEAD:** wall outputs carry `work_id` in `_scene_wall_fields`, `_republished_fields`,
  `upcoming`, `last_shown` and `display_state` (`arrt/src/arrt/mcp/bindings.py`); every act on a wall is on
  `art_theme` (activate, hang_selection, not_again, kept_off, allow_again, unhang, and seven
  scene acts); `not_again(scope='theme')` does what `remove` does; the description budget is
  2048 bytes, the client's truncation limit (`arrt/src/arrt/mcp/registry.py`), and `art_display` uses 2045;
  `arrt/src/arrt/ask/prompt.py`'s `ASK_SCOPE` holds no wall act; HTTP names the same fields `work_id`.
- **Owns:** everything under `arrt/src/arrt/mcp/` until 53 takes it, `.prawduct/artifacts/api-contract.md`
  (the MCP surface table, the frozen names, the budget section), `arrt/tests/contract/test_mcp_surface.py`,
  `arrt/tests/contract/test_mcp_scenarios.py`, `arrt/tests/integration/test_theme_and_display_tools.py`,
  `arrt/tests/integration/test_mcp_preview_and_sync.py`, `arrt/tests/integration/test_client_tools.py`,
  and `arrt/tests/unit/test_surface_parity.py` (the wall rename map).
- **Must not touch:** `arrt/src/arrt/http/` (HTTP keeps `work_id`); `contract/` (its `work_id`
  is a contract field); `arrt/src/arrt/ask/prompt.py`.
- **Deliverables:** first, before any code, the byte count of the gathered descriptions on
  `art_display` (the corrected DECISION decides between one tool and a new `art_players` on
  that number, and the report shows it); then the break: `artwork_id` in every wall output,
  every act on a wall in one tool, `not_again`'s theme scope gone, `has_reported`; a call to a
  moved action answers with a message naming where it went; the frozen-name list and
  `api-contract.md` updated; the change record's migration note written for 54.
- **Implicit guarantees of the old grouping:** every tool's description fits the budget
  (`test_mcp_surface.py`); every action has an example; the tools Ask may call are unchanged
  (`ASK_SCOPE` is a subset of the tools, held); the frozen list names every action.
- **Rewritten assertions:** every MCP test reading `work_id` from a wall output reads
  `artwork_id`; every test calling a wall act on `art_theme` calls it where it went; the
  frozen-name list; each a recorded contract change (ruling 3), listed.
- **Acceptance:**
  1. The budget test green for every tool after the regroup; red with one description padded.
  2. A scenario hanging a theme and applying a scene through the new grouping passes; the old
     call fails naming the new tool — red if silently accepted.
  3. A test walking every wall output's keys finds no `work_id` — red today.
  4. The rename map refuses a stale rename (red with one planted).
  5. `uv run mypy` clean.
- **Records owed:** the change record's announcement (54), `api-contract.md` (its own).
- **Verification ceiling:** `testament run --json=summary --suite curation -- arrt/tests/contract
  arrt/tests/integration/test_theme_and_display_tools.py arrt/tests/integration/test_mcp_preview_and_sync.py
  arrt/tests/integration/test_client_tools.py arrt/tests/unit/test_surface_parity.py
  arrt/tests/unit/test_ask_agent.py`.
- **Model:** Opus-class, high.
- **Waits for:** 30, 32, 35 (their parity exemptions merged first).

### Chunk 46: The docstring sweep — moved to a third part

- **Type:** doc-only
- Dropped (frontmatter): a cleanup across every module under `arrt/src/arrt/`, last of
  everything, with a corrected count; § What moves to a third part.

### Chunk 47: Contract 1.3.0: the Player states' words, one corrected answer, the missing must-refuse fixtures

- **Type:** code
- **Exposed API:** the Player contract (`arrt-contract`)
- **Closes:** C7, C28, and the `player_states` half of the words DECISION.
- **Found at HEAD:** `contract/transport.json`'s heartbeat route records `not_an_object` as
  422 in the framework's body; the client heartbeat's route answers 400; the wall heartbeat's
  handler takes its body as a dict (`arrt/src/arrt/http/player.py`), so the framework refuses first. About
  20 of 26, 17 of 22 and 81 of 86 schema constraints have no must-refuse fixture; no schema
  refuses a duplicate label name.
- **Owns:** `contract/transport.json`, `contract/vocabulary.json` (`player_states` and `_about`),
  `contract/fixtures/` (new must-refuse fixtures and their index rows), `contract/schemas/` and
  `contract/src/arrt_contract/` (only for a rule a new fixture needs), `contract/pyproject.toml`
  (the version, 1.3.0), `contract/uv.lock`, `arrt/uv.lock` (the package's metadata line),
  `contract/tests/test_transport.py`, `contract/tests/test_vocabulary.py`,
  `contract/tests/test_schemas_and_fixtures.py`, `arrt/src/arrt/http/player.py` (the wall
  heartbeat's body), `arrt/tests/contract/test_transport_table.py`,
  `arrt/tests/contract/test_player_surface.py`, and `.prawduct/artifacts/player-contract.md`
  (§ Transport's sentence on that answer only).
- **Must not touch:** `contract/released/` (28's; never edited); `contract/tests/test_released.py`;
  § Releases (54).
- **Deliverables:** the wall heartbeat answers a body that is not a JSON object with 400 in the
  error shape, and its row says so; a must-refuse fixture for every schema constraint that has
  none, each index row with its reason; a duplicate label name refused by a semantic rule if
  the server never writes one, else recorded in § Transport as a known gap; `player_states` with
  the DECISION's keys, words, `setup` and `means`; the version 1.3.0.
- **Acceptance:**
  1. `test_transport_table.py` drives the real server with a non-object body to the wall
     heartbeat and gets 400 in the error shape — red today (422). The framework's 422 body is
     copied from an observed run into the test that shows it gone (lesson 1).
  2. A new test counts constraints with no must-refuse fixture and wants none — red today, with
     the counts.
  3. `test_released.py` green: nothing loosened, nothing removed, 28's guard satisfied.
  4. `test_vocabulary.py` holds `player_states` to the five keys and their fields.
- **Records owed:** § Releases' 1.3.0 entry and "What a Player does at 1.3.0" (54): a Player
  gives each new must-refuse fixture a reason; nothing it reads or writes must change.
- **Verification ceiling:** `testament run --json=summary --suite contract`; `testament run
  --json=summary --suite curation -- arrt/tests/contract`; the governance suite whole (it adds
  tracked fixtures).
- **Model:** Opus-class, medium.
- **Waits for:** 28.

### Chunk 48: Programming reads inside its writes; one home for the lookups; the facade's leftovers

- **Type:** code
- **Closes:** C1, C2, C9, C18, C19.
- **Found at HEAD:** `delete_theme` checks the default flag and the walls hanging it, then opens
  its transaction; `exclude_work`, `allow_work` and `remove_from_theme` check before
  `publishing()`; `make_default` and `update_theme` read then write with no transaction;
  `_record_screen` reads the known screens before its transaction (`arrt/src/arrt/programming/reports.py`);
  `scene_walls` (`arrt/src/arrt/programming/scenes.py`) reads with no read scope and asserts a wall it read a
  moment ago; every collaborator looks walls and themes up through `FeedPublisher.get_wall` and
  `get_theme` (about 63 sites); `DisplaySettings` is defined in `arrt/src/arrt/programming/display.py`; the
  facade sets `_store`, `_library` and `_settings` and reads none.
- **Owns:** `arrt/src/arrt/programming/themes.py`, `arrt/src/arrt/programming/scenes.py`,
  `arrt/src/arrt/programming/walls.py`, `arrt/src/arrt/programming/reports.py`
  (`_record_screen` only), `arrt/src/arrt/programming/feeds.py` (`get_wall`, `get_theme`),
  `arrt/src/arrt/programming/display.py`, new `arrt/src/arrt/programming/lookups.py`,
  new `arrt/src/arrt/programming/settings.py`, and the tests:
  `arrt/tests/unit/test_display_facade.py`, `arrt/tests/unit/test_scenes.py`,
  `arrt/tests/unit/test_feed_publisher.py`, `arrt/tests/unit/test_programming_consistency.py`,
  `arrt/tests/integration/test_theme_routes.py`, `arrt/tests/integration/test_selections_and_exclusions.py`,
  `arrt/tests/integration/test_scene_routes.py`, and new `arrt/tests/unit/test_reads_inside_their_writes.py`.
- **Must not touch:** any public name of the facade or of a collaborator; `arrt/src/arrt/services/container.py`
  and `__main__.py` (`display.py` re-exports `DisplaySettings`); the not-found messages' words (37's).
- **Deliverables:** each check moved inside the scope that writes; `scene_walls` inside
  `reading()`; the lookups in one module every collaborator calls, `FeedPublisher` among them;
  `DisplaySettings` in its own module, re-exported; the unread attributes gone.
- **Implicit guarantees of the lookups on `FeedPublisher`:** the messages "No wall with id …" and
  "No theme with id …" (tests pin them); one store behind every collaborator
  (`test_display_facade.py`); every module logging as `arrt.programming.display` (a test holds it).
  Each kept and tested.
- **Rewritten assertions:** `test_display_facade.py`'s reads of the facade's `_store` (it finds the
  shared store through the collaborators); listed.
- **Acceptance:**
  1. A store spy recording whether a transaction or read scope is open at each read: every read
     the seven methods make happens inside the scope that writes — red today, naming each method.
  2. A wall deleted between `_pins_on_held_walls` and the wall's read: `scene_walls` answers
     without a 500 — red today.
  3. A test that no collaborator but the lookups module defines a wall or theme lookup (red with
     one planted).
  4. `DisplaySettings` is one class object imported from either module.
  5. `uv run mypy` clean.
- **Verification ceiling:** `testament run --json=summary --suite curation --` the owned test
  files and `arrt/tests/unit/test_surface_parity.py`.
- **Model:** Opus-class, high: seven methods' transaction scopes, and a move under every collaborator.
- **Waits for:** 30.

### Chunk 49: The catalogue's shape guards: an exact schema, a release list a test holds, a generation's sentence

- **Type:** code
- **Closes:** C8, C10, C11, C12.
- **Found at HEAD:** `_EXPECTED_SCHEMA` (`arrt/tests/unit/test_catalogue_store.py`) lists 18
  tables, and `_EXPECTED_SCHEMA.keys() <= tables` passes about fifteen it does not list,
  `reported_screens` and `catalogue_opened` among them; `RELEASES` (`arrt/tools/old_catalogue.py`)
  names v0.1.0 to v0.11.0 and `releases.json` keeps a row only for a release whose dump differs;
  nothing fails when a release ships without its dump; the snapshot's refusal on a generation
  rise says the migration "drops catalogue shape generation N", and
  `test_pre_migration_snapshot.py` pins "drops themes.is_active" for the column case.
- **Owns:** `arrt/tests/unit/test_catalogue_store.py` (`_EXPECTED_SCHEMA` and its check),
  `arrt/tools/old_catalogue.py`, `arrt/tests/fixtures/catalogues/releases.json` (and the dumps
  beside it), `arrt/tests/system/test_migration_chain.py`,
  new `tests/preferences/test_catalogue_release_dumps.py`, `arrt/src/arrt/persistence/backup.py`
  (`SnapshotFailed`'s sentence), `arrt/src/arrt/persistence/migrations.py` (the phrase a
  generation rise contributes only), `arrt/tests/unit/test_pre_migration_snapshot.py`, and
  `.prawduct/artifacts/project-preferences.md` (the restore and migration-chain norm row only).
- **Deliverables:** `_EXPECTED_SCHEMA` lists every table the store creates, with its columns, and
  the check is equality; `releases.json` gives every release in `RELEASES` a row (its dump, or
  the release whose shape it shares); the DECISION's governance test; the refusal on a
  generation rise says what it is (the open raises the shape generation from N to M); the norm
  row says what is enforced.
- **Rewritten assertions:** `test_pre_migration_snapshot.py`: the column case keeps asserting
  "drops themes.is_active"; a new generation case asserts the new sentence. The reshaping is the
  point (C12), listed.
- **Acceptance:**
  1. The schema check red today (the unlisted tables named), and red when a table is created
     with no entry.
  2. The release test red today if a release below 0.11.0 has no row; red when the change log
     records a release below the version that `releases.json` lacks; its parser tested on the
     change log's own `release=` lines (lesson 1).
  3. The generation case red on today's sentence.
  4. `test_norm_index.py` green on the reworded row.
- **Reads outside arrt/:** the governance test reads `arrt/tools/`, the fixtures, the change log.
- **Verification ceiling:** `testament run --json=summary --suite curation --
  arrt/tests/unit/test_catalogue_store.py arrt/tests/unit/test_pre_migration_snapshot.py
  arrt/tests/unit/test_schema_generation.py arrt/tests/system/test_migration_chain.py`; the
  governance suite whole (a new tracked test).
- **Model:** Opus-class, medium.
- **Waits for:** —.

### Chunk 50: The system tests guard what they run

- **Type:** code
- **Closes:** C4, C5, C6, C16, C29, C30.
- **Found at HEAD:** `every_feed_keeps_the_contract` (`arrt/tests/conftest.py`) patches the
  builder in the test process, so a server process's feeds are never checked;
  `test_restore.py` compares works and the hung theme's id; `[tool.mypy]` checks the plane's source
  only, and `tests/preferences/test_type_gate.py` asserts exactly that list; a test calling
  `monkeypatch.undo()` switches the guard off for its remainder; `test_one_function_writes_a_feed`
  matches only the alias.
- **Owns:** `arrt/tests/system/conftest.py`, `arrt/tests/system/test_restore.py`,
  `arrt/tests/system/test_a_real_player.py` (its types only), `arrt/tests/feed_guard.py`,
  `arrt/tests/conftest.py` (`every_feed_keeps_the_contract` only), `arrt/tests/unit/test_feed_guard.py`,
  `arrt/tests/unit/test_reconciliation.py` and `arrt/tests/unit/test_scenes.py` (the two tests
  named above only), `arrt/pyproject.toml` (`[tool.mypy]` files), `tests/preferences/test_type_gate.py`
  (its files assertion), and `arrt/src/arrt/programming/feeds.py` (the reconcile, only if
  acceptance 3 is red).
- **Deliverables:** every feed a server process under test wrote is validated against the
  contract when the test ends, through the package; the restore compares the household whole;
  the stale-feed case measured and, if red, fixed in the reconcile; `arrt/tests/system` type-checked;
  the guard cannot be switched off in passing, and the one-writer test sees the module attribute.
- **Implicit guarantees of the in-process guard:** every feed built in a test process is checked
  as it is built — kept, and the new check is in addition, never instead.
- **Rewritten assertions:** `test_type_gate.py`'s `files == ["src/arrt"]`; listed.
- **Acceptance:**
  1. A feed corrupted on disk before a system test ends fails it, naming the wall — red today.
  2. A restored copy missing one membership fails the restore test — red today.
  3. A backup older than a hang, restored beside the feed the hang wrote: after start the feed
     names no work the backup lacks — measured; if red, fixed, and the fix's own red returned.
  4. mypy over `arrt/tests/system` clean with narrowings, no casts; a reintroduced optional indexing
     is red.
  5. A test that calls `monkeypatch.undo()` still has its feeds checked — red today.
  6. A feed written through `feeds.as_v2_document` by its module attribute is caught — red today.
- **Verification ceiling:** `testament run --json=summary --suite curation -- arrt/tests/system
  arrt/tests/unit/test_feed_guard.py arrt/tests/unit/test_reconciliation.py arrt/tests/unit/test_scenes.py`;
  `testament run --json=summary --suite player`; `testament run --json=summary --suite governance --
  tests/preferences/test_type_gate.py`.
- **Model:** Opus-class, medium.
- **Waits for:** 29, 48.

### Chunk 51: Browser assertions that can fail; flake #442

- **Type:** code
- **Closes:** C13, C14, C23, C31.
- **Found at HEAD:** `test_no_machine_dates.py` waits 300 ms for "a late paint";
  `test_wanted.py` sleeps 1500 ms to stagger two holds; `test_the_run_view.py` sleeps a window to
  count polls; `test_keyboard_and_phone.py`'s `not_to_have_attribute("tabindex")` passes on its
  first poll, before the `ResizeObserver` has reported; #442's one failure was a 30 s wait for
  "Skipped." in `test_walls_last_and_next.py`, under load, with no tab involved.
- **Owns:** `arrt/tests/browser/test_walls_last_and_next.py`, `arrt/tests/browser/test_no_machine_dates.py`,
  `arrt/tests/browser/test_wanted.py`, `arrt/tests/browser/test_the_run_view.py`,
  `arrt/tests/browser/test_keyboard_and_phone.py`, `arrt/tests/browser/test_hanging_a_theme.py`,
  `docs/testing.md` (§ "Assertions read the page through `expect`": the table and the hazards
  only), and `arrt/tests/unit/test_browser_reads_retry.py` (only if a marker changes kind).
- **Deliverables:** each of the three sleeps becomes a condition (a per-screen anchor; the hold's
  countdown; `page.clock` for the window) or is argued in its marker as a "nothing happens"
  claim; the tabindex clause made falsifiable (assert after the observer is seen to have run) or
  dropped with its reason; #442 reproduced on the pool under load with its failure text, and its
  cause established, or what was measured recorded on the issue; chunk 12's three claims
  measured in a scratch page and written into the table.
- **Acceptance:** each converted test red under a client break that makes its waited-for thing
  never happen, and not red by timing (five pool runs green); the tabindex clause red under a
  break that marks a fitting box focusable after its first paint; #442: the run count and every
  failure's text, in the report.
- **Verification ceiling:** `testament run --json=summary --suite browser --` the six files, five
  times; `testament run --json=summary --suite curation -- arrt/tests/unit/test_browser_reads_retry.py`.
- **Model:** Opus-class, medium.
- **Waits for:** —.

### Chunk 52: The fallback runs what the manifest says

- **Type:** code
- **Closes:** C22 (native review N8), C35.
- **Found at HEAD:** the fallback's steps in `tests.yml` restate each suite's command and
  selection by hand; `tests/test_ci_fallback.py` holds them to the manifest after the fact.
- **Owns:** `.github/workflows/tests.yml` (the fallback steps only),
  `.github/scripts/pool_or_fallback.py` (a subcommand that runs one suite's manifest command
  here, without testament), `tests/test_ci_fallback.py`, `docs/testing.md` (the CI paragraph).
- **Implicit guarantees of the hand-written steps:** each suite writes a report named for it;
  each step has its own time limit within the job's; the governance step syncs both projects'
  environments first; the browser suite never runs here. Each tested.
- **Acceptance:**
  1. A change to a suite's selection in `.testament.toml` changes what the fallback runs with no
     edit to `tests.yml` (a test with a manifest of its own).
  2. A test refuses a fallback step that names a path or a pytest command of its own.
  3. The command translation is tested on the manifest's own lines.
  4. **Seen on a scratch pull request (the coordinator's):** a workflow pointed at an
     unreachable console falls back after its retries, runs every suite but the browser here,
     and the non-required job goes red; the run's address in the integration entry.
- **Verification ceiling:** `testament run --json=summary --suite governance --
  tests/test_ci_fallback.py tests/test_assert_tests_ran.py tests/test_default_suite_ci_scope.py`; `actionlint`.
- **Model:** Opus-class, medium.
- **Waits for:** 29.

### Chunk 53: MCP II: the twins of 2b's new fields

- **Type:** code
- **Exposed API:** the MCP surface (additive)
- **Closes:** the MCP twins of 30 (wall and Player states, `settings_url`, failed fetches), 32
  (outcomes; retry by cause, audit-5 § 3), 33 (the search record's counts), 35 (unknown-cost
  spend), 40 (history by work, audit-5 F18's MCP half; a work's Get; `pictured_artwork_id`);
  `art_catalogue`'s topics description naming `WIKIDATA_USER_AGENT` (ledger L14); rulings 1 and
  2 in every description.
- **Owns:** everything under `arrt/src/arrt/mcp/` (after 45), `.prawduct/artifacts/api-contract.md`
  (the MCP sections), `arrt/tests/contract/test_mcp_surface.py`, `arrt/tests/contract/test_mcp_scenarios.py`,
  `arrt/tests/integration/test_client_tools.py`, `arrt/tests/integration/test_registry_tools.py`,
  `arrt/tests/integration/test_history_surface.py`, `arrt/tests/integration/test_catalogue_tool.py`,
  `arrt/tests/integration/test_discovery_tool.py`, and `arrt/tests/unit/test_surface_parity.py`
  (it removes every exemption naming Chunk 53).
- **Must not touch:** any name 45 settled (this chunk only adds); `arrt/src/arrt/http/`.
- **Acceptance:**
  1. No exemption naming Chunk 53 is left, and the file's stale-exemption test is green.
  2. Each twin agrees value for value with HTTP (the parity test's form).
  3. The descriptions carry no environment-variable name and say *theme* and *the Library* (a
     test over every description; red with one planted).
  4. Every tool within the budget.
- **Verification ceiling:** `testament run --json=summary --suite curation -- arrt/tests/contract`
  and the owned integration and unit files.
- **Model:** Opus-class, high.
- **Waits for:** 30, 32, 33, 35, 40, 45.

### Chunk 56: The image's test stage leaves GitHub's runner for ordinary pull requests

- **Type:** code
- **Closes:** the owner's ruling of 2026-11-20 (CI is kept small); audit-8's note that the
  image job is the largest per-pull-request cost on GitHub's runner (about seven minutes of
  build and test, measured on pull request 446).
- **Model:** Opus-class, medium: it changes what a pull request is checked by, and the
  image's test stage has caught a defect the pool did not (four tests reading a
  repository-root file the image does not carry, wave 1).
- **Waits for:** 29 and 52 (one chunk at a time edits `.github/` and `.testament.toml`).
- **Owns:** `.github/workflows/image.yml`, `.testament.toml` (one suite added, if the pool
  can build), `arrt/Dockerfile` (comments only), `docs/testing.md` (the image paragraph),
  `CLAUDE.md` (one line, if the command table changes), the root tests that read
  `image.yml`.
- **Deliverables:**
  - Find out, by running it, whether a runner of the pool can build `arrt/Dockerfile`'s
    `test` target and run it (the pool has runners labelled for Docker; read
    `testament guide project` for a suite that runs in a container or needs a label). If it
    can: a suite of its own on the pool runs the image's test stage, selected for every pull
    request by the same step that runs the other suites, and its result is in the same
    verdict. If it cannot: say exactly why, with the output, and keep the stage for pull
    requests into `main` and for `workflow_dispatch`.
  - `image.yml` runs on pull requests into `main` and by hand, not on every pull request;
    the `player` job is unchanged.
  - The guarantee the job gave is listed and kept: a test that reads a file outside what
    the image carries fails before `develop`, not at the release. If the pool cannot hold
    it, a cheap guard does (a root test that the image's build context contains every
    repository-root file a test under `arrt/tests/` opens), shown red on wave 1's case.
- **Acceptance:** on an ordinary pull request no job builds an image on GitHub's runner
  (read from the workflows as data, by a root test); the wave-1 defect (a test reading
  `.env.example` from the repository root with the file left out of the image) is caught
  by whatever now holds the guarantee, shown red; the required check's name is unchanged;
  what the first pull request should show is stated for the coordinator to compare.
- **Verification ceiling:** the root tests that read the workflows, the governance suite
  whole, `actionlint` if installed; the pool suite itself if one is added. No image is
  built on this machine.

### Chunk 57: Walls — hang chosen works on a wall

- **Type:** code
- **Closes:** audit-5 F9's wall-side half, by the owner's ruling of 2026-11-20.
- **Model:** Opus-class, medium: a small flow across two screens, with a selection that must
  remember which wall it is for and say so.
- **Waits for:** 34 (the selection's *Hang…*, `hangOnAWall`, `canHang`), 31 (the Walls
  screen's health states) and 41 (the Walls screen's small items): one chunk at a time
  edits `arrt/src/arrt/http/static/screens/walls.js`.
- **Owns:** `arrt/src/arrt/http/static/screens/walls.js` (the *Hanging* picker only),
  `arrt/src/arrt/http/static/screens/collection.js` and
  `arrt/src/arrt/http/static/core/selecting.js` (only what selecting *for a wall* needs),
  new `arrt/tests/browser/test_hanging_works_from_a_wall.py`,
  `.prawduct/artifacts/information-architecture.md` (the Walls and Artworks rows).
- **Deliverables:**
  - A wall's *Hanging* picker offers choosing works, beside its themes. Choosing it opens
    Artworks in selection, for that wall: the page says which wall the selection is for,
    in words, for as long as it is, and offers a way out that leaves the wall as it was.
  - The selection's *Hang…* then hangs on that wall without asking which (the question
    still says what will happen and what is left out, as Chunk 34 built it); for any other
    selection *Hang…* asks as before.
  - Afterwards the person is back on Walls, at that wall, which shows what it now hangs.
  - Nothing new on the server: the act is the one Chunk 34 sends. If the flow needs a
    server change, that is a finding to return, not to build.
  - Keyboard and phone: the flow works by keyboard alone, focus returns to the wall's
    picker on the way out and to the wall's card after a hang, and the "for this wall"
    words do not push *Select* off its place (ruling 6: *Select* last on the right).
- **Acceptance:** from Walls, choosing works for one wall and hanging two of them sends one
  `hang_selection` naming that wall and those two works (asserted on the request body) and
  returns to Walls with that wall showing them; leaving without hanging sends nothing and
  the wall is unchanged; a selection not started from a wall still asks which wall; the
  words naming the wall are read by a screen reader when selection starts. Each shown red
  first, by a client break of the behaviour it names.
- **Verification ceiling:** the new browser file and the browser files of Walls, Artworks
  and the selection model, on the pool; the guard `arrt/tests/unit/test_browser_reads_retry.py`;
  ruff and black in `arrt/`.

### Chunk 58: The frozen release holds the transport table and the vocabulary

- **Type:** code
- **Closes:** the gap the integration of Chunk 47 measured (above, § Decisions made
  mid-build); the rule in `.prawduct/artifacts/player-contract.md` § The package that a
  minor is additive, for the two data files 1.2.0 added.
- **Model:** Opus-class, medium: a release's frozen copy is amended once, before it has
  left this branch, and the check it enables must fail for a change of meaning and pass
  for a recorded correction.
- **Waits for:** 28 and 47.
- **Owns:** `contract/released/1.2.0/` (two files added, `sha256.json` rewritten by the
  same writer that wrote it), `contract/tests/test_released.py`,
  `contract/src/arrt_contract/__init__.py` (only if `released()` must expose the new
  files), `.prawduct/artifacts/player-contract.md` (§ The package: what a release's copy
  holds).
- **Deliverables:**
  - `contract/released/1.2.0/` gains `transport.json` and `vocabulary.json` with the bytes
    they have at the tag `contract-v1.2.0`, and its `sha256.json` covers them. The copy has
    not left this branch, so amending it is honest; the specification says from which
    release on a copy holds these files (1.0.0 and 1.1.0 had neither).
  - The package's suite holds HEAD to every frozen copy that has them: every answer of a
    release (a route, a case, its status and its body's shape) still holds, unless HEAD's
    row carries a `corrected` record naming the version it changed in, what it was and
    why; no route or case of a release is gone; every state and word of a release's
    vocabulary is still there with the same meaning (a word may be added, a state may be
    added; a word changed is a change of meaning and fails).
  - The one recorded correction (the wall heartbeat's answer to a body that is not an
    object, 422 to 400 in 1.3.0) passes because it is recorded.
- **Acceptance:** with an answer of 1.2.0 changed in HEAD's table and no `corrected`
  record the suite is red naming the route and case (the integrator's own experiment:
  `label`/`captions_no_wall` 404 to 410); with the record added it is green; a route's
  case removed is red; a vocabulary word of 1.2.0 reworded is red, and a state added is
  green; a byte changed in either frozen file is red by its hash. Each shown.
- **Verification ceiling:** the contract suite whole, the server's contract tests
  (`arrt/tests/contract`), the governance suite whole, the contract project's mypy, ruff
  and black in `contract/`.

### Chunk 59: The contract package's loose ends — the release-copy writer, `py.typed`, a docstring

- **Type:** code
- **Closes:** what Chunks 28, 50 and 58 found (above, § Decisions made mid-build).
- **Model:** Sonnet-class, high: three small, separate things in one package.
- **Waits for:** 58.
- **Owns:** new `contract/tools/freeze_release.py`, new `contract/tests/test_freeze_release.py`,
  new `contract/src/arrt_contract/py.typed`, `contract/pyproject.toml` (package data only),
  `contract/src/arrt_contract/__init__.py` (`released()`'s docstring only),
  `.prawduct/artifacts/player-contract.md` (§ The package: how a release is copied).
- **Deliverables:**
  - The writer of a frozen copy is in the repository: given a tag and a version it writes
    `contract/released/<version>/` (the fixtures with their index, `routes.json`, and from
    1.2.0 on `transport.json` and `vocabulary.json`) and its `sha256.json`. Run on the tags
    of 1.0.0, 1.1.0 and 1.2.0 it reproduces the three existing copies byte for byte; a test
    holds that for every copy whose tag is fetched, and says by name when a tag is not
    there to compare (never a silent pass).
  - The package ships `py.typed`, and its wheel carries it (a test reads the built
    distribution's file list, or the installed package).
  - `released()`'s docstring says what a copy holds, from which release.
- **Acceptance:** the three copies reproduced byte for byte from their tags by the
  committed tool; a byte changed by the tool's logic (a file left out, a hash line
  reordered) is red; `py.typed` is found by a type checker importing the package from an
  environment that installed it. Each shown red first.
- **Verification ceiling:** the contract suite whole, the governance suite whole, the
  contract project's mypy, ruff and black in `contract/`.

### Chunk 60: Small server follow-ups from groups B and C

- **Type:** code
- **Closes:** items the chunks of groups B and C reported and could not settle in their own
  files (§ Decisions made mid-build).
- **Model:** Opus-class, medium: eight small things, three of which change what a person
  reads on Status.
- **Waits for:** 39 and 53 (it adds response fields; 53 owns `arrt/src/arrt/mcp/` until it
  merges).
- **Owns:** `arrt/src/arrt/services/health.py` (setup steps and the source's sentence only),
  `arrt/src/arrt/library/sources/names.py`, `arrt/src/arrt/library/services/registry_search.py`,
  `arrt/src/arrt/services/container.py` (the reconcile's cadence only),
  `arrt/src/arrt/http/models.py` and `arrt/src/arrt/http/api.py` (the four cost summaries
  only), `contract/` (one semantic rule, its fixtures, the specification's sentence),
  their tests, and the builders in `arrt/tests/browser/`.
- **Deliverables:**
  - The walls of a Player still in setup (no token, or awaiting its first report) are setup
    steps, not troubles.
  - A source's sentence names the museum the plugin declares, as the rest of its answer does.
  - `registry_search.py`'s own copy of "which held work pictures this" calls
    `CatalogueService.pictured`.
  - `names.built_in_museums()` does not import the plugin-testing helper, and the test that
    holds the helper out of a plugin's imports covers that path.
  - The answers that carry a cost and no sentence gain the service's `summary`: the
    unattended allowance, a watch, an Ask reply's metadata, a run. Additive; the client
    reads them in a later chunk.
  - The cap of 32 outputs and 32 label outputs per report is a rule of the contract (1.3.0,
    not yet released): a semantic rule with a must-refuse fixture for each, and the
    specification says it.
  - The periodic reconcile's cost is measured at 2,000 and 5,000 works, and it runs as
    often as that cost allows: the number and its reason are recorded.
- **Acceptance:** each item has a test through the route or caller that reads it, shown red
  first; the whole browser suite passes with the builders deriving the new fields through
  the server's own functions; the contract suite and the server's contract tests pass with
  the two new fixtures refused for their own reason alone; the measurement is returned as
  made, with how.
- **Verification ceiling:** the curation files of each item, `arrt/tests/contract`, the
  contract suite whole, the whole browser suite, the governance suite whole, mypy in both
  projects, ruff and black.

### Chunk 61: The type gate holds in the fallback's environment

- **Type:** code
- **Closes:** the fault two chunks made together (§ Decisions made mid-build): the type
  check passed on the pool and failed in the environment CI's fallback builds.
- **Model:** Sonnet-class, high: one guard and one allowance removed.
- **Waits for:** 50, 52, 56 and 59.
- **Owns:** new `tests/preferences/test_type_gate_in_the_fallback.py`,
  `tests/preferences/test_type_gate.py`, `arrt/pyproject.toml` (`[tool.mypy]` only).
- **Deliverables:**
  - A root test that reads the groups CI's fallback syncs for each project from
    `.github/scripts/pool_or_fallback.py`'s `FALLBACK_SETUP` itself, and, for every module
    the type check follows (the configured `files` and what they import from `mypy_path`),
    requires each third-party import, one guarded only by `TYPE_CHECKING` included, to come
    from those groups' packages, the project's own dependencies, or the
    `ignore_missing_imports` allowance. It fails by name for an import the fallback's
    environment would not have.
  - The allowance for `arrt_contract` comes out, with its comment: the package ships its
    type marker (Chunk 59), and the type check is clean without it.
- **Acceptance:** with `playwright` taken out of the allowance the new test is red naming
  `tools.ux_walk` and the import; with a new third-party import under `TYPE_CHECKING` in a
  followed module it is red; with the fallback's groups changed in `FALLBACK_SETUP` it
  follows; the type check is clean in both environments (the pool's, and a fresh sync of
  the fallback's groups alone) with `arrt_contract` out of the allowance.
- **Verification ceiling:** the governance suite whole on the pool; the fallback's
  governance step run locally in a fresh environment; ruff and black at the root.

### Chunk 62: One setup step per cause, and a cost said once

- **Type:** code
- **Exposed API:** `/api`
- **Closes:** what integration found in Chunks 60, 41 and 34 together (§ Decisions made
  mid-build): one cause listed as several setup steps, a wall's panel contradicting the
  page's summary, and the three places a cost is still formatted by its reader.
- **Model:** Opus-class, high: it changes what Status says about a household that is half
  set up, on two surfaces and three screens.
- **Waits for:** 60 and 41.
- **Owns:** `arrt/src/arrt/services/health.py` and `arrt/src/arrt/programming/player_state.py`
  (setup steps and a wall's display state only), `arrt/src/arrt/http/models.py` (those
  shapes only), `arrt/src/arrt/ask/` (the ledger's unknown cost only),
  `arrt/src/arrt/library/services/unattended.py` (`Standing.sentence` only),
  `arrt/src/arrt/mcp/tools.py` (one description), the client's Status, top bar, Ask,
  General and Watches screens under `arrt/src/arrt/http/static/` (only what reads these),
  their tests, and the builders in `arrt/tests/browser/`.
- **Deliverables:**
  - One setup step for one cause. A Player with no token, or awaiting its first report,
    is one step, which names the walls that wait for it and links to the Player. Its
    walls make no step of their own and no trouble.
  - A wall whose Player is still being set up says so on its own panel, in the server's
    words and with the mark a setup step takes, never the mark of a problem. Status, the
    top bar and MCP's status agree, because each renders the service's reading.
  - Ask's ledger records a call whose cost is unknown as unknown, never as a known zero,
    and its total says so in the words the Spend page uses.
  - The unattended allowance's sentence is the one cost writer's.
  - The client shows the server's `summary` for Ask's reply, the allowance, a Watch and a
    run, and formats no cost of its own.
  - MCP says a Watch is forgotten, as the screens do.
- **Acceptance:** for one Player with no token showing two walls: one step, naming both
  walls, on `GET /api/health`, on MCP's status and on Status; the top bar reads as setting
  up and the System link counts one step; each wall's panel says it waits, and nothing on
  the page says a problem. The same for a Player awaiting its first report. A wall whose
  Player has reported and gone quiet is still a trouble. An Ask call of unknown cost makes
  the total read "at least", through the route. A guard reads the client for a cost
  formatted outside the one helper that shows the server's sentence. Each shown red first.
- **Verification ceiling:** the curation files of health, Players, Ask and spend;
  `arrt/tests/unit/test_surface_parity.py`; `arrt/tests/contract`; the whole browser suite
  (it changes `arrt/src/arrt/http/models.py`); mypy, ruff and black in `arrt/`.

### Chunk 63: The suite's tail

- **Type:** code
- **Closes:** what integration found in Chunks 43, 39, 41 and 57 (§ Decisions made
  mid-build).
- **Model:** Sonnet-class, high: named states, named fixtures, one instant.
- **Waits for:** 43, 57 and 60.
- **Owns:** `arrt/tests/browser/test_the_ux_walk.py` and `arrt/tools/ux_walk.py` (the
  states a walk visits only), `arrt/src/arrt/library/services/taste.py` (the instant
  only), the fixtures of the tests that write a report for a wall no Player shows,
  `arrt/tests/unit/test_scheduler.py`, `arrt/src/arrt/http/static/index.html` (one
  sentence), `arrt/src/arrt/http/static/screens/walls.js` (one sentence), and the stale
  comments integration listed.
- **Deliverables:**
  - The UX walk visits by name the states it used to reach only as a screen's second
    visit: History for one work, Walls at one wall, Artworks searched, and Artworks
    choosing works for a wall. The time this adds to each walk is measured and returned.
  - Recording an artist's affinity inside a verdict takes the verdict's instant.
  - Every test that writes a wall's report does so for a wall a Player shows. No
    assertion changes; a test that turns out to depend on the impossible state is
    reported, not edited around.
  - A scheduler pass between two reconciles writes its one line saying nothing was due:
    a test asserts the line.
  - The page's first sentence says the Library, and a wall with no theme says both ways
    to hang something.
- **Acceptance:** each walk's visited states, before and after, with the four named
  states present; a probe wrapping the report writers counts no report for a wall no
  Player shows across unit, contract and integration tests, and counts some on the
  unfixed tree; a fixed clock given to a verdict is what the affinity carries, red today.
- **Verification ceiling:** the browser files it edits and the files of the fixtures it
  changes, on the pool; the governance suite whole; mypy, ruff and black in `arrt/`.

### Chunk 64: A last sweep

- **Type:** code
- **Closes:** rulings 1 and 2 in the last sentences a person reads; the reads of a 404
  that no test held (§ Decisions made mid-build).
- **Model:** Sonnet-class, high: named sentences, named tests, one guard.
- **Waits for:** 37, 62 and 63.
- **Owns:** `arrt/src/arrt/programming/reports.py`, `arrt/src/arrt/http/api.py`,
  `arrt/src/arrt/services/health.py`, `arrt/src/arrt/persistence/records.py` and
  `arrt/src/arrt/library/acquisition/space.py` (one sentence each),
  `arrt/src/arrt/library/services/taste.py` (one method's instant and id),
  `arrt/src/arrt/http/static/core/router.js` (one comment), the tests of those sentences,
  `arrt/tests/browser/test_the_run_view.py`, `arrt/tests/browser/test_asking.py`,
  `arrt/tests/browser/test_hanging_works_from_a_wall.py`,
  `arrt/tests/unit/test_major_2_feed.py` (one test's name), and two comments in
  `arrt/tests/browser/`.
- **Deliverables:**
  - The five sentences say the Library: Status's description of a household with no
    wall, the notice after accepting a work the Library nearly holds already, the
    trouble and the panel about backups, and the fetch queue's reason for pausing.
  - A guard over the sentences the server sends a person, wherever they are built, that
    names any that says the catalogue or, of the household's holdings, the collection;
    the operator's log and the start-up refusals are outside it and it says so.
  - A run that is gone is stubbed with what the server answers, a 404, and the run
    page shows the server's sentence for it; a test holds the 404 on opening a thread
    Ask has forgotten.
  - A test of a stale theme beside a wall being chosen for: the note says the theme is
    gone and the page is still choosing for that wall.
  - The test of a report for a wall with no display is named for what it protects: the
    guard that makes a wall unassigned mid-report harmless.
  - Setting an affinity by hand takes the service's clock and id source.
- **Acceptance:** the guard is red on each of the five sentences at its old wording and
  on one planted in a module it had not seen; each new browser test is red under the
  client break it names; a fixed clock and id source given to the taste service are what
  a set affinity carries, red today; no assertion is loosened.
- **Verification ceiling:** the curation and browser files it edits;
  `arrt/tests/unit/test_browser_reads_retry.py` and
  `arrt/tests/unit/test_client_vocabulary.py`; every test file that reads one of the five
  sentences (by grep); `arrt/tests/unit/test_surface_parity.py`; the governance suite
  whole; mypy, ruff and black in `arrt/`.

### Chunk 54: Records, and the change record

- **Type:** doc-only
- **Closes:** every chunk's *Records owed*, worked as a numbered checklist; C32, C34, C51; C49 and
  Q1's amendments if ruled.
- **Owns:** new `.prawduct/changes/audit-wave-2b.md`, `.prawduct/artifacts/observability-strategy.md`,
  `.prawduct/artifacts/data-model.md`, `.prawduct/artifacts/api-contract.md` (the HTTP sections),
  `.prawduct/artifacts/architecture.md`, `.prawduct/artifacts/operational-spec.md`,
  `.prawduct/artifacts/nonfunctional-requirements.md`, `.prawduct/artifacts/boundary-patterns.md`,
  `.prawduct/artifacts/player-contract.md` (§ Releases, and "What a Player does at 1.3.0"),
  `.prawduct/artifacts/build-plan-audit-wave-2.md` (its § Wave 2b becomes a pointer to this
  plan; its `dropped:` entries stay), `.prawduct/operator-verification.md` (the entries the
  visual chunks owe), and, only if the owner has ruled Q1, `.prawduct/artifacts/project-preferences.md`
  (the four norms) and `arrt/tests/unit/test_catalogue_store.py` (the forbidden-columns check).
- **Deliverables:** each sentence cites the file and line it describes (lesson 4: a delegate's
  report is evidence about intent, so each is checked against the code before it is written);
  the change record names each chunk's findings, `closes:` derived from the plan and checked on
  GitHub, the MCP break's migration note (45's) announced, contract 1.3.0's additions and what
  the Player does about them, interface 1.6 for the sources, and what is left open with its
  reason (#442 if not established, Q1-Q4, the third part). REL-M5X8 and SEC-K3V9 checked against
  the code (`--init`, `HostGuard`) and each closed with its evidence or filed.
- **Acceptance:** `prawduct-hook verify-records` 0 findings; `prawduct-hook check-change-log-entry`
  valid; `uv run pytest tests/preferences/test_citations_resolve.py tests/preferences/test_artifact_manifest.py
  tests/preferences/test_norm_index.py` green; every checklist item ticked or named as not done
  with its reason.
- **Verification ceiling:** `testament run --json=summary --suite governance`.
- **Model:** Sonnet-class, high.
- **Waits for:** every other chunk.

### Chunk 55: Integration and the boundary review (the coordinator's)

- **Type:** cumulative-final
- **Owner:** the coordinator, or one integrator it names; no build delegate.
- **Deliverables:** each delegate branch merged with its scoped merge commit, trailers counted
  first; the draft pull request opened once 28 and 29 are in (29's acceptance 5 seen there, and
  52's acceptance 4 on a scratch pull request); the governance suite whole after every merge that
  adds a tracked file.
- **Done when:** on the merged head the five suites pass (`testament run --json`); the image's
  test stage passes (`image.yml` by hand on the head); the coordinator has read each delegate's
  fail-first evidence and 45's byte count before its code; the Critic's cumulative review finds
  nothing blocking.
- **The operator's checklist, after the merge into `develop`:**
  1. Close by hand what the change record's `closes:` lists; `git-tidy --after-merge`.
  2. Cut `contract-v1.3.0` (an annotated tag on the merge commit), the way the 2026-11-13
     ruling records the owner approving a contract tag; the next plan's first commit copies
     the 1.3.0 release into `contract/released/` (28's guard demands it when the version next moves).
  3. Tell the Player's coordinator: 1.3.0's additions, each new must-refuse fixture needing a
     reason, C37. Tell the sources' coordinator: interface 1.6 and `link_gone`, the testing helper.
  4. Put Q4 (and #150) to the owner again; then branch protection, if not on yet, requiring
     "Lint, then every suite" only (never "The browser suite ran on the pool"), knowing it now
     waits for the real-Player pair, and that a fork's pull request can never pass it (C44).
  5. By hand on this machine: the `live_binary` dezoomify probe (40 edited `dezoomify.py`;
     ledger L6); the `live_api` OpenRouter probe if the generation lookup is to be re-checked (35).
  6. `drift-freshness.yml`: one manual dispatch after this reaches `main` (C40), if still owed.
  7. The real-Player test's docker path is first seen on the release's pull request into `main` (C36).
  8. The operator-verification entries 31, 34, 36, 41 and 42 owe.
