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
  | owner, 2026-10-08 | owner can veto] *(Chunk 02: search reaches the LAN
  instance without either; they are the fetch transport's, for `web_fetch`.)*
- [ASSUMPTION: no SearXNG instance exists yet — none is found in the operator's
  homelab repo — so web search is optional and off until one is deployed and
  configured by URL | MED impact | owner can point to one] **Overturned
  2026-10-08:** one runs on the operator's NAS, and Chunk 02 measured with it.
  Web search stays optional, configured by URL.
- [ASSUMPTION: the agent gets no display tools (`art_display`) in this wave;
  changing what is on a wall from Ask is a later decision | MED impact |
  owner can include them]
- [ASSUMPTION: Get stays free and starts without asking, like any other tool;
  the agent offers works and Get is an act on the card the curator presses,
  not something the agent does on its own | MED impact | owner can let the
  agent get works itself]

**What would raise it:** chunk 02's numbers.

## Outside this repo

- **3tears: granular spending caps, at the app and feature level.** The owner
  ruled that they live there. Filed as pacepace/3tears#583, an ask for an
  investigation and a strategy rather than a proposed fix.
- **3tears: agent-tools' memory, audit and NATS client as optional extras.**
  Filed as pacepace/3tears#582. Not blocking: Arrt accepts the couplings.
- **A SearXNG instance**, deployed beside the server, recorded in the
  operator's private homelab repo.

## Status

- [x] Chunk 01: The requirements say what the owner ruled
- [x] Chunk 02: Measure cheap models on Ask-shaped requests
- [x] Chunk 03: Ask is one thread with an agent in it
- [x] Chunk 04: Retire the conversation, the direct box and the commit seam

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

**Recorded at the chunk (2026-10-08):** the measurements, N, requests and both
decisions are in `ask-agent-findings.md`. In short:

- **Default model: `anthropic/claude-haiku-5.5`** (decision, owner can veto):
  every request passed, 3 steps at most, about $0.003 and ~15 s a reply.
  `qwen/qwen3.7-flash` was as reliable, cheaper and three times slower;
  `deepseek/deepseek-v4-flash` ran into the call budget on open requests.
- **Step limit for 03: 8 model replies** per curator reply (decision, owner can
  veto), from observed maxima of 3 (haiku) and 7 (qwen).
- **No model used web search in 55 runs.** Whether 03 ships it enabled is
  left open in the findings.
- **The MCP surface gained six read-only registry actions on `art_discovery`**
  (`search`, `find_topics`, `artist`, `similar_artists`, `work`, `topic`), each
  its route's twin field for field (`test_registry_tools.py`); `api-contract.md`
  records them. `artist` on a held artist answers with their works rather
  than "held" (`ArtistService.works_by_qid`).
- **What 03 inherits from the harness:** the agent is offered whole tool
  definitions and an action outside its scope is answered with a teaching error
  and never run (`driver.py` `_outside`); the draft prompt and scope are
  `ASK_SYSTEM` and `ASK_SCOPE` in `arrt/tests/eval/ask.py`. 03 moves them into
  the server and keeps the eval pointing at them.
- **Assumptions this overturned:** a SearXNG instance exists (the operator's
  NAS), so the no-instance assumption above is stale; and the search half of
  3tears' web search needs no `allow_private_addresses`, which belongs to the
  fetch transport only.

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

*Ticked 2026-10-09 with the last clause outstanding:* the owner's use waits on
the deploy, and `operator-verification.md` § Ask as an agent holds it as
pending until then. That entry, not this box, is the record of it.

**Stated at the chunk, before code (2026-10-08).** Decisions are the agent's,
each one the owner can veto:

- The owner confirmed the default model, `anthropic/claude-haiku-5.5`
  (2026-10-08). It is set by `ASK_MODEL`. The step limit is 8 model replies,
  set by `ASK_STEP_LIMIT` and enforced by LangChain's
  `ModelCallLimitMiddleware(run_limit=…, exit_behavior="error")`, which counts
  model calls exactly. `recursion_limit` counts graph steps instead.
- [DECISION: the stream is NDJSON, one 3tears `StreamEvent` per line, on the
  `POST` that sends the curator's words. The plan said SSE, but a browser
  cannot open an `EventSource` on a POST, so SSE would be parsed by hand over
  `fetch` either way. The client already reads a line-streamed answer
  (`apiLines`, the Topic page's works), so this reuses it rather than adding a
  second framing. The events are 3tears' own, unchanged: `stream_start`,
  `stream_token`, `tool_call_start`, `tool_call_end`, then `stream_end` or
  `stream_error`. The lifecycle is driven by hand, not by `run_graph`:
  `run_graph` emits no tool events, and its `end()` cannot carry the reply's
  cost | agent | owner can veto]
- [DECISION: cards are the works, artists and topics **the answer names that
  a tool returned**, not everything a tool returned. A registry search returns
  dozens of items, and the answer is where the agent chose among them. A QID
  the answer names that no tool returned gets no card, so an invented item
  cannot be offered for Get. The cards travel on `stream_end.metadata`, built
  on the server from the tool payloads by one function that the eval's
  scorer also reads | agent | owner can veto]
- [DECISION: web search is offered when `SEARXNG_URL` is set and is absent
  otherwise. The owner ruled that the agent may search and that SearXNG is
  free, and an unused tool costs only its definition | agent | owner can
  veto]
- [DECISION: a reply's cost is shown under it and logged, and no
  `SpendRecord` is written. The sidebar's month figure is the provider's own,
  so it already includes Ask, and a per-reply record belongs with the 3tears
  spending cap (pacepace/3tears#583) | agent | owner can require one]
- [DECISION: a thread is opened when the curator first sends words, not when
  Ask is opened, because loading a page must write nothing (the UX walk's
  refused-on-load check caught the first version) | agent | owner can veto]
- Asking the agent is Ask's one filled act. The direct *Get* stays, unfilled,
  until chunk 04 retires it.
- In this chunk the thread sits on Ask, above the direct box and the
  conversations. Chunk 04 removes those, so nothing here deletes them.

**Cross-cutting, the loop (a new execution context):**

- *Where it runs:* on the server's event loop. Each tool call goes to
  `mcp.server.dispatch` on a worker thread, the way the MCP surface already
  calls it, because the service layer is synchronous and one call can hold
  for 45 s. The agent is a third thin binding: it is offered the MCP
  definitions whole, and an action outside `ASK_SCOPE` is answered with a
  teaching error and never dispatched.
- *Bounds:* model calls per reply (the step limit); one reply in flight per
  thread, so a second send while one runs is refused with a 409; at most 20
  threads kept in memory, the least recently used dropped first. Nothing
  persists, and a restart forgets every thread.
- *Failure:* no key means the reply is refused before anything is called,
  and says so. The step limit ends the stream with `stream_error` code
  `STEP_LIMIT` and a sentence for the curator; the text already streamed
  stays. Any other fault ends with 3tears' `AGENT_FAILED` and is logged with
  its traceback. A client that disconnects cancels the run, which ends with
  `AGENT_CANCELLED`.
- *Observability:* one INFO line per reply on `arrt.ask`: thread, steps,
  tool calls, cost and its uncosted replies, duration, and how the reply
  ended. Cost is OpenRouter's `response_metadata["cost"]`, summed.
- *Security:* only read actions are in scope. The agent cannot get, hang or
  change anything; Get is a press on a card. It is reached only through the
  curation plane's own HTTP surface, which has the same trust boundary as
  every other `/api` route.

**Cross-cutting, the stream surface (a new kind of response):**
`POST /api/ask/threads/{id}/replies` answers `application/x-ndjson`.
Refusals made before the stream opens (no key, an unknown thread, a reply
already running) are ordinary JSON errors with a status. Once the stream
opens it always closes with exactly one terminal event, which 3tears'
`StreamingResponse` guarantees. `GET /api/ask/threads/{id}` returns each
turn's events as they were sent, so a returning page repaints through the
same renderer that drew them live. The surface is internal to the browser
client and unversioned.

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

**Stated at the chunk, before code (2026-10-09).** Removing the stored turns
forces four decisions the plan did not name. Each is the agent's, and the owner
can veto it:

- [DECISION: a catalogue migration drops `conversations` and
  `conversation_turns`, and the two columns that cite a turn,
  `affinities.source_turn_id` and `spend_records.conversation_turn_id`, with
  their indexes. Dropping a turn already nulled both, so the migration only
  does to every row what deleting a conversation did to some. The owner
  ruled that old threads may go | agent | owner can veto]
- [DECISION: the `conversation_tokens` spend category stays readable, and
  nothing writes it any more. Its rows are money that was spent, and the
  month total and the ledger must keep counting them | agent | owner can
  veto]
- [DECISION: an `inferred` judgment can no longer be written, and the rows
  that exist keep their derivation and rationale. Its rule was that it cites
  the turn it was read out of. Ask's threads are not saved, so there is
  nothing to cite. In practice only the retired conversation could satisfy
  the rule, since an MCP client had no turn to name. The wave that saves
  threads decides how a judgment cites one. Until then `art_taste` loses
  `source_turn_id`, and a judgment's view loses `conversation_id` | agent |
  owner can veto]
- [DECISION: the box's routes stay: `POST /api/runs` with an intent, and
  `GET /api/estimate`. MCP's `art_discovery` and a Get's approval gate still use them.
  Only the browser's way into them from Ask goes. `#conversation/<id>`
  stops being a route, so an old bookmark lands where any unknown address
  does | agent | owner can veto]

**Found while building (2026-10-09).**

- **A requirement the retired code carried, moved to Ask.** The owner's
  ruling 3 of 2026-10-07 (#290) has a reply refused at the spending cap lead
  with "This month's budget is spent". The conversation met it through the
  OpenRouter client, and Ask's agent did not: a spent key ended a reply with
  "Ask could not answer: PermissionDeniedError." OpenRouter's 403 now ends an
  Ask reply with `stream_error` code `BUDGET_SPENT` and the same sentence,
  built by one function both callers share.
- **Two pieces of code the retirement left unreachable went with it.** The
  rule that a weaker provenance may not overwrite a stronger one has nothing
  to refuse once only `stated` is writable, and the order-of-magnitude caption
  under Ask's *Get* had no Get left to sit under.
- **The security model never covered Ask's agent.** Chunk 03 sent the
  curator's words to OpenRouter and SearXNG, and let web pages reach the
  model, without `security-model.md` saying so. § The curator's own words now
  does, in place of the retired exception for stored turns.
- **Ask's Screen States row asked for two or three worked examples on an
  empty thread. They were never built, for the direct box or for Ask**, and
  the row now says so rather than claiming them.
