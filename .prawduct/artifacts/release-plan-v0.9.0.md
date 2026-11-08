# Release Plan — v0.9.0, Whole-Develop Promotion

**Version:** v0.9.0, a **minor**. The owner asked for it on 2026-11-08 ("yep release").
It is a minor because it adds behaviour: Ask reads the household's taste and records
taste the curator states (its scope gains `art_taste` `list` and `set`), discovery's
phase 1 is told the taste and the works already rejected, and review's verdicts become
observed taste. It also carries one fix: the view no longer draws a focus ring round
the page when it opens (#405). `develop` was at `85717226` (the merge of #408) when this
was cut.

## Release classification

Every release-pending scope ships. `check-releasability --release v0.9.0`, run before
tagging, listed 3 scopes and none unclassifiable.

**No open issue blocks the release.** brookstalley/arrt has no open issue labelled blocker.

| Scope | Disposition | Blocker |
|---|---|---|
| taste-in-ask | ships | |
| observed-taste | ships | |
| view-focus-ring | ships | |

**Nothing is withheld**, so this is a standard whole-develop promotion. `view-focus-ring`
has no build plan, and that is expected: it was a small fix on its own branch, reviewed
by the Critic, and its change-log entry records what it changed. #406 (the owner's
direction of 2026-11-08, `agents-and-memory.md`) is documents only and carries no change
record.

## Release prep

- The two change fragments (`taste-in-ask`, `observed-taste`) are cut into
  `.prawduct/change-log-archive/2026-11.md` with `release=v0.9.0`, and the
  `view-focus-ring` change-log entry is tagged `release=v0.9.0`.
- The root and `arrt` `pyproject.toml` files and their lockfiles go from 0.8.0 to 0.9.0.
  The contract package keeps its own version (`contract-v1.0.0`), which this release does
  not change.
- `plan-backfill` archived `build-plan-observed-taste.md`. `build-plan-taste-in-ask.md`
  was archived by hand (`archive-plan --state completed`), because `plan status`
  attributed that branch's cumulative review (`rev-20261108T192801Z-7caeb476`) to Chunk 01
  alone, though the review spanned Chunk 02's commit (`f26b62e6`) too. Its archive stamp
  therefore reads "Chunk 02 not done", which is that attribution and not the work: Chunk 02
  shipped in #407. Seven older plans stay live, as at v0.8.0, each with a chunk still open.

## What the first start does

On its first start, v0.9.0 reads every accept and reject already in the catalogue and
writes an observed judgment for each artist whose verdicts meet the owner's rule (at
least 5, and at least 90% of that artist's verdicts, one way). Taste shows them as "Read
from what you accepted and rejected", each with its counts. They reach Ask and Gets
from then on. The curator overrules one by correcting it on Taste.

## Rollback

- **The catalogue:** v0.9.0 changes no schema. It writes `observed` affinity rows, which
  v0.8.0 already reads and shows. Under v0.8.0 they stay as they are, no longer kept
  current by verdicts, and can be forgotten on Taste.
- **Ask's taste writes:** `stated` rows Ask recorded under v0.9.0 are ordinary stated
  judgments to v0.8.0.
- Nothing else is stored differently, so v0.8.0's image opens a catalogue v0.9.0 has used.

## Deploy

This merge deploys nothing by itself. The NAS moves to `main` by the homelab runbook
(`deploying-a-new-arrt-release.md`). The Pi is arrt-player's, and no contract change
reaches it.
