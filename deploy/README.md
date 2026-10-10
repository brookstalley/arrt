# Deployment

> **Direction changed 2026-09-30. See `.prawduct/artifacts/re-architecture.md`.
> This file documents the Pi deployment that is live today, and every procedure
> in it still applies to that machine.**
>
> The target splits this deployment across two machines:
> - **The server (today's `curation` plane) moves to the operator's NAS**
>   (TrueNAS SCALE) as a container in wave 3, together with the catalogue and art
>   tree. That deployment is recorded in the operator's homelab repository, not
>   here. Until then, `curation.service` below keeps running on the Pi.
> - **The Player (today's `display` plane) stays on the Pi** under systemd. From
>   wave 2 it *can* pull each wall's manifest and media over HTTP into a local
>   cache and render only from that cache, switched on by configuration while the
>   file channel keeps working. From wave 3 that is the only mode. A server
>   restart or a NAS reboot then never blanks the wall, and the Pi needs no
>   `ART_ROOT` shared with anything, only a cache directory of its own.
> - **After the wave-5 repo split**, the Player's deployment docs move to the
>   player repository along with `arrt-player/`.
>
> Do not remove anything below before the wave that retires it has landed. The
> cutover record, the power-key measurements and the e-paper pin are hardware
> facts about the wall, and they travel with the Player.

> **As of 2026-10-02 the Pi runs only `display.service`, as a client of the
> server on the NAS** (§ The Player as a client of the NAS, below). Its
> `curation.service` is stopped and disabled. The sections after that one
> describe the one-wall Player of released v0.1.0, with `WALL_ID`,
> `MANIFEST_SOURCE` and the file channel. The current Player refuses all three.
> Those sections stay as the record of how the wall got here, and as hardware facts
> about the Frame, which comes back as a client's `frame` output.

**`display.service` and `curation.service` ran the wall**, as the `tvpi` service
account on the Raspberry Pi driving the Frame TV. They were installed and enabled
on 2026-08-11; § The cutover below is what was run.

`samsung-frame-art-loader.service` is the **2024** unit. It is retired, it is not
installed, and it is kept here as recovered evidence until the legacy retirement —
see the banner above its recipe further down before running anything from it.

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

## The Player as a client of the NAS (2026-10-02, `build-plan-clients.md`)

**A Pi is a client of the server.** The server knows which walls each client
shows and on which of its outputs. The Pi is configured with the server's
address and its own token, and learns everything else from `GET /client`.
`clients.md` is the authority. This is what was run on 2026-10-02.

**Before deploying the clients release to the server, copy the catalogue.** The
release drops the per-wall token columns when it opens the catalogue, so the way
back below needs a copy taken first, outside the backup writer's rotation:

    sqlite3 <art root>/catalogue.sqlite ".backup <backups dir>/pre-clients-<timestamp>.sqlite"

Then deploy (`bin/arrt-app.sh` in the homelab repo) and confirm `/healthz`.

**On the server** (Settings › Clients, or the same routes from a shell):

    curl -s -X POST -H 'content-type: application/json' -d '{"name":"Living room Pi"}' "$SERVER_URL"/api/clients
    curl -s -X POST "$SERVER_URL"/api/clients/<client_id>/token        # shown once; keep it out of shell history

**On the Pi**, with `display.service` stopped:

    cd /opt/samsung-frame-art-loader
    sudo -u tvpi git fetch origin <branch or tag> && sudo -u tvpi git checkout -B <branch> FETCH_HEAD
    cd arrt-player && sudo -u tvpi /usr/local/bin/uv sync --group raster --group epaper
    sudo cp -p ../.env ../.env.pre-clients-<date>      # the way back starts here
    # in .env: set SERVER_URL, CLIENT_TOKEN and CACHE_DIR; remove WALL_ID,
    # WALL_TOKEN and MANIFEST_SOURCE, which the client Player refuses by name
    sudo adduser tvpi video                            # an HDMI wall opens the display card
    sudo cp ../deploy/display.service /etc/systemd/system/ && sudo systemctl daemon-reload
    sudo systemctl enable --now display.service

**Then assign a wall** to one of the outputs the client reported, on Settings ›
Clients or with `POST /api/walls/<wall_id>/client {client_id, output}`. The
Player starts that wall within a poll (about 30 s).

**The Frame is optional, and was left off on 2026-10-02.** `TV_ADDRESS` gives the
client a `frame` output, and `EPD_DEVICE` gives it a label output, `epd-0`, which
needs no Frame: the server maps it to any wall. Both are commented out in the Pi's `.env` while the set is being watched, so
the client reports only its HDMI connectors and nothing on the Pi can reach for
the television.

**How to tell it worked:**
- Settings › Clients shows the client's outputs (`hdmi-a-1` connected at its
  screen's size) and how long ago it reported.
- The Player's journal shows `client.started`, then `client.wall_started`,
  `pull.adopted` and `rotation.selected` for each work.
- On an HDMI wall, `screen.absent` means the Pi sees no screen on that
  connector. Unless the cable has been pulled, `sudo vclog --msg` is where to
  look (`hdmi-output-findings.md`).
- **A stopped Player leaves the text console on the screen.** The Player holds
  the display card while it runs, and the kernel hands the screen back to the
  console when it exits.
- With the server stopped, the wall keeps rotating from `CACHE_DIR`
  (`client.unreachable` and `pull.unreachable` are logged, and nothing else
  changes). This was checked on 2026-10-02 with the NAS app stopped for two
  minutes across a rotation.

**The way back**, to the one-wall Player of v0.1.0 pulling over HTTP:
1. On the NAS, take a catalogue copy, then roll the app back with
   `TAG=<the previous image> bin/arrt-app.sh app` in the homelab repo. **The
   clients release drops the per-wall token columns on open**, so the old image
   needs the catalogue backup taken before the clients deploy
   (`pre-clients-<timestamp>.sqlite` in the backups directory). It cannot use
   the migrated catalogue.
2. On the Pi: `sudo systemctl stop display.service`, check out the release the
   Pi ran before (`7e211f1`), `uv sync` as above, restore
   `.env.pre-clients-<date>`, install that revision's `deploy/display.service`,
   and start it again.

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

## The Player renamed Arrt Player (2026-10-08, #311)

**The Player's project moved from `postarr/` to `arrt-player/`, and its module
from `postarr` to `arrt_player`.** The installed `display.service` names the old
directory and module, so after pulling this it fails to start until it is
replaced. The unit keeps its name. A virtualenv is not relocatable, so the old
one is removed and the new directory gets a fresh one. That also clears the
`jetson-gpio` overlap from #181 below, with no `--reinstall-package` needed.

    sudo systemctl stop display.service
    cd /opt/samsung-frame-art-loader
    sudo -u tvpi git rev-parse HEAD    # write this down: "To go back" returns to it
    # Both must start with / or ~. A relative one lives inside postarr/, so move
    # it out and make it absolute in .env before going on; the Player now refuses
    # to start on a relative one.
    grep -nE '^(CACHE_DIR|TV_TOKEN_FILE)=' .env
    grep -n postarr .env    # any hit names the old path: edit it
    sudo -u tvpi git pull
    # git moves the tracked files; postarr/ keeps only what was untracked.
    # Lists every file left in it that is not a venv, a cache or bytecode.
    # It must print nothing; stop if it prints anything:
    find postarr -type f -not -path '*/.venv/*' -not -path '*/__pycache__/*' \
        -not -path '*/.pytest_cache/*' -not -path '*/.ruff_cache/*' -not -path '*/.hypothesis/*'
    sudo rm -rf postarr
    cd arrt-player && sudo -u tvpi /usr/local/bin/uv sync --group raster --group epaper
    cd /opt/samsung-frame-art-loader
    sudo cp deploy/display.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl start display.service

Logger names now start `arrt_player.`, so a saved journal filter on `postarr.`
stops matching. **To go back**, stop the unit, check out the commit you wrote
down, remove `arrt-player/`, run `uv sync --group raster --group epaper` in `postarr/`, copy that commit's
`display.service` in, reload and start.

## The panel's GPIO package (2026-10-08, #181)

**On a Pi whose venv predates #181's fix, sync with `--reinstall-package
rpi-gpio`.** `jetson-gpio` and `rpi-gpio` both installed `RPi/GPIO/__init__.py`;
the sync removes `jetson-gpio`, and with it that file, so `rpi-gpio` has to be
installed again to put the real one back:

    cd arrt-player && sudo -u tvpi /usr/local/bin/uv sync --group raster --group epaper --reinstall-package rpi-gpio

## The two new units, and where everything they name now lives

`display.service` and `curation.service` are the planes this product is being
rebuilt onto. Three paths they depend on were unsettled until the cutover and are
settled now; `operational-spec.md` § Where the two trees live records why each one
won, and this is the short form:

| | |
|---|---|
| `ART_ROOT` | `/srv/art` |
| Checkout | `/opt/samsung-frame-art-loader` |
| `uv` | `/usr/local/bin/uv`, named absolutely in both units |

**All three are off any home directory, and that is the requirement rather than a
preference.** `tvpi` is a `--system` account with `/usr/sbin/nologin`; the machine's
existing checkout and its only `uv` both sat under a home directory at mode `0700`,
which such an account cannot traverse at all. A path the service account cannot
reach is not a detail to leave to whoever reads a unit file next.

Creating that account, giving it the `spi`, `gpio` and `video` groups, moving the art tree
to `/srv/art`, placing the checkout at `/opt`, and enabling these two units are
**one change, not five** — any of them landing alone leaves a machine that is
neither the old arrangement nor the new one. `operational-spec.md` § The Service
Account is the authority on the account and on why the five are one change; the
steps below, in the order they are written, are the authority on the order.
*(This used to point at a build-plan chunk for the ordering. A plan is archived
when it finishes and its sub-numbering is bookkeeping, so a deployment document —
which outlives every plan — cannot rest its procedure on one.)*

> **What this cutover is not.** It has been described in the plan as the moment
> `tvart.py` stops being the production entry point. On the machine as rebuilt
> that describes a swap that does not exist: **no unit of this product is
> installed on the Pi at all** — no `samsung-frame-art-loader.service`, no cron
> entry, no user service. The 2024 loader has not run unattended since the card
> was rebuilt on 2026-08-04, and the wall has been driven by hand since. So this
> is a first install rather than a replacement, which removes the rollback
> pressure a real cutover would carry and is worth knowing before anyone plans
> around a maintenance window. The sentence is corrected here rather than
> quietly, because it read as a statement about the machine and was one.

## The cutover

Performed 2026-08-11 on the wall Pi (Debian 13 trixie, aarch64). This is the record
of what was run, in order, and it is the procedure for doing it again.

    # uv where any account can reach it, and the account itself.
    # Copying the operator's own binary takes whatever version that account holds
    # — 0.12.1 on the day this was run, which is the fact worth recording, since
    # nothing else in the tree pins it. `uv --version` after the copy is the check.
    sudo install -m 0755 -o root -g root ~/.local/bin/uv /usr/local/bin/uv
    sudo adduser --system --group --no-create-home --shell /usr/sbin/nologin tvpi
    sudo adduser tvpi spi && sudo adduser tvpi gpio
    sudo adduser tvpi video                         # an HDMI wall: the display card; added 2026-10-02
    sudo install -d -m 0750 -o tvpi -g tvpi /var/lib/tvpi
    sudo usermod --home /var/lib/tvpi tvpi          # see the note below

    # the checkout, owned by the account that executes it
    sudo install -d -o "$USER" -g "$USER" /opt/samsung-frame-art-loader
    git clone <this repo> /opt/samsung-frame-art-loader
    sudo chown -R tvpi:tvpi /opt/samsung-frame-art-loader

    # the art tree, moved rather than copied — same filesystem, so it is a rename
    sudo mv <old ART_ROOT> /srv/art
    sudo chown -R tvpi:tvpi /srv/art

    # dependencies, as the account that will run them
    cd /opt/samsung-frame-art-loader/arrt-player && sudo -u tvpi /usr/local/bin/uv sync --group raster --group epaper
    cd /opt/samsung-frame-art-loader/arrt && sudo -u tvpi /usr/local/bin/uv sync

    # the environment file: 0640, owned by tvpi, because it carries API keys
    sudo install -m 0640 -o tvpi -g tvpi <your .env> /opt/samsung-frame-art-loader/.env

    # the units and the journal bound
    sudo cp deploy/display.service deploy/curation.service /etc/systemd/system/
    sudo mkdir -p /etc/systemd/journald.conf.d
    sudo cp deploy/journald.conf.d/10-bound-the-journal.conf /etc/systemd/journald.conf.d/
    sudo systemctl restart systemd-journald && sudo systemctl daemon-reload
    sudo systemctl enable --now curation.service
    sudo systemctl enable --now display.service

**`--no-create-home` then `usermod --home` is not a detour, it is the finding.**
An account with `HOME=/nonexistent` cannot run `uv` at all — it fails on its own
cache directory before doing any work. `operational-spec.md` § The Service Account
records why the answer is a home for tool state rather than a list of `UV_*`
variables in both units. Create it directly with `--home /var/lib/tvpi` if you are
doing this fresh; the two-step above is only what this machine's history looked
like.

**Moving the art tree is a rename when `/srv` and the old location share a
filesystem**, which is worth checking (`stat -c %d`) before assuming the move is
instant: across filesystems it is a 647 MB copy and the ownership change after it
is not free either. Verify the count and the byte total on both sides rather than
trusting `mv`'s silence — this move was checked at 168 files and 677,652,949
bytes, identical before and after.

**A machine that has never run this product needs a catalogue before the wall can
do anything.** The units come up healthy against an art root with no catalogue and
correctly do nothing, which looks like a fault and is not one. Seeding is a
separate hand-run step and it neither spends nor renders — it carries the mat
colour from the 2024 index and adopts the renders already in the tree:

    cd /opt/samsung-frame-art-loader/arrt && sudo -u tvpi /usr/local/bin/uv run python -m arrt.seed <path to all.json>

Then create a theme and activate it, over the JSON API or the browser interface —
**activation is what publishes the manifest**, and until one is published the
display plane has nothing to rotate and says so.

**Re-run the same command on a machine that is already seeded, whenever the
catalogue gains a field.** It creates no works the second time; what it does is
carry across what an earlier run could not, and it is the only step that does.
The catalogue *file* upgrades itself — the store adds nullable columns on open —
but a column is not the same as a value, and the two arrive by different roads:

    cd /opt/samsung-frame-art-loader/arrt && sudo -u tvpi /usr/local/bin/uv run python -m arrt.seed <path to all.json>
    # Re-activate the live theme — this, and nothing else, republishes the manifest:
    curl -s localhost:"$CURATION_PORT"/api/walls                       # read WALL_ID and the active theme
    curl -sX POST localhost:"$CURATION_PORT"/api/themes/"$THEME_ID"/activate \
         -H 'content-type: application/json' -d '{"wall_id":"'"$WALL_ID"'"}'

**Restarting `curation.service` does NOT republish the manifest**, and this file
said it did until 2026-08-14. Nothing writes a manifest at startup —
`DisplayService.sync` is the only writer and it is reached by activating a theme,
over the JSON API above or the browser interface. An operator who restarted both
units after a seed re-run saw the old label text and had no reason to suspect the
instructions. The § Moving a running deployment section below states the same rule
from the other direction; the two now agree.

**Then restart the display plane, and this step is not optional if the wall is
sitting on one work.** The republished manifest is adopted on the next poll, but
the *label already drawn* is not redrawn with it: the panel captions what the set
announces, and it skips the draw while the announced work is the one it last
captioned — so the new text arrives when the wall next changes, which on a pinned
wall is never. A rotating wall gets it at the next rotation; a restart gets it now,
and is the only thing that does on a wall that is not rotating.

    sudo systemctl restart display.service      # redraw the label already on the wall

**Skipping it costs a quieter label rather than an error**, which is why it is
written here: the artists' family and given names arrived as fields on
2026-08-11, and until this runs every row still has null ones. The panel then
prints each artist's whole name unstyled instead of leading with the family name
— correct behaviour for a record nobody has split, and indistinguishable by eye
from the feature not working. The command reports which artists it named, and
names any it could not.

**The name table wins over what is stored, for the names it carries.** A re-run
does not merely fill blanks: where the table and the row disagree, the row is
rewritten. That is deliberate and it is how a *wrong* split gets fixed — correct
the line in the table, re-run, and the wall follows. The cost of the same rule is
that a hand-edited split would be reverted, which nothing can do today because no
surface writes those two fields. Anything that gains one has to decide whether it
outranks the table; until then the table is the only author and the only
authority. Names the table does not carry are never touched.

Then **check the manifest actually carries the new fields**, because a restart
that republished nothing looks identical to one that did:

    sudo -u tvpi jq '.schema, (.works | to_entries[0].value.label)' /srv/art/theme-manifest-"$WALL_ID".v2.json

`WALL_ID` is a wall's id — there is one feed per wall. `ls /srv/art/theme-manifest-*.v2.json`
lists every room the catalogue publishes for. *(Wave 4g: the `.json` files
without `.v2` are major 1's, which nothing writes or reads now.)*

### Wave 4g: the walls move to manifest major 2 alone (2026-10-10)

From wave 4g the server publishes each wall's feed (manifest major 2) and
nothing else, and Arrt Player reads only that. Deploy the server and the Player
from the same revision; until both are up, a wall goes on showing the work it
has. Then check, in this order:

1. **The server forgot its canvases.** Its first start logs `Forgot N television
   canvases and previews drawn from them; ART_ROOT/ready/ can be deleted.` (N is
   0 on a catalogue that never had any). `ART_ROOT/ready/` and every
   `ART_ROOT/theme-manifest-<wall>.json` without `.v2` are now nothing's, and
   are yours to delete when you are satisfied.
2. **The wall's Player reads the feed.** Its heartbeat lists major 2:

       sudo -u tvpi jq '.capabilities.manifest_majors' /srv/art/display-heartbeat-"$WALL_ID".json

   It should print `[2]`. Walls shows a line under the wall's name when a
   Player cannot read the feed; there should be none.
3. **The wall changes picture on its schedule.** The feed's first slot is the
   work up now:

       sudo -u tvpi jq '.schedule.slots[0]' /srv/art/theme-manifest-"$WALL_ID".v2.json

**Settings.** The server no longer reads `TV_PANEL_*`, `MAT_WIDTH_INCHES` or
`MAT_BOTTOM_WEIGHT`; they are the Player's, under the same names, and stay in the
Pi's `.env`. The Player no longer reads `ROTATION_INTERVAL_SECONDS` or
`ROTATION_SHUFFLE`; they are the server's. Neither plane refuses the other's
keys, so a shared `.env` needs no edit.

### Moving a running deployment onto a newer revision

**Written 2026-08-13, from doing it and finding three things this file did not
say.** Checking out a newer revision on a machine that is already serving a wall
is not the same act as the first cutover above, and it took the wall down for the
better part of an hour.

**Settings arrive with revisions, and an unset one refuses to start the plane.**
`.env` is not in the repository, so nothing carries a new key onto the machine and
nothing warns that one is owed. Diff before restarting:

    diff <(grep -oE '^[A-Z_]+' /opt/samsung-frame-art-loader/.env | sort -u) \
         <(grep -oE '^#? ?[A-Z_]+=' /opt/samsung-frame-art-loader/.env.example | tr -d '#= ' | sort -u)

**A wall has to exist before `WALL_ID` can name one.** The revision that made
manifests per-wall also made `WALL_ID` required, and the id is a UUID minted when
the wall is created — so there is an ordering: set `WALL_NAME` and start the
curation plane, which establishes the wall and carries whatever theme was active
onto it; read the id back from `curl -s localhost:"$CURATION_PORT"/api/walls`; put
it in `.env`; then start the display plane. Starting the display plane first gets
a refusal naming the variable, which is correct and is not a fault to debug.

**Activate the theme again after any upgrade that changes what the label
carries.** The manifest is written at activation, not at startup, so a plane that
restarts against an existing manifest serves the old label text — including after
a seed re-run that has just filled in new fields. **The block above this one is a
read** — it recovers `WALL_ID` from `/api/walls` — and this sentence used to point
at it as though it were the activation. The activation is the `POST` in
§ Seeding the catalogue, above:

    curl -sX POST localhost:"$CURATION_PORT"/api/themes/"$THEME_ID"/activate \
         -H 'content-type: application/json' -d '{"wall_id":"'"$WALL_ID"'"}'

### Looking at the label without the daemon

`arrt-player/tools/label_preview.py` renders the chain the daemon runs — metadata,
layout, Pango — so the type can be judged against real ink rather than imagined.
Its own docstring points here for this machine's paths, because a checkout, a
service account and its home are facts about a deployment and do not belong in a
source file:

    sudo systemctl stop display.service
    cd /opt/samsung-frame-art-loader/arrt-player && sudo -u tvpi env HOME=/var/lib/tvpi \
        /usr/local/bin/uv run --group raster --group epaper \
        python tools/label_preview.py --panel --record hokusai
    sudo systemctl start display.service

**No `--cap-arcmin` here, and that is the correction of 2026-08-13.** This example
used to pass `11`, which is an *override*: the daemon draws at the calibrated
12.4′, so the panel showed type the wall never sets. Every question the queued
verification entries ask is written in terms of 12.4′ and the 8.8′ floor — one of
them is literally "is 12.4′ still right in bold?" — so an operator following this
line answered them against the wrong size. Pass the flag only when the angle
itself is what you are trying out.

**Stopping the unit is not optional.** `--panel` takes the SPI device, and
`display.service` holds it while it runs; the two contend for the same bus.

**Stop it once and draw several records, rather than bracketing each one.**
`--record` chooses which of the wall's records is set, and the questions this
instrument answers are comparative — a long name against a short one, a full
record against a nearly empty one. The panel holds the last frame it was given,
so a sitting is a run per record against one stopped service, with the unit
started again at the end. `--help` lists the records there are, and so does the
refusal you get for naming one that does not exist.

**It states no geometry, and that is correct here and only here.** The tool
refuses to guess the panel's diagonal or its reading distance, and takes both
from this deployment's `.env` — the same two settings the daemon reads. So the
short form above is right on this machine and would be wrong anywhere else, where
`--diagonal-inches` and `--viewing-distance-inches` have to be passed. Running it
before `EPD_PANEL_DIAGONAL_INCHES` and `EPD_VIEWING_DISTANCE_INCHES` are in
place gets a refusal naming them, not a guess. (This used to say "the two `.env`
lines above"; they are set out under § Moving a running deployment onto a newer
revision, which is above this only in the file and below it in the order anybody
does things.)

### Measuring what the power keys do

`arrt-player/tools/power_probe.py` is the only thing in this repo that presses power on
the television. It exists because the transitions were never measured — the
documents describing them call themselves a sketch — and Chunks 25–27 are built on
what it records. This machine's paths, in the same shape as the label instrument
above:

    sudo systemctl stop display.service
    cd /opt/samsung-frame-art-loader/arrt-player && sudo -u tvpi env HOME=/var/lib/tvpi \
        /usr/local/bin/uv run python tools/power_probe.py
    # then, with somebody watching the set:
    ... python tools/power_probe.py --click --i-am-at-the-set
    ... python tools/power_probe.py --hold 3 --i-am-at-the-set
    sudo systemctl start display.service

**Stopping the unit is not optional, and here the reason is not a bus.** The daemon
holds the art channel, and this set has been observed refusing a *new* art-channel
connection for minutes after a client went away without closing — so a probe run
alongside the daemon contends for the slot, and a probe run after a `SIGKILL` may not
get one at all. `display.service` allows 90 s to stop; wait for it. The probe warns
when the art channel does not answer, because a contention refusal and a
state-dependent refusal look identical in its output and only one of them is a
finding about the television.

**It will not send anything without `--i-am-at-the-set`.** One of the measurements is
taken from the television state, which
`nonfunctional-requirements.md` § The television belongs to whoever is using it
forbids shipped code to press at; passing the flag is what says a person is standing
in front of the set, which is the whole difference between a measurement and an
interruption. A run with no gesture flag reads the state and is always safe.

**It leaves a second token file behind, on purpose.** The remote-control channel
gets `<TV_TOKEN_FILE>_probe_remote` rather than the daemon's file, because both
channels rewrite whatever token file they are handed and the wall depends on that
one. Its first open may raise a pairing prompt on screen — accept it while you are
there, and note that it happened. The file is the probe's alone; deleting it after
the sitting costs one more prompt next time and nothing else.

Read as evidence that the arrangement works, not as a promise about your machine:

- The curation plane marked the art root on its own — it holds a catalogue but had
  no marker, and a directory holding a catalogue is an art root by the only
  evidence that matters.
- The display plane adopted the 40-entry manifest, **disabled the television's own
  slideshow**, and **removed 40 images the binding table could not account for**.
  That last one is startup reconciliation working as designed: this device had no
  prior state, so nothing on the set was accounted for, and it re-uploaded all 40.
  **Expect a fresh device to re-upload the whole theme**, which took about three
  and a half minutes for 40 works.
- The set was in standby, and the plane logged *"the television is not in art
  mode; leaving the wall alone until it is"* rather than acting. The heartbeat said
  `television_reachable: true`, `television_showing_art: false`,
  `label_surface_working: null` — which is the honest reading of a device that has
  a panel and has not yet had anything to draw.

### How to tell your own install worked

> *2026-09-30: every check below reads files under `/srv/art`, meaning the
> manifest, the heartbeat and the catalogue, because both planes share that
> directory today. From wave 3 the Pi holds none of them. The equivalent checks
> become an HTTP `GET` of the wall's manifest from the server, the server's
> health view for the heartbeat, and a listing of the Player's cache. Rewrite
> this section when wave 3 lands, not before. See
> `.prawduct/artifacts/re-architecture.md`.*

**The two failures this arrangement deliberately makes loud both happen before the
process runs**, which is why "read the journal" is not the answer to them: a
missing `EnvironmentFile=` and a missing `/usr/local/bin/uv` are both refused by
systemd, so there is no application log line to go looking for. `systemctl status`
names them and `journalctl -u <unit>` does not. Run these in order; each one fails
differently from the others, which is the point of having four rather than one.

    # 1. Both units loaded, active, and enabled — enabled is the one people skip,
    #    and its absence is invisible until a reboot leaves the wall dark.
    systemctl is-active curation.service display.service
    systemctl is-enabled curation.service display.service

    # 2. The installed copies still match the checkout. They drift the moment
    #    somebody edits /etc/systemd/system directly, and nothing else notices.
    for u in display curation; do
      diff -q /etc/systemd/system/$u.service /opt/samsung-frame-art-loader/deploy/$u.service
    done

    # 3. The account can actually reach what it needs. Run AS tvpi — running it as
    #    yourself proves nothing, because your account is the one that already works.
    sudo -u tvpi /usr/local/bin/uv --version
    sudo -u tvpi test -r /opt/samsung-frame-art-loader/.env && echo ".env readable"
    sudo -u tvpi test -w /srv/art && echo "/srv/art writable"

    # 4. The display plane's own account of itself. This is the honest one: it
    #    distinguishes a device with no panel from one whose panel will not open,
    #    and a set that is unreachable from one that is simply not showing art.
    sudo cat /srv/art/display-heartbeat-"$WALL_ID".json

**Read the heartbeat rather than the wall.** `television_reachable: false` is a
network or pairing problem; `television_showing_art: false` with the set awake
means somebody is watching television and the plane is correctly leaving it alone;
the wall heartbeat says nothing about the label panel any more
(`has_label_surface: false`, `label_surface_working: null` on every wall): the panel
is a label output of the client, reported in the client heartbeat on the server's
Settings › Clients. There, `connected: false` is a panel that was configured and
would not open, or whose last draw failed — which costs the label and nothing
else — and a client with no `label_outputs` never had one.

**A `last_error` of `null` and a `reported_at` that is not advancing is worse than
an error**, because it means the daemon is not looping. Read it twice, a minute
apart, before believing a quiet heartbeat.

Verify the journal bound while you are here — `systemd-analyze cat-config` proves
only that the file parses:

    sudo journalctl -b -u systemd-journald | grep -i 'Journal.*max'
    # expect: "Runtime Journal (...) is 8M, max 256M, 248M free."

**The display plane's panel needs two optional dependency groups, and a default
`uv sync` installs neither.** They are separate because they install on different
machines: `raster` is the label's text stack (PyGObject and pycairo, which build
or wheel on any modern Linux), and `epaper` is the panel driver (`omni_epd`, which
compiles Cython against the Broadcom SPI and GPIO libraries and installs on a
Raspberry Pi and nowhere else). On the Pi:

    cd arrt-player && uv sync --group raster --group epaper

**A device with a television and no panel installs neither, and that is a
supported deployment** — leave `EPD_DEVICE` empty in `.env` and the wall rotates
with no label. A device with a monitor rather than e-ink would install `raster`
alone. Verified on the Pi 2026-08-07: PyGObject 3.56 and pycairo 1.29 resolve
under uv on Trixie/aarch64 with no `apt install python3-gi` needed.

**A device that names a panel owes two more values, and this is a step an
existing deployment has to take by hand.** Since 2026-08-11 the label's type
size is derived rather than fixed, from `EPD_PANEL_DIAGONAL_INCHES` and
`EPD_VIEWING_DISTANCE_INCHES` — the panel's diagonal and the distance people
actually stand at, inches for both. There is no default and there will not be
one: a guessed distance gives type that is silently illegible, which is what
this deployment shipped for as long as the sizes were fixed.

So **a `.env` written before that date has neither key, and the first restart
after deploying this draws no label** — the daemon logs which key is missing,
reports it on the heartbeat, and goes on rotating the wall. Add both lines to
`/opt/samsung-frame-art-loader/.env` before or with the deploy:

    EPD_PANEL_DIAGONAL_INCHES=6
    EPD_VIEWING_DISTANCE_INCHES=84

Those are the reference wall's: a 6-inch panel read from 7 feet. Measure to
where people stand, not to where you stand while installing it.

**Before the unit is enabled, the checkout needs its environment file.** Since
2026-07-27 `config.py` raises at import unless `ART_ROOT`, `TV_ADDRESS`,
`LATITUDE`, `LONGITUDE`, `LOCATION_NAME` and — since 2026-08-12 — `WALL_ID` all
resolve, deliberately, so that a missing deployment value stops the process
instead of quietly running against a plausible-looking default.

**`WALL_ID` is the one value here that cannot be typed from this document**: it is
the id the curation catalogue minted for the room this device serves, read off the
Walls screen or `art_display(action='walls')`. Start the curation plane once first
if this is a fresh install, since the id does not exist until the catalogue is
opened. Each wall has its own manifest, so a display carrying another room's id
shows that room's pictures with nothing anywhere reporting a fault — which is why
the plane refuses to start rather than guess one. The unit names that file in `EnvironmentFile=`, and
`load_dotenv` independently resolves it next to `config.py`; both point at the
repository root, which is also the unit's `WorkingDirectory`. The two agree
today because they read the same file, and if they are ever pointed at
different ones **the unit's `EnvironmentFile=` wins**: it is already in the
process environment by the time the code runs, and `load_dotenv` fills only
what the environment does not carry.

> **The recipe below installs the *2024* unit, and it is kept as a record rather
> than as an instruction — do not run it.** That unit is retired: it names
> `/home/tvpi/…` paths that do not exist — the account does now, since the
> cutover created it, but deliberately without that home — it runs `tvart.py`
> through a `.venv` that no longer exists, and its hand-written `PATH` carries
> pyenv shims and a stray editor directory. It is committed exactly as recovered
> because it had only ever existed on an SD card, and it is deleted with the rest
> of the 2024 plane at the legacy retirement. The live procedure is
> **§ The cutover, near the top of this file** — not below this banner, where the
> only thing you will find is the retired recipe itself. The Provenance section at
> the foot of this file records what else was assumed from the original card.

    cp .env.example .env      # then fill it in
    sudo cp deploy/samsung-frame-art-loader.service /etc/systemd/system/
    sudo mkdir -p /etc/systemd/journald.conf.d
    sudo cp deploy/journald.conf.d/10-bound-the-journal.conf /etc/systemd/journald.conf.d/
    sudo systemctl restart systemd-journald
    sudo systemctl daemon-reload
    sudo systemctl enable --now samsung-frame-art-loader

**The journald line is not optional decoration.** Committing that drop-in without
installing it is how the last unit file came to exist nowhere but a card. It bounds
the journal at 256M on *both* ceilings — `SystemMaxUse=` and `RuntimeMaxUse=` —
because Raspberry Pi OS ships `Storage=volatile`, so the journal lives in RAM and a
`SystemMaxUse=`-only file would bind nothing while reading as though it does. Two
things follow from volatile storage that are worth knowing before you debug
anything: **the journal does not survive a reboot**, and **logging does not wear the
card**. The file's own header carries the detail.

Verify it took — `systemd-analyze cat-config` proves only that the file parses:

    sudo journalctl -b -u systemd-journald | grep -i 'Journal.*max'
    # expect: "Runtime Journal (...) is 9.2M, max 256M, ..."

**Skipping the first line now fails loudly, and the two ways it can fail are
worth telling apart.** If `.env` is *absent*, systemd refuses to start the unit at
all and names the path it wanted — the fastest diagnosis available. If `.env` is
*present but incomplete*, the unit starts, `config.py` raises at import naming the
first variable it could not resolve, and the unit retries every ten seconds
indefinitely rather than giving up; `systemctl status` shows it actively failing
and `journalctl -u samsung-frame-art-loader` shows the variable. Neither case is
silent, which is the whole point of both settings.

## Provenance

This unit was recovered from the Pi's SD card, where it had only ever existed at
`/etc/systemd/system/`. It was never in version control, so it was invisible to
anyone reading this repo and would have been lost with the card.

It is committed here exactly as recovered. That means it still carries the
assumptions of the machine it was written on, all of which need revisiting before
it is deployed again:

- Absolute paths to `/home/tvpi/source/samsung-frame-art-loader` and its `.venv`.
- A hardcoded `PATH` containing pyenv shims and — spuriously — a VS Code Remote
  extension directory that happened to be in the shell environment when the unit
  was written.
- `User=tvpi`.
- ~~**No `EnvironmentFile=`, and the code now requires one.**~~ **Resolved
  2026-08-02** — the unit now declares
  `EnvironmentFile=/home/tvpi/source/samsung-frame-art-loader/.env`, un-prefixed,
  so a missing file stops the unit with a message naming the path instead of
  letting a process start that will raise at import. `operational-spec.md`
  § Configuration carries the reasoning and makes it a rule for every unit, not
  just this one. Note that the *path* is still one of the machine-specific
  absolutes listed above, and moves with them if the checkout ever does.
- `After=network.target`, which does not guarantee the network is actually up.
  `network-online.target` is the correct dependency for a service that talks to
  the TV on startup.
- ~~**`Restart=always` with no `RestartSec` or `StartLimit*` override**~~ —
  **Resolved 2026-08-02.** systemd's defaults restart after 100ms and give up
  after 5 attempts in 10 seconds, so a loader that crashed on startup burned its
  whole burst allowance in half a second and landed in `failed`, permanently, with
  nothing sent anywhere — the exact opposite of the success criterion requiring
  that *"a failure in the unattended loader is visible without inspecting the
  wall"*. The unit now sets `StartLimitIntervalSec=0` with `RestartSec=10`, so a
  persistent fault keeps retrying visibly rather than going quiet; the rule is
  recorded for every unit in `operational-spec.md` § Process Management. **The
  `OnFailure=` prescription that
  used to end this bullet is withdrawn (2026-07-20):** the recorded alerting
  decision (`observability-strategy.md` § The Health Surface) chose the curation
  UI health panel as the *only* alerting surface, and a crash-looped display
  already surfaces there as a stopped heartbeat with its age shown. Wiring
  `OnFailure=` to a notification path would implement an alerting surface the
  operator explicitly declined; if the deferred push path is ever revisited, that
  is the decision to reopen — not this unit file.
- No `SyslogIdentifier` or `StandardOutput` settings, so journal lines are
  attributed by executable path. Compounded by the code's use of `print()` for
  operational output, which produces journal entries with no level and no
  timestamp — recorded as a known departure in `project-preferences.md`.

## Before you install the current `requirements.txt` on the Pi

Two pin moves are described here. This one is the more recent; both have now
been exercised against the real television.

`aiohttp` (3.9.5 → 3.14.3), `lxml` (5.2.2 → 6.1.1), `pillow` (10.4.0 → 12.3.0),
`python-dotenv` (1.0.1 → 1.2.2) and `requests` (2.32.3 → 2.34.2) moved together on
2026-08-06 to clear published security advisories against the 2024 pins. What was
verified is that the set resolves in a clean 3.12 interpreter and that every
upstream call site these modules reach still behaves — the Pillow surface, the
`lxml`-backed BeautifulSoup parse, and the `samsungtvws` imports. `beautifulsoup4`
was left at 4.12.3: it was the companion bump lxml 6 looked likely to force, and
the parse was verified against 6.1.1 without it.

**It has been run against the television, and the check is discharged.**
`aiohttp` is not imported anywhere in this repo — it is the `samsungtvws` fork's
transport — so what was owed was a measurement on the set rather than an argument
from a resolver. `tv_api_check.py` passed 9 checks and 0 failures against the real
television on 2026-08-06 on `aiohttp` 3.14.3, `websockets` 16.1.1, `requests`
2.34.2 and the pinned fork. **The display plane then drove that transport hard on
2026-08-07** — 39 uploads, 41 deletions, brightness writes and confirmed
selections, unattended, across several hours. `pi-freeze-2024.txt` records the
pre-move version of all five and remains the rollback.

> **Attempted on 2026-08-06 and got no further than the handshake**, which is
> recorded so the next person does not read "owed" as "nobody has tried".
>
> **The diagnosis in this note was wrong, and is corrected here rather than
> quietly deleted** (2026-08-07). It said a set in standby refuses the art
> channel with `ms.channel.timeOut` and that `PowerState: 'on'` is the fix. With a
> cached pairing token both channels open in standby — the art channel in 2.4 s —
> and the whole surface works against a dark panel. `ms.channel.timeOut` has since
> been seen with the set **in art mode and healthy**, after heavy connection churn
> and a SIGKILLed client that never closed its socket, so it reads as a
> concurrent-client limit rather than a power state. If you meet it, wait a couple
> of minutes rather than reconnecting harder, and stop this plane with SIGTERM so
> it closes its own socket.
>
> `PowerState` is worth reading as the cheapest thing that separates a dark panel
> from a lit one, and this is how:
>
>     curl -s http://<TV_ADDRESS>:8001/api/v2/ | python3 -m json.tool | grep PowerState
>
> **It cannot tell art mode from somebody watching television** — it reads `on`
> for both. Only `get_artmode` does that, over the art websocket rather than this
> REST endpoint, which is why there is no one-liner for it here; the display
> plane asks it before every selection.
>
> The bumped set was exercised as far as the wire in the process: a clean 3.12
> interpreter carrying exactly these pins built the client, reached the set over
> the LAN, and failed only at pairing. **Everything past the handshake is proven
> now** — the display plane drove these pins through 39 uploads, 41 deletions and
> confirmed selections against the real television on 2026-08-07.

`samsungtvws` and `websockets` moved together on 2026-08-01 — a two-year-old fork
SHA to fork master, and websockets 12.0 to 16.1.1, which the new library requires.
~~That pair has been verified to resolve and import, and has not yet been run
against the television.~~ **It was run against the television on 2026-08-04 and the
checks pass** — construction, art-mode support, API version, a real 4K upload by
path, a confirmed delete, and callback registration, against a 2024
`QN50LS03DAFXZA` on firmware 1310. **One defect was found and is not fixed**
(issue #73): at the default `timeout=10`, `upload()` **reports failure on uploads
that succeeded** — observed twice, once returning `None` and once raising
`AssertionError`, with the `None` run's image demonstrably on the set. At an
explicit `timeout=60` the same upload returned its content id. Anything calling it
must pass an explicit timeout **and** confirm against the set's own content list
rather than trusting the return. *(The mechanism is deliberately not stated here:
an earlier revision named a raise site and an argument-form rule that the library's
source does not support, and both are retracted. Issue #73 separates what was
measured from what was inferred.)*
Findings in `.prawduct/artifacts/platform-and-dependency-findings.md` § The
television. Run it yourself after any change to the pins or the set's firmware:

    python tv_api_check.py --image "<any 3840x2160 JPEG>"

That exercises upload, callback registration, and a confirmed delete against the
live set, touching only the image it uploads itself, and exits non-zero if any
check fails. If it does fail, `pi-freeze-2024.txt` below is the rollback — it
records the exact versions the wall ran on before the move.

Behaviour changes to expect. Both were established by reading the library's source
and have since been confirmed on the set by the run above. (The upload defect is a
third change, but it belongs to neither category — it was *measured* on hardware,
and the source-derived mechanism first written around it has been retracted. Issue
#73 carries it.)

- **Building the art client now performs blocking network I/O** and raises when
  the set is unreachable, where it used to defer that to first use.
- **Deletion is confirmed against the television's own content list**, and the
  loader now says which of three things happened. *Removed* — an ordinary INFO
  line with the confirmed count. *Still listed* — the set kept them: a WARNING
  naming the images. ***Unconfirmable*** — nobody could establish which of those
  it is, whether because the set refused the request or because its list could
  not be read back: an ERROR, and the run *continues*, because stopping there
  would skip the catalogue save and every pending upload to prevent some leftover
  images. That third case is the one that used to be indistinguishable from
  success.

**The code and the pins can be deployed independently**, which is what makes this
safe to land ahead of the hardware pass. `tvart.py` calls only shapes that both
library versions carry: `available(category=...)` is unchanged between them, and
`upload()` has always accepted a path — the old one reads the file itself, the new
one streams it. So pulling the checkout without reinstalling degrades to the old
buffering behaviour and keeps working, rather than breaking.

### The e-paper driver is pinned rather than vendored, and here is why

`omni_epd` **declares `IT8951[rpi]` as a git dependency with no commit**, so
installing the parent alone resolves roughly 1,500 lines of Cython — which the
label panel depends on completely — to whatever that repository's master is on the
day. Builds are reproducible today only because it has not moved since 2023: a
fact about upstream inactivity, not a property of this project.

**Decision taken 2026-08-07: pin it.** A vendor buys exactly one thing a pin does
not — survival if the upstream repository disappears — and costs 1,500 lines of
Cython nobody here can maintain plus the ability to take any fix from upstream.
Vendoring stays available as the escape hatch if that repository ever goes away;
`pi-freeze-2024.txt` records what to vendor.

The pin is applied on both install paths, because they resolve independently:

- `requirements.txt` (the 2024 plane) carries an explicit `IT8951[rpi] @ …@9f13613`
  line beside `omni_epd`.
- `arrt-player/pyproject.toml` (the display plane) uses `[tool.uv] override-dependencies`,
  which is the only mechanism that reaches a requirement written inside another
  package's metadata. **Verified resolving on the Pi 2026-08-07** — `uv lock`
  lands `it8951` on `9f13613` from the override rather than from upstream's
  master happening to still be that commit.

**The compiler was the other unpinned axis**, and pinning the driver alone would
have left it open: `IT8951` builds its Cython extensions from 2023-era `.pyx`
sources and its own build-requires names `Cython` with no bound, so a PEP 517
isolated build takes whatever released most recently. `[tool.uv]
build-constraint-dependencies` holds it at `>=3.0,<4`. `requirements.txt` has no
equivalent mechanism, so that path remains exposed to a Cython 4 — one more reason
the 2024 install path is retired rather than maintained.

**If the label panel misbehaves after a rebuild, this is still the first thing to
check**: confirm the installed `it8951` is `9f13613` before looking anywhere else.

## What `pi-freeze-2024.txt` is

A `pip freeze` of the environment the 2024 loader was running on the Pi, captured
during the 2026-07-19 archaeology. **Nothing installs from it.** It is kept as
evidence of which versions the recovered code actually ran against — the frozen
`samsungtvws` in it is what dictated that plane's interpreter, and the record is
what makes that traceable rather than remembered. It is also the rollback target
for the dependency move described above.
