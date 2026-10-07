---
artifact: build-plan
version: 1
scope: ux-walkthrough
branch: feature/ux-walkthrough
partition: serial — one builder; Chunk 02's critique lenses fan out to independent read-only reviewers, which write nothing in the tree
depends_on:
  - artifact: information-architecture
  - artifact: ia-proposal
  - artifact: user-scenarios
  - artifact: design-direction
  - artifact: accessibility-spec
last_validated: null
---

# Build Plan — The UX walkthrough, as a practice and a first run

## What this plan is

The owner, 2026-10-07: IA/UX/UI is the product's weakest point. Every guard the
surface has asks whether the client matches its documents
(`tests/preferences/test_screen_tables.py`, the browser suite); none asks
whether a screen is good to use. The owner asked for the method to be written
down as this repository's practice, "so we don't re-derive later", and then run.

| Chunk | What |
|---|---|
| 01 | The practice (`docs/ux-walkthrough.md`) and the Pass 1 harness (`arrt/tools/ux_walk.py`) with its test |
| 02 | The first walkthrough: Pass 1 run, Passes 2–3 run, findings synthesised and filed |

**Not in this plan:** fixing what the walkthrough finds (each finding goes to
the backlog or, for structure, to `ia-proposal.md` for a ruling); Pass 4, which
is people using the product and only the owner can arrange; visual-regression
gating in CI (the harness is run by hand, like `search_latency.py`).

## Requirements Confidence

**High** for Chunk 01: the method was proposed and accepted in conversation on
2026-10-07, and the harness reads, never writes. **Medium** for Chunk 02:

- [ASSUMPTION: the real library is reachable from this Mac over the network for
  Pass 1's real-data walk; if not, Pass 1 runs on the synthetic corpus alone and
  the report says so.]
- [ASSUMPTION: screenshots and the contact sheet are working material, kept out
  of the repository — it is public, and they are large binaries — in a
  gitignored output directory.]

## Status

- [x] Chunk 01: The practice, and the Pass 1 harness
- [ ] Chunk 02: The first walkthrough

### Chunk 01: The practice, and the Pass 1 harness

Done when:

1. `docs/ux-walkthrough.md` states the four passes, the synthesis, and the
   rules that make each pass worth running, with the *why* inline.
2. `arrt/tools/ux_walk.py` walks a running Arrt (`--base-url`) or a synthetic
   one it boots (`--synthetic N`), and for every declared route records
   screenshots (phone and desktop, light and dark), the page's headings,
   controls and links, and an accessibility scan; and writes `inventory.json`
   and a contact sheet `index.html`.
3. **The inventory is derived from the thing itself**: the declared set is
   parsed from `app.js`'s `ROUTES`; the reached set is crawled from the home
   page by links and by a sample of buttons that navigate by script, each
   recorded as which. Declared-but-unreached, and reached-but-undeclared, are each
   reported by name.
4. **It cannot write.** Every request that is not `GET`/`HEAD` is aborted by
   the harness and recorded, so pointing it at the real library is safe. Proven
   by a test that issues a write and watches it refused.
5. Each quiet state has its own output: a route with no instance to visit, an
   accessibility scan that could not run, and a scan that found nothing are
   three different lines.
6. A browser-marked test drives the harness against the suite's server.

### Chunk 02: The first walkthrough

Done when:

1. Pass 1 has run against the synthetic corpus and, if reachable, the real
   library; its contact sheet exists.
2. Passes 2 and 3 have run, each lens by an independent reviewer.
3. The findings are one ranked list, each tagged with lens, screen and whether
   `ia-proposal.md` already plans its fix — the screenshots stay in the
   gitignored `.ux-walk/`, because this repository is public, so a finding
   names its screen and the walk re-photographs it — in
   `.prawduct/artifacts/ux-review-2026-10.md`; actionable ones are filed through
   `/prawduct:backlog`.
4. Pass 4 is handed to the owner with its three tasks written out.
