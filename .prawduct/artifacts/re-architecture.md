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

## What changed, in one paragraph

The product was **a curated-art appliance for a Samsung Frame TV**. It is
becoming **two products**:

1. **A server** in the manner of Radarr/Sonarr. It finds, acquires, maintains,
   upgrades and enhances artwork, and decides what hangs on which wall.
2. **A player** in the manner of a Plex client. It reads what the server
   publishes and shows it on whatever screen it owns: a Samsung Frame, a plain
   LCD, a monitor on a Mac. An optional e-ink label is supported, and a caption
   drawn in the mat is the alternative.

The server runs on the household NAS, next to the operator's existing *arr stack.
Players run at the walls. Most of the code already exists: `curation/` is most of
the server and `display/` is most of the player. The change is mainly about
**where the seams are drawn**, not a rewrite.

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
| **Library** | What exists and what to go and get. Works, artists, sources, originals, image instances, verdicts, mat colour (a paid judgement about the work), label *text*, library facets (facts), discovery runs and conversations, taste, spend. New: **Watches** (standing searches), upgrade monitoring, a scheduler, and a device-independent *presentation master* per work. | **Server** (one process) |
| **Programming** | What hangs where, and when. Themes (now *playlists*), membership, walls, hanging (ThemeAssignment), directives (`next` / `show_now` pins), rotation and shuffle, publishing the per-wall manifest, receiving player heartbeats, wall health. New: **programming tags** and **smart playlists**. | **Server** (the same process) |
| **Player** | Making one wall's screen match its manifest. Screen geometry and backend, **compositing the mat**, drawing the label (e-ink panel, caption in the mat, or none), a local media cache, TV bindings and orphan removal, the heartbeat. | **Player** (one process per wall, at the wall) |

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

These rules are what make a future split a **deployment change**. Each is
proposed as a Direction norm in `architecture.md` (§ Direction, born
`in-transition`, tracked by this program).

1. **Two packages, one-way imports.** Programming imports only a small Library
   *facade*. The Library never imports Programming. Enforce it the way
   `tests/preferences/test_plane_isolation.py` already enforces plane isolation:
   statically, following imports transitively.
2. **The facade is written as if it were already remote.** It is coarse-grained,
   takes and returns ids and plain data (no ORM rows, no lazy loads), and is
   idempotent. The central call is roughly
   `playable(work_ids) -> {id: PlayableWork | Unplayable(reason)}`. Today's
   manifest readiness logic (`manifest/builder.py` `assess` / `entry_for`) moves
   behind it, because whether a work has an original and a current mat colour,
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
   its neighbours.
5. **Manifests point at Library-served, content-addressed media.** Programming
   never serves image bytes. After a split, the manifest's media URLs name the
   Library's host and no Player notices.
6. **The UI and MCP layer is the only thing allowed to span both.** "Accept this
   candidate into the Winter playlist" is two service calls, composed by the
   surface. This extends the existing ratified norm (operation logic lives only
   in the service layer): bindings stay thin, and a *composition* of two services'
   calls is still dispatch, not logic.

## Seam 2: Server ↔ Player (a real network contract from day one)

Today the channel is a file per wall in a shared directory, plus a heartbeat file
back (`architecture.md` § Communication & Boundaries). The target is:

- `GET /walls/{wall_id}/manifest`: polled at about the cadence of today's mtime
  check (about 1 s), with an ETag. It carries the playlist entries, rotation
  settings, the directive sequence and pin, the label text, the current mat
  colour, and a **content-addressed media URL and hash** per entry.
- `GET /media/{hash}`: immutable, cacheable forever. It serves the
  **presentation master**, a device-independent image derived from the Original:
  no mat, long edge capped (starting proposal about 8K, to be measured), so a
  Pi never pulls a gigapixel file.
- `POST /walls/{wall_id}/heartbeat`: today's heartbeat document, over HTTP. The
  Player may include its screen geometry *as an observation*, so Programming can
  warn "this work is too small for the living room". The Library never sees it.

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

**The contract gets its own artifact** before it is built: a JSON Schema plus
example manifests, owned by the server, and pinned by the Player's tests after the
repo split. Today's `SCHEMA_MAJOR` / `SCHEMA_MINOR` scheme carries over. The
additive HTTP channel is a minor bump. Moving compositing to the Player (below)
is **major 2**.

## Compositing moves to the Player

This is the biggest change to built code. Today curation composes a 3840×2160
canvas with the mat in it (`Rendition.kind = tv_display`), sized from
`TV_PANEL_*` and `MAT_*` configuration, and judges image adequacy
(`services/display_fit.py`) against that panel. `data-model.md` defended this as
"a property of the artwork's presentation, not of a device". That stops being
true the moment a second screen exists: a 1920×1200 LCD, a portrait monitor, or a
caption drawn in the mat, which needs the mat *sized for the caption*.

- **The Library keeps** the Original, the mat colour and its reasoning, and the
  label text. It **produces** the presentation master.
- **The Player composes** the mat for its own geometry, and (for caption mode)
  sets the label in the mat area.
- **On a Samsung Frame, a caption can only exist burned into the image before
  upload.** That is a second reason compositing belongs where the label is
  decided.
- **The mat colour engine reasons partly about mat proportion.** One colour per
  work is expected to remain good enough across screens. Recomputing per aspect
  ratio is an open question, not a requirement.
- **Image adequacy becomes a Player/Programming observation.** A Player knows its
  geometry and can report "below floor" for a work. The Library stores only
  panel-independent facts (width, height), exactly as `data-model.md` already
  requires.
- **The resolution floor loses its input, and this must be decided before
  wave 4.** Automatic instance selection (`curation/src/curation/services/
  selection.py`) excludes below-floor instances using the artwork box computed
  from the server's `TV_PANEL_*` / `MAT_*` settings, and review cards show a fit
  verdict from the same source. When geometry leaves the server, both lose
  their input. If nothing replaces it, below-floor scans get auto-selected
  silently. The options:
  - a pixel floor stated in the Library, independent of any device;
  - a reference geometry derived from the largest screen any Player has
    reported;
  - judging adequacy only at hang time, per wall.
- **Compositing on a Pi 4 has no measured cost.** Composing from an 8K-class
  master whenever a new work arrives or the geometry changes needs a budget in
  `nonfunctional-requirements.md` before wave 4 is planned.
- **The presentation master is transported, and that conforms.** It is
  rendered for no geometry, so the data-model norm "derived artifacts are
  regenerated, never transported" does not reach it. The ruling is recorded in
  `data-model.md` § Direction.

`[DECISION: compositing moves from curation to the Player, and the tv_display
Rendition, TV_PANEL_* and MAT_* leave the server | the ratified 2026-08-07 norm
"a display device renders its own label" (architecture.md § Direction) already
names a monitor that draws the label in the mat area, and that is only possible
if the device composes the mat. Keeping compositing upstream would force the
catalogue to learn every screen's geometry, which is the data-model norm's cited
anti-pattern | user can veto/override]`

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
  medium | palette`) and each row marked `sourced` or `inferred`. Nothing writes
  them yet.
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
a rule by asking the Library facade for matching ids (AND/OR over kind and value,
maybe a date range) and then applying its own tags in Python. At a few thousand
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
- **Upgrades run on the same scheduler.** `awaiting_better_image` is already a
  wanted-upgrade marker, and periodically re-searching those works for a
  higher-resolution scan is Radarr's upgrade-until-cutoff. Nothing in this
  codebase runs on a schedule today except the preview sweep, so a job scheduler
  is new Library infrastructure.
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

## Player outputs

There are two families of screen, behind one "show this work" interface:

- **Push-to-appliance (Samsung Frame):** upload, select, bindings, orphan cleanup,
  selection confirmed by the set's own `image_selected` announcement. Today's
  `TvClient` has this shape, and `samsung-tv-state-findings.md` stays the
  authority on it.
- **Framebuffer (HDMI LCD on a Pi, a monitor on a Mac):** composite, then draw.

**Label mode is set per wall:** e-ink panel (today's `LabelSurface`,
`EpaperSurface`), caption in the mat, or none. The label typography rules in
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
- **After wave 6, the backup covers two catalogue files as a pair.** A restore
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
| **0: clear the decks** | Park round 2. Retire the 2024 root modules. Reconcile v1 `build-plan.md`'s open chunks. | Round 2 is **parked, not abandoned**, on branch `curation-ui/rulings-and-plan` (three commits, local only as of 2026-09-30). It is curation-UI work that remains valid for the server; revisit after wave 2. The v1 plan's open chunks (13A, 13B, 24–27) wait on hardware; decide which survive the new direction. |
| **1: plan** | Amend the artifacts (this change started that). Write the Player contract artifact with a JSON Schema and fixtures. Write the wave-2 build plan. | Doc-only. The amendments were drafted 2026-09-30; see § Artifacts touched. |
| **2: HTTP channel, alongside the file** | The server serves manifest, media and heartbeat over HTTP. Display gains a pull-to-local-cache mode behind configuration. Schema minor bump. | The wall never goes dark. The file channel keeps working until wave 3 retires it. `tests/preferences/test_plane_isolation.py` forbids any HTTP client in display today. Narrow it in the same chunk that adds the pull (one manifest-client module, three endpoints), not before and not after. |
| **3: server to the NAS** | Containerize curation. Deploy on the NAS. Point the Pi at HTTP. Retire the file channel. | The deployment side lives in the operator's homelab repo. |
| **4: compositing to the Player** | Add the presentation master. Remove the `tv_display` rendition and `TV_PANEL_*` / `MAT_*` from the server. Display composes. **Schema major 2.** | The largest built-code change. Mat-colour regression corpus: `curation/tools/mat_masters.py`. Blocked on deciding the resolution floor's new home and a compositing budget (see § Compositing moves to the Player). |
| **5: split the repos** | `git filter-repo --subdirectory-filter display` into a new player repo. `/prawduct:onboard` there. Carry the player's artifacts. Pin contract fixtures. Rename this repo for the server. | GitHub keeps redirects on rename. |
| **6+: in parallel** | Server: the Library/Programming package and database split with events; Watches, the scheduler and upgrades; Programming tags and smart playlists. Player: a framebuffer backend and caption in the mat. | Independent streams after the split. Watches carry the security and observability re-derivations above. |

**Agents.** Through wave 5, run one Claude session in this repo, so prawduct's
hooks and gates apply. Parallel agents in worktrees are fine inside a wave. After
the split, run one session per repo, with the contract as their only shared
ground: a player agent that needs a field files it against the server repo, not
the other way round.

## Open questions

- **Names** for the two products and their repos. Unset. This file says
  "server" and "player".
- **The presentation master's size cap and encoding.** About 8K long edge is a
  starting guess, to be measured against the corpus and the Pi's decode time.
- **Player authentication on the LAN.** The endpoints are read-only except the
  heartbeat, and today's trust boundary is the network (`security-model.md`).
  Decide before wave 3 exposes a LAN listener. The heartbeat POST is an integrity
  exposure: anything on the LAN can make a wall's health read green or red. The
  options are to accept that or to issue each wall a token.
- **Directive latency:** an ETag poll at about 1 s, or server-sent events.
  Polling matches today and is the default.
- **The smart-playlist rule language:** how rich, and whether the facade's
  query needs anything beyond AND/OR over (kind, value) plus a date range.
- **Mat colour per aspect ratio:** see § Compositing moves to the Player.
- **Who owns the wake/sleep window?** v1 Chunk 26 puts the bedtime window on
  the display plane. "When" is otherwise Programming's (rotation, schedules).
  Decide whether it is Player configuration or Programming policy carried in the
  manifest.
- **Can facts be edited in the UI?** Correcting a facet is a Library edit, but
  `information-architecture.md` § Boundaries forbids editing artwork metadata.
  Facets are not titles, artists or dates, so the two need not conflict, but
  this needs an operator ruling before facet editing is built.
- **What a review card shows about size before any wall hangs the work.** This
  follows from the resolution-floor question in § Compositing moves to the
  Player.
- **The fate of v1 `build-plan.md`'s open chunks.** They are hardware checks
  on the Frame and the panel. Most remain meaningful for the Player.
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
