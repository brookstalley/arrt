# Change Log — Samsung Frame Art Loader

<!-- Append new entries at the top. Each entry is a ## section.
     This file is separate from project-state.yaml to reduce merge conflicts
     when multiple branches add entries simultaneously.

     # Tagged entries

     Add a tag-line directly under each ## header recording its rollup scope
     and, once released, which release it belongs to.

     **Nothing is REGENERATED from these tags any more — but they are still
     READ, and the difference matters when you write one.** `prawduct-hook
     regen-views` once rebuilt the build-plan `## Status` block, a release-notes
     view and a `scope_rollups:` block from them; prawduct v3.2.8 retired that
     command and the `views_enabled` switch that governed it, so this header
     spent three releases telling readers to run something that no longer
     exists.

     What survives is consumption, not generation. `scope=` and the *absence* of
     `release=` are how release-readiness enumerates work that has not shipped —
     which is why any value at all in `release=`, a placeholder included, drops
     that entry's whole scope out of the pending set. The PR flow refuses a
     branch whose entry carries no `scope=`. Only `status=` is inert now, and
     the Status checkboxes are ticked by hand and believed by every reader.

     Format:

         ## YYYY-MM-DD: title (vN.M.P)

         <!-- prawduct: release=v1.3.18 | scope=v1.4 -->

         **Why:** ...

     Recognized keys:
       chunks   - retired: nothing reads it. Archived entries carry it as
                  history; `scope=` ties an entry to its plan.
       release  - version string (used by the release-notes view)
       status   - shipped | merged (legacy). Write a new entry with NO
                  status= on the feature branch: a statusless tagged entry
                  is the release-pending state, and it becomes "merged" by
                  construction when its PR lands — no stamp, no post-merge
                  bookkeeping commit (protected branches take commits only
                  by PR). Flip to `shipped` as part of release-prep when
                  the integration branch is released (gitflow), or write
                  `status=shipped` directly in the closing PR when the
                  PR's base IS the release surface (trunk; include
                  `release=vN.M.P` when the product tracks versions —
                  release-notes groups by it) — either way the tag merges
                  atomically with the work it describes.
                  `merged` is a legacy stamp some logs carry; it is treated
                  as statusless. Don't invent states — the three above are
                  the whole vocabulary.
       scope    - rollup identifier (e.g., v1.4) -->

> **Names, 2026-10-01.** Entries are history and keep the names of their day. Until
> 2026-10-01 **Curatarr** named the server and **Arrt** named the player. Since then
> the server is **Arrt** and the player is **Postarr**
> (`build-plan-rename-arrt-postarr.md`). Paths and package names here are the
> old ones.


<!-- Older entries live in .prawduct/change-log-archive/YYYY-MM.md, moved there verbatim by `prawduct-hook archive-change-log`. -->

## 2026-10-06: A holder's name for the artist that Wikidata records, on the item's page

<!-- prawduct: scope=artist-name-identity -->

**Why:** arrt#245, which the owner made the top public priority the same day.
Phase 2 compared the holder's artist with the Library's under `artist_key`
alone. So Art UK's "Laurence Stephen Lowry" was refused for "L. S. Lowry", and
the NGA's "Rembrandt van Rijn" for "Rembrandt", even on the page the work's
Wikidata item records. Measured, that refused 18,252 of 67,361 NGA items with an
image, and 301 of 2,198 Pompidou items (`artist-name-identity-findings.md`).

**What:** on a page the work's item records, an artist disagreement is now
settled by Wikidata. The record is accepted at `CONFIDENT` when the Library's
artist and the holder's are both, under `artist_key`, a label or an alias in any
language of one creator the item records. Its card says the holder's name is
another one Wikidata records for the requested artist.

- **Measured:** this accepts 7,588 of the NGA refusals, 272 of the Pompidou's,
  and Art UK's Lowry. Against independent ground truth (NGA's own constituent
  QIDs, navigart's life dates), no accepted record was a different work.
- **Off the item's pages nothing changes.** Aliases name two people at times
  (Canaletto is an alias of Bellotto), so a title match alone does not earn one.
- **New registry question:** `Registry.creator_names(qid)`. It is asked once per
  work, and only for an artist disagreement on the item's page. If Wikidata
  cannot answer, the refusal stands, and a look keeps that "none" only as long
  as an outage.
- **The item's pages are now also asked when only the artist differs.** That is
  one `pages_about` per such work, where a title-matched artist refusal asked
  nothing before. An outage there also shortens a look's kept refusal to the
  outage window.
- **New log lines:** `phase_two.renamed`, `phase_two.names_unavailable`, and
  `names` on `phase_two.not_the_work`.
- **Unchanged:** `artist_key` and the persisted suppression key.
- **Still refused:** prints `after` a design, multiple makers, honorifics
  Wikidata does not record, and token order (#79).
## 2026-10-06: The NGA, through a copy of its open data, as a built-in source; plugins get a directory of their own

<!-- prawduct: scope=nga-source -->

**Why:** about 128,000 Wikidata items carry an NGA artwork ID (arrt#234), and no
NGA interface turns that ID into an image except its open data's CSV
(`nga-api-findings.md`). The owner ruled on 2026-10-06 to keep that copy, within
bounds: on disk gzipped, refreshed at most once a day with a conditional request,
in memory only when a query asks the NGA, released after six hours with no NGA
query.

**What:** interface 1.2 adds `SourceContext.data_dir`, a directory of each
plugin's own under `ART_ROOT/sources/<name>/`, which the loader narrows from one
root (a name that is not one plain path segment gets none). It holds what a
plugin can fetch again, and is not backed up. A built-in `nga` plugin
(`library/sources/nga.py`) keeps the NGA's `published_images.csv` and
`objects.csv` there under the owner's bounds, the second because the first has
no title or artist for the identity check to read. It finds a work through its
item's NGA page and reports the image under that page: the original through its
IIIF tiles, at the original's size; or, where the NGA serves only a capped copy,
that copy as a placeholder at the size the capped service states. Rights from
`openaccess`: public domain, else unknown, never in copyright. It declines with
no directory, and offers its reader alone with no registry. The built-in
enumerations, the contract (`source-plugins.md` § A plugin's own directory, with
the line naming `nga` the first plugin to keep a copy of a holder's catalogue),
the plugin guide, the security model and the `ART_ROOT` layout records name the
new directory and plugin.

## 2026-10-06: navigart.fr, through its API, as a built-in source of placeholders

<!-- prawduct: scope=navigart-source -->

**Why:** the owner ruled on 2026-10-05 that navigart.fr's 1,000 px images are
worth having as placeholders (arrt#213). One platform serves dozens of French
public collections, and about 5,000 Wikidata items link a navigart artwork.

**What:** a built-in `navigart` plugin (`library/sources/navigart.py`). It finds
a work only through its Wikidata item: each navigart artwork page the item
records is read through the documented, public API and reported under the page
exactly as the item spells it. Which vault to ask comes from a table of
publications read from each one's own front end, because one (`matisse_lecateau`,
vault 701) does not match its IDs' prefix; a page of a publication not in the
table stays a sighting. The image is the 1,000 px rendering, the largest served,
at the size the record states. The artist, written surname first in capitals, is
put in reading order so the identity check can match it. Rights come from the
holder's own line: public domain, in copyright for a `©` line, else unknown.
With no registry the plugin loads as a reader alone. It needs no setting and
never declines. The built-in enumerations (entry points, modules, the network
allowlist, the startup lines, the live roster), `docs/source-plugins.md` and
`security-model.md` name it. Measurements in `navigart-api-findings.md`.
## 2026-10-06: Artist pages that lead somewhere, quieter search marks, a settled review card

<!-- prawduct: scope=artist-search-review-fixes -->

**Why:** four things the owner hit the same day (`build-plan-artist-search-review-fixes.md`).
The library's Franz Kline had no Wikidata item, so his page listed nothing of
Wikidata's while search showed Wikidata's Kline beside him. The matcher that
links artists is hand-run and had not run since he was acquired. Lucy Bull's page
by QID said Wikidata lists no works and stopped there. Every row under *Not held*
said "Not held" again. And a review card kept *Why*, *Accept* and *Reject* after
Accept, though both verdicts are final.

**What:**
- `GET /api/artists/{id}/registry` carries `candidates` for an unlinked artist:
  Wikidata's people of that name, those whose years agree first (the matcher's
  own search and test, `identity.years_agree`, now public). The page offers each
  with *This is them*, which stores it through the identity route. Nothing is
  stored without the click. The search is kept a week (`registry.people`).
- `GET /api/registry/artists/{qid}` carries `unlinked`: library artists of that
  name with no item. The page offers *Link them to this item*.
- An artist Wikidata lists no works for is offered *Ask for their work*, which
  fills in Ask with "Paintings by <name>" and starts nothing.
- Inside a search group a mark says only what the heading does not. Artist rows
  carry none (the top result keeps its own). A not-held work reads ◐ *Image found*
  or ○ *No image known*. This holds in the results page and the dropdown.
- A decided review card says "Accepted. It is in your library." with *Open it in
  Artworks*, or "Rejected. It will not be proposed again.", where its controls
  were. Its scans offer no choice. A wanted card keeps *Forget*.
- Every candidate work served over HTTP carries `decided` (`Verdict.is_terminal`),
  which the card hides its controls on, so the client keeps no copy of the
  final verdicts. It is HTTP-only, as `RunOut.is_terminal` is. Additive.
- The picture-store norm in `data-model.md` is re-affirmed by the owner: #61, #62
  and #81 are the history it closed (the startup advisory, answered the same day).

**Tests changed, and why:** in `test_the_search_results_page.py`,
`test_held_then_not_held_each_marked_and_nothing_twice` is renamed
`…_marked_only_where_the_group_does_not_say_…`. It and the tests asserting
`● In your library` on a grouped artist row, and *Not held* in a not-held work's
mark, now assert the owner's ruling, with absence assertions added. The top
result's `● In your library` assertion is unchanged. In `test_search_one_world.py`,
`test_wikidata_follows_the_library_and_shows_nothing_twice` changes the same
way. This records a changed requirement; the contract was not weakened.
`_answered` there and in `test_topics.py` read `#view p[aria-live]` before the
page drew it, and failed under `-n auto` on develop as well. They now wait for
the Not held group's own note.
`test_surface_parity.py`'s `…_agree_but_for_one_named_field` is renamed
`…_agree_but_for_the_named_fields`. `decided` joins `rationale` as a named
HTTP-only field, for the reason `RunOut.is_terminal` is one. The check is
unchanged: each exempt field is still named.

## 2026-10-06: The browser suite runs in four CI shards, and skips record-only pull requests

<!-- prawduct: scope=ci-browser-shards -->

**Why:** the owner, 2026-10-06: CI was slow. The browser suite ran as one serial
job of about ten minutes on every PR. It is serial on purpose: its tests time
real poll windows, and parallel workers on a CI runner's few cores make them flaky.

**What:** `.github/workflows/browser.yml` runs four jobs side by side. Each is
still serial, on a share of the files that `.github/scripts/browser_shard.py`
computes from the directory, balanced by test count (158, 157, 157 and 158
`def test_` lines at the time). Locally the four shares collect exactly the 692
tests the single job did, with none twice. Each shard keeps the job's "nothing
actually ran" guard. A pull request that changes only Markdown, `.prawduct/` or
`docs/` skips the browser workflow: no browser test reads those, checked by grep.
Neither `develop` nor `main` has branch protection, so no required check is
stranded by the new job names. `tests/test_browser_shards.py` (root suite) holds
that every test module pytest would collect under `tests/browser` (by its own
rule, `test_*.py` and `*_test.py` in any subdirectory, walked independently of the
script) is in exactly one share, and that the matrix is the one place the shard
count is stated, the job reading it back as `strategy.job-total` and
`strategy.job-index`. **From review:** the first version listed top-level
`test_*.py` only, and its test used that same listing, so a nested or `*_test.py`
module would have run in no shard unnoticed. Fixed, and the planted case fails
against the old listing.

## 2026-10-06: A look shows what the image sources hold of a work, before any Get

<!-- prawduct: scope=look-before-get -->

**Why:** the owner, 2026-10-06: a work's page should show what it looks like
before the Get, asked of the sources on every unheld work page, "as long as we
cache the result so repeated similar searches don't do too many queries."

**What (`build-plan-look-before-get.md`, Chunks 01 and 02):**
- **`LookService`** (`library/services/look.py`), wired as `Services.look`. It asks
  every image source what a Get would ask and judges as a Get judges, and writes
  nothing to the catalogue. Answers are kept in memory per work and source: 6 h for
  an answer (holding nothing and "can't look this up" included), 10 min for "could
  not be asked", never as holding nothing, and at most 256 works. One look at a
  time asks each source, on threads of the look's own; a second look joins the
  first; a queued ask for a work nobody has polled for 20 s is dropped; a run using
  a source goes first. A finder of pages only is not asked.
- **Get's code extracted, not copied, with Get unchanged:** `ImageSourcePool.ask`
  (one source, sorted as the pool sorts every answer; `find_images` is rebuilt on
  it) and `wait_for_runs`; `PhaseTwoEngine.judge`, `rank` and `link`, public;
  `WikidataLink` (was `_WikidataLink`) safe to share between threads; the query
  builders `get.chosen_work` and `runner.image_query`; and
  `RegistryWorkService.known`, `view` without the picture's size, so a poll costs a
  kept answer and the library's own rows.
- **Surfaces:** `GET /api/registry/works/{qid}/look` (polled; answers at once),
  `GET /api/registry/works/{qid}/look/pictures/{key}?size=card|large` (from the
  picture store, by a key the server computed; a key the work's current look does
  not name is a 404), and `art_discovery(action='look', qid=…)`, which holds up to
  30 s within a 40 s budget and inlines the best six pictures.
- **Carried from the picture store's review:** `picture_key` encodes with
  `errors="surrogatepass"`, so a lone surrogate in a source's URL cannot make
  `PictureStore.keep` raise.
- **Observability:** `look.started`, `look.source_answered`,
  `look.source_unreachable`, `look.abandoned`, `look.picture_served`, and a
  `look_qid` context variable stamped by the run-correlation filter.
- **Records:** `api-contract.md` (the routes, and the one registry page with an MCP
  twin, with why), `security-model.md` § Direction (a look's picture by a
  server-minted key), `observability-strategy.md` (the events and `look_qid`).
- **Container:** `Services.bind` takes `look_now`, the clock a look's kept answers
  age by, so a suite can expire one.
- **The Work page (Chunk 02):** `screens/work.js` draws *What the image sources
  hold* for a work not held, polling `/look` every 2 s while a source is still
  asking and repainting only its own section: a row per source as a glyph and a
  word, the finds best first as enlargeable cards with pixels, fit, source and
  rationale (six, then *Show N more*), and one `role=status` line that changes
  only when its words do. A picture once drawn is never redrawn or moved, so a
  poll never moves focus. Wikidata's picture stays on top; without one, the first
  find takes the top and keeps it. A source holding the work with no size reads
  "Holds this work but gives no size for it; not shown" rather than "Holds none".
  The line under *Get this work* now reads "These are what the sources hold now;
  getting the work records them and spends nothing.", and the old sentence's
  half about Wikidata's picture moved under that picture. Records:
  `information-architecture.md` (the Work rows in § Screen Inventory, § Information
  Hierarchy and § Screen States), an operator-verification entry, and
  `tests/browser/test_the_look.py`.
- **Review fixes to Chunk 01:**
  - **A queued ask is dropped only if, under the lock that drops it, nobody now
    wants it**, and a look lists a row for every configured image source, an
    unanswered one as `asking`, so a held look can no longer lose a source or read
    finished while one has not answered.
  - **Every new fan-out builds its question and Wikidata link afresh**, and a
    "none" judged while Wikidata could not be asked is kept 10 min, not 6 h
    (`WikidataLink.unavailable`).
  - **A source's thread that stops or never starts** answers its waiting asks as
    `unreachable`; finder and judge faults log `look.source_unreachable` at WARNING.
  - **Registry states map to look states by a stated table**; an unknown one is
    refused by name.
  - **`look_qid` is bound around the picture route and the model's picture
    fetches**, so the store's `picture.*` lines carry it.
  - **The MCP look fits the client's minute**: `LookService.look_for_a_model`
    holds up to 30 s, sends the pictures the store keeps, fetches the rest
    together, and stops at 40 s, listing any picture not arrived as coming with
    the next call. Its notice is its own, no longer the review grid's.
  - **A look picture's `rationale` is `selection_rationale`**, the name a scan's
    carries on both surfaces, and a tip maps the look's size and fit names onto
    `list_images`'.

## 2026-10-06: The preview sweep is retired, and the picture store is on the health panel

<!-- prawduct: scope=picture-store -->

**Why:** the owner's norm that every picture Arrt fetches from outside is kept
(`data-model.md` § Direction), with that day's rulings: no ceiling, the store's
size and file count on the health panel, and the store not in the backup. A sweep
that deletes decided works' previews contradicts the first; the other two are
what keeping everything costs.

**What (Chunk 02 of `build-plan-picture-store.md`):**
- **Retired:** `library/services/sweep.py` (`PreviewSweep`, `SweepResult`,
  `run_periodically`, `start_sweeping`), `Services.sweep`, `create_app`'s
  `preview_sweep_interval_seconds`, the entry point's pass-through and its
  `preview_sweep=` startup token, `Settings.preview_sweep_interval_seconds`,
  `PREVIEW_SWEEP_INTERVAL_SECONDS` and `DEFAULT_PREVIEW_SWEEP_INTERVAL_SECONDS`, the
  `.env.example` block, and the two `DiscoveryService` methods only the sweep
  called, `forget_preview` and `transaction`. A deployment's `.env` that still sets
  the variable is ignored: nothing reads it.
- **The health panel:** `GET /api/health` and `art_display(action='status')` carry
  `pictures` (`pictures_bytes`, `pictures_files`, `age_seconds`, `description`),
  from `PictureStore.size()`, a walk reused for ten minutes. Status shows it as
  *Kept pictures*. `age_seconds` is beyond the plan's two names: the panel states
  every observation with its age, and this one can be ten minutes old.
- **The review notes** say what is true without the sweep: a decided work's row
  with no picture names both reasons it may have none (never arrived, or deleted
  before 2026-10-06), and a missing file is "no longer there" rather than
  "reclaimed".
- **Records:** the stale sweep, `PreviewCache` and "disposable" passages in
  `architecture.md`, `boundary-patterns.md`, `operational-spec.md`,
  `observability-strategy.md` (the sweep's events replaced by the store's),
  `nonfunctional-requirements.md`, `api-contract.md`, `data-model.md` (the norm is
  now steady-state) and the norm's row, plus comments citing the sweep as a
  precedent, which now cite the topic sweep.

**Tests retired, each by the norm that every picture fetched from outside is kept
(`data-model.md` § Direction, 2026-10-06):** all 24 of
`arrt/tests/unit/test_preview_sweep.py`, which asserted what the sweep deletes, what
it holds back, its transaction, its loop and its shutdown, and `forget_preview`'s
refusals; in `test_container.py`,
`test_the_containers_sweep_reads_the_same_art_tree_everything_else_writes`,
`test_the_application_sweeps_previews_while_it_is_serving`,
`test_the_application_stops_sweeping_when_it_stops_serving` and
`test_an_application_given_no_interval_never_sweeps`; in `test_startup.py`,
`test_the_configured_sweep_interval_reaches_the_application`; in
`test_verdict_surface.py`, `test_a_decided_works_previews_become_reclaimable` (both
verdicts); and in `test_browser_review.py`,
`test_a_reclaimed_old_preview_is_refused_with_words_and_the_card_stops_promising_it`.
Three of the sweep file's tests were about what review says afterwards, which
survives it, so they moved to `test_review_service.py` with the new wording: a
decided work's note names both reasons and the verdict, a live work's says only
that none was kept (and nothing about deletion), and a row whose files are gone
reads as absent, not corrupt.

**Tests changed:** `test_a_decided_works_picture_is_kept_through_a_sweep` became
`…_through_a_restart` (it now runs `reconcile` instead of the sweep); the container's
concern check asserts the picture store in place of the sweep; and the review
grid's mocked note test became
`test_a_picture_that_is_not_kept_is_named_rather_than_requested`, with the new
wording. **Added:** the unreadable-header case the Chunk 01 Critic named (a
damaged 480 tier with nothing at 2,048 is never served for a larger ask, and the
picture is fetched again); the store's size, its exclusion of temporary files and
its ten-minute reuse; the backup carrying none of `pictures/`; HTTP and MCP parity
and an end-to-end check of both; and two browser tests of the panel.

**Review fixes (cumulative Critic):** the key is total, falling back to the
stripped URL where `urlsplit` raises, so an instance address with an unbalanced
bracket cannot end a run or stop a start; the import counts any failure on a row
as `failed` (broad, with the traceback for anything but a disk or row write) and
retires itself once `previews/` is gone (`pictures.import_retired`); a failure of
the store's own disk is `picture.unreadable` or `picture.unwritable` at WARNING,
never `picture.absent` at INFO, and a kept file that will not read is
`picture.unreadable` (it was `preview.not_inlined` at INFO); the size walk counts
what it could not read (`unreadable`, on both surfaces and Status) instead of
`rglob`'s silent skip; `art_display(action='status')` is built from the panel's
single `HealthService.observe()` call, with a test that places every
`HealthReading` field on it or off it by name; the startup line reads
`pictures=<path> fetching=on|off`; `PictureStore.owns`, `PictureStore.directory`
and `Settings.previews_path` are gone (only tests used the first, nothing the
other two); and `imaging.UNDECODABLE` / `UNREADABLE` name Pillow's failures once,
for every caller. Tests added for each, each seen to fail on a re-break.

## 2026-10-06: Every picture Arrt fetches is kept

<!-- prawduct: scope=picture-store -->

**Why:** the owner's norm: "we should persist all thumbnails we ever get/generate,
and use them instead of hitting sources when the ask is only for thumbnail size",
with the same day's rulings (two sizes, 480 and 2,048 px; not in the backup; no
ceiling). Recorded in `data-model.md` § Direction, replacing the paragraphs that
made candidate previews disposable, and indexed in `project-preferences.md`.

**What (Chunk 01 of `build-plan-picture-store.md`):** a picture store,
`library/services/pictures.py`, under `ART_ROOT/pictures/`. It re-encodes every
picture a source serves as JPEG at quality 82 (through `encode_downscaled`, so
the decompression-bomb guard applies), writes 480 and 2,048 px tiers through
temporary names it renames, makes one fetch for concurrent asks of one key, and
deletes nothing but its own stray `*.tmp` files at startup. It is the only module
that calls a source's `fetch_preview`, which a static test holds. `PreviewCache`
is now its client; the review card, the enlarged view and MCP's inline copy are
answered from it (the card and the enlarged view with the kept bytes as they
are). At startup the plane cleans the store and imports every file in `previews/`
a row names, under that row's key, and repoints the row; unnamed files are left.
The sweep never considers a path under `pictures/`; it retires in Chunk 02.

**Departure from the plan, found in build:** the key's normalisation keeps the
URL's fragment, where the plan said to drop it. SMK reports an image under the
page Wikidata records, and `collection.smk.dk` names its object only in the
fragment (`#/en/detail/KMS8010`), so dropping it would answer every such work's
card with one picture. Query parameters are sorted, never dropped: SMK's API
spelling carries the object in its query. The coordinator approved; the plan's
decision is amended.

**Measured bytes per picture** (2026-10-06, `PictureStore.put` on this Mac;
synthetic sources, since no museum image is tracked in the repository): the
suite's fixture, a flat 1200 × 900 JPEG, keeps 1.3 KB at 480 and 6.7 KB at 2048;
an ARTIC-sized 843 × 1000 painting-like source (blurred noise) 33 KB and 100 KB;
a Commons-sized 960 × 1200 one 33 KB and 136 KB; a 3000 × 2000 one 25 KB and
386 KB; and raw noise at 3000 × 2000, the worst case, 31 KB and 1.3 MB. The plan
estimated 35 KB and 180 KB; for previews at the sizes sources serve today
(843 to 1,200 px) the larger tier is the source's own size and about 100 to
140 KB.

**Tests changed, and why:** the old cache's tests asserted a preview's raw bytes,
its `previews/` file name and its `.partial` staging name. Their behaviour moved
to the store's tests (`test_pictures.py`) and to the phase-two caller
(`test_previews.py`): fetched once, never raises, nothing temporary left, a
relative path, kept apart from `thumbs/`. `FakeFinder` now serves a decodable
preview by default, because the store keeps only what decodes. Two browser-review
tests asserted that the sweep takes a decided work's picture away; under the norm
it keeps it, so one now asserts that, and the other asserts the reclaimed wording
for a row still naming the old directory. Fixtures that seeded `previews/` files
now keep their pictures in the store.

## 2026-10-06: Search groups what you hold and what you do not

<!-- prawduct: scope=search-held-not-held -->

**Why:** the owner pressed Enter on a work they did not hold. Enter opened
Artworks filtered to the words, Artworks lists only what is held, and the page
found nothing and offered no way on. They ruled: Enter opens one results page,
grouped *Held* / *Not held*, a group with nothing in it one line. That reverses
the ruling of 2026-09-30, kept 2026-10-01, that Enter stays on Artworks.

**What:** Enter in the search box opens `#search?q=…`, returning to the page it
was made from. The results page has two groups, Held then Not held, each with
its artists, works and topics (topics are new on the page: the library's by
name, Wikidata's from `GET /api/registry/topics`). The *All* / *In your library*
/ *Not held* switch is gone and a `view=` in an old address is ignored. An empty
Held is "Nothing you hold matches."; an empty Not held is "Wikidata has nothing
more.", or "Wikidata has nothing for …" with *Ask about* when it found nothing
at all. The dropdown uses the same halves: each group's accessible name carries
its half ("Held: works", "Not held: topics"), and the two headings are drawn
`aria-hidden`. A Wikidata match the library holds that the library's own rows
do not show sits under Held, in both places, so no row marked ● is under *Not
held*. The Held works' link to Artworks reads *All N in Artworks*
(*Open in Artworks* for one) and shows whenever the library has a match.

**Tests rewritten to the 2026-10-06 ruling** (a recorded requirement change, not a
weakening):
- `test_search_in_two_scopes.py`: `test_enter_with_several_matches_opens_artworks_filtered_not_the_first`
  → `…opens_the_results_page_not_the_first` (`#collection?q=the` with two cards
  → `#search?q=the` with two Held works); `test_enter_with_no_match_opens_artworks_saying_so`
  → `…opens_the_results_page_saying_so` (`#collection?q=Vermeer` and Artworks'
  empty state → `#search?from=walls&q=Vermeer` and "Nothing you hold matches.");
  `test_with_no_library_match_only_the_search_of_everything_is_offered` →
  `…held_is_one_line_and_only_…` (no label holding "library" → labels are only
  *Ask* and *Search*, and the one line is there); `test_typing_offers_library_matches_then_a_search_of_everything`
  (group names *Artists* / *In your library* → *Held: artists* / *Held: works*).
- `test_search_one_world.py`: `test_a_new_query_starts_with_nothing_highlighted_so_enter_searches_artworks`
  → `…so_enter_opens_the_results` (`#collection` → `#search`); group names
  *Wikidata: artists / works / topics* → *Not held: …* in
  `test_wikidata_follows_the_library_and_shows_nothing_twice` and
  `test_artists_and_works_are_shown_while_the_topic_search_is_held`.
- `test_the_search_results_page.py`: `test_all_shows_the_library_then_wikidata_each_marked_and_nothing_twice`
  → `test_held_then_not_held_each_marked_and_nothing_twice` (one list per kind with
  the *All* button pressed → a list per kind in each group, and no switch);
  `test_in_your_library_shows_only_the_library_and_asks_wikidata_nothing` →
  `test_an_old_view_in_the_address_is_ignored_and_both_groups_show` (the
  assertion inverts: `view=library` now asks Wikidata); `test_not_held_shows_only_what_the_library_does_not_hold`
  folded into the first, whose Not held rows are exactly the unheld; `test_switching_view_keeps_the_query`
  retired with the switch; `test_an_outage_leaves_the_librarys_results` →
  `test_an_outage_leaves_the_held_group_and_says_so`; `test_the_librarys_matches_open_in_artworks`
  (*Open them in Artworks* → *Open in Artworks*, in the Held works).
- `test_topics.py`: `test_the_dropdown_has_a_topics_group_after_works` (labels
  *In your library, Topics, Ask, Search* → *Held: works, Held: topics, Ask,
  Search*) and `test_the_dropdown_offers_wikidatas_topics_with_their_descriptions`
  (*Wikidata: topics* → *Not held: topics*).
- `test_the_sidebar.py`: `test_searching_from_anywhere_lands_in_artworks` →
  `test_searching_from_anywhere_opens_the_results_and_returns_there` (Artworks lit
  → the results page, whose back link returns to Walls). `test_a_search_is_in_the_address_and_narrows_the_grid`
  and `test_browser_back_undoes_a_search` keep their assertions and reach the grid
  through the results page.

New cases: Enter opens the results page; nothing held is one line with
Wikidata's works under Not held; a query matching only held things shows nothing
twice and says "Wikidata has nothing more."; a held Wikidata match the library's
rows miss is under Held; every dropdown group names its half; an outage leaves
Held standing; an old `view=library` renders both groups; more matches than
listed are one click from Artworks; topics in each group, on the page and in the
dropdown.

**From review:** each kind's heading carries its half unseen ("Held: Artists"), so
a screen reader's list of regions tells the halves apart; the held-group heading
assertion in `test_held_then_not_held_each_marked_and_nothing_twice` reads the
heading's full text for that reason. A failed topic listing no longer replaces
the page with an error: the Held artists and works stand and the Held group says
the topics could not be listed (two new tests). **Artworks' filters no longer
carry into a search made from Artworks**, since Enter now opens the results page;
search first, then *Open in Artworks*, then filter. Enter with an empty box opens
the results page's "type in the search box" note (it used to clear Artworks'
search).

## 2026-10-06: The minimum is 1,000 px on the long edge

<!-- prawduct: scope=quality-minimum -->

**Why:** the owner: "let's adjust our minimum acceptable size to be 1000, on a
1080p display with a mat that's about right for a minimum". That is the number
`re-architecture.md` left open for the Library quality profile.

**What:** the open question is answered in `re-architecture.md`, and
`nonfunctional-requirements.md` § The floor carries a dated direction note. No
code changes: until wave 4 the inch floor carries the minimum, and the owner's
deployment sets `RESOLUTION_FLOOR_INCHES=11.34` (1,000 px on its 50" 4K panel,
checked with `assess_display_fit`: 1000 × 700 passes, 999 × 700 does not).
`DEFAULT_RESOLUTION_FLOOR_INCHES` stays 12 for an unconfigured deployment.

## 2026-10-06: SMK, through its open API, as a built-in source

<!-- prawduct: scope=smk-source -->

**Why:** the owner asked for the next sources by works unlocked, and ruled that
SMK's terms allow its in-copyright images for household use (arrt#232). SMK's is
the only open API found that serves in-copyright works at full size, and about
6,900 Wikidata items of SMK works record an SMK page.

**What:** a built-in `smk` plugin (`library/sources/smk.py`). It finds by the
pages the work's Wikidata item records (any `collection.smk.dk` or `open.smk.dk`
page), takes the object number from each, asks the API, and reports the image
under the page exactly as the item spells it, so the item's link identifies it
(fragment pages included: `#/en/detail/KMS8010`). An item with no SMK page, or
none SMK knows, and a work with no item, are searched for by title and artist,
then by title alone when that finds nothing, ten objects at most. Rights come
from SMK's own statement: public domain, in copyright (SMK's page on the use of
its material, in either language), else unknown; nothing is left out for them.
The reader answers with `image_native`, measured serving the original at the
record's size for a public-domain and an in-copyright work, so no tiled fallback
was built. It needs no setting and never declines. Measurements, including the
objects with no IIIF image (one 1600-pixel file) and the page spellings Wikidata
holds, in `smk-api-findings.md`.

## 2026-10-06: Wanted pictures each work by the scan its card shows

<!-- prawduct: scope=wanted-pictures -->

**Why:** the owner, while the private Met page reader was being built (it reports
the Met's web-size and thumbnail images of in-copyright works): thumbnails should
show what a wanted work looks like, though it cannot yet hang. Wanted rows carried
no picture. The owner chose that thumbnails stay ordinary below-floor scans, and
that Wanted shows the best surviving one.

**What:** `GET /api/wanted` and `art_review(action='list_wanted')` gain `shown`:
the scan the work's review card pictures it by (the selection, else the best
surviving scan), or null when nothing was found or every scan was turned down.
`ReviewService.list_wanted` builds it with the card's own choice, so the two can
never picture a work differently. The listing is uncapped, so neither surface
reads bytes: the browser asks the preview route per row, and MCP sends no image
block and its notice points at `get_work`. Wanted's first column shows the
picture, enlargeable and badged, or words where nothing stands. *Why* is now
derived from what the work holds: it used to say "No scan found" for a work
holding a too-small scan. `met-api-findings.md` records the Met's web pages as
measured in a browser.

## 2026-10-06: A guard holds the artifact manifest to the artifacts on disk

<!-- prawduct: scope=artifact-manifest-guard -->

**Why:** nothing checked that `artifact_manifest` lists every artifact, and every
registration had been made by hand, four times over (#224). An unregistered
artifact is invisible to a dependency walk, so a sweep reports a clean pass over a
document it never saw.

**What:** `tests/preferences/test_artifact_manifest.py` fails by name on a
top-level artifact (less `build-plan-*`) the manifest does not list, a manifest
entry whose file is gone, and a file registered twice. It was seen failing on the
tree, naming `clients`, `hdmi-output-findings`, `ia-proposal`, `upgrades` and
`user-scenarios`, which are now registered with their edges. PyYAML joins the
root dev group to parse the manifest. Membership only: whether the edges are
right is not checked.

## 2026-10-06: The Met, through its open API, as a built-in source

<!-- prawduct: scope=met-source -->

**Why:** the owner asked for more sources and chose the Met's open API, after
being shown it fills none of today's 36 gaps: the three gap works the Met holds
are in copyright, and the API gives images only for public-domain works. Its
value is public-domain works later Asks propose, as full-size CC0 originals with
no key. The owner also asked how a public and a later private Met plugin would
live together.

**What:** a built-in `met` plugin (`library/sources/met.py`). It finds by the
work's Wikidata item (the Met ids its pages give) and otherwise by title search,
narrowed to the artist's objects when the Met knows the artist (a broad title
comes back in id order, not relevance). It reports the original, sized from its
JPEG header by a ranged read, and reads its own recorded URL back to the
original. **It records and claims only the API's object URL**, so a private
plugin reading the Met's web pages can claim those and each row reaches the
reader that recorded it in any order (`source-plugins.md` § One holder, two
plugins). It needs no setting and never declines, so a deployment with nothing
configured now has an image source. Measurements in `met-api-findings.md`
(the search endpoint moved on 2026-10-01; the image host refuses
`Accept: application/json`, which the live test found after the unit suite
passed). `source-plugins.md` registered in `project-state.yaml`, where it had
never been.

**Also (2026-10-06, the owner's asks mid-build):** a Settings › Sources page lists
every installed plugin, most preferred first, with the package and version that
installed it, whether it loaded and why not, what it provides, and the interface
it was written for (`GET /api/sources`). `art_discovery(action='source_plugins')` answers
the same, field for field and value for value, and `GET /api/health`'s `sources`
gained the same fields. From the review: a search cut at one page no longer says
the Met holds nothing; the image host's check has one owner; the tests run under
the plugins' real client policy (Commons' no-redirect default is now held too).
From the cumulative review: the MCP action is `source_plugins`, since
`art_catalogue`'s `sources` already means a work's provenance; an image the Met's
host says is gone (404, 410) skips that object rather than failing the work's
search; a package whose metadata cannot be read costs only its plugin's origin.

## 2026-10-05: The client revalidates every file, so a deploy cannot leave a phone half-updated

<!-- prawduct: scope=static-revalidate -->

**Why:** right after the #222 deploy the owner's phone hung on "Loading the
catalogue". The server and a fresh browser were fine. The shell and its ES modules
were served with no `Cache-Control`, and the image keeps each file's checkout
date, so a browser held unchanged-for-days modules for hours by heuristic. A
cached old module beside a fetched new one that imports a name only the new one
exports stops the client from starting. Inferred from the headers and the import
graph; the phone's console was not read.

**What:** the shell (every UI path) and every file under `/static` now carry
`Cache-Control: no-cache`; under `/static` the ETag keeps an unchanged file to a
304, and the few-kilobyte shell is sent whole (`pages.ClientFiles`,
`CLIENT_CACHE_CONTROL`). `api-contract.md` states the policy. Tested on every module and every UI
path, and a conditional request answering 304. A browser that cached the old files
still needs its site data cleared once.

## 2026-10-05: Pictures in the registry lists on a phone, and sizes on a work's page

<!-- prawduct: scope=work-pictures-and-sizes -->

**Why:** the owner's feedback after the v0.3.0 deploy. On a phone, *Their work*
marked rows *Not held · Image found* with no picture, so choosing what to Get was
guesswork; and a work's page by QID (*Rhythms*) showed Wikidata's picture with
nothing to judge it by. Plan: `build-plan-work-pictures-and-sizes.md`.

**What:**
- **Pictures at every width.** The phone rule that hid them, against
  `information-architecture.md` § A work's mark, is gone. The three registry
  lists draw each picture at 3rem from Commons' 250 px rendering; on a phone the
  badge stacks, and the By and Year columns fold under the title so the row fits.
  The long-title wrap rule now sits on the title cell (it had landed on the Get
  column), and years before the common era read "50 BCE". The search typeahead
  and results page share the 250 px rendering, still drawn at 2rem.
- **A registry work's page states sizes.** The work's own size (cm and inches)
  among the facts; under the picture its pixels and the review grid's fit badge,
  from the same `assess_display_fit`. The registry reads best-ranked height and
  width, leaving out frame, framed and mount, and asks Commons for the file's
  pixels (raster only, 5 s, none for a held work), kept per file for a week.
  The line under *Get this work* now says the picture is the one Wikidata names
  and that a Get asks every image source.
- **The size is checked for plausibility first** (the owner's ruling,
  `procurement-corpus.md` § Gaps 4): `plausible_size` withholds sides no work has,
  shapes past 50 : 1, and a shape more than 1.25× off its picture's. Corpus rows
  12 and 33 are its test cases.
- **Records.** `api-contract.md`, `architecture.md` channel 9,
  `wikidata-findings.md` § A work's size, the norm's enforcement column and the two
  "sizes are read nowhere" sentences. #221 filed (Commons alternatives).
  `learnings/core.md`'s norm rule now also says to search the norm index for a
  plan's new data at plan time, the lesson of this branch's blocked review.
