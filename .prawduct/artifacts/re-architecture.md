---
artifact: re-architecture
version: 1
depends_on:
  - artifact: product-brief
  - artifact: architecture
  - artifact: data-model
last_validated: null
status: program — direction ratified 2026-09-30, no code built against it yet
---

# Re-architecture: a library, its programming, and players

**Start here if you are new to this repo after 2026-09-30.** On that date the
product's direction changed. Everything under `.prawduct/artifacts/` written
before then describes a product that is still true *as built*: two planes on one
Raspberry Pi, driving one Samsung Frame, sharing one directory. It is no longer
the product being built *toward*. This file is the record of the change, the
target shape, and the order of work. Where an older artifact disagrees with this
file about the **target**, this file wins. Where they disagree about **what is
built today**, the older artifact wins until the wave that changes it lands.
Every artifact this change touches carries a dated pointer back here.

The conversation that produced it was held in the operator's homelab
workspace, not in this repo. Its substance, including the owner's own words
where they decided something, is reproduced below so nobody has to go and find
it.

**Amended later the same day, after a review.** It adds § What is showing, and
how it is shown (walls, settings, the schedule and scenes), and settles the
resolution floor as a Library quality profile. It adds a reconciliation rule to
Seam 1 and brings the package split forward to wave 2. It also adds facet
population to wave 6+ and re-sorts § Open questions. § Artifacts touched lists
both passes.

## What changed, in one paragraph

The product was **a curated-art appliance for a Samsung Frame TV**. It is
becoming **two products**:

1. **Arrt, the server,** in the manner of Radarr/Sonarr. It finds,
   acquires, maintains, upgrades and enhances artwork, and decides what hangs on
   which wall.
2. **Postarr, the player,** in the manner of a Plex client. It reads what the server
   publishes and shows it on whatever screen it owns: a Samsung Frame, a plain
   LCD, a monitor on a Mac. An optional e-ink label is supported, and a caption
   drawn in the mat is the alternative.

The server runs on the household NAS, next to the operator's existing *arr stack.
Players run at the walls. Most of the code already exists: `arrt/` is most of
the server and `postarr/` is most of the player. The change is mainly about
**where the seams are drawn**, not a rewrite.

**The names were given by the operator on 2026-09-30:** "The library/performance
controller will be Curatarr, the device side playback will be Displayarr." The
same day the operator renamed the player **Arrt**. On 2026-10-01, under a hard
requirement, the operator renamed both: the server is now **Arrt** and the
player **Postarr**. The Samsung name no longer fits a product that drives any screen. This file keeps
saying "server" and "player" where the role matters more than the product.

## The owner's rulings (2026-09-30)

In the operator's words, in the order they were given.

> "I want to break the Samsung utility into two parts: a new *arr package for
> finding and curating artwork, much like radarr, and then a playback utility
> more like plex/etc that reads that library and displays it, either on a
> Samsung tv or dumb LCD display or anything else. The artwork cards on e-ink
> displays will be supported and optional, with on-screen captions as an
> alternative."

> "The cleanest would be three parts: a library manager that procures,
> maintains, upgrades, enhances artwork files. Then a display manager that is
> aware of walls, and assigns artwork and playlists to walls, and finally a
> display manager that renders to displays. But that's a lot of complexity and
> two servers for a moderately simple app. Collapse the first two, design with
> seams to allow future separation."

> "Both library and programming will need some concept of themes, and we should
> separate. Library holds objective truth: artist, title, date, school, probably
> even statements about content ('snake, cup, biblical'). But programming may
> want more playlist oriented tags: 'funny, party, morning', etc."
> *Resolved as two layers, below. The operator agreed: "makes sense".*

On procurement surfaces (one-shot discovery vs. standing watches) the operator
said "Makes sense". On the order of work and the repo strategy: "Fantastic plan.
… We'll park the current branch, work on develop."

The advisor's recommendations that those replies accepted are recorded as
decisions below. Each is written in the vetoable form, because the operator
accepted the plan as a whole rather than deciding each point one by one.

## Three roles, two deployables

| Role | Owns | Deploys as |
|---|---|---|
| **Library** | What exists and what to go and get. Works, artists, sources, originals, image instances, verdicts, mat colour (a paid judgement about the work), label *text*, library facets (facts), discovery runs and conversations, taste, spend. New: **Watches** (standing searches), upgrade monitoring, a scheduler, a **quality profile** (the resolution floor and upgrade cutoff), and a device-independent *presentation master* per work. The Library has no concept of a wall. | **Server** (one process) |
| **Programming** | What hangs where, and when. Themes (now *playlists*), membership, walls as logical targets, hanging (ThemeAssignment), directives (`next` / `show_now` pins), publishing the per-wall manifest, receiving player heartbeats, wall health. New: **the schedule** (rotation computed centrally, across walls), **scenes** (live overrides), **wall settings** (label mode, viewing distance), **programming tags** and **smart playlists**. | **Server** (the same process) |
| **Player** | Making one wall's screen match its manifest. Screen geometry and backend, **compositing the mat**, drawing the label (e-ink panel, caption in the mat, or none), a local media cache, TV bindings and orphan removal, the guardrails that keep it from fighting the household for the screen, the heartbeat, which **reports its capabilities**. | **Player** (one process per wall, at the wall) |

`[DECISION: Library and Programming ship as one server process, with seams that
keep a later split a deployment change rather than a rewrite | the owner's ruling
above: a third process and a second server buy auth, deployment and network
failure modes a household app does not need, while the seams keep the option
open | user can veto/override]`

**The rule of thumb for "which part owns this request".** Requests that begin
"find" or "grab" go to the Library. Requests that begin "show" or "play" go to
Programming. A request with both halves is two objects that the UI creates
together (see § Procurement).

### Why not three processes now

Programming has no consumer other than the Player and no UI other than the
curation UI. Separating it would mean authenticating a second service, versioning
a third contract, and teaching the UI to talk to two backends, with nothing gained
until a second library or a second programmer exists. The seam rules below are
what keep that decision cheap to reverse.

## Seam 1: Library ↔ Programming (in-process today, network-ready)

These rules are what make a future split a **deployment change**.
`architecture.md` § Direction carries them as four norms, born `in-transition`
and tracked by this program. Rules 4 and 5 merge into its fourth norm. Rule 6 is
a ruling under the existing thin-binding norm, not a norm of its own.

1. **Two packages, one-way imports.** Programming imports only a small Library
   *facade*. The Library never imports Programming. Enforce it the way
   `tests/preferences/test_plane_isolation.py` already enforces plane isolation:
   statically, following imports transitively.
2. **The facade is written as if it were already remote.** It is coarse-grained,
   takes and returns ids and plain data (no ORM rows, no lazy loads), and is
   idempotent. The central call is roughly
   `playable(work_ids) -> {id: PlayableWork | Unplayable(reason)}`. The
   manifest readiness logic (`assess` and what was `entry_for`) moved behind it
   into `library/readiness.py` in wave 2b, because whether a work has an original and a current mat colour,
   and is not archived, is the Library's question. If splitting later would force
   a redesign of this interface, it was drawn wrong.
3. **Two SQLite files, no foreign keys across the seam.** This is the rule most
   likely to be skipped and the one that matters most. With one file, someone
   eventually writes the cross-seam join, and splitting then needs a data
   migration. Programming holds work ids as opaque references and tolerates
   ones that no longer resolve. Today two foreign keys cross it:
   `theme_memberships.artwork_id` and `directives.pinned_work_id`, both pointing
   at `artworks`.
4. **The Library announces changes, and Programming never polls Library tables.**
   In-process events such as `work.accepted`, `work.archived`,
   `work.image_changed` and `work.mat_changed` drive manifest rebuilds and pin
   withdrawal. After a split they become webhooks, the same way Radarr notifies
   its neighbours. **Events make updates prompt, not correct.** With two
   SQLite files there is no transaction spanning the Library's commit and
   Programming's handler, so a crash between them loses the event. Programming
   therefore reconciles every manifest against the facade at startup. The
   codebase already treats an interrupted discovery run this way. A lost event
   then delays an update until the next start, and never leaves a manifest wrong.
5. **Manifests point at Library-served, content-addressed media.** Programming
   never serves image bytes. After a split, the manifest's media URLs name the
   Library's host and no Player notices.
6. **The UI and MCP layer is the only thing allowed to span both.** "Accept this
   candidate into the Winter playlist" is two service calls, composed by the
   surface. This extends the existing ratified norm (operation logic lives only
   in the service layer): bindings stay thin, and a *composition* of two services'
   calls is still dispatch, not logic.

`[DECISION: events are a promptness mechanism, and Programming reconciles every
manifest against the facade at startup | two stores have no shared transaction,
so a crash between the Library's commit and Programming's handler loses an event,
and without reconciliation that manifest stays wrong. Advisor's recommendation in
review, 2026-09-30, approved by the operator | user can veto/override]`

`[DECISION: the seam rules migrate in waves 2 and 3, not wave 6. Rules 1, 2 and 4
(packages, facade, events) come in wave 2, ahead of the HTTP manifest endpoint.
Rule 3 (the store split) comes at the start of wave 3, before the catalogue moves
to the NAS | the manifest endpoint is built on exactly the readiness logic rule 2
moves, so building it before the split means building it twice, and splitting
the store before the move means the data moves once. Advisor's recommendation in
review, 2026-09-30, approved by the operator | user can veto/override]`

## Seam 2: Server ↔ Player (a real network contract from day one)

Today the channel is a file per wall in a shared directory, plus a heartbeat file
back (`architecture.md` § Communication & Boundaries). The target is:

- `GET /walls/{wall_id}/manifest`: polled at about the cadence of today's mtime
  check (about 1 s), with an ETag. It carries the label text and a
  **content-addressed media URL and hash** per entry. From major 2 it also
  carries the current mat colour, because the Player composes the mat from then
  on. Until
  schema major 2 it also carries the playlist entries, rotation settings and
  the directive sequence and pin, as today. From major 2 those become the
  **schedule**, any active **scene**, a **staging** list and the **wall
  settings** (§ What is showing, and how it is shown).
- `GET /media/{hash}`: immutable, cacheable forever. From wave 4 it serves the
  **presentation master**, a device-independent image derived from the Original:
  no mat, long edge capped (starting proposal about 8K, to be measured), so a
  Pi never pulls a gigapixel file. In waves 2 and 3, before any master exists,
  it serves today's composed `tv_display` rendition, which is what the display
  plane already reads from the file tree.
- `POST /walls/{wall_id}/heartbeat`: today's heartbeat document, over HTTP. From
  wave 4 it also reports the Player's **capabilities**: screen geometry,
  backend and label hardware. These are observations, not configuration, and
  Programming uses them to warn "this work is too small for the living room".
  The Library never sees them.

**The Player plays from a local cache, always.** It pulls the manifest and the
media into local storage and renders only from there, so a NAS reboot or a
server restart does not blank the wall.

`[DECISION: the ratified "theme manifest file is the only channel" norm is
amended to "the per-wall manifest document and immutable media, pulled into a
Player-local cache, are the only channel" | the norm's why was that display must
never require curation to be reachable, and that a fallback path is never
exercised until the night it matters. A pull-to-cache design keeps the first
property (the wall runs from the cache) and answers the second: the cache is not
a fallback, it is the only path the Player ever renders from, exercised on every
rotation. The alternative, NFS or SMB mounts of the art tree on each Pi, was
rejected because network mounts hang processes on a NAS reboot, which is the
exact failure the norm exists to prevent | user can veto/override]`

The one-directional corollary survives in spirit. The Player never writes
anything the server owns; the heartbeat is the Player *reporting*, exactly as the
heartbeat file does today.

**Each wall has a token.** The operator ruled on 2026-09-30: "each wall gets a
token". Arrt issues one per wall from the UI, shows it once and keeps only a
verifier. Postarr holds it as local configuration next to `WALL_ID` and sends
it on every request. Arrt checks it on every `/walls/{wall_id}/...` route,
the manifest GET as well as the heartbeat POST, and a token only opens its own
wall. `/media/{hash}` accepts any valid wall token. Rotation is: issue a new
token in the UI, then update the Player. A leaked token lets someone read one
wall's schedule and forge its health, and nothing more. It never reaches the
catalogue or the curator's surfaces. It lands in wave 2, with the routes.

> **Amended 2026-10-02 by the owner's ruling that clients are first-class
> (`clients.md`).** The token is per **client**, an installed Player driving
> any number of walls, and opens the walls assigned to that client; wall
> tokens are retired. `player-contract.md` § Transport is the as-built rule.

`[DECISION: per-wall bearer tokens, checked on every wall route and on media;
the server stores only a verifier | the operator's ruling "each wall gets a
token". Checking the GETs as well as the POST is the advisor's addition: one rule
for every route is simpler to get right than two, and the schedule a manifest
carries says when the household is home | user can veto/override]`

**The contract gets its own artifact** before it is built: a JSON Schema plus
example manifests, owned by the server, and pinned by the Player's tests after the
repo split. Today's `SCHEMA_MAJOR` / `SCHEMA_MINOR` scheme carries over. The
additive HTTP channel is a minor bump. **Major 2 carries every breaking change
at once**: compositing moving to the Player (below), plus the schedule, scenes
and wall settings (next section). One breaking bump costs less than three. The
wave 1 contract artifact specifies all of them, even though they are built in
wave 4.

## What is showing, and how it is shown

The operator's framing, 2026-09-30: the server "should not even have the concept
of walls, and should only have media management", but "if I have three walls in
the house, their rotations and displays should be coordinated and not require me
to go change settings on each player individually". The split that satisfies
both is between **what is showing**, which is coordinated centrally, and **how
it is shown**, which is local to each device.

- **The Library has no walls.** It manages media, which is the first half of the
  instinct.
- **Programming has walls, but only as logical targets.** "Living room" is a
  name, what plays there, when, and how the operator would like it presented. It
  has no address, no pixel size and no driver. Coordinating walls needs one place
  that knows all of them, and Programming is that place.
- **The Player owns the device.** It holds only what it needs to reach its
  hardware and the server.

**Settings flow down, and capabilities flow up.**

| Lives in | What | Examples |
|---|---|---|
| **Player**, local configuration set once | What it needs to reach its hardware and the server | server URL, `WALL_ID`, the television's address and token, the panel's physical size (today's `TV_PANEL_*`), the e-ink driver |
| **Player to server**, in the heartbeat | What its hardware can do, as observed | geometry, backend (Frame, LCD, monitor), label hardware present |
| **Programming**, set centrally and sent in the manifest | Everything the operator would otherwise walk round the house to change | playlist rules, the schedule, dark hours, the mat's proportions (today's `MAT_*`), the label mode (chosen from what the hardware reports), which facts the label shows, viewing distance |
| **Library** | The work itself | the Original, mat colour, label text, facets, pixel dimensions |

Viewing distance is a fact about the room rather than the device, so it is a
wall setting. The Player uses it with its own geometry to size label type under
the legibility norm (`accessibility-spec.md`).

### The manifest is a schedule, not a playlist

Today each Player shuffles its own list. Three walls therefore cannot avoid
showing the same work at once, and cannot change together. From major 2,
Programming publishes a **time-anchored schedule** for each wall: this work from
14:00 until 14:30, then that one, covering a horizon of about a day. Programming
computes all walls together, so "no work on two walls at once", "change the
whole house together" and "spread this playlist across rooms" become central
calculations. The Player follows the clock from its cache, so an unreachable
server still never blanks a wall. It just runs to the end of the horizon.

- **The dark hours are gaps in the schedule.** That settles who owns the
  wake/sleep window: Programming, because "when" is Programming's. The
  guardrails that stop a Player waking a set someone is watching, or fighting
  the household for the remote, stay on the Player, because they are about the
  device. The v1 plan's Chunk 26 splits along that line.
- **Rotation logic leaves the display plane.** The Player's timed selection
  becomes "show what the schedule says now". That is a real move of built code,
  and it lands with major 2 in wave 4.

### Scenes: live control above the schedule

The operator's case: put three Dalís next to each other in the living room and
see what that looks like, without writing a schedule and waiting. The schedule
is the baseline, and a **scene** overrides it.

- **A scene is one object spanning walls.** It holds a pin for each wall
  ("living room left: Dalí A") and a lifetime. The Player's rule is: show the
  active scene if there is one, or follow the schedule otherwise. It takes over
  the temporary, multi-wall uses of today's per-wall pin. `show_now` and `next`
  themselves become republishes of the schedule, which keeps their "jump there,
  then carry on" meaning (`player-contract.md` § Major 2).
- **A scene has a lifetime, so a test cannot strand a wall.** *Preview*, the
  default, holds for a set time and then the wall returns to the schedule. The
  expiry travels in each wall's manifest, so walls revert on their own even if
  the server goes down mid-test. *Hold* lasts until released. *Keep* turns the
  scene into ordinary Programming state, as pins or a playlist.
- **It stays a pull.** The 1 s ETag poll gets a scene to every wall within about
  a second. A true push would put a network listener, and so authentication, on
  every Player. Server-sent events remain the upgrade if a second proves too
  slow. Either way the Player pulls.
- **The real delay is rendering, so the UI stages a scene before applying it.**
  While the operator assembles a scene, Programming lists its works under
  **staging** in the affected manifests, and those Players fetch and compose
  them ahead. Applying the scene is then only a switch. On a Frame, that means
  selecting an image already uploaded.
- **A scene respects the Player's guardrails.** It does not interrupt someone
  watching the set. The UI shows that wall as waiting for the TV to be free.

`[DECISION: walls exist only in Programming, as logical targets; settings flow
down in the manifest and capabilities flow up in the heartbeat; from schema
major 2 the manifest is a time-anchored schedule with scenes as an override layer
and a staging hint | the operator's framing above ("This makes sense", on the
advisor's proposal) and the operator's scene requirement. Rejected alternative:
the server rendering each wall's image from reported geometry, the way a Plex
server transcodes for its clients. It would have put "how it is shown" on the
server, against the operator's split | user can veto/override]`

## Compositing moves to the Player

This is the biggest change to built code. Today curation composes a 3840×2160
canvas with the mat in it (`Rendition.kind = tv_display`), sized from
`TV_PANEL_*` and `MAT_*` configuration, and judges image adequacy
(`library/services/display_fit.py`) against that panel. `data-model.md` defended this as
"a property of the artwork's presentation, not of a device". That stops being
true the moment a second screen exists: a 1920×1200 LCD, a portrait monitor, or a
caption drawn in the mat, which needs the mat *sized for the caption*.

- **The Library keeps** the Original, the mat colour and its reasoning, and the
  label text. It **produces** the presentation master.
- **The Player composes** the mat for its own geometry, and (for caption mode)
  sets the label in the mat area. The mat takes the **work's** shape and the
  rest of the screen is black (`nonfunctional-requirements.md` § The mat is
  geometric, ruled 2026-10-02 and built in the server's compositor ahead of this
  move); the Player's compositor inherits that rule.
- **On a Samsung Frame, a caption can only exist burned into the image before
  upload.** That is a second reason compositing belongs where the label is
  decided.
- **The mat colour engine reasons partly about mat proportion.** One colour per
  work is expected to remain good enough across screens. Recomputing per aspect
  ratio is an open question, not a requirement.
- **Image adequacy for a wall is Programming's judgement.** Programming compares
  a work's pixel dimensions, which it gets through the facade, with the geometry
  that wall's Player reports in its heartbeat. The result is one answer per wall
  ("too small for the living room"). The Player composes and does not judge. The
  Library stores only panel-independent facts (width, height), exactly as
  `data-model.md` already requires.
- **The resolution floor becomes a Library quality profile.** Automatic instance
  selection (`arrt/src/arrt/library/services/selection.py`) excludes
  below-floor instances using the artwork box computed from the server's
  `TV_PANEL_*` / `MAT_*` settings, and review cards show a fit verdict from the
  same source. When geometry leaves the server, both would lose their input, and
  below-floor scans would be auto-selected silently. The replacement is a
  profile stated in pixels, independent of any device. It has a **minimum**,
  which selection and the review card judge against, and a **cutoff**, above
  which the Library stops looking for a better scan. That is Radarr's quality
  profile, and the cutoff is what the wave 6+ upgrade job needs anyway. Two
  alternatives were weighed and not taken. One was a reference geometry derived
  from the largest screen any Player reports, which would put device geometry
  in the Library. The other was judging only at hang time, which would let
  review accept scans no wall could use.
- **Compositing on a Pi 4 is measured and budgeted** (2026-10-04,
  `nonfunctional-requirements.md` § Performance): composing from a 7680 master
  takes at most about 3 s and 800 MB, against a budget of 5 s and 1 GB.
- **The presentation master is transported, and that conforms.** It is
  rendered for no geometry, so the data-model norm "derived artifacts are
  regenerated, never transported" does not reach it. The ruling is recorded in
  `data-model.md` § Direction.

`[DECISION: compositing moves from curation to the Player, and the tv_display
Rendition and TV_PANEL_* leave the server, and MAT_* stops being server
configuration and becomes a per-wall setting in Programming | the ratified 2026-08-07 norm
"a display device renders its own label" (architecture.md § Direction) already
names a monitor that draws the label in the mat area, and that is only possible
if the device composes the mat. Keeping compositing upstream would force the
catalogue to learn every screen's geometry, which is the data-model norm's cited
anti-pattern | user can veto/override]`

> **Direction changed 2026-10-02 (the owner's ruling, `upgrades.md`):** "No
> cutoff, but back off searches. At 3840, maybe once a month. At 7680, every six
> months." The minimum stays; the cutoff becomes a search cadence by size tier,
> and upgrades never stop looking.

`[DECISION: the resolution floor is a Library quality profile in pixels, with a
minimum and an upgrade cutoff; per-wall adequacy is Programming's comparison
against reported geometry | it keeps device geometry out of the Library, gives
selection and review an input that survives wave 4, and is the shape the upgrade
job needs. Advisor's recommendation, 2026-09-30 | user can veto/override]`

## Two layers of tags

| Library facet: *a fact about the work* | Programming tag: *how this household uses it* |
|---|---|
| subject: snake, Nativity, nude | funny, party, morning |
| movement: Impressionism | calm, conversation piece |
| palette: warm, dark | not for guests, Mom likes it |

**The test:** would a museum cataloguer say this is true of the work, no matter
whose wall it hangs on? If so, it is a Library facet.

- **Library facets already exist** as `WorkFacet` (`data-model.md`), with the
  closed `VocabularyKind` shared with taste (`artist | movement | era | subject |
  medium | palette`) and each row marked `sourced` or `inferred`. **Nothing
  writes them yet**, so every smart playlist below depends on a pipeline that
  does not exist. Filling them means mapping museum fields and inferring the
  rest with paid model calls, and museum fields rarely copy across unchanged.
  That needs its own requirements cycle, and wave 6+ schedules it ahead of smart
  playlists.
- **The line is not objective versus subjective.** Taste (`Affinity`) is
  subjective and stays in the Library, because it drives what gets acquired. The
  line is between *what the work is and what to acquire* (Library) and *when,
  where and for whom to show it* (Programming).
- **Programming tags** live in Programming's own store, keyed by `work_id`. Each
  records whether the curator set it or a model suggested it. The vocabulary is
  open, like Plex labels, with the text normalized and offered through an
  autocomplete.
- **Programming never writes facets.** Correcting a fact ("that's an eel, not a
  snake") is a Library edit made through the UI.
- **Model suggestions read facts and write tags.** They are paid calls, so they
  are recorded in `SpendRecord` under the existing paid-path rule.

### Most playlist tags should be rules

A theme becomes a **smart playlist**: a rule over Library facets and Programming
tags, plus manual additions and exclusions. For example:

- The December playlist is `subject: Nativity OR subject: winter landscape`.
- The kids' room excludes `subject: nude`. The fact lives in the Library and the
  policy lives in Programming, so the Library never learns that "not for kids"
  exists.

Hand-tags are then only needed for what cannot be derived. Programming evaluates
a rule by asking the Library facade for matching ids (AND, OR and NOT over kind
and value, maybe a date range; the kids' room above needs the NOT) and then
applying its own tags in Python. At a few thousand
works that is cheap.

**"More like my party playlist" feeds discovery one way.** The UI passes those
work ids to discovery as examples. The Library never reads Programming's tags.

## Procurement: one-shot discovery and standing Watches

Both belong to the Library.

- **"Find art that's won awards recently"** is today's discovery pipeline,
  unchanged: conversation, then run, then review. Phase 1 already searches the
  web for recency-bound intents (`product-brief.md`). Expect in-copyright,
  modest-resolution results; `Source.rights_status` records that, and review
  should show it.
- **"Whenever a new abstract expressionist piece is available, grab it"** is a
  new **Watch**: an intent that re-runs on a schedule. This is the most *arr-like
  piece of the design, the equivalent of Radarr's import lists and monitored flag.
  A Watch has:
  - its intent in words, plus optional facet filters and which sources to check;
  - a cadence (museum APIs have no RSS feeds, so it polls);
  - a policy for what happens when it finds something: notify only, queue for
    review (the default, because the product promises the curator reviews
    everything before it reaches the wall), or auto-accept;
  - a **spending cap per period**, recorded in `SpendRecord`, because a
    standing search is exactly where an unmetered paid path would hide;
  - memory of what it has already seen, through the existing dedup and
    rejected-candidate records, so it never offers the same thing twice.
- **Upgrades run on the same scheduler.** The `wanted` verdict (named
  `awaiting_better_image` until 2026-10-02) is already a wanted-upgrade marker,
  and periodically re-searching those works for a higher-resolution scan is
  Radarr's upgrade-until-cutoff. What runs in the background today is three
  single-purpose workers, each woken by an event or an interval: the preview
  sweep, the topic sweep and the acquisition queue. A job scheduler that Watches
  and upgrades share is still new Library infrastructure.
- **Watches fire two recorded revisit triggers, so they cannot ship as a
  feature alone.**
  - **Security:** `security-model.md` § Prompt Injection names *unattended
    discovery* as the trigger for re-deriving the prompt-injection bounds.
    Review-queue Watches remove one bound. Auto-accept Watches remove two. That
    section must be re-derived in the plan that builds Watches, and that plan
    may conclude auto-accept is not offered at all.
  - **Observability:** `observability-strategy.md`'s panel-only alerting
    decision names *scheduled discovery* as its revisit trigger. A Watch that
    silently stops running is the new "down looks like up".
  - **Attribution:** `initiated_by` on runs and spend needs a value for Watches.

**Where the design pays off.** "Grab new abstract expressionist pieces and show
them in the living room" is a Watch plus a smart playlist that knows nothing of
the Watch:

1. The Watch accepts a work, which gets the facet `movement: Abstract
   Expressionism`.
2. The Library announces `work.accepted`.
3. The living room's rule picks the work up on the next manifest rebuild.

The UI may offer "also make a playlist from this watch" as a shortcut that
creates both.

### Sources are plugins (the owner, 2026-10-03)

**The owner's ruling:** *"let's make acquisition through plugins, that way people
can add paid or local or whatever they choose to; then build our own as a private
repo."* So:

- **Image sources are plugins.** A deployment adds a source without changing
  Arrt, whether that source is paid, local, or a site Arrt's authors would never
  ship.
- **The owner's own scrapers live in a private repo**, not here. That settles
  the terms-of-service question for sources that forbid scraping, such as Google
  Arts & Culture and the auction houses: this public repo ships the plugin
  contract, not those adapters.
- **The seam already exists.** `ImageSearch` (`library/discovery/images.py`, renamed `Finder` when plugins were built) is
  what the pool asks, and nothing above the pool knows how many sources there
  are. A plugin is that protocol opened to code outside Arrt.

**Decided later the same day, by the owner:**

- **A plugin is a Python package loaded inside Arrt**, not a separate service.
  The agent recommended a service, for isolation and for deployment as a sibling
  container; the owner chose the package. So installing a plugin trusts it as
  fully as Arrt's own code.
- **The existing sources are the examples.** The Art Institute and Commons are
  rebuilt on the plugin interface rather than kept as a special case beside it.
- **Plugins are per protocol, not per institution** (IIIF, Google Arts &
  Culture, Artlogic, and so on), so one plugin reaches every holder that serves
  its protocol.

**Not yet decided:**

- where search lives: in each plugin, or in Arrt with plugins only reading what
  it finds;
- what a plugin must report for its spending to be capped;
- how its untrusted text and bytes are bounded (`security-model.md`).

The contract artifact settles these before any code.

## Player outputs

There are two families of screen, behind one "show this work" interface:

- **Push-to-appliance (Samsung Frame):** upload, select, bindings, orphan cleanup,
  selection confirmed by the set's own `image_selected` announcement. Today's
  `TvClient` has this shape, and `samsung-tv-state-findings.md` stays the
  authority on it.
- **Framebuffer (HDMI LCD on a Pi, a monitor on a Mac):** composite, then draw.

**Label mode is a wall setting in Programming,** chosen from what the wall's
Player reports it can do: e-ink panel (today's `LabelSurface`, `EpaperSurface`),
caption in the mat, or none. Until caption mode exists (wave 6+) the only modes
are the panel and none, and today's `EPD_*` Player configuration decides which. The label typography rules in
`accessibility-spec.md` (a type floor derived from geometry and reading distance)
apply to a caption in the mat exactly as they apply to the panel.

**One process per wall** drives both the picture and the label, so they can
never disagree about what is showing. That keeps the Player on the Pi at walls
with an e-ink panel, even though a Frame could be driven from anywhere on the LAN.

**Each new Player host needs its text stack re-verified.** The label is typeset
with Pango through PyGObject (`platform-and-dependency-findings.md`). A Pi driving
an HDMI LCD, or a Mac, is a new host for that stack, and caption mode depends on
it.

## Deployment target

- **The server** runs as a container on the operator's NAS (TrueNAS SCALE,
  x86_64), deployed the way the operator's other custom apps are: an image in a
  LAN registry, a custom app, and a LAN hostname through the operator's reverse
  proxy. The deployment itself is recorded in the operator's homelab repository,
  not here. The catalogue and art tree live on NAS storage, which retires the
  SD-card bottlenecks in `architecture.md` § Scaling Model.
- **The Player** stays on the Pi(s) under systemd, with a local cache directory.
- **The 2026-08-04 rejection of SQLite over a network filesystem still stands.**
  It argued against a process opening its catalogue across the network. The
  server opens its catalogue on storage local to its own host (the NAS), and
  Players never open it at all, so nothing here reverses that decision.
- **The server container gets a memory limit.** On a shared NAS, a gigapixel
  acquisition must not be able to starve the operator's other applications.
  This replaces the `MemoryMax` in `curation.service`.
- **From wave 3, the backup covers two catalogue files as a pair.** A restore
  has to be exercised against Programming references to works the restored
  Library does not hold.
- **The co-location decision of 2026-07-20** (curation on the Pi, see
  `architecture.md` Decision Log) is reversed. Its trade-off, "one hardware failure
  domain, and curation competes with display for the Pi", no longer has to be
  accepted.

## Order of work

**The repo split comes last.** While server and player share one repo, every
contract change is one atomic commit with both suites behind it. Across two repos
it becomes two PRs and version skew. So the contract is settled here first, and
the repo is cut along it afterwards. The plan is a **program**, not one build
plan: each wave gets its own `build-plan-<scope>.md` when it starts, per
`methodology/planning.md`.

| Wave | Scope | Notes |
|---|---|---|
| **0: clear the decks** *(closed 2026-09-30)* | Park round 2. ~~Reconcile the v1 plan's open chunks.~~ | Round 2 is **parked, not abandoned**, on branch `curation-ui/rulings-and-plan`. It is curation-UI work that remains valid for the server; revisit after wave 2. **The operator closed the rest of this wave: "wave 0 -- abandon. We'll rebuild with this new plan."** The v1 plan's open chunks (13A, 13B, 20, 24–27) are abandoned, not carried; § Where the v1 open chunks' requirements went records what each one served and where it is rebuilt. Retiring the 2024 root modules moves to wave 5, when this repo becomes Arrt. |
| **1: plan** *(closed 2026-09-30)* | Amend the artifacts (this change started that). Write the Player contract artifact with a JSON Schema and fixtures. Write the wave-2 build plan. | Planned as doc-only; it shipped code as well. The contract's schemas and fixtures are tested from all three suites, which each declare `jsonschema` in their `dev` group. The amendments were drafted 2026-09-30; see § Artifacts touched. Wave 2 is two plans: `build-plan-wave-2a-rename.md`, then `build-plan-wave-2b-seams-and-http.md`. |
| **2: seams and the HTTP channel, alongside the file** *(closed 2026-09-30)* | Split curation into Library and Programming packages with one-way imports and the `playable()` facade. Move the manifest's readiness logic behind the facade. Add the events, and Programming's reconciliation at startup (§ Seam 1). Then serve manifest, media and heartbeat over HTTP, with Programming's manifest endpoint as the facade's first consumer. Display gains a pull-to-local-cache mode behind configuration. Schema minor bump. | The package split comes first because the manifest endpoint is built on exactly the readiness logic rule 2 moves; building it before the split means building it twice. The static import guard for rule 1 lands here. The wall never goes dark: the file channel keeps working until wave 3 retires it. `tests/preferences/test_plane_isolation.py` forbade any HTTP client in display. It was narrowed in the chunk that added the pull, and now allows one only in `postarr/src/postarr/pull.py`, whose routes must be ones `contract/routes.json` names. **The per-wall tokens land with the routes** (§ Seam 2), because the server on the Pi is already reachable on the LAN. The cache claim gets a test that stops the server while the wall runs. |
| *(2026-10-02, the owner's direction)* **Upgrades, pulled forward** | Manual upgrades of held works (`build-plan-upgrades.md`), then the scheduler that runs them, ahead of wave 3 and out of wave 6+. The presentation master stays in wave 4; Watches stay in wave 6+. | "let's move from UI to discovery, acquisition, retry and upgrade following the *arr and ../tacularr's patterns". Requirements: `upgrades.md`. *Parked the same day as a research spike (next row, and `upgrades.md` § Status).* |
| *(2026-10-02, the owner's direction)* **Wave 3 now, without the store split** | "NAS now": the server goes to the NAS beside the owner's other apps (`build-plan-nas.md`) and the backup writer lands; the Pi was cut over to HTTP, then stood down when the owner skipped the Frame, and returns as a client of the server (`build-plan-clients.md`). The store split is skipped for now, accepting one more data migration when it lands. Upgrades were pulled forward the same day and then parked as a research spike (#177, #178). | The owner asked for "what's needed to really get the system usable day to day". |
| **3: server to the NAS** | First, split the store: Programming's tables move to their own SQLite file, and the two cross-seam foreign keys become opaque references (rule 3), so the data moves once. Then containerize the server, deploy it on the NAS, point the Pi at HTTP and retire the file channel. Move the backup and restore exercise to NAS storage, with `VACUUM INTO` and the two catalogue files backed up as a pair. | The deployment side lives in the operator's homelab repo. The image needs what the Pi's install has today: a uv-managed Python 3.14, the `dezoomify-rs` binary, and a memory limit in place of `MemoryMax`. It does not need Pango unless the server ever typesets. The schema test for rule 3 lands here. |
| **4: schema major 2** | Add the presentation master and the quality profile. Remove the `tv_display` rendition and `TV_PANEL_*` from the server, and turn `MAT_*` into per-wall settings. Display composes, with the wall's mat proportions. The manifest becomes the schedule, with scenes, staging and wall settings. The heartbeat reports capabilities, and Programming judges per-wall adequacy from them. | The largest built-code change, and the only breaking one. Mat-colour regression corpus: `arrt/tools/mat_masters.py`. Its compositing budget on a Pi 4 was measured 2026-10-04 (§ Compositing moves to the Player). Rotation logic moves from the display plane to Programming, along with the wake/sleep window from the v1 plan's Chunk 26. |
| **5: split the repos** | Extract the player with `git filter-repo` in **two passes**. Its history spans three paths: `display/` until wave 2a, `arrt/` until the rename of 2026-10-01, and `postarr/` since, and filter-repo does not follow renames. From the commit that renamed the server Curatarr to Arrt (`c1c31255a4e47e0116c088950325d62dd9b46d63`, landed on develop by the merge `1194e1e0ea546b8effc385e70794d782189b4d47`), `arrt/` holds the server instead. filter-repo rewrites every ref, so that commit and every commit descending from it on any branch are `c1c3125` plus `git rev-list --all --ancestry-path=c1c3125 ^c1c3125`. A set taken from one tip (`--ancestry-path c1c3125..<tip>`) misses a branch cut after the rename and not merged into that tip, which keeps the server under `arrt/` and collides in pass 2; either use the all-refs set or run both passes with `--refs <tip>`. Measured 2026-10-01: the all-refs set held 6 commits, the 4 on develop plus 2 on an unmerged branch. **Pass 1** works on the original paths: a `--commit-callback` turns every change under `arrt/` into a deletion in that commit and in every commit descending from it, the merge that landed it included (`FileChange(b"D", ch.filename)` for each `ch` whose filename starts `b"arrt/"`, when `commit.original_id` is in that set). **Pass 2** is `git filter-repo --path display/ --path arrt/ --path postarr/ --path-rename display/: --path-rename arrt/: --path-rename postarr/:`. It cannot be one pass: filter-repo applies the renames before the callback runs, so server and player files collide on shared names, and fast-import crashed on `uv.lock`. **Measured 2026-10-01** on a scratch clone, with the branch merged `--no-ff` into develop: the one-pass form crashed, and the two-pass form gave a tip tree identical to the original `postarr/`, and a tree at the player rename's parent identical to the original `arrt/` there. Rerun both checks on the real split. `/prawduct:onboard` there. Carry the player's artifacts. Pin `contract/` together with `player-contract.md` and the major 2 semantic validator (today in `tests/preferences/test_player_contract.py`), because the schemas alone do not carry the rules a schema cannot state. The new repo is **Postarr**, and this repo is renamed **Arrt**. Remove the 2024 root modules as this repo becomes Arrt. | GitHub keeps redirects on rename. |
| **6+: in parallel** | Server: Watches, the scheduler and upgrades to the quality profile's cutoff; **facet population**, then Programming tags and smart playlists. Player: a framebuffer backend, caption in the mat, and **power control** (the television's power read, the guardrails, and acting on the schedule's dark hours). | Independent streams after the split. Watches carry the security and observability re-derivations above. Facet population needs its own requirements cycle (§ Two layers of tags), and smart playlists wait for it. |

### Where the v1 open chunks' requirements went

The chunks are abandoned. The requirements they served are not, and each is
rebuilt in this program:

| v1 chunk | The requirement it served | Rebuilt in |
|---|---|---|
| 13A, 13B | The label on the panel, and the wall surviving a television power-cycle unattended | Postarr. The label code is built and is carried as it stands. The unattended power-cycle check becomes an acceptance check on the Player once it pulls over HTTP (wave 3). |
| 24 | Measure what the set's power keys do, before any code presses them | Postarr power control (wave 6+). `postarr/tools/power_probe.py` already exists and is the instrument. |
| 25, 27 | A three-way power reading, a channel that can press, and a heartbeat that says why | Postarr power control (wave 6+). The heartbeat's reason travels in the HTTP heartbeat. |
| 26 | When the wall may wake and must go dark, and the guardrails against fighting the household | Split: the dark hours are gaps in Programming's schedule (wave 4); the guardrails are Postarr power control (wave 6+). |
| 20 | Backup and restore, and retiring legacy | Backup and restore: wave 3, on NAS storage. Legacy retirement: wave 5. |

`nonfunctional-requirements.md`'s power norm (§ The television belongs to
whoever is using it) keeps its interim rule until power control is built: no
code that runs unattended sends a power key until the transitions are measured.

**Agents.** Through wave 5, run one Claude session in this repo, so prawduct's
hooks and gates apply. Parallel agents in worktrees are fine inside a wave. After
the split, run one session per repo, with the contract as their only shared
ground: a player agent that needs a field files it against the server repo, not
the other way round.

## Open questions

- **The presentation master's size cap and encoding.** About 8K long edge is a
  starting guess, to be measured against the corpus. The Pi needs no reduction
  for its own sake (next item, answered).
- **Directive latency:** an ETag poll at about 1 s, or server-sent events.
  Polling matches today and is the default. Scenes are the test of whether it is
  fast enough (§ Scenes).
- **The schedule's horizon and a scene's default preview lifetime.** About a day,
  and about twenty minutes, are starting proposals. The wave 1 contract wrote
  the fields that carry them (`player-contract.md` § Major 2). The values are
  settled before wave 4 builds major 2.
- ~~**The compositing budget on a Pi 4.**~~ *Answered 2026-10-04:* measured and
  budgeted in `nonfunctional-requirements.md` § Performance. A 7680 cap needs no
  reduction for the Pi's sake, which bears on the master's size cap above.
- **The quality profile's numbers:** the minimum and the upgrade cutoff, in
  pixels. The floor the code derives from today's panel is the starting point.
- **The smart-playlist rule language:** how rich, and whether the facade's
  query needs anything beyond AND, OR and NOT over (kind, value) plus a date
  range.
- **Mat colour per aspect ratio:** see § Compositing moves to the Player.
- **Can facts be edited in the UI?** Correcting a facet is a Library edit, but
  `information-architecture.md` § Boundaries forbids editing artwork metadata.
  Facets are not titles, artists or dates, so the two need not conflict, but
  this needs an operator ruling before facet editing is built.
- **Where the Player's cache lives,** and whether the SD card can carry it
  (`operational-spec.md`). A wave 2 decision.
- **The server image's provenance:** how the container image is pinned and
  where it is built (`security-model.md`). Before wave 3.
- **Watches, before the plan that builds them:** the re-derived
  prompt-injection bounds (`security-model.md` § Prompt Injection), whether
  auto-accept is offered at all, the `initiated_by` value for a Watch
  (`api-contract.md`), and whether scheduled jobs revisit the no-push-alerts
  decision (`observability-strategy.md`).
- **External identity for works and artists, before Watches.** *(Raised
  2026-09-30, while planning the *arr navigation.)* Sonarr and Radarr rest on an
  external ID (TVDB, TMDB) that they use and do not maintain. Arrt's work
  identity is its own: `work_dedup_key` is a normalised title and artist
  (`arrt/src/arrt/library/discovery/dedup.py`). Series titles
  ("Composition", "Untitled", "Haystacks") are where two works would share a
  key, which has not been tested. For public-domain works, registries already
  exist: Wikidata QIDs for artworks, which carry creator, inception, movement,
  genre and depicts; Getty ULAN for artists; Getty AAT for movements,
  techniques and materials; and each museum's own object ID. The question is
  whether to store those IDs where they exist, the way Radarr stores a TMDB ID.
  They would give *Already in your library* and a Watch's "monitored" a stable
  identity, and they might give facet population sourced values in place of
  inferred ones. **The line to hold:** Arrt uses registries and keeps a
  private catalogue. It never becomes a registry. The contemporary web art
  `project-state.yaml` commits to is in no registry, and there the catalogue's
  own identity stands. *(Corrected 2026-10-01: this said works past the
  public-domain boundary are in no registry too. Measured for Dalí, Wikidata
  records 1,072 works and 358 holders but only 5 free images: existence is
  registered past the boundary, and images are what stop there.
  `user-scenarios.md` § Four layers.)* Wikidata's coverage of these fields for
  the corpus is otherwise **not measured**. That measurement
  is the cheapest first step, and belongs with the facet-population
  requirements cycle (§ Two layers of tags).
- **Filing the program as backlog items.** The live backlog is public GitHub
  Issues (`backlog_service_repo`). Filing them is the operator's call and has not
  been done. Until then this file is the tracking reference for the
  `in-transition` norms it creates.

## Artifacts touched by this change (2026-09-30)

Each carries a dated note pointing here. None of their *as-built* content was
rewritten, because it remains true of the code until the wave that changes it.

- `product-brief.md`: Vision, Identity and scope amended for two products and
  plural screens.
- `architecture.md`: Direction norms amended and born, target topology, Decision
  Log.
- `data-model.md`: role ownership of each entity; the `tv_display` Rendition
  reversal; planned entities (programming tags, Watch, smart playlist rule,
  presentation master).
- `project-state.yaml`: the `multi_process_distributed` flip, a technical
  decision, the artifact manifest, open questions.
- `project-preferences.md`: norm index rows for the new and amended norms.
- `nonfunctional-requirements.md`: the display-independence norm is **amended**
  and `in-transition` (a `[DECISION]` block), plus forward notes.
- `accessibility-spec.md`: two **amendments**, each with a `[DECISION]` block. The
  legibility norm now covers the label on any surface; the 16-grey clause stays
  panel-only. § The television admits a caption in the mat on walls configured
  for one, and still never an overlay on the picture.
- `build-plan.md`: proposed dispositions for the open v1 chunks, for the operator
  to confirm in wave 0.
- `learnings.md`: one new rule. "Device-independent" is only evidence once it has
  been checked against a second, different device.
- `api-contract.md` (including a PLANNED section for the Server↔Player surface),
  `security-model.md`, `operational-spec.md`, `observability-strategy.md`,
  `boundary-patterns.md`, `information-architecture.md`,
  `platform-and-dependency-findings.md`, `samsung-tv-state-findings.md` and
  `design-direction.md`: forward notes where their target-state claims change.
- `README.md`, `CLAUDE.md`, `deploy/README.md`: orientation for a new reader.

**The second pass, later on 2026-09-30,** followed a review of the first. It
wrote the decisions in § What is showing, and how it is shown and the quality
profile, and reconciled the forward notes that disagreed with this file or with
each other. The disagreements were over the floor options, who judges adequacy,
the wave for label mode and for the presentation master, and when the system
becomes distributed. It added missing notes to `project-preferences.md`'s norm
index, `3tears-integration-findings.md` and `openrouter-api-findings.md`. It
moved the open questions into `project-state.yaml` and brought the Seam 1 norms'
schedule in `architecture.md` into line with the new wave table.

**Settled by the operator later the same day:** the names (then Curatarr and
Arrt; since 2026-10-01 Arrt and Postarr), Player authentication (a token per wall, § Seam 2), and the v1 open
chunks (abandoned; § Where the v1 open chunks' requirements went).

**Settled by the second pass:** who owns the wake/sleep window (Programming, as
gaps in the schedule, with the guardrails staying on the Player), and the
resolution floor's home (a Library quality profile). Also settled: what a review
card shows about size before any wall hangs a work, which is the verdict against
that profile.
