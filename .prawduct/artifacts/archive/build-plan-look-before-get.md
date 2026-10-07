---
artifact: build-plan
version: 1
scope: look-before-get
branch: feature/look-before-get
partition: serial — one builder. Depends on build-plan-picture-store.md (merged into develop first; this branch merges develop before building)
depends_on:
  - artifact: build-plan-picture-store
  - artifact: information-architecture
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ Screens, the Work row for a work not held → amended: it shows what the image sources hold now, filling in as each answers, before any Get"
  - artifact: api-contract
    dispositions:
      - "Every HTTP answer has an MCP twin with the same field names → conforms: `art_discovery(action='look')` twins the look route; the registry pages' 'no MCP twin' line is amended for the look, with the reason"
  - artifact: security-model
    dispositions:
      - "§ Direction, an outside image comes only from a named host or a checked id → conforms: look pictures come from the picture store through a route keyed by a server-minted id; no client-supplied URL is fetched"
  - artifact: data-model
    dispositions:
      - "The picture-store norm (every outside picture kept; asks of 2,048 px or less answered from it) → conforms: the look's pictures go through the store"
  - artifact: accessibility-spec
    dispositions:
      - "Glyph and word carry the state; a live region announces changes and never moves focus → conforms: each source's row is a glyph and a word; one status region"
  - artifact: observability-strategy
    dispositions:
      - "Correlation by context variable → conforms: a `look_qid` context variable binds the look's lines as `run_id` binds a run's"
last_validated: null
lifecycle: completed
archived: 2026-10-07
released_in: v0.4.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — A work you don't hold shows what the sources hold, before any Get

## What this plan is

The owner, 2026-10-06: "The work page should prioritize getting a thumbnail or
something to see what it's like, even before the get request. It's weird to have
to get it before know what it looks like." Asked when, they ruled that **the
sources are asked on every unheld work page**, and then: "Hitting multiple
sources is fine, as long as we cache the result so repeated similar searches
don't do too many queries." The pictures themselves are kept forever by the
picture store (`build-plan-picture-store.md`, the owner's norm of the same day).

Today `#work/Q…` for a work the library does not hold shows only Wikidata's own
picture, if it has one. *Tantra-Vision* (Q20267229) has none, though SMK holds it
at 2,201 × 2,221.

The design was drafted by a Plan agent on 2026-10-06 with file:line citations.
They are summarised here and are to be re-checked at build time.

## Requirements Confidence

**High** for the shape; **Medium** for the slow-source scheduling (live timings unmeasured under load).

- [DECISION: **a "look"**: `LookService.look(qid)` in `library/services/look.py`, wired beside `GetService`. It asks every image source what a Get would ask, with the same `ImageQuery` a Get's run builds, judges identity with Get's own judge, and writes nothing to the catalogue. Get's code is extracted, not copied: `ImageSourcePool.ask(provider, query)` (the per-source sorting from `pool.py`, with `find_images` rebuilt on it), `PhaseTwoEngine.judge` and its sort key made public, `_WikidataLink` made thread-safe, and the query builder extracted from `get.py`/`runner.py` | agent's]
- [DECISION: **progressive fill by polling**: `GET /api/registry/works/{qid}/look` starts the fan-out or joins it, and answers at once with each source's state. The page polls every 2 s while any source is still being asked, repainting only the look's section. The fan-out runs on its own executor. Not SSE and not a request per source, because a held synchronous request ties a worker (`api.py` records why) | agent's]
- [DECISION: **MCP twin** `art_discovery(action='look', qid)`. It holds up to `LOOK_HOLD_SECONDS` (30 s) within `MODEL_LOOK_BUDGET_SECONDS` (40 s), under the client's 60 s, and inlines the best pictures by the existing image-block mechanism | parity rule; the budget amended at review, since `status`'s 45 s hold plus picture fetches could pass the client's timeout]
- [DECISION: **pictures**: `GET /api/registry/works/{qid}/look/pictures/{key}?size=card|large`, served from the picture store. `key` is the store's key, valid only if this QID's cached look names it. Otherwise the answer is 404, "Look again". A refused find gets no key. No route takes a URL from the client | security model; store norm]
- [DECISION: **finder caching, in memory**, per (QID, provider):
  - an answer is kept 6 h, including "holds nothing" and "can't look this up";
  - "could not be asked" is kept 10 min, never as "holds nothing";
  - at most 256 QIDs, least recently used dropped first;
  - concurrent looks share one fan-out;
  - not persisted, because the pictures persist in the store and finder answers describe the moment

  | the owner's caching requirement; agent's numbers]
- [DECISION: **politeness**:
  - at most one look at a time per source;
  - queued asks for a QID nobody has polled for 20 s are dropped before they start;
  - an ask that has started always finishes and is cached;
  - **a Get has priority**: a look's ask to a source a Get is using waits behind it

  | agent's; the owner can veto the priority rule]
- [DECISION: **a Get does not reuse a look's finds.** A run's journal needs its own per-result lines, and a cached answer would tie the run to staleness it can't see. Its pictures are free anyway: the store already holds them | agent's]
- [DECISION: **the page**:
  - Wikidata's picture stays on top when there is one. When there isn't, the first look picture to arrive takes the place and is never swapped afterwards.
  - A panel, *What the image sources hold*, has a row per source: `◌ Asking SMK…`, `● 2 found`, `○ Holds none`, `⊘ Holds a work by this title by another artist; not shown`, `▲ Could not be asked; trying again in 10 minutes`, `— Can't look this work up`.
  - Pictures are shown best first. Each is enlargeable and carries its source, pixels, fit badge (against the 1,000 px minimum, as built) and the rationale sentence. Six are shown, then "Show N more".
  - "No image source holds a picture of this work now." once every source has answered with none.
  - One `role=status` region announces only changes in the summary.
  - The line under *Get this work* reads: "These are what the sources hold now; getting the work records them and spends nothing."

  | agent's, on the review card's conventions]
- [DECISION: **states**: a held QID redirects to the library's page, as today; `being_got` asks nothing ("A Get is already asking the sources"); `no_sources`; and the registry's own states when Wikidata is off or has no such item | agent's]
- [ASSUMPTION: page-read plugins fetch previews over plain HTTP with bounded reads (verified 2026-10-06: `fetch_bounded` in moma, met_pages and artuk), so a 15 s bound on a picture fetch holds]

**Not in this plan:** Commons list pictures and conversation samples behind Arrt's routes (the third plan); a Get reusing a look.

## Status

- [x] Chunk 01: The look service, its cache and its two surfaces
- [x] Chunk 02: The Work page shows the look

### Chunk 01: The look service, its cache and its two surfaces

**Exposed API:** `GET /api/registry/works/{qid}/look`,
`GET /api/registry/works/{qid}/look/pictures/{key}`, and
`art_discovery(action='look')`.

Done when:

- The extractions (`pool.ask`, `judge`, the query builder) leave Get's behaviour
  unchanged. Existing phase-two and Get tests stay green unmodified, and a test
  shows the look's query equals the Get run's query.
- `LookService` and its cache. Unit tests with an injected clock:
  - TTLs and the 256-QID bound;
  - a failure is never kept as "holds none";
  - a second look joins the first (one finder call);
  - unwatched queued asks are dropped;
  - a Get's priority on a source;
  - a refused find has no key;
  - the look writes nothing: catalogue rows unchanged.
- Integration tests over real uvicorn with fake finders:
  - identity refused;
  - one source failing while others answer;
  - a slow source (the first poll says asking, a later one found);
  - a QID nothing holds;
  - a held QID;
  - a picture key from another QID or an expired look gets a 404;
  - MCP parity, and the MCP hold.
- Carried from the picture store's review (an observation accepted there): `picture_key`
  encodes with `errors="surrogatepass"`, so a lone surrogate in a source's URL cannot
  make `PictureStore.keep` raise. Add one example test through `keep`.
- Observability: `look.started`, `look.source_answered`, `look.source_unreachable`,
  `look.abandoned`, `look.picture_served`, with a `look_qid` context variable.
- Records: `api-contract.md`, `security-model.md`, `observability-strategy.md`,
  and a change-log entry with `scope=look-before-get`.
- **Critic mode:** chunk

### Chunk 02: The Work page shows the look

**Exposed API:** none new.

Done when:

- `arrt/src/arrt/http/static/screens/work.js` draws the panel, rows, pictures and states above, polling only
  its own section.
- Browser tests:
  - rows fill over successive polls, and focus never moves;
  - the live region is not rewritten with the same text;
  - the top picture is not swapped once filled;
  - the refused, failing and no-source wordings;
  - a picture's error fallback;
  - enlarge and Escape;
  - *Tantra-Vision*'s shape: no Wikidata picture, so the first find takes the top.
- `information-architecture.md`: the Work row and its content and empty-state
  rows, dated 2026-10-06.
- Operator verification: open `#work/Q20267229` and see SMK's picture without
  pressing Get; reload within 6 h and see no source asked (log).
- **Critic mode:** cumulative
