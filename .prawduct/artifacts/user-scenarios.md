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

## Three layers, not two

"Do I have it?" has a third answer between *yes* and *go get it*. Whether a work
**exists** is a different question from whether it **can be downloaded**, and the
two have different sources and costs.

| Layer | The curator's question | Source | Cost |
|---|---|---|---|
| **Held** | Is it in my library? | Arrt's catalogue | Free, instant |
| **Exists** | What did Dalí make, and who holds it? | Wikidata, Getty ULAN for the artist, catalogues raisonnés, the holding museum's accession number. Today Arrt asks a model instead (below) | Free and instant from a registry; under a cent from a model |
| **Downloadable** | Can I get an image good enough for the wall? | Open-access museum APIs and Commons, or tile reassembly from a museum's viewer | A discovery run: minutes and money |

**Downloadable has grades, not a yes or no**: no image, a small image, or a
full-resolution image. Rights are a separate axis. The library's own works show
both:

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
| S3 | Get more by an artist than they have ("more Dalí") | Search, or a work's artist | Exists → Downloadable | Monthly | New works by the artist are waiting for review |
| S4a | Find a specific work they have heard of: does it exist, who holds it? | Search | Exists | Occasionally | They see the work, its holder, and whether it can be got |
| S4b | Get a copy of that work | S4a's result | Downloadable | Occasionally | It is waiting for review, or they are told plainly why not |
| S5 | Find artists they could not have named ("who's like Dalí?") | Add New, conversation | Exists → Downloadable | Monthly | A direction is committed as a run |
| S6 | Learn what is on the wall right now | Walls | Held | Weekly | They see the work and its label facts |
| S7 | Make a theme ("winter") and switch a wall to it | Artworks, Themes | Held | Seasonal | The wall is drawing from the theme |
| S8 | Take a work they are tired of out of rotation | The wall, or the work | Held | Monthly | It no longer comes up, and nothing else changed |
| S9 | Clean up: bad crops, low resolution, candidates never judged | Artworks, Activity | Held | Monthly | The library holds only what they would hang |
| S10 | Check everything is working | The status indicator, System | Held | Rarely, or when warned | They know whether anything needs them |

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

Two things follow for the IA, and both are for the owner to rule on:

- **S4a has no home in search.** Arrt answers "exists" today in two places,
  both through a model: a conversation turn, from the model's own knowledge for
  well under a cent (`product-brief.md` flow 1), and phase 1 of a run, a call
  plus a few searches inside a run already committed to (flow 2). Neither is a
  lookup against a registry, neither says who holds a work, and neither is
  reachable from the search box. A registry lookup could answer S4a in the
  dropdown or on Add New at no cost, marking each result *In your library*,
  *Can be downloaded* or *Exists, no image available*.
- **Which meaning does Enter take?** Today Enter opens Artworks filtered to the
  query (ruled 2026-09-30), which serves S1 and S2. If S3 or S4a is the common
  case, that ruling should be revisited with this table in hand.

## Open questions for the owner

1. Which scenarios are real, and how often does each happen? Add any that are
   missing.
2. When you type an artist's name, which of S1–S4a do you usually mean?
3. Should Arrt show what *exists* but cannot be downloaded, or only what it can
   get? Showing it is honest about the supply horizon. Hiding it keeps the screen
   to things you can act on.
4. Should Arrt store a Wikidata QID on a work where one exists? That is
   `re-architecture.md`'s open "External identity" question, and S2 and S4a are
   the scenarios that would use it.
