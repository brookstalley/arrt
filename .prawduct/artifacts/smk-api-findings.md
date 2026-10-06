# SMK API Findings

Captured 2026-10-06 by probing the open API of SMK (Statens Museum for Kunst, the
National Gallery of Denmark) before writing the `smk` source plugin
(`arrt/src/arrt/library/sources/smk.py`). Everything below is **measured**, with
a generic agent string, except where a line says it is read from SMK's OpenAPI
document (`https://api.smk.dk/api/v1/swagger.json`). The durable form is
`arrt/tests/live/test_smk_shapes_are_still_real.py` (`live_museum`), and the
recorded answers the unit suite reads are `arrt/tests/fixtures/smk/`.

## Access

- No key and no account. Base: `https://api.smk.dk/api/v1`, served by nginx
  behind Varnish (`X-Cache: HIT`/`MISS`).
- **No rate limit was found.** The OpenAPI document states none, and no answer
  carried a rate-limit or `Retry-After` header. About 30 requests over half an
  hour, three of them whole originals, drew no refusal. The plugin asks one
  request at a time per work.
- `lang=en` asks for English; Danish is the default (OpenAPI). It changes the
  titles and the rights page (§ Rights).

## The object record

- `GET /art/?object_number=<n>` answers `{"items": [record]}`. The OpenAPI
  document types `object_number` as an array; one value answers one record.
- **An unknown number is HTTP 200 with `{"items": []}`** (`NOPE-0`).
- **The number is matched without regard to case:** `kms1` answers `KMS1`.
- **A number may hold a slash** (`KKS2020-3/16`, `KKSgb2947/26`) or a letter
  outside ASCII (`KMSst28Ø`); both are asked for as they are and answered.
- Fields read: `object_number`, `titles` (a list of `{title, language, type?}`;
  in English where SMK has an English title, in Danish where not, so
  `lang=en` still gives `Interiør` for some), `artist` (a list of names,
  forename first), `public_domain`, `rights`, `has_image`, `image_width`,
  `image_height`, `image_native`, `image_thumbnail`, `frontend_url`. Also present
  and unread: `production`, `image_iiif_id`, `image_iiif_info`, `image_hq`,
  `alternative_images`, `object_url`, `iiif_manifest`.
- `frontend_url` is `https://open.smk.dk/artwork/image/<n>`, the number
  unencoded, its slash and `Ø` included.
- `KMSst28Ø` is an object with `has_image: false` and no `image_native`.

## The image: which URL serves the original at full size

- **`image_native` serves the original at exactly `image_width` × `image_height`,
  for a work in copyright as for one in the public domain.** It is
  `https://api.smk.dk/api/v1/download/<base64 of the IIIF full/full URL>/<n>.jpg`,
  answered HTTP 200 by the API's own host, with no redirect, as `image/jpeg`
  (`Content-Disposition: attachment`):
  - **public domain**, KMS1 (*The Fall of the Titans*): 7174 × 5536, 28,129,362
    bytes, about two minutes for the whole body;
  - **in copyright**, KKS2020-3/16 (Al Masson, *Salon*): 6296 × 4370, 10,125,395
    bytes, first byte at 2.1 s, whole body at 42.8 s.
  Both sizes are read from the served file's header, against the record's.
- The base64 segment decodes to the IIIF image service's
  `<image_iiif_id>/full/full/0/native.jpg`. The IIIF `info.json` for KMS1 states
  7174 × 5536 with `maxWidth`/`maxHeight` 50,000, so IIIF's `full/full` is the
  same image. **No fallback to tiles is needed**, and none is built.
- **Some objects have no IIIF image.** Their `image_native` and `image_thumbnail`
  are the same file, `https://api.smk.dk/api/v1/thumbnail/<uuid>.jpg`, with
  `image_iiif_id` null and `image_hq` null. KMS7121 (Willy Ørskov, *Interior*):
  stated 1229 × 1600, served 1229 × 1600 (91,939 bytes). Four of the fifteen
  "Interior" search hits recorded in the fixtures are this shape. It is SMK's
  largest image of those works, so it is offered at that size, and phase 2
  judges it against the floor like any other.
- `image_thumbnail` for an object with a IIIF image is
  `https://iip-thumb.smk.dk/iiif/jp2/<id>/full/!1024,/0/default.jpg`: KMS1's was
  1024 × 790, 113,024 bytes. That is the preview.
- The served JPEG's EXIF says `copyright=Public Domain` for the in-copyright
  *Salon* too. It is not read.

## Rights

- `public_domain: true` with `rights` the CC Public Domain Mark
  (`https://creativecommons.org/publicdomain/mark/1.0/`).
- **A work in copyright** has `public_domain: false` and `rights` naming SMK's
  page on the use of its material, **in the language asked**:
  `https://www.smk.dk/section/brug-af-museets-materiale/` by default,
  `https://www.smk.dk/en/section/use-of-smk-material/` with `lang=en`. The build
  plan names the Danish one; the plugin asks in English, so it reads both as
  in copyright. Any other value with `public_domain` false is recorded unknown.
- Filtering `[public_domain:false],[has_image:true]` found 14,918 records.

## Search

- `GET /art/search/?keys=<words>&qfields=<field>…&filters=[has_image:true]&rows=<n>&lang=en`
  answers `{"offset", "rows", "found", "items", "facets", …}`, each item a whole
  record. `rows` is at most 2,000 (OpenAPI); the plugin asks for 10.
- `qfields` limits the words to fields (`titles`, `creator`, …). **Every word
  must match in one of them:** `Interior Vilhelm Hammershøi` over `titles` and
  `creator` found 5, all Hammershøi; `Interior` over `titles` alone found 238,
  by many artists: the first ten are all titled exactly `Interior` or
  `Interiør`, by nine artists.
- **The keys are a query language.** `Interior: "An Old Stove" (Hammershøi) [x`
  found nothing, and its words alone found the work (KMS7246); a colon alone did
  no harm. The plugin sends a title's and an artist's words only.
- No match is `{"found": 0, "items": []}`.

## Wikidata

- There is no SMK identifier property. 7,034 items have collection (P195) = SMK
  (Q671384); 6,883 carry "described at URL" (P973), as the build plan measured.
- **Shapes of the SMK pages P973 records**, counted by item: `collection.smk.dk`
  detail pages 6,795 items; `open.smk.dk/artwork/image/…` 87; the old
  `www.smk.dk/udforsk-kunsten/…` site 37 (not read: no installed reader claims
  it, so it stays a sighting and the work is searched for).
- Spellings seen, each kept exactly, because the identity check matches a page
  as the item spells it:
  - `https://collection.smk.dk/#/en/detail/KMS8010` (the common one; *Tree
    Trunks*, Q20268298), and `#/detail/<n>` with no language;
  - `http://collection.smk.dk/#/en/detail/KMSst28Ø` (http, a raw `Ø`);
  - `https://collection.smk.dk/#/detail/KKS12485%2F6` (the slash encoded);
  - `https://open.smk.dk/en/artwork/image/KKSgb2947/26` (the slash raw), and
    `…/KMS421/` with a trailing slash;
  - `https://open.smk.dk/artwork/image/KMS4585?q=KMS4585&page=0` (a search's
    query string left on).
- `Registry.pages_about` yields P973 values as given, and the fragment page
  reaches the finder and its `FoundImage.url` unchanged (live test).
