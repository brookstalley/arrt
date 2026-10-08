---
artifact: build-plan
version: 1
scope: lists-settings-and-scale
branch: feature/lists-settings-and-scale
partition: chunk 01 serial first (it sets the component rules every later chunk builds to, and touches every screen). Then delegates in isolated worktrees in two waves. Wave 1 — A follow-ups and spend (02); B Themes and Settings (03, 04); C Status (10). Wave 2, after wave 1 merges — D selection and Artworks (05, 06, 07: all edit screens/collection.js, so one delegate); E Queue (08); F Topics (09). Chunk 11 and every review stay with the coordinator. app.css and api.py take appends, not rewrites.
depends_on:
  - artifact: ux-review-2026-10
  - artifact: ia-proposal
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: api-contract
governed_by:
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: nonfunctional-requirements
last_validated: null
---

# Build Plan — Lists, Settings, and scale

## What this plan is

The rest of `ux-review-2026-10.md`: the findings `build-plan-walls-work-and-trust.md`
left open (22–25, 27–29, 17, 18), the owner's System-page feedback (#265, #266),
and the six follow-ups that PR #297 filed (#298, #302–#306). One branch, one PR,
as the owner asked of the last plan (memory: one PR per plan while Arrt is new).

The owner set the scope on 2026-10-08: core + Status + scale. That includes
#131 and #281, the 2,000-work problems, even though today's library holds 46
works.

| Chunk | What | Backlog |
|---|---|---|
| 01 | Component rules: headings, empty states, badges, button states | #287 |
| 02 | Follow-ups from #297, plus a tier on an Ask turn | #298, #302–#306 |
| 03 | Themes index as cards; ordering on the theme page | #284 |
| 04 | Settings opens on an index; Taste is called Taste | #286 |
| 05 | One selection model on every list | #285 |
| 06 | Clean-up facets: size on the wall, not on any wall | #288 |
| 07 | Artworks reaches every work | #131 |
| 08 | Queue at thousands: grouped by cause, paged, retried in bulk | #281 |
| 09 | Topics offers periods and movements before any are held | #289 |
| 10 | Status: sources as a table; the geometry panel goes | #265, #266 |
| 11 | Walk S7, S9, S12 and re-photograph at scale | — |

**Not in this plan.** #252 (the hand-run matcher, finding 8): it is identity
work on the server, not a UI change. #91 (mat control) waits for wave 4's
per-wall mat, for the reason the last plan gave. #282 (the gallery-room photo)
is a source-filtering problem in acquisition. Recording *which works a wall
showed* is filed, not built (chunk 06).

**What I would do differently.** Two things, neither blocking:

- **#131 and #281 are built ahead of need.** At 46 works neither bites, and
  `shortfallNote` already says aloud when the 1,250 cap is hit. The owner chose
  to include them. I've put them in wave 2 so they can't hold up the rest.
- **#289's fixed list is the weakest requirement here.** "A short list of
  periods and movements" is a hand-kept list. It ages and leans toward whoever
  picked it. Centuries are free of that. Movements are not. Chunk 09 keeps the
  movement list short and defines it in one place, so it can be removed if the
  owner prefers centuries alone.

## Requirements Confidence

**High** for 02, 03, 04, 06, 10. Each one is a backlog item with acceptance
criteria, or an owner ruling from 2026-10-08. **Medium** for 01, 05, 07, 08 and
09, which each carry a design choice:

- `[DECISION: Settings opens on an index of its pages, each with one line on
  what it holds. This is Sonarr's and Radarr's v4 /settings page. Taste moves
  to last, after Clients and Sources. | the *arr convention (memory: prefer
  ecosystem familiarity), and it removes the question of which page is "first"
  | owner can veto]`
- `[DECISION: selection is a Select toggle on every list (Sonarr's "Select"
  mode), not permanent checkboxes. In select mode a fixed action bar offers
  Select all, then every action valid for the selection: Add to theme (with
  New theme…), Archive, Get. Select all means every work the filter matches,
  including works not yet loaded. | one model, and the one the *arr apps use;
  permanent checkboxes add a Tab stop to every card (finding 30) | owner can
  veto]`
- `[DECISION: Artworks pages from the server as the curator scrolls, and the
  1,250 cap is retired. The grid asks for the next page when its last row comes
  near the viewport, with a "Show more" button as a fallback for the keyboard
  and for screen readers. | the server already filters, sorts and counts
  (core/api.js worksFilter), so paging adds nothing new to it. A virtualised
  client grid would need every work loaded, which is the thing that breaks |
  builder's call]`
- `[DECISION: Queue groups failed Gets by their cause's text and shows each
  group as one row: the cause, the count and Retry all, which opens into the
  works. Paged at the server's default. | 2,000 rows that share one cause are
  one problem (#281) | builder's call]`
- `[DECISION: Topics shows the centuries from the 13th to the 21st, plus a
  short list of movements (at most twelve, defined in one constant), whether or
  not any work is held. A topic page shows each work as its answer arrives. |
  #289; see the doubt above | owner can veto the movements]`
- `[DECISION (2026-10-08, chunk 09 at build): a topic page streams its answers
  (topic, ranked works, makers) as they land, and the existing TopicSweep thread
  also keeps the fixed list's answers warm, about a week old at most, asked one at
  a time and stopped by any refusal. | the 22 s is one SPARQL range scan that no
  split makes cheaper (wikidata-findings.md § Topics), so streaming alone saves
  only the makers query; warming 21 fixed topics is about 42 queries a week on a
  thread that already exists | owner can veto]`
- `[DECISION: chunk 01's rules are written into design-direction.md §
  Component Patterns, and the stylesheet supplies a shared class for each. The
  "native" and "wall render" badges are removed from tiles. Disabled buttons
  get a disabled style. | #287; a badge that every tile carries tells the
  curator nothing (memory: challenge whether a field earns its place) | owner
  can veto]`
- `[ASSUMPTION: the Status sources table (#265), ruled by the owner on
  2026-10-08: Source, State, Offered, Chosen and Faults always show. As the
  width narrows, columns drop in this order: Median long edge first (the owner
  didn't name it, so it is the least protected), then Last fault, then Only
  here, then Faults since startup. Once that column is gone, the fault count
  moves into the State cell ("Working · 2 faults"), so faults are always on
  screen. | MED | owner can correct]`

**Ruled by the owner, 2026-10-08:** "Never hung" is built as **Not on any
wall**: works that no wall plays now, through any theme or selection. A
backlog item is filed to start recording which works a wall shows, from the
heartbeat. The geometry panel on Status is **removed** (#266), and wave 4 brings
back a version per wall under Clients.

## Norm dispositions

- `information-architecture.md` § Direction, *navigation is a link, an act is a
  button*: **conforms**. Theme cards, the Settings index rows and Queue's group
  rows are links. Select, Retry all and Add to theme are buttons.
- § Direction, *a new section needs an *arr precedent or an owner ruling*:
  **inapplicable**, because no section is added. The Settings index is a page
  in an existing section.
- `design-direction.md` § Direction: **conforms**. Chunk 01 adds rules to §
  Component Patterns and changes no norm.
- `accessibility-spec.md`, *colour is never the only carrier of state*:
  **conforms**. Status's State is a word, and the dropped columns move their
  meaning into the State cell instead of losing it.
- `nonfunctional-requirements.md` § Direction, *spend is read from the
  provider, never tallied from the ledger*: **conforms**. An Ask turn's tier
  (chunk 02) is an estimate shown before spending; it neither reads nor writes
  the budget.
- `api-contract.md` has no Direction section; its HTTP surface inventory is
  descriptive and **tracks**: every route a chunk adds or changes (the new
  facets, select-all by filter, Queue's groups, the Ask turn estimate) gets its
  row in the same chunk.

## Status

- [x] Chunk 01: Component rules
- [x] Chunk 02: Follow-ups and an Ask turn's tier
- [x] Chunk 03: Themes index as cards
- [x] Chunk 04: Settings index
- [ ] Chunk 05: One selection model
- [ ] Chunk 06: Clean-up facets
- [ ] Chunk 07: Artworks reaches every work
- [ ] Chunk 08: Queue at thousands
- [ ] Chunk 09: Topics before any are held
- [x] Chunk 10: Status sources table
- [ ] Chunk 11: Walk and re-photograph

### Chunk 01: Component rules (#287)

**Visual change:** yes

Done when:

1. `design-direction.md` § Component Patterns covers headings (one treatment
   per level, and no oversized Walls heading, since Walls is no longer the
   home), empty states (one pattern: what's missing, why, and the next step as
   a link or button), badges (only where the value varies between tiles; one
   meaning per glyph), and button states (disabled looks disabled, and an
   action row is spaced from the text above it).
2. `app.css` has one class per pattern, and every screen uses it. The old
   per-screen variants are deleted, not left beside the new ones.
3. A browser test checks every route in the route table for: one `h1`; each
   empty state using the shared pattern; a disabled button with computed
   styles different from the enabled one.

### Chunk 02: Follow-ups and an Ask turn's tier (#298, #302–#306)

Done when:

1. #302: renaming a theme updates `document.title`.
2. #303: the Walls lead picture asks for a bare-art size sharp at 48rem on a
   2× screen.
3. #304: Wanted's table stacks on a phone the way Activity's tables do.
4. #305: the `.action` hover effect does not create a containing block, so no
   full-card link is confined to its `.action`. A test covers a full-card link
   outside a stacked card.
5. #306: an Ask turn shows its cost tier before it is sent, from an estimate
   the conversation service returns.
6. #298: server-composed sentences on Status, the Work page's look reasons and
   the MCP estimate's `basis` name the museum, not the plugin id or "phase 1".
   A test runs every source plugin through each sentence and fails on a
   plugin id.

### Chunk 03: Themes index as cards (#284)

**Visual change:** yes

Done when:

1. `#theme` is a grid of cards: name, count, up to four pictures, and the walls
   it hangs on. Each card is a link to `#theme/<id>`. Rename, delete and
   membership move to the theme page.
2. The theme page orders its works with Move to top and Move to bottom beside
   ↑/↓, keyboard-operable. No drag: a drag has no keyboard equivalent.
3. The order copy depends on the theme's shuffle: "Position decides what the
   wall shows first" only when shuffle is off, and "Shown in shuffled order"
   when it is on, matching Walls.
4. Ten themes fit on one desktop screen (a browser test with ten seeded
   themes).

### Chunk 04: Settings index (#286)

Done when:

1. The sidebar's Settings opens `#settings`: a list of its pages (Clients,
   Sources, Taste), each a link with one line saying what it holds.
   `information-architecture.md`'s screen tables gain the row, and
   `tests/preferences/test_screen_tables.py` passes.
2. Taste's heading is "Taste". Its help lists every way taste is recorded,
   *More like this* included.

### Chunk 05: One selection model (#285)

**Visual change:** yes

Done when:

1. Artworks, Artist, Search and Topic share one selection module
   (`core/selection.js`): a Select toggle labelled with its state, Select all,
   and a fixed action bar with every action valid for the selection.
2. Add to theme offers New theme…, so S7 runs without leaving Artworks.
3. Select all on a filter larger than what has loaded acts on every match (the
   server is given the filter, not just the loaded ids). A test checks this
   with a filter larger than one page.
4. Outside select mode, cards have no checkbox Tab stop.

### Chunk 06: Clean-up facets (#288)

Done when:

1. Artworks gains a *Size on the wall* facet (the existing small/native bands)
   and a *Not on any wall* facet, both counted by the server like the existing
   facets.
2. The rail toggle reads Show filters / Hide filters.
3. A backlog item is filed for recording which works a wall shows, from the
   heartbeat.

### Chunk 07: Artworks reaches every work (#131)

Done when:

1. Artworks loads pages from the server as the curator scrolls, with a
   Show more button for the keyboard. `PAGE_CEILING` no longer limits Artworks.
2. Back to Artworks from a work restores the scroll position and the loaded
   pages, so card 900 is still card 900.
3. With a 2,003-work fixture every work can be reached, and the shortfall note
   never appears.

### Chunk 08: Queue at thousands (#281)

Done when:

1. Failed Gets are grouped by cause, one row per group with its count and
   Retry all. A group opens into its works, named by title.
2. The table pages from the server.
3. Measured with `arrt/tools/ux_walk.py --synthetic 4000`: Queue with 2,000
   failures of one cause shows one group row.

### Chunk 09: Topics before any are held (#289)

Done when:

1. `#topics` lists the centuries and the movement constant even with an empty
   library, and each opens its topic page.
2. A topic page shows each work as its answer arrives, so it is never blank for
   the length of a Wikidata query.
3. 16th century can be reached on Topics without typing (browser test).

### Chunk 10: Status sources table (#265, #266)

**Visual change:** yes

Done when:

1. Status's Image sources panel is a table, one row per source, with the
   columns and drop order in the assumption above. "Only here" counts held works
   whose chosen image came from a source that no other source offered an image
   for.
2. The geometry panel is gone, and nothing on Status says "this television".
3. A backlog item is filed for the per-search record (searches asked, hit rate,
   latency).
4. The IA's Status entry says what the table holds.

### Chunk 11: Walk and re-photograph

**Type:** cumulative-final

Done when:

1. S7, S9 and S12 are walked in the real product and pass.
2. `arrt/tools/ux_walk.py` is re-run against the operator's library and a
   synthetic 2,000-work library, and `ux-review-2026-10.md` gets a dated note
   saying which findings are closed.
3. Each backlog item above is updated to shipped, or says what remains.
4. The two owner walks still owed on develop (walls-work-and-trust chunk 13,
   display-state chunk 05) are ticked here if the owner has walked them, or
   stay owed.

## Verification

All three suites, plus `-m browser` in `arrt/`, at every chunk, because almost
every chunk touches `static/`. Run the full suites after each delegate's merge,
not once per wave: the last plan's reflection shows that is what keeps a
cross-delegate seam attributable to one merge. Layout tests that check whether
something fits are run once with simulated wider fonts (letter-spacing 0.1em),
because CI's fonts are wider than this Mac's.
