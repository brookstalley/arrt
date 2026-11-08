# Release Plan — v0.9.1, Security Patch

**Version:** v0.9.1, a **patch**. The owner asked for it on 2026-11-08 ("yes to the 0.9.1
fix"). It changes no behaviour: it moves Pillow to 13.0.0 and certifi to 2026.10.23 for
their security fixes, ahead of deploying to the NAS. `develop` was at the merge of #411
when this was cut, and held nothing beyond v0.9.0 but that fix.

## Release classification

`check-releasability --release v0.9.1`, run before tagging, listed 1 scope and none
unclassifiable.

**No open issue blocks the release.** brookstalley/arrt has no open issue labelled blocker.

| Scope | Disposition | Blocker |
|---|---|---|
| pillow-13 | ships | |

`pillow-13` has no build plan, and that is expected: a dependency upgrade on its own
branch, reviewed by the Critic and the PR reviewer (#411). Its archived change record says
what moved and why. Arrt Player took the same upgrade in brookstalley/arrt-player#26.

## Release prep

- The `pillow-13` fragment is cut into `.prawduct/change-log-archive/2026-11.md` with
  `release=v0.9.1`.
- The root and `arrt` `pyproject.toml` files and their lockfiles go from 0.9.0 to 0.9.1.
  The contract package keeps `contract-v1.0.0`.
- `project-preferences.md` sets `PR merge: automatic`, by the owner's instruction of
  2026-11-08 ("Please always just merge").

## Rollback

- No schema or stored format changes, so v0.9.0's image opens a catalogue v0.9.1 has used.
- Rolling back reinstates Pillow 12.3.0 and its vulnerabilities; prefer rolling forward.

## Deploy

This merge deploys nothing by itself. The NAS moves to `main` by the homelab runbook
(`deploying-a-new-arrt-release.md`). The Pi is arrt-player's, whose own upgrade is #26.
