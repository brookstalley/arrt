---
artifact: build-plan
version: 1
scope: yale-source
branch: feature/linked-art-yale
partition: serial — one builder, one contract addition (interface 1.3), one plugin module and their records. Runs beside the private Philadelphia reader, which is another repository's work and shares no file with this one
depends_on:
  - artifact: source-plugins
governed_by:
  - artifact: source-plugins
    dispositions:
      - "§ Versioning and errors → conforms: 1.3 adds parsing helpers to `arrt.library.sources` and nothing a plugin must use, so a plugin written for 1.0–1.2 loads unchanged; `yale` imports only `arrt.library.sources`"
      - "§ What a finder or reader must report → conforms: title and artist are Yale's own (its manifest's `Title` and creator lines); dimensions are the original's; rights recorded from the canvas's own `Image Use Rights`, never a filter"
      - "§ Which plugin reads a URL → conforms: `yale` claims YUAG's and YCBA's object pages in the shapes Wikidata's formatters build, and nothing else"
      - "§ Not in version 1, readers for new protocols → partly answered: IIIF parsing becomes part of the interface; a general IIIF *reader* (claiming any IIIF URL) is still not built"
  - artifact: project-preferences
    dispositions:
      - "A source that reads pages treats a page it does not recognise as could-not-be-asked → conforms: a manifest or `info.json` not of the shape expected is `ImageSearchFailure`"
      - "Identity is never a source URL → conforms: the page URL is a source attribute; identity stays the work's"
      - "Testing strategies → conforms: the network is doubled with recorded answers; the live half is `live_museum`"
  - artifact: data-model
    dispositions:
      - "Invariant 13, rights gate nothing → conforms: Yale's in-copyright works, served at 480 px, are found and offered as placeholders (the owner's ruling of 2026-10-03)"
last_validated: null
---

# Build Plan — a shared IIIF helper (interface 1.3), and Yale through its manifests

## What this plan is

arrt#242 (the shared helper, approved 2026-10-06) with its first consumer, arrt#229
(Yale: the Yale University Art Gallery and the Yale Center for British Art). The
owner asked on 2026-10-07 for the next public plugin. On the same day they ruled
that #233 Paris Musées is demoted, not dropped, so the Linked Art group is next,
and #242 blocks it.

**Measured 2026-10-07** (about 110 requests; recorded answers in the session
scratchpad, copied to `arrt/tests/fixtures/` by this plan; written up in a new
`linked-art-findings.md`):

- **The three museums share only the last step.** Yale goes object → IIIF
  Presentation 3 manifest → canvas → Image API 2 service. The Rijksmuseum goes
  object → VisualItem → DigitalObject → an image URL on `iiif.micr.io`, which
  is Image API 3, with three dereferences and no manifest. Getty goes object →
  media VisualItem → access point (Image API 3), or through a deprecated
  `representation`, or through manifests. Each image service is on a different
  host from its record. What all three share is reading an image service's
  `info.json` for the original's size and declared caps, and choosing between
  one direct request and tiles.
- **Caps.** Rijksmuseum `info.json` declares `maxArea: 17550000`, which confirms
  #226's 17.5 MP. Getty declares `maxWidth`/`maxHeight` 30000. Yale declares
  none, but `full/full` on a 46,800 × 34,053 YCBA canvas answers HTTP 500. Its
  14,484 × 9,741 canvas (the Dort) and 7,408 × 5,848 (*The Night Café*) are
  served in full by one request.
- **Yale needs no Linked Art and no LUX.** Wikidata's YUAG ID (P8583) and YCBA
  Lido ID (P9789) have formatters `artgallery.yale.edu/collections/objects/$1`
  and `collections.britishart.yale.edu/catalog/tms:$1`, which
  `Registry.pages_about` already returns. The manifest is
  `manifests.collections.yale.edu/{yuag|ycba}/obj/<id>`, which needs no LUX call.
  Of the YUAG 2D items with no P18, 4,053 of 4,068 carry an ID. YCBA's gap is
  392, and only 3 of those carry one.
- **The manifest carries the rest.** It holds `Title`, the creator
  (`Creator(s)`: "Artist: Vincent van Gogh (Dutch, …)" at YUAG; `Creator`:
  "Joseph Mallord William Turner, born in London, …" at YCBA), the canvas size,
  the image service, and each canvas's `Image Use Rights`. The manifest-level
  `rights` is CC0 on every manifest, Rothko's included: it licenses the
  metadata, not the image.
- **Most works with no image on Wikidata are served at 480 px.** In a random
  draw of 25 YUAG items with no P18, 2 had no manifest (404), 18 were 480 px
  (public domain and in copyright alike), and 5 were served in full (2,255 to
  9,143 px). Every in-copyright work seen was 480 px (Rothko, de Kooning, Albers,
  Gottlieb, Hopper's *Rooms by the Sea*). "Copyright Not Evaluated" (Hopper's
  *Sunlight in a Cafeteria*) is served in full. So about one in five fills the gap
  at full size (e), and the rest are placeholders under the 2026-10-03 ruling.
- **Access.** Object pages: 403, Cloudflare challenge. Manifests and images:
  200, no challenge, no rate-limit headers. `manifests.` has no robots.txt
  (404); `images.`'s is empty.

## Requirements Confidence

**High** for Yale. **Medium** for the helper's long-term shape, because only one
consumer is built here.

- [DECISION: **#242 is narrowed from a "Linked Art → IIIF" helper to a IIIF
  helper.** The Linked Art walks stay in each plugin. This is a descope of
  #242's proposed change ("one helper that a plugin calls with a Linked Art
  object"), stated here and on the issue rather than dropped. | measured: the
  three walks share no step before the image service, and Yale has no Linked
  Art step at all. A shared walk would be three walks behind one name | agent's;
  the owner approved a shared helper, and this is the part the measurement
  shows is shared]
- [DECISION: **interface 1.3 adds a module `arrt.library.sources.iiif` of pure
  parsers**, re-exported from `arrt.library.sources`:
  `ImageService.from_info(info_json)`, which reads Image API 2 or 3 into its id,
  version, full width and height, and declared `maxWidth`/`maxHeight`/`maxArea`;
  `ImageService.locator(*, direct_max_side)`, which gives
  `FetchLocator.direct(<full size URL>)` (v2 `full/full`, v3 `full/max`) when
  nothing is declared below the full size and the long side is at most
  `direct_max_side`, and `FetchLocator.tiles(<id>/info.json)` otherwise; and
  `manifest_images(manifest)`, the image service, size and label of each canvas
  of a Presentation 2 or 3 manifest. **No I/O**: each plugin fetches with its own
  bounded client and hosts. | Arrt checks the locator's address, not the
  plugin's own requests (`docs/source-plugins.md` § What Arrt does), so a helper
  that fetched would be a request policy in the interface. Parsing alone adds no
  network surface | agent's]
- [DECISION: `direct_max_side` is the caller's, with no default | the one
  undeclared cap seen is Yale's, and another server's will differ; a default
  would be a number nobody measured for that server | agent's]
- [DECISION: `yale` uses `direct_max_side = 16384` | the largest full request
  measured to succeed was 14,484 px and the smallest to fail 46,800; 16,384 is
  the next power of two above the success and well below the failure. A direct
  fetch keeps the original (Arrt bounds it at 512 MB), where tiles assemble at
  most 8,192 px per side and cost hundreds of requests | agent's]
- [DECISION: a built-in plugin `yale`, `arrt/src/arrt/library/sources/yale.py`.
  The finder reads the item's `pages_about` for the two page shapes and reports
  each image under the page exactly as the item spells it. The reader maps a page
  to its manifest and never fetches the page. With no registry it offers its
  reader alone, as `navigart` does | an open, unchallenged image service belongs
  in the public repository; the page is challenged, but the plugin never reads
  it | agent's]
- [DECISION: **LUX search is not built.** A work with no QID, or an item naming
  no Yale page, is not answerable by `yale` (`ImageQueryUnanswerable` for no
  QID, empty otherwise) | #229 proposed "a finder on LUX's Linked Art search",
  but the IDs reach 4,053 of YUAG's 4,068 imageless items. LUX's nested name
  search answered 0 in four attempts. LUX's YCBA records carry no Wikidata
  equivalent | agent's; a descope of #229's proposed finder, recorded on the
  issue]
- [DECISION: the image is the **first canvas** | the Dort's first canvas is
  "recto, cropped to image"; later canvases are other views. A rule for choosing
  among views waits for a case that needs one | agent's]
- [DECISION: rights come from the first canvas's `Image Use Rights`. "No
  Copyright - United States" and the CC0 text → `PUBLIC_DOMAIN`; "In Copyright" →
  `IN_COPYRIGHT`; anything else, "Copyright Not Evaluated" included → `UNKNOWN`.
  The manifest-level `rights` is never read as the image's | measured: CC0 on
  every manifest, in-copyright ones included | agent's]
- [DECISION: the finder reports the canvas's width × height. The reader reads
  `info.json` to choose the locator | the canvas size equalled `info.json`'s and
  the served `full/full` size on every image measured (4 of 4, read from JPEG
  headers). A finder that read `info.json` too would cost a second request per
  work for no difference measured | agent's]
- [DECISION: an ID that answers 404 at the manifest host → holds nothing (as
  for YUAG 90363, an object with no image); 403, 429, 5xx, network errors, a body
  that is not a Presentation manifest, or a canvas whose image is not IIIF →
  could-not-be-asked. An image service off `images.collections.yale.edu` is
  refused (could-not-be-asked) | the house rule, and the plugin asks only Yale's
  hosts | agent's]
- [DECISION: P4738 (YCBA VuFind) pages are not claimed | measured: the VuFind
  number does not map to a manifest | agent's]
- [ASSUMPTION: Yale publishes no rate limit and none was met in about 45 requests; the plugin asks one request at a time, unpaced, as `smk` does. A finder reads one manifest per page, at most ten]
- [ASSUMPTION: no change to `DEFAULT_SOURCE_ORDER`]
- [ASSUMPTION: the existing IIIF readers (`artic`, `nga`, `smk`) are not moved onto the helper here. Each hard-codes a measured, holder-specific rule; moving them is a refactor with its own review, for when a fourth consumer shows the helper's shape holds]

**Not in this plan:** the Rijksmuseum (#226) and Getty (#230) plugins; LUX search;
Linked Art parsing; YCBA works reachable only by VuFind number; canvases after the
first; a IIIF reader claiming arbitrary IIIF URLs.

**Found while measuring, for the owner (recorded on the issues, not ruled here):**
`iiif.micr.io`, the Rijksmuseum's image host, has robots.txt `Disallow: /` for
every agent (#226). `media.getty.edu` answers robots.txt with 503, which RFC 9309
reads as disallow-all (#230).

## Status

- [x] Chunk 01: Interface 1.3's IIIF helper, the `yale` plugin, their records and the live check

### Chunk 01: Interface 1.3's IIIF helper, the `yale` plugin, their records and the live check

**Exposed API:** interface 1.3 (`arrt.library.sources` gains `ImageService` and
`manifest_images`), shown as `interface_version` on Settings › Sources and
`art_discovery(action='source_plugins')`. A new built-in source plugin, `yale`.
No route changes.

Done when:

- `arrt/src/arrt/library/sources/iiif.py`, re-exported from `__init__.py`;
  `API_VERSION = (1, 3)` with its line in `plugin.py`.
- The helper is tested on recorded `info.json`s from all three museums: Yale v2,
  no caps; Getty v3, `maxWidth`/`maxHeight` 30000; the Rijksmuseum v3,
  `maxArea` 17,550,000, whose full size exceeds it, so the answer is tiles.
  Falsifying members: a body that is neither version; a v3 `maxWidth` below the
  full width (tiles); a long side above `direct_max_side` (tiles), and at it
  (direct). Manifests: Yale v3 single and multi-canvas, a v2 manifest (YCBA's
  `/v2/` or Getty's), a canvas whose body has no service (not IIIF), and a
  manifest with no canvases.
- `arrt/src/arrt/library/sources/yale.py`: finder, reader, `claims`, `PLUGIN`,
  importing nothing from `arrt` but `arrt.library.sources` (and `httpx`, as `smk` and `nga` do).
- `claims` accepts the two page shapes over http and https, and refuses another
  host, a path of another shape, a VuFind page, and a look-alike host
  (`artgallery.yale.edu.example.com`).
- Recorded answers under `arrt/tests/fixtures/yale/` drive the real client:
  *The Night Café* (public domain, in full, direct); the Rothko (in copyright,
  480 px, recorded `IN_COPYRIGHT`, still found); Hopper's *Sunlight* ("Copyright
  Not Evaluated" → `UNKNOWN`); the Dort (YCBA, five canvases, first taken, the
  YCBA creator line); the 46,800 px canvas (tiles); a 404 manifest (holds
  nothing); a service on another host (refused); another artist's object refused
  by the identity check through phase 2. The page is reported as the item
  spells it, and the link identifies it through the caller, not only in the
  plugin.
- `arrt/tests/live/test_yale_shapes_are_still_real.py` under `live_museum`,
  run once.
- Every place that enumerates the built-ins names `yale` (grep for where `nga`
  is listed: entry point, module list, network allowlist, startup lines, live
  roster, docs, security model); the surface's `interface_version` test reads
  1.3.
- Records: `linked-art-findings.md` (new, registered in `project-state.yaml`'s
  `artifact_manifest`); `source-plugins.md` (§ Versioning: 1.3; § Not in version
  1: the IIIF line); `docs/source-plugins.md` (1.3, the built-ins list and
  examples table, and the helper); the change-log with `scope=yale-source`; #242
  and #229 updated with the descopes above; the robots findings on #226 and
  #230.

- **Critic mode:** chunk (the one boundary review)
