---
schema: 1
type: fix
scope: audit-wave-2b
date: 2026-11-20
title: "The audit's second wave, second part: one story about the walls and Players, the plugin host's answers kept apart, hang on any selection, spend that says what it does not know, not found as 404, and the MCP surface's one break"
---
This is the second part of the audit's second wave (`build-plan-audit-wave-2b.md`,
chunks 28 to 66, 55 the integration). Where the first part changed what is checked, this
part changes behaviour: what Status, Walls and the top bar say, what the acquisition queue
does with each answer a plugin gives, what a failed paid call is recorded as, which
status `/api` answers for a thing that is not there, and where an agent finds every act on
a wall. Every check it adds was shown red first, against the code before it or a
deliberate re-break. **It closes no GitHub issue outright**; § What is left open says,
for each issue the plan named, what is settled and what is not. The draft chunks 38 (one
view model per entity) and 46 (the docstring sweep) moved whole to a third part, with
their reasons in the plan (§ What moves to a third part).

### What each chunk settled

**The contract, 1.3.0, not yet cut (28, 47, 58, 59, 60).** `contract/released/1.2.0/`
is the 1.2.0 release frozen beside 1.0.0 and 1.1.0 (28), and from 58 it holds that
release's `transport.json` and `vocabulary.json` too, so HEAD is held to every answer and
word 1.2.0 published. 1.3.0 adds a Player's five states and their words to
`vocabulary.json` (`player_states`), 170 must-refuse fixtures (counted against
`contract-v1.2.0`'s index), each invalid row's `constraint` and `refused_because`, two
semantic rules of the client heartbeat (no two outputs of one name; at most
`MAX_OUTPUTS_PER_REPORT`, 32, of each), and **two answers that are not additive**, each a
bounded exception recorded in the plan's § Decisions made mid-build: one **corrected**, the
wall heartbeat's body that is not a JSON object is `400` in the error shape, as the client
heartbeat's is, where 1.2.0's table recorded the framework's `422` (47); and one
**narrowed**, the cap of 32 outputs and 32 label outputs, since a report past it was valid
under 1.2.0, whose schema bounds no list of outputs (40, 60). The package ships `py.typed`, and
`contract/tools/freeze_release.py` writes a frozen copy from a tag (59).
`player-contract.md` § Releases and "What a Player does at 1.3.0" have the detail.

**One health model (30, 31, 40, 60).** A wall's state and a Player's are the contract's
words, quoted on both sides with a test against the package (`programming/display_state.py`,
`programming/player_state.py`, `http/static/core/states.js`). `GET /api/health` and
`art_display(action='status')` answer `troubles` (faults) and `setup_steps` (steps not yet
taken: no wall, a wall no Player shows, a Player with no token or no first report), and
the top bar and the System badge count only the troubles; a Player not heard from and the
walls it shows are one trouble, named on the Player. **One step for one cause** (62): a
Player with no token, or awaiting its first report, is one step naming the walls that wait
for it, and those walls make no step and no trouble; a waiting wall's `display_state`
stays `silent` (a new state would be a contract change) and `GET /api/health` says
beside it whom it waits for (`waiting_for`), as `GET /api/walls`, MCP's `walls` and
`status` do since 66, from one function (`walls_waiting`). The question asked before a
hang says the server's words for a waiting wall ("The hall waits for The living room Pi,
which has no token yet.") and still says everyone sees a wall a Player shows change (66).
A wall waits only while nothing was ever written for it; one whose reports came and
stopped is a trouble. For one repaint the question before a hang could say a wall waits
while its badge showed a work, because one answer read the wall's report twice and a
first report could land between the reads. **Every walls answer now says everything it
says of a wall from one reading** (`HealthService.observe_walls`, `WallsReading` in
`arrt/src/arrt/programming/clients.py`): its state, its wait, who shows it, its display
and labels, and whether its Player reads the feed, from one survey of the placements and
one read of each report file, in one store scope. Before it, a Player assigned between
two reads could make one answer say `unassigned` beside the Player showing the wall, and a
wall deleted while the list was being built refused the whole answer. With four walls and
two Players a list of walls read each wall's report three times and each Player's ten;
now each once, and one wall's answer reads its own report and each Player's, once
(`test_a_walls_or_health_answer_reads_each_report_file_once_however_many_walls_and_players`
and the interleaving test beside it, `arrt/tests/integration/test_client_tools.py`).
`HealthService.observe_waiting`, the shape of the second read, is deleted (66, 55). Works the queue holds as failed are a
trouble too, with their count and the newest's age, linking to Queue (`failed_fetches`;
the instant is the queue's new `failed_at`, and a failure from before it reads "not
known", never guessed). `GET /api/clients` serves each Player's state and its settings
page's address when it passes the contract's pattern, which Settings › Players links to. A full disk
inside `dezoomify-rs` pauses the queue instead of failing the work; a report of more than
32 outputs is refused by name (40).

**The plugin host's second half (32, 33, 44).** An acquisition's outcome is one of `ok`,
`partial_tiles`, `none_held`, `unasked`, `faulted`, `link_gone` or `failed`, kept in a new
column beside the coarse status, which keeps its three values so an older release still
reads it; each outcome has its retry rule (`RETRY_RULES`), and Queue groups failures by
outcome and plugin rather than by the reason's text. Source plugin interface **1.6** adds
`LinkGone` (additive: a 1.5 plugin loads and behaves as before). Phase two answers with the
sources that answered within the look's 30-second window and keeps the slower answers in a
durable search record (`source_searches`), read on the work's next pass; the could-not-be-
asked counts survive a restart. Within one pass (the acquisition queue's, or phase 2's
over one run's works), a plugin that could not be asked three times in a row is not asked
again that pass (`HOLD_BACK_AFTER`), and the works it was not asked about are left exactly
as they were (33). **A plugin still owing one work's answer is not asked about the next**
(55, from the boundary review): while one of its calls is owed (`OWED_CALLS_PER_PLUGIN`, 1,
`arrt/src/arrt/library/sources/loading.py`), neither a run nor a queue pass starts another
there, and the work is not asked at that source, as a hold-back leaves it
(`image_pool.still_asking`, `source.plugin_still_asking`); before, a run going from work to
work started one call per work at a slow source. The queue's `failures` counts the
failures in a row under the retry rule of the last one, so could-not-be-asked passes no
longer use up the schedule's four tries (55; `data-model.md`, the queue's table). Its two
statements of when a work falls due are one (`_standing`), and a failure cause's sentence
names the museum its `museum` field names (`HealthService.museum_of`, 55).
`arrt.library.sources.testing` is a supported helper that drives the real host code for a
plugin's own tests (44); it stops before either fetch, a direct image's or tiles', through
the seams `AcquisitionService` takes (`open_stream`, `fetch_tiles`), not by overriding its
private methods (55).

**Hang on any selection, and from a wall (34, 57).** *Hang…* is in the selection toolbar of
Artworks, an Artist's works, Search and a Topic; it sends one `hang_selection` and says how
many works it left out. A wall's card offers *Choose works*, which opens Artworks selecting
for that wall and comes back to it (the owner's ruling of 2026-11-20). Hanging for a
duration is not built (the same ruling).

**Spend (35, 36, 60).** A paid call that fails after it was sent records a spend row whose
cost is unknown (`spend_records.cost_status`); every figure that sums the ledger counts
those calls apart, worded by one function as "at least $X, and N calls whose cost is
unknown", on runs, months, the unattended allowance and Watches. Since 62 every cost a
person reads is those words, shown as the server sent them, so a cost under a dollar is
said to a hundredth of a cent ("$0.0024" where a screen said "under $0.01"), something
spent below that reads "under $0.0001" (beside unknown calls, "more than $0.00, and N
calls whose cost is unknown"), never "$0.00", and a figure from a thousand dollars is
grouped ("$1,234.56") (66); Ask
records a call of unknown cost as unknown, never a known zero; a guard
(`arrt/tests/unit/test_one_cost_formatter.py`) refuses a dollar formatted in a screen.
System › Spend
(`#spend`, `GET /api/spend`) lists the current month and up to eleven earlier ones that
spent anything, by category and by Get, and every call whose cost is unknown. No generation
lookup was built: it answered 404 on every attempt (`openrouter-api-findings.md`).

**Not found is 404, and a refusal names the Library (37, 48).** Under `/api` a thing named
that does not exist answers `404`; every other refusal stays `400`, one error shape; MCP's
failure shape is unchanged and a Player's routes answer exactly as before (`api-contract.md`
§ the error model; the integration compared 35 cases byte for byte before and after). Programming's collaborators look walls and themes up through one `Lookups`, and
every act reads what it checks inside the transaction that writes (48). The refusal
sentences say the Library, not the catalogue, and so do the five other sentences a person
read that still said it (Status's description of a household with no wall, now "No wall
is recorded…", the notice after accepting a work the Library nearly holds, the backup
trouble and its panel, the queue's reason for pausing) (64). A guard reads every
sentence the server builds (`arrt/tests/unit/test_refusal_sentences.py`): every string
literal of two words or more in every module, less docstrings, a logger's arguments,
the start-up modules, code in another language and a model's prompt, and a few
sentences each with its reason. **Its limits, as it states them:** it cannot see a
sentence assembled from parts or a word arriving from a value (an enum's, a stored
name, a plugin's), a comment, or the client's JavaScript (which `test_client_vocabulary.py`
reads), and it names a literal in a module no person reads all the same. MCP's opening
instruction and thirteen client sentences were corrected with it.

**The publisher's two promises (39, 60).** The full reconciliation of every wall's feed
also runs as a scheduler job, at the first pass and every sixth (thirty minutes), so a lost
event is mended while the server runs; a feed over the contract's `max_bytes` is never
published (the act is refused and the wall keeps its old feed). Each act reads the clock
once. Removing a work from a theme writes `work.left_theme` on every wall the theme hangs
on, from every surface.

**The MCP surface, broken once, then grown (45, 53, 60).** The break the owner allowed in
ruling 3 of 2026-11-19: see the consumer note. A recording of the surface before it
(`arrt/tests/fixtures/mcp-surface-before-the-break.json`) and `test_mcp_break.py` hold
every other action, argument and result key unchanged. After it, MCP only grew: the twins
of this part's new fields, a new read-only tool `art_spend`, and a route inventory that
pairs every HTTP read route with an MCP action or names why not.

**Small client items (41, 63).** Counts are written one way; a Player and a Watch are
forgotten, a wall and a theme deleted, a work removed; the Work page links its Get and its
own history; a wall with nothing hanging says both ways to hang something there.

**CI and the image (29, 52, 56, 61).** The real-Player test is a testament suite of its
own, `player`, run on every pull request inside the required check; the fallback leaves it
out by name, as it does the browser suite (the owner's ruling of 2026-11-20). The fallback
runs each suite from the manifest's own command (52). `image.yml` builds the image's test
stage only on a pull request into `main` and by hand, and a root test holds what the stage
copies against what the tests open (56). Once the owner granted this project the pool's
host executor, the stage became a sixth suite, `image` (`.testament.toml`,
`tests/the_image_test_stage.py`), run in a full `testament run` from a machine doing the
work and never by CI, whose key holds no owner secret; a machine without one gets one red
verdict for the run (`no_warrant`) with the other suites' results inside it (65;
`docs/testing.md` § The image's test stage on the pool has its cost and what it leaves on a
runner). **Its first run found a test that passed everywhere but inside the image**: a
system test expected the server's working directory to be the checkout's, where the image's
is `/app`; chunk 64 made it take the path from where the server runs. A root test holds
the type gate to the fallback's environment, and `arrt_contract` left the type checker's
allowance once the package shipped `py.typed` (61).

**Checks that check what they say (49, 50, 51, 43, 63).** The catalogue schema check is an
equality, and found five tables it had let through unlisted; every release has a row in the
migration chain, held by a governance test (49). The system tests guard what a server
process publishes and where it writes, and are type-checked (50). Three sleeps became
conditions and a clause that could not fail was made to (51). `CatalogueService` and
`DiscoveryService` take a clock and an id source; the curation suite declares areas; the
UX walk names the states it must visit (43, 63).

**The compose example, hardened (42).** Every capability dropped, a read-only root, and a
64 MB `/tmp` tmpfs, which SQLite's sort spill was measured to need (`operational-spec.md`).

**The owner's rulings while it was built**: three on 2026-11-20 (an agent may post its
measurements on the issue it works; a hang can be started from Walls and hanging for a
duration waits; CI is kept small and makes no paid call) and six more the same day, "six
answers while part 2b was finishing"; each is in `.prawduct/owner-rulings.md`, with what it
changed in the plan in the plan's § Decisions made mid-build.

**Records (54).** The artifacts, `docs/testing.md`, `docs/source-plugins.md`,
`docs/ux-walkthrough.md` and `deploy/README.md` say what this part built, each against
the code it describes; the 2a plan's § Wave 2b points here.

**The boundary review (55).** The Critic's cumulative review of the whole branch
(`rev-20261120T181428Z-637817e0`) found nothing blocking, six warnings and twelve
observations, and a paired native review found eight more. The warnings: the 1.3.0 cap
narrows a minor the records called additive but for one answer; the no-paid-call guard read
only `.yml` workflows; the plugin-testing helper kept its no-network promise by overriding
two private methods, the tiled one untested; `HealthService.observe_waiting` had no caller
and was the shape of a double read; new server sentences hand-roll count agreement beside
`arrt.counting`; and a slow source's owed asks overlapped without bound. The native
review's: the queue's schedule counted failures of other rules; a walls answer still took
who shows a wall from a second reading, and read each report several times; a pass read a
settled work's item again; the queue had two statements of when a work falls due; and a
failure cause's museum came from another owner than its field's. **Fixed before the
merge**: all of these but the counting (left below), each in a commit naming Chunk 55; the
cap is recorded as the plan's DECISION and put to the owner. Three of the observations
are records corrected here (two governed-by dispositions' lists of chunks, the `/api`
inference the plan still carried, and the System link's words in
`operator-verification.md`); the comments the branch added that carried chunk numbers and
review ids now carry their reasons instead; those that ask for an edit and are not made are
left below, and the rest asked for none.

### What is left open, and why

**Issues the plan named, none closed here:**
- **#318** (Queue groups by message text) asks for grouping by a recorded cause key and
  for a measurement against the real library's failures. Chunk 32 built the first for
  every failure recorded since: the acquisition queue's row keeps the fetch's `outcome`
  and the `plugin` that said it beside the sentence, and Queue groups a classified
  failure by the two (`FailureCause`, `arrt/src/arrt/library/acquisition/queue.py`). A
  row recorded before the column has neither and groups by its words, as before, until
  the work is tried again. The measurement needs the owner's own library, which no
  delegate reaches; it is the operator's, after a Retry of the real queue.
- **#313** (a durable record of each search) asks for the record and for three columns on
  Status's sources table. The record exists (`source_searches`; `SourceSearch` and
  `SearchTally`, `arrt/src/arrt/persistence/discovery_records.py`): per source,
  `searched`, `answered`, `unasked` and `owed`, and when it last answered and was last
  asked, counted over the newest search of each work (the only one kept) for the 100
  works it was asked about most recently, and it survives a restart. Not built: a
  latency (each row keeps when it was asked and when it answered, and nothing computes
  the difference), a split of `answered` into found something and found nothing (each
  row keeps how many images it gave, and the tally does not divide by it), and the
  *Searches*, *Hit rate* and *Median latency* columns; the counts reach Status only in
  the source's sentence. The remainder is on the third part's list below.
- **#438** (cacheability): the two services' clocks and ids are injected, and the
  integrator's full run on the head with chunk 43 merged (`c4ceada5`, `--no-cache`;
  request ids `27dbbdf2`, `f9ae3248`, `5df08bac`, `27a9d59e`, `123b9e2c`) measured 49.6%
  uncacheable, 5,454 of 11,007. By reason, that run's figures: clock 2,257, subprocess
  1,695, socket 1,412, entropy 90; so about 3,100 are blocked for a real server process or
  a socket. The clock's share is the shared fixtures', in the third part.
- **#442** (a Skip test's flake) is **not established**. Ruled out, measured on the pool:
  CPU load alone, disk-sync load alone and many Chromiums, each well above the natural
  failures' load (chunk 51); ruled out from the code: the step that could fail to move on,
  since the route answers 200 either way and the client writes "Skipped." on that answer
  (chunk 39). Left: a lost click, an unanswered or refused POST, or a repaint detaching the
  card; every Skip test now waits for the POST's answer and asserts it, so the next red
  names which.

**REL-M5X8 and SEC-K3V9**, two items filed after the old markdown backlog was frozen
(`.prawduct/artifacts/archive/backlog-2026.md`), are settled in the code and have no live
home to close: a directory with neither the art root's marker nor a catalogue is refused
unless the server is started with `--init` (`arrt/src/arrt/art_root.py`,
`arrt/tests/unit/test_art_root.py`); every surface but the Player's checks `Host`, `Origin`
and `Sec-Fetch-Site` (`HostGuard`, `arrt/src/arrt/http/hosts.py`,
`arrt/tests/integration/test_host_guard.py`).

**The third part** (nothing in it is begun here): the surface's shape (draft 38: view
models, `api.py` by resource, the facade's removal, #307); the docstring sweep (draft 46);
configuration that imports no service; Ask's and MCP's executors; the six read routes with
no MCP twin (`/api/artists`, `/api/artists/{id}`, `/api/works/{id}/mat`,
`/api/works/{id}/placements`, `/api/sources/yields`, `/api/budget`), and an inventory of
the write routes, which the route inventory does not read; #313's remainder (a search's
latency, answered split into found and found nothing, and the sources table's *Searches*,
*Hit rate* and *Median latency* columns); the shared fixtures' clock and id source; batching the reconcile's per-work lookups (the cost below); the Library's
sentences that name a museum through `museum_name(` without the declared name (14 call
sites in six modules); the 25 direct clock reads in Programming's modules; the
prototype-scale test's `build_large_catalogue`; the browser tests that seed a time from
`datetime.now`; about 28 client strings that say "your library" (the owner is asked
whether the Library's capital belongs there too); the run's not-found page drawing the
router's words; `walls.js` joining `waiting_for` from `/api/health` rather than reading it
on the walls answer, which carries it since 66; a guard for the fixtures that write a
wall's report, which chunk 63 measured (about thirty lines, two exemptions and a marker)
and did not add; the cost words, which say a
spend under a hundredth of a cent two ways ("under $0.0001" alone, "more than $0.00, and
N calls whose cost is unknown" beside unknown calls), both true and left so; and the route
inventory, which pairs a read route with an MCP action by name only, so whether the twin
answers the same is left to the record-parity tests, which pair only some records (a
different gap from the write routes it does not read).

**Found by the boundary review, and left** (each checked at the merged head):
- **The Players answers pair a survey with a second one.** `GET /api/clients` (`_clients`,
  `arrt/src/arrt/http/api.py`), MCP's `clients` (`_list_clients`,
  `arrt/src/arrt/mcp/bindings.py`), and the answers to adding and renaming a Player
  (`http/api.py`) each take `placements.survey()` beside a `list_clients()` or
  `get_client_view()` that took its own: the two-readings shape the walls answers lost, unfixed.
- **Count agreement and digit grouping are hand-rolled beside `arrt.counting`.** The branch
  adds about a dozen server sentences that choose a noun or a verb by `== 1 else` (20 such
  lines in `arrt/src/arrt` at the head, 9 at the base), and two of them group digits
  (`f"{count:,} works"`, `arrt/src/arrt/services/health.py`) where `counted` does not, so the
  server writes a count of thousands two ways ("2,000 works", "2000 works"). Accepted for a
  third part (Critic R-5): give `counted` the grouping and route them through it.
- **A wall whose feed would exceed the size bound stops rolling forward**, and only a
  one-time journal line says so (`feed.over_bound`, `arrt/src/arrt/programming/feeds.py`):
  no trouble on Status, while the wall keeps its old feed until its horizon runs out.
- **`SourceSearch.images` is written and nothing reads it**
  (`arrt/src/arrt/persistence/discovery_records.py`): the yields question its docstring lists
  is not answered yet (#313's remainder, below).
- **Every top-bar health read scans every owed work to count the failed ones**
  (`AcquisitionQueue.failed_states`, read by `GET /api/health`): bounded and measured at
  2,000 failed works, but growing with the works owed an image rather than with the count
  and one age the top bar uses.
- **A Wikidata item changed while the queue sleeps** is caught only at the queue's next
  pass: a settled work falls due by an event no clock marks, the queue is nudged by a work
  accepted and by a Retry, and the identity service announces no change of item, so such a
  work waits for the next nudge or for `IDLE_SECONDS` (a day).
- **Two latent couplings.** `dezoomify.py`'s disk-fault words are keyed by hand against
  `atomic.DISK_FAULT_ERRNOS` (two members today), so an errno added to the set would raise
  `KeyError` where the queue pauses on `OSError`; and the health model works out a failure's
  instant for a row older than `failed_at` by inverting the queue's `RETRY_AFTER`
  (`failure_instant`, `arrt/src/arrt/services/health.py`), outside the queue that owns it.

**No workflow holds a model key** (66), as the owner's ruling of 2026-11-20 says: CI makes
no paid call. `api-drift.yml` has no paid job, no monthly schedule and no input that asks
for one; `drift-freshness.yml` watches the free tier alone; and
`tests/test_ci_makes_no_paid_call.py` allows CI exactly the secrets it names (the pool's
client key) and fails by name for any other a workflow reads, on any event, in a `.yml`
or a `.yaml` workflow alike, as `tests/test_actions_pinned.py`'s check of the jobs that
write issues does (55). The paid
probe is run by hand, `cd arrt && uv run pytest tests/live -m live_api -n0`. That answers
the standing question of #150 as the ruling answered it; the issue, opened by the drift
job, asks to be closed once someone has reconciled the findings against what the API
returns now, which is a hand run's to settle, so it is not closed here. The repository
holds no model key to delete: its secrets list names `TESTAMENT_KEY` alone (read with
`gh secret list` on 2026-11-20).

**For the owner** (Q2 and Q4 were ruled on 2026-11-20, `.prawduct/owner-rulings.md`): Q1 (the four norm texts in `project-preferences.md`, and with it the
forbidden-columns check in `test_catalogue_store.py`), Q3 (which household settings are set
where), **the 1.3.0 cap as an exception to "a minor is additive"** (`player-contract.md`
§ Versioning; the plan's DECISION, from the boundary review: ratify it, or have the cap
wait for a major), and the delegate-verification norm (`project-preferences.md` `## Workflow`,
`Delegate verification`), which says a change to `contract/` "runs all five" where there
are six suites: the owner is asked whether five, the suites that read the contract, is
what it should say. The host executor and the one scratch pull request were ruled (rulings 1 and 3 of
"six answers"). **An assumption to see at that scratch pull request:** that CI's key
holds no owner secret, so the pool step must never ask for the `image` suite, rests on
testament's guide and a simulation (the identity taken from the environment, as a CI job
has it), not on a run in GitHub's runner.

**For the operator's hands** (the plan's Chunk 55 checklist): close by hand what this
record settles; cut `contract-v1.3.0` on the merge commit and freeze it in the next plan's
first commit; tell the Player's coordinator about 1.3.0, including its two answers that are not additive, and the sources' coordinator about
interface 1.6 and the testing helper; branch protection, knowing the required check now
waits for the real-Player pair and that a fork's pull request can never pass it; the
`live_binary` dezoomify probe on this machine; one manual `drift-freshness.yml` dispatch
after this reaches `main`; the real-Player test's docker path, first seen on the release's
pull request into `main`; the one scratch pull request for the fallback, closed unmerged;
the paid probe by hand when the OpenRouter findings are to be re-checked (#150);
and the entries in `.prawduct/operator-verification.md`.

## Consumer note
**For a person running the server.** Status reads differently: setting up is not a
trouble. A wall no Player shows, a Player with no token and one that has not reported yet
are steps, listed under *Still to set up* and never counted on the top bar or the System
badge, one step per cause: a Player with no token that shows two walls is one step naming
both, and each wall's own panel says it waits for that Player rather than "Not
reporting"; *Needs attention* lists only faults, and two thousand failed fetches are now one of
them, linking to Activity › Queue. Spend has a page, System › Spend, and any total that
includes a paid call that never said what it cost reads "at least $X, and N calls whose
cost is unknown" rather than leaving the call out; a cost under a dollar is said to a
hundredth of a cent, where some screens said "under $0.01". A wall's card can start a hang with
*Choose works*. The first start widens the catalogue (five nullable columns on the
acquisition queue and the sources, `cost_status` on the spend records) and adds one table,
`source_searches`; **the shape generation does not rise, so the way back is the previous
image alone** (measured: the code 2a merged opens such a file and ignores the new columns
and table, and v0.11.0 sums an unknown-cost row as $0). **The feeds are reconciled every
half hour while the server runs**, not only at start, and a reconcile holds the store's
lock: measured in-process on one machine, seven passes after a warm one, with nothing to
fix, about 0.4 s at 2,000 works and 1.1 to 2.5 s at 5,000, so an act that arrives during
one can wait that long, longer on a slower machine; nothing was measured on the NAS. The
compose example drops every capability and runs read-only with a `/tmp` tmpfs; if you adopt
it, the `user:` it names must own the art root and the backup directory.

**For a reader of `/api`** (the browser is its only one, and `api-contract.md` says nothing
outside this repository may bind to it): a thing named that does not exist is `404`, every
other refusal still `400`, in the same `{"error": …}` shape. Everything else is additive.

**For an agent or script on MCP: the surface breaks once** (the owner's ruling 3 of
2026-11-19), and only here:
- Call `activate`, `hang_selection`, `unhang`, `not_again`, `kept_off`, `allow_again`,
  `scenes`, `draft_scene`, `pin_scene`, `unpin_scene`, `discard_scene`, `apply_scene` and
  `release_scene` on **`art_display`**, not `art_theme`.
- Call `clients`, `add_client`, `rename_client`, `remove_client`, `issue_client_token`,
  `assign_wall`, `assign_display`, `add_label`, `remove_label` and `unassign_wall` on the
  new **`art_players`**, not `art_display`.
- `not_again` takes no `scope` and keeps a work off every wall. To take a work out of what
  hangs on one wall, call `art_theme(action='remove', theme_id=<the wall's
  hanging.theme_id>, artwork_id=…)`, which now records that the work left the theme on
  every wall the theme hangs on.
- In `art_display` answers read `artwork_id` where you read `work_id`, and `has_reported`
  where you read `display_plane_has_reported`.
- An old call is refused with a message naming the new one; nothing is silently accepted.
  `work_id` stays on `art_review` and `art_discovery`, where it names a candidate work, and
  `status`'s `reported` passes the Player's heartbeat through in the contract's names.

What an agent can now ask, all additive: `art_display(action='status')` answers `players`,
`failed_fetches`, `troubles`, `setup_steps` and each wall's `display_state`;
`art_players(action='clients')` each Player's `state` and `settings_url`; a new tool,
**`art_spend`** (`history`, the twin of System › Spend); `art_catalogue` gains `queue`,
`failures` and `retry_failures` (a write: retry every work of one cause), `history` takes
`artwork_id`, `get` answers the Get a work came from and its acquisition's `outcome`,
`plugin` and `failed_at`, and the tool's title is *Art Library*;
`art_discovery(action='source_plugins')` answers the could-not-be-asked and search-record
counts; a run, the unattended allowance and a Watch carry `summary`, their cost in words
with any unknown calls counted inside them, and `art_discovery(action='spend')` and
`art_spend`'s totals carry `unknown_cost_calls` beside it. `art_watches`' delete is
described as forgetting a Watch. `art_display`'s `walls` and `status` say whom a wall
waits for (`waiting_for`), as the walls answer and Status do. A refusal names the
Library, not the catalogue.

**For Arrt Player: nothing to change now.** Contract **1.3.0 is not released**; `contract-v1.3.0`
is cut after this merges. When the Player moves its pin it must give a reason to each new
must-refuse fixture its table reads (170, and four client-heartbeat fixtures that pass the
schema and break a rule), and may quote `player_states` and replay the corrected heartbeat
row (`player-contract.md`, "What a Player does at 1.3.0"). **Two answers are not additive**,
and the Player's coordinator is told both: the corrected `not_an_object` row, to which a
Player reacts as before, and the narrowed cap, a client heartbeat of more than 32 outputs
or 32 label outputs refused whole, which the server has done since 2026-11-19 and which no
Player reaches (its writer should keep under it). Otherwise nothing a Player reads, writes or
requests changes: the integration compared every refusal row of `transport.json` and the
Player routes' unknown and retired cases (35 in all) before and after not-found became
404, and the answers were identical. Separately, for its next plan: the Player prints one
plain-text line among its JSON journal lines.

**For the private source plugins: interface 1.6.** A finder or reader may raise `LinkGone`
when every page the work's Wikidata item links at that holder is gone; the host settles the
work for that source and names it apart from could-not-be-asked. A 1.5 plugin loads and
behaves as before; one needing 1.7 is refused by name. Their tests can use
`arrt.library.sources.testing.host(...)` in place of reaching into phase two's internals
(`docs/source-plugins.md`).
