# Release Plan — v0.6.0, Whole-Develop Promotion

**Version:** v0.6.0, a **minor**. The owner asked for it ("please pr and merge and get to
main", 2026-10-16). It is a minor because it adds behaviour and API: the Work page shows and
chooses the mat, with new `GET`/`POST /api/works/{id}/mat` routes, a `preset` argument on
`art_catalogue set_mat_color` and a new stored `MatMethod.DERIVED`. `develop` was at
`ede86ba3` (the merge of #380) when this was cut.

## Release classification

Every release-pending scope ships. `check-releasability --release v0.6.0`, run before
tagging, listed 1 entry in 1 scope and no unclassifiable entry.

**No open issue blocks the release.** brookstalley/arrt has no open issue labelled blocker.

| Scope | Disposition | Blocker |
|---|---|---|
| ui-mat-selection-labels | ships | |

**Nothing is withheld**, so this is a standard whole-develop promotion.

## Release prep

- The release-pending change-log entry is tagged `release=v0.6.0`.
- The three `pyproject.toml` files and their lockfiles go from 0.5.0 to 0.6.0.
- `arrt/uv.lock` takes mcp 1.28.1 → 1.30.0, the fix for Dependabot alert #76 (medium:
  unbounded session accumulation in the Streamable HTTP transport, which is what `/mcp`
  serves). The upgrade is held below 2: an unconstrained `--upgrade-package mcp` resolves
  2.3.0, a major that swaps httpx for httpx2 and adds `mcp-types`, which is not a
  release-time change. The 1.30.0 lock changes no other package. The curation suite passed
  against it (5286 passed, 1 xfailed), and so did the browser suite's MCP and Ask tests
  (66 passed). `arrt-player` and the root project do not depend on mcp.
- `plan-backfill` archived `build-plan-ui-mat-selection-labels`. It left the same three
  plans live as v0.5.0 did, each with an unticked operator chunk: `display-state`,
  `displays-and-label-outputs` and `walls-work-and-trust`.

## Rollback

A build before this one fails on `mat_colors.method = 'derived'` rows. The change-log entry
gives the rewrite to run first.

## Deploy

This merge deploys nothing. The NAS and the Pi are moved to a revision separately, as
described in the deploy runbooks.
