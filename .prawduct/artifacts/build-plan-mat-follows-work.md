---
artifact: build-plan
version: 1
scope: mat-follows-work
branch: feature/mat-follows-work
partition: one builder, sequential; Chunk 02 records the geometry Chunk 01 draws, and both touch preparation
depends_on:
  - artifact: nonfunctional-requirements
  - artifact: re-architecture
governed_by:
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ The mat is geometric: a mat width in physical inches, bottom weighted → amended by the owner's ruling of 2026-10-02: the mat's outer edge takes the work's aspect ratio and everything outside it is pure black; still physical inches, default 1.5\" (was 2.5\"), bottom weight 1.15 unchanged"
      - "§ Output Quality: mat colour at least as good as the 2024 corpus → conforms: the colour engine and its prompt are untouched; grey and near-black mats are #183, not this plan"
  - artifact: re-architecture
    dispositions:
      - "§ Compositing moves to the Player (wave 4) → this plan changes the server's compositor now, because wave 4 is blocked on a Pi 4 measurement and the owner is looking at the wrong mat today; the rule is written into that section so wave 4's Player compositor inherits it"
last_validated: null
---

# Build Plan — The mat follows the work

## What this plan is

Backlog #189. On every screen the composed picture has three regions: the
work, a mat whose outer edge has the **work's** aspect ratio, and pure black
(`#000000`) everywhere else. Today the mat fills the whole 16:9 canvas, so a
square or tall work sits in a wide field of mat colour.

| Chunk | What |
|---|---|
| 01 | The compositor paints black, then a mat hugging the work, then the work; the default mat becomes 1.5" |
| 02 | A canvas records the geometry it was drawn with, and is recomposed when that geometry changes (#74) |
| 03 | Deploy and look |

**Not in this plan:** mat colour (#183, grey and near-black mats), composing
per screen (wave 4), a curator control for the mat (#91), caption in the mat.

## The owner's ruling (2026-10-02)

Verbatim, from #189: "the mat should match the work's aspect ratio, and
everything outside should be pure black". Asked the same day:

- **Every screen, the Frame included.** One canvas serves both today.
- **The mat stays physical, at 1.5"** top and sides, with the bottom 1.15x.
- **The matted work is as large as fits.** The mat may meet the screen's edge
  in one dimension; no minimum black margin.

## The geometry

The work keeps today's fitting: it is fitted (never upscaled) into the artwork
box `Settings.tv_artwork_box` already computes, and centred in it. The mat is
the work's rectangle grown by the side mat on the left, right and top, and by the
bottom mat below. Because the box is inset by exactly those margins, the mat
rectangle comes out centred on the screen (within a pixel of rounding). The fit
judgement, the resolution floor and the never-upscale rule are unchanged and still
measure the work alone.

At the operator's 50" 4K panel (88.1 ppi), 1.5" is 132 px, the bottom 152 px,
and the box 3576 x 1876. A 1:1 work renders 1876 px square inside a 2140 x 2160
mat, with about 9.6" of black on each side.

## Requirements Confidence

High. The owner stated the requirement and answered the three open questions.

- [ASSUMPTION: the vision model's mat prompt stays as it is; its description, a mat "on all four sides", becomes true rather than changing | LOW impact | owner can correct]
- [ASSUMPTION: until a canvas is recomposed, the old one keeps serving; the wall never drops a work because its geometry is out of date | MED impact | owner can correct]

## Status

- [x] Chunk 01: The mat follows the work
- [x] Chunk 02: Canvases recompose when the geometry changes
- [ ] Chunk 03: Deploy and look

### Chunk 01: The mat follows the work

- `arrt/src/arrt/library/acquisition/compose.py`: the canvas is black; the
  mat is a rectangle around the work at the side, top and bottom margins
  recovered from the box; the work is pasted where it goes today.
  `Composition` reports the mat's rectangle.
- `DEFAULT_MAT_WIDTH_INCHES` becomes 1.5; `.env.example` likewise.
- Tests, in `arrt/tests/unit/test_compose.py`: for 1:1, 4:7, 16:9, a 3:1
  panorama, and a work smaller than the box, assert that the pixels outside the
  mat are `#000000`, the mat's margins against the work, and that the mat is
  centred on the canvas. A 16:9 work fills the canvas with no black.
- Artifacts: amend `nonfunctional-requirements.md` § The mat is geometric
  with the ruling; add the rule to `re-architecture.md` § Compositing moves to
  the Player; correct comments that describe the old shape (`mat.py` above
  `MAT_PROMPT`, `postarr/src/postarr/kms.py` `fitted()`).

*Chunks 01–02 verified 2026-10-02 (commits `fb63be9`, `e06901b`; review
`rev-20261003T053907Z-88ee94a6`, 0 blocking, 4 observations accepted).* The
comment above `MAT_PROMPT` needed no edit: it says the mat is of even width on
all four sides, which this change made true. A changed diagonal reaches
preparation only as a different box, so the narrower-mat test covers it.

### Chunk 02: Canvases recompose when the geometry changes

Without this, every canvas already composed reads as current and the wall keeps
the old full-screen mat (#74, which this closes).

- A rendition records the **layout** it was drawn with: the panel's size and
  the mat's margins in pixels, plus a version for the drawing rule itself.
  A new nullable column on `renditions`, with a migration; null means unknown,
  which is out of date.
- `_current_tv_rendition` treats a different layout as not current, so
  `prepare` recomposes.
- At startup, the out-of-date canvases are recomposed in the background. The
  old canvas keeps serving until its replacement is recorded.
- Tests: a changed mat width, a changed diagonal and a pre-migration row each
  lead to a recompose; a current layout does not; readiness keeps serving the old
  canvas meanwhile.

### Chunk 03: Deploy and look

- The owner sets `MAT_WIDTH_INCHES=1.5` in the NAS's environment (its `.env`
  was copied from `.env.example`, which set 2.5 explicitly) and deploys.
- The startup log shows the recompose; the owner looks at a square and a tall
  work on the HDMI monitor. Entered in `operator-verification.md`.

## Verification strategy

Chunk 01 and 02: `cd arrt && uv run pytest`, and the root suite (the
preferences contracts read the artifacts). Chunk 03 is the owner's eye.

## Governance checkpoints

One `cumulative` Critic review after Chunk 02, before the PR.
