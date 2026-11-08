# Agents, memory and MCP — direction of 2026-11-08

The owner's direction of 2026-11-08 for how Arrt's agents remember, how a
household's own agents reach Arrt, and what a household installing Arrt may
choose. Where an older artifact disagrees with
this file about the **target**, this file wins. Where they disagree about **what
is built today**, the older artifact wins until the work below lands. Each
artifact this touches carries a dated pointer back here.

**Where it came from.** A research pass read Arrt and the owner's 3tears
framework (0.65.0 pinned here, 0.89.0 checked out) to ask whether 3tears' agents
and memory should improve discovery and Ask. What it found, read from the code:

- Arrt already stores the curator's taste, typed, in SQLite (`Affinity`,
  `data-model.md`), and **no agent reads it**: Ask's scope excludes `art_taste`,
  and discovery's phase 1 is sent only the intent, so works the curator has
  rejected are dropped after the model was paid to propose them.
- 3tears' agent memory, knowledge, intention and skills packages all need
  Postgres with pgvector and a paid embedding provider. Its scheduled jobs need
  NATS and a Postgres store. None runs on SQLite.
- Arrt's storage is isolated: every SQL statement is under
  `arrt/src/arrt/persistence/` (about 7,200 lines, four modules import `sqlite3`),
  and the lower layer, `durable.py`, is shaped on 3tears' `DurableStore` on
  purpose. The SQL above it is SQLite's dialect (`COLLATE NOCASE`, `rowid`,
  `PRAGMA`, `VACUUM INTO`, hand-written `ALTER`/`DROP COLUMN` migrations).

## The owner's rulings

The advisor's recommendations, and the owner's reply to them, "Good recs. Yes to
all", plus what the owner added in their own words:

1. **Ask knows the curator's taste.** "Yes ask should know taste." Ask reads the
   stored affinities, and records taste the curator states to it. Discovery's
   phase 1 is told the taste too.
2. **Fencing tool results is reasonable, and not a huge concern.** "fence is
   reasonable but not a huge concern." Ask's tool results get 3tears' installed
   `fence` module; it is the last item below, not the first.
3. **Arrt is meant for other households, each running its own instance, and
   each chooses whether to run Postgres.** "Arrt is meant for other households,
   and they should be able to adopt postgres or not." Clarified the same day:
   "Other households will not use our instance of arrt; the source is public and
   they can run it themselves. Our security boundary remains the lan and single
   household within lan." So an installation is still one household, and its
   trust boundary is still its LAN.
4. **MCP is the extension point.** "Mcp is important." A household may bring its
   own agents and their memory, outside Arrt, and reach its Arrt over MCP from
   inside its LAN.
5. **Unattended agent work runs inside Arrt, behind settings, because it spends
   with nobody watching.** "Unattended agent work should be in arrt I think, but
   that needs settings since it can burn tokens unattended."
6. **A public Arrt server may come later: anonymous Players only, no agents.**
   "we might run a public arrt server that only allows anonymous players to
   connect, but not with any kind of ask or agentic capability. This is not soon,
   but a design consideration." Then, of what it serves: "it's the apple tv
   case… those players will connect to get art, but no web UI or MCP is exposed,
   only the public art themes and artwork." It is `feeds-and-players.md`'s public
   channels (case b: anonymous feeds, control off), served by a running Arrt
   rather than only as static documents.

`[DECISION: a public deployment serves only the public themes' feeds and their
artwork. The web UI, its API, MCP and everything agentic (Ask, discovery's model
calls, unattended work, memory) can be absent from it, not only switched off in
its settings | ruling 6: a public server is outside the LAN
boundary rulings 3 and 4 rest on, and a capability that is present but disabled
is one setting away from being exposed to anyone | user can veto/override]`

Ruling 6 builds nothing now. It is a constraint on items 1–6 below: none of them
may make a feed, its media or a Player's routes depend on the web UI, MCP, an
agent or a model key being present.

`[DECISION: the catalogue stays on SQLite for every household; Postgres is an
optional addition that turns on memory features and holds only them | the
advisor's recommendation the owner accepted ("Yes to all"), weighed against a
second full backend: every schema change and migration would be written and
tested twice, for ever, and CI would run the suite against both, while SQLite
already serves one household well. Ruling 3's "adopt postgres or not" is met by
Postgres being optional, not by the catalogue running on it | user can
veto/override]`

`[DECISION: Arrt's own memory is typed and lives in the catalogue (taste, the
curator's verdicts and rulings); free-text and semantic memory is either the
optional Postgres layer's or the household's own agent's, over MCP | Arrt's
typed taste model answers "what does this household like" better than free-text
memories over a few dozen rows, and needs no new infrastructure | user can
veto/override]`

## What this reverses or reopens

- **`product-brief.md` § Out of scope.** "3tears agent memory … dropped rather
  than deferred" is reopened: memory becomes optional (ruling 3). The other rows
  stand: an installation is one household, and MCP's consumers are that
  household's own agents, which the MCP surface has always served.
- **Who installs Arrt.** The brief describes one operator's appliance. Other
  households installing it from the public source makes installation and
  configuration a requirement: Postgres optional, unattended work off until
  chosen, nothing in the defaults that assumes this household.
- **`product-brief.md` § Users & Personas.** One operator per installation still,
  but many installations.
- **`feeds-and-players.md` § Public channels.** Ruling 6 adds a running public
  server as a way to publish them, beside static hosting. Not soon; its own
  requirements cycle when it comes, including its own trust boundary.
- **Not reopened: `security-model.md` § Trust Boundary.** The application still
  performs no authentication; the LAN and the one household on it are the
  boundary (ruling 3's clarification). An agent the household brings reaches
  `/mcp` from inside that LAN, as the household's MCP clients do today.
- **`data-model.md`.** Conversations and affinities were modelled on 2026-08-10;
  verdicts becoming taste, and stated taste, add writers to `Affinity`.
- **`api-contract.md`.** Ask's scope was read actions only, and `art_taste`'s `set`
  refuses `observed`. Ask gains a `stated` write (ruling 1), and review becomes the
  path that writes `observed` (item 2).
- **`nonfunctional-requirements.md`'s spend norm.** The monthly cap stays the
  ceiling. Unattended work needs its own allowance under it (ruling 5).
- **`re-architecture.md` § Order of work, wave 6+.** Watches are the first
  unattended agent work; their scheduler is built in Arrt, behind ruling 5's
  settings.

## Order of work

Each item gets its own build plan when it starts, as the waves did.

| | Scope | Notes |
|---|---|---|
| **1** | **Taste in Ask and discovery** | Ask's system prompt carries the household's affinities; Ask records taste the curator states, through the same service `art_taste` calls; phase 1's prompt carries taste and the works already rejected. No dependency, no infrastructure. |
| **2** | **Verdicts become observed taste** | Accept and reject in review write `observed` affinities, at the owner's thresholds (open question 1, answered 2026-11-08: at least 5, and at least 90% of the verdicts, each way, by artist). `inferred` writes stay off. |
| **3** | **MCP for the household's own agents** | `art_taste` writes for stated taste and verdicts, and whatever else a household's agent needs to do through MCP what Ask does inside Arrt (open question 5). No credential: the boundary stays the LAN. |
| **4** | **Unattended agent settings, then Watches** | Settings: whether unattended agent work runs at all, its own monthly allowance under the cap, its cadence and its model. Then Watches, in Arrt, with what they write tagged as written unattended (input to the prompt-injection review Watches owe). The scheduler itself is shared with upgrades (`upgrades.md`), which call no model, so it is not held back by this item; only agent work behind it waits for the settings. |
| **5** | **Optional Postgres for memory** | Off unless a Postgres address is configured; Arrt works fully without it. Brings 3tears' agent memory (and the 3tears pin from 0.65 forward), an embedding provider's cost, and its permission bundle. Built only when items 1–4 leave a memory need typed taste does not meet. |
| **6** | **Fence Ask's tool results** | 3tears' `fence`, already installed; recorded in the security model as a weak bound, not a defence. |

## Open questions

1. ~~At what thresholds do verdicts become observed taste (how many rejections of
   an artist, a style, a period)?~~ **Answered 2026-11-08 (the owner): "it should
   be at least 5, but with at least 90% rejections (100 approvals and 5 rejections
   is fine)".** Review's verdicts write an observed dislike of a thing only when
   both hold: at least 5 of its works were rejected, and rejections are at least
   90% of the accept-and-reject verdicts on its works. 5 rejected beside 100
   accepted writes nothing. **The rest, ruled the same day** on the advisor's
   recommendations ("yes, and even artists that are asked for and approved seem
   like taste. agreed on others"):
   - **Approvals write an observed like by the mirror rule**: at least 5 accepted,
     and accepts at least 90% of the verdicts. Approvals from a run whose request
     named the artist count too (the owner overruled the advisor's exclusion). An
     observed like is `likes`, never `loves`, which only the curator states.
   - **Counted by artist only.** A proposed work records its artist's name and
     sometimes its Wikidata item, never its movement or era.
   - **An observed judgment never overwrites a `stated` one.**
   - **An observed dislike is `declines` with `open_to_more` false**; an observed
     like is open to more.
   - **An observed judgment is removed when its rule stops holding**, so it
     always reflects the verdicts as they stand.

   `[DECISION: approvals count even when the request named the artist | the
   owner: "even artists that are asked for and approved seem like taste". The
   advisor's concern, recorded so it can be revisited: a learned like steers
   phase 1 toward that artist, whose works are then approved, which strengthens
   the like, narrowing discovery over time | user can veto/override]`
2. May anything a Watch finds while nobody is watching shape taste or a later
   prompt, or only what the curator accepts?
3. Is the monthly spend cap still meant to come from 3tears, which at 0.89 has
   none for OpenRouter?
4. How is the 3tears pin moved: on a schedule, or only when a needed piece moves?
5. What does a household's own agent need over MCP that the six tools lack
   today: taste writes certainly, and what else?
6. A public server (ruling 6): is it the same codebase in a public mode, or a
   separate feed server built from the contract package? Not needed until it is
   planned; its answer decides how "absent" is implemented.
