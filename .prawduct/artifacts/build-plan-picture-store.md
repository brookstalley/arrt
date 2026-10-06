---
artifact: build-plan
version: 1
scope: picture-store
branch: feature/picture-store
partition: serial — one builder, two chunks over one store. Runs beside the search plan (client search modules only) and ahead of the look plan, which depends on this store
depends_on:
  - artifact: data-model
governed_by:
  - artifact: data-model
    dispositions:
      - "§ Direction, 'Candidate previews are a third class, and they are disposable' → amended by the owner's norm of 2026-10-06: every picture fetched from outside is kept forever. The disposable-previews paragraphs are rewritten, not deleted silently"
      - "Derived artifacts are regenerated, never transported → conforms: the store is a cache of outside pictures on the server's own disk, never synced, and not in the backup (owner, 2026-10-06)"
  - artifact: security-model
    dispositions:
      - "§ Direction, an outside image comes only from a named host or a checked id → conforms: every byte served is re-encoded JPEG from Arrt's own routes, keyed by server-computed keys"
  - artifact: boundary-patterns
    dispositions:
      - "§ ART_ROOT filesystem contract → amended: `pictures/` joins it"
  - artifact: observability-strategy
    dispositions:
      - "One health panel → conforms: the store's size and file count join it"
last_validated: null
lifecycle: active
---

# Build Plan — Every picture Arrt fetches is kept

## What this plan is

**The owner's norm, 2026-10-06:** "we should persist all thumbnails we ever
get/generate, and use them instead of hitting sources when the ask is only for
thumbnail size." Asked about the details, the owner ruled the same day:

- two sizes are kept, 480 px and 2,048 px on the long edge, so enlarging a scan
  at review stays as sharp as today;
- the store is not in the backup, because it can be rebuilt;
- there is no ceiling, and the health panel shows the store's size and file count.

Today a candidate's preview is the provider's raw bytes in `previews/`, deleted by
`PreviewSweep` once every work naming it is decided (`data-model.md` § Direction),
and re-rendered per request. Bugs #61, #62 and #81 are about that sweep's races.

The look before a Get (`build-plan-look-before-get.md`) depends on this store,
and so does moving Commons and conversation pictures behind Arrt's routes (a third
plan).

The design was drafted by a Plan agent on 2026-10-06 with file:line citations. It
is summarised in the decisions below, and every citation is to be re-checked
against the code at build time.

## Requirements Confidence

**High** for the store; **Medium** for the import (counts on the NAS unmeasured).

- [DECISION: **the norm**, recorded in `data-model.md` § Direction in place of the disposable-previews paragraphs, with a `project-preferences.md` row for its enforcement. Statement: "A picture Arrt fetches from outside is kept forever under `ART_ROOT/pictures/`, re-encoded as JPEG and keyed by its source; an ask of 2,048 px or less is answered from it, never from the source again." Why: fewer requests to museums, faster pages, and pictures that outlive a source going down. Retroactive for previews | the owner's words and rulings; the wording is the agent's]
- [DECISION: **location and shape**: `ART_ROOT/pictures/<2 hex>/<digest>.<tier>.jpg`, tiers `480` and `2048`. Files only, with no catalogue table: rows already carry `provider` and `url`, from which the key is computed. `preview_path` is still written, as the path in the store, so the column and the MCP projections keep their shape | a table would make kept pictures a catalogue class the backup and the derived-artifacts rule must then cover | agent's]
- [DECISION: **the key** is `sha256(provider + "\n" + normalise(image url))`. `normalise` lower-cases the scheme and host, drops default ports, sorts query parameters (dropping none), settles percent-encoding, and keeps the fragment (SMK's collection pages identify the object only in it, `smk.py`); found in build. The key uses the instance's `FoundImage.url`, not its `preview_url`. The same picture at two holders is two keys, and that is accepted (two instances) | agent's]
- [DECISION: **writing**: every picture is re-encoded through `encode_downscaled` with its decompression-bomb guard, quality 82, never enlarged. A source's preview is written at the 2048 tier at its own size if smaller, and the 480 tier is cut from it. Each write goes to its own temporary name, then is renamed. Concurrent asks for one key in-process wait for the first. Stray temporary files are removed at startup, which is the store's only deletion | `thumbnails.py`'s atomic write is the precedent; `PreviewCache`'s single shared `.partial` name is not to be copied]
- [DECISION: **"thumbnail size" is a long edge of 2,048 px or less**: every surface that draws a picture of a candidate (the review card 480, MCP inline 400, the enlarged view 2,048) is answered from the store. An ask is served from the smallest tier at or above it; a stored file smaller than its tier is the source's full size and answers larger asks too | owner's tier ruling]
- [DECISION: **only the store calls `fetch_preview`**. `PreviewCache` becomes a client of it (look first, fetch on a miss, write), and a static test fails if any other module under `arrt/src` calls a plugin's `fetch_preview` | agent's]
- [DECISION: **import, retroactively**: at startup, each file in `previews/` that a row names is imported under that row's (provider, url) key. The import is idempotent, and `preview_path` is rewritten to the store path. Files no row names are imported nowhere and left in place; the operator removes `previews/` by hand once the import reports done. `thumbs/` is not imported: it is derived from held masters and never touches a source | agent's; owner can ask for `previews/` to be removed automatically]
- [DECISION: **the sweep is retired**: `PreviewSweep`, `PREVIEW_SWEEP_INTERVAL_SECONDS` and its default go. Before deleting the setting, grep `tools/`, `scripts/`, `deploy/`, `.env.example` and the homelab-facing docs for it (core.md) | the norm]
- [DECISION: **backup excludes `pictures/`**, asserted by a test | owner's ruling]
- [DECISION: **the health panel** gains the store's size in bytes and its file count, on HTTP and MCP with the same names, computed by a walk cached for 10 minutes | owner's ruling; the walk's cost is bounded]
- [ASSUMPTION: thumbnails of held works (`thumbs/`) and #116 are out of scope]
- [ASSUMPTION: about 180 KB at 2048 and 35 KB at 480 per picture: an estimate the builder measures on fixtures and records. Measured in build, on synthetic sources: about 100 to 140 KB at 2048 and 33 KB at 480 for previews of 843 to 1,200 px; the figures are in `change-log.md`, scope `picture-store`]

**Not in this plan:** the look (`build-plan-look-before-get.md`); Commons list
pictures and conversation samples moving behind Arrt's routes (a third plan, which
also settles #218's browser half).

## Status

- [x] Chunk 01: The store, the norm, previews through it, and the import
- [ ] Chunk 02: The sweep retired, the store on the health panel, and the bugs it closes

### Chunk 01: The store, the norm, previews through it, and the import

**Exposed API:** none outward. `GET /api/candidate-images/{id}/preview` and
`art_review` previews answer the same, now from the store.

Done when:

- `arrt/src/arrt/library/services/pictures.py` (`PictureStore`): key, tiers,
  get, and put-by-fetching, with the rules above. Unit tests:
  - key normalisation, with two spellings giving one key;
  - tier choice, including a small source answering a larger ask;
  - re-encoding, with a non-image refused and a decompression bomb refused;
  - the atomic write, and two concurrent asks making one fetch;
  - startup clean-up of temporary files only;
  - nothing ever deleted otherwise.
- **`PreviewCache` and the review routes read and write through the store.** A
  second record of the same image makes no fetch, tested through the phase-two
  caller with a counting finder.
- **The static test:** only `pictures.py` calls `fetch_preview`. See it fail on a
  planted call.
- **The import:** idempotent, rewrites `preview_path`, and reports counts in a log
  line. Tested on a fixture art root with a named file, an unnamed file, and a row
  whose file is missing.
- **Records:**
  - `data-model.md` § Direction (the norm, replacing the disposable paragraphs,
    dated, with retroactivity);
  - `project-preferences.md` (the norm's row);
  - `boundary-patterns.md` § ART_ROOT (`pictures/`);
  - `security-model.md` (re-encoding, and keys never from the client);
  - a change-log entry `scope=picture-store`.
- **The measured bytes** per picture at each tier, recorded in the plan's records.
- **Critic mode:** chunk

### Chunk 02: The sweep retired, the store on the health panel, and the bugs it closes

**Exposed API:** `GET /api/health` and its MCP twin gain the store's
`pictures_bytes` and `pictures_files`.

Done when:

- `PreviewSweep`, its scheduling, `PREVIEW_SWEEP_INTERVAL_SECONDS` and its default
  are removed, and the grep for consumers comes back empty (tools, scripts, deploy,
  `.env.example`, docs). The tests that asserted the sweep's behaviour are retired
  with the change-log naming each one and the norm that retired it.
- **The health panel** shows the size and the count, on HTTP, MCP and in
  `health.js`, with a parity test and a browser test.
- **A test asserts the backup does not carry `pictures/`.**
- An operator-verification entry: after deploy, the import's log line, the health
  panel's numbers, and a review card's picture loading with no source asked.
- **Backlog, closed at merge** through `/prawduct:backlog`: #61 and #81 (nothing
  deletes a preview any more) and #62 (a file no row names is kept on purpose).
  Each close says why.
- **Critic mode:** cumulative (the boundary review covers both chunks)
