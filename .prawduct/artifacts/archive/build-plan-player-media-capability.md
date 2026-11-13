---
artifact: build-plan
version: 2
scope: player-media-capability
branch: feature/player-media-capability
base: develop
working-branches: []
last_validated: 2026-11-11
depends_on:
  - artifact: player-contract
  - artifact: architecture
governed_by:
  - artifact: architecture
    dispositions:
      - "§ Direction, the Player makes only the requests contract/routes.json names → inapplicable because no route is added; the capability rides the existing wall heartbeat"
      - "§ Direction, a display device renders its own label and decides what its geometry allows → conforms: what a Player plays smoothly is observed and reported by the Player, never configured or computed by the server"
      - "§ Direction, the Library/Programming seam → inapplicable because nothing in either package changes"
partition: serial, one chunk; a contract minor, its fixtures and its prose are one atomic change
lifecycle: completed
archived: 2026-11-13
released_in: v0.11.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

## Goals

**Response taken:** Proceed, citing it: brookstalley/arrt#424, which the owner
told the advisor to build first ("yes to 424", 2026-11-11).

**Product:** Arrt Player is gaining an mpv renderer that plays animated and video
media (arrt-player#27). The owner wants Arrt walls able to use it, and the
contract has no way for a Player to say it can. The Player sends the capability
as soon as a `contract-v*` tag carries the field, so the contract change is what
unblocks the other repository.

**Scope: the heartbeat half only.** A heartbeat minor 5 adds
`capabilities.media`: the content kinds the display shows (`image`, `animated`,
`video`), and optionally the largest video frame it plays smoothly. Then the
package's minor (1.0.0 → 1.1.0) and the tag `contract-v1.1.0`.

**Decisions made by the advisor, for the owner to overrule (inferred).** *The
owner confirmed all four on 2026-11-13 (`.prawduct/owner-rulings.md`).*

- **The frame limit is in.** The Player measured it on a Pi 4 at 4K: a 720p clip
  plays with no dropped frames, and a 1080p one drops about a third. A yes/no
  would let a server send that 1080p clip.
- **The manifest half is deferred: no `duration_s` this time.** The manifest's
  `media.content_type` admits only `image/jpeg` and `image/png`, and the Library
  holds no moving media, so a duration would describe something no feed can
  carry. Adding moving media to a feed means adding content types, the owner's
  dwell rule (#424: the smallest whole number of plays that reaches a minimum
  dwell, cut at a maximum) with its two values, and a reader behaviour for a
  Player that cannot play a work. That is its own change. #424 stays open for it.
- **A heartbeat without `media` is a Player that shows still images**, read as
  `kinds: ["image"]`, the same way a heartbeat without capabilities is read as
  `manifest_majors: [1]`.
- **A reader ignores a kind name it does not know**, so a later minor may add one.

## Build Chunks

### Chunk 01: Heartbeat minor 5, `capabilities.media`

- **Description:** The schema, its fixtures and the contract's prose say how a
  Player reports the media it can show, and the server accepts the report.
- **Depends on:** none
- **Artifacts consumed:** `player-contract.md` § Versioning, § The package, § The heartbeat, minor 2 to 4
- **Deliverables:**
  - `contract/schemas/heartbeat.v1.schema.json`: `capabilities.media`, an object
    with `kinds` (required, unique, at least one of `image`, `animated`,
    `video`) and an optional `video_max_frame` (`width_px`, `height_px`, whole
    numbers of at least 1), which the schema permits only beside `video`.
  - Fixtures, each listed in `contract/fixtures/index.json`: valid ones for a
    minor 5 Player that plays video at a limit and for one that shows only
    images; invalid ones for an unknown kind, an empty `kinds`, and a frame limit
    without `video`.
  - `player-contract.md` § The heartbeat, minor 5.
  - `contract/pyproject.toml` version 1.1.0.
- **Tests:** the contract suite judges every fixture against the schema, each
  invalid one failing for exactly one reason; the curation suite's
  `test_player_surface.py` posts every valid heartbeat fixture to the real route,
  so the server accepting a minor 5 heartbeat is tested through its caller.
- **Acceptance criteria:** all four suites green. Each new invalid fixture is
  watched failing against the schema without the rule it names.
- **Type:** cumulative-final
- **Exposed API:** player-contract-heartbeat
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. Committed, then `/prawduct:critic cumulative` run and blocking findings resolved
  3. After the merge to `develop`, the annotated tag `contract-v1.1.0` is pushed
     and arrt-player is told the field exists

## Governance Checkpoints

One chunk, one cumulative review, one PR. The tag is cut from the merge commit on
`develop`, because `player-contract.md` § The package says a released tag is never
moved.
