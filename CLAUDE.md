# CLAUDE.md

@AGENTS.md

## Change of direction — 2026-09-30 (read before anything else)

**The product is two: Arrt, this repository, a server holding the Library and
Programming; and Arrt Player, the player at each wall, which lives in
[brookstalley/arrt-player](https://github.com/brookstalley/arrt-player).** The
target, the waves and the open questions are in
`.prawduct/artifacts/re-architecture.md`. The contract between the two is
`player-contract.md` and `contract/`, which Arrt owns and Arrt Player pins by
tag. A field a Player needs is a change to that package here. Rules for working
here meanwhile:

- **The as-built artifacts are still true of the code.** Where one carries a
  dated `Direction changed 2026-09-30` note, `re-architecture.md` wins for the
  target and the older text wins for what runs today, until its wave lands.
- **Several norms are `in-transition`**, each with an interim rule. Read
  `architecture.md` § Direction before touching the manifest, the routes a
  Player calls, or the theme and wall tables.
- **Each wave has its own plan, which names its branch.** What comes next is
  `re-architecture.md` § Order of work, and the plan whose `branch:` you are on
  is the one in force. Branch from `develop`.
- **This repo is public.** The operator's NAS deployment is recorded in their
  private homelab repo. Don't put network addresses, hostnames or usernames here.

## Dev commands

Three independent projects, three suites.

| | governance (repo root) | curation plane | contract package |
|---|---|---|---|
| Test | `uv run pytest tests` | `cd arrt && uv run pytest` | `cd contract && uv run pytest` |
| Lint | `uv run ruff check .` | `cd arrt && uv run ruff check .` | `cd contract && uv run ruff check .` |
| Type-check | — (not type-checked) | `cd arrt && uv run mypy` | `cd contract && uv run mypy` |
| Format | `uv run black .` | `cd arrt && uv run black .` | `cd contract && uv run black .` |

**Run the suites through testament** (`AGENTS.md` § Running tests): `testament
run --json` runs all four on the pool, the browser suite on the runners with
Chromium; `--suite governance|curation|browser|contract` picks one, and a path
after `--` picks tests. `.testament.toml` says how each runs. CI runs every suite
on the pool (`.github/workflows/tests.yml`); the commands above are the local
equivalents, and testament's own fallback runs `.testament.toml`'s commands here. The live suites
(`live_*`, `llm_eval`) are not on the pool and stay on this machine.

**All three must pass.** `contract/` is the `arrt-contract` package
(`player-contract.md` § The package): every suite reads the schemas, fixtures,
vectors and routes through it, never by a path of its own. A change to it is
released as a `contract-v<version>` tag, which Arrt Player's `pyproject.toml`
names.

**Nothing in any of the three reaches a television, a panel, or a museum.** The
`live_*` markers below reach museums and are run by hand. Everything that drives
hardware is Arrt Player's, in its own repository.

**`uv run` in every column, including the root.** pytest, ruff and black live in a
`[dependency-groups] dev` group that only uv installs — `pip install -e .` does
not. Dropping the prefix gets either command-not-found or, worse, a system-Python
pytest that resolves different dependencies and reports a green suite that means
nothing. This table is the authority README.md points at for running the tests, so
a wrong command here costs a fresh clone its first hour.

Run the curation plane: `cd arrt && uv run python -m arrt`. It needs
`ART_ROOT` (copy `.env.example` to `.env`); the browser interface serves on
`CURATION_PORT`, its JSON API under `/api`, and MCP clients connect to `/mcp` on
the same port.

## Testing rules that bite

Each is an instruction. Why it holds is in `docs/testing.md`.

- Debug a curation failure with `cd arrt && uv run pytest … -n0`, here, never
  through testament.
- Never swap the curation suite's real uvicorn server for an in-process ASGI
  transport.
- In `arrt/`, sync with the groups the run needs (`uv sync --group browser`),
  never a bare `uv sync`.
- After touching `arrt/src/arrt/http/static/`, run the browser tests for the
  screens you changed. The whole browser suite runs on the integrated branch, by
  the coordinator (`project-preferences.md` § Workflow, `Delegate verification`).
- The root suite is not optional, even for a change made entirely inside `arrt/`.
- The live markers (`live_museum`, `live_binary`, `live_api`, `llm_eval`) run by
  hand, as `uv run pytest … -n0` on this machine, never through testament.
- The mutation sweep runs per project.
- Whether the UI is good to use: follow `docs/ux-walkthrough.md`.
