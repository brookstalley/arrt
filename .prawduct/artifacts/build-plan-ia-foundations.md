---
artifact: build-plan
version: 1
scope: ia-foundations
branch: feature/ia-foundations
partition: serial — Chunks 01, 02 and 03 each change `arrt/src/arrt/persistence/sqlite.py` (the works query, the themes table, the artists and artworks tables), and Chunk 04 is built on Chunk 03's identities
depends_on:
  - artifact: ia-proposal
  - artifact: user-scenarios
  - artifact: information-architecture
  - artifact: data-model
  - artifact: architecture
governed_by:
  - artifact: architecture
    dispositions:
      - "the Library/Programming seam, rule 1, one-way imports through the facade (in-transition, `tests/preferences/test_seam_imports.py`) → binds Chunk 02: the Library never imports Programming"
      - "rule 3, no new cross-seam foreign keys (interim rule until wave 3) → conforms: the default theme's members are `theme_memberships` rows, an existing reference, and the QID columns are on Library tables only"
      - "rule 4, Library changes reach Programming as events (`arrt/src/arrt/library/events.py`, `arrt/tests/unit/test_library_events.py`, `test_reconciliation.py`) → binds Chunk 02: the join is a Programming subscriber to the existing `work.accepted` event, and startup reconciliation must not re-add a work the curator removed from the default theme"
      - "operation logic lives only in the service layer; a binding may compose calls but not branch on one to choose the next → binds Chunks 02-04: the join, the matcher and the Artist page's assembly are services, and the HTTP and MCP bindings stay thin"
  - artifact: data-model
    dispositions:
      - "identity is never a source URL → conforms: Chunk 03 stores the QID itself (`Q160149`), never a Wikidata URL"
      - "a work is distinct from an image of it → conforms: the QID identifies a work, and *Image found* on the Artist page names an image of it without becoming one"
      - "a persisted format is a lock-in decision whose consumers' queries are its requirements (§ What this data must answer) → binds Chunks 02 and 03: each enumerates its questions above, and they become Q-rows in `data-model.md` before the fields are fixed"
  - artifact: api-contract
    dispositions:
      - "adding a field to a result is additive; changing an MCP tool's description is breaking (§ Versioning rules) → binds Chunks 02 and 03: the default mark and the QID are added fields; existing tool descriptions are not edited. Setting a QID by hand is a new tool or action, documented as new"
  - artifact: information-architecture
    dispositions:
      - "the curation surface is laid out like the *arr apps (§ Direction, with ruled departures) → conforms: Library › Artists follows Lidarr's artist index, which is that app's Library; no new section"
      - "one row per screen in the three tables, held by `tests/preferences/test_screen_tables.py` → binds Chunk 04"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA on the curation browser; colour never the sole carrier of state → binds Chunks 02 and 04: the default mark, *Held* and *Image found* each carry glyph, word and colour"
  - artifact: design-direction
    dispositions:
      - "the stylesheet holds token values, and `arrt/tests/unit/test_design_tokens.py` refuses a colour outside the token blocks → binds Chunks 02 and 04: any new colour is a token covered by that test in the same commit"
  - artifact: security-model
    dispositions:
      - "outbound fetches go to publicly routable addresses only, checked on each redirect hop, and hosts are deliberately not allowlisted → binds Chunk 03: the Wikidata client uses the same guarded fetch the museum clients use. (Corrected while building, 2026-10-01: that guard is for source URLs, which are attacker-influenceable; the museum API clients talk to fixed hosts and do not use it. The Wikidata client's endpoint is a constant, so there is nothing to check, and it follows no redirect at all, which is the stricter half of the norm. Tested in `tests/unit/test_wikidata_client.py`.)"
      - "no norm covers rendering untrusted external text in the browser → gap, recorded rather than assumed: Chunk 04 renders registry text as text (never as HTML), and the Critic reviews it. A norm for it is owed to `security-model.md` and is not written by this plan"
  - artifact: observability-strategy
    dispositions:
      - "what the museum is told about us: a configured User-Agent with no default, and the feature off when unset (§ What the museum is told about us) → binds Chunk 03: Wikidata is told the same, and registry features say they are off when it is unset"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider → inapplicable because Wikidata lookups are free and spend nothing"
      - "the display plane never depends on the curation plane being reachable → inapplicable because nothing here touches the Player or the manifest"
last_validated: null
---

# Build Plan — IA foundations: accents, the default theme, registry identity, the Artist page

## What this plan is

The owner ruled nine decisions on 2026-10-01 (`ia-proposal.md` § Rulings), on an
IA derived from `user-scenarios.md`. Together they are a **program**, more than one
plan should carry (`methodology/planning.md`, Plan Shape). This plan is its first
wave: the pieces that stand on their own or that everything after needs.

| Chunk | What | Ruling |
|---|---|---|
| 01 | Library search ignores accents, so `dali` finds Dalí | The defect in `user-scenarios.md` § What the search box can mean |
| 02 | *All works* is the default theme, and ordinary acceptances join it | 8 (and 5a) |
| 03 | Works and artists carry a Wikidata QID where one exists | 7 |
| 04 | The Artist page and Library › Artists | 4, in part |

**What comes after**, each its own plan when it starts, in this order:

1. **One-world search, and the rest of the hub.** Typeahead and results show
   library and registry matches with their states (ruling 2). A Work page exists
   for works not held. The Artist page gains *Similar artists*. The Artist and
   Work pages gain a control to set or clear a Wikidata QID by hand: the routes
   exist (`POST /api/works|artists/{id}/wikidata`), and until then the only way
   to correct a *Held* mark is `art_catalogue(action='set_work_qid')`. A norm for
   showing external text in the browser is owed first (`security-model.md` §
   Open).
2. **Get and Ask.** Add New is dissolved (ruling 3): *Get* acts on any selection
   and seeds a run with the chosen works. The conversation becomes *Ask*, under
   Library. Activity gains *To review*, which needs the unjudged-candidate count
   `information-architecture.md` § The *arr layout records as owed, and *Wanted*.
3. **Topics and destinations.** Topic pages (period, movement, subject, medium),
   and a destination on every Get, *All works* by default or any other theme,
   whose acceptances join that theme and not the default (5a). What a
   destination means for taste (5b) moved to plan 4. *(Renamed from "Topics and
   excursions" by the owner's rulings of 2026-10-02:
   `build-plan-topics-and-destinations.md` § The owner's rulings.)*
4. **Taste that is read.** Ask and Similar artists read affinities (the brief's
   unbuilt promise, `user-scenarios.md` § Tested).
5. **Walls.** The page leads with what each wall shows. Archive a selection, *Not
   this one again*, and wall history. Hanging for a duration waits for wave 4
   (ruling 6).

## What I would do differently

- **Ship Chunk 01 on its own, first.** It is a defect fix with no dependency on
  the rest and the owner's own first search hit it. It can merge in a day and
  stop being wrong while the rest is built.
- **Measure match quality before committing the Artist page to it.** Chunk 03
  starts by matching the library's 40 works and their artists against Wikidata
  and reporting the rate. If works match poorly, Chunk 04 still ships, and its
  *Their work* list marks *Held* only where a QID says so. It does not fall back
  to title matching, which is what "Untitled" breaks.
- **The order departs from `re-architecture.md` § Order of work**, where wave 3
  (the server to the NAS) is next. Recorded as a DECISION below.

## Requirements Confidence

**Medium.** The rulings settle what to build. Three things are inferred rather
than ruled, and one is unmeasured:

- `[DECISION: build this plan before wave 3 | the owner directed it on 2026-10-01 ("write build plan… start with a new session to build"). Its cost to wave 3: the store split that wave starts with carries a QID column on each of two Library tables and a designation on a Programming table. None crosses the seam, so rule 3's opaque references are unaffected | user can veto/override]`
- `[ASSUMPTION: the default theme is designated by a stored mark on one theme, at most one at a time (a partial unique index enforces at most one, and the owner's All works is designated by migration so there is exactly one in practice); the default can be renamed and cannot be deleted while it is the default | MED impact | user can correct]`
- `[ASSUMPTION: until a Get can name a destination (plan 3 of § What comes after), every acceptance joins the default theme | LOW impact | user can correct]` *(Superseded 2026-10-02: a Get names its destination, `build-plan-topics-and-destinations.md` Chunk 01.)*
- `[ASSUMPTION: a QID is stored only on an unambiguous match, because a wrong QID marks the wrong work Held and is worse than none. Ambiguous and unmatched works keep no QID and stay matchable later | HIGH impact | user can correct]`
- `[ASSUMPTION: Wikidata is the only registry this plan reads. Getty ULAN is reachable from a Wikidata artist (property P245) when something needs it | LOW impact | user can correct]`
- `[DECISION: the Artist page ships with header, In your library, Their work and Holdings; Similar artists moves to the next plan | ruling 4 asks for the full hub. Similar artists depends on registry links and on Ask's suggestions, both of which the next plans build, and the chunk is the size of one Critic pass without it. Not dropped: § What comes after, plan 1 | user can veto/override]`
- **Unmeasured:** how many of the 40 works and their artists match a QID
  unambiguously. Chunk 03 measures it first.

**What would raise it:** Chunk 03's match rate, and the owner reading the
assumptions above.

## Status

- [x] Chunk 01: Library search ignores accents
- [x] Chunk 02: All works is the default theme
- [x] Chunk 03: Works and artists carry a Wikidata QID
- [x] Chunk 04: The Artist page and Library › Artists

### Chunk 01: Library search ignores accents

`GET /api/works?q=` matches with SQLite `LIKE` over the searched columns
(`arrt/src/arrt/persistence/sqlite.py`, the `_SEARCHED` clause). `LIKE` ignores case
for ASCII letters only and never ignores accents, so `dali`, `miro` and `rene`
find nothing in a library that holds Dalí, Miró and Magritte (measured
2026-10-01, `user-scenarios.md`). Fold both sides: the stored text and the query
term, to one form that drops combining marks and case.

`arrt/src/arrt/library/discovery/dedup.py` already decomposes with
`unicodedata.normalize("NFKD", …)`. Read what else it strips before reusing it:
a dedup key may also drop punctuation or words that a search must keep. Every
surface that searches the library goes through the same fold: the HTTP route,
its MCP twin, and the top-bar typeahead, which calls the route.

**Done when:**
1. A test with Dalí, Miró and René Magritte in the library finds each by the
   unaccented spelling and by the accented one, and finds nothing for a name not
   there. It is watched failing against today's code first.
2. A non-Latin name and a name with a ligature or a German ß are in the fixture,
   so the fold is tested on more than one kind of mark.
3. The facet counts and the theme filter agree with the folded search (the same
   query, narrowed), tested through the route, not the store.
   *(Built: the facet half. The theme half does not apply: a theme and a search
   cannot both narrow Library › Works, because a theme's works come from
   `GET /api/themes/{id}` and neither route can express the other's narrowing, so
   the screen lets the search win and says so (`themeIsShowing` in
   `arrt/src/arrt/http/static/screens/collection.js`). Found while building,
   2026-10-01.)*
4. The curation, browser and root suites pass.

### Chunk 02: All works is the default theme

**Visual change:** yes

Ruling 8: *"There should be a default 'all works' theme."* A work accepted from a
Get joins it. Today nothing adds a work to a theme automatically: the only
callers of `add_to_theme` are the HTTP route and its MCP twin (measured
2026-10-01).

**The seam decides where the join happens.** Acceptance is the Library's
(`arrt/src/arrt/library/services/discovery.py`, `_accept`), themes are
Programming's, and the Library never reaches Programming. Seam rule 4 says
Library changes reach Programming as events, and the event exists:
`work.accepted` in `arrt/src/arrt/library/events.py`, published after the change
commits, with a failed subscriber caught up by reconciliation at the next start.
**The join is a Programming subscriber to `work.accepted`.** Two traps to test:

- **Reconciliation must not undo the curator.** A work removed from the default
  theme by hand must not be re-added at the next start. Whatever records "this
  work has been offered to the default theme" is part of this chunk's persisted
  format.
- **Restore may publish the same event.** Read what `restore` publishes. Whether
  a restored work rejoins the default theme is a question for the owner, raised
  in the chunk rather than decided silently.
  *(Read 2026-10-01: `restore_artwork` publishes `work.accepted`, the same event
  as a new work, and every `add_artwork` publishes it, seed ingest and manual
  adds included. Archiving leaves theme memberships alone.)*
  `[ASSUMPTION: a work is offered to the default theme once, the first time the
  Library announces it, and never again: a restored work does not rejoin, so a
  removal by hand stands. Every way in counts as an acceptance, not only a Get |
  MED impact | recommended to the owner 2026-10-01, who said "keep going"
  without ruling; user can correct]`

**A persisted designation**, so the questions it must answer come first:

- Which theme is the default, if any? (Programming, the Theme screen, MCP)
- Can there be two? (No: at most one, enforced by the store, not by convention.)
- Does an acceptance join it, and which acceptances do not? (All, until plan 3's
  destinations: 2026-10-02, an acceptance from a Get that named another theme
  joins that theme instead.)
- Has this work already been offered to it? (So reconciliation never re-adds a
  work the curator removed.)
- What happens when the default theme is deleted or renamed? (Delete refused
  while it is the default; rename allowed.)
- Is the owner's existing *All works* the default after migration? (Yes, by name,
  once. A catalogue with no theme of that name gets none, and the Theme screen
  offers to make one the default.)

`data-model.md` is amended with the field and these answers. The Theme screen and
Library › Themes mark the default theme with glyph, word and colour.

**Done when:**
1. Accepting a work through the HTTP verdict route and through the MCP verdict
   tool each adds it to the default theme at the end of its order, by way of the
   `work.accepted` subscriber. Tested through
   both surfaces, not the service, with a second theme in the fixture that must
   *not* gain the work.
2. With no default theme, acceptance still succeeds and joins nothing. A work
   removed from the default theme by hand is not re-added by a restart's
   reconciliation.
3. Deleting the default theme is refused with a message naming why; renaming it
   keeps it the default.
4. The migration designates *All works* on a copy of the owner's catalogue shape
   and is idempotent across two runs with different theme sets.
   *(Built, and also run twice on an actual copy of the owner's catalogue on
   2026-10-01: All works marked, 40 of 40 works recorded as offered, its 40
   members untouched.)*
5. The seam guard and the curation, browser and root suites pass.
6. An operator-verification entry covers the default mark on the Theme screen.

### Chunk 03: Works and artists carry a Wikidata QID

Ruling 7. **Read and probe Wikidata before writing a client** (`methodology/
planning.md`, Foreign API Verification): its search endpoint, its query service,
its User-Agent policy, and what a lookup returns for one of the library's works.
Record the findings as new `.prawduct/artifacts/wikidata-findings.md`, as the
other foreign APIs have theirs.

**A persisted format.** Its questions:

- Is this registry result a work the library holds? (Search and the Artist page
  in later plans: match by QID.)
- Which registry artist is this library artist? (The Artist page's header and
  *Their work*.)
- Which held works and artists have no QID yet? (A later matching pass.)
- How was a QID set, and can it be trusted? (Matched automatically and
  unambiguously, or set by the curator; a correction must be possible.)

**Measure first:** match the library's 40 works and their artists, and report how
many matched unambiguously, how many were ambiguous and how many found nothing,
with the query used. That number goes in the findings file and decides Chunk 04's
reliance on it (§ What I would do differently).

Then: the columns, the matcher (unambiguous only), a backfill the owner can run
against their catalogue, the QID on the works and artists the API and MCP return,
and a way to set or clear a QID by hand. `data-model.md` and `api-contract.md`
are amended, the latter under its versioning rule for an added field.

**Done when:**
1. The findings file records the probe and the match rate, measured against the
   owner's catalogue.
2. Matcher tests include an ambiguous title ("Untitled") by an artist with
   several, which must store nothing, and a work whose artist matches and title
   does not.
3. The backfill is idempotent and never overwrites a QID set by hand.
4. A `live_museum`-style marked test checks the Wikidata contract the client
   relies on, deselected by default, run by hand with `-n0`.
5. The curation and root suites pass.

*(Built 2026-10-01. The measurement changed the design: works match **only by the
holding museum's identifier** (Art Institute `P4610`, Google Arts & Culture
`P4701`), never by title, because every title match agreed with an identifier
match and added none, while generic titles were ambiguous. Artists match by
their matched works' creator, else by name plus agreeing life dates; a name
alone matched the culture *Moche* to a 17th-century painter. Run on a copy of
the owner's catalogue: 22 of 40 works, 24 of 31 artists, nothing ambiguous;
`wikidata-findings.md` has the rest. Done-when 2's "ambiguous Untitled" is
tested as two Untitled works each matched by their own identifier, and one with
no identifier storing nothing. Matching is a hand-run command,
`python -m arrt.identify`, which needs `WIKIDATA_USER_AGENT`; a work
accepted later has no QID until it is run again.)*

### Chunk 04: The Artist page and Library › Artists

**Type:** cumulative-final
**Visual change:** yes

Ruling 4, in part (the DECISION above). Library › **Artists** lists the artists
the library holds, with counts. An **Artist** page has:

- **Header:** name, life dates, nationality from the library; movements and a
  short description from Wikidata where the artist has a QID. Taste controls
  (*More like this*, *Not for me*) write an artist affinity through the existing
  taste service.
- **In your library:** the held works, with Hang and Add to theme on a
  selection, as Library › Works does.
  *(Corrected while building, 2026-10-01: Library › Works offers Add to theme
  on a selection and nothing hangs a selection anywhere; ruling 6 defers
  hanging a selection to wave 4. So the page offers Add to theme, sharing
  Works' logic through `arrt/src/arrt/http/static/core/membership.js`. Not a descope: there was no Hang
  to match.)*
- **Their work:** works Wikidata lists for the artist, sorted by renown (sitelink
  count), each marked *Held* (by QID) or with *Image found* where Wikidata has a
  free image. Read-only in this plan: *Get* arrives with plan 2.
- **Holdings:** collections holding their work, with counts.

The page's address is the library artist's own, with the QID beside it, so it
works for every held artist whether or not a QID matched. Artist names on Library
› Works, the Work page and the top-bar typeahead link to it. Registry content is
untrusted text and is rendered as text. A registry failure leaves the header and
*In your library* working and says what is missing.

**Done when:**
1. Browser tests, watched failing first: the index lists held artists with
   counts; the page shows held works; *Their work* marks a held work *Held* and
   an unheld one not; a registry failure degrades as stated; the taste controls
   write an affinity.
2. Every Screen States row for both pages is written (empty, loading, error) in
   `information-architecture.md`, with their rows in the three tables and in
   `SCREEN_NAMES` (`tests/preferences/test_screen_tables.py`).
3. Rothko and Dalí are checked in the running app against the owner's catalogue,
   with screenshots at desktop width and 375px in an operator-verification
   entry.
4. All three suites and the browser suite pass, then the cumulative review.

*(Built 2026-10-01. Running it on a copy of the owner's catalogue changed one
thing the tests had passed: none of the owner's held works is among its
artist's 50 most renowned, so *Held* marked nothing. The page now asks for the
held works by QID too, and the fixtures were changed to put the held work
outside the top list, so the test can fail. Also found there: registry items
with no readable title, now shown as *No English title (Q…)*, and a table too
wide for a phone. The typeahead gained an Artists group, which changed the
option lists two earlier tests pinned. Registry text is rendered as text, and a
browser test feeds the page markup to prove it. Similar artists is the next
plan's, per the DECISION above.)*

## Governance checkpoints

- **After Chunk 03**, read its match rate against Chunk 04's design before
  building the page.
  *(Read 2026-10-01. The design stands, with three consequences for Chunk 04.
  **Held** works: 22 of 40 works carry a QID, including both Rothkos and the
  Dalí, so the two pages the operator checks mark their held works. **Image
  found** is almost empty for in-copyright artists (Rothko 1 of 1,276, Dalí 13
  of 1,178), because a Wikidata image is a Commons file; the page must not
  promise pictures for them, and *what does it look like?* for those artists
  stays with the museum previews later plans bring. **Their work** runs to
  thousands of items and 1 to 6 seconds a query, so it is capped by sitelinks,
  says how many more there are, is fetched by its own request after the page
  paints, and is remembered per artist for the life of the process. An artist
  with no QID (7 of 31) shows header and *In your library* only, and says the
  registry knows nothing for them yet.)*
- **Before the PR**, the cumulative review in Chunk 04.

## Verification strategy

The browser suite drives the real client against a booted server. Beyond it,
each visual chunk runs Arrt against the owner's local catalogue (`cd arrt && uv
run python -m arrt`) and is driven with Playwright at desktop width and 375px,
as on 2026-10-01: the searches `dali` and `rothko`, the default theme's mark, and
the Artist pages for Rothko and Dalí. The question for each is the scenario it
serves in `user-scenarios.md`, not whether the page renders.
