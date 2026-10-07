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

<!-- prawduct: scope=artist-name-identity | release=v0.4.0 -->

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
- **Still refused:** prints `after` a design and multiple makers (#257),
  honorifics Wikidata does not record, and token order (#79). The owner ruled
  2026-10-06 that a page the item records does not vouch for the artist alone.

## 2026-10-06: The NGA, through a copy of its open data, as a built-in source; plugins get a directory of their own

<!-- prawduct: scope=nga-source | release=v0.4.0 -->

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

<!-- prawduct: scope=navigart-source | release=v0.4.0 -->

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

<!-- prawduct: scope=artist-search-review-fixes | release=v0.4.0 -->

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

<!-- prawduct: scope=ci-browser-shards | release=v0.4.0 -->

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

<!-- prawduct: scope=look-before-get | release=v0.4.0 -->

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
