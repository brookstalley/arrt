---
artifact: build-plan
version: 1
scope: upgrades
branch: feature/upgrades
partition: 01 delegated to one agent in an isolated worktree — building and labelling a few hundred image pairs by eye is long, image-heavy work that would fill the coordinator's context, and it writes only under `arrt/tools/upgrade_gate/` (the findings move into `.prawduct/artifacts/` at merge). 02-06 serial: 03 and 04 share the records 03 designs, and 05 draws them
depends_on:
  - artifact: upgrades
  - artifact: re-architecture
  - artifact: data-model
  - artifact: architecture
governed_by:
  - artifact: re-architecture
    dispositions:
      - "§ Order of work puts upgrades in wave 6+ and the quality profile in wave 4 → departure by the owner's direction of 2026-10-02 ('let's move from UI to discovery, acquisition, retry and upgrade'), recorded in `upgrades.md` and as a dated note in § Order of work; the presentation master stays in wave 4, and the NAS move (wave 3) follows this plan"
      - "DECISION: the profile has a minimum and a cutoff above which the Library stops looking → amended by the owner's ruling of 2026-10-02 ('No cutoff, but back off searches'), recorded in `upgrades.md` § The owner's rulings and as a dated note beside the decision; the minimum stays"
      - "Watches fire security and observability re-derivations → inapplicable to this plan: it adds no standing intent-driven discovery and no scheduled job (both are the scheduler plan's); upgrades here run only when a curator or agent asks"
  - artifact: data-model
    dispositions:
      - "a persisted format is a lock-in decision; enumerate the questions first → binds Chunk 03: Q38–Q42 (`upgrades.md`) are added to § What this data must answer before fields are designed"
      - "derived artifacts are regenerated, never transported → conforms: a swap regenerates the TV rendition from the new original; the superseded original is a master, not a derived artifact"
      - "constraint 16, a partial tile fetch never replaces a complete original → conforms, and is step 4 of the upgrade decision"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer → binds Chunks 02–05: the gate, the search and the swap are Library services; HTTP and MCP are thin bindings"
      - "Library/Programming seam → conforms: upgrades are wholly Library; Programming learns of a new image through the existing `work.image_changed` event, as it does today"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider; the vision model is the one paid path → conforms: the gate is local compute and a swap keeps the mat colour, so an upgrade spends nothing"
      - "the Pi's memory: one fetch at a time → binds Chunks 01 and 04: the gate's compute and a staged fetch are measured against it, and run in the acquisition worker's one slot"
  - artifact: dependency manifest (`project-preferences.md` § Dependencies)
    dispositions:
      - "every new library is justified with alternatives → binds Chunk 01: any IQA or vision dependency (OpenCV, pyiqa/PyTorch, imagehash) is chosen by measurement and recorded"
  - artifact: information-architecture
    dispositions:
      - "a page an *arr app has goes where it puts it, by its name → [DECISION: the held-works listing is Wanted › **Upgrades**, not Radarr's 'Cutoff Unmet', because the owner ruled there is no cutoff; it sits where Cutoff Unmet sits, beside Wanted | the *arr name would describe a rule Arrt does not have | owner can veto]; the blocklist is Activity › Blocklist, as in every *arr app"
  - artifact: security-model
    dispositions:
      - "text from outside Arrt reaches the page as text; links out are built from an item id → binds Chunk 05: a scan's source, title and the gate's reasons are shown as text"
      - "fetches go only to the sources Arrt already knows → binds Chunks 03–04: an upgrade fetches only scans a configured source returned, never a URL typed or supplied by a model"
  - artifact: observability-strategy
    dispositions:
      - "an acquisition outcome is a structured event, not prose (backlog #70) → binds Chunk 04: each search, decision, swap, refusal and revert is an event with the work id"
last_validated: null
lifecycle: superseded
archived: 2026-10-03
superseded_by: "backlog #177 (manual upgrades), #178 (scheduler), #179 (tacularr idea) — parked by the owner as a research and planning spike, 2026-10-02"
unbuilt_at_archive: "6 of 6 Status items still unticked (Chunk 01: Measure the gate, Chunk 02: The gate as a Library service, Chunk 03: Finding scans for a held work, …) — the scope shipped, but this plan did not finish with it"
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — Upgrades (manual)

## What this plan is

The first of two plans for `upgrades.md`: finding a better image for a work
you already hold, and taking it safely, when a curator or an agent asks. The
next plan adds the scheduler that asks on its own.

| Chunk | What |
|---|---|
| 01 | Measure the gate: what tells "same work, faithful, better" on real scans |
| 02 | The gate, as a Library service |
| 03 | Finding scans for a held work, and recording what was found and why |
| 04 | Taking a scan: staged fetch, verify, swap, keep the old, revert, blocklist |
| 05 | Wanted › Upgrades, the work's image history, Activity › Blocklist, MCP |
| 06 | The owner's review |

**Not in this plan:** the scheduler and its size-tier cadence, System › Tasks,
per-museum rate limits and escalating backoff, the daily cap (next plan);
Watches; the presentation master (wave 4); the NAS move (wave 3, after these).

## What I would do differently

**Measure before designing the gate, and expect to be surprised.** The
riskiest sentence in `upgrades.md` is "faithful reproduction", and nothing in
the repo measures it today. Chunk 01 is deliberately a measurement chunk with
no product code, so that thresholds come from real pairs of scans rather than
from the research's defaults. If the measured signals cannot separate a
museum scan from a visitor's photograph, the plan stops there and the owner
chooses between a paid model judgement and curator review for upgrades.

## Requirements Confidence

**Medium.** The flow, the decision order, the swap and the surfaces are clear
from the owner's rulings and the *arr / tacularr patterns. The gate's signals
and thresholds, the minimum increment, and the gate's compute cost are not
known; Chunk 01 resolves them.

Open assumptions:
- [ASSUMPTION: an upgrade's candidates come from the same sources a re-search uses today (Commons, the Art Institute of Chicago), found by the work's Wikidata item and museum identifiers; no new source is added | MED impact | owner can correct]
- [ASSUMPTION: size is the long edge in pixels, as the fetch caps measure | LOW impact | owner can correct]
- [ASSUMPTION: a superseded original is kept until the next successful backup after the swap, then reclaimable | MED impact | owner can correct]
- [ASSUMPTION: the per-work "Don't look for better" mark stops automatic searches only (scheduler plan); a curator's Search still runs | LOW impact | owner can correct]
- [ASSUMPTION: the Library screens branch's #172 marks are not needed here; this plan branches from develop and will merge after it | LOW impact | owner can override]

## Status

- [ ] Chunk 01: Measure the gate
- [ ] Chunk 02: The gate as a Library service
- [ ] Chunk 03: Finding scans for a held work
- [ ] Chunk 04: Taking a scan
- [ ] Chunk 05: The surfaces
- [ ] Chunk 06: The owner's review

### Chunk 01: Measure the gate

**Type:** doc-only

0. verify-api: read the research pass on image quality assessment (current
   no-reference and full-reference measures, museum digitisation standards,
   same-work matching, CPU cost) and the libraries it names, from their source
   and docs, before choosing anything.
1. Build an evaluation set from the dev library's 40 held works: other images
   of each work from Commons (the work's Commons category and `P18`) and the
   Art Institute (alternates), and negatives — gallery photographs of the same
   works (camera EXIF, visible frame or wall), crops and details, and other
   works by the same artist. Label each pair by eye; the owner confirms a
   sample.
2. Compute the candidate signals for every pair: perceptual hash distance;
   feature-match inlier ratio and the homography's departure from a similarity
   transform; a full-reference measure at the held image's scale after
   alignment; clipped-highlight share; colour distance; border detection; a
   no-reference quality score at native size; EXIF camera presence; each
   one's CPU time and peak memory.
3. Choose the signals and thresholds that separate the labels, and the minimum
   increment; record the false-accept and false-refuse rates.

Done when: `upgrade-gate-findings.md` records the set (counts per label, where
each came from), every signal's separation, the chosen gate with its measured
error rates, the compute cost on this Mac with the Pi's ceiling reasoned, and
the dependency choice with its alternatives; the measurement script is kept
under `arrt/tools/` so the numbers can be regenerated. If no local gate
separates the labels, the findings say so and the plan pauses for the owner.

### Chunk 02: The gate as a Library service

A Library service that takes the held original and a fetched candidate and
answers *take* or *refuse, because …* with the signals that decided it, using
Chunk 01's thresholds. Tests on a small fixture set drawn from Chunk 01's
pairs (each label represented, including a visitor photo and a crop), plus the
decision order of `upgrades.md` § The upgrade decision as unit tests, one per
step, each with a fixture that the step alone refuses.

### Chunk 03: Finding scans for a held work

Searching for scans of an accepted work (by its Wikidata item and museum
identifiers, through the existing sources), recording each scan found and the
decision for it. The data-model Q-rows Q38–Q42 are written first, then the
fields. Search for one work and Search all, as a Library service, over HTTP and
`art_catalogue` actions; a re-search of held works refuses double coverage as
`resolve_images` does.

### Chunk 04: Taking a scan

Staged fetch in the acquisition worker's one slot; verify (decodes, real size,
the gate against the held image); swap, keeping the old original as a
superseded original; regenerate the TV rendition and keep the mat colour;
`work.image_changed`; revert from a superseded original; blocklist on a failed
gate or fetch, removable by hand; every step a structured event. Tests that a
failed verify leaves the held image untouched, that a revert restores it, and
that no vision call is made.

### Chunk 05: The surfaces

**Visual change:** yes

Wanted › Upgrades (held works, size, last searched, what was found; Search,
Search all); the Work page's image history (scans found and why each was taken
or refused, the swap, Revert); Activity › Blocklist (Remove); MCP parity;
`information-architecture.md` and `api-contract.md` entries.

### Chunk 06: The owner's review

**Type:** cumulative-final

The owner looks at upgrades on a catalogue copy, including a swap and a
revert; what they ask for is fixed here, then the one cumulative review.

## Verification strategy

Chunk 01 is itself the verification of the gate. From Chunk 03 on, every
chunk runs on a copy of the dev library against the live sources (searches
cost nothing), with the swap and revert exercised end to end before the
owner's review.

## Governance checkpoints

After Chunk 01 (the gate's evidence decides whether the plan continues as
designed), and the cumulative review at Chunk 06.
