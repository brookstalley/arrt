---
artifact: design
version: 1
depends_on:
  - artifact: re-architecture
  - artifact: clients
  - artifact: player-contract
  - artifact: samsung-tv-state-findings
  - artifact: accessibility-spec
last_validated: 2026-10-08
---

# Labels, surfaces, and what a wall is showing

<!-- Design, 2026-10-08, from the owner's direction. Governs: how a label learns
what to say, what label outputs are, and how a caption in the image fits the same
model. Supersedes the "one process per wall drives both" rule in
`re-architecture.md` § Player outputs and `clients.md`. Backlog: #188. -->

## The owner's direction

2026-10-08, declining an interim fix that would let the HDMI wall drive the Pi's
panel: *"let's build a proper model of labels, which can be associated with any
wall. We could have a device that only shows 4 labels, which go to 4 walls living
on totally different devices. Split the label from wall functions, and keep them
in sync."*

And, the same day, two things the model must cover:

1. *"The wall controller knows the state of a display. For instance, a frame TV
   that the user is watching a movie on, when art is scheduled. The label should
   just be blank to be not-distracting."*
2. *"In the future, we might composite an artwork's name into the image shown on
   an LCD display… perhaps reserve region for a label. Don't need to design this
   now, but let's make sure our wall, controller, device, label abstractions are
   clean for this scenario."*

## Rulings (2026-10-08)

The owner's choices among options the builder wrote, with the builder's
recommendation taken in each but the first, which the owner then revised.

| # | Question | Ruling |
|---|---|---|
| 1 | Where a label learns what its wall shows | **The wall's reported display state, never the schedule.** First ruled "wait for wave 4's schedule"; revised the same day once the movie case showed that the schedule says what a wall *should* show and only its controller knows what it *is* showing. |
| 2 | The guarantee that replaces "one process drives picture and label" | **A label follows its wall's reported state.** They can disagree only between a change and its report, and a label whose wall stops reporting keeps its last caption only for a bounded time, then blanks. |
| 3 | Cardinality | **A wall has 0..n labels; a label captions at most one wall.** Mapping is server-side. A label output may live on a client with no display at all. |
| 4 | What a label shows with no signal | **A quiet card with the wall's name when the wall is unassigned or has no work; while the wall is silent, the last caption stays, and blanks once it has been silent or unreachable for 30 minutes** (the owner confirmed the number, 2026-10-08). And from the movie case: **blank whenever the screen is in use or dark**, *"to be not-distracting"*. |
| 5 | Order | **This note, then the display-state report as a small build ahead of wave 4, then label outputs and their mapping.** |

## The model

Five nouns. Each owns one thing, and nothing else decides it.

| Noun | Lives in | Owns |
|---|---|---|
| **Wall** | Programming (server) | Curatorial: which display output it uses (0..1), which label outputs caption it (0..n), and whether the display carries a caption (off, or on where the display can). Nothing device-specific. |
| **Client** (device) | A host at a wall, or anywhere | Reports its outputs and runs one controller per assigned display output and one renderer per assigned label output. A client may hold any mix: four label panels and no screen is a valid client. |
| **Output** | Reported by its client | A physical surface, of a family: **display** (`frame`, `framebuffer`) or **label** (`epaper` today). Each reports its geometry and its capabilities. A display output that can composite reports `caption` among its `label_modes` (the field exists: `heartbeat.v1` minor 2 `capabilities.label_modes`). |
| **Wall controller** | The Player, one per assigned display output | Drives the screen to match the wall's manifest, and is the **only** thing that knows what the screen is doing. Reports the wall's **display state**. |
| **Label renderer** | Wherever the label surface is | Turns *(display state, label text)* into pixels for one surface. Two kinds: a **panel renderer** (today's `EpaperSurface`, on any client) and, later, a **caption renderer** inside a display's compositor. |

### Display state

What the controller reports, whenever it changes:

| State | Means | Frame reading | HDMI reading |
|---|---|---|---|
| `showing_art` | The screen shows this work | `get_artmode` on, and the selection confirmed by the set's `image_selected` (a remote-control change included, resolved to a work id) | the framebuffer drew it |
| `in_use` | Somebody else has the screen | `PowerState` on, `get_artmode` off: television | — |
| `dark` | The screen is off | `PowerState` standby | connector reports no screen |
| `no_screen` | Nothing to drive | — | output absent |
| `unreachable` | The controller cannot tell | no answer | — |

The server adds two of its own, which no controller reports: **`unassigned`** (no
display output mapped) and **`silent`** (the last report is older than the
staleness threshold Walls already uses, `core/outputs.js` `STALE_AFTER_SECONDS`).

`samsung-tv-state-findings.md` § The states is the authority on the Frame
readings: `PowerState` does not distinguish art mode from television, and
`get_artmode` does.

### What a label says

One pure rule, run identically by every renderer, wherever it is:

| Wall's state | The label shows |
|---|---|
| `showing_art` | the work's label text |
| `in_use`, `dark`, `no_screen` | blank: somebody is using the screen, or there is none to caption |
| `unassigned`, or no work to show | a quiet card with the wall's name |
| `silent`, `unreachable` | the last caption, for 30 minutes (the owner, 2026-10-08); then blank |

That rule is the whole of the sync guarantee. Every label of a wall reads the same
record, so two panels on two devices cannot disagree with each other, and each
agrees with the screen to within the report's latency.

### Latency

The label requirement is a redraw within 15 s of a picture change
(`nonfunctional-requirements.md`). Today the server learns a wall's work from a
heartbeat written at most every 60 s, and on a Frame its `current_work_id` is
wrong after a remote-control change. So the display-state report is its own
signal, not a heartbeat field on the heartbeat's cadence:

- the controller writes it **on change**, and the existing pull forwards a changed
  file within about a second (`pull.py`);
- the server keeps each wall's latest state, which Walls, History and every label
  read;
- a label renderer polls a small label document per label output (about once a
  second, with an ETag) and redraws only when it changes, since an e-paper redraw
  flashes for 1.5 to 1.9 s.

### Captions in the image (not designed; kept open)

Nothing here is built for it, and these rules keep it possible:

- **Label text stays plain data that doesn't care how it's rendered**: the ten keys
  `library/readiness.py` builds, text only (`player-contract.md` § The manifest).
  Panel layout never leaks into it.
- **The typesetter takes a target region, not a panel**: a size, a viewing
  distance, a type floor (`accessibility-spec.md`). `panel/layout.py` and
  `panel/legibility.py` already work from geometry; a caption is the same typesetting
  into a region the display's compositor reserves.
- **A caption is drawn by the wall's own controller**, because it is part of the
  image (on a Frame, burned in before upload). It needs no sync, and the same
  table applies trivially: a caption is only ever on screen with its art.
- **Reserving the region is the compositor's**, which wave 4 moves to the Player
  with "the mat sized for the caption" (`re-architecture.md` § Compositing moves
  to the Player).

## What changes, in order

1. **Display state** (a small build, ahead of wave 4). The controllers report it on
   change; the server keeps it; Walls reads it in place of `current_work_id` alone;
   today's panel, still on the Frame loop, follows the table above.
   Contract: a minor bump of the heartbeat, or a document of its own beside it,
   decided in that plan.
2. **Label outputs and their mapping** (#188, after #181). Clients report label
   outputs; the server maps a wall's labels; a label renderer runs per label output
   on any client; `EPD_DEVICE`'s refusal without a Frame goes
   (`postarr/src/postarr/config.py`).
3. **Caption mode** (wave 6+, with the Player's compositor).

## Open questions

- **Two thresholds, on purpose.** Walls calls a report stale after three heartbeats
  (is the report current?); a label blanks after 30 minutes (should the room lose its
  caption?). They answer different questions.
- **Several Frames per client** (#184) is unchanged by this, and simpler under it:
  each Frame is a display output with its own controller.
