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

- The Rijksmuseum ID is **P13234**; P350 is RKDimages (m). Records are at
  `https://id.rijksmuseum.nl/<n>` with `Accept: application/ld+json`, or
  `https://data.rijksmuseum.nl/<n>`. The search's `title`, `creator` and
  `imageAvailable` parameters work.
- **The road (m):** `shows[0]` → VisualItem → `digitally_shown_by[0]` →
  DigitalObject → `access_point[0]`, an image URL on `iiif.micr.io`. An object
  with no image still has `shows`; its VisualItem lacks `digitally_shown_by`.
- **`iiif.micr.io`'s robots.txt is `Disallow: /` for every agent (m).** Only the
  Night Watch's `info.json` was read (14,645 × 12,158, `maxArea` 17,550,000),
  before the robots file was read. `full/max` was not asked. Whether Arrt may
  fetch from this host is the owner's ruling to make. The same host serves the
  Philadelphia Museum of Art's images (arrt-sources#13).

## Getty (for #230)

- P2582 holds the page's slug, not the data ID: `data.getty.edu/museum/collection/object/<slug>`
  answers 404 (m). The page's `local_id_manager` script, or the SPARQL endpoint,
  maps the slug to the UUID.
- **The road (m):** `shows[]` → `data.getty.edu/media/image/<uuid>` →
  `digitally_shown_by[0].access_point[]`, the one classified "IIIF image
  service", and `digitally_shown_by[0].dimension` gives the original's size.
  `representation` is marked deprecated in the record.
- **In copyright is served in full (m):** Brockhurst, "In Copyright", clearance
  "zoom": 3,347 × 4,020 in full; Irises 9,021 × 7,122 by `full/max` and
  `full/full` alike.
- **`media.getty.edu` answers robots.txt with 503 (m)**, which RFC 9309 reads
  as disallow-all. Nine requests were made there before this was weighed. It is
  the owner's ruling to make, with #226's.
