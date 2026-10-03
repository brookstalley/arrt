# Upgrades: finding and taking a better image of a work you hold

<!-- Requirements and design, written 2026-10-02 from the owner's direction and
three research passes (tacularr, the *arr apps, Arrt as built). The build is
`build-plan-upgrades.md` (manual upgrades); a later plan adds the scheduler. -->

## What this is

Arrt finds an image for a work once, when it is accepted, and never looks
again. A work held at 1200 pixels stays at 1200 pixels even when its museum
publishes a 6000-pixel scan. This artifact is the requirements for looking
again, judging what is found, and taking a better image safely — the *arr
apps' "upgrade", shaped by tacularr's habit of keeping the old file until the
new one is proven.

**The owner's direction, 2026-10-02:** "let's move from UI to discovery,
acquisition, retry and upgrade following the *arr and ../tacularr's patterns
for tracking and finding better quality." This pulls upgrades ahead of the NAS
move (`re-architecture.md` wave 3) and out of wave 6+, where the
re-architecture placed them. The quality profile's *presentation master* half
stays in wave 4.

## The owner's rulings, 2026-10-02

1. **No cutoff; searches back off by size instead.** In the owner's words: "No
   cutoff, but back off searches. At 3840, maybe once a month. At 7680, every
   six months." Arrt never stops looking for a bigger scan of a work; how often
   it looks falls as the held image grows. This **amends** the re-architecture's
   decision that the profile has "a minimum … and a cutoff, above which the
   Library stops looking" (`re-architecture.md` § The resolution floor becomes
   a Library quality profile): the minimum stays, the cutoff becomes a search
   cadence by size tier. The cadence is the scheduler plan's; this plan records
   the tiers and searches only when asked.
2. **Upgrades swap automatically — behind a "same picture" gate.** "Swap
   automatically but we want a good quality measure for it being the same
   picture, not like someone posting a 21mp camera picture from a museum with
   glare, etc." A bigger scan replaces the held image only when Arrt can show it
   is the same work, reproduced faithfully. Pixel count alone never wins.
3. **Manual first, the scheduler next.** This plan builds upgrades a curator
   triggers (Search, Search all) and everything an automatic job would need to
   be safe; the next plan adds the scheduler, System › Tasks, per-museum rate
   limits and backoff, and the size-tier cadence. Watches come after that.

## What the research found

Three read-only passes, each with file and line evidence in their reports
(not copied here; the conclusions are).

**tacularr owns no quality model.** It sits beside Sonarr and Radarr, which
rank releases and hold the profiles, and it replaces a file only for a named
defect (no English audio; does not play through). What it does own, and what
Arrt takes from it:

- separate *wanting*, *pending* and *gave up* states, each with `since`, `due`,
  an attempt count and the releases already tried;
- **keep the old file until the new one is verified**, and put it back if
  verification fails;
- blocklist the release a bad file came from — and *not* a release that was
  merely unneeded;
- a per-item attempt cap, a daily cap, a longest wait, and a person's "this
  does not exist" mark that can be undone;
- after a failure, due again soon rather than at the full interval;
- check a replacement exists before touching what you have.

**The *arr apps** (Radarr, Sonarr, Lidarr, read from the Servarr wiki and the
`develop` source):

- *Monitored* per item; Wanted › Missing and Wanted › Cutoff Unmet; Search
  Selected and Search All.
- A profile of ordered qualities with a cutoff, plus custom-format scores with
  a minimum, an "upgrade until" and a **minimum increment** — an upgrade must
  beat the held file by enough to be worth taking.
- The upgrade decision has a fixed order: better quality while below the
  cutoff → take; worse → refuse; same quality → only a proper/repack or a
  better score by the increment.
- **They do not search on a schedule.** RSS sync reads each indexer's feed of
  new posts; periodic upgrade searches are bolted on by outside scripts.
  Museums publish no such feed, so Arrt polls — tacularr's `due` pattern, not
  Radarr's RSS.
- Per-indexer politeness: one request per two seconds by default, `429
  Retry-After` honoured, and a failing indexer disabled for 0s, 1m, 5m, 15m,
  30m, 1h, 3h, 6h, 12h, then 24h.
- Failed download handling records the failure, blocklists the release and
  searches again. The blocklist is per item, kept until a person removes it,
  and a manual pick can override it. Activity has Queue, History and Blocklist.
- **A lesson from Radarr's code:** its Cutoff Unmet page checks quality only,
  while its upgrade decision also checks the score, so items it would upgrade
  never appear on the page. Arrt's listing uses the same predicate as its
  decision.

**Arrt as built** already has half of it: the `wanted` verdict and Activity ›
Wanted (Lidarr's Wanted › Missing), Search again and Search all
(`resolve_images`), ranking by `quality_score`, a turned-down scan suppressed
by URL so it never returns, several sources per work with a primary, a retry
queue with backoff and a pause, and constraint 16 (a partial tile fetch never
replaces a complete original). What it lacks:

- **any path to upgrade a held work** — a re-search refuses decided works, a
  Get skips held ones, and new scans are never added to an accepted work's
  sources;
- a pixel comparison between a found scan and the held original;
- per-work history (the queue row is deleted on success, and a source's last
  fetch overwrites itself);
- a scheduler, a monitored flag, and an `initiated_by` for scheduled work (the
  next plan).

## The model

How the *arr concepts land:

| *arr | Arrt |
|---|---|
| Monitored | Every accepted work is upgradable; a per-work *Don't look for better* mark (tacularr's undoable "no English") stops it |
| Quality ladder | Pixel size of the image, by its **long edge** (as the fetch caps already measure) |
| Minimum quality | The resolution floor, as today; nothing below it is ever taken |
| Cutoff | None (ruling 1); size tiers set how often the scheduler looks |
| Minimum increment | An upgrade must be meaningfully bigger, not a few pixels (measured in Chunk 01) |
| Custom-format score | The **same-picture gate** below: a pass/fail, not a score to trade against size |
| Interactive search | A held work's page lists every scan found, with why each was or was not taken |
| Wanted › Cutoff Unmet | **Wanted › Upgrades**: held works, their size, when they were last searched, and what was found |
| Blocklist | Per work, by source URL; written when a scan fails the gate or its fetch fails; removable by hand |
| History | Per-work events: searched, found, fetched, verified, swapped, refused (with the gate's reason), failed, reverted |
| Failed handling, redownload | A failed fetch or a failed gate blocklists that scan and tries the next candidate |

### The upgrade decision, in order

For a held work and one scan found for it:

1. **Blocklisted for this work** → refuse (a person can still pick it by hand).
2. **Below the floor** → refuse.
3. **Not bigger than the held image by the minimum increment** → refuse.
4. **A partial tile fetch** → refuse (constraint 16).
5. **Fails the same-picture gate** → refuse, and blocklist it with the reason.
6. Otherwise → take it: fetch it alongside the held image, verify, swap.

The Upgrades listing and the decision call the same predicate (the Radarr
lesson).

### The same-picture gate (ruling 2)

A scan passes only if both halves hold, judged against the **held image**,
which the curator has already accepted as the work:

- **It is the same work.** Perceptual similarity to the held image at a common
  small size, after normalising for size and aspect. Its aspect ratio within a
  tolerance of the held image's.
- **It is a faithful reproduction, not a photograph of the object.** Signals to
  measure, none assumed to work until Chunk 01 has measured them:
  - geometry: no perspective keystone or rotation relative to the held image
    (a homography close to a similarity transform);
  - border: no frame, wall or gallery background around the image;
  - glare: the share of clipped highlights not well above the held image's;
  - provenance: a museum's own image (institutional source class) rather than
    a contributed photograph; camera metadata (a phone or consumer camera in
    EXIF) as a warning sign on a Commons file;
  - colour: no gross cast relative to the held image.

**And it must be measurably better, not only bigger.** The owner, later the
same day: "we need something that measures quality — contrast, sharpness, not
sure what else. This must be a solved problem." It is: *image quality
assessment* (IQA) is an established field, with no-reference measures that
score one image (BRISQUE, NIQE, and learned ones such as MUSIQ, CLIP-IQA and
TOPIQ) and full-reference measures that compare against a reference (SSIM,
LPIPS, DISTS). Museum digitisation has its own standards (FADGI, Metamorfoze,
ISO 19264-1: sharpness, noise, tone, colour accuracy, geometric distortion).
Chunk 01 chooses from these by measurement, with a research pass on current
practice first, rather than inventing a score.

**The design's advantage over a generic IQA problem:** Arrt already holds an
image of the same work that the curator accepted. So the strongest test
compares the candidate *against the held image*, aligned to it: glare,
perspective, a frame, a colour cast or a different crop all show up as
disagreement with a reproduction the curator already trusts. A no-reference
score then judges "better" at full size (sharpness, detail), normalised for
scale. **A caution the research must answer:** learned no-reference models are
trained on photographs, and may score a soft-edged Rothko as blurred or a flat
colour field as low-contrast; comparing two images *of the same work* cancels
most of that, since the style is common to both.

**What the research pass on IQA found (2026-10-02), and the gate it points
to.** No-reference IQA is trained on consumer photographs and judges "a good
photo", not "a faithful reproduction" — a vivid gallery phone shot may outscore
an evenly lit museum scan, and no study measures it on paintings. The best
maintained library, `pyiqa`, is licensed for **non-commercial use only** and
needs PyTorch (over 1 GB of memory), so it is not used. Heritage digitisation
standards (FADGI, ISO 19264-1, Metamorfoze) define "faithful" — sharpness,
tone, colour error, geometric distortion — but measure it against a target
chart Arrt never has. So the gate is the reference-based design, **torch-free**
(OpenCV, numpy, scikit-image):

1. **Geometry**: local features matched between candidate and held image, a
   homography fitted robustly. Too few matches → a different work. Strong
   keystone → photographed at an angle. The held image's corners falling
   outside the candidate → a crop or detail. The held image filling much less
   than the candidate → a frame or wall around it. Then the candidate is warped
   onto the held image's frame.
2. **Fidelity at the held image's scale**: a full-reference measure (GMSD or
   MS-SSIM) overall and per tile, so glare and reflections show as local
   disagreement; colour error on blurred versions, and the mean colour shift (a
   cast). Fidelity says "different", not "which is right", so provenance
   counts too: an institutional source, no phone in the EXIF.
3. **Better at full size**: *effective* resolution, not pixel count — detail
   the candidate carries beyond what the held image can, and a test that an
   upscaled image fails — plus a JPEG-quality floor.
4. **Never automatic for objects that are not flat** (sculpture, vessels: a
   homography does not hold), and other impressions of a print or photograph
   are different objects, not upgrades.

Thresholds are set so that **no negative in the evaluation set is accepted**:
replacing a held image wrongly costs more than missing an upgrade. The miss
rate that leaves is reported for the owner.

**The gate is computed locally, with no model call**, so an upgrade spends
nothing (the vision model's $20 a month ceiling is for mat colour). A paid
model judgement is a fallback the owner can choose later if the measured
signals fall short. Its compute must fit the server it runs on: on the NAS a
CPU-only PyTorch model is affordable; on the Pi it may not be — Chunk 01
records the cost.

### Keeping the old until the new is proven (tacularr)

The scan is fetched to a staging place beside the held original; it is
verified (decodes, really is the size it claimed, passes the gate against the
held image); only then does it become the original, and the old original is
kept as a **superseded original**, so the swap can be reverted from the work's
page. The TV rendition is regenerated from the new original; **the mat colour
is kept** (it is the same work), so no vision call is made.

### What the scheduler plan will add

The size tiers and their cadence (below 3840 px more often; at 3840 monthly; at
7680 every six months — exact intervals then), per-work `due` with backoff after
a failure, per-museum courtesy intervals and escalating disablement, per-run and
daily caps, System › Tasks (name, interval, last run, last duration, next run,
Run now), and the observability re-derivation the re-architecture names
(scheduled work is the push-alert revisit trigger).

## What the stored data must answer

Lock-in questions, added to `data-model.md` § What this data must answer as
Q38–Q42 when Chunk 02 designs the fields:

- **Q38** Which held works could have a bigger image, how big is each now, and
  when was each last searched?
- **Q39** Which scans were found for a held work, and why was each taken or
  refused (size, increment, constraint 16, which gate signal)?
- **Q40** What was this work's image before, and can the swap be undone?
- **Q41** Which scans are blocklisted for this work, why, when, and by whom?
- **Q42** What happened to a work's image, in order?
- *(Scheduler plan)* **Q43** When is each work next due for a search, given its
  size tier and its last outcome?

## Open questions

- **The gate's thresholds** — Chunk 01 measures them on real pairs before any
  are chosen.
- **The minimum increment** — likewise measured: how much bigger is worth a
  swap.
- **Where a superseded original lives, and for how long** — on the Pi's card it
  doubles the masters' footprint for upgraded works; on the NAS it does not
  matter. Proposed: kept until the next successful backup after the swap, then
  reclaimable.
