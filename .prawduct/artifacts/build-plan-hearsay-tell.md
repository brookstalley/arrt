---
artifact: build-plan
version: 2
scope: hearsay-tell
branch: feat/hearsay-tell
base: develop
working-branches: []
partition: "serial for 01, which lays the tap, the queue and the plugin interface every later chunk uses. After 01, Chunk 04 (the sender, its configuration and the health line) may go to one delegate in an isolated worktree beside 02 and 03, which both edit loading.py and the plugins and stay serial. The coordinator integrates and runs the suites and the Critic. Decided when 01 lands, by whether 04's brief costs less than building it."
depends_on:
  - artifact: source-plugins
  - artifact: architecture
  - artifact: security-model
  - artifact: data-model
  - artifact: operational-spec
  - artifact: observability-strategy
governed_by:
  - artifact: architecture
    dispositions:
      - "the per-wall manifest and content-addressed media are the only channel to a Player → inapplicable because this plan adds no Player route and changes no manifest"
      - "a display device renders its own label → inapplicable because nothing here reaches a Player"
      - "operation logic lives only in the service layer → conforms: the queue summary is a service call, the health line is a HealthService signal, and the command that prints the queue is a thin binding over the same call"
      - "Library/Programming seam rules 1, 2 and 4 → conforms: the tap, the queue and the sender live in the Library; Programming is not touched"
      - "seam rule 3, separate stores → inapplicable because the queue is neither side's store and holds no work ids"
  - artifact: security-model
    dispositions:
      - "text from outside Arrt reaches the page as text → conforms: the health line shows counts and Hearsay's error codes, rendered as text like every other signal"
  - artifact: nonfunctional-requirements
    dispositions:
      - "spend ceilings are enforced by the provider → inapplicable because Hearsay is the operator's own service and no paid call is added"
      - "the display plane never depends on the curation plane → inapplicable because nothing here reaches a Player"
  - artifact: project-preferences
    dispositions:
      - "the server passes the type checker, no module excused → conforms, with a question for Chunk 01's verify-api: hearsay-client ships no py.typed, so either Hearsay adds it or Arrt types the calls it makes; a mypy override that silences the import is not taken without a ruling"
      - "no hardcoded deployment values in source → conforms: the base URL, key and environment come from configuration only, and test_deployment_values stays green"
      - "no secret ever reaches a log line → conforms: Chunk 04 extends the startup test to the Hearsay key"
      - "catch specific exceptions → conforms: a queue write failure is caught by the sqlite and OS errors it can raise, never broadly"
      - "a backup is restored from → conforms: the queue is outside the catalogue and not in a backup generation, which operational-spec.md will say"
      - "all other rows (formatting, naming, waivers, the design tokens, the arr layout, navigation, held-out artists, the heartbeat key, the TV token, drift probes, contract minors) → inapplicable because this plan touches none of their subjects beyond following them"
  - artifact: data-model
    dispositions:
      - "identity is never a source URL → conforms: queue rows are keyed by an id Arrt mints, and no artwork identity is derived from what is told"
      - "a work is distinct from an image of it → inapplicable because the queue holds documents and searches, not works"
      - "per-device runtime state never lives in the catalogue → inapplicable because the queue is its own file, not the catalogue"
      - "derived artifacts are regenerated, never transported → inapplicable because what is told is the museum's own document as read, not anything Arrt derived"
      - "a picture fetched from outside is kept forever under ART_ROOT/pictures/ → inapplicable because the tap never copies an image and the picture store is unchanged"
last_validated: 2026-11-25
---

# Build Plan — Tell Hearsay the museum fetches and searches

## What this plan is

#451. The owner ruled on 2026-11-25 that Arrt contributes to Hearsay, the owner's
attributed claim store: the museum documents it fetches, and what discovery learns
(`.prawduct/owner-rulings.md`, "Arrt contributes to Hearsay's knowledge graph"). The
same day the owner settled how (`owner-rulings.md`, "how Arrt tells Hearsay (#451)").
There is one copy point in the host and a label in each plugin. The queue fills
before anything is sent, and there is no backfill (#454).

This plan builds the part Hearsay can take today: **fetches and searches**, through
`POST /tell/fetch` and `POST /tell/search` (Hearsay contract 1.1, `hearsay-client`
0.2.0). Arrt's own statements, such as "record R is work W" and phase 1's proposals,
wait for `POST /tell/statements` (contract 1.2). That gets a plan of its own once it
ships, and `/tell/witnessed` is not used as a stand-in.

**Code starts after audit Wave 3 merges to `develop`.** Wave 3 changes
`library/sources/loading.py` and `nga.py`, so merge `develop` into this branch first.

## Goals

- **Response taken:** asked in batches. The owner answered on 2026-11-25 ("yes to all
  recommendations"), and Hearsay's session answered the intake questions the same day.
- **Product:** Hearsay keeps what Arrt reads from museums and Wikidata, and what each
  museum search returned. It will later read those into world claims, through a mapping
  per museum that the owner approves. Arrt drops a museum's document once it has parsed
  it, so a fetch that is not told is lost to Hearsay for good. That is why the copy is
  taken as the document is read, and queued on disk.
- **Architecture: what must hold.**
  - **A tell never slows or fails a museum fetch, a search or a run.** Queueing is a
    local write. A queue that cannot be written is counted and logged, and the fetch
    goes on.
  - **Nothing leaves the machine until the owner turns sending on.**
  - **Only text documents are told.** Images, tiles and previews are never told.
  - **A request no plugin labels is not told.**
- **Architecture: what must stay possible.**
  - Arrt's statements, once contract 1.2 ships: the sender and the queue take a third
    kind of item without being redesigned.
  - Hearsay's CSV intake (Hearsay #47), so the National Gallery of Art's open data can
    be told later.
  - The backfill (#454), which refetches through the same tap.
- **What Hearsay settled (its session, 2026-11-25, from its `api-contract.md` Tell
  and Limits).**
  - **Size.** A document's text is at most 2 MiB of UTF-8, and a request body at most
    8 MiB. A longer document is sent cut, with `chars_read` under `chars_total`;
    Hearsay keeps it marked as cut and never reads it as the record. A checksum
    instead of the text is refused unless Hearsay already holds that text.
  - **The National Gallery of Art's two CSVs are not told** until #47 settles how CSV
    is kept.
  - **Wikidata is told.** An entity document has audience `world`. A SPARQL query URL
    has audience `product`, because Arrt wrote the query.
  - **Readers.** One consumer reader per source module, `arrt-<module>` (`arrt-artic`,
    `arrt-wikidata`), whose version is Arrt's release.
  - **Search provider.** `Search.provider` is the plugin's stable id (`artic`), never
    the museum's name, because Hearsay matches it exactly.
  - **Fetch or search.**
    - A search is told as a Search, the Art Institute's POST search included: the query
      as text, the structured query as `scope`, and the results it returned.
    - A Fetch is told only for a GET Arrt made for a record, linked to its search by
      `Fetch.search` when it was made for one.
    - A record that arrived inside a search's response stays a search result. A raw
      search response is never told as a Fetch.
    - Audience: a record URL that carries none of Arrt's words is `world`; a URL
      carrying Arrt's query is `product`.
- **Constraints.**
  - The base URL, the key and the environment name (`production`) live in the
    operator's private deployment configuration, never in this repo.
  - The consumer key Hearsay issued sits outside every repo, and is never read, printed
    or committed here.
  - Hostnames and addresses never go in tracked files.
- **Tradeoffs accepted.**
  - **A third-party plugin is not covered.** One that does not build its HTTP client on
    the host's transport is not told (owner, ruling 1). All ten plugins today are
    in-tree.
  - **The queue is not backed up.** Losing the disk loses documents not yet sent.
    Revisit if sending is ever off for long.
  - **Only successful reads are told.** *Inferred:* told outcomes are `read` only in
    this plan. A 404 or 410 is not told unless verify-api (Chunk 01, step 0) finds an
    outcome Hearsay defines for "not there", in which case Chunk 03 tells it.
  - **A queue size cap.** *Mine, and offered as removable:* a cap of 512 MiB, past
    which new items are refused and counted (`hearsay.queue_full`), so a sender left
    off for months cannot fill the NAS. Drop it if you'd rather the queue grow without
    a bound.
- **Out of scope.**
  - Arrt's statements (contract 1.2).
  - The backfill (#454).
  - The National Gallery's CSVs (Hearsay #47).
  - OpenRouter's calls, and the pages phase 1's web search read: OpenRouter fetched
    those pages, not Arrt.
  - Reading anything back from Hearsay.
- **Decisions made mid-build:** *(appended while building, one line each)*
- **Level: Medium.** What would raise it: Chunk 01's verify-api, which pins four
  things.
  - What `Fetch.search` holds: a search event id or something else.
  - The outcome values `tell/fetch` accepts.
  - Whether `hearsay-client` ships type information mypy can read. It has no
    `py.typed` at 0.2.0.
  - Whether the server image's build can install a git dependency.

## Design

### The tap (`new arrt/src/arrt/library/hearsay/`)

- **Plugin interface 1.7** (`source-plugins.md` § Versioning and errors) adds two
  fields. A 1.6 plugin loads unchanged and is not told.
  - **`SourceContext.transport`** is the host's HTTP transport. A plugin builds its
    client on it, as each built-in's `_client(transport)` already takes one for tests.
  - **`SourcePlugin.tells`** is static, like `claims`. It maps a request's method and
    URL to `world`, `product` or nothing (not told).
- **The Wikidata registry** (`library/registry/wikidata.py`) is not a plugin. It gets
  the same transport and a label of its own.
- **What the transport copies.**
  - It copies a labelled request's response body as the plugin reads it, and only for
    a text content type (JSON, XML, HTML, `text/*`).
  - It copies up to the 2 MiB text cap. Past the cap it counts on and records the item
    as cut, with `chars_read` and `chars_total`.
  - It queues the item when the response closes.
- **What a told fetch carries.**
  - `url_requested`: the URL the plugin asked for.
  - `url_final`: where the body came from. Only the Art Institute's client follows
    redirects today.
- **Searches.** The host's wrapper around `find_images` and `browse` (`loading.py`)
  queues one Search per call, whether it found something, nothing, or failed.
  - The search carries the provider, the query as text, the structured query as
    `scope`, and each result's rank, URL and title.
  - A fetch made while that call runs carries a link to the search's queue row. The
    sender turns the link into Hearsay's id.

### The queue (`ART_ROOT/hearsay/outbox.sqlite`, its own file)

This is a persisted format. The questions it must answer, from its consumers (the
sender, the owner's inspection, the health line, and #454):

1. What is waiting, by source and kind, and how old is the oldest?
2. Exactly what a send will make: the payload as it will go out, for the owner to
   read before the first send.
3. What Hearsay refused, with its error code. These items are kept until the operator
   acts, and never retried on their own.
4. Each item's idempotency key, minted when it is queued and stable across restarts
   and retries.
5. That a sent item is gone. A sent row is deleted once Hearsay answers, and a running
   count is kept. *Inferred:* no history of sent items is needed, because Hearsay is
   the record of them.

### The sender

- **Where it runs.** An asyncio task started by the app's lifespan.
- **Configuration.**
  - It needs `HEARSAY_URL`, `HEARSAY_KEY_FILE` and `HEARSAY_ENVIRONMENT`.
  - `HEARSAY_SEND=on` turns sending on, and it is off otherwise. With sending off, the
    queue still fills, and start-up says so in one line.
  - Partial configuration is refused at start, by name.
  - The key is read from its file and never logged.
- **Readers.** It registers the `arrt-<module>` readers when it connects.
- **Sending.**
  - It drains the oldest item first, and sends a search before the fetches linked to
    it.
  - A retryable error, or an unreachable service, leaves the item queued and backs off,
    with a cap.
  - A refusal moves the item to refused, with its code.

### What a person sees

- **The health panel** has one line: waiting, oldest, refused, last sent, and whether
  sending is on.
- **A command,** `uv run python -m arrt hearsay`, prints the summary and, with
  `--show N`, the next N payloads exactly as they would be sent. This is how the owner
  looks before turning sending on.

### New structural context

| Concern | The tap and queue (new storage) | The sender (new context, new external surface) |
|---|---|---|
| Observability | `hearsay.queued` / `hearsay.queue_failed` / `hearsay.queue_full` counts, logged once a pass, not per item | `hearsay.sent` / `hearsay.refused` / `hearsay.unreachable` log events; the health line |
| Errors | A write failure never reaches the fetch: it is caught by name, counted and logged | Retryable versus refused follows Hearsay's error codes, never by catching everything |
| Auth | None needed: a local file | A bearer key from a file; a new row in `security-model.md`'s secrets inventory |
| Config | `ART_ROOT` | Four variables, documented in `.env.example` (no values) and `operational-spec.md` |

## Build Chunks

### Chunk 01: The tap and the queue, through the Art Institute

- **Description:** a thin slice through the whole path for one source.
  - Plugin interface 1.7.
  - The transport that copies labelled text responses.
  - The queue file, with the Art Institute's label (`/artworks/<id>` GETs are
    `world`).
  - The command that prints the queue.
  - Record one real Art Institute record response as a fixture. None exists, and the
    Art Institute supplies most works.
- **Depends on:** Wave 3 merged into `develop`, and `develop` merged here.
- **Foreign API:** hearsay-client 0.2.0 (`tell/fetch`, `tell/search`)
- **Deliverables:**
  - The `arrt.library.hearsay` package: tap and queue.
  - `SourceContext.transport` and `SourcePlugin.tells` at API 1.7.
  - The Art Institute plugin built on the transport, with its label.
  - The `hearsay` command.
  - The new fixture under `arrt/tests/fixtures/artic/`.
- **Tests:**
  - A labelled JSON GET is queued with its URLs, text and audience.
  - An unlabelled GET, an image and a preview are not queued.
  - A body over 2 MiB is queued cut, with both counts.
  - A queue that cannot be written leaves the fetch's answer unchanged and counts the
    failure. Prove it red with the catch removed.
  - Each check runs through the plugin's real `read` and `find_images`, not the
    transport alone (core rule: test through the caller).
- **Acceptance criteria:**
  - A local server run that reads one Art Institute work leaves its record in the
    queue.
  - `python -m arrt hearsay --show 1` prints it as it would be sent.
- **Done when:**
  0. verify-api: read `hearsay-client` 643291af at the pinned commit, and ask Hearsay's
     session for the contract's definitions of `Fetch.search` and the fetch `outcome`
     values. Record the answers in this plan's Goals. Check mypy against the client,
     and whether a git dependency installs in the image's build stage.
  1. Acceptance criteria met, and the curation and governance suites pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed

### Chunk 02: Searches

- **Description:**
  - The host's wrapper around `find_images` and `browse` queues a Search per call,
    including an empty or failed one. The Art Institute's POST search is told as its
    query text, its structured query and its results.
  - Fetches made during the call carry the search's link.
- **Depends on:** Chunk 01
- **Deliverables:** search items in the queue and their links from fetches, in the
  `loading.py` wrapper.
- **Tests:**
  - One search with results, one with none, one that failed, and one past its deadline.
  - A record GET inside a search call is linked; one outside a search call is not.
  - The raw POST response is never queued as a fetch.
  - A search result with no title follows `SearchResult`'s rule that a title is
    needed, and is dropped from the told results and counted, not sent and refused.
- **Acceptance criteria:** a discovery run against fixtures queues one search per
  provider asked, with its results in rank order.
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed

### Chunk 03: Every other source, and Wikidata

- **Description:**
  - Build every built-in plugin's client on the host transport, and label its record
    GETs: commons, met, smk, navigart, yale, getty, rijksmuseum and wikidata.
  - Getty's SPARQL and Wikidata's SPARQL are `product`.
  - The National Gallery of Art's CSV downloads are labelled not told, with the reason
    (Hearsay #47) beside the label.
  - The Wikidata registry gets the transport and its label.
- **Depends on:** Chunk 01; after Chunk 02, because both edit the plugins.
- **Deliverables:** labels for nine plugins and the registry.
- **Tests:**
  - One test parametrised over the `arrt.sources` entry points (core rule: the symbol
    that names the set). It proves each built-in loads at 1.7, builds on the host
    transport, and labels at least one record URL and none of its image URLs.
  - National Gallery CSV URLs are not told.
- **Acceptance criteria:** with fixtures, a read through each plugin queues its record
  with the right audience.
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed

### Chunk 04: The sender, its configuration, and the health line

- **Description:**
  - Pin `hearsay-client` by commit in `arrt/pyproject.toml`.
  - Read the four variables and refuse partial configuration by name.
  - Register the readers, then drain the queue in order, with backoff and refusals as
    in § Design.
  - Add one health signal.
  - Sending stays off by default.
- **Depends on:** Chunk 01, and verify-api's answers.
- **Foreign API:** hearsay-client 0.2.0
- **Visual change:** yes. The health line needs a look on the Status page at phone
  and desktop width.
- **Deliverables:**
  - The sender in `arrt.library.hearsay`.
  - The configuration in `config.py` and `.env.example`.
  - The health signal.
  - A browser test for the line.
- **Tests:** the client runs against an `httpx.MockTransport` that answers in the
  shapes verify-api recorded, built after it.
  - Off: nothing is sent.
  - On: items go out in order with their keys, and a search goes before its linked
    fetches.
  - Retryable and unreachable: kept and retried.
  - Refused: kept, with its code, and not retried.
  - Restart mid-drain: the same key, and nothing sent twice.
  - Partial configuration: refused by name.
  - The key never appears in a log line. Seed a key and grep the captured logs.
  - Run the browser tests for Status, and the two curation guards CLAUDE.md names.
- **Acceptance criteria:** with sending off, a running server shows the waiting count
  on Status. With sending on against the mock, the queue empties and the line says
  when it last sent.
- **Done when:**
  1. Acceptance criteria met and tests pass
  2. `/prawduct:critic` run and blocking findings resolved
  3. Committed, and an operator-verification entry added for the health line

### Chunk 05: Records, then the first send

- **Description:**
  - **`source-plugins.md`:** 1.7's two fields, and § Trust's note that a plugin's
    reads are told.
  - **`architecture.md`:** the sentence that AcquisitionService is the one service
    that leaves the machine is description, not a Direction norm. Correct it: the
    Hearsay sender is a new edge to the operator's own service. Check the sentence
    against DiscoveryService, the registry and OpenRouter, which it already seems not
    to count; core rule: run the search that would falsify it. `api-contract.md:598`
    is about `art_taste`, which is untouched; say so in the change record.
  - **`security-model.md`:** the Hearsay key row.
  - **`operational-spec.md`:** the variables, the queue file and that it is not backed
    up.
  - **`observability-strategy.md`:** the events.
  - **The change fragment.**
  - **The backlog:** close #451 when merged.
  - **The first send:** the owner turns sending on in the private deployment config
    after reading `--show`.
- **Depends on:** Chunks 01–04
- **Type:** cumulative-final
- **Deliverables:** the records above, and the PR when the owner asks.
- **Acceptance criteria:**
  - Every artifact names what runs.
  - The change record states the departure.
  - The owner has seen a real `--show` before the first send.
- **Done when:**
  1. Records written, root and curation suites pass
  2. Committed, then `/prawduct:critic cumulative` run and blocking findings resolved

## Early Feedback Milestone

**Milestone chunk:** 01
**What the owner can do:** run `python -m arrt hearsay --show 5` on a server that has
read real Art Institute works, and read exactly what Hearsay would be sent. This is
the first look at what leaves the machine, before any sender exists.

## Governance Checkpoints

- **Commit and PR cadence:** commit per chunk after its review. One PR for the plan
  (owner, `one-pr-per-plan`), opened when the owner asks.
- **After Chunk 01:** confirm the tap's shape (transport plus static label) before
  nine more plugins are built on it.
- **Before the first send:** the owner reads the queue.
