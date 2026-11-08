---
artifact: build-plan
version: 2
scope: taste-in-ask
branch: feature/taste-in-ask
base: develop
working-branches: []
last_validated: 2026-11-08
depends_on:
  - artifact: agents-and-memory
  - artifact: data-model
  - artifact: api-contract
  - artifact: security-model
partition: serial — both chunks read the same taste brief, which Chunk 01 writes
---

## Goals

**Response taken:** Proceed, citing it — `agents-and-memory.md` ruling 1 and
item 1 of its order of work, which the owner ratified on 2026-11-08 ("Yes to all").

**Product:** Arrt already stores the curator's taste (`Affinity`), and no agent
reads it. After this plan, Ask's system prompt carries the household's taste.
Ask records taste the curator states, through the service `art_taste` calls.
Discovery's phase 1 is told the taste and the works already rejected, so the
model is not paid to propose them again.

**Constraints:**
- No new dependency and no new infrastructure (the item's own words).
- Ruling 6: nothing here may make a feed, its media or a Player's routes depend on
  an agent or a model key. Both chunks touch only Ask and phase 1.
- Item 2 is not in scope. Verdicts do not write `observed` taste here; open
  question 1 (the thresholds) is the owner's and still unanswered.

**Inferred (not stated by the owner; the boundary review shows these):**
- **Ask's write is `art_taste(action='set')` only, never `delete`.** `set` is an
  upsert that may *correct* a judgment, which a curator saying "actually I've
  gone off Klimt" needs. `delete` is unrecoverable and stays on Taste and MCP.
- **Only `stated` can be written, and the service already enforces that**
  (`set_affinity` refuses `observed` and `inferred`). The prompt tells the agent
  to record only what the curator says about their own taste, and to say so in
  its reply. The tool call also shows in the thread as it happens.
- **Taste reaches Ask as a reader injected at construction**, built per reply,
  so a judgment set in one reply is in the next reply's prompt.
- **Phase 1 is told at most `REJECTED_TOLD` rejected works, newest first.** The
  suppression check after the call stays the guard. The list in the prompt only
  saves spend, so a cap that leaves old rejections out costs money and never
  correctness. A household's whole rejection history grows without bound; its
  taste is tens of rows.
- **The request outranks the taste in both prompts.** "Show me Dalí" from a
  curator who declines Surrealism is answered with Dalí. Taste ranks and fills
  in; it does not overrule what was asked.

**Tradeoffs accepted:** a prompt-injected page in Ask's web search could now steer
a taste write. A write is visible in the thread, correctable on Taste, and spends
nothing, so it is recorded in `security-model.md` rather than designed out.
Fencing tool results (item 6) is the later, weak bound the owner already ranked
last.

**Decisions made mid-build:**
- Chunk 01 — the Taste screen's help, which lists every way a judgment is
  recorded, gains "tell Ask"; settled by the help's own claim to completeness.
- Chunk 01 — the brief orders loves, declines, likes, cool, so a cut at
  `TASTE_TOLD` keeps the judgments that most change what a model offers.
- Chunk 02 — the request is built inside the runner's guard, because it now
  reads the catalogue, and a read that raised outside it would hold the run.
- Chunk 02 — `REJECTED_TOLD` is 100, one per dedup key at its latest rejection.

## Build Chunks

### Chunk 01: Ask reads the taste and records what the curator states

- **Description:** One rendering of the taste for a prompt, shared by both
  chunks. Ask's system prompt carries it, per reply. `ASK_SCOPE` gains
  `art_taste` `list` and `set`.
- **Depends on:** none
- **Artifacts consumed:** `agents-and-memory.md` ruling 1, `api-contract.md`
  (Ask's scope), `security-model.md` (what Ask may do)
- **Deliverables:** `describe_taste` in `arrt/src/arrt/library/services/taste.py`;
  `ask_system(taste)` in `arrt/src/arrt/ask/prompt.py`, with `ASK_SCOPE` widened;
  `Ask` given a taste reader and wired in `app.py`; `_SAID` lines and card cases for
  the two actions; the eval composing the prompt the same way; the artifacts amended.
- **Tests:** unit — the brief for every sentiment × open_to_more combination, the
  empty taste, the brief's cap; the agent sends the taste in its system prompt, and
  a judgment set in reply 1 is in reply 2's prompt; `delete` is refused in Ask.
  Integration — Ask's `set` writes a `stated` row through dispatch.
- **Acceptance criteria:** the tests above pass, and the suites stay green.
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. Committed

### Chunk 02: Phase 1 is told the taste and the works already rejected

- **Description:** `WorkListRequest` carries the taste brief and the newest
  rejected works. Phase 1's prompt names both, below the request, which wins.
- **Depends on:** Chunk 01
- **Artifacts consumed:** `data-model.md` (`CandidateWork`, `Verdict`)
- **Deliverables:** a store read for rejected works, newest first and bounded;
  the request's two new fields, filled by the runner; `PROMPT` with the two
  sections, which are left out when empty.
- **Tests:** unit — the prompt with and without each section, and that the request
  is still in it verbatim. Store — rejected only (not `wanted`, `pending` or
  `accepted`), newest first, the cap honoured. Runner — the engine receives the
  taste and the rejections (a recording fake engine).
- **Acceptance criteria:** the tests above pass, and all three suites stay green.
- **Type:** cumulative-final
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. Committed, then `/prawduct:critic cumulative` run and blocking findings resolved
