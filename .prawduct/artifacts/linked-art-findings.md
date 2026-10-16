# Linked Art and IIIF Findings: Yale, the Rijksmuseum, Getty

Captured 2026-10-07 before writing the IIIF parsers (interface 1.3,
`arrt/src/arrt/library/sources/iiif.py`) and the `yale` source plugin
(`arrt/src/arrt/library/sources/yale.py`), for arrt#242 (a shared helper) and
the three plugins it serves: Yale #229, the Rijksmuseum #226 and Getty #230. About
140 plain HTTP requests in all, with a generic agent string. Each figure is
marked (m) measured, (e) estimated or (r) recalled. Sizes served were read from the
JPEG header, never from a label. The durable form for Yale is
`arrt/tests/live/test_yale_shapes_are_still_real.py` (`live_museum`). The recorded
answers the unit suite reads are `arrt/tests/fixtures/yale/` and
`arrt/tests/fixtures/iiif/`.

## What the three share: only the last step

Each museum reaches its image service by a different road (m):

| | Road from the object to the image | Image API | Declared limit |
|---|---|---|---|
| Yale | object → Presentation 3 manifest → canvas → image service | 2 | none |
| Rijksmuseum | object → VisualItem → DigitalObject → an image URL (three dereferences, no manifest) | 3 | `maxArea` 17,550,000 |
| Getty | object → media VisualItem → access point; or a deprecated `representation`; or manifests | 3 | `maxWidth`/`maxHeight` 30,000 |

In every case the service is on a host other than the record's. Rights are in a
different place in each, and an object- or manifest-level CC0 licenses the
record, not the image. What all three share is reading the service's `info.json`
for the original's size and declared limits, then choosing one request or the
tiles. So that is what the interface carries (`source-plugins.md` § Versioning
and errors, 1.3), and each plugin keeps its own road.

## Yale (YUAG and YCBA)

### Access

- **Object pages are challenged (m):** `artgallery.yale.edu/collections/objects/<n>`
  and `collections.britishart.yale.edu/catalog/tms:<n>` answer 403 with
  Cloudflare's "Just a moment...".
- **Manifests and images are not (m).** Every one of about 45 requests to
  `manifests.collections.yale.edu` and `images.collections.yale.edu` answered
  200, 404 or (once, § Size) 500, with no challenge and no rate-limit header.
  `manifests.` has no robots.txt (404) and `images.`'s is empty.
  `lux.collections.yale.edu` disallows only `/view/results/`.

### Wikidata

- **The IDs name the pages (m).** YUAG ID P8583 has the formatter
  `https://artgallery.yale.edu/collections/objects/$1`, and YCBA Lido ID P9789
  has `https://collections.britishart.yale.edu/catalog/tms:$1`.
  `Registry.pages_about` builds pages from external-ID formatters, so it returns
  both. YCBA's VuFind number (P4738, `…/vufind/Record/$1`) does not map to a
  manifest.
- **Reach (m), 2D items counted on direct P31 in painting, drawing, print,
  photograph, watercolour and pastel:** YUAG has 4,068 items with no P18, and
  4,053 of them carry P8583 or P9789. YCBA has 392 with no P18, and only 3 of
  those carry one. Counted over P31/P279* instead, YUAG is 20,255 items / 4,698
  with no P18 / 5,804 with P8583, and YCBA is 31,837 / 392 / 29,206 with P9789.
- **P973 is mostly unusable** for YUAG: 8,383 links go to `library.artstor.org`,
  118 to JSTOR and 110 to YUAG's own object pages.

### The manifest

- `https://manifests.collections.yale.edu/{yuag|ycba}/obj/<n>` is built from
  the ID with no LUX call (m). **An object with no image answers 404** (YUAG
  90363; 2 of 25 drawn).
- Presentation 3 (YCBA also serves Presentation 2 at `/v2/ycba/obj/<n>`, which has
  the same canvases). Metadata gives `Title`, and the maker under `Creator(s)`
  at YUAG ("Artist: Vincent van Gogh (Dutch, active France, 1853–1890)";
  "Artist, copy after: Giovanni Francesco Romanelli (…)"; "Artist: Unknown") or
  under `Creator` at YCBA ("Joseph Mallord William Turner, born in London,
  England,1775; …"; "Johann Lorenz Haid, 1702–1750").
- **Rights are per canvas (m):** each canvas's `Image Use Rights` is one of "No
  Copyright - United States", the CC0 1.0 text, "In Copyright", "Copyright Not
  Evaluated" or "Not Assigned". The manifest-level `rights` is CC0 on every
  manifest measured, in-copyright Rothkos included.
- **Several canvases are other views (m):** the Dort (YCBA 34) has five. The first
  is "recto, cropped to image" (14,484 × 9,741), and the fifth is an X-radiograph
  (46,800 × 34,053).

### Size

- **The canvas states the original (m).** Canvas size equalled `info.json`'s on 8
  of 8 images, and `full/full` served exactly that on 5 of 5 (up to 14,484 px).
- **No limit is declared, but one exists (m).** `full/full` of the
  46,800-pixel X-radiograph answered HTTP 500 ("Invalid scanline stride");
  `full/30000,` also failed, and `full/23400,` succeeded in 27 s. Where between
  23,400 and 46,800 a whole request starts failing was not measured.
- **Most works with no image on Wikidata are 480 px (m).** In a random draw of
  25 YUAG items with P8583 and no P18, 2 answered 404, 18 were 480 px on the
  long side, and 5 were served in full (2,255 to 9,143 px). The 480 px works are
  public domain and in copyright alike. Six drawn YUAG prints with IDs (images or
  not) were five Dürers at 7,313–9,915 px and a Warhol at 480.
- **In-copyright works are 480 px (m):** Rothko (2), de Kooning, Hopper's *Rooms
  by the Sea*, Albers, Gottlieb, Buchheister, Beal. Hopper's *Sunlight in a
  Cafeteria*, "Copyright Not Evaluated", is served in full (5,789 × 3,864).
- **So Yale's value for works with no image** is about one in five at full size
  (e, from 5 of 25), and the rest as 480 px placeholders under the owner's ruling
  of 2026-10-03.

### LUX (not used)

`/api/search/item?q=<JSON>` answers Linked Art search pages. Searches by
`identifier` (an accession number, or a Wikidata URI for YUAG) work. A nested
name search (`producedBy.name`) answered 0 in four attempts, and LUX's YCBA
records carry no Wikidata equivalent. Since the IDs reach the YUAG gap, the
plugin does not search.

## The Rijksmuseum (for #226)

Measured 2026-10-07 before writing `arrt/src/arrt/library/sources/rijksmuseum.py`:
about 90 plain HTTP requests, user agent `arrt-research/0.1`, sizes read from the
JPEG header or `info.json`. The durable form is
`arrt/tests/live/test_rijksmuseum_shapes_are_still_real.py` (`live_museum`); the
recorded answers the unit suite reads are `arrt/tests/fixtures/rijksmuseum/`.

### Wikidata and the record

- The Rijksmuseum ID is **P13234**; P350 is RKDimages (m). Its formatter is
  `https://id.rijksmuseum.nl/$1` and its format `^\d{7,9}$` (m).
- That URL answers the Linked Art record to `Accept: application/ld+json`, and
  sends a browser to the object's page on `www.rijksmuseum.nl` with a 303 (m). The
  page's URL carries a title slug and a hash, not the object number
  (`/nl/collectie/object/De-Nachtwacht--3137deb4…`), so this plugin reads no page.
- A well-shaped number the museum does not know answers 400 (`299999999`) or 404
  (`20000000`) (m).

### The search

- `https://data.rijksmuseum.nl/search/collection` takes `title`, `creator`,
  `objectNumber` and `imageAvailable`, and answers a Linked Art
  `OrderedCollectionPage` of record ids, 100 to a page (m).
- `title` matches words in any of the record's languages: "The Night Watch" and
  "Nachtwacht" both find SK-C-5, and "night" finds 26 Rembrandts (m).
- `creator` matches the museum's spelling, not Wikidata's: "Piet Mondrian" finds
  nothing and "Piet Mondriaan" 9 (m). It folds accents for some makers and not
  others: "Isaac Israëls" finds 0 and "Isaac Israels" 2,748; "Jozef Israëls"
  finds 1,180 and "Jozef Israels" 1 (m). So the plugin asks once more without
  accents when an accented name finds nothing. The opposite case (asked plain,
  recorded accented) is not recovered.

### The road to the image

- **object → `shows[0]` (VisualItem) → `digitally_shown_by[0]` (DigitalObject) →
  `access_point[0]`**, an image URL `https://iiif.micr.io/<id>/full/max/0/default.jpg` (m).
  All three records are on `id.rijksmuseum.nl`. An object with no image still has
  `shows`; its VisualItem lacks `digitally_shown_by` (200556187) (m).
- **Rights are on the VisualItem's `subject_to`** (m, 13 objects): the Creative
  Commons Public Domain Mark on public-domain works, rightsstatements.org `InC` on
  in-copyright ones (Marlene Dumas, Karel Appel, Ed van der Elsken, Kees van
  Dongen). The record's `subject_of` carries CC0, which licenses the metadata.
- The DigitalObject says "downloadbaar" or "niet downloadbaar" and "zichtbaar" or
  "niet zichtbaar". In-copyright works are "niet downloadbaar" and served anyway; van
  Dongen's, "niet zichtbaar", served a 345 × 400 preview and a 6,033 × 7,003
  `full/max` (m). The plugin does not read these labels.

### Titles and makers

- Titles are `identified_by` Names; preferred ones are classified `aat:300404670`,
  in English (`aat:300388277`) and Dutch (`aat:300388256`). Some objects are titled
  only in Dutch (Sluijters' poster) (m).
- The maker is in `produced_by.part[]`, in the museum's order. Three shapes (m,
  about 60 records across Rembrandt, Hals, Mierevelt, Bruegel, Vermeer, Israels,
  Appel, Dumas, van Dongen and anonymous works):
  1. `carried_out_by` names the person inline, with `notation` in English and
     Dutch ("Johannes Vermeer"; "anonymous", "anoniem" for an unknown hand).
  2. `assigned_by` assigns the person under `assigned_property: carried_out_by`,
     unclassified, `motivated_by` the evidence (`aat:300028705` signed,
     `aat:300028702` mentioned on object). The part's name statement
     (`aat:300435417`) reads "Karel Appel (signed by artist)".
  3. The same, but the assignment is classified, which is an attribution:
     `aat:300404269` "attributed to Rembrandt van Rijn" (*Samson and Delilah*),
     `aat:300435722` "(possibly)".
- Later parts name a publisher or printer (Sluijters' poster, then Scheltens &
  Giltay), or the design a print is after (`assigned_property: influenced_by`,
  "after design by Rembrandt van Rijn"). A rejected attribution sits in
  `produced_by.assigned_by`, outside the parts ("attributed to Jan Lievens
  [rejected attribution]").
- A person's own record carries a Wikidata `equivalent` (Rembrandt: Q5598) and many
  name forms (m). The plugin does not read it: the identity check works from names.

### Size

- `info.json` is Image API 3, `maxArea` 17,550,000, no `maxWidth` (m).
- The service is looser than it declares (m): `full/max` served 4,649 × 5,177
  (24 MP) and 5,832 × 7,209 (42 MP) whole, and shrank the Night Watch
  (14,645 × 12,158) to 7,133 × 5,922 and a van Dongen (8,217 × 9,538) to
  6,033 × 7,003, both about 42.2 MP. An explicit width beyond the area answers 400.
  1,024 px tiles are served.
- The plugin trusts the declaration: an original within 17.55 MP is one request,
  anything larger is tiled, and `TILE_MAX_PIXELS` bounds what tiling assembles.
  Originals sampled ran from 3,200 × 3,327 to 14,645 × 12,158, most over 17.5 MP.

### Access

- **`iiif.micr.io`'s robots.txt is `Disallow: /` for every agent (m).** The same
  host serves the Philadelphia Museum of Art's images (arrt-sources#13). **The owner
  ruled on 2026-10-07 that a plugin may ask it** (`source-plugins.md` § Trust):
  single, human-led requests are not crawling.
- `data.rijksmuseum.nl` has no robots.txt (404); `id.rijksmuseum.nl` answers 400
  for one; `www.rijksmuseum.nl` disallows only its search pages (m). No challenge
  and no rate-limit header anywhere.

## Getty (for #230)

Measured 2026-10-07 in two passes: the first while building Yale, the second
(about 120 requests) before building the `getty` plugin
(`build-plan-getty-source.md`).

- **Wikidata reaches few works with no image (m).** 2,596 items carry P2582, and 30
  of them have no P18. Of those 30, 28 have an image at the Getty and 2 have no
  manifest (a bound volume, an armlet). The museum holds 124,301 objects with
  images (#230), so the plugin also searches.
- **P2582 holds the page's slug, not the data ID (m):** six characters
  `[0-9A-Z]` on all 2,596, and `data.getty.edu/museum/collection/object/<slug>`
  answers 404. Each record carries the slug as an identifier,
  `urn:getty-local:idm:object:slug/<slug>`, so the SPARQL endpoint
  (`data.getty.edu/museum/collection/sparql`) maps slugs to records: 30 in one
  query, 0.22 s. The page (a JavaScript shell) carries the same map in its
  `local_id_manager` script. The plugin never reads it.
- **The endpoint has no text index (m).** `bds:search` answers nothing. A
  case-insensitive scan over every title, or over every maker's name joined to
  its objects, took 11–14 s. A person by label, case-insensitively, among
  25,611 `E21_Person`s took 0.6 s, and that person's objects with title words
  0.2–0.3 s. A maker of several is in `produced_by → part[] → carried_out_by`, so the
  query follows `P108i_was_produced_by/P9_consists_of?`. 4,716 people link to ULAN
  (`skos:exactMatch`).
- **The record (m).** Titles are `Name`s: preferred (AAT 300404670), primary,
  translated ("La Ville" / "The City"), alternate. The maker's name, its prefix and
  its suffix are `LinguisticObject`s on the production, classified
  `producer-name`, `producer-name-prefix` and `producer-name-suffix`. Prefixes
  include "Attributed to" (3,630), "and" (1,259), "Possibly" (813), "Workshop of"
  (162), "Follower of" (156) and "After" (30). Suffixes include "maker, American"
  (a role and nationality) and "or workshop" / "and workshop". The role statement
  is an occupation ("Photographer" 110,202, "Artist" 37,473), not an attribution.
  `subject_of` names the page (`text/html`) and the IIIF manifest, in
  Presentation 2 and 3.
- **The manifest drops non-ASCII letters (m):** "Fédèle Azari" is
  "Fdle Azari" in its bytes, so names are read from the record.
- **The image road (m).** `shows[]` → `data.getty.edu/media/image/<uuid>` →
  `digitally_shown_by[0]` carries the size and the "IIIF image service" access
  point, but `shows` is in no useful order. On *Irises* the third is its frame,
  which is another object, and on *Migrant Mother* the first is "Subject
  Terms". The manifest's first canvas is the main view on both, matching the
  record's deprecated `representation`, so the plugin reads the manifest.
- **Rights are per object in the manifest's `rights` (m):** CC0, or
  rightsstatements.org `InC` / `InC-RUU` for works in copyright. These agreed with the
  media record's rights on 6 of 6. One manifest (Cariani) states none. The media record
  also carries Getty's clearance: `download`, `zoom` or `thumbnail`.
- **Sizes (m), from JPEG headers.** `info.json` declares `maxWidth`/`maxHeight`
  30,000, and `full/max` served every original asked whole: 573 × 600 (Arbus,
  `thumbnail`), 3,347 × 4,020 (Brockhurst, `zoom`), 4,748 × 6,073 (Lange), 6,455 ×
  5,022 (Weston, `zoom`), 8,409 × 12,441 (Moore, in copyright). Irises came out at
  9,021 × 7,122 by `full/max` and `full/full` alike. Of the 28 with no P18 and a
  manifest, nine are 600–768 px on the long side (eight in copyright, one with no
  rights stated) and the rest 3,540–12,448 px.
- **Access (m).** `data.getty.edu`: no robots.txt (404), no challenge, no
  rate-limit headers. **`media.getty.edu` answers robots.txt with 503**, which RFC
  9309 reads as disallow-all. Nine requests were made there before this was weighed.
  The owner's ruling of 2026-10-07 (§ The Rijksmuseum) covers it.
- **Names the identity check compares (m).** Of the 30, 23 have both a maker in
  the record (read as the plugin reads it) and an English creator label on
  Wikidata. For 15 the names agree by `artist_key`. 8 differ: two attributions,
  which the check is right to refuse ("Circle of Jacopo Sansovino", "Attributed
  to Alessandro Algardi"); five spellings or initials ("Karl Blossfeldt" /
  "Karl Blosfeldt", "Shinjiro" / "Shimjiro" on two items, "Gerald L. Brockhurst"
  / "Gerald Brockhurst", "Robert Oliver Skemp" / "Robert Skemp"); and one name
  carrying another in parentheses ("Giovanni Busi (Cariani)"). Wikidata's own
  names for the maker, read since #245, may settle some of these; that was not
  measured.
