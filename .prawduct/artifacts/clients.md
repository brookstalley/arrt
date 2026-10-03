# Clients: a Player install that drives one or more walls

<!-- Requirements and design, 2026-10-02, from the owner's direction. The build
is `build-plan-clients.md`. Governs: the Player contract's transport and
authentication, Programming's walls, the Player's process model. -->

## What this is

The owner, 2026-10-02, with the Frame in use: "Let's skip the frame, I'm
watching stuff on it. Instead, let's get the rpi ready to show images over
hdmi. This gets at an important client abstraction… a client can control one
or more walls."

Today a Player is configured for exactly one wall (`WALL_ID`, `WALL_TOKEN`),
the server knows walls and nothing of what drives them, and the only output a
Player has is a Samsung Frame over its network API. This makes the **client**
a thing the server knows — an installed Player on a host, with one credential,
driving any number of walls, each on one of the client's outputs — and adds
the **HDMI output** the re-architecture planned for wave 6+ (§ Player outputs,
"framebuffer").

## The owner's rulings, 2026-10-02

1. **Clients are first-class server records.** A client has a name, one client
   token, and the walls it controls. The host is configured with the server's
   address and its token only, and learns its walls from the server: adding a
   wall to a client needs no edit on the host. The Walls screen shows which
   client drives each wall. (*arr precedent: Settings › Download Clients — the
   server's list of the external programs it works with.)
2. **An HDMI wall shows the server's render, fitted to the screen**: the same
   matted picture the Frame gets, scaled to fit. Composing per screen (the
   re-architecture's wave 4) comes later.
3. **The Frame is skipped for now**; the Pi's player was stopped and disabled
   on 2026-10-02 so nothing reaches for a set someone is watching.
4. **The HDMI screen will be a TV or monitor the owner plugs in**; until then
   the output is built and tested against a stand-in.

## The model

**Client** (Programming): an id, a name, the verifier of its token (the token
shown once, kept as SHA-256, exactly as wall tokens were), when it was issued.
Nothing about the device: no address, no geometry, no model.

**Wall** gains two fields: the client that drives it (nullable — a wall nobody
drives is an ordinary state) and the **output** it is shown on, a name the
client reported (`hdmi-a-1`, `frame`). Both are *assignment*, a curatorial act
like hanging a theme.

**What stays on the client, and why.** The client knows its outputs: which
HDMI connectors exist and are connected and at what size, and the Frame's
network address (`TV_ADDRESS`, as today). It **reports** them to the server in
a client heartbeat, a file under the art root as the wall heartbeats are, so
the curator can choose an output by name. The server stores only the name it
was given. This keeps the `Wall` record's ruling ("geometry, network address,
panel model … are per-device runtime state and are permanently forbidden
here") for everything but the one new fact the owner ruled the server must
hold: which client, on which output.

`[DECISION: the server records which client drives each wall and on which of its outputs, by name | the owner's ruling 1 needs the server to tell a client its walls; the output's name is the smallest fact that lets a curator place a wall on a screen without the device's geometry or address entering the catalogue, which the Wall record's ruling still forbids | owner can veto]`

## The contract change

Transport stays HTTP and pull; the per-wall routes stay. What changes:

| Route | What |
|---|---|
| `GET /client` (new) | This client's walls: `{client_id, name, walls: [{wall_id, name, output}]}`, with an `ETag`. Polled about every 30 s |
| `POST /client/heartbeat` (new) | The client's outputs: name, kind (`frame`, `framebuffer`), connected, screen size. `204` |
| `GET /walls/{wall_id}/manifest`, `POST /walls/{wall_id}/heartbeat` | Unchanged in shape; admitted for the walls assigned to the presenting client |
| `GET /media/sha256-{hex}` | Unchanged; any valid client token |

**Every request carries the client's token.** A missing or unknown token is
`401`; a valid token naming a wall that is not this client's is `403`. **Wall
tokens retire**: the one deployment is moved to a client token in the same
change (no transition is kept — backwards compatibility was not asked for and
there is one Player). This is a breaking change to the Player contract's
transport, recorded in `player-contract.md`.

## The Player

One process per **client**, supervising one worker per assigned wall. Each
worker is today's wall loop (manifest, cache, rotation, heartbeat) bound to
one output; the label panel, where present, belongs to the wall whose output
is the Frame.

> **Direction changed 2026-10-02 (the owner): labels become outputs.** "Each
> client provides zero or more display outputs, and zero or more label
> outputs. Mappings are server side." A client's e-ink panel will be reported
> like its HDMI connectors and Frames, and the server will map a wall's label
> to it, so the panel can caption an HDMI wall or any Frame without an edit on
> the host. Until that plan lands (it follows this one, after #181), the
> sentence above is what runs: an HDMI wall has no label.

`re-architecture.md`'s "one process per wall drives both the
picture and the label, so they can never disagree" is kept *per worker*: a
wall's picture and label are still decided in one place. The supervisor polls
`GET /client`, starts a worker for a newly assigned wall, stops one for a wall
taken away, and reports outputs.

**As built (`build-plan-clients.md` Chunk 03), where it adds to the above:**

- **The last good client document is kept** in `CACHE_DIR`, so a client
  restarted while the server is down starts the walls it last knew, each from its
  own cache, rather than none.
- **A worker that fails is restarted by the supervisor**, logged at ERROR with a
  wait that doubles to five minutes. A wall's pull dying ends that wall's worker
  rather than the process: one process now drives several walls, and stopping it
  over one wall's fault would blank the others. The supervisor's own failure
  still ends the process for systemd to restart.
- **The Frame is reported `connected: true` with no screen size.** It is a
  television on the network rather than a cable this host can sense; whether it
  answers is reported per wall (`television_reachable`), and its size is the
  server's to know, since the render arrives composed for it.
- **A wall assigned to an output this client lacks**, or to an output another
  wall already holds, is reported once at ERROR and not started; the wall goes
  on being shown nowhere until the assignment changes.
- **A wall id that is not a plain directory name is refused**, since it names
  the wall's directory under `CACHE_DIR`.
- The Frame's pairing token now defaults to `CACHE_DIR/token_file`; a Player
  paired under the old default points `TV_TOKEN_FILE` at it.
- The Frame's binding store (`display-state.sqlite`) moves from `ART_ROOT/` to
  the wall's directory under `CACHE_DIR`, and nothing reads `ART_ROOT` any
  more. A Frame Player upgraded in place starts with no record of what it
  uploaded and uploads its theme to the set again, unless the old store is
  copied into the wall's directory first.
- **A Frame store written by a newer Player parks that wall**: said once at
  ERROR, the wall not shown until a rollout, every other wall running.
- **A client document that cannot be cached** (a full disk) is still followed;
  said once, and a restart while the server is down starts from the last one
  that was cached.

**The HDMI output** draws the render fitted to the connector's screen, with no
desktop, as the service user: kernel mode setting through `libdrm`, chosen and
measured on the Pi in `hdmi-output-findings.md`. Waking or switching a TV's
input over CEC is a power act and is not done automatically
(`nonfunctional-requirements.md` § The television belongs to whoever is using
it). What it does as built:

- **Fitted whole, on black**, at the first mode the kernel lists for the
  connector, which is the size the client heartbeat reports.
- **The service user must be in group `video`** to open the card; a Player
  that cannot is logged once per episode, keeps rotating, and tries again on
  every poll.
- **A screen that is absent is not an error**: said once (`screen.absent`), the
  wall rotating unseen. When a screen arrives, comes back or changes size, the
  current picture is drawn on the next poll (`screen.returned`).
- **The Player holds the screen while it runs.** When it stops, the kernel
  gives the screen back to the text console, which is what a wall shows while
  its Player is down.

## What the stored data must answer

Added to `data-model.md` § What this data must answer when Chunk 01 designs
the fields:

- Which client drives this wall, and on which output?
- Which walls does this client drive (the client's own question, over HTTP)?
- Is this request from a client allowed this wall?
- What outputs did this client last report, and when?

## Out of scope

Composing per screen (wave 4); caption in the mat (wave 6+); several clients
showing one wall in sync; CEC; the Frame (skipped by the owner for now; it is
one output kind among two, and comes back by assigning a wall to the `frame`
output).
