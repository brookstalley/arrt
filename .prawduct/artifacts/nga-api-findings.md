# NGA Findings

Captured 2026-10-06 for arrt#234, a reader for the National Gallery of Art
(Washington). The issue asked for one thing before any build: **an ID-to-image
lookup that does not need the 89 MB CSV.** This records what was measured
against that question. Everything below is **measured**, with a generic agent
string and one request at a time, unless a line says *inferred*.

**The answer is no.** No public interface measured here turns an NGA object ID
into its image without the open data's CSV or the artwork's web page. So the
design the issue names ("resolve the object ID through NGA's open data to its
IIIF service, never fetching the page") cannot be built as written. Which of the
two ways round it to take is the owner's call (§ What the owner decides). Nothing
was built.

## Wikidata

- The property is **P4683** ("National Gallery of Art artwork ID"; regex
  `[12]?\d{1,5}`). P4659, which looks like it, is the Musée d'Orsay's.
- **127,886 items carry P4683**; 53,085 of them have an image (P18), and 130
  carry more than one ID.
- P4683's preferred formatter is `https://www.nga.gov/collection/art-object-page.$1.html`,
  and its normal-rank one is `…/content/ngaweb/Collection/art-object-page.$1.html`.
  So `Registry.pages_about` yields the old site's page.
- **128,459 IIIF manifest URL (P6108) claims** on these items name
  `https://www.nga.gov/api/v1/iiif/presentation/manifest.json?cultObj:id=<id>`
  (and a `content/ngaweb/` twin). **That endpoint is dead.** About half of the
  requests met a Cloudflare challenge (HTTP 403, `cf-mitigated: challenge`). The
  others got a 302 to `https://api.nga.gov/api/v1/iiif/presentation/manifest.json`,
  which drops the query string and answers 404. The twin answers 404. The
  Wayback Machine holds this endpoint's JSON answers up to 2025-03-21, so it
  died with the site's rebuild after that date (*inferred* from those dates).

## www.nga.gov

- The site is Drupal, behind Cloudflare.
- **The old page redirects to the new one.** `…/collection/art-object-page.1185.html`
  (both formatter shapes) gives a 301 to `/artworks/1185-two-women-window`. The
  new page needs its slug: `/artworks/1185` alone is a 404.
- **The artwork page carries the image.** It names `https://api.nga.gov/iiif/<uuid>/…`,
  with the original's `info.json` for an open image and the `<uuid>__900`
  service for a capped one. Six artwork-page requests, over two works, were all
  answered 200, and none was challenged. These pages are the only per-object route measured
  that leads from an ID to an image.
- **Every JSON route tried was refused or does not exist.** `/artwork-search`,
  `/api/…` and `/jsonapi` were challenged (403). The artwork page with
  `?_format=json` gets a 406 ("only supports the HTML format").
  `https://id.nga.gov/<uuid>` (linked from the page) is a 404, and
  `https://id.nga.gov/` redirects to the home page.

## The open data (GitHub)

- `NationalGalleryOfArt/opendata`, released as CC0, updated once a day: the last
  five commits to `data/published_images.csv` were at about 10:00 UTC on
  2026-10-01 through 10-06, with one day skipped.
- **`published_images.csv` is the only file that joins an object to its image.**
  It is 89,400,881 bytes, served from `raw.githubusercontent.com` gzipped:
  26,598,786 bytes on the wire, read in 7.1 s. Parsing it into an index took
  0.8 s and 38 MB (tracemalloc peak, one `(uuid, width, height, maxpixels,
  openaccess)` tuple per object).
- **It cannot be looked up by range.** The rows are sorted by image `uuid`, not
  by object, and the host serves the file gzipped, so a range covers compressed
  bytes. A binary search by object ID is not possible.
- A refresh can be conditional. It sends a weak ETag, an `If-None-Match`
  request is answered 304 with no body, and `Cache-Control` is `max-age=300`.
- Columns: `uuid, iiifurl, iiifthumburl, viewtype, sequence, width, height,
  maxpixels, openaccess, created, modified, depictstmsobjectid, assistivetext`.
- 129,548 rows: 120,191 `primary` and 9,357 `alternate`. 120,013 objects have a
  primary image, and 177 have more than one, all at `sequence` 0.
- **`maxpixels` decides what is served, not `openaccess`.** Among primary rows:
  `openaccess=1` with `maxpixels` empty, 63,944; `openaccess=0` with `900`,
  50,228; `openaccess=0` with `maxpixels` empty, 6,011; `openaccess=0` with
  `4000`, 8. A non-open row with empty `maxpixels` is served uncapped, as an
  open one is (§ The IIIF image service).
- `width` and `height` are the original's. For object 1185 the CSV states
  17385 × 20855, and so does `info.json`.

## The IIIF image service (`api.nga.gov/iiif`)

- IIIF Image API 2, level 1, served with `Access-Control-Allow-Origin: *` and
  `Cache-Control: max-age=86400`. No rate limit or `Retry-After` header was seen.
- **An open image's `info.json` states the original.** Object 1185 is 17385 ×
  20855. Its tiles are served at full resolution, including one cut from the
  far corner (`17000,20500,385,355`). So the original is reached through the
  tiles (`FetchLocator.tiles` on `info.json`, read by `dezoomify-rs`).
- **A direct `full/full` (or `full/max`) is capped at 4,096 px on the long
  side.** For object 1185 it gave 3414 × 4096, and the same cap held for two
  non-open images with empty `maxpixels` (5404 × 1164 gave 4096 × 882; 4147 ×
  5418 gave 3135 × 4096). A direct fetch is not the original.
- **A capped image redirects.** Every request to `<uuid>/…` for a
  `maxpixels=900` row is answered 303 to `/iiif/<uuid>__900/…`, `info.json`
  and tiles included. That service's `info.json` states the derivative (887 ×
  900 and 895 × 900, measured), and `full/full` serves it at that size. **It
  also upscales:** `full/!4000,4000/` gave 3942 × 4000 from the 900 px file.
  Only `full/full` or `info.json` gives the true size. A `maxpixels=4000` row
  redirects to `<uuid>__4000` in the same way (4000 × 3098 stated).
- An unknown uuid gets a 303 to `<uuid>__300/info.json`. So "no such image" is
  not an error status, and a reader has to check the size it is given.

## What the open data reaches, joined to Wikidata

The 127,886 P4683 items were joined to the CSV's primary images by object ID
(2026-10-06). For each image class, the table counts the items with no P18 and
the items with one:

| The NGA's image | No P18 | Has P18 |
|---|---|---|
| uncapped, 3,000 px or more on the long side | **11,655** | 51,948 |
| uncapped, under 3,000 px | 510 | 945 |
| capped at 900 px | **40,797** | 154 |
| capped at 4,000 px | 2 | 0 |
| no image in the open data | 21,837 | 38 |

Against the issue's figures, which were taken by another method:

- **6,011 "new works with open images of 3,000 px or more" is not what was
  measured.** 6,011 is exactly the number of non-open primary rows with empty
  `maxpixels`. The join gives 11,655 items with an uncapped image of 3,000 px or
  more and no P18 (*inferred:* the two figures were conflated).
- **"47,993 larger copies of works Commons holds"** compares with 51,948 items
  that have P18 and an uncapped NGA image of 3,000 px or more. Whether the NGA's
  copy is larger than the Commons file was not measured.
- **"About 42,840" 900 px placeholders** compares with 40,797 items with no P18
  plus 154 with one.

**The corpus rows the issue names are all capped at 900:**

| Row | Item | NGA object | Original (CSV) |
|---|---|---|---|
| 15, Escher, *Castrovalva* | Q65574099 | 54101 | 3519 × 4497 |
| 35, Lichtenstein, *Crak!* | Q75119355 | 76397 | 4000 × 2829 |
| 44, Agnes Martin, *On a Clear Day* I | Q74034248 | 59824 | 9724 × 9928 |

Rows 17 (*Relativity*, 54256, 3648 × 3580) and the Warhol *Marilyn* sheet
(143438) are capped too. Row 16 (*Metamorphosis II*, 46828) has no image in the
open data. *Castrovalva* has been US public domain since 2026-01-01
(`procurement-corpus.md` row 15) and is still capped. So **`openaccess=0` does
not mean "in copyright"**: a reader would record it as unknown, not as
`IN_COPYRIGHT`.

## What the owner decides

Each of these was measured to work. None was chosen.

1. **The plugin keeps the open data's index.** It downloads
   `published_images.csv` (26.6 MB on the wire, 7 s; 38 MB in memory), refreshes
   it no more than once a day with a conditional request, and answers object ID
   → uuid, size and cap from memory. The page is never fetched and every host is
   open. The costs:
   - the issue named avoiding this CSV as its precondition;
   - a plugin that holds a day-old copy of a holder's catalogue is new to the
     contract (`source-plugins.md` says Arrt, not the plugin, decides storage).
     In memory only, it writes nothing, but every restart downloads it again.
2. **The reader reads the artwork page.** One request per object, through the
   formatter's 301, and the uuid is taken from the page. This is a museum-page
   reader on a host behind Cloudflare, which challenges every other path tried.
   Under the owner's rule that museum-page and challenge-passing readers are
   private (`build-plan-smk-source.md`, citing the rulings of 2026-10-03/04),
   it belongs in the private repository.
3. **Wait** for the NGA to restore a per-object manifest. The Wikidata P6108
   claims show one existed.

Whichever is chosen, the reader's shape is settled by the measurements above:

- open or uncapped → `FetchLocator.tiles(<uuid>/info.json)` at the original's
  size;
- capped → the `__900` derivative as a placeholder. A direct `full/full` gets it
  at its stated size, and that is the size reported;
- rights: `openaccess=1` → public domain (*recalled, not measured here:* the NGA
  releases its open-access images as CC0);
  `openaccess=0` → unknown.
