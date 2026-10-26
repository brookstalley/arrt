---
artifact: build-plan
version: 1
scope: wave-5-split
branch: feature/wave-5-split
base: develop
working-branches: []
partition: serial, one worktree. 01, 02 and 03 all edit the root suite and the three pyproject files, and 03 re-homes guards that 01 and 02 reshape; 04 and 05 run in order across two repos, because 05 deletes what 04 must first prove it carried. 06 is the operator's.
depends_on:
  - artifact: re-architecture
  - artifact: player-contract
  - artifact: architecture
  - artifact: feeds-and-players
  - artifact: project-preferences
governed_by:
  - artifact: re-architecture
    dispositions:
      - "§ Order of work, wave 5 row (two-pass filter-repo over four historical paths; move the root's non-2024 hardware tools into arrt-player/tools first; remove the 2024 root modules; onboard prawduct there; carry the Player's artifacts; pin contract/ with player-contract.md and the major 2 semantic validator; the new repo is arrt-player, this one Arrt) → conforms: 02 moves the tools and removes the modules, 04 runs the measured recipe and its two tree checks, 01 makes the pin a package that carries all three, 05 leaves this repo as Arrt. The pin's form is the owner's ruling of 2026-10-26 (Goals)"
      - "§ Agents (after the split, one session per repo; a Player agent that needs a field files it against the server repo) → conforms: 05 transfers the Player's issues and the contract package lives here, so a field is a change to this repo's package and a version the Player then takes"
  - artifact: architecture
    dispositions:
      - "§ Direction, the only channel to a Player (the Player makes only the requests contract/routes.json names; it imports no server module) → conforms: 03 carries the isolation test's Player half into the Player's own suite, reading routes.json from the package, and keeps the clause that only pull.py opens an HTTP client. After the split the no-server-import clause is true by construction and is still asserted, because a vendored server module would break it silently"
  - artifact: player-contract
    dispositions:
      - "the contract under contract/ is what each side is tested against and what the Player pins → conforms: 01 makes it the `arrt-contract` package; the schemas, fixtures, vectors, routes and `semantic_errors` travel together at one version"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ The television belongs to whoever is using it (no unattended code presses a power key) → conforms: 02 moves tv_api_check.py and tv_delete.py beside power_probe.py, unchanged; nothing new runs unattended"
  - artifact: project-preferences
    dispositions:
      - "merge commits; no attribution trailers; PR merge waits for the owner → conforms, in both repos: 04 copies the preferences into arrt-player at onboarding"
last_validated: 2026-10-26
---

# Build Plan — Wave 5: split the repos

## What this plan is

The last wave of `re-architecture.md` § Order of work before the two products
develop independently. Arrt Player leaves this repository with its history, as
**brookstalley/arrt-player**. This repository, already named `arrt` on GitHub,
keeps the server and becomes Arrt. The contract between them becomes a
published package that the server owns and the Player depends on.

The wave row already says how to extract the history: two passes of
`git filter-repo`, measured on a scratch clone on 2026-10-01. This plan adds what
that row did not settle. It says how the contract is pinned, and which of the
root suite's cross-plane guards survive on which side. It also gives the order
of the work, so that no guard is deleted before its replacement runs green.

Two PRs to `develop` in this repo, one first PR in the new one:

| Chunk | What | Ships in |
|---|---|---|
| 01 | The contract becomes the `arrt-contract` package; every reader goes through it | PR 1 (arrt) |
| 02 | The root is cleared down to governance: hardware tools to `arrt-player/tools`, 2024 modules removed | PR 1 (arrt) |
| 03 | Every cross-plane guard is split by plane, while both planes are still here to prove it | PR 1 (arrt) |
| 04 | Extraction: arrt-player exists, onboarded, green, with the contract from a tag | arrt-player's first PR |
| 05 | Arrt without the Player | PR 2 (arrt) |
| 06 | The wall runs from the new repo (the operator's) | — |

**Not in this plan:**
- Publishing to PyPI (inferred below; a later one-line change).
- Renaming the local checkout directory, the homelab repo's references, or the
  NAS image. These are the operator's, and they are private. 06 lists them.
- Any change in behaviour on either side. Both suites hold the same tests
  before and after, give or take moves.
- The four outstanding operator walks. The owner ruled that the split does not
  wait for them (Goals). The walks stay recorded in Arrt's
  `operator-verification.md`, beside the plans they close.

## Goals

**Response taken:** ask, in one batch; the owner answered 2026-10-26.
1. The new repo: **public, and I may create it** ("Public, create it").
2. The contract pin: **a published package** (chosen over a vendored copy
   with a check, and over a submodule).
3. The Player's backlog: **"Transfer, but arrt-player needs to be
   prawduct-enabled as well."**
4. Timing: **split now**, without waiting for the outstanding walks.

**Product:** no user-visible change. The point is the one
`re-architecture.md` gives. After the split, server and Player can each be
built, released and run by their own session, with the contract as the only
ground they share. That is the precondition for wave 6+'s two independent
streams.

**Architecture:**
- **Arrt owns the contract.** The package's source lives in this repo, and
  a contract change is a PR here and a new package version. The Player takes
  that version when it is ready, and the skew is a version number that anyone
  can read.
- **Nothing that guards today guards less afterwards.** Each root test that
  reads both planes is split before the extraction, and each half is watched
  failing in the suite that will keep it (03).
- **The extracted history is checked, not trusted:** the measured tree
  equalities are rerun on the real split (04).
- **Must stay possible:** PyPI publication of the contract; a third client
  repo (the Apple platform in `apple-platform-findings.md`) depending on the
  same package.

**Constraints:**
- `filter-repo` does not follow renames; the Player's history spans `display/`,
  `arrt/` (until `c1c31255`), `postarr/` and `arrt-player/` (re-architecture.md).
- This repo is public, and so is the new one: no addresses, hostnames or
  usernames go into either (CLAUDE.md).
- The display suite's typesetter needs `--group raster`, and its CI is two jobs
  (CLAUDE.md). That shape goes with it.

**Tradeoffs accepted:**
- **During PR 1 and until 05, the contract is a path dependency in all three
  projects.** That is the same atomicity the monorepo gives today. Only the
  Player's source changes at 04.
- **One more lockfile, for the package, and a fourth suite leg in Arrt's CI.**
  Its tests are the contract's own: schemas against fixtures, the vectors, and
  `semantic_errors`.

**Open assumptions** (each the builder's inference, not the owner's ruling):
- *Inferred:* "published" means a version that anyone can install by name and
  that does not move: an annotated tag `contract-v<version>` on
  brookstalley/arrt, which the Player installs as
  `arrt-contract @ git+https://github.com/brookstalley/arrt@contract-v<version>#subdirectory=contract`.
  PyPI would publish the same artifact more permanently, under a name that
  cannot be taken back, and it needs an account and a token in CI. The swap to
  PyPI is one line in the Player's `pyproject.toml`. [MED impact | user can override]
- *Inferred:* the package is a **dev-group dependency on both sides**, not a
  runtime one. No `src/` module on either side reads `contract/` today; the
  Player's reader enforces the rules in its own code, and the contract tests
  that it agrees. So the Pi's install gains nothing. [LOW impact | user can override]
- *Inferred:* the package carries its own semver, starting at **1.0.0**. Its
  major is not the manifest's major: a new schema minor is a package minor, and
  a manifest major is a package major. `player-contract.md` § Versioning
  records the rule. [LOW impact | user can override]
- *Inferred:* the 2024 root modules and their tests are removed in PR 1, not in
  05. They live outside every path the extraction keeps, so removing them
  earlier changes nothing in the Player's history. It also lets `config.py`
  leave with the hardware tools, without a copy left behind for `art.py`. [LOW impact | user can override]
- *Inferred:* arrt-player uses the same gitflow (`main` and `develop`, PRs to
  `develop`). Its first release is **v0.6.0**, the version its `pyproject.toml`
  already carries, so both repos start from the same number. [LOW impact | user can override]
- *Inferred:* the artifacts that leave with the Player are the Player-only
  findings (`samsung-tv-state-findings.md`, `hdmi-output-findings.md`,
  `apple-platform-findings.md`) and the display learnings. Shared ones
  (`player-contract.md`, `feeds-and-players.md`, `clients.md`,
  `labels-and-surfaces.md`) stay in Arrt, which owns the contract, and the
  Player's artifacts point at them by URL. 04 derives the final list from what
  the Player's code and tests cite. [MED impact | user can override]

`[DECISION: the contract package is installed from a git tag on brookstalley/arrt rather than PyPI | the owner asked for a published package; a tag gives a named, immutable, installable version with no account, token or global name to hold, and uv resolves it like any index; PyPI is a one-line swap when a third consumer or an outside user appears | the builder's, 2026-10-26; user can veto]`

**Decisions made mid-build:** *(appended while building; one line each, naming
what settled it)*

**Level:** Medium. The extraction recipe is measured. The package boundary is
new, and the guard split (03) is the part most likely to hide a loss. What would
raise it: 01's inventory of every contract reader, derived by grep and checked
against a run in which `contract/` is renamed away and both suites fail
loudly.

## Chunks

### Chunk 01 — The contract becomes a package

**Type:** code. **Critic mode:** final (a keystone: 02, 03 and 04 all read the
contract through what this chunk builds).

`contract/` becomes the `arrt-contract` distribution, with the import name
`arrt_contract`. The data moves into the package (new
`contract/src/arrt_contract/`) by `git mv`, so the history follows each file.
The package exposes the following:
- `root()`: the package's data directory, as a path.
- `schema(name)`, the registry, and `validator(name)`. These are lifted from
  `tests/preferences/test_player_contract.py`.
- `semantic_errors(document)`: the reference statement of major 2's rules that
  no schema can state, moved out of that test file.
- `fixtures()` and `routes()`.

The package's own tests (new `contract/tests/`) take over everything in the
root suite that reads only the contract: `test_player_contract.py`,
`test_label_rule.py`, and the contract-only parts of `test_contract_vectors.py`.

Every reader goes through the package. The inventory is derived from the code
(grep for `"contract"` path joins across `arrt/`, `arrt-player/`, `tests/` and
both `tools/` trees; 30 sites when this plan was written), never copied from
this sentence. Each project declares `arrt-contract` in its `dev` group, with
`[tool.uv.sources]` set to an editable path. The CI gains a contract leg, with
`assert_tests_ran.py` behind it, and `test_default_suite_ci_scope.py` learns
about that leg. CLAUDE.md's table gains the column.

**Done when:**
1. With `contract/src/arrt_contract/` renamed away, all four suites fail at
   collection or in the first test. This proves that no reader still resolves
   a path of its own.
2. All four suites are green, and the contract leg collects more than zero tests.
3. `semantic_errors` exists once in the tree (`grep -rn "def semantic_errors"`),
   and Arrt's `feed_guard.py` and the Player's reader tests import it.
4. The package builds a wheel that carries the schemas
   (`uv build`, then list the wheel's contents).

### Chunk 02 — The root is cleared down to governance

**Type:** cleanup.

This carries out the owner's ruling of 2026-10-05:
- `tv_api_check.py`, `tv_delete.py`, `panel_check.py` and the `config.py`
  they read move to `arrt-player/tools/`.
- Their tests (`test_tv_delete.py`, `test_panel_check.py`, `test_config.py`)
  move into the display suite. Their dependencies, which are already in the
  Player's `pyproject.toml`, are checked against what they import.
- The 2024 modules are removed, with their tests (`test_dezoomify_argv.py`),
  data (`all.json`, `all.urls`, `test.json`, `test.urls`) and deploy files
  (`samsung-frame-art-loader.service`, `pi-freeze-2024.txt`), and
  `requirements.txt`. The root `pyproject.toml` stops being
  `samsung-frame-art-loader-legacy` and becomes the governance suite's own.

The inventory of what the 2024 modules are comes from what imports what, not
from this list. A root file that nothing in the Player or the governance
suite imports is a 2024 module; one that something imports is not.

**Done when:** the root holds only the governance tests, `.github/`, `deploy/`,
the artifacts, the docs and the three projects. All four suites are green. The
moved tools run `--help` from their new home, in a clean interpreter. A
whole-repo grep (no `--include`) for each removed filename finds only history:
the change log and the archived plans.

### Chunk 03 — Every cross-plane guard is split by plane

**Type:** code. **Critic mode:** cumulative (the last chunk of PR 1).

Every root test that reads `arrt-player/` is listed by grep. When this plan was
written they were: `test_plane_isolation`, `test_heartbeat_contract`,
`test_contract_vectors`, `test_label_corpus_contract`,
`test_staleness_threshold`, `test_file_organization`, `test_norm_index`,
`test_default_suite_ci_scope` and `test_repo_hygiene`. For each one, decide:
- **Its Player half moves into `arrt-player/tests/`**, reading the contract
  through the package. The plane-isolation clauses go here: only `pull.py`
  opens an HTTP client, only to the routes in `routes()`, and no server import.
- **Its server half stays in the root or moves to `arrt/tests/`.**
- **What it asserts across both is restated against the contract.** Example:
  the heartbeat's two sides agree because each side agrees with the
  package's schema and vectors.

Each moved or rewritten half is watched failing in its new home against a
re-break, per the learnings rule on new checks. Nothing in this chunk deletes
an assertion without naming the one that replaces it.

**Done when:** no root test reads `arrt-player/`
(`grep -rln "arrt-player\|arrt_player" tests/` is empty, apart from
`test_default_suite_ci_scope` while the leg exists). All four suites are green.
The cumulative review is clean. PR 1 is merged to `develop`, and the tag
`contract-v1.0.0` is pushed at its merge commit.

### Chunk 04 — Extraction: arrt-player stands alone

**Type:** code. Outward-facing (the owner approved, 2026-10-26).

1. On a scratch clone of `develop` after PR 1 merges, run pass 1 and pass 2 as
   `re-architecture.md`'s wave 5 row gives them, with the ancestry set taken
   over all refs. The set is recomputed, not copied from the row.
2. Rerun the two measured checks: the tip tree equals `develop:arrt-player/`,
   and the tree at the rename's parent equals `<parent>:arrt/`. Also check that
   `git log --follow` on one Player module reaches a `display/` commit.
3. Create **brookstalley/arrt-player** (public) with `gh`, and push `main`
   and `develop`. Both start at the extracted tip.
4. In a checkout of the new repo, on `feature/stand-alone`:
   - The contract source becomes the tag.
   - CI: the display leg and the typesetting job, with `assert_tests_ran.py`.
   - CLAUDE.md, carrying the dev commands, the television's rules and the
     public-repo rule.
   - The Player's artifacts and the display learnings, per the inference in
     Goals.
   - `/prawduct:onboard`, with `project-preferences.md` carried across.
5. Its first PR goes to that repo's `develop`, reviewed by that repo's Critic.
   The owner merges it.

**Done when:** the new repo's CI is green on `develop`. A fresh clone runs
`uv run --group raster pytest` green without this repo on disk. Prawduct's
session banner loads there.

### Chunk 05 — Arrt without the Player

**Type:** cleanup. **Critic mode:** cumulative (PR 2).

The following go:
- `arrt-player/`.
- Its CI leg and the typesetting job.
- `test_default_suite_ci_scope`'s Player rows.
- The `display.md` learnings.
- Every mention of Arrt Player as a sibling directory. That sweep covers
  CLAUDE.md, README, `docs/` and the artifacts. Each mention either goes or
  becomes a link to the new repo, and the sweep greps for the old wording.

`re-architecture.md` § Order of work marks wave 5 closed, and
`architecture.md`'s transition notes move to the new shape. The Player's open
issues are transferred with `gh issue transfer`. Each one is listed first, from
the backlog's areas (display, the Player, panels), and the owner sees the
list before the transfer.

**Done when:**
- `grep -rn "arrt-player/" --exclude-dir=.git .` finds only links and history.
- Arrt's three suites (root, server, contract) are green.
- The transferred issues resolve on arrt-player, and `/prawduct:backlog` there
  lists them.

### Chunk 06 — The wall runs from the new repo *(the operator's)*

The Pi's checkout becomes a clone of arrt-player, and `display.service` paths
are updated in the operator's homelab repo. The walk:
- The wall resumes from its cache.
- Its heartbeat reaches Arrt.
- A republish reaches it.

Recorded in `operator-verification.md`. Optional: rename the local checkout
directory to `arrt`.

## Verification strategy

The suites prove that the code still agrees with itself. What proves the split
is two things:
- The tree equalities and `--follow` in 04.
- A fresh clone of each repo running green with the other repo absent.

The last proof is the wall in 06, running from code that never sat in this
repository's working tree.

## Governance checkpoints

- After 01, the `final` review, because 03 and 04 build on the package boundary.
- Before the push in 04, the tree checks. A failed check stops the push.
