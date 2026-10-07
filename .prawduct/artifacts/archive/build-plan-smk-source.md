---
artifact: build-plan
version: 1
scope: smk-source
branch: feature/smk-source
partition: serial — one builder, one plugin module and its records. Runs beside the private Art UK reader, which is another repository's work and shares no file with this one
depends_on:
  - artifact: source-plugins
governed_by:
  - artifact: source-plugins
    dispositions:
      - "§ What a finder or reader must report → conforms: title and artist are SMK's own; dimensions are the original's; rights recorded from SMK's own flag, never a filter"
      - "§ Which plugin reads a URL → conforms: `smk` claims SMK's page and API shapes only; no other installed plugin claims an smk.dk host"
      - "§ Versioning and errors → conforms: imports only `arrt.library.sources`, written for major 1"
  - artifact: project-preferences
    dispositions:
      - "A source that reads pages treats a page it does not recognise as could-not-be-asked → conforms: an API answer that is not the object asked for is `ImageSearchFailure`"
      - "Identity is never a source URL → conforms: the page URL is a source attribute; identity stays the work's"
      - "Testing strategies → conforms: the network is doubled with recorded answers; the live half is `live_museum`"
  - artifact: data-model
    dispositions:
      - "Invariant 13, rights gate nothing → conforms: in-copyright works are found and recorded as such; the owner's ruling of 2026-10-06 on SMK's terms rests on this invariant's household premise"
last_validated: null
lifecycle: completed
archived: 2026-10-07
released_in: v0.4.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — SMK, through its open API

## What this plan is

The owner asked on 2026-10-06 for the next sources by works unlocked, and ruled the
same day that SMK's terms allow its in-copyright images for household use (arrt#232).
SMK (Statens Museum for Kunst, the National Gallery of Denmark) is the only open
API found that serves in-copyright works at full size. Its value is twofold:
Wikidata items of SMK works that have no image, and works in copyright that no
other wired source serves.

**Measured 2026-10-06** (one request each, `arrt-research/0.1`; findings go to a
new `smk-api-findings.md`):

- No key. `https://api.smk.dk/api/v1/art/search/?keys=*&filters=[public_domain:false],[has_image:true]`
  found 14,918 records; `?object_number=KMS1` answers one object.
- An object carries `object_number`, `titles`, `artist`, `production`,
  `public_domain`, `rights`, `image_width`, `image_height`, `image_native` (a
  download URL on `api.smk.dk`), `image_iiif_id` (on `iip.smk.dk`),
  `image_iiif_info`, `frontend_url` (`https://open.smk.dk/artwork/image/<object number>`).
- Sizes: KMS1 7,174 × 5,536 (public domain); two in-copyright samples 6,296 ×
  4,370 and 6,329 × 4,508. The issue's earlier sample download was 10.8 MB.
- Rights: a public-domain object's `rights` is the CC Public Domain Mark; every
  in-copyright sample's is `https://www.smk.dk/section/brug-af-museets-materiale/`,
  SMK's own page saying the work is in copyright (household private use needs no
  permission; the owner's ruling).
- Wikidata: 7,034 items have collection (P195) = SMK (Q671384). 6,883 carry
  "described at URL" (P973) as `https://collection.smk.dk/#/en/detail/<object number>`
  (note the fragment), and 7,006 carry the object number as inventory number (P217).
  There is no SMK ID property. `Registry.pages_about` already yields P973 pages.

## Requirements Confidence

**High** for the finder and reader; the decisions below are the agent's unless marked.

- [DECISION: a built-in plugin `smk` in `arrt/src/arrt/library/sources/smk.py`, entry point in `arrt/pyproject.toml` | an open API with no challenge belongs in the public repository (the owner's rule of 2026-10-03/04: only challenge-passing and museum-page readers are private); built-in as `met` is | agent's]
- [DECISION: finding with a QID reads the item's SMK pages from `pages_about` (any `collection.smk.dk` or `open.smk.dk` page), takes the object number from each, and asks the API for that object. It reports the image under the page exactly as the item spells it, so the link identifies it (`docs/source-plugins.md` § A finder: "an image read from a page the work's Wikidata item records is identified by that link") | SFMOMA's precedent, where reporting the plugin's own spelling refused a true match | agent's]
- [DECISION: an item with no SMK page, or a work with no QID, falls back to the API's search by title, narrowed by the artist when one is known, reading at most ten objects; each is reported under its `frontend_url` and judged by title and artist | the Met's precedent; the cap bounds one work's cost | agent's]
- [DECISION: `claims` accepts `collection.smk.dk` detail pages, `open.smk.dk/artwork/image/<n>` pages, and `api.smk.dk` object URLs, and nothing else. The reader never fetches a page: it parses the object number and asks the API | the pages are a JavaScript front end; the API is the documented interface | agent's]
- [DECISION: the image fetched is the original at `image_width` × `image_height`. Prefer one direct download (`image_native`, or IIIF `full/full`); fall back to the IIIF tiles through Arrt's existing tiled path only if a direct fetch is measured capped below the stated size. The builder measures which, on at least one public-domain and one in-copyright object, and records it in `smk-api-findings.md` | the contract requires the original's size; which URL serves it is a measurement, not a guess | agent's]
- [DECISION: rights — `public_domain` true → `PUBLIC_DOMAIN`; false with `rights` equal to SMK's copyright page, in either language (asked in English, SMK names `https://www.smk.dk/en/section/use-of-smk-material/`; the Danish page is `brug-af-museets-materiale`) → `IN_COPYRIGHT`; anything else → `UNKNOWN` | SMK's own statement, read for what it says; a value never seen is not guessed at | agent's]
- [DECISION: an object with `has_image` false or no image URL is not an image; the object number SMK answers "not found" for skips that page, and the work's search stands; 403, 429, 5xx and network errors fail it as could-not-be-asked | the Met plugin's rule, for the same reasons | agent's]
- [DECISION: `smk` needs no setting and never declines | as `met`; a switch nobody asked for is a setting to document and test | agent's]
- [ASSUMPTION: no collection browse | the issue scopes it out]
- [ASSUMPTION: no change to `DEFAULT_SOURCE_ORDER` | order only breaks ties]
- [ASSUMPTION: SMK publishes no rate limit; the plugin asks one request at a time per work and the builder records any limit found]

**Not in this plan:** browsing SMK's collection; `alternative_images`; 3D files.

## Status

- [x] Chunk 01: The `smk` plugin, its records and its live check

### Chunk 01: The `smk` plugin, its records and its live check

**Exposed API:** a new built-in source plugin `smk` (entry point in
`arrt/pyproject.toml`). No HTTP or MCP surface changes; Settings › Sources lists
it as it lists every plugin.

Done when:

- `arrt/src/arrt/library/sources/smk.py`: finder, reader, `claims`, `PLUGIN`,
  importing only `arrt.library.sources`.
- `claims` accepts the three SMK shapes above and refuses another host, a path of
  another shape, and a look-alike host (`smk.dk.example.com`).
- The fragment page (`https://collection.smk.dk/#/en/detail/KMS8010`) survives
  from `pages_about` to the reported `FoundImage.url` unchanged, and the identity
  check passes it on the link: tested through the caller, not only the plugin.
- Recorded answers under `arrt/tests/fixtures/smk/`; unit tests drive the real
  client through them, with the falsifying members: an object by another artist
  among search hits, an object with no image, an in-copyright object (recorded
  `IN_COPYRIGHT`, still found), an unknown `rights` value (`UNKNOWN`), an image on
  another host (refused), an object number SMK does not know.
- `arrt/tests/live/test_smk_shapes_are_still_real.py` under `live_museum`,
  covering one public-domain and one in-copyright object.
- Records: `smk-api-findings.md` (new, registered in `project-state.yaml`'s
  `artifact_manifest`, which `tests/preferences/test_artifact_manifest.py` holds);
  `docs/source-plugins.md` (the built-ins list); the entry-point test names `smk`;
  the change-log entry with `scope=smk-source`.

- **Critic mode:** chunk (the one boundary review)
