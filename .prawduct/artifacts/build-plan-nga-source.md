---
artifact: build-plan
version: 1
scope: nga-source
branch: feature/nga-source
partition: serial — one builder: one contract addition (interface 1.2), one plugin module and their records. Shares no file with the curation UI work running beside it
depends_on:
  - artifact: source-plugins
governed_by:
  - artifact: source-plugins
    dispositions:
      - "§ Versioning and errors → conforms: 1.2 adds one optional field, `SourceContext.data_dir`, so a plugin written for 1.0 or 1.1 loads unchanged; `nga` imports only `arrt.library.sources`"
      - "§ What a finder or reader must report → conforms: title and artist are NGA's own (its open data's `title` and `attribution`); the size is the original's for an image served in full, and the capped service's for one that is not; rights recorded from `openaccess`, never a filter"
      - "§ Which plugin reads a URL → conforms: `nga` claims NGA's artwork pages in the shapes Wikidata records, and nothing else"
      - "Arrt decides storage, so a plugin writes nothing → amended: a plugin may keep what it can fetch again in its own directory under `ART_ROOT/sources/`, which is not backed up; `nga` is the first, with the owner's bounds (decision below)"
  - artifact: project-preferences
    dispositions:
      - "A source that reads pages treats a page it does not recognise as could-not-be-asked → conforms: a download that is not the CSV expected is a failed refresh, and yesterday's file stands"
      - "Identity is never a source URL → conforms: the page URL is a source attribute; identity stays the work's"
      - "Testing strategies → conforms: the network and the clock are doubled; the live half is `live_museum`"
  - artifact: data-model
    dispositions:
      - "Invariant 13, rights gate nothing → conforms: an image NGA serves capped is found and offered as a placeholder; `openaccess=0` is recorded unknown, never in copyright"
last_validated: null
lifecycle: active
---

# Build Plan — NGA, through its open data's catalogue

## What this plan is

arrt#234. `nga-api-findings.md` (this branch's first commit) measured that no NGA
interface turns an object ID into its image without the open data's
`published_images.csv` or the artwork's web page. **The owner ruled on
2026-10-06**: build the public plugin around the CSV, and bound its lifetime:

- the downloaded file is kept on disk, gzipped, under the deployment's data area;
- it is refreshed at most once a day, with a conditional request, so a 304
  downloads nothing;
- it is parsed into memory only when a query asks NGA, and released after
  **6 hours with no NGA query**. A month with no searches costs no memory and no
  downloads.

Also settled by the findings and the ruling: full-size images come through the
tiles; the capped (900 px) service is the placeholder, and only its stated size
is trusted; rights come from `openaccess`, `maxpixels` deciding whether an image
is capped, and `openaccess=0` is unknown, never in copyright; the finder works by
the item's NGA artwork ID (P4683).

Measured beyond the findings, 2026-10-06 (added to `nga-api-findings.md`):

- `published_images.csv` has no title and no artist. The identity check needs
  the holder's own words for both (`FoundImage.title` is required, and the artist
  is compared even on a link). **`objects.csv` carries them** (`title`,
  `attribution`, e.g. `Two Women at a Window`, `Bartolomé Esteban Murillo`): 16.5
  MB gzipped on the wire (82 MB raw), 2 s, 146,099 rows.
- An index of every object with a primary image, its title and attribution,
  measured at about 38 MB for each file's half: about 80 MB while warm.

## Requirements Confidence

**High** for the plugin, given the ruling. **Medium** for one extension of it,
which the owner should confirm (the first decision below).

- [DECISION: **the plugin keeps two of NGA's files, not one**: `published_images.csv` (image, size, cap, rights) and `objects.csv` (title and attribution), each under the ruling's bounds, joined in memory when warm | the ruling named the image file; without the second, every NGA image would carry no title of NGA's own and no artist to compare, and a title invented from Wikidata would make the identity check compare Wikidata against itself. Both are the same open data, CC0, refreshed by the same rule. The owner can narrow it | agent's, extending the owner's ruling]
- [DECISION: **interface 1.2 adds `SourceContext.data_dir: Path | None`**, the plugin's own directory, `ART_ROOT/sources/<plugin name>/`. The loader narrows one root to each plugin's name, so no plugin is handed another's directory; a name that is not one plain path segment gets `None`. It may not exist yet, and the plugin creates it. It holds only what the plugin can fetch again, so it is not backed up. A plugin built against 1.0 or 1.1 never reads it | the smallest additive change: one optional field, a minor version, nothing an existing plugin must do. A path rather than a store API, because a plugin is trusted code with Arrt's own access (`security-model.md` § Source plugins) and the contract's job is to say where, not to police | agent's]
- [DECISION: `nga` declines with no `data_dir` (an Arrt older than 1.2, or a context built without one). With no registry it offers its reader alone, as `navigart` does | the reader needs the catalogue copy as much as the finder does | agent's]
- [DECISION: the files are stored gzipped exactly as the host serves them (`Content-Encoding: gzip`, written raw), or compressed by the plugin when the host sends them plain. A download is accepted only when its header names the columns read, else it is a failed refresh. Each is written to a temporary file and renamed into place, so a reader never sees half a file | agent's]
- [DECISION: "at most once a day" is per file, counted from the last attempt, whatever its outcome. A failed attempt keeps the file it has, and is not retried until the next day. With no file at all, a failed attempt is could-not-be-asked, and the next query tries again | the ruling, and a failure must not cost a download per work | agent's]
- [DECISION: the copy is checked for its day's refresh when a query asks NGA, so a warm copy is refreshed too, and re-parsed only when a file changed. An idle timer releases it: armed on each load, it releases the index once 6 hours have passed since the last query, else re-arms for the remainder. The clock and the timer are injected | agent's]
- [DECISION: claims: `www.nga.gov/collection/art-object-page.<id>.html` (P4683's preferred formatter), `www.nga.gov/content/ngaweb/Collection/art-object-page.<id>.html` (its other formatter; 127 P973 links), http or https, and the new site's `www.nga.gov/artworks/<id>-<words>`. Not provenance or artist pages | counted in the findings | agent's]
- [DECISION: an image with no `maxpixels` → `FetchLocator.tiles("https://api.nga.gov/iiif/<uuid>/info.json")`, reported at the CSV's width × height (equal to `info.json`'s, measured), as `DEZOOMIFY`. An image with `maxpixels` → `FetchLocator.direct("https://api.nga.gov/iiif/<uuid>__<maxpixels>/full/full/0/default.jpg")`, reported at the original's size scaled so its long side is `maxpixels` (887 × 900 and 895 × 900 computed, both equal to the capped service's `info.json`, measured), as `DIRECT_HTTP`. Nothing is asked at a size above that | the owner's ruling: the capped service's stated size is the only one trusted, since it upscales whatever is asked | agent's]
- [DECISION: the artist is `attribution` as NGA writes it, whitespace collapsed. About a quarter of NGA's attributions do not match Wikidata's creator label under the identity check's exact key (`Rembrandt van Rijn` against `Rembrandt`; 9,377 of 39,873 measured), and those are refused on the artist. That is #245's subject (the owner's first item), not this plugin's to work around | agent's]
- [ASSUMPTION: GitHub's raw host stays where the open data's README points, and serves the files gzipped with an ETag (measured)]
- [ASSUMPTION: no change to `DEFAULT_SOURCE_ORDER`]

**Not in this plan:** a search for works with no item; alternate images; the
NGA's web pages; a store API for plugin files; backing up `sources/`.

## Status

- [ ] Chunk 01: Interface 1.2's data directory, the `nga` plugin, its records and its live check

### Chunk 01: Interface 1.2's data directory, the `nga` plugin, its records and its live check

**Exposed API:** interface 1.2 (`SourceContext.data_dir`), shown as
`interface_version` on Settings › Sources and `art_discovery(action='source_plugins')`;
a new built-in source plugin `nga`. No route changes.

Done when:

- `plugin.py`: `data_dir`, `API_VERSION = (1, 2)`; `loading.py`: each plugin gets
  `data_root / <name>`, and a name that is not one plain segment gets `None`;
  `__main__` passes `ART_ROOT/sources`; `config.py` names the directory.
- `arrt/src/arrt/library/sources/nga.py`: the catalogue copy, finder, reader,
  `claims`, `PLUGIN`, importing only `arrt.library.sources` and the standard library.
- Tests with an injected clock, timer and fake HTTP: a cold query downloads both
  files and stores them gzipped; a second query within a day asks nothing; a query
  after a day sends `If-None-Match` and `If-Modified-Since`, and a 304 downloads
  nothing and keeps the index; a 200 replaces the file and re-parses; a failed
  refresh (5xx, network error, a body that is not the CSV) keeps yesterday's file
  and its index; no file and a failed refresh is could-not-be-asked; the index is
  released after 6 h with no query and kept while queries come; a restart reads
  the files on disk without downloading.
- Recorded rows (a slice of the real CSVs) drive the finder and reader through
  the real client, with the falsifying members: an object with no image, an
  object with no title row, a capped image, an uncapped non-open image (served in
  full, rights unknown), another artist's object refused by the identity check
  (through phase 2), and an item naming no NGA page.
- `arrt/tests/live/test_nga_shapes_are_still_real.py` under `live_museum`.
- Every place that enumerates the built-ins names `nga` (entry point, module
  list, network allowlist, startup lines, live roster, docs, security model);
  the surface's `interface_version` test reads 1.2.
- Records: `nga-api-findings.md` (the second file, the attribution measure);
  `source-plugins.md` and `docs/source-plugins.md` (1.2, the data directory, and
  the contract line naming `nga` as the first plugin to keep a copy of a holder's
  catalogue, with the owner's bounds); the `ART_ROOT` layout in
  `architecture.md`, `boundary-patterns.md`, `nonfunctional-requirements.md` and
  `operational-spec.md`; `security-model.md`; the change-log with `scope=nga-source`.

- **Critic mode:** chunk (the one boundary review)
