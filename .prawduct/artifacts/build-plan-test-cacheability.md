---
artifact: build-plan
version: 1
scope: test-cacheability
branch: perf/test-cacheability
base: develop
working-branches: []
partition: one delegate (Opus-class, in an isolated worktree) builds 01 and 02. They are disjoint, but each is smaller than a second brief would cost. The coordinator integrates on perf/test-cacheability, runs the full suite and the Critic. A second delegate works on #374 at the same time on fix/household-mixed-paces and owns arrt/src/arrt/programming/ and the schedule tests, so this plan leaves them alone.
depends_on:
  - artifact: architecture
last_validated: null
---

# Build Plan — More tests reusable from testament's cache

## What this plan is

#435, a priority for the owner (2026-11-18). Testament reuses a passing test's result
when nothing it reads has changed, but only for a test that reads no clock, randomness,
subprocess or socket. On tree 5da22dd3: 0 of 486 governance tests and 2718 of 5758 curation
tests were cacheable. `testament cacheability --offline` lists the causes, and
`testament guide project` says what each cause means and how to clear or decline it.

## Goals

- **Response taken:** proceed, citing #435, which names the causes and the way to fix
  them.
- **Measurable:** more cacheable tests in the governance and curation suites, counted by
  `testament cacheability --offline` before and after.
- **Tests never weaken.** A cause is cleared by:
  - passing the time or randomness in;
  - freezing it in the test;
  - moving an import-time or hook-time subprocess into the test or fixture that needs it.
  
  Never by dropping an assertion. A cause that is the test's point (a test that runs node
  or dezoomify-rs) is declined with its reason, as `testament guide project` describes,
  not removed.
- **Production behaviour is unchanged.** Passing a clock in keeps today's default.
- **Out of scope:**
  - the browser suite, which is a live server and Chromium by design;
  - `arrt/src/arrt/programming/` and its tests, whose randomness in `schedule.py:build`
    waits until #374 merges.
- `[DECISION: no new test dependency (freezegun, time-machine) unless a cause cannot be
  cleared without one, and then it is named in the report | a dependency is a decision for
  the owner, and most causes take a parameter | coordinator's call]`

## Chunks

### Chunk 01: The governance suite

- **Type:** code
- **What:** `projects` in `tests/repository.py` and `_tracked` in
  `tests/preferences/test_citations_resolve.py` start a subprocess at import or in a hook. That taints every test in the process. Move
  each into the test or fixture that needs it. Then work down the per-test subprocess causes
  where a cheaper read exists.
- **Done when:** the governance suite passes, and its cacheable count has risen.

### Chunk 02: The curation suite

- **Type:** cumulative-final
- **What:** the clock and entropy causes, largest first:
  - `arrt/src/arrt/persistence/kept.py` (`KeptAnswers.__init__`, `_write`, `Kept.get`);
  - `observe` in `arrt/src/arrt/observations.py`;
  - `arrt/src/arrt/library/services/pictures.py` (`PictureStore._write`, `PictureStore.<lambda>`);
  - `arrt/src/arrt/library/sources/loading.py` (`SourceRoster`);
  - `arrt/src/arrt/persistence/backup.py`.
  
  The node and dezoomify subprocess tests are declined with their reasons, or cleared if
  testament offers a way to.
- **Done when:** the affected tests pass, and the curation cacheable count has risen. The
  full suite passes on the integration branch, and the Critic's cumulative review finds
  nothing blocking.
