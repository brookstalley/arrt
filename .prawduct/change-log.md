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


<!-- Older entries live in .prawduct/change-log-archive/YYYY-MM.md, moved there verbatim by `prawduct-hook archive-change-log`. -->

## 2026-10-08: The contract for displays and label outputs

<!-- prawduct: scope=displays-and-label-outputs -->

**Why:** Chunk 01 of `build-plan-displays-and-label-outputs.md` (#188): the contract
both the server and the Player build to before either changes. The plan's
high-impact assumption, that a Frame names itself, was checked first.

**What:**
- `client-heartbeat.v1`: a display output may carry `identity`, and a new
  optional `label_outputs` list (`epaper`) reports panels. The server refuses a
  malformed one and two label outputs of one name, as it does for outputs.
- `client.v1`: each wall may name its `display`, and a new optional `labels`
  list maps this client's label outputs to walls. The Player reads both and
  refuses the document whole when either is malformed, as it does for walls.
- `label.v1` (new): the label document, carrying the wall's display state and
  the label text, never a layout.
- `contract/vectors/label-rule.json` (new): the label rule as conformance
  vectors, the first behaviour vectors. `tests/preferences/test_label_rule.py`
  states the rule once, runs every vector against it, and checks that the
  vectors cover the table and both sides of the 30-minute hold. Mutating the
  reference rule fails it; one inert clamp was removed rather than defended.
- Fixtures for each new shape, indexed.
- `player-contract.md` § Transport and § Versioning describe the label route,
  display identity, label outputs and the rule.
- `samsung-tv-state-findings.md` § The set's identity: the Frame's `/api/v2/`
  carries one uuid as `id`, `duid` and `udn` on both ports; 8002 answers over
  TLS in 0.14 s, from standby. Not recorded: the value, the address, the MAC.
- The plan: the identity assumption marked verified in part; three decisions
  recorded; the route's entry in `contract/routes.json` moved to Chunk 03,
  because the server's route test holds mounted and named routes equal.
- `build-plan-display-state.md` and `build-plan-walls-work-and-trust.md` no
  longer claim their merged branches: each has only the operator's walk left.

## 2026-10-08: Plan displays and label outputs; the Apple platform findings

<!-- prawduct: scope=displays-and-label-outputs -->

**Why:** #188 is next in `labels-and-surfaces.md`'s order, and the owner widened it
on 2026-10-08 (`feeds-and-players.md` rulings 1 and 9) so displays become server
records too. The platform facts in `feeds-and-players.md` § Platforms were the
builder's recollection until a spike measured or sourced them.

**What:** Planning and findings; no code.
- `build-plan-displays-and-label-outputs.md` (new): seven chunks. A contract with
  display identity, label outputs, a label document and the label rule as
  conformance vectors. Display and LabelOutput records with a migration that keeps
  every wall on its screen. The label route and the duplicate-display fault. The
  interface, held until `feature/lists-settings-and-scale` merges. The Player's
  reports. A label renderer per label output, with the Frame loop no longer
  drawing the panel. The operator on the wall, after #181. Four observations from
  the display-state review are carried in.
- `apple-platform-findings.md` (new): what a macOS screensaver and a tvOS app can
  do as Players, each fact labelled measured, sourced or unverified.
- `feeds-and-players.md` § Platforms corrected from it: a backgrounded tvOS app
  goes silent rather than reporting `in_use`; tvOS has no local-network permission
  and the Frame's certificate is the obstacle; the macOS saver host must be torn
  down on `willstop`, and whether a saver can reach the LAN is its largest risk;
  `UIScreen` gives no physical size, so the relative mat width applies on Apple
  TV; CoreText can do the label's measuring; and unverified facts are verified
  on hardware before each platform's plan is written.
- `labels-and-surfaces.md` § What changes, in order: #181 now blocks only the
  plan's last chunk, the operator's.
- `apple-platform-findings.md` registered in `project-state.yaml`.

## 2026-10-08: Feeds and players: one Player core for private walls and public channels

<!-- prawduct: scope=feeds-and-players -->

**Why:** The owner set the Player's next shape: Players on several platforms (the Pi,
Apple TV, Mac and Windows screensavers), a display controller kept apart from the
wall it shows, the Player in its own repository, and logic and documentation
reused across platforms. A second use case came with it: public channels of
public-domain art that any number of Apple TV apps read, with the server neither
knowing nor caring how many. Major 2 is still a draft, so this is the cheapest
moment to reshape it.

**What:** Design only; no code.
- `feeds-and-players.md` (new): the owner's direction in their words, and ten
  rulings, each marked with whose proposal it was. Major 2 becomes a **feed** (schedule, works,
  default presentation settings) plus an optional **control** layer; each major at
  its own URL; displays as server records with one client each, configured on the
  host and never discovered; rendering always on the client; presentation settings
  in three layers (feed, wall, device), including which facts about a work show;
  the feed carries only the mat colour and the client decides mode and width;
  public channels published to static hosting, public-domain only, 4K at most,
  listed in a published index; reuse through a Player spec and conformance
  vectors, with no shared native core until a stated trigger.
- Dated pointers in `re-architecture.md`, `player-contract.md` (§ Major 2 and
  § The cutover), `data-model.md` constraint 13 (reopened for public channels
  only) and `nonfunctional-requirements.md` § The mat is geometric.
- Registered in `project-state.yaml`'s artifact manifest.

## 2026-10-08: Labels as outputs, and each wall reports its display state

<!-- prawduct: scope=display-state -->

**Why:** The owner, declining an interim fix for the Pi's e-ink panel: labels are
their own outputs, mappable to any wall on any device, kept in sync; blank while
somebody watches a movie on the Frame; and the abstractions must stay clean for a
caption composited into the image later. Only a wall's controller knows what its
screen is doing, so labels need that report before they can be split from walls.

**What:**
- `labels-and-surfaces.md` (new): the owner's rulings of 2026-10-08 (ruling 1 revised
  the same day from schedule-first to report-first), five nouns (wall, client, output,
  wall controller, label renderer), the display states and what a label shows in each,
  and the rules that keep a caption-in-image possible. Reverses "one process per wall
  drives both picture and label" in `re-architecture.md` and `clients.md`.
- **Heartbeat minor 3** carries `display_state {state, work_id, since}`: `showing_art`,
  `in_use`, `dark`, `no_screen`, `unreachable`; a work only beside `showing_art`.
- **The Frame controller** reports it on change: a remote-control change resolved to a
  work through the bindings; `in_use` vs `dark` from one read-only PowerState GET taken
  only after `get_artmode` says off (never a key press). Its panel blanks for `in_use`
  and `dark`, and 30 minutes into `unreachable` (the owner's number).
- **The HDMI controller** reports `showing_art`, `dark` (no screen detected) and
  `no_screen` (output gone).
- **The server** keeps each wall's state, adds `unassigned` and `silent`, refuses a
  malformed `display_state` but reads a state name it does not know as `unreachable`
  (so a Player can upgrade before the server), and carries it on `/api/walls` and
  `art_display`; **Walls**
  leads with it ("Somebody is using the screen", "Its screen is off", "Not heard from
  since …").

**Tests:** contract fixtures on both sides of the work-id rule; `postarr/tests/test_display_state.py`
drives the TV double through each transition (remote change, TV and back, standby, a failed
PowerState read, unreachable at 29 and 31 minutes); server unit and browser tests seed
real heartbeats for each state, a pre-minor-3 one and a stale one;
`test_staleness_threshold.py` ties the Player, server and client thresholds together.

**Deploy:** the server and the Pi's Player both, in either order: a server reads a
state a later Player adds as `unreachable`. A minor-2 Player keeps working: the
server reads its `current_work_id` as `showing_art`. Rolling back either side alone is
safe; nothing new is stored beyond the heartbeat file.

**Not done:** chunk 05, the owner's check on the wall. The PowerState read goes to the
set's TLS port (8002), unmeasured on the set until then. Label outputs and their mapping
are #188, next.

## 2026-10-08: Walls, Work, and signals you can trust

<!-- prawduct: scope=walls-work-and-trust -->

**Why:** The high-priority findings of `ux-review-2026-10.md`, built as one plan and one
PR at the owner's request ("minimize ceremony"). The two weekly scenarios failed: one
held work could not be hung (S1), and Walls could not say what was on the wall (S6, S8).
The review also found navigation by script buttons, signals that contradicted
themselves, a product voice that was the code's rather than the curator's, and art
shown as the wall render.

**What:**
- **Walls and Work** (#272, #295, #162): each wall card leads with the work its
  heartbeat names, with Skip, *Not this one again* (this theme, or every wall) and
  Change; a client report older than three heartbeats is said as unknown. The Work
  page's state strip lists the walls and themes a work is on, with Hang…; Archive is
  secondary; museum `<i>`/`<b>` render through an allow-listed tokeniser.
- **Programming**: a wall can hang a selection (a theme with a hidden flag, deleted once
  no wall hangs it, refused as a destination, default, add target or rename target); a
  work can be kept off every wall (`work_exclusions`) and allowed again;
  `GET /api/works/{id}/placements`.
- **History is events** (#293): a Library-side `history_events` log of Gets, verdicts,
  archives, restores, hangs and exclusions, from now on; History and each wall read it.
- **Navigation is a link** (#273): every list opens its items by `<a href>`; scroll,
  focus and Back keep the place; each screen has its own title and h1.
- **Failures beside the control** (#277), through one helper.
- **Search and review trust** (#275, #276, #89): registry rows fold into held twins;
  works waiting for review are marked and a Get skips them, and skips held works matched
  by title and artist; review candidates carry confirmed / unconfirmed / unknown
  (`source_found` from the model); a verdict is held 5 s with Undo.
- **Spend** (#290): the approval gate is retired (ruling 3); `GET /api/budget` and the
  sidebar's "left this month"; a cost tier on every spending action.
- **One vocabulary** (#291, #292, #267, #283): Get everywhere (`#get/`, `#run` aliased),
  Wanted always shown, bare-noun labels, one date formatter, costs to the cent, museum
  names.
- **Tiles show the art** (#278, ruling 7), with a 1920 px `/wall-preview` for the Work
  page; **keyboard and phone** (#280, #279).
- Retired the parked round-2 UI plan; carried its operator-ruled § Boundaries amendment.

**Tests:** guards new with this branch include `test_navigation_is_a_link.py`,
`test_labels_are_bare.py`, `test_no_machine_dates.py`, `test_one_date_formatter.py`,
`test_stylesheet_is_whole.py`, `test_staleness_threshold.py`, and browser suites for
Walls, the Work page, History, review trust, spend, tiles, keyboard and phone (a
sideways-scroll check over every route at 390 px). Each new test was watched failing
against the unfixed code. Existing tests changed deliberately are named in their
commits; none was weakened.

**Deploy and roll back:** the catalogue gains `history_events`, `work_exclusions`,
`themes.is_hidden` and `candidate_works.source_confirmed`, added at startup; tiles and
wall previews cache under `thumbs/tiles/` and `thumbs/wall-previews/`, and an old
thumbnail row regenerates. `MONTHLY_BUDGET_USD` is optional (only for a key with no
provider limit). **Rolling back to an older image is not clean:** an older build reads
every hidden selection as an ordinary theme, and puts back on the walls every work kept
off with *Not this one again from every wall*. Restore the catalogue backup taken
before this deploy alongside the older image, rather than the image alone.

**Not done:** the live walk of S1, S6 and S8 on the real wall (chunk 13), owned by the
operator after deploy. Pass 1 re-run on a synthetic 2,000-work library found no screen
reached only by a button and no dead end.

## 2026-10-07: Walls says "Shown by" only when a screen is there

<!-- prawduct: scope=wall-screen-state -->

**Why:** #274, finding 6 of the October UX review. With the TV off, Clients said both
outputs were "not connected", Walls said the wall was "Shown on hdmi-a-1", and the top bar
said "Well". Measured on the wall's Pi with the owner confirming the set was off: the
kernel reported the connector `disconnected`, as it does when a TV is off or unplugged. So
Clients was right. Walls was claiming display from the *assignment* alone. The owner
ruled that "Well" means healthy, not that the TV is on, so the top bar is unchanged.

**What:** `core/outputs.js` (new) holds one state per output, read from the client's
last report: detected, not detected, not reported, unreadable, or not listed. It also
holds the words for each. Walls keeps each client's report from the listing it was
already fetching and says "Shown by" only for a screen detected. Otherwise it says
"Assigned to…" with "no screen is detected (off or unplugged)", or which of the three
reasons leaves the screen unknown. Clients' column becomes *Screen*
("● detected" / "○ none detected (off or unplugged)") beside *Size*, and the output
picker says "screen detected" / "no screen detected". Clients' own lines about a wall
say *assigned*, not *shown*: the "Walls assigned to it" heading, "has no wall assigned
yet", "Every wall is already assigned to", the assign and unassign messages, the wall and
output pickers, and the rotate and remove confirmations. Otherwise the same
claim would have come back one screen over. `information-architecture.md`'s Walls and
Clients rows describe the new lines.

**Tests:** `tests/browser/test_the_walls.py`:
- detected, with a second wall on the same client's other output, so a lookup by
  client rather than by output reads wrong for one of them;
- not detected;
- each unknown reason, each asserting "Shown" absent;
- the listing down.

`test_the_clients.py`: the column's words, its headers, that "connected" no longer
appears, and the assignment lines' new wording. The two rewritten assertions keep their tests' claims: an assigned wall with a
screen detected still reads "Shown by", and the listing-down test still names the
output. Watched to fail before the fix, and two hand mutations of `screenState` (always
detected; no not-listed case) each turned one test red.

**Not changed:**
- **How old the report is.** A client that died after reporting `connected: true` still
  reads as shown. Choosing a threshold is a requirements question of its own, filed as
  #295.
- **The Frame output.** It is reported connected because it is configured; whether the
  TV answers is the wall heartbeat's `television_reachable`.
- **A kernel `unknown` status.** The Player reports it as `connected: false`, so it reads
  "none detected". The Player's docstring chooses that on purpose ("a screen this client
  cannot confirm is not one it should claim"), and the contract's `connected` is a
  boolean with no third value.

**Measured both ways on the wall's Pi:** `card1-HDMI-A-1` read `disconnected` at
15:48 and 16:19 local with the TV off, and `connected` at 16:21 after the owner turned
it on. So "Shown by" rests on a signal that follows the set.

## 2026-10-07: the UX walkthrough, as a practice and a harness

<!-- prawduct: scope=ux-walkthrough -->

**Why:** the owner, 2026-10-07: IA/UX/UI is the product's weakest point, and every
guard the browser client has asks whether it matches its documents, never whether it
is good to use. They asked for the method to be written down "so we don't re-derive
later", and then run.

**What:** `docs/ux-walkthrough.md`, the four passes (inventory, scenarios, critique by
independent lens, people) and how their findings are ranked and routed; a pointer to
it from `CLAUDE.md`. `arrt/tools/ux_walk.py`, Pass 1: it reads the declared screens
from `app.js`'s `ROUTES`, crawls the reachable ones from the home page by links
and by clicking up to 30 buttons a page (`--clicks-per-page`; 0 follows links only),
because the client navigates by buttons that call the router; photographs each at phone and desktop width in light and dark, records headings,
controls and links, runs axe-core per photograph, and writes `inventory.json` and a
contact sheet. It refuses every request but `GET`/`HEAD` in the browser, so a clicked Accept,
Rename or Unassign never lands, but check the server's state after a run against
the real library; `--synthetic N` boots a throwaway server over the suite's large corpus.
Output goes to the gitignored `.ux-walk/`.

**Tests:** `tests/unit/test_ux_walk_parsing.py` (the route table and address
grammar); `tests/browser/test_the_ux_walk.py` (a write from the page refused and
absent from the server afterwards, a read let through, every declared screen
photographed or named as never visited, the skip link not mistaken for a screen, a
screen reached only by address marked so, one a button opens found and marked as
reached by script, `--clicks-per-page 0` following links only, a scan's clean,
violations and not-run kept as three states, a screen that never paints recorded
blank rather than aborting the walk). The guard and the anchor skip were each broken by
hand and watched to fail, as were the synthetic boot's cleanup and the axe-core
pin. The browser tests are deselected by default, so they are not in the
recorded suite run; `uv run --group browser pytest tests/browser/test_the_ux_walk.py
-m browser -n0` ran them, 8 passed. `tests/integration/test_ux_walk_synthetic.py`
boots `--synthetic` in the default suite.

**The first run** is `.prawduct/artifacts/ux-review-2026-10.md`: 30 ranked findings
from Pass 1 on the real library and a synthetic one, Pass 2's 13 scenarios, and five
independent lenses, routed to 18 new backlog items (#272–#289), comments on #131,
#252 and #265, and five decisions put to the owner. Pass 4 is the owner's. The
practice doc gained the reviewer brief and two rules the run taught; `design-direction.md`
lost a notice that its palettes were not yet in the stylesheet, which they had been
for weeks.

**The owner's rulings on the review**, the same day (`ia-proposal.md` § Rulings
(2026-10-07)): the ruled Walls and Work pages are next (#272); a new norm,
*navigation is a link, an act is a button*, in `information-architecture.md`
§ Direction, in-transition (#273); spend shown as a monthly budget with cost tiers
and no approval gate (#290), reversing the 2026-08-04 decision never to show the
remaining balance, recorded in `nonfunctional-requirements.md` and
`observability-strategy.md`; *Get* everywhere (#291); Wanted always in the sidebar
(#292); History as events (#293). The proposal's claim that walls already keep a
history is corrected: the schema overwrites each wall's hang.

## 2026-10-07: the Rijksmuseum as a built-in source, through its Linked Art records, its search and IIIF

<!-- prawduct: scope=rijksmuseum-source -->

**Why:** arrt#226, asked for by the owner on 2026-10-07, the last of the Linked Art
tier. The museum holds the largest open volume measured, almost none of it reachable
through Wikidata (`linked-art-findings.md` § The Rijksmuseum). The robots.txt
ruling it waited on was made the same day.

**What:** a built-in `rijksmuseum` plugin (`library/sources/rijksmuseum.py`). The
finder reads the item's `id.rijksmuseum.nl` records (P13234) and reports each under
the URL as the item spells it. When the item names none the museum knows, or the work
has no item, it searches the collection by title and maker among objects with an
image. If an accented maker finds nothing, it asks once more without the accents,
because the museum folds them for some makers and not others. A work with no maker
is not searched for. The image is three records away (VisualItem, DigitalObject,
access point on `iiif.micr.io`), and its rights are the VisualItem's (Public Domain
Mark, `InC`). In-copyright works the museum marks not downloadable are found like
any other. The maker is the first part of the production naming one. An
attribution ("attributed to …", "(possibly)") is kept, and evidence ("(signed by
artist)", "(mentioned on object)") is dropped. The image service declares 17.55 MP,
so most originals are tiled under `TILE_MAX_PIXELS`, and the rest are fetched in
one request. It reads no web page. The built-in enumerations, the plugin guide's
examples table and the security model name it. A mutation sweep of 46 mutations left
4 survivors. One was an inert check (the access point's shape already pins the
image host), which was deleted. The other three got tests. The live check
(`test_rijksmuseum_shapes_are_still_real.py`) passed 8 of 8 on 2026-10-07.

## 2026-10-07: the Getty as a built-in source, through its SPARQL endpoint, Linked Art records and IIIF

<!-- prawduct: scope=getty-source -->

**Why:** arrt#230, asked for by the owner on 2026-10-07 after Yale. Measured the
same day (`linked-art-findings.md` § Getty): only 30 Wikidata items with a Getty
ID lack an image, while the museum holds 124,301 objects with images. So the
plugin searches as well as following the item.

**What:** a built-in `getty` plugin (`library/sources/getty.py`). The finder maps
the slugs of the item's Getty pages (P2582) to Linked Art records in one query to
the museum's SPARQL endpoint, and reports each under the page as the item spells
it. When the item names none the Getty knows, or the work has no item, it asks
for the maker by name and then for that maker's objects whose titles hold the
title's words. A work with no maker is not searched for, because the endpoint has
no text index and a scan takes 11–14 s. Title and maker come from the record,
since the manifest drops non-ASCII letters. The title is the record's title equal
to the one asked, else Getty's preferred one. The maker keeps Getty's attribution
("Workshop of", "and workshop"). The image is the v3 manifest's first canvas, and
rights are the manifest's per-object `rights` (CC0, `InC`, `InC-RUU`). Works the
Getty keeps at 600 px are found as placeholders. The reader answers one request for
originals up to the service's declared 30,000 px. It reads no web page. The
built-in enumerations, the plugin guide's examples table and the security model
name it. `getty` sorts third in the default order, ahead of `met`. That changes
only which image wins a tie, since every finder is asked at once. A hand mutation sweep of 48 mutations left 4 survivors: one inert check
was deleted, and the other three got tests. The live check
(`test_getty_shapes_are_still_real.py`) passed 7 of 7 on 2026-10-07.

## 2026-10-07: IIIF parsers in the plugin interface (1.3), and Yale through its manifests as a built-in source

<!-- prawduct: scope=yale-source -->

**Why:** arrt#242, a helper shared by the Linked Art museums (Yale, the
Rijksmuseum, Getty), approved by the owner on 2026-10-06, and arrt#229, its first
consumer. The owner asked for the next public plugin on 2026-10-07, the day #233
Paris Musées was demoted. Measured the same day (`linked-art-findings.md`): the
three museums reach their image services by three roads and share only the last
step, so the shared part is IIIF, not Linked Art. That narrows #242's proposal,
and is recorded on the issue.

**What:** interface 1.3 adds IIIF parsers that do no I/O: `ImageService` (an
`info.json`'s original size and declared limits, and whether one request or the
tiles fetch it, below a long side the caller states), and `CanvasImage`,
`manifest_images` and `manifest_metadata` (a Presentation 2 or 3 manifest).
A built-in `yale` plugin (`library/sources/yale.py`) finds a work through the
YUAG or YCBA page its Wikidata item names (P8583, P9789). It never fetches the
page, which is challenged. It reads the manifest built from the page's number
and reports the first canvas under the page as the item spells it. The title and
maker are Yale's own words. Rights come from the canvas, not the manifest's CC0,
which licenses the record. The size is the canvas's: most works with no
image on Wikidata are served at 480 px and are reported as placeholders. The
reader answers one request for an original up to 16,384 px, and tiles beyond
it or below a declared limit. It offers its reader alone with no registry. LUX
search is not built: the IDs reach 4,053 of the 4,068 YUAG items with no image.
The built-in enumerations, the contract (§ Versioning and errors), the plugin
guide (§ Reading IIIF) and the security model name the parsers and the plugin.
The live check (`test_yale_shapes_are_still_real.py`) passed 5 of 5 on
2026-10-07, and the descopes and the robots.txt findings are recorded as comments
on #242, #229, #226 and #230. The owner ruled the same day that robots.txt does
not bar a plugin's single, human-led requests (`source-plugins.md` § Trust): the
Rijksmuseum's and Philadelphia's image host (`iiif.micr.io`) disallows `/`, and
Getty's answers its robots.txt with 503. The plugin guide adds "ask per work,
never walk a site".
