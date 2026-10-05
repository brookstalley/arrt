---
artifact: build-plan
version: 1
scope: run-end-reason
branch: feature/run-failure-reason
partition: serial — one builder, one chunk
depends_on:
  - artifact: data-model
  - artifact: api-contract
governed_by:
  - artifact: security-model
    dispositions:
      - "§ Direction: outside text reaches the page as text → conforms. A reason can quote the provider's own words (`_provider_message`), and the run page renders it through `el`'s `text`, never as markup"
  - artifact: data-model
    dispositions:
      - "Additive widening only → conforms. One nullable TEXT column, which `durable.py`'s widening adds to an existing catalogue file in place"
last_validated: null
---

# Build Plan — Why a run ended

## What this plan is

Backlog #207. A discovery run that fails keeps no record of why: the runner
composes a reason at every failure site and only logs it, so the API, the MCP
`status` action and the run page all say "failed" with nothing a curator can act
on. Seen 2026-10-05 on an Ask for Lucy Bull (run `4756cdee`), whose reason could
not be recovered without the container's logs.

The owner said go on 2026-10-05, with the defaults proposed in the session that
picked it (the questions the issue left open, answered below).

## Requirements Confidence

**High.** The reasons already exist as prose, written for a reader; this stores
and shows them.

- [DECISION: one nullable column, `discovery_runs.end_reason`, written by the run's own ending call, in the same write as its status | a reason held anywhere else can disagree with the status it explains | owner approved 2026-10-05]
- [DECISION: written by the two endings the worker reaches on its own — `failed` and `halted_by_budget` — and required by both | a halt's reason quotes the provider's refusal, naming the limit that refused, which the page's fixed sentence cannot (corrected at review: the asked-against-left arithmetic is a 402's, which fails the run). A required argument makes a reasonless failure a type error rather than a quiet null | owner approved 2026-10-05]
- [DECISION: not written for `cancelled`, `declined`, `interrupted` or `completed` | this narrows the default proposed to the owner, which named cancellations too. A cancel or decline is the curator's own act and nothing composes a reason for it; `interrupted` is written by startup reconciliation, which knows only what its status already says. Their page sentences already say what is known | agent's, owner can veto]
- [DECISION: an unexpected exception records a fixed sentence that points at the server log, never the exception's text | exception text can carry paths and addresses, and a curator cannot act on a traceback. The runner already does this; the sentence gains the pointer | owner approved 2026-10-05]
- [DECISION: shown on the run page and in the run's API and MCP shapes, including the listings; not on the catalogue | a reason is short and appears only on runs that need one, unlike `strategy`, which the MCP listing drops for size | owner approved 2026-10-05]
- [ASSUMPTION: a run that ended before the column has a null reason and the page falls back to today's sentence ("The server log has the details") | LOW impact | owner can correct]

**Not in this plan:** diagnosing the Lucy Bull run, and changing
`DISCOVERY_MAX_OUTPUT_TOKENS` (both out of scope on the issue).

## Status

- [x] Chunk 01: A run keeps why it ended, and the run page says it

### Chunk 01: A run keeps why it ended, and the run page says it

**Exposed API:** `RunOut.end_reason` (HTTP), `end_reason` in the MCP run fields

Done when:

- `DiscoveryService.fail_run` and `halt_run_for_budget` take a required `reason`
  and store it with the ending; the runner passes the reason it already logs.
- `GET /api/runs/{id}`, the runs listing and the MCP `status`/listing return
  `end_reason`, null when no reason was written.
- The run page shows a failed or halted run's reason, and shows no reason line
  for a run without one, including a failed run from before the column.
- A catalogue file written before the column opens, widens, and reads its old
  runs with a null reason.
- `data-model.md` and `api-contract.md` describe the field.
- Tests: through the runner (a phase-1 engine failure and a budget halt reach
  `GET /api/runs/{id}` with their own words), the store round trip, widening an
  old file, and the browser run page for both the present and absent cases.

- **Critic mode:** cumulative (one chunk, so this is its review and the branch's)
