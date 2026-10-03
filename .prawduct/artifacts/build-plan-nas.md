---
artifact: build-plan
version: 1
scope: nas
branch: feature/nas
partition: serial — 01 and 02 both change the server's startup and configuration, 03 consumes 01's image, and 04 and 05 are operations on the owner's NAS and Pi that the coordinator runs and watches itself
depends_on:
  - artifact: re-architecture
  - artifact: operational-spec
  - artifact: security-model
  - artifact: player-contract
governed_by:
  - artifact: re-architecture
    dispositions:
      - "wave 3, 'first, split the store … so the data moves once' → departure by the owner's choice of 2026-10-02 ('NAS now', skipping the split), accepting one more data migration when the split lands; recorded as a dated note in § Order of work. The rest of wave 3 is this plan: containerize, deploy on the NAS, point the Pi at HTTP; retiring the file channel follows the soak (backlog)"
      - "the deployment side lives in the operator's homelab repo → binds Chunk 03"
      - "the image needs a uv-managed Python 3.14, the dezoomify-rs binary, and a memory limit in place of MemoryMax; no Pango → binds Chunk 01"
  - artifact: security-model
    dispositions:
      - "both surfaces are LAN-only, reached remotely over an overlay network; the application performs no authentication → [DECISION: on the NAS, Arrt is reached at a `.lan` name through the homelab's LAN-only reverse proxy, with no login and no overlay network, as tacularr is; the provider's $20/month cap bounds the worst case of a LAN client spending OpenRouter credit | the owner's choice of 2026-10-02 ('LAN-only, as tacularr'); the homelab has no overlay network, so the model's assumption is amended rather than met | owner can veto]. A login is backlog, not this plan"
      - "the Player routes require a per-wall bearer token → conforms: Chunk 05 issues the Pi's token on the Walls screen"
      - "image provenance and pinning undecided (§ open) → binds Chunk 01: base images and the dezoomify-rs binary are pinned by version and checksum, and the image is built from a commit"
  - artifact: operational-spec
    dispositions:
      - "back up the catalogue only, with the SQLite backup API or VACUUM INTO, several generations, the receipt written only on success, age on the health panel; the restore path is a deliverable with an exercise → binds Chunk 02"
      - "code apart from data: back up the data, re-fetch the code → conforms: the image is rebuilt from a commit; the data lives on a NAS dataset"
  - artifact: observability-strategy
    dispositions:
      - "a periodic job logs every pass, so one that died can be told from one with nothing to do → binds Chunk 02's backup job"
      - "panel-only alerting → conforms for now; the homelab's Prometheus sees the container (cAdvisor); a health probe is backlog"
  - artifact: nonfunctional-requirements
    dispositions:
      - "the Pi's memory ceiling for image work → relaxed on the NAS: the container gets a memory limit (3 GB) in place of the unit's MemoryMax; the one-fetch-at-a-time worker is unchanged"
  - artifact: project rule (CLAUDE.md)
    dispositions:
      - "this repo is public; no network addresses, hostnames or usernames → binds every chunk: the Dockerfile and a generic compose example live here; the real compose, env, Caddy block, addresses and the deploy script live in the private homelab repo (the owner's choice of 2026-10-02)"
last_validated: null
---

# Build Plan — Arrt on the NAS

## What this plan is

The owner, 2026-10-02: "pivot to what's needed to really get the system usable
day to day", then "NAS now". Today the wall runs August code on the Pi, and
everything built since runs only on dev copies on the Mac. This plan puts
current Arrt on the NAS, beside the owner's other apps, with the house's
configuration in the homelab repo, backups on NAS storage, and the Pi pulling
its art over HTTP.

| Chunk | What |
|---|---|
| 01 | The container: `arrt/Dockerfile`, a cheap health route, a generic compose example |
| 02 | The backup writer, and the restore exercise (closes #14) |
| 03 | The homelab half: `apps/arrt`, its env, Caddy, the deploy script (private repo) |
| 04 | Seed the NAS with the Mac's dev library, deploy, check it end to end |
| 05 | The Pi: update its player to current code, switch it to HTTP, soak |

**The owner's choices, 2026-10-02:** NAS now, skipping the store split; the
Mac's dev library (`~/samsung-art`) becomes the live one; LAN-only at a `.lan`
name with no login, as tacularr; the Dockerfile here and the rest in
homelab; build the backup writer; the Pi straight to the NAS, then a soak.

**Not in this plan:** the store split (re-architecture wave 3's first step);
retiring the file channel (after the soak); a login; Tailscale; a health probe
in the homelab's Prometheus; the Library screens and upgrades branches (each
merges and redeploys on its own: images are tagged by commit).

## What I would do differently

Nothing in the shape. Two risks the choices carry, so they are visible:
**no login on the LAN** (any LAN client can curate and spend, bounded by the
$20 provider cap), and **one more data migration** when the store split lands.
And one the research found: **the Pi runs August code**, which predates the
HTTP pull mode, so Chunk 05 updates the Pi's player first — the riskiest step,
done with the runbook already written and the wall dark for a few minutes.

## Requirements Confidence

**High** for 01–03, **Medium** for 04–05: the NAS and Pi steps depend on the
state of machines this repo does not describe, and each is checked on the
machine before anything is changed.

Open assumptions:
- [ASSUMPTION: the container's memory limit is 3 GB | LOW impact | owner can correct]
- [ASSUMPTION: the masters (`raw/`), renders (`ready/`) and thumbnails (`thumbs/`) move with the library; previews are regenerated or lost (they are disposable) | MED impact | owner can correct] *(Revised in Chunk 01: regenerating renders on the NAS is not what happens — see the finding under Chunk 02.)*
- [ASSUMPTION: backups go to a separate NAS dataset (not the app's own), 14 daily generations kept; ZFS snapshots of the app's dataset are the owner's to configure if they are not already | MED impact | owner can correct]
- [ASSUMPTION: the Pi's old `curation.service` is stopped and disabled, not removed, for a quick way back during the soak | LOW impact | owner can override]

## Status

- [x] Chunk 01: The container
- [x] Chunk 02: The backup writer
- [x] Chunk 03: The homelab half
- [ ] Chunk 04: Seed and deploy
- [x] Chunk 05: The Pi on HTTP *(re-scoped: the wall rotating moves to build-plan-clients.md)*

### Chunk 01: The container

`arrt/Dockerfile`: uv copied from a pinned image, Python 3.14 from uv,
`uv sync --frozen --no-dev`, a pinned `dezoomify-rs` release binary checked
against its checksum, run as an unprivileged user, `CURATION_HOST=0.0.0.0`,
`ART_ROOT=/art` as a volume, a `test` target that runs the curation suite in the
image. A cheap `GET /healthz` (the container's healthcheck; `/api/health` reads
the whole panel). `deploy/nas/compose.example.yaml`: a generic compose with
placeholders, no addresses. `deploy/README.md` § The NAS says where the real
half lives.

Done when: the image builds for `linux/amd64` on the Mac; the test target is
green in the image; the image runs against a copy of the dev library and serves
the UI, `/api/health`, `/mcp` and a Player route with a token; `/healthz` has a
test; `.dockerignore` keeps `.env`, `.venv` and data out of the build context
(checked by listing the context).

*Chunk 01 verified 2026-10-02:* the image built for `linux/amd64`; the test
target passed in the image (3005 passed, browser and paid suites skipped as
everywhere); run against a copy of the dev library it served the UI (200),
`/healthz` (`ok`), `/api/health`, `/mcp` (6 tools, `art_catalogue` listing 40
works), and a wall's manifest only with that wall's token (401 without, 200
with: 40 entries, 40 with media) and a render through `/media/sha256-…` (200,
a JPEG); the build context held only `Dockerfile`, `pyproject.toml`, `uv.lock`,
`src`, `tests`, `tools` and `.dockerignore`.

### Chunk 02: The backup writer

A backup job in the server: on an interval, `VACUUM INTO` the catalogue at a
configured `BACKUP_DIR` under a dated name, keep the newest N, and write the
receipt (`backup-status.json`, success only) the health panel already reads.
A pass is logged every time, as the queue's is. `kept-answers.sqlite` is not
backed up. The restore exercise: a documented command that restores the newest
backup into a scratch art root and starts the server against it.

**Found in Chunk 01, and moved to the backlog rather than fixed here** *(the
builder's call, 2026-10-02, which the owner can veto; filed as #180)*:
readiness checks that a work has a current render *row*, never that the render
*file* exists. Run against a copy with no `ready/`, the manifest listed all 40
works with no exclusion (measured 2026-10-02), so a restore onto an empty image
tree does not do what `operational-spec.md` § The restore path promised ("the
manifest build finds no current render for any work, excludes them all and
reports why"), and nothing re-fetches a master whose row survives its file.
Fixing it changes a decision the Player contract pins
(`test_a_render_with_no_file_is_published_without_media_and_says_so`: an
unreadable render is published without media), so it is a contract decision
of its own, not a backup detail; and day-to-day use does not need it, since the
NAS seed carries the renders and the NAS's snapshots carry the image tree. This
chunk corrects the operational spec to say what a restore actually does, and
the restore exercise restores the catalogue *with* its image tree.

Done when: tests for a backup, the receipt written only on success, retention,
a failure leaving the previous receipt, and the panel's age after a run; the
restore exercise run once on the Mac and recorded; the readiness finding filed
in the backlog; `operational-spec.md`
§ Backup and Restore updated; #14 closed.

### Chunk 03: The homelab half

In the private homelab repo, following its own pattern and tacularr's deploy:
`apps/arrt/compose.yaml` (the image by commit tag, the app's data directory
as `/art`, the backup dataset, env file, port, healthcheck, memory limit,
restart policy, `no-new-privileges`), the env template, the reverse proxy's route
for its `.lan` name, the router's A record (instructions), and an Arrt deploy script
adapted from tacularr's (`image`: build amd64, tag with the commit, push to the
NAS registry; `app`: render and apply; rollback by tag; `test`).

Done when: the homelab files are committed in the homelab repo (not pushed
without the owner); the script's `image` step pushes an image the registry
lists; nothing in this repo names an address.

*Chunk 03 done 2026-10-02 (homelab commit `f6607eb`, not pushed):* `arrt/compose.yaml`
(a template outside `apps/`, because the homelab's apps loop applies compose
files verbatim and this one needs `${TAG}` rendered), `bin/arrt-app.sh`
(tacularr's deploy flow on the homelab's own NAS helpers: `image`, `app`,
`test`, `seed`, rollback by `TAG`), `secrets/arrt.env.example`, the Caddy route
and a README section. `bin/arrt-app.sh image` pushed the image, and the NAS
registry lists it. The router's DNS record is the owner's.

### Chunk 04: Seed and deploy

Copy the Mac's dev library to the NAS dataset (the catalogue with the SQLite
backup API; `raw/` as files), with the app's ownership; deploy; open
the app's `.lan` address from the Mac; check the UI, Activity, the Walls screen, a
Get's search, MCP from a client, a backup run and its receipt; let
renditions and thumbnails regenerate.

Done when: each check above passes on the NAS and is recorded; the first
backup exists on the backup dataset; the owner has opened it.

*Chunk 04, 2026-10-02 (all but the owner's look):* the Mac's dev library was
seeded onto the NAS with `bin/arrt-app.sh seed` (the catalogue by SQLite's
backup API, then `raw/`, `ready/` and `thumbs/`, 619 MB; the directories then
made group-writable for the container, which the script now does itself), and
image `249a8ec` deployed as the app `arrt`, state RUNNING. On the NAS:
`/healthz` ok, the UI 200, 40 works, a Wikidata search answered, MCP's
`art_catalogue` listed 40, the backup taken at start (the panel: "last backed
up 3 seconds ago", one generation in the backups directory), and *All works*
hung on the wall published 40 entries with none excluded. Waiting on the owner:
the router's `arrt.lan` record, and opening it.

### Chunk 05: The Pi on HTTP

On the Pi, before any change: snapshot `/srv/art` (done once on 2026-10-02;
again now). Update the Pi's checkout and its player to current code with the
runbook (`operator-verification.md` § The Pi's units after the renames); issue
the wall's token on the NAS's Walls screen; set `MANIFEST_SOURCE=http`,
`SERVER_URL`, `WALL_TOKEN`, `CACHE_DIR`; restart the player; stop and disable
the Pi's `curation.service`. Watch `pull.*`, the heartbeat on the NAS's Walls
screen, and the wall changing; stop the NAS app briefly to see the wall keep
running from its cache.

Done when: the wall shows art pulled from the NAS; the NAS's Walls screen shows
a fresh heartbeat; the cache test passed; the soak entry in
`operator-verification.md` is updated with what was seen; the way back is
written down (re-enable the Pi's server and set `MANIFEST_SOURCE=file`).

*Chunk 05, 2026-10-02 evening (the owner approved "go now" while away):* the
Pi's databases and `.env` were snapshotted to the Mac first; its checkout went
from `7b400ff` to released `main` (`7e211f1`; no player or contract change
between `main` and `develop`) by the runbook, the player synced with its
raster and e-paper groups, the new `display.service` installed, `WALL_ID` set
to the NAS's wall and HTTP mode switched on (`.env.pre-http-2026-10-02` kept),
and the Pi's `curation.service` stopped and disabled. **Working:** the player
pulled the NAS's manifest ("40 of 40 entries; 40 renders held") and the NAS's
Walls screen shows its heartbeat. **Not yet:** (1) **the television has not
opened its art channel since 16:23 local, three hours before the cutover** —
the old code logged the same `tv.unavailable` after the Pi's reboot and never
recovered, so the wall has not rotated since then under either version; it
needs a look at the set (a restart of the TV, by a person: no code presses
power, per `nonfunctional-requirements.md`). (2) **The label panel no longer
opens**: "could not open the e-paper device 'waveshare_epd.it8951' (Could not
determine Jetson model)" — the old environment opened it on this same kernel
this morning, and the driver pins are identical, so the fresh environment
differs somewhere not yet found. (3) The cache test (stop the NAS, the wall
keeps rotating) waits for (1). Not ticked until the wall rotates from the NAS.

*Chunk 05 re-scoped by the owner, later on 2026-10-02:* "Let's skip the frame,
I'm watching stuff on it. Instead, let's get the rpi ready to show images over
hdmi." The Pi's player was stopped and disabled so nothing reaches for the set.
What this chunk proved stands — the Pi pulls the NAS's manifest and renders and
the NAS sees its heartbeat — and the rest (a wall rotating from the NAS) moves
to `build-plan-clients.md` Chunk 05, on HDMI. #182 (the TV's art channel) and
#181 (the label panel) stay open for when the Frame returns.

## Verification strategy

Every chunk ends on the real thing: the image running on the Mac (01), a
restore from a real backup (02), an image in the NAS registry (03), the app on
the NAS from a browser and an MCP client (04), and the wall itself (05).

## Governance checkpoints

After Chunk 01 (the image is the artifact everything after deploys), and a
cumulative review before the PR, with the code chunks (01, 02) reviewed as they
land.
