---
artifact: build-plan
version: 1
scope: ui-pass-walls
branch: feature/ui-pass-walls
base: develop
working-branches: []
partition: serial, one worktree. 03 and 04 both rewrite `arrt/src/arrt/http/static/screens/walls.js`, and 04's Edit dialog calls the route 02 adds, so nothing can be handed to a second builder without the two colliding. 02 alone is independent, and it is small enough that a brief would cost more than building it.
depends_on:
  - artifact: ia-proposal
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: api-contract
  - artifact: architecture
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ Direction, the *arr layout (sidebar sections, a toolbar on list pages, *arr names) → conforms: Walls keeps its slot and gains the shared `toolbar()` every list page already uses; no section or page is added (a wall's setup is a dialog, not a page, ruling 4)"
      - "§ Direction, navigation is a link and an act is a button → conforms: History and a work's title on a card are links; Skip, Remove…, Edit…, Add wall…, Scene… and the Hanging picker are buttons, because each acts or opens a dialog. `test_navigation_is_a_link.py` covers the new code"
      - "§ More than one wall (every act that changes a wall names the wall in its control and its confirmation) → conforms: each card's acts carry the wall's name in their accessible names, and every dialog's title names the wall"
      - "§ Vocabulary, the words for walls (2026-10-27) → conforms for Walls, which is the page this plan changes: Player, screen, label panel, Hanging, Remove…, Search your library. Settings › Clients keeps its words until its own plan"
  - artifact: design-direction
    dispositions:
      - "§ Direction (token values live in `app.css`, and `test_design_tokens.py` refuses any colour outside the token blocks) → conforms: the screen-off picture is dimmed with opacity over the existing `--scrim` tokens, and no colour is added. If one is needed, it is added inside the token blocks, where the test reads it"
      - "§ Component Patterns, How a page reads (2026-10-27) → conforms: this plan is the first page built to it"
      - "§ Component Patterns, Buttons (one filled act per region; no destructive style) → conforms: Skip is each card's filled act; Remove… and Edit…'s delete-free dialog carry no danger style. This departs from the prototype's red, as `ia-proposal.md` § Rulings (2026-10-27) records"
  - artifact: accessibility-spec
    dispositions:
      - "norm 2 (WCAG 2.1 AA on the browser; colour never the sole carrier of state) → conforms: a wall's state is a badge (glyph, word, colour) from `core/glyphs.js`; every dialog is the platform `<dialog>` `confirm.js` already uses, for focus trapping and Escape; the axe scan in the browser suite runs on the new page"
      - "norm 1 (the e-paper label) → inapplicable because nothing here changes what a Player draws"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer; MCP and HTTP are thin → conforms: renaming a wall is one `DisplayService` method; its route and its `art_display` action each make one call"
      - "the Library/Programming seam → conforms: renaming touches only Programming's `walls` table; no Library read is added"
      - "the manifest is the only channel to a Player → conforms: a wall's name is not in its feed (`player-contract.md`), so renaming republishes nothing"
  - artifact: security-model
    dispositions:
      - "§ Direction (text from outside Arrt reaches the page as text) → conforms: a wall's name is the owner's own text and is set with `textContent`, through `el()`, like every name on the page"
  - artifact: data-model
    dispositions:
      - "per-device runtime state never lives in the catalogue → conforms: the screen-off card reads `display_state` from the heartbeat as it does today; nothing about it is stored"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ The television belongs to whoever is using it → inapplicable because no act on this page reaches a set except through the feed, as today"
last_validated: 2026-10-27
---

# Build Plan — the UI pass, part 1: Walls

## What this plan is

The first of three plans that build the owner's rulings of 2026-10-27
(`ia-proposal.md` § Rulings (2026-10-27)). The owner walked Walls on the
deployed server, found it jumbled, and asked for a coherent design across
several pages. A clickable prototype of six pages, built on the owner's real
library, was reviewed and approved with three changes. This plan rebuilds
**Walls** to it, and adds the one server act the new page needs.

The prototype is a private Claude artifact, not committed: it carries the
owner's library pictures, and this repository is public. The rulings, the page
rules in `design-direction.md` § Component Patterns ("How a page reads") and
this plan are the record a builder works from.

**Not in this plan:**

- **The Work and Artworks pages** (rulings 1 and 8) and **Themes, a theme and
  Settings › Players** (rulings 1, 7 and 9). Each is its own plan and PR,
  filed to the backlog with this one's records.
- **Deleting a wall.** The prototype's Edit dialog offered it. Nothing in the
  server can delete a wall today (no service method, route or tool), and what
  it would mean for the wall's history and its Player's feed is a design
  question, not a button. Filed to the backlog; the Edit dialog has no
  delete until it is built.
- **Moving wall assignment off Settings › Clients.** This plan puts assignment
  and the label in the wall's Edit dialog (ruling 4). Clients keeps its own
  controls until the Players plan rebuilds it, so for one release the same
  setting has two homes. Both call the same routes, so they cannot disagree.

## Goals

**Response taken:** proceed. The owner reviewed the prototype, gave three
changes (*Remove…*, no "until changed", no rights on Work), and answered "yes
to all" to the four questions (Players; cards with no page per wall; Scene as a
dialog; the next work dimmed when the screen is off, re-ruled during the build as the last shown, else the next, once the builder corrected a wrong premise).

**Product:** Walls answers "what is on each wall, and what comes next", and
lets the owner change it without reading a sentence to find the control. The
everyday acts (Skip, Remove…, choosing what hangs) sit where the eye already
is; setup and rare acts (a wall's Player, playback, a scene) are one step
away, in dialogs.

**Architecture:**

- Every act on the page already has a route except renaming a wall (02). The
  page is a client rebuild over `GET /api/walls`, `GET /api/themes`,
  `GET /api/scenes/live`, `GET /api/clients` and the existing writes.
- The shared pieces go in `core/` only if a second page in the next two plans
  will use them: the Edit dialog shell (the Work, theme and Player pages all
  have one) and the fact-as-control picker (the Work page's mat). The toolbar
  is `core/toolbar.js`, already shared.

**Constraints:**

- The browser suite boots a real server per class (`CLAUDE.md`), and runs
  whenever `static/` changes.
- `tests/preferences/test_screen_tables.py` holds the IA's screen tables
  against `app.js`. Walls keeps its route, so only its rows' prose changes.
- Wording the browser tests pin today changes by ruling ("Not this one
  again", "until changed", "Find a work"). Each assertion rewritten for that
  reason says so in the same commit (`core.md`, "When you drop or rewrite a
  test's assertion…").

**Tradeoffs accepted:**

- Two homes for wall assignment until the Players plan ships (above). Worth
  revisiting if that plan slips past one release.
- The screen-off card shows the last-shown work, and the next work only until the showings log has one (ruling 6, re-ruled once the builder corrected the premise it was first asked on).

**Decisions made mid-build:** *(appended while building; one line each, naming
the goal or prior choice that settled it.)*

- 02: renaming is `POST /walls/{wall_id}`, not the `PATCH` this plan first named, because renaming a client is `POST /clients/{client_id}` (match the product's other choices).
- 02: `art_display`'s menu was at its 2 KB budget (`DESCRIPTION_BUDGET_BYTES`), so the `status` and `add_label` descriptions say the same in fewer words to make room for `rename_wall`.
- 02 (after its review): a name another wall has is refused as "Another wall is already called '…'." by `add_wall` and `rename_wall` alike, rather than the store's "already stored", because 04's dialogs show the refusal to the owner.

**Level:** High for the page; Medium for the size of 03. The prototype settles the layout
and the words, and every write already exists. What could raise it: 03's diff
is most of a 1,500-line screen, so if it does not fit one review, the Scene
dialog moves to 04 rather than the review being skimmed.

## Scaffolding

No new project, dependency or tool. The curation suite (`cd arrt && uv run
pytest`, with `uv sync --group browser` so the browser tests run) and the root
suite are the harness.

### Verification Strategy

Beyond the suites, after 03 and again after 04: run this branch locally
against a copy of the NAS catalogue, and walk the prototype's states on the real
page (screen off, showing, a scene, a wall with no Player, two walls), with
`arrt/tools/ux_walk.py` for the phone and dark-mode photographs. Then 05, the
owner on the deployed server.

## Build Chunks

### Chunk 01: The rulings, the page rules and this plan

- **Type:** doc-only
- **Surfaces:** `.prawduct/artifacts/ia-proposal.md` (§ Rulings
  (2026-10-27), and a pointer in § Walls), `.prawduct/artifacts/design-direction.md`
  (§ Component Patterns, "How a page reads"),
  `.prawduct/artifacts/information-architecture.md` (§ Vocabulary, the words
  for walls), this plan, and three backlog items: the Work and Artworks plan,
  the Themes and Players plan, and deleting a wall.
- **Done when:** the root suite passes, including the citation guard, and the
  three backlog items exist with links to the rulings.

### Chunk 02: Renaming a wall

- **Type:** code
- **Exposed API:** `/api` (internal, unversioned, `ServiceError` envelope, as
  recorded in `api-contract.md`)
- **Surfaces:** `arrt/src/arrt/programming/display.py` (`rename_wall`, beside
  `add_wall`, refusing an empty or duplicate name the way `add_wall` does);
  `arrt/src/arrt/http/api.py` (`POST /walls/{wall_id}` with `{name}`,
  returning the wall as `GET /walls` does); `arrt/src/arrt/mcp/tools.py` and
  `bindings.py` (`art_display(action='rename_wall')`, sharing the name
  description `add_wall` and `rename_client` already share);
  `api-contract.md` (the route row); tests beside the existing wall tests.
- **Done when:**
  1. The service, the route and the tool each have a test through the
     service's own errors (an unknown wall; an empty name; a name another wall
     has), watched failing first.
  2. Renaming republishes nothing. A test holds that the wall's feed is
     byte-identical before and after.
  3. The api-contract row says what was built.

### Chunk 03: The wall card

- **Type:** code
- **Visual change:** yes
- **Surfaces:** `arrt/src/arrt/http/static/screens/walls.js`, rebuilt to
  `design-direction.md` § Component Patterns, "How a page reads":
  - the page head (*Walls*, one line of facts) and `toolbar()` with *Add
    wall…* (wired in 04) and *Scene…*;
  - one card per wall: its name, a state badge (*Showing*, *Screen off*, *No
    Player*, *Scene*), *Edit…* (wired in 04), the picture on its mat;
  - with the screen off, the last-shown work dimmed under "Screen off since {time}", or the next work when the wall has shown nothing yet (ruling 6, as re-ruled);
  - the work's title (a link) and artist; *Skip*, the card's one filled act,
    and *Remove…*, which keeps today's two choices (from this theme; from every
    wall) under its new name (ruling 2);
  - *Hanging [theme ▾]*, the theme's name as the control that hangs another
    (ruling 3), with no "until changed";
  - the next three works with their times;
  - a footer of links: *History*, and *{n} works can't be shown here* (which
    opens the list the card's *Not showing* section holds today);
  - *Scene…* opens a dialog holding today's scene section, with its search labelled
    *Search your library*; a live scene is one line above the cards, with
    *Release* (ruling 5).

  Also `arrt/src/arrt/http/static/app.css` for the card and the dimmed picture, inside the token rules; the
  Walls rows of `information-architecture.md` § Screen Inventory, Information
  Hierarchy and Screen States; and the browser tests under `arrt/tests/browser/`
  that pin Walls' wording (`test_walls_lead_with_the_work.py`,
  `test_the_history.py` and the scene tests), each rewritten assertion naming
  the ruling that changed it.
- **Done when:**
  1. The browser suite drives Skip, Remove… (both choices), the Hanging
     picker, the scene dialog through apply and release, and the screen-off,
     no-Player and two-wall states, each from server state rather than a
     stubbed response.
  2. Each conditional line has an absence test as well (the scene line with
     no scene; the *can't be shown* link with nothing excluded; the No Player badge on an
     assigned wall).
  3. The axe scan is clean on Walls, and a keyboard-only pass reaches every act
     and closes every dialog with Escape.
  4. `git grep -i "not this one again"` finds the old name only in records that
     describe the past (change logs, archived plans, the 2026-10-07 ruling), and
     `git grep -i "until changed"` finds it nowhere in `arrt/src`.

### Chunk 04: Edit and add a wall

- **Type:** cumulative-final
- **Visual change:** yes
- **Surfaces:** `arrt/src/arrt/http/static/screens/walls.js` (the *Edit…*
  dialog: name (02's route); *Where it shows*, the Player and screen (the
  `POST`/`DELETE /walls/{id}/client` and `/display` routes Clients uses); *Label
  panel* (`/walls/{id}/labels`); *Playback*, the interval and the order
  (`PUT /walls/{id}/playback`); *Fit*, the tallest and widest shapes; *Mat*
  (`PUT /walls/{id}/mat`). *Add wall…*: name, Player and screen, and the theme to
  hang (`POST /walls`, then the existing assign and hang calls). The dialog
  shell goes in new `arrt/src/arrt/http/static/core/editing.js`, so the next
  two plans reuse it. It is a platform `<dialog>`, like `confirm.js`.) Also the
  operator-verification entry for 05, and the change-log fragment.
- **Done when:**
  1. The browser suite edits each setting through the dialog and reads it back
     from `GET /api/walls`, with a non-default value for each (`core.md`, "test
     through that caller with a non-default value").
  2. Adding a wall with a Player and a theme leaves it showing in the suite's
     Player double, end to end through the feed.
  3. Cancel and Escape change nothing (asserted from the server, not the page).
  4. Committed, then the one `/prawduct:critic cumulative`, and
     `/prawduct:pr create` when the owner asks.

### Chunk 05: On the wall

The owner's walk, from the operator-verification entry 04 writes, on the NAS after
the release deploys: each state of the card on the real wall; rename the wall;
add a second wall on HDMI 2 and see it reach the Player; a scene through the
dialog; and whether the words read as the prototype did.

## Early Feedback Milestone

**Milestone chunk:** 03
**What the user can do:** open Walls and see the redesigned card, with Skip,
Remove…, the Hanging picker and the scene dialog working against the real
server.

## Governance Checkpoints

**Commit & PR cadence:** commit per chunk after its review. Five chunks, so
not a short plan: 02 and 03 each get their chunk review, and 04's cumulative is
the one that makes the branch PR-ready. One PR to `develop`.

- After 03: a look at the page against the prototype, before the dialogs are
  built on it.
- After 04 (cumulative): the full bundle.

## Status

- [ ] Chunk 01: The rulings, the page rules and this plan
- [ ] Chunk 02: Renaming a wall
- [ ] Chunk 03: The wall card
- [ ] Chunk 04: Edit and add a wall
- [ ] Chunk 05: On the wall

Context: branched from `develop` at `1a1af8a3`, 2026-10-27, the commit the NAS
runs. Waves 4f and 5 have plans with open operator walks; neither claims this
branch.
