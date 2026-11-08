---
artifact: build-plan
version: 2
scope: observed-taste
branch: feature/observed-taste
base: develop
working-branches: []
last_validated: 2026-11-08
depends_on:
  - artifact: agents-and-memory
  - artifact: data-model
  - artifact: api-contract
partition: serial — Chunk 02 calls the rule Chunk 01 writes
---

## Goals

**Response taken:** Proceed, citing it. `agents-and-memory.md` item 2 and open
question 1 were answered by the owner on 2026-11-08 ("it should be at least 5, but
with at least 90% rejections (100 approvals and 5 rejections is fine)"; "yes, and
even artists that are asked for and approved seem like taste. agreed on others").

**Product:** Review's verdicts become taste the product observed, so Ask and phase 1
(item 1) are told what the curator's decisions show and not only what they said.

**The rule (the owner's):** by artist, over every accepted and rejected candidate
work. At least 5 rejected, and rejections at least 90% of the artist's verdicts:
an observed `declines`, `open_to_more` false. At least 5 accepted, and accepts at
least 90%: an observed `likes`, open to more. Otherwise no observed judgment, and an
existing one is removed. Approvals count whatever the request named. An observed
judgment never overwrites a `stated` one.

**Constraints:** no new dependency; `set_affinity` keeps refusing `observed` from
callers, because only review can assert it.

**Ruled by the owner on 2026-11-08** ("agreed on others", on the advisor's
recommendations): counted by artist only; a `stated` judgment is never overwritten;
an observed dislike offers no more; an observed judgment is removed when its rule
stops holding.

**Inferred (the boundary review shows these):**
- **An artist is its `artist_key`**, the half of the dedup key that already makes
  "Dali" and "Dalí" one artist. The judgment is written under the name the latest
  verdict used. A stated judgment blocks the observed one when its value has the
  same `artist_key`, so a differently spelled stated row still wins.
- **An `inferred` judgment is left alone**, like a stated one. Nothing can write
  an inferred row any more, so replacing it would lose it for good once the
  verdicts stopped holding. *(Revised after the cumulative review: the first build
  replaced it.)*
- **An observed judgment beside a stated or inferred one of the same artist is
  withdrawn**, so the two never contradict each other in a prompt.
- **Forgetting an observed judgment lasts until the verdicts are read again**,
  and the Forget dialog says so. Correcting it is how the curator overrules it.
- **Unattributed works count for nobody.**
- **`wanted` and `pending` are not verdicts on the work's maker** and count for
  neither side.
- **The rule re-derives at startup over every artist**, in `Services.reconcile`, so
  the household's existing verdicts become taste on the first start, and a rule
  change reaches every row (the learnings rule on stored derived values).
- **The rationale says the counts** ("Rejected 6 of 6 works by Klimt in review"),
  so Taste shows why, and so does the prompt.

## Build Chunks

### Chunk 01: The rule, applied at every verdict

- **Deliverables:** a store read of the decided works by artist; the rule in
  `arrt/src/arrt/library/services/taste.py` as one function over counts; `set_verdict` applying it
  to the work's artist inside its transaction; the docstrings that say nothing writes
  `observed`.
- **Tests:** the thresholds at their edges (4/4, 5/5, 9 of 10, 5 beside 100); the
  mirror; a stated row by another spelling blocks; an inferred row is left alone; a
  falling ratio removes the row; wanted and unattributed count for nothing; through
  `set_verdict` (the caller), not only the function.
- **Done when:** tests pass; committed.

### Chunk 02: Existing verdicts, at startup

- **Deliverables:** `Services.reconcile` re-derives every artist; the artifacts
  (`data-model.md`, `api-contract.md`'s `art_taste` refusal text, the IA's Taste
  help if it names how observed rows arrive).
- **Tests:** a catalogue with history gets its observed rows at reconcile, and a
  second reconcile changes nothing (with the inputs varied between runs).
- **Type:** cumulative-final
- **Done when:** tests pass; committed, then `/prawduct:critic cumulative`.
