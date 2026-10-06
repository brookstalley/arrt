---
artifact: build-plan
version: 1
scope: search-held-not-held
branch: feature/search-held-not-held
partition: serial — one builder; the client's search modules, the results screen, their browser tests and the IA rows that describe them. Runs beside the look-before-Get plan, which owns the Work screen and shares no file but the IA document and the change-log
depends_on:
  - artifact: information-architecture
governed_by:
  - artifact: information-architecture
    dispositions:
      - "§ The *arr layout, the search paragraph (Enter stays on Artworks, ruled 2026-09-30 and kept 2026-10-01) → amended by the owner's ruling of 2026-10-06: Enter opens the Search results page, grouped Held / Not held"
      - "§ Screens, the Search results rows (purpose, content, actions, empty states) → amended: two groups replace the All / In your library / Not held switch; an empty Held is one line"
      - "Ruling 2, one world → conforms: the library's and Wikidata's results stay on one page; only their grouping changes"
  - artifact: accessibility-spec
    dispositions:
      - "Glyph and word carry the state → conforms: each row keeps its mark; the group a row is in is in its accessible name, not only its position"
      - "The dropdown is an ARIA combobox whose options are named by group → conforms: a listbox cannot nest groups, so each group's label names its half (Held: works, Not held: works)"
last_validated: null
lifecycle: active
---

# Build Plan — Search groups what you hold and what you do not

## What this plan is

The owner, 2026-10-06, after trying to reach a work they did not hold: "It's
weird for the search box's wikidata and all that to filter to only held items,
so the user has to choose 'all items'. It would be better to group 'held' and
'not held' and have wikidata/etc under each. For 'held' if there are none, a
single 'none' or similar is sufficient, don't need to say no wikidata ones held,
no artists, no works, etc."

They pressed Enter, which opens Artworks filtered to held works, and found
nothing and no way on. Asked, the owner ruled: **Enter opens one results page,
grouped Held / Not held**. That reverses the 2026-09-30 ruling, kept 2026-10-01,
that Enter stays on Artworks. The owner confirmed they had pressed Enter only, so
no separate navigation bug is in scope.

## Requirements Confidence

**High.** The owner chose the shape from a mock-up; the details below are the agent's unless marked.

- [DECISION: **Enter with nothing highlighted opens `#search?q=…`**, the Search results page. A highlighted row still opens that row | the owner's ruling, 2026-10-06]
- [DECISION: **the Search results page has two groups, Held then Not held.** Held holds the library's artists, works and topics that match. Not held holds Wikidata's artists, works and topics that the library does not already show. The *All*, *In your library*, *Not held* switch is removed; a `view=` in an old address is ignored | the owner's mock-up, accepted 2026-10-06]
- [DECISION: **a group with nothing in it is one line**: "Nothing you hold matches." and, once Wikidata has answered, "Wikidata has nothing more." No per-kind "No artists." / "No works." in an empty group. A group with some kinds empty lists only the kinds that have rows | the owner's words]
- [DECISION: **Wikidata's topics join the results page**, under Not held, from `GET /api/registry/topics` as the dropdown already asks. The library's matching topics join Held, from `GET /api/topics` filtered as the dropdown filters | the accepted mock-up lists Topics under Not held; the dropdown already shows both, so the page stops being the narrower of the two | agent's reading of the mock-up]
- [DECISION: **the dropdown uses the same two halves**: the library's groups first under Held, Wikidata's under Not held, then Ask and *All results*. Because a listbox cannot nest groups, each group's accessible name carries its half ("Held: artists", "Not held: works"), and a visual heading row for each half is presentation only. An empty Held half is one presentation line, "Nothing you hold matches." | accessibility spec; the owner's words]
- [DECISION: **kept as they are**: the top result when the words name one artist; *Get N works* on Not held works; *Ask about* when Wikidata finds nothing; the library half drawn first and never waiting on Wikidata; the polite live region; *Asking Wikidata…* | none of these was the complaint]
- [DECISION: **the path to Artworks filtered by the words stays**, as the Held works section's "All N in Artworks" link when more match than are listed, and from Artworks' own filter | Enter no longer reaches it, and a curator with many matching works needs the grid's tools]
- [ASSUMPTION: no server change: every list the page needs already has a route]

**Not in this plan:** a picture of a work before it is got (`build-plan-look-before-get.md`); any change to the Work screen.

## Status

- [ ] Chunk 01: Held and Not held, on the results page and in the dropdown, and Enter opens the page

### Chunk 01: Held and Not held, on the results page and in the dropdown, and Enter opens the page

**Exposed API:** none. Client and records only.

Done when:

- `arrt/src/arrt/http/static/core/search.js`: Enter with nothing highlighted goes
  to `search` with `q`; the dropdown's groups are named by half; an empty Held is
  one line. The module comments that cite the 2026-09-30 and 2026-10-01 Enter
  rulings say what now holds and why.
- `arrt/src/arrt/http/static/screens/search.js`: the two groups, topics in each,
  one line for an empty group, the switch gone, and the Artworks link kept.
- **Browser tests** (`arrt/tests/browser/`, `-m browser`). The tests that assert
  Enter opens Artworks, or that exercise the switch, are rewritten to the new
  ruling, and the change-log entry names each rewritten test and the ruling that
  moved it. Tests are contracts, so this is a recorded requirement change, not a
  weakening. New cases:
  - Enter opens the results page;
  - a query nothing held matches shows the single Held line and Wikidata's works under Not held (the case the owner hit);
  - a query matching only held things shows no Not held rows that the library already shows;
  - the dropdown's groups carry their half in their accessible names;
  - Wikidata down leaves the Held group standing and says so;
  - an old `view=library` address renders both groups.
- `information-architecture.md`: the search paragraph in § The *arr layout, and
  the Search results rows in § Screens and the content and empty-state tables,
  with the 2026-10-06 ruling dated. `tests/preferences/test_screen_tables.py`
  stays green.
- `api-contract.md` is unchanged (no route changes); confirm by grep that nothing
  there describes Enter or the switch.

- **Critic mode:** chunk (the one boundary review)
