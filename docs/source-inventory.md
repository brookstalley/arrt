# Source inventory

Every holder Arrt reads images from through an open, documented interface, or could,
with where each stands. How a source plugin works is `docs/source-plugins.md`. Why
each candidate is ranked where it is, and what was measured, is on its backlog item.

**How candidates are ranked.** By the art the owner would hang: 20th-century modern
through living artists, much of it in copyright. Public-domain volume counts for
less. Two rulings shape the ranking:
- A small image of a work someone asked for is worth having, as a placeholder for
  a better one (2026-10-03). So a size floor lowers a source's value but does not
  rule it out.
- Rights gate nothing for household use (2026-10-06).

Measurements are from 2026-10-06 and 2026-10-07 unless stated. "WD gap" is the
count of 2D works Wikidata places in the collection that have no image (P18).

## Built

| Plugin | Holder | How it finds a work | Largest image | Notes |
|---|---|---|---|---|
| `commons` | Wikimedia Commons | the work's Wikidata image (P18) | the file's own size | Needs a Wikidata item; no title search |
| `wikidata` | Wikidata | pages only: the holder pages an item records | none | Finds pages for other plugins to read |
| `artic` | Art Institute of Chicago | its API, by search; also browses its collection | IIIF original | Declines without `ARTIC_USER_AGENT` |
| `met` | The Metropolitan Museum of Art | its open-access API, by item or by search | the original | The API carries images of public-domain objects only |
| `smk` | SMK, National Gallery of Denmark | its open API, by the item's pages or by search | IIIF, 7,000–9,000 px | In-copyright works included, at full size |
| `navigart` | navigart.fr collections, among them the Musée d'Art Moderne de Paris | its documented API, by the item's pages | 1,000 px | Placeholders until a better copy is found |
| `nga` | National Gallery of Art, Washington | a local copy of its open data, by the item's pages | IIIF original, or a capped copy | Keeps its data in its own directory |
| `yale` | Yale University Art Gallery and Yale Center for British Art | IIIF manifests, by the item's pages | IIIF original, up to 14,484 px | Rights read per canvas |
| `getty` | J. Paul Getty Museum | SPARQL and Linked Art, by the item's pages or by maker and title | IIIF, up to 30,000 px in one request | In-copyright works included, some kept at 600 px |
| `rijksmuseum` | Rijksmuseum | Linked Art, by the item's record or by maker and title | IIIF; over 17.55 MP is fetched as tiles | In-copyright works included |

## Candidates

In the order they would be built. "Tier" is the backlog's.

| Holder | Interface | Largest image | Reach | Disposition | Item |
|---|---|---|---|---|---|
| Europeana | Search API, free key | `>4 MP` filter; holders' own hosts | 34,524 open extra-large paintings | Tier 5. Its unique value is holders with no API of their own. Matching rests on title and artist, often not in English. Ruled 2026-10-06: it may read any public host that passes Arrt's address check | arrt#227 |
| Victoria and Albert Museum | API v2, IIIF | 2,500 (1 sample) | WD gap 826 | Tier 5 | arrt#228 |
| Smithsonian Open Access (SAAM, NPG and others) | API, key | 2,725 (1 sample) | WD gap: SAAM 4,423, NPG 1,897 | Tier 5. SAAM is the closest fit to the owner's taste of the tier | arrt#231 |
| Paris Musées | GraphQL, key | 600 px at the Musée d'Art Moderne | 252,903 free images, mostly Carnavalet and the Petit Palais | Tier 5, demoted 2026-10-07: navigart serves the Musée d'Art Moderne's works larger. Kept for Carnavalet and the Petit Palais, whose sizes are unmeasured | arrt#233 |
| Cleveland Museum of Art | open API | 3,400–5,500 | WD gap 21,189; of 25 sampled, 20 were in copyright and served no image | Tier 5 | arrt#235 |
| Harvard Art Museums | API, key; IIIF answered 403 | ~3,000 | WD gap 3,972 | Tier 5 | arrt#236 |
| Finnish National Gallery | API | not measured | WD gap 7,483 | Tier 6. Check first whether Europeana covers it | arrt#237 |
| Princeton University Art Museum, Minneapolis Institute of Art | open APIs | not measured | WD gap ~2,500 each | Tier 6 | arrt#238 |
| RKDimages, POP (French heritage database) | open | small (recalled) | WD gaps 56,846 and 10,459 | Tier 7. Measure image sizes before building; likely adds nothing | arrt#239 |

## Not yet measured

Found on 2026-10-07 by ranking every collection on Wikidata by modern works (creator
born 1870 or later) with no image. Each would be a candidate here if it has an open
interface. That has not been checked.

| Holder | Modern works with no image on Wikidata |
|---|---|
| Cultural Heritage Agency of the Netherlands (the Dutch state collection) | 8,130 |
| National Gallery of Modern Art, New Delhi | 4,997 |
| National Gallery of Australia | 4,060 |
| Mu.ZEE, Ostend | 3,723 |
| Berlinische Galerie | 2,608 |
| Slovak National Gallery and three regional Slovak galleries | ~10,900 together |
