---
artifact: build-plan
version: 1
scope: work-pictures-and-sizes
branch: feature/work-page-pictures-and-sizes
partition: serial — one builder, two small chunks touching the same client
depends_on:
  - artifact: information-architecture
  - artifact: api-contract
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ A work's mark: every listed registry work carries its picture → conforms after Chunk 01; the phone rule that hid it departed from this without a recorded ruling"
  - artifact: accessibility-spec
    dispositions:
      - "Glyph and word carry the state → conforms. The picture stays decorative (`aria-hidden`); nothing a picture adds is the only carrier"
  - artifact: project-preferences
    dispositions:
      - "A work's size or date read from Wikidata is checked for plausibility before anything relies on it → conforms for sizes: `plausible_size` withholds one whose sides no work has or whose shape disagrees with its picture's, tested on corpus rows 12 and 33. Dates are not read by this plan (#215)"
  - artifact: security-model
    dispositions:
      - "§ Direction: outside text reaches the page as text → conforms. Sizes are numbers the server formats into nothing; the client renders them through `el`'s `text`"
last_validated: null
lifecycle: completed
archived: 2026-10-07
released_in: v0.4.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — Pictures in the registry lists, and sizes on a work's page

## What this plan is

The owner's feedback after the v0.3.0 deploy, 2026-10-05, seen on a phone:

1. The Artist page's *Their work* marks rows *Not held · Image found* but shows no
   picture, so choosing what to Get is guesswork.
2. A work's page by QID (*Rhythms*, Delaunay, Q19861769) shows Wikidata's
   picture but says nothing about how big the work is or how big the picture is.

The owner chose scope on 2026-10-05: build 1 and 2a, file 2b (#221).

**What was found before planning** (measured 2026-10-05, the evidence in the
session's notes):

- The pictures already load: `workState` asks Commons for each one. The phone
  hid them on purpose: `app.css` sets `.artist-works .work-pic { display: none }`
  below 40rem, which contradicts `information-architecture.md` § A work's mark.
  On a desktop they show at 2rem, from a 120 px rendering.
- Wikidata records *Rhythms* as 145 × 113 cm (P2048/P2049). Commons holds one
  file of it, 2,081 × 2,668 px. Arrt's Commons source reads only P18, so a Get
  finds this one candidate.
- Across five artists' 3,462 works with a height, 48 carry more than one
  best-rank height; some are a frame qualified with *applies to part* (P518),
  the rest small disagreements between sources.

## Requirements Confidence

**High.** Both halves show facts that already exist.

- [DECISION: no server-side copy of the registry pictures | the cause was the layout, not fetching; a cache would be a second thumbnail store with no lifecycle (#39) | owner approved 2026-10-05]
- [DECISION: the registry lists' pictures show at every width, larger than today (3rem), from Commons' 250 px rendering | 3rem is what tells two works apart; 250 is the fixed width that stays sharp at 3rem on a 3× screen (Commons serves fixed widths only, `sources/commons.py`) | agent's; owner can correct]
- [DECISION: physical size is the best-rank height and width, leaving out any qualified with *applies to part* = frame, framed or mount, normalised by Wikidata to metres and shown in cm and inches; shown only when each has exactly one value | a frame's size is not the work's, but a canvas's is: Wikidata records most paintings' own size as the canvas's (`wikidata-findings.md` § A work's size), so leaving out every part would lose most sizes. Two disagreeing sources have no right answer to pick, and saying nothing is better than saying the wrong one | agent's; corrected at build when the first rule emptied Q11826533; owner can correct]
- [DECISION: the size is checked for plausibility before it is shown (`plausible_size`): each side 0.5 cm to 120 m, no more than 50 : 1, and the shape within 1.25× of the picture's when its size is known; a failing size is unknown | the owner's ruling (`procurement-corpus.md` § Gaps, 4) binds the first reader of a size, which this is. Measured: good works within 1.034, the corpus's bad rows 2.27× and ~100× | agent's, under the owner's ruling; raised by the cumulative review]
- [DECISION: the picture's pixel size is Commons' own for the P18 file, asked by the registry, and judged by `assess_display_fit` against this deployment's box, shown as the review grid's fit badge | one verdict function, one badge, as the review card shows (the owner's ruling of 2026-10-02 that the badge carries the verdict word only) | agent's; owner can correct]
- [DECISION: the page says the picture is the one Wikidata names and that a Get asks every source | the owner read the picture as what Get would take; #221 adds Commons alternatives, the private scrapers already search | agent's]
- [ASSUMPTION: the fit is judged on the file as Commons holds it, not on the 3,840 px rendering a Get fetches of a wider one | LOW: for a box no wider than 3,840 px both verdicts are native | owner can correct]
- [ASSUMPTION: a failure to ask Commons for the size leaves the page known and the size unknown, and is not kept | LOW]

**Not in this plan:** Commons alternatives (#221); ranking a framed photo below a
flat scan (#177); alternatives from the private scrapers (their own repo).

## Status

- [x] Chunk 01: Pictures in the registry lists at every width
- [x] Chunk 02: A registry work's sizes, and what its picture is

### Chunk 01: Pictures in the registry lists at every width

**Exposed API:** none.

Done when:

- `.artist-works` tables (*Their work*, *Representative works*, *More by*) show
  each work's picture on a phone, at 3rem, with glyph and word beside or under it.
- The registry picture is asked at 250 px.
- `information-architecture.md` § A work's mark says the picture shows at every
  width.
- Tests: the browser suite shows a not-held picture on the Artist page at a phone
  width, and that a picture that fails to load still leaves glyph and word.

### Chunk 02: A registry work's sizes, and what its picture is

**Exposed API:** `GET /api/registry/works/{qid}` gains `height_cm`, `width_cm`,
`image_width`, `image_height`, `fit`.

Done when:

- `Registry.work` reads the physical size by the rule above; `Registry.image_size`
  asks Commons for a file's pixel size (raster only), with no redirect followed
  and a short wait. A held work does not ask it.
- The size is checked for plausibility before it is shown (the decision above).
- `RegistryWorkService` keeps the size per file for a week, as it keeps the work,
  and judges the fit against the deployment's box.
- The work page shows *Size* among the facts, and under the picture its pixel
  size and fit badge; with no size known it shows neither line.
- `api-contract.md` describes the fields.
- Tests: the client reads a frame-qualified and a disagreeing height correctly;
  the Commons ask refuses a redirect and reads a missing file as none; the route
  carries the fields, and none of them when Commons fails; the browser page shows
  both lines and neither.

- **Critic mode:** cumulative (two chunks, so the one boundary review covers both)
