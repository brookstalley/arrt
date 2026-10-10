---
artifact: design-direction
version: 1
depends_on:
  - artifact: product-brief
  - artifact: information-architecture
last_validated: null
---

# Design Direction

Authored 2026-08-10, after the visual system had already been built and tested.
This artifact is therefore mostly **a record of decisions that already hold**, plus
the tokens the interface work added. Where it merely describes what the stylesheet
does, the stylesheet wins; where it states a rule, the rule binds.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The product is
> becoming a server (library plus programming) and a player. **This artifact's
> scope and its Direction norm are unchanged**: they govern the curation browser,
> which stays the one human interface and moves with the server. The one new
> *visual* surface the change creates is the **caption set in the mat** on a
> player's screen. That surface belongs to the Player, and its type is governed
> by `accessibility-spec.md` (norm 1, amended the same day), not by the browser's
> tokens. **Nothing in `app.css` is a source of truth for anything a player
> draws.** The two products share no stylesheet, and the player repo will not
> have one to share after the split (wave 5). If a caption ever wants the
> browser's palette, that is a design decision to make then, not an inheritance.

## Direction

<!-- Ratified by the owner 2026-08-11. Enforcement row in project-preferences.md. -->

**The stylesheet is the source of truth for token values, and this artifact is the
source of truth for the rules about them.** `arrt/src/arrt/http/static/app.css`
holds the values; `arrt/tests/unit/test_design_tokens.py` reads that file,
computes every text and control pair in both colour schemes, and **refuses any
colour written outside the token blocks**.

> **Why:** a design artifact that restated hex values would be a second copy of a
> thing a test already enforces, and the copy is what goes stale. Naming the
> mechanism instead means the durable prose cannot drift from the value.
>
> **The load-bearing consequence:** a new colour token is not "added" until the
> test covers it. The token test has already narrowed itself once — two non-greedy
> regexes ate three quarters of the stylesheet, every component rule went
> unscanned, and a planted `#ff0000` reported clean. It now asserts its own scan
> scope. Any token added below must land inside that scope, or it is an unguarded
> colour wearing a token's name.
>
> **Status:** steady-state. Ratified by the owner 2026-08-11, together with the
> navigation norm in `information-architecture.md`. *(That navigation norm was
> amended to the *arr layout on 2026-09-30. This token norm is unchanged, and the
> amendment keeps the current palette: the *arr apps' look was offered and not
> chosen.)*
>
> **Retroactivity: completed 2026-08-12**, when the revised palettes landed in
> `app.css` (the norm sweep of 2026-10-05 found this paragraph still describing
> the day of ratification). As written then: the revised palettes are **not** in
> `app.css`, so the norm's own subject does not conform on the day it was ratified. That is deliberate and
> is not a grace period — it names the chunk that owes the work. Until those values
> land in the stylesheet they are hand-checked and ungoverned, and this norm is
> what says so.

## Visual Identity

**Museum, not gadget** (`product-brief.md` § Identity). Three constraints, already
recorded at the top of the stylesheet and restated here because they are the whole
direction:

1. **WCAG 2.1 AA**, enforced by the token test rather than by care.
2. **Chrome never competes with the artwork.** This is an image-review tool whose
   job is judging colour, so surfaces are near-neutral with a slight warm cast — a
   gallery wall, not a screen — saturation stays low, and nothing but the images
   carries a strong hue.
3. **Colour is never the sole carrier of state.** Every state indicator pairs a
   glyph and a word with its colour, so it survives greyscale, colour blindness,
   and a curator who has turned the lights down.

The third is the one that decays quietest under new work, and the IA round already
caught it decaying: a masthead status indicator that dropped its label at phone
width, leaving a bare amber dot. The rule is not "add a label where convenient" —
it is that a state indicator with no word is a bug at every viewport.

## Colour

### The light scheme is a gallery wall, not a page *(revised 2026-08-10)*

The first light palette read as software. The operator's verdict — "very tech,
needs to be more museum; dark theme is good" — is recorded here with the diagnosis,
because "make it warmer" is not a rule anyone can apply twice.

**Two things were doing it, and neither was the warm cast the stylesheet already
had:**

- **Pure white cards on an off-white ground.** `--surface-1: #ffffff` against
  `--surface-0: #faf9f7` is the exact figure of every SaaS dashboard: content
  floating on a page. A gallery has no white; it has a wall, and things hang on it.
  **There is now no pure white in the light scheme at all** — the ground is warm
  plaster and the raised surface is paper.
- **A blue accent.** `#2f5068` was chosen desaturated so it would sit behind a
  painting, and it does — but blue is what software uses for "interactive", and a
  museum's own accent is ink. The accent is now a **warm bistre**, the colour of a
  printed label. Primary buttons read as letterpress rather than as calls to
  action.

### The dark scheme is a wood-panelled study *(revised 2026-08-10, second pass)*

The dark scheme survived the first revision untouched and then failed the same
test one round later: *"still a bit too trendy tech, suspiciously like Claude's
colours."* The reference the operator gave is the useful part — **a wood-panelled
study with paintings and warm lighting** — and the diagnosis mirrors the light
scheme's almost exactly.

**Near-neutral charcoal with a single pale-blue accent is the default shape of
every dark UI.** `--surface-0: #161513` was warm only barely, and `--accent:
#9dc0da` was the same move the light scheme's `#2f5068` was making: blue standing
for "interactive". Two changes, both small:

- **The neutrals carry walnut rather than charcoal.** More red in the ground, and
  the text warms from `#f5f3ef` toward `#f4ece0` — lamplight on paper rather than
  white on grey.
- **The accent is gilt.** `#ccad66` — a brass fitting, a frame, a lamp — not a
  hyperlink. It is the dark-scheme sibling of light's bistre ink: in a lit room
  the label is dark on paper, in a dark room the fitting is bright on wood.

**`--warn` moved with it**, pushed orange to `#e0964a`. Gilt and amber are
neighbours by nature and remain close in lightness; what actually keeps them apart
is the standing rule that every state indicator pairs a glyph and a word with its
colour. Recorded rather than solved, because it is the kind of thing a later
palette edit will re-collide.

> **Both schemes were revised on the same diagnosis, one round apart, which is
> itself the finding.** In both, the identity was being carried by warm neutrals
> and undone by a blue accent — and in both, the accent was the part that had been
> reasoned about most carefully and defended in a comment. The lesson worth
> keeping: *a colour chosen for a good reason can still be the wrong colour,* and
> the tell was that it looked like other software rather than like the subject.

Two consequences worth stating, because they are easy to miss:

- **The accent can no longer distinguish a link from body text**, being near-black.
  Links carry an underline. This is the older convention and the better one.
- **Ground-to-card contrast dropped on purpose.** Tiles should read as work hung on
  a wall, not as cards stacked on a page, so the border does more and the
  background difference does less.

### Tokens the IA work added

Values live in the stylesheet. What this artifact adds is **the tokens the IA work
requires and the existing set does not have**, with the reasoning:

| Token | Role | Why it is not an existing token |
|---|---|---|
| `--good`, `--warn`, `--crit` | Semantic status | The accent means "this is a control". Status must be distinguishable from interactivity, so it cannot be the accent — and the existing per-state badge colours are specific to fit verdicts and image states, not to appliance health |
| `--good-quiet`, `--warn-quiet`, `--crit-quiet` | Status backgrounds | A status *ground* needs to sit under text at AA, which the foreground values cannot do |
| `--scrim`, `--scrim-text` | Type over artwork | The Walls screen and the contact sheet lay text on an unknown image. No surface token can serve this: the ground is a painting, so contrast has to come from the scrim rather than from the palette |

**Saturation on the status trio stays low deliberately.** A healthy appliance must
never shout on a page full of paintings, and the semantic hues are the only place
besides the accent where a hue appears at all.

**These three pairs must clear AA against the surfaces they sit on, in both
schemes, and are not exempt from the token test.** They are stated here as
requirements rather than as measurements, because the measurement belongs to the
test.

## Typography

*Rewritten 2026-10-08, when the owner chose the "Wall label" direction
(`build-plan-wall-label.md`) and ruled that the client may use webfonts. The
serif/sans split is unchanged. What changed is that each side now has a face of
its own instead of whatever the operator's machine supplies.*

- `--font-label`: **Newsreader**, an optical-size serif, falling back to
  `ui-serif, Georgia`. Used for page names, work titles, section headings, a
  work's description, and anything else in the voice of a museum label.
- `--font-ui`: **Instrument Sans**, falling back to `system-ui`. Used for
  chrome, controls and data.

**Webfonts, self-hosted: the owner's ruling, 2026-10-08.** This section used
to refuse webfonts, for three reasons. Each is answered here rather than
deleted, so the ruling can be challenged on its merits:

- *A payload to serve.* Two variable families in Latin and Latin Extended come
  to about 600 KB on disk, and a page usually fetches the two upright Latin
  files, about 190 KB, which are then revalidated rather than re-sent. The
  owner judged that the identity is worth that cost on a home network.
- *A licence to track.* Both families are under the SIL Open Font License.
  Each family's `OFL.txt` sits beside its files in
  `arrt/src/arrt/http/static/fonts/`, and that directory's `README.md` names
  the package and version each file came from.
- *A silent fallback when it fails.* That risk is real: `font-display: swap`
  draws a page that looks like it works in the fallback face. It is made loud
  by `arrt/tests/browser/test_the_typefaces.py`, which reads the browser's own
  record of each face, and by `test_every_font_the_stylesheet_names_is_served_as_a_font`
  in `arrt/tests/integration/test_browser_surface.py`.

**No font CDN.** The files are served by the app's own `/static` mount. A CDN
would put an outside request in front of every page of a home-network service,
and leave the fallback face in front of a curator whose internet is down.

Scale is 1.25 from a 16px base, `--text-xs` through `--text-2xl`, plus
`--text-3xl` (2.5rem) used only for a page's `h1`. *(An earlier `--text-3xl`
was added for a large Walls heading and removed with it on 2026-10-08. The new
one is the same size on every page, Walls included.)*

## Spacing & Layout

4px base, `--space-1` … `--space-8`. Content max-width 96rem. Radii stay crisp —
`--radius-sm: 2px`, `--radius-md: 4px` — because *a museum label is not a pill*.

**Breakpoints**, as the IA's three shapes:

| Bound | What changes |
|---|---|
| ≥ 60rem | Full layout. Theme rail vertical and sticky |
| 40–60rem | Rail becomes a horizontal scroller of pill filters; work detail stacks |
| < 40rem | The sidebar becomes a drawer behind a menu button, as in the *arr apps (`information-architecture.md` § The *arr layout); the top bar keeps the menu button, search and status; grid at two columns. *(Until 2026-09-30 this row said destinations moved to a bottom bar. That was never built.)* |

**Every element in the top bar after the brand must be allowed to compress**
(`flex: 0 1 auto; min-width: 0`), and long labels ellipsize. This is stated as a
rule because its absence was a defect the built surface had — five non-wrapping
tabs overflowed a 375px viewport — and the prototype reproduced the same failure
at *tablet* width the moment the status label grew. A top bar whose items cannot
shrink will overflow again the next time a word gets longer.

**Touch targets are keyed on the pointer, not the viewport.** `@media (pointer:
coarse)` raises control heights to 2.75rem (44px). The 2.5rem default
(`--control-h`) clears WCAG 2.2 AA's 24px floor, but 44px is what every touch
platform assumes, and a small window on a desktop still has a mouse — so
viewport width is the wrong signal.

## Component Patterns

*Rewritten 2026-10-08 (`build-plan-lists-settings-and-scale.md` Chunk 01, #287)
to say what the stylesheet holds and to add the patterns the October review
found ungoverned. The earlier text named `.btn`, `.primary` and `.danger`
classes the client never had.*

- **Headings** — one treatment per level. A page's `h1` is its name at
  `--text-3xl` in the label serif, weight 500, on every page, Walls included.
  *(Until 2026-10-08 it was `--text-lg`, because "the art on it is what is
  large". Wall label takes the boxes away from a page's sections, and once they
  are gone the page's name is what tells a curator where they are:
  `build-plan-wall-label.md`, a DECISION the owner can veto.)* A section's `h2`
  (`.panel h2`, a wall's title, an offered group) is `--text-xl` serif, weight
  500. The confirmation's title is an `h2` and takes the same type. A filter rail's group names are small capitals in the UI
  sans, a label rather than a section. Nothing else is a heading: an empty
  page's lead sentence is a paragraph.
- **Empty states** — one shape, `emptyState()` in `core/render.js`: the lead
  (what is missing) in the label serif at `--text-md`, never larger than the page's `h1`, then a muted line saying
  why or what fills it, then the way on as links or acts. No panel around it.
  This is for a page whose list is empty. A section with nothing in it, on a
  page that has other things, is one muted line under its heading.
- **Buttons** — `.action` is an act, and a link offered at the same weight
  wears its shape. Filled is the one committing act in a region: if two things
  are filled, neither is. `.action.quiet` is every other act. Hover tints toward
  the act's own text colour. **A disabled act looks disabled**: no fill, muted
  text, no hover, a not-allowed cursor. There is no destructive style:
  removal is confirmed in words (`core/confirm.js`), and colour reaching the
  reader before the label is the problem a red button would cause.
- **Spacing** — a row of acts sits one step (`--space-4`) below whatever
  precedes it, never flush: a paragraph, a facts list, another row. *(Until
  2026-10-08 only `p + .row` was spaced, so the Artist page spaced its three
  rows of acts three different ways.)* A row inside a flex column is spaced
  by that column's gap. One line of words that says what pressing an act
  costs or starts sits under that act, starting where it starts, small and muted
  (`captioned`, `.act-caption`), and is read with it by a screen reader.
- **Controls** *(2026-10-08)* — one height for every act and field,
  `--control-h` (2.5rem), and a compact one, `--control-h-compact` (2rem),
  for a menu's items. Under `@media (pointer: coarse)` both are 2.75rem.
- **Cost** — a priced act's cost is never a boxed badge, because a box
  beside a button reads as another button. It must plainly belong to its act
  and plainly not be an act. A priced act carries "Cost: <tier>" as words
  beside it. Ask's *Ask* spends without asking and says what each reply cost
  after it ends, so it carries a caption saying that instead *(owner,
  2026-10-08)*. The order-of-magnitude caption the owner asked for under a Get
  from words ("About $0.01", "About $0.10", "About $1": the curator is
  deciding between cents, dimes and dollars, not reading an exact bound) went
  with that Get on 2026-10-09; it is the form to reach for if another act
  wants one.
- **Badges** — glyph + word + colour, never fewer than all three. **A glyph
  has one meaning on every screen**, named in `core/glyphs.js`, where the word
  carries the specifics and the glyph only the kind of state; a new meaning
  gets a new glyph. **A badge appears only where its value varies**: a badge
  every tile would carry ("native") is left off, and the exceptions show.
- **Sections** *(Wall label, 2026-10-08)* — a part of a page (`.panel`) is set off
  by a `--border-strong` rule above it and space below, never boxed. A bordered
  panel on a tinted ground round every part of every page was what made the
  client read as a form. Its heading is the second level (see Headings).
- **Cards** — kept only where the card is a block of facts and acts about one
  thing: a theme on the Themes index, a work under review. Paper, not UI: 1px
  border, `--shadow-1`, 4px radius, elevation barely there on purpose. A work's
  tile and an artist's poster are the thing itself and are not cards (Tiles).
- **Tiles** — two densities (Posters, Overview; a Table view beside them) per `information-architecture.md`
  § Information Hierarchy. **Uniform row height in both**, which is a layout
  decision made for a behavioural reason: a grid of art that reflows as images
  arrive is the opposite of the identity, and the built client has already shipped
  that bug. *(Wall label, 2026-10-08.)* A work's tile and an artist's poster are
  not cards: the picture sits on a `--surface-2` mat with `--shadow-art` under
  it, and the label sits beneath on the page's ground. The label is at least
  the height of its longest shape: its clamped lines (two of title, one of
  artist, two of date and medium) and one badge row. That minimum is what makes
  rows uniform; only a tile whose badges wrap is taller. Sizing rows to the tallest tile instead (`grid-auto-rows: 1fr`)
  was tried and broke scroll restoration, because the page's length changed as
  later pages arrived.
- **Skeletons** occupy the final geometry rather than approximating it.

## Motion & Transitions

**Almost none, and that is the direction rather than an omission.** Opacity on
hover-revealed metadata (120ms), width on a progress bar, nothing else. No screen
transitions, no scroll-triggered reveals, no entrance animation on a grid of
paintings.

`prefers-reduced-motion: reduce` collapses every duration to ~0. Note that this
covers the skeleton pulse, which is the only ambient animation in the product.

**The one motion rule that is about correctness rather than taste: a poll must
never move focus.** The built surface shipped a two-second poll that stole focus on
the single screen with a decision on it. Every live region added by the IA work —
the run progress card, the status indicator, Ask's thread — updates
without touching focus.

## Platform Conventions

Web conventions, responsive, no platform-native affordances. Two deliberate
departures:

- **No swipe gestures for judging**, though a phone review queue is the canonical
  place for them. Accepting acquires and spends; rejecting suppresses a work from
  every future run. Neither is cleanly reversible, so both stay explicit labelled
  controls on every viewport (`information-architecture.md` flow 3).
- **No pull-to-refresh.** The surfaces that change on their own already poll and
  repaint from the response.

## Open questions

- **The dark-scheme pattern differs between the prototype and the product.** The
  prototype uses the three-state form (bare `:root`, a guarded
  `prefers-color-scheme` block, and an explicit `[data-theme]` stamp) because it
  offers a manual toggle. `app.css` uses the simple two-state form, which is
  correct while the product has no toggle. **If the product ever gains one, it must
  move to the three-state form** — a token defined only inside a media query never
  applies in the un-stamped state, and the page renders one theme's text on the
  other theme's ground.
- **Whether the semantic trio should replace any existing badge colours.** The fit
  and image-state badges predate it and have their own values; leaving both is
  defensible today and becomes two vocabularies for one idea if it persists.
