# The UX walkthrough

How this repository looks at its own interface. Run it before a redesign, after
a run of screen work, and whenever the surface "feels off" without anyone being
able to say where.

## Why it exists

Every guard the browser client has asks one question: **does the client match
its documents?** `tests/preferences/test_screen_tables.py` holds the route table
against `information-architecture.md`; the browser suite holds behaviour
against what the plans said. Nothing asks the other question — **is this good
to use?** — so a screen can be correct by its spec and still bad, and the
documents describe structure (what is where) rather than experience (what it is
like to get something done).

The walkthrough is that other question, asked in a fixed order so the answer
does not depend on who asks or what they happened to open.

## The rule that orders everything: pictures and tasks before prose

Start from the rendered product, never from the artifacts. The artifacts are
what the surface was meant to be; reading them first means critiquing the
intent and seeing the screens through it. Read them in synthesis, to tag each
finding with whether a ruling already covers it.

## Pass 1 — Inventory, derived from the running client

`arrt/tools/ux_walk.py` does this pass. It:

- reads the **declared** screens from `app.js`'s `ROUTES` and crawls the
  **reached** ones by following links from the home page, and reports each
  difference by name. A screen nothing links to is a finding; so is a link to a
  route nobody declared.
- captures every reached page at **phone and desktop width**, in **light and
  dark**. Most of this surface's layout faults live in one cell of that grid.
- records each page's headings, controls and outbound links, which is the raw
  material for "what can I do here, and where can I go".
- runs an accessibility scan on every page.
- writes a **contact sheet**: every screen side by side. Inconsistency between
  screens is invisible one screen at a time and obvious side by side.

**Run it at two scales.** `--synthetic 2000` boots a throwaway server over the
suite's large corpus; `--base-url` walks a real deployment. Layout that works at
forty works breaks at two thousand, and synthetic titles hide what real ones
reveal (long names, missing dates, odd aspect ratios). The synthetic corpus has
no pictures, so the harness paints a flat placeholder for each thumbnail and the
sheet says so. A screen that never paints, or never lets the network rest, is
photographed anyway and listed by name: the walk exists to find such screens,
so one never ends it.

**It cannot write.** The harness aborts every request that is not `GET` or
`HEAD` and lists what it refused, which is what makes pointing it at the real
library safe — and what lets it click. Much of this client navigates by buttons
that call the router rather than by links, so on each page the harness clicks a
sample of buttons (as many of each kind as `--per-screen`, two by default) and keeps those that change the address.
A write such a click attempts is refused and tagged with the button; a write a
page attempts merely by being viewed is listed apart, and is a finding. After a
run against the real library, confirm on the server that nothing a probe
clicked (Accept, Rename, Unassign) took effect: the guard is the browser's,
and the server's own state is the evidence that it held. A screen whose interesting state is behind an action (Review mid-verdict,
a Get in flight) is reached in Pass 2, by hand.

```sh
cd arrt && uv sync --group browser          # once, with `playwright install chromium`
cd arrt && uv run python tools/ux_walk.py --synthetic 2000 --out ../.ux-walk/synthetic
cd arrt && uv run python tools/ux_walk.py --base-url http://<host>:<port> --out ../.ux-walk/real
```

`.ux-walk/` is gitignored: the repository is public and the screenshots are
working material, not records.

## Pass 2 — Walk the scenarios through the built product

Take the scenarios in `user-scenarios.md` § Tested against three requests and
the flows in `information-architecture.md` § User Flows. Do each one in the
real product and log every click, wait, decision, and moment of "where now?".
Then compare with the path `ia-proposal.md` § The scenarios, walked predicted.
**The differences are the findings** — a predicted path the product does not
offer, or an extra step nobody designed.

## Pass 3 — Critique, one lens per reviewer

Each lens is run by a separate reviewer who does not see the others' notes, for
the same reason the Critic is independent: a reviewer who has read another's
findings looks for those.

| Lens | Asks | Against |
|---|---|---|
| Usability | Can a person tell what to do, see what happened, and recover? | Nielsen's ten heuristics |
| *arr familiarity | Does a Sonarr/Radarr user find each page where they expect it? | `information-architecture.md` § Direction, beside Sonarr/Radarr screenshots |
| Design direction | Does it read as a museum, not a gadget? Hierarchy, density, rhythm | `design-direction.md` |
| Vocabulary | Is one idea one word everywhere — sidebar, heading, button, empty state, MCP? | the screens' own text, from the inventory |
| Accessibility | Keyboard-only path, focus, names, contrast, screen-reader spot check | `accessibility-spec.md`, plus Pass 1's scan |

A model reviewing screenshots is good at heuristics and consistency and weak at
what a task *feels* like; weight its findings accordingly and say which lens
produced each.

## Pass 4 — People

Nothing above replaces this, and no agent can do it.

- **The operator's friction log.** A week of ordinary use, one line each time
  something annoys, with the address bar's contents.
- **Someone who has never seen it** — ideally a member of the household whose
  wall it runs. Three tasks, thinking aloud, nobody helping. One or two such
  sessions find what every pass above cannot.

## Synthesis

One ranked list, not one per pass. Rank by **severity × how often it bites ×
whether it sits on a core flow**. Each finding carries:

- the screen and its address, and the screenshot that shows it;
- the lens or pass that found it;
- the scenario or flow it blocks, if any;
- **whether a ruling already plans its fix** — `ia-proposal.md` § Rulings or a
  build plan. The surface is often mid-move, and a walkthrough that does not tag
  this re-litigates decisions the owner has made.

Then route by kind, because each kind has a different owner:

- **Structure** (navigation, naming, placement) → `ia-proposal.md`, for a
  ruling. It binds through `information-architecture.md` § Direction.
- **Interaction, visual, copy** → the backlog, through `/prawduct:backlog`.

The run's report lives in `.prawduct/artifacts/ux-review-<yyyy-mm>.md`.

Before citing a backlog item as covering a finding, resolve it
(`prawduct-hook backlog cache-query resolve <n> --repo brookstalley/arrt`): a search hit can be shipped,
and a shipped item cited as "planned" hides an open defect.

## Running Passes 2 and 3 with agents

One agent per lens, plus one for Pass 2, launched together. Each gets the same
brief and only its own lens; none sees another's output. What the brief must
say, because each line closed a gap the first run found:

- **What the product is**, in three sentences, and that the browser client is
  its only human interface, laid out like the *arr apps by the owner's ruling.
- **Where Pass 1's evidence is** (`.ux-walk/<run>/index.html`, `inventory.json`,
  `shots/`), and that the screenshots are the primary evidence: read them as
  images, real library first, synthetic for scale.
- **Read-only, absolutely.** The live product may be browsed only through a
  Playwright context wrapped by `ux_walk.guard_writes`; nothing but `GET` by
  any other client. A path that needs a write stops there and is recorded as
  "continues past a write — Pass 4".
- **Judge what renders, not what the artifacts say.** Read only the artifact the
  lens names, and the Pass 2 agent reads the predicted paths last.
- **One finding format**: screen and address, evidence (a screenshot path or the
  steps), what a person experiences, the heuristic or rule it breaks, severity
  1–4, frequency, core flow, kind (structure, interaction, visual, copy,
  accessibility), and an optional suggestion. Then up to five things that work
  well, and the review's limits.
- **Write only to the given output file**; nothing in the repository.

The lenses' own instructions are the table in § Pass 3, plus, for
accessibility, a keyboard-only walk of the core screens through the guard, and
for vocabulary, a term table built from the inventory before reading
`ia-proposal.md` § Objects. Expect each to take ten to fifteen minutes.

**The synthetic corpus has works and nothing else** — no themes, runs, history
or walls — so Themes, History and To review at scale are extrapolated until
the corpus grows them. Say so in the report's limits.
