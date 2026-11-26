---
schema: 1
type: governance
scope: prawduct-advisories-2026-11-25
date: 2026-11-25
title: The current unloaded-plugin tripwire, a session-temp ignore, and the Hearsay ruling
---
Two advisories from prawduct v3.10.0's session briefing, repaired with prawduct's own commands
after the owner approved each one, plus a ruling.

- **`.claude/settings.json`:** `prawduct-hook install-tripwire --apply` replaced the stale
  SessionStart tripwire with the current copy, keeping every other key. The new copy also
  warns when a settings file's `enabledPlugins` switches prawduct off for this repo, so that
  session no longer runs ungoverned and silent.
- **`.gitignore`:** `prawduct-hook update-gitignore` added `.prawduct/**/*.prawduct.tmp`,
  the one session-file entry the contract was missing.
- **`owner-rulings.md`:** the 2026-11-25 ruling that Arrt contributes its museum records and
  what discovery learns to Hearsay, starting soon, with Hearsay keeping the data until
  after its music demo. No code follows from it yet.

## Consumer note
none: governance configuration and a recorded ruling; no route, schema, contract or product behaviour changes.
