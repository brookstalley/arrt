---
artifact: build-plan
version: 1
scope: ask-pages
branch: feature/ask-pages
partition: serial — one builder; Chunk 02 is built in the private plugin repository and depends on Chunk 01's interface
depends_on:
  - artifact: source-plugins
  - artifact: data-model
  - artifact: security-model
  - artifact: procurement-corpus
governed_by:
  - artifact: data-model
    dispositions:
      - "§ Direction: identity is never a source URL → conforms. A page the search cited is evidence handed to one resolution attempt, stored beside the run, never part of a work's identity or its key"
  - artifact: security-model
    dispositions:
      - "§ Direction: outside text reaches the page as text; an outside link or image is used only when its host is one this repository names → conforms. Cited pages are never sent to the browser, and the plugin reports images only on Artlogic's asset host"
      - "§ Prompt Injection bound 2 (no fetch a curator did not first accept) → amendment proposed, approved by the owner 2026-10-05: a plugin may read a page the run's web search cited, before acceptance. See the DECISION below; the section is re-derived in Chunk 01, as its own trigger list requires"
last_validated: null
---

# Build Plan — Pages from Ask, and the Artlogic galleries

## What this plan is

The owner chose the next source after MoMA and SFMOMA: **Artlogic**, the gallery
platform (`procurement-corpus.md` § Sources a prediction may name). They ruled
on 2026-10-05:

- **A gallery is found through Ask's web search**, not a configured list of
  gallery sites. So Ask must hand what its search found to the source plugins,
  which it does not do today.
- **Both of Artlogic's page templates** are read: Artlogic CMS (Markel, Nüart)
  and exhibit-E (Kordansky).
- **Go on this plan**, including the amendment to the security model's bound 2
  below.

Gallery works have no Wikidata item, so the route MoMA and SFMOMA take (a QID
gives the holder's page) does not exist for them. Phase 1's web search returns
the pages it read as citations (`Completion.citations`, `openrouter.py`), and
today they are read only to count them.

| Chunk | Where | What |
|---|---|---|
| 01 | this repository | A run keeps its search's citations, and they reach every finder through `ImageQuery.pages` (interface 1.1) |
| 02 | `arrt-sources` (private) | The Artlogic plugin: a finder for Artlogic CMS and exhibit-E gallery pages |
| 03 | the NAS | Deploy, and Ask for the corpus's gallery rows (54–59) |

**Not in this plan:** a list of galleries to search; pasting a URL; sightings for
cited pages (the table is keyed by QID, and stored citations make it possible
later); carrying a run's pages to an accepted artwork, for upgrades (#177);
exhibit-E and Artlogic sites that are not galleries.

## What the probe measured (2026-10-05)

Recorded in `procurement-corpus.md` § The probe: Artlogic, and what Ask's search
cites (2026-10-05). What it decided here:

- **The search cites a gallery's artist page, not a work's page.** So the model
  is not asked to name pages; **the run's citations are the pages**, and the
  plugin finds the asked work on the gallery page it recognises.
- **The asset host serves the stored original** under an empty transform, up to
  10,446 px measured, so the plugin records that address and never a transform.
- **Both templates print the holder's words beside each image**, and Artlogic
  CMS's listing also prints the original's size.

## Requirements Confidence

**Medium-high.** Both ends are measured: the search cites the galleries, and the
galleries serve the originals with the holder's words beside them. What is not:

- how often the search cites a gallery for an artist it was not handed by name
  (Part B's question, not this plan's);
- whether exhibit-E's other galleries use Kordansky's slider markup. One site
  was read.

- [ASSUMPTION: a run's citations are stored with the run, and every work the run proposed is searched with all of them, at most 10 (the search's own `max_results`) | LOW impact | owner can correct]
- [ASSUMPTION: a run's citations are not carried to an artwork on acceptance | MED impact: an upgrade search of a held gallery work (#177) will not have them | owner can correct]
- [ASSUMPTION: the plugin records the original's address on the asset host as the source's `url`, so acquisition fetches it as recorded and the plugin needs no reader. The gallery page stays among the run's citations | MED impact, a persisted shape: `Source.url` for these rows is an image file, as Commons' already are | owner can correct]
- [ASSUMPTION: from a cited page on a gallery's host, the plugin may read that host's works listing for the same artist (Artlogic CMS: the artist's `/works/` path; exhibit-E: `featured-works?view=slider`), one page further and never another host | MED impact: it widens what a citation lets the plugin read | owner can correct]
- [DECISION: the pages are exactly the search's citations; the model is never asked to name an address | a structured answer can name an address nobody served, and a citation is one the search engine itself fetched. Measured: the search cites gallery artist pages, not work pages, so a per-work answer would have had nothing better to say | agent's]
- [DECISION: interface 1.1 adds `ImageQuery.pages`, a tuple that defaults to empty. A plugin written for 1.0 loads and never sees it | a minor only adds optional capabilities (`plugin.py`, `API_VERSION`) | owner can veto]
- [DECISION: Arrt runs `check_fetchable` on each page before it reaches a finder, and drops (and logs) one it refuses | a plugin's own requests are unguarded (`security-model.md` § Source plugins), and these addresses came from outside; a LAN address or a `.local` name never reaches a plugin | owner can veto]
- [DECISION: security-model § Prompt Injection bound 2 is amended, not worked around. A plugin may now read, before any curator acceptance, a public page the run's search cited, and the same gallery's listing for that artist. What bounds it: the page must be a citation; Arrt checks its address; the plugin reads only pages of a shape it recognises, on that page's own host, with GET and a bounded body; and the Artlogic plugin reports images only on Artlogic's asset host, so an injected page cannot name an arbitrary image to fetch. The realistic worst case, an injected page steering which gallery image is offered, is the one the section already names, and it still stops at review | the section lists "a tool that fetches an arbitrary URL on request" as a trigger to re-derive, and this is a narrow form of it | approved by the owner 2026-10-05]

## Status

- [x] Chunk 01: A run's citations, stored, and handed to the finders
- [ ] Chunk 02: The Artlogic plugin (private repository)
- [ ] Chunk 03: Deploy, and Ask for the gallery rows

### Chunk 01: A run's citations, stored, and handed to the finders

**Foreign API:** OpenRouter web search (citations)
**Exposed API:** the source-plugin interface, 1.0 → 1.1

Done when:

0. **verify-api.** Done 2026-10-05 (§ What the probe measured): the citations'
   shape is `openrouter-api-findings.md` § Search citations come back as
   annotations, and they name the galleries. Recorded in `procurement-corpus.md`.
1. **Phase 1** (`phase_one.py`, `engine.py`): `WorkList` carries the run's
   citations, in the search's order, deduplicated, http(s) only. Its prompt and
   schema are unchanged.
2. **Stored** (persisted format). New table `run_citations(discovery_run_id,
   url, position)`, keyed on the run and the URL, with its migration, written
   when the runner records phase 1's answer. The questions it must answer, from
   its readers:
   - *phase 2:* which pages did this run's search read, in order? Asked on
     approval, on a re-search, and after a restart, all of which build the query
     from stored rows;
   - *later sightings for works with no item* (not built here): which hosts do
     the citations of runs with unresolved works name?
   - *never:* the browser. Citations are not sent to it (security-model §
     Direction).
3. **The query.** The one site that builds an `ImageQuery` from a stored row
   (`runner.py`) adds its run's citations, each passed through `check_fetchable`
   once per run, and a refused one is dropped and logged. A Get's works, offered
   works from a run with no citations, and runs from before this change have no
   pages, and are searched exactly as before.
4. **The interface.** `API_VERSION` becomes `(1, 1)`. `ImageQuery.pages`'
   docstring says what a page is (an address the run's search cited, public when
   Arrt checked it, about the run's intent rather than this one work) and that
   its content is outside text.
5. **Tests**, each watched failing once against a re-break:
   - the citations are kept in order, deduplicated, and non-http(s) ones are
     dropped;
   - they survive a restart and reach the query on a re-search;
   - a LAN or `.local` citation never reaches a finder, and the others do;
   - a 1.0 plugin loads under 1.1;
   - a Get's query has no pages.
6. **Artifacts:**
   - `source-plugins.md` and `docs/source-plugins.md`: `ImageQuery.pages`, and
     what a finder may do with it;
   - `data-model.md`: the table and its questions;
   - `security-model.md`: bound 2 re-derived, and § Source plugins;
   - `api-contract.md`, if the run API exposes anything new (expected: nothing).

### Chunk 02: The Artlogic plugin (private repository)

Built in `arrt-sources`, beside `moma` and `sfmoma`, with its measurements in its
docstring and its record there. Reviewed by fresh agents until a review finds no
blocking issue, as those two were. What it must do:

- **Recognise a page by its shape before reading it:** a path under an Artlogic
  CMS artist (`/artists/<n>-<slug>/…` or `/artists/<n>/…`) or an exhibit-E
  artist (`/artist/<slug>…`). A page of neither shape is not read. A query with
  no pages is not answerable.
- **Read the artist's works on that host** (the CMS works listing; exhibit-E's
  slider), confirm the template from what it serves, and treat a page that is not
  the one expected as could-not-be-asked, never as "holds nothing"
  (`source-plugins.md` § Three answers).
- **Report the asked work only**, matched on its caption's title and artist, in
  the holder's own words. Other works on the page are left out.
- **Report the original:**
  - the source `url` is the empty-transform address on the asset host;
  - its size from the listing's `data-width`/`data-height` where given, else a
    ranged read of the original's JPEG header;
  - the preview is a small transform;
  - rights from the caption where one is printed, else unknown, never free.
- **Read politely and within bounds:** one page at a time per host, a listing
  read once per run rather than once per work, with `sfmoma`'s timeouts and body
  bound as the model.

### Chunk 03: Deploy, and Ask for the gallery rows

- The owner's go to deploy. A catalogue copy is taken first.
- Asks naming Peter Stephens's and Lucy Bull's corpus works (rows 54–59). The
  result is recorded in `procurement-corpus.md` beside run 5: which rows were
  found, at what size, and through which page.
- **Part B's held-out rule:** no held-out artist is named in an Ask, a prompt or
  the plugin. The galleries Markel and Nüart represent held-out artists, and
  nothing here lists a gallery's artists.

## Verification strategy

The three suites, and `arrt-sources`' own unit suite and live tests. The product
check is Chunk 03: the corpus rows found through an Ask, at the original's size,
reviewed in To review.

## Governance checkpoints

After Chunk 01, which fixes the interface Chunk 02 builds on. Then the
cumulative review of this branch before its PR.
