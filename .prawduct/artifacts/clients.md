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
is the Frame. `re-architecture.md`'s "one process per wall drives both the
picture and the label, so they can never disagree" is kept *per worker*: a
wall's picture and label are still decided in one place. The supervisor polls
`GET /client`, starts a worker for a newly assigned wall, stops one for a wall
taken away, and reports outputs.

**The HDMI output** draws the render fitted to the connector's screen, with no
desktop, as the service user. The technology is chosen by a research pass and
a spike on the Pi (Chunk 04); waking or switching a TV's input over CEC is a
power act and is not done automatically (`nonfunctional-requirements.md`
§ The television belongs to whoever is using it).

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
