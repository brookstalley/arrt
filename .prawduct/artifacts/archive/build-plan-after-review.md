---
artifact: build-plan
version: 1
scope: after-review
branch: feature/after-review
partition: 01 ∥ 03 delegated, each in its own worktree and branch. 01 owns `library/acquisition/`, the catalogue store, `PreparationService`, the container's wiring, `app.py` and `__main__.py`; 03 owns the discovery service, its store, records and migration, and the verdict's vocabulary on HTTP, MCP and in `static/`. Neither touches the other's files; if 01 needs a way to record spend without a run, it adds one method at the end of `DiscoveryService`, the one shared file. Then 02, 04, 05 serial, because all three edit `mcp/tools.py`, `mcp/bindings.py`, `http/api.py`, `core/reviewing.js` or `screens/activity.js`. The coordinator merges each delegate, runs the three suites and the Critic per chunk
depends_on:
  - artifact: build-plan-topics-and-destinations
  - artifact: information-architecture
  - artifact: ia-proposal
  - artifact: data-model
  - artifact: architecture
governed_by:
  - artifact: architecture
    dispositions:
      - "Library/Programming seam rule 1, one-way imports → conforms: the acquisition queue and wanted works are Library; Programming learns a work became playable from the existing IMAGE_CHANGED event and the facade, as today"
      - "seam rule 4, Library changes reach Programming as events; reconcile at start → conforms, and the queue copies its shape: acceptance wakes it, and at start it catches up on every accepted work with no image, so a lost event delays a fetch and never loses one"
      - "operation logic lives only in the service layer → binds Chunks 01-05: the queue, want, and the Wikidata match are services; HTTP and MCP are thin bindings"
      - "RULING 2026-09-30: a binding that branches on one call's result is a violation → binds Chunk 05: Search again on a work with no item is two calls the client makes (match, then search), never a binding that matches and then branches into searching"
      - "Readiness: manifest membership is catalogue readiness, and the manifest build reports its exclusions → conforms: the queue makes `no_original`, `no_mat_color` and `no_rendition` exclusions clear themselves; it adds no readiness state of its own"
  - artifact: data-model
    dispositions:
      - "a work's QID is matched only by the holding museum's identifier, never by title (§ Artwork, Registry identity) → conforms by the owner's choice of 2026-10-02: the curator picks the item from Wikidata's matches for the title and artist, and it is recorded as the curator's (`IdentitySetBy.CURATOR` at acceptance, as a Get's chosen QID already is). Nothing is matched by title automatically"
      - "a persisted format is a lock-in decision; enumerate the questions first → binds Chunks 01 and 03: the questions are listed in each chunk, and become Q-rows in `data-model.md` § What this data must answer"
      - "the verdict state machine is closed at write time (`discovery.py` module docstring) → amendment proposed, at the owner's request (#168, 2026-10-02): `awaiting_better_image` becomes `wanted`, with one way in (`want`) that suppresses a scan only when one is named. The old rule's reason, that a turned-down scan is always suppressed, still holds: turning a scan down remains the only way to suppress one"
  - artifact: api-contract
    dispositions:
      - "§ Versioning, the rules: renaming a result enum value or changing an action's description is breaking; § Deprecation: announce, retire and annotate inline, no shims → binds Chunks 02 and 03: the verdict's rename and `retry_acquisition` no longer fetching in the call are both breaking, recorded in `api-contract.md`, annotated at the replacing site, and announced to the operator in the PR"
      - "§ Rejecting an image does not re-search; the re-search is the separate call (called paid until Chunk 05b found it free) → conforms: `want` searches nothing; Search again and Search all are `resolve_images`"
      - "§ `set_verdict` cannot set `awaiting_better_image`, one entry point → amendment proposed (Chunk 03): the one entry point becomes `want`, and `set_verdict` still refuses the verdict. The section's reason, that a scan turned down is always suppressed, is kept: suppression stays on the turning-down path. A resolve run that finds a scan still returns a wanted work to `pending`, as it does today from `awaiting_better_image`"
      - "§ 'exactly one tool spends' → inapplicable because it already does not hold and this plan adds no tool: `art_catalogue`'s `regenerate` and `set_mat_color` ask the vision model today; the queue is not a surface, and its spend is recorded (Chunk 01)"
  - artifact: information-architecture
    dispositions:
      - "the curation surface is laid out like the *arr apps; no new page without a precedent or a ruling (§ Direction) → conforms: Activity › Wanted is Lidarr's Wanted, placed by `ia-proposal.md` § Activity; acquisitions in flight join Activity › Queue as Radarr's downloads do. The line 'Wanted is not shown yet' is amended, with the owner's decision of 2026-10-02 (#168) as its authority"
      - "one row per screen in the three tables, held by `tests/preferences/test_screen_tables.py` → binds Chunk 05"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider, never by application code → conforms: the queue's mat-colour calls run under the provider's $20/month key limit, and a refused call falls back to the derived mat as `mat.py` already does. Chunk 01 records each call's spend (`SpendCategory.MAT_COLOR_VISION`, which exists and nothing writes) so the cost is visible, not so it is enforced"
      - "the Pi's memory → binds Chunk 01: one fetch and one preparation at a time, in one worker"
  - artifact: observability-strategy
    dispositions:
      - "a periodic job logs every pass, so one that died can be told from one with nothing to do (the preview and topic sweeps' rule) → binds Chunk 01"
      - "a deployment fault is journalled where it is raised (`acquisition.deployment_fault`) → conforms: the queue calls `acquire`, which already journals it; the queue adds the pause and its reason"
  - artifact: security-model
    dispositions:
      - "outside text reaches the page as text → binds Chunks 02, 04 and 05: a failure's detail, Wikidata's titles and creators are shown as text; a match's picture comes through the preview cache, as on the Artist page"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA; colour never the sole carrier of state → binds Chunks 02 and 05: queued, fetching, failed and wanted carry glyph and word"
last_validated: null
lifecycle: completed
archived: 2026-10-05
released_in: v0.2.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — After Review

## What this plan is

The "after Review" plan the owner asked for on 2026-10-02: two things that
happen to a work once a curator has judged it, which today happen to none.

- **An accepted work gets its image, and reaches its walls on its own** (#167).
  Today nothing fetches an accepted work's master image, and nothing prepares
  it either, so every work accepted through Get or Ask stays off every wall
  until an agent calls `retry_acquisition` and then `regenerate` by hand.
- **A work can be wanted, with or without a scan, and found again later**
  (#168). Today a no-scan work offers only Accept, which would mint a work with
  no image, and Reject, which suppresses it for good.

| Chunk | What | Issue |
|---|---|---|
| 01 | The acquisition queue: fetch, then prepare, with retries and a pause | #167 |
| 02 | Saying it: the Work page, Review, Activity › Queue, Retry, and MCP | #167 |
| 03 | One wanted state and one way in | #168 |
| 04 | Matching a wanted work to its Wikidata item, picked by the curator | #168 |
| 05 | Want and Forget on the card, and Activity › Wanted | #168 |
| 05b | A re-search spends nothing, said everywhere | found in Chunk 05 |
| 06 | The owner's review of the screens | both |

**Not in this plan:**
- **A scheduler.** `re-architecture.md` lists one under Library (wave 6+), for
  Watches and upgrades. The queue here is one worker with one job, shaped like
  the topic sweep. It is not a general scheduler, and it should be easy to fold
  into one when one exists.
- **Scheduled re-search of wanted works.** It waits for Watches (#168
  requirement 4).
- **Want on an Artist or Topic page's *No image known* works**
  (`ia-proposal.md` § The states). Those are registry works with no candidate
  row, so Want there would first mint a candidate. That is a small follow-on
  once Wanted exists, and is left out to keep Chunk 05 one review.
- **Wanted › Cutoff Unmet** (wave 4's quality profile) and **Wanted › Missing**
  (wave 6's Watches). Chunk 05 builds Wanted as one page, and those become tabs
  beside it when they exist.
- **The related acquisition items #65, #66 and #68.** Not duplicates, and not
  re-checked here.

## The owner's decisions, 2026-10-02

Recorded on #167 and #168 when they were filed:

- **#167: a background queue.** One worker thread, woken by acceptance, that
  catches up at start; retries after about 1 h, then 1 day, then 3 days, then
  stops with a Retry button; a partial result counts as acquired. Builder
  defaults the owner did not overrule: when disk is short (`MIN_FREE_BYTES`,
  2 GB) the queue pauses and Activity says why; no confirmation; one fetch at a
  time.
- **#168: Want and Forget on a no-scan card; Activity › Wanted with *Search
  again*, *Forget* and *Search all*; Search again first matches the work to its
  Wikidata item; re-search stays manual.** And: "'want a better scan' is not
  that different from 'want any scan at all'. … see if we can converge rather
  than having two paths." Chunk 03 is the answer: one state and one way in.
- **Build both in one plan.**

Asked while this plan was drafted, after reading the code:

- **The queue prepares as well as fetches.** Fetching alone does not put a
  work on a wall, because readiness also needs a mat colour and a current
  render (`architecture.md` § Readiness), and nothing prepares a work
  unattended either. A work's first preparation asks the vision model for its
  mat colour, at a fraction of a cent on `qwen3.7-flash`. The owner chose
  fetch then prepare over preparing with the free derived mat, or fetching
  only.
- **The curator picks the Wikidata item.** #168 requirement 3 asked for a
  title-and-artist match, but `data-model.md` § Registry identity rules that a
  work is never matched by title, and a candidate's QID becomes the artwork's
  identity at acceptance (`DiscoveryService._accept`). The owner chose a picker
  over a one-search automatic match and over storing an automatic match.

## What I would do differently

- **Rename the verdict, as the owner allowed.** `awaiting_better_image` is
  false for a work that never had a scan, and the IA already calls the state
  *Wanted*. One migration `UPDATE` and the vocabulary on two surfaces buys one
  name from the store to the screen. Chunk 03 does it.
- **Turning down an alternate should not make a work wanted.** Today
  `reject_image` sets `awaiting_better_image` whatever was turned down, so a
  curator who rejects a poor alternate under a scan they like has, without
  being told, asked for a better one. Once Wanted is a page, that work turns up
  on it with no reason the curator can see. Chunk 03 makes turning down the
  scan on offer mean "want a better one", and turning down an alternate only
  turns it down.
- **Route MCP's `retry_acquisition` through the queue.** Today it fetches
  synchronously, for up to 30 minutes, and could run beside the queue's own
  fetch. That would break one fetch at a time on the Pi. Chunk 02 makes it the
  Retry button: it wakes the queue and returns at once.
- **Record what preparation spends.** `SpendCategory.MAT_COLOR_VISION` and a
  spend row's `artwork_id` exist, and nothing writes them. Unattended
  preparation turns an occasional cost into a routine one, and the spend
  report should show it.

## Requirements Confidence

**Medium.** The owner's decisions settle what to build. Three things are
inferred from the code and not yet exercised:

- **How many accepted works have no image** on the owner's deployment, which
  sets how long the first catch-up runs. **Counted 2026-10-02 (Chunk 01) on the
  catalogue copy in the session scratchpad: 0** — its 40 accepted works all hold
  an original, and it holds no *Hunters in the Snow* (that was another copy).
  The owner's deployment is still uncounted; Chunk 06 counts it on a fresh copy. A tiled fetch may run up to 1800 s
  (`TILE_TIMEOUT_SECONDS`), so a backlog of 20 could take hours, unattended.
- **Whether Wikidata's `works_matching` finds the Dalí works by title** well
  enough for a picker. It returns a creator with each match, which is what
  tells two *The Kiss*es apart. Chunk 04 measures it on the seven Dalí works
  first.
- **Whether a first preparation on the Pi fits memory beside the server**,
  straight after a gigapixel fetch. Today they run as two separate MCP calls.

Open assumptions:

- `[ASSUMPTION: the queue fetches accepted works only, never archived ones; restoring an archived work announces ACCEPTED, which wakes the queue for it | MED impact | user can correct]`
- `[ASSUMPTION: every condition acquisition raises for rather than records (`_DEPLOYMENT_FAULTS`: a short disk, no dezoomify-rs, a provider with no resolver) pauses the queue the same way, since none is one work's fault and none is fixed by retrying that work. A paused queue tries again every 15 minutes and on every wake, and counts no attempt against the work | HIGH impact | user can correct]`
- `[ASSUMPTION: an attempt counts as a failure only when `acquire` records one (`AcquisitionOutcome.FAILED`), or preparation refuses. KEPT_HELD cannot happen to a work with no image. After the 4th failure (the first try plus the three retries) the queue gives up until Retry | MED impact | user can correct]`
- `[ASSUMPTION: a preparation failure after a good fetch counts as that work's failure and is retried on the same schedule, re-preparing without re-fetching, since the image is held and `acquire` is not re-run for a work that has one | MED impact | user can correct]`
- `[ASSUMPTION: works are fetched oldest acceptance first, and a Retry moves the work to the front | LOW impact | user can correct]`
- `[ASSUMPTION: Retry resets the work's failures and wakes the queue; it never fetches in the request. MCP's `retry_acquisition` becomes the same call, so its `source_id` is carried on the queue's row for the next attempt and its answer says 'queued' rather than the fetch's outcome | HIGH impact | user can correct]`
- `[ASSUMPTION: the verdict is renamed `wanted`, in the store by migration and on every surface; the API and MCP accept no old spelling, since both have one client each and they ship with the server | MED impact | user can correct]`
- `[ASSUMPTION: Want without naming a scan is allowed on any undecided work, not only a no-scan one, and suppresses nothing; the card offers it only where the owner asked (no scan). Turning a scan down stays the only way to suppress one | MED impact | user can correct]`
- `[ASSUMPTION: a curator's 'none of these' in the Wikidata picker is not stored: the work is searched without an item, and the picker is offered again next time | LOW impact | user can correct]`
- `[ASSUMPTION: Search again and Search all use the existing re-search (`runner.resolve_images`), which spends the phase-two estimate per work; the button says so with the estimate, as the run review's re-search offer does, and asks no confirmation | MED impact | user can correct]`
  **Found false while building Chunk 05:** the phase-two estimate is zero, so Wanted says searching spends nothing, and Chunk 05b corrects the rest.

**What would raise it:** counting the accepted works with no image on a
fresh copy of the owner's catalogue (one query, Chunk 06's first step; the
scratchpad copy held none), and Chunk 04's measurement on the Dalí works.

## Status

- [x] Chunk 01: The acquisition queue
- [x] Chunk 02: Saying it: the Work page, Review, Activity › Queue, Retry, and MCP
- [x] Chunk 03: One wanted state and one way in
- [x] Chunk 04: Matching a wanted work to its Wikidata item
- [x] Chunk 05: Want and Forget on the card, and Activity › Wanted
- [x] Chunk 05b: A re-search spends nothing, said everywhere
- [x] Chunk 06: The owner's review of the screens

### Chunk 01: The acquisition queue

**The questions the queue's stored state answers** (a persisted format; these
become Q-rows in `data-model.md` § What this data must answer):
1. Which accepted works hold no master image, and are due a fetch now? (The
   worker, at start and on every wake.)
2. How many times in a row has a work's fetch or preparation failed, and when
   may it next be tried? (The retry schedule: 1 h, 1 day, 3 days.)
3. Why did the last attempt fail, in words a curator can act on? (Work page,
   Queue.)
4. Has the queue given up on this work? (The Retry button.)
5. Which source should the next attempt use, when someone named one? (MCP's
   `retry_acquisition`.)

What is in flight, and why the queue is paused, live in memory: a restart
re-derives both by asking again.

- **Library:** new `library/acquisition/queue.py`, an `AcquisitionQueue` with
  `nudge`, `wait_for_work`, `run` (one pass), `retry(artwork_id, source_id=None)`
  and `state_of(artwork_ids)`, plus `start_acquisition_queue`, copying
  `topic_sweep.py`'s shape: woken on `WorkChange.ACCEPTED`, a pass at start,
  INFO on every pass, a bounded join at shutdown. A pass takes the due works
  one at a time: `acquire`, then `PreparationService.prepare` once an image is
  held.
- **Store:** the queue's state, keyed by artwork id, in the catalogue file
  (Library), shaped by the questions above. New table or columns, decided at
  build time. It is widened in place by `SqliteDurableStore`, so no migration.
- **Spend:** `PreparationService` records a `MAT_COLOR_VISION` spend row with
  the artwork's id whenever the model was asked, on every path, MCP's included,
  so the record follows the call and not the route in.
- **Wiring:** `arrt/src/arrt/services/container.py` subscribes the queue's nudge to
  acceptance, as it does the topic sweep's; `create_app` starts it only when
  asked (`acquire_queue=True` from `__main__`), for the reason the sweeps are
  off in tests.
- **Observability:** `acquisition.queue_pass`, `acquisition.queue_paused` (with
  the condition), `acquisition.queue_gave_up`, and the existing
  `acquisition.deployment_fault`.

**New structural context:** a worker thread. Cross-cutting concerns: errors,
since a pass that raises is logged and the loop survives (the sweep's broad
catch, waived the same way); observability, as above; configuration, since
`MIN_FREE_BYTES` and the tile timeout already exist and the retry schedule is
code constants; auth, none, since it calls services directly.

Done when:
1. The count of accepted works with no image on the catalogue copy is recorded
   here (Requirements Confidence).
2. Tests, through the container with the queue started against a double
   behind `acquire` and `prepare`: acceptance leads to an acquired and prepared
   work; a work accepted while the queue is stopped is fetched at the next
   start; a failure is retried at 1 h, 1 day, 3 days by an injected clock and
   then given up; a partial result is not retried; a short disk pauses without
   counting an attempt and resumes when space returns; two acceptances during a
   fetch are both fetched, one at a time; an archived work is not fetched.
3. Each new test is watched failing once against a re-break (core.md).
4. `data-model.md` gains the Q-rows and the table; `architecture.md`
   § Readiness says what now clears `no_original`.
5. All three suites, lint and format green; Critic.

### Chunk 02: Saying it: the Work page, Review, Activity › Queue, Retry, and MCP

**Exposed API:** `GET /api/works/{id}` (gains the work's acquisition state),
new `POST /api/works/{id}/acquisition/retry`, new `GET /api/acquisitions`
for the Queue, and
`art_catalogue(action='retry_acquisition')`. (The plan first said
`/api/artworks/…`; the routes are `/api/works/…`, and the build follows them.)

**Decided while building, 2026-10-02:**
- `[DECISION: Activity's count stays To review's; the images being fetched are not counted on Activity's link | `arrt/src/arrt/http/static/core/awaiting.js` and the IA call To review the one queue that needs the curator, and a fetch needs time, not the curator; a gave-up or paused fetch is said on Activity › Queue and on the Work page | owner can veto]` This replaces "Activity's count includes them" below.
- `[DECISION: an unexpected error raised during one work's attempt counts as that work's failure, on the retry schedule; only an error outside any attempt pauses the queue | a pause left the failing work first in line, so one work that always raised held every work behind it (Chunk 01's review) | owner can veto]`
- `[DECISION: a Retry on a work with no source is refused at once, not queued to fail | nothing a retry schedule does gives a work a source | owner can veto]`
- Every candidate work gains `artwork_id` on HTTP and MCP, so an accepted Review card can find its fetch.

- **Work page:** "No master image has been acquired for this work yet"
  becomes one of: *Queued*; *Fetching since …*; *Failed: why, next try at …*;
  *Gave up after 4 tries: why* with **Retry**; *Paused: why* (the deployment's
  reason and remedy, the sentence `_retry_acquisition` already writes, moved to
  one place both surfaces read).
- **Review:** an accepted card says the same in one line, so a curator who
  just accepted sees that the fetch has started.
- **Activity › Queue:** a section beneath the runs listing the queued,
  fetching, failed and given-up works, and the pause with its reason when
  paused (Radarr's Queue holds downloads). Activity's count includes them.
- **MCP:** `retry_acquisition` calls `queue.retry` and returns the queued state.
  Its tool text says it no longer fetches in the call. `art_catalogue(action='get')`
  carries the acquisition state.

- **Carried from Chunk 03's review:** MCP `resolve_images`' description and
  example in `arrt/src/arrt/mcp/tools.py` still say "works whose instances the
  curator turned down" / "awaiting a better image", while `want` sends an agent
  there for a work with no scan. Say *wanted works*, and record the
  description change in `api-contract.md` (§ Versioning treats it as breaking).
- **Carried from Chunk 01's review:** an unexpected error (not a deployment
  fault, not a `ServiceError`) pauses the whole queue without counting against
  the work, so one work that always raises one holds every work behind it.
  Decide here, once Activity shows the pause, whether repeated errors on the
  same work count against it. And `queue.py` imports `service.py`'s private
  `_DEPLOYMENT_FAULTS`; make it public if this chunk reads it too.

Done when: browser tests for each Work-page state and the Retry button, and
the Queue section; `information-architecture.md`'s Queue row and the screen
tables amended; `api-contract.md` records the retry change; the operator
verification queue gets the Work page and Queue entries (**Visual change:** yes);
suites green; Critic.

### Chunk 03: One wanted state and one way in

**The questions the verdict answers, unchanged except for its name:**
1. Which works does the curator want and not yet hold? (Activity › Wanted.)
2. Was this work wanted because a scan was turned down, or because none was
   found? (Read from its instances, not stored: a wanted work with a turned-down
   instance was turned down.)

- **Store:** `Verdict.AWAITING_BETTER_IMAGE` becomes `Verdict.WANTED`
  (`"wanted"`), with a migration in `persistence/migrations.py` that rewrites
  the rows, idempotent and safe to interrupt like its siblings. The store gains
  `list_wanted_works()`.
- **Service:** `DiscoveryService.want(candidate_work_id, *, turning_down=None)`
  is the one way into `wanted`. Given a scan, it turns that scan down exactly as
  `reject_image` does now (suppression, the vacancy filled) in the same
  transaction. `reject_image` becomes "turn this scan down": when the scan was
  the one on offer it calls `want(turning_down=…)`; when it was an alternate it
  only suppresses, and the verdict stands. `set_verdict` still refuses `wanted`,
  now naming `want`. The "exactly one entry" claims in the module docstring,
  `reject_image`, `Verdict`, `http/models.py`, `http/api.py` and MCP's tool text
  are rewritten, and the tests that guard them are rewritten to the new rule
  (core.md: re-read each test's name against its new assertion).
- **Surfaces:** `POST /api/candidates/{id}/want` with an optional
  `turning_down`; `art_review(action='want')`; `GET /api/wanted` and
  `art_review(action='list_wanted')`; the API's and MCP's verdict vocabulary
  says `wanted`. The client's `VERDICT_GLYPHS`/`VERDICT_WORDS` and every
  `awaiting_better_image` in `static/` follow (grep the whole repo for the old
  spelling, artifacts included).

Done when: tests for want with and without a scan, turning down the scan on
offer vs an alternate, set_verdict's refusal, the migration over a file holding
old rows (run twice); suites green; Critic.

### Chunk 04: Matching a wanted work to its Wikidata item

**Foreign API:** Wikidata (`Registry.works_matching`)

- **Service:** `DiscoveryService` (or a small sibling) offers
  `wikidata_matches(candidate_work_id)`, Wikidata's works matching the work's
  title, with each one's creator and picture, the work's proposed artist's
  matches first; and `set_wikidata_item(candidate_work_id, qid)`, refused on a
  decided work. A QID set here becomes the artwork's at acceptance, as the
  curator's, exactly as a Get's chosen QID already does.
- **Surfaces:** `GET /api/candidates/{id}/wikidata-matches`,
  `PUT /api/candidates/{id}/wikidata-item`; MCP's `art_review` gains both. With
  no `WIKIDATA_USER_AGENT` both say matching needs it.

Done when: 0. verify-api: run `works_matching` live on the seven Dalí works and
*Lobster Telephone* (Q2990594), and record what came back in
`wikidata-findings.md`; tests against a double built from that answer; suites
green; Critic.

**Built 2026-10-02.** verify-api ran live: the seven no-scan Dalí works
(*Lobster Telephone* among them) answered as recorded in `wikidata-findings.md`
§ Matching a wanted work. It changed the design in one place: the search is the
title **with the artist's name** first, the title alone only when that finds
nothing, because the title alone missed the Dalí *Mountain Lake* entirely. The
service is `WikidataMatchService` (new module) rather than a method on
`DiscoveryService`, since it needs the registry and discovery does not hold one;
the write stays in `DiscoveryService.set_wikidata_item`. Pictures in the picker:
none in this chunk; each match says `has_image`, and Chunk 05 links it to the
registry Work page (`#work/Q…`), which shows Wikidata's picture.

### Chunk 05: Want and Forget on the card, and Activity › Wanted

**Visual change:** yes

**Built 2026-10-02, and what changed on the way:**
- **No pictures on Wanted** (descoped, the builder's call): `GET /api/wanted`
  carries none, and a picture per row would be a request per wanted work. Each
  work's Wikidata link opens the registry Work page, which shows Wikidata's
  picture, and the picker says whether each item has one. The owner can ask for
  pictures in Chunk 06.
- **Want and Forget appear once the search has finished and found nothing**
  (`resolution_status` `unresolved`), not on a card whose search is still
  running, which has found nothing *yet*.
- **"Turn it down" keeps its label**; on the scan on offer its accessible name
  and the card's note after it say the work now waits in Wanted. Six existing
  tests click the label, and the action is the same.
- **Search all starts one re-search per originating search**, in the client,
  as `resolve_images` requires, and opens Queue when there are several.

**Carried from Chunk 04's review:** split the title in `WikidataMatchService.matches`
with `registry_search.py`'s word splitter (`_WORDS.findall`), so "Life," or
"(Premonition" is not dropped by the registry's word filter; and a test that
picking an item on a **wanted** work is allowed (it holds only because `wanted`
is not a terminal verdict).

**Found while building Chunk 02:** `art_discovery(action='resolve_images')`
requires every work to come from the same discovery run, so **Search all**
across runs needs one re-search per run (several runs, several prices), or that
rule relaxed with its reason re-read first (`api-contract.md` § Rejecting an
image… records why a resolve run has a `parent_run_id`).

- **Review card:** a work with no scan on offer and none found offers **Want**
  and **Forget** in place of Accept and Reject. Forget is `rejected`, and its
  label says it stops the work being proposed again. *Turn it down* on the scan
  on offer says the work will wait in Wanted.
- **Activity › Wanted:** every wanted work, newest first, each with its
  picture where one exists, why it is wanted (no scan found, or *N* scans
  turned down), its Wikidata item or "No Wikidata item", the run it came from,
  and **Search again** and **Forget**. **Search all** with the estimate. Search
  again on a work with no item opens the picker first (Chunk 04), then
  re-searches; the client makes the two calls. The sidebar shows Wanted with
  its count only once something is in it (`ia-proposal.md` § The map).
- **IA:** `information-architecture.md` amends "Wanted is not shown yet",
  adds Wanted's row to the three screen tables, and records the owner's
  decision as its authority.

Done when: browser tests for Want and Forget on a no-scan card, the Wanted page
(both reasons, Search again with and without an item, Forget, Search all), and
the sidebar's count; `test_screen_tables.py` green; the operator verification
queue gets entries; suites green, browser suite under `-n auto`; Critic.

### Chunk 05b: A re-search spends nothing, said everywhere

**Found while building Chunk 05, 2026-10-02.** `RunnerSettings.phase2_estimate_usd`
returns zero, "measured, not assumed" (2026-08-02): phase 2 asks open museum and
Commons APIs and makes no model call, and nothing writes an `IMAGE_RESEARCH`
spend row. Yet the review page ("a re-search is what looks, and it spends"),
MCP's `want`, `reject_image` and `_nothing_searching` texts, `http/api.py`'s
docstrings, `api-contract.md` § "Rejecting an image does not re-search — that is
a separate, paid call", and comments in `discovery.py` and `reviewing.js` still
say a re-search spends. Sweep the whole repo for the claim (no `--include`),
rewrite each to what the code does (free today; the price returns if a paid
image provider is added), and record the MCP description changes in
`api-contract.md` § Versioning. Chunk 05's Wanted page says it correctly from
the start.

### Chunk 06: The owner's review of the screens

**Type:** cumulative-final

**The owner's review, 2026-10-02** (on the review server and an older one; "looking
good! Some improvements to be had"). The owner asked the builder to "use your
judgment on sequence":
- **Built here:** a labelled field and its button now share a bottom edge
  everywhere (Create on Themes; Rename, Make default and Delete beside a theme's
  name; Look up on the Artist page; Want or Accept beside *Why*). One rule
  (`.row > .field` kept its bottom margin), one browser test. And the
  Wikidata form on the Artist and Work pages no longer shows before Change… is
  pressed: `hidden` lost to `.stack`'s display; one global `[hidden]` rule fixes
  it and every other class that would have done the same.
- **Filed for one "Library screens" plan after this PR, with #169** (the theme
  rail and a Select mode): the typeahead's and Topic page's held / image-found
  states (the owner: "Does image found mean held?" — no; and on a Topic page an
  image-found work shows a thumbnail while a held one does not); the Artists
  index (sort by surname, use the width: cards, grid or a view toggle); the
  Artist page's Wikidata controls; Library › Topics' single long column.
- **Still owed:** the count of accepted works with no image on the owner's real
  deployment. The scratchpad copy holds none; the PR says the first catch-up's
  length is unmeasured.
- **Deferred to deploy, on the record (cumulative review R-2):** this chunk's
  live checks (accept a work and watch it fetch, prepare and reach the manifest;
  break the tile binary and watch the pause). The copy the owner reviewed holds
  no accepted work without an image, and its masters are not on disk, so nothing
  was fetched live; the queue's first real fetch is on the owner's deployment.

First, count the accepted works with no image on a fresh copy of the owner's
catalogue, and record it in Requirements Confidence. Then, on that copy: accept
a work and watch it fetch, prepare and reach the
wall's manifest; break the tile binary path and watch the queue pause and say
why; want the seven Dalí works, pick *Lobster Telephone*'s item, and search
again. Whatever the owner asks for is built here or filed. Then the cumulative
Critic, and `/prawduct:pr`.
