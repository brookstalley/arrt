---
artifact: build-plan
version: 1
scope: navigart-source
branch: feature/navigart-source
partition: serial — one builder, one plugin module and its records. It shares no file with the curation UI work running beside it
depends_on:
  - artifact: source-plugins
governed_by:
  - artifact: source-plugins
    dispositions:
      - "§ What a finder or reader must report → conforms: the title is the holder's own; the artist is the holder's name with its two halves put in reading order (decision below); dimensions are the largest the image host serves, which is the record's stated size; rights recorded, never a filter"
      - "§ Which plugin reads a URL → conforms: `navigart` claims navigart.fr artwork pages of the publications it knows, and the API's artwork URL, only"
      - "§ Versioning and errors → conforms: imports only `arrt.library.sources`, written for major 1"
  - artifact: project-preferences
    dispositions:
      - "A source that reads pages treats a page it does not recognise as could-not-be-asked → conforms: an API answer that is not the artwork asked for is `ImageSearchFailure`"
      - "Identity is never a source URL → conforms: the page URL is a source attribute; identity stays the work's"
      - "Testing strategies → conforms: the network is doubled with recorded answers; the live half is `live_museum`"
  - artifact: data-model
    dispositions:
      - "Invariant 13, rights gate nothing → conforms: in-copyright works are found and recorded as such"
last_validated: null
lifecycle: completed
archived: 2026-10-07
released_in: v0.4.0
maintained: false
---

> **Archived — no longer maintained.** This plan records what was built, not what will be. Do not edit it to reflect later changes; write those where they are true.

# Build Plan — navigart.fr, through its API, as placeholders

## What this plan is

arrt#213. navigart.fr is Videomuseum's collection platform. One host serves
dozens of French public collections, each as a "publication" with its own
"vault" on `api.navigart.fr`. Every image is capped at 1,000 px, which is under
the floor. The owner ruled on 2026-10-05: build it, as placeholders (the ruling
of 2026-10-03 that a small image of a wanted work is worth having until a better
one is found). Upgrade search (#178) replaces them later.

Everything below was measured on 2026-10-06 and is in `navigart-api-findings.md`
(new). In short:

- About 5,258 Wikidata items link a navigart artwork: through five ID properties
  (MAM Paris P6374, MAMCS P12301, Nantes P11945, FNAC P12213, Musée Picasso
  P6358) and through "described at URL" (P973) across about 30 publications.
- `GET https://api.navigart.fr/<vault>/artworks/<id>` answers one record with no
  key. A sample of 256 items across 24 vaults: 228 have an image, 219 of those
  at exactly 1,000 px on the long side, and none over 1,000. 175 of the 228 have
  no P18.
- The API's documentation says publications are public by default, "everyone
  have access to it".
- Corpus rows 6 (FNAC, 1000 × 979, in copyright) and 14 (Grenoble, 777 × 1000,
  public domain) are reached. Row 7 links Paris Musées, not navigart.

## Requirements Confidence

**High**, given the owner's ruling. The decisions below are the agent's unless marked.

- [DECISION: a built-in, public plugin `navigart` | the issue said it "probably belongs in the private sources repo". The owner's rule puts readers of a museum's own *pages* in the private repository, challenged or not (2026-10-04). This plugin reads no page: it reads a documented JSON API whose documentation says publications are public to everyone by default, as SMK's is (`build-plan-smk-source.md`). The owner confirmed it stays public, 2026-10-06 | agent's, ruled by the owner]
- [DECISION: a static table of publication slug → vault, measured from each publication's own front end, decides which pages are claimed and which vault is asked | the vault is not always derivable from the artwork ID: `matisse_lecateau`'s IDs start with 7 and its vault is 701, and vault 7 answers nginx's own 404. A page of a publication not in the table is not claimed, so it stays a sighting, which is what counts towards adding it | agent's]
- [DECISION: `claims` accepts `www.navigart.fr/<known slug>/` artwork pages in the shapes Wikidata records (`/#/artwork/<id>`, `#/artwork/<id>`, `/artwork/<id>`, `/artwork/<words>-<id>`, a fragment query such as `?note=no`, http or https), and `https://api.navigart.fr/<known vault>/artworks/<id>`. Nothing else | the shapes are counted in the findings | agent's]
- [DECISION: the finder finds by the work's Wikidata item only: each page `pages_about` gives that the plugin claims is read through the API and reported under the page exactly as the item spells it. A work with no item, or a deployment with no registry, cannot be asked (`ImageQueryUnanswerable`). Without a registry the plugin provides its reader alone, so that it is not listed as an image source it cannot be | the platform has no search across publications, and the item's link is what identifies the work (`docs/source-plugins.md` § A finder) | agent's]
- [DECISION: the image is `https://images.navigart.fr/1000/<file_name>`, the largest the host serves (measured: other sizes are 100, 200, 300, 400, 600 and 800; 1200, 2000, `full` and `max` are refused). The size reported is the record's `max_width` × `max_height`, which the served file matched on five images, three of them under 1,000. The preview is the 400 px rendering | agent's]
- [DECISION: the artist is the first author whose `type` is not `anonyme`, from `name.notice`, which navigart writes surname first in capitals with any alias in brackets (`TAEUBER-ARP Sophie (TAEUBER Sophie-Henriette, dite)`). The plugin reports it in reading order with the surname in title case (`Sophie Taeuber-Arp`) and drops the bracket. It changes no letter's identity, only order and case | the identity check compares artists by normalised key (`dedup.artist_key`), and `delaunay sonia` never equals `sonia delaunay`, so the holder's spelling as given would refuse every navigart image | agent's]
- [DECISION: rights — `copyright` "Domaine public" → `PUBLIC_DOMAIN`; a value beginning "©" → `IN_COPYRIGHT` ("© droits réservés" included, which names no holder but asserts a right); anything else → `UNKNOWN` | the holder's own statement | agent's]
- [DECISION: a 404 with navigart's own `{"error":"Not found"}` is an artwork the publication does not have, so that page is skipped and the rest of the work's pages stand; any other 404 (nginx's page, for a vault that does not exist), 401, 403, 429, 5xx, a redirect or a network error is could-not-be-asked | the SMK and Met plugins' rule | agent's]
- [DECISION: `navigart` needs no setting and never declines | as `met` and `smk` | agent's]
- [ASSUMPTION: no rate limit was found (about 330 requests over the probe; `Cache-Control: public, max-age: 3600`). The plugin asks one request at a time per work, at most ten artworks per work]
- [ASSUMPTION: no change to `DEFAULT_SOURCE_ORDER` | order only breaks ties]

**Not in this plan:** `query.pages` (navigart pages a web search cited); the
museums' own sites that embed navigart (`mam.paris.fr`, `cnap.fr`); search
within a publication; alternate images; the overlap with Paris Musées for the
Musée d'Art Moderne de Paris (#233), which `navigart-api-findings.md` notes for
that build.

## Status

- [x] Chunk 01: The `navigart` plugin, its records and its live check

### Chunk 01: The `navigart` plugin, its records and its live check

**Exposed API:** a new built-in source plugin `navigart` (entry point in
`arrt/pyproject.toml`). No HTTP or MCP surface changes; Settings › Sources lists
it as it lists every plugin.

Done when:

- `arrt/src/arrt/library/sources/navigart.py`: finder, reader, `claims`,
  `PLUGIN`, importing only `arrt.library.sources`.
- `claims` accepts the shapes above and refuses another host, a look-alike
  host, a publication not in the table, another path, and an ID of the wrong
  form.
- The item's page survives from `pages_about` to the reported `FoundImage.url`
  unchanged, and the identity check passes it on the link with the artist
  matched: tested through phase 2, not only the plugin.
- Recorded answers under `arrt/tests/fixtures/navigart/`; unit tests drive the
  real client through them, with the falsifying members: another artist's
  artwork (refused by the identity check), an artwork with no image, an image
  under 1,000 px (its own size, not 1,000), an anonymous first author, an image
  on another host (refused), an artwork navigart does not have, an unknown vault
  (could not be asked), and the vault that differs from its IDs' prefix.
- `arrt/tests/live/test_navigart_shapes_are_still_real.py` under `live_museum`.
- Every place that enumerates the built-in plugins names `navigart`: the entry
  point test, the module list, the network allowlist, the startup lines, the live
  roster, `docs/source-plugins.md` and `security-model.md`.
- Records: `navigart-api-findings.md` (new, registered in `project-state.yaml`);
  the change-log entry with `scope=navigart-source`.

- **Critic mode:** chunk (the one boundary review)
