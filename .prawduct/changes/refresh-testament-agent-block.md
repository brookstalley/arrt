---
schema: 1
type: docs
scope: refresh-testament-agent-block
date: 2026-11-14
title: Refresh the testament agent block in AGENTS.md (verdict first)
---
The "Running tests" block in `AGENTS.md` is now testament 0.49.0's `testament guide agent-block`
output (owner, 2026-11-14). The old copy told an agent to rerun any exit 2 whose `error.retryable`
was true, which can rerun a real red away. The current block reads `verdict` first, adds exit 75
and the frozen exit codes, and says to keep one envelope per run. Nothing outside the block changed.

## Consumer note
none: agent instructions only.
