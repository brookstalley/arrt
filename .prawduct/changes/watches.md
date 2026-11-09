---
schema: 1
type: feature
scope: watches
closes: [brookstalley/arrt#417]
date: 2026-11-09
title: Watches, standing requests Arrt runs on a schedule with nobody watching, and the scheduler that runs them
---

`agents-and-memory.md` item 4, second half (`build-plan-watches.md`), on the
owner's four answers of 2026-11-09: review only, only verdicts shape taste,
browser-only alerts, a cadence and a cap per Watch.

**Chunk 01, the records Watches owed.** `security-model.md` § Prompt Injection
is re-derived for unattended runs (§ The unattended trigger fired): auto-accept
is not offered, a Watch's run holds no verdict tool, and an agent writing a
Watch over MCP is the new path, bounded by the budget and traced by its surface.
`observability-strategy.md`'s push-alert revisit is answered (browser only).

**Chunk 02, a set-aside setting says so (#417).** A stored setting this release
or deployment no longer allows reads as `source` `set_aside` with a
`set_aside_reason`, on the route, over MCP and on Settings › General, and is
logged once per value.

**Chunk 03, Watches stored.** A `watches` table and `discovery_runs.watch_id`,
`WatchService`, `GET/POST /api/watches`, `GET/POST/DELETE /api/watches/{id}`,
and a new MCP tool, `art_watches`. Each write records its surface.

**Chunk 04, the scheduler.** One Library thread, a pass every five minutes,
logging `scheduler.pass` every time. Each due Watch is weighed against the
unattended allowance and its cap, counting what the pass has already started,
and started as an ordinary discovery run, `initiated_by` `unattended`, on the
unattended model; a refusal is stored with its reason. A Watch's run is in
flight only while the runner holds it, so a deployment with no image search
does not hold its Watch for ever. A Watch whose run failed is tried again
within the hour; a server down for days runs a Watch once, not once per missed
slot.

**Chunk 05, Settings › Watches.** A page under Settings, after Sources: a
Watch's words, how often, its cap, on or off, each applied when changed, with
the server's sentence for where it stands, this month's spend, when it is next
due and its last Get; *Remove…* asks first. A Watch's Get and Review say it was
found by a Watch, and runs list it as *Get from a Watch*. An overdue Watch (an
hour past due with nothing tried) and a spent allowance holding one are named
on the status indicator and on Status. `arrt/tools/ux_walk.py` reached the page
by link from six pages and found it clean at phone and desktop width in both
schemes; it walked the empty page only, and the browser suite covers a Watch's
panel.

## Consumer note

Nothing runs until you turn unattended work on and give it an allowance in
Settings › General, then write a Watch in Settings › Watches. A Watch never
accepts anything: what it finds waits in To review. A household's agent over
MCP can write and switch on Watches (`art_watches`), as it can change settings;
each write says which surface made it. The scheduler starts with the server.
An earlier release ignores the new table and column, so rolling back starts
cleanly and runs no Watches. `GET /api/health` gains `watches`; runs gain
`watch_id`; `WatchOut` is new.
