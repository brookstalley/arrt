---
artifact: build-plan
version: 1
scope: source-plugins
branch: plan/source-plugins
partition: "serial: 02 and 03 both rebuild the pool and acquisition seams that 01 lays down, and 04 documents what 01-03 settle"
depends_on:
  - artifact: source-plugins
  - artifact: re-architecture
governed_by:
  - artifact: security-model
    dispositions:
      - "§ Direction, outside text reaches the page as text → conforms: plugin titles and artists reach the client by the same path as a museum's"
      - "§ Direction, an outside image or link only from a named host or a checked identifier → conforms, and the plan keeps it so: plugin URLs and Wikidata formatter URLs are fetched by the server and never sent to the client as links (source-plugins.md § The Wikidata finder)"
      - "§ Supply Chain → amended (Chunk 04): an installed plugin is trusted code of the PyPI-wheel class, and § Source plugins says what installing one trusts; the owner chose in-process loading over isolation"
  - artifact: data-model
    dispositions:
      - "Identity is never a source URL → conforms: a sighting is keyed by the work, and its URL is an attribute"
      - "A work is distinct from an image of it → conforms: a sighting records a page, not an image of the work"
      - "Per-device runtime state never lives in the catalogue → inapplicable: nothing here is per device"
      - "Derived artifacts are regenerated, never transported → inapplicable: nothing here is rendered"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ Direction, spend ceilings enforced by the provider → conforms: nothing here spends, and the metered-plugin note defers the ceiling to the paid service (source-plugins.md § Not in version 1)"
  - artifact: architecture
    dispositions:
      - "§ Direction, operation logic only in the service layer → conforms: loading is wiring, and the sightings query is a service method the API binds"
      - "§ Direction, the Library/Programming seam → conforms: arrt.library.sources is Library-side, and Programming imports none of it (Chunk 01 confirms the import guard sees the new package)"
      - "§ Direction, the theme manifest file / the display renders its own label → inapplicable: nothing here reaches the Player"
  - artifact: project-preferences
    dispositions:
      - "Catch specific exceptions; broad catch needs the waiver → conforms by waiver: fault containment is one broad catch per plugin call site, each with its reason, logged at error and counted on the health panel"
      - "Hardware and network access sits behind an interface → conforms: finders and readers are that interface"
last_validated: null
---

# Build Plan — Source plugins

## What this plan is

The owner's rulings of 2026-10-03 (`re-architecture.md` § Sources are plugins)
built to the contract in `source-plugins.md`: finders and readers in Python
plugins, the Art Institute and Commons rebuilt as the examples, and Arrt finding
what Wikidata knows by itself.

| Chunk | What |
|---|---|
| 01 | The plugin interface and loader; the Art Institute and Commons load through it |
| 02 | Readers: acquisition resolves a URL through the reader that claims it |
| 03 | The Wikidata finder, and sightings of pages no reader claims |
| 04 | The author's guide, the private-plugin deployment shape, the security model |
| 05 | Deploy, and check against the corpus |

**Not in this plan** (each waits for the first plugin that needs it,
`source-plugins.md` § Not in version 1): plugins serving their own bytes,
metered spending, pasting a URL, Watches, and any new reader. The first new
readers are the next plan's, chosen by Chunk 03's sightings count, and the
private repository's.

**What I would do differently.** Two things the owner should weigh:

- **Chunk 03 adds the plan's one persisted format**, sightings. It could start as
  a log line and cost nothing to reverse. I keep it as a table because question 1
  ("which reader next?") is the measurement the procurement corpus otherwise does
  by hand, and because question 2 (installing a plugin improves the library at
  once) is the payoff of the whole design. Cut it to a log line if you would
  rather wait.
- **Question 2 is only acted on once the upgrade loop exists**, and that work
  is parked on `feature/upgrades` (4 commits never pushed, one of the session
  advisories). That branch's fate is worth deciding before Chunk 03.

## Requirements Confidence

Medium. The shape is ruled and the seams are read; these are mine and unconfirmed:

- [ASSUMPTION: "yes to existing being examples" means the Art Institute and Commons are rebuilt as plugins, and no local-folder plugin is added | MED impact | owner can correct]
- [ASSUMPTION: `Source.provider` keeps recording the finder's name, and the reader is chosen by the URL at fetch time, not stored. Today's rows (`artic`, `commons`, and the Google Arts & Culture rows) keep working unchanged | MED impact, a persisted shape | owner can correct]
- [ASSUMPTION: `SOURCE_ORDER` (plugin names, comma-separated) sets preference; unnamed plugins follow by name | LOW impact | owner can correct]
- [DECISION: a fault in a plugin is contained to the call, recorded as "could not be asked", logged at error and counted on the health panel; suites fail on any logged fault | one bad package must not stop every run, and today's propagation was built for code that was all Arrt's | owner can veto]
- [DECISION: a plugin that fails to load is left out, with Arrt starting without it and saying so on the health panel | a dark wall after an upgrade is worse than a missing source | owner can veto]
- [DECISION: the plugin interface is versioned `major.minor` from `1.0`; a different major is refused by name | an in-process interface that breaks silently fails inside a run | owner can veto]

**What would raise it:** the owner confirming the first assumption. The second is
checked mechanically in Chunk 02 against every stored source row.

## Status

- [x] Chunk 01: The plugin interface and loader
- [x] Chunk 02: Readers
- [x] Chunk 03: The Wikidata finder, and sightings
- [x] Chunk 04: The author's guide, deployment, security model
- [ ] Chunk 05: Deploy, and check against the corpus

### Chunk 01: The plugin interface and loader

Critic mode: final. The interface is the keystone everything else is built on,
and it is a public surface once a private plugin depends on it.

**Exposed API:** `arrt.library.sources`, the plugin interface.

- new `arrt/src/arrt/library/sources/`: the only import path for a plugin (under
  `arrt.library` so the Library/Programming import guard walks it). It exports
  `API_VERSION`, `SourceContext`, the plugin factory's signature and its "decline
  with a reason" answer, `Finder` (today's `ImageSearch.find_images` and
  `fetch_preview`), `ImageQuery`, `FoundImage`, `ImageSearchFailure`,
  `ImageQueryUnanswerable`, and `CollectionBrowse` with its types. The types
  move or are re-exported; their docstrings' contracts move with them unchanged.
- Entry-point group `arrt.sources`. `arrt/pyproject.toml` registers `commons`
  and `artic` there. `_image_sources` and `_collection` in `arrt/src/arrt/__main__.py`
  give way to the loader, and nothing in the wiring imports either built-in by
  module name.
- The loader: the major-version check; declines logged at info with their reason
  (replacing today's "none (ARTIC_USER_AGENT and WIKIDATA_USER_AGENT unset)"
  line); load failures logged at error and reported by `HealthService.observe`;
  `SOURCE_ORDER`.
- Fault containment in the pool, around every plugin call (`find_images`,
  `fetch_preview`, `browse`), with the broad-except waiver and
  `event=source.plugin_fault`. A per-plugin fault count reaches the health panel.
  A suite-wide fixture fails any test that logs one.
- Provider names are unchanged (`artic`, `commons`), because stored rows and
  tile routing key on them until Chunk 02.
- **Guards scoped to the old shape** (the learnings rule on moved code): the
  plane-isolation and Library/Programming import guards are re-read to confirm
  they see `arrt/src/arrt/library/sources/`; the held-out-artists guard already scans all of
  `arrt/src`. Every consumer listed by
  `grep -rln "discovery.artic\|discovery.commons\|ImageSearch\b\|build_image_search\|build_collection_browse"`
  over `arrt/` (2026-10-03: 30 files, mostly tests) is
  checked off.
- Tests:
  - A plugin given as an entry point loads, and one written for another major is
    refused by name.
  - A factory that raises leaves Arrt running, with the plugin named on the
    health panel.
  - A declining plugin is logged with its reason.
  - A finder that raises `KeyError` is recorded as could-not-be-asked, logged,
    and counted, while the other finders' answers stand.
  - The built-in plugins import nothing from `arrt` but `arrt.library.sources`,
    so the examples authors copy cannot reach past the interface. (Third-party
    libraries such as httpx are theirs to use.)
  - The existing phase 2, Get and browse suites pass unchanged.
  - The loader is tested with injected entry points; one test reads the
    installed `arrt` distribution's real entry points, because a typo in
    `pyproject.toml` passes every injected test.
- Artifacts: `project-state.yaml` § design_decisions records the plugin API's
  versioning and error model; `observability-strategy.md` gains the two health
  signals.

**Visual change:** yes. The health panel names a plugin that failed to load or
is faulting; an entry goes in `.prawduct/operator-verification.md`.

### Chunk 02: Readers

**Design, settled at the start of the chunk** (mine, 2026-10-03; it refines the
bullets below, which were written before the code was read):

- **Which plugin a URL needs is known even when that plugin is not loaded.** A
  `SourcePlugin` declares `claims(url) -> bool`: static, no I/O, available
  whether the factory loaded or declined. A loaded plugin that claims URLs
  provides a `reader`, and one with a reader declares `claims`. One reader per
  plugin, which may read many URL shapes.
- **`Reader.read(url) -> FetchLocator`**: `direct` (an image URL), `tiles` (a URL
  `dezoomify-rs` reads), or `none` (the page is the expected one and shows no
  image, with a reason). Could-not-be-asked raises `ImageSearchFailure`.
- **Acquisition routes a stored source by its URL:**
  - claimed by a loaded plugin: its reader decides the fetch;
  - claimed by a plugin that is installed and not loaded: a deployment fault
    naming the plugin and its reason (this generalises `RESOLUTION_REQUIRED`:
    the Art Institute without `ARTIC_USER_AGENT`);
  - claimed by none: fetched as recorded, as today. That covers the Google Arts
    & Culture rows and Commons' direct image URLs, which need no plugin.

  *Changed from the bullet below:* a source whose provider is not installed at
  all cannot be told from a 2024 seed provider (`google_arts_culture` was never a
  plugin), so it is fetched as recorded and journalled at INFO
  (`acquisition.unclaimed`), not WARNING, because it fires on every Commons fetch.
- **`Finder.tile_url` leaves the interface**, with `RESOLUTION_REQUIRED`, the
  pool's `tile_targets` and the container's `tile_targets`. The interface stays
  1.0, because it has not left this branch.
- **The Commons reader moves to Chunk 03.** Its input, a Commons file page, first
  exists when the Wikidata finder offers P18 as one. A reader with no URL to read
  would be built against a shape nothing produces. *(Descoped from this plan at
  Chunk 03, 2026-10-03: P18 stayed the Commons finder's, so that input never
  exists. See Chunk 03's design note.)*
- **The roster is the container's only source input** (carried below).
  `SourceRoster.of(...)` builds one from parts without entry points, for tests
  and for anything that assembles sources by hand.

**Carried from Chunk 01's final review** (`rev` of 2026-10-03, 0 blocking; the
observations below are real, and land here so this chunk's review covers them):

- **Containment has holes.**
  - The loader reads a part's `provider` outside any `try`, so a plugin whose
    `provider` raises stops startup.
  - A finder's answer is not checked: an image under another plugin's name is
    stored as that plugin's; an unknown name raises `ValueError` and a `None`
    answer `TypeError`, both outside containment.
  - A part that is not a `Finder` or `CollectionBrowse` loads, then faults on
    every call.

  Contain all three, and check the answer's shape.
- **`Services.bind` takes `image_sources`, `collection` and `sources`, which
  can disagree.** Make the roster the only input.
- **A plugin's error text reaches the log, `/api/health` and the panel
  unfiltered.** An HTTP error carries its request URL, so a key in a query string
  would be published, against "no secret in a log line". Strip query strings, or
  show only the exception type, on the panel.
- **The wiring in `__main__._sources` is untested:** four of its lines can each
  be deleted with every suite green. Add a test that builds the services from
  loaded plugins and reads `/api/health`.
- **The suite-wide fault guard:**
  - It hooks a hard-coded logger name, so it goes quiet if this chunk moves the
    containment. Derive the name instead.
  - It has been watched failing only by hand; keep that check in the suite.
- **The built-ins' import guard misses relative imports.**
- **Stale names:**
  - `architecture.md` still says `ImageSearch`, and describes sources wired in
    the entry point.
  - The examples are still called `ArticImageSearch` and `CommonsImageSearch`.
    Rename them with the reader work.
- **The one-finder rule is the agent's call;** mark it *Mine* in `source-plugins.md`.
- **Smaller fixes:**
  - A `SOURCE_ORDER` name that no installed plugin has should be logged.
  - Log before each factory runs, so a hang names its plugin.
  - The startup line misreports a plugin that offers only a collection.

- `Reader` joins `arrt.library.sources`: recognise a URL (or say *not mine*), then return
  a fetch locator (`direct`, `tiles`, or `none`), with the size and the holder's
  title and artist where the page carries them.
- The Art Institute plugin gains a reader for its object URLs (today's
  `tile_url`). *(The Commons reader moved to Chunk 03, and was descoped there;
  see both design notes.)*
- Acquisition asks the readers in order for a stored source's URL:
  - the first that claims it decides the fetch;
  - a URL no reader claims is fetched as recorded, as today (the Google Arts &
    Culture rows);
  - a URL claimed by a plugin that is installed and not loaded is a deployment
    fault naming the plugin. *(Changed at design: a provider not installed at
    all is fetched as recorded; see the design note.)*

  `RESOLUTION_REQUIRED` and the provider-keyed `tile_targets` retire, with
  their docstrings' reasons carried to the reader contract.
- Arrt still fetches every locator, through `check_fetchable` and the existing
  bounds.
- Tests:
  - **Every stored source shape resolves exactly as before:** an `artic` object
    URL to the same IIIF target, a Commons file to the same direct URL, a Google
    Arts & Culture page to itself.
    *Descoped from this chunk, 2026-10-03, and moved to Chunk 05:* the fixtures
    were to come from a copy of the NAS catalogue's `sources` table, and this
    session has no access to the NAS. The shapes were taken instead from the code
    that writes them: the 2024 seed's two known hosts (`arrt/src/arrt/seed/legacy.py`,
    `_KNOWN_HOSTS`, over `all.json`: 33 `www.artic.edu` and 8
    `artsandculture.google.com` rows, all `dezoomify`), and the two finders'
    recorded URLs (Art Institute API links, Commons direct image URLs). Chunk 05
    surveys the live table before deploying.
  - Two readers claiming one URL go to the one first in order.
  - An `artic` row whose plugin declined is a deployment fault, not a failed
    source.
  - A reader whose page is not the page it expects raises could-not-be-asked
    (gap 5).

### Chunk 03: The Wikidata finder, and sightings

**Design, settled at the start of the chunk** (the owner's choice of three,
2026-10-03; the rest is mine). It replaces the bullets below where they differ:

- **Commons keeps its finder, and no Commons reader is built in this plan.** As
  the bullets were written, a page the finder offers would reach a reader, and a
  reader's answer carries no size and none of the holder's own words, so phase 2
  would drop every such image. Taking P18 into the Wikidata finder would put
  Commons' size rule in two plugins that may not import each other. Bringing the
  paste-URL addition forward, so readers report size, would change both sides of
  the interface. The owner chose the smallest change: P18 stays the Commons
  finder's, and a curator sees no difference.
- **The Wikidata finder offers pages only:** every external-identifier claim
  whose property has a formatter URL, and every P973. It never offers P18.
- **A finder's answer may carry `FoundPage`s beside its `FoundImage`s**: a page
  about the work that the finder found and does not read. The pool carries them
  apart from the images, and phase 2 passes them on untouched. The interface
  stays 1.0, because it has not left this branch.
- **Arrt routes each page:** one that no installed plugin claims is a sighting;
  one that a plugin claims is journalled and left to that plugin. Turning a
  claimed page into an image needs a reader that reports size, which is the
  paste-URL addition (`source-plugins.md` § Not in version 1).
- **A sighting is keyed by the work's Wikidata item**, the only key the Wikidata
  finder has. A page offered for a work with no item is journalled, not stored.
- **Sightings store the item and the URL, and nothing else.** Question 1 counts
  hosts, which are read from the URL. Question 2 gives each URL to `claims`.
  Question 3 is a read by item.
- **Question 1 is answered over works still open:** wanted, or unresolved with
  their verdict pending. A work the catalogue holds is left out, and so is a
  page that an installed plugin claims now.
- **There is no caching.** The bullet below assumed the registry client caches;
  it does not, because caching is done in the services, which a plugin cannot
  reach. One query per work per resolution attempt needs none.
- **Measured 2026-10-03 against the live service**, on four corpus items:
  - besides holders' pages, items carry encyclopedias, catalogues raisonnés and
    a Google search link (P646, Freebase), so the host count will include noise.
    Chunk 05 reads it with that in mind;
  - the Athenaeum's formatter URL goes through `web.archive.org`;
  - one formatter (BabelNet's) is not a well-formed URL template;
  - values carry characters a URL must encode (`fr:La_Persistance_de_la_mémoire`).

  *Drowning Girl* (`Q5308687`) carries MoMA (P2014), the Lichtenstein catalogue
  raisonné (P11885) and P646. The recorded answers are the tests' fixtures.

- A built-in `wikidata` plugin's finder: for a query carrying a QID, every
  external-identifier claim whose property has a formatter URL (P1630), every
  P973, and P18 as a Commons file page. The Commons plugin keeps only its reader,
  because finding a Commons image becomes this finder's P18. Formatter URLs are
  checked as URLs before use, and the registry client's existing caching and
  user agent apply. *(Changed at design: P18 stays the Commons finder's, no
  Commons reader is built, and there is no caching to apply. The registry's user
  agent does apply.)*
- Each page found goes to the readers. A page none claims is stored as a
  sighting. *(A page a plugin claims is journalled and left to it.)*
- **Persisted format, enumerated before its fields** (the planning rule on
  lock-in). Sightings answer three questions:
  1. Hosts by count, over works that are `wanted` or unresolved.
  2. The sightings a given reader now claims.
  3. A work's sightings.

  Fields follow from those three and nothing else, with a migration and its
  idempotence test, varying the inputs between runs (the learnings rule).
- Question 1 as a service method, `GET /api/sightings/hosts`, and the matching
  MCP read action.
- Tests:
  - On a recorded Wikidata item fixture for *Drowning Girl* (`Q5308687`), the
    finder offers the MoMA page through P2014's formatter URL.
  - The fixture also carries a reproduction site's ID; it is offered too, and
    left to the readers. *(The recording for* Drowning Girl *carries the
    Lichtenstein catalogue raisonné and a Google link. The Athenaeum and HA! are
    on* The Persistence of Memory*'s, which is recorded too.)*
  - An item with no external IDs offers only its P18 image. *(Changed at
    design: through the pool, the image is the Commons finder's, and the
    Wikidata finder offers nothing.)*
  - A page no reader claims becomes exactly one sighting, and the same page
    found twice stays one.
  - The hosts query counts only `wanted` and unresolved works: a held work's
    sighting is in the fixture and absent from the count.
  - No sighting URL reaches any API response as a link field; the host is
    reported as a name.

**Foreign API:** Wikidata (formatter URLs on property entities).

### Chunk 04: The author's guide, deployment, security model

Type: doc-only.

- new `docs/source-plugins.md`, for people writing a plugin:
  - the entry point and the factory;
  - `arrt.library.sources` and nothing else;
  - the three answers and gap 5's rule;
  - what Arrt fetches and checks for them;
  - how to test against the built-ins as examples.

  It points to `source-plugins.md` for the contract rather than copying it.
- `deploy/README.md`: the private-plugin image shape (`FROM arrt:<commit>`, the
  plugin installed into `/opt/venv`), with no house values.
- `security-model.md`: a § Source plugins, and the Supply Chain amendment from
  this plan's dispositions. It must say what installing a plugin trusts.

### Chunk 05: Deploy, and check against the corpus

- **Before deploying, survey the NAS catalogue's `sources` table** (moved from
  Chunk 02): count rows by provider, acquisition method and URL shape (host and
  path pattern, never a full house URL, since this repository is public). Check
  each shape against `SourceRoster.route`: claimed by a loaded plugin, fetched as
  recorded, or a deployment fault. A shape the suite does not cover gets a test
  before the deploy.

  *Done 2026-10-03, read-only.* 40 rows, two shapes, all `dezoomify`, none yet
  fetched:

  | Rows | Provider | Shape | Route, Art Institute configured | Route, unset |
  |---|---|---|---|---|
  | 32 | `artic` | `https://www.artic.edu/artworks/<n>/<slug>` | the `artic` reader | deployment fault naming `artic` |
  | 8 | `google_arts_culture` | `https://artsandculture.google.com/asset/<slug>/<id>` | fetched as recorded | fetched as recorded |

  Each URL was routed through the installed plugins, not the shape alone. Both
  shapes were already in the suite (`test_acquisition_reading.py`), so no test
  was owed. No Commons row is stored.

- A `live_museum` test over the corpus's rows found in run 1 (1, 2, 3, 9, 19, 35)
  gets the same source and size through the plugins. It runs by hand with `-n0`.
  *Done:* `tests/live/test_corpus_finds_through_the_plugins.py`, passing
  2026-10-03, and seen failing on a wrong size.
- **Carried from Chunk 03's review:** `pages_about` gets a live case in
  `arrt/tests/live/test_wikidata_shapes_are_still_real.py` (*Drowning Girl*
  gives a `www.moma.org` page), so the 2026-10-03 measurement stays a check
  rather than a fixture. *Done, and seen failing on a wrong ID.*
- Deploy to the NAS. The startup log names the loaded plugins, and the health
  panel shows them. *Done 2026-10-03:* image `e51adfb`, after a catalogue copy
  (`pre-source-plugins-<timestamp>.sqlite` in the backups directory; the way
  back is `bb021bb`). `/api/health` reports all three plugins loaded, with no
  faults. The startup log was not read, because the container's logs need root
  on the NAS.
- Get the corpus's 50 QIDs again, through a run that writes nothing new for
  works already held. Record in `procurement-corpus.md` § Results, as run 2:
  - the sightings-by-host count;
  - how it compares with the corpus's "museum-page" holders (MoMA 8, the
    Pompidou 3, SFMOMA 3).

  That count is step 3's first measurement, and the next plan's input.

  *Changed, and done 2026-10-03* (mine): a re-search of run 1's 39 unresolved
  works, not a Get of all 50. A Get would have put a second copy of the 11 finds
  into To review, and the host count covers only open works, which the 11 are
  not. The live test above re-checks them. Recorded as run 2: MoMA 9, the Met 4,
  navigart.fr 3 (one platform, three collections), SFMOMA 3.
- The owner looks at the health panel. That check is the
  `operator-verification.md` entry.

## Verification strategy

`cd arrt && uv run pytest`, and the root suite for the artifact-reading guards,
for every chunk; `-m browser` for Chunk 01's health panel change. Chunk 02's
regression fixtures are drawn from the code that writes source rows, and Chunk
05 checks them against the real catalogue's stored rows. Chunk 05 is the live
check and the owner's look.

## Governance checkpoints

- **After Chunk 01**, a `final` review of the interface before anything is built
  on it.
- **Chunks 02 and 03** get per-chunk reviews.
- **The last chunk is followed by one `cumulative` review before the PR.**
