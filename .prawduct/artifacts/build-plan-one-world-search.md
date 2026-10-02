---
artifact: build-plan
version: 1
scope: one-world-search
branch: feature/one-world-search
partition: serial — every chunk after 01 edits `arrt/src/arrt/library/registry/wikidata.py`, `arrt/src/arrt/http/api.py` and the Artist or Work screen, and 03 to 05 link to the pages 02 builds
depends_on:
  - artifact: ia-proposal
  - artifact: information-architecture
  - artifact: security-model
  - artifact: wikidata-findings
  - artifact: build-plan-ia-foundations
governed_by:
  - artifact: security-model
    dispositions:
      - "no norm yet covers showing external text in the browser (§ Open, opened 2026-10-01, owed before this plan ships) → Chunk 01 proposes it for the owner to ratify, and Chunks 02-05 are bound by it"
      - "outbound fetches: the registry client talks to one constant endpoint and follows no redirect → binds Chunks 02, 03 and 05: every new query goes through the same `_select`, and no new endpoint is added"
  - artifact: information-architecture
    dispositions:
      - "the curation surface is laid out like the *arr apps (§ Direction) → conforms: no new section; the results page is a contextual page, as Sonarr's search results are"
      - "Enter opens Artworks filtered to the query (owner, 2026-09-30) against the proposal's results page (§ Search, the target since 2026-10-01) → ruled by the owner 2026-10-01: Enter stays on Artworks; the results page is reached from the dropdown's last row (Chunk 04)"
      - "one row per screen in the three tables, held by `tests/preferences/test_screen_tables.py` → binds Chunks 02 and 04"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA; colour never the sole carrier of state → binds Chunks 02-05: *Held*, *Image found* and *Not held* each carry glyph, word and colour, in the typeahead as on the Artist page; registry rows that arrive late are announced in a polite live region the typeahead gains (it has none today), not by moving focus"
  - artifact: design-direction
    dispositions:
      - "token values only, held by `arrt/tests/unit/test_design_tokens.py` → binds Chunks 02-05"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer → binds Chunks 02-05: search, the work view and similar artists are services; the HTTP bindings stay thin"
      - "the Library never imports Programming (`tests/preferences/test_seam_imports.py`) → binds Chunks 02-05: registry search and the work view live under `library/`"
  - artifact: observability-strategy
    dispositions:
      - "registry features say they are off when no User-Agent is configured → binds Chunks 03-05: the typeahead and results page show the library half alone and say Wikidata is off"
  - artifact: nonfunctional-requirements
    dispositions:
      - "nothing spends on a keystroke (builder's ruling, `information-architecture.md` § The *arr layout) → conforms: Wikidata is free, and a registry search is debounced and cached, so typing does not query per keystroke"
last_validated: null
---

# Build Plan — One-world search, and the rest of the Artist hub

## What this plan is

Plan 1 of `build-plan-ia-foundations.md` § What comes after. Ruling 2 says search
covers one world, library and registry together, each match with its state.
Ruling 4 asks for the full Artist hub, and that plan shipped all of it except
*Similar artists*. Today a registry work is only a link out to wikidata.org.
After this plan it has a page here.

| Chunk | What | Ruling or debt |
|---|---|---|
| 01 | A norm: external text is shown as text, and an external URL is used only from a stated host | `security-model.md` § Open, owed before this plan ships |
| 02 | A Work page and an Artist page for things the library does not hold, addressed by QID | 2, 4 |
| 03 | The typeahead adds Wikidata's artists and works, each with its state | 2 |
| 04 | The search results page | 2; see the open question |
| 05 | *Similar artists* on the Artist page, and setting or clearing a QID by hand | 4; the QID routes exist with no control |

**Not in this plan**, each in the plan that ruling 3 or 4 assigns it:
- **Get**: plan 2. Until then an unheld work's page offers the existing museum search, seeded with its title and artist (a DECISION below).
- **Ask**, including Similar artists "from Ask" and the results page's "nothing here, ask instead": plan 2.
- **Topics** in search and on pages: plan 3.
- Similar artists ranked by **taste**: plan 4.

## What I would do differently

- **Settle Enter before Chunk 04, or cut Chunk 04.** *(Settled 2026-10-01, below.)* The typeahead (Chunk 03)
  already gives one world. A results page is what Enter opens, and the owner has
  ruled Enter twice in effect, in two directions (the open question below).
  If the answer is "keep Enter on Artworks", Chunk 04 shrinks to one dropdown
  row, *All results for "{query}"*. I would take that, because it keeps a ruled
  behaviour and costs a page less.
- **Use full-text search for works, not the prefix search artists use.** The
  probe (`wikidata-findings.md` § Searching for works) found the prefix search
  misses *The Persistence of Memory* and *The Hunters in the Snow* unless "The"
  is typed. Full text finds them, but lets in TV series and comics, so it needs
  a filter whose cost is measured in Chunk 03, before the typeahead is built on
  it.
- **Rank Similar artists by fame first, shared movements second.** The obvious
  ranking, by number of shared movements, put four painters most people have
  not heard of ahead of Picasso for van Gogh.

## Requirements Confidence

**Medium.** The rulings and the owner's two answers of 2026-10-01 settle what to build;
the registry's behaviour is measured for three queries, not proven.

- **Ruled by the owner 2026-10-01: Enter stays on Artworks**, and the dropdown's last row, *All results for "{query}"*, opens the results page. The question as put: what Enter does. On 2026-09-30 the owner ruled *"yes to filtered to the query"*: Enter opens Artworks filtered, departing from Sonarr. The proposal the owner ruled on 2026-10-01 says Enter opens a results page with *All*, *In your library* and *Not held*. Ruling 2 ("one world") ruled the scope, not the key. Built today: Enter opens `#collection?q=` (`arrt/src/arrt/http/static/core/search.js`, `installSearch`). Recommended: **keep Enter as ruled, and add *All results for "{query}"* as the dropdown's last row**, opening the results page.
- `[NORM, ratified by the owner as written 2026-10-01, written into `security-model.md` by Chunk 01: "Text from outside Arrt (a registry, a museum, a model) reaches the page as text and is never parsed as markup. An image or link from outside is used only when its host is one this repository names, or is built here from a checked identifier." | HIGH impact | user can amend or reject]`
- `[DECISION: an unheld work's page offers *Search museums for this work*, which opens the existing Add New with the work's title and artist filled in and spends nothing until the curator presses Search | ruling 3 dissolves Add New into Get, which is plan 2. Showing no action until then would make the page a dead end, and the seeded search is the one way to acquire a work that exists today. Plan 2 replaces it | user can veto/override]`
- `[ASSUMPTION: registry rows in the typeahead come after the library's, start at three typed characters, are asked at the typeahead's existing 200 ms pause after the last keystroke, show at most 3 artists and 5 works, and are remembered per folded query for the life of the process | MED impact | user can correct]`
- `[ASSUMPTION: an Artist page for an artist the library does not hold shows what the registry knows (header, Their work, Holdings, Similar artists) and says that nothing of theirs is held. The address is `#artist/Q…`; a held artist keeps `#artist/{id}` | LOW impact | user can correct]`
- `[ASSUMPTION: Similar artists shows 12, people sharing a movement (`P135`), visual artists only, ranked by sitelinks, each with its count of works that have an image. Influence links are too sparse to rank and are left out | MED impact | user can correct]`
- `[ASSUMPTION: the QID control offers Set (a QID, checked against Wikidata before it is stored, so a typo cannot mark the wrong work *Held*) and *There is none* (stops the matcher, as the routes already do). Handing an item back to the matcher has no route and is not added | MED impact | user can correct]`
- `[ASSUMPTION: the typeahead gains a Themes group (library-only, matched by name), because § Search lists it and it costs no query | LOW impact | user can correct]`

**What would raise it:** Chunk 03's measurement of the filtered full-text search.

## Status

- [x] Chunk 01: External text is shown as text
- [x] Chunk 02: Pages for works and artists the library does not hold
- [ ] Chunk 03: The typeahead shows one world
- [ ] Chunk 04: The search results page
- [ ] Chunk 05: Similar artists, and setting a QID by hand

### Chunk 01: External text is shown as text

The Artist page keeps registry text out of markup by its own tests
(`security-model.md` § Registry text). This chunk turns that into a norm, so
Chunks 02-05 and every page after them are bound by a rule, not by someone
remembering one page.

- The norm above goes into `security-model.md` as a `## Direction` section, with
  its *why*. The owner ratified it as written on 2026-10-01.
- A row for it in `project-preferences.md` § Enforcement, naming its mechanism.
- **The mechanism**, a test in `tests/preferences/` that reads every script
  under `arrt/src/arrt/http/static/` and refuses the sinks that parse
  markup: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`,
  `eval` and `new Function`. Today the client uses none of them (all six
  searched for under `arrt/src/arrt/http/static/` on 2026-10-01), so the test passes now and turns red on the first one added.
- **The URL half:** a unit test drives every URL field the registry API
  returns through the client's host check (`_commons_file` today) with a
  hostile URL, so a new URL field that skips the check fails. What a test cannot
  see (a link built from a string the registry supplied) is left to the Critic
  and says so in the row.

*(Built 2026-10-01. The sink list grew to twelve: `parseFromString`,
`createContextualFragment`, `setHTMLUnsafe`, `parseHTMLUnsafe` and `srcdoc` parse
markup too, and a timer handed a string compiles it; pages are also checked for
inline script. The URL half is built on types
rather than on field names: every string on the registry seam, in its types and in
each question's answer, is now `ItemId`, `RegistryText`, `MuseumIdentifier` or
`CommonsFile`; a test refuses a plain `str`, and a second test answers every
`Registry` method with a stranger's URL in every column and checks
that none reaches a `CommonsFile`, an `ItemId` or a key. `works_by_identifier`
now keeps only identifiers it was asked about. Both derive what they check
from the seam, so Chunks 02-05's new fields and questions fail by name until
they choose a kind and state a call.)*

**Done when:**
1. The sink test is watched failing against a one-line `innerHTML` added to a
   screen, then passing with it removed.
2. The URL test is watched failing with the Commons check bypassed.
3. `security-model.md` § Open's entry is closed in place, pointing to the norm.
4. The root suite and the curation suite pass.

### Chunk 02: Pages for works and artists the library does not hold

**Foreign API:** Wikidata Query Service

- **The registry learns one work.** `work(qid)` returns its title, creators,
  year (`P571`), medium (`P186`), image (`P18`, through the Commons check),
  collection (`P195`) and inventory number (`P217`). One query.
- **The Work page takes a QID.** `#work/Q…` shows one work in every state
  (`ia-proposal.md` § Work). Held, it is the library's own work page, so a QID
  that matches a held work redirects there. Not held, it shows the image found
  or an empty frame at a neutral ratio, its facts, its holder with accession
  number, the DECISION's *Search museums for this work*, and the rest of the
  artist's work below.
- **The Artist page takes a QID.** `#artist/Q…` serves an artist the library
  does not hold: header, *Their work*, *Holdings*. A QID matching a held artist
  redirects to `#artist/{id}`.
- **Registry rows lead here.** *Their work* titles open `#work/Q…` instead of
  linking out to wikidata.org; the wikidata.org link moves to the page itself.
- **`people_named` asks for `mul` labels too.** Live, it names Mark Rothko
  `Q160149`, because his name is no longer an `en` label (`wikidata-findings.md`
  § One work by QID). Nothing shows that label yet; Chunk 03's typeahead would.
  The live test pins Rothko's name, and a unit test pins the label languages.
- **Two observations from Chunk 01's review ride here:** `test_registry_strings.py`
  derives its set of kinds from the `NewType`s the seam module defines, so a new
  kind is named by the quick check; and `creators_of` keeps only the items it was
  asked about, as `works_by_identifier` does.
- **The accepted gap from the last plan closes here:** the *Held ×2* browser
  test asserts which duplicate the badge opens
  (`arrt/tests/browser/test_the_artist_page.py`; accepted on the record at the
  last plan's release review, to be fixed by the next commit touching that test).

*(Built 2026-10-01. The probe found `people_named` naming Rothko by his QID and
fixed it before the typeahead could show it; the matcher's result on a copy of
the catalogue was unchanged at 22 works and 24 artists. Pages addressed by QID
branch on the id's shape, which a library id (a uuid) never has, and the
library's page replaces a held one through a new `redirect` in the router, so
Back skips it. A work with no image found shows a sentence saying so rather than an empty frame: the registry gives no dimensions, so a frame would have a ratio it made up. The shared registry helpers moved to `core/registry.js`. Running it
on the copy at 375 px found the library Work page 333 px wider than the screen,
from a source URL in a table, a defect older than this plan: the shared table
helper now scrolls inside its panel, with a browser test. Also seen there, not
fixed: a museum description's `<i>` shows as literal text, filed to the backlog.)*

**Done when:**
0. verify-api: `work(qid)` is probed live for three works (one held by the owner,
   *The Hunters in the Snow*, and one with no English label), and the shapes
   are written into `wikidata-findings.md` before the fake is built.
1. Browser tests, watched failing first: an unheld work's page shows its state
   and facts; a held QID redirects to the library's work; an unheld artist's
   page; a registry failure says so on both pages and leaves the address
   working; registry markup in a title arrives as text.
2. The Work and Artists rows in all three tables of
   `information-architecture.md` describe the QID-addressed forms, and their
   Screen States rows cover *not found in the registry*.
3. *The Hunters in the Snow* and an unheld Rothko are checked in the running
   app at desktop width and 375px, with an operator-verification entry.
4. All three suites and the browser suite pass.

### Chunk 03: The typeahead shows one world

**Foreign API:** Wikidata Query Service

- **Carried from Chunk 02's review:** `GET /api/registry/artists/{qid}` answers
  with the held artist's id before asking Wikidata, as the work route already
  does, so the redirect never waits on the registry.
- **The registry searches works by title**, full text with `haswbstatement:P170`
  and a filter for works of visual art. Which filter is measured first
  (verify-api), against the six queries in `wikidata-findings.md`: the filter
  must drop *Kojak* and *Power Girl* and keep *The Persistence of Memory*, and
  its time is recorded.
- **One search service** returns registry artists (`people_named`) and works
  together, each marked *Held* (by QID, linking to the library's own record) or
  *Image found* or neither, and is cached per folded query.
- **A route**, `GET /api/registry/search?q=`, with the four states the Artist
  page's registry half already uses (answered, not configured, could not ask,
  nothing found).
- **The typeahead** keeps its library groups as they are and adds *Wikidata:
  artists* and *Wikidata: works* below them when the registry answers, plus the
  Themes group. A held registry match is shown once, as the library's. A slow or
  failed registry never delays or removes the library rows. Late rows are
  announced in a polite live region the typeahead gains; focus does not move.

*(Built 2026-10-01. The filter is the search index's own `haswbstatement` on ten
artwork classes, with `wikibase:limit 50`: both class walks in SPARQL took up to
a minute and kept TV series, and the 44 s for `david` was the query service
paging through every hit, not the search. Typed text is cut into words, so search
syntax never reaches the index. Artists and works are asked on two threads and
remembered per folded query. The by-QID artist route now answers a held artist
without asking Wikidata (carried from Chunk 02's review). Driving it against the
copy of the catalogue found makers named two ways ("Pieter Bruegel" and "Pieter
Brueghel the Elder") because a label filter accepting `en` or `mul` let SAMPLE pick
either. Every name now comes from the label service, the Artist page's movements
included, which had the same `en`-only filter as Rothko's name. A unit test fails
on any language-filtered label. The *Themes* group is in. The typeahead opened
on every one of six driven runs.)*

**Done when:**
0. verify-api: the filter is chosen by measurement, recorded in
   `wikidata-findings.md` with its times and what it drops.
1. Unit tests for the search service (held marking by QID, de-duplication,
   caching, each registry state); browser tests watched failing first: registry
   rows appear after library rows, a held match is not shown twice, the
   registry being off or failing leaves the library half unchanged, arrow keys
   reach registry rows, markup in a registry label arrives as text.
2. Typing `dali`, `the persistence` and `hunters` into the running app, against
   the owner's catalogue, with screenshots in an operator-verification entry.
   Watch for the typeahead failing to open (seen once in Chunk 04 of the last
   plan, not reproduced).
3. `information-architecture.md` § The *arr layout's search bullet describes
   the groups as built.
4. All three suites and the browser suite pass.

### Chunk 04: The search results page

A contextual page, `#search?q=`, with *All*, *In your library* and *Not held* views. Artists
first, then works, each with its state. If the query names one artist, that
artist is the top result. Nothing on the page spends. When the registry has
nothing, the page says so and offers *Search museums* (Ask replaces it in plan
2). Reached by the dropdown's last row, *All results for "{query}"*. Enter still opens Artworks filtered to the query (ruled 2026-09-30, kept 2026-10-01).

**Done when:**
1. The 2026-10-01 answer is recorded in `information-architecture.md`, as a
   ruling, beside the Enter departure.
2. The page has its `SCREEN_NAMES` entry, its rows in the three tables, and its
   place in the Contextual sentence (`tests/preferences/test_screen_tables.py`).
3. Browser tests, watched failing first: each view filters; a single-artist
   query puts the artist first; the registry off or failing shows the library
   half and says why.
4. Checked in the running app at both widths, with an operator-verification
   entry. All suites pass.

### Chunk 05: Similar artists, and setting a QID by hand

**Foreign API:** Wikidata Query Service
**Type:** cumulative-final

- **Similar artists**, per the ASSUMPTION: a registry method, one query, in the
  Artist page's registry half, fetched after the page paints like *Their work*.
  Each row shows the artist's name, dates and works with an image found, and
  opens their page (held or by QID).
- **The QID control** on the Artist and Work pages: shows the QID and who set it
  (matcher or curator), *Change…*, and *There is none*. A new QID is looked up
  before it is stored and the dialog shows what it names, so a typo cannot pass
  as an identity. Calls the routes that exist (`POST
  /api/works|artists/{id}/wikidata`).

**Done when:**
0. verify-api: the similar-artists query with the occupation filter is run for
   Renoir, Rothko, Dalí and van Gogh, and the result is recorded against the
   lists in `wikidata-findings.md`.
1. Browser tests, watched failing first: Similar artists lists and links; a
   registry failure leaves the rest of the page working; Set shows what the QID
   names before storing it; *There is none* clears *Held* marks for that work.
2. Checked on Dalí and Renoir in the running app, with an operator-verification
   entry.
3. All suites pass, then the cumulative review.

## Governance checkpoints

- **After Chunk 02**, check that the QID-addressed pages hold up on the owner's
  catalogue before the typeahead starts sending people to them.
- **Before the PR**, the cumulative review in Chunk 05.

## Verification strategy

As in the last plan: the browser suite drives the real client against a booted
server, and each visual chunk runs Arrt against a copy of the owner's catalogue
with `WIKIDATA_USER_AGENT` set and is driven with Playwright at desktop width
and 375px. The question for each is the scenario it serves in
`user-scenarios.md` (*"show me the Dalís"*, *"what else did Brueghel paint?"*,
*"who's like Rothko?"*), not whether the page renders. Every figure written into
a test or a record is read from the probe output or the catalogue in the same
step, never typed from memory (Q5432 is the reminder, `wikidata-findings.md`).
