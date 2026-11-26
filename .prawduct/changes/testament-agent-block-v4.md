---
schema: 1
type: docs
scope: testament-agent-block-v4
date: 2026-11-26
title: Refresh the testament agent block in AGENTS.md to v4 (retries and flaky passes)
---
The "Running tests" block in `AGENTS.md` is now the current `testament guide agent-block` output,
agent block v4, replacing v3 (owner, 2026-11-26). Every testament run had printed an
`agent_block` advice line until this was done. The repo's v3 copy had no additions of its own,
so the block is swapped whole.

v4 adds:
- `--retry-failed` (or `[retry] failed = 1`), which retries each failed test once on another
  runner;
- the `passed_flaky` verdict reason and `report.flaky`, for a test that passed only on its
  retry, and `report.retry`;
- the `retry_flaky` advice kind.

It says a flaky test is reported to the person and never rerun away, and a test that fails both
attempts is a real red. This repo turns on no retry; the block only describes the option.

## Consumer note
none: agent instructions only.
