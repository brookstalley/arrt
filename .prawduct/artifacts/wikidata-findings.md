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
- **Holdings come for free** from `P195` on the same rows. Some collections now
  carry only a language-neutral (`mul`) label, so the label service is asked
  for `en,mul`; without it the National Gallery of Art came back as `Q214867`.
- **The library's own works are rarely among the most renowned.** None of the
  owner's two Rothkos or their Dalí is in its artist's top fifty by sitelinks
  (each has none), so the page asks for the held works by QID as well, or it
  would mark nothing *Held*. Measured by running the page on a copy of the
  catalogue, 2026-10-01.
- **Registry titles can differ from the museum's.** The Art Institute's
  *Untitled (Desert Landscape)* (Dalí, 1934) is labelled "Atmospheric Chair" on
  the item carrying its identifier, and about a fifth of Rothko's top fifty
  have no English or `mul` label at all.

## Searching for works, and similar artists (one-world search)

Measured 2026-10-01 for `build-plan-one-world-search.md`, two runs of each
query, same User-Agent.

**Finding works by title.** Two search calls are reachable through the query
service's `wikibase:mwapi`, and they answer different questions:

| Query | `EntitySearch` (label prefix, as `people_named` uses) | `Search` with `haswbstatement:P170` (full text) |
|---|---|---|
| `persistence of memory` | J.C. Heywood's *Persistence of Memory* only; Dalí's is missed | Dalí's (48 sitelinks), then his *Disintegration of…*, then Heywood's |
| `hunters in the snow` | Brueghel the Younger, Heymans, Courbet; the Elder's is missed | Brueghel the Elder's (39) first |
| `starry night` | van Gogh (76), then *Over the Rhone* (38) | the same |
| `starr` (a typed prefix) | van Gogh's two, then Munch | comics and TV ("Power Girl"); `starr*` gives van Gogh's two, then *Reign* and *Kojak* |
| time per query | 0.3–0.9 s | 0.4–1.2 s |

- **`EntitySearch` misses any title that starts with "The"** unless the curator
  types the article, because it matches labels and aliases from their start. The
  owner's own first test, *The Persistence of Memory*, is such a title.
- **Full text finds them, and lets in anything with a creator.** `P170` sits on
  TV series, comics and software (*Kojak*, *Power Girl*, Wikidata itself for
  `mona`). Sorting by sitelinks puts those near the top, because they are
  famous. So full text needs a filter for works of visual art, and the filter's
  cost is unmeasured.
- **Neither search folds a missing accent the way the library does.** That was not
  measured here; `dali` finding Salvador Dalí through `wbsearchentities` is.

**Similar artists, from shared movements (`P135`).** People sharing a movement,
ranked by sitelinks, kept only if they made at least one work with an image:

| Artist | Movements | Top of the list | Time |
|---|---|---|---|
| Renoir (Q39931) | Impressionism | Matisse, Octave Mirbeau, Monet, Gauguin, Degas, Manet, Cassatt, Pissarro | 0.8–1.3 s |
| Rothko (Q160149) | abstract expressionism | Bourgeois, de Kooning, Appel, Gorky, Newman | 0.4–1.5 s |
| Dalí (Q5577) | surrealism | Picasso, Kahlo, Miró, David Lynch, Klee, Buñuel, Duchamp, Ernst | 0.4 s |
| van Gogh (Q5582) | Expressionism, Post-impressionism | four minor painters sharing both, then Picasso, Matisse, Cézanne, Gauguin, Munch | 0.9 s |

- **Ranking by the number of shared movements promotes obscure people.** For van
  Gogh, four painters with 5 to 25 sitelinks come first because they share both
  movements. Fame first, then shared movements, reads better on every artist
  measured.
- **Movements admit people who are not painters.** Octave Mirbeau is a critic
  and novelist, Buñuel and Lynch are filmmakers, and Captain Beefheart appears
  for Rothko without the image filter. The image filter removes some of them but
  not all. An occupation filter (visual artist, as `people_named` uses) is the
  next thing to try.
- **Influence links (`P737`) are sparse and one-sided.** Renoir has 7, all
  *influenced*, all minor; Dalí has 12 (Picasso, Bosch and Nietzsche among
  *influenced by*). They are too few to rank, and are useful as a second section
  at most.

**One work by QID** (for the Work page of a work not held), measured on three
works: the owner's held Rothko *Untitled (Purple, White, and Red)* (Q20270685,
the live test's ARTIC 100472), *The Hunters in the Snow* (Q500985, from
`wbsearchentities`), and Rothko's most-linked work with no English or `mul`
label (Q16682090, from a query). One query each, 0.24–0.49 s:

| Work | Title | Year | Image | Medium (`P186`) | Collection (`P195`) | Inventory (`P217`) |
|---|---|---|---|---|---|---|
| Q20270685 | *Untitled (Purple, White, and Red)* | 1953 | none | oil paint, canvas | Art Institute of Chicago | 1983.509 |
| Q500985 | *The Hunters in the Snow* | 1565 | a Commons file | panel, oil paint | Kunsthistorisches Museum | GG_1838 |
| Q16682090 | the QID itself | 1964 | none | oil paint, canvas | Musée National d'Art Moderne (twice) | AM 2007-126 |

- **Names need `mul` as well as `en`.** Mark Rothko (Q160149) has a `mul` and an
  `en-gb` label and no `en` one, so a creator label filtered to `en` came back
  empty for both Rothkos. Every label the work query asks for goes through
  `en,mul`, as `_LABELS` already says.
- **The shipped `people_named` has this defect.** It asks the label service for
  `"en"` alone, and live it returns `Q160149` as Mark Rothko's label (Dalí and
  Renoir come back named). The matcher reads only the QID and the years, so
  nothing shown today is wrong. The typeahead would show it, so it is fixed
  before registry artists are listed there (`build-plan-one-world-search.md`
  Chunk 02).
- **An inventory number belongs to a collection.** `P217` carries the collection
  as a `P195` qualifier (GG_1838 at the Kunsthistorisches Museum; 1983.509 at the
  Art Institute). A work held in two places has two numbers, so the pair is read
  together and not as two lists.
- **Collections repeat**, as Q16682090's does, when a work has two `P195`
  statements naming one collection. The page de-duplicates by QID.
- **A work with no readable title** shows its QID as the label, as on the Artist
  page, and is shown there as *No English title (Q…)*.

A wrong figure that was caught: the first run used Q5432 for Dalí, typed from
memory. It is another person, with Romanticism and Rococo as movements. Every
QID above was read from a search result or from this document.

## Reproducing

The probes were scratch scripts, not product code: a SPARQL helper with the
User-Agent above and three queries, the identifier lookup (`VALUES ?id { … }
?work wdt:P4610 ?id`), the artist search (`EntitySearch`, then the filter above,
then `P569`/`P570` years), and the creator's works (`?work wdt:P170 wd:<artist>;
wikibase:sitelinks ?links`). Chunk 03's `live_museum`-style marked test keeps the
parts the client relies on checked, and is what to run before trusting a figure
here again.
