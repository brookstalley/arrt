---
artifact: build-plan
version: 1
scope: wall-rotation-settings
branch: feature/wall-rotation-settings
partition: serial, one worktree. Two chunks; 02's client reads the API shape 01 writes
Critic mode: cumulative-final
depends_on:
  - artifact: ia-proposal
  - artifact: data-model
governed_by:
  - artifact: ia-proposal
    dispositions:
      - "§ Rulings (2026-10-11), ruling 2 (a theme has an order and is never shuffled; shuffle and the interval are the wall's) → conforms: this plan builds it"
  - artifact: architecture
    dispositions:
      - "§ Direction (operation logic only in the service layer; bindings thin) → conforms: one service method, two bindings"
      - "§ Direction (the Library/Programming seam) → conforms: wall and theme are both Programming; nothing crosses"
last_validated: null
lifecycle: completed
archived: 2026-10-16
released_in: v0.5.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — shuffle and the interval move from the theme to the wall (#353)

## What this plan is

Ruling 2 of 2026-10-11 (`ia-proposal.md` § Rulings): a theme has an order and is
never shuffled. Whether a wall shuffles, and how long each work stays up, are
settings of the wall that plays the theme. Today both are nullable fields on
`Theme`, and null means the deployment default.

## Goals

- **01: the store, the service, the migration, the API and MCP.** `Wall` gains
  `shuffle` and `rotation_interval_seconds`, both nullable, with null meaning the
  deployment default, as before. `Theme` loses both. One service method,
  `DisplayService.set_rotation(wall_id, *, shuffle, rotation_interval_seconds)`,
  takes the `UNSET` sentinel, as `update_theme` does today, and **republishes the
  wall's schedule** (`sync`). That differs from `set_mat_mode`, which leaves every
  slot where it is: changing the order or the pace changes the slots. The bindings
  are `PUT /api/walls/{id}/rotation` and `art_display(action='set_rotation')`. The
  theme's `shuffle` and `rotation_interval_seconds` go from `ThemeOut`, from
  `PATCH` on a theme, and from `art_theme(action='update')`. `ThemeDetailOut.shuffled`
  and `DisplayService.shuffles(theme)` go too.
- **Migration (`migrations.carry_rotation_to_walls`).** Each wall hanging a theme
  that set a value gets that value, and nothing else is copied. The theme columns
  are dropped after the copy is committed, which makes the migration safe to
  interrupt and to run more than once, the same shape as `walls_name_displays`.
  Tests pin each of these: a shuffled theme gives a shuffled wall, a set interval
  is kept, a theme that set nothing gives null (the default), a wall hanging
  nothing gets nothing, and an interrupted run is finished by the next open.
- **02: the client.** On Walls, the *How it rotates* panel on the wall's card
  becomes editable: an Order picker (*Deployment default* / *As curated* /
  *Shuffled*), an interval in minutes, and *Set*. It follows the mat panel's
  pattern: a status line, and no repaint that would close the disclosure. The
  Theme page loses its shuffle caption. Position now always decides the order of
  the theme itself, and only a wall may shuffle it.
- **Done when:** all three suites and the browser suite are green; each new test
  has been seen to fail against the unfixed code; `data-model.md`,
  `api-contract.md`, `information-architecture.md` (the Themes and Walls rows)
  and `architecture.md`'s settings line describe the code as it is.

### Decisions

- **Stored on the wall, not on the hanging** (the owner chose this 2026-10-13,
  asked with #370 in view). The columns go on `walls`, beside `mat_mode`, and
  not on `theme_assignments`. The settings survive hanging a different theme
  and clearing the wall. #370 (a wall filters its theme by aspect ratio) is
  also a fact about the wall, so it will go in the same place and needs no
  second mechanism. **#370 is not built here.** This plan only leaves the path
  from wall to schedule that #370 will use.
- **"Chosen where a theme is hung" is read as the wall's card on Walls**, where
  the hang control and the setup disclosure already sit. It is not a step added
  to the hang dialog: the settings are the wall's, and they outlive any one
  hanging. *Inferred; for the boundary review to show the owner.*
- **A theme with a setting and no wall loses the setting.** The ruling says a
  theme carries neither setting, and there is no wall to copy it to. The
  migration logs each loss, naming the theme and the value.
- **The interval is minutes in the client and seconds in the API.** Seconds stay
  in the store, the API and MCP, as today. The panel shows minutes because a
  curator thinks of a work staying up in minutes, and accepts decimals so 90 s
  can still be set.

*(2026-10-13, #370: `set_rotation`, `PUT /api/walls/{id}/rotation` and
`art_display(action='set_rotation')` were widened and renamed `set_playback`
and `/playback` before either was released; see `build-plan-wall-shape-filter.md`.)*

## Chunks

### 01 — store, service, migration, API, MCP
Files: `persistence/{records,sqlite,migrations,file}.py`, `programming/display.py`,
`http/{api,models}.py`, `mcp/{tools,bindings}.py`, tests under `arrt/tests/unit`
and `arrt/tests/integration`, and the artifacts named above.

### 02 — the client
Files: `http/static/screens/walls.js`, `http/static/screens/theme.js`, the browser
tests and their payloads, and the Themes and Walls rows in `information-architecture.md`.

## Status

- [x] 01 — store, service, migration, API, MCP
- [x] 02 — the client
