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

Three rules here changed on the owner's answers the same day; what each changed
is § The owner's rules, re-measured. The artists' ranking changed again after
that measurement: § The fame of their works, re-measured, at the end of this
section.

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

### The owner's rules, re-measured (Chunk 03b, 2026-10-02)

The owner answered the measurement above with three rule changes
(`build-plan-topics-and-destinations.md` § The owner's answers): years alone no
longer make a period; search drops a movement no maker of a work of visual art
belongs to (`?maker wdt:P135 ?item . ?work wdt:P170 ?maker`, the work an instance
of one of the ten classes); and a topic's artists are ranked by how many of their
works are in the topic, sitelinks breaking ties, over every work in it rather than
the makers of its hundred most renowned. For a movement the count is of its own
artists' works of visual art, and an artist of the movement with none is still
listed, last.

Measured with the client's own `topic`, `topic_artists(limit=10)` and
`topics_named`, through the same timing wrapper and User-Agent: **before** is the
unchanged client and **after** the changed one, the same day, one run each,
the twenty QIDs taken from the table above. Period topics were spaced 45 s apart;
the service answered every query in both runs and refused none.

**Kind and the artists' query time** (seconds):

| Topic | Kind before | Kind after | Artists s before | Artists s after |
|---|---|---|---|---|
| 16th century (Q7017) | period | period | 17.3 | 7.37 |
| 1920s (Q35736) | period | period | 14.68 | 6.04 |
| Dutch Golden Age (Q661566) | period | period | 22.55 | 20.91 |
| Edo period (Q184963) | period | period | 51.01 | 25.76 |
| Belle Époque (Q466887) | period | period | 51.63 | 33.06 |
| Baroque (Q37853) | movement, period | movement, period | 1.36 | 4.72 |
| Romanticism (Q37068) | movement, period | movement | 1.2 | 4.92 |
| Impressionism (Q40415) | movement | movement | 1.11 | 8.03 |
| cubism (Q42934) | movement | movement | 0.98 | 2.34 |
| abstract expressionism (Q177725) | movement | movement | 0.57 | 2.27 |
| winter (Q1311) | subject | subject | 11.16 | 0.85 |
| horse (Q726) | subject | subject | 10.0 | 1.61 |
| still life (Q170571) | subject | subject | 11.64 | 7.59 |
| death (Q4) | subject | subject | 7.02 | 0.61 |
| love (Q316) | subject | subject | 6.91 | 1.89 |
| woodcut print (Q18219090) | medium | medium | 7.53 | 0.52 |
| watercolor painting (Q18761202) | medium | medium | 5.77 | 0.96 |
| pastel artwork (Q12043905) | medium | medium | 5.09 | 0.57 |
| etching print (Q18218093) | medium | medium | 12.96 | 0.8 |
| lithograph print (Q15123870) | medium | medium | 11.17 | 1.16 |

**What changed in kind:** Romanticism alone of the twenty, from movement and
period to movement. In search, Renaissance (Q4692) and *Baroque painting* lose
their period kind the same way. Every other topic's kind is as before.

**Time:** the artists of a subject or a kind of work now answer in under 2 s
(still life 7.6 s), from 5 to 13 s; a century's and a decade's in 6 to 7 s, from
15 to 17 s. The Edo period's and the Belle Époque's, which timed out in Chunk
03's runs, answered in both: 51 s before, 26 and 33 s after. The Dutch Golden
Age's took 21 to 23 s both times. All three are still over the pages' 20 s. A movement's artists are slower, 2 to 8 s from about 1 s, because
every work of every artist of the movement is now counted.

**Top ten artists** (after: works in the topic; sitelinks). The rows came back
from the service in no order: the grouping around the ranked choice keeps none,
so the client puts them back in rank order.

- **16th century**. Before: Leonardo da Vinci, Michelangelo, Raphael, Albrecht Dürer, Caravaggio, El Greco, Titian, Hieronymus Bosch, Pieter Brueghel the Elder, Jacopo Tintoretto. After: Lucas Cranach the Elder (992; 60), Philip Galle (553; 14), Titian (415; 109), Jacopo Tintoretto (372; 85), Maarten van Heemskerck (344; 27), El Greco (329; 115), Joris Hoefnagel (310; 18), Lucas Cranach the Younger (297; 42), Hendrik Goltzius (288; 31), Paolo Veronese (274; 79).
- **1920s**. Before: Pablo Picasso, Salvador Dalí, Henri Matisse, Joan Miró, Wassily Kandinsky, Paul Klee, René Magritte, Amedeo Modigliani, Diego Rivera, Kazimir Malevich. After: Stanisław Ignacy Witkiewicz (872; 49), Alfred Stieglitz (443; 49), Edvard Munch (356; 120), Marc Chagall (351; 103), Lovis Corinth (314; 50), Augusto Malta (313; 2), Paul Klee (300; 97), André Dunoyer de Segonzac (291; 10), Jan Sluijters (267; 16), Percy Benzie Abery (266; 5).
- **Dutch Golden Age**. Before: Michelangelo, Rembrandt, Peter Paul Rubens, Diego Velázquez, Caravaggio, Johannes Vermeer, El Greco, Pieter Brueghel the Elder, Gian Lorenzo Bernini, Artemisia Gentileschi. After: Peter Paul Rubens (2049; 175), Anthony van Dyck (1450; 84), Jacques Callot (1357; 35), Rembrandt (1133; 207), David Teniers the Younger (1120; 31), Jan van Goyen (703; 42), Philips Wouwerman (597; 33), El Greco (567; 115), Jacob van Ruisdael (552; 48), Jacob Jordaens (547; 44).
- **Edo period**. Before: Rembrandt, Francisco Goya, Peter Paul Rubens, Diego Velázquez, Claude Monet, Jean-Auguste-Dominique Ingres, Eugène Delacroix, Caravaggio, Johannes Vermeer, Édouard Manet. After: Paul Gavarni (2771; 27), Honoré Daumier (2506; 65), Thomas Rowlandson (2036; 34), Peter Paul Rubens (1990; 175), Anthony van Dyck (1477; 84), Jacques Callot (1339; 35), David Teniers the Younger (1158; 31), Rembrandt (1146; 207), George Catlin (887; 37), Charles Balthazar Julien Févret de Saint-Mémin (856; 4).
- **Belle Époque**. Before: Vincent van Gogh, Pablo Picasso, Claude Monet, Paul Cézanne, Paul Gauguin, Auguste Rodin, Edvard Munch, Pierre-Auguste Renoir, Edgar Degas, Édouard Manet. After: Militão Augusto de Azevedo (9337; 4), John Thomas (2419; 10), Stanisław Wyspiański (2208; 48), Pierre-Auguste Renoir (1798; 115), Marc Ferrez (1522; 10), Edvard Munch (1394; 120), Apel·les Mestres i Oñós (1157; 13), Theo van Doesburg (1130; 60), Émile Bernard (1088; 52), Percy Benzie Abery (1045; 5).
- **Baroque**. Before: Peter Paul Rubens, Diego Velázquez, Caravaggio, Francisco de Zurbarán, Gian Lorenzo Bernini, Frans Hals, Jusepe de Ribera, Giovanni Battista Tiepolo, Francesco Borromini, Guido Reni. After: Peter Paul Rubens (2852; 175), David Teniers the Younger (1475; 31), Jacob Jordaens (621; 44), Nicolaes Pieterszoon Berchem (511; 24), Giovanni Battista Tiepolo (449; 67), Wenceslaus Hollar (448; 32), Luca Giordano (443; 39), Stefano della Bella (405; 13), Guido Reni (393; 55), Cornelius van Poelenburgh (350; 19).
- **Romanticism**. Before: Hans Christian Andersen, Francisco Goya, William Blake, Taras Shevchenko, Jean-Auguste-Dominique Ingres, Mikhail Lermontov, Eugène Delacroix, E. T. A. Hoffmann, Théophile Gautier, J. M. W. Turner. After: J. M. W. Turner (4052; 87), Thomas Rowlandson (2561; 34), Francisco Goya (945; 186), Eugène Delacroix (614; 121), William Blake (583; 162), John Constable (570; 72), Thomas Lawrence (556; 40), Henry Raeburn (451; 28), Akseli Gallen-Kallela (437; 52), Ivan Aivazovsky (418; 73).
- **Impressionism**. Before: Henri Matisse, Claude Monet, Paul Gauguin, Pierre-Auguste Renoir, Edgar Degas, Édouard Manet, Mary Cassatt, Camille Pissarro, Alfred Sisley, Berthe Morisot. After: Pierre-Auguste Renoir (2131; 115), Lovis Corinth (1351; 50), Claude Monet (1284; 155), Eliseu Visconti (1165; 12), Eugène Louis Boudin (926; 53), Camille Pissarro (878; 87), John Singer Sargent (850; 62), Alfred Sisley (838; 74), Henri Matisse (818; 181), Paul Gauguin (756; 133).
- **cubism**. Before: Pablo Picasso, Georges Braque, Francis Bacon, Juan Gris, Francis Picabia, André Derain, Fernand Léger, Josef Čapek, Max Jacob, Alexander Archipenko. After: Pablo Picasso (2215; 265), Fernand Léger (706; 54), André Derain (499; 55), Ossip Zadkine (473; 42), Georges Braque (434; 86), Maurice de Vlaminck (350; 47), Victor Brauner (330; 32), Alfred Pellan (238; 8), Juan Gris (237; 63), William Zorach (193; 15).
- **abstract expressionism**. Before: Jackson Pollock, Mark Rothko, Louise Bourgeois, Willem de Kooning, Karel Appel, Arshile Gorky, Captain Beefheart, James Rosenquist, Helen Frankenthaler, Barnett Newman. After: Richard Diebenkorn (1496; 18), Mark Rothko (1274; 71), Jacob Kainen (622; 2), Jackson Pollock (252; 118), Robert Motherwell (208; 29), Sam Francis (201; 24), Philip Guston (185; 26), Franz Kline (180; 32), Willem de Kooning (178; 53), Karel Appel (177; 47).
- **winter**. Before: Vincent van Gogh, Claude Monet, Edvard Munch, Pieter Brueghel the Elder, Caspar David Friedrich, Camille Pissarro, Gustave Courbet, Franz Marc, Alfred Sisley, Ivan Aivazovsky. After: Claude Monet (10; 155), Alfred Sisley (9; 74), Camille Pissarro (7; 87), Percy Benzie Abery (7; 5), Johan Christian Dahl (6; 36), Carl Hasenpflug (6; 10), Régis François Gignoux (6; 7), Axel Stephansen (6; 1), Edvard Munch (5; 120), Simon Kozhin (5; 18).
- **horse**. Before: Rembrandt, Raphael, Francisco Goya, Peter Paul Rubens, Diego Velázquez, Jean-Auguste-Dominique Ingres, Eugène Delacroix, El Greco, Pierre-Auguste Renoir, Sandro Botticelli. After: Philips Wouwerman (239; 33), Grandma Moses (187; 38), Józef Chełmoński (105; 28), Thomas Rowlandson (89; 34), Aelbert Cuyp (59; 41), Werner Haberkorn (50; 3), Théodore Géricault (49; 71), Peter Paul Rubens (42; 175), George Catlin (34; 37), Jean Moyreau (33; 2).
- **still life**. Before: Vincent van Gogh, Pablo Picasso, Salvador Dalí, Rembrandt, Albrecht Dürer, Francisco Goya, Henri Matisse, Andy Warhol, Diego Velázquez, Claude Monet. After: Abraham van Beijeren (304; 26), Jan Fyt (283; 25), Pieter Claesz (270; 35), Pablo Picasso (248; 265), Jan Sluijters (243; 16), Kees Verwey (212; 7), Adriaen de Grijef (200; 4), Frans Snyders (182; 31), Émile Bernard (173; 52), Lovis Corinth (169; 50).
- **death**. Before: Francisco Goya, Peter Paul Rubens, Eugène Delacroix, Edvard Munch, Caravaggio, Édouard Manet, Paul Klee, Jusepe de Ribera, Giovanni Battista Tiepolo, Robert Capa. After: Jean Le Pautre (15; 11), Gustave Moreau (14; 53), Militão Augusto de Azevedo (12; 4), Léon Cogniet (8; 30), Pierre Mariette II (8; 1), Edvard Munch (7; 120), Claude Vignon (7; 16), François Chauveau (7; 11), Abraham Bosse (5; 23), Gilles Rousselet (5; 6).
- **love**. Before: Raphael, Albrecht Dürer, Peter Paul Rubens, Jean-Auguste-Dominique Ingres, Auguste Rodin, Titian, Jacques-Louis David, Jean-Antoine Watteau, Pietro Perugino, William-Adolphe Bouguereau. After: Nicolas de Larmessin (7; 3), François Perrier (4; 15), François de Poilly (4; 8), François Gérard (3; 36), Pierre-Jacques Cazes (3; 11), Raphael (2; 195), William-Adolphe Bouguereau (2; 63), Théodore Chassériau (2; 31), Maarten van Heemskerck (2; 27), Jean-Bruno Gassies (2; 5).
- **woodcut print**. Before: Benjamin Franklin, Albrecht Dürer, Katsushika Hokusai, M. C. Escher, Utagawa Hiroshige, Lucas Cranach the Elder, Peter Behrens, Albrecht Altdorfer, Kitagawa Utamaro, Raoul Dufy. After: Albrecht Dürer (421; 187), Utagawa Hiroshige (260; 68), Yoshitoshi (236; 26), Frans Masereel (223; 31), Jef Diederen (189; 3), Kitagawa Utamaro (165; 50), Katsushika Hokusai (158; 177), Suzuki Harunobu (158; 34), Sharaku (143; 28), Marianne van der Heijden (82; 3).
- **watercolor painting**. Before: Adolf Hitler, Vincent van Gogh, Pablo Picasso, Albrecht Dürer, William Blake, Paul Gauguin, Eugène Delacroix, Wassily Kandinsky, Paul Klee, Caspar David Friedrich. After: J. M. W. Turner (3155; 87), Ferdinand Bauer (964; 23), Mary Vaux Walcott (787; 14), Hmayak Hakobyan (424; 5), William Catto (423; 0), Gerardo Orakian (348; 1), James Tissot (339; 47), Daniel Lysons (330; 4), Winslow Homer (320; 44), Ilon Wikland (241; 33).
- **pastel artwork**. Before: Vincent van Gogh, Pablo Picasso, Eugène Delacroix, Pierre-Auguste Renoir, Edgar Degas, Édouard Manet, Henri de Toulouse-Lautrec, Mary Cassatt, Jean-François Millet, Élisabeth Louise Vigée Le Brun. After: Stanisław Ignacy Witkiewicz (2021; 49), Stanisław Wyspiański (336; 48), Edgar Degas (86; 114), Jean-Étienne Liotard (40; 32), Mary Cassatt (34; 89), Leon Wyczółkowski (32; 26), Maurice Quentin de La Tour (25; 40), Odilon Redon (23; 60), Cornelis Troost (22; 12), Giuseppe De Nittis (19; 24).
- **etching print**. Before: Vincent van Gogh, Pablo Picasso, Salvador Dalí, Rembrandt, Albrecht Dürer, Francisco Goya, William Blake, Pierre-Auguste Renoir, Paul Klee, William Hogarth. After: James Ensor (653; 51), James Gillray (286; 33), Isaac Cruikshank (230; 10), Jules De Bruycker (181; 9), J. M. W. Turner (179; 87), Francesco Bartolozzi (153; 22), William Miller (132; 6), George Cruikshank (131; 33), David Young Cameron (108; 13), Thomas Rowlandson (107; 34).
- **lithograph print**. Before: Vincent van Gogh, Pablo Picasso, Salvador Dalí, Francisco Goya, Eugène Delacroix, Edvard Munch, Henri de Toulouse-Lautrec, Camille Pissarro, M. C. Escher, Franz Marc. After: John Gould (1410; 40), Louis-Joseph van Peteghem (98; 2), James Ensor (83; 51), François-Séraphin Delpech (70; 6), John Doyle (63; 8), Pieter Defesche (63; 2), Henri Borremans (52; 2), Honoré Daumier (51; 65), Charles Heaphy (50; 9), Alexandre Joos (49; 0).

**What the ranking says.** Every list changed, and every change is the counts:

- **The fame-from-elsewhere cases are gone.** Benjamin Franklin is out of woodcut
  (Dürer first, 421 woodcuts), Adolf Hitler out of watercolour, and Hans Christian
  Andersen, Lermontov and E. T. A. Hoffmann out of Romanticism, which Turner,
  Rowlandson, Goya and Delacroix now lead.
- **A count rewards whoever has an item per work.** Printmakers, illustrators and
  photographers lead: Militão Augusto de Azevedo's 9337 works top the Belle
  Époque, Philip Galle's 553 the 16th century, John Gould's 1410 lithograph
  print, Jean Le Pautre's 15 death. That a museum's or archive's catalogue import
  put them there is inference, not measured. Asked directly, Leonardo has 35 works dated 1501 to 1600,
  Michelangelo 107 and Raphael 195, against 274 for tenth place (Veronese); for
  winter, Pieter Brueghel the Elder has 3 and Vincent van Gogh 1, against 5 for
  tenth. Nothing here is a fault in the query; it is what the rule ranks by.
- **A period is still everything made in its years, anywhere** (§ above): the
  Edo period's ten include no Japanese artist (Gavarni, Daumier, Rowlandson lead).
  That is Chunk 05's matter, not the ranking's.

**Topic search** (seconds; kinds as the client reads them):

| Typed | Before (s) | Offered before | After (s) | Offered after |
|---|---|---|---|---|
| `renaissance` | 0.64 | Renaissance (movement, period); Renaissance architecture (movement); Renaissance art (movement); Renaissance Revival architecture (movement); Renaissance (period) | 1.07 | Renaissance (movement); Renaissance architecture (movement); Renaissance Revival architecture (movement) |
| `winter` | 0.75 | winter (subject); Winter War (period); Withania somnifera (subject); Winterswijk (subject) | 1.0 | winter (subject); Winter War (subject); Withania somnifera (subject); Winterswijk (subject) |
| `16th century` | 0.97 | 16th century (period); 16th century BC (period); 16th century AH (period); 16th century generation (period); 16th-century clothing (period) | 1.11 | 16th century (period); 16th century BC (period); 16th century AH (period) |
| `impressionism` | 0.96 | Impressionism (movement); impressionism in music (movement); impressionism (movement); Impressionism in Greece (movement); Impressionism in the Netherlands (movement); Impressionism: The Art of Landscape (period); impressionism in visual arts (movement); Impressionism, Fashion, and Modernity (period); Impressionism: Seurat, Renoir, Monet, Sisley, Pissarro (period); impressionist music (subject) | 2.31 | Impressionism (movement); impressionist music (subject) |
| `baroque` | 0.84 | Baroque (movement, period); Baroque music (movement); baroque architecture (movement); baroque revival (movement); baroque pop (subject); Baroque painting (movement, period) | 3.21 | Baroque (movement, period); Baroque music (movement); baroque architecture (movement); baroque pop (subject); Baroque painting (movement) |

- **The exhibitions, the war and the clothing are no longer periods.** The
  Louvre-Lens *Renaissance* (Q16672500, 2012–2013), *Impressionism: The Art of
  Landscape* (Q106858047), *16th-century clothing* (Q28972137) and *16th century
  generation* (Q65643776) each read as a subject, asked one by one, and none is
  offered; nor are the other two Impressionism exhibitions. The Winter War (Q134949,
  1939–1940) is offered as a subject, because something depicts it.
- **A music movement is dropped, but not every one.** *impressionism in music*
  (Q837182) goes, and so does *baroque revival*. **Baroque music (Q8361) is still
  offered**: eight makers of works of visual art name it as their movement,
  composers who also drew or painted (Christian Ludwig von Loewenstern 8 works,
  Robert Woodcock 4, Louis Aubert 3, Constantijn Huygens 2, Jan Zach 2,
  Jean-Philippe Rameau, Corona Schröter and François Roberday 1 each). The rule
  as chosen keeps it, and it was not tuned.
- **Visual movements nobody is recorded as belonging to go too**: *Renaissance
  art* (Q1133779), *impressionism in visual arts* (Q132300980), and Impressionism
  in Greece and in the Netherlands. No maker of a work of visual art names them,
  so as movements their pages would have listed no works.
- **The check costs time**: `baroque` took 3.2 s and `impressionism` 2.3 s, from
  under 1 s.

### The fame of their works, re-measured (Chunk 03d, 2026-10-02)

Asked again after the measurement above, the owner chose to rank a topic's
artists by **the sum of the sitelinks of their works in the topic**, their own
sitelinks breaking ties (`build-plan-topics-and-destinations.md` § The owner's
answers). Each work is counted once per artist before it is summed, however many
routes reach it. For a movement, it is still its own artists' works of visual
art, and one with none sums to nought.

Measured with the client's own `topic` and `topic_artists(limit=10)`, through the
same timing wrapper and User-Agent, over the twenty QIDs of the first table:
**03b's rule** is the unchanged client and **by fame** the changed one, one run
each, the same afternoon. Period topics were spaced 45 s apart. The service
refused nothing. 03b's rule gave back the lists recorded above, name for name,
for all twenty.

**The artists' query time** (seconds; the whole call, with its image count):

| Topic | Kind | Artists s, 03b's rule | Artists s, by fame |
|---|---|---|---|
| 16th century (Q7017) | period | 3.43 | 3.15 |
| 1920s (Q35736) | period | 8.13 | 8.07 |
| Dutch Golden Age (Q661566) | period | 8.29 | 14.78 |
| Edo period (Q184963) | period | 26.21 | 48.84 |
| Belle Époque (Q466887) | period | 46.16 | timed out (60.0) |
| Baroque (Q37853) | movement, period | 7.75 | 3.55 |
| Romanticism (Q37068) | movement | 1.84 | 6.34 |
| Impressionism (Q40415) | movement | 3.71 | 4.72 |
| cubism (Q42934) | movement | 1.22 | 2.13 |
| abstract expressionism (Q177725) | movement | 2.05 | 2.4 |
| winter (Q1311) | subject | 1.05 | 1.31 |
| horse (Q726) | subject | 0.84 | 4.2 |
| still life (Q170571) | subject | 1.91 | 2.53 |
| death (Q4) | subject | 0.57 | 2.14 |
| love (Q316) | subject | 0.46 | 0.43 |
| woodcut print (Q18219090) | medium | 0.53 | 1.61 |
| watercolor painting (Q18761202) | medium | 0.78 | 3.52 |
| pastel artwork (Q12043905) | medium | 0.87 | 1.49 |
| etching print (Q18218093) | medium | 0.77 | 0.63 |
| lithograph print (Q15123870) | medium | 1.25 | 0.67 |

**The Belle Époque timed out once, and so did 03b's rule.** Asked again with
60 s between runs: by fame 29.36 s, then 03b's rule timed out at 60 s, then by
fame 40.07 s. The Edo period, asked the same way, took 44.47 s by 03b's rule and
26.78 s by fame. Both rules sit near the client's 60 s for those two, and the
same query varies by more than the rules differ. The Dutch Golden Age (14.8 s)
is the only other period over 10 s. Elsewhere summing is slower than counting by
up to 3.5 s (horse 0.8 s to 4.2 s), and no topic that is not a period took over
7 s (Romanticism 6.3 s).

**Top ten artists by fame** (the sum of their works' sitelinks; how many works;
their own sitelinks). The Belle Époque's, from the retry that answered: Vincent
van Gogh, Pierre-Auguste Renoir, Claude Monet, Paul Gauguin, Edvard Munch, Paul
Cézanne, Édouard Manet, Pablo Picasso, Gustav Klimt, John Singer Sargent.

- **16th century**: Titian (1790; 415; 109), Raphael (1312; 195; 195), El Greco (1033; 329; 115), Pieter Brueghel the Elder (746; 98; 92), Caravaggio (605; 48; 116), Lorenzo Lotto (518; 146; 45), Michelangelo (505; 107; 259), Albrecht Dürer (504; 257; 187), Lucas Cranach the Elder (498; 992; 60), Jacopo Tintoretto (492; 372; 85).
- **1920s**: Wassily Kandinsky (141; 115; 103), Salvador Dalí (138; 220; 247), Henri Matisse (91; 202; 181), René Magritte (86; 97; 96), Joan Miró (82; 104; 106), Paul Klee (68; 300; 97), Edward Hopper (62; 41; 60), Pablo Picasso (49; 243; 265), Félix Vallotton (44; 83; 47), Max Ernst (35; 114; 72).
- **Dutch Golden Age**: Rembrandt (1796; 1133; 207), Peter Paul Rubens (1491; 2049; 175), Caravaggio (1265; 107; 116), El Greco (1234; 567; 115), Diego Velázquez (976; 176; 167), Johannes Vermeer (869; 36; 116), Anthony van Dyck (566; 1450; 84), Artemisia Gentileschi (484; 126; 74), Bartolomé Esteban Murillo (445; 263; 81), Gian Lorenzo Bernini (425; 166; 80).
- **Edo period**: Francisco Goya (1798; 555; 186), Rembrandt (1795; 1146; 207), Peter Paul Rubens (1450; 1990; 175), Diego Velázquez (999; 180; 167), Johannes Vermeer (869; 36; 116), Gustave Courbet (858; 439; 81), Jean-Auguste-Dominique Ingres (744; 311; 133), Jacques-Louis David (700; 264; 94), Anthony van Dyck (571; 1477; 84), Caspar David Friedrich (569; 338; 91).
- **Belle Époque**: timed out at 60 s in this run; see the retries above.
- **Baroque**: Peter Paul Rubens (1510; 2852; 175), Caravaggio (1266; 116; 116), Diego Velázquez (1000; 200; 167), Gian Lorenzo Bernini (513; 220; 80), Guercino (390; 348; 46), Francisco de Zurbarán (383; 308; 81), Frans Hals (382; 312; 68), Jusepe de Ribera (366; 330; 68), Annibale Carracci (292; 340; 50), Giovanni Battista Tiepolo (258; 449; 67).
- **Romanticism**: Francisco Goya (1842; 945; 186), Jean-Auguste-Dominique Ingres (746; 347; 133), Eugène Delacroix (563; 614; 121), J. M. W. Turner (552; 4052; 87), John Constable (274; 570; 72), Thomas Lawrence (195; 556; 40), Francesco Hayez (183; 104; 51), Théodore Géricault (171; 371; 71), Ivan Aivazovsky (131; 418; 73), Horace Vernet (126; 245; 40).
- **Impressionism**: Pierre-Auguste Renoir (1354; 2131; 115), Claude Monet (1137; 1284; 155), Édouard Manet (1055; 466; 113), Paul Gauguin (789; 756; 133), Henri Matisse (617; 818; 181), Camille Pissarro (463; 878; 87), John Singer Sargent (458; 850; 62), Edgar Degas (452; 667; 114), John William Waterhouse (381; 141; 49), Gustave Caillebotte (374; 253; 54).
- **cubism**: Pablo Picasso (855; 2215; 265), Francis Bacon (119; 135; 69), Georges Braque (104; 434; 86), Juan Gris (54; 237; 63), André Derain (50; 499; 55), Fernand Léger (46; 706; 54), Jean Metzinger (35; 97; 33), Amadeo de Souza Cardoso (31; 80; 33), Francis Picabia (28; 133; 57), Marie Laurencin (19; 142; 43).
- **abstract expressionism**: Jackson Pollock (63; 252; 118), Mark Rothko (43; 1274; 71), Willem de Kooning (38; 178; 53), Louise Bourgeois (37; 35; 59), Mark di Suvero (19; 41; 11), Barnett Newman (17; 97; 37), David Smith (12; 50; 18), John Chamberlain (12; 9; 13), Louise Nevelson (7; 140; 30), Joan Mitchell (7; 65; 25).
- **winter**: Pieter Brueghel the Elder (75; 3; 92), Claude Monet (32; 10; 155), Hendrick Avercamp (19; 4; 44), Gustave Courbet (18; 3; 81), Camille Pissarro (16; 7; 87), Vincent van Gogh (15; 1; 266), Jean-Léon Gérôme (13; 2; 57), Gustave Caillebotte (13; 1; 54), Caspar David Friedrich (11; 3; 91), Johan Christian Dahl (11; 6; 36).
- **horse**: Peter Paul Rubens (140; 42; 175), Eugène Delacroix (107; 28; 121), Diego Velázquez (89; 9; 167), Francisco Goya (55; 8; 186), Franz Marc (55; 19; 75), Józef Chełmoński (55; 105; 28), Anthony van Dyck (54; 19; 84), Hieronymus Bosch (49; 1; 93), Théodore Géricault (45; 49; 71), Jacques-Louis David (35; 4; 94).
- **still life**: Vincent van Gogh (270; 130; 266), Paul Cézanne (139; 135; 139), Édouard Manet (104; 39; 113), Jean-Baptiste-Siméon Chardin (91; 138; 51), Salvador Dalí (82; 37; 247), Henri Matisse (61; 83; 181), Paul Gauguin (49; 52; 133), Pablo Picasso (47; 248; 265), Diego Velázquez (46; 4; 167), Luis Egidio Meléndez (43; 65; 17).
- **death**: Francisco Goya (40; 2; 186), Caravaggio (27; 1; 116), Piero di Cosimo (15; 1; 45), Eugène Delacroix (11; 2; 121), Gustave Moreau (9; 14; 53), Sebastiano del Piombo (8; 1; 38), Edvard Munch (7; 7; 120), Arnold Böcklin (7; 1; 56), Georges de La Tour (7; 1; 53), Pierre-Paul Prud'hon (7; 2; 28).
- **love**: William-Adolphe Bouguereau (21; 2; 63), Jacques-Louis David (15; 1; 94), François Gérard (15; 3; 36), Jean-Auguste-Dominique Ingres (11; 1; 133), Pietro Perugino (8; 1; 65), Anne-Louis Girodet (7; 1; 35), Jean-Antoine Watteau (5; 1; 70), Jean-Baptiste Greuze (5; 1; 37), Giovanni Segantini (4; 1; 33), Nasreddine Dinet (4; 1; 22).
- **woodcut print**: Albrecht Dürer (291; 421; 187), Utagawa Hiroshige (245; 260; 68), Katsushika Hokusai (214; 158; 177), M. C. Escher (40; 17; 87), Benjamin Franklin (20; 1; 216), Kitagawa Utamaro (19; 165; 50), Franz Marc (13; 19; 75), Hans Springinklee (12; 4; 9), Sharaku (11; 143; 28), Lucas Cranach the Elder (10; 50; 60).
- **watercolor painting**: Vincent van Gogh (98; 72; 266), Albrecht Dürer (51; 19; 187), Stanisław Masłowski (26; 27; 10), Anders Zorn (24; 20; 53), J. M. W. Turner (22; 3155; 87), John Singer Sargent (22; 43; 62), Winslow Homer (19; 320; 44), Edward Burne-Jones (17; 33; 47), Félicien Rops (17; 1; 34), Carl Larsson (14; 14; 57).
- **pastel artwork**: Edgar Degas (55; 86; 114), Stanisław Wyspiański (15; 336; 48), Pablo Picasso (9; 6; 265), Henri de Toulouse-Lautrec (9; 2; 97), Maurice Quentin de La Tour (8; 25; 40), Rosalba Carriera (8; 12; 39), Édouard Manet (6; 12; 113), Leon Wyczółkowski (6; 32; 26), Fernand Khnopff (5; 9; 30), Odilon Redon (4; 23; 60).
- **etching print**: Rembrandt (39; 46; 207), William Blake (19; 19; 162), Jacques Callot (10; 19; 35), Albrecht Dürer (9; 9; 187), William Hogarth (8; 81; 82), Pablo Picasso (7; 11; 265), Francisco Goya (6; 5; 186), James Ensor (5; 653; 51), Wenceslaus Hollar (5; 43; 32), Adrien de Witte (5; 4; 4).
- **lithograph print**: M. C. Escher (114; 22; 87), J. Howard Miller (34; 1; 9), Walter Hood Fitch (22; 25; 14), Henri de Toulouse-Lautrec (19; 15; 97), Alphonse Mucha (10; 10; 70), Henry De la Beche (10; 1; 23), Francisco Goya (7; 1; 186), Hermann Knackfuß (7; 1; 9), Pablo Picasso (5; 3; 265), Honoré Daumier (3; 51; 65).

**What the ranking says:**

- **The best-known artists are back.** Titian, Raphael, Michelangelo and
  Brueghel for the 16th century; Kandinsky, Dalí, Matisse and Magritte for the 1920s; Rembrandt, Vermeer
  and Velázquez for the Dutch Golden Age; van Gogh, Renoir and Monet for the Belle
  Époque. Subjects too: Brueghel first for winter, van Gogh and Cézanne for still
  life, Goya and Caravaggio for death. The printmakers, photographers and
  illustrators that a count put first (Philip Galle, Militão Augusto de Azevedo,
  John Gould, Jean Le Pautre) are gone from all twenty.
- **Leonardo is still not in the 16th century's ten.** His 35 works dated 1501 to
  1600 sum to 345, *Mona Lisa* 146 of it, against 492 for tenth place
  (Tintoretto). Asked by the same period pattern restricted to him.
- **Many obscure works now rank below a few famous ones.** James Ensor has 653
  etchings worth 5 sitelinks together and is eighth, below Rembrandt's 46 (39);
  J. M. W. Turner's 3155 watercolours (22) are fifth; Philip Galle is out.
- **One famous work can carry its maker.** Benjamin Franklin is back in woodcut,
  fifth, on *Join, or Die* alone (20); J. Howard Miller is second in lithograph
  on *We Can Do It!* (34); Hieronymus Bosch is in horse on one work. This is
  the work's fame, not the maker's: Franklin was first under the first rule, on
  his own 216 sitelinks, and is now below Dürer, Hiroshige, Hokusai and Escher.
  Adolf Hitler is not in watercolour's ten, and no writer is in Romanticism's
  (Andersen, Lermontov, Hoffmann and Gautier were, under the first rule).
- **A period is still everything made in its years, anywhere.** The Edo period's
  ten are European (Goya, Rembrandt, Rubens), as they were under the count.

## Matching a wanted work (After Review, 2026-10-02)

Measured live on 2026-10-02 for `build-plan-after-review.md` Chunk 04, with
`WikidataRegistry.works_matching` (the typeahead's search, `prefix=False`,
limit 8), over the seven works the August "salvador dali" Ask run (`4ab5063d`)
left with no scan. User-Agent as above. Every call answered in 0.2-0.8 s.

| Stored title | Title alone: first match | With "Salvador Dalí" added |
|---|---|---|
| Illumined Pleasures (1929) | Q4380958, Dalí (the only match) | not asked |
| Lobster Telephone (1938) | Q2990594, Dalí, 13 sitelinks, image; then Q63109663, Dalí, 0 | the same two |
| Mae West Lips Sofa (1938) | Q17986845, Dalí, image (the only match) | not asked |
| Metamorphosis of Narcissus (1937) | Q2464824, Dalí (the only match) | not asked |
| Mountain Lake (1938) | **no Dalí item**: eight landscapes by others (Heade, Sonntag, Turner, unknown) | **Q28555476, Dalí** (the only match) |
| Portrait of my Sister (1925) | Q3937747, Dalí; then Q12142565, Dalí; then Émile Bernard | not asked |
| The Persistence of Memory (1931) | Q25729, Dalí, 48 sitelinks; then *The Disintegration of…*, Dalí | Q25729, then *The Disintegration…* |

What it settles for the picker:

- **The year in brackets does no harm.** Results were identical with and without
  it (the search drops tokens that are not words); the service strips it anyway
  so the narrower search is asked for the words that matter.
- **Search with the artist's name first.** It found the one item the title alone
  missed (*Mountain Lake*) and narrowed the rest. "dali" and "dalí" answered
  the same. When it finds nothing, the title alone is asked.
- **A picker, not a match.** Two titles have two Dalí items each (*Lobster
  Telephone*, *Portrait of my Sister*), which no rule about the creator can
  choose between, and `data-model.md` § Registry identity forbids matching by
  title in any case. The owner chose the curator's pick (2026-10-02).
- **Five of seven matches carry no image.** A pick is still worth making for
  them: a re-search by item asks Commons, and the image may be added later.

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
