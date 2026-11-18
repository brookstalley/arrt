---
artifact: build-plan
version: 1
scope: server-image
branch: fix/server-image-test-target
base: develop
working-branches: []
partition: serial, one worktree. One chunk, too small to hand to a second builder.
depends_on:
  - artifact: architecture
last_validated: null
---

# Build Plan — The server image's test target is green, and CI builds it

## What this plan is

#386. `arrt/Dockerfile`'s `test` target is the documented way to run the server's
suite in the image the NAS runs. On 2026-10-26 it was red for four reasons, and no CI
job built the image, so nothing noticed. This plan adds the CI job first, watches it
fail against the unfixed tree, then fixes each cause.

## Goals

- **The test target passes** in the image as built for the NAS (amd64).
- **CI builds it on every pull request**, so a change that breaks the image is caught at
  review, not at deploy.
- **The app stage is unchanged** apart from what the fixes need: the NAS runs it.

Inferences:

- `[DECISION: the job lives in suites.yml, on every pull request, not in a workflow
  filtered by path | a path filter would have to track every file the Dockerfile
  copies, and would stop catching breaks once it fell out of step with them | builder's
  call]`
- `[DECISION: CI builds linux/amd64 on an amd64 runner | the image is amd64-only:
  dezoomify-rs ships an x86_64 binary, so a native arm64 build fails at its install
  step (measured 2026-11-18). An amd64 runner needs no emulation, which is what made the
  healthz probe time out in the 2026-10-26 run | builder's call]`

## Chunks

### Chunk 01: The CI job, and the four causes fixed

- **Type:** cumulative-final
- **What:** a `suites.yml` job builds `--target test`. Watch it fail on the unfixed
  tree. Then: copy `tools/` into the test stage; run the test stage as an unprivileged
  user, so a file chmod-ed unreadable cannot be read; give `test_wall_state_words.py` a
  path that holds in the image as well as in the repository; and see whether the healthz
  timeout survives a native amd64 build before budgeting it.
- **Done when:** the CI job is red on the unfixed tree with the issue's causes and green
  after the fixes; all four suites pass through testament; the Critic's cumulative
  review finds nothing blocking.
