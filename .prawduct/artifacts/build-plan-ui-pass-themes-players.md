---
artifact: build-plan
version: 1
scope: ui-pass-themes-players
branch: feature/ui-pass-themes-players
base: develop
working-branches: []
partition: serial, one worktree. 02 (Players) and 03-04 (Themes) touch different screens, but all three edit `app.css`, the Screen Inventory and Information Hierarchy tables of `information-architecture.md` (which `tests/preferences/test_screen_tables.py` reads as one file), and the route table in `app.js`; 04 builds on 03's dialog and 02's table-row *Edit…* shape, so a second builder would collide on all three.
depends_on:
  - artifact: ia-proposal
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: api-contract
  - artifact: clients
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ Direction, the *arr layout (sidebar sections, a toolbar on list pages, *arr names) → conforms: Players keeps Clients' slot under Settings, first; Themes keeps its slot under Artworks"
      - "§ Direction, navigation is a link and an act is a button → conforms: a theme card, a wall a theme hangs on and a Player's walls are links; Hang…, Edit…, New theme…, Add Player…, Remove from theme are buttons. `test_navigation_is_a_link.py` covers the new code"
      - "§ More than one wall (every act that changes a wall names the wall) → conforms: Hang… lists each wall by name, and its one confirmation names each wall it hangs on and each it takes the theme down from, through `arrt/src/arrt/http/static/core/hanging.js`"
      - "§ Vocabulary, the words for walls (a Player is the device at a wall, never a *client* on a screen a person reads; the server's records, routes and MCP tools keep `client`) → conforms: every word a person reads becomes Player; `/api/clients`, `client_id` and the MCP tools are unchanged"
      - "§ Navigation Structure (a page keeps its address's spelling when its label changes: `#collection` is Artworks, `#health` is Status) → conforms: the page stays `#clients`, `#clients?client=<id>` and `screens/clients.js`, labelled Players"
  - artifact: design-direction
    dispositions:
      - "§ Direction (token values live in `app.css`; `test_design_tokens.py` refuses any colour outside the token blocks) → conforms: no colour is added"
      - "§ Component Patterns, How a page reads (2026-10-27) → conforms: Themes, a theme and Players are built to it; each page's settings move into its *Edit…* with deleting the thing last"
      - "§ Component Patterns, Buttons (one filled act per region; no destructive style) → conforms: Hang… is the theme page's filled act; Delete and Remove are quiet and confirmed in words, as `ia-proposal.md` § Rulings (2026-10-27) records against the prototype's red"
  - artifact: accessibility-spec
    dispositions:
      - "norm 2 (WCAG 2.1 AA on the browser; colour never the sole carrier of state) → conforms: the drag handle is a `button` named *Move {title}* that also moves its work with the arrow keys (Home and End for top and bottom) and says where it landed in the live region, so order is never pointer-only; dialogs are `arrt/src/arrt/http/static/core/editing.js`'s `<dialog>`; a Player's status is a glyph and a word; the axe scan runs on Themes, a theme (Select off and on, each dialog open) and Players"
      - "norm 1 (the label) → inapplicable because nothing here changes what a Player draws"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer; MCP and HTTP are thin → conforms: the one server change lets `POST /api/themes/{id}` carry a description to `DisplayService.update_theme`, which already takes one and which `art_theme(action='update')` already reaches; the route adds no logic"
  - artifact: security-model
    dispositions:
      - "§ Direction (text from outside Arrt reaches the page as text) → conforms: theme names and descriptions, Player names and output names are typed by people or reported by devices, and are set with `textContent` through `el()`, in dialogs as on the page"
last_validated: 2026-10-29
---

# Build Plan — the UI pass, part 3: Themes, a theme and Settings › Players

## What this plan is

The third of three plans that build the owner's rulings of 2026-10-27
(`ia-proposal.md` § Rulings (2026-10-27); backlog #390). Walls was the first
(`build-plan-ui-pass-walls.md`), Work and Artworks the second
(`build-plan-ui-pass-work-artworks.md`). This one rebuilds **Settings ›
Clients** as **Settings › Players** (ruling 7), the **Themes** index and **a
theme's page** (ruling 9), all to the page rules (ruling 1).

It also ends the period with two homes that the Walls plan opened: a wall's
Player, screen and label panel are set in the wall's *Edit…* dialog, and
Players stops offering them.

**Not in this plan:**

- **Renaming `client` on the server.** `information-architecture.md` §
  Vocabulary keeps `client` in the records, the routes and the MCP tools, as a
  contract with what calls them (Arrt Player authenticates to `/api/clients`'
  tokens). Only what a person reads changes.

## Goals

**Response taken:** proceed, citing #390 and the rulings. The design is the
owner's, approved from the prototype. One gap, *Add a work*, which ruling 9
does not name, was put to the owner on 2026-10-29 and ruled (below).

**Product:** Players answers "what devices does this house have, and are they
working"; Themes answers "what playlists do I have, and where is each
playing"; a theme's page answers "what is in it, in what order, and where does
it hang". Each opens the way Walls, Artworks and Work now do.

**Architecture:**

- A client rebuild, with one server change: `POST /api/themes/{id}` accepts an
  optional `description`, told apart from an absent one by
  `model_fields_set`, so a rename still cannot clear a description by accident
  (the reason `RenameTheme` carried a name alone). `art_theme(action='update')`
  already takes both.
- **Every act on these pages already has a route.** Hang: `POST
  /themes/{id}/activate` per ticked wall; take down: `DELETE
  /walls/{id}/theme` per unticked wall; remove a selection: `POST
  /themes/{id}/works/remove`; order: `POST /themes/{id}/works/{work}/position`;
  default: `POST /themes/{id}/default`; Players: the `/api/clients` routes.
- The theme page's member list acts on a selection through
  `core/selecting.js`, the model the four library lists share, so *Remove from
  theme* sits in the toolbar as their acts do since part 2.
- The Hang… dialog asks one question for the whole change, naming each wall
  it hangs on and each it takes down from. A ticked wall left ticked is not
  re-hung: republishing stays the Walls picker's (the comment in
  `screens/theme.js` explains why that filter is load-bearing).

**Constraints:**

- The browser suite boots a real server per class (`CLAUDE.md`) and runs
  whenever `static/` changes, after `uv sync --group browser`.
- `tests/preferences/test_screen_tables.py` holds the IA's screen tables and
  sidebar order against `app.js`: the Clients → Players rename lands in the
  route table, `SCREEN_NAMES` and the IA in one commit.
- `pages.py` `UI_PATHS` gains `/players`, keeping `/clients`.
- Browser tests pin today's wording (*Clients*, *Take down from …*, the per-row
  ↑ ↓ buttons, the inline rename). Each assertion rewritten for that reason
  names the ruling that changed it, in the same commit (`core.md`, "When you
  drop or rewrite a test's assertion…").

**Tradeoffs accepted:**

- None yet.

**Ruled with this plan: no *Add a work* on a theme's page** *(the owner,
2026-10-29)*. Today a theme's page has a picker of every work in the library
and *Add*. Ruling 9 lists the page's acts and does not name it; the page rules
put nothing but the name, the facts and the toolbar above the content; and on
*All works* the picker lists the whole library. Asked whether to drop it for a
link to Artworks, keep adding behind an *Add works…* dialog with a search, or
offer no add at all, the owner chose the link: the toolbar's *Add works* goes
to Artworks, where *Add to theme…* acts on a selection with the pictures and
filters beside it. Recorded in `ia-proposal.md` § Rulings (2026-10-27).

**Decisions made mid-build:** *(appended while building; one line each, naming
the goal or prior choice that settled it.)*

- 02: the page keeps its address, `#clients`, and its module, labelled Players: § Navigation Structure keeps a renamed page's spelling so a bookmark never breaks over a word, as Artworks kept `#collection`. The plan had first renamed the address; the norm settled it.
- 02: the server's sentences a person reads say Player (the display fault, and why a heartbeat could not be read), since they reach Players and Walls as written. The log line and the records keep `client`.
- 02: *No Player shows this wall* opens the wall's *Edit…* rather than linking to Players, which no longer assigns; *Captioned by …* in that dialog loses its link to Clients, since the controls under it are where a label changes.
- 02: a Samsung Frame is named *Samsung Frame* by `core/outputs.js`' `screenName`, on Players and in Walls' screen picker alike; it showed as its port's name, `frame`, which § Vocabulary rules out.
- 02: a label panel's captioned wall is named from `GET /api/walls`, since it may be a wall on another Player, which the Player's own listing does not name (found by its test).
- 02: the axe scan ran by hand, as parts 1 and 2's did (the suite does not fetch axe-core): `ux_walk.scan` from a temporary test over the suite's fixtures, a Player reporting two screens and a panel captioning a wall beside one with no token, was clean on Players, *Add Player…*, *Edit…* and the token dialog, at 1280 and 390 wide, light and dark, 2026-10-29.
- 02, flagged, not fixed here: on Walls, a wall's *Edit…* opened in the moment before the page repaints after another dialog's write offers what was true before that write (a panel just stopped is not offered until the repaint lands). Found by a test under parallel load, which now waits for the repaint as a curator would see it; the window is one repaint, and the fix (each dialog reading a fresh listing as it opens) is Walls' and is for the backlog.

**Level:** High for Players and the Themes index, whose layout and words the
rulings and the two earlier plans settle. Medium for a theme's page: the drag
handle is new to the product, and how it reads on a phone is not something the
rulings show. What raises it: the phone photographs of 04 from
`arrt/tools/ux_walk.py`, and a keyboard-only reorder in the browser suite.

## Scaffolding

No new project, dependency or tool. The curation suite (`cd arrt && uv run
pytest`, with `uv sync --group browser`) and the root suite are the harness.

### Verification Strategy

After each code chunk: run the branch locally against a copy of the NAS
catalogue and use the page as the owner would. Players: add a Player and read
its token once, rename it, rotate the token, remove it. Themes: create a theme,
open it, reorder by dragging and by keyboard, remove a selection, edit its
name and description, make it the default, hang it on one wall and take it down
from another in one dialog, delete it. Then `arrt/tools/ux_walk.py` for the
phone and dark-mode photographs, and the axe scan. Then 05, the owner on the
deployed server.

## Build Chunks

### Chunk 01: This plan

- **Type:** doc-only
- **Surfaces:** this plan.
- **Done when:** the root suite passes.

### Chunk 02: Settings › Players

- **Type:** code
- **Visual change:** yes
- **Surfaces:**
  - `arrt/src/arrt/http/static/screens/clients.js`, rebuilt as Players: the
    page's name, one line of facts (how many Players, how many reporting), and
    a toolbar with *Add Player…*. Then a table, one row per Player: its name and
    status (a glyph and a word: reporting, not heard from since …, no token,
    never reported), its screens and the walls on each (each wall a link), its
    label panel and the wall it captions. One quiet *Edit…* per row: *Name*
    (*Rename*), the token (*Issue a token* or *Rotate the token…*, which asks
    first), and *Remove…* last, which asks first naming the walls left without
    a Player. A token issued, by *Add Player…* or in *Edit…*, is shown once in
    the dialog that issued it, with what to put in the Player's settings.
    Assigning a wall, unassigning, captioning and stopping a caption leave the
    page: they are the wall's *Edit…*.
  - The words a person reads: the sidebar, the Settings index
    (`screens/settings.js`), Walls' links (*See Settings › Players*, and any
    remaining *Settings › Clients*), and the route table's label in `app.js`.
    The address stays `#clients` (§ Navigation Structure keeps a renamed
    page's spelling), so `core/route.js` and `pages.py` do not change.
    *No Player shows this wall* on a wall's card opens that wall's *Edit…*,
    where a Player is now chosen, in place of its link to Clients.
  - `app.css`; the Clients rows of `information-architecture.md` § Screen
    Inventory, § The *arr layout, Information Hierarchy and Screen States,
    renamed and rewritten; `tests/preferences/test_screen_tables.py`'
    `SCREEN_NAMES`; the browser tests that drive Clients, each rewritten
    assertion naming ruling 7.
- **Done when:**
  1. The browser suite adds a Player and reads its token once (and not after a
     reload), renames it, rotates its token, issues a first token and removes
     it, each read back from the server with a non-default value.
  2. Absence tests: no assign, unassign, caption or stop-caption control on
     Players; no word *Client* or *Clients* on any page a person reads (a scan
     of the rendered text of every routed page in the suite's fixtures).
  3. `#clients?client=<id>` arrives at Players with that row in view; a
     wall's *No Player shows this wall* opens that wall's *Edit…*.
  4. Cancel or Escape in each dialog changes nothing, asserted from the server;
     the axe scan is clean on Players with each dialog open.

### Chunk 03: The Themes index, and a theme's description

- **Type:** code
- **Visual change:** yes
- **Surfaces:**
  - `arrt/src/arrt/http/models.py` `RenameTheme` (renamed for what it now
    carries) and `api.py` `rename_theme`: an optional `description`, passed to
    `update_theme` only when the body names it; a curation-suite test that a
    rename leaves the description, that a description is set and that `null`
    clears it. `api-contract.md`'s `POST /api/themes/{id}` row, additive.
  - `arrt/src/arrt/http/static/screens/theme.js`, the index: *Themes*, one
    line of facts (how many themes, which is the default), a toolbar with *New
    theme…* (a dialog: *Name*, *Description*, *Create*), and one card per theme:
    a picture, its name, its size and the walls it hangs on, each card a link.
    The inline *New theme* form leaves the page head. The note that no theme is
    the default stays an exception, quiet unless it stops the page.
  - `app.css`; the Themes index's half of the Themes row of
    `information-architecture.md` § Screen Inventory and Information Hierarchy;
    the browser tests that pin the index.
- **Done when:**
  1. The browser suite creates a theme with a description from *New theme…*
     and reads both back from the server; Cancel creates nothing.
  2. The curation suite's three description tests, each watched failing once
     against the unchanged route.
  3. The axe scan is clean on the index, with the dialog open and shut.

### Chunk 04: A theme's page

- **Type:** cumulative-final
- **Visual change:** yes
- **Surfaces:** `arrt/src/arrt/http/static/screens/theme.js`, a theme, rebuilt
  to ruling 9:
  - the way back, the theme's name (`h1`), one line of facts: how many works,
    *Default* when it is (works you accept join it), the walls it hangs on
    (links), its description.
  - the toolbar: *Hang…* (the filled act), *Edit…*, and Select on the right;
    with Select on, *Remove from theme* on the selection, as part 2's lists act.
  - *Hang…* opens a dialog of every wall, ticked where the theme hangs; *Hang*
    asks once through `core/hanging.js`, naming each wall it hangs on and each it
    takes the theme down from, and only changed walls are sent. No walls: the
    dialog says so, in today's words. A fresh catalogue seeds one wall
    (`persistence/migrations.py`) and nothing deletes a wall, so the case is
    kept for a catalogue whose walls were removed by hand, not built for.
  - *Edit…*: *Name*, *Description*, *Make this the default* (absent on the
    default), *Delete…* last (asks first; the server's refusal for a hung theme
    shown as written).
  - the members in order, each row its picture, title and artist (links), its
    size against the walls (`too_small_for`), and a drag handle; no per-row
    buttons. The shortfall note stays an exception, quiet.
  - *Add works* in the toolbar, a link to Artworks (the ruling above); the
    *Add a work* picker and its *Add* are gone.
  - Walls' empty-theme note, whose *Add works to {theme}* links to the theme's
    page for its picker (`screens/walls.js`): it goes where adding now is.

  Also `app.css`; the theme's half of the Themes row of
  `information-architecture.md` and its Information Hierarchy and Screen
  States; the browser tests that pin the theme page, each rewritten assertion
  naming ruling 9; the operator-verification entry for 04; and the change-log
  fragment.
- **Done when:**
  1. The browser suite reorders by drag and by keyboard (arrows, Home, End),
     removes a selection across a page boundary, edits the name and the
     description, makes the theme the default, and deletes one, each read back
     from the server with a non-default value.
  2. One *Hang…* that ticks one wall and unticks another hangs and takes down
     in one confirmation naming both, read back from `GET /api/walls`; leaving
     the ticks as they were sends nothing.
  3. Absence tests: no *Take down*; no ↑, ↓, *Move to top* or *Move to bottom*;
     no per-row *Remove*; no *Make this the default* on the default theme; no
     *Add a work* picker.
  4. Cancel or Escape in each dialog changes nothing, asserted from the server;
     the axe scan is clean on a theme with Select on and off and each dialog
     open, phone and desktop.
  5. Committed, then the one `/prawduct:critic cumulative`, and
     `/prawduct:pr create` when the owner asks.

### Chunk 05: In the house

The owner's walk, from the operator-verification entry 04 writes, on the NAS
after the release deploys: Players on a phone and a desktop; Themes; a theme,
dragging its order on a phone, *Hang…* across two walls; and whether they read
as the prototype did.

## Early Feedback Milestone

**Milestone chunk:** 02
**What the user can do:** open Settings › Players and see every Player as a
row, with the wall's settings in one place.

## Governance Checkpoints

**Commit & PR cadence:** commit per chunk after its review. 02 and 03 get their
chunk reviews; 04's cumulative makes the branch PR-ready. One PR to `develop`.

- After 02: the photographs of the Players table on a phone, since 04's member
  rows reuse the row shape.
- After 04 (cumulative): the full bundle.

## Status

Context: branched from `develop` at `be641ba2`, 2026-10-29, after part 2 (#398)
merged. `build-plan-ui-pass-work-artworks.md` stays live until its release
(its Chunk 05 is the owner's walk); it claims its own branch, not this one.
