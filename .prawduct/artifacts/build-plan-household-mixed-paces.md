---
artifact: build-plan
version: 1
scope: household-mixed-paces
branch: fix/household-mixed-paces
base: develop
working-branches: []
partition: one delegate (Opus-class, in an isolated worktree) builds 01 then 02, because 02 is the fix for what 01 reproduces. The coordinator integrates on fix/household-mixed-paces, runs the full suite and the Critic. A second delegate works on #435 at the same time on perf/test-cacheability; that one owns nothing under arrt/src/arrt/programming/ or the schedule tests, so the two branches touch no shared file.
depends_on:
  - artifact: architecture
last_validated: null
---

# Build Plan — Walls at mixed paces keep the household rule

## What this plan is

#374. After a household pass (#350, `archive/build-plan-household-schedule-lock.md`), two
walls at different paces that share only two works can still clash, and a three-wall case
is suspected. The household rule: no work on two walls at the same moment
(`re-architecture.md`, wave 4).

## Goals

- **Response taken:** proceed, citing #374. It names the cause (the republished wall is
  built first, against only each neighbour's slot now), the actual behaviour and the
  expected one.
- **Binding rulings, carried from #350:**
  - a republish may rebuild the *slots to come* of every wall that shares a work with it
    (the owner, 2026-10-13);
  - the slot on each wall now is never changed (same ruling);
  - the picture now may linger, but under one more interval (the owner, 2026-10-14).
- **Target:**
  - **Case A:** a republished wall with shorter slots than a neighbour, the two sharing
    two works. It does not clash where a clash-free schedule exists.
  - **Case B:** three walls, A {x, y}, N1 {x, w, v}, N2 {y, w}. Reproduce it first, and
    fix it if it reproduces.
- **Not a target unless the fix covers it as it stands:** intervals that are not multiples
  of each other. The issue's "the household rule holds whenever some schedule satisfies it"
  is the direction. A general guarantee that needs a search over schedules is a new
  requirement, and it comes back as **proposed**, not built.
- **Still holds:**
  - a clash nothing could avoid is still named in the journal;
  - a pass still rebuilds each wall at most once per write;
  - a neighbour that cannot be rebuilt keeps its schedule.

## Chunks

### Chunk 01: Reproduce both cases

- **Type:** code
- **What:** tests in `arrt/tests/unit/test_schedule.py` (or the service tests if the pass
  is only reachable there): one for case A and one for case B. Each is red on the unfixed
  code, or recorded as not reproducing, with why.
- **Done when:** each case is red against `develop`'s code with the clash named, or shown
  not to reproduce.

### Chunk 02: Build the pass so both hold

- **Type:** cumulative-final
- **What:** the fix in `arrt/src/arrt/programming/schedule.py` (and the service that runs a
  pass, if the order lives there): build the pass's walls longest slot first, each against
  the walls already built and the slot now of those still to come, and build neighbours
  against each other where case B needs it. The module docstring's "What a pass cannot do"
  says what remains.
- **Done when:** 01's tests pass, and so do the existing schedule and scheduler tests,
  unchanged. The full suite passes on the integration branch, and the Critic's cumulative
  review finds nothing blocking.
