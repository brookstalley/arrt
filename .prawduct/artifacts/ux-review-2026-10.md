---
artifact: ux-review
version: 1
depends_on:
  - artifact: information-architecture
  - artifact: ia-proposal
  - artifact: user-scenarios
  - artifact: design-direction
  - artifact: accessibility-spec
last_validated: 2026-10-07
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
| 4 | **Navigation by script buttons.** Works, artists, topics, runs and reviews open by `<button>`, never `<a href>`: no new tab, no copyable or previewable address, nothing announced as a link; "go to artist" appears in four styles. | every list | 3 | P1 U X A D | No. | Owner ruling (§ Decisions 2) |
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
| 16 | **One request has four names (Ask, search, run, Get), and "search" means five things,** only some of which cost money. | Ask, Run, Review, Queue, History, Wanted, top bar | 3 | V | Partly: `ia-proposal.md` § Objects calls it a Get. | Owner ruling (§ Decisions 3) |
| 17 | **At 2,000 works, 750 cannot be browsed to;** Artworks stops at 1,250 by design (`core/badges.js`'s runaway guard) with no next page. | Artworks | 3 | U A | No. Rare today (46 works). | #131 (comment) |
| 18 | **Queue at 2,000 is one table, a Retry per row, no paging or bulk action,** naming each work by its ID beside its title. | Queue | 3 | U A | No. Rare today. | #281 |
| 19 | **A Get can offer a photo of visitors in a gallery** as a native-size match. | Work (not held) | 3 | P2 | No. ("Image found is a weaker promise than it looks" is § Dependencies and risks.) | #282 |
| 20 | **Machine formats where people read:** ISO timestamps to the microsecond (To review, History), nine-decimal dollars, plugin ids, "phase 1", "manifest build", "Directive sequence", raw keys on Status. | To review, History, Run, Status, Sources, Ask, Walls | 2 | U V D A | No. | #283 |
| 21 | **Every page is titled "Arrt"** and its only `h1` is the brand; old addresses (`#collection`, `#discover`, `#health`) are then the only page names a bookmark or history entry carries. | all | 2 | X V | No. | #273 |
| 22 | **Themes is an inline editor of every theme,** with no art, ↑/↓ one step at a time, and no link to `#theme/<id>`. "Position decides what shows first" while the wall says "shuffled". | Themes | 2 | A U D | No. #133 (shipped) gave one theme its address; nothing on the index links to it. | #284 |
| 23 | **Selection works three ways and offers one action;** Artworks' selection cannot add to a new theme (S7 detour). | Artworks, Artist, Search, Topic | 2 | A P2 | No. #169 (shipped) separated filter from add-to-theme on Artworks only. | #285 |
| 24 | **Settings opens on Taste,** which configures nothing and is headed "What this product thinks you like"; Wanted is hidden from the sidebar when empty and its help names a "Want" button that does not exist. | Taste, Wanted, sidebar | 2 | A U V | Wanted's hiding is recorded in the IA; *arr keeps it permanent. | #286; Wanted: owner ruling (§ Decisions 4) |
| 25 | **Status dumps healthy detail;** no About, Logs or Tasks. | Status | 2 | A U D | Partly: #265. | #265 (comment) |
| 26 | **History lists runs, not events** — nothing records an accept, archive or hang. | History | 2 | A | No. | Owner ruling (§ Decisions 5) |
| 27 | **No visual system across screens:** five heading treatments, four empty-state patterns, badges on every tile that say nothing ("native", "wall render"), disabled primaries that look live, spacing collisions. | all | 2 | D U | No. #2 (shipped) built the tokens; nothing governs headings, empty states or badges. | #287 |
| 28 | **Clean-up (S9) has no resolution or never-hung facet;** "Filter" hides the facets rather than filtering. | Artworks | 2 | P2 | No. | #288 |
| 29 | **Topics lists only held topics,** so S12 starts by recalling a name; a fresh topic took 22 s to fill. | Topics, Topic | 2 | P2 | No. #175 (shipped) fixed the index's layout, not what it lists. | #289 |
| 30 | **Accessibility minors:** three Tab stops per card, focus reset on a facet click, duplicate accessible names, the review note field unnamed, the status live region rewritten on every navigation, tables not keyboard-scrollable at narrow width, 13 px checkboxes, a 3.7:1 placeholder. | various | 2 | X | No. | #280 |

Two findings were resolved in this branch rather than filed: the stale
"proposed palettes" notice in `design-direction.md` § Colour (the stylesheet
already holds them), and the harness's own blind spot for pictures below the
fold.

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

1. **Build the ruled Walls and Work pages next?** Findings 1, 2, 3 and 13 are
   one plan and need no new ruling: `ia-proposal.md` already designed them.
   Part of Walls (what is next, durations) waits on wave 4; the current work and
   *Not this one again* do not.
2. **A norm: navigation is a link, an act is a button.** Fixing 4, 5 and 21
   together is cheap; making it a norm stops the next screen regressing.
3. **The request's one name.** § Objects says *Get*; the screens say Ask, search
   and run. Which word does a curator see?
4. **Wanted always in the sidebar,** as in every *arr app, or hidden when empty,
   as built?
5. **History: runs, or events** (accepted, archived, hung)?

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
