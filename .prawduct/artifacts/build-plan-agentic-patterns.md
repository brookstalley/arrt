---
artifact: build-plan
version: 2
scope: agentic-patterns
branch: chore/agentic-patterns
base: develop
working-branches: []
last_validated: 2026-11-18
depends_on:
  - artifact: project-preferences
governed_by:
  - artifact: accessibility-spec
    dispositions:
      - "a household reader at standing distance can read every label surface → exception: a dated stopgap, expiring 2027-01-17, recorded in the norm's own entry, at the owner's ruling of 2026-11-18"
      - "WCAG 2.1 AA on the curation browser, colour never the sole carrier → inapplicable because this plan changes no screen"
partition: serial, because every chunk is a few files of prose or one test helper, and a brief for any of them would cost more than the chunk.
---

# Build Plan — How agents build here

## What this plan is

The owner's ruling of 2026-11-18 (`.prawduct/owner-rulings.md`) accepted four
recommendations and a stopgap. The evidence for them came from
`prawduct-hook review-stats` and `stats` since 2026-10-15. A body of work took a median of five
review rounds, with a p90 of 8 to 11. Boundary reviews averaged 9.7 findings
against 0.54 for inner ones. Both delegated branches of the last cycle took a
second round, for reasons a brief could have prevented.

## Goals

- **Response taken:** proceed, citing the owner's ruling.
- **The goal they serve:** fewer review rounds on agent-built work, and a green
  that means what it says.
- **Out of scope:** changing the Critic's rigor by stage, which is prawduct's,
  not this repo's; and `Inner-loop verification`, which the owner has not been
  asked about. `/prawduct:doctor` proposes it on its next run.
- **Decisions made mid-build:**
  - The owner added, mid-build, that delegates never run heavy integration tests.
    It is in `Delegate verification`, in their words.
  - `holding` waits for a held request by polling `wait_for_timeout`, which pumps
    Playwright's events, rather than reading a clock. The browser suite is outside
    testament's cache anyway, but a clock read in a test helper is the shape #437
    removed. Both `stop()` and `release()` wait, because two tests release
    straight after a click.

## Chunks

### Chunk 01: The delegation policy, the stopgap, and #432

- **Type:** code
- **Deliverables:**
  - the `Delegation` and `Delegate verification` rows in
    `.prawduct/artifacts/project-preferences.md` § Workflow, and their one row in
    the norm index;
  - a `Stopgap:` field on norm 1 of `.prawduct/artifacts/accessibility-spec.md`
    § Direction;
  - `holding` in `arrt/tests/browser/test_editing_a_wall.py`: `stop()` and
    `release()` wait until a request has been held. It fixes #432 and the same
    race in the three tests that share the helper.
- **Tests:** the governance suite, which reads the norm index; the browser file
  `arrt/tests/browser/test_editing_a_wall.py`. #432's race is shown red against
  the old `stop()` with every fetch delayed by 300 ms, and green with the new
  one.

### Chunk 02: Learnings and CLAUDE.md

- **Type:** cumulative-final
- **Deliverables:**
  - `.claude/rules/learnings/core.md`: three rules that each restate "a check
    that cannot fail" become one, now that the delegation policy asks for the
    evidence. The rule on testing through the caller stays its own, because its
    mutation step is a different technique;
  - `CLAUDE.md`: the curation-suite, `uv sync` and root-suite paragraphs move to
    `docs/testing.md`, and CLAUDE.md keeps each rule as a one-line instruction;
  - the two flaky browser tests seen 2026-11-18 filed through the backlog.
- **Tests:** the governance suite, which holds the citation and learnings
  checks.
