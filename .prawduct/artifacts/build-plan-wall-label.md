---
artifact: build-plan
version: 1
scope: wall-label
branch: feature/wall-label
partition: serial — every chunk rewrites parts of app.css, and chunk 01's tokens are what every later chunk is drawn in. 03 and 04 touch different screens but share the stylesheet's tile, heading and section rules, so parallel worktrees would conflict on the same blocks.
depends_on:
  - artifact: design-direction
  - artifact: information-architecture
  - artifact: accessibility-spec
governed_by:
  - artifact: design-direction
  - artifact: information-architecture
  - artifact: accessibility-spec
last_validated: null
---

# Build Plan — Wall label

## What this plan is

The owner said on 2026-10-08 that the client "still looks amateur", in its
layout, type and design system, not its colour. Three directions were drawn on
a Claude Design canvas (https://claude.ai/artifact/KKGdo4ktsDS32t15yyUpCS),
each shown on the Artworks grid and on a work's page, and the owner chose
**A · Wall label**. The owner also ruled the same day that **webfonts may be
used**, which reverses `design-direction.md` § Typography ("No webfont, and
this is a decision").

What Wall label is, in one line each:

- **Type.** Newsreader (an optical-size serif) for the museum voice: page
  names, work titles, section headings, a work's description. Instrument Sans
  for chrome, controls and data. Both are self-hosted.
- **Hierarchy.** A page's name is large (2.5rem serif). A section heading is
  the serif at `--text-xl`. Group labels are small capitals in the sans.
- **No boxes.** Sections are separated by a rule and space, not by a bordered
  card on a tinted ground. A bordered panel on a plaster ground is what reads
  as a form, not a museum.
- **The art sits on a mat.** A tile is the work on a `--surface-2` mat with a
  label beneath it: serif title, then the artist, then date and medium. On a
  work's page the image sits on the work's own mat colour, where one is
  recorded.
- **The shell is quieter.** The sidebar runs the full height of the page,
  with a hairline edge and a bar marking the current page. The top bar's
  search carries its icon inside the field. The status is a dot and a word, not
  a boxed button.

The palette does not change. Both schemes keep their tokens, and
`test_design_tokens.py` keeps checking them.

| Chunk | What |
|---|---|
| 01 | Typefaces, type scale and the Typography amendment |
| 02 | The shell: top bar, sidebar, status |
| 03 | The Artworks grid and its filter rail |
| 04 | A work's page |
| 05 | Ruled sections everywhere, and the walk |
| 06 | Controls: button rows, a size scale, touch heights, the cost as words beside its act |

**Not in this plan.** Colour: the palette stays. A dark-scheme redesign: the
dark scheme gets the new type and layout, and nothing more. Postarr's caption
in the mat: it has its own type rules (`accessibility-spec.md` norm 1), and
`design-direction.md` says nothing in `app.css` governs what a player draws.

**What I would do differently.** Two things, neither blocking:

- **The canvas drew the light scheme only.** Newsreader on the walnut ground
  has never been seen. Chunk 05 photographs both schemes, and if the dark
  scheme reads wrong, the fix is a weight or size change in that scheme's
  block. The fonts stay.
- **The canvas was drawn from a screenshot older than the current build.**
  Since then, the tile badges have been removed (#287), and a work's page has
  gained sections: Walls and Themes, What this work is, and the master image's
  acquisition state. The tile and the work page are built from what the code
  holds now, not from the canvas. The canvas sets the look; it is not a spec
  for the contents.

## Requirements Confidence

**Medium.** The look is chosen, and the screens it was drawn on are clear.
What is not yet confirmed is how it holds on the screens nobody drew (chunk
05), and in the dark scheme.

What would raise it: chunk 05's walk, done by the owner rather than by me, on
the real library.

- `[DECISION (owner, 2026-10-08): the client uses webfonts. Newsreader and
  Instrument Sans, both under the SIL Open Font License, served from
  /static/fonts as variable woff2 files in Latin and Latin Extended subsets.
  No CDN. | design-direction's reason for refusing them was a payload to serve,
  a licence to track, and a silent fallback. The owner judged the identity was
  worth the payload. The licence goes beside the files, and the fallback is
  made loud by a test that fails if the face did not load (chunk 01). A CDN
  would add an outside request to every page on a home-network service, so the
  files are served by the app | owner ruled]`
- `[DECISION: a page's h1 grows from --text-lg to a new --text-3xl (2.5rem)
  serif, on every page, Walls included. This amends § Component Patterns,
  whose reason for a small h1 was that "the art on it is what is large". |
  with the cards gone, the page's name is the only thing that tells a curator
  where they are, and one treatment per level is kept | owner can veto]`
- `[DECISION: sections are separated by a rule, not by a card. A .panel loses
  its border, background and shadow and gains a top rule. Cards survive only
  where the card is a block of facts and acts about a thing: a theme on the
  Themes index, and a work under review. A work's tile and an artist's poster
  are the thing itself, so they lose the card too, and become a picture on a
  mat with a label beneath (chunk 03). *(Corrected at chunk 03: this said a
  tile survives as a card, which contradicted chunk 03's "no card border".)*
  This amends § Component Patterns "Cards". | a bordered box around
  every section is what made the work page read as a form | owner can veto]`
- `[ASSUMPTION: Latin and Latin Extended cover the library's names. A title in
  another script (Japanese, Cyrillic) falls back to the system serif or sans,
  which is the behaviour today. | LOW | owner can correct]`
- `[ASSUMPTION, corrected at chunk 04: a work's page uses its recorded mat
  colour behind the hero image, and --surface-2 when none is recorded. | MED |
  owner can correct]` The hero is the *wall preview*, by an earlier owner
  ruling (`library/services/thumbnails.py`: on the Work page the wall render
  is the subject), and that preview already carries the work's mat and the
  panel around it. So the hero is drawn as it is, with no ground of its own;
  only the canvas, which drew the bare work, needed one.

## Norm dispositions

- `design-direction.md` § Direction, *the stylesheet holds the token values,
  and the token test refuses any colour outside the token blocks*:
  **conforms**. The shadow under an artwork becomes a token (`--shadow-art`)
  in both scheme blocks. No colour is written in a component rule.
- `design-direction.md` § Typography, *no webfont*: this is a description
  under the artifact, not its Direction norm, and it is **amended by owner
  ruling** (the DECISION above). The amendment is recorded as the owner's,
  dated, with the old reasoning kept and answered rather than deleted.
- `design-direction.md` § Visual Identity, *chrome never competes with the
  artwork*: **conforms**. The type is more distinctive, but it carries no
  colour, and removing the panel boxes reduces chrome rather than adding to it.
- `information-architecture.md` § Direction, *the *arr layout*: **conforms**.
  The sidebar of sections, the top bar with search, the toolbar on list pages
  and the library as home all stay. Only how they are drawn changes.
- `accessibility-spec.md`, *colour is never the only carrier of state*:
  **conforms**. The status keeps its word beside the dot, and the sidebar's
  review count keeps its words.
- `accessibility-spec.md`, *text contrast at AA*: **conforms**. The palette is
  unchanged and the token test still computes every pair. One new check: the
  label text under a tile stays at or above `--text-sm`.
- `api-contract.md`: **inapplicable**, because no route changes. The font
  files are served by the existing `/static` mount (`http/pages.py`
  `ClientFiles`), with its revalidation headers.

## Status

- [x] Chunk 01: Typefaces and type scale
- [x] Chunk 02: The shell
- [x] Chunk 03: The Artworks grid
- [x] Chunk 04: A work's page
- [x] Chunk 05: Ruled sections everywhere, and the walk
- [x] Chunk 06: Controls

### Chunk 01: Typefaces and type scale

**Visual change:** yes

Done when:

1. new `arrt/src/arrt/http/static/fonts/` holds Newsreader and Instrument Sans
   as variable woff2 files (Latin and Latin Extended, normal and italic), each
   family's `OFL.txt` beside its files, and a short README naming each file's
   source package and version.
2. `app.css` declares them with `@font-face` (`font-display: swap`,
   `unicode-range` per subset). `--font-label` and `--font-ui` lead with them,
   and the system stacks they replace stay as the fallbacks.
3. The type scale gains `--text-3xl: 2.5rem`. The h1 and h2 treatments in §
   Component Patterns are changed to the DECISION above.
4. A browser test asserts that after load, `document.fonts.check()` is true
   for both faces and that a page's h1 computes to Newsreader. It is watched
   failing once with a font file renamed, because a webfont that fails to load
   looks like a working page in a fallback face.
5. `design-direction.md` § Typography is rewritten as the owner's 2026-10-08
   ruling, with the old "no webfont" reasoning kept and answered. *(At build:
   the plan said the platform-and-dependency findings would list the fonts,
   but that artifact covers hardware and the Python platform, and the repo has
   no dependency manifest. The fonts are recorded in § Typography and in
   `arrt/src/arrt/http/static/fonts/README.md`, beside the files.)*

### Chunk 02: The shell

**Visual change:** yes

Done when:

1. The sidebar runs the full height of the viewport at every page length (it
   stops partway down today), with a hairline right edge and a 2px bar on the
   current page. Sub-pages are indented and set at `--text-sm`.
2. The top bar's search has its icon inside the field. The submit button
   stays, as an icon button with an accessible name, because Enter is not
   discoverable to everyone.
3. The status indicator is a dot and a word, with no box, and is still a link
   to System › Status.
4. The phone drawer (below 40rem) and the coarse-pointer target heights
   behave as before. `test_the_sidebar.py` and `test_keyboard_and_phone.py`
   stay green unchanged.

### Chunk 03: The Artworks grid

**Visual change:** yes

Done when:

1. A tile is the work on a `--surface-2` mat (fixed height, image contained,
   `--shadow-art`), with the label beneath: the title in the serif, the artist,
   then date and medium muted. There is no card border.
2. Rows stay uniform in height (the § Component Patterns rule): a long title
   clamps to two lines and the artist to one, and nothing reflows as images
   arrive.
3. The filter rail's group names are small capitals in the sans, and counts
   are tabular figures. *(Descoped at build: "aligned to the right". A count
   is part of its button's text, "Native (39)", which is the button's
   accessible name and is pinned by about twenty browser tests. Moving it to
   a separate, right-aligned element would change every filter's spoken name
   for a small visual gain. The counts keep their parentheses and are set in
   tabular figures.)*
4. Posters, Overview and Table keep working. Table is a table, not tiles, and
   gets the new type only.
5. `test_the_grid.py` and `test_the_collection.py` stay green. A new test
   asserts uniform row height in a grid that mixes a one-line title and a
   three-line title.

### Chunk 04: A work's page

**Visual change:** yes

Done when:

1. The hero is two columns, collapsing to one below 60rem: the wall preview
   as it is (see the corrected ASSUMPTION), and the label block (h1 title,
   where it hangs, the facts list, and the acts).
2. The description is set in the serif at a readable measure (at most 68ch).
3. Every section the page holds today keeps its content and its order: Walls
   and Themes, What this work is, Master image, Where it can be obtained, What
   has been rendered, Mat colour. Each becomes a ruled section, two to a row
   at full width. Nothing is dropped.
4. A work with no master image, a failed acquisition and no sources (the
   synthetic corpus's common case) still reads correctly. A test covers it,
   alongside a held work.

### Chunk 05: Ruled sections everywhere, and the walk

**Visual change:** yes
*(Was the cumulative-final chunk. Its cumulative review ran and was clear
(`rev-20261008T204828Z-ce07f6e1`, then verify-resolutions). The marker
moved to chunk 06, which the owner added on 2026-10-08 after walking the
result.)*

Done when:

1. `.panel` and every per-screen card variant that is a section becomes a
   ruled section, per the DECISION above. Theme cards and tiles stay cards.
   § Component Patterns "Cards" is rewritten to match. `test_component_rules.py`
   gains an h2 check beside its h1 check: every section heading on every page
   computes to `--text-xl` (chunk 01 changed the h2 size and nothing pins it).
2. `arrt/tools/ux_walk.py` photographs every screen at phone and desktop
   widths in both schemes, on the synthetic corpus and on the real library.
   The contact sheets are compared with `.ux-walk/after-lists-settings`, and
   every regression is fixed or filed.
3. The browser suite (`-m browser`), the curation suite, and the root suite
   (`tests/preferences`, including `test_screen_tables.py`) pass.
4. An entry in `.prawduct/operator-verification.md` asks the owner to walk
   the real library in both schemes.

### Chunk 06: Controls

**Type:** cumulative-final
**Visual change:** yes

Added by the owner on 2026-10-08, after walking the redesign: "buttons are
spaced erratically", "a jumble of font sizes and button sizes", and "unclear
if $ is a button". Investigated: a row of acts after anything but a
paragraph sat flush against it (only `p + .row` spaced it). There was no
control size scale, and several places set their own padding.
`design-direction.md` promised 2.75rem controls under `@media (pointer:
coarse)`, but `app.css` never implemented it and no test checked it. The
cost tier is a boxed badge beside the button it prices, which reads as a
button itself.

Done when:

1. One action-row rule: a row of acts sits one step below whatever precedes
   it, whatever that element is, and its controls align on one line. The
   Artist page's Wikidata line, taste reactions and Select are spaced alike.
2. A control size scale in tokens: `--control-h` (2.5rem) for every act and
   field, and a compact size for toolbar menus and the menu button. Under
   `@media (pointer: coarse)`, every control is at least 2.75rem. The ad hoc
   paddings are folded into the scale. § Component Patterns records the
   scale.
3. A cost is part of the act it prices: the tier mark is no longer a boxed
   badge beside a button, and on the Ask page the Get button carries its
   bound ("Get · up to $0.01"), replacing the separate note. Every priced act
   still carries its tier (the IA ruling "a cost tier on every action"). *(Built differently: the tier stays beside the
   act, as plain words, "Cost: $", and the Ask page's bound moved from a boxed
   note above the buttons to one muted line directly under them. Putting the
   bound inside the button would change Get's spoken name, and the tier
   beside it, which every priced act shares, is pinned by the spend tests.
   The owner's complaint, a "$" that looked like a button, is answered either
   way.)*
4. Tests: rows of acts are spaced from what precedes them on every sidebar
   page; every `.action` meets `--control-h`, and 2.75rem in a coarse-pointer
   context; no tier mark is drawn as a box. Each is watched failing once.
5. The walk is re-run, and the cumulative review covers the branch.

## Verification

Each chunk is exercised in a browser against the synthetic corpus as it is
built. Chunk 05's walk is the whole-product check. The owner's walk on the
real library is the one this plan can't do for itself: whether it still looks
amateur is a judgement, and the owner makes it.
