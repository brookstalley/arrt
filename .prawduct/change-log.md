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
