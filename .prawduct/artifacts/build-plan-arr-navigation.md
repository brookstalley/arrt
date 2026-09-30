---
artifact: build-plan
version: 1
scope: arr-navigation
branch: feature/arr-navigation
partition: serial — Chunk 02 rebuilds the route table and the router that Chunks 03 and 04 both build on, and 03-05 each edit the route table or the top bar in `app.js`
depends_on:
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: architecture
  - artifact: project-preferences
governed_by:
  - artifact: information-architecture
    dispositions:
      - "the curation surface is laid out like the *arr apps (§ Direction, amended by the owner 2026-09-30, in-transition) → this plan IS its migration. Chunk 01 records the amendment; Chunks 02-04 build § The *arr layout; the norm is steady-state when this plan merges"
      - "every screen and every consequential state is addressable (§ Navigation Structure) → conforms: every page in the sidebar has its own fragment, and every fragment the surface has ever served keeps resolving through `FRAGMENT_ALIASES` in `curatarr/src/curatarr/http/static/core/route.js`, since an agent's or a bookmark's old link must land on the page that took over its job"
      - "one row per screen in the three tables, held by `tests/preferences/test_screen_tables.py` → conforms: each chunk that renames or adds a route renames or adds its rows, and `SCREEN_NAMES` in that test, in the same commit, because the root suite goes red between them otherwise"
      - "Health is safe to demote only because its indicator is always present and speaks up (§ Navigation Structure) → conforms, by ruling: the top-bar indicator keeps that contract and the System badge is added beside it (§ The *arr layout records the collision with the accessibility rule and why it went this way)"
  - artifact: design-direction
    dispositions:
      - "the stylesheet holds token values, and `curatarr/tests/unit/test_design_tokens.py` refuses any colour outside the token blocks (§ Direction) → binds Chunks 02 and 04. The sidebar, drawer, badge and toolbar use existing tokens. Any token they need is added inside the scanned blocks and covered by the test in the same commit, or it is an unguarded colour wearing a token's name"
      - "the layout table's phone row (destinations move to a bottom bar) → amended by Chunk 02: the sidebar becomes a drawer behind a menu button. This is a description the norm change makes stale, not a norm, and Chunk 02 edits it"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA on the curation browser (§ Direction) → binds Chunks 02 and 04. The sidebar is a `nav` landmark whose current page carries `aria-current=\"page\"`. The drawer opens and closes from the keyboard, closes on Escape, and returns focus to the menu button. The skip link stays the first focusable element and still jumps past the sidebar. The View, Sort and Filter menus are buttons with `aria-expanded`, operable by keyboard"
      - "glyph + word + colour, never fewer than all three; a state indicator with no word is a bug (§ Announcement and semantics) → binds Chunk 02, and is why the System badge does not replace the top-bar indicator. The badge carries a word as well as a number in its accessible name, and the indicator keeps its visible word"
      - "a poll must never move focus → binds Chunk 02: the badge and the indicator repaint from the same health poll, and neither may take focus"
  - artifact: architecture
    dispositions:
      - "a module under `screens/` may import from `core/` and must never import another screen (§ Components & Responsibilities) → conforms: the sidebar and the toolbar are `core/` modules that know no screen, and `app.js` stays the one place the two meet. `curatarr/tests/unit/test_client_module_boundaries.py` stays green"
      - "no framework and no build step in the browser client → conforms: nothing in this plan adds a dependency. The comment in `app.js` that justifies it by a Pi is out of date (the server moves to the NAS in wave 3), and Chunk 02 rewrites that reason. It does not change the decision"
  - artifact: project-preferences
    dispositions:
      - "the mechanical rows (formatting, naming, imports, specific exceptions, no hardcoded deployment values) → conforms: every chunk runs the curation plane's three commands, and the root suite whenever it touches `tests/` or `information-architecture.md`"
      - "the browser suite runs whenever anything under `static/` changes → binds Chunks 02-04"
last_validated: null
---

# Build Plan — The *arr Navigation

## What this plan is

On 2026-09-30 the owner ruled that Curatarr's browser surface should be laid out
like the *arr apps: *"More important to be familiar than to have our own thing."*
The ruling amends the navigation norm in `information-architecture.md`
§ Direction, and § The *arr layout in the same artifact is the target. The owner
chose three things in the same conversation:

- The library section is called **Artworks**, the plural noun of the item, as
  every *arr app names this section.
- The product opens on **Artworks**, not the Walls.
- This round covers **the sidebar and the page toolbar**. The current palette
  stays, and the *arr visual look was offered and not chosen.

| Chunk | What it is |
|---|---|
| 01 | The norm amendment and the target layout, in the artifacts |
| 02 | The sidebar and the top bar, with Artworks as home |
| 03 | Activity › Queue and History: runs move out of Add New |
| 04 | Search in two scopes, Sonarr-style: the library as you type, museums on Add New |
| 05 | The page toolbar: View, Sort and Filter, with Posters, Overview and Table on Artworks |

## What I would do differently

- **Table view is the one piece with no demand behind it yet.** At 41 works the
  poster grid shows everything. I kept it because the owner picked the option
  that names it, and because it is the view *arr users reach for at scale. It is
  last in Chunk 05, so it can be cut there without touching anything else.
- **The sidebar costs the Walls page width**, and that page's content is the
  artwork. Sonarr's sidebar does not collapse on desktop, and I follow it here.
  If the Walls page feels cramped, a collapsible sidebar is a later change that
  needs no norm change.
- **The badge and the top-bar indicator say the same thing twice.** That is the
  price of the accessibility ruling in § The *arr layout. The alternative, a
  badge that carries a visible word, stops looking like the *arr badge, which
  was the point of adding it.

## Requirements Confidence

**Medium.** The owner settled the shape: name, home and scope. What remains is
placement, which the norm assigns by *arr precedent, and for which I have
filled in Radarr's answer where it has one:

- `[ASSUMPTION: Taste goes under Settings, following Radarr's Profiles (the preferences that rank what it finds) | MED impact | user can correct]`
- `[ASSUMPTION: the Walls sits second, in Calendar's slot, as a top-level entry with no sub-pages | LOW impact | user can correct]`
- `[ASSUMPTION: Collection's facets and theme rail move into the toolbar's Filter menu. The facet rules come with them unchanged: counts shown, each facet counted over the other facets, and a zero option disabled rather than hidden | MED impact | user can correct]`
- `[DECISION, revised while building Chunk 02: fragments keep their spellings (#collection is Artworks, #discover is Add New, #health is Status), and only the labels change | renaming them would have touched about 150 test addresses and every link an agent has already been given, for a word the curator never sees. The plan first assumed new spellings (#artworks, #add, #status) | user can veto/override]`
- `[ASSUMPTION: sub-pages show only under the current section, as Sonarr and Radarr show them | LOW impact | user can correct]`
- `[DECISION: Add New fills in a search term handed to it and does not start the run | Sonarr's lookup is free and instant, while a Curatarr search is a discovery run that takes minutes and spends money. Nothing may spend on a keystroke | user can veto/override]`
- `[DECISION: Enter in the top-bar search opens Artworks filtered to the query, not the first match as Sonarr does | an artist or movement matches many works where a series title matches one, so the first match is arbitrary. This departs from the *arr norm. **Ruled by the owner 2026-09-30: "yes to filtered to the query"** | settled]`
- `[DECISION, taken while building Chunk 03: Queue is the runs that have not ended, not "working or waiting for review" | the run listing carries no signal for a finished run with unjudged candidates, and adding one is an API change on GET /api/runs and its MCP twin, outside this plan. Nothing is lost against today's single list, and the gap is recorded in information-architecture.md § The *arr layout as owed | user can veto/override]`
- `[DECISION: keep the top-bar status indicator beside the *arr System badge | accessibility-spec.md requires glyph + word + colour, and a count-only badge has no word; the familiarity norm governs placement and naming, not legibility of state | user can veto/override]`

**What would raise it:** the owner reading the placement table in
§ The *arr layout. Every row names the *arr page it follows, so a wrong one is
visible without running anything.

## Status

- [x] Chunk 01: The norm amendment and the target layout, in the artifacts
- [x] Chunk 02: The sidebar and the top bar, with Artworks as home
- [ ] Chunk 03: Activity › Queue and History
- [ ] Chunk 04: Search in two scopes
- [ ] Chunk 05: The page toolbar

### Chunk 01: The norm amendment and the target layout, in the artifacts

**Type:** doc-only

Record the owner's ruling where it binds and describe the target.

- `information-architecture.md` § Direction: the amended statement, the owner's
  words as its why, what the old norm gave up, status and retroactivity.
  § The *arr layout (new): the sidebar, the placement table, and the rules for
  badge, search, toolbar, Wanted and phones. § Navigation Structure is marked as
  as-built until Chunk 02. The Watches line in § Open questions moves to Settings
  and Wanted.
- `project-preferences.md`: the enforcement row states the amended norm and keeps
  the old one as history.
- `design-direction.md`: the token norm's status notes that its sibling was
  amended and that the palette stays.

**Done when:**
1. The root suite passes, and `tests/preferences/test_screen_tables.py` in
   particular, since no route changed and so no table row may.
2. A repo-wide grep for "three destinations", "pipeline's stages" and "opens on
   the Walls" finds only code and tests that Chunk 02 owns, plus text that is
   marked as history or as-built.

### Chunk 02: The sidebar and the top bar, with Artworks as home

**Visual change:** yes

The route table in `curatarr/src/curatarr/http/static/app.js` gains sections:
each entry names its section and whether it is a sidebar page, which replaces the
`destination` key. `core/router.js` builds the sidebar from the table, so the
labels keep one source, shows sub-pages only under the current section, and lights
the current page with `aria-current="page"`. The top bar carries the brand,
search and the status indicator. The System badge repaints from the same health
reading as the indicator. On viewports under 40rem the sidebar is a drawer behind
a menu button.

Pages this chunk routes: Artworks (was Collection, and now home), Artworks › Add
New (was Discover, whole, including its run list until Chunk 03), Artworks ›
Themes (was Theme's index), Walls, Settings › Taste, System › Status (was Health).
Activity appears in Chunk 03, because it has no page until then.

Surfaces this touches, listed up front because the rename cascades:
`app.js`, `core/router.js`, `core/route.js` (aliases), `core/status.js`,
`index.html`, `app.css`, every screen's page heading, the three tables and
§ Navigation Structure in `information-architecture.md`, `SCREEN_NAMES` in
`tests/preferences/test_screen_tables.py`, the layout table in
`design-direction.md`, and the keyboard section of `accessibility-spec.md`.

**Tests.** `curatarr/tests/browser/test_the_three_destinations.py` encodes the
norm that was amended, so it is rewritten, not weakened. It becomes new
`curatarr/tests/browser/test_the_sidebar.py`. Each old test is kept against the
new shape, rewritten to the amended norm, or retired, and the commit message says
which, with the norm as the reason. The tests for the indicator, search, back
and aliases carry over whole. Two tests change what they assert because the
ruling changed the fact: *the product opens on the walls* becomes *opens on
Artworks*, and *health is not in the navigation* becomes *Status is under System*.

**Done when:**
1. The curation suite, the browser suite and the root suite pass.
2. New sidebar tests are watched failing once against the unbuilt sidebar,
   then passing: sections and pages match the route table, the home page,
   `aria-current`, the drawer from the keyboard, and the badge's accessible name
   in both the well state and a problem state.
3. Every fragment in `FRAGMENT_ALIASES`, old and new, opens the page that took
   over its job (a parametrised test over that symbol, not a copied list).
4. `app.js`'s no-build-step comment carries a reason that is true on the NAS.
5. An entry in `.prawduct/operator-verification.md` covers the sidebar at desktop
   width and the drawer at 375px.

### Chunk 03: Activity › Queue and History

**Visual change:** yes

Runs leave Add New. Activity › **Queue** lists runs that are working or waiting
for review. Activity › **History** lists finished runs, keeping the "most recent
N of M" truncation the run list has now. Add New keeps the intent box and the
conversations. Run and Review open from Queue or History and return to whichever
one they were opened from.

**Done when:**
1. The curation suite, the browser suite and the root suite pass, with Queue and
   History in the three tables and in `SCREEN_NAMES`.
2. A run shows in Queue while it works, stays there while it waits for review,
   and moves to History when it finishes. This is tested with a run in each
   state, including one that each list must *not* show.
3. Every Screen States row for Queue and History is written: empty, loading and
   error.
4. An operator-verification entry covers both lists.

### Chunk 04: Search in two scopes

**Visual change:** yes

The top-bar search follows Sonarr's pattern, recorded from its source in
`information-architecture.md` § The *arr layout. Typing shows a dropdown with
*In your library* (works matching the query, from the catalogue search that
exists today) and one row, *Search museums for "{query}"*, which goes to
`#add?term={query}`. Add New fills in its intent box from `term` and shows the
free estimate, and does not start a run. A Review candidate that is already an
accepted work is marked *Already in your library* and opens that work instead of
offering Accept.

**Step 0:** find out what a run does today with a work that is already accepted:
whether it skips it, proposes it again, or marks it. Read
`curatarr/src/curatarr/library/services/discovery.py` and build the case in a
test. The marking design depends on the answer, and nothing in this plan has
established it yet. The mark matches on the identity the catalogue has, which is
`work_dedup_key` today. It records that limit rather than building a better
identity here: external IDs are an open question in `re-architecture.md`, not
work for this plan.

**Done when:**
1. The curation suite, the browser suite and the root suite pass.
2. The dropdown is a keyboard-operable combobox (`role="combobox"`, a listbox,
   arrow keys, Escape) whose two groups are announced by name.
3. Following *Search museums* never starts a run. A test asserts that no run
   exists after landing on `#add?term=…`, and that the box holds the term.
4. Enter opens Artworks filtered to the query, as the owner ruled. It is tested
   with several library matches, where it must not open the first one, and with none.
5. *Already in your library* is tested with a candidate that is an accepted work
   and one that is not. The second case is there so the mark cannot pass by
   appearing on everything.
6. An operator-verification entry covers the dropdown and Add New's filled-in
   state.

### Chunk 05: The page toolbar

**Visual change:** yes
**Type:** cumulative-final

A `core/` toolbar module: actions on the left, and View, Sort and Filter on the
right, each a keyboard-operable menu button. On Artworks, View offers Posters,
Overview and Table. Posters is today's contact sheet and Overview is today's
catalogue, and the old `density=` values stay as aliases. Sort and Filter take
over the controls Collection draws today, with the facet rules unchanged. Themes,
Queue and History get the toolbar with actions only. Table view comes last.

**Done when:**
1. The curation suite, the browser suite and the root suite pass. The facet-rule
   tests from `test_the_collection.py` and `test_the_grid.py` pass unedited
   against the Filter menu. Only locators may change.
2. View, Sort and Filter survive a reload and browser back, as density does
   today.
3. An operator-verification entry covers the toolbar and the three views.
4. `/prawduct:critic cumulative` over the branch.

## Governance checkpoints

- **After Chunk 02**, read the built sidebar against § The *arr layout's
  placement table before building on it. Chunks 03 and 04 assume its shape.
- **Before the PR**, the cumulative review in Chunk 05, then turn § Direction's
  status to steady-state and its retroactivity to "migrate, no residual sites",
  in the PR that merges this plan.

## Verification strategy

The browser suite drives the real client against a real server, which is what
the curation plane's suite already does. Beyond it, each visual chunk runs
Curatarr locally against a seeded catalogue (`cd curatarr && uv run python -m
curatarr`) and is clicked through at desktop width and at 375px. The question to
ask is whether a Sonarr user would find each page where they expect it. The
screenshots go with the operator-verification entry.
