# CLAUDE.md

<!-- PRAWDUCT:ANCHOR — static governance pointer managed by the prawduct plugin. Keep it small and version-free: principles, methodology, and the active version live in the plugin and are injected at session start. -->

## Governance (Prawduct)

This repo is governed by **Prawduct**, installed as a Claude Code plugin — not as
committed framework files. The principles, methodology, Critic protocol, and PR
review live in the plugin and are read on demand (run `/prawduct:methodology`);
they are intentionally not copied into this repo.

**Before writing any code, STOP and read the build cycle: `/prawduct:methodology building`.**
Skipping it is the #1 governance failure.

The hardest rules (everything else is in the plugin):

- **Tests are contracts** — fix the code, never weaken a test.
- **No "pre-existing" exception** — fix what you find, or flag why you can't.
- **Never silently drop a requirement** — say so explicitly.
- **Run `/prawduct:critic` after medium+ work** — never write Critic findings
  yourself; the independence is the value.

**Enforcement is structural:** the plugin's Stop hook runs at session end and
**blocks** if code changed against an active build plan with no Critic findings.
The session-start banner shows the active version and what changed — this anchor
stays version-free.

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
| Format | `uv run black .` | `cd arrt && uv run black .` | `cd contract && uv run black .` |

**All three must pass.** `contract/` is the `arrt-contract` package
(`player-contract.md` § The package): every suite reads the schemas, fixtures,
vectors and routes through it, never by a path of its own. A change to it is
released as a `contract-v<version>` tag, which Arrt Player's `pyproject.toml`
names.

**Nothing in any of the three reaches a television, a panel, or a museum.** The
`live_*` markers below reach museums and are run by hand. Everything that drives
hardware is Arrt Player's, in its own repository.

**A plain `uv sync` uninstalls the optional groups.** uv treats anything outside
the default groups as extraneous and removes it, so after a bare `uv sync` in
`arrt/` the browser suite skips itself. The suite stays green and quietly
shrinks. Sync with the groups the run needs: `uv sync --group browser`.

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

**The mutation sweep runs per project.** How to read a sweep, budget one, and
sweep the browser suite: `docs/testing.md`.

The curation suite boots a real uvicorn server per test class of surface work.
Do not replace that with an in-process ASGI transport: Starlette does not run a
mounted sub-app's lifespan, and the lifespan is what makes the MCP mount work,
so an in-process test would pass against an app that fails every real request.

**That suite runs across cores** — `-n auto` is in the curation plane's
`addopts`, so `uv run pytest` is already parallel (118s → 21s, measured
2026-08-05). **Add `-n0` to debug a failure**: workers interleave output and a
`pdb` breakpoint has no terminal to stop in. The root suite runs in a fraction of
a second and is left serial.

**The root suite holds no product code, and it is not optional.** It carries
`tests/preferences/`, where this repo's artifact-versus-code contracts
live — the Library/Programming seam, the norm index, deployment values, and the
screen tables — and the repository-wide scans, which cover every project its
tracked `pyproject.toml` files name. Agreements with Arrt Player (the
heartbeat, the timing, the label corpus) are held by each side's own suite
against the contract package, never by a test that reads both. The screen tables
span two homes by design: `test_screen_tables.py` reads
the *curation* plane's `http/static/app.js` against
`.prawduct/artifacts/information-architecture.md`, and the server's own suite
does not read the artifacts. So a change made entirely inside `arrt/` — routing a screen,
editing those IA tables — is guarded by a leg in the repo root.

## The browser suite and the live suites

The client under `arrt/src/arrt/http/static/` is the product's only human
interface, and no Python suite runs it: `-m browser` does, and you run it
whenever you touch anything under `static/`. The four live markers (`live_museum`,
`live_binary`, `live_api`, `llm_eval`) check foreign APIs and are deselected by
default; `live_api` and `llm_eval` spend real money, and every live run takes
`-n0`. Commands, setup and the reasons behind each rule: `docs/testing.md`.

**Every suite asks whether the client matches its documents; none asks whether
it is good to use.** When the question is the second one — a redesign, a run of
screen work, "the UI feels off" — follow `docs/ux-walkthrough.md` rather than
inventing a method: four passes, in order, and `arrt/tools/ux_walk.py` does the
first.
