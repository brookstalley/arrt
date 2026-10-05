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
      - "§ Direction: identity is never a source URL → conforms. A page the search showed is evidence handed to one resolution attempt, stored beside the candidate, never part of the work's identity or its key"
  - artifact: security-model
    dispositions:
      - "§ Direction: outside text reaches the page as text; an outside link or image is used only when its host is one this repository names → conforms. Pages are never sent to the browser, and the plugin reports images only on Artlogic's asset host"
      - "§ Prompt Injection bound 2 (no fetch a curator did not first accept) → amendment proposed: a plugin may read a page the run's web search cited, before acceptance. See the DECISION below; the section is re-derived in Chunk 01, as its own trigger list requires"
last_validated: null
---

# Build Plan — Pages from Ask, and the Artlogic galleries

## What this plan is

The owner chose the next source after MoMA and SFMOMA: **Artlogic**, the gallery
platform (`procurement-corpus.md` § Sources a prediction may name). They ruled
on 2026-10-05:

- **A gallery is found through Ask's web search**, not a configured list of
  gallery sites. So Ask must hand the pages its search found to the source
  plugins, which it does not do today.
- **Both of Artlogic's page templates** are read: Artlogic CMS (Markel, Nüart)
  and exhibit-E (Kordansky).

Gallery works have no Wikidata item, so the route MoMA and SFMOMA take (a QID
gives the holder's page) does not exist for them. Today phase 1 proposes a
title, an artist and a reason, and nothing else. Its web search's citations come
back (`Completion.citations`, `openrouter.py`) and are read only to count them.

| Chunk | Where | What |
|---|---|---|
| 01 | this repository | Phase 1 names each work's pages from its search's citations; they are stored with the candidate and reach every finder through `ImageQuery.pages` (interface 1.1) |
| 02 | `arrt-sources` (private) | The Artlogic plugin: a finder for Artlogic CMS and exhibit-E pages |
| 03 | the NAS | Deploy, and Ask for the corpus's gallery rows (54–59) |

**Not in this plan:** a list of galleries to search; pasting a URL; sightings for
pages of works with no Wikidata item (the table is keyed by QID, and stored pages
make it possible later); carrying a candidate's pages to the artwork when it is
accepted, for upgrades (#177); exhibit-E and Artlogic sites that are not
galleries.

## What the probe measured (2026-10-05)

By hand, over plain HTTP, with Arrt's own user agent:

- **The asset host serves the stored original** when asked with an empty
  transform (`https://static-assets.artlogic.net//<path>`), on both templates:
  - Lucy Bull, *The Bottoms* (Kordansky, exhibit-E): **10,446 × 7,970**. The
    corpus measured 3,600 × 2,747, the largest transform the page asks for.
  - Peter Stephens, *Mambo Jumbo* (Markel, Artlogic CMS): 2,885 × 3,173, the
    same as the page's `w_4000` transform.
  - Peter Stephens, *Big Top* (Nüart, Artlogic CMS): 2,839 × 2,838, where the
    page stops at 2,400.
  - A larger transform than the original upscales it (`w_8000` gave 8,000 ×
    6,104 for *The Bottoms*), so a transform is never how the master is fetched.
- **A ranged read works** (`Range: bytes=0-65535` → 206), so the original's size
  comes from its JPEG header without downloading it, as the MoMA plugin does
  (`arrt_sources/jpeg.py`).
- **Artlogic CMS has one page per work**, `/artists/<n>-<slug>/works/<n>/`, with
  `og:title` "Peter Stephens, Mambo Jumbo, 2023" and the image on the asset host.
  The footer says "Site by Artlogic".
- **exhibit-E has no page per work.** The artist's works are slides on one page
  (`/artist/lucy-bull/featured-works?view=slider`). Each slide's `img` carries
  `alt='Lucy Bull, The Bottoms, 2021'` and the asset-host image, and its
  `figcaption` carries the artist, the title in `<em>`, the year, the medium and
  the size. The page names `collageplatform` and no Artlogic credit.

## Requirements Confidence

**Medium.** The plugin side is measured. What is not: **whether phase 1's search
cites a gallery's own page for a work at all**, rather than a press article or
an aggregator. If it rarely does, this route finds little, and the configured
list the owner declined would be the fallback to raise with them.

What would raise it: **Chunk 01's first step**, one live Ask naming Peter
Stephens and one naming Lucy Bull on today's build, with the citations logged.
It spends about two cents each (`openrouter-api-findings.md`: the flat web fee
plus inference).

- [ASSUMPTION: at most 3 pages are kept per work, in the model's order | LOW impact | owner can correct]
- [ASSUMPTION: a page is stored with the candidate only. Acceptance records the image's source as today, and does not carry the pages to the artwork | MED impact: an upgrade search of a held gallery work (#177) will not have them | owner can correct]
- [ASSUMPTION: the plugin records the original's address on the asset host as the source's `url`, so acquisition fetches it as recorded and the plugin needs no reader. The gallery page stays on the candidate's pages | MED impact, a persisted shape: `Source.url` for these rows is an image file, as Commons' already are | owner can correct]
- [DECISION: a page passes only if it is one of the run's citations, compared on scheme, host (case-folded), path (a trailing slash ignored) and query, with the fragment dropped, and stored in the citation's own spelling | a model's structured answer can name an address nobody served, and a citation is an address the search engine itself fetched; it is also the narrowest thing an injected page can steer | owner can veto]
- [DECISION: interface 1.1 adds `ImageQuery.pages`, a tuple that defaults to empty. A plugin written for 1.0 loads and never sees it | a minor only adds optional capabilities (`plugin.py`, `API_VERSION`) | owner can veto]
- [DECISION: Arrt runs `check_fetchable` on each page before it reaches a finder, and drops (and logs) one it refuses | a plugin's own requests are unguarded (`security-model.md` § Source plugins), and these addresses came from outside; a LAN address or a `.local` name never reaches a plugin | owner can veto]
- [DECISION: security-model § Prompt Injection bound 2 is amended, not worked around. A plugin may now read, before any curator acceptance, a public page the run's search cited. What bounds it: the page must be a citation; Arrt checks its address; the plugin reads only pages of a shape it recognises, with GET and a bounded body; and the Artlogic plugin reports images only on Artlogic's asset host, so an injected page cannot name an arbitrary image to fetch. The realistic worst case, an injected page steering which gallery image is offered, is the one the section already names, and it still stops at review | the section lists "a tool that fetches an arbitrary URL on request" as a trigger to re-derive, and this is a narrow form of it | owner can veto]

## Status

- [ ] Chunk 01: Pages from Ask, stored, and handed to the finders
- [ ] Chunk 02: The Artlogic plugin (private repository)
- [ ] Chunk 03: Deploy, and Ask for the gallery rows

### Chunk 01: Pages from Ask, stored, and handed to the finders

**Foreign API:** OpenRouter web search (citations)
**Exposed API:** the source-plugin interface, 1.0 → 1.1

Done when:

0. **verify-api.** One live Ask each for Peter Stephens and Lucy Bull on today's
   build, logging every citation's URL: does the search cite the galleries' own
   pages, and in which form (with or without exhibit-E's slider query)? Recorded
   in `procurement-corpus.md` under its date. If neither cites a gallery page,
   stop and take it to the owner before building.
1. **Phase 1** (`phase_one.py`): each work in `WORK_LIST_SCHEMA` gains a required
   `pages` array of strings, which may be empty. The prompt asks for the address
   of each work's own page among the search results, a holder's or gallery's page
   showing that work, and for none rather than a guess. `ProposedWork` gains
   `pages`, kept by the citation rule above, at most 3. Logged per run: pages
   named, kept, and dropped as not cited.
2. **Stored** (persisted format). New table `candidate_pages(candidate_work_id,
   url, position)`, keyed on the work and the URL, with its migration, written
   when the runner proposes a work. The questions it must answer, from its
   readers:
   - *phase 2:* which pages did the search show for this work, in order? Asked
     on approval, on a re-search, and after a restart, all of which build the
     query from the stored row;
   - *later sightings for works with no item* (not built here): which hosts do
     the stored pages of unresolved works name?
   - *never:* the browser. Pages are not sent to it (security-model § Direction).
3. **The query.** The one site that builds an `ImageQuery` from a stored row
   (`runner.py`) adds the row's pages, each passed through `check_fetchable`, and
   a refused one is dropped and logged. A Get's works and pre-existing Ask works
   have no pages, so they are searched exactly as before.
4. **The interface.** `API_VERSION` becomes `(1, 1)`. `ImageQuery.pages`'
   docstring says what a page is (an address the run's search cited, public when
   Arrt checked it) and that its content is outside text.
5. **Tests**, each watched failing once against a re-break:
   - only cited pages are kept;
   - spelling variants match, and a different query string does not;
   - the cap keeps the model's first three;
   - an empty `pages` is valid;
   - a page survives a restart and reaches the query on a re-search;
   - a LAN or `.local` page never reaches a finder;
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

- **Recognise a page by its shape before reading it:** an Artlogic CMS work page
  (`/artists/<n>-<slug>/works/<n>/`) or an exhibit-E artist page
  (`/artist/<slug>` and its `featured-works` views). A page of neither shape is
  not read. A query with no pages is not answerable.
- **Confirm the template from the page**, with the asset host's images present,
  and treat a page that is not the one expected as could-not-be-asked, never as
  "holds nothing" (`source-plugins.md` § Three answers).
- **Report the holder's own words** (artist and title from `og:title` on Artlogic
  CMS, from the slide's caption on exhibit-E). On exhibit-E it reports the slide
  whose caption is the work asked for, and every other slide is left out.
- **Report the original:**
  - the source `url` is the empty-transform address on the asset host;
  - its size comes from a ranged read of the original's JPEG header;
  - the preview is a small transform;
  - rights come from the caption where one is printed, else unknown, never free.
- **Read politely and within bounds,** one page at a time per host, with
  `SFMOMA`'s timeouts and body bound as the model.

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

After Chunk 01's verify-api step, which decides whether the route is worth
building. Then the cumulative review of this branch before its PR.
