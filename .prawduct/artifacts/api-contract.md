---
artifact: api-contract
version: 1
depends_on:
  - artifact: product-brief
  - artifact: data-model
last_validated: null
---

# API Contract

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The product is
> becoming a **server** (Library + Programming, on the operator's NAS) and a
> **player** (one per wall). In this file, that affects:
> - the **curation↔display contract**, which becomes a network surface: an HTTP
>   manifest per wall, immutable media and a heartbeat POST;
> - the review surface's **fit verdict**, which becomes an observation the
>   player reports;
> - the **transport and trust paragraphs**, because the server moves off the Pi.
>
> The MCP tool surface, the HTTP API for the curation UI, the error model and
> the versioning rules for tools are **unchanged**. The server keeps all three.
> The planned surface is specified in § The Server↔Player surface, below. It is
> PLANNED and not built. Everything else here still describes the code as it
> stands.

> **Status: operations decided 2026-07-19.** This artifact was deliberately
> incomplete on first authoring — the operations table was left empty because a tool
> surface is a contract external clients bind to, and guessing one into existence is
> the expensive kind of wrong. The granularity question has since been answered
> against three inputs: the operator's two production MCP servers
> (`cordyceps`, public and in wide use; `hallucinote`, private), Anthropic's
> published tool-design guidance, and the Model Context Protocol specification at
> revision `2025-11-25`. What remains open is named as open.

## Overview & Surface Type

Three surfaces, and they are not the same kind of thing:

| Surface | Consumers | Kind | Stability obligation |
|---|---|---|---|
| **MCP tool surface** | **External** — Claude Code, the in-UI agent, any MCP client | Model Context Protocol tools | **Real.** Clients bind to tool names, argument schemas, and result shapes. |
| **HTTP API** | Internal — the curation UI's direct controls | JSON over HTTP on the LAN | None. Shipped and deployed with its only consumer. |
| **curation↔display contract** | Internal — the display plane | Theme manifest: a versioned JSON document on a shared filesystem | **Bounded.** Additive changes are free; a breaking change bumps the major version, and display refuses an unrecognised major and keeps the manifest it has. |

> **Amended 2026-07-20.** This row read *"To be designed. None. Single consumer,
> deployed together."* — the blanket exemption `architecture.md` § Deployment &
> Version Skew explicitly recorded as owed an edit here, and which Critic findings
> flagged as still standing.
>
> The exemption was incompatible with the ratified availability norm:
> *deployed-together* and *survives-independently* cannot both be true without
> saying what display holds and how stale it may be. And skew is real even with
> both planes on one host — the two processes restart independently, so an upgrade
> leaves a window where new curation has written a manifest an old display is still
> reading, and a reboot mid-upgrade widens that to "until someone notices".
>
> The obligation is deliberately small rather than a full compatibility regime:
> without a version field the failure is a misparse rendering wrong art or a crash
> loop blanking the wall; with one, it is a logged refusal and yesterday's theme
> still on the wall.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The third row's
> *kind* changes: "a versioned JSON document on a shared filesystem" becomes a
> versioned JSON document served over HTTP per wall, plus content-addressed media
> and a heartbeat POST. The Player pulls both into a local cache.
> - **The stability obligation carries over unchanged**, and it gets heavier
>   rather than lighter. Once the player repo splits off (wave 5), "deployed
>   together" stops being true even in practice, and the major-refusal rule is
>   all that stands between a new server and an old player.
> - The row's consumer is renamed the **Player**. The two build steps each have
>   a schema bump: the channel change is a minor bump and moving compositing is
>   major 2. See § The Server↔Player surface.

### Transport: streamable HTTP, not stdio

**Decided, and effectively forced.** Claude Code runs on the operator's laptop
while the catalogue and `ART_ROOT` live on the curation host, reached over an
overlay network. stdio transport requires the client to *spawn* the server locally,
which cannot work across that boundary. So the MCP server is an ASGI application
served over streamable HTTP.

**It is mounted in the same application as the curation UI's HTTP API.** One
process, both surfaces binding the same in-memory service layer — which is what
makes the thin-binding norm below structurally easy to hold rather than a rule
someone has to remember. The alternative, a separate MCP process, would need its
own path to the catalogue and would reintroduce exactly the divergence the norm
exists to prevent. The cost accepted: the MCP surface goes down when the UI process
does. That is tolerable because both live on the curation plane, whose downtime is
already defined as invisible to the household (`product-brief.md` → Platform).

> **Direction changed 2026-09-30 — see `re-architecture.md`.** "The curation
> host" becomes the operator's NAS, running the server as a container (wave 3).
> The reasoning above holds as it stands: stdio still cannot cross the boundary,
> and the MCP surface still mounts in the same application as the HTTP API.
> From wave 3 that one application also serves the Player surface.
>
> Its downtime is invisible to the household for the same reason: the Player
> plays from its local cache, not from the server. That is now a property of
> the Player's design rather than of two processes sharing a disk.

### The in-UI agent is an MCP client

**Decided 2026-07-19**, and it is the reason the surface has to be good rather than
merely present. Either way the agent must be taught a surface; MCP describes itself,
so the teaching is free. The stronger argument is scope: making the server the unit
of "an art library on a system" lets one agent manage several, which promotes
multiple libraries from an accommodate-only concern toward a design driver.

What this does **not** imply is routing the UI's own controls through MCP. Tool
results are shaped for a model to read; a UI wants typed, paginated, partial data,
and forcing it through MCP would produce either awkward results or a parallel read
path anyway. Location transparency belongs in the service layer, beneath both
surfaces.

**Each surface carries its own obligation — re-deriving it per surface is the
point.** The MCP surface carries the real versioning obligation. The HTTP API
keeps the original "none — internal-only" answer. The curation↔display contract
does **not**: its exemption was narrowed 2026-07-20 to the bounded obligation in
the table above — additive changes free, a breaking change bumps a major that
display refuses. *(This paragraph previously said the "none" decision "still
holds for the other two" — corrected 2026-07-20; it contradicted the amended
table fifty lines above it, and was one of three surviving sites of the retired
exemption.)* A blanket policy would either over-engineer the HTTP API or
under-protect the other two.

Built on the **official `mcp` SDK** (`mcp>=1.28.1`), not `3tears-mcp` — that package
would drag NATS in via `3tears-epoch`, and its RBAC-gated server has nothing to
gate in a single-principal product. See `project-state.yaml` →
`technical_decisions.technology`.

## Operations

### The framing that was wrong

This artifact previously posed the choice as intention-shaped tools versus
fine-grained primitives, and claimed the coarse option made the Dalí request "one
call". **It cannot be one call, for two independent reasons already committed
elsewhere.** Phase 2 of discovery takes minutes, so a blocking call is the wrong
shape regardless of granularity. And review requires a human, so — as
`product-brief.md` says plainly — an agent cannot literally finish the request; it
stages works and the wall changes when the curator looks. The most a coarse tool
can do is *start* something. That is a much smaller claim than the one this
artifact made, and it dissolves most of the supposed trade.

### The surface

**Each tool is a noun, each dispatches on a required `action` string, and the
table below is the whole set.** This follows the pattern proven in the operator's
two production servers: cordyceps exposes 7 tools with 5–30 actions each;
hallucinote exposes 13. Both sit inside the 1–15 range Anthropic's MCP-authoring
guidance identifies as the point where one tool per action stops paying and
consolidation starts, and so does this table.

*That sentence opened with "Five tools" until 2026-08-11, when `art_taste` made it
six and nothing but a reader would have noticed. The claim worth making is
containment in the range, which the table can be read against; the tally was a copy
of the table sitting four lines above it. The paragraph below records the same
lesson from a different count, which is why this one is stated as a shape.*

| Tool | Actions | Notes |
|---|---|---|
| `art_discovery` | `estimate`, `start`, `status`, `approve`, `decline`, `cancel`, `resolve_images`, `get`, `look`, `list_runs`, `spend`, `source_plugins`, `help` | **The only tool that spends money in amounts worth authorising** — see the correction below. `source_plugins` (added 2026-10-06; not `sources`, which is `art_catalogue`'s provenance read) answers what `GET /api/sources` does, in its field names and values (`test_source_plugins_surface.py`, `test_surface_parity.py`). `look` (added 2026-10-06, `build-plan-look-before-get.md`) is `GET /api/registry/works/{qid}/look`, in its field names, and spends and records nothing; see that route's row. |
| `art_review` | `list_works`, `get_work`, `list_images`, `set_canonical`, `set_verdict`, `reject_image`, `want`, `list_wanted`, `sighting_hosts`, `wikidata_matches`, `set_wikidata_item`, `help` | Returns thumbnails; see Inputs & Outputs. Never spends. `want` and `list_wanted` (added 2026-10-02, `build-plan-after-review.md` Chunk 03) are the one way into `wanted` and Wanted's listing; see § `set_verdict` cannot set `wanted`. `wikidata_matches` offers Wikidata's items for a work's title and stores nothing; `set_wikidata_item` records the curator's pick, refused on a decided work (added 2026-10-02, `build-plan-after-review.md` Chunk 04). `sighting_hosts` counts, by host, the open works with a page there that no installed source plugin reads, and returns no address (added 2026-10-03, `build-plan-source-plugins.md` Chunk 03). |
| `art_catalogue` | `list`, `get`, `sources`, `archive`, `restore`, `retry_acquisition`, `set_mat_color`, `set_work_qid`, `set_artist_qid`, `regenerate`, `topics`, `topic`, `history`, `help` | `sources` is the provenance read; see below. `set_work_qid` and `set_artist_qid` (added 2026-10-01) are the curator's word on a Wikidata identity; matching itself is the hand-run `python -m arrt.identify`, not a tool. `topics` and `topic` (added 2026-10-02) are `GET /api/topics` and `GET /api/topics/{qid}`, the library's half only. `retry_acquisition` **queues** the work and returns at once (changed 2026-10-02, `build-plan-after-review.md` Chunk 02; breaking, see § Versioning): it fetched in the call until then, for up to half an hour, beside the acquisition queue's own fetch. `get` carries the work's `acquisition` state. `history` (added 2026-10-07) is `GET /api/history`: `kinds` (array) and `wall_id` narrow it. |
| `art_theme` | `list`, `get`, `create`, `update`, `delete`, `make_default`, `add`, `remove`, `reorder`, `activate`, `hang_selection`, `not_again`, `kept_off`, `allow_again`, `unhang`, `help` | `activate` changes the wall immediately; `unhang` leaves the wall showing what it was showing. `make_default` (added 2026-10-01) moves the mark new works join, and changes no wall. `hang_selection`, `not_again`, `kept_off` and `allow_again` (added 2026-10-07) are § History, selections and *Not this one again*'s routes on this surface; `list` leaves selections out, and every theme carries `hidden`. |
| `art_display` | `walls`, `add_wall`, `status`, `sync`, `show_now`, `next`, `clients`, `add_client`, `rename_client`, `remove_client`, `issue_client_token`, `assign_wall`, `unassign_wall`, `help` | Every wall action goes through the theme manifest — see below. `walls` is where every other action's `wall_id` comes from, and `clients` every `client_id` and output name. The client actions (added 2026-10-02, `build-plan-clients.md` Chunk 02) are § Clients' routes on this surface; `issue_client_token` answers the token once. Destructive since then, because `remove_client` and `issue_client_token` cannot be undone. |
| `art_taste` | `list`, `set`, `delete`, `help` | The curator's standing judgments about artists, movements and subjects. Never spends. Added 2026-08-11 by operator decision — see below, and § The routes the interface design requires. |

**This table is the surface as designed, and no row states what is built.** That
is deliberate rather than an omission: while the build is in progress some tools
declare fewer actions than they list here, and annotating some rows and not
others is worse than annotating none — a reader takes an unannotated row for a
complete one. **The surface answers the as-built question itself, at runtime and
without ambiguity:** `action='help'` returns exactly the actions a tool serves,
and a tool with none carries `unavailable_note` saying so. A caller therefore
cannot be misled into calling something that does not exist, which is the failure
a build-status column would exist to prevent.

*The sentence above carried a count until 2026-08-03, and the count was wrong —
it had said "three of the five" since before `art_discovery`'s last action landed,
and nothing could notice. A tally in prose about work in progress is stale by
construction; the shape of the claim is what belongs here, and `help` is what
answers the question a number was pretending to.*

**Unbuilt actions are never declared.** Action values are additive and a
declaration is a promise, so an action appears in the registry on the day it
works — a model reading the menu has no way to tell a declared action from a
working one, and finding out by calling it is the expensive way.

### What the review surface must show about an image

`list_images` and `get_work` carry two derived values per candidate image, both
computed by the service layer rather than stored (`data-model.md` → Original):

- **`display_fit`** — `native`, `matted_small`, or `below_floor`, computed from the
  image's pixel dimensions against the configured panel geometry and mat width.
- **The rendered physical size**, in inches, on the configured panel — *"would show
  at 8.6 inches"*. This is the number a curator can actually judge. **A thumbnail
  cannot convey resolution**: a 900 px image and a 6000 px image look identical in a
  review grid, which is exactly why the review gate ("a human saw the artwork")
  does not by itself protect against hanging a postage stamp.

> **Direction changed 2026-09-30 — see `re-architecture.md` § Compositing moves
> to the Player.** "The configured panel geometry and mat width" are server
> settings today (`TV_PANEL_*`, `MAT_*`), and wave 4 removes them from the
> server. After that there is no single panel, because every Player has its own.
> - The fit verdict and the rendered size become something **Programming works
>   out from the geometry each Player reports in its heartbeat**, one answer per
>   wall ("too small for the living room"). The Library stores only
>   panel-independent width and height, as `data-model.md` already requires.
> - The requirement survives unchanged: a curator must be able to see that an
>   image is too small before it hangs. The open design question for wave 4 is
>   what a review card shows before any wall has hung the work.
>
> Until then, these two fields describe the code as built.

> **The browser stopped showing the inches, 2026-10-02** (the owner's ruling,
> `build-plan-topics-and-destinations.md` Chunk 07). A review card states the
> scan's own pixels — `InstanceOut.width` and `height`, the provider's reported
> size, null where none was reported — and the fit badge keeps only the verdict's
> word, everywhere it draws. `rendered_long_edge_inches` stays on the API and
> `renders_at_inches` on MCP, where a reader is told what the figure is about; it
> was a card beside a picture, with no panel named, where it read as a fact about
> the picture. The selection sentence phase 2 writes names pixels for runs from
> then on; a sentence already stored is a record and stays as written.

A `below_floor` image is **shown, labelled, and selectable** — never auto-selected
by phase 2, and never hidden. The curator may take it anyway; that judgement is the
product.

**"Never hidden" binds the listing too, and that took a decision at build
(2026-08-03).** `list_works` carries one picture per work, and the obvious choice —
the *selected* instance — has no answer for a work where nothing was selected,
which is exactly the below-floor case. Such a row would have arrived with no image
at all: not withheld by any rule, just absent, and indistinguishable to a curator
from a work no picture exists for. So the row falls back to the best surviving
instance and reports `is_on_offer: false` beside it. The two states a curator must
not confuse are then still distinct — "this is what you would accept" versus "this
is all there is, and nothing chose it" — and the only row that carries no picture
is one whose instances are all rejected or absent, where there is genuinely
nothing to show.

**A work the library already holds says so (2026-09-30).** A run refuses only a
work the curator rejected, so it can propose one an earlier run acquired.
`list_works` and `get_work` (and the browser's candidate listing) carry
`held_artwork_id`: the catalogue artwork an earlier proposal of the same
`work_dedup_key` became, or null. It is additive, and a caller that ignores it
behaves as before. The browser shows *Already in your library*, makes opening
that artwork the card's first control and keeps a quieter *Accept anyway*,
following Sonarr's Add New
(`information-architecture.md` § The *arr layout). The identity is the dedup
key, with that key's limits: two works sharing a title and an artist read as one.

**`rights_status` is returned alongside**, as a provenance and source-quality
signal. It gates nothing (`data-model.md` constraint 13).

**Listings carry less per instance than `list_images` does**, by the same rule the
catalogue already follows: enough to choose, with the record behind a second call.
This is a budget constraint rather than a stylistic one — see § Token budget.

### How `art_display` reaches the display plane

**Corrected 2026-07-20 (Critic R-17).** This tool's actions were specified before
the manifest-only channel was ratified, and `show_now`/`next` were left with no
route to the plane that would execute them — unimplementable as written, and tool
names are frozen, so it was cheap to settle now and expensive later.

Every action resolves against the manifest. **The curation plane never sends the
display plane a command; it writes desired state, and display converges on it.**

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The mechanism
> changes and the principle does not.
> - `sync` stops writing `theme-manifest-{wall_id}.json` and instead republishes
>   the document `GET /walls/{wall_id}/manifest` serves. Its ETag changes, and
>   the Player notices on its next poll.
> - `status` stops reading `display-heartbeat-{wall_id}.json` and instead reads
>   the last heartbeat each wall POSTed.
> - `show_now` and `next` are unchanged: they still advance a sequence in a
>   document the Player polls.
>
> "Desired state, never a command" is exactly what makes the network hop safe.
> A directive issued while a Player is unreachable is still just state, waiting
> to be read. After the internal split, these actions belong to **Programming**.
> The tool names are frozen and stay as they are.

| Action | What curation does | What display does |
|---|---|---|
| `status` | Reads the display plane's heartbeat file | Nothing — it wrote the heartbeat already |
| `sync` | Rebuilds and rewrites **that wall's** manifest from the theme hanging on it — `theme-manifest-{wall_id}.json` | Picks up the new manifest on its next poll and reconciles. Each display plane reads the one file its `WALL_ID` names, so syncing one wall cannot disturb another |
| `show_now(wall_id, artwork_id)` | Increments **that wall's** directive `sequence` and sets its `pinned_work_id`, and writes that directive into the wall's published manifest | Jumps to that work, then continues rotating from there |
| `next(wall_id)` | Increments **that wall's** directive `sequence` with no pin, and writes that directive into the wall's published manifest | Steps to the next work in the list |

> **Built 2026-09-30 (wave 2b Chunk 02): the directive reaches the manifest.**
> Until then `show_now` and `next` advanced the stored directive and nothing
> wrote it into the manifest, so neither reached the wall until something else
> synced. The write patches the published document's `directive` block and
> nothing else. It is not a sync, so a step publishes no work added to the theme
> since the last one. A wall with nothing published yet carries the directive
> out with its first sync. A write that fails refuses the step, so a directive
> is never recorded as issued when it never reached the wall.

**Every action but `status` takes a required `wall_id`**, built 2026-08-12. The
directive is a row per wall rather than a singleton, so a `next` in the living
room does not step the study — which is the whole point of naming a wall, and
which the earlier form of this table could not express. `status` is the exception
and takes none, but for the opposite reason to the one it used to give: the
heartbeat is per wall now, and `status` answers with `walls[]` — every wall's
reading in one call — so a `wall_id` would narrow an answer that is cheap whole
and is read by a screen showing all of them. It also carries `pictures`, the
picture store's files and bytes, as `GET /api/health` does (added 2026-10-06): it
is the health panel's twin on this surface.

> **Both this row and that paragraph described the pre-per-wall behaviour until
> 2026-08-12**, when Critic review found them — after the split had landed, and
> with the correction already written 1,150 lines further down this file. The
> `sync` cell was the expensive one: it told an external consumer that a second
> wall's sync overwrites the first wall's manifest, which is a data-loss
> behaviour that no longer exists, in the table that is this tool's canonical
> description. A correction placed after the claim does not reach a reader who
> stopped at the claim.

`show_now` **refuses any work that could not reach the wall**, rather than pinning
one, and archiving the pinned work withdraws the pin without advancing the
sequence. Both rules and their reasoning live in `data-model.md` § Directive and
are deliberately not restated here; what this table owes is that a caller sees a
refusal, not a silent no-op.

**Widened from "refuses an archived work" 2026-07-31.** Archiving is what
`data-model.md` specifies, but the neighbouring causes fail identically from the
curator's side: a work with no original, no render, a stale render or no current
mat colour is equally unshowable, and pinning one wrote a directive naming
something the manifest does not carry. The caller was answered "the directive is
written" and the wall never moved — the exact silence the exclusion report exists
to break, arriving through the one action that did not consult readiness. So the
refusal applies the whole readiness rule and returns the same sentence the
manifest build would have given, which tells the curator what to fix.

**This does not discharge the display plane's obligation, and the residual is the
default path rather than a rare race.** `show_now` checks *readiness*, not theme
membership: a perfectly displayable work that simply is not in the active theme
can be pinned, and the manifest's `entries` will not contain it. That is available
on every call, not a timing window. (Readiness changing between the pin and the
read is a second, rarer route to the same state.)

The membership check is deliberately **not** added here: only the display plane
can decide what to do with a pin it cannot resolve, and choosing at the writing
end would design that behaviour from the wrong plane.

**Settled 2026-08-06, when that plane was built.** Display logs one WARNING
naming the work and carries on rotating — the same posture as a missing render
file, and for the same reason: the wall going black is always worse than the wall
being incomplete. Two consequences are worth stating here rather than leaving to
the implementation, because a caller can observe both:

- **The directive is consumed.** The sequence advances on this plane's side even
  though nothing moved, so the manifest is not re-read as a standing instruction.
  Without that, an unresolvable pin would warn once per poll — every second,
  forever — about a condition that will not change until somebody switches theme.
- **A pin issued while the television is asleep is *not* consumed**, and that
  asymmetry is deliberate. An unresolvable pin has been answered; an undelivered
  one has not, and since the manifest does not change, a sequence marked
  acted-on during an outage is a `show_now` the curator never gets. An outage
  therefore delays a jump rather than eating it.

Two consequences worth stating because they surprise:

- **These actions are not synchronous confirmations.** They return "the directive
  is written", not "the wall changed". Actual latency is bounded by display's poll
  interval (~1 s). A result claiming the TV has changed would be asserting
  something curation cannot observe — the same false-success pattern this contract
  already refuses elsewhere.
- **If the display plane is down, the directives queue harmlessly.** The manifest
  holds the latest desired state; display converges whenever it comes back. There
  is no command to be lost, because there is no command — only state.

### Rejecting an image does not re-search — that is a separate call

`art_review(action='reject_image')` marks the instance rejected and, when it was
the scan on offer, moves the work to `wanted`; `art_review(action='want')` does the
same for a work named directly. Neither goes looking for a replacement.
`art_discovery(action='resolve_images', work_ids=[...])` does. **It costs nothing
today** (corrected 2026-10-02, `build-plan-after-review.md` Chunk 05b): phase 2
asks open museum and Commons APIs and makes no model call, so
`RunnerSettings.phase2_estimate_usd` is zero, measured on 2026-08-02. Until then
this section, the review page and MCP's tips called it the paid operation. A paid
image provider added later brings the price back, in that one method.

**This split keeps searching out of the review tool.** Letting `reject_image`
trigger a search inline would put minutes of museum requests, and any future
provider's cost, inside `art_review`, the tool a curator clicks through. It also
means a curator can reject several images while reviewing and re-resolve them in
one batch, rather than firing a search per click.

**`resolve_images` returns a run handle, exactly like `start` (decided 2026-07-20).**
It creates a `DiscoveryRun` with `kind='resolve'` and `parent_run_id` set to the run
that originally proposed the works, and returns immediately with its id. It takes
minutes; it previously created no row, which left it without a handle to poll, a
`cancel`, a cost of its own, or any guard against the same ids being submitted
twice concurrently. `status`,
`cancel`, and `spend` accept a resolve run id with no special-casing.

**It refuses work ids already covered by an in-flight resolve run**, naming them in
the error rather than silently deduplicating — a curator who double-submitted should
find out, not be quietly corrected. Coverage is recorded in `ResolveRunWork`
(`data-model.md`), which is also what lets `status` on a resolve run report *which*
works it is resolving rather than only that it is running.

Spend from a re-search attributes to the **resolve run**, which is what having a row
is for, and rolls up to the originating run through `parent_run_id` so "what did
asking for Dalí cost?" stays answerable. **This supersedes the earlier rule that
re-search spend attributed directly to the originating run** — that rule existed
only because there was no other row to attribute it to. The originating run still
never reopens: a `completed` run stays completed. See `data-model.md` → SpendRecord.

### `set_verdict` cannot set `wanted`

*Renamed and amended 2026-10-02 (`build-plan-after-review.md` Chunk 03, the owner's
#168). This section was "`set_verdict` cannot set `awaiting_better_image`", and its
one entry point was `reject_image`. Both changes below are **breaking** by
§ Versioning — a result enum value renamed, and an action's description and
behaviour changed — and are made with no shim, annotated inline at the replacing
site (`mcp/tools.py`, above `want`), and announced to the operator in the PR.*

**`want` is the one way into `wanted`.** `art_review(action='want', work_id,
turning_down?)` and `POST /api/candidates/{work_id}/want` record that the curator
wants a work and holds no scan of it they would accept. `wanted` covers every
reason a work is wanted — its scan on offer was turned down, nothing was found, or
the only scans found are too small for the wall — because they are one wish; which
it was is read from the work's instances, never stored, and `list_wanted` reports
it as `scans_turned_down` and `shown` together (a work wanted from a below-floor
card has `scans_turned_down` 0 and a `shown` scan). `set_verdict` accepts
`accepted` and `rejected` only, and its refusal of `wanted` names `want`.

**Turning a scan down is still the only way to suppress one.** `want` with
`turning_down` suppresses that scan and fills the vacancy in the same transaction
as the verdict; `want` without it suppresses nothing, because wanting a work found
with no scan is not a judgement about any scan, and a scan nobody turned down must
stay offerable to the re-search that looks for one. `reject_image` turns a scan
down: the scan on offer goes through `want`, so the work becomes `wanted`; an
alternate is only suppressed, and the verdict stands — a curator who turns down a
poor alternate under a scan they like has not asked for a better one.

**`want` takes a `work_id` and, optionally, an `image_id`, and refuses a pair that
disagrees.** § The arity of the three write actions declines a second id beside an
`image_id` because the pair can disagree. `want` is work-scoped — a work found with
no scan has no `image_id` to name — so its scan is the optional one, and a scan
found for a different work is refused by name rather than resolved by a rule about
which id wins.

**The old spelling is not accepted anywhere.** `awaiting_better_image` is an
unknown verdict on HTTP and on MCP, and the stored rows are rewritten by a
migration on open (`persistence/migrations.py`). Both surfaces have one client
each and ship with the server, which is what § Deprecation's no-shims rule rests
on.

**This constrains the target value only — never the source state** (clarified
2026-07-20). `set_verdict` is available from any non-terminal state, including
`wanted`: the curator may accept the best instance on offer or give up on the work
without waiting for a re-search, and must never be blocked on a background job.
`want` is refused on a work already accepted or rejected. The corresponding guard
on the *other* writer: a resolve run completing returns a work to `pending` when it
finds a scan, and never writes over a terminal verdict — it reports its result
without applying it. See `data-model.md` → CandidateWork, "Terminal verdicts are
never overwritten".

**A path to the verdict that skips the suppression is the failure this prevents.**
When two paths reached the old `awaiting_better_image` and only `reject_image` set
`rejected_at`, a work sent there via `set_verdict` had no suppressed instance, and
the re-search could legitimately hand back the image the curator had just turned
down — the suppression failure **Q11** exists to prevent, on the instance scope
instead of the work scope. One entry point that suppresses exactly the scan it is
told about makes it impossible rather than defended against.

### `art_taste`, and the derivation a caller may not claim

Placed beside `set_verdict` above because it carries the same shape of rule: a
write action that accepts most of an enum and refuses one value, because that value
is a claim only another path can honestly make.

**Added 2026-08-11 by operator decision, against the recommendation recorded in
§ The routes the interface design requires** — which argued for deferring the tool
until discovery begins weighting `Affinity`. That section now records the decision
and what the deferral would have bought; this one is the tool it obliges.

**It stands on `Affinity`, and both were built on 2026-08-12.** Until then nothing
here was declared at runtime — "unbuilt actions are never declared" governed it, and
the tool answered `action='help'` with its `unavailable_note`. The paragraphs below
fixed meaning and rules and left field-level shapes to the chunk that built the
service method under them; that chunk has landed, all three actions are declared,
and `FROZEN_TOOL_NAMES` now pins the name it could not reach before. The rules
below are therefore descriptions of built behaviour rather than instructions to a
future builder, with one exception marked where it occurs: the `inferred` invariant
is enforced on the write path only, and deliberately not as a stored constraint.

**Three actions and no `get`.** `list` returns the taste, narrowed by `kind`,
`sentiment` or `derivation`; `set` writes one judgment; `delete` forgets one. The
single-affinity read is omitted rather than overlooked — `list` returns a
household's entire taste, which is tens of rows, so a `get` would be a second way
to read what one call already hands back whole. § Conditional Patterns' limit-and-
report-the-total rule bounds the listing if that ever stops being true.

**`set` is an upsert, and is named `set` for that reason.** `data-model.md` makes
`Affinity` unique on (`kind`, `value`) — one live judgment per thing, corrected in
place rather than accumulating contradictions. `create` would be a lie on the
second call and `update` a lie on the first, so this takes the verb the surface
already uses for "write this fact over whatever was there": `set_canonical`,
`set_verdict`, `set_mat_color`. A correction therefore needs no id — `kind` plus
`value` is the handle, and it is the handle a model has, since the thing being
judged is a name in a sentence rather than a row it fetched. `delete` takes the id
`list` returns, matching `DELETE /api/affinities/{id}` rather than giving one
entity two identities.

**`set` may not write `derivation='observed'`, and the refusal names the path that
can.** The three derivations are claims about where a judgment came from: `stated`
is the curator saying it, `inferred` is a model reading it out of what they said,
`observed` is the product reading it out of accept-and-reject behaviour in review.
Only the review path can assert the third truthfully, and an `observed` row written
by a caller is a fabricated observation — indistinguishable afterwards from one the
product earned. That matters beyond tidiness because `data-model.md` makes
derivation load-bearing: affinities are rebuilt from the retained turns when the
derivation improves (Q14), and a row claiming behaviour that never happened has
nothing to rebuild from and cannot be audited.

**`inferred` requires a `source_turn_id`; `stated` does not.** Both are writable —
the in-UI agent is an MCP client, so the tool is a path a model takes while the
curator is talking to it — but that justification is about *one* caller, and the
tool cannot check which caller it has. Any other client (Claude Code at a terminal
is the stated consumer) could otherwise write "the model read this out of what they
said" citing nothing, which is the same unrebuildable, unauditable row the
`observed` refusal exists to refuse, arriving through the door left open beside it.
`stated` needs no turn because the curator saying a thing is the whole provenance —
`data-model.md` already makes `rationale` normally null for it. *(Added 2026-08-11,
Critic R-11: the first draft guarded one derivation and left its neighbour able to
break the identical invariant.)*

**An upsert may not overwrite a row's provenance with a weaker one.** `set` lands on
(`kind`, `value`), and that row may already carry `derivation='observed'` and a
`source_turn_id` — the sample-reaction path writes exactly that pair. So the rule the
building chunk must not violate: a `set` **replaces the judgment** (`sentiment`,
`open_to_more`, `rationale`) and **replaces the provenance with its own** —
`derivation` becomes what the caller wrote, and `source_turn_id` becomes the turn the
caller cited or null if it cited none. What it may never do is keep the old
`source_turn_id` under the new judgment. That is the cheap default — write the fields
given, leave the rest — and it produces a row whose turn did not produce the judgment
stored on it, indistinguishable afterwards from real provenance, from which Q14's
rebuild then either resurrects a superseded judgment or overwrites the curator's
correction. A correction is a new judgment with its own provenance or it is not
auditable at all. *(Added 2026-08-11, Critic R-17.)*

**Sentiment and openness are both required, because the pair is the entity's
point.** `data-model.md` keeps `sentiment` and `open_to_more` apart so that "meh on
Magritte, but open to learning more" is writable at all; a tool taking sentiment
and defaulting openness would put a default in the way of the one sentence the two
fields exist for, and the default that reads as safe — don't offer more — is the
one that silently blacklists an artist the curator asked to keep hearing about.

**Annotations:** `title` "Art taste", `readOnlyHint: false`, `destructiveHint:
true`, `openWorldHint: false`. Destructive because `delete` drops a judgment and
`set` overwrites one, and neither is recoverable — unlike `art_catalogue`'s
`archive`, which is annotated non-destructive precisely because `restore` exists.
Closed-world because nothing here leaves the machine.

### The arity of the three write actions (settled at build, 2026-08-03)

The rules above specify what these actions *mean*; their argument shape was left
open and is recorded here rather than only in a schema.

**`set_verdict` judges one work per call.** "Requires explicit work ids" is
satisfied by there being no action that omits one — a batch parameter would
satisfy it too, and one call per work is chosen because the payload differs per
work (an `artwork_id`, a minted artist, its near-misses) and a batch result would
either flatten those or invent a per-item envelope this surface has nowhere else.
The accepted cost is the friction the security section already accepts: accepting
a good run's whole output is one call each. A UI's select-all sends the ids either
way.

**`set_canonical` and `reject_image` take an `image_id` and no second id.** An
instance already carries its work, so accepting a `work_id` beside it would create
a pair that can disagree and a rule about which wins — for an argument the caller
would have to fetch anyway. `list_images` is where an `image_id` comes from, which
is also the call that shows the picture being judged. `set_canonical` also takes
an optional `rationale`, which is not an identifier but the curator's reason: it
is persisted on the instance and carried onto the `Source` at promotion, so why
this scan was chosen survives into the catalogue. `reject_image` takes no reason,
and that asymmetry is deliberate — "this one" is a judgement worth keeping, while
"not this one" is followed by a re-search whose result is the record.

### `sources` is its own action, not a field on `get` (settled at build, 2026-08-03)

`art_catalogue` had no way to read where a catalogued work came from. The gap was
not an unbuilt action but a missing one: the table above listed none, so `get`
returned artwork fields and the resolved artist, and `url`, `provider`,
`rights_status`, `is_primary`, `confidence`, `selection_rationale` and
`last_fetch_status` were unreachable over MCP while `GET /api/works/{id}` had been
returning them to the browser all along.

The blind spot opened exactly at acceptance. Before it, scans are inspectable via
`art_review(list_images)` under a run's `work_id`; the promotion that mints an
`Artwork` re-keys them by `artwork_id`, and at that moment they left the surface.
So an agent could not say which source is primary or whether the last fetch failed
— and `retry_acquisition` would have acted on a source its caller could not read.

**Two shapes were available and the round trip is not what decided it.** Folding
`sources` into `get`'s result is *Additive* under the compatibility table below, so
it was compatible and would have cost no extra call. It was rejected because `get`
is the payload every list-then-detail hop pulls, and provenance is not what that
hop is for: rights, fetch status and primacy are acquisition-time concerns, read
when a caller is about to act on a source, not when it is reading a title and a
date. Fattening the common read to spare a call on the rare one is the wrong trade
in a surface whose § Token budget is a standing constraint.

**It reads through `CatalogueService.list_sources()` — the same service method the
browser detail view already uses.** No second projection of "a work's sources"
exists, which is the service-layer norm doing its job: the two surfaces cannot
drift because there is nothing to drift.

### Why not split reads from writes

Anthropic's connector Directory review criteria require read and write tools to be
separate, and would reject a tool that multiplexes both. **That rule is not binding
here** — this product will never be listed — and the operator's own servers
demonstrably do multiplex (`gh_canvas` carries `add`/`delete`/`move` alongside
`list`/`info`).

The mechanism behind the rule is real, though: a multiplexed tool cannot honestly
declare `readOnlyHint: true`, and Claude Code auto-approves read-only tools while
prompting on everything else. For a single operator that cost is retired by
allowlisting the server once.

What remains worth isolating is not reads-versus-writes but **the operation that
spends money**, and that falls on a tool boundary anyway: `art_discovery` is the
only tool with a cost, so it can be gated independently without splitting anything
else. Note the consequence — because MCP annotations are per *tool*, not per
action, an operation needing its own confirmation must be its own tool. That is the
real constraint on how far consolidation can go.

> **Corrected 2026-08-03, when the mat engine landed: `art_discovery` is no
> longer the only tool with a cost.** `art_catalogue(action='set_mat_color')`
> asks a vision model whenever it is given no `hex_rgb`, at about $0.000063 a
> call — **and so does `action='regenerate'`, for a work that has never had a
> mat**. That second path was missed when this block was first written and two
> Critic reviewers found it independently: a work cannot be rendered without a
> mat, `acquire` does not prepare, so the first `regenerate` on every acquired
> work is the paying one. It is the *normal* case, not an edge, which is what
> made the omission worth correcting rather than footnoting. Both actions now
> report `cost_usd` on every answer, including the zeroes. The paragraph above is left standing because its *reasoning* survives
> intact and only its premise moved, and because the reasoning is what a reader
> needs: a boundary is worth drawing where an operation needs its own
> confirmation.
>
> **A mat call does not need one, and the difference is four orders of
> magnitude.** A discovery run is the operation with an approval gate, a run
> handle, a stored estimate and a monthly ceiling behind it; a mat call is a
> fraction of a cent spent on one work at the curator's explicit request, and
> re-preparing an entire collection spends nothing at all because a work that
> already has a mat keeps it. Splitting `set_mat_color` onto its own tool to
> carry an annotation would buy a confirmation prompt nobody wants and a seventh
> tool on a surface this artifact argues should be small.
>
> **What did have to change is `openWorldHint`.** `art_catalogue` declared a
> closed world while `retry_acquisition` was already fetching arbitrary museum
> URLs — understating it to every client that reads the hint, since Chunk 18A.
> It is now `true`. The lesson generalises past this instance: an annotation is
> per tool, so **adding an action can falsify a flag the tool has carried
> correctly for months**, and nothing about the new action's own code review
> would look at that flag.

### Argument shape

**`action` first and required; every other parameter flat and optional.** Not a
discriminated union — the union of all actions' parameters is *flattened* onto one
schema, with per-action validation at dispatch. hallucinote's rationale for this is
worth carrying: a nested `params: {...}` envelope is agent-hostile, and a wire-level
discriminated union forces callers to widen to `str` anyway because the valid set is
runtime data.

**The tool definitions are generated from a registry, not hand-maintained.** One
record per action carries its description, parameters, example, and tips; the wire
schema, the argument validation, the `help` output, and the error messages are all
derived from it. This is what makes them provably consistent instead of consistent
by discipline, and it is the single most transferable thing from the operator's
existing servers.

### Help is an action, not a tool

**Every tool answers `action='help'`**, returning its action menu with per-action
required/optional parameters, a worked example, and tips. It must work with no other
arguments and without touching the catalogue.

Two reasons this beats a dedicated `help` tool: it keeps the tool count down, and —
because help is generated from the same registry as the schema — help cannot drift
from the contract. There is also a hard client constraint behind it: **Claude Code
truncates tool descriptions and server instructions at 2KB each**, so the description
cannot carry the detail. Put the action menu in the description and the depth behind
`help`.

## Inputs & Outputs

**Provenance binds.** Tool results must carry enough for the curator to reconstruct
what an agent did. A `DiscoveryRun` records `initiated_by`, every candidate work
carries its `rationale`, and every candidate image carries its
`selection_rationale` — so "why did forty Dalí candidates appear, and why this scan"
is answerable after the fact, not just during.

### Images are returned inline, and this departs from the operator's other servers

**Decided 2026-07-19.** `art_review` returns candidate thumbnails as image content
blocks.

This is a deliberate departure worth recording, because both of the operator's
production MCP servers do the opposite: cordyceps writes captures to disk and
returns `{filePath, width, height, hint: "Use Read tool to view image"}`;
hallucinote returns absolute paths to its audio captures and reports. Neither ever
emits an image block.

**That pattern does not transfer, because both of those servers are local.**
cordyceps binds `127.0.0.1`; hallucinote is stdio. A returned path works because
client and server share a filesystem. Ours do not — the curation host is reached
over an overlay network, so a path it returns is meaningless on the client. Worse,
it fails by returning a plausible-looking result the client cannot act on.

This requirement is not a preference. `product-brief.md` makes "a curator never
accepts a work without having been shown its image" a success criterion (amended
2026-07-20 — over MCP the enforceable claim is that the image was present in the
transcript; see `security-model.md` § Content Appropriateness), and the review
gate's whole justification is content appropriateness — which only a person
looking at the picture can judge. Inline thumbnails are what make that possible
at all on this surface.

### Token budget

Claude Code caps MCP tool output at **25,000 tokens** and warns above 10,000. A
server may raise its own ceiling via `_meta["anthropic/maxResultSizeChars"]` up to
500,000 characters, but **that applies to text only — images do not benefit.**

Image cost is approximately `(width × height) / 750` tokens:

| Thumbnail | Per image | × 40 works |
|---|---|---|
| 256×256 | ~87 | ~3,500 |
| 400×300 | ~160 | ~6,400 |
| 512×512 | ~350 | ~14,000 |

**Thumbnails are capped at 400px on the long edge**, which keeps a full 40-work
batch comfortably inside the budget. That resolution is sufficient for the judgement
the gate exists to make; it is *not* sufficient for judging mat colour, which
happens after acceptance on a real screen.

**Measured at build, 2026-08-03 — and the text turned out to be half the bill.**
A full 40-work page costs about **10,200 tokens**: 6,400 of picture, exactly as the
table above predicts, and **3,800 of text**. The first shape of the listing put the
text at ~7,000, which took the page past 10,000 with the images alone still inside
it — so the row was narrowed to what a caller needs in order to *choose*, and the
instance record moved behind `list_images`. The lesson generalises past this
surface: a cap sized from the pictures alone is not a cap, because the rows scale
with the same batch and nothing was watching them.

**Two thresholds, held with two different knobs.** Above 25,000 the client
truncates — which takes the *pictures* and leaves the rows, turning this surface
into the metadata listing `security-model.md` § Content Appropriateness forbids —
while above 10,000 it merely warns. So the page **ceiling** is 40, sized against
the hard cap and served to any caller who asks for it; the **default** page is 30,
about 7,700 tokens, sized so a caller who asked for nothing never trips the
warning. The remaining 2% overshoot at the ceiling is deliberate: closing it means
dropping `resolution_status` or `instances_held` from the row, and both carry the
distinction between "nothing was found" and "we could not look".

**The row gains `unresolved_reason` beside `resolution_status`** — which kind of
nothing, null unless the work is unresolved, **with the one exception
`data-model.md` § CandidateWork records: a row whose attempt predates the
column reads null beside `unresolved`.** The column was added nullable and
existing files are widened without backfill, so a null there means "this
attempt happened before the reason was recorded", never "no reason applies". It
is a short enum and it is the answer to the question `resolution_status` raises, so
a caller that has one and not the other has to fetch each work to act.

**Re-measured when it was added, 2026-08-04, because the figures above were taken
without it.** A full 40-row page is now **10,522 tokens** — 6,400 of picture,
unchanged, and **4,122 of text**, up from 3,800. The default 30-row page is
**7,933**, against the 10,000 the client warns at. Both thresholds still hold and
neither cap moved; the field cost about 8 tokens a row, which is roughly a third of
the headroom the default page had. The two budget tests in
`tests/integration/test_review_surface.py` assert each figure against its own
threshold on a live server, so this is a measurement with a mechanism behind it
rather than a number in prose — the next field added to this row fails there before
it costs a curator their images.

**The row also carries `provenance`** — whether the model named this work or a
wired collection offered it (`data-model.md` § CandidateWork). It is on every row
rather than only on offered ones, because a label that appears sometimes is one a
reader learns to stop looking for, and the whole value of the distinction is that
a curator can trust it without checking.

**Re-measured again when that field was added, 2026-08-04.** A full 40-row page is
**10,842 tokens** — 6,400 of picture, still unchanged, and **4,442 of text**, up
from 4,122. The default 30-row page is **8,173** against the 10,000 warning. So
this field cost about 8 tokens a row, the same as the last one, and both
thresholds still hold with neither cap moved. **The pattern across two additions
is the thing to carry forward**: the pictures are fixed and every field lands on
the text, so the default page's headroom is what each one spends — it has gone
from 2,067 tokens to 1,827 across these two, and roughly seven more fields of this
size would exhaust it. The next addition should say what it displaces rather than
assume there is room.

**Two fields were added 2026-08-10, and they displace nothing because they were
spent from the headroom — not because anything was deleted to pay for them.**
`offered_for_artist` and `offered_artist_matched` (issue #95) are a **net add of
two keys on every row**. An earlier draft of this paragraph claimed they were
paid for by shortening `rationale`; that was wrong on its own terms, since
`rationale` is not in this row at all (`_work_summary`'s docstring says so), so no
deletion here funded anything.

**What that costs, by the rate this section already establishes rather than by a
fresh count.** The two additions above measured ~8 tokens a row each. These two
are a null pair on every proposed row and an artist name plus a small integer on
offered ones, so the same order applies. On the precedent rate the default 30-row
page moves from **8,173** toward roughly **8,650**, against the 10,000 warning —
still inside it, with headroom falling from 1,827 to something near 1,350.
**Stated as an estimate, and it is not a measurement**: the runs that would
produce one are the operator's, and the number above should be replaced with a
counted one the next time a full page is measured.

**The headroom sentence above still governs, and now bites sooner.** At this rate
roughly four or five more fields of this size exhaust the default page's room,
not seven. The next addition should say what it displaces and mean it.

**Image content blocks correlate by position and by nothing else.** The protocol
gives a block no identity, and a result's blocks are only the instances that had a
local copy — so block *n* is not row *n* the moment one preview is missing. Every
row therefore carries `image_block_index`, null when it contributed no block, and
every result that carries pictures says so in its notice.

**`list_images` is capped at 12 instances, and it is the third capped result on
this surface** — a work's scans accumulate across every re-search, rejected ones
stay as the record of a judgement, and the growth is driven by a curator asking
for something better rather than by anything that stops. Measured 2026-08-03: a
full card is about **3,600 tokens**, 1,920 of picture and 1,700 of text.

**It offers no paging, and that is a different decision from the page's.** The
still-choosable instances get first claim on the card's slots, so a truncated card
omits scans the curator has already turned down, and reaches choosable ones only
once those alone outrun the cap. **The invariant is not that what fell off ranks
lowest — it is that nothing omitted is both choosable and better than what is
shown.** Those differ, and only the weaker one is true: once the choosable scans
fill the card no refused scan is on it at all, and a refused scan is typically the
*highest*-confidence one there is, since being the best on offer is why it was
offered and turned down. A notice claiming the omitted scans rank below the shown
ones is therefore false in exactly that state. It names the two kinds of omission
separately instead, which is also what makes an offset not worth having — unlike a
page, where what falls off is arbitrary and paging is the remedy.

**The rows keep the store's ranking, and the notice must not imply otherwise.**
Filling by preference and ordering by rank are different operations: a card can
legitimately read [choosable, refused, …, choosable], so a sentence promising the
choosable ones "first" would send a caller to the top of a list where the
alternate they want sits last. Which scans are still open is a per-row fact and is
reported as one.

Truncation is always explicit. A result that omits rows says so and says how many —
never a silent cut. Where the action takes an `offset` the notice names paging as
the remedy; `art_discovery(action='status')` deliberately does not, because it has
no offset to point at — `art_review(action='list_works')` is the paged listing it
defers to — and `art_review(action='list_images')` does not, because paging its
list would be an affordance pointing the wrong way.

**Every cap on this surface is measured by a test, not argued in prose.** The
reason is recorded above: the page cap was first sized from its images alone, and
the rows — which scale with the same batch — came to nearly as much again.

### Long-running operations: start, then poll

**Discovery must not block.** `art_discovery(action='start')` returns a run handle
immediately; `action='status'` polls it.

Three client facts force this, all verified rather than assumed:

1. **MCP's own Tasks primitive is unusable here.** SEP-1686 landed in spec revision
   `2025-11-25` marked experimental, and Claude Code closed the request to support
   it as *not planned*. Declaring `execution.taskSupport: "required"` would break
   Claude Code outright. `"optional"` is safe and forward-looking; `"required"` is
   not.
2. **Claude Code aborts a call that goes silent.** No response and no progress
   notification for 5 minutes on HTTP transport ends the call.
3. **A call still running after 2 minutes is auto-backgrounded** by Claude Code
   (≥ 2.1.212). Start-and-poll is correct either way, and does not depend on that
   version.

hallucinote reaches the same conclusion independently and supplies a calibrated
number: its status action long-polls for 45s, sized to sit under a 60s tool timeout.

> **Built 2026-08-02, and the hold is keyed on work in flight rather than on the
> run's state.** The obvious implementation — hold while the run is in a
> process-held state — was written first and was wrong in a way worth recording,
> because it looked right and failed silently. A run's status can name a phase
> that *nothing in the current build advances*: after phase 1 lands a work list,
> a run sits in `resolving_images` because that is truthfully where it is, and
> image resolution is a later chunk. Every `status` call on such a run waited out
> the full 45 seconds to report something that had been true for minutes, and the
> only symptom was a slow surface.
>
> Asking instead whether *this process has the run in hand* is both correct and
> the one formulation that cannot go stale: a phase this process does not run is
> a phase it does not register, with nobody having to remember to say so. It also
> answers `interrupted` correctly for free — after a restart nothing is in flight,
> so the call returns at once.
>
> **The whole dispatch moved off the event loop** to make the hold safe
> (`asyncio.to_thread` in `mcp/server.py`). A 45-second hold on the loop would
> stop every other request in the process, the browser surface included. The
> synchronous service layer was already reached this way from HTTP, because
> Starlette runs a synchronous endpoint in a worker thread, and the catalogue is
> built for it — one connection behind a reentrant lock.

> **Amended 2026-07-20 — a "must" withdrawn.** Point 2 previously continued: *"So
> the server **must** emit `notifications/progress` during phase 2 — this is what
> keeps the connection alive, not a nicety."* That is withdrawn on two findings from
> reading the SDK.
>
> **It can silently do nothing.** `Context.report_progress` no-ops when the client
> did not send a `progressToken` (`mcp/server/fastmcp/server.py:1170-1173`). A
> keep-alive that depends on client behaviour we do not control, and fails
> invisibly, cannot be the thing a design rests on.
>
> **It is unnecessary.** The run handle returns immediately, so the only long call
> is the status long-poll capped at 45 s — nowhere near either threshold. Nothing
> is ever idle long enough to need keeping alive. The start-and-poll shape was
> already doing the whole job.
>
> Corroboration: neither of the operator's production servers emits progress
> notifications at all. hallucinote backgrounds work behind a blocking `status`
> action; cordyceps is stateless JSON with no SSE stream, so mid-call
> server-to-client notifications are structurally impossible there. Both reached
> polling independently.
>
> Progress notifications remain **permitted as a UX nicety** where a client does
> send a token. They are not a correctness dependency, and nothing may be designed
> as though they were.

### `estimate` answers two different questions, by arity

**Specified 2026-08-02.** The action appeared in the surface table from the start
and its behaviour was never written down. Every artifact frames the estimate as
*post*-phase-1 ("the moment phase 1 finishes, the work count is known and the
phase-2 cost is computable"), which left `estimate` with nothing to return when
called before a run exists — while issue #12 simultaneously requires a "pre-run
estimate" that phase-1 searches count inside. Both are real, and they are two
questions:

- **`estimate` with no `run_id`** — "what will it cost me to ask this?" Returns the
  **phase-1** figure: one model call plus the flat phase-1 search allowance. It is
  computable before anything runs, which is what makes it the number shown at the
  point of decision. Bounded rather than typical, per the cap.
- **`estimate` with a `run_id`** — "what will it cost to resolve what I found?"
  Returns that run's stored `estimated_cost_usd`, the **phase-2** figure. **That
  figure is zero as of 2026-08-02**, when phase 2 was built against museum APIs:
  they are open and unmetered, and whether a result is the requested work is
  decided locally, so resolving a work list makes no model call and no paid
  search. The action, the arity and the stored value all stay — a zero that a
  caller can read is the answer to the question, and the `basis` alongside it says
  *why* it is zero so it cannot be misread as a missing estimate. **The approval
  gate is unaffected: it fires on the work count and never was on the price.**

Both are *read-only and free*. `estimate` is the one `art_discovery` action that
spends nothing, which is worth stating explicitly on the tool that is otherwise
defined as the one that spends: an agent must be able to price an intent without
committing to it.

The phase-2 figure is **stored, not recomputed on read**, for the same reason
`approval_required` is stored — prices and caps are configuration, and a run
reviewed later must still report the estimate it was actually authorised against.

> **Built 2026-08-02, with one thing settled that this section had left open.**
> The phase-1 figure has to come from *somewhere* before any engine exists, and
> the answer is arithmetic over deployment values — the assumed per-run token
> basis at the configured prices, plus the flat phase-1 allowance at the
> configured search price. So `estimate` reaches no engine, which is what makes
> it answerable on a deployment where discovery itself is not wired up, and is
> the sharper form of "free": it is not merely unbilled, it is incapable of
> spending.
>
> **Refusing is part of the contract too.** `estimate` with a run id that has not
> finished phase 1 is refused rather than answered with a zero or a null — there
> is no work count yet, so there is no figure — and the refusal names the
> run's state and points at the no-argument form.

> **A run reports how its intent was read (added 2026-08-02).** Every payload
> carrying a run carries `strategy` beside the verbatim `intent`: one or two
> sentences, in the engine's own words, on what it took to be in scope and what
> it searched for. It is `null` until phase 1 finishes, because nothing has read
> the intent yet, and it stays `null` on a run whose engine offered no account.
>
> The two fields answer different questions and neither substitutes for the
> other. A work list is judged against the *reading* of a request rather than its
> wording, so "you asked for recent, I took that to mean 2026 prize winners" is
> what makes a surprising list explicable instead of merely wrong — and a curator
> who disagrees with the reading can decline at the gate rather than working
> through works that were never going to match.

> **A run says why its worker ended it (added 2026-10-05, #207).** Every payload
> carrying a run carries `end_reason`: on `failed` and `halted_by_budget`, the
> sentence the worker composed when it ended the run, stored with the ending in
> the same write; `null` on every other ending, and on a run that ended before
> the field existed. It is prose for a reader, never a code to branch on, and it
> sits beside the terminal state rather than replacing it: the state says which
> response is right (constraints 1 and 3 under § Error Model), and the reason says
> what to investigate. A halt's reason quotes the provider's refusal, which names
> the limit that refused; a request the provider declined as unaffordable fails
> the run instead, and its reason carries what was asked for against what was
> left. A fault nothing anticipated
> records a fixed sentence pointing at the server log and never the exception's
> text, for the reason stack traces stay out of tool results. The MCP `status`
> notice for a failed run names `end_reason` when it is set, and the log only when
> it is not.

### Partial success is the normal case

A run that resolves 34 of 40 works succeeded partially. Bulk actions return a
per-item breakdown rather than a single verdict — the shape cordyceps uses for its
bulk operations: `{success: failed == 0, changedCount, failedCount, results[],
error}`, where `results[]` carries a per-id outcome. Unresolvable items are
*reported as failures*, never silently skipped.

## Error Model

**Envelope: decided 2026-07-19.** Errors are returned as **tool results with
`isError: true`**, never as JSON-RPC protocol errors — with one exception: an
unknown *tool* stays a protocol error, because the client addressed something that
does not exist. Everything past that point concerns a known tool, and a known tool's
failure is information the model should be able to act on. The MCP specification
supports this directly: execution errors are meant to "contain actionable feedback
that language models can use to self-correct and retry", and clients SHOULD feed
them back to the model.

> **The unknown-tool exception is retired, 2026-07-27, on building it.** It is
> not implementable on the official SDK: `Server.call_tool`'s request handler
> wraps the registered function in an unconditional `except Exception` and
> converts anything raised into a normal `CallToolResult(isError=True)`
> (`mcp/server/lowlevel/server.py`, 1.28.1). No exception survives that
> boundary, so a protocol error cannot be raised from the point a tool name is
> first seen. Independently confirmed in `3tears`' changelog, which records the
> same behaviour *"confirmed directly against that dispatch path, not just by
> reading its source"* after it swallowed a graph interrupt.
>
> **What ships instead:** an error result naming the unknown tool and
> enumerating every tool the server has registered — `[known.name for known in
> TOOLS]`, so the list is whatever is declared on the day rather than a number
> written here. *(This read "the five real names" until 2026-08-11 — Critic R-10 —
> which was the third stale tool count in this artifact and the only one stating
> what a shipped payload contains. Between 2026-08-11 and
> 2026-08-12 "registered" was not the same set as § The surface, `art_taste` being
> designed and undeclared; it shipped on the 12th and the two sets agree again.)* The same
> teach-don't-guess shape as every
> other error here. The exception's own reasoning is what makes this cheap: a
> client only calls names `list_tools` returned, so the case is defensive
> rather than live. Stated as a retirement rather than quietly implemented
> differently, because a future reader finding the old rule would otherwise
> take the code for a bug.

`isError` is **derived from the payload**, not set by hand at each call site — a
result is an error iff its `success` field is boolean `false`. Both of the
operator's servers do this, and the reason is that a hand-set flag drifts from the
body it is supposed to describe.

> **Implemented as the negative — "an error unless `success` is boolean `true`"
> (2026-07-27).** The two readings agree on every payload this surface produces,
> because the two constructors always set a boolean; they differ only on a
> malformed payload with no `success` at all, and there the negative form fails
> closed. That case is a defect, and reporting a defect as a success is this
> codebase's existing failure shape — `upload_file` catches every exception,
> records a null content id, and returns with success set. Rule 4 below forbids
> exactly that, so the derivation obeys rule 4 rather than the letter of the
> "iff".

### Errors teach

Every error carries four things: **what was wrong**, the **enumerated valid set**,
a **correct example**, and a pointer to `action='help'`. Worked shape:

```json
{ "success": false,
  "error": "Unknown action: 'aprove'",
  "valid_actions": ["list_works", "get_work", "set_verdict", "..."],
  "example": "art_review(action='set_verdict', work_id='...', verdict='accepted')",
  "hint": "Use art_review(action='help') to see all actions with their parameters." }
```

**No fuzzy nearest-match suggestions.** Neither production server implements "did
you mean" — there is no Levenshtein or close-match logic in either. The substitute
is always to enumerate the full valid set inline, which is more useful to a model
than a single guess and cannot mislead.

**Log the full exception operator-side; ship the message only to the client.**
Stack traces are for the journal, not the tool result.

**These constraints were already decided and continue to bind:**

1. **`halted_by_budget` is a distinguishable outcome, not a generic failure.** An
   agent must be able to tell "you are out of money" from "the fetch failed" —
   the first means stop, the second means retry. Collapsing them makes a spend cap
   that fails closed behave, to an agent, like a transient error worth retrying.
2. **Partial success must be expressible.** Partial dezoomify tile fetches are
   normal, and a run that acquires 30 of 40 works succeeded partially. An
   ok/fail binary would force one of two lies.
3. **`interrupted` is distinguishable from `failed`, for the same reason (added
   2026-07-20).** A run reported as `interrupted` was stopped by a curation restart
   or OOM kill; a run reported as `failed` hit an error. **The correct caller
   response differs** — re-run the first unchanged, investigate the second — which
   is exactly the discriminator test this contract already applies to
   `halted_by_budget`. An agent that cannot tell them apart will either retry a real
   fault forever or escalate a routine deploy restart as a bug. `status` and
   `list_runs` therefore return the terminal state itself, never a collapsed
   ok/error flag.
4. **Never report success on a failed operation.** This is the product's existing
   defect pattern — `upload_file` catches every exception, logs, and returns
   having recorded a null content id while the retry loop sets `success = True`.
   The contract must make that shape impossible rather than merely discouraged.
5. **Errors are typed and specific.** A broad catch at a tool boundary needs
   `# prawduct:allow prawduct/broad-except -- reason`.

## Versioning

**Decided 2026-07-19: no version negotiation. Tool names are a frozen contract;
actions are the unit of evolution; changes are additive-only.**

This decision was **reopened, not silently amended**. The original — no versioning,
internal-only — carried the revisit trigger *"any consumer not deployed from this
repo"*, and the MCP requirement fired it the same day it was written. Preserving
that history matters: the trigger doing its job is the evidence the mechanism works.

### Why no scheme

**The specification has nothing to offer here.** Tool semantic versioning (SEP-1575,
proposed 2025-09-29) remains a dormant proposal, sponsored by nobody and adopted
into no spec revision. There is no standard for versioned tools to conform to, so
"adopt the standard" is not an available choice.

What the protocol *does* provide is `notifications/tools/list_changed`, which Claude
Code honours by refreshing its tool list automatically. Combined with the fact that
every client here is the operator's own, that makes evolution genuinely cheap — a
breaking change is recoverable in a way a public API's would not be.

### The rules

| Change | Verdict |
|---|---|
| Add a tool | Additive. Safe. |
| Add an action to a tool | Additive. Safe. **This is the intended growth path.** |
| Add an optional parameter | Additive. Safe. |
| Add a **required** parameter | Breaking. Add it optional with a default instead. |
| Add a field to a result | Additive — readers tolerate unknown keys, the discipline `3tears` already uses for its `--json` envelopes. |
| Add a **value** to a result field that reads as an enum | Additive, **on the condition that the new value's own meaning is carried in prose beside it** — see below. |
| Remove or rename a **tool** | **Not permitted.** |
| Remove or rename an **action** | Breaking. Announce, then retire with the retirement noted inline at the old name's site. |
| Change a tool or action **description** | **Treat as breaking.** |
| Change the prose of a result's `notice` | Additive. Not a description — see below. |

**On the `notice` row — ruled by the builder on 2026-08-17, mid-chunk, when
subject–verb agreement was corrected across nine sentences in `_run_notice`.**
That change edited prose that ships to every external client, and the plan it was
built under recorded "Artifacts consumed: none" — so the question of whether it
crossed this boundary had no recorded answer, and the next builder editing a
notice would have had to guess.

**Whose ruling this is.** Every other ruling in this document is the operator's,
and this one is not. It was taken to unblock the change that raised it and stands
until the operator rules otherwise. Naming the author here rather than only in
the change log is the point of this paragraph: a rule written in the document's
own voice reads as settled by nobody, and nobody is who a reader cannot argue
with.

The answer is that it does not, and the reason is the same property the enum row
above already leans on: **a description is switched on, a notice is relayed.** A
client chooses a tool by its description, so changing one changes what gets
called; a client hands the notice to a reader — a human or a model — so changing
one changes only what that reader is told. That is what makes "the new value's
meaning is carried in prose beside it" a workable condition at all: if callers
parsed the prose, prose could not be the escape hatch for a growing enum.

**Two things this does not license.** A notice that stops saying something a
caller was told to act on is a removal, not a rewording — the retirement rule
applies. And a notice is not a place to put a fact with no field behind it: the
prose accompanies the structured result, it does not substitute for it.

**On the enum row, added 2026-08-04 when `acquire` first grew a value.** The table
had no verdict for this and the answer is not the same as adding a *field*. An
unknown key is ignored by a reader that does not know it; an unknown **value** in a
key the reader already switches on falls through every branch it has, so the caller
carries on as though nothing happened — which is the failure mode
`retry_acquisition`'s new `kept_held` would produce exactly when it matters, a
curator told nothing while their re-fetch was refused. It is Additive only because
this surface pairs every outcome with a `notice` in prose, so a client that
understands no outcome values at all still relays a sentence saying what happened.
**A result field that reads as an enum and has no prose companion cannot grow a
value additively** — give it the companion first.

> **A related correction, same date.** `retry_acquisition`'s tip said *"A failed
> attempt replaces nothing — the work keeps whatever image it already held."* That
> was true and was read as more than it said: paired with the tip above it
> recommending retry *after a partial fetch*, it implied retrying was safe, while a
> partial re-fetch overwrote a complete master. The tip now states what the code
> enforces. By the last row of the table this is a breaking description change, and
> it is made anyway: the alternative is keeping wording whose plain reading is false,
> and the compatibility rule exists to protect callers rather than to preserve
> sentences that mislead them. (The behaviour it now describes is constraint 16 in
> `data-model.md`.)

> **`retry_acquisition` stops fetching in the call, 2026-10-02** (the builder's
> recommendation in `build-plan-after-review.md`, unopposed by the owner; Chunk 02).
> It now queues the work and answers with the work's queue state, and the fetch's
> outcome is read afterwards from `get`'s `acquisition` and from `sources`. A
> behaviour and description change, so breaking by the table, and made because the
> old shape broke a rule the owner set for the Pi: one fetch at a time. A tiled
> fetch may run half an hour, and a synchronous retry would have run beside the
> queue's own. Its `outcome`, `detail`, `relative_path`, size fields and the
> per-outcome notice (a partial fetch "has gaps; retrying may complete it") went
> with it; `sources` still reports a partial fetch as `partial_tiles`. The
> deployment faults' remedies moved from this binding's `except` clauses to
> `DEPLOYMENT_REMEDIES` in `library/acquisition/service.py`, which the queue's
> pause carries to every surface. Annotated at the action in `mcp/tools.py`, and
> announced to the operator in the PR.

> **Re-searching is said to cost nothing, 2026-10-02** (Chunk 05b). The tips of
> `art_review`'s `want` and `reject_image` and of `art_discovery`'s
> `resolve_images`, the notices `want`, `resolve_images` and the review's
> nothing-choosable listing return, the double-submit refusal, and the server's
> instructions said a re-search "spends", is "the call that spends money", or
> "would pay twice"; they now say it costs nothing, or would search twice. It costs nothing today
> (§ Rejecting an image does not re-search). By the table, a description change
> is breaking; it is made because the old wording told an agent to ration a free
> call. The server's instructions now say `art_discovery` is the only tool that
> spends money in amounts worth authorising, as its own summary already did.

> **`resolve_images` says *wanted works*, 2026-10-02** (Chunk 02, carried from
> Chunk 03's review). Its description read "works whose instances the curator
> turned down", and its example "a work_id awaiting a better image". Since
> `want` can mark a work wanted with no scan at all, and its answer sends an agent
> here, the text now says "wanted works, with or without a scan", and the example
> takes an id from `art_review(action='list_wanted')`. The behaviour is
> unchanged; by the table a description change is breaking, and it is made because
> the old wording would steer an agent away from re-searching a work that never
> had a scan. Annotated at the action in `mcp/tools.py`.

**Tool names never change.** hallucinote states the rule as *"stable surface — never
rename, only alias"* and enforces it at import time; cordyceps pins its seven tool
names in an explicit test whose comment reads *"a regression here silently renames
the entire MCP tool surface for every client."* Both learned it the same way:
cordyceps' one consolidation to unified tools required follow-up sweeps through
prompts, guides, and a stale tool count in its own documentation.

**That last row is the non-obvious one.** A description change alters tool-selection
probability even when the JSON Schema is untouched, so a "harmless wording fix" can
change which tool a model reaches for. This is sound reasoning rather than a
measured finding, and it is flagged as such — but it has a concrete consequence:
descriptions belong under the same review and evaluation discipline as schemas, not
treated as prose.

## Deprecation & Compatibility

**Announce, retire, and annotate — no compatibility shims.**

The asymmetry that licenses this: these MCP clients are **not** anonymous third
parties. They are the operator's own Claude Code sessions and the in-UI agent. A
breaking change means telling one person and updating one config, not a migration
window for strangers.

- **Retired actions are annotated inline** at the site that replaced them, naming
  what went and why. hallucinote does exactly this, carrying a ticket id in the
  comment and restating it in the tool description.
- **No compatibility shims for wire-shape breaks.** hallucinote's precedent is a
  strict version handshake with a documented per-call bypass, on the reasoning that
  the cost of a false positive (re-run the install) is tiny against a false negative
  (silent "unknown action" errors). That trade holds here for the same reason.
- **The 12-month deprecation window the MCP project uses for its own features is a
  precedent, not a rule that binds servers.** It is disproportionate for one
  operator and is not adopted.

## Surface Inventory & Stability Tiers

The MCP surface is the only one needing tiers. The HTTP API ships with its only
consumer and carries no obligation. The curation↔display contract is not
tier-less: it carries exactly one rule — additive changes free, a breaking change
bumps the manifest's major version, and display refuses an unrecognised major and
keeps the manifest it has. *(Corrected 2026-07-20 — this sentence previously said
both internal surfaces "ship with their only consumers", which is the retired
exemption's reasoning and must not be cited for the manifest contract.)*

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The manifest
> contract keeps its one rule, and gains **a written schema as its authority**.
> A JSON Schema plus example manifests, owned by the server, is written in wave 1
> before the HTTP channel is built. After the repo split the Player's tests pin a
> copy.
>
> That closes the residual `boundary-patterns.md` records: today each plane is
> tested against its own reading of the contract, and nothing checks the two
> readings agree. Once the two sides live in different repositories, a shared
> fixture is the only thing that can.

| Element | Tier | Meaning |
|---|---|---|
| Tool names (every row of § The surface) | **Frozen** | Never renamed or removed. **Pinned by test from the day the tool is declared, and frozen by decision until then** — `FROZEN_TOOL_NAMES` in `arrt/tests/contract/test_mcp_surface.py` asserts set-equality against the live server, so it can only ever cover tools that exist. `art_taste` was Frozen from 2026-08-11 and, for one day, was the one name nothing pinned; it shipped on 2026-08-12 and its entry joined that set with it. *(The row said only "Pinned by test" until 2026-08-11 — Critic R-16 — while widening itself to cover exactly the name the pin cannot reach.)* |
| `action` values | **Stable** | Additive; retirement is announced and annotated. |
| Required parameters | **Stable** | New ones must be optional with a default. |
| Optional parameters | **Additive** | May be added freely. |
| Result fields | **Additive** | Readers tolerate unknown keys. |
| Tool and action descriptions | **Stable** | Changing one is a behavioural change; see Versioning. |

### The HTTP surface, as built 2026-08-01

Recorded so "carries no obligation" is not read as "is undocumented". These
routes exist and are exercised end to end against a booted server by
`arrt/tests/integration/test_browser_surface.py`; nothing outside this
repository may bind to them, and they may be reshaped in any commit that reshapes
the client with them.

| Route | What it is |
|---|---|
| `GET /` and every page path in `UI_PATHS` (`arrt/src/arrt/http/pages.py`) | The client shell. Listed rather than globbed, so a mistyped `/api/...` 404s instead of returning HTML a client parses as JSON. `UI_PATHS` is the list, rather than a copy here, because it grew with every sidebar page and a copy was six paths behind it. |
| `GET /static/…` | The client: a stylesheet and a tree of ES modules under `app.js`, no build step. Every file, and the shell on every UI path, carries `Cache-Control: no-cache` (`pages.CLIENT_CACHE_CONTROL`, which says why): the modules import names from one another, so a browser holding any of them across a deploy can stop the client from starting. A `/static` file answers a conditional request with 304. **Added 2026-10-05.** |
| `GET /api/works` | A page of works, each with its fit verdict and image state. `sort` is `title` (the default), `artist` (unattributed last) or `newest`, and orders the page only: the total and the facet counts describe the same set whatever the order. An unknown value is refused by name. |
| `GET /api/works/{id}` | One work with sources, renditions and mat history. |
| `GET /api/works/{id}/thumbnail` | A downscaled copy, generated on first ask and revalidated thereafter. |
| `GET /api/themes`, `GET /api/themes/{id}` | Themes, and one theme's works in curated order. |
| `POST /api/themes` | Record a theme. |
| `POST`/`DELETE /api/themes/{id}/works[/{work_id}]`, `POST .../position` | Membership and order. Each returns the resulting order, so the surface repaints from the response. |
| `POST /api/themes/{id}/activate` | Change the wall. Returns the manifest that was published, exclusions included. |
| `GET /api/manifest` | What a theme *would* put on the wall, evaluated without writing. |
| `GET /api/sources` | Every installed source plugin, most preferred first, as `GET /api/health`'s `sources` reads it, with `interface_version` (`major.minor`, the plugin interface this Arrt provides). Settings › Sources reads it; `art_discovery(action='source_plugins')` answers the same. Added 2026-10-06. |
| `GET /api/health` | Every observation the panel states: **one heartbeat per wall** with the document that wall's display reported, the backup's age, this deployment's resolved artwork box, **every installed source plugin** (`sources`, added 2026-10-03), and the picture store's files and bytes (`pictures`, added 2026-10-06). There is deliberately no budget balance, settled 2026-08-04. Shape below. |

Added 2026-08-05 with the run half of the browser surface, and exercised by
`arrt/tests/integration/test_browser_discovery.py`:

| Route | What it is |
|---|---|
| `GET /api/estimate` | What asking would cost, before anything is committed. Optional `run_id` asks the phase-2 question instead. Spends nothing. |
| `POST /api/runs` | Begin a run. Returns a handle at once; phase 1 proceeds on a worker behind it. Records `initiated_by: web_ui`. |
| `GET /api/runs` | The newest runs, newest first, capped at `MAX_RUNS_LISTED` in the service so this route and its MCP twin report the same history (#54). `total` and `truncated` say what the cap left out, and there is no paging: optional `status` and `kind` filters are how a caller reaches older runs. Activity's Queue and History split this one capped listing on `is_terminal`, and each says when the cap left runs out. `awaiting_works` counts every work, across all runs, that found an image and has no verdict, and `awaiting` gives the same by listed run (a run with none is absent); `awaiting=true` narrows the listing to such runs before the cap, which is what Activity › To review reads. `art_discovery(action='list_runs', awaiting=true)` carries the same. |
| `GET /api/runs/{id}` | The run, its works, its tallies and its search usage. |
| `POST /api/runs/{id}/approve`, `/decline`, `/cancel` | The approval gate and the stop. Each returns the whole resulting view, as the MCP surface does, so the client repaints from the response. |
| `GET /api/runs/{id}/spend` | What the run actually cost, including every re-search descended from it. Read by the run view's costs panel once the run is terminal — it is the only place the **family total** appears, since the run record carries only the run's own direct spend. |

Added 2026-08-05 with the review half, and exercised by
`arrt/tests/integration/test_browser_review.py`:

| Route | What it is |
|---|---|
| `GET /api/runs/{id}/candidates` | A page of the works a run is responsible for, each as a card: the instance whose picture stands for it, its size on this wall, and whether that instance is the one a verdict would accept on. **Paged where the run view's own work list is not**, and the difference is the payload rather than an inconsistency — that list is text, this one is a card per work. |
| `GET /api/candidates/{work_id}` | One card, which is what the grid repaints a single tile from after a verdict. Every candidate work, here and on MCP's summaries, carries `artwork_id`: the catalogue work its acceptance made, or null (added 2026-10-02, Chunk 02). Every candidate work served over HTTP also carries `decided`, true when its verdict is final (`Verdict.is_terminal`: accepted or rejected), which the review card hides its verdict and scan controls on (added 2026-10-06, `build-plan-artist-search-review-fixes.md`). Additive. |
| `GET /api/candidates/{work_id}/images` | Every scan found for the work, in the order the card offers them, capped — with `held` and `shows_every_choosable_instance` beside the rows so a truncated card cannot read as a complete one. Each instance, here and as a card's `shown`, carries the scan's own `width` and `height` in pixels (added 2026-10-02; null where the provider reported none). MCP's `list_images` already carried them as `estimated_width` and `estimated_height`. |
| `POST /api/candidates/{work_id}/verdict` | Accept or reject. Carries the minted artist and any held painter it may duplicate, which is the one part of a promotion a curator can neither see nor undo from the work. `wanted` is refused here — `want` is its only entry. |
| `POST /api/candidates/{work_id}/want` | Want the work, `{turning_down?}` (added 2026-10-02, `build-plan-after-review.md` Chunk 03). Returns the work. Naming a scan suppresses it; naming none suppresses nothing. Refused on a decided work. Twin: `art_review(action='want')`. |
| `GET /api/wanted` | Every wanted work across runs, newest run first: `work_id`, `title`, `artist`, `run_id`, `wikidata_qid`, `scans_turned_down` (added 2026-10-02, Chunk 03), and `shown`, the scan its review card pictures it by (an `InstanceOut`, as on the card), or null when nothing was found or every scan was turned down (added 2026-10-06, `build-plan-wanted-pictures.md`). Uncapped, because each row is a work somebody wanted by name; so no row's bytes are read: whether a picture exists is a `stat`, and the browser asks the preview route for each. Twin: `art_review(action='list_wanted')`, whose `shown` carries the card summary's fit fields and sends no image block; its notice names `art_review(action='get_work')` for the picture whenever a row has one. |
| `GET /api/sightings/hosts` | Each host with a page for an open work (wanted, or unresolved with no verdict) that no installed source plugin reads: `host`, `works`, most works first (added 2026-10-03, `build-plan-source-plugins.md` Chunk 03). **A host is a name; no page's address is returned**, because a sighting's URL came from a registry anyone can edit (`security-model.md` § Direction). Uncapped, and bounded by the distinct hosts the open works' items name, which they mostly share (MoMA, Google, WikiArt): a row per host, never per page. Twin: `art_review(action='sighting_hosts')`. |
| `GET /api/candidates/{work_id}/wikidata-matches` | Wikidata's items matching the work's title, the proposed artist's first: `state` (`known`, `not_configured`, `unavailable`), `note`, and `matches` of `qid`, `title`, `creator`, `sitelinks`, `has_image`, `by_proposed_artist`. Stores nothing (added 2026-10-02, Chunk 04). |
| `PUT /api/candidates/{work_id}/wikidata-item` | Record the item the curator picked, `{qid}`. Returns the work. Refused on a decided work and on anything but an item id (added 2026-10-02, Chunk 04). |
| `POST /api/candidate-images/{id}/select`, `/reject` | Choose a scan, or turn one down. Rejecting returns the *work*, because turning down the scan on offer moves it to `wanted`; turning down an alternate leaves its verdict where it was. |
| `GET /api/candidate-images/{id}/preview` | The picture, re-encoded to JPEG. **Not the cached file served directly:** a preview's name on disk is derived from a URL and falls back to `.jpg` for anything unrecognised, so the suffix is not evidence of what the bytes are. Held rather than revalidated — the bytes behind an image id are written once and only ever deleted. **`size=large`** (added 2026-10-02, Chunk 07) is the picture a card enlarges in place: the largest preview the server holds, at its own size (843 px wide from ARTIC, 960 from Commons), bounded at 2048 px for decode memory; the default `card` fits 480 px. Any other value is refused (422). |
| `POST /api/runs/resolve` | Look again for images of wanted works. A re-search is a run, so `GET /api/runs/{id}` follows it with nothing special to know. Records `initiated_by: web_ui`. |
| `POST /api/gets` | Get works chosen by their Wikidata items, `{qids}`: one run of kind `get`, phase 2 only, spending nothing. Returns `{run, skipped}`: items the library holds, items a Get under way is already looking for, and items Wikidata has no work for are skipped with their reason (`held`, `being_got`, `not_found`), never refused; when every item is skipped `run` is null. At most 50 items, because each is a Wikidata lookup inside the request. Refused with no registry or no image source. **Optional `theme_id`** (added 2026-10-02, `build-plan-topics-and-destinations.md` Chunk 01): the theme the accepted works join instead of the default. The binding asks Programming for the theme and then starts the Get, two calls with no branch, so an unknown id is the theme's not-found refusal and nothing starts; a new theme is the client's earlier `POST /api/themes`. The run carries it back as `destination_theme_id` (null for the default) on every run shape, here and in MCP. Twin: `art_discovery(action='get', qids=[...], theme_id=...)`. Records `initiated_by: web_ui`. |
| `GET /api/works/{id}` gains `acquisition` | Where the work stands in the acquisition queue — `phase` (`queued`, `fetching`, `failed`, `gave_up`, `paused`), `failures`, `detail`, `next_try_at`, `since`, `condition`, `remedy` — or null when the queue owes it nothing (added 2026-10-02, Chunk 02). `art_catalogue(action='get')` carries the same object. |
| `POST /api/works/{id}/acquisition/retry` | Forget the work's failures and put it first in the acquisition queue; fetches nothing in the request. Returns the work's new state. Refused for an archived work, or one with no source (added 2026-10-02, Chunk 02). |
| `GET /api/acquisitions` | Activity › Queue's images: `pause` (`condition`, `detail`, `since`, `remedy`) or null, then every work owed, `{title, acquisition}`, in the order the queue tries them (added 2026-10-02, Chunk 02). Uncapped: it is bounded by the accepted works that hold no image, which the queue drains. |

**The review listing does not inline its pictures, and the MCP twin does.** Both
call the same service method; the browser passes `pictures=False` and fetches each
picture by URL. Inlining base64 for a caller that discards it costs a re-encode
per instance — roughly half of what a page of the grid costs on a Pi — and the
two readers have unrelated budgets: a model pays for a picture in context tokens
and a curator pays in pixels on a screen. They share the decode and the media type
and nothing else.

**`GET /api/runs/{id}` answers immediately; the MCP `status` action holds for up
to 45 seconds.** This is a deliberate divergence between the two surfaces rather
than an oversight. A model calls `status` once and waits, so holding is what
keeps it from spinning; a browser is already an event loop and polls on a timer.
Because these handlers are synchronous, a held request occupies one of
Starlette's worker threads for the whole hold — with a few tabs open that starves
the same pool serving thumbnails. The client polls every two seconds and stops
when the run reports `is_terminal`.

**`is_terminal` is on the wire rather than derived by the client** from a list of
finished status names. That list is the part that goes stale: a tenth status
would leave a browser either polling a finished run forever or abandoning a live
one, and neither failure announces itself.

**The two surfaces compose their own prose and share their arithmetic.** The MCP
notice is written for a model — it names fields in backticks and says to call
`status` again — and neither sentence suits a page with buttons on it. What must
not be written twice is the *figures*, and they are not: every count on both
surfaces is a property of `RunView`, computed once. That is the defect this
splits to avoid, and it is not hypothetical — a run-level figure computed as
`len(works)` beside a view that counted provenance apart is what reached a
review on the chunk before this one.

**A resolution rate is stated over what the model proposed, never over the
total,** on this surface as on the MCP one. Works a wired collection offered
arrived carrying their own images, so counting them in the numerator reports a
retrieval rate the run never achieved.

**One error shape, one status.** Every refusal is `400` with `{"error": "..."}`.
The service layer raises a single exception type by design, so a per-error status
table here would be this surface inventing a taxonomy the layer below it does not
have — and the message is already written to be shown to whoever asked.

### The routes the interface design requires — designed 2026-08-11, none built

**Every route in this section is a design. None of it exists.** The three tables
above are inventories of running code; this one is not, and the difference is the
only thing a reader must not miss. It is set apart under its own heading for that
reason rather than appended to them.

This discharges the debt `information-architecture.md` § Status recorded against
this artifact. The IA designs a curation surface over operations the HTTP API does
not have, and the paragraph that used to sit here called several of them
"deliberately absent" — which, once the IA was approved, was a document telling
the next builder that a decision had been made against work that had in fact been
decided *for*.

> **The precedent that sets this section's rules is in this file.**
> `art_display(show_now|next)` was specified before the manifest-only channel was
> ratified, and was unimplementable as written the day the norm landed — corrected
> 2026-07-20 under Critic R-17. So each row below names the entity or service
> concept it stands on, and **a route standing on something unbuilt says so**. The
> failure being avoided is not a wrong route; it is a route that reads as settled
> and cannot be built.

**Method follows the surface's own convention rather than REST orthodoxy:** the
built routes write with `POST` and remove with `DELETE`, and there is no `PATCH`
anywhere. Renaming a theme is therefore `POST`, not `PATCH` — one surface with two
spellings for "change this" costs more than the orthodoxy is worth here.

| Route | What it is | Stands on | MCP twin |
|---|---|---|---|
| `GET /api/works` — extended | Gains `q` for text search and one repeatable filter per facet `kind`. Additive to a built route. **Built 2026-08-12** — see below for the parameter shapes. | `WorkFacet`, built | `art_catalogue(action='list')` takes the same filters |
| `GET /api/works` — facet counts in the same response | The counts the IA's disabled-not-hidden rule needs. **Not a second route** — see below. **Built 2026-08-12**, with the latency measured. | `WorkFacet`, built | as above |
| `POST /api/works/{id}/archive`, `/restore` | Take a work out of circulation, and put it back. **Not a delete** — see below. **Built 2026-08-12**; both read back the full `WorkDetailOut` dossier, because the screen that archives is the screen that shows the work and a slimmer body would only send it straight back for the rest. | `Artwork.status`, built | `art_catalogue(action='archive'\|'restore')`, already designed |
| `POST /api/themes/{id}` | Rename. **Built 2026-08-12**; answers with `ThemeOut`, so the screen repaints the name the service *normalised* rather than the one it typed. Its body carries a name and **nothing else** — see below. | `Theme`, built | `art_theme(action='update')`, already designed |
| `GET /api/artists`, `GET /api/artists/{id}`, `GET /api/artists/{id}/registry` | Library › Artists and the Artist page (ruling 4). The index lists every artist with a work in circulation, by surname (the stored family name, else the last word once a generational suffix is set aside; `surname_key`), with `held` (how many) and `pictured_artwork_id`, their first accepted work in circulation, whose thumbnail the Artists index pictures them by (added 2026-10-02, #173; null only on `/{id}` for an artist with nothing in circulation); `?q=` narrows names, ignoring case and accents, for the top-bar search's Artists group. `/{id}` is the library half and always answers for a held artist. `/registry` is Wikidata's half, asked separately so it delays nothing: always a 200 for a held artist, with `state` `known` \| `no_identity` \| `not_configured` \| `unavailable` and a `note` sentence for every state but `known`; `works` are the 50 most renowned (by sitelinks) plus every work the library holds of theirs, with `works_total` beside them, each with `held_artwork_ids`, the works in circulation that are it **by QID** (several where held works share a QID, a duplicate shown rather than hidden) and `image` only ever a Commons file URL; `holdings` the 10 largest collections; `name`, `born` and `died` are the registry's (added 2026-10-01), and `artist_id` is always null here. Kept per artist for a week, across restarts (`kept-answers.sqlite`, since 2026-10-02); a failure is not kept. Every registry string is untrusted text. **Built 2026-10-01.** **`candidates`, added 2026-10-06**: in state `no_identity`, who Wikidata's name search (the matcher's `people_named`) says the artist might be, each `qid`, `name`, `born`, `died` and `years_agree` (the matcher's year test), those agreeing first, at most 5, leaving out any item another library artist carries; empty when the curator said there is none (the `note` says so, and nothing is asked), when no registry is configured, or when Wikidata could not be asked (the `note` says so). Proposed, never stored: `POST /api/artists/{id}/wikidata` stores the one chosen. The name search is kept per name for a week (`registry.people`); a failure is not. Additive. | `Artist`, registry identity | none: the page is the browser's, and an agent has `art_catalogue(action='list', artist_id=…)` for the held half |
| `GET /api/registry/artists/{qid}`, `GET /api/registry/works/{qid}` | The pages of an artist and a work reached by QID, which the library may not hold (ruling 2). A malformed QID is a 400 naming it; otherwise always a 200. `/registry/artists/{qid}` is the artist `/registry` shape with the same states except `no_identity`, plus `held`: when the library holds an artist with that QID, `artist_id` names them, the page goes there instead, and Wikidata is not asked. With state `known` it also carries **`unlinked`** (added 2026-10-06): the library's artists whose name, accents and case folded, is the registry's for this item, who carry no QID and of whom the curator has not said there is none, each `artist_id`, `name`, `born`, `died`, so the page can offer to link them; `candidates` is always empty here. `/registry/works/{qid}` has `state` `known` \| `not_found` (Wikidata has no such item) \| `not_configured` \| `unavailable` and a `note` for every state but `known`; `title`, `year`, `sitelinks`, `image` (a Commons file URL or null), `creators` (each with the library's `artist_id` where held), `media`, and `holders` (each with the collection's own `inventory` number where Wikidata pairs one with it); `height_cm` and `width_cm`, the work's own size, each null unless Wikidata's best-ranked measurements not of a frame or mount give exactly one value (**added 2026-10-05**); `image_width` and `image_height`, the picture's pixels as Commons holds the file, and `fit`, the `FitOut` the review grid gives a scan, judged against this deployment's box, all three null with no picture, a non-raster file, or Commons not answering (**added 2026-10-05**, kept per file for a week; a failure is not); `held_artwork_ids` is the library's works in circulation with that QID, filled whatever the registry did, and a non-empty one sends the page to the library's own work. A known work is kept per QID for a week, across restarts; a missing item and a failure are not. Every registry string is untrusted text. **Built 2026-10-01.** | Registry identity | none: the pages are the browser's, as the Artist page's registry half is |
| `GET /api/registry/works/{qid}/look`, `GET /api/registry/works/{qid}/look/pictures/{key}?size=card\|large` | **A look**: what every image source holds of a work the library does not, asked before any Get (`build-plan-look-before-get.md`, the owner's request of 2026-10-06). `/look` starts the asking or joins it and answers at once: `{qid, state, note, held_artwork_ids, sources, pictures}`. `state` is `asking` (the page polls) \| `answered`, or why nothing is asked: `held` (with `held_artwork_ids`; the page goes to the library's own), `being_got` (a Get is asking already), `no_sources`, `not_configured`, `not_found`, `unavailable`, each with a `note`. `sources` has one row per image source, `{provider, state, found, refusals, answered_at, retry_at}` (`refusals` names why phase 2's judge turned finds away: `not_held`, `identity_refused`, `size_unknown`; the Work page words a source whose only finds were `size_unknown` as holding the work without giving its size), `state` `asking` \| `found` \| `holds_none` \| `refused` (it holds a work by this title, or on the item's page, by another artist; not shown) \| `unreachable` (asked again at `retry_at`) \| `cannot`; a finder of pages only is not asked. `pictures` are every source's finds, best first by phase 2's own order, each `{key, provider, url, title, artist, width, height, fit, below_floor, confidence, rights_status, selection_rationale}`. `note` says "No image source holds a picture of this work now." once every source answered with none, or "No image source that answered holds a picture of this work now." when one could not be asked. Every configured source has a row, answered or `asking`, so a look never reads as finished while one has not answered; a source whose asking thread stopped or never started reads `unreachable`. A source that found nothing while Wikidata could not be asked which pages describe the work, or its creators' names, is kept 10 min, as an outage is, and every new fan-out builds its question and Wikidata link afresh. **Asked and judged as a Get asks and judges** (the same query builders, `ImageSourcePool.ask`, `PhaseTwoEngine.judge` and `rank`); **writes nothing to the catalogue**. Kept in memory per work and source: an answer for 6 h, "holds nothing" and "can't look this up" included; "could not be asked" for 10 min, never as holding nothing; at most 256 works. One look at a time asks each source; a queued ask for a work nobody has polled for 20 s is dropped before it starts; a run using a source goes first. `/pictures/{key}` is a picture from the picture store, fetched into it on first ask: `key` is the store's key, computed on the server from the source's answer, and valid only while this work's kept look names it; any other key is a **404** ("Look again"), and a named key whose picture could not be kept is a 400. A refused find has no key. `immutable`, as a candidate preview is. A malformed QID is a 400. Every source string is untrusted text. **Built 2026-10-06.** | Image sources, phase 2, the picture store | `art_discovery(action='look', qid=…)`, the same fields, plus each picture's `image_block_index`: the best six travel as image blocks. **The one registry page with a twin**, because a look answers a question an agent asks before a Get ("what would I get?"), where the rest of the registry pages are the browser's layout of facts an agent reaches otherwise. It holds up to `LOOK_HOLD_SECONDS` (30 s) until no source is still asking, then sends the pictures the store keeps and fetches the rest together, the whole call within `MODEL_LOOK_BUDGET_SECONDS` (40 s) of the client's 60; a picture not arrived by then is listed with a null `image_block_index` and said in `notice` to come with the next call, since its fetch goes on into the store. The notice is the look's own: it says why a picture did not come (not arrived in time, or nothing keepable). A picture's `width`, `height`, `fit` and `selection_rationale` are the browser's names; the action's tips map them onto `list_images`' |
| `GET /api/registry/search?q=&prefix=&wide=` | The registry's half of the top-bar search and of the results page (ruling 2). `q` is cut into words, and nothing but words reaches the registry, so search syntax typed by a curator is dropped; `prefix=true` reads the last word as the start of one. `state` is `known` \| `too_short` (under three letters: nothing asked) \| `not_configured` \| `unavailable`, with a `note` for the last two. `wide=true` returns the results page's longer lists (up to 10 artists and 20 works) and is kept apart. `artists` (up to 3, from Wikidata's name search: `qid`, `name`, `born`, `died`, and the library's `artist_id` where held) and `works` (up to 5 works of visual art, by sitelinks: `qid`, `title`, `sitelinks`, `image` only ever a Commons file URL, `creator` with its library `artist_id`, and `held_artwork_ids`). Kept per folded query, `prefix` and `wide` for a week, across restarts; a failure is not. Every registry string is untrusted text. **Built 2026-10-01.** | Registry identity | none: the typeahead is the browser's, as the Artist page's registry half is |
| `GET /api/registry/artists/{qid}/similar` | *Similar artists* on the Artist page, held or not (ruling 4). Up to 12 visual artists sharing a movement (`P135`), by sitelinks, each with `qid`, `name`, `born`, `died`, `images` (their works with a free image, so a curator sees who cannot be supplied) and the library's `artist_id` where held. `state` `known` \| `not_configured` \| `unavailable`, with a `note` for the last two. A malformed QID is a 400. Kept per artist for a week, across restarts; a failure is not. Every registry string is untrusted text. **Built 2026-10-01.** | Registry identity | none: the page is the browser's, as its registry half is |
| `GET /api/topics`, `GET /api/topics/{qid}` | Library › Topics and the library's half of a Topic page (`build-plan-topics-and-destinations.md` Chunk 04), **read from the facet rows alone, so neither waits on Wikidata**. `/api/topics` is `{state, note, kinds: [{kind, topics: [{qid, label, works}]}]}`: one group per kind, always all four in the order `period`, `movement`, `subject`, `medium`, each topic by label with `works` the library's works in circulation carrying it. `/api/topics/{qid}` is `{state, note, qid, label, kinds, works}`: `label` and `kinds` are what the library's works carry the topic as (null and empty for a topic none is in, which is not an error: a Topic page reached by search is ordinary), and `works` are those works in circulation as grid cards (`WorkOut`), by title. `state` is `known`, or `not_configured` with a `note` saying topics need `WIKIDATA_USER_AGENT`, when the rows are whatever an earlier configuration recorded. A malformed QID is a 400. Labels are registry text. Each facet on `GET /api/works/{id}` gains `value_qid`, the Topic page it opens or null, an added field. **Built 2026-10-02.** | `WorkFacet.value_qid` (`data-model.md` Q25-Q28) | `art_catalogue(action='topics')`, the same fields; `art_catalogue(action='topic', qid=…)`, the same fields with `works` as the tool's work summaries |
| `GET /api/topics/{qid}/registry`, `GET /api/topics/{qid}/works`, `GET /api/topics/{qid}/artists` | The registry's half of a Topic page, each asked separately after the page draws, as the Artist page's `/registry` and *Similar artists* are: a period's works took 7 to 26 seconds (`wikidata-findings.md` § Topics). `/registry` is the head, `{state, note, qid, label, kinds, description, start, end}` (`kinds` every kind Wikidata's classes give it, the one its works are found by first; `start`/`end` a period's years). `/works` is *Representative works*, `{state, note, works: [{qid, title, sitelinks, year, image, creators: [{qid, name, artist_id}], creator_unknown, state, held_artwork_ids}]}`: up to 50 by sitelinks, `state` `held` (the library holds it in circulation, **matched by QID**, with `held_artwork_ids`), `image_found` or `no_image`; `image` only ever a Commons file URL; `creator_unknown` a maker recorded as unknown. `/artists` is `{state, note, artists: [...]}`, up to 12, each as *Similar artists* lists one. Section `state` is `known` \| `not_found` \| `not_configured` \| `unavailable`, with a `note` for every state but `known`. Always a 200 for a well-formed QID; a malformed one is a 400. `/works` and `/artists` wait up to Wikidata's own 60 s, since a named period's took 26-60 s; the head keeps the pages' 20 s. Kept per topic for a week, across restarts (`kept-answers.sqlite`); a missing item and a failure are not; *Held* is read fresh. Every registry string is untrusted text. **Built 2026-10-02.** | `TopicService` (Chunk 03) | none: the sections are the browser's, as the Artist page's registry half is |
| `GET /api/registry/topics?q=` | Topics Wikidata's own search finds for a typed name, filtered to the four kinds, for Library › Topics' search and the top bar's Topics group: `{state, note, topics: [{qid, label, kinds, description, start, end}]}`, `state` `known` \| `not_configured` \| `unavailable`. An empty `q` asks nothing. Kept for a week by the text typed, ignoring case, across restarts; a failure is not. **Built 2026-10-02.** | `TopicService.named` (Chunk 03) | none, as `/api/registry/search` has none |
| `GET /api/works?artist_id=` | One artist's works, by the work's own link to its artist rather than by the `artist` facet, which a catalogue may not carry (the owner's held no facet rows on 2026-10-01, and the topic sweep writes none of kind `artist`). Narrows the page, the total and every facet count alike. **Built 2026-10-01.** | `Artwork.artist_id` | `art_catalogue(action='list', artist_id=…)`, an added optional parameter |
| `wanted` on registry works | Every answer that lists registry works with `held_artwork_ids` — `GET /api/registry/search` (`works`), `GET /api/registry/works/{qid}`, `GET /api/registry/artists/{qid}` and `/api/artists/{id}/registry` (`works`), and `GET /api/topics/{qid}/works` — also carries `wanted`: true when a wanted work (Wanted) is matched to that item. Reported beside `held_artwork_ids`, and beside the Topic works' `state` rather than as a fourth value of it, so a reader branching on `held` / `image_found` / `no_image` is unchanged; the page decides that held wins. Read fresh on every request, as *Held* is. Additive. **Built 2026-10-02** (`build-plan-library-screens.md` Chunk 03, #172). | `CandidateWork.wikidata_qid` with verdict `wanted` | none: these pages are the browser's |
| `GET /api/works?theme=` | One theme's works, filtered and counted like the rest of the catalogue: Artworks' *Filter* rail offers a theme beside the facets (the owner's ruling on #169, Radarr's filters). Narrows the page, the total and every facet count, and composes with `q`, every facet and `sort`. The binding composes two calls, as `GET /api/themes/{id}` does: Programming names the theme's work ids, and the Library lists within them as opaque ids, so it learns nothing about themes (`architecture.md` seam rule 1). An unknown theme is the surface's one refusal (400, naming it) rather than ignored, since ignoring it would answer with the whole catalogue labelled as the theme's; an empty theme is an empty page. **Built 2026-10-02.** **Every page also carries `themes`** (Chunk 02 of the Library screens plan): every theme by name as a filter option, `{theme_id, name, count, selected, disabled}`, its count the works it would select given every other filter but the theme, as a facet's count ignores its own kind, and `disabled` at zero unless selected. Two calls again, one per plane: the Library's `matching_ids` names what the other filters select, and Programming's `theme_counts` counts each theme's members among them. `art_catalogue(action='list')` carries the same list. | `ThemeMembership` (Programming), `Artwork` | `art_catalogue(action='list', theme=…)`, an added optional parameter |
| `POST /api/works/{id}/wikidata`, `POST /api/artists/{id}/wikidata` | The curator's word on which Wikidata item a work or artist is: body `{"qid": "Q160149"}`, or `{"qid": null}` for "there is none". A QID is trimmed and upper-cased; anything else (a URL included) is refused naming the shape. Since 2026-10-01 two more refusals, on both surfaces: an artist's QID another catalogue artist already carries (naming that artist), and, when a registry is configured, a QID Wikidata has no item for, or one it could not be asked about. With no registry configured, a well-formed QID is stored unchecked. The work route answers with the dossier, the artist route with `ArtistOut`. `WorkOut` and `ArtistOut` gain `wikidata_qid` and `wikidata_qid_set_by` (`matched` \| `curator` \| null), added fields. **Built 2026-10-01**; the Artist and Work pages call them from a control that looks a new item up first (`build-plan-one-world-search.md` Chunk 05). | `Artwork`/`Artist` registry identity (`data-model.md`) | `art_catalogue(action='set_work_qid'\|'set_artist_qid')`, new actions, where `qid='none'` says there is none; both fields added to every work and artist the tools return |
| `POST /api/themes/{id}/default` | Make this the theme newly accepted works join, taking the mark off whichever had it (`data-model.md` § Theme, `is_default`). Answers with `ThemeListOut`, because the act changes two themes. `ThemeOut` gains `is_default`, an added field. **Built 2026-10-01.** | `Theme.is_default`, `DefaultThemeOffer` | `art_theme(action='make_default')`, a new action; `is_default` added to every theme the tool returns |
| `DELETE /api/themes/{id}` | Delete. **The refusal it must reuse is already built** — see below. **Built 2026-08-12**; answers with `ThemeListOut`, the themes that remain, so the list repaints from the response like every other membership act. | `Theme`, built, and `DisplayService.delete_theme`'s guard with it | `art_theme(action='delete')`, built and wired to that guard |
| `GET`/`POST /api/conversations` | The thread list, ordered by `last_turn_at`; and starting one. **Built 2026-08-12.** | `Conversation`, built | none proposed — see below |
| `GET /api/conversations/{id}` | One thread with its turns. **Built 2026-08-12.** | `ConversationTurn`, built | none proposed |
| `POST /api/conversations/{id}/turns` | One exchange. **Spends** — `SpendRecord` category `conversation_tokens`. **Built 2026-08-12**; a retry sends no new text, so the transcript is the idempotency key and asking again spends nothing twice. | `ConversationTurn`, built | none proposed |
| `POST /api/conversations/{id}/commit` | Commit a direction: starts a `DiscoveryRun` and sets the turn's `committed_run_id`. **Built 2026-08-12.** | `ConversationTurn`, built | none proposed |
| `DELETE /api/conversations/{id}` | Deletes the thread and its turns. **Detaches rather than cascades** — see below. **Built 2026-08-12.** The detach is a loop over the citing rows rather than a schema rule, so its atomicity rests on the transaction it runs in and on reading the code — it is the one behaviour in this chunk no mutation could express. | `ConversationTurn`, built | none proposed |
| `GET`/`POST /api/affinities`, `DELETE /api/affinities/{id}` | The Taste screen, and every sample reaction in a conversation. **Built 2026-08-12**; `POST` upserts on (`kind`, `value`) and refuses to overwrite a stronger provenance with a weaker one. | `Affinity`, built | `art_taste(action='list'\|'set'\|'delete')`, built — see below and § `art_taste` |
| `POST /api/works/{id}/mat` | Re-derive a work's mat. **Owned by issue #91, not by this set** — see below. | `MatColor`, built | `art_catalogue(action='set_mat_color')`, built |
| `POST /api/directives` | The Walls screen's `next`. **Shape settled and built 2026-08-12** — see below. | `Directive`, built | `art_display(action='next')`, built |
| `GET /api/spend` | The Health screen's spend history, across runs. | `SpendRecord`, built | `art_discovery(action='spend')` already answers the cross-run question by calendar month — see below |

**Facet counts ride on the works response rather than getting a route.** They are
an answer to the same question the grid answers — *what does this filter set
select?* — and two routes would give a curator two answers to it, which is the
defect shape this codebase has already shipped once and argues against in the
review view's own source. The cost is that counts are recomputed on page 2 of a
grid that did not change them. That is accepted rather than optimised away, on a
loopback service serving one household; **revisit trigger:** the recompute shows
up in the collection's response time on the real thousands-scale corpus.

**How the filters are carried, and what comes back.** `q` is free text, split on
whitespace, and every word must appear somewhere in the work's title, description,
commentary, medium or date, or in its artist's name; a second word narrows rather
than widens. **Case, accents and ligatures are ignored on both sides**, so `dali`
finds Dalí, `strasse` finds Straße, `hammershoi` finds Hammershøi, and a name a
source stored decomposed matches the one a keyboard types (`search_fold` in
`arrt/src/arrt/persistence/folding.py`; built 2026-10-01). At most eight words are accepted (more is refused, because dropping the
surplus would silently *broaden* the answer). Each facet kind is its own repeatable
parameter named for the kind — `?movement=Baroque&movement=Rococo&era=17th+c.` —
repeated rather than comma-joined, because a facet value may contain a comma and a
separator the data can hold is a parser that goes wrong on the data. **Values
within one kind mean *either*; two kinds mean *both*.** The response carries a
`facets` array of one group per kind, always all six and always in vocabulary
order, each with its `options` (`value`, `count`, `selected`, `disabled`),
`total_values` and `truncated`. Options are ordered commonest first and capped at
fifty per kind — an `artist` rail on a thousands-work catalogue is a scroll rather
than a choice — with any *selected* value kept whatever its count, since the
control that removes a filter is the option itself. `art_catalogue(action='list')`
takes the same six arrays and `q`, and returns the same groups.

> **Measured 2026-08-12 on the 4,000-work corpus, and the FTS5 question is
> settled: `LIKE`, and no full-text index.** Run
> `cd arrt && uv run python tools/search_latency.py` to reproduce; figures are
> medians of 50 runs on an Apple-silicon laptop, and the tool prints p95 and worst
> beside them.
>
> | | median |
> |---|---|
> | The whole response, unfiltered first page | **5.9 ms** |
> | The whole response, one facet chosen | **17.9 ms** |
> | The whole response, a search term | **24–33 ms** |
> | The `LIKE` clause on its own | **1.0–1.7 ms** |
> | The same term through an FTS5 index | **0.01–0.19 ms** |
>
> **FTS5 is genuinely two orders of magnitude faster and is still the wrong
> answer, for two reasons and only the second is about speed.** It matches whole
> tokens, so a search for `harb` finds nothing at all where `LIKE '%harb%'` finds
> "harbour" — the contains-match a search box is expected to do would have to be
> taught to the curator as a prefix operator, or given up. And the clause is not
> where the time goes: 1.5 ms of a 30 ms answer. Replacing it would buy about 5%
> of the response for a second copy of every searched column, kept in step by
> triggers, on a file whose whole appeal is that it can be copied to a backup and
> back. *(The measurement is the number; this paragraph's account of where the
> time goes is inference from the per-part timings in the same tool run.)*
>
> **The revisit trigger above fired, and was answered by fixing the query rather
> than by dropping the counts.** Recomputing them cost 57 ms unfiltered and 101 ms
> with a search term — on a laptop, so several times that on the Pi this is
> deployed to. Two changes took it to the table above: a facet count no longer
> restricts itself to a set of works when nothing narrows that set (the collection's
> *first* screen is exactly that case), and the kinds the curator has not filtered
> on are counted in one statement instead of five, which is not an exception to the
> exclusion rule but a consequence of it — dropping a kind's own selection leaves
> the same query for every kind that has none. **Counts still ride on the works
> response.** The trigger now reads: revisit if the recompute shows up again on the
> real corpus, measured with the tool above rather than estimated.
>
> **Re-measured 2026-10-01 when search began ignoring accents**, same tool, same
> laptop. Folding runs in Python, once per work per evaluation of the clause, and
> remembers what it folded. A search response went from **26–35 ms** to
> **44–66 ms** median; the clause alone from **0.9–1.6 ms** to **5.3–6.0 ms**
> (the tool's *LIKE, folded* rows). **These time the fast path only**: the
> synthetic corpus's text is all ASCII (0 of 4,000 works otherwise), and half the
> owner's 40 works are not. Text shaped like theirs was measured separately, in
> `_FOLDS_REMEMBERED`'s comment (`arrt/src/arrt/persistence/folding.py`). Unfiltered and facet-only responses are
> unchanged, since they run no text clause. The FTS5 answer stands on its first
> reason, which the fold does not touch: a contains-match is not a token match.
> Note for whoever next revisits it: FTS5's `unicode61` tokenizer removes
> diacritics itself, so an index would fold for free; the cost is still the
> prefix-only match.

**Three built routes gain a wall, and this is the only change in this section to
something that already ships.** The operator ruled on 2026-08-12 that themes are
created globally and assigned per wall (`data-model.md` § ThemeAssignment), which
makes three of the routes above singular where the product is not:

| Route | Today | Becomes |
|---|---|---|
| `POST /api/themes/{id}/activate` | Changes *the* wall | Names which wall it hangs on. The wall is a required part of the request, **even while there is one and the answer is obvious** — the IA's rule that every act naming a wall keeps a confirmation from silently becoming wrong. |
| `GET /api/manifest` | What a theme would put on *the* wall | Takes the wall as well as the theme: exclusions are per-wall once two walls can hang different themes, and this route's whole job is to state a consequence before it happens. |
| `POST /api/directives` (built above) | An advance | Names the wall. `Directive` stops being a singleton and becomes one row per wall, so a `next` in the living room does not step the study. |

**`art_theme(action='activate')` and `art_display` take the same parameter**, by
the parity requirement in `product-brief.md` item 8 — a model that can hang a
theme must be able to say where, and an action that guesses the wall is worse on
the tool surface than on the web one, because there is no confirmation dialog to
catch it.

**Built 2026-08-12**, and the one-wall installation is the degenerate case
throughout: one wall, one assignment, identical behaviour. **The inter-plane half
landed the same day** — `architecture.md` § One manifest per wall: one
`theme-manifest-{wall_id}.json` and one `display-heartbeat-{wall_id}.json` per
wall, with the display plane taking `WALL_ID` from its environment as it takes
`TV_ADDRESS`. No route carries a manifest's *bytes*, so nothing in the table above
changed shape for it; `GET /api/health` did, and its new shape is below.

### `GET /api/health` aggregates across walls — built 2026-08-12

The heartbeat became one file per wall, so "has the display plane reported"
stopped being a question with one answer and became "which wall has not". The
response is:

```json
{
  "walls": [
    {
      "wall_id": "…",
      "wall_name": "The living room",
      "heartbeat": {
        "path": "/srv/art/display-heartbeat-….json",
        "reported_at": "2026-08-12T09:14:02+00:00",
        "age_seconds": 41.2,
        "absent": false,
        "problem": null,
        "description": "The display plane last reported 41 seconds ago.",
        "reported": { "…": "whatever that plane wrote, passed through" }
      }
    }
  ],
  "description": "Every wall has reported; the least recent is 'The study', 4 minutes ago.",
  "backup": { "…": "unchanged" },
  "artwork_box": { "…": "unchanged" },
  "sources": [
    {
      "name": "artic",
      "state": "loaded",
      "reason": null,
      "faults": 0,
      "last_fault_at": null,
      "last_fault_age_seconds": null,
      "last_fault": null,
      "description": "artic is loaded, with no faults since startup.",
      "distribution": "arrt",
      "version": "0.3.0",
      "api_major": 1,
      "provides": ["finds_images", "reads", "browses"]
    }
  ],
  "pictures": {
    "pictures_bytes": 52428800,
    "pictures_files": 600,
    "age_seconds": 212.0,
    "unreadable": 0,
    "description": "The picture store keeps 600 files, 52.4 MB, counted 212 seconds ago. Each picture is two files, one per size kept."
  }
}
```

**`pictures`** *(added 2026-10-06, `build-plan-picture-store.md` Chunk 02)* is the
picture store's size: every tier file under `ART_ROOT/pictures/` and their bytes,
from a walk reused for ten minutes, with the walk's age. It has no ceiling (owner,
2026-10-06), so this is a figure to watch, never a verdict. `unreadable` counts
directories and files the walk could not read: not zero is this machine's disk
refusing the store, the count is short by what they hold, and `description` says
so in place of "no pictures yet". `art_display(action='status')` carries the same
object under the same names and values, built from the same single reading
(`test_surface_parity.py`).

**`sources`** *(added 2026-10-03, `source-plugins.md` § Loading)* lists every
installed plugin, most preferred first, and is empty when none is installed.
`state` is `loaded`, `declined` (installed and not configured here) or `failed`
(installed and could not be loaded), carried as itself. `reason` and `last_fault`
are scrubbed of query strings (`security-model.md` § Source plugins).
*Added 2026-10-06:* `distribution` and `version` are the installed package that
registers the plugin, read from its metadata before the plugin's code runs (null
for one registered by hand, or a name two packages register); `api_major` is the
interface major the plugin was written for (null when it failed before saying);
`provides` is what its parts provide, `finds_images`, `finds_pages`, `reads` and
`browses`, and is empty for a plugin that did not load.

**`heartbeat` is gone from the top level and is not coming back**: one reading for
an installation with two rooms is a reading that cannot name the room, which is
the entire reason the file was split. `walls` is ordered as `GET /api/walls`
orders them, so no surface has to hold two orderings.

**`description` is a summary of the readings beside it, not a fourth signal.** It
names the walls that have not reported — `"'The study' has not reported. …"` — or,
when all of them have, states the *least recent* age, because a sentence quoting
the freshest would read as an all-clear bought from whichever wall reported last.
It applies **no threshold and uses no verdict word**: whether four minutes is late
depends on whether that television was switched off on purpose, which this plane
does not know. A client must not derive a colour from it.

**The per-wall `heartbeat` object is byte-for-byte the shape the top-level one
had**, including `reported` being passed through unread — exactly one key
(`reported_at`) is contract, and inventing more on the reading side would be a
second contract the writer never agreed to.

`art_display(action='status')` mirrors this on the tool surface: it takes no wall,
returns `walls[]` with `count`, and states the same `observation` sentence from the
same readings.

**How the wall is actually carried, since the table above says only that it is.**
`POST /api/themes/{id}/activate` takes `{"wall_id": …}` as a request **body**;
`GET /api/manifest` takes `wall_id` as a **required query parameter**, having no body
to put it in. Stated because the two differ and a reader of the table above would have
no way to tell which was which. `GET /api/manifest` also echoes `wall_id` and
`wall_name` back, so a caller stating a consequence can name the room in words rather
than in a UUID.

**Four routes and three tool actions arrived with them**, none of which this section
had designed:

| Route | Tool | What it is for |
|---|---|---|
| `POST /api/walls` | `art_display(action='add_wall')` | Nothing else creates a wall. The migration makes the first one; a second room needs an operation. **Create only** — no delete and no rename, because deleting a wall raises consequences for its assignment, its directive row and any display configured to serve it that nothing has ruled on. |
| `GET /api/walls` | `art_display(action='walls')` | What rooms exist, and what hangs in each. |
| `DELETE /api/walls/{wall_id}/theme` | `art_theme(action='unhang')` | Takes the picture down. See § Deleting a theme for why this had to exist before the delete refusal could be made absolute. |
| — | — | `GET /api/themes` reshaped to `{theme, hanging_on[]}` per entry, because `ThemeOut.is_active` had nothing to become: "is it active" is now "which walls is it on". The MCP listing stays flat with a `hanging_on` key added, since a model reads a list better than a nesting. |

**`art_display(action='status')` still takes no wall, and the reason changed
underneath it on 2026-08-12.** § `art_display` above once said a wall parameter
would be a lie while the heartbeat was one file, and that the action would gain
one when the inter-plane chunk landed. That chunk landed and the heartbeat *is*
per wall now — so the old reason expired, and the action takes no wall anyway for
a new one: what it answers is "has every wall reported". It returns `walls[]`
with a count and one observation sentence, which is the aggregate question and
not a per-wall one, and a caller wanting one room reads the entry it wants out of
that list. See § `GET /api/health` aggregates across walls above, which this
paragraph must not be read as contradicting.

> **The reason above is now stated where the action is described, not only
> here.** It was written only here for a day, 1,150 lines below the table that
> still carried the expired claim — so the artifact contradicted itself in
> reading order and the first statement won. Recorded because the lesson is about
> placement rather than about heartbeats: a correction belongs at the claim.

**"Work delete" was the wrong word, and the route is archive.** The IA § Status
row asked for one; `data-model.md` gives `Artwork.status` exactly two values,
`accepted` and `archived`, with a state machine in which restoration is permitted.
A hard delete would have been this artifact inventing a destructive operation the
data model does not have — and it has downstream consequences a delete could not
carry. The IA row is corrected to match.

**Two of them, and the second is the one that reaches the room.** Archiving a
pinned work makes a directive unsatisfiable, which `data-model.md` already settles
by having `show_now` refuse an archived work. And archiving a work that is in the
**active** theme takes a picture off the wall: `architecture.md` records that
archive removes a work from the manifest and leaves it in the theme, with
`archived` the first of the five exclusion causes, and calls that silence
"precisely this product's characteristic failure". **So the confirmation names the
wall consequence, not merely which of archive and restore it is doing** —
`GET /api/manifest?theme_id=` already evaluates a theme's exclusions without
writing, so the route can state the consequence rather than predict it. The IA
carries this rule for flow 6's activation and now carries it here too.

**Deleting a theme that is hanging refuses — and this rule is built, not designed.** The
operator settled the question on 2026-08-11, and the answer turned out to be what
`DisplayService.delete_theme` had enforced all along, reached by
`art_theme(action='delete')`. It was generalised from "the active theme" to "hanging on
any wall" on 2026-08-12, when a theme stopped being active and started hanging somewhere. **This paragraph therefore describes shipped
behaviour**, and the HTTP route now shares it: `DELETE /api/themes/{id}` calls that
method and writes no guard of its own, which is what keeps one refusal sentence
reaching a curator and an agent alike.

**Deleting the default theme refuses too** *(built 2026-10-01)*, in the same method
and so on both surfaces: the refusal names the theme as the default and says to
make another theme the default first. Renaming it keeps the mark, because the mark
is written only by `make_default`, never by saving a theme.

**The rename body carries a name and nothing else, and that is a decision.**
`update_theme` distinguishes "leave this alone" from "clear this" with a sentinel, so
a request model whose other fields defaulted to `None` would reset a theme's rotation
pace every time somebody fixed a typo in its name — silently, and on the surface
least likely to be looking at pace. A route that can only rename cannot do that. The
day a screen genuinely edits pace, it earns a model that says so explicitly rather
than inheriting one that can.

**`position` is an index on both `add` and `POST .../position`, never a sort key —
settled 2026-08-12, and it was a defect until then.** The work lands *at* that place
and the works renumber densely around it. What it replaced wrote the number into the
column and stopped, which sounds equivalent and is not: `list_memberships` breaks a
tie on `added_at`, so a work sent from 0 to 1 landed level with the work already
there and sorted ahead of it again, being the older row. Moving a work **up** worked;
moving it **down** did nothing at all, and the Theme screen's ↓ button had never once
reordered anything. An index past the end lands at the end rather than refusing —
there is no wrong answer to "put this last" worth an error.

**Omitting it means the end on an add and unplaced on a reorder, and the asymmetry
is the point.** A curator returning a work to unplaced is saying they have no opinion
about where it goes, which is a thing worth being able to say; a curator adding a
work has no opinion to express yet, and the end is where a work nobody has placed
belongs. This is what makes the list a surface renders and the list the service
renumbers **one list**: nothing a curator or a tool can reach sends a position, so
when an add left the work unplaced, every theme the product could actually build had
a placed prefix the renumber walked and an unplaced tail the surface still indexed
against. Two lists indexed against each other is a reorder that does nothing, or one
that moves the work the way it was not asked to go.

> **The operator ruled this on 2026-08-12**, closing #132, after Critic review found
> the reorder shipped in this chunk still broken for every theme built through the
> screen that shipped with it. The alternatives were renumbering the full list on a
> move while leaving `add` alone — which reaches the same end state by drift, since
> the first move places everything — and having the Theme screen send an index,
> which fixes one screen and leaves the same defect reachable from a conversation.
>
> It changes what `test_q1_which_works_belong_to_a_theme…` sets up. The claim that
> test makes — `theme_works` returns the curated order — is unchanged and still
> asserted; the two adds that expressed an order by writing sort keys express the
> same order by index instead. A test is a contract here, and a ruling is how a
> contract changes.

> **The question was put to the operator as though nothing were built, and that
> framing was wrong** — found by Critic review, R-8, on the commit that recorded the
> decision. The ruling and the shipped behaviour agree on the case that was asked
> about, so nothing was decided against the code; but the case below was hidden by
> the same mistake and never reached them. Recorded rather than quietly corrected,
> because the correction is the interesting part: a decision framed against an
> artifact when the code was the authority.
>
> **The hidden case was then put to them separately and ratified** — see the
> last-theme paragraph below. It is a ruling now, not a builder's reading of a
> docstring, which matters because the two are worth different amounts to whoever
> next proposes changing it.

**The refusal is now absolute, and the exception that used to soften it is retired —
replaced rather than dropped.** `delete_theme` refuses a theme **hanging on any
wall**, and names the walls. Built 2026-08-12.

> **What this replaced, and why the replacement was owed.** Until then the refusal was
> narrower: it refused the active theme *only while another theme existed*, so the
> last theme was deletable even while hanging. That was **ratified by the operator on
> 2026-08-11** for a specific and good reason — refusing unconditionally would have
> made the last theme undeletable forever, because there was no way to take a theme
> down, so a curator could never empty the catalogue.
>
> Generalising the refusal to "hanging on any wall" reinstates exactly that deadlock,
> and with walls it gets worse rather than better: "the last theme" hanging in three
> rooms would be freely deletable and would blank three rooms at once. **So the
> operation the 2026-08-11 ruling was compensating for now exists** — see
> `art_theme(action='unhang')` below — and the exception is retired because the thing
> it worked around is gone. The ruling is honoured, not overturned: a curator can
> still empty the catalogue, by taking the theme down first.
>
> The gap was found mid-build, from this plan's own acceptance test saying the refusal
> "permits the last *unhung* theme" — a word that presupposed an operation nothing had
> built.

Deleting a theme deliberately does not rewrite the manifest: a wall keeps showing what
it was showing, the same posture as curation being stopped entirely. Publishing an
empty manifest would blank a wall as a side effect of tidying the catalogue.

**The message is normative and is already written.** "Theme *X* is hanging on *'Living
room', 'Study'*. Hang another theme there first, or take this one down, so that what
those walls show next is a choice rather than whatever was on them before."

It names the walls, because with more than one wall "the wall" identifies nothing, and
it offers **both** ways out. Hanging another theme there is a remedy in its own right
rather than a longer road to the same place: `wall_id` alone is the assignment's
primary key, so hanging something else *is* the unhanging. The remedy a refusal names
has to be an operation that exists and that the curator can reach — that is the whole
obligation § Errors teach places on it.

> **The message changed when the refusal did, 2026-08-12, and the old one is recorded
> because it was right for a shape that no longer exists.** It read: "Theme *X* is the
> one the wall is showing. Activate another theme first, so that what replaces it on
> the wall is a choice rather than whichever is oldest." Every clause of that has
> stopped being true. There is more than one wall now, so "the wall" does not
> identify anything. Activating another theme no longer resolves the refusal, because
> the theme has to leave *every* wall. And "whichever is oldest" described
> `reconcile()`'s promote-the-oldest behaviour, which was **removed in the same
> change** — along with `add_theme`'s activate-if-none-else-is, the same rule reached
> by a second route, which the plan had not noticed and which was equally
> indefensible once a wall had to be named.
>
> An earlier draft had also invented "or deactivate this one", refused at the time
> because no such action existed. **It does now** — `unhang` — which is worth noticing:
> the draft was not wrong about what a curator would want, only about what was built,
> and the honest fix was to build it rather than to keep steering people away from it.

> **"Promote another theme, then delete" was the third option, and the reason it was
> declined is now gone too.** `reconcile()` promoted the oldest remaining theme when
> none was active, so a curator deleting what was on the wall would get *some* other
> theme on it without having chosen one. That was the strongest argument for refusing.
> With promotion removed, deleting a hung theme would simply leave the wall hanging
> nothing — a named, designed empty state rather than an unbidden substitution. The
> refusal survives on the remaining reason, which is enough on its own: a wall that
> goes dark should do so because a curator took the picture down, not as a side effect
> of tidying the catalogue.

> **Both rules generalise once themes are assigned per wall, and neither survives
> translation unexamined.** "Refuses the active theme while another exists" becomes
> **refuses a theme hung on any wall** — a theme on two walls is two rooms that go
> dark, so the count that matters is assignments and not themes. And the
> reconcile-promotion this refusal was built to prevent is being **dropped**
> rather than made per-wall (`data-model.md` § ThemeAssignment), which removes the
> guard's original motivation while leaving the guard correct for a better reason:
> a curator deleting what is hanging should choose the replacement, and with the
> promotion gone the alternative is not a surprise theme but a blank wall. The
> archive confirmation's wall consequence generalises the same way — it names
> *which* walls lose the picture. Neither is built; both belong to the chunk that
> builds the assignment.

**Taste gets an MCP tool; conversation does not — settled by the operator
2026-08-11, and the three cases came apart under the ruling.** `product-brief.md`
item 8 states as a must-have that **every content-management operation is available
as an MCP tool, at parity with the web UI**, and `technical_decisions` records that
parity as the reason the thin-binding norm binds at all. The question these routes
raised was whether an `Affinity` is a content-management operation — it is a record
of taste, not of holdings.

**The ruling is that it is: `art_taste` is designed in § `art_taste` above.** It
was taken **against the recommendation recorded here**, which argued for deferring
until discovery began weighting `Affinity`, on the grounds that tool names are
**Frozen** — never renamed or removed — so adding is cheap and retiring is not,
which argues for deciding late. That reasoning is left standing rather than deleted,
because it is what the decision cost: a name was frozen over an entity that did not
yet exist, and had `Affinity` been reshaped before it was built, `art_taste` was the
part that could not be reshaped with it. **The window closed on 2026-08-12**, one
day later, when the entity and all three actions shipped together and nothing had
been reshaped — so the risk was real and it did not land, which is worth recording
as precisely that rather than as either vindication or a near miss. Set against
that, the deferral had its own cost — item
8's parity claim would have read as met while the surface knowingly withheld an
operation the web UI has, and a "revisit trigger" is a promise nothing enforces.

**Conversation keeps its deferral, and the ruling strengthens it rather than
weakening it.** The reasons were never the Frozen-tier argument: the in-UI agent
*is* an MCP client, so a model conducting a conversation would be reading its own
thread back through a tool; and the operation a model actually wants is the taste,
not the transcript. Granting the first while withholding the second is precisely
what that reasoning asked for. `DELETE /api/conversations/{id}` keeps its
deferral on the *tool* side for the same reasons; what it no longer lacks is a
shape.

**`DELETE /api/conversations/{id}` has one now — ruled by the operator 2026-08-12,
closing issue #118.** The rule and its reasoning live in `security-model.md`
§ Deleting a conversation, which is the authority; what this section owes is the
route's own obligations:

- **It deletes the thread and its turns, and detaches everything derived from
  them.** `Affinity.source_turn_id` and `SpendRecord.conversation_turn_id` are
  nulled. Nothing else is touched.
- **The response names what was detached**, because the confirmation has to state
  a consequence rather than a row count: how many affinities keep their judgment
  and lose their derivation, and that those can no longer be rebuilt when the
  derivation improves. The IA's rule for archive and for activation — a
  confirmation names the consequence in the curator's terms — binds here, and this
  is the one operation in the product that genuinely destroys a record.
- **It must not enforce `inferred ⇒ source_turn_id` as a stored constraint.** That
  rule, stated in § `art_taste` above, is an invariant on the write path only;
  built into the schema it makes this route impossible. This is the sentence a
  builder needs, and it is why the constraint's *site* is named rather than left
  to reading.

**Spend history needs no new tool, and its row no longer borrows taste's reasoning.**
Item 8 reaches content management, and a read of what was spent is not that under
any reading. It is also already answered: `art_discovery(action='spend')` reports a
run's cost or a whole calendar month's, across runs, by arity — the same
two-questions-by-arity shape § `estimate` describes. Whether the Health screen's
history wants more than a month at a time is the builder's question against a
service method that exists, not a sixth-tool question. *(That row read "same
deferral as taste" until 2026-08-11, which was two claims stapled together: one
died with this ruling and the other was never true, since the month report shipped
with `art_discovery`.)*

**Sample reactions write through `/api/affinities`, not through a conversation
route.** The IA's flow 1 gives each sample "more like this" / "not this" / "tell
me more", and each writes an `Affinity` with `derivation='stated'` and
`source_turn_id` set. That is the same operation the Taste screen performs when a
curator corrects one, so it is one service method with one route and two callers —
`architecture.md` § Direction reduced to its simplest case. A reaction route on
the conversation would have been a second way to write one entity.

**What each of these owes the chunk that builds it.** Field-level request and
response shapes are deliberately not here. `architecture.md` § Direction binds
that work — each route unpacks arguments, composes service calls without
branching on their results, and formats the result (as amended 2026-10-05) — and a response shape written before the service method exists is a
shape written against a guess. What this section fixes is the *set*: which
operations exist, what they stand on, and the rules above that a shape must not
violate. Everything else in this artifact still binds them, in particular the
`limit`-and-report-the-total rule under § Conditional Patterns and the single
`400` error shape.

**The two conversation reads are unpaged, and by the same reasoning `art_taste`
gives.** `GET /api/conversations` returns every thread and `GET
/api/conversations/{id}` returns every turn with its frozen samples, with no
`limit` and no total — because a household's threads and one thread's exchanges
are tens of rows, on the same scale as its taste, and a page control over ten
items is a control with nothing behind it. Recorded 2026-08-12 after Critic
review observed that every other collection in the surface names what bounds it —
`history_turns`, `SAMPLES_PER_SUGGESTION`, `PAGE_CEILING` with its shortfall note
— and these two named nothing, which reads as an oversight rather than as the
judgement it is.

**What would change it, so the next reader can check rather than re-argue.** The
threads accumulate on the curator's own rate and are deleted by hand, which is
the ruled lifecycle rather than a retention policy; the turns within one thread
are bounded by the conversation ending. If either stops being tens — a thread
that runs for months, or a household that never deletes — the
`limit`-and-report-the-total rule under § Conditional Patterns is what they take,
and `POST /turns` answering with the whole thread is the call that will feel it
first, since each exchange re-sends everything said before it.

**The last three rows came from the screens, not from the debt list, and that is a
correction worth recording.** The set above was first taken from
`information-architecture.md` § Status's five-item enumeration — and an enumeration
is not an inventory. Reading the screens' own Actions columns instead turned up
three designed controls with no route: the Work screen's **re-mat**, the Walls
screen's **next**, and the Health screen's **spend history**. Two of the three were
missed in the same way, by trusting a list that was written to record a debt rather
than to bound a surface.

> **`POST /api/works/{id}/mat` is listed here but is NOT this set's to decide.**
> Issue **#91** (`curation-ui: mat colour has no control on any human surface`,
> stage `design`) owns it, and its statement of the defect is *"an agent can change
> a mat colour and a curator cannot"*. An earlier draft of the paragraph below
> justified the route's absence with "re-deriving a mat is an operation
> `art_catalogue` already has" — **which is the exact reasoning #91 was filed
> against**, restated as though it were a settled decision. The row is here so the
> Work screen's builder finds it rather than inventing a route outside this set;
> its shape is #91's.

> **`next` was the one screen action with an MCP action and no HTTP route, and
> the shape it was waiting on arrived. Settled and built 2026-08-12.**
>
> It was left open on purpose: `art_display(action='next')` incremented the
> directive sequence while the built HTTP surface only ever *reported*
> `directive_sequence` in the manifest payload, so the Walls screen had a control
> the browser could not perform — and the multi-display blockers in § More than
> one wall landed on exactly this route. A directive is per-wall the moment there
> is more than one, so writing the installation-wide shape then would have been
> writing the shape that had to change. Walls became first-class; the shape
> followed.
>
> **`POST /api/directives`, body `{wall_id}`, returning `DirectiveOut {wall_id,
> sequence, pinned_work_id}`.** One service call, no new domain logic — the
> advance rule already lived in `DisplayService`.
>
> **It returns the directive rather than the wall**, which is the one part worth
> stating here rather than leaving in a docstring. A directive is what the caller
> changed and `sequence` is the thing that moved; returning the wall would answer
> a question nobody asked and would make the caller diff two wall payloads to
> discover whether the advance took. The read-back convention is honoured — the
> response is the written row, re-read — and the *row* is the directive.

**Still deliberately absent, so these omissions are not read as oversights:**
nothing here writes an artwork's own metadata, a source or an original. Title,
artist and date come from the source and are the physical label's evidence
(`information-architecture.md` § Boundaries). *(This paragraph carried the theme rename
and delete until 2026-08-11, correctly, and stopped being true when the IA was
approved. Its earlier correction of 2026-08-05 stands and is why the acquisition
routes are not listed as absent-because-unbuilt: acquisition **is** built —
`art_catalogue` gained the fetch, retry and mat actions on 2026-08-03 — and the
routes are absent because no browser screen has needed them.)*

**Annotations are mandatory on every tool**, because their defaults are worst-case:
omit them and MCP assumes `destructiveHint: true` and `openWorldHint: true`, which
costs the operator a confirmation prompt on every call. Each tool declares `title`
plus honest `readOnlyHint` / `destructiveHint`.

## The Server↔Player surface — PLANNED 2026-09-30, BUILT 2026-09-30

> **Built (wave 2b Chunk 03): the server's three routes, and wall tokens.**
> `arrt/src/arrt/http/player.py` mounts them at the root beside `/api`,
> spelled exactly as `contract/routes.json` spells them, and a test holds the
> router to that file. The manifest route serves the published file's bytes with
> their SHA-256 as the `ETag`, and answers `404` for a wall with nothing
> published. The media route hashes the bytes it is about to send and refuses
> (`404`) if they no longer match. The heartbeat POST accepts exactly what the
> health panel can read and answers `400` otherwise, in the error shape `/api`
> already uses. Tokens were issued per wall from `POST /api/walls/{wall_id}/token`
> and `art_display(action='issue_token')` until 2026-10-02, when clients replaced
> them (below). The Player's side is `postarr/src/postarr/pull.py` (Chunk 04):
> `MANIFEST_SOURCE=http` pulls into `CACHE_DIR` and renders only from there. What follows is the design as recorded before the build, and where it
> disagrees with the code or with `player-contract.md`, those win.

### Clients — BUILT 2026-10-02 (`build-plan-clients.md` Chunk 01)

`clients.md` is the requirement: a **client** is an installed Player with one
token, driving any number of walls, each on one of its outputs by name. The
Player routes take the client's token (`player-contract.md` § Transport is the
specification); the curator's routes below bind `programming/clients.py` and
`programming/access.py`. **The MCP twins arrived with Settings › Clients
(Chunk 02, 2026-10-02)** as `art_display` actions, thin bindings over the same
two services: until then these routes were HTTP-only, a recorded gap in parity.
`art_display` became `destructiveHint: true` with them, because
`remove_client` and `issue_client_token` cannot be undone (the reason
`art_taste` gives for its own flag).

| Route | Tool | What it is for |
|---|---|---|
| `GET /client` *(Player)* | — | The presenting client and its walls with their outputs, `ETag`/`304`. `401` without a valid client token |
| `POST /client/heartbeat` *(Player)* | — | The client's outputs (name, kind, connected, screen), kept as `client-heartbeat-{client_id}.json` under `ART_ROOT` beside the wall heartbeats. `204`; `400` naming the problem |
| `GET /api/clients` | `art_display(action='clients')` | Every client, with `token_issued_at` (never the token), its walls and outputs, and its last heartbeat's outputs, age and `description` (the reading as one sentence, the same on both surfaces; added Chunk 02) |
| `POST /api/clients` `{name}` | `art_display(action='add_client', name)` | Record a client. No token, no walls |
| `POST /api/clients/{client_id}` `{name}` | `art_display(action='rename_client', client_id, name)` | Rename. Token and walls unchanged |
| `DELETE /api/clients/{client_id}` | `art_display(action='remove_client', client_id)` | Forget a client: its token stops working, its walls become unassigned and keep their themes, its heartbeat file goes. Answers the remaining list; the tool answers the walls released (`released_walls`), named in its notice |
| `POST /api/clients/{client_id}/token` | `art_display(action='issue_client_token', client_id)` | Issue or rotate; answers `{client_id, token, token_issued_at}` once. The tool adds a notice naming `CLIENT_TOKEN` and `SERVER_URL` |
| `POST /api/walls/{wall_id}/client` `{client_id, output}` | `art_display(action='assign_wall', wall_id, client_id, output)` | Show the wall on that client's output. Answers `{wall, notice}`: `notice` says when the output is not among the client's last reported outputs, or it has not reported; the assignment is made either way. Refused when that output already shows another wall |
| `DELETE /api/walls/{wall_id}/client` | `art_display(action='unassign_wall', wall_id)` | Unassign. Idempotent |

`WallOut` and the MCP wall shape lose `token_issued_at` and gain `client_id` and
`output` (both null while no client shows the wall).

**Retired 2026-10-02:** `POST /api/walls/{wall_id}/token` and
`art_display(action='issue_token')`, with the Walls screen's Player token panel.
A wall token admits nothing. This is breaking for a Player configured with
`WALL_TOKEN`, by the plan's ruling that no transition is kept.

**Before 2026-09-30 nothing in this section existed in code.** It records the target that
`re-architecture.md` § Seam 2 sets. **The contract artifact now exists:
`player-contract.md`, with its schemas and fixtures under `contract/`.** Where
this section and that file disagree, that file wins.

**Why it replaces the file channel.** Once the server moves to the NAS, the
shared `ART_ROOT` would have to become a network mount on every Pi. Network
mounts hang the processes that read them when the NAS reboots, which is the exact
failure the availability norm exists to prevent. A pull into a Player-local cache
keeps the norm true across the hop: the cache is the only path the Player ever
renders from, so it is exercised on every rotation rather than being a fallback
that is tested only on the night it matters. The norm amendment itself is
recorded in `architecture.md` § Direction.

| Route | Direction | Shape | Obligation |
|---|---|---|---|
| `GET /walls/{wall_id}/manifest` | Player → server, polled at about 1 s | Today's manifest document with `ETag`, answered `304` when unchanged. Carries the playlist entries, rotation settings, the directive block (`sequence`, `pinned_work_id`), the label text and, per entry, a **content-addressed media URL and hash**. From major 2 it also carries the current mat colour, and the playlist, rotation and directive become the **schedule**, any active **scene**, a **staging** list and the **wall settings** (`re-architecture.md` § What is showing, and how it is shown). | **Bounded.** The same major/minor rule as the file channel, described below. |
| `GET /media/{hash}` | Player → server | From wave 4, the **presentation master**: device-independent, unmatted, long edge capped (starting proposal about 8K, to be measured). In waves 2 and 3, before any master exists, today's composed `tv_display` rendition. Immutable. `Cache-Control: immutable` and a long max-age, because the name *is* the content. | **Frozen per hash.** A hash never serves different bytes. |
| `POST /walls/{wall_id}/heartbeat` | Player → server | Today's heartbeat document (`reported_at` and the rest; see `observability-strategy.md`). From wave 4 it also carries the Player's **capabilities** (geometry, backend, label hardware) **as observations**. | **Bounded**, like the manifest. Programming reads the capabilities and judges per-wall adequacy from them; the Library never sees them. |

**Every route carries the wall's token** (decided 2026-09-30,
`re-architecture.md` § Seam 2) as a bearer credential. A missing or wrong token
is `401`, and a token for another wall is `403`. *(Amended 2026-10-02: the
client's token, admitted for the walls assigned to that client; `403` for a wall
that is not its client's. § Clients above.)* The Player treats either as a
configuration error, stated once in the journal, and keeps its cache, like a
`404` on its wall.

**Versioning carries over rather than being re-decided.** `SCHEMA_MAJOR` and
`SCHEMA_MINOR` keep their meanings: additive changes are free, and a breaking
change bumps the major, which the Player refuses while keeping the manifest it
has.
- **The HTTP channel is a minor bump (wave 2).** It is built *alongside* the
  file channel, and the document itself does not change shape. Only its
  transport and its media references are new.
- **Major 2 (wave 4) carries every breaking change at once.** `render_path` to a
  composed 4K canvas is replaced by a presentation-master reference plus the mat
  colour, and the playlist and directive become the schedule and scenes. A
  major-1 Player cannot draw a wall from either. The refusal rule is
  what makes the cutover safe: an un-upgraded Player keeps showing yesterday's
  wall instead of misreading today's.

**The error model follows the manifest's existing posture, not the MCP
envelope.** The consumer is a daemon, not a model, so errors do not need to
teach. They need to be classifiable.
- **Transport failures, 5xx responses and timeouts** are "server unreachable":
  keep the cache and back off, the same ladder an unreachable television gets.
- **404 on a wall** is a configuration error, stated once in the journal.
- **404 on a media hash** is a work that cannot be shown: skip it and keep
  rotating, as with a missing render file today.
- **An unrecognised major** is refused, and the last good manifest is kept.

The wall going black stays worse than the wall being incomplete. That is the rule
this whole surface is judged by.

**Open, each settled before the wave named in `re-architecture.md` § Open questions:**
- **Authentication** is settled: a bearer token per wall, on every route
  (`player-contract.md` § Transport).
- **ETag polling or server-sent events** for directive latency. Polling matches
  today's roughly 1 s behaviour and is the default.
- **The presentation master's encoding and cap.**

### History, selections and *Not this one again* — BUILT 2026-10-07 (`build-plan-walls-work-and-trust.md` Chunks 03, 04)

The server halves of the owner's rulings 1 and 6 of 2026-10-07 (`ia-proposal.md`
§ Rulings). Exercised against a booted server by
`arrt/tests/integration/test_history_surface.py` and
`arrt/tests/integration/test_selections_and_exclusions.py`, both surfaces.

| Route | What it is |
|---|---|
| `GET /api/history` | What happened, newest first: `events` of `{event_id, kind, occurred_at, artwork_id, run_id, wall_id, theme_id, detail}`, with `total`, `limit`, `offset`. `kind` repeats and any named matches (`EventKind`'s values; an unknown one is refused by name); `wall_id` is one wall's history, what was hung there and what was kept off from there. `limit` 1–100, default 25. Every id may no longer resolve, so `detail` carries the words: `title`, `theme_name`, `wall_name`, `selection`, `works`, `run_kind`, `intent`, `status`, `reason`, `candidate_work_id`. Recorded from 2026-10-07 on; nothing earlier. Twin: `art_catalogue(action='history', kinds=[...], wall_id=...)`. |
| `POST /api/walls/{wall_id}/selection` | Hang `{artwork_ids}` (one or more, in order) on the wall until something else is hung there. Stored as a theme with `hidden: true`. Returns the manifest build, as `activate` does. Refused, with nothing hung, for an empty list or an id the Library does not hold. Twin: `art_theme(action='hang_selection')`. |
| `POST /api/walls/{wall_id}/not-again` | *Not this one again*, `{artwork_id, scope}`: `theme` takes the work out of the theme hanging on that wall; `every_wall` keeps it off every wall (a `WorkExclusion`), and it stays held and in its themes. The walls carrying it lose it from their published manifests at once, and a pin naming it is withdrawn without advancing; nothing else on any wall changes. Returns `{scope, artwork_id, wall, left_theme, excluded_at}`, the wall read back. Twin: `art_theme(action='not_again')`. |
| `GET /api/exclusions` | Every work kept off every wall, `{artwork_id, excluded_at}`, oldest first. Twin: `art_theme(action='kept_off')`. |
| `DELETE /api/exclusions/{artwork_id}` | The undo: the work may go on walls again. Republishes nothing; the next hang or sync carries it. Returns the exclusions that remain. Refused for a work not kept off. Twin: `art_theme(action='allow_again')`. |
| `ThemeOut.hidden`, and `theme_fields`' `hidden` | Every theme shape carries it. `GET /api/themes`, `art_theme(action='list')` and the works grid's theme options leave hidden themes out (the grid keeps one only while it is the filter in force); a wall's `theme` may be one. |
| `ExclusionOut.reason` gains `kept_off_every_wall` | A manifest build names an excluded work with this reason, ahead of any reason the Library would give. |

Each act writes one `HistoryEvent` (`data-model.md`), and a refused act writes
none. *Not this one again*'s two answers are one service method,
`DisplayService.not_this_one_again`, so the HTTP route and the tool do not each
decide which act a scope means.

**The Library facade is a second, internal interface, drawn now to be
network-ready later.** `re-architecture.md` § Seam 1 has Programming calling the
Library only through a small facade, centred on
`playable(work_ids) -> {id: PlayableWork | Unplayable(reason)}`. It is
coarse-grained, id-based, returns plain data and is idempotent. Since
2026-10-07 it also takes `record(ProgrammingAct)`, Programming's acts on the walls
for the history, written after Programming's own change commits. That one call is
a write and is not idempotent: a retried call records a second line. It is **not an
exposed API** today and carries no versioning obligation, because both sides ship
in one process. It is recorded here because it is written *as if* it were
remote. If the Library and Programming ever split, this facade becomes a network
surface and inherits the bounded obligation above. Nothing about its shape should
need to change when that happens.

## Conventions

**One binding norm already governs this artifact** — `architecture.md` § Direction,
ratified by the owner 2026-07-20, with its enforcement row in
`project-preferences.md`:

> **Operation logic lives ONLY in the service layer. MCP tools and HTTP handlers
> are thin bindings and contain no business logic.**

This is what makes the chosen architecture safe. UI controls call HTTP, agents
call MCP — two entry points, one implementation. A handler that validates,
orders, or decides is a violation; a handler that unpacks arguments, calls one
service method, and formats the result is the norm.

Without it, "MCP at parity with the web UI" degrades into two implementations of
every operation that diverge invisibly — an agent and a click producing different
results, with no test that would catch it.

**The registry gives that norm a structural home.** hallucinote separates
declarative action records (schema, description, example, tips — no logic) from
handlers (the work). That split *is* this norm, expressed as a directory boundary
rather than a rule someone has to remember: an action record that contains a
decision is visibly in the wrong file. Adopting the same shape here means the norm
is enforced by where code lives, not only by review.

**Consolidation is vertical, never horizontal.** A tool may do several internal
steps to serve one operator intention. What it may not become is a generic
multiplexer — an `art_request(method=..., path=...)` passthrough is the
anti-pattern Anthropic's Directory review rejects outright, and it would put routing
logic in the binding, which the norm above forbids.

## Security

**Trust model:** the network layer carries it. The MCP server is LAN-only, reached
remotely via an overlay network (Tailscale/VPN). No authentication, no TLS
termination, no rate limiting in the application — proportionate for a
single-principal household tool, and recorded as a decision in
`project-state.yaml` → `technical_decisions.integrations`.

**`initiated_by` is provenance, not authorisation.** Every surface has identical
authority. Agent-initiated runs queue candidates for the same reason UI-initiated
runs do — the review gate is universal, not a restriction on agents. Branching
authority on the caller would reintroduce the parity split MCP exists to prevent.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The server moves
> to the operator's NAS and gains a **LAN listener for Players**, whose clients
> are devices, not the curator. "Anyone on the network is the curator" was
> sound when every inbound caller was a person. It needs restating once a Pi at
> a wall holds a write route: the heartbeat POST can make a wall's health read
> green or red.
>
> Whether the Player surface authenticates is open, and `security-model.md`
> § Trust Boundary owns the answer. Two more things apply:
> - **Watches** are standing, scheduled searches, and can auto-accept. They fire
>   the "unattended discovery" trigger that `security-model.md` § Prompt Injection
>   names. That section must be re-derived before Watches are built.
> - **`initiated_by`** will need a value for a Watch.

**The real exposure is prompt injection, and it is bounded — but less tightly than
this artifact previously claimed.**

Discovery reads arbitrary gallery sites, prize pages, and artist portfolios —
attacker-influencable text — and feeds it to an agent whose tools mutate the
catalogue and spend money.

> **A bound was voided on 2026-07-19 and is corrected here rather than quietly
> dropped.** This section used to open with *"Agents cannot auto-accept. Every
> addition stops at curator review."* That was true while the review gate was
> withheld from the MCP surface. It is no longer: `art_review(action='set_verdict')`
> exists, decided the same day, because the gate's real content is that a human
> *saw the artwork* — not that a surface was denied a tool. An injected
> instruction now has a verdict tool within reach.
>
> Leaving the old sentence in place would have been the worse outcome: a future
> reader would have taken a stale guarantee as current and built on it.

What actually bounds the exposure now, in descending order of strength:

1. **The spend cap fails closed.** A poisoned page cannot run up an unbounded bill.
   This bound is unchanged and is the strongest one.
2. **Tool authority stays narrow** — no filesystem access, no shell, no arbitrary
   fetch. The blast radius stays inside the catalogue.
3. **Acceptance is visible and fully reversible.** It changes the wall, which is the
   most conspicuous surface the product has; archive restores.
4. **The curator is present in the session** that issued the request, and the
   accepted set is enumerated in the transcript.

Bounds 3 and 4 are materially weaker than "cannot", and are stated as such. Bound 4
in particular is a property of how the operator works, not something the system
enforces.

**One design consequence follows, DECIDED 2026-07-20: `set_verdict` requires
explicit work ids and refuses a bare "accept everything pending."**

It does not stop a determined injection — an agent can enumerate first — but that
was never the bar. The bar is that **the accepted set appears in the transcript
where the curator sees it.** Given the review gate's durable justification is
content appropriateness rather than spend, the ids being visible at the moment of
acceptance *is* the gate doing its job; an `accept_all` that leaves no record of
what "all" was would hollow it out while looking identical in the happy path.

Accepted cost: friction on the legitimate "accept them all" path, which is the
common case after a good run. The curation UI can still offer a select-all
affordance — it simply sends the ids, which is what a UI naturally has anyway.

Worth stating plainly: the realistic worst case is a poisoned page steering
candidate selection, burning budget, or getting an unwanted image onto the wall
until someone looks. Annoying and visible, not a breach. There is no
multi-tenancy and no payment surface.

> **The "no PII" half of that sentence was retired on 2026-08-12** and is struck
> rather than quietly deleted, because the threat assessment above rests on it.
> `security-model.md` § The one exception designates `ConversationTurn.text` as
> the product's only retained free-text record of a person. **It does not change
> this section's conclusion**: the vector reasoned about here is content coming
> *inward* from a museum or search page into the candidate pipeline, and nothing
> an injected page can reach reads a conversation turn back out. What it does
> change is that "not a breach" can no longer be argued from the product holding
> nothing personal — it is argued from what this particular vector reaches. That
> is a narrower claim, and it is the true one.
>
> **The outward direction is real and is not this paragraph's**: `commit` passes
> the curator's own committed sentence to `DiscoveryRunner.start(intent_text=…)`,
> which is what a search provider is asked. That is by design — a run cannot be
> explained without it — and it is why `observability-strategy.md` names the
> words the one thing here whose logging is a decision rather than a freedom.
>
> This was the third file carrying the retired wording, found after the other two
> were corrected. `observability-strategy.md` owns the logging consequence,
> `security-model.md` is the authority on the record itself, and this paragraph
> owns only what an injected page can get to.

## Conditional Patterns

**Pagination and filtering.** Listing actions take a `limit` with a sane default and
a filter appropriate to the entity. A truncated result says so explicitly and gives
the total — `"showing 20 of 84; narrow the filter"` — never a silent cut. Both of
the operator's servers enforce this and cordyceps' own comment names the reason:
items that cannot be handled are *reported as failures, not silently skipped*.

**Bounded exception — a listing whose cut can only fall on items the caller has
no reason to reach takes no `limit`.** `art_review(action='list_images')` is the
one such listing. The `limit` half of the rule exists to let a caller reach items
a cut would otherwise hide; where the cut provably hides nothing a caller could
act on, there is nothing to reach and a lower limit would only ask for fewer of
the best. The cap is therefore fixed. The truncation half still binds in full: the
card reports what it holds against what it shows, and offers no paging it cannot
honour. **Any listing whose cut is arbitrary takes the `limit`.**

**The exception is conditional, and the condition is a requirement on the card,
not an observation about it: a truncated card must never drop a selectable
instance in favour of one the curator has already turned down.** Rejected scans
stay on the card as the evidence of a judgement, so they compete for its slots —
and they arrive at the *top* of a confidence ordering, because the scan a curator
turns down is the best one on offer and rejecting it does not change its
confidence. An ordering that does not sink them therefore has a state where the
card is entirely already-rejected scans while the only selectable ones fall off
the bottom, and the notice's promise — that what is unlisted is not worth choosing
— is false in the one state where it decides anything. `list_images` is the sole
enumerator of a work's instances, so there is no second path to the ids it drops.
Filling the card from the surviving instances first and spending what remains on
rejected ones satisfies this; so does any ordering that sinks rejections. What
does not satisfy it is a cut that reads confidence alone.

**Bulk operations** return the per-item shape described under Inputs & Outputs.

**Summary then detail.** Listing actions return the fields needed to decide;
`get_*` returns the full record. This is the cheapest lever on token cost and it is
why `art_review(action='list_works')` returns one thumbnail per work rather than
the instances found for it. That one picture is not always the instance a verdict
would accept on — a work whose scans are all below the floor has no selection and
still arrives with a picture, because a work no picture exists for and a work
whose picture was withheld must not look alike. `is_on_offer` is what separates
them.

## Open Questions

Carried in `project-state.yaml` → `open_questions`; restated here so this artifact
is self-contained:

- ~~Whether the MCP surface should expose *resources* in addition to tools.~~
  **CLOSED 2026-07-20: no resources in v1**, recorded in `project-state.yaml`
  with its reopen trigger and restated under the build plan's "Explicitly
  deferred". Left listed as open here until 2026-07-20, which is a live invitation
  to re-open a settled scope decision — this artifact is what an implementer binds
  when building the tool surface. The original reasoning, which still holds and is
  why the answer is no: the
  specification's split is about *control* — who decides when something enters
  context — not about mutability, and it never says read-only operations must be
  resources. Anthropic's own guidance says a tool is right when the result depends
  on parameters the model chooses, which covers every read here. A stable browsable
  artifact (the active theme, display state) may still earn a resource later.
- **Opened 2026-09-30, and owned by `re-architecture.md` § Open questions:**
  - authentication on the Server↔Player surface;
  - ETag polling versus server-sent events;
  - the presentation master's cap and encoding;
  - how a review card shows fit once no single panel exists.

  New MCP actions will be needed for Watches, programming tags and smart
  playlists. Each is an additive action on an existing tool, or a new tool
  name, and each is decided when its wave is planned, not here.

## Validation

The tool surface is **measured, not argued about**. Anthropic's published method is
to write verifiable operator prompts, run them against the surface, and compare
accuracy, tool-call count, token consumption, and error rate — and it explicitly
names workflow-versus-atomic granularity and namespacing as things to *test* rather
than deduce.

*(Amended 2026-07-27. This paragraph read "the repo currently has **no test suite at
all**"; that departure was closed the same day, two suites now run, and the sentence
had become false.)* On top of those suites sits an **MCP evaluation harness** — a
different thing from the contract tests. The contract tests assert the surface's
shape; the harness asserts that a model can actually *use* it, which is the only way
to know whether this consolidation is right *for this product* rather than in
general, and the thing that catches the description-drift problem the Versioning
section flags. Filed as issue #17.

*(Amended 2026-08-01 — built, in two halves, and the split is worth stating because
the distinction above is exactly what produced it.)* Asserting a model can use the
surface needs a model, and a model is not deterministic: it may reach the same goal
by a different route on the next run. So the harness is:

- **A scenario runner** (`arrt/tests/contract/`), deterministic and in the
  default suite, driving real product flows as a real MCP client. Each step passes
  an id the *previous* step's envelope returned, which is what fails when two tools
  disagree about the name of the thing they hand each other — a defect neither
  tool's own tests can see. It also checks two envelope invariants on every call:
  that `isError` agrees with the payload's `success`, and that the JSON text and
  `structuredContent` bodies match.
- **A model-driven evaluation** (`arrt/tests/eval/`), behind the `llm_eval`
  marker and deselected by default, running verifiable operator prompts and
  measuring accuracy, call count and error rate against the scripted route as its
  yardstick. It asserts the **end state, not the route** — a model that takes six
  calls instead of four has not failed. It runs through `3tears-models` over
  OpenRouter.

The second one is what settles the question this section poses, and the reason it
cannot gate a suite is the reason it is worth having: only a model can tell you
whether an error message actually teaches.

Both production servers already do the narrower version of this. cordyceps pins its
tool names in a test; hallucinote boots a real server and asserts `list_tools()`
output against its registry, including that prose and code cannot drift — it tests
that the tool count quoted in its README matches the registry.
