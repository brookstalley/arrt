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

**The filter, chosen by measurement (Chunk 03's verify-api, 2026-10-01).** Four
candidates, run on `persistence of memory`, `hunters in the snow`, `starry night`,
`starr*`, `mona*` and `water lilies`:

| Filter | Drops *Kojak*, *Power Girl*, Wikidata? | Worst time |
|---|---|---|
| none | no | 5.6 s (`mona*`) |
| item is a subclass of *work of art* (`P31/P279*` Q838948), in SPARQL | no: TV series sit under it | 57 s, and `mona*` timed out |
| item is a subclass of *visual artwork* (Q4502142), in SPARQL | no | 49 s, and `mona*` timed out |
| a creator whose occupation is under *visual artist*, in SPARQL | no (`starr*` kept *Kojak* and *Power Girl*) | 6.2 s |
| **the search index's own `haswbstatement:P31=…`, one per class below** | **yes** | 7.9 s for `mona*`, 44 s for `david` |

The classes, each read from `wbsearchentities` on the day: painting Q3305213,
sculpture Q860861, drawing Q93184, print Q11060274, photograph Q125191, mural
Q219423, watercolor painting Q18761202, work of art Q838948, triptych Q79218,
panel painting Q55439. *fresco* and *tapestry* were dropped: their top search
result was a surname and an album.

**The index answers in 0.3 s; the time was the query service paging.** Asked
directly, the search index answered `david` in 0.32 s. Inside SPARQL, `mwapi`
follows the search's continuation through every page unless told
`wikibase:limit`. With `wikibase:limit 50` and `srlimit 50`, two runs of nine
queries (the six above, `david`, `the kiss`, `thinker`, `dal*`) took 0.37–0.85 s
on the second run and 1.75 s at worst. Results, by sitelinks: `david` gives
Michelangelo's *David*, then Jacques-Louis David's works; `dal*` gives Dalí's
works, because the index matches more than titles; `the kiss` gives Klimt,
Hayez, Eisenstaedt and Rodin; `thinker` includes Rodin's.

**A name filtered by language is a coin toss between `en` and `mul`.** Selecting a
maker's label with `FILTER(LANG(?l) IN ("en","mul"))` and `SAMPLE` returned
"Pieter Bruegel" in one run and "Pieter Brueghel the Elder" in the next, because an
item carrying both labels gives two rows and SAMPLE takes either. The label
service's explicit form (`?maker rdfs:label ?makerLabel` inside `SERVICE
wikibase:label`) prefers `en` and falls back to `mul`, and it binds inside an
aggregating query, where its implicit form did not. Every name the client reads
now comes through it.

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
- **`people_named` had this defect, and it is fixed.** It asked the label
  service for `"en"` alone, and live it returned `Q160149` as Mark Rothko's label.
  It now asks for `en,mul` like every other query, and the live test pins
  Rothko's name (`build-plan-one-world-search.md` Chunk 02).
- **An inventory number belongs to a collection.** `P217` carries the collection
  as a `P195` qualifier (GG_1838 at the Kunsthistorisches Museum; 1983.509 at the
  Art Institute). A work held in two places has two numbers, so the pair is read
  together and not as two lists.
- **Collections repeat**, as Q16682090's does, when a work has two `P195`
  statements naming one collection. The page de-duplicates by QID.
- **A work with no readable title** shows its QID as the label, as on the Artist
  page, and is shown there as *No English title (Q…)*.

**Similar artists with the occupation filter (Chunk 05's verify-api, 2026-10-01).**
People sharing a movement, whose occupation is under *visual artist* (Q3391743, as
`people_named` uses), ranked by sitelinks, with a second query counting each
one's works that have an image (`P170` and `P18`):

| Artist | Time (second run) | Top of the list, with works having an image |
|---|---|---|
| Renoir | 7.4 s, then 0.4 s for images | Matisse 507, Monet 1,286, Gauguin 739, Degas 649, Manet 443, Cassatt 255 |
| Rothko | 2.2 s, then 0.4 s | Pollock 0, Bourgeois 7, de Kooning 3, Appel 8, Gorky 35, Captain Beefheart 0 |
| Dalí | 5.2 s, then 0.5 s | Picasso 14, Kahlo 1, Miró 25, David Lynch 1, Klee 525, Buñuel 2, Breton 0 |
| van Gogh | 4.3 s, then 0.4 s | Picasso 14, Matisse 507, Bhumibol Adulyadej 0, Cézanne 808, Gauguin 739, Munch 1,963 |

- **The filter drops Octave Mirbeau and keeps everyone Wikidata also calls a
  painter**: André Breton, Tristan Tzara and Paul Éluard for Dalí, Captain
  Beefheart for Rothko, and the King of Thailand for van Gogh. Each has a
  painter-like occupation recorded. No filter tried removes them without losing
  real painters.
- **Requiring an image would be wrong.** Pollock has none (in copyright) and is
  Rothko's first. The count is shown instead, as `ia-proposal.md` § Artist asks,
  so a curator sees that nobody can supply a Pollock before committing to him.
- **Ranking by sitelinks first** keeps the obscure out of the top, as the earlier
  table found.
- **2 to 7 seconds** is too slow to wait for, so the section is asked after the
  page is drawn, like *Their work*, and remembered per artist.

A wrong figure that was caught: the first run used Q5432 for Dalí, typed from
memory. It is another person, with Romanticism and Rococo as movements. Every
QID above was read from a search result or from this document.

## Commons, as an image source (Get and Ask, 2026-10-02)

Measured for `build-plan-get-and-ask.md` Chunk 02, over every artist in a copy of
the owner's catalogue that carries a QID (24 of 31). For each, every item whose
creator (`P170`) is that artist, whether it has an image (`P18`), and whether that
image, at the size Commons reports for the original, clears the floor on the
operator's panel (3840 x 2160, 50", 2.5" mat, bottom x1.15, 12" floor: a 3400 x
1687 box).

| Artist | Works on Wikidata | With an image (P18) | Image clears the floor |
| --- | --- | --- | --- |
| Alexander Calder | 162 | 27 | 19 |
| Arthur Dove | 216 | 60 | 41 |
| Charles Demuth | 86 | 49 | 45 |
| Constantin Brancusi | 26 | 9 | 5 |
| Ellsworth Kelly | 385 | 3 | 3 |
| Frank Lloyd Wright | 14 | 2 | 2 |
| Franz Kline | 180 | 0 | 0 |
| Georgia O'Keeffe | 225 | 21 | 8 |
| Harry Callahan | 180 | 0 | 0 |
| Jasper Johns | 2012 | 1 | 0 |
| Joan Miró | 580 | 25 | 23 |
| John Steuart Curry | 47 | 13 | 11 |
| Juan Gris | 241 | 215 | 181 |
| Katsushika Hokusai | 387 | 339 | 297 |
| Marilyn Minter | 6 | 0 | 0 |
| Mark Rothko | 1276 | 1 | 0 |
| Paul Klee | 670 | 525 | 478 |
| Pierre Andrieu | 18 | 13 | 8 |
| Pierre-Auguste Renoir | 2159 | 1987 | 1322 |
| Piet Mondrian | 1466 | 586 | 115 |
| Raoul Dufy | 435 | 93 | 66 |
| René Magritte | 319 | 3 | 2 |
| Salvador Dalí | 1178 | 13 | 12 |
| Vasily Kandinsky | 526 | 454 | 321 |
| **All** | 12794 | 4439 | 2959 |

**What it says:** Commons follows copyright. An artist whose work is in the
public domain is well covered (Renoir, Klee, Gris, Hokusai, Kandinsky). One still
in copyright has almost nothing (Rothko 1, Dalí 13, Magritte 3, Kline 0), so for
those the Art Institute stays the only source. Two thirds of the images that exist
clear the floor.

**Licences** of the 4,439 images: public domain 3,802, CC0 247, and the rest CC BY
or CC BY-SA in their versions. Commons' own `Copyrighted` flag is what the source
reads: `False` is recorded public domain, `True` in copyright.
**Types:** JPEG 4,289, PNG 73, TIFF 58, GIF 12, WebP 5, SVG 1.

**The originals can be too large to fetch.** The five largest: Renoir's *Dance at
Le Moulin de la Galette* at 40,869 x 30,379 and 752,213,958 bytes, a 357 MB TIFF,
and three of 164 to 244 MB. Starry Night's (`Q45585`) is 44,567 x 35,291 and
696,195,208 bytes. The acquisition path refuses a body over 512 MiB.

**Renderings come in fixed widths, up to 3840.** `imageinfo` with `iiurlwidth`
returns a `thumburl` at the next fixed width (843 asked gives a 960 px file) while
`thumbwidth` echoes the width asked, so only a fixed width yields a true size. A
URL for 5000 or 7680 px is refused with HTTP 400, so 3840 is the widest. For a
file narrower than the width asked, `thumburl` is the original and `thumbwidth`
is still the width asked. Renderings are served from `thumb.wikimedia.org`,
originals from `upload.wikimedia.org`; both answered 200 with no redirect.
`Special:FilePath` redirects twice before reaching the file, which is why the
source asks the API for the file's own URL instead. The API's URLs carry
`utm_` tracking parameters, which are not part of the file's address.

The recorded answers the source's tests run against are in
`arrt/tests/fixtures/commons/`.

## Topics (Topics and destinations, 2026-10-02)

Measured for `build-plan-topics-and-destinations.md` Chunk 03 with the client's
own calls (`topic`, `topic_works`, `topic_artists`, `topics_named`,
`topics_of`), User-Agent `arrt test suite (+https://github.com/brookstalley/arrt) bot`,
through a wrapper that timed and kept every query and answer. Each call was made
twice in a row. **The second run was no warmer than the first**: slower as
often as faster (the Dutch Golden Age's works 15.1 s, then 25.9 s), so the
service did not answer the client's queries from a cache, and the plan's 0.2 s
"warm" figure is not reproduced. Why is not measured; the client POSTs every
query, and the plan's probe may not have. The only warm answer the product has
is the topic service's own memory.

**Twenty topics, QIDs read from `wbsearchentities` on the day**, five a person
would call each kind: a century, a decade and named periods; movements old and
modern; subjects concrete, abstract and a genre; kinds of work. Times in seconds.

| Topic | A person says | The rule says | Years | topic() s | works s (1st / 2nd) | artists s (1st / 2nd) |
|---|---|---|---|---|---|---|
| 16th century (Q7017) | period | period | 1501–1600 | 0.64 / 0.59 | 7.14 / 12.2 | 15.64 / 11.48 |
| 1920s (Q35736) | period | period | 1920–1929 | 0.32 / 0.33 | 13.24 / 17.32 | 22.39 / 27.75 |
| Dutch Golden Age (Q661566) | period | period | 1575–1675 | 0.39 / 0.38 | 15.13 / 25.9 | 16.92 / 30.72 |
| Edo period (Q184963) | period | period | 1603–1868 | 0.35 / 0.34 | 60.0 / 60.11 (timed out) | 60.0 / 60.13 (timed out) |
| Belle Époque (Q466887) | period | period | 1871–1914 | 0.38 / 0.32 | 50.77 / 60.0 (the second timed out) | 60.0 / 60.23 (timed out) |
| Baroque (Q37853) | movement | movement, period | 1590–1750 | 0.71 / 0.49 | 2.38 / 3.97 | 2.55 / 0.82 |
| Romanticism (Q37068) | movement | movement, period | 1800–1900 | 0.46 / 0.46 | 2.69 / 2.13 | 1.37 / 1.57 |
| Impressionism (Q40415) | movement | movement |  | 0.46 / 0.29 | 3.76 / 3.5 | 1.67 / 1.47 |
| cubism (Q42934) | movement | movement |  | 0.39 / 0.34 | 1.28 / 1.1 | 0.67 / 1.37 |
| abstract expressionism (Q177725) | movement | movement | 1940– | 0.68 / 0.45 | 2.11 / 1.75 | 1.04 / 0.68 |
| winter (Q1311) | subject | subject |  | 0.38 / 0.44 | 0.63 / 0.44 | 6.29 / 8.15 |
| horse (Q726) | subject | subject |  | 0.5 / 0.37 | 2.58 / 1.22 | 8.59 / 7.33 |
| still life (Q170571) | subject | subject |  | 0.75 / 0.57 | 3.89 / 3.55 | 9.68 / 16.99 |
| death (Q4) | subject | subject |  | 0.37 / 0.31 | 0.96 / 0.65 | 6.29 / 5.03 |
| love (Q316) | subject | subject |  | 0.81 / 0.58 | 0.55 / 0.78 | 12.33 / 12.94 |
| woodcut print (Q18219090) | medium | medium |  | 0.37 / 0.46 | 0.95 / 0.68 | 5.66 / 5.51 |
| watercolor painting (Q18761202) | medium | medium |  | 0.44 / 0.5 | 1.83 / 1.31 | 5.67 / 7.01 |
| pastel artwork (Q12043905) | medium | medium |  | 0.39 / 0.78 | 0.62 / 1.04 | 16.14 / 8.56 |
| etching print (Q18218093) | medium | medium |  | 0.35 / 0.29 | 0.88 / 0.94 | 11.01 / 12.99 |
| lithograph print (Q15123870) | medium | medium |  | 0.38 / 0.35 | 0.62 / 0.87 | 9.99 / 6.33 |

**The kind rule is right on all twenty**, read as the kind the works are found
by: a movement, then a period, then a medium, then a subject. Two get a second
kind. Baroque is an instance of *historical period* and of *art movement*, which
a person would agree with. Romanticism is an instance of *art movement* and *art
style* only, and is a period too because it has a start and an end (1800–1900):
a person would call it a movement and not a period, so the rule's last clause
gives it a kind nobody asked for. Nothing reads the second kind yet.

**The rule had to be asked differently.** As first written, one query asked
whether each class sat under its roots, and asking whether an item is a subclass
of *visual artwork* walked the class tree down from the root: 3.0–13.8 s a topic,
2.7 s for that one test alone. Asking for the item's own ancestors among the six
roots (century Q578, decade Q39911, historical period Q11514315, art movement
Q968159, art style Q1792644, visual artwork Q4502142) takes 0.3–0.8 s, and the
rule is applied to the answer in the client. *woodcut print* is a subclass of
*art style* (and of *engraving*), so a movement is read from instance-of only.

**Top ten works, by sitelinks** (maker, inception year; sitelinks). One entry per
work: *Sleeping Venus* has two makers, Titian and Giorgione, and is listed once.

- **16th century**: *Mona Lisa* (Leonardo da Vinci, 1503; 146); *Venus of Urbino* (Titian, 1538; 40); *The Hunters in the Snow* (Pieter Brueghel the Elder, 1565; 39); *The Virgin and Child with Saint Anne* (Leonardo da Vinci, 1511; 39); *Netherlandish Proverbs* (Pieter Brueghel the Elder, 1559; 38); *Sistine Madonna* (Raphael, 1512; 38); *Sleeping Venus* (Titian, Giorgione, 1509; 37); *Aztec sun stone* (Mexica, 1510; 36); *Saint John the Baptist* (Leonardo da Vinci, 1514; 35); *The Tempest* (Giorgione, 1506; 35).
- **1920s**: *The Treachery of Images* (René Magritte, 1929; 32); *The Great Masturbator* (Salvador Dalí, 1929; 18); *Automat* (Edward Hopper, 1927; 17); *Frederic Chopin Monument in Warsaw* (Wacław Szymanowski, 1926; 15); *Angelus Novus* (Paul Klee, 1920; 14); *The Farm* (Joan Miró, 1920; 14); *Girl at Sewing Machine* (Edward Hopper, 1921; 13); *Jules Rimet Trophy* (Abel Lafleur, 1929; 13); *Victory Monument* (no maker recorded, 1927; 13); *Black Circle* (Kazimir Malevich, 1924; 12).
- **Dutch Golden Age**: *Girl with a Pearl Earring* (Johannes Vermeer, 1665; 72); *Manneken Pis* (Hiëronymus Duquesnoy the Elder, 1619; 66); *The Night Watch* (Rembrandt, 1642; 58); *Las Meninas* (Diego Velázquez, 1656; 57); *The Anatomy Lesson of Dr. Nicolaes Tulp* (Rembrandt, 1632; 45); *The Milkmaid* (Johannes Vermeer, 1660; 44); *Ecstasy of Saint Teresa* (Gian Lorenzo Bernini, 1647; 41); *View of Delft* (Johannes Vermeer, 1661; 40); *The Surrender of Brea* (Diego Velázquez, 1634; 38); *The Astronomer* (Johannes Vermeer, 1664; 33).
- **Belle Époque** (first run): *The Little Mermaid* (Edvard Eriksen, 1913; 82); *The Starry Night* (Vincent van Gogh, 1889; 76); *The Potato Eaters* (Vincent van Gogh, 1885; 53); *Impression, Sunrise* (Claude Monet, 1872; 52); *The Kiss* (Gustav Klimt, 1907; 51); *Reply of the Zaporozhian Cossacks* (Ilya Repin, 1890; 46); *Bal du moulin de la Galette* (Pierre-Auguste Renoir, 1876; 44); *Siegessäule* (Anton von Werner, Albert Wolff, Friedrich Drake, Alexander Calandrelli, Karl Philipp Franz Keil, Moritz Schulz, 1873; 44); *Irises* (Vincent van Gogh, 1889; 43); *Wheatfield with Crows* (Vincent van Gogh, 1890; 43).
- **Edo period**: none; both runs timed out at 60 s.
- **Baroque**: *Las Meninas* (Diego Velázquez, 1656; 57); *Amber Room* (Andreas Schlüter, Johann Friedrich Eosander von Göthe, 1712; 44); *Ecstasy of Saint Teresa* (Gian Lorenzo Bernini, 1647; 41); *The Surrender of Brea* (Diego Velázquez, 1634; 38); *The Calling of Saint Matthew* (Caravaggio, 1609; 33); *Rokeby Venus* (Diego Velázquez, 1644; 31); *Las Hilanderas* (Diego Velázquez, 1655; 30); *The Beheading of Saint John the Baptist* (Caravaggio, 1608; 30); *Judith Beheading Holofernes* (Caravaggio, 1599; 29); *Medusa* (Caravaggio, 1597; 29).
- **Romanticism**: *Liberty Leading the People* (Eugène Delacroix, 1830; 67); *The Raft of the Medusa* (Théodore Géricault, 1819; 47); *The Third of May 1808* (Francisco Goya, 1814; 45); *La maja desnuda* (Francisco Goya, 1795; 45); *Saturn Devouring His Son* (Francisco Goya, 1820; 37); *The Ninth Wave* (Ivan Aivazovsky, 1850; 36); *Grande Odalisque* (Jean-Auguste-Dominique Ingres, 1814; 34); *Charles IV of Spain and His Family* (Francisco Goya, 1800; 30); *Death of Sardanapalus* (Eugène Delacroix, 1827; 30); *The Hay Wain* (John Constable, 1821; 30).
- **Impressionism**: *Impression, Sunrise* (Claude Monet, 1872; 52); *Luncheon on the Grass* (Édouard Manet, 1863; 45); *Bal du moulin de la Galette* (Pierre-Auguste Renoir, 1876; 44); *Olympia* (Édouard Manet, 1863; 43); *A Bar at the Folies-Bergère* (Édouard Manet, 1882; 39); *Where Do We Come From? What Are We? Where Are We Going?* (Paul Gauguin, 1897; 33); *The Yellow Christ* (Paul Gauguin, 1889; 32); *When Will You Marry?* (Paul Gauguin, 1892; 31); *L'Absinthe* (Edgar Degas, 1875; 30); *Luncheon of the Boating Party* (Pierre-Auguste Renoir, 1880; 30).
- **cubism**: *Guernica* (Pablo Picasso, 1937; 71); *Les Demoiselles d'Avignon* (Pablo Picasso, 1907; 37); *Garçon à la pipe* (Pablo Picasso, 1905; 22); *Dora Maar au Chat* (Pablo Picasso, 1941; 18); *Weeping Woman* (Pablo Picasso, 1937; 18); *Le Rêve* (Pablo Picasso, 1932; 16); *Nude, Green Leaves and Bust* (Pablo Picasso, 1932; 16); *The Old Guitarist* (Pablo Picasso, 1903; 16); *Massacre in Korea* (Pablo Picasso, 1951; 14); *La Vie* (Pablo Picasso, 1903; 13).
- **abstract expressionism**: *No. 5, 1948* (Jackson Pollock, 1948; 22); *Maman* (Louise Bourgeois, 1999; 21); *Woman III* (Willem de Kooning, 1953; 15); *Moon Museum* (Claes Oldenburg, Robert Rauschenberg, David Novros, John Chamberlain, Forrest Myers, Andy Warhol, 1969; 12); *Autumn Rhythm (Number 30)* (Jackson Pollock, 1950; 11); *Interchange* (Willem de Kooning, 1955; 7); *Blue Poles* (Jackson Pollock, 1952; 6); *No 1* (Mark Rothko, 1954; 6); *Orange, Red, Yellow* (Mark Rothko, 1961; 6); *Father and Son* (Louise Bourgeois, 2005; 5).
- **winter**: *The Hunters in the Snow* (Pieter Brueghel the Elder, 1565; 39); *The Massacre of the Innocents* (Pieter Brueghel the Elder; 20); *The Magpie* (Claude Monet, 1868; 19); *Killing a Deer* (Gustave Courbet, 1867; 16); *Winter Landscape with a Bird Trap* (Pieter Brueghel the Elder, 1565; 16); *Winter landscape with skaters* (Hendrick Avercamp, 1608; 16); *Landscape with Snow* (Vincent van Gogh, 1888; 15); *The Duel After the Masquerade* (Jean-Léon Gérôme, 1857; 13); *Vue de toits* (Gustave Caillebotte, 1878; 13); *Winter at the Sognefjord* (Johan Christian Dahl, 1827; 11).
- **horse**: *The Garden of Earthly Delights* (Hieronymus Bosch, 1490; 49); *The Surrender of Brea* (Diego Velázquez, 1634; 38); *Death of Sardanapalus* (Eugène Delacroix, 1827; 30); *The Hay Wain* (John Constable, 1821; 30); *The Massacre at Chios* (Eugène Delacroix, 1824; 29); *Landscape with the Fall of Icarus* (unknown maker, 2000; 26); *Lion Capital of Asoka* (unknown maker, -249; 25); *The Second of May 1808* (Francisco Goya, 1814; 25); *The Elevation of the Cross* (Peter Paul Rubens, 1610; 24); *Washington Crossing the Delaware* (Emanuel Leutze, 1851; 24).
- **still life**: *The Persistence of Memory* (Salvador Dalí, 1931; 48); *Luncheon on the Grass* (Édouard Manet, 1863; 45); *Campbell's Soup Cans* (Andy Warhol, 1962; 26); *Old Woman Cooking Eggs* (Diego Velázquez, 1618; 23); *Van Gogh's Chair* (Vincent van Gogh, 1889; 19); *The Waterseller of Seville* (Diego Velázquez, 1620; 18); *A Slaughtered Ox* (Rembrandt, 1655; 14); *Basket of Fruit* (Caravaggio, 1600; 14); *Crab on its Back* (Vincent van Gogh, 1887; 14); *Still Life with Old Shoe* (Joan Miró, 1937; 14).
- **death**: *Saturn Devouring His Son* (Francisco Goya, 1820; 37); *Death of the Virgin* (Caravaggio, 1603; 27); *Portrait of Simonetta Vespucci* (Piero di Cosimo, 1480; 15); *Death of Adonis* (Sebastiano del Piombo, 1512; 8); *Last Words of the Emperor Marcus Aurelius* (Eugène Delacroix, 1844; 8); *Death and the Child* (Edvard Munch, 1899; 7); *Saint Sebastian Attended by Saint Irene* (Georges de La Tour, 1649; 7); *The Plague* (Arnold Böcklin, 1898; 7); *Assumption of the Virgin* (Francesco Botticini, 1475; 6); *Jupiter and Semele* (Gustave Moreau, 1895; 6).
- **love**: *Erasistratus Discovering the Cause of Antiochus' Disease* (Jacques-Louis David, 1774; 15); *The abduction of Psyche* (William-Adolphe Bouguereau, 1895; 12); *Antiochus and Stratonice* (Jean-Auguste-Dominique Ingres, 1840; 11); *Cupid and Psyche* (François Gérard, 1798; 10); *Cupid and Psyche (Roman sculpture)* (no maker recorded, 200; 9); *Whisperings of Love* (William-Adolphe Bouguereau, 1889; 9); *Combat of Love and Chastity* (Pietro Perugino, 1503; 8); *Anne-Louis Girodet - Pygmalion & Galatée* (Anne-Louis Girodet, 1819; 7); *Cupid Crowned by Psyche* (Jean-Baptiste Greuze, 1787; 5); *The two cousins* (Jean-Antoine Watteau, 1716; 5).
- **woodcut print**: *The Dream of the Fisherman's Wife* (Katsushika Hokusai, 1820; 34); *The Rhinoceros* (Albrecht Dürer, 1512; 34); *Fine Wind, Clear Morning* (Katsushika Hokusai, 1830; 24); *Flammarion engraving* (unknown maker; 23); *Join, or Die* (Benjamin Franklin; 20); *Three Beauties of the Present Day* (Kitagawa Utamaro, 1790; 14); *Sudden Shower over Shin-Ōhashi Bridge and Atake* (Utagawa Hiroshige, 1857; 11); *Triumphal Arch* (Albrecht Altdorfer, Wolf Traut, Jorg Kolderer, Hans Springinklee, Albrecht Dürer, 1512; 10); *Lightnings below the summit* (Katsushika Hokusai, 1831; 9); *Holy Family with the Three Hares* (Albrecht Dürer, 1497; 8).
- **watercolor painting**: *Young Hare* (Albrecht Dürer, 1502; 19); *Pornocrates* (Félicien Rops, 1878; 17); *Great Piece of Turf* (Albrecht Dürer, 1503; 13); *Duria Antiquior* (Henry De la Beche, 1830; 10); *Wing of a European Roller* (Albrecht Dürer, 1500; 10); *Arab Woman* (John Singer Sargent, 1902; 8); *Boy Cutting Grass with a Sickle* (Vincent van Gogh, 1881; 8); *Horses in landscape* (Franz Marc, 1911; 8); *Karin by the shore* (Carl Larsson, 1908; 8); *The Apparition* (Gustave Moreau, 1876; 8).
- **pastel artwork**: *Blue Dancers* (Edgar Degas, 1897; 18); *Waiting* (Edgar Degas, 1882; 7); *Les Choristes* (Edgar Degas, 1877; 6); *The Rope Dancer* (Henri de Toulouse-Lautrec, 1899; 6); *Self-portrait* (Rosalba Carriera, 1746; 4); *Dancer with bouquet, bowing on stage* (Edgar Degas, 1877; 3); *Portrait of Vincent van Gogh (1887)* (Henri de Toulouse-Lautrec, 1887; 3); *Q8355010* (Pablo Picasso, 1903; 2); *Q8773719* (Pablo Picasso, 1899; 2); *A Woman Combing Her Hair* (Edgar Degas, 1884; 2).
- **etching print**: *The Ancient of Days* (William Blake, 1794; 19); *The Three Crosses* (Rembrandt, 1653; 13); *Christ Healing the Sick (‘Hundred Guilder Print’)* (Rembrandt, 1647; 12); *Les Grandes Misères de la guerre* (Jacques Callot, 1633; 10); *Minotauromachy* (Pablo Picasso, 1935; 5); *Strolling Actresses Dressing in a Barn* (William Hogarth, 1738; 5); *Buonsignori Map* (Stefano Bonsignori, 1584; 4); *Hell* (Eduard Wiiralt, 1932; 4); *A Chess Game: Lenin with Hitler — Vienna 1909* (Emma Löwenstamm; 3); *Alice Frontispiece* (Salvador Dalí, 1969; 3).
- **lithograph print**: *We Can Do It!* (J. Howard Miller, 1942; 34); *Drawing Hands* (M. C. Escher, 1948; 13); *Waterfall* (M. C. Escher, 1961; 13); *Ascending and Descending* (M. C. Escher, 1960; 12); *Duria Antiquior* (Henry De la Beche, 1830; 10); *Belvedere* (M. C. Escher, 1958; 9); *Hand with Reflecting Sphere* (M. C. Escher, 1935; 9); *Relativity* (M. C. Escher, 1953; 9); *Peoples of Europe, guard your dearest goods.* (Hermann Knackfuß, 1895; 7); *The Bulls of Bordeaux* (Francisco Goya, 1824; 7).

**Artists**, the first eight by sitelinks, with how many of their works have an
image. For a movement they are its own (`P135`), as *Similar artists* reads
them; for the rest, the makers of the topic's hundred most renowned works. Ranked
over every maker of every work in the topic, the first rule tried, the 1920s
began with Adolf Hitler and Winston Churchill and the 16th century included
Ferdowsi and Rembrandt; the times above for horse, still life, love, pastel,
etching and lithograph are that first rule's and were not re-run.

- **winter**: Vincent van Gogh (1118), Claude Monet (1286), Edvard Munch (1963), Pieter Brueghel the Elder (105), Caspar David Friedrich (362), Camille Pissarro (845), Gustave Courbet (594), Franz Marc (258).
- **woodcut print**: Benjamin Franklin (2), Albrecht Dürer (814), Katsushika Hokusai (339), M. C. Escher (1), Utagawa Hiroshige (368), Lucas Cranach the Elder (1051), Peter Behrens (5), Albrecht Altdorfer (234).
- **watercolor painting**: Adolf Hitler (14), Vincent van Gogh (1118), Pablo Picasso (14), Albrecht Dürer (814), William Blake (450), Paul Gauguin (739), Eugène Delacroix (530), Wassily Kandinsky (454).
- **death**: Francisco Goya (785), Peter Paul Rubens (1725), Eugène Delacroix (530), Edvard Munch (1963), Caravaggio (114), Édouard Manet (443), Paul Klee (525), Jusepe de Ribera (286).
- **16th century**: Leonardo da Vinci (775), Michelangelo (176), Raphael (325), Albrecht Dürer (814), Caravaggio (114), El Greco (541), Titian (421), Hieronymus Bosch (118).
- **1920s**: Pablo Picasso (14), Salvador Dalí (13), Henri Matisse (507), Joan Miró (25), Wassily Kandinsky (454), Paul Klee (525), René Magritte (3), Amedeo Modigliani (576).
- **Dutch Golden Age**: Michelangelo (176), Rembrandt (1229), Peter Paul Rubens (1725), Diego Velázquez (189), Caravaggio (114), Johannes Vermeer (36), El Greco (541), Pieter Brueghel the Elder (105).
- **Edo period**: timed out at 60 s twice.
- **Belle Époque**: timed out at 60 s twice.
- **Movements**: Baroque: Rubens (1725), Velázquez (189), Caravaggio (114), Zurbarán (314). Impressionism: Matisse (507), Monet (1286), Gauguin (739), Renoir (1987). Cubism: Picasso (14), Braque (3), Francis Bacon (0), Juan Gris (215). Abstract expressionism: Pollock (0), Rothko (1), Bourgeois (7), de Kooning (3). Romanticism began with Hans Christian Andersen (8), then Goya (785) and William Blake (450).

**What the measurement says:**

- **A period's works are slow, and a long or dense one fails.** Read as a range
  of the inception index (`hint:rangeSafe`), a century, a decade and the Dutch
  Golden Age answered in 7 to 26 s; the Belle Époque took 50 s once and timed out
  once; the Edo period timed out at 60 s both times. A filter on `YEAR()`
  instead timed out for the 16th century, paintings alone took 36 s, and the
  range with the optimiser turned off timed out. The server's pages give up at
  20 s (`INTERACTIVE_TIMEOUT_SECONDS`), so a period's sections will often say
  Wikidata could not be asked. Every other kind's works answered in under 4 s;
  their artists took up to 17 s.
- **The service refused the probe after the period queries.** Following four
  minutes of mostly timed-out period queries, the next query (Baroque's
  `topic`) was answered HTTP 429. A run started about a minute later was
  answered throughout, and so was every query after it.
- **A period's works are everything made in its years, anywhere.** The Dutch
  Golden Age lists *Las Meninas*, *Manneken Pis* and Bernini; the 16th century
  the *Aztec sun stone*. A named period is a place as well as a time, and the
  rule does not know it.
- **Subjects and kinds of work read well** (*The Hunters in the Snow* first for
  winter, Dürer and Hokusai for woodcut, Degas for pastel). *still life* as a
  genre (`P136`) puts *The Persistence of Memory* and *Luncheon on the Grass*
  first, as the plan found.
- **An unknown maker is a blank node**, `http://www.wikidata.org/.well-known/genid/…`:
  the *Flammarion engraving*, *Landscape with the Fall of Icarus* and the *Lion
  Capital of Asoka* each have one and no named maker. **Two works by Picasso
  among pastels have no English or `mul` label** (Q8355010, Q8773719) and come
  back titled by their QID.
- **A maker's fame is not the topic's**: Benjamin Franklin leads woodcut (*Join,
  or Die*) and Adolf Hitler leads watercolour, among the makers of the most
  renowned works.

**Topic search** (`topics_named`, EntitySearch, 20 hits, kinds read as above;
a hit with no kind is kept only if something depicts it or has it as its genre):

| Typed | Time (two runs) | Offered |
|---|---|---|
| `renaissance` | 0.98 / 0.87 s | Renaissance (movement, period), Renaissance architecture, Renaissance art, Renaissance Revival architecture (movements), *Renaissance* (period: an exhibition at the Louvre-Lens, 2012–2013) |
| `still life` | 1.14 / 0.76 s | still life (subject) |
| `16th century` | 0.60 / 0.63 s | 16th century, 16th century BC, 16th century AH, 16th century generation, 16th-century clothing (all periods) |
| `winter` | 0.81 / 0.68 s | winter (subject), Winter War (period), *Withania somnifera* and Winterswijk (subjects) |
| `baroque` | 0.93 / 1.00 s | Baroque (movement, period), Baroque music, baroque architecture, baroque revival (movements), Baroque painting (movement, period) |
| `woodcut` | 1.03 / 0.99 s | woodcut process, lumberjack, wordless novel, xylographer (subjects), woodcut print (medium) |
| `impressionism` | 0.69 / 1.12 s | Impressionism and five other movements (music, literature, Greece, the Netherlands, visual arts); three exhibitions as periods (Museum Barberini 2017, the Metropolitan Museum 2012–2013, SFMOMA 1938); impressionist music (subject) |

- **The French political party *Renaissance* (Q23731823) is the search's first
  hit and is not offered**: it has no kind and nothing depicts it.
- **Requiring the depicting item to be a work of visual art** (the ten classes)
  took 2.5–3.0 s for `still life` against 0.35–0.46 s without. Without it,
  `renaissance` found two more hits depicted (Renaissance art, Renaissance
  Revival architecture), both movements and offered anyway; no subject changed,
  so the check is on any item.
- **A work of art is not offered.** Kunisada's print *Woodcut* (Q106535219) came
  back as a movement, because it is an instance of *woodcut print*, a subclass
  of *art style*; a hit that is an instance of visual artwork is now dropped.
- **"A start and an end" lets in what is not a period**: exhibitions, a war,
  *16th-century clothing*. Every one of the twenty periods is an instance of
  century, decade or historical period, so that clause decided nothing there and
  made Romanticism a period.

**Held works' topics** (`topics_of`, over the 22 work QIDs and 24 artist QIDs in
a copy of the owner's catalogue): **1.18 s and 0.71 s**, two queries. Every one
of the 22 works got a century and a kind of work (painting, all 22); 20 are 20th
century and 2 are 19th. Six have subjects (`P180`/`P136`): landscape painting,
sunset and abstract art twice each; man, Pablo Picasso, portrait, landscape,
poplar, police officer once. 20 of the 24 artists have a movement: Rothko and
Kline abstract expressionism, Hokusai four (Japonisme, Kasei culture, ukiyo-e,
woodblock printing in Japan).

- **The Islamic calendar's centuries are centuries too.** Asked for the century
  whose years hold the inception, every 20th-century work also got *14th century
  AH* (1882–1978). The Gregorian centuries are each part of a millennium (`P361`
  → millennium Q36507) and those are not, so the query asks for that. The
  registry's centuries before 1000 overlap by a year (2nd century 100–200, 3rd
  201–301, and two 10th centuries), so a work dated on a boundary there gets two.

## Reproducing

The probes were scratch scripts, not product code: a SPARQL helper with the
User-Agent above and three queries, the identifier lookup (`VALUES ?id { … }
?work wdt:P4610 ?id`), the artist search (`EntitySearch`, then the filter above,
then `P569`/`P570` years), and the creator's works (`?work wdt:P170 wd:<artist>;
wikibase:sitelinks ?links`). Chunk 03's `live_museum`-style marked test keeps the
parts the client relies on checked, and is what to run before trusting a figure
here again; `tests/live/test_wikidata_topic_shapes_are_still_real.py` does the
same for § Topics, whose recorded answers the unit tests read from
`arrt/tests/fixtures/wikidata_topics/`.
