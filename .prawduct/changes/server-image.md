---
schema: 1
type: fix
scope: server-image
date: 2026-11-18
title: The server image's test target is green, and CI builds it on every pull request
closes: [brookstalley/arrt#386]
---
`arrt/Dockerfile`'s `test` target, the documented way to run the server's suite in the image
the NAS runs, was red, and no CI job built it. On the unfixed tree the new job failed with
4 failed and 3 errors, the issue's first three causes:

- the UX walk's tests import `tools/ux_walk.py`, and `tools/` was not copied into the image;
- the stage ran as root, which reads a file whatever its mode, so the three tests that make
  a file unreadable to prove it is reported failed. It now runs as the app stage's user;
- `test_wall_state_words.py` found `walls.js` by a path that holds only in the repository.
  It now reads it from the server's own `STATIC_DIR`.

The fourth cause, the healthz probe timing out, did not recur on a native amd64 build; it
was emulation on an arm Mac. `suites.yml` gains the job "The server image's test target",
which builds the stage for `linux/amd64` on an amd64 runner with the layer cache in GitHub
Actions, and reads the stage's JUnit report (a `test-report` stage exports it) with
`assert_tests_ran.py`, as the other suite jobs do, so a skip fails it. For that the test stage
installs node, so the four test modules that run the client's own JavaScript run instead of
skipping, and it leaves `tests/browser` uncollected, as the curation job does. The image is
amd64-only (dezoomify-rs ships an x86_64 binary). `deploy/README.md` says so, and that under
emulation on an arm Mac a timed test can fail for that reason alone.

## Consumer note
none: the app stage the NAS runs is unchanged.
