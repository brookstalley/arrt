# Wikidata Findings

Recorded 2026-10-01 for `build-plan-ia-foundations.md` Chunk 03 (ruling 7: works
and artists carry a Wikidata QID where one exists). Everything below was measured
against the live services from the development machine on that date, with the
scripts described in § Reproducing, not recalled. Wikidata is edited continuously,
so counts drift; the shapes and the rules built on them are what this records.

## What was used

- **The query service**, `https://query.wikidata.org/sparql`, `GET` with
  `format=json`. Every probe below is one SPARQL query. Name search goes through
  the service's `wikibase:mwapi` `EntitySearch` call, which is the same ranking
  `wbsearchentities` gives, so no second endpoint was needed.
- **No key, no cost.** Nothing here spends (`nonfunctional-requirements.md`'s
  spend ceilings do not apply).

## The User-Agent policy

Read from the policy itself, which has moved to
`foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy`.
Requests need a **descriptive User-Agent with contact information** (a URL or an
email), and a missing, empty or generic one (`curl`, `python-requests/x`) may be
refused with HTTP 403 or blocked without notice. Including `bot` in the string is
asked for automated agents. The probes sent
`arrt-probe/0.1 (+https://github.com/brookstalley/arrt) bot` and were never
refused. **For the client:** it is told what the museum clients are told
(`observability-strategy.md` § What the museum is told about us), and registry
features say they are off when no User-Agent is configured.

## The match rate on the owner's catalogue (40 works, 31 artists)

**Works: 22 of 40 match unambiguously, and only by the museum's own identifier.**

| Route | Unambiguous | Ambiguous | Not found |
|---|---|---|---|
| Art Institute of Chicago artwork ID (`P4610`), 32 works | 21 | 0 | 11 |
| Google Arts & Culture asset ID (`P4701`), 8 works | 1 | 0 | 7 |
| Title among the artist's works (label or alias, ignoring case) | 16 | 3 | 19 (+ artists not resolved) |

- **Every one of the 16 title matches agreed with the identifier match**, and the
  title route found nothing the identifiers missed. It adds no coverage here and
  carries the risk: generic titles are ambiguous (Harry Callahan's *Chicago*
  matched 17 items, Jasper Johns's *Target* 6, Renoir's *Seascape* 2), and a
  generic title that happens to match once (Franz Kline's *Painting*) is a match
  nothing can verify without the identifier.
- **So the matcher matches works by identifier only.** The identifier comes from
  the work's source URL (`artic.edu/artworks/<id>`,
  `artsandculture.google.com/asset/<slug>/<id>`), which is exact by construction:
  a museum's id names one object. A work with no identifier on Wikidata gets no
  QID, which the plan's assumption already prefers to a wrong one.

**Artists: 24 of 31 match unambiguously, with life dates.**

- **Name search alone is not safe.** It found exactly one human for *Moche*, which
  in this library is a culture, not a person: Frederik de Moucheron, a Dutch
  painter born in 1633, reached by the search's fuzzy matching. A confident,
  wrong answer. It found
  two for Joan Miró, Katsushika Hokusai and Pierre Andrieu.
- **Name search plus agreeing life dates** (birth and death year each within one
  year, where both sides have one, and at least one compared) gives exactly one
  candidate for 24 artists, including all three of the ambiguous names. The seven
  left are the seven with no dates in the library: six from Google Arts &
  Culture, which the library's own records leave undated, and *Moche*, which
  correctly matches nothing.
- **A matched work's creator (`P170`) agrees** wherever both routes answered (17
  artists), and is the stronger route: it inherits the identifier's certainty.
- **Wikidata's occupation tree has moved.** *Visual artist* (`Q3391743`) is no
  longer a subclass of *artist* (`Q483501`), so a filter on `P106/P279* Q483501`
  excludes every painter. The filter that worked: human (`P31 Q5`) and either an
  occupation under *visual artist* or the creator of some item.

## The built matcher, run on a copy of the owner's catalogue

`uv run python -m arrt.identify`, run twice on 2026-10-01 against a copy
(never the catalogue itself): **22 of 40 works and 24 of 31 artists matched, 0
ambiguous**, the seven undated artists listed by name; the second run matched
nothing new and changed nothing. Joan Miró, Katsushika Hokusai and Pierre Andrieu
got the probe's items (`Q152384`, `Q5586`, `Q15962367`) and *Moche* none, so the
built rules reproduce the probe.

## What the Artist page will get (Chunk 04)

Measured for three artists, works where they are the creator (`P170`), with the
sitelink count, image (`P18`) and collection (`P195`):

| Artist | Works | With an image | Query time | Top by sitelinks |
|---|---|---|---|---|
| Mark Rothko | 1,276 | 1 | 1.3 s | *Rothko Chapel* (13), *Orange, Red, Yellow* (6) |
| Salvador Dalí | 1,178 | 13 | 3.6 s | *The Persistence of Memory* (48), *The Great Masturbator* (18) |
| Pierre-Auguste Renoir | 2,159 | 1,987 | 6.2 s | *Bal du moulin de la Galette* (44), *Luncheon of the Boating Party* (30) |

- **An image on Wikidata is close to a public-domain flag.** `P18` names a
  Commons file, and Commons holds the in-copyright artists' work almost never.
  *Image found* will appear for Renoir and almost never for Rothko or Dalí, which
  bears on `user-scenarios.md` § Tested: Rothko: Wikidata does not answer "what
  does it look like?" for a living-copyright artist.
- **Counts are dominated by whole collections catalogued item by item.** 926 of
  Rothko's 1,276 are drawings at the National Gallery of Art. Sorting by sitelinks
  is what puts the paintings a curator has heard of first, and the list needs a
  cap: the whole of it is thousands of rows and seconds of query.
- **Holdings come for free** from `P195` on the same rows.

## Reproducing

The probes were scratch scripts, not product code: a SPARQL helper with the
User-Agent above and three queries, the identifier lookup (`VALUES ?id { … }
?work wdt:P4610 ?id`), the artist search (`EntitySearch`, then the filter above,
then `P569`/`P570` years), and the creator's works (`?work wdt:P170 wd:<artist>;
wikibase:sitelinks ?links`). Chunk 03's `live_museum`-style marked test keeps the
parts the client relies on checked, and is what to run before trusting a figure
here again.
