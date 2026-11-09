---
schema: 1
type: feature
scope: unattended-settings
closes: [brookstalley/arrt#329]
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

**Chunk 02, Settings › General.** A new page under Settings, after Sources,
lists every setting the server declares, each its own control applied when
chosen. A setting the environment gives shows its value and the variable that
sets it, with no control. *Label units* is the first, which closes #329.
`arrt/tools/ux_walk.py` reached it by link and found it clean in both schemes at
phone and desktop width.

**Chunk 03, unattended work's settings and its allowance.** Four settings under
their own heading on Settings › General: *Unattended work* (off until chosen),
*Monthly allowance* (dollars, never above `MONTHLY_BUDGET_USD`), *How often* and
*Model* (empty is the discovery model). `UnattendedAllowance` answers whether a
piece of unattended work may start: off, no model key, or the month's allowance
passed, counting only the spend of runs started `unattended` (a new
`initiated_by`). `GET /api/unattended` and `art_settings(action='unattended')`
say where it stands. Nothing starts unattended work yet: Watches, the next plan,
will ask it first. `arrt/tools/ux_walk.py` walked the section: its
accessibility scan was clean at phone and desktop width in both schemes.

## Consumer note

Arrt's settings can now be changed while it runs, in Settings › General or by
an agent over MCP. **If your environment sets `LABEL_UNITS`, that setting is now
locked to it**, and Arrt says so where you would change it. Remove it from your
env file to choose the units in Arrt instead. The new table is ignored by an
earlier release, so rolling back starts cleanly; but a household that removed
`LABEL_UNITS` from its env file to choose the units here gets the earlier
release's default (imperial) until it sets `LABEL_UNITS` again. Unattended work is off until
you turn it on and give it an allowance; nothing yet runs unattended either way.

Four new environment variables, `UNATTENDED_WORK`, `UNATTENDED_ALLOWANCE_USD`,
`UNATTENDED_CADENCE` and `UNATTENDED_MODEL`, each lock their setting as
`LABEL_UNITS` does; leave them unset to choose in Settings › General.
`.env.example` documents them, commented out. Arrt now refuses to start, naming
the variable, on a `MONTHLY_BUDGET_USD` that is not a number of dollars (NaN,
Infinity) and on an `UNATTENDED_ALLOWANCE_USD` above the month's budget.
