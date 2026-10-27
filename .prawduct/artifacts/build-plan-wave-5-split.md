---
artifact: build-plan
version: 1
scope: wave-5-split
branch: feature/wave-5-extraction
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
      - "§ Order of work, wave 5 row (two-pass filter-repo over four historical paths; move the root's non-2024 hardware tools into arrt-player/tools first; remove the 2024 root modules; onboard prawduct there; carry the Player's artifacts; pin contract/ with player-contract.md and the major 2 semantic validator; the new repo is arrt-player, this one Arrt) → conforms: 02 moves the tools and removes the modules, 04 runs the measured recipe and its two tree checks, 01 makes the pin a package that carries all three, 05 leaves this repo as Arrt. The pin's form is the owner's ruling of 2026-10-26 (Goals). Exception, recorded as a decision in Goals and ratified by the owner 2026-10-26: the tools do not carry the root's `config.py` with them; they read the Player's own settings"
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
- *Ratified 2026-10-26 ("Git tag for now"):* "published" means a version that anyone can install by name and
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

`[DECISION: the contract package is installed from a git tag on brookstalley/arrt rather than PyPI | the owner asked for a published package; a tag gives a named, immutable, installable version with no account, token or global name to hold, and uv resolves it like any index; PyPI is a one-line swap when a third consumer or an outside user appears | the builder's, 2026-10-26; **ratified by the owner 2026-10-26: "Git tag for now."**]`

`[DECISION: the hand-run tools read the Player's own settings (arrt_player.config.load) instead of carrying the root's config.py into arrt-player/tools | the owner's 2026-10-05 ruling moved "tv_api_check.py, tv_delete.py, panel_check.py, and the config.py they read" so that the tools leave with the Player and keep working; that config.py was the 2024 configuration and required ART_ROOT, LATITUDE, LONGITUDE and LOCATION_NAME at import, so carried as written it would have stopped tv_api_check.py on a Player, and a tool reaching the set by settings other than the wall's checks something other than the wall | the builder's, 2026-10-26; **ratified by the owner 2026-10-26: "Yes accept change."**]`

**Decisions made mid-build:** *(appended while building; one line each, naming
what settled it)*
- 01: the data stays at `contract/schemas/`, `fixtures/`, `vectors/` and `routes.json`, with the package in `contract/src/`, and the wheel force-includes the data. Settled by "do it right": 58 files cite those paths, and moving them would rewrite the specification's addresses for no change in meaning.
- 01: the package carries `player-contract.md` (`specification()`), through a symlink in `contract/` for the wheel and its real path for the sdist. Settled by the wave 5 row: pin the contract "together with `player-contract.md`".
- 01: the Player's suite does not import `semantic_errors`. Its reader states the rules in its own code and is held to the fixtures' `player_must_refuse`, which is the independence the contract wants. The plan's Done-when 3 said otherwise and was corrected. Not settled by the goals: an error in the plan.
- 01: the package's tests are the three root files that read only the contract, moved whole with `git mv`, plus a new `test_package.py` for `root()`, `specification()` and the wheel.
- 01, after its review (0 blocking): every remaining caller reads through `validator()`, `routes()` and `schema()`, so no project builds its own registry; `semantic_errors` states that it is asked only of a schema-valid document, and the feed guard asks it only then; a test installs the built wheel and reads its data through it; the root's `jsonschema` and `referencing` went with the test that used them. Carried into chunk 02's commit, per the learnings rule on cheap observations.
- 02: the tools read the Player's own settings (`arrt_player.config.load()`) rather than carrying the root's `config.py` with them. That file was the 2024 configuration: it required `ART_ROOT`, `LATITUDE`, `LONGITUDE` and `LOCATION_NAME` at import, so `tv_api_check.py` would have refused to start on a Player that sets none of them, and reaching the set by other settings than the wall's would check something other than the wall. This departs from the letter of the owner's 2026-10-05 ruling ("and the `config.py` they read") and keeps its purpose, which was that the tools leave with the Player and keep working. Not settled by the goals: flagged for the boundary review.
- 02: `all.json` stays: the server's seed tool reads it and `arrt/Dockerfile` copies it into the NAS image, so it is the server's data, not a 2024 module. `deploy/pi-freeze-2024.txt` stays as the record of the Player's pinned panel driver (`arrt-player/pyproject.toml` cites it) and leaves with the Player in 04. Settled by "do it right": the plan's list was wrong about both.
- 02: `tv_delete.py`'s `remove_from_tv`, `forgettable_ids` and `describe_removal` went with their only caller, `tvart.py`, and so did the ten tests that exercised only them. The two tests that held the cause in the refusal's message were rewritten against `delete_list_confirmed`, which carries that message.
- 02: `tests/test_config.py` was split. Its repo-wide deployment-value guards became `tests/preferences/test_deployment_values.py`, now walking `contract/src` too. Its tests of the 2024 `config.py` left with that file, and the norm index's secret row now names the planes' own startup guards. The two tests of the 2024 systemd unit left with the unit, because the live-unit tests beside them assert the same properties on the units that run.
- 02: the 2024 sections of `deploy/README.md` (the retired unit's recipe and its provenance) were removed, and the dependency-move record stays with its references corrected. The rest of that file is the Player's install history, which 04 carries.
- 02, after its review (0 blocking): `tv_delete.py` takes `UPLOADED_CATEGORY` from the daemon's `arrt_player.tv.client`; rewiring the tool onto `SamsungTv.remove` is #384, because it changes what the tool measures and only the set can verify it. `tv_api_check` refuses a Player with no television in a sentence and exit 2. The feed guard's schema-first branch has a test. The surviving present-tense references to the 2024 plane in the artifacts were corrected; historical ones stay.
- 03: each cross-plane agreement is restated against the contract rather than split in two: a side holds its own constant to the package, so the two agree because each agrees with the contract. That needed the contract to say three things it only implied: `instant_key()` (the heartbeat's one required `date-time` key), `timing.json` (the heartbeat interval and the three-interval staleness threshold, which `player-contract.md` states in prose), and `vectors/label-corpus.json` (the real records renderers measure against, which Arrt holds to its seed tables and the Player holds its copy to). Settled by the architecture goal, "nothing that guards today guards less afterwards".
- 03: the corpus vector found that the `anonymous` record has no title, which no server sends (#385). It is a named exception in the package test until that is decided, rather than a change to records the accessibility spec's measurements were taken against.
- 03: the plane-isolation guard moved whole into the Player's suite, with a copy of the import reader; it reads only Player code and the contract's routes. The root's repository-wide scans (deployment values, gitignored source, test placement) now derive their scope from the tracked `pyproject.toml` files rather than naming planes, and the Player carries its own copies scoped to itself.
- 03: the Player's deploy files (`deploy/display.service`, the journald bound, `pi-freeze-2024.txt`) and the root tests that guard `display.service` are not moved here. The Pi's runbook and the deploy README name those paths for the live install, so moving them mid-wave changes the operator's procedure; 04 copies them, with their guards, into the new repository, and 05 removes them here. The norm index's rows that name Player tests move with the Player's artifacts in 04 and 05 likewise.

- 04: the ancestry set was recomputed over all refs of a fresh clone: 744 commits (the row's measurement of 2026-10-01 held 6). All three checks held: the tip tree equals `develop:arrt-player/` (`b8ddfa29`), and `main` equals `main:arrt-player/`; the tree at the player rename's parent equals `65b78db2:arrt/` (`e9cc9440`), reached through #155's merge because filter-repo pruned #156's, which touched only the server; and `--follow` on `src/arrt_player/__init__.py` reaches `src/display/__init__.py`. Only `main` and `develop` were pushed. The rewritten `v0.x` and `contract-v1.0.0` tags name this repository's releases, so none went.
- 04: the artifacts that left were derived from what the Player's code, tests, tools and its deploy record cite, and the derivation added two to the inference in Goals. `platform-and-dependency-findings.md` (cited by six Player files, by nothing in `arrt/`) and the Pi runbook (`moving-the-pi-player-to-a-new-revision.md`, cited by the deploy record) went with the three findings. The learnings `core.md` and `tooling.md` went beside `display.md`, re-scoped to the new tree. Chunk 06 updates the runbook in arrt-player, where it now lives; 05 removes Arrt's copies.
- 04: `display.service` in arrt-player names a checkout at `/opt/arrt-player`, with the `.env` at its root, because the monorepo's path does not exist in a clone of the new repository; a new guard holds the `.env` to the checkout's root. Not settled by the goals. The arrt-player session reports the owner confirmed `/opt/arrt-player` on 2026-10-26; not yet confirmed to this session directly. The move itself is 06.
- 04: four root guards walked every tracked file of the shared repository, so they guarded the Player and would have stopped at the split. Each was carried: the waiver check, the norm-index check, `assert_tests_ran.py`'s own tests, and the CI-scope check, re-derived for one suite and one typesetting job. The deploy-unit guards were carried for the display unit. The norm index was carried as 23 rows naming the Player's own guards, with the Why kept present-tense and the history left in Arrt's file. The corpus and timing agreements have no norm rows, so none were carried for them.
- 04: carrying the scope check found a hole in Arrt's copy: it collected only the literal `uv run pytest`, so `uv run --group raster pytest` (the typesetting job) was never checked. Fixed in both repositories, with an example test watched failing against the old matcher. Carrying the deploy record found a dangling "§ Seeding the catalogue", which names a paragraph rather than a heading; fixed in both.
- 04: on a Mac, a fresh clone's `uv run` picks uv's managed interpreter, which cannot load Homebrew's GLib, so the typesetter fails at import; a venv built on Homebrew's 3.13 passes. Measured on the fresh clone. arrt-player's CLAUDE.md gives the command. Arrt's display column has the same exposure until 05 removes it; the server's suite needs no text stack.
- 04: discovery for arrt-player (its `project-state.yaml` product definition) was left to a session opened there, as onboarding directs from another directory. So were its Critic, its PR and `evidence configure`, because the gates resolve to the session's working directory.

- 04, done 2026-10-26: brookstalley/arrt-player#1 (`feature/stand-alone` → `develop`) merged as `c41a9191`, after that repository's own Critic (one blocker, fixed: the Pi runbook drove the monorepo checkout, and now carries a first-time move off `/opt/samsung-frame-art-loader` that keeps the old checkout as the way back) and its PR review (0 blocking). Done-when, each checked: CI green on `develop` (run 40439480295 at `c41a9191`, all three jobs); a fresh clone from GitHub, with an empty uv cache and no path reference, ran `uv run --group raster pytest` green (1254, at `4da02cf`); prawduct's banner loads there (that session ran its Critic and PR). 05 is unblocked.
**Level:** Medium. The extraction recipe is measured. The package boundary is
new, and the guard split (03) is the part most likely to hide a loss. What would
raise it: 01's inventory of every contract reader, derived by grep and checked
against a run in which the package is renamed away and every suite fails
loudly. *(Done 2026-10-26: all four failed at collection.)*

## Chunks

### Chunk 01 — The contract becomes a package

**Type:** code. **Critic mode:** final (a keystone: 02, 03 and 04 all read the
contract through what this chunk builds).

`contract/` becomes the `arrt-contract` distribution, with the import name
`arrt_contract`. The data stays where the specification names it
(`contract/schemas/` and the rest), and the package (new
`contract/src/arrt_contract/`) carries it in the wheel; see the mid-build
decisions. The package exposes the following:
- `root()`: the directory holding the data, as a path.
- `schema(name)`, `registry()` and `validator(name)`, lifted from the root
  suite's contract test.
- `semantic_errors(document)`: the reference statement of major 2's rules that
  no schema can state, moved out of that test file.
- `fixtures()`, `routes()` and `specification()`.

The package's own tests (new `contract/tests/`) take over the three root
tests that read only the contract, moved whole: they are now
`contract/tests/test_schemas_and_fixtures.py`, `test_label_rule.py` and
`test_vectors.py`.

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
   and Arrt's `feed_guard.py` imports it.
4. The package builds a wheel that carries the schemas, the routes and
   `player-contract.md`, through the sdist as an installer may build it, and
   the wheel reads cleanly in an isolated interpreter.

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
(`grep -rln "arrt-player\|arrt_player" tests/` finds only comments, and
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
