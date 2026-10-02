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

## 2026-10-02: Where an accepted work's image stands, on every screen that shows the work

<!-- prawduct: scope=after-review -->

**Why:** Chunk 01's queue fetches and prepares accepted works in the background,
and a background job that nobody can see reads exactly like one that never ran.
The owner asked that the Work and Review pages say whether a work is queued,
being fetched, or failed and why, and that a pause say why on Activity (#167).

**What:**
- **The Work page, a Review card for an accepted work, and Activity › Queue**
  say where a work stands, in one set of words (`core/acquiring.js`): queued,
  fetching, failed (which try, why, when next), gave up (with **Retry**), or
  paused (why, and the remedy). Queue lists every work owed, in the order the
  queue will try them, under the searches. Activity's count stays To review's.
- **HTTP:** `GET /api/works/{id}` gains `acquisition`; new
  `POST /api/works/{id}/acquisition/retry` and `GET /api/acquisitions`; every
  candidate work gains `artwork_id`.
- **MCP, breaking:** `retry_acquisition` queues the work and returns at once,
  instead of fetching in the call beside the queue's own fetch; `get` carries
  `acquisition`. Its per-outcome notice went with the synchronous fetch, and
  `sources` still reports a partial fetch. `resolve_images`' text now says
  *wanted works*. Recorded in `api-contract.md` § Versioning.
- **The queue:** an unexpected error from one work's attempt now counts against
  that work instead of pausing every fetch; a Retry on a work with no source is
  refused. The deployment faults' remedies moved from MCP's binding to
  `DEPLOYMENT_REMEDIES`, beside `DEPLOYMENT_FAULTS` (now public).
- **Tests rewritten to the new contract, not weakened:** MCP's retry tests (it
  queues; a pass then shows the failure or the pause through `get`); the
  binding's notice and remedy tests (the remedy table, parametrised over
  `DEPLOYMENT_FAULTS`); Chunk 01's pause-on-unexpected-error test, split into
  the error from one work (counts against it, the next is still fetched) and the
  error outside any work (still pauses). Queue's empty sentence now says "No
  search is in flight", since the fetches beneath may be. Eight new tests watched
  failing against eight re-breaks.

## 2026-10-02: An accepted work fetches and prepares itself; one wanted state

<!-- prawduct: scope=after-review -->

**Why:** nothing fetched an accepted work's master image or prepared it, so
every work accepted through Get or Ask stayed off every wall until an agent
called `retry_acquisition` and `regenerate` by hand (#167). And a work with no
scan offered only Accept or Reject, with no way to say "I want this, find it
later" (#168). The owner asked that wanting any scan and wanting a better one
converge.

**What:**
- **The acquisition queue** (`library/acquisition/queue.py`, Chunk 01): one
  worker, woken by acceptance and catching up at start, fetches each accepted
  work holding no image and then prepares it. Failures retry after 1 h, 1 day
  and 3 days, then wait for Retry; a partial result counts as acquired; a
  deployment fault (short disk, no dezoomify-rs, no tile resolver) pauses the
  queue without counting against the work. Its state is one table,
  `acquisition_queue` (Q31-Q35). Preparation now records the mat colour's model
  spend as `mat_color_vision`. Built by a delegate in its own worktree; 30
  re-breaks caught, re-run after a scratchpad collision with the other delegate.
  Critic `rev-20261002T194630Z-9a001a93`: 1 blocking (two untested branches:
  when the worker wakes for a retry, and no second fetch after a named source),
  fixed with four tests watched failing, plus a Retry/attempt race closed;
  `rev-20261002T195129Z-b2afcdfd` clean.
- **One wanted state** (Chunk 03): `awaiting_better_image` is renamed `wanted`
  by migration, with one way in, `DiscoveryService.want(work, turning_down=…)`.
  Turning down the scan on offer wants a better one; turning down an alternate
  only suppresses it. `set_verdict` still refuses the verdict. `POST
  /api/candidates/{id}/want`, `GET /api/wanted`, and MCP `art_review` actions
  `want` and `list_wanted`. The rename and the `reject_image` change are
  breaking and recorded in `api-contract.md` (Q36-Q37). Built by a delegate;
  integration found `art_review`'s pinned help listing missing the two new
  actions, and added them.
- Carried fixes: `app.css`'s scans and `.stack-tight` comments, `search_topics`'
  docstring (topic search is kept a week), and `re-architecture.md`'s list of
  what runs in the background.

## 2026-10-02: The owner's review of the screens: Add to, the typeahead, and Review on a Get's own page

<!-- prawduct: scope=topics-and-destinations -->

**Why:** the owner looked the screens over on a catalogue copy. On a Topic page
*Add to* showed *New theme…* with the name already typed; the typeahead hid
Wikidata's artists and works behind the slower topic search; a Get asked for a
second page to judge works the curator had already chosen; Review's card was a
narrow column whose Scans facts wrapped a few characters wide; and "would show
at 28.2″" meant nothing without knowing the panel.

**What:** *Add to* offers a caller's name as "<name> (new theme)", selected,
with the name field hidden unless *New theme…*. The typeahead paints each
Wikidata answer as it arrives, with *Asking Wikidata…* until both have. A Get's
page is its review; cards are one work per row; Scans is a table after Radarr's
interactive search; the scan's pixels show above the fold and no screen shows
inches; clicking a picture enlarges it in place (`?size=large` previews). The
scan payload gains `width` and `height`. Critic `rev-20261002T174121Z-200674d5`:
0 blocking; its follow-ups keep a review card (its *Why*, open *Scans* and focus)
across a running Get's redraw, tell a finished Get whose cards could not be read
to reload, name an enlarged scan for the picture, and let fact lists wrap
between words on phones (`rev-20261002T180820Z-3fd253b4`, clean). PR #171's
browser CI leg then found the Scans table scrolling sideways inside a 1280 px
card on the runner's wider fonts (it was already 24 px over on macOS, inside the
edge check's padding slack): a scan's two actions now stack, and the test
asserts the table's box does not scroll. Three browser tests that read the page
before it settled under `-n auto` now wait for what they assert. Filed from the owner's review of the screens: #167 (accepting never acquires the
master), #168 (Wanted), #169 (Artworks' theme filter vs add-to-theme, decided:
follow Radarr).

## 2026-10-02: Library › Topics and the Topic page, kept answers, and the owner's topic rules

<!-- prawduct: scope=topics-and-destinations -->

**Why:** S12 asks to browse by period, movement, subject or medium and Get from
there into a theme named after the topic. Chunk 03's measurement found period
pages slow (7-60 s) and three rules that read badly; the owner answered all of
it the same day.

**What:**
- **Library › Topics (`/topics`) and the Topic page (`#topic/<qid>`):** your
  topics by kind with counts and a Wikidata search; a topic's head, *In your
  library*, *Representative works* (headed with its years for a period) and
  *Artists*, the registry sections filled after the page draws. Get from a topic
  defaults *Add to* to a theme named after it. The top bar gains *Topics* and
  *Wikidata: topics* groups.
- **Answers kept across restarts:** `persistence/kept.py`, a general store any
  slow foreign source can use, in **`ART_ROOT/kept-answers.sqlite`, which is
  disposable: a backup may skip it, and deleting it costs only time.** Every
  registry page section and topic search keeps its answers for a week. The
  in-memory `Remembered` is retired; its LRU tests live on in
  `test_kept_answers.py`.
- **The owner's topic rules:** the kind rule loses its "start and end time"
  clause; search drops movements no visual artwork's maker belongs to; a topic's
  artists rank by the summed sitelinks of their works in it (after works-count
  let bulk catalogue imports lead). A topic's works and artists get Wikidata's
  own 60 s limit, so a named period is slow once and then kept.
- Driven on a catalogue copy (S12): 16th century → three works into a new theme
  "16th century" → accepted: the theme holds them, *All works* does not, and the
  topic's count rose from 1 to 4. A bookmark to `/topics` 404'd until added to
  `UI_PATHS`, caught by the boundary run.
- Cumulative Critic `rev-20261002T161451Z-8549ec71`: 0 blocking; three warnings
  fixed (section timeouts, topic search kept, the artist-match nudge tested),
  the rest accepted on the record. Backlog #165 and #166 filed.

## 2026-10-02: Topics from Wikidata, and your works' topics as facets

<!-- prawduct: scope=topics-and-destinations -->

**Why:** a curator could browse by artist but not by period, movement, subject
or medium, and the Artworks facet rail was empty because nothing wrote
`work_facets`.

**What:** the registry answers a topic, its works, its artists, topic search
and a held work's topics (`wikidata.py`, `TopicService`); the kind rule was
measured on twenty topics, 0 wrong (`wikidata-findings.md` § Topics). A topic
sweep writes `sourced` facet rows with `value_qid` at start, after acceptance
and after a QID change, never touching `inferred` rows. `GET /api/topics`,
`/api/topics/{qid}` (no network), its `/registry`, `/works` and `/artists`
sections, `/api/registry/topics`, and `art_catalogue(action='topics'|'topic')`.
Driven on a catalogue copy: the sweep wrote 140 rows and the rail shows
movement, era, subject and medium with counts, narrowing the grid when chosen.
Critic `rev-20261002T145007Z-483be496` found the sweep's wiring untested; four
tests now hold it (`rev-20261002T145426Z-32e27622`, resolved).

## 2026-10-02: A Get names where its works go, over HTTP, MCP and the client

<!-- prawduct: scope=topics-and-destinations -->

**Why:** every accepted work joined the default theme, so works a curator
wanted for one occasion entered the everyday rotation. The owner recast
ruling 5a's "excursion" as a destination on every Get (2026-10-02).

**What:** `discovery_runs.destination_theme_id` (nullable, no cross-seam
foreign key) records a Get's theme; `LibraryFacade.destinations` answers it per
work; Programming's `offer_destinations` (was `offer_to_default`) puts an
accepted work in that theme, or none if it was deleted, and `catch_up_offers`
does the same at start. `POST /api/gets` and `art_discovery(action='get')` take
`theme_id`. The Get control gains *Add to*; Queue, History, the run page and
Review say where a run's works go. "Excursion" is retired from the live
artifacts; `data-model.md` gains Q22-Q24. Built by two delegates in worktrees,
merged no-ff; Critic `rev-20261002T141127Z-2cff3579`, 0 blocking.

## 2026-10-02: The cumulative review of Get and Ask, resolved

<!-- prawduct: scope=get-and-ask -->

**Why:** the cumulative review found two defects behind green suites. With
Commons the only source, a search's works were recorded `not_held`, because
Commons answered "nothing" for a work it cannot look up by title. And a level tie
between sources was stored on a random id, because the stored selection
re-ranked without the pool's order.

**What:** a source now has a third answer, `ImageQueryUnanswerable`; Commons
gives it for a work with no Wikidata item, the pool treats no answer as no answer
(`NoSourceCanAnswer`, logged `phase_two.unanswerable`), and the work waits.
`selection.py` ranks by the pool's precedence before the id, and a row from a
source no longer wired ranks last rather than raising. Also: the pool's threads
keep the run id in their logs; turning a scan down re-reads the To review count;
a failed count read is said in the console; `get.asked` names the run it
started; and `architecture.md`, `api-contract.md`, `observability-strategy.md`
and `.env.example` describe the pool, the listing's counts, the new events and a
Commons-only deployment.

## 2026-10-02: Activity › To review, with what waits counted in the sidebar

<!-- prawduct: scope=get-and-ask -->

**Why:** a run that finished with works nobody judged sat in History looking
done (`information-architecture.md` § The *arr layout recorded the gap on
2026-09-30), and Get makes such runs ordinary.

**What:** `GET /api/runs` and `art_discovery(action='list_runs')` carry
`awaiting` (works that found an image and have no verdict, by run) and
`awaiting_works` (in all), and narrow to such runs with `awaiting`, before the
cap. *To review* is Activity's first page, listing those runs with their counts,
each opening Review; the count shows on its link and as *N to review* on
Activity's, and is read again after every navigation and as soon as a verdict is
recorded. The sidebar test now checks every section's pages, which it had listed
and never read.

## 2026-10-02: Ask, where Add New was

<!-- prawduct: scope=get-and-ask -->

**Why:** ruling 3 dissolves Add New. Acquiring is *Get* on a selection, and the
page that held the intent box and the conversations becomes *Ask*.

**What:** the sidebar's Artworks › Add New is Artworks › Ask, at the same address
`#discover`. The search box's group and row read *Ask* and *Ask about "…"*, as does
the results page's empty state, and every button that opened Add New names Ask.
`information-architecture.md` describes Ask in its screen tables, flows and the
*arr-layout table. `tests/preferences/test_screen_tables.py` now holds each sidebar
page's name to its route-table label, which a hand-written name had let drift.
Carried from the last review: the run screen's no-provider sentence is tested
over a discovery run holding an offered work.

## 2026-10-02: Get in the client, and no more "null" on the page

<!-- prawduct: scope=get-and-ask -->

**Why:** ruling 3 makes Get an action on any selection. The server half shipped
with Chunk 03; this is where a curator does it.

**What:** *Their work* on the Artist page and the results page's Wikidata works
gain a tick box on every work the library does not hold, and a *Get N works*
control (`core/getting.js`) that posts the ticked items and says what started,
what was left out, and links the run. A work's own page offers *Get this work* in
place of *Search museums for this work*; that page's test is replaced, not
weakened (`test_it_offers_get_rather_than_a_museum_search`). Queue and History
list a Get as *Get* with *Works you chose*, the run screen words it as one, and
Review heads it *Get*, goes back to *← The Get*, and links each chosen work's
item. `replaceChildren` wrote a `null` argument as the word "null", which the
Artist page printed above an artist with no description: every screen now goes
through `fill` in `core/render.js`, and `test_client_vocabulary.py` refuses a
direct call. Two Artist-page tests now read the work from the second column.

## 2026-10-02: Get: works chosen by their Wikidata items, over HTTP and MCP

<!-- prawduct: scope=get-and-ask -->

**Why:** ruling 3 dissolves Add New into *Get*, an action on a selection. A
curator who has found works in Wikidata needs to acquire those works, not to
describe them to a model and hope it names them.

**What:** a run of the new kind `get` holds one `chosen` candidate per item, each
carrying its `wikidata_qid`, and starts at phase 2: no phase 1, no approval, no
spend, and no supplement. The item reaches the image sources, so Commons answers
it. `POST /api/gets {qids}` and `art_discovery(action='get')` start one through
`GetService`, which skips items the library holds, items a Get under way is
looking for, and items Wikidata does not have, and reports each skip. Accepting a
chosen work stores its item on the artwork, set by the curator. The review grid
labels a chosen work *◇ you chose*, and the provenance guard now holds a word and
a glyph per provenance. `data-model.md` and `api-contract.md` carry the kind, the
provenance, the column and the route.

## 2026-10-02: Commons is an image source, reached from a work's Wikidata item

<!-- prawduct: scope=get-and-ask -->

**Why:** the owner ruled Commons first and the Art Institute second in the
image-source pool. A work chosen from Wikidata usually has an image there, and
the Art Institute holds only its own collection.

**What:** `library/discovery/commons.py` answers a query that names a Wikidata
item: it reads the item's image through the registry, asks Commons for the file's
size, type and rights, and offers the original when it is no wider than 3840 px
and Commons' 3840 px rendering otherwise, at the size that will arrive. It is
wired, first in the pool, whenever `WIKIDATA_USER_AGENT` is set. Measured first
over the catalogue's artists (`wikidata-findings.md` § Commons): coverage follows
copyright. `data-model.md`'s deferred canonicity paragraph is reopened. The
startup line's image sources are now tested, and a live test keeps the 3840
limit checked.

## 2026-10-02: Phase 2 asks a pool of image sources at once

<!-- prawduct: scope=get-and-ask -->

**Why:** the owner asked for a pool of image sources, with none special-cased,
searched in parallel and open to more. Until now phase 2 was wired to one
museum, so a second source would have been a change to the runner, the preview
cache and the tile wiring.

**What:** `library/discovery/pool.py` asks every wired source at once and keeps
a source that could not be asked apart from one that holds nothing. Phase 2
settles a work only on an instance that clears the floor while any source was
down; otherwise the work stays pending, as when no source answers. Rank ties go
to the source listed first. Previews and tiles are routed back to the source an
instance was recorded under, so `PreviewCache` now takes the source's name with
the URL. `ImageQuery` carries an optional Wikidata item for sources that can use
one. The container takes `image_sources`, a list, and the startup line names the
sources wired (`phase2 image_sources=`). The Art Institute is the only source
for now.

## 2026-10-02: The cumulative review of one-world search, resolved

<!-- prawduct: scope=one-world-search -->

**Why:** the cumulative review found that the rules on a curator's Wikidata item
lived only in the browser. An agent's `set_artist_qid` could give a second artist
the same item, and every page that finds an artist by QID would then silently
show one of the two.

**What:** the identity service now refuses an artist's QID another catalogue
artist carries, and checks that an item exists on Wikidata through a new
one-query `label_of`. Both hold over HTTP and MCP. The matcher reports a second
artist matching a taken item as ambiguous. `artist_ids_by_qid` resolves any
older duplicate to the first by name. The review's warnings, fixed:
- a work's maker the library holds links there in search, though the name search did not find them;
- Wikidata's name search is ranked by renown (the sort key has to be selected, or the service ignores the order);
- unpressed view buttons say `aria-pressed="false"`;
- the page of an artist not held says where held work is filed rather than claiming none;
- one `stateMark` draws ● / ◐ / ○ everywhere;
- live tests cover the new queries;
- the server's registry gives up after 20 s, not the matcher's 60;
- the registry services share one bounded memory, note and QID check (`library/services/remembered.py`).

## 2026-10-01: Similar artists, and setting a Wikidata item by hand

<!-- prawduct: scope=one-world-search -->

**Why:** ruling 4 asks for the full Artist hub, and *Similar artists* was the
piece left. Ruling 7's identities had routes to correct them and no control, so
the only way to fix a wrong *Held* mark was an MCP action.

**What:** *Similar artists* on every Artist page, held or by QID, from
`GET /api/registry/artists/{qid}/similar`. It lists up to twelve visual artists
sharing a movement, by renown, each with how many of their works have an image,
and ● where the library holds them. It is asked after the page is drawn and
remembered per artist. The registry gains `similar_to`. Under a held artist's
name and on a held work's page, a new control shows the Wikidata item and who set
it. *Change…* looks a new item up and says what it is before *Use* can store it.
It refuses an item another artist in the library already has, and warns of a
duplicate work. *There is none* is confirmed first. The results page's
failed-search test now asserts the library's own message.

## 2026-10-01: A results page for everything a search finds

<!-- prawduct: scope=one-world-search -->

**Why:** ruling 2, one world. The dropdown shows a few of each kind; a curator
reading what exists needs the whole list. The owner kept Enter on Artworks on
2026-10-01, so the page is reached from the dropdown's new last row.

**What:** `#search?q=` (served at `/search` too), a contextual page. The library's
artists and works are drawn first, then Wikidata's that are not already shown,
each marked ● *In your library*, ◐ *Image found* or ○ *Not held*. *All*, *In your
library* and *Not held* narrow it, and only the first and last ask Wikidata. When
the words name exactly one artist, that artist leads as the top result. When
Wikidata has nothing, the page says so and offers *Search museums* (filled in,
not started). The library's matches open in Artworks from a link. The registry
search gains `wide` for the page's longer lists. The dropdown's last row, *All
results for "…"*, opens it. Seven assertions in two typeahead tests now expect
that row, one of them rewritten to count the library group directly. The screen
tables, `SCREEN_NAMES` and the Contextual sentence carry the new screen.

## 2026-10-01: The search box covers Wikidata too

<!-- prawduct: scope=one-world-search -->

**Why:** ruling 2, one world: typing an artist or a title should show what the
library holds and what exists, each with its state, in one place.

**What:** below the library's rows, the typeahead adds *Themes* (by name),
*Wikidata: artists* and *Wikidata: works*. These are fetched from a new
`GET /api/registry/search` from the third letter, after the library's rows are
drawn. They say *in your library* or *Image found*, leave out what the library's
rows already show, and open the library's page or the page by QID. Their
arrival is announced in a polite live region and keeps the highlight where it
was. Wikidata off or down is said in its own note, apart from the library's. The
registry gains `works_matching`: a full-text search filtered in the search index
to ten artwork classes and capped at 50 hits, which keeps TV series and comics
out and answers in about half a second (measured; the alternatives took up to a
minute). Typed text reaches it only as words. A new search service asks for
artists and works at once and remembers each query. The by-QID artist route now
answers a held artist without asking Wikidata. Every registry name comes from
the label service. That fixed makers named two ways, and the Artist page's
movements, which had the same `en`-only filter as Rothko's name. Tests were
watched failing under mutations of the client, the service and the registry.

## 2026-10-01: Pages for works and artists the library does not hold

<!-- prawduct: scope=one-world-search -->

**Why:** ruling 2 puts the library and the registry in one world. Until now a
work Wikidata lists was only a link out to wikidata.org, and an artist the
library does not hold had no page at all.

**What:** `#work/Q…` and `#artist/Q…`, read through two new routes,
`GET /api/registry/works/{qid}` and `GET /api/registry/artists/{qid}`. A work
not held shows its picture or none, its creators, date, media, and each holder
with its own number there. It offers *Search museums for this work* (Add New,
filled in and not started) until *Get* exists, and lists the rest of its
artist's work. An artist not held shows Wikidata's half and says nothing of
theirs is held. A QID the library holds is replaced by the library's own page
through a new router `redirect`, so Back skips it. Titles in *Their work* now
open these pages instead of wikidata.org. The registry gains `work(qid)` (one
query, its rows read back into sets, inventory numbers paired with their
collection) and the artist's name and dates. Each answer is remembered per QID.
`people_named` asks for language-neutral labels too, which fixes Mark Rothko
coming back as `Q160149`. `creators_of` keeps only items it was asked about.
The registry-string test now derives its kinds from the seam. The *Held ×2*
browser test asserts which work opened, as the last plan's review asked. Found
on a phone against a copy of the catalogue and fixed: the shared table helper
scrolls inside its panel, because a source URL made the whole Work page 333 px
wider than the screen. Integration and browser tests were each watched failing
under mutations of the code they cover.

## 2026-10-01: Outside text reaches the page as text, by norm

<!-- prawduct: scope=one-world-search -->

**Why:** one-world search puts Wikidata's words into the typeahead, the second
page to show registry text. The first, the Artist page, was bounded only by its
own tests. The owner ratified the norm as written, so every page after is bound
by a rule, not by someone remembering one page.

**What:** `security-model.md` gains a § Direction: text from a registry, a
museum or a model is never parsed as markup, and an outside image or link is
used only from a named host or built from a checked id. Its row in the norm
index names five tests. `tests/preferences/test_external_text.py` reads every
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

<!-- prawduct: scope=ia-foundations -->

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

<!-- prawduct: scope=ia-foundations -->

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

<!-- prawduct: scope=ia-foundations -->

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

<!-- prawduct: scope=ia-foundations -->

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
