---
artifact: build-plan
version: 1
scope: title-identity
branch: fix/title-identity
partition: one builder, sequential; one chunk of code, then the owner's go to deploy and re-run
depends_on:
  - artifact: data-model
  - artifact: source-plugins
governed_by:
  - artifact: data-model
    dispositions:
      - "§ Direction: identity is never a source URL → held. The work's identity stays its key and its QID; a page the work's Wikidata item records is evidence in one resolution attempt, the mirror of the QID matcher reading a holder's identifier from a source URL"
last_validated: null
---

# Build Plan — A title worded differently by its holder

## What this plan is

Run 3 (`procurement-corpus.md`, on `records/moma-reader`) searched the nine open
MoMA works through the MoMA plugin. Seven were found. Two were refused by phase
two's title gate (`title_key` in `phase_two.py`), which compares normalised
titles before anything else:

- row 43, "Tree" against MoMA's "The Tree";
- row 13, "Composition of Circles and Overlapping Angles" against MoMA's
  "Composition".

| Chunk | What |
|---|---|
| 01 | A leading English article is cataloguing variation; a page the work's Wikidata item records passes the title gate; stored keys follow the derivation |
| 02 | Deploy and re-run the two rows |

**Not in this plan:** a holder's shorter title passing on its own (the owner
ruled it out); articles in other languages; a cache for `pages_about`.

## The owner's ruling (2026-10-04)

Asked with the built behaviour and the agent's recommendation, the owner said
"Yes your recommendation":

- **A leading article passes.** "Tree" and "The Tree" are one title.
- **A holder's shorter title does not pass on its own.** "Composition" would
  match every *Composition* by that painter, which is the merge the gate exists
  to stop.
- **Instead, Arrt trusts the Wikidata link.** When the work's Wikidata item
  records the page an image was read from, the record is about the work, whatever
  its title says. The artist check still runs.

## Requirements Confidence

High for the rule, which the owner stated. The mechanism is the agent's:

- [DECISION: the article rule lives in `title_key`, so it also changes `work_dedup_key`. Phase two's gate and suppression are derived from one normalisation (`data-model.md` § Q3 notes), and splitting them is the drift that rule exists to prevent | agent's, owner can veto]
- [DECISION: English articles only (`the`, `a`, `an`), and only when a word follows. A title that is only an article keeps it | agent's, owner can veto]
- [DECISION: Arrt asks the registry itself (`Registry.pages_about`), not the pages the pool's finders returned. Any plugin may answer a `FoundPage`, including one found by a search, and a search's page is no evidence of identity | agent's]
- [DECISION: an image's `url` must equal a page the item records, exactly. A plugin that rewrites the address differently fails closed, back to the title gate. MoMA's plugin records `https://www.moma.org/collection/works/N`, which is the P2014 formatter's form | agent's]
- [DECISION: the registry is asked at most once per work searched, and only when a result's title differs and the work has a QID. A registry that cannot be asked means no link, and the title gate refuses as before | agent's]
- [DECISION: the startup repair re-derives every stored key, not only those whose title the cleaning changed. Every writer derives the key from the stored title and artist (checked: `propose_work` via the runner, `offer_work`, `choose_works`), so a key that differs from that derivation is stale | agent's]

## Status

- [x] Chunk 01: The article rule, the Wikidata link, and stored keys
- [ ] Chunk 02: Deploy and re-run

### Chunk 01: The article rule, the Wikidata link, and stored keys

- `dedup.py`: `title_key` drops one leading `the`, `a` or `an` after
  normalising, when a word follows.
- `phase_two.py`: `PhaseTwoEngine` takes an optional `registry`. A result whose
  title differs passes the gate when the query has a QID and the result's `url` is
  among `pages_about(qid)`; it is logged as identified by the link. The artist
  check is unchanged.
- `container.py`: the engine gets the deployment's registry.
- `discovery.py`: `_reclean_proposed_titles` also rewrites a row whose stored
  key differs from the key its (cleaned) title and artist derive, and reports
  re-keyed rows apart from re-cleaned ones.
- Tests: article variants share a key, a bare "The" keeps its word, and articles
  mid-title are kept; the corpus floor holds and nothing new over-merges; a
  linked page passes with a differing title; an unlinked one is refused; a link
  with a disagreeing artist is refused; no QID means no registry call; a registry
  that cannot be asked refuses; the registry is asked once per work; a stored
  "The X" key is re-keyed at startup and a rejection under it then suppresses
  the new proposal.
- Artifacts: `data-model.md` (the derivation and the link), `source-plugins.md`
  and `docs/source-plugins.md` (what a plugin's `url` buys), `boundary-patterns.md`
  (the repair now pays every derivation change).

### Chunk 02: Deploy and re-run

- The owner's go to deploy. Then a run over rows 13 and 43; the result is recorded
  in `procurement-corpus.md` beside run 3.

## Verification strategy

`cd arrt && uv run pytest` and the root suite. The re-run in Chunk 02 is the
product check.

## Governance checkpoints

One `cumulative` Critic review after Chunk 01, before the PR.
