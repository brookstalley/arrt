---
artifact: design
version: 1
depends_on:
  - artifact: re-architecture
  - artifact: player-contract
  - artifact: clients
  - artifact: labels-and-surfaces
  - artifact: data-model
  - artifact: nonfunctional-requirements
last_validated: null
status: direction ratified 2026-10-08, nothing built against it yet
---

# Feeds and players: one Player core, many platforms, private walls and public channels

<!-- Design, 2026-10-08, from the owner's direction. Governs: the shape of the
Player contract's major 2 (a feed, plus an optional control layer), how a display
relates to the client that drives it, where rendering happens, publishing public
channels, and how Player logic is reused across platforms. Amends
`re-architecture.md`, `player-contract.md`, `data-model.md` constraint 13 and
`nonfunctional-requirements.md` § The mat is geometric; each carries a dated
pointer here. -->

**Read this before wave 4 builds major 2.** Major 2 is still a draft
(`player-contract.md` § Major 2), and this note changes its shape. That is the
cheapest moment to change it.

## The owner's direction

2026-10-08, the goals:

> "1. Separate the player ("poster") from the server ("arrt"). 2. Support
> multiple players using different platforms (rpi like now, apple TV, mac/windows
> screensavers) 3. Correctly abstract display controller from wall target. …
> samsung frame is a network target and we may want a future macos client to
> drive the frame, or even the apple tv client (if possible). And the labels are
> independent of the displays … 4. Move the player to a different repo. 5.
> Maximize re-use of logic and documentation for players on different platforms"

Two corrections to the first proposal, the same day:

> "Clients should not find network devices, should take explicit configuration.
> We don't need two rpis finding the same frame TV and all of the UX complexity
> that brings."

> "Rendering cannot be on the server, as clients may have dynamic elements (a
> window on macos may be resized) and walls may have preferences (overlay title
> and credit for first and last 30 seconds, fade those in, show different text
> sizes, etc)."

Then the two use cases the architecture must hold:

> "a. In my house. I have a samsung frame, an rpi that drives an HDMI display and
> eink label for the display in my office, and the rpi drives the samsung frame's
> pictures. I have a mac that I'd like to use as a screensaver, and an apple on a
> different TV that should display art. I will put together themes and assign to
> walls (different styles in office vs living room, coordinated displays from the
> same artist or topic on the apple TV + samsung frame).
>
> b. As a public service, with public domain art only, where someone could
> download the apple tv app, choose one of maybe 5 themes, and it would default
> to a server in the cloud that I own and just passively rotate art, without the
> server knowing or caring if there are 0, 1, or 1000 apple tv apps connecting to
> it. … that will come later. But the architecture should accommodate it"

And on the public channels' mats: "agreed public feed maxxes out at 4k. We will
have different mat options for public feed to: no mat (black), proportional mat
(what we're doing today), full mat (no black, all mat color outside of artwork).
those can just be different static files, OR we could enlighten the client to do
it".

## Rulings (2026-10-08)

The owner approved the builder's proposals "on all counts". Each row says whose
proposal it was.

| # | Question | Ruling |
|---|---|---|
| 1 | How a client learns which network displays it drives | **Explicit configuration only; no discovery.** One network display, one client. (The owner.) |
| 2 | Where a work is rendered for a screen | **On the client, always.** Server-rendered images per screen were proposed by the builder and rejected by the owner (geometry changes at runtime; presentation is time-dependent). Wave 4's "compositing moves to the Player" stands. |
| 3 | The contract's shape | **A feed, plus an optional control layer.** The Player core consumes only a feed; control is switched on for a paired client. (The builder's proposal.) |
| 4 | Versioning when Players cannot be upgraded | **Each major at its own URL**, published side by side while readers of it may exist; one mechanism for home walls and public channels. Replaces "the server publishes one major for all walls". (The builder's proposal.) |
| 5 | Rights on public channels | **A public channel carries only works whose chosen image is `public_domain`; `unknown` is refused.** Private walls are unchanged: rights gate nothing there. (The builder's proposal; it is constraint 13's own reopen trigger.) |
| 6 | Public media size | **4K on the long edge at most** for public channels. (The owner.) |
| 7 | Public mat options: static variants, or the client | **The client draws the mat.** The feed specifies only the mat colour; the mode (none, proportional, full) and the mat's width are the client's to decide (§ Mat modes). (The builder's recommendation; the owner confirmed it and extended it to the width: "specify mat color, let client draw … then clients can decide about no mat, proportional mat, full mat".) |
| 8 | Work metadata on screen | **Optional, shown by the client by preference**: which facts, if any, is a presentation setting in every layer (§ Presentation settings come in three layers). (The owner.) |
| 9 | Where a network display's configuration lives | **On the client's host**, as `TV_ADDRESS` is today: "frame is configured on Pi". The server never holds a display's network address. (The owner.) |
| 10 | The channel list a public app offers | **A published index document**, so channels change without an app update. (The builder's proposal; the owner: "good call".) |

## The model

| Noun | Lives in | Owns |
|---|---|---|
| **Feed** | A document at a URL | What to show and when: the schedule (absolute slots), the works it names (presentation master, mat colour, label text) and default presentation settings. Read-only, the same bytes for every reader, cacheable. |
| **Channel** | A published feed with no walls behind it | A public theme. Anonymous, static, hosted anywhere. The server never learns who reads it. |
| **Wall** | Programming (server) | Curatorial: a private feed (its manifest), its display (0..1), its labels (0..n), its presentation settings. Unchanged from `labels-and-surfaces.md` § The model. |
| **Display** | Programming (server), new | One physical screen, with an identity of its own: a Frame, an HDMI connector on a host, a Mac's screen, a TV behind an Apple TV. Driven by exactly one client. A wall names a display, never a client and an output name. |
| **Client** | A host | One install with one token. Runs a controller per display it drives and a renderer per label output it holds. Reports its displays' state and capabilities. |
| **Control** | The server's routes for a paired client | Client identity, `GET /client`, heartbeats, display state, label outputs, scenes. Absent for a channel reader. |

### Feed and control

| | **Feed** | **Control** |
|---|---|---|
| Carries | Schedule, works, label text, default presentation settings; media by hash | Client document, client and wall heartbeats, display state, label documents, scenes, pairing |
| Home walls (case a) | Each wall's manifest is a private feed, behind the client's token | On |
| Public channels (case b) | One public feed per channel and major, no token | Off |

**The Player core only ever consumes a feed.** A Player in "public" mode is the
same core with control off and a channel URL in place of a wall's. A scene is a
control-layer concept that reaches the Player as a republished feed
(`player-contract.md` § What happens to `show_now` and `next` already works this
way), so the core needs nothing extra for it.

`[DECISION: the major 2 manifest is a feed document plus control routes, and a wall's manifest is a private feed | the public case needs a reader the server knows nothing about, and a feed that serves both cases keeps one Player core and one renderer; the wall-specific parts (identity, heartbeats, display state, labels) already travel on their own routes | builder's proposal, owner approved 2026-10-08]`

### Displays are configured, never discovered

- **A network display is configured explicitly, on exactly one client.** Nothing
  scans the network. Two clients can never claim one Frame, because only one is
  ever told about it, so no lease or arbitration is needed.
- **Configured on the client's host** (ruling 9). The Pi holds the Frame's
  address, as `TV_ADDRESS` does today. The server never stores a network
  address, so `clients.md`'s rule against device facts in the Wall record
  extends unchanged to the Display record.
- **The display has its own server record**, so a wall names the display and
  the display names its client. The client reports each configured display with
  an identity read from the device itself (for a Frame, the set's own device
  id), not the name the client chose, and the server keys the record on that.
  Moving the Frame from the Pi to a Mac is a configuration edit on both hosts;
  the Mac then reports the same identity, the record's client changes, and no
  wall or label mapping moves.
- **Two clients reporting one display is a configuration fault**, not a contest:
  the server shows it to the curator and assigns the display's wall to neither
  until one host's configuration is fixed. Nothing on the clients arbitrates.
- **Attached outputs** (HDMI connectors, e-ink panels, a Mac's screen) are
  reported by their host as today (`clients.md`) and become display or label
  records when assigned.
- **Display state** (`labels-and-surfaces.md` § Display state) is reported by
  the display's one client. Labels follow it whichever client holds the label, so
  the office case (the Pi's e-ink panel captioning an HDMI wall) and a split case
  (an Apple TV showing art, a Pi's panel beside it) are the same mechanism.

## Rendering is the client's

Everything between a work and pixels happens on the client: the mat, the
caption or overlay, its timing and fades, and type sizes. The server sends
**data**; the client decides **pixels**, because only it knows its current
geometry (a resizable window) and the current time within a slot.

### Presentation settings come in three layers

1. **Feed defaults**: what a channel or a wall's manifest carries.
2. **Wall settings** (home): the curator's choices in Programming, already in
   major 2's `settings`, widened below.
3. **Device preferences**: what the viewer chooses on the device (a public
   viewer asking for larger text). Local, never reported.

A later layer overrides an earlier one, key by key. Major 2's `settings` grows to
carry: label mode, a **mat mode** the client may honour (§ Mat modes), overlay timing (for example the
first and last 30 seconds of a slot), fade durations, text scale, viewing
distance, and **which facts about the work an overlay shows**.

**The work's metadata travels as data and is shown by preference** (the owner,
2026-10-08: "metadata about the work could also be optionally rendered by the
client according to user preferences"). The feed carries the label's facts as
plain text keys, as major 1's `label` already does (`player-contract.md` § The
manifest). Which of them appear, whether any do, and when, is a setting in all
three layers: a channel's default, a wall's choice, a viewer's preference. So a
public viewer can turn the title and credit off, or show only the artist, with
no change to what is published. A field the feed lacks is simply not shown.

### Mat modes

| Mode | What the client draws |
|---|---|
| `none` | The work fitted on black |
| `proportional` | The work in a mat of the work's shape, black beyond (today's rule, `nonfunctional-requirements.md` § The mat is geometric) |
| `full` | The work in mat colour to every edge of the screen, no black |

**The feed specifies only the mat colour; the client decides the rest** (ruling
7): which mode, and how wide the mat is. The client draws all three from one
presentation master and the work's mat colour. A client that knows its screen's
pixel density, as the Pi does for a configured Frame, keeps the physical rule
(`nonfunctional-requirements.md` § The mat is geometric: a width in inches,
bottom weighted). One that does not, such as an Apple TV or a resizable window,
uses a width relative to the screen, and that fallback is part of the layout
spec its conformance vectors pin, so every platform without a density computes
the same mat. A wall setting or a device preference may name a mode, and the
client applies it where it can. Static variants were the alternative and
are not taken: they would triple the public media, bake the mat into the master
that is defined as having none (`re-architecture.md` § Compositing moves to the
Player), and fix one screen shape, when `proportional` and `full` both depend on
the reader's own aspect ratio. A public viewer's mat mode is a device preference
over the channel's default.

`[DECISION: the published media carries no mat and the feed carries only the mat colour; mode and width are the client's | three static variants would multiply public bandwidth and storage by three and still be wrong for any screen shape but the one they were made for | builder's recommendation, owner confirmed 2026-10-08]`

### What a display reports it can do

A display's capabilities (heartbeat minor 2 `capabilities`, widened) say which
settings it can honour, and Programming offers a wall only those. **A Frame
cannot time an overlay**: a caption on a Frame exists only burned into the image
before upload (`re-architecture.md` § Compositing moves to the Player), so it is
static for the whole slot. So `label_modes` distinguishes a static caption from a
timed overlay with fades. **Geometry that changes at runtime** (a window) is
reported as it changes; Programming's adequacy judgement ("too small for this
wall") uses the largest size reported recently, not the latest.

## Public channels

- **Published, not served.** Arrt builds a channel's feed and writes it, with
  the media it names, to static hosting behind a CDN. The household's Arrt can
  do this: no public server runs, nothing at the house is reachable from the
  internet, and the cost follows bandwidth, not viewers. A cloud Arrt stays
  possible and changes no contract.
- **Public domain only** (ruling 5). The publish step refuses a work whose chosen
  image is not `public_domain` (the image instance's own rights status, or its
  source's where the instance has none), and says which works it left out.
- **Media at most 4K on the long edge** (ruling 6): a public copy of the
  presentation master, still not fitted to any screen.
- **A longer horizon and a daily republish.** A week's schedule, republished
  each day, so a reader that cannot reach the CDN keeps rotating, and the replay
  rule (`player-contract.md` § Time) carries it beyond that.
- **A published channel index** (ruling 10) lists the channels and the majors
  each is published at. The app ships knowing only the index's URL.
- **Every viewer of a channel sees the same work at the same moment**, because
  the schedule is absolute. Nothing per-viewer is computed.
- **Each major at its own URL** (ruling 4), for example
  `channels/{channel_id}/v2/feed.json`, kept published while an app that reads
  it may exist. The URL the app ships with names a domain the owner controls,
  never a storage provider's hostname, so hosting can move without an app
  update.

## Versioning when Players cannot be upgraded

`player-contract.md` § The cutover upgrades every Player first and then switches
the server, which assumes the operator can upgrade every Player. An App Store
install updates when its owner lets it. So **each major lives at its own URL**,
and a Player requests the highest major it reads. For a home wall that means the
server serves a wall's feed at each major it still builds, and retires a major
once no client's heartbeat lists it in `manifest_majors`. For a channel, a major
is retired by decision, not by evidence, because nothing reports.

## Reuse across platforms

Rendering on the client means every platform draws. What is shared is
everything above the paint call.

| Layer | What | How it is shared |
|---|---|---|
| **Settings** | The three layers above, as data | The contract |
| **Layout and timeline** | A pure function: (geometry, settings, label text, slot start and end, now, a text-measuring function) → regions, type sizes, and each element's opacity over time | A written spec, plus **conformance vectors** in `contract/`: inputs and expected outputs that every Player's suite runs |
| **Painting** | Native image and text drawing (Pango, CoreText, DirectWrite), windows, resizes, the display driver | Per platform. This is what stays irreducible |

- **The text-measuring function is passed in**, so layout stays pure and
  testable while each platform measures with its own text stack. Vectors are
  checked to a tolerance, not pixel for pixel, because text stacks differ.
- **The Pi's label code is the reference implementation**
  (`postarr/src/postarr/panel/layout.py`, `legibility.py`). Its behaviour is
  written out as vectors before a second platform ports it.
- **Behaviour vectors beyond layout**: (feed, now) → the slot or scene to show;
  (display state, label document, age) → what a label shows; invalid feeds →
  refuse and keep the last good one. Today's fixtures test parsing only.
- **One Player spec**, language-neutral, gathers the rules now spread across
  `player-contract.md`, `clients.md`, `labels-and-surfaces.md` and
  `nonfunctional-requirements.md`: the cache, "every failure keeps the cache",
  refusal, replay, the label table, display states, the guardrails.
  `samsung-tv-state-findings.md` stays the Frame driver's spec for any language.
- **No shared native core yet.** Port layout to Swift for the first non-Pi
  Player against the vectors and measure where the two disagree. **Revisit
  when** a third platform is committed to and the layout layer is still growing;
  the likely shape then is one core with generated bindings (for example Rust
  with bindings for Python, Swift and C#).

`[DECISION: reuse comes from the contract, a Player spec and conformance vectors, not from a shared code library, until the revisit trigger above | with two platforms the cost of a cross-language core (build toolchains on a Pi, tvOS and Windows) exceeds the cost of porting about 1,200 lines against vectors | builder's proposal, 2026-10-08]`

## Platforms

Measured or sourced 2026-10-08 in `apple-platform-findings.md`, which carries
the evidence and labels each fact; this section keeps only what the design
depends on. **Every fact still marked unverified there is verified on hardware
before its platform's plan is written**: for tvOS, the connection to a Frame;
for macOS, the saver's local-network permission and an external TV's reported
size.

- **Apple TV.** tvOS does not let third-party apps be screensavers, so the
  Player is a foreground app. **A backgrounded app is suspended and goes
  silent**: it can send at most one last heartbeat as it leaves, so the server
  sees a silent wall, not `in_use`. Two modes: a public channel with no setup, or
  pairing with a household Arrt. tvOS has no local-network permission; the
  obstacle to driving a Frame is its self-signed certificate, which Network
  framework can accept and `URLSession` likely cannot. The connection code
  compiles; nothing has run against a set. `UIScreen` gives no physical size, so
  the relative mat width applies.
- **macOS screensaver.** It runs inside Apple's sandboxed `legacyScreenSaver`
  host, which never stops old instances or exits. So the saver **tears itself
  down on `com.apple.screensaver.willstop`**, and can write only its own
  container's cache. A screensaver wall is unreported most of the time, which is
  normal for it, not a fault (`silent` in `labels-and-surfaces.md` § Display
  state already covers it). It must draw from its cache immediately on start.
  **Whether a saver can be granted macOS's local-network permission is
  unverified and is this platform's largest risk**; if it cannot, a companion
  app fills a cache the saver only reads. That is tested on a real Mac before
  this Player's plan is written.
- **Text.** CoreText measures what the layout needs, so the label ports; vectors
  check rules, not pixels (§ Reuse across platforms).
- **Windows screensaver.** Last; a .NET Player. Not investigated.
- **Pairing.** A token cannot be typed on a TV remote. Control gains a pairing
  flow: the device shows a short code, the operator approves it in Arrt, and the
  device receives its client token.

## Repository shape after wave 5

- **Arrt** owns `contract/`: schemas, fixtures, conformance vectors and the
  Player spec, released by tag.
- **Postarr** is one repository holding every Player: the Pi Player (Python, the
  reference), one Swift package with a tvOS app target and a macOS screensaver
  target, and later Windows. It pins a contract tag and its hash, and every
  Player's suite runs the same vectors.
- **Before the split**, the Pi Player's two wall loops are reshaped: the Frame
  loop (`daemon.py`) and the HDMI loop (`screen.py`) duplicate the wall logic
  (adopt, directive, rotate, advance, show, beat), and the Frame loop also holds
  the label. They become one wall loop, a display driver per kind, and a label
  renderer. This is done in wave 4, when rotation leaves the Player, rather
  than before it, so the code about to be deleted is not refactored first.

## What changes, in order

1. **#188, widened**: displays become server records with one client each;
   label outputs and their mapping as planned.
2. **Wave 4, major 2, reshaped**: the feed document as the base, the wall
   manifest as a private feed plus control; per-major URLs; settings widened
   into three layers with mat mode and overlay timing; capabilities that
   distinguish static captions from timed overlays; the wall loop / driver /
   label renderer split; the layout spec and conformance vectors.
3. **Wave 5**: the repository split, as planned, into the shape above.
4. **The first non-Pi Player**: the macOS screensaver, as a home client with
   control on. It is the cheapest test of the abstraction and of the vectors.
5. **The tvOS Player**, with both modes, and pairing.
6. **Later**: publishing channels from Arrt (static hosting, the public-domain
   gate, the 4K copy) and the published channel index the public mode reads.

## Open questions

- **The relative mat width** for a client with no pixel density: its number
  (a fraction of the screen's shorter side is the obvious form) is set when the
  layout spec is written in wave 4, ideally so it matches the inch rule on a
  50" 4K Frame.
- **A display's identity for kinds other than the Frame.** An HDMI connector or a
  Mac's screen has no device id the client can read reliably; the client and
  connector name may have to stand in, which is what `clients.md` does today.
- **Mat colour on public channels** is the Library's paid judgement, published
  per work. Nothing new is needed unless a channel wants its own colours.
- **Whether a home wall's feed is ever readable without a token.** Not proposed;
  a household that wants to share a wall publishes a channel instead.
