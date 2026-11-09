---
artifact: build-plan
version: 2
scope: unattended-settings
branch: feature/unattended-settings
base: develop
working-branches: []
last_validated: 2026-11-09
depends_on:
  - artifact: agents-and-memory
  - artifact: nonfunctional-requirements
  - artifact: data-model
  - artifact: information-architecture
governed_by:
  - artifact: nonfunctional-requirements
  - artifact: data-model
  - artifact: architecture
  - artifact: security-model
  - artifact: information-architecture
  - artifact: api-contract
  - artifact: design-direction
  - artifact: accessibility-spec
partition: serial — every chunk edits the settings service, its route and the Settings › General screen, and Chunk 03 builds on both before it
---

## Goals

**Response taken:** Ask, in one batch, answered 2026-11-09. This is the first half
of `agents-and-memory.md` item 4 ("Unattended agent settings, then Watches"). The
owner's answers, each to an option the advisor put:

- **The unattended allowance is enforced by Arrt**, from the ledger. A second
  OpenRouter key whose limit is the allowance was the advisor's recommendation,
  and it was declined.
- **Item 4 is two plans.** This one carries the settings and the allowance.
  `build-plan-watches.md`, not yet written, carries the scheduler and Watches.
- **The scheduler moves to the Watches plan**, so it is built against its first
  job. Upgrades, the scheduler's other consumer (#177, #178), stay parked.
- **The settings are stored and edited in Settings › General**, not environment
  variables. This builds the runtime settings store #329 asks for, and gives
  `LABEL_UNITS` its control.
- **Settings can be changed over MCP** (the owner, 2026-11-09: "settings can be
  changed by MCP, definitely"). The advisor had proposed browser-only writes and
  that was overruled, so parity holds (`product-brief.md` item 8).

**Product:** a household chooses in the browser whether Arrt may spend on agent
work with nobody watching, and how much a month (ruling 5: "that needs settings
since it can burn tokens unattended"). Unattended work is off until it is chosen,
because other households install Arrt from the public source and nothing in the
defaults may assume this one (`agents-and-memory.md` § What this reverses).
`LABEL_UNITS`, an environment variable with no control today, moves to the same
screen.

**Architecture:**
- The settings store is the Library's. It lives in the catalogue file, and
  Programming reads none of it, so seam rules 1–3 hold. `LABEL_UNITS` is read by
  `LibraryFacade` when a label is built, which is Library work.
- Every setting is declared once, in a typed registry: its name, its type, its
  default, the environment variable that may set it, and its bounds. The service,
  the route, the screen and the tests all read that registry, so a setting cannot
  be added to one and missed by another.
- Each read is made when the value is used, never captured at startup, so a change
  needs no restart (#329's acceptance).
- Ruling 6 holds: no feed, media or Player route reads a setting.

**Constraints:**
- No new dependency.
- No hostnames or addresses, because the repo is public.
- The month is UTC's, matching the provider's reset (`DiscoveryService.spend_in_month`).

**Tradeoffs accepted:**
- **The allowance check, the cadence and the model have no caller until the
  Watches plan.** The check is tested directly; the cadence and the model are
  stored and shown, and the Watches plan is the first to read them. Revisit if
  that plan is not written.
- **App-enforced allowances fail open on a ledger bug.** The owner chose this over
  a second key. The provider's monthly limit still stops the bill, so the hazard
  is overspend inside the $20 ceiling, not past it. #337 (Ask's spend in the
  ledger, `fix/ask-spend`) was the most recent such gap.

**Ruled 2026-11-09** (the owner, "Yes agreed", to the advisor's recommendation):
- **Precedence: the environment wins and locks the control.** A setting given in
  the environment shows its value with "Set by `LABEL_UNITS` in the environment"
  and cannot be changed in the browser or over MCP. A stored value applies only
  where the environment says nothing. Chosen over "stored wins" so that a
  deployment pinned in its env file (the homelab's way) is never silently
  overridden, and a browser change is never silently reverted at the next
  restart. A deployment whose env file still carries the old example's
  `LABEL_UNITS=imperial` finds Label units locked, and removes the line to
  choose it in the browser.

**Inferred, for the owner to veto** (none was ruled):
- **Defaults:** unattended work off; allowance $0.00; cadence once a day; model
  the same as `DISCOVERY_MODEL`'s default. The allowance may not exceed
  `MONTHLY_BUDGET_USD` where one is set.
- **What cadence means before Watches exist:** the longest a Watch may go
  between runs by default. A Watch's own cadence, if it gets one, is the Watches
  plan's question.

**What the MCP ruling costs, recorded so it can be revisited:** an agent on the
LAN, possibly steered by text it read (`security-model.md` § Prompt Injection),
can turn on unattended work and set its allowance. Two bounds remain. The
allowance may not exceed `MONTHLY_BUDGET_USD`, and the provider's key limit still
stops the bill. Every change is logged with the surface that made it, so a
surprise is traceable. The Watches plan's prompt-injection re-derivation must
count this.

`[DECISION: the allowance is budgeting under the spend norm's scope note, not a
second ceiling | nonfunctional-requirements.md: the ceiling stays the provider's
key limit, and "a per-run search cap is application-enforced and does not
depart". The allowance bounds unattended work's share, as that cap bounds one
run's; it is not the thing that stops the bill | owner ruled 2026-11-09 for
Arrt-enforced; user can veto/override]`

**Decisions made mid-build:**
- Chunk 01: the write route is `POST /api/settings/{key}`, not `PUT`. Settled by
  the surface's convention ("this surface writes with `POST` everywhere", `api.py`
  § taste).
- Chunk 01: the table is in the discovery store (`SqliteDiscovery`), beside taste
  and spend, the Library's own. Settled by the seam rules, and Chunk 03's allowance
  reads spend there.
- Chunk 01: a change is logged, not written to `history_events`, whose events are
  a work's and a wall's. Settled by that table's subject; the goals asked for a log
  line at least.
- Chunk 01: `.env.example` no longer sets `LABEL_UNITS`, because copying it would
  lock the new control on every installation. A root test holds that for every
  setting `SETTINGS` declares. The goals did not foresee this.
- Chunk 02: General sits under Settings after Sources and before Taste.
  Settled by the index's own rule ("what the server works with", then "what it
  has come to believe"); Sonarr's General sits near its end. Inferred.
- Chunk 02: each setting carries a `label` from the server, so the screen and an
  agent name it alike. A choice's words ("Metric (centimetres)") are the client's,
  falling back to the value. Settled by "One word per thing".
- Chunk 03: an empty model is the discovery model, rather than a copy of
  `DEFAULT_DISCOVERY_MODEL`, which the settings module cannot import from `config`
  (config imports it), and which would go stale when the discovery model changes.
  Settled by "do it right".
- Chunk 03: cadence is a choice (hourly, daily, weekly), not an interval, until a
  Watch needs finer. Inferred.
- Chunk 03: on/off is a choice spelled `off`/`on`, so it takes the picker every
  choice takes. Settled by the screen's one control per kind.
- Chunk 03: a stored value is held to the deployment's rules when read, so an
  allowance above a budget since lowered reads as $0.00 and is logged. Settled by
  "fails closed" (`nonfunctional-requirements.md`).
- Chunk 03: `GET /api/unattended` and `art_settings(action='unattended')` give the
  standing, which the plan's section needed and did not name a route for.
- After the cumulative review: an allowance spent to the cent refuses a piece with
  no estimate; an allowance past $1,000,000 is refused rather than overflowing;
  `MONTHLY_BUDGET_USD=NaN` is refused by name; a setting's variable is named in its
  refusals by the setting alone; and the UTC month is one function
  (`library/months.py`) that the month's spend and the allowance both count by.

**Level:** Medium. The store and the screen follow patterns the repo already has.
What could move: the defaults and what cadence means are inferred, and the screen
is new to the IA. The precedence rule was ruled on 2026-11-09.

## Governing artifacts, reconciled

| Artifact | Norm | Disposition |
|---|---|---|
| `nonfunctional-requirements.md` | Spend ceilings are the provider's | conforms: the allowance is budgeting (decision above); the key limit is untouched |
| `data-model.md` | Identity is never a source URL | inapplicable because no artwork identity is touched |
| `data-model.md` § `initiated_by` | Not an authorisation input | conforms: `UNATTENDED` is summed for the allowance; no operation branches on it, and every surface may change every setting |
| `architecture.md` | Operation logic only in the service layer | conforms: the route and the MCP read are bindings over `SettingsService` |
| `architecture.md` | Seam rules 1–4 | conforms: a Library store, read by the Library alone |
| `architecture.md` | The manifest is the only channel to display | conforms: no Player reads a setting; label units reach the wall as label text, as today |
| `security-model.md` | Outside text is never parsed as markup | conforms: the screen builds its nodes with `el` |
| `information-architecture.md` | Its Direction (the screen tables bind the client) | conforms: Settings › General is added to the tables before `app.js` routes it (`tests/preferences/test_screen_tables.py`) |
| `design-direction.md`, `accessibility-spec.md` | Their Direction norms | conforms, checked in Chunk 02 by the browser suite and `docs/ux-walkthrough.md` pass 1 |
| `api-contract.md` | Its route rows | conforms: two routes added in Chunk 01 |

**New structural context:** a new storage surface (the settings table). The
cross-cutting concerns land on it as follows:
- **Backup:** it is in the catalogue file, so `VACUUM INTO` already carries it.
- **Migration:** additive, and an older release ignores the table.
- **Observability:** a changed setting is logged at INFO with key, old value, new
  value and surface (a `history_events` row was ruled out mid-build, below).
- **Errors:** an invalid value is refused in the service's words.
- **Auth:** none, per the LAN boundary.

## The questions the stored settings must answer

A persisted format is lock-in, so its readers come first:

1. What is this setting's value now? (every reader, at the moment of use)
2. Where did that value come from: the environment, the browser, or the default? (the screen)
3. When was it last changed, and from which surface? (the screen; anyone tracing a
   surprise in the month's spend)
4. Is unattended work allowed to start now, and if not, why? (the Watches scheduler,
   from the enabled setting, the allowance, and the month's unattended spend)
5. What has unattended work spent this month against its allowance? (the screen;
   `art_discovery(action='spend')` already sums the whole month)

## Chunks

### Chunk 01 — the runtime settings store, its route and its MCP read

Critic mode: final. This is the keystone the other two build on.

- New `arrt/src/arrt/library/services/settings.py`: the typed registry of settings
  and `SettingsService`, with `get`, `describe` (value, source and when changed) and
  `set`. `set` refuses a key that is unknown, a value of the wrong type or out of
  bounds, or a key the environment locks.
- A `settings` table (`key` primary, `value` text, `updated_at`, `updated_by`) in the
  catalogue file, with an additive migration and a test that an older file opens.
- `LABEL_UNITS` moves into the registry. `LibraryFacade` reads it per build instead
  of taking it at construction, and a test changes it between two builds with no
  restart.
- `GET /api/settings` and `POST /api/settings/{key}`, as rows in `api-contract.md`.
- `art_settings(action='list'|'set')`, the same service as the route. Its
  fields are the route's (`test_surface_parity.py`).
- Tests: precedence (environment locks, stored applies, default otherwise), each
  refusal by name, and the facade reading the value it was just given. Each guard
  is watched failing once.

**Done when** the three suites are green, and a label built after `POST
/api/settings/label_units` uses the new units with no restart.

### Chunk 02 — Settings › General

- `information-architecture.md`: a Settings › General row in the screen table and in
  the Settings index, before the client routes it.
- The screen: each setting with its control, its value's source in words, and the
  environment lock said where it applies. `LABEL_UNITS` is the first control.
- Browser tests (`-m browser`, after `uv sync --group browser`): changing units
  changes the next label, and a locked setting cannot be changed and says why.
- Closes #329.

**Done when** the browser suite is green, `arrt/tools/ux_walk.py` reports nothing
new on the screen, and #329's acceptance list is met.

### Chunk 03 — unattended work's settings and its allowance

Type: cumulative-final.

- Four settings in the registry: `unattended_work` (default off),
  `unattended_allowance_usd` (Decimal, at least 0, at most
  `MONTHLY_BUDGET_USD` where set), `unattended_cadence` (hourly, daily or weekly,
  default daily) and `unattended_model` (empty is the discovery model).
- `InitiatedBy.UNATTENDED`, with its row in `data-model.md`: spend is attributed to
  it through its run, the way agent spend is today.
- New `arrt/src/arrt/library/services/unattended.py`: `UnattendedAllowance`, with
  `spent_this_month()` and `standing(estimate)`. The second returns a typed answer
  (`may_start`, and a `Refusal` naming its reason: off, no model key, or the
  allowance spent or about to be passed). Each reason is a sentence for the screen
  and the log.
- Settings › General gains an *Unattended work* section: its four controls, and what
  it has spent this month against the allowance.
- `nonfunctional-requirements.md` § Cost Constraints: the 2026-11-08 Direction note
  says where the allowance is built and how it is enforced.
- Tests: a setting the environment gives locks only itself, now that a second
  setting exists to show it; each refusal reason, the month's boundary in UTC, spend from attended runs
  not counted against the allowance, and an allowance above the monthly budget refused.

**Done when** the three suites and the browser suite are green, the cumulative
review is clean, and the Watches plan can call `may_start` with nothing more built.

## Verification strategy

Run the server against a scratch `ART_ROOT` (`cd arrt && uv run python -m arrt`).
Then, in the browser:
- change label units and read a work's label;
- set an environment value and confirm the control locks;
- turn unattended work on with a small allowance;
- seed an unattended spend row and see the allowance's remaining figure fall.

No model is called by this plan.
