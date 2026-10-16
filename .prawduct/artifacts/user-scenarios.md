# User Scenarios

**Written 2026-10-01.** This artifact lists what the curator comes to Arrt to do.
The information architecture is to be re-derived from it. It precedes any IA or
UX change to search, and the IA does not yet reflect it.

**Status: a draft the owner has not confirmed.** The owner asked for it and set
two of its distinctions: search intent is like a movie or music app's, where a
query may mean something held or something not held; and finding a work that
*exists* is different from finding one that *can be downloaded*. The scenario
list and every frequency below are the builder's reading, marked as assumptions
until the owner corrects them.

## Why this exists

`product-brief.md` § Core Flows lists eight flows, and each is a **pipeline
stage**: intent, discovery, review, acquire, organise, display, ambient, MCP.
`information-architecture.md` § User Flows traces five of them through screens.
Neither says what the curator is trying to do when they open the app, where they
start, or how often. So the search design answers *how Sonarr does it*
(`information-architecture.md` § The *arr layout, "One search box, two scopes")
and not *what the curator means by "dali"*. The brief's one real scenario, "I love
Dalí and Delaunay — who else should I look at?", was added on 2026-08-10, after
it was found that nothing served it.

## Four layers, not two

"Do I have it?" has more answers than *yes* and *go get it*. Whether a work
**exists** is a different question from whether it **can be downloaded**, and the
two have different sources and costs. Downloadable then splits again: seeing a
work is not the same as being able to hang it.

| Layer | The curator's question | Source | Cost |
|---|---|---|---|
| **Held** | Is it in my library? | Arrt's catalogue | Free, instant |
| **Exists** | What did Dalí make, and who holds it? | Wikidata, Getty ULAN for the artist, catalogues raisonnés, the holding museum's accession number. Today Arrt asks a model instead (below) | Free and instant from a registry; under a cent from a model |
| **Seeable** | What does it look like? | A museum's preview image, Commons | Free and instant from a museum API; reached inside Ask or a run (inside a conversation until 2026-10-09) |
| **Hangable** | Can I get an image good enough for the wall? | Open-access museum APIs and Commons, or tile reassembly from a museum's viewer | A discovery run: minutes and money |

**Seeable is a separate layer because it is free, not because it is rarer.**
A museum's API returns preview images with its search results, at no cost and in
under a second, so "what does it look like?" never needs a run. Whether a work
is also Hangable depends on the **route** to it, and rights are a separate axis.

*Corrected 2026-10-01, the same day.* This paragraph first said a copyrighted
Rothko at the Art Institute is Seeable and not Hangable, because the image
service capped a whole-image request at 843 px (from a 4,840 px scan). The
owner pointed out that Rothkos had been found before. The library holds two,
both from the Art Institute by `dezoomify`: *Untitled (Purple, White, and Red)*
at 2,370 × 2,250 and *Untitled (Painting)* at 5,092 × 4,533. The cap applies to
asking for the whole image, and assembling it from zoom tiles gets past it.
**How common Seeable-but-not-Hangable is, is not measured.** The library's own
works show the route that matters:

- *Blue Half Circle* (Calder, 1970) came from the Art Institute's site and
  *Cat Litter* (Gober, 1989) from Google Arts & Culture. Both were acquired by
  `dezoomify`, which rebuilds an image from the viewer's tiles, and both have
  `rights_status = unknown`.
- `nonfunctional-requirements.md` § The Supply Horizon measured open-access
  supply stopping around 1929. These two works are past that line, and they came
  in through a different route from the one it measured.

### There is no ISRC for art

No identifier is assigned to every artwork the way ISRC is to recordings or ISBN
to books. **The nearest equivalent is Wikidata**, which is to art roughly what
MusicBrainz is to music. Lidarr, the *arr app for music, keys its library to
MusicBrainz IDs, so keying works to Wikidata QIDs is the *arr pattern and not an
invention (`re-architecture.md` § Open questions, "External identity").

Other identity sources:

- **Getty ULAN** for artists: it resolves "dali" to Salvador Dalí.
- **Getty CONA** for works: built for this purpose, but with thin coverage.
- **Catalogues raisonnés:** the scholarly per-artist list of everything an artist
  made, with one format per publication.
- **Museum accession numbers:** unique within one institution only.

**Measured 2026-10-01, Dalí on Wikidata** (creator `Q5577`, instance of painting
`Q3305213` or a subclass):

| | Count |
|---|---|
| Works | 1,072 |
| Naming a holding collection (`P195`) | 358 |
| Carrying a free image (`P18`) | 5 |

```sparql
SELECT (COUNT(DISTINCT ?w) AS ?works) (COUNT(DISTINCT ?img) AS ?withImage)
       (COUNT(DISTINCT ?coll) AS ?withCollection) WHERE {
  ?w wdt:P170 wd:Q5577 ; wdt:P31/wdt:P279* wd:Q3305213 .
  OPTIONAL { ?w wdt:P18 ?img } OPTIONAL { ?w wdt:P195 ?coll } }
```

*The Persistence of Memory* is `Q25729`, held by MoMA as `162.1934`. **That is one
artist, measured once.** A few of the 1,072 may be mis-typed, and coverage for the
library's other artists is not measured.

The finding is about layers: **existence is well registered past the public-domain
boundary, and images are what stop there.** A curator can be told everything that
exists, for free, and then shown which of it Arrt can actually get.

## Scenarios

Frequency is the builder's guess in every row:
`[ASSUMPTION: frequencies are inferred, not reported | HIGH impact, since frequency decides what search does by default | owner corrects]`.

| # | The curator wants to… | Starts from | Layer | Frequency (assumed) | Done when |
|---|---|---|---|---|---|
| S1 | Put a work they own on the wall now ("the Dalí, tonight") | Search, or Artworks | Held | Weekly | It is showing on the chosen wall |
| S2 | Check whether they already have a work, before adding it | Search | Held | Each time they add | They know yes or no, and a yes opens it |
| S3 | Get more by an artist than they have ("more Dalí") | Search, or a work's artist | Exists → Hangable | Monthly | New works by the artist are waiting for review |
| S4a | Find a specific work they have heard of: does it exist, who holds it? | Search | Exists, Seeable | Occasionally | They see the work, its holder, and whether it can be got |
| S4b | Get a copy of that work | S4a's result | Hangable | Occasionally | It is waiting for review, or they are told plainly why not |
| S5 | Find artists they could not have named ("who's like Dalí?") | Ask (Add New and a conversation until 2026-10-09) | Exists, Seeable → Hangable | Monthly | Works by them are waiting for review |
| S6 | Learn what is on the wall right now | Walls | Held | Weekly | They see the work and its label facts |
| S7 | Make a theme ("winter") and switch a wall to it | Artworks, Themes | Held | Seasonal | The wall is drawing from the theme |
| S8 | Take a work they are tired of out of rotation | The wall, or the work | Held | Monthly | It no longer comes up, and nothing else changed |
| S9 | Clean up: bad crops, low resolution, candidates never judged | Artworks, Activity | Held | Monthly | The library holds only what they would hang |
| S10 | Check everything is working | The status indicator, System | Held | Rarely, or when warned | They know whether anything needs them |
| S11 | Get acquainted with an artist they know only by name: what the work looks like, and which works could be had | Search | Exists, Seeable → Hangable | Monthly | They have seen the work, and have a list with thumbnails marking what can be hung (§ Tested: Rothko) |
| S12 | Spend a day or two outside their taste: a theme of works got into a destination other than *All works*, on every wall, then back to normal with nothing left behind (the word "excursion" retired 2026-10-02 for a Get's destination, `build-plan-topics-and-destinations.md` § The owner's rulings) | Add New, then Themes | Exists → Hangable → Held | A few times a year | The walls are back on what they showed before, and their taste and everyday library are as they were (§ Tested: the 16th century) |

### What the search box can mean

Typing `dali` can be S1, S2, S3 or S4a, and the box cannot tell which. Three of
the four are free. Only S3's acquisition and S4b cost money.

**How it behaves today, measured 2026-10-01** against the running server, whose
library holds one Dalí (*Untitled (Desert Landscape)*):

| Query | `GET /api/works?q=` | Top-bar dropdown |
|---|---|---|
| `dali` | 0 works | Only *Search museums for "dali"* |
| `Dalí` | 1 work | The Dalí, then *Search museums for "Dalí"* |
| `miro` / `Miró` | 0 / 1 | — |
| `rene` / `René` | 0 / 1 | — |

**Library search does not fold accents.** A curator who types the name as most
keyboards produce it is told they hold no Dalí, and the only offer is a paid
discovery run. That fails S1 and S2 outright, and it turns S2's "do I already have
it?" into a wrong answer. It is a defect against the built search, separate from
the IA question, and it is recorded here because this is where it was found.
*(Fixed 2026-10-01 by `build-plan-ia-foundations.md` Chunk 01: search now ignores
case, accents and ligatures on both sides, so each unaccented row in the table
above finds its work. The table stays as the measurement that found it.)*

Two things follow for the IA, and both are for the owner to rule on:

- **S4a has no home in search.** Arrt answers "exists" today in two places,
  both through a model: a conversation turn, from the model's own knowledge for
  well under a cent (`product-brief.md` flow 1), and phase 1 of a run, a call
  plus a few searches inside a run already committed to (flow 2). Neither is a
  lookup against a registry, neither says who holds a work, and neither is
  reachable from the search box. A registry lookup could answer S4a in the
  dropdown or on Add New at no cost, marking each result *In your library*,
  *Can be hung*, *Preview only* or *No image available*.
- ~~**Which meaning does Enter take?**~~ *Answered 2026-10-06 (the owner):*
  Enter opens the Search results page, grouped Held / Not held, which serves
  S3 and S4a as well as S1 and S2 (`build-plan-search-held-not-held.md`). It
  had opened Artworks filtered since 2026-09-30, a dead end for a work not held.

## Tested against three requests (2026-10-01)

The owner put three requests to this document. Each is traced through the
scenario table and through what is built, against the running server and the
code. What each one changed is listed with it.

### "I heard about Rothko and know nothing. I just type it in."

The curator wants to see what the work looks like, then a list with thumbnails
of the works that can be had.

**The table did not hold it.** S4a is one known work, and S5 starts from taste.
Getting acquainted with an artist known only by name is its own scenario, now
**S11**.

**Supply, measured.** Wikidata: Rothko (`Q160149`) has 349 works, 69 with a
holder, 0 with a free image. The Art Institute holds 8 (agent `36467`), each
with an image and none in the public domain. **The library already holds two of those 8**, both
assembled from tiles at hangable size (§ Four layers). He died in 1970, so
open-access supply has none of his work, and tile reassembly is the route that
reaches it. How many of the other 6, or of other museums' Rothkos, would come
through at hangable size is not measured.

**Today.** Typing `rothko` lists the library's two Rothkos, then *Search museums
for "rothko"*, which goes to Add New and a paid run. A run is the only path that
ends in a list with thumbnails of what can be had, and it ends in candidates,
not in a picture of what exists. The conversation would show sample pictures
(its samples come from the Art Institute, as the server's startup log says), but
search does not route there. So a curator who knows nothing about Rothko sees two
works they already hold, and then has to pay to see the rest.

**What it changed:** the layer model gained *Seeable* (§ Four layers), and S11 is
the case for a free lookup in search that shows the museums' previews, marks the
two already held, and leaves the paid run for acquiring.

*Corrected 2026-10-01, the same day.* The first version of this walkthrough said
`rothko` finds nothing in the library, and that Rothko is "Seeable and almost
never Hangable". Neither was measured: the first was assumed, and the second
read the Art Institute's whole-image cap as a ceiling on the work. The owner
caught it from memory of past runs.

### "A 16th-century theme for a day or two, then back to my normal taste."

The curator knows nothing about the period, wants a theme and representative
works on every wall, and above all wants to return to their usual, more modern
taste in a few days with nothing left behind.

**The table half held it.** S5 covers learning about the period, and S7 covers
making a theme and hanging it. Neither has an end. A time-boxed excursion is its
own scenario, now **S12**. "Nothing left behind" names three places an excursion
leaves traces, and the code was read for each:

| Trace | What is built today | Gap |
|---|---|---|
| **The walls** | Hanging is one act per wall: a *Hang on <wall>* button per wall on the Theme screen, and `POST /api/themes/{id}/activate` takes one `wall_id`. Nothing is timed. Taking a theme down leaves the wall showing it until another is hung. A wall holds one assignment row keyed by the wall, and hanging overwrites it, so what hung before is not remembered (`programming/store.py`, `set_assignment`). | No hang on every wall in one act, no end time, no return to what was hanging before. `re-architecture.md` § The manifest is a schedule (wave 4) is where a timed hanging would live. |
| **The library** | The works stay accepted, and show in Artworks and in any theme drawn from the whole library. Archiving takes a work out of circulation and Restore puts it back, but it is one work at a time, from the work's own page. | No archive for a selection or a theme. Archiving rather than deleting is right here: the run was paid for, and the next excursion can restore it. |
| **Taste** | Nothing is contaminated today, and only because taste is not read. Review writes no affinity: `observed` is in the enum and refused on every write path but review's, and review does not write it. No conversation or discovery code reads affinities; they are only listed (`GET /api/affinities`, its MCP twin) and detached when a conversation is deleted. | **When observed taste is built, an excursion will teach Arrt that the curator likes the 16th century.** Accepting thirty works is the strongest signal review can give. An excursion needs a way to say its acquisitions are not taste. |

Supply is no obstacle here: 16th-century work is long out of copyright and is the
easy case for Hangable.

**What it changed:** S12, and three requirements an excursion makes, listed in
the open questions for the owner to rule on rather than assumed. *(Recorded as
tested on 2026-10-01. The owner's rulings 5a and 8 answered the library half,
and on 2026-10-02 "excursion" became a **destination** on every Get: works got
into any theme other than *All works* stay out of the default. The taste half
is plan 4's. `build-plan-topics-and-destinations.md` § The owner's rulings.)*

### "I like Robert and Sonia Delaunay. Who's similar?"

**The table held it.** This is S5, and its path is built: Add New, conversation,
a commit card, a run. *(Since 2026-10-09 the path is Ask: a reply's artist
cards carry the reactions, and its work cards *Get this work*.)* The reactions on each sample ("more like this", "not
this") record taste as `stated`.

**Supply, measured** by each source's own identifier for the artist. Wikidata:
Robert Delaunay (`Q33978`, died 1941) has 225 works, 187 with a free image; Sonia
Delaunay (`Q232972`, died 1979) has 50, with 4. The Art Institute, by agent ID:
Robert has 5 works split across **two agent records** (`34225` and `54231`), 4
with an image and 1 public domain; Sonia, recorded as Sonia Delaunay-Terk
(`34226`), has 15, 13 with an image and none public domain. **The sources
disagree about the same artist**: most of Robert's work is free on Commons, and
almost none of it is marked free at the Art Institute. And one museum holds one
artist under two records, which is the identity problem of § There is no ISRC
for art inside a single source. So supply has to be asked per source and per
work, not per artist.

*Corrected 2026-10-01, the same day.* The first version gave the Art Institute
31 works by Robert and 37 by Sonia, about half public domain, and argued from it
that US law made Sonia's early work free there. Those counts came from a
free-text search that matches almost the whole collection (133,118 hits),
filtered on the surname alone, so they counted every Delaunay. The conclusion
went with them.

**Two gaps:**

- **Suggestions do not show supply.** A conversation can recommend an artist
  whose work cannot be hung, and the curator learns that only after paying for a
  run. Marking each suggestion with how much of the work is Hangable answers it
  at the point of choice.
- **The brief's promise is not built.** `product-brief.md` flow 1 says a later
  conversation "opens knowing that Kandinsky landed and Magritte did not", and
  `data-model.md` Q13 says the same. Nothing reads affinities (above), so a
  conversation about the Delaunays starts from nothing the curator has said
  before. No artifact recorded this as unbuilt until now.

## Open questions for the owner

1. Which scenarios are real, and how often does each happen? Add any that are
   missing.
2. When you type an artist's name, which of S1–S4a do you usually mean?
3. Should search show works Arrt can see but may not be able to hang (only a
   small image, or no image at all), or only what it can hang? S11 needs the
   pictures to answer "what does his work look like?", and hangability is not
   known until a run tries the route. How often a work is Seeable and not
   Hangable is not measured.
4. Should Arrt store a Wikidata QID on a work where one exists? That is
   `re-architecture.md`'s open "External identity" question, and S2 and S4a are
   the scenarios that would use it.
5. For S12, which of these does an excursion need? Hang a theme on every wall in
   one act. Give a hanging an end, after which each wall returns to what it
   showed before. Archive and restore a whole theme's works. Keep an excursion's
   acceptances out of taste.
6. Should a conversation's suggestions show how much of each artist's work can
   be hung, before the curator commits to a run?
