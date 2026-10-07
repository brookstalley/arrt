# Artist-name identity findings

Measured 2026-10-06 for arrt#245, before the design. The question: phase 2
refuses an image when the holder's artist and the work's artist differ under
`dedup.artist_key`. How many of those refusals name the same person, what
would accept them, and would any wider rule let a wrong image in?

The scripts and their inputs were kept in a scratch directory and are not part
of the repo. Each number below names its population. The durable check that
the measured name shapes still exist is
`arrt/tests/live/test_wikidata_creator_names_are_still_real.py` (`live_museum`).

## What the check knows when it refuses

- The work's QID, when the work has one, and the page the image was found on.
- The pages the item records (`Registry.pages_about`), which phase 2 already asks
  for when a title differs.
- Through the item, its creators (P170). Each creator has a label and aliases in
  many languages, and birth and death years.
- The holder's record gives only a name. `FoundImage` carries no dates, so life
  dates cannot be compared at the seam today.

**Every source that reaches a work through its item finds images on the item's
own pages.** NGA (built on `feature/nga-source`), navigart and Art UK all do. So
for them the item already vouches for the page, and the artist comparison is the
only check left once the title differs.

## Populations

- **NGA.** Wikidata items with an NGA object ID (P4683) and a creator (P170),
  joined to NGA's open data (`objects.csv`, `published_images.csv`, fetched
  2026-10-06). Kept only objects with a primary image and an attribution: 67,361
  items. The holder's name is `attribution`, as the NGA finder reports it. The
  Library's artist is the creator's `en,mul` label, as the registry gives it.
  NGA's own `constituents.csv` names a Wikidata QID for many of its artists. That
  is ground truth for "same person", and independent of Wikidata's aliases.
  - This counts 18,252 refusals in 67,361 items. The NGA findings
    (`feature/nga-source`) count 9,377 of 39,873, under a different join. The
    rates are close: 27% and 24%.
- **Pompidou.** Items with an MNAM artwork ID (P6355) and a creator: 2,198 items.
  Their records came from navigart vault 15, which is what
  `collection.centrepompidou.fr` reads. The first non-anonymous author was put
  in reading order with `navigart.reading_order`. The deployed plugin is
  private, so its rendering of the name is assumed to be the same. Ground truth
  is navigart's `authors_birth_death` against the creator's Wikidata birth year,
  within 2 years.
- **Art UK.** Art UK answers 403 to an unattended fetch, so its pages were not
  read. **The holder's name is inferred** from the creator's Art UK artist ID
  (P1367, for example `lowry-laurence-stephen-18871976`): forenames, then
  surname, with every split of the slug tried. That is a lower bound on
  refusals, since any reading that matches the label counts as agreement.
  - Two samples were taken of creators of Art UK works (P1679): the 500 with
    the most works, covering 54,812 of 157,708 items, and 500 at random
    (seed 245).

## What the refusals are

| Population | Pairs | Label key agrees | Refused |
|---|---|---|---|
| NGA | 67,361 | 49,109 | 18,252 |
| Pompidou | 2,198 | 1,897 | 301 |
| Art UK, top 500 creators | 500 creators | 411 (44,602 works) | 89 (10,210 works) |
| Art UK, 500 at random | 500 creators | 437 (1,815 works) | 63 (324 works) |

The shapes, with the commonest first:

- **Full name against a short or initialled label:** `Laurence Stephen Lowry` /
  `L. S. Lowry`, `Joseph Mallord William Turner` / `J. M. W. Turner`,
  `Rembrandt van Rijn` / `Rembrandt` (345 NGA items), `Charles B. J. Févret de
  Saint-Mémin` / `Charles Balthazar Julien Févret de Saint-Mémin` (840).
- **Another language's form:** `Vassily Kandinsky` / `Wassily Kandinsky` (125
  Pompidou items), `Natalia Gontcharova`, `Kasimir Malévitch`, `William Heine` /
  `Wilhelm Heine`.
- **A mononym or a known-as name:** `Kisling`, `Canaletto` / `Giovanni Antonio
  Canal`, `Le Douanier Rousseau`, `Moderno`.
- **Spelling variants:** `Allart` / `Allaert van Everdingen`, `Renold Elstrack` /
  `Elstracke`.
- **Honorifics and generations:** `Sir Muirhead Bone` (268), `Sir Anthony van
  Dyck`, `Willem van de Velde II`.
- **Several people, or a print after a design:** `Robert Havell after John James
  Audubon` / `Robert Havell` (424), `Willem de Passe and Magdalena de Passe`,
  `Pierre Bonnard, Ambroise Vollard (publisher)`.
- **A wrong creator on the item:** `Vassily Kandinsky` on an item whose creator
  is `Joe Keery`, and `Maurice Utrillo` against `Raoul Dufy`. These refusals are
  correct.

## The candidate rule: both names are names Wikidata records for one creator

Accept when the Library's artist and the holder's artist are both, under
`artist_key`, a label or an alias of the same creator the work's item records.
The three name sources were measured:

| Names compared | NGA accepted | NGA same person (NGA's QID) | NGA no QID to check | NGA different QID | Pompidou accepted |
|---|---|---|---|---|---|
| Labels, every language | 5,152 | 4,941 | 194 | 17 | 204 |
| Labels and aliases, `en` and `mul` | 7,363 | 6,780 | 532 | 51 | 253 |
| **Labels and aliases, every language** | **7,588** | **6,920** | **606** | **62** | **272** |

- **Pompidou:** 271 of the 272 it accepts have the same birth year within 2
  years. The one that differs is `Jean Kwiatkowski`, born 1894 by navigart,
  against the creator `Jan Kwiatkowski`, born 1887. The rule leaves 29
  Pompidou refusals, including both wrong creators above.
- **Art UK (inferred names):** of the top 500, it accepts 85 creators (9,950
  works) and leaves 4 (260). Of the random 500, it accepts 41 (252 works) and
  leaves 22 (72). It accepts `Laurence Stephen Lowry` for L. S. Lowry (Q1354277)
  and `Joseph Mallord William Turner` for J. M. W. Turner.
- **The 62 NGA pairs whose QIDs differ** are mostly duplicate Wikidata items for
  one person: `George Joji Miyasaki`, `Wilhelm Heine`, `Reg Gammon`, `Godfrey
  Frankel`, `Pittoni`, `Battista d'Agnolo`. A few are family names the sources
  split differently: `Hans Collaert the Elder` / `Jan Collaert (I)`, `Bernd and
  Hilla Becher` / `Bernd Becher`. One is a wrong creator on the item:
  `Charles Maurin` against Winston Churchill (Q65071199), whose English aliases
  include "Charles Maurin". In every one the image is the item's own page.
  - **No accepted pair was found to be a different work.** The page is the one
    the item records, so the image is the item's work. What differs is which
    person-item Wikidata and NGA hold for its maker.

### Aliases are noisy, and that bounds where the rule may run

Wikidata aliases include imported name variants that also name other people.
`Canaletto` and `Giovanni Antonio Canal` are both aliases of Bernardo Bellotto
(Q164688), who was Canal's nephew. `Thomas Wright` and `Wright` are aliases of
Joseph Wright of Derby. Measured as ambiguity, the holder's name is also a name
of another creator in the fetched population (8,027 people):

- NGA: 61 of the 7,588 accepted (nearly all `Canaletto`).
- Pompidou: 2 of 272 (`Constant`, `Corneille`).

**So an alias match is safe only where something else already identifies the
work.** On a page the item records, accepting a wrong image would take two
independent errors: the item records the wrong page, *and* that page's artist is
an alias of the item's creator. Where only the title identifies the work, the
alias is the only corroboration. The case it would let through is real.
Brueghel the Younger painted copies of his father's compositions under the same
titles, and "Bruegel" names both men.

## Options weighed

1. **The item's page vouches for the artist too** (skip the artist check on a
   linked page). It accepts all 18,252 NGA refusals. It also accepts the
   wrong-creator items above and any wrong page an item records. It removes a
   check `test_a_recorded_page_by_another_artist_is_still_refused` pins as a
   contract. Not chosen: the owner ruled 2026-10-06 that the name check stays.
   The "X after Y" and multi-maker shape is filed as #257.
2. **Wikidata names, on a page the item records only.** It accepts 7,588 of
   18,252 NGA refusals, 272 of 301 Pompidou, and Art UK's Lowry. No accepted
   pair is a different work. Every wrong-creator refusal measured stays refused,
   except where the item's creator already carries the holder's name as an
   alias. **Chosen.**
3. **Wikidata names wherever the work has a QID**, title-matched results from
   search sources included. It would widen the search sources (AIC, the Met,
   SMK) by an amount not measured here. It carries the Brueghel risk with only a
   title behind it. Not chosen.
4. **Initials against full given names** (`L S Lowry` = `Laurence Stephen
   Lowry`), which is local and needs no registry. It covers one shape of the
   seven, and it merges `J Turner` with every Turner. Not chosen.
5. **Life dates.** These are the strongest disambiguator, but `FoundImage`
   carries no dates and most holders' records name none. Out of scope here.

## What the rule leaves refused

The rule leaves these refused, by design, for later work:

- **Prints after a design, and multiple makers** (`X after Y`, `X and Y`): the
  largest remaining NGA shape, 424 items for Havell alone. Splitting a holder's
  attribution into its makers is a parser per holder's convention. Here the
  holder names the right person, inside a longer string.
- **Honorifics** that are not in Wikidata's names. `Sir Muirhead Bone` (268) and
  `Sir Anthony van Dyck` are accepted, because the creator's aliases carry those
  forms. A `Sir` that no alias carries stays refused.
- **Token order** (#79): untouched. The name comparison stays ordered, so it
  only accepts a reversed name that Wikidata itself records.
