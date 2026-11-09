---
schema: 1
type: feature
scope: unattended-settings
date: 2026-11-09
title: Household settings, stored and changed at runtime, from the browser or over MCP
---

`agents-and-memory.md` item 4, first half (`build-plan-unattended-settings.md`).

**Chunk 01, the settings store.** Settings are declared once, in `SETTINGS`
(`library/services/settings.py`), and stored in a new `settings` table in the
catalogue file. A setting's value is the environment's if it gives one, which
locks the setting; otherwise the stored value; otherwise the default. Each is
read when used, so a change applies with no restart. `GET /api/settings`,
`POST /api/settings/{key}` and a new MCP tool, `art_settings` (`list`, `set`),
read and change them in the same fields. `LABEL_UNITS` is the first setting:
`LibraryFacade` asks for it at each label build. `.env.example` no longer sets
it.

## Consumer note

Arrt's settings can now be changed while it runs, from the browser or by an
agent over MCP. **If your environment sets `LABEL_UNITS`, that setting is now
locked to it**, and Arrt says so where you would change it. Remove it from your
env file to choose the units in Arrt instead. The new table is ignored by an
earlier release, so rolling back needs nothing.
