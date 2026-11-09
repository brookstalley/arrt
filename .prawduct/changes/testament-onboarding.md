---
schema: 1
type: chore
scope: testament-onboarding
date: 2026-11-09
title: The suites run on the household's testament pool
---

`.testament.toml` runs Arrt's four suites on the pool: governance (the root),
curation, contract, and the browser suite on the runners labelled `chrome`. Each
runs from the repo root against its own project's environment, because a pytest
suite cannot set a working directory (brookstalley/testament#546). They run in a
new test image, `.devcontainer/Dockerfile`, not the deploy image: that one builds
from `arrt/` and runs its tests as root, which testament refuses (#386). The test
image carries Python, Node (for the client-parsing checks, which otherwise skip)
and Playwright's Chromium at the version `arrt/uv.lock` pins, which a root test
holds. `AGENTS.md` carries testament's agent instructions; `CLAUDE.md` points
there. The live suites stay on this machine.

Measured 2026-11-09 on the pool: governance 475 passed, contract 223 passed,
curation 5,452 passed (the 95 Node-only checks that skipped on the first run then
passed with Node in the image), browser 1,451 passed in about 4 minutes.
