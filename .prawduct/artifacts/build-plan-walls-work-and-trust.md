---
artifact: build-plan
version: 1
scope: walls-work-and-trust
# branch: feature/walls-work-and-trust — merged in #297 and deleted. Chunk 13, the only one left, is the operator's at the wall and claims no branch; it is ticked in whichever PR follows the walk.
partition: parallel in waves, delegates in worktrees, coordinator integrates (the owner asked for subagents to cut wall clock). Wave 1 — A static/ foundation (01, 02); B Programming and the event log, server only (03, 04); C search, review and spend, server only (07, 08, 10 server halves). Wave 2, after wave 1 merges — D Walls and History UI (05, 03 UI); E Work page (06); F Search, Artist, Review and spend UI (07, 08, 10 UI). Wave 3 — G vocabulary (09); H tiles, then keyboard and phone (11, 12). Chunk 13 and every review stay with the coordinator. Shared files (api.py, models.py, app.css) take appends, not rewrites.
depends_on:
  - artifact: ia-proposal
  - artifact: information-architecture
  - artifact: ux-review-2026-10
  - artifact: design-direction
  - artifact: accessibility-spec
last_validated: null
---

# Build Plan — Walls, Work, and signals you can trust

## What this plan is

The fixes for the high-priority findings of `ux-review-2026-10.md`, built in one
branch and shipped as one PR. The owner, 2026-10-07: *"this is a young product,
we need to minimize ceremony. One plan, one big PR."* So each chunk gets an
inner review that blocks only on ships-broken, and the boundary review runs once,
at the end.

The first half makes the two weekly scenarios work: hang one work (S1), see
what's on the wall (S6), and take it out of rotation (S8). The second half fixes
what the review found you couldn't trust (search, review, failures) and how the
product talks (vocabulary, machine formats, spend).

| Chunk | What | Backlog |
|---|---|---|
| 01 | Navigation is a link: scroll, focus, Back, and document titles | #273 |
| 02 | A failed action is reported beside its control | #277 |
| 03 | History is an event log | #293 |
| 04 | A wall can hang a selection, and a work can be kept off every wall | #272 (server) |
| 05 | Walls leads with what is on the wall | #272, #295 |
| 06 | The Work page: the picture, the title, and Hang | #272, #162 |
| 07 | Search and Artist say held, waiting for review, or not held, once | #275 |
| 08 | Review says what it doesn't know, and an open card takes the row | #276, #89 |
| 09 | One vocabulary: Get, Wanted, bare-noun labels, human dates and costs | #291, #292, #267, #283 |
| 10 | Spend: a monthly budget, and a tier on every action | #290 |
| 11 | Tiles show the art | #278 |
| 12 | Keyboard and phone | #280, #279 |
| 13 | Walk S1, S6, S8 and re-run Pass 1 | — |

**Not in this plan:** hanging for a duration, *Hang everywhere*, and Walls'
"next three". Durations and Hang everywhere wait for wave 4 (ruling 6 of
2026-10-01). "Next three" needs rotation in Programming, which also moves in
wave 4. Also out: Tier-3 findings #284–#289, #265, #266, #131 and #281, which
stay on the backlog. Mat control (#91), and #116/#120 from the retired round-2
plan, stay on the backlog too: wave 4 moves the mat to the Player and makes
`MAT_*` per wall, so a curator mat control built now would be built twice.

## Requirements Confidence

**High** for 01, 02, 05–09 and 11. Each is ruled (`ia-proposal.md` § Rulings
2026-10-07) or written as a backlog item with acceptance criteria, built against
screens the review photographed. **Medium** for 03, 04 and 10, each of which
carries a design choice:

- `[DECISION: a wall's source is a theme or a selection. A selection is stored
  as a theme with a hidden flag, left off the Themes index and the theme
  pickers | because the manifest, the readiness facade and the directive path
  already work through themes, so a hidden theme changes one listing filter
  where a new kind of source would change every reader of theme_assignments |
  owner can veto]`
- `[DECISION: Not this one again from every wall is a Programming exclusion
  (a row per work), filtered out by the manifest. It is not Archive, which
  removes the work from the Library | because S8 says "nothing else changed" |
  owner can veto]`
- `[DECISION: the event log lives in the Library store. Programming writes hang
  events through the existing seam, with the wall as an opaque reference, so
  seam rule 1's one-way imports hold | builder's call]`
- `[ASSUMPTION: OpenRouter's GET /api/v1/key returns limit_remaining for this
  key. Chunk 10 starts by measuring it against the live key (#150 says the
  recorded API has drifted). If it doesn't, the sidebar shows spend this month
  from the ledger against a configured budget, and the item says so.]`
- `[ASSUMPTION: the age past which a client report is stale is three heartbeat
  intervals (#295 leaves the threshold open). It is a named constant, shared
  with Clients so both pages agree.]`

**Confirmed by the owner, 2026-10-08:** works whose candidate came from Wikidata
or a museum collection read as *confirmed* by their provenance; on a key with no
provider limit the budget reads the provider's `usage_monthly` against
`MONTHLY_BUDGET_USD` (not the local ledger); the builders' wording ("Unchecked",
"Nothing spends", "Budget unknown", the museum display names in `core/providers.js`,
"Get from Ask", "Get again", "Get of chosen works", "under $0.01") stands. The
three-heartbeat staleness threshold remains the plan's assumption.

## Status

- [x] Chunk 01: Navigation is a link
- [x] Chunk 02: Failures beside the control
- [x] Chunk 03: History is an event log
- [x] Chunk 04: Selections and exclusions in Programming
- [x] Chunk 05: Walls leads with what is on the wall
- [x] Chunk 06: The Work page
- [x] Chunk 07: Search and Artist states
- [x] Chunk 08: Review trust
- [x] Chunk 09: One vocabulary
- [x] Chunk 10: Spend as a budget and tiers
- [x] Chunk 11: Tiles show the art
- [x] Chunk 12: Keyboard and phone
- [ ] Chunk 13: Walk and re-photograph

### Chunk 01: Navigation is a link (#273)

The norm is `information-architecture.md` § Direction: navigation is a link, an
act is a button. This chunk goes first because every later chunk renders lists.

Done when:

1. Every work, artist, topic, theme, Get and review in a list opens through an
   `<a href="#…">`, so it can be opened in a new tab and its address copied. The
   go-to-artist control has one style. Acts stay `<button>`.
2. A route change scrolls to the top and focuses the view with
   `preventScroll: true`. Back restores the list's scroll position and focuses
   the card that was opened.
3. Every routed screen sets `document.title` (the work's or artist's name on
   detail pages), and each screen's heading is its `h1`.
4. Browser tests pin: a work opened from card 20 shows its title at the top;
   Back returns to card 20 with focus on it; every route in `core/route.js` has
   its own title (parametrised over the route table, not a copied list).

### Chunk 02: Failures beside the control (#277)

Done when:

1. One helper in `core/` reports a failed write next to the control that sent
   it, naming the act and the outcome ("Couldn't reject *Title*: the server
   didn't answer. Nothing was changed."). The control keeps its state, so a
   retry is one click.
2. Every existing write uses it. The `#view`-top "Failed to fetch" banner is
   gone for writes.
3. A browser test refuses a verdict, a Get and a theme hang, and checks that
   each message sits beside its control.

### Chunk 03: History is an event log (#293)

Done when:

1. A Library-side event record holds Get started and finished, accept, reject,
   archive, restore and hang (with the wall and what it was drawn from), each
   written where the act happens, from now on. Past hangs are not recovered.
2. Activity › History reads events, can be filtered by kind, and shows relative
   dates.
3. A per-wall history read exists for Chunk 05.
4. Tests: each act writes exactly one event (through the API caller, not the
   store); seam rule 1's import guard still passes.

### Chunk 04: Selections and exclusions in Programming (#272, server half)

Done when:

1. Hanging a selection of one or more works on a wall creates a hidden
   selection theme and assigns it ("until changed"). The Themes index and theme
   pickers leave hidden themes out.
2. *Not this one again* takes `from this theme` (leave the theme) or
   `from every wall` (a Programming exclusion that the manifest filters out,
   reversible from the Work page).
3. Both are in the JSON API and the MCP surface, and write events (Chunk 03).
4. Tests: a manifest built for a wall hanging a one-work selection contains that
   work; an excluded work is in no wall's manifest but is still in the Library.

### Chunk 05: Walls leads with what is on the wall (#272, #295)

Done when:

1. Each wall card leads with the work the heartbeat's `current_work_id` names:
   large, with its label facts, linking to its Work page. Below it: what the
   wall draws from (a theme or a selection) and "until changed".
2. The controls are **Skip** (the existing directive, which replaces "Move on"),
   **Not this one again** (asking *from this theme* / *from every wall*) and
   **Change**. After Skip, the card shows the new work once the heartbeat
   reports it.
3. A client report older than the staleness threshold never reads "Shown by".
   Walls and Clients state its age the same way (#295).
4. The wall's history (Chunk 03) opens from its card.
5. "Showing (46)" and "Directive sequence" are gone from the card.
6. Browser tests: a seeded heartbeat's current work leads the card; an old
   `reported_at` reads as unknown, not "Shown by"; Skip writes the directive.

### Chunk 06: The Work page (#272, #162)

Done when:

1. The title is the page's `h1`. The picture is the largest thing on the page,
   and the wall render (with its mat) is shown here, where it is the subject.
2. For a held work, the state strip lists the walls and themes it is on, and
   has **Hang…** (pick a wall; hangs it as a one-work selection, Chunk 04) and
   undo for *Not on any wall* if it is excluded.
3. Archive is a secondary action.
4. Museum descriptions render their `<i>`/`<b>` as emphasis without parsing
   HTML: an allow-listed tokeniser builds the elements, per `security-model.md`
   § Direction (#162).
5. S1 passes in a browser test: from a work's page, Hang on a wall, and Walls
   shows the work.

### Chunk 07: Search and Artist states (#275)

Done when:

1. A registry row whose stored registry ID matches a held work or artist is
   folded into the held row. Until every held work or artist carries an ID, it
   is folded by title and artist (or by name and life dates).
2. Works waiting in To review show *Waiting for review* (linking to the review)
   on Search and Artist pages, and offer no Get.
3. Browser tests: a held work appears once; a work in review offers no Get.

### Chunk 08: Review trust (#276, #89)

Done when:

1. A candidate whose model note says it is unconfirmed carries a
   *Not confirmed* badge, and unconfirmed candidates sort after confirmed ones.
2. Notes are in the product's voice, with Markdown rendered as plain text and
   links (no raw `[..](..)`).
3. A verdict offers Undo for a few seconds.
4. Opening a card's other scans takes the full row rather than the card's
   column (#89, the shape the round-2 plan's Chunk 03 settled).
5. Browser tests for each.

### Chunk 09: One vocabulary (#291, #292, #267, #283)

Done when:

1. Every spending request is called a Get: `#get/…` routes, with `#run` kept in
   `FRAGMENT_ALIASES`. "Search" means only the free search, "run" is gone from
   curator-facing text, and the MCP names are judged in the same pass.
2. Wanted is always in the sidebar, with its count when non-zero, and its empty
   state names the controls that really add a work to it.
3. A labels rule in `information-architecture.md` (bare nouns and verbs for
   navigation, headings, column headers, buttons and field labels), guarded by
   a `tests/preferences` test that covers every label form, not only headings.
4. One date formatter (a readable date plus relative age), costs to the cent,
   museum display names. "phase 1", "manifest build" and plugin ids are gone
   from curator-facing text, and Status's raw keys sit behind a Details
   disclosure.
5. A test fails on an ISO timestamp rendered outside Details.

### Chunk 10: Spend as a budget and tiers (#290)

Done when:

1. The provider's key endpoint has been measured, and the result recorded in
   `openrouter-api-findings.md`.
2. The sidebar shows what is left this month.
3. Every spending action shows free, $, $$ or $$$ before it is taken, estimated
   from what the action will do (an Ask shows the tier of its bound).
4. The approval gate for runs of more than 25 works is gone. Doing the action is
   the approval.
5. When the provider refuses at the cap, the screen says the month's budget is
   spent.

### Chunk 11: Tiles show the art (#278)

The owner confirmed the direction 2026-10-07 (`ia-proposal.md` § Rulings
2026-10-07, ruling 7).

Done when:

1. Library tiles (Artworks, Walls' secondary rows, Artist, Topic, Search) show
   the work itself at its own aspect. The wall render appears only on the Work
   page.
2. Previews of works not held are real thumbnails marked by a badge, not
   hatching.
3. The "native" and "wall render" badges, which say nothing on a tile, are
   removed from tiles.

### Chunk 12: Keyboard and phone (#280, #279)

Done when:

1. The focus ring is visible on every card (no clipping by `overflow: hidden`),
   with one Tab stop per card.
2. The rest of #280's list: focus kept on a facet click, distinct accessible
   names for same-titled works, named review-note fields, the live region
   written only on change, and keyboard-scrollable tables.
3. Below ~40rem, Activity tables render as stacked cards with the row as the
   link, Themes fits 390 px, and the top bar is one row.
4. Browser tests at 390 px: To review's action is on screen; no page scrolls
   sideways.

### Chunk 13: Walk and re-photograph

Done when:

1. S1, S6 and S8 are walked in the real product, writes included, and pass.
2. `arrt/tools/ux_walk.py` is re-run, and `ux-review-2026-10.md` gets a dated
   note saying which findings are closed.
3. Each backlog item above is updated to shipped, or says what remains.

## Verification

All three suites, plus `-m browser` in `arrt/`, at every chunk, because nearly
every chunk touches `static/`. Pass 4 (a household member doing the three
tasks) remains the owner's, after merge.
