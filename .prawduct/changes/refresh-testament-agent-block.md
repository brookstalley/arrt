---
schema: 1
type: docs
scope: refresh-testament-agent-block
date: 2026-11-18
title: Refresh the testament agent block in AGENTS.md to v3 (verdict first)
---
The "Running tests" block in `AGENTS.md` is now testament 0.54.0's `testament guide agent-block`
output, agent block v3 (owner, 2026-11-14; brought from v2 to v3 on 2026-11-18). The old copy
told an agent to rerun any exit 2 whose `error.retryable` was true, which can rerun a real red
away. The current block reads `verdict` first and says a `failed` verdict is never retryable.
It adds exit 75, the `not_run` outcome, `report.stopped` and `report.last_failed`, and the
`agent_block` advice. It ends with the version line testament checks. `-x`, `--maxfail` and
`--lf` now run on the pool, and only `--sw` and `--nf` fall back to this machine. `-n` is
dropped and the selection sent to the pool.

Because testament drops `-n`, `CLAUDE.md`'s two `-n0` instructions now say they are
`uv run pytest` runs on this machine: debugging one failure, and every live run, which must
never reach the pool.

## Consumer note
none: agent instructions only.
