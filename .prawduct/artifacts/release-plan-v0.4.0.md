# Release Plan — v0.4.0, Whole-Develop Promotion

**Version:** v0.4.0, a **minor**. The owner asked for the release ("let's release to main",
2026-10-07). It is a minor because it adds new behaviour rather than fixing old: four built-in
image sources (the Met, SMK, navigart, the NGA), the picture store, a look before any Get, and
search grouped by held and not held. `develop` was at `8a337186` when this was cut.

## Release classification

Every release-pending scope ships. `check-releasability --release v0.4.0` enumerates them: 16
entries across 15 scopes.

**Checked against v0.3.0:** none of the 16 entry headings is in the v0.3.0 tree's change log or
its archive. As a control, the three headings tagged `release=v0.3.0` are all found there.

**No open issue blocks the release.** brookstalley/arrt has no blocker label. A title search
for blocker, regression and broken found only three old backlog items (#79, #91, #119), and none
of them is a regression from this work.

**Four scopes have no build plan:** `ci-browser-shards`, `quality-minimum`,
`artifact-manifest-guard` and `static-revalidate`. Each is a small change, and its change-log
entry is its whole record.

| Scope | Disposition | Blocker |
|---|---|---|
| artist-name-identity | ships | |
| nga-source | ships | |
| navigart-source | ships | |
| artist-search-review-fixes | ships | |
| ci-browser-shards | ships | |
| look-before-get | ships | |
| picture-store | ships | |
| search-held-not-held | ships | |
| quality-minimum | ships | |
| smk-source | ships | |
| wanted-pictures | ships | |
| artifact-manifest-guard | ships | |
| met-source | ships | |
| static-revalidate | ships | |
| work-pictures-and-sizes | ships | |

**Nothing is withheld**, so this is a standard whole-develop promotion.

## Release prep

- The 16 release-pending change-log entries are tagged `release=v0.4.0`.
- The three `pyproject.toml` files and their lockfiles go from 0.3.0 to 0.4.0.
- `plan-backfill` archived the 11 shipped build plans. First it refused all 11, because each
  carried `lifecycle: active` in its frontmatter. That key takes only terminal states
  (`completed`, `superseded`), and leaving it out is what marks a plan live. Each plan had copied
  the line from the one before, and no template carries it. Every plan's `## Status` was fully
  ticked before the line was removed.
- `archive-change-log` moved 10 shipped entries to `change-log-archive/2026-10.md`, taking the
  live log from 43KB to 19KB.

## Deploy

The NAS deploy runs separately from this merge, from `develop` `8a337186`, with arrt-sources
`263fc0a` (Tate merged). That build is `arrt-sources:8a337186-263fc0a`. The 0.4.0 version bump
changes no code, so that image is this release's code.
