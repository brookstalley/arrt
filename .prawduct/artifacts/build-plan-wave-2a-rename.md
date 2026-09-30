---
artifact: build-plan
version: 1
scope: wave-2a-rename
branch: feature/wave-2a-rename
partition: serial — one mechanical chunk, and a rename split across agents would collide on every import line
depends_on:
  - artifact: re-architecture
  - artifact: operational-spec
governed_by:
  - artifact: project-preferences
    dispositions:
      - "plane isolation (display imports no curation module) → conforms: the test is renamed with the packages and keeps asserting the same property, displayarr importing no curatarr module. Its assertions do not change, only the names in them"
      - "the two planes agree on the heartbeat's filename and its instant's key by construction → conforms: the test's source paths are renamed; the constants and file names it compares are untouched"
      - "the mechanical norm-index rows (formatting, naming, imports) → conforms: every renamed import is re-sorted by ruff, and each plane's lint and format run"
  - artifact: nonfunctional-requirements
    dispositions:
      - "the display plane never requires the curation plane to be reachable → inapplicable because: nothing about either process's behaviour changes; only the names do"
last_validated: null
---

# Build Plan — Wave 2a: Curatarr and Displayarr, in the code

## What this plan is

The operator named the products on 2026-09-30: Curatarr (the server) and
Displayarr (the player). The GitHub repo is already renamed. This plan renames
the code: the `curation/` project and `curation` package become `curatarr`,
and `display/` and `display` become `displayarr`. It is its own plan because it
is a different kind of change from the rest of wave 2. It is purely mechanical,
touches around two hundred files, and changes no behaviour. Reviewed alongside
the seam split, it would bury a refactor inside a rename.

**It goes first in wave 2** because the Library/Programming split
(`build-plan-wave-2b-seams-and-http.md`) creates new packages and moves modules
across them. Doing that under the old names and renaming afterwards would touch
every moved file twice.

**Prose keeps its role names.** "The curation plane" and "the display plane" in
the artifacts describe roles in the as-built system, and they retire as the
waves replace those roles. Only paths, package names, commands and identifiers
change.

## Requirements Confidence

**High.** It is a rename with a green suite on each side, and the suites are the
proof.

- `[ASSUMPTION: the MCP server's advertised name becomes "curatarr" and the
  museum User-Agent names the curatarr repo URL; neither is an interface any
  client keys on, since tool names are frozen and unchanged | LOW impact | user
  can correct]`
- `[ASSUMPTION: the Pi keeps its checkout at /opt/samsung-frame-art-loader until
  wave 3 retires the Pi as the server, so the units change their project
  directories and module names but not the checkout path | MED impact | user can
  correct]`

## Status

- [ ] Chunk 01: Rename the projects and packages, and everything that names them

### Chunk 01: Rename the projects and packages, and everything that names them

- **Type:** cleanup
- **Depends on:** `build-plan-wave-1-contract.md` merged
- **Surfaces, enumerated so the chunk's true size shows:**
  - The directories `curation/` → `curatarr/` and `display/` → `displayarr/`,
    by `git mv`, so history follows.
  - The packages under each `src/`, every import, and each `pyproject.toml`'s
    project name, scripts and tool configuration. Each `uv.lock` is regenerated.
  - `python -m curation` / `python -m display` in `deploy/curation.service` and
    `deploy/display.service`, and each unit's `WorkingDirectory`. The unit files
    keep their names until wave 3, so the Pi's installed units are replaced
    rather than added beside.
  - `.github/workflows/*.yml`: working directories, paths and job names.
  - `tests/preferences/*.py`: the source paths they read across both projects.
    `test_plane_isolation.py` keeps its assertions and changes only names.
  - `contract/`-reading tests in both projects, which compute the repo root
    from their own depth.
  - `CLAUDE.md`'s dev-command table and every command in it, `README.md`,
    `deploy/README.md`, and `.env.example` where it names a module.
  - Path references in `.prawduct/artifacts/` (about a hundred lines) and
    `project-state.yaml`'s `test_commands`. The archive and the change-log
    archive are left alone, because they are history.
  - `SERVER_NAME` in the MCP server, and its contract test. The User-Agent in
    `config.py` and the live test.
- **Tests:** all three suites pass with no test weakened. Proof the rename is
  complete: `git grep -nE '\b(from|import) (curation|display)\b'` and
  `git grep -nE '(curation|display)/(src|tests|tools)'` return nothing outside
  the archives.
- **Visual change:** no. **Operator verification:** yes. The Pi's units must be
  reinstalled from `deploy/` after this lands, or they start the old module
  names and fail. The step joins `operator-verification.md` with the commands.
- **Done when:** the three suites and their lint pass under the new names; the
  greps above are empty; CI passes on the branch; the queue entry exists.
