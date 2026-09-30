# Change Log — Samsung Frame Art Loader

<!-- Append new entries at the top. Each entry is a ## section.
     This file is separate from project-state.yaml to reduce merge conflicts
     when multiple branches add entries simultaneously.

     # Tagged entries

     Add a tag-line directly under each ## header recording which build-plan
     chunks the entry shipped, which release it belongs to, and its rollup
     scope.

     **Nothing is REGENERATED from these tags any more — but they are still
     READ, and the difference matters when you write one.** `prawduct-hook
     regen-views` once rebuilt the build-plan `## Status` block, a release-notes
     view and a `scope_rollups:` block from them; prawduct v3.2.8 retired that
     command and the `views_enabled` switch that governed it, so this header
     spent three releases telling readers to run something that no longer
     exists.

     What survives is consumption, not generation. `scope=` and the *absence* of
     `release=` are how release-readiness enumerates work that has not shipped —
     which is why any value at all in `release=`, a placeholder included, drops
     that entry's whole scope out of the pending set. The PR flow refuses a
     branch whose entry carries no `scope=`. Only `status=` is inert now, and
     the Status checkboxes are ticked by hand and believed by every reader.

     Format:

         ## YYYY-MM-DD: title (vN.M.P)

         <!-- prawduct: chunks=00,01,02 | release=v1.3.18 | status=shipped | scope=v1.4 -->

         **Why:** ...

     Recognized keys:
       chunks   - comma-separated chunk IDs (zero-padded, must match
                  build-plan.md ## Status headers exactly: `Chunk 00:`)
       release  - version string (used by the release-notes view)
       status   - shipped | merged (legacy). Write a new entry with NO
                  status= on the feature branch: a statusless tagged entry
                  is the release-pending state, and it becomes "merged" by
                  construction when its PR lands — no stamp, no post-merge
                  bookkeeping commit (protected branches take commits only
                  by PR). Flip to `shipped` as part of release-prep when
                  the integration branch is released (gitflow), or write
                  `status=shipped` directly in the closing PR when the
                  PR's base IS the release surface (trunk; include
                  `release=vN.M.P` when the product tracks versions —
                  release-notes groups by it) — either way the tag merges
                  atomically with the work it describes.
                  `merged` is a legacy stamp some logs carry; it is treated
                  as statusless. Don't invent states — the three above are
                  the whole vocabulary.
       scope    - rollup identifier (e.g., v1.4) -->

<!-- Older entries live in .prawduct/change-log-archive/YYYY-MM.md, moved there verbatim by `prawduct-hook archive-change-log`. -->

## 2026-09-30: The Player contract (wave 1)

<!-- prawduct: scope=wave-1-contract -->

**Why:** Wave 2 builds both ends of the HTTP channel between Curatarr and
Displayarr. The contract between them has to exist first, and be tested against
the code that already writes and reads it, so neither side is built against a
guess.

**What:**
- `player-contract.md` is the contract's home. JSON Schemas (Draft 2020-12) and
  indexed fixtures live under `contract/`.
- **Major 1** describes the manifest and heartbeat as written today, plus wave
  2's additive changes: a content-addressed `media` reference per entry, a
  `schema` key on the heartbeat, the routes, the per-wall bearer token, status
  codes, and an error model that always keeps the cache.
- **Tests on three sides:**
  - The root suite checks that fixtures and schemas agree. Every invalid fixture
    breaks exactly one rule, the one its filename names.
  - Curation validates manifests its real builder writes, and runs its heartbeat
    reader over the fixtures.
  - Display runs its manifest reader over the fixtures, including refusing
    major 2 as an unsupported version, and validates the heartbeat it writes.
- Eight deliberate breakages, four per plane, were each caught by the new tests.
- `jsonschema` is declared in all three `dev` groups, rather than inherited
  indirectly in one of them.
- Each `date-time` is backed by a pattern, because the common validator skips
  `format` unless an optional package is installed. The dry run proved it: a
  timestamp without an offset passed on `format` alone.

## 2026-09-30: Curatarr and Displayarr; a token per wall; wave 0 closed

<!-- prawduct: scope=re-architecture -->

**Why:** The operator made three rulings: "wave 0 -- abandon. We'll rebuild with
this new plan"; "each wall gets a token"; and "The library/performance
controller will be Curatarr, the device side playback will be Displayarr."

**What:** Documentation only.
- The names are recorded in `re-architecture.md`, the product brief's Identity,
  `project-state.yaml`, `CLAUDE.md` and the README. The GitHub repo and the
  Python packages are not renamed yet.
- Per-wall tokens are recorded in `re-architecture.md` § Seam 2, with a
  decision block, in `security-model.md` (option b chosen) and in
  `api-contract.md` (`401` and `403`). The token is checked on every wall route
  and on media, which is the advisor's extension and vetoable. It lands in
  wave 2.
- Wave 0 is closed. The v1 open chunks are abandoned, and a table maps the
  requirement each served to where it is rebuilt: power control becomes a
  Displayarr stream in wave 6+, the dark hours go to the wave 4 schedule, backup
  goes to wave 3, and retiring the legacy modules goes to wave 5. The power
  norm's status and interim rule now point there.
- Three open questions are closed.

## 2026-09-30: Wave 1 begins: what is showing versus how, the schedule, scenes, and the waves re-cut

<!-- prawduct: scope=re-architecture -->

**Why:** A review of the morning's re-architecture found internal contradictions
in the forward notes and four structural gaps. Separately, the operator framed
the server's responsibilities: the server should manage media without knowing
walls, yet walls must be coordinated without configuring each Player. This
entry writes the resulting model and the approved review points into the
artifacts.

**What:** Documentation only. No code changed.
- `re-architecture.md` gains § What is showing, and how it is shown:
  - Walls exist only in Programming, as logical targets. Settings flow down and
    capabilities flow up.
  - From schema major 2 the manifest is a time-anchored schedule, with scenes as
    a live override that expires back to it, and a staging hint.
  - The resolution floor becomes a Library quality profile.
  - These are recorded as vetoable decisions, each naming its author.
- Seam rules 1, 2 and 4 move from wave 6 to wave 2, and rule 3 (the store split)
  to the start of wave 3. Rule 4 gains a reconciliation duty at startup. Facet
  population joins wave 6+, ahead of smart playlists. Major 2 carries every
  breaking change at once.
- The contradictions are reconciled across 12 other files: the floor options,
  who judges adequacy, the wave for label mode, mat settings and the
  presentation master, and when the system becomes distributed. The heartbeat
  auth deadline moves to before wave 2.
- Missing notes are added: two norm-index rows and two findings files. The open
  questions are re-sorted in `project-state.yaml`, with two settled, and two
  technical decisions are added.
- Two home-directory paths that exposed a username are removed from the public
  artifacts.

## 2026-09-30: Direction change — a Library/Programming server and a Player, documented before any code

<!-- prawduct: scope=re-architecture -->

**Why:** The operator decided to split the product into an *arr-style server,
holding the Library (procure, maintain, upgrade, enhance) and Programming (walls,
playlists), and a Plex-style Player that renders to any screen, with the e-ink
label optional and a caption in the mat as the alternative. The decision was made
in the operator's homelab workspace. This entry brings that conversation into
the repo so the next session starts from it rather than from the old target.

**What:** Documentation only. No code changed.
- **New:** `artifacts/re-architecture.md`. It holds the owner's rulings in their
  words, the three roles, both seams, the two tag layers, Watches, Player
  outputs, the deployment target, waves 0–6 and the open questions.
- **Amended, with recorded decisions:**
  - `architecture.md` § Direction: the manifest channel is amended and
    `in-transition`; two rulings; four seam norms born `in-transition`; Decision
    Log entries reversing the 2026-07-20 co-location.
  - `nonfunctional-requirements.md`: the display-independence norm.
  - `accessibility-spec.md`: the legibility norm now covers any label surface;
    § The television admits a caption in the mat.
  - `data-model.md`: two rulings, the reversal of the `tv_display` rendition, a
    role for every entity, and § Planned entities.
  - `product-brief.md`: Vision, Identity, flows and scope.
  - `project-state.yaml`: the `multi_process_distributed` flip recorded, a
    technical decision, an open question, and the artifact manifest.
  - `project-preferences.md`: norm index rows.
- **Forward notes** (as-built text left intact): every other artifact whose
  target-state claims change, plus `README.md`, `CLAUDE.md` and
  `deploy/README.md`.
- **Parked, not archived:** the round-2 UI plan, on local branch
  `curation-ui/rulings-and-plan`. This work is on `develop`, branched from `main`.
