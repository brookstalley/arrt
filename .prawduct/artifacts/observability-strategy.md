---
artifact: observability-strategy
version: 1
depends_on:
  - artifact: product-brief
  - artifact: architecture
  - artifact: nonfunctional-requirements
last_validated: null
---

# Observability Strategy

**The defining constraint: failure is silent by construction.** The only feedback
channel the household has is a picture on a wall, and a stalled loader is
indistinguishable from a working one showing a static image. Everything below
exists to make "down" distinguishable from "up", because nothing about the
product's own behaviour does that.

Scaled to a medium-risk single-household product: **structured logs, one health
surface, and no backends.** No metrics store, no tracing collector, no dashboards.
Naming what is deliberately absent matters as much as what is present — a future
reader should not conclude these were forgotten.

> **Direction changed 2026-09-30. See `re-architecture.md`.** The defining
> constraint is unchanged, and so is the single panel in the curation UI. What
> moves:
> - **The heartbeat becomes an HTTP POST** from each Player to the server (waves
>   2–3). It stops being a file in a shared directory.
> - **Logs live on two machines.** The server's are in the NAS container's log,
>   and each Player's are in its Pi's journal.
> - **The server gains scheduled work** (Watches and upgrade re-searches, wave
>   6). Its failures happen with no curator in the session, which fires the
>   push-notification revisit trigger recorded under § Accepted detection
>   latency.
>
> The dated notes below mark each place. As-built content is unchanged, because
> it describes the running Pi.

## Signals

| Signal | Present? | Where |
|---|---|---|
| Structured logs | **Yes** — the primary signal | Both planes, to the systemd journal |
| Health/heartbeat state | **Yes** | Display writes it; the curation UI reads and displays it |
| Spend | **Per run, yes; the month's remaining budget, yes, in the sidebar** *(since 2026-10-07; it was "never" until the owner reversed it, see the note below the table)* | Recorded spend is on the run and reported by the discovery surface. What is left this month is `GET /api/budget`, read from `limit_remaining` (`library/services/spending.py`), display only and never on the health panel |
| Ask's replies | **Yes, per reply, since 2026-10-08** | One INFO line on `arrt.ask` per reply: thread, how it ended (`answered`, `step_limit`, `budget_spent`, `failed`, `cancelled`), model calls, tool calls, cost (OpenRouter's own `response_metadata["cost"]`, summed) with the number of calls that carried none, and seconds. A failed reply also logs its traceback. The cost is shown to the curator under the reply. **No `SpendRecord` is written for it**: the month's figure in the sidebar is the provider's own, so it already includes Ask. A per-reply record is the 3tears spending cap's question (pacepace/3tears#583) |
| Metrics (time series) | No | No store, no query surface, nobody to read them. Revisit only if a real question needs a trend |
| Distributed tracing | No | Two processes with no request/response between them. There is no distributed call to trace. *(2026-09-30: after wave 2 there is one: the Player's manifest poll and media pull, and its heartbeat POST. Each is a single hop with no fan-out, so `work_id` and the wall id remain enough correlation, and this row still holds. See `re-architecture.md`.)* |
| Uptime monitoring (external) | No | Follows from the operator's alerting decision below |

> **On `limit_remaining`, and why this row shrank (2026-08-02).** The Spend row
> read "**Yes** — read from the authority | `GET /api/v1/key` → `limit_remaining`".
> No surface exposes that figure: the client can read it, and nothing in the
> services, HTTP or MCP layers calls the reader. More importantly it should not be
> the budget indicator on its own even once something does — it lags by minutes,
> and was observed reporting credit remaining while live calls were already being
> refused. A panel built naively from it would tell the operator they had money at
> the exact moment spending stopped working. The signals that do not have that
> failure mode are recorded per-run spend and the `halted_by_budget` outcome.
> (`operational-spec.md` § Troubleshooting corrected the same claim the same day;
> this artifact was the copy that sweep did not reach.)
>
> *(**Reversed by the owner 2026-10-07** (`ia-proposal.md` § Rulings (2026-10-07), ruling 3): the month's remaining budget is shown. How, and what was weighed, is the note in `nonfunctional-requirements.md` § Direction, under its *read from the authority* corollary; #290 builds it; the server half, `GET /api/budget`, was built 2026-10-07.)*
>
> **Settled 2026-08-04 by the operator: it is not surfaced, in any form.** The
> question left open here was whether to show it anyway as a lagging advisory
> figure with its age on screen. That option was the serious one — it appears to
> satisfy this artifact's own panel rule, *state the observation and its age, not a
> verdict* — and it was declined because **the figure's failure mode is inversion,
> not staleness.** A caveat about age warns that the number may be old; what was
> measured is a number that was *wrong in the reassuring direction*, reading credit
> remaining while live calls were already refused. Age-stamping does not caution
> against that, so the panel would carry a figure whose one dangerous reading is
> the one the caveat does not cover. A lagging balance is a green dot wearing a
> timestamp, and § The panel shows staleness in absolute terms forbids green dots.
>
> **This settles display, not provenance.** The ratified corollary in
> `nonfunctional-requirements.md` § Direction — "budget remaining" is read from the
> authority, never from a local tally — is untouched and was never in question; it
> governs where the number comes from *if* shown, and the answer here is that no
> surface shows it. Nothing in this resolution amends that norm.

**Both planes use stdlib `logging`, and neither takes a dependency for it.**

> **Corrected 2026-07-27.** This section previously said "`3tears-observe` is
> available on the curation plane and carries structured logging plus
> OpenTelemetry at no infrastructure cost — take the structured logging". The
> 2026-07-27 technology amendment withdrew every 3tears dependency, and nothing
> replaced this claim: `arrt/pyproject.toml` does not declare the package, its
> explicit "deliberately not pinned yet" list does not mention it, and the plane
> ships stdlib logging. So the artifact naming structured logs as the primary
> signal rested on a package no manifest carries. The withdrawal was swept through
> the dependency lists and not through here, which is the repo's own recorded
> obligation — retiring a claim is a repo-wide grep, not a local edit.

**Curation's shape is one JSON object per line, and the run id is bound rather
than passed** (built 2026-08-02, `arrt/src/arrt/logs.py`). This discharges
the debt this section recorded: the plane previously emitted
`"%(asctime)s %(levelname)s %(name)s %(message)s"`, which was enough for startup,
refusals and reconciliation and not enough for the per-run correlation below.

Two decisions worth not re-deriving:

- **JSON, not logfmt.** Both are structured; the deciding case is free text. An
  intent is the curator's own words and goes in a log line, and quoting it into a
  key=value stream is a rule every call site has to get right. A traceback is
  carried as one field for the same reason — multi-line output would break the
  one-line-one-object property the whole shape rests on.
- **`run_id` rides a context variable and is stamped by a filter**, so a module
  that logs inside a run carries the key without knowing runs exist. Threading
  the id through every call site that might log is a discipline, and one
  forgotten site defeats it — the lines lost that way are the ones emitted from
  deep inside a failure, which are the ones worth having.

The OTel question does not reopen: an exporter with no collector is machinery
pretending to be observability.

> **A finding worth keeping, from building it.** The first implementation cleared
> every root handler to make `configure()` idempotent. That silently disabled the
> test harness's own capture, and it failed as *"nothing was logged"* rather than
> as *"your logging setup removed my handler"* — a library evicting handlers it
> did not install is this product's characteristic failure shape in miniature. It
> now removes only its own, and both halves are pinned by test.

## Two Defects to Fix, Not Inherit

These are named specifically because they exist in the 2024 code and are the exact
shape of failure this strategy exists to prevent.

**`upload_file` catches every exception, logs it, and returns success anyway** —
recording a null content id while the retry loop sets `success = True`. This is
worse than no logging: it produces a log line *and* a false success, so the system
actively asserts a thing that did not happen. The rule it violates is already a
recorded norm (never report success on a failed operation), and it is why the
"catch specific exceptions" preference has an advisory audit home rather than a
janitor one.

**`print()` is used for operational output throughout** (`ai.py`, `display.py`,
others), producing journal lines with no level and no timestamp. Under systemd
that means failures are present in the journal but unfilterable and unsortable —
technically logged, practically invisible. *(Restated 2026-08-01: this said
"Critic-enforced preference; converted on touch", and both halves changed on
2026-07-27. It is now a **linter** rule — ruff `T20` in both `pyproject.toml`s —
and its disposition for the eight legacy modules is a **dated waiver, not
convert-on-touch**: they die with the 2024 modules at the legacy retirement,
because convert-on-touch had no mechanism behind it and all eight were touched without a
single call being converted. Do not convert them against that waiver, and do not
report their survival as a defect. The authority is `project-preferences.md`'s
`T20` row.)*

## Correlation

Deliberately minimal, because the topology does not need more.

- **`run_id`** — a discovery run's correlation key, on every log line emitted
  during that run on the curation plane. This is the one place where a single user
  action fans out across minutes and many external calls, so it is the one place a
  correlation key earns its keep. **This covers re-searches too**, since
  `resolve_images` creates a `DiscoveryRun` with `kind='resolve'` (2026-07-20) —
  before that decision the product's second paid, minutes-long fan-out emitted log
  lines with no correlation key at all. Where a resolve run's lineage matters, it is
  `parent_run_id`, not a second field on the log line.
- **`look_qid`** — a look's correlation key *(added 2026-10-06,
  `build-plan-look-before-get.md`)*: the Wikidata item a look is asking the image
  sources about, bound by `logs.look_context` as `run_id` is bound, on every line
  logged from the look's own threads, its picture route and the model's picture
  fetches, the picture store's `picture.*` lines included (`test_look.py` holds
  both). A look is not a run
  (it writes nothing and has no id), so it gets its own key rather than borrowing
  `run_id`; `jq 'select(.look_qid == "Q…")'` returns one work's look.
- **`work_id`** — the only identifier that spans both planes. It appears in
  curation logs, in the theme manifest, and in display logs. That is sufficient to
  answer "why is this artwork behaving oddly" across the process boundary.
  **Bound, never passed — which is why it has to be bound where the paths meet.**
  Display's label events inherited the id for free on the rotation path, because
  the selection binds one around everything it does; the path that captions a work
  somebody chose with the remote bound nothing, so the journal could report a
  panel failing and not say which work it failed to name. Corrected 2026-08-13 by
  binding inside the caption itself rather than at its two callers: one forgotten
  call site defeats a discipline, and the lines lost that way are the ones logged
  from inside a failure.
- *(Direction changed 2026-10-08, build plan displays-and-label-outputs Chunk 06:
  the label is drawn by a label renderer from a label document, not by the Frame
  loop, so no label event carries `tv_content_id` any more. Every one carries
  `label_id`, a caption binds the document's `work_id`, and `label.blanked` and
  the new `label.card` carry the `display_state` that asked for them. The
  renderer's own events are `label.renderer_started`, `label.server_unreachable`
  / `label.server_reachable`, `label.refused` / `label.accepted` and
  `label.document_refused` / `label.document_readable`, each once per episode;
  the client's are `client.label_started`, `client.label_stopped`,
  `client.label_unplaceable`, `client.label_crashed` / `client.label_ended`, and
  `client.identity_unreadable` / `client.identity_read` for the Frame's device
  id. The paragraph below is the history of the Frame loop's events.)*
- **`tv_content_id` on a label event is not a duplicate of `work_id`**, though it
  looks like one on the path where both appear. The set's own id is the *only*
  identity available when the wall shows a picture the manifest cannot name —
  there is no work, so there is nothing else to tie the line to — and it is what
  joins a caption to the `rotation.selected` that preceded it. It is carried on
  `label.drawn`, `label.blanked`, `label.failed` and — since 2026-08-13 —
  `label.unusable`, for that reason, and deliberately **not** on the rest: a
  second id there would be a field defended only by the test written to defend it.
  They are not silent for the same reason, and whoever adds the next label event
  needs the difference. `label.truncated`, `label.shrunk` and `label.name_wrapped`
  are all unreachable without a work — a blank label has no lines to drop, no type
  to reduce and no name to break — so `work_id` is always bound under them.
  `label.absent` names the work directly, because the whole point of it is which
  record had nothing to print. `label.unusable` carries the content id
  because it is a statement about the *device*: the surface has no usable area at
  all, which is true of whatever the wall happens to be showing. **`label.recovered`
  carries neither id on the blank path** — it is emitted before the caption knows
  whether it has a work, so a panel recovering on a blank caption logs a bare
  recovery line. That is left alone deliberately: it is a statement about the
  surface rather than about a work, and the very next line it emits is the
  `label.drawn` or `label.blanked` that names what the recovery was drawing.
- **`run_id` deliberately does not cross into display.** The manifest is a
  statement of *current state*, not a record of the run that produced it. Carrying
  a run id into it would imply a provenance relationship the manifest does not
  have.

There is no request-id propagation between planes because there are no requests
between planes.

> **Phase 2's events, added 2026-08-02, and what they exist to make visible.**
> Phase 2 is where a run can fail *quietly* in the one direction this product
> cannot otherwise detect — by finding nothing and looking like it worked, or by
> finding the wrong painting and looking like it found the right one. So the
> discards are logged as loudly as the successes:
>
> | Event | Says |
> |---|---|
> | `phase_two.searched` | which collection was asked about which work, how many results came back, and how many were usable at all |
> | `phase_two.judged` | how many instances were credible, how many of those are below the quality minimum (`instances_below_floor`, named when the minimum was an inch floor), and `refused_at` — the gates that turned the rest away, which is the per-work summary of the `not_the_work` and `size_unknown` lines below |
> | `phase_two.not_the_work` | a result was discarded as a different painting, naming what the provider called it and who it says painted it, its `found_url`, the work's `qid`, and `link`: why no Wikidata link settled a differing title (`no_registry`, `no_qid`, `registry_unavailable`, `not_recorded`), or how the title was settled before the artist refused it (`title_matched`, `linked`); and, on an artist refusal, `names`: why Wikidata's names for the creator did not settle it (the page link's own word when the page is not the item's, `names_unavailable`, or `not_a_creators_name`) |
> | `phase_two.renamed` | a result whose artist is named differently was kept, on a page the work's item records, because Wikidata records both names for one of the item's creators; naming both artists, the page and the item |
> | `phase_two.linked` | a result whose title differs was kept because the work's Wikidata item records its page, naming both titles, the page and the item |
> | `phase_two.link_unavailable` | Wikidata could not be asked which pages describe a work, so no page of it was taken as the work: a differing title, or a differently named artist, was refused; at WARNING, once per work |
> | `phase_two.names_unavailable` | Wikidata could not be asked the names of a work's creators, so a differently named artist was refused; at WARNING, once per work |
> | `phase_two.size_unknown` | a result was discarded because the provider reported no dimensions |
> | `phase_two.unreachable` | a provider could not be asked about a work, which leaves it pending rather than unresolved |
> | `phase_two.unanswerable` | no wired image source can look a work like this one up (Commons alone, for a work named by title); the work stays pending. Kept apart from `phase_two.unreachable`, which says a source was down |
> | `image_pool.unreachable` | one image source of several could not be asked about a work, naming the source; the others' answers stand, and the work waits unless one of them found an instance that clears the floor |
> | `commons.not_raster` | the image a Wikidata item names on Commons is not a picture the acquisition path can decode (SVG, PDF, video), naming its type; the work is answered as having none there |
> | `get.asked` | a Get was asked for, with the run it started (`started_run_id`), the theme its accepted works join (`destination_theme_id`, null for the default), how many works it chose and how many it skipped for each reason |
> | `phase_two.verdict_stands` | a resolution finished against a work the curator had already decided; the result is reported, not applied |
> | `phase_two.preview_too_large` | a provider's preview body passed the size ceiling and the read was abandoned, naming the URL and the ceiling. Distinct from `preview_failed`, which is a preview that could not be fetched at all — this one *was* being served, and the far end was sending more than a thumbnail. Both leave the card falling back to the source URL, so the log line is the only place the difference is visible |
> | `picture.kept` / `picture.absent` | whether a review card will have a kept picture to show: `picture.kept` names the store path and the bytes of each tier written; `picture.absent`, at INFO, names a source's reason none was kept (it returned nothing or raised, or the bytes are not a picture). A failure of this machine's own disk is not a miss and is never logged as one: see `picture.unreadable` and `picture.unwritable` below. Replaced `preview.cached` / `preview.absent` on 2026-10-06 |
> | `run.completed` | the run's works split into resolved, unresolved and unreachable |
> | `look.started` | a look queued an ask at one or more image sources (`providers`) for a work (`work_title`); not logged when every source's answer is still kept, so a quiet reload is visible as the absence of this line |
> | `look.source_answered` | one source answered a look: its `state` (`found`, `holds_none`, `refused`, `cannot`), how many finds it holds (`found`), `refused_at`, and `registry_unavailable`: true when Wikidata could not be asked which pages describe the work, or its creators' names, so the judge decided without them and a "none" is kept ten minutes rather than six hours. Phase 2's own `phase_two.not_the_work` lines appear beside it, since the look judges with phase 2's judge |
> | `look.source_unreachable` | at WARNING: a source could not be asked for a look, with its `reason`; kept for ten minutes and asked again after, never recorded as holding nothing. Also, with a traceback, when a finder or the judge raised something unexpected, and when the thread asking a source stopped or could not be started, whose waiting asks are all answered this way |
> | `look.abandoned` | a queued ask was dropped before it started: nobody had polled the work for 20 seconds (`unwatched`), or the look was no longer kept (`forgotten`) |
> | `look.picture_served` | a look's picture was served from the picture store, by `key` and `size`; the store's own `picture.kept` / `picture.absent` say whether it had to be fetched |
>
> **The supplement's events, which are a separate subsystem.** A run may offer
> works from a wired collection when phase 2 cannot confirm what phase 1 named,
> and that path fails differently from a search: it is a *supplement*, so its
> failures are swallowed rather than surfaced to the run — which means the
> journal is the only place they appear at all.
>
> | Event | Says |
> |---|---|
> | `browse.searched` | how many artists the collection was asked about in one request, how many it holds anything for, and how many works came back |
> | `browse.offered` | how many works the run actually offered, against how many the collection holds for those artists — the ratio a bound is judged by |
> | `browse.unreachable` | the collection could not be browsed. **A supplement failing must not fail the run**, so this is the only signal that one was attempted and lost |
> | `browse.surname_retried` | an artist was recovered under a different spelling, naming the surname and the artist the collection filed it under. **The one line to read when a wrong-hand offer reaches a curator**: this is the only path that returns work under a name nobody asked for, and it is licensed by a measurement the museum could change under us |
> | `browse.surname_ambiguous` | a retry was refused because the surname reaches several artists — the guard working, and the counterpart to the line above |
> | `browse.below_floor` | a work was not offered because it is below the quality minimum (the event keeps its name from when that was an inch floor, so a journal query written then still finds it). **Systemic rather than per-work**: one wrong `QUALITY_MINIMUM_PX` makes every browse result fall below it, and without this line the supplement offers nothing for ever while reporting only `works_offered: 0` |
> | `work.suppressed` / `work.already_present` | an offer was declined because the curator rejected that work earlier, or because the run already carries it |
>
> **Acquisition's events, which start here.** `acquisition.source_read` (named
> `acquisition.tile_target_resolved` until 2026-10-03, when readers became
> plugins) is the product's first, and it exists because the fetch that follows it is
> against an address no record holds — without the line, a failed tile fetch
> cannot be told apart from a museum that went away, and the recorded failure
> names only the URL the source carries, which was never the one fetched.
>
> | Event | Says |
> |---|---|
> | `acquisition.source_read` | a plugin's reader turned a source's URL into what to fetch, naming the plugin, the recorded URL, the URL actually fetched, and whether it was tiles or a direct image |
> | `acquisition.unclaimed` | a source was fetched as recorded because no installed plugin claims its URL. Ordinary for a 2024 seed row or a Commons image URL; the line that traces a source whose plugin was uninstalled, since nothing else can tell that case apart |
> | `acquisition.deployment_fault` | acquisition refused before it started for a reason no source is at fault for — a full disk, a missing binary, a source whose plugin is installed and not loaded (`SourcePluginUnavailable`). **At ERROR, and for these three conditions it is the only journal signal there is**: unlike a failed fetch, which is recorded against the source and readable afterwards, these reach the caller as a refusal the tool boundary answers without logging — and the person who can fix them is not the one holding the tool result. **Emitted by `AcquisitionService` at the raise, so the signal follows the condition and not the route in** — every caller gets it, and a surface added later inherits it rather than inheriting silence. The operator-facing *remedy* is held once beside the conditions, in `DEPLOYMENT_REMEDIES` (`library/acquisition/service.py`): the acquisition queue pauses on these conditions (`acquisition.queue_paused`, naming the condition), and the Work page, Activity › Queue and MCP's `get` all show the pause with that remedy (since 2026-10-02, `build-plan-after-review.md` Chunk 02; until then `retry_acquisition`'s three `except` clauses wrote it). (Until 2026-08-05 the line was emitted by that binding instead, so it existed only where acquisition was driven over MCP. Harmless while MCP was the only caller and a trap the moment it was not.) |
>
> **`phase_two.not_the_work` is the one to read first when a run comes back
> emptier than expected.** It carries the museum's own title and artist beside the
> requested ones, so the failure modes it sits between are distinguishable from
> the journal alone: a work the collection genuinely does not hold, and a work it
> holds under a name the identity comparison did not match. The second is a defect
> in the comparison; the first is the product working.
>
> **There is a third, and this split could not express it — which is how it went
> unseen (2026-08-04).** A record the query *never retrieved* emits no event at
> all, because nothing reached the comparison to be discarded. The measured case:
> the artist was folded into the free-text museum query, its tokens competed with
> the title's for the ten places a result has, and works the collection
> demonstrably holds fell outside the window. Every one of them looked, from the
> journal, exactly like a work the collection does not hold — the product
> working. A two-way split over *what was discarded* is blind by construction to
> what was never fetched, so the journal alone cannot close this, and the count
> already on `phase_two.searched` is what distinguishes a thin result from an
> absent one. **When a run comes back emptier than expected and
> `not_the_work` explains all of it, the next question is what the query asked
> for**, not what came back.

> **The picture store's events, added 2026-10-06** (`library/services/pictures.py`,
> `build-plan-picture-store.md`). They replace the preview sweep's, which retired
> with the norm that every picture fetched from outside is kept
> (`data-model.md` § Direction): nothing deletes a kept picture, so there is no
> periodic job whose silence is the fault.
>
> | Event | Level | Says |
> |---|---|---|
> | `pictures.cleaned` | INFO | the store's stray temporary files were removed at startup, with how many. Logged at every start, zero included |
> | `pictures.imported` | INFO | the startup import of the old `previews/` directory ran, with rows `imported`, `missing`, `refused` and `failed`, files no row names (`unnamed`), and `done`. Logged at every start while `previews/` exists; `done` is when it may be removed by hand, after which a start logs `pictures.import_retired` instead |
> | `pictures.import_failed` | WARNING | one row's old preview could not be read, or its picture or row could not be written. Counted in `failed`, so `done` is false until a later start succeeds |
> | `picture.unreadable` | WARNING | the store could not be read: when keeping a picture (so nothing is fetched over it), or when a card or the model's copy asked for a kept file that will not read or decode. Every kept file is one the store wrote and checked, so this is the disk, never a museum |
> | `picture.unwritable` | WARNING | a picture arrived and could not be written: a full or read-only disk. The instance is recorded without a picture, and the run goes on |
> | `pictures.import_retired` | INFO | the old `previews/` directory is gone, so the startup import walked nothing. The state after the operator removes it |
>
> The store's size is not a log line: its files and bytes are on the health panel
> and `art_display(action='status')`, from a walk at most ten minutes old, because
> a store with no ceiling is watched as a figure rather than as an event. **The
> walk counts what it could not read** (`unreadable`), and the panel's sentence
> then says the store could not be read in full rather than "no pictures yet": an
> unreadable store must never read as an empty one.

> **The topic sweep's events, added 2026-10-02** (`library/services/topic_sweep.py`,
> `build-plan-topics-and-destinations.md` Chunk 04). The sweep keeps the
> library's works' topics as facet rows from Wikidata: at start, when a work is
> accepted or a QID changes, and daily. Its failure mode is any periodic job's:
> Library › Topics and the Artworks rail quietly stop changing.
>
> | Event | Level | Says |
> |---|---|---|
> | `topics.off` | INFO | logged **once, at start**, when `WIKIDATA_USER_AGENT` is unset: no sweep is started and topics stay as they are. Nothing else about the sweep is logged in that state |
> | `topics.sweep_started` | DEBUG | a pass began; against `topics.swept`, a start with no finish is a pass waiting on Wikidata or wedged |
> | `topics.swept` | INFO | a pass finished, with how many works were due, how many of those were asked about (the rest have no QID and no artist QID), and how many rows were withdrawn and are now written. Logged on every pass, including one with nothing due |
> | `topics.sweep_unavailable` | WARNING | Wikidata could not be asked; nothing was replaced, and the due works are asked again next pass. Not followed by `topics.swept` |
> | `topics.sweep_error` | ERROR | a whole pass raised, with its traceback; the loop continues |
> | `topics.sweep_wedged` | WARNING | shutdown asked the sweep to stop and it did not within five seconds |
>
> At a daily interval `topics.swept` is one line a day plus one per acceptance or
> QID change, so its absence over a day is the signal that the sweep died.

> **The acquisition queue** (`library/acquisition/queue.py`, since 2026-10-02,
> `build-plan-after-review.md` Chunks 01-02) fetches and then prepares each
> accepted work holding no image, one at a time: woken by acceptance, a pass at
> start, and otherwise when the next retry falls due or a day passes. Its failure
> mode is the sweeps': accepted works quietly stay off every wall.
>
> | Event | Level | Says |
> |---|---|---|
> | `acquisition.queue_pass` | INFO | a pass finished: how many works were due, acquired, failed, given up on and waiting, and the pause it ended in if any. Logged on every pass, including one with nothing due |
> | `acquisition.queue_failed` | INFO | one work's attempt failed; it names the try and when the next is due |
> | `acquisition.queue_gave_up` | WARNING | a work failed its last try and waits for Retry |
> | `acquisition.queue_paused` | WARNING | a deployment fault (`DEPLOYMENT_FAULTS`) paused every fetch, naming the condition; Activity › Queue and the Work page show it with its remedy |
> | `acquisition.queue_unexpected` | ERROR | an error nothing anticipated, from one work's attempt, with its traceback; it counts as that work's failure |
> | `acquisition.queue_error` | ERROR | a whole pass, or the wait for the next work, raised, with its traceback; the queue pauses and the loop continues |
> | `acquisition.queue_retry` | INFO | a curator or an agent asked for a work again |
> | `acquisition.queue_wedged` | WARNING | shutdown asked the worker to stop and a fetch was still running after five seconds |
>
> `acquisition.queue_pass` is at least one line a day and one per acceptance, so
> its absence over a day, or after an acceptance, is the signal that the worker
> died.

> **The kept answers file's events, added 2026-10-02** (`persistence/kept.py`).
> The file is disposable and every way it fails is a miss, so a page never
> shows the fault: it only asks its foreign source again, and is slow. The
> journal is the one place the difference between "kept" and "asked every time"
> is visible, so each quiet state has a line of its own.
>
> | Event | Level | Says |
> |---|---|---|
> | `kept.opened` | INFO | the file was opened at startup, with its path, how many answers it holds, and how many it threw away as expired |
> | `kept.replaced` | WARNING | the file was not a database, was damaged, or was of another format, and was replaced by an empty one, with the reason. Every page asks again once. Once after an upgrade that changes the format is expected; at every start it is a disk that is failing |
> | `kept.unreadable` | INFO | one answer could not be read back by its namespace's codec, naming the namespace and the error's type, and was dropped. A run of these after an upgrade is a changed answer shape costing one question each; one namespace logging them at every visit is a codec that cannot read what it writes |
> | `kept.unwritable` | WARNING | a namespace's codec could not write an answer, so it is not kept. A bug in the caller's declared type, never a condition of the machine: the page has its answer, and every visit asks again |
> | `kept.failed` | WARNING | a read or write of the file raised (a full disk, a read-only mount), naming the namespace and the operation. The answer is asked fresh or not kept |
>
> Hits and misses are not logged: a page section asks at human pace, and a
> line per view would bury the four above.

## What the museum is told about us

The Art Institute's API is open — no key, no account — but asks callers to
identify themselves. `ARTIC_USER_AGENT` carries a deployment name and a contact
address, and **there is deliberately no default**: sending a made-up identifier
would misrepresent whoever runs this to a third party. Unset leaves the Art
Institute out of phase 2's image sources rather than asking it anonymously, and
Commons is in them only when `WIKIDATA_USER_AGENT` is set, for the same reason.
That is why the startup line `phase2 image_sources=` names the sources configured
— a run stuck at `resolving_images` should be one journal read from its
explanation.

No rate-limit headers exist on that API to read back (measured, not assumed), so
there is no budget signal to log and none is invented.

## The Health Surface

> **Direction changed 2026-09-30. See `re-architecture.md` § Seam 2.** The
> heartbeat's *transport* changes and its *contract* does not. In wave 2 each
> Player sends the same document as `POST /walls/{wall_id}/heartbeat`, and the
> file channel retires in wave 3. The one named key, `reported_at`, stays the
> contract for the same reason it is one today. The wall id moves from the
> filename into the path. Both copies of the name are still checked against each
> other, because the Player and server must agree on the route exactly as they
> agree on the filename today. Wave 1's contract pins the key: both planes are
> tested against `contract/schemas/heartbeat.v1.schema.json`. The route's
> spelling is pinned when wave 2 builds it, by a `contract/routes.json` that the
> server's route tests and the Player's client tests both assert against. After
> the repo split, `contract/` is the only thing both repos share.
>
> What changes with the transport:
> - **The 60-second interval stops being a wear budget.** It remains bounded by
>   the rotation interval, and it no longer writes the card.
> - **A POST can fail in a way a file write cannot.** The server may be
>   unreachable while the wall is fine, because the Player renders from its
>   cache. A Player that cannot deliver its heartbeat must not stop, retry
>   unboundedly or treat it as a wall failure. It logs, and the panel shows the
>   last heartbeat's age, as today.
> - **The Player may add its screen geometry** as an observation, so the panel
>   can say a work is below the floor *on that wall*. The Library never reads it.
> - **The Player's cache state becomes worth reporting**: how many of the
>   playlist's media it holds, and whether any are missing. That is the new way
>   "down looks like up": a newly hung playlist whose media never arrived.

**Display writes a heartbeat; curation reads and displays it.**

The display plane writes a small status document to the shared directory on a
regular interval, using the same atomic write-and-rename discipline as the
manifest. It carries: the moment it was written, the manifest version currently
loaded, the work currently displayed, TV connectivity state, e-paper state, and
the last error if any.

**Two names in it are a contract, not a suggestion, because the reader is already
built** (`arrt/src/arrt/programming/manifest/heartbeat.py`): the file is named by the
template **`display-heartbeat-{wall_id}.json`** under `ART_ROOT`, and the timestamp
key is **`reported_at`**, an ISO-8601 instant.
The reader treats any other spelling as an unreadable heartbeat and says so — so a
writer that calls the field `timestamp` produces a plane that looks *down* to
curation while running perfectly. That is this product's defining failure mode
manufactured by the mechanism built to detect it, which is why the key is named
here rather than left to the writer. Everything else in the document is the
writer's to shape: the reader hands the whole object through untouched.

**One heartbeat per wall, since 2026-08-12**, matching the manifest
(`architecture.md` § One manifest per wall). The wall id is the one the curation
catalogue minted. Until 2026-10-02 the display plane took it from `WALL_ID` in its
environment, exactly as it takes `TV_ADDRESS`. The client Player
(`clients.md`) learns its walls from the server's client document and refuses
`WALL_ID`, and one process now writes one heartbeat per wall it shows. The reason is this section's own
requirement read across two rooms: `information-architecture.md` asks health to
name *which* wall is silent, and one shared file cannot — a second display would
overwrite the first's report every minute, so a wall that had gone dark would
read identically to a wall that was fine. The filename is a template rather than
a constant on both sides, and the two copies are held equal by
`tests/preferences/test_heartbeat_contract.py`, whose value is that **both sides
moving together is still a break**: a rename that updated both planes would
orphan every heartbeat already on disk and every line of this document.

**The interval is 60 seconds, and it is a wear budget as much as a freshness one.**
This file is rewritten forever, on the same medium as the catalogue, and the
storage decision in `operational-spec.md` § Risks rests on this product having no
unbounded small-write source: a writer that borrowed the manifest poll's ~1 s
cadence by symmetry would commit roughly 86,400 write-and-rename cycles a day to
that medium in perpetuity. The ceiling on the other side is the rotation interval —
the document names the work *currently* displayed, so a heartbeat slower than the
wall's rotation would report works the wall had already left, and would skip others
entirely. Sixty seconds sits comfortably under the 180 s rotation default with
margin for a faster theme. A theme rotating faster than the heartbeat will have
works the panel never names; that is a reporting limitation of a coarse cadence,
not a fault, and it costs nothing because no display behaviour reads this file.

Freshness costs nothing here either, because the panel states staleness in absolute
terms rather than judging it: "last heartbeat: 4 days ago" reads the same whether
the interval is one second or sixty, and nothing downstream compares the age to a
threshold.

> `[DECISION: the display heartbeat is written every 60 seconds | the cadence was
> unspecified while being the product's only unbounded small-write source on the
> medium named as the top operational risk, and the reader judges heartbeat age
> absolutely rather than against a threshold, so a coarse interval costs no
> fidelity; bounded above by the rotation interval, since the document names the
> work currently displayed | user can veto/override]`

> `[DECISION: display writes a heartbeat file rather than curation reading
> display-state.sqlite directly | a file keeps the planes' schemas decoupled and
> reuses a discipline already proven for the manifest, where a cross-process read
> of another plane's database would couple curation to display's internal schema |
> user can veto/override]`

This does not violate the manifest-only norm, which governs the curation → display
direction. The heartbeat runs display → curation, and it creates no availability
dependency for the display plane: display writes it and never checks whether
anyone read it.

**Everything else in the document reaches the panel unread**, as of 2026-08-05.
`GET /api/health` carries the heartbeat's whole object through as `reported`, and
the panel renders whatever keys it finds. That is what gives the TV, panel and
last-error rows of the failure table below a reader — they had none until then,
which made them a monitoring plan whose evidence existed only in a file no
surface opened.

**As of 2026-08-12 it carries one such reading per wall**, under `walls[]`, each
with the wall's id and name beside it, plus one `description` across them all —
which names the wall that has not reported rather than reporting that *a* wall
has not. The sentence applies no threshold and uses no word like "healthy": a
wall has written a heartbeat or it has not, and if it has, the age is stated in
the unit a person reads it in. Deciding whether four minutes is late stays the
reader's, because this plane does not know whether that television was switched
off on purpose.

Passed through rather than unpacked into named fields, and that is the same
decision as naming `reported_at` here: exactly one key is contract, so inventing
more on the reading side would be a second contract the writer never agreed to,
and a writer that spelled one of them differently would drop off the panel in
silence — the failure the one named key exists to prevent, reintroduced for every
other field.

### A client, and a wall on its screen (2026-10-02, `clients.md`)

**Two levels of report, kept apart.** The **client heartbeat** (`POST
/client/heartbeat`) says which outputs a client has, whether each is connected,
and at what size. Settings › Clients shows it with its age. **Each wall's
heartbeat** stays what it was: the work on the screen and the last error. A
screen that is unplugged shows up in the first as `connected: false`, while the
wall's own heartbeat keeps beating, because its worker keeps rotating.

The Player's journal events for a client and an HDMI wall:

| Event | Level | Means |
|---|---|---|
| `client.started` | INFO | The process is up, naming its server and cache, and whether it has a Frame |
| `client.wall_started` / `client.wall_stopped` | INFO | The server assigned or took away a wall on an output |
| `client.unreachable` / `client.reachable` | WARNING / INFO | The server cannot be reached; the walls run on from the cache |
| `client.refused` | ERROR | The server refuses this client's token (`CLIENT_TOKEN`) |
| `screen.absent` / `screen.returned` | WARNING / INFO | No screen on the wall's connector, then one again (drawn at once) |
| `screen.draw_failed` / `screen.draw_recovered` | WARNING / INFO | The output refused a picture, said once per episode. The commonest cause is a service user outside group `video` |
| `screen.refresh_failed` / `screen.refresh_recovered` | WARNING / INFO | The same, for the redraw tried on every poll |

**A Player that has stopped leaves the text console on an HDMI screen**: the
kernel gives the screen back when the process lets go of the display card. On
the wall, that is how an outage looks, and Settings › Clients shows the client
heartbeat ageing.

### The backup records that it succeeded, and the panel reads its age

`operational-spec.md` promises backup age on this panel in absolute terms — "last
successful backup: 6 days ago" — because a backup that silently stopped
succeeding a month ago is the failure that matters for the one asset nothing else
protects. The reading side shipped 2026-08-05, ahead of the job.

**The receipt is `backup-status.json` under `ART_ROOT`, and the key is
`completed_at`.** It is written **only on success**, which is what makes its age
mean what the panel says it means: a job stamping every attempt would report a
fresh age for a backup that has been failing since Tuesday. Everything else in it
is the job's to shape and reaches the panel the same way the heartbeat's does.

> `[DECISION: the backup records its success in a file beside the catalogue,
> never as a row inside it | the backup copies the catalogue, so a receipt
> recorded as a row could only ever be written after the copy was taken — every
> restored catalogue would then carry the *previous* backup's receipt and report
> an age older than the file it came from. A file beside it is stamped by the run
> that succeeded and restores as whatever the destination actually holds |
> user can veto/override]`

Both ends of this one are ours, unlike the heartbeat's, so the key cannot drift
across planes. It can still drift in time — the reader is built and the writing
job is separate, later work — which is why the name is written here rather than
left in the code that reads it.

### Source plugins: what loaded, and what faulted (2026-10-03, `source-plugins.md`)

Image sources are plugins, so a source can now be missing or broken for reasons
outside this repository. Either way the symptom is works that read as held by
nobody, which looks like a fact about art rather than about this deployment. So
the panel names every installed plugin and what became of it.

- **At startup, each plugin is loaded, declined or failed.** A declined plugin is
  installed and not configured here (the Art Institute without
  `ARTIC_USER_AGENT`), and says which setting would change it. A failed one could
  not be imported, was written for another interface major, raised in its
  factory, or broke the interface's rules, and says which. Logged as
  `source.loading` (INFO, before each factory runs, so a factory that hangs
  leaves its name), `source.loaded`, `source.declined` (INFO) and `source.failed`
  (ERROR). A `SOURCE_ORDER` name no installed plugin has is
  `source.order_unknown` (WARNING), because a misspelling would otherwise
  reorder the sources in silence.
- **While running, a loaded plugin's faults are counted.** A fault is anything a
  plugin raises outside its three answers. It is contained to the call, logged at
  ERROR as `source.plugin_fault` with the traceback's frames, and the panel shows the count
  since startup and the age of the last one. Counts reset with the process,
  because the count is about the code running now. A fault includes answering in
  a shape the interface forbids: an image under another plugin's name, or a
  `None` where a list belongs.
- **Every URL's query string is cut from every journal line**, by the formatter
  (`logs.JsonFormatter`): message, fields and traceback alike. An HTTP client's
  error names the URL it asked, a reader may answer a URL with a key in it, and a
  paid source's key usually travels in the query, so this is the "no secret in a
  log line" rule (`project-preferences.md`) applied at the one place every line
  passes. What leaves by other routes is scrubbed where it leaves: a plugin's
  failures and decline reason at the containment (they reach the health panel),
  and a recorded acquisition failure in `_record_failure` (it reaches the Work
  page and MCP).
- **The System badge counts a failed plugin and a faulting one**, never a
  declined one, which is a choice and not a problem.
- **Pages a search found are journalled by what became of them** (2026-10-03,
  `source-plugins.md` § Sightings), all at INFO, since none is a problem:
  `sightings.recorded` (how many pages, and how many were new sightings),
  `sightings.claimed` (a page an installed plugin claims, naming the plugin and
  the host, and left to it), and `sightings.no_item` (pages for a work with no
  Wikidata item, which have no key to be kept under). The count by host is a
  query (`GET /api/sightings/hosts`), not a panel signal: it chooses the next
  reader, and is read when that choice is being made.

### The panel shows staleness in absolute terms

**Never a green dot.** The health panel displays "last heartbeat: 4 days ago", not
a status light. A green indicator that is green because nothing checked is exactly
this product's characteristic failure wearing a UI, and it would be worse than no
panel at all because it manufactures false confidence.

The same rule applies to every derived status the panel shows: state the
observation and its age, not a verdict.

**"4 days ago" is the wording, not shorthand for it.** Both readings state their
age in the unit a person reads it in, because the conversion is the whole service
this panel performs: a display plane down since Tuesday reported "345600 seconds
ago" until 2026-08-05, which is arithmetic handed back to the reader on the one
surface built so they would not have to do any. A negative age — the planes'
clocks disagreeing — is reported as itself rather than folded into zero.

**Nothing here compares an age to a threshold**, and the backup is where that
restraint earns its keep: six days is alarming for a nightly job and unremarkable
for a destination that is usually asleep, and this panel does not know which
deployment it is on.

### Accepted detection latency, stated as a number

**Alerting decision, 2026-07-20:** the operator chose the curation UI health panel
as the only alerting surface — no push notifications, no email, no external
monitor.

The consequence, recorded honestly rather than left implicit: **mean time to
detection is bounded by how often the curator opens the UI**, which for a leisure
activity done in short sessions may be days. Nothing detects a stalled display
plane in the meantime.

This was stress-tested and holds up. If the display plane stalls, the TV keeps
showing the last selected work — the household sees art, just not rotating.
Budget exhaustion and disk-full are self-announcing at the next curation session,
because that is when they block something. The one failure that is genuinely bad
while undetected is **the label disagreeing with the artwork**, which shows guests
confidently wrong information; it is minor, and it is the thing to watch if this
decision is ever revisited.

Deferred rather than rejected: a push notification path (self-hosted ntfy or
similar) for the small set of conditions that would want a human now. Revisit
trigger: if undetected staleness turns out to be annoying in practice, or if
unattended/scheduled discovery is ever added — the latter removes the curator from
the session, which is what makes self-announcing failures self-announcing.

> **2026-09-30: the second revisit trigger is scheduled to fire.**
> `re-architecture.md` § Procurement adds **Watches**, standing searches that
> re-run on a schedule and may auto-accept, plus scheduled upgrade re-searches
> (wave 6). That is exactly "unattended/scheduled discovery", so the
> panel-only decision must be revisited in the wave-6 plan, before Watches ship.
> Three conditions no longer announce themselves at the next session:
> - a Watch whose job silently stopped firing. This has the topic sweep's
>   shape, so it needs a positive signal on every run, including empty ones.
> - a Watch that hit its per-period spending cap;
> - a Watch that auto-accepted something.
>
> Revisiting is not deciding to add push notifications. The operator has
> declined notifications for now. The decision is the operator's, made with this
> trigger in view.

### The one surface the panel does not cover: CI

**Scope correction, 2026-08-06.** The decision above says "the curation UI health
panel as the only alerting surface", and it was written when every failure in
this strategy happened on the operator's own hardware. There is now a class that
does not: a foreign API moving under a measurement recorded in one of the
`*-api-findings.md` documents. `.github/workflows/api-drift.yml` re-runs those
measurements on a schedule, and the panel cannot show its result — the panel
reads a running display plane, and this failure happens on GitHub's runners,
possibly while nothing of ours is running at all.

So the panel-only rule is amended rather than broken: **it governs the running
product; CI has its own route, and this section is that route written down.** Two
distinct faults, two mechanisms, because a run that failed and a run that never
happened leave completely different traces:

**A probe ran and failed.** The failing job opens an issue in this repo's
backlog, one per contract, via `.github/scripts/report_drift_failure.py`. Repeat
failures comment on the open issue rather than opening another, so the comment
history is how long the contract has been moving. **It does not close itself when
the probe goes green**, and that is deliberate: a green run proves the probe
passed, not that anyone reconciled the findings document against what the API now
returns. The operator closes it, having done that work.

*Why an issue rather than email.* GitHub's default Actions email for a scheduled
run goes to whoever last edited the cron file, is silently absent for anyone whose
Actions notifications are off, and breaks the moment somebody else touches the
file. It is also the exact mechanism the 2026-07-20 decision rules out. An issue
survives an unread inbox, does not depend on edit history, and lands where the
remedial work is already tracked. Scheduled runs only — a hand-dispatched run
already has somebody watching it.

**The schedule stopped firing.** Nothing above can fire, because no job runs.
This is the same shape as the topic sweep's `topics.swept`: the positive
signal is a successful run, and its *absence* over an interval is the fault.
`suites.yml`'s `drift-freshness` job measures how long since each tier last
succeeded — **free after 21 days, paid after 75** — reading the tiers apart,
because a healthy monthly run would otherwise vouch for three missed Mondays.
Both known routes land here: a workflow not on the default branch has never run,
and a schedule GitHub disabled for repository inactivity stops refreshing.

*Its limit, stated rather than implied.* That job runs only on a push to `main`,
so absence is detected at the next push, not continuously. A pull request cannot
fix either fault, so failing one would be a red check nobody on that branch can
clear. The undetected window is therefore exactly the window in which nobody was
working — which is the same window in which GitHub disables a schedule, and the
same one in which a stale museum measurement costs nothing.

## Spend as an Observability Signal

Spend is a *signal* here, not only a cost control: the hard cap cannot be trusted
to fail closed without something reading it.

**Read from the authority, never from a local tally.** Per-generation `cost` is
the actual spend for a run, and `limit_remaining` from `GET /api/v1/key` is the
provider's own figure for budget left. A local counter would be a second source of
truth for a number the provider owns, and the two would drift — which is the
reasoning behind the ratified provider-enforced-ceilings norm.

> *(Reversed by the owner 2026-10-07; the note under the signals table says how. #290 builds it: `GET /api/budget`, server half built 2026-10-07.)*
>
> **`limit_remaining` is not surfaced, and as of 2026-08-04 that is settled rather
> than pending.** Two measured facts stand against it: nothing outside the client
> and its tests reads it, and it lags by minutes — it was observed reporting credit
> remaining while live calls were already being refused. A panel built on it would
> tell the operator they had money at the moment spending stopped working.
>
> The question raised 2026-08-02 — show it anyway, as an advisory figure with its
> lag on screen? — **was answered no by the operator.** The reasoning is under the
> signals table: the figure fails by inversion rather than by staleness, so stating
> its age does not warn about the case that bites.
>
> This does **not** overturn the corollary above, which is a ratified norm owned by
> `nonfunctional-requirements.md` § Direction and is not this artifact's to amend.
> The corollary answers "where does budget-left come from if you show it" —
> authority, never a local tally — and that answer is untouched. The honest budget
> signals remain recorded per-run spend and the `halted_by_budget` outcome.

Surfaced in two places: before a run (the estimate, so the curator can decline)
and after (the actual). `halted_by_budget` is a first-class outcome that must be
distinguishable in both logs and tool results from an ordinary failure — an agent
has to be able to tell "you are out of money" from "the fetch failed" and stop
rather than retry.

## Sensitive Data in Logs

**No secret may ever reach a log line.** This has unusual force here because the
repository is **public** and log excerpts are exactly what gets pasted into a
GitHub issue. Concretely: no OpenRouter API key, no TV pairing token, no
client token, no full `Authorization` header, no `.env` dump on startup. A refused
Player request is logged by the client it came from, or as "an unknown client",
with the reason (`Refused a Player request from …`), once per that subject per
ten minutes, and never with the token it presented or the wall id it asked for;
`arrt/tests/contract/test_player_surface.py` holds that.

**Programming's reconciliation says what it changed** (from 2026-09-30): `Wall
…: took works the Library no longer offers off the published manifest (…)` and
`withdrew the standing pin` at INFO, naming only the works that wall lost, and at
startup, when there is nothing to do, `Reconciled N walls against the Library at
startup: nothing to change`. A start that cannot rewrite a manifest logs the
failure at ERROR and serves anyway.

Beyond credentials there is very little to filter — no accounts and no user
records. Prompts and model responses may be logged freely; they contain artwork
metadata and curatorial intent.

> **"No PII" stopped being true on 2026-08-12 and this paragraph did not notice**
> — found by Critic review, and corrected here rather than argued with.
> From then until 2026-10-09 `ConversationTurn.text` was the product's only
> retained free-text record of a person; since then the curator's words are held
> only in the server's memory for a thread's life (`security-model.md` § The
> curator's own words). Either way that is a classification this section owns the
> log-filtering consequences of, and the path is live: a Get from words hands the
> curator's sentence to `DiscoveryRunner.start(intent_text=...)`, and
> § Correlation's stated reason for structured logging is that "an intent is the
> curator's own words and goes in a log line".
>
> **So forgetting a thread does not reach the journal, and that is a limit rather
> than a gap to close.** A log line is written once and shipped; a retraction mechanism
> over journald would be a second, weaker copy of a deletion guarantee this
> product does not otherwise make. What follows instead is that **the words are
> the one thing here whose logging is a decision rather than a freedom**: an
> intent is logged because a run cannot be explained without the sentence that
> started it, and a turn's full text is not. That is the built shape rather than
> an aspiration: `run.started` carries `intent_text`, and Ask's one line per
> reply carries its thread, steps and cost and no words at all. If that ever changes,
> it changes here first. `security-model.md` is the authority on what the record is; this
> section is the authority on where it may be repeated.

## What Each Failure Looks Like

The practical test of this strategy — for each failure in `architecture.md`, what
signal exists:

| Failure | Signal |
|---|---|
| The wired collection could not be browsed | `browse.unreachable` at WARNING, and nothing else — a supplement is swallowed so it cannot fail the run, which makes this line the only trace that one was attempted. **Distinguish it from a collection that answered and offered nothing**, which is `browse.offered` carrying `works_offered: 0` against a non-zero `collection_holds`: that is every candidate declined, and `browse.below_floor` / `work.suppressed` / `work.already_present` say which gate did it |
| Display plane stalled or dead | Heartbeat stops advancing; panel shows its age |
| TV unreachable | Heartbeat carries TV connectivity state; WARNING in the journal. **The panel renders the heartbeat's whole reported document as of 2026-08-05**, so this row and the two below it have a reader rather than naming a field nothing displayed |
| E-paper panel not updating | Heartbeat carries its state, and the panel shows it — same mechanism as the row above, and no second contract. *(2026-10-08: the panel is a label output now, so its state is the client heartbeat's `label_outputs[].connected` — false for a panel that would not open or whose last draw failed — and no longer the wall heartbeat's `has_label_surface` / `label_surface_working`, which every wall reports false / null. Two things the wall heartbeat carried have no field there yet and are journal-only: why a panel would not open (`panel.unavailable`), and a geometry with no usable area (`label.unusable`, the panel still `connected`).)* **The journal answers the question the heartbeat cannot**, added 2026-08-13: the heartbeat is a snapshot of current state, so it can say the surface is working and never say *what it captioned*, and its `current_work_id` is the rotation's rather than the label's — the two disagree exactly when the label is wrong, which is the failure that matters. `label.drawn` names the work per draw, so the panel's history is reconstructable after the fact and joinable to `rotation.selected` |
| **The panel is captioning, and nobody can read it** | `label.shrunk` at WARNING per draw, carrying the lines set below the floor as the catalogue spells them, the derived `floor_px` and the `smallest_px` actually set. **The only WARNING this plane emits about legibility, and the condition an accessibility ruling rests on.** Type never shrinks to fit — except for the facts that identify the work, which shrink rather than vanishing, because a name too small to read at 7 feet can still be read by somebody who steps closer. That exception is only safe because this line exists: illegible type fails invisibly, and a panel routinely setting names below the floor is a misconfigured device — too small a panel, or one read from further than `EPD_VIEWING_DISTANCE_INCHES` claims — which nobody discovers by eye. **INFO would have been wrong**: a dropped medium is the engine working as designed and a name below the floor is a deployment that cannot show its corpus. **Not episode-gated, unlike `label.failed`**: the shrunk set is per work rather than per device, so a gate would swallow a different label's shrink to spare a repeat of the first |
| **The label surface has no usable area at all** | `label.unusable` at WARNING, added 2026-08-13, replacing the `label.drawn` that would otherwise claim a caption that is not there. Reachable rather than theoretical: the margin derives from the primary tier, which grows with viewing distance, so a device configured to be read from far enough away borders its own label out of existence. **It is guarded on facts having existed and not been placed**, because a work whose institution published no label text also lays out to nothing — and that is a fact about the record rather than about the device. **Episode-gated like `label.failed` and unlike `label.shrunk`**, and the split is the same one the `work_id` paragraph draws: a shrunk set belongs to one work, so a gate would swallow the next work's, while this is a statement about the surface and says the same thing whatever the wall shows. What causes it is a geometry setting, so it holds until somebody changes one — ungated, that is the same line some five hundred times a day at the default rotation, in the only channel this plane reports failure through. **The episode ends on `label.drawn` with no recovery line of its own**: a label actually placed is the proof, and that line already names it, where `label.recovered` exists only because `label.failed`'s success path is silent. **The heartbeat carries it too, added 2026-08-13, and the episode gate is why it must**: this row described the journal as the whole answer, and the one WARNING an episode emits can be hours scrolled away on a headless Pi while the panel has been blank throughout — so the condition is written to `last_error`, which the health panel reads every beat. **`label_surface_working` stays `true`** on that path, because the driver took the frame and the geometry is what failed; reporting the driver broken would send somebody to the panel wiring for a margin they can change in a config file |
| **A name the line breaker split across rows** | `label.name_wrapped` at WARNING per draw, added 2026-08-13, carrying the line as the catalogue spells it, the row count and the wrap width. **The fault a person found by standing in front of the panel, and the channel that would have said it.** The wall drew `KATSUSHIKA,` / `Hokusai, Japanese` / `1760–1849` — every fact split mid-phrase, the comma that inverts the name stranded at a row end where the weight distinguishing it from a list separator cannot work — and nothing reported it: type was at its tier so `label.shrunk` was silent, every fact was placed so `label.truncated` was silent, and `label.drawn` said the panel was captioning the work. The name ladder exists to prevent this and normally does; reaching here means no arrangement of the name fitted, which is a fact about the *device* — too narrow a panel, or type calibrated for a reader further away — which is why it is a WARNING beside `label.shrunk` rather than an INFO beside `label.truncated`. **Load-bearing beyond its own report**: `legibility.MARGIN_TO_PRIMARY_RATIO` cites the ladder's wrap trigger to declare itself freely movable, and without this line the next margin, viewing-distance or panel change could put the fault back on the wall in silence |
| **A work whose institution published no label text** | `label.absent` at INFO per draw, added 2026-08-13. Not a failure and not `label.unusable`: that one is the device bordering a label out of existence, this is a record with nothing to print, where a blank surface is the right answer. It has its own line because the success line it used to fall through to made two claims that were both false — that the panel was captioning the work, of a frame with no ink, and (by ending the `label.unusable` episode) that the surface had usable area again, which a label with nothing in it cannot demonstrate. Ending the episode there would have silenced the warning for every later work until the geometry changed |
| **The panel captions the wrong work, or stops captioning** | `label.drawn` at INFO per draw, carrying `work_id` and `tv_content_id`. **The only positive label signal, and it exists because every other one is an exception** — `label.failed`, `label.truncated` and `label.recovered` all fire on something going wrong, so before 2026-08-13 a panel captioning correctly all day emitted nothing whatsoever and was indistinguishable in the journal from one that stopped at boot. Its *absence* over a rotation is what says the label stopped following the wall. **A picture no manifest can name is `label.blanked`, not a success and not a failure**: somebody choosing an art-store image with the remote gets a deliberately blank panel, and a success event there would answer *why is the label empty* by naming a work that is not on the wall. It carries the content id because there is no `work_id` on that path to carry |
| Backup silently stopped succeeding | **`backup-status.json` stops advancing; the panel shows its age.** The receipt is written only on success, so a failing job goes stale rather than reporting fresh. Nothing has ever written one is itself an observation the panel states plainly |
| Manifest references a missing file | WARNING per work, and the work is skipped — the run continues |
| **The TV takes selections and displays none of them** | `rotation.wall_unchanged` at WARNING **once**, carrying the id that was accepted and the set's own `art_mode` — then `rotation.wall_recovered` at INFO when the wall starts changing again. **The pairing is the design**, because the condition lasts as long as somebody leaves the panel off: a line per rotation would be a hundred a night saying the one thing that has not changed, and journald rate-limits by dropping the ERRORs this plane's only failure channel carries. The art-mode flag is read on this path for the operator's sake — it is the answer to *why is the wall not changing*, and it costs one call on a rotation that has already failed. It is read **separately, before every selection**, for a different purpose: the plane may not touch a television somebody is watching, and that gate asks whether it may act at all rather than why it did not. **The absence of `rotation.selected` is not itself the signal**: nothing distinguishes a wall that stopped changing from a daemon that stopped running, which is what this line exists to say |
| Manifest major version unrecognised | ERROR, previous manifest retained. *(2026-09-30: the same over HTTP, from wave 2. Wave 4's major-2 bump, when compositing moves to the Player, is the planned occasion for it, so the ERROR is how an un-upgraded Player announces itself. See `re-architecture.md`.)* |
| *Planned, 2026-09-30:* the server is unreachable from a Player | The Player keeps rendering from its cache (`nonfunctional-requirements.md` § Direction, amended). It logs the failed poll once per episode rather than per poll, the same pairing `rotation.wall_unchanged` uses. The panel shows the heartbeat's age, which grows only if the POST also fails. It becomes a real fault when the manifest names media the cache does not hold, and the heartbeat's cache report exists to say that. Built in wave 2 |
| *Planned, 2026-09-30:* a scheduled Library job (Watch, upgrade re-search) stopped running | A positive line on every pass, including empty ones, as with the topic sweep. Absence over an interval is the fault. Whether it also reaches a push channel is the revisit above. Built with Watches in wave 6 |
| Budget exhausted | `halted_by_budget` outcome on the run, and the refusal text names the cause. *(Corrected 2026-08-02: this also promised "`limit_remaining` at zero in the UI" — a figure no surface exposes, and one that lags badly enough to read non-zero while calls are already being refused. See the note under the signals table.)* |
| Acquisition queue stopped running | `acquisition.queue_pass` at INFO on every pass, including empty ones; its absence for more than a day, or after an acceptance, is the fault, and Activity › Queue keeps showing *queued* works that never move. A run of `acquisition.queue_paused` is the deployment refusing (disk, binary, provider), not the worker dying |
| Topic sweep stopped running | `topics.swept` at INFO on every pass, including empty ones; its absence for more than a day, or after an acceptance, is the fault. A run of `topics.sweep_unavailable` is Wikidata refusing, not the sweep dying. With no `WIKIDATA_USER_AGENT` the one `topics.off` line at start says why there is nothing |
| The picture store grows without bound | **By design** (owner, 2026-10-06: no ceiling). Its files and bytes are on the health panel and `art_display(action='status')`, counted at most ten minutes ago; the operator watches the figure. *(Replaced 2026-10-06 the row for the preview sweep stopping, which retired.)* |
| Disk nearly full | Guarded *before* acquisition starts, not discovered as an exception during it |
| A work silently absent from a theme | **The manifest build reports exclusions** with a per-work reason — see `architecture.md`. Not a log line: a first-class UI surface |
| Mat colour degraded to the dominant-colour fallback | Recorded on the record itself (`MatColor.method`), not merely logged. The 2024 code degrades invisibly |
| Curation killed mid-run (OOM, deploy restart, crash) | **Startup reconciliation logs one line per run it moves to `interrupted`**, at WARNING, with the run id and its prior status. This is the only signal that a run died — the dying process cannot report its own death, and the operator's next clue would otherwise be `resolve_images` refusing work ids. Silence here means reconciliation did not run, which is itself the bug (`data-model.md` → State Machines) |
| A foreign API moved under a recorded measurement | **An issue in this repo's backlog, one per contract**, opened by the failing `api-drift.yml` job; repeat failures comment on it rather than opening another. Not the panel — this failure happens on GitHub's runners, possibly while nothing of ours is running. It stays open until a human reconciles the `*-api-findings.md` document, because a green re-run proves the probe passed and nothing about whether anyone did the work. See § The one surface the panel does not cover |
| The API-drift schedule stopped firing | **The only signal is a positive one, exactly as with the topic sweep**: a successful run per tier, whose *absence* is the fault. `suites.yml`'s `drift-freshness` job fails past 21 days (free) or 75 days (paid), reading the tiers apart so a healthy monthly run cannot vouch for three missed Mondays. Covers both routes — never on the default branch, and disabled for repository inactivity. Detected at the next push to `main`, not continuously |
| A default-suite regression reaches `main` | `suites.yml` runs all three default suites — the 2024 modules, curation, and display since 2026-08-06 — on every pull request and every push to `main`. Until 2026-08-06 there was no such signal at all: the repo had two workflows, and neither ran the suites that gate correctness, so a reviewer reading two green checks was reading the browser suite and a schedule |
