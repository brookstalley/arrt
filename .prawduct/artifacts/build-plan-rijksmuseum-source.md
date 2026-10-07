---
artifact: build-plan
version: 1
scope: rijksmuseum-source
branch: feature/rijksmuseum-source
partition: serial — one builder, one plugin module and its records. Runs beside a research delegate measuring unmeasured modern holders, which writes only to the session scratchpad and shares no file with this plan
depends_on:
  - artifact: source-plugins
governed_by:
  - artifact: source-plugins
    dispositions:
      - "§ Versioning and errors → conforms: `rijksmuseum` imports only `arrt.library.sources` (and `httpx`), and uses interface 1.3's `ImageService`; no interface change"
      - "§ What a finder or reader must report → conforms: title and artist are the Rijksmuseum's own (a title its record gives, its maker statement with its attribution); dimensions are the original's, from `info.json`; rights from the VisualItem's `subject_to`, never a filter"
      - "§ Which plugin reads a URL → conforms: `rijksmuseum` claims `id.rijksmuseum.nl/<7–9 digits>`, the shape Wikidata's formatter for P13234 builds, and nothing else"
      - "§ Trust → conforms: `iiif.micr.io`'s robots.txt disallows `/`; the owner's ruling of 2026-10-07 lets a plugin make single, human-led requests there"
  - artifact: project-preferences
    dispositions:
      - "A source that reads pages treats a page it does not recognise as could-not-be-asked → conforms: a record, search answer or `info.json` not of the shape expected is `ImageSearchFailure`. The plugin reads no web page"
      - "Identity is never a source URL → conforms: the record URL is a source attribute; identity stays the work's"
      - "Testing strategies → conforms: the network is doubled with recorded answers; the live half is `live_museum`"
  - artifact: data-model
    dispositions:
      - "Invariant 13, rights gate nothing → conforms: in-copyright works (rightsstatements.org `InC`, marked not downloadable) are found and offered at the size served"
last_validated: null
---

# Build Plan — the Rijksmuseum through its Linked Art API and IIIF

## What this plan is

arrt#226. The owner asked for it on 2026-10-07 ("let's do 226"), the last of the
Linked Art tier after Yale (#229) and Getty (#230). The robots.txt question it
waited on was ruled the same day (`source-plugins.md` § Trust).

**Measured 2026-10-07** (about 90 requests, user agent `arrt-research/0.1`;
recorded answers in the session scratchpad, copied to
`arrt/tests/fixtures/rijksmuseum/` by this plan; written up in
`linked-art-findings.md` § The Rijksmuseum):

- **Wikidata's P13234 is the record's number.** Its formatter is
  `https://id.rijksmuseum.nl/$1` and its format `^\d{7,9}$`. That URL answers its
  Linked Art record under `Accept: application/ld+json`, and redirects a browser
  (303) to the object's page on `www.rijksmuseum.nl`. A well-shaped number the
  museum does not know answers 400 (`299999999`) or 404 (`20000000`).
- **The search** (`data.rijksmuseum.nl/search/collection`) takes `title`,
  `creator`, `objectNumber` and `imageAvailable`, and answers a Linked Art
  `OrderedCollectionPage` of record ids (100 per page). `title` matches words in
  any of the record's languages ("The Night Watch" and "Nachtwacht" both find
  SK-C-5; "night" finds 26). `creator` matches the museum's own spelling of the
  maker, not Wikidata's: "Piet Mondrian" finds nothing, "Piet Mondriaan" 9. It
  folds accents only sometimes: "Isaac Israëls" finds 0 and "Isaac Israels" 2,748,
  but "Jozef Israëls" finds 1,180 and "Jozef Israels" 1.
- **The road** is object → `shows[0]` (VisualItem) → `digitally_shown_by[0]`
  (DigitalObject) → `access_point[0]`, which is `https://iiif.micr.io/<id>/full/max/0/default.jpg`.
  An object with no image has a VisualItem with no `digitally_shown_by`
  (200556187).
- **Rights are on the VisualItem's `subject_to`**: the Creative Commons Public
  Domain Mark on public-domain works, rightsstatements.org `InC` on in-copyright
  ones (Marlene Dumas, Karel Appel, Ed van der Elsken, Kees van Dongen). The record's own
  `subject_of` CC0 licenses the metadata. The DigitalObject says "downloadbaar"
  or "niet downloadbaar", and "zichtbaar" or "niet zichtbaar"; the image is served either way
  (van Dongen, "niet zichtbaar": a 400 px preview served).
- **The titles** are `identified_by` Names, preferred ones classified
  `aat:300404670`, in English (`aat:300388277`) and Dutch (`aat:300388256`). Some
  objects have only a Dutch title.
- **The maker** is in `produced_by.part[]`, in the museum's order. Three shapes:
  1. `carried_out_by` names the person inline, with English and Dutch
     `notation` ("Johannes Vermeer"; "anonymous" for an unknown hand).
  2. `assigned_by` assigns the person with `assigned_property: carried_out_by`,
     unclassified, and `motivated_by` the evidence: "signed by artist" or
     "mentioned on object". The part's English name statement (`aat:300435417`)
     then reads "Karel Appel (signed by artist)".
  3. The same, but the assignment is **classified**, which is an attribution:
     `aat:300404269` reads "attributed to Rembrandt van Rijn"
     (*Samson and Delilah*), and `aat:300435722` "possibly".
  Another part may name a publisher or printer (Sluijters' poster: the designer, then
  Scheltens & Giltay), or a design the print is after
  (`assigned_property: influenced_by`).
- **Sizes.** `info.json` is Image API 3 and declares `maxArea` 17,550,000 and no
  `maxWidth`. The service is looser than it declares: `full/max` served 4,649 × 5,177
  (24 MP) and 5,832 × 7,209 (42 MP) whole, and shrank the Night Watch
  (14,645 × 12,158) and a van Dongen to about 42 MP. A width the area exceeds
  answers 400. Tiles of 1,024 are served. Among those sampled, originals run from
  3,200 × 3,327 to 14,645 × 12,158, most over 17.5 MP.
- **Access.** `data.rijksmuseum.nl` has no robots.txt (404), and `id.` answers 400 for
  one. `www.rijksmuseum.nl` disallows only its search pages. No challenge and no
  rate-limit header anywhere.

## Requirements Confidence

**High** for the item road, the image and the rights. **Medium** for the search
(the creator's matching rule is the museum's, measured on a dozen names) and the
maker (three shapes, measured on about 60 records).

- [DECISION: a built-in plugin `rijksmuseum`, `arrt/src/arrt/library/sources/rijksmuseum.py`.
  The finder reads the item's `pages_about` for `id.rijksmuseum.nl` records; when the
  item names none the museum knows, or there is no QID, it searches. The reader
  follows a record to its image service | an open API and image service belong in
  the public repository | agent's]
- [DECISION: **the search needs the artist.** A work with no artist and no record on
  its item is `ImageQueryUnanswerable` | each hit costs four requests (record,
  VisualItem, DigitalObject, `info.json`). A title alone ("Portrait") matches across
  the collection, which the identity check then refuses. As `getty` | agent's]
- [DECISION: search with `title`, `creator` and `imageAvailable=true`, reading at
  most ten hits from the first page. When that finds nothing and the artist's name
  has letters outside ASCII, search once more with the accents removed | the
  museum's accent folding is inconsistent, measured both ways. The opposite case
  (asked plain, recorded accented) is not recoverable without its spelling | agent's]
- [DECISION: the reported title is the record's title equal to the one asked,
  ignoring case and spacing, where there is one; otherwise the preferred English
  title; otherwise the first preferred title; otherwise the first title | as `getty`.
  The museum's titles are its own, and English is what a request names | agent's]
- [DECISION: the reported artist comes from the first part that names a maker by
  `carried_out_by`, inline or assigned. Shape 1: the person's English notation,
  else any notation; "anonymous" is None. Shape 2 (unclassified assignment): the
  part's English name statement with one trailing parenthetical removed, so "Karel
  Appel (signed by artist)" reports "Karel Appel" and "Pieter Bruegel (I) (mentioned
  on object)" reports "Pieter Bruegel (I)". Shape 3 (classified assignment): the
  part's English name statement as written, "attributed to Rembrandt van Rijn" |
  evidence that the artist made the work is not an attribution, and the identity
  check should compare the name. An attribution should be refused by the identity check, as
  `getty`'s "Attributed to" is. A part with no English statement falls back to the
  Dutch one, then None | agent's]
- [DECISION: rights from the VisualItem's `subject_to[].classified_as`: a Creative
  Commons `publicdomain/mark/` or `publicdomain/zero/` → `PUBLIC_DOMAIN`;
  rightsstatements.org `InC` with any `-` suffixes → `IN_COPYRIGHT`; anything else,
  absence included → `UNKNOWN`. "niet downloadbaar" is not read | measured on 13
  objects; rights gate nothing | agent's]
- [DECISION: the finder reads `info.json` for the original's size (there is no
  manifest), and reports `DIRECT_HTTP` when the service declares it serves the
  original whole, `DEZOOMIFY` otherwise. The reader returns `ImageService.locator`.
  `direct_max_side` is 16,384 | the declared `maxArea` decides first: an original
  within 17.55 MP is a single request, anything larger is tiled, and
  `TILE_MAX_PIXELS` bounds what tiling assembles. Relying on the undeclared 42 MP
  that `full/max` served would build on behaviour the service does not promise | agent's]
- [DECISION: hosts. Records on `id.rijksmuseum.nl` (object, VisualItem and
  DigitalObject alike), the search on `data.rijksmuseum.nl/search/collection`, images
  and previews on `iiif.micr.io`. No redirect is followed. An access point or
  service elsewhere is could-not-be-asked | the house rule | agent's]
- [DECISION: a record answering 400 or 404, a VisualItem with no
  `digitally_shown_by`, and an object with no `shows` hold nothing. Any other
  status, network errors, and a body not of the measured shape are
  could-not-be-asked | 400 is what the museum answers for a number it does not
  know, and a number reaches a request only after matching `\d{7,9}` | agent's]
- [DECISION: every hit is reported under its `id.rijksmuseum.nl` URL, whether found
  through the item or the search | it is what Wikidata's formatter builds, so the
  identity check's page link holds. A curator opening it lands on the museum's page
  through the 303 | agent's]
- [ASSUMPTION: the museum publishes no rate limit and none was met; one request at a time, unpaced, as `getty`]
- [ASSUMPTION: no change to `DEFAULT_SOURCE_ORDER`; `rijksmuseum` sorts among the unordered built-ins by name]

**Not in this plan:** reading `www.rijksmuseum.nl` object pages (their URLs now carry
a title slug and a hash, not the object number; a pasted old-style
`/en/collection/SK-C-5` could be mapped by `objectNumber` later); objects beyond the
first `shows`; a pixel ceiling on single-request fetches (a backlog item: Getty's
and Yale's direct fetches are bounded only by `MAX_IMAGE_BYTES`).

## Status

- [x] Chunk 01: The `rijksmuseum` plugin, its records and the live check

### Chunk 01: The `rijksmuseum` plugin, its records and the live check

**Exposed API:** a new built-in source plugin, `rijksmuseum`. No interface or route change.

Done when:

- `arrt/src/arrt/library/sources/rijksmuseum.py`: finder, reader, `claims`,
  `PLUGIN`, importing nothing from `arrt` but `arrt.library.sources`.
- `claims` accepts `id.rijksmuseum.nl/<7–9 digits>` over http and https, and
  refuses another host, a look-alike host, `data.rijksmuseum.nl`, a `www` page, a
  number of the wrong length, a query, a fragment, a port and credentials.
- Recorded answers under `arrt/tests/fixtures/rijksmuseum/` drive the real client:
  *The Milkmaid* through its item (public domain, 24 MP → tiled); van der Elsken
  (`InC`, 10.6 MP → one request, "niet downloadbaar" still found); Appel (assigned
  and signed → "Karel Appel"); *Samson and Delilah* (attributed → "attributed to
  Rembrandt van Rijn"); *The Adoration of the Magi* (anonymous → None); Sluijters'
  poster (two parts, the first reported); a Dutch-only title; an object with no image
  (holds nothing); a number the museum does not know (400, holds nothing); an access
  point or service on another host (refused); a search by artist and title; the
  accent retry (Isaac Israëls → Isaac Israels); a work with no artist and no
  record (unanswerable); another artist's object refused by the identity check
  through phase 2; the Night Watch read as tiles.
- `arrt/tests/live/test_rijksmuseum_shapes_are_still_real.py` under `live_museum`,
  run once.
- Every place that enumerates the built-ins names `rijksmuseum` (entry point,
  module list, persistence-boundary allowlist, startup lines, live roster, docs,
  security model).
- Records: `linked-art-findings.md` § The Rijksmuseum; `docs/source-plugins.md`;
  `security-model.md`; the change-log with `scope=rijksmuseum-source`; #226 updated.

- **Critic mode:** chunk (the one boundary review)
