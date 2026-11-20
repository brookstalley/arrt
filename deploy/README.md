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
  curation suite inside it with `--target test --build-context repo=.`, as the
  app's own user. CI builds that target natively on amd64 on every pull request
  into `main`, which is a release, so the image is built before every release
  without anyone remembering to, and when the workflow is run by hand
  (`.github/workflows/image.yml`); on a pull request into any other branch it does
  not run at all, whatever changed (since 2026-11-20, by the owner's ruling that CI
  is kept small). So a Dockerfile, lockfile or interpreter change is first built at
  the release's pull request unless you run the workflow, or the build below, by
  hand on the branch. On an arm Mac it builds under emulation, takes far longer, and
  a test that times a server's answer can fail there for that reason alone.
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

### Hardening the container (2026-11-19)

**`deploy/nas/compose.example.yaml` drops every capability (`cap_drop: [ALL]`),
makes the root filesystem read-only (`read_only: true`), and mounts the three
places the server writes.** The example holds exactly what was measured, and
`tests/preferences/test_compose_example.py` fails when a line of it goes or a
writable path appears that was not measured.

**Measured 2026-11-19 on the operator's own machine, not a deployment:** the
`app` image (`arrt:290e054a`, built for amd64 and run under emulation), as user
568, with `cap_drop: [ALL]`, `read_only: true`, `no-new-privileges` and a 3 GiB
limit, from an empty art root started once with `--init`, through the compose
example filled in with local values. It started and answered `/healthz`
(`healthy`), took its start-up backup, wrote a wall's feed when a theme was hung
on it, and stopped on SIGTERM in about seven seconds with exit code 0. A
second container of the same image ran with a writable root as a control. What
each wrote:

| Where | What | Mounted as |
|---|---|---|
| `/art` | `catalogue.sqlite` (and its journal while open), `kept-answers.sqlite` with its `-wal` and `-shm`, `backup-status.json`, `theme-manifest-<wall>.v2.json` | the art root's volume |
| `/backups` | `catalogue-<UTC instant>.sqlite`, one at start | the backup volume |
| `/tmp` | nothing in normal use; SQLite's spill of a large sort | `tmpfs`, 64 MiB, `mode=1777`, `noexec`, `nosuid` |
| the rest of the root filesystem | nothing: `docker diff` listed only the two mount points, with the root writable | read-only |

- **Why `/tmp` is mounted although nothing was seen writing it.** SQLite sorts in
  memory until a sort outgrows its 2 MB cache, then spills to a temporary file in
  `/tmp`, and with the root read-only and no `/tmp` the query fails with `disk I/O
  error`. Measured with the image's own Python (SQLite 3.53.1), not through a
  server request: 5,000 rows sorted, 20,000 failed, and 100,000 sorted with the
  tmpfs. `HOME` is `/` for user 568, and nothing wrote there.
- **`dezoomify-rs`** (the tile fetcher) ran read-only against a local IIIF source
  with its tile cache and its output under `/art`, and wrote nothing else. It was
  not run against a museum.
- **The tmpfs counts against `mem_limit`.** 64 MiB of the 3 GiB.
- **`cap_drop: [ALL]` assumes the server's user owns what it writes.** With no
  `CAP_DAC_OVERRIDE`, a user that does not own the art root and the backup
  directory cannot write them, whatever their mode; `user:` is the one that does.
- **Not measured:** a long run, a restore, a source plugin that writes somewhere
  of its own (a derived image's plugin: § A private source plugin), and the
  operator's own NAS (`operator-verification.md` owes that check against the
  private compose file).

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
- **The plugin's own lock is held the same way.** The constraint above keeps
  Arrt's versions; the plugin's dependencies Arrt does not already carry
  still resolve to whatever is newest on the day of the build, so two builds of
  one commit may differ. The private source plugins' repository found a second step
  necessary for a reproducible image: it exports the plugin's own `uv.lock` as a
  constraints file (`plugin_constraints.py`, there) and passes it to the install
  beside Arrt's. Its `arrt-sources:deploy/Dockerfile` is the recipe to copy; the snippet above
  is the part that protects Arrt, not the whole of a reproducible build.
- **The plugin names no `arrt` dependency** (`docs/source-plugins.md` § A plugin
  is a distribution with one entry point), so nothing here can fetch an `arrt`
  from PyPI.
- **Rebuild it for every Arrt commit you deploy.** It carries Arrt's code
  inside it, so a derived image left on an old tag holds the server back too.
- **A plugin that reads through a browser, or is otherwise slow, declares its
  deadlines before an image is built from this server (interface 1.5).** The host
  waits 60 seconds for a finder or a reader, 30 for a preview and 120 for a
  browse, and a call that takes longer is answered "could not be asked", so a
  plugin whose pages take longer than that, left as it was written for 1.4,
  would never answer and every work behind it would wait. It declares
  `SourcePlugin(deadlines={"finder": ..., "reader": ...})` in seconds, at most
  3,600 each, and a value outside that is refused at load, naming it
  (`docs/source-plugins.md`, `source-plugins.md` § Versioning and errors). A 1.4
  plugin loads unchanged and gets the defaults.

**How to tell it worked:** the startup log has `source plugin <name> loaded`, or
the reason it declined, and the health panel lists it. Run once with
`--entrypoint python` and the snippet in `docs/source-plugins.md` § Testing to
see the same answer before deploying. Verified 2026-10-03 against `arrt:0e10e6d`,
with the guide's example reader: the plugin read `loaded` beside
the three built-ins that existed then, as uid 568. There are ten today: the
`arrt.sources` entry points in `arrt/pyproject.toml` are the list.

What installing a plugin trusts is `security-model.md` § Source plugins.

### What is reachable, and what is logged (2026-11-19)

**The boundary is every network that can route to the published port**, not the
reverse proxy. The server asks no one who they are, and its host check admits any
IP address as the name asked for (`security-model.md` § Trust Boundary), so a
port published on every NAS interface lets a guest network, an IoT network or a
VPN reach everything the proxy does, without it. `deploy/nas/compose.example.yaml`
now publishes the port to one address (the proxy's, or loopback) and bounds
Docker's log. **Before deploying**, set the real file's `ports:` to the address
only the proxy reaches, then check from a machine on another network that
`curl -s -o /dev/null -w '%{http_code}' http://<NAS address>:<host port>/healthz`
does not answer.

Four more things changed at the server's edges:

- **A Player's successful requests write no access line.** A manifest, label,
  media or heartbeat request answered `2xx` or `304` is not logged; a refusal
  (`401`, `403`, `404`) still is, and so is every request to any other route.
  Before this, one wall wrote about 170,000 lines a day.
- **A request the browser marks `Sec-Fetch-Site: cross-site` is refused** on
  `/api` and `/mcp` (`403`): a page elsewhere can no longer start a look by a
  `GET` that carries no `Origin`. The interface's own requests, an MCP client
  (which sends no such header) and a Player are unaffected, and so is a link to
  a page of the interface from anywhere.
- **The browser interface cannot be framed** (`frame-ancestors 'none'`,
  `X-Frame-Options: DENY`). A reverse proxy that serves the interface inside
  another page needs its own header to say so.
- **A Player's request body over 256 KiB is refused with `413`.** A heartbeat
  is a few kilobytes.

**The way back** is the previous image. Nothing in the catalogue changed.

## Before an upgrade that drops something (2026-11-19)

**The server copies the catalogue itself before a migration that drops a column
or a table.** The three sections below each say to copy the catalogue by hand
before deploying their release, and that is still sound, but from this release a
catalogue that needs such a migration is copied first by the server, whoever
forgot. The copy is `pre-migration-<UTC instant>.sqlite`, in `BACKUP_DIR` when it
is set and beside the catalogue when it is not. The three newest are kept,
outside the backup generations' count, so no number of restarts prunes them. A
catalogue already on the current shape, or a new one, takes none.

**If the copy cannot be written, the server does not start**, and the catalogue is
left exactly as it was: the message names the directory and the reason (a full
disk, a read-only mount). Free the space or make the directory writable, or point
`BACKUP_DIR` at one that is, and start again. Nothing is dropped without its
copy, so nothing is lost by the refusal.

**The way back across such a migration** is that copy and the previous image
together (`operational-spec.md` § Backup and Restore, whose numbered steps these
are):

1. Stop the server.
2. Remove `catalogue.sqlite-journal` (and a `-wal` or `-shm`, if anything left
   one) from beside the catalogue: a copy put in beside a hot journal opens as
   the stopped server's last commit, and looks fine.
3. Copy the chosen copy in beside the catalogue and rename it over
   `catalogue.sqlite`.
4. Start the previous image.

**Which rollbacks need it (2026-11-19).** The catalogue records the shape
generation each release expects (`catalogue_opened.schema_generation`), and a
release that carries the record refuses only a file recorded at a higher
generation than its own, naming the copies beside the file that it opens, or
saying there are none. So a rollback across no change to the shape, such as a bad
patch release back to the one before it, is the previous image alone, and the
previous image says so by starting; one across a raised generation is refused
and is the steps above. A release from before the record (v0.11.0 and older)
checks nothing and opens a migrated file without a word, so to one of those the
copy is what makes the way back safe, never the image alone. A restart is not a
backup either way: the start-up backup pass is skipped while the newest
generation is younger than `BACKUP_INTERVAL_SECONDS`, so a server restarting in a
loop no longer replaces the generations from before the upgrade.

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

## The names the server answers to (2026-11-08)

`build-plan-mcp-household-agents.md`. **Before deploying, add to the env file
every name a browser or an MCP client uses to reach the server**, the reverse
proxy's name for it included:

    CURATION_ALLOWED_HOSTS=<name>,<other name>

From this release on, every surface but the Player's refuses a request for a
name not listed (`421`), and a request from a page at any address but a listed
name or its own (`403`). `localhost` and any IP address always pass as the name
asked for. The Player's routes are not checked, so the
walls keep their feed whatever is set. A deployment that sets nothing and is
reached by name loses its browser interface and MCP until the name is listed,
and each refusal says so. Then check:

1. **The browser interface opens** at the name the household uses.
2. **The server logs no `refused a request for host`** for a name the household
   uses.
3. **A name not listed is refused**: `curl -s -o /dev/null -w '%{http_code}' -H
   'Host: not-listed.example' http://<address>:8770/api/health` prints `421`.

**The way back** is the previous image. Nothing in the catalogue changed, and the
setting is ignored by a server from before this.

## Ask's spend in the ledger (2026-11-09)

From this release on, each Ask reply that was billed anything writes a spend
row in the category `ask_tokens` (#337). Nothing to do before deploying. Check
after one Ask reply that `art_discovery(action='spend')` went up by about what
the reply showed under it.

**The way back** is the previous image, after one statement on the catalogue.
A server from before this refuses a spend row in a category it does not know,
so its month's spend fails once Ask has written one:

    sqlite3 <art root>/catalogue.sqlite "DELETE FROM spend_records WHERE category = 'ask_tokens';"

That forgets only what Ask spent since the upgrade, which the earlier server
never counted.

## Restarting the server

**A restart is not a way to force a republish.** At every start the server
reconciles each published feed against the Library (`DisplayService.reconcile`)
and republishes only a feed that no longer agrees with it, or a hung theme's
feed that is missing from disk. A feed that already agrees is left as it is.
