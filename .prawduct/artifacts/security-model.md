---
artifact: security-model
version: 1
depends_on:
  - artifact: product-brief
  - artifact: data-model
  - artifact: api-contract
last_validated: null
---

# Security Model

One principal, one household, no PII, no payment surface, no multi-tenancy. Most
of a conventional security model does not apply here, and generating it anyway
would be template worship. What this document covers is the four things that are
genuinely live:

1. **Credentials**, because the repository is public and one is already committed.
2. **Prompt injection**, because discovery feeds attacker-influencable web text to
   an agent holding mutating, money-spending tools.
3. **Content appropriateness**, because the household never opted in to what
   appears on the wall.
4. **The trust boundary**, because it is carried entirely by the network layer,
   which is a real decision with real consequences if it ever changes.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The product is
> becoming a **server** (Library + Programming) on the operator's NAS and a
> **player** at each wall. In this file, that affects:
> - **the trust boundary:** a new LAN listener whose clients are devices, a
>   heartbeat POST that is the first write route a non-curator holds, and an
>   open question on player authentication;
> - **credential placement:** the OpenRouter key moves with the server to the NAS;
> - **prompt injection:** Watches fire the "unattended discovery" trigger below;
> - **supply chain:** the server's interpreter comes from a container image.
>
> The four live concerns listed above do not change. The notes below sit at each
> affected section. None of them is built yet.

## Direction

<!-- Ratified by the owner 2026-10-01, as written. Enforcement row in project-preferences.md. -->

**Text from outside Arrt (a registry, a museum, a model) reaches the page as
text and is never parsed as markup. An image or link from outside is used only
when its host is one this repository names, or is built here from a checked
identifier.**

> **Why:** anyone can edit Wikidata, a museum's catalogue text is the museum's,
> and a model repeats what it read. Every one of them arrives in the curator's
> browser by a channel no model reads (`architecture.md` channel 9), so the
> prompt-injection bounds below do not cover it. A title carrying `<img
> onerror>` is the whole of the text attack, and an `img` source or link the
> registry chose is the whole of the URL one: it tells a stranger's server
> that the curator is looking, and it can send the curator anywhere. One page
> was bounded by its own tests (§ Registry text). A norm is what binds the next
> page, and one-world search is that page.

**What holds it:**
- **Markup is never parsed in the client.** No script under
  `arrt/src/arrt/http/static/` uses a sink that parses markup or compiles a
  string (`innerHTML`, `document.write`, `srcdoc`, `eval`, a timer handed a
  string, and the rest the test lists), and no page there carries script of its
  own. Nodes are built with `el` (`core/render.js`), which sets text through
  `textContent`.
- **A registry's strings say what they are.** Every string a registry hands the
  Library, in a type or in a question's answer, is typed as registry text, an
  item id, a museum identifier the caller asked about, a Commons file, or a work
  page. A plain string fails a test, so a new field or question has to choose. A
  Commons file is the only kind that may become a URL in the browser, and the
  server builds that URL itself, as a `commons.wikimedia.org` FilePath address from
  the file's name (`library/registry/wikidata.py`), so no host the registry
  supplied reaches the page. *(Corrected 2026-10-05 by the Norm Health sweep: this
  sentence said the client checks the host, and no client check exists; the
  server-side construction is what holds it.)* **A work page**
  (added 2026-10-03, `source-plugins.md` § The Wikidata finder) is a URL the
  server keeps as a sighting and never sends to the browser, as a link or as
  text: the sightings route and its MCP twin return its host as a name, which
  `tests/integration/test_sightings_api.py` holds.
- **Links out are built from an item id**, never from a URL the registry
  supplied. No test sees this half, which is the Critic's.

**Retroactive:** yes. Every page the client has today already conforms, which
the sink test confirms on the day it lands. The museum clients' text (titles,
descriptions, provider names) reached the page under `core/render.js`'s rule
before this norm, and this norm is that rule made binding.

## Trust Boundary

**The network layer carries the entire trust boundary.** Both surfaces — the MCP
endpoint and the UI's HTTP API — are LAN-only, reached remotely over an overlay
network (Tailscale/VPN). The application performs no authentication, no
authorisation, no TLS termination, and no rate limiting.

> **Amended by the owner, 2026-10-02 (`build-plan-nas.md`):** on the NAS the
> server is reached at a `.lan` name through the house's LAN-only reverse proxy,
> with **no overlay network** — the homelab has none — and still no login, as
> the owner's other apps there are. So "anyone on the overlay network" below
> reads "anyone on the house's LAN". The worst case of a LAN client spending
> model credit is bounded by the provider's $20/month cap
> (`nonfunctional-requirements.md`). A login, and Tailscale for reaching it from
> away, are backlog, not decided against.

This is a recorded decision, not an omission
(`technical_decisions.integrations`, 2026-07-19). For a single-principal household
tool it is the proportionate answer, and it is what keeps this document short.

**What it means concretely:** anyone who is on the overlay network is the curator,
with full authority over every operation. There is no lesser role, no read-only
mode, and no audit distinction between principals because there is only one.

**The consequence that must not be forgotten:** the day this surface becomes
reachable from the public internet, *every* control in this document is void and
the model must be rebuilt from scratch — authentication, authorisation, rate
limiting, TLS, and abuse prevention all become real requirements simultaneously.
That is not a gradual degradation; it is a cliff. Any change that exposes the
curation plane publicly is a structural characteristic flip and triggers the full
re-derivation protocol, not a patch.

> **Direction changed 2026-09-30 — see `re-architecture.md` § Seam 2 and
> § Deployment target.** Three things change at this boundary. The first comes in
> wave 3, and the other two in wave 2, when the HTTP routes first appear on the
> server that already listens on the Pi. None of them is the public-exposure cliff above, and that paragraph
> binds as it stands.
>
> 1. **The server moves from the Pi to the operator's NAS.** The surfaces stay
>    LAN-only and are reached remotely the same way. The host changes, and the
>    boundary does not.
> 2. **A new inbound surface appears, and its clients are devices, not the
>    curator.** `GET /walls/{id}/manifest` and `GET /media/{hash}` are
>    read-only, and they expose nothing the curation UI does not already show.
>    `POST /walls/{id}/heartbeat` is a **write**: anything on the LAN that can
>    reach it can make a wall's health read green while its screen is dark, or
>    red while it works. That is the product's defining silent-failure shape,
>    manufactured on purpose. It is an integrity exposure, not a
>    confidentiality one, and it cannot reach the catalogue. It is still the
>    first write route held by something that is not the curator.
> 3. **"Anyone on the network is the curator" needs a narrower statement for
>    that route.** Before wave 2 ships the POST, decide one of. *(Moved
>    later on 2026-09-30 from "before wave 3": the curation server on the Pi is
>    already reachable on the LAN, so the route exists from wave 2.)*
>    - (a) the LAN stays the whole boundary, and the heartbeat is accepted from
>      any LAN host, recorded as an accepted risk; or
>    - (b) each Player holds a per-wall token that the server checks on the
>      POST, and optionally on the GETs.
>
>    (b) adds the product's first credential held by something other than the
>    curator's own processes, and a row in the Inventory below.
>
>    **Decided 2026-09-30: (b).** The operator ruled "each wall gets a token".
>    The token is checked on every wall route and on media, not only on the
>    POST. That extension is the advisor's, and it is vetoable. The full
>    record, including issue, storage and rotation, is in `re-architecture.md`
>    § Seam 2.
>
> The Player's reverse path (the TV websocket, SPI) is unchanged, and it stays
> the only thing that talks to a television.

**`initiated_by` is provenance, not authorisation.** Every surface has identical
authority. An agent-initiated run and a UI-initiated run are subject to the same
gates, because branching authority on the caller would reintroduce exactly the
parity split MCP exists to prevent.

## Credentials and Secrets

### Inventory

| Secret | Held by | Exposure if leaked |
|---|---|---|
| OpenRouter API key | curation plane | **Real money.** Bounded by the per-key credit limit, which is the same control that bounds a runaway agent |
| Samsung TV pairing token | display plane | LAN-scoped. Lets a LAN-present attacker drive the TV |
| Museum API keys, if any | curation plane | Negligible; the ARTIC API is free and public |
| Client token, one per client *(replaced the per-wall token 2026-10-02, `clients.md`)* | the installed Player (the client) on its host, in its environment file; the server keeps only its SHA-256 (`clients.token_verifier`) | LAN-scoped. Lets someone on the LAN read the manifests and renders of the walls assigned to that client, read which walls those are and on which outputs (`GET /client`), and forge those walls' heartbeats and the client's own. It cannot change what hangs anywhere or which client shows which wall, and it opens no wall assigned to another client. Rotated by issuing again (`POST /api/clients/{client_id}/token`), which stops the old one at once; removing the client stops it too |

The display plane holds no credential except the TV pairing token and, once it
pulls over HTTP, its own client token, and the curation plane holds no
device credentials. That falls out of the topology rather
than being separately enforced.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The separation
> above survives the move, and becomes a separation of *machines* rather than of
> processes on one Pi. That is stronger.
> - **The OpenRouter key and any museum keys move with the server to the NAS**,
>   configured as secrets of the server's container, not in its image and not in
>   this public repository.
> - **The TV pairing token stays with the Player** on the Pi at the wall. The
>   server never holds it, and after wave 4 the server does not even know a
>   television exists.
> - **Each Player holds a per-wall token** (§ Trust Boundary, option b, decided
>   2026-09-30), and the server holds only the matching verifier. **Built
>   2026-09-30 (wave 2b Chunk 03)**, and its row is in the Inventory above. It is
>   32 random bytes, shown once, compared in constant time, and never logged: a
>   refusal is logged by wall and status, once per wall per ten minutes. Media
>   answers to any wall's token, because a render is shared by every wall that
>   shows it.
> - **Amended 2026-10-02 by the owner's ruling that clients are first-class
>   (`clients.md`): the token is per client, not per wall.** One installed Player
>   drives several walls with one credential, admitted to the walls assigned to
>   it (`401` for no valid token, `403` for a wall not its client's); media
>   answers to any client's token. Kind unchanged: 32 random bytes, shown once,
>   SHA-256 verifier, constant-time compare, never logged. A refusal is logged
>   by client name, or as "an unknown client", once per that subject per ten
>   minutes. **Wall tokens are retired**: nothing admits one, and the server
>   drops the stored wall verifiers on opening a catalogue that holds them
>   (`migrations.retire_wall_tokens`). The credential is still the product's
>   only one held by something other than the curator's processes.

### The repository is public

`brookstalley/arrt` (renamed 2026-09-30 from `samsung-frame-art-loader` to `curatarr`, and 2026-10-01 to `arrt`) is a **public** GitHub repository. This is
the single most important fact in this document, because it converts "don't commit
secrets" from hygiene into a hard requirement with an audience.

**A secret must never appear in source, in a committed config file, in a test
fixture, or in a log line that could be pasted into an issue.** Deployment values
already have a Critic-enforced norm keeping them out of source
(`project-preferences.md`); secrets are the same rule with a worse failure mode.

### `token_file` was a leak, and it is closed — 2026-07-27

**Status: remediated.** The Samsung TV pairing token had been committed since
`e825276`. It was untracked and gitignored in `ba007cd` (issue #4, closed), and
the operator confirmed **the leaked token had already expired**, so the re-pair
that rotation would normally require was not needed. Both halves matter: untracking
alone would not have closed it.

**The residue is honest and permanent.** The expired token is still in git history,
which is public and cloned. That is not fixable by any future commit and does not
need to be: an expired LAN-scoped token authenticates nothing.

**The rule this leaves behind, which still binds.** The remediation for a leaked
credential is *rotation*, not deletion — the sequence below is the one to follow
if a **live** token is ever committed again. It is kept because the reasoning is
what makes the next incident cheap, not because this incident is open.

**Honest severity: low, and deliberately not inflated.** The token is LAN-scoped
— an attacker needs to already be on the household network to use it, and an
attacker already on the household LAN can reach the TV's pairing flow anyway. The
realistic worst case was someone changing what is on a television. While it was
open it was recorded as unfixed rather than quietly downgraded, because "we decided
it was fine" and "we forgot" look identical in six months — and it is now recorded
as closed with the evidence, for the same reason.

**Order of operations — CORRECTED 2026-07-20 (Critic R-1). Untrack first, then
rotate.** This artifact previously prescribed the reverse, and that order creates a
*second* leak: rotating while the file is still tracked puts the freshly-issued
token into a tracked file, where the next `git add -A` commits it. This repository
is developed with frequent `git add -A`, so that window is not theoretical.

The old order was argued from *perception* — that untracking first "creates the
impression it has been dealt with". That concern is real but is answered by honest
prose, which this section already carries. It is not worth a second exposure.

1. **`git rm --cached token_file`, add it to `.gitignore`, commit.** Costs nothing
   in security terms — the old token is already public in history — and guarantees
   the replacement is never tracked. *(Done 2026-07-27.)*
2. **Re-pair against the TV** (physical access required). The new token is written
   to an untracked path and never enters git. *(Not needed for this incident: the
   leaked token was confirmed already expired. Required for any live one.)*

> **The operational hazard this note described is gone (2026-07-27), and the
> remediation sequence it prescribed must not be followed.** It read: `token_file`
> is read at runtime by relative path (`tvart.py`), so because deployment is
> `git pull`, the commit that untracks it **deletes it on the Pi** — meaning untrack
> and re-pair had to be done in one sitting, with hardware access.
>
> That coupling was removed by the config hoist: the token now resolves under
> `ART_ROOT` (`config.tv_token_file`, passed explicitly at both call sites in
> `tvart.py`), which is outside the checkout. Untracking it therefore does not
> delete it on the Pi, and the two steps are independent. **An operator following
> the old sequence would be scheduling hardware access for a problem that no longer
> exists** — which is why this is corrected here rather than quietly deleted.
>
> The relative-path load was itself an instance of the hardcoded-deployment-value
> departure recorded in `project-preferences.md`. That departure is closed.

**What this does not fix:** the token remains in git history, which is public and
cloned. Only rotation invalidates it. Untracking is hygiene for the *next* token,
never remediation for this one.

## Prompt Injection

This is the product's most interesting exposure and the one most easily
overstated in either direction.

**The mechanism.** Discovery reads arbitrary gallery sites, prize pages, artist
portfolios, and search results — text an attacker can influence — and feeds it to
an agent whose tools mutate the catalogue and spend money. There is no way to
build the product's core feature without this exposure existing.

**A guarantee was voided on 2026-07-19 and is not restored here.** This model used
to rest on *"agents cannot auto-accept; every addition stops at curator review."*
That stopped being true when `art_review(action='set_verdict')` was placed on the
MCP surface — a deliberate decision, because the review gate's real content is
that *a human saw the artwork*, not that a surface was denied a tool. An injected
instruction now has a verdict tool within reach.

What bounds the exposure now, **in descending order of strength, with the weak
ones labelled as weak**:

| # | Bound | Strength |
|---|---|---|
| 1 | **The spend cap fails closed**, enforced by OpenRouter server-side rather than by our code | **Strong.** A poisoned page cannot run up an unbounded bill, and it cannot be bypassed by a bug in our metering |
| 2 | **Tool authority is narrow** — no filesystem access, no shell, and **no fetch by Arrt a curator did not first accept**. Blast radius stays inside the catalogue | **Strong, and narrower than it was.** Structural, but see the re-derivations below: acquisition fetches, and what bounds it is the URL policy rather than the absence of the capability; and a source plugin may read a page the run's search cited before anything is accepted (§ Plugins read pages a search cited) |
| 3 | **A per-run search cap** bounds a single runaway run, not just the month | **Moderate.** Bounds cost and loop length, not content |
| 4 | **Acceptance is visible and fully reversible** — it changes the wall, the most conspicuous surface the product has, and archive restores | **Weak as prevention.** It is detection and recovery, not prevention |
| 5 | **`set_verdict` requires explicit ids**, so the accepted set is enumerated in the transcript | **Weak.** An agent can enumerate first. It buys visibility, not refusal |
| 6 | **The curator is present** in the session that issued the request | **Weakest.** This is a property of how the operator works, not something the system enforces |

**Bounds 4–6 are materially weaker than "cannot" and are stated as such.** The
honest summary: the realistic worst case is a poisoned page steering candidate
selection, burning budget, or getting an unwanted image onto the wall until
someone looks. **Annoying and visible, not a breach.** There is no tenancy to
cross, no payment surface to abuse, and no credential the agent can reach — and
**nothing an injected page can reach reads a conversation turn back out**, which
is the form this clause takes now that § The one exception below designates
`ConversationTurn.text` as a record of a person. It said "no PII to exfiltrate"
until 2026-08-12; the conclusion is unchanged and the premise is narrower.

**What would change this assessment.** If any of the following land, this section
must be re-derived rather than extended:

- A tool that reads or writes the filesystem outside ART_ROOT, or that fetches an
  arbitrary URL on request.
- Unattended or scheduled discovery with no curator in the session — this removes
  bounds 4 and 6 simultaneously, which are the two that depend on a human being
  around.
- Any credential becoming reachable from a tool.

> **Direction changed 2026-09-30 — the second trigger is now scheduled to fire.**
> `re-architecture.md` § Procurement adds **Watches**: standing searches that
> re-run discovery on a cadence with no curator in the session. Their result
> policy is notify, queue for review, or **auto-accept**.
> - A Watch set to **queue for review** removes bound 6 and leaves bound 4.
>   Nothing reaches the wall until a human sees it.
> - A Watch set to **auto-accept** removes both, and bound 4 turns into
>   detection after the fact.
>
> The per-Watch spending cap is a new instance of bound 1's control, and is
> welcome. It bounds cost, not content. **This section must be re-derived, not
> extended, in the plan that builds Watches, before any Watch runs.** That
> plan owes an answer to whether auto-accept is offered at all, and if so what
> replaces the human in `set_verdict`'s visible-ids bound. It is not re-derived
> here, because Watches have no design beyond the anchor doc yet.

### The fetch trigger fired — re-derived 2026-08-03

The first of those triggers has landed. Acquisition fetches the URL a `Source`
names, and it does so with a third-party binary whose input argument accepts a
local path as readily as a URL: probed at 2.18.1, `dezoomify-rs /etc/hosts` reads
the file and runs every parser over its contents, loopback addresses are attempted,
and `--bulk` will take its list of URLs *out of a file it reads*
(`dezoomify-cli-findings.md`). Those URLs originate in web discovery, which the
mechanism paragraph above establishes as attacker-influenceable.

**Bound 2 is re-derived rather than extended, per the rule above.** It no longer
rests on the capability being absent, because it is not. It rests on three
properties, and each is weaker than "the tool cannot do this":

1. **A fetch is reachable only through a URL a curator already accepted.** Nothing
   on the surface takes a URL as an argument; `retry_acquisition` re-fetches what a
   `Source` already holds, and a `Source` exists only because a verdict promoted a
   reviewed candidate. This is real but **not** a human URL audit — a curator
   approves a picture, not a hostname.

   > **Narrowed 2026-08-04, and it no longer holds as first written.** A tiled
   > fetch is now made against a URL **no record holds**: the provider is asked
   > where the object's image service is, and its answer is what gets fetched. So
   > the accepted `Source.url` bounds which *object* is fetched, not which
   > *address*, and a compromised or malicious provider response is a live path to
   > choosing one.
   >
   > What carries the weight instead is two checks, both in code and both tested:
   > the advertised IIIF base must start with the museum's own `https` host before
   > it is used (`library/sources/artic.py`, and the mutation sweep kills a version that
   > trusts whatever is advertised), and **bound 2 below runs on the resolved URL
   > rather than on the recorded one** — so scheme and routability are checked on
   > the address actually fetched. *(It read "re-runs … rather than only on the
   > recorded one" until 2026-08-04, which described a period when the recorded URL
   > was checked too. It no longer is on this path: gating a tiled fetch on a
   > provenance link nothing fetches recorded failures against innocent sources.
   > The property asserted here is unchanged — the fetched address is checked —
   > and it is now checked once rather than twice.)* A resolver that returned
   > `file:///etc/passwd` is refused before the binary is invoked, which is asserted
   > directly. Bound 1 is therefore weakened, and bound 2 is what now does the work
   > it used to share.
2. **Scheme and host are checked before invocation, not after.** `https`/`http`
   only, and the resolved address must be publicly routable — loopback,
   link-local, RFC1918 and `.local` are refused. This is what keeps a poisoned
   candidate from turning the loader into a probe of the operator's own LAN, which
   is the one asset on this network that a purely external attacker cannot
   otherwise reach.
3. **The binary never receives an unvalidated argument, and never a shell.** argv
   list, no shell, `stdin` at `/dev/null`, an explicit `--image-index` so no input
   path can reach an interactive prompt.

**Redirects are the door a host check normally leaves open, and it is closed.**
The check runs against whichever URL this path is about to fetch — the recorded
one on the direct-HTTP path this paragraph describes, and the *resolved* one on
the tiled path, per the amendment above. Either way it is one check, of one
address, before one fetch. A client left to follow redirects itself would let a
source answer a checked public URL with a `Location:` naming `127.0.0.1`,
reaching the operator's network through the one hop nobody validated. The transport therefore follows one hop at a time and puts every
`Location` through the same check, resolving relative ones first so the string
checked is the string requested.

**What this deliberately does not do is allowlist hosts.** `data-model.md` scopes
`source_class = contemporary_web` with an open provider vocabulary — galleries,
prize sites, artist portfolios — so a registry of permitted hosts would make every
new gallery a code change and would quietly re-scope the product. The check is
therefore on what a host *is* (publicly routable) rather than on which host it is.

**The honest residual.** An attacker who gets a poisoned candidate past a curator
can cause one authenticated-as-nobody GET to a public host of their choosing, from
the operator's network, and can have the response written to `ART_ROOT` as an
image. That is a worse position than before this chunk and it is not reduced to
nothing by any of the three properties above. It stays acceptable for the same
reason the rest of this section does — one principal, a private overlay network,
no PII, no tenancy, no payment surface — and it is recorded here rather than
implied so that a future reader weighing a fourth trigger starts from the real
baseline.

### Plugins read pages a search cited — re-derived 2026-10-05

The fetch trigger has a second, narrower form. Phase 2 now hands every finder the
pages the run's web search read (`ImageQuery.pages`, `source-plugins.md` § Pages
a search read), so a plugin may read a page **before any curator has accepted
anything**, at an address the open web chose. Before this, a plugin read only
addresses it built itself: its own host, from a work's title or Wikidata item.
The owner approved this on 2026-10-05, for gallery works, which have no other
route (`build-plan-ask-pages.md`).

**Bound 2's first property no longer covers plugin reads.** "A fetch is
reachable only through a URL a curator already accepted" still holds for every
fetch Arrt itself makes, acquisition included. It never covered a plugin's own
requests, which are unguarded (§ Source plugins), and now those requests can
reach an address taken from search results. What bounds them instead:

1. **Only the search's citations.** The pages are what the search engine read,
   never an address in the model's answer (`phase_one.py`, `_cited_pages`), so an
   injected instruction to *name* an address reaches nothing. An attacker has to
   get their page into the search's results, and then the page they control is
   the one read, which they could have served to anyone.
2. **Arrt checks each address before a plugin sees it**, with property 2 above
   (`check_fetchable`, in the runner): http(s), publicly routable, no `.local`
   name. A citation naming the operator's LAN never reaches a plugin. A plugin's
   redirects and later requests are its own, and unguarded. So is its own lookup
   of the name: an attacker who controls a cited host's DNS can answer Arrt's
   check with a public address and the plugin's connection with a LAN one (DNS
   rebinding). The read is a GET whose answer is parsed for a gallery's markup and
   never returned to the attacker, so it can reach a LAN service but not read it
   back; accepted on the same grounds as § The fetch trigger fired's residual.
3. **A plugin reads only pages of a shape it recognises**, on that page's own
   host (`docs/source-plugins.md` § A finder). This is the plugin's property, not
   Arrt's: it holds for the plugins in this deployment and is what their reviews
   check.
4. **What a plugin reports still stops at review.** Its title, artist and image
   address are outside text (§ Source plugins), judged by the identity check, and
   nothing is fetched by Arrt until a curator accepts the work. The Artlogic
   plugin reports images only on Artlogic's asset host, so an injected page cannot
   name an arbitrary image to fetch.

**The honest residual.** An attacker who gets a page into an Ask's search
results can have a plugin GET that public page (or, through rebinding, a LAN
address, blind), and, if it is shaped like a page
the plugin reads, steer which image is offered for review. That is the realistic
worst case § Prompt Injection already names, now reachable one step earlier, and
it still stops at the curator. Each Ask is started by a person, so bound 6 is
unchanged; Watches would remove it, and their plan must re-derive this.

## Content Appropriateness

**This is a safety concern, not a security one, and it is the one with a real
victim.** It is documented here because nothing else owns it.

Discovery searches the open web, so a mis-aimed intent or a poisoned page can
surface work that is explicit, disturbing, or simply wrong for a living room. The
consequence lands on the household persona — **people with no interface, who never
opted in, and who see whatever is on the wall.**

It fires without an adversary. An honest search returning honest results the
curator would not have chosen is the common case; prompt injection is the rare one.

**The control is the review gate, and its content is that the reviewing surface
shows the image.** Not that a surface is withheld — that framing was tried and
voided. Every surface on which a work can be accepted must display the image
first, including an agent's.

Two things follow that must not be traded away later:

- **A curator accepting on a title and a rationale alone is this control's failure
  mode, not its mitigation.** An MCP tool result that returns candidate metadata
  without the thumbnail defeats the gate while appearing to honour it. This is
  precisely why candidate thumbnails are returned inline as image content blocks.
- **The gate must not be relaxed on convenience grounds.** The spend argument for
  relaxing it is void anyway — spend is already capped by a stronger control — so
  any future proposal to skip review is trading the only protection the household
  has for a saved click.
- **What the MCP surface can and cannot enforce, stated exactly (added
  2026-07-20).** Returning the thumbnail inline guarantees that the *model* saw
  the image and that it is present in the transcript at the moment of acceptance.
  It cannot guarantee a *human* looked — rendering depends on the client, and
  looking depends on the curator. So the gate has two strengths: the web UI
  enforces "a human saw it"; MCP enforces "it was there to see". This is the same
  shape as bounds 4–6 under Prompt Injection — visibility, not refusal — and is
  recorded so the product brief's success criterion is not read as a stronger
  guarantee than the surface can carry. A backstop is filed as backlog work, not
  committed design: a "recently accepted over MCP" shelf in the curation UI, so
  everything accepted agent-side gets a guaranteed second human look on the next
  visit.

## Data Privacy

Almost nothing to say, which is itself worth recording so a future reader does not
assume it was overlooked.

- **No PII.** No accounts, no user records, no analytics, no telemetry leaving the
  device. One operator, no personal data about anyone.
- **No third-party data sharing.** Data flows outward only to OpenRouter (prompts
  and, for mat colour, artwork thumbnails) and to museum APIs (ordinary requests).
- **Artwork thumbnails go to a model provider.** Worth noting rather than hiding:
  mat-colour selection sends a downsized artwork image to OpenRouter. The images
  are public museum works, so the disclosure is nil, but the data flow is real and
  should not be discovered later as a surprise.
- **Logs must not contain secrets.** The one live rule in this section, and it has
  teeth because the repo is public and log excerpts get pasted into issues. Owned
  by `observability-strategy.md`.

### The one exception: the operator's own words

**`ConversationTurn.text` is the product's only retained free-text record of a
person**, and "no PII" above is true of everything else and not of it. Nobody
else's data is in it; it is still the one store where a curator may reasonably
want something gone, and it is retained deliberately — `data-model.md` records
that affinities are derived and the derivation will improve, which is worthless
without the turns to re-derive from.

### Deleting a conversation

*Ruled by the operator 2026-08-12. This closes issue #118, which
`information-architecture.md` § Open questions had held at `stage: requirements`
with three candidate rules.*

**Deleting a conversation deletes its turns and nothing else.** The rule in one
line: **deletion does not flow to what was derived from the thread.** Every row
citing a turn keeps its own record and loses only the citation —
`Affinity.source_turn_id` and `SpendRecord.conversation_turn_id` are set null.

The two rows are nulled for different reasons, and both reasons matter:

- **An affinity is a judgment, and the judgment is the product's memory of the
  curator.** It is accumulated across conversations by design and cannot be
  reconstructed from a thread that no longer exists. Cascading would mean deleting
  a six-month-old transcript quietly resets what the product knows about its
  operator's taste — a consequence no confirmation could state in a way anyone
  would predict.
- **A spend record is a ledger entry, and a ledger must not change retroactively.**
  Q4 asks what was spent and on what. Cascading makes a month total *fall* because
  somebody tidied — a number that lies about the past, which is worse than a
  number with a gap in its provenance.

**What the delete does cost is real and is not recoverable:** the ability to
rebuild those affinities when the derivation improves. The confirmation says that
in those terms.

**Two consequences the builder must not resolve on their own:**

- `api-contract.md` § `art_taste` requires a `source_turn_id` for
  `derivation='inferred'`. That is an invariant on the **write path**, not a
  stored constraint — enforced as the latter it makes this delete impossible.
- `Affinity.rationale` is now **required** for `inferred` and `observed`
  (`data-model.md`), because after a delete it is the only surviving evidence.

**No other deletion in the product has this shape**, and the difference is worth
naming so the rule is not generalised: archiving a work keeps the row and moves it
out of circulation, and deleting a theme is refused while it is hung. This is the
only place where a record is genuinely destroyed at the curator's request, which
is precisely why the things standing on it are detached rather than destroyed
with it.

## Abuse Prevention

**Not applicable, deliberately.** There is one principal on a private overlay
network. There is no registration, no untrusted user input, no shared resource to
exhaust on anyone else's behalf, and no rate limiting because there is nobody to
limit. The only "abuse" vector is an unbounded agent loop spending money, which is
handled as a cost control (`nonfunctional-requirements.md` § Direction), not as an
abuse control.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** Two footnotes
> apply once the Player surface exists, and neither reverses "not applicable".
> - **Players poll**, at about 1 s per wall. That is a handful of requests per
>   second across a household, from known devices: load, not abuse.
> - **A Watch is a new way to spend without a person.** Its per-period spending
>   cap is a cost control under the same norm, not a rate limit.

## Supply Chain

**Curation's CPython does not come from Debian.** The 2026-07-20 interpreter
decision installs a uv-managed standalone build (`uv python install 3.14`), because
Trixie ships 3.13 and `3tears` requires 3.14. The security consequence is a
patching one, not a trust one: **`apt upgrade` does not patch curation's
interpreter.** CPython fixes reach it only via `uv python upgrade`, on Astral's
republish cadence rather than Debian's security cadence. The procedure is in
`operational-spec.md` § Routine Operations; the point recorded here is that a
CPython CVE is now a two-plane action where an operator would reasonably assume one.

The display plane is unaffected — it runs the system 3.13 and is patched by `apt`
like anything else.

> **Direction changed 2026-09-30 — see `re-architecture.md` § Deployment
> target.** From wave 3 the server runs as a container on the operator's NAS.
> - Its CPython and its wheels come from the **image**, built from this
>   repository and pushed to a LAN registry. Patching it therefore means
>   **rebuilding and redeploying the image**, not `uv python upgrade` on the Pi.
>   The two-step caveat above stays true for as long as curation runs on the Pi.
> - The image's base and its build are a new link in the supply chain. They are
>   the same trust class as the PyPI wheels accepted above, and like them, no
>   pinning or provenance policy has been decided.
> - The Player stays on the Pi's system interpreter and `apt`, unchanged.

This is a narrowing of an already-accepted surface rather than a new one. Both
planes install PyPI wheels into venvs, which is a far larger volume of third-party
code than the interpreter, and that was accepted when the dependency set was
chosen. No dependency pinning or provenance policy has been decided — for a
single-principal LAN appliance that is a defensible position, but it is a position,
not an oversight.

> **Amended 2026-10-03: source plugins** (`source-plugins.md`, § Source plugins
> below). An installed source plugin and its dependencies are the same trust
> class as the PyPI wheels above, installed by the operator into the server's
> venv. A private plugin adds a derived image (`deploy/README.md` § A private
> source plugin) as a link after Arrt's own. That recipe constrains the install
> to Arrt's locked versions, which keeps Arrt's dependencies as they were tested.
> It does nothing for the plugin's own, and no pinning or provenance policy is
> decided for them either. *The owner's ruling* is that plugins load in-process
> (`re-architecture.md` § Sources are plugins). Classing them with the wheels is
> mine.

## Source plugins *(2026-10-03)*

**Installing a source plugin trusts it with everything Arrt has.** A plugin is a
Python package loaded into Arrt's process (`source-plugins.md` § Loading). Arrt
neither vets nor sandboxes it. *The owner chose* this over a separate service,
which would have isolated it, and accepted the trust that comes with it.

**What installing one trusts, concretely:**

- **Its code, and its dependencies' code, runs as Arrt**: same process, same
  user, same container. It runs at startup, when the module is imported (before
  its factory can decline), and on every call after.
- **It reaches what Arrt reaches.** That is:
  - the catalogue and the art tree, to read and to write;
  - the whole environment, the OpenRouter key included (`SourceContext.environ`
    is a read-only copy, and `os.environ` is there regardless);
  - the clients' token verifiers, which are hashes in the catalogue, not the
    tokens;
  - the network from inside the container, the house's LAN included.
  "A plugin writes nothing" is what the interface lets it say, not a barrier.
- **Its own requests are unguarded.** `check_fetchable` and the redirect checks
  (§ The fetch trigger fired) run on what Arrt fetches. A plugin's search,
  preview and page reads are made by the plugin's own client, and nothing stops
  one addressing the LAN. The one exception is the addresses Arrt hands it: the
  pages a run's search cited are checked before a plugin sees them (§ Plugins
  read pages a search cited).
- **Its dependencies can replace Arrt's.** They install into the same venv.
  Measured 2026-10-03: without a constraint, a plugin requiring `httpx<0.28`
  downgraded Arrt's locked httpx, and the image built cleanly. The derived-image
  recipe constrains the install to Arrt's lock, so such a plugin fails the build
  by name.
- **Its name.** Two installed distributions with one name load neither
  (`library/sources/loading.py`). So a plugin cannot take over a built-in's rows
  by taking its name, but installing one with a clashing name turns the
  built-in off. The health panel says so.

**What still holds, because Arrt keeps it rather than trusting a plugin to.**
Against a well-behaved plugin these are the boundary, and against a malicious
one, which has the access above, they are not:

- **A plugin's text is outside text.** Titles, artists and descriptions reach the
  page as text (§ Direction), and the model under § Prompt Injection's bounds,
  the same as a museum's.
- **Arrt fetches every locator a reader returns**, after bound 2 on the URL in
  the locator (§ The fetch trigger fired). The Art Institute's reader also checks
  that its advertised IIIF base is the museum's own host, and that check is the
  plugin's. The Met's reader returns an image only on `images.metmuseum.org`,
  and its finder reads image heads and previews only there, also the plugin's
  checks. SMK's reader returns an image only from `api.smk.dk`'s download and
  thumbnail paths, and its finder reads previews only from `iip-thumb.smk.dk`
  or that thumbnail path, again the plugin's checks. A third-party reader's locator gets bound 2 only: any public address.
- **Arrt decides** a work's identity, its rights record, duplicates, review,
  quality, spending and storage. A plugin answers "what images exist, and where".
- **A plugin's error text is scrubbed** before the journal and the health panel.
  Every URL's query string is cut, found by running to whitespace, `"`, `<` or
  `>`, the characters an HTTP client always encodes. The scrub runs past `'` and
  `\`, which httpx leaves in a path and a query as they are (`O'Keeffe`), and a
  test checks every character httpx leaves unencoded, read from httpx itself. So
  `?q=van gogh&key=…` written raw would keep everything after the space, while an
  encoded URL, which is what an HTTP client's own error carries, has no space in
  it. *Mine*, accepted at review rather than built: no plugin here logs a raw
  URL, and `docs/source-plugins.md` tells authors not to.

**Why this is accepted.** One principal, who installs the plugin, on a LAN
appliance with no PII, tenancy or payment surface: the same reasons as
§ Supply Chain. **What would reopen it** (mine): a plugin from someone the operator does
not know, or a plugin that holds a credential of its own that it must not share
with Arrt. Either calls for the separate service the owner declined, not for a
check inside the process.

## Registry text *(2026-10-01)*

**The exposure.** The Artist page shows what Wikidata says about an artist:
descriptions, movement and work titles, collection names, and image URLs.
Anyone can edit Wikidata, so every one of those is attacker-influenceable text
arriving in the curator's browser, by a channel (`architecture.md` channel 9)
that no model reads, so the prompt-injection bounds above do not cover it.

**What bounds it, as built** (`build-plan-ia-foundations.md` Chunk 04):

- **Text is rendered as text, never as markup.** Every registry string reaches
  the page through `el`'s `text`, which sets `textContent`; a browser test feeds
  the page a description carrying an `<img onerror>` and asserts it arrives as
  words and runs nothing (`tests/browser/test_the_artist_page.py`).
- **An image URL is a Commons file or nothing.** The client keeps only
  `https://commons.wikimedia.org/wiki/Special:FilePath/…` and drops anything
  else the registry offers as an image, before it reaches an `img` source
  (`tests/unit/test_wikidata_client.py`); the page loads it with no referrer.
- **Links out are built from a checked QID**, never from a URL the registry
  supplied.
- **The server asks one constant endpoint and follows no redirect**, so nothing
  the registry says can steer a request at the operator's network.

**Now a norm.** These were properties of one page, enforced by its tests. Since
2026-10-01 they are § Direction, which binds every page that shows outside text,
one-world search first.

## Open

- **Licence and rights enforcement — no longer open; this entry had gone stale.**
  Decided 2026-07-20: rights gate nothing. `rights_status` is a display-only
  provenance and source-quality signal, with named reopen triggers (sharing,
  export, or the catalogue becoming public). Decision and rationale live in
  `data-model.md` constraint 13; this entry is corrected rather than deleted
  because a reader of this document alone would have re-opened a settled question.
- ~~**Whether TV auto-update can be disabled.**~~ **Closed 2026-08-04: it can be,
  and it is.** Not strictly security, but it is the vendor-controlled capability the
  whole product rests on, and Samsung has already removed art mode from some units.
  The set is held at firmware 1310 with 1400 offered and declined; the standing
  recommendation is to stay there, because the update is one-way and every measured
  fact about this television is firmware-scoped. Reasoning, consequences and the
  re-verification path live in `operational-spec.md` § Risks — not restated here,
  because the version numbers will move and one home for them is enough.
- ~~**Opened 2026-10-01: a norm for showing external text in the browser.**~~
  **Closed 2026-10-01: ratified by the owner, and written as § Direction.** It was
  owed before one-world search (`build-plan-one-world-search.md`) ships, and is
  that plan's Chunk 01.
- **Opened 2026-09-30:**
  - **Player authentication on the LAN.** Closed 2026-09-30: a per-wall token
    (§ Trust Boundary, the note on the re-architecture); a per-client token
    since 2026-10-02.
  - **The re-derivation of § Prompt Injection for Watches.** Owed by the plan
    that builds them, before any Watch runs unattended.

  Both are tracked by `re-architecture.md` § Open questions until backlog items
  are filed.
