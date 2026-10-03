---
artifact: build-plan
version: 1
scope: clients
branch: feature/clients
partition: Chunks 01, 02 and 03 each built by one delegate in an isolated worktree, 02 and 03 in parallel (02 touches only the server's static client, MCP and the IA; 03 touches only `postarr/`, the Player's settings and the display suite's contract test — disjoint files); the coordinator reviews and merges each. 04 follows 03 (both change the Player) and 05 is operations on the owner's machines, both run by the coordinator
depends_on:
  - artifact: clients
  - artifact: player-contract
  - artifact: build-plan-nas
governed_by:
  - artifact: player-contract
    dispositions:
      - "transport: every request carries the wall's token; per-wall tokens → amended by the owner's ruling of 2026-10-02 (clients first-class): every request carries the client's token, admitted for that client's walls; two new routes, GET /client and POST /client/heartbeat. Breaking for a Player configured with a wall token; the one deployment moves in the same change (Chunk 05). Recorded in player-contract.md and contract/routes.json"
      - "every failure keeps the cache; the wall going black is worse than incomplete → binds Chunks 03-04: a client that cannot reach the server keeps every worker on its last good manifest"
  - artifact: architecture
    dispositions:
      - "operation logic lives only in the service layer → binds Chunks 01-02: clients, assignment and admission are Programming services; HTTP and MCP bind them"
      - "Library/Programming seam → conforms: clients and wall assignment are Programming's; the Library is untouched"
      - "seam rule 3, no new cross-seam foreign keys → conforms: walls.client_id references clients, both Programming's"
  - artifact: data-model
    dispositions:
      - "the Wall record's ruling: per-device runtime state (geometry, address, model) never in the catalogue; which display serves which wall is display-plane configuration → [DECISION in clients.md: the server records which client drives each wall and on which output, by name; geometry and address stay on the client, reported in a client heartbeat file as wall heartbeats are | the owner's ruling 1 | owner can veto]"
      - "a persisted format is a lock-in decision; questions first → binds Chunk 01: the four questions in clients.md become Q-rows before fields"
  - artifact: security-model
    dispositions:
      - "the Player's credential: one token per wall, shown once, stored as SHA-256, constant-time compare, never logged → carried over to the client token unchanged in kind; the wall token retires"
      - "LAN-only, no login on the curator surfaces (amended 2026-10-02) → conforms: nothing here changes the curator surfaces' exposure"
  - artifact: information-architecture
    dispositions:
      - "the *arr layout: a page an *arr app has goes where it puts it → Settings › Clients, where Radarr keeps Settings › Download Clients; the Walls screen keeps its place and gains each wall's client and output"
  - artifact: nonfunctional-requirements
    dispositions:
      - "the television belongs to whoever is using it: no unattended power key → binds Chunk 04: no CEC power or input switching; an HDMI output draws only when its screen is already on and connected"
  - artifact: re-architecture
    dispositions:
      - "§ Player outputs: framebuffer backend (wave 6+); one process per wall drives picture and label → the HDMI output is pulled forward by the owner's direction; one process per client supervising one worker per wall keeps picture and label decided in one place per wall"
last_validated: null
---

# Build Plan — Clients, and an HDMI wall

## What this plan is

`clients.md`: the server learns which **client** (an installed Player)
drives which walls, a client drives any number of walls on its outputs, and a
Pi gains an **HDMI output** that shows the server's render fitted to the
screen.

| Chunk | What |
|---|---|
| 01 | Clients on the server: records, admission by client token, `GET /client`, `POST /client/heartbeat`, the contract |
| 02 | Settings › Clients, and each wall's client and output on the Walls screen; MCP |
| 03 | The Player as a client: one process, one worker per assigned wall |
| 04 | The HDMI output |
| 05 | Deploy: the server to the NAS, the Pi as a client on HDMI; the owner's look |

**Not in this plan:** composing per screen (wave 4), caption in the mat, CEC,
the Frame (an output kind that stays supported and untested here, the owner
having skipped it), the store split.

## What I would do differently

**Keep the change to the contract to one breaking step.** Wall tokens retire
in the same change rather than living beside client tokens, because there is
one Player and no transition to protect; a dual scheme would be the code a
second deployment never needs. The cost is that the Pi's player cannot run
against the new server until Chunk 05 moves it — acceptable, since it is
stopped by the owner's choice today.

## Requirements Confidence

**Medium.** The model and contract are clear from the rulings. Open: the HDMI
drawing technology (research pass running; Chunk 04 spikes it on the Pi), and
the screen the owner plugs in (its size and whether it is on when the Pi
starts).

Open assumptions:
- [ASSUMPTION: a client's outputs are named by the client (`hdmi-a-1`, `hdmi-a-2`, `frame`) and the curator assigns a wall to one by that name | MED impact | owner can correct]
- [ASSUMPTION: a client polls `GET /client` about every 30 s, so assigning a wall reaches the screen within a minute | LOW impact | owner can correct]
- [ASSUMPTION: an HDMI screen that is off or unplugged keeps the wall's worker running and reports `connected: false`, drawing again when it returns | LOW impact | owner can correct]
- [ASSUMPTION: one client per host; a host with two Players is two clients | LOW impact | owner can override]

## Status

- [x] Chunk 01: Clients on the server
- [x] Chunk 02: Settings › Clients and the Walls screen
- [ ] Chunk 03: The Player as a client
- [ ] Chunk 04: The HDMI output
- [ ] Chunk 05: Deploy and look

### Chunk 01: Clients on the server

The `clients` table and two `walls` columns (`client_id`, `output`) with a
migration; Q-rows in `data-model.md`; a Programming service to add, rename,
remove a client, issue and rotate its token, and assign or unassign a wall
(client and output); admission by client token for the Player routes (401 for
an unknown token, 403 for a wall that is not the client's), retiring wall
tokens; `GET /client` with an `ETag`; `POST /client/heartbeat` written as a
file beside the wall heartbeats; `contract/routes.json`, a schema for the
client document and the client heartbeat with fixtures, and `player-contract.md`
§ Transport rewritten.

Done when: service tests for each operation; HTTP tests for admission (own
wall, another client's wall, unknown token, a retired wall token refused), for
`GET /client` (assigned walls only, `ETag`/`304`) and the client heartbeat;
contract tests against the schemas and fixtures from all three suites; the
migration tested on a copy of the dev catalogue.

*Chunk 01 verified 2026-10-02, and one Done-when moved:* a copy of the dev
catalogue (`~/samsung-art`, 20 tables, 1 wall with the two wall-token columns,
1 hanging, 1 directive) migrated on first start under this code: the walls
table became `id, name, created_at, client_id, output`, the `clients` table was
created, the foreign key `walls.client_id → clients.id` is present, the wall,
its hanging and its directive kept, `PRAGMA integrity_check` ok and
`foreign_key_check` empty; the API listed the wall with no client. **Moved to
Chunk 03:** "contract tests against the schemas and fixtures from all three
suites" is met by the root and curation suites; the display suite gets its
test of `client.v1` and `client-heartbeat.v1` in Chunk 03, which is where the
Player starts reading the one and writing the other (the builder's call,
2026-10-02, the owner can veto).

### Chunk 02: Settings › Clients and the Walls screen

**Visual change:** yes

Settings › Clients: list, add (token shown once), rename, rotate, remove;
each client's walls with an output picker from its last reported outputs, and
its heartbeat's age. The Walls screen: each wall says which client and output
show it, or that none does. MCP: `art_display` actions for clients and
assignment. `information-architecture.md` rows.

Done when: browser tests for each act and the token shown once; MCP parity
tests; screenshots; an operator-verification entry.

*Chunk 02 verified 2026-10-02 (delegate, merged `7325384`; review
`rev-20261003T030831Z-cfc36e3f`, 0 findings):* curation 3214, browser 604, root
402 passed after the merge; screenshots of the Clients page (empty, populated,
token once) and the Walls screen at 1280 and 390 px were looked at.

### Chunk 03: The Player as a client

`CLIENT_TOKEN` and `SERVER_URL` configure the Player; a supervisor polls
`GET /client`, starts one worker per assigned wall bound to its output, stops
workers for walls taken away, and posts the client heartbeat with the outputs
it can drive. Each worker is today's wall loop, unchanged in behaviour. The
Frame output keeps working behind the same interface.

Done when: tests with the server double for a wall assigned, a wall taken away,
the server unreachable (workers keep their caches), and two walls on two
outputs at once; the client heartbeat validated against its schema; the display
suite's contract test reading `client.v1` and `client-heartbeat.v1` and their
fixtures (moved here from Chunk 01); `.env.example`'s Player section rewritten
for `CLIENT_TOKEN`.

### Chunk 04: The HDMI output

0. verify-api: the research pass and a one-hour spike on the Pi, drawing a
   render to a connector as the service user with no desktop.

**Foreign API:** the chosen DRM/KMS drawing library (named by the spike)

An output that draws a render fitted to its connector's screen, reports the
connector's presence and size, and survives the screen being off or
unplugged. Tested against a stand-in surface in the suite; exercised on the
Pi's real connector in Chunk 05.

Done when: the spike's findings recorded (`hdmi-output-findings.md`); unit
tests for fitting (letterbox for a non-16:9 screen) and for hotplug states;
the output running on the Pi against a test image.

### Chunk 05: Deploy and look

**Type:** cumulative-final

The server to the NAS (`bin/arrt-app.sh`), a client added for the Pi, its
token on the Pi, a wall assigned to its HDMI output; the owner plugs in the
screen and looks; then the cumulative review.

Done when: the screen shows the wall's art from the NAS and changes on the
rotation; the owner has looked; the way back is written down.

## Verification strategy

The server chunks are tested through HTTP and MCP; the Player chunks against
the server double and then the Pi's real connector; Chunk 05 is the whole path
on the owner's hardware.

## Governance checkpoints

After Chunk 01 (the contract and access change everything else uses), and the
cumulative review at Chunk 05.
