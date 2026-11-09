---
artifact: build-plan
version: 1
scope: watches
branch: feature/watches
base: develop
working-branches: []
last_validated: 2026-11-09
depends_on:
  - artifact: agents-and-memory
  - artifact: re-architecture
  - artifact: build-plan-unattended-settings
  - artifact: data-model
  - artifact: information-architecture
governed_by:
  - artifact: security-model
  - artifact: observability-strategy
  - artifact: nonfunctional-requirements
  - artifact: data-model
  - artifact: architecture
  - artifact: api-contract
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
partition: serial — 02 to 05 each build on the one before (store, then the scheduler that reads it, then the screen that reads both), and 01 is the record the rest is built against
---

## Goals

**Response taken:** Ask, in one batch, answered 2026-11-09. This is the second half
of `agents-and-memory.md` item 4 ("Unattended agent settings, then Watches"). The
first half, `build-plan-unattended-settings.md`, is merged to develop and not
yet released. The owner chose the advisor's recommendation each time:

- **Review only.** A Watch puts every find in To review. Auto-accept is not
  offered, and neither is notify-only, because in Arrt a find *is* a review card.
  This answers `re-architecture.md` § Open questions, "whether auto-accept is
  offered at all".
- **Only verdicts shape taste** (open question 2 of `agents-and-memory.md`).
  Nothing a Watch finds reaches taste or any prompt until the curator accepts or
  rejects it, and then it does so exactly as any other verdict does.
- **Browser only for alerts.** Settings › Watches and the status indicator show
  a Watch that is overdue or refused, and every scheduler pass logs one positive
  line. Push notifications stay deferred, and the revisit trigger is rewritten
  as what remains (`observability-strategy.md`).
- **Each Watch has its own cadence and an optional monthly cap.** The cadence
  defaults to `unattended_cadence`. The cap must fit under the unattended
  allowance.

**Product:** a household writes a standing request in words ("new abstract
expressionist pieces in museum collections"), and Arrt runs it on a cadence
with nobody watching. Arrt spends inside the allowance the household set in
Settings › General, and only leaves the finds in To review. It is the *arr
apps' monitored list (Radarr's Lists), and the product's first unattended agent
work (ruling 5).

**Architecture:**
- **The scheduler is the Library's, in the server process.** It is a single
  thread in the same shape as the topic sweep: it wakes, finds the Watches that
  are due, asks permission for each and starts a run. Upgrades (#178) are its
  intended second job, so the scheduler knows jobs, not Watches. Watches are the
  only job this plan registers.
- **A Watch run is an ordinary discovery run** (`DiscoveryRunner.start`), with
  `initiated_by=unattended` and a new nullable `watch_id` on the run. It spends,
  dedups, proposes and is reviewed exactly as an Ask is. Nothing new reads a
  page or calls a model.
- **Permission comes from one place.** Before each run the scheduler asks
  `UnattendedAllowance.standing(estimate)` and then the Watch's own cap, and
  records the refusal on the Watch when either says no. `initiated_by` is still
  never an authorisation input. The scheduler checks permission because it is
  the thing starting unattended work, and the run's attribution stays what it
  was.
- **Programming reads nothing of Watches** (seam rules 1–3). No feed, media or
  Player route reads one (ruling 6).

**Constraints:**
- No new dependency. No hostnames or addresses (the repo is public).
- The month is UTC's (`library/months.py`).
- No Watch runs until Chunk 01's re-derivations are on the record
  (`security-model.md`: "before any Watch runs"). Chunk 01 comes first for
  that reason.

**Tradeoffs accepted:**
- **Run on the scheduler's clock, not catching up.** A Watch due while the server
  was down runs once when the server comes back, never once for each slot it
  missed. Revisit if a household needs runs at set times of day.
- **Hourly is the finest cadence** (`Cadence`). Revisit if a Watch needs finer.
- **App-enforced caps fail open on a ledger bug**, as the allowance does. The
  provider's key limit still stops the bill (`build-plan-unattended-settings.md`
  § Tradeoffs).

**Descoped explicitly** (from `data-model.md` § Watch and `re-architecture.md`
§ Procurement, both written before any design):
- **`facet_filter` and `sources`.** A run is driven by its words alone today. A
  Watch's words can name a movement or a museum, as an Ask's can. Revisit once
  facet population (wave 6+) gives runs facets to filter on.
- **`on_match`.** There is one policy, so there is no field. A later
  auto-accept would add one with a migration.
- **Wanted › Missing for a Watch.** A Watch's intent is open-ended, so there is
  no list of works it lacks to show. The IA's mention is amended to say so.
- **"Also make a playlist from this Watch".** Smart playlists do not exist yet.

**Inferred, for the owner to veto** (none was ruled):
- **External identity is not a prerequisite.** `re-architecture.md` lists
  "external identity for works and artists, before Watches". Dedup by key, plus
  the rejected-candidate records, already keeps a Watch from offering a work
  twice. The series-title collision ("Untitled") is a risk today for every run,
  and a Watch makes it no worse per run, only more frequent. Revisit if a Watch
  is seen offering a held work again.
- **A Watch can be written and changed over MCP**, because the parity rule
  holds (`product-brief.md` item 8), and the owner ruled settings writable over
  MCP on 2026-11-09. Chunk 01's re-derivation counts what this costs.
- **One run per Watch at a time.** A Watch with a run still in flight is not
  started again. Runs of different Watches may overlap, each priced by its own
  check.
- **A Watch whose last run failed or was interrupted is due again at the next
  pass**, not at its full interval (tacularr's "due again soon",
  `upgrades.md`), at most once per hour, so a broken Watch cannot loop.
- **The estimate is phase 1's** (`DiscoverySettings.phase1_estimate_usd`), and
  phase 2 is free. It is what an Ask is priced at.
- **A new Watch is due at once.** It runs at the next pass, so the household
  sees whether its words find anything.
- **The Watches screen sits at Settings › Watches**, where the IA already puts it
  (Radarr's Lists). Its rows are added to the screen tables before the client
  routes it.

**Decisions made mid-build:**
- Chunk 03: a Watch is removed with `DELETE /api/watches/{id}`, not `POST …/delete`.
  Settled by the surface's own convention: `DELETE` is how affinities, themes and
  walls are removed.
- Chunk 03: `art_watches` is not in Ask's scope. Settled by `ASK_SCOPE`'s rule
  ("nothing that spends or reaches a wall"), which already keeps `art_settings` out.
- Chunk 03: the record holds `cadence` and `last_refusal` as text, and the service
  owns their meaning. Settled by the layering: persistence imports no Library
  service, and `StoredSetting` holds its value the same way.
- Chunk 03: a cap is refused while the allowance is below it, even at $0.00, with a
  refusal naming where to raise the allowance. Settled by the allowance's own rule
  under the budget ("refused when written, read as the bound").
- Chunk 04: the unattended model reaches phase 1 as `WorkListRequest.model`, passed
  per call to the client (`model=` on `complete`), not through a second engine.
  Settled by "do it right": one engine, one client, and nothing else differs.
- Chunk 04: a Watch's run is in flight only while the runner has it in hand
  (`DiscoveryRunner.is_working_on`), never because its status is not terminal. On a
  deployment with no image engine a run rests in `resolving_images` for good, and a
  status-only rule would have held its Watch for ever. Found by the suite, whose
  container wires no phase 2. The goals did not foresee this.
- Chunk 04: a pass every five minutes (`PASS_SECONDS`), the first at start. Settled
  by hourly being the finest cadence. Inferred.
- Chunk 04: `could_not_start` is a fifth refusal, for a start the runner refused
  (no engine). Settled by "each refusal is stored with its reason".
- Chunk 04: overdue is an hour past due with nothing tried (`OVERDUE_AFTER`), not
  one cadence. Settled by what overdue is for: a live scheduler tries a due Watch
  within a pass, and a weekly Watch must not take a week to show a dead one. Found
  by the Chunk 04 review.
- Chunk 04: a pass prices each start on top of what it has already started that
  pass, so several due Watches cannot all start on room for one. Found by the
  Chunk 04 review.
- Chunk 04: a Watch's run is estimated at the discovery model's price, not the
  unattended model's, which Arrt has no price for. Accepted: the estimate is the
  look-ahead, the spend recorded after each run is what the next check reads, and
  the provider's key limit is the ceiling. Revisit if a dearer unattended model
  is seen passing its cap by more than a run.
- Chunk 04: nothing tests that the deployment entry point passes `schedule=True`;
  `__main__` has no test for its `create_app` flags (the topic sweep and the queue
  are in the same position). Recorded rather than built here, because the entry
  point calls `uvicorn.run` and a test of it is its own piece of work.

**Level:** Medium. The runner, the allowance and the settings exist and are
tested. A Watch is mostly storage, a scheduler and a screen. What could move:
whether the runner can take the unattended model per run (checked in Chunk 04's
first step), and how restart and interruption interact with "due".

## Governing artifacts, reconciled

| Artifact | Norm | Disposition |
|---|---|---|
| `security-model.md` | § Prompt Injection: "re-derived, not extended" when unattended discovery lands | conforms: Chunk 01 re-derives it before any Watch can run |
| `security-model.md` | Outside text is never parsed as markup | conforms: the screen builds nodes with `el`, and a Watch's words are the household's but are still shown as text |
| `observability-strategy.md` | Panel-only alerting, with scheduled discovery as its revisit trigger | conforms after Chunk 01 records the owner's ruling (browser only) and the positive-line signal the strategy's row already names |
| `nonfunctional-requirements.md` | Spend ceilings are the provider's | conforms: a Watch's cap is budgeting under the allowance, as the allowance is under the ceiling |
| `data-model.md` § `initiated_by` | Not an authorisation input | conforms: the scheduler checks permission because it starts unattended work, and attribution is recorded, not branched on |
| `data-model.md` | Identity is never a source URL | inapplicable because no artwork identity is touched |
| `architecture.md` | Operation logic only in the service layer | conforms: route and MCP tool are bindings over `WatchService` |
| `architecture.md` | Seam rules 1–4 | conforms: Library store, read by the Library alone |
| `architecture.md` | The manifest is the only channel to display | conforms: a Watch reaches a wall only through a verdict, as today |
| `api-contract.md` | Its route rows | conforms: rows added in Chunk 03 |
| `information-architecture.md` | The screen tables bind the client | conforms: Settings › Watches rows land before `app.js` routes it (Chunk 05) |
| `design-direction.md`, `accessibility-spec.md` | Their Direction norms | conforms, checked in Chunk 05 by the browser suite and `docs/ux-walkthrough.md` pass 1 |

**New structural context:** a new execution context (the scheduler thread) and a
new storage surface (the `watches` table, and `watch_id` on runs).
- **Backup:** both are in the catalogue file's discovery store, which `VACUUM INTO`
  already carries.
- **Migration:** additive. An older release ignores the table and the column.
- **Observability:** one INFO line per pass, empty passes included (event
  `scheduler.pass`, with counts due, started and refused). One line per start
  and per refusal, naming the Watch. Each Watch's last outcome is stored on it,
  so the screen reads it. A pass that raises is logged at ERROR and the thread
  carries on, with a specific catch.
- **Errors:** an invalid Watch is refused in the service's words. A refusal to
  run is a state on the Watch, not an error.
- **Auth:** none, per the LAN boundary. Chunk 01 counts what that means for an
  agent that can write a Watch.
- **Shutdown:** the thread stops with the lifespan, as the topic sweep does. A
  run in flight is the runner's, and is marked interrupted by the runner's
  existing startup path.

## The questions the stored Watches must answer

A persisted format is lock-in, so its readers come first:

1. Which Watches are due now, and is each on? (the scheduler, each pass)
2. What did this Watch last do: when, which run, and with what outcome (started,
   refused and why, failed)? (the screen; anyone asking "why did nothing run")
3. When is it next due? (the screen, the overdue flag)
4. What has this Watch spent this UTC month, against its cap? (the scheduler,
   the screen) Read through its runs' spend rows, never stored twice.
5. Which run, and so which review cards, did this Watch produce? (To review's
   "found by" line; `runs.watch_id`)
6. Who created or last changed it, and from which surface? (tracing a surprise:
   Chunk 01's re-derivation relies on this)

## Chunks

### Chunk 01 — the re-derivations Watches owe, before any code

Type: doc-only. Critic mode: final.

- `security-model.md` § Prompt Injection, **re-derived** for review-only
  Watches, not extended. It carries the bounds table as it stands with nobody
  in the session, and states which bounds a Watch run removes (6) and which it
  keeps (4: nothing reaches a wall without a verdict). It notes that a Watch
  run's engine holds no verdict tool, and that the new path is an MCP agent,
  steered by a page, writing a Watch and switching unattended work on. That
  path is bounded by the allowance and the key limit, and made traceable by
  `updated_by`. It records auto-accept as declined, with the condition for
  revisiting it. The "Opened 2026-09-30" item closes.
- `observability-strategy.md`: the owner's ruling (browser only), the three
  conditions its 2026-09-30 note listed, each with where it now shows (the
  third, auto-accept, has nothing to show), and the push revisit trigger as
  what remains.
- `agents-and-memory.md`: open question 2 answered.
- `re-architecture.md` § Open questions: the Watches item closed, pointing here.
  The external-identity item says it is not a prerequisite, marked inferred.
- `data-model.md` § Watch: the fields this plan builds, and the descoped ones
  named. `discovery_runs.watch_id`.
- `information-architecture.md`: Wanted › Missing no longer promises a Watch tab.

**Done when** each record above says what this plan builds, a grep for the
old wording ("auto-accept", "on_match", "Missing (a Watch") finds no survivor
that claims otherwise, and the root suite is green.

### Chunk 02 — a set-aside stored setting says so (#417)

Before the scheduler reads the allowance, so the household can see why it
reads $0.00.

- `SettingsService`: a stored value that fails its check reports
  `source=set_aside` with a `reason`, in `SettingOut` and `art_settings`. It is
  logged once per value, not once per read.
- Settings › General: one sentence under the control saying the household's
  choice was set aside, and why.
- Tests: the lowered-budget case through the real config, the log line counted
  over several reads, and a value that passes showing no reason.

**Done when** the curation and browser suites are green and #417's expected list
is met.

### Chunk 03 — Watches stored, and written from every surface

- New `arrt/src/arrt/library/services/watches.py`: `WatchService`, with list,
  get, create, update (words, cadence, cap, on/off) and delete. It refuses empty
  words, an unknown cadence, a negative cap and a cap above the allowance. It
  is bounded by the allowance when the cap is read, as the allowance is by the
  budget.
- A `watches` table in the discovery store, and a nullable `watch_id` on
  `discovery_runs`, with additive migrations and a test that an older file opens.
- `GET/POST /api/watches`, `POST /api/watches/{id}`, `POST /api/watches/{id}/delete`
  (the surface writes with POST), each a row in `api-contract.md`.
- `art_watches(action='list'|'get'|'create'|'update'|'delete')`, the same
  service. Its fields are the route's (`test_surface_parity.py`).
- Each write logged with the surface that made it, and `updated_by` stored.
- Tests: each refusal by name, through the route and the tool, with a cap
  above a lowered allowance read as the allowance.

**Done when** the three suites are green and a Watch written over MCP reads
back the same from the route.

### Chunk 04 — the scheduler, with Watches as its first job

Critic mode: final. This is the keystone, the first thing that spends with
nobody watching.

- `arrt/src/arrt/http/static/screens/activity.js`: the comment saying a scheduled Get-again
  "waits for Watches" names the upgrades job instead (Chunk 01's review).
- Step 0: read how the runner chooses its model, and whether
  `unattended_model` can be given per run. If it cannot, run the Watch on a
  second engine built from the same factory, and record the choice.
- New `arrt/src/arrt/library/services/scheduler.py`: one thread, a registry of
  jobs (Watches the only one), started and stopped by the lifespan as the topic
  sweep is. Each pass logs one `scheduler.pass` line, empty or not.
- The Watch job, each pass: for every Watch that is on and due, and has no run
  in flight, it asks `standing(phase1 estimate)`, then the Watch's cap against
  its month's spend. If both allow, it starts the run with `initiated_by=unattended`
  and `watch_id`, and the run uses the unattended model. Otherwise it stores
  the refusal and its sentence on the Watch. Due is reckoned from the last
  start, and comes again at the next pass after a failed or interrupted run,
  at most hourly.
- `WatchService` reports, per Watch: last outcome, next due, this month's spend,
  and overdue (on, due more than one cadence ago, and not refused by a setting
  the household chose). *(Built as an hour past due with nothing tried, not one
  cadence: see the decisions above.)*
- Tests, through the real container with a scripted engine: a due Watch starts
  one run attributed `unattended` with its `watch_id`, and its spend counts
  against both the allowance and its cap; each refusal (off, no key, allowance,
  cap) starts nothing and is stored; a Watch in flight is not started twice; a
  restart does not catch up; an empty pass still logs its line; a run of each
  failure kind is retried at the next pass, not in a loop; and a Watch's
  unreviewed find is absent from the next run's phase 1 request, while the same
  find, once rejected, is present (`agents-and-memory.md` open question 2). Each guard is
  watched failing once.

**Done when** the three suites are green, and on a scratch `ART_ROOT` with a
scripted engine a Watch runs on schedule and its finds appear in To review.

### Chunk 05 — Settings › Watches, and what the status indicator says

Type: cumulative-final.

- `information-architecture.md`: Settings › Watches rows in the screen tables
  and the Settings index, before the client routes it. Its states follow
  § Screen States.
- The screen: each Watch's words, cadence, cap, on/off, last outcome in its
  sentence, next due, and this month's spend. Create, edit, delete. The
  allowance's standing sits at the top, linking to Settings › General.
- To review: a card from a Watch says "Found by your Watch *…*".
- The status indicator: Watch spend, plus a flag when a Watch is overdue or the
  allowance is spent (`information-architecture.md`: "Watch spend belongs on the
  status indicator").
- Browser tests (`-m browser`, after `uv sync --group browser`): create a Watch,
  see it refused while unattended work is off, switch work on, see it run (scripted
  engine), and see its card in To review with the found-by line.

**Done when** the three suites and the browser suite are green,
`arrt/tools/ux_walk.py` reports nothing new on the screen, and the cumulative
review is clean.

## Verification strategy

Run the server against a scratch `ART_ROOT` with a scripted engine, so no model
is called. Then, in the browser: write a Watch with unattended work off and see it
refused, with the reason. Turn work on with a small allowance, wait a pass and see
the run start, its finds in To review and its spend on the screen. Seed spend past
the cap and see the next pass refuse. Stop the server mid-run, start it again, and
see the Watch due once, not once for every slot it missed. One live run, on the
owner's say-so and with a cents-sized allowance, is the last check before release.

## Governance checkpoints

- After Chunk 04: the whole trajectory, because it is the first code that spends
  with nobody watching.
- Chunk 05's cumulative, before the PR.
