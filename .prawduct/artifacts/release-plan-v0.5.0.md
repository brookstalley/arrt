# Release Plan — v0.5.0, Whole-Develop Promotion

**Version:** v0.5.0, a **minor**. The owner asked for the release ("Let's get everything PR'd
to develop and main", 2026-10-16). It is a minor because it adds new behaviour: the Arrt / Arrt
Player split through wave 4g (manifest major 2, Programming's schedule, the Player composing
major 2 works), Ask as an agent, the wall label redesign, three more built-in sources (Yale,
the Getty, the Rijksmuseum), and the second UX walk. `develop` was at `55205ca8` when this
was cut.

## Release classification

Every release-pending scope ships. `check-releasability --release v0.5.0`, run before tagging,
listed 61 entries across 35 scopes and no unclassifiable entry.

**No open issue blocks the release.** brookstalley/arrt has no open issue labelled blocker.
A title search for blocker, regression and broken found four items (#48, #91, #119, #301). All
four are backlog work, and none is a regression from this work.

**Ten scopes have no build plan:** `flaky-tests`, `ask-card-get-trim`, `ask-card-pictures`,
`ask-card-payloads`, `feature-label-units`, `fix-epaper-single-refresh`,
`fix-324-discovery-thread-teardown`, `fix-181-gpio-shim`, `feeds-and-players` and
`wall-screen-state`. Each one is a fix, a design record or a follow-up to a planned scope, and
its change-log entry is its whole record.

| Scope | Disposition | Blocker |
|---|---|---|
| ux-second-walk | ships | |
| shown-record | ships | |
| household-schedule-lock | ships | |
| wall-shape-filter | ships | |
| wall-rotation-settings | ships | |
| flaky-tests | ships | |
| get-page-and-debug-view | ships | |
| feed-follows-theme | ships | |
| wave-4g-cutover | ships | |
| wave-4e-schedule | ships | |
| wave-4d-compositing | ships | |
| ask-card-get-trim | ships | |
| ask-card-pictures | ships | |
| ask-card-payloads | ships | |
| ask-agent | ships | |
| wave-4c-wall-loop | ships | |
| wave-4b-master-quality | ships | |
| wave-4a-contract | ships | |
| rename-arrt-player | ships | |
| get-and-review-clarity | ships | |
| feature-label-units | ships | |
| wall-label | ships | |
| fix-epaper-single-refresh | ships | |
| fix-324-discovery-thread-teardown | ships | |
| fix-181-gpio-shim | ships | |
| displays-and-label-outputs | ships | |
| lists-settings-and-scale | ships | |
| feeds-and-players | ships | |
| display-state | ships | |
| walls-work-and-trust | ships | |
| wall-screen-state | ships | |
| ux-walkthrough | ships | |
| rijksmuseum-source | ships | |
| getty-source | ships | |
| yale-source | ships | |

**Nothing is withheld**, so this is a standard whole-develop promotion.

## Release prep

- The 61 release-pending change-log entries are tagged `release=v0.5.0`.
- The three `pyproject.toml` files and their lockfiles go from 0.4.0 to 0.5.0.
- `arrt-player/uv.lock` takes multidict 6.7.1 → 6.9.1. Dependabot alert #75 (medium) is
  reported against `postarr/uv.lock`, which exists only on `main` and is removed by this merge.
  `arrt-player/uv.lock` was its renamed successor and pinned the same vulnerable version, so
  without this bump the alert would come back against the new path. multidict reaches the
  Player through aiohttp, which the Player and samsungtvws both depend on. The lock changes no other package version.
- `plan-backfill` archived 22 shipped build plans. It left three live, each with one unticked
  operator chunk that still needs someone at the wall: `display-state` (Chunk 05, On the wall),
  `displays-and-label-outputs` (Chunk 07, On the wall) and `walls-work-and-trust` (Chunk 13, Walk
  and re-photograph). Their scopes ship. The plans stay live until those walks are done.
- `archive-change-log` moved 54 shipped entries to `change-log-archive/2026-10.md`, taking the
  live log from 145KB to 15KB.

## Deploy

This merge deploys nothing. The NAS and the Pi are moved to a revision separately, as described
in the deploy runbooks. The version bump and the multidict lock are the only changes beyond
`develop`'s code.
