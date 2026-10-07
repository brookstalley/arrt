---
artifact: build-plan
version: 1
scope: getty-source
branch: feature/getty-source
partition: serial — one builder, one plugin module and its records. Runs beside the private Whitney reader (arrt-sources#11), delegated in another repository's worktree, which shares no file with this one
depends_on:
  - artifact: source-plugins
governed_by:
  - artifact: source-plugins
    dispositions:
      - "§ Versioning and errors → conforms: `getty` imports only `arrt.library.sources` (and `httpx`), and uses interface 1.3's IIIF parsers; no interface change"
      - "§ What a finder or reader must report → conforms: title and artist are Getty's own (a title Getty records, the producer's name with Getty's attribution prefix); dimensions are the original's; rights recorded from the manifest's `rights`, never a filter"
      - "§ Which plugin reads a URL → conforms: `getty` claims `www.getty.edu/art/collection/object/<slug>`, the shape Wikidata's formatter builds, and nothing else"
      - "§ Trust → conforms: `media.getty.edu` answers robots.txt with 503; the owner's ruling of 2026-10-07 lets a plugin make single, human-led requests there"
  - artifact: project-preferences
    dispositions:
      - "A source that reads pages treats a page it does not recognise as could-not-be-asked → conforms: a record, manifest or `info.json` not of the shape expected is `ImageSearchFailure`. The plugin reads no web page at all"
      - "Identity is never a source URL → conforms: the page URL is a source attribute; identity stays the work's"
      - "Testing strategies → conforms: the network is doubled with recorded answers; the live half is `live_museum`"
  - artifact: data-model
    dispositions:
      - "Invariant 13, rights gate nothing → conforms: in-copyright works are found and offered, at the size served (600 px under Getty's `thumbnail` clearance, in full under `zoom`)"
last_validated: null
---

# Build Plan — Getty through Linked Art, its SPARQL endpoint and IIIF

## What this plan is

arrt#230, the J. Paul Getty Museum. The owner asked for it on 2026-10-07 ("let's
get getty next"), after Yale (#229) shipped interface 1.3's IIIF parsers.

**Measured 2026-10-07** (about 120 requests, user agent `arrt-research/0.1`;
recorded answers in the session scratchpad, copied to `arrt/tests/fixtures/getty/`
by this plan; written up in `linked-art-findings.md` § Getty):

- **Wikidata reaches few Getty works with no image.** 2,596 items carry the
  Getty object ID (P2582), and 30 of them have no P18. Of those 30, 28 have an image at
  the Getty and 2 have none (a bound volume, an armlet). The museum holds 124,301
  objects with images, nearly all of them off Wikidata, so **the finder also
  searches**, as `smk` and `met` do when the item names no page.
- **P2582 is the page's slug** (`103JNH`, six characters `[0-9A-Z]` on all 2,596).
  The page is `https://www.getty.edu/art/collection/object/<slug>`, a JavaScript
  shell. Each Linked Art record carries the slug as an identifier,
  `urn:getty-local:idm:object:slug/<slug>`, so **one query to the SPARQL endpoint**
  (`data.getty.edu/museum/collection/sparql`) maps any number of slugs to records:
  30 slugs in 0.22 s. No page is read.
- **The search.** The endpoint has no text index (`bds:search` answers nothing). A
  case-insensitive scan over every title takes 11–14 s. Two short queries do
  the same work: the maker by name, case-insensitively, among 25,611
  `E21_Person`s (0.6 s), then that maker's objects whose titles contain the title's
  words (0.3 s). *Migrant Mother* is found for "Dorothea Lange", *Irises* for
  "Vincent van Gogh".
- **The record carries the identity**: titles (preferred, primary, translated,
  alternate), the producer (`produced_by.carried_out_by`, or one per
  `produced_by.part` for several makers), Getty's attribution qualifiers in the
  production's "Name Prefix" ("Attributed to" 3,630, "Workshop of" 162, "Follower
  of" 156, "After" 30, …) and "Name Suffix" ("or workshop", "and workshop"; and
  "maker, American", a role and not an attribution), the object's page
  (`subject_of`, `text/html`), and its IIIF manifest (`subject_of`, classified
  "IIIF Manifest", Presentation 2 and 3).
- **Use the record for names, not the manifest.** The manifest's metadata drops every
  non-ASCII letter: "Fédèle Azari" is "Fdle Azari" in its bytes.
- **The image is the manifest's first canvas.** `shows[]` is in no useful order:
  on *Irises* the third is a frame, which is another object, and on *Migrant
  Mother* the first is "Subject Terms", not an image. On both, the manifest's
  first canvas is the view the record's `representation` names as the main one
  ("Front", "Main View"). `representation` is deprecated in the record, so the
  manifest's order is what the plugin relies on.
- **Rights are per object, in the manifest's `rights`**: CC0 on open content, and
  rightsstatements.org `InC` or `InC-RUU` on in-copyright works. They agreed with the
  image's own rights record on all 6 compared. One manifest had none.
- **Sizes.** The `info.json` declares `maxWidth`/`maxHeight` 30,000. `full/max`
  served the original whole on every image asked, read from the JPEG header: 573 × 600
  (Arbus, `thumbnail` clearance), 3,347 × 4,020 (Brockhurst, `zoom`), 4,748 × 6,073
  (Lange), 6,455 × 5,022 (Weston, `zoom`) and 8,409 × 12,441 (Moore, in copyright).
  Getty's clearance decides the master it keeps: of the 28, nine are 600–768 px
  on the long side (eight in copyright, one with no rights stated), and the rest
  3,540–12,448 px.
- **Access.** `data.getty.edu`: no robots.txt (404), no challenge, no rate-limit
  headers. `media.getty.edu`'s robots.txt answers 503 (ruled on 2026-10-07: may be asked).

## Requirements Confidence

**High** for the item road and the image. **Medium** for the search: it is a new
shape (SPARQL), measured on a handful of names.

- [DECISION: a built-in plugin `getty`, `arrt/src/arrt/library/sources/getty.py`.
  The finder reads the item's `pages_about` for Getty object pages and maps
  their slugs in one SPARQL query. When the item names none, or has no QID, it
  searches. The reader maps a page's slug to its record, its record to its v3
  manifest, and the first canvas to its image service, and never fetches the page
  | an open record, endpoint and image service belong in the public repository |
  agent's]
- [DECISION: **the search needs the artist.** A work with no artist, and no Getty
  page on its item, is `ImageQueryUnanswerable` | the scan by title alone takes
  11–14 s, against a 20 s read timeout, and it matches across the whole
  collection ("Emigrant Mother" by another hand). The maker's name narrows it to
  one person's objects | agent's]
- [DECISION: the maker is matched by Getty's person label, case-insensitively and
  otherwise exactly. Accents, initials and spellings are not matched ("Gerald
  Leslie Brockhurst" against Getty's "Gerald L. Brockhurst") | the identity check
  above the seam compares names the same strict way, so a looser search would
  find objects it then refuses. ULAN equivalents link 4,716 of 25,611 persons. A
  ULAN road, from the work's creator's P245, waits for a case that needs it |
  agent's]
- [DECISION: the title matches when every word of the query's title, lowercased,
  is contained in one of the object's titles. At most ten objects are read |
  `smk`'s word rule; the identity check decides what survives | agent's]
- [DECISION: **a search hit's reported title is the object's title equal to the
  query's, ignoring case and spacing, where one is; else Getty's preferred title.
  An object found through the item's page reports the preferred title**, since the
  identity check accepts a linked page whatever its title |
  every title in the record is Getty's own, and the identity check compares one
  title. Getty prefers the original language ("La Ville") and records the
  translation ("The City") | agent's]
- [DECISION: the reported artist is the first producer's name. For several makers
  that is the first `part`. Getty's name prefix goes before it ("Attributed to
  Rembrandt"), and a suffix that is not a "maker…" role goes after it ("Peter Paul
  Rubens and workshop"). "Unknown" is None | a copy after or a workshop work is
  not the master's, and the identity check should be told so, as `yale` does.
  Several makers (#257) are reported as Getty orders them | agent's]
- [DECISION: rights from the manifest's `rights`. `creativecommons.org/publicdomain/zero/`
  → `PUBLIC_DOMAIN`; `rightsstatements.org/vocab/InC`, with any `-` suffixes
  (`InC-RUU`, `InC-OW-EU`) → `IN_COPYRIGHT`; anything else, absence included →
  `UNKNOWN` | measured per object,
  6 of 6 agreeing with the image's record | agent's]
- [DECISION: `direct_max_side = 30000`, Getty's own declared `maxWidth`/`maxHeight` |
  unlike Yale, Getty declares a cap, and served every size asked whole, up to
  12,441 px. Arrt bounds a direct fetch at 512 MB | agent's]
- [DECISION: the finder reports the first canvas's width × height, and the reader reads
  `info.json` to choose the locator | as for Yale: the canvas size equalled
  `info.json`'s and the served size on all 5 measured | agent's]
- [DECISION: hosts. SPARQL and records on `data.getty.edu`, manifests and
  images on `media.getty.edu` under `/iiif/manifest/3/` and `/iiif/image/`. No
  redirect is followed. A record whose manifest or service is elsewhere is
  could-not-be-asked | the house rule | agent's]
- [DECISION: a slug the endpoint maps to no record, a record with no manifest,
  and a manifest with no canvas hold nothing. HTTP 403, 429 or 5xx, network
  errors, and a body not of the measured shape are could-not-be-asked | as `yale`
  | agent's]
- [DECISION: a search hit is reported under its record's `subject_of` page, and
  skipped with a warning when that page is not the shape the reader claims | the
  reader must be able to read back what the finder reports, as `smk` does | agent's]
- [ASSUMPTION: the Getty publishes no rate limit and none was met; one request at a time, unpaced, as `yale` and `smk`]
- [ASSUMPTION: no change to `DEFAULT_SOURCE_ORDER`]

**Not in this plan:** the older `/art/collection/objects/<TMS id>/` pages (P973,
a few dozen items with no P18; the record carries the TMS ID, so a later reader
can map them); a ULAN road; canvases after the first; the Getty Research Institute's
archives (#230's scope-out); the Rijksmuseum (#226).

## Status

- [x] Chunk 01: The `getty` plugin, its records and the live check

### Chunk 01: The `getty` plugin, its records and the live check

**Exposed API:** a new built-in source plugin, `getty`. No interface or route change.

Done when:

- `arrt/src/arrt/library/sources/getty.py`: finder, reader, `claims`, `PLUGIN`,
  importing nothing from `arrt` but `arrt.library.sources`.
- `claims` accepts the page shape over http and https (trailing slash allowed), and
  refuses another host, an `/objects/<n>/` page, an exhibition or person page, a
  slug of the wrong shape, and a look-alike host.
- Recorded answers under `arrt/tests/fixtures/getty/` drive the real client:
  *Irises* (public domain, three canvases, the first taken; `CC0`); Brockhurst
  (`InC`, in full, under a slug the item spells); Arbus (`InC`, 600 px, still
  found); Cariani (no `rights` → `UNKNOWN`); *Rocky Bear* (two makers in `part`,
  the first reported); a prefixed maker ("Attributed to …"), reported with the
  prefix; *La Ville* found by "The City", the translated title reported; a
  record with no manifest (holds nothing); a slug the endpoint does not know
  (holds nothing); a manifest or service on another host (refused); a search
  by artist and title; a work with no artist and no page (unanswerable); another
  artist's object refused by the identity check through phase 2. The page is
  reported as the item spells it, and the link identifies it through the caller.
- `arrt/tests/live/test_getty_shapes_are_still_real.py` under `live_museum`,
  run once.
- Every place that enumerates the built-ins names `getty` (where `yale` is
  listed: entry point, module list, network allowlist, startup lines, live roster,
  docs, security model).
- Records: `linked-art-findings.md` § Getty; `docs/source-plugins.md` (the built-ins
  list and examples table); `security-model.md`; the change-log with
  `scope=getty-source`; #230 updated.

- **Critic mode:** chunk (the one boundary review)
