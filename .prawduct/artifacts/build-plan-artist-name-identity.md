---
artifact: build-plan
version: 1
scope: artist-name-identity
branch: fix/artist-name-identity
partition: serial — one builder. The identity check (`phase_two.py`), one registry question, and their tests. It runs beside the NGA source plan in its own worktree. That plan owns `sources/nga.py` and the plugin lists, which this one does not touch. The two share only the change-log.
depends_on:
  - artifact: artist-name-identity-findings
governed_by:
  - artifact: data-model
    dispositions:
      - "§ How both scores are derived (an artist disagreement is disqualifying, not a deduction) → amended: on a page the work's item records, two names Wikidata records for one of the item's creators are not a disagreement"
  - artifact: security-model
    dispositions:
      - "§ Direction (every registry string is a named kind) → conforms: the names are `RegistryText` and are compared on the server, never sent to the browser"
  - artifact: source-plugins
    dispositions:
      - "§ What a finder or reader must report → amended: the artist comparison on an item's page accepts a name Wikidata records for the creator"
  - artifact: observability-strategy
    dispositions:
      - "phase_two events → amended: `phase_two.renamed` and the refusal's `names` field"
last_validated: null
lifecycle: active
---

# Build Plan — A holder's name for the artist that Wikidata records

## What this plan is

Backlog arrt#245, made the top public priority by the owner on 2026-10-06.
Phase 2 compares the holder's artist with the Library's under `artist_key`, so
`Laurence Stephen Lowry` is refused for `L. S. Lowry`, and `Rembrandt van Rijn`
for `Rembrandt`. That refuses 18,252 of 67,361 NGA items with an image, and 301
of 2,198 Pompidou items (`artist-name-identity-findings.md`).

## Requirements Confidence

**High.** The rule and its bounds come from measurement on all three of the
owner's populations, against ground truth independent of the rule: NGA's own
constituent QIDs, and navigart's life dates.

- **Problem:** a holder names the right artist in a form the Library's label
  does not key to, so the right image is refused.
- **Success:** on a page the work's Wikidata item records, the holder's
  `Laurence Stephen Lowry` is accepted for the Library's `L. S. Lowry`. On a
  page the item does not record, it is still refused. So is a holder naming an
  artist that is no name of the item's creator, even on the item's page.
- **Out of scope:** `X after Y` and multiple makers; honorifics Wikidata does not
  record; token order (#79); life dates; the persisted key (`artist_key` and
  `work_dedup_key` are unchanged).
- [DECISION: **the Wikidata-name rule runs only on a page the work's item records** | aliases are noisy (`Canaletto` is an alias of Bellotto), and with only a title behind it an alias would accept a Brueghel the Younger copy for his father's work; on the item's page a wrong image needs two independent errors | findings § Options, option 2]
- [DECISION: **both names must be names of the same recorded creator**: the Library's artist and the holder's, each a label or an alias, in any language, keyed by `artist_key` | "the artists agree" stays a statement about one person; any language, because the Pompidou writes French forms and the measured wrong-person rate did not rise (findings table) | agent's]
- [DECISION: **an accepted renaming keeps `CONFIDENT`**, and the card says the holder's name is one Wikidata records for the requested artist | the identity is as confirmed as an exact match; the card names how | agent's]
- [DECISION: **the names are asked of the registry once per work**, only when a result's artist disagrees on a page the item records; if Wikidata cannot be asked, the refusal stands and is logged | as the page link: refusing is the direction a later search can undo]
- [DECISION: option 1, letting the item's page vouch for the artist as well, is **not** built; it is reported to the owner as an option | it removes the cross-check that catches a wrong creator on the item (Kandinsky's work credited to Joe Keery) and would weaken a pinned contract]

## Status

- [x] Chunk 01: the rule, the registry question, tests, artifacts

### Chunk 01

**Exposed API:** none. `Registry` gains one question, `creator_names(qid)`. That is an internal seam.

Done when:

- `arrt/src/arrt/library/registry/__init__.py`, `arrt/src/arrt/library/registry/wikidata.py`: `creator_names(qid) -> Mapping[ItemId, frozenset[RegistryText]]`, each creator's labels and aliases in every language. A bad QID is refused before it reaches the query. `arrt/tests/unit/test_wikidata_client.py` (shape, injection, failure) and `test_registry_strings.py` (named kinds, stranger URLs) cover it.
- `arrt/src/arrt/library/discovery/phase_two.py`: on an artist disagreement, `WikidataLink` checks the page against the item. It then checks the names once per work. Accepted is `CONFIDENT` with a sentence saying so. Refused keeps `IDENTITY_REFUSED` and gains the `names` reason on `phase_two.not_the_work`. `phase_two.renamed` is logged on acceptance.
- `arrt/tests/unit/test_phase_two_engine.py` covers:
  - Lowry on the item's page is accepted.
  - The same on an unrecorded page is refused.
  - A name of a *different* creator on the item's page is refused (Jean Arp).
  - The Library's artist must be a name of the same creator.
  - A failing registry refuses.
  - A matching artist asks no names.
  - Names are asked once per work.
  - The rationale's absence in an exact match.
- `arrt/tests/fakes.py`: `FakeRegistry.creator_names`.
- `arrt/tests/live/test_wikidata_creator_names_are_still_real.py`: Lowry, Turner, Rembrandt and Kisling's names still carry the holders' forms.
- Artifacts: data-model, source-plugins, observability-strategy and `phase_two.py`'s docstring.
- Change-log entry.
- All three suites, ruff and black. `/prawduct:critic`.
