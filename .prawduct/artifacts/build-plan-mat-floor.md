---
artifact: build-plan
version: 1
scope: mat-floor
branch: feature/mat-floor
partition: one builder, sequential; Chunk 02 relies on the floor Chunk 01 puts into the engine
depends_on:
  - artifact: nonfunctional-requirements
governed_by:
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ Output Quality: mat colour at least as good as the 2024 corpus → amended by the owner's ruling of 2026-10-03: no mat darker than L* 15, which excludes 10 of the corpus's 41 colours; the corpus stays the bar above the floor"
      - "§ Output Quality: the curator's presets #222222 and #6b6b6b (unbuilt, #91) → #222222 is below the floor; recorded there, and choosing its replacement is left to #91"
last_validated: null
---

# Build Plan — No mat near black

## What this plan is

Backlog #183. Now that the mat sits inside pure black (#189), a near-black mat
next to the screen's black looks like a panel that can't show black. The owner saw
it on the HDMI monitor ("it looks like a bad LCD"). Neutral greys "look accidental".

| Chunk | What |
|---|---|
| 01 | The engine never answers darker than L\* 15, and a curator's colour below it is refused |
| 02 | Existing mats below the floor are chosen again, at startup, through the queue |
| 03 | Deploy and look |

**Not in this plan:** a floor on colourfulness (the owner ruled it out),
composing per screen (wave 4), the curator's mat control and its presets (#91).

## The owner's ruling (2026-10-03)

Asked against the 2024 corpus: 10 of its 41 mats are darker than L\* 15, and 21
are neutral (C\* < 5). The mat the owner liked, the Renoir seascape's `#22394b`,
is L\* 22.9, C\* 14.2.

- **The rule is lightness only.** No mat darker than L\* 15, on every screen.
  The owner chose the number from the agent's proposal rather than from swatches.
- **Black-and-white works still get a faint cast**, drawn from the paper or
  canvas tone, never a neutral grey. This is guidance in the prompt, not
  enforced. That is how the agent reads the ruling: lightness is the only thing
  enforced, and avoiding grey is guidance.
- **Existing mats below the floor are chosen again by the vision model.** The old
  colour stays in the work's mat history.

## Requirements Confidence

High for the rule, which the owner stated. The mechanism is the agent's:

- [DECISION: a model answer below the floor gets one more request that says why; a second answer below it falls back to the mechanical colour, lifted to the floor. The module still never retries until the model complies, and never silently changes a colour the model chose | agent's, owner can veto]
- [ASSUMPTION: a curator's own colour below the floor is refused, not accepted. Otherwise Chunk 02's startup pass would replace a person's choice | MED impact | owner can correct]
- [ASSUMPTION: the mechanical fallback is lifted in lightness only, keeping its hue; it is not given a cast, because the cast is guidance for the model | LOW impact | owner can correct]

## Status

- [x] Chunk 01: The floor in the engine
- [x] Chunk 02: Existing mats below the floor are chosen again
- [x] Chunk 03: Deploy and look

### Chunk 01: The floor in the engine

- `arrt/src/arrt/library/acquisition/mat.py`: a public `MAT_LIGHTNESS_FLOOR =
  15.0`. The prompt says the display around the mat is pure black, that a mat
  darker than L\* 15 reads as the screen failing, and that even an achromatic
  work takes a faint warm or cool cast rather than a neutral grey. It no longer says
  a grey is right for an achromatic work.
- A model answer below the floor gets one more request that names the floor and
  the colour it gave. Both calls' cost is reported. A second answer below the floor
  is a fallback, and the reason is recorded.
- The fallback is lifted to the floor, keeping a\* and b\*, and searches upward
  where the conversion's gamut clip darkens it. That is the mirror of the ceiling.
- `PreparationService.set_mat` refuses a colour below the floor by name.
  *(Moved at review: `CatalogueService.record_mat_color`, the one write every
  mat goes through, refuses it, so no caller can bypass it. The seed skips a 2024
  colour below the floor, with a report note, and no longer re-carries a colour
  the work has worn before, which would have restored the dark mats on every
  re-seed.)*
- Tests: the prompt carries the floor; a model answer below it is asked again and
  the second answer is used; two answers below it fall back, with both costs
  reported; fallbacks across the RGB cube land in [floor, ceiling]; `set_mat`
  refuses below the floor and accepts at it.
- Artifacts: the ruling in `nonfunctional-requirements.md` § Output Quality,
  with the `#222222` preset marked below the floor.

### Chunk 02: Existing mats below the floor are chosen again

- `prepare` treats a current mat below the floor as one it must choose again,
  and recomposes the canvas whenever it chose a mat, since the existing canvas was
  painted in another colour.
- At startup, every accepted work whose current mat is below the floor gets a
  prepare-only row on the acquisition queue, as `owe_recomposition` does for
  layouts. The old canvas serves until the new one is recorded.
- Tests: a below-floor mat is chosen again and the canvas redrawn; a mat at the
  floor is left alone and nothing is spent; the startup pass queues exactly the
  works below the floor; a work already queued keeps its row.
- *(Added at review.)* A canvas records the mat it was painted in
  (`renditions.mat_hex`), and one painted in another colour is not current. A
  mat is recorded before its canvas is redrawn, so without this a crash between
  the two left the old colour on the wall for good; it also replaces the
  "superseded" flag the first version passed around. The startup pass also
  queues a work with a canvas and no mat, which is what a fresh seed leaves for
  a dark 2024 colour.

### Chunk 03: Deploy and look

- Before deploying: the NAS's OpenRouter key is set and has credit. Without it
  the startup pass gives these works the mechanical colour, permanently, since
  a mat at the floor is never chosen again. Run `arrt/tools/mat_masters.py` knowing
  #119: it now counts every floor lift as "machine lighter than the human".
- The startup journal shows the works queued; the owner looks at the wall,
  especially the works that had near-black mats (Kelly, Hokusai, Rothko, Albers,
  Johns, Vasarely, Kline, Egreja, Still). Entered in `operator-verification.md`.

*Deployed 2026-10-03 (image `bb021bb`, 10 mats re-chosen by the model, none by
the fallback); looked at by the owner 2026-10-03: "Yep all good".*

## Verification strategy

`cd arrt && uv run pytest` and the root suite for Chunks 01–02. Before deploying,
`arrt/tools/mat_masters.py` on the machine that holds the masters reports the
fallback's change. Chunk 03 is the owner's eye.

## Governance checkpoints

One `cumulative` Critic review after Chunk 02, before the PR.
