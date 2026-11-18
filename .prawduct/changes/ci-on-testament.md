---
schema: 1
type: chore
scope: ci-on-testament
date: 2026-11-18
title: CI runs on testament's pool
---
The owner's ruling of 2026-11-18 (`owner-rulings.md`): use testament, and no heavy
builds on GitHub's runners. A pull request push cost about 51 runner-minutes.

- **`tests.yml`:** one Actions job per pull request. It lints, installs testament from
  the pool's console with the CI key, and runs every suite with `testament run
  --no-fallback`, retrying once when the pool says to. `assert_tests_ran.py` fails it
  on any skip that is not an expected failure. The key is the `TESTAMENT_KEY` secret,
  and the coordinator and console are repository variables.
- **`image.yml`:** the server image's test target, built only when a file the image is
  built from changes. A new check derives the Dockerfile's `COPY` sources and fails on
  one the filter does not watch and the pool does not run.
- **`drift-freshness.yml`:** the drift schedule's freshness check, on a push to `main`
  as before.
- **Retired:** `suites.yml`, `browser.yml`, `.github/scripts/browser_shard.py` and its
  test. Nothing runs on a push to `main` but the freshness check. The curation job's
  `--ignore` checks retire with that job. The manifest checks that every test
  directory is in some suite stay, and now decide what CI covers.
- **`assert_tests_ran.py`** reads testament's xfail shape, `[<phase>] xfail: `, and
  only that exact opening, so a skip that mentions xfail still fails.

## Consumer note
none: no route, schema, contract or product behaviour changes. CI needs the
`TESTAMENT_KEY` secret and the `TESTAMENT_COORDINATOR` and `TESTAMENT_CONSOLE`
variables.
