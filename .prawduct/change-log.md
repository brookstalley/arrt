# Change Log — Samsung Frame Art Loader

<!-- Append new entries at the top. Each entry is a ## section.
     This file is separate from project-state.yaml to reduce merge conflicts
     when multiple branches add entries simultaneously.

     # Tagged entries

     Add a tag-line directly under each ## header recording its rollup scope
     and, once released, which release it belongs to.

     **Nothing is REGENERATED from these tags any more — but they are still
     READ, and the difference matters when you write one.** `prawduct-hook
     regen-views` once rebuilt the build-plan `## Status` block, a release-notes
     view and a `scope_rollups:` block from them; prawduct v3.2.8 retired that
     command and the `views_enabled` switch that governed it, so this header
     spent three releases telling readers to run something that no longer
     exists.

     What survives is consumption, not generation. `scope=` and the *absence* of
     `release=` are how release-readiness enumerates work that has not shipped —
     which is why any value at all in `release=`, a placeholder included, drops
     that entry's whole scope out of the pending set. The PR flow refuses a
     branch whose entry carries no `scope=`. Only `status=` is inert now, and
     the Status checkboxes are ticked by hand and believed by every reader.

     Format:

         ## YYYY-MM-DD: title (vN.M.P)

         <!-- prawduct: release=v1.3.18 | scope=v1.4 -->

         **Why:** ...

     Recognized keys:
       chunks   - retired: nothing reads it. Archived entries carry it as
                  history; `scope=` ties an entry to its plan.
       release  - version string (used by the release-notes view)
       status   - shipped | merged (legacy). Write a new entry with NO
                  status= on the feature branch: a statusless tagged entry
                  is the release-pending state, and it becomes "merged" by
                  construction when its PR lands — no stamp, no post-merge
                  bookkeeping commit (protected branches take commits only
                  by PR). Flip to `shipped` as part of release-prep when
                  the integration branch is released (gitflow), or write
                  `status=shipped` directly in the closing PR when the
                  PR's base IS the release surface (trunk; include
                  `release=vN.M.P` when the product tracks versions —
                  release-notes groups by it) — either way the tag merges
                  atomically with the work it describes.
                  `merged` is a legacy stamp some logs carry; it is treated
                  as statusless. Don't invent states — the three above are
                  the whole vocabulary.
       scope    - rollup identifier (e.g., v1.4) -->

> **Names, 2026-10-01.** Entries are history and keep the names of their day. Until
> 2026-10-01 **Curatarr** named the server and **Arrt** named the player. Since then
> the server is **Arrt** and the player is **Postarr**
> (`build-plan-rename-arrt-postarr.md`). Paths and package names here are the
> old ones.
>
> **Names, 2026-10-08.** Postarr is now **Arrt Player**: `postarr/` became
> `arrt-player/` and the `postarr` package `arrt_player`
> (`build-plan-rename-arrt-player.md`). Entries before this date keep `postarr`.


<!-- Older entries live in .prawduct/change-log-archive/YYYY-MM.md, moved there verbatim by `prawduct-hook archive-change-log`. -->

## 2026-10-29: Settings › Players, Themes and a theme's page, rebuilt to the page rules (UI pass, part 3)

<!-- prawduct: scope=ui-pass-themes-players -->

**Why:** the last of the three plans that build the owner's rulings of
2026-10-27 (`ia-proposal.md` § Rulings (2026-10-27), #390). Settings › Clients
becomes Settings › Players (ruling 7), and Themes and a theme's page are rebuilt
(ruling 9), each opening as Walls, Artworks and Work do. A wall's Player, screen
and label panel are now set in one place, the wall's *Edit…*.

**What changed:**
- **Settings › Players** is a table, one row per Player: its status (*Reporting*,
  *Not heard from since …*, *No token*, *Never reported*, *Report unreadable*),
  its screens as *HDMI 1* or *Samsung Frame* with the wall on each, and its label
  panel with the wall it captions. One *Edit…* per row: its name, its token
  (*Rotate the token…* asks first; a token is shown once, in the dialog that
  issued it) and *Remove…*. *Add Player…* in the toolbar. Assigning a wall and
  captioning it left this page for the wall's *Edit…*. The address stays
  `#clients`, as every renamed page's has.
- **No page calls a Player a client.** The server's sentences a person reads say
  Player too (the display fault, why a report could not be read, and the
  notices kept with a placement it cannot confirm). The records, routes and MCP
  tools keep `client`.
- **Walls:** *No Player shows this wall* opens the wall's *Edit…*. A placement
  the server keeps but cannot confirm says the server's notice in that dialog,
  which stays open to read it (Players said it until this change). Walls' screen
  picker names a Frame *Samsung Frame*.
- **Themes** opens with its name, a line of facts (how many, which is the
  default) and *New theme…*, a dialog of name and description whose *Create*
  opens the new theme's page.
- **A theme's page** opens with its way back, its name, a line of facts (how many
  works, *Default* when it is, the walls it hangs on as links) and a toolbar:
  *Hang…* (a dialog of every wall, ticked where it hangs, asked once for every
  wall it changes; in place of a button per wall and *Take down*), *Edit…* (name
  and description, *Make this the default*, *Delete…*) and *Add works*, a link to
  Artworks. Works are removed by selecting them. The order is a drag handle per
  row, dragged by pointer or finger or moved by the arrow keys, Home and End.
  The *Add a work* picker is gone (the owner, 2026-10-29), and the page no longer
  loads the whole library.

**Server:** `POST /api/themes/{id}` takes an optional `description`, read only
when the body names it (`null` clears it), additive (`api-contract.md`). The
server's person-read sentences about Players say Player.

**Tests:** browser tests pinning Clients and the old theme page were rewritten,
each naming the ruling that moved it; those that drove controls the rulings
removed (assigning and captioning from Clients, the *Add a work* picker) were
retired with the tests that now hold the same contract named. New tests cover
every Players act against the server and the Player's own route, a scan for
*client* on every sidebar page, the theme description route, *New theme…*, the
handle by keyboard and by drag, *Hang…* across walls (exactly the changed walls
sent), and Cancel and Escape in each new dialog. Each new test was watched
failing on a re-break. The axe scan (by hand, `arrt/tools/ux_walk.py`) is clean
on Players, Themes and a theme with each dialog open.

**Rollback:** revert the branch's merge; the description field is additive and
nothing is stored differently.

Retires: "Assign it in Settings › Clients", "Change in Settings › Clients", "See Settings › Clients", "is assigned on Settings › Clients" — a wall's Player and label are set in its own Edit… since ruling 7 of 2026-10-27, and the page is Players.

## 2026-10-29: Artworks and a work's page, rebuilt to the page rules (UI pass, part 2)

<!-- prawduct: scope=ui-pass-work-artworks -->

**Why:** the second of the three plans that build the owner's rulings of
2026-10-27 (`ia-proposal.md` § Rulings (2026-10-27), #389). Artworks and Work
now open as Walls does: the page's name, one line of facts, and a toolbar
holding its acts.

**What changed:**
- **Artworks** is headed *Artworks*, with a line of facts saying how many works
  and what narrows them. **On every list** (Artworks, an Artist, a Topic, Search
  results), *Select*'s acts sit in the toolbar, which stays at the top of the
  window while Select is on. *Add to theme…* and *Get N works…* each open a
  dialog holding the theme picker and the new theme's name. The selection bar no
  longer sits at the foot of the window.
- **A work's page** opens with its way back, its title, one line of facts and its
  toolbar. The facts are the artist (a link, with nationality and life), date,
  medium, size, and *Mat [colour ▾]*, whose value opens the mat choices. The
  toolbar holds *Hang…* (the one filled act; several walls are offered in a
  dialog), *Add to theme…* (the selection's dialog, for this one work), and ⋯
  holding *Archive…* and *Match on Wikidata…*. An archived work has *Restore* in
  place of *Hang…*. Walls and themes sit beside the picture. A work kept off every
  wall says so in one quiet line, with *Allow on walls again*. The Rights fact is
  gone (ruling 8). There is no *Edit…*: the owner ruled on 2026-10-29 that it
  waits until a work has a setting (#396). A work the library does not hold
  (`#work/Q…`) opens under the same head, with *Get this work* as its act.
- `core/toolbar.js` gains `actionMenu` (⋯), sharing `menuButton`'s keyboard;
  `core/membership.js` gains `themeChoice`, the picker both *Add to theme…*
  dialogs use.
- A panel (`core/editing.js`) closed by a control leaves the page at once, not
  when the browser's queued `close` event runs. Until then, a question asked in
  the same click (*Hang…*'s wall choice) shared the page with the closed panel's
  title, and the browser suite read the wrong one on CI.

**No server change.** Every act calls a route that already existed.

**Tests:** browser tests pinning the old positions and words were rewritten, each
naming the ruling that moved it. New tests cover Add to theme into an existing
and a new theme, Cancel and Escape in each dialog (read back from the server),
the ⋯ keyboard, the absences (no Rights, no *Edit…*, no *Hang…* when archived, no
kept-off line when not kept off), and the positions photographs found wrong.
Each new test was watched failing on a re-break of the code it defends. The axe
scan (by hand, `arrt/tools/ux_walk.py`) is clean on the four lists and on a
held, an archived and a not-held work.

**Rollback:** revert the branch's merge; there is no data or contract change.

## 2026-10-28: The browser suite's `open` loads the page again, and `navigate` moves within it

<!-- prawduct: scope=fix-hanging-badge-race -->

**Why:** `test_hanging_reports_back_by_naming_the_wall_rather_than_a_colour` failed once
in #394's CI, and locally about once in twelve runs, with "assert 'on Study' in '▲ No
Player'". It hangs a theme, which lands on Walls, then opens the Theme page again. That
`open` changes only the fragment, so it can return with Walls still painted. Since the
Walls rebuild, Walls cards carry a screen-state badge, and the test's bare `.badge`
read that badge in place of the theme's.

The cause is the shared helper, not that one test. Any `ui.open` to the page already
loaded was a hashchange, so its waits could be met by the screen still painted. A test
that opened a page again to read what the server kept was reading what the client held.

**What changed:** `ui.open` reloads when only the fragment would change, so every open
is a load. The new `ui.navigate` moves within the client and keeps its memory, for the
three Ask tests about a page the curator comes back to, which need that. No product
code changed.

**Tests:** the Theme test failed about once in twelve runs against the old helper, and
0 times in 40 against the new one. The full browser suite passes with the helper
changed.

## 2026-10-27: Walls, rebuilt to the page rules (UI pass, part 1)

<!-- prawduct: scope=ui-pass-walls | release=v0.7.0 -->

**Why:** the owner walked Walls on the newly deployed server and found it jumbled:
no way to add or rename a wall, a scene search that did not say what it searched,
"Drawing from All works, until changed" with nothing to change it beside it, the
wall's Player shown as if it were a fact about the theme, and buttons and links
mixed in one row. A clickable prototype of six pages on the owner's real library
was approved with three changes; `ia-proposal.md` § Rulings (2026-10-27) records
the rulings, and `design-direction.md` § Component Patterns, "How a page reads",
the page rules. This is the first of three plans (#389 and #390 are the others).

**What changed:**
- **A wall can be renamed** (`POST /api/walls/{id}`, `art_display(action='rename_wall')`),
  and a taken name is refused as "Another wall is already called '…'." by add and
  rename alike.
- **Walls** opens with its name, one line of facts and a toolbar (*Add wall…*,
  *Scene…*). Each card: the wall's name and its screen's state as a badge; the work
  on it (a dark screen: the last shown, dimmed, else the next); *Skip* and *Remove…*
  (it was *Not this one again*); *Hanging*, whose theme's name is the picker that
  hangs another; the next three; History and, only when there are some, the works
  it cannot show. Its settings (name, Player and screen, label panels, rotation,
  shapes, mat) are its *Edit…* dialog, which names a screen *HDMI 1* and a label
  panel *the label panel on {Player}* rather than their ports, and the card is
  repainted when it closes; the card names its Player only as a problem.
- **The scene** is assembled in the *Scene…* dialog, whose search says "Search your
  library"; a live one is a line above the cards.
- `core/editing.js` is the dialog shell the next two plans reuse.

**Tests:** about forty browser assertions rewritten, each naming the ruling that
changed it; new tests for the badge, the facts line, the keyboard path, the card's
spacing, renaming, putting a wall on a screen, its labels, the card after the
dialog closes, a dark wall whose next work cannot be read, and a wall added,
assigned and hung through the page whose feed, read with its Player's token,
carries the work hung.

**Not in this:** deleting a wall (#391); Settings › Clients still carries its own
assignment controls until the Players plan (#390).

## 2026-10-27: Arrt without the Player (wave 5, part 2)

<!-- prawduct: scope=wave-5-split | release=v0.7.0 -->

**Why:** Arrt Player now lives in its own repository,
[brookstalley/arrt-player](https://github.com/brookstalley/arrt-player),
extracted with its history and green on its own CI (`build-plan-wave-5-split.md`
chunk 04). This repository becomes Arrt, the server, and stops carrying a copy
of the Player that nothing here builds or deploys (chunk 05).

**What changed:**
- **`arrt-player/` is gone**, and so are the Player's deploy files
  (`deploy/display.service`, the journald bound, `deploy/pi-freeze-2024.txt`),
  its artifacts (the Frame's state, HDMI output, Apple platform, and platform
  and dependency findings), the Pi runbook and the `display.md` learnings. Each
  is in arrt-player, carried at chunk 04; the tree removed here was the
  extracted tip exactly.
- **CI runs three suites:** the governance suite, the server and the contract.
  The display leg, the typesetting job and the display lint step are gone, and
  so are the CI-scope guard's two display tests. `project-state.yaml`'s
  `test_commands` and `tests_dirs` drop the Player's suite.
- **The scans of CI's pytest lines match `pytest` as a whole word.** Both the
  scope guard and the CI-scope guard stopped inside `pytest-cov` or `./pytest`,
  so `uv run --with pytest-cov pytest …` was split at the wrong word and an
  unscoped run could read as scoped. The review of chunk 04 found it in the
  matcher chunk 04 had widened, from the literal `uv run pytest` to anything
  between `uv run` and `pytest`. The CI-scope guard now uses the same matcher.
- **The norm index drops the four rows only the Player's code can hold** (the
  television belongs to whoever is using it; the Player never requires the
  server; the e-paper label's legibility; the Player's only channel), which
  arrt-player's index carries. The mixed rows keep the server's guard, and the
  index says where the Player's halves are.
- **The records say what this repository is.** CLAUDE.md's commands, the
  README, `deploy/README.md` (the server's deployment, with each release's
  server half; the Pi's record is arrt-player's), `.env.example` (the keys the
  server reads), and the live artifacts, which name a Player file as
  `arrt-player:<path>`. `re-architecture.md` closes wave 5, and
  `architecture.md` records the two repositories and the pinned contract.
  History (the change log, archived and released plans, dated rulings) keeps
  the paths of its day.
- **Every file a live record cites now resolves in this tree or names its
  repository** (`tests/preferences/test_citations_resolve.py`, new). A sweep keyed
  on the Player's old directory had missed the departed deploy files and findings
  cited by bare name, among them an instruction to install the moved journald
  drop-in; those citations now read `arrt-player:<path>`. The CI pytest matcher
  also sees a quoted `run:` value, and is shared by both of its scans.
- **Ten of the Player's issues moved to brookstalley/arrt-player** (#16 to #25
  there: #41, #103, #104, #105, #107, #153, #182, #184, #326, #384 here), with the
  labels the transfer dropped restored. The rest stay here.
- **Queued for the operator:** the wall moving onto a clone of arrt-player
  (`operator-verification.md`), which is chunk 06.

**Tests changed in what they assert:**
- *Deleted with the code they guarded, each carried to arrt-player at chunk 04:*
  the display unit's restart policy and stop timeout, and the CI-scope guard's
  display-leg and typesetting-job tests.
- *Strengthened:* the CI scope check's fixture carries `pytest` inside an
  option's value and in quoted `run:` values, each watched failing against the
  matcher before it.
- *New:* the citation guard, watched failing on every record it then fixed.

**Rolling back:** no data changes, and nothing deployed reads this repository's
copy of the Player: the Pi moves to arrt-player at chunk 06. Until it does, its
old checkout keeps the files on disk and must not be pulled. Checking out a
commit before this one restores the tree.
