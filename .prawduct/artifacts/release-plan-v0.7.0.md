# Release Plan — v0.7.0, Whole-Develop Promotion

**Version:** v0.7.0, a **minor**. The owner asked for it ("pr and merge to develop, release to
main, and get the nas back on main", 2026-10-28). It is a minor because it adds behaviour and
API: scenes (`/api/scenes`, `art_display` scene actions), renaming a wall
(`POST /api/walls/{id}`, `rename_wall`), and the Walls page rebuilt. It also removes the Player
from this repository, which now lives in brookstalley/arrt-player. `develop` was at
`5954de74` (the merge of #392) when this was cut.

## Release classification

Every release-pending scope ships. `check-releasability --release v0.7.0`, run before
tagging, listed 4 entries in 3 scopes and no unclassifiable entry.

**No open issue blocks the release.** brookstalley/arrt has no open issue labelled blocker.

| Scope | Disposition | Blocker |
|---|---|---|
| wave-4f-scenes | ships | |
| wave-5-split | ships | |
| ui-pass-walls | ships | |

**Nothing is withheld**, so this is a standard whole-develop promotion.

## Release prep

- The release-pending change-log entries are tagged `release=v0.7.0`.
- The root and `arrt` `pyproject.toml` files and their lockfiles go from 0.6.0 to 0.7.0. The
  contract package keeps its own version (`contract-v1.0.0`), which this release does not change.
- `plan-backfill` archived nothing. Six plans whose scopes have shipped stay live, each with
  chunks still open: `display-state`, `displays-and-label-outputs` and `walls-work-and-trust`
  (as at v0.6.0), plus `wave-4f-scenes` (the scenes walk), `ui-pass-walls` (the Walls walk) and
  `wave-5-split`. Backfill reads each plan's Status boxes, which for `wave-5-split` and
  `ui-pass-walls` chunk 02 were never ticked, so it counts more open chunks there than
  `plan status` does. The walks are the reason these plans stay live.

## Rollback

- **Scenes:** an older build fails on `scene.applied` and `scene.ended` History rows. The
  wave 4f change-log entry gives the delete to run first.
- **The catalogue:** the NAS already runs develop `1a1af8a3`, which migrated the catalogue on
  open. The image before that (`75770fe8`) can't open the migrated catalogue. The copy taken
  before that deploy is in the NAS backups.

## Deploy

This merge deploys nothing by itself. The NAS is moved to `main` by the homelab runbook
(`deploying-a-new-arrt-release.md`). The Pi is arrt-player's.
