# Procurement Corpus

Started 2026-10-03. A fixed list of works and artists the owner wants, used to
measure what procurement can get and what discovery can find, so that the next
source is chosen by what it would deliver rather than by guess.

**Why now.** `nonfunctional-requirements.md` § The Supply Horizon measured that the
wired sources resolve works from before about 1930 and almost nothing after, and
left open whether the contemporary-web half of procurement would be built. The
owner closed that on 2026-10-03: *"in-copyright count, users will add those and
it's not our place to limit them."* So it gets built, and this corpus decides
which source first.

**Who decided what.** The owner chose the anchors, ruled in-copyright works in,
and asked for up-and-coming artists. The structure, the bands, the failure list,
the choice of works per anchor and every prediction are mine (the agent's,
2026-10-03), and are open to challenge as such.

## The rules of the corpus

1. **Predictions are written before any run, and never edited after one.** A run's
   outcome goes in § Results under its date, beside the prediction it tests. A
   corpus whose predictions are fitted to its results measures nothing. The
   research that picked the works was told not to look at whether any image
   exists on Commons or the Art Institute, for the same reason.
2. **An entry is keyed by its Wikidata QID where one exists**, and otherwise by
   artist, title and date. A URL in an entry says where the work was *seen*; it is
   never the entry's identity (`data-model.md`: identity is never a source URL).
3. **Rights are recorded, never a reason to leave a work out** (the owner,
   2026-08-04 and 2026-10-03).
4. **The list is the owner's to strike.** A work they would not hang is removed,
   not kept for coverage; the coverage it carried goes to another work.

## Two parts

- **Part A — Procurement.** Specific works by the anchors. Measures: given a work
  someone named, can the system get an image of it fit for the wall? Mostly
  reachable through *Get*, which starts from a QID and spends nothing.
- **Part B — Discovery.** The anchors as examples of taste, and a held-out list of
  artists the system is never shown. Measures: asked for "more like these", does
  discovery surface artists the owner would want? Lidarr's *similar artists*;
  `re-architecture.md` plan 4 (Ask reading taste).

A later **Part C** will hold a few artists to *follow*, re-checked over weeks, to
test Watches (`re-architecture.md` § Procurement) once they exist. Nothing is in
it yet.

## Bands

By rights status rather than decade, because rights is what the Supply Horizon
measured as the partition. US public domain covers works published before 1931
as of 2026, and the boundary moves a year each 1 January; EU is the author's life
plus 70 years.

A band belongs to the *work*, not the artist: Robert Delaunay's 1912 *Windows* and
his 1938 *Rythme* sit in different bands.

| Band | Meaning | Anchors with works in it |
|---|---|---|
| **open** | Public domain in the US and in the EU | Robert Delaunay, Exter, Taeuber-Arp |
| **us-open** | Public domain in the US only: published before 1931, artist died after 1955 | Sonia Delaunay, Escher, Dalí |
| **eu-open** | Public domain in the EU only: artist died before 1956, work published after 1930 and restored in the US | Robert Delaunay, Exter, Taeuber-Arp |
| **estate** | In copyright everywhere, artist dead; an estate or foundation holds the rights | Sonia Delaunay, Escher, Dalí, Sage, Calder, Rauschenberg, Warhol, Lichtenstein, Twombly, Kelly, Martin |
| **living** | Living and established, held by museums | Richter, Kiefer, Banksy |
| **gallery** | Living, represented by commercial galleries, no museum or registry presence | Peter Stephens |
| **emerging** | Living, early career, recent attention | Lucy Bull |

**The US verdicts after 1930 are the researchers' reading of the law, not checked
work by work.** They assume restoration under the URAA for foreign works, leave
the notice-and-renewal question open for American ones (Sage, Calder), and treat
"published" as unsettled for a unique painting. One verdict moves soon: Dalí's
*Persistence of Memory* (1931) enters the US public domain on 2027-01-01.

## What can go wrong

Each entry names the failures it is expected to meet. The failures are separate
because they have separate fixes; "hard to get" is not one thing.

| Failure | Meaning | Whose fix |
|---|---|---|
| **identity** | No registry item, or the item is ambiguous (many *Untitled*, shared names) | the identity matcher; the catalogue's own identity |
| **no image** | No source holds any image | a new source |
| **resolution** | Images exist, but below the floor (below) | a better source; an upgrade later |
| **fidelity** | The image is not of the work alone: a photograph of a wall, with perspective, context, glare | review; possibly a crop |
| **shape** | Not a flat object: a mobile, a Combine, a material-heavy surface | a flat route (a gouache, a print) or nothing |
| **edition** | One of many impressions or a member of a series; which one is the work? | the data model (§ Gaps) |
| **attribution** | More than one artist | the data model (§ Gaps) |
| **holder** | The holding institution has no open API or online collection | a source, or nothing |

**Resolution, precisely.** Nothing is ever upscaled (`project-state.yaml`, the mat
geometry decision of 2026-07-20); an image smaller than its box renders smaller,
inside a wider mat. The floor is a rendered size, 12 inches on the long edge by
default (`RESOLUTION_FLOOR_INCHES`), which on the owner's 50-inch panel (about 88
pixels per inch across 3840) is about 1,060 pixels. Each entry also carries a
**tolerance**: whether a small image still reads as the work. A flat-colour Kelly
does (*tolerant*); Agnes Martin's pencil grids, Twombly's graphite and
Lichtenstein's Ben-Day dots do not (*critical*), because a small image of a large
canvas has already discarded what the work is made of.

## Sources a prediction may name

The predictions below say which source would get each work. Today's pool is the
Art Institute and Commons (`library/discovery/pool.py`); the rest are candidates,
and nothing here has been measured unless it says so.

| Source | Expected strength | Expected weakness |
|---|---|---|
| **pool** (Art Institute, Commons) | Large open images, structured metadata | Stops at the rights boundary (measured) |
| **us-museum** (the Met, NGA, Cleveland open access) | Judge public domain by US law alone, where Commons generally also needs the work's home country | Hold few of these works; measured empty past 1930 |
| **foundation** (artist foundation or online catalogue raisonné) | Authoritative identity for one artist's whole work | One site per artist; image policies vary |
| **auction** (Christie's, Sotheby's, Phillips) | Well catalogued; often large images; strong 1950–2000 | Only what has sold |
| **gallery** (commercial gallery sites) | The only route to many living artists | No shared structure, except a platform (below) |
| **museum-page** (museum sites showing in-copyright work) | Authoritative | Deliberately small images |
| **tiles** (Google Arts & Culture, via dezoomify) | High resolution | Uneven coverage of in-copyright work |
| **photo** (news, photo libraries) | The only image of most street work | Fidelity; no structure |

**Artlogic, measured 2026-10-03 on two pages.** Both of Peter Stephens's galleries
(Markel Fine Arts, Nüart) run on Artlogic ("Site by Artlogic" in the footer), and
the work image comes from `static-assets.artlogic.net` with its size in the URL
(`w_2400,h_2400,c_limit`), served at 2400 × 2400. If that holds widely, one scraper
reaches every gallery on the platform.

**How widely, measured 2026-10-03 across the 18 gallery sites Part B's research
visited:** 7 carry Artlogic's credit; 5 more run on exhibit-E, which Artlogic
merged with in 2022, and serve their images from the same asset host under a
different page template; 6 are something else (Squarespace, WordPress twice,
ManagedArtwork, hand-written HTML, a custom build). So 12 of 18 share an image host
and 7 of 18 share a template. The sample leans towards Artlogic, because it
started from Stephens's own two galleries. Whether one scraper reads both
templates is untested.

**What the platform served, measured on Stephens's and Bull's pages:**

- **Sizes:** 2,400 to 3,600 pixels on the long edge, all above the floor.
- **Format:** WebP behind a URL ending `.jpg` (`f_auto`).
- **Cap:** a per-gallery size cap in the URL (Markel's pages ask for up to 4,000, Nüart's for 2,400).

The acquisition path's handling of WebP from a gallery is unchecked.

## Part A — Procurement

59 works, 2–3 per anchor, researched 2026-10-03. The researchers checked every
QID against the item's type, creator, collection, date and materials. They were
told not to look at any image on Commons, the Art Institute or a museum's open
access, and did not. The one exception is the six gallery works (Bull, Stephens),
whose pages they had to read to find the works at all; those rows say *measured*,
not *predicted*.

The researchers' notes, with every source, the per-artist rights policies quoted
with their URLs, and the Wikidata errors found, are in
`procurement-corpus-research/`. Their row numbers match this table: rows 1–26 are
`part-a-early-and-estate.md` 1–26, and rows 27–59 are
`part-a-pop-abstract-living.md` 1–33.

### How the predictions were made

Each is derived from one of these rules, so a wrong prediction says which rule
was wrong:

- **R1, Commons.** The pool asks Commons only for the image the item itself names
  (P18), never by title (`library/discovery/commons.py`). I predict an item has
  that image when the work is free in the US *and* in its home country, which
  Commons generally requires. The exception: works free at home and restored in
  the US (eu-open) usually stay on Commons too. For 3D works and for items created
  recently, I lower the confidence.
- **R2, the Art Institute.** It searches by title alone and holds only its own
  collection; the 843-pixel preview is the only size it serves directly
  (`artic-api-findings.md`). I predict it finds a work only when it holds that work
  or, for editions, another impression of it. For a work in copyright I predict
  *small*, at low confidence.
- **R3, Get's identity.** Get accepts any item the registry returns. It checks
  neither the item's type nor whether it has a creator
  (`library/services/get.py`, `registry/wikidata.py`). An item with no creator
  reaches the Art Institute with no artist to check a title match against.
- **R4, no QID.** A work with no item cannot be got. It reaches the pool only
  through Ask, which spends money, and only the Art Institute can answer it.

Outcome words: **found** (at or above the floor), **small** (found, below it),
**none**, **wrong-risk** (a sibling or another work could be attached).

### The works

Columns:

- **Fails**: the failures from § What can go wrong that each work is expected to meet.
- **Tol**: resolution tolerance, t / m / c for tolerant, moderate, critical.
- **Pool today**: the prediction for the wired sources.
- **Would come from**: the source I predict would get it, if any.

| # | Artist | Work | QID | Band | Fails | Tol | Pool today | Would come from |
|---|---|---|---|---|---|---|---|---|
| 1 | R. Delaunay | *Windows Open Simultaneously (1st part, 2nd motif)*, 1912; Hamburger Kunsthalle | Q19861807 | open | identity: about 12 sibling *Windows* items | m | found (R1) | pool |
| 2 | R. Delaunay | *Homage to Blériot*, 1914; Kunstmuseum Basel | Q19861802 | open | identity: two same-title siblings; square | t | found (R1) | pool |
| 3 | R. Delaunay | *Rythme n°1*, Salon des Tuileries panel, 1938; MAM Paris | Q18927491 | eu-open | Wikidata says "public domain", true only in the EU | t | found, low confidence (R1) | pool |
| 4 | S. Delaunay | *Prismes électriques*, 1914; Centre Pompidou | Q60144838 | us-open | no image | t | none (R1) | museum-page, tiles |
| 5 | S. Delaunay | *Couverture* (cradle blanket), 1911; Centre Pompidou | none | us-open | identity; shape: textile | m | none (R4) | museum-page |
| 6 | S. Delaunay | *Rythme couleur n°1076*, 1939; Lille, on deposit from the state | Q116464677 | estate | holder: a French regional museum | t | none | museum-page |
| 7 | S. Delaunay | *Rythme*, Salon des Tuileries panel, 1938; MAM Paris | Q104423957 | estate | attribution: nearest to a joint work (companion to #3) | t | none | museum-page |
| 8 | S. Delaunay with Cendrars | *La Prose du Transsibérien*, 1913; the Met's copy | Q126119699 | us-open | edition (about 60 copies); shape: 1 : 5.5 strip; three kinds of item | c | none (R1); the Art Institute holding a copy is unknown (R2) | us-museum |
| 9 | Exter | *City at Night*, 1913; State Russian Museum | Q124646012 | open | holder: no open API reaches it | m | found, medium confidence: Commons holds what the museum does not serve (R1) | pool |
| 10 | Exter | *Spanish Dancer* (marionette), 1926; Staatsgalerie Stuttgart | Q129176446 | open | shape: 3D | m | none, low confidence (R1, 3D) | museum-page |
| 11 | Exter | *Panorama de la côte*, 1938; IVAM's copy | Q106713772 | eu-open | edition; shape: folding strip | t | none (R1, obscure item) | auction |
| 12 | Taeuber-Arp | *Tête Dada*, 1920; Centre Pompidou | Q138581656 | open | shape: 3D; identity: a Zürich sibling; Wikidata gives its height as 2943 cm | m | none, low confidence (R1, recent item, 3D) | museum-page |
| 13 | Taeuber-Arp | *Composition of Circles and Overlapping Angles*, 1930; MoMA | Q19884054 | open | Wikidata says both public domain and copyrighted | t | found, medium confidence (R1) | pool |
| 14 | Taeuber-Arp | *Échelonnement*, 1934; Musée de Grenoble | Q136030970 | eu-open | identity: no English label | t | none, low confidence (R1, recent item) | museum-page |
| 15 | Escher | *Castrovalva*, 1930 | Q2899660 (work); NGA impression Q65574099 | us-open | edition; the item mixes work and impression; the Escher Company forbids all reproduction | c | none (R1) | us-museum (NGA) |
| 16 | Escher | *Metamorphosis II*, 1939–40 | Q9032006; NGA Q65511117 | estate | edition; shape: about 1 : 20 | c | none | museum-page |
| 17 | Escher | *Relativity*, 1953 | Q2635136; NGA Q65574317 | estate | edition | c | none | museum-page |
| 18 | Sage | *Tomorrow is Never*, 1955; the Met | Q19917650 | estate | no image | m | none | museum-page |
| 19 | Sage | *In the Third Sleep*, 1944; Art Institute of Chicago | Q20268302 | estate | the one holder the pool asks | m | small, low confidence (R2) | pool |
| 20 | Sage | *No Passing*, 1954; Whitney | Q64514800 | estate | holder: no open API | m | none | museum-page |
| 21 | Dalí | *Young Woman at a Window*, 1925; Reina Sofía | Q153552 | us-open | no image | t | none (R1) | tiles |
| 22 | Dalí | *The Persistence of Memory*, 1931; MoMA | Q25729 | estate until 2027-01-01, then us-open | the boundary moves under it | m | none, before and after 2027-01-01 (R1: Spain) | museum-page |
| 23 | Dalí (with Edward James) | *Lobster Telephone*, 1936 | Q2990594 | estate | shape: 3D; edition: one item for about 11 copies; attribution | t | none | museum-page |
| 24 | Calder | *Cirque Calder*, 1926–31; Whitney | Q2974254 | estate (straddles 1931) | shape: an installation of about 70 figures | m | none | photo |
| 25 | Calder | *Lobster Trap and Fish Tail*, 1939; MoMA | Q6663853 | estate | shape: kinetic | m | none | museum-page |
| 26 | Calder | *Across the Orange Moons*, 1967 (gouache); Smithsonian American Art Museum | Q20486268 | estate | Calder's flat route | t | none | museum-page |
| 27 | Rauschenberg | *Monogram*, 1955–59; Moderna Museet | Q6901603 | estate | shape: free-standing; the item is typed as a lettering monogram | m | none; the Get starts anyway (R3) | foundation |
| 28 | Rauschenberg | *Bed*, 1955; MoMA | Q19887269 | estate | shape: relief with real textiles; 2.4 : 1 portrait | m | none | foundation |
| 29 | Rauschenberg | *Erased de Kooning Drawing*, 1953; SFMOMA | Q17143206 | estate | fidelity: the frame and label are part of the work; near-blank | c | none | foundation |
| 30 | Warhol | *Shot Sage Blue Marilyn*, 1964; private | Q111956958 | estate | series: one of five near-identical *Shot Marilyns* | m | none | auction |
| 31 | Warhol | *Campbell's Soup Cans*, 1962; MoMA | Q2697937 | estate | series: one item for 32 canvases | t | none | museum-page |
| 32 | Warhol | *Marilyn Monroe (Marilyn)*, 1967, a portfolio sheet; the Met's impression | Q98843233 | estate | edition: 10 colourways, edition of 250 | m | none; an Art Institute impression is unknown (R2) | auction |
| 33 | Lichtenstein | *Whaam!*, 1963; Tate | Q3567592 | estate | Ben-Day moiré; 2.35 : 1 diptych; dimensions wrong on Wikidata | c | none | museum-page |
| 34 | Lichtenstein | *Drowning Girl*, 1963; MoMA | Q5308687 | estate | Ben-Day moiré | c | none | museum-page |
| 35 | Lichtenstein | *Crak!*, 1963–64 (offset lithograph) | Q16155640; NGA Q75119355 | estate | edition: size disputed; work vs impression items | c | none; an Art Institute impression is unknown (R2) | auction |
| 36 | Twombly | *Leda and the Swan*, 1962; MoMA | Q19887609 | estate | graphite in paint | c | none | museum-page |
| 37 | Twombly | *Untitled (New York City)*, 1968; Museum Brandhorst | Q30085443 | estate | identity: German label only, near-identical siblings | c | none | museum-page |
| 38 | Twombly | *Fifty Days at Iliam*, 1978; Philadelphia | none | estate | series: a ten-part room; identity | c | none (R4) | museum-page |
| 39 | Kelly | *Blue Green Red*, 1963; the Met | Q20189992 | estate | identity: same title at the Whitney and elsewhere | t | none | museum-page |
| 40 | Kelly | *Colors for a Large Wall*, 1951; MoMA | Q19887001 | estate | 64 panels; square | t | none | museum-page |
| 41 | Kelly | *Austin*, 2015–18; Blanton Museum | Q22073172 | estate | shape: a building; no creator on Wikidata | — | none, and a wrong-risk: no artist to check a title match (R3) | photo |
| 42 | Agnes Martin | *Friendship*, 1963; MoMA | Q19887636 | estate | fidelity: incised gold leaf, the lighting is the content | c | none | museum-page |
| 43 | Agnes Martin | *The Tree*, 1964; MoMA | Q19887701 | estate | identity: a different *The Tree*, 1965, in Buffalo | c | none | museum-page |
| 44 | Agnes Martin | *On a Clear Day*, sheet I of 30, 1973; NGA | Q74034248 | estate | edition and series; no creator on Wikidata | c | none, and a wrong-risk (R3) | auction |
| 45 | Richter | *Abstract Painting (809-3)*, 1994; ARTIST ROOMS, Tate | Q18542994 | living | series: 809-1 to 809-4 | c | none | museum-page (the artist's site is offline) |
| 46 | Richter | *256 Farben*, 1974/1984; SFMOMA | Q50323239 | living | series: several colour charts by count; 1.86 : 1 | t | none | museum-page |
| 47 | Richter | *Betty*, 1988; Saint Louis Art Museum | Q78640464 | living | identity: the *Betty* prints | m | none | museum-page |
| 48 | Kiefer | *Margarethe*, 1981; SFMOMA | Q50321310 | living | shape: straw relief; fidelity: raking light | m | none | museum-page |
| 49 | Kiefer | *Sulamith*, 1983; SFMOMA | Q50315793 | living | fidelity: very dark, where the mat floor and the panel's blacks meet | m | none | museum-page |
| 50 | Kiefer | *Breaking of the Vessels*, 1990; Saint Louis Art Museum | none | living | shape: lead and glass installation; identity | — | none (R4) | photo |
| 51 | Banksy | *The Mild Mild West*, 1999; a wall in Stokes Croft, Bristol | Q22330073 | living | fidelity: a photograph of a wall; UK freedom of panorama excludes murals | m | none, medium confidence (R1) | photo |
| 52 | Banksy | *Devolved Parliament*, 2009; private | Q69662656 | living | no image | m | none | auction |
| 53 | Banksy | *Love is in the Bin*, 2006/2018; private | Q56886750 | living | shape: half-shredded; identity: canvas, print and mural share the title | m | none | auction |
| 54 | Lucy Bull | *3:13*, 2023 | none | emerging | shape: 3.6 : 1 diptych | m | none (R4) | gallery: measured 3200 × 1111, probably with surround |
| 55 | Lucy Bull | *The Bottoms*, 2021 | none | emerging | identity | m | none (R4) | gallery: measured 3600 × 2747 |
| 56 | Lucy Bull | *13:13*, 2024; ICA Miami stairwell commission | none | emerging | fidelity: only an installation view exists; 8.7 : 1 | c | none (R4) | gallery: measured 1200 × 1800, an installation view |
| 57 | Peter Stephens | *Mambo Jumbo*, 2023 | none | gallery | identity only | t | none (R4) | gallery: measured 2885 × 3173 |
| 58 | Peter Stephens | *Quadrivium 77*, 2024 | none | gallery | series; three images on its page, which is the work? | t | none (R4) | gallery: measured 3024 × 3024 |
| 59 | Peter Stephens | *Big Top*, undated, sold | none | gallery | no date; the gallery's 2400-pixel cap | t | none (R4) | gallery: measured 2400 × 2399 |

**What the predictions add up to.** Today's pool is predicted to deliver **5 of
59** (rows 1, 2, 3, 9 and 13), plus 1 small (row 19), with three Art Institute
impressions unknown. That is **every one of the predicted finds in the open or
eu-open band, and nothing past it**, which is the Supply Horizon restated per
work. The interesting predictions are in the last column:

| Would come from | Rows |
|---|---|
| museum-page | 30 |
| auction | 7 |
| pool | 6 |
| gallery | 6 |
| photo | 4 |
| foundation | 3 |
| us-museum | 2 |
| tiles | 1, and second choice for row 4 |

Counted from the table's first-named source; 9 rows have no QID, so a Get cannot
reach them.

Museum-page dominates, and it is the source predicted to serve images too small
for the wall. That raised a question for the owner before any run: is an
800-pixel museum image of a work you love worth having on the wall, smaller, in a
wider mat?

**The owner, 2026-10-03: yes, "because it's a placeholder for getting better
versions".** So a small image is worth getting, and it is the start of a work's
life in the library, not the end. This makes upgrade monitoring
(`re-architecture.md`: the quality profile and its upgrade cutoff, Radarr's
pattern) load-bearing rather than optional, because it is what turns the
placeholder into the keeper.

**"Museum-page" is not one source.** Its 30 rows name about 15 holders, one
site each. MoMA alone holds 8 of them (rows 22, 25, 31, 34, 36, 40, 42, 43), then
the Centre Pompidou and SFMOMA with 3 each. So the first museum to measure by
hand is MoMA, and any build is per museum, largest holder first.

## Part B — Discovery

The anchors are what discovery is shown. Below is what it must find without being
shown it: artists a knowledgeable curator would predict the owner likes, researched
2026-10-03 (every artist QID checked, every gallery page fetched).

**The held-out rule.** No artist in the two tables below may be named by the
server, in a prompt, a few-shot example, a default or a tool description, or have
a work in the library. A held-out artist the system has been shown measures
memory, not discovery, and the run still looks fine.

`tests/preferences/test_held_out_artists.py` enforces part of this. It reads the
names from these tables and fails if any full name, or any surname distinctive
enough to search alone, appears in a text file under `arrt/src`, or if any name
is an artist in the 2024 library seed (`all.json`). It cannot see the live
library, which grows with every acceptance. **An artist accepted into the library
must come off this list by hand**, and before each Part B run the list is checked
against the live library.

**What a run is scored on:** of the artists it proposes, how many are on this list
(recall against a list it never saw), and of the rest, how many the owner would
keep (precision, by the owner's verdict). The list is a floor, not the whole
answer: a good proposal that is not on it is a success the owner scores, not a
miss.

### B1 — established (20)

| Artist | Dates | Near | Why | QID |
|---|---|---|---|---|
| František Kupka | 1871–1957 | the Delaunays | named with them as Orphism's founders | Q167414 |
| Hilma af Klint | 1862–1944 | the Delaunays, Taeuber-Arp | geometric colour abstraction before Orphism | Q436267 |
| Natalia Goncharova | 1881–1962 | S. Delaunay, Exter | Rayonism; painting into textile and stage | Q232391 |
| Lyubov Popova | 1889–1924 | Exter | showed with her in *5×5=25*, 1921 | Q259594 |
| Naum Gabo | 1890–1977 | Calder, Exter | an early kinetic construction, 1920 | Q309482 |
| Yves Tanguy | 1900–1955 | Sage, Dalí | Sage's husband; the same dreamscape idiom | Q164720 |
| Bridget Riley | b. 1931 | Kelly, Escher, Stephens | optical rhythm from flat colour | Q234449 |
| Richard Hamilton | 1922–2011 | Warhol, Lichtenstein | British Pop's founding collagist | Q159465 |
| Sigmar Polke | 1941–2010 | Richter, Warhol | Capitalist Realism with Richter, 1963; raster dots | Q376062 |
| Georg Baselitz | 1938–2026 | Kiefer, Richter | post-war German painting and history | Q164775 |
| Carmen Herrera | 1915–2022 | Kelly | Paris-period hard edge, compared with Kelly's | Q522662 |
| Robert Ryman | 1930–2019 | Agnes Martin | near-monochrome, surface and light | Q640936 |
| Sean Scully | b. 1945 | Agnes Martin, Kelly | stripes and blocks of muted colour | Q535343 |
| Joan Mitchell | 1925–1992 | Twombly, Bull | large lyrical gesture | Q469934 |
| Jean Tinguely | 1925–1991 | Calder | witty motorised machines | Q163938 |
| George Rickey | 1907–2002 | Calder | wind-driven kinetic steel | Q632656 |
| Keith Haring | 1958–1990 | Banksy, Warhol | from the subway to Pop | Q485635 |
| Jean-Michel Basquiat | 1960–1988 | Banksy, Twombly, Warhol | SAMO© text, Warhol collaborations | Q155407 |
| Jenny Holzer | b. 1950 | Banksy | text in public space | Q270388 |
| Barbara Kruger | b. 1945 | Banksy, Warhol | slogans over appropriated photographs | Q262284 |

Held in reserve: Shepard Fairey.

**Magritte, Jasper Johns and Vasarely were on this list and came off it** the day
it was written: the 2024 library already holds a work by each, so discovery is
shown them. The research was briefed with the anchors and not the library, and
the test below is what caught it. (Magritte was doubly wrong: "meh on Magritte" is
the owner's own recorded example of lukewarm taste, `data-model.md`.) Hilma af
Klint, Sean Scully and Barbara Kruger came in from the reserve, their QIDs
checked the same day.

### B2 — living, gallery-represented and emerging (14)

Attention claims are sourced, with dates, in `procurement-corpus-research/part-b-held-out.md`. The *Platform*
column feeds § Sources.

| Artist | Born | Like | Why | Gallery platform | QID |
|---|---|---|---|---|---|
| Debra Smith | 1971 | Stephens, Taeuber-Arp | geometry pieced from silk linings | Artlogic | none |
| Susan Dory | 1964 | Stephens, S. Delaunay | layered translucent geometric patchworks | Artlogic | none |
| Paolo Arao | 1977 | Taeuber-Arp, S. Delaunay | sewn geometric textile paintings | Artlogic | Q110781487 |
| Leslie Roberts | 1957 | Stephens, Martin | text coded into colour on pencilled grids | Squarespace | none |
| Mokha Laget | 1959 | Kelly | hard edge on shaped canvas | exhibit-E | Q19802467 |
| Nate Ethier | 1977 | Escher, S. Delaunay | modular symmetry, optical alternation | ManagedArtwork | none |
| Gary Petersen | 1956 | S. Delaunay, Kelly | bright curving geometric arcs | hand-written | none |
| Emma Webster | 1989 | Sage, Dalí | uncanny landscapes built in VR, then painted | custom; exhibit-E | Q113099236 |
| Tomashi Jackson | 1980 | the Delaunays | colour theory, halftone, geometric abstraction | exhibit-E | Q29527424 |
| Jadé Fadojutimi | 1993 | Twombly, Bull | large lyrical gesture | Artlogic | Q57628796 |
| Grant Levy-Lucero | 1981 | Warhol, Lichtenstein | ceramic reclamations of brand logos | exhibit-E | none |
| Jammie Holmes | 1984 | Banksy | aerial banners of George Floyd's last words, 2020 | WordPress; Artlogic | Q107663687 |
| Vhils (Alexandre Farto) | 1987 | Banksy | portraits carved into walls | WordPress | Q115823 |
| Felipe Pantone | 1986 | Calder, Delaunay | kinetic art, graffiti, digital colour | Artlogic | Q58494412 |

Doubtful fits, for the owner to judge: Fadojutimi is probably past "emerging" (a
$2M auction result, and Gagosian); Levy-Lucero and Pantone have gallery attention
only; Ethier's and Petersen's nearness was inferred from gallery text, with no
images viewed. **The rows go stale fastest of anything here**, and should be
re-researched before each Part B run rather than trusted. Lucy Bull's own
representation moved during the research: Hauser & Wirth announced worldwide
representation alongside Kordansky around Art Basel Paris 2026 (date unconfirmed:
the source is paywalled).

## The owner's rulings, 2026-10-03

1. **Small images are worth getting, as placeholders for better versions** (above).
2. **Every work stays.** The owner would hang all 59, so none is struck.
3. **The first Get runs on the NAS**, so its finds land in the real To review and
   the corpus is also the owner's wishlist.
4. **The gaps below are mine to rule on.** The owner asked; the rulings are mine
   (the agent's), each marked, and each the owner's to overturn.
5. **The held-out rule is enforced by a test** (§ Part B).

## Gaps the corpus exposes

These are findings about the product, not predictions. Each carries my ruling.

1. **One artist per work.** `artwork.artist_id` is a single nullable key
   (`data-model.md`), so a joint work cannot carry both artists. The anchors
   suggested the Delaunays would test this, but **no work attributed to both
   exists on Wikidata** (searched 2026-10-03). The real cases are an artist with
   someone else: Sonia with the poet Cendrars (row 8), Dalí with Edward James
   (row 23). The gap is real and narrow.
   *My ruling: no change.* The first-named artist is the work's artist, and the
   collaborator is named in the work's own text. Revisit when finding or browsing
   by the second artist is something the owner asks for.
2. **Work, impression and series are three things; the model knows two.** Prints
   exist as many impressions (rows 8, 15–17, 32, 35, 44). One item can stand for
   32 canvases (row 31) or about 11 copies (row 23). Wikidata itself mixes work and
   impression items for Escher. The data model separates a work from an image of
   it, and has no layer for which impression.
   *My ruling: no new layer.* A QID for one impression names the work, and the
   source the image came from records which impression it was. Revisit if two
   impressions of one work both reach the library.
3. **Get trusts any item.** It checks neither the item's type nor its creator
   (§ R3). Rows 27, 41 and 44 test what follows.
   *My ruling: fix it if the first Get shows the harm, not before.* Fixing it
   first would void the prediction meant to measure it. If a row with no creator
   gets an image by title alone, it goes to the backlog as a defect: a work with no
   known artist is never matched by title.
4. **Wikidata is wrong more often than its shape suggests:**
   - Swapped or wrong dimensions (rows 12, 33, 52).
   - Contradictory rights (row 13).
   - Missing creators (rows 41, 44).
   - A German-only label (row 37).
   - Wrong dates (row 46).

   Anything that reads a size or a date from the registry, for example to place
   a work on the wall at its true scale, inherits these.

   *My ruling: no change now.* Nothing in the server reads a work's dimensions from
   Wikidata (searched 2026-10-03). Whatever first does must check them for
   plausibility before relying on them, and must state so.
5. **Sources vanish.** gerhard-richter.com has been offline since about January
   2026 after a security breach (reported 2026-04-29; still down 2026-10-03). A
   foundation or gallery source needs a "this source is gone" state that is not
   "this work has no image".
   *My ruling: this binds every new source.* The pool already separates the two
   (`ImageSearchFailure`, `library/discovery/images.py`). The trap a scraper adds
   is the one this site shows: it answers HTTP 200 with a page saying "This site is
   unavailable". So a scraper must recognise a page that is not the page it
   expects and raise the failure, never read it as an empty answer.
6. **The flat route needs a rule.** For a mobile, a Combine or an installation,
   either a flat work stands in (Calder's gouache, row 26), an installation view
   is accepted as the image (rows 50, 56), or nothing is. Today nothing decides.
   *My ruling:* a photograph or installation view of the work *is* the work's image,
   judged at review like any other. Another work is never attached in its place:
   the gouache is got as itself. This follows the existing rule that an offered
   work is never presented as the work named (`project-state.yaml` § integrations,
   2026-08-04).
7. **Extreme shapes.** *Metamorphosis II* at about 1 : 20 and *13:13* at 8.7 : 1
   will be a thin line on a 16:9 wall. This is a display question, recorded here
   because the corpus is what found it.
   *My ruling: no action until one is on a wall and the owner has looked.* The mat
   already places a work by its shape. A crop or a detail would be a different
   image, and choosing one is the owner's call.

## Running it

**Part A, step 1: the 50 rows with a QID, through one Get. It spends nothing.**
`POST /api/gets` with the QIDs, or the MCP `get` action. Record each row's outcome
in § Results: which source answered, at what size, or which `unresolved_reason`.
Run it twice, once before and once after 2027-01-01, to test row 22.

It runs on the NAS (the owner, 2026-10-03), so its finds land in the real To
review.

**Step 2: the 9 rows without a QID.** These reach only the Art Institute, through
Ask, which spends. Predicted none for all nine. It is worth one cheap run to
confirm R4, not more.

**Step 3: probe each candidate source by hand, before building any of them.**
For every row the last column assigns to a source, look at what that source
serves: whether it has the work, at what size, under what terms. That turns each
"would come from" into a measurement. The ranking of what to build first falls
out of those numbers, weighed against the owner's answer on small images
(§ What the predictions add up to).

**Part B** runs when Ask can be given examples (`re-architecture.md`, plan 4).
Before then, an Ask whose intent names the anchors approximates it, and spends.

## Results

### Run 1 — Part A step 1, the first Get (2026-10-03)

Run `a41ecc1b`, on the NAS, against the predictions as committed in `4134e9c`:

- 50 QIDs chosen, none skipped (no item held, being got, or missing from the registry).
- Finished in 20 seconds; spent $0.
- **11 found, 2 below the floor, 37 not.**
  - Of the 37: 34 were not held by any source.
  - The other 3 were refused on identity.
- **40 of the 50 predictions were right.**
  - 36 of the 44 "none" predictions held.
  - 4 of the 5 "found" held.
  - The one "small" did not.

| # | Work | Predicted | Outcome |
|---|---|---|---|
| 1 | *Windows* | found | **found**, Commons, 3168 × 3564, a reproduction |
| 2 | *Homage to Blériot* | found | **found**, Commons, 3840 × 3805 |
| 3 | *Rythme n°1* | found | **found**, Commons, 2985 × 2715 |
| 9 | *City at Night* | found | **found**, Commons, 952 × 1200, matted small |
| 12 | *Tête Dada* | none | **found**, Commons, 1044 × 2180: a photograph of the object in the museum, CC BY |
| 13 | *Composition of Circles…* | found | **none**: the item names no Commons image |
| 19 | *In the Third Sleep* | small | **found**, Art Institute, 8786 × 5798, in copyright |
| 23 | *Lobster Telephone* | none | **found**, Commons, 1280 × 929: a photographer's own photograph, CC BY |
| 24 | *Cirque Calder* | none | **below floor**, Commons, 400 × 400: a 1951 photograph of Calder with the circus |
| 31 | *Campbell's Soup Cans* | none | **found**, Commons, 2604 × 1514: the 32 canvases photographed on MoMA's wall |
| 33 | *Whaam!* | none | **found, and wrong**: Commons, 3648 × 2406, a 1967 photograph of Lichtenstein in front of "one of his paintings" at the Stedelijk |
| 34 | *Drowning Girl* | none | **below floor**, Commons, 140 × 63, a crop of the speech balloon |
| 35 | *Crak!* | none (impression unknown) | **found**, Art Institute's impression, 11073 × 7794, in copyright |
| 41 | *Austin* | none, wrong-risk | **found**, Commons, 3200 × 1800: the building, photographed |
| 10, 27, 36 | *Spanish Dancer*, *Monogram*, *Leda and the Swan* | none | **refused on identity**: a title match naming another artist was turned away |

Every other row: none, as predicted.

**What the misses say about each rule:**

- **R1 was wrong in one specific way.** Commons does stop reproducing paintings at
  the rights boundary. But the image a Wikidata item names is often not a
  reproduction at all. It can be a *photograph*, freely licensed by whoever took
  it, of:
  - a 3D object (12, 23);
  - an installation (24, 31);
  - a building (41);
  - and once, the artist rather than the work (33).

  Past the boundary, Commons answers with photographs. Under gap 6's ruling those
  are legitimate images of a work, judged at review, and the review is all that
  stands between the owner and row 33. One find was missed the other way: row 13
  is public domain, yet its item names no image.
- **R2 was wrong.** The Art Institute serves full-resolution tiles for works it
  holds *in copyright*, too. Measured: for both rows 19 and 35, a tile beyond
  the first 843 pixels came back as image data (about 250 KB each). Its limit is
  what it holds, not the rights.
- **R3's harm did not appear.** Row 41, with no creator, got its own item's image,
  which is the right one. Row 44 got nothing. Per gap 3's ruling, nothing is filed.
  The wrong image came from a different place: an item whose chosen image is not
  the work (row 33).
- **The identity check worked.** Three title matches naming another artist were
  refused rather than attached.

**What this changes:**

- **The Art Institute is a source past the boundary**, for what it holds. Step 3
  starts with the cheapest probe there is: ask it for each anchor artist.
- **The owner's review queue holds the 11 finds.** Reject row 33's photograph; it
  is not *Whaam!*.
