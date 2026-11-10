# Release Plan — v0.10.0, Whole-Develop Promotion

**Version:** v0.10.0, a **minor**. The owner asked for it on 2026-11-09 ("let's release
to main and push to the nas"). It is a minor because it adds behaviour: the taste brief
over MCP and Host and Origin checks on every surface but the Player's (#414), household
settings stored and changed at runtime (#418), and Watches with the scheduler that runs
them (#420). It also carries Ask's spend in the ledger (#415), fixes for tests that
failed now and then and the run-status race behind two of them (#416), and the suites'
move onto the testament pool (#419). `develop` was at `2bc032b7` (the merge of #420)
when this was cut.

## Release classification

Every release-pending scope ships. `check-releasability --release v0.10.0`, run before
tagging, listed 6 scopes and none unclassifiable.

**No open issue blocks the release.** brookstalley/arrt has no open issue labelled blocker.

| Scope | Disposition | Blocker |
|---|---|---|
| mcp-household-agents | ships | |
| ask-spend | ships | |
| flaky-tests | ships | |
| unattended-settings | ships | |
| testament-onboarding | ships | |
| watches | ships | |

**Nothing is withheld**, so this is a standard whole-develop promotion. `ask-spend`,
`flaky-tests` and `testament-onboarding` have no build plan, and that is expected: each
was a fix or chore on its own branch, reviewed by the Critic and the PR reviewer, and its
change record says what it changed.

## Release prep

- `mcp-household-agents.md`'s `closes:` named `53`, which the releasability check refused
  as no backlog ID; it now names `brookstalley/arrt#53`, the issue it closed.
- The six change fragments are cut into `.prawduct/change-log-archive/2026-11.md` with
  `release=v0.10.0`.
- The root and `arrt` `pyproject.toml` files and their lockfiles go from 0.9.1 to 0.10.0.
  The contract package keeps `contract-v1.0.0`, which this release does not change.
- `plan-backfill` archived `build-plan-mcp-household-agents.md`,
  `build-plan-unattended-settings.md` and `build-plan-watches.md`. The older plans it
  refused stay live, as at v0.9.0, each with a chunk still open.

## Before deploying

`deploy/README.md` has two dated sections for this release:

- **§ The names the server answers to (2026-11-08).** The env file must list every name
  a browser or MCP client uses to reach the server in `CURATION_ALLOWED_HOSTS`, the
  reverse proxy's names included, or the browser interface and MCP refuse requests by
  name (`421`). The walls are unaffected either way.
- **§ Ask's spend in the ledger (2026-11-09).** Nothing to do before deploying.

`LABEL_UNITS`, and the four new `UNATTENDED_*` variables, lock their setting when the env
file sets them. Watches run nothing until unattended work is switched on with an
allowance in Settings › General.

## Rollback

- **The catalogue:** v0.10.0 adds the `settings` and `watches` tables and
  `discovery_runs.watch_id`, which v0.9.1 ignores.
- **Ask's spend:** v0.9.1 refuses a spend row in the `ask_tokens` category. Before
  starting v0.9.1's image, run
  `DELETE FROM spend_records WHERE category = 'ask_tokens';` on the catalogue
  (`deploy/README.md` § Ask's spend in the ledger).
- **Settings:** a household that removed `LABEL_UNITS` from its env file to choose units
  in Arrt gets v0.9.1's default (imperial) until it sets `LABEL_UNITS` again.

## Deploy

This merge deploys nothing by itself. The NAS moves to `main` by the homelab runbook
(`deploying-a-new-arrt-release.md`). The Pi is arrt-player's, and no contract change
reaches it.
