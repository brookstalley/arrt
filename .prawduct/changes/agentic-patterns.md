---
schema: 1
type: chore
scope: agentic-patterns
date: 2026-11-18
title: How agents build here, written down
closes: [brookstalley/arrt#432]
---
The owner's ruling of 2026-11-18 (`owner-rulings.md`). Since 2026-10-15, a body of work
took a median of five review rounds, and both delegated branches of the last cycle took
a second round for reasons a brief could have prevented.

- **Delegation policy:** `project-preferences.md` § Workflow gains `Delegation` and
  `Delegate verification`, with one row in the norm index.
  - Delegates run feature tests only. The coordinator, or one integration subagent,
    holds the integration branch and decides the heavy runs in proportion to what
    merged. This is in the owner's words.
  - A plan's file refs resolve (`verify-chunk-refs`) before dispatch.
  - A delegate returns proof that each new check fails on the unfixed code.
- **Learnings:** four `core.md` rules that each said "a check must be able to fail"
  are one, now that the policy asks for the evidence.
- **#432:** `holding`'s `stop()` in `arrt/tests/browser/test_editing_a_wall.py` waits
  until the request it means to hold is held. With every fetch delayed by 300 ms, the
  old `stop()` fails #432's way and the new one passes. The test beside it had the same
  race.
- **#217's transition:** a stopgap on `accessibility-spec.md`'s norm 1, expiring
  2027-01-17.
- **CLAUDE.md:** the curation, `uv sync` and root-suite paragraphs moved to
  `docs/testing.md`. CLAUDE.md keeps each rule as one line with a pointer.

Not done here:
- `Inner-loop verification`, which the owner has not been asked about;
- the two other flaky browser tests, filed as #441 and #442 because their causes are
  unknown.

## Consumer note
none: no route, schema, contract or product behaviour changes.
