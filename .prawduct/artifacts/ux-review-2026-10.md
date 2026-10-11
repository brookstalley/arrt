---
artifact: ux-review
version: 1
depends_on:
  - artifact: information-architecture
  - artifact: ia-proposal
  - artifact: user-scenarios
  - artifact: design-direction
  - artifact: accessibility-spec
last_validated: 2026-10-11
---

# UX review — October 2026

The first run of `docs/ux-walkthrough.md`, on 2026-10-07, against the built
client at `develop` (`bafc9b67`). The owner asked for it because IA/UX/UI is the
product's weakest point.

**What was looked at.** Pass 1 (`arrt/tools/ux_walk.py`) photographed 29 pages
of the operator's real library (46 works, one wall) and 21 of a synthetic
2,000-work library, each at phone and desktop width in both schemes. Pass 2
walked the 13 scenarios of `ia-proposal.md` § The scenarios, walked through the
real product. Pass 3 ran five lenses (usability, *arr familiarity, design
direction, vocabulary, accessibility), each by an independent reviewer. Pass 4,
people, is the owner's and has not run (§ Pass 4).

**Everything was read-only.** Each reviewer browsed through the harness's write
guard. Every write the walk or a reviewer attempted (Accept, Reject, Rename,
Unassign, Move on, Create theme, Start the search) was refused in the browser;
afterwards the server's own state was checked and none had landed. So nothing
past a write was seen: what success looks like is Pass 4's.

**Where the evidence is.** Screenshots, inventories and the reviewers' full
reports are working material in the gitignored `.ux-walk/`, not records; this
repository is public. Each finding below names its screen so the next walk can
re-photograph it.

## What the review says, in six lines

1. **The ruled design is not built where it matters most.** The two weekly
   scenarios fail: a single held work cannot be hung (S1), and Walls cannot say
   what is on the wall (S6). Both pages are designed in `ia-proposal.md` and in
   no build plan.
2. **Navigation is done by buttons that call the router.** That one choice,
   plus focus and scroll handling on route change, is behind about a dozen
   findings across four lenses: no new tab, no copyable address, pages opening
   scrolled to the bottom, Back losing your place, every page titled "Arrt".
3. **The product speaks in its own voice, not the curator's.** One request has
   four names, "search" has five meanings, timestamps carry microseconds, and
   review cards quote the model in the first person.
4. **Some signals cannot be trusted.** Health pages contradict each other,
   unconfirmed matches look confirmed, search answers "do I have it?" with both
   yes and no, and works waiting for review are shown as not held.
5. **The art is not the hero.** Library tiles show the wall render, black bars
   and all, at a third of the tile; previews of works to Get are 48 px and
   hatched over.
6. **Scale and phone are untested ground.** At 2,000 works, 750 cannot be
   browsed to and Queue is one 209,000-px table; on a phone, To review's only
   action is off-screen and Themes widens the page.

## The ranked list

Ranked by severity × how often it bites × whether it sits on a core flow, then
by how many independent passes found it. **Lenses** counts the passes that
reported it (P1 inventory, P2 scenarios, U usability, A *arr, D design,
V vocabulary, X accessibility). **Planned?** says whether a ruling or plan
already covers the fix. **Route** is where the finding went (`docs/ux-walkthrough.md`
§ Synthesis): a backlog item, a comment on an open one, or a decision for the owner.

| # | Finding | Screens | Sev | Lenses | Planned? | Route |
|---|---|---|---|---|---|---|
| 1 | **A single held work cannot be hung.** The Work page offers only Archive and Edit; the only way is a one-work theme, three writes, and remembering to re-hang *All works*. | Work, Walls | 4 | P2 A U D | **Ruled**: `ia-proposal.md` § Work (state strip: walls and themes), § Artist ("Hang… applies to a selection"), S1 row. No build plan. | #272 |
| 2 | **Walls does not show what is on the wall.** "Showing (46)" lists the whole theme; the current work appears only on Status as a raw ID. "Move on" gives no visible result. | Walls, Status | 3 | P2 U V | **Ruled**: § Walls ("the work on the wall now, large… the next three"). No build plan. | #272 |
| 3 | **"Not this one again" does not exist, and Archive is the loudest button in reach.** A wall card opens the Work page, whose filled primary button removes the work from the whole library. | Walls, Work | 3 | P2 U D A | **Ruled**: § Walls, and § Against what is built ("Archive a selection; Not this one again from Walls"). | #272 |
| 4 | **Navigation by script buttons.** Works, artists, topics, runs and reviews open by `<button>`, never `<a href>`: no new tab, no copyable or previewable address, nothing announced as a link; "go to artist" appears in four styles. | every list | 3 | P1 U X A D | No. | Norm, ruled 2026-10-07; migration #273 |
| 5 | **Each navigation lands scrolled, and Back loses your place.** Focus on `#view` scrolls the page: a work opened from low on a list opens at its sources table; Back to Artworks returns to the top, 68 Tabs from card 20. | every route | 3 | P2 X U | No. | #273 |
| 6 | **Wall health contradicts itself.** Clients says both outputs "not connected"; Walls says "shown on hdmi-a-1"; the top bar says "Well". | Clients, Walls, top bar | 3 | U V | No. Possibly a heartbeat bug, not copy — investigate first. | #274 |
| 7 | **Search says both held and not held,** and a held artist appears twice as identical buttons leading to different pages. | Search | 3 | P2 | Partly: ruling 7 (store registry IDs); #252 (artists stay unlinked). | #275 |
| 8 | **A held artist's page hides its useful half behind a write** ("This is them"), and the registry page for the same artist says nothing of theirs is held. Every artist in the real library is unlinked. | Artist (held, registry) | 3 | P2 | Partly: ruling 4 (the hub), ruling 7, #252. | #252 (comment) |
| 9 | **Works waiting for review are invisible** to search and artist pages, which offer Get again (pay twice). | Search, Artist, To review | 3 | P2 | No. | #275 |
| 10 | **Review: an unconfirmed match looks confirmed.** The model's note says it found no source; the badges and Accept say match. Notes speak in the first person and show raw Markdown. Accept has no undo. | Review, Run | 3 | U V | No. | #276 |
| 11 | **A failed action says "Failed to fetch", at the top of the page,** often off-screen from the control clicked. | every action | 3 | U X P2 | No. | #277 |
| 12 | **The art is shown as the wall render** — mat, black 16:9 bars and grey band — at about 46% of the tile; previews of works to Get are ~48 px under hatching. The Review card is the model to follow. | Artworks, Walls, Artist, Topic, Search | 3 | D P2 | No. | #278 |
| 13 | **Work page anatomy.** The picture is ~190 px in a 1,168 px column; the title is not the heading; Archive is primary; no toolbar, no history. | Work | 3 | D A U | Partly, with 1. | #272 |
| 14 | **Phone: primary actions off-screen.** To review's Review button is at x=512 in 390 px; Themes renders 497 px wide; Activity tables clip; the top bar takes three rows. | To review, History, Run, Themes, all | 3 | U D X P2 | No. | #279 |
| 15 | **Focus ring clipped on card pictures** (`.card { overflow: hidden }`): on one Tab stop in three the keyboard user cannot see where they are. | Artworks and every `.card` grid | 3 | X | No. | #280 |
| 16 | **One request has four names (Ask, search, run, Get), and "search" means five things,** only some of which cost money. | Ask, Run, Review, Queue, History, Wanted, top bar | 3 | V | Partly: `ia-proposal.md` § Objects calls it a Get. | Ruled 2026-10-07: Get, everywhere — #291 |
| 17 | **At 2,000 works, 750 cannot be browsed to;** Artworks stops at 1,250 by design (`core/badges.js`'s runaway guard) with no next page. | Artworks | 3 | U A | No. Rare today (46 works). | #131 (comment) |
| 18 | **Queue at 2,000 is one table, a Retry per row, no paging or bulk action,** naming each work by its ID beside its title. | Queue | 3 | U A | No. Rare today. | #281 |
| 19 | **A Get can offer a photo of visitors in a gallery** as a native-size match. | Work (not held) | 3 | P2 | No. ("Image found is a weaker promise than it looks" is § Dependencies and risks.) | #282 |
| 20 | **Machine formats where people read:** ISO timestamps to the microsecond (To review, History), nine-decimal dollars, plugin ids, "phase 1", "manifest build", "Directive sequence", raw keys on Status. | To review, History, Run, Status, Sources, Ask, Walls | 2 | U V D A | No. | #283 |
| 21 | **Every page is titled "Arrt"** and its only `h1` is the brand; old addresses (`#collection`, `#discover`, `#health`) are then the only page names a bookmark or history entry carries. | all | 2 | X V | No. | #273 |
| 22 | **Themes is an inline editor of every theme,** with no art, ↑/↓ one step at a time, and no link to `#theme/<id>`. "Position decides what shows first" while the wall says "shuffled". | Themes | 2 | A U D | No. #133 (shipped) gave one theme its address; nothing on the index links to it. | #284 |
| 23 | **Selection works three ways and offers one action;** Artworks' selection cannot add to a new theme (S7 detour). | Artworks, Artist, Search, Topic | 2 | A P2 | No. #169 (shipped) separated filter from add-to-theme on Artworks only. | #285 |
| 24 | **Settings opens on Taste,** which configures nothing and is headed "What this product thinks you like"; Wanted is hidden from the sidebar when empty and its help names a "Want" button that does not exist. | Taste, Wanted, sidebar | 2 | A U V | Wanted's hiding is recorded in the IA; *arr keeps it permanent. | #286; Wanted ruled always shown — #292 |
| 25 | **Status dumps healthy detail;** no About, Logs or Tasks. | Status | 2 | A U D | Partly: #265. | #265 (comment) |
| 26 | **History lists runs, not events** — nothing records an accept, archive or hang. | History | 2 | A | No. | Ruled 2026-10-07: events — #293 |
| 27 | **No visual system across screens:** five heading treatments, four empty-state patterns, badges on every tile that say nothing ("native", "wall render"), disabled primaries that look live, spacing collisions. | all | 2 | D U | No. #2 (shipped) built the tokens; nothing governs headings, empty states or badges. | #287 |
| 28 | **Clean-up (S9) has no resolution or never-hung facet;** "Filter" hides the facets rather than filtering. | Artworks | 2 | P2 | No. | #288 |
| 29 | **Topics lists only held topics,** so S12 starts by recalling a name; a fresh topic took 22 s to fill. | Topics, Topic | 2 | P2 | No. #175 (shipped) fixed the index's layout, not what it lists. | #289 |
| 30 | **Accessibility minors:** three Tab stops per card, focus reset on a facet click, duplicate accessible names, the review note field unnamed, the status live region rewritten on every navigation, tables not keyboard-scrollable at narrow width, 13 px checkboxes, a 3.7:1 placeholder. | various | 2 | X | No. | #280 |

Two findings were resolved in this branch rather than filed: the stale
"proposed palettes" notice in `design-direction.md` § Colour (the stylesheet
already holds them), and the harness's own blind spot for pictures below the
fold.

## Closed by `build-plan-walls-work-and-trust.md` (2026-10-08)

Built on `feature/walls-work-and-trust` against the ranked list above. **Closed:**
1–3 and 13 (Walls leads with the work on the wall; Skip, *Not this one again*,
Change; the Work page's state strip and Hang…; Archive secondary), 4, 5 and 21
(navigation is a link; scroll, focus and Back; a title per page), 6 (a stale
client report no longer reads "Shown by"), 7 and 9 (search folds held twins and
marks works waiting for review; a Get skips both), 10 (*Not confirmed*, Markdown
as text, Undo by a 5-second hold, since an accept cannot be reversed on the
server), 11 (failures beside the control), 12 (tiles show the art), 14, 15 and
30 (phone layout and keyboard), 16 (Get, everywhere), 20 (one date formatter,
costs to the cent, plain words), 24's Wanted half, and 26 (History is events).
Ruling 3's budget and tiers are built too.

**Not closed:** 8 (#252, the hand-run matcher), 17 (#131), 18 (#281), 19 (#282),
22 (#284), 23 (#285), 24's Settings half (#286), 25 (#265), 27 (#287), 28
(#288), 29 (#289). Server sentences that still name plugins are filed apart.

**Re-photographed:** Pass 1 against a synthetic 2,000-work library on 2026-10-08:
no screen is reached only by a script button, and none is a dead end. The live
walk of S1, S6 and S8, with writes, waits on the branch being deployed, and Pass 4
is still the owner's.

## Closed by `build-plan-lists-settings-and-scale.md` (2026-10-08)

Built on `feature/lists-settings-and-scale` against the findings the previous
plan left open. **Closed:** 17 (Artworks pages from the server as you scroll;
every work of 2,003 reachable, #131), 18 (Queue groups failures by cause, pages,
and retries a cause in one request; one row for 4,000 failures, #281), 22
(Themes is a card grid, ordering lives on the theme page, the order copy
follows shuffle, #284), 23 (one selection model on every list, Select all by
filter, *New theme…* from any selection, #285), 24's Settings half (Settings
opens an index; Taste is headed Taste, #286), 27 (one heading scale, one empty
state, a disabled act looks disabled, one meaning per glyph in
`core/glyphs.js`, #287), 28 (*Size on the wall* and *Not on any wall* facets,
the owner's ruling for "never hung", #288), and 29 (Topics offers centuries and
movements before any are held, and a topic's works arrive as they are found,
#289). 25 is partly closed: Status's sources are one table with what each is
worth (#265) and the single-television geometry panel is gone (#266); About,
Logs and Tasks are not built.

**Still open:** 8 (#252, the hand-run matcher), 19 (#282, a gallery-room photo
offered as a match), 25's About, Logs and Tasks, and the records filed on the
way: #313 (each search, so a source's value survives a restart) and #316 (which
works a wall shows, for a real "never shown").

**Walked, with writes, on a throwaway synthetic library (300 works):** S7 made
a three-work theme from Artworks' selection without leaving the page. S9 found
297 works on *Not on any wall* once that theme hung, selected all and archived
them in one request; they stay on Artworks with their badge, as designed. S12
reached 16th century on Topics without typing; on a cold start the first works
took 19 s, the one Wikidata query that no split makes cheaper, and a warmed
topic answers at once. *Size on the wall* could not be walked there: the
synthetic library has no masters, so it has one band and the facet is not drawn.

**Re-photographed:** Pass 1 against a synthetic 2,000-work library, 21 pages,
84 captures: every capture scans clean, no console errors, no screen reached
only by a button, no dead end. The walk on the operator's library, and Pass 4,
wait on the branch being deployed.

## Second walk, on the deployed library (2026-10-11)

The first walk of the operator's own library since both plans above were
deployed (`develop` at `81e2d15e`: 61 works, one wall with its screen off, one
client). The owner asked for a critical pass on four things: uneven spacing and
layout, missing pictures, site and page navigation, and options or copy that
should not be there. **Pass 1** photographed 28 pages (112 captures); no screen
is reached only by a button, none is a dead end, and `search` is declared but
reached only by typing, which is by design. Its probe clicks attempted 18
writes (Create, Skip, Rename, Unassign, Retry, Want…), all refused in the
browser; the server was checked afterwards and none landed. **Pass 3** ran four
lenses, one per question, each by an independent reviewer: layout (L, 23
findings), pictures (P, 14), navigation (N, 14), economy (E, 24). Passes 2 and
4 did not run. The reviewers' files are working material in the gitignored
`.ux-walk/`; the codes below are theirs.

**What it says, in four lines.** Three screens carry most of the cost: the
Theme page, a Get, and Walls. Each is where the earlier plans changed the least.
The art is still missing where a person decides what to hang. And the product
still shows its plumbing: file hashes, port names, exception text and the
model's own instructions.

| # | Finding | Screens | Sev | Lenses | Planned? |
|---|---|---|---|---|---|
| 31 | **The Theme page is a wall of buttons with no art and no links.** 61 rows × five acts (↑ ↓ Move to top, Move to bottom, Remove) make a 7,256 px page of 305 boxes. On a shuffled theme, 244 of them change nothing, under a caption that says position does not matter. Titles, artists and the wall badge are plain text. The Size column is empty. *Add a work* on *All works* offers only works already in it. On a phone the acts sit in a 517 px table inside a 342 px scroller, off-screen, with the caption cut at "does not dec". | Theme | 3 | L1 L2 E2 E19 P-3 N1 | No. #284 moved ordering here and fixed its copy; the shape was not ruled. |
| 32 | **A Get shows error text where its pictures should be, and its one act leads nowhere.** Every *Also offered* cell holds a 30-word sentence ("…disk, so it cannot be shown here… Its source URL is…"), clipped top and bottom, which promises a URL it does not show. *How it read the request* prints the model's instructions. *Review these works*, the only filled button, opens "Nothing here is left to judge". The works listed link nowhere, though Get → Work is in the IA. *Asked for* says "No image found / not held" for a work the library holds. | Get, Review | 3 | P-1 L4 E3 E4 E5 N3 P-6 | No. |
| 33 | **Walls shows no picture.** With the screen off there is no last-shown work and no next three. The page says the screen is off twice, names `hdmi-a-1` and `epd-0`, and reads "not currently displayable". *Change* has no button shape, while the *History* link looks exactly like the *Skip* button. | Walls | 3 | P-4 E6 L16 N7 | **Ruled**: ia-proposal § Walls ("the work on the wall now, large… the next three"). #272 built the work now showing, drawn only while the screen reports one (`screens/walls.js`); the next three are not built. |
| 34 | **The Work page ends in a disk listing.** Under the label sit the master's path, its SHA-256, a renditions table (`presentation_master`, UUID file names, "current" on every row) and the mat as `#27285b`, not as a picture of the matted work. The picture cannot be enlarged, and nothing links to the work's topics. | Work | 3 | E1 P-9 P-10 N6 L12 | No. Whether this belongs in the product at all is the owner's call (below). |
| 35 | **The named back link goes to the sidebar index, not the page you came from.** A work opened from Dalí's page says "← Artists". An artist opened from a work says "← Artworks". From search the query is lost. The browser's Back is right every time, so the two disagree. | Work, Artist, Topic, Theme, Search | 3 | N2 | **Ruled**: IA § Direction ("returns to the page it was opened from"). Built for Work-from-lists only. |
| 36 | **The phone top bar cuts the status to "● W…" on every page,** a state with no word, which design-direction forbids. The drawer hides its own Menu button. | all, phone | 3 | L3 N12 | No. |
| 37 | **Two works with no master are text everywhere.** *Crak!* and *In the Third Sleep*: artic.edu refuses their master (403), and both are in the hung theme. Their thumbnails answer 400 and Artists asks for them anyway. Tiles print the endpoint's exception text, worded three ways across four screens. | Artworks, Artists, Work, Theme | 2 | P-5 E8 | No. Queue's retry is the data half. |
| 38 | **Search's dropdown pictures strangers' works but not yours.** Pictures in search rows and registry tables are 48–56 px and sit inside the state badge. | top bar, Search, Artist (registry) | 2 | P-2 P-8 | Partly: #12 above fixed tiles, not rows. |
| 39 | **Status has three names and talks in plugin IDs.** The masthead says *Well*, the sidebar *System*, the heading *Status*. 11 of 21 sources show by plugin ID, three columns repeat one value, and the disclosures are raw JSON. Queue groups failures by raw exception string, one group per URL. | Status, Sources, Queue | 2 | E9 E10 E11 E14 N11 | Partly: #265. |
| 40 | **Rows and spacing drift in a few shared rules.** `.row { align-items: flex-end }` drops Ask's *Start over* 26 px and sits text low beside its button. Acts sit flush against text (Clients, Artist, Theme). Tile titles take a heading margin inside panels. A tile's badge floats to the next row's picture. A page's name gets three different gaps to its content. Dark mode paints every quiet control gilt. Badges by a heading fall into the serif. | all | 2 | L5 L6 L8 L9 L11 L18 L21 | No. #287 set the heading scale; these are the rules it did not reach. |
| 41 | **Phone layouts outside Theme:** Artworks puts three toolbar rows before the first picture, and its filter rail is cut with no sign it scrolls. Clients' tables overflow and wrap IDs mid-word while Status's stack. Artists leaves about 175 px between rows. | Artworks, Clients, Artists | 2 | L14 L15 P-13 L10 | No. |
| 42 | **A dead address leaves the previous page painted** under the new title. A dead work address on a fresh load sits on "Loading the catalogue…" for good. | any detail | 2 | N4 | No. |
| 43 | **Walls and clients are named on six screens and linked from none.** | Work, Theme, History, Clients, Status | 2 | N5 | No. |
| 44 | **Copy that explains the system rather than the art.** Taste opens with an 80-word preamble above one item, and its verbs differ from the Artist page's. Topic pages speak Wikidata and are titled "Wikidata Q7049". An unmatched artist is told so three times, with a QID. Clients explains the architecture. History is 40 near-identical rows with full timestamps. A Get spends four rows saying "under a cent". The Artworks rail offers groups whose only option is zero. | Taste, Topic, Artist, Clients, History, Get, Artworks | 2 | E7 E12 E15 E16 E17 E18 E20 N8 L7 | No. |
| 45 | **Polish:** prose runs 1,168 px wide; table text is inset 12 px and numbers are left-aligned; the Themes index pins narrow cards left; Queue and Get stack headings with nothing between; topic indexes collide a one-item group with the next heading; Settings repeats its own sub-nav; Wanted's empty state explains click paths; *Start over* shows on an empty thread. | various | 1 | L13 L17 L19 L20 L22 L23 E22 E23 E25 | No. |

**Data, not design:** the home page's rail offers "End-to-end validation
2026-08-04 (1)", a test theme in the operator's library.

**What the plans above did hold.** Back restores scroll and focus; filters, sort,
search and paging live in the address and survive Back and Forward; keyboard
order is sound; the phone drawer works; every capture's pictures load except the
two masters artic.edu refuses (59 of 61 works answer on all three image routes).

**For the owner.** (1) Should the Work page's file, hash, renditions and Status's
raw detail stay in the product, folded away, or move to a debug view? (2) On a
shuffled theme, should ordering controls appear at all? (3) Walls with the
screen off: show the last-shown work, the next three, or both? The reviewers
assumed "keep, folded" for (1); nothing is built until these are ruled.

**Limits.** One wall, its screen off throughout; To review and Wanted were
empty, so their full states were not seen; nothing past a write; the 40–60rem
band was not measured; dark mode was spot-checked; Chromium only, no screen
reader.

## What works, and should survive a redesign

Several reviewers named these independently.

- **Confirmations** name the act, the target and the consequence, and are kept
  for acts that change a wall or cannot be undone (U, X).
- **The top-bar search dropdown** is Sonarr's, with states on every row and
  "Ask about…" where Sonarr puts "Search for…" (A, P2).
- **The sidebar** orients an *arr user within a second, phone drawer included
  (A, X).
- **Empty states and waits are honest** and offer a next step; **cost is shown
  before spending** and accounted for after (U, P2, A).
- **The Review card** is the best presentation of art in the product (D), and
  **Work remembers where it was opened from** (U, A).
- **The palettes and the serif/sans label pairing** land "museum, not gadget" (D).
- **axe-core found one rule** (`scrollable-region-focusable`, phone only) across
  50 pages: the accessibility spec's guards hold for what a scanner can see.

## Decisions only the owner can make

Put to the owner one at a time on 2026-10-07 and ruled the same day; the
rulings and their wording are `ia-proposal.md` § Rulings (2026-10-07). The
numbers below are that table's.

1. **Build the ruled Walls and Work pages next** — yes (#272).
2. **Navigation is a link, an act is a button** — yes, as a norm
   (`information-architecture.md` § Direction; migration #273).
3. **Approving spend**, the larger question the name opened — **no approvals;
   a monthly budget shown in the sidebar and a cost tier on every action** (#290).
4. **The request's one name** — *Get*, everywhere (#291).
5. **Wanted** — always in the sidebar (#292).
6. **History** — events, from now on (#293).

## Pass 4 — the owner's

No agent can do this part. Two things:

- **A week's friction log.** One line each time something annoys, with the
  address bar's contents.
- **Someone who has never seen it**, ideally someone in the household, given
  three tasks and no help, thinking aloud:
  1. *"Put the Kline up on the wall tonight."* (S1; finding 1)
  2. *"What's on the wall right now? Take it out of the rotation."* (S6, S8;
     findings 2, 3)
  3. *"Find something by Sonia Delaunay you'd like, and get it."* (S3, Delaunays;
     findings 7–9, 12)

Everything past a write — what Accept, Get, Hang and Archive look like when
they work — is seen only here.

## Limits

- Nothing past a write was seen (§ above).
- The real Sonarr and Radarr are behind a login, so the *arr comparison rests
  on the reviewer's knowledge of them.
- The synthetic library has no themes, runs or history; Themes and History at
  scale are extrapolated.
- No real screen reader was run; screen-reader findings are read from
  Chromium's accessibility tree.
- One wall: hanging on several walls was not exercised.
- Wikidata answers for the three scenario artists were warm from Pass 1, so
  their latency is not measured.
