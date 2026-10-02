---
artifact: build-plan
version: 1
scope: get-and-ask
branch: feature/get-and-ask
partition: serial — 01 to 04 all edit the runner and `library/services/discovery.py`, and 04 to 06 all edit `app.js`, the sidebar tests and the screen tables
depends_on:
  - artifact: ia-proposal
  - artifact: information-architecture
  - artifact: build-plan-ia-foundations
  - artifact: build-plan-one-world-search
  - artifact: wikidata-findings
  - artifact: artic-api-findings
governed_by:
  - artifact: information-architecture
    dispositions:
      - "the curation surface is laid out like the *arr apps (§ Direction) → ruled departure (ruling 3, already recorded in § Direction): Add New is dissolved. Ask takes its slot under the library section; To review goes under Activity, where Radarr puts what needs the user (§ The *arr layout's recorded gap). No new top-level section"
      - "one row per screen in the three tables, held by `tests/preferences/test_screen_tables.py` → binds Chunks 05 and 06"
  - artifact: security-model
    dispositions:
      - "outside text reaches the page as text; an outside image or link only from a named host or a checked id (§ Direction) → binds Chunks 02-06: Commons titles, licences and file names are registry text; a Get's previews are served from the preview cache as today"
      - "outbound fetches go through the one-hop checked transport, which checks what a host is, never which host (§ SSRF, deliberately no allowlist) → binds Chunk 02: Commons downloads use the direct-HTTP path and its transport unchanged; Commons metadata uses one constant endpoint and follows no redirect, like the registry client"
  - artifact: data-model
    dispositions:
      - "identity is never a source URL → conforms: a Get's candidate carries the Wikidata item it was asked for, and acceptance stores it on the artwork"
      - "a work is distinct from an image of it, at every stage → conforms: the pool returns instances for one work from many sources, and phase 2 already ranks them and selects one, keeping the rest"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer → binds Chunks 03 and 06: Get and the unjudged count are services; the HTTP route and the MCP action are thin bindings over them"
      - "the Library never imports Programming (`tests/preferences/test_seam_imports.py`) → binds Chunks 01-03: the pool, the Commons source and Get live under `library/`"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider, never by application code → conforms: a Get skips phase 1 and spends nothing; nothing here adds a cap"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA; colour never the sole carrier of state → binds Chunks 04 and 06: a selection's Get control says how many works it will ask for and how many it skips; the To review count is a word and a number, never a number alone"
  - artifact: observability-strategy
    dispositions:
      - "registry features say they are off when no User-Agent is configured → binds Chunk 02: with no `WIKIDATA_USER_AGENT` there is no Commons source, the startup line says which sources are wired, and Get says it cannot run with no source"
last_validated: null
---

# Build Plan — Get and Ask

## What this plan is

Plan 2 of `build-plan-ia-foundations.md` § What comes after. Ruling 3 dissolves
Add New: *Get* is an action on any selection, and the conversation becomes *Ask*.
Today a run takes free text only, and phase 2 asks one museum by title. After
this plan a curator can select works the registry knows and Get them, and the
images come from a pool of sources asked together.

| Chunk | What | Ruling or debt |
|---|---|---|
| 01 | An image-source pool: every wired source asked in parallel, behind the existing seam | Owner, 2026-10-01 (below) |
| 02 | Commons as a source, reached from a work's Wikidata item | Owner, 2026-10-01 |
| 03 | Get: a run seeded by chosen works, from HTTP and MCP | 3 |
| 04 | Get in the client: on a selection, and on a Work page | 3 |
| 05 | Ask replaces Add New | 3 |
| 06 | Activity › To review, with the unjudged count | 3; owed in `information-architecture.md` § The *arr layout |

**Not in this plan:**
- **Wanted.** Ruled out by the owner 2026-10-01: it appears when the first thing
  fills it (wave 4's cutoff, or a Watch). A work a Get finds nothing for stays
  visible on that Get.
- **Excursion Gets**: plan 3 (Topics and excursions). Until then every acceptance
  joins the default theme, as today.
- **Ask reading taste**, and Similar artists from Ask: plan 4.
- **Finding a Wikidata item for a work phase 1 proposes.** A discovery run's
  proposals carry a title and an artist, not an item, so the Commons source has
  nothing to look up for them and they reach the Art Institute alone, as today.
  Matching proposals to items is the identity matcher's job and needs its own
  measurement of how often it is wrong.

## What I would do differently

- **Ship Chunks 01 and 02 before the UI, even if the rest slips.** They change
  nothing a curator sees, and the first time a Get runs the pool should already
  have been exercised against real sources. Ordered so.
- **Fetch a Commons image at a bounded size, never the original.** The probe found
  a 44,567 px wide Starry Night. The panel needs a fraction of that, and the
  acquisition path caps a body at 512 MiB. Commons serves scaled renderings on
  request. Chunk 02 measures the largest scaled width it will serve and the byte
  size of a few originals before choosing.
- **Leave the Art Institute's own identifier (`P4610`) for later.** The registry
  can map an item to the Art Institute's object id, which would make that lookup
  exact instead of by title. It is a second identity path for one source. The
  pool makes it a local change to that source whenever it is wanted.

## Requirements Confidence

**Medium.** The rulings settle what to build. How often a Commons image clears the
display floor is measured for three works only.

- **Ruled by the owner 2026-10-01:** *"Let's build a pool, and not special case any
  particular one. Commons then Chicago to start, but make them pluggable so we can
  add more, search in parallel, etc."* The question as put: where a Get looks for
  images, Commons then the Art Institute, or the Art Institute alone. Probe: Starry
  Night's Commons image is 44,567 × 35,291; a Delaunay's is 1,229 × 1,335; *The
  Persistence of Memory* has none.
- **Ruled by the owner 2026-10-01:** Wanted is left out of this plan.
- **Ruled by the owner 2026-10-01:** the free-text box moves to the top of the Ask page.
- `[DECISION: "Commons then Chicago" is an order of preference among instances, never an order of asking. Every source is asked at once, and phase 2's existing ranking picks the selected instance. Where two instances rank level, the source listed earlier in the wiring wins | the owner's ruling asks for parallel search and no special case; a source asked only when another failed would be a special case | user can veto/override]`
- `[DECISION: when some sources fail and the others find nothing, the work stays pending, exactly as when today's one source fails. It is never recorded as not found. When any source finds an instance, the failures are logged and the work resolves on what was found | core.md: keep 'unconfirmable' apart from 'failed'. A work called unresolved because a server was down would tell the curator the painting is not out there | user can veto/override]`
- `[ASSUMPTION: Get acts on works the library does not hold. A held work in a selection is skipped and the control says how many it skips. Get on a held work (a better image) is a re-search, which exists, and is not merged into Get here | MED impact | user can correct]`
- `[ASSUMPTION: a Get is a new run kind, "get". It starts at phase 2 (no phase 1, no approval step, no spend) with one candidate per chosen item. Each candidate carries the Wikidata item it was asked for, and accepting it stores that item on the new artwork, set by the curator | HIGH impact | user can correct]`
- `[ASSUMPTION: after a Get starts, the page stays where it is and says so in its live region, with a link to the run. Radarr's Add does the same. The run is listed in Queue | LOW impact | user can correct]`
- `[ASSUMPTION: the Commons source answers only a query that names a Wikidata item, and offers the item's image (P18). It searches Commons by title for nothing | MED impact | user can correct]`
- `[ASSUMPTION: To review lists runs with at least one candidate not yet judged, newest first, each opening Review. The sidebar entry reads "To review" followed by the count as a number, and the Activity section carries the same word and count | MED impact | user can correct]`

**What would raise it:** Chunk 02's measurement of Commons images against the
display floor over the owner's own artists' works.

## Status

- [ ] Chunk 01: An image-source pool
- [ ] Chunk 02: Commons as a source
- [ ] Chunk 03: Get, from HTTP and MCP
- [ ] Chunk 04: Get in the client
- [ ] Chunk 05: Ask replaces Add New
- [ ] Chunk 06: Activity › To review

### Chunk 01: An image-source pool

- **New `library/discovery/pool.py`**: an `ImageSearch` that holds an ordered list
  of `ImageSearch` sources. `find_images` asks every source at once, on a bounded
  thread pool, and returns their instances together. A failure in one source is
  logged with its name. Only when every source failed, or when some failed and the
  rest found nothing, does the pool raise `ImageSearchFailure` naming the ones that
  failed (the DECISION above). `fetch_preview` and `tile_url` go to the source
  whose name the instance was recorded under. A URL naming no wired source is
  refused by name, never guessed.
- **Ranking ties go to the source listed first.** Phase 2 sorts on its own
  quality score today. The pool gives each instance its source's position, and
  that position breaks ties. Phase 2's judgement of identity is unchanged.
- **`ImageQuery` gains an optional Wikidata item.** A source that cannot use it
  ignores it.
- **Wiring**: `__main__.py` builds the pool from every configured source, with the
  Art Institute as the only one for now. The startup line names the sources wired.
  The runner and `PreviewCache` see one `ImageSearch`, as they do today.

**Done when:**
1. Unit tests, each watched failing: two fake sources answering at once (each
   blocks until the other has been asked); one failing and the other finding (it
   resolves, and the failure is logged); one failing and the other finding nothing
   (it raises); both finding nothing (an empty answer, not a failure); a preview
   routed to its own source; a tie broken by order.
2. The runner's existing tests pass through the pool unchanged.
3. All suites pass.

### Chunk 02: Commons as a source

**Foreign API:** Wikimedia Commons (MediaWiki action API), Wikidata (P18)

- **New `library/discovery/commons.py`**: an `ImageSearch` named `commons`. For a
  query with a Wikidata item, it reads the item's image (P18) through the registry
  client's endpoint and rules, then asks Commons for the file's size, type and
  licence. It reports one instance: the master's dimensions, the item's label as
  the title, the creator as the artist, `institutional`, `direct_http`, and the
  licence as its rights. A query without an item gets an empty answer.
- **The download is a scaled rendering**, at a width chosen from the measurement
  in step 0. It goes through the existing direct-HTTP acquisition and its
  one-hop checked transport. The preview is Commons' small rendering, read with
  the existing preview bound.
- **Configuration**: wired when `WIKIDATA_USER_AGENT` is set, because Wikimedia
  asks every client for a descriptive User-Agent. It is listed first in the pool,
  before the Art Institute.
- `wikidata-findings.md` gains a section on Commons: the measurements and the
  licences seen.

**Done when:**
0. verify-api: for the Wikidata works of every artist the owner's catalogue holds
   (QIDs read from the catalogue copy, never typed), record how many have a P18
   image and how many of those clear the display floor. For five files, record the
   byte size of the original, the widest scaled rendering Commons serves, the
   licence fields it returns, and whether the file URL redirects to another host.
1. Unit tests against recorded responses, each watched failing: an item with an
   image; an item without one; a file whose size is unknown; a licence that is not
   free; an endpoint that fails (the source raises; it never answers empty).
2. A Get-shaped resolution, by a test through the runner, selects a Commons
   instance over a smaller Art Institute one, and the Art Institute's over a smaller
   Commons one.
3. All suites pass.

### Chunk 03: Get, from HTTP and MCP

- **Persisted format.** The questions the new fields must answer, from their
  consumers:
  - Which Wikidata item was this candidate asked for? Acceptance stores it on the
    artwork. Review shows it. A later Get skips an item already held.
  - Was this run a Get, a discovery, or a re-search? Queue, History and To review
    label runs by kind.
  - What did a Get skip, and why (held already, or the item named nothing)? This
    is answered in the response and the run's log, and is not stored. Nothing
    reads it later.
  So: `RunKind.GET`, `WorkProvenance.CHOSEN`, and `candidate_works.wikidata_qid`
  (nullable, with a migration). `data-model.md` and `api-contract.md` gain them.
- **`DiscoveryRunner.get(qids, initiated_by)`**: looks each item up in the
  registry, skips held ones, writes one candidate per item from the registry's
  title and maker, and starts phase 2 over the pool at `resolving_images`. It
  refuses with no registry or no image source, saying which.
- **Acceptance** of a candidate with an item stores the item on the new artwork,
  set by the curator. If another artwork already carries the item, the identity
  service's existing rule refuses, and the acceptance says so.
- **Bindings**: `POST /api/gets {qids}` returns the run and what was skipped. MCP:
  `art_discovery(action='get', qids=[…])`.

**Done when:**
1. Integration tests over HTTP and MCP, each watched failing: a Get of two items
   starts one run with two candidates, spends nothing, and resolves through fake
   sources; a held item is skipped and reported; accepting stores the item on the
   artwork; accepting an item another artwork holds is refused.
2. A migration test opens a store from before this chunk.
3. All suites pass.

### Chunk 04: Get in the client

**Visual change:** yes

- **Selection on registry lists**: the Artist page's *Their work* and the results
  page's Wikidata works gain the same tick boxes the library's lists have. A
  toolbar control reads *Get 3 works*, or *Get 2 works (1 held, skipped)*.
- **A Work page for a work not held** replaces *Search museums for this work* with
  *Get this work*.
- **After a Get**, the page stays and announces *Getting 3 works*, with a link to
  the run. Queue and History label a Get as *Get*.
- **Review** shows the item a Get asked for, linked by QID.

**Done when:**
1. Browser tests, each watched failing: a selection's Get posts exactly the
   ticked, unheld items; the count and skip wording; the Work page's Get; the
   announcement and its link; Queue's kind label.
2. Driven against a copy of the owner's catalogue at 1280 and 375 px: Get two
   unheld works from an artist the library holds, and Review shows what came back.
   Operator-verification entry.
3. All suites pass, including the browser suite.

### Chunk 05: Ask replaces Add New

**Visual change:** yes

- **The `discover` screen becomes `ask`**, named *Ask*, in the same slot under
  the library section. `#discover` and `/discover` (and `/discovery`) keep
  working as aliases, so old links still open. The conversation opens from Ask.
- **Ask's page**: the free-text box and its estimate on top, with *Search now* and
  *Talk it through*, then the conversations.
- **Every way in is re-pointed**: the typeahead's group becomes *Ask*, with the row
  *Ask about "{query}"*. The empty states and the buttons that opened Add New
  open Ask.
- **Artifacts**: `information-architecture.md`'s screen tables, the *arr layout
  table and Flows 1 and 2 are amended from the proposal.
  `tests/preferences/test_screen_tables.py` holds them to `app.js`.

**Done when:**
1. The sidebar, typeahead, conversation and route tests are updated to the new
   name in the same commit as the rename. A test asserts the old addresses still
   arrive at Ask.
2. Driven at both widths. Operator-verification entry.
3. All suites pass.

### Chunk 06: Activity › To review

**Type:** cumulative-final
**Visual change:** yes

- **The unjudged count**: `ReviewService` counts each run's candidates with no
  verdict. `GET /api/runs` carries it per run, and the MCP run listing does the
  same.
- **To review**, under Activity before Queue: the runs with something to judge,
  newest first, each opening Review. The sidebar entry and the Activity section
  carry the count as a word and a number.
- `information-architecture.md`'s tables gain the screen, and its recorded gap is
  closed.

**Done when:**
1. Integration tests for the count over HTTP and MCP (a run with mixed verdicts;
   a re-search's works counted once). Browser tests: the page lists exactly the
   runs with something to judge, and the count updates after a verdict. Each
   watched failing.
2. Driven at both widths. Operator-verification entry.
3. All suites pass, then the cumulative review.

## Governance checkpoints

- **After Chunk 02**, read the Commons measurement before building Get on it. If
  few of the owner's artists' works clear the floor, say so to the owner before
  Chunk 03.
- **Before the PR**, the cumulative review in Chunk 06.

## Verification strategy

As in the last two plans: the browser suite drives the real client against a
booted server. Each visual chunk runs Arrt against a copy of the owner's
catalogue, with `WIKIDATA_USER_AGENT` and `ARTIC_USER_AGENT` set, driven with
Playwright at 1280 and 375 px. The question for each is the scenario it serves
(S3 *more by an artist*, S4b *get a copy*, S11 *Rothko, knowing nothing*). A Get
run live fetches real images into the copy's art root and never the owner's.
Every identifier, count and measurement written into a test or a record is copied
from its source in that step.
