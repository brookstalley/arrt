# Ask as an agent — measured

Captured 2026-10-08 for `build-plan-ask-agent.md` Chunk 02: whether the cheap
models Arrt runs today can answer what a curator types into Ask, using the
product's own tools, before Chunk 03 builds the agent on them. Everything below
was **measured** against live services. Where a line is inference, it says so.

## How it was measured

**The harness** is the existing evaluation driver (`arrt/tests/eval/driver.py`),
extended. It offers a model the real MCP tool definitions over HTTP from a
booted server, executes every call through the real service layer, and records
the route. What Chunk 02 added to it:

- **A scope.** The run is offered only `art_catalogue` and `art_discovery`,
  whole, and any action outside Ask's set is answered with a teaching error
  naming the set, and never sent. Ask's set: `art_catalogue` `list`, `get`,
  `topics`, `topic`; `art_discovery` `search`, `find_topics`, `artist`,
  `similar_artists`, `work`, `topic`; and every tool's `help`. Nothing that
  spends, writes or reaches a wall. `look` is left out because its pictures
  travel as image blocks the driver does not relay.
- **Local tools beside the surface.** 3tears' `web_search` over SearXNG
  (`3tears-agent-tools` 0.65.0), when `SEARXNG_URL` is set.
- **Per-run accounting.** Steps (model replies), the provider's own cost
  summed over them (`response_metadata["cost"]`; a reply without one is counted
  as uncosted, and none was), and each reply's `finish_reason`, so a provider
  error is its own outcome rather than "the model never answered".

**The registry is Wikidata, asked live**, with a fresh answer cache per run, so
every run asked Wikidata afresh. The library is the suite's seeded catalogue:
three works, one of them Salvador Dalí's *The Persistence of Memory*.

**The prompt and scope are drafts of what Chunk 03 ships**, in
`arrt/tests/eval/ask.py`. The prompt asks the model to look things up rather
than answer from memory, to name every work, artist and topic with its Wikidata
item in brackets, to name only items a tool returned, and to say which works the
library holds.

**Scoring reads the transcript, never the model's account of itself.** An item
the answer names (by QID) is *grounded* when some tool result contained it and
*invented* otherwise. A *work* is a QID a tool returned beside a title;
*gettable* is a work offered in the answer that the tools did not mark held.

**The requests** (`REQUESTS` in `ask.py`), each with its check:

| Id | What the curator types | Passes when |
|---|---|---|
| `early_dali` | Show me Salvador Dalí's early work. | at least 3 gettable works offered |
| `taste_exclusions` | I like Dalí and Warhol but not Haring. Help me find more. | at least 3 gettable works, none whose maker the tools named as Haring |
| `calm_bedroom` | Something calm for a bedroom. | at least 3 gettable works offered |
| `held_dali` | What do I already have by Dalí, and what else of his should I look at? | the answer names *The Persistence of Memory*, which the library holds |

Every request also fails on a provider error, on no answer, and on any invented
item.

**Re-running it:** `cd arrt && uv sync --group eval`, then with
`OPENROUTER_API_KEY`, `SEARXNG_URL`, `ART_EVAL_MODEL` and `ART_EVAL_RECORD` (a
file) set, `uv run --group eval pytest -n0 -m llm_eval tests/eval/test_ask_requests.py`.
Each run appends one JSON line to the record file.

## Results

**N and when.** 55 runs on 2026-10-08, every one with web search on (SearXNG on
the operator's LAN): each of the four requests three times per model, twice for
`anthropic/claude-sonnet-5.5`, the stronger reference. One `qwen/qwen3.7-flash`
pass lost one run to OpenRouter's rate limit (`TooManyRequestsResponseError`),
which the harness raised rather than recorded, hence 11. The whole matrix cost
$0.58, $0.47 of it Sonnet's.

| Model | Runs | Passed (as recorded) | Passed (re-scored) | Stopped at 24 calls | Provider errors | Steps median / max | Tool calls median / max | Invalid calls (of them refused) | Invented items | Web searches | Cost per reply median / max | Seconds per reply |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 12 | 10 | 12 | 0 | 0 | 3 / 3 | 4.5 / 6 | 3 (0) | 0 | 0 | $0.0028 / $0.0032 | ~15 |
| `qwen/qwen3.7-flash` | 11 | 10 | 11 | 0 | 0 | 4 / 7 | 6 / 13 | 3 (1) | 0 | 0 | $0.0009 / $0.0067 | ~50 |
| `deepseek/deepseek-v4-flash` | 12 | 7 | 6 | 5 | 0 | 8 / 11 | 22.5 / 24 | 0 (0) | 1 | 0 | $0.0039 / $0.0078 | ~58 |
| `google/gemini-2.5-flash-lite` | 12 | 0 | 0 | 0 | 2 | 2 / 4 | 1 / 3 | 16 (16) | 17 | 0 | $0.0003 / $0.0019 | ~4 |
| `anthropic/claude-sonnet-5.5` | 8 | 7 | 7 | 0 | 0 | 3 / 3 | 6 / 8 | 0 (0) | 0 | 0 | $0.0625 / $0.0774 | ~18 |

| Model (re-scored) | `early_dali` | `taste_exclusions` | `calm_bedroom` | `held_dali` |
|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 3/3 | 3/3 | 3/3 | 3/3 |
| `qwen/qwen3.7-flash` | 3/3 | 2/2 | 3/3 | 3/3 |
| `deepseek/deepseek-v4-flash` | 3/3 | 0/3 | 0/3 | 3/3 |
| `google/gemini-2.5-flash-lite` | 0/3 | 0/3 | 0/3 | 0/3 |
| `anthropic/claude-sonnet-5.5` | 2/2 | 1/2 | 2/2 | 2/2 |

**How to read the columns.** A *step* is one model reply, tool-calling or
final. *Cost per reply* is the provider's figure for the whole curator-facing
reply, all its steps; no reply came back without one. *Seconds per reply* is not
measured per run: it is each model's pytest wall clock per four-request pass,
divided by four, so it includes booting a server and asking Wikidata cold every
time; it orders the models and does not predict production latency.
*Invalid calls* are calls that failed, *refused* among them those outside Ask's
scope. Wikidata could not answer 6 calls in all, in four `taste_exclusions` runs (5
in deepseek's, 1 in qwen's). Two of deepseek's ran into the call budget
with two failed calls each, so an outage may have cost them calls; it did not
decide any other run.

**Re-scored, and why.** `taste_exclusions` first passed only on three gettable
*works*. Reading the answers, the best ones (qwen, haiku) answered "help me find
more" with a dozen grounded *artists* by movement, which is a good answer and
failed the check. The check now counts grounded works or artists, and fails on
naming Haring or a work a tool attributed to him (`_more_and_no_haring`). The
re-scored column applies that rule to the recorded answers, Haring's items
identified by their QIDs (Q485635, Q4000955, Q20431246). It also corrects
deepseek's one recorded pass, which named an item no tool returned: the test
failed it, and the record's `passed` did not count invented items. It does now
(`ask.passed`), with a test.

**One check cannot tell naming from offering.** Sonnet's failing
`taste_exclusions` run listed Haring and two of his works under "Haring's own
items, which I left out". A reader passes it; the check does not.

**What each model did:**

- **`anthropic/claude-haiku-5.5`**: every request answered and grounded,
  always in 3 steps and at most 6 calls, at a cost that barely varies. Its 3
  invalid calls were recovered from. **One answer mislabelled an item**: it
  gave Ed Ruscha the QID of Robert Indiana, then wrote a garbled correction into
  the answer. Grounding does not catch that, since the QID was a tool's. One
  instance, seen by reading; not measured systematically.
- **`qwen/qwen3.7-flash`**: as reliable on these requests, at about a third of
  haiku's median cost but a long tail ($0.0067) and roughly three times slower.
- **`deepseek/deepseek-v4-flash`**, the discovery model: thorough to a fault.
  On the two open-ended requests it fanned out, one `work` or `artist` call per
  candidate, and ran into the 24-call budget without answering 5 times in 6.
  Where it answered, the answers were the most detailed.
- **`google/gemini-2.5-flash-lite`**, the surface evaluation's default: cannot
  do Ask. It asked the curator for Wikidata items instead of searching, called
  actions outside the scope 16 times, invented 17 items in one answer, and the
  provider errored on 2 runs.
- **`anthropic/claude-sonnet-5.5`**: answers as reliable as haiku's and richer,
  at about twenty times the cost.

**No model used web search, in 55 runs.** The registry tools answered every
request well enough that none reached for it. Whether it earns its place in
Chunk 03 is a question for requests these four do not ask: a living artist
Wikidata barely knows, or a show seen last week.

## Decisions taken from these numbers

**[DECISION: Ask's default model is `anthropic/claude-haiku-5.5` | the agent,
2026-10-08, from the table above | owner can veto]** It passed every request,
in the fewest steps, with the tightest cost and the fastest replies among the
models that passed. At about $0.003 a reply, a $20 month is roughly 6,600
replies. `qwen/qwen3.7-flash` is the cheaper alternative and equally reliable
here, at three times the wait; a curator waits on every reply, so the wait
decides it. The model stays a setting, as the discovery and mat models are.

**[DECISION: the step limit for Chunk 03 is 8 model replies per curator
reply | the agent, 2026-10-08 | owner can veto]** Haiku never took more than 3
steps and qwen never more than 7, so 8 holds the chosen model with room and a
switch to qwen without a cut-off. Deepseek's runaway fan-out shows what the
limit is for. In LangGraph's count, where each model call and each round of
tool calls is one super-step, 8 replies is a `recursion_limit` of 15; Chunk 03
confirms that count by test rather than by this sentence.

**Not decided here:** whether `web_search` ships enabled (above), and whether
`look`, left out of this scope, joins it once the agent can relay pictures.


## Found along the way

**3tears 0.65 works for the agent loop unchanged, with one gap.**
`create_chat_model(model_id, api_key=, provider="openrouter")` returns a binding
that both `bind_tools` and LangChain's `create_agent` (langchain 1.4.4) accept,
and a two-step tool loop ran on `deepseek/deepseek-v4-flash` and
`qwen/qwen3.7-flash` through `create_agent` with no adapter. Importing
`threetears.models` and `threetears.agent.tools.builtin.web_search` loaded
neither `nats` nor `asyncpg`. **The gap:** 3tears' `UsageTracker` records
`cost_usd=None` for these models, while OpenRouter's own figure arrives on every
reply as `response_metadata["cost"]`. Chunk 03 reads the latter.

**The search half of 3tears' web search reaches a LAN SearXNG with no
private-address setting.** `allow_private_addresses` belongs to the fetch
transport (`build_fetch_transport`), which `web_search` does not use; the search
transport is bound to its one configured base URL. The plan's decision expected
to need the setting for search; it needs it only when `web_fetch` arrives.

**SearXNG's general results for a person's name are poor.** "Salvador Dalí early
works 1920s" returned El Salvador pages first, with the Wikipedia list of Dalí's
works third. Inference, not measured further: the engines (Google CSE, Bing)
weight the country.

**`google/gemini-2.5-flash-lite` intermittently answers the tool surface with
`finish_reason: error`.** One run of the existing surface evaluation failed this
way on the new schema, so it looked like a regression. It was not: the same
schema then answered 12 of 12 calls without an error (9 tool calls, 3 answers
with no tool), and in a bisect a variant with the new actions taken back out of
the `action` enum errored once while the full schema did not. The driver now reports a provider error by name.

**Pinning 3tears 0.65 moved `websockets` from 17.0.1 to 16.1.1 in `uv.lock`**
for every group, through `langgraph-sdk`'s cap, since uv resolves one lock for
all groups. Nothing in `arrt` imports `websockets`; it reaches the `dev` group
only through langsmith.
