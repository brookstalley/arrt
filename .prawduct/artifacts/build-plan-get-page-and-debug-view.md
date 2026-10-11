---
artifact: build-plan
version: 1
scope: get-page-and-debug-view
branch: feature/get-page-and-debug-view
partition: serial, one worktree. Three chunks; 01 and 02 share `screens/run.js`, and 03 changes the plugin interface the other two only read
Critic mode: cumulative-final
depends_on:
  - artifact: ia-proposal
  - artifact: source-plugins
governed_by:
  - artifact: ia-proposal
    dispositions:
      - "§ Rulings (2026-10-11), ruling 1 (engineering detail behind `?debug`) → conforms: 02 builds it"
  - artifact: information-architecture
    dispositions:
      - "§ Direction (navigation is a link, an act is a button) → conforms: 01's work titles are links"
  - artifact: source-plugins
    dispositions:
      - "§ Versioning (a minor only adds optional capabilities) → conforms: 03 adds an optional `museum` as interface 1.4"
last_validated: null
---

# Build Plan — the Get page, and the debug view

## What this plan is

The two items the second UX walk (`ux-review-2026-10.md` § Second walk,
findings 32, 34 and 39) put first, chosen by the owner 2026-10-11 ("yes to
all" to the suggestion of #363 and #355 first):

- **#363.** A Get's page shows error prose where its pictures belong, the
  model's reading of the request, a *Review these works* that can open onto
  nothing, works that link nowhere, and "not held" for a work the library holds.
- **#355.** Engineering detail moves behind `?debug` (ruling 1 of 2026-10-11),
  and every source is named by its museum.

## Goals

- **01: a Get's page shows pictures, links and only acts that lead somewhere.**
  A picture cell with no picture is a short picture-shaped placeholder, never
  the server's explanation (which stays reachable in debug). *Review these
  works* appears only while a card is left to judge. Each work's title links to
  a page: the work it was accepted as, else the library's own copy of it, else
  its Wikidata item. A work the library holds says so, with a link.
- **02: without `?debug` no page shows a file path, hash, rendition table,
  mat hex, raw JSON, raw key or plugin id; with it, each shows where it does
  today.** The flag is the page's own query, so it survives in-app navigation.
- **03: every installed source has a museum name to show.** Plugin interface
  1.4 adds an optional `museum` to `SourcePlugin`; the server names every
  installed plugin by it (built-ins keep `MUSEUM`), `/api/sources` carries it,
  and the client names sources from the server. The operator's private plugins
  declare theirs, in their own repository.
- Done when: the three suites and the browser suite green; each new browser
  test seen red against the unfixed code; the records say what the code does;
  deployed, with the operator's library showing no plugin id outside debug.

### Decisions

- **[DECISION: a proposed work with no accepted work, no held copy and no
  Wikidata item stays text.]** The IA says a Get's rows open a work; such a
  work has no page to open. Making one is not this plan.
- **[DECISION: the model's reading of the request goes behind `?debug`.]** The
  issue proposed it; on one Get it is a fair paraphrase, on another the model's
  own instructions echoed back, and nothing tells the two apart.
- **[DECISION: the Mat colour panel moves to debug whole.]** A swatch without
  its hex would make colour the only carrier of the value, which the
  accessibility spec forbids; #346 brings the mat back as a picture.
- **[DECISION: the "not held" badge is reworded "in no collection".]** It means
  no wired museum holds the work, and was read as "you don't have it".
- **[DECISION: the branch starts from `docs/ux-walk-2026-10-11`]** (PR #364),
  which carries ruling 1; it merges after #364.

## Chunks

### Chunk 01: the Get page (#363)

- `core/reviewing.js` `rowPicture`/`instanceImage`: an absent picture reads
  *No picture kept*, and a review card keeps the server's reason as a caption
  under it (an existing contract: the card says why); `screens/run.js`: *Review these
  works* only when the review page has a card to judge (or could not be read);
  titles link per Goals; a held work's row says *In your library* as a link;
  `core/badges.js` `not_held` worded *in no collection*.
- Browser tests: no cell holds the server's note; the button is absent when
  nothing is to judge and present when something is; each linkable title is a
  link to the right page and an unlinkable one is text; a held work's row links
  to it.

### Chunk 02: `?debug` (#355, ruling 1)

- `core/debug.js`: `DEBUG`, read from `location.search` once.
- Work: the Master image panel's file, pixels-size and hash rows, What has
  been rendered, and Mat colour only in debug; the acquisition line and Where
  it can be obtained stay. Status: every `details()` only in debug. Sources: the
  Plugin and Package rows only in debug. Get: the model's reading only in debug.
- `information-architecture.md`: the Work, Status, Sources and Get rows say
  what debug adds. `test_no_machine_dates.py` keeps holding raw values inside
  the disclosures.
- Browser tests: each page with and without `?debug`; the flag survives a
  link followed in-app. Nine existing tests of debug-only content (the mat,
  Status's raw fields, paths breaking on a phone, the Work record's layout,
  Sources' package words) open their page with `?debug`, assertions unchanged.
- **[DECISION: Sources' Interface row goes to debug with the id and package]**:
  all three say how a plugin is installed, not what it does.

### Chunk 03: every source named by its museum (#355)

- `library/sources` plugin interface 1.4: optional `SourcePlugin.museum`;
  `names.py` gathers installed plugins' names too; `SourcePluginOut.museum`;
  the client loads the names once at start and `museumName` uses them, falling
  back to `MUSEUM_NAMES` and then the id.
- Records: `source-plugins.md` (1.4), `docs/source-plugins.md`, `api-contract.md`.
- Tests: a plugin declaring `museum` is named by it on the server and in the
  browser; one declaring none is named by its id, outside debug only where no
  name exists.
- The private plugins declare `museum` (their own repository, own commit).
  **[DECISION, found mid-build: after this branch merges, not on it.]** Their
  tests run against an Arrt commit pinned in their `pyproject.toml` (interface
  1.1), where `museum=` is a `TypeError`; the step bumps that pin to the merged
  commit and names the eleven, and the deploy follows it. Until then the live
  library names those sources by id outside debug, as today.

## Status

- [x] Chunk 01: the Get page (#363)
- [x] Chunk 02: `?debug` (#355, ruling 1)
- [ ] Chunk 03: every source named by its museum (#355)
