---
artifact: build-plan
version: 1
scope: household-schedule-lock
branch: fix/household-schedule-lock
partition: serial, one worktree. One chunk
Critic mode: cumulative-final
depends_on:
  - artifact: build-plan-wave-4e-schedule
governed_by:
  - artifact: re-architecture
    dispositions:
      - "§ The manifest is a schedule, not a playlist (no work on two walls at once, the owner 2026-10-08) → conforms: the rule is unchanged; what changes is which walls are rebuilt to keep it"
  - artifact: player-contract
    dispositions:
      - "§ Major 2 (a republish is a new document; the Player shows the slot covering its clock) → conforms: a neighbour's republish keeps the slot covering now, so no picture changes on it"
  - artifact: architecture
    dispositions:
      - "§ Direction (operation logic only in the service layer) → conforms: the change is in `schedule.py` and `DisplayService`; no binding changes"
last_validated: null
lifecycle: completed
archived: 2026-10-16
released_in: v0.5.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — two walls sharing few works no longer lock (#350)

## What this plan is

Two walls whose themes share only a few works can each end up showing a single
work for the whole three-day horizon. One wall is rebuilt against the other's
all-B schedule, so the only schedule obeying the household rule is all-A; the
other is then rebuilt against that, and the lock sustains itself. No sequence
of one-wall rebuilds can break it.

## Goals

- **Response taken:** proceed, citing #350 (a bug with a repro and an expected
  outcome: each wall cycles its theme, and a shared work is shown on each at a
  different time).
- **The owner's ruling (2026-10-13):** a wall's republish may rebuild the
  *slots to come* of every other wall that shares a work with it. The slot on
  each wall now is never changed. This vetoes the wave-4e decision of
  2026-10-09 that a republish never moves a wall nobody touched
  (`build-plan-wave-4e-schedule.md`), whose reason, "would swap a picture
  nobody asked to change", held only for the slot on the wall now.
- **Mechanism (mine):** when a wall is written, the walls whose published feed
  shares a work with it are its *neighbours*. The wall is built against only
  the slot covering now on each neighbour (the part a rebuild keeps), then each
  neighbour is rebuilt, in wall-id order, keeping its slot now, against the
  full slots of the walls already rebuilt in this pass and the kept slot of
  those still to come. One level only: a neighbour's rebuild does not rebuild
  its own neighbours, so one write rebuilds each wall at most once. A caller
  that writes every wall in turn (reconciliation, a startup catch-up) can so
  rebuild up to the square of the wall count; harmless at a household's few
  walls, and said here so it is not discovered. *Inferred.*
- **A neighbour's slots line up with the wall just built.** Breaking the lock
  is not enough: two walls' slots start seconds apart in practice, so with two
  shared works every neighbour slot would overlap one of each on the other wall
  and the household rule would give way at every slot. So the neighbour's slot
  on the wall now runs on until the slots after it are in step with the wall
  just built: by `(boundary − end) mod interval`, under one interval, the whole
  slot staying under two. Nothing on screen changes; the picture now stays up a
  little longer, and the two walls alternate from there. *Ruled by the owner,
  2026-10-14: the picture now may linger, under one more interval.*
- **A neighbour is rebuilt as its roll would rebuild it:** from its hung theme
  when the feed carries that theme (so a large theme is not narrowed to the
  works one horizon named), else from the works its feed carries. Either way
  `Keep`, never a fresh start. *Inferred.*
- **`Reconciliation.republished` keeps its narrower meaning:** the walls whose
  feed changed for the works in question. A neighbour's slots to come moving
  is not listed. *Inferred.*

### Decisions made mid-build

- **In step by phase, not to the next boundary** (settled by the goal). A wall
  at three minutes beside one changing on the hour has its next boundary up to
  an hour off; by phase it falls in step within three minutes. Seen in the
  service test, whose fixture runs the hall at an hour.
- **Bounded by the slot's start, under two intervals** (settled by "nothing on
  screen changes": a picture held indefinitely would be a change). Every step on
  the other wall is a pass, so a bound on the move alone let repeated steps
  lengthen one slot without limit.
- **A slot already clashing may run on** (settled by the household rule: the
  lesser failure). Before a work is allowed back, both walls show the one work
  left, a clash nothing could avoid. Refusing to run it on left the next slot
  overlapping both of the other wall's works for a whole interval.
- **A neighbour is movable only with two works no fixed wall holds**
  (`schedule.movable_walls`; settled by the household rule, raised by the
  Critic twice). One with a single work, or whose others a wall outside the
  pass always shows, has nothing to step aside to: discounting its slots to
  come sent the republished wall onto its one work and left a clash for the
  horizon where the old build avoided it. Fixed is every wall outside the pass
  and any neighbour already found fixed, asked again until nothing changes.
  Coarse in the safe direction: a wall wrongly thought fixed is built as before.
- **A neighbour that cannot be rebuilt keeps its schedule** (settled by "the act
  asked for succeeds"): a `ServiceError` there is logged by the neighbour's name
  and the republished wall's write stands, as before a pass existed.
- **One helper decides how a wall republishes keeping its picture**
  (`_republish`): the roll, a setting change and a pass all use it. They
  differ in one case, said there: a feed not of the hung theme is put right by
  the wall's own act and left alone by a pass beside another.
- **Reconciliation reads each feed as it reaches it**, since an earlier wall's
  pass may have rebuilt it.
- **Not solved, and said** (filed as #374): walls whose intervals are not multiples, and a
  republished wall with shorter slots than a neighbour when the two share only
  two works. The republished wall is built first, so the neighbour's long slot
  spans both works; the clash is named in the journal. Solving it means
  building walls longest-slot first, which changes who is built against whom on
  every republish; out of proportion while the house's walls run at one pace.
  In the `schedule` module docstring.

## Chunks

### Chunk 01: Neighbours are rebuilt with the wall

- `schedule.build` takes `movable`: other walls whose slots after the one
  covering now are about to be rebuilt, so only that slot counts against this
  wall. Property test: two walls sharing two works, rebuilt as a pass, never
  lock, and the household rule holds.
- `DisplayService._write_v2` rebuilds neighbours as above; logs each by name.
- Tests: #350's repro end to end (both walls show both works over the
  horizon, never at once); a neighbour's slot now is unchanged; a wall sharing
  no work is untouched to the byte (the one-feed-per-wall property, narrowed
  from "any other wall" by the ruling); repeated republishes keep it unlocked.
  `test_undo_puts_it_back_on_the_walls_whose_theme_holds_it` asserts per wall.
- Artifacts: `re-architecture.md` § The manifest is a schedule, `data-model.md`
  § Schedule entry, the wave-4e plan's decision (veto noted), the module and
  `sync` docstrings.

## Status

- [x] 01 — neighbours are rebuilt with the wall
