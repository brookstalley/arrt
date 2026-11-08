# Release Plan — v0.8.0, Whole-Develop Promotion

**Version:** v0.8.0, a **minor**. The owner agreed to it on 2026-11-08. It is a minor
because it adds behaviour and API: deleting a wall (`DELETE /api/walls/{wall_id}` and the
`art_display` action that does the same), and Artworks, a work's page, Settings › Players,
Themes and a theme's page all rebuilt to the page rules. It also carries two fixes: the
hanging badge's race, and Walls' *Edit…* and *Scene…* reading what is true at the moment
they are pressed (#400). `develop` was at `132d06b0` (the merge of #401) when this was cut.

## Release classification

Every release-pending scope ships. `check-releasability --release v0.8.0`, run before
tagging, listed 6 entries in 6 scopes and no unclassifiable entry.

**No open issue blocks the release.** brookstalley/arrt has no open issue labelled blocker.

| Scope | Disposition | Blocker |
|---|---|---|
| delete-a-wall | ships | |
| walls-stale-edit | ships | |
| ui-pass-themes-players | ships | |
| ui-pass-work-artworks | ships | |
| fix-hanging-badge-race | ships | |
| install-tripwire | ships | |

**Nothing is withheld**, so this is a standard whole-develop promotion.

Three scopes have no build plan, and that is expected: `walls-stale-edit` and
`fix-hanging-badge-race` were small fixes on their own branches, each reviewed by the
Critic, and `install-tripwire` is one hook in `.claude/settings.json` that ships no
product code. Each change-log entry records what it changed.

## Release prep

- The release-pending change-log entries are tagged `release=v0.8.0`.
- The root and `arrt` `pyproject.toml` files and their lockfiles go from 0.7.0 to 0.8.0. The
  contract package keeps its own version (`contract-v1.0.0`), which this release does not
  change.
- `plan-backfill` archived nothing, because it archives only plans whose scopes a release
  has already recorded. Three plans for this release (`delete-a-wall`,
  `ui-pass-themes-players`, `ui-pass-work-artworks`) stay live until a backfill after this
  tag, and each also still owes the owner's walk in `operator-verification.md`. Six earlier
  plans stay live for the same reason as at v0.7.0: each has a chunk still open.
- The release also carries one accepted PR-review note: a redundant history sentence is
  deleted from `arrt/src/arrt/http/static/core/hanging.js`'s header comment. Only the
  comment changes.

## Rollback

- **Deleted walls:** a wall deleted under v0.8.0 stays deleted under v0.7.0. The rows that
  named it were removed or cleared in the same transaction. A catalogue that has no walls
  left gets the default wall reseeded by v0.7.0 when it opens, because v0.7.0 reseeds
  whenever the table is empty. The migration has no schema change to undo.
- **The catalogue:** v0.8.0 adds no migration, so v0.7.0's image opens a catalogue that
  v0.8.0 has used.

## Deploy

This merge deploys nothing by itself. The NAS moves to `main` by the homelab runbook
(`deploying-a-new-arrt-release.md`). The Pi is arrt-player's.
