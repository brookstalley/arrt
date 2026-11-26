---
schema: 1
type: feature
scope: hearsay-tell
date: 2026-11-25
title: Tell Hearsay the museum fetches and searches
---
The plan for #451 and the owner's rulings on how Arrt tells Hearsay
(`build-plan-hearsay-tell.md`; `owner-rulings.md`, "how Arrt tells Hearsay (#451)").
One copy point in the host, with a label in each plugin. A queue on disk fills
before anything is sent, and the owner turns sending on. The backfill is split out
as #454. No code has shipped under this scope yet. Its five chunks follow on
`feat/hearsay-tell` once audit Wave 3 merges, and this record is rewritten as they
land.

## Consumer note
none: the plan and rulings only; nothing a person using Arrt sees has changed yet.
