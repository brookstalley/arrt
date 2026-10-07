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

**The product is becoming two: Arrt, a server holding the Library and
Programming, and Postarr, a Player at each wall.** The target, the waves and
the open questions are in `.prawduct/artifacts/re-architecture.md`. The contract
between the two is `player-contract.md` and `contract/`. Rules for working here
meanwhile:

- **The as-built artifacts are still true of the code.** Where one carries a
  dated `Direction changed 2026-09-30` note, `re-architecture.md` wins for the
  target and the older text wins for what runs today, until its wave lands.
- **Several norms are `in-transition`**, each with an interim rule. Read
  `architecture.md` § Direction before touching the manifest, the display
  plane's I/O, or the theme, wall and directive tables.
  `tests/preferences/test_plane_isolation.py` allows an HTTP client in
  `postarr/src/postarr/pull.py` only, since wave 2b; everything else it holds is unchanged.
- **Each wave has its own plan, which names its branch.** What comes next is
  `re-architecture.md` § Order of work, and the plan whose `branch:` you are on
  is the one in force. Branch from `develop`.
- **This repo is public.** The operator's NAS deployment is recorded in their
  private homelab repo. Don't put network addresses, hostnames or usernames here.

## Dev commands

Three independent projects, three interpreters, three suites.

| | 2024 modules (repo root) | curation plane | display plane |
|---|---|---|---|
| Test | `uv run pytest tests` | `cd arrt && uv run pytest` | `cd postarr && uv run --group raster pytest` |
| Lint | `uv run ruff check .` | `cd arrt && uv run ruff check .` | `cd postarr && uv run ruff check .` |
| Format | `uv run black .` | `cd arrt && uv run black .` | `cd postarr && uv run black .` |

**All three must pass.** The display plane got its suite, its `test_commands`
entry and its CI leg on 2026-08-06, with its first modules — until then its
`pytest` collected nothing and exited 5, which is neither a pass nor a failure.
That same commit carried the plane-isolation test, because both are the same
claim about when a guard starts guarding.

**Nothing in any of the three reaches a television, a panel, or a museum.** The
display suite drives a double behind the TV interface, which is why it runs on a
GitHub runner; the hardware is exercised by `tv_api_check.py`, by
`postarr/tools/power_probe.py`, and by the `live_*` markers below, all of them run
by hand.

**`power_probe.py` presses power on the real television, and it is the only thing
in this repo that does.** It refuses to send anything without `--i-am-at-the-set`,
because one measurement is deliberately taken from the television state that
`nonfunctional-requirements.md` § The television belongs to whoever is using it
forbids shipped code to press at — legitimate only with somebody watching the set.
Stop the daemon first. Its docstring carries the rest and `deploy/README.md`
§ Measuring what the power keys do carries this machine's paths.

**The display column carries `--group raster` because the recorded evidence
does.** Without it `pytest` collects a strictly smaller suite than the one
`test_commands` runs, so a developer following this table and a `.test-evidence.json`
claiming a green display leg are talking about different suites — and the
difference is the typesetter, the plane's most important accessibility surface.

**`postarr/tests/raster` needs one optional group and skips itself without it.**
The label is typeset with Pango through PyGObject, which a default `uv sync` does
not install. **It does install and import on this Mac** — verified 2026-08-13,
PyGObject 3.56.3 resolving as a wheel against Pango 1.57.1, rendering through
PangoCairo. (This entry said the opposite for months, on the strength of an older
Homebrew build that failed at import; the cost of believing it is that the
product's most important accessibility surface goes unexercised locally and is
first seen in CI.) So run it:

```sh
cd postarr && uv run --group raster pytest tests/raster
```

The display CI leg carries `--ignore=tests/raster` so the collection skip is not
read as a provisioning failure, and a **separate `typesetting` job** installs the
group and runs it, with `assert_tests_ran.py` behind it. Both halves of that are
derived rather than trusted by `tests/test_default_suite_ci_scope.py`, which fails
at home if a leg ignores a directory no other job runs. The panel *driver* group
(`--group epaper`, `omni_epd`) installs on a Raspberry Pi and nowhere else;
nothing in either suite needs it, because the driver is passed into
`EpaperSurface` rather than opened by it.

**A plain `uv sync` uninstalls the optional groups.** uv treats anything outside
the default groups as extraneous and removes it, so after a bare `uv sync` in
`arrt/` the browser suite skips itself, and in `postarr/` the typesetter
does. The suites stay green and quietly shrink. Sync with the groups the run
needs: `uv sync --group browser` in curation, `uv sync --group raster` in display.

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

Run the display plane: `cd postarr && uv run python -m postarr`. **It drives the
real television**, so it is not a thing to start casually: it uploads, deletes and
selects against whatever `TV_ADDRESS` points at. **Stop it with SIGTERM, never
SIGKILL** — the set holds an abandoned art-channel client's slot for minutes, and
a hard kill can leave the next connection refused. It declines to touch a set that
is not in art mode, so it will not interrupt somebody watching television.

**The mutation sweep runs per plane, and the display plane needs `--project`:**

```sh
cd postarr && uv run python ../arrt/tools/mutation_sweep.py --project . m.json tests/
```

Without it the tool sweeps the curation project with the display plane's paths and
reports every mutation as drifted. How to read a sweep, budget one, and sweep the
browser suite: `docs/testing.md`.

The curation suite boots a real uvicorn server per test class of surface work.
Do not replace that with an in-process ASGI transport: Starlette does not run a
mounted sub-app's lifespan, and the lifespan is what makes the MCP mount work,
so an in-process test would pass against an app that fails every real request.

**That suite runs across cores** — `-n auto` is in the curation plane's
`addopts`, so `uv run pytest` is already parallel (118s → 21s, measured
2026-08-05). **Add `-n0` to debug a failure**: workers interleave output and a
`pdb` breakpoint has no terminal to stop in. The root suite runs in a fraction of
a second and is left serial.

**The root suite is not only the 2024 modules**, and believing that costs a
developer their first hour on the leg most likely to go red under them. It also
carries `tests/preferences/`, where this repo's artifact-versus-code contracts
live — plane isolation, the Library/Programming seam, the heartbeat, the norm
index, the label corpus, and the screen tables. Those span two projects by design: `test_screen_tables.py` reads
the *curation* plane's `http/static/app.js` against
`.prawduct/artifacts/information-architecture.md`, and neither plane's own suite
can see both. So a change made entirely inside `arrt/` — routing a screen,
editing those IA tables — is guarded by a leg in the repo root.

## The browser suite and the live suites

The client under `arrt/src/arrt/http/static/` is the product's only human
interface, and neither Python suite runs it: `-m browser` does, and you run it
whenever you touch anything under `static/`. The four live markers (`live_museum`,
`live_binary`, `live_api`, `llm_eval`) check foreign APIs and are deselected by
default; `live_api` and `llm_eval` spend real money, and every live run takes
`-n0`. Commands, setup and the reasons behind each rule: `docs/testing.md`.

**Every suite asks whether the client matches its documents; none asks whether
it is good to use.** When the question is the second one — a redesign, a run of
screen work, "the UI feels off" — follow `docs/ux-walkthrough.md` rather than
inventing a method: four passes, in order, and `arrt/tools/ux_walk.py` does the
first.
