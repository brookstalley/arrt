---
schema: 1
type: chore
scope: ci-on-testament
date: 2026-11-18
title: CI runs on testament's pool
---
The owner's ruling of 2026-11-18 (`owner-rulings.md`): use testament, and no heavy
builds on GitHub's runners. A pull request push cost about 51 runner-minutes.

- **`tests.yml`:** one Actions job per pull request. It lints (ruff and black only,
  one command a line so any failure ends the step), installs testament from the pool's
  console with the CI key, and runs every suite with `testament run --no-fallback`,
  retrying once when the pool says to. `assert_tests_ran.py` fails it on any skip that
  is not an expected failure, and on any suite `.testament.toml` declares that ran
  nothing. A check allowlists the run's flags, so no spelling of `--suite`, `--area`
  or a path can narrow it. The key is the `TESTAMENT_KEY` secret,
  and the coordinator and console are repository variables.
- **`image.yml`:** the server image's test target, built only when the image's
  environment changes (Dockerfile, interpreter pin, dependency files). A new check
  derives the Dockerfile's `COPY` sources and fails on one the filter does not watch
  and the pool does not run, and on any Dockerfile shape it cannot read. This reduces
  coverage: a source- or test-only change no longer builds the image, and two of the
  three causes of its first red (#386) were in that class. Run it by hand before a
  release.
- **`drift-freshness.yml`:** the drift schedule's freshness check, on a push to `main`
  as before.
- **Retired:** `suites.yml`, `browser.yml`, `.github/scripts/browser_shard.py` and its
  test. Nothing runs on a push to `main` but the freshness check. The curation job's
  `--ignore` checks retire with that job. The manifest checks that every test
  directory is in some suite stay, and now decide what CI covers.
- **`assert_tests_ran.py`** reads testament's xfail shapes (`[<phase>] xfail`, with or
  without a reason, multi-line reasons included) and only that opening, so a skip that
  mentions xfail still fails. It also takes `--suites-from <manifest>` and requires
  each declared suite to run something.

## Consumer note
none: no route, schema, contract or product behaviour changes. CI needs the
`TESTAMENT_KEY` secret and the `TESTAMENT_COORDINATOR` and `TESTAMENT_CONSOLE`
variables.
