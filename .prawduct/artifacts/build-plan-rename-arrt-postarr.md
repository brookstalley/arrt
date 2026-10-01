---
artifact: build-plan
version: 1
scope: rename-arrt-postarr
branch: feature/rename-arrt-postarr
partition: serial — two mechanical chunks in a fixed order, and a rename split across agents would collide on every import line
depends_on:
  - artifact: re-architecture
  - artifact: build-plan-wave-2a-rename
governed_by:
  - artifact: project-preferences
    dispositions:
      - "plane isolation (display imports no curation module) → conforms: the test is renamed with the packages and keeps asserting the same property, now postarr importing no arrt module. Its assertions do not change, only the names in them, and it is watched failing once against a planted import after the rename, because the name it forbids now means the other plane"
      - "the two planes agree on the heartbeat's filename and its instant's key by construction → conforms: only the source paths the test reads are renamed"
      - "the mechanical norm-index rows (formatting, naming, imports) → conforms: every renamed import is re-sorted by ruff, and each plane's lint and format run"
  - artifact: nonfunctional-requirements
    dispositions:
      - "the display plane never requires the curation plane to be reachable → inapplicable because: neither process's behaviour changes; only the names do"
last_validated: null
---

# Build Plan — Arrt and Postarr

## What this plan is

On 2026-10-01 the operator renamed the products again, under a hard
requirement: the server becomes **Arrt** and the player becomes **Postarr**.
Until now the server was Curatarr and the player was Arrt (wave 2a,
`build-plan-wave-2a-rename.md`). The operator said this is the last rename
and asked that it not be built as a feature. So there is no indirection and no
configurable name: this is a plain rename, like wave 2a.

**What makes this rename different from wave 2a is that "Arrt" swaps
meaning.** Before, it names the player. After, it names the server. Done as
one pass, either order of substitution destroys information. Curatarr→Arrt
first, then Arrt→Postarr, makes everything Postarr. The other way round only
works if no step ever sees both meanings at once. So this plan is **two
chunks, two commits, in a fixed order**:

1. **Arrt → Postarr.** Afterwards the string `arrt` occurs nowhere outside the
   history files, so an empty grep proves the chunk complete.
2. **Curatarr → Arrt.** Afterwards the string `curatarr` occurs nowhere outside
   the history files, so an empty grep proves this chunk complete too.

Each chunk ends with an old name that has disappeared completely, so each has
a completeness check that cannot be confused by the name's new meaning. Doing
it in one commit would remove that check.

**Prose keeps its role names**, as in wave 2a. "The curation plane" and "the
display plane" describe roles and do not change. Product names in prose
("Curatarr, a server holding the Library", "Arrt power control") do change,
because the product name is the thing being renamed.

**History is left as written, with a pointer.** The completed build plans
(wave 1, 2a, 2b, *arr navigation), `change-log.md`, its archive,
`reflections.md` and `artifacts/archive/` record what was true on their day.
Rewriting "the operator named the player Arrt" to say Postarr would falsify
them. Leaving them as they are makes "Arrt" ambiguous in the history. So each
history file that names either product gets one dated note at its head saying
that, before 2026-10-01, Arrt named the player and Curatarr named the server.
Those are `change-log.md` and the four completed plans. Neither archive and not
`reflections.md` name either product, so they get nothing.

## Requirements Confidence

**High.** It is a rename with a green suite on each side, and the suites are
the proof.

- `[ASSUMPTION: the operator renames the GitHub repo brookstalley/curatarr to
  brookstalley/arrt themselves, before this branch merges; Chunk 02 writes the
  new URL into the schemas' $id, the User-Agent and backlog_service_repo, and
  the backlog tooling cannot reach the new name until the rename happens | MED
  impact | user can correct]`
- `[ASSUMPTION: the server's directory and package become arrt/ and arrt,
  taking the path the player has just left, rather than a role name such as
  server/; the reuse of the path costs wave 5 a commit-aware history filter,
  recorded below | MED impact | user can correct]`
- `[ASSUMPTION: the MCP server's advertised name becomes "arrt"; no client keys
  on it, since tool names are frozen and unchanged | LOW impact | user can
  correct]`
- `[ASSUMPTION: the Pi keeps its checkout at /opt/samsung-frame-art-loader; the
  units change their project directories and module names but not the checkout
  path, as in wave 2a | MED impact | user can correct]`

## What the path reuse costs wave 5

Wave 5 extracts the player's history with `git filter-repo`. After this plan,
the player's history spans three paths: `display/` (until wave 2a), `arrt/`
(from wave 2a until Chunk 01) and `postarr/` (from Chunk 01). From Chunk 02 on,
`arrt/` is the server. Filtering on all three paths alone would carry the
server's history into the player repo. The filter therefore has to be
commit-aware, and it has to run in **two passes**. The first pass works on the
original paths. In the server rename commit and every commit that descends from
it, including the merge that lands this branch, every change under `arrt/`
becomes a deletion. The second pass filters and renames the three paths. One
pass does not work: filter-repo renames paths before its commit callback runs,
so server and player files collide on the names they share (`uv.lock`,
`pyproject.toml`, `tests/conftest.py`).

**Measured 2026-10-01**, after the cumulative review (R-4) said the one-pass
recipe first recorded here would fail. On a scratch clone with this branch
merged `--no-ff` into develop, the one-pass form crashed fast-import on
`uv.lock`. The two-pass form produced a tip tree byte-identical to the original
`postarr/` and, at the player rename's parent, a tree identical to the original
`arrt/`. Those two comparisons are the check to rerun on the real split.
`re-architecture.md` § Order of work carries the recipe.

## Status

- [x] Chunk 01: Arrt → Postarr (the player)
- [x] Chunk 02: Curatarr → Arrt (the server), and the PR #156 debt

### Chunk 01: Arrt → Postarr (the player)

- **Type:** cleanup
- **Surfaces:**
  - `git mv arrt postarr`, then the package beneath it, giving `postarr/src/postarr`.
    Every import, `pyproject.toml`'s project name, scripts and tool
    configuration. `uv.lock` regenerated.
  - `deploy/display.service` (`WorkingDirectory`, `python -m`), `deploy/README.md`.
  - `.github/workflows/*.yml`: the `arrt` job, working directories and paths.
  - `tests/preferences/*.py`, `tests/test_repo_hygiene.py`,
    `tests/test_default_suite_ci_scope.py`, `tests/test_config.py`, the root
    `pyproject.toml` and `requirements.txt`, wherever they name the player's
    paths.
  - The curation plane's mentions of the player by name (one `src` file).
  - `contract/routes.json` and the schemas' descriptions, where they name the
    player.
  - `CLAUDE.md`, `README.md`, `docs/`, live artifacts under
    `.prawduct/artifacts/`, `operator-verification.md` and
    `project-state.yaml` (`test_commands` included).
  - The heads of the history files: the dated note described above.
  - Three lines that record the naming history keep the old name on purpose:
    the naming paragraph in `re-architecture.md` and its copy in
    `project-state.yaml`, and the wave 5 filter, which must name `arrt/`
    because the player lived there.
- **Tests:** all three suites pass with no test weakened. Completeness is
  shown by a grep for the old name, with a count taken before the chunk starts
  so that an empty result means "renamed" and not "never matched":
  `git grep -niP 'arrt'`, excluding the history files and this plan. Before:
  360 lines in 82 files. After: the three history lines named above, and
  nothing else. A second check is keyed on something the substitution did
  not key on: `git diff -M --name-status` against the parent shows every
  tracked file under `arrt/` as a rename into `postarr/`, and nothing else
  removed. Measured: 58 tracked files under `arrt/`, 58 renamed into
  `postarr/`.
- **Rebuilding `.venv` picked Python 3.14**, and the typesetter failed to
  import. This is backlog #153, unchanged by the rename. It was rebuilt on
  3.13, where the suite had been green. #153 is still open, and wave 3's
  container settles it.
- **Done when:** the three suites, their lint and their format pass; the grep
  shows only the three history lines; the rename roster is complete.

### Chunk 02: Curatarr → Arrt (the server), and the PR #156 debt

- **Type:** cleanup
- **Depends on:** Chunk 01 committed. The order is the point of the plan.
- **Surfaces:**
  - `git mv curatarr arrt`, then the package beneath it, giving `arrt/src/arrt`. Every
    import, `pyproject.toml`, `uv.lock`, the `curatarr` CI job, and the
    `.claude/rules/learnings/*.md` path globs.
  - `deploy/curation.service`, `deploy/README.md`. The unit files keep their
    role names.
  - `SERVER_NAME` in the MCP server and its contract test.
    `DEFAULT_ACQUISITION_USER_AGENT` and the live test.
  - The schemas' `$id` URLs and `backlog_service_repo`, which name the GitHub
    repo (see the first assumption).
  - `tests/preferences/test_plane_isolation.py`: it now asserts that postarr
    imports no arrt module. **Watched failing once** against a planted
    `import arrt` in a postarr module, then reverted. The name it forbids has
    just changed meaning, and a swap done in the wrong order would leave it
    asserting something true and useless.
  - Everything Chunk 01 listed under prose and artifacts, for the server's
    name. `re-architecture.md` § Order of work, wave 5: the player repo is
    Postarr, this repo becomes Arrt, and the filter recipe above.
  - The harness's auto-memory, where it names Curatarr.
- **Carried into this chunk's commit** (accepted from the PR #156 review, and
  every file is touched here anyway):
  - `build-plan-arr-navigation.md`'s stale Chunk 05 text is **dropped from the
    debt, deliberately**: that plan is complete and is history (see above), and
    rewriting a ticked chunk's text to match later decisions would misrecord
    what was planned.
  - `information-architecture.md` and `project-preferences.md`: the open
    questions test new pages against the replaced three-destination norm; the
    Add New empty state still mentions runs; "Collection" and "masthead" still
    appear as current names; a pointer still names the deleted
    `test_the_three_destinations.py` (now `test_the_sidebar.py`). Only
    current text was changed; CHANGE and RULING blocks and dated history keep
    "Collection", as they recorded it.
  - The "Chunk 05" comment in `arrt/src/arrt/http/static/screens/collection.js`.
- **Tests:** all three suites pass, the browser suite included (static files
  are touched). `git grep -niP 'curatarr'`, excluding the history files and
  this plan: before 1162 lines in 241 files. After: 13 lines at the PR, each
  one a record of the naming history (the operator's 2026-09-30 quote and the
  names settled that day, the wave 5 filter, the repo's former names, and the
  Pi step's old directory names and rollback), and nothing else. Rename roster: 263 tracked files under the old server directory, 263
  renamed into `arrt/`, and `arrt/` holds exactly those 263. The isolation
  test failed on a planted `import arrt.config` in `postarr/src/postarr/config.py`,
  naming it as the curation plane, and passed once it was removed.
- **Visual change:** yes, the browser's `<title>` and brand heading read Arrt.
  `arrt/tests/integration/test_browser_surface.py` asserts both in the served
  shell; the brand assertion was added here and watched failing against the
  old name. **Operator verification:** yes. The Pi's units must be
  reinstalled from `deploy/` after this lands, or they start module names that
  no longer exist. The step joins `operator-verification.md` with the commands.
- **The commit's subject contains `Rename the server Curatarr to Arrt`**, and no
  other commit's does, because wave 5's filter finds the commit by that phrase.
  The branch lands as a merge commit (the project's default), so the commit
  survives. Once merged, its id goes into the recipe in `re-architecture.md`.
- **Done when:** the three suites, lint, format and the browser suite pass;
  both greps are empty; CI passes on the branch; the queue entry exists; the
  Critic has reviewed the branch; and **the operator has renamed the GitHub
  repo to brookstalley/arrt**, which is a precondition of the merge, because
  the User-Agent, the schemas' `$id`, `backlog_service_repo` and
  `security-model.md` already name it.
