---
artifact: build-plan
version: 1
scope: met-source
branch: feature/met-source
partition: serial — one builder, one plugin module and its records
depends_on:
  - artifact: source-plugins
governed_by:
  - artifact: source-plugins
    dispositions:
      - "§ What a finder or reader must report → conforms: title and artist are the Met's own; dimensions are the original's, read from its JPEG header; rights recorded, never a filter"
      - "§ Which plugin reads a URL → conforms, and extended: two plugins for one holder claim disjoint URL shapes (the decision below)"
      - "§ Versioning and errors → conforms: imports only `arrt.library.sources`, written for major 1"
  - artifact: project-preferences
    dispositions:
      - "A source that reads pages treats a page it does not recognise as could-not-be-asked → conforms: any answer that is not the object asked for, or the Met's own 'ObjectID not found', is `ImageSearchFailure`"
      - "Identity is never a source URL → conforms: the API URL is a source attribute; identity stays the work's"
      - "Testing strategies → conforms: the network is doubled with recorded answers; the live half is `live_museum`"
  - artifact: information-architecture
    dispositions:
      - "§ The *arr layout: a new Settings page follows the *arr page it mirrors → Settings › Sources follows Radarr's Settings › Indexers, after Clients; the screen tables gain its rows (held by `tests/preferences/test_screen_tables.py`)"
  - artifact: accessibility-spec
    dispositions:
      - "Glyph and word carry the state → conforms: a plugin's state is a word in its sentence, never a colour, as on Status"
  - artifact: security-model
    dispositions:
      - "§ Direction: outside text reaches the page as text → conforms: a plugin's name, distribution, version and reason are set with `el`'s `text`"
  - artifact: security-model
    dispositions:
      - "§ Source plugins: a plugin's own requests are unguarded → bounded: it asks only the Met's API host and reads image heads only on `images.metmuseum.org` over https; anything else from the API is dropped"
last_validated: null
lifecycle: active
---

# Build Plan — The Met, through its open API

## What this plan is

The owner asked on 2026-10-06 for more sources and chose the Metropolitan Museum's
open API, after being shown that it fills none of today's 36 gaps (all three
gap works the Met holds are in copyright, and the API gives images only for
public-domain works). Its value is future Asks of public-domain art: full-size
CC0 originals with no key.

**Measured 2026-10-06** (generic agent string; the findings go to
`met-api-findings.md`):

- No key; the Met asks for at most 80 requests a second.
- `/v1/search` was **retired 2026-10-01**; `/v1.1/search` takes the same filters
  plus `offset`/`limit` (≤500). No match answers `{"total":0,"objectIDs":null}`.
  A broad title (`Window`, 886 hits) comes back in what looks like id order, not
  relevance, so the first ten are a lottery.
- `artistOrCulture=true&q=<artist>` finds an artist's objects (Robert Delaunay
  7, van Gogh 38); `title=true&q=<title>` searches titles only.
- `/v1/objects/<id>` carries `primaryImage` (original), `primaryImageSmall`
  (`web-large`, 599 px measured), `isPublicDomain`, `title`,
  `artistDisplayName`, `objectURL`, `objectWikidata_URL`. In-copyright objects
  answer with empty image fields (five Ellsworth Kelly objects). An unknown id is
  HTTP 404 `{"message":"ObjectID not found"}`. `/v1.1/objects` is 404.
- No pixel size anywhere. `images.metmuseum.org` honours `Range`; the
  start-of-frame of *Wheat Field with Cypresses* (4000 × 3184) sits at byte
  40,798, behind its metadata segments.
- The Met's web pages sit behind a Vercel bot checkpoint (HTTP 429 to a plain
  client), which is why in-copyright images need a private browser reader.
- Wikidata P3634 (Met object ID) has two formatters: the web page (preferred) and
  the API object URL (normal). `Registry.pages_about` reads `wdt:P1630`, best
  rank only, so it yields the web page.

## Requirements Confidence

**High** for the finder and reader; the rules below are the agent's unless marked.

- [DECISION: one holder, two plugins, disjoint claims. The public `met` plugin records and claims only the API object URL (`https://collectionapi.metmuseum.org/public/collection/v1/objects/<id>`); a private plugin reading the Met's web pages would claim `www.metmuseum.org` pages and record those | Arrt routes a stored row by URL, never by provider; with one URL claimed by both, `SOURCE_ORDER` picks one reader for both plugins' rows, and the API reader would answer "no image" for every in-copyright work the browser reader found. Disjoint shapes make each row reach the reader that recorded it, whatever the order | the owner raised the question 2026-10-06; agent's answer, owner can correct]
- [DECISION: consequence — the Met's web page from Wikidata stays unclaimed by `met`, so for a work still open it remains a sighting | that is true (nothing installed reads that page) and it is the count that says when the private reader is worth building | agent's]
- [DECISION: consequence — the public plugin's URL is not a page Wikidata records, so its instances get no title shortcut; title and artist are both compared | the Met's titles for its public-domain works are largely the ones it gave Wikidata; recording the web page instead would bring back the collision above | agent's]
- [DECISION: finding. With a QID: the Met ids in `pages_about`'s Met pages; an item with none falls back to search. Without a QID: search | Wikidata's Met ids are near-complete for paintings (the Met's 2017 upload), not for prints and drawings | agent's]
- [DECISION: search is the title search intersected with the artist search when an artist is known and the Met knows them; title alone, first ten, otherwise. At most ten objects read per work | the intersection fixes the id-ordered broad title; falling back when the artist search finds nobody keeps a differently spelt name from reading as "holds nothing" | agent's]
- [DECISION: an object with no `primaryImage` is not an image; an image's size is read from its JPEG head (ranged, at most 256 KiB); a head with no frame leaves the size unknown | the size is the original's, as the contract requires; unknown size is the Commons precedent | agent's]
- [DECISION: rights: `isPublicDomain` true → public domain, else unknown | the API's own flag, read for what it says | agent's]
- [DECISION: `met` never declines and has no off switch; leaving it out means uninstalling it (an image built without it) | it needs no key and names itself with the deployment's own agent, as every fetch does; a switch nobody asked for is a setting to document and test. Consequence: a deployment with nothing configured now has an image source, so `.env.example` and the startup test that described "no source at all" were rewritten to the deployment where every plugin declined | agent's, raised by the review; owner can ask for a switch]
- [DECISION: a search cut at one page (500 ids) cannot say the Met holds nothing: an empty title-and-artist intersection of a cut list falls back to the title's first results | an absence from a cut list is not evidence; paging an artist with thousands of prints costs a request per 500 for a fallback the identity check already covers | agent's, raised by the review]
- [ASSUMPTION: no collection browse in this plan | the owner asked for gaps and Asks, not browsing; the Art Institute's browse is the template when wanted]
- [ASSUMPTION: no change to `DEFAULT_SOURCE_ORDER` | order only breaks ties; `met` follows `commons`, `artic` by name]

**Not in this plan:** the private Met page reader (its own item, in the private
repository); browsing the Met's collection; `additionalImages`.

## Status

- [x] Chunk 01: The `met` plugin, its records and its live check
- [ ] Chunk 02: Settings › Sources lists every installed plugin and its version

### Chunk 01: The `met` plugin, its records and its live check

**Exposed API:** a new built-in source plugin `met` (entry point in
`arrt/pyproject.toml`). No HTTP or MCP surface changes.

Done when:

- `arrt/src/arrt/library/sources/met.py`: finder, reader, `claims`, `PLUGIN`,
  importing only `arrt.library.sources`.
- `claims` accepts the API object URL only (not the web page, not another host).
- The reader answers `direct(primaryImage)` on the image host, `none` for an
  object with no image or one the Met says is not found, and `ImageSearchFailure`
  for anything else.
- Recorded answers under `arrt/tests/fixtures/met/`; unit tests drive the real
  client through them, including the falsifying members (an in-copyright object
  among the hits, a hit by another artist, an image on another host, a head with
  no frame).
- `arrt/tests/live/test_met_shapes_are_still_real.py` under `live_museum`.
- Records: `met-api-findings.md`; `source-plugins.md` (the disjoint-claims rule);
  `docs/source-plugins.md` (built-ins); the entry-point test names `met`.

### Chunk 02: Settings › Sources lists every installed plugin and its version

The owner asked on 2026-10-06, while Chunk 01 was in review: "a settings page that
lists active plugins and their versions". System › Status already lists every
installed plugin with its state and faults, and no version or package.

- [DECISION: a new page, Settings › Sources, after Clients | the owner asked for a settings page; it mirrors Radarr's Settings › Indexers as Clients mirrors Download Clients. Status keeps its health panel: Sources is the inventory, Status is how they are doing | agent's, owner can correct]
- [DECISION: every installed plugin is listed, loaded or not, most preferred first | "active" read as installed: a declined plugin is the one whose setting the curator would look for here, and hiding it would make it look uninstalled | agent's]
- [DECISION: each shows its name, the distribution that registers it and that distribution's version, its state and reason, what it provides (finds images, finds pages, reads URLs, browses a collection, read from its parts), and the interface major it was written for; the page heads with the interface version Arrt provides | the version a curator compares is the package's; the interface major says whether an upgrade of Arrt would refuse it | agent's]
- [ASSUMPTION: read-only | ordering is `SOURCE_ORDER` and installing is an image build; neither is a page action]
- [DECISION: MCP and HTTP parity — `art_discovery(action='sources')` answers what `GET /api/sources` does, in the same field names and values | the owner's requirement, 2026-10-06, mid-build. On `art_discovery` because image sources are discovery's, beside `spend` | owner's requirement; placement agent's]

**Exposed API:** `GET /api/sources` (new) and `art_discovery(action='sources')`
(new): `interface_version` and `sources`, each a `SourcePluginOut`. `SourcePluginOut` gains `distribution`, `version`,
`api_major` and `provides`, so `GET /api/health`'s `sources` carries them too.

Done when:

- The loader records each plugin's distribution, version, interface major and
  parts; `PluginReading` carries them.
- `GET /api/sources` answers them; `api-contract.md` describes it.
- `#sources` renders the list, with a plugin that failed before any version or
  part could be read saying so in words.
- `information-architecture.md`: sidebar, the *arr table, and the three screen
  tables; `test_screen_tables.py`'s name map.
- Tests: the loader reads distribution and version from a real entry point and
  none from an injected one; the route and the tool over real HTTP, equal; the two
  projections equal value for value; the browser page (loaded, declined, failed;
  text, not markup).

- **Critic mode:** cumulative (the one boundary review covers both chunks)
