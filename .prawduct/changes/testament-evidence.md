---
schema: 1
type: chore
scope: testament-evidence
date: 2026-11-18
title: Test evidence comes from the testament run; one more session file ignored
---
The evidence hook's `test_commands` in `.prawduct/project-state.yaml` is now one entry,
`testament run --junit-xml {junit_xml}`, in place of the three local pytest invocations
(owner, 2026-11-18, approving prawduct's `testament-evidence` advisory). Testament runs every
suite `.testament.toml` declares. A run made through the recorder is then both the verification
and the evidence, where before the recorder ran the suites again locally after the testament run
that verified them (a separate `testament run` is still a second run unless its report is
ingested with `--from-junit`). The evidence now includes the browser suite, which the old
commands never ran. Where no runner answers, testament runs the same suites on this machine.
`project-preferences.md` § Testing says so, and a governance test holds every `tests_dirs` root
to a suite in `.testament.toml`, so a suite dropped from the manifest cannot drop out of the
evidence unnoticed.

`.gitignore` adds `.prawduct/.session-activity.json`, a prawduct session file (owner,
2026-11-18, approving the `gitignore` advisory).

## Consumer note
none: how this repo records test evidence, not anything the server or the contract exposes.
