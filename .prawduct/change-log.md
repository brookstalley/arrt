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

## 2026-10-26: The contract becomes a package, the root clears, and every cross-plane guard holds where it will survive the split (wave 5, part 1; #33)

<!-- prawduct: scope=wave-5-split | release=v0.7.0 -->

**Why:** Wave 5 splits Arrt Player into its own repository
(`re-architecture.md` § Order of work). Before the history can be cut, the
contract both sides test against has to be something a repository outside
this one can depend on, and every guard that read both planes from the root
has to hold in a suite that survives the cut (`build-plan-wave-5-split.md`,
chunks 01 to 03). The owner chose a published package, as a git tag for now.

**What changed:**
- **`contract/` is the `arrt-contract` package** (`player-contract.md`
  § The package): the schemas, fixtures, vectors, routes and timing, the
  rules a schema cannot state (`semantic_errors`), and `player-contract.md`
  itself, at one version (1.0.0). The data stays where the specification
  names it; the wheel carries it. The server's and the Player's suites read
  it through the package, each as an editable dev dependency; the contract
  has its own suite, CI leg and `test_commands` entry.
- **The contract says three things it only implied:** the heartbeat's
  instant key (`instant_key()`), the 60-second heartbeat interval and the
  three-interval stale threshold (`timing.json`), and the label corpus
  (`vectors/label-corpus.json`) that renderers measure against.
- **The root holds no code.** `tv_api_check.py`, `tv_delete.py` and
  `panel_check.py` moved to `arrt-player/tools/` and read the Player's own
  settings (the owner ratified this in place of carrying the 2024
  `config.py`). The Player declares `requests>=2.32`, which `tv_api_check.py`
  imports and the television client already installed, so the Pi's install
  does not change. The 2024 modules, `requirements.txt` and the 2024 systemd
  unit are deleted, and `.env.example` drops the three settings only they read
  (`OPENAI_KEY`, `EPD_TYPE`, `USE_ART_LABEL`). The root project is renamed
  `arrt-governance`. `all.json` stays: the server's seed reads it.
- **#33 is finished:** the broad-except rule (`BLE001`) now holds in every
  project with no per-file exception, because the root's last one went with
  the 2024 modules. It closes when this merges.
- **Each agreement between the planes is held by each side against the
  contract**, in its own suite: the heartbeat key, the timing, the label
  corpus (Arrt against its seed tables, the Player's copy against the
  vector). The plane-isolation guard moved whole into the Player's suite.
  The root's repository-wide scans derive their scope from the projects
  present, and the Player carries its own copies.
- **The server image's test stage installs the contract.** Its suite in the
  image still fails for reasons this work did not cause (#386).

**Tests changed in what they assert:**
- *Moved, unchanged in what they assert:* the contract's schema, fixture,
  vector and label-rule tests (`contract/tests/`), and the plane-isolation
  guard (`arrt-player/tests/test_plane_isolation.py`).
- *Restated against the contract:* the heartbeat-key, staleness and
  label-corpus guards, each split into a server half and a Player half that
  hold their own constant to the package instead of reading the other
  plane's source. Each half was watched failing against a re-break.
- *Deleted with the code they tested:* the 2024 `config.py` tests and the
  2024 dezoomify argv test; the two tests of the deleted 2024 unit (the live
  units' tests assert the same properties); and ten `tv_delete` tests of
  `remove_from_tv`, `forgettable_ids` and `describe_removal`, whose only
  caller was the deleted `tvart.py`. Two of those asserted that a refusal's
  message names its cause; they were rewritten against
  `delete_list_confirmed`, which carries that message.

**Rolling back:** no data changes. A checkout before this one reads the
contract from `contract/` by path, so rolling back is checking out the older
commit; nothing a running wall or server stores is touched.

## 2026-10-26: Scenes — a work per wall, shown together (wave 4f)

<!-- prawduct: scope=wave-4f-scenes | release=v0.7.0 -->

**Why:** The owner's MVP for wave 4f: "the HDMI display on rpi and samsung
frame transitioning at the same time to related works that I pick manually."
The Player has honoured a feed's `scene` and `staging` since wave 4c; nothing
on the server wrote them (`build-plan-wave-4f-scenes.md`).

**What changed:**
- **Scenes are Programming state.** Two tables, `scenes` and `scene_pins`;
  a draft, live or ended scene, a preview or a hold. Keep is deferred until
  Programming has something to keep a scene into.
- **Every feed carries the control layer.** One function now spells and
  writes a wall's feed, and asks the store for the wall's live scene and the
  draft's staged works on every write, so no publish path can drop a live
  scene. A pinned work archived or kept off every wall leaves that wall's
  feed at once, and Walls says why the wall shows its schedule instead; it
  comes back when the work is restored or allowed again.
- **Walls has a Scene section** above the cards: pick a work per wall (each
  pick stages it), *Apply* as a 5, 20 or 60 minute preview or *Hold*, both
  asked first naming each wall and its work; once live, whether each wall has
  reached it, from its heartbeat, and *Release*. A card says when a scene is
  showing on it.
- **`/api/scenes`** routes, and seven `art_theme` actions for agents. A
  preview lasts at most a day (1,440 minutes); longer is refused (400), and
  a hold is how a scene stays longer.
- **History** records a scene applied and ended on each wall (released,
  replaced, or its time run out).

**End to end, on this Mac (2026-10-26).** A server booted from this branch
with two walls, each hanging a theme, and Arrt Player's real Frame and screen
wall loops run beside their real pulls against it, with the suite's Frame
double and screen double in place of the television and the HDMI output.
Pinning a work to each wall had the Frame double holding the staged upload
within a second, while both walls went on showing their schedules. Applying
as a hold switched both walls within the same 50 ms poll, and both
heartbeats reported the scene. Release put both back on the schedule works
they showed before. A one-minute preview, applied and then the server
stopped, ended on both walls 60.1 s after Apply, with the server down. The
Frame double uploads at once, so this shows the upload happens before Apply,
not how long a real one takes; the walk at the wall times that.

**Rolling back:** a build before this one reads each History row through
`EventKind(...)` and fails on the new `scene.applied` and `scene.ended`
rows, so History would not load once any scene has been applied. Before
rolling back, delete them: `DELETE FROM history_events WHERE kind IN
('scene.applied', 'scene.ended')`. Release any live scene first, or a held
scene stays in a wall's feed until the older server next rewrites that
wall. The `scenes` and `scene_pins` tables are left behind unread.

**Tests changed in what they assert:** the Walls nesting test lists the
Scene's `h2` among the page's headings, beside one per wall; its claims of
one `h2` per wall and panels a rank below are unchanged.

## 2026-10-16: The brand goes home, held works select everywhere, and the Work page shows and chooses the mat (#317, #346, #91)

<!-- prawduct: scope=ui-mat-selection-labels | release=v0.6.0 -->

**Why:** A backlog triage of the UI items, at the owner's request. The mat is
the most visible thing on a wall, and since wave 4g the Work page showed the
master bare, while only an agent could change a mat's colour. The owner also
asked for the product's name to lead home, as it does in every *arr app.

**What changed:**
- **The brand.** "Arrt" in the top bar is a link to Artworks, its address read
  from the route table. Pressed on Artworks itself it arrives afresh and clears
  a filter.
- **Held works select on Search and Topic** (#317). Their held rows and cards
  get Add to theme, New theme… and Archive, as Artworks has. A topic makes its
  selection even when Wikidata cannot be asked.
- **The Work page shows the work in its mat** (#346). New `core/mat.js` ports
  the Player's layout rule and is held to every vector in
  `contract/vectors/mat-geometry.json`.
- **The curator chooses the mat** (#91, without its AI picker, which is #379).
  The *Mat* line under the picture opens on the presets `#272727` (replacing
  `#222222`, which is under the L* 15 floor) and `#6b6b6b`, and on *From the
  picture* when it would change the mat. Each is shown on the picture before
  *Use this mat* records it. `GET`/`POST /api/works/{id}/mat` are new;
  `art_catalogue set_mat_color` takes `preset`. A curator's re-derive is
  recorded as the new `MatMethod.DERIVED`.
- **Dropped from #91 by the owner:** the derived colour as the default mat
  (the vision model stays first), and with it removing `NO_MAT_COLOR`.
- **#267 closed.** It had shipped in v0.5.0 and its issue was left open.

**Tests changed in what they assert, each with its reason beside it:** a held
Search row now has a tick, and a held work is still never offered a Get; the
picture leads what a Search row draws, its hidden tick aside; the Work page's
width check measures the mat, which is what a wall shows; the shell test
reads the brand as a link; and History's age test asserts a recent age in
seconds under a minute rather than at most three, because a loaded parallel
browser run opened the page more than three seconds after the event.

**Rolling back:** a build before this one reads `mat_colors.method` through
`MatMethod(...)` and fails on a `derived` row. Before rolling back, rewrite
those rows to the older value for the same derivation:
`UPDATE mat_colors SET method = 'dominant_color_fallback' WHERE method = 'derived'`.

## 2026-10-15: Walls shows the last-shown work and the next three (#354)

<!-- prawduct: scope=ux-second-walk | release=v0.5.0 -->

**Why:** In the second UX walk, a wall's card on Walls listed ports and state
but never showed the art. The owner ruled on 2026-10-14 that it should show the
work the wall showed last, which waited on #316's log of showings.

**What changed:**
- **Walls.** With no work of ours on the screen, the card leads with its state,
  said once. Then comes the work the wall showed last, large, from the log of
  showings. The next three from the schedule follow, small.
- Ports show only under `?debug`. *Change* is shaped like the page's other
  actions, and *History* is a link.
- **Tests.** The way back's topic test now waits on the topic's title, because
  the previous page already satisfied what it waited on (#371). The *Last shown*
  rail fixture spreads its showings so that every period counts differently.

## 2026-10-15: What each wall has shown (#316)

<!-- prawduct: scope=shown-record | release=v0.5.0 -->

**Why:** Nothing recorded what a wall had actually shown. So Walls couldn't show
the last work and Artworks couldn't find works no wall had shown. The owner chose
a log over a first/last summary, and fixed periods for *Not shown since*, on
2026-10-15.

**What changed:**
- **A log of showings.** A new `showings` table in Programming, with no foreign
  keys. It holds one row per stretch of one work on one wall, written from each
  heartbeat's display state against the wall's published feed. The write is a
  bulkhead: whatever fails, the heartbeat is still answered and the horizon
  still rolls.
- **Walls' read.** `GET /api/walls` and `art_display(action='walls')` carry
  `last_shown` and `upcoming` (the next three slots of the published schedule).
  So does every write that answers with a wall.
- **Artworks' *Last shown* facet.** It offers never, or not in the last month,
  3 months or a year, counted like the other facets. The narrowing moved to
  `services/works_filter.py`, which `art_catalogue(action='list')` now calls
  too, so the tool surface gains the `fit` and `not_on_wall` filters it lacked.

## 2026-10-14: Each screen says one thing once (#359)

<!-- prawduct: scope=ux-second-walk | release=v0.5.0 -->

**Why:** In the second UX walk (findings 39 and 44), copy explained the system
rather than the art:
- Status said one fact three times.
- Topic pages were titled "Wikidata Q7049".
- An unmatched artist was told so three times, with a QID.
- A Get's cost took four rows.
- History listed forty near-identical rows.
- The rail drew a heading over one dead option.

**What changed:**
- **Status.** A wall's panel says "Last heard from …" once. The server's
  sentence (the display plane, the file path) shows only under `?debug`. The
  page summary shows only over more than one wall.
- **Topic.** "Topic" until a name arrives, never the bare item, and the tab
  follows the name. The link reads "On Wikidata".
- **Artist.** An unmatched artist is told so once, by the server's note. Where
  people are offered, their list asks "Is it one of these?". The identity line
  there shows "Wikidata:" and *Edit*. A candidate's item is only the link's
  target.
- **Get.** One *Cost* row; the family total joins it only where it differs,
  and is kept when the Get recorded nothing of its own. The estimate and the
  lookups show only while the Get runs.
- **History.** Three or more consecutive verdicts of one kind from one Get are
  one row, with the works behind *Which works*.
- **Artworks' rail.** A group whose every option counts zero is left out
  while nothing narrows the counts.
- **Clients and Taste.** Their leads are cut.
- **Kept, with reasons in the plan:** Taste's list of ways (pinned), Wanted's
  empty state (pinned), *Clients* as the page's name.
- **Open for the owner:** one set of verbs for a taste judgment.
- **Tests changed in meaning:** re-pointed to the new wording, each keeping
  its check.
  - In `test_the_run_view.py`, the cost rows became one.
  - `test_fact_lists_on_a_phone.py` measures a running Get, and its floor of
    facts is 3.
  - `test_topics.py` and `test_the_artist_page.py`: no bare item. The
    candidates test now checks link targets.
  - `test_the_debug_view.py` waits on the wall's panel.
  - `test_names_that_link.py`'s scroll allows a sub-pixel.

## 2026-10-14: The Theme page shows its art, at two boxes a row (#352)

<!-- prawduct: scope=ux-second-walk | release=v0.5.0 -->

**Why:** In the second UX walk (finding 31), the Theme page was 61 rows of five
acts: 305 boxes, no pictures, no links, an empty Size column. *Add a work* on
*All works* offered only works already in it, and on a phone the acts were
off-screen.

**What changed:**
- **One Position field a row** replaces ↑, ↓, *Move to top*, *Move to bottom*
  and "#".
  - It commits once, on Enter or leaving the field. It never commits on
    `change`, which Chromium fires at every arrow step.
  - It commits once per field, because removing a focused field fires
    `blur`.
  - A place past either end is clamped, and a move to where the work already
    is sends nothing.
  - The keyboard stays on the moved work's new field.
  - A refused move puts the field back.
- **Each member row** leads with its picture, or `noPicture`, and links its
  title to Work and its artist to Artist.
- **The Size column** appears only when some work has something to say in it.
- **The table is stacked into cards on a phone.**
- ***Add a work*** offers only works not in the theme, rebuilt with every
  change of membership. With none left, it says so, and its row stays hidden
  until the members have arrived.
- **Tests changed:** `test_the_theme_screen.py` and `test_the_themes_index.py`
  drive the Position field where they drove the buttons. Each test's intent
  is kept: a move takes effect and survives a reload, a move reaches either
  end, moves work from the keyboard, the ends send no non-move. The dated
  docstrings say what changed. Their title helpers read
  `td[data-label='Title']`.

## 2026-10-14: Pictures where a person decides (#358)

<!-- prawduct: scope=ux-second-walk | release=v0.5.0 -->

**Why:** In the second UX walk (findings 37, 38 and 34):
- Works whose master the museum refuses read as the server's exception text,
  in three wordings across four screens, and the Artists index asked for
  thumbnails the server refused.
- The search dropdown pictured Wikidata's works but not the library's own.
- Result pictures sat small inside the state's badge.
- The Work page's picture could not be enlarged.

**What changed:**
- **`noPicture` (`core/badges.js`).** One placeholder, "No picture", for a
  held work with no master, on Artworks, Artists, a topic and the Work page.
  The server's note shows only under `?debug`.
- **An artist is pictured only by a work holding a master.**
  `held_artists` in `persistence/sqlite.py` now does this, and
  `pictured_artwork_id` is null when no such work exists. It fell back to a
  work with no image, whose thumbnail answers 400. The model, the store
  protocol, `api-contract.md` and the IA's Artists row say so.
- **Search.** The dropdown and the results page lead each work's row with
  its picture, out of the badge (`statePicture`, `heldPicture`), at 2.5rem
  and 4.5rem. The library's own works are pictured when they hold a master.
- **Work page.** The picture is a button that opens it large in
  `core/enlarge.js`'s dialog.
- **Tests changed in meaning:**
  - `test_artist_surface.py`'s ordering test gives both its works a master,
    and a new test pins null.
  - `test_asking.py`'s and `test_the_artist_page.py`'s held-artist picture
    tests give their work a master.
  - `test_the_work_page.py`'s "the picture is the largest thing" passes over
    the picture's own button.

## 2026-10-14: Shared rules that hold every page, and the pages at a phone's width (#360, #357)

<!-- prawduct: scope=ux-second-walk | release=v0.5.0 -->

**Why:** In the second UX walk (findings 36, 40, 41 and 45), rows, gaps and
type drifted in a few shared rules, not page by page. At 390 px the status was
cut to "● W…", the open drawer covered Menu, and Clients' tables broke output
names.

**What changed:**
- **`app.css` shared rules:**
  - Rows align on the baseline, and labelled fields on their boxes.
  - One gap under a page's name.
  - Tile titles take no panel heading margin, and a tile's badge follows its
    label.
  - Badges are set in the UI face, and quiet acts in ink in both schemes.
  - Prose is held to 70ch.
  - A table's first column sits on the page edge.
  - An act in a line of words is spaced from it, and what follows a row is a
    step below it.
  - A sub-heading after content stands clear of it.
  - The budget line sits on the nav's grid.
- **`core/badges.js` `table()`:** marks a column of figures `.num` (right
  aligned, tabular), decided from its values. Status's sources table marks
  its own.
- **Phone:**
  - The status shows "Well" or "Unwell" and keeps the sentence for a screen
    reader.
  - Menu sits above the open drawer.
  - The facet rail fades at its edge.
  - Clients' outputs and labels are cards.
  - Artist posters reserve their own shape.
- **Ask:** *Start over* is offered once something has been said.
- **Queue:** the fetching section says its counts before its parts.
- **Rules recorded:** `design-direction.md` § Spacing & Layout and § Component
  Patterns.
- **Kept, with reasons in the plan:** E22, the ⚙ glyph, L22 (ten themes on a
  screen) and the Artworks toolbar. E23 moves to chunk 06.
- **Tests changed:** `test_the_status_sources_table.py` reads a column's
  `col-` class rather than its whole class string, which now also carries
  `num`.

## 2026-10-14: The way back names where it goes, a dead address says so, and walls, clients and topics link (#356, #361, #362)

<!-- prawduct: scope=ux-second-walk | release=v0.5.0 -->

**Why:** In the second UX walk (findings 35, 42, 43 and 34), the back link on a
detail page went to the sidebar index rather than to the page it was opened
from. An address naming nothing left the previous page painted, or waited for
ever on a fresh load. Walls, clients and a work's topics were named on six
screens and linked from none.

**What changed:**
- **The way back.** Work, Artist, Topic, one Theme and Search results are each
  a place to return to (`returnLabel`, `returnFor` in `app.js`). Search results
  carry their query (`returnParam`). The back link names its opener from the
  name that page gave itself this visit (`setTitle`), or its kind when reached
  from a bookmark. A way back records no opener of its own.
- **An address naming nothing** (a work, artist, topic, theme, Get or review)
  is one not-found page (`core/router.js`, `notFound`). A refusal (400, the
  server's one refusal status) or a 404 on a one-thing read reaches it. A 5xx
  keeps the banner, and on arrival the view says only that the page could not
  be shown. A failed repaint keeps the page that was showing. A gone Get stops
  its watch at the first refusal.
- **Names that link.** A wall is addressed `#walls?wall=<id>` and a client
  `#clients?client=<id>`, and the page brings that card to the reader
  (`data-arrive`). They are linked from Work, Theme, History, Clients and
  Status, and from Walls for clients (`core/places.js`). A facet with a
  `value_qid` links to its Topic page.
- **Found and fixed:** a search pressed while the client started submitted the
  form natively. The top bar now installs before the start-up read.
  `tests/browser` `ui.open` waited on the served placeholder, so it returned
  before the client ran; it now waits for `html[data-started]`.
- **Tests changed in meaning:**
  - `test_the_run_view.py`'s two give-up tests held a 400. They now hold a
    502, because a refusal now ends the watch at once with the not-found page,
    which a new test pins.
  - The not-found link selectors in `test_the_theme_screen.py` and
    `test_topics.py` follow the link's new name, the index's sidebar label.
- Filed: #376, a feed test that passes only within one wall-clock second.
