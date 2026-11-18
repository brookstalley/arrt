---
artifact: build-plan
version: 2
scope: ci-on-testament
branch: ci/testament-pool
base: develop
working-branches: []
last_validated: 2026-11-18
depends_on:
  - artifact: project-preferences
  - artifact: observability-strategy
partition: serial, because it is one change to CI, its guard tests and the records that name the workflows, and each part reads the others.
---

# Build Plan — CI runs on testament's pool

## Goals

- **Response taken:** proceed, citing the owner's ruling of 2026-11-18
  (`owner-rulings.md`): "we should be using testament where possible and not doing
  heavy builds. we keep running out of github actions minutes".
- **Measured before:** a pull request push cost about 51 runner-minutes: four browser
  shards (38), the image's test target (7), the curation suite (5), the rest under one.
  About 100 such runs in the 30 days to 2026-11-18.
- **Target:** one thin Actions job per pull request that lints and waits on the pool;
  the Docker build only when the image's inputs change; nothing on a push to `main`
  except the drift-freshness check.
- **Open premise, not settled here:** `brookstalley/arrt` is public, and GitHub does not
  normally bill a public repository's standard runners. If that holds, this change
  saves wall time and the queue rather than the allowance. The per-run `timing`
  endpoint reported 0 even for the private testament repo, so it settles nothing.
- **Decisions made mid-build:**
  - `[DECISION: the image build is filtered by path, and a test derives the
    Dockerfile's COPY sources so the filter cannot fall out of step | the owner ruled
    out heavy builds on every pull request, and the earlier objection to a filter
    (build-plan-server-image.md) was drift between filter and Dockerfile, which the
    derived check now refuses by name | user can veto/override]`
  - `[DECISION: a pull request from a fork fails the pool job with a message naming
    the missing secret, rather than falling back to GitHub's runner | a fallback would
    spend the minutes this change removes, and outside pull requests are not expected
    here | user can veto/override]`
  - `assert_tests_ran.py` learns testament's xfail shape (`[<phase>] xfail: `), because
    testament's JUnit carries no `type` on a `<skipped>`. Measured against a pool run
    of `arrt/tests/unit/test_schedule.py`: the old guard failed it, the new one reads
    `xfailed 1`.

## Chunks

### Chunk 01: The pool workflow, the image filter, and their guards

- **Type:** cumulative-final
- **Deliverables:**
  - new `.github/workflows/tests.yml`, new `.github/workflows/image.yml`, new
    `.github/workflows/drift-freshness.yml`. `suites.yml`, `browser.yml` and the
    browser shard script are retired;
  - `.github/scripts/assert_tests_ran.py` reads testament's xfail shape;
  - `tests/test_default_suite_ci_scope.py`: the pool run is every suite, cannot fall
    back, and is guarded on its own report; the image filter watches every file the
    Dockerfile copies that the pool does not run;
  - the records that named the old workflows.
- **Tests:** the governance suite. Each new check is shown failing on a re-break of
  the real workflow file. The workflow itself is proven by the pull request's own run.
