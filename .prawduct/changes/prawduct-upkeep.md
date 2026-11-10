---
schema: 1
type: governance
scope: prawduct-upkeep
date: 2026-11-10
title: The change record moves to fragments, the governance anchor to AGENTS.md, and chunk status to review facts
---
Three repairs from a `/prawduct:doctor` health check, each its own commit so it reverts alone.

- **Change record on fragments.** `.prawduct/changes/` exists, so each branch records its change
  in its own file instead of prepending to `.prawduct/change-log.md`. No entry was release-pending
  (v0.10.0 had just shipped), so nothing moved; the log keeps its history.
- **Governance anchor in `AGENTS.md`.** `CLAUDE.md` carried the anchor prawduct shipped, which a
  host reading only `AGENTS.md` never sees. `prawduct-hook reanchor --apply` appended the current
  anchor to `AGENTS.md` and put `@AGENTS.md` in its place; the rest of `CLAUDE.md` is unchanged.
- **Chunk status from review facts.** Five live plans (`display-state`,
  `displays-and-label-outputs`, `walls-work-and-trust`, `ui-pass-walls`, `wave-4f-scenes`) carried
  hand-ticked `## Status` lists. Their ticked boxes are recorded as `chunk-imported` facts (24
  written; `ui-pass-walls`' two were recorded on 2026-10-28) and only the checkbox lists were
  removed. `plan import-status --remove-block` would have deleted the whole `## Status` section,
  and in three plans that section holds every chunk's definition, open operator walks included,
  so the lists were cut by hand: those chunk definitions now sit under `## Chunks`, and the two
  plans whose section ended in a branch note keep it under `## Branch context`. The derived status
  shows `ui-pass-walls` Chunks 02 and 03 done by review (`55b9ec3e`, `8049846d`), which the
  unticked boxes had hidden; each plan's open chunk is now only its operator walk.

Three live plans (`ui-pass-walls`, `wave-4f-scenes`, `wave-5-split`) named branches that were
merged and deleted; their `branch:` claims are commented out the way the other three already
were, each naming its open operator walk. Prose that still described hand-ticked boxes or
appending to `change-log.md` (`project-state.yaml`, the log's header, the plans) and `AGENTS.md`'s
opening lines were reworded to match.

`wave-5-split` was considered for archiving and kept live: its Chunk 06, the wall running from an
arrt-player clone, is an operator walk nothing records as walked.

## Consumer note
none: repository governance only; nothing a user of Arrt sees changes.
