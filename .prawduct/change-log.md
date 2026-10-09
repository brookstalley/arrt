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
>
> **Names, 2026-10-08.** Postarr is now **Arrt Player**: `postarr/` became
> `arrt-player/` and the `postarr` package `arrt_player`
> (`build-plan-rename-arrt-player.md`). Entries before this date keep `postarr`.


<!-- Older entries live in .prawduct/change-log-archive/YYYY-MM.md, moved there verbatim by `prawduct-hook archive-change-log`. -->

## 2026-10-09: Wave 4d — compositing moves to the Player

<!-- prawduct: scope=wave-4d-compositing -->

**Why:** The fourth of wave 4's seven plans (`build-plan-wave-4d-compositing.md`).
A major 2 work arrives as an unmatted presentation master, and until now
nothing on the Player could draw its mat, so the Player read major 2 but never
asked for it. This plan gives it a compositor and the Frame's geometry, then
asks for major 2 first. The owner ruled the same day that until the repository
split two sessions may run, one per plane (`re-architecture.md` § Agents).

**What:**
- **The compositor** (`arrt-player/src/arrt_player/compose.py`): the
  contract's layout, held exactly to every `contract/vectors/mat-geometry.json`
  vector, then the work drawn at that rectangle in a work-shaped mat (or
  `full`, or `none`) on black, never enlarged. A work whose mat colour cannot be
  read is drawn as `none`. A composed file is named by a key over everything
  that moves a pixel.
- **The Player's geometry** (`config.py`): the Player reads `TV_PANEL_*` for
  the Frame and `MAT_*` for every wall, under the server's names, and names
  them in its startup line. **`test_config.py`'s guard "the plane holds no fact
  about the television's size" is replaced by its opposite**, because
  `feeds-and-players.md` ruling 7 moved that fact here.
- **The wall composes** (`programmes/schedule.py`): each work the feed names
  is composed in a thread, one at a time, the slot's work first, and a work
  not composed yet is passed over for the pass. A master that will not decode
  costs its work; a failed write is retried after five minutes. A tidy removes
  compositions no work needs, and keeps the picture on the wall until another
  replaces it. A switch of major calls `Programme.entered()`, so the programme
  switched to puts its own picture up. **The rotation now takes the wall on
  the switching pass**, not at its next interval (an inference, put to the
  owner).
- **Asking for major 2:** `REQUESTED_MAJORS` is `(2, 1)`, and the Frame writes
  `capabilities` with its configured panel. A wall served a lower major asks
  for the higher one about once a minute, not every poll, and at once if the
  major it was served stops answering. **Tests whose assertions changed by
  design:** the major 2 tests now assert that the composition reaches the
  display; the Frame's heartbeat test now asserts its screen and `[2, 1]`; the
  pull's `two_major_pull` fixture no longer patches the constant.
- **The contract:** `player-contract.md` § The cutover no longer names a
  Frame as a display that cannot say its size, and says how often this Player
  asks for a higher major.

**Deploying it:** set the Frame's real `TV_PANEL_*` (and `MAT_*`, if they
differ from the defaults) in the Pi's `.env` before restarting.
`.env.example` says which plane reads which key. No server change is needed:
Arrt answers `v2` with 404 until 4e, and the walls run major 1 as before.
Rolling back is checkout and restart; the `composed/` directory under each
wall can be deleted at any time.

## 2026-10-09: Wave 4c — one wall loop, a driver per display, a reader for majors 1 and 2

<!-- prawduct: scope=wave-4c-wall-loop -->

**Why:** The third of wave 4's seven plans (`build-plan-wave-4c-wall-loop.md`).
The Pi Player ran two wall loops, the Frame's and an HDMI screen's, each
adopting, rotating, acting on directives and beating, and already drifting
apart. `feeds-and-players.md` asks for one wall loop and a driver per display
before the repository split, and major 2 is the reason to do it now: its reader
is written once, not once per loop.

**What:**
- **One loop** (`arrt-player/src/arrt_player/wall.py`): a programme says what
  should be on the wall, a display driver puts it there, and the loop beats.
  `displays/frame.py` keeps every behaviour of the Frame's loop (uploads spread
  across passes, the art-mode gate, reconciliation, brightness, the set's
  announcements, closing the art channel on every way out); `displays/screen.py`
  draws over kernel mode setting as before. `daemon.py` and `screen.py` are gone.
- **Major 1's rotation and directive** moved into `programmes/rotation.py`, to
  be deleted whole in 4g. Where the two loops disagreed and only the Frame's
  tests pinned a version, the screen takes the Frame's: an empty screen retries
  as soon as a new manifest lands, and a directive that shows nothing does not
  restamp the timer.
- **The major 2 reader**: `manifest.py` reads a feed, refusing it for the
  shape a Player reads, an instant without an offset, and the five rules a
  schema cannot state, never for a presentation setting. `programmes/schedule.py`
  shows the active scene, else the slot after replay by whole horizons, else
  keeps the last work through a gap; it asks the display's wait and then
  whether the wall is ours before it shows anything. Every vector in
  `contract/vectors/schedule.json` runs in the Player's suite.
- **The pull** caches a feed whole with every work's media, staged works
  included, and asks for the manifest at `/walls/{wall_id}/manifest/v{major}`,
  highest first, falling back on 404. **It asks only for major 1 until 4d**
  (`REQUESTED_MAJORS`), because a major 2 work needs a mat drawn around it.
- **The heartbeat** carries `scene_id`, and `capabilities` (screen, backend,
  label modes, the majors asked for) for a display that knows its screen's
  size: an HDMI screen now, the Frame once its geometry moves to the Player.
- **The contract:** `contract/fixtures/index.json` marks which invalid major 2
  documents a Player must refuse. `player-contract.md` § The cutover is
  amended for a reader of two majors, and gains a rule **the server must
  honour when it retires a major (4e/4g): a heartbeat with no `capabilities`
  counts as `manifest_majors: [1]`**, because a Frame wall writes none until
  the Player owns its geometry. § Transport notes that the Player asks for
  `v{major}`.

**Deploying it:** no server change, and nothing to migrate. The Player now
requests `…/manifest/v1`, which Arrt has served since wave 4a, so the server
must be at 4a or later before a Player from this branch is started. Rolling
back is checkout and restart: the Player's store is unchanged.

## 2026-10-08: Wave 4b — the quality profile, and the presentation master

<!-- prawduct: scope=wave-4b-master-quality -->

**Why:** The second of wave 4's seven plans (`build-plan-wave-4b-master-quality.md`).
The Library judged every scan against an artwork box worked out from one
television's `TV_PANEL_*` and `MAT_*` settings, with a floor in inches. Wave 4
takes screens out of the server, so the Library now judges against a quality
profile that names no device: a minimum in pixels on the long edge. The owner
ruled the two open behaviours on 2026-10-08: two badge states (none when a scan
meets the minimum, "below minimum" when it does not), and the minimum as an
environment setting with no Settings screen.

**What:**
- `QUALITY_MINIMUM_PX` (default 1,000, the owner's figure of 2026-10-06)
  replaces `RESOLUTION_FLOOR_INCHES`. **`RESOLUTION_FLOOR_INCHES` is retired**: a
  deployment still setting it starts normally and logs a WARNING naming it and
  its replacement (`config.retired_setting`).
- `library/services/quality.py` replaces `display_fit.py`: a `QualityProfile`
  and a two-value verdict, `meets_minimum` or `below_minimum`, judged on the
  long edge. Selection, discovery, the collection supplement, phase two, the
  review card, the survey, the registry work page and the *Size* facet all take
  the profile; no Library service receives an `ArtworkBox`, which now lives in
  `compose.py` with width and height only, until 4g.
- Phase two ranks meets-the-minimum above below-it, and within a band by the
  long edge, level past the presentation master's 7,680 px cap.
- **Breaking for MCP clients, announced in the tool tips:** `display_fit` and
  `regenerate`'s `fit` take the new values; `renders_at_inches`,
  `renders_at_pixels` and `rendered_long_edge_inches` are retired; a look
  picture's `below_floor` is `below_minimum`; a listing row gains `size_px`.
  On HTTP, `FitOut` is `{verdict}` alone, the `fit` filter takes the new bands
  and refuses a retired one by name, and a look picture's `below_floor` is
  `below_minimum`. The stored `unresolved_reason` value `below_floor` keeps its
  spelling.
- The browser: no badge for a scan that meets the minimum, anywhere; "below
  minimum" for one that does not; the facet is *Size*, with *Meets minimum*,
  *Below minimum* and *No size known*. The unused `caution` glyph is gone.
- `regenerate` still warns when a work goes on the wall below the minimum.
- Records: the cutoff is struck wherever it was still promised (`data-model.md`,
  `nonfunctional-requirements.md`, `re-architecture.md`,
  `information-architecture.md`, `procurement-corpus.md`, `project-state.yaml`),
  and the API contract, operational spec, observability strategy and
  `.env.example` describe the new setting.

- **The presentation master** (Chunk 02): one device-independent image per held
  work, the Original upright and unmatted, at most 7,680 px on its long edge,
  JPEG at quality 95, as `presentation/{artwork_id}.jpg`, recorded as a
  `presentation_master` Rendition. `prepare()` makes it current before it looks
  at the canvas, so every acquisition, regenerate and mat change leaves one, and a
  mat change never rewrites it. Each master records the rule it was made by
  (cap and quality), so a changed rule makes every master owed again. At
  startup every accepted work with no master recorded from its Original by
  today's rule is queued prepare-only (`preparation.masters_queued`),
  so the first start after the upgrade makes one for each held work, without
  refetching or redrawing. `GET /media/{hash}` serves it as it serves any
  rendition; no manifest names it until 4e. Measured over the 46 local
  originals: about 4.9 MB a master, 37% of the originals' bytes.
- **Rollback is not checkout and restart.** The first start records a
  `presentation_master` Rendition for every held work, and the release before
  this one cannot read that kind (`RenditionKind(row["kind"])` raises), so it
  starts and then fails on every work's renditions. To roll back, restore
  `catalogue.sqlite` from the pre-deploy backup, or delete the
  `presentation_master` rows and the `presentation/` directory first; and put
  `RESOLUTION_FLOOR_INCHES` back in `.env`, or the old code falls to its 12"
  default. On the first start, expect `preparation.masters_queued` to name
  every held work and `presentation/` to grow by about 5 MB a work.

**Surfaced:** navigart serves at most 1,000 px, and its test expected that to
fall below the floor, which held only against the 42" reference default (about
1,260 px). On the owner's 50" deployment (11.34") the floor already cut at
exactly 1,000 px, and the owner's minimum is inclusive, so nothing changes on
the wall.

## 2026-10-08: Wave 4a — the major 2 contract settled

<!-- prawduct: scope=wave-4a-contract -->

**Why:** The first of wave 4's seven plans (`re-architecture.md` § Order of
work, row 4). The Player's reader (4c), its compositor (4d) and the server's
builder (4e) all build against major 2, and a Player must read the final shape
before the server switches, so the shape is fixed first. The owner ruled the
open values the same day: a three-day horizon, a twenty-minute preview default,
and a relative mat of 6% of the shorter side; and the program itself, with
scenes after the cutover and one household-wide rule (no work on two walls at
once).

**What:**
- `manifest.v2`: a feed. `settings` is the first of three presentation layers,
  itself optional, and every key in it optional: label mode (`none`, `caption`, `overlay`), mat mode
  (`none`, `proportional`, `full`), overlay lead and tail, fades, text scale,
  viewing distance, and which label facts show. The mat width leaves the
  document (`feeds-and-players.md` ruling 7), and with it the
  `mat-bottom-weight-below-one` fixture, whose rule no longer exists. `scene`
  and `staging` are optional, so a document without them is a channel's feed.
  `label-mode-unknown` now carries `panel`, which major 2 no longer has. A root
  test holds `facts` to the label's keys.
- `heartbeat.v1` `capabilities.label_modes` are `none`, `caption` and
  `overlay`; `panel` leaves, because a label on its own surface is a label
  output. No Player writes the field yet, so nothing is stranded.
  `capabilities.screen` is reported again whenever it changes, and Programming
  judges adequacy from the largest size reported recently.
- `routes.json` names `manifest_major`, `/walls/{wall_id}/manifest/v{major}`.
  The server answers `v1` with the unversioned route's document and `404` for
  any other spelling, `01` included. `player-contract.md` § The cutover follows
  ruling 4: each major is served while a heartbeat lists it, and a Player steps
  down a major on `404`.
- Conformance vectors: `contract/vectors/mat-geometry.json` and
  `schedule.json`, with reference statements in the root suite, and the
  server's compositor held to the `proportional` vectors that have a density.
  `player-contract.md` gains § Layout, and § Time says spans are half-open and
  an instant before the horizon is moved into it as one after it is.

**Tests:** all three suites green. Each new rule was watched failing once: the
new invalid fixtures against a schema re-widened to admit them, the `facts`
guard against a trimmed enum, the per-major route against a lenient integer
parse (`01`), each reference rule against a mutated copy (closed spans, an
enlarging scale, no replay), and the server's vectors against a shifted vector
and a compositor that centres the work on the screen.

## 2026-10-08: Postarr becomes Arrt Player

<!-- prawduct: scope=rename-arrt-player -->

**Why:** The owner, 2026-10-08 (#311): the playback side "is just a player like
plex or jellyfin and not really a *arr app". "Poster" was the first choice and
was dropped the same day: it is taken on PyPI, and in this repo it already means
Lidarr's poster cards and a poster as a kind of object. The owner chose the
Plex and Jellyfin convention instead, where a client carries its server's name.
It lands before wave 4, which adds most of the Player's new modules.

**What:**
- `postarr/` → `arrt-player/`, package `postarr` → `arrt_player`, distribution
  `arrt-player`, run with `python -m arrt_player`. Every import, the lockfile's
  own entry, the CI job, root excludes, the root guards' paths, learnings
  globs, `display.service`, and the prose of live artifacts. The hypothesis
  profile is renamed with it.
- `deploy/README.md` § The Player renamed Arrt Player: the Pi's steps and the
  way back. The queue entry at the top of `operator-verification.md` points
  there, and says the older entries keep their day's paths.
- `re-architecture.md`: the naming paragraph gains 2026-10-08. Wave 5's
  history now spans four paths, so pass 2 adds `postarr/` and `arrt-player/`.
  Pass 1 is unchanged, because its `b"arrt/"` prefix does not match
  `arrt-player/`. The new repository is `arrt-player`.
- One behaviour change, from the boundary review: the Player refuses to start on
  a relative `CACHE_DIR` or `TV_TOKEN_FILE` (a leading `~` is expanded first).
  The Pi's rename steps delete the old checkout directory, and a relative cache
  resolved inside it would have taken the store and the TV pairing with it.
  `.env.example` says both must be absolute.

**Left as written:** archived plans, `change-log-archive/`, earlier entries
here, the dated `operator-verification.md` entries, the live plans whose chunks
are all ticked, and the 2026-10-05 norm-sweep measurements in
`project-state.yaml`. All of them record their day.

**Tests:** all three suites pass, with lint and format. `git grep -niP postarr`
outside those history files leaves only the lines recording the names. All 71
tracked files under `postarr/` are renamed into `arrt-player/`, with nothing
added or deleted. `test_plane_isolation.py` failed on a planted `import
arrt.config` in `arrt_player/config.py`, naming it as the curation plane, and
passed once it was removed. The new names share the server's `arrt` prefix,
so the search for unanchored prefixes was run over the renamed tree. It found
one, `record.name.startswith("arrt")` in the curation suite's
`test_player_surface.py`. It is left: that filter reads only the server's own
process, where `arrt_player` is not installed, and matching more would only
make the assertion stricter.

## 2026-10-08: Get and review clarity: the boundary review's findings

<!-- prawduct: scope=get-and-review-clarity -->

**Why:** The cumulative review of the plan (`rev-20261009T000127Z-d99ef2f2`).

**What:**
- An offered work records which source offered it (`offered_by`, a new
  nullable column, widened into older files), and a Get's page names the
  museum from that. It had read the museum off the work's current scan, which
  names the wrong museum once the offered scan is turned down and another
  museum's found. An offer recorded before the column sits under "the
  collection". The HTTP work and the MCP row carry it;
  `data-model.md` and `api-contract.md` say so.
- `COST_UNKNOWN` is said in one place; Ask logs why an estimate could not be
  read; two comments in `run.js` say what the code does, not what it
  replaced; the server's docstrings call Queue's control a cause's Retry; the
  IA's per-screen table describes Ask and a Get's page as they are now.

**Tests:** `test_an_offered_work_stays_under_the_museum_that_offered_it_when_its_picture_changes`
and `test_an_offered_work_recorded_before_its_museum_was_kept_says_the_collection`
failed first; `test_an_offered_work_carries_which_query_produced_it_and_how_many_it_matched`
asserts `offered_by`, and the proposed-work test asserts it null.
`test_an_offered_work_arrives_saying_which_query_and_which_museum_offered_it`
asserts the offer's facts through `/api/runs/{id}`, the route the page reads,
and failed with `offered_by` dropped from the route. A commit-card
assertion that could not fail (`"Get" in card`) is deleted; the caption test
holds what it meant to.

## 2026-10-08: Get and review clarity, chunk 04: Queue's Retry, and the walk

<!-- prawduct: scope=get-and-review-clarity -->

**Why:** "Retry all" on one failure group read as retrying every failure on
the page (`build-plan-get-and-review-clarity.md` chunk 04).

**What:**
- A failure group's button says how many it retries: *Retry 3*, or *Retry*
  for a group of one. Its spoken name is "Retry the 3 works that failed:
  <cause>". The line above the groups says each group's Retry puts its works
  back in line. `information-architecture.md` and `api-contract.md` say so.
- The walk was re-run on the synthetic corpus (`.ux-walk/clarity-synthetic`):
  84 captures, 21 screens, no accessibility violations, console errors or
  dead ends. The corpus holds no Gets, so a Get's page and Review were seen
  from stubbed pages only. The owner's look at the whole plan is queued in
  `operator-verification.md`.

**Tests:** the two Queue tests that pressed *Retry all* now assert the label,
*Retry* for one and *Retry 4* for four, and press it by that label. Both
failed before the change.

## 2026-10-08: Get and review clarity, chunk 03: Review

<!-- prawduct: scope=get-and-review-clarity -->

**Why:** The owner walked Review and found the cards to judge mixed in with
cards that had no picture and cards already decided
(`build-plan-get-and-review-clarity.md` chunk 03, owner's rulings of
2026-10-08).

**What:**
- Review's cards still to judge come first, in the server's order. After them
  one line, *N found no image*, folds the cards whose Get found none; it only
  opens, onto the same cards with their *Want* and *Forget*. Last, one line,
  *N decided*, folds the accepted and rejected cards. The same on a Get of
  chosen works' page, which draws the same cards.
- Folding happens when the page is drawn: a card decided now stays where the
  curator's hand is until the next visit (the builder's call, so a verdict
  never moves the card out from under the keyboard).
- A page whose every card is folded says "Nothing here is left to judge by
  its picture."
- A Get still looking redraws its page every poll, so each card's place and
  each fold's open state are read back from the section being replaced and
  kept: a card decided there stays put, and an opened fold stays open (the
  review caught both). Only a decision is held back: a card whose search
  ends with nothing while the Get looks still folds (the next review caught
  the first fix holding every card in place).
- `information-architecture.md` § Review records the rule as the owner's, and
  that the server's order already put works with an image first. The plan's
  premise that it put named works first was wrong.

**Tests:** `tests/browser/test_review_folds.py`, six tests, five watched
failing first (the sixth, no fold lines on a page with nothing to fold,
passed before as it must). Eleven tests about a decided or found-none card's
own behaviour now open the folds first (`Ui.open_folds`), as a curator would;
what each asserts about the card is unchanged.
`test_a_card_decided_while_a_get_looks_stays_where_it_was` and
`test_a_fold_opened_while_a_get_looks_stays_open` failed before the
placement was carried across redraws;
`test_a_card_whose_search_ends_with_nothing_folds_while_the_get_looks`
failed against the first fix; the "nothing left to judge" sentence
is tested present and absent.
`test_a_discovery_run_s_page_is_unchanged` no longer asserts that the page
never reads the cards, which chunk 02 changed on purpose (it reads them for
the pictures). It asserts what it was for: a table, and no cards.

## 2026-10-08: Get and review clarity, chunk 02: a Get's page

<!-- prawduct: scope=get-and-review-clarity -->

**Why:** The owner found a finished Get's page hard to read: one paragraph
holding two different counts that are often the same number, and one table
mixing the works asked for with works a museum volunteered, each offered row
repeating a long stored sentence (`build-plan-get-and-review-clarity.md`
chunk 02).

**What:**
- A finished Get from words says "This Get finished." and three counts:
  *Asked for*, *Found with an image*, *Not matched*. The pending clause
  ("could not be looked up at all…") still follows when there is one.
- Its works are listed under *Asked for (N)*, with why the run named each,
  then under *Also offered by <museum> (N)*, one section per museum, with no
  reason column. Every row carries the picture found for it (`rowPicture`),
  8rem wide at every width.
- The page reads every run's review cards for the pictures, not only a Get
  of chosen works'.
- Chunk 01's review observations are fixed here: `design-direction.md` no
  longer says the caption is centred; `captioned` sits above `render`'s doc
  comment rather than inside it; `aboutCost` says "Cost unknown just now"
  for a figure that is not one, and its zero and non-figure branches are
  tested.
- The review caught *Not matched* reading the tally's `unresolved`, which
  counts offered works too: it now counts the unresolved works asked for. A
  row with no picture says which kind of nothing: the cards could not be
  read, the search is still running, or it found none.

**Tests:** `test_a_finished_get_says_three_counts_rather_than_a_paragraph`
(now with an offered work that ended unresolved),
`test_a_row_without_a_picture_says_which_kind_of_nothing`,
`test_offered_works_sit_under_the_museum_that_offered_them_without_a_reason`,
`test_each_row_shows_the_picture_found_for_it` and
`test_a_row_s_picture_stays_small_on_a_phone` were watched failing first.
Four tests pinned the paragraph and now pin what replaced it: the provenance
test asserts the two section headings instead of the words "asked for" and
"offered by the collection"; the count-of-one test asserts the counts; the
singular-verb test keeps its re-search case and drops the discovery one,
which no longer has a verb; the does-not-deny test asserts the museum
heading instead of "the collection offered 1 more work". The run-view
fixtures now stub the cards listing, as a real run has one.

## 2026-10-08: Get and review clarity, chunk 01: Ask

<!-- prawduct: scope=get-and-review-clarity -->

**Why:** The owner walked Wall label and found Ask confusing: three acts of
equal weight, a link to Taste among them, and a cost they could not place
(`build-plan-get-and-review-clarity.md` chunk 01, with the owner's rulings
of 2026-10-08).

**What:**
- Get is Ask's one filled act. Under it, a caption tied to it for a screen
  reader says roughly what it costs, as an order of magnitude: "About $0.01",
  "About $0.10", "About $1" (`aboutCost`, the nearest power of ten, never
  below a cent). It replaces the "Cost: $" mark and the "This Get costs at
  most …" sentence. A conversation's commit card, which starts the same Get,
  says the same under its Get.
- *Talk it through first* is quiet, with "Free to start; each reply shows its
  cost" under it. The plan's ruling said "a conversation is free", but every
  reply is a priced model call, so the caption says what is true (the
  builder's wording).
- Ask no longer links to Taste, which is under Settings.
- Ask opens when the estimate cannot be read, and says "Cost unknown just
  now" under Get. It used to fail the whole page.
- `captioned` (core/render.js) and `.captioned` / `.act-caption` replace the
  `.act-note` line; `askingCost` is gone.
- `information-architecture.md` (Ask, Taste) and `design-direction.md`
  (Cost, the caption) say so.

**Tests:** `test_ask_says_about_what_a_get_costs_under_it` (six bounds),
`test_ask_still_opens_when_the_estimate_cannot_be_read`,
`test_ask_has_one_filled_act`, `test_ask_does_not_link_taste` and
`test_the_commit_card_says_about_what_its_get_costs_under_it` were each
watched failing first. Three tests are replaced because the owner's ruling
replaced what they held: `test_asks_button_shows_its_tier_before_it_is_pressed`
(the tier mark beside Get), `test_discover_offers_the_way_into_taste` (the
Taste link; Taste's own route is still held by
`test_taste_is_a_page_under_settings`), and the commit card's "costs at
most" assertion. The tier mark's look, which the controls test checked on
Ask, moves to `test_a_tier_mark_is_words_on_one_line_not_a_box` on a Get's
Approve, where the mark still is.

## 2026-10-08: A label states dimensions in one system, rounded to whole units

<!-- prawduct: scope=feature-label-units -->

**Why:** the owner asked for imperial or metric on the label, not both, and
whole inches ("not 30 1/8 x 38 1/4 in, just 30 x 38 in"). Rulings: one server
setting, imperial by default; the first measurement only, with its qualifier.

**What:**
- `arrt/src/arrt/library/dimensions.py`: `for_label(dimensions, units)` reads
  the first measurement of a museum's dimensions string and states it in one
  system, half rounding up, preferring the source's own figures in that system;
  a value under one unit keeps a decimal (never below 0.1); a first measurement
  it cannot wholly read comes back unchanged (the cases: `accessibility-spec.md`
  § Dimensions on the label). A bare fraction is one value, and a non-breaking space inside
  a mixed number parses. No model: every string in the
  library follows a pattern a parser reads.
- `LABEL_UNITS` (`config.py`, `.env.example`) reaches `LibraryFacade` through
  `Services.bind`, and `label_of` applies it, so the manifest and the label
  document set the same text. The stored string is unchanged.
- Tests: every distinct dimensions string in the reference library (38),
  checked by hand in both systems; the half-up and source-preference rules and
  the `main` wiring each seen failing when broken.
- `accessibility-spec.md` § Dimensions on the label holds the rule;
  `data-model.md` points at it; `museum-label-findings.md` records the ruling,
  settling #142. The Settings › General control is deferred until the interface
  redesign merges (#329).

## 2026-10-08: Wall label: the boundary review's findings

<!-- prawduct: scope=wall-label -->

**Why:** The cumulative review over the merged branch.

**What:**
- A conversation's commit card says its cost under the Get row, as Ask does,
  priced or not. It had sat above the Direction field.
- The cost mark keeps "Cost:" and its tier on one line (`white-space:
  nowrap`, lost with the `badge` class), and drops the border, background
  and padding resets that no longer overrode anything.
- `held_artists`' docstring says the artist's picture moves when the
  circulating works or their masters change, not in two named cases only.
- Get and review clarity keeps the owner's Ask ruling as given. Chunk 01
  carries what Wall label built instead and puts it back to the owner.

**Tests:** `test_the_commit_card_says_its_cost_under_the_get_it_prices`
(priced and unpriced) failed before the move: there was no sentence under the
row. `test_a_cost_is_words_beside_its_act_not_a_box` gains the `nowrap`
check, which failed on `normal`.

## 2026-10-08: Wall label: the review's touch-size and picture-choice findings

<!-- prawduct: scope=wall-label -->

**Why:** The cumulative review of chunk 06 (`rev-20261008T213736Z-54a26b10`).

**What:**
- The 44px touch rule now reaches the top bar and the sidebar: the search
  field, the magnifier, every sidebar link and the filter options are sized
  from `--control-h` / `--control-h-compact`. `--masthead` is derived from
  `--control-h` instead of copying its value.
- How an artist's picture is chosen (a work with an image first) is now said
  in `api-contract.md`, `information-architecture.md`, `http/models.py`,
  `library/services/artists.py` and `screens/artists.js`. The docstring no
  longer claims the choice never changes.
- The cost mark drops the `badge` class.

**Tests:** `test_a_touch_screen_gets_44px_controls` now measures every
visible control on four kinds of page. Before the fix it failed on the
search field (40px), the magnifier (32px) and every sidebar link (36–39px).
`test_a_status_badge_keeps_its_boundary_on_its_own_ground`, added in chunk 03,
is removed. It checked the state colour on its quiet ground at 3:1, the same
pair `test_every_status_colour_clears_aa_on_its_own_quiet_ground` holds at
4.5:1, so it could never fail on its own.

## 2026-10-08: Wall label, chunk 06: controls

<!-- prawduct: scope=wall-label -->

**Why:** The owner walked the redesign and found buttons "spaced
erratically", "a jumble of button sizes", and a "$" that read as a button
(`build-plan-wall-label.md` chunk 06).

**What:**
- A row of acts sits one step below whatever precedes it (it was `p + .row`
  only), except inside a flex column, whose gap spaces it.
- `--control-h` (2.5rem) and `--control-h-compact` (2rem) size every act,
  field, menu item and the menu button. Both become 2.75rem under
  `@media (pointer: coarse)`. `design-direction.md` had described that rule
  as built for months; it was not in `app.css`.
- A cost tier is words, "Cost: $", with no badge box, and its "Cost:" label
  is visible. On Ask, the cost line moved from a boxed note above the buttons
  to one muted line under them.
- No rule is drawn above a page's name when the name sits inside a section
  (the Artist page).
- Found by the walk: the Artists index pictured an artist by their first
  accepted work even when it had no image, so its thumbnail request was
  answered 400 and the poster read "No picture". `held_artists` now prefers
  the first accepted work holding a master.

**Tests:** New: `test_the_controls.py` (rows spaced on every sidebar page and
on an artist's page; every act at least `--control-h`; 44px controls in a
touch context; the cost mark not boxed),
`test_no_rule_is_drawn_above_a_page_s_name`, and
`test_an_artist_is_pictured_by_a_work_with_an_image_before_one_without`. Each
was watched failing against the code before it. `test_the_conversation.py`'s
`shown_tier` helper now reads `.tier-value`: it read "the tier without the
words only a screen reader hears", and the "Cost:" label is now shown to
everyone. The tier it checks is unchanged.

## 2026-10-08: Wall label, chunk 05: ruled sections everywhere, and the walk

<!-- prawduct: scope=wall-label -->

**Why:** `build-plan-wall-label.md` chunk 05.

**What:**
- `.panel` is a section set off by a `--border-strong` rule above it, with no
  box, ground or radius, on every page. The work page's own overrides shrink to
  what is specific to it. Theme cards and review cards keep their cards.
  `design-direction.md` § Component Patterns gains *Sections*, and *Cards*
  says where a card is still used.
- Fact values that hold a path or URL get a line-break opportunity after each
  slash (`<wbr>`, in `facts()` in `core/badges.js`). CSS does not break after
  "/" before a letter, so on a phone `overflow-wrap: anywhere` broke paths
  wherever the column's edge fell. Removing the panels' side padding moved
  that edge into the middle of a word on Status, and
  `test_the_health_page_s_facts_break_between_words` went red. It had been
  passing only because of where the edge happened to fall.
- The work page's description cap (68ch) never applied, because the
  description is an inline span. It is now a block.
- `arrt/tools/ux_walk.py` walked a copy of the local library: 100 captures,
  no accessibility violations, no console errors.

**Tests:** New: `test_every_section_heading_has_the_one_h2_treatment` (watched
failing with the old h2 size), the description's serif and measure at 959px
(watched failing without the cap: 687px against 673px), and a failed work's
page keeping the layout with its failure in the Master image section.

## 2026-10-08: Wall label, chunk 04: a work's page

<!-- prawduct: scope=wall-label -->

**Why:** `build-plan-wall-label.md` chunk 04.

**What:**
- The picture (the wall preview, as before) and its label sit side by side,
  three to two, and stack below 60rem. The picture stays in view while a long
  label is read. The description stays in the facts list, where a test pins
  it, but takes the label's whole width and is set in the label serif at
  `--text-lg`, at most 68ch.
- The record (What this work is, Master image, Where it can be obtained, What
  has been rendered, Mat colour) is a grid of sections separated by a rule,
  not boxed panels. A section holding a table spans the full width.
- The plan's assumption that the hero would sit on the work's mat colour is
  corrected: the wall preview already carries the mat.

**Tests:** New in `test_the_work_page.py`: side by side at 1280px and stacked
at 800px, the record's sections in order, ruled and not boxed, for a held work
and for one with nothing acquired. Watched failing against the old page, which
has no `.work-head`.

## 2026-10-08: Wall label, chunk 03: the work on a mat, its label beneath

<!-- prawduct: scope=wall-label -->

**Why:** `build-plan-wall-label.md` chunk 03.

**What:**
- A work's tile (Artworks, an artist's works, a topic's) and an artist's
  poster have no card: the picture sits on a `--surface-2` mat with
  `--shadow-art` (a new token in both schemes), and the label sits beneath on
  the page's ground. Selected by the `data-artwork` and `data-artist`
  attributes the tiles already carry. The Artworks skeleton carries
  `.tile-skeleton`, so it takes the same geometry. Theme cards and review
  cards keep their cards.
- The label's text is clamped (two lines of title, one of artist, two of date
  and medium), and the label has a minimum height that fits its longest shape
  and one row of badges. That is what keeps rows uniform. Sizing rows to the
  tallest tile (`grid-auto-rows: 1fr`) was tried first and broke
  `test_the_way_back_link_returns_to_card_20_as_back_does`: the page's length
  changed as later pages arrived, and the restored scroll landed 90px short.
- Facet counts are set in tabular figures. Right-aligning them is descoped,
  with the reason in the plan.

**Tests:** New: `test_the_tiles.py` (uniform rows with a three-line title in
the first row, a two-line clamp, and no box with the picture on the mat).
Watched failing against the old stylesheet: rows of 384 and 322px, four title
lines, a solid border. `test_design_tokens.py` (chunk 02's status work, landed
here): `test_a_status_ground_keeps_its_control_boundary` checked
`--border-strong` on the status grounds, a pair drawn only by the old boxed
status indicator. It is replaced by
`test_a_status_badge_keeps_its_boundary_on_its_own_ground` (the state colour
as a badge's border on its ground, at 3:1) and
`test_every_status_colour_clears_aa_on_the_page_ground` (the status words on
the page). Both were watched failing with `--warn` weakened.

## 2026-10-08: Wall label, chunk 02: the shell

<!-- prawduct: scope=wall-label -->

**Why:** `build-plan-wall-label.md` chunk 02.

**What:**
- The sidebar's edge is painted on `.shell`, which is as tall as the page. As
  a border on the sticky sidebar it stopped one window down on any longer page.
  The sidebar and the top bar now sit on the page's ground. The current page is
  marked with a 2px accent bar, and sub-pages are set at `--text-sm`.
- The search's magnifier, inside the field, is the form's submit button,
  named "Search". On a phone the bar stays on one row as before, the magnifier
  is hidden there as the button was, and the field's text starts at its edge.
- The status indicator is its glyph and words in the state's colour, with no
  box, and is still a link to System › Status. The brand is set at
  `--text-2xl` (`--text-xl` on a phone) and never shrinks.

**Tests:** New: `test_the_shell.py`. The sidebar-edge test reads the pixel at
the sidebar's edge near the bottom of a page longer than the window. It was
watched failing against the old stylesheet, where it read the ground instead
of the border. The search-button test passes on both the old and new shells,
on purpose: it pins the accessible name across the change.

## 2026-10-08: Wall label, chunk 01: Newsreader and Instrument Sans, self-hosted

<!-- prawduct: scope=wall-label -->

**Why:** The owner said the client still looked amateur in its layout, type
and design system. They chose direction A ("Wall label") from a Claude Design
canvas, and ruled that webfonts may be used, reversing design-direction's
"no webfont" (`build-plan-wall-label.md`).

**What:**
- Newsreader (`--font-label`) and Instrument Sans (`--font-ui`) are served
  from `arrt/src/arrt/http/static/fonts/` as variable woff2 files in Latin and
  Latin Extended subsets. Each family's OFL licence is beside its files, and a
  README names the source package and version. The system stacks remain as
  fallbacks. No CDN.
- `--text-3xl` (2.5rem) is a page's `h1` on every page. Section headings
  (`.panel` h2–h4, a wall's title, an offered group) and the confirmation's
  title are now `--text-xl` at weight 500.
- `design-direction.md` § Typography is rewritten as the owner's ruling, with
  the old reasons answered rather than deleted, and § Component Patterns
  "Headings" records the new sizes.

**Tests:** New: `test_the_typefaces.py` reads the browser's record of each
face and requires both Latin upright faces to be `loaded`; also
`test_every_font_the_stylesheet_names_is_served_as_a_font`. Both were watched
failing with `newsreader/latin-normal.woff2` renamed: the face's status was
`error`, and the served-font test got a 404. `test_component_rules.py`'s h1
probe now reads `--text-3xl`. The contract is unchanged: one h1 size on every
page; the size it names is what changed.

## 2026-10-08: A label is one panel refresh, not a clear and then a frame

<!-- prawduct: scope=fix-epaper-single-refresh -->

**Why:** the owner noticed the e-paper flashing more than expected. omni-epd's
IT8951 driver calls `clear()` inside `_display()` before every frame: a white
frame in the INIT waveform, then the label in GC16. Two full refreshes per label,
the first the heaviest flashing the panel has. Measured on the wall's panel:
1.77 and 2.31 s per label as shipped, 0.57 and 0.57 s without the clear.

**What:**
- `postarr/src/postarr/panel/epaper.py`: `open_panel` makes the opened driver's
  `clear()` a no-op (`_never_clear`). Nothing in the surface calls it; the
  driver's own `_display()` was the only caller.
- `postarr/tests/test_epaper.py`: `TestALabelIsOneRefreshNotTwo` drives
  `open_panel` against a stand-in omni-epd whose driver clears before each frame,
  as the real one does; seen failing with the call removed.
- `platform-and-dependency-findings.md` § The e-paper panel and
  `labels-and-surfaces.md`: the 1.5–1.9 s figure was two refreshes; now 0.57 s.
  The comments that quoted it (`surface.py`, `label_renderer.py`, `tests/fakes.py`,
  `tools/label_preview.py`) point at the findings instead.
- `_never_clear` runs inside `open_panel`'s guard: a driver that refuses it is
  `SurfaceUnavailable`, with a test.
- The panel now never gets an INIT refresh; #326 watches for ghosting.
- On the wall (2026-10-08): a rotation's caption landed 1.85 s after the picture
  changed, end to end, against 2.9–3.8 s before.

## 2026-10-08: Every run and look thread is joined before a test's catalogue closes (#324)

<!-- prawduct: scope=fix-324-discovery-thread-teardown -->

**Why:** #324. CI blamed `test_a_rejected_image_can_be_re_searched_over_the_wire`
for a `discovery-run` thread that hit a closed database in `_close_phase_two`.
With a 0.5s sleep put into `_close_phase_two` for the experiment,
`pytest -n0 -p no:randomly tests/integration/test_resolve_surface.py` failed the
same way, 1 failed and 8 passed. The thread belonged to the test before it,
`test_a_client_can_obtain_the_work_ids_the_actions_taking_one_require`. That test
returns once phase 1 hands the run to phase 2, and the thread dies during the
next test. #198 joined threads through a `run_threads` spawn. Only the shared
`services` fixture and two overrides passed it. Every other file's `services`
override used the runner's bare daemon thread. Under the same sleep, the tests
that left a thread alive at teardown were four in `test_get_surface.py`, one in
`test_resolve_surface.py` and two in `test_browser_review.py` (`TestTheReSearch`).

**What:**
- `arrt/tests/conftest.py`: a new `quiet_catalogue_file` fixture, which both
  stores are built from, joins every live thread named `RUN_THREAD_NAME` or
  `LOOK_THREAD_NAME` before `catalogue_file` closes, so a module that overrides
  `catalogue_file` keeps the join. It enumerates again after each join, so it also
  catches a follow-on run. It fails the test after 20s, and remembers the threads
  it failed for so one hung thread fails one test, not every later one. `run_threads` is retired, along with its uses in
  `test_browser_discovery.py` and `test_look_surface.py`. The look never received
  that spawn anyway, because `Services.bind` passed it to the runner only.
- `runner.py`, `look.py`: the thread names became module constants.
- `services/container.py`: `Services.bind(spawn=)` is removed. Nothing else
  passed it.
- `arrt/pyproject.toml`: corrected the comment on the `filterwarnings` error that
  #198 added. The error is reported against whichever test is running when the
  thread dies, not the test that started it.
- Checked by removing the join with the sleep still in. Then
  `test_resolve_surface.py` plus `test_get_surface.py` gave 3 failed and 2 errors.

## 2026-10-08: The panel opens again: jetson-gpio no longer overwrites RPi.GPIO (#181)

<!-- prawduct: scope=fix-181-gpio-shim -->

**Why:** #181. After a fresh install the panel failed with "Could not determine
Jetson model". Measured on the wall's Pi: `RPi/GPIO/__init__.py` in the venv was
`jetson-gpio`'s one-line shim (`from Jetson.GPIO import *`, its RECORD hash),
not `rpi-gpio`'s. Both packages own that path, so the last one installed wins,
which is why one lockfile gave a working panel on one install and not the next.
The issue's lead (the Waveshare board check) was refuted: the pinned
`epdconfig.py` is unmodified and detects the Pi from `/proc/cpuinfo`.

**What:**
- `postarr/pyproject.toml` `[tool.uv]`: an override removes `jetson-gpio` (the
  Waveshare sample imports it only on its Jetson branch). `uv.lock` follows.
- `postarr/tests/test_gpio_has_one_owner.py`: every lock requirement of
  `jetson-gpio` carries the never marker, and `rpi-gpio` is still locked; it
  fails against the previous lock.
- `deploy/README.md`: an existing venv syncs with `--reinstall-package
  rpi-gpio`, since removing `jetson-gpio` deletes the file both owned.

## 2026-10-08: Labels mapped on Settings › Clients; Walls says which caption each wall

<!-- prawduct: scope=displays-and-label-outputs -->

**Why:** Chunk 04 of `build-plan-displays-and-label-outputs.md`: the interface for
the records Chunks 02 and 03 made.

**What:**
- Settings › Clients: each client's *Labels* table (kind, whether the panel
  answers, size, the wall it captions), a *Caption a wall* form for any wall on
  any client, a Stop per mapping, and a ▲ note in both clients' panels for a
  display two clients report. Removing a client says which labels stop.
- Walls: "Captioned by {output} on {client}" under a wall a label captions; the
  duplicate-display fault in place of the client line.
- Mapping lives on Clients beside wall assignment, not on Walls as the plan said;
  the plan records it as a decision the owner can veto.
- Carried in: `nowShowing`'s unused parameter removed; `STATE_WORDS` held to the
  label schema's states by `test_wall_state_words.py`; an unreachable screen now
  "cannot say what its screen is showing", true of an unknown state too.
- Tests: `tests/browser/test_displays_and_labels.py` (the panel mapped to two
  HDMI walls and a Frame wall in turn, a refused second mapping, no panel, the
  fault on both pages), each watched failing against a re-break.
- Deploying: `deploy/README.md` § Displays and labels says to copy the catalogue
  first, since the migration drops the walls' client and output columns.

## 2026-10-08: Displays as records, label outputs, and a label renderer per panel

<!-- prawduct: scope=displays-and-label-outputs -->

**Why:** Chunks 02, 03, 05 and 06 of `build-plan-displays-and-label-outputs.md`
(#188): a wall names a display rather than a (client, output) pair, so a Frame
moved between clients keeps its walls; a wall has any number of labels on any
clients; and the panel stops belonging to the Frame loop.

**What:**
- Server: Display and LabelOutput records in Programming, with a migration that
  gives every assigned wall a display keyed `{client_id}/{output}` and keeps it on
  its screen. The client heartbeat keeps both records: a display first seen
  without identity is re-keyed when its identity arrives, and a Frame moved to
  another client moves with its walls. Two clients reporting one identity is a
  fault: neither is given the wall, and the API names both.
- Server routes: `GET /client` names each wall's display and the client's labels;
  `GET /labels/{label_id}` serves the label document with an ETag (`contract/routes.json`
  names it); HTTP and MCP map a wall's display and labels through one service in
  `programming/clients.py`. `ScreenState` is checked against both schemas' states
  in both directions.
- Player: the client reads the Frame's `device.duid` itself, once, without the
  art channel or a key, so a Frame with no wall still reports it. A configured
  panel is a label output, and `EPD_DEVICE` no longer needs `TV_ADDRESS`. One
  label renderer per mapped label polls its document through `pull.py`, applies
  the rule (`label_rule.py`, run over every contract vector), holds a caption for
  30 minutes while the server is away, and redraws only when the ink would
  change. `daemon.py` no longer draws the panel; its label tests moved to
  `test_label_renderer.py`, each move's reason in its commit.
- Mutation sweeps: the server delegate broke its new code in 11 places, 10 caught
  and one inert check deleted; the Player delegate's 37 were all caught; the
  coordinator's own sweep of the rule and the redraw decision caught 14 of 15,
  and the survivor (reading an unknown state as unreachable in `outcome`, which
  the fall-through already does) was deleted here and in the root reference rule.
- Artifacts: `data-model.md` (Display, LabelOutput, Q48–Q52), `api-contract.md`
  § Clients, `player-contract.md` (the label route's answers, the fault),
  `clients.md` § The Player, `observability-strategy.md` (label events carry
  `label_id`), and the plan's decisions. #315 filed for the panel failure reasons
  the client heartbeat cannot yet carry.
- Suites: 6297 passed across the three (recorded); browser suite 898 passed.

## 2026-10-08: The contract for displays and label outputs

<!-- prawduct: scope=displays-and-label-outputs -->

**Why:** Chunk 01 of `build-plan-displays-and-label-outputs.md` (#188): the contract
both the server and the Player build to before either changes. The plan's
high-impact assumption, that a Frame names itself, was checked first.

**What:**
- `client-heartbeat.v1`: a display output may carry `identity`, and a new
  optional `label_outputs` list (`epaper`) reports panels. The server refuses a
  malformed one and two label outputs of one name, as it does for outputs.
- `client.v1`: each wall may name its `display`, and a new optional `labels`
  list maps this client's label outputs to walls. The Player reads both and
  refuses the document whole when either is malformed, as it does for walls.
- `label.v1` (new): the label document, carrying the wall's display state and
  the label text, never a layout.
- `contract/vectors/label-rule.json` (new): the label rule as conformance
  vectors, the first behaviour vectors. `tests/preferences/test_label_rule.py`
  states the rule once, runs every vector against it, and checks that the
  vectors cover the table and both sides of the 30-minute hold. Mutating the
  reference rule fails it; one inert clamp was removed rather than defended.
- Fixtures for each new shape, indexed.
- `player-contract.md` § Transport and § Versioning describe the label route,
  display identity, label outputs and the rule.
- `samsung-tv-state-findings.md` § The set's identity: the Frame's `/api/v2/`
  carries one uuid as `id`, `duid` and `udn` on both ports; 8002 answers over
  TLS in 0.14 s, from standby. Not recorded: the value, the address, the MAC.
- The plan: the identity assumption marked verified in part; three decisions
  recorded; the route's entry in `contract/routes.json` moved to Chunk 03,
  because the server's route test holds mounted and named routes equal.
- `build-plan-display-state.md` and `build-plan-walls-work-and-trust.md` no
  longer claim their merged branches: each has only the operator's walk left.

## 2026-10-08: Archiving says the room loses the work now; an unknown filter key is refused

<!-- prawduct: scope=lists-settings-and-scale -->

**Why:** The boundary review of `build-plan-lists-settings-and-scale.md`.

**What:**
- Both archive confirmations said a wall loses the work later ("at that wall's
  next build", "the next time its theme is hung", with re-hanging offered as the
  remedy). Programming has taken an archived work off every published manifest
  as the archive lands since wave 2's reconciliation (removals republish,
  additions wait). They now say *now*, and `information-architecture.md`'s note
  that the archive path does not republish is marked superseded.
- `WorksFilter` refuses a key it does not know (422), so an act on a whole
  filter can never reach more works than the grid shows; a test keeps its keys
  equal to `GET /api/works`'s query parameters.
- Filed rather than built: #317 (held works on Search and Topic cannot be
  selected), #318 (Queue's grouping by message text can split one cause).

**Tests:** `test_archiving_a_work.py`'s `test_the_confirmation_says_how_to_make_the_room_catch_up`
became `test_the_confirmation_says_the_room_loses_it_now`: its claim, *when*
the room loses the picture, is kept and its premise corrected (the old test
asserted a delay and a remedy that wave 2 removed; `test_reconciliation.py`
pins the immediate removal). New in `test_acting_on_a_selection.py`: an unknown
narrowing is refused and acts on nothing; the filter model's keys are the
listing's. Each watched failing against the old code.

## 2026-10-08: One selection model, clean-up facets, every work reachable, Queue by cause, Topics before any are held

<!-- prawduct: scope=lists-settings-and-scale -->

**Why:** Chunks 05–09 of `build-plan-lists-settings-and-scale.md`: review
findings 17, 18, 23, 28 and 29 (#131, #281, #285, #288, #289).

**What:**
- **Chunk 05.** One selection module, `core/selecting.js` (`core/selection.js`
  was already the hang-a-selection act), on Artworks, Artist, Search and Topic:
  a Select toggle that reads *Select* / *Stop selecting*, ticks hidden outside
  select mode, and a sticky bar with Select all / Select none and every act
  valid for the selection: a theme picker with *New theme…*, Add, Remove from
  the shown theme, Archive (asks first), or Get for works not held. **On Search
  and a topic page only the not-held half is wired**: a held work there cannot
  be added to a theme or archived from that page (descoped at the boundary
  review, #317). Select all
  sends `{filter, except_ids}`, so it acts on every match, loaded or not
  (`POST /api/themes/{id}/works/bulk`, `/works/remove`, `POST /api/works/archive`).
- **Chunk 06.** `GET /api/works` takes `fit` (native, matted small, below floor,
  no size known) and `not_on_wall`, each counted like the other facets. *Not on
  any wall* is the owner's ruling for "never hung": what no hung theme or
  selection plays now, less works kept off every wall. The planes meet as id
  sets in the HTTP layer only (`DisplayService.work_ids_on_walls`), so neither
  imports the other. The rail toggle reads *Show filters* / *Hide filters*.
  Backlog item filed for recording which works a wall shows.
- **Chunk 07.** Artworks pages from the server as the curator scrolls, with
  *Show more* for the keyboard; `PAGE_CEILING` no longer limits it. Back
  restores the pages loaded and focuses the card opened (card 900 stays card
  900). A Posters tile with no image now opens its work.
- **Chunk 08.** Queue groups failed fetches by cause on the server (a cause is
  the reason with the work's own id or title taken out), largest first, each
  with *Retry all* in one request; a group opens into its works, 25 a page,
  named by title. Works in line page too. Retry's refusals name the work by
  title, over MCP as well. `tools/ux_walk.py` wrote spaces as `+` in addresses,
  which the client reads literally; it writes `%20` now.
- **Chunk 09.** Topics always offers the 13th–21st centuries and twelve major
  movements (`OFFERED_TOPICS`, QIDs checked 2026-10-08), each a link, a held one
  never twice. A topic's works stream (NDJSON on `Accept`) so they show before
  their makers are known, and the TopicSweep thread keeps the offered list's
  answers warm, a week at most, one topic at a time, stopped by any refusal
  (at most 63 queries a week). Topic names start with a capital.

**Tests:** new `test_one_selection_model.py`, `test_acting_on_a_selection.py`,
`test_clean_up_facets.py` (browser), `test_clean_up_facet_routes.py`,
`test_acquisition_queue.py`, `test_acquisition_routes.py`, `test_topics_offered.py`,
`test_topics_offered_surface.py`, `test_topics_before_any_are_held.py`,
`test_wikidata_topics.py`, and new cases in `test_the_grid.py`,
`test_navigation.py`, `test_acquisition_states.py`, each watched failing first or
by mutation. Changed, not weakened: Select-toggle assertions read the label (no
`aria-pressed`); the "no themes" tests now expect Select with *New theme…* and
Archive; Get tests on Artist, Search and Topic enter select mode first; grid
paging tests reach the end through *Show more*, and the runaway-guard test is
replaced by one paging past the old ceiling (the 2,000-work test asserts every
work is reachable); Queue's listing tests read failed works from their cause;
Topics' held-list selector is narrowed now that a kind also holds the offered
list, and two expectations capitalise the topic name; the three search-typing
helpers wait for the dropdown's answer to all the words, because under load it
opened on a mid-word pause (seen twice); a modifier-click test waits for the new
tab's address rather than reading `about:blank`.

## 2026-10-08: Themes as cards, Settings as an index, Status as a table, and the #297 follow-ups

<!-- prawduct: scope=lists-settings-and-scale -->

**Why:** Chunks 02, 03, 04 and 10 of `build-plan-lists-settings-and-scale.md`:
the follow-ups PR #297 filed, review findings 22 and 24, and the owner's
System-page feedback of 2026-10-07 (#265, #266).

**What:**
- **Chunk 02.** The Walls lead picture asks `GET /api/works/{id}/thumbnail?size=large`
  (the bare work fitted to 1,536 px, cached apart from the tile) (#303). Wanted's
  table stacks on a phone (#304). An Ask turn shows its cost tier from
  `GET /api/conversations/{id}/estimate`, a flat allowance at the conversation
  model's prices (new `CONVERSATION_*` settings); it reads and writes no spend
  (#306). Server sentences name the museum: each built-in plugin declares
  `MUSEUM`, `library/sources/names.py` gathers them, and the client's
  `MUSEUM_NAMES` is tested against them pair by pair (#298). #305 shipped in
  chunk 01.
- **Chunk 03.** `#theme` is a grid of cards (name, count, four pictures, the
  walls it hangs on), each linking to `#theme/<id>`, where rename, delete and
  membership live, with Move to top and Move to bottom. The order copy follows
  the theme's shuffle, from one `DisplayService.shuffles()` the manifest uses
  too. Renaming retitles the tab (#302). `GET /api/themes` gains `work_count`
  and `picture_ids`; theme answers gain `shuffled`.
- **Chunk 04.** Settings opens `#settings`, an index of Clients, Sources and
  Taste, in that order. Taste is headed "Taste" and names every way taste is
  recorded.
- **Chunk 10.** Status's Image sources panel is one table, a row per source,
  from `GET /api/sources/yields` (one SQL statement): Source, State, Offered,
  Chosen, Only here, Median long edge, Faults since startup, Last fault. Columns
  drop by the table's width in the ruled order, and the fault count moves into
  State when its column goes, so it shows once at every width; below 31rem a
  row stacks. The geometry panel and `artwork_box` on `/api/health` are gone
  (#266); nothing else read the field.

**Tests:** new `test_sentences_name_the_museum.py`, `test_source_yields.py`,
`test_the_status_sources_table.py` (a width sweep, plain and with wider
letter-spacing), `test_the_themes_index.py`, `test_the_settings_index.py`,
`test_theme_routes.py` cases, each watched failing first. Changed, not weakened:
wording expectations now name the museum where they named the plugin id (five
files, and the health-panel stubs in `browser/conftest.py`, which described
sentences the server no longer writes); single-theme tests open `#theme/<id>`,
and the two delete tests now check that the index lands without the theme
(the "repaints from the delete's answer" claim is retired, because delete
moved to the theme page); the sidebar tests take the new Settings order; the
integration test of the geometry panel is removed with the panel (#266), and
`/api/health`'s key-set test asserts `artwork_box` is absent; one Walls
thumbnail route glob was widened to match the query string, the assertion
unchanged.

## 2026-10-08: Component rules — one heading scale, one empty page, one glyph per meaning

<!-- prawduct: scope=lists-settings-and-scale -->

**Why:** The October review (finding 27, #287) found five heading treatments,
four empty-page patterns, disabled acts drawn as ready, and glyphs that meant
different things on different screens (◇ was "matted small", "cool" and "you
chose"). Chunk 01 of `build-plan-lists-settings-and-scale.md` sets the rules the
later chunks build to.

**What:**
- `design-direction.md` § Component Patterns rewritten to what the stylesheet
  holds (it named `.btn`, `.primary` and `.danger`, which never existed) and
  extended: headings, empty states, buttons and their disabled state, spacing,
  badges with one meaning per glyph.
- `core/glyphs.js` (new) names every badge glyph by meaning; every screen takes
  its glyphs from it. Reassigned so no glyph is shared: *you chose* ◇ → ◎,
  *likes* ◆ → ☆, *declines* ✕ → ✗, *gave up* ✗ → ▲ (a failure, not a verdict),
  the wall render ▣ → ▤ (▣ is the Artworks section icon), *Already in your
  library* ✓ → ●. The decorative ◦ before a taste row's derivation is gone.
- One `emptyState()` in `core/render.js` for every page whose list is empty
  (Artworks, Themes, Topics, Artists, To review, Queue, History, Wanted, Taste,
  Clients, Sources, Walls without a wall). The lead is a paragraph, not an `h2`.
- Walls' 36px heading and the `--text-3xl` token only it used are gone: every
  page's `h1` is one size.
- A disabled act looks disabled. Hover tints with an inset shadow instead of a
  `filter`, so a full-card link inside an act keeps covering its card (#305);
  the stacked-table exception that worked around the filter is removed.

**Tests:** new `tests/unit/test_glyphs_have_one_meaning.py` and
`tests/browser/test_component_rules.py`, each watched failing against the old
code. Changed, not weakened: `test_the_review_grid.py` expects ◎ for *you chose*
(the glyph was reassigned); `test_activity.py`'s empty-queue check asserts the
lead's exact words instead of a trailing space, and its absence check keys on
`.empty` (`.panel.empty` no longer exists, so the old check would pass on
anything); `test_wanted.py` reads `.empty`; in `test_client_vocabulary.py` the
sentiment-glyph check verifies each shape names a meaning `core/glyphs.js`
holds, since the values are no longer string literals.

## 2026-10-08: Plan displays and label outputs; the Apple platform findings

<!-- prawduct: scope=displays-and-label-outputs -->

**Why:** #188 is next in `labels-and-surfaces.md`'s order, and the owner widened it
on 2026-10-08 (`feeds-and-players.md` rulings 1 and 9) so displays become server
records too. The platform facts in `feeds-and-players.md` § Platforms were the
builder's recollection until a spike measured or sourced them.

**What:** Planning and findings; no code.
- `build-plan-displays-and-label-outputs.md` (new): seven chunks. A contract with
  display identity, label outputs, a label document and the label rule as
  conformance vectors. Display and LabelOutput records with a migration that keeps
  every wall on its screen. The label route and the duplicate-display fault. The
  interface, held until `feature/lists-settings-and-scale` merges. The Player's
  reports. A label renderer per label output, with the Frame loop no longer
  drawing the panel. The operator on the wall, after #181. Four observations from
  the display-state review are carried in.
- `apple-platform-findings.md` (new): what a macOS screensaver and a tvOS app can
  do as Players, each fact labelled measured, sourced or unverified.
- `feeds-and-players.md` § Platforms corrected from it: a backgrounded tvOS app
  goes silent rather than reporting `in_use`; tvOS has no local-network permission
  and the Frame's certificate is the obstacle; the macOS saver host must be torn
  down on `willstop`, and whether a saver can reach the LAN is its largest risk;
  `UIScreen` gives no physical size, so the relative mat width applies on Apple
  TV; CoreText can do the label's measuring; and unverified facts are verified
  on hardware before each platform's plan is written.
- `labels-and-surfaces.md` § What changes, in order: #181 now blocks only the
  plan's last chunk, the operator's.
- `apple-platform-findings.md` registered in `project-state.yaml`.

## 2026-10-08: Feeds and players: one Player core for private walls and public channels

<!-- prawduct: scope=feeds-and-players -->

**Why:** The owner set the Player's next shape: Players on several platforms (the Pi,
Apple TV, Mac and Windows screensavers), a display controller kept apart from the
wall it shows, the Player in its own repository, and logic and documentation
reused across platforms. A second use case came with it: public channels of
public-domain art that any number of Apple TV apps read, with the server neither
knowing nor caring how many. Major 2 is still a draft, so this is the cheapest
moment to reshape it.

**What:** Design only; no code.
- `feeds-and-players.md` (new): the owner's direction in their words, and ten
  rulings, each marked with whose proposal it was. Major 2 becomes a **feed** (schedule, works,
  default presentation settings) plus an optional **control** layer; each major at
  its own URL; displays as server records with one client each, configured on the
  host and never discovered; rendering always on the client; presentation settings
  in three layers (feed, wall, device), including which facts about a work show;
  the feed carries only the mat colour and the client decides mode and width;
  public channels published to static hosting, public-domain only, 4K at most,
  listed in a published index; reuse through a Player spec and conformance
  vectors, with no shared native core until a stated trigger.
- Dated pointers in `re-architecture.md`, `player-contract.md` (§ Major 2 and
  § The cutover), `data-model.md` constraint 13 (reopened for public channels
  only) and `nonfunctional-requirements.md` § The mat is geometric.
- Registered in `project-state.yaml`'s artifact manifest.

## 2026-10-08: Labels as outputs, and each wall reports its display state

<!-- prawduct: scope=display-state -->

**Why:** The owner, declining an interim fix for the Pi's e-ink panel: labels are
their own outputs, mappable to any wall on any device, kept in sync; blank while
somebody watches a movie on the Frame; and the abstractions must stay clean for a
caption composited into the image later. Only a wall's controller knows what its
screen is doing, so labels need that report before they can be split from walls.

**What:**
- `labels-and-surfaces.md` (new): the owner's rulings of 2026-10-08 (ruling 1 revised
  the same day from schedule-first to report-first), five nouns (wall, client, output,
  wall controller, label renderer), the display states and what a label shows in each,
  and the rules that keep a caption-in-image possible. Reverses "one process per wall
  drives both picture and label" in `re-architecture.md` and `clients.md`.
- **Heartbeat minor 3** carries `display_state {state, work_id, since}`: `showing_art`,
  `in_use`, `dark`, `no_screen`, `unreachable`; a work only beside `showing_art`.
- **The Frame controller** reports it on change: a remote-control change resolved to a
  work through the bindings; `in_use` vs `dark` from one read-only PowerState GET taken
  only after `get_artmode` says off (never a key press). Its panel blanks for `in_use`
  and `dark`, and 30 minutes into `unreachable` (the owner's number).
- **The HDMI controller** reports `showing_art`, `dark` (no screen detected) and
  `no_screen` (output gone).
- **The server** keeps each wall's state, adds `unassigned` and `silent`, refuses a
  malformed `display_state` but reads a state name it does not know as `unreachable`
  (so a Player can upgrade before the server), and carries it on `/api/walls` and
  `art_display`; **Walls**
  leads with it ("Somebody is using the screen", "Its screen is off", "Not heard from
  since …").

**Tests:** contract fixtures on both sides of the work-id rule; `postarr/tests/test_display_state.py`
drives the TV double through each transition (remote change, TV and back, standby, a failed
PowerState read, unreachable at 29 and 31 minutes); server unit and browser tests seed
real heartbeats for each state, a pre-minor-3 one and a stale one;
`test_staleness_threshold.py` ties the Player, server and client thresholds together.

**Deploy:** the server and the Pi's Player both, in either order: a server reads a
state a later Player adds as `unreachable`. A minor-2 Player keeps working: the
server reads its `current_work_id` as `showing_art`. Rolling back either side alone is
safe; nothing new is stored beyond the heartbeat file.

**Not done:** chunk 05, the owner's check on the wall. The PowerState read goes to the
set's TLS port (8002), unmeasured on the set until then. Label outputs and their mapping
are #188, next.

## 2026-10-08: Walls, Work, and signals you can trust

<!-- prawduct: scope=walls-work-and-trust -->

**Why:** The high-priority findings of `ux-review-2026-10.md`, built as one plan and one
PR at the owner's request ("minimize ceremony"). The two weekly scenarios failed: one
held work could not be hung (S1), and Walls could not say what was on the wall (S6, S8).
The review also found navigation by script buttons, signals that contradicted
themselves, a product voice that was the code's rather than the curator's, and art
shown as the wall render.

**What:**
- **Walls and Work** (#272, #295, #162): each wall card leads with the work its
  heartbeat names, with Skip, *Not this one again* (this theme, or every wall) and
  Change; a client report older than three heartbeats is said as unknown. The Work
  page's state strip lists the walls and themes a work is on, with Hang…; Archive is
  secondary; museum `<i>`/`<b>` render through an allow-listed tokeniser.
- **Programming**: a wall can hang a selection (a theme with a hidden flag, deleted once
  no wall hangs it, refused as a destination, default, add target or rename target); a
  work can be kept off every wall (`work_exclusions`) and allowed again;
  `GET /api/works/{id}/placements`.
- **History is events** (#293): a Library-side `history_events` log of Gets, verdicts,
  archives, restores, hangs and exclusions, from now on; History and each wall read it.
- **Navigation is a link** (#273): every list opens its items by `<a href>`; scroll,
  focus and Back keep the place; each screen has its own title and h1.
- **Failures beside the control** (#277), through one helper.
- **Search and review trust** (#275, #276, #89): registry rows fold into held twins;
  works waiting for review are marked and a Get skips them, and skips held works matched
  by title and artist; review candidates carry confirmed / unconfirmed / unknown
  (`source_found` from the model); a verdict is held 5 s with Undo.
- **Spend** (#290): the approval gate is retired (ruling 3); `GET /api/budget` and the
  sidebar's "left this month"; a cost tier on every spending action.
- **One vocabulary** (#291, #292, #267, #283): Get everywhere (`#get/`, `#run` aliased),
  Wanted always shown, bare-noun labels, one date formatter, costs to the cent, museum
  names.
- **Tiles show the art** (#278, ruling 7), with a 1920 px `/wall-preview` for the Work
  page; **keyboard and phone** (#280, #279).
- Retired the parked round-2 UI plan; carried its operator-ruled § Boundaries amendment.

**Tests:** guards new with this branch include `test_navigation_is_a_link.py`,
`test_labels_are_bare.py`, `test_no_machine_dates.py`, `test_one_date_formatter.py`,
`test_stylesheet_is_whole.py`, `test_staleness_threshold.py`, and browser suites for
Walls, the Work page, History, review trust, spend, tiles, keyboard and phone (a
sideways-scroll check over every route at 390 px). Each new test was watched failing
against the unfixed code. Existing tests changed deliberately are named in their
commits; none was weakened.

**Deploy and roll back:** the catalogue gains `history_events`, `work_exclusions`,
`themes.is_hidden` and `candidate_works.source_confirmed`, added at startup; tiles and
wall previews cache under `thumbs/tiles/` and `thumbs/wall-previews/`, and an old
thumbnail row regenerates. `MONTHLY_BUDGET_USD` is optional (only for a key with no
provider limit). **Rolling back to an older image is not clean:** an older build reads
every hidden selection as an ordinary theme, and puts back on the walls every work kept
off with *Not this one again from every wall*. Restore the catalogue backup taken
before this deploy alongside the older image, rather than the image alone.

**Not done:** the live walk of S1, S6 and S8 on the real wall (chunk 13), owned by the
operator after deploy. Pass 1 re-run on a synthetic 2,000-work library found no screen
reached only by a button and no dead end.

## 2026-10-07: Walls says "Shown by" only when a screen is there

<!-- prawduct: scope=wall-screen-state -->

**Why:** #274, finding 6 of the October UX review. With the TV off, Clients said both
outputs were "not connected", Walls said the wall was "Shown on hdmi-a-1", and the top bar
said "Well". Measured on the wall's Pi with the owner confirming the set was off: the
kernel reported the connector `disconnected`, as it does when a TV is off or unplugged. So
Clients was right. Walls was claiming display from the *assignment* alone. The owner
ruled that "Well" means healthy, not that the TV is on, so the top bar is unchanged.

**What:** `core/outputs.js` (new) holds one state per output, read from the client's
last report: detected, not detected, not reported, unreadable, or not listed. It also
holds the words for each. Walls keeps each client's report from the listing it was
already fetching and says "Shown by" only for a screen detected. Otherwise it says
"Assigned to…" with "no screen is detected (off or unplugged)", or which of the three
reasons leaves the screen unknown. Clients' column becomes *Screen*
("● detected" / "○ none detected (off or unplugged)") beside *Size*, and the output
picker says "screen detected" / "no screen detected". Clients' own lines about a wall
say *assigned*, not *shown*: the "Walls assigned to it" heading, "has no wall assigned
yet", "Every wall is already assigned to", the assign and unassign messages, the wall and
output pickers, and the rotate and remove confirmations. Otherwise the same
claim would have come back one screen over. `information-architecture.md`'s Walls and
Clients rows describe the new lines.

**Tests:** `tests/browser/test_the_walls.py`:
- detected, with a second wall on the same client's other output, so a lookup by
  client rather than by output reads wrong for one of them;
- not detected;
- each unknown reason, each asserting "Shown" absent;
- the listing down.

`test_the_clients.py`: the column's words, its headers, that "connected" no longer
appears, and the assignment lines' new wording. The two rewritten assertions keep their tests' claims: an assigned wall with a
screen detected still reads "Shown by", and the listing-down test still names the
output. Watched to fail before the fix, and two hand mutations of `screenState` (always
detected; no not-listed case) each turned one test red.

**Not changed:**
- **How old the report is.** A client that died after reporting `connected: true` still
  reads as shown. Choosing a threshold is a requirements question of its own, filed as
  #295.
- **The Frame output.** It is reported connected because it is configured; whether the
  TV answers is the wall heartbeat's `television_reachable`.
- **A kernel `unknown` status.** The Player reports it as `connected: false`, so it reads
  "none detected". The Player's docstring chooses that on purpose ("a screen this client
  cannot confirm is not one it should claim"), and the contract's `connected` is a
  boolean with no third value.

**Measured both ways on the wall's Pi:** `card1-HDMI-A-1` read `disconnected` at
15:48 and 16:19 local with the TV off, and `connected` at 16:21 after the owner turned
it on. So "Shown by" rests on a signal that follows the set.

## 2026-10-07: the UX walkthrough, as a practice and a harness

<!-- prawduct: scope=ux-walkthrough -->

**Why:** the owner, 2026-10-07: IA/UX/UI is the product's weakest point, and every
guard the browser client has asks whether it matches its documents, never whether it
is good to use. They asked for the method to be written down "so we don't re-derive
later", and then run.

**What:** `docs/ux-walkthrough.md`, the four passes (inventory, scenarios, critique by
independent lens, people) and how their findings are ranked and routed; a pointer to
it from `CLAUDE.md`. `arrt/tools/ux_walk.py`, Pass 1: it reads the declared screens
from `app.js`'s `ROUTES`, crawls the reachable ones from the home page by links
and by clicking up to 30 buttons a page (`--clicks-per-page`; 0 follows links only),
because the client navigates by buttons that call the router; photographs each at phone and desktop width in light and dark, records headings,
controls and links, runs axe-core per photograph, and writes `inventory.json` and a
contact sheet. It refuses every request but `GET`/`HEAD` in the browser, so a clicked Accept,
Rename or Unassign never lands, but check the server's state after a run against
the real library; `--synthetic N` boots a throwaway server over the suite's large corpus.
Output goes to the gitignored `.ux-walk/`.

**Tests:** `tests/unit/test_ux_walk_parsing.py` (the route table and address
grammar); `tests/browser/test_the_ux_walk.py` (a write from the page refused and
absent from the server afterwards, a read let through, every declared screen
photographed or named as never visited, the skip link not mistaken for a screen, a
screen reached only by address marked so, one a button opens found and marked as
reached by script, `--clicks-per-page 0` following links only, a scan's clean,
violations and not-run kept as three states, a screen that never paints recorded
blank rather than aborting the walk). The guard and the anchor skip were each broken by
hand and watched to fail, as were the synthetic boot's cleanup and the axe-core
pin. The browser tests are deselected by default, so they are not in the
recorded suite run; `uv run --group browser pytest tests/browser/test_the_ux_walk.py
-m browser -n0` ran them, 8 passed. `tests/integration/test_ux_walk_synthetic.py`
boots `--synthetic` in the default suite.

**The first run** is `.prawduct/artifacts/ux-review-2026-10.md`: 30 ranked findings
from Pass 1 on the real library and a synthetic one, Pass 2's 13 scenarios, and five
independent lenses, routed to 18 new backlog items (#272–#289), comments on #131,
#252 and #265, and five decisions put to the owner. Pass 4 is the owner's. The
practice doc gained the reviewer brief and two rules the run taught; `design-direction.md`
lost a notice that its palettes were not yet in the stylesheet, which they had been
for weeks.

**The owner's rulings on the review**, the same day (`ia-proposal.md` § Rulings
(2026-10-07)): the ruled Walls and Work pages are next (#272); a new norm,
*navigation is a link, an act is a button*, in `information-architecture.md`
§ Direction, in-transition (#273); spend shown as a monthly budget with cost tiers
and no approval gate (#290), reversing the 2026-08-04 decision never to show the
remaining balance, recorded in `nonfunctional-requirements.md` and
`observability-strategy.md`; *Get* everywhere (#291); Wanted always in the sidebar
(#292); History as events (#293). The proposal's claim that walls already keep a
history is corrected: the schema overwrites each wall's hang.

## 2026-10-07: the Rijksmuseum as a built-in source, through its Linked Art records, its search and IIIF

<!-- prawduct: scope=rijksmuseum-source -->

**Why:** arrt#226, asked for by the owner on 2026-10-07, the last of the Linked Art
tier. The museum holds the largest open volume measured, almost none of it reachable
through Wikidata (`linked-art-findings.md` § The Rijksmuseum). The robots.txt
ruling it waited on was made the same day.

**What:** a built-in `rijksmuseum` plugin (`library/sources/rijksmuseum.py`). The
finder reads the item's `id.rijksmuseum.nl` records (P13234) and reports each under
the URL as the item spells it. When the item names none the museum knows, or the work
has no item, it searches the collection by title and maker among objects with an
image. If an accented maker finds nothing, it asks once more without the accents,
because the museum folds them for some makers and not others. A work with no maker
is not searched for. The image is three records away (VisualItem, DigitalObject,
access point on `iiif.micr.io`), and its rights are the VisualItem's (Public Domain
Mark, `InC`). In-copyright works the museum marks not downloadable are found like
any other. The maker is the first part of the production naming one. An
attribution ("attributed to …", "(possibly)") is kept, and evidence ("(signed by
artist)", "(mentioned on object)") is dropped. The image service declares 17.55 MP,
so most originals are tiled under `TILE_MAX_PIXELS`, and the rest are fetched in
one request. It reads no web page. The built-in enumerations, the plugin guide's
examples table and the security model name it. A mutation sweep of 46 mutations left
4 survivors. One was an inert check (the access point's shape already pins the
image host), which was deleted. The other three got tests. The live check
(`test_rijksmuseum_shapes_are_still_real.py`) passed 8 of 8 on 2026-10-07.

## 2026-10-07: the Getty as a built-in source, through its SPARQL endpoint, Linked Art records and IIIF

<!-- prawduct: scope=getty-source -->

**Why:** arrt#230, asked for by the owner on 2026-10-07 after Yale. Measured the
same day (`linked-art-findings.md` § Getty): only 30 Wikidata items with a Getty
ID lack an image, while the museum holds 124,301 objects with images. So the
plugin searches as well as following the item.

**What:** a built-in `getty` plugin (`library/sources/getty.py`). The finder maps
the slugs of the item's Getty pages (P2582) to Linked Art records in one query to
the museum's SPARQL endpoint, and reports each under the page as the item spells
it. When the item names none the Getty knows, or the work has no item, it asks
for the maker by name and then for that maker's objects whose titles hold the
title's words. A work with no maker is not searched for, because the endpoint has
no text index and a scan takes 11–14 s. Title and maker come from the record,
since the manifest drops non-ASCII letters. The title is the record's title equal
to the one asked, else Getty's preferred one. The maker keeps Getty's attribution
("Workshop of", "and workshop"). The image is the v3 manifest's first canvas, and
rights are the manifest's per-object `rights` (CC0, `InC`, `InC-RUU`). Works the
Getty keeps at 600 px are found as placeholders. The reader answers one request for
originals up to the service's declared 30,000 px. It reads no web page. The
built-in enumerations, the plugin guide's examples table and the security model
name it. `getty` sorts third in the default order, ahead of `met`. That changes
only which image wins a tie, since every finder is asked at once. A hand mutation sweep of 48 mutations left 4 survivors: one inert check
was deleted, and the other three got tests. The live check
(`test_getty_shapes_are_still_real.py`) passed 7 of 7 on 2026-10-07.

## 2026-10-07: IIIF parsers in the plugin interface (1.3), and Yale through its manifests as a built-in source

<!-- prawduct: scope=yale-source -->

**Why:** arrt#242, a helper shared by the Linked Art museums (Yale, the
Rijksmuseum, Getty), approved by the owner on 2026-10-06, and arrt#229, its first
consumer. The owner asked for the next public plugin on 2026-10-07, the day #233
Paris Musées was demoted. Measured the same day (`linked-art-findings.md`): the
three museums reach their image services by three roads and share only the last
step, so the shared part is IIIF, not Linked Art. That narrows #242's proposal,
and is recorded on the issue.

**What:** interface 1.3 adds IIIF parsers that do no I/O: `ImageService` (an
`info.json`'s original size and declared limits, and whether one request or the
tiles fetch it, below a long side the caller states), and `CanvasImage`,
`manifest_images` and `manifest_metadata` (a Presentation 2 or 3 manifest).
A built-in `yale` plugin (`library/sources/yale.py`) finds a work through the
YUAG or YCBA page its Wikidata item names (P8583, P9789). It never fetches the
page, which is challenged. It reads the manifest built from the page's number
and reports the first canvas under the page as the item spells it. The title and
maker are Yale's own words. Rights come from the canvas, not the manifest's CC0,
which licenses the record. The size is the canvas's: most works with no
image on Wikidata are served at 480 px and are reported as placeholders. The
reader answers one request for an original up to 16,384 px, and tiles beyond
it or below a declared limit. It offers its reader alone with no registry. LUX
search is not built: the IDs reach 4,053 of the 4,068 YUAG items with no image.
The built-in enumerations, the contract (§ Versioning and errors), the plugin
guide (§ Reading IIIF) and the security model name the parsers and the plugin.
The live check (`test_yale_shapes_are_still_real.py`) passed 5 of 5 on
2026-10-07, and the descopes and the robots.txt findings are recorded as comments
on #242, #229, #226 and #230. The owner ruled the same day that robots.txt does
not bar a plugin's single, human-led requests (`source-plugins.md` § Trust): the
Rijksmuseum's and Philadelphia's image host (`iiif.micr.io`) disallows `/`, and
Getty's answers its robots.txt with 503. The plugin guide adds "ask per work,
never walk a site".
