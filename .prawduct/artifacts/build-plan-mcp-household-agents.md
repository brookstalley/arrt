---
artifact: build-plan
version: 2
scope: mcp-household-agents
branch: feature/mcp-household-agents
base: develop
working-branches: []
last_validated: 2026-11-08
depends_on:
  - artifact: agents-and-memory
  - artifact: api-contract
  - artifact: security-model
governed_by:
  - artifact: security-model
  - artifact: api-contract
partition: serial — both chunks edit `api-contract.md` and the MCP surface tests, and Chunk 02 is small enough that a delegate's brief would cost more than the work
---

## Goals

**Response taken:** Proceed, citing it. `agents-and-memory.md` item 3 ("MCP for the
household's own agents") and open question 5. The advisor proposed this scope on
2026-11-08. The owner's reply was "let's keep going", which this plan reads as
accepting it. *Inferred, not ruled:* the owner had not seen the #53 finding below
when they replied.

**Product:** a household's own agent reaches its Arrt over `/mcp` from inside the
LAN and does what Ask does inside Arrt (ruling 4). Two things stand in the way:
- The agent is not told the taste the way Ask is. Ask's prompt carries
  `TasteService.brief()`, but MCP gives only the raw rows.
- The surface the agent is invited onto has no Host or Origin check (#53), so a web
  page open in any browser on the LAN can drive it by DNS rebinding.

**Open question 5, answered by the code (measured 2026-11-08):**
- **Taste writes are already on MCP.** `art_taste` has `list`, `set` and `delete`,
  and `set` refuses anything but `stated`.
- **Verdicts are already on MCP.** `art_review(action='set_verdict')` calls
  `DiscoveryService.set_verdict`, which calls `observe_artist`, so a verdict over MCP
  feeds observed taste as the browser's does.
- **MCP is a superset of `ASK_SCOPE`.**

So the question's "taste writes certainly" was already built, and what remains is
the brief and the guard.

**#53, the fork it asks the operator to pick:**
- Fork 2 (binding policy) cannot close the vector on the reference deployment. The
  homelab publishes the server's port directly on the NAS, so the Pi can pull its
  wall's feed when the reverse proxy is down. A rebinding page can reach that
  port, and the proxy never sees the request.
- So this plan takes fork 1: Arrt checks Host and Origin itself.

`[DECISION: Arrt refuses a request whose Host is not an IP address, localhost or a
name the deployment lists in CURATION_ALLOWED_HOSTS, and a request whose Origin
(when sent) is neither a listed name nor the request's own address (its Host's
name and port); the Player's token-admitted routes are not
checked | #53 fork 1, because fork 2 would take away the direct port the Player
relies on. IP addresses and localhost are always allowed: a rebinding page's
requests carry the attacker's domain name in Host, never an IP address, so allowing
them costs nothing and keeps a fresh install reachable. The Player's routes are
already guarded by the wall token, which a rebinding page cannot read, and checking
their Host would let a name a Player is configured with, and the server is not,
darken a wall | user can veto/override]`

**Architecture:** one guard for every surface a person or an agent uses: `/mcp`,
`/api`, Ask's routes, the pages and the static files. It is not two guards, one on
the MCP transport and one on FastAPI, because two would drift apart.
`StreamableHTTPSessionManager`'s own `security_settings` is not used, so the rule is
stated once. Ruling 6 holds: nothing here makes a feed depend on the web UI or MCP.

**Constraints:**
- No authentication. `security-model.md` § Trust Boundary stands, and this is an
  integrity check on where a request came from, not a login.
- No new dependency.
- The repository is public, so no deployment hostname is written here. The
  operator's names go in the homelab's env file.

**Tradeoff accepted:** a deployment reached by a hostname must list that name, or
its browser UI and MCP refuse every request after the upgrade. The refusal says
which setting to set. Deploys are asked for, and the release notes say it.

**Level:** High. The mechanism is small and well understood, and the one
deployment fact it rests on was read from the homelab's compose file and Caddyfile.

**Decisions made mid-build:**
- `brief` answers `{"brief": …}` with no `count`. A count would be a second read of
  the store that could disagree with the text, and an empty brief already says
  there is no taste. *(Settled by the learnings rule on one rendering read along
  one path.)*
- The guard is installed with `add_middleware`, and `create_app` still returns
  the FastAPI app, because the suite and the lifespan use it as one. Middleware
  wraps the mounts too.
- `Origin` is parsed by hand rather than with `urllib.parse`, because
  `test_persistence_boundary` keeps `urllib` out of every module but the network
  client. A malformed `Origin` is refused, not skipped.
- `Origin` takes a stricter test than `Host`: a listed name, or the request's own
  name and port. The first build applied `Host`'s test, which passes every IP
  address, so a page served from another LAN device could still make bodyless
  cross-origin POSTs. *(Revised after the cumulative review.)*
- The api-contract and security-model entries say **proposed**, not decided, until
  the owner rules on #53's fork, because their "let's keep going" came before they
  saw it.
- `CURATION_ALLOWED_HOSTS` refuses a URL, a port or a path at startup instead of
  keeping the name part, so a misunderstanding of the setting is reported.
- The setting is documented in `.env.example`, `deploy/README.md` (a dated
  section, with the check and the way back) and the compose example, not in the
  operational spec, which does not list settings one by one. *(Not settled by
  the goals: the plan named the operational spec.)*
- The suite's way of starting a real server moved from conftest's `server_url`
  into `tests/serving.py`'s `serve(app)`, so the guard's tests can start an app
  configured with allowed names under the same port rule.

## Build Chunks

### Chunk 01: The taste brief over MCP

- **Deliverables:** `art_taste(action='brief')`, returning `TasteService.brief()`
  as text (no count: see Decisions made mid-build). Its binding in
  `arrt/src/arrt/mcp/bindings.py`; its row in `api-contract.md`; open question 5
  answered in `agents-and-memory.md`, and item 3's row updated.
- **Tests:** through the MCP surface (the caller): an empty taste returns an
  empty brief, and a seeded taste returns the same text `Ask` is given, compared
  against `TasteService.brief()`, not a copy of the wording. A `stated` and an
  `observed` row both appear, so the derivation suffix is exercised.
- **Done when:** tests pass; committed.

### Chunk 02: Host and Origin are checked on every surface but the Player's

- **Deliverables:** the setting `CURATION_ALLOWED_HOSTS` in `arrt/src/arrt/config.py`
  (comma-separated names, empty by default); one ASGI guard wrapped around the app
  in `arrt/src/arrt/app.py`; the Player's routes exempt by `contract/routes.json`'s
  list, not by a prefix written here. Refusals: `421` for a Host that fails, `403`
  for an Origin that fails, each naming the setting. The records:
  - `api-contract.md` § Security gets the dated decision #53 asks for, naming
    `art_discovery`'s spend.
  - `security-model.md` § Trust Boundary gets a line on the guard.
  - The operational spec gets the setting.
  - #53 closes.
- **Tests:** at the ASGI boundary, through a real server per the suite's rule:
  - A name not listed is refused on `/mcp`, `/api` and a page.
  - The same name, once listed, is admitted.
  - An IP address and `localhost` are admitted with nothing listed.
  - A foreign Origin is refused even with a good Host.
  - No Origin is admitted.
  - `Origin: null` is refused.
  - A Player route is admitted under a foreign Host.
  - Port and case in the Host do not matter.
  - An IPv6 literal is admitted.

  Each test must fail once against the unguarded app.
- **Type:** cumulative-final
- **Done when:** all three suites pass; committed, then `/prawduct:critic cumulative`.
