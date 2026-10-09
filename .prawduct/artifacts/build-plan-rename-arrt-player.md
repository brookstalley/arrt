---
artifact: build-plan
version: 1
scope: rename-arrt-player
branch: feature/rename-arrt-player
partition: serial — one mechanical chunk; a rename split across agents would collide on every import line
depends_on:
  - artifact: re-architecture
governed_by:
  - artifact: project-preferences
    dispositions:
      - "plane isolation (display imports no curation module) → conforms: the test keeps asserting the same property under the new names. The player's new package, arrt_player, shares a prefix with the server's, arrt, so the test is watched failing once against a planted `import arrt` in an arrt_player module, and passing for arrt_player's own imports, after the rename"
      - "the two planes agree on the heartbeat's filename and its instant's key by construction → conforms: only the source paths the test reads are renamed"
      - "the mechanical norm-index rows (formatting, naming, imports) → conforms: every renamed import is re-sorted by ruff, and each plane's lint and format run"
  - artifact: nonfunctional-requirements
    dispositions:
      - "the display plane never requires the curation plane to be reachable → conforms: the rename changes only names. The one behaviour change the review brought in, the Player refusing a relative CACHE_DIR or TV_TOKEN_FILE at startup, is a config refusal that reads no server"
last_validated: null
---

# Build Plan — Postarr becomes Arrt Player

## What this plan is

On 2026-10-08 the owner renamed the Player again (#311). The first name chosen
was "Poster", because "the playback side … is just a player like plex or
jellyfin and not really a *arr app". That name was dropped the same day: `poster`
is taken on PyPI, and in this repo the word already means two other things,
Lidarr's poster cards on Artists and a poster as a kind of object that
selection treats as not the artwork itself. The owner chose the Plex and
Jellyfin convention instead, where clients carry the server's name:

| | Before | After |
|---|---|---|
| Product name in prose | Postarr | **Arrt Player** |
| Project directory | `postarr/` | `arrt-player/` |
| Distribution name | `postarr` | `arrt-player` |
| Import package | `postarr` | `arrt_player` |
| Run command | `python -m postarr` | `python -m arrt_player` |
| Wave-5 repository | Postarr | `arrt-player` |

Later platforms follow the same pattern ("Arrt for Apple TV", the Arrt
screensaver) when they are built. This plan names only what exists today.

**It lands before wave 4**, because wave 4 adds most of the Player's new modules
(the wall loop, driver and label renderer split), and each would otherwise be
renamed afterwards.

**Unlike the 2026-10-01 rename, no name changes meaning.** "Postarr" only ever
named the Player, so one pass is safe, and an empty grep for `postarr` proves
the rename is complete.

**The new names share a prefix with the server's.** `arrt_player` starts with
`arrt`, and `arrt-player/` starts with `arrt`. Anything that tells the planes
apart with an unanchored prefix (`startswith("arrt")`, a glob `arrt*`, a path
regex without a separator) would now treat the Player as the server. As
measured 2026-10-08, the plane-isolation test anchors on `name == "arrt" or
name.startswith("arrt.")`, and the wave-5 filter's pass 1 matches `b"arrt/"`,
so both are safe. The chunk re-runs that search over the renamed tree, not the
old one.

**Prose keeps its role names.** "The Player", "the display plane" and "the
curation plane" are roles and stay unchanged. "Postarr" in prose becomes
"Arrt Player", or "the Player" where the role reads better.

**History is left as written.** Archived plans, `change-log-archive/`, completed
change-log entries, the dated entries in `operator-verification.md`, the
2026-10-05 norm-sweep measurements in `project-state.yaml`, and the live build
plans whose chunks are all ticked record what was true on their day.
`operator-verification.md` gets a new entry at the top of Pending that says
older entries keep their day's paths. `change-log.md` gets one dated line at its head
saying that Postarr is the former name of Arrt Player. `re-architecture.md`'s
naming paragraph gets the 2026-10-08 sentence and keeps the old names as
history.

## Requirements Confidence

**High.** It's a rename with three green suites on each side, and the suites
are the proof.

- `[ASSUMPTION: the Pi keeps its checkout at /opt/samsung-frame-art-loader and
  its unit name display.service (a role name); only WorkingDirectory and the
  module change, as in both earlier renames | MED impact | user can correct]`
- `[ASSUMPTION: the wave-5 filter's pass 2 gains a fourth path, arrt-player/,
  renamed to the root like the other three; pass 1 is unchanged because its
  `b"arrt/"` prefix does not match `arrt-player/`. The scratch-clone
  measurement is re-run at the split, as it already says | LOW impact | user can
  correct]`

## Status

- [x] Chunk 01: Postarr → Arrt Player

### Chunk 01: Postarr → Arrt Player

- **Type:** cumulative-final
- **Surfaces** (measured 2026-10-08: `git grep -niP 'postarr'` finds 512 lines in
  113 files, 58 of them under `postarr/`):
  - `git mv postarr arrt-player`, then `git mv` the package to
    `arrt-player/src/arrt_player`. Every import, `pyproject.toml`'s project name,
    ruff's first-party setting and any tool configuration. Regenerate
    `uv.lock`.
  - `deploy/display.service` (`WorkingDirectory`, `python -m`) and `deploy/README.md`.
  - `.github/workflows/suites.yml`: the `postarr` job, working directories and
    result paths.
  - Root: `pyproject.toml`'s excludes, `requirements.txt`, `.env.example`, and
    `tests/` wherever they name the Player's paths or package.
  - `.claude/rules/learnings/display.md` and `tooling.md` path globs.
  - `contract/routes.json` and the schemas' descriptions.
  - The curation plane's two mentions (under `arrt/`).
  - `CLAUDE.md`, `README.md`, `docs/`, live artifacts, and `project-state.yaml`
    (including `test_commands`). This includes the two live plans
    that still have unticked chunks (`build-plan-display-state.md`,
    `build-plan-displays-and-label-outputs.md`), since their walks run under the
    new names.
  - `re-architecture.md` § Order of work, wave 5: the four-path recipe and the
    new repository name.
  - The harness's auto-memory, where it names Postarr.
  - The local `.venv`: it does not move with `git mv`, so rebuild it on Python 3.13
    under `arrt-player/` (#153), and never commit the pin.
- **Tests:** all three suites pass, including `--group raster`, with no test
  weakened. Then three checks, each keyed on something different:
  1. **The grep.** `git grep -niP 'postarr'`, excluding the history files: 512
     lines before, and afterwards only the dated history lines this plan names.
  2. **The roster.** `git diff -M --name-status` against the parent shows every
     tracked file under `postarr/` as a rename into `arrt-player/`, and nothing
     else removed.
  3. **The prefix.** A search for unanchored `arrt` prefixes (`startswith("arrt")`,
     `arrt*`, regexes without a separator) over the renamed tree. The
     isolation test is watched failing against a planted `import arrt` in an
     `arrt_player` module, then reverted.
- **Measured 2026-10-08:** all three suites pass, with lint and format. The
  grep leaves only the lines recording the names: `re-architecture.md`'s
  naming paragraph, wave-5 recipe and seam note, `product-brief.md`'s naming
  paragraph, and `project-state.yaml`'s naming comment and dated sweep. This
  chunk's own text names `postarr/` as what was moved, which is why it stays. Roster: 71 tracked files under `postarr/`, 71 renamed into
  `arrt-player/`, none added or deleted. Prefix: one unanchored
  `startswith("arrt")`, in `arrt/tests/contract/test_player_surface.py`, left
  because it filters only the server's own process. The isolation test failed
  on a planted `import arrt.config` and passed once it was removed.
- **Operator verification:** yes. The Pi's unit must be reinstalled from
  `deploy/`, and its venv rebuilt under `arrt-player/`, or it starts a module
  that no longer exists. The commands are in `deploy/README.md` § The Player
  renamed Arrt Player, and the queue entry points there.
- **Done when:** the three suites, lint and format pass, as do the three checks;
  CI is green on the branch; the queue entry exists; the cumulative Critic has
  reviewed the branch.
