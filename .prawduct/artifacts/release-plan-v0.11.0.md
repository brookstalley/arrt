# Release Plan — v0.11.0, Whole-Develop Promotion

**Version:** v0.11.0, a **minor**. The owner asked for it on 2026-11-13 ("Yes push and
merge and deploy"). It is a minor because the contract Arrt owns gains a field: heartbeat
minor 5, `capabilities.media`, released as `arrt-contract` 1.1.0 and tagged
`contract-v1.1.0` on the merge of #427 (#424's heartbeat half, #426). It also carries the
owner's rulings on that minor (#427) and the move of the change record to fragments, the
governance anchor to `AGENTS.md` and chunk status to review facts (#423). `develop` was at
`45b07238` (the merge of #427) when this was cut.

**The server's code is unchanged since v0.10.0.** `git diff v0.10.0..45b07238 -- arrt/src`
is empty, and so is the same diff of `deploy/README.md`. The server accepted a minor 5
heartbeat before this release too: of `capabilities` it checks only that it is an
object and that `screen` is readable (`programming/manifest/heartbeat.py`), and nothing in
`media`; the curation suite's `test_player_surface.py` posts every valid heartbeat
fixture, the two minor 5 ones included, to the real route.

## Release classification

Every release-pending scope ships. `check-releasability --release v0.11.0`, run before
tagging, listed 3 scopes and none unclassifiable.

**No open issue blocks the release.** brookstalley/arrt has no open issue labelled blocker.

| Scope | Disposition | Blocker |
|---|---|---|
| player-media-capability | ships | |
| media-capability-rulings | ships | |
| prawduct-upkeep | ships | |

**Nothing is withheld**, so this is a standard whole-develop promotion.
`media-capability-rulings` and `prawduct-upkeep` have no build plan, and that is expected:
each was a governance chore on its own branch, reviewed by the Critic, and its change
record says what it changed.

## Release prep

- The three change fragments are cut into `.prawduct/change-log-archive/2026-11.md` with
  `release=v0.11.0`.
- The root and `arrt` `pyproject.toml` files and their lockfiles go from 0.10.0 to 0.11.0.
  The contract package is already 1.1.0, released as `contract-v1.1.0`.
- `plan-backfill` archived `build-plan-player-media-capability.md`. It refused six older
  plans, as at v0.10.0, each with one chunk still open, the operator's walk:
  `display-state` 05, `displays-and-label-outputs` 07, `ui-pass-walls` 05,
  `walls-work-and-trust` 13, `wave-4f-scenes` 03 and `wave-5-split` 06. They stay live.

## Before deploying

`deploy/README.md` has no new dated section for this release. Nothing to do before
deploying. The Pi is arrt-player's, and it may pin `contract-v1.1.0` before or after this
deploy (arrt-player#31).

## Rollback

v0.11.0 adds no table, column or setting, so v0.10.0's image runs on the catalogue as
v0.11.0 leaves it.

## Deploy

This merge deploys nothing by itself. The NAS moves to `main` by the homelab runbook
(`deploying-a-new-arrt-release.md`).
