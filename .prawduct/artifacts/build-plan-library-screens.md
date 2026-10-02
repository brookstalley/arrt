---
artifact: build-plan
version: 1
scope: library-screens
branch: feature/library-screens
partition: serial — every chunk edits `information-architecture.md`; 03 and 04 both edit `screens/artists.js`, 03 and 05 both edit `screens/topics.js`, and 02, 03 and 04 all add to `app.css`. The one independent pair (01's server work beside 03's client work) is too small to repay a delegate's brief and merge
depends_on:
  - artifact: build-plan-after-review
  - artifact: information-architecture
  - artifact: architecture
  - artifact: api-contract
governed_by:
  - artifact: information-architecture
    dispositions:
      - "the curation surface is laid out like the *arr apps; a page an *arr app has goes where it puts it (§ Direction) → conforms: Artworks' Select mode is Radarr's mass editor (Chunk 02), the Artists index is Lidarr's artist index with its poster/table toggle (Chunk 04). No page is added or moved"
      - "one row per screen in the three tables, held by `tests/preferences/test_screen_tables.py` → binds Chunks 02-05: each ruling lands in the row of the screen it changes, and no row is added"
      - "§ A control never offers a dead end → binds Chunk 02: Select mode's action bar offers Add and Remove only when they would do something (a work ticked; a theme in the filter for Remove)"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer → binds Chunks 01 and 02: each binding composes two service calls, one per plane, and decides nothing beyond whether a theme was named (see the seam decision below)"
      - "seam rule 1, the Library never imports Programming → binds Chunk 01. [DECISION: the theme filter is two calls composed in each binding, as `_theme_detail` (HTTP) and `_get_theme` (MCP) already compose them: Programming's `theme_work_ids`, then the Library's listing restricted to those ids as opaque references | the Library learns nothing about themes, so the split stays a deployment change; the alternative, the listing reading `theme_memberships`, is the cross-seam read rule 4 forbids. Chunk 01 first planned a composing service in `arrt/services/`; the existing precedent, which `theme_work_ids`' docstring names as the composition bindings are allowed, made it unnecessary | owner can veto]"
      - "seam rule 2, the facade takes and returns ids and plain data → conforms: the survey's new restriction is a set of work ids"
      - "seam rule 3, no new cross-seam foreign keys → conforms: no schema change in this plan"
  - artifact: api-contract
    dispositions:
      - "§ Versioning: adding a field to a response is additive → conforms: Chunk 03's wanted marker on registry works"
      - "§ Versioning: adding an optional query parameter is additive, not breaking → conforms: `GET /api/works?theme=<id>` is new and optional; the route's other parameters keep their meaning, and its MCP twin, `art_catalogue(action='list')`, takes the same `theme` (the facet filters landed on both surfaces together, and `test_search_and_facets.py` holds the two to the same answer)"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA; colour is never the sole carrier of state → binds Chunk 03: each state's image style is a second signal, never the only one; ● Held, ◑ Wanted, ◐ Not held · Image found and ○ Not held keep their glyph and word, and are tested with no picture at all"
      - "→ binds Chunks 02 and 04: Select mode's toggle reports its state (`aria-pressed`); the cards/table toggle is a named control with its state reported, and both views reach every artist by keyboard"
  - artifact: security-model
    dispositions:
      - "text from outside Arrt reaches the page as text; links out are built from an item id → conforms: Chunk 03 shows Wikidata's pictures through the preview cache as the Topic page does today, and adds no new outside text"
last_validated: null
---

# Build Plan — Library screens

## What this plan is

The owner's screen review of 2026-10-02 found five things on the Library's
screens. The owner delegated their order; this plan takes all five.

| Chunk | What | Issue |
|---|---|---|
| 01 | The works listing filters by theme, alongside facets and text | #169 |
| 02 | Artworks: Theme joins the Filter rail; Select mode carries add and remove | #169 |
| 03 | A work's mark: held, wanted and not held, each pictured in its own image style | #172 |
| 04 | Artists: surname order, Lidarr's cards with a table toggle | #173 |
| 05 | One quiet *Edit* on Wikidata identity; Topics in columns | #174, #175 |
| 06 | The owner's review of the screens | all |

**Not in this plan:**
- **Wikidata's family name (P734)** as a surname source (#173 proposed it). A
  listing makes no network calls, and storing it would add a write path to the
  identity match. Surname order uses the stored `family_name`, then the last
  word that is not a particle. Filed as a follow-up if the fallback sorts a
  real artist wrongly.
- **Artist portraits.** No artist has a picture of their own anywhere in the
  data; a card shows one of the artist's held works instead.
- The empty artist and palette facets (#165) and the 1,250-work grid ceiling
  (#131), which #169 scoped out.

## The owner's decisions, 2026-10-02

- **#169:** Radarr's pattern. Theme filtering is one more group in the *Filter*
  rail; the rail's separate theme list and its per-theme *Open* buttons go;
  adding and removing appear only in a *Select* mode with an action bar that
  names what it does. **A theme filter composes with facets and text.**
- **#172:** "Pictures for both, but visually different. Hashmarks on unheld
  maybe, so you can see what it is but it's immediately distinct from held."
  Then: "we should probably css style held, wanted, not held as image styles
  and then iterate on what's most clear". Each state gets an image style, tuned
  at the owner's review; glyph and word stay on every state.
- **#173:** Lidarr's cards by default, with a table toggle.
- **#174:** *There is none* goes behind *Edit*.
- **#175:** Columns, ordered by name.

## What I would do differently

Nothing in the scope. One risk the issues do not price: **#172 touches four
screens through one helper** (`stateMark` and `workState` in
`core/registry.js`: the typeahead, the Topic page, the Artist page, the Work
page). The owner's notes saw two of them in a browser; the other two are known
by code reading. Chunk 03 screenshots all four before and after, so the owner's
review in 06 sees every place the change landed.

## Requirements Confidence

**High.** Every open question was ruled on by the owner on 2026-10-02.

Open assumptions:
- [ASSUMPTION: the first try at the three image styles is: held plain, wanted with a dashed outline, not held under diagonal hatching (a `repeating-linear-gradient` overlay) | LOW impact | the owner iterates on them at 06, as they asked]
- [ASSUMPTION: an artist card's picture is the artist's earliest-accepted held work's thumbnail, and an artist with none held shows a plain tile with name and life | MED impact | owner can correct at 06]
- [ASSUMPTION: the cards/table choice on Artists is remembered in the address, as Artworks' density is, so a reload and a link land on the same view | LOW impact | owner can override]
- [ASSUMPTION: the surname particle list is the common Western set (van, von, de, da, di, del, della, der, den, du, la, le, ter, ten) plus generational suffixes (the Elder, the Younger, Jr., Sr.) | LOW impact | owner can correct]
- [ASSUMPTION: Select mode is not in the address; leaving the screen leaves it | LOW impact | owner can override]

## Status

- [x] Chunk 01: The works listing filters by theme
- [x] Chunk 02: Artworks: the Filter rail and Select mode
- [x] Chunk 03: A work's mark
- [ ] Chunk 04: Artists: surname order and cards
- [ ] Chunk 05: Identity's *Edit*; Topics in columns
- [ ] Chunk 06: The owner's review

### Chunk 01: The works listing filters by theme

`GET /api/works` gains an optional `theme=<id>`. With it, the page and its
facet counts are computed within the theme's members, and it composes with `q`,
every facet and `sort` as they compose with each other. The Library's
listing (`CatalogueService.list_artworks`, and `SurveyService.list_works`
over it) gains an opaque work-id restriction; each binding asks Programming
for the theme's member ids and passes them through (the seam decision above).
`art_catalogue(action='list')` takes the same `theme`. An unknown theme id is
the surface's one refusal (400, naming it), not an empty page.

Done when: service and HTTP tests for a theme alone, a theme with a facet, a
theme with text, the facet counts within the theme's slice (with a fixture
holding a non-member that would change the count), an empty theme, and an
unknown id; `tests/preferences/test_seam_imports.py` still green; the
api-contract entry for the parameter; and the `themeIsShowing` comment in
`collection.js` no longer true of the API (it goes in Chunk 02).

### Chunk 02: Artworks: the Filter rail and Select mode

**Visual change:** yes

- The rail's *Themes* list, its chips and its *Open* buttons go. A *Theme*
  group joins the *Filter* rail beside the facets, one theme at a time, and
  composes with them through Chunk 01. `themeIsShowing` and the exclusivity it
  enforced go with it.
- **Each theme option carries the count it would select, and a theme that
  would select nothing is disabled**, as every facet option is
  (`information-architecture.md` § A control never offers a dead end; found
  reading the rail while Chunk 01 was in review — a theme group without counts
  would be the one rail group that can lead to an unexplained empty grid). The
  count is computed with the theme's own selection ignored, as a facet's is.
  Two calls, one per plane, composed in each binding: the Library answers the
  ids the other filters select (a new unpaged `matching_ids`), and Programming
  counts each theme's members among them (a new `theme_counts(work_ids)`), so
  neither side learns the other's model. `GET /api/works` and
  `art_catalogue(action='list')` both return the group; `api-contract.md`
  records it.
- **A theme filtered on Artworks is in the Sort menu's order**, not its
  curated order, as any filter is; the curated order is the theme's own page's
  (Library › Themes). "Sort is not offered while a theme is showing" goes.
- The toolbar's always-on theme `<select>` goes. A *Select* toggle
  (`aria-pressed`) puts ticks on the tiles and shows an action bar: "Add 3
  works to…" with a visibly labelled theme choice, and, when a theme is in the
  filter, "Remove 3 from <theme>". Leaving Select mode clears the ticks.
- `information-architecture.md` Flow 5 and the Artworks row record the ruling.
- The three rail tests named in #169 are retired or rewritten in this commit,
  each replaced by the contract the new design owes, with the reason recorded.

Done when: service and HTTP/MCP tests for the theme counts (one theme with a
member the facet excludes, so its count differs from its size; a theme the
filter empties, disabled); browser tests for the Theme filter group composing with a facet,
Select mode's toggle and its action bar (Add disabled with nothing ticked;
Remove offered only with a theme in the filter), and that no theme control
shows outside Select mode; screenshots at desktop and phone width; an
operator-verification entry.

### Chunk 03: A work's mark

**Visual change:** yes

**The owner, later on 2026-10-02:** "we should probably css style held,
wanted, not held as image styles and then iterate on what's most clear". So
the state is carried by **an image style per state**, defined side by side in
one block of `app.css`, and the styles are tuned at the owner's review (06)
rather than settled here. Hatching is the first try for *not held*, not a
ruling.

**Wanted is a fourth state the marks do not know today.** `stateMark` and
`workState` see held, image found and not held; a work wanted through #168 is
invisible to them. Candidate works carry their `wikidata_qid`
(`persistence/sqlite_discovery.py`), so every registry-work answer that fills
`held_artwork_ids` (the search typeahead's, a registry work's, the Topic
page's and the Artist page's, all in `http/api.py`) also says whether a wanted
work names that item. That is an additive field on four response models,
recorded in `api-contract.md`. Held wins over wanted when both are true.

Wherever `stateMark` or `workState` draws a work (the search typeahead, the
Topic page's representative works, the Artist page's and the Work page's state
columns):
- **held**: its own thumbnail (`/api/works/<id>/thumbnail`), in the held
  image style, beside ● *Held*;
- **wanted**: Wikidata's picture where there is one, in the wanted image style,
  beside ◑ *Wanted* (the glyph Review already uses for the verdict);
- **not held, image found**: Wikidata's picture, through the preview cache as
  today, in the not-held image style, beside ◐ *Not held · Image found*;
- **not held, no image**: ○ *Not held* and no picture.

`information-architecture.md`'s Work screen table and the screens it names
record the ruling, and the typeahead stops dropping the "Not held ·" prefix.
*(Built: the Search results page draws works with the same mark, so it took
the ruling too; the IA's new § A work's mark names all five places. Topics keep
their `state` enum and gain a `wanted` beside it, so no reader branching on
the enum changes.)*

Done when: API tests that each of the four producers reports wanted (with a
fixture holding a wanted candidate for a different QID, which must not mark
this one) and that held wins over wanted; browser tests on each of the four
screens for all four states, each asserting the glyph and word, the picture's
presence or absence, and which image style it carries, plus one with pictures
failing to load that still tells the states apart; before/after screenshots of
all four screens; an operator-verification entry.

### Chunk 04: Artists: surname order and cards

**Visual change:** yes

- The artists listing orders by a surname key: `family_name` where it is set,
  else the last word of the name that is not a particle or generational
  suffix, then the full name. Test cases: "Hans Holbein the Younger" under H,
  "Vincent van Gogh" under G, "Moche" under M, and a stored `family_name` that
  disagrees with the fallback winning.
- The index is a card grid by default (Lidarr's artist index): a card shows a
  held work's thumbnail, the name, life dates and works held. A table toggle
  shows today's table, also in surname order. The view is in the address.
- `information-architecture.md`'s Artists row records the ruling.

Done when: store/service tests for the order; browser tests for both views,
the toggle's state, keyboard reach, and an artist with no held work; a layout
test that the cards fill the width at desktop and stack at phone width;
screenshots; an operator-verification entry.

### Chunk 05: Identity's *Edit*; Topics in columns

**Visual change:** yes

- `identityControl` (`core/identity.js`, used on the Artist and Work pages) at
  rest shows the current identity and one quiet *Edit*. *Edit* reveals the Q…
  field, *Look up* and *There is none* together. The handoff's carried wording
  note on `identity.js` lands here.
- Library › Topics draws each kind as CSS columns, by name, each count beside
  its name: as many columns as fit at desktop width, one on a phone.
- `information-architecture.md`'s Artist, Work and Topics rows record the
  rulings.

Done when: browser tests that only *Edit* shows at rest on both pages and that
*Edit* reveals the three controls; a layout test that a kind with 30 topics
takes no more than a third of the height it takes in one column at desktop
width and is one column at phone width; screenshots; an operator-verification
entry.

### Chunk 06: The owner's review

**Type:** cumulative-final

The owner looks at the five screens on a catalogue copy; what they ask for is
fixed here. Then the one `/prawduct:critic cumulative` over the branch.

Done when: the owner has seen every screen this plan changed; the three suites,
lint and format green in all three columns; the browser suite under `-n auto`.

## Verification strategy

Each chunk runs a server on a copy of the catalogue (never the original) and
screenshots its screens at desktop and phone width, with the browser suite
driving the same states. Chunk 06 puts them in front of the owner.

## Governance checkpoints

After Chunk 01 (the seam decision is the plan's one architectural choice), and
the cumulative review at Chunk 06.
