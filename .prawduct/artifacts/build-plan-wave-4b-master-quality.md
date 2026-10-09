---
artifact: build-plan
version: 1
scope: wave-4b-master-quality
branch: feature/wave-4b-master-quality
partition: serial — 01 and 02 are one verdict's two halves (02 renders what 01 computes, and its wire values are 01's enum), and 03 edits `preparation.py`, `container.py` and `queue.py`, which 01 also edits
depends_on:
  - artifact: re-architecture
  - artifact: upgrades
  - artifact: data-model
  - artifact: nonfunctional-requirements
governed_by:
  - artifact: data-model
    dispositions:
      - "derived artifacts are regenerated, never transported (in-transition; ruling 2026-09-30) → conforms: 03's master is rendered for no geometry and is content-addressed, which is the ruling's case exactly. The interim rule (no new geometry-specific render is served to a Player) holds: the master has no geometry, and no manifest names it until 4e"
      - "a work is distinct from an image of it, at every stage → conforms: the master is a Rendition of the work's Original, current only while its `source_content_hash` matches that Original's hash, like every other kind"
      - "per-device runtime state never lives in the catalogue → conforms, and more strictly than today: 01 takes the artwork box (a fact about one television) out of every Library service; only the compositor keeps it, until 4g"
  - artifact: architecture
    dispositions:
      - "the manifest and content-addressed media are the only channel → conforms: the master is servable by hash at the existing `GET /media/{hash}`, and no manifest changes in this plan"
      - "operation logic lives only in the service layer → conforms: the verdict is computed by one function in `library/services/`, and HTTP, MCP and the client only render it"
      - "the Library/Programming seam's four norms (in-transition) → conforms: the profile and the master are Library state, and no Programming code is touched. The facade gains no accessor for the master; 4e adds one when Programming first reads it"
  - artifact: nonfunctional-requirements
    dispositions:
      - "§ The mat is geometric, the floor paragraph: the profile 'must land in the same change that removes the panel settings' → departs, recorded as a decision below: it lands in 4b, ahead of 4g's removal"
      - "below the floor, the work is not rejected and the image is not hidden; the curator may select it anyway → conforms: 01 changes what the floor is measured in, not what happens beneath it"
      - "never upscale → conforms: 03's master is never larger than its Original"
  - artifact: accessibility-spec
    dispositions:
      - "norm 2, WCAG 2.1 AA and colour never the sole carrier of state → conforms: 02's badge keeps a glyph and a word for every state, as today"
  - artifact: upgrades
    dispositions:
      - "ruling 1, no cutoff; searches back off by size → conforms: the profile has a minimum and nothing else, and 01 retires every record that still promises a cutoff"
last_validated: null
---

# Build Plan — Wave 4b: the presentation master and the quality profile

## What this plan is

The second of wave 4's seven plans (`re-architecture.md` § Order of work, row
4). Two Library changes that 4c–4g build on, neither of which changes what a
wall shows:

- **The quality profile.** Today the Library judges every scan against an
  artwork box worked out from one television's `TV_PANEL_*` and `MAT_*`
  settings, with a floor in inches. From this plan it judges against a minimum
  in pixels that names no device: 1,000 px on the long edge (the owner,
  2026-10-06). A scan either meets it or does not. `matted_small` goes, because
  it is a judgement about one panel; per-wall adequacy comes back in 4e as
  Programming's comparison against what each Player reports.
- **The presentation master.** One device-independent image per held work:
  the Original, upright, unmatted, long edge capped at 7,680 px. The Player
  composes from it from 4d on. This plan produces it, keeps it current and
  makes it servable; it does not put it in a manifest.

**The owner's rulings for this plan (2026-10-08):** the badge has two states
(nothing shown when a scan meets the minimum, "below minimum" when it does
not, "no size known" when nobody recorded a size), and the *Size on the wall*
facet becomes *Size* with those three choices. The minimum is an environment
setting, `QUALITY_MINIMUM_PX`, with no Settings screen.

**After this plan, only the compositor reads panel geometry.**
`library/acquisition/compose.py` and `preparation.py` keep `ArtworkBox` to draw
today's `tv_display` canvas, and 4g deletes them with the settings.

**Not in this plan:** a manifest naming the master (4e), the Player composing
from it (4d), removing `TV_PANEL_*`, `MAT_*` or `tv_display` (4g), drawing
thumbnails from the master instead of the Original (no plan; the thumbnail is
bounded and cached already), and any upgrade cadence (#178, parked).

## Requirements Confidence

**Level:** Medium

**Why:** What changes is settled by rulings, and the owner chose both of this
plan's open behaviours. What is the builder's: the wire spelling of the new
verdict, how phase two ranks scans with no box, and the master's encoding.
The first is read by MCP clients as well as the browser.

**Open assumptions / unknowns:**
- [ASSUMPTION: the verdict's wire values are `meets_minimum` and `below_minimum`, on HTTP's `fit.verdict`, the `fit` query filter and its facet, and MCP's `display_fit`; the badge words are "meets minimum" (hidden on tiles, as `native` is today) and "below minimum" | MED impact | user can override]
- [ASSUMPTION: `QUALITY_MINIMUM_PX` defaults to 1,000 and must be a positive integer. A `RESOLUTION_FLOOR_INCHES` still set at startup is logged as retired, by name, with the new key it maps to, and is otherwise ignored, so the NAS keeps starting after the upgrade | LOW impact | user can override]
- [ASSUMPTION: the master is generated for every held work, including one below the minimum, because a curator may choose such a scan and the wall then needs an image of it | LOW impact | user can override]

**What would raise confidence:** 01's verdict function and its callers read
against `nonfunctional-requirements.md`'s floor section and `upgrades.md`
ruling 1 before the consumers are rewired.

`[DECISION: the quality profile lands in 4b, ahead of 4g, which removes the panel settings, and not "in the same change" as the NFR asks | that sentence exists so a below-floor scan is never auto-selected silently in the gap between the box leaving and the profile arriving. Landing the profile first leaves no gap at all, and the seven-plan split (the owner, 2026-10-08) puts the Library's half here | the builder's, 2026-10-08; user can veto]`

`[DECISION: phase two ranks scans in two bands, meets the minimum above below it, and within a band by the long edge in pixels, rising until the master's 7,680 cap and level after it | the box coverage it uses today needs the box. The long edge is the measure the minimum, the master's cap and the parked upgrade tiers already share, and a scan larger than the master gains nothing anyone can see | the builder's, 2026-10-08; user can veto]`

`[DECISION: MCP's fit fields change shape: \`renders_at_inches\`, \`rendered_long_edge_inches\` and \`renders_at_pixels\` are retired, and \`display_fit\` takes the two new values. This is a breaking change to result fields, which \`api_versioning_approach\` calls additive-only, so it is announced the way its deprecation policy says: in the tool descriptions and in the change-log, with no compatibility shim | the inch figures describe one television the server will stop knowing about, and the owner already took them out of the browser on 2026-10-02 for that reason. Keeping them in MCP would keep the panel settings alive for an agent's sake | the builder's, 2026-10-08; user can veto]`

`[DECISION: the master is a JPEG at quality 95, the compositor's own setting, upright (EXIF orientation applied) and in sRGB as read, with no ICC conversion, at most 7,680 px on the long edge and never upscaled. It is stored as \`presentation/{artwork_id}.jpg\` under \`ART_ROOT\` and recorded as a Rendition of a new kind, \`presentation_master\` | 7,680 is the cap the Pi 4's compositing budget was measured against (nonfunctional-requirements.md § Performance, 2026-10-04). Quality 95 matches the canvas a Player is shown today, so moving composition to the Player costs no fidelity. \`color.py\` already treats every image as sRGB with no colour management. 03 measures the store's size over the local corpus and records it | the builder's, 2026-10-08; user can veto]`

## Status

- [ ] Chunk 01: The quality profile replaces the artwork box in the Library
- [ ] Chunk 02: Every surface states the two-state verdict
- [ ] Chunk 03: The presentation master

Context: branched from develop after #333.

### Chunk 01: The quality profile replaces the artwork box in the Library

- **Surfaces:** `arrt/src/arrt/config.py` (the new key; the floor and
  `tv_artwork_box`'s floor field retired; the retired-key warning);
  `library/services/display_fit.py` (the profile and the two-value verdict);
  every Library consumer of the box: `selection.py`, `discovery.py`,
  `runner.py` (the collection supplement), `discovery/phase_two.py` (bands and
  within-band), `look.py`, `review.py`, `catalogue.py`, `survey.py`,
  `registry_works.py`; `services/container.py` (binds the profile, not the
  box, to those services); `compose.py` and `preparation.py` stop returning a
  fit and inches; `__main__.py`'s startup log; `.env.example`;
  `arrt/tests/live/test_the_resolution_floor_still_holds.py`.
- **What:** `QualityProfile(minimum_long_edge_px)` and `assess(width, height,
  profile)` → `meets_minimum` | `below_minimum`, and `None` when a size is
  unknown, as today. Every consumer listed takes the profile, and no Library
  service receives an `ArtworkBox`. Phase two ranks as the decision above says.
  The records: `data-model.md` § Quality profile (minimum only; the cutoff
  struck, pointing at `upgrades.md` ruling 1) and its `display_fit` direction
  note; `nonfunctional-requirements.md`'s floor section (the mechanism is now
  pixels; the inch bridge retired); `re-architecture.md`'s two cutoff
  sentences (a dated pointer, not a rewrite); `operational-spec.md`'s setting;
  `procurement-corpus.md` where it names the floor. A grep of the whole repo for
  `RESOLUTION_FLOOR`, `floor_inches`, `artwork box` and `cutoff` closes the
  chunk, with every survivor either changed or named as still true.
- **Tests:** `test_display_fit.py` rewritten for the profile: exactly at the
  minimum meets it, one pixel under does not, a tall narrow work is judged on
  its long edge, a work smaller than the old box but over the minimum meets it
  (the case `matted_small` used to catch), refusals of a zero size and a
  non-positive minimum. `test_config.py`: the key's default and refusal; the
  retired key's warning, asserted present when set and absent when not. Phase
  two: a bigger scan wins below 7,680 and ties above it; a scan below the
  minimum sorts last and is kept. Selection and discovery: a below-minimum
  instance is not auto-claimed and a work with only those lands `unresolved`,
  through the service, with a non-default minimum so the setting is proven
  wired. Every rewritten assertion names in its commit why the old one went
  (the box is gone), and each new guard is watched failing once.

### Chunk 02: Every surface states the two-state verdict

- **Visual change:** yes
- **Surfaces:** `http/models.py` (`FitOut` loses `rendered_*`); `http/api.py`
  (the `fit` filter and facet values); `mcp/bindings.py` and `mcp/tools.py`
  (the fields and descriptions the decision above retires, and the regenerate
  notice); `http/static/core/badges.js`, `core/reviewing.js`,
  `screens/collection.js` (the facet, renamed *Size*), `screens/work.js`,
  `app.css` (badge classes); `api-contract.md` (the `fit` rows and the MCP
  result fields); `information-architecture.md` (the facet's name, and
  *Cutoff Unmet* retired in favour of `upgrades.md`'s *Wanted › Upgrades*).
- **What:** every surface shows exactly the 01 verdict, with no inch or box
  figure anywhere. The tile hides `meets_minimum` as it hides `native` today.
- **Tests:** the HTTP and MCP tests that pin fit fields, rewritten to the new
  values, and `fit=below_minimum` filtering through the real server; the
  surface-parity test across HTTP and MCP; the browser suite (`-m browser`) for
  the badge, the facet, the review grid's "found only too small" and the work
  page. An unknown old value (`matted_small`) in the `fit` filter is refused
  by name, not ignored. `tests/preferences/test_screen_tables.py` stays green
  against the renamed facet.

### Chunk 03: The presentation master

- **Type:** cumulative-final
- **Surfaces:** `persistence/records.py` (`RenditionKind.PRESENTATION_MASTER`);
  new `library/acquisition/master.py` (derive and write);
  `library/acquisition/preparation.py` (the master before the canvas, current
  or regenerated); `library/acquisition/queue.py` and `services/container.py`
  (startup backfill, the `owe_recomposition` pattern); `persistence/sqlite.py`
  (the query naming works that owe a master); `config.py` (the directory name);
  `data-model.md` § Rendition; `boundary-patterns.md` § `ART_ROOT` filesystem
  contract (`presentation/` joins it as a regenerated class);
  `operational-spec.md` (the store's measured size);
  `re-architecture.md` § Open questions (the cap and encoding answered).
- **What:** the master is derived as the decision above says and recorded with
  its own `source_content_hash`, so a new Original makes it stale through the
  existing `is_current`. `prepare()` makes it current before the canvas, so
  every acquisition, regenerate and mat change leaves both. A mat change does
  not rewrite the master. At startup every held work without a current master
  is queued prepare-only, and the queue's one thread works through them.
  `GET /media/{hash}` already serves any Rendition by its hash, so the master
  is servable unchanged; no manifest names it.
- **Tests:** a large Original yields a 7,680 long edge in its own aspect; a
  small one is copied at its own size, never enlarged; an EXIF-rotated Original
  comes out upright; a new Original makes the master stale and `prepare()`
  replaces it; a mat change leaves the master's hash as it was; the startup
  query names a work with no master and a work with a stale one, and not a work
  with a current one; the master is fetched by its hash through the real
  server's `/media` route, and the bytes match. The master's byte size is
  measured over the local corpus (or the fixture set if there is none) and the
  figure recorded with what was measured and N.

**Done when (whole plan):** all three suites, the browser suite, lint and
format green; `/prawduct:critic cumulative` over the branch with no blocking
finding; the change-log entry for `wave-4b-master-quality` written, naming the
MCP breaking change and the retired `RESOLUTION_FLOOR_INCHES`.
