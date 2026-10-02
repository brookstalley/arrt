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
