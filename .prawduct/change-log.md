# Change Log — Samsung Frame Art Loader

<!-- Append new entries at the top. Each entry is a ## section.
     This file is separate from project-state.yaml to reduce merge conflicts
     when multiple branches add entries simultaneously.

     # Tagged entries

     Add a tag-line directly under each ## header recording which build-plan
     chunks the entry shipped, which release it belongs to, and its rollup
     scope.

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

         <!-- prawduct: chunks=00,01,02 | release=v1.3.18 | status=shipped | scope=v1.4 -->

         **Why:** ...

     Recognized keys:
       chunks   - comma-separated chunk IDs (zero-padded, must match
                  build-plan.md ## Status headers exactly: `Chunk 00:`).
                  Informational: nothing regenerates from it and release
                  readiness ignores it, but it ties an entry to the chunk it
                  shipped, which a reader and the Critic's record check use.
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

## 2026-10-01: Outside text reaches the page as text, by norm

<!-- prawduct: chunks=01 | scope=one-world-search -->

**Why:** one-world search puts Wikidata's words into the typeahead, the second
page to show registry text. The first, the Artist page, was bounded only by its
own tests. The owner ratified the norm as written, so every page after is bound
by a rule, not by someone remembering one page.

**What:** `security-model.md` gains a § Direction: text from a registry, a
museum or a model is never parsed as markup, and an outside image or link is
used only from a named host or built from a checked id. Its row in the norm
index names three tests. `tests/preferences/test_external_text.py` reads every
script under `arrt/src/arrt/http/static/`, comments removed, and refuses twelve
sinks that parse markup or compile a string; the client uses none today. It also
refuses inline script in a page there. On the registry seam every string, in a
type or in a question's answer, is now typed `ItemId`, `RegistryText`,
`MuseumIdentifier` or `CommonsFile`, and
`arrt/tests/unit/test_registry_strings.py` refuses a plain `str` there. It then
answers every `Registry` question with a stranger's URL in every column, and
checks that none reaches an image, an id or a key. `works_by_identifier` now
keeps only identifiers it was asked about, where it had keyed by whatever the
answer named. Each test was watched failing first: an `innerHTML`, a `srcdoc`, a
string timer and an `onerror` attribute planted in the client; the Commons check
bypassed; a whole URI kept as an id; unasked keys kept; and a plain `str` field,
return and question. Links built from registry-supplied
strings are the Critic's to check, and the row says so. `security-model.md` §
Open's entry is closed in place. Also: the plan for this scope, and
`wikidata-findings.md` § Searching for works, and similar artists.

## 2026-10-01: Library › Artists, and the Artist page

<!-- prawduct: chunks=04 | scope=ia-foundations -->

**Why:** the owner's ruling 4: the artist is the hub. A curator getting to know
an artist (S11) wants to see who they are, what the library holds of theirs,
what else they made, and where it hangs.

**What:** Library › Artists (`#artist`), every artist with a work in
circulation, and the Artist page (`#artist/<id>`): life dates and nationality;
Wikidata's description and movements; *More like this* and *Not this* writing
an artist affinity; *In your library* with *Add to theme* on a selection, sharing
Works' logic through the new `core/membership.js`; *Their work*, the 50 most
renowned works Wikidata lists plus every work the library holds, each marked
*Held* (by QID) or *Image found* (a Commons file); and *Holdings*. The registry
half is its own request (`GET /api/artists/{id}/registry`), remembered per
artist, with four states each said in a sentence, so a slow or absent Wikidata
holds nothing up. Registry text is rendered as text only, and an image is only
ever a Commons file URL. Artist names on work cards, table rows and the Work
page open the page; the top-bar search offers matching artists first (two
typeahead tests changed their expected lists for that). `GET /api/works` and
`art_catalogue(action='list')` gain `artist_id`, because the owner's catalogue
holds no facet rows to filter by. `search_fold` moved to
`persistence/folding.py`, which both the adapter and the artist index use.

Also carried: Chunk 03's review observations. A test where two creators narrow
the name search, and the `set_*_qid` tips no longer overstate what `none` does.
And the cumulative review's record work: Wikidata is channel 9 in
`architecture.md`; `security-model.md` § Registry text says what bounds
registry text in the browser and lists the norm owed before one-world search;
and every findings file, the five older ones included, is in the artifact
manifest (backlog #147).

## 2026-10-01: Works and artists carry a Wikidata QID where one is certain

<!-- prawduct: chunks=03 | scope=ia-foundations -->

**Why:** the owner's ruling 7, so the Artist page (and later, search) can tell
which registry works the library holds without matching titles.

**What:** `wikidata_qid` and `wikidata_qid_set_by` (`matched` | `curator`) on
artworks and artists. A probe of the owner's catalogue (`wikidata-findings.md`)
settled the rules: a work matches only through the holding museum's identifier
on Wikidata (Art Institute `P4610`, Google Arts & Culture `P4701`), never its
title; an artist matches as their matched works' one creator, else by a name
search narrowed by agreeing life dates, never by name alone (which matched the
culture *Moche* to a 1633 painter). The matcher fills only identities nobody has
set, so it is idempotent and a curator's QID or "there is none" stands. It runs
by hand, `python -m arrt.identify`, with `WIKIDATA_USER_AGENT` set (no
default, per the museum norm); on a copy of the owner's catalogue it matched 22
of 40 works and 24 of 31 artists with nothing ambiguous, and a second run
changed nothing. The curator sets or clears a QID with `POST
/api/works|artists/{id}/wikidata` or `art_catalogue(action='set_work_qid' |
'set_artist_qid')`. The client sends to one constant endpoint and follows no
redirect. A `live_museum` test pins the shapes the client relies on.

Also carried: Chunk 02's review observations. The *Make default* button's
accessible name now contains its visible words, a constraint test shows the
store refusing a second default, the Theme screen's two conditional lines are
asserted present and absent, and `architecture.md`'s rule-3 inventory names the
migration that reads across the seam.

## 2026-10-01: All works is the default theme, and acceptances join it

<!-- prawduct: chunks=02 | scope=ia-foundations -->

**Why:** the owner's ruling 8, "There should be a default 'all works' theme."
Nothing added a work to a theme automatically, so an accepted work landed nowhere
it could be hung.

**What:** `themes.is_default`, at most one under a partial unique index, written
only by `make_default` (`POST /api/themes/{id}/default`, `art_theme(action=
'make_default')`). Programming subscribes to the Library's `work.accepted` and
adds the work at the end of the default theme. A new `default_theme_offers`
table records each work offered, joined or not, so each is offered once: a work
taken out by hand stays out through a restore (which the Library announces as an
acceptance) and through the startup catch-up of lost announcements. A one-time
migration marks *All works* (ignoring case) and records every held work as
offered, archived ones included; run twice on a copy of the owner's catalogue it
marked *All works* and recorded 40 of 40. Deleting the default is refused with
the reason; renaming keeps it. The Theme screen shows ★ *default* in the accent
colour, offers *Make default*, and says when no theme is the default. A restored
work not rejoining is an ASSUMPTION in the plan, recommended to the owner.

## 2026-10-01: Library search ignores case, accents and ligatures

<!-- prawduct: chunks=01 | scope=ia-foundations -->

**Why:** `dali`, `miro` and `rene` found nothing in a library holding Dalí, Miró
and Magritte, and the typeahead offered only a paid museum search
(`user-scenarios.md` § What the search box can mean). SQLite's `LIKE` ignores
case for ASCII only and never ignores accents.

**What:** both sides of the search clause pass through `search_fold`
(casefold, NFKD with the marks dropped, and a short table for letters Unicode
does not decompose, such as ø and œ). The catalogue adapter defines it on its
own connection, via a new `SqliteDurableStore.define_function`. The searched
columns are folded as one separator-joined string per work, and the fold
remembers what it folded, so that a request's repeated evaluations stay cheap.
A search response at 4,000 works went from 26–35 ms to 44–66 ms
(`tools/search_latency.py`, which now times the folded clause too). The HTTP
route, the MCP `list` action and the typeahead are tested with an unaccented
query, as are a German ß, Greek, a ligature, and a name stored decomposed.
Watched failing against the unfolded code first: 13 route tests and the
typeahead test, every unaccented or non-ASCII spelling among them.

## 2026-10-01: pyjwt and urllib3 bumped for the open Dependabot alerts

<!-- prawduct: scope=deps-security-2026-10 | release=v0.1.0 -->

**Why:** 18 open Dependabot alerts. pyjwt 2.13.0 (12 alerts, one critical)
reaches the server through `mcp[crypto]`; urllib3 2.7.0 (3 per plane) reaches
both through `requests`. Neither is named in a pyproject.

**What:** `uv lock --upgrade-package` moved only those two: pyjwt 2.15.1 in
`arrt/uv.lock`, urllib3 2.8.0 in `arrt/uv.lock` and `postarr/uv.lock`. Wave 5's
recipe in `re-architecture.md` now names the server rename commit and its merge
by id, and the pass-1 commit set across every ref, since filter-repo rewrites
them all and a one-tip set misses an unmerged branch cut after the rename.

**Not closed by this merge:** GitHub files the alerts against main's
`curation/` and `display/` lockfiles, so they close when develop is released.

## 2026-10-01: Arrt and Postarr — the products renamed again

<!-- prawduct: scope=rename-arrt-postarr | release=v0.1.0 -->

**Why:** the operator renamed both products under a hard requirement: the
server is now **Arrt** and the player **Postarr**. Until today they were
Curatarr and Arrt. The operator called it the last rename and asked that it not
be built as a feature, so there is no indirection; it is a plain rename.

**What changed:**
- **Two commits, in a fixed order, because "Arrt" swaps meaning.** First
  `arrt/` → `postarr/` (the player), leaving no `arrt` outside the history.
  Then `curatarr/` → `arrt/` (the server), leaving no `curatarr`. Each step's
  completeness is an empty grep for a name that no longer exists, and a rename
  roster: 58 and 263 tracked files, every one carried by a rename.
- Packages, imports, `pyproject.toml`s, lockfiles, CI jobs, unit files,
  `deploy/README.md`, the learnings' path globs, `CLAUDE.md`, `README.md`,
  `docs/` and the live artifacts follow. The MCP server is advertised as `arrt`.
  The User-Agent, the schemas' `$id` and `backlog_service_repo` name
  `github.com/brookstalley/arrt`. The browser's title and brand read **Arrt**.
- `tests/preferences/test_plane_isolation.py` now asserts that postarr imports
  no arrt module. It was watched failing once against a planted import.
- **History keeps its names.** This file and the four completed plans carry a
  dated note at their head instead. A few lines that record the naming
  history keep the old names on purpose.
- **Wave 5's filter is commit-aware now.** The player lived at `display/`,
  `arrt/` and `postarr/`, and `arrt/` is the server from the second commit on.
  `re-architecture.md` § Order of work records the recipe and the check to run
  before trusting it.
- `operator-verification.md`: the pending wave-2a step on the Pi becomes one
  step covering both renames. It removes every project's `.venv` before the
  pull, because a checkout that took wave 2a has the player's virtualenv in
  `arrt/`, where the server now lands.
- Carried from the PR #156 review: `information-architecture.md`'s current
  text says Artworks and the top bar's status indicator rather than Collection
  and the masthead. The new-objects open question tests against the *arr
  norm. Add New's empty state no longer mentions runs. `project-preferences.md`
  marks `test_the_three_destinations.py` as deleted, with `test_the_sidebar.py`
  as its successor. The "Chunk 05" in `screens/collection.js` is gone.


## 2026-09-30: The *arr navigation: the sidebar, Activity, two-scope search and the page toolbar

<!-- prawduct: scope=arr-navigation | release=v0.1.0 -->

**Why:** the owner ruled that Curatarr's browser surface should be laid out like
the *arr apps: *"More important to be familiar than to have our own thing."*

**What changed:**
- `information-architecture.md` § Direction is amended, and states what the old
  norm (three destinations, organised around what a curator does) gave up.
  § The *arr layout (new) places each page by its Radarr precedent, and records
  Sonarr's two-scope search from its source.
- `project-preferences.md`'s enforcement row and `design-direction.md`'s token
  norm note the amendment.
- `re-architecture.md` § Open questions gains external identity (Wikidata, ULAN)
  before Watches: use registries, never become one.
- `build-plan-arr-navigation.md` plans the build in five chunks.
- **The sidebar (Chunk 02).** The three tabs became Sonarr's sidebar. Artworks
  (was Collection) is home, with Add New (was Discover) and Themes beneath it,
  followed by Walls, Settings › Taste, and System › Status (was Health). System
  shows a problem-count badge whose words are the link's name. The top-bar
  indicator stays beside it, because a badge is a number and a state needs a
  word. Below 40rem the sidebar is a drawer behind a Menu button. Fragments keep
  their spellings (`#collection`, `#discover`, `#health`), so no bookmark or
  agent link breaks.
- **One theme (`#theme/<id>`) returns to Themes by default**, since Themes is a
  sidebar page. Opened from Artworks or a wall, it records `?from=` and returns
  there, as other contextual screens do.
- **The skip link had sent keyboard users to the home page.** The hash router
  read `#view` as an address. It now moves focus instead, with a test that
  fails without the fix.
- **Activity › Queue and History (Chunk 03).** The run list left Add New. Queue
  holds the searches that have not ended and History the ones that have, split
  on the server's `is_terminal` flag. A run and its review now return to Queue
  by default. They share it because each opens the other, and separate defaults
  put an opener in the address on every hop between them. `/queue` and `/history` are served as reloadable paths.
  A finished run with unjudged candidates belongs in Queue as Radarr's "manual
  import" does, but the listing has no signal for it. That gap is recorded in
  `information-architecture.md` and not built here.
- **Search in two scopes (Chunk 04).** The top-bar search is Sonarr's: typing
  shows *In your library* matches and a *Search museums for "…"* row, which
  hands the words to Add New without starting a run (runs cost money). Enter
  with nothing highlighted opens Artworks filtered to the query, as the owner
  ruled. Review cards for a work the library already holds say *Already in your
  library*, with opening that artwork as the first control and a quieter
  *Accept anyway* for works that only share a title and artist. A run could always
  re-propose an accepted work, which would have acquired a duplicate.
  `held_artwork_id` is new, additive, on the HTTP card and both `art_review`
  shapes.
- **The page toolbar (Chunk 05).** Artworks gets the *arr toolbar: the
  selection's actions on the left, and View (Posters, Overview, Table), Sort
  (Title, Artist, Recently added) and Filter on the right. Filter shows and
  hides the facet and theme rails, which stay beside the grid as the owner
  ruled. Sort is new on the server: `GET /api/works?sort=`, a `WorkOrder` that
  orders the page and never moves the total or the facet counts. View, Sort and
  Filter are all in the address and survive a reload, and "Show everything"
  keeps them.
- **The cumulative review's fixes.** The search dropdown had taken the
  `.suggestions` class a conversation turn already used, so on a thread with
  several suggesting turns every block stacked in one place. It is now
  `.search-suggestions`, with a two-turn test that failed first. `art_catalogue
  list` takes `sort` as the browser does, and a bad value is refused under the
  name the caller sent. Hidden rails that still narrow the works say so. A Work
  opened from a review returns to that review, which the IA had always required.
  A failed library lookup in the dropdown says so rather than looking like no
  matches. A stale `?sort=` falls back to the default, and after "Accept anyway"
  the original card no longer points at the duplicate.
- `test_the_three_destinations.py` became `test_the_sidebar.py`. Its docstring
  records which tests were kept, which rewritten to the amended norm, and which
  retired: *no entry names a pipeline stage* and *the navigation is flat*, both
  of which the ruling deliberately gave up. Six re-breaks (skip link, badge,
  pages shown under every section, Escape, a second `aria-current`, the home
  page) each turned their tests red.

## 2026-09-30: The Library/Programming seam, and the Player pulls over HTTP (wave 2b)

<!-- prawduct: scope=wave-2b-seams-and-http | release=v0.1.0 -->

**Why:** wave 2 of `re-architecture.md`. Programming has to stop reaching into
the Library before the store can be split (wave 3). And the Player needs a
transport that does not depend on sharing a filesystem with the server.

**What changed:**
- Library code now lives under `curatarr/library/` and Programming code under
  `curatarr/programming/`. Programming reads the Library only through
  `library/facade.py`. `tests/preferences/test_seam_imports.py` holds that
  boundary (seam rules 1 and 2).
- The Library announces `work.accepted`, `work.archived`,
  `work.image_changed` and `work.mat_changed` after each commit. Programming
  subscribes to them, and at startup reconciles every published manifest
  against the Library. `archive_artwork` no longer writes Programming's tables
  (rule 4).
- Curatarr serves `GET /walls/{id}/manifest` (with ETag/304),
  `GET /media/sha256-{hex}` and `POST /walls/{id}/heartbeat`. Each is behind a
  per-wall token, issued from the Walls screen or through MCP. Manifest minor 2
  adds `media` to each entry.
- Arrt can run with `MANIFEST_SOURCE=http`. It pulls into `CACHE_DIR` and
  renders only from that cache, so it keeps showing its last good wall while
  the server is down. File mode is still the default. Only `arrt/pull.py`
  speaks HTTP, and `aiohttp` is now a declared dependency of Arrt (it was
  already locked, through `samsungtvws`). In HTTP mode the heartbeat file moves
  into `CACHE_DIR` and the pull forwards it.
- The facade adds a new reason a work is left off a wall: `not_in_catalogue`.
  It cannot happen while the foreign keys hold, and exists for when rule 3
  drops them.
- Several of wave 1's review items were carried here: R-1, R-2, R-5/R-9, R-6
  and R-10.

**The catalogue file changes, additively:** `walls` gains `token_verifier` and
`token_issued_at`, `renditions` gains `content_sha256` and `byte_size`, and
there is a new index, `renditions_by_content`. All four columns are nullable.
The store adds them to an existing file the first time it opens it (the
`ALTER TABLE ADD COLUMN` path in `persistence/durable.py`), and logs each
addition. Rolling back to wave 2a's code on a widened file has not been
tried, so the way back is the copy of the file taken before the upgrade.

**Fixed along the way:** `next` and `show_now` did not write the directive into
the manifest, so neither reached the wall until the next sync. Backlog #35:
a failed manifest write in `activate_theme` now undoes the hang.

**Operator verification queued:** the HTTP soak on the Pi, the token panel,
the Next fix, and the archive removal. (Reinstalling the Pi's units is also on
the queue, but from wave 2a.)

## 2026-09-30: Curatarr and Arrt, in the code (wave 2a)

<!-- prawduct: scope=wave-2a-rename | release=v0.1.0 -->

**Why:** the products have names, and wave 2b is about to move modules across new
packages. Renaming first means no file is touched twice.

**What changed:** `curation/` and the `curation` package are now `curatarr`;
`display/` and the `display` package are now `arrt`. The operator named the
player Arrt on 2026-09-30, the same day, replacing Displayarr, and the direction
artifacts, the contract schemas' descriptions and the READMEs now say so. The
dated quotes that gave the first names are kept as they were said. Imports,
module paths inside strings, `python -m`, the units' `WorkingDirectory`, CI job
ids, `test_commands`, the root tool excludes and the learnings' path scopes all
follow. The MCP server now advertises itself as `curatarr`, and the acquisition
User-Agent names the curatarr repository. Logger names follow the packages, so
journal lines are prefixed `curatarr.` and `arrt.` rather than `curation.` and
`display.`; nothing in the repo filters on them. Otherwise no behaviour changes,
and both lockfiles resolve the same package versions as before.

**What deliberately did not change:** the unit files' names and their
`SyslogIdentifier`s (until wave 3), the Pi's checkout path, the environment
variables' names (`CURATION_PORT` and the rest are the operator's configuration),
the "curation plane" / "display plane" role names in prose, and the 2024 root
module `display.py`, which `tvart.py` still imports.

**Carried in:** `CLAUDE.md`'s browser and live-suite sections moved to
`docs/testing.md` with a pointer left behind (wave 1 review R-4), and its "Next
up" now points at `re-architecture.md` § Order of work instead of naming a wave
(O-3). `test_tool_config.py` now pins that the real `display.py` stays under the
root tools, because the name collision that motivated its trailing-slash guard
no longer exists by name. `tests/test_repo_hygiene.py` now scans `arrt/tests`
as well, which widens that guard rather than only renaming its paths. And
`re-architecture.md`'s wave 5 command for splitting the player into its own repo
now filters on both `display/` and `arrt/`, because filter-repo does not follow
renames and filtering on `arrt/` alone would drop the player's history from
before this rename.

## 2026-09-30: The learnings compacted into one-line rules

<!-- prawduct: scope=learnings-compact | release=v0.1.0 -->

**Why:** `core.md` had grown to 78KB of narrative against a 12KB cap and was
frozen until compacted. It is now 9.3KB of one-line rules, with `display.md`,
`surface.md` and `acquisition.md` scoped to their planes by path.

**What moved:** the narrative sections that were project facts rather than rules
(platform and dependencies, the two-plane split, the 3tears tiers, the `ART_ROOT`
data contract, the `all.json` defects) now live only in the artifacts that
already carried them. Every pointer into the retired sections is retargeted
there, and the one fact no artifact held (the three inconsistent `raw/` filename
conventions) was added to `product-brief.md` § Out of scope.

**Corrected on the way:** the claim that the display plane needs an HTTP client
and PIL survived in `product-brief.md`, `3tears-integration-findings.md` and
`project-state.yaml` after 2026-08-06 made it false. Each now says what it needs
today and points at `architecture.md` § Direction for wave 2's change to the
plane-isolation rule.

## 2026-09-30: The Player contract (wave 1)

<!-- prawduct: scope=wave-1-contract | release=v0.1.0 -->

**Why:** Wave 2 builds both ends of the HTTP channel between Curatarr and
Displayarr. The contract between them has to exist first, and be tested against
the code that already writes and reads it, so neither side is built against a
guess.

**What:**
- `player-contract.md` is the contract's home. JSON Schemas (Draft 2020-12) and
  indexed fixtures live under `contract/`.
- **Major 1** describes the manifest and heartbeat as written today, plus wave
  2's additive changes: a content-addressed `media` reference per entry, a
  `schema` key on the heartbeat, the routes, the per-wall bearer token, status
  codes, and an error model that always keeps the cache.
- **Tests on three sides:**
  - The root suite checks that fixtures and schemas agree. Every invalid fixture
    breaks exactly one rule, the one its filename names.
  - Curation validates manifests its real builder writes, and runs its heartbeat
    reader over the fixtures.
  - Display runs its manifest reader over the fixtures, including refusing
    major 2 as an unsupported version, and validates the heartbeat it writes.
- Eight deliberate breakages, four per plane, were each caught by the new tests.
- `jsonschema` is declared in all three `dev` groups, rather than inherited
  indirectly in one of them.
- Each `date-time` is backed by a pattern, because the common validator skips
  `format` unless an optional package is installed. The dry run proved it: a
  timestamp without an offset passed on `format` alone.
- **Major 2, as a draft:**
  - A works map carrying presentation masters, mat colours and labels.
  - A time-anchored schedule whose gaps are dark hours. When the horizon runs
    out, the Player replays it by whole days, so a wall cut off from the server
    keeps its household's hours.
  - Scenes with lifetimes, a staging list, and wall settings.
  - Capabilities as heartbeat minor 2.
  - Five rules no schema can state (references resolve, slots are ordered and
    inside a whole-day horizon, scenes run forward) have a reference validator
    in the root test and one invalid fixture each.
  - Display pins the cutover: every major 2 shape is refused as an unsupported
    version.
- A mutation sweep found a real gap: no fixture proved major 2's reused label is
  enforced. That fixture is added.
- `show_now` and `next` become schedule republishes in major 2. The
  re-architecture and data model no longer say a scene replaces them.
- **Wave 2 is planned as two plans:**
  - `build-plan-wave-2a-rename.md`: the package rename, one cleanup chunk, first.
  - `build-plan-wave-2b-seams-and-http.md`: the Library/Programming split, events
    with startup reconciliation, the HTTP surface with wall tokens, and
    Displayarr's cache-first pull.
  - The one HIGH-impact assumption, whether a readiness-removing Library change
    republishes walls, is put to the operator.
- `deploy/README.md` no longer says the Player pulls over HTTP from wave 2. In
  wave 2 the pull is switched on by configuration while the file channel keeps
  working; it becomes the only mode in wave 3.
- `project-state.yaml` sets `base_branch: develop`. The re-architecture
  integrates on `develop` and releases to `main`, and the remote's default is
  still `main`, so without it every PR gate measured from `main`.
- **The cumulative review found 2 blocking findings, both fixed:**
  - The root test imported `referencing` without declaring it.
  - The rename plan's proof grep matched nothing on this Mac even before a
    rename. It now uses a code-only `-P` pattern, with counts recorded before
    the rename.
- **Also fixed from the review:**
  - Days in the schedule are 24 absolute hours, with a fixture across a clock
    change and the replay cost stated.
  - Media `url` is a resolvable reference; the hash is the identity.
  - Stale wave 1 promises are corrected in five places.
  - `CLAUDE.md` is trimmed, and warns that a plain `uv sync` drops the optional
    groups.
  - A black failure committed in Chunk 02 is fixed.
- The rest is accepted on the record. The verification review found 0 blocking.

## 2026-09-30: Curatarr and Displayarr; a token per wall; wave 0 closed

<!-- prawduct: scope=re-architecture | release=v0.1.0 -->

**Why:** The operator made three rulings: "wave 0 -- abandon. We'll rebuild with
this new plan"; "each wall gets a token"; and "The library/performance
controller will be Curatarr, the device side playback will be Displayarr."

**What:** Documentation only.
- The names are recorded in `re-architecture.md`, the product brief's Identity,
  `project-state.yaml`, `CLAUDE.md` and the README. The GitHub repo and the
  Python packages are not renamed yet.
- Per-wall tokens are recorded in `re-architecture.md` § Seam 2, with a
  decision block, in `security-model.md` (option b chosen) and in
  `api-contract.md` (`401` and `403`). The token is checked on every wall route
  and on media, which is the advisor's extension and vetoable. It lands in
  wave 2.
- Wave 0 is closed. The v1 open chunks are abandoned, and a table maps the
  requirement each served to where it is rebuilt: power control becomes a
  Displayarr stream in wave 6+, the dark hours go to the wave 4 schedule, backup
  goes to wave 3, and retiring the legacy modules goes to wave 5. The power
  norm's status and interim rule now point there.
- Three open questions are closed.

## 2026-09-30: Wave 1 begins: what is showing versus how, the schedule, scenes, and the waves re-cut

<!-- prawduct: scope=re-architecture | release=v0.1.0 -->

**Why:** A review of the morning's re-architecture found internal contradictions
in the forward notes and four structural gaps. Separately, the operator framed
the server's responsibilities: the server should manage media without knowing
walls, yet walls must be coordinated without configuring each Player. This
entry writes the resulting model and the approved review points into the
artifacts.

**What:** Documentation only. No code changed.
- `re-architecture.md` gains § What is showing, and how it is shown:
  - Walls exist only in Programming, as logical targets. Settings flow down and
    capabilities flow up.
  - From schema major 2 the manifest is a time-anchored schedule, with scenes as
    a live override that expires back to it, and a staging hint.
  - The resolution floor becomes a Library quality profile.
  - These are recorded as vetoable decisions, each naming its author.
- Seam rules 1, 2 and 4 move from wave 6 to wave 2, and rule 3 (the store split)
  to the start of wave 3. Rule 4 gains a reconciliation duty at startup. Facet
  population joins wave 6+, ahead of smart playlists. Major 2 carries every
  breaking change at once.
- The contradictions are reconciled across 12 other files: the floor options,
  who judges adequacy, the wave for label mode, mat settings and the
  presentation master, and when the system becomes distributed. The heartbeat
  auth deadline moves to before wave 2.
- Missing notes are added: two norm-index rows and two findings files. The open
  questions are re-sorted in `project-state.yaml`, with two settled, and two
  technical decisions are added.
- Two home-directory paths that exposed a username are removed from the public
  artifacts.

## 2026-09-30: Direction change — a Library/Programming server and a Player, documented before any code

<!-- prawduct: scope=re-architecture | release=v0.1.0 -->

**Why:** The operator decided to split the product into an *arr-style server,
holding the Library (procure, maintain, upgrade, enhance) and Programming (walls,
playlists), and a Plex-style Player that renders to any screen, with the e-ink
label optional and a caption in the mat as the alternative. The decision was made
in the operator's homelab workspace. This entry brings that conversation into
the repo so the next session starts from it rather than from the old target.

**What:** Documentation only. No code changed.
- **New:** `artifacts/re-architecture.md`. It holds the owner's rulings in their
  words, the three roles, both seams, the two tag layers, Watches, Player
  outputs, the deployment target, waves 0–6 and the open questions.
- **Amended, with recorded decisions:**
  - `architecture.md` § Direction: the manifest channel is amended and
    `in-transition`; two rulings; four seam norms born `in-transition`; Decision
    Log entries reversing the 2026-07-20 co-location.
  - `nonfunctional-requirements.md`: the display-independence norm.
  - `accessibility-spec.md`: the legibility norm now covers any label surface;
    § The television admits a caption in the mat.
  - `data-model.md`: two rulings, the reversal of the `tv_display` rendition, a
    role for every entity, and § Planned entities.
  - `product-brief.md`: Vision, Identity, flows and scope.
  - `project-state.yaml`: the `multi_process_distributed` flip recorded, a
    technical decision, an open question, and the artifact manifest.
  - `project-preferences.md`: norm index rows.
- **Forward notes** (as-built text left intact): every other artifact whose
  target-state claims change, plus `README.md`, `CLAUDE.md` and
  `deploy/README.md`.
- **Parked, not archived:** the round-2 UI plan, on local branch
  `curation-ui/rulings-and-plan`. This work is on `develop`, branched from `main`.
