---
artifact: build-plan
version: 1
scope: topics-and-destinations
branch: feature/topics-and-destinations
partition: 01 ∥ 03, then 02 ∥ 04 ∥ 03b ∥ 03c, then 05, each chunk starting when what it needs is merged. 03 touches only `library/registry/wikidata.py`, a new topic service and `wikidata-findings.md`, which no other chunk in its wave edits; 03b owns `wikidata.py`'s rules, which 04 is barred from; 03c is a new module plus the Artist page's adoption, and adopts it in `topics.py` after 04 merges. 04 waits for 01 because both edit the catalogue store and `library/facade.py`; 02 waits for 01's API; 05 waits for 02 and 04 and shares `core/getting.js` and `app.js` with 02. Each delegate works in its own worktree and branch; the coordinator merges, runs the suites and the Critic per wave (amended 2026-10-02, owner asked for parallel subagents)
depends_on:
  - artifact: ia-proposal
  - artifact: information-architecture
  - artifact: build-plan-ia-foundations
  - artifact: build-plan-get-and-ask
  - artifact: wikidata-findings
  - artifact: data-model
governed_by:
  - artifact: architecture
    dispositions:
      - "Library/Programming seam rule 1, one-way imports through the facade → binds Chunk 01: the Library records a Get's destination as an opaque theme id and never imports Programming; Programming learns it through the facade"
      - "seam rule 2, the facade is written as if remote → binds Chunk 01: the facade answers 'where should these accepted works go' for a list of ids with plain data, and is idempotent"
      - "seam rule 3, no new cross-seam foreign keys (interim rule) → binds Chunk 01: `discovery_runs.destination_theme_id` is an opaque reference that may fail to resolve, with no REFERENCES clause"
      - "seam rule 4, Library changes reach Programming as events; Programming reconciles at start → binds Chunk 01: the acceptance event is unchanged; the handler and `catch_up_offers` (formerly `catch_up_the_default`) both ask the facade for the destination, so a lost event and a delivered one land the work in the same theme"
      - "RULING 2026-09-30: composing two services is still dispatch; a binding that branches on one call's result is a violation → binds Chunks 01 and 02: `POST /api/gets` with a theme checks the theme exists (Programming) and then starts the Get (Library), with no branch; creating a new theme by name is the client's (or agent's) earlier call to `POST /api/themes`, never a branch in the binding"
      - "operation logic lives only in the service layer → binds Chunks 01, 03 and 04: destination, topic lookup and the topic index are services; HTTP and MCP are thin bindings"
  - artifact: information-architecture
    dispositions:
      - "the curation surface is laid out like the *arr apps; no new top-level section without a precedent or a ruling (§ Direction) → conforms: Topics goes under Library (ruling 9). The destination control follows Radarr's Add dialog, where the root folder is chosen when a movie is added"
      - "one row per screen in the three tables, held by `tests/preferences/test_screen_tables.py` → binds Chunk 05"
  - artifact: security-model
    dispositions:
      - "outside text reaches the page as text; an outside image or link only from a named host or a checked id (§ Direction) → binds Chunks 03-05: topic labels, descriptions and work titles are registry text; previews come through the preview cache as today; a topic's Wikidata link is built from a checked QID"
  - artifact: data-model
    dispositions:
      - "identity is never a source URL → conforms: a topic's identity is its Wikidata QID (ruling 7; P6 'one page in every state')"
      - "a persisted format is a lock-in decision; enumerate the questions first → binds Chunks 01 and 04: the questions are listed in each chunk, and become Q-rows in `data-model.md` § What this data must answer"
  - artifact: observability-strategy
    dispositions:
      - "registry features say they are off when no User-Agent is configured → binds Chunks 03-05: with no `WIKIDATA_USER_AGENT`, Library › Topics and a Topic page say topics need it, and the topic sweep logs that it is off, once, at start"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider → inapplicable because nothing here spends: Wikidata is unmetered and a Get spends nothing"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA; colour never the sole carrier of state → binds Chunks 02 and 05: the destination is a labelled select whose confirmation names the theme in words; a topic's works carry their state as glyph and word, as the Artist page's do"
last_validated: null
---

# Build Plan — Topics and destinations

## What this plan is

Plan 3 of `build-plan-ia-foundations.md` § What comes after, renamed by the
owner's rulings of 2026-10-02 below. Two things a curator cannot do today:

- **Say where a Get's works go.** Every accepted work joins the default theme
  (ruling 8). A Get now names its **destination**: *All works* by default, or any
  theme, new or existing. Works sent anywhere else stay out of the everyday
  rotation. This is what ruling 5a's "excursion" asked for, without the word.
- **Browse by topic.** A period, movement, subject or medium has a page, like a
  genre: your works in it, then the works it is known for, then its artists.
  From there, select and Get, into a theme named after the topic.

| Chunk | What | Ruling |
|---|---|---|
| 01 | A Get's destination, from HTTP and MCP | 5a, 8; owner 2026-10-02 |
| 02 | The destination in the client, and in Review | 5a; owner 2026-10-02 |
| 03 | Topics in the registry: one topic, its works, its artists, topic search | P6, owner 2026-10-02 |
| 04 | Your works' topics, as facets, and the topic index | owner 2026-10-02 |
| 05 | Library › Topics and the Topic page | 9; owner 2026-10-02 |

**Not in this plan:**
- **The taste half of ruling 5b.** Nothing reads taste, and acceptance writes
  none (`DiscoveryService._accept`; `user-scenarios.md` § Tested). This plan only
  records each Get's destination where the taste reader can find it. Plan 4
  decides what a destination means for taste (owner, 2026-10-02).
- **Hanging on every wall at once, or for a duration**: wave 4 (ruling 6).
- **Archiving a selection**: plan 5, Walls.
- **Linking an Artworks facet value to its Topic page.** Chunk 04 fills the
  facet rail; the link is a small follow-on once the page exists, and is left out
  to keep Chunk 05 one review.

## The owner's rulings, 2026-10-02

- **"Excursion" becomes a destination on every Get.** Asked *"Is an excursion
  really just a playlist?"*; the builder's answer was that after acceptance it is
  exactly a theme, and that only the moment of acceptance differs. Offered a
  destination on every Get, defaulting to *All works*, with the taste half left
  to plan 4, the owner chose it. Ruling 5a stands in substance (the works form a
  theme and are not in the default one); the word does not reach the interface.
- **Library › Topics lists your library's topics**, each with a count, with a
  search for any other topic. Chosen over a search box alone and a fixed list.
- **Topic kinds: period, movement, subject and medium.** The builder recommended
  leaving medium out; the owner chose to include it.
- **A destination defaults to the topic's name on a Topic page**, and to *All
  works* elsewhere. A name that is already a theme joins that theme.

## The owner's answers to Chunk 03's measurement, 2026-10-02

Asked after the twenty-topic measurement (`wikidata-findings.md` § Topics):

- **Period speed: keep answers on disk, "as a general purpose cache system, not
  specific to Wikidata"** (owner's words). Chosen over narrowing the query and
  over accepting slow pages. Chunk 03c.
- **A named period says "from its years".** Its works stay matched by date, and
  the section is headed with the years so it claims no more than it checks.
  Narrowing by place was offered and not chosen. Chunk 05.
- **A topic's artists are ranked by how many of their works are in the topic**,
  fame breaking ties. Chosen over an occupation filter. Chunk 03b.
- **Search drops the "start and end time" clause and non-visual movements.**
  Both recommended, both chosen. Chunk 03b.
- **Asked again after Chunk 03b's re-measurement: rank a topic's artists by the
  fame of their works in it** (the sum of those works' sitelinks), chosen over
  counting only works with an article, keeping the count, and returning to the
  artist's own fame. The count, which the builder had recommended, let bulk
  catalogue imports lead (Philip Galle second in the 16th century, Leonardo,
  Michelangelo and Raphael out). The owner also kept the years heading on every
  period, and asked for the empty artist and palette facets to be backlogged.
  Chunk 03d.

## The owner's review of the screens, 2026-10-02

Looked over on a catalogue copy after Chunk 05:

- **Library › Topics and *Find a topic*: good.** The page moves about as it
  fills; to be organised later, not now.
- **A held work with no image.** *The Hunters in the Snow* is *In your library*
  with "No master image". Accepting a work never acquires its master: the only
  caller of `AcquisitionService.acquire` is MCP's `retry_acquisition`, since
  acquisition was built (archived plan Chunk 18, whose tests called `acquire`
  directly). Not this plan's; filed for its own.
- **On a Topic page, *Add to* should default to the topic's name, and the name
  field should be blank and hidden unless *New theme…* is chosen.** Chunk 06.
- **The typeahead showed only *Ask* and *Search* the first time.** Chunk 05
  joined the topic search to the registry search, so Wikidata's works and artists
  (0.7 s) waited for the topic search (5 s cold), with nothing on screen saying
  so. Chunk 06.
- Phone width: good.
- **Later the same day, on a Get of *The Magpie*:** the Get's page says "1 work"
  and offers *Review these works*, a second page for works the curator already
  chose; Review's card is a fixed narrow column, and with *Scans* open each
  scan's facts wrap in a column a few characters wide (a one-work card ran to
  about 7,000 px at 1280); the card should say the scan's resolution, and
  "native — would show at 28.2″" means nothing without knowing the panel (it is
  the long edge on the one panel this server is configured for, after the mat);
  clicking the image should enlarge it without leaving the page. Asked, the
  owner chose: **review a Get on its own page**; **pixels, and drop the inches**
  (a per-wall fit returns with per-wall geometry, re-architecture wave 4); and
  **on this branch, before the PR**. Chunk 07.

## What I would do differently

- **Medium is the weakest of the four kinds.** Wikidata's medium property (`P186`)
  holds materials: oil paint, canvas, panel. A topic page for *canvas* is noise.
  What reads as a medium to a curator, woodcut or watercolour or pastel, is a
  *kind of work* (`P31`: woodcut print Q18219090, watercolor painting Q18761202,
  pastel artwork Q12043905). So a medium topic here is a work type, and
  materials are not topics. Chunk 03 measures it before building it.
- **Ship Chunks 01 and 02 even if topics slip.** A destination is useful from the
  Artist page and the results page today, and it is the half of S12 that touches
  the rotation.
- **Fill the facet rail from the registry, not by inference.** `work_facets` has
  existed since v1 with nothing writing it, waiting for "inference from museum
  text and a model's answer". Wikidata's facts are free, sourced and citable, so
  Chunk 04 writes them as `sourced` and leaves inference for later. The Artworks
  rail lights up as a side effect.

## Requirements Confidence

**Medium.** The rulings settle what to build. Three things are measured on a
handful of topics only (2026-10-02, probes in this plan's session):

- **Period:** 16th-century paintings with an image, ranked by sitelinks, came back
  in 14 s cold and 0.2 s warm; one row per maker, so *Salvator Mundi* appears for
  Leonardo and for "Leonardeschi" (as `ia-proposal.md` § Topic found).
- **Movement:** `P135` sits on **artists**, not works. Asked for works with
  `P135` = Impressionism (Q40415), the top 30 were all people (Matisse, Mirbeau,
  Monet). Paintings with an image by artists in the movement, ranked by sitelinks,
  read well (*Impression, Sunrise*, *Luncheon on the Grass*, *Bal du moulin de la
  Galette*) in 1.1 s.
- **Subject:** depicts (`P180`) = winter (Q1311) gave *The Hunters in the Snow*
  first, in 0.4 s. Genre (`P136`) = still life (Q170571) is messier: *Luncheon on
  the Grass* came first.
- **Medium:** woodcut print (Q18219090) as a kind of work gave Dürer's *The
  Rhinoceros* and Hokusai's *The Dream of the Fisherman's Wife* first, in 1.0 s.
  *The Flammarion engraving*'s maker came back as an unnamed blank node (an
  "unknown value" statement), not a person. (A first probe used Q18218093, typed
  from memory: it is *etching print*, and its results were reported to the owner
  as woodcuts before being caught. Corrected in the same conversation.)

Open assumptions:

- `[ASSUMPTION: a destination is stored on the Get's run as an opaque theme id. No destination means the default theme, exactly as today; a run that names one sends its accepted works there and records them as offered to the default, so the startup catch-up never sweeps them into the rotation | HIGH impact | user can correct]`
- `[ASSUMPTION: if the destination theme has been deleted by the time a work is accepted, the work joins no theme and is recorded as offered to the default. The curator chose 'not the rotation' when they started the Get, and a deleted theme does not reverse that. The log says so | MED impact | user can correct]`
- `[ASSUMPTION: a destination applies to Gets only. A discovery run from Ask keeps joining the default theme. Ask's commit card could gain the same control later | LOW impact | user can correct]`
- `[ASSUMPTION: a topic's kind comes from what Wikidata says it is (P31): a century, decade or historical period is a period (the 'or anything with a start and end time' clause was dropped by the owner on 2026-10-02, Chunk 03b); an art movement or style is a movement; a subclass of a work of visual art is a medium; anything else is a subject. Chunk 03 measures this on twenty topics before trusting it | HIGH impact | user can correct]`
- `[ASSUMPTION: a movement's works are works by its artists (P170 → P135). A subject's works are works that depict it or have it as their genre (P180 or P136). A period's works have an inception (P571) inside its start and end. A medium's works are instances of it (P31) | HIGH impact | user can correct]`
- `[ASSUMPTION: representative works are works of visual art (the ten classes `works_matching` already filters by), ranked by sitelinks, top 50, each with its state (Held, Image found, No image known). Requiring an image would hide what a Get cannot supply, which the Artist page shows rather than hides | MED impact | user can correct]`
- `[ASSUMPTION: your works' topics come from the registry only: a work's own QID gives its period, subjects and medium; its artist's QID gives its movements. A held work with no QID and an artist with none has no topics. 22 of 40 held works and 24 of 31 artists on the owner's catalogue copy carry a QID | MED impact | user can correct]`
- `[ASSUMPTION: a period facet is the century only. Decades and named periods (Dutch Golden Age) have Topic pages, reached by search, but are not facets, so the rail stays short | LOW impact | user can correct]`

**What would raise it:** Chunk 03's twenty-topic measurement of kind and
coverage.

**Chunk 03's measurement (2026-10-02, `wikidata-findings.md` § Topics):** the
kind rule was wrong on 0 of 20, so it stands. It raised five questions, which
the owner answered the same day (§ The owner's answers to Chunk 03's
measurement): period works are slow (7-26 s, some time out);
a named period is matched by its dates only (Dutch Golden Age lists *Las
Meninas*); the "start and end time" clause admits exhibitions and wars to
search and makes Romanticism a period; ranking artists by sitelinks puts
non-artists first (Franklin for woodcut); search offers non-visual movements
(impressionism in music).

## Status

- [x] Chunk 01: A Get's destination, from HTTP and MCP
- [x] Chunk 02: The destination in the client, and in Review
- [x] Chunk 03: Topics in the registry
- [x] Chunk 03b: Topic rules, as the owner answered
- [x] Chunk 03c: Answers kept across restarts
- [x] Chunk 04: Your works' topics, and the topic index
- [x] Chunk 03d: A topic's artists ranked by the fame of their works in it
- [x] Chunk 05: Library › Topics and the Topic page
- [x] Chunk 06: The owner's review of the screens
- [x] Chunk 07: Review on a Get's own page, wide, with its scans readable

### Chunk 01: A Get's destination, from HTTP and MCP

**Exposed API:** `POST /api/gets`, `art_discovery(action='get')`

**The questions the stored destination answers** (a persisted format; these become
Q-rows in `data-model.md` § What this data must answer):
1. Which theme does a work accepted from this Get join? (Programming, at
   acceptance and at every start.)
2. Did this acceptance go into the everyday rotation? (Plan 4's taste reader;
   no destination means it did.)
3. Which Gets were sent somewhere other than the rotation? (Queue and Review show
   it.)

- **Library:** `discovery_runs` gains `destination_theme_id TEXT`, nullable, with
  no `REFERENCES` (seam rule 3). `DiscoveryService.start_get_run`, `runner.get`
  and `GetService.start` take an optional `destination_theme_id`. The run record
  and its API model carry it.
- **Facade:** `destinations(work_ids)` answers each accepted work id with its
  run's destination, or none: work → candidate (`candidate_works.artwork_id`) →
  run. A work accepted before this column existed, or from a discovery run, has
  none.
- **Programming:** `offer_to_default` becomes `offer_destinations`, the offer for a work's destination.
  It asks the facade, then adds the work to the destination theme if it still
  exists, to the default otherwise, and records the offer either way, in one
  transaction as today. `on_work_changed` and `catch_up_offers` both go
  through it, so a lost event lands the work where a delivered one would.
- **Surfaces:** `StartGet` gains optional `theme_id`; `art_discovery(action='get')`
  gains optional `theme_id`. The binding gets the theme (unknown → the existing
  not-found refusal) and then starts the Get, two calls with no branch.
- **Retiring "excursion":** grep the whole repo for `excursion` and amend each live
  artifact to *destination*, with a dated pointer to this plan's rulings
  (`ia-proposal.md` § Theme and S12, `user-scenarios.md` S12,
  `build-plan-ia-foundations.md` § What comes after and its assumption,
  `information-architecture.md`'s Direction note). Archived plans and the
  rulings table keep their wording, as records.

**Done when:**
1. Tests, each watched failing: a Get with a theme puts an accepted work in that
   theme and not the default; a Get without one puts it in the default; the
   startup catch-up does the same for a work whose event was lost; a work whose
   destination theme was deleted joins no theme and is not swept into the default
   at the next start; an unknown theme refuses the Get over HTTP and MCP; a
   restored work is offered nothing.
2. A test that the Library side still imports nothing from Programming
   (`test_seam_imports.py` passes unchanged).
3. Root and curation suites pass; mutations of the destination branch, the
   offer record and the facade join each turn a test red.

### Chunk 02: The destination in the client, and in Review

**Visual change:** yes

- **`core/getting.js`:** the Get control gains **Add to**, a labelled select
  listing *All works* (the default theme, first and selected), then every other
  theme, then *New theme…*, which reveals a name field. A caller may pass a
  default name; when it is given, it is offered and selected as "<name> (new
  theme)" with the name field hidden (Chunk 06, the owner's review), or the
  existing theme of that name is selected if there is one (the owner's
  ruling: a taken name joins). A new name is created with `POST /api/themes`
  before the Get starts.
- **The confirmation names the destination in words**: "Getting 3 works into
  *16th century*", and "into *All works*" by default.
- **Queue, the run page and Review** say where a Get's works go, by theme name, or
  "a theme that has been deleted".
- An operator-verification entry for the control at 1280 and 375 px.

**Done when:**
1. Browser tests, each watched failing: the default sends no `theme_id`; picking a
   theme sends its id; a new name creates the theme first and sends the new id; a
   default name that is already a theme selects it rather than creating a second;
   the confirmation names the theme; Review names the destination.
2. Driven on a catalogue copy: a Get into a new theme, accepted, lands in that
   theme and not in *All works*.
3. All suites and the browser suite pass.

### Chunk 03: Topics in the registry

**Foreign API:** Wikidata (SPARQL; `wbsearchentities` through `wikibase:mwapi`)

- **New registry calls** in `library/registry/wikidata.py`, each through `_select`
  and its rules:
  - `topic(qid)`: label, description, kind (the assumption above), and for a
    period its start and end.
  - `topic_works(topic, limit)`: works of visual art in the topic, ranked by
    sitelinks, with creator, inception and whether an image exists, one row per
    work (makers joined, never a row per maker).
  - `topic_artists(topic, limit)`: the artists most represented among the
    topic's works, or for a movement its artists, ranked by sitelinks (by
    their works in the topic since Chunk 03b, by those works' summed sitelinks
    since Chunk 03d), with the count of their works
    that have an image (as Similar artists shows).
  - `topics_named(text)`: topic candidates for a typed name, filtered to the four
    kinds, so `renaissance` offers the movement and not the political party.
  - `topics_of(work_qids, artist_qids)`: for held works, each work's period,
    subjects and medium, and each artist's movements.
- **`TopicService`** in `library/services/`, over those calls, with the cache the
  Artist page's sections use, remembered per topic.
- `wikidata-findings.md` gains § Topics: the measurements below, verbatim from
  the probe's output.

**Done when:**
0. verify-api: for twenty topics read from `wbsearchentities` on the day (five of
   each kind, QIDs copied from its output, never typed: a century, a decade, a
   named period, movements old and modern, subjects concrete and abstract, work
   types), record the kind the P31 rule assigns against the kind a person would,
   the top ten works and their time cold and warm, and the time of
   `topics_named` and `topics_of` over the catalogue copy's QIDs. A kind rule
   wrong on more than two of twenty is rewritten before building.
1. Unit tests over recorded answers, each watched failing: kind assignment for
   each kind and for an item with two kinds (Baroque is a movement and a period);
   one row per work when a work has two makers; a maker recorded as unknown
   value (a blank node) shown as an unknown maker, never as its URL; a topic with
   no works; a label-less work shown by QID as elsewhere.
2. A `live_museum`-marked test keeps the shapes checked.
3. Root and curation suites pass.

### Chunk 03b: Topic rules, as the owner answered

**Foreign API:** Wikidata

- **The kind rule loses its "has a start and an end time" clause.** A period is
  an instance of a century, a decade or a historical period (or a subclass).
- **`topics_named` drops movements no visual artwork's maker belongs to**: a
  movement is offered only if some work of visual art has a maker whose `P135`
  is it, the same shape as the subject check.
- **`topic_artists` ranks by the count of the artist's works in the topic**,
  sitelinks breaking ties; for a movement, its artists' works.
- `wikidata-findings.md` § Topics records the re-measurement beside the first.

**Done when:**
0. verify-api: re-run the twenty topics of Chunk 03's table (QIDs from that
   table, which were copied from the service) for kind and top ten artists, and
   the search names that admitted an exhibition, a war, clothing and a music
   movement; record before and after.
1. Unit tests over recorded answers, each watched failing: an item with start
   and end time and no period class is not a period; Romanticism is a movement
   only; a music movement is not offered; artists come back in works-count order
   with the tie broken by sitelinks.
2. The `live_museum` shape test still passes.

### Chunk 03d: A topic's artists ranked by the fame of their works in it

**Foreign API:** Wikidata

- **`topic_artists` ranks by the sum of the sitelinks of the artist's works in
  the topic**, the artist's own sitelinks breaking ties; for a movement, its
  artists' works. The count of their works with an image is still reported.
- The kept-answers namespace for a topic's artists changes name, so an answer
  ranked by the old rule is never served as the new one.
- `wikidata-findings.md` § Topics records the third measurement beside the two
  before it.

**Done when:**
0. verify-api: the twenty topics of Chunk 03's table, top ten artists and time,
   against Chunk 03b's; say for each period and subject whether its best-known
   artists are back, and whether Franklin, Hitler and the writers stay out.
1. Unit tests over recorded answers, each watched failing: artists come back in
   summed-fame order, a tie broken by the artist's own sitelinks; an artist with
   many obscure works ranks below one with a few famous ones.
2. The `live_museum` shape test still passes.

### Chunk 06: The owner's review of the screens

**Visual change:** yes

- **`core/getting.js`, a caller's default name:** when no theme has that name,
  *Add to* offers it as its own option, "<name> (new theme)", selected; *New
  theme…* stays last and reveals an empty name field, hidden otherwise. Get with
  the named option creates the theme by that name first (`POST /api/themes`),
  then starts the Get. A name that is already a theme still selects that theme.
- **`core/search.js`:** Wikidata's artists and works are painted when they
  arrive, and its topics when they arrive, each on its own; while either is
  pending the dropdown says *Asking Wikidata…*. The announcement and the one
  note per dropdown still hold.

**Done when:**
1. Browser tests, each watched failing: on a Topic page with no theme of its
   name, *Add to* shows "<name> (new theme)" selected and no name field; *New
   theme…* reveals an empty field; Get creates the theme by the topic's name and
   sends its id; registry artists and works appear while the topic search is
   still held open; *Asking Wikidata…* shows while one is pending and is gone
   after.
2. All suites and the browser suite pass.

### Chunk 07: Review on a Get's own page, wide, with its scans readable

**Visual change:** yes

- **A Get's page is its review.** The run page of a `get` run shows the review
  cards (Accept, Reject, Why, Scans) in place of the *Works* table and *Review
  these works*. Queue, To review and the confirmation's link lead there. A
  discovery run's page is unchanged, and `#review/<run>` keeps working for both.
- **The card is wide.** One work per row at desktop width: the image on the left,
  the facts and actions on the right; one column at phone width.
- **Scans as a table**, as Radarr's interactive search lists releases: one row
  per scan with its preview, resolution, provider, rights, confidence and whether
  it is the chosen one, and the existing actions (choose, turn down). *Scans*
  stays collapsed by default.
- **Resolution above the fold, in pixels** ("3,840 × 2,604 px"), for the shown
  scan. The fit badge's "would show at N″" goes everywhere `fitBadge` draws it
  (Review, Work, Theme, Artworks); the verdict word stays. The API gains the
  scan's own `width` and `height`; the runner's selection sentence names pixels,
  not inches, for new runs (stored sentences are records and stay).
- **Clicking an image enlarges it in place**: a dialog with the largest preview
  the server holds, closed by Escape, a close button or a click outside, focus
  returned to the image; no navigation.

**Done when:**
1. Browser tests, each watched failing: a Get's page has Accept/Reject and no
   *Review these works*; a discovery run's page is unchanged; a single card at
   1280 px is wider than half the content area; Scans' facts never wrap a label
   onto two lines at 1280 px; the card shows the scan's pixels and no inches
   anywhere the fit badge draws; the enlarged image opens and closes without the
   address changing, and focus returns.
2. A unit test that the selection sentence names pixels and no inches; an API
   test that the scan's width and height reach the payload.
3. All suites and the browser suite pass; screenshots at 1280 and 375 px in the
   operator-verification entry.

### Chunk 03c: Answers kept across restarts

**The questions the stored answers answer** (a persisted format, but a
disposable one; Q-rows in `data-model.md`):
1. Do I already have this answer, and is it fresh enough to use? (Every page
   section that asks a foreign service.)
2. How much is kept, and what can be thrown away first? (The bound.)

- **A durable form of `Remembered`**, in the curation plane, usable by any
  service that asks a slow foreign source: the same `get`/`put` shape, plus a
  namespace per use and a maximum age per namespace. Wikidata is its first user,
  not its definition.
- **Adopted by every registry page section** that uses `Remembered` today: the
  Artist page's sections and Similar artists, and the Topic page's sections
  (the Topic adoption follows Chunk 04's merge, since Chunk 04 edits
  `topics.py`).

`[ASSUMPTION: the kept answers live in their own SQLite file under ART_ROOT, apart from the catalogue, so deleting it loses only time and a backup can skip it | MED impact | user can correct]`
`[ASSUMPTION: an answer older than its namespace's maximum age is a miss, never served stale; the registry's sections keep answers for 7 days | MED impact | user can correct]`
`[ASSUMPTION: a failure is never kept (as today), Held marks are read fresh on every call (as today), and an entry that cannot be decoded is a miss, so a changed answer shape costs one refetch | LOW impact | user can correct]`
`[ASSUMPTION: the file is bounded by entry count, oldest-used first out, as Remembered is | LOW impact | user can correct]`

**Done when:**
1. Tests, each watched failing: an answer survives a restart; an expired one is
   a miss; a failure is not kept; an undecodable entry is a miss; the bound
   evicts oldest-used first; two namespaces with the same key do not collide;
   an Artist page section answers from the kept answer with the registry down.
2. Root and curation suites pass.

### Chunk 04: Your works' topics, and the topic index

**Exposed API:** `GET /api/topics`, `GET /api/topics/{qid}`, `GET /api/topics/{qid}/works`, `GET /api/topics/{qid}/artists`, `art_catalogue(action='topics'|'topic')`. The two section routes were added 2026-10-02 after Chunk 03 measured period works at 7-26 s and some periods timing out: the page route answers from the facet rows with no network, and the registry sections are served apart, as the Artist page's are.

**The questions the facet rows answer** (a persisted format; Q-rows in
`data-model.md`):
1. Which topics does my library touch, and how many works in each? (Library ›
   Topics, and the Artworks rail.)
2. Which of my works are in this topic? (A Topic page's first section, with no
   network.)
3. Where did this claim come from, so a curator correcting it knows what they are
   arguing with? (`derivation`, `source_note`.)
4. Which topic page does this facet value open? (A QID beside the label.)

- **`work_facets` gains `value_qid TEXT`**, nullable (a facet inferred later may
  have none). Rows written here are `sourced`, `source_note` "Wikidata".
- **A topic sweep**, beside the preview sweep: at start and after any acceptance
  or QID change, it asks `topics_of` for held works whose facts are missing or
  older than the sweep's interval, and replaces those works' `sourced` rows. An
  `inferred` row is never touched. Off, and saying so once, without
  `WIKIDATA_USER_AGENT`.
- **`TopicService.index()`**: every topic your works touch, grouped by kind, with
  counts, from the facet rows. **`TopicService.page(qid)`**: the topic, your works
  in it (from facets), its works with their states (Held matched by QID), and
  its artists.
- **Surfaces:** `GET /api/topics`, `GET /api/topics/{qid}`, and their MCP twins on
  `art_catalogue`.

**Done when:**
1. Tests, each watched failing: the sweep writes one row per work, kind and value;
   a second sweep with a changed answer replaces rather than adds; an `inferred`
   row survives a sweep; a work with no QID whose artist has one gets movements
   only; the index counts match the rows; a topic page marks a work Held by QID;
   both surfaces return the same shape.
2. On a catalogue copy, the Artworks facet rail shows movement, era, subject and
   medium values with counts, and choosing one narrows the grid.
3. Root and curation suites pass; mutations of the replace, the `inferred` guard
   and the Held match each turn a test red.

### Chunk 05: Library › Topics and the Topic page

**Visual change:** yes
**Type:** cumulative-final

- **Library › Topics** (`#topics`), under Library after Themes: your topics by
  kind, each with its count, linking to its page, and a search box offering
  `topics_named`'s candidates.
- **The Topic page** (`#topic/<qid>`): name, kind, description and a Wikidata
  link; for a period, **Representative works** is headed with its
  years ("Works from 1588-1672"; the owner's answer of 2026-10-02 named named
  periods, and the coordinator extended it to every period, centuries included,
  because every period's works are matched by date alone and the client then
  needs no rule telling a century from a named period); **In your library**; **Representative works**, with states and tick
  boxes; **Artists**, linking to Artist pages. Its Get control passes the topic's
  name as the default destination (Chunk 02).
- **The top bar's typeahead gains a Topics group**, after Works, as
  `information-architecture.md` lists it.
- **`information-architecture.md`:** the screen inventory, the sidebar table and
  the route table gain Topics and Topic, held by `test_screen_tables.py`; the
  Direction note's *Topic pages* points here.
- An operator-verification entry for both screens at 1280 and 375 px.

**Done when:**
1. Browser tests, each watched failing: the index lists kinds and counts from the
   API; a topic page draws its three sections, the registry ones after the page
   (as *Their work*); a held work offers no tick box; Get from a topic defaults
   to a new theme named after it; the typeahead shows a Topics group; with no
   User-Agent both screens say topics need it.
2. Driven on a catalogue copy: S12's path, Library › Topics → 16th century → tick
   three → Get into *16th century* → accept → the theme holds them and *All
   works* does not.
3. All suites and the browser suite pass; then the one cumulative review.
