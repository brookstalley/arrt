---
artifact: build-plan
version: 1
scope: curation-ui-round-2
depends_on:
  - artifact: information-architecture
  - artifact: data-model
  - artifact: design-direction
  - artifact: accessibility-spec
  - artifact: api-contract
  - artifact: nonfunctional-requirements
  - artifact: architecture
  - artifact: project-preferences
governed_by:
  - artifact: information-architecture
    dispositions:
      - "the curation surface is organised around what a curator does, never around the pipeline's stages (§ Direction) → conforms: no chunk adds a destination or renames one. Chunk 04 adds controls to a panel that already exists on the Work screen; Chunk 03 changes how an open card lays out. The three destinations are untouched throughout"
      - "every screen and every consequential state is addressable (§ Navigation Structure) → inapplicable because: no chunk introduces a screen or a state a curator would want to link to. An expanded alternates disclosure (Chunk 03) is a transient reveal on a card, not a consequential state — it was already unaddressed before this plan and this plan does not make it more so"
      - "no in-browser image editing; a mat may never be unrecorded (§ Boundaries) → **amendment landed with this plan**, ruled by the operator 2026-08-18. Chunks 04 and 05 are what the old wording forbade. The amended clause is what they conform to: every mat they write carries a `MatMethod`, and nothing in either chunk paints on a picture"
      - "One row here per screen in § Screen Inventory, and the agreement is the check (§ Information Hierarchy) → conforms: no chunk routes a screen. `tests/preferences/test_screen_tables.py` (root suite) stays green throughout and is the mechanism, not the reading"
  - artifact: design-direction
    dispositions:
      - "the stylesheet is the source of truth for token values; this artifact is the source of truth for the rules about them (§ Direction) → **the constraint Chunks 04 and 05 must not trip.** `curation/tests/unit/test_design_tokens.py` refuses any colour written outside `curation/src/curation/http/static/app.css`'s token blocks. A mat preset is a **catalogue value, not a chrome token** — `#222222` and `#6b6b6b` are data about artworks, they belong beside the other mat values in the service layer, and they must not be added to `curation/src/curation/http/static/app.css`. The precedent is the swatch `curation/src/curation/http/static/screens/work.js:283` already draws from `current.hex_rgb` in a style attribute, which the source calls out as the only place data enters a style"
      - "chrome never competes with the artwork (§ Visual Identity) → binds Chunk 05's candidate previews directly: three composed canvases of the same work, side by side, are the most artwork-dense thing this interface will have drawn. The surrounding controls stay quiet"
      - "colour is never the sole carrier of state (§ Visual Identity) → **binds Chunk 04's presets and Chunk 05's candidates.** A swatch alone names nothing; every mat control carries its name and its hex beside the colour, and the current one is marked by more than being highlighted"
  - artifact: accessibility-spec
    dispositions:
      - "WCAG 2.1 AA on the curation browser, and colour is never the sole carrier of state (§ Direction) → binds Chunks 03, 04, 05. Chunk 03 must keep the alternates' reading order intact when the card spans the row — a visual reflow that reorders the DOM would change what a screen reader hears. Chunks 04 and 05 need real accessible names on controls whose visible content is a colour"
      - "an image is either decorative with `alt=\"\"` or is the content and carries the work and its artist; there is no third state (§ Announcement and semantics) → binds Chunk 05: a candidate preview is a picture of the work, so it carries the work and its artist, and the mat colour it demonstrates is named by the control beside it rather than buried in `alt`. This is the same rule that made #92's fourth acceptance criterion wrong"
      - "the e-paper label is legible at standing distance → inapplicable because: no chunk renders a label, touches the display plane, or changes a field the typesetter reads. A mat colour reaches the television, not the panel"
  - artifact: data-model
    dispositions:
      - "per-device runtime state never lives in the catalogue (§ Direction) → **binds Chunk 01 and is the reason its field is shaped the way it is.** Thumbnail provenance is a fact about *derivation lineage* — which row this file was drawn from — not about any device. The anti-pattern the artifact names by example (`_w648_h480` in a filename, `tv_content_thumb_md5`) is exactly what a provenance field could become if it recorded geometry or a device's idea of freshness. It records a rendition id and nothing else"
      - "derived artifacts are regenerated, never transported (§ Direction) → conforms: Chunk 01 changes when a thumbnail is regenerated, never whether. The operator's 2026-08-10 decision that the database may be zeroed is what lets the column arrive without a migration"
      - "invariant 4, whose text names #116 and reads *Still open* → **Chunk 01 closes it and must edit that sentence.** Leaving an artifact asserting a gap the code has closed is the failure this repo has recorded twice"
  - artifact: api-contract
    dispositions:
      - "`POST /api/works/{id}/mat` is listed but its shape is #91's to decide, not that set's → **Chunks 04 and 05 are where that debt is paid.** The row exists so a builder finds it rather than inventing a route outside the set; these chunks give it a shape and update the row"
      - "a description is switched on, a notice is relayed — notice prose is additive (§ compatibility table) → conforms: Chunks 04 and 05 may change `art_catalogue` notice prose freely and must not change an action description. Ruled by the builder 2026-08-17, standing until the operator rules otherwise"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ Output Quality makes the 41 hand-tuned 2024 mats the regression bar → **binds Chunks 02, 04 and 05.** Chunk 02 renames the constants that state the bar and must leave both numbers untouched. Chunks 04 and 05 must run `curation/tools/mat_masters.py` over the operator's real masters, because every mat test in the suite uses synthetic flats — which have no cluster competition and no pale regions, and are how a near-white mat over a Mondrian once shipped green"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer; MCP tools and HTTP handlers are thin bindings → binds Chunks 04 and 05. The preview primitive is a service-layer operation; the route and the tool are bindings over it"
      - "a module under `screens/` may import from `core/` and must never import another screen → conforms: Chunks 03-05 touch `curation/src/curation/http/static/screens/work.js`, `curation/src/curation/http/static/screens/review.js` and `curation/src/curation/http/static/app.css` only. `curation/tests/unit/test_client_module_boundaries.py` stays green"
  - artifact: project-preferences
    dispositions:
      - "the mechanical rows (formatting, naming, imports, logging-not-print, type-annotate-on-touch, specific exceptions, no hardcoded deployment values) → conforms: every chunk runs the curation plane's three commands, and the root plane's where it touches `tests/`"
last_validated: null
lifecycle: active
---

# Build Plan — Curation UI, Round Two

**Independent of `build-plan.md`, and for the same reason as the round before
it.** That plan's remaining boxes wait on a television or a panel. Nothing here
does: every chunk is browser client, service layer, persistence or artifact, and
the whole of it is exercised by suites that run on a laptop. The Pi display
service stays down for the duration — the operator's instruction of 2026-08-18,
and nothing in this plan wants it up.

**`active_build_plan` points here for the duration** and moves back to
`.prawduct/artifacts/build-plan.md` when this plan is archived. Unset, governance resolves
each chunk against the v1 plan and reports a pass about a different plan's
Chunk 01. That is not a missing check; it is a check that runs against the wrong
subject and passes. Three consecutive Critic rounds on the round-one branch came
back `chunk-ref-missing: unchecked` for exactly this reason, having graded
chunk 13A — hardware work unrelated to anything being reviewed.

## What this plan is

Three backlog items the operator picked on 2026-08-18, plus one that has to ride
with them.

| Chunk | Issue | What it is |
|---|---|---|
| 01 | #116 | What a cached thumbnail was drawn from, recorded rather than inferred |
| 02 | #120 | `curation/src/curation/acquisition/mat.py`'s two lightness ceilings, named so they cannot be confused |
| 03 | #89 | An open review card takes the row, so alternates are legible |
| 04 | #91 (i) | A mat a curator can choose: the derived default and two dark presets |
| 05 | #91 (ii) | The vision model as an opt-in that offers three, and applies none |

**#92 is deliberately not here, and this plan is what unblocks it.** Its own
triage orders it after #116: a thumbnail put into the run detail table is served
by the same cache, under the same badge that can currently lie about what it
drew from. Chunk 01 closes that. #92 stays at `stage:design` and is the obvious
next round.

**#120 is here because #91 edits the module it renames.** It is not one of the
three the operator picked. Doing them in separate rounds means one rewrites the
other's lines in `curation/src/curation/acquisition/mat.py`, and #91's own issue text quotes `CORPUS_MAX_LIGHTNESS`
by its current name — so the rename has to happen before or with the work that
cites it, not after.

**#116 is filed as `area:curation-ui` and that is wrong.** Not one line of the
fix is on a screen. Its own triage says so and recommends `area:curation`,
leaving the change to whoever picked it up; this plan relabels it. The symptom is
visible to a curator, which is presumably how the label was chosen, but every
item in this product is visible to somebody, and an area that tracks the symptom
routes the item to the wrong reader — which is literally what happened, since
this is how a persistence fix arrived in a UI triage set.

## Requirements Confidence

**Medium overall**, and unevenly so — the chunks are High and Medium, not a
uniform middle.

- **Chunks 01, 02, 03: High.** Each has its problem, its success criterion and
  its scope statable in a sentence, and each has its acceptance mechanism already
  written: #116 has a strict xfail that flips to a failure when it is fixed, #120
  has three named readers, #89 has a measurement and an operator's decision.
- **Chunks 04 and 05: Medium.** The *policy* is settled — the operator settled it
  on 2026-08-05 and refined it on 2026-08-10, on measured evidence, and the norm
  it collided with was amended by their ruling of 2026-08-18. What is unwritten is
  mechanism, in two places.

**What would raise Chunks 04 and 05 to High** — both cheap, both first steps of
their own chunk rather than research projects:

1. **A 30-minute spike on the preview primitive** (Chunk 04's Done-when step 0):
   compose a canvas at an arbitrary mat colour without recording a rendition or a
   `mat_color` row. `PreparationService.prepare()` writes both today; the question is
   whether the composition step can be reached without them, or whether it needs
   extracting. The answer changes Chunk 05's shape, not just its size.
2. **Reading the real `MAT_SCHEMA` response** (Chunk 05's `verify-api` step):
   `MatEngine.choose` returns exactly one `MatChoice` and `MAT_SCHEMA` is a
   single-object schema. Three candidates means a new schema and a new prompt,
   and what the model actually returns under it is not knowable from the current
   code.

**Open assumptions**

- `[ASSUMPTION: a thumbnail's provenance is fully described by "which rendition
  it was drawn from", so a nullable rendition id is the whole field | MED impact |
  user can correct]` — the alternative is recording the source's content hash
  and path as well. Rejected as designed because the id resolves to the row that
  carries both, and a duplicated hash is the field-with-no-defence shape this
  project has a learning about. If a rendition can be deleted and re-created with
  a new id while the thumbnail stays valid, this is wrong and the chunk finds out
  in its first test.
- `[ASSUMPTION: the two presets are named "Near-black" and "Mid-grey" on the
  surface | LOW impact | user can override]` — the operator settled the values,
  not the words. Colour is never the sole carrier, so they need names; these are
  placeholders a review can change.
- `[ASSUMPTION: three candidates is three, and the number is not itself a
  setting | LOW impact | user can override]` — the item says three. Making it
  configurable would be scope this plan does not have.

## A decision this plan takes, for the operator to veto

`[DECISION: § Boundaries gets one norm-index row, rather than ten or none |
because the clause that was just amended had been binding future work while
sitting outside the index that lists what binds — which is how a false rationale
survived in it unexamined | user can veto/override]`

The amendment landed with this plan. Writing it turned up that
`information-architecture.md` § Boundaries has **no row in
`project-preferences.md`'s norm index** — the only indexed IA norm is *organised
around what a curator does*. Yet § Boundaries plainly binds: the #91 triage's own
conclusion was that building the presets against it would be shipping a
documented violation, and that is what stalled the item.

Three options were weighed. **One row per clause** (ten rows) is faithful and
unreadable, and most of the clauses — no accounts, no mobile app — will never be
consulted. **No row** leaves the situation that produced this amendment: a
binding clause nobody re-reads, whose stated reason was contradicted by the data
model from the day it was written. **One row for the section**, with mechanism
`Critic`, says the true thing — that adding back anything § Boundaries excludes
is a ruling and not a build decision — at the cost of one row.

Recommended: the third. It is written into Chunk 04, because that is the chunk
whose work the amended clause governs; taking the row without the amendment's own
chunk would leave the index describing a rule the plan had not yet exercised.

---

## Status

- [ ] Chunk 01: What a thumbnail was drawn from, recorded rather than inferred (issue #116)
- [ ] Chunk 02: `curation/src/curation/acquisition/mat.py`'s two ceilings, named apart (issue #120)
- [ ] Chunk 03: An open card takes the row (issue #89)
- [ ] Chunk 04: A mat a curator can choose (issue #91, first half)
- [ ] Chunk 05: Three candidates, none applied (issue #91, second half)

---

### Chunk 01: What a thumbnail was drawn from, recorded rather than inferred

- **Description:** Nothing records what a cached thumbnail was actually drawn
  from, so `ThumbnailService._drawn_from` infers it from the current source's
  timestamp. The inference has a reachable failure: a thumbnail drawn from the
  canvas keeps being served after the canvas file disappears, under a badge that
  says "master image". Record the provenance instead of inferring it.
- **Depends on:** none. First because #92 waits on it and because everything else
  in this plan is above the persistence layer.
- **Issue:** #116
- **Artifacts consumed:** `data-model.md` invariant 4 and § Direction,
  `architecture.md` § Components & Responsibilities
- **Persisted format — the questions this column must answer** (required before
  designing the field, per the planning guide; lock-in is reversal cost, not
  size):
  1. *Was this thumbnail drawn from the original, or from a rendition?* — the
     question `_drawn_from` asks on every card paint.
  2. *If from a rendition, which one?* — so the answer survives that rendition
     being redrawn, deleted, or having its file vanish, which is the reported bug.
  3. *Nothing else.* Geometry, device, and freshness are explicitly out: they are
     the `_w648_h480` anti-pattern `data-model.md` § Direction names, and a
     duplicated content hash is the field-with-no-defence shape the project has a
     learning about. The rendition row already carries both.
- **Deliverables:**
  - **A nullable provenance column on `Rendition`** (`curation/src/curation/persistence/records.py`) —
    the id of the rendition this one was drawn from, null meaning the Original.
    No migration: the operator's decision of 2026-08-10 is that the database may
    be zeroed.
  - **`_drawn_from` reads it instead of comparing timestamps.** The docstring
    that currently explains the inference and names its accepted windows is
    rewritten to describe what is now recorded — including which of those
    accepted windows the change closes, and any that survive.
  - **The strict xfail removed.** `test_a_canvas_derived_thumbnail_is_not_served_once_the_canvas_file_goes`
    (`curation/tests/unit/test_thumbnails.py`) is strict, so closing this flips it
    from xfail to a failure. Removing the marker is part of the fix, not a
    follow-up, and the test is the acceptance check.
  - **`data-model.md` invariant 4 updated.** Its text names #116 by number and
    reads *"Still open"*. It stops reading that, and says what is recorded now.
- **The shortcut to refuse**, named by the item's design reviewer and repeated
  here so it is refused in review rather than discovered: do **not** close this by
  regenerating whenever an absent-file `tv_display` row exists. It spends a
  re-encode on every page load for a thumbnail legitimately drawn from the master,
  and it does not fix the reported case — in the repro the thumbnail *postdates*
  the canvas row, so a timestamp comparison still answers "current".
- **Acceptance criteria:**
  - The strict xfail is gone and its test passes on its own terms.
  - A thumbnail drawn from a canvas is regenerated once that canvas file is
    absent, and one drawn from the master is not regenerated by that state.
  - `data-model.md` invariant 4 no longer says the gap is open.
  - No new read is added to the card-paint path that scales with page size.
- **Done when:**
  1. The three suites pass and `.prawduct/.test-evidence.json` records it.
  2. A mutation sweep over the new branch in `_drawn_from` and over the column's
     writer, caught.
  3. `/prawduct:critic` for the chunk.
- **Critic mode:** (inferred — `chunk`)
- **Type:** code
- **Visual change:** no. A curator sees a correct picture instead of a wrong one;
  there is nothing new to look at, and the badge's own copy is unchanged.

---

### Chunk 02: `curation/src/curation/acquisition/mat.py`'s two ceilings, named apart

- **Description:** `CORPUS_MAX_LIGHTNESS` (50.0) is public, in `__all__`, and
  referenced nowhere inside its own module; `_DERIVED_LIGHTNESS_CEILING` (45.2) is
  private and is the one the clamp enforces. The constant that reads as the
  module's headline ceiling is the one the module never applies. It has already
  misled a reader once — `nonfunctional-requirements.md` carries a
  `Corrected 2026-08-11` note about a name that was a hybrid of the two.
- **Depends on:** none. Ordered before Chunks 04 and 05 because they edit this
  module and this issue's own text cites the old name.
- **Issue:** #120
- **Artifacts consumed:** `nonfunctional-requirements.md` § Output Quality
- **Deliverables:**
  - **Both constants renamed** so one reads as the corpus's observed region and
    the other as the ceiling the derivation enforces.
  - **Every reader updated** — `curation/tests/unit/test_mat_corpus.py`,
    `curation/tools/mat_masters.py`, and the
    `nonfunctional-requirements.md` prose that names them.
  - **The public/private split reconciled with the readership.** A public
    constant no module code uses is either part of the package's contract — in
    which case the module says so — or it is not public. The requirement's bar is
    the product's rather than the test suite's, which is an argument for keeping
    it exported; the argument is made in the source or the export goes.
- **Scope-out:** **neither number changes.** 50.0 and 45.2 are what the record
  says they are (#115), and this is a naming and visibility fix. A diff that moves
  either value has misunderstood the chunk.
- **Acceptance criteria:**
  - The two names distinguish the observed region from the enforced ceiling at a
    glance.
  - Every reader names the new constant; a grep for either old name returns
    nothing outside history.
  - Both values are byte-identical to what they were.
- **Done when:**
  1. The three suites pass.
  2. `cd curation && uv run python tools/mat_masters.py ../all.json` runs and
     reports against the renamed bar — needs `ART_ROOT`, spends nothing.
  3. `/prawduct:critic` for the chunk.
- **Critic mode:** (inferred — `chunk`)
- **Type:** trivial
  **Trivial because:** a rename of two module constants and their three readers,
  with both values fixed by an explicit scope-out and asserted unchanged by the
  existing corpus test. No control flow, no new files, no test deleted. The
  structural property bounding the risk is that the compiler-equivalent — a grep
  for the old names — is exhaustive in a codebase with no dynamic attribute
  access to them.
- **Visual change:** no.

---

### Chunk 03: An open card takes the row

- **Description:** Expanding "other scans" crams the alternates into the column a
  review card occupies. The `.alternate` rule is `grid-template-columns: 12rem 1fr`
  and it sits inside the `.grid` rule's `repeat(auto-fill, minmax(15rem, 1fr))` — a
  12rem picture and a column of facts, in a 15rem track. The only relief is the
  `@media (max-width: 40rem)` block that restates `.alternate`, which keys on the
  **viewport**, so at the desktop width the curator actually uses every card is
  narrow and no query fires. **The wrong axis is the defect in one sentence.**

  **Scoped by selector rather than by line, deliberately.** An earlier draft of
  this chunk cited four line numbers in `curation/src/curation/http/static/app.css`
  and three were already stale — the brittleness the planning guide names under
  *line-number scoping*. Worse, the citation hid a fact the chunk needs: that
  stylesheet has **two** `@media (max-width: 40rem)` blocks, not one. The other
  gives the Collection grid its phone layout and has nothing to do with this.
- **Depends on:** none.
- **Issue:** #89
- **Artifacts consumed:** `information-architecture.md` §§ User Flows (flow 3),
  Information Hierarchy (the Review row); `accessibility-spec.md` § Announcement
  and semantics; `design-direction.md` § Visual Identity
- **The decision, and what it closed:**
  `[DECISION: an open card spans the grid row (grid-column: 1 / -1) rather than
  adapting to a narrow one with a container query | ruled by the operator
  2026-08-18 | user can veto]` — the task is comparing pictures, and a container
  query fixes the axis while leaving the picture at 12rem, which is too small to
  judge a scan by. The surface question was already answered in favour of the card
  (flow 3, and `curation/src/curation/http/static/app.css`'s own note that a curator who navigated away would be
  choosing from memory); only legibility was open.
- **Deliverables:**
  - **An open card spans the row.** The disclosure's open state widens its own
    container instead of the layout adapting to a cramped one.
  - **The `.alternate` viewport query goes or is re-aimed** — the one restating
    `.alternate`'s columns, and **not** the Collection grid's block at the same
    breakpoint, which is a different rule about a different surface. Leaving a rule
    that keys on the wrong axis beside a fix for the wrong axis is how the next
    reader concludes the axis was fine.
  - **The DOM order is unchanged by the reflow.** A visual widening that reorders
    content changes what a screen reader hears; the accessibility norm binds this
    directly and it is the one thing a CSS diff can break invisibly.
  - **A browser test at the real grid width** — the bug is invisible at the
    viewport width the existing tests use, which is the whole reason it shipped.
- **Acceptance criteria:**
  - At a desktop viewport with a multi-column grid, an opened card's alternates
    show the picture and the facts without either being crushed.
  - Reading order matches visual order, open and closed.
  - The grid does not reflow *other* cards' contents in a way that moves what the
    curator was reading — § Screen States' rule that the loading state's job is
    not to move applies to a layout that shifts under a click as well.
- **Done when:**
  1. The three suites pass, and `-m browser -n0` separately.
  2. A mutation sweep over the new CSS branch and its test, caught.
  3. Operator verification entry appended — this is a layout judgement and no
     test can speak to whether it reads well.
  4. `/prawduct:critic` for the chunk.
- **Critic mode:** (inferred — `chunk`)
- **Type:** code
- **Visual change:** yes.

---

### Chunk 04: A mat a curator can choose

- **Description:** `choose_mat` and `set_mat` exist as services and as MCP
  actions, so an agent can change a mat colour and a curator cannot. Every human
  surface is read-only on the output property most visible on the wall:
  `curation/src/curation/http/static/screens/work.js:273` prints the current hex beside a swatch and offers no
  control. This chunk builds the half that spends nothing.
- **Depends on:** Chunk 02 (renames the constants this chunk's tests report
  against).
- **Issue:** #91, first half
- **Artifacts consumed:** `information-architecture.md` §§ Boundaries (as
  amended), Information Hierarchy (the Work row's re-mat action);
  `api-contract.md` `POST /api/works/{id}/mat`; `nonfunctional-requirements.md`
  § Output Quality; `accessibility-spec.md` § The curation browser;
  `design-direction.md` § Visual Identity
- **Deliverables:**
  - **The route gets its shape.** `POST /api/works/{id}/mat` is in the ratified
    contract with an explicit note that its shape is this issue's to decide. This
    chunk decides it and updates the row.
  - **Two dark presets as one-press controls** — `#222222` (L\* 13.2) and
    `#6b6b6b` (L\* 45.2), the values the operator settled on 2026-08-10. Each
    writes `MatMethod.MANUAL`, which is what the amended § Boundaries requires and
    what `set_mat_color` has always written. **The values live in the service
    layer, not in `curation/src/curation/http/static/app.css`** — they are catalogue data about artworks, and
    `curation/tests/unit/test_design_tokens.py` refuses a colour written outside the token blocks.
  - **The mechanical derivation as the non-AI default**, per the operator's
    policy: every work always has a mat, and the default is the dominant-colour
    derivation rather than off-white — which was proposed and withdrawn on
    evidence, the 41 hand-tuned mats running L\* 6.7–45.2 against a pale work's
    competition.

    **What #115's closure did and did not settle, because "unblocked" overstates
    it.** It fixed the *breach*: `_DERIVED_LIGHTNESS_CEILING` at 45.2 — the
    corpus's own lightest mat, deliberately tighter than the stated bar — took
    7/40 mats over the line to 0/40, and merging perceptually-identical clusters
    at CIEDE2000 10 took instability from 5/25 to 2/25. **The lightness bias
    remains, deliberately: the derivation is still lighter than the operator's own
    choice on 31 of 40 works**, and `curation/src/curation/acquisition/mat.py`
    assigns the rest to the vision model — which is this item's third bullet, not
    a reopening of this one. So the default clears the bar without closing the gap
    under it, and what a curator gets with no AI is a mat that is *acceptable*
    rather than *the one they would have picked*. That is the operator's settled
    policy and not a defect; it is written here because a builder reading only
    "unblocked" would think the derivation now matches the corpus, and would size
    Chunk 05 as a nicety rather than as the half that closes the gap.
  - **Each control names itself.** A swatch is a colour and colour is never the
    sole carrier: every control carries a name and the hex, and the current choice
    is marked by more than being highlighted.
  - **`ExclusionReason.NO_MAT_COLOR` stays, and this plan was wrong to retire it.**
    An earlier draft of this chunk deleted the enum member, the branch in
    `curation/src/curation/manifest/builder.py` that raises it, and the tests
    asserting it, on the ground that a guaranteed default mat makes it
    unreachable. **It does not.** The guarantee is about *which* colour is chosen,
    not about *when* a `mat_color` row exists: `record_mat_color` runs from
    `prepare()`, from `set_mat` and from the seed, so a work holding an original
    and a current TV rendition and no mat row still reaches the builder's
    assessment. With the branch deleted that work is not excluded — it goes to the
    wall unmatted, with nothing reported saying why. The exclusion is the only
    thing that makes the state visible, which is the argument the exclusion report
    was built on.

    So the deliverable is the opposite one: **prove the branch still guards
    something.** The test that pins it already exists —
    `test_a_work_with_no_current_mat_colour_is_excluded_and_named`
    (`curation/tests/unit/test_manifest.py`), reaching the state through the
    `ready_work(mat=False)` fixture — so Chunk 04 **keeps and strengthens** it
    rather than adding one: the strengthening is to reach that state through the
    real service calls this chunk adds, since a fixture that constructs it
    directly cannot show that the new default path leaves it reachable. The
    default makes the state rare; rare is not impossible, and a guarantee asserted
    in a plan is not a guarantee enforced by a schema.
  - **The § Boundaries norm-index row**, per the decision recorded above. Taken
    here because this is the chunk the amended clause governs.
- **Deliberately not here:** anything that spends. The AI control is Chunk 05.
- **Acceptance criteria:**
  - A curator can set a work's mat to either preset and to the derivation, from
    the Work screen, and every resulting row records its method.
  - No mat value is written into `curation/src/curation/http/static/app.css`; `curation/tests/unit/test_design_tokens.py` passes
    unchanged.
  - Every control has an accessible name that does not depend on its colour.
  - `NO_MAT_COLOR` is **still in the enum and still raised by the builder**, and a
    work holding an original, a current rendition and no `mat_color` row is
    excluded with that reason rather than reaching the wall unmatted. (This
    criterion said the opposite until the plan's own review caught it — the
    deliverable had been corrected and the criterion a builder builds to had not,
    which would have left the correction decorative.)
  - An existing mat is never overwritten without a curator's act.
- **Done when:**
  0. **Spike the preview primitive** — compose at an arbitrary mat colour without
     recording a rendition or a `mat_color` row. Chunk 05 needs it; finding out
     here is what keeps that chunk from discovering it mid-build. Record the
     answer in this chunk's notes even though Chunk 05 is what consumes it.
  1. The three suites pass, and `-m browser -n0` separately.
  2. `cd curation && uv run python tools/mat_masters.py ../all.json` — **required,
     not optional.** Every mat test in the suite uses synthetic flats, which have
     no cluster competition and no pale regions; that is how a near-white mat over
     a Mondrian shipped green.
  3. A mutation sweep over the new branches, caught.
  4. Operator verification entry appended.
  5. `/prawduct:critic` for the chunk.
- **Critic mode:** (inferred — `chunk`)
- **Type:** code
- **Visual change:** yes.
- **Read before building:** `curation/src/curation/services/imaging.py`'s docstring. It says it is the
  one downscale so its callers cannot drift, and the mat engine and the compositor
  already drifted once — one translating Pillow failures into a named refusal and
  one letting them escape, with the escaping path being the common one, since a
  work that already has a mat skips the engine and hits the compositor first.
  Every `set_mat()` takes that path, and this chunk adds callers to it.

---

### Chunk 05: Three candidates, none applied

- **Description:** The vision model becomes an opt-in button offering three
  candidate colours, each shown as a real composed canvas of the work, with
  nothing applied until the curator picks one. A mat is judged by how it reads
  *around* a picture, so swatches will not do. The spend buys options rather than
  a fait accompli.
- **Depends on:** Chunk 04 (the route, the panel, and the primitive spiked in its
  step 0).
- **Issue:** #91, second half
- **Artifacts consumed:** as Chunk 04, plus `openrouter-api-findings.md` and
  `api-contract.md` § the spend statement precedent
- **Foreign API:** the vision model behind `MatEngine.choose`
- **Deliverables:**
  - **`MAT_PROMPT` and `MAT_SCHEMA` return three choices, not one.** Today the
    schema is a single object of `hex_rgb`/`lab_*`/`reason` and `choose` returns
    exactly one `MatChoice`. Both change, and the fallback path — which returns a
    mechanical choice whenever the model cannot be reached — has to answer what
    "three" means when there is no model. **That is a real design question and not
    a detail:** one mechanical colour is not three candidates, and offering one
    option in a chooser built for three is a state the surface must have copy for.
  - **The preview primitive**, composing at an arbitrary colour with nothing
    recorded — the thing Chunk 04's step 0 spiked.
  - **The control says what it costs**, following the precedent already in the
    product: `/api/estimate` returns `estimated_cost_usd` and `basis`, and the UI
    prints "Asking costs at most $X. {basis}".
  - **The candidates carry the work in their `alt`**, not the mat colour — an
    image is either decorative or is the content, and there is no third state. The
    colour is named by the control beside the picture.
- **Acceptance criteria:**
  - Asking produces three composed canvases of the actual work and records
    nothing; the current mat stays current until one is picked.
  - Picking one records it with its method.
  - The control states its cost before it is pressed.
  - The no-model path is honest about how many options it has.
- **Done when:**
  0. **`verify-api`** — read the OpenRouter client and the real response under the
     new schema before drafting handlers or fakes. Vendor docs lag code and
     training data lags further, and a fake built from an assumed shape passes
     against the same assumption.
  1. The three suites pass, and `-m browser -n0` separately.
  2. `curation/tools/mat_masters.py` over the real masters, as Chunk 04.
  3. `-m llm_eval -n0` **by hand before shipping** — this chunk changes a
     model-driven surface and nothing else will measure it. It spends.
  4. A mutation sweep over the new branches, caught.
  5. Operator verification entry appended.
  6. `/prawduct:critic` for the chunk.
- **Critic mode:** `cumulative`
- **Type:** `cumulative-final`
- **Visual change:** yes.

---

## Governance checkpoints

Two, which is proportionate for five chunks on a built product with no new
execution context and no new external surface.

1. **After Chunk 01** — the only chunk that changes a persisted format. Check the
   column answers the three questions listed there and no fourth one, and that
   nothing in the card-paint path grew a per-row read.
2. **Before Chunk 05** — the last point at which the mat work can be descoped
   cheaply. Chunk 04 delivers a curator-usable mat control on its own; Chunk 05 is
   the half that spends money and changes a foreign schema. If Chunk 04's step-0
   spike says the preview primitive needs `PreparationService.prepare()` broken apart,
   that is the moment to decide whether Chunk 05 is still this round's work.

## Verification strategy

Beyond the suites: the three chunks with `Visual change: yes` each append an
entry to `.prawduct/operator-verification.md`, and `/prawduct:pr create` blocks on
pending entries. That is deliberate for this plan — two of the three are
judgements no test can make (whether alternates read well at a real window size,
whether three candidate mats around a real painting are actually comparable), and
the third is a colour control on the product's most colour-sensitive surface.

`curation/tools/mat_masters.py` is the other half, and it is required rather than
suggested on both mat chunks. It needs `ART_ROOT`, spends nothing, writes
nothing, and is the only thing in the repo that puts the mat engine in front of
the paintings the corpus was derived from.
