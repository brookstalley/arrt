---
artifact: build-plan
version: 1
scope: artist-search-review-fixes
branch: feature/artist-search-review-fixes
partition: serial — one builder; the Artist screens, the search marks, the review card, the artist service's registry half, and their tests. Runs beside the NGA source plan in its own worktree, which owns no file here but the change-log
depends_on:
  - artifact: information-architecture
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ Screens, the Search results row (an artist marked ● In your library or ○ Not held) → amended by the owner, 2026-10-06: inside a group a mark says only what the group heading does not"
      - "§ A work's mark → conforms: the Topic page's precedent (○ reading No image known) is reused inside the Not held group"
      - "§ Screens, the Artists row → amended: an unlinked artist's page names Wikidata's candidates; an artist Wikidata lists no works for offers Ask"
  - artifact: accessibility-spec
    dispositions:
      - "Glyph and word carry the state → conforms: every mark kept keeps glyph and word; the group a row is in stays in its heading's accessible name"
  - artifact: data-model
    dispositions:
      - "§ Registry identity (ruling 7: the matcher sets an identity only where certain; the curator corrects it) → conforms: candidates are shown, never stored; only the curator's click stores one, through the existing route"
last_validated: null
lifecycle: completed
archived: 2026-10-07
released_in: v0.4.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — Artist pages that lead somewhere, quieter search marks, a settled review card

## What this plan is

Four things the owner hit on 2026-10-06:

1. "Search Franz Kline … click artist name, get to a library page with two works.
   But from there it's impossible to see non-held works from Kline … Also it's
   weird the Wikidata ID appears on not-held, but held says no Wikidata ID."
2. "Searching for Lucy Bull correctly turns up no held works, but clicking the
   artist lands on a dead-end with no works, no holdings, no thumbnails."
3. "The 'not held' box on search results doesn't really make sense when the
   whole section is 'not held'."
4. "On the get/run page, clicking accept still leaves the why/accept/reject
   boxes … it should change to accepted / remove the UI prompting."

**Causes, measured against the owner's server:**

1. The library's Franz Kline has no QID. The matcher that sets one is a hand-run
   command (`python -m arrt.identify`) that needs the server stopped, so every
   artist acquired since it last ran is unlinked. Its own rule would match Kline
   (one visual artist of that name, 1910–1962 agreeing). The Artist page already
   lists *Their work* for a linked artist; an unlinked one says only "not matched".
   Search then lists the same person twice, once held and once not.
2. Wikidata lists no works, holdings or similar artists for Lucy Bull
   (Q123365005). The page says so, and offers nothing to do next.
3. Inside the *Not held* group, each row repeats "○ Not held".
4. A terminal verdict is final (`DiscoveryService.set_verdict`), but the card
   draws *Why*, *Accept* and *Reject* whatever the verdict, so the controls
   offered after Accept are ones the server refuses.

## Requirements Confidence

**High** for 2–4; **Medium** for 1's shape (the owner asked for the list; linking
is the mechanism, and the owner has not seen it).

- [DECISION: **an unlinked artist's page names Wikidata's candidates**: the visual artists a name search finds (`Registry.people_named`, the matcher's own search), those whose years agree with the library's first, at most five, leaving out any item another library artist carries. Each has *This is them*, which stores it through `POST /api/artists/{id}/wikidata`, as the identity control does; the page then repaints with *Their work*. Nothing is stored without that click | ruling 7: a wrong QID marks the wrong works held, so the page proposes and the curator decides | agent's]
- [DECISION: a curator's "there is none" is honoured: no candidates are asked for, and the note says they said so | ruling 7]
- [DECISION: **an artist reached by QID whom the library holds unlinked under the same name** (accents and case folded, no QID, not "there is none") is named on that page with *Link them to this item*, which stores the QID and opens their library page | the owner's Kline path went through this page | agent's]
- [DECISION: **an artist Wikidata lists no works for offers *Ask for their work***, which opens Ask filled with "Paintings by <name>" and starts nothing, as search's *Ask about* does; on both Artist pages | IA § A control never offers a dead end; Ask is how works Wikidata does not list are found (Lucy Bull's were found by Ask, run bd44c4b3) | agent's]
- [DECISION: **inside the search groups a mark says only what the group heading does not**: artist rows carry no mark (the top result, outside the groups, keeps it); a not-held work reads ◐ *Image found*, ◑ *Wanted*, or ○ *No image known* (the Topic page's words); a held work keeps ● *Held* and its picture, since *Held ×2* says something the heading does not. Results page and dropdown alike | the owner's words; the dropdown has the same two halves]
- [DECISION: **a decided card shows its decision, not the controls**: accepted or rejected, the *Why* field and the verdict buttons are replaced by one line: "Accepted. It is in your library." with *Open it in Artworks*, or "Rejected. It will not be proposed again." (the rejection reason is not served to the card, so it is not repeated). *Wanted* is not terminal and keeps *Forget* | `set_verdict` refuses a second verdict]
- [DECISION: **the candidates answer is kept a week**, as the rest of the registry half is (`REGISTRY_KEPT_FOR`), keyed by the name; a failure is not kept | `artists.py` module rule]
- [ASSUMPTION: running the matcher automatically at acceptance is the deeper fix for (1) and is out of this plan; filed to the backlog. The owner is asked to run `python -m arrt.identify` once for the artists already unlinked, after checking the candidates on Franz Kline; recorded in `operator-verification.md`]

**Not in this plan:** automatic identity matching; finders that list an artist's works from a gallery (#210).

## Status

- [x] Chunk 01: all four

### Chunk 01: all four

**Exposed API:** `GET /api/artists/{id}/registry` gains `candidates` (state `no_identity`); `GET /api/registry/artists/{qid}` gains `unlinked` (state `known`); every candidate work over HTTP gains `decided` (added at review). Additive.

Done when:

- `arrt/src/arrt/library/services/artists.py`: `RegistryView.candidates` and `.unlinked`, as above; unit/integration tests for agreeing-first order, the cap, a taken item left out, "there is none" asking nothing, an outage leaving the note, and the namesake fold.
- `arrt/src/arrt/http/models.py`, `arrt/src/arrt/http/api.py`, `.prawduct/artifacts/api-contract.md`: the two fields.
- `arrt/src/arrt/http/static/screens/artists.js`: candidates with *This is them*; *Link them to this item*; *Ask for their work*.
- `arrt/src/arrt/http/static/screens/search.js`, `arrt/src/arrt/http/static/core/search.js`, `arrt/src/arrt/http/static/core/registry.js`: the group marks.
- `arrt/src/arrt/http/static/core/reviewing.js`: the decided line, hidden on the server's `decided` (added at review: `CandidateWorkOut.decided`, so the client holds no copy of the terminal verdicts).
- Browser tests for each, including the absence assertions (no mark on a grouped artist row; no *Accept* after Accept; no candidates after "there is none").
- `information-architecture.md` rows amended; operator-verification entry; change-log.
