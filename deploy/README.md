# Deployment

**Arrt runs on the operator's NAS as a container** (§ The server on the NAS).
Each wall is driven by Arrt Player, a client of this server, whose deployment
record lives in its own repository:
[brookstalley/arrt-player, `deploy/README.md`](https://github.com/brookstalley/arrt-player/blob/develop/deploy/README.md).
That is where the Pi's unit, its install and cutover record, the television's
power-key measurements and the e-paper driver's pin are kept, with the runbook
for moving a Pi onto a newer revision.

The sections dated below are what each release asked of the server. Where a
release also changed the Player, the order of the two is given here and the
Player's steps are in its repository.

## The server on the NAS (2026-10-02, `build-plan-nas.md`)

**The server is moving to the NAS as a container.** What is public lives here:

- `arrt/Dockerfile` — the image, built from a commit with everything it
  fetches pinned (base images by digest, Python by version, packages by
  `uv.lock`, `dezoomify-rs` by release and checksum). It runs as an
  unprivileged user, serves on 8770, writes under `/art` and, when
  `BACKUP_DIR` is set, under `/backups` (both mounts must be writable by it), and answers
  `/healthz` for the container's healthcheck. Build it for the NAS with
  `docker buildx build --platform linux/amd64 -t arrt:<commit> arrt/`; run the
  curation suite inside it with `--target test --build-context repo=.`.
- `deploy/nas/compose.example.yaml` — the app's shape with placeholders.

**What is not here, by the rule that this repository names no address:** the
real compose file, the env file, the reverse proxy's route, the registry, and
the build-and-push script. They are in the operator's homelab repository,
beside the house's other apps.

**Two facts a deployment needs, found while building the image:**

- **The art root must carry `presentation/` and `thumbs/`, not only `raw/` and
  the catalogue.** A work is ready for a wall when its presentation master's
  file can be read, so a catalogue without its masters keeps every work off
  every wall, each named with why; the startup backfill makes them again from
  `raw/`. *(Until wave 4g this named `ready/`, the server's composed canvases,
  which nothing reads now.)*
- **Masters recorded before the media route existed carry no content hash.**
  They are hashed the first time a feed names them, which needs the file.

### A private source plugin

**A plugin that is not in this repository reaches the server through an image
built on top of Arrt's.** Its recipe lives beside the plugin, in the private
repository. The shape, with the plugin's source as the build context:

```dockerfile
ARG ARRT_IMAGE
FROM ${ARRT_IMAGE}
USER root
COPY . /tmp/plugin
RUN uv pip freeze --python /opt/venv/bin/python --exclude-editable > /tmp/arrt-locked.txt \
 && uv pip install --python /opt/venv/bin/python --constraint /tmp/arrt-locked.txt /tmp/plugin \
 && rm -rf /tmp/plugin /tmp/arrt-locked.txt
USER 568:568
```

Build it with `--build-arg ARRT_IMAGE=arrt:<commit>` and deploy that tag in
place of Arrt's.

- **The constraint is what keeps Arrt's locked versions.** Without it, the
  installer changes whatever Arrt's dependencies the plugin asks it to. Measured
  2026-10-03: a plugin requiring `httpx<0.28` downgraded Arrt's locked 0.28.1 to
  0.27.2 and built cleanly. With the constraint, the same build fails and names
  the conflict. Fix such a plugin, not the constraint.
- **`USER root` for the install, then back.** Arrt's image runs as 568 and its
  venv is root's. Change the last line if the compose file runs another user.
- **The plugin names no `arrt` dependency** (`docs/source-plugins.md` § A plugin
  is a distribution with one entry point), so nothing here can fetch an `arrt`
  from PyPI.
- **Rebuild it for every Arrt commit you deploy.** It carries Arrt's code
  inside it, so a derived image left on an old tag holds the server back too.

**How to tell it worked:** the startup log has `source plugin <name> loaded`, or
the reason it declined, and the health panel lists it. Run once with
`--entrypoint python` and the snippet in `docs/source-plugins.md` § Testing to
see the same answer before deploying. Verified 2026-10-03 against `arrt:0e10e6d`,
with the guide's example reader: the plugin read `loaded` beside
the three built-ins, as uid 568.

What installing a plugin trusts is `security-model.md` § Source plugins.

## Clients (2026-10-02, `build-plan-clients.md`)

**A Player is a client of the server.** The server knows which walls each client
shows and on which of its outputs. The Player is configured with the server's
address and its own token, and learns everything else from `GET /client`.
`clients.md` is the authority.

**Before deploying the clients release to the server, copy the catalogue.** The
release drops the per-wall token columns when it opens the catalogue, so the way
back needs a copy taken first, outside the backup writer's rotation:

    sqlite3 <art root>/catalogue.sqlite ".backup <backups dir>/pre-clients-<timestamp>.sqlite"

Then deploy (`bin/arrt-app.sh` in the homelab repo) and confirm `/healthz`.

**Make a client** (Settings › Clients, or the same routes from a shell), and
give its token to the Player:

    curl -s -X POST -H 'content-type: application/json' -d '{"name":"Living room Pi"}' "$SERVER_URL"/api/clients
    curl -s -X POST "$SERVER_URL"/api/clients/<client_id>/token        # shown once; keep it out of shell history

**Then assign a wall** to one of the outputs the client reported, on Settings ›
Clients or with `POST /api/walls/<wall_id>/client {client_id, output}`. The
Player starts that wall within a poll (about 30 s).

**How to tell it worked:** Settings › Clients shows the client's outputs and how
long ago it reported. With the server stopped, a wall keeps rotating from the
Player's cache; nothing on the server is needed for a wall to go on showing what
it has.

**The way back:** on the NAS, roll the app back with
`TAG=<the previous image> bin/arrt-app.sh app` in the homelab repo, with the
`pre-clients-<timestamp>.sqlite` copy restored. **The clients release drops the
per-wall token columns on open**, so the old image cannot use the migrated
catalogue.

## Displays and labels (2026-10-08, `build-plan-displays-and-label-outputs.md`)

**Copy the catalogue before deploying this server.** Opening the catalogue
gives every assigned wall a display record and drops `walls.client_id` and
`walls.output`, so an older image cannot read it afterwards:

    sqlite3 <art root>/catalogue.sqlite ".backup <backups dir>/pre-displays-<timestamp>.sqlite"

The way back is that copy and the previous image, together.

**Either order works, and server first is the one to choose.** A new server
reads an older Player's client heartbeat (the new keys are optional), and an
older Player ignores the new keys in `GET /client`. A new Player against an old
server is given no labels, so its panel draws nothing until the server is
updated.

**After the Player update, a panel draws nothing until it is mapped.** It is
reported as the client's label output `epd-0`; caption a wall with it on
Settings › Clients. `EPD_DEVICE` no longer needs `TV_ADDRESS`.

## Wave 4g: the walls move to manifest major 2 alone (2026-10-10)

From wave 4g the server publishes each wall's feed (manifest major 2) and
nothing else, and Arrt Player reads only that. Every file named below is in the
server's art root.

**Copy the catalogue before deploying this server.** Opening the catalogue
drops the `directives` table, forgets every television canvas and the wall
previews drawn from them, and drops `renditions.mat_hex`, so an older image
cannot run on it afterwards:

    sqlite3 <art root>/catalogue.sqlite ".backup <backups dir>/pre-4g-<timestamp>.sqlite"

Deploy the server and the Player from the same revision; until both are up, a
wall goes on showing the work it has. Then check, in this order:

1. **The server forgot its canvases.** Its first start on a catalogue from
   before wave 4g logs `Forgot N television canvases and previews drawn from
   them, and dropped renditions.mat_hex; ART_ROOT/ready/ can be deleted.`, once
   (N may be 0). A catalogue made after wave 4g never had them and says nothing.
   `<art root>/ready/` and every `<art root>/theme-manifest-<wall>.json` without
   `.v2` are now nothing's, and are yours to delete when you are satisfied.
2. **The wall's Player reads the feed.** Its heartbeat lists major 2:

       jq '.capabilities.manifest_majors' <art root>/display-heartbeat-"$WALL_ID".json

   It should print `[2]`. Walls shows a line under the wall's name when a
   Player cannot read the feed; there should be none.
3. **The wall changes picture on its schedule.** The slot covering now names the
   work up now (the feed writes every instant in UTC, so the strings compare):

       now=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
       jq --arg now "$now" '.schedule.slots[] | select(.from <= $now and $now < .until)' \
           <art root>/theme-manifest-"$WALL_ID".v2.json

**Settings.** The server no longer reads `TV_PANEL_*`, `MAT_WIDTH_INCHES` or
`MAT_BOTTOM_WEIGHT`; they are the Player's, under the same names, and stay in the
Pi's `.env`. The Player no longer reads `ROTATION_INTERVAL_SECONDS` or
`ROTATION_SHUFFLE`; they are the server's. Neither plane refuses the other's
keys, so a shared `.env` needs no edit.

**The way back** is the catalogue copy and the previous image together on the
NAS, and the Pi's previous revision (`git rev-parse HEAD` before checking out
the new one): a Player from before wave 4g reads major 1, which this server no
longer writes, so the two go back as a pair.

## Heartbeat minor 4, and the feed following its theme (2026-10-10)

`build-plan-feed-follows-theme.md`. **Deploy the server first, then the
Player.** The Player now sends `capabilities` without `screen` when its screen
is unplugged, and a server from before this refuses that heartbeat, which would
leave Walls reading the wall as silent until the server caught up. The other
order is safe: the new server reads the old Player's heartbeats as before.

On its first start the server publishes a feed for every wall that has a theme
hung and none on disk, logging `Wall '<name>': published theme '<theme>', which
had no feed on this wall (after startup).` The wave 4g deploy needed a re-hang
by hand for this, and no longer does. Then check:

1. **Walls shows no feed notice for a Player with its screen unplugged.** Its
   heartbeat lists major 2 without a screen:

       jq '.schema, .capabilities' <art root>/display-heartbeat-"$WALL_ID".json

   It should print minor 4 and `manifest_majors: [2]`, with `screen` only while
   the screen is connected.
2. **A work added to the hung theme reaches the feed without a re-hang.** Add
   one that can be shown, from Library › Works; the server logs `Wall '<name>':
   published theme '<theme>' with <id> joining (after joining its theme).`, and
   the feed carries it whenever its three days of slots name it:

       jq --arg id "$WORK_ID" '.works | has($id)' <art root>/theme-manifest-"$WALL_ID".v2.json

**The way back** is the previous image on the NAS and the Pi's previous
revision. Nothing in the catalogue changed, so no copy is needed; a server from
before this refuses the new Player's screenless heartbeats, so the Player goes
back first.

## `curation.service`

`deploy/curation.service` runs the server under systemd rather than in a
container. It ran the server on the Pi from 2026-08-11 until the server moved to
the NAS on 2026-10-02, and has been stopped and disabled there since. The
service account, the paths and the cutover it was installed in are recorded in
Arrt Player's `deploy/README.md`, beside the Pi's own unit.

**A restart is not a way to force a republish.** At every start the server
reconciles each published feed against the Library (`DisplayService.reconcile`)
and republishes only a feed that no longer agrees with it, or a hung theme's
feed that is missing from disk. A feed that already agrees is left as it is.
