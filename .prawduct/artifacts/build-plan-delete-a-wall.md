---
artifact: build-plan
version: 1
scope: delete-a-wall
branch: feature/delete-a-wall
base: develop
working-branches: []
partition: serial, one worktree. 03's dialog calls 02's route, and both edit the wall's Edit… (`screens/walls.js`), which the #400 fix on the branch below this one also rewrote.
depends_on:
  - artifact: data-model
  - artifact: information-architecture
  - artifact: api-contract
  - artifact: player-contract
  - artifact: design-direction
  - artifact: accessibility-spec
governed_by:
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer → conforms: `DisplayService.delete_wall` does the work; `DELETE /api/walls/{wall_id}` and `art_display(action='delete_wall')` call it and add nothing"
      - "the Library/Programming seam (one-way imports, the facade, no cross-seam foreign keys, events) → conforms: the delete is Programming's own rows and files; history is reached as it is today, through the facade's `record`, and no Library row names a wall"
      - "the theme manifest file is the only channel from curation to display → conforms: the deleted wall's feed is removed with it and the Player learns from `GET /client`, which stops listing the wall, as an unassign already does"
  - artifact: data-model
    dispositions:
      - "per-device runtime state never lives in the catalogue → conforms: the wall's heartbeat file, outside the catalogue, is removed after the commit, as a removed Player's is"
      - "identity, work vs image, derived artifacts, pictures kept forever → inapplicable because a wall holds no work, image or picture"
  - artifact: information-architecture
    dispositions:
      - "the *arr layout → conforms: *Delete…* is the last part of the wall's *Edit…*, as a theme's is (ruling 4 of 2026-10-27)"
      - "navigation is a link; an act is a button → conforms: *Delete…* is a button, confirmed in words"
  - artifact: design-direction
    dispositions:
      - "token values live in `app.css` → conforms: no colour is added; *Delete…* is quiet, as a theme's and a Player's are"
  - artifact: accessibility-spec
    dispositions:
      - "norm 2 (WCAG 2.1 AA; colour never the sole carrier) → conforms: the confirmation is `core/confirm.js`'s dialog, named in words; the axe scan covers the Edit… dialog with *Delete…* in it and the empty Walls page"
      - "norm 1 (the label) → inapplicable because nothing here changes what a Player draws"
  - artifact: security-model
    dispositions:
      - "text from outside reaches the page as text → conforms: wall, theme and Player names in the confirmation are set through `el()`"
last_validated: 2026-10-30
---

# Build plan: deleting a wall (#391)

## Goals

**Response taken:** ask, in one batch. #391 named four open questions; the
owner answered them on 2026-10-30, each with a recommendation in front of them:

1. **Permanent, and the history stays.** The wall's row, its theme assignment,
   its feed and its heartbeat go; its showings, its history events and the
   scenes it was in stay, as `data-model.md` already says they outlive a wall
   (Showing, History). Confirmed in words and not undone, as deleting a theme
   and removing a Player are. *(The owner's ruling.)*
2. **A wall in the live scene: its pin drops and the scene goes on** for the
   other walls. *(The owner's ruling; the owner was offered refusing until the
   scene is released, and chose this.)*
3. **A wall a theme hangs on is deleted anyway**, and the confirmation names
   the theme and says it stays. *(The owner's ruling.)*
4. **The last wall can be deleted**, and the empty Walls page then offers
   *Add wall…*. *(The owner's ruling.)*

**Product:** a household rearranging its rooms can take a wall away as it can
add one. Today a wall that is no longer a place is stuck on Walls for good.

**Architecture: what must hold.**
- **The Player needs no contract change.** A deleted wall drops out of
  `GET /client` as an unassigned one does; the Player stops showing it on its
  next poll (`player-contract.md`, the 403 for "a wall … the server does not
  hold"). Nothing in `contract/` changes.
- **Every dependant is decided, not discovered by a foreign key.** The schema
  refuses the delete while `theme_assignments` or `label_outputs` names the wall;
  each row below is a decision:

  | What names the wall | On delete |
  |---|---|
  | `theme_assignments` | removed; a selection it hung is retired as `clear_wall` retires one |
  | `label_outputs.wall_id` | set to null: the panel stays recorded, captions nothing, and is offered to other walls |
  | `walls.display_id` | goes with the row, freeing the screen |
  | a pin in the scene being assembled | removed, so the draft can still be applied |
  | a pin in the live scene | kept as the scene's record; the wall simply leaves it (ruling 2) |
  | `showings`, `history_events`, applied scenes | kept (ruling 1); no foreign key, by design |
  | `theme-manifest-{id}.v2.json`, `display-heartbeat-{id}.json` | removed after the commit |

**Decisions made in planning, the owner's goals settling them:**
- **A wall is created at start-up only when the file has never had walls.**
  `establish_the_wall` seeds one whenever the table is empty, so ruling 4 would
  bring the last wall back at the next restart. It seeds instead only when the
  `walls` table did not exist before this open: a new file, or one from before
  walls (the one-time move it already does). An empty table is the curator's.
  No stored marker is added. *(Inferred from ruling 4; the alternative, a
  persisted "seeded" flag, adds a format for one bit the schema already says.)*
- **No new history event kind.** Deleting a theme and removing a Player record
  none; this follows them, with a log line. Two kinds that name a wall without
  its name (`work.left_theme`, `work.excluded`) gain `wall_name` in `detail`, as
  `wall.hung` has, so a deleted wall's history still names it going forward.
  Older events keep reading "a wall no longer recorded". *(Inferred: ruling 1
  keeps the history, and a history that cannot name its wall keeps less of it.)*
- **The live-scene pin is kept, not deleted** (table above). *(Inferred from
  ruling 2: "the scene goes on" for the walls left, and an applied scene's pins
  are its record, `data-model.md` § Scenes retention.)*

**Decisions made mid-build:**
- **Five `art_display` action descriptions shortened** (`status`, `sync`,
  `add_wall`, `remove_client`, `issue_client_token`), meaning kept, so the tool's
  description stays inside the 2 KB a client reads (`test_mcp_surface.py`'s
  budget) with `delete_wall` in it. Settled by "do it right": the alternative,
  leaving `delete_wall` out of the menu, hides it from an agent.
- **A new file interrupted between its schema and its first wall opens with
  none**, and Walls offers *Add wall…*: the state ruling 4 already designed. A
  file from before walls is recognised by `themes.is_active` and still carried.
  *(Inferred; not an alignment-pass miss, since ruling 4 settles what an empty
  catalogue looks like.)*
- **A live scene's pin on a deleted wall** goes through one helper
  (`DisplayService._pins_on_held_walls`) on every scene path, so the wall has
  left the scene everywhere at once: no feed republished, no history line, no
  name.

**Carried from the #400 review** (`fix/walls-stale-edit`, the branch below):
the press guard keys on the wall, not the button, so *Choose its Player…* and
*Edit…* on one card cannot open two dialogs; a read that returns to a Walls
page painted since it began opens nothing (`control.isConnected`); and the
"no longer recorded" refusal beside *Edit…*, unreachable until now, gets its
test.

**Tradeoffs accepted:** no undo (ruling 1). History events written before this
change for `work.left_theme` and `work.excluded` stay nameless once their wall is
deleted; worth revisiting only if History on a deleted wall becomes something
the owner reads.

**Level:** High. Every dependant is enumerated from the schema and the code
(`git grep -l wall_id -- arrt/src`, 2026-10-30), and each delete has a
precedent to follow.

## Chunks

### Chunk 01: This plan

- **Type:** doc-only
- **Surfaces:** this plan.
- **Done when:** the root suite passes.

### Chunk 02: The server deletes a wall

- **Type:** code
- **Surfaces:**
  - `arrt/src/arrt/programming/display.py`: `DisplayService.delete_wall(wall_id)`, one transaction over the table above, files after the commit, a log line; `wall_name` in the two event kinds' `detail`.
  - `arrt/src/arrt/programming/store.py` and `arrt/src/arrt/persistence/sqlite.py`: `remove_wall`.
  - `arrt/src/arrt/persistence/migrations.py` and `arrt/src/arrt/persistence/file.py`: seed only when the file had no `walls` table.
  - `arrt/src/arrt/http/api.py`: `DELETE /api/walls/{wall_id}`.
  - `arrt/src/arrt/mcp/bindings.py`, `arrt/src/arrt/mcp/tools.py`: `art_display(action='delete_wall')`.
  - Artifacts: `api-contract.md` (the route and the tool), `data-model.md` (Wall: how one ends, and the seeding rule), `information-architecture.md` (Walls' empty state).
- **Done when:**
  - A unit test per row of the table, each with a wall that has that dependant and a second wall that keeps its own, so a delete that took both fails.
  - The draft scene can be applied after its wall is deleted; the live scene goes on for the other wall and its record keeps both pins.
  - Deleting the last wall and reopening the file leaves no wall; a new file still gets one, and so does a file from before walls.
  - `GET /client` for the Player that showed it no longer lists it, and its manifest and heartbeat routes answer 403.
  - Route and tool each reach the service with a wall that exists and refuse one that does not, through a real server.

### Chunk 03: *Delete…* in a wall's Edit…, and Walls with no wall

- **Type:** cumulative-final
- **Visual change:** yes
- **Surfaces:**
  - `arrt/src/arrt/http/static/screens/walls.js`: *Delete…* last in *Edit…*, asked with the dialog closed, naming what it hangs (which stays), the Player that stops showing it, its label panel, and that its history stays; the empty page offers *Add wall…*; the #400 carry-overs above.
  - `.prawduct/artifacts/information-architecture.md`: the Walls rows (Edit…, empty state).
  - `.prawduct/operator-verification.md`: an entry for the owner's walk.
- **Done when:**
  - A browser test deletes a wall that hangs a theme and has a Player and a label panel, reads the server afterwards, and checks the confirmation names each.
  - Cancel deletes nothing.
  - Deleting the last wall leaves the empty page with *Add wall…*, and adding one from it works.
  - The #400 carry-overs each have a test seen to fail first.
  - The axe scan covers the dialog and the empty page.
  - The full browser suite, the three suites, and `/prawduct:critic cumulative`.

## Verification record

- 03: the axe scan ran by hand, as the UI pass's did (the suite does not fetch
  axe-core): `ux_walk.scan` from a temporary test over the suite's fixtures, on a
  wall hanging a theme with a Player and a label panel: its *Edit…* with
  *Delete…*, the *Delete Study?* question, and the empty Walls page, at 1280 wide
  light and 390 wide dark: clean, 2026-10-30. The temporary test is not kept.
