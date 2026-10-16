---
artifact: build-plan
version: 1
scope: ui-mat-selection-labels
branch: feature/ui-mat-selection-labels
partition: serial, one worktree — every chunk edits `arrt/src/arrt/http/static/` (01 and 04 touch the shared top bar and labels across screens; 02 and 03 both edit `screens/work.js` and 03 builds on 02's mat drawing), so two delegates would collide on the same files
depends_on:
  - artifact: information-architecture
  - artifact: api-contract
  - artifact: player-contract
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: nonfunctional-requirements
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ Direction (the *arr layout: library as home, *arr names and places) → conforms: 01 makes the product name a link to the home page, as Sonarr's and Radarr's logos are; no page moves and no section is added"
      - "§ Direction (navigation is a link, an act is a button) → conforms: 01's brand is an `<a href>` through the router's `link`; 03's presets and Re-derive are buttons, because they write"
      - "§ Boundaries (no in-browser image editing; a mat is never unrecorded) → conforms: 02 draws a mat beside the picture and paints nothing on it; 03 records every choice through `record_mat_color` with its method"
  - artifact: design-direction
    dispositions:
      - "§ Direction (token values live in app.css; test_design_tokens.py refuses any colour outside the token blocks) → conforms: the mat colour is data from the catalogue, set as a custom property on the element, not a stylesheet colour; any new chrome uses existing tokens"
  - artifact: accessibility-spec
    dispositions:
      - "§ Direction 2 (WCAG 2.1 AA; colour never the only carrier of state) → conforms: 03's presets are named in words, not swatches alone, and the current one is marked by more than its colour"
      - "§ Direction 1 (the label's floor) → inapplicable because this plan changes no label surface"
  - artifact: player-contract
    dispositions:
      - "§ mat geometry (6% of the shorter side, bottom ×1.15; `contract/vectors/mat-geometry.json`) → conforms: 02 reads the same vectors in a browser test rather than copying the numbers"
  - artifact: architecture
    dispositions:
      - "§ Direction (operation logic lives only in the service layer; HTTP and MCP are thin bindings) → conforms: 03's presets and re-derive are `PreparationService` operations; the route and `art_catalogue` both call them"
  - artifact: security-model
    dispositions:
      - "§ Direction (outside text reaches the page as text) → conforms: 02 sets the mat colour as a style value only after the catalogue's `#rrggbb` check, the same guarantee the debug swatch already relies on"
  - artifact: data-model
    dispositions:
      - "§ Direction (a work is distinct from an image of it; derived artifacts are regenerated, never transported) → conforms: a mat colour stays a per-work record, and 02 draws no stored rendition"
last_validated: 2026-10-16
---

# Build Plan: the brand goes home, held works select everywhere, the mat on the Work page, and a rule for labels

## Goals

**Response taken:** Asked in two batches; the owner answered on 2026-10-16. They
chose the scope (the brand link, #317, #346, #91 without its AI picker, #267), split
#91's AI picker into a follow-up, took #267's rule as drafted, set the dark preset to
`#272727`, and kept the vision model as the first-preparation mat.

**Product:** Arrt's browser interface is the product's only human interface, and
the mat is the most visible thing on the wall (`information-architecture.md`
§ Information Hierarchy, the Work row: *re-mat*). Today only an agent can change a
mat, and the Work page shows the master with no mat at all. This plan:

- makes the Work page show the work as a wall does, mat and all;
- gives the curator mat control;
- closes one inconsistency in selection;
- makes the brand go home, as it does in every *arr app;
- writes the label rule the owner asked for, so later screens don't drift.

**Architecture:** The server composes no canvas since wave 4g. Each Player draws its
own mat (`player-contract.md`). So the browser draws its mat the same way: from the
work's current mat colour, with the contract's no-density proportions, read from
`contract/vectors/mat-geometry.json`. It must stay possible to:

- preview a mat colour **without recording it**, which #91's follow-up (the AI's
  three candidates) needs. Because 02 draws mats client-side, that follow-up needs
  no server compose primitive. This is why 02 takes the colour as a parameter, not
  only from the work's current row;
- add per-wall mat modes (`MatMode`: none, proportional, full) to the Work page
  later. Out of scope here: the Work page draws the proportional mat.

**Constraints (owner):**

- The mat lightness floor is L\* 15 (ruling of 2026-10-03, `MAT_LIGHTNESS_FLOOR`),
  enforced at `record_mat_color`. It binds the presets.
- The corpus ceiling is L\* 45.2, under `CORPUS_MAX_LIGHTNESS` = 50.
- Ruling 1 of 2026-10-11: engineering detail (hex values, method names) stays behind
  `?debug`.
- The repo is public.

**Tradeoffs accepted:**

- **#91's AI picker is split out.** The owner, 2026-10-16. It is a follow-up backlog
  item, filed at Chunk 03's close.
- **#91's "derived colour is the default" policy is descoped.** The owner,
  2026-10-16, chose to keep the vision model for first preparation. The derived
  colour is still lighter than the hand-tuned mats (median +14.2 L\*), and closing
  that gap was left to the model. So these #91 acceptance bullets are **dropped, not
  built**:
  - "every work has a mat by default, derived mechanically";
  - "`NO_MAT_COLOR` and its reason are removed". `UnplayableReason.NO_MAT_COLOR`
    (`library/readiness.py`) stays live, because a work not yet prepared still has
    no mat.

  03 records both on #91 when it closes the item.
- **#91's dark preset is `#272727` (L\* 15.6), not `#222222`.** `#222222` is L\* 13.2,
  under the floor, and the store refuses it. The owner, 2026-10-16.

**Inferred (not ruled):**

- The brand, pressed on Artworks, returns Artworks to its unfiltered state, as the
  sidebar's Artworks link does (`core/sidebar.js`'s `link`). It does not restore the
  last filter.
- 03's preset values live on the server and reach the client on the work's detail,
  so the client holds no hex.
- 03's Re-derive is shown only when it would change the mat.

**Decisions made mid-build:** *(appended while building)*

**Level:** High for 01, 02 and 04. Medium for 03, because its one persisted-format
question (below) is open until the chunk answers it. What raises it: answer that
question before writing the route.

## Status

- [ ] Chunk 01: the brand links home, and held works select on Search and Topic (#317)
- [ ] Chunk 02: the Work page shows the work in its mat (#346)
- [ ] Chunk 03: the curator chooses the mat (#91, presets and re-derive)
- [ ] Chunk 04: labels are bare nouns, by rule and by test (#267)
Context: Plan written 2026-10-16 on `feature/ui-mat-selection-labels`, from
`origin/develop` at `dfeb61a1`. Nothing built yet. Next: Chunk 01, after reading
`/prawduct:methodology building`.

## Verification Strategy

Run the curation plane (`cd arrt && uv run python -m arrt`) against a copy of the
operator's library. After each chunk, walk the changed screens at desktop width and
at 390 × 844, in both schemes. Run `-m browser` whenever `static/` changes
(CLAUDE.md). Chunks 01–03 carry `Visual change: yes` and append an
`operator-verification.md` entry. The mat especially needs a human eye at the wall's
proportions, which a test can pin but not judge.

## Build Chunks

### Chunk 01: the brand links home, and held works select on Search and Topic (#317)

- **Description:**
  - **The brand.** The top bar's `<p class="brand">Arrt</p>` becomes a link to the
    home page (Artworks), made with the router's `link`. So it has a real `href` and
    opens in a new tab with a modifier. A plain click goes through `go`, which
    returns Artworks to its unfiltered state even when it is already showing. It
    stays out of the heading outline, and its focus ring and hover follow the top
    bar's existing tokens.
  - The phone top bar stays one row (`information-architecture.md`
    § The *arr layout).
  - **IA records it:** the top bar's description in § The *arr layout and the
    Artworks row's "Reached from" gain "the product's name in the top bar", with the
    *arr precedent.
  - **#317.** On Search's held rows and a topic's *In your library* grid, held works
    can be ticked in Select mode. They get **Add to theme**, **New theme…** and
    **Archive**, by passing `selectionMode` its `held` half, as Artworks and the
    Artist page do. Hanging a selection is out of scope (#317 § Scope-out).
- **Depends on:** none
- **Tests:**
  - **Browser, the brand:**
    - It is a link whose `href` resolves to Artworks.
    - Pressed on a filtered Artworks, it clears the filter.
    - Pressed on a Work page, it lands on Artworks with focus handled as for any
      route change.
    - It is not an `h1`. The existing `test_navigation.py` check is kept, and
      `test_browser_surface.py`'s literal `<p class="brand">` assertion is replaced
      with the new shape and the reason recorded, not deleted.
  - **Browser, #317:** each acceptance bullet of #317, on Search and on Topic. A held
    work is ticked, added to an existing theme, added to a new one, and archived. A
    not-held work on the same page still offers Get. The fixture holds both kinds on
    one page, so a page that wires only one half fails.
- **Acceptance criteria:** #317's two acceptance bullets. The brand returns home from
  every route in the route table (parametrised over it, not a hand list).
- **Visual change:** yes — the brand's hover and focus state, and the select boxes on
  Search's held rows.
- **Done when:**
  1. Acceptance criteria met; root, curation and browser suites pass
  2. Committed, `/prawduct:critic` run and blocking findings resolved
  3. `operator-verification.md` entry appended; chunk marked `[x]`; #317 updated to
     shipped through `/prawduct:backlog`

### Chunk 02: the Work page shows the work in its mat (#346)

- **Description:** The Work page draws the master inside a mat in the work's current
  mat colour. Mat widths follow the contract's no-density proportions: 6% of the
  shorter side on each edge, and the bottom edge ×1.15. The mat follows the
  letterboxed picture, not the image element's box.
  - **The geometry is one module**, new `core/mat.js`. It is a pure function from
    the picture's natural size, the box it is fitted into, and a colour, to the
    mat's edges. Two callers rely on that: 03's previews, and #91's follow-up.
  - **The numbers are not copied.** A test reads `contract/vectors/mat-geometry.json`
    and runs every vector through the module.
  - **The colour is data**, set as a custom property from the catalogue's hex. The
    hex itself stays behind `?debug`.
  - **A work with no mat yet** (not yet prepared) shows the picture unmatted and says
    so in words. It shows no invented colour.
  - **The comment in the Work screen** that says the mat is drawn only at each wall
    is rewritten to say what is true (`arrt/src/arrt/http/static/screens/work.js`).
- **Depends on:** none (independent of 01; ordered second for review size)
- **Tests:**
  - **Browser:**
    - The mat's colour is the current `MatColor`.
    - Its edge widths match the contract vectors at a landscape, a portrait and a
      square master, within a pixel. A fixture with a non-current mat row present
      fails if the screen takes the first row instead of the current one.
    - A work with no mat shows no mat and says why.
    - The picture still enlarges, by keyboard as well (the second walk's #358).
  - **The module itself:** every vector in `mat-geometry.json`, run through
    the new `core/mat.js` by importing it in the page (`page.evaluate`). The client has no
    separate JS test runner, and the plan does not add one.
- **Acceptance criteria:** #346's four acceptance bullets.
- **Visual change:** yes — the matted work at desktop and phone width, both schemes,
  against the same work on a wall.
- **Done when:**
  1. Acceptance criteria met; suites pass
  2. Committed, `/prawduct:critic` run and blocking findings resolved
  3. `operator-verification.md` entry appended; chunk marked `[x]`; #346 updated to
     shipped

### Chunk 03: the curator chooses the mat (#91, presets and re-derive)

- **Description:** The Work page gets a mat control, visible without `?debug`.
  - **Two one-press presets**, named in words: `#272727` (dark, L\* 15.6) and
    `#6b6b6b` (L\* 45.2, the corpus's lightest). `art_catalogue` gains the same
    two operations, so an agent and a curator still have the same controls.
  - **Re-derive from the picture:** the free, mechanical dominant-colour derivation
    (the mat engine's `dominant_color` path, `arrt/src/arrt/library/acquisition/mat.py`, under the floor and ceiling it already
    obeys).
  - **Each choice is previewed** with 02's mat drawing before it is applied, and
    applied only when pressed. The current choice is marked by more than its colour.
    The previous colour is never discarded; `record_mat_color` already holds that.
  - **Server:** `POST /api/works/{id}/mat`, the row `api-contract.md` reserves for
    #91, records the preset as `manual` through `set_mat`, or records the
    derivation. The preset values live once, in the server's mat module, and reach
    the client on the work's detail.
  - **Records:** `api-contract.md`'s row is filled in, with its request and error
    shapes. A refusal from the floor reaches the curator as the store's message,
    beside the control (the second walk's failures-beside-the-control rule).
  - **The persisted question, answered before the route is written.** A re-derive the
    curator asked for and the engine's silent fallback both produce a dominant
    colour. They answer different questions: "did a person choose this?" and "did the
    model fail?". So does a curator's re-derive record `MANUAL`, a new `MatMethod`
    member, or `DOMINANT_COLOR_FALLBACK`? Whoever reads `mat_colors` later, chiefly
    `mat_masters.py`, the debug view and the follow-up's comparisons, must be able to
    tell the two apart. The chunk records the answer and its reason under
    *Decisions made mid-build*. A new enum member is a stored-value change and is
    reviewed as one.
  - **At close:**
    - #91 is updated through `/prawduct:backlog`: what shipped; the two dropped
      acceptance bullets and why (Goals § Tradeoffs); `#222222` → `#272727`.
    - A follow-up is filed for the AI picker: three candidates, previewed with
      `arrt/src/arrt/http/static/core/mat.js` (made in 02), nothing applied until picked, the cost stated on the button,
      and `MAT_PROMPT`/`MAT_SCHEMA` returning three.
- **Depends on:** Chunk 02
- **Tests:**
  - **Curation (real uvicorn, as the suite does):**
    - The route applies each preset and the derivation, through the route and not
      the service, using a preset other than the first.
    - A colour under the floor is refused with the store's message.
    - The previous row survives, not current.
  - **Unit:** the presets clear `MAT_LIGHTNESS_FLOOR` and sit under the corpus
    ceiling. They are parametrised over the server's preset table, so a preset added
    later is checked too.
  - **Browser:**
    - Pressing a preset previews it and then applies it.
    - The Work page's mat changes colour.
    - The current one is marked.
    - A refusal shows beside the control.
    - Re-derive is absent when it would change nothing, and present when it would.
- **Acceptance criteria:** #91's remaining bullets: the presets are one-press with
  their values recorded, and the previous colour is never discarded. Also: a curator
  can re-derive, and every choice is recorded with its method.
- **Visual change:** yes — the control's layout, the preview, and the copy.
- **Done when:**
  1. Acceptance criteria met; suites pass, `-m browser` included
  2. Committed, `/prawduct:critic` run and blocking findings resolved
  3. `operator-verification.md` entry appended; chunk marked `[x]`; #91 updated and
     the follow-up filed

### Chunk 04: labels are bare nouns, by rule and by test (#267)

- **Description:**
  - **The rule, as drafted in #267 and confirmed by the owner on 2026-10-16:**
    navigation, headings, column headers, buttons and field labels are bare nouns or
    verbs and never open with "The". Sentences, notes and announcements stay
    sentences.
  - **Its home** is a new subsection of `information-architecture.md`, beside
    § Vocabulary.
  - **The guard** is a new `tests/preferences/test_label_style.py`. It reads the
    curation plane's `static/` and fails on any short label that opens with "The ".
    It ranges over every label form #267 names (headings, buttons, return labels,
    field labels, panel titles passed through a helper, captions, `<option>`s), not
    only headings.
  - **Measured 2026-10-16, before planning:** the second walk's copy pass (#359)
    already removed most of #267's sites. A grep of `text:`/`label:`/`caption:`
    strings found only sentences left (the getting module's "The themes could not be
    read", the Walls screen's "The mat is always the work's own colour."). So the
    guard may be green on arrival. It must still be seen to fail once, against a
    re-broken label of each form (learning: a new check is watched failing).
  - **What separates a label from a sentence** is the guard's real design question.
    Settle it by the label's form, not by a word count, and record it in the IA
    subsection.
- **Depends on:** Chunks 01–03 (so the guard sees their labels)
- **Tests:** the guard itself. Its fixture includes one label of each form opening
  with "The", which must fail, and one sentence opening with "The", which must pass.
- **Acceptance criteria:** #267's three bullets (the owner's confirmation is
  recorded above). Every site renamed, or none left, stated with the grep that shows
  it.
- **Type:** cumulative-final
- **Done when:**
  1. Acceptance criteria met; all three suites and `-m browser` pass
  2. Committed, then `/prawduct:critic cumulative` run and blocking findings resolved
  3. Chunk marked `[x]`; #267 updated to shipped; change-log entry with
     `scope=ui-mat-selection-labels`

## Early Feedback Milestone

**Milestone chunk:** 01
**What the user can do:** press "Arrt" from any page to get home, and select held
works from Search and Topic.

## Governance Checkpoints

**Commit & PR cadence:** commit per chunk after its review. 04's cumulative review
makes the branch PR-ready. `/prawduct:pr create` runs when the owner asks.

- After Chunk 02: confirm that `core/mat.js` matches the Player's geometry on the
  real wall, before 03 builds previews on it.
- After Chunk 04 (cumulative): the whole bundle. In particular, check that #91's
  dropped bullets are recorded on the item and not silently missing.
