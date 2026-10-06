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

## 2026-10-05: Norm Health sweep: the rules re-measured, and the owner's rulings built

<!-- prawduct: scope=norm-sweep-2026-10 | release=v0.3.0 -->

**Why:** the sweep was 64 days overdue, and the first since the 2026-09-30
re-architecture, the display plane and the paid discovery path. Measurements and
the owner's rulings are in `project-state.yaml` (`norm_health`, 2026-10-05). Plan:
`build-plan-norm-sweep-2026-10.md`.

**What:**
- **Records.** The service-layer norm amended (bindings compose, never branch on
  a result); the manifest norm says the Player makes only the requests
  `contract/routes.json` names; the broad-except norm exempts a catch that always
  re-raises, superseding the 2026-08-02 ruling, because ruff `BLE001` now audits
  it. Four `data-model.md` norms indexed; four unassigned preferences assigned;
  stale chunk references, departures and counts brought to the tree. Issues
  #215–#218 filed; ten older items given their filing reason. Also on this
  branch: `upgrades.md`'s reserved questions relabelled U1–U6 (Q38–Q43 had been
  given to others), the owner keeping the exhibit-E skip rule, the stats
  contribution preference (`always`), and two learnings (a core rule amended, a
  new `learnings/tooling.md`).
- **The deployment guard no longer publishes the deployment.** It checks shapes
  (a private address, a named home directory) and this checkout's own `.env`
  values, never the values themselves. A home path in a legacy comment, the Pi's
  hostname and login, and an email in two live tests' User-Agent are scrubbed.
  History is not rewritten (the owner's ruling).
- **Guards and fixes.** Commons reads an unrecognised page as "could not be
  asked"; the scrim text pair is computed; the startup secret test covers every
  declared secret; the surfaces import persistence records and never a store
  (#24, `WorkOrder` and `BackupReading` moved to `records.py`); the Player's token
  check is a dependency, with its refusal shape now tested on all five routes;
  the root's module set may only shrink, and tests live in their plane's
  `tests/`; the mat fallback's stored reason names its case (#212); a run's
  threads are joined before its test's store closes (#198); the heartbeat guard
  compares the key both bodies carry and pins it to the contract.
- **Ruff, gone big** (the owner's ruling). Both planes select every rule ruff has,
  less a short ignore list each with its reason; the root adds `N` and `BLE`, its
  2024 modules leaving at wave 5. The residual was fixed, or waived per line with
  a reason, and `tests/preferences/test_waivers.py` now refuses a waiver without
  one. The curation plane's half was built by a delegate in its own worktree and
  merged here; its one behaviour slip (Playwright route handlers as bound
  methods) was caught by the browser suite and reverted.
- **Wanted is a section of its own**, after Activity, as in Sonarr, Radarr and
  Lidarr (the owner's ruling, against IA ruling 9). It is drawn hidden and shown
  once its count says something is wanted, which also ends a sidebar race the
  browser suite tripped on once in six runs. Cards now say a work "waits in
  Wanted".
- **Tests changed, none weakened:** composite asserts split, three assigned
  lambdas made functions, blocking HTTP in async tests moved off the loop, and the
  sidebar tests rewritten to the new section list.

## 2026-10-05: A run keeps why it ended

<!-- prawduct: scope=run-end-reason | release=v0.3.0 -->

**Why:** a run that failed kept no record of why. The runner composed a reason
at every failure site and only logged it, so the API, the MCP `status` action and
the run page all said "failed". Seen on an Ask for Lucy Bull (run `4756cdee`),
whose reason could not be recovered without the container's log (#207). Plan:
`build-plan-run-end-reason.md`.

**What:**
- New nullable column `discovery_runs.end_reason`, added in place by widening.
  `fail_run` and `halt_run_for_budget` require a non-blank `reason` and store it
  with the ending; every other ending stores null (`data-model.md`).
- The runner passes the reason it already logged. A fault nothing anticipated
  stores "Phase N failed unexpectedly. The server log has the details." and never
  the exception's text.
- `end_reason` on every HTTP and MCP run shape, listings included
  (`api-contract.md`). The MCP notice for a failed run names it when it is set.
- The run page shows "Why it stopped: …" under a failed or halted run's sentence,
  as text. A failed run from before the column keeps the log pointer.

**Review:** cumulative, 0 blocking, two warnings. The new
blank-reason refusal, raised inside the worker's handlers, would have stranded a
run whose engine error had an empty message; `_end` now replaces a blank reason.
A halt's reason was described as carrying a 402's arithmetic; a halt is a 403,
and the records now say so. Both verified in a second pass.

## 2026-10-05: An Ask's search hands the pages it read to the source plugins

<!-- prawduct: scope=ask-pages | release=v0.3.0 -->

**Why:** the owner chose Artlogic, the gallery platform, as the next source, found
through Ask's web search rather than a list of galleries. Gallery works have no
Wikidata item, so no plugin could be told where to look. Measured: a search for an
artist's paintings cites the gallery's artist page (`procurement-corpus.md` § The
probe: Artlogic, and what Ask's search cites). Plan: `build-plan-ask-pages.md`.

**What:**
- Phase 1 keeps its search's citations (`WorkList.citations`): in the search's
  order, each once, http(s) only. Never an address from the model's answer.
- New table `run_citations`, written when phase 1 closes (`data-model.md`
  § RunCitation, Q46–Q47).
- Phase 2 hands every work the run proposed its run's citations as
  `ImageQuery.pages`, on approval, on a re-search and after a restart. Each passes
  `check_fetchable` first, once per run per pass; a refused one is dropped and
  logged (`phase_two.page_refused`). A Get has none. The container hands the
  check the same resolver acquisition uses, so a suite's stated DNS answers
  reach it too.
- The plugin interface is 1.1. A plugin written for 1.0 loads unchanged.
- `check_fetchable` refuses a URL it cannot parse (`http://[x/`) and a name the
  resolver cannot encode (`a..b`, a label over 63 characters) instead of raising
  a parser's error. A stored citation of either shape would otherwise have failed
  its run's phase 2 on every re-search; acquisition's three callers gain the same.
- `security-model.md`: bound 2 re-derived for plugin reads of cited pages
  (§ Plugins read pages a search cited), with the owner's approval.
- **The gallery source itself is a private plugin**, `artlogic` in `arrt-sources`
  (`eedae73`), which this repository does not ship. With it, run 6 found all six
  of the corpus's gallery rows through Ask, at the galleries' stored originals
  (`procurement-corpus.md` § Run 6). A failed run keeping no reason was filed as
  #207.
- **Shipping and rolling back.** `run_citations` is additive: an older build
  opens the file and ignores it. Arrt and the plugin image are built together
  (`arrt-sources:<arrt>-<plugin>`), so roll them back together; the `artlogic`
  plugin under an Arrt before 1.1 answers every work "not answerable" rather
  than failing.
- Also carried: two wording fixes owed from PR #203's review (`re-architecture.md`'s
  master-size-cap question; `project-state.yaml`'s blocking line).

## 2026-10-04: Library screens — Artworks' theme filter and Select mode, a work's mark, Artists by surname

<!-- prawduct: scope=library-screens | release=v0.2.0 -->

**Why:** the owner's review of the Library screens (#169, #172-#175): the theme
dropdown on Artworks read as a filter and was an editor; search's *Image found*
badge read as if it might mean held; the Artists index sorted by first name in
one narrow table; the Wikidata identity controls all showed at once; Library ›
Topics was one long column. Plan: `build-plan-library-screens.md`.

**What:**
- `GET /api/works?theme=<id>` and `art_catalogue(action='list', theme=...)`
  narrow to one theme, composing with facets and text. Each binding composes
  Programming's `theme_work_ids` with the Library's listing restricted to those
  ids (seam rule 1). Each page carries the themes with counts against the other
  filters. An unknown theme is refused by name.
- Artworks: *Theme* is the Filter rail's first group. **Select** mode shows the
  ticks and an action bar that adds the ticked works to a theme or removes them
  from the theme being filtered. An address naming a deleted theme shows the
  works the other filters select and says the theme is gone.
- A work's mark: held, wanted and not held each have their own image style
  wherever registry works are listed (typeahead, Search results, a Topic, an
  Artist's *Their work*, a work's *More by*), each keeping its glyph and word.
  Registry works report `wanted`.
- Artworks, behaviour that changed: a filtered theme now follows the Sort menu
  rather than its own curated order, and the Sort menu is offered with it. The
  rail's *Themes* list with its *Open* buttons and *Manage themes*, and the
  toolbar's always-shown theme picker, are gone: themes are reached from
  Library › Themes, and the picker lives in Select mode's action bar.
- Library › Artists sorts by surname (the stored family name, else the last
  word once a generational suffix such as *the Younger* or *Jr.* is set aside),
  shown as posters by default with a table view in the address.
- Artist and Work pages show the Wikidata identity with one quiet *Edit*.
  Library › Topics lays each kind out in columns.

**Tests changed, and why:** each retired test asserted a design the owner's
review replaced; its successor asserts the new design.
- `test_a_theme_chip_filters_the_grid_to_its_members`,
  `test_the_rails_filter_and_its_opener_are_separate_controls_with_separate_names`
  and `test_the_rails_opener_goes_to_the_theme_rather_than_filtering_the_grid`:
  the rail's Themes list and its *Open* buttons are gone. Replaced by
  `test_a_theme_in_the_filter_rail_narrows_the_grid` and
  `test_filtering_by_a_theme_and_changing_its_members_are_different_controls`.
- `test_a_theme_is_shown_in_its_own_order_so_sort_is_not_offered`: a filtered
  theme now follows the Sort menu. Replaced by
  `test_a_theme_filtered_here_is_in_the_sort_menus_order`.
- `test_the_table_carries_the_tick_only_when_there_is_a_theme_to_add_to`: ticks
  now show only in Select mode. Replaced by
  `test_the_table_carries_the_tick_in_select_mode_only_when_there_is_a_theme_to_add_to`.
- `test_the_item_field_stays_hidden_until_change_is_pressed`: the identity's
  *Change* became one *Edit* that hides every control. Replaced by
  `test_at_rest_the_control_is_the_identity_and_one_edit`.
- `test_held_artists_are_listed_with_counts_and_open_their_page` and
  `test_held_artists_by_name_with_works_in_circulation_counted`: the index went
  from name order to surname order. Replaced by
  `test_held_artists_are_posters_in_surname_order_and_open_their_page` and
  `test_held_artists_by_surname_with_works_in_circulation_counted`.
- `test_removing_from_a_theme_takes_the_tiles_out_and_says_what_is_left` waits
  for the rail's count instead of reading it at once: the rail is recounted by a
  fetch after the tile goes, and under parallel load the immediate read saw the
  old count. Same assertion, same strength; a rail that never recounts still
  fails it, checked by removing the recount.

**Owner verification:** 2026-10-04, "Screens are good".

## 2026-10-04: A title worded differently by its holder

<!-- prawduct: scope=title-identity | release=v0.2.0 -->

**Why:** run 3 found seven of the nine open MoMA works; phase two's title gate
refused the other two on wording ("Tree" against MoMA's "The Tree"; Taeuber-Arp's
long title against MoMA's "Composition"). The owner ruled: a leading article
passes; a holder's shorter title does not pass on its own; a page the work's
Wikidata item records does. Plan: `build-plan-title-identity.md`.

**What:**
- `title_key` drops one leading English article (`the`, `a`, `an`) followed by
  whitespace in the title as written, so "A. Lincoln" keeps its initial; quotes
  or emphasis before it are passed over, and a title that would be left empty
  keeps its article. It is
  half of `work_dedup_key`, so the identity key changes with it. The generic-title
  guard compares the title without its article, so "The Portrait (Hands)" keeps
  its parenthetical.
- `phase_two.not_the_work` names `found_url`, `qid` and `link`, how the title
  gate was or was not settled.
- Phase two passes a result whose title differs when the work has a QID and the
  result's `url` is exactly one of `Registry.pages_about(qid)`. The artist check
  still runs. The registry is asked at most once per work, only on a differing
  title; one that cannot be asked means no link (`phase_two.link_unavailable`).
  The review card says the title differs and what identified it.
- The container hands phase two the deployment's registry.
- The startup repair re-derives every stored key, not only those whose title it
  re-cleaned, and reports re-keyed rows apart (`works.rekeyed`, at INFO). Before
  this, a change to the derivation alone left stored keys under the old rule.
  **A rollback does not undo it:** the previous build re-keys only re-cleaned
  titles, so article-titled rows stay split from new proposals until this build
  is redeployed or the pre-deploy catalogue copy is restored.

**Tests changed, and why:**
- `test_a_stored_title_the_rules_do_not_reach_is_left_exactly_as_it_is`: it
  seeded keys no writer produces (`title.lower()`) and asserted them unchanged.
  The repair now rewrites any stale key, so the rows are seeded with the keys the
  rules derive. It still asserts title and key unchanged, and now also that no
  repair is logged.
- `test_a_work_the_curator_already_rejected_is_not_proposed_again` and
  `test_the_stored_estimate_counts_the_works_actually_proposed`: they wrote the
  old derivation's key out by hand (`salvador dali::the elephants`). They now
  seed the key the rules derive, with the artist the row would carry.
- The shared `propose` fixture defaults a key to its title's derivation rather
  than `title.lower()`, so a test that restarts the plane does not see its rows
  re-keyed.
