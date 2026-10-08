---
artifact: build-plan
version: 1
scope: get-and-review-clarity
branch: feature/get-and-review-clarity
partition: serial — chunks 01 and 02 both change how a Get's cost is said, and 03's collapsed lines reuse 02's counts; the screens are small enough that one builder in order is cheaper than merging.
depends_on:
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: api-contract
governed_by:
  - artifact: information-architecture
  - artifact: design-direction
  - artifact: accessibility-spec
last_validated: null
---

# Build Plan — Get and review clarity

## What this plan is

The owner walked the Wall label redesign on 2026-10-08 and found screens whose
*content* confuses. No stylesheet fixes these. The look is Wall label's;
this plan is about what each screen says and asks. It is drafted from that
walk and the owner's rulings, and is to be built after Wall label merges.

**Owner rulings, 2026-10-08** (asked as options, each with a recommendation,
and each chosen as recommended):

- **Ask** offers one main act, Get, which carries its cost in its own label
  (Wall label chunk 06), and a quieter *Talk it through first* with a
  one-line explanation that a conversation is free. *See what this product
  thinks you like* is removed from Ask: it is a link to Settings › Taste,
  where it already lives.
- **A Get's page** splits its works into *Asked for* and *Also offered by
  <museum>*, both with thumbnails. The *Why it is here* column is dropped for
  offered works, because the section heading says it once. This needs the
  source's name on each row: today `CandidateWorkOut` carries no provider, so
  the API gains one.
- **Review** shows cards with a picture to judge first, collapses the cards
  where the Get found no image into one line at the end, and moves cards
  already decided out of the way.

**Recommended without a ruling** (no decision needed, just fixes):

- **The Get summary** becomes three short counts (asked for, found with an
  image, not matched) instead of one paragraph. The paragraph used two
  different counts that were both 7 on the walked Get: `tally.proposed` and
  `tally.unresolved` (`screens/run.js` `runSentence`). They can diverge
  (`library/services/runner.py`).
- **Queue's Retry all** says what it acts on: "Retry" for a group of one,
  "Retry 3" for a group. It has always been per group
  (`POST /api/acquisitions/causes/retry`). A page-wide retry is added only if
  the owner often sees many causes at once.

**Known from the investigation:**

- The long "Offered by the collection, not proposed by the model: one of N
  works…" text is *stored* data. Runs since commit 8e157ae8 store only the
  short sentence. Dropping the column for offered works removes both.
- "Rejected" plus "the Get found none" on one card are two separate facts:
  the curator's verdict and the run's image-search outcome.
- Review's order today (`library/services/review.py` `list_works`) is
  resolved works, then unresolved, then pending, and within each a work no
  source confirms after the ones a source does. So "pictures first" is
  largely already true at the group level; the investigation note that said
  the opposite was wrong. What chunk 03 changes is the client: the
  unresolved group and the decided cards fold away.

## Requirements Confidence

**Medium.** The rulings are clear. The chunks are drafted, not sized. Open
questions for build time: whether the collapsed "found none" line offers
anything (Want, or retry the search), and what Review does with a card once
it is decided (hide it, or move it to the end).

## Status

- [ ] Chunk 01: Ask: one act and a quieter alternative
- [ ] Chunk 02: A Get's page: asked-for and offered, with pictures and counts
- [ ] Chunk 03: Review: pictures first, "found none" collapsed
- [ ] Chunk 04: Queue's retry says what it retries, and the walk

### Chunk 01: Ask

Done when: the Taste link is gone from Ask, Get is the one filled act and
carries its cost, *Talk it through first* is quiet and explained in one
line, and `information-architecture.md`'s Ask screen table matches.

**Owner ruling, 2026-10-08, replacing the one above for where the cost
sits:** beside or under Get is fine, provided it plainly belongs to Get and
plainly is not an act. What it should say is the order of magnitude, roughly
"About $0.01", "About $0.10" or "About $1", not an exact bound. So: a short
muted caption directly under Get, tied to it for a screen reader, in place of
the "Cost: $" mark and the long "costs at most" sentence. The same on a
conversation's commit card, which starts the same Get. Other priced acts keep
their tier mark; whether they move to the same form is not in this plan.

### Chunk 02: A Get's page

**Exposed API:** `/api/runs/{id}` gains the offering source per offered work.

Done when: the summary is three counts; works are under *Asked for* and *Also
offered by <museum>*, each row with a thumbnail where one was found; offered
rows carry no reason column; `api-contract.md` has the new field.

### Chunk 03: Review

**Type:** code

Done when: cards with a picture come first; the "found none" cards are one
collapsed line at the end; decided cards move out of the way. The ordering
rule is recorded in `information-architecture.md` as the owner's ruling,
with the old reason it replaces.

### Chunk 04: Queue and the walk

**Type:** cumulative-final

Done when: a group's retry names its count; the walk is re-run.

## Verification

Each chunk is walked on the real library copy. The owner judges the result.
