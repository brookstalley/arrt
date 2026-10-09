---
artifact: build-plan
version: 1
scope: ask-agent
branch: feature/ask-agent
partition: serial — 02's measurements choose 03's model and tool set, and 04 retires what 03 replaces; nothing is independent enough to hand off.
depends_on:
  - artifact: product-brief
  - artifact: information-architecture
  - artifact: 3tears-integration-findings
governed_by:
  - artifact: product-brief
  - artifact: information-architecture
  - artifact: nonfunctional-requirements
  - artifact: data-model
  - artifact: architecture
  - artifact: api-contract
  - artifact: observability-strategy
  - artifact: project-preferences
last_validated: null
---

# Build Plan — Ask as an agent

## What this plan is

Ask today is half a feature. A conversation turn is one model call with no
tools, and its prompt forbids claiming a search, so it can only name artists
from memory. Committing throws the thread away: it starts a separate phase-1
run that sees one line of direction. Nothing reads Taste. A direct Get beside
it asks the curator to say, by button, what their words already say.

This plan makes Ask one thing: a conversation with an agent that has the
product's tools, searches as it goes, and answers with works, artists and
topics the curator can act on.

This is the first wave of a program. Saved threads, taste-aware prompting
and a wider tool set are later waves, each with its own plan when it starts.

**Owner rulings, 2026-10-08** (the owner's words, given in conversation):

- **Ask is an agent, and it may search as it talks.** "The product brief is
  wrong — the app exists to help people find art, artificial barriers around
  how people do that make no sense." This reverses product-brief flow 1's
  "Conversation forms intent; it does not perform discovery".
- **The agent may spend without asking.** No estimate is shown before a reply.
  What a reply cost is shown after it.
- **The spending cap belongs in 3tears**, so each consuming app does not
  re-implement it. Arrt does not build one.
- **SearXNG counts as free** web search, reached through 3tears.
- **Start with cheap models and measure them with evals.**
- **Threads need not be saved at first.** "Eventually yes, but to start
  proving the user experience nobody will care if old ones are just gone."

## Requirements Confidence

**Medium.** The direction is clear and ruled. What is not known:

- Whether the cheap models Arrt runs today use tools reliably enough. Chunk
  02 measures this before anything is built on it.
- What a reply costs once it is several model calls. Chunk 02 measures this
  too.
- How the tool results render as cards. Chunk 03 builds the first version,
  and the owner judges it by using it.

**Open assumptions:**

- [ASSUMPTION: until 3tears has a spending cap, each reply is bounded by a
  step limit (LangGraph's `recursion_limit`). This is not the ceiling, and does
  not need to be: `nonfunctional-requirements.md` § Direction puts the ceiling
  on the OpenRouter key and forbids app code from owning it, and its scope note
  allows a per-run cap in app code as budgeting. The 3tears cap is that kind
  | HIGH impact | owner can require the 3tears cap before 03 ships]
- [ASSUMPTION: the agent loop is LangChain's `create_agent` with
  `3tears-models` and the 3tears stream event types; nothing from 3tears that
  needs Postgres or NATS (checkpointer, conversations, agent-memory,
  agent-tools) | HIGH impact | owner can correct]
- [DECISION: tools come from `3tears-agent-tools` (`web_search` over
  SearXNG, later `web_fetch` and `analyze_media`), accepting that it declares
  agent-memory (pgvector), agent-audit and the NATS client as install
  dependencies. At v0.65 the tools Arrt uses import none of them at load and
  connect to neither NATS nor Postgres, and `3tears-langgraph` already brings
  core 3tears with asyncpg. Re-implementing the wrapper in Arrt would repeat
  the per-app re-implementation the owner ruled against for the spending cap.
  The coupling stays install-only by test, not by luck: chunk 03's guard. 3tears
  is pinned to an exact version. A SearXNG on the LAN is reached with
  `allow_private_addresses=True`, pinned to its one host by `allowed_hosts`
  | owner, 2026-10-08 | owner can veto]
- [ASSUMPTION: no SearXNG instance exists yet — none is found in the operator's
  homelab repo — so web search is optional and off until one is deployed and
  configured by URL | MED impact | owner can point to one]
- [ASSUMPTION: the agent gets no display tools (`art_display`) in this wave;
  changing what is on a wall from Ask is a later decision | MED impact |
  owner can include them]
- [ASSUMPTION: Get stays free and starts without asking, like any other tool;
  the agent offers works and Get is an act on the card the curator presses,
  not something the agent does on its own | MED impact | owner can let the
  agent get works itself]

**What would raise it:** chunk 02's numbers.

## Outside this repo

- **3tears: a spending cap for agent runs.** The owner ruled that it lives
  there. `3tears-search` already has the shape: `BudgetPort` checks an
  estimate before each call and records the spend after it, with scopes such
  as per-run. Model calls need the same. Not filed yet.
- **3tears: agent-tools' memory, audit and NATS client as optional extras.**
  Filed as pacepace/3tears#582. Not blocking: Arrt accepts the couplings.
- **A SearXNG instance**, deployed beside the server, recorded in the
  operator's private homelab repo.

## Status

- [x] Chunk 01: The requirements say what the owner ruled
- [ ] Chunk 02: Measure cheap models on Ask-shaped requests
- [ ] Chunk 03: Ask is one thread with an agent in it
- [ ] Chunk 04: Retire the conversation, the direct box and the commit seam

### Chunk 01: The requirements say what the owner ruled

Type: doc-only

Amend product-brief flow 1 with the rulings above, in the owner's name. Its
2026-08-10 amendment argues from two `data-model.md` choices: one batch per run
because a batch has a scope to estimate, and not holding the curator at the
keyboard. Re-read both, and the spend-ceiling language in flow 2, and record
what each becomes. The estimate before spending goes away for Ask. Rewrite the
Ask row and Flow 1 in `information-architecture.md`, including the "wizard in
costume" seam requirement, which no longer has a seam to protect. Record in
`3tears-integration-findings.md` that the 2026-08-02 reason for setting aside
`3tears-models` (install weight on the Pi) went when the server moved to the
NAS. Sweep the whole repo for the old wording before calling it done.

Dispositions known at drafting, to be confirmed in the chunk:
`nonfunctional-requirements.md` § Direction, provider-enforced ceilings:
conforms. The key's limit stays the ceiling, and a per-reply cap is budgeting
under its scope note. Its Cost visibility text (estimate before, actual after)
was deliberately not ratified as a norm; amend it so that Ask reports the
actual cost after, with no estimate before. Every other governing artifact
listed in the frontmatter gets a disposition line in this chunk.

**Dispositions, recorded at the chunk (2026-10-08):**

- `product-brief.md` flow 1: amendment proposed and made, in the owner's name,
  as a dated direction-changed note; the 2026-08-10 text stays true of what
  runs until 04.
- `information-architecture.md`, the Ask and Conversation rows and Flows 1 and
  2: the same. The seam requirement has nothing left to protect once 04
  retires the commit card.
- `nonfunctional-requirements.md` § Direction, provider-enforced ceilings:
  conforms. § Cost visibility (a requirement, not a norm): amended for Ask.
- `data-model.md` § Direction: conforms. No norm there governs conversations;
  the Conversation entity and the one-batch decision carry direction notes.
- `architecture.md` § Direction, operation logic only in the service layer:
  conforms, provided the agent is a third thin binding over the services that
  the MCP tools and HTTP handlers already bind. 03 must hold that.
- `api-contract.md` and `observability-strategy.md`: no Direction norm bears on
  this chunk. 03 owes the cross-cutting statement for the new loop and stream.
- `project-preferences.md`: no norm row bears on this chunk. Plane isolation
  concerns the display plane.
- `project-state.yaml` → `technical_decisions.technology`: a 2026-10-08 entry
  records the stack and where the operator's "no NATS" constraint stands.
- `3tears-integration-findings.md`, `openrouter-api-findings.md` and
  `ia-proposal.md` § Ask carry dated notes.

Done when: no live artifact says a conversation does not search, or that Ask
has two acts; each norm the change touches has a disposition; the root suite
(`tests/preferences/`, including the screen tables) is green.

### Chunk 02: Measure cheap models on Ask-shaped requests

**Foreign API:** OpenRouter tool calling through `3tears-models`;
`3tears-agent-tools` `web_search` over SearXNG.

0. verify-api: read `3tears-models`' current OpenRouter provider and the
   `create_agent` signature at the version to be pinned. The `eval` group pins
   `>=0.22.5,<0.23` and the remote is at 0.65, so exercise the existing driver in
   a clean interpreter on the new pin before anything else.

Extend the existing harness (`arrt/tests/eval/driver.py`, `llm_eval`) with
Ask-shaped requests. At least: a named body of work ("Salvador Dalí's early
work"); taste with exclusions ("I like Dalí and Warhol but not Haring, help me
find more"); a mood ("something calm for a bedroom"); and one the library
already holds. The harness drives the real MCP surface, so a tool the agent
needs and MCP lacks gets added there first. Registry search and the artist and
topic pages are missing today. Run the cheap models Arrt uses, one stronger
model, and SearXNG if an instance is available.

Record for each model and request: whether every tool call was valid; whether
the answer named real works the curator could get; how many steps it took; and
what it cost. Record N and the requests, so the numbers can be checked and
re-run.

Done when: the measurements are recorded in an artifact, a default model is
chosen from them and the choice recorded, and the step limit for 03 is set
from the observed step counts.

### Chunk 03: Ask is one thread with an agent in it

**Visual change:** yes. **Exposed API:** the Ask stream, internal to the
browser client — none versioned.

The agent runs in the server process, on the tools the MCP surface already
defines, called in-process rather than over HTTP. There is one definition of
each, and the MCP layer keeps it. Free tools run without asking. The thread
lives in memory and is gone on restart. Replies stream to the browser as 3tears
stream events over SSE: text as it arrives, a line for each tool call, and
cards for the works, artists and topics a tool returned, each showing whether
it is held and offering Get or a reaction. The reply's actual cost is shown
when it ends. Cross-cutting concerns for the new execution context (the loop)
and the new stream surface are stated in the chunk before code.

A guard test starts the agent and answers a turn with no NATS and no
Postgres reachable, so a 3tears release that turns the install-time coupling
into a runtime one fails here, by name.

Done when: the four requests from 02 work end to end in the browser; the
browser suite drives a thread against a stubbed model; a reply that hits the
step limit says so in the thread; the owner has used it.

### Chunk 04: Retire the conversation, the direct box and the commit seam

Retire the old conversation service, its routes, its client screen and its
stored turns. The owner ruled old threads may simply go. Affinities that point
at a conversation turn keep the judgment and drop the pointer, as deleting a
conversation already does. Also retire the direct intent box, the two buttons
and the in-place commit card. Grep for every caller, and for the screen-table
rows and tests scoped to them, before deleting.

Type: cumulative-final

Done when: nothing reaches the old conversation code; all three suites and
the browser suite are green; the cumulative review is clean.
