---
artifact: build-plan
version: 1
scope: ui-pass-work-artworks
branch: feature/ui-pass-work-artworks
base: develop
working-branches: []
partition: serial, one worktree. 02 and 03 both change `core/selecting.js` and the selection tests over the same fixtures, and 04's Work page reuses 02's *Add to theme…* dialog and 03's Get dialog shape, so nothing can be handed to a second builder without the three colliding.
depends_on:
  - artifact: ia-proposal
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: api-contract
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ Direction, the *arr layout (sidebar sections, a toolbar on list pages, *arr names) → conforms: Artworks and Work keep their slots and routes; the toolbar every list page has gains the selection's acts on its left, as Sonarr's does"
      - "§ Direction, navigation is a link and an act is a button → conforms: a work's artist, its walls and its themes are links in its facts; Hang…, Add to theme…, ⋯ and its items are buttons. `test_navigation_is_a_link.py` covers the new code"
      - "§ More than one wall (every act that changes a wall names the wall in its control and its confirmation) → conforms: Hang… names each wall in its dialog and its confirmation, through `arrt/src/arrt/http/static/core/hanging.js` as today"
      - "§ Vocabulary → conforms: Hang…, Add to theme…, Archive…, Restore, Match on Wikidata…, Artworks, theme"
  - artifact: design-direction
    dispositions:
      - "§ Direction (token values live in `app.css`; `test_design_tokens.py` refuses any colour outside the token blocks) → conforms: no colour is added; the sticky toolbar takes `--surface` and the existing rule"
      - "§ Component Patterns, How a page reads (2026-10-27) → conforms: Artworks is the first list, and Work the first detail page, built to it"
      - "§ Component Patterns, Buttons (one filled act per region; no destructive style) → conforms: Hang… is the Work page's filled act, and Restore takes its place on an archived work, which cannot hang; Archive… carries no danger style, as `ia-proposal.md` § Rulings (2026-10-27) records against the prototype's red"
  - artifact: accessibility-spec
    dispositions:
      - "norm 2 (WCAG 2.1 AA on the browser; colour never the sole carrier of state) → conforms: the ⋯ menu is an ARIA menu of `menuitem`s with the keyboard `menuButton` already has, and its trigger's accessible name is *More acts on {title}*, never the glyph; dialogs are `arrt/src/arrt/http/static/core/editing.js`'s `<dialog>`; the mat picker names each colour in words beside its swatch; the axe scan runs on Artworks, Work, an Artist, a Topic and Search results"
      - "norm 1 (the e-paper label) → inapplicable because nothing here changes what a Player draws"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer; MCP and HTTP are thin → inapplicable because no server code changes: every act on both pages already has a route (`POST /themes/{id}/works`, the hang routes `arrt/src/arrt/http/static/core/hanging.js` calls, `/works/{id}/archive`, `/restore`, `/mat`, `/wikidata`)"
  - artifact: security-model
    dispositions:
      - "§ Direction (text from outside Arrt reaches the page as text) → conforms: a work's title, artist and description come from museums and Wikidata and are set with `textContent` through `el()`, in the dialogs' titles as on the page"
last_validated: 2026-10-29
---

# Build Plan — the UI pass, part 2: Work and Artworks

## What this plan is

The second of three plans that build the owner's rulings of 2026-10-27
(`ia-proposal.md` § Rulings (2026-10-27); backlog #389). Walls was the first
(`build-plan-ui-pass-walls.md`, #392). This one rebuilds **Artworks**, the
library's list, and **Work**, one work's page, to the page rules in
`design-direction.md` § Component Patterns ("How a page reads") and ruling 8.

The prototype the owner approved is a private Claude artifact, not committed,
because it carries the library's pictures. The rulings, the page rules and this
plan are the record a builder works from.

**Not in this plan:**

- **Themes, a theme and Settings › Players** (rulings 1, 7 and 9): the third
  plan, #390.
- ***Edit…* on a work.** Ruling 8 placed it beside Hang. A work has nothing for
  it to open: no route changes a work's title, date, medium, description or
  artist, and the two things a work can change are placed elsewhere by the same
  ruling (the mat in its facts, the match behind ⋯). Asked 2026-10-29, the owner
  chose to leave it out until a work has a setting, and to file editing a work's
  catalogue fields to the backlog (#396), as the Walls plan did for deleting
  a wall.

## Goals

**Response taken:** proceed, citing #389 and the rulings. The design is the
owner's, approved from the prototype. One gap, *Edit…* with nothing in it, was
put to the owner on 2026-10-29 and ruled (above).

**Product:** Artworks answers "what do I have", and Work answers "what is this,
and where is it". Each opens the way every page now opens (its name, one line of
facts, its toolbar), so a curator who learned Walls finds the acts in the same
place here. On Work the everyday act is hanging it, and the rare ones (archive,
correcting its Wikidata item) are one step away behind ⋯.

**Architecture:**

- A client rebuild with no server change. Every act already has a route
  (dispositions, above).
- **The selection's acts move into the toolbar on every list**, not only
  Artworks. `core/selecting.js` is one model for Artworks, an Artist's page,
  Search results and a Topic's page, by its own header, and the page rule ("the
  acts on what is selected take the toolbar's left side") binds every list. So
  the three other lists change too, in their selection bar alone. *Inferred:*
  the owner's ruling covers every list, since it is stated as a rule for "a table
  or grid of things", not for Artworks.
- The toolbar stays in reach while a long grid scrolls (sticky under the top
  bar), because the acts on a selection are now at the top of a list that pages
  as it scrolls. Today the bar sits at the window's foot for the same reason.
- The ⋯ menu is a new kind of menu: acts, not a choice among values.
  `core/toolbar.js` gains it beside `menuButton`, sharing the keyboard. Themes
  (#390) will use it for a theme's rarer acts.

**Constraints:**

- The browser suite boots a real server per class (`CLAUDE.md`) and runs
  whenever `static/` changes, after `uv sync --group browser`.
- `tests/preferences/test_screen_tables.py` holds the IA's screen tables
  against `app.js`. No route changes; the Artworks and Work rows' prose does.
- Browser tests pin today's wording and positions (the heading "N works", the
  selection bar at the window's foot, the Rights fact, the mat's disclosure
  under the picture). Each assertion rewritten for that reason says which ruling
  changed it, in the same commit (`core.md`, "When you drop or rewrite a test's
  assertion…").

**Tradeoffs accepted:**

- A sticky toolbar takes a row of a phone's height on every list. Worth
  revisiting if the walk (04) finds it crowds the grid; the fallback is sticky
  only while Select is on.

**Decisions made mid-build:** *(appended while building; one line each, naming
the goal or prior choice that settled it.)*

- 02: the toolbar sticks only while Select is on, the plan's named fallback taken up front: at rest nothing on its left side needs reaching from far down a list, and a phone keeps its height (the tradeoff below).
- 02: *Add to theme…* opens a dialog holding the theme picker and the new theme's name. The plan moved the bar's acts into the toolbar as they were; photographed, the picker and name field wrapped the toolbar to four rows on a desktop and half a phone screen while it stuck, which the Level had named as the open question. An act that opens a dialog ends in "…" (the page rules), and 04's *Add to theme…* on Work reuses the same dialog. *Archive…* gains its "…" by the same rule, since it asks first.
- 02 (after the photographs): Get's own *Add to* picker sits in the toolbar the same way on Search, a Topic and an Artist page, so it gets the same treatment in a chunk of its own, 03, and Work moves to 04. Found by building; the alignment pass did not settle it.
- 02: on a phone, View, Sort and the filters leave the sticky toolbar while Select is on: still five rows there after the dialog, and each of the three repaints the list, which drops the selection (`goWithParams` navigates and the page builds a new selection).
- 02: the stale-theme note stays a notice above the works rather than a muted line: when the address's theme is gone, the works shown are not what was asked for, which stops the page's job (the exception rule's own test).
- 02: `core/toolbar.js` is unchanged. The sticky state is a class `core/selecting.js` sets on the toolbar holding its toggle, so the toolbar keeps knowing no screen.
- 02: the axe scan ran by hand, as Walls' did: the suite does not fetch axe-core (`arrt/tools/ux_walk.py` does). `ux_walk.scan` from a temporary test over the suite's fixtures reported clean on Artworks, an Artist page, Search results and a Topic page, each with Select off and on, 2026-10-29.
- 03: both openers, *Add to theme…* and *Get N works…*, are quiet; the dialog's button is the filled act. Neither opener commits anything, and Search results put both in one toolbar, where two filled acts would break one-per-region (`design-direction.md` § Buttons). This changes 02's *Add to theme…*, which was filled.
- 03: `getAndSay` takes a `started` hook that closes the dialog before the sentence takes the keyboard, for 02's reason; its re-break fails the first Get test.
- 03: chunk 02's test that the dialog was gone after an add counted `dialog` elements, and raced `arrt/src/arrt/http/static/core/editing.js` removing a closed one a task later; it failed once under load. It now counts `dialog[open]`.
- 03: in the toolbar, the shared spacing for a row of acts (`:not(…) > * + .row`) set *Get…* a step below its neighbours, and the tier was centred in the dialog; both found by photograph, fixed in `app.css`, and held by position assertions that fail on the re-break.
- 03 (after its review): Done-when 1 on Search results was missing, and is now two tests, into a chosen theme and a new one. What "read back from the server" means for a Get: the suite answers `POST /api/gets` in the page, because a real Get asks Wikidata and the image sources, so a test holds the body sent and reads from the server only what the server keeps before the Get (a new theme). The Cancel and Escape tests hold that nothing was sent. The comment edit in `screens/collection.js` is chunk 02's review observation O-3, riding this commit.

- 04: *Add to theme…*'s picker became `themeChoice` in `core/membership.js`, which both the selection's dialog and the Work page's call: the plan named reuse, and a copy would be two answers to what a typed name that is already a theme does.
- 04: with one wall, *Hang…* asks its question directly rather than opening a dialog of one wall; a choice of one is not a choice, and the question already names the wall. The dialog of walls opens for two or more.
- 04: the mat's choices open inline under the toolbar, not in a dialog: a modal's backdrop would cover the picture the preview is drawn on. Its fact is a button (*Mat* then its value) with `aria-expanded`, and *Use this mat* folds the choices and returns the keyboard to the fact.
- 04: the artist's nationality and life stay, in brackets after the artist in the facts line, as a museum label gives them; the plan's list (artist, date, medium, size, mat) did not name them, and dropping them would have dropped facts the page showed.
- 04: the Wikidata item, when a work has one, is a fact beside the picture (a link); the control that changes it is in *Match on Wikidata…*, whose form is open (`identityControl`'s new `open`), since opening the dialog was the asking.
- 04: while a work is kept off every wall, *Hang…* leaves the toolbar (as it did from the strip), so the page has no filled act then; its undo is quiet in the kept-off line, by the exception rule.
- 04: photographs found three alignment faults (the mat's value above the text's line, "Mat" wrapping from its value on a phone, and on a not-held work *Cost: Free* centred on the label and field rather than the button: the last was there before this branch). Each is fixed in `app.css` and held by a position test that fails on its re-break.
- 04: the axe scan ran by hand again, `ux_walk.scan` from a temporary test over the suite's fixtures: clean on a held work (with the mat choices, ⋯, *Add to theme…*, *Hang…* and *Match on Wikidata…* each open), an archived work and a not-held work, phone and desktop, light and dark, 2026-10-29.

**Level:** High for Work, Medium for 02. Work's layout and words are settled by
ruling 8 and the Walls page it now matches. 02 moves a shared bar on four pages
and makes the toolbar sticky, and how that reads on a phone is not something the
rulings show. What raises it: the phone and dark photographs from
`arrt/tools/ux_walk.py` after 02, before 03 and 04 build on it.

## Scaffolding

No new project, dependency or tool. The curation suite (`cd arrt && uv run
pytest`, with `uv sync --group browser`) and the root suite are the harness.

### Verification Strategy

After 02 and after 04: run the branch locally against a copy of the NAS
catalogue and walk both pages as the owner would: select across pages and add
to a theme, archive from a filter, hang a work from its page, change its mat,
archive and restore it, match it on Wikidata. Then `arrt/tools/ux_walk.py` for
the phone and dark-mode photographs. Then 04, the owner on the deployed server.

## Build Chunks

### Chunk 01: This plan, the ruling on Edit…, and the backlog item

- **Type:** doc-only
- **Surfaces:** this plan; `.prawduct/artifacts/ia-proposal.md` (§ Rulings
  (2026-10-27): the 2026-10-29 ruling that the Work page has no *Edit…* until a
  work has a setting); one backlog item, editing a work's catalogue fields (#396).
- **Done when:** the root suite passes, and the backlog item exists with a link
  to the ruling.

### Chunk 02: Artworks, and every list acting from its toolbar

- **Type:** code
- **Visual change:** yes
- **Surfaces:**
  - `arrt/src/arrt/http/static/screens/collection.js`: the page head is
    *Artworks* (`h1`), then one line of facts (how many works, and what narrows
    them: the search, the theme, the filters), then the toolbar. Today's `h1`,
    "2,003 works in “Garden”", becomes that line. The stale-theme note follows
    the exception rule: one muted line, a notice only when it stops the page.
  - `arrt/src/arrt/http/static/core/selecting.js`: the action bar's acts (*Select
    all*, *Add to theme…*, *Remove from*, *Archive…*, *Get N works…*) and its count take
    the toolbar's left side while Select is on, in place of the bar at the
    window's foot. The live region that announces an act's outcome stays.
    *Add to theme…* opens a dialog holding the theme picker and *New theme…*'s
    name field, whose button is the act.
  - `app.css`: the toolbar is sticky while Select is on; on a phone, View, Sort
    and the filters step out of it until Select ends.
  - The other three lists, `screens/artists.js`, `screens/search.js` and
    `screens/topics.js`, only as far as they place the bar.
  - The Artworks row of `information-architecture.md` § Screen Inventory and
    its Information Hierarchy; the toolbar line in § The *arr layout.
  - The browser tests that pin the heading or the bar's place, each rewritten
    assertion naming ruling 1.
- **Done when:**
  1. The browser suite selects across a page boundary, adds to a theme (and to
     *New theme…*), removes from the filtered theme and archives, on Artworks,
     reading each outcome back from the server; and adds to a theme from an
     Artist page, a Topic page and Search results through the moved acts.
  2. With Select off, the toolbar's left side holds only *Select*: an absence
     test.
  3. The facts line names each narrowing it is given, and says only the count
     with none (one test per branch, including the absence).
  4. The axe scan is clean on all four lists with Select on and off, and the
     toolbar stays visible after scrolling a long grid (asserted from its
     bounding box, not its class).

### Chunk 03: Get's choice in a dialog

- **Type:** code
- **Visual change:** yes
- **Surfaces:** `arrt/src/arrt/http/static/core/getting.js` (`getSelection`):
  the registry half of a selection puts *Get N works…* in the toolbar, and its
  *Add to* theme picker, the new theme's name and the tier mark move into the
  dialog it opens, whose button is the act, as 02 did for *Add to theme…*.
  The single *Get this work* on a QID page keeps its inline control, which is
  not in a toolbar. Also the Search, Topic and Artist tests that drive a Get
  from a selection, each rewritten assertion naming ruling 1.
- **Done when:**
  1. The browser suite gets works from a selection on Search results, a Topic
     and an Artist page into an existing theme and a new one, read back from
     the server.
  2. Cancel and Escape in the dialog get nothing (asserted from the server)
     and return the keyboard to *Get N works…*.
  3. On Search results with both halves, the toolbar fits two rows at
     1280px (asserted from its bounding box).

### Chunk 04: The Work page

- **Type:** cumulative-final
- **Visual change:** yes
- **Surfaces:** `arrt/src/arrt/http/static/screens/work.js`, rebuilt to ruling 8:
  - the way back, then the work's title (`h1`), then one line of facts: its
    artist (a link), date, medium, size, and *Mat [Warm grey ▾]*, the mat as a
    fact that is its own control. Choosing a colour previews it on the picture
    and is kept with *Use this mat*, as the folded control under the picture does
    today. The Rights fact is gone.
  - the toolbar: *Hang…* (the filled act), *Add to theme…*, and ⋯ holding
    *Archive…* and *Match on Wikidata…*. An archived work's toolbar has
    *Restore* as its filled act and no *Hang…* (an archived work cannot hang).
    *Hang…* opens a dialog of walls (`arrt/src/arrt/http/static/core/editing.js`) in place of today's row
    of buttons, and asks through `arrt/src/arrt/http/static/core/selection.js` (`hangSelection`) as now. *Add to theme…* opens
    the selection's theme picker for this one work, *New theme…* included.
  - the walls and themes it is on, as facts with links, and *Kept off every
    wall* with *Allow on walls again* only when it is (an exception, quiet).
  - the record below the picture keeps its sections (*What this work is*, its
    master image, its sources); the debug-only ones stay debug-only.
  - the QID form of the page (`#work/Q…`, a work the library does not hold)
    keeps *Get this work* as its filled act, under the same head.

  Also `app.css`; the Work row of `information-architecture.md` § Screen
  Inventory and its Information Hierarchy; the browser tests that pin the Work
  page (`test_work_*`, the mat and the strip tests), each rewritten assertion
  naming ruling 8; the operator-verification entry for 04; and the change-log
  fragment.
- **Done when:**
  1. The browser suite hangs a work through *Hang…* on one wall and on two,
     adds it to a theme and to a new one, changes its mat, archives and restores
     it from ⋯, and matches it on Wikidata, each read back from the server with a
     non-default value (`core.md`, "test through that caller with a non-default
     value").
  2. Absence tests: no *Rights*; no *Hang…* on an archived work; no *Kept off
     every wall* line on a work that is not; no *Edit…*.
  3. The ⋯ menu opens and closes from the keyboard (Enter, arrows, Escape back
     to its trigger), and Cancel or Escape in each dialog changes nothing,
     asserted from the server.
  4. The axe scan is clean on a held work, an archived work and a QID work.
  5. Committed, then the one `/prawduct:critic cumulative`, and
     `/prawduct:pr create` when the owner asks.

### Chunk 05: In the house

The owner's walk, from the operator-verification entry 04 writes, on the NAS
after the release deploys: Artworks on a phone and a desktop, selecting across
pages; a work's page, hanging it, its mat, and ⋯; and whether both read as the
prototype did.

## Early Feedback Milestone

**Milestone chunk:** 02
**What the user can do:** open Artworks and act on a selection from the toolbar
on any list.

## Governance Checkpoints

**Commit & PR cadence:** commit per chunk after its review. 02 and 03 get
their chunk reviews; 04's cumulative makes the branch PR-ready. One PR to
`develop`.

- After 02: the photographs of the sticky toolbar on a phone, before 03 and 04
  build on the same toolbar.
- After 04 (cumulative): the full bundle.

## Status

Context: branched from `develop` at `83aac935`, 2026-10-29, after v0.7.0
(Walls). No other live plan claims this branch.
