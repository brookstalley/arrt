---
artifact: build-plan
version: 1
scope: ux-second-walk
branch: feature/ux-second-walk
partition: serial, one worktree. Every chunk edits `app.css` or the shared `core/` modules (router, badges, render), so two delegates would conflict on the same files
depends_on:
  - artifact: ux-review-2026-10
  - artifact: ia-proposal
  - artifact: information-architecture
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ Direction (the *arr layout) → conforms: no page moves and no section is added; 03 and 06 rename nothing that has an *arr name"
      - "§ Direction (navigation is a link, an act is a button) → conforms: 01 turns wall, client and topic names into links; 04 gives *Change* a button's shape and *History* a link's"
  - artifact: design-direction
    dispositions:
      - "§ Direction (token values live in app.css, rules here, and test_design_tokens.py refuses any colour outside the token blocks) → conforms: 02's dark-mode quiet control and any new rule use existing tokens or add a token inside the scanned scope"
  - artifact: accessibility-spec
    dispositions:
      - "§ Direction 2 (WCAG 2.1 AA; colour never the only carrier of state) → conforms: 03's enlarge works by keyboard, 05's reorder has a keyboard equivalent, and 02's status word stays whole so the state is not only a dot's colour"
      - "§ Direction 1 (the label's floor) → inapplicable because this plan changes no label surface"
  - artifact: ia-proposal
    dispositions:
      - "§ Rulings (2026-10-11), ruling 1 (engineering detail behind `?debug`) → conforms: 04 moves port names behind it"
      - "§ Rulings (2026-10-11), ruling 2 (a theme is never shuffled) → conforms: 05 removes every word of shuffle from the Theme page"
      - "§ Rulings (2026-10-11), ruling 3 (with the screen off, Walls shows the last-shown work) → conforms: 04 builds it"
last_validated: null
---

# Build Plan: the rest of the second UX walk

## What this plan is

The nine items still open from the second UX walk (`ux-review-2026-10.md`
§ Second walk, findings 31, 33 and 35–45). #363 and #355 shipped in
`build-plan-get-page-and-debug-view.md`, and #353 (shuffle moves to the wall)
shipped in `build-plan-wall-rotation-settings.md`. The owner approved this plan
on 2026-10-14, after a backlog triage that ranked it first. The reason given:
it is the product's only human interface, and its severity-3 findings are still
open.

| Item | Finding | Sev | Chunk |
|---|---|---|---|
| #361 a dead address leaves the old page | 42 | 2 | 01 |
| #356 the back link goes to the index, not the opener | 35 | 3 | 01 |
| #362 walls, clients and topics are named, never linked | 43, 34 | 2 | 01 |
| #360 shared row, spacing and table rules drift | 40, 45 | 2 | 02 |
| #357 on a phone the status word is cut and screens overflow | 36, 41 | 3 | 02 |
| #358 pictures missing or too small where a person decides | 37, 38, 34 | 3/2 | 03 |
| #354 Walls shows no picture when dark, and not the next three | 33 | 3 | 04 |
| #352 the Theme page is a wall of buttons | 31 | 3 | 05 |
| #359 copy explains the system rather than the art | 39, 44 | 2 | 06 |

## Goals

- **Response taken:** proceed, citing the items. Each item carries its own
  acceptance list. Rulings 1–3 of 2026-10-11 settle the design questions the
  walk raised. The owner approved the plan 2026-10-14 ("Yes plan approved").
- **Product:** a person deciding what to hang sees the art, can always get
  back to where they came from, and is never shown the plumbing. That is the
  walk's four-line summary, turned into a target.
- **Architecture:** the client stays framework-free ES modules over the JSON
  API. Any server change is a read the API does not yet offer, and it appears
  on the MCP surface too (`test_surface_parity.py`). The browser suite pins
  every acceptance bullet, and each new test is seen red against today's
  client.
- **Constraints:**
  - Every chunk touches `static/`, so the browser suite (`-m browser`) runs
    for every chunk.
  - `test_screen_tables.py` in the root suite holds the IA tables against
    `app.js`, so the root suite runs too.
  - The design-token test refuses colours written outside the token blocks.
- **Tradeoffs accepted:**
  - Chunk 02 fixes the walk's polish findings (45) as shared rules, not page by
    page. A page whose oddity no shared rule reaches is recorded as kept, with
    its reason, per #360's first acceptance bullet.
- **Inferred (not ruled by the owner):**
  - The back link names the opener by its thing's name ("← Salvador Dalí"),
    not by its page ("← Artists"). #356 says "names and returns to the opening
    page", and finding 35's examples are about pages. A thing's name is the
    more specific of the two readings.
  - #359's "the masthead's word is a state, not a page name": the masthead
    keeps its state word ("Well") and the page is *Status* in both the
    sidebar and the heading. *Status* is the *arr name, and the
    information-architecture norm says to use it.
- **Decisions made mid-build:**
  - [DECISION, 01: a refusal (400) of a one-thing read is the not-found page,
    as a 404 is] The server answers every service refusal with 400 by design
    (`service_error_response`, one `ServiceError`). The Artist and Topic
    screens already read a 400 on their own read as "nobody is here". The
    router now does this for every route that declares a `thing`. A 5xx is
    still the banner's. A 404 type on the server would grow the per-error
    table that `services/errors.py` exists to avoid.
  - [DECISION, 01: the not-found page's way on is named by the index's
    sidebar label ("Artworks", "Themes", "Queue")] It was "All artists" and
    "All themes" before. "All queue" for a Get made that pattern ungrammatical.
    Two tests' selectors moved with it (`test_the_theme_screen.py`,
    `test_topics.py`). Each still asserts the link reaches the index.
  - [DECISION, 01: a way back names its opener from the name the opener gave
    itself this visit (`setTitle`), and otherwise its kind ("← Artist")] A
    cold bookmark carrying `?from=` has no name to hand without a second read,
    and the address still returns to the right place. Settled by #356's
    acceptance (it names and returns) and the cost of an extra request per page.
  - [DECISION, 01: a wall is addressed `#walls?wall=<id>` and a client
    `#clients?client=<id>`, and the page brings that card to the reader
    (`data-arrive`)] Neither has a page of its own, and the IA requires that
    every consequential state be addressable. The Walls screen's own wall names
    are not links, because they are on their own page.
  - [DECISION, 01: a History page about one wall names the wall in its heading
    as plain text and links it in the line beneath ("… on Walls")] A link
    inside the page's `h1` would make the page's name a control.
  - [DECISION, 01: fixed in this chunk, outside its items: a search pressed
    while the client starts loaded the page natively (`/?q=…`), and the
    browser harness's `ui.open` returned before the client ran] Both were
    found by `test_the_shell.py`'s magnifier test failing once under the full
    parallel run of this chunk.
    - The cause, measured: `app.js` awaited `/api/sources` before calling
      `installSearch`. `ui.open` waited on `#view *`, which the served
      "Loading the catalogue…" placeholder already satisfied.
    - The fix: the top bar installs before the read. The client marks
      `html[data-started]` once the router is installed, and `ui.open` waits
      for that before the view's content.
    - Not "painted": five tests hold one of a screen's reads open to see the
      screen part-way, so a first-paint mark never came for them.
    - A held-read test now reproduces the failure deterministically. It was
      seen red first.
    - Not backlogged: fixed, per "no pre-existing exception".
  - [DECISION, 02: #360's list is mapped to the layout review's codes as the
    review wrote them] The issue swaps L18 and L21. Both are fixed: the
    badge's face, and quiet acts in ink.
  - Fixed as shared rules, each pinned in `test_shared_rules_and_phone.py`:
    - L5: rows align on the baseline, and fields on their boxes.
    - L6: an act in a line of words is spaced from them, what follows a row
      sits a step below it, and Clients' caption list loses its stray bullet.
    - L8: a tile's title takes no panel heading margin or weight.
    - L9: a tile's badge follows its label.
    - L11: one gap under a page's name.
    - L13: a sub-heading after content stands clear of it.
    - L17 (Queue): the section says its counts before its parts.
    - L18/L21: badges are set in the UI face, and quiet acts in ink.
    - L19: prose held to 70ch.
    - L20: a table's first column on the page edge, and figure columns
      right-aligned.
    - L23: the budget line on the nav's grid.
    - E25: *Start over* only after something has been said.
  - [DECISION, 02: kept, with the reason]
    - **E22, Settings repeats its sub-nav.** Kept. ux-review-2026-10 #24 made
      Settings an index on Sonarr and Radarr v4's precedent, and the
      information-architecture norm puts a page where the *arr app does.
    - **L23, the ⚙ glyph's weight.** Kept. It comes from a fallback font, and
      swapping the glyph is a choice of mark for the owner, not a spacing rule.
    - **L22, narrow theme cards.** Kept. `test_ten_themes_fit_on_one_desktop_screen`
      pins an earlier requirement, ten themes on one desktop screen, and
      13rem cards already break it at wider fonts. Larger theme pictures need
      the owner to trade that requirement away.
    - **L17, Get's "Works", button, "Asked for".** Kept. The Get page was
      rebuilt by #363 after the walk, and the synthetic library has no Get, so
      no walk has seen it since. It is queued for the operator's look
      (`operator-verification.md`) rather than claimed.
  - [DECISION, 02: E23 (Wanted's empty state names the controls that add a
    work) moves to chunk 06] `test_wanted.py` pins those words deliberately,
    so that the page names the controls that really put a work there. Cutting
    them is a copy decision for #359's single pass, not a spacing rule.
  - [DECISION, 02: #357's Artworks toolbar stays three short rows at 390 px]
    With a rail of facets above the grid, the first pictures are inside the
    first screen. That was #357's acceptance, and it held before this chunk
    (seen in the test against the old client). Collapsing View and Sort into
    one menu would change a control shared with desktop for no acceptance gain.
  - [DECISION, 02: on a phone the status shows "Well" or "Unwell", keeping
    the sentence for a screen reader] A state word, whole, is what
    `design-direction.md` § Visual Identity 3 asks. The sentence is too long
    for the bar. Recorded in § Spacing & Layout.
  - [DECISION, 03: a held work with no master is drawn by one placeholder,
    "No picture", on Artworks, Artists, a topic and the Work page
    (`noPicture` in `core/badges.js`)] The server's note (an exception's text
    as often as not) is shown only under `?debug`, per ruling 1. Why a work
    has no picture is the Work page's *Master image* panel's to say, where its
    acquisition line already says it. A picture that fails to load keeps its
    own sentence, because it is a different state.
  - [DECISION, 03: an artist is pictured only by a work holding a master, and
    `pictured_artwork_id` is null when none does] It fell back to a work with
    no image, whose thumbnail answers 400: the walk's "Artists asks for them
    anyway".
    - A contract change: the model, the store protocol, `api-contract.md` and
      the IA's Artists row all said "else their first accepted work".
    - `test_artist_surface.py`'s ordering test now gives both its works a
      master, so it still pins first-accepted, and a new test pins null.
    - Settled by #358's acceptance ("no thumbnail request for a work known to
      have no master").
  - [DECISION, 03: results and the dropdown lead each row with its picture,
    out of the state's badge (`statePicture`, `heldPicture`); the registry
    tables on Artist, Topic and Work keep theirs in the State column] The
    tables already draw it at 5rem (4rem on a phone), and their phone layout
    folds the other columns around it. The 48–56px the walk measured were the
    search rows. The library's own works in the dropdown are pictured only
    when they hold a master.
  - **[RULING, the owner, 2026-10-14: Walls' last-shown work comes from #316's
    record, built first]** Asked between the published schedule's slot at the
    time the screen went dark (recommended), building #316 first, and a
    one-field record. The owner chose "Build #316 first".
    - Chunk 04 therefore waits on #316: a durable per-wall record of the
      works shown, which is a new persisted format with its own requirements
      pass.
    - #316 is server work of another kind, so it gets its own plan, which may
      share this branch.
    - Chunks 05 and 06 do not depend on it and are built first.
  - [DECISION, 03: the Work page's picture opens in `core/enlarge.js`'s
    dialog, from a plain button around it] The review cards already use that
    dialog. It gives Escape, Close, a backdrop click and focus restored to the
    picture.
- **Level: Medium.** Chunks 01–03 are well understood: each item is at
  `ready`, or is a client-only change with a concrete proposal. Chunks 04–06
  are at `design`, and 04 may need a server read. Each of those chunks opens
  with a short design pass against its ruling, recorded under Decisions before
  any code. What would raise the level is that design pass, chunk by chunk.

## Chunks

### Chunk 01: the way back, a dead address, and names that link (#361, #356, #362)

- **Type:** bugfix
- `arrt/src/arrt/http/static/core/router.js`: a route whose object the server refuses (400) or answers 404 for clears
  the view and paints a not-found state. The state names what was asked for
  and offers a way on (the page's index). A fresh load of a dead work address
  reaches the same state instead of "Loading the catalogue…" for ever.
- `arrt/src/arrt/http/static/core/router.js` and `arrt/src/arrt/http/static/app.js` (`returnTarget`, `backLink`, the route table's
  `returnLabel`/`returnFor`): Work, Artist, Topic, Theme and Search each carry
  the opener in `?from=`, with Search's query kept. The back link names the
  opener and returns to it. A page opened cold falls back to its index, as
  today.
- Wall, client and topic links on Work, Theme, History, Clients and Status:
  every wall name links to Walls at that wall, every client name to Clients at
  that client, and a work's topics to their Topic pages. Walls and Clients may
  need an addressable anchor per wall or client. Check whether one exists
  before adding it.
- **Browser tests:**
  - opener → page → back link, for each of the five pages, including search
    with its query;
  - a cold load falls back to the index;
  - a dead address reached from a live page, and a dead address on a fresh
    load;
  - each wall, client and topic site is an `<a href>` that lands on the
    right place.
- **Records:** `information-architecture.md`'s navigation tables if a page
  gains an opener or an anchor.

### Chunk 02: shared rules, then phone width (#360, #357)

- **Type:** feature
- `app.css` shared rules:
  - row alignment;
  - the gap between an act and its text, and after a page's name;
  - tile title margins, and badge placement and font;
  - the dark-mode quiet control;
  - a prose measure;
  - right-aligned numerals in tables.
  Then #360's polish list, each item fixed or recorded as kept.
- Phone width (390 px):
  - the top bar's status keeps a whole word (shorten the bar, not the word);
  - the drawer leaves Menu reachable;
  - Artworks' toolbar collapses so a picture is in the first viewport, and
    the rail shows that it scrolls;
  - Clients' tables stack like Status's;
  - Artists' rows close up.
- **Browser tests:**
  - one gap after the page's name on every routed page;
  - prose capped;
  - numerals right-aligned;
  - each #357 acceptance bullet at 390 × 844;
  - the token test stays green.
- **Verification:** re-take the UX walk's captures (`arrt/tools/ux_walk.py`)
  for the affected screens and compare them by eye. #360 asks for that.

### Chunk 03: pictures where a person decides (#358)

- **Type:** feature
- Opens with a design pass on the placeholder and the
  enlarge control.
- A work with no master: one picture-shaped placeholder and one short
  sentence, the same on Artworks, Artists, Work and Theme. The client makes no
  thumbnail request for a work the server says has no master. Find out first
  whether the listing payloads already say so. If not, they gain a field (and
  the MCP surface with them).
- Held works in the search dropdown show their picture. Row pictures in search
  rows and registry tables grow and move out of the state badge.
- The Work page's picture opens large, by keyboard and by pointer, and closes
  with Escape.
- **Browser tests:** each #358 acceptance bullet, including that no thumbnail
  request goes out for a masterless work.

### Chunk 04: Walls shows a picture, and the next three (#354)

- **Type:** feature
- It may cross into the server (see the design pass).
- **Design pass first:** where the last-shown work and the next three come
  from. #354 names #316 and #309 as possible sources. Surveyed 2026-10-14:
  - **No server record of the last-shown work for a dark screen.**
    - The heartbeat is one file, overwritten on every report
      (`record_heartbeat`).
    - The heartbeat checker refuses a `work_id` beside any state other than
      `showing_art`.
    - `display_state.last` is filled only for `silent` (stale) walls.
    - No history event records a showing.
    So ruling 3 needs either a small record kept from the last `showing_art`
    heartbeat (which is #316's subject, and a persisted format), or the
    published schedule's slot at the moment the screen went dark (an
    inference, since the schedule says what was meant to show).
  - **The next three are in the published schedule but not exposed.**
    - `Published.on_the_wall(now)` and `after(now)` (`programming/manifest/v2.py`)
      exist, and nothing routes them.
    - A read belongs beside `get_wall_view` in `DisplayService`, served on
      `WallOut`, with its MCP twin.
  The choice between the two last-shown sources is recorded under Decisions
  before any code. It is a persisted format if the first is chosen, and that
  enumerates its consumers' questions first (#316's own).
- The work now on the wall, or with the screen dark the last-shown work, large.
  The next three, from the wall's schedule. "Screen off" said once, in words.
  Port names behind `?debug`. *Change* shaped as a button, *History* as a
  link.
- **Browser tests:** each #354 acceptance bullet, including the screen-off
  case. If a server read is added, a contract test on it and its MCP twin.

### Chunk 05: the Theme page (#352)

- **Type:** feature
- Opens with a design pass on reordering.
- Each member row: the work's picture, its title linked to Work, its artist to
  Artist. A member with no master draws `noPicture()` (`core/badges.js`), as
  every other screen does since chunk 03, and asks for no thumbnail. Reordering costs fewer than five boxes a row. The pattern is chosen
  in the design pass; the keyboard equivalent is required by
  `accessibility-spec.md`.
- The caption speaks of order only. *Add a work* offers only works not
  already in the theme. The Size column shows a value or goes. At 390 px every
  act is reachable without a sideways scroll, and the caption is whole.
- **Browser tests:** each #352 acceptance bullet.

### Chunk 06: copy (#359)

- **Type:** feature
- Status has one name. Topic pages are titled by the topic's name, with no
  bare QID in a title or heading. An unmatched artist is told so once. The
  cost of a Get is stated in one row. Taste's preamble is cut, with its verbs
  matching the Artist page's. Clients stops explaining the architecture.
  Repeated History rows group. The Artworks rail hides a group whose every
  option is zero.
- **Browser tests:** each #359 acceptance bullet.
- **Records:** `information-architecture.md`'s screen tables wherever a name
  changes. The root suite's `test_screen_tables.py` holds them.

## Verification strategy

**Per chunk:**
- `cd arrt && uv sync --group browser`. A plain `uv sync` removes the browser
  group, and the browser suite then skips itself while staying green.
- Run the chunk's browser tests and the tests for the files touched.
- Run the root suite whenever IA tables or `app.js` routes change.

**Before the PR:**
- the three suites and `-m browser`, in full;
- one pass of `ux_walk.py` over the routed pages;
- the screens this plan touched, compared by eye against the walk's
  captures.

**Pass 4** of `docs/ux-walkthrough.md` (the owner's friction log) is not this
plan's. It follows the deploy.

## Done when (every chunk)

1. Its acceptance bullets are pinned by browser tests, each seen red against the unfixed client; the chunk's tests and the touched files' tests pass.
2. `/prawduct:critic` run (inferred mode: `chunk` mid-plan, `final`/`cumulative` with the last), blocking findings resolved.
3. Committed; the item's backlog entry updated; the box below ticked.
4. Visual change: yes. Each chunk enqueues its screens in `.prawduct/operator-verification.md`.

## Status

- [x] Chunk 01: the way back, a dead address, and names that link (#361, #356, #362)
- [x] Chunk 02: shared rules, then phone width (#360, #357)
- [x] Chunk 03: pictures where a person decides (#358)
- [ ] Chunk 05: the Theme page (#352)
- [ ] Chunk 06: copy (#359)
- [ ] Chunk 04: Walls shows a picture, and the next three (#354), after #316's record (the owner's ruling, 2026-10-14)
